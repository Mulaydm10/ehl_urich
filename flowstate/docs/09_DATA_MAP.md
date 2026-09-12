# 09 — THE DATA MAP

**Every asset we hold, the one table that fuses them, every cross-dataset join, and every feature
test with its verdict.**

Authority: `docs/08_DATA_FINDINGS.md` is the ground truth on units, dead channels and traps; this
document does not contradict it and extends it with the corner-level fusion layer.
Numbers below are the output of `analysis/04_master_table.py`, `05_missing_features.py`,
`06_cross_mapping.py` re-run on 2026-09-12. Outputs live in `analysis/out/`.
Run everything with `PYTHONIOENCODING=utf-8` — the console is cp1252 and umlauts in route names crash the print.

---

## 1. Every data asset we hold

| Asset | Volume | Schema shape | Uniquely good for |
|---|---|---|---|
| `recordedTrips/*.csv` | **100 rides / 508,183 points**, 2021-07-23 → 2026-08-07 | 43 columns, one row per trackpoint, **~1 Hz** (median interval 1.04 s) | The only source of **rider response**. Lean, speed, throttle, gear, RPM, ABS, temp, tyre pressure, odometer. Everything in §2 is built from this and nothing else can replace it. |
| `cloudRecordedTracks-<uuid>.csv` | **1 file / 101 rides** | 31 ride-level columns: `bikeId`, `isFavorite`, `leanAngleLeftMax`, `leanAngleRightMax`, `title`, `rideDistance`, `rideTime`, `speedAverageKmh`/`MaxKmh`, `accelerationMax`, `decelerationMax`, `elevationMin/MaxM`, `temperatureMin/MaxC`, `engineMaxRpm`, start/end lat/lon/timestamp | The **join key to identity and to labels**. `bikeId` is the only way to control for the machine (§3 M5); `isFavorite` is the only true preference field BMW ship; `title` is rider-authored text. Note it carries 101 rides against 100 CSVs — the manifest is the superset. |
| `plannedRoutes/*.gpx` | **89 routes** (87 parse with ≥5 points), median **163 km** | GPX 1.1. Mixed encodings: some routes are `rtept` only (8–27 waypoints), some are dense `trkpt` (up to 9,138 points), some both. `wpt` is empty throughout. | **Revealed preference before the fact** — the rider built these deliberately. 48% are round trips. Also the only source of road geometry for roads **never ridden** (§3 M4). |
| `morton_code` column | Present on **every trackpoint** (508,183) | 32-digit **base-4 quadkey** over an *equirectangular* square grid: `xf=(lon+180)/360`, `yf=(lat+90)/360`, digit = `2*latBit + lonBit`. Prefix length = zoom level; cell side = `360/2^L` degrees → **L=14 ≈ 2.4 km, L=18 ≈ 153 m x 102 m at lat 48, L=22 ≈ 10 m** | A **spatial index for free**. Truncate the string, `GROUP BY`, and you have a road grid with no OpenStreetMap, no map matching and no routing graph. It is also the only aggregation key that will survive scaling to 26.7 M crowd points. **Read it as text** — int conversion overflows 32 digits. |
| `tripViewer/` | 1 Leaflet app, `app.js` 2,103 lines | Client-side CSV loader; three view modes: single ride, heatmap-all-rides, **"Morton cells (avg)"**; ABS/ASC point badges from `ridingabsbraking` / `ridingasccontrol` | **The baseline to beat, and a tell.** BMW's own toy already aggregates by morton cell and already badges ABS events — so §3 M3 and feature F75 are on their own shortlist, not exotic. Their README calls it "quick & dirty" and explicitly not a starting point. Beating it means *personalised*, not *prettier*. |
| README images | 6 PNGs on disk (`trips-samples-1` x2, `trips-samples-2` x4) + 2 tripViewer screenshots; the README markup references 7 map images including `exampleUserA/B/C_trips.png`, which did not ship | Coverage maps of the crowd lake and of the three example users | Slide material, and the **shape of the data we are missing** — they show the lake's DE/AT/CH footprint and the Munich/Alpine box the `trips-samples-2` subset covers. |

