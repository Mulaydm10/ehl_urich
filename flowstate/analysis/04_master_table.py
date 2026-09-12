"""THE ONE BIG THING: a corner-level master table that fuses every data type we hold.

One row = one corner the rider has ever ridden, carrying
  ROAD DNA  (radius, required lean, gradient, direction, elevation)
+ RIDER RESPONSE (actual lean, speed, throttle, gear, rpm, braking, ABS)
+ CONTEXT  (bike, ambient temp, time of day, season, km into ride, tyre pressure)
+ IDENTITY (ride id, morton cell, position)

Every other analysis in this project is a view over this table.
Also emits a morton-cell road grid = Road DNA WITHOUT OpenStreetMap.

Run: PYTHONIOENCODING=utf-8 python F:\\bmw\\analysis\\04_master_table.py
"""
import glob
import os

import numpy as np
import pandas as pd

OUT = r"F:\bmw\analysis\out"
RAW = r"F:\bmw\data\raw\exampleUserA_x\exampleUserA"
G = 9.81
pd.set_option("display.width", 200, "display.max_columns", 40)

print("=" * 98)
print("DATA TYPES WE HOLD  (every asset, and what each is good for)")
print("=" * 98)
inv = [
    ("recordedTrips/*.csv", 100, "43-col telemetry, ~1 Hz, 508k points", "Rider DNA, Road DNA, corner table"),
    ("cloudRecordedTracks-*.csv", 1, "31-col ride manifest, 101 rides", "ride-level labels: bikeId, isFavorite, L/R max lean, title"),
    ("plannedRoutes/*.gpx", 89, "GPX 1.1, wpt/rtept/trkpt", "REVEALED PREFERENCE + road geometry with no OSM"),
    ("morton_code column", "in every row", "32-char Z-order spatial key", "a road grid for free - crowd aggregation without map matching"),
    ("tripViewer/", 1, "Leaflet app, has playback + lean/rpm colouring", "baseline to beat, and proof BMW expect playback"),
    ("README images", 7, "coverage maps of the lake + 3 users", "slide material, and the shape of the missing data"),
]
for name, n, what, use in inv:
    print("  %-28s %-12s %-44s -> %s" % (name, n, what, use))

# ------------------------------------------------------------------ load
df = pd.read_parquet(os.path.join(OUT, "userA_all.parquet"))
man = pd.read_csv(glob.glob(os.path.join(RAW, "recordedTrips", "cloudRecordedTracks-*.csv"))[0])
man["trip"] = man["itemId"].str.split("#").str[-1]
man["bike"] = man["bikeId"].str[:8]

df = df.sort_values(["_file", "timestampinmillis"]).reset_index(drop=True)
df["trip"] = df["_file"].str.replace(".csv", "", regex=False)
g = df.groupby("_file")
df["dt"] = g["timestampinmillis"].diff() / 1000.0
df["v"] = df["ridingvehiclespeed"]
df["lean"] = df["sensorsbankingangle"].where(df["v"] > 0.5)      # side-stand guard
dh = ((g["positionmapmatchedheading"].diff() + 180) % 360) - 180
df["yaw"] = np.radians(dh) / df["dt"]
df.loc[df["dt"] > 5, "yaw"] = np.nan
df["a_long"] = g["v"].diff() / df["dt"]
df["elev"] = df["positionrawelevation"].where(df["positionrawelevation"] > 0)
df["dist_m"] = (df["v"] * df["dt"]).fillna(0)
df["km_into_ride"] = g["dist_m"].cumsum() / 1000
df["min_into_ride"] = g["timestampinmillis"].transform(lambda s: (s - s.min()) / 60000)
df["grade"] = (g["elev"].diff() / df["dist_m"].replace(0, np.nan)).clip(-.3, .3)
ts = pd.to_datetime(df["timestampinmillis"], unit="ms")
df["hour"] = ts.dt.hour
df["month"] = ts.dt.month
df["date"] = ts.dt.date

mov = (df["v"] > 5) & df["dt"].between(0.8, 1.3) & df["yaw"].notna() & df["lean"].notna()
d = df[mov].copy()
d["theta_req"] = np.degrees(np.arctan(d["v"] * d["yaw"] / G))
d = d[d["theta_req"].abs() < 60]

# ---------------------------------------------------- corner segmentation
d["sgn"] = np.sign(d["yaw"]).where(d["yaw"].abs() > 0.04, 0)
d["blk"] = (d["sgn"] != d.groupby("_file")["sgn"].shift()).cumsum()

