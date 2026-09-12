# 14 — Phase 2: the router

Written 2026-09-13 on the Mac. Everything here was measured by
`analysis/12_route_calibration.py`, which reruns in ~18 s.

`app/router.py` is done and runs a full A→B route in **60 ms**. Four
functions as specified: `build_graph`, `snap`, `route_a_to_b`,
`route_summary`, plus `calibrate_rider` and `compare_routes`, which the plan
did not anticipate needing and which turned out to be the whole job.

## The plan's stop-check cannot be met, and that is a finding

Phase 2 ends with: tune LAMBDA until Send It is 1.5–1.8× the direct distance.
**The maximum detour available anywhere in this network is 1.137×.** Not a
tuning problem — three independent measurements say the graph has no room:

**1. LAMBDA has a mathematical ceiling.** `cost = L·(1 + λ(1−flow))` tends to
`λ·L·(1−flow)` as λ grows, so above some λ the *ranking* of paths cannot
change. Measured: λ = 3, 6, 10, 20, 40, 80 return the byte-identical route.
λ is not a dial you can keep turning.

**2. At 18 characters there is exactly one corridor.** Delete the shortest
path's edges and ask again:

```
_s2  Bad Tolz -> Tegernsee    30.4 km / 285 cells | 2nd disjoint path: NONE, disconnected
_s2  Kochel -> Tegernsee      52.8 km / 499 cells | 2nd disjoint path: NONE, disconnected
_s2  Starnberg -> Schliersee  66.1 km / 610 cells | 2nd disjoint path: NONE, disconnected
```

A graph built from 8,000 ride traces at 153×102 m is a **bundle of corridors,
not a road network**. Riders follow the same roads; the branches between them
were never ridden, so they do not exist. No cost function of any shape can
route around something that has no second path.

**3. So the router runs at 16 characters.** ~600×400 m cells let parallel
roads share a node and real alternatives appear:

```
_c16 Bad Tolz -> Tegernsee    30.7 km /  75 cells | 2nd disjoint: 41.5 km (1.35x)
_c16 Kochel -> Tegernsee      53.6 km / 130 cells | 2nd disjoint: 74.2 km (1.38x)
_c16 Starnberg -> Schliersee  54.9 km / 140 cells | 2nd disjoint: NONE
```

**This reverses doc 13's "staying at CELL_CHARS=18" — for routing only.**
Doc 13 was right that mean out-degree is a bad reason to coarsen, and it
tested degree. Degree was the wrong metric for a router. The right one is
whether a second corridor exists, and at 18 chars it does not, anywhere.
Scoring, the map, and the corner work stay at 18. **Only topology moves.**

The cost: a 600×400 m cell can fuse two genuinely separate roads into one
node. Edges still come only from real ride transitions, so no edge is
invented — but a false junction is possible where two roads pass within
600 m. In alpine valleys they usually do connect. This is a real risk and
should be said aloud rather than hidden.

## Two bugs found in the Phase 1 output

**`median_metres` is not edge length.** It is the distance between the last
sample before a cell boundary and the first sample after it — two samples one
second apart, ~21 m at 75 km/h. A cell is 153 m across. Summing it gave
**10.1 km for a route whose endpoints are 42.8 km apart**. The router now
computes length as the haversine distance between cell centres and derives
time from `length / median_speed`. `median_seconds` (always ≈1.0 s) is the
same artefact and is not used. *`graph_edges` itself is unchanged — the fix
lives in the consumer.*

**`10_crowd_layer.py` never read `FS_CELL_CHARS`.** It hardcoded
`CELL_CHARS = 18` while script 11 honoured the variable, so asking for a
16-char build produced an 18-char cell table and a 16-char edge table that
could not be joined. Doc 13 states this variable works; it only ever worked
for script 11. **Fixed.**

## The scale mismatch that made every road score zero

The first working router scored flow ≈ 0 on all 21,130 cells. The cause was
not code:

- `rider_dna` skill = peak lean **per corner**, p95 = **30.2°**
- `demand_p90` = 90th percentile over **every sample in a cell**, straights
  included, median **7.4°**

Different statistics of the same physical quantity. Subtracting one from the
other gives z ≈ −3 everywhere and the model says "nothing in Bavaria could
interest you" — an artefact of aggregation, not a fact about the rider.

