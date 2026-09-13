"""
18_answer_types.py — new kinds of answer, tested before they are offered.   (Phase 4, doc 23)

  arc_loop      F4.3  a loop composed as warm-up -> peak at ~2/3 -> easy return, from
                      today's own loop candidates plus crowd gems, ridden either way round
  pareto        F4.2  the time-vs-lean trade-off for an A -> B across dial x offered modes:
                      is there a frontier worth showing, or one or two routes?
  commute       F4.6  are there habitual commutes inside the crowd box to upgrade?
  stop_rate           split-half, because urban wander rests on it
  urban_wander  F4.5  does the urban mode keep a town loop moving and off the busy roads?
  F4.4 / F4.7 / F4.8  recorded: built earlier / built earlier / not built (T4)

Every threshold below was fixed before this script first ran. Output is
aggregates only — no trip ids, no ride coordinates: analysis/out/answer_types_test.json.
Joy is WEAK (doc 20) and is never an objective or a judge here.

Run (after 10_crowd_layer.py and 17_riders_modes.py):
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    $V analysis/18_answer_types.py
"""

from __future__ import annotations

import glob
import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import flowstate as F       # noqa: E402
import router as R          # noqa: E402
import service as S         # noqa: E402

OUT = R.OUT
C_DIR = ROOT / "data" / "raw" / "salvaged" / "exampleUserC" / "recordedTrips"

# ------------------------------------------------------------------------------
# PRE-REGISTERED. Fixed before the first run.
# ------------------------------------------------------------------------------
RIDER = "userA"
ARC_DIAL = 0.50                  # the Flow preset
ARC_HOURS = (1.0, 2.0, 3.0)      # x the 4 preset loop starts = 12 loops
ARC_BETTER = 0.75                # arc error at most 3/4 of today's loop's ...
ARC_PEAK_WINDOW = (0.55, 0.80)   # ... and the best riding lands in this share of the ride
ARC_PASS_N = 9                   # of 12; 5-8 PARTIAL
ARC_PARTIAL_N = 5
PARETO_DIALS = S.PARETO_DIALS
PARETO_MIN_FRONT = 3             # a frontier worth drawing has >= 3 distinct non-dominated routes
PARETO_PASS_SHARE = 0.50         # ... on at least half of the O-D pairs
COMMUTE_KM = (5.0, 20.0)
COMMUTE_IN_BOX = 0.50
COMMUTE_JACCARD = 0.50           # a habitual ride shares >= half its cells with >= 2 others
COMMUTE_MIN_HABITUAL = 10
HALF_MIN_TRAV = 10
RELIABLE_RHO = 0.50
URBAN_TOWNS = {"Weilheim": (47.84, 11.14), "Garmisch-Partenkirchen": (47.49, 11.10),
               "Starnberg": (48.00, 11.34), "Bad Toelz": (47.76, 11.56),
               "Miesbach": (47.79, 11.83), "Murnau": (47.68, 11.20)}
URBAN_HOURS = 1.0
URBAN_PASS_N = 5                 # of 6 towns: lower stop rate AND fewer rides per cell than Flow
N_BOOT = 2000
SEED = 7


def r3(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 3)


def spearman(x, y) -> float:
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def split_half(H: pd.DataFrame, col: str, rng) -> dict:
    a = H[H["half"] == 0].set_index("morton_code")
    b = H[H["half"] == 1].set_index("morton_code")
    j = a[[col, "n_trav"]].join(b[[col, "n_trav"]], lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j["n_trav_a"] >= HALF_MIN_TRAV) & (j["n_trav_b"] >= HALF_MIN_TRAV)].dropna()
    x, y = j[col + "_a"].to_numpy(float), j[col + "_b"].to_numpy(float)
    bs = [spearman(x[i], y[i]) for i in (rng.integers(0, len(x), len(x)) for _ in range(N_BOOT))]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    rho = spearman(x, y)
    return {"rho": r3(rho), "ci": [r3(lo), r3(hi)], "n": int(len(x)),
            "verdict": "RELIABLE" if rho >= RELIABLE_RHO else "UNRELIABLE"}


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / max(len(a | b), 1)


# ------------------------------------------------------------------------------

