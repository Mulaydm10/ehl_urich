# 25 — the backend, for whoever builds the front end

Written 2026-09-13, Phase 5. **The backend is finished.** This is the contract a front end (the native app, or anything else) builds against. Every example value below was read off the running service on the Mac from `data/cache/demo.pkl`, not copied from another doc.

## 1. What the backend is

- **One module: `flowstate/app/service.py`.** It is plain in-process Python, and every function returns JSON-shaped dicts and lists: no DataFrames, no numpy types, no morton codes you need to understand.
- **It runs off one file:** `data/cache/demo.pkl` (6.1 MB). `init()` loads it in **12 ms**, touches no raw data and makes no network call.
- **There is no HTTP server.** The Streamlit demo imports `service` directly. A native app needs a thin wrapper, which is not built. If you write one, the rules in §9 are not optional.
- **Coordinates:** inputs are `(lat, lon)` tuples. Map geometry comes back as `[lon, lat]` pairs, the order pydeck, Mapbox and GeoJSON expect.
- **Coverage is Bavaria only:** lat 47.38–48.03, lon 10.72–11.96. Outside it you get `ok: false` with a sentence in `note`. Show the sentence.

```python
import sys; sys.path.insert(0, "flowstate/app")
import service as S
S.init()                                   # -> status dict, 12 ms
S.compare((47.59, 11.75), (47.73, 11.37), "userA")
```

## 2. The rule every answer follows

**Anything that failed its pre-registered test answers with its verdict, not with a fake result.** Such a call returns

```json
{"ok": false, "note": "arc loop verdict FAIL; loop() is the answer"}
```

The front end must either show `note` or not offer the feature. It must never paper over it. The verdicts live in the committed test JSONs (`analysis/out/*_test.json`) and in docs 20–24.

## 3. Startup and reference data

| Call | Returns |
|---|---|
| `init(bake=None)` | `status()` below. Call once. |
| `status()` | `{source, loaded_s, cells: 5698, edges: 10318, riders: 4, osm: true, basemap_ways: 17345, precomputed: 21, joy_rides: 324, gems: 100, road_character: true, riders_modes: true}` |
| `riders()` | list of `{key, label, skill, sigma, gate, hardest_ridden, gate_agreement, n_cells, n_corners, grip_p95}` |
| `presets()` | `{routes: [{key, label, a, b, why}], loops: [{key, label, start}], dial: {"Cruise": 0.15, "Flow": 0.5, "Send it": 0.9}}` |
| `basemap()` | list of `{cls, path: [[lon, lat], ...]}`: grey OSM road polylines for drawing with the network off |
| `cells_layer(rider_key, z_star, min_flow=0, mode="flow")` | list of `{lat, lon, flow, demand, gated}`: every road cell scored for this rider |

**Riders, measured:**

| key | label | skill ° | σ | gate ° | hardest ridden ° | gate agreement |
|---|---|---|---|---|---|---|
| `userA` | User A - all rides | 11.40 | 5.59 | 22.59 | 21.24 | 1.063 |
| `userC` | User C - all rides | 10.65 | 5.44 | 21.53 | 20.08 | 1.072 |
| `bike_da67fa06` | Bike da67fa06 | 10.10 | 6.57 | 23.25 | 25.80 | 0.901 |
| `bike_4e1a9d64` | Bike 4e1a9d64 | 13.25 | 5.32 | 23.89 | 20.43 | 1.169 |

`userA` and `userC` are two different people. The `bike_*` profiles are user A on one motorcycle at a time.

## 4. Use case A — A → B

### `route(a, b, rider_key="userA", z_star=0.5, lam=10, mode="flow")`

```text
{
  ok: bool,
  note: str,               # "" on a healthy route; a caveat or a refusal sentence otherwise
  cells: [str],            # routing cell ids, in order; use them for "shared road" maths
  path: [[lon, lat]],      # the polyline
  segments: [{from: [lon, lat], to: [lon, lat], flow: 0..1, demand: deg}],   # colour by flow
  refusals: [{cell, lat, lon, demand, reason}],                             # at most 8
  summary: {...},          # below
  rider: str, z_star: float,
  explain: [str]           # sentences, in display order (section 6)
}
```

