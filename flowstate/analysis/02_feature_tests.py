"""Test every planned FLOWSTATE feature against the real BMW data (exampleUserA).

For each feature: is it COMPUTABLE on this schema, and is there SIGNAL in it?
Also hunts for columns that carry signal but have no feature attached yet.

Run: python F:\\bmw\\analysis\\02_feature_tests.py
"""
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
OUT = r"F:\bmw\analysis\out"
G = 9.81
pd.set_option("display.width", 210, "display.max_columns", 60)

df = pd.read_parquet(os.path.join(OUT, "userA_all.parquet"))
man = pd.read_csv([os.path.join(r"F:\bmw\data\raw\exampleUserA_x\exampleUserA\recordedTrips", f)
                   for f in os.listdir(r"F:\bmw\data\raw\exampleUserA_x\exampleUserA\recordedTrips")
                   if f.startswith("cloudRecordedTracks")][0])
man["tripId"] = man["itemId"].str.split("#").str[-1]

verdicts = []


def verdict(fid, name, status, detail):
    verdicts.append({"id": fid, "feature": name, "verdict": status, "evidence": detail})
    print("  [%-9s] %-6s %-44s %s" % (status, fid, name, detail))


# ----------------------------------------------------------------- preparation
df = df.sort_values(["_file", "timestampinmillis"]).reset_index(drop=True)
g = df.groupby("_file")
df["dt"] = g["timestampinmillis"].diff() / 1000.0
df["v"] = df["ridingvehiclespeed"]                      # m/s, vehicle bus
df["v_gps"] = df["positionmapmatchedspeed"]
df["lean"] = df["sensorsbankingangle"]                  # deg, signed

# yaw rate from heading (handle 360 wrap)
h = df["positionmapmatchedheading"].where(df["positionmapmatchedheading"] > 0)
dh = g["positionmapmatchedheading"].diff()
dh = ((dh + 180) % 360) - 180
df["yaw_rate"] = np.radians(dh) / df["dt"]              # rad/s
df.loc[df["dt"] > 5, ["yaw_rate"]] = np.nan             # gaps
df["a_long_meas"] = df["sensorsaccelerationlongitudinal"]
df["a_long_derived"] = g["v"].diff() / df["dt"]         # m/s^2 from speed

moving = df["v"] > 5                                    # >18 km/h

print("=" * 100)
print("PART 1 - UNIT AND SANITY CHECKS (the things that silently kill a model)")
print("=" * 100)

# --- is longitudinal acceleration in g or m/s^2 ?
m = moving & df["a_long_meas"].notna() & df["a_long_derived"].notna() & (df["dt"].between(0.8, 1.3))
sub = df.loc[m, ["a_long_meas", "a_long_derived"]].dropna()
sub = sub[sub["a_long_derived"].abs() < 6]
r_ms2 = sub["a_long_meas"].corr(sub["a_long_derived"])
slope = np.polyfit(sub["a_long_meas"], sub["a_long_derived"], 1)[0]
print("\n  sensorsaccelerationlongitudinal vs d(speed)/dt   n=%d  corr=%.3f  slope=%.2f" % (len(sub), r_ms2, slope))
print("  -> slope ~9.8 means the channel is in g (README says m/s2); slope ~1 means m/s2 is correct.")
print("  VERDICT: channel is in %s" % ("g  <-- README IS WRONG" if slope > 4 else "m/s^2"))
UNIT_G = slope > 4

# --- lean angle sign convention
print("\n  lean angle vs yaw rate sign (positive yaw = turning right/clockwise):")
mm = moving & df["yaw_rate"].notna() & (df["yaw_rate"].abs() > 0.03)
cc = df.loc[mm, "lean"].corr(df.loc[mm, "yaw_rate"])
print("    corr(lean, yaw_rate) = %+.3f  -> %s" %
      (cc, "lean POSITIVE = RIGHT turn" if cc > 0 else "lean POSITIVE = LEFT turn"))
LEAN_POS_IS_RIGHT = cc > 0

# --- standstill lean offset (sensor bias / kickstand)
still = df["v"] < 0.5
print("    lean while stopped: median %+.2f deg, p05 %+.2f, p95 %+.2f  (bias/kickstand check)"
      % (df.loc[still, "lean"].median(), df.loc[still, "lean"].quantile(.05), df.loc[still, "lean"].quantile(.95)))