def t_arc() -> dict:
    s = S._need()
    cells, edges, osm = s["cells"], s["edges"], s["osm"]
    rider = s["riders"][RIDER]["rider"]
    g = R.build_graph(edges, cells, rider, ARC_DIAL, osm=osm)
    gems = S.gem_cells()
    rows = []
    for p in S.PRESET_LOOPS:
        for h in ARC_HOURS:
            t0 = time.time()
            b = R.route_loop(p["start"], h, rider, ARC_DIAL, graph=g, cells=cells, edges=edges, osm=osm)
            t1 = time.time()
            a = R.route_loop_arc(p["start"], h, rider, ARC_DIAL, graph=g, cells=cells, edges=edges,
                                 osm=osm, gem_cells=gems)
            t2 = time.time()
            if not (b.ok and a.ok and "arc_error" in a.summary):
                rows.append({"start": p["key"], "hours": h, "ok": False})
                continue
            su = a.summary
            fill_ok = abs(su["budget_fill"] - 1.0) <= max(0.20, abs(b.summary["budget_fill"] - 1.0))
            achieved = (su["arc_error"] <= ARC_BETTER * su["base_arc_error"]
                        and ARC_PEAK_WINDOW[0] <= su["arc_peak_at"] <= ARC_PEAK_WINDOW[1]
                        and fill_ok)
            rows.append({"start": p["key"], "hours": h, "ok": True, "achieved": bool(achieved),
                         "base_arc_error": r3(su["base_arc_error"]), "arc_error": r3(su["arc_error"]),
                         "base_peak_at": r3(su["base_arc_peak_at"]), "arc_peak_at": r3(su["arc_peak_at"]),
                         "base_minutes": r3(b.summary["minutes"]), "arc_minutes": r3(su["minutes"]),
                         "base_km": r3(b.summary["km"]), "arc_km": r3(su["km"]),
                         "base_distinct": r3(b.summary["distinct_share"]), "arc_distinct": r3(su["distinct_share"]),
                         "base_mean_flow_lenweighted": r3(b.summary["mean_flow"]),
                         "arc_mean_flow_lenweighted": r3(su["mean_flow"]),
                         "shared_cells": r3(jaccard(b.cells, a.cells)),
                         "changed": bool(su["arc_changed"]), "reversed": bool(su["arc_reversed"]),
                         "turnaround_gem": bool(su["arc_turnaround_gem"]),
                         "gem_candidates": int(su["gem_candidates"]),
                         "ms_base": round(1000 * (t1 - t0)), "ms_arc": round(1000 * (t2 - t1))})
    ok = [r for r in rows if r["ok"]]
    n = sum(r["achieved"] for r in ok)
    return {"dial": ARC_DIAL, "rider": RIDER, "loops": rows, "achieved": int(n), "of": len(rows),
            "achieved_by_reversal_only": int(sum(r["achieved"] and r["reversed"] and r["shared_cells"] == 1.0
                                                 for r in ok)),
            "median_arc_error": [r3(np.median([r["base_arc_error"] for r in ok])),
                                 r3(np.median([r["arc_error"] for r in ok]))],
            "verdict": "PASS" if n >= ARC_PASS_N else "PARTIAL" if n >= ARC_PARTIAL_N else "FAIL"}


def t_pareto() -> dict:
    s = S._need()
    cells, edges, osm = s["cells"], s["edges"], s["osm"]
    rider = s["riders"][RIDER]["rider"]
    offered = [m["key"] for m in S.modes() if m["offered"]]
    graphs = {(m, z): R.build_graph(edges, cells, rider, z, osm=osm, mode=m)
              for m in offered for z in PARETO_DIALS}
    anchors = [(round(float(la), 3), round(float(lo), 3))
               for la in np.arange(47.45, 48.01, 0.14) for lo in np.arange(10.80, 11.95, 0.19)]
    per = []
    for A, B in itertools.combinations(anchors, 2):
        if not 25 < 111 * np.hypot(B[0] - A[0], (B[1] - A[1]) * 0.67) < 75:
            continue
        rows = []
        for (m, z), g in graphs.items():
            r = R.route_a_to_b(A, B, rider, z, graph=g, cells=cells, edges=edges, osm=osm, mode=m)
            if r.ok and not r.note:
                rows.append({"mode": m, "z_star": z, "cells": r.cells, "minutes": r.summary["minutes"],
                             "mean_demand": r.summary["mean_demand"]})
        if len(rows) < len(graphs):
            continue
        front = S.nondominated(rows)
        per.append({"distinct": len({tuple(r["cells"]) for r in rows}), "front": len(front),
                    "front_minutes_span": front[-1]["minutes"] - front[0]["minutes"],
                    "front_demand_span": front[-1]["mean_demand"] - front[0]["mean_demand"],
                    "front_modes": sorted({r["mode"] for r in front})})
    d = pd.DataFrame(per)
    share = float((d["front"] >= PARETO_MIN_FRONT).mean())
    wide = d[d["front"] >= 2]
    return {"dials": list(PARETO_DIALS), "modes": offered, "pairs": int(len(d)),
            "distinct_routes_median": r3(d["distinct"].median()),
            "front_size_counts": {int(k): int(v) for k, v in d["front"].value_counts().sort_index().items()},
            "share_front_ge_3": r3(share),
            "on_fronts_ge_2_extra_minutes_median": r3(wide["front_minutes_span"].median()) if len(wide) else None,
            "on_fronts_ge_2_extra_demand_deg_median": r3(wide["front_demand_span"].median()) if len(wide) else None,
            "share_fronts_using_a_non_flow_mode": r3(float(d["front_modes"].map(lambda x: x != ["flow"]).mean())),
            "verdict": "PASS" if share >= PARETO_PASS_SHARE else "THIN"}


