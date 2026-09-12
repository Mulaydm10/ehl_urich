"""
FLOWSTATE — core scoring logic.

Pure pandas/numpy. No streamlit import, so this module is importable and testable
on its own (``python -m app.flowstate`` runs a self-check).

THE MODEL
---------
    challenge = req_deg                     degrees of lean the corner demands
    skill     = rider lean p95, per corner DIRECTION (LEFT / RIGHT)
    z         = (challenge - skill) / sigma  sigma = rider sd of lean_deg
    flow      = exp(-(z - z*)^2 / (2 tau^2))
    gate      : flow := 0 where challenge > skill + 2*sigma   (safety)

z* is the Thrill Dial: 0.15 Cruise, 0.50 Flow, 0.90 Send it.

DATA TRAPS HONOURED (docs/08_DATA_FINDINGS.md, NOTES.md)
  * sensorsbankingangle is invalid below 0.5 m/s  -> side stand, parks left
  * positive sensorsbankingangle = RIGHT-hand corner
  * ridingvehiclespeed is m/s
  * split on time gaps > 5 s before differentiating anything
  * use positionrawelevation, not positionmapmatchedelevation
  * ridingabsbraking == 3 is the only real hard-braking / ABS-regulation code
  * sensorsaccelerationlongitudinal is in g, NOT m/s^2 (BMW README is wrong)
  * morton codes are strings -- never parse them as ints
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# constants / paths
# --------------------------------------------------------------------------

G = 9.80665
MIN_SPEED_MS = 0.5          # below this the lean channel is the side stand
GAP_SPLIT_S = 5.0           # split the ride here before differentiating
TAU_DEFAULT = 0.5
GATE_SIGMAS = 2.0
ACCEL_LONG_IS_G = 9.80665   # multiply sensorsaccelerationlongitudinal by this

Z_PRESETS = {"Cruise": 0.15, "Flow": 0.50, "Send it": 0.90}

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "out"

CORNERS_ALL = OUT / "master_corners.parquet"
CORNERS_FILTERED = OUT / "corners_filtered.parquet"
GRID = OUT / "morton_grid.parquet"
TRACKPOINTS = OUT / "userA_all.parquet"
RAW_TRIPS = ROOT / "data" / "raw" / "exampleUserA_x" / "exampleUserA" / "recordedTrips"

# BMW's own demo box (trips-samples-2), NOTES.md
REGIONS = {
    "Everything user A rode": None,
    "Munich / Alpine foothills (BMW box)": (47.452237, 47.945786, 10.844879, 11.851501),
    "The Alps (south of 47.6 N)": (45.5, 47.6, 9.0, 13.5),
}

TRACKPOINT_COLS = [
    "trip_id",
    "timestampinmillis",
    "positionmapmatchedlatitude",
    "positionmapmatchedlongitude",
    "positionrawelevation",
    "positionmapmatchedheading",
    "ridingvehiclespeed",
    "sensorsbankingangle",
    "ridingthrottlevalue",
    "ridingenginespeed",
    "ridinggear",
    "ridingabsbraking",
    "sensorsoutsidetemperature",
    "sensorsaccelerationlongitudinal",
]

ABS_LABEL = {0: "off", 1: "armed", 2: "active", 3: "ABS LIMIT"}


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in metres, vectorised."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float))
                              for x in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 6371008.8 * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def required_lean_deg(v_ms, yaw_rate_dps) -> np.ndarray:
    """theta = arctan(v * omega / g). The Road DNA half of the bridge."""
    v = np.asarray(v_ms, dtype=float)
    omega = np.radians(np.asarray(yaw_rate_dps, dtype=float))
    return np.degrees(np.arctan(np.abs(v * omega) / G))


# --------------------------------------------------------------------------
# loaders (plain functions; the streamlit app wraps these in @st.cache_data)
# --------------------------------------------------------------------------

def load_corners(filtered: bool = True) -> pd.DataFrame:
    """5,253 real road corners (filtered) or all 5,747 (incl. manoeuvres)."""
    path = CORNERS_FILTERED if filtered else CORNERS_ALL
    df = pd.read_parquet(path)
    df["morton"] = df["morton"].astype(str)          # never let it become an int
    df["corner_id"] = df["trip"].str.slice(0, 8) + "#" + df["blk"].astype(str)
    return df


def load_grid() -> pd.DataFrame:
    """1,090 morton cells of Road DNA, built from telemetry alone."""
    g = pd.read_parquet(GRID)
    g["cell"] = g["cell"].astype(str)
    return g


def load_manifest() -> pd.DataFrame:
    """
    BMW's own per-ride summary (cloudRecordedTracks-*.csv): title, bikeId,
    rideDistance, and — the interesting part — leanAngleLeftMax /
    leanAngleRightMax, i.e. BMW's own asymmetry estimator.
    """
    hits = sorted(RAW_TRIPS.glob("cloudRecordedTracks-*.csv")) if RAW_TRIPS.exists() else []
    if not hits:
        return pd.DataFrame()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            m = pd.read_csv(hits[0], encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        return pd.DataFrame()
    m["trip_id"] = m["itemId"].astype(str).str.split("#").str[-1]
    m["bike"] = m["bikeId"].astype(str).str.slice(0, 8)
    m["title"] = (m["title"].astype(str).str.replace(r'^"|"$', "", regex=True)
                  .str.replace("\\n", ", ", regex=False).str.strip())
    m["km_manifest"] = pd.to_numeric(m.get("rideDistance"), errors="coerce") / 1000.0
    return m


def manifest_asymmetry(manifest: pd.DataFrame) -> dict | None:
    """BMW's own estimator: mean per-ride (leanAngleLeftMax - RightMax) with a 95% CI."""
    if manifest.empty or "leanAngleLeftMax" not in manifest:
        return None
    d = (pd.to_numeric(manifest["leanAngleLeftMax"], errors="coerce")
         - pd.to_numeric(manifest["leanAngleRightMax"], errors="coerce")).dropna()
    if len(d) < 5:
        return None
    se = float(d.std(ddof=1) / math.sqrt(len(d)))
    return {"mean": float(d.mean()), "lo": float(d.mean() - 1.96 * se),
            "hi": float(d.mean() + 1.96 * se), "n": int(len(d)),
            "significant": bool((d.mean() - 1.96 * se) * (d.mean() + 1.96 * se) > 0)}


