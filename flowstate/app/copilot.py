"""
copilot.py — the assistant that speaks while you are riding, instead of
waiting to be asked.

Everything else in the app answers a question. This module watches the ride
and decides, on its own, when there is something worth saying. The hard part
is not generating a suggestion; it is NOT generating one. A co-pilot that
talks every twenty seconds is switched off before the first pass.

So the loop is deliberately split in two, and the model is on the quiet side
of the split:

    phone -> POST /api/copilot/tick {lat, lon, speed, heading, route, ...}
             |
             |  1. TRIGGERS   pure functions over position + the FLOWSTATE
             |                engine. They decide IF there is something to
             |                say and compute the actual numbers.
             |  2. GATE       cooldowns, dismissals, one suggestion per tick.
             |  3. NARRATION  OpenAI phrases the winning trigger in one
             |                spoken sentence — and may veto it.
             v
          {suggestion | null}

The model never plans, never invents a distance and never decides that a road
is dull: a trigger did that from the engine's own numbers, and the payload it
narrates already contains the sentence we would have said without it. That is
also why this degrades honestly — with no OPENAI_API_KEY the templated `say`
ships as-is and the co-pilot still works, it just sounds like a machine.

Why let the model veto at all: relevance is the one judgement the rules are
bad at. "There is a gem 3 km off your line" is correct and unwelcome when the
rider is 8 minutes from home in the rain at 19:40. The model sees the ride
context, and returning an empty sentence is an allowed answer — a cheap filter
on a trigger set that is otherwise tuned to over-fire.

State is per ride session, in memory, bounded. Nothing here is persisted: a
co-pilot that remembers yesterday's ride is a different feature with different
privacy questions.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

OPENAI_URL = os.environ.get("OPENAI_URL", "https://api.openai.com/v1/chat/completions")
NARRATOR_MODEL = os.environ.get("OPENAI_COPILOT_MODEL", "gpt-4o-mini")
NARRATOR_TIMEOUT = 12          # a suggestion that arrives late is noise
MAX_SESSIONS = 32
MAX_FIXES = 240                # ~80 minutes of riding at one fix per 20 s

# --- when the co-pilot is allowed to speak --------------------------------
QUIET_S = 150.0                # never two suggestions inside this
KIND_COOLDOWN_S = 600.0        # ... and never the same kind inside this
DISMISS_COOLDOWN_S = 1800.0    # a dismissed kind is parked for half an hour
MIN_FIX_GAP_S = 5.0            # ignore a phone that ticks faster than this

# --- trigger thresholds, all in SI-ish units the rest of the app uses -----
OFF_ROUTE_M = 150.0            # GPS scatter on a bike is ~10-30 m; 150 is real
OFF_ROUTE_STREAK = 2           # two consecutive fixes, so one bad fix is not a reroute
STOPPED_KMH = 3.0
STOPPED_S = 240.0
MOVING_KMH = 12.0
DULL_FLOW = 0.20               # router.LOW_FLOW: below this a cell is the dull tail
DULL_MIN_SHARE = 0.55          # ... and this much of the road ahead must be dull
LOOK_AHEAD_M = 6000.0
GEM_RADIUS_M = 5000.0
GEM_MIN_SCORE = 0.0
GATE_WARN_M = 2500.0
FUEL_RESERVE = 1.20            # refuse to call it fine unless range covers 1.2x
FUEL_WARN_PERCENT = 25.0

COVERAGE = {"lat": (47.38, 48.03), "lon": (10.72, 11.96)}

NARRATOR_PROMPT = """You are the co-pilot of a motorcyclist who is riding right now.

You are given ONE suggestion that the app's routing engine has already decided
is worth raising, with its real numbers. Your only job is to say it out loud in
a single short sentence a helmeted rider can absorb at speed.

Rules:
- Never invent or change a number, a place or a road. Use only what is given.
- One sentence. No markdown, no lists, no emoji, no greeting.
- If the suggestion would be unwelcome or unsafe to raise right now given the
  ride context, reply with exactly: SKIP