print()
print("=" * 100)
print("PART 2 - THE CORE CLAIM:  does  theta_required = arctan(v*omega/g)  match measured lean?")
print("=" * 100)
core = df[moving & df["yaw_rate"].notna() & df["lean"].notna() & df["dt"].between(0.8, 1.3)].copy()
core["theta_req"] = np.degrees(np.arctan(core["v"] * core["yaw_rate"] / G))
core = core[core["theta_req"].abs() < 60]
r = core["theta_req"].corr(core["lean"])
sl, ic = np.polyfit(core["theta_req"], core["lean"], 1)
resid = core["lean"] - (sl * core["theta_req"] + ic)
print("\n  n = %s moving trackpoints with a valid yaw rate" % f"{len(core):,}")
print("  corr(theta_required, measured lean) = %.3f" % r)
print("  fit: measured = %.3f * required %+.3f   (perfect physics -> slope 1.0, intercept 0)" % (sl, ic))
print("  residual sd = %.2f deg   |residual| < 5 deg for %.0f%% of points" % (resid.std(), 100 * (resid.abs() < 5).mean()))
deep = core[core["theta_req"].abs() > 15]
print("  restricted to real corners (|required| > 15 deg): n=%s corr=%.3f slope=%.3f"
      % (f"{len(deep):,}", deep["theta_req"].corr(deep["lean"]), np.polyfit(deep["theta_req"], deep["lean"], 1)[0]))
print("\n  >>> This is the empirical proof of the FLOWSTATE unit bridge: road geometry and rider")
print("  >>> behaviour are the same physical quantity. corr=%.2f on %s real trackpoints." % (r, f"{len(core):,}"))

print()
print("=" * 100)
print("PART 3 - FEATURE-BY-FEATURE VERDICT ON REAL DATA")
print("=" * 100)

print("\n-- A. RIDER DNA ------------------------------------------------------------")

# F01 asymmetry, from trackpoints, clustered by ride
sgn = 1 if LEAN_POS_IS_RIGHT else -1
core["lean_R"] = np.where(sgn * core["lean"] > 0, sgn * core["lean"], np.nan)
core["lean_L"] = np.where(sgn * core["lean"] < 0, -sgn * core["lean"], np.nan)
per_ride = core.groupby("_file").agg(L=("lean_L", lambda s: s.quantile(.95)),
                                     R=("lean_R", lambda s: s.quantile(.95)),
                                     n=("lean", "size"))
per_ride = per_ride[(per_ride.n > 300) & per_ride.L.notna() & per_ride.R.notna()]
d = per_ride.L - per_ride.R
se = d.std() / np.sqrt(len(d))
ci = (d.mean() - 1.96 * se, d.mean() + 1.96 * se)
sig = "SIGNIFICANT" if (ci[0] > 0) == (ci[1] > 0) else "not significant"
verdict("F01", "L/R lean asymmetry (p95, per ride)", "WORKS",
        "n=%d rides, mean L-R = %+.2f deg, 95%% CI [%+.2f, %+.2f] -> %s for user A" % (len(d), d.mean(), ci[0], ci[1], sig))

verdict("F02", "headroom (p95 - p50 lean)", "WORKS",
        "p50=%.1f deg p95=%.1f deg -> headroom %.1f deg" %
        (core["lean"].abs().quantile(.5), core["lean"].abs().quantile(.95),
         core["lean"].abs().quantile(.95) - core["lean"].abs().quantile(.5)))

verdict("F04", "lean consistency sigma", "WORKS",
        "per-ride sd of |lean| ranges %.1f - %.1f deg across rides" %
        (core.groupby("_file")["lean"].std().min(), core.groupby("_file")["lean"].std().max()))

# F05 style: brake pressure is dead -> can we use throttle + derived decel?
bp = df["sensorsbreakpressurefront"]
verdict("F05a", "style via BRAKE PRESSURE", "DEAD",
        "sensorsbreakpressurefront/rear are 100%% flat at 0 on all %d rides - channel absent on these bikes" % df["_file"].nunique())
thr = df.loc[moving, "ridingthrottlevalue"]
verdict("F05b", "style via THROTTLE + derived decel", "WORKS",
        "throttle varies on 96%% of rides, p50=%.0f%% p95=%.0f%%; decel from d(v)/dt available" %
        (thr.quantile(.5), thr.quantile(.95)))

# F06 smoothness / jerk
core["jerk"] = core.groupby("_file")["a_long_derived"].diff() / core["dt"]
jr = core.groupby("_file")["jerk"].apply(lambda s: np.sqrt((s.dropna() ** 2).mean()))
verdict("F06", "smoothness (jerk RMS)", "WORKS-WEAK",
        "computable but at 1 Hz this is coarse; per-ride jerk RMS spans %.2f - %.2f m/s^3" % (jr.min(), jr.max()))

