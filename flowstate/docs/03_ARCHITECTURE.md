# 03 — ARCHITECTURE, MATHS AND ALGORITHMS

Everything here is designed to be implementable in Python within a 24-hour window, and to be defensible
line-by-line during the "algorithm walk-through" they said the final pitch would include.

```
                 OFFLINE (once per region, hours)              ONLINE (per query, milliseconds)
  OSM + DEM  ──┐
  crowd GPX  ──┼─►  ROAD DNA TENSOR  ──────────────────────────►  FLOW MATCH  ──►  ROUTE SEARCH  ──► UI
  land cover ──┘    (E x 24 float32, one row per edge)              (dot product)     (Dijkstra /
                                                                        ▲             orienteering)
  BMW rider telemetry ──►  RIDER DNA  ────────────────────────────────┘
                           (~40-dim vector per rider, incremental)     ▲
  weather / radar / sun / closures ──► TIME-AWARE COST OVERLAY ────────┘
```

The separation matters and is the answer to their **Scalability & Efficiency** criterion: the expensive
geometry is computed **once for everyone**, personalization is **one dot product per edge**, and the graph
is shared across the whole fleet.

---

## 1. Segmentation

Split the OSM road graph into segments of roughly uniform character, 100–500 m, breaking at junctions and
at large changes in curvature or gradient. Each segment is one row in the Road DNA tensor and one edge in
the routing graph. Keep the original OSM way id for joins and for drawing.

Filter out from the start: motorways/trunk with no scenic value (keep them as connectors only, heavily
penalised), private/service roads, and anything the profile cannot legally use.

---

## 2. ROAD DNA — what the road demands (24 features, computed offline)

### 2.1 Geometry (from OSM polyline + DEM)

| # | Feature | How |
|---|---|---|
| R1 | `radius_p10/p50/p90` | Fit circumcircle radius through sliding triples of shape points; smooth first, raw OSM nodes are noisy |
| R2 | `curves_per_km` | Count direction changes above a heading threshold (e.g. 12°) per km |
| R3 | `theta_req_p50/p90` | `arctan(v_ref^2 / (R * 9.81))`, `v_ref` = min(speed limit, crowd p50 speed). **The headline difficulty channel.** |
| R4 | `handedness` | Signed sum of turn angles / total turn angle → -1 (all right) to +1 (all left) |
| R5 | `rhythm` | Lag-1 autocorrelation of successive corner radii. High = uniform sweepers. Low = irregular/technical. **This is the "uniform curve vs fast curve" preference channel.** |
| R6 | `grade_mean`, `grade_max` | DEM sampled along the polyline, differentiated, smoothed over ~100 m |
| R7 | `climb_share` | Fraction of length ascending (direction matters — store per direction) |
| R8 | `elev_gain_per_km` | Total ascent / length |
| R9 | `sight_index` | Proxy for "clear road view": `f(radius, tree_cover, building_proximity, cut_slope)`. Small radius + dense land cover = blind. Cheap version: `min(1, R/80) * (1 - canopy_fraction)` |
| R10 | `width_class` | OSM `width` / `lanes` / highway class |
| R11 | `tunnel_share`, `bridge_share` | OSM tags. Tunnels are cold, dark and dull — penalise. |

### 2.2 Context (from OSM tags + land cover)

| # | Feature | How |
|---|---|---|
| R12 | `settlement_fraction` | Length inside `landuse=residential/retail/industrial` or inside a place polygon → their **inner-city red flag** |
| R13 | `signal_density`, `junction_density` | Nodes with `highway=traffic_signals`/`stop` per km → their **standstill red flag** |
| R14 | `surface_class` | OSM `surface` + `smoothness`; unknown defaults by highway class |
| R15 | `speed_limit` | OSM `maxspeed`, with country defaults |
| R16 | `scenic_index` | Viewpoints (`tourism=viewpoint`) within a buffer, water/forest/alpine land cover fraction, and **DEM openness** (how much horizon is visible from the segment — a real panorama proxy, and a genuinely differentiating computation) |
| R17 | `pass_flag`, `pass_altitude` | Local maximum of elevation along a through-route = an alpine pass. Also used for closure checks. |

