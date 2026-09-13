# 24 — Phase 5: integration, verified live

Written 2026-09-13 on the Mac. **The backend is finished and frozen.**

This phase rebuilt everything from the raw lake, proved the rebuild identical, rebaked, re-ran every
gate, clicked through the app with AppTest, and read every number the pitch and demo use off the running
service.

**By the user's decision, `06_PITCH.md` and `10_LIVE_DEMO.md` were not rewritten in this phase.**
§5 is the measured drift table for whoever rewrites them. The front-end contract is doc 25.

Sources, committed, aggregates only (no trip ids, no ride coordinates):
- `analysis/out/phase5_live_measure.json`: every number below, read off `service.py` and the tables;
- `analysis/out/phase5_apptest.json`: the 23-run AppTest sweep.

## 1. Rebuild from the raw lake

**Every table changed nothing, with one explained exception.** Rebuilt in order on the Mac, and
compared with the Phase 4 files (`DataFrame.equals`, CSVs byte for byte):

| Step | Wall time | Result |
|---|---|---|
| crowd grid, 18 chars | 26.8 s | 7,976 rides parsed (23 skipped), 2,721,275 points, 26,987 cells: **identical** |
| crowd grid, 16 chars | 26.4 s | 5,698 cells: **identical** (halves and transitions too) |
| graph, 16 chars | 9.6 s | 8,929 edges: **differs, see below** |
| graph, 18 chars | 9.2 s | 38,351 edges: **identical** |
| OSM join (cached tiles, no network) | 0.8 s | identical |
| route calibration, 200 pairs | 18.5 s | `route_calibration.csv` **byte-identical** |
| gems, hazards, every other CSV in `analysis/out` | — | byte-identical |
| rebake | 2.5 s | 6.1 MB, 21 pre-solved answers |

**The one difference.**
- **What changed:** the committed `graph_edges_c16.parquet` had `radius_i/j`, `demand_i/j` and
  `surprise` NaN on **every** row. The rebuild fills them: 7,700 / 8,866 / 7,708 / 8,870 / 6,999 of
  8,929 rows. Keys, row order, transitions, seconds, metres and speeds are identical.
- **Why it is harmless:** the router does not read those columns at 16 chars. The surprise readout uses
  the 18-char edges (doc 21), and the baked answers prove it (§2).
- **Doc 21 is stale on this point.** Its line "surprise is NaN throughout the 16-char edge table"
  described a stale file, not the script.

## 2. Gates

Run after the final rebake. **All pass.**

| Gate | Result |
|---|---|
| baked answers vs the Phase 4 bake (cells and summary, compared file to file) | **21/21 identical** |
| Lenggries → Bad Tölz headline | "Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked of you." |
| Kochel → Tegernsee overlap | 0.848 |
| Kochel 2 h Send it loop | 133.4 km / 118.7 min / 0.936 |
| `bike_4e1a9d64` switch at Send it | 0.10 (0.105) |
| `service.init()` | 12 ms; 5,698 cells, 10,318 edges, 4 riders, 17,345 basemap ways, 324 joy rides, 100 gems |
| AppTest default run | 0 exceptions, 5 tabs |

## 3. AppTest sweep — every rider, every preset, every loop start

**23 runs, 0 exceptions, 5 tabs on every run.**
- **Coverage:** all 4 riders × 3 A → B presets; user A and user C × 4 loop starts at 2 h Send it; the
  DIAL tab at both ends; plus the default screen.
- **One red box on every run:** the RIDER DNA tab's designed asymmetry warning, which begins
  "**DO NOT ACT.**" (an `st.error` used as a warning panel). It is not a failure.

**A → B, as the app renders it** (headline · shared road · refusal pins · "dial barely moves" caption):

