"""
flowstate_mock.py — a stand-in for service.py when the bake is absent.

The real FLOWSTATE engine (service.py) runs off data/cache/demo.pkl, which is
NDA crowd data and lives only on the Mac mini. A fresh clone (CI, a laptop, the
phone-app developer's machine) has no bake, so service.init() cannot run there.

This module answers the *same contract* as service.py (docs 25 / 26) with
realistic, deterministic values: the rehearsed demo pairs reproduce the exact
numbers written in doc 25, and free-clicked points get plausible, coverage-aware
answers. It exists so the whole app can be wired and tested live everywhere;
on the Mac, api.py loads the real service instead and this is never touched.

Nothing here is BMW crowd data. The rider constants are the calibrated summary
values already published in docs 22 / 25.
"""

from __future__ import annotations

import math

# coverage box (doc 25 §1)
LAT_MIN, LAT_MAX = 47.38, 48.03
LON_MIN, LON_MAX = 10.72, 11.96

Z_PRESETS = {"Cruise": 0.15, "Flow": 0.50, "Send it": 0.90}

PRESET_ROUTES = [
    {"key": "lenggries_bad_toelz", "label": "Lenggries -> Bad Tolz",
     "a": [47.59, 11.75], "b": [47.73, 11.37],
     "why": "the strongest dial effect measured: 17% shared cells, +3 deg demand"},
    {"key": "lenggries_kochel", "label": "Lenggries -> Kochel",
     "a": [47.59, 11.75], "b": [47.73, 11.18], "why": "25% shared cells"},
    {"key": "kochel_tegernsee", "label": "Kochel -> Tegernsee",
     "a": [47.66, 11.35], "b": [47.85, 11.85],
     "why": "where the gate bites: roads refused outright, and the only pair "
            "measured where switching rider really moves the line (10% shared)"},
]

PRESET_LOOPS = [
    {"key": "kochel", "label": "Kochel am See", "start": [47.66, 11.35]},
    {"key": "holzkirchen", "label": "Holzkirchen", "start": [47.90, 11.40]},
    {"key": "schliersee", "label": "Schliersee", "start": [47.85, 11.85]},
    {"key": "lenggries", "label": "Lenggries", "start": [47.59, 11.75]},
]

RIDERS = {
    "userA": {"label": "User A - all rides", "skill": 11.40, "sigma": 5.59, "gate": 22.59,
              "hardest_ridden": 21.24, "gate_agreement": 1.063, "n_cells": 4212,
              "n_corners": 5253, "grip_p95": 0.53},
    "userC": {"label": "User C - all rides", "skill": 10.65, "sigma": 5.44, "gate": 21.53,
              "hardest_ridden": 20.08, "gate_agreement": 1.072, "n_cells": 1876,
              "n_corners": 2104, "grip_p95": 0.49},
    "bike_da67fa06": {"label": "Bike da67fa06", "skill": 10.10, "sigma": 6.57, "gate": 23.25,
                      "hardest_ridden": 25.80, "gate_agreement": 0.901, "n_cells": 1442,
                      "n_corners": 1610, "grip_p95": 0.61},
    "bike_4e1a9d64": {"label": "Bike 4e1a9d64", "skill": 13.25, "sigma": 5.32, "gate": 23.89,
                      "hardest_ridden": 20.43, "gate_agreement": 1.169, "n_cells": 1233,
                      "n_corners": 1301, "grip_p95": 0.47},
}

# rehearsed pairs whose measured compare() output is fixed in doc 25
_EXACT = {
    # (rider, round(a), round(b)) -> per-dial measured summary
    ("userA", (47.59, 11.75), (47.73, 11.37)): {
        0.15: {"km": 46.9, "minutes": 42.8, "mean_demand": 7.02, "max_demand": 17.1,
               "peak_flow": 0.41, "refused": 0},
        0.90: {"km": 53.0, "minutes": 40.1, "mean_demand": 9.71, "max_demand": 22.4,
               "peak_flow": 0.57, "refused": 0},
        "overlap": 0.167,
        "headline": "Same two points. 1.13x the distance, 83% of it on different roads, "
                    "+2.7 deg more lean asked of you."},
}


def _in_box(pt) -> bool:
    la, lo = float(pt[0]), float(pt[1])
    return LAT_MIN <= la <= LAT_MAX and LON_MIN <= lo <= LON_MAX


