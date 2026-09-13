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
import os
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

When the rider asks to see or plan something, call the function and also call
open_screen so the app shows the result. Routes from plan_route and plan_loop
are drawn on the "thrill" screen, so that is the screen to open after planning.
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
            return {"error": f"I don't know where {value} is."}
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

SCREENS = ["ride", "plan", "thrill", "discover", "garage", "group", "maps",
           "handoff", "more"]

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


# --------------------------------------------------------------------------
# tool execution against the same engine + cloud the REST API uses
# --------------------------------------------------------------------------

class Assistant:
    def __init__(self, engine: Any, cloud: Any, engine_kind: str) -> None:
        self.engine = engine
        self.cloud = cloud
        self.engine_kind = engine_kind
        self.model = DEFAULT_MODEL

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

    def handlers(self) -> dict[str, Callable[[dict[str, Any]], Any]]:
        return {
            "plan_route": self.t_plan_route,
            "plan_loop": self.t_plan_loop,
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

    # -- OpenAI ------------------------------------------------------------

    def _call_openai(self, messages: list[dict[str, Any]], key: str) -> dict[str, Any]:
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

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if context:
            messages.append({
                "role": "system",
                "content": "Current app context: " + json.dumps(context)[:1500],
            })
        messages.append({"role": "user", "content": text})

        handlers = self.handlers()
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
                handler = handlers.get(name)
                if handler is None:
                    result: Any = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = handler(args)
                    except Exception as exc:  # noqa: BLE001 - report, don't crash the turn
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                used.append(name)
                if (name in ("plan_route", "plan_loop")
                        and isinstance(result, dict) and result.get("ok")):
                    # The model only gets a truncated summary; the app gets the
                    # whole plan so it can draw the route it was just told about.
                    actions.append({"type": "show_route", "plan": result})
                if name == "open_screen" and isinstance(result, dict) and result.get("ok"):
                    actions.append({"type": "navigate", "screen": result["screen"]})
                if name == "select_bike" and isinstance(result, dict) and result.get("ok"):
                    actions.append({"type": "select_bike", "bikeId": result["bike"]["id"]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, default=str)[:6000],
                })

        return {"ok": True, "say": "That took too many steps, ask me something narrower.",
                "actions": actions, "tools_used": used, "engine": self.engine_kind}
