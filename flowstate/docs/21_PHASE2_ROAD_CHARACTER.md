# 21 — Phase 2: road character columns

Written 2026-09-13 on the Mac. Code: `analysis/10_crowd_layer.py` (new columns, 24 s per grid),
`analysis/16_road_character.py` (the tests, 60 s), `router.road_character()`,
`router.surprise_boundaries()`, `service.safety_readout()`, `service.gem_pool()`.
**Everything here ran on the real crowd lake**: 7,976 rides, 2,721,275 points, trips-samples-2.
Every threshold was written into the scripts **before the first run** and not changed after it.

## Verdicts

| Feature | Verdict | Evidence (16-char grid unless stated) |
|---|---|---|
| `dwell_share` | **RELIABLE-BUT-REDUNDANT** | split-half ρ 0.503 [0.459, 0.545]; ρ with `stop_rate` **0.917** |
| F2.6 reversals / km, cell level | **RELIABLE** | split-half ρ 0.915 [0.903, 0.927] with residential masked |
| F2.5 FFT rhythm | **PASS** | split-half ρ 0.926 [0.910, 0.941]; wavelength vs corner radius ρ **0.380** [0.334, 0.422] |
| F2.7 adventure index | **PASS**, but close to a rename | ρ with demand 0.887 > ρ with rarity 0.510 |
| F2.8 crowd-mined viewpoints | **INSUFFICIENT-DATA** | **0 candidates**; the lake ends trips where riders stop |
| F2.9 traffic on good roads | **UNRELIABLE** | split-half ρ 0.357 [0.286, 0.425] |
| F2.3 hazard readout | **REPEATABLE** | exposure-stratified risk ratio **2.89** [2.09, 3.69] across halves |
| F2.10 surprise | **PASS** | braking after a tightening step, radius-stratified ratio **1.87** [1.44, 2.37] |
| F2.4 gems as a pool | **EXPOSED** | 100 gems, all in the graph; **43 routable** for user A at Flow, 57 behind the gate |

**The default route did not move.** No new column enters the flow score.

## The method: split-half, because the lake has no rider ids

A road property should survive a change of riders. The crowd lake has no rider ids, so the rides
are split into two disjoint halves (odd and even ride index). Every column is rebuilt on each half,
and the halves are compared cell by cell (Spearman, 2,000 bootstraps over cells, ≥ 10 traversals
in each half).

- **Pre-registered bar:** ρ ≥ 0.50 means a property of the road. Below it, the column describes
  whoever happened to ride there.
- **Physical or external claims are tested as well:** rhythm against a different channel,
  viewpoints against OpenStreetMap, surprise against braking, hazard against itself.

## Each column

**Rebuild safety first.** Adding the columns left every existing column of `crowd_grid_s2` and
`crowd_grid_c16` identical (`DataFrame.equals`), and `crowd_gems_*.csv` / `crowd_hazards_*.csv` are
byte-identical. The router's inputs did not move. Rebuild time went from 13.8 s to 24 s per grid.

### dwell_share — reliable, adds nothing

Share of in-cell time below 2 m/s (sample gaps over 5 s excluded).

- It replicates just at the bar: ρ 0.503 at 16 chars, 0.401 at 18.
- It rank-correlates **0.917** with `stop_rate` (0.983 at 18 chars).
- `router.score_cells` keeps its `1 − flow_index` stand-in, so today's routes stay put.
- **Phase 3 should not add dwell as a separate mode term:** it would double-count stops.

### Reversals per km — reliable at cell level

Lean sign changes past ±5° at > 5 m/s, per km ridden in the cell.

- **Split-half ρ is 0.915 with residential cells masked, and 0.916 without.**
- **The mask barely matters.** Only 124 cells with ≥ 10 rides are residential. Their median is
  4.16 reversals/km against 2.64 elsewhere, so the junction confound is real but small in area.
- Outside residential cells, reversals rank-correlate 0.55 with demand.

**How this squares with doc 20.** There, ride-level reversals flipped sign between user A and
user C. Here, the same quantity is a stable property of the road across disjoint rides. The likely
reading is that the ride-level flip came from *which roads* each rider's commutes cross, not from
the measurement. That is an interpretation, not a test. Masking stays in `road_character()` as
specified.

