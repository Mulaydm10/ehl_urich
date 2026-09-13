# CONTEXT — read this first

**BMW Motorrad "Find Your Thrill" route challenge · TUM.AI Hackathon Zürich 2026.**
Submission: pitch deck + this GitHub repo (Entire enabled) + live demo. **Deadline Sun 13 Sep 12:00 CEST.**

## Machine

You are on the **Mac mini** (arm64, macOS 26, ~314 GB free). This is the compute box — the Linux
laptop that set this up is at <300 MB free and cannot hold the dataset. Do the data work here.

## Current position — 2026-09-12 ~22:00 CEST

The build now follows **`FLOWSTATE_Execution_Plan.docx`** (Parts A–E). Phase status:

| Phase | Deliverable | Status |
|---|---|---|
| 0 own the argument | the three answers, cold | numbers VERIFIED, rehearsal is human-side |
| 1 edge table | `analysis/11_build_graph.py` | **DONE** |
| 2 router | `app/router.py` | **DONE** — 60 ms/route |
| 3 wire into app | ROUTE tab + rider switch | **DONE** — `app/route_tab.py`, mobile-first |
| 4 X-hour loop | `route_loop()` | **DONE** — 16/16 starts, ~150 ms |
| 5 rebuild pitch | `docs/06_PITCH.md` + `docs/10_LIVE_DEMO.md` | **DONE** — both rewritten from doc 18, beats verified against the running service |
| 6 bake + rehearse | `data/cache/demo.pkl` | bake **DONE**; rehearsal not started |
| + external sources | OSM, not in the original plan | **DONE** |
| **FEATURES.md build** | phases 0-5 in **doc 19** | **Phases 0-2 DONE** — Joy Meter **WEAK**, grip-budget claim **REJECTED** (doc 20); road character (doc 21): rhythm, reversals, adventure **pass**, hazard **repeatable**, surprise **pass** (both in `explain()` as safety readout), dwell **redundant**, traffic **unreliable**, viewpoints **no data**; default route unchanged. **Phase 3 DONE (doc 22)**: user C is a real second rider (calibrated, not distinguishable in skill, beat 3 unchanged); bike DNA **no structure**; modes scenic + mountain **pass but small** (+1-2 m), adventure **fail**; mood **fail**; rhythm match **not personal**; flow bit-identical. **Phase 4 DONE (doc 23)**: arc loop **fail** (network caps it at 3/12), Pareto frontier **pass but short** (+3.5 min for +0.2 deg), commute **blocked** (no in-box commutes), urban wander **fail**; all baked answers identical. **Phase 5 DONE (doc 24) — BACKEND FINISHED**: full rebuild from the lake identical, 21/21 baked answers identical, all gates pass, AppTest sweep 23 runs / 0 exceptions, user C beat reproduces (17% shared), refusal/caption strings fixed; pitch + demo docs deliberately NOT rewritten (doc 24 §5 lists every drifted number); front-end contract = **doc 25** |

Beyond the plan, also done: `app/service.py` (the API the UI calls),
`analysis/13_osm_layer.py`, `analysis/14_bake_demo.py`, `run_demo.sh`.

**Phase 1→2→3 is a strict serial chain and is the whole submission.** Phases 0, 3, 5, 6 are
never to be cut; cut order if short is surprise index, then Phase 4, then peak-end.

**The authoritative record is docs 13-25** (19 = the FEATURES.md phase plan — read it before building anything; 20 = Phase 1 Joy Meter results; 21 = Phase 2 road character columns; 22 = Phase 3 riders and modes; 23 = Phase 4 answer types; 24 = Phase 5 integration + the pitch drift table; 25 = the front-end API contract; 26 = the from-scratch prompt for a front-end AI) — 13 (phases 0-1), 14 (the router), 15 (OSM),
16 (the loop, the API, the bake), 17 (the ROUTE tab), 18 (the pitch audit), 19 (the feature phases). They record what was measured, which plan claims survived
checking and which did not. Read them before quoting any number.

## The dataset is here now

The full package was recovered and extracted on this Mac:
`flowstate/data/raw/salvaged/` — **trips-samples-2 complete at 8,000/8,000 rides**,
trips-samples-1 partial at 1,469. 1.7 GB, gitignored, stays on this machine.
Rebuild the cell table in 24 s per grid (13.8 s before the Phase 2 columns) and the graph in 8.7 s
(commands in docs 13 and 21).

