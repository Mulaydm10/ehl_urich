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

ROAD CHARACTER (Phase 2, doc 21). Added columns only - every column above is
computed exactly as before, so the grid the router already uses rebuilds
identical. Validated by analysis/16_road_character.py, not here.
  dwell_share        share of in-cell time (sample gaps > 5 s excluded) below 2 m/s
  long_stop_rides    rides with a stop of >= 60 s here, >= 1 km along the ride from
                     both of its ends (a stop at the start or finish is parking)
  reversals_km       left-right changes of lean past 5 deg at > 5 m/s, per km ridden
  abs_rides          rides with at least one ABS code-3 sample in the cell
  traffic_share      share of traversals that crawl: mean speed < half the cell's
                     median traversal speed, throttle sd <= 5 %-pts, no ABS
  trav_v_median      median over traversals of the traversal's mean speed (m/s)
  rhythm_wavelength_m  median dominant wavelength of signed lean, resampled every
                     10 m, in 1.28 km Hann windows (hop 160 m) with lean rms >= 3 deg
  rhythm_purity      median share of spectral power within +-1 bin of that peak
  rhythm_rides       distinct rides contributing a rhythmic window centred here
  elev_prominence_m  elev_mean minus the median elev_mean of the nearest 200 cells
                     within 3 km