Replying SKIP is a normal, expected answer. Silence is better than chatter."""


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def _nearest_on_path(lat: float, lon: float,
                     path: list[list[float]]) -> tuple[float, int]:
    """Distance in metres to the closest vertex of a [lon, lat] path, and its index.

    Vertex distance, not perpendicular distance to the segment: FLOWSTATE paths
    are cell centres about 600 m apart, so the perpendicular refinement would be
    smaller than the grid it is measured on.
    """
    best, best_i = float("inf"), -1
    for i, pt in enumerate(path):
        if not pt or len(pt) < 2:
            continue
        d = _haversine_m(lat, lon, float(pt[1]), float(pt[0]))
        if d < best:
            best, best_i = d, i
    return best, best_i


def _in_coverage(lat: float, lon: float) -> bool:
    return (COVERAGE["lat"][0] <= lat <= COVERAGE["lat"][1]
            and COVERAGE["lon"][0] <= lon <= COVERAGE["lon"][1])


# --------------------------------------------------------------------------
# ride state
# --------------------------------------------------------------------------

@dataclass
class Fix:
    lat: float
    lon: float
    speed_kmh: float | None
    heading_deg: float | None
    at: float


@dataclass
class RideSession:
    """One ride's worth of live state. Bounded, in memory, never persisted."""

    session: str
    started_at: float = field(default_factory=time.time)
    fixes: list[Fix] = field(default_factory=list)
    last_spoken_at: float = 0.0
    last_by_kind: dict[str, float] = field(default_factory=dict)
    dismissed: dict[str, float] = field(default_factory=dict)
    off_route_streak: int = 0
    stopped_since: float | None = None
    seq: int = 0

    def add(self, fix: Fix) -> None:
        self.fixes.append(fix)
        if len(self.fixes) > MAX_FIXES:
            del self.fixes[: len(self.fixes) - MAX_FIXES]

    @property
    def last(self) -> Fix | None:
        return self.fixes[-1] if self.fixes else None

    def distance_m(self) -> float:
        return sum(_haversine_m(a.lat, a.lon, b.lat, b.lon)
                   for a, b in zip(self.fixes, self.fixes[1:]))

    def moving_kmh(self) -> float | None:
        """Median-ish current speed: the reported one, else derived from the fixes."""
        if self.last and self.last.speed_kmh is not None:
            return self.last.speed_kmh
        if len(self.fixes) < 2:
            return None
        a, b = self.fixes[-2], self.fixes[-1]
        dt = b.at - a.at
        if dt <= 0:
            return None
        return _haversine_m(a.lat, a.lon, b.lat, b.lon) / dt * 3.6

    def elapsed_min(self) -> float:
        return (time.time() - self.started_at) / 60.0


# --------------------------------------------------------------------------
# suggestions
# --------------------------------------------------------------------------

@dataclass
class Suggestion:
    """What a trigger produced. `say` is already usable without any model."""

    kind: str
    priority: int                 # higher wins when two triggers fire on one tick
    title: str
    detail: str
    say: str
    action: dict[str, Any] | None = None      # {tool, args} — an assistant tool
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, seq: int, narrated: bool) -> dict[str, Any]:
        return {"id": f"{self.kind}-{seq}", "kind": self.kind, "title": self.title,
                "detail": self.detail, "say": self.say, "action": self.action,
                "evidence": self.evidence, "narrated": narrated,
                "priority": self.priority}


# --------------------------------------------------------------------------
# the co-pilot
# --------------------------------------------------------------------------