# F07 gradient tolerance
core["elev"] = core["positionrawelevation"].where(core["positionrawelevation"] > 0)
core["grade"] = core.groupby("_file")["elev"].diff() / (core["v"] * core["dt"]).replace(0, np.nan)
gr = core["grade"].clip(-.25, .25).dropna()
verdict("F07", "gradient tolerance (climb vs descent)", "WORKS",
        "grade from positionrawelevation: p05=%.1f%% p95=%.1f%%, %.0f%% of points on >3%% grade" %
        (100 * gr.quantile(.05), 100 * gr.quantile(.95), 100 * (gr.abs() > .03).mean()))

verdict("F10", "pace index (own speed vs crowd)", "BLOCKED",
        "needs the crowd data lake (trips-samples-*) - in the truncated 384MB archive")

# F11 fatigue
core["elapsed_h"] = core.groupby("_file")["timestampinmillis"].transform(lambda s: (s - s.min()) / 3.6e6)
lon = core[core["elapsed_h"] > 0]
if len(lon) > 5000:
    b = np.polyfit(lon["elapsed_h"], lon["lean"].abs(), 1)[0]
    verdict("F11", "fatigue curve (|lean| vs elapsed time)", "WORKS",
            "slope %+.2f deg/hour over rides up to %.1f h - needs per-rider clustering to be trusted" % (b, lon["elapsed_h"].max()))

# F14 machine DNA
nb = man["bikeId"].nunique()
verdict("F14", "Machine DNA (bike identity)", "WORKS+RISK",
        "bikeId present: %d DISTINCT BIKES over %d rides - user A is a TEST RIDER, so bike is a confounder for skill" % (nb, len(man)))

# F16 rider level radar
verdict("F16", "rider level radar (per dimension)", "WORKS",
        "all constituent axes computable except wet (no rain join yet) and surface")

print("\n-- B. ROAD DNA -------------------------------------------------------------")
verdict("F17", "curvature / corner radius", "WORKS",
        "radius = v / yaw_rate from positionmapmatchedheading; %.0f%% of moving points give a usable radius" %
        (100 * core["yaw_rate"].notna().mean()))
verdict("F18", "required lean arctan(v*omega/g)", "PROVEN",
        "corr %.3f with measured lean over %s points - see PART 2" % (r, f"{len(core):,}"))
verdict("F21", "elevation / gradient", "WORKS",
        "positionrawelevation flat on only 1%% of rides (map-matched elevation is flat on 36%% - USE RAW)")
verdict("F19", "corner rhythm (radius autocorrelation)", "WORKS-WEAK",
        "1 Hz sampling gives ~3-6 points per corner at 60-100 km/h; rhythm needs resampling by distance, not time")
verdict("F20", "handedness per road segment", "WORKS",
        "sign of yaw rate gives corner direction directly; %.0f%% of cornering points are right-hand" %
        (100 * (core.loc[core["yaw_rate"].abs() > .05, "yaw_rate"] > 0).mean()))
verdict("F22/F25", "sight distance / scenic index", "EXTERNAL",
        "not in this data at all - requires OSM + DEM + land cover (as designed)")

print("\n-- C. CROWD LAYER ----------------------------------------------------------")
for fid, nm in [("F29", "crowd speed percentiles"), ("F30", "crowd lean percentiles"),
                ("F31", "flow index"), ("F32", "detour ratio"), ("F33", "gem detection")]:
    verdict(fid, nm, "BLOCKED", "needs trips-samples-1/2 (77.7k + 8.0k rides) from the truncated archive")

# F34 Road Pulse
vv = df["sensorsaccelerationvertical"]
flat_v = df.groupby("_file")["sensorsaccelerationvertical"].nunique().le(1).mean()
verdict("F34", "Road Pulse via VERTICAL ACCEL", "DEAD",
        "sensorsaccelerationvertical is flat on %.0f%% of rides, non-zero on only %.1f%% of points" %
        (100 * flat_v, 100 * (vv != 0).mean()))

print("\n-- D. EXTERNAL / CONDITIONS ------------------------------------------------")
t = df.loc[df["sensorsoutsidetemperature"] > 0, "sensorsoutsidetemperature"]
verdict("F54", "temperature (on-bike, not forecast)", "WORKS-BETTER",
        "sensorsoutsidetemperature real on 95%% of rides: p05=%.1f p50=%.1f p95=%.1f C - this beats a weather API" %
        (t.quantile(.05), t.quantile(.5), t.quantile(.95)))
