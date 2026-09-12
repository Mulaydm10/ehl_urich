# 10 — THE LIVE DEMO

**Rewritten 2026-09-13, beat-by-beat against `app/route_tab.py` as it actually exists.**
The previous version scripted five beats — a greyed-out dial option, per-kilometre traffic-light
counts, counter-clockwise loop routing, time-aware weather and a Skill Quest — **none of which are
features**. Doc 18 has the audit. Everything below is a click that works.

BMW said it twice: *"Explainability + live demo will score bonus points"* and *"Final pitch: demo +
algorithm walk-through."*

> **The governing idea: answer their two questions, on their data, with the network unplugged —
> and let the app admit its own limits out loud.** Every other team will show a route on a map.
> We show the route, the reason in sentences, the roads we refused, and the case where our own
> dial does nothing.

---

## 1. THE SETUP — non-negotiable

1. **`./run_demo.sh` from `flowstate/`.** It binds the Tailscale address only. Never
   `--server.address=0.0.0.0` (this Mac holds a routable public address on the conference network —
   Streamlit will happily publish an NDA app), never `tailscale funnel`.
2. **Phone opens `http://100.80.210.100:8501`.** Conference Wi-Fi usually isolates clients, so the
   fallback is the phone's own hotspot with the Mac joined to it. Rehearse both.
3. **The Mac's Wi-Fi goes off before the demo.** Everything renders from `data/cache/demo.pkl`
   (5.2 MB) and a 17,345-way local road basemap. There is no tile server, no CDN, no API.
   *Test this literally, not theoretically.*
4. **Record a 3-minute screen capture** of a perfect run. If anything breaks, cut to the video
   without apologising and keep talking.
5. **Whoever pitches does not drive the phone.**
6. **Stay inside the coverage box** (47.38–48.03 N, 10.72–11.96 E). Outside it the app returns a
   refusal sentence, which is correct behaviour and still a bad thirty seconds on stage.

---

## 2. THE APP — five tabs, and which one is the demo

**`🛣 ROUTE` is the demo.** It is first for that reason. It talks only to `app/service.py`;
init is 12 ms, a route 60 ms, a loop ~150 ms.

| Tab | What it is | Status |
|---|---|---|
| **🛣 ROUTE** | both BMW use cases: A→B on the crowd graph, and a loop for X hours. Rider picker, Thrill Dial, refusal pins, `explain()` sentences. | **the demo** |
| 🎬 RIDE REPLAY | a real ride plays back with a moving dot on the flow curve, over bands labelled BOREDOM · FLOW · RISK | second act |
| 🧬 RIDER DNA | lean histograms, radar, headline numbers — **with "not significant" printed on screen where it is** | second act |
| 🎚 THRILL DIAL | re-scores 5,253 real corners on every change; watch the selection centroid walk from **47.16°N at Cruise to 46.88°N at Send it** — geography is nowhere in the model | second act |
| 🗺 ROAD GRID | one rider's own 1,090 Morton cells, Road DNA with no OpenStreetMap at all | second act |

Worth saying once if there is room: BMW's own `tripViewer/app.js` already has a *"Morton cells
(avg)"* mode and ABS badges. **We are not showing them something exotic — we are showing them the
thing they already built a viewer for, with a rider model on top of it.**

---

## 3. THE SCRIPT — five beats, four taps, ~3 minutes

Open on the ROUTE tab with rider **`userA`** selected and mode **A → B**.
**Every number below was read off the running service on 2026-09-13, not off a doc.**

