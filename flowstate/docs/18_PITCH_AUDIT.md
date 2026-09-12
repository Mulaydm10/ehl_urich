# 18 — the pitch audit, and what replaces each dead claim

Written 2026-09-13 ~01:10 CEST. **Read this before touching `06_PITCH.md`.**
Phase 5 is a rewrite, not an edit pass.

## Why this is urgent

`06_PITCH.md` was written before the data was analysed. Six of its claims were
later **measured and disproved**, and the five-beat demo script describes an
app that does not exist. If it is presented as written, **the live demo will
contradict the slides in front of the judges** — the worst possible failure,
because the demo is a bonus-scoring criterion and it is the part they believe.

## Every claim, checked

| Where | Claim | Verdict |
|---|---|---|
| Slide 0 | "fun is the fit between road and rider" | **KEEP.** The whole idea, and it survived everything. |
| Slide 1 | their flags are road properties, not rider properties | **KEEP.** Still the sharpest framing we have. |
| Slide 2 | "seven degrees stronger on left-handers than rights" | **DEAD.** Asymmetry tested on 2 riders / ~21k corners and **rejected**. |
| Slide 3 | "gradient, sight distance, surface" in the road model | **HALF TRUE.** Surface arrived with OSM. Sight distance was never built; 46-51% of elevation is zero, so gradient is not trustworthy. |
| Slide 4 | the flow curve, safety as the right shoulder | **KEEP — it is the best slide in the deck** and the router implements it literally. |
| Slide 5 | live demo | **REWRITE** — see below. |
| Slide 6 | "measured contribution from the ablation" | **DEAD. No ablation was ever run.** Do not show a weights table we did not measure. |
| Slide 7 | "leave-one-rider-out with a clustered CI" | **IMPOSSIBLE.** There is **one** rider in the lake (`exampleUserA`). LORO cannot exist. |
| Slide 8 | before / during / after in ConnectedRide | **KEEP the frame**, drop "around the rain" (weather is dropped) and the asymmetry half of "after". |
| Slide 9 | scale, four sentences | **KEEP**, and now it has real numbers: 12 ms init, 60 ms route, 150 ms loop. |
| Slide 10 | "your thrill, literally" | **KEEP.** |

### The demo script is entirely fictional

| Beat | Claim | Reality |
|---|---|---|
| 1 | "Cruise 40 min → Flow 58 min", drag the dial | the detour ceiling in this network is **1.137x**. The app shows both dials at once *because* dragging is a bad bet. |
| 1 | "for a different rider this option is greyed out" | not a feature and never was. |
| 2 | "2.4 sets of lights per km, 61% built-up" | **these numbers do not exist** anywhere in the analysis. |
| 3 | "counter-clockwise, 31% more of the corners they're good at" | rests on the **disproved** asymmetry. Loop direction is not a feature. |
| 4 | time-aware weather, "the shower arrives in 40 minutes" | weather was **dropped**; cold-grip did **not** replicate (rho = -0.016). |
| 5 | Skill Quest, "three specific right-hand hairpins" | rests on the same disproved asymmetry. |

**Nothing in the current script can be performed.** Write the new one against
`route_tab.py` as it now exists.

## What replaces it — all measured, all stronger

1. **The gate lands on the hardest road actually ridden.** 27.29 vs 26.62 deg
   at 18 chars (1.025x) and 23.01 vs 23.18 at 16 chars (0.992x). A safety
   threshold derived from the *spread* of a rider's road choices lands within
   3% of the hardest road they ever chose — **twice, independently**. This is
   the strongest number the project produced and it is not in the deck.
2. **"We never recommend speeding" is a term in the cost function.** Of 2,237
   cells where OSM knows a limit, **1,172 (52%) have crowd p85 above it**,
   median 1.11x. Re-pricing demand at the posted limit drops those cells
   **9.67 -> 5.60 deg**. The crowd's enthusiasm is not silently inherited.
3. **The honest headline.** Not "we ride you further" but: same two points,
   roughly the same distance, **83% different roads, +38% more lean asked**.
   The router chooses character, not mileage.
4. **Change the rider, and 90% of the road changes.** Kochel -> Tegernsee,
   `userA` vs `bike_4e1a9d64`: 73% shared cells at Cruise, **10% at Send it**,
   3-5 roads refused outright. Personal rider data is a judged criterion and
   this is it, visibly, on the map.
5. **A refusal is a deleted edge, not an expensive one.** A safety gate you can
   buy past with a big enough detour budget is not a gate.
6. **What we disproved about our own idea.** Asymmetry, cold-tarmac grip, and
   the "three trip ids" forensics card were all ours, all tested, all reported
   as failures. Offer this deliberately — it is the most credible thing we can
   say, and it inoculates the deck against the obvious challenge.

## The one thing not to do

Do not quote **1.5-1.8x detour** (the plan's target), any **ablation weight**,
any **LORO** result, or the **"three trip ids"** card. Doc 13 explains why the
last one is the worst place to be wrong: it is pitched as a gift to BMW about
their own data.

## Rebuild order when Phase 5 starts

1. Slides 0, 1, 4, 9, 10 survive nearly as written — start from them.
2. Slide 2 becomes the **gate-agreement** slide (replacement 1).
3. Slide 6 becomes the **source ledger without invented weights**: BMW crowd,
   BMW personal, OSM. What each contributes, stated, not weighted.
4. Slide 7 becomes **"what we tested and what failed"** (replacement 6).
5. The demo script is rewritten beat-by-beat against `route_tab.py`, and
   `10_LIVE_DEMO.md` must be rewritten with it.

> **Executed 2026-09-13 (Phase 5).** `06_PITCH.md` and `10_LIVE_DEMO.md` were rewritten from
> this audit, and every demo beat was then checked against the running `service.py`. Two beats as
> written here were still wrong — see **F101** in `analysis/out/feature_verdicts.csv`: the first
> preset refuses nothing, and the honest "the dial did nothing" caption fires on *Kochel →
> Tegernsee*, not on the second preset. This document stays as the audit record; the two rewritten
> docs are the operative ones.
