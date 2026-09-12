# 06 — THE PITCH

**Rewritten 2026-09-13 from `docs/18_PITCH_AUDIT.md`.** The previous version was written
before the data was analysed; six of its claims were later measured and disproved and all five
demo beats described an app that does not exist. Everything below is either measured and cited
to a doc, or labelled as roadmap out loud.

They asked for two things at the end: a **demo** and an **algorithm walk-through**, and they said
**explainability and a live demo score bonus points**. So: pitch first, walk-through ready as a second act.

> **Never say on stage:** a 1.5–1.8× detour, any ablation weight, a leave-one-rider-out result,
> the left/right asymmetry, or the "three trip ids" forensics card. Each is disproved, impossible,
> or unverified — see doc 18 §"The one thing not to do". The three-trip-ids card is deliberately
> absent even from the failures slide: the other three failures are about *our* model and carry the
> same credibility, without volunteering that we were once wrong about *their* data.

---

## The spine (assume 5 minutes; cut from the bottom if it is 3)

### Slide 0 — the hook, spoken before any slide is read

> *"Ask a navigation app for the best route and it gives you the fastest one. Ask ten motorcyclists what
> the best route is and you get ten answers — because the same mountain pass is the best day of the year
> for one of them and the most frightening hour of their life for another.*
>
> ***Fun is not a property of the road. It's a property of the fit between the road and the rider.***
> *That is the only idea in this pitch. Everything else is us taking it seriously."*

### Slide 1 — the problem, stated as their own brief
Their green flags and red flags, on screen. Then the turn:
> *"Every one of these is a property of the road. Not one of them is a property of the rider. Optimise
> these and you build a very good road-ranking engine — and you hand a Black-grade pass to somebody who
> has never leaned past twenty degrees."*

### Slide 2 — **the safety gate lands on the hardest road this rider ever chose**
*(This replaces the old Rider DNA / asymmetry slide, which was tested and rejected. It is the
strongest number the project produced.)*

We never ask the rider anything. We take the roads they have ridden, read the demand the crowd
records on those same roads, and define `skill` as the median and `σ` as the spread. The safety
gate is then just `skill + 2σ` — a number derived entirely from the **spread** of their road
choices, with no knowledge of what their hardest road was.

| grid | gate = skill + 2σ | hardest road they actually rode | agreement |
|---|---|---|---|
| 18-char cells | 27.29° | 26.62° | **1.025×** |
| 16-char cells | 23.01° | 23.18° | **0.992×** |
| after re-pricing at posted limits | 22.59° | — | **1.063×** |

> *"Nothing in that construction forces this. We derived a safety threshold from how varied their
> road choices are, and it landed within three per cent of the hardest road they have ever chosen —
> at two different cell sizes, and again after we re-priced every road at its legal speed limit.
> That is the moment we started believing our own model."*

(Docs 14 §gate, 15 §"what it did to the router".)

### Slide 3 — Road DNA
The same map three times: coloured by curvature, by demanded lean, by our flow score.
> *"For every patch of road we compute what it demands — corner radius from yaw rate, the lean angle
> that radius requires at the speed the crowd actually rides it, the **posted** limit, the road class,
> the surface, and how often the crowd gets through the cell without stopping."*

**Say what is not in there, unprompted:** gradient is a BMW green flag and we do not score it,
because 46–51% of the elevation in the lake is exactly zero. Sight distance was never built.
Both are roadmap, and the honest version of that sentence buys more than the feature would.
(Doc 15, `research/FINDINGS.md`.)

### Slide 4 — **the flow curve. The single most important image in the deck.**
The Gaussian, rider skill marked, the road's challenge distribution, the shaded flow band, and both
shoulders labelled **BOREDOM** and **RISK**.
> *"Flow theory says you are in flow when the challenge is slightly above your skill. Below it you are
> bored. Far above it you are anxious — and on a motorcycle, anxiety is not a mood, it's the thing that
> happens right before a crash.*
>
> ***We did not add a safety penalty to our fun score. Safety is the right-hand side of the same curve.
> One model, both of your criteria — because the road that is too hard for you is exactly the road that
> stops being fun.***"

`z = (challenge − skill)/σ`, `flow = exp(−(z − z*)²/2τ²)`, τ = 0.5. The Thrill Dial is `z*`:
Cruise 0.15, Flow 0.50, Send it 0.90. The router optimises this literally — it is the edge weight.

### Slide 5 — **LIVE DEMO** (see the demo script below)

### Slide 6 — the source ledger (their literal deliverable #2)
One table: every source and **what it contributes**, stated — not weighted.

| Source | What it contributes | Measured |
|---|---|---|
| BMW crowd lake | 26,987 road cells from 7,976 rides, 2.72 M points: speed p50/p85, lean p50/p90, flow index, stop rate | `demand_p90` vs crowd lean p90 **r = 0.892** over the 4,558 cells with ≥20 rides |
| BMW personal telemetry | skill, σ, the gate, grip envelope — per rider **and per bike** | 20 distinct bikes over 101 rides; across the 15 with enough corners to measure, lean p95 spreads 6.3° |
| OpenStreetMap | posted limit, road class, surface — the things telemetry physically cannot see | 63% of cells matched within 80 m, median snap 6 m |
| Physics | required lean = arctan(v²/Rg) | **not weighted at all** — it is an identity |