## The challenge

Two use cases, one or both: **A→B best route**, and **loop for X hours from here**.
Six judged criteria: BMW crowd data · personal rider data · external sources · scalability/efficiency ·
fun-score calculation · rider safety. Explainability + live demo score bonus.
BMW RED flags: inner city, standstills, bad weather, bad road surface.
GREEN: curves, high lean angle, 50–120 km/h, scenic views, flow, elevation, clear road view.

## What is in this repo — two independent work streams

**1. `research/` + `eda/` + `derived/`** (earlier session)
- `research/FINDINGS.md` — **the data-traps list. Read it before touching the data.** Shifted crowd
  timestamps, 46–51% zero elevation, ABS/ASC as status codes, a test-track cell, autobahn density traps.
- `derived/*.parquet` — already-built crowd tables: `S1_cells` 72,563 cells, `S1_trips` 75,993 trips,
  plus A/B/C rider tables. These load in <100 ms and need no raw data.

**2. `flowstate/`** (later session) — the concept, the code and the validated findings
- `flowstate/START_HERE.md` → `README.md` → `HANDOFF.md` → `docs/08`–`12`.
  **Docs 08–12 override docs 02–07 wherever they disagree.**
- `flowstate/app/streamlit_app.py` + `app/flowstate.py` — the demo app.
- `flowstate/analysis/01…10` — run in order to regenerate everything from raw data.

## The idea

Fun = the **fit** between road and rider, measured in degrees of lean.
Road demands `theta = arctan(v²/(R·g))`; telemetry shows what the rider actually uses.
`z = (challenge − skill)/sigma`, `flow = exp(−(z − z*)²/(2·tau²))`, `z* > 0` = the Thrill Dial.
One curve produces both **Fun Score** and **Rider Safety**.

## Validated (and not)

- Physics bridge **corr 0.73** over 5,747 corners (0.765 over 5,253) — solid. **The EIV slope 1.08 is POINT-level** (244,363 trackpoints, raw heading, r 0.602); at corner level it is 0.785 / 0.731. Never pair 1.08 with the corner correlation (re-validated, doc 24 §5).
- Crowd-scale risk: braking cells demand 13.3° vs 12.5°, **p = 4.6e-3, n = 6,895** (re-validated on the rebuilt grid) — solid.
- Rider-level risk 3.6× but **13 events, p = 0.071, CI [0, 17.1]** — weak; the pitch states this openly.
- ⛔ **Left/right asymmetry was tested and REJECTED** (2 riders, ~21k corners). Pitch slide 2 is dead.

## Blocked / open

1. ~~Truncated download~~ **RESOLVED.** The salvage worked; the lake is extracted here.
   F29–F33 are built, F10 is **PROVEN** (46.2% of user-A moving points snap to a crowd cell;
   per-trip pace vs lean ratio spearman **+0.502** over 66 trips). F32 detour ratio is
   unblocked but not yet computed — it needs the router.
2. ~~ABS semantics contested~~ **RESOLVED.** `ridingabsbraking == 3` is the hard-braking event:
   60 samples (0.02%), mean **−0.250 g**, 86.7% decelerating, vs codes 0/1/2 all ≈0 g.
   **But:** ABS is orthogonal to cornering demand (ρ=+0.05 vs `demand_p90`), so never say
   "hard corners are where ABS fires."
3. ~~`04_master_table.py` uses map-matched heading~~ — `10`/`11` already use `positionrawheading`
   only. Script 04 is superseded by the crowd layer for anything downstream.
4. ~~Entire Inactive~~ **RESOLVED.** A region mirror was added (EU Frankfurt); state is active.

**Still genuinely open:**

- **The "three trip ids" forensics card is wrong** — measured 24 cells, median 5 distinct rides.
  Do not offer it to BMW until re-derived. See doc 13.