### Beat 1 — both dials at once (40 s)
**Tap:** preset **`Lenggries → Bad Tölz`** (first button; its own caption says *"the strongest dial
effect measured"*).
**On screen:** one map — Cruise steel blue, Send it gold — the headline `compare()` writes itself:

> Same two points. 1.13x the distance, 83% of it on different roads, +2.7 deg more lean asked of you.

Metrics below it: **Cruise 47 km / 7.0° mean lean · Send it 53 km / 9.7° · Shared road 17%.**

> *"Same two points, same rider. Not 'we ride you further' — it's thirteen per cent longer.
> **Eighty-three per cent of the road is different, and it asks nearly three degrees more lean.**
> The dial chooses character, not mileage — and here it doesn't even cost you the day: forty
> minutes against forty-three.*
>
> *We draw both at once on purpose. We are not going to make a judge drag a slider and hope."*

### Beat 2 — why this road (30 s)
**Tap:** nothing — scroll past the second map to **Why this road**. Read the app's own sentences:

```
53 km, about 40 minutes.
This road asks a mean 9.7 deg of lean and peaks at 22.4 deg. Your gate is 22.6 deg,
which is 2 sigma above the road you habitually ride.
Best five kilometres score 0.57 out of 1 for fit at this dial setting.
Cornering asks about 33% of the tyre's grip here, against the 53% you have already
used on your own rides.
Nothing on this route crosses your safety gate.
```

> *"Every answer comes with sentences, not a score. And the last line matters: nothing here crosses
> the gate. Watch what happens when something does."*

**Do not promise red pins on this beat — this pair has none.** That is the setup for beat 3.

### Beat 3 — the dial can't move this road; the rider can (50 s) — **the beat that lands**
**Tap:** preset **`Kochel → Tegernsee`**.
**On screen, immediately:** overlap 85%, so the app's honest caption fires by itself —
*"On this pair the dial barely moves the road, and the app says so rather than dressing it up."*
Three red pins appear, each labelled *"REFUSED — the crowd leans 27° here, past your gate of 23°."*

> *"Different pair. And here our own dial does almost nothing — fifteen per cent of the road
> changes, the lean demand goes **down** two tenths of a degree. The app tells you that itself; we
> didn't hide it behind a cherry-picked coordinate.*
>
> *Now the red pins: three roads next to this route that we **deleted from the graph** — not made
> expensive. A safety gate you can buy past with a big enough detour budget is not a gate."*

**Tap:** scroll up → **Rider profile → `bike_4e1a9d64`**, dial on **Send it**.
The gold line redraws onto different roads.

> *"Same two points, same dial, different rider — the same human on a different motorcycle, because
> there is one rider in this lake and we are not going to invent a second one. At Cruise these two
> profiles share seventy-three per cent of their road. **At Send it they share ten per cent.**
>
> *The dial couldn't move this route. The rider moved almost all of it. That is what 'personal
> rider data' is supposed to mean."*

Open the **`This rider · skill · gate`** expander if a judge leans in: skill, σ, gate, hardest road
ever ridden, and **gate agreement 1.063×** — a threshold derived from the *spread* of their choices,
landing within 6% of their hardest road.

### Beat 4 — the second use case (30 s)
**Tap:** mode **`Loop for X hours`** → **`Kochel am See`** → **`2 h`**.
**On screen:** a closed loop, **133 km · 119 min (99% of budget) · road ridden only once 94%**.

> *"Your second question: a loop from where I'm standing, for the next two hours. A hundred and
> thirty-three kilometres, back at the start, a hundred and nineteen minutes against the hundred
> and twenty I asked for — and ninety-four per cent of it is ridden exactly once, so it's a loop,
> not an out-and-back.*
>
> *The timing is the crowd's own median speed on those cells, not an assumed average. Choosing a
> best closed tour under a time budget is NP-hard; this is a heuristic and the app says so."*

### Beat 5 — say the limitation before they find it (25 s)
**Tap:** nothing. Speak over the loop.

> *"One honest thing to end on. Across two hundred random point pairs, the median gain from our
> dial is zero — you saw that live two minutes ago. The reason is worth ten seconds: our graph is
> built from ride traces, so it's a bundle of corridors, not a road network. Riders take the same
> roads, so the branch you'd detour onto was never ridden and doesn't exist. Real topology
> underneath the crowd scoring is the first thing we'd build next — and it's the one thing your
> full lake fixes for free."*

### Close (10 s)
> *"Everything you just saw came off the bike. We never asked the rider a single question — and
> none of it left this machine."*

---

## 4. THE SECOND ACT — the result to have loaded, not to lead with

If the walk-through happens, this is the deepest thing we have. **It belongs on slide 7 of the
pitch, framed as a limitation we volunteered.** Hard-braking rate by how far a corner sits above
the rider's own skill, in units of their lean σ:

| z (corner demand above rider skill) | corners | hard-braking rate |
|---|---|---|
| below −1 σ | 3,110 | 0.23% |
| −1 → 0 | 1,151 | 0.17% |
| 0 → 0.5 | 343 | 0.29% |
| **0.5 → 1** | 269 | **0.74%** |
| **1 → 2** | 265 | **0.75%** |
| **above 2 σ** | 115 | **0.87%** |

Monotonic across all six bands, **3.6×** between "over their head" and "at or below their level".

> *"Fisher gives p = 0.071. Bootstrapped over rides rather than corners — corners inside one ride
> are not independent — the 95% interval on that 3.6× is [0, 17.1]. There are thirteen events in
> the whole sample. **We are not claiming significance.** We are claiming a monotonic trend in the
> predicted direction across six bands, and your crowd lake carries roughly ten thousand of these
> events, which is the first thing we would check with it."*

Two supporting numbers to have ready:
- **The continuous version:** a logistic over all 5,253 corners gives **odds × 1.28 per 1 σ** above
  skill. Same direction, no threshold.
- **What would settle it:** 50 events ≈ 330 rides (±28% on the ratio), 200 ≈ 1,300 rides (±14%),
  1,000 ≈ 6,700 rides (±6%). The crowd lake is 77,700 rides.

**And the crowd-scale version, which is not underpowered at all:** cells where the crowd brakes
hard demand **13.3° vs 12.5°**, p = 4.9e-3 over 6,912 cells.

One caution, stated in the room before a judge finds it: **ABS is orthogonal to cornering demand**
(ρ = +0.05 vs `demand_p90`). Never say "hard corners are where the ABS fires" — the honest and more
interesting line is that the hazard layer measures something *independent* of the fun layer, which
is why one model can carry both criteria without circularity.

---

## 5. WHAT WAS CUT FROM THIS DOCUMENT, AND WHY

So nobody reinstates it from memory at 11:00 on Sunday:

| Cut | Why |
|---|---|
| the Grossglockner "the model flagged it before the ABS fired" beat | it is one corner out of thirteen events, and it sits outside the crowd coverage box — the router cannot route there. Keep it as an anecdote in the walk-through if asked; never as a beat. |
| "one slider walks the recommendation 300 km south into the Dolomites" | never re-derived. The measured version is the centroid moving 47.16°N → 46.88°N, which the DIAL tab prints itself. |
| counter-clockwise loops / the asymmetry payoff | left/right asymmetry was tested and **rejected**. Loop direction is not a feature. |
| time-aware weather | dropped: cold-grip did not replicate (ρ = −0.016), and Sunday is dry across Europe anyway. |
| Skill Quests, "drop a ride get a rider", judges' phones driving the dial | not built. The UI is frozen; the product is a native app. |
| "65% of planned routes were ridden" as a demo beat | it is a labelling fact (89 GPX routes, 65% positives at 60%+ coverage, 7% hard negatives), good for the walk-through, invisible on screen. |

---

## 6. WHAT THE DEMO PROVES, criterion by criterion

| BMW criterion | What on screen answers it |
|---|---|
| **Fun Score** | the flow curve, and a route coloured segment-by-segment by fit to *this* rider |
| **Rider Safety** | the same curve's right shoulder — the gate, drawn as deleted roads with reasons, plus the 3.6× trend and its honest interval |
| **Personal Rider Data** | change the rider, watch 90% of the road change; skill, σ and gate derived from telemetry alone |
| **BMW Crowd Data** | 26,987 cells from 7,976 rides and 2.72 M points — every lean angle in the score is somebody's real ride |
| **External Sources** | OpenStreetMap: posted limits, road class, surface. 52% of cells with a known limit are ridden above it; we re-price them at the legal speed before scoring |
| **Scalability & Efficiency** | 12 ms cold start, 60 ms route, 150 ms loop, off a 5.2 MB file, network unplugged |
| **Explainability** | `explain()` prints sentences, not numbers — and the refusal list says which roads we would not send you down and why |