def load_trip_index() -> pd.DataFrame:
    """One row per recorded ride: date, length, duration, elevation range."""
    tp = pd.read_parquet(
        TRACKPOINTS,
        columns=["trip_id", "timestampinmillis",
                 "positionmapmatchedlatitude", "positionmapmatchedlongitude",
                 "positionrawelevation", "ridingvehiclespeed", "sensorsbankingangle"],
    )
    tp = tp.sort_values(["trip_id", "timestampinmillis"])
    lat = tp["positionmapmatchedlatitude"].to_numpy()
    lon = tp["positionmapmatchedlongitude"].to_numpy()
    step = np.zeros(len(tp))
    if len(tp) > 1:
        step[1:] = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    same = tp["trip_id"].to_numpy()
    step[1:][same[1:] != same[:-1]] = 0.0
    step[step > 500] = 0.0                      # teleport / gap guard
    tp["_step_m"] = step

    g = tp.groupby("trip_id", sort=False).agg(
        n_points=("timestampinmillis", "size"),
        t_start=("timestampinmillis", "min"),
        t_end=("timestampinmillis", "max"),
        km=("_step_m", lambda s: s.sum() / 1000.0),
        elev_min=("positionrawelevation", "min"),
        elev_max=("positionrawelevation", "max"),
        v_max=("ridingvehiclespeed", "max"),
        lean_sd=("sensorsbankingangle", "std"),
        lat=("positionmapmatchedlatitude", "mean"),
        lon=("positionmapmatchedlongitude", "mean"),
    ).reset_index()

    # DATA PROBLEM found here, not in the docs: on 27 of 100 rides EVERY speed
    # channel (bus, map-matched, raw) is flat zero. Those rides fall back to a
    # GPS-derived speed, and we say so in the UI rather than showing 0 km/h.
    g["bus_speed_ok"] = g["v_max"] > 1.0
    g["lean_ok"] = g["lean_sd"].fillna(0) > 1.0

    g["start"] = pd.to_datetime(g["t_start"], unit="ms")
    g["minutes"] = (g["t_end"] - g["t_start"]) / 60000.0
    g["elev_range"] = g["elev_max"] - g["elev_min"]

    man = load_manifest()
    if not man.empty:
        keep = [c for c in ["trip_id", "title", "bike", "km_manifest", "isFavorite",
                            "leanAngleLeftMax", "leanAngleRightMax", "speedMaxKmh"]
                if c in man.columns]
        g = g.merge(man[keep], on="trip_id", how="left")
    for col, default in [("title", ""), ("bike", "?")]:
        if col not in g:
            g[col] = default
    g["title"] = g["title"].fillna("").astype(str).str.slice(0, 42)

    g["label"] = (
        g["start"].dt.strftime("%Y-%m-%d")
        + "  ·  " + g["km"].round(0).astype(int).astype(str) + " km"
        + "  ·  " + g["minutes"].round(0).astype(int).astype(str) + " min"
        + "  ·  " + g["elev_range"].round(0).astype(int).astype(str) + " m climb"
        + np.where(g["title"].str.len() > 0, "  ·  " + g["title"], "")
        + np.where(g["bus_speed_ok"], "", "   [GPS speed only]")
        + np.where(g["lean_ok"], "", "   [no lean channel]")
    )
    # most interesting first — but a ride with dead channels is never the default
    g["interest"] = (g["elev_range"].fillna(0) + g["km"].fillna(0) * 2.0
                     + np.where(g["bus_speed_ok"] & g["lean_ok"], 100000.0, 0.0))
    return g.sort_values("interest", ascending=False).reset_index(drop=True)


