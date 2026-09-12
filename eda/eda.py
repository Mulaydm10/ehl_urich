import pandas as pd, numpy as np, glob, xml.etree.ElementTree as ET, collections
B = "/home/ubuntu/bmw/data/exampleUserA/exampleUserA/"
m = pd.read_csv(glob.glob(B + "recordedTrips/cloud*.csv")[0])
m["start"] = pd.to_datetime(m.startTimestamp, unit="s")
print("== RIDES", len(m), "| years", m.start.dt.year.value_counts().sort_index().to_dict())
print("month", m.start.dt.month.value_counts().sort_index().to_dict())
print("weekday(0=Mon)", m.start.dt.dayofweek.value_counts().sort_index().to_dict())
print("start hour", m.start.dt.hour.value_counts().sort_index().to_dict())
km = m.rideDistance / 1000
print("dist km: <10", (km < 10).sum(), "10-50", ((km >= 10) & (km < 50)).sum(), "50-150", ((km >= 50) & (km < 150)).sum(), ">150", (km >= 150).sum(), "max", km.max())
print("avg speed kmh p50/p90", m.speedAverageKmh.median().round(1), m.speedAverageKmh.quantile(.9).round(1), "| max speed p50/max", m.speedMaxKmh.median(), m.speedMaxKmh.max())
print("lean max L/R p50/p90/max", m.leanAngleLeftMax.quantile([.5, .9, 1]).round(1).tolist(), m.leanAngleRightMax.quantile([.5, .9, 1]).round(1).tolist())
print("rides with lean>35:", ((m.leanAngleLeftMax > 35) | (m.leanAngleRightMax > 35)).sum())
print("elev gain proxy (max-min) p50/max", (m.elevationMaxM - m.elevationMinM).median().round(0), (m.elevationMaxM - m.elevationMinM).max().round(0))
print("bikes", m.bikeId.nunique(), "top bike share", m.bikeId.value_counts(normalize=True).iloc[0].round(2), "favorites", int(m.isFavorite.fillna(0).astype(bool).sum()))
print("temp min/max C", m.temperatureMinC.min(), m.temperatureMaxC.max())
# same start/end (loops) vs A->B
loop = (np.hypot(m.startLat - m.endLat, m.startLon - m.endLon) < 0.02)
print("loop rides (start≈end)", loop.sum(), "A->B", (~loop).sum())
print("start clusters (rounded 0.1deg)", collections.Counter(zip(m.startLat.round(1), m.startLon.round(1))).most_common(4))

# trackpoints
fs = [f for f in glob.glob(B + "recordedTrips/*.csv") if "cloud" not in f]
rows = []
for f in fs:
    d = pd.read_csv(f)
    d = d[(d.positionmapmatchedlatitude != 0)]
    v = d.ridingvehiclespeed * 3.6
    lean = d.sensorsbankingangle.abs()
    mov = v > 5
    rows.append(dict(
        n=len(d), moving=mov.mean(), stop_frac=(v < 1).mean(),
        lean_p90=lean[mov].quantile(.9) if mov.any() else np.nan,
        lean_gt20=(lean[mov] > 20).mean() if mov.any() else np.nan,
        lean_gt30=(lean[mov] > 30).mean() if mov.any() else np.nan,
        thr_p90=d.ridingthrottlevalue[mov].quantile(.9) if mov.any() else np.nan,
        thr_full=(d.ridingthrottlevalue > 80).mean(),
        rpm_p90=d.ridingenginespeed[mov].quantile(.9) if mov.any() else np.nan,
        gear_top=(d.ridinggear >= 5).mean(),
        v_gt100=(v > 100).mean(), v_gt130=(v > 130).mean(),
        abs_ev=(d.ridingabsbraking >= 2).sum(), asc_ev=(d.ridingasccontrol >= 2).sum(),
        hard_brake=(d.sensorsaccelerationlongitudinal < -0.5).sum(),
        elev_gain=np.clip(d.positionmapmatchedelevation.diff(), 0, 50).sum(),
        abs_codes=d.ridingabsbraking.value_counts().to_dict(), asc_codes=d.ridingasccontrol.value_counts().to_dict(),
    ))
t = pd.DataFrame(rows)
print("\n== TRACKPOINT STYLE (per ride medians / totals)")
print(t.drop(columns=["abs_codes", "asc_codes"]).median().round(3).to_string())
print("ABS events total", t.abs_ev.sum(), "rides w/ ABS", (t.abs_ev > 0).sum(), "| ASC events", t.asc_ev.sum(), "rides", (t.asc_ev > 0).sum())
print("ABS code union", collections.Counter(sum([list(c.keys()) for c in t.abs_codes], [])), "ASC code union", collections.Counter(sum([list(c.keys()) for c in t.asc_codes], [])))
print("hard brake events total", t.hard_brake.sum(), "| speed>130 frac overall", t.v_gt130.mean().round(4))
print("lean>30 frac range across rides", t.lean_gt30.min().round(3), t.lean_gt30.max().round(3))

# GPX prefs
opts = collections.Counter(); avoid = collections.Counter(); npts = []
for g in glob.glob(B + "plannedRoutes/*.gpx"):
    r = ET.parse(g).getroot(); ns = {"g": "http://www.topografix.com/GPX/1/1", "c": "http://www.bmw-motorrad.com/CNRD/1/0"}
    ro = r.find(".//c:routeOptions", ns)
    if ro is not None:
        for k, v in ro.attrib.items(): opts[(k, v)] += 1
        av = ro.find("c:avoidances", ns)
        if av is not None:
            for k, v in av.attrib.items(): avoid[(k, v)] += 1
    npts.append((len(r.findall("g:wpt", ns)), len(r.findall(".//g:rtept", ns)), len(r.findall(".//g:trkpt", ns))))
print("\n== GPX", len(npts), "routeOptions", dict(opts))
print("avoidances", dict(avoid))
print("pts median wpt/rtept/trkpt", np.median(npts, axis=0), "max", np.max(npts, axis=0))