| Rider | Lenggries → Bad Tölz | Lenggries → Kochel | Kochel → Tegernsee |
|---|---|---|---|
| User A | 1.13x · 83% different · +2.7° · 17% | 1.11x · 75% · +2.3° · 25% | 0.98x · 15% · −0.2° · 85% · pins · caption |
| **User C** | **1.00x · 0% · +0.0° · 100% · pin · caption** | 1.01x · 12% · +0.3° · 88% · pins · caption | 0.98x · 16% · −0.1° · 84% · pins · caption |
| Bike da67fa06 | 1.13x · 83% · +2.7° · 17% | 1.11x · 75% · +2.3° · 25% | 0.99x · 28% · +0.4° · 72% · pins · caption |
| Bike 4e1a9d64 | 1.13x · 84% · +2.7° · 16% | 1.11x · 76% · +2.3° · 24% | 0.96x · 90% · −0.5° · 10% · pins |

**Loops, 2 h, Send it, share of road ridden once:**

| Start | User A | User C |
|---|---|---|
| Kochel | 94% | 89% |
| Holzkirchen | 96% | 93% |
| Schliersee | 96% | 95% |
| Lenggries | 92% | 89% |

**DIAL tab, top-set centroid:** 47.16°N at z* 0.15 and **46.93°N** at 0.90. The in-app caption said
46.88 and now says 46.93.

## 4. The live runs behind the demo beats

Every value was read off `service.py` after the rebake.

| Beat | Measured |
|---|---|
| 1 | Cruise 46.9 km / 42.8 min / 7.02° mean / 17.1° peak · Send it 53.0 km / 40.1 min / 9.71° / 22.4° · overlap 0.167 · 0 refusals |
| 2 | `explain()`: "53 km, about 40 minutes." · "mean 9.7 … peaks at 22.4 … gate is 22.6" · "Best five kilometres score 0.57" · "33% of the tyre's grip … against the 53%" · "Nothing on this route crosses your safety gate." · **three safety lines, new since Phase 2 (below)** |
| 3 | overlap 0.848, gain −0.167, 3 refusals at Cruise and Send it · rider switch vs Bike 4e1a9d64: 0.73 shared at Cruise, 0.86 at Flow, **0.105 at Send it** · user C vs user A at Send it: 1.00 |
| 3, expander | User A: skill 11.40, σ 5.59, gate 22.59, hardest 21.24, **1.063** · User C: 10.65 / 5.44 / 21.53 / 20.08 / **1.072** |
| 4 | Kochel 2 h Send it: 133.4 km, 118.7 min of 120, 94% ridden once, 1 refusal. User C: 136.0 km, 119.3 min, 89% |
| 5 | 200 routable pairs: detour median 1.005, max **1.137**; median demand gain **−0.00°**; λ = 3 … 80 return the identical route |

**Beat 2's safety lines**, verbatim from `explain()`:
- "Hard braking around km 47: 4 of the 41 trips that ride this stretch set off the ABS hard-braking code
  here - across the crowd data, stretches where this happens tend to see it again in other trips."
- "Tightening bend around km 28: the corner radius drops from 670 m to 122 m in one step. Shown for
  safety; it is not part of the fun score."
- "Tightening bend around km 31: the corner radius drops from 319 m to 112 m in one step. …"

### The doc 22 candidate — user C on Lenggries → Bad Tölz: REPRODUCED

**What reproduced:**
- At Send it, users A and C share **16.7%** of the road.
- User C's gate is 21.53°. User A's Send it line peaks at 22.38°, and **2 of its cells are gated for C**
  (0 for A).
- So for C the dial returns the Cruise road at both settings: 46.9 km, 7.0°, one refusal.
- The pin reads: "REFUSED — the crowd leans 22.4° here, past your gate of 21.5° (10.7° + 2σ)".

**Two app strings made it read wrong, and both were fixed. Strings only; no model, cost or route change:**
1. **The refusal reason rounded to whole degrees.** It printed "leans 22° here, past your gate of 22°",
   which reads as false. It now prints one decimal. Beat 3's pins read "24.1° / 26.9° / 26.2° … past your
   gate of 22.6° (11.4° + 2σ)".
