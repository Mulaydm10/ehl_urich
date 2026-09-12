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
| 1 edge table | `analysis/11_build_graph.py` | **DONE** — 21,130 nodes / 38,351 edges, LCC 93.9%, 8.7 s |
| 2 router | `app/router.py` | **NEXT** — not started |
| 3 wire into app | ROUTE tab + two-rider switch | not started |
| 4 X-hour loop | arc orienteering | not started |
| 5 rebuild pitch | `docs/06_PITCH.md` holds disproved claims | not started |
| 6 bake + rehearse | `data/cache/demo.pkl` | not started |

**Phase 1→2→3 is a strict serial chain and is the whole submission.** Phases 0, 3, 5, 6 are
never to be cut; cut order if short is surprise index, then Phase 4, then peak-end.

**`flowstate/docs/13_PHASE0_PHASE1.md` is the authoritative record** of what was measured,
which plan claims survived checking, and which did not. Read it before quoting any number.

## The dataset is here now

The full package was recovered and extracted on this Mac:
`flowstate/data/raw/salvaged/` — **trips-samples-2 complete at 8,000/8,000 rides**,
trips-samples-1 partial at 1,469. 1.7 GB, gitignored, stays on this machine.
Rebuild the cell table in 13.8 s and the graph in 8.7 s (commands in doc 13).

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
- **Pitch slide 2 is still dead** (asymmetry rejected) and `docs/06_PITCH.md` still contains it.
- **Two corner tables disagree**: 5,747 corners at r=0.730 vs 5,253 at r=0.765. Pick one, use it
  everywhere.
- **Coverage is Bavaria only** (lat 47.38–48.03, lon 10.72–11.96). A Zürich start returns nothing.
  Bound the demo map and rehearse start points inside the box.

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

**Re-check `docs/09_DATA_MAP.md` for a re-exposed street address after any archive extraction
over the repo** — unzipping the package silently reverted that redaction once already.