def load_trip(trip_id: str, max_points: int = 2000) -> pd.DataFrame:
    """
    Load one recorded ride, clean it, derive the live physics, and downsample
    to <= max_points frames for animation.

    Returned columns: t_s, lat, lon, elev_m, km, kmh, v_ms, lean_deg (signed,
    + = right), lean_abs, yaw_dps, req_deg, turn_dir, throttle, gear, rpm,
    abs_code, abs_label, temp_c, accel_ms2, seg.
    """
    df = pd.read_parquet(TRACKPOINTS, columns=TRACKPOINT_COLS,
                         filters=[("trip_id", "==", trip_id)])
    df = df.sort_values("timestampinmillis").drop_duplicates("timestampinmillis")
    df = df.dropna(subset=["positionmapmatchedlatitude", "positionmapmatchedlongitude"])
    df = df[(df["positionmapmatchedlatitude"].abs() > 0.01)
            & (df["positionmapmatchedlongitude"].abs() > 0.01)].reset_index(drop=True)
    if df.empty:
        return pd.DataFrame()

    ts = df["timestampinmillis"].to_numpy(dtype="int64")
    dt = np.diff(ts, prepend=ts[0]) / 1000.0
    seg = (dt > GAP_SPLIT_S).cumsum()                  # TRAP: split on gaps > 5 s
    dt_safe = np.clip(dt, 0.2, GAP_SPLIT_S)

    lat = df["positionmapmatchedlatitude"].to_numpy()
    lon = df["positionmapmatchedlongitude"].to_numpy()
    step = np.zeros(len(df))
    if len(df) > 1:
        step[1:] = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    step[seg != np.roll(seg, 1)] = 0.0
    step[step > 500] = 0.0

    # speed: the vehicle bus is the cleanest channel WHEN IT IS ALIVE. On 27 of
    # user A's 100 rides every speed channel is flat zero, so fall back to a
    # GPS-derived speed and tell the UI which one we used.
    v_bus = df["ridingvehiclespeed"].to_numpy(dtype=float)
    v_gps = pd.Series(step / dt_safe).rolling(3, center=True, min_periods=1).median()
    v_gps = np.clip(np.nan_to_num(v_gps.to_numpy(dtype=float)), 0.0, 80.0)
    speed_source = "vehicle bus (ridingvehiclespeed)"
    v = v_bus
    if np.nanmax(v_bus) <= 1.0:
        v = v_gps
        speed_source = "GPS-derived (every speed channel is flat zero on this ride)"

    # yaw rate from map-matched heading, wrapped, gap-safe, median-smoothed
    hdg = df["positionmapmatchedheading"].to_numpy(dtype=float)
    dh = np.diff(hdg, prepend=hdg[0])
    dh = (dh + 180.0) % 360.0 - 180.0
    dh[seg != np.roll(seg, 1)] = 0.0
    yaw = np.array(pd.Series(dh / dt_safe).rolling(3, center=True, min_periods=1).median(),
                   dtype=float)
    yaw[np.abs(yaw) > 90.0] = np.nan                            # GPS spike guard
    yaw = pd.Series(yaw).ffill().bfill().fillna(0.0).to_numpy()

    req = required_lean_deg(v, yaw)
    req = np.clip(np.nan_to_num(req), 0.0, 60.0)
    req[v < 2.0] = 0.0                                           # crawling: no demand
    # 1 Hz gives 3-6 samples per corner (docs/08 3), and map-matched heading is
    # quantised to road segments, so a single sample often reads 0 in the middle
    # of a real corner. Demand is a property of the CORNER, not of the instant:
    # hold it across a 5 s window. Measured against sensorsbankingangle on this
    # rider that lifts corr from 0.74 to 0.77.
    req = pd.Series(req).rolling(5, center=True, min_periods=1).max().to_numpy()

    lean = df["sensorsbankingangle"].to_numpy(dtype=float, copy=True)
    lean[v < MIN_SPEED_MS] = np.nan                              # TRAP: side stand

    out = pd.DataFrame({
        "t_s": (ts - ts[0]) / 1000.0,
        "lat": lat,
        "lon": lon,
        "elev_m": df["positionrawelevation"].to_numpy(dtype=float),   # raw, not matched
        "km": np.cumsum(step) / 1000.0,
        "v_ms": v,
        "kmh": v * 3.6,
        "lean_deg": lean,                     # signed, POSITIVE = RIGHT corner
        "lean_abs": np.abs(lean),
        "yaw_dps": yaw,
        "req_deg": req,
        "throttle": df["ridingthrottlevalue"].to_numpy(dtype=float),
        "gear": df["ridinggear"].to_numpy(dtype=float),
        "rpm": df["ridingenginespeed"].to_numpy(dtype=float),
        "abs_code": df["ridingabsbraking"].to_numpy(dtype="int64"),
        "temp_c": df["sensorsoutsidetemperature"].to_numpy(dtype=float),
        # BMW README says m/s^2; measured slope says g. Convert.
        "accel_ms2": df["sensorsaccelerationlongitudinal"].to_numpy(dtype=float) * ACCEL_LONG_IS_G,
        "seg": seg,
    })
    out["turn_dir"] = np.where(out["yaw_dps"] > 2.0, "RIGHT",
                               np.where(out["yaw_dps"] < -2.0, "LEFT", "STRAIGHT"))

    # trim the parked minutes off both ends — a replay that opens on seven
    # minutes of a stationary bike is a wasted demo
    moving = (out["v_ms"].to_numpy() >= 2.0)
    trimmed = 0
    if moving.any():
        i0 = max(0, int(np.argmax(moving)) - 5)
        i1 = min(len(out), len(moving) - int(np.argmax(moving[::-1])) + 5)
        trimmed = len(out) - (i1 - i0)
        out = out.iloc[i0:i1].reset_index(drop=True)
        if len(out):
            out["km"] = out["km"] - out["km"].iloc[0]
            out["t_s"] = out["t_s"] - out["t_s"].iloc[0]

    out = _downsample(out, max_points)
    out["abs_label"] = out["abs_code"].map(ABS_LABEL).fillna("?")
    out["i"] = np.arange(len(out))
    out.attrs["speed_source"] = speed_source
    out.attrs["trip_id"] = trip_id
    out.attrs["raw_points"] = int(len(df))
    out.attrs["trimmed_points"] = int(trimmed)
    out.attrs["lean_ok"] = bool(np.isfinite(out["lean_abs"]).any()
                                and np.nanstd(out["lean_deg"]) > 1.0)
    return out


