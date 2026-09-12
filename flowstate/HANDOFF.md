# HANDOFF LOG

Append-only running record so any Claude session, on any account, can pick this up cold.
**Read `README.md` first, then this file, then `docs/02_CONCEPT.md`.**
**Before you stop working, append a new entry at the bottom.** Newest entries go last.

---

## Entry 1 — 2026-09-12 · concept and planning complete

### What the session was given
- Working directory switched to `F:\bmw` (empty at the time).
- Two PDFs attached from `C:\Users\HP\Favorites\Downloads\`:
  `20260912 Hackathon BMW Motorrad short.pdf` (7 pp) and
  `20260912 Hackathon Presentation Zürich Short 2.pdf` (4 pp).
- A long free-form idea from the user, reproduced verbatim in §"Original idea" below.

### What was done
- The Read tool could not render the PDFs (`pdftoppm`/poppler not installed on this machine). **Workaround
  that worked and should be reused: PyMuPDF is installed** —
  `python -c "import fitz; d=fitz.open(path); [print(p.get_text()) for p in d]"`.
  `pypdf` and `pdfplumber` are also present. Python is 3.13.7.
- Both decks fully extracted and preserved in `docs/01_BRIEF.md`, so the PDFs are no longer needed.
- Designed the concept (**FLOWSTATE**) and wrote the complete document set listed in `README.md`.

### The decisions that were made, and why — do not silently reverse these

| Decision | Reasoning |
|---|---|
| **Lean angle (degrees) is the common unit** for road difficulty and rider skill | Makes "hardness 7 vs level 5" into physics instead of an invented scale. `theta = arctan(v²/(R·g))`. It is also a channel BMW is explicitly providing. |
| **Gaussian flow kernel with `z* > 0`**, not a threshold or a monotone score | Flow sits *slightly above* skill. Gives both failure modes (boredom, risk), one user-facing knob, and `tau` has a measured meaning (rider consistency). |
| **Fun and safety are one curve**, not a score plus a penalty | BMW lists them as two separate criteria; unifying them is the single strongest differentiator available. |
| **Multiplicative segment score**, not additive | A disqualifier (closed pass, two grades too hard, hailstorm) must zero the segment, not be averaged away. |
| **No deep learning as the primary scorer** | They offer bonus points for explainability and a live demo. An optional thin re-ranker with attribution is allowed; a black box is not. |
| **Never score speed or lap times** | Brand and legal landmine for a European OEM; the safer product is also the better one. Say it unprompted in the pitch. |
| **Streamlit + pydeck** for the demo | Sliders and a 3D map in pure Python. A mobile app or custom JS frontend is not affordable in 24 h. |
| **Continuity term in the route score** | Three great corners separated by 20 km of motorway is a bad ride with a good average. This is what separates us from a naive scorer. |
| Ski-piste **Blue / Red / Black** grading metaphor | Instantly legible to a Zürich/Munich audience, and carries the right connotation: Black is not "better", it is *for a different skier*. That is the thesis in a metaphor they already own. |

### Still open — decide these early
- **Which use case to prioritise** if time runs short: A→B or the X-hour loop. Ask BMW on site which they
  care about more (question 6 in `docs/05_BUILD_PLAN.md`). Current default: build A→B first, loop second —
  but the loop is where the asymmetry/direction demo moment lives, so do not drop it lightly.
- **Demo region bbox** — not yet chosen. Candidates: Zürich → Klausen/Sattel/Sihlsee, or Sursee/Napf.
- **Actual telemetry schema** — unknown until the NDA data lands. Everything in `docs/03_ARCHITECTURE.md` §3
  assumes lean angle, speed, 3-axis acceleration, GPS and timestamps exist. If lean is missing, the fallback
  is deriving lateral acceleration from GPS speed and path curvature (`docs/05_BUILD_PLAN.md`, failure table).
- **Is there any enjoyment ground truth** (ratings, saved routes, repeats)? If yes, `docs/07_VALIDATION.md`
  gets much stronger. Ask BMW.
- **Team size and split** unknown; the build plan assumes 3–4 people on four parallel tracks.

### What has NOT been done
- **No code exists.** `F:\bmw` contains documentation only — no `src/`, no `app/`, no `data/`.
- No BMW data has been seen. Everything about the telemetry is an assumption based on the brief's stated
  channels ("GPS Tracks, Motorcycle Sensor Data (Speed, G Forces, Lean Angle, etc.)").
- No OSM extract or DEM has been downloaded.

### Recommended next action for the continuing agent
Scaffold the repo exactly as laid out in `docs/05_BUILD_PLAN.md` (§"Repo layout") and implement the P0
spine from `docs/04_FEATURES.md` in this order: `ingest_osm.py` → `road_dna.py` → `flow.py` →
`router.a_to_b` → `app/streamlit_app.py`. Build the Streamlit app against a mock `road_dna.parquet` in
parallel from the start.

---

## Original idea, as given by the user (preserved verbatim — it is the source of the concept)

> this is our hacakhathon topic and i want you to give me features for this hacathon and they want to make
> the the riding experience good for riders in means of giving not the shortest path but the interestio ng
> path but and but there are so many factors for this like not every rider likes the incline riding or
> decline riding and also some can do right curve some can do left curve in short not everyone is a pro
> rider to ride for that perfect experience for everyone the defination of flow state is different and
> defination of joy ride is different my and i was thinking to make a level semulation for the rides and
> like if some one wants to go from one location to other and there are severel wasy to get there so rate
> the hardness of the ways and aslo rate the level of rider like at make on which routes he can ride and
> also that and like a gaming semulation and also track his fav routes rides ans also and also something
> like if some one is aming to become a pro rider he will get the routes want he has to do and how he has
> to do to level up and also track some how what he likes like uniform curve on curve or fast curve like
> fast break and then fast fast throtal this is only one thing im saysing all similar things to be
> considered also that an gods eye view integrated to guide through teh roads and also to see the roads and
> pithols are ok after a bad wheaher and all this is just an idea i want you to read my idea see all possib
> le angles and give me a winning idea and all the work should be transcriot recorder for other claude
> accouths to continue where you stoped write everything and thnks

**Where each part of that idea ended up:**

| Original idea | Where it lives now |
|---|---|
| interesting path, not shortest | The entire Flow Match objective — `docs/02_CONCEPT.md` §2 |
| not everyone likes inclines / declines | `grade_tolerance_up` / `grade_tolerance_down` — F07, and they are measured separately because descents are where nervous riders reveal themselves |
| some can do right curves, some left | **F01 asymmetry → F43 loop direction.** Promoted to the single best demo moment in the pitch |
| not everyone is a pro; flow state differs per person | The whole thesis. The `z*` Thrill Dial and per-rider `sigma` — `docs/02_CONCEPT.md` §2 |
| level simulation, rate hardness of ways, rate rider level | F58 route grade (Blue/Red/Black) + F16 rider radar, both in **degrees of lean** so the comparison is physical, not arbitrary |
| gaming simulation | Kept, but re-based on flow theory so it is a model rather than a metaphor; and F51 live adaptive difficulty is literally dynamic difficulty adjustment from games, used for safety |
| track favourite routes / rides | F62 ride library, scored on **flow, never on time** |
| aiming to become a pro — which routes, and how, to level up | **F60 Skill Quests**, closed loop: prescribe → ride → measure → re-grade |
| track what they like: uniform curves vs fast curves, hard brake then hard throttle | **F19 corner rhythm** (autocorrelation of successive radii) + **F05 style classifier** (momentum vs point-and-shoot from brake phase and lateral-G shape) |
| god's eye view to guide through the roads | The pydeck 3D map with Road DNA rendered — it is also their literal deliverable #3, "a visual representation of the data and algorithm" |
| are the roads and potholes OK after bad weather | **F34/F35 Road Pulse** — roughness from vertical acceleration across the fleet, plus closure detection from a coverage drop. Pitch line: *"BMW doesn't need to buy road-condition data; BMW's customers are generating it right now."* |

Nothing from the original idea was dropped. Two things were **added** on top: the flow-theory framing that
makes fun and safety one curve, and the validation of the fun score itself.

---

## Entry 2 — 2026-09-12 · the real data arrived; every feature tested against it

### What the session was given
The NDA data, as two password-protected archives in `C:\Users\HP\Favorites\Downloads\`
(`exd_download.zip`, `exd_download (1).zip`), password `&mLaR?TUM.ai#2026!`.

