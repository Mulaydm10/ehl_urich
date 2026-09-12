"""Deep checks: ABS/ASC event semantics, the physics bridge done properly, planned-route ground truth."""
import glob
import os
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

OUT = r"F:\bmw\analysis\out"
RAW = r"F:\bmw\data\raw\exampleUserA_x\exampleUserA"
G = 9.81
pd.set_option("display.width", 200)

df = pd.read_parquet(os.path.join(OUT, "userA_all.parquet")).sort_values(["_file", "timestampinmillis"])
gb = df.groupby("_file")
df["dt"] = gb["timestampinmillis"].diff() / 1000.0
dh = ((gb["positionmapmatchedheading"].diff() + 180) % 360) - 180
df["yaw"] = np.radians(dh) / df["dt"]
df.loc[df["dt"] > 5, "yaw"] = np.nan
df["v"] = df["ridingvehiclespeed"]
mov = (df["v"] > 5) & df["dt"].between(0.8, 1.3)

print("=" * 96)
print("1. ABS / ASC  - what do the status codes actually mean?")
print("=" * 96)
for c in ["ridingabsbraking", "ridingasccontrol"]:
    vc = df[c].value_counts().sort_index()
    print("\n  %s value counts (all points):" % c)
    for k, n in vc.items():
        print("      %d : %10s  (%.2f%%)" % (k, f"{n:,}", 100 * n / len(df)))
    mv = df.loc[mov, c]
    print("    while moving >18 km/h: %s" % {int(k): round(100 * v, 2) for k, v in (mv.value_counts(normalize=True) * 100).items()})
    # rides where the high codes ever appear
    hi = df.groupby("_file")[c].max()
    print("    rides where max code >= 2: %d of %d" % ((hi >= 2).sum(), len(hi)))
    print("    rides where max code == 3: %d of %d" % ((hi == 3).sum(), len(hi)))

print("\n  Interpretation: the modal code while moving is the 'system armed, not intervening' state.")
print("  Rarer codes are candidate INTERVENTION events - the per-km rate of those is the new feature.")

print()
print("=" * 96)
print("2. THE PHYSICS BRIDGE, done properly (per-corner, errors-in-variables)")
print("=" * 96)
d = df[mov & df["yaw"].notna() & df["sensorsbankingangle"].notna()].copy()
d["theta_req"] = np.degrees(np.arctan(d["v"] * d["yaw"] / G))
d = d[d["theta_req"].abs() < 60]
d["lean"] = d["sensorsbankingangle"]

# naive OLS both ways + sd-ratio (the errors-in-variables slope when noise is symmetric)
b_fwd = np.polyfit(d["theta_req"], d["lean"], 1)[0]
b_rev = np.polyfit(d["lean"], d["theta_req"], 1)[0]
sd_ratio = d["lean"].std() / d["theta_req"].std()
print("\n  point level: n=%s  corr=%.3f" % (f"{len(d):,}", d["theta_req"].corr(d["lean"])))
print("    OLS lean~req slope = %.3f | OLS req~lean slope = %.3f | geometric-mean slope = %.3f | sd ratio = %.3f"
      % (b_fwd, b_rev, np.sqrt(b_fwd / b_rev), sd_ratio))

# aggregate into CORNERS: contiguous runs of same-sign yaw above a threshold
d["corner_sign"] = np.sign(d["yaw"]).where(d["yaw"].abs() > 0.04, 0)
d["blk"] = (d["corner_sign"] != d.groupby("_file")["corner_sign"].shift()).cumsum()
cor = d[d["corner_sign"] != 0].groupby(["_file", "blk"]).agg(
    n=("lean", "size"), req=("theta_req", lambda s: s.abs().max()),
    lean=("lean", lambda s: s.abs().max()), v=("v", "mean"), sign=("corner_sign", "first"))
cor = cor[cor.n >= 3]
print("\n  corner level: %s corners of >=3 s   (median %.0f km/h)" % (f"{len(cor):,}", 3.6 * cor.v.median()))
print("    corr(required, measured) = %.3f" % cor["req"].corr(cor["lean"]))
bf = np.polyfit(cor["req"], cor["lean"], 1)
print("    fit measured = %.3f * required %+.2f ; sd ratio = %.3f" % (bf[0], bf[1], cor["lean"].std() / cor["req"].std()))
for lo, hi in [(5, 10), (10, 20), (20, 30), (30, 60)]:
    s = cor[(cor["req"] >= lo) & (cor["req"] < hi)]
    if len(s) > 30:
        print("      required %2d-%2d deg : n=%5d  measured lean median %5.1f deg  (ratio %.2f)"
              % (lo, hi, len(s), s["lean"].median(), s["lean"].median() / s["req"].median()))

