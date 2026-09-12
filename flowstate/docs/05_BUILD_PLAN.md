# 05 — BUILD PLAN (24 hours, 3–4 people)

Clock reference: the brief is dated **12–13 September 2026**. This plan is written as **T+h from "now"**
(concept locked). Compress or stretch the blocks, but keep the order and keep the **freeze times**.

> **Three rules that decide whether you finish.**
> 1. **T−4h is a hard feature freeze.** After it, nothing new is added — only bug-fixing, the deck and rehearsal.
> 2. **The demo runs on a saved scenario file, not on a live API.** Pre-compute and cache one flawless demo
>    region, rider and route. Live calls fail on conference wifi; yours will not.
> 3. **Nobody blocks on the NDA data.** Track B starts on OSM alone and works with zero BMW rows.

---

## Stack (chosen for speed, not elegance)

| Layer | Choice | Why |
|---|---|---|
| Graph / map data | **OSMnx** (or Pyrosm for speed) + GeoPandas + Shapely | one call to get a drivable graph for a bbox |
| Elevation | SRTM/Copernicus DEM via `elevation`/`rasterio`, or Open-Topo-Data | grade and openness need a raster, not an API per point |
| Routing | **NetworkX** for clarity, `igraph`/`scipy.sparse.csgraph` if it gets slow | Dijkstra on 10^5 edges is fine |
| Telemetry | pandas + NumPy | it is time series, nothing exotic |
| Map matching | nearest-edge projection with a heading filter | **do not** build a full HMM matcher — it is a 6-hour tar pit |
| Frontend | **Streamlit + pydeck** | sliders and a 3D map in Python, no JS, hours saved |
| Charts | Plotly or Altair inside Streamlit | the flow curve and the radar |
| Weather | **Open-Meteo** (free, **no API key**) | at 03:00 nobody wants a signup flow |
| Deck | Slides/PowerPoint, exported to PDF | never present from a browser tab you might lose |

Environment: `python -m venv .venv` then `pip install osmnx geopandas shapely rasterio networkx pandas
numpy scipy scikit-learn streamlit pydeck plotly requests`.

---

## Repo layout to create (the next agent should follow this exactly)

```
F:\bmw\
  docs\                      # this documentation set
  data\
    raw\                     # BMW NDA data — NEVER commit, NEVER upload anywhere
    osm\                     # cached graph + DEM for the demo region
    cache\                   # road_dna.parquet, rider_dna.parquet, demo_scenario.pkl
  src\
    ingest_osm.py            # bbox -> segmented graph + geometry
    road_dna.py              # segment -> 24 features        (Arch. §2)
    telemetry.py             # BMW snippets -> clean per-ride frames, map-matched
    rider_dna.py             # rides -> ~40-dim profile      (Arch. §3)
    crowd.py                 # fleet traces -> per-segment crowd layer (Arch. §2.3)
    flow.py                  # challenge(), skill(), flow_score(), route_score() (Arch. §4)
    router.py                # a_to_b(), loop_for_hours(), safety_gate()        (Arch. §5)
    external.py              # weather at arrival time, sun azimuth, closures   (Arch. §6)
    explain.py               # why-this-route, counterfactual, attribution
    validate.py              # leave-one-rider-out, ablation, clustered SEs     (doc 07)
  app\
    streamlit_app.py         # the demo
  scripts\
    build_demo_scenario.py   # precompute EVERYTHING for the pitch, save to cache
  NOTES.md                   # running log — append as you go
```

### Function signatures worth agreeing on before anyone writes code

```python
# road_dna.py
def segment_graph(G, max_len_m=300) -> gpd.GeoDataFrame     # one row per segment
def road_dna(segments, dem, landuse, crowd=None) -> pd.DataFrame   # index=seg_id, 24 cols

# rider_dna.py
def rider_dna(rides: pd.DataFrame, archetype_prior: dict) -> dict   # ~40 keys, shrunk

# flow.py
def challenge(dna_row, conditions) -> float          # degrees of lean, Arch 4.1
def skill(rider, dna_row, conditions) -> float       # degrees, direction-aware
def flow_score(rider, dna, conditions, z_star, tau) -> np.ndarray  # VECTORISED over all segments
def route_score(seg_ids, scores, lengths) -> dict    # mean, continuity, fragmentation, tail

# router.py
def a_to_b(G, A, B, rider, z_star, detour_budget=1.6, k=3) -> list[Route]
def loop_for_hours(G, origin, hours, rider, z_star) -> Route
```

Keep `flow_score` **vectorised over all segments at once** — it is the scalability claim, and it also keeps
the Streamlit slider instant, which is the demo.

---

## Parallel tracks

| Track | Owner | Never blocked by |
|---|---|---|
| **A — Data & Rider DNA** | the person with the NDA login | — |
| **B — Road DNA & routing** | strongest Python/geo person | starts on OSM alone, zero BMW data needed |
| **C — App & visuals** | fastest UI person | works against fake DNA frames from hour 1 |
| **D — Narrative, deck, validation** | the presenter | everything; starts immediately |

Track C must build against a **mock** `road_dna.parquet` with random values in hour 1 so the UI is finished
before the real numbers land. This one decision is usually the difference between demoing and not demoing.

---

## Hour by hour