def _downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    """Bin to <= max_points, keeping the PEAKS of lean and demand (not the mean)."""
    n = len(df)
    if n <= max_points:
        return df.reset_index(drop=True)
    stride = int(math.ceil(n / max_points))
    key = np.arange(n) // stride
    agg = {
        "t_s": "first", "lat": "first", "lon": "first", "elev_m": "mean",
        "km": "last", "v_ms": "max", "kmh": "max",
        "lean_abs": "max", "yaw_dps": "mean", "req_deg": "max",
        "throttle": "max", "gear": "median", "rpm": "max",
        "abs_code": "max", "temp_c": "mean", "accel_ms2": "min",
        "seg": "first", "turn_dir": "first",
    }
    g = df.groupby(key, sort=True)
    out = g.agg(agg)
    # signed channels: keep whichever extreme in the bin has the larger magnitude,
    # never the mean — averaging a left and a right turn gives a straight line
    for col in ("lean_deg", "yaw_dps"):
        hi, lo = g[col].max(), g[col].min()
        out[col] = np.where(hi.abs().fillna(-1) >= lo.abs().fillna(-1), hi, lo)
    out["turn_dir"] = np.where(out["yaw_dps"] > 2.0, "RIGHT",
                               np.where(out["yaw_dps"] < -2.0, "LEFT", "STRAIGHT"))
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------
# Rider DNA
# --------------------------------------------------------------------------

