# 19 — the FEATURES.md build, in phases

Written 2026-09-13. Source: `~/Downloads/FEATURES.md` (not in the repo; it is
stale — it predates the router, the ROUTE tab and OSM, and it contradicts doc 14 in places).
**This doc is the operative plan.** Features are grouped by where they land in the code, and
the hardest group goes first.

## The loop, every phase

1. Build → verify by **running it** on the Mac (never by reading it).
2. Regression gate: the three presets must still return today's numbers unless the phase
   deliberately changes the default — `1.13x / 83% different / +2.7 deg` on Lenggries -> Bad Tolz,
   overlap 0.848 on Kochel -> Tegernsee, Kochel 2 h loop 133 km / 119 min / 94% distinct.
3. Rebake `analysis/14_bake_demo.py`; `service.init()` still loads; AppTest 0 exceptions.
4. Write the phase doc + verdict rows + CONTEXT phase table.
5. **Merge**: commit, push, `git pull --ff-only` on the Mac, both at the same hash.
6. **Compact**, then start the next phase from the post-compact prompt.

A feature that fails its own test is **recorded as failed and not wired into routing**. That is
a result, not a reason to skip the doc.

## Order

Sequenced by difficulty and dependency, **not by the clock — nothing is cut for time.**

| Phase | Group | Depends on |
|---|---|---|
| 0 | plan + fix the one-rider error | — |
| **1** | **THE FROG — measure fun on a ride** | — |
| 2 | road character columns | — |
| 3 | riders and modes | 2 (columns), 1 (Joy, to judge modes) |
| 4 | new answer types | 1 (Joy), 2 (gems), 3 (modes) |
| 5 | integration: rebake, pitch + demo refresh, verify | all |

---

## Phase 0 — plan, and correct the one-rider claim  *(this commit)*

`06_PITCH.md`, `10_LIVE_DEMO.md` and doc 18 said there is one rider. **There are two riders with
personal telemetry**: `exampleUserA` (101 rides, 20 bikes, 508,183 trackpoints) and
`exampleUserC` (224 raw ride CSVs, 15,810 corners, no bike manifest). The crowd lake itself has
no rider ids. The claim came from doc 16 ("there is no user B"), which was true and was then
over-read. Corrected in all three docs. Leave-one-rider-out stays off the slides: with two
riders it is a pair of anecdotes, not a validation.

## Phase 1 — THE FROG: measure fun on a ride  (Layer 1)

> **DONE — doc 20.** Joy Meter **WEAK** on both riders (length-matched AUC 0.675 A, 0.637 C);
> only U (uninterrupted share) replicates; R (reversals) flips sign between riders; grip-budget
> mechanism **REJECTED** (AUC 0.55 / 0.53); F1.2 blocked by coverage. Joy is exposed as a
> measurement with its verdict and is **not** an optimisation target for Phases 3-4.

Why first: it is the hardest, the likeliest to fail its own test, the one the file calls "the
thing that wins it" — and it produces the **outcome metric** that Phases 3 and 4 trade on. A
mode or a Pareto curve with no measure of fun is a slider.

| Feature | Lands in | Notes |
|---|---|---|
| **F1.1 Joy Meter** | new `app/joy.py` (pure functions over a trackpoint frame) + `analysis/15_joy_meter.py` (per-ride table) | components below |
| F2.6 lean reversals / km (ride level) | `joy.py` | it is Joy's R term |
| F1.3 grip-vs-ABS test | `analysis/15_joy_meter.py` | `grip_used()` already exists in `router.py`; the test was never run |
| F1.2 learned weights | `analysis/15_joy_meter.py` | **blocked as specified** — see below |
| exposure | `service.py`: `ride_joy()`, `rider_joy()` | bake extended |

**Joy components.** `E` g–g hull area per km (`scipy.spatial.ConvexHull`, `a_lat = tan(lean)`),
`R` lean sign reversals with |lean|>5° per km, `T` throttle entropy, `U` share of distance above
15 km/h, `C` completion. **The file's `F = ride speed ÷ crowd speed` is DROPPED** — it scores
riding faster than the crowd, which breaks "never score speed or lap times". Say so in the doc.

**Data traps to handle, not rediscover:** lean invalid below 0.5 m/s (side stand ≈ −15°); all
three speed channels zero on 27 of user A's 100 rides — exclude and count them; 40 of 100 rides
have gaps >10 s — split before differentiating; `a_long` is already in g.

**The stop-gate test.** Does Joy separate user A's 51 rides under 20 km from the 20 over 100 km
**using only these terms**? AUC per component and combined, bootstrapped over rides, plus the
partial correlation with distance and duration. If Joy is just ride length, it FAILS, it is
recorded as failed, and it is not used by Phases 3-4.

**F1.2 as specified cannot be fitted.** It needs each planned route compared with the router's
alternative between the same endpoints, and **only 11 of 83 parsed planned GPX routes are ≥50%
inside the coverage box** — measured on the Mac. Eleven pairs cannot carry five weights. Fallback,
decided now: z-scored components with equal weights, and the **per-component AUC table is the
answer to "how are the terms weighted"** — measured discriminative power, not invented weights.
That table is also the honest replacement for the ablation slide 6 does not have.

Run the same meter on user C: a second human is the only out-of-sample check available.

## Phase 2 — road character columns  (Layer 2)