def _haversine_km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _seed(*vals) -> int:
    s = 2166136261
    for v in vals:
        s = (s ^ (int(abs(v) * 1000) & 0xFFFFFFFF)) * 16777619 & 0xFFFFFFFF
    return s or 1


def _path(a, b, z_star: float, seed: int, points: int = 90,
          target_km: float | None = None) -> list[list[float]]:
    """Return [lon, lat] pairs, bendier at higher z.

    With target_km the wiggle is scaled so the drawn line is that long, so
    what the map measures and what the summary claims are the same number.
    """
    s = {"v": seed}

    def r():
        s["v"] = (s["v"] * 1103515245 + 12345) % 2147483648
        return s["v"] / 2147483648

    d_lat, d_lon = b[0] - a[0], b[1] - a[1]
    length = math.hypot(d_lat, d_lon) or 1.0
    px, py = -d_lat / length, d_lon / length
    phase = r() * math.pi * 2
    wig = 0.012 + z_star * 0.03

    def draw(scale: float) -> list[list[float]]:
        out = []
        for i in range(points):
            t = i / (points - 1)
            env = math.sin(t * math.pi)
            bend = (math.sin(t * math.pi * 2.1 + phase) * wig * 6
                    + math.sin(t * math.pi * 6.3 + phase * 2) * wig * 2.4) * env * scale
            la = a[0] + d_lat * t + py * bend * 0.7
            lo = a[1] + d_lon * t + px * bend
            out.append([round(lo, 5), round(la, 5)])
        return out

    if target_km is None:
        return draw(1.0)

    # length grows with the wiggle, so bisect on it; a straight line is the
    # shortest we can draw, and anything under that is left straight.
    lo_s, hi_s = 0.0, 1.0
    while _path_km(draw(hi_s)) < target_km and hi_s < 64.0:
        hi_s *= 2
    for _ in range(28):
        mid = (lo_s + hi_s) / 2
        if _path_km(draw(mid)) < target_km:
            lo_s = mid
        else:
            hi_s = mid
    return draw((lo_s + hi_s) / 2)


def _path_km(path) -> float:
    """Length of a drawn [lon, lat] line, the way the phone measures it."""
    return sum(_haversine_km([path[i][1], path[i][0]], [path[i + 1][1], path[i + 1][0]])
               for i in range(len(path) - 1))


def init(*_a, **_k) -> dict:
    return status()


def status() -> dict:
    return {"source": "mock (no bake on this machine)", "loaded_s": 0.0, "cells": 5698,
            "edges": 10318, "riders": len(RIDERS), "osm": True, "basemap_ways": 0,
            "precomputed": len(PRESET_ROUTES), "joy_rides": 324, "gems": 100,
            "road_character": True, "riders_modes": True, "mock": True}


def riders() -> list[dict]:
    out = []
    for k, v in RIDERS.items():
        out.append({"key": k, **{kk: vv for kk, vv in v.items()}})
    return out


def presets() -> dict:
    return {"routes": PRESET_ROUTES, "loops": PRESET_LOOPS, "dial": Z_PRESETS}


def modes() -> list[dict]:
    return [
        {"key": "flow", "verdict": "DEFAULT", "phase4": False, "offered": True},
        {"key": "scenic", "verdict": "PASS", "phase4": False, "offered": True},
        {"key": "mountain", "verdict": "PASS", "phase4": False, "offered": True},
        {"key": "adventure", "verdict": "FAIL", "phase4": False, "offered": False},
        {"key": "urban", "verdict": "FAIL", "phase4": True, "offered": False},
    ]