`calibrate_rider` fixes it by measuring the rider with the crowd's own ruler:
take the cells this rider actually rode, and read skill off the same
`demand_p90` column the challenge comes from. Skill is the **median** of
those cells, not p95 — `z = (challenge − skill)/σ` is a stretch measured from
where the rider normally lives, so z* = 0 has to mean "the road I habitually
ride".

### The gate lands on the hardest road actually ridden

Nothing in the construction forces this, and it holds at both resolutions:

| grid | skill (median) | σ | gate = skill + 2σ | p95 of ridden cells | ratio |
|---|---|---|---|---|---|
| 18 chars | 14.68° | 6.31° | **27.29°** | 26.62° | **1.025×** |
| 16 chars | 12.63° | 5.19° | **23.01°** | 23.18° | **0.992×** |

A safety threshold derived from the *spread* of this rider's road choices
lands within 3% of the hardest road they have ever chosen — derived
independently, at two different cell sizes. This is the best evidence we have
that the gate is set at a real place, and it is the strongest single number
Phase 2 produced.

## What the dial actually moves

200 routable O-D pairs, 25–75 km apart, λ=10:

```
detour ratio : median 1.005   p90 1.055   MAX 1.137
cell overlap : p10 0.255      median 0.881
demand gain  : median -0.00 deg   p90 +0.75 deg
```

**Read the median honestly: for a typical pair of points the dial does
almost nothing.** The effect is real but concentrated in a minority of pairs
— the ones with a genuine alternative corridor. A judge who clicks two random
points will very likely see the same road twice. Phase 6's rehearsed start
points are therefore not stagecraft, they are a requirement.

Where it does work, it works well. The best pair in the network:

```
(47.59, 11.75) -> (47.73, 11.37)      direct 46.9 km
  Cruise  z*=0.15   47.0 km / 44 min   1.00x   mean demand  8.01 deg   peak flow 0.499
  Send it z*=0.90   53.3 km / 41 min   1.14x   mean demand 11.02 deg   peak flow 0.560
  dial effect: 1.13x the distance, 17% of cells shared, +3.01 deg mean demand
```

**The honest headline is not "we ride you further". It is: for the same two
points and roughly the same distance, the dial puts you on 83% different
roads, 38% more demanding.** That is a better claim than the plan's anyway —
it says the router is choosing character, not padding mileage.

## Safety, as measured

- Gate refuses **256 of 10,318 edges** at this rider's setting, and the graph
  stays connected (LCC 97.1% at 16 chars) — the fallback that reopens the
  gate as a penalty did not fire on any of the 200 scanned pairs.
- A refusal is a removed edge, not an expensive one. A safety gate you can
  buy past with a big enough detour budget is not a gate.
- Friction circle: `grip = sqrt(tan(theta)² + (a_long/g)²)/mu`, mu = 1.1.
  `a_long` is already in g (doc 13) — it is **not** divided by 9.81 again.
  Rider's own p95 = **1.04**; the Cruise route asks 0.23 and Send It 0.33
  (lateral only). Both routes sit far inside this rider's demonstrated
  envelope.
- `a_min`/`a_max` are clipped at 1.0 g before the grip percentile; the raw
  columns reach −2.6 g, which is not a motorcycle.

## Things the UI must not get wrong

- **`fun_score` is comparable across routes at the same dial, never across
  dial settings.** Flow is fit to whatever z* is asked for, so Send It can
  score *below* Cruise on the same roads (it does: 22.4 vs 25.4) without
  either being wrong. Show the dial next to the number, or compare
  `mean_demand`, which is absolute.
- Start and finish outside the coverage box return a refusal with a reason,
  not an empty map. **A Zürich start still returns nothing** — bound the map.
- Edges are **symmetrised**. `graph_edges` is directed by ride direction, so
  a road only ever caught northbound had no southbound edge; that is a fact
  about the sample, not the road. This does reverse genuine one-way streets,
  which is rare outside town centres and is the cheaper error.

## Reproducing

```bash
cd ~/ehl_urich/flowstate
export FS_LAKE=$PWD/data/raw/salvaged/anonymizedDataLake
export FS_OUT=$PWD/analysis/out
V=/Users/mulaydm10/ehl_urich/.venv/bin/python      # the venv is COMPULSORY

FS_CELL_CHARS=16 $V analysis/10_crowd_layer.py --set trips-samples-2 --tag _c16
FS_CELL_CHARS=16 $V analysis/11_build_graph.py --set trips-samples-2 --tag _c16
$V app/router.py                      # the stop-check, 60 ms per route
$V analysis/12_route_calibration.py   # all the evidence above, ~18 s
```