### How to open them (this took a while — do not rediscover it)
Both are **nested** zips: an outer plain zip containing an inner **AES-encrypted** zip (compress_type 99).
Python's stdlib `zipfile` cannot do AES — `pip install pyzipper`, then `pyzipper.AESZipFile(p)` +
`setpassword(b'...')`. Extracted to `F:\bmw\data\raw\` (NDA — never commit, never upload).

### What we actually have
- ✅ `exampleUserA` — **100 rides, 508,183 trackpoints, 89 planned GPX routes, 5 years** (2021-07 → 2026-08)
- ✅ `README.md` — the full 43-column schema reference and the data-lake description
- ✅ `tripViewer/` — BMW's own quick-and-dirty Leaflet viewer (`python -m http.server` in `web/`)
- ❌ `datasetHackathon.zip` — **the 384 MB download is TRUNCATED** (no EOCD, no central directory; the
  outer entry is streamed with flag bit 3 so sizes live in a missing trailer). It holds the crowd lake
  (`trips-samples-1`: 77,700 rides / 26.7 M points; `trips-samples-2`: 7,999 / 2.4 M) **and users B and C**.
  **Re-download is the top priority** — it blocks F10, F29–F33 and the whole crowd-data judging criterion.

### The analysis written (all runnable, all in `analysis/`)
| Script | What it does |
|---|---|
| `01_profile.py` | schema reality-check: sample rate, missingness, flat-channel detection, sentinels → `out/profile_*.csv`, `out/userA_all.parquet` |
| `02_feature_tests.py` | verdict on every planned feature + hunt for unused signal → `out/feature_verdicts.csv`, `out/unused_signal.csv` |
| `03_deep_checks.py` | ABS/ASC semantics, the physics bridge per corner, planned-route ground truth |

**Findings live in `docs/08_DATA_FINDINGS.md`, which overrides docs 02–07 wherever they disagree.**

### Decisions and corrections from this entry — carry these forward
| | |
|---|---|
| ✅ **Keep** the lean-angle unit bridge | Confirmed: corr **0.73** over **5,747 corners**; errors-in-variables slope **0.92** at point level. Use a calibration `k ≈ 0.8`; the gap is body position (riders hang off), which is why the ratio falls to 0.70 in the hardest corners. |
| ⚠️ **Do not claim** universal L/R asymmetry | For user A it is ~1° and **the sign flips with the estimator**. Per-ride maxima are noise; **per-corner p95 is the right estimator**. Re-test on B and C. |
| ❌ **F05 brake-phase style is dead** | `sensorsbreakpressurefront/rear` are exactly 0 on all 100 rides. |
| ✅ **New: `ridingabsbraking == 3`** | Mean accel −2.22 m/s², 93% decelerating, 33/100 rides. A real limit-event detector, and a better channel than brake pressure. Added as **F75**. |
| ❌ **Road Pulse via vertical accel is dead** | `sensorsaccelerationvertical` flat on 91% of rides. Rebuild on ABS-3 density / speed variance / GPS accuracy, or present as roadmap. |
| ⚠️ **README unit error** | `sensorsaccelerationlongitudinal` is in **g**, not m/s². Slope 5.47 against d(v)/dt. Tell BMW — it is free credibility. |
| ⚠️ **Lean sign / side stand** | Positive banking = **right** corner. At standstill p05 = −14.7° = the parked bike on its side stand. Drop lean where speed < 0.5 m/s. |
| ⚠️ **20 distinct `bikeId` for one "user"** | User A is an internal test rider. Bike confounds skill — control for it, and consider it as a natural experiment. |
| ✅ **Prioritise use case #2 (the loop)** | **48% of his 89 planned routes are round trips**, median 163 km, named after alpine passes (Grossglockner, Nockalm, Obertauern, Felbertauern). |
| ⚠️ **Weather join limitation** | Example-user timestamps are real; the anonymized lake's are **shifted per trip**, so crowd rides cannot be joined to historical weather. |
| ⚠️ **`isFavorite` is False on all 101 rides** | The field exists in BMW's schema. Check B and C — one rider with favourites upgrades `07_VALIDATION.md` from proxy labels to real ones. |

### Nine new features the data handed us
**F75** ABS limit events · **F79** odometer as experience · **F77/F78** gear+RPM mood detector ·
**F80** measured tyre warm-up · **F54+** on-bike ambient temperature · **F81** engine-temp congestion
detector · **F83** GPS accuracy as an enclosure proxy · **F82** range for fuel stops · **F76** ASC (weak).
Detail in `docs/08_DATA_FINDINGS.md` §6 and `analysis/out/unused_signal.csv`.

### State of the code
`analysis/` only. Still **no product code** — no `src/`, no `app/`. The P0 spine from
`docs/04_FEATURES.md` is unchanged except that **F75 and F79 should be added to it**.

### Next action
Re-download the crowd archive; meanwhile scaffold `src/` per `docs/05_BUILD_PLAN.md` using
`analysis/out/userA_all.parquet` as the stand-in rider, and lock the Munich/Alpine-foothills bbox.

---

## Entry 3 — 2026-09-12 · master table, all cross-mappings, the key result, and the live demo

### The key result — the project's single most important finding
**The risk side of the flow curve predicts real hard-braking / ABS events.** Hard-braking rate rises
**monotonically across all six z bands** (0.23 → 0.17 → 0.29 → 0.74 → 0.75 → 0.87%), a **3.6× risk ratio**
between "over their head" (z>1) and "at or below their level" (z<0.5).

**Do not overclaim it.** Fisher exact **p = 0.071**; bootstrapped over rides (not corners — they are
correlated) the 95% CI is **[0.0, 17.1]**; there are **13 events** in the whole sample. The honest framing
is in `docs/10_LIVE_DEMO.md` §1 and it is a *stronger* pitch than a false claim would be.
Reproduce with `analysis/07_risk_validation.py`.

**Demo moment found in the data:** `47.0766, 12.7646` — required lean 38°, z = +0.97, **2,253 m on the
Grossglockner High Alpine Road**, where the model said "above his level" and the ABS then fired.

### What was built
| File | What |
|---|---|
| `analysis/04_master_table.py` | **The one big thing** — corner-level master table, 5,747 corners × 35 cols fusing road + rider + context + identity; plus the morton-cell road grid (Road DNA with no OSM) |
| `analysis/05_missing_features.py` | Every remaining feature test: warm-up, fatigue, temperature, bike-vs-rider, style, rhythm, mood, tyre warm-up, GPS proxy, end-to-end flow score |
| `analysis/06_cross_mapping.py` | All cross-dataset joins M1–M6 |
| `analysis/07_risk_validation.py` | The key result above |
| `docs/09_DATA_MAP.md` | Every data asset, the master table, the mapping matrix, the complete feature verdict list |
| `docs/10_LIVE_DEMO.md` | The live demo design, the 5-beat script, and the out-of-the-box ideas ranked by impact ÷ risk |
| `app/` | Streamlit demo (built in parallel — see `app/README.md`) |

### New findings that change decisions
| Finding | Consequence |
|---|---|
| **F45 warm-up CONFIRMED** — use-ratio 0.768 ±0.034 in the first 5 km vs 0.813 ±0.007 after 15 km, non-overlapping | The warm-up ramp is **measured**, not folklore. Promote it. |
| **F77/F78 mood detector STRONG** — corr(rpm-per-kmh, median lean) = **0.54** across rides | The bike reports the rider's *mood*, same road, different day. This is the Thrill Dial observed rather than asked for. |
| **M1 conversion label** — 40% of planned routes fully ridden, 25% partly, 7% never | **The strongest preference label in the dataset.** Train on this. |
| **M2 repeats are COMMUTES** — repeated roads are *less* demanding (19.7° vs 20.4°) and *lower* (590 m vs 856 m) | ⚠️ **`docs/07_VALIDATION.md` ranks "Repeat" as the #2 label. That is wrong for this rider — demote it.** |
| **M5 bike effect = 6.3° of lean p95** across the same rider's 15 bikes (26.3–32.6) | Larger than any asymmetry effect. **Every skill estimate must control for `bikeId`.** |
| **Thrill Dial verified on real corners** — Cruise → Munich (566 m), Flow → Tauern (973 m), Send it → Dolomites (1,271 m) | One slider walks the recommendations 300 km south. The demo needs no caption. |
| **F19 rhythm works** — lag-1 autocorr of log radius 0.407 pooled, per-ride 0.16 / 0.37 / 0.48 | The "uniform sweepers vs technical" axis is real. |
| **F11 fatigue NOT confirmed**, **F09 temperature NOT significant**, **F80 tyre warm-up FAILED** (pressure *falls* 2.360 → 2.240 bar), **F83 canopy proxy FAILED** (but accuracy is worse in town than in the mountains → reframe as an **urban-canyon** detector, which maps to their inner-city red flag) | Drop or reframe. Say so plainly — the clean failure list is worth more than an inflated success list. |
| **F05b/M6 style index is WEAK** | At 1 Hz the in-corner minimum speed usually *is* the entry speed, so `brake_frac ≈ 0`. Only the exit-drive half works. Call it a "corner-exit drive index", not a point-and-shoot classifier. The variant inside `05_missing_features.py` is degenerate — **use the `06_cross_mapping.py` version**. |

### Known bugs to fix before anyone trains on this
1. **M1 has no time ordering** — a plan can be scored "ridden" by a ride that predates it. Fix before using it as a label.
2. **M1 home-adjacent cells inflate** every Munich-start route's coverage. Exclude a radius around home.
3. **M4 GPX Road DNA** — sparse shaping points produce implausible radii (one route shows req_p90 = 73°). Needs a minimum point-spacing filter.

### Useful facts discovered
- **Morton geometry**, decoded from BMW's own `tripViewer/app.js`: 32-digit base-4 quadkey on an
  equirectangular grid, cell side `360/2^L` degrees → **L=18 ≈ 153 × 102 m at latitude 48**.
- **BMW's own viewer already has a "Morton cells (avg)" mode and ABS/ASC badges** — so M3 and F75 are on
  their own shortlist, not exotic. Worth saying in the pitch; it reads as fluency in their stack.
- Manifest has 101 rides vs 100 ride CSVs; the README references 7 images but only 6 shipped.
- The 384 MB archive **is still truncated** — re-download remains the top blocker.

### Next action
Re-download the crowd archive. Then: fix the two M1 bugs, add `bikeId` as a control in the skill estimate,
and rehearse the 5-beat demo script in `docs/10_LIVE_DEMO.md`.

---

## Entry 3b — 2026-09-12 · the app, and two data corrections found while building it

The Streamlit demo is built and verified: `app/flowstate.py` (pure logic, has a self-check —
`python app/flowstate.py` prints the dial sweep and asserts the kernel and the safety gate) and
`app/streamlit_app.py` (four tabs). Run:
`streamlit run F:\bmw\app\streamlit_app.py --server.headless true --server.port 8502`.
It has an offline renderer that needs neither map tiles nor WebGL, and falls back automatically.

**Two data corrections, both verified independently — they override earlier entries:**

1. **27 of 100 rides have NO speed data at all.** `ridingvehiclespeed`, `positionmapmatchedspeed` and
   `positionrawspeed` are *all* flat zero on the same 27 rides — **131,970 points, 26% of the archive**.
   GPS position still moves and lean is still 100% present on those rides, so fall back to GPS-derived
   speed and **always report how many rides an aggregate actually used.** Entry 2 called
   `ridingvehiclespeed` "the cleanest speed channel" — that is wrong. Add it to the BMW question list.

2. **Use `positionrawheading`, not `positionmapmatchedheading`, for curvature.** Map-matched heading is
   quantised to road-segment bearings: **38% of moving samples read exactly zero yaw** (raw: 6%). Switching
   channels improves the physics bridge from corr **0.576 → 0.602** and moves the errors-in-variables slope
   from 0.92 to **1.08 — straddling the perfect 1.0.** A 5 s smooth pushes correlation to 0.663 but
   over-smooths (slope drifts to 1.375), so prefer raw unsmoothed for the headline claim.
   ⚠️ **`analysis/04_master_table.py` still uses map-matched heading — re-run it with raw to improve every
   downstream number**, including the corner-level 0.730 in `docs/08_DATA_FINDINGS.md`.

**On the asymmetry:** the app now shows four estimators side by side, with a cluster bootstrap on *ride*
(corner-level bootstrap is wrong — 5,253 corners sit inside 67 rides). Corner estimator +1.15°
[+0.09, +2.44]; per-ride +1.10° [+0.11, +2.10]; **BMW's own maxima −0.38° [−1.05, +0.29] — opposite sign.**
The app prints *"the estimators disagree on the sign; that is not an asymmetry, that is noise wearing a
confidence interval."* Keep that framing — it survives questioning in a way "not significant" would not.

---

## Entry 4 — 2026-09-12 · the truncated archive was salvaged; the asymmetry is dead

### The archive did not need re-downloading — 9,694 files (1.77 GB) were recovered from it
Full method in `docs/11_ARCHIVE_SALVAGE.md`, reproducible via `analysis/08_salvage_archive.py` (~30 s).
The trick: a truncated zip has no central directory, **but WinZip AES is AES-CTR — a stream cipher — so a
truncated prefix decrypts fine.** Inflate the outer streamed entry from byte 54, parse the 0x9901 AES extra
field (strength 3 = AES-256, 16-byte salt), PBKDF2-HMAC-SHA1(pw, salt, 1000, 66) — the 2-byte verifier
matched `cd0f` before decrypting anything — then AES-CTR (little-endian counter from 1) + raw inflate, then
walk the local headers inflating each entry to its natural `eof`.

| Recovered | Files | vs documented | |
|---|---|---|---|
| `anonymizedDataLake/trips-samples-2` | **7,999** | 7,999 | ✅ **COMPLETE** — Munich/Alpine box, ~2.4 M points |
| `anonymizedDataLake/trips-samples-1` | 1,468 | 77,700 | ⚠️ 1.9% |
| `exampleUserC/recordedTrips` | **224** | 224 | ✅ **COMPLETE** |

All parse at the full 43-column schema. **`exampleUserB` and user C's `cloudRecordedTracks` manifest are
past the truncation point** — so user C has no `bikeId`, `isFavorite` or `leanAngleLeftMax`/`RightMax`.

### ⛔ The asymmetry feature is dead. Do not pitch it.
User C: **15,810 corners over 214 rides** (3× user A). L−R p95 = **−0.40°, cluster-bootstrap 95% CI
[−1.04, +0.26]** → not significant. **This is a precise null, not an underpowered one** — the interval is
±0.65°. Across both riders: ~21,000 corners, no effect above ~1°.

**Consequences — apply these:**
- `docs/02_CONCEPT.md` §4B and `docs/06_PITCH.md` slide 2 build on the asymmetry reveal. **Replace that
  demo moment** with the crowd layer and the risk-ratio result.
- **F43 (loop direction by handedness) drops out of P1** — it has no measured basis.
- F01 is computable but *measured and rejected*. Reclassify.
- Keep it as a **method** and pitch that instead — the framing is written out in
  `docs/11_ARCHIVE_SALVAGE.md` §3 and is a stronger story than the feature was.

### ✅ F29–F33 unblocked
The whole "Usage of BMW Crowd Data" criterion is now buildable on 7,999 complete rides.
`analysis/10_crowd_layer.py` (crowd grid, gems, hazards) was in progress at the end of this entry —
check `analysis/out/crowd_grid.parquet`, `crowd_gems.csv`, `crowd_hazards.csv`.

### Next action
Rework the pitch's demo moment #2 around the crowd layer, and re-run `analysis/04_master_table.py` with
`positionrawheading` (entry 3b) so every downstream number improves.

---

## Entry 5 — 2026-09-12 · the crowd layer is live, and it confirms the core finding

`analysis/10_crowd_layer.py` processed the salvaged **7,999 complete `trips-samples-2` rides**.
Full write-up: `docs/12_CROWD_LAYER.md`.

**26,987 cells · 478,668 ride-traversals · 2,721,275 trackpoints · 174,733 corners · 1,243 ABS events.**
Coverage: 21,952 cells with 2+ rides, 16,254 with 5+, 6,734 with 20+, **836 with 100+**.
**F29–F33 are all live.** Outputs: `crowd_grid.parquet`, `crowd_gems.csv`, `crowd_hazards_corrected.csv`.

### 🎯 Second, independent confirmation of the risk link
Free-flowing cells **with** a hard-braking event demand **13.3°** (n=311) vs **12.5°** without (n=6,601),
**Mann-Whitney p = 4.9e-3**. The rider-level result (3.6×, 13 events, p=0.071) now has a crowd-level
companion at a different unit of analysis, two orders of magnitude better on p. Effect is modest (+0.8°) —
say so. Pitch the pair together; see `docs/12_CROWD_LAYER.md` §4 for the wording.

### ⚠️ Hazard-layer bug — found and fixed, keep the story
The first ABS-per-traversal ranking returned cells at **26 km/h with 0.10 stop rate and 8.4° demand** —
junctions with queues, not dangerous corners. A naive hazard map just rediscovers traffic lights. Fixed by
restricting to free-flowing cornering cells (≥5 rides, crowd speed >40 km/h, stop_rate <0.15, ≥5 corners)
→ 6,912 candidates, 311 with events, written to `crowd_hazards_corrected.csv`. **Use the corrected file.**
Tell the story in the walk-through — catching your own bug scores better than hiding it.

### Gems found without being told anything
Top cells cluster on Tegernsee/Schliersee, Kesselberg/Walchensee and the Ammergau — real Bavarian
motorcycling roads, located from lean angle and flow alone.

### Limits to respect
Crowd `trip_id` is a fresh UUID per snippet and is **not linkable to a rider**, so the lake gives road-level
demand/flow/hazard only — rider-level `z` stays with the example users. Lake timestamps are shifted (no
weather, no time-of-day). Everything here is **Bavaria only** until `trips-samples-1` is re-downloaded.

### Still outstanding
Waiting on the user for the cloud-share URL to re-download the full archive: `exampleUserB` (73 rides),
user C's manifest (`bikeId`/`isFavorite`/`leanAngleLeftMax`), and the other 98% of `trips-samples-1`.

---

## Entry 6 — (next session: copy this heading, fill it in, append below)

- **Date / session:**
- **What I did:**
- **Decisions made:**
- **What broke / what I learned about the data:**
- **State of the code:**
- **Next action:**
