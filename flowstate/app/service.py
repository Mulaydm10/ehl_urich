"""
service.py — the one module the UI talks to.

Everything above this line is physics and graphs. Everything below it is
pixels. The UI never sees a DataFrame, never builds a graph, never knows what
a morton code is: it asks for a route and gets plain dicts and lists of
[lon, lat] pairs that go straight into pydeck.

Two reasons that matters tonight. It makes the front end assembly rather than
engineering, and it means the demo can run off a baked pickle with no BMW data
on the machine at all — `init()` will take the bake if it is there and fall
back to the parquets if it is not.

Typical use:

    import service as S
    S.init()
    S.riders()                       -> [{key, label, skill, sigma, gate, ...}]
    S.presets()                      -> {"routes": [...], "loops": [...]}
    S.route(A, B, "userA", 0.9)      -> dict, map-ready
    S.loop((47.66, 11.35), 2.0, "userA", 0.5)
    S.basemap()                      -> grey road polylines, offline
"""

from __future__ import annotations

import pickle
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import router as R                                            # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BAKE = ROOT / "data" / "cache" / "demo.pkl"

Z_PRESETS = {"Cruise": 0.15, "Flow": 0.50, "Send it": 0.90}

# measured in analysis/12_route_calibration.py — pairs where the dial actually
# changes the road. Free-click is allowed but these are what we rehearse.
PRESET_ROUTES = [
    {"key": "lenggries_bad_toelz", "label": "Lenggries -> Bad Tolz",
     "a": (47.59, 11.75), "b": (47.73, 11.37),
     "why": "the strongest dial effect measured: 17% shared cells, +3 deg demand"},
    {"key": "lenggries_kochel", "label": "Lenggries -> Kochel",
     "a": (47.59, 11.75), "b": (47.73, 11.18), "why": "25% shared cells"},
    {"key": "kochel_tegernsee", "label": "Kochel -> Tegernsee",
     "a": (47.66, 11.35), "b": (47.85, 11.85),
     "why": "where the gate bites: roads refused outright, and the only pair "
            "measured where switching rider really moves the line (10% shared)"},
]

PRESET_LOOPS = [
    {"key": "kochel", "label": "Kochel am See", "start": (47.66, 11.35)},
    {"key": "holzkirchen", "label": "Holzkirchen", "start": (47.90, 11.40)},
    {"key": "schliersee", "label": "Schliersee", "start": (47.85, 11.85)},
    {"key": "lenggries", "label": "Lenggries", "start": (47.59, 11.75)},
]

_S: dict | None = None


# --------------------------------------------------------------------------
# startup
# --------------------------------------------------------------------------

def init(bake: Path | None = None, force_parquet: bool = False) -> dict:
    """Load once. Returns a small dict describing what was loaded."""
    global _S
    t0 = time.time()
    bake = Path(bake) if bake else BAKE

    if bake.exists() and not force_parquet:
        with open(bake, "rb") as f:
            d = pickle.load(f)
        _S = {**d, "graphs": {}, "source": f"bake {bake.name}"}
        if _S.get("joy") is None:               # a bake from before Phase 1
            _S["joy"] = _load_joy()
        if _S.get("character") is None:         # a bake from before Phase 2
            _S["character"] = _load_character()
    else:
        cells = R.load_cells()
        osm = R.load_osm()
        cells = R.apply_legal_speed(cells, osm)
        _S = {"cells": cells, "edges": R.load_edges(), "osm": osm,
              "riders": _build_riders(cells), "basemap": None,
              "precomputed": {}, "graphs": {}, "source": "parquet",
              "joy": _load_joy(), "character": _load_character()}

    _S["loaded_s"] = time.time() - t0
    return status()


