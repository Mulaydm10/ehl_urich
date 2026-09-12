# CONTEXT — read this first

**BMW Motorrad "Find Your Thrill" route challenge · TUM.AI Hackathon Zürich 2026.**
Submission: pitch deck + this GitHub repo (Entire enabled) + live demo. **Deadline Sun 13 Sep 12:00 CEST.**

## Machine

You are on the **Mac mini** (arm64, macOS 26, ~314 GB free). This is the compute box — the Linux
laptop that set this up is at <300 MB free and cannot hold the dataset. Do the data work here.

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

- Physics bridge **corr 0.73** over 5,747 corners, EIV slope 1.08 — solid.
- Crowd-scale risk: braking cells demand 13.3° vs 12.5°, **p = 4.9e-3, n = 6,912** — solid.
- Rider-level risk 3.6× but **13 events, p = 0.071, CI [0, 17.1]** — weak; the pitch states this openly.
- ⛔ **Left/right asymmetry was tested and REJECTED** (2 riders, ~21k corners). Pitch slide 2 is dead.

## Blocked / open

1. **The download was truncated at 384 MB** → 98% of `trips-samples-1`, all of `exampleUserB`, and
   user C's manifest are missing. Everything so far is **Bavaria-only**. This blocks six features
   (F10, F29–F33) = the whole "BMW crowd data" criterion. **Fixing this is the highest-value move**,
   and this machine has the disk for it. See `flowstate/docs/11_ARCHIVE_SALVAGE.md`.
   Note: `derived/*.parquet` were built from the FULL lake and may already cover much of it.
2. **ABS semantics are contested.** `flowstate` treats `ridingabsbraking` as an intervention event
   (the Grossglockner demo moment depends on it); `research/FINDINGS.md` says it is a status code;
   BMW's schema says 0/1 but the data holds 0–3. **Ask BMW on site — it is question #1.**
3. `analysis/04_master_table.py` uses `positionmapmatchedheading`; switching to `positionrawheading`
   improves every downstream number.
4. Entire shows **Inactive** on entire.io — the GitHub App needs `ehl_urich` added to its repo list
   (needs GitHub sudo re-auth). Checkpoints push fine regardless.

## Non-negotiables

- **Never score speed or lap times.** Lean, smoothness, rhythm, flow — within posted limits.
- **NDA data never leaves the machine.** No hosted demo, no cloud notebook, no third-party API.
  `flowstate/analysis/out/planned_route*.csv` and `flowstate/session/transcript.*` are **gitignored**
  personal data (home addresses, employer, colleague names, BMW internal test codes) — they were
  transferred out-of-band and must never be committed.
- Weather: an Open-Meteo/RainViewer live layer was considered and dropped. The bike's own
  `sensorsoutsidetemperature` is real on 95% of rides and beats a weather API. Also: Sun 13 Sep is dry
  across all of Europe at 12:00, so a rain demo would show nothing.

## Environment

`uv` is the package manager. `uv venv .venv && uv pip install pandas pyarrow numpy scipy matplotlib`
(add `osmnx geopandas shapely rasterio networkx streamlit pydeck plotly` for the app).
Run scripts with `PYTHONIOENCODING=utf-8` — route names contain umlauts.