### 1b. What is MISSING, and what it blocks

`exd_download (1).zip` (**384 MB**) is a **truncated download** — no end-of-central-directory record, no
central directory, so nothing inside it can be extracted. It contains `datasetHackathon.zip`, which holds:

| Missing asset | Volume | What it unblocks |
|---|---|---|
| `trips-samples-1` | **77,700 rides / 26.7 M trackpoints** (DE/AT/CH) | The entire crowd layer: F10 pace index, F29 crowd speed, F30 crowd lean, F31 flow index, F32 detour ratio, F33 gem detection — i.e. **the whole "Usage of BMW Crowd Data" judging criterion**. Also turns the §3 M3 morton grid from 1,090 cells into a real Road DNA layer. |
| `trips-samples-2` | **7,999 rides / 2.4 M trackpoints** (Munich / Alpine foothills, lat 47.452–47.946, lon 10.845–11.852) | The demo-region density. This is BMW's own choice of interesting area and user A's routes run straight through it. |
| `exampleUserB` | 73 rides | Cross-rider validation. Specifically: re-testing L/R asymmetry (§4 F01) and whether **any** ride anywhere has `isFavorite = true`. |
| `exampleUserC` | 224 rides | Same, plus leave-one-rider-out becomes possible at n=3 instead of n=1. |

Total missing: **85,699 rides / 29.1 M points** — 57x the trackpoints we have.

One constraint to design around *now*: the anonymized lake's `timestampinmillis` is **shifted by a random
per-trip offset**, so crowd trips **cannot be joined to historical weather**. Example-user timestamps are
real, so the weather join works there only. Any crowd feature must be weather-agnostic.

**Also structurally absent from all of it** (needs an external source, not a re-download): OSM road
classes, speed limits, surface type, DEM sight lines, land cover, traffic, POIs. F22/F25 (sight distance,
scenic index) are `EXTERNAL` for that reason.

---

## 2. The master table — the one big thing

`analysis/04_master_table.py` produces **`out/master_corners.parquet`: one row per corner ever ridden.**
Not per trackpoint, not per ride. The corner is the unit at which road demand and rider response are the
same physical quantity, so it is the unit at which every FLOWSTATE claim is testable.

**How a row is built.** Split each ride on gaps, guard the side stand (`ridingvehiclespeed > 0.5`),
compute yaw rate from `d(positionmapmatchedheading)/dt`, segment into signed-curvature blocks
(`|yaw| > 0.04 rad/s`), keep blocks of **≥3 samples**, then aggregate.

| Dimension | Value |
|---|---|
| Corners | **5,747** |
| After filtering manoeuvres (`radius > 12 m`, `v > 8 m/s`, `req_deg` in 3–55) | **5,253** |
| Rides represented | **67** (of 100 — the rest are too short, too urban, or lack usable heading) |
| Distinct bikes | **15** (of 20 in the manifest) |
| Columns | **35** |
| Span | elevation **66–2,617 m**, ambient **0–37 C**, **2021-07-23 → 2026-08-07** |

**The median corner this rider has ridden: 61 m radius, 54 km/h, 20.7 deg required, 16.7 deg used,
21% throttle, gear 3.**

Every column is one of four kinds, and that is the point:

| Block | Columns |
|---|---|
| **Road DNA** | `radius_m`, `req_deg`, `dir`/`dir_name`, `grade`, `elev_m`, `lat`, `lon`, `morton` |
| **Rider response** | `lean_deg`, `lean_p50`, `use_ratio`, `v_ms`, `v_entry`, `v_exit`, `throttle`, `throttle_exit`, `rpm`, `gear`, `a_min`, `a_max`, `abs_max`, `asc_max` |
| **Context** | `temp_c`, `tyre_f`, `km_into`, `min_into`, `hour`, `month`, `gps_acc` |
| **Identity** | `trip`, `blk`, `bike`, `isFavorite`, `n_s` |

