# 02 — THE CONCEPT: **FLOWSTATE**

> ### The one sentence
> **Fun is not a property of a road. Fun is a property of the *fit* between a road and a rider —
> and the same number that measures the fit also measures the risk.**

> ### The tagline for the slide
> **FLOWSTATE — the best route isn't the best road. It's the best road *for you*, today.**

Product surface names to use consistently everywhere (deck, code, UI):

- **Road DNA** — what a stretch of road demands.
- **Rider DNA** — what a rider actually does, measured from the bike, not from a questionnaire.
- **Flow Match** — the scorer that compares the two.
- **Thrill Dial** — the single user-facing knob (Cruise / Flow / Send it).
- **Road Pulse** — crowd-sourced road-surface health (the "is the pass OK after the storm" layer).

---

## 1. Why this idea, and what was wrong with the raw version

The original instinct (from the team) was right on every count and is preserved whole: routes rated for
*hardness*, riders rated for *level*, matched like game difficulty; nobody is a pro; some riders prefer
left curves to right; some hate climbs; flow state means different things to different people; track
favourite rides; give an aspiring rider a *progression path*; learn their style (uniform sweepers vs
brake-hard-then-throttle-hard); a god's-eye view of the roads, including whether the surface survived the
last storm.

Two upgrades turn that from a good hackathon idea into a winning one.

### Upgrade 1 — name the theory, and get the shape of the curve right

"Level matching" implies *challenge = skill* is optimal. It isn't. In flow theory (Csikszentmihalyi —
literally where the phrase "flow state" comes from), flow occurs when challenge sits **slightly above**
skill. Below it: boredom. Far above it: anxiety — and on a motorcycle, anxiety is not a mood, it is the
precondition for a crash.

So the objective is not "match the rider's level", it is **put the rider a controlled epsilon above their
level** — and epsilon is the product. That one correction gives us a unimodal scoring function, a
one-knob UI, and a safety argument for free.

### Upgrade 2 — put road difficulty and rider skill in the same physical unit

Otherwise "hardness 7 / rider level 5" is a made-up number and a judge will poke a hole in it. The unit
that works is **lean angle in degrees**, because it is (a) physics and (b) a channel BMW is literally
handing us.

For a corner of radius `R` taken at speed `v`, the required lean is `theta = arctan(v^2 / (R*g))`. So a
road's demand and a rider's capability are **the same quantity measured two ways**:

- Road DNA gives `theta_required(segment, target pace)` — from map geometry.
- Rider DNA gives the `theta_used` distribution, **separately for left and right corners** — from telemetry.

Difficulty minus skill is now a number in degrees, with a meaning any BMW engineer accepts instantly.
This is the intellectual core of the submission. Everything else hangs off it.

---

## 2. The model, in one formula they will remember

For rider `r` on segment `s`, define the standardized stretch:

```
z(s, r) = ( challenge(s) - skill(r) ) / sigma(r)

FlowScore(s | r) = exp( -(z - z*)^2 / (2 * tau^2) )
```

Challenge and skill are in degrees of lean (plus gradient, surface and sight-distance terms — see
`03_ARCHITECTURE.md`), and `sigma(r)` is that rider's own variability, so a consistent rider gets a
narrower band than an erratic one.

- **`z*` > 0 is the Thrill Dial** — how far above their own level the rider wants to sit today.
  `z* ~ 0.15` = Cruise, `0.5` = Flow, `0.9` = Send it.
- **`tau`** is tolerance width — wide for adventurous riders, narrow for riders who want consistency.

**Read the curve out loud in the pitch, left to right:**

| Region | Meaning | What the router does |
|---|---|---|
| `z << z*` | the road is beneath them → **boredom** | this is why we reject the motorway |
| `z ~ z*` | **flow** | this is what we route toward |
| `z >> z*` | over their head → **anxiety, then risk** | this is where we hard-stop |

> **The line that wins the "Fun Score + Rider Safety" section of their rubric:**
> *"We did not add a safety penalty to our fun score. Safety is the right-hand side of the same curve.
> One model, both criteria — because the road that is too hard for you is exactly the road that stops
> being fun."*

Nobody else in that room will say this. Most teams will present
`fun = 0.4*curvature + 0.3*elevation + 0.2*scenery - 0.1*traffic` and then bolt a safety filter on the end.

---

## 3. The three claims to repeat until the judges repeat them back

1. **"Fun isn't in the road. It's in the gap between the road and the rider."**
   → answers *Personalization* + *Personal Rider Data*.
2. **"Challenge minus skill is one number that scores both fun and safety."**
   → answers *Fun Score* + *Rider Safety* in one breath.
3. **"We measure the rider from the bike, not from a questionnaire."**
   → answers *Personal Rider Data* + *Crowd Data*, and it is the honest use of the exact sensor channels
   they are providing (lean angle, G-force, speed, GPS).