def t_commute() -> dict:
    lo_la, hi_la, lo_lo, hi_lo = R.COVERAGE
    cset = set(S._need()["cells"]["morton_code"])

    def summarise(rides: list[dict]) -> dict:
        d = pd.DataFrame(rides)
        short = d[d["km"].between(*COMMUTE_KM)]
        inbox = short[short["inbox"] >= COMMUTE_IN_BOX]
        sets = dict(zip(inbox["id"], inbox["cells"]))
        hab = sum(1 for t in sets
                  if sum(1 for u in sets if u != t and jaccard(sets[t], sets[u]) >= COMMUTE_JACCARD) >= 2)
        return {"rides": int(len(d)), "commute_length": int(len(short)),
                "commute_length_in_box": int(len(inbox)), "habitual_in_box": int(hab)}

    man = F.load_manifest()
    km = dict(zip(man["trip_id"].astype(str), man["km_manifest"]))
    tp = pd.read_parquet(F.TRACKPOINTS, columns=["trip_id", "positionmapmatchedlatitude",
                                                 "positionmapmatchedlongitude", "morton_code"])
    ra = []
    for tid, g in tp.groupby(tp["trip_id"].astype(str)):
        la, lo = g["positionmapmatchedlatitude"].to_numpy(), g["positionmapmatchedlongitude"].to_numpy()
        ra.append({"id": tid, "km": km.get(tid, np.nan),
                   "inbox": float(((la >= lo_la) & (la <= hi_la) & (lo >= lo_lo) & (lo <= hi_lo)).mean()),
                   "cells": set(g["morton_code"].astype(str).str.slice(0, 16)) & cset})
    rc = []
    for f in sorted(glob.glob(str(C_DIR / "*.csv"))):
        if os.path.basename(f).startswith("._"):
            continue
        d = pd.read_csv(f, usecols=["positionmapmatchedlatitude", "positionmapmatchedlongitude", "morton_code"],
                        dtype={"morton_code": str}).dropna()
        if len(d) < 10:
            continue
        la, lo = d["positionmapmatchedlatitude"].to_numpy(), d["positionmapmatchedlongitude"].to_numpy()
        st = R._haversine_m(la[:-1], lo[:-1], la[1:], lo[1:])
        rc.append({"id": Path(f).stem, "km": float(st[st < 500].sum() / 1000),
                   "inbox": float(((la >= lo_la) & (la <= hi_la) & (lo >= lo_lo) & (lo <= hi_lo)).mean()),
                   "cells": set(d["morton_code"].str.slice(0, 16)) & cset})
    out = {"userA": summarise(ra), "userC": summarise(rc),
           "note": "user A km from the BMW manifest; user C km summed from map-matched steps < 500 m"}
    best = max(out["userA"]["habitual_in_box"], out["userC"]["habitual_in_box"])
    out["verdict"] = "BUILDABLE" if best >= COMMUTE_MIN_HABITUAL else "BLOCKED-COVERAGE"
    return out