2. **The "dial barely moves the road" caption named only one cause.** It said "The crowd graph has one
   corridor here; where a second exists (try the first preset) the same dial puts you on 83% different
   tarmac". For user C *on* the first preset that is wrong: the cause is the gate. It now reads: "Either
   the crowd graph has only one corridor here, or the more demanding road sits past this rider's safety
   gate - any road refused is pinned in red below." Its first sentence, which beat 3 quotes, is unchanged.

**Whether to stage it** is the demo owner's decision, not made here. With the caption fixed it no
longer contradicts a speaker.

**Other string corrections:** the ROUTE tab footer "5 MB local bake" → "6 MB", and the DIAL caption
and `app/README.md` 46.88 → 46.93.

## 5. Drift table for `06_PITCH.md` and `10_LIVE_DEMO.md`

These docs were **not** edited, by decision. Every row below was re-measured in this phase.

### Changed, or wrong as written

| Claim as written | Where | Measured now | Source |
|---|---|---|---|
| "5.2 MB" file | 06 slide 9; 10 §1, §6 | **6.1 MB** | measure `bake_mb` |
| "a full A→B route is 60 ms" | 06 slide 9; 10 §2, §6 | **22 ms** with the graph built; **40 ms** including the graph build for a new dial or rider | `t_route_cached_graph_ms`, `t_dial_change_fresh_graph_ms` |
| "moving the dial is 20–37 ms" | 06 slide 9; CONTEXT | **40 ms** | same |
| "three-hour loop 150 ms" | 06 slide 9; 10 §2, §6 | **167 ms** (2 h: 156) | `t_loop_3h_ms` |
| "rebuilding … takes 13.8 seconds, graph 8.7 s" | 06 slide 9 | **26.8 s** per grid, **9.6 s** graph (the Phase 2 columns added time) | §1 |
| "`demand_p90` vs crowd lean p90 r = 0.892 over 4,558 cells" | 06 slide 6 | **r = 0.924 over 6,734 cells** (≥ 20 rides, today's 18-char grid) | `crowd_bridge_crowd_lean_p90` |
| "across the 15 [bikes] with enough corners, lean p95 spreads 6.3°" | 06 slide 6, Q&A | 15 bikes are in the corner table. 6.29° holds for the **6 bikes with ≥ 100 corners**; 13.4° for the 12 with ≥ 20. The tested statement is doc 22's: bike explains η² 0.30 of peak lean, p < 0.001, but there are no archetypes | `bike_lean_p95_spread_*`, riders_modes_test `bike_dna` |
| "Thirteen events" / "thirteen events in the whole sample" | 06 slide 7; 10 §4 | **15 events in the sample**; 13 of them sit in the two groups the Fisher test compares (z > 1: 3, z < 0.5: 10) | `risk_events_total`, check2 |
| "above λ≈10 it stops changing the answer" | 06 slide 6 | identical from **λ = 3** up to 80 | 12_route_calibration run |
| beat 3 pins "the crowd leans 27° here, past your gate of 23°" | 10 beat 3 | three pins, "24.1° / 26.9° / 26.2° … past your gate of 22.6° (11.4° + 2σ)" | `b3_send_refusals_reasons` |
| beat 3 caption, second sentence | 10 beat 3 | reworded (§4) | `route_tab.py` |
| beat 2 `explain()` block | 10 beat 2 | adds the three safety lines in §4 | `b2_explain` |
| THRILL DIAL centroid "46.88°N at Send it" | 10 §2, §5 | **46.93°N** | AppTest `DIAL z*=0.9` |
| "ABS is orthogonal to cornering demand (ρ = +0.05)" | 10 §4 | this rebuild prints ρ(abs rate, demand_p90) **+0.022** (16-char) / **+0.035** (18-char) | `11_build_graph.py` output |

### Not re-measured in Phase 5

Quote these only with their original doc, or re-derive first:
- EIV slope 1.08. OLS is 0.53 on the 5,747 table; EIV needs an error model that is not in a script.
- Cold grip ρ −0.016.
- "46–51% of elevation is zero".
- Crowd-scale braking 13.3° vs 12.5°, p = 4.9e-3.
- "77,700 rides", "roughly ten thousand events", and the "330 / 1,300 / 6,700 rides" projections. The
  ±28 / 14 / 6% intervals are 1.96/√n arithmetic; the ride counts assume a fixed event rate.

### Standing-rule conflict

06 slide 7 and 10 §5 state the left/right asymmetry, as a rejected result. The standing never-quote list
names the asymmetry, so the owner should decide whether the failures slide may carry it.

### Verified unchanged

- **Beat 1:** 1.13x / 83% / +2.7°; 47 vs 53 km; 7.0° vs 9.7°; 17% shared; 40 vs 43 min.
- **Beat 2:** 9.7 / 22.4 / 22.6; 0.57; 33% vs 53%.
- **Beat 3:** 85% shared, −0.2°; 73% → 10%; 1.063.
- **Beat 4:** 133 km / 119 min / 94%.
- **Gate table:** 27.29 / 26.62 / 1.025, 23.01 / 23.18 / 0.992, 22.59 / 1.063.
- **Physics bridge:** r 0.765 over 5,253 corners, 0.730 over 5,747.
- **Crowd lake:** 26,987 cells, 7,976 rides, 2,721,275 points.
- **OSM:** 63% matched within 80 m, median snap 5.8 m.
- **Speed limits:** 52% of cells ridden above the limit (1,173 of 2,237), median 1.11×; 1,171 cells
  re-priced, 9.67 → 5.60°.
- **Riders:** 101 rides and 20 bikes in the manifest.
- **Risk:** the six bands, 3.6× (3.63), p 0.071, CI [0, 17.1], odds ×1.28 per σ.
- **Network:** detour max 1.137, median gain −0.00°.
- **App:** 17,345 basemap ways, 1,090 ROAD GRID cells.

### Passed in Phases 1–4, available to a rewrite

The allowed wording is in docs 20–23:
- user C is a real second rider, and gate agreement replicates (1.072);
- the safety readout lines;
- morton decoded exactly (100% of 66,632 samples);
- road columns tested split-half: elevation 0.993, rhythm 0.926, reversals 0.915, popularity 0.880,
  prominence 0.743, stop rate 0.511;
- scenic and mountain modes: right direction on 80% / 81% of changed pairs, median +1.2 / +2.3 m;
- the Pareto frontier: short, +3.5 min for +0.21°.

**Measured and failed, for a failures slide:**
- Joy Meter WEAK (AUC 0.675 A / 0.637 C);
- grip-budget mechanism not supported (0.55 / 0.53);
- bike archetypes none (silhouette 0.32);
- mood fails (ρ 0.02 / −0.22);
- arc loop 2/12;
- commute blocked (0/45, 1/106);
- urban wander 0/6;
- adventure mode fails;
- traffic unreliable (0.357).

## 6. Front end

`docs/25_FRONTEND_API.md` is the contract. It covers:
- every `service.py` call, with its return shape and measured examples;
- which answers are offered and which return a verdict note;
- the `explain()` sentence order, with fun lines kept apart from safety lines;
- measured latencies;
- the rules any wrapper must keep: tailnet only, no data out, NaN to null, never score speed.

## Reproduce

```bash
cd ~/ehl_urich/flowstate
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake FS_OUT=$PWD/analysis/out PYTHONIOENCODING=utf-8
FS_CELL_CHARS=18 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _s2
FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
FS_CELL_CHARS=16 $V analysis/11_build_graph.py --set trips-samples-2 --tag _c16
FS_CELL_CHARS=18 $V analysis/11_build_graph.py --set trips-samples-2 --tag _s2
$V analysis/13_osm_layer.py
$V analysis/12_route_calibration.py
$V analysis/14_bake_demo.py
```
