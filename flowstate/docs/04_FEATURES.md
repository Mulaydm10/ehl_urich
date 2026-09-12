# 04 — FEATURE CATALOGUE

Every feature carries an ID, the **judging criterion it buys** (Crowd / Personal / External / Scale / Fun /
Safety / Explain), a **priority** and a rough **effort** in person-hours. Build strictly in priority order.

- **P0 = the demo does not exist without it.**
- **P1 = this is what makes us win** (build these second, they are the differentiators).
- **P2 = show as a slide/mockup, label it roadmap** — do not let a P2 eat a P1.
- **P3 = the vision slide only.**

Effort assumes one competent Python person and that the BMW data is reasonably clean.

---

## A. Rider modelling — "Rider DNA"

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F01 | **Lean-angle envelope split left vs right**, p50/p95 each, and the asymmetry index | Personal, Fun | **P0** | 2 |
| F02 | Comfort lean vs max lean (**headroom**) — how much they hold in reserve | Personal, Safety | P0 | 0.5 |
| F03 | `theta_vs_crowd` — their lean relative to the crowd on *the same segments* (road-difficulty-free skill estimate) | Personal, Crowd | **P0** | 1.5 |
| F04 | Consistency `sigma_theta` — feeds the width of the flow band | Personal | P0 | 0.5 |
| F05 | **Cornering style classifier**: momentum/sweeper vs point-and-shoot, from brake-decel phase + lateral-G shape | Personal, Fun | **P1** | 3 |
| F06 | **Smoothness / jerk index** — the metric we gamify instead of speed | Personal, Safety | **P1** | 1 |
| F07 | Gradient tolerance, **climb and descent separately** (descents reveal nervous riders) | Personal, Safety | P1 | 2 |
| F08 | Surface tolerance — speed drop on rough roads vs crowd | Personal | P1 | 1 |
| F09 | Wet tolerance — lean in rain / lean in dry, joined to historical weather by timestamp | Personal, External | P2 | 2 |
| F10 | `pace_index` — speed relative to crowd median, deliberately **not** an absolute speed | Personal | P0 | 0.5 |
| F11 | **Fatigue curve** — jerk and lean regressed on elapsed time; justifies ride ordering | Personal, Safety | P1 | 2 |
| F12 | Novelty appetite — share of new road per ride | Personal | P2 | 1 |
| F13 | Urban tolerance | Personal | P2 | 0.5 |
| F14 | **Machine DNA** — archetype prior by bike family (GS / RR / R / Tour). The data field only BMW has. | Personal, Scale | **P1** | 1.5 |
| F15 | Cold-start Bayesian shrinkage toward the archetype prior; converges in ~5 rides | Scale | P1 | 1.5 |
| F16 | Rider level **radar**, per dimension (Corner-L, Corner-R, Braking, Gradient, Surface, Wet, Endurance) | Explain, Fun | **P1** | 1.5 |

## B. Road modelling — "Road DNA"

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F17 | Curvature extraction: radius distribution, curves/km | Fun | **P0** | 3 |
| F18 | **Required lean angle** `arctan(v^2/(R g))` — the common currency with rider skill | Fun, Explain | **P0** | 0.5 |
| F19 | **Corner rhythm** (autocorrelation of successive radii) — uniform sweepers vs technical | Fun, Personal | **P1** | 2 |
| F20 | **Handedness balance** per segment — enables direction choice on loops | Fun, Personal | **P1** | 1 |
| F21 | Elevation profile, grade mean/max, climb share, ascent per km | Fun | **P0** | 2 |
| F22 | **Sight-distance / blind-corner index** — their "clear road view" green flag, which nobody computes | Safety, Fun | **P1** | 2.5 |
| F23 | Surface class from OSM tags | Safety | P0 | 0.5 |
| F24 | Settlement fraction + signal/junction density — their inner-city and standstill red flags | Fun | **P0** | 1.5 |
| F25 | **Scenic index**: viewpoints, land cover, and **DEM horizon openness** (a real panorama proxy) | External, Fun | P1 | 2.5 |
| F26 | Tunnel/bridge share, road width class | Fun | P2 | 0.5 |
| F27 | Alpine **pass detection** + altitude | External | P1 | 1 |
| F28 | Speed-limit profile — scoring stays inside legal limits, always | Safety | **P0** | 0.5 |

