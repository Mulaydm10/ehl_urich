"""
modes.py — what kind of ride, and who is riding it. Phase 3, doc 22.

Pure functions. Nothing here reads raw data or decides what the app may offer:
the router imports the mode weights, analysis/17_riders_modes.py tests every
claim below on real rides, and service.py offers only what passed there.

Three things live here.

  MODES          a weight vector over road-character columns that PASSED doc 21,
                 turned into an extra unfit term in [0, MODE_ALPHA] on a cell's
                 edge cost. It never changes flow (the fit to this rider) and it
                 never touches the gate.
  mood           rpm per km/h (holding a low gear) and lean in the first ten
                 minutes of a ride — the F3.4 signal, tested for whether it
                 predicts the rest of the ride, not just whether it exists.
  rhythm match   how close a road's crowd lean wavelength is to a rider's own.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# modes (F3.2)
# --------------------------------------------------------------------------

MODE_ALPHA = 0.5     # a road wholly unlike the mode costs as if half its fit were gone

# + prefers high values of the column, - prefers low. Weights act on percentile
# ranks across the cell table, so metres, rides and ratios are commensurable.
#
# There is no demand column in any mode. The Thrill Dial IS the demand axis, and
# adventure_index is demand again (doc 21: rho 0.89), so either would count demand
# twice. dwell_share (redundant with stop_rate), traffic (unreliable) and
# viewpoints (no data) failed doc 21 and are not used.
MODES = {
    "flow": {},                                           # today's router, bit for bit
    "scenic": {"elev_prominence_m": +1.0},                # above your surroundings
    "adventure": {"n_rides": -1.0,                        # roads the crowd rarely rides
                  "rhythm_purity": -1.0,                  # broadband, not one repeating bend
                  "elev_prominence_m": +1.0},
    "mountain": {"elev_mean": +2.0,                       # altitude itself
                 "reversals_km": +1.0},                   # switchbacks; residential masked
    "urban": {"n_rides": -1.0, "stop_rate": -1.0},        # F4.5, Phase 4: defined, not offered
}
PHASE4_MODES = ("urban",)

# the one raw column each mode is judged on in the per-mode scan (sign = intended move)
MODE_TARGET = {"scenic": ("elev_prominence_m", +1), "adventure": ("n_rides", -1),
               "mountain": ("elev_mean", +1), "urban": ("n_rides", -1)}

# F3.3: which mode a bike archetype opens on, if archetypes exist at all
ARCHETYPE_MODE = {"sport": "flow", "adventure": "adventure", "tour": "scenic"}


def mode_columns(mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; one of {sorted(MODES)}")
    return MODES[mode]


def mode_preference(frame: pd.DataFrame, mode: str) -> np.ndarray:
    """
    How much each row is this mode's kind of road, in [0, 1]. `frame` holds the
    mode's columns in cell-table row order. A missing value is neutral (0.5):
    a cell with no rhythmic window is not broadband, it is unmeasured.
    """
    w = mode_columns(mode)
    if not w:
        return np.ones(len(frame))
    num = np.zeros(len(frame))
    den = 0.0
    for col, wt in w.items():
        r = frame[col].rank(pct=True).to_numpy(dtype=float)
        r = np.where(np.isfinite(r), r, 0.5)
        num += abs(wt) * (r if wt > 0 else 1.0 - r)
        den += abs(wt)
    return num / den


def mode_penalty(frame: pd.DataFrame, mode: str, alpha: float = MODE_ALPHA) -> np.ndarray:
    """
    Extra unfit in [0, alpha], added to (1 - flow) in the edge cost:

        cost = L * (1 + lambda * (1 - flow + penalty))

    Additive on purpose. The first version (doc 22, v1) MULTIPLIED flow by
    1 - alpha * (1 - preference). Its penalty is lambda * flow * alpha * (1 - pref),
    which is zero wherever flow is already zero, so the router escaped a mode by
    leaving good roads for dull ones: on changed pairs the cells only the mode
    route used had base flow 0.10 against 0.40, and a LOWER mode preference.
    """
    return float(alpha) * (1.0 - mode_preference(frame, mode))


# --------------------------------------------------------------------------
# mood (F3.4)
# --------------------------------------------------------------------------

MOOD_WINDOW_S = 600.0        # "the first ten minutes"
MOOD_MIN_V = 5.0             # m/s; the speed floor demand already uses
MOOD_MIN_RPM = 500.0         # below this the engine channel is off, not idling
MOOD_MIN_SAMPLES = 120       # ~2 moving minutes at 1 Hz


def mood_frame(tp: pd.DataFrame) -> pd.DataFrame:
    """
    One ride's trackpoints -> t_s, v (bus speed, m/s), rpm, lean (abs, side
    stand masked). Bus speed only: rpm / speed with a GPS-derived speed
    differences two noisy fixes and is not a gear.
    """
    d = tp.sort_values("timestampinmillis")
    t = d["timestampinmillis"].to_numpy(dtype=float) / 1000.0
    v = d["ridingvehiclespeed"].to_numpy(dtype=float)
    lean = np.abs(d["sensorsbankingangle"].to_numpy(dtype=float))
    return pd.DataFrame({"t_s": t - (t[0] if len(t) else 0.0), "v": v,
                         "rpm": d["ridingenginespeed"].to_numpy(dtype=float),
                         "lean": np.where(v > 0.5, lean, np.nan)})


def mood_signal(f: pd.DataFrame) -> dict:
    """rpm per km/h and lean p90 over the moving samples of a (part of a) ride."""
    mv = np.isfinite(f["v"].to_numpy()) & (f["v"].to_numpy() > MOOD_MIN_V)
    rpm = f["rpm"].to_numpy(dtype=float)
    m = mv & np.isfinite(rpm) & (rpm > MOOD_MIN_RPM)
    lean = f["lean"].to_numpy(dtype=float)[mv]
    lean = lean[np.isfinite(lean)]
    return {"n": int(m.sum()),
            "rpm_per_kmh": (float(np.median(rpm[m] / (3.6 * f["v"].to_numpy()[m])))
                            if m.any() else float("nan")),
            "lean_p50": float(np.percentile(lean, 50)) if lean.size else float("nan"),
            "lean_p90": float(np.percentile(lean, 90)) if lean.size else float("nan")}


def detect_mood(first_minutes: pd.DataFrame, cuts: tuple[float, float]) -> dict:
    """
    Where this ride's first ten minutes sit among the rider's own rides.
    `cuts` are the rider's own tercile edges of first-ten-minute rpm_per_kmh
    (aggregates, from analysis/17). Suggests, never switches: offered, not imposed.
    """
    s = mood_signal(first_minutes[first_minutes["t_s"] <= MOOD_WINDOW_S])
    lo, hi = (float(cuts[0]), float(cuts[1])) if cuts else (float("nan"), float("nan"))
    if s["n"] < MOOD_MIN_SAMPLES or not (np.isfinite(s["rpm_per_kmh"]) and np.isfinite(lo)):
        return {"ok": False, "note": "not enough moving riding yet to read a mood"}
    x = s["rpm_per_kmh"]
    band = "spirited" if x >= hi else "calm" if x < lo else "steady"
    suggest = {"spirited": "flow", "calm": "scenic"}.get(band)
    return {"ok": True, "band": band, "suggest": suggest, **s}


# --------------------------------------------------------------------------
# rhythm match (F3.5)
# --------------------------------------------------------------------------

def rider_wavelength(windows: pd.DataFrame) -> float:
    """Median dominant lean wavelength over a rider's own rhythmic windows."""
    w = windows["wavelength"].to_numpy(dtype=float)
    w = w[np.isfinite(w)]
    return float(np.median(w)) if w.size else float("nan")


def rhythm_match(road_wavelength, rider_wl: float, h: float) -> np.ndarray:
    """exp(-(road - rider)^2 / 2h^2). NaN where the road has no rhythm."""
    x = np.asarray(road_wavelength, dtype=float)
    return np.exp(-((x - float(rider_wl)) ** 2) / (2.0 * float(h) ** 2))
