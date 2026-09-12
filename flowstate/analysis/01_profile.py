"""Profile the real BMW data: schema reality-check, sample rate, missingness, sentinels.

Run:  python F:\\bmw\\analysis\\01_profile.py
Writes: F:\\bmw\\analysis\\out\\profile_columns.csv, profile_trips.csv, and a printed report.
"""
import glob
import io
import json
import os

import numpy as np
import pandas as pd

RAW = r"F:\bmw\data\raw\exampleUserA_x\exampleUserA"
TRIPS = os.path.join(RAW, "recordedTrips")
OUT = r"F:\bmw\analysis\out"
os.makedirs(OUT, exist_ok=True)

manifest_path = glob.glob(os.path.join(TRIPS, "cloudRecordedTracks-*.csv"))[0]
csvs = [p for p in glob.glob(os.path.join(TRIPS, "*.csv")) if "cloudRecordedTracks" not in p]
csvs = [p for p in csvs if not os.path.basename(p).startswith("._")]

print("=" * 78)
print("TRIP MANIFEST")
print("=" * 78)
man = pd.read_csv(manifest_path)
man["tripId"] = man["itemId"].str.split("#").str[-1]
print("rows:", len(man), "| columns:", list(man.columns))
for c in ["bikeId", "isFavorite", "leanAngleLeftMax", "leanAngleRightMax", "rideDistance",
          "rideTime", "speedAverageKmh", "speedMaxKmh", "accelerationMax", "decelerationMax",
          "elevationMaxM", "elevationMinM", "temperatureMaxC", "temperatureMinC", "engineMaxRpm"]:
    if c not in man:
        continue
    s = pd.to_numeric(man[c], errors="coerce")
    if s.notna().sum() == 0:
        print("  %-22s all non-numeric; values: %s" % (c, man[c].astype(str).value_counts().head(4).to_dict()))
    else:
        print("  %-22s n=%3d  min=%10.2f  med=%10.2f  max=%12.2f" %
              (c, s.notna().sum(), s.min(), s.median(), s.max()))
print("  distinct bikeId:", man["bikeId"].nunique() if "bikeId" in man else "n/a")
print("  isFavorite counts:", man["isFavorite"].astype(str).value_counts().to_dict() if "isFavorite" in man else "n/a")

# asymmetry straight from BMW's own summary fields
if {"leanAngleLeftMax", "leanAngleRightMax"} <= set(man.columns):
    L = pd.to_numeric(man["leanAngleLeftMax"], errors="coerce")
    R = pd.to_numeric(man["leanAngleRightMax"], errors="coerce")
    d = (L - R).dropna()
    d = d[(L.abs() > 1) & (R.abs() > 1)]
    print("\n  *** LEFT-RIGHT MAX LEAN ASYMMETRY (BMW's own per-ride fields) ***")
    print("      n=%d  mean=%+.2f deg  median=%+.2f  sd=%.2f  |d|>3deg in %.0f%% of rides  max|d|=%.1f"
          % (len(d), d.mean(), d.median(), d.std(), 100 * (d.abs() > 3).mean(), d.abs().max()))

print()
print("=" * 78)
print("TRACKPOINT FILES:", len(csvs))
print("=" * 78)

frames = []
trip_rows = []
for i, p in enumerate(csvs):
    try:
        df = pd.read_csv(p, low_memory=False)
    except Exception as e:
        print("  FAILED", os.path.basename(p), e)
        continue
    df["_file"] = os.path.basename(p)
    ts = df["timestampinmillis"].astype("int64")
    dt = np.diff(np.sort(ts.values)) / 1000.0
    dt = dt[(dt > 0) & (dt < 600)]
    trip_rows.append({
        "trip": os.path.basename(p)[:-4],
        "rows": len(df),
        "dur_min": (ts.max() - ts.min()) / 60000.0,
        "dt_median_s": float(np.median(dt)) if len(dt) else np.nan,
        "dt_p90_s": float(np.percentile(dt, 90)) if len(dt) else np.nan,
        "gaps_gt10s": int((dt > 10).sum()) if len(dt) else 0,
    })
    frames.append(df)

trips = pd.DataFrame(trip_rows)
trips.to_csv(os.path.join(OUT, "profile_trips.csv"), index=False)
all_df = pd.concat(frames, ignore_index=True)
print("total trackpoints: %s across %d trips" % (f"{len(all_df):,}", len(frames)))
print("sample interval  : median %.2f s (p90 %.2f s)  -> ~%.2f Hz"
      % (trips.dt_median_s.median(), trips.dt_p90_s.median(), 1 / trips.dt_median_s.median()))
print("trip duration    : median %.1f min (min %.1f, max %.1f)"
      % (trips.dur_min.median(), trips.dur_min.min(), trips.dur_min.max()))
print("trips with >10s gaps: %d of %d" % ((trips.gaps_gt10s > 0).sum(), len(trips)))

# ---------------------------------------------------------------- per-column
print()
print("=" * 78)
print("COLUMN REALITY CHECK  (flat%% = share of TRIPS where the channel never changes)")
print("=" * 78)
rows = []
numeric = [c for c in all_df.columns if c not in ("trip_id", "morton_code", "_file")]
for c in numeric:
    s = pd.to_numeric(all_df[c], errors="coerce")
    if s.notna().sum() == 0:
        continue
    flat = 0
    for _, g in all_df.groupby("_file"):
        v = pd.to_numeric(g[c], errors="coerce").dropna()
        if len(v) and v.nunique() <= 1:
            flat += 1
    nz = (s != 0).mean()
    rows.append({
        "column": c,
        "nonnull_pct": round(100 * s.notna().mean(), 1),
        "nonzero_pct": round(100 * nz, 1),
        "flat_trips_pct": round(100 * flat / len(frames), 1),
        "min": round(float(s.min()), 3),
        "p01": round(float(s.quantile(.01)), 3),
        "p50": round(float(s.quantile(.50)), 3),
        "p99": round(float(s.quantile(.99)), 3),
        "max": round(float(s.max()), 3),
    })
cols = pd.DataFrame(rows).sort_values("flat_trips_pct")
cols.to_csv(os.path.join(OUT, "profile_columns.csv"), index=False)
pd.set_option("display.width", 200, "display.max_columns", 50, "display.max_rows", 60)
print(cols.to_string(index=False))

all_df["morton_code"] = all_df["morton_code"].astype(str)
all_df["trip_id"] = all_df["trip_id"].astype(str)
all_df.to_parquet(os.path.join(OUT, "userA_all.parquet"))
print("\nwrote", os.path.join(OUT, "userA_all.parquet"))