### FFT rhythm — passes both halves of its test

**Method:**
- Signed lean is resampled every 10 m by distance.
- Each window is 1.28 km long with a Hann taper, hopping 160 m, and must be moving throughout with
  lean rms ≥ 3°.
- The dominant wavelength is taken between 640 m and 40 m, refined parabolically.
- Purity is the share of power within ±1 bin of the peak.
- 148,283 rhythmic windows; 4,800 cells at 16 chars carry a rhythm.

**Results:**
- **Reliability:** ρ 0.926 at 16 chars, 0.916 at 18.
- **Physics:** wavelength rises with the corner radius measured from the *yaw* channel,
  ρ 0.380 [0.334, 0.422] (0.369 at 18). The bar was ≥ 0.30, positive.
- **Limitation, stated:** wavelength p10 / p50 / p90 is 234 / 471 / **853 m**. The p90 is the
  resolution floor of a 1.28 km window, where the peak sits in the lowest bin. Read it as "no
  alternation within a kilometre", not as a measured 853 m rhythm.

### Adventure index — passes its rule, says little beyond demand

`demand_p90 / log1p(n_rides)`, defined from 3 rides.

- **Pre-registered failure mode:** rarity dominates. It does not: ρ with demand is 0.887, with
  1/log1p(n_rides) 0.510.
- **The honest reading is that it is mostly `demand_p90` again.**
- Its top 5% of cells snap to a mapped OSM road less often than the average cell (51% vs 64%).
  Rarely ridden demanding cells are partly off the mapped road network.

### Crowd-mined viewpoints — no candidates at all

**Rule:**
- ≥ 2 rides stopped ≥ 60 s in the cell;
- each stop ≥ 1 km along the ride from both of its ends;
- stops on ≥ 5% of the rides that pass;
- the cell sits ≥ 50 m above the median of the cells within 3 km.

**Result:**
- **Zero cells meet it.** The test is **INSUFFICIENT-DATA**, not a fail.
- The probe showed why before the run: 12% of rides contain a stop of 2 minutes or more, but
  only 2 of 598 sampled rides have one more than 2 km from both ends. **The lake cuts a trip where
  the rider stops**, so a viewpoint visit becomes a trip end.
- 356 cells hold any mid-ride long stop. The 45 that pass the stop rule all sit below the
  prominence bar.

**Descriptive only.** OpenStreetMap has 1,001 `tourism=viewpoint` features in the box; the query
is cached in `data/osm/viewpoints.json`, and no lake data was sent. Their within-300 m hit rates:

| Cells | Hit rate |
|---|---|
| Stop-rule cells (45) | 6.7% |
| Prominent cells without stops (840) | 7.1% |
| All cells | 2.8% |

**Not done, on purpose:** using trip *ends* instead. The lake has no rider ids, so a cell with many
trip ends cannot be told apart from somebody's home.

### Traffic on good roads — unreliable

A traversal "crawls" if its mean speed is under half the cell's median traversal, its throttle sd
is ≤ 5 %-points, and it has no ABS.

- Split-half ρ is **0.357** at 16 chars and 0.320 at 18, below the bar.
- Congestion in this sample does not recur by place. Crowd timestamps are shifted per trip, so it
  cannot be conditioned on time of day either.
- The flag fires on 6 cells at 16 chars.
- **Not handed to the router's output, and not used by Phase 3.**

### Hazard readout — repeatable, worded as counts

`abs_rides` is the number of rides with an ABS code-3 sample in the cell.

**Test:** does ABS in one half predict ABS in the other?
- Mantel-Haenszel risk ratio, stratified by traversal-count quintile so that busy cells do not win
  on exposure alone.
- Both directions pooled, over 1,618 cells.
- Result: **2.89 [2.09, 3.69]**. 51 cells have ABS in both halves and 259 in one.

**In `explain()`**, safety readout only, never the fun score. A line appears for cells with ≥ 3
such rides, at most two per route:

> Hard braking around km 41: 4 of the 41 trips that ride this stretch set off the ABS hard-braking
> code here - across the crowd data, stretches where this happens tend to see it again in other trips.