> **DONE — doc 21.** Split-half reliability across disjoint rides (the lake has no rider ids) plus
> a physical or external test per column, all pre-registered. **Pass:** FFT rhythm (ρ 0.93, vs
> radius 0.38), cell reversals/km (ρ 0.92), adventure index (but ≈ demand, ρ 0.89). **Readout:**
> hazard REPEATABLE (RR 2.89) and surprise PASS (braking ratio 1.87, radius-stratified), both in
> `explain()` as safety lines. **Not usable:** dwell_share redundant with stop_rate (0.92), traffic
> UNRELIABLE (0.36), viewpoints INSUFFICIENT-DATA (0 candidates: trips end where riders stop).
> Gem pool exposed, 43/100 routable for user A. Default route identical; old grid columns identical.

All new per-cell columns in `analysis/10_crowd_layer.py` (13.8 s rebuild, 24 s after), read by
`router.score_cells`. **Scoring only; the default route must not change.**

| Feature | Column / use |
|---|---|
| `dwell_share` | missing today — `router.py` says so in a comment. Prerequisite for F2.8 |
| F2.6 reversals / km | cell-level version of Phase 1's R — **flipped sign between riders in doc 20; mask OSM residential cells before trusting it** |
| F2.5 FFT rhythm | lean resampled every 10 m by distance, dominant wavelength + bandwidth. Heaviest item in the phase |
| F2.7 adventure index | `demand_p90 / log1p(n_rides)` |
| F2.8 crowd-mined viewpoints | high dwell AND high elevation AND far from ride start/end. **Mask zero elevation (46-51%).** Validate against OSM `tourism=viewpoint` via a cached Overpass fetch following `13_osm_layer.py` — BMW data is not transmitted |
| F2.9 traffic on good roads | high demand, speed ≪ crowd median, collapsed throttle entropy, no ABS |
| F2.3 hazard, F2.10 surprise | wired as **safety readout** in `explain()`, never the fun score. Say "three of the five trips that ride this stretch", never "the crowd brakes here" |
| F2.4 gems | exposed as a candidate pool for Phase 4's arc loop |

## Phase 3 — who is riding, and what kind of ride  (Layer 3 + riders)

> **DONE — doc 22.**
> - **Morton decoded exactly.** It is lat/lon bits interleaved over 360°, 100% of samples.
> - **User C in the rider switch.** CALIBRATED: 592 cells, gate agreement 1.072. Skill is not
>   distinguishable from user A's. Beat 3 stays (100% shared at Send it).
> - **Recipe.** Calibration is RECIPE-SENSITIVE (0.7 σ).
> - **Bike DNA.** NO-STRUCTURE (silhouette 0.32, ARI 0.24; rev ceiling does not identify a bike),
>   so bike → mode is DEFAULT-ONLY.
> - **Modes.** v1 (multiplicative) failed on mechanism. v2 (additive): scenic and mountain PASS on
>   direction, but the effect is only +1–2 m. Adventure FAIL; urban PASS, left for Phase 4.
>   Flow is bit-identical and the gate is mode-invariant.
> - **Mood** FAIL (the 0.54 does not replicate). **Rhythm match** NOT-PERSONAL.
> - **Phase 2 defect.** Rhythm purity leaked a bin and reached 4.7; fixed, no Phase 2 verdict moved.

| Feature | Lands in |
|---|---|
| **user C in `service.riders()`** | 1,959 of 15,810 corners are inside the box. A real two-person rider switch; measure it on the presets and rewrite beat 3 only if it moves the road. Also fix the `route_tab.py` help text that says there is no second human — a string, not a pixel change |
| F0.4 bike DNA | cluster user A's 20 bikes on `engineMaxRpm` (7,210-11,745) + lean p95 + range. User C has no manifest → default archetype |
| **F3.2 five modes** | a weight vector over Phase 2 columns applied in `score_cells`; `mode=` threaded through `build_graph / route / loop / compare`. **`mode="flow"` must reproduce today's numbers exactly** |
| F3.3 bike → default mode | `service.py` |
| F3.4 mood | `detect_mood(first 10 min)` → suggested mode. Backend function only |
| F3.5 rhythm match | only if F2.5 landed |

**Expect small route effects, and measure them.** Modes change the score, not the graph, so they
hit the same corridor ceiling as the dial (max 1.137x, doc 14). Rerun the 200-pair scan per mode
and report it. osmnx topology is the only fix and it is **not in this plan**.

## Phase 4 — new answer types  (Layer 4)

Alongside `route_a_to_b` / `route_loop`:
- **F4.3 arc loop** — re-rank the existing loop candidates by distance to a target flow arc
  (warm-up → peak at 65-70% → easy return), and add Phase 2 gems as turnarounds. Cheapest item here.
- **F4.2 Pareto** — sweep z* × mode (**not λ: it saturates**, doc 14); non-dominated (minutes, mean demand / flow), joy shown beside but not optimised — it is WEAK (doc 20).
- F4.6 commute upgrade — first check how many of user A's commutes are inside the box.
- F4.5 urban wander — lowest; crowd timestamps are shifted, so time-of-day flow is not computable.
- F4.8 solar/thermal — T4, say it, don't build it.

## Phase 5 — integration

Rebake; AppTest sweep; regression numbers; rewrite `06_PITCH.md` / `10_LIVE_DEMO.md` **only for
features that passed their test**; CONTEXT + verdicts; merge.

## Out of scope, on purpose

F5.5 visuals and any Streamlit work (UI frozen, native app is the product) · F5.4 leave-one-rider-out
(two riders) · Open-Meteo (dropped) · the file's 1.5-1.8x λ calibration (unachievable, doc 14) · the
"3 trip ids" hazard story as the file words it (doc 13 measured median 5 rides).