## C. Crowd layer (their own data — a graded criterion, do not under-invest)

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F29 | Crowd speed percentiles per segment → the realistic pace, replacing the limit | Crowd | **P0** | 1.5 |
| F30 | Crowd lean percentiles per segment → ground-truth road difficulty | Crowd, Fun | **P0** | 1.5 |
| F31 | **Flow index** — share of traversals with no stop and low speed variance. Their green flag, measured. | Crowd, Fun | **P1** | 2 |
| F32 | **Detour ratio / revealed preference** — the roads riders go out of their way for | Crowd, Fun | **P1** | 2 |
| F33 | **Gem detection** — crown-jewel segments, used as attractors for loop generation | Crowd, Fun | **P1** | 1 |
| F34 | **Road Pulse** — roughness from vertical acceleration, aggregated per segment | Crowd, Safety | P1 | 2.5 |
| F35 | Road Pulse **over time** — post-storm damage and closure detection from fleet coverage drop | Crowd, Safety | P2 | 3 |
| F36 | Latent hazard proxy — abnormal hard-braking density vs the segment's own curvature | Safety | P2 | 2 |
| F37 | Privacy design: on-device profile, aggregate-only upload, k-anonymity, home geofence | Scale | **P1** | 0.5 (slide) |

## D. Matching, routing and ride shaping

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F38 | **Flow Match kernel** `exp(-(z-z*)^2/2tau^2)` — the core | Fun, Safety | **P0** | 1 |
| F39 | **Thrill Dial** — one slider, `z*` from Cruise to Send it | Fun, Explain | **P0** | 1 |
| F40 | **A→B routing** in a detour-budget corridor, flow-weighted Dijkstra | Fun, Scale | **P0** | 4 |
| F41 | **Three alternatives** (Cruise / Flow / Send it) with honest cost labels: "+18 min, +34 flow" | Explain, Fun | **P0** | 1.5 |
| F42 | **Loop for X hours** — orienteering over gem clusters within a time budget | Fun, Scale | **P1** | 5 |
| F43 | **Direction choice (CW vs CCW) by corner-handedness match** — the asymmetry payoff | Personal, Fun | **P1** | 1 |
| F44 | **Route continuity term** — punishes gems separated by motorway slog | Fun | **P1** | 1 |
| F45 | **Warm-up ramp** — first 15 km one grade easier. Cold tyres, cold rider. | Safety, Fun | **P1** | 1 |
| F46 | **Fatigue-aware ordering** — hardest section in the first 60% | Safety, Personal | P1 | 1.5 |
| F47 | **Hard safety gate** — grade > rider grade + 1 excluded, *and shown with a reason* | Safety, Explain | **P0** | 1 |
| F48 | Wet / cold / night → every rider grade drops one level, re-gate | Safety, External | P1 | 1 |
| F49 | Stop planning — viewpoint or cafe mid-ride and after technical sections (lifestyle brand) | External, Fun | P2 | 2 |
| F50 | Fuel / range-aware stop insertion | External | P3 | 2 |
| F51 | **Live adaptive difficulty** — telemetry says they are struggling (lean below comfort, jerk up, hard braking) → offer the easier way home. Dynamic difficulty adjustment, borrowed from games, used for safety. | Safety, Personal | P2 | 3 |

## E. External / time-aware layer

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F52 | **Spatio-temporal rain** — forecast evaluated at *arrival time* per segment, via Open-Meteo (keyless) | External, Safety | **P1** | 2.5 |
| F53 | Rain-driven re-planning — flip loop direction or swap the pass when a cell is inbound | External | P1 | 1.5 |
| F54 | Temperature at altitude (−6.5 °C / 1000 m) feeding the cold gate | External, Safety | P2 | 0.5 |
| F55 | **Sun-glare avoidance** — solar azimuth vs segment bearing at arrival time | Safety, External | P2 | 2 |
| F56 | Seasonal **pass-closure** handling (OSM conditional access + crowd-coverage check) | External, Safety | P1 | 1.5 |
| F57 | Traffic by time-of-day from crowd flow index (substitute for a live traffic feed) | Crowd, External | P2 | 1.5 |

