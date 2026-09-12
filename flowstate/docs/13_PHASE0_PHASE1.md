# 13 — Phase 0 fact-check + Phase 1 edge table

Written 2026-09-12 ~22:00 CEST on the Mac (the compute box). Everything below was
re-derived from the data on this machine, not carried over from the plan document.

## Where we are against FLOWSTATE_Execution_Plan.docx

| Phase | Deliverable | Status |
|---|---|---|
| 0 — own the argument | the three answers, cold | numbers VERIFIED here; rehearsal is human-side |
| 1 — edge table | `analysis/11_build_graph.py` → `graph_edges_s2.parquet` | **DONE** |
| 2 — router | `app/router.py` | NOT STARTED ← next |
| 3 — wire into app | ROUTE tab + two-rider switch | NOT STARTED |
| 4 — X-hour loop | arc orienteering | NOT STARTED |
| 5 — rebuild pitch | `docs/06_PITCH.md` still holds disproved claims | NOT STARTED |
| 6 — bake + rehearse | `data/cache/demo.pkl` | NOT STARTED |

Prerequisites the plan assumes ("BUILT") are all real and were re-verified:
cell table 26,987 cells, Rider DNA for 2 riders, analysis 01–11, docs 01–13.

## Phase 0 — every stage number, checked

| Claim in Part A | Verdict |
|---|---|
| 0.89 across 4,558 well-travelled cells | **EXACT.** `n_rides>=20` → n=4,558, Pearson 0.892, R² 0.80 |
| 0.73 rider-level over 5,747 corners | **EXACT.** `master_corners.parquet` 5,747 rows, r=0.730 |
| coverage box 47.38–48.03 / 10.72–11.96 | **EXACT to 2 dp** |
| max lean 43.8° | 43.7° over 244,930 moving points — fine |
| `sensorsaccelerationlongitudinal` is in g | **CONFIRMED** (see below) |
| ABS code 3 is the hard-braking event | **right, numbers drift** (see below) |
| hazard cluster near 47.83,11.76 is "three trip ids" | **DOES NOT HOLD UP — do not say it** |

Sensitivity of the headline correlation, so it can be quoted honestly under
challenge: r = 0.876 at `n_rides>=5` (n=11,055), **0.892 at >=20 (n=4,558)**,
0.848 at >=50 (n=1,442). It does not rest on one threshold.

### The units claim needed a careful test
A first pass regressing `d(v)/dt` on `a_long` with `np.gradient` gave slope 4.72
and looked like it refuted the claim. That test was invalid: `np.gradient` runs
across trip boundaries and assumes uniform 1 s cadence. Redone within-trip on
trusted cadence (`dt ∈ [0.8,1.3] s`, `v > 5 m/s`, n=244,486):

- forward slope 5.52 (attenuated by noise in x), inverse slope 10.15 (inflated)
- **truth is bracketed in [5.52, 10.15]** — contains 9.81, excludes 1.00 by far
- unit-free cross-check: p99|dv/dt| / p99|a_long| = **8.39**
- max |a_long| = 1.84 — absurd as 1.8 m/s² on a motorcycle, normal as 1.84 g

**Conclusion: it is in g. Safe to say.**

### ABS code 3 — correct finding, restate the numbers
Measured on user A, moving points only (`v > 5 m/s`):

| code | n | share | mean a_long | share decelerating |
|---|---|---|---|---|
| 0 | 1,420 | 0.58% | +0.001 g | 7.9% |
| 1 | 221,027 | 90.24% | −0.004 g | 52.0% |
| 2 | 22,423 | 9.15% | +0.003 g | 41.4% |
| **3** | **60** | **0.02%** | **−0.250 g (−2.45 m/s²)** | **86.7%** |

The plan says −2.22 m/s² and 93%; that is a different filter. **Quote these or
re-derive — do not say 93% without being able to say how you filtered.**

### The forensics card that fails
"The apparent hazard cluster near 47.83, 11.76 is three trip ids, not a crowd."
Measured: **24 cells in that box, 132 ABS samples, median 5 distinct rides per
cell, max 12.** That is not three trips. Either it refers to one specific cell or
it is wrong. **Do not offer this to BMW until someone re-derives it from the
lake** — it is pitched as a gift about their own data, and being wrong there is
the worst place to be wrong.