---

## 4. The demo moments, engineered to be remembered

A pitch is won by two or three images, not by completeness. These are ours, in priority order.

**A. The Thrill Dial.** Same A → B, one slider. Drag it and the line on the map physically re-draws:
motorway → valley road → the pass. Three words under it: *Cruise · Flow · Send it*. Say:
*"Same two points. Same rider. Three different definitions of 'best' — and the rider chooses in one gesture."*

**B. The left/right asymmetry reveal.** Pull a real anonymized rider out of the BMW data and show their
lean-angle histogram split by corner direction. Almost every rider is asymmetric; many by 5–10°. Then:
*"This rider is 7° stronger on left-handers. So we ride this loop **counter-clockwise** — same roads, same
distance, 31% more of the corners they are actually good at. No navigation product on earth does this, and
we didn't ask them a single question to find it out."*
This is the "I never thought of that" moment. Judges vote for surprise.

**C. The counterfactual panel.** Click the boring road we rejected. The panel says:
*"Rejected for you: 2.4 signals/km, 61% built-up, no corner above 12° lean. Flow 0.19."*
That is the explainability bonus they explicitly said they would award, delivered as a click.

**D. The warm-up ramp.** The first 15 km of every route are held one grade below the rider's level.
*"Cold tyres, cold rider. Our first ten minutes are never the hardest ten minutes."*
Ten seconds, and every motorcyclist in the room — which is all of them — nods.

**E. Road Pulse** (show it even if partly mocked, and say which part is live). Every ConnectedRide bike is
already a road-surface sensor: vertical acceleration + speed = roughness. Aggregate it and you get a live
condition map; after a storm, roughness on a segment jumps and we route around it.
*"BMW does not need to buy road-condition data. BMW's customers are generating it right now."*

---

## 5. What the rest of the room will build, and why we beat it

| Likely approach | Share of teams | Why we beat it |
|---|---|---|
| Weighted-sum fun score (curvature + elevation + scenery − traffic) on a Folium map | ~60% | Not personalized → near-zero on two criteria. Weights are arbitrary and a judge *will* ask "why 0.4?". We answer with physics and measured distributions. |
| LLM chat wrapper: "tell me your mood, I'll plan a ride" | ~20% | Ignores the sensor data they handed us. Not reproducible, not explainable, no scalability story. |
| RL / deep model on the telemetry | ~10% | Will not converge in 24 h on test-ride snippets, and forfeits the explainability bonus they are openly offering points for. |
| Genuinely strong concept | ~10% | The real competition. Beat them on the safety-and-fun-are-one-curve unification, the validation slide, and the asymmetry reveal. |

**Deliberate anti-strategy:** we are *not* training a deep model. They offered bonus points for
explainability and a live demo; a transparent physical model maximises both. If time is left over, add a
*small* learned re-ranker with per-feature attribution — never a black box (see `03_ARCHITECTURE.md` §7).

---

## 6. Where the gaming layer fits — it is the *after-ride* product

BMW said ConnectedRide owns **before, during and after** every ride. Map the concept onto those three and
the gamification stops being a gimmick and becomes the third of their product that everyone else forgets.

- **Before** — Thrill Dial; route grade preview ("this pass is Black; you have never ridden above Red");
  weather and pass-closure check; warm-up plan.
- **During** — flow-optimal routing; spatio-temporal rain avoidance; live difficulty adaptation when the
  telemetry says the rider is struggling; sun-glare avoidance.
- **After** — Rider DNA updates; the ride scored on **smoothness and flow, never on time**; favourite
  routes auto-detected and named; and **Skill Quests** — the system names the rider's weakest dimension,
  prescribes the specific road that trains it, then verifies improvement from the next ride's telemetry.
  *Prescribe → ride → measure → re-grade.* A closed loop, which is what makes it a product and not a badge.

> **Frame the grading with the ski-piste metaphor — Blue / Red / Black.** In Zürich and Munich every single
> person in the room gets it instantly, and it carries exactly the right connotation: a Black piste is not
> "better", it is *for a different skier*. That is our whole thesis in a metaphor they already own.

---

## 7. The honesty that scores points — do not skip these in the pitch

- **Speed is never the metric.** We score lean, smoothness and rhythm, all within posted limits. A product
  that gamifies speed on public roads cannot ship at a European OEM, and we designed around that from hour one.
- **Cold start is solved, not ignored.** With zero rides, Road DNA still works and Rider DNA falls back to a
  bike-model archetype prior (GS ≠ S1000RR ≠ R18). Every ride updates the profile; the Bayesian shrinkage is
  in the code, not just the slides.
- **Say which parts are live and which are roadmap.** Judges punish fakery, and reward a clean line between
  the two far more than they reward extra features.