@dataclass
class RiderDNA:
    label: str
    n_corners: int
    n_rides: int
    skill_left: float
    skill_right: float
    skill_all: float
    sigma: float
    abs_events: int
    n_bikes: int
    total_km: float
    borrowed_sigma: bool = False
    notes: list = field(default_factory=list)

    @property
    def headroom(self) -> float:
        """Degrees of extra demand before the safety gate fires."""
        return GATE_SIGMAS * self.sigma

    def skill_for(self, direction) -> np.ndarray | float:
        """Per-direction skill. Accepts a scalar or a Series of LEFT/RIGHT."""
        if isinstance(direction, (pd.Series, np.ndarray, list)):
            s = pd.Series(direction).astype(str).str.upper()
            return s.map({"LEFT": self.skill_left, "RIGHT": self.skill_right}) \
                    .fillna(self.skill_all).to_numpy()
        d = str(direction).upper()
        return {"LEFT": self.skill_left, "RIGHT": self.skill_right}.get(d, self.skill_all)

    def gate_for(self, direction):
        return self.skill_for(direction) + GATE_SIGMAS * self.sigma


def rider_dna(corners: pd.DataFrame, label: str = "User A — all rides",
              fallback_sigma: float | None = None) -> RiderDNA:
    """Skill = lean p95 per direction. Sigma = sd of lean. Both from their own corners."""
    c = corners.dropna(subset=["lean_deg"])
    left = c.loc[c["dir_name"] == "LEFT", "lean_deg"]
    right = c.loc[c["dir_name"] == "RIGHT", "lean_deg"]
    notes = []

    def p95(s, default=np.nan):
        return float(np.percentile(s, 95)) if len(s) >= 5 else default

    skill_all = p95(c["lean_deg"], 25.0)
    skill_left = p95(left, skill_all)
    skill_right = p95(right, skill_all)

    sigma = float(c["lean_deg"].std()) if len(c) >= 10 else np.nan
    borrowed = False
    if not np.isfinite(sigma) or sigma < 1e-6:
        sigma = float(fallback_sigma or 7.5)
        borrowed = True
        notes.append("Too few corners for a stable sigma — borrowed the fleet-wide value.")
    if len(c) < 50:
        notes.append(f"Only {len(c)} corners in this selection: treat the profile as indicative.")

    return RiderDNA(
        label=label,
        n_corners=int(len(c)),
        n_rides=int(c["trip"].nunique()) if "trip" in c else 0,
        skill_left=skill_left,
        skill_right=skill_right,
        skill_all=skill_all,
        sigma=sigma,
        abs_events=int((c["abs_max"] >= 3).sum()) if "abs_max" in c else 0,
        n_bikes=int(c["bike"].nunique()) if "bike" in c else 0,
        total_km=float(c.groupby("trip")["km_into"].max().sum()) if "trip" in c else 0.0,
        borrowed_sigma=borrowed,
        notes=notes,
    )


# --------------------------------------------------------------------------
# the flow kernel
# --------------------------------------------------------------------------

def flow_score(challenge, skill, sigma: float, z_star: float,
               tau: float = TAU_DEFAULT, gate_sigmas: float = GATE_SIGMAS):
    """
    Returns (z, flow, gated).

    z     = (challenge - skill) / sigma
    flow  = exp(-(z - z*)^2 / (2 tau^2)), forced to 0 where the safety gate fires
    gated = challenge > skill + gate_sigmas * sigma
    """
    challenge = np.asarray(challenge, dtype=float)
    skill = np.asarray(skill, dtype=float)
    sigma = float(sigma) if float(sigma) > 1e-6 else 1e-6
    z = (challenge - skill) / sigma
    flow = np.exp(-((z - float(z_star)) ** 2) / (2.0 * float(tau) ** 2))
    gated = challenge > (skill + gate_sigmas * sigma)
    flow = np.where(gated, 0.0, flow)
    return z, flow, gated


def score_corners(corners: pd.DataFrame, dna: RiderDNA, z_star: float,
                  tau: float = TAU_DEFAULT) -> pd.DataFrame:
    """Score every corner for this rider at this dial setting."""
    df = corners.copy()
    df["skill"] = dna.skill_for(df["dir_name"])
    z, flow, gated = flow_score(df["req_deg"], df["skill"], dna.sigma, z_star, tau)
    df["z"] = z
    df["flow"] = flow
    df["gated"] = gated
    df["gate_deg"] = df["skill"] + GATE_SIGMAS * dna.sigma
    df["band"] = np.where(gated, "EXCLUDED — over the safety gate",
                          np.where(z < z_star - tau, "BOREDOM",
                                   np.where(z > z_star + tau, "RISK", "FLOW")))
    return df


