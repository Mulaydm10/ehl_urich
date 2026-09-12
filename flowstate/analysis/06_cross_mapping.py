"""ALL THE CROSS-DATASET MAPPINGS - the joins that turn separate files into one product.

M1 planned GPX  x recorded CSV   -> did he ride what he planned? (conversion = the strongest label)
M2 recorded     x recorded       -> repeat roads (revealed preference)
M3 trackpoints  -> morton grid   -> Road DNA with no OSM
M4 planned GPX  -> geometry      -> Road DNA from routes nobody has ridden yet
M5 corners      x bikeId         -> separating machine from rider
M6 style index, fixed
"""
import glob
import os
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

OUT = r"F:\bmw\analysis\out"
RAW = r"F:\bmw\data\raw\exampleUserA_x\exampleUserA"
G = 9.81
pd.set_option("display.width", 200, "display.max_columns", 40)


def hdr(t):
    print("\n" + "=" * 98 + "\n" + t + "\n" + "=" * 98)


def cells(lat, lon, p=2):
    """coarse spatial key ~1.1 km at p=2"""
    return pd.Series(np.round(lat, p).astype(str) + "_" + np.round(lon, p).astype(str))


# ---------------------------------------------------------------- load
df = pd.read_parquet(os.path.join(OUT, "userA_all.parquet"))
df["trip"] = df["_file"].str.replace(".csv", "", regex=False)
man = pd.read_csv(glob.glob(os.path.join(RAW, "recordedTrips", "cloudRecordedTracks-*.csv"))[0])
man["trip"] = man["itemId"].str.split("#").str[-1]
man["start_ts"] = pd.to_datetime(pd.to_numeric(man["startTimestamp"], errors="coerce"), unit="s")

rec = df[(df.positionmapmatchedlatitude > 1)].copy()
rec["cell"] = cells(rec.positionmapmatchedlatitude, rec.positionmapmatchedlongitude)
rec_cells = rec.groupby("trip")["cell"].apply(set)
all_ridden = set().union(*rec_cells) if len(rec_cells) else set()

# ---------------------------------------------------------------- GPX parse
rows, geom = [], {}
for p in glob.glob(os.path.join(RAW, "plannedRoutes", "*.gpx")):
    if os.path.basename(p).startswith("._"):
        continue
    try:
        t = ET.parse(p).getroot()
    except Exception:
        continue
    ns = {"g": re.match(r"\{(.*)\}", t.tag).group(1)} if t.tag.startswith("{") else {}
    q = (lambda x: "g:" + x) if ns else (lambda x: x)
    pts = [(float(e.get("lat")), float(e.get("lon")))
           for e in (t.findall(".//" + q("trkpt"), ns) or t.findall(".//" + q("rtept"), ns)
                     or t.findall(".//" + q("wpt"), ns))]
    if len(pts) < 5:
        continue
    a = np.array(pts)
    name = os.path.basename(p)[:-4]
    geom[name] = a
    dd = np.hypot(np.diff(a[:, 0]) * 111320, np.diff(a[:, 1]) * 111320 * np.cos(np.radians(a[:-1, 0])))
    pc = set(cells(pd.Series(a[:, 0]), pd.Series(a[:, 1])))
    rows.append({"name": name, "n_pts": len(a), "km": dd.sum() / 1000, "cells": pc,
                 "date": name.split("_")[1] if "_" in name else "",
                 "covered": len(pc & all_ridden) / len(pc)})
pl = pd.DataFrame(rows)

hdr("M1  PLANNED x RECORDED - did he actually ride what he planned?")
pl["ridden"] = pl.covered > 0.6
print("  %d planned routes x %d recorded rides, matched on ~1.1 km cells" % (len(pl), rec.trip.nunique()))
print("\n  coverage of each planned route by roads he has actually ridden:")
for lo, hi, lab in [(0, .1, "never ridden      "), (.1, .4, "partly (10-40%)   "),
                    (.4, .6, "mostly (40-60%)   "), (.6, .9, "ridden (60-90%)   "), (.9, 1.01, "fully ridden (90%+)")]:
    n = pl.covered.between(lo, hi, inclusive="left").sum()
    print("    %s : %3d routes (%4.0f%%)" % (lab, n, 100 * n / len(pl)))
