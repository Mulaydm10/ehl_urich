"""10 - BMW crowd-data layer for FLOWSTATE.

Streams every ride CSV in one anonymized-lake sample set, turns trackpoints into
corners with the CORRECTED recipe from 09_userC_asymmetry.py, and accumulates
per-morton-cell aggregates incrementally. Nothing leaves this machine (NDA).

MEASURED DATA RULES honoured here (see NOTES.md):
  * yaw from positionrawheading ONLY (map-matched is quantised to road bearings:
    38% of moving samples read exactly zero yaw vs 6% for raw)
  * ridingvehiclespeed (m/s) -> positionmapmatchedspeed -> GPS-derived, per ride,
    and the fallback actually used is counted and reported
  * sensorsbankingangle is degrees, signed, +ve = RIGHT, INVALID below 0.5 m/s
    (that is the side stand; a parked bike reads about -15 deg)
  * ridingabsbraking == 3 is the hard-braking / ABS event code (not 2)
  * positionrawelevation (map-matched elevation is flat on a third of rides)
  * required lean: theta = degrees(arctan(v * yaw_rate / 9.81))
  * morton_code is a 32-char base-4 string: read as TEXT, never as an int
  * lake timestamps are shifted per trip -> no weather join, no time-of-day

CELL = first 18 chars of morton_code = BMW quadkey level 18, ~153 x 102 m at lat 48.

DEFINITIONS (stated so the numbers are reproducible):
  demand_*      quantiles of |required lean| over trusted-cadence moving points
                (v > 5 m/s, dt in [0.8, 1.3] s, raw heading valid) -- so a mostly
                straight cell honestly scores low.
  crowd_lean_*  quantiles of |sensorsbankingangle| over points with v > 0.5 m/s.
  crowd_v_*     quantiles of speed over ALL points in the cell (stops included,
                so p50 sags where traffic really stops and p85 is the free-flow proxy).
  n_corners     distinct corner blocks (09 recipe: >=3 contiguous same-sign-yaw
                samples, |yaw| > 0.04 rad/s, peak required lean in [3, 55] deg)
                that put at least one point in the cell.
  radius_p50    median of v / |yaw| over corner points in the cell, clipped 5-2000 m.
  traversal     one (ride, cell) pair. A ride that re-enters a cell counts once.
  stop_rate     share of traversals containing a sample below 2 m/s.
  flow_index    share of traversals with NO sample below 2 m/s AND speed
                coefficient of variation <= 0.25 (single-sample traversals: CV waived).
  grade_mean    mean of 100 * d(elev) / d(distance) over 5-sample windows with
                >20 m of travel, clipped to +-25 percent.
"""
import argparse
import glob
import os
import time

import numpy as np
import pandas as pd

G = 9.81
LAKE = os.environ.get("FS_LAKE")
OUT = os.environ.get("FS_OUT")
CELL_CHARS = int(os.environ.get("FS_CELL_CHARS", 18))
BUDGET_S = 22 * 60          # wall-clock guard; over this we stop and SAY SO
STOP_V = 2.0                # m/s, "stopped"
CV_MAX = 0.25               # speed coefficient of variation for "flowing"

USE = ["timestampinmillis", "positionmapmatchedlatitude", "positionmapmatchedlongitude",
       "positionmapmatchedspeed", "positionrawelevation", "positionrawheading",
       "ridingabsbraking", "ridingvehiclespeed", "sensorsbankingangle",
       "trip_id", "morton_code"]


def safe_max(a):
    a = a[np.isfinite(a)]
    return a.max() if a.size else 0.0


