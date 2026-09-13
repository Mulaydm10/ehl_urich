"""
assistant.py — the server-side voice/chat assistant.

The phone sends a sentence, OpenAI decides which of this app's own functions to
call, this module executes them against the same FLOWSTATE engine and BMW
services the REST API uses, and OpenAI narrates the result. The reply carries
both the spoken sentence and any UI action (open a screen, select a bike) so
the app can drive itself from voice.

    phone -> POST /api/assistant -> OpenAI tool calls -> ENGINE / CLOUD
          <- {say, actions, tools_used}

The key lives here, server-side, in OPENAI_API_KEY (or a key file pointed at by
OPENAI_API_KEY_FILE). It is never shipped in the APK. With no key configured,
/api/assistant/status reports enabled=false and the app falls back to its
on-device intent matcher instead of pretending to be an LLM.

Only the stdlib is used to reach OpenAI, so the API keeps its existing
dependency set (fastapi + pydantic).
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable

# Override to route through a compatible gateway (Azure OpenAI, a proxy) or a
# local stub when testing the tool loop without spending a real key.
OPENAI_URL = os.environ.get(
    "OPENAI_URL", "https://api.openai.com/v1/chat/completions",
)
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
MAX_TOOL_ROUNDS = 4
REQUEST_TIMEOUT = 45
# A rider mid-sentence will not wait out a rate limit, but one quick retry
# rescues the 429s and 5xxs that clear on their own.
RETRY_STATUS = (408, 409, 429, 500, 502, 503, 504)
RETRY_PAUSE_S = 1.5
# What one tool result may cost the model. Results are summarised before they
# are sent, so this is a backstop, not the usual shape.
TOOL_RESULT_CHARS = 4000

# Realtime speech-to-speech. The phone holds the audio leg directly with
# OpenAI over WebRTC, so the key must never leave this process: the app asks
# for a short-lived client secret here and uses that instead.
REALTIME_SESSIONS_URL = os.environ.get(
    "OPENAI_REALTIME_SESSIONS_URL", "https://api.openai.com/v1/realtime/client_secrets",
)
REALTIME_CALLS_URL = os.environ.get(
    "OPENAI_REALTIME_CALLS_URL", "https://api.openai.com/v1/realtime/calls",
)
REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")
REALTIME_VOICE = os.environ.get("OPENAI_REALTIME_VOICE", "alloy")
REALTIME_DISABLED = os.environ.get("OPENAI_REALTIME", "").lower() in ("0", "off", "false")

SYSTEM_PROMPT = """You are the ride assistant inside a BMW Motorrad rider app.

You speak to a motorcyclist who is usually helmeted and moving, so answer in one
or two short spoken sentences. No markdown, no lists, no emoji. Numbers should be
said the way a person would say them ("about four hundred and twelve kilometres"
is fine as "412 kilometres").

You can call this app's own functions to read real data and to drive the UI.
Never invent range, fuel, tyre pressure, service dates, distances or route
numbers - call the function and use what it returns. If a function reports that
something is unavailable, say so plainly instead of guessing.

Route planning runs on FLOWSTATE, which scores roads by how well their lean-angle
demand matches this rider's skill. It only covers Bavaria (latitude 47.38 to
48.03, longitude 10.72 to 11.96); outside that, say so rather than planning.
Thrill is a number from 0 to 1: 0.15 cruise, 0.50 flow, 0.90 send it. Modes are
flow, scenic and mountain.

Place names you can use directly: {places}. Any other name has to be given as
latitude and longitude, so if the rider names somewhere else, say you cannot
place it and offer the nearest of these instead of guessing coordinates.

A planned route comes back summarised: distance, riding time, fun score, the
lean angle it asks for, and the roads it refused. Those refusals are the
rider's own safety gate and are not negotiable - report them, never offer to
plan around them.

When the rider asks to see or plan something, call the function and also call
open_screen so the app shows the result. Routes from plan_route and plan_loop
are drawn on the "thrill" screen, so that is the screen to open after planning.

While the rider is moving the app sends its live position and the plan being
followed as app context. When the complaint is about the road they are on
right now - "this is boring", "too much for me", "get me off this road",
"something nicer" - call reroute_from_here, never plan_route: only
reroute_from_here knows where they are and what they were following. It re-
plans from the current position to the same destination and reports how much
of the old line the new one still uses; say that number rather than promising
a road you have not been told about.