**Wording fix, made after the first gate run:** the first draft ended "it happens in both halves of
the crowd data". The test is a population result, not a per-cell one, so that over-claimed. The
threshold and the rule did not change; only the sentence did. It never says "the crowd brakes here".

### Surprise — passes, on direction-correct braking

Doc 13 found surprise weak against cell-level ABS (ρ +0.051). That test could not see direction:
ABS in a cell does not say which way the rider came from. So `10_crowd_layer.py` now records, for
every directed step between 18-char cells, how many rides entered and how many decelerated
≥ 0.25 g inside the destination. It uses the speed channel between two ~1 s samples; rides with
GPS-derived speed are excluded as too noisy.

**Test design:**
- Destination cells that are OSM residential or have `stop_rate ≥ 0.25` are dropped.
- Tightening steps (radius at least halves, ≥ 5 rides) are compared with radius-stable steps
  (within ±25%).
- The comparison is stratified by **destination radius quintile**, so a merely tight corner cannot
  carry the effect.

**Result:**

| Steps | Braking share |
|---|---|
| Tightening (1,041) | 5.9% |
| Radius-stable (5,940) | 1.8% |

Crude ratio 3.25. **Radius-stratified ratio 1.87 [1.44, 2.37]**; the bar was ≥ 1.5 with CI above 1.

**How it is read out:**
- Surprise is NaN throughout the 16-char edge table; a 600 m cell has no single radius.
- `router.surprise_boundaries()` therefore reads the 18-char directed edges and keeps, for each
  step between two routing cells, the sharpest tightening seen across that boundary. That gives
  3,527 boundaries.
- The line reads: "Tightening bend around km 8: the corner radius drops from 250 m to 33 m in one
  step. Shown for safety; it is not part of the fun score."

**Known risk, said aloud:** a 16-char cell can fuse two parallel roads (doc 14). The 18-char edge
chosen for a boundary could belong to the other road.

### Gems — a pool for Phase 4

`service.gem_pool(rider, z_star, n)` returns the ranked `crowd_gems_s2.csv` cells with their
16-char routing cell, flow, gate status and a `routable` flag.

- For user A at Flow: all 100 gems are graph nodes, **43 are routable, and 57 sit behind the
  rider's gate**.
- The crowd's best corners are mostly harder than this rider's habitual road.
- Phase 4's arc loop should draw turnarounds from the routable subset and say why the others are
  missing.

## Gates

| Gate | Result |
|---|---|
| Existing grid columns + gems/hazards CSVs identical after rebuild | PASS |
| Lenggries → Bad Tölz headline "1.13x … 83% … +2.7 deg" | PASS, identical |
| Kochel → Tegernsee overlap 0.848 | PASS |
| Kochel 2 h loop at Send it 133.4 km / 118.7 min / 0.936 | PASS |
| Rider switch on Kochel → Tegernsee at Send it (userA vs bike_4e1a9d64) | still 10% shared |
| Bake | 6.1 MB (was 5.3) in 2.5 s; `init()` 12 ms; fresh dial 19 ms |
| AppTest | 0 exceptions, 5 tabs |

**The explain list got longer.** Every preset now carries 2–4 safety lines. `10_LIVE_DEMO.md`
still quotes the refusal line correctly ("Nothing on this route crosses your safety gate" is
unchanged), but beat 2 should be re-read against the new lines in Phase 5.

## Consequences for Phase 3

- **Modes may weight:** reversals/km (reliable), rhythm wavelength and purity (pass), and adventure
  index (pass, but ≈ demand, so do not count demand twice).
- **Do not weight:** `dwell_share` (redundant with stops), traffic (unreliable), viewpoints (none
  exist).
- **F3.5 rhythm match is unblocked.** F2.5 landed.

## Reproduce

```bash
cd ~/ehl_urich/flowstate
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake FS_OUT=$PWD/analysis/out
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
FS_CELL_CHARS=18 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _s2
FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
$V analysis/16_road_character.py        # -> analysis/out/road_character_test.json
$V analysis/14_bake_demo.py
```

`crowd_halves_*.parquet` and `crowd_transitions_*.parquet` are gitignored with the rest of
`analysis/out/*.parquet`. `road_character_test.json` is committed: aggregates only, with no
coordinates and no trip ids.
