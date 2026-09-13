#!/usr/bin/env python3
"""
phone_sim.py - stand in for the phone so the dashboard can be watched hands-free.

Does exactly the HTTP calls the app makes, in the app's order, nothing more:
  1. POST /api/route                      plan a route (what the Navigate screen does)
  2. POST /api/copilot/tick  every second  position reports along that line
  3. POST /api/assistant/tool             one assistant tool call with the ride
                                          context, as the realtime (voice) session
                                          does when the model calls a function
  4. keep ticking along the route the tool returned

Everything the dashboard then shows comes from those responses; this script
invents no route figures, only the GPS points along a plan the engine produced.

    python3 viz/scripts/phone_sim.py --base http://127.0.0.1:8090 \
        --say "this road is boring, get me off it" --change avoid_this_road

For the real thing use the phone: start the co-pilot on Navigate, hold the mic,
say the same sentence. The dashboard reacts the same way.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def km(a: list[float], b: list[float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def route_for_tick(plan: dict, remaining_km: float) -> dict:
    return {"path": plan["path"], "segments": plan.get("segments") or [],
            "refusals": plan.get("refusals") or [], "destination": plan["_dest"],
            "remaining_km": round(remaining_km, 1)}


def ride(base: str, a: argparse.Namespace, plan: dict, stop_at: float | None) -> tuple[list[float], list[float]]:
    """Tick along `plan` at `a.speed` km/h (in wall-clock `a.rate`x). Returns
    (position, heading) where it stopped; stop_at is a fraction of the length."""
    path = plan["path"]
    total = sum(km(path[i], path[i + 1]) for i in range(len(path) - 1))
    step_km = a.speed / 3600.0 * a.rate  # per 1 s tick
    done = 0.0
    i = 0
    pos = list(path[0])
    while i < len(path) - 1:
        if stop_at is not None and done >= stop_at * total:
            break
        left = step_km
        while i < len(path) - 1:
            seg = km(pos, path[i + 1])
            if seg > left:
                f = left / seg
                pos = [pos[0] + (path[i + 1][0] - pos[0]) * f, pos[1] + (path[i + 1][1] - pos[1]) * f]
                done += left
                break
            pos = list(path[i + 1]); i += 1; done += seg; left -= seg
        nxt = path[min(i + 1, len(path) - 1)]
        heading = (math.degrees(math.atan2(nxt[0] - pos[0], nxt[1] - pos[1])) + 360) % 360
        post(base, "/api/copilot/tick", {
            "session": a.session, "lat": pos[1], "lon": pos[0], "speed_kmh": a.speed,
            "heading_deg": heading, "rider_key": a.rider, "thrill": a.thrill, "mode": a.mode,
            "route": route_for_tick(plan, total - done)})
        print(f"tick  {pos[1]:.4f},{pos[0]:.4f}  {total - done:5.1f} km left", flush=True)
        time.sleep(1.0)
    return pos, plan.get("cells") or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--a", default="47.66,11.35", help="start lat,lon")
    ap.add_argument("--b", default="47.85,11.85", help="destination lat,lon")
    ap.add_argument("--rider", default="userA")
    ap.add_argument("--thrill", type=float, default=0.5)
    ap.add_argument("--mode", default="flow")
    ap.add_argument("--speed", type=float, default=70.0, help="km/h the bike rides at")
    ap.add_argument("--rate", type=float, default=20.0, help="wall-clock speed-up")
    ap.add_argument("--at", type=float, default=0.4, help="share of the route ridden before the rider speaks")
    ap.add_argument("--change", default="avoid_this_road",
                    choices=["avoid_this_road", "more_fun", "calmer", "scenic", "mountain"])
    ap.add_argument("--say", default="this road is boring, get me off it")
    ap.add_argument("--session", default="phone-sim")
    a = ap.parse_args()

    start = [float(x) for x in a.a.split(",")]
    dest = [float(x) for x in a.b.split(",")]
    plan = post(a.base, "/api/route", {"a": start, "b": dest, "rider_key": a.rider,
                                         "z_star": a.thrill, "mode": a.mode})
    if not plan.get("ok"):
        print("route refused:", plan.get("note"), file=sys.stderr)
        return 1
    plan["_dest"] = dest
    print(f"plan  {plan['summary'].get('km')} km, {len(plan['path'])} points", flush=True)

    pos, cells = ride(a.base, a, plan, a.at)

    # The realtime model heard the rider and called reroute_from_here; the
    # phone executes it here with its ride context, exactly as VoiceAssistant does.
    print(f"mic   \"{a.say}\"  -> reroute_from_here(change={a.change})", flush=True)
    res = post(a.base, "/api/assistant/tool", {
        "name": "reroute_from_here",
        "args": {"change": a.change, "reason": a.say},
        "context": {"ride": {"lat": pos[1], "lon": pos[0], "rider_key": a.rider, "thrill": a.thrill,
                             "mode": a.mode, "navigating": True,
                             "route": {"destination": dest, "cells": cells}}}})
    result = res.get("result") or {}
    if not result.get("ok"):
        print("tool  ", result.get("error") or result.get("note"), file=sys.stderr)
        return 1
    rr = result["reroute"]
    print(f"tool  -> {rr['mode_to']} @ {rr['thrill_to']}  {result['summary'].get('km')} km  "
          f"shares {rr.get('shares_current_road')}", flush=True)
    a.thrill, a.mode = float(rr["thrill_to"]), str(rr["mode_to"])

    new = dict(result)
    new["_dest"] = rr.get("destination") or dest
    time.sleep(6)  # the dashboard steps through the candidates meanwhile
    ride(a.base, a, new, None)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