> *"You asked how we weight and combine our sources. Here is the honest answer: the physics terms
> are not weighted, they are an identity. The safety gate is a hard constraint, not a weight. There
> is exactly one tunable number in the whole router — λ, the price of a dull kilometre — and we can
> show you that above λ≈10 it stops changing the answer at all. **We did not run an ablation, so we
> are not going to show you an ablation table.** With one rider in the lake it would measure our
> own arithmetic."*

### Slide 7 — **what we tested, and what failed**
> *"You said: you define fun, we evaluate. So we evaluated it ourselves first — and we are going to
> lead with the things that did not work."*

- **Left/right asymmetry: rejected.** It was our best story. Bootstrapped over rides rather than
  corners — corners inside one ride are not independent — the effect is under 1° and the sign flips
  by estimator. The code still ships, gated on a CI that clears zero. It never fires.
- **Cold-tarmac grip: did not replicate.** spearman(lean, temperature) = **−0.016** over 5,253
  corners. Physics says cold tarmac has less grip; our 29 trips cannot resolve it. It ships as a
  labelled assumption feeding the safety readout only, and never the fun score.
- **Our own detour target was unachievable.** We set out to make Send It a substantially longer
  ride. The maximum detour available anywhere in this network is **1.137×**, for a reason worth
  hearing: a graph built from ride traces is a bundle of corridors, not a road network. Riders take the
  same roads; the branch you would detour onto was never ridden, so it does not exist.

**And the one that did survive, stated with its interval:** hard-braking rate rises monotonically
across all six bands of "how far above this rider's skill the corner sits" — 0.23% below −1σ to
0.87% above +2σ, a **3.6× ratio**. *"Fisher gives p = 0.071. Thirteen events. Bootstrapped over
rides, the 95% interval is [0, 17.1]. **We are not claiming significance.** We are claiming a
monotonic trend in the predicted direction across six bands — and your crowd lake carries roughly
ten thousand of these events, which is the first thing we would check with it."* (Doc 12.)

### Slide 8 — it is a product, and it lives in ConnectedRide
Before / During / After.
> *"You told us ConnectedRide owns before, during and after every ride. **Before**, we show the grade
> of the road before they commit to it, and we refuse the ones above their gate. **During**, we route
> them into their flow band rather than around the clock. **After**, their own telemetry updates
> skill and σ — the gate moves because they moved it, not because we asked them a question."*

### Slide 9 — scale, in four sentences
> *"Everything you just saw ran off a 5.2 MB precomputed file. Cold start is **12 ms**, a full A→B
> route is **60 ms**, moving the dial is **20–37 ms**, and a three-hour loop search is **150 ms** —
> on a Mac mini, with the network cable out. Rebuilding the entire 26,987-cell road layer from
> 2.72 million raw trackpoints takes 13.8 seconds, and the graph on top of it 8.7 seconds.
> Nothing here is a research prototype waiting for a cluster: it is a lookup and a Dijkstra."*

### Slide 10 — close
> *"Your tagline is 'find your thrill'. Not 'find the thrill' — **your** thrill. We built the engine that
> takes the word 'your' literally."*

---

## The live demo script — 3 minutes, rehearsed to the word

Pre-baked, network unplugged, served from the Mac and shown on a phone over Tailscale.
**Every beat below is a thing `app/route_tab.py` actually does.** Full click-path in `docs/10_LIVE_DEMO.md`.

**Beat 1 — both dials at once, on one map (40 s).** ROUTE tab → *Lenggries → Bad Tölz*.
Cruise steel blue, Send it gold, drawn together. The app writes its own headline.
> *"Same two points, same rider. Not 'we ride you further' — it's thirteen per cent longer.
> **Eighty-three per cent of the road is different, and it asks nearly three degrees more lean.**
> The dial chooses character, not mileage — and here it doesn't even cost you the day: forty
> minutes against forty-three. We show both at once on purpose, because we are not going to make a
> judge drag a slider and hope."*

**Beat 2 — why this road (30 s).** Scroll to *Why this road*.
> *"Every answer comes with sentences, not a score: this road asks a mean 9.7 degrees of lean and
> peaks at 22.4; your gate is 22.6. Cornering asks a third of the tyre's grip, against the half
> you've already used on your own rides. And the last line — nothing here crosses your gate.
> Watch what happens when something does."*

**Beat 3 — the dial can't move this road; the rider can (50 s).** Preset *Kochel → Tegernsee*,
then switch rider `userA` → `bike_4e1a9d64` at Send it. **This is the beat that lands.**
> *"Here our own dial does almost nothing — fifteen per cent of the road changes and the lean
> demand goes down. The app says so itself, in a caption we wrote for exactly this case. And those
> three red pins are roads we **deleted from the graph**, not made expensive — a gate you can buy
> past with a big enough detour budget is not a gate.*
>
> *Now change the rider. Same two points, same dial. At Cruise these two profiles share
> seventy-three per cent of their road. **At Send it they share ten.** The dial couldn't move this
> route; the rider moved almost all of it."*

