# 22 — Phase 3: riders and modes

Written 2026-09-13 on the Mac. Code: `app/modes.py` (new), `router.morton_encode()`, `mode=` through
`router.score_cells / build_graph / route_a_to_b / route_loop` and every `service` answer,
`service._build_riders()` (user C), `service.modes() / default_mode() / suggest_mode() / rhythm_fit()`,
and the tests in `analysis/17_riders_modes.py` → `analysis/out/riders_modes_test.json` (aggregates only).
**Everything ran on real data**: the crowd lake (7,976 rides), user A's 100 raw rides + manifest,
user C's 224 raw rides. Thresholds were written into the script **before the first run** and not
changed after it. Two things were changed after the first run, and both are recorded below rather
than hidden: a bug in the test (the popularity split-half) and the mode mechanism (v1 → v2).

## Verdicts

| Feature | Verdict | Evidence |
|---|---|---|
| lake `morton_code` from a position | **EXACT** | 32 digits = 2·lat bit + lon bit, both axes over 360°, map-matched position: 100% of 66,632 samples (crowd, user A, user C) |
| rhythm purity defect (Phase 2) | **FIXED** | a bin outside the denominator was counted in the numerator: purity reached 4.7; now ≤ 0.97. No Phase 2 verdict moved |
| columns the modes use | **RELIABLE** | split-half ρ: elevation 0.993, prominence 0.743, purity 0.942, popularity 0.88 |
| **user C in the rider switch** | **CALIBRATED** | 592 shared cells, skill 10.65°, gate 21.53°, gate agreement 1.072 |
| user C's skill differs from user A's | **no** | ride-bootstrap CIs overlap: A [10.53, 12.26], C [8.95, 11.38] |
| calibration recipe | **RECIPE-SENSITIVE** | skill from corner cells vs every touched cell: 0.72 σ (A), 0.66 σ (C), bar 0.5 σ |
| beat 3 with user C | **ROAD-STAYS** | Kochel → Tegernsee at Send it: A and C share **100%** of the road |
| F0.4 bike DNA | **NO-STRUCTURE** | silhouette 0.32 (bar 0.50), bootstrap ARI 0.24 (bar 0.70); rev ceiling does not identify the bike (p 0.42) |
| F3.2 modes, v1 (multiplicative) | **FAIL-MECHANISM** | the router escaped a mode by leaving good roads for dull ones |
| F3.2 **scenic** (v2) | **PASS**, small | prominence up on 80% of changed pairs (p < 0.001), median **+1.2 m** |
| F3.2 **mountain** (v2) | **PASS**, small | elevation up on 81% of changed pairs (p < 0.001), median **+2.3 m** |
| F3.2 adventure (v2) | **FAIL** | fewer-ridden roads on only 41% of changed pairs (p 0.91) |
| F3.2 urban (v2) | **PASS, Phase 4** | defined and measured, not offered |
| F3.3 bike → default mode | **DEFAULT-ONLY** | no archetypes to map; every ride opens on Flow |
| F3.4 mood from rpm per km/h | **FAIL** | does not predict the rest of the ride on either rider; the FEATURES.md 0.54 does not replicate |
| F3.5 rhythm match | **NOT-PERSONAL** | user C − user A ride-median wavelength −38 m, CI [−77, +6] |
| riders' rides inside the crowd lake | **RIDES-IN-LAKE**, user A only | sample fingerprints: 3 of user A's 100 rides are ≥ 50% inside, 18 share a sample; user C 0 of 224 |

**The default did not move.** `mode="flow"` skips the new code path. Its scored frame and cost
matrix are bit-identical to a graph built without the argument, and the regression gates reproduce
exactly (see Gates).

## 1. The morton code, decoded

User C's corner table has a position but no cell, so it could not be calibrated. The first guess, a
Bing quadkey, matched **0%** of samples at every prefix. Regressing the two bit streams of the code on
latitude and longitude gave the answer:

- each of the 32 base-4 digits is `2·(latitude bit) + (longitude bit)`;
- latitude is scaled as `(lat + 90) / 360` (over 360°, not 180°) and longitude as `(lon + 180) / 360`;
- the input is the **map-matched** position.

`router.morton_encode()` reproduces all 32 digits on **100%** of samples: 7,374 from 20 random crowd
files, 36,055 from 10 of user A's rides and 23,203 from 10 of user C's. The raw GPS position matches
16 digits 98.5% of the time.