**`use_ratio = lean_deg / req_deg` is the single derived quantity the whole product runs on.** It is
dimensionless, it is comparable across roads, riders and bikes, and it is what §4's F45, F09, F11 and F14
all test. Median 0.79–0.81 — consistent with `08_DATA_FINDINGS.md` §1's `k ≈ 0.8` hang-off constant,
derived independently here.

**Every other analysis in this project is a view over this table.** The morton road grid is a `GROUP BY`
on `morton[:18]`. The bike effect is a `GROUP BY bike`. The warm-up ramp is a `GROUP BY` on `km_into`.
The flow score is one column arithmetic on `req_deg`. If you change the corner definition, you change
every number in §3 and §4 at once — which is a feature, not a risk, as long as nobody forks it.

Sanity check that it is real: running the flow kernel on it with `skill = lean p95 = 30.2 deg`,
`sigma = 7.5 deg` gives **three different sets of "best" corners** for `z* = 0.15 / 0.50 / 0.90`
(508 / 414 / 304 corners scoring >0.8 of 5,253). The Thrill Dial moves the answer on real telemetry.

---

## 3. The mapping matrix

Seven joins. Each is a few lines of pandas; together they are the difference between six folders and one product.

| ID | Join | Produces | Measured result | Status |
|---|---|---|---|---|
| **M1** | planned GPX x recorded CSV, matched on ~1.1 km lat/lon cells | **Conversion label** — did he ride what he planned? | 87 routes x 100 rides. **40% fully ridden (90%+ coverage, 35 routes)**, **25% ridden 60–90% (22)**, 8% mostly 40–60% (7), 20% partly 10–40% (17), **7% never ridden (6)** | **Use as the primary label** |
| **M2** | recorded x recorded, same cells | Repeat roads | **3,945 distinct cells**; **1,869 ridden on 2+ rides**, 163 on 5+; **53% one-offs**. Repeated corners are **LESS** demanding (19.7 vs 20.4 deg) and **LOWER** (590 m vs 856 m) | **Demote — sign is wrong** |
| **M3** | trackpoints → `morton_code` prefix → corner aggregation | **Road DNA with no OpenStreetMap** | L=14: 854 cells, 6.7 corners/cell, 207 on >1 ride. **L=18: 4,050 cells, 1.4 corners/cell, 616 on >1 ride**; **1,090 cells carry ≥2 corners**. Cell demand p90: p25 20.0 / p50 26.1 / p75 35.1 / p95 47.7 deg | **Ship it** |
| **M4** | planned GPX → differential geometry → Road DNA | Difficulty of roads **nobody has ridden** | **27 of 89 routes** have enough shape points. Ranks sensibly at the ends (Naturns 59.1 / T2_COMPLEX 57.8 deg req_p90 vs Erlangen_test 2.7) but **one route returns req_p90 = 73.1 deg — noise** | **Ship with a spacing filter** |
| **M5** | master table x `bikeId` | **The machine effect** | **6.3 deg of spread in lean p95 across bikes for the SAME rider** (26.3 → 32.6 over 6 bikes with ≥100 corners) | **Mandatory control** |
| **M6** | speed trace → style index | Momentum vs point-and-shoot, replacing dead brake pressure | 5,417 corners, 28 rides with ≥20. ps index **p10 0.044 / p50 0.075 / p90 0.103** (2.3x spread). But `brake_frac` is ~0 on almost every ride and `corr(ps, exit throttle) = -0.22` | **Partial — exit half only** |
| **M7** | master x `z*` flow kernel | Flow score | 508 / 414 / 304 corners >0.8 at z* = 0.15 / 0.50 / 0.90 | **Works end to end** |

### M1 — why conversion is the strongest label in the dataset