**`summary` keys:**
- `km`, `minutes`, `n_cells`;
- `mean_demand`, `max_demand` (degrees of lean the road asks);
- `mean_flow`, `peak_flow` (best 5 km), `final_flow`, `fun_score` (0–100), `dull_share`;
- `grip_lat_p95`, `grip_lat_max` (share of tyre grip, 0–1);
- `gate_deg`, `n_refused_nearby`, `imputed_cells`.

**Flow and the fun score are read at the dial that produced them.** Compare them between routes at the *same* dial, never across dial settings. Mean demand is absolute, so it compares everywhere.

**A refusal is a road deleted from the graph**, not a road made expensive. Draw each one as a red pin at `lat, lon` with its `reason`, e.g. `REFUSED — the crowd leans 26.9° here, past your gate of 22.6° (11.4° + 2σ)` (Kochel → Tegernsee, user A).

### `compare(a, b, rider_key="userA", lo=0.15, hi=0.90, mode="flow")` — the main screen

```text
{ low: <route>, high: <route>, lo_z, hi_z, overlap: 0..1, km_ratio, demand_gain, headline: str }
```

**Draw both routes on one map.** Cruise is steel blue `[130,148,178]` and Send it is gold `[255,210,63]`. Print `headline` as written.

**When `overlap > 0.60 and demand_gain < 0.5`, the dial has not moved the road.** Say so. The Streamlit caption for this case reads: *"On this pair the dial barely moves the road, and the app says so rather than dressing it up. Either the crowd graph has only one corridor here, or the more demanding road sits past this rider's safety gate - any road refused is pinned in red below."*

**Measured, Lenggries → Bad Tölz, user A:**

| | km | min | mean lean ° | peak lean ° | refusals |
|---|---|---|---|---|---|
| Cruise (0.15) | 46.9 | 42.8 | 7.02 | 17.1 | 0 |
| Send it (0.90) | 53.0 | 40.1 | 9.71 | 22.4 | 0 |

`overlap 0.167`, `headline "Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked of you."`

### `pareto(a, b, rider_key="userA")` — optional trade-off view

```text
{ ok, verdict: "PASS", routes_tried: 15,
  frontier: [{mode, z_star, minutes, km, mean_demand}] }   # sorted fastest first
```

- **What it is:** the routes no other route beats on both fewer minutes and more lean, across 5 dial settings × the offered modes.
- **It is short.** Across 200 pairs the median front spans **+3.5 min for +0.21°**.
- **It is often one route**, e.g. Lenggries → Bad Tölz, where the leaning road is also the faster one.
- **Allowed copy:** "a few more minutes buys a little more lean". Never show a joy share or a "knee".

## 5. Use case B — a loop for X hours

### `loop(start, hours, rider_key="userA", z_star=0.5, lam=10, mode="flow")`

This returns the same shape as `route`. `summary` adds `is_loop: true`, `budget_min`, `budget_fill` and `distinct_share` (the share of road ridden only once). `note` states the retracing share.

**Measured:** Kochel, 2 h, Send it, user A → `133.4 km, 118.7 min against 120, distinct_share 0.936, 1 refusal`.

- **Time budget:** the minutes come from the crowd's own median speeds, not an assumed average.
- **Latency:** the loop search takes about 160 ms.

`loop_arc(...)` returns `{ok: false, note: "arc loop verdict FAIL; loop() is the answer"}`. Do not offer a "dramatic arc" loop.

## 6. `explain` — the sentences, and what each one is

The order is fixed. Render them as a list, and keep **fun lines** and **safety lines** visually distinct.

| # | Sentence | Kind |
|---|---|---|
| 1 | "53 km, about 40 minutes." / loop: "A 133 km loop back to where you started, 119 minutes …" | fact |
| 2 | "This road asks a mean 9.7 deg of lean and peaks at 22.4 deg. Your gate is 22.6 deg …" | fit |
| 3 | "Best five kilometres score 0.57 out of 1 for fit at this dial setting." | fit |
| 4 | "Cornering asks about 33% of the tyre's grip here, against the 53% you have already used …" | physics readout |
| 5 | "Nothing on this route crosses your safety gate." **or** "N road(s) near this route were refused outright …" + up to 3 indented reasons | **safety** |
| 6 | "Hard braking around km 47: 4 of the 41 trips that ride this stretch set off the ABS hard-braking code here - …" (≤ 2) | **safety readout** |
| 7 | "Tightening bend around km 28: the corner radius drops from 670 m to 122 m in one step. Shown for safety; it is not part of the fun score." (≤ 2) | **safety readout** |
| 8 | "N cells had no corner in the crowd data and were treated as straight …" | data caveat |