## F. Gamification and progression — the *after-ride* third of ConnectedRide

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F58 | **Route Grade — Blue / Red / Black**, ski-piste metaphor, from demanded lean + blind corners + grade + surface | Explain, Safety | **P1** | 1.5 |
| F59 | **Difficulty preview before committing** — "this pass is Black; you ride up to Red." The genuine safety product. | Safety, Explain | **P1** | 1 |
| F60 | **Skill Quests** — name the weakest dimension, prescribe the exact road that trains it, verify from the next ride's telemetry. *Prescribe → ride → measure → re-grade.* | Personal, Fun | **P1** | 3 |
| F61 | Badges for **style, never speed**: Smooth Operator (low jerk), Ambidextrous (L/R gap under 2°), Pass Collector, All-Weather | Fun | P2 | 1.5 |
| F62 | Ride library — favourite routes auto-detected, named, with **flow-score** personal bests (not times) | Fun, Personal | P2 | 2.5 |
| F63 | Ghost/replay coaching — "the crowd brakes 40 m earlier than you here", framed toward smoothness | Crowd, Safety | P3 | 3 |
| F64 | Social share of a route **with its grade**, and a friend's app warns if it is above their level | Safety, Fun | P3 | 2 |
| F65 | Group ride mode — route to the *weakest* rider's grade, not the average. Genuinely original, and a real cause of group-ride crashes. | Safety, Fun | P3 | 2 |

## G. Explainability — they said this scores bonus points

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F66 | **The flow curve chart** — rider skill, road challenge distribution, shaded flow band. One image that sells the whole concept. | Explain | **P0** | 1.5 |
| F67 | **"Why this route" card** — the three largest contributing factors with magnitudes | Explain | **P0** | 1.5 |
| F68 | **Counterfactual panel** — click a rejected road, see exactly why it lost | Explain | **P1** | 1.5 |
| F69 | Segment-level hover: full Road DNA and the per-rider match score | Explain | P1 | 1 |
| F70 | Data-source ledger — one slide showing every source, its weight, and its measured contribution (their literal deliverable #2) | Explain | **P0** | 1 |

## H. Validation — the differentiator almost nobody will attempt

| ID | Feature | Criterion | Pri | Hrs |
|---|---|---|---|---|
| F71 | **Leave-one-rider-out test**: does the fun score predict *held-out* revealed preference? | Fun, Explain | **P1** | 3 |
| F72 | **Clustered standard errors** — one rider contributes many segments, so they are correlated; the naive CI is a lie | Fun | **P1** | 1.5 |
| F73 | **Ablation** — how much does each data source actually add? Answers "how are they weighted and combined" with evidence instead of assertion. | Crowd, External, Explain | **P1** | 2 |
| F74 | Honest power statement — with N test riders, here is what we can and cannot claim | Explain | P1 | 0.5 |

---

## The P0 spine — if everything else burns, this is the demo

`F01 F03 F10 F17 F18 F21 F24 F28 F29 F30 F38 F39 F40 F41 F47 F66 F67 F70`
Roughly **26 person-hours** — achievable overnight by a team of three or four.

## The five that actually win it

`F01`+`F43` (asymmetry → loop direction) · `F38`+`F47` (one curve for fun *and* safety) ·
`F52` (time-aware weather) · `F60` (Skill Quests closing the loop) · `F71`+`F73` (validation and ablation).

## Deliberately excluded, and say so if asked

- Anything that scores or rewards **speed** or **lap times** on public roads. Off-brand, unshippable, unsafe.
- A trained black-box model as the primary scorer — it would forfeit the explainability bonus.
- A native mobile app. A web demo shows the same thing in a tenth of the time.