A planned route he went on to ride beats every other preference signal available, because **he committed
to it before he knew the weather, before he knew the traffic, and before he knew how he would feel.**
A repeat is a decision made with the road already known and the commute already necessary. A favourite is
a decision made afterwards, and it is empty anyway (`isFavorite = False` on all 101 rides). Conversion is
an *ex ante* choice with an *ex post* outcome attached — which is the exact structure a preference model
wants, and it has **65% positives (60%+ coverage) and 7% hard negatives** without any hand labelling.

The 6 never-ridden routes are not a failure of the label; they are **the Skill Quest target list**, and it
writes itself: `T2_TM_2022` (538 km), `T2_PLAIN_TM22` (224 km), `T2_COMPLEX_TM22_STAGE_1` (156 km),
`Baindlk_Moorenw_Biburg_schön` (95 km).

**Two caveats to fix before this label goes into a model:**
1. Coverage is measured against *all* recorded rides, with **no time ordering** — a plan can be scored
   "ridden" by a ride that predates it. Both timestamps are in the filenames; require ride date > plan date.
2. Cells near home inflate coverage for every route that starts in Munich. Drop the rider's top-N home
   cells before computing coverage, or the label degenerates into "does it start at his house".

### M2 — CRITICAL FINDING: repeat means commute, not favourite

This is the most important negative result in the project.

| | n | required lean p50 | median elevation | median radius |
|---|---|---|---|---|
| Corners on **repeated** roads (cells with ≥4 rides) | 650 | **19.7 deg** | **590 m** | 73 m |
| Corners on **one-off** roads | 4,603 | **20.4 deg** | **856 m** | 66 m |

**Repeated roads are less demanding and 266 m lower than roads he rides once.** The sign is the opposite
of the assumption. The mechanism is obvious once measured and is already documented in
`08_DATA_FINDINGS.md` §4: **51 of 101 rides are under 20 km and half of what he records is commuting.**
Roads he repeats are the roads between his house and work. Roads he rides once are the alpine passes he
drove 200 km to get to.

**`docs/07_VALIDATION.md` lists "Repeat — segment ridden more than once by the same rider" as the #2
revealed-preference label, behind Detour only. On this data that ranking is wrong and must be changed.**
Its own stated weakness — "confounded by proximity to home" — is not a caveat here, it is the entire
signal. Using repeat as a positive label will train the model to recommend the B471 to Garching.

Recommended label ordering after this finding:

1. **Conversion** (M1) — planned then ridden. New #1.
2. **Detour** — unchanged, still strong in principle, still needs a counterfactual router we do not have yet.
3. **Dwell/stop** — sparse but high precision.
4. **Sustained flow** — traversal with no stop and low speed variance.
5. **Repeat** — **demoted to a negative/commute indicator, or dropped.** If kept at all, keep it only as a
   *control* variable, and only after excluding cells within ~15 km of the modal start location.

### M3 — Road DNA without OpenStreetMap

The `morton_code` prefix is a free spatial index and BMW's own viewer already aggregates on it, so this is
a join they will recognise instantly.

| Prefix | Cell side | Cells | Corners/cell | Cells on >1 ride |
|---|---|---|---|---|
| 14 | ~2.4 km | 854 | 6.7 | 207 |
| **18** | **~153 x 102 m** | **4,050** | **1.4** | **616** |
| 22 | ~10 m | 5,426 | 1.1 | 242 |

**L=18 is the operating point**: 1,090 cells hold ≥2 corners, and 616 cells have been seen on more than
one ride, which is what makes a per-cell statistic meaningful rather than a single observation. L=14 has
more corners per cell but averages away the corner itself; L=22 is finer than the GPS is accurate.

With 100 rides this is a demo. With `trips-samples-1`'s 77,700 rides it is **the** Road DNA layer, and the
per-cell demand distribution (p50 26.1 deg, p95 47.7 deg) already looks like a usable difficulty scale.

### M4 — Road DNA for roads nobody has ridden, and its noise floor