def t_urban(H: pd.DataFrame, rng) -> tuple[dict, dict]:
    sr = split_half(H, "stop_rate", rng)
    s = S._need()
    cells, edges, osm = s["cells"], s["edges"], s["osm"]
    rider = s["riders"][RIDER]["rider"]
    ci = cells.set_index("morton_code")
    res = (osm["red_inner_city"].fillna(False).astype(bool) if osm is not None
           and "red_inner_city" in osm.columns else pd.Series(dtype=bool))
    touched = set(pd.read_parquet(F.TRACKPOINTS, columns=["morton_code"])["morton_code"]
                  .astype(str).str.slice(0, 16))
    gF = R.build_graph(edges, cells, rider, 0.5, osm=osm)
    gU = R.build_graph(edges, cells, rider, 0.5, osm=osm, mode="urban")

    def describe(r):
        c = r.cells
        return {"km": r3(r.summary["km"]), "minutes": r3(r.summary["minutes"]),
                "distinct": r3(r.summary.get("distinct_share", np.nan)),
                "stop_rate": r3(float(ci["stop_rate"].reindex(c).mean())),
                "n_rides": r3(float(ci["n_rides"].reindex(c).mean())),
                "residential_share": r3(float(res.reindex(c).fillna(False).mean())) if len(res) else None,
                "novel_to_rider_share": r3(float(np.mean([x not in touched for x in c])))}
    towns, wins = {}, 0
    for name, st in URBAN_TOWNS.items():
        f = R.route_loop(st, URBAN_HOURS, rider, 0.5, graph=gF, cells=cells, edges=edges, osm=osm)
        u = R.route_loop(st, URBAN_HOURS, rider, 0.5, graph=gU, cells=cells, edges=edges, osm=osm, mode="urban")
        if not (f.ok and u.ok):
            towns[name] = {"ok": False, "note": (f.note if not f.ok else u.note)[:120]}
            continue
        df, du = describe(f), describe(u)
        win = du["stop_rate"] < df["stop_rate"] and du["n_rides"] < df["n_rides"]
        wins += win
        towns[name] = {"ok": True, "flow": df, "urban": du, "shared_cells": r3(jaccard(f.cells, u.cells)),
                       "urban_moves_less_and_novel": bool(win)}
    out = {"hours": URBAN_HOURS, "towns": towns, "wins": int(wins), "of": len(URBAN_TOWNS),
           "note": "BMW's RED inner-city multiplier (x0.45 on residential) stays on in every mode; "
                   "crowd timestamps are shifted, so time-of-day flow is not computable"}
    out["verdict"] = ("COLUMN-UNRELIABLE" if sr["verdict"] != "RELIABLE"
                      else "PASS" if wins >= URBAN_PASS_N else "FAIL")
    return sr, out


if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    S.init(force_parquet=True)
    H = pd.read_parquet(OUT / "crowd_halves_c16.parquet")
    H["morton_code"] = H["morton_code"].astype(str)
    res = {"preregistered": {k: v for k, v in globals().items()
                             if k.isupper() and isinstance(v, (int, float, str, tuple)) and k != "OUT"}}
    res["preregistered"]["URBAN_TOWNS"] = {k: list(v) for k, v in URBAN_TOWNS.items()}

    def step(name, fn):
        t1 = time.time()
        res[name] = fn()
        print(f"{name:<13s} {res[name].get('verdict', '-'):<18s} ({time.time() - t1:5.1f} s)", flush=True)

    step("arc_loop", t_arc)
    step("pareto", t_pareto)
    step("commute", t_commute)
    t1 = time.time()
    res["stop_rate"], res["urban_wander"] = t_urban(H, rng)
    print(f"stop_rate     {res['stop_rate']['verdict']}\nurban_wander  {res['urban_wander']['verdict']}"
          f"  ({time.time() - t1:5.1f} s)", flush=True)
    res["edge_disjoint_return"] = {"feature": "F4.4", "verdict": "BUILT-EARLIER",
                                   "evidence": "route_loop penalises used edges 6x on the return (doc 16); "
                                               "distinct share is reported on every loop"}
    res["gate_visible"] = {"feature": "F4.7", "verdict": "BUILT-EARLIER",
                           "evidence": "refused edges are deleted and listed with a reason (docs 14, 17)"}
    res["solar_thermal"] = {"feature": "F4.8", "verdict": "NOT-BUILT",
                            "evidence": "T4 in FEATURES.md; out of scope by the phase plan (doc 19)"}

    p = OUT / "answer_types_test.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "preregistered"}, indent=1))
    print(f"\nwrote {p}  in {time.time() - t0:.1f} s")