def score_trip(trip: pd.DataFrame, dna: RiderDNA, z_star: float,
               tau: float = TAU_DEFAULT) -> pd.DataFrame:
    """Live per-trackpoint flow along a recorded ride."""
    df = trip.copy()
    d = df["turn_dir"].replace("STRAIGHT", np.nan)
    df["skill"] = dna.skill_for(d.fillna("ALL"))
    z, flow, gated = flow_score(df["req_deg"], df["skill"], dna.sigma, z_star, tau)
    df["z"] = z
    df["flow"] = np.where(df["req_deg"] < 3.0, np.nan, flow)   # straight line: no score
    df["gated"] = gated
    df["band"] = np.where(gated, "RISK — gated",
                          np.where(z < z_star - tau, "BOREDOM",
                                   np.where(z > z_star + tau, "RISK", "FLOW")))
    return df


def flow_curve(z_star: float, tau: float = TAU_DEFAULT, lo: float = -4.0,
               hi: float = 4.0, n: int = 241):
    """The Gaussian itself, for plotting."""
    z = np.linspace(lo, hi, n)
    return z, np.exp(-((z - z_star) ** 2) / (2.0 * tau ** 2))


# --------------------------------------------------------------------------
# honesty: the left/right asymmetry, with an interval
# --------------------------------------------------------------------------

def lr_asymmetry(corners: pd.DataFrame, n_boot: int = 2000, seed: int = 7,
                 cluster: bool = True) -> dict:
    """
    95% CI on (p95 lean LEFT - p95 lean RIGHT).

    ``cluster=True`` resamples RIDES, not corners. This matters: corners inside
    one ride share a road, a bike, a mood and a day, so the naive corner-level
    bootstrap treats ~5,000 non-independent observations as independent and
    reports a spuriously tight interval. docs/07_VALIDATION.md asks for errors
    clustered on the rider/ride for exactly this reason.

    docs/08_DATA_FINDINGS.md 2.1: for user A the effect is ~1 deg and its SIGN
    FLIPS depending on the estimator. We report the interval and refuse to act
    inside it.
    """
    c = corners.dropna(subset=["lean_deg"])
    left = c.loc[c["dir_name"] == "LEFT", "lean_deg"].to_numpy(dtype=float)
    right = c.loc[c["dir_name"] == "RIGHT", "lean_deg"].to_numpy(dtype=float)
    if len(left) < 20 or len(right) < 20:
        return {"ok": False, "reason": "not enough corners in one direction"}

    rng = np.random.default_rng(seed)
    point = float(np.percentile(left, 95) - np.percentile(right, 95))

    def naive_ci():
        bl = np.percentile(rng.choice(left, (n_boot, len(left)), replace=True), 95, axis=1)
        br = np.percentile(rng.choice(right, (n_boot, len(right)), replace=True), 95, axis=1)
        return np.percentile(bl - br, [2.5, 97.5])

    def cluster_ci():
        trips = c["trip"].to_numpy()
        groups = [c.loc[c["trip"] == t] for t in pd.unique(trips)]
        packs = [(g.loc[g["dir_name"] == "LEFT", "lean_deg"].to_numpy(dtype=float),
                  g.loc[g["dir_name"] == "RIGHT", "lean_deg"].to_numpy(dtype=float))
                 for g in groups]
        k = len(packs)
        out = []
        for _ in range(n_boot):
            pick = rng.integers(0, k, k)
            L = np.concatenate([packs[i][0] for i in pick]) if k else left
            R = np.concatenate([packs[i][1] for i in pick]) if k else right
            if len(L) >= 5 and len(R) >= 5:
                out.append(np.percentile(L, 95) - np.percentile(R, 95))
        return np.percentile(out, [2.5, 97.5]) if len(out) > 20 else naive_ci()

    n_lo, n_hi = naive_ci()
    lo, hi = (cluster_ci() if cluster and "trip" in c else (n_lo, n_hi))
    significant = bool(lo > 0 or hi < 0)

    # the same quantity measured the other way round, per ride — the estimator
    # that flipped sign in docs/08_DATA_FINDINGS.md
    per_ride = []
    if "trip" in c:
        for _, g in c.groupby("trip"):
            gl = g.loc[g["dir_name"] == "LEFT", "lean_deg"]
            gr = g.loc[g["dir_name"] == "RIGHT", "lean_deg"]
            if len(gl) >= 5 and len(gr) >= 5:
                per_ride.append(np.percentile(gl, 95) - np.percentile(gr, 95))
    per_ride = np.asarray(per_ride, dtype=float)
    if len(per_ride) >= 5:
        se = per_ride.std(ddof=1) / math.sqrt(len(per_ride))
        pr = {"mean": float(per_ride.mean()), "lo": float(per_ride.mean() - 1.96 * se),
              "hi": float(per_ride.mean() + 1.96 * se), "n": int(len(per_ride))}
    else:
        pr = None

    return {
        "ok": True,
        "p95_left": float(np.percentile(left, 95)),
        "p95_right": float(np.percentile(right, 95)),
        "diff": point,
        "lo": float(lo),
        "hi": float(hi),
        "naive_lo": float(n_lo),
        "naive_hi": float(n_hi),
        "clustered": bool(cluster and "trip" in c),
        "per_ride": pr,
        "n_left": int(len(left)),
        "n_right": int(len(right)),
        "n_rides": int(c["trip"].nunique()) if "trip" in c else 0,
        "significant": significant,
        "stronger": ("LEFT" if point > 0 else "RIGHT") if significant else "neither",
        "n_boot": n_boot,
    }