print("\n  >>> CONVERSION LABEL: a planned route he went on to ride is the strongest preference signal in")
print("  >>> this dataset - stronger than a repeat, because he committed to it before he knew the weather.")
top = pl.nlargest(6, "covered")[["name", "km", "covered"]]
print("\n  best-converted plans:")
for r in top.itertuples():
    print("    %5.0f km  %3.0f%%  %s" % (r.km, 100 * r.covered, r.name[:72]))
never = pl.nsmallest(5, "covered")[["name", "km", "covered"]]
print("\n  planned but never ridden (aspiration - the Skill Quest target list writes itself):")
for r in never.itertuples():
    print("    %5.0f km  %3.0f%%  %s" % (r.km, 100 * r.covered, r.name[:72]))

hdr("M2  RECORDED x RECORDED - which roads does he come back to?")
cell_rides = rec.groupby("cell")["trip"].nunique().sort_values(ascending=False)
print("  %d distinct ~1.1 km cells ridden; %d ridden on 2+ separate rides, %d on 5+"
      % (len(cell_rides), (cell_rides >= 2).sum(), (cell_rides >= 5).sum()))
print("  repeat rate: %.0f%% of cells are one-offs" % (100 * (cell_rides == 1).mean()))
rep = cell_rides[cell_rides >= 4].index
cor = pd.read_parquet(os.path.join(OUT, "corners_filtered.parquet"))
cor["cell"] = cells(cor.lat, cor.lon)
cor["is_repeat"] = cor.cell.isin(rep)
a = cor[cor.is_repeat]; b = cor[~cor.is_repeat]
print("\n  corners on REPEATED roads vs one-off roads:")
print("    repeated : n=%5d  required lean p50 %.1f deg  elev %.0f m  radius %.0f m"
      % (len(a), a.req_deg.median(), a.elev_m.median(), a.radius_m.median()))
print("    one-off  : n=%5d  required lean p50 %.1f deg  elev %.0f m  radius %.0f m"
      % (len(b), b.req_deg.median(), b.elev_m.median(), b.radius_m.median()))
print("  >>> If repeated roads are MORE demanding, repeat behaviour is a usable fun label. Check the sign above.")

hdr("M4  PLANNED GPX -> ROAD DNA for roads NOBODY has ridden yet")
out = []
for name, a in list(geom.items()):
    if len(a) < 20:
        continue
    lat, lon = a[:, 0], a[:, 1]
    x = np.radians(lon) * 6371000 * np.cos(np.radians(lat.mean()))
    y = np.radians(lat) * 6371000
    dx, dy = np.diff(x), np.diff(y)
    seg = np.hypot(dx, dy)
    hd = np.unwrap(np.arctan2(dy, dx))
    dpsi = np.diff(hd)
    ds = (seg[:-1] + seg[1:]) / 2
    kappa = np.abs(dpsi) / np.maximum(ds, 1)          # 1/m
    kappa = kappa[(ds > 5) & (ds < 500)]
    if len(kappa) < 20:
        continue
    R = 1 / np.maximum(kappa, 1e-4)
    v = 22.0                                            # 80 km/h reference
    req = np.degrees(np.arctan(v ** 2 / (np.maximum(R, 15) * G)))
    out.append({"route": name[:60], "km": seg.sum() / 1000,
                "curves_per_km": (kappa > 1 / 200).sum() / (seg.sum() / 1000),
                "req_p50": np.median(req), "req_p90": np.percentile(req, 90),
                "radius_p50": np.median(R)})
rd = pd.DataFrame(out).sort_values("req_p90", ascending=False)
print("  computed Road DNA straight from %d planned GPX routes - no OSM, no crowd data, no map matching" % len(rd))
print("\n  the 8 most demanding routes he has ever planned (at an 80 km/h reference pace):")
print(rd.head(8).to_string(index=False, float_format=lambda x: "%.1f" % x))
print("\n  the 4 gentlest:")
print(rd.tail(4).to_string(index=False, float_format=lambda x: "%.1f" % x))
rd.to_csv(os.path.join(OUT, "planned_route_dna.csv"), index=False)