Curvature from raw GPX geometry: `kappa = |d(psi)| / ds`, `R = 1/kappa`, then
`req = arctan(v^2 / (R*g))` at a **22 m/s (80 km/h) reference pace**. 27 routes clear the
≥20-usable-segment bar. The ranking is credible at both ends — `Naturns_Day2` req_p90 59.1 deg at
radius_p50 154 m, `T2_COMPLEX_TM22_STAGE_1` 57.8 deg at 20.7 curves/km, against `Erlangen_test` at
2.7 deg and radius_p50 3,459 m.

**The caveat is load-bearing, so state it before a judge finds it.** `[route-near-Kochel]`
returns **req_p90 = 73.1 deg with a median radius of 825 m** — those two numbers cannot both be true.
It is a sparse route where consecutive shaping points are far apart and a single heading jump between
two widely spaced points produces an enormous apparent curvature. **Fix: require minimum point spacing
(the code already filters `5 m < ds < 500 m`; tighten to `ds > 20 m` and require ≥3 consecutive
qualifying segments), and clip `req` at the physical limit (~55 deg) rather than reporting it raw.**
Until that filter lands, M4 output is ordinal, not metric — use it to rank routes, never to quote a
degree value.

### M5 — the machine effect, and why it outranks everything

| bike | corners | rides | lean p95 | use ratio | median rpm |
|---|---|---|---|---|---|
| 4e1a9d64 | 1,312 | 4 | **32.63** | 0.82 | 2,475 |
| d4bc466c | 841 | 5 | 31.64 | 0.82 | 3,139 |
| 2105b648 | 453 | 13 | 29.20 | 0.83 | 2,852 |
| da67fa06 | 1,648 | 13 | 28.02 | 0.73 | 2,932 |
| bf8c029e | 125 | 4 | 27.47 | 0.82 | 2,963 |
| 3dc7f3aa | 475 | 4 | **26.34** | 0.82 | 3,092 |

**6.3 deg of spread in lean p95, same rider, different motorcycles.** For scale: the entire left/right
asymmetry effect that was going to be demo moment B is **~1 deg and not significant**
(`08_DATA_FINDINGS.md` §2.1). The bike effect is **six times larger than the headline rider effect**, so
any skill estimate that does not condition on `bikeId` is measuring the fleet.

This is also the best natural experiment in the dataset and nobody else will touch it: one rider,
15 bikes, 5,253 corners. It lets us **separate the machine term from the rider term** instead of asserting
that we would. Note `use_ratio` is far more stable across bikes (0.73–0.83) than raw lean p95 — which is
the empirical argument for making `use_ratio`, not lean angle, the reported skill axis.

### M6 — style index, honest version

Brake pressure is 100% dead (`08_DATA_FINDINGS.md` §2.2), so style must come from the speed trace:
`brake_frac = (v_in - v_min)/v_in`, `drive_frac = (v_out - v_min)/v_min`, `ps_index = brake + drive`.

It separates rides: p10 **0.044** → p90 **0.103**, a 2.3x spread over 28 rides with ≥20 corners.
**But be precise about what is doing the separating.** `brake_frac` is ~0.000 on nearly every ride —
at ~1 Hz with 3–6 samples per corner, the in-corner minimum speed usually *is* the entry speed, so the
braking half of the index never fires. All discrimination comes from `drive_frac` (the exit half).
And `corr(ps_index, exit throttle) = -0.22` across rides, i.e. **negative** — rides that gain the most
speed on exit are not the rides holding the most throttle at the exit sample, which is what you would
expect if exit throttle at 1 Hz is sampled at a semi-random point in the drive.

So: **M6 is currently a "corner exit drive" index, not a full point-and-shoot classifier.** Rename it,
report it as one axis, and do not claim brake-phase detection. Note also that the earlier version inside
`05_missing_features.py` (using `v_entry - v_mean`) is **degenerate — p10/p50/p90 all round to 0.000**;
the `06_cross_mapping.py` version using per-point `v_min` is the one to keep. Delete the other.

---

## 4. Feature test results, complete

