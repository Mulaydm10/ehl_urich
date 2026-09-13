# 26 — prompt for a front-end AI, from scratch

Paste everything below the line into the front-end assistant as its first message. It assumes the reader
knows nothing about this project. It contains no BMW data. The only coordinates in it are the rehearsed
demo points, which are already in `service.py`. The full contract is `docs/25_FRONTEND_API.md`; attach
that file too if the tool accepts files.

---

You are building the front end for **FLOWSTATE**, a motorcycle route engine for BMW Motorrad's "Find Your
Thrill" challenge. The backend is finished and frozen. Your job is the rider-facing app on top of it. Do
not change the model, the scoring or the routes. Read this whole brief before writing code.

## 1. The idea, in one sentence

**Fun is not a property of the road. It is the fit between the road and the rider.**

A navigation app gives everyone the fastest road. FLOWSTATE gives each rider the road that fits them:
challenging enough to be absorbing, never past what they can safely ride. Everything is measured in
**degrees of lean angle**, which makes road difficulty and rider skill the same unit.

## 2. How the backend thinks (just enough to design honestly)

- **Road demand.** For each ~600 × 400 m patch of road ("cell"), the lean it asks is computed from
  physics, `θ = arctan(v²/(R·g))`. The speed and corner radius come from BMW's crowd of real rides.
  Where OpenStreetMap knows the posted limit, speed is capped at the limit first: **the app never
  rewards speeding.**
- **Rider skill.** From a rider's own telemetry: `skill` = the median demand of roads they ride, `σ` =
  its spread. Nobody fills in a questionnaire.
- **The flow curve.** `z = (demand − skill)/σ` and `flow = exp(−(z − z*)² / (2·0.5²))`, on a 0–1 scale.
  Too easy is boredom and too hard is risk; flow is the band between.
- **The Thrill Dial is `z*`,** with three settings: **Cruise 0.15, Flow 0.50, Send it 0.90.** It shifts
  how far above skill the rider wants to be.
- **The safety gate.** Any road demanding more than `skill + 2σ` is **deleted from the route graph**,
  not made expensive. The app shows these as refused roads with a reason.
- **Routing.** Dijkstra over the crowd road graph, with cost `length × (1 + 10 × (1 − flow))`. A loop
  search builds round trips that fit a time budget.

**Limits the UI must not hide:**
- **Coverage is only a box around Munich and the Alpine foothills:** lat 47.38–48.03, lon 10.72–11.96.
- **On most random point pairs the dial does not change the road.** The road graph is built from ride
  traces, so there is often only one corridor. The app says so in its own words.

## 3. The two jobs the user can do

1. **A → B:** the best road rather than the fastest.
2. **Loop for X hours:** a round trip from where they stand, back on time.

## 4. How to call the backend

- **Module:** `flowstate/app/service.py`, plain Python, in process. There is **no HTTP server yet**.
  Either run your UI in Python, or write a thin local wrapper that follows §8.
- **Types:** every function returns JSON-shaped dicts and lists.
- **Coordinates:** inputs are `(lat, lon)`; geometry comes back as `[lon, lat]`.
- **Data:** it loads one 6 MB precomputed file in 12 ms and needs no network.

```python
import sys; sys.path.insert(0, "flowstate/app")
import service as S
S.init()
```

| Call | What it gives you |
|---|---|
| `S.riders()` | `[{key, label, skill, sigma, gate, hardest_ridden, gate_agreement, n_cells, n_corners, grip_p95}]`. Keys: `userA`, `userC` (two different people), `bike_da67fa06`, `bike_4e1a9d64` (user A on one motorcycle) |
| `S.presets()` | rehearsed A→B pairs, loop starts, and the three dial values |
| `S.compare(a, b, rider_key)` | **the main A→B screen:** `{low, high, overlap, km_ratio, demand_gain, headline}`, where `low` is the Cruise route and `high` the Send it route |
| `S.route(a, b, rider_key, z_star, mode="flow")` | one route: `{ok, note, cells, path, segments, refusals, summary, explain}` |
| `S.loop(start, hours, rider_key, z_star)` | one loop: same shape, plus `summary.is_loop`, `budget_min`, `distinct_share` |
| `S.pareto(a, b, rider_key)` | optional: `frontier` rows `{mode, z_star, minutes, km, mean_demand}`, the "more minutes buys more lean" options |
| `S.modes()` | offered modes: `flow` (default), `scenic`, `mountain` |
| `S.rider_joy(rider_key)` | a ride-fun measurement **with its verdict (WEAK)**. Display only, never for ranking |
| `S.basemap()` | grey road polylines for an offline map |
| `S.cells_layer(rider_key, z_star)` | every road cell with `flow`, `demand`, `gated`, for a heat layer |

**The route payload:**
- `path`: the polyline.
- `segments[i]`: `{from, to, flow, demand}`. Colour the route by `flow`.
- `refusals[i]`: `{lat, lon, demand, reason}`. Draw red pins with the reason.
- `summary`: `km`, `minutes`, `mean_demand`, `max_demand`, `mean_flow`, `peak_flow`, `fun_score`,
  `grip_lat_p95`, `gate_deg`, etc.