For "anywhere nice on the way?" mid-ride, call stops_ahead: it returns the
crowd's best corners that lie near the road still to be ridden, with how far
ahead each one is. Only those are on the way; suggest_stops is for planning
before setting off.
"""

# Places inside the FLOWSTATE coverage box, so spoken place names resolve
# without a geocoder. (lat, lon)
PLACES: dict[str, tuple[float, float]] = {
    "munich": (48.010, 11.560),
    "muenchen": (48.010, 11.560),
    "starnberg": (47.997, 11.341),
    "tutzing": (47.909, 11.283),
    "murnau": (47.681, 11.201),
    "kochel": (47.660, 11.369),
    "walchensee": (47.583, 11.331),
    "sylvenstein": (47.573, 11.510),
    "bad toelz": (47.761, 11.556),
    "lenggries": (47.683, 11.571),
    "tegernsee": (47.713, 11.757),
    "schliersee": (47.735, 11.859),
    "bayrischzell": (47.674, 12.012),
    "garmisch": (47.492, 11.095),
    "partenkirchen": (47.492, 11.095),
    "mittenwald": (47.442, 11.261),
    "oberammergau": (47.597, 11.066),
    "ettal": (47.570, 11.093),
    "kreuth": (47.647, 11.744),
    "achenpass": (47.600, 11.680),
    "kesselberg": (47.635, 11.333),
    "wallberg": (47.680, 11.760),
    "spitzingsee": (47.671, 11.885),
}

COVERAGE = {"lat": (47.38, 48.03), "lon": (10.72, 11.96)}

# How a mid-ride complaint moves the dial. Big enough that the rider feels the
# difference on the next corner; a 0.1 nudge is not worth interrupting a ride
# for.
REROUTE_STEP = 0.35
REROUTE_LOOP_HOURS = 1.5

# A stop further than this from the planned line is a detour, not a stop on
# the way, and saying otherwise mid-ride would be a lie the rider rides into.
CORRIDOR_M = 2500


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle metres between two (lat, lon) points."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def _known_places() -> str:
    """Distinct place names for the prompt; the dict holds spelling variants."""
    seen: dict[tuple[float, float], str] = {}
    for name, point in PLACES.items():
        seen.setdefault(point, name)
    return ", ".join(sorted(seen.values()))


def _system_prompt() -> str:
    return SYSTEM_PROMPT.format(places=_known_places())


def _place(name: str) -> tuple[float, float] | None:
    key = name.strip().lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    if key in PLACES:
        return PLACES[key]
    for k, v in PLACES.items():
        if k in key or key in k:
            return v
    return None


def _point(value: Any) -> tuple[float, float] | dict[str, str]:
    """Accept either a place name or [lat, lon] from the model."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lat, lon = float(value[0]), float(value[1])
    elif isinstance(value, str):
        hit = _place(value)
        if not hit:
            return {"error": f"I don't know where {value} is.",
                    "known_places": _known_places()}
        lat, lon = hit
    elif isinstance(value, dict) and "lat" in value and "lon" in value:
        lat, lon = float(value["lat"]), float(value["lon"])
    else:
        return {"error": "Give a place name or a latitude and longitude."}
    if not (COVERAGE["lat"][0] <= lat <= COVERAGE["lat"][1]
            and COVERAGE["lon"][0] <= lon <= COVERAGE["lon"][1]):
        return {"error": "That is outside the Bavarian area FLOWSTATE covers."}
    return (lat, lon)


# --------------------------------------------------------------------------
# tool schemas exposed to the model
# --------------------------------------------------------------------------