print("\n  left vs right corners, same rider:")
for s, nm in [(-1, "LEFT "), (1, "RIGHT")]:
    c = cor[cor["sign"] == s]
    print("    %s n=%5d  measured p50=%5.1f p95=%5.1f deg   required p50=%5.1f p95=%5.1f"
          % (nm, len(c), c["lean"].quantile(.5), c["lean"].quantile(.95), c["req"].quantile(.5), c["req"].quantile(.95)))

print()
print("=" * 96)
print("3. PLANNED ROUTES (GPX) - the revealed-preference ground truth")
print("=" * 96)
gpx = [p for p in glob.glob(os.path.join(RAW, "plannedRoutes", "*.gpx")) if not os.path.basename(p).startswith("._")]
rows = []
for p in gpx:
    try:
        t = ET.parse(p).getroot()
    except Exception:
        continue
    ns = {"g": re.match(r"\{(.*)\}", t.tag).group(1)} if t.tag.startswith("{") else {}
    q = (lambda x: "g:" + x) if ns else (lambda x: x)
    wpt = t.findall(".//" + q("wpt"), ns)
    rte = t.findall(".//" + q("rtept"), ns)
    trk = t.findall(".//" + q("trkpt"), ns)
    pts = [(float(e.get("lat")), float(e.get("lon"))) for e in (trk or rte or wpt)]
    if len(pts) > 1:
        a = np.array(pts)
        dd = np.sqrt((np.diff(a[:, 0]) * 111320) ** 2 + (np.diff(a[:, 1]) * 111320 * np.cos(np.radians(a[:, 0][:-1]))) ** 2)
        km = dd.sum() / 1000
        loop = np.hypot((a[0, 0] - a[-1, 0]) * 111320, (a[0, 1] - a[-1, 1]) * 111320) < 2000
    else:
        km, loop = np.nan, False
    rows.append({"file": os.path.basename(p), "wpt": len(wpt), "rtept": len(rte), "trkpt": len(trk),
                 "km": km, "loop": loop, "name": os.path.basename(p)[:-4]})
r = pd.DataFrame(rows)
print("\n  %d planned routes parsed" % len(r))
print("  point types: wpt(destinations) median %.0f | rtept median %.0f | trkpt(shaping) median %.0f"
      % (r.wpt.median(), r.rtept.median(), r.trkpt.median()))
print("  routes containing shaping/supporting points (trkpt>0): %d of %d  <- deliberate road choice" % ((r.trkpt > 0).sum(), len(r)))
print("  length km: p25=%.0f median=%.0f p75=%.0f max=%.0f" % (r.km.quantile(.25), r.km.median(), r.km.quantile(.75), r.km.max()))
print("  ROUND TRIPS (start within 2 km of end): %d of %d  = %.0f%%   <- BMW use case #2 is what this rider actually plans"
      % (r.loop.sum(), len(r), 100 * r.loop.mean()))
print("\n  sample route names (riders name routes after what they value):")
for n in r.sort_values("km", ascending=False).name.head(12):
    print("     ", n)
r.to_csv(os.path.join(OUT, "planned_routes.csv"), index=False)

print()
print("=" * 96)
print("4. WHERE AND WHEN DOES THIS RIDER RIDE?  (does the data contain fun roads at all)")
print("=" * 96)
man = pd.read_csv(glob.glob(os.path.join(RAW, "recordedTrips", "cloudRecordedTracks-*.csv"))[0])
man["ts"] = pd.to_datetime(pd.to_numeric(man["startTimestamp"], errors="coerce"), unit="s")
man["dist_km"] = pd.to_numeric(man["rideDistance"], errors="coerce") / 1000
man["elev_range"] = pd.to_numeric(man["elevationMaxM"], errors="coerce") - pd.to_numeric(man["elevationMinM"], errors="coerce")
print("\n  date range: %s to %s (%.1f years of history)" %
      (man.ts.min().date(), man.ts.max().date(), (man.ts.max() - man.ts.min()).days / 365))
print("  weekday share: %.0f%% weekend rides" % (100 * man.ts.dt.dayofweek.ge(5).mean()))
print("  rides with >500 m of elevation range (mountain rides): %d of %d" % ((man.elev_range > 500).sum(), len(man)))
print("  rides >100 km: %d | 20-100 km: %d | <20 km (commute-ish): %d"
      % ((man.dist_km > 100).sum(), man.dist_km.between(20, 100).sum(), (man.dist_km < 20).sum()))
lat = pd.to_numeric(man["startLat"], errors="coerce")
lon = pd.to_numeric(man["startLon"], errors="coerce")
print("  start bbox: lat %.2f-%.2f  lon %.2f-%.2f" % (lat.min(), lat.max(), lon.min(), lon.max()))
print("  alpine rides (max elevation > 1200 m): %d" % (pd.to_numeric(man["elevationMaxM"], errors="coerce") > 1200).sum())