# --------------------------------------------------------------------------
# the six-axis profile
# --------------------------------------------------------------------------

RADAR_AXES = [
    ("Cornering L", "p95 lean on left-hand corners (deg)"),
    ("Cornering R", "p95 lean on right-hand corners (deg)"),
    ("Braking", "p95 of peak deceleration into corners (m/s^2)"),
    ("Gradient", "p95 |road gradient| cornered on (%)"),
    ("Endurance", "how deep into a ride they still corner (km)"),
    ("Pace", "p95 corner entry speed (km/h) — context only, never scored"),
]


def _axis_values(c: pd.DataFrame) -> dict:
    c = c.dropna(subset=["lean_deg"])
    if c.empty:
        return {k: np.nan for k, _ in RADAR_AXES}

    def p95(s):
        s = pd.Series(s).dropna()
        return float(np.percentile(s, 95)) if len(s) >= 3 else np.nan

    left = c.loc[c["dir_name"] == "LEFT", "lean_deg"]
    right = c.loc[c["dir_name"] == "RIGHT", "lean_deg"]
    return {
        "Cornering L": p95(left),
        "Cornering R": p95(right),
        "Braking": p95(-c["a_min"]) if "a_min" in c else np.nan,
        "Gradient": p95(c["grade"].abs() * 100.0) if "grade" in c else np.nan,
        "Endurance": float(c["km_into"].max()) if "km_into" in c else np.nan,
        "Pace": p95(c["v_ms"] * 3.6),
    }


def radar_profile(subset: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """
    Six-axis profile, scaled 0-100 against the spread of the SAME statistic
    computed per ride across the reference population. Honest because the
    reference is stated, not implied: it is this dataset, not humanity.
    """
    vals = _axis_values(subset)
    per_ride = (reference.groupby("trip", group_keys=False)
                .apply(lambda g: pd.Series(_axis_values(g)), include_groups=False)
                if "trip" in reference else pd.DataFrame([_axis_values(reference)]))

    rows = []
    for name, desc in RADAR_AXES:
        v = vals.get(name, np.nan)
        col = per_ride[name].dropna() if name in per_ride else pd.Series(dtype=float)
        if len(col) >= 5:
            lo, hi = np.percentile(col, [5, 95])
        else:
            lo, hi = (0.0, v if np.isfinite(v) and v > 0 else 1.0)
        span = max(hi - lo, 1e-6)
        score = float(np.clip((v - lo) / span * 100.0, 0.0, 100.0)) if np.isfinite(v) else 0.0
        rows.append({"axis": name, "value": v, "score": score,
                     "lo": float(lo), "hi": float(hi), "what": desc})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# helpers for the map tabs
# --------------------------------------------------------------------------

FLOW_STOPS = [
    (0.00, (110, 122, 145)),   # cool grey-blue: boredom
    (0.35, (0, 120, 190)),     # BMW blue
    (0.65, (0, 190, 160)),     # teal
    (0.85, (120, 220, 90)),    # green
    (1.00, (255, 220, 60)),    # gold: in the band
]


def flow_color(values, alpha: int = 200) -> list:
    """Map flow 0..1 to RGBA. Gated / NaN rows come back red."""
    v = pd.Series(values, dtype=float)
    out = []
    stops = FLOW_STOPS
    for x in v:
        if not np.isfinite(x):
            out.append([90, 90, 100, 60])
            continue
        x = float(np.clip(x, 0.0, 1.0))
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if x <= b or b == stops[-1][0]:
                t = 0.0 if b == a else (x - a) / (b - a)
                t = float(np.clip(t, 0.0, 1.0))
                out.append([int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3)] + [alpha])
                break
    return out