**Beat 4 — the second use case (30 s).** Mode *Loop for X hours* → Kochel, 2 h.
> *"A loop from where I'm standing, for the next two hours: 133 kilometres, back at the start,
> **119 minutes against the 120 I asked for**, and ninety-four per cent of it ridden exactly once.
> That timing is the crowd's own median speed on those cells, not an assumed average."*

**Beat 5 — say the limitation before they find it (25 s).** No tap; speak over the loop.
> *"Across two hundred random point pairs the median gain from our dial is zero — you saw that
> live. Our graph is built from ride traces, so it's a bundle of corridors, not a road network:
> the branch you'd detour onto was never ridden, so it doesn't exist. Real topology under the crowd
> scoring is the first thing we'd build next, and your full lake fixes it for free."*

**Close (10 s).**
> *"Everything you just saw came off the bike. We never asked the rider a single question."*

---

## The algorithm walk-through (second act, be ready with the notebook)

In order: one cell of the road layer with its real numbers → the physics bridge (required lean vs
measured lean, **r = 0.765** over 5,253 real road corners; keep the 494 low-speed manoeuvres in and
it is 0.730 with an errors-in-variables slope of 1.08) → this rider's skill and σ read off the same
column the challenge comes from → the flow kernel → the Dijkstra weight `L·(1 + λ(1−flow))` with
the gate as a deleted edge → the refusal list. Show a road they can name with real degrees on it.

**The one consistency rule:** quote **5,253 corners at r = 0.765** everywhere. The 5,747 table
includes low-speed manoeuvres; say that if asked, and say the filter is a definition rather than a
search for a better number.

---

## Q&A — the questions that are coming

**"Why a Gaussian? Why not just a threshold?"**
> Because both tails are real and they are different failures. Below the band is boredom, above it is
> risk. A threshold models one and ignores the other. The Gaussian also gives the user one knob
> instead of two, and τ has a physical meaning — the rider's own consistency, which we measure.

**"Where do the weights come from?"**
> Three places and we will name which is which. The physics is unweighted — required lean is
> arctan(v²/Rg). The gate is a hard constraint. There is one tunable, λ, and it saturates: λ = 3, 6,
> 10, 20, 40, 80 return the byte-identical route. We did not run an ablation and we are not going to
> show you one we did not run.

**"Your sample is tiny."**
> It is: one rider in the personal lake, across twenty bikes. That is why slide 7 is the failures
> slide, and why we bootstrap over rides rather than corners. The crowd half is not tiny — 7,976
> rides, 2.72 million points — and the architecture takes another rider without a retrain: skill and
> σ are two numbers read off the same column the road is scored on.

**"Aren't you encouraging people to ride dangerously?"**
> The opposite, and we can show it as a line of code rather than a promise. We never score speed and
> never reward a time. When OpenStreetMap knows the posted limit we found that on **52% of those
> cells the crowd habitually rides above it** — median 1.11×. So we re-price those roads at the
> posted speed before scoring: demand on them drops from 9.67° to 5.60°. The crowd's enthusiasm is
> not silently inherited. And we refuse outright — delete from the graph — any road demanding more
> than skill + 2σ.

**"What about a rider who has never ridden with you?"**
> Road DNA needs zero rider data. Rider DNA starts as a prior by bike family — and we can show you
> that matters: the same human's lean p95 spreads **6.3° across the fifteen of his bikes we can measure**, which is larger
> than any rider effect we tested. You already know which bike they bought. Cold start is a designed
> path, not an apology.

**"How is this different from a scenic route option?"**
> A scenic route is the same for everybody. Ours is different for every rider — measurably: same two
> points, same dial, two riders, 10% shared road.

**"Could you just use an LLM for this?"**
> For the conversation, yes. Not for the scoring — we would lose the per-segment reason, and the
> interesting part is not the language. It is that lean angle makes road difficulty and rider skill
> the same measurement.

**"What would you build next, with our data?"**
> Two things, in order. Real road topology from OpenStreetMap underneath the crowd scoring — our
> graph is built from ride traces, so it is a bundle of corridors and the dial has nothing to detour
> onto. And gradient, which is one of your own green flags and which we refuse to score today
> because half the elevation in the lake is zero.

---

## Delivery notes

- **One sentence, said three times.** Open with it, repeat it on the flow curve, close with it.
- **Lead with a failure on slide 7.** Engineers trust the team that shows the wide interval.
- **Say what is live and what is roadmap**, unprompted, once.
- **Name a real road out loud** — Lenggries, Kochel, Tegernsee. Local specificity reads as real work.
- Whoever pitches should not be the one driving the laptop.
- Coverage is Bavaria only (47.38–48.03 N, 10.72–11.96 E). Never click outside it live; the app
  refuses with a sentence, which is correct behaviour and still a bad thirty seconds.
- If the demo breaks: cut to the recorded video without apologising, keep talking, fix nothing live.