## 2. A Phase 2 defect, found here and fixed

While checking the columns modes would use, `rhythm_purity` had a maximum of **4.73**. A share cannot
exceed 1.

- **Cause:** `10_crowd_layer.py` summed three FFT bins around the peak but divided by the power from
  bin 2 up. When the peak sat at bin 2 (640 m), bin 1 entered the numerator and not the denominator.
- **Fix:** bin 1 is now excluded from the numerator too.
- **Effect on the grids:** only `rhythm_purity` moved.
  - 16 chars: 2,810 of 4,800 cells change; median 0.618 → 0.537, maximum 4.733 → 0.955.
  - 18 chars: 8,907 of 18,573 cells change; maximum 8.856 → 0.966.
  - Every other column is identical (`DataFrame.equals`) and `crowd_gems_s2.csv` is byte-identical.
- **Effect on Phase 2:** `16_road_character.py` reran with **every verdict and every number
  identical**, because no Phase 2 test used purity.
- **Also new:** the halves table gained `elev_mean`, so elevation could be split-half tested.

## 3. The columns modes lean on

Doc 21 tested wavelength, reversals, dwell, traffic, hazard and surprise. It never tested elevation,
prominence, purity or popularity, which are exactly what the modes use. Here they are, on the same
method: disjoint ride halves, ≥ 10 traversals per half (≥ 5 rhythmic rides for purity), 2,000
bootstraps, bar ρ ≥ 0.50.

| Column | Split-half ρ | 95% CI | Cells |
|---|---|---|---|
| `elev_mean` | 0.993 | [0.991, 0.994] | 1,618 |
| `elev_prominence_m` (recomputed per half) | 0.743 | [0.710, 0.770] | 1,618 |
| `rhythm_purity` (after the fix) | 0.942 | [0.931, 0.950] | 1,592 |
| popularity (traversals) | 0.880 | [0.865, 0.894] | 1,618 |

All four are **RELIABLE**. Purity still rank-correlates 0.45 with wavelength: long, lazy bends are also
the purest. Recomputing prominence from the grid reproduces the stored column to within 3.3 m.

**Bug in the first run:** the popularity row came back with n = 0. The test passed `n_traversals` as
both the value and the filter, and the join dropped it. That made adventure and urban read
"COLUMN-UNRELIABLE". It was a test bug, not a data result, and it is fixed.

## 4. User C, the second human

User C's corners are the `09_userC_asymmetry.py` recipe: yaw-sign blocks of ≥ 3 samples at
positionrawheading, with the block's mean map-matched position. User A's 5,253 corners are
`corners_filtered`. **These are different recipes, which is why the recipe test below exists.** User C's
corners get the lake's exact cell via `morton_encode`, then go through the same `calibrate_rider` as
user A's.

| | user A | user C |
|---|---|---|
| corners (in box) | 5,253 | 15,810 (1,959, 21 rides) |
| shared cells | 360 | 592 |
| skill / σ | 11.40° / 5.59 | 10.65° / 5.44 |
| gate | 22.59° | 21.53° |
| hardest road ridden · gate agreement | 21.24° · 1.063 | 20.08° · 1.072 |
| skill, 95% CI resampling rides | [10.53, 12.26] | [8.95, 11.38] |

- **The gate-agreement check replicates on a second human.** For user C, skill + 2σ lands within 7% of
  the hardest road they chose, the same as user A's 6%. Nothing in the construction forces that.
- **The two riders are not measurably different in skill.** Their CIs overlap.
- **The calibration depends on which cells count as "ridden", and that is now measured.**
  Reading skill off every cell the trackpoints touch, instead of the cells with a corner, drops it
  from 11.40° to 7.40° for user A (0.72 σ) and from 10.65° to 7.05° for user C (0.66 σ). The
  pre-registered bar was 0.5 σ, so the verdict is **RECIPE-SENSITIVE**. The shift is the same size and
  direction for both riders, so a switch between them is read on one ruler. The absolute skill number
  is a property of the corner-cell definition, not of the rider alone.

**On the presets** (service config, user A vs user C):