def process_ride(path, ride_idx, cell_map):
    """Return (points DataFrame, traversal DataFrame, speed_source) or None."""
    d = pd.read_csv(path, usecols=USE, dtype={"morton_code": str, "trip_id": str},
                    low_memory=False)
    if len(d) < 10:
        return None
    d = d.sort_values("timestampinmillis")
    d = d[pd.notna(d.morton_code.to_numpy())]
    if len(d) < 10:
        return None

    n = len(d)
    ts = d.timestampinmillis.to_numpy(dtype=float)
    lat = d.positionmapmatchedlatitude.to_numpy(dtype=float)
    lon = d.positionmapmatchedlongitude.to_numpy(dtype=float)
    dt = np.diff(ts, prepend=np.nan) / 1000.0
    dt = np.where(dt > 0, dt, np.nan)

    # step distance (m): needed for grade and for the GPS speed fallback
    dlat = np.diff(lat, prepend=np.nan)
    dlon = np.diff(lon, prepend=np.nan)
    step = np.hypot(dlat * 111320.0,
                    dlon * 111320.0 * np.cos(np.radians(np.clip(lat, -89, 89))))

    # ---- speed, with the measured three-step fallback ----
    vv = d.ridingvehiclespeed.to_numpy(dtype=float)
    mm = d.positionmapmatchedspeed.to_numpy(dtype=float)
    if safe_max(vv) > 0:
        v, src = vv, "vehicle"
    elif safe_max(mm) > 0:
        v, src = mm, "mapmatched"
    else:
        v, src = np.clip(step / dt, 0, 70), "gps"
        if safe_max(v) <= 0:
            return None
    v = np.where(np.isfinite(v), v, np.nan)

    # ---- lean: side-stand guard ----
    lean = np.abs(d.sensorsbankingangle.to_numpy(dtype=float))
    lean = np.where(v > 0.5, lean, np.nan)

    # ---- yaw from RAW heading only ----
    hd = d.positionrawheading.to_numpy(dtype=float)
    hd = np.where(hd > 0, hd, np.nan)
    dh = ((np.diff(hd, prepend=np.nan) + 180.0) % 360.0) - 180.0
    yaw = np.radians(dh) / dt
    yaw = np.where(dt > 5, np.nan, yaw)

    # ---- required lean on trusted-cadence moving points ----
    good = (v > 5) & (dt >= 0.8) & (dt <= 1.3) & np.isfinite(yaw) & np.isfinite(lean)
    req = np.full(n, np.nan)
    req[good] = np.degrees(np.arctan(v[good] * yaw[good] / G))
    req = np.where(np.abs(req) < 60, req, np.nan)
    good = good & np.isfinite(req)

    # ---- corner blocks: exact 09_userC_asymmetry recipe, on the masked subsequence ----
    corner_id = np.full(n, -1, dtype=np.int64)
    radius = np.full(n, np.nan)
    idx = np.flatnonzero(good)
    if idx.size:
        sg = np.sign(yaw[idx])
        sg[np.abs(yaw[idx]) <= 0.04] = 0
        newb = np.empty(idx.size, dtype=bool)
        newb[0] = True
        newb[1:] = sg[1:] != sg[:-1]
        blk = np.cumsum(newb)
        ub, inv, cnt = np.unique(blk, return_inverse=True, return_counts=True)
        peak = np.zeros(ub.size)
        np.maximum.at(peak, inv, np.abs(req[idx]))
        bsgn = np.zeros(ub.size)
        bsgn[inv] = sg
        keep = (cnt >= 3) & (peak >= 3) & (peak <= 55) & (bsgn != 0)
        pm = keep[inv]
        if pm.any():
            ci = idx[pm]
            corner_id[ci] = ride_idx * 1000000 + blk[pm]
            ay = np.abs(yaw[ci])
            radius[ci] = np.where(ay > 0.01,
                                  np.clip(v[ci] / np.maximum(ay, 1e-9), 5, 2000), np.nan)

    # ---- elevation + grade ----
    elev = d.positionrawelevation.to_numpy(dtype=float)
    elev = np.where((elev != 0) & (elev > -100) & (elev < 4000), elev, np.nan)
    dist5 = pd.Series(step).rolling(5, min_periods=5).sum().to_numpy()
    de5 = elev - pd.Series(elev).shift(5).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        grade = np.where(dist5 > 20, 100.0 * de5 / dist5, np.nan)
    grade = np.where(np.abs(grade) <= 25, grade, np.nan)

    absf = (d.ridingabsbraking.to_numpy(dtype=float) == 3)

    # ---- cell codes ----
    cells = pd.Series(d.morton_code.to_numpy()).str[:CELL_CHARS].to_numpy()
    code = np.fromiter((cell_map.setdefault(s, len(cell_map)) for s in cells),
                       dtype=np.int64, count=n).astype(np.int32)

    P = pd.DataFrame({
        "cell": code,
        "v": v.astype(np.float32),
        "lean": lean.astype(np.float32),
        "req": np.abs(req).astype(np.float32),
        "radius": radius.astype(np.float32),
        "elev": elev.astype(np.float32),
        "grade": grade.astype(np.float32),
        "absf": absf,
        "corner": corner_id,
        "lat": lat.astype(np.float32),
        "lon": lon.astype(np.float32),
    })

    # ---- traversal records: one row per (ride, cell) ----
    vs = P.groupby("cell")["v"].agg(["min", "mean", "std"])
    vmin = vs["min"].to_numpy()
    cv = (vs["std"] / vs["mean"]).to_numpy()
    stop = np.isfinite(vmin) & (vmin < STOP_V)
    nostop = np.isfinite(vmin) & (vmin >= STOP_V)
    flow = nostop & ((cv <= CV_MAX) | ~np.isfinite(cv))
    T = pd.DataFrame({"cell": vs.index.to_numpy().astype(np.int32),
                      "stop": stop, "flow": flow})
    return P, T, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="trips-samples-2")
    ap.add_argument("--tag", default="")
    ap.add_argument("--limit", type=int, default=0, help="0 = all files")
    a = ap.parse_args()

    src_dir = os.path.join(LAKE, a.set)
    files = [p for p in glob.glob(os.path.join(src_dir, "*", "*.csv"))
             if not os.path.basename(p).startswith("._")]
    files.sort()
    print("=" * 78)
    print("CROWD LAYER  |  set=%s  |  %d ride files found" % (a.set, len(files)))
    sampled = False
    if a.limit and a.limit < len(files):
        rng = np.random.default_rng(0)
        files = [files[i] for i in sorted(rng.choice(len(files), a.limit, replace=False))]
        sampled = True
        print("*** RANDOM SAMPLE of %d rides (seed 0) ***" % len(files))
    print("=" * 78, flush=True)

    cell_map = {}
    pts, trv, chunks_p, chunks_t = [], [], [], []
    srcs = {"vehicle": 0, "mapmatched": 0, "gps": 0}
    n_ok = n_bad = n_skip = 0
    t0 = time.time()
    truncated = False

    for i, p in enumerate(files):
        try:
            r = process_ride(p, i, cell_map)
        except Exception:
            r = None
            n_bad += 1
        if r is None:
            n_skip += 1
        else:
            P, T, s = r
            pts.append(P)
            trv.append(T)
            srcs[s] += 1
            n_ok += 1
        if len(pts) >= 800:
            chunks_p.append(pd.concat(pts, ignore_index=True))
            chunks_t.append(pd.concat(trv, ignore_index=True))
            pts, trv = [], []
        if (i + 1) % 500 == 0:
            el = time.time() - t0
            print("  %5d/%d files | %5.1f s | %.1f files/s | %d usable | %s cells"
                  % (i + 1, len(files), el, (i + 1) / el, n_ok, f"{len(cell_map):,}"),
                  flush=True)
        if time.time() - t0 > BUDGET_S:
            truncated = True
            print("\n*** TIME BUDGET HIT after %d of %d files - stopping early ***"
                  % (i + 1, len(files)), flush=True)
            break

    if pts:
        chunks_p.append(pd.concat(pts, ignore_index=True))
        chunks_t.append(pd.concat(trv, ignore_index=True))
    P = pd.concat(chunks_p, ignore_index=True)
    T = pd.concat(chunks_t, ignore_index=True)
    del chunks_p, chunks_t
    print("\nparsed %d rides (%d skipped, %d threw) -> %s points, %s traversals, %s cells in %.1f s"
          % (n_ok, n_skip, n_bad, f"{len(P):,}", f"{len(T):,}", f"{len(cell_map):,}",
             time.time() - t0), flush=True)
    tot = max(n_ok, 1)
    print("SPEED SOURCE: vehicle %d (%.1f%%) | mapmatched %d (%.1f%%) | GPS-derived %d (%.1f%%)"
          % (srcs["vehicle"], 100 * srcs["vehicle"] / tot, srcs["mapmatched"],
             100 * srcs["mapmatched"] / tot, srcs["gps"], 100 * srcs["gps"] / tot), flush=True)

    # ---------------- per-cell aggregation ----------------
    print("\naggregating...", flush=True)
    g = P.groupby("cell", sort=True)
    grid = g.agg(n_points=("v", "size"), abs_events=("absf", "sum"),
                 elev_mean=("elev", "mean"), grade_mean=("grade", "mean"),
                 lat=("lat", "mean"), lon=("lon", "mean"))
    qv = g["v"].quantile([0.50, 0.85]).unstack()
    grid["crowd_v_p50"], grid["crowd_v_p85"] = qv[0.50], qv[0.85]
    ql = g["lean"].quantile([0.50, 0.90]).unstack()
    grid["crowd_lean_p50"], grid["crowd_lean_p90"] = ql[0.50], ql[0.90]
    qd = g["req"].quantile([0.50, 0.90]).unstack()
    grid["demand_p50"], grid["demand_p90"] = qd[0.50], qd[0.90]
    grid["radius_p50"] = g["radius"].quantile(0.50)

    cor = P.loc[P.corner >= 0, ["cell", "corner"]].drop_duplicates()
    grid["n_corners"] = cor.groupby("cell").size()
    grid["n_corners"] = grid["n_corners"].fillna(0).astype(int)

    tg = T.groupby("cell")
    grid["n_rides"] = tg.size()
    grid["flow_index"] = tg["flow"].mean()
    grid["stop_rate"] = tg["stop"].mean()

    inv = {v: k for k, v in cell_map.items()}
    grid.insert(0, "morton_code", [inv[c] for c in grid.index])
    grid = grid.reset_index(drop=True)
    grid = grid[["morton_code", "n_rides", "n_points", "n_corners", "crowd_v_p50",
                 "crowd_v_p85", "crowd_lean_p50", "crowd_lean_p90", "demand_p50",
                 "demand_p90", "radius_p50", "flow_index", "stop_rate", "abs_events",
                 "grade_mean", "elev_mean", "lat", "lon"]]
    os.makedirs(OUT, exist_ok=True)
    tag = a.tag
    grid.to_parquet(os.path.join(OUT, "crowd_grid%s.parquet" % tag), index=False)
    print("wrote crowd_grid%s.parquet  (%s cells)" % (tag, f"{len(grid):,}"))

    # ---------------- coverage story ----------------
    print("\nCOVERAGE  cells with >=1 ride: %s | >=2: %s | >=5: %s | >=20: %s"
          % (f"{(grid.n_rides >= 1).sum():,}", f"{(grid.n_rides >= 2).sum():,}",
             f"{(grid.n_rides >= 5).sum():,}", f"{(grid.n_rides >= 20).sum():,}"))
    print("          points/cell median %.0f | rides/cell p50 %.0f p95 %.0f max %d"
          % (grid.n_points.median(), grid.n_rides.median(),
             grid.n_rides.quantile(.95), grid.n_rides.max()))
    print("          %s cells carry a corner | %s ABS(code 3) samples total"
          % (f"{(grid.n_corners > 0).sum():,}", f"{int(grid.abs_events.sum()):,}"))

    # ---------------- gems ----------------
    elig = (grid.n_rides >= 5) & (grid.n_corners >= 1) & (grid.demand_p90 >= 10)
    gem = grid[elig].copy()
    dsc = gem.demand_p90.clip(0, 45) / 45.0
    fsc = gem.flow_index.fillna(0)
    psc = np.log1p(gem.n_rides) / np.log1p(grid.n_rides.max())
    gem["gem_score"] = 100 * (0.50 * dsc + 0.30 * fsc + 0.20 * psc)
    gem = gem.sort_values("gem_score", ascending=False).head(100)
    gem_out = gem[["morton_code", "lat", "lon", "gem_score", "demand_p90", "demand_p50",
                   "flow_index", "stop_rate", "n_rides", "n_corners", "crowd_v_p50",
                   "crowd_v_p85", "crowd_lean_p90", "radius_p50", "grade_mean",
                   "elev_mean", "n_points"]].round(4)
    gem_out.to_csv(os.path.join(OUT, "crowd_gems%s.csv" % tag), index=False)
    print("\nwrote crowd_gems%s.csv (top %d of %s eligible cells;"
          " gate n_rides>=5, n_corners>=1, demand_p90>=10 deg)"
          % (tag, len(gem_out), f"{int(elig.sum()):,}"))
    print("  gem_score = 100*(0.50*demand_p90/45 + 0.30*flow_index + 0.20*log1p(n_rides)/log1p(max))")
    print("\nTOP 10 GEMS")
    print("  %-3s %9s %9s %6s %7s %6s %6s %6s %5s"
          % ("#", "lat", "lon", "score", "dem_p90", "flow", "v_p85", "rad_m", "rides"))
    for k, (_, r) in enumerate(gem_out.head(10).iterrows(), 1):
        print("  %-3d %9.5f %9.5f %6.1f %7.1f %6.2f %6.1f %6.0f %5d"
              % (k, r.lat, r.lon, r.gem_score, r.demand_p90, r.flow_index,
                 r.crowd_v_p85, r.radius_p50, r.n_rides))

    # ---------------- hazards ----------------
    hz = grid[grid.n_rides >= 5].copy()
    hz["abs_per_traversal"] = hz.abs_events / hz.n_rides
    hz["abs_per_1k_points"] = 1000.0 * hz.abs_events / hz.n_points
    hz = hz[hz.abs_events > 0].sort_values(["abs_per_traversal", "n_rides"],
                                           ascending=[False, False])
    hz_out = hz[["morton_code", "lat", "lon", "abs_per_traversal", "abs_events", "n_rides",
                 "abs_per_1k_points", "stop_rate", "flow_index", "crowd_v_p50", "crowd_v_p85",
                 "demand_p90", "radius_p50", "grade_mean", "elev_mean", "n_points"]].round(4)
    hz_out.to_csv(os.path.join(OUT, "crowd_hazards%s.csv" % tag), index=False)
    print("\nwrote crowd_hazards%s.csv (%d cells with >=5 rides AND >=1 ABS event)"
          % (tag, len(hz_out)))
    print("TOP 5 HAZARDS")
    print("  %-3s %9s %9s %8s %5s %6s %6s %6s"
          % ("#", "lat", "lon", "abs/trav", "abs", "rides", "stop", "v_p85"))
    for k, (_, r) in enumerate(hz_out.head(5).iterrows(), 1):
        print("  %-3d %9.5f %9.5f %8.3f %5d %6d %6.2f %6.1f"
              % (k, r.lat, r.lon, r.abs_per_traversal, r.abs_events, r.n_rides,
                 r.stop_rate, r.crowd_v_p85))

    if sampled or truncated:
        print("\n" + "!" * 78)
        print("!!! THIS RUN IS A SAMPLE, NOT THE FULL SET: %d rides read." % n_ok)
        print("!" * 78)
    print("\ndone in %.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