Verdicts from `out/feature_verdicts.csv` plus the re-run of `05_missing_features.py`. Failures are listed
with the same prominence as successes, because a clean list of what did not work is worth more than an
inflated one — and because every one of these is a question a judge can ask.

| ID | Feature | Verdict | Measured evidence |
|---|---|---|---|
| **F18** | Required lean `arctan(v*omega/g)` | **PROVEN** | corr **0.576** over 244,147 points; **0.730** over 5,747 corners; errors-in-variables slope **0.92** |
| **F45** | **Warm-up ramp** | **CONFIRMED** | use-ratio **0.768 +/- 0.034** in the first 5 km vs **0.813 +/- 0.007** after 15 km — **non-overlapping intervals.** Monotone across all four bands: 0.747 / 0.765 / 0.784 / 0.798 (0-5 / 5-15 / 15-40 / 40+ km). The rider genuinely holds back early. |
| **F19** | **Corner rhythm** | **WORKS** | lag-1 autocorrelation of log radius **0.407** pooled; per-ride **p10 0.16 / p50 0.37 / p90 0.48** across 29 rides. Rides genuinely separate into rhythmic and irregular. Caveat from `08_DATA_FINDINGS.md` §3 stands: resample by **distance**, not time. |
| **F77/F78** | **Mood detector** (gear x RPM at speed) | **STRONG** | rpm-per-kmh per ride p10 49.4 / p50 53.0 / p90 62.0; **corr(rpm-per-kmh, median lean used) = 0.54** across rides. Holding a lower gear goes with leaning harder — same rider, different day, observable Thrill Dial setting. |
| **F14** | Machine DNA (`bikeId`) | **WORKS + RISK** | 20 bikes / 101 rides in the manifest, 15 in the corner table. **6.3 deg spread in lean p95** (26.3–32.6). Computable, and a confounder that must be controlled. |
| **F75** | ABS limit events (`ridingabsbraking == 3`) | **WORKS** | 60 points, mean **-2.22 m/s²**, 93% decelerating, p05 -4.7 m/s² ≈ 0.48 g; **33 of 100 rides** contain one. Replaces the dead brake channel. |
| **F79** | Odometer = experience | **WORKS** | `ridingtotalmileage` 0 → **49,917 km**, flat on only 2% of rides. One column, and the cold-start prior we said we lacked. |
| **F54** | On-bike ambient temperature | **WORKS-BETTER** | real on 95% of rides, p05 11.5 / p50 22.2 / p95 32.5 C. Ground truth at the exact time and place, beats a weather API. |
| **F01** | L/R lean asymmetry | **WORKS (but ~noise)** | per-ride p95: mean **-1.40 deg**, 95% CI [-2.11, -0.69]; per-corner p95: **+0.8 deg** the other way; BMW's own field: **-0.40 +/- 0.70**. **The sign flips with the estimator.** Do not pitch until B/C. |
| **F02** | Headroom (p95 - p50 lean) | **WORKS** | p50 2.4 deg, p95 18.0 deg → headroom 15.6 deg |
| **F04** | Lean consistency sigma | **WORKS** | per-ride sd of abs(lean) spans 0.0–19.9 deg |
| **F07** | Gradient tolerance | **WORKS** | grade from `positionrawelevation`: p05 -8.7%, p95 +8.7%; 35% of points on >3% grade |
| **F17** | Curvature / corner radius | **WORKS** | radius from `v / yaw_rate`; usable on 100% of moving points |
| **F20** | Handedness per segment | **WORKS** | sign of yaw rate gives direction directly; 50% of cornering points are right-hand |
| **F21** | Elevation / gradient | **WORKS** | `positionrawelevation` flat on 1% of rides — **use it**; `positionmapmatchedelevation` flat on 36% |
| **F16** | Rider level radar | **WORKS** | all axes computable except wet (no rain join yet) and surface |
| **F71b** | Ground truth via `plannedRoutes` | **WORKS** | 89 deliberate GPX routes; upgraded to the conversion label in §3 M1 |
| **F71c** | Ground truth via repeats | **WORKS, WRONG SIGN** | 54 distinct start locations, max 13 repeats — **but §3 M2 shows repeated roads are easier and lower. Demote.** |
| **F06** | Smoothness (jerk RMS) | **WORKS-WEAK** | computable, but coarse at 1 Hz; per-ride jerk RMS 0.00–1.26 m/s³ |
| **F52** | Rain at arrival time | **PARTIAL** | example-user timestamps are real (2021-07-23 → 2026-08-07) so a historical weather join works **here only**; the anonymized lake's timestamps are shifted and cannot be joined |
| **F05b / M6** | Style via speed trace | **PARTIAL** | ps index p10 0.044 / p50 0.075 / p90 0.103, but `brake_frac ≈ 0` everywhere and corr with exit throttle **-0.22**. Exit-drive axis only — see §3 M6. The variant in `05_missing_features.py` is **degenerate (all ~0.000)**. |
| **F11** | **Fatigue curve** | **NOT CONFIRMED** | use-ratio by elapsed hours: **<1 h 0.774, 1-2 h 0.806, 2-3 h 0.811, 3 h+ 0.792**. Non-monotone, no clean degradation; hard-braking rate is actually *lowest* in the 3 h+ band (0.145% vs 0.631% at 2-3 h). **The dip is at the START, not the end — that is F45 warm-up, and F11 and F45 are confounded by construction** because km-into-ride and minutes-into-ride are the same axis. Any fatigue claim must control for warm-up (and for the fact that long rides are motorway rides). Do not pitch fatigue. |
| **F09** | **Temperature tolerance** | **NOT SIGNIFICANT** | cold (<12 C) **0.800 +/- 0.030** vs warm (>22 C) **0.820 +/- 0.009** — intervals overlap. The band table is flat: 0.800 / 0.772 / 0.787 / 0.791 / 0.801 across <10 / 10-15 / 15-20 / 20-25 / 25+ C. The channel is excellent (F54); the *behavioural response* to it is not measurable here. Keep cold as a **safety policy**, not as a measured rider trait. |
| **F80** | **Tyre warm-up** | **FAILED — sign reversed** | front pressure **2.360 bar in the first 5 min → 2.240 bar after 20 min (-0.120 bar)**, monotone down across all bands (2.360 / 2.320 / 2.320 / 2.240 / 2.240). The hypothesis was that pressure climbs as the tyre heats; **it falls.** Most likely the TPMS reports a temperature-compensated value, or the sensor settles after wake-up. Either way the feature as specified is dead. **F45 survives on its own evidence and does not need F80.** |
| **F83** | **GPS accuracy as canopy proxy** | **FAILED as specified — REFRAME** | corr(accuracy, elevation) **+0.022**, corr(accuracy, 1/radius) **+0.004** — no canopy or enclosure signal. corr(accuracy, abs(grade)) **+0.154** is the only non-zero, and it is weak. **But the direction is informative: median accuracy is 4.0 m in the mountains (>1200 m) and 6.0 m in the lowlands (<700 m).** Accuracy is *worse* where the buildings are, not where the trees are. **Reframe F83 as an URBAN-CANYON detector** — which is more useful anyway, because it maps directly onto BMW's own "inner city" red flag: high `positionmapmatchedhorizontalaccuracy` = built-up = de-prioritise the segment. Free, needs no land-cover source. |
| **F76** | Traction control (`ridingasccontrol`) | **WEAK** | code 2 (756 points) shows *lower* lean and *lower* throttle than baseline — not a clean slip event. Do not oversell. |
| **F05a** | Style via brake pressure | **DEAD** | `sensorsbreakpressurefront/rear` exactly 0 on **all 100 rides** |
| **F34** | Road Pulse via vertical accel | **DEAD** | `sensorsaccelerationvertical` flat on 91% of rides, non-zero on 2.8% of points; `sensorsaccelerationlateral` identical |
| **F71a** | Ground truth via `isFavorite` | **PRESENT BUT EMPTY** | the field exists in BMW's schema, `False` on all 101 of user A's rides. Check B and C the moment they land. |
| **F10, F29, F30, F31, F32, F33** | Pace index, crowd speed, crowd lean, flow index, detour ratio, gem detection | **BLOCKED** | all six need `trips-samples-1/2` from the truncated 384 MB archive — **the entire "Usage of BMW Crowd Data" criterion** |
| **F22 / F25** | Sight distance, scenic index | **EXTERNAL** | not in this data at any resolution; needs OSM + DEM + land cover |

