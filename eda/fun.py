import pandas as pd, numpy as np, glob, xml.etree.ElementTree as ET, collections
B = "/home/ubuntu/bmw/data/exampleUserA/exampleUserA/"
m = pd.read_csv(glob.glob(B + "recordedTrips/cloud*.csv")[0]).set_index("itemId")
fs = [f for f in glob.glob(B + "recordedTrips/*.csv") if "cloud" not in f]
D = []
for f in fs:
    d = pd.read_csv(f)
    d = d[(d.positionmapmatchedlatitude != 0)].copy()
    d["trip"] = f.split("/")[-1][:-4]
    D.append(d)
d = pd.concat(D, ignore_index=True)
d["v"] = d.ridingvehiclespeed * 3.6
d["lean"] = d.sensorsbankingangle.abs()
d["cell"] = (d.positionmapmatchedlatitude.round(3).astype(str) + "," + d.positionmapmatchedlongitude.round(3).astype(str))  # ~100m cells
d["cell_c"] = (d.positionmapmatchedlatitude.round(2).astype(str) + "," + d.positionmapmatchedlongitude.round(2).astype(str))  # ~1km cells
d["t"] = pd.to_datetime(d.timestampinmillis, unit="ms")

# 1) Re-ride frequency: cells visited on many different trips (habit vs. destinations)
cv = d.groupby("cell_c").trip.nunique()
print("== 1 RE-RIDE: 1km cells total", len(cv), "| visited on >=5 trips", (cv >= 5).sum(), ">=10 trips", (cv >= 10).sum())
home = cv.idxmax(); print("home cell", home, "trips", cv.max())
# excluding cells within 15km of home -> repeatedly ridden 'fun' roads far from home
hl, ho = map(float, home.split(","))
far = cv[[np.hypot((float(c.split(",")[0]) - hl) * 111, (float(c.split(",")[1]) - ho) * 75) > 15 for c in cv.index]]
print("far-from-home cells revisited on >=3 distinct trips:", (far >= 3).sum(), "| top:", far.sort_values(ascending=False).head(5).to_dict())

# 2) Where does he lean hardest? cells by mean lean when moving, with support
mv = d[d.v > 20]
lc = mv.groupby("cell_c").agg(lean=("lean", "mean"), n=("lean", "size"), trips=("trip", "nunique"), v=("v", "mean"), elev=("positionmapmatchedelevation", "mean"))
lc = lc[lc.n > 30]
print("\n== 2 LEAN HOTSPOTS (1km cells, >30pts): lean>15 cells", (lc.lean > 15).sum(), "of", len(lc))
print(lc.sort_values("lean", ascending=False).head(6).round(1).to_string())
print("corr(lean cell, revisit trips)", lc[["lean", "trips"]].corr().iloc[0, 1].round(3), "| corr(lean, elev)", lc[["lean", "elev"]].corr().iloc[0, 1].round(3))

# 3) Stops mid-ride away from start/end = viewpoints/cafes (dwell >3 min, speed<1)
stops = []
for tid, g in d.groupby("trip"):
    g = g.sort_values("timestampinmillis")
    still = (g.v < 1).astype(int)
    grp = (still.diff() != 0).cumsum()
    for k, s in g[still == 1].groupby(grp[still == 1]):
        dur = (s.timestampinmillis.iloc[-1] - s.timestampinmillis.iloc[0]) / 60000
        pos = (s.index[0] - g.index[0]) / len(g)
        if dur >= 3 and 0.05 < pos < 0.95:
            stops.append(dict(trip=tid, dur=dur, lat=s.positionmapmatchedlatitude.iloc[0], lon=s.positionmapmatchedlongitude.iloc[0], elev=s.positionmapmatchedelevation.iloc[0], pos=pos))
st = pd.DataFrame(stops)
print("\n== 3 MID-RIDE STOPS >=3min:", len(st), "in", st.trip.nunique(), "rides | dur p50/max", st.dur.median().round(1), st.dur.max().round(1), "| elev>1000m stops", (st.elev > 1000).sum())
print(st.sort_values("dur", ascending=False).head(5).round(3).to_string())

# 4) Per-ride 'engagement' profile: does lean/throttle intensity differ tour vs commute?
r = d.groupby("trip").agg(km=("ridingtrip1", lambda s: (s.max() - s.min()) / 1000), lean_p90=("lean", lambda s: s.quantile(.9)),
                          lean20=("lean", lambda s: (s > 20).mean()), thr_p90=("ridingthrottlevalue", lambda s: s.quantile(.9)),
                          v_p90=("v", lambda s: s.quantile(.9)), elev_gain=("positionmapmatchedelevation", lambda s: np.clip(s.diff(), 0, 50).sum()),
                          hour=("t", lambda s: s.iloc[0].hour), dow=("t", lambda s: s.iloc[0].dayofweek))
r["kind"] = np.where(r.km > 60, "tour", np.where(r.km < 15, "short", "mid"))
print("\n== 4 RIDE TYPES\n", r.groupby("kind")[["km", "lean_p90", "lean20", "thr_p90", "v_p90", "elev_gain"]].median().round(2).to_string(), "\ncounts", r.kind.value_counts().to_dict())
print("weekend share: tour", (r[r.kind == "tour"].dow >= 5).mean().round(2), "short", (r[r.kind == "short"].dow >= 5).mean().round(2))
print("corr km~lean20", r[["km", "lean20"]].corr().iloc[0, 1].round(2), "elev_gain~lean20", r[["elev_gain", "lean20"]].corr().iloc[0, 1].round(2))

# 5) Curvature preference vs. available: on tours, heading change rate distribution
mv = d[(d.v > 20)].sort_values(["trip", "timestampinmillis"])
h = mv.groupby("trip").positionmapmatchedheading.diff().abs(); h = np.minimum(h, 360 - h)
mv = mv.assign(turn=h)
tw = mv.groupby("trip").turn.mean()
print("\n== 5 TWISTINESS (mean |heading change|/s when moving) p10/p50/p90:", tw.quantile([.1, .5, .9]).round(2).tolist())
print("corr twistiness~lean_p90", pd.concat([tw, r.lean_p90], axis=1).corr().iloc[0, 1].round(2))

# 6) Planned vs recorded: how often did he plan 'winding' and are planned dests re-used
names = collections.Counter()
for g in glob.glob(B + "plannedRoutes/*.gpx"):
    root = ET.parse(g).getroot(); ns = {"g": "http://www.topografix.com/GPX/1/1"}
    for p in root.findall(".//g:rtept", ns):
        n = p.find("g:name", ns)
        if n is not None and n.text: names[n.text.strip()] += 1
print("\n== 6 PLANNED ROUTE POINT NAMES reused >=3x:", [(k, v) for k, v in names.most_common(12) if v >= 3])
