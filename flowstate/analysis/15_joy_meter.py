"""
15_joy_meter.py — does the Joy Meter measure fun, or just ride length?  (Phase 1)

Three tests, thresholds fixed in this file BEFORE the first run:

  1. JOY. Commutes (5-20 km) vs long rides (>100 km), using only the four
     rate/share components. Twice:
       whole-ride     — the test as FEATURES.md words it
       length-matched — each long ride cut to a window from its MIDDLE, as
                        long as the median commute. Same distance on both
                        sides, so length cannot be what separates them.
     The verdict is read off the length-matched combined AUC.
     Bootstrap over RIDES, never samples: points inside a ride are not
     independent.

  2. OUT OF SAMPLE. The same meter, same reference recipe, same thresholds on
     user C — a second human the components were never looked at on.

  3. GRIP BUDGET (F1.3). "ABS fires because the grip was already spent on
     cornering." The naive test — does grip_used (lean + a_long) predict ABS
     better than lean — is CIRCULAR: a_long IS the braking. The honest one:
     among hard-braking samples only (a_long <= -0.2 g), is lateral grip higher
     when ABS==3 fires than when it does not? Same deceleration, so the only
     thing left to differ is how much tyre was already in use sideways.

F1.2 (learned weights) is not attempted: only 11 of 83 parsed planned GPX
routes are >=50% inside the crowd coverage box, so there is no honest fit.
The per-component AUC table below is the replacement answer to "how are the
terms weighted".

Run:
    V=/Users/mulaydm10/ehl_urich/.venv/bin/python
    PYTHONIOENCODING=utf-8 $V analysis/15_joy_meter.py
"""

from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import joy as J             # noqa: E402

OUT = ROOT / "analysis" / "out"
USER_A = OUT / "userA_all.parquet"
USER_C_DIR = ROOT / "data" / "raw" / "salvaged" / "exampleUserC" / "recordedTrips"

# ---- PRE-REGISTERED. Set before the first run; do not tune on the result. ----
COMMUTE_KM = (5.0, 20.0)
LONG_KM = 100.0
MIN_GROUP = 8                 # fewer rides than this in a group -> UNTESTABLE
PASS_AUC, PASS_CI_LO = 0.70, 0.50
WEAK_AUC = 0.60
LENGTH_RHO = 0.50             # |spearman(joy, km)| at or above this -> flagged as length
HARD_BRAKE_G = -0.20
N_BOOT = 2000
SEED = 7
# ------------------------------------------------------------------------------


def load_user_a() -> pd.DataFrame:
    tp = pd.read_parquet(USER_A, columns=J.TP_COLS)
    tp["trip_id"] = tp["trip_id"].astype(str)
    return tp


def load_user_c() -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(str(USER_C_DIR / "*.csv"))):
        d = pd.read_csv(f, usecols=lambda c: c in J.TP_COLS)
        if "trip_id" not in d or d["trip_id"].isna().all():
            d["trip_id"] = Path(f).stem
        d["trip_id"] = d["trip_id"].astype(str)
        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=J.TP_COLS)


def bike_map() -> dict:
    try:
        import flowstate as F
        m = F.load_manifest()
        return dict(zip(m["trip_id"].astype(str), m["bike"].astype(str))) if "bike" in m else {}
    except Exception as exc:                          # manifest is optional
        print(f"    (no bike manifest: {type(exc).__name__})")
        return {}


def per_ride(tp: pd.DataFrame, rider: str) -> tuple[pd.DataFrame, dict]:
    rows, prepared = [], {}
    for tid, g in tp.groupby("trip_id", sort=False):
        if len(g) < 60:
            continue
        p = J.prepare(g)
        prepared[tid] = p
        rows.append({"rider": rider, "trip_id": tid, **J.components(p)})
    return pd.DataFrame(rows), prepared


def boot_auc(pos_ids, neg_ids, val: dict, rng) -> tuple[float, float, float]:
    pos = np.array([val[i] for i in pos_ids], dtype=float)
    neg = np.array([val[i] for i in neg_ids], dtype=float)
    point = J.auc(pos, neg)
    draws = []
    for _ in range(N_BOOT):
        a = J.auc(rng.choice(pos, len(pos)), rng.choice(neg, len(neg)))
        if np.isfinite(a):
            draws.append(a)
    lo, hi = (np.percentile(draws, [2.5, 97.5]) if draws else (np.nan, np.nan))
    return point, float(lo), float(hi)


def verdict(a, lo, n_pos, n_neg) -> str:
    if min(n_pos, n_neg) < MIN_GROUP or not np.isfinite(a):
        return "UNTESTABLE"
    if a >= PASS_AUC and lo > PASS_CI_LO:
        return "PASS"
    if a >= WEAK_AUC:
        return "WEAK"
    return "FAIL"