def status() -> dict:
    s = _need()
    return {"source": s["source"], "loaded_s": round(s["loaded_s"], 3),
            "cells": len(s["cells"]), "edges": len(s["edges"]),
            "riders": len(s["riders"]), "osm": s["osm"] is not None,
            "basemap_ways": (len(s["basemap"]) if s.get("basemap") else 0),
            "precomputed": len(s.get("precomputed", {})),
            "joy_rides": (len(s["joy"]["rides"]) if s.get("joy") else 0),
            "gems": (0 if (s.get("character") or {}).get("gems") is None
                     else len(s["character"]["gems"])),
            "road_character": "dwell_share" in s["cells"].columns}


def _need() -> dict:
    if _S is None:
        init()
    return _S


def _build_riders(cells: pd.DataFrame) -> dict:
    """Calibrate every rider profile we can offer. Needs the corner table."""
    import flowstate as F
    corners = F.load_corners(filtered=True)
    out = {}
    r = R.calibrate_rider(corners, cells, "User A - all rides")
    out["userA"] = {"rider": r, "n_corners": int(len(corners)),
                    "grip_p95": R.rider_grip_p95(corners)}
    # User A rode 15 bikes. Lean p95 on an S1000RR and an R18 are not the same
    # measurement, so the honest "second rider" is the same human on a
    # different machine.
    for bike, n in corners["bike"].value_counts().head(2).items():
        sub = corners[corners["bike"] == bike]
        key = f"bike_{bike[:8]}"
        out[key] = {"rider": R.calibrate_rider(sub, cells, f"Bike {bike[:8]}"),
                    "n_corners": int(n), "grip_p95": R.rider_grip_p95(sub)}
    return out


def riders() -> list[dict]:
    s = _need()
    out = []
    for k, v in s["riders"].items():
        r = v["rider"]
        out.append({"key": k, "label": r.label, "skill": round(r.skill, 2),
                    "sigma": round(r.sigma, 2), "gate": round(r.gate, 2),
                    "hardest_ridden": round(float(r.hardest_ridden), 2),
                    "gate_agreement": round(float(r.gate_agreement), 3),
                    "n_cells": r.n_cells, "n_corners": v["n_corners"],
                    "grip_p95": round(float(v["grip_p95"]), 2)})
    return out


def presets() -> dict:
    return {"routes": PRESET_ROUTES, "loops": PRESET_LOOPS, "dial": Z_PRESETS}


# --------------------------------------------------------------------------
# graphs, cached per (rider, dial)
# --------------------------------------------------------------------------

def _graph(rider_key: str, z_star: float, lam: float = R.LAMBDA_DEFAULT):
    s = _need()
    key = (rider_key, round(float(z_star), 3), round(float(lam), 2))
    if key not in s["graphs"]:
        if len(s["graphs"]) > 12:               # keep the dial responsive, not greedy
            s["graphs"].clear()
        s["graphs"][key] = R.build_graph(
            s["edges"], s["cells"], s["riders"][rider_key]["rider"],
            float(z_star), lam=lam, osm=s["osm"])
    return s["graphs"][key]


# --------------------------------------------------------------------------
# the two answers BMW asked for
# --------------------------------------------------------------------------

def route(a, b, rider_key: str = "userA", z_star: float = 0.5,
          lam: float = R.LAMBDA_DEFAULT) -> dict:
    """A -> B. Everything the map and the caption need, in plain types."""
    s = _need()
    g = _graph(rider_key, z_star, lam)
    r = R.route_a_to_b(tuple(a), tuple(b), s["riders"][rider_key]["rider"],
                       float(z_star), graph=g, cells=s["cells"],
                       edges=s["edges"], osm=s["osm"], lam=lam)
    return _pack(r, g, rider_key, z_star)


def loop(start, hours: float, rider_key: str = "userA",
         z_star: float = 0.5, lam: float = R.LAMBDA_DEFAULT) -> dict:
    """A closed loop of roughly `hours` from `start`."""
    s = _need()
    g = _graph(rider_key, z_star, lam)
    r = R.route_loop(tuple(start), float(hours),
                     s["riders"][rider_key]["rider"], float(z_star),
                     graph=g, cells=s["cells"], edges=s["edges"],
                     osm=s["osm"], lam=lam)
    return _pack(r, g, rider_key, z_star)


