# 23 — Phase 4: new answer types

Written 2026-09-13 on the Mac. Code: `router.route_loop_arc()` with `loop_profile / arc_error /
arc_target`; `router._loop_setup / _loop_paths / _path_sum_checked`, the shared loop internals;
`service.loop_arc() / pareto() / nondominated() / gem_cells()`; and the tests in
`analysis/18_answer_types.py` → `analysis/out/answer_types_test.json` (aggregates only, 108 s).
**Everything ran on real data**: user A calibrated on the crowd grid, the 4 preset loop starts, the
200-pair O-D lattice, both riders' raw rides, and the crowd halves. Thresholds were written into the
script before the first run. **Joy is WEAK (doc 20). It was never an objective or a judge here.**

## Verdicts

| Feature | Verdict | Evidence |
|---|---|---|
| `stop_rate` across disjoint rides | **RELIABLE**, at the bar | split-half ρ 0.511 [0.466, 0.554], 1,618 cells |
| F4.3 loop as a dramatic arc | **FAIL** | achieved on **2 of 12** loops (bar 9). The candidates cap it at 3 of 12 |
| F4.2 A→B Pareto frontier | **PASS, short** | ≥ 3 non-dominated routes on 59.5% of 200 pairs; median span **3.5 min for +0.21°** |
| F4.6 commute upgrade | **BLOCKED-COVERAGE** | 0 of user A's 45 commute-length rides, and 1 of user C's 106, are inside the box |
| F4.5 urban wander | **FAIL** | the urban loop is calmer and less ridden than Flow in **0 of 6** towns |
| F4.4 edge-disjoint return | **BUILT-EARLIER** | `route_loop`'s 6× reuse penalty (doc 16) |
| F4.7 safety gate, visible | **BUILT-EARLIER** | refused edges are deleted and listed with a reason (docs 14, 17) |
| F4.8 solar & thermal | **NOT-BUILT** | T4 in FEATURES.md, out of scope by doc 19 |

**Nothing existing moved.** `route_loop` now shares its setup and candidate generation with the arc
loop through `_loop_setup` and `_loop_paths`, the same code rather than a copy. All **21/21** baked
preset answers (12 loops, 9 routes) come back identical, cell for cell and summary for summary. The
crowd grids rebuilt identical; the halves table gained only `stop_rate`.

## F4.3 — the loop as a dramatic arc: FAIL

**Construction.**
- The target shape: warm-up at 35% of the loop's own flow range, peak at 67.5% of the distance, easy
  return at 45%.
- A loop's profile is flow per step along the ride, smoothed over 5 km, resampled to 40 points and
  min-max normalised.
- **Arc error** is the RMS distance from the target shape.
- **Candidates** are exactly `route_loop`'s ring, plus crowd gems that fit the ring as turnarounds.
  Each is ridden **either way round**, since a loop read backwards peaks at the other end.
- **Constraints:** a candidate may win only if it keeps ≥ 90% of today's loop's mean fit, ≥ today's
  distinct share − 5 points, and the time budget.
- Today's loop is itself a candidate, so the arc loop can only equal or improve the shape.

**Pre-registered bar.** "Achieved" needs arc error ≤ 0.75 × today's **and** the best riding in 55–80%
of the ride **and** budget fill within ±20%. PASS needs ≥ 9 of the 12 loops (4 starts × 1/2/3 h,
user A, dial 0.50).

| Start | h | Today: error / peak at | Arc: error / peak at | Minutes (today → arc) | Shared cells | Reversed | Gem turn | Achieved |
|---|---|---|---|---|---|---|---|---|
| Kochel | 1 | 0.353 / 51% | 0.338 / 56% | 60.0 → 67.3 | 95% | no | yes | no |
| Kochel | 2 | 0.328 / 49% | **0.229 / 79%** | 118.7 → 106.4 | 96% | yes | no | **yes** |
| Kochel | 3 | 0.404 / 36% | 0.381 / 41% | 144.9 → 144.9 | 100% | yes | no | no |
| Holzkirchen | 1 | 0.357 / 11% | 0.254 / 89% | 55.8 → 54.8 | 100% | yes | no | no (peak) |
| Holzkirchen | 2 | 0.356 / 46% | 0.311 / 54% | 98.3 → 96.0 | 100% | yes | no | no |
| Holzkirchen | 3 | 0.439 / 51% | 0.357 / 54% | 176.5 → 163.5 | 96% | yes | no | no |
| Schliersee | 1 | 0.476 / 34% | 0.365 / 4% | 59.6 → 70.8 | 24% | yes | no | no (peak) |
| Schliersee | 2 | 0.416 / 54% | 0.318 / 56% | 134.2 → 121.2 | 45% | yes | yes | no |
| Schliersee | 3 | 0.375 / 71% | 0.299 / 86% | 194.3 → 202.8 | 97% | yes | no | no |
| Lenggries | 1 | 0.435 / 84% | 0.342 / 86% | 60.5 → 64.4 | 76% | yes | yes | no |
| Lenggries | 2 | 0.349 / 26% | **0.244 / 64%** | 120.8 → 126.1 | 98% | yes | no | **yes** |
| Lenggries | 3 | 0.496 / 19% | 0.376 / 94% | 161.7 → 189.1 | 19% | no | yes | no |

