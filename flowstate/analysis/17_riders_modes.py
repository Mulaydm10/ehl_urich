"""
17_riders_modes.py — who is riding, and what kind of ride?   (Phase 3, doc 22)

Every claim FEATURES.md makes about riders and modes, tested on the real rides
before anything is offered by the app:

  morton      is the lake's morton_code computable from a position? (user C's
              corners have a position and no cell)
  columns     do the columns the modes lean on replicate across disjoint rides?
              elevation, prominence and rhythm purity were never split-half tested
  userC       the second human, calibrated on the crowd's ruler; robust to the
              corner recipe; does switching rider move the preset roads?
  bike_dna    do user A's bikes declare an archetype through their telemetry?
  modes       per mode, across the 25-75 km O-D scan: does the road change, and
              does the mode's own column move the intended way where it does?
  bike_mode   does a bike's archetype predict the roads it is ridden on?
  mood        does the first ten minutes (rpm per km/h) predict the rest of the ride?
  rhythm      does a rider have a lean wavelength of their own?

Every threshold below was fixed before this script first ran. None was tuned
on its result. Output is aggregates only — no trip ids, no ride coordinates:
analysis/out/riders_modes_test.json. Nothing leaves this machine.

Run (after 10_crowd_layer.py for _c16, 16_road_character.py, 09_userC_asymmetry.py):
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    $V analysis/17_riders_modes.py
"""

from __future__ import annotations

import glob
import importlib.util
import itertools
import json
import os
import sys
import time
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import binomtest, rankdata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import flowstate as F       # noqa: E402
import modes as M           # noqa: E402
import router as R          # noqa: E402
import service as S         # noqa: E402

OUT = R.OUT
LAKE = ROOT / "data" / "raw" / "salvaged" / "anonymizedDataLake" / "trips-samples-2"
C_DIR = ROOT / "data" / "raw" / "salvaged" / "exampleUserC" / "recordedTrips"

# ------------------------------------------------------------------------------
# PRE-REGISTERED. Fixed before the first run.
# ------------------------------------------------------------------------------
MORTON_FILES_LAKE = 20
MORTON_FILES_RIDER = 10
HALF_MIN_TRAV = 10               # split-half: >= 10 traversals in EACH half (doc 21)
RHY_HALF_MIN_RIDES = 5
RELIABLE_RHO = 0.50
MIN_SHARED_CELLS = 50            # calibrate_rider's own floor
RECIPE_SHIFT_SIGMA = 0.50        # skill from corner cells vs every touched cell: < 0.5 sigma
BEAT_PAIR = "kochel_tegernsee"
ROAD_MOVES_SHARED = 0.50         # user A vs user C at Send it: at most half the road shared
BIKE_MIN_RIDES = 3
K_ARCHETYPES = 3                 # FEATURES.md names three
SILHOUETTE_BAR = 0.50
ARI_BAR = 0.70                   # median adjusted Rand index over ride bootstraps
N_BOOT_BIKE = 1000
N_PERM = 5000
BIKE_P = 0.01                    # "the bike declares itself": between-bike share of variance
SCAN_DIAL = 0.50                 # modes compared at the Flow preset, user A, service config
CHANGED_OVERLAP = 0.90           # a pair's road changed if Jaccard(mode, flow) <= 0.90
MIN_CHANGED_SHARE = 0.10
MIN_CHANGED_PAIRS = 10
SIGN_SHARE = 0.70                # target column moves the intended way on >= 70% of changed pairs
SIGN_P = 0.01                    # one-sided binomial sign test
BIKE_MODE_P = 0.05
BIKE_MODE_MIN_CELLS = 20         # a ride must touch >= 20 routing cells to say what roads it chose
MOOD_MIN_RIDE_S = 1200.0         # ten minutes to read, ten minutes to predict
MOOD_BIKE_MIN_RIDES = 3
MOOD_RHO = 0.30
RIDER_MIN_WINDOWS = 10           # rhythmic windows per ride
CROWD_RHY_MIN_RIDES = 10         # crowd wavelength trusted for a residual
PROV_RIDE_SHARE = 0.50           # provenance (added after run 1, no random draws): ride inside lake
N_BOOT = 2000
SEED = 7

_TP = ["trip_id", "timestampinmillis", "ridingvehiclespeed", "sensorsbankingangle",
       "ridingenginespeed", "morton_code"]


# ------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------

def r3(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 3)