def compare(a, b, rider_key: str = "userA",
            lo: float = 0.15, hi: float = 0.90) -> dict:
    """
    The money shot: the same A and B at two dial settings, side by side.
    Do not make a judge drag a slider and hope — show both at once.
    """
    x, y = route(a, b, rider_key, lo), route(a, b, rider_key, hi)
    out = {"low": x, "high": y, "lo_z": lo, "hi_z": hi}
    if x["ok"] and y["ok"]:
        ca, cb = set(x["cells"]), set(y["cells"])
        out["overlap"] = len(ca & cb) / max(len(ca | cb), 1)
        out["km_ratio"] = y["summary"]["km"] / max(x["summary"]["km"], 1e-9)
        out["demand_gain"] = (y["summary"]["mean_demand"]
                              - x["summary"]["mean_demand"])
        out["headline"] = (
            f"Same two points. {out['km_ratio']:.2f}x the distance, "
            f"{1-out['overlap']:.0%} of it on different roads, "
            f"{out['demand_gain']:+.1f} deg more lean asked of you.")
    return out


# --------------------------------------------------------------------------
# packing — the only place that knows what pydeck wants
# --------------------------------------------------------------------------

def _pack(r, g, rider_key: str, z_star: float) -> dict:
    if not r.ok:
        return {"ok": False, "note": r.note, "path": [], "segments": [],
                "refusals": [], "summary": {}, "explain": [r.note]}

    sc = g.scored
    on = sc.reindex(r.cells)
    path = [[float(lo), float(la)]
            for la, lo in zip(on["lat"].to_numpy(), on["lon"].to_numpy())
            if np.isfinite(la) and np.isfinite(lo)]

    flow = np.nan_to_num(on["flow"].to_numpy(dtype=float))
    dem = np.nan_to_num(on["demand"].to_numpy(dtype=float))
    segments = [{"from": path[i], "to": path[i + 1],
                 "flow": float(flow[i + 1]), "demand": float(dem[i + 1])}
                for i in range(len(path) - 1)]

    summary = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
               for k, v in r.summary.items() if k != "refusals"}
    return {"ok": True, "note": r.note, "cells": list(r.cells), "path": path,
            "segments": segments, "refusals": r.summary.get("refusals", []),
            "summary": summary, "rider": rider_key, "z_star": float(z_star),
            "explain": explain(summary, r.summary.get("refusals", []),
                               _need()["riders"][rider_key]["rider"], z_star,
                               _need()["riders"][rider_key]["grip_p95"],
                               route_cells=list(r.cells))}


def explain(summary: dict, refusals: list, rider, z_star: float,
            rider_grip: float | None = None,
            route_cells: list | None = None) -> list[str]:
    """
    Sentences a human can read out. Explainability is a judged criterion, so
    the reasons live next to the numbers rather than in a slide.
    """
    out = []
    if summary.get("is_loop"):
        out.append(f"A {summary['km']:.0f} km loop back to where you started, "
                   f"{summary['minutes']:.0f} minutes of riding against the "
                   f"{summary['budget_min']:.0f} you asked for.")
        if summary.get("distinct_share", 1) < 0.95:
            out.append(f"{summary['distinct_share']:.0%} of it is road you only "
                       f"ride once; the rest is unavoidable retracing.")
    else:
        out.append(f"{summary['km']:.0f} km, about {summary['minutes']:.0f} "
                   f"minutes.")

    out.append(f"This road asks a mean {summary['mean_demand']:.1f} deg of lean "
               f"and peaks at {summary['max_demand']:.1f} deg. Your gate is "
               f"{rider.gate:.1f} deg, which is 2 sigma above the road you "
               f"habitually ride.")
    out.append(f"Best five kilometres score {summary['peak_flow']:.2f} out of 1 "
               f"for fit at this dial setting.")
    grip = summary.get("grip_lat_p95")
    if grip is not None and np.isfinite(grip):
        msg = (f"Cornering asks about {grip:.0%} of the tyre's grip here")
        if rider_grip and np.isfinite(rider_grip):
            msg += (f", against the {rider_grip:.0%} you have already used on "
                    f"your own rides")
        out.append(msg + ".")
    if refusals:
        out.append(f"{len(refusals)} road(s) near this route were refused "
                   f"outright, not just made expensive:")
        out += [f"    {x['reason']}" for x in refusals[:3]]
    else:
        out.append("Nothing on this route crosses your safety gate.")
    if route_cells:
        out += safety_readout(route_cells)
    if summary.get("imputed_cells"):
        out.append(f"{int(summary['imputed_cells'])} cells had no corner in the "
                   f"crowd data and were treated as straight, not as missing.")
    return out


