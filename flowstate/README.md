# FLOWSTATE — BMW Motorrad Route Challenge

**TUM.AI Hackathon Zürich 2026 · 12–13 September 2026 · BMW Motorrad "FIND YOUR THRILL"**

> **The one sentence the whole project rests on:**
> **Fun is not a property of a road. Fun is a property of the *fit* between a road and a rider — and the
> same number that measures the fit also measures the risk.**

---

## If you are a new agent or a new teammate, read this page, then `docs/02_CONCEPT.md`. Nothing else is required to start.

## The concept in ninety seconds

Everyone else at this hackathon will build `fun = w1·curvature + w2·elevation + w3·scenery − w4·traffic`
and put it on a map. That scores a **road**. It cannot be personalized, its weights are indefensible, and
it hands a Black-grade alpine pass to a rider who has never leaned past 20°.

We score the **match** instead, and we do it in a physical unit both sides share — **degrees of lean angle**:

- A corner of radius `R` at speed `v` **demands** `theta = arctan(v² / (R·g))`. That is **Road DNA**.
- A rider's telemetry shows the lean they **actually use**, separately for left and right corners, by
  gradient, by surface, wet and dry. That is **Rider DNA**.
- Difficulty minus skill is now a number in degrees. Feed it through a flow kernel:

```
z    = (challenge − skill) / sigma_rider
flow = exp( −(z − z*)² / (2·tau²) )
```

`z* > 0` is the **Thrill Dial** — flow theory says people are in flow when the challenge sits *slightly
above* their skill, not equal to it. Below the band: boredom. Far above it: anxiety, which on a motorcycle
is the state immediately preceding a crash.

**Which means one curve scores both of BMW's separate criteria — Fun Score *and* Rider Safety.** No other
team will unify those two; they will all bolt a safety filter onto the end of a fun score. That unification
is the pitch.

## The five things that win it

1. ~~**Left/right lean asymmetry → loop direction.**~~ ⛔ **TESTED AND REJECTED.** Across two riders and
   **~21,000 corners** the effect is under 1° with the interval straddling zero (user C: −0.40°, CI
   [−1.04, +0.26] over 214 rides). **Do not pitch it.** Pitch the *method* instead — we tested our own
   idea, bootstrapped over rides, and dropped it. See `docs/11_ARCHIVE_SALVAGE.md` §3 for the exact wording;
   it demonstrates *"you define fun, we evaluate"* better than the feature would have.
2. **One curve for fun and safety** (above).
3. **Time-aware weather.** We know *when* the rider reaches each segment, so we cost the forecast at
   arrival time and flip the loop direction to beat the shower — rather than overlaying the current radar.
4. **Skill Quests.** Name the rider's weakest axis, prescribe the exact road that trains it, then verify
   from their next ride's telemetry. *Prescribe → ride → measure → re-grade.* This is the "after the ride"
   third of ConnectedRide that everyone forgets.
5. **We validate our own fun score** (leave-one-rider-out, clustered on rider, plus an ablation table).
   BMW said *"you define fun, we evaluate"*. Evaluating it first is the single cheapest way to be the most
   credible team in the room.

## The document set

| File | What is in it |
|---|---|
| [`docs/01_BRIEF.md`](docs/01_BRIEF.md) | Both BMW decks, fully extracted, plus what the brief is really asking for and the hard constraints (speed is a brand landmine, GDPR, NDA, Alpine pass closures) |
| [`docs/02_CONCEPT.md`](docs/02_CONCEPT.md) | **The winning idea in full** — the thesis, the formula, the three claims, the five demo moments, and what the rest of the room will build |
| [`docs/03_ARCHITECTURE.md`](docs/03_ARCHITECTURE.md) | Road DNA (24 features), Rider DNA (~40), the Flow Match maths, both routing algorithms, the time-aware external layer, and the scalability answer |
| [`docs/04_FEATURES.md`](docs/04_FEATURES.md) | **74 features**, each tagged with the judging criterion it buys, a priority and an hour estimate. The P0 spine is ~26 person-hours. |
| [`docs/05_BUILD_PLAN.md`](docs/05_BUILD_PLAN.md) | Hour-by-hour 24 h plan, stack, repo layout, function signatures, parallel tracks, failure fallbacks, and the six questions to ask BMW on site |
| [`docs/06_PITCH.md`](docs/06_PITCH.md) | The 10-slide spine, the word-for-word 3-minute demo script, and prepared answers to the eight questions that are coming |
| [`docs/07_VALIDATION.md`](docs/07_VALIDATION.md) | How to prove the fun score is real: revealed-preference labels, leave-one-rider-out, clustered standard errors, the ablation table |
| [`docs/08_DATA_FINDINGS.md`](docs/08_DATA_FINDINGS.md) | **What the real data says** — every feature tested on 508,183 real trackpoints: what works, what is dead, what the units really are, and nine features the data handed us |
| [`docs/09_DATA_MAP.md`](docs/09_DATA_MAP.md) | Every data asset, the corner-level **master table**, the full **mapping matrix** (M1–M6), and the complete feature verdict list |
| [`docs/10_LIVE_DEMO.md`](docs/10_LIVE_DEMO.md) | **The live demo** — the four tabs, the five-beat script, the Grossglockner moment, and the out-of-the-box ideas ranked by impact ÷ risk |
| [`docs/11_ARCHIVE_SALVAGE.md`](docs/11_ARCHIVE_SALVAGE.md) | How the truncated 384 MB archive was recovered (9,694 files), what came out, and the two-rider test that **killed the asymmetry feature** |
| [`docs/12_CROWD_LAYER.md`](docs/12_CROWD_LAYER.md) | **The crowd layer** — 26,987 cells from 7,999 rides, the gems, the hazard-layer bug and its fix, and the crowd-scale confirmation of the risk link |
| [`HANDOFF.md`](HANDOFF.md) | **Session log and current state — any continuing agent reads this first, and appends to it before stopping** |