agg = {
    "n_s": ("lean", "size"),
    "req_deg": ("theta_req", lambda s: s.abs().max()),
    "lean_deg": ("lean", lambda s: s.abs().max()),
    "lean_p50": ("lean", lambda s: s.abs().median()),
    "v_ms": ("v", "mean"), "v_entry": ("v", "first"), "v_exit": ("v", "last"),
    "radius_m": ("yaw", lambda s: np.nan),
    "dir": ("sgn", "first"),
    "throttle": ("ridingthrottlevalue", "mean"),
    "throttle_exit": ("ridingthrottlevalue", "last"),
    "rpm": ("ridingenginespeed", "mean"),
    "gear": ("ridinggear", "median"),
    "a_min": ("a_long", "min"), "a_max": ("a_long", "max"),
    "abs_max": ("ridingabsbraking", "max"),
    "asc_max": ("ridingasccontrol", "max"),
    "grade": ("grade", "mean"),
    "elev_m": ("elev", "mean"),
    "temp_c": ("sensorsoutsidetemperature", "mean"),
    "tyre_f": ("sensorstirepressurefront", "mean"),
    "km_into": ("km_into_ride", "first"),
    "min_into": ("min_into_ride", "first"),
    "hour": ("hour", "first"), "month": ("month", "first"),
    "lat": ("positionmapmatchedlatitude", "mean"),
    "lon": ("positionmapmatchedlongitude", "mean"),
    "morton": ("morton_code", "first"),
    "gps_acc": ("positionmapmatchedhorizontalaccuracy", "mean"),
}
cor = d[d["sgn"] != 0].groupby(["trip", "blk"]).agg(**agg).reset_index()
cor = cor[cor.n_s >= 3].copy()
cor["radius_m"] = cor["v_ms"] ** 2 / (G * np.tan(np.radians(cor["req_deg"].clip(0.5, 59))))
cor["use_ratio"] = cor["lean_deg"] / cor["req_deg"].replace(0, np.nan)
cor["dir_name"] = np.where(cor["dir"] > 0, "RIGHT", "LEFT")
cor = cor.merge(man[["trip", "bike", "isFavorite"]], on="trip", how="left")

print()
print("=" * 98)
print("MASTER CORNER TABLE")
print("=" * 98)
print("  %s corners | %d rides | %d bikes | %d columns"
      % (f"{len(cor):,}", cor.trip.nunique(), cor.bike.nunique(), cor.shape[1]))
print("  median corner: %.0f m radius, %.0f km/h, %.1f deg required, %.1f deg used, %.0f%% throttle, gear %.0f"
      % (cor.radius_m.median(), 3.6 * cor.v_ms.median(), cor.req_deg.median(),
         cor.lean_deg.median(), cor.throttle.median(), cor.gear.median()))
print("  span: elevation %.0f-%.0f m | temp %.0f-%.0f C | %s to %s"
      % (cor.elev_m.min(), cor.elev_m.max(), cor.temp_c.min(), cor.temp_c.max(),
         d.date.min(), d.date.max()))
cor.to_parquet(os.path.join(OUT, "master_corners.parquet"))
print("  -> out/master_corners.parquet")

# ------------------------------------------------- morton cell road grid
print()
print("=" * 98)
print("ROAD DNA WITHOUT OPENSTREETMAP: aggregate the corner table by morton cell")
print("=" * 98)
for prec in (14, 18, 22):
    cor["cell"] = cor["morton"].str[:prec]
    n = cor["cell"].nunique()
    rep = cor.groupby("cell").size()
    print("  morton prefix %2d chars -> %6d cells, %5.1f corners/cell, %d cells seen on >1 ride"
          % (prec, n, rep.mean(), (cor.groupby("cell")["trip"].nunique() > 1).sum()))
cor["cell"] = cor["morton"].str[:18]
grid = cor.groupby("cell").agg(
    n_corners=("req_deg", "size"), rides=("trip", "nunique"),
    demand_p50=("req_deg", "median"), demand_p90=("req_deg", lambda s: s.quantile(.9)),
    radius_p50=("radius_m", "median"), v_p50=("v_ms", "median"),
    grade=("grade", "mean"), elev=("elev_m", "mean"),
    abs_events=("abs_max", lambda s: (s >= 3).sum()),
    lat=("lat", "mean"), lon=("lon", "mean")).reset_index()
grid = grid[grid.n_corners >= 2]
print("\n  usable grid: %d cells with >=2 corners" % len(grid))
print("  demand p90 across cells: p25=%.1f p50=%.1f p75=%.1f p95=%.1f deg"
      % (grid.demand_p90.quantile(.25), grid.demand_p90.median(),
         grid.demand_p90.quantile(.75), grid.demand_p90.quantile(.95)))
print("  >>> With 77,700 crowd rides instead of 100, this IS the Road DNA layer - no OSM, no map matching.")
grid.to_parquet(os.path.join(OUT, "morton_grid.parquet"))
print("  -> out/morton_grid.parquet")

# ------------------------------------------------------- hardest roads he rides
print()
print("=" * 98)
print("WHAT THE TABLE IMMEDIATELY ANSWERS")
print("=" * 98)
top = grid.nlargest(8, "demand_p90")[["lat", "lon", "demand_p90", "radius_p50", "elev", "n_corners", "rides"]]
print("\n  The 8 most demanding places this rider has been (lat, lon -> paste into a map):")
print(top.to_string(index=False, float_format=lambda x: "%.4f" % x if abs(x) < 100 else "%.0f" % x))
haz = grid[grid.abs_events > 0].nlargest(5, "abs_events")[["lat", "lon", "abs_events", "demand_p90", "n_corners"]]
print("\n  Places where hard-braking/ABS events cluster (the hazard layer, F75):")
print(haz.to_string(index=False, float_format=lambda x: "%.4f" % x if abs(x) < 100 else "%.0f" % x) if len(haz)
      else "    (none at this grid precision)")
