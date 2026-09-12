# 20 — Phase 1: the Joy Meter, and the grip-budget test

Written 2026-09-13 on the Mac. `app/joy.py` + `analysis/15_joy_meter.py` (10.3 s).
**Everything here ran on real BMW telemetry**: user A's 508,183 trackpoints over 100 rides, and
user C's 535,608 trackpoints over 224 raw ride CSVs. Thresholds were written into the script
**before the first run** and were not changed after it.

## Verdicts

| Test | User A | User C |
|---|---|---|
| **Joy Meter (F1.1)**, length-matched | **WEAK** — AUC 0.675 [0.508, 0.828] | **WEAK** — AUC 0.637 [0.509, 0.764] |
| **Grip budget (F1.3)** | **FAIL** — AUC 0.550 [0.450, 0.670] | **FAIL** — AUC 0.528 [0.444, 0.612] |
| Learned weights (F1.2) | **not attempted** — 11 of 83 planned routes inside the coverage box | — |

Pre-registered rule: PASS = AUC ≥ 0.70 with CI lower bound > 0.5 · WEAK = AUC ≥ 0.60 · FAIL below.
Joy flagged as "just length" if |spearman(joy, km)| ≥ 0.5 — **not flagged** on either rider.

## What the Joy Meter is

Four components, each a rate or a share so a longer ride cannot score higher for being longer:

| | Component | Meaning |
|---|---|---|
| E | g–g envelope | area of the polygon through the per-sector p90 radius of (tan lean, a_long) |
| R | lean reversals / km | left-right lean changes past 5° |
| T | throttle entropy | how much of the throttle range is used, 0..1 |
| U | uninterrupted share | share of distance above 15 km/h |

`joy` = mean z-score of the four against the rider's own usable rides.

**Removed from the FEATURES.md design, on purpose:**
- **F = ride speed ÷ crowd speed.** It scores riding faster than the crowd. We never score speed.
- **C = completion / loop closure.** Commutes are one-way and weekend rides are loops, so it would
  pass the test on route geometry rather than on fun. Kept as a descriptor, not a component.
- **E as a convex hull per km.** A hull grows with sample count and shrinks when divided by km —
  either way it measures length. Replaced by a percentile polygon.

## The test, and why it is length-matched

FEATURES.md asks whether Joy separates commutes from long rides. Done naively that is nearly free:
long rides are on open roads, so anything correlated with distance passes. So the verdict is read
off a **length-matched** version: every long ride (> 100 km) is cut to a window from its **middle**,
as long as the median commute (8.9 km for A, 9.2 km for C), and compared against whole commutes
(5–20 km). Same distance on both sides. Bootstrap over rides, 2,000 draws.

```
                          USER A  (47 commutes vs 21 long)     USER C  (108 vs 18)
length-matched            AUC    95% CI                         AUC    95% CI
  E  envelope             0.475  [0.301, 0.652]                 0.391  [0.255, 0.532]
  R  reversals / km       0.681  [0.505, 0.846]                 0.279  [0.165, 0.412]   <- flips
  T  throttle entropy     0.659  [0.496, 0.809]                 0.843  [0.722, 0.940]
  U  uninterrupted        0.916  [0.838, 0.976]                 0.951  [0.893, 0.989]
  joy                     0.675  [0.508, 0.828]                 0.637  [0.509, 0.764]

whole-ride joy            0.722  [0.581, 0.858]                 0.822  [0.723, 0.916]
spearman(joy, km)         +0.435 (all) / +0.349 (20-100 km)     +0.344 / +0.128
```

## What it actually says

1. **Only U replicates cleanly.** Share of distance kept above 15 km/h separates open-road riding
   from commuting on both riders, length-matched, with CIs far from chance. That is BMW's own RED
   flag — inner city and standstills — and **the router already scores it** through `stop_rate` and
   the OSM residential penalty. So the one component that survived is independent confirmation of
   a term we already route on, measured from a different direction (rides, not cells).
2. **T mostly replicates**: clear on C, just touching chance on A length-matched (CI 0.496).
3. **R does not replicate — it flips.** On user A long-ride stretches have more lean reversals per
   km; on user C commutes have far more (AUC 0.279). Most likely town junctions: every turn at a
   crossroads is a lean reversal. **The "esses signal" (F2.6) is confounded by junctions** and must
   not be used as a GREEN flag without masking urban cells.