**Score: 17 work, 3 partial, 3 failed outright (F80, F83-as-specified, F11), 1 not significant (F09),
3 dead channels, 6 blocked, 2 external.** Three of the four nine-feature "free wins" from
`08_DATA_FINDINGS.md` §6 survived contact with the data (F75, F79, F77/F78); **F80 did not, and F83 only
survives reframed.** Say all of that out loud — the failures are the evidence that the successes were tested.

---

## 5. What this changes

Priorities, in order, given §3 and §4.

1. **Rewrite the label set in `docs/07_VALIDATION.md` before any model is trained.** Promote
   **Conversion (M1)** to #1 — 65% positives, 7% hard negatives, free, and an *ex ante* commitment.
   **Demote Repeat from #2 to a commute control or drop it** — repeated roads measure 19.7 deg vs 20.4 deg
   and 590 m vs 856 m, so training on it teaches the model to recommend the commute. This is a one-line
   edit that changes what the whole system optimises; do it first.
2. **Put `bikeId` in every model that touches lean.** 6.3 deg of machine spread versus a ~1 deg asymmetry
   effect means an uncontrolled skill estimate is mostly a bike estimate. Report **`use_ratio`** (stable
   0.73–0.83 across bikes) as the headline skill axis instead of raw lean p95 (26.3–32.6).