## Status

**Concept, planning and a full data reality-check are complete. No product code written yet.**

`analysis/` holds three scripts that profile the real BMW data and test every planned feature against it.
**`docs/08_DATA_FINDINGS.md` is the result, and it overrides anything in docs 02–07 that it contradicts.**

- ✅ The core physics claim is **empirically confirmed** — corr **0.73** over **5,747 real corners**.
- ✅ **The risk side of the flow curve predicts real hard-braking events** — monotonic across all six z
  bands, **3.6× risk ratio**. Fun and safety are one model, measured. *But only 13 events: p = 0.071,
  bootstrap CI [0.0, 17.1] — present it as a trend, never as significance* (`docs/10_LIVE_DEMO.md` §1).
- ✅ **…and the crowd confirms it independently** — free-flowing cells with a hard-braking event demand
  **13.3°** vs **12.5°** without, **p = 4.9e-3** over 6,912 cells (`docs/12_CROWD_LAYER.md` §4). Two units
  of analysis, same mechanism.
- ✅ **Crowd layer live** — 26,987 cells, 478,668 traversals, 2.7 M points, 174,733 corners, 1,243 ABS
  events from the 7,999 salvaged rides. F29–F33 all unblocked.
- ⚠️ **Repeated roads are commutes, not favourites** for this rider — `docs/07_VALIDATION.md` ranks
  "Repeat" as the #2 preference label and is **wrong**; the planned-route conversion label replaces it.
- ⚠️ **The bike is worth 6.3° of lean p95** across the same rider's 15 machines — control for `bikeId`
  or you will read the motorcycle as the rider.
- ⚠️ The left/right asymmetry claim is **not confirmed** for user A; re-test on B and C before pitching it.
- ❌ Brake pressure and vertical/lateral acceleration are **dead channels** on this fleet; `ridingabsbraking == 3`
  replaces the first, and Road Pulse needs rebuilding on a different signal.
- ✅ **The truncated 384 MB archive was salvaged** — 9,694 files, 1.77 GB. `trips-samples-2` is **100%
  complete** (7,999 rides, Munich/Alpine box) and so is **user C** (224 rides). The crowd-data criterion is
  **unblocked**. Method in `docs/11_ARCHIVE_SALVAGE.md`.
- ⛔ **The asymmetry feature is tested and rejected** on two riders / ~21,000 corners. Pitch the method, not
  the feature. `exampleUserB` and user C's manifest are still past the truncation point.

## The immediate next three actions

1. **Re-download `exd_download (1).zip` (384 MB).** It is truncated. It contains the entire crowd data lake
   (85,699 rides / 29.1 M points) plus example users B and C. Six features and one judging criterion are
   blocked until it lands.
2. **Lock the demo region.** The data argues for BMW's own Munich/Alpine-foothills box (lat 47.452–47.946,
   lon 10.845–11.852) — it is where `trips-samples-2` lives and user A's routes run straight through it.
3. **Scaffold the repo** per `docs/05_BUILD_PLAN.md`, with `analysis/` as the head start it already is.
   Track C (the app) must build against a **mock** `road_dna.parquet` from hour one, so the UI is finished
   before the real numbers arrive. That single decision usually decides whether a team demos at all.

## Non-negotiables

- **The BMW data is under NDA.** Never commit it, never upload it to a hosted demo, an Artifact, or any
  third-party API. `data/raw/` stays local.
- **Never score speed or lap times.** Lean, smoothness, rhythm and flow — always within posted limits. A
  European OEM cannot ship a product that gamifies going fast on public roads, and the safer product is
  also the better one.
- **T−4h is a hard feature freeze**, and the demo runs from a pre-baked scenario file with the network
  unplugged. Test that literally.