### 2.3 Crowd-derived (from BMW fleet traces — the *Crowd Data* criterion)

| # | Feature | How |
|---|---|---|
| R18 | `crowd_v_p50`, `crowd_v_p85` | Observed speeds. **Use these, not the limit, as the realistic pace.** |
| R19 | `crowd_theta_p50/p90` | Observed lean angles — the ground truth for how hard the road actually is |
| R20 | `flow_index` | Share of traversals completed with no stop and low speed variance. **Their green flag "Flow", measured rather than assumed.** |
| R21 | `roughness` | RMS of vertical acceleration, normalised by speed → **Road Pulse**. Store a time series if coverage allows. |
| R22 | `popularity`, `detour_ratio` | How many riders use it, and how far out of their way they came for it → **revealed preference: the roads riders detour for are the good roads.** This is a very strong crowd-data feature and cheap. |
| R23 | `repeat_rate` | Share of riders who ride it more than once |
| R24 | `incident_proxy` | Segments with abnormal hard-braking / extreme-lean density vs their own curvature → latent hazard. Frame carefully and conservatively. |

**Gem detection:** top percentile of `flow_index * crowd_theta_p90 * detour_ratio` → the crown-jewel roads
used as attractors in loop generation (§5.2).

---

## 3. RIDER DNA — what the rider actually does (~40 dims, from telemetry)

Computed per ride and merged incrementally (streaming quantiles + Bayesian shrinkage toward an archetype
prior, so a rider with two rides is not over-fitted).

### 3.1 Cornering

- `theta_p50_L`, `theta_p95_L`, `theta_p50_R`, `theta_p95_R` — **split left/right. This is the asymmetry
  finding and it is the single most quotable output of the whole system.**
- `asymmetry = theta_p95_L − theta_p95_R`
- `headroom = theta_p95 − theta_p50` — how much they hold in reserve. Small headroom on hard roads = a
  rider at their limit = a safety flag.
- `theta_vs_crowd` — their lean relative to the crowd p50 *on the same segments*. This normalises away
  road difficulty and is the cleanest single skill estimate available.
- `sigma_theta` — consistency. Feeds `sigma(r)` in the Flow formula.

### 3.2 Style (the "brake hard then throttle hard" vs "smooth sweeper" axis)

- `brake_decel_p90` and **where** it happens relative to the corner (entry vs trail-braking into the apex)
- `throttle_reapply_phase` — how early after the apex longitudinal acceleration goes positive
- `lateral_G_shape` — trapezoidal (constant-radius sweeper) vs triangular (point-and-shoot)
- `jerk_rms` — RMS of d(accel)/dt, the cleanest "smoothness" scalar
- Derive a 2-axis style label: **Momentum ←→ Point-and-shoot** and **Smooth ←→ Aggressive**

### 3.3 Terrain, conditions, endurance

- `grade_tolerance_up`, `grade_tolerance_down` — descents are where nervous riders reveal themselves;
  measure braking intensity per unit of negative grade
- `surface_tolerance` — speed drop on rough segments relative to crowd
- `wet_ratio` — lean in rain / lean in dry, joined by timestamp to historical weather
- `pace_index` — their speed / crowd p50 speed, a unitless pace, **deliberately not an absolute speed**
- `session_length_p50`, `fatigue_slope` — regression of `jerk_rms` and `theta_p90` against elapsed time.
  A negative slope after ~90 min is the justification for **fatigue-aware ordering** (§5.4).
- `novelty_appetite` — share of new road per ride
- `urban_tolerance` — do they accept built-up detours or avoid them

### 3.4 Machine DNA (BMW's unfair advantage — they know the bike)

The same rider wants a different road on a different bike. Segment the prior by model family:
**GS/Adventure** (gravel, passes, long days), **S/RR Sport** (smooth radii, clean surface, tight rhythm),
**R/Cruiser** (scenic, gentle, low lean), **Tour** (distance, comfort, weather shelter). Say this in the
pitch — it uses a data field only BMW has.

---

## 4. FLOW MATCH — the scorer

### 4.1 Challenge and skill in one unit

