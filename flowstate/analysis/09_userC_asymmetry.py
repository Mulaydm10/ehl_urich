"""Does a SECOND rider show the left/right lean asymmetry? User A did not.

Uses the corrected recipe from HANDOFF entry 3b:
  - positionrawheading (not map-matched: map-matched is quantised, 38% zero-yaw)
  - corner-level p95, not per-ride maxima
  - cluster bootstrap on RIDE, because corners within a ride are not independent
  - side-stand guard: drop lean below 0.5 m/s
  - GPS-derived speed fallback (27% of user A's rides have no speed channel at all)
"""
import glob
import os

import numpy as np
import pandas as pd

G = 9.81
SRC = r"F:\bmw\data\raw\salvaged\exampleUserC\recordedTrips"
OUT = r"F:\bmw\analysis\out"


def corners_for_ride(path):
    d = pd.read_csv(path, low_memory=False).sort_values("timestampinmillis")
    if len(d) < 60:
        return None
    d["dt"] = d.timestampinmillis.diff() / 1000.0
    v = d.ridingvehiclespeed.astype(float)
    if v.max() <= 0:                                   # dead speed channel -> GPS fallback
        v = d.positionmapmatchedspeed.astype(float)
    if v.max() <= 0:
        lat, lon = d.positionmapmatchedlatitude, d.positionmapmatchedlongitude
        step = np.hypot(lat.diff() * 111320, lon.diff() * 111320 * np.cos(np.radians(lat.clip(-89, 89))))
        v = (step / d.dt).clip(0, 70)
    d["v"] = v
    d["lean"] = d.sensorsbankingangle.where(d.v > 0.5)
    hd = d.positionrawheading.where(d.positionrawheading > 0)
    dh = ((hd.diff() + 180) % 360) - 180
    d["yaw"] = np.radians(dh) / d.dt
    d.loc[d.dt > 5, "yaw"] = np.nan
    m = (d.v > 5) & d.dt.between(0.8, 1.3) & d.yaw.notna() & d.lean.notna()
    d = d[m].copy()
    if len(d) < 30:
        return None
    d["req"] = np.degrees(np.arctan(d.v * d.yaw / G))
    d = d[d.req.abs() < 60]
    d["sgn"] = np.sign(d.yaw).where(d.yaw.abs() > 0.04, 0)
    d["blk"] = (d.sgn != d.sgn.shift()).cumsum()
    c = d[d.sgn != 0].groupby("blk").agg(n=("lean", "size"), req=("req", lambda s: s.abs().max()),
                                         lean=("lean", lambda s: s.abs().max()), sgn=("sgn", "first"),
                                         v=("v", "mean"), lat=("positionmapmatchedlatitude", "mean"),
                                         lon=("positionmapmatchedlongitude", "mean"),
                                         elev=("positionrawelevation", "mean"))
    c = c[(c.n >= 3) & c.req.between(3, 55)]
    if len(c) < 5:
        return None
    c["ride"] = os.path.basename(path)[:8]
    return c


files = [p for p in glob.glob(os.path.join(SRC, "*.csv")) if not os.path.basename(p).startswith("._")]
print("user C: %d ride files" % len(files))
parts = []
for i, p in enumerate(files):
    try:
        c = corners_for_ride(p)
    except Exception:
        c = None
    if c is not None:
        parts.append(c)
    if (i + 1) % 50 == 0:
        print("  parsed %d/%d -> %d rides with usable corners" % (i + 1, len(files), len(parts)), flush=True)
cor = pd.concat(parts, ignore_index=True)
print("\nuser C corner table: %s corners across %d rides" % (f"{len(cor):,}", cor.ride.nunique()))
print("  median corner: %.0f km/h, %.1f deg required, %.1f deg used, elevation %.0f m"
      % (3.6 * cor.v.median(), cor.req.median(), cor.lean.median(), cor.elev.median()))

L = cor[cor.sgn < 0]
R = cor[cor.sgn > 0]
print("\n  LEFT  corners n=%5d  lean p50=%5.1f  p95=%5.1f   (required p50 %.1f)"
      % (len(L), L.lean.quantile(.5), L.lean.quantile(.95), L.req.quantile(.5)))
print("  RIGHT corners n=%5d  lean p50=%5.1f  p95=%5.1f   (required p50 %.1f)"
      % (len(R), R.lean.quantile(.5), R.lean.quantile(.95), R.req.quantile(.5)))
point = L.lean.quantile(.95) - R.lean.quantile(.95)
print("\n  POINT ESTIMATE  L-R (p95) = %+.2f deg" % point)

# cluster bootstrap on ride
rides = cor.ride.unique()
by = {r: g for r, g in cor.groupby("ride")}
rng = np.random.default_rng(0)
bs = []
for _ in range(4000):
    s = rng.choice(rides, len(rides), replace=True)
    g = pd.concat([by[r] for r in s], ignore_index=True)
    l, r_ = g[g.sgn < 0].lean, g[g.sgn > 0].lean
    if len(l) > 50 and len(r_) > 50:
        bs.append(l.quantile(.95) - r_.quantile(.95))
bs = np.array(bs)
lo, hi = np.percentile(bs, [2.5, 97.5])
sig = (lo > 0) or (hi < 0)
print("  CLUSTER BOOTSTRAP on %d rides: 95%% CI [%+.2f, %+.2f]  -> %s"
      % (len(rides), lo, hi, "SIGNIFICANT" if sig else "NOT significant"))
if sig:
    side = "LEFT" if point > 0 else "RIGHT"
    print("\n  >>> USER C IS ASYMMETRIC: %.1f deg stronger on %s-handers." % (abs(point), side))
    print("  >>> Route loops so this rider gets more %s-hand corners. This is the demo moment." % side)
else:
    print("\n  >>> User C is NOT significantly asymmetric either. Two riders, no effect:")
    print("  >>> present the METHOD and the interval, never the claim.")
cor.to_parquet(os.path.join(OUT, "userC_corners.parquet"))
print("\nwrote out/userC_corners.parquet")