### T+0 → T+2 · Foundations (everyone)
- Lock the concept, the names (FLOWSTATE / Road DNA / Rider DNA / Thrill Dial / Road Pulse) and **the
  demo region**. Pick one: **Zürich → Klausen/Sattel/Sihlsee** or **Sursee/Napf**. Small, roads you can
  eyeball, guaranteed good curves. Do not attempt all of Switzerland.
- A: pull the BMW data, open one ride, **write down the actual column names and units in `NOTES.md`** (is
  lean in degrees or radians, is it signed, what is the sample rate, what is the timestamp timezone?).
  Half the teams will lose two hours to a units mistake — do it in the first twenty minutes.
- B: OSMnx download for the bbox, cache to disk, segment the graph, get DEM tiles.
- C: Streamlit skeleton + pydeck map + the Thrill Dial slider, wired to a mock scorer.
- D: draft the pitch spine from `06_PITCH.md`, and book a slot to ask BMW on site the questions in §Questions.

### T+2 → T+6 · The two DNAs
- B: **F17 F18 F21 F24 F28** — curvature, required lean, grade, settlement/signals, limits. Write
  `road_dna.parquet`. Sanity-check by eye: the known good pass must score above the motorway, or something
  is wrong and you want to know now.
- A: clean telemetry, map-match to segments (nearest edge + heading filter), then **F01 F02 F03 F04 F10** —
  and produce **the left/right lean histogram for one real rider**. That plot is demo moment B; get it early
  and put it straight in the deck.
- C: real `road_dna.parquet` loads, segments coloured on the map by a single feature.
- D: slides 1–4 drafted.

### T+6 → T+10 · Flow Match and the first route (the critical block)
- B+A: `flow.py` — `challenge`, `skill`, `flow_score`, `route_score` with continuity (**F38 F44**).
- B: `router.a_to_b` with the corridor and detour budget (**F40**), then the three alternatives (**F41**).
- **T+10 milestone (non-negotiable): one route renders on the map and the Thrill Dial changes it.**
  If this does not exist at T+10, cut the loop use case (F42) and spend the rest of the night on polish —
  a beautiful A→B demo beats two half-broken ones.
- C: the why-this-route card (**F67**) and the flow curve chart (**F66**).

### T+10 → T+14 · The differentiators
- B: loop generation (**F42**) + direction by handedness (**F43**) — the moment that wins it.
- A: crowd layer (**F29 F30 F31 F32 F33**) and style/smoothness (**F05 F06**).
- C: counterfactual panel (**F68**), rider radar (**F16**), route grade badges (**F58**).
- D: run the deck past someone who has not seen it. If they cannot repeat the one sentence back, rewrite it.

### T+14 → T+18 · The layer that makes it feel real
- External time-aware weather (**F52 F53**), pass closures (**F56**), warm-up ramp (**F45**),
  safety gate with visible reasons (**F47 F59**).
- Validation run (**F71 F73**) — even a small, honest result is worth more than another feature.
- Road Pulse (**F34**) if the data supports it; if not, one clean slide and say plainly it is a roadmap item.

### T+18 → T+20 · FREEZE. Scenario baking.
- `scripts/build_demo_scenario.py` precomputes the demo region, rider, routes and weather into
  `data/cache/demo_scenario.pkl`. **The app must run with the network cable unplugged. Test that literally.**
- Screen-record a full 3-minute run of the demo as a backup video. Wifi at hackathons fails; yours will not
  matter when it does.

### T+20 → T+23 · Rehearsal
- Three full run-throughs, timed. Then a fourth with someone interrupting with hostile questions.
- Prepare the algorithm walk-through separately from the pitch — they asked for both.
- Print/export the deck to PDF. Have it on two laptops and a USB stick.

### T+23 → T+24 · Sleep or buffer. Do not add features. Ever.

---

## Ask BMW on site (they said "ask us anything" — use it, and it is visible effort)

1. Is **lean angle** signed (left positive)? What sample rate? Is it IMU roll or corrected for camber?
2. Do the profiles include **bike model**? (That unlocks Machine DNA, F14.)
3. Is there any **ground-truth enjoyment** label — ride ratings, saved routes, repeats? (That unlocks the
   whole validation story, F71, which is our biggest edge.)
4. What does ConnectedRide already do about route difficulty, and where are its users unhappy?
5. Is there **suspension travel** or vertical acceleration in the channel list? (That is Road Pulse, F34.)
6. Which matters more to them: the A→B use case or the "X hours from here" loop? **Then weight accordingly.**

Asking #3 and #6 in front of them is itself a scoring event — it shows you are designing for their rubric.

---

## Failure modes and their pre-agreed fallbacks

| Risk | Fallback (decide now, not at 04:00) |
|---|---|
| NDA data late, thin or unusable | Road DNA needs zero BMW data. Rider DNA falls back to 4 hand-built archetypes and **you say so honestly** — "cold start is a designed path, not an excuse" |
| Map matching is a mess | Nearest-edge projection with a 45° heading filter, drop unmatched points, report the match rate |
| Lean angle missing or garbage | Derive lateral acceleration from GPS speed and path curvature; `theta = arctan(a_lat/g)`. Say it is derived. |
| Routing too slow | Shrink the bbox, raise the segment length to 500 m, precompute the demo routes |
| Loop generation does not converge | Ship A→B only, with three thrill levels. Better one thing that works. |
| Streamlit falls over in the pitch | The recorded video, and a PDF of the key screens in the deck |
| Someone asks "why those weights?" | `07_VALIDATION.md` §Ablation. This is the question we *want*. |