def joy_test(rides: pd.DataFrame, prepared: dict, rider: str, rng) -> tuple[dict, pd.DataFrame]:
    usable = rides[(rides["km"] >= COMMUTE_KM[0]) & rides[list(J.COMPONENTS)].notna().any(axis=1)].copy()
    ref = J.reference(usable)
    usable["joy"] = J.joy(usable, ref)

    com = usable[(usable["km"] >= COMMUTE_KM[0]) & (usable["km"] < COMMUTE_KM[1])]
    lng = usable[usable["km"] > LONG_KM]
    win_km = float(com["km"].median()) if len(com) else float("nan")
    print(f"\n  [{rider}] rides usable {len(usable)} | commutes {len(com)} "
          f"(median {win_km:.1f} km) | long {len(lng)} | "
          f"GPS-speed rescued {int((~usable['bus_speed_ok']).sum())} | "
          f"no lean channel {int((~usable['lean_ok']).sum())}")

    # length-matched windows from the middle of each long ride
    wins = []
    for tid, km in zip(lng["trip_id"], lng["km"]):
        p = prepared[tid]
        mid = km / 2.0
        w = J.window(p, mid - win_km / 2.0, mid + win_km / 2.0)
        if len(w) >= 60:
            wins.append({"trip_id": tid, **J.components(w)})
    wins = pd.DataFrame(wins)
    if len(wins):
        wins["joy"] = J.joy(wins, ref)

    table = []
    for label, pos_df in (("whole-ride", lng), ("length-matched", wins)):
        for c in list(J.COMPONENTS) + ["joy"]:
            if not len(pos_df):
                continue
            val = {**{("n", t): v for t, v in zip(com["trip_id"], com[c])},
                   **{("p", t): v for t, v in zip(pos_df["trip_id"], pos_df[c])}}
            a, lo, hi = boot_auc([("p", t) for t in pos_df["trip_id"]],
                                 [("n", t) for t in com["trip_id"]], val, rng)
            table.append({"test": label, "component": c, "auc": round(a, 3),
                          "ci_lo": round(lo, 3), "ci_hi": round(hi, 3),
                          "n_long": int(len(pos_df)), "n_commute": int(len(com))})
    tab = pd.DataFrame(table)
    if len(tab):
        print(tab.to_string(index=False))

    rho_all = float(usable[["joy", "km"]].corr(method="spearman").iloc[0, 1])
    mid_band = usable[(usable["km"] >= COMMUTE_KM[1]) & (usable["km"] <= LONG_KM)]
    rho_mid = (float(mid_band[["joy", "km"]].corr(method="spearman").iloc[0, 1])
               if len(mid_band) >= MIN_GROUP else float("nan"))
    head = tab[(tab["test"] == "length-matched") & (tab["component"] == "joy")] if len(tab) else tab
    if len(head):
        h = head.iloc[0]
        v = verdict(h["auc"], h["ci_lo"], h["n_long"], h["n_commute"])
    else:
        v = "UNTESTABLE"
    flag = abs(rho_all) >= LENGTH_RHO
    print(f"  spearman(joy, km): all rides {rho_all:+.3f} | unlabelled 20-100 km band "
          f"{rho_mid:+.3f} (n={len(mid_band)})")
    print(f"  VERDICT [{rider}]: {v}" + ("  + LENGTH FLAG" if flag else ""))

    return {"verdict": v, "length_flag": bool(flag), "window_km": win_km,
            "rho_joy_km_all": rho_all, "rho_joy_km_mid_band": rho_mid,
            "n_usable": int(len(usable)), "n_commute": int(len(com)), "n_long": int(len(lng)),
            "n_gps_rescued": int((~usable["bus_speed_ok"]).sum()),
            "table": tab.to_dict("records"), "reference": ref}, usable