Side outputs: crowd_halves{tag}.parquet (the same columns per odd/even ride, for
split-half reliability) and crowd_transitions{tag}.parquet (per directed cell
pair: rides, and rides that decelerated >= 0.25 g inside the destination cell).
"""
import argparse
import glob
import os
import time

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.spatial import cKDTree

G = 9.81
LAKE = os.environ.get("FS_LAKE")
OUT = os.environ.get("FS_OUT")
CELL_CHARS = int(os.environ.get("FS_CELL_CHARS", 18))
BUDGET_S = 22 * 60          # wall-clock guard; over this we stop and SAY SO
STOP_V = 2.0                # m/s, "stopped"
CV_MAX = 0.25               # speed coefficient of variation for "flowing"

# ---- road character (Phase 2). Fixed before the first full run. ----
GAP_S = 5.0                 # a longer sample gap starts a new segment (as joy.py)
TELEPORT_M = 500.0          # a longer step is a fix jump, not riding
REV_LEAN_DEG = 5.0          # a reversal is a lean sign change past +-5 deg ...
REV_MIN_V = 5.0             # ... at the trusted speed floor demand already uses
LONG_STOP_S = 60.0          # a stop, not a traffic light
LONG_STOP_END_M = 1000.0    # ... this far along the ride from both of its ends
RHY_STEP_M = 10.0           # lean resampled by distance, not time
RHY_N = 128                 # 1.28 km window
RHY_HOP = 16                # 160 m hop, about one 18-char cell
RHY_MIN_RMS = 3.0           # deg; below this the window is a straight
RHY_MIN_V = 5.0             # the whole window must be moving
RHY_HANN = np.hanning(RHY_N)
BRAKE_MS2 = 2.5             # 0.25 g between two ~1 s speed samples
TRAFFIC_V_RATIO = 0.5
TRAFFIC_THR_SD = 5.0        # throttle sd in %-points: "collapsed"
PROMINENCE_R_M = 3000.0
PROMINENCE_K = 200          # median over the nearest 200 cells inside 3 km

USE = ["timestampinmillis", "positionmapmatchedlatitude", "positionmapmatchedlongitude",
       "positionmapmatchedspeed", "positionrawelevation", "positionrawheading",
       "ridingabsbraking", "ridingvehiclespeed", "sensorsbankingangle",
       "trip_id", "morton_code"]
OPTIONAL = ["ridingthrottlevalue"]  # read when present; a ride without it is NOT dropped


def safe_max(a):
    a = a[np.isfinite(a)]
    return a.max() if a.size else 0.0


def process_ride(path, ride_idx, cell_map):
    """Return (points, traversals, speed_source, rhythm windows, transitions) or None."""
    want = set(USE) | set(OPTIONAL)
    d = pd.read_csv(path, usecols=lambda c: c in want,
                    dtype={"morton_code": str, "trip_id": str}, low_memory=False)
    missing = set(USE) - set(d.columns)
    if missing:                     # same outcome as the old usecols=USE: the ride throws
        raise ValueError("missing columns %s" % sorted(missing))
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
    T, W, X = road_character(d, T, code, ts, dt, step, v, absf, src, ride_idx)
    return P, T, src, W, X


def road_character(d, T, code, ts, dt, step, v, absf, src, ride_idx):
    """
    Phase 2 columns for one ride. Reads the arrays process_ride already built
    and never writes to them, so the original columns cannot move.
    Returns T with traversal-level extras, rhythm windows W, transitions X.
    """
    n = len(code)
    uc, li = np.unique(code, return_inverse=True)
    if not np.array_equal(uc, T["cell"].to_numpy()):
        raise AssertionError("traversal order does not match np.unique")
    nc = uc.size
    tsec = ts / 1000.0

    ok_dt = np.isfinite(dt) & (dt <= GAP_S)
    dtc = np.where(ok_dt, dt, 0.0)
    seg = np.cumsum(np.nan_to_num(dt, nan=0.0) > GAP_S)     # a duplicate timestamp is not a gap
    stepc = np.where(ok_dt & np.isfinite(step) & (step <= TELEPORT_M), step, 0.0)
    cum = np.cumsum(stepc)
    vfin = np.isfinite(v)
    vf = np.where(vfin, v, 0.0)
    slow = vfin & (v < STOP_V)

    # ---- dwell ----
    time_s = np.bincount(li, dtc, nc)
    dwell_s = np.bincount(li, dtc * slow, nc)
    km = np.bincount(li, stepc, nc) / 1000.0

    # ---- lean reversals, attributed to the cell where the sign flips ----
    lean_s = d.sensorsbankingangle.to_numpy(dtype=float)
    q = np.flatnonzero(np.isfinite(lean_s) & (np.abs(lean_s) > REV_LEAN_DEG) & (vf > REV_MIN_V))
    flips = np.zeros(nc)
    if q.size > 1:
        sg = np.sign(lean_s[q])
        f = (sg[1:] != sg[:-1]) & (seg[q[1:]] == seg[q[:-1]])
        flips = np.bincount(li[q[1:][f]], minlength=nc).astype(float)

    # ---- per-traversal speed + throttle, for traffic ----
    nv = np.bincount(li, vfin, nc)
    with np.errstate(divide="ignore", invalid="ignore"):
        v_mean = np.bincount(li, vf, nc) / nv
    thr = (d["ridingthrottlevalue"].to_numpy(dtype=float)
           if "ridingthrottlevalue" in d.columns else np.full(n, np.nan))
    if not (np.isfinite(thr).any() and np.nanmax(thr) > 0):
        thr = np.full(n, np.nan)              # a dead channel is not a steady throttle
    elif np.nanmax(thr) <= 1.5:
        thr = thr * 100.0
    tf = np.isfinite(thr)
    thr_n = np.bincount(li, tf, nc)
    t1 = np.bincount(li, np.where(tf, thr, 0.0), nc)
    t2 = np.bincount(li, np.where(tf, thr * thr, 0.0), nc)
    with np.errstate(divide="ignore", invalid="ignore"):
        thr_sd = np.sqrt(np.maximum(t2 / thr_n - (t1 / thr_n) ** 2, 0.0))
    abs_any = np.bincount(li, absf, nc) > 0

    # ---- elevation per traversal: only so the halves can test it (Phase 3) ----
    el = d.positionrawelevation.to_numpy(dtype=float)
    el_ok = np.isfinite(el) & (el != 0) & (el > -100) & (el < 4000)
    elev_sum = np.bincount(li, np.where(el_ok, el, 0.0), nc)
    elev_n = np.bincount(li, el_ok, nc)

    # ---- long stops, away from both ends of the ride ----
    long_stop = np.zeros(nc, dtype=bool)
    e = np.flatnonzero(np.diff(np.r_[0, slow.astype(np.int8), 0]))
    if e.size:
        a_, b_ = e[::2], e[1::2]                       # samples a_ .. b_-1
        dur = tsec[np.minimum(b_, n - 1)] - tsec[a_]
        far = (cum[a_] >= LONG_STOP_END_M) & (cum[-1] - cum[b_ - 1] >= LONG_STOP_END_M)
        hit = (dur >= LONG_STOP_S) & far
        long_stop[li[(a_[hit] + b_[hit] - 1) // 2]] = True

    T = T.assign(time_s=time_s, dwell_s=dwell_s, km=km, flips=flips, v_mean=v_mean,
                 thr_sd=thr_sd, thr_n=thr_n, abs_any=abs_any, long_stop=long_stop,
                 elev_sum=elev_sum, elev_n=elev_n, half=np.int8(ride_idx % 2))

    # ---- rhythm: FFT of signed lean against distance ----
    W = None
    mv = vf > REV_MIN_V
    lean0 = np.where(np.isfinite(lean_s) & (vf > 0.5), lean_s, 0.0)
    if mv.sum() > RHY_N and np.nanstd(lean_s[mv]) > 1.0:
        parts = []
        bounds = np.flatnonzero(np.diff(seg)) + 1
        for m in np.split(np.arange(n), bounds):
            if m.size < 10 or cum[m[-1]] - cum[m[0]] < RHY_N * RHY_STEP_M:
                continue
            cu, first = np.unique(cum[m], return_index=True)
            mi = m[first]
            grid_s = np.arange(cu[0], cu[-1], RHY_STEP_M)
            if grid_s.size < RHY_N:
                continue
            lr = np.interp(grid_s, cu, lean0[mi])
            vr = np.interp(grid_s, cu, vf[mi])
            starts = np.arange(0, grid_s.size - RHY_N + 1, RHY_HOP)
            wl_ = sliding_window_view(lr, RHY_N)[starts]
            vmin = sliding_window_view(vr, RHY_N)[starts].min(axis=1)
            x = wl_ - wl_.mean(axis=1, keepdims=True)
            rms = np.sqrt((x * x).mean(axis=1))
            keep = (vmin > RHY_MIN_V) & (rms >= RHY_MIN_RMS)
            if not keep.any():
                continue
            pw = np.abs(np.fft.rfft(x[keep] * RHY_HANN, axis=1)) ** 2
            r = np.arange(pw.shape[0])
            kk = np.argmax(pw[:, 2:33], axis=1) + 2          # wavelengths 640 .. 40 m
            lp = np.log(pw + 1e-12)
            a0, a1, a2 = lp[r, kk - 1], lp[r, kk], lp[r, kk + 1]
            den = a0 - 2.0 * a1 + a2
            off = np.clip(np.where(np.abs(den) > 1e-12, 0.5 * (a0 - a2) / den, 0.0), -0.5, 0.5)
            wavelength = RHY_N * RHY_STEP_M / (kk + off)
            # bin 1 is outside the denominator, so it must stay outside the numerator:
            # counting it at kk=2 let purity reach 4.7 (found in Phase 3, doc 22)
            lo_bin = np.where(kk - 1 >= 2, pw[r, kk - 1], 0.0)
            purity = (lo_bin + pw[r, kk] + pw[r, kk + 1]) / pw[:, 2:].sum(axis=1)
            centre = grid_s[starts[keep] + RHY_N // 2]
            j = np.clip(np.searchsorted(cu, centre), 0, cu.size - 1)
            parts.append(pd.DataFrame({"cell": code[mi[j]], "wavelength": wavelength.astype(np.float32),
                                       "purity": purity.astype(np.float32)}))
        if parts:
            W = pd.concat(parts, ignore_index=True).assign(ride=np.int32(ride_idx))

    # ---- transitions: did the ride brake hard inside the cell it just entered? ----
    X = None
    if src != "gps":                          # GPS-derived speed is too noisy to difference
        chg = np.r_[True, code[1:] != code[:-1]]
        rid = np.cumsum(chg) - 1
        with np.errstate(invalid="ignore"):
            dv = np.r_[np.nan, np.diff(v)] / dt
        hard = np.isfinite(dv) & (dt >= 0.8) & (dt <= 1.3) & (dv <= -BRAKE_MS2)
        brake = np.bincount(rid, hard, rid[-1] + 1) > 0
        rc = code[chg].astype(np.int64)
        entry_ok = ok_dt[chg]
        if rc.size > 1:
            sel = entry_ok[1:]
            key = (rc[:-1][sel] << 32) | rc[1:][sel]
            if key.size:
                uk, inv = np.unique(key, return_inverse=True)
                bb = np.zeros(uk.size, dtype=bool)
                np.logical_or.at(bb, inv, brake[1:][sel])
                X = pd.DataFrame({"ci": (uk >> 32).astype(np.int32),
                                  "cj": (uk & 0xFFFFFFFF).astype(np.int32), "brake": bb})
    return T, W, X


def character(T, W, keys):
    """Aggregate the Phase 2 columns over `keys` (cell, or cell + half)."""
    g = T.groupby(keys)
    a = g.agg(time_s=("time_s", "sum"), dwell_s=("dwell_s", "sum"), km_ridden=("km", "sum"),
              flips=("flips", "sum"), abs_rides=("abs_any", "sum"),
              long_stop_rides=("long_stop", "sum"), n_trav=("stop", "size"),
              trav_v_median=("v_mean", "median"), elev_sum=("elev_sum", "sum"),
              elev_n=("elev_n", "sum"), stop_rate=("stop", "mean"))
    with np.errstate(divide="ignore", invalid="ignore"):
        a["elev_mean"] = np.where(a.elev_n > 0, a.elev_sum / a.elev_n, np.nan)
        a["dwell_share"] = np.where(a.time_s > 0, a.dwell_s / a.time_s, np.nan)
        a["reversals_km"] = np.where(a.km_ridden >= 1.0, a.flips / a.km_ridden, np.nan)
    med = g["v_mean"].transform("median")
    stuck = ((T["v_mean"] < TRAFFIC_V_RATIO * med) & (T["thr_n"] >= 3)
             & (T["thr_sd"] <= TRAFFIC_THR_SD) & ~T["abs_any"])
    tr = T.loc[T["thr_n"] >= 3, keys].assign(stuck=stuck[T["thr_n"] >= 3])
    a["traffic_share"] = tr.groupby(keys)["stuck"].mean()
    a["traffic_trav"] = tr.groupby(keys).size()
    if W is not None and len(W):
        Wk = W if "half" not in keys else W.assign(half=(W["ride"] % 2).astype(np.int8))
        gw = Wk.groupby(keys)
        a["rhythm_wavelength_m"] = gw["wavelength"].median()
        a["rhythm_purity"] = gw["purity"].median()
        a["rhythm_rides"] = gw["ride"].nunique()
    else:
        a["rhythm_wavelength_m"] = a["rhythm_purity"] = np.nan
        a["rhythm_rides"] = 0
    a["rhythm_rides"] = a["rhythm_rides"].fillna(0).astype(int)
    a["traffic_trav"] = a["traffic_trav"].fillna(0).astype(int)
    return a.drop(columns=["time_s", "dwell_s", "flips", "elev_sum", "elev_n"])


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
    wins, trans = [], []
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
            P, T, s, Wr, Xr = r
            pts.append(P)
            trv.append(T)
            if Wr is not None:
                wins.append(Wr)
            if Xr is not None:
                trans.append(Xr)
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

    # ---------------- road character (Phase 2, doc 21) ----------------
    W = pd.concat(wins, ignore_index=True) if wins else None
    CH_COLS = ["dwell_share", "long_stop_rides", "reversals_km", "km_ridden", "abs_rides",
               "traffic_share", "traffic_trav", "trav_v_median", "rhythm_wavelength_m",
               "rhythm_purity", "rhythm_rides"]
    ch = character(T, W, ["cell"])
    grid = grid.join(ch[CH_COLS])

    # elevation prominence: above the cells around it, not above sea level
    ok = grid["elev_mean"].notna().to_numpy()
    kx = 111320.0 * np.cos(np.radians(float(grid["lat"].mean())))
    xy = np.c_[grid["lat"].to_numpy() * 110540.0, grid["lon"].to_numpy() * kx]
    ev = grid["elev_mean"].to_numpy(dtype=float)
    prom = np.full(len(grid), np.nan)
    if ok.sum() > 1:
        tree = cKDTree(xy[ok])
        kq = int(min(PROMINENCE_K, ok.sum()))
        dist, nb = tree.query(xy[ok], k=kq, distance_upper_bound=PROMINENCE_R_M)
        evs = np.append(ev[ok], np.nan)                  # index ok.sum() = "no neighbour"
        prom[ok] = ev[ok] - np.nanmedian(evs[np.where(np.isfinite(dist), nb, ok.sum())], axis=1)
    grid["elev_prominence_m"] = prom

    inv = {v: k for k, v in cell_map.items()}
    grid.insert(0, "morton_code", [inv[c] for c in grid.index])
    grid = grid.reset_index(drop=True)
    grid = grid[["morton_code", "n_rides", "n_points", "n_corners", "crowd_v_p50",
                 "crowd_v_p85", "crowd_lean_p50", "crowd_lean_p90", "demand_p50",
                 "demand_p90", "radius_p50", "flow_index", "stop_rate", "abs_events",
                 "grade_mean", "elev_mean", "lat", "lon"] + CH_COLS + ["elev_prominence_m"]]
    os.makedirs(OUT, exist_ok=True)
    tag = a.tag
    grid.to_parquet(os.path.join(OUT, "crowd_grid%s.parquet" % tag), index=False)
    print("wrote crowd_grid%s.parquet  (%s cells)" % (tag, f"{len(grid):,}"))

    hv = character(T, W, ["cell", "half"])[CH_COLS + ["n_trav", "elev_mean", "stop_rate"]].reset_index()
    hv.insert(0, "morton_code", [inv[c] for c in hv["cell"]])
    hv.drop(columns="cell").to_parquet(os.path.join(OUT, "crowd_halves%s.parquet" % tag),
                                       index=False)
    if trans:
        X = pd.concat(trans, ignore_index=True)
        X = X.groupby(["ci", "cj"]).agg(n=("brake", "size"), n_brake=("brake", "sum")).reset_index()
        X["ci"] = [inv[c] for c in X["ci"]]
        X["cj"] = [inv[c] for c in X["cj"]]
        X.to_parquet(os.path.join(OUT, "crowd_transitions%s.parquet" % tag), index=False)
        print("wrote crowd_transitions%s.parquet (%s directed pairs)" % (tag, f"{len(X):,}"))
    print("ROAD CHARACTER  dwell_share p50 %.3f | long-stop cells %s | reversals/km p50 %.2f"
          " | abs_rides>=1 %s | traffic_share p90 %.3f | rhythm cells %s (%s windows)"
          % (grid.dwell_share.median(), f"{(grid.long_stop_rides > 0).sum():,}",
             grid.reversals_km.median(), f"{(grid.abs_rides > 0).sum():,}",
             grid.traffic_share.quantile(0.9), f"{(grid.rhythm_rides > 0).sum():,}",
             f"{0 if W is None else len(W):,}"), flush=True)

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