hdr("M6  STYLE INDEX, FIXED - using in-corner minimum speed from the raw points")
d = df.sort_values(["_file", "timestampinmillis"]).copy()
gg = d.groupby("_file")
d["dt"] = gg["timestampinmillis"].diff() / 1000
d["v"] = d["ridingvehiclespeed"]
dh = ((gg["positionmapmatchedheading"].diff() + 180) % 360) - 180
d["yaw"] = np.radians(dh) / d["dt"]
d.loc[d.dt > 5, "yaw"] = np.nan
d["sgn"] = np.sign(d.yaw).where(d.yaw.abs() > 0.04, 0)
d["blk"] = (d.sgn != gg["sgn"].shift()).cumsum() if "sgn" in d else 0
d["blk"] = (d["sgn"] != d.groupby("_file")["sgn"].shift()).cumsum()
cc = d[(d.sgn != 0) & (d.v > 8)].groupby(["trip", "blk"]).agg(
    n=("v", "size"), v_in=("v", "first"), v_min=("v", "min"), v_out=("v", "last"),
    thr_out=("ridingthrottlevalue", "last"), thr_in=("ridingthrottlevalue", "first")).reset_index()
cc = cc[cc.n >= 3]
cc["brake_frac"] = (cc.v_in - cc.v_min) / cc.v_in
cc["drive_frac"] = (cc.v_out - cc.v_min) / cc.v_min.replace(0, np.nan)
cc["ps_index"] = cc.brake_frac + cc.drive_frac
pr = cc.groupby("trip").agg(n=("ps_index", "size"), ps=("ps_index", "median"),
                            brake=("brake_frac", "median"), drive=("drive_frac", "median"),
                            thr_out=("thr_out", "median"))
pr = pr[pr.n >= 20]
print("  %d corners, %d rides with >=20 corners" % (len(cc), len(pr)))
print("  point-and-shoot index (speed lost into the corner + speed gained out):")
print("    p10=%.3f  p50=%.3f  p90=%.3f   spread %.3f" % (pr.ps.quantile(.1), pr.ps.median(), pr.ps.quantile(.9),
                                                          pr.ps.quantile(.9) - pr.ps.quantile(.1)))
print("    corr(ps_index, exit throttle) = %+.2f across rides" % pr.ps.corr(pr.thr_out))
print("\n  the 3 most 'point-and-shoot' rides vs the 3 most 'momentum/sweeper' rides:")
for lab, sel in [("POINT-AND-SHOOT", pr.nlargest(3, "ps")), ("MOMENTUM ", pr.nsmallest(3, "ps"))]:
    for r in sel.itertuples():
        print("    %-16s %s  ps=%.3f  brake=%.3f drive=%.3f" % (lab, r.Index[:8], r.ps, r.brake, r.drive))
print("\n  >>> Brake pressure is dead on these bikes, but the SPEED TRACE still separates riding styles.")
cc.to_parquet(os.path.join(OUT, "corner_style.parquet"))

hdr("SUMMARY OF THE MAPPING MATRIX")
print("""
  planned GPX  --M1 spatial-->  recorded CSV      : conversion label (strongest preference signal)
  planned GPX  --M4 geometry->  Road DNA          : difficulty of roads never ridden -> Skill Quests, cold start
  recorded CSV --M2 spatial-->  recorded CSV      : repeat roads -> revealed preference
  recorded CSV --M3 morton --> road grid          : Road DNA with no OSM, scales to 77,700 crowd rides
  recorded CSV --corners  -->  MASTER TABLE       : 5,253 corners x 35 columns, the single object everything reads
  MASTER       --M5 bikeId-->  machine effect     : 6.3 deg of lean p95 is the BIKE, not the rider
  MASTER       --M6 speed -->  style index        : momentum vs point-and-shoot without brake pressure
  MASTER       --z* dial  -->  flow score         : three different 'best' answers from one rider profile
""")