```
challenge(s) = theta_req_p90(s)
             + a1 * max(0, grade_max(s) - g0)          # steepness above a neutral grade
             + a2 * (1 - sight_index(s)) * theta_req_p90(s)   # blind corners amplify demand
             + a3 * roughness(s)
             + a4 * wet_penalty(s, t)                  # time-aware, see §6

skill(r, s)  = theta_p95_dir(r, handedness(s))         # direction-aware skill!
             - b1 * (1 - grade_tolerance(r, sign(grade)))
             - b2 * (1 - surface_tolerance(r))
             - b3 * fatigue(r, elapsed_time)
             - b4 * (1 - wet_ratio(r)) * is_wet(s, t)
```

Note `skill` is a function of the **segment**, not just the rider: the same rider has different capability
on a left-hander in the rain going downhill than on a dry right-hand sweeper. That is the whole point.

### 4.2 The flow kernel

```
z    = (challenge - skill) / sigma_theta(r)
flow = exp( -(z - z_star)^2 / (2 * tau^2) )
```

### 4.3 The full segment score

```
score(s|r,t) = flow(s|r,t)
             * rhythm_match(s, r)          # does its corner rhythm match their preferred style
             * (1 - w_urban  * settlement_fraction)
             * (1 - w_signal * min(1, signal_density / 3))
             * (1 + w_scenic * scenic_index)
             * (1 + w_crowd  * flow_index)
             * weather_gate(s, t)          # 0..1, time-aware
             * safety_gate(s, r, t)        # HARD 0 if grade(s) > rider_grade(r) + 1
```

Multiplicative, not additive — so any single disqualifier (a closed pass, a road two grades too hard, a
hailstorm) zeroes the segment instead of being averaged away. Defend this choice explicitly; it is a real
modelling decision and judges notice.

`rhythm_match` is where the "some riders like uniform sweepers, some like fast technical corners" idea
lives: `exp(-(rhythm(s) - rhythm_pref(r))^2 / 2h^2)`.

### 4.4 Route-level aggregation

A route is **not** the mean of its segments. Two properties matter beyond the average:

```
Route = w1 * length_weighted_mean(score)
      + w2 * continuity          # longest contiguous run above 0.6 / total length
      - w3 * fragmentation       # number of transitions between high and low score
      - w4 * boredom_tail        # share of length below 0.25 (the motorway slog home)
      + w5 * stop_quality        # viewpoints/cafes at sensible intervals (BMW = lifestyle)
```

**Continuity is the feature that separates us from a naive scorer.** Three brilliant corners separated by
20 km of dual carriageway is a bad ride with a good average. Say that sentence in the pitch.

---

## 5. ROUTE SEARCH

### 5.1 Use case 1 — A to B

1. Compute the shortest/fastest path, note its length `L0` and duration `T0`.
2. Build a search corridor: the ellipse with foci A and B and a detour budget `beta` (user-set, default
   1.6, exposed as a "how much extra time?" slider). Typically 10^4–10^5 edges.
3. Edge cost: `cost(e) = length(e) / (epsilon + score(e|r,t))`, plus a turn penalty for U-turns.
4. Dijkstra/A* on the corridor. A* heuristic: straight-line distance / max achievable score. Runs in ms.
5. Produce **three** routes, not one, by running at `z* = 0.15 / 0.5 / 0.9`: **Cruise / Flow / Send it**,
   each labelled with its honest cost: *"+18 min, +34 flow"*. Alternates via edge-penalty diversification
   (multiply the cost of already-used edges by ~1.4 and re-run) so they are genuinely different roads.

### 5.2 Use case 2 — loop for X hours (this is the more impressive one — do it)

1. Time budget → distance budget via the rider's own `pace_index` and the terrain, not a flat 60 km/h.
2. Candidate **gems** within reach: high-score segments inside a disk of radius `~0.35 * distance_budget`.
   Cluster them (DBSCAN on geometry) to ~50–150 clusters.
3. Solve an **orienteering / prize-collecting tour**: choose a subset of clusters maximising total route
   score subject to the distance budget, connected by flow-weighted shortest paths. Greedy insertion by
   score-per-added-km, then 2-opt, then a few randomised restarts. Seconds, and good enough.