# --------------------------------------------------------------------------
# offline basemap
# --------------------------------------------------------------------------

def basemap() -> list:
    """
    Grey road polylines from the cached OSM tiles, so the map has context with
    the network unplugged. Built at bake time; None means fall back to tiles.
    """
    return _need().get("basemap") or []


def cells_layer(rider_key: str = "userA", z_star: float = 0.5,
                min_flow: float = 0.0) -> list:
    """Every scored cell, for colouring the map by fit."""
    g = _graph(rider_key, z_star)
    sc = g.scored
    m = sc["flow"].to_numpy(dtype=float) >= min_flow
    sub = sc[m]
    return [{"lat": float(a), "lon": float(o), "flow": float(f),
             "demand": float(d), "gated": bool(x)}
            for a, o, f, d, x in zip(sub["lat"], sub["lon"], sub["flow"],
                                     sub["demand"], sub["gated"])]


# --------------------------------------------------------------------------
# the Joy Meter — fun measured on a ride after it happened (Phase 1, doc 20)
# --------------------------------------------------------------------------

JOY_RIDES = ROOT / "analysis" / "out" / "joy_rides.parquet"
JOY_TEST = ROOT / "analysis" / "out" / "joy_test.json"

_JOY_WORDS = {
    "E_envelope": "how much of the grip circle you used",
    "R_reversals_km": "left-right changes of lean per km",
    "T_throttle_entropy": "how much you worked the throttle",
    "U_uninterrupted": "share of distance you kept moving above 15 km/h",
}


def _load_joy() -> dict | None:
    """Per-ride components + the pre-registered test result, or None if not built."""
    import json
    if not (JOY_RIDES.exists() and JOY_TEST.exists()):
        return None
    return {"rides": pd.read_parquet(JOY_RIDES),
            "test": json.loads(JOY_TEST.read_text())}


def _joy_rides_for(rider_key: str) -> pd.DataFrame:
    j = _need().get("joy")
    if not j:
        return pd.DataFrame()
    d = j["rides"]
    if rider_key.startswith("bike_"):
        return d[(d["rider"] == "userA")
                 & d["bike"].fillna("").str.startswith(rider_key[5:])]
    return d[d["rider"] == rider_key]