| Pair | Cruise: shared road | Send it: shared road |
|---|---|---|
| Lenggries → Bad Tölz | 100% | **17%**: A rides 53.0 km at 9.7° mean; C gets the 46.9 km, 7.0° road with 1 refusal |
| Lenggries → Kochel | 100% | 30%: A 68.7 km / 9.6°; C 62.6 km / 7.6° |
| Kochel → Tegernsee (beat 3) | 99% | **100%** (A vs `bike_4e1a9d64`: 10.5%, unchanged) |

- **Beat 3 stays.** The pre-registered rule was "rewrite beat 3 only if user C moves Kochel → Tegernsee
  at Send it to ≤ 50% shared road". It is 100%, so `10_LIVE_DEMO.md` beat 3 is not rewritten.
- **A candidate for Phase 5:** on beat 1's own pair, user C's gate sits 1° lower. That refuses a road
  on user A's Send it line, and 83% of the road changes. It is a two-human moment on a pair we
  already rehearse.
- User C's Kochel 2 h Send it loop: 136.0 km, 119.3 min, 89% ridden once.
- `route_tab.py`'s rider help text no longer says there is no second human (string only).

## 5. F0.4 bike DNA: no structure

FEATURES.md says user A's bikes "span 7,210 → 11,745" rpm and that "the bike declares itself through
its rev ceiling". Measured on the manifest:

- **The spec's range is not a range across bikes.** 7,210 and 11,745 are two single bikes' maxima. The
  per-bike maximum spans **4,754 → 11,745**, and it rank-correlates **0.45** with how many rides the bike
  has. A max grows with sample size, so bikes are summarised by medians here.
- **Eligible sample:** 8 bikes with ≥ 3 usable rides, 84 rides.
- **Does the bike explain a feature more than chance?** Between-bike share of variance with 5,000
  label permutations:
  - rev ceiling η² 0.084, p 0.42: **it does not identify the bike**;
  - acceleration 0.21, p 0.02;
  - peak lean 0.30, p < 0.001;
  - ride length 0.33, p < 0.001.
- **Do three archetypes exist?** Exhaustive best 3-partition of the 8 bikes' standardised medians:
  - silhouette **0.32** against a bar of 0.50 (k = 2 would give 0.40);
  - median adjusted Rand index over 1,000 ride bootstraps **0.24** against a bar of 0.70;
  - cluster sizes 1 / 4 / 3.

**Verdict NO-STRUCTURE.** No archetype names are assigned; naming clusters that do not exist would be
decoration. User C has no manifest and would get the default archetype either way.

## 6. F3.2 modes

### Design

- **A mode is a weight vector over percentile ranks of reliable columns.**
  - scenic: + prominence;
  - adventure: − popularity, − purity (broadband), + prominence;
  - mountain: + 2 × elevation, + reversals/km (residential masked);
  - urban (Phase 4): − popularity, − stop rate.
- **No mode carries a demand term.** The Thrill Dial is the demand axis, and `adventure_index` is demand
  again (doc 21, ρ 0.89), so either would count demand twice.
- **Columns left out, and why.** `dwell_share` is redundant with stop rate, traffic is unreliable,
  viewpoints have no data. Scenic therefore rests on elevation alone. The spec's "dwell reward"
  has nothing valid to stand on.
- **Flow is today's router, and it is the default.** The spec's Flow/Fast row (popular, no-stop,
  narrow rhythm) is not re-weighted on top of it, so `mode="flow"` stays exact.
- **Joy is not used to judge modes.** It is WEAK (doc 20). Each mode is judged on its own column.

### The pre-registered test

- **Sample:** user A, service configuration (legal-speed demand, OSM), dial 0.50, on the
  `12_route_calibration` lattice. There are **200** O-D pairs 25–75 km apart with both routes clean.
- **"Changed":** Jaccard(mode route, flow route) ≤ 0.90.
- **PASS needs all of:**
  - ≥ 10% of pairs changed, and ≥ 10 changed pairs;
  - the mode's column moves the intended way on ≥ 70% of changed pairs;
  - a one-sided sign test p < 0.01.
- **Invariance, a hard assertion in the test:** for every mode, `z`, `gated`, the refusal reasons and
  the refused edge set are identical to Flow's.

### v1: multiplicative, FAIL-MECHANISM