- ~~`docs/06_PITCH.md` contradicts the demo~~ **RESOLVED 2026-09-13 (Phase 5).** Both `06_PITCH.md`
  and `10_LIVE_DEMO.md` were rewritten from doc 18, and every beat was then checked against the
  running `service.py` rather than against a doc. Two things the docs got wrong and the probe
  caught: **Lenggries -> Bad Tolz has NO refused roads** (`explain()` ends "Nothing on this route
  crosses your safety gate"), so do not promise red pins on that beat; and the app's honest
  "the dial barely moves the road" caption fires on **Kochel -> Tegernsee** (overlap 0.848, gain
  -0.17), not on the second preset. The script now uses that one screen for both halves of the
  payoff: the dial does nothing there, and switching rider changes 90% of the road.
  **Still never say:** 1.5-1.8x detour, any ablation weight, leave-one-rider-out, left/right
  asymmetry, or the "three trip ids" card.
- ~~Two corner tables disagree~~ **DECIDED in the rewrite: quote 5,253 corners at r = 0.765**
  everywhere, because that is the table the app renders. The 5,747 table keeps the low-speed
  manoeuvres and gives 0.730 with an EIV slope of 1.08 - say that if challenged, and say the
  filter is a definition rather than a search for a better number.
- **Coverage is Bavaria only** (lat 47.38–48.03, lon 10.72–11.96). A Zürich start returns nothing.
  Bound the demo map and rehearse start points inside the box.
- **The Thrill Dial moves the route on a MINORITY of A→B pairs.** Across 200 routable pairs the
  median demand gain is −0.00°; the effect concentrates where a second corridor exists. Two
  randomly clicked points will very likely give the same road twice, so rehearsed start points are
  a requirement, not stagecraft. Best measured pair: (47.59, 11.75) → (47.73, 11.37).
- **The plan's Phase 2 stop-check is unachievable.** Max detour anywhere in this network is
  **1.137×**, not 1.5–1.8×, for three measured reasons. Do not quote 1.5–1.8×. See doc 14.
- ~~Switching rider does not change the route~~ **partly wrong — it was the wrong pair.** On
  Lenggries -> Bad Tolz and Lenggries -> Kochel all three profiles return the same road, but on
  **Kochel -> Tegernsee the gate bites**: userA vs bike_4e1a9d64 share 73% of cells at Cruise and
  only **10% at Send it**, with 3-5 roads refused outright. Demo the rider switch there. See doc 17.
- **Weather stays dropped, and the cold-grip idea did NOT replicate**: spearman(lean, temp)
  = −0.016 over 5,253 corners (re-validated); the old "per-trip +0.224 at p=0.24 over 29 trips" does NOT reproduce — per-trip ρ is −0.07..+0.05 at every cut (doc 24 §5). `mu_for_temp` ships as a
  labelled engineering assumption feeding the safety readout only, never the fun score.

## The demo runs off a bake, not the repo

**A fresh clone cannot run a demo.** The lake and every derived parquet are gitignored and live
only on this Mac. `data/cache/demo.pkl` (6.1 MB) is the freeze artefact: scored cells, edges, the
OSM join, calibrated riders, a 17,345-way offline road basemap, and 21 pre-solved presets.
`service.init()` loads it in **12 ms**; a route on a built graph **22 ms**, a dial or rider change **40 ms** (measured Phase 5, doc 24).
**Rebake after any change to the router, the cell table or the OSM layer:**
`$V analysis/14_bake_demo.py` (2.4 s).

## Serving the demo

`./run_demo.sh` from `flowstate/`. Streamlit runs on this Mac and the phone opens
**http://100.80.210.100:8501** over Tailscale. `--lan` and `--local` are fallbacks;
conference Wi-Fi usually isolates clients, so prefer the phone's own hotspot with the
Mac joined to it.

**Never launch with `--server.address=0.0.0.0`.** It binds every interface, and on the
conference network this Mac also holds a routable public address - Streamlit happily
printed `External URL: http://141.70.42.255:8501`, which is an NDA-backed app on the
open internet. `run_demo.sh` binds the tailnet address and nothing else. Same reason,
still absolute: **never `tailscale funnel` / `tailscale serve --funnel`.**

## Standing decisions — 2026-09-13 ~01:30

**The Streamlit UI is FROZEN.** `route_tab.py` works and is verified; the intended product is a
native mobile app, so no further effort goes into Streamlit pixels. Ideas explicitly parked:
tap-the-map to pick points (`st.pydeck_chart(on_select="rerun")` does support it in 1.63 - verified,
just not worth building here) and any restyling. **New work goes into the backend.**

**Leaflet / folium was evaluated and REJECTED.** Two measured blockers, not opinions:
folium emits the Leaflet library itself from a CDN (10 external URLs, including
`cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js`), so with the network unplugged the map is
blank, not degraded - and that is the hard demo requirement; and the basemap is 17,345 ways /
76,116 points, which deck.gl pushes to the GPU as WebGL while Leaflet would draw on the CPU.
It also fixes nothing in the model: rendering is not the limitation.

**The geo stack is SAFE to install - the earlier GDAL warning was wrong.** Probed in a throwaway
venv at `/tmp/geoprobe` (never the project venv): `shapely 2.1.2, networkx 3.6.1, geopandas 1.1.4,
osmnx 2.1.1, rasterio 1.5.1, pyproj 3.8.0` all install from **wheels only**
(`--only-binary=:all:`) on Python 3.14 arm64, carrying **GDAL 3.12.4 bundled inside the wheels**,
on the same numpy 2.5.3 we already run. No Homebrew GDAL, no source build, no environment risk.
A CRS round-trip through EPSG:32632 was verified. Install with
`uv pip install --only-binary=:all: ...` and nothing else.

**What each is actually for, ranked** (nothing committed to yet):
1. **osmnx** - the only one that fixes a real limitation. Our graph is built from ride traces, so it
   is a bundle of corridors, not a road network: one path per O-D pair, hence the 1.137x detour
   ceiling and a dial that does nothing on most pairs. The strong design is **OSM for topology,
   BMW crowd for scoring** - real alternatives, chosen by real telemetry. Most invasive: it touches
   `build_graph`, the cell-to-node join, the bake, and every number in docs 14 and 16.
2. **rasterio** - gradient, a BMW GREEN flag we cannot score today because 46-51% of lake elevation
   is zero. Needs a DEM fetched once, kept local and gitignored.
3. **shapely** - snap the drawn path to real OSM way geometry instead of 600x400 m cell centres.
   Model unchanged; the line stops looking approximate. (Borderline UI, so parked with the freeze.)
4. **geopandas / networkx** - skip. `cKDTree` and `scipy.sparse.csgraph` already do these jobs and
   are faster. networkx earns a place only if we want Yen's k-shortest-paths instead of osmnx.

## Non-negotiables

- **Never score speed or lap times.** Lean, smoothness, rhythm, flow — within posted limits.
- **NDA data never leaves the machine.** No hosted demo, no cloud notebook, no third-party API.
  `flowstate/analysis/out/planned_route*.csv` and `flowstate/session/transcript.*` are **gitignored**
  personal data (home addresses, employer, colleague names, BMW internal test codes) — they were
  transferred out-of-band and must never be committed.
- Weather: an Open-Meteo/RainViewer live layer was considered and dropped. The bike's own
  `sensorsoutsidetemperature` is real on 95% of rides and beats a weather API. Also: Sun 13 Sep is dry
  across all of Europe at 12:00, so a rain demo would show nothing.

## Entire (session capture - required for submission)

Entire is enabled here and captures this session automatically. On this Mac the token lives in a
FILE store, not Keychain, so `export ENTIRE_TOKEN_STORE=file` must be set - it is already exported
in `~/.zshrc`. Verify with `entire status`; it should report `Enabled - branch main` and
`Checkpoints sync to: origin`. Checkpoints are created on commit and pushed on `git push`.

## Environment

`uv` is the package manager. `uv venv .venv && uv pip install pandas pyarrow numpy scipy matplotlib`
(add `osmnx geopandas shapely rasterio networkx streamlit pydeck plotly` for the app).
Run scripts with `PYTHONIOENCODING=utf-8` — route names contain umlauts.

**The venv is compulsory.** Use `/Users/mulaydm10/ehl_urich/.venv/bin/python` by absolute path
(a relative `../.venv/bin/python` triggers a sys.prefix RuntimeWarning). Installed and verified:
pandas 3.0.5, pyarrow 25.0.1, numpy 2.5.3, scipy 1.18.1.

**The router runs on the 16-char grid (`_c16`); everything else stays on 18 (`_s2`).** Deliberate:
at 18 chars the ride-derived graph has exactly one corridor between any two points, so no cost
function can detour around anything. This reverses doc 13's "staying at CELL_CHARS=18" **for
routing only** — scoring, the map and the corner work are unchanged. See doc 14.

**Re-check `docs/09_DATA_MAP.md` for a re-exposed street address after any archive extraction
over the repo** — unzipping the package silently reverted that redaction once already.