def rider_joy(rider_key: str = "userA") -> dict:
    """
    What the Joy Meter says about a rider, AND whether the meter can be
    trusted. The verdict travels with the number on purpose: at WEAK it is a
    measurement to show, not a score to route on.
    """
    j = _need().get("joy")
    person = "userA" if rider_key.startswith("bike_") else rider_key
    if not j or person not in j["test"]:
        return {"ok": False, "note": "Joy Meter not built — run analysis/15_joy_meter.py."}
    t = j["test"][person]
    rides = _joy_rides_for(rider_key)
    lm = [r for r in t["table"] if r["test"] == "length-matched"]
    comp = {r["component"]: {"auc": r["auc"], "ci": [r["ci_lo"], r["ci_hi"]]} for r in lm}
    head = comp.get("joy", {})
    scope = ("all of User A's rides — this bike alone has too few to test"
             if rider_key.startswith("bike_") else "this rider's rides")
    sentences = [
        f"Measured on {int(rides['joy'].notna().sum())} rides, from telemetry alone.",
        f"Tested on {scope}: commutes against same-length stretches of long rides. "
        f"The meter separates them with AUC {head.get('auc', float('nan')):.2f} "
        f"(95% CI {head.get('ci', [np.nan, np.nan])[0]:.2f}–"
        f"{head.get('ci', [np.nan, np.nan])[1]:.2f}): verdict {t['verdict']}.",
    ]
    # a component only "carries" the meter if it clears chance for EVERY rider
    # tested; one that flips direction between riders is named as such
    people = [p for p in ("userA", "userC") if p in j["test"]]
    lm_all = {p: {r["component"]: r for r in j["test"][p]["table"]
                  if r["test"] == "length-matched"} for p in people}
    replicated = [k for k in _JOY_WORDS
                  if all(lm_all[p].get(k, {}).get("ci_lo", 0) > 0.5 for p in people)]
    flipped = [k for k in _JOY_WORDS
               if len({lm_all[p][k]["auc"] > 0.5 for p in people if k in lm_all[p]}) > 1]
    if replicated:
        sentences.append("What carries it on both riders: "
                         + "; ".join(_JOY_WORDS[k] for k in replicated) + ".")
    if flipped:
        sentences.append("Points the opposite way on the other rider, so not trusted: "
                         + "; ".join(_JOY_WORDS[k] for k in flipped) + ".")
    g = t.get("grip_budget", {})
    if g.get("verdict") in ("FAIL", "WEAK"):
        sentences.append(
            f"Tested and not supported: that ABS fires because grip was already spent "
            f"cornering (AUC {g['auc']:.2f}, CI {g['ci_lo']:.2f}–{g['ci_hi']:.2f}).")
    return {"ok": True, "rider": rider_key, "verdict": t["verdict"],
            "length_flag": t["length_flag"], "n_rides": int(rides["joy"].notna().sum()),
            "median_joy": float(rides["joy"].median()) if len(rides) else float("nan"),
            "components": comp, "grip_budget": g, "explain": sentences}


def ride_joy(trip_id: str) -> dict:
    """One ride's components and joy (z-score against its own rider's rides)."""
    j = _need().get("joy")
    if not j:
        return {"ok": False, "note": "Joy Meter not built."}
    d = j["rides"]
    row = d[d["trip_id"].astype(str) == str(trip_id)]
    if row.empty:
        return {"ok": False, "note": f"No ride {trip_id} in the Joy table."}
    r = row.iloc[0]
    keys = ("km", "minutes", "joy", "lean_p90", "loop_closure_km",
            "E_envelope", "R_reversals_km", "T_throttle_entropy", "U_uninterrupted")
    return {"ok": True, "rider": r["rider"], "trip_id": str(trip_id),
            **{k: (float(r[k]) if pd.notna(r[k]) else None) for k in keys},
            "verdict": j["test"].get(r["rider"], {}).get("verdict")}


# --------------------------------------------------------------------------
# road character — Phase 2, doc 21. Safety readout and the gem pool.
# Nothing here changes a route: it reads what the route already is.
# --------------------------------------------------------------------------

GEMS_CSV = ROOT / "analysis" / "out" / "crowd_gems_s2.csv"
CHARACTER_TEST = ROOT / "analysis" / "out" / "road_character_test.json"


def _load_character() -> dict:
    """Gems, the 18-char surprise boundaries, and the pre-registered verdicts."""
    import json
    out = {"gems": None, "surprise": None, "test": None}
    if GEMS_CSV.exists():
        out["gems"] = pd.read_csv(GEMS_CSV, dtype={"morton_code": str})
    fine = R.OUT / "graph_edges_s2.parquet"
    if fine.exists():
        out["surprise"] = R.surprise_boundaries(R.load_edges("_s2", symmetrise=False))
    if CHARACTER_TEST.exists():
        out["test"] = json.loads(CHARACTER_TEST.read_text())
    return out


def _verdict(name: str) -> str | None:
    t = (_need().get("character") or {}).get("test") or {}
    return (t.get(name) or {}).get("verdict")