def grip_budget_test(prepared: dict, rider: str, rng) -> dict:
    rows = []
    for tid, p in prepared.items():
        m = p["moving"] & p["lean"].notna() & (p["a_long_g"] <= HARD_BRAKE_G)
        if m.any():
            q = p.loc[m, ["lean", "abs"]]
            rows.append(pd.DataFrame({"trip_id": tid,
                                      "grip_lat": np.abs(np.tan(np.radians(q["lean"]))) / 1.1,
                                      "abs3": (q["abs"] == 3).to_numpy()}))
    if not rows:
        return {"verdict": "UNTESTABLE", "n_hard_brake": 0, "n_abs": 0}
    d = pd.concat(rows, ignore_index=True)
    pos, neg = d.loc[d["abs3"], "grip_lat"], d.loc[~d["abs3"], "grip_lat"]
    a = J.auc(pos, neg)
    trips = d["trip_id"].unique()
    by = {t: g for t, g in d.groupby("trip_id")}
    draws = []
    for _ in range(N_BOOT):
        s = pd.concat([by[t] for t in rng.choice(trips, len(trips))], ignore_index=True)
        if s["abs3"].any() and (~s["abs3"]).any():
            draws.append(J.auc(s.loc[s["abs3"], "grip_lat"], s.loc[~s["abs3"], "grip_lat"]))
    lo, hi = (np.percentile(draws, [2.5, 97.5]) if draws else (np.nan, np.nan))
    n_abs_trips = int(d.loc[d["abs3"], "trip_id"].nunique())
    v = ("UNTESTABLE" if len(pos) < MIN_GROUP or n_abs_trips < 3
         else "PASS" if (a >= WEAK_AUC and lo > PASS_CI_LO) else "WEAK" if a >= WEAK_AUC else "FAIL")
    bands = d.assign(lean_band=pd.cut(np.degrees(np.arctan(d["grip_lat"] * 1.1)),
                                      [0, 10, 20, 90], labels=["<10", "10-20", ">20"]))
    rate = bands.groupby("lean_band", observed=False)["abs3"].agg(["size", "mean"])
    print(f"\n  [{rider}] GRIP BUDGET: hard-brake samples {len(d):,} | ABS==3 among them "
          f"{int(d['abs3'].sum())} on {n_abs_trips} rides")
    print(f"  median lateral grip  ABS {np.median(pos) if len(pos) else float('nan'):.3f} "
          f"vs no-ABS {np.median(neg):.3f} | AUC {a:.3f} [{lo:.3f}, {hi:.3f}] (bootstrap over rides)")
    print("  P(ABS | hard brake) by lean: " + " | ".join(
        f"{k} deg {r['mean']:.2%} (n={int(r['size'])})" for k, r in rate.iterrows()))
    print(f"  VERDICT [{rider}] grip budget: {v}")
    return {"verdict": v, "auc": a, "ci_lo": float(lo), "ci_hi": float(hi),
            "n_hard_brake": int(len(d)), "n_abs": int(d["abs3"].sum()), "n_abs_rides": n_abs_trips,
            "median_grip_abs": float(np.median(pos)) if len(pos) else float("nan"),
            "median_grip_no_abs": float(np.median(neg)),
            "rate_by_lean": {str(k): [int(r["size"]), float(r["mean"])] for k, r in rate.iterrows()}}


if __name__ == "__main__":
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    results, all_rides = {}, []

    for rider, loader in (("userA", load_user_a), ("userC", load_user_c)):
        tp = loader()
        print(f"\n[{rider}] {len(tp):,} trackpoints, {tp['trip_id'].nunique()} trips  "
              f"| throttle {tp['ridingthrottlevalue'].min():.1f}..{tp['ridingthrottlevalue'].max():.1f} "
              f"| a_long p1/p99 {tp['sensorsaccelerationlongitudinal'].quantile(.01):+.2f}/"
              f"{tp['sensorsaccelerationlongitudinal'].quantile(.99):+.2f} g "
              f"| ABS==3 {int((tp['ridingabsbraking'] == 3).sum())}")
        rides, prepared = per_ride(tp, rider)
        res, usable = joy_test(rides, prepared, rider, rng)
        res["grip_budget"] = grip_budget_test(prepared, rider, rng)
        results[rider] = res
        all_rides.append(rides.merge(usable[["trip_id", "joy"]], on="trip_id", how="left"))

    rides = pd.concat(all_rides, ignore_index=True)
    bm = bike_map()
    rides["bike"] = rides["trip_id"].map(bm).where(rides["rider"] == "userA")
    rides.to_parquet(OUT / "joy_rides.parquet", index=False)          # gitignored: carries trip ids

    summary = {r: {k: v for k, v in res.items()} for r, res in results.items()}
    summary["preregistered"] = {"commute_km": COMMUTE_KM, "long_km": LONG_KM, "min_group": MIN_GROUP,
                                "pass_auc": PASS_AUC, "pass_ci_lo": PASS_CI_LO, "weak_auc": WEAK_AUC,
                                "length_rho": LENGTH_RHO, "hard_brake_g": HARD_BRAKE_G,
                                "n_boot": N_BOOT, "seed": SEED}
    (OUT / "joy_test.json").write_text(json.dumps(summary, indent=1, default=float))
    print(f"\nwrote joy_rides.parquet ({len(rides)} rides) + joy_test.json in {time.time()-t0:.1f} s")