3. **Fix M1's two label bugs before it is used**: enforce ride-date > plan-date, and exclude home-adjacent
   cells. Both are cheap; without them the "strongest label in the dataset" is partly an artefact of
   starting every ride in Munich.
4. **Add the M4 spacing filter** (`ds > 20 m`, ≥3 consecutive qualifying segments, clip `req` at 55 deg).
   Until then quote M4 as a **ranking** only, never a degree value — one route currently reports
   73.1 deg req_p90 at an 825 m median radius, and that number is in a CSV a judge can open.
5. **Build the demo on M3 at morton prefix 18.** 1,090 cells with ≥2 corners, 616 seen on >1 ride, no OSM,
   no map matching, and BMW's own tripViewer already aggregates the same way. It is also the only part of
   the pipeline that is already shaped for 26.7 M crowd points.
6. **Cut F11 (fatigue), F09 (temperature tolerance) and F80 (tyre warm-up) from the pitch.** Keep **F45
   warm-up** — it is the one confirmed time-varying rider effect (0.768 +/- 0.034 → 0.813 +/- 0.007) and
   it stands on its own without tyre data. Say explicitly that F11 and F45 are confounded and that the
   evidence supports the warm-up reading, not the fatigue one.
7. **Promote F77/F78 (mood) into the P0 spine.** corr 0.54 between rpm-per-kmh and lean used is the
   second-strongest measured relationship in the project after the physics bridge itself, and it is the
   only channel that observes the Thrill Dial setting *the rider chose today* rather than inferring it.
8. **Reframe F83 as an urban-canyon / "inner city" detector** (accuracy 6.0 m lowland vs 4.0 m mountain)
   and delete the canopy claim. Rename M6 to a corner-exit drive index and delete the degenerate copy in
   `05_missing_features.py`.
9. **Re-download `exd_download (1).zip`.** Still the highest-leverage single action: it unblocks six
   features, one whole judging criterion, cross-rider validation of F01, and the only chance of a real
   `isFavorite` label. Everything above is built to accept it without a rewrite — M3's morton grid and the
   master table's schema both scale by adding rows, not columns.
