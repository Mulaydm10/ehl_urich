# 07 — VALIDATING THE FUN SCORE

> BMW's success metric is one sentence: **"You define 'fun', we evaluate."**
>
> Every team will define fun. Almost none will evaluate their own definition before BMW does. Doing it is
> cheap, it takes about three hours, and it converts the weakest part of every other pitch — *"why those
> weights?"* — into our strongest slide.

This is also where this team has an unfair advantage: the statistical core here (paired comparisons,
correlated within-subject samples, honest power) is exactly Parth's design-of-experiments background.
Use it. It is a genuine differentiator, not a flourish.

---

## 1. The problem with "fun"

There is no label. Nobody in the dataset ticked a box saying *that was a great ride*. So we do what
recommender systems do: **use revealed preference** — what riders actually did, not what they said.

Four proxy labels, in descending order of trustworthiness:

| Label | Definition | Weakness (state it) |
|---|---|---|
| **Detour** | Rider passed within X km of a faster alternative and took the longer road anyway | Strongest signal. Needs a plausible counterfactual route. |
| **Repeat** | Segment ridden more than once by the same rider | Confounded by proximity to home |
| **Sustained flow** | Traversal completed with no stop and low speed variance | Partly confounded by traffic |
| **Dwell/stop** | Stopped at a viewpoint on the segment | Sparse, but very high precision when present |

Combine into a binary `preferred` label, and **report results for each label separately**. If the
conclusion only holds for one of them, say so. That single act of honesty will land better than a
rounder number.

---

## 2. The evaluation that matters: leave-one-rider-out

The question is not "does our score fit the data" — it is **"does our score predict what a rider we have
never seen will prefer?"**

```
for each rider r:
    fit / calibrate everything on all riders except r
    build r's Rider DNA from a held-out-safe subset of r's own early rides
    score r's candidate segments
    measure: does FlowScore rank r's actually-preferred segments above the ones they skipped?
report: AUC (or top-k precision), pooled across riders, with a clustered interval
```

Two comparisons make the result meaningful:

- **vs. a personalization-free baseline** — the same score with the population-average rider substituted.
  **The gap between these two is the entire thesis of the project, expressed as one number.** If
  personalization adds nothing, we need to know before BMW tells us.
- **vs. a naive "shortest route" and a naive "most curvature" ranker** — the two things everyone else built.

---

## 3. The statistics everyone else will get wrong

**One rider contributes hundreds of segments, and they are not independent.** A rider who likes mountains
likes all of that day's mountain segments. Treating them as independent samples inflates the sample size,
shrinks the confidence interval and produces a false-positive rate several times the nominal one.

So:

- **Cluster by rider.** Bootstrap over *riders*, not over segments (a cluster bootstrap: resample riders
  with replacement, keep each sampled rider's segments whole). Report that interval.
- **Report the naive interval next to it**, and the ratio. Something like: *"Clustered on rider, our
  interval is 2.6 times wider than the naive one. The naive number is the one you would usually be shown."*
  Saying this out loud to an engineering audience is a credibility event.
- **State N honestly** — number of riders, not number of GPS points. "1.2 million samples" from 8 riders is
  8 samples wearing a costume, and a BMW data scientist knows it.
- **Power:** with a handful of internal test riders, a small effect is not detectable. Say what effect size
  *is* detectable at this N, and say that the design tightens with every rider rather than needing a retrain.

> This is the same failure mode Parth's R simulation study quantifies: with correlated repeated measures, a
> pooled test with a nominal 5% false-positive rate can fire around 29% of the time on data with no effect
> in it. It is worth one sentence in the pitch — it explains *why* we clustered, and it is a real result.

---

## 4. The ablation table — their deliverable #2, answered with evidence

They explicitly asked for "an overview of all used data sources and how they are weighted and combined."
Every other team will show a pie chart of weights they invented. Show this instead:

| Configuration | AUC vs. revealed preference | Δ |
|---|---|---|
| Geometry only (OSM + DEM) | — | baseline |
| + crowd speed & lean | — | +? |
| + crowd flow index & detour ratio | — | +? |
| + personalization (Rider DNA) | — | **+? ← the thesis** |
| + external (weather, scenery, sun) | — | +? |
| Full model | — | |

Fill it with real numbers even if they are unimpressive. **An honest small number beats an invented large
one**, and the ablation is what makes the answer to "why those weights?" a slide instead of a stammer.

---

## 5. Sanity checks to run before trusting any of it (30 minutes, do not skip)

1. **The eyeball test.** Take a road you know is great and a motorway. If the great road does not score
   higher, something is broken — find it now, not on stage.
2. **Units.** Lean in degrees vs radians, signed vs absolute, m/s vs km/h. Print min/max/mean of every
   channel once and look at it. This is the single most common way a hackathon model quietly dies.
3. **Direction.** Grade, handedness and sight distance are all direction-dependent. A segment traversed the
   other way is a different segment. Store both directions or you will get climbs and descents backwards.
4. **Map-match rate.** Report it (e.g. "87% of points matched within 15 m"). Unmatched points silently bias
   everything downstream.
5. **Leakage.** The rider's own preferred segments must not be inside the data used to build their own DNA
   for that test. Easy to get wrong, fatal to the result.
6. **Degenerate optimum.** Check the router is not looping the same perfect 2 km hairpin forty times. If it
   is, add a no-repeat penalty — and mention that you found it, because it is a good story about actually
   testing your own system.

---

## 6. The two sentences for slide 7

> *"You said you'd evaluate our definition of fun, so we evaluated it first. Holding out an entire rider,
> our score ranks the roads they actually chose above the ones they skipped with an AUC of **[x]**, clustered
> on rider — and the same model with personalization switched off drops to **[y]**. That gap is the whole
> idea of this project, and it's the only number in our deck we'd ask you to check."*
