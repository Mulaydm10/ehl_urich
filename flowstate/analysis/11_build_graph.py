"""11 - Build the navigable edge table from real ride transitions.

The cell table (10_crowd_layer.py) says how good a place is. This says what
connects to what. Connectivity comes from rides, never from geometric proximity:
if a bike went from cell A to cell B there is a road between them; if no bike
ever did, there is not. That rules out routing across rivers, ridges and
motorway fences, which a 250 m radius join would cheerfully do.

MEASURED DATA RULES honoured here (see NOTES.md / 10_crowd_layer.py):
  * morton_code is a 32-char base-4 string: read as TEXT, never as an int
  * CELL = first 18 chars = BMW quadkey level 18, ~153 x 102 m at lat 48
  * ridingvehiclespeed (m/s) -> positionmapmatchedspeed -> GPS-derived
  * lake timestamps are shifted per trip, but DIFFERENCES within a trip are
    intact, so travel seconds are usable; absolute time still is not.

DEFINITIONS
  transition    one consecutive (cell_i -> cell_j) pair within one ride, after
                collapsing runs of the same cell. A ride that sits parked in a
                cell for 12,000 samples still emits at most one departure.
  seconds       trip-local dt between the last sample in cell_i and the first
                in cell_j.
  metres        great-circle distance between the two cell centroids as ridden.
  surprise      log(radius_i / radius_j); positive means the road tightens on
                you. Design-consistency literature says crashes cluster on the
                differential, not on the absolute.
"""
import argparse
import glob
import os
import time

import numpy as np
import pandas as pd

LAKE = os.environ.get("FS_LAKE")
OUT = os.environ.get("FS_OUT")
CELL_CHARS = int(os.environ.get("FS_CELL_CHARS", 18))
R_EARTH = 6371000.0
MAX_GAP_S = 120.0      # a jump longer than this is a logging gap, not a road
MAX_STEP_M = 2000.0    # ditto in space: 18-char cells are ~153 m apart