class Copilot:
    """Live ride watcher. Owns no data of its own — it reads the same engine
    and cloud the REST API and the assistant use."""

    def __init__(self, engine: Any, cloud: Any, engine_kind: str = "unknown") -> None:
        self.engine = engine
        self.cloud = cloud
        self.engine_kind = engine_kind
        self.sessions: dict[str, RideSession] = {}

    # -- session bookkeeping ----------------------------------------------

    def _session(self, key: str) -> RideSession:
        s = self.sessions.get(key)
        if s is None:
            if len(self.sessions) >= MAX_SESSIONS:       # drop the oldest
                oldest = min(self.sessions.values(), key=lambda x: x.started_at)
                self.sessions.pop(oldest.session, None)
            s = RideSession(session=key)
            self.sessions[key] = s
        return s

    def reset(self, key: str) -> dict[str, Any]:
        self.sessions.pop(key, None)
        return {"ok": True, "session": key}

    def dismiss(self, key: str, kind: str) -> dict[str, Any]:
        """The rider said no. Park that kind for half an hour — dismissals are
        the only feedback we get, so they have to cost the trigger something."""
        s = self._session(key)
        s.dismissed[kind] = time.time()
        return {"ok": True, "session": key, "dismissed": kind}

    def status(self) -> dict[str, Any]:
        return {"ok": True, "engine": self.engine_kind,
                "narrator": {"enabled": bool(_api_key()), "model": NARRATOR_MODEL},
                "sessions": len(self.sessions),
                "triggers": [t.__name__[2:] for t in self._triggers()]}

    # -- the tick ----------------------------------------------------------

    def tick(self, req: dict[str, Any]) -> dict[str, Any]:
        """One position report. Returns at most one suggestion."""
        key = str(req.get("session") or "default")
        s = self._session(key)
        now = time.time()

        try:
            lat, lon = float(req["lat"]), float(req["lon"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "lat and lon are required",
                    "suggestion": None}

        if s.last is not None and now - s.last.at < MIN_FIX_GAP_S:
            return self._quiet(s, "tick ignored: fixes closer than the minimum gap")

        speed = req.get("speed_kmh")
        s.add(Fix(lat=lat, lon=lon,
                  speed_kmh=float(speed) if speed is not None else None,
                  heading_deg=(float(req["heading_deg"])
                               if req.get("heading_deg") is not None else None),
                  at=now))

        kmh = s.moving_kmh()
        if kmh is not None and kmh < STOPPED_KMH:
            s.stopped_since = s.stopped_since or now
        else:
            s.stopped_since = None

        if not _in_coverage(lat, lon):
            return self._quiet(s, "outside the FLOWSTATE coverage box; "
                                  "nothing here is scored")

        ctx = {
            "lat": lat, "lon": lon, "speed_kmh": kmh,
            "heading_deg": s.last.heading_deg if s.last else None,
            "rider_key": str(req.get("rider_key") or "userA"),
            "thrill": float(req.get("thrill") or 0.5),
            "mode": str(req.get("mode") or "flow"),
            "route": req.get("route") or None,          # {path, destination, summary}
            "bike_id": req.get("bike_id"),
            "elapsed_min": round(s.elapsed_min(), 1),
            "ridden_km": round(s.distance_m() / 1000.0, 1),
            "now": time.strftime("%H:%M", time.localtime(now)),
        }

        fired: list[Suggestion] = []
        for trigger in self._triggers():
            if not self._allowed(s, trigger.__name__[2:], now):
                continue
            try:
                out = trigger(self, s, ctx)
            except Exception as exc:  # noqa: BLE001 - a broken trigger must not end the ride
                out = None
                fired.append(Suggestion(
                    kind="error", priority=-1, title="co-pilot trigger failed",
                    detail=f"{trigger.__name__}: {type(exc).__name__}: {exc}",
                    say="", evidence={"trigger": trigger.__name__}))
            if out is not None:
                fired.append(out)

        real = [f for f in fired if f.kind != "error"]
        if not real:
            return self._quiet(s, "nothing worth saying", errors=[f.detail for f in fired
                                                                  if f.kind == "error"])
        if now - s.last_spoken_at < QUIET_S:
            return self._quiet(s, "held: inside the quiet window")

        best = max(real, key=lambda x: x.priority)
        say, narrated = self._narrate(best, ctx)
        if not say:
            # The model vetoed it. Treat that as a soft dismissal so the same
            # trigger does not re-fire on the very next tick.
            s.last_by_kind[best.kind] = now
            return self._quiet(s, f"held: narrator skipped {best.kind}")

        best.say = say
        s.seq += 1
        s.last_spoken_at = now
        s.last_by_kind[best.kind] = now
        return {"ok": True, "session": s.session,
                "suggestion": best.as_dict(s.seq, narrated),
                "considered": [f.kind for f in real], "engine": self.engine_kind}

    def _quiet(self, s: RideSession, why: str,
               errors: list[str] | None = None) -> dict[str, Any]:
        out = {"ok": True, "session": s.session, "suggestion": None, "why": why,
               "engine": self.engine_kind}
        if errors:
            out["errors"] = errors
        return out

    def _allowed(self, s: RideSession, kind: str, now: float) -> bool:
        if now - s.dismissed.get(kind, 0.0) < DISMISS_COOLDOWN_S:
            return False
        return now - s.last_by_kind.get(kind, 0.0) >= KIND_COOLDOWN_S

    def _triggers(self) -> list[Callable[["Copilot", RideSession, dict], Suggestion | None]]:
        return [Copilot.t_off_route, Copilot.t_gate_ahead, Copilot.t_dull_ahead,
                Copilot.t_scenic_detour, Copilot.t_fuel, Copilot.t_stopped]

    # -- triggers ----------------------------------------------------------
    # Each returns a Suggestion or None. They read the engine; they never read
    # the clock for cooldown purposes (that is _allowed's job) and they never
    # decide whether the rider hears it.

    def t_off_route(self, s: RideSession, c: dict) -> Suggestion | None:
        """Drifted off the planned line, twice in a row. Re-plan from here."""
        route = c["route"] or {}
        path = route.get("path") or []
        if len(path) < 2:
            s.off_route_streak = 0
            return None

        away, idx = _nearest_on_path(c["lat"], c["lon"], path)
        if away <= OFF_ROUTE_M:
            s.off_route_streak = 0
            return None
        s.off_route_streak += 1
        if s.off_route_streak < OFF_ROUTE_STREAK:
            return None

        dest = route.get("destination") or (path[-1][1], path[-1][0])
        dest = [float(dest[0]), float(dest[1])]
        plan = self.engine.route([c["lat"], c["lon"]], dest, c["rider_key"],
                                 c["thrill"], mode=c["mode"])
        if not plan.get("ok"):
            return None
        km = plan["summary"].get("km", 0.0)
        mins = plan["summary"].get("minutes", 0.0)
        return Suggestion(
            kind="off_route", priority=90,
            title="Off the planned line",
            detail=(f"You are {away:.0f} m from the route, {len(path) - idx} cells "
                    f"from where you left it. A new line from here is "
                    f"{km:.0f} km, about {mins:.0f} minutes."),
            say=(f"You're about {away/1000:.1f} kilometres off the plan. I can "
                 f"re-route from here, {km:.0f} kilometres."),
            action={"tool": "plan_route",
                    "args": {"start": [c["lat"], c["lon"]], "end": dest,
                             "thrill": c["thrill"], "mode": c["mode"]}},
            evidence={"off_by_m": round(away, 1), "km": km, "minutes": mins})

    def t_gate_ahead(self, s: RideSession, c: dict) -> Suggestion | None:
        """A road the rider's own gate refuses, close ahead on the planned route.

        This is the one trigger that is a warning rather than an offer, so it
        outranks everything else: the gate is the safety criterion and it does
        not negotiate.
        """
        route = c["route"] or {}
        refusals = route.get("refusals") or []
        if not refusals:
            return None
        near = []
        for r in refusals:
            lat, lon = r.get("lat"), r.get("lon")
            if lat is None or lon is None:
                continue
            d = _haversine_m(c["lat"], c["lon"], float(lat), float(lon))
            if d <= GATE_WARN_M:
                near.append((d, r))
        if not near:
            return None
        near.sort(key=lambda x: x[0])
        d, r = near[0]
        return Suggestion(
            kind="gate_ahead", priority=100,
            title="Refused road near your line",
            detail=f"{d:.0f} m ahead: {r.get('reason', 'past your gate')}",
            say=(f"Heads up, about {d/1000:.1f} kilometres ahead there's a road "
                 f"your gate refuses. I've already routed around it."),
            action=None,
            evidence={"distance_m": round(d, 1), "reason": r.get("reason")})

    def t_dull_ahead(self, s: RideSession, c: dict) -> Suggestion | None:
        """The next few kilometres of the planned route score below the dull
        line. Offer the same destination at a higher thrill setting."""
        route = c["route"] or {}
        segs = route.get("segments") or []
        path = route.get("path") or []
        if len(segs) < 4 or len(path) < 2:
            return None
        _, idx = _nearest_on_path(c["lat"], c["lon"], path)
        if idx < 0:
            return None

        ahead, run_m, dull_m = [], 0.0, 0.0
        for seg in segs[idx:]:
            a, b = seg.get("from"), seg.get("to")
            if not a or not b:
                continue
            d = _haversine_m(float(a[1]), float(a[0]), float(b[1]), float(b[0]))
            run_m += d
            if float(seg.get("flow") or 0.0) < DULL_FLOW:
                dull_m += d
            ahead.append(seg)
            if run_m >= LOOK_AHEAD_M:
                break
        if run_m < LOOK_AHEAD_M * 0.5 or dull_m / max(run_m, 1e-9) < DULL_MIN_SHARE:
            return None
        if c["thrill"] >= 0.85:            # already at the top of the dial
            return None

        dest = route.get("destination") or [path[-1][1], path[-1][0]]
        thrill = min(0.90, c["thrill"] + 0.35)
        alt = self.engine.route([c["lat"], c["lon"]], [float(dest[0]), float(dest[1])],
                                c["rider_key"], thrill, mode=c["mode"])
        if not alt.get("ok"):
            return None
        share = dull_m / run_m
        km = alt["summary"].get("km", 0.0)
        return Suggestion(
            kind="dull_ahead", priority=60,
            title="Flat stretch coming up",
            detail=(f"{share:.0%} of the next {run_m/1000:.0f} km scores below "
                    f"{DULL_FLOW:.2f} for fit. At thrill {thrill:.2f} the same "
                    f"destination is {km:.0f} km."),
            say=(f"The next {run_m/1000:.0f} kilometres are mostly flat. I can "
                 f"take you the interesting way instead, {km:.0f} kilometres."),
            action={"tool": "plan_route",
                    "args": {"start": [c["lat"], c["lon"]],
                             "end": [float(dest[0]), float(dest[1])],
                             "thrill": thrill, "mode": c["mode"]}},
            evidence={"dull_share": round(share, 3), "looked_m": round(run_m),
                      "thrill_from": c["thrill"], "thrill_to": thrill})

    def t_scenic_detour(self, s: RideSession, c: dict) -> Suggestion | None:
        """A crowd gem within a few kilometres that this rider's graph can
        actually reach and does not gate."""
        if (c["speed_kmh"] or 0.0) < MOVING_KMH:
            return None
        gems = self.engine.gem_pool(c["rider_key"], c["thrill"], 20, "scenic")
        best = None
        for g in gems or []:
            if not g.get("routable"):
                continue
            d = _haversine_m(c["lat"], c["lon"], float(g["lat"]), float(g["lon"]))
            if d > GEM_RADIUS_M or d < 500.0:
                continue
            if best is None or d < best[0]:
                best = (d, g)
        if best is None:
            return None
        d, g = best
        return Suggestion(
            kind="scenic_detour", priority=40,
            title="Gem off your line",
            detail=(f"{d/1000:.1f} km away, crowd gem score {g['gem_score']:.2f} "
                    f"from {g['n_rides']} rides, demand {g['demand_p90']:.1f}°, "
                    f"fit {g.get('flow', 0):.2f} at your dial."),
            say=(f"There's one of the crowd's best corners about "
                 f"{d/1000:.1f} kilometres off your line. Want it in?"),
            action={"tool": "plan_route",
                    "args": {"start": [c["lat"], c["lon"]],
                             "end": [g["lat"], g["lon"]],
                             "thrill": c["thrill"], "mode": "scenic"}},
            evidence={"distance_m": round(d, 1), "gem_score": g["gem_score"],
                      "n_rides": g["n_rides"], "cell16": g.get("cell16")})

    def t_fuel(self, s: RideSession, c: dict) -> Suggestion | None:
        """Range against the ride still to come.

        The range number is whatever the garage last recorded, NOT a live bike
        reading, and the suggestion says so — a fuel warning that implies a
        live fuel sender we do not have is worse than no warning.
        """
        route = c["route"] or {}
        remaining_km = route.get("remaining_km")
        try:
            bike = None
            for b in self.cloud.get_bikes() or []:
                if c["bike_id"] and b.get("id") == c["bike_id"]:
                    bike = b
                    break
                if bike is None and b.get("connected"):
                    bike = b
            bike = bike or (self.cloud.get_bikes() or [None])[0]
        except Exception:  # noqa: BLE001 - the cloud is a stand-in; never fatal
            return None
        if not bike:
            return None

        rng = bike.get("rangeKm")
        pct = bike.get("fuelPercent")
        if rng is None and pct is None:
            return None
        need = float(remaining_km) if remaining_km else None
        tight = (need is not None and rng is not None
                 and float(rng) < need * FUEL_RESERVE)
        low = pct is not None and float(pct) < FUEL_WARN_PERCENT
        if not (tight or low):
            return None
        return Suggestion(
            kind="fuel", priority=80,
            title="Fuel before the rest of this",
            detail=(f"Garage record: {rng if rng is not None else '--'} km range, "
                    f"{pct if pct is not None else '--'}% tank"
                    + (f", {need:.0f} km still to ride." if need else ".")
                    + " This is the last recorded value, not a live reading "
                      "from the bike."),
            say=("Worth fuelling soon — the last recorded range doesn't "
                 "comfortably cover what's left."),
            action={"tool": "bike_status", "args": {"bike_id": bike.get("id")}},
            evidence={"range_km": rng, "fuel_percent": pct,
                      "remaining_km": need, "source": "garage record"})

    def t_stopped(self, s: RideSession, c: dict) -> Suggestion | None:
        """Parked for a while. This is the only moment a longer interaction is
        safe, so it is the moment to offer a fresh plan."""
        if s.stopped_since is None:
            return None
        stopped_s = time.time() - s.stopped_since
        if stopped_s < STOPPED_S:
            return None
        return Suggestion(
            kind="stopped", priority=20,
            title="Still here?",
            detail=(f"Stopped for {stopped_s/60:.0f} minutes after "
                    f"{c['ridden_km']:.0f} km. I can plan a loop back from this "
                    f"spot whenever you are ready."),
            say=(f"You've been stopped a while. Want a loop back from here?"),
            action={"tool": "plan_loop",
                    "args": {"start": [c["lat"], c["lon"]], "hours": 1.5,
                             "thrill": c["thrill"], "mode": c["mode"]}},
            evidence={"stopped_min": round(stopped_s / 60.0, 1),
                      "ridden_km": c["ridden_km"]})

    # -- narration ---------------------------------------------------------

    def _narrate(self, s: Suggestion, ctx: dict) -> tuple[str, bool]:
        """Phrase the suggestion, or drop it. Returns (sentence, model_used).

        With no key the templated sentence ships unchanged — the co-pilot is a
        rules engine that OpenAI makes fluent, not the other way round.
        """
        key = _api_key()
        if not key:
            return s.say, False
        payload = {
            "suggestion": {"kind": s.kind, "title": s.title, "detail": s.detail,
                           "draft": s.say, "evidence": s.evidence},
            "ride": {k: ctx.get(k) for k in
                     ("speed_kmh", "elapsed_min", "ridden_km", "thrill", "mode", "now")},
        }
        body = json.dumps({
            "model": NARRATOR_MODEL,
            "messages": [{"role": "system", "content": NARRATOR_PROMPT},
                         {"role": "user", "content": json.dumps(payload)}],
            "temperature": 0.3,
            "max_tokens": 90,
        }).encode()
        req = urllib.request.Request(
            OPENAI_URL, data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=NARRATOR_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            said = (data["choices"][0]["message"].get("content") or "").strip()
        except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
            return s.say, False          # unreachable model -> the rules still speak
        if said.upper().startswith("SKIP"):
            return "", True
        return said or s.say, True


def _api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()
    path = os.environ.get("OPENAI_API_KEY_FILE")
    if path and os.path.exists(path):
        return open(path, encoding="utf-8").read().strip() or None
    return None