**2 of 12 → FAIL.**
- **Shape improved.** Median arc error went from 0.39 to 0.33.
- **Reversal did most of the work.** The winning loop was the same road ridden the other way round in
  10 of 12 cases. A gem was the turnaround in 4.
- **Time cost:** 265–494 ms per arc loop, against 102–216 ms for today's.

**Why it failed, checked before accepting it.** Doc 22 found a wrong mechanism behind a failure, so
this one was diagnosed too, on the same candidates.
- **Is the objective at fault?** For each loop the question was whether *any* candidate that satisfies
  the constraints has its peak in the window **and** error ≤ 0.75 × today's.
  - Only **3 of 12** loops have one: Kochel 2 h (3 candidates), Holzkirchen 1 h (2) and
    Lenggries 2 h (10).
  - The objective found two of them. On Holzkirchen 1 h it picked a loop peaking at 89% whose error
    (0.254) beat the best in-window candidate (0.259) by 0.005.
- **The ceiling is in the network, not in the objective.** A perfect objective would reach 3 of 12.
  Around most starts the crowd graph does not offer a closed tour whose best five kilometres sit at
  two-thirds of the ride.
- **So there is no v2.** Unlike doc 22's modes, there is no mechanism error to fix.

`service.loop_arc()` answers with the FAIL verdict. `loop()` stays the answer. The functions stay in
`router.py` for Phase 5 and for anyone who wants to see the profiles.

## F4.2 — the A→B Pareto frontier: PASS, but short

**Construction.**
- **Sweep:** dial × offered mode: z* ∈ {0.15, 0.30, 0.50, 0.70, 0.90} × {flow, scenic, mountain} =
  15 routes per pair.
- **Not swept:** λ, which saturates (doc 14).
- **Axes:** minutes ↓ and mean demand ↑. Mean demand is used because it is absolute; flow is fit to
  its own dial and cannot be compared across settings.
- **Front:** distinct routes (by cells) that no other route beats on both axes.

**Pre-registered bar:** a frontier worth drawing has ≥ 3 distinct non-dominated routes on ≥ 50% of
pairs.

| Measure | Value |
|---|---|
| pairs with all 15 routes clean | 200 |
| distinct routes per pair, median | 6 |
| front size: 1 / 2 / 3 / 4 / 5 / 6 / 7+ | 20 / 61 / 28 / 26 / 31 / 18 / 16 |
| **pairs with ≥ 3 on the front** | **59.5% → PASS** |
| fronts that use a non-Flow mode | 78.5% |
| front span (fronts of ≥ 2), median | **+3.5 min for +0.21° mean demand** |

**How different are the routes on a front?** This was measured after the verdict, and it does not
change it.
- **The two ends** (fastest vs most lean) share a median **67%** of their cells. 26% of fronts have
  ends sharing ≥ 90%.
- **Neighbouring routes** on a front share a median **95%** of their cells.

**What that means.** The frontier is real but short and incremental. It is mostly the same corridor
with small swaps, which is the corridor ceiling of docs 14 and 22 again. `service.pareto()` offers it,
and the honest sentence is "on this network the extra lean costs minutes, not an hour — and the
choices are variations on one road". FEATURES.md's "eight extra minutes buys 60% of the joy" cannot be
said: Joy is WEAK, and nothing is measured for a route that has not been ridden.

## F4.6 — commute upgrade: BLOCKED-COVERAGE

