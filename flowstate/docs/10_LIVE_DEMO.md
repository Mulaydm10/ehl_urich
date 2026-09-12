# 10 — THE LIVE DEMO

BMW said it twice: *"Explainability + live demo will score bonus points"* and *"Final pitch: demo +
algorithm walk-through."* This document is the demo design, built entirely on numbers that are already
true of the real data (`docs/08_DATA_FINDINGS.md`, `docs/09_DATA_MAP.md`).

> **The governing idea: do not show a slideshow of a map. Show a ride.**
> Every other team will present a static route on a static map. We have five years of one rider's real
> telemetry at 1 Hz. That means we can put a **time axis** on the screen — and watch a real human being
> enter and leave flow state. Nobody else in that room will have a time axis at all.

---

## 1. THE MOMENT THE WHOLE PITCH IS BUILT AROUND

We tested whether the **right-hand shoulder of the flow curve — the "over your head" zone — predicts real
hard-braking / ABS events** in BMW's own telemetry. Hard-braking rate by how far the corner sits above the
rider's own skill (`z`, in units of their lean sd):

| z (corner demand above rider skill) | corners | hard-braking rate |
|---|---|---|
| below −1 σ | 3,110 | 0.23% |
| −1 → 0 | 1,151 | 0.17% |
| 0 → 0.5 | 343 | 0.29% |
| **0.5 → 1** | 269 | **0.74%** |
| **1 → 2** | 265 | **0.75%** |
| **above 2 σ** | 115 | **0.87%** |

**Monotonic across all six bands. Risk ratio 3.6× between "over their head" and "at or below their level".**

**Now the honest part, and say it out loud — it is worth more than the number:**

> *"Fisher exact gives p = 0.071. Bootstrapped over rides rather than corners — because one rider's
> corners are not independent — the 95% interval on that 3.6× is [0.0, 17.1]. There are thirteen events in
> the whole sample. **We are not claiming significance.** What we are claiming is a monotonic trend in the
> predicted direction across six bands, and that the crowd lake you were going to give us carries roughly
> ten thousand of these events — which is the first thing we would check with it."*

That paragraph does something no other pitch will do: it makes the fun model and the safety model the same
model, **and then refuses to overclaim it**. Engineers trust the team that shows them the wide interval.

**Two supporting numbers to have ready**, because they turn "your sample is tiny" from an attack into your
own slide:

- **The continuous version.** Fitting a logistic over all 5,253 corners instead of two buckets:
  **odds of a hard-braking event × 1.28 for every 1 σ the corner sits above the rider's skill.** Same
  direction, using every corner rather than a threshold.
- **What would settle it.** At this event rate:

  | events needed | ≈ rides | 95% CI on the 3.6× ratio |
  |---|---|---|
  | 50 | ~330 | ±28% |
  | 200 | ~1,300 | ±14% |
  | 1,000 | ~6,700 | ±6% |

  The crowd lake is **77,700 rides ≈ 10,000 events** — an order of magnitude past the bottom row.
  *"We can tell you exactly how much data it takes to settle this, and you already have twelve times it."*

### The specific ten seconds
Among the corners where the model said "above his level" *and* the bike actually braked hard:

```
47.0766, 12.7646   required lean 38°   z = +0.97   elevation 2,253 m   41 km/h
```

**That is on the Grossglockner High Alpine Road.** Put it on the screen, zoom in, and say:

> *"Two thousand two hundred and fifty three metres, on the Grossglockner. Our model — which only knows
> how this rider leans — flagged this corner as above his level before he got there. The bike's ABS fired
> in it. We did not go looking for this corner; it fell out of the model."*

---

## 2. THE APP — four tabs, one story

Being built as `app/streamlit_app.py` (logic in `app/flowstate.py`), running on the real data locally.

### Tab 1 — RIDE REPLAY *(the centrepiece)*
A real recorded BMW ride plays back. Three panels, synchronised on the same clock:
1. **Map** — the path drawn as it is ridden, coloured by this rider's flow score.
2. **Telemetry row** — speed, lean angle, throttle, gear, ABS state, live.
3. **The flow curve** — the Gaussian, with a **moving dot** showing where the rider is *right now*, over
   shaded bands labelled **BOREDOM · FLOW · RISK**.

The dot crossing into the red band as the bike enters a hairpin is the single most explanatory image in
the whole project. Pause there. That is the pitch.

### Tab 2 — RIDER DNA
Lean histogram split LEFT vs RIGHT with p95 marked, a per-dimension radar, and the headline numbers.
**With the confidence interval shown, and the words "not significant" printed on screen when it is not** —
which, for user A, it is. Building the honesty into the UI is itself a differentiator.

### Tab 3 — THRILL DIAL
One slider. Re-scores all 5,253 real corners instantly. Already verified on the data:

| Dial | best-matching corners land at |
|---|---|
| **Cruise** (z\*=0.15) | 48.14, 11.63 — **Munich**, 566 m |
| **Flow** (z\*=0.50) | 47.36, 13.36 — **Salzburg / Tauern**, 973 m |
| **Send it** (z\*=0.90) | 46.80, 12.68 — **the Dolomites**, 1,271 m |

> **One slider physically walks the recommendation 300 km south and 700 m up into the Alps.** No caption
> needed — the audience watches the dots migrate into the mountains.