4. **Choose the direction (clockwise vs counter-clockwise) by handedness match** — evaluate both, keep the
   one that gives the rider more of their stronger corner direction. This is demo moment B and costs
   almost nothing to implement.
5. Randomised restarts also give **variety**: "give me a different one" is one button.

### 5.3 Safety gate (hard constraints, applied before scoring)

- Segment grade > rider grade + 1 → excluded entirely, and **shown to the user as excluded with a reason**
  ("Klausen pass: Black, you ride up to Red — unlock it with 2 more Red rides").
- Wet or below ~4°C → drop every rider grade by one level and re-gate.
- Night → drop one level, and weight `sight_index` harder.
- Never route onto surfaces the bike class cannot handle.

### 5.4 Ride shaping (ordering within a route)

- **Warm-up ramp:** the first 15 km are capped one grade below the rider's level. Cold tyres, cold rider.
- **Fatigue-aware ordering:** place the hardest cluster in the first 60% of the ride, the cruise home last.
  Justified by the measured `fatigue_slope`, not by vibes.
- **Stop placement:** insert a viewpoint or cafe near the middle and after any long technical section.
  BMW is a lifestyle brand — the stops are part of the ride.

---

## 6. TIME-AWARE EXTERNAL LAYER (the criterion most teams half-do)

The essential trick: we know *when* the rider will reach each segment, because we routed them. So every
external factor is evaluated at **arrival time**, not now.

- **Rain:** Open-Meteo forecast (free, no API key — critical at 02:00) or RainViewer radar tiles.
  Cost at segment `s` uses the forecast at `t_arrival(s)`. Say this: *"Everyone else overlays the current
  radar. We route in space and time — we ask what the pass looks like in the forty minutes when you'll
  actually be on it, and if the cell is arriving we flip the loop and ride it the other way round."*
- **Temperature at altitude:** roughly −6.5 °C per 1000 m. A 2000 m pass at 19:00 is cold. Feeds the wet/cold
  gate. Cheap, specific, credible.
- **Sun glare:** compute solar azimuth/elevation at arrival time and compare with the segment bearing.
  Low sun within ~15° of the heading = glare = a real, under-modelled hazard, and a genuine "nobody else
  thought of that" line. `pvlib` or ~30 lines of NOAA solar-position maths.
- **Pass closures / seasonal:** OSM `seasonal=yes` / `access:conditional`, plus a crowd check (zero traversals
  in the last N days on a normally busy pass = probably shut). Essential in Switzerland — do not get caught
  routing over a closed pass in front of a Zürich audience.
- **Traffic:** if any live source is available use it; otherwise crowd `flow_index` by time-of-day bucket is
  a legitimate substitute and uses BMW's own data.

---

## 7. Optional learned layer (only if ahead of schedule)

Do **not** replace the physical model. Add a thin re-ranker on top:

- **Label:** revealed preference — segments a rider repeats, detours for, or rides with sustained high flow.
- **Model:** gradient-boosted trees or logistic regression over Road DNA × Rider DNA interaction features.
- **Output:** a correction term, `score_final = score_physical * (1 + gamma * f_learned)` with small gamma.
- **Always** show per-feature attribution alongside it. The moment it becomes a black box we lose the
  explainability bonus they are openly offering.

---

## 8. Scalability and efficiency — the exact answer to give

Have these four sentences ready verbatim; it is a graded criterion and thirty seconds wins it:

1. **Road DNA is computed once per region, offline** — an `E x 24` float32 tensor, a few hundred MB for all
   of Switzerland and Bavaria, recomputed weekly, identical for every rider.
2. **Personalization is a dot product.** Rider DNA is a ~40-dim vector; the per-edge score is one small
   matrix-vector operation, vectorised over the whole corridor in NumPy. **One shared graph, millions of riders.**
3. **Search is bounded**, not global: an ellipse for A→B, a disk for loops, then ~10^4–10^5 edges of Dijkstra
   — single-digit milliseconds. Loop planning searches ~100 gem clusters, not 10^5 edges.
4. **Rider DNA updates incrementally** — streaming quantile sketches per ride, no retraining, no batch job.
   And it degrades gracefully: zero rides → bike-model archetype prior → converges within ~5 rides.
