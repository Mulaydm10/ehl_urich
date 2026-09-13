# FLOWSTATE — the demo app

```
streamlit run F:\bmw\app\streamlit_app.py --server.headless true --server.port 8502
```

Then open <http://localhost:8502>. Run it from `F:\bmw` so it picks up `.streamlit/config.toml`
(dark BMW theme). Requires `streamlit`, `pydeck`, `plotly`, `pandas`, `numpy`, `pyarrow`.

**Offline by construction.** No API calls, no uploads, no external data fetches — the BMW data is
under NDA and never leaves the machine. The only network request the app can make is a basemap
tile, and there are two switches in the sidebar for that:

* **Basemap tiles** — off gives a pure-vector map, no tiles, no network.
* **Map renderer** — `pydeck` (GPU) or `plotly (no tiles)`, a plain lat/lon scatter that needs
  neither tiles nor WebGL. If pydeck throws for any reason the app falls back to it automatically.
  **Test the demo once with the network unplugged and the toggle off.**

**One stage tip:** the deck.gl maps zoom on mouse wheel (Streamlit ignores deck's controller
config), so scroll the page from the margin beside a map rather than over it. Drag to pan, `+`/`-`
to zoom, and the `plotly (no tiles)` renderer scrolls the page normally if that matters more than
the basemap.

---

## The model (implemented in `flowstate.py`, importable and testable)

```
challenge = req_deg                                    degrees of lean the corner demands
skill     = rider's lean p95, per corner direction     LEFT and RIGHT scored separately
z         = (challenge - skill) / sigma                sigma = rider's sd of lean_deg
flow      = exp(-(z - z*)^2 / (2 tau^2))               tau default 0.5
gate      : flow := 0 where challenge > skill + 2 sigma
```

`z*` is the **Thrill Dial** — 0.15 Cruise · 0.50 Flow · 0.90 Send it. One curve scores fun and
safety, because the gate is expressed in the same unit as the score.

`python F:\bmw\app\flowstate.py` runs a self-check: it asserts flow peaks at 1.0 when `z == z*`,
asserts the gate zeroes the score, and prints the dial sweep, the asymmetry intervals and a replay
sanity line.

## The four tabs

| Tab | What it shows |
|---|---|
| **🎬 RIDE REPLAY** | A real recorded ride animated from its own telemetry. Play / pause / reset, a 1–50× speed multiplier and a scrub bar. Live gauges (speed, lean with L/R, road demand, throttle, gear, ABS state, flow). The map draws the whole route dim and the ridden part bright, coloured by this rider's flow, with gold dots on flow moments and red dots on ABS limit events. Beside it the flow kernel with **BOREDOM / FLOW / RISK** annotated and a marker showing where the rider is right now, over a rolling demand-vs-lean trace of the last 2 km. Rides are downsampled to ≤ 2,000 frames, peak-preserving, and parked minutes are trimmed off both ends. |
| **🧬 RIDER DNA** | Lean histogram split LEFT vs RIGHT with p95 marked on each, a six-axis profile (cornering L, cornering R, braking, gradient, endurance, pace), and headline stats: lean p95, σ, headroom to the gate, ABS limit events, bikes, rides. Then the honesty panel — **the left/right difference with a 95% CI, computed four ways.** You can switch the rider scope to a single `bikeId`, because 15 bikes over 67 rides means bike confounds skill. |
| **🎚 THRILL DIAL** | `z*` and `τ` sliders plus Cruise / Flow / Send it presets. Every change re-scores all 5,253 corners. Map of the best-fitting corners, a table of the best 15, and a **why panel** for any corner: its demand, the rider's skill, z, the flow value, the gate threshold, and whether the gate fired. The centroid metric makes the movement measurable: 47.16 °N at Cruise → 46.93 °N at Send it, i.e. south out of Munich into the Alps, with no geography anywhere in the model. |
| **🗺 ROAD GRID** | The 1,090-cell Morton grid coloured and sized by `demand_p90`, with the 14 ABS-event cells marked as hazards, filterable by region and by how many rides crossed the cell. *Road DNA built from ride telemetry alone — no OpenStreetMap.* |

## Honesty built into the UI

* **The L/R asymmetry is not claimed.** The app computes it four ways — per-corner p95 bootstrapped
  **clustered on ride**, the same thing unclustered (shown precisely to demonstrate it is too tight,
  because corners inside one ride are not independent), the mean of per-ride differences, and BMW's
  own `leanAngleLeftMax − RightMax` from `cloudRecordedTracks-*.csv`. On user A they **disagree on
  the sign** and all sit inside ±1.2°, so the app prints **DO NOT ACT** and says why.
* **The radar is scaled against a stated reference** — the 5th–95th percentile of the same statistic
  computed per ride across this dataset (one rider, 15 bikes), not against a population of humans.
* **Gated corners are shown, not hidden**, in red, with the reason and the arithmetic.
* **Speed is context, never a score.** It appears on the gauges and on one radar axis, labelled as
  such, and it does not enter the flow model.

## Data traps honoured

* `sensorsbankingangle` dropped below 0.5 m/s (side stand — a parked BMW leans left ~15°).
* Positive `sensorsbankingangle` = RIGHT-hand corner.
* `ridingvehiclespeed` is m/s, and rides are split on time gaps > 5 s before anything is differentiated.
* `positionrawelevation`, never `positionmapmatchedelevation` (flat on 36% of rides).
* `ridingabsbraking == 3` is the only unambiguous hard-braking code.
* `sensorsaccelerationlongitudinal` is converted from **g** (BMW's README says m/s² and is wrong).
* Morton codes are read as strings — 32 digits overflows any int conversion.

## Two data problems this app hit that are not in the docs

1. **27 of user A's 100 rides have every speed channel flat zero** — `ridingvehiclespeed`,
   `positionmapmatchedspeed` and `positionrawspeed` are all 0 on the same rides, so `08_DATA_FINDINGS.md`'s
   "cleanest speed channel" is dead on a quarter of the archive. Those rides fall back to a GPS-derived
   speed and the replay tab says so in a banner; the ride picker labels them `[GPS speed only]`.
   Worth asking BMW about on site.
2. **Map-matched heading is quantised to road segments**, so at 1 Hz a single sample often reads zero
   yaw in the middle of a real corner (68% of moving samples on the test ride). Demand is a property of
   the corner, not of the instant — with 3–6 samples per corner the app holds it over a 5 s window,
   which lifts the correlation with measured lean from 0.74 to 0.77 on that ride.

## Files

| File | What it is |
|---|---|
| `app/flowstate.py` | All scoring logic and loaders. No streamlit import. Run it directly for the self-check. |
| `app/streamlit_app.py` | The four-tab UI. Every load wrapped in `@st.cache_data`. |
| `.streamlit/config.toml` | Dark BMW theme, telemetry off, headless. |

Inputs, all read-only from `analysis/out/`: `corners_filtered.parquet` (5,253 corners),
`master_corners.parquet` (5,747), `morton_grid.parquet` (1,090 cells),
`userA_all.parquet` (508,183 trackpoints), plus `data/raw/.../cloudRecordedTracks-*.csv` for
ride titles and BMW's own per-ride lean maxima.