- **Lines 6–7 are never part of the fun score.** Do not turn them into a rating, a colour on the route or a warning icon that implies prediction.
- **Keep the count wording.** "4 of the 41 trips" stays a count. The hazard verdict is REPEATABLE only as a population result (doc 21).

## 7. Riders, modes and the rest

| Call | Status | Returns |
|---|---|---|
| `modes()` | live | `[{key, verdict, phase4, offered}]`. **Offered: `flow` (default), `scenic`, `mountain`.** Not offered: `adventure` (FAIL), `urban` (its answer type failed, doc 23) |
| `route/loop/compare(..., mode="scenic" \| "mountain")` | live | same shapes. Copy must say **"leans the route towards higher ground where the network offers a choice"**. The median effect is +1–2 m, so never "takes you to the views / into the mountains" |
| `default_mode(rider_key)` | live | `{mode: "flow", why: "bike -> mode verdict DEFAULT-ONLY; every ride opens on Flow"}` |
| `rider_joy(rider_key)` | live, **WEAK** | `{verdict: "WEAK", n_rides, median_joy, components: {name: {auc, ci}}, grip_budget, explain: [str]}`. Show it only with its verdict. **Never rank or route on joy** |
| `ride_joy(trip_id)` | live | one ride's components. Trip ids are NDA data: never display or transmit them |
| `gem_pool(rider_key, z_star, n)` | live | `[{lat, lon, gem_score, demand_p90, n_rides, cell16, in_graph, gated, flow, routable}]` |
| `suggest_mode(first_minutes, rider_key)` | **not offered** | `{ok: false, note: "mood detection verdict FAIL; not offered"}` |
| `rhythm_fit(rider_key)` | **not offered** | `{ok: false, note: "rhythm match verdict NOT-PERSONAL"}` |
| `loop_arc(...)` | **not offered** | FAIL note (section 5) |
| commute upgrade, urban wander, solar/thermal | **do not exist** | blocked (no in-box commutes), failed (0/6 towns), not built |

## 8. Performance, measured on the Mac mini

| Operation | Median |
|---|---|
| `init()` from the bake | 12 ms |
| `route()` with the rider × dial graph already built | 22 ms |
| dial or rider change (graph build + route) | 40 ms |
| `loop()` 2 h / 3 h | 156 / 167 ms |
| `compare()` | two `route()` calls; not timed separately |
| `pareto()` | 15 `route()` calls over up to 15 graphs; not timed. It is the slowest call, so show a spinner |

Graphs are cached per (rider, dial, λ, mode), up to 13 at a time. Snap the dial to the three presets rather than a continuous slider, so the cache hits.

## 9. Rules a wrapper or front end must keep

- **The BMW data never leaves the Mac.** No hosted backend, no cloud function, no third-party API, no analytics SDK that ships payloads. Trip ids and ride coordinates are never displayed or logged.
- **Serve on the tailnet only.** Never bind `0.0.0.0`, never `tailscale funnel` / `serve --funnel`. `run_demo.sh` shows the pattern.
- **JSON hygiene:** some summary floats can be NaN (e.g. `grip_lat_p95` on a route with no corners). Python's `json.dumps` writes `NaN`, which is not valid JSON, so convert it to `null` in the wrapper.
- **Never score speed or show a time as an achievement.** `minutes` is a trip length, never a lap time.
- **Never display:** a 1.5–1.8× detour, ablation weights, leave-one-rider-out, left/right asymmetry, a "three trip ids" hazard card, the grip-budget/ABS mechanism line, or "the crowd brakes here".
- **Rehearsed pairs matter.** The dial moves the road on a minority of A → B pairs: the median demand gain over 200 pairs is −0.00°. Lead with the `presets()`; free points are allowed, but `compare()` will often say, truthfully, that nothing changed.

## 10. Rebuilding the bake

The backend is frozen. If you must rebuild (on the Mac only):

```bash
cd ~/ehl_urich/flowstate
V=/Users/mulaydm10/ehl_urich/.venv/bin/python
PYTHONIOENCODING=utf-8 $V analysis/14_bake_demo.py     # 2.6 s -> data/cache/demo.pkl
```

Doc 24 has the full rebuild from the raw lake and the gates that must still pass.