SCREENS = ["ride", "plan", "thrill", "navigate", "discover", "garage", "group",
           "maps", "handoff", "more"]

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "plan_route",
            "description": "Plan a fun-fit route from A to B with FLOWSTATE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Place name or 'lat,lon'"},
                    "end": {"type": "string", "description": "Place name or 'lat,lon'"},
                    "thrill": {"type": "number", "description": "0 to 1; 0.15 cruise, 0.5 flow, 0.9 send it"},
                    "mode": {"type": "string", "enum": ["flow", "scenic", "mountain"]},
                    "rider_key": {"type": "string"},
                },
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_loop",
            "description": "Plan a round trip of roughly N hours starting and ending at one place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "hours": {"type": "number"},
                    "thrill": {"type": "number"},
                    "mode": {"type": "string", "enum": ["flow", "scenic", "mountain"]},
                    "rider_key": {"type": "string"},
                },
                "required": ["start", "hours"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reroute_from_here",
            "description": (
                "Re-plan from where the rider is right now, mid-ride. Use this "
                "for any complaint about the road they are on ('this is "
                "boring', 'too much', 'get me off this road') or any request "
                "for an alternative now. The app supplies the live position "
                "and the plan being followed; you only choose how it should "
                "change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "change": {
                        "type": "string",
                        "enum": ["more_fun", "calmer", "scenic", "mountain",
                                 "avoid_this_road", "same"],
                        "description": (
                            "more_fun raises the thrill dial, calmer lowers it, "
                            "scenic and mountain switch mode, avoid_this_road "
                            "searches the variants for the line that shares "
                            "least road with the current one, same re-plans "
                            "unchanged from here."
                        ),
                    },
                    "destination": {
                        "type": "string",
                        "description": (
                            "Only when the rider names a new one. Otherwise the "
                            "destination of the plan they are following is kept."
                        ),
                    },
                    "hours": {
                        "type": "number",
                        "description": "Loop length when there is no destination to keep.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "The rider's own words, kept with the result.",
                    },
                },
                "required": ["change"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stops_ahead",
            "description": (
                "Scenic stops on the road still ahead of the rider, with the "
                "distance to each along the plan. Mid-ride only; the app "
                "supplies the position and the plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "within_km": {
                        "type": "number",
                        "description": "How far ahead to look. Default 40.",
                    },
                    "count": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_routes",
            "description": "Compare a calm and a spirited route between two places.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "mode": {"type": "string", "enum": ["flow", "scenic", "mountain"]},
                    "rider_key": {"type": "string"},
                },
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_stops",
            "description": "Suggest scenic roads and stops that fit this rider, optionally near a place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "thrill": {"type": "number"},
                    "mode": {"type": "string", "enum": ["flow", "scenic", "mountain"]},
                    "rider_key": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "garage",
            "description": "List the bikes in the rider's garage with range, fuel and connection state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bike_status",
            "description": "Full status for one bike: range, fuel, tyres, odometer, service, doors of the app's vehicle status card.",
            "parameters": {
                "type": "object",
                "properties": {"bike_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "season_stats",
            "description": "Season totals: distance, ride count, lean angle, time in the saddle.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_rides",
            "description": "Recorded rides, most recent first.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ride_debrief",
            "description": "Details of one recorded ride for a coaching summary. Omit ride_id for the latest ride.",
            "parameters": {
                "type": "object",
                "properties": {"ride_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_ride",
            "description": "Start recording a ride on a bike.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bike_id": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_ride",
            "description": "Stop the ride that is currently recording.",
            "parameters": {
                "type": "object",
                "properties": {"ride_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group_ride",
            "description": "State of the current group ride and who is in it.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "offline_maps",
            "description": "Offline map regions and their download state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_route",
            "description": "Send a planned route to the bike's TFT. Returns a stand-in result; no bike is actually contacted yet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "string"},
                    "bike_id": {"type": "string"},
                },
                "required": ["route_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_screen",
            "description": "Show a screen in the app.",
            "parameters": {
                "type": "object",
                "properties": {"screen": {"type": "string", "enum": SCREENS}},
                "required": ["screen"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_bike",
            "description": "Make a bike the active one in the app.",
            "parameters": {
                "type": "object",
                "properties": {"bike_id": {"type": "string"}},
                "required": ["bike_id"],
            },
        },
    },
]


def _realtime_tools() -> list[dict[str, Any]]:
    """The same tools, in the flat shape the realtime API expects."""
    return [{"type": "function", **t["function"]} for t in TOOLS]


def _actions_for(name: str, result: Any) -> list[dict[str, Any]]:
    """What the app should do after a tool ran. Shared by the chat loop and
    the realtime session so voice and text drive the UI identically."""
    if not isinstance(result, dict) or not result.get("ok"):
        return []
    if name in ("plan_route", "plan_loop", "reroute_from_here"):
        # The model only gets a truncated summary; the app gets the whole plan
        # so it can draw the route it was just told about.
        return [{"type": "show_route", "plan": result}]
    if name == "open_screen":
        return [{"type": "navigate", "screen": result["screen"]}]
    if name == "select_bike":
        return [{"type": "select_bike", "bikeId": result["bike"]["id"]}]
    return []


def _reroute_variants(change: str, thrill: float, mode: str) -> list[tuple[float, str]]:
    """(thrill, mode) settings to plan, best guess first.

    `avoid_this_road` gets the whole list because it is a search: the engine
    cannot be told to forbid a road, so the only way off one is to ask for a
    different enough ride that the router picks another line.
    """
    up = min(0.90, round(thrill + REROUTE_STEP, 2))
    down = max(0.15, round(thrill - REROUTE_STEP, 2))
    if change == "more_fun":
        return [(up, mode)]
    if change == "calmer":
        return [(down, mode)]
    if change in ("scenic", "mountain"):
        return [(thrill, change)]
    if change == "avoid_this_road":
        return [(up, mode), (thrill, "scenic"), (thrill, "mountain"), (down, mode)]
    return [(thrill, mode)]


def _candidates(plans: list[dict[str, Any]], won: dict[str, Any] | None,
                change: str) -> list[dict[str, Any]]:
    """Every variant that was planned, with the engine's plan and the reason
    it was kept or dropped. `won` is the winning entry of the search, or None
    when nothing planned. Purely a readout of what t_reroute_from_here did."""
    out: list[dict[str, Any]] = []
    win_idx = won.get("index") if won else None
    win_share = won.get("shares_current_road") if won else None
    for p in plans:
        plan = p["plan"]
        summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
        share = p.get("shares_current_road")
        if not p["ok"]:
            verdict, why = "failed", f"engine returned no route: {p.get('note') or 'no note'}"
        elif p["index"] == win_idx:
            if change == "avoid_this_road":
                why = ("lowest share of the current road among the variants"
                       if share is not None else
                       "no current plan loaded, so overlap is unknown; first planned variant kept")
            else:
                why = "first variant in the order that planned; the one the change asked for"
            verdict = "accepted"
        elif not p["in_search"]:
            verdict = "not_searched"
            why = ("the live tool stops at the first successful variant; planned here only "
                   "because the dashboard asked for every variant")
        elif change == "avoid_this_road" and share is not None and win_share is not None:
            verdict = "rejected"
            why = (f"shares {share:.0%} of the current road, the winner shares {win_share:.0%}"
                   if share > win_share else
                   f"same {share:.0%} share as the winner; the earlier variant in the order is kept")
        else:
            verdict, why = "rejected", "a later variant ranked better in the search"
        out.append({
            "index": p["index"], "thrill": p["thrill"], "mode": p["mode"],
            "ok": p["ok"], "in_search": p["in_search"], "verdict": verdict, "why": why,
            "shares_current_road": share,
            "km": summary.get("km"), "minutes": summary.get("minutes"),
            "fun_score": summary.get("fun_score"),
            "mean_demand": summary.get("mean_demand"), "max_demand": summary.get("max_demand"),
            "path": plan.get("path") or [], "cells": plan.get("cells") or [],
            "segments": plan.get("segments") or [],
            "refusals": plan.get("refusals") or [], "summary": summary,
            "explain": plan.get("explain") or [], "note": plan.get("note"),
        })
    return out


def _route_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """A route as the model needs to hear it, not as the map needs to draw it.

    A plan carries a few hundred path points and cell ids. Sent whole they
    crowd out the numbers that matter and get cut mid-token by the size cap,
    which is how a model ends up narrating half a distance. The app still
    receives the full plan through the show_route action.
    """
    summary = result.get("summary")
    slim: dict[str, Any] = {
        "ok": result.get("ok"),
        "note": result.get("note"),
        "rider": result.get("rider"),
        "thrill": result.get("z_star"),
        "points_in_path": len(result.get("path") or []),
        "summary": summary if isinstance(summary, dict) else None,
        "explain": (result.get("explain") or [])[:6],
    }
    refusals = result.get("refusals") or []
    if refusals:
        reasons: list[str] = []
        for r in refusals:
            reason = str(r.get("reason", "")) if isinstance(r, dict) else str(r)
            if reason and reason not in reasons:
                reasons.append(reason)
        slim["refused_roads"] = len(refusals)
        slim["refusal_reasons"] = reasons[:4]
    return slim


def _for_model(name: str, result: Any) -> Any:
    """Shrink a tool result to what can be said out loud."""
    if not isinstance(result, dict):
        return result
    if name in ("plan_route", "plan_loop", "reroute_from_here") and "path" in result:
        slim = _route_for_model(result)
        if "reroute" in result:
            slim["reroute"] = result["reroute"]
        return slim
    if name == "compare_routes":
        return {
            key: _route_for_model(value) if isinstance(value, dict) and "path" in value else value
            for key, value in result.items()
        }
    return result


# --------------------------------------------------------------------------
# tool execution against the same engine + cloud the REST API uses
# --------------------------------------------------------------------------

class Assistant:
    def __init__(self, engine: Any, cloud: Any, engine_kind: str) -> None:
        self.engine = engine
        self.cloud = cloud
        self.engine_kind = engine_kind
        self.model = DEFAULT_MODEL
        # Observers of every tool run: (name, args, ride, result, source).
        # The viz dashboard's live feed hangs off this; nothing else does.
        self.on_tool: list[Callable[[str, dict[str, Any], dict[str, Any] | None, Any, str], None]] = []

    def _notify(self, name: str, args: dict[str, Any], ride: dict[str, Any] | None,
                result: Any, source: str) -> None:
        for fn in self.on_tool:
            try:
                fn(name, args, ride, result, source)
            except Exception:  # noqa: BLE001 - a watcher must never break a turn
                pass

    # -- key ---------------------------------------------------------------

    @staticmethod
    def api_key() -> str | None:
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key.strip()
        path = os.environ.get("OPENAI_API_KEY_FILE")
        if path and os.path.exists(path):
            return open(path, encoding="utf-8").read().strip() or None
        return None

    def enabled(self) -> bool:
        return bool(self.api_key())

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "model": self.model if self.enabled() else None,
            "engine": self.engine_kind,
            "tools": [t["function"]["name"] for t in TOOLS],
            "reason": None if self.enabled() else "OPENAI_API_KEY is not set on the server",
            "realtime": {
                "enabled": self.enabled() and not REALTIME_DISABLED,
                "model": REALTIME_MODEL if self.enabled() and not REALTIME_DISABLED else None,
                "voice": REALTIME_VOICE,
            },
        }

    # -- tools -------------------------------------------------------------

    def _bike(self, bike_id: str | None) -> dict[str, Any] | None:
        bikes = self.cloud.get_bikes()
        if not bikes:
            return None
        if bike_id:
            for b in bikes:
                if b.get("id") == bike_id or bike_id.lower() in str(b.get("name", "")).lower():
                    return b
        for b in bikes:
            if b.get("connected"):
                return b
        return bikes[0]

    def t_plan_route(self, a: dict[str, Any]) -> Any:
        s, e = _point(a.get("start")), _point(a.get("end"))
        if isinstance(s, dict):
            return s
        if isinstance(e, dict):
            return e
        return self.engine.route(list(s), list(e), a.get("rider_key", "userA"),
                                 float(a.get("thrill", 0.5)), mode=a.get("mode", "flow"))

    def t_plan_loop(self, a: dict[str, Any]) -> Any:
        s = _point(a.get("start"))
        if isinstance(s, dict):
            return s
        return self.engine.loop(list(s), float(a.get("hours", 2.0)),
                                a.get("rider_key", "userA"), float(a.get("thrill", 0.5)),
                                mode=a.get("mode", "flow"))

    def t_reroute_from_here(self, a: dict[str, Any]) -> Any:
        """Re-plan from the rider's live position, mid-ride.

        The rider complains about the road they are on; the model picks a
        direction of travel for the change and this does the rest. Where they
        are and what they were following come from the app's ride context, not
        from the model — a model that guesses a position while the bike is
        moving is worse than no answer.

        `avoid_this_road` is the interesting one. The engine has no
        "forbid these roads" mode, so instead of pretending otherwise we plan
        every variant we do have and keep the one that reuses least of the
        line ahead, then report that share. "About a third of it is the same
        road" is a true answer; silently returning the same road is not.
        """
        ride = a.get("_ride") or {}
        try:
            here = [float(ride["lat"]), float(ride["lon"])]
        except (KeyError, TypeError, ValueError):
            return {"error": "I don't have a live position, so I cannot re-plan "
                             "from here. Start the co-pilot on the Navigate "
                             "screen and let it get a GPS fix.",
                    "needs": "live position"}
        if not (COVERAGE["lat"][0] <= here[0] <= COVERAGE["lat"][1]
                and COVERAGE["lon"][0] <= here[1] <= COVERAGE["lon"][1]):
            return {"error": "You are outside the Bavarian area FLOWSTATE "
                             "covers, so there is nothing scored here to "
                             "re-plan onto.",
                    "position": here}

        rider_key = str(ride.get("rider_key") or a.get("rider_key") or "userA")
        thrill = float(ride.get("thrill") or 0.5)
        mode = str(ride.get("mode") or "flow")
        route = ride.get("route") or {}
        ahead = {str(c) for c in (route.get("cells") or [])}

        dest: list[float] | None = None
        if a.get("destination"):
            hit = _point(a["destination"])
            if isinstance(hit, dict):
                return hit
            dest = [hit[0], hit[1]]
        elif route.get("destination"):
            d = route["destination"]
            dest = [float(d[0]), float(d[1])]

        # A complaint is about the road being ridden towards somewhere. With no
        # plan loaded and no destination given there is nothing to keep, and a
        # loop from here is a different ride than the one asked for — so it is
        # only planned when the caller asked for one by naming its length.
        if dest is None and not a.get("hours"):
            return {"error": "You are not following a plan, so there is nothing "
                             "to re-plan. Give me a destination, or ask for a "
                             "loop of a certain length.",
                    "needs": "destination or loop hours"}

        change = str(a.get("change") or "same")
        variants = _reroute_variants(change, thrill, mode)
        # The dashboard asks to see every variant, including the ones the
        # live tool would never have planned. Which one wins is unchanged.
        keep_all = bool(a.get("candidates"))

        tried: list[dict[str, Any]] = []
        plans: list[dict[str, Any]] = []
        best: tuple[float, dict[str, Any], dict[str, float | str]] | None = None
        searching = True
        for i, (z, m) in enumerate(variants):
            if not searching and not keep_all:
                break
            plan = (self.engine.route(here, dest, rider_key, z, mode=m) if dest
                    else self.engine.loop(here, float(a.get("hours") or REROUTE_LOOP_HOURS),
                                          rider_key, z, mode=m))
            entry: dict[str, Any] = {"index": i, "thrill": z, "mode": m,
                                     "ok": bool(plan.get("ok")), "in_search": searching}
            if not plan.get("ok"):
                tried.append({"thrill": z, "mode": m, "ok": False,
                              "note": plan.get("note")})
                plans.append({**entry, "note": plan.get("note"), "plan": plan})
                continue
            cells = {str(c) for c in (plan.get("cells") or [])}
            shared = (len(cells & ahead) / len(cells)) if cells and ahead else None
            plans.append({**entry, "shares_current_road": shared, "plan": plan})
            if not searching:
                continue
            tried.append({"thrill": z, "mode": m, "ok": True,
                          "km": (plan.get("summary") or {}).get("km"),
                          "shares_current_road": shared})
            # Lowest overlap wins when the rider wants off this road; otherwise
            # the first variant is the one they asked for.
            rank = shared if (change == "avoid_this_road" and shared is not None) else 0.0
            if best is None or rank < best[0]:
                best = (rank, plan, {"thrill": z, "mode": m,
                                     "shares_current_road": shared, "index": i})
            if change != "avoid_this_road":
                searching = False

        if best is None:
            out_err: dict[str, Any] = {"error": "The engine could not plan anything from here.",
                                       "tried": tried}
            if keep_all:
                out_err["candidates"] = _candidates(plans, None, change)
            return out_err

        _, plan, won = best
        extra = {"candidates": _candidates(plans, won, change)} if keep_all else {}
        return {**plan, **extra, "reroute": {
            "change": change,
            "reason": a.get("reason"),
            "from": here,
            "destination": dest,
            "kept_destination": bool(dest) and not a.get("destination"),
            "thrill_from": thrill, "thrill_to": won["thrill"],
            "mode_from": mode, "mode_to": won["mode"],
            "shares_current_road": won["shares_current_road"],
            "variants_tried": tried,
            "note": ("Share of the new line that is road you were already "
                     "going to ride; null when no current plan was loaded."),
        }}

    def t_stops_ahead(self, a: dict[str, Any]) -> Any:
        """Crowd gems that are actually on the road still to be ridden.

        `suggest_stops` answers "where is nice around here", which mid-ride
        sends the rider backwards as often as forwards. This walks the plan's
        own line from the rider's position onward and keeps only gems close to
        it, so "on the way" means on the way. Distance is measured along the
        line, not straight-line, because that is the number the rider will
        watch count down.
        """
        ride = a.get("_ride") or {}
        try:
            here = (float(ride["lat"]), float(ride["lon"]))
        except (KeyError, TypeError, ValueError):
            return {"error": "I don't have a live position, so I cannot tell "
                             "what is ahead.", "needs": "live position"}

        line = [(float(p[0]), float(p[1]))
                for p in ((ride.get("route") or {}).get("line") or [])
                if isinstance(p, (list, tuple)) and len(p) == 2]
        if len(line) < 2:
            return {"error": "No route is being followed, so nothing is "
                             "'ahead'. Plan one first, or ask for stops near "
                             "a place.", "needs": "active route"}

        within_m = float(a.get("within_km") or 40.0) * 1000.0
        start = min(range(len(line)), key=lambda i: _metres(here, line[i]))

        # Distance along the remaining line, point by point.
        along = [0.0] * len(line)
        for i in range(start + 1, len(line)):
            along[i] = along[i - 1] + _metres(line[i - 1], line[i])

        gems = self.engine.gem_pool(str(ride.get("rider_key") or "userA"),
                                    float(ride.get("thrill") or 0.5), 40,
                                    "scenic")
        out: list[dict[str, Any]] = []
        for gem in gems:
            if not gem.get("routable", True) or gem.get("gated"):
                continue
            at = (float(gem["lat"]), float(gem["lon"]))
            near_i, off = min(
                ((i, _metres(at, line[i])) for i in range(start, len(line))),
                key=lambda pair: pair[1])
            if off > CORRIDOR_M or along[near_i] > within_m:
                continue
            out.append({"lat": at[0], "lon": at[1],
                        "gem_score": gem.get("gem_score"),
                        "flow": gem.get("flow"),
                        "demand_p90": gem.get("demand_p90"),
                        "km_ahead": round(along[near_i] / 1000.0, 1),
                        "off_route_m": round(off)})
        out.sort(key=lambda g: g["km_ahead"])
        return {"stops": out[: int(a.get("count") or 5)],
                "within_km": within_m / 1000.0,
                "corridor_m": CORRIDOR_M,
                "note": ("Crowd-rated corners within %d m of the line still "
                         "ahead; distance is measured along the route."
                         % CORRIDOR_M)}

    def t_compare_routes(self, a: dict[str, Any]) -> Any:
        s, e = _point(a.get("start")), _point(a.get("end"))
        if isinstance(s, dict):
            return s
        if isinstance(e, dict):
            return e
        return self.engine.compare(list(s), list(e), a.get("rider_key", "userA"),
                                   0.15, 0.90, mode=a.get("mode", "flow"))

    def t_suggest_stops(self, a: dict[str, Any]) -> Any:
        gems = self.engine.gem_pool(a.get("rider_key", "userA"),
                                    float(a.get("thrill", 0.5)),
                                    int(a.get("count", 8)), a.get("mode", "scenic"))
        near = a.get("near")
        if near:
            hit = _place(str(near))
            if hit:
                return {"near": near, "at": list(hit), "gems": gems}
        return {"gems": gems}

    def t_garage(self, _a: dict[str, Any]) -> Any:
        return self.cloud.get_bikes()

    def t_bike_status(self, a: dict[str, Any]) -> Any:
        bike = self._bike(a.get("bike_id"))
        if not bike:
            return {"error": "No bikes in the garage."}
        return {"bike": bike, "status": self.cloud.vehicle_status(bike["id"])}

    def t_season_stats(self, _a: dict[str, Any]) -> Any:
        return self.cloud.get_stats()

    def t_list_rides(self, a: dict[str, Any]) -> Any:
        rides = self.cloud.get_rides()
        return rides[: int(a.get("limit", 5))]

    def t_ride_debrief(self, a: dict[str, Any]) -> Any:
        rides = self.cloud.get_rides()
        if not rides:
            return {"error": "No rides recorded yet."}
        ride_id = a.get("ride_id")
        for r in rides:
            if r.get("id") == ride_id:
                return r
        return rides[0]

    def t_start_ride(self, a: dict[str, Any]) -> Any:
        bike = self._bike(a.get("bike_id"))
        if not bike:
            return {"error": "No bikes in the garage."}
        return self.cloud.start_recording(bike["id"], a.get("title", ""))

    def t_stop_ride(self, a: dict[str, Any]) -> Any:
        ride_id = a.get("ride_id")
        if not ride_id:
            live = self.cloud.live_rides()
            if not live:
                return {"error": "No ride is recording."}
            ride_id = live[-1]["id"]
        return self.cloud.stop_recording(ride_id)

    def t_group_ride(self, _a: dict[str, Any]) -> Any:
        return self.cloud.get_group()

    def t_offline_maps(self, _a: dict[str, Any]) -> Any:
        return self.cloud.get_regions()

    def t_handoff_route(self, a: dict[str, Any]) -> Any:
        bike = self._bike(a.get("bike_id"))
        res = self.cloud.handoff(a["route_id"], bike["id"] if bike else "")
        return {**res, "note": "stand-in: nothing was sent to a physical bike"}

    def t_open_screen(self, a: dict[str, Any]) -> Any:
        screen = str(a.get("screen", "")).lower()
        if screen not in SCREENS:
            return {"error": f"No screen called {screen}."}
        return {"ok": True, "screen": screen}

    def t_select_bike(self, a: dict[str, Any]) -> Any:
        bike = self._bike(a.get("bike_id"))
        if not bike:
            return {"error": "No such bike."}
        return {"ok": True, "bike": bike}

    def run_tool(self, name: str, args: dict[str, Any],
                 context: dict[str, Any] | None = None, record: bool = True,
                 source: str = "tool") -> dict[str, Any]:
        """Execute one tool by name. Used by both the chat loop and the
        realtime session, whose tool calls arrive from the phone. `record=False`
        keeps the run out of `on_tool` — for read-only callers such as the viz
        dashboard, whose own lookups are not something the phone did.

        The live ride — where the bike is and which plan it is following —
        travels as `_ride` from the app context rather than as tool arguments.
        It is the app's knowledge, and a model asked to repeat a moving
        position back to us would eventually get it wrong.
        """
        handler = self.handlers().get(name)
        if handler is None:
            err = {"error": f"unknown tool {name}"}
            return {"ok": False, "result": err, "for_model": err, "actions": []}
        ride = (context or {}).get("ride")
        if ride:
            args = {**args, "_ride": ride}
        try:
            result = handler(args)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the turn
            err = {"error": f"{type(exc).__name__}: {exc}"}
            if record:
                self._notify(name, args, ride, err, source)
            return {"ok": False, "result": err, "for_model": err, "actions": []}
        if record:
            self._notify(name, args, ride, result, source)
        # result is what the app draws, for_model is what is worth speaking:
        # the realtime model reads its tool output over the data channel, so
        # it must not be handed a route's full geometry.
        return {"ok": True, "result": result, "for_model": _for_model(name, result),
                "actions": _actions_for(name, result)}

    def handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "plan_route": self.t_plan_route,
            "plan_loop": self.t_plan_loop,
            "reroute_from_here": self.t_reroute_from_here,
            "stops_ahead": self.t_stops_ahead,
            "compare_routes": self.t_compare_routes,
            "suggest_stops": self.t_suggest_stops,
            "garage": self.t_garage,
            "bike_status": self.t_bike_status,
            "season_stats": self.t_season_stats,
            "list_rides": self.t_list_rides,
            "ride_debrief": self.t_ride_debrief,
            "start_ride": self.t_start_ride,
            "stop_ride": self.t_stop_ride,
            "group_ride": self.t_group_ride,
            "offline_maps": self.t_offline_maps,
            "handoff_route": self.t_handoff_route,
            "open_screen": self.t_open_screen,
            "select_bike": self.t_select_bike,
        }

    # -- realtime voice ----------------------------------------------------

    def realtime_session(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Mint a short-lived client secret for a speech-to-speech session.

        The phone negotiates WebRTC straight with OpenAI using this secret, so
        audio never round-trips through the Mac. The tools and instructions are
        pinned here, not on the phone, so a client cannot widen what the model
        may do.
        """
        key = self.api_key()
        if not key:
            return {"ok": False, "error": "no_key",
                    "say": "The cloud assistant is not configured on the server."}
        if REALTIME_DISABLED:
            return {"ok": False, "error": "realtime_disabled",
                    "say": "Live voice is switched off on the server."}

        instructions = _system_prompt()
        if context:
            instructions += "\n\nCurrent app context: " + json.dumps(context)[:1500]
        body = json.dumps({
            "session": {
                "type": "realtime",
                "model": REALTIME_MODEL,
                "instructions": instructions,
                "tools": _realtime_tools(),
                "tool_choice": "auto",
                "audio": {
                    "input": {"transcription": {"model": "whisper-1"}},
                    "output": {"voice": REALTIME_VOICE},
                },
            },
        }).encode()
        req = urllib.request.Request(
            REALTIME_SESSIONS_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return {"ok": False, "error": f"openai_http_{exc.code}",
                    "detail": exc.read().decode()[:300],
                    "say": "I couldn't start live voice."}
        except Exception as exc:  # noqa: BLE001 - network/timeout are equivalent here
            return {"ok": False, "error": type(exc).__name__,
                    "say": "I couldn't start live voice."}

        secret = data.get("value")
        if not secret:
            return {"ok": False, "error": "no_client_secret",
                    "say": "I couldn't start live voice."}
        return {
            "ok": True,
            "client_secret": secret,
            "expires_at": data.get("expires_at"),
            "model": REALTIME_MODEL,
            "voice": REALTIME_VOICE,
            "calls_url": REALTIME_CALLS_URL,
        }

    # -- OpenAI ------------------------------------------------------------

    def _call_openai(self, messages: list[dict[str, Any]], key: str) -> dict[str, Any]:
        try:
            return self._post_openai(messages, key)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_STATUS:
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(RETRY_PAUSE_S)
        return self._post_openai(messages, key)

    def _post_openai(self, messages: list[dict[str, Any]], key: str) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            OPENAI_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    def ask(self, text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        key = self.api_key()
        if not key:
            return {"ok": False, "error": "no_key",
                    "say": "The cloud assistant is not configured on the server."}

        messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt()}]
        if context:
            messages.append({
                "role": "system",
                "content": "Current app context: " + json.dumps(context)[:1500],
            })
        messages.append({"role": "user", "content": text})

        handlers = self.handlers()
        # The live ride never goes to the model as a tool argument; tools read
        # it straight from the app context.
        ride = (context or {}).get("ride")
        actions: list[dict[str, Any]] = []
        used: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                data = self._call_openai(messages, key)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode()[:300]
                return {"ok": False, "error": f"openai_http_{exc.code}", "detail": detail,
                        "say": "I couldn't reach the assistant service."}
            except Exception as exc:  # noqa: BLE001 - network/timeout are equivalent here
                return {"ok": False, "error": type(exc).__name__,
                        "say": "I couldn't reach the assistant service."}

            choice = data["choices"][0]["message"]
            calls = choice.get("tool_calls") or []
            messages.append(choice)

            if not calls:
                return {
                    "ok": True,
                    "say": (choice.get("content") or "").strip(),
                    "actions": actions,
                    "tools_used": used,
                    "engine": self.engine_kind,
                }

            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                if ride:
                    args = {**args, "_ride": ride}
                handler = handlers.get(name)
                if handler is None:
                    result: Any = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = handler(args)
                    except Exception as exc:  # noqa: BLE001 - report, don't crash the turn
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                self._notify(name, args, ride, result, "ask")
                used.append(name)
                actions.extend(_actions_for(name, result))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(_for_model(name, result), default=str)[:TOOL_RESULT_CHARS],
                })

        return {"ok": True, "say": "That took too many steps, ask me something narrower.",
                "actions": actions, "tools_used": used, "engine": self.engine_kind}
