"""
joy.py — measure fun on a ride, from telemetry alone.  (FEATURES F1.1, F2.6)

Every other module in app/ scores a ROAD before anybody rides it. This one
scores a RIDE after it happened, so the definition of fun stops being ours and
becomes something the bike reports. It is the outcome metric the later phases
(modes, Pareto) are judged against — which is why it has to pass its own test
before anything else is allowed to trust it (analysis/15_joy_meter.py).

Four components, each a RATE or a SHARE so that a longer ride does not score
higher just for being longer:

    E  grip envelope     area of the g-g polygon, per-sector p90 radius, in g^2
    R  lean reversals    sign changes of lean with |lean| > 5 deg, per km
    T  throttle entropy  Shannon entropy of throttle position, 0..1
    U  uninterrupted     share of distance covered above 15 km/h

    joy = mean of the z-scores of E, R, T, U against a reference set of rides

Two terms from the original design are deliberately NOT in joy:

    F  ride speed / crowd speed — it scores riding faster than the crowd, and
       we never score speed. Dropped, not down-weighted.
    C  completion / loop closure — commutes are one-way and weekend rides are
       loops, so it would separate them by route geometry rather than by fun
       and pass the test for the wrong reason. Kept as a descriptor only.

Why E is not a convex hull: a hull is set by its most extreme samples, so it
grows with the number of samples (longer rides win), and dividing it by km
flips that into "shorter rides win". Either way it measures length. The
per-sector p90 radius is a percentile, so it does neither.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

G = 9.80665
MIN_SPEED_MS = 0.5            # below this the lean channel is the side stand
GAP_SPLIT_S = 5.0             # a longer gap starts a new segment
TELEPORT_M = 500.0            # a longer GPS step is a fix jump, not riding
MAX_GPS_SPEED_MS = 70.0
REVERSAL_LEAN_DEG = 5.0
FLOWING_MS = 15.0 / 3.6
A_LONG_CLIP_G = 1.0           # raw channel reaches -2.6 g, which is not a motorcycle
N_SECTORS = 16
SECTOR_MIN_POINTS = 5
THROTTLE_BINS = 10

COMPONENTS = ("E_envelope", "R_reversals_km", "T_throttle_entropy", "U_uninterrupted")

TP_COLS = ["trip_id", "timestampinmillis", "positionrawlatitude", "positionrawlongitude",
           "ridingvehiclespeed", "sensorsbankingangle", "sensorsaccelerationlongitudinal",
           "ridingthrottlevalue", "ridingabsbraking"]


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def prepare(tp: pd.DataFrame) -> pd.DataFrame:
    """
    One ride -> a clean frame: t_s, dt, seg, step_m, cum_km, v_ms, moving,
    lean, a_long_g, throttle, abs.

    Speed: the bus channel when it is alive, otherwise GPS. On 27 of user A's
    100 rides every speed channel is flat zero; they are rescued, not dropped.
    """
    d = tp.sort_values("timestampinmillis").reset_index(drop=True)
    t = d["timestampinmillis"].to_numpy(dtype=float) / 1000.0
    lat = d["positionrawlatitude"].to_numpy(dtype=float)
    lon = d["positionrawlongitude"].to_numpy(dtype=float)

    dt = np.zeros(len(d))
    dt[1:] = np.diff(t)
    step = np.zeros(len(d))
    if len(d) > 1:
        step[1:] = _haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    gap = dt > GAP_SPLIT_S
    bad_fix = ((lat == 0) | (lon == 0))
    bad_fix = bad_fix | np.r_[False, bad_fix[:-1]]
    step[gap | bad_fix | (step > TELEPORT_M)] = 0.0
    seg = np.cumsum(gap)

    with np.errstate(divide="ignore", invalid="ignore"):
        v_gps = np.where((dt > 0) & ~gap, step / dt, np.nan)
    v_gps[v_gps > MAX_GPS_SPEED_MS] = np.nan

    v_bus = d["ridingvehiclespeed"].to_numpy(dtype=float)
    bus_ok = bool(np.nanmax(v_bus) > 1.0) if len(v_bus) else False
    v = v_bus if bus_ok else v_gps

    lean = d["sensorsbankingangle"].to_numpy(dtype=float)
    moving = np.nan_to_num(v) >= MIN_SPEED_MS

    thr = d["ridingthrottlevalue"].to_numpy(dtype=float)
    if np.nanmax(thr) <= 1.5:                 # a fraction, not a percentage
        thr = thr * 100.0

    return pd.DataFrame({
        "t_s": t - t[0] if len(t) else t, "dt": dt, "seg": seg, "step_m": step,
        "cum_km": np.cumsum(step) / 1000.0, "v_ms": v, "moving": moving,
        "lean": np.where(moving, lean, np.nan),
        "a_long_g": np.clip(d["sensorsaccelerationlongitudinal"].to_numpy(dtype=float),
                            -A_LONG_CLIP_G, A_LONG_CLIP_G),
        "throttle": np.clip(thr, 0.0, 100.0),
        "abs": d["ridingabsbraking"].to_numpy(),
        "lat": lat, "lon": lon,
    }).assign(bus_speed_ok=bus_ok)


def window(p: pd.DataFrame, km_from: float, km_to: float) -> pd.DataFrame:
    """The slice of a prepared ride between two distances along it."""
    return p[(p["cum_km"] >= km_from) & (p["cum_km"] <= km_to)]


# --------------------------------------------------------------------------
# the four components
# --------------------------------------------------------------------------

def envelope_area(a_lat_g, a_long_g) -> float:
    """
    g-g polygon: in each of 16 angular sectors take the p90 radius, then the
    area of the star polygon through those radii. A sector with fewer than 5
    samples contributes 0 — conservative, and it biases AGAINST fast rural
    rides (fewer samples per km), not in their favour.
    """
    x = np.asarray(a_lat_g, dtype=float)
    y = np.asarray(a_long_g, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < SECTOR_MIN_POINTS * 4:
        return float("nan")
    ang = np.mod(np.arctan2(y, x), 2 * np.pi)
    rad = np.hypot(x, y)
    k = np.minimum((ang / (2 * np.pi) * N_SECTORS).astype(int), N_SECTORS - 1)
    r = np.zeros(N_SECTORS)
    for s in range(N_SECTORS):
        m = k == s
        if m.sum() >= SECTOR_MIN_POINTS:
            r[s] = np.percentile(rad[m], 90)
    return float(0.5 * np.sin(2 * np.pi / N_SECTORS) * np.sum(r * np.roll(r, -1)))


def reversals_per_km(p: pd.DataFrame, km: float) -> float:
    """Left-right changes of lean past 5 deg, within a segment, per km. The esses signal."""
    if not km or km <= 0:
        return float("nan")
    m = p["lean"].abs() > REVERSAL_LEAN_DEG
    q = p.loc[m, ["lean", "seg"]]
    if len(q) < 2:
        return 0.0
    s = np.sign(q["lean"].to_numpy())
    seg = q["seg"].to_numpy()
    flips = (s[1:] != s[:-1]) & (seg[1:] == seg[:-1])
    return float(flips.sum() / km)


def throttle_entropy(p: pd.DataFrame) -> float:
    th = p.loc[p["moving"], "throttle"].dropna().to_numpy()
    if len(th) < 30:
        return float("nan")
    h, _ = np.histogram(th, bins=THROTTLE_BINS, range=(0.0, 100.0))
    q = h[h > 0] / h.sum()
    return float(-(q * np.log(q)).sum() / np.log(THROTTLE_BINS))


def uninterrupted_share(p: pd.DataFrame) -> float:
    step = p["step_m"].to_numpy()
    tot = step.sum()
    if tot <= 0:
        return float("nan")
    fast = np.nan_to_num(p["v_ms"].to_numpy()) >= FLOWING_MS
    return float(step[fast].sum() / tot)


def components(p: pd.DataFrame) -> dict:
    """The four joy components plus descriptors, for a prepared ride or window."""
    km = float(p["step_m"].sum() / 1000.0)
    lean_ok = bool(np.nanstd(p["lean"].to_numpy()) > 1.0) if p["lean"].notna().any() else False
    mv = p[p["moving"]]
    a_lat = np.tan(np.radians(mv["lean"].to_numpy()))
    out = {
        "km": km,
        "minutes": float(p["dt"].where(p["dt"] <= GAP_SPLIT_S, 0).sum() / 60.0),
        "n_points": int(len(p)),
        "bus_speed_ok": bool(p["bus_speed_ok"].iloc[0]) if len(p) else False,
        "lean_ok": lean_ok,
        "E_envelope": envelope_area(a_lat, mv["a_long_g"]) if lean_ok else float("nan"),
        "R_reversals_km": reversals_per_km(p, km) if lean_ok else float("nan"),
        "T_throttle_entropy": throttle_entropy(p),
        "U_uninterrupted": uninterrupted_share(p),
        "lean_p90": float(np.nanpercentile(np.abs(mv["lean"]), 90)) if lean_ok and len(mv) else float("nan"),
    }
    ll = p[(p["lat"] != 0) & (p["lon"] != 0)]
    out["loop_closure_km"] = (float(_haversine_m(ll["lat"].iloc[0], ll["lon"].iloc[0],
                                                  ll["lat"].iloc[-1], ll["lon"].iloc[-1]) / 1000.0)
                              if len(ll) > 1 else float("nan"))
    return out


# --------------------------------------------------------------------------
# the score
# --------------------------------------------------------------------------

def reference(rides: pd.DataFrame) -> dict:
    """Mean and sd of each component over a reference set of rides."""
    return {c: (float(rides[c].mean()), float(rides[c].std(ddof=1))) for c in COMPONENTS}


def joy(rides: pd.DataFrame, ref: dict) -> pd.Series:
    """Mean z-score of the available components. NaN only if all four are missing."""
    z = pd.DataFrame({c: (rides[c] - ref[c][0]) / (ref[c][1] or np.nan) for c in COMPONENTS})
    return z.mean(axis=1, skipna=True)


def auc(pos, neg) -> float:
    """P(a positive outscores a negative), ties count half. Mann-Whitney form."""
    pos = np.asarray(pos, dtype=float)
    neg = np.asarray(neg, dtype=float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return float("nan")
    allv = np.concatenate([pos, neg])
    ranks = pd.Series(allv).rank(method="average").to_numpy()
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