def demand_color(values, vmin=None, vmax=None, alpha: int = 190) -> list:
    """Blue (easy) -> red (demanding) for the road-demand layers."""
    v = pd.Series(values, dtype=float)
    lo = float(v.min()) if vmin is None else vmin
    hi = float(v.max()) if vmax is None else vmax
    span = max(hi - lo, 1e-6)
    t = ((v - lo) / span).clip(0, 1).fillna(0)
    return [[int(20 + 235 * x), int(90 + 110 * (1 - abs(2 * x - 1))), int(230 - 200 * x), alpha]
            for x in t]


def apply_region(df: pd.DataFrame, region: str) -> pd.DataFrame:
    box = REGIONS.get(region)
    if box is None:
        return df
    la0, la1, lo0, lo1 = box
    return df[(df["lat"].between(la0, la1)) & (df["lon"].between(lo0, lo1))]


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def _selfcheck() -> None:
    print("FLOWSTATE self-check")
    c = load_corners(True)
    print(f"  corners_filtered      {c.shape}")
    dna = rider_dna(c)
    print(f"  skill L/R             {dna.skill_left:.1f} / {dna.skill_right:.1f} deg")
    print(f"  sigma                 {dna.sigma:.2f} deg   headroom {dna.headroom:.1f} deg")

    # kernel maths
    z, flow, gated = flow_score(np.array([dna.skill_left + 0.5 * dna.sigma]),
                                np.array([dna.skill_left]), dna.sigma, 0.5, 0.5)
    assert abs(flow[0] - 1.0) < 1e-9, "peak flow must be 1.0 at z == z*"
    _, f2, g2 = flow_score(np.array([dna.skill_left + 3 * dna.sigma]),
                           np.array([dna.skill_left]), dna.sigma, 0.5, 0.5)
    assert g2[0] and f2[0] == 0.0, "safety gate must zero the score"
    print("  kernel                 peak=1.0 at z*, gate zeroes beyond +2 sigma  OK")

    for name, zs in Z_PRESETS.items():
        s = score_corners(c, dna, zs)
        top = s.nlargest(200, "flow")
        print(f"  {name:8s} z*={zs:<5} top200: req {top.req_deg.mean():5.1f} deg  "
              f"elev {top.elev_m.mean():6.0f} m  centroid {top.lat.mean():.3f} N "
              f"{top.lon.mean():.3f} E  gated {int(s.gated.sum())}")

    a = lr_asymmetry(c)
    verdict = "SIGNIFICANT" if a["significant"] else "NOT significant"
    print(f"  L-R asymmetry          {a['diff']:+.2f} deg  clustered 95% CI "
          f"[{a['lo']:+.2f}, {a['hi']:+.2f}]  {verdict}")
    print(f"     naive (corner) CI   [{a['naive_lo']:+.2f}, {a['naive_hi']:+.2f}]  "
          f"<- wrong, corners are clustered in rides")
    if a["per_ride"]:
        print(f"     per-ride estimator  {a['per_ride']['mean']:+.2f} "
              f"[{a['per_ride']['lo']:+.2f}, {a['per_ride']['hi']:+.2f}] over {a['per_ride']['n']} rides")
    ma = manifest_asymmetry(load_manifest())
    if ma:
        print(f"     BMW's own maxima    {ma['mean']:+.2f} [{ma['lo']:+.2f}, {ma['hi']:+.2f}] "
              f"over {ma['n']} rides -> SIGN FLIPS vs the corner estimator")

    g = load_grid()
    print(f"  morton_grid           {g.shape}, {int((g.abs_events > 0).sum())} hazard cells")

    idx = load_trip_index()
    print(f"  rides                 {len(idx)}")
    t = load_trip(idx.iloc[0]["trip_id"])
    st = score_trip(t, dna, 0.5)
    print(f"  replay frames         {len(st)} (from {int(idx.iloc[0]['n_points'])} raw)  "
          f"peak lean {st.lean_abs.max():.1f} deg  peak demand {st.req_deg.max():.1f} deg")
    print(f"  radar                 {radar_profile(c, c)['score'].round(0).tolist()}")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    _selfcheck()