4. **E does not separate** on either rider, and leans the wrong way on C. Note the conservative
   bias built in: fast rural windows have fewer samples per km, so fewer sectors fill.
5. **The composite is WEAK, and we are not rescuing it.** A U+T-only meter would score higher on
   this same data — but that would be choosing the formula after seeing the answer. It is not
   reported as a pass.

**The label is a proxy.** There is no ground-truth "fun" in the data. Commute vs open-road ride is
the best available stand-in, and a meter that passes it is detecting open-road riding at least as
much as enjoyment. Say that if asked.

## Grip budget — the mechanism claim does not hold

FEATURES.md's line: *"ABS doesn't fire because a corner is hard. It fires because the grip budget
was spent on cornering and there was nothing left to brake with."*

The obvious test is circular — `grip_used` includes `a_long`, and `a_long` **is** the braking. So:
among **hard-braking samples only** (a_long ≤ −0.2 g, same deceleration), is lateral grip higher
when ABS code 3 fires?

```
                        hard-brake samples   ABS==3   rides   lateral grip ABS / no-ABS   AUC
USER A                        7,869             53       25        0.068 / 0.051          0.550 [0.450, 0.670]
USER C                       41,857            601       69        0.057 / 0.052          0.528 [0.444, 0.612]

P(ABS | hard brake) by lean   <10 deg        10-20 deg      >20 deg
USER A                        0.62%          0.93%          0.67%
USER C                        1.37%          1.24%          2.47%
```

**Not supported on either rider.** User C shows a hint above 20° of lean, but the overall effect is
indistinguishable from chance. This agrees with doc 13 (ABS is orthogonal to cornering demand,
ρ = +0.05). **Never say the grip-budget line on stage.** `grip_used()` stays in the product as a
readout of how much tyre a route asks for — that is physics, not this claim.

## F1.2 learned weights — blocked, and what replaces it

It needs each planned route compared against the router's alternative between the same endpoints.
Only **11 of 83** parsed planned GPX routes are ≥50% inside the crowd coverage box. Eleven pairs
cannot carry four weights. The per-component AUC table above is the honest answer to "how are the
terms weighted": measured discriminative power, stated, not fitted.

## Exposure

`service.py`:
- `rider_joy(key)` → verdict, per-component AUC + CI, grip-budget result, and sentences. A component
  is named as "carrying" the meter only if it clears chance **on both riders**; one that flips is
  named as not trusted. Bike profiles report the user-A test and say the bike alone has too few rides.
- `ride_joy(trip_id)` → one ride's components and joy.
- `status()` gains `joy_rides`. The bake carries the joy block (5.3 MB, 2.4 s).

## Gates

```
regression  Lenggries -> Bad Tolz headline identical · Kochel -> Tegernsee overlap 0.848 ·
            Kochel 2 h loop 133.4 km / 118.7 min / 0.936        PASS
init        11 ms from the bake, 324 joy rides loaded
AppTest     0 exceptions, 5 tabs
```

## Consequences for the later phases

- **Phases 3-4 may REPORT joy; they must not optimise routes on it.** At WEAK it is a measurement,
  not an objective. Phase 4's Pareto trades minutes against mean demand / flow, with joy shown beside.
- **Phase 2's cell-level reversals need junction masking** (OSM residential cells out) before they
  mean anything.
- **Open data question:** user C's `a_long` reaches p99 +1.10 g against user A's +0.24 g. Clipped
  at 1.0 g here. Whether that is a different sensor, a unit difference or noise is untested; it
  touches E and the hard-brake threshold for user C only.
- **Pitch (Phase 5):** both results belong on slide 7. A Joy Meter we built, tested against a
  pre-registered bar, and report as WEAK is more credible than one we only describe.

## Reproducing

```bash
cd ~/ehl_urich/flowstate
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
PYTHONIOENCODING=utf-8 $V analysis/15_joy_meter.py   # 10 s -> joy_rides.parquet (gitignored) + joy_test.json
$V analysis/14_bake_demo.py                          # 2.4 s
```