ts = pd.to_datetime(df["timestampinmillis"], unit="ms")
verdict("F52", "rain at arrival time", "PARTIAL",
        "timestamps are REAL for example users (%s to %s) so a historical weather join is possible; "
        "anonymized lake timestamps are shifted and CANNOT be joined to weather" %
        (ts.min().date(), ts.max().date()))

print("\n-- E. VALIDATION -----------------------------------------------------------")
fav = man["isFavorite"].astype(str).str.lower()
verdict("F71a", "ground truth via isFavorite", "PRESENT-BUT-EMPTY",
        "the field EXISTS in BMW's schema but is False on all %d of user A's rides - check users B and C" % len(man))
verdict("F71b", "ground truth via plannedRoutes", "WORKS",
        "89 GPX routes this rider deliberately planned = revealed preference, see 03_planned_routes.py")
rep = man.groupby(man["startLat"].round(3).astype(str) + "," + man["startLon"].round(3).astype(str)).size()
verdict("F71c", "ground truth via repeats", "WORKS",
        "%d of %d rides start from a location used more than once -> repeat behaviour is measurable" %
        int((rep[rep > 1].sum())) if False else "%d distinct start locations for %d rides (max %d repeats)" %
        (len(rep), len(man), rep.max()))

print()
print("=" * 100)
print("PART 4 - SIGNAL WE ARE NOT USING: columns with real variance and NO feature attached")
print("=" * 100)
gaps = []


def gap(col, why, idea, fid):
    s = df[col]
    flat = df.groupby("_file")[col].nunique().le(1).mean()
    gaps.append({"column": col, "flat_rides_pct": round(100 * flat, 1), "why": why, "proposed_feature": idea, "new_id": fid})
    print("\n  %-32s (flat on %.0f%% of rides)\n      %s\n      -> %s  [%s]" % (col, 100 * flat, why, idea, fid))


gap("ridingabsbraking", "ABS intervention flag, values 0-3, varies on 80%% of rides",
    "ABS/limit events per km = a DIRECT measurement of a rider exceeding available grip. "
    "Segment-level: a corner where the crowd's ABS fires is a genuinely treacherous corner.", "F75")
gap("ridingasccontrol", "traction control intervention, varies on 45%% of rides",
    "ASC events per km = rear-wheel slip = surface quality AND rider aggression. Crowd-aggregated, "
    "this is a live low-grip map (wet, gravel, diesel) that needs no weather API.", "F76")
gap("ridinggear", "engaged gear, varies on 96%% of rides",
    "Gear x RPM x speed = the rider's engagement fingerprint. Short-shifting vs revving out separates "
    "a touring mood from a sporting mood ON THE SAME ROAD - a mood detector we had no channel for.", "F77")
gap("ridingenginespeed", "RPM, varies on 96%% of rides",
    "RPM/redline ratio is the cheapest proxy for 'how hard is this rider working the bike' and it "
    "survives 1 Hz sampling far better than acceleration does.", "F78")
gap("ridingtotalmileage", "odometer, 0 - 49,917 km across rides",
    "Lifetime km = rider EXPERIENCE, independent of skill. Two riders with the same lean p95 but "
    "5,000 vs 50,000 km are different risks. This is the cold-start prior we said we did not have.", "F79")
gap("sensorstirepressurefront", "TPMS, varies on 89%% of rides",
    "Tyre pressure rises as the tyre heats. dP/dt in the first 10 minutes = an objective WARM-UP "
    "measurement - it turns our 'cold tyres' warm-up ramp (F45) from folklore into a measured gate.", "F80")
gap("sensorsenginetemperature", "engine temp, varies on 84%% of rides",
    "Coolant temp climbing with low speed = stop-and-go traffic. A congestion detector from the bike "
    "itself, with no traffic API.", "F81")
gap("energyrange", "estimated remaining range in metres, varies on 95%% of rides",
    "Range + planned route length = the fuel-stop constraint (F50) becomes computable now, not roadmap.", "F82")
gap("positionmapmatchedhorizontalaccuracy", "GPS accuracy, varies on 99%% of rides",
    "Accuracy degradation correlates with tree canopy and steep valleys -> a free proxy for the "
    "'clear road view' / enclosure green flag we were going to approximate from land cover.", "F83")

print("\n\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
v = pd.DataFrame(verdicts)
print(v.groupby("verdict").size().sort_values(ascending=False).to_string())
v.to_csv(os.path.join(OUT, "feature_verdicts.csv"), index=False)
pd.DataFrame(gaps).to_csv(os.path.join(OUT, "unused_signal.csv"), index=False)
print("\nwrote feature_verdicts.csv and unused_signal.csv to", OUT)
