# 06 — THE PITCH

They asked for two things at the end: a **demo** and an **algorithm walk-through**, and they said
**explainability and a live demo score bonus points**. So: pitch first, walk-through ready as a second act.

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

### Slide 2 — Rider DNA (**show the real histogram**)
The left/right lean distribution of one real anonymized BMW test rider.
> *"We didn't ask this rider a single question. This is their bike talking. They are seven degrees stronger
> on left-handers than on rights — and almost every rider is asymmetric like this. Their navigation app has
> no idea."*

### Slide 3 — Road DNA
The same map three times: coloured by curvature, by demanded lean, by our flow score.
> *"For every 300 metres of road we compute what it demands — corner radius, the lean angle that radius
> requires at the pace people actually ride it, gradient, sight distance, surface, and how often the crowd
> gets through without stopping."*

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

### Slide 5 — **LIVE DEMO** (see the demo script below)

### Slide 6 — the data-source ledger (their literal deliverable #2)
One table: every source, what it contributes, its weight, and — critically — **its measured contribution
from the ablation**, not an asserted weight.
> *"You asked how we weight and combine our sources. We'd rather show you what each one is worth."*

### Slide 7 — validation
> *"You said: you define fun, we evaluate. So we evaluated it ourselves first."*
Leave-one-rider-out result, with the clustered confidence interval, and the honest limitation stated out
loud. (`07_VALIDATION.md`.)

### Slide 8 — it is a product, and it lives in ConnectedRide
Before / During / After, with the Skill Quest loop on the right.
> *"You told us ConnectedRide owns before, during and after every ride. Before, we show the grade of the
> road before they commit to it. During, we route them into flow and around the rain. After, we tell them
> which corner direction is holding them back and exactly which road will fix it — and then we check, from
> their own telemetry, whether it did."*

### Slide 9 — scale, in four sentences
The four sentences from `03_ARCHITECTURE.md` §8. Do not improvise this; it is a graded criterion.

### Slide 10 — close
> *"Your tagline is 'find your thrill'. Not 'find the thrill' — **your** thrill. We built the engine that
> takes the word 'your' literally."*

---

## The live demo script — 3 minutes, rehearsed to the word

Pre-baked scenario, no network. Rider profile loaded, map already on screen.

**Beat 1 — the dial (40 s).**
A→B set. Drag the Thrill Dial from Cruise to Send it. The line re-draws: motorway → valley road → the pass.
> *"Same two points, same rider, one gesture. Cruise: forty minutes, it gets you there. Flow: fifty-eight
> minutes and it's the reason they bought the bike. Send it: we only offer this because this rider's
> telemetry says they can — for a different rider this option is greyed out."*

**Beat 2 — the rejection (25 s).**
Click the fast road we did not choose.
> *"Two point four sets of lights per kilometre, sixty-one per cent built-up, no corner that asks for more
> than twelve degrees of lean. Flow score: zero point one nine. For this rider. That's the whole
> explanation, and you can click any road on this map and get it."*

**Beat 3 — the asymmetry payoff (35 s). The moment they remember you.**
Switch to "3 hours from here". A loop appears.
> *"Now the second use case — three hours, back where they started. And watch this: we're running this loop
> counter-clockwise. Same roads, same distance. But this rider is seven degrees stronger on left-handers,
> and going this way round, thirty-one per cent more of the corners are the ones they're actually good at.
> Clockwise, it's the same ride on paper and a worse ride in the seat."*

**Beat 4 — time-aware weather (25 s).**
Toggle the weather layer.
> *"There's a shower over this pass — not now, in forty minutes, which is exactly when this rider arrives.
> Everybody else overlays the current radar. We route in space **and** time, so the fix isn't a warning,
> it's riding the loop the other way round and getting there before it."*

**Beat 5 — the after-ride (25 s).**
The rider radar and one Skill Quest.
> *"And after the ride: right-hand corners are this rider's weak axis. Here are three specific right-hand
> hairpins, one grade above what they've ridden, on a road we know is dry and empty on Sunday mornings.
> Ride it, and their own telemetry tells us whether it worked."*

**Close (10 s).**
> *"Everything you just saw came off the bike. We never asked them a single question."*

---

## The algorithm walk-through (second act, be ready with the notebook)

Have a second screen or notebook ready with, in order: the segmentation, the Road DNA table for one real
segment, the rider's lean histograms, `challenge` and `skill` evaluated on that segment, the flow kernel,
the corridor with the Dijkstra weights, and the ablation table. Show the actual numbers on a road they can
name. Nothing convinces engineers like a real segment id with real degrees on it.

---

## Q&A — the questions that are coming

**"Why a Gaussian? Why not just a threshold?"**
> Because both tails are real and they are different failures. Below the band is boredom, above it is risk.
> A threshold models one and ignores the other. The Gaussian also gives us one knob for the user instead of
> two, and `tau` has a physical meaning — the rider's own consistency, which we measure.

**"Where do the weights come from?"**
> Three places, and we will name which is which. The physics terms are not weighted at all — required lean
> is arctan(v squared over r g). The gates are hard constraints. Only the taste terms are weighted, and
> those we fit to revealed preference and then ablate, so we can tell you what each source is worth rather
> than assert it.

**"Your sample is tiny."**
> It is. Here is exactly what we can claim at this N and what we cannot — that is slide 7. The architecture
> is built so that every additional rider tightens the interval without a retrain.

**"What about a rider who has never ridden with you?"**
> Road DNA needs zero rider data. Rider DNA starts as a prior by bike family — a GS rider and an S1000RR
> rider want different roads, and you already know which bike they bought. It converges within about five
> rides, and cold start is a designed path, not an apology.

**"Aren't you encouraging people to ride dangerously?"**
> The opposite, and it was a design constraint from hour one. We never score speed and we never reward a
> time. We score lean, smoothness and rhythm, within the posted limits. And the one hard constraint in the
> system is that we will not route a rider onto a road more than one grade above what their own telemetry
> says they have ridden. Most crashes on a great road are somebody riding a road that was one grade too
> much for them, and this is the first navigation product that can actually see that coming.

**"How is this different from a scenic route option?"**
> A scenic route is the same for everybody. Ours is different for every rider, and it changes for the same
> rider in the rain, at night, and in hour three of a long day.

**"Could you just use an LLM for this?"**
> For the conversation, yes. Not for the scoring — we would lose the explainability, and we would not be
> able to give you a per-segment reason or an ablation. The interesting part is not the language, it is
> that lean angle makes road difficulty and rider skill the same measurement.

---

## Delivery notes

- **One sentence, said three times.** Open with it, repeat it on the flow curve, close with it. If the
  judges can repeat your sentence to each other afterwards, you have won the room.
- **Say what is live and what is roadmap**, unprompted, once. It buys more credibility than any feature.
- **Name a real road** in the demo region out loud. Local specificity reads as real work.
- Whoever pitches should not be the one driving the laptop.
- If the demo breaks: cut to the recorded video without apologising, keep talking, fix nothing live.