USE = ["timestampinmillis", "positionmapmatchedlatitude", "positionmapmatchedlongitude",
       "positionmapmatchedspeed", "ridingvehiclespeed", "trip_id", "morton_code"]


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def ride_transitions(path):
    """One ride file -> DataFrame of consecutive cell-to-cell transitions."""
    try:
        d = pd.read_csv(path, usecols=lambda c: c in USE, low_memory=False)
    except Exception:
        return None
    if "morton_code" not in d.columns or len(d) < 3:
        return None

    d["cell"] = d.morton_code.astype(str).str[:CELL_CHARS]
    d = d[d.cell.str.len() == CELL_CHARS]
    if len(d) < 3:
        return None

    t = pd.to_numeric(d.timestampinmillis, errors="coerce").to_numpy(float) / 1000.0
    lat = pd.to_numeric(d.positionmapmatchedlatitude, errors="coerce").to_numpy(float)
    lon = pd.to_numeric(d.positionmapmatchedlongitude, errors="coerce").to_numpy(float)
    ok = np.isfinite(t) & np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) > 1e-6)
    if ok.sum() < 3:
        return None
    cells = d.cell.to_numpy()[ok]
    t, lat, lon = t[ok], lat[ok], lon[ok]
    order = np.argsort(t, kind="stable")
    cells, t, lat, lon = cells[order], t[order], lat[order], lon[order]

    # collapse runs of the same cell: keep the LAST sample of each run as the
    # departure point and the FIRST of the next run as the arrival point.
    newrun = np.empty(len(cells), bool)
    newrun[0] = True
    newrun[1:] = cells[1:] != cells[:-1]
    first = np.flatnonzero(newrun)
    if len(first) < 2:
        return None
    last = np.r_[first[1:] - 1, len(cells) - 1]

    i_dep, i_arr = last[:-1], first[1:]
    secs = t[i_arr] - t[i_dep]
    mets = haversine(lat[i_dep], lon[i_dep], lat[i_arr], lon[i_arr])
    keep = (secs > 0) & (secs <= MAX_GAP_S) & (mets > 0) & (mets <= MAX_STEP_M)
    if not keep.any():
        return None
    return pd.DataFrame({"ci": cells[first[:-1]][keep], "cj": cells[first[1:]][keep],
                         "secs": secs[keep], "mets": mets[keep]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="trips-samples-2")
    ap.add_argument("--tag", default="")
    ap.add_argument("--min-transitions", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(p for p in glob.glob(os.path.join(LAKE, a.set, "*", "*.csv"))
                   if not os.path.basename(p).startswith("._"))
    if a.limit:
        files = files[:a.limit]
    print("=" * 78)
    print("EDGE TABLE  |  set=%s  |  %d ride files" % (a.set, len(files)))
    print("=" * 78, flush=True)

    parts, n_ok, n_bad = [], 0, 0
    t0 = time.time()
    for k, p in enumerate(files, 1):
        r = ride_transitions(p)
        if r is None:
            n_bad += 1
        else:
            parts.append(r)
            n_ok += 1
        if k % 1000 == 0:
            print("  %5d/%d | %5.1f s | %d usable" % (k, len(files), time.time() - t0, n_ok),
                  flush=True)

    raw = pd.concat(parts, ignore_index=True)
    print("\nparsed %s rides (%s unusable) -> %s transitions in %.1f s"
          % (f"{n_ok:,}", f"{n_bad:,}", f"{len(raw):,}", time.time() - t0))

    g = raw.groupby(["ci", "cj"], sort=False)
    E = g.agg(n_transitions=("secs", "size"),
              median_seconds=("secs", "median"),
              median_metres=("mets", "median")).reset_index()
    E["median_speed"] = E.median_metres / E.median_seconds
    print("raw edges (any support): %s" % f"{len(E):,}")

    E = E[E.n_transitions >= a.min_transitions].reset_index(drop=True)
    print("edges with n_transitions >= %d: %s" % (a.min_transitions, f"{len(E):,}"))

    # ---- attach cell geometry + the surprise index ----
    tag = a.tag
    grid_path = os.path.join(OUT, "crowd_grid%s.parquet" % tag)
    if os.path.exists(grid_path):
        C = pd.read_parquet(grid_path).set_index("morton_code")
        for side, col in (("ci", "i"), ("cj", "j")):
            E["radius_" + col] = E[side].map(C.radius_p50)
            E["demand_" + col] = E[side].map(C.demand_p90)
        E["surprise"] = np.log(E.radius_i / E.radius_j)
        print("joined cell table: %.1f%% of edges have radius on both ends"
              % (100 * E.surprise.notna().mean()))

    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, "graph_edges%s.parquet" % tag)
    E.to_parquet(dst, index=False)
    print("\nwrote graph_edges%s.parquet (%s edges)" % (tag, f"{len(E):,}"))

    # ---- STOP-CHECK: is the graph actually navigable? ----
    nodes = pd.Index(pd.unique(np.r_[E.ci.values, E.cj.values]))
    idx = pd.Series(np.arange(len(nodes)), index=nodes)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    A = coo_matrix((np.ones(len(E)), (idx[E.ci].values, idx[E.cj].values)),
                   shape=(len(nodes), len(nodes))).tocsr()
    n_comp, lbl = connected_components(A, directed=True, connection="weak")
    sizes = np.bincount(lbl)
    lcc = sizes.max()
    print("\nSTOP-CHECK")
    print("  nodes %s | edges %s | mean out-degree %.2f"
          % (f"{len(nodes):,}", f"{len(E):,}", len(E) / len(nodes)))
    print("  weakly-connected components %s | largest %s (%.1f%% of nodes)"
          % (f"{n_comp:,}", f"{lcc:,}", 100 * lcc / len(nodes)))
    print("  median edge %.0f m / %.1f s (%.1f km/h)"
          % (E.median_metres.median(), E.median_seconds.median(),
             3.6 * E.median_speed.median()))
    if lcc / len(nodes) < 0.70:
        print("  !! FRAGMENTED (<70%). Re-run with --min-transitions 1, "
              "or coarsen CELL_CHARS to 16.")
    if len(E) / len(nodes) < 2.0:
        print("  !! mean degree < 2. Cell prefix is too fine; try CELL_CHARS=16.")

    # ---- does surprise predict hard braking better than absolute demand? ----
    if "surprise" in E.columns and os.path.exists(grid_path):
        sub = E.dropna(subset=["surprise"]).copy()
        sub["abs_j"] = sub.cj.map(C.abs_events)
        sub["rides_j"] = sub.cj.map(C.n_rides)
        sub = sub[sub.rides_j >= 5]
        sub["abs_rate"] = sub.abs_j / sub.rides_j
        print("\nSURPRISE INDEX vs ABS (destination cells with >=5 rides, n=%s)"
              % f"{len(sub):,}")
        for name, col in (("surprise  log(Ri/Rj)", "surprise"),
                          ("absolute demand_p90", "demand_j"),
                          ("absolute radius_p50", "radius_j")):
            print("  spearman(abs_rate, %-20s) = %+.3f"
                  % (name, sub.abs_rate.corr(sub[col], method="spearman")))
        hi = sub[sub.surprise > sub.surprise.quantile(0.90)]
        lo = sub[sub.surprise.abs() < 0.1]
        print("  ABS rate: tightening top decile %.3f  vs  radius-stable %.3f  (%.2fx)"
              % (hi.abs_rate.mean(), lo.abs_rate.mean(),
                 hi.abs_rate.mean() / max(lo.abs_rate.mean(), 1e-9)))

    print("\ndone in %.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
