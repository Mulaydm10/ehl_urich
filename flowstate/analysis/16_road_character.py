"""
16_road_character.py — do the Phase 2 columns measure the ROAD?   (doc 21)

The crowd lake has no rider ids, so the question "is this a property of the
road or of whoever happened to ride it" is answered the only way the data
allows: split the 7,976 rides into two disjoint halves (odd / even ride index),
rebuild every column on each half, and ask whether the two halves agree cell by
cell. A column that does not replicate across disjoint rides is noise about
riders, and is recorded as such.

Where a column makes a physical or external claim, that claim is tested too:
rhythm wavelength against the corner radius from a different channel, crowd
viewpoints against OpenStreetMap, tightening bends against braking on the step
into them, hazards against themselves in the other half.

Every threshold below was fixed before this script first ran. None was tuned
on its result. Outputs are aggregates only (no coordinates, no trip ids):
analysis/out/road_character_test.json.

The one network call is a cached Overpass query for tourism=viewpoint over
the same generic box 13_osm_layer.py uses. Nothing from the lake is sent.

Run (after analysis/10_crowd_layer.py for _s2 and _c16, and 13_osm_layer.py):
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    $V analysis/16_road_character.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import router as R          # noqa: E402

OUT = R.OUT
VIEW_CACHE = ROOT / "data" / "osm" / "viewpoints.json"
BBOX = (47.3, 10.6, 48.1, 12.0)          # 13_osm_layer.py's box; nothing lake-derived
ENDPOINTS = ["https://overpass.kumi.systems/api/interpreter",
             "https://overpass-api.de/api/interpreter",
             "https://overpass.osm.ch/api/interpreter"]

# ------------------------------------------------------------------------------
# PRE-REGISTERED. Fixed before the first run.
# ------------------------------------------------------------------------------
PRIMARY = "_c16"                 # the grid score_cells reads; _s2 reported beside it
HALF_MIN_TRAV = 10               # split-half: >= 10 traversals in EACH half
RELIABLE_RHO = 0.50              # split-half Spearman for "a property of the road"
REDUNDANT_RHO = 0.90             # dwell_share vs stop_rate: above this it adds nothing
RHY_HALF_MIN_RIDES = 5           # rhythmic rides per half
RHY_PHYS_MIN_RIDES = 10
RHY_PHYS_RHO = 0.30              # wavelength must rise with corner radius (+ sign)
VIEW_GRID = "_s2"                # a viewpoint is a point; the fine grid
VIEW_HIT_M = 300.0
VIEW_MIN_CANDIDATES = 10
VIEW_LIFT = 2.0                  # hit rate >= 2x the matched random null ...
VIEW_P = 0.05                    # ... and beaten by < 5% of null draws
VIEW_NULL_DRAWS = 5000
HAZARD_LIFT = 2.0                # exposure-stratified risk ratio across halves
SURPRISE_GRID = "_s2"            # surprise exists only at 18 chars
SURPRISE_MIN_RIDES = 5
SURPRISE_CONTROL = float(np.log(1.25))
SURPRISE_LIFT = 1.5              # radius-stratified braking ratio, tightening vs stable
STRATA = 5
N_BOOT = 2000
SEED = 7


# ------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------

def _finite(*a):
    m = np.ones(len(a[0]), dtype=bool)
    for x in a:
        m &= np.isfinite(np.asarray(x, dtype=float))
    return m


def spearman(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = _finite(x, y)
    if m.sum() < 10:
        return float("nan")
    return float(np.corrcoef(rankdata(x[m]), rankdata(y[m]))[0, 1])


def spearman_ci(x, y, rng) -> tuple[float, float, float, int]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = _finite(x, y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 10:
        return float("nan"), float("nan"), float("nan"), n
    bs = []
    for _ in range(N_BOOT):
        i = rng.integers(0, n, n)
        bs.append(np.corrcoef(rankdata(x[i]), rankdata(y[i]))[0, 1])
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return spearman(x, y), float(lo), float(hi), n


def r3(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 3)


def split_half(H: pd.DataFrame, col: str, need_col: str, need: float, rng,
               drop: pd.Index | None = None) -> dict:
    a = H[H["half"] == 0].set_index("morton_code")
    b = H[H["half"] == 1].set_index("morton_code")
    j = a[[col, need_col]].join(b[[col, need_col]], lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j[need_col + "_a"] >= need) & (j[need_col + "_b"] >= need)]
    if drop is not None:
        j = j[~j.index.isin(drop)]
    r, lo, hi, n = spearman_ci(j[col + "_a"], j[col + "_b"], rng)
    return {"rho": r3(r), "ci": [r3(lo), r3(hi)], "n_cells": int(n)}


def load(tag: str) -> dict:
    cells = R.load_cells(tag)
    osm = R.load_osm(tag)
    cells = R.apply_legal_speed(cells, osm)
    H = pd.read_parquet(OUT / f"crowd_halves{tag}.parquet")
    H["morton_code"] = H["morton_code"].astype(str)
    residential = (osm.index[osm["red_inner_city"].fillna(False).astype(bool)]
                   if osm is not None else pd.Index([]))
    return {"cells": cells.set_index("morton_code"), "osm": osm, "halves": H,
            "character": R.road_character(cells, osm), "residential": residential}


# ------------------------------------------------------------------------------
# the tests
# ------------------------------------------------------------------------------

def t_dwell(L, rng) -> dict:
    out = {}
    for tag, d in L.items():
        c = d["cells"]
        big = c[c["n_rides"] >= 20]
        out[tag] = {"split_half": split_half(d["halves"], "dwell_share", "n_trav", HALF_MIN_TRAV, rng),
                    "rho_vs_stop_rate": r3(spearman(big["dwell_share"], big["stop_rate"])),
                    "share_cells_nonzero": r3(float((c["dwell_share"] > 0).mean()))}
    p = out[PRIMARY]
    rel = (p["split_half"]["rho"] or 0) >= RELIABLE_RHO
    red = (p["rho_vs_stop_rate"] or 0) >= REDUNDANT_RHO
    out["verdict"] = ("UNRELIABLE" if not rel else "RELIABLE-BUT-REDUNDANT" if red else "RELIABLE")
    return out


def t_reversals(L, rng) -> dict:
    out = {}
    for tag, d in L.items():
        c = d["cells"]
        ok = (c["n_rides"] >= 10) & (c["km_ridden"] >= 1.0)
        res = c.index.isin(d["residential"])
        out[tag] = {
            "split_half_masked": split_half(d["halves"], "reversals_km", "n_trav", HALF_MIN_TRAV,
                                            rng, drop=d["residential"]),
            "split_half_unmasked": split_half(d["halves"], "reversals_km", "n_trav", HALF_MIN_TRAV, rng),
            "median_residential": r3(float(c.loc[ok & res, "reversals_km"].median())),
            "median_not_residential": r3(float(c.loc[ok & ~res, "reversals_km"].median())),
            "n_residential": int((ok & res).sum()), "n_not_residential": int((ok & ~res).sum()),
            "rho_vs_demand_not_residential": r3(spearman(c.loc[ok & ~res, "reversals_km"],
                                                         c.loc[ok & ~res, "demand_p90"])),
        }
    out["verdict"] = ("RELIABLE" if (out[PRIMARY]["split_half_masked"]["rho"] or 0) >= RELIABLE_RHO
                      else "UNRELIABLE")
    return out


def t_rhythm(L, rng) -> dict:
    out = {}
    for tag, d in L.items():
        c = d["cells"]
        phys = c[c["rhythm_rides"] >= RHY_PHYS_MIN_RIDES]
        r, lo, hi, n = spearman_ci(phys["rhythm_wavelength_m"], phys["radius_p50"], rng)
        out[tag] = {"split_half": split_half(d["halves"], "rhythm_wavelength_m", "rhythm_rides",
                                             RHY_HALF_MIN_RIDES, rng),
                    "rho_wavelength_vs_radius": {"rho": r3(r), "ci": [r3(lo), r3(hi)], "n_cells": n},
                    "wavelength_m_p10_p50_p90": [r3(v) for v in
                                                 np.nanpercentile(phys["rhythm_wavelength_m"], [10, 50, 90])]
                    if len(phys) else None,
                    "cells_with_rhythm": int((c["rhythm_rides"] > 0).sum())}
    p = out[PRIMARY]
    rel = (p["split_half"]["rho"] or 0) >= RELIABLE_RHO
    phy = (p["rho_wavelength_vs_radius"]["rho"] or 0) >= RHY_PHYS_RHO
    out["verdict"] = ("PASS" if rel and phy else "FAIL-RELIABILITY" if phy
                      else "FAIL-PHYSICS" if rel else "FAIL-BOTH")
    return out


def t_adventure(L, rng) -> dict:
    out = {}
    for tag, d in L.items():
        c = d["cells"].join(d["character"][["adventure_index"]])
        c = c[c["n_rides"] >= R.ADVENTURE_MIN_RIDES]
        rarity = 1.0 / np.log1p(c["n_rides"].to_numpy(dtype=float))
        top = c["adventure_index"] >= c["adventure_index"].quantile(0.95)
        snap = (d["osm"]["osm_dist_m"].reindex(c.index).notna() if d["osm"] is not None
                else pd.Series(False, index=c.index))
        out[tag] = {"rho_vs_demand": r3(spearman(c["adventure_index"], c["demand_p90"])),
                    "rho_vs_rarity": r3(spearman(c["adventure_index"], rarity)),
                    "osm_snap_share_top5pct": r3(float(snap[top].mean())),
                    "osm_snap_share_all": r3(float(snap.mean())),
                    "n_cells": int(len(c))}
    p = out[PRIMARY]
    out["verdict"] = ("PASS" if abs(p["rho_vs_demand"] or 0) > abs(p["rho_vs_rarity"] or 0)
                      else "RARITY-DOMINATED")
    return out


def fetch_viewpoints() -> pd.DataFrame:
    VIEW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not (VIEW_CACHE.exists() and VIEW_CACHE.stat().st_size > 200):
        s, w, n, e = BBOX
        q = f'[out:json][timeout:90];nwr["tourism"="viewpoint"]({s},{w},{n},{e});out center;'
        for attempt in range(6):
            try:
                r = requests.post(ENDPOINTS[attempt % len(ENDPOINTS)], data={"data": q},
                                  headers={"User-Agent": "flowstate-hackathon/1.0"}, timeout=120)
                if r.status_code == 200 and r.content.startswith(b"{"):
                    VIEW_CACHE.write_bytes(r.content)
                    break
                raise RuntimeError(f"HTTP {r.status_code}")
            except Exception as exc:
                print(f"  overpass: {exc} — retrying")
                time.sleep(6 * (attempt + 1))
        else:
            raise SystemExit("viewpoint fetch failed on every mirror")
    rows = []
    for el in json.loads(VIEW_CACHE.read_bytes()).get("elements", []):
        la = el.get("lat", (el.get("center") or {}).get("lat"))
        lo = el.get("lon", (el.get("center") or {}).get("lon"))
        if la is not None and lo is not None:
            rows.append((float(la), float(lo)))
    return pd.DataFrame(rows, columns=["lat", "lon"])


def t_viewpoints(L, rng) -> dict:
    d = L[VIEW_GRID]
    c = d["cells"].join(d["character"][["viewpoint_candidate"]])
    vp = fetch_viewpoints()
    lat0 = float(c["lat"].mean())
    kx = 111320.0 * np.cos(np.radians(lat0))
    tree = cKDTree(np.c_[vp["lat"].to_numpy() * 110540.0, vp["lon"].to_numpy() * kx])
    dist, _ = tree.query(np.c_[c["lat"].to_numpy() * 110540.0, c["lon"].to_numpy() * kx], k=1)
    c["hit"] = dist <= VIEW_HIT_M

    pool = c[(c["n_rides"] >= R.VIEW_MIN_STOP_RIDES) & c["elev_prominence_m"].notna()].copy()
    pool["stratum"] = pd.qcut(pool["n_rides"].rank(method="first"), STRATA, labels=False)
    cand = pool[pool["viewpoint_candidate"]]
    obs = float(cand["hit"].mean()) if len(cand) else float("nan")

    null = np.zeros(VIEW_NULL_DRAWS)
    if len(cand):
        need = cand["stratum"].value_counts()
        groups = {s: pool.loc[pool["stratum"] == s, "hit"].to_numpy() for s in need.index}
        for k in range(VIEW_NULL_DRAWS):
            h = 0
            for s, m in need.items():
                g = groups[s]
                h += g[rng.choice(len(g), size=min(m, len(g)), replace=False)].sum()
            null[k] = h / len(cand)
    stops = (c["long_stop_rides"] >= R.VIEW_MIN_STOP_RIDES) & \
            (c["long_stop_rides"] / c["n_rides"] >= R.VIEW_MIN_STOP_SHARE)
    high = c["elev_prominence_m"] >= R.VIEW_MIN_PROMINENCE_M
    out = {
        "grid": VIEW_GRID, "osm_viewpoints_in_box": int(len(vp)),
        "n_candidates": int(len(cand)), "candidate_hit_rate": r3(obs),
        "null_hit_rate_mean": r3(float(null.mean())) if len(cand) else None,
        "lift": r3(obs / null.mean()) if len(cand) and null.mean() > 0 else None,
        "p_null_ge_obs": r3(float((null >= obs).mean())) if len(cand) else None,
        "contrast_stops_not_high": {"n": int((stops & ~high).sum()),
                                    "hit_rate": r3(float(c.loc[stops & ~high, "hit"].mean()))},
        "contrast_high_no_stops": {"n": int((high & ~stops).sum()),
                                   "hit_rate": r3(float(c.loc[high & ~stops, "hit"].mean()))},
        "all_cells_hit_rate": r3(float(c["hit"].mean())),
        "cells_with_any_long_stop": int((c["long_stop_rides"] > 0).sum()),
    }
    if len(cand) < VIEW_MIN_CANDIDATES:
        out["verdict"] = "INSUFFICIENT-DATA"
    elif (out["lift"] or 0) >= VIEW_LIFT and (out["p_null_ge_obs"] or 1) < VIEW_P:
        out["verdict"] = "PASS"
    else:
        out["verdict"] = "FAIL"
    return out


def t_traffic(L, rng) -> dict:
    out = {}
    for tag, d in L.items():
        c = d["cells"].join(d["character"][["traffic_on_good_road"]])
        flagged = c[c["traffic_on_good_road"]]
        cls = (d["osm"]["osm_highway"].reindex(flagged.index).fillna("no match").value_counts()
               .head(5).to_dict() if d["osm"] is not None else {})
        out[tag] = {"split_half": split_half(d["halves"], "traffic_share", "traffic_trav",
                                             HALF_MIN_TRAV, rng),
                    "cells_flagged": int(len(flagged)),
                    "share_cells_traffic_gt0": r3(float((c["traffic_share"] > 0).mean())),
                    "flagged_osm_class": {str(k): int(v) for k, v in cls.items()}}
    out["verdict"] = ("RELIABLE" if (out[PRIMARY]["split_half"]["rho"] or 0) >= RELIABLE_RHO
                      else "UNRELIABLE")
    return out


def _mh_ratio(event, exposed, stratum) -> float:
    """Mantel-Haenszel risk ratio of `event` for exposed vs unexposed, over strata."""
    num = den = 0.0
    for s in np.unique(stratum):
        m = stratum == s
        e, x = event[m], exposed[m]
        n1, n0 = x.sum(), (~x).sum()
        if n1 == 0 or n0 == 0:
            continue
        N = n1 + n0
        num += e[x].sum() * n0 / N
        den += e[~x].sum() * n1 / N
    return num / den if den > 0 else float("nan")


def t_hazard(L, rng) -> dict:
    H = L[PRIMARY]["halves"]
    a = H[H["half"] == 0].set_index("morton_code")
    b = H[H["half"] == 1].set_index("morton_code")
    j = a[["abs_rides", "n_trav"]].join(b[["abs_rides", "n_trav"]], lsuffix="_a",
                                        rsuffix="_b", how="inner")
    j = j[(j["n_trav_a"] >= HALF_MIN_TRAV) & (j["n_trav_b"] >= HALF_MIN_TRAV)]
    expo = np.minimum(j["n_trav_a"], j["n_trav_b"]).to_numpy()
    strat = pd.qcut(pd.Series(expo).rank(method="first"), STRATA, labels=False).to_numpy()
    # both directions: does ABS in one half predict ABS in the other?
    ev = np.r_[j["abs_rides_b"].to_numpy() >= 1, j["abs_rides_a"].to_numpy() >= 1]
    ex = np.r_[j["abs_rides_a"].to_numpy() >= 1, j["abs_rides_b"].to_numpy() >= 1]
    st = np.r_[strat, strat]
    n = len(j)
    rr = _mh_ratio(ev, ex, st)
    bs = []
    for _ in range(N_BOOT):
        i = rng.integers(0, n, n)
        ii = np.r_[i, i + n]
        bs.append(_mh_ratio(ev[ii], ex[ii], st[ii]))
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    out = {"grid": PRIMARY, "n_cells": int(n), "cells_abs_in_both_halves": int(((j["abs_rides_a"] >= 1)
                                                                               & (j["abs_rides_b"] >= 1)).sum()),
           "cells_abs_in_one_half": int(((j["abs_rides_a"] >= 1) ^ (j["abs_rides_b"] >= 1)).sum()),
           "mh_risk_ratio": r3(rr), "ci": [r3(lo), r3(hi)]}
    out["verdict"] = "REPEATABLE" if rr >= HAZARD_LIFT and lo > 1.0 else "NOT-REPEATABLE"
    return out


def t_surprise(L, rng) -> dict:
    d = L[SURPRISE_GRID]
    E = pd.read_parquet(OUT / f"graph_edges{SURPRISE_GRID}.parquet",
                        columns=["ci", "cj", "surprise", "radius_j"])
    E["ci"] = E["ci"].astype(str)
    E["cj"] = E["cj"].astype(str)
    X = pd.read_parquet(OUT / f"crowd_transitions{SURPRISE_GRID}.parquet")
    X["ci"] = X["ci"].astype(str)
    X["cj"] = X["cj"].astype(str)
    J = X.merge(E, on=["ci", "cj"], how="inner")
    J = J[(J["n"] >= SURPRISE_MIN_RIDES) & np.isfinite(J["surprise"]) & np.isfinite(J["radius_j"])]
    c = d["cells"]
    town = J["cj"].isin(d["residential"]) | (c["stop_rate"].reindex(J["cj"]).to_numpy() >= 0.25)
    J = J[~np.asarray(town)]
    tight = (J["surprise"] >= R.SURPRISE_MIN).to_numpy()
    ctrl = (J["surprise"].abs() <= SURPRISE_CONTROL).to_numpy()
    J = J[tight | ctrl]
    tight = (J["surprise"] >= R.SURPRISE_MIN).to_numpy()
    strat = pd.qcut(J["radius_j"].rank(method="first"), STRATA, labels=False).to_numpy()

    # MH over edges, each carrying rides and braking rides: expand weights, not rows
    nb = J["n_brake"].to_numpy(dtype=float)
    nn = J["n"].to_numpy(dtype=float)

    def mh(idx):
        num = den = 0.0
        for s in np.unique(strat[idx]):
            m = idx[strat[idx] == s]
            t, k = m[tight[m]], m[~tight[m]]
            n1, n0 = nn[t].sum(), nn[k].sum()
            if n1 == 0 or n0 == 0:
                continue
            N = n1 + n0
            num += nb[t].sum() * n0 / N
            den += nb[k].sum() * n1 / N
        return num / den if den > 0 else float("nan")

    allidx = np.arange(len(J))
    rr = mh(allidx)
    bs = [mh(rng.integers(0, len(J), len(J))) for _ in range(N_BOOT)]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    crude_t = nb[tight].sum() / max(nn[tight].sum(), 1)
    crude_c = nb[~tight].sum() / max(nn[~tight].sum(), 1)
    out = {"grid": SURPRISE_GRID, "n_edges_tightening": int(tight.sum()),
           "n_edges_stable": int((~tight).sum()),
           "brake_share_tightening": r3(crude_t), "brake_share_stable": r3(crude_c),
           "crude_ratio": r3(crude_t / crude_c) if crude_c > 0 else None,
           "radius_stratified_ratio": r3(rr), "ci": [r3(lo), r3(hi)]}
    out["verdict"] = "PASS" if rr >= SURPRISE_LIFT and lo > 1.0 else "FAIL"
    return out


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    L = {tag: load(tag) for tag in ("_c16", "_s2")}
    res = {"preregistered": {k: (v if not isinstance(v, float) else round(v, 4))
                             for k, v in globals().items()
                             if k.isupper() and isinstance(v, (int, float, str))}}
    for name, fn in (("dwell", t_dwell), ("reversals", t_reversals), ("rhythm", t_rhythm),
                     ("adventure", t_adventure), ("viewpoints", t_viewpoints),
                     ("traffic", t_traffic), ("hazard", t_hazard), ("surprise", t_surprise)):
        t1 = time.time()
        res[name] = fn(L, rng)
        print(f"{name:<11s} {res[name]['verdict']:<24s} ({time.time()-t1:4.1f} s)")
    p = OUT / "road_character_test.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "preregistered"}, indent=1))
    print(f"\nwrote {p}  in {time.time()-t0:.1f} s")