FEATURES.md's premise ("51 of user A's 101 rides are under 20 km, he's commuting") is true, but the
commutes are not where the crowd is.

| | commute-length rides (5–20 km) | ≥ 50% inside the box | habitual (shares ≥ 50% of cells with ≥ 2 others) |
|---|---|---|---|
| user A | 45 | **0** | 0 |
| user C | 106 | **1** | 0 |

Pre-registered bar: ≥ 10 habitual in-box commutes for at least one rider. There are none. The router
has no crowd data where these riders commute, so there is nothing to upgrade. Not built.

## `stop_rate` split-half, and F4.5 urban wander: FAIL

**`stop_rate`** had never been split-half tested, and urban wander rests on it. It replicates at ρ
**0.511** [0.466, 0.554], just over the 0.50 bar, so it counts as RELIABLE.

**The urban wander test.** A 1 h loop at dial 0.50 in urban mode (fewer rides, fewer stops) against
Flow, from six town centres inside the box. PASS needed a **lower stop rate AND fewer rides per cell**
in ≥ 5 of 6 towns.

| Town | Flow: stop rate / rides per cell | Urban: stop rate / rides per cell | Shared cells |
|---|---|---|---|
| Weilheim | 0.045 / 17.3 | 0.062 / 15.1 | 1% |
| Garmisch-Partenkirchen | 0.067 / 70.5 | 0.067 / 70.0 | 99% |
| Starnberg | 0.117 / 19.0 | 0.063 / 21.5 | 19% |
| Bad Tölz | 0.059 / 18.7 | 0.052 / 19.4 | 77% |
| Miesbach | 0.090 / 10.1 | 0.090 / 10.1 | 100% |
| Murnau | 0.039 / 19.9 | 0.039 / 19.9 | 99% |

**0 of 6 → FAIL.** In three towns the urban loop is the Flow loop.
- **Where it does move:** fewer stops come with more-ridden roads (Starnberg, Bad Tölz), or the
  reverse (Weilheim).
- **These are not urban answers.** A one-hour loop covers 51–78 km and leaves the town. Residential
  share is 0–10%.
- **BMW's own RED inner-city flag** (× 0.45 on residential) stays on in every mode, by design.
- **Time of day is not computable.** Crowd timestamps are shifted, so "the city flows on a Sunday
  evening" cannot be measured.

The urban mode stays defined and not offered.

## What the app may now say

- **May:** "Here is the trade-off for this trip: a few more minutes buys a little more lean, and these
  are the routes on the edge of it." Use the numbers from `pareto()`, never a knee or a joy share.
- **May not:** "We compose your loop as a dramatic arc." That is tested and failed on this network.
- **May not:** "We upgrade your commute" or "urban wander". Both are blocked or failed, with the
  reasons above.

## Gates

Run on the Mac after the rebake: `demo.pkl` is 6.1 MB and took 2.5 s; `service.init()` loads it in
12 ms. **All pass.**

| Gate | Result |
|---|---|
| Lenggries → Bad Tölz headline | "Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked of you." (identical) |
| Kochel → Tegernsee overlap | 0.848 (identical) |
| Kochel 2 h Send it loop | 133.4 km / 118.7 min / 0.936 (identical) |
| `bike_4e1a9d64` switch at Send it | 10% shared (identical) |
| all baked answers after the `route_loop` refactor | **21/21 identical** (cells and summaries) |
| `modes()` | flow, scenic, mountain offered; adventure and urban not |
| `loop_arc()` | "arc loop verdict FAIL; loop() is the answer" |
| AppTest | 0 exceptions, 5 tabs |

**`pareto()` on the demo's own pair.** On Lenggries → Bad Tölz the frontier is **one route**: Flow at
z* 0.70, 53.0 km, 40.1 min, 9.7° mean demand. The Send it road is both faster than the Cruise road (40
vs 43 min, doc 10 beat 1) and leans more, so it dominates. That is the one-point case the size table
counts. Here the trade-off is not a trade: the better road is also the quicker one. Beat 1 already
says so ("forty minutes against forty-three"), so nothing in the demo script changes.

## Reproduce

```
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake FS_OUT=$PWD/analysis/out
FS_CELL_CHARS=18 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _s2
FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
$V analysis/17_riders_modes.py        # the offered modes Pareto sweeps over
$V analysis/18_answer_types.py        # this doc
$V analysis/14_bake_demo.py
```