def _summary_for(a, b, rider_key: str, z_star: float, is_loop=False, hours=None):
    rd = RIDERS.get(rider_key, RIDERS["userA"])
    base_km = _haversine_km(a, b)
    detour = 1.06 + z_star * 0.12
    km = round(base_km * (2 if is_loop else 1) * detour, 1)
    if is_loop and hours:
        km = round(min(km, hours * 62), 1)
    minutes = round(km / (0.92 + (1 - z_star) * 0.15), 1)
    mean_demand = round(rd["skill"] * 0.55 + z_star * (rd["gate"] - rd["skill"]) * 0.62, 2)
    max_demand = round(mean_demand + 6.0 + z_star * 4.5, 1)
    z = (mean_demand - rd["skill"]) / rd["sigma"]
    peak_flow = round(math.exp(-((z - z_star) ** 2) / (2 * 0.5 ** 2)), 2)
    mean_flow = round(peak_flow * 0.78, 2)
    fun = round(min(100.0, peak_flow * 92 + z_star * 6), 1)
    grip = round(0.28 + z_star * 0.22, 2)
    s = {"km": km, "minutes": minutes, "n_cells": max(6, int(km / 0.6)),
         "mean_demand": mean_demand, "max_demand": max_demand, "mean_flow": mean_flow,
         "peak_flow": peak_flow, "final_flow": mean_flow, "fun_score": fun,
         "dull_share": round(max(0.0, 0.4 - z_star * 0.3), 2),
         "grip_lat_p95": grip, "grip_lat_max": round(grip + 0.12, 2),
         "gate_deg": rd["gate"], "n_refused_nearby": 0, "imputed_cells": max(0, int(km / 30))}
    if is_loop:
        s["is_loop"] = True
        s["budget_min"] = round((hours or 2) * 60)
        s["budget_fill"] = round(minutes / max(1, s["budget_min"]), 2)
        s["distinct_share"] = round(min(0.98, 0.9 + z_star * 0.05), 3)
    return s


def _refusals_for(a, b, rider_key: str, z_star: float, summary) -> list[dict]:
    rd = RIDERS.get(rider_key, RIDERS["userA"])
    # the gate bites on Kochel -> Tegernsee at Send it, hardest for the sharp bike
    key_pair = (round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2))
    is_teg = key_pair == (47.66, 11.35, 47.85, 11.85)
    out = []
    if z_star >= 0.85 and (is_teg or rd["gate"] < 22.0):
        demand = round(rd["gate"] + 2.0 + z_star, 1)
        out.append({"cell": "mock", "lat": round((a[0] + b[0]) / 2 + 0.02, 4),
                    "lon": round((a[1] + b[1]) / 2 - 0.02, 4), "demand": demand,
                    "reason": f"REFUSED - the crowd leans {demand:.1f} deg here, past your "
                              f"gate of {rd['gate']:.1f} deg ({rd['skill']:.1f} deg + 2 sigma)"})
    summary["n_refused_nearby"] = len(out)
    return out


def _explain(summary, refusals, rider_key, route_cells=None) -> list[str]:
    rd = RIDERS.get(rider_key, RIDERS["userA"])
    out = []
    if summary.get("is_loop"):
        out.append(f"A {summary['km']:.0f} km loop back to where you started, "
                   f"{summary['minutes']:.0f} minutes of riding against the "
                   f"{summary['budget_min']:.0f} you asked for.")
        if summary.get("distinct_share", 1) < 0.95:
            out.append(f"{summary['distinct_share']:.0%} of it is road you only ride once; "
                       f"the rest is unavoidable retracing.")
    else:
        out.append(f"{summary['km']:.0f} km, about {summary['minutes']:.0f} minutes.")
    out.append(f"This road asks a mean {summary['mean_demand']:.1f} deg of lean and peaks at "
               f"{summary['max_demand']:.1f} deg. Your gate is {rd['gate']:.1f} deg, which is "
               f"2 sigma above the road you habitually ride.")
    out.append(f"Best five kilometres score {summary['peak_flow']:.2f} out of 1 for fit at "
               f"this dial setting.")
    grip = summary.get("grip_lat_p95")
    if grip is not None:
        out.append(f"Cornering asks about {grip:.0%} of the tyre's grip here, against the "
                   f"{rd['grip_p95']:.0%} you have already used on your own rides.")
    if refusals:
        out.append(f"{len(refusals)} road(s) near this route were refused outright, not just "
                   f"made expensive:")
        out += [f"    {x['reason']}" for x in refusals[:3]]
    else:
        out.append("Nothing on this route crosses your safety gate.")
    if summary.get("imputed_cells"):
        out.append(f"{int(summary['imputed_cells'])} cells had no corner in the crowd data and "
                   f"were treated as straight, not as missing.")
    return out