- `explain`: sentences in a fixed order (§6).

**Any call can return `{ok: false, note: "..."}`.** Examples are a point outside coverage, or a feature
that failed its test (`loop_arc`, `suggest_mode`, `rhythm_fit`). **Show the note** or do not offer the
feature. Never fake a result.

## 5. Real example to design against — Lenggries → Bad Tölz, user A

`S.compare((47.59, 11.75), (47.73, 11.37), "userA")`:
- headline: *"Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked
  of you."*
- Cruise: 46.9 km, 43 min, mean lean 7.0°. Send it: 53.0 km, 40 min, mean lean 9.7°. Shared road 17%.
- **Draw both routes on one map at once**: Cruise in steel blue, Send it in gold. Never make the user drag
  a slider and hope something changes.

Other useful cases:
- **Kochel → Tegernsee** `((47.66, 11.35), (47.85, 11.85))`:
  - the dial barely moves the road (85% shared), and three roads are refused;
  - switching the rider to `bike_4e1a9d64` at Send it leaves only 10% shared road;
  - this is the "your thrill, not the thrill" moment.
- **Loop:** `S.loop((47.66, 11.35), 2.0, "userA", 0.9)` gives 133 km, 119 min against 120, 94% of the road
  ridden once.
- **User C on Lenggries → Bad Tölz:** the dial returns the same road at both settings, because the Send it
  road is past C's gate (22.4° vs 21.5°). One red pin explains why.

**When `overlap > 0.60` and `demand_gain < 0.5`**, show an honest line: the dial barely moves the road
here, either because there is one corridor or because the more demanding road is past this rider's gate.

## 6. The explanation sentences

`explain` is a list of plain sentences. Explainability is a judged criterion, so give them real space.
The order is fixed:
1. Distance and time.
2. Lean asked (mean and peak) vs the rider's gate.
3. Best five kilometres' fit score.
4. Tyre grip asked vs grip this rider already uses.
5. Refusals, or "Nothing on this route crosses your safety gate."
6. **Safety readout.** Up to two "Hard braking around km N: X of the Y trips that ride this stretch set
   off the ABS hard-braking code…" lines, and up to two "Tightening bend around km N…" lines.
7. A data caveat, if any.

**Style fun lines (2–4) and safety lines (5–6) differently.** Safety lines are information and never
part of the fun score. Keep the counts as counts ("4 of the 41 trips"). Do not turn them into scores,
colours on the route, or predictions.

## 7. Wording rules (these are product rules, not style)

**Allowed:**
- "the road that fits you";
- "refused: past your safety gate";
- "a few more minutes buys a little more lean" (Pareto);
- scenic/mountain modes: **"leans the route towards higher ground where the network offers a choice"**
  (the measured effect is small, a median of 1–2 m);
- Joy: always with its verdict, "weak measurement".

**Never:**
- speed, lap times or "faster than others" as an achievement;
- "takes you to the views" or "into the mountains";
- "we compose your ride as a dramatic arc" (tested, failed);
- mood detection;
- bike-type archetypes;
- commute upgrade;
- urban wander;
- a 1.5–1.8× detour;
- ablation weights;
- left/right asymmetry;
- "the crowd brakes here";
- "ABS fires because grip was used up in the corner".

**Never display trip ids or any ride coordinates** other than the route geometry the backend returns.

## 8. Hard constraints

- **The BMW data is under NDA and never leaves the Mac mini that runs the backend.** No hosted backend,
  cloud function, third-party API, remote logging, crash reporter or analytics SDK that ships payloads.
- **If you add a local HTTP wrapper:**
  - bind it to the Tailscale address only, never `0.0.0.0`, never `tailscale funnel`;
  - convert `NaN` floats to `null` before sending JSON.
- **Offline first.** The demo runs with the network unplugged. Use `S.basemap()` rather than online map
  tiles, and bundle any library locally.
- **Mobile first.** It is shown on a phone. Put A → B / Loop, the rider picker and the three dial buttons
  within thumb reach, the map large and the sentences readable.
- **Performance:**
  - `route` 22 ms on a warm graph, 40 ms after a dial or rider change;
  - `loop` about 160 ms;
  - `pareto` is 15 route calls, so give it a spinner;
  - use the three dial presets rather than a free slider, so results come from cache.

## 9. What to build first

1. A → B screen: rider picker, preset pairs, `compare()` on one map with both routes and the headline,
   Cruise / Send it / shared-road figures, then a single-dial route coloured by flow with red refusal pins
   and the `explain` list.
2. Loop screen: start presets, 1 / 1.5 / 2 / 3 h, dial, the loop coloured by flow, km / minutes against
   budget / share ridden once, `explain`.
3. A rider card: skill, σ, gate, hardest road ridden, gate agreement. Say plainly that the gate comes
   from the rider's own telemetry.
4. Optional: the Pareto options list, and the scenic/mountain mode switch with the allowed wording.

Ask before inventing any number, label or claim that the backend does not return.