- **What v1 did:** it multiplied flow by `1 − 0.5·(1 − preference)`.
- **Result:** scenic's column moved the right way on 34% of changed pairs, mountain's on 68% (p 0.03),
  and adventure and urban went to *more* popular roads.
- **Diagnosis, on the same pairs:**
  - both routes are optimal in their own graph, and the preferences rank correctly (scenic ρ 1.0
    with prominence), so the code did what it said;
  - the extra cost was `λ·L·flow·0.5·(1 − pref)`, which is **zero wherever flow is already zero**;
  - the cells only the mode route used had base flow **0.10** against **0.40** for the flow-only cells,
    and a *lower* mode preference in 72–74% of pairs.
- **In plain words:** the cheapest way to escape a mode was to leave the good roads for dull ones, where
  the mode cannot see you. That is a mechanism error, not a finding about scenery.

### v2: additive, the one re-run

- **The change:** the mode became its own term, `cost = L·(1 + λ·(1 − flow + 0.5·(1 − pref)))`. Flow is
  not touched, so fit numbers and the gate cannot move.
- **Scope of the re-run:** same test, same bars, same pairs, run once. Whatever it said was final.

| Mode | Pairs changed | Column moved right way | Sign p | Median change on changed | km ratio vs Flow: median / max | Mean flow change | Verdict |
|---|---|---|---|---|---|---|---|
| scenic | 37.5% (75) | 80% | < 0.001 | prominence **+1.2 m** | 1.00 / 1.17 | −0.05 | **PASS** |
| mountain | 26% (52) | 81% | < 0.001 | elevation **+2.3 m** | 1.00 / 1.29 | +0.00 | **PASS** |
| adventure | 22% (44) | 41% | 0.91 | fewer rides −0.2 | 1.00 / 1.05 | −0.04 | **FAIL** |
| urban (Phase 4) | 30% (60) | 78% | < 0.001 | 1.7 fewer rides per cell | 1.00 / 1.05 | −0.01 | **PASS**, not offered |

**Read the size, not only the verdict.** Scenic and mountain point the right way reliably, but a
median of one or two metres of prominence or elevation is not a different kind of ride. They hit the
same corridor ceiling as the dial (doc 14): the median detour is 1.00×. Mountain reaches 1.29× on
its best pair, beyond the dial's 1.137× maximum. The wording that is allowed is **"leans the route
towards higher ground where the network offers a choice"**. "Takes you into the mountains" is not.

`service.modes()` offers **flow, scenic, mountain**. It lists adventure as FAIL and urban as Phase 4.
The Streamlit UI is frozen and does not show modes.

## 7. F3.3 bike → default mode: DEFAULT-ONLY

With no archetypes (F0.4), there is nothing to map a bike from. `service.default_mode()` returns Flow
for every rider and says why. The test is in the script for the case where archetypes exist; it did not
run here.

## 8. F3.4 mood: FAIL

- **Signal:** median `rpm / (3.6·v)` over moving samples in the first ten minutes (bus speed only;
  GPS speed is not a gear).
- **Outcome:** lean p90 over the rest of the ride.
- **Sample:** rides of ≥ 20 minutes. For user A, values are demeaned within bike (gearing differs by
  bike) on bikes with ≥ 3 rides.
- **PASS needs:** ρ ≥ 0.30 with CI above 0 on both riders, **and** a partial correlation above 0 after
  controlling for first-ten-minute lean.

| | user A (33 rides, 6 bikes) | user C (101 rides) |
|---|---|---|
| FEATURES.md claim replicated: whole-ride rpm/kmh vs median lean | ρ −0.02 [−0.36, 0.32] | ρ **−0.21** [−0.37, −0.035] |
| first 10 min rpm/kmh → rest-of-ride lean | ρ 0.02 [−0.35, 0.39] | ρ **−0.22** [−0.39, −0.04] |
| beyond first-10-min lean (partial) | −0.03 [−0.41, 0.35] | −0.14 [−0.33, 0.04] |
| first-10-min lean alone → rest | −0.21 [−0.57, 0.15] | **0.53** [0.35, 0.68] |
| tercile agreement κ | 0.14 | −0.19 |

- **The claimed 0.54 does not replicate.** On user C the sign is reversed and its CI excludes 0.
- **For user C, the first ten minutes of lean predict the rest far better than the gear does.** That
  does not replicate on user A.