### Consistency trap
Two corner tables exist: 5,747 corners at r=0.730 (`master_corners`) and 5,253 at
r=0.765 (`corners_filtered`). Phase 3 of the plan quotes 5,253. **Pick one pairing
and use it in every slide.**

## Phase 1 — the edge table

`analysis/11_build_graph.py`, full 7,999-ride set, **8.7 s** on this Mac.

```
478,234 transitions → 50,767 raw edges → 38,351 edges at n_transitions >= 2
21,130 nodes | largest weakly-connected component 19,837 = 93.9%
median edge 21 m / 1.0 s
```

Connectivity comes from consecutive cell-to-cell transitions inside real rides,
never from a proximity join — a 250 m radius join connects across rivers, ridges
and motorway fences and will route through a lake live on stage.

Guards in the builder: runs of the same cell are collapsed (so a parked-but-still
-logging ride emits at most one departure, which is the documented 276-cell dwell
trap); transitions longer than 120 s or 2,000 m are dropped as logging gaps.

### The stop-check on mean degree is miscalibrated — ignore it
Out-degree came out **1.82**. The plan says that means the morton prefix is too
fine and to try 16 chars. Measured: **16 chars gives 1.88**, for 4.4× fewer nodes
(21,130 → 4,761) and cells ballooning to ~600×400 m. A genuinely too-fine prefix
would have moved degree a lot under that much coarsening. It did not, because
**~1.85 is what a road network is** — roads are linear chains, each cell leads to
about two others. **Staying at CELL_CHARS=18.** The real health check is the
largest connected component, and 93.9% clears the plan's 70% bar comfortably.

### Surprise index — partial null, report it honestly
```
spearman(abs_rate, surprise log(Ri/Rj)) = +0.051
spearman(abs_rate, absolute demand_p90) = +0.035
spearman(abs_rate, absolute radius_p50) = -0.155
tightening top decile 0.012 ABS/ride vs 0.002 radius-stable  →  4.89x
```
Surprise beats absolute *demand*, as design-consistency literature predicts, but
**loses to absolute radius**. Quote the decile contrast (4.9×) and say the rank
correlation is weak. **Do not claim surprise beats absolute geometry here.**

### Independent finding: ABS is orthogonal to cornering demand
Across cells with >=5 rides: ABS cells have median `v_p85` 12.4 m/s vs 24.6 for
non-ABS, and radius 111 m vs 263 m — but `demand_p90` is flat, 7.2 vs 7.6
(ρ=+0.05). Median `stop_rate` is 0.00 in both groups, so this is **not**
congestion. **Do not say "hard corners are where ABS fires."** The honest and
more interesting line: the hazard layer measures something independent of the fun
layer, which is why one model can carry both criteria without circularity.

## NDA / PII notes from this session

- Extracting the package **silently reverted the redaction in `09_DATA_MAP.md`**
  and re-exposed a street address. Re-redacted. **Re-check after any future
  extraction over the repo.**
- `crowd_gems*.csv` / `crowd_hazards*.csv` were already tracked from an earlier
  commit, so BMW ride coordinates sit in git history. Now untracked and
  gitignored. History still holds the old copies; the repo is private, so it is
  contained, but a history rewrite is the only full fix.
- `flowstate/data/` (1.7 GB salvaged lake) is gitignored and stays on the Mac.

## Reproducing any of this

```bash
cd ~/ehl_urich/flowstate
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake
export FS_OUT=$PWD/analysis/out
V=/Users/mulaydm10/ehl_urich/.venv/bin/python      # the venv is COMPULSORY
$V analysis/10_crowd_layer.py --set trips-samples-2 --tag _s2   # 13.8 s
$V analysis/11_build_graph.py --set trips-samples-2 --tag _s2   #  8.7 s
```
`FS_CELL_CHARS` overrides the 18-char prefix if the graph ever needs coarsening.
