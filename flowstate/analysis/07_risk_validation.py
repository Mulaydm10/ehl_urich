"""THE KEY RESULT: does the risk side of the flow curve predict real hard-braking / ABS events?

This is the empirical unification of BMW's two separate criteria (Fun Score, Rider Safety).
Reports the effect AND its honest uncertainty - clustered on ride, because one rider's corners
are not independent observations.
"""
import os

import numpy as np
import pandas as pd
from scipy import stats

OUT = r"F:\bmw\analysis\out"
cor = pd.read_parquet(os.path.join(OUT, "corners_filtered.parquet"))

skill = cor.lean_deg.quantile(.95)
sigma = cor.lean_deg.std()
cor["z"] = (cor.req_deg - skill) / sigma
cor["hard"] = (cor.abs_max >= 3).astype(float)      # ridingabsbraking==3 = real hard braking (see doc 08)

print("rider skill (lean p95) = %.1f deg   sigma = %.1f deg   corners = %s"
      % (skill, sigma, f"{len(cor):,}"))

print("\nHard-braking rate by how far the corner sits above the rider's own skill:")
cor["band"] = pd.cut(cor.z, [-9, -1, 0, 0.5, 1, 2, 9])
t = cor.groupby("band", observed=True).agg(corners=("hard", "size"), events=("hard", "sum"),
                                           rate_pct=("hard", lambda s: 100 * s.mean()),
                                           req_deg=("req_deg", "median"))
print(t.to_string(float_format=lambda x: "%.2f" % x))

hi, lo = cor.z > 1.0, cor.z < 0.5
a = int(cor.hard[hi].sum()); b = int(hi.sum()) - a
c = int(cor.hard[lo].sum()); d = int(lo.sum()) - c
print("\nrisk zone (z>1)  : %d events / %d corners = %.2f%%" % (a, a + b, 100 * a / (a + b)))
print("at or below (z<.5): %d events / %d corners = %.2f%%" % (c, c + d, 100 * c / (c + d)))
odds, p = stats.fisher_exact([[a, b], [c, d]])
print("Fisher exact: odds ratio %.2f, p = %.4f" % (odds, p))

# cluster bootstrap over RIDES - corners within a ride are correlated
per_ride = cor.groupby("trip").apply(lambda g: pd.Series({
    "hi_n": (g.z > 1.0).sum(), "hi_e": g.hard[g.z > 1.0].sum(),
    "lo_n": (g.z < 0.5).sum(), "lo_e": g.hard[g.z < 0.5].sum()}), include_groups=False).values
rng = np.random.default_rng(0)
n = len(per_ride)
rr = []
for _ in range(20000):
    s = per_ride[rng.integers(0, n, n)].sum(0)
    if s[0] > 0 and s[2] > 0 and s[3] > 0:
        rr.append((s[1] / s[0]) / (s[3] / s[2]))
rr = np.array(rr)[np.isfinite(rr)]
print("cluster bootstrap over %d rides: risk ratio median %.1fx, 95%% CI [%.1f, %.1f], P(>1) = %.0f%%"
      % (n, np.median(rr), np.percentile(rr, 2.5), np.percentile(rr, 97.5), 100 * (rr > 1).mean()))

# continuous version - uses all corners instead of two buckets
from scipy.optimize import minimize
x, y = cor.z.values, cor.hard.values


def nll(prm):
    e = np.clip(1 / (1 + np.exp(-(prm[0] + prm[1] * x))), 1e-9, 1 - 1e-9)
    return -np.sum(y * np.log(e) + (1 - y) * np.log(1 - e))


b1 = minimize(nll, [-6, 0.3]).x[1]
print("logistic trend over all %s corners: slope %+.3f per sigma -> odds of a hard-braking event x%.2f "
      "for every 1 sigma the corner sits above the rider's skill" % (f"{len(cor):,}", b1, np.exp(b1)))

print("\nWHAT WOULD SETTLE IT (the answer to 'your sample is tiny'):")
for n_ev in (50, 200, 1000):
    print("   %5d events (~%5d rides at this event rate) -> 95%% CI on the 3.6x ratio narrows to about +/-%.0f%%"
          % (n_ev, n_ev / 0.15, 100 * 1.96 / np.sqrt(n_ev)))
print("   the crowd lake (77,700 rides) would carry roughly 10,000 - comfortably past the last row.")

print("""
HOW TO STATE THIS (do not overclaim - the honesty is the point):
  "The trend is monotonic across all six bands and the risk ratio is 3.6x. Fisher exact p = 0.071,
   and bootstrapped over rides rather than corners the 95%% interval is [0.0, 17.1]. There are
   thirteen events in the whole sample, so we are NOT claiming significance - we are claiming a
   consistent trend in the predicted direction, and that the crowd lake carries roughly ten thousand
   of these events, which is the first thing we would check with it."
""")

ev = cor[(cor.hard > 0) & (cor.z > 0.5)].nlargest(6, "z")
print("Demo moments - real corners the model called 'above his level' where the bike then braked hard:")
for r in ev.itertuples():
    print("  %.4f,%.4f  req=%2.0f deg  z=%+.2f  elev=%4.0f m  %2.0f km/h  ride %s"
          % (r.lat, r.lon, r.req_deg, r.z, r.elev_m, 3.6 * r.v_ms, r.trip[:8]))
print("\n  47.0766,12.7646 at 2253 m is on the GROSSGLOCKNER HIGH ALPINE ROAD - use that one.")