- `detect_mood()` exists as a backend function. `service.suggest_mode()` answers with the FAIL verdict
  and suggests nothing.

## 9. F3.5 rhythm match: NOT-PERSONAL

- **Method:** each rider's rhythmic windows come from `10_crowd_layer.process_ride` itself (the same
  10 m, 128-sample Hann, hop-16 code as the crowd), so the method is the same by construction.
- **Windows:** user A 18,046 over 85 rides, median wavelength 434.6 m; user C 23,332 over 169 rides,
  401.7 m.
- **h:** the median absolute split-half difference of crowd cell wavelength, **7.3 m** over 1,592 cells.

**Results:**
- **Raw:** user C − user A ride-median wavelength **−38 m, CI [−77, +6]**, over 75 and 135 rides. It
  includes 0, so the verdict is **NOT-PERSONAL**.
- **Residual against the crowd wavelength of the same cell:** 0.0, CI [0.0, 0.0], over 17 and 17 rides.
  This is degenerate, and was investigated:
  - wavelength is coarsely resolved: 20% of all windows sit on 10 values, and 17% of crowd cells have
    exactly the same median in both disjoint halves;
  - 16% of rider windows equal their cell's crowd median exactly.

  - so the next question was whether these riders' own rides are inside the crowd, which would make
    the residual self-referential.

**Provenance.** This test was added after the first run and uses no random draws, so every other
number in the file reproduced identically.
- **By id:** trip ids and file names overlap 0 of 100 (user A) and 0 of 224 (user C). The lake is
  anonymised, so that proves nothing.
- **By sample fingerprint:** each sample is hashed on its 32-digit cell (centimetres) + lean + rpm, as
  recorded, giving 2,583,234 distinct lake samples.
  - user A: **3 of 100 rides** have ≥ 50% of their samples in the lake, and 18 share at least one;
  - user C: **0 of 224** (2 share a sample).
- **Verdict RIDES-IN-LAKE**, for user A only, at 3 rides out of 7,976.

**What that does and does not change:**
- **User A's calibration** reads a crowd ruler that contains three of their own rides. At that share
  it is negligible, but it is not zero.
- **It cannot explain the degenerate residual.** User C has no rides in the lake and shows the same
  0.0. The residual test is limited by wavelength resolution, so it is **uninformative**, not evidence
  either way. The verdict rests on the raw comparison, which includes 0.

`service.rhythm_fit()` answers with the verdict and computes nothing.

## Gates

Run on the Mac after the rebake. `service.init()` from `demo.pkl` loads in 13 ms and now reports
4 riders and `riders_modes: True`. The bake is 6.1 MB and took 2.6 s.

**All pass.**

| Gate | Result |
|---|---|
| Lenggries → Bad Tölz headline | "Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked of you." (identical) |
| Kochel → Tegernsee overlap | 0.848 (identical) |
| Kochel 2 h Send it loop | 133.4 km / 118.7 min / 0.936 (identical) |
| `bike_4e1a9d64` switch at Send it | 10% shared (identical) |
| user C offered in `riders()` | yes; Kochel → Tegernsee Send it shares 100% with user A |
| `modes()` | offers flow, scenic, mountain; adventure FAIL; urban PASS but Phase 4 |
| `default_mode()` · `suggest_mode()` · `rhythm_fit()` | Flow (DEFAULT-ONLY) · not offered (FAIL) · not offered (NOT-PERSONAL) |
| scenic / mountain on Kochel → Tegernsee Send it | route ok, 25% shared with Flow, `gated` identical |
| AppTest | 0 exceptions, 5 tabs |
| Phase 2 rerun after the purity fix | every verdict and number identical |

**Note on the refusals list.** The "refused roads nearby" differ between a mode route and the Flow
route. That is not the gate moving: the gated cells and the refused edge set are asserted identical
for every mode, across all 200 scan pairs. The list is what sits *next to the route*, and the mode
route runs on other roads. On beat 3's pair, scenic at Send it moves 75% of the road, where the dial
moves 15%.

## Reproduce

```
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake FS_OUT=$PWD/analysis/out
FS_CELL_CHARS=18 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _s2
FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
$V analysis/16_road_character.py      # Phase 2 verdicts, unchanged
$V analysis/17_riders_modes.py        # this doc
$V analysis/14_bake_demo.py
```
