import pandas as pd, numpy as np, glob, sys, os
from multiprocessing import Pool
F = "/home/ubuntu/bmw/full/"
COLS = ["timestampinmillis", "positionmapmatchedlatitude", "positionmapmatchedlongitude", "positionmapmatchedelevation", "positionmapmatchedheading",
        "ridingvehiclespeed", "ridingthrottlevalue", "ridingenginespeed", "sensorsbankingangle", "sensorsaccelerationlongitudinal", "ridingabsbraking", "ridingasccontrol", "ridingtrip1", "sensorsoutsidetemperature"]

def trip(f):
    try:
        d = pd.read_csv(f, usecols=lambda c: c in COLS)
    except Exception:
        return None
    d = d[d.positionmapmatchedlatitude != 0]
    if len(d) < 30: return None
    d = d.sort_values("timestampinmillis")
    v = d.ridingvehiclespeed.values * 3.6; lean = np.abs(d.sensorsbankingangle.values)
    mv = v > 20
    h = np.diff(d.positionmapmatchedheading.values); h = np.abs((h + 180) % 360 - 180)
    dt = np.diff(d.timestampinmillis.values) / 1000
    ok = (dt > 0) & (dt < 5) & mv[1:]
    turn = (h[ok] / dt[ok]) if ok.sum() else np.array([0.])
    # corner beats: lean crossing >12deg
    peaks = ((lean[1:-1] > 12) & (lean[1:-1] >= lean[:-2]) & (lean[1:-1] > lean[2:])).sum()
    dur = (d.timestampinmillis.iloc[-1] - d.timestampinmillis.iloc[0]) / 60000
    hrs = pd.to_datetime(d.timestampinmillis.iloc[0], unit="ms")
    # per-cell aggregates (1km)
    cell = (d.positionmapmatchedlatitude.round(2) * 100).astype(int).astype(str) + "_" + (d.positionmapmatchedlongitude.round(2) * 100).astype(int).astype(str)
    cells = pd.DataFrame({"cell": cell.values, "lean": lean, "v": v, "mv": mv, "elev": d.positionmapmatchedelevation.values})
    cells = cells[cells.mv].groupby("cell").agg(n=("lean", "size"), lean=("lean", "mean"), lean20=("lean", lambda s: (s > 20).mean()), v=("v", "mean"), elev=("elev", "mean")).reset_index()
    cells["trips"] = 1
    r = dict(f=os.path.basename(f), n=len(d), mins=dur, km=(d.ridingtrip1.max() - d.ridingtrip1.min()) / 1000 if "ridingtrip1" in d else np.nan,
             v_mean=v[mv].mean() if mv.sum() else 0, v_p90=np.percentile(v, 90), stop=(v < 1).mean(),
             lean_p90=np.percentile(lean, 90), lean20=(lean > 20).mean(), lean_max=lean.max(), thr_p90=d.ridingthrottlevalue.quantile(.9),
             rpm_p90=d.ridingenginespeed.quantile(.9), turn=turn.mean(), cpm=peaks / max(dur, 1),
             elev_gain=np.clip(np.diff(d.positionmapmatchedelevation.values), 0, 50).sum(), elev_max=d.positionmapmatchedelevation.max(),
             hour=hrs.hour, month=hrs.month, lat0=d.positionmapmatchedlatitude.iloc[0], lon0=d.positionmapmatchedlongitude.iloc[0],
             loop=np.hypot(d.positionmapmatchedlatitude.iloc[0] - d.positionmapmatchedlatitude.iloc[-1], d.positionmapmatchedlongitude.iloc[0] - d.positionmapmatchedlongitude.iloc[-1]) * 111 < 1,
             abs_nz=(d.ridingabsbraking > 0).mean(), asc_vals=tuple(sorted(d.ridingasccontrol.unique()))[:6], temp=d.sensorsoutsidetemperature.replace(0, np.nan).median())
    return r, cells

if __name__ == "__main__":
    src, out, lim = sys.argv[1], sys.argv[2], int(sys.argv[3])
    fs = sorted(glob.glob(F + src + "/**/*.csv", recursive=True))
    if "example" in src: fs = [f for f in fs if "cloud" not in f]
    fs = fs[:lim]
    with Pool(8) as p: res = [r for r in p.imap_unordered(trip, fs, chunksize=20) if r]
    T = pd.DataFrame([r for r, c in res]); T.to_parquet(out + "_trips.parquet")
    C = pd.concat([c for r, c in res]).groupby("cell").agg(n=("n", "sum"), trips=("trips", "sum"), lean=("lean", "mean"), lean20=("lean20", "mean"), v=("v", "mean"), elev=("elev", "mean")).reset_index()
    C.to_parquet(out + "_cells.parquet"); print(src, len(T), "trips", len(C), "cells")