def safety_readout(route_cells: list) -> list[str]:
    """
    What the crowd's own events say about the road under this route, read out
    beside the fun score and never inside it.

    Hard braking is a COUNT of trips, always worded as one ("3 of the 12 trips
    that ride this stretch"), because the lake has no rider ids and a handful
    of events is not a crowd. Whether it may also be called recurring is
    decided by analysis/16_road_character.py, not here.

    Tightening bends are shown only if surprise passed its braking test there.
    """
    s = _need()
    c = s["cells"]
    if not route_cells or "abs_rides" not in c.columns:
        return []
    if "_cidx" not in s:
        s["_cidx"] = c.set_index("morton_code")
    on = s["_cidx"].reindex(route_cells)
    lat = on["lat"].to_numpy(dtype=float)
    lon = on["lon"].to_numpy(dtype=float)
    step = np.r_[0.0, np.nan_to_num(R._haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:]))]
    km = np.cumsum(step) / 1000.0

    out = []
    hz = np.nan_to_num(on["abs_rides"].to_numpy(dtype=float))
    nr = np.nan_to_num(on["n_rides"].to_numpy(dtype=float))
    seen, picks = set(), []
    for i in np.argsort(-hz, kind="stable"):
        if hz[i] < R.HAZARD_MIN_RIDES or len(picks) >= 2:
            break
        if route_cells[i] not in seen:
            seen.add(route_cells[i])
            picks.append(i)
    # REPEATABLE is a population result (doc 21), so the sentence claims it for
    # stretches like this one, never for this particular cell
    tail = ("across the crowd data, stretches where this happens tend to see it "
            "again in other trips." if _verdict("hazard") == "REPEATABLE"
            else "a count of what happened, not a prediction.")
    for i in sorted(picks):
        out.append(f"Hard braking around km {km[i]:.0f}: {int(hz[i])} of the {int(nr[i])} "
                   f"trips that ride this stretch set off the ABS hard-braking code here - {tail}")

    sb = (s.get("character") or {}).get("surprise")
    if sb is not None and len(sb) and _verdict("surprise") == "PASS":
        hits = []
        for k in range(len(route_cells) - 1):
            key = (route_cells[k], route_cells[k + 1])
            if key in sb.index:
                row = sb.loc[key]
                if float(row["surprise"]) >= R.SURPRISE_MIN:
                    hits.append((float(row["surprise"]), k + 1, row))
        for _, k, row in sorted(sorted(hits, key=lambda h: -h[0])[:2], key=lambda h: h[1]):
            out.append(f"Tightening bend around km {km[k]:.0f}: the corner radius drops from "
                       f"{float(row['radius_i']):.0f} m to {float(row['radius_j']):.0f} m in one "
                       f"step. Shown for safety; it is not part of the fun score.")
    return out


def gem_pool(rider_key: str = "userA", z_star: float = 0.5, n: int = 20) -> list[dict]:
    """
    The crowd's best corners (crowd_gems_s2.csv, already ranked) as candidate
    turnaround points for Phase 4's arc loop. A gem is `routable` when its
    16-char routing cell is a node of this rider's graph and is not gated.
    """
    s = _need()
    gems = (s.get("character") or {}).get("gems")
    if gems is None:
        return []
    g = _graph(rider_key, z_star)
    sc = g.scored
    out = []
    for r in gems.head(n).itertuples(index=False):
        c16 = str(r.morton_code)[:16]
        known = c16 in sc.index
        gated = bool(sc.at[c16, "gated"]) if known else None
        out.append({"lat": float(r.lat), "lon": float(r.lon), "gem_score": float(r.gem_score),
                    "demand_p90": float(r.demand_p90), "n_rides": int(r.n_rides),
                    "cell16": c16, "in_graph": c16 in g.index, "gated": gated,
                    "flow": float(sc.at[c16, "flow"]) if known else None,
                    "routable": bool(c16 in g.index and known and not gated)})
    return out