def route(a, b, rider_key: str = "userA", z_star: float = 0.5,
          lam: float = 10.0, mode: str = "flow") -> dict:
    if not _in_box(a) or not _in_box(b):
        return {"ok": False, "note": "Those points are outside the covered area (a box around "
                "Munich and the Alpine foothills). Pick a start and end inside it.",
                "path": [], "segments": [], "refusals": [], "summary": [],
                "explain": ["Outside coverage."]}
    summary = _summary_for(a, b, rider_key, z_star)
    # honour the measured exact values for the rehearsed pair
    ex = _EXACT.get((rider_key, (round(a[0], 2), round(a[1], 2)),
                     (round(b[0], 2), round(b[1], 2))))
    if ex and z_star in ex:
        summary.update({k: v for k, v in ex[z_star].items() if k != "refused"})
    path = _path(a, b, z_star, _seed(a[0], a[1], b[0], b[1], z_star),
                 target_km=summary["km"])
    summary["km"] = round(_path_km(path), 1)
    cells = [f"c{i}" for i in range(len(path))]
    refusals = _refusals_for(a, b, rider_key, z_star, summary)
    seg = []
    for i in range(len(path) - 1):
        t = (i + 1) / len(path)
        fl = round(max(0.05, summary["peak_flow"] * (0.6 + 0.4 * math.sin(t * math.pi))), 3)
        seg.append({"from": path[i], "to": path[i + 1], "flow": fl,
                    "demand": round(summary["mean_demand"] * (0.7 + 0.6 * math.sin(t * math.pi)), 2)})
    return {"ok": True, "note": "", "cells": cells, "path": path, "segments": seg,
            "refusals": refusals, "summary": summary, "rider": rider_key,
            "z_star": float(z_star), "explain": _explain(summary, refusals, rider_key, cells)}


def loop(start, hours: float = 2.0, rider_key: str = "userA", z_star: float = 0.5,
         lam: float = 10.0, mode: str = "flow") -> dict:
    if not _in_box(start):
        return {"ok": False, "note": "That start is outside the covered area.", "path": [],
                "segments": [], "refusals": [], "summary": [], "explain": ["Outside coverage."]}
    # build a loop as an out-and-back to a synthesized turnaround
    turn = [start[0] + 0.12 + z_star * 0.05, start[1] + 0.16 + z_star * 0.05]
    turn = [min(turn[0], LAT_MAX), min(turn[1], LON_MAX)]
    summary = _summary_for(start, turn, rider_key, z_star, is_loop=True, hours=hours)
    out = _path(start, turn, z_star, _seed(start[0], start[1], hours, z_star),
                target_km=summary["km"] / 2)
    back = [[p[0] + 0.004, p[1] - 0.004] for p in reversed(out)]
    path = out + back
    summary["km"] = round(_path_km(path), 1)
    cells = [f"c{i}" for i in range(len(path))]
    refusals = _refusals_for(start, turn, rider_key, z_star, summary)
    seg = []
    for i in range(len(path) - 1):
        t = (i + 1) / len(path)
        fl = round(max(0.05, summary["peak_flow"] * (0.6 + 0.4 * math.sin(t * 2 * math.pi))), 3)
        seg.append({"from": path[i], "to": path[i + 1], "flow": fl,
                    "demand": round(summary["mean_demand"] * (0.7 + 0.6 * abs(math.sin(t * math.pi))), 2)})
    note = f"{1 - summary['distinct_share']:.0%} of the loop is unavoidable retracing."
    return {"ok": True, "note": note, "cells": cells, "path": path, "segments": seg,
            "refusals": refusals, "summary": summary, "rider": rider_key,
            "z_star": float(z_star), "explain": _explain(summary, refusals, rider_key, cells)}


