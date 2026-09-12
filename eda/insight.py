import pandas as pd, numpy as np, glob
B = "/home/ubuntu/bmw/data/exampleUserA/exampleUserA/"
m = pd.read_csv(glob.glob(B + "recordedTrips/cloud*.csv")[0]).set_index("itemId")
D = []
for f in [f for f in glob.glob(B + "recordedTrips/*.csv") if "cloud" not in f]:
    d = pd.read_csv(f); d = d[d.positionmapmatchedlatitude != 0].copy(); d["trip"] = f.split("/")[-1][:-4]; D.append(d)
d = pd.concat(D, ignore_index=True).sort_values(["trip", "timestampinmillis"])
d["v"] = d.ridingvehiclespeed * 3.6; d["lean"] = d.sensorsbankingangle.abs()
d["t"] = pd.to_datetime(d.timestampinmillis, unit="ms")
d["frac"] = d.groupby("trip").cumcount() / d.groupby("trip").trip.transform("size")
d["mins"] = (d.timestampinmillis - d.groupby("trip").timestampinmillis.transform("min")) / 60000
mv = d[d.v > 20]

# A) style drift within a ride: lean & throttle by ride-fraction (tours only)
km=d.groupby("trip").apply(lambda g:(g.ridingtrip1.max()-g.ridingtrip1.min())/1000); tours=km[km>60].index; print("tours n",len(tours))
tv = mv[mv.trip.isin(tours)]
print("== A WITHIN-RIDE DRIFT (tours), by decile of ride:")
print(tv.groupby(pd.cut(tv.frac, 5))[["lean", "ridingthrottlevalue", "v"]].mean().round(2).to_string())
print("by minutes into ride:")
print(tv.groupby(pd.cut(tv.mins, [0, 15, 30, 60, 90, 120, 180, 400]))[["lean", "ridingthrottlevalue", "v"]].mean().round(2).to_string())

# B) after a stop: does he ride harder in the 10 min after a >=3min stop vs 10 min before?
res = []
for tid, g in d.groupby("trip"):
    still = (g.v < 1).astype(int); grp = (still.diff() != 0).cumsum()
    for k, s in g[still == 1].groupby(grp[still == 1]):
        dur = (s.timestampinmillis.iloc[-1] - s.timestampinmillis.iloc[0]) / 60000
        if dur < 3: continue
        t0, t1 = s.timestampinmillis.iloc[0], s.timestampinmillis.iloc[-1]
        pre = g[(g.timestampinmillis > t0 - 600000) & (g.timestampinmillis < t0) & (g.v > 20)]
        post = g[(g.timestampinmillis > t1) & (g.timestampinmillis < t1 + 600000) & (g.v > 20)]
        if len(pre) > 60 and len(post) > 60:
            res.append((pre.lean.mean(), post.lean.mean(), pre.ridingthrottlevalue.mean(), post.ridingthrottlevalue.mean(), pre.v.mean(), post.v.mean()))
r = np.array(res); print("\n== B AROUND STOPS n=", len(r), "lean pre/post", r[:, :2].mean(0).round(2), "throttle", r[:, 2:4].mean(0).round(1), "speed", r[:, 4:].mean(0).round(1))

# C) lean-speed envelope: at what speed does he lean most? and how does he corner: braking before or throttle through?
print("\n== C LEAN vs SPEED band (mean lean, moving):")
print(mv.groupby(pd.cut(mv.v, [20, 40, 60, 80, 100, 130, 200])).lean.agg(["mean", lambda s: (s > 25).mean(), "size"]).round(3).to_string())
# throttle while leaning >20
lk = mv[mv.lean > 20]
print("throttle while leaning>20: p50", lk.ridingthrottlevalue.median(), "| share throttle==0 (coasting in corner)", (lk.ridingthrottlevalue == 0).mean().round(2), "| overall coasting share", (mv.ridingthrottlevalue == 0).mean().round(2))
print("longitudinal accel in corners mean", lk.sensorsaccelerationlongitudinal.mean().round(3), "vs straight", mv[mv.lean < 5].sensorsaccelerationlongitudinal.mean().round(3))

# D) bike dependence
bk = m
bd = bk.groupby("bikeId").agg(n=("rideDistance", "size"), km=("rideDistance", lambda s: s.sum() / 1000), leanmax=("leanAngleLeftMax", "mean"), vmax=("speedMaxKmh", "mean"), rpm=("engineMaxRpm", "mean")).sort_values("n", ascending=False)
print("\n== D BIKES (top 6):\n", bd.head(6).round(1).to_string())

# E) gear/rpm habit: shift points
sh = mv[(mv.ridinggear.between(1, 6))]
print("\n== E RPM at which he rides per gear (p50/p90):")
print(sh.groupby("ridinggear").ridingenginespeed.quantile([.5, .9]).unstack().round(0).to_string())
print("share of moving time in top gear (>=5):", (mv.ridinggear >= 5).mean().round(2), "| RPM>6000 share", (mv.ridingenginespeed > 6000).mean().round(4))

# F) outside temperature / weather comfort: rides by temp; lean vs temp
print("\n== F TEMP: ride-start temp p10/p50/p90", m.temperatureMinC.quantile([.1, .5, .9]).round(1).tolist())
tt = mv[mv.sensorsoutsidetemperature > 0]
print(tt.groupby(pd.cut(tt.sensorsoutsidetemperature, [0, 10, 15, 20, 25, 30, 40]))["lean"].agg(["mean", "size"]).round(2).to_string())

# G) what he never does: motorway share proxy (v>110 sustained), night, rain? ; and ride-end behaviour
print("\n== G NEVER/RARELY: share moving time >110 km/h", (mv.v > 110).mean().round(4), "| rides after 20h", (m.startTimestamp.pipe(pd.to_datetime, unit='s').dt.hour >= 20).sum(), "| rides <5C", (m.temperatureMinC < 5).sum())
# H) trip1 odometer reset -> does he reset trip counter (habit), tire pressure trend
print("== H tire pressure front p10/p50/p90 (bar)", d[d.sensorstirepressurefront > 0].sensorstirepressurefront.quantile([.1, .5, .9]).round(2).tolist(), "| rides with TPMS", d[d.sensorstirepressurefront > 0].trip.nunique())
# I) recurring tours: same start+end pairs
m["se"] = m.startLat.round(2).astype(str) + "," + m.startLon.round(2).astype(str) + "->" + m.endLat.round(2).astype(str) + "," + m.endLon.round(2).astype(str)
print("== I repeated start->end pairs:", m.se.value_counts().head(5).to_dict())
# J) multi-day tours (consecutive days away from home)
s = pd.to_datetime(m.startTimestamp, unit="s").dt.date.value_counts().sort_index()
print("== J days with >1 ride:", (s > 1).sum(), "| max rides/day", s.max())