def _load(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "analysis" / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def spearman(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 5:
        return float("nan")
    return float(np.corrcoef(rankdata(x[m]), rankdata(y[m]))[0, 1])


def boot(stat, n: int, rng, n_boot: int = N_BOOT) -> tuple[float, float]:
    """Percentile CI of stat(idx) over resampled row indices."""
    bs = [stat(rng.integers(0, n, n)) for _ in range(n_boot)]
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return float(lo), float(hi)


def spearman_ci(x, y, rng) -> dict:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 10:
        return {"rho": None, "ci": [None, None], "n": int(len(x))}
    lo, hi = boot(lambda i: spearman(x[i], y[i]), len(x), rng)
    return {"rho": r3(spearman(x, y)), "ci": [r3(lo), r3(hi)], "n": int(len(x))}


def split_half(H: pd.DataFrame, col: str, need_col: str, need: float, rng) -> dict:
    a = H[H["half"] == 0].set_index("morton_code")
    b = H[H["half"] == 1].set_index("morton_code")
    j = a[[col, need_col]].join(b[[col, need_col]], lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j[need_col + "_a"] >= need) & (j[need_col + "_b"] >= need)]
    out = spearman_ci(j[col + "_a"], j[col + "_b"], rng)
    out["verdict"] = "RELIABLE" if (out["rho"] or 0) >= RELIABLE_RHO else "UNRELIABLE"
    return out


def rider_files(d: Path) -> list[str]:
    return sorted(p for p in glob.glob(str(d / "*.csv"))
                  if not os.path.basename(p).startswith(("._", "cloudRecordedTracks")))


def load_user_c() -> pd.DataFrame:
    parts = []
    for f in rider_files(C_DIR):
        d = pd.read_csv(f, usecols=lambda c: c in _TP, dtype={"morton_code": str}, low_memory=False)
        d["trip_id"] = Path(f).stem
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_user_a() -> pd.DataFrame:
    tp = pd.read_parquet(F.TRACKPOINTS, columns=_TP)
    tp["trip_id"] = tp["trip_id"].astype(str)
    tp["morton_code"] = tp["morton_code"].astype(str)
    return tp


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / max(len(a | b), 1)


# ------------------------------------------------------------------------------
# 1. morton
# ------------------------------------------------------------------------------

def t_morton(rng) -> dict:
    cols = ["positionmapmatchedlatitude", "positionmapmatchedlongitude", "morton_code"]
    lake = sorted(p for p in glob.glob(str(LAKE / "*" / "*.csv"))
                  if not os.path.basename(p).startswith("._"))
    srcs = {"crowd_lake": list(rng.choice(lake, MORTON_FILES_LAKE, replace=False)),
            "userA": list(rng.choice(rider_files(F.RAW_TRIPS), MORTON_FILES_RIDER, replace=False)),
            "userC": list(rng.choice(rider_files(C_DIR), MORTON_FILES_RIDER, replace=False))}
    out = {}
    for name, files in srcs.items():
        n = hit = 0
        for f in files:
            d = pd.read_csv(f, usecols=cols, dtype={"morton_code": str}).dropna()
            if not len(d):
                continue
            e = R.morton_encode(d[cols[0]].to_numpy(), d[cols[1]].to_numpy())
            n += len(d)
            hit += int((e == d["morton_code"].to_numpy(dtype=object)).sum())
        out[name] = {"files": len(files), "samples": n, "exact_32_digits": r3(hit / max(n, 1))}
    out["verdict"] = ("EXACT" if all(v["exact_32_digits"] == 1.0 for v in out.values())
                      else "INEXACT")
    return out


# ------------------------------------------------------------------------------
# 2. the columns modes lean on
# ------------------------------------------------------------------------------

def prominence(lat, lon, elev, lat_ref: float) -> np.ndarray:
    """10_crowd_layer.py's rule: elev minus the median of the nearest 200 cells inside 3 km."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    ev = np.asarray(elev, dtype=float)
    ok = np.isfinite(ev)
    kx = 111320.0 * np.cos(np.radians(lat_ref))
    xy = np.c_[lat * 110540.0, lon * kx]
    prom = np.full(len(ev), np.nan)
    if ok.sum() > 1:
        tree = cKDTree(xy[ok])
        kq = int(min(CROWD.PROMINENCE_K, ok.sum()))
        dist, nb = tree.query(xy[ok], k=kq, distance_upper_bound=CROWD.PROMINENCE_R_M)
        evs = np.append(ev[ok], np.nan)
        prom[ok] = ev[ok] - np.nanmedian(evs[np.where(np.isfinite(dist), nb, ok.sum())], axis=1)
    return prom


def t_columns(cells: pd.DataFrame, H: pd.DataFrame, rng) -> dict:
    c = cells.set_index("morton_code")
    lat_ref = float(c["lat"].mean())
    re = prominence(c["lat"], c["lon"], c["elev_mean"], lat_ref)
    out = {"elev_prominence_reproduces_grid_max_abs_m":
           r3(float(np.nanmax(np.abs(re - c["elev_prominence_m"].to_numpy(dtype=float)))))}
    out["elev_mean"] = split_half(H, "elev_mean", "n_trav", HALF_MIN_TRAV, rng)
    halves = []
    for h in (0, 1):
        hh = H[H["half"] == h].set_index("morton_code").reindex(c.index)
        halves.append(pd.DataFrame({
            "morton_code": c.index, "half": h, "n_trav": hh["n_trav"].to_numpy(dtype=float),
            "elev_prominence_m": prominence(c["lat"], c["lon"], hh["elev_mean"], lat_ref)}))
    out["elev_prominence_m"] = split_half(pd.concat(halves, ignore_index=True),
                                          "elev_prominence_m", "n_trav", HALF_MIN_TRAV, rng)
    out["rhythm_purity"] = split_half(H, "rhythm_purity", "rhythm_rides", RHY_HALF_MIN_RIDES, rng)
    out["rhythm_purity"]["rho_vs_wavelength"] = r3(spearman(c["rhythm_purity"],
                                                            c["rhythm_wavelength_m"]))
    # a copy: a column cannot be both the value and the filter in split_half's join
    out["n_rides"] = split_half(H.assign(popularity=H["n_trav"]), "popularity", "n_trav",
                                HALF_MIN_TRAV, rng)
    rc = json.loads((OUT / "road_character_test.json").read_text())
    out["reversals_km"] = {"verdict": rc["reversals"]["verdict"], "source": "doc 21"}
    out["stop_rate"] = {"verdict": "NOT-TESTED", "source": "used only by urban (Phase 4)"}
    return out


# ------------------------------------------------------------------------------
# 3. user C
# ------------------------------------------------------------------------------

def _skill_ci(groups: list[np.ndarray], demand: pd.Series, rng) -> tuple[float, float]:
    def stat(i):
        u = np.unique(np.concatenate([groups[k] for k in i]))
        return float(np.median(demand.reindex(u).dropna()))
    return boot(stat, len(groups), rng)


def t_user_c(A_tp: pd.DataFrame, C_tp: pd.DataFrame, rng) -> dict:
    s = S._need()
    cells = s["cells"]
    dem = cells.set_index("morton_code")["demand_p90"].dropna()
    rA, rC = s["riders"]["userA"]["rider"], s["riders"]["userC"]["rider"]
    cc = pd.read_parquet(OUT / "userC_corners.parquet")
    lo_la, hi_la, lo_lo, hi_lo = R.COVERAGE
    box = cc["lat"].between(lo_la, hi_la) & cc["lon"].between(lo_lo, hi_lo)
    c16 = pd.Series(R.morton_encode(cc["lat"].to_numpy(), cc["lon"].to_numpy(), 16), index=cc.index)
    ca = F.load_corners(True)

    out = {"corners": int(len(cc)), "corners_in_box": int(box.sum()),
           "rides_in_box": int(cc.loc[box, "ride"].nunique()),
           "recipe_note": "user C corners: 09_userC_asymmetry.py (block of >= 3 samples, "
                          "centroid position); user A corners: corners_filtered (5,253). "
                          "Different recipes."}
    for key, r in (("userA", rA), ("userC", rC)):
        out[key] = {"skill": r3(r.skill), "sigma": r3(r.sigma), "gate": r3(r.gate),
                    "n_cells": int(r.n_cells), "hardest_ridden": r3(r.hardest_ridden),
                    "gate_agreement": r3(r.gate_agreement), "calibrated": r.n_cells >= MIN_SHARED_CELLS}

    # recipe robustness: skill from corner cells vs every cell the trackpoints touch
    for key, tp, r in (("userA", A_tp, rA), ("userC", C_tp, rC)):
        touched = tp["morton_code"].dropna().astype(str).str.slice(0, 16).unique()
        d = dem.reindex(touched).dropna()
        sk = float(np.median(d))
        out[key]["skill_all_touched_cells"] = r3(sk)
        out[key]["touched_cells"] = int(len(d))
        out[key]["recipe_shift_sigma"] = r3(abs(sk - r.skill) / r.sigma)
    out["recipe"] = ("ROBUST" if max(out["userA"]["recipe_shift_sigma"],
                                     out["userC"]["recipe_shift_sigma"]) < RECIPE_SHIFT_SIGMA
                     else "RECIPE-SENSITIVE")

    ga = [ca.loc[ca["trip"] == t, "morton"].str.slice(0, 16).to_numpy() for t in ca["trip"].unique()]
    gc = [c16[cc["ride"] == t].to_numpy() for t in cc["ride"].unique()]
    loA, hiA = _skill_ci(ga, dem, rng)
    loC, hiC = _skill_ci(gc, dem, rng)
    out["skill_ci_by_ride"] = {"userA": [r3(loA), r3(hiA)], "userC": [r3(loC), r3(hiC)]}
    out["skills_differ"] = bool(hiC < loA or hiA < loC)

    pres = {}
    for p in S.PRESET_ROUTES:
        row = {}
        for name, z in (("cruise", 0.15), ("send_it", 0.90)):
            a = S.route(p["a"], p["b"], "userA", z)
            c = S.route(p["a"], p["b"], "userC", z)
            row[name] = {"ok": bool(a["ok"] and c["ok"]),
                         "note_C": c.get("note") or None,
                         "shared_A_C": r3(jaccard(a.get("cells", []), c.get("cells", []))),
                         "km_A": r3(a["summary"].get("km", np.nan)),
                         "km_C": r3(c["summary"].get("km", np.nan)),
                         "mean_demand_A": r3(a["summary"].get("mean_demand", np.nan)),
                         "mean_demand_C": r3(c["summary"].get("mean_demand", np.nan)),
                         "refusals_A": len(a["refusals"]), "refusals_C": len(c["refusals"])}
            if p["key"] == BEAT_PAIR and name == "send_it":
                b = S.route(p["a"], p["b"], "bike_4e1a9d64", z)
                row[name]["shared_A_bike_4e1a9d64"] = r3(jaccard(a["cells"], b["cells"]))
        pres[p["key"]] = row
    lp = S.loop((47.66, 11.35), 2.0, "userC", 0.9)
    pres["kochel_loop_2h_send_it_userC"] = {
        "ok": bool(lp["ok"]), "km": r3(lp["summary"].get("km", np.nan)),
        "minutes": r3(lp["summary"].get("minutes", np.nan)),
        "distinct_share": r3(lp["summary"].get("distinct_share", np.nan))}
    out["presets"] = pres
    shared = pres[BEAT_PAIR]["send_it"]["shared_A_C"]
    out["beat3"] = ("ROAD-MOVES" if shared is not None and shared <= ROAD_MOVES_SHARED
                    else "ROAD-STAYS")
    out["verdict"] = "CALIBRATED" if out["userC"]["calibrated"] else "UNCALIBRATED"
    return out


# ------------------------------------------------------------------------------
# 4. bike DNA
# ------------------------------------------------------------------------------

def _labelings(n: int, k: int) -> np.ndarray:
    L = np.array([(0,) + t for t in itertools.product(range(k), repeat=n - 1)], dtype=np.int8)
    return L[np.array([len(set(row)) == k for row in L])]


def _best_partition(X: np.ndarray, L: np.ndarray, k: int) -> np.ndarray:
    tot = np.zeros(len(L))
    q = (X ** 2).sum(axis=1)
    for c in range(k):
        Mk = (L == c).astype(float)
        cnt = Mk.sum(axis=1)
        sm = Mk @ X
        tot += Mk @ q - (sm ** 2).sum(axis=1) / np.maximum(cnt, 1.0)
    return L[int(np.argmin(tot))]


def _silhouette(X: np.ndarray, lab: np.ndarray) -> float:
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(axis=2))
    s = []
    for i in range(len(X)):
        same = (lab == lab[i])
        same[i] = False
        if not same.any():
            s.append(0.0)
            continue
        a = D[i, same].mean()
        b = min(D[i, lab == c].mean() for c in set(lab) if c != lab[i])
        s.append((b - a) / max(a, b))
    return float(np.mean(s))


def _ari(a, b) -> float:
    ct = pd.crosstab(np.asarray(a), np.asarray(b)).to_numpy()
    sc = sum(comb(int(x), 2) for x in ct.ravel())
    sa = sum(comb(int(x), 2) for x in ct.sum(axis=1))
    sb = sum(comb(int(x), 2) for x in ct.sum(axis=0))
    n = comb(int(ct.sum()), 2)
    exp = sa * sb / n
    mx = (sa + sb) / 2.0
    return 1.0 if mx == exp else float((sc - exp) / (mx - exp))


def _eta2(v: np.ndarray, g: np.ndarray) -> float:
    grand = v.mean()
    ssb = sum(len(v[g == k]) * (v[g == k].mean() - grand) ** 2 for k in np.unique(g))
    return float(ssb / ((v - grand) ** 2).sum())


FEATS = ["engineMaxRpm", "accelerationMax", "lean_max", "log_km"]


def t_bike_dna(rng) -> dict:
    m = F.load_manifest()
    for col in ("engineMaxRpm", "accelerationMax", "leanAngleLeftMax", "leanAngleRightMax",
                "rideDistance"):
        m[col] = pd.to_numeric(m[col], errors="coerce")
    m["lean_max"] = m[["leanAngleLeftMax", "leanAngleRightMax"]].max(axis=1)
    m["log_km"] = np.log1p(m["km_manifest"])
    allb = m.groupby("bike").agg(n=("trip_id", "size"), rpm_max=("engineMaxRpm", "max"))
    ok = m["engineMaxRpm"].notna() & (m["rideDistance"] > 0) & (m["lean_max"] > 0)
    r = m[ok]
    cnt = r["bike"].value_counts()
    elig = sorted(cnt[cnt >= BIKE_MIN_RIDES].index)
    r = r[r["bike"].isin(elig)].reset_index(drop=True)

    out = {"rides": int(len(m)), "bikes": int(m["bike"].nunique()),
           "rides_usable": int(ok.sum()), "bikes_eligible": len(elig),
           "rides_eligible": int(len(r)),
           "per_bike_max_rpm_range": [r3(allb["rpm_max"].min()), r3(allb["rpm_max"].max())],
           "rho_bike_max_rpm_vs_n_rides": r3(spearman(allb["rpm_max"], allb["n"])),
           "note": "FEATURES.md's 7,210-11,745 are two single bikes' maxima; a per-bike MAX grows "
                   "with the number of rides, so bikes are summarised by medians"}
    g = r["bike"].to_numpy()
    declares = {}
    for f in FEATS:
        v = r[f].to_numpy(dtype=float)
        e = _eta2(v, g)
        perm = np.array([_eta2(v, rng.permutation(g)) for _ in range(N_PERM)])
        declares[f] = {"eta2": r3(e), "p": r3((1 + (perm >= e).sum()) / (1 + N_PERM))}
    out["between_bike_share"] = declares
    out["bike_declares_itself_rpm"] = bool(declares["engineMaxRpm"]["p"] < BIKE_P)

    med = r.groupby("bike")[FEATS].median().loc[elig]
    X = ((med - med.mean()) / med.std(ddof=0)).to_numpy(dtype=float)
    L = _labelings(len(elig), K_ARCHETYPES)
    lab = _best_partition(X, L, K_ARCHETYPES)
    sil = _silhouette(X, lab)
    L2 = _labelings(len(elig), 2)
    sil2 = _silhouette(X, _best_partition(X, L2, 2))
    by_bike = {b: r.loc[r["bike"] == b].reset_index(drop=True) for b in elig}
    aris = []
    for _ in range(N_BOOT_BIKE):
        mb = pd.DataFrame([by_bike[b].iloc[rng.integers(0, len(by_bike[b]), len(by_bike[b]))][FEATS]
                           .median() for b in elig])
        Xb = ((mb - mb.mean()) / mb.std(ddof=0).replace(0, 1)).to_numpy(dtype=float)
        aris.append(_ari(lab, _best_partition(Xb, L, K_ARCHETYPES)))
    out["silhouette_k3"] = r3(sil)
    out["silhouette_k2_info"] = r3(sil2)
    out["bootstrap_ari_median"] = r3(float(np.median(aris)))
    cz = pd.DataFrame(X, columns=FEATS).groupby(lab).mean()
    out["centroids_z"] = {f"cluster_{k}": {f: r3(cz.loc[k, f]) for f in FEATS} for k in cz.index}
    out["cluster_sizes"] = {f"cluster_{k}": int((lab == k).sum()) for k in cz.index}
    structure = sil >= SILHOUETTE_BAR and float(np.median(aris)) >= ARI_BAR
    out["verdict"] = "ARCHETYPES" if structure else "NO-STRUCTURE"
    out["bikes"] = {}
    if structure:
        sport = int(cz["engineMaxRpm"].idxmax())
        rest = [k for k in cz.index if k != sport]
        tour = int(min(rest, key=lambda k: cz.loc[k, "lean_max"]))
        names = {sport: "sport", tour: "tour"}
        names.update({k: "adventure" for k in rest if k != tour})
        out["bikes"] = {b: names[int(k)] for b, k in zip(elig, lab)}
        out["naming_note"] = "names are an interpretation of centroids, not a lookup of the model"
    out["userC"] = "default (no manifest, no bike id)"
    return out


# ------------------------------------------------------------------------------
# 5. modes
# ------------------------------------------------------------------------------

def t_modes(cols: dict) -> tuple[dict, pd.DataFrame]:
    s = S._need()
    cells, edges, osm = s["cells"], s["edges"], s["osm"]
    rider = s["riders"]["userA"]["rider"]
    ci = cells.set_index("morton_code")

    graphs = {m: R.build_graph(edges, cells, rider, SCAN_DIAL, osm=osm, mode=m) for m in M.MODES}
    base = graphs["flow"]
    plain = R.build_graph(edges, cells, rider, SCAN_DIAL, osm=osm)
    out = {"flow_identical_to_no_mode": bool(
        plain.scored.equals(base.scored)
        and np.array_equal(plain.matrix.data, base.matrix.data)
        and np.array_equal(plain.matrix.indices, base.matrix.indices))}
    ref0 = set(zip(base.refused["ci"], base.refused["cj"]))
    inv = {}
    for m, g in graphs.items():
        inv[m] = bool(g.scored["gated"].equals(base.scored["gated"])
                      and g.scored["z"].equals(base.scored["z"])
                      and g.scored["reason"].equals(base.scored["reason"])
                      and set(zip(g.refused["ci"], g.refused["cj"])) == ref0
                      and g.scored["flow"].equals(base.scored["flow"]))
    out["gate_and_refusals_mode_invariant"] = inv
    if not (out["flow_identical_to_no_mode"] and all(inv.values())):
        raise AssertionError(f"mode leaked into flow or the gate: {out}")

    anchors = [(round(float(la), 3), round(float(lo), 3))
               for la in np.arange(47.45, 48.01, 0.14)
               for lo in np.arange(10.80, 11.95, 0.19)]
    rows = []
    for A, B in itertools.combinations(anchors, 2):
        if not 25 < 111 * np.hypot(B[0] - A[0], (B[1] - A[1]) * 0.67) < 75:
            continue
        rF = R.route_a_to_b(A, B, rider, SCAN_DIAL, graph=base, cells=cells, edges=edges, osm=osm)
        if not rF.ok or rF.note:
            continue
        for m in M.MODES:
            if m == "flow":
                continue
            g = graphs[m]
            rM = R.route_a_to_b(A, B, rider, SCAN_DIAL, graph=g, cells=cells, edges=edges,
                                osm=osm, mode=m)
            if not rM.ok or rM.note:
                continue
            col, _ = M.MODE_TARGET[m]
            pen = g.scored["mode_penalty"]
            rows.append({"pair": f"{A}-{B}", "mode": m,
                         "overlap": jaccard(rF.cells, rM.cells),
                         "km_ratio": rM.km / max(rF.km, 1e-9),
                         "demand_gain": rM.summary["mean_demand"] - rF.summary["mean_demand"],
                         "target_F": float(ci[col].reindex(rF.cells).mean()),
                         "target_M": float(ci[col].reindex(rM.cells).mean()),
                         "pref_gain": float(pen.reindex(rF.cells).mean() - pen.reindex(rM.cells).mean()),
                         "flow_change": float(rM.summary["mean_flow"] - rF.summary["mean_flow"])})
    df = pd.DataFrame(rows)
    out["pairs"] = int(df["pair"].nunique()) if len(df) else 0
    out["dial"] = SCAN_DIAL
    for m in M.MODES:
        if m == "flow":
            continue
        d = df[df["mode"] == m]
        col, sign = M.MODE_TARGET[m]
        ch = d[d["overlap"] <= CHANGED_OVERLAP]
        diff = sign * (ch["target_M"] - ch["target_F"])
        nz = diff[diff != 0]
        k, n = int((nz > 0).sum()), int(len(nz))
        p = float(binomtest(k, n, 0.5, alternative="greater").pvalue) if n else float("nan")
        bad = [c for c in M.MODES[m] if (cols.get(c) or {}).get("verdict") == "UNRELIABLE"]
        res = {"target": col, "direction": "+" if sign > 0 else "-", "pairs": int(len(d)),
               "share_changed": r3(len(ch) / max(len(d), 1)), "changed_pairs": int(len(ch)),
               "share_target_moved_right_way": r3(k / n) if n else None, "sign_test_p": r3(p),
               "median_target_change_on_changed": r3(float(np.median(diff))) if len(ch) else None,
               "km_ratio_median": r3(d["km_ratio"].median()), "km_ratio_max": r3(d["km_ratio"].max()),
               "demand_gain_median": r3(d["demand_gain"].median()),
               "pref_gain_median_on_changed": r3(ch["pref_gain"].median()) if len(ch) else None,
               "mean_flow_change_median_on_changed": r3(ch["flow_change"].median()) if len(ch) else None,
               "unreliable_columns": bad, "phase4": m in M.PHASE4_MODES}
        if bad:
            v = "COLUMN-UNRELIABLE"
        elif (len(ch) / max(len(d), 1)) < MIN_CHANGED_SHARE:
            v = "NO-EFFECT"
        elif len(ch) < MIN_CHANGED_PAIRS:
            v = "INSUFFICIENT-PAIRS"
        elif n and k / n >= SIGN_SHARE and p < SIGN_P:
            v = "PASS"
        else:
            v = "FAIL"
        res["verdict"] = v
        out[m] = res
    return out, df


# ------------------------------------------------------------------------------
# 6. bike -> mode
# ------------------------------------------------------------------------------

def t_bike_mode(dna: dict, modes_res: dict, A_tp: pd.DataFrame, rng) -> dict:
    if dna["verdict"] != "ARCHETYPES":
        return {"verdict": "DEFAULT-ONLY",
                "why": f"bike DNA verdict {dna['verdict']}: there are no archetypes to map"}
    ci = S._need()["cells"].set_index("morton_code")
    trip_bike = dict(zip(F.load_manifest()["trip_id"].astype(str), F.load_manifest()["bike"]))
    rows = []
    for tid, g in A_tp.groupby("trip_id", sort=False):
        b = trip_bike.get(str(tid))
        if b not in dna["bikes"]:
            continue
        u = pd.Index(g["morton_code"].astype(str).str.slice(0, 16).unique())
        u = u[u.isin(ci.index)]
        if len(u) < BIKE_MODE_MIN_CELLS:
            continue
        rows.append({"bike": b, **{m: float(ci.loc[u, M.MODE_TARGET[m][0]].mean())
                                    for m in M.MODE_TARGET}})
    d = pd.DataFrame(rows)
    out = {"rides_in_box": int(len(d)), "bikes": int(d["bike"].nunique()) if len(d) else 0}
    if not len(d):
        out["verdict"] = "DEFAULT-ONLY"
        return out
    bm = d.groupby("bike").mean(numeric_only=True)
    lab = np.array([dna["bikes"][b] for b in bm.index])
    tested, passed = 0, 0
    for arche, mode in M.ARCHETYPE_MODE.items():
        if mode == "flow":
            out[arche] = {"mode": mode, "tested": False, "why": "flow is everyone's default"}
            continue
        if (modes_res.get(mode) or {}).get("verdict") != "PASS":
            out[arche] = {"mode": mode, "tested": False,
                          "why": f"mode {mode} verdict {(modes_res.get(mode) or {}).get('verdict')}"}
            continue
        if (lab == arche).sum() < 2 or (lab != arche).sum() < 2:
            out[arche] = {"mode": mode, "tested": False, "why": "fewer than 2 bikes on a side"}
            continue
        sign = M.MODE_TARGET[mode][1]
        v = sign * bm[mode].to_numpy(dtype=float)
        stat = v[lab == arche].mean() - v[lab != arche].mean()
        perm = []
        for _ in range(N_PERM):
            pl = rng.permutation(lab)
            perm.append(v[pl == arche].mean() - v[pl != arche].mean())
        p = float((1 + (np.array(perm) >= stat).sum()) / (1 + N_PERM))
        tested += 1
        passed += int(p < BIKE_MODE_P)
        out[arche] = {"mode": mode, "tested": True, "stat": r3(stat), "p": r3(p)}
    out["verdict"] = ("DEFAULT-ONLY" if tested == 0 else "PASS" if passed == tested else "FAIL")
    return out


# ------------------------------------------------------------------------------
# 7. mood
# ------------------------------------------------------------------------------

def _mood_rows(tp: pd.DataFrame, bike_of: dict | None) -> pd.DataFrame:
    rows = []
    for tid, g in tp.groupby("trip_id", sort=False):
        if len(g) < 60:
            continue
        f = M.mood_frame(g)
        if f["t_s"].max() < MOOD_MIN_RIDE_S:
            continue
        sf = M.mood_signal(f[f["t_s"] <= M.MOOD_WINDOW_S])
        sr = M.mood_signal(f[f["t_s"] > M.MOOD_WINDOW_S])
        if sf["n"] < M.MOOD_MIN_SAMPLES or sr["n"] < M.MOOD_MIN_SAMPLES:
            continue
        sw = M.mood_signal(f)
        rows.append({"bike": (bike_of or {}).get(str(tid), "single"), "s_raw": sf["rpm_per_kmh"],
                     "s": np.log(sf["rpm_per_kmh"]), "b": sf["lean_p90"], "o": sr["lean_p90"],
                     "w_s": sw["rpm_per_kmh"], "w_lean50": sw["lean_p50"]})
    return pd.DataFrame(rows)


def _partial_rank(x, y, z) -> float:
    rx, ry, rz = rankdata(x), rankdata(y), rankdata(z)
    A = np.c_[rz, np.ones_like(rz)]
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    return float(np.corrcoef(ex, ey)[0, 1])


def _kappa3(x, y) -> float:
    tx = pd.qcut(rankdata(x), 3, labels=False)
    ty = pd.qcut(rankdata(y), 3, labels=False)
    cm = pd.crosstab(tx, ty).reindex(index=range(3), columns=range(3), fill_value=0).to_numpy()
    n = cm.sum()
    po = np.trace(cm) / n
    pe = (cm.sum(axis=1) @ cm.sum(axis=0)) / n ** 2
    return float((po - pe) / (1 - pe))


def t_mood(A_tp: pd.DataFrame, C_tp: pd.DataFrame, rng) -> dict:
    man = F.load_manifest()
    bike_of = dict(zip(man["trip_id"].astype(str), man["bike"]))
    out = {"signal": "median rpm / (3.6 v) over moving samples (v > 5 m/s, rpm > 500), bus speed only",
           "outcome": "lean p90 over the moving rest of the ride (after minute 10)",
           "baseline": "lean p90 over the first ten minutes"}
    ok_all = True
    pred_all = True
    for person, tp, bikes in (("userA", A_tp, bike_of), ("userC", C_tp, None)):
        d = _mood_rows(tp, bikes)
        res = {"eligible_rides": int(len(d))}
        if len(d):
            res["replicate_features_claim_whole_ride"] = spearman_ci(d["w_s"], d["w_lean50"], rng)
        if person == "userA" and len(d):
            keep = d["bike"].value_counts()
            d = d[d["bike"].isin(keep[keep >= MOOD_BIKE_MIN_RIDES].index)].copy()
            for c in ("s", "b", "o"):
                d[c] = d[c] - d.groupby("bike")[c].transform("mean")
            res["within_bike_rides"] = int(len(d))
            res["bikes"] = int(d["bike"].nunique())
        if len(d) < 10:
            res["verdict_part"] = "INSUFFICIENT-DATA"
            ok_all = pred_all = False
            out[person] = res
            continue
        s, b, o = (d[c].to_numpy(dtype=float) for c in ("s", "b", "o"))
        res["predict_rest"] = spearman_ci(s, o, rng)
        lo, hi = boot(lambda i: _partial_rank(s[i], o[i], b[i]), len(s), rng)
        res["beyond_first10_lean"] = {"partial_rho": r3(_partial_rank(s, o, b)), "ci": [r3(lo), r3(hi)]}
        res["lean_alone_predicts_rest"] = spearman_ci(b, o, rng)
        res["kappa_terciles"] = r3(_kappa3(s, o))
        res["tercile_cuts"] = [r3(v) for v in np.percentile(d["s_raw"], [100 / 3, 200 / 3])]
        pr = res["predict_rest"]
        predictive = (pr["rho"] or 0) >= MOOD_RHO and (pr["ci"][0] or 0) > 0
        beyond = (res["beyond_first10_lean"]["ci"][0] or 0) > 0
        pred_all &= predictive
        ok_all &= predictive and beyond
        out[person] = res
    out["verdict"] = "PASS" if ok_all else "REDUNDANT-WITH-LEAN" if pred_all else "FAIL"
    return out


# ------------------------------------------------------------------------------
# 8. rhythm match
# ------------------------------------------------------------------------------

def _windows(files: list[str]) -> pd.DataFrame:
    parts, cmap = [], {}
    for i, f in enumerate(files):
        try:
            r = CROWD.process_ride(f, i, cmap)
        except Exception:
            r = None
        if r is not None and r[3] is not None and len(r[3]):
            parts.append(r[3])
    if not parts:
        return pd.DataFrame(columns=["cell", "wavelength", "purity", "ride", "morton_code"])
    W = pd.concat(parts, ignore_index=True)
    inv = {v: k for k, v in cmap.items()}
    W["morton_code"] = W["cell"].map(inv).astype(str)
    return W


def _ride_medians(W: pd.DataFrame, col: str) -> np.ndarray:
    g = W.groupby("ride")[col].agg(["median", "size"])
    return g.loc[g["size"] >= RIDER_MIN_WINDOWS, "median"].to_numpy(dtype=float)


def _diff_ci(a: np.ndarray, c: np.ndarray, rng) -> dict:
    if len(a) < 5 or len(c) < 5:
        return {"diff_C_minus_A": None, "ci": [None, None], "rides": [int(len(a)), int(len(c))]}
    bs = [np.median(c[rng.integers(0, len(c), len(c))]) - np.median(a[rng.integers(0, len(a), len(a))])
          for _ in range(N_BOOT)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"diff_C_minus_A": r3(float(np.median(c) - np.median(a))), "ci": [r3(lo), r3(hi)],
            "rides": [int(len(a)), int(len(c))]}


def _fingerprints(d: pd.DataFrame) -> np.ndarray:
    """
    One 64-bit key per sample: 32-digit cell (centimetres) + lean + rpm, exactly as
    recorded. Both sides are parsed by the same read_csv call, so equal samples hash equal.
    """
    d = d.dropna(subset=["morton_code"])[["morton_code", "sensorsbankingangle", "ridingenginespeed"]]
    return pd.util.hash_pandas_object(d, index=False).to_numpy(dtype=np.uint64)


def t_provenance() -> dict:
    """
    Added after the first run, when 16% of the riders' rhythm windows matched a crowd
    cell's median wavelength to the last float digit. Trip ids and file names do not
    overlap, but the lake is anonymised. Are these riders' own rides inside it anyway?
    No random draws: every other number in this file is unaffected by it.
    """
    use = ["morton_code", "sensorsbankingangle", "ridingenginespeed"]
    parts = []
    lake = sorted(p for p in glob.glob(str(LAKE / "*" / "*.csv"))
                  if not os.path.basename(p).startswith("._"))
    for p in lake:
        try:
            parts.append(_fingerprints(pd.read_csv(p, usecols=use, dtype={"morton_code": str})))
        except ValueError:
            continue
    keys = np.unique(np.concatenate(parts))                 # sorted
    out = {"lake_files": len(lake), "lake_sample_keys": int(len(keys)),
           "rule": f"a ride is inside the lake if >= {PROV_RIDE_SHARE:.0%} of its samples match"}
    for key, files in (("userA", rider_files(F.RAW_TRIPS)), ("userC", rider_files(C_DIR))):
        shares = []
        for p in files:
            try:
                fp = _fingerprints(pd.read_csv(p, usecols=use, dtype={"morton_code": str}))
            except ValueError:
                continue
            if len(fp):
                pos = np.clip(np.searchsorted(keys, fp), 0, len(keys) - 1)
                shares.append(float((keys[pos] == fp).mean()))
        sh = np.array(shares)
        out[key] = {"rides": int(len(sh)), "rides_inside_lake": int((sh >= PROV_RIDE_SHARE).sum()),
                    "median_sample_match": r3(float(np.median(sh))) if len(sh) else None,
                    "rides_any_match": int((sh > 0).sum())}
    inside = out["userA"]["rides_inside_lake"] + out["userC"]["rides_inside_lake"]
    out["verdict"] = "RIDES-IN-LAKE" if inside else "DISJOINT"
    return out


def t_rhythm(cells: pd.DataFrame, H: pd.DataFrame, rng, provenance: dict) -> dict:
    a = H[H["half"] == 0].set_index("morton_code")
    b = H[H["half"] == 1].set_index("morton_code")
    j = a[["rhythm_wavelength_m", "rhythm_rides"]].join(b[["rhythm_wavelength_m", "rhythm_rides"]],
                                                        lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j["rhythm_rides_a"] >= RHY_HALF_MIN_RIDES) & (j["rhythm_rides_b"] >= RHY_HALF_MIN_RIDES)]
    h = float(np.median(np.abs(j["rhythm_wavelength_m_a"] - j["rhythm_wavelength_m_b"])))

    WA = _windows(rider_files(F.RAW_TRIPS))
    WC = _windows(rider_files(C_DIR))
    ci = cells.set_index("morton_code")
    trusted = ci.loc[ci["rhythm_rides"] >= CROWD_RHY_MIN_RIDES, "rhythm_wavelength_m"]
    out = {"method": "10_crowd_layer.process_ride itself (10 m, 128-sample Hann, hop 16)",
           "h_m": r3(h), "h_source": f"median |split-half difference| of crowd cell wavelength, "
                                     f"{len(j)} cells", "h_cells": int(len(j))}
    for key, W in (("userA", WA), ("userC", WC)):
        W["resid"] = W["wavelength"].astype(float) - trusted.reindex(W["morton_code"]).to_numpy()
        out[key] = {"windows": int(len(W)), "rides": int(W["ride"].nunique()),
                    "wavelength_m": r3(M.rider_wavelength(W)),
                    "windows_on_trusted_crowd_cells": int(W["resid"].notna().sum())}
    raw = _diff_ci(_ride_medians(WA, "wavelength"), _ride_medians(WC, "wavelength"), rng)
    res = _diff_ci(_ride_medians(WA.dropna(subset=["resid"]), "resid"),
                   _ride_medians(WC.dropna(subset=["resid"]), "resid"), rng)
    out["raw_ride_medians"] = raw
    out["residual_vs_crowd_same_cell"] = res
    # resolution: the interpolated peak often clips at +-0.5 bin, so wavelength sits on a
    # small set of values and a window can equal its cell's median exactly
    both = pd.concat([WA, WC], ignore_index=True)
    top = both["wavelength"].round(3).value_counts(normalize=True)
    out["resolution"] = {"distinct_wavelengths": int(both["wavelength"].round(3).nunique()),
                         "share_on_10_most_common_values": r3(float(top.head(10).sum())),
                         "share_residual_exactly_zero": r3(float((both["resid"].dropna() == 0).mean())),
                         "share_crowd_split_half_identical": r3(float(
                             (j["rhythm_wavelength_m_a"] == j["rhythm_wavelength_m_b"]).mean()))}
    pa, pc = provenance.get("userA") or {}, provenance.get("userC") or {}
    out["note"] = (f"{pa.get('rides_inside_lake')} of user A's {pa.get('rides')} rides and "
                   f"{pc.get('rides_inside_lake')} of user C's {pc.get('rides')} are inside the crowd "
                   f"lake (provenance): too few to make the residual self-referential, and user C "
                   f"shows the same degenerate residual with none. The residual is limited by "
                   f"wavelength resolution and is uninformative either way")

    def excludes0(d):
        return d["ci"][0] is not None and (d["ci"][0] > 0 or d["ci"][1] < 0)
    raw_ok = excludes0(raw) and abs(raw["diff_C_minus_A"]) >= h
    if raw_ok and excludes0(res):
        v = "PERSONAL"
    elif raw_ok:
        v = "PERSONAL-ROAD-CHOICE"
    else:
        v = "NOT-PERSONAL"
    out["verdict"] = v
    return out


# ------------------------------------------------------------------------------

os.environ["FS_CELL_CHARS"] = "16"          # before loading: windows land on routing cells
CROWD = _load("crowd_layer", "10_crowd_layer.py")

if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    S.init(force_parquet=True)
    cells = S._need()["cells"]
    H = pd.read_parquet(OUT / "crowd_halves_c16.parquet")
    H["morton_code"] = H["morton_code"].astype(str)

    res = {"preregistered": {k: v for k, v in globals().items()
                             if k.isupper() and isinstance(v, (int, float, str)) and k not in ("OUT",)}}

    def step(name, fn):
        t1 = time.time()
        res[name] = fn()
        v = res[name]["verdict"] if isinstance(res[name], dict) and "verdict" in res[name] else "-"
        print(f"{name:<11s} {v:<24s} ({time.time() - t1:5.1f} s)", flush=True)

    step("morton", lambda: t_morton(rng))
    step("columns", lambda: t_columns(cells, H, rng))
    A_tp = load_user_a()
    C_tp = load_user_c()
    print(f"loaded user A {A_tp['trip_id'].nunique()} rides, user C {C_tp['trip_id'].nunique()} rides",
          flush=True)
    step("userC", lambda: t_user_c(A_tp, C_tp, rng))
    step("bike_dna", lambda: t_bike_dna(rng))
    t1 = time.time()
    res["modes"], scan = t_modes(res["columns"])
    print(f"modes       {res['modes']['pairs']} pairs ({time.time() - t1:5.1f} s)", flush=True)
    for m in M.MODES:
        if m != "flow":
            print(f"  {m:<10s} {res['modes'][m]['verdict']}", flush=True)
    step("bike_mode", lambda: t_bike_mode(res["bike_dna"], res["modes"], A_tp, rng))
    step("mood", lambda: t_mood(A_tp, C_tp, rng))
    step("provenance", t_provenance)
    step("rhythm_match", lambda: t_rhythm(cells, H, rng, res["provenance"]))

    p = OUT / "riders_modes_test.json"
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "preregistered"}, indent=1))
    print(f"\nwrote {p}  in {time.time() - t0:.1f} s")