def compare(a, b, rider_key: str = "userA", lo: float = 0.15, hi: float = 0.90,
            mode: str = "flow") -> dict:
    x = route(a, b, rider_key, lo, mode=mode)
    y = route(a, b, rider_key, hi, mode=mode)
    out = {"low": x, "high": y, "lo_z": lo, "hi_z": hi}
    if x["ok"] and y["ok"]:
        ex = _EXACT.get((rider_key, (round(a[0], 2), round(a[1], 2)),
                         (round(b[0], 2), round(b[1], 2))))
        if ex:
            out["overlap"] = ex["overlap"]
            out["km_ratio"] = round(ex[hi]["km"] / ex[lo]["km"], 3) if hi in ex and lo in ex else 1.13
            out["demand_gain"] = round(ex[hi]["mean_demand"] - ex[lo]["mean_demand"], 2) \
                if hi in ex and lo in ex else 2.7
            out["headline"] = ex["headline"]
        else:
            ca, cb = set(x["cells"]), set(y["cells"])
            # synthesized shared fraction: closer skill/gate => more shared road
            shared = max(0.1, min(0.95, 1.0 - (hi - lo) * 0.9))
            out["overlap"] = round(shared, 3)
            out["km_ratio"] = round(y["summary"]["km"] / max(x["summary"]["km"], 1e-9), 3)
            out["demand_gain"] = round(y["summary"]["mean_demand"] - x["summary"]["mean_demand"], 2)
            out["headline"] = (f"Same two points. {out['km_ratio']:.2f}x the distance, "
                               f"{1 - out['overlap']:.0%} of it on different roads, "
                               f"{out['demand_gain']:+.1f} deg more lean asked of you.")
    return out


def pareto(a, b, rider_key: str = "userA") -> dict:
    if not _in_box(a) or not _in_box(b):
        return {"ok": False, "note": "Outside coverage.", "frontier": []}
    front = []
    for z in (0.15, 0.50, 0.90):
        s = _summary_for(a, b, rider_key, z)
        front.append({"mode": "flow", "z_star": z, "minutes": s["minutes"], "km": s["km"],
                      "mean_demand": s["mean_demand"]})
    front = sorted({(r["minutes"], r["mean_demand"]): r for r in front}.values(),
                   key=lambda r: r["minutes"])
    return {"ok": True, "verdict": "PASS", "routes_tried": 15, "frontier": front}


def basemap() -> list:
    return []


def cells_layer(rider_key: str = "userA", z_star: float = 0.5, min_flow: float = 0.0,
                mode: str = "flow") -> list:
    rd = RIDERS.get(rider_key, RIDERS["userA"])
    out = []
    n = 22
    for i in range(n):
        for j in range(n):
            la = LAT_MIN + (LAT_MAX - LAT_MIN) * (i + 0.5) / n
            lo = LON_MIN + (LON_MAX - LON_MIN) * (j + 0.5) / n
            demand = 4 + 14 * abs(math.sin(i * 0.7) * math.cos(j * 0.6))
            z = (demand - rd["skill"]) / rd["sigma"]
            flow = math.exp(-((z - z_star) ** 2) / (2 * 0.5 ** 2))
            gated = demand > rd["gate"]
            if flow >= min_flow:
                out.append({"lat": round(la, 4), "lon": round(lo, 4), "flow": round(flow, 3),
                            "demand": round(demand, 2), "gated": bool(gated)})
    return out


def rider_joy(rider_key: str = "userA") -> dict:
    return {"ok": True, "rider": rider_key, "verdict": "WEAK", "length_flag": True,
            "n_rides": 324, "median_joy": 0.02,
            "components": {"joy": {"auc": 0.61, "ci": [0.53, 0.69]}},
            "grip_budget": {"verdict": "FAIL", "auc": 0.52, "ci_lo": 0.44, "ci_hi": 0.60},
            "explain": [
                "Measured on 324 rides, from telemetry alone.",
                "Tested on this rider's rides: commutes against same-length stretches of long "
                "rides. The meter separates them with AUC 0.61 (95% CI 0.53-0.69): verdict WEAK.",
                "Shown as a weak measurement, never used to rank or route."]}


def gem_pool(rider_key: str = "userA", z_star: float = 0.5, n: int = 20,
             mode: str = "flow") -> list[dict]:
    out = []
    for i in range(min(n, 12)):
        la = LAT_MIN + (LAT_MAX - LAT_MIN) * ((i * 7 % 12) + 0.5) / 12
        lo = LON_MIN + (LON_MAX - LON_MIN) * ((i * 5 % 12) + 0.5) / 12
        out.append({"lat": round(la, 4), "lon": round(lo, 4), "gem_score": round(0.9 - i * 0.05, 3),
                    "demand_p90": round(16 - i * 0.4, 2), "n_rides": 40 - i, "cell16": f"g{i}",
                    "in_graph": True, "gated": False, "flow": round(0.7 - i * 0.03, 3),
                    "routable": True})
    return out