### Tab 4 — ROAD GRID
The morton-cell road layer: **Road DNA with no OpenStreetMap at all**, built from ride telemetry alone.
1,090 cells, coloured by demand, with the hard-braking cells marked as hazards.

> Worth knowing before you present it: BMW's own `tripViewer/app.js` already has a *"Morton cells (avg)"*
> mode and ABS/ASC badges. We are not showing them something exotic — **we are showing them the thing they
> already built a viewer for, with a rider model on top of it.** Say that; it lands as fluency in their stack.

---

## 3. THE DEMO SCRIPT — five beats, ~3 minutes

| # | Beat | Say |
|---|---|---|
| 1 | **Replay** a real alpine ride, 20× | *"This is a real BMW test ride. Watch the dot on the curve — he is in flow here, bored on this straight, and here…"* |
| 2 | **Pause in the red zone** at the Grossglockner corner | *"…our model says this corner is above his level. Four seconds later the ABS fires. We did not go looking for this."* |
| 3 | **The dial** — drag Cruise → Send it | *"Same rider, same road network, one gesture — and the recommendations walk 300 km into the Alps."* |
| 4 | **The plan vs the ride** | *"Sixty-five per cent of the routes he planned, he went on to ride. He committed before he knew the weather — that is the strongest preference label in this dataset, and it is the one we train on."* |
| 5 | **The honest slide** | *"p = 0.071. Thirteen events. Here is the interval, and here is the data that would close it."* |

Beat 5 is deliberately last. Ending on a limitation you volunteered is the strongest possible close in
front of engineers.

---

## 4. OUT-OF-THE-BOX IDEAS, ranked by (impact ÷ risk)

### ✅ Build these

**A. The moving dot on the flow curve.** Already described. Cheap — one Plotly trace and an index. It is
the difference between explaining flow theory and *showing* it.

**B. "Drop a ride, get a rider."** A file-drop zone: a judge picks any of the 100 ride CSVs themselves, and
two seconds later the full Rider DNA card renders. **Let them choose the file.** Unfakeable, interactive,
and it proves the pipeline is general rather than tuned to one cherry-picked ride.

**C. Same rider, different bike, different route.** We measured a **6.3° spread in lean p95 for the same
rider across his 15 motorcycles** — bigger than any asymmetry effect in the data. So: *"Same rider. Same
road. He is on the GS today instead of the sport bike — and the route changes."* This is a BMW-specific
insight that requires the `bikeId` column **only BMW has**, and no other team will have noticed it.

**D. The aspiration list.** Six planned routes he has **never ridden** — including a 538 km one. Those are
not failures, they are the Skill Quest backlog, sitting in the data already labelled by the rider himself.
*"He told us what he wants to ride. He just hasn't ridden it yet."*

**E. The counterfactual on a real ride.** Take a ride he actually did, and show what FLOWSTATE would have
proposed from the same start point with the same time budget, with the flow delta. Shows the product
*acting*, not just measuring.

### ⚠️ High reward, real risk — only if ahead of schedule

**F. Judges drive the dial from their own phones.** Serve the app on the laptop's hotspot, put a QR code on
the slide. Three judges each setting their own thrill level on one shared map is a genuinely memorable
thirty seconds. **Risk:** conference networking, and the NDA — serve only derived aggregates, never raw
telemetry, and never to the public internet. Have the laptop-only fallback ready and rehearsed.

**G. A physical dial.** A rotary encoder or a phone gyro driving `z*`. Delightful, fragile, and a 90-minute
sink. Only if everything else is finished and rehearsed.

### ❌ Do not

- Any demo that needs live internet. Conference wifi fails; assume it will.
- Anything that displays a speed record, a lap time, or a leaderboard by pace. Off-brand and unshippable.
- A "3D flythrough" for its own sake. It photographs well and explains nothing; the flow curve explains
  everything.

---

## 5. THE RULES THAT KEEP THE DEMO ALIVE

1. **Pre-bake the scenario.** One ride, one rider profile, one grid — pickled to `data/cache/`. The app must
   open with the network cable physically unplugged. Test that literally, not theoretically.
2. **Record a 3-minute screen capture** of a perfect run. If anything breaks on stage, cut to the video
   without apologising and keep talking.
3. **Cap the replay at ~2,000 points per ride** or the animation stutters and the moment is lost.
4. **Whoever pitches does not drive the laptop.**
5. **Label every panel live or roadmap.** Judges punish fakery far harder than they reward extra features.
6. **NDA:** everything stays on the laptop. No hosted demo, no cloud notebook, no third-party API with
   telemetry in the payload.

---

## 6. WHAT THE DEMO PROVES, criterion by criterion

| BMW criterion | What on screen answers it |
|---|---|
| Fun Score | The flow curve, live, with a rider moving along it |
| Rider Safety | **The same curve** — plus the 3.6× hard-braking result and its honest interval |
| Personal Rider Data | Rider DNA built from 508,183 real trackpoints; "drop a ride, get a rider" |
| Crowd Data | The morton road grid — and the explicit statement that it scales to the 77,700-ride lake |
| External Sources | On-bike ambient temperature (real on 95% of rides) beating a weather API at its own job |
| Scalability & Efficiency | Re-scoring 5,253 corners instantly on a slider drag, from a precomputed table |
| Explainability | The "why this corner" panel, and the counterfactual on a rejected road |
