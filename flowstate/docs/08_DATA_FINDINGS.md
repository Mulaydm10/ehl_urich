# 08 — WHAT THE REAL DATA SAYS

Every number here was measured on the actual BMW hackathon data, not assumed.
Scripts: `analysis/01_profile.py`, `02_feature_tests.py`, `03_deep_checks.py`. Outputs in `analysis/out/`.

**Sample analysed:** `exampleUserA` — 100 recorded rides, **508,183 trackpoints**, 89 planned routes,
5 years of history (2021-07-23 → 2026-08-07). The crowd data lake (`trips-samples-1/2`, 85,699 rides,
29.1 M points) is **not yet available** — see §7.

---

## 1. THE HEADLINE: the physics bridge is real

FLOWSTATE rests on one claim — that road demand and rider behaviour are **the same physical quantity**,
so `theta_required = arctan(v·ω/g)` computed from the map should match `sensorsbankingangle` measured on
the bike. It does.

| Level | n | corr | slope |
|---|---|---|---|
| Trackpoint | 244,147 | **0.576** | OLS 0.527 / reverse 0.628 → **errors-in-variables slope 0.92** |
| Per corner (≥3 s, median 54 km/h) | **5,747 corners** | **0.730** | 0.53 (OLS), ratio of sd 0.73 |

Measured lean / required lean, by demand band:

| Required lean | n corners | measured median | ratio |
|---|---|---|---|
| 5–10° | 425 | 7.2° | 0.85 |
| 10–20° | 2,257 | 12.5° | 0.82 |
| 20–30° | 1,775 | 19.6° | 0.81 |
| 30–60° | 1,269 | 25.8° | **0.70** |

**Read this correctly, because it is the strongest slide in the deck.** Naive OLS gives ~0.53 only because
*both* variables carry noise (yaw rate from 1 Hz map-matched heading is noisy); the errors-in-variables
slope is **0.92**, i.e. essentially the physics. The residual gap — and the fall to 0.70 at high demand —
is itself physically correct: **the bike leans less than the centre of mass when the rider hangs off**, and
the harder the corner the more they hang off. So use a calibration constant `k ≈ 0.8` and say why.

> **Pitch line:** *"We claimed road difficulty and rider skill are the same measurement. On 5,747 real
> corners from BMW's own sensors, correlation 0.73 — and where they disagree, they disagree in exactly the
> direction body position predicts."*

---

## 2. CORRECTIONS — things in our plan that the data disproves

### 2.1 The left/right asymmetry is NOT there for this rider (this changes the pitch)

This was demo moment B. Measured three ways:

| Estimator | Result |
|---|---|
| BMW's own per-ride `leanAngleLeftMax − RightMax` (n=96) | mean **−0.40°**, 95% CI ±0.70 → **not significant** |
| Per-ride p95 of trackpoint lean (n=66 rides) | mean −1.40°, CI [−2.11, −0.69] → significant, **right stronger** |
| **Per-corner p95, left vs right corners (n=5,747 corners)** | L 31.2° vs R 30.4° → **left stronger by 0.8°** |

**The sign flips depending on the estimator, and the effect is ~1° either way — it is noise for user A.**
The mechanism is sound and BMW themselves store `leanAngleLeftMax`/`leanAngleRightMax` as first-class
fields, so the feature is real and computable. But **do not build the pitch on "every rider is asymmetric"
until it is verified on users B and C.** Check it the moment the full archive lands; if a rider does show
it, that rider becomes the demo. If none do, the honest framing is: *"we measure it per rider, we report
the confidence interval, and we only act on it when it clears the interval"* — which is a better story than
an effect that evaporates when a judge asks for the error bar.

> Note the methodology point worth saying out loud: **per-ride maxima are noise-dominated; per-corner p95
> is the right estimator.** That is a real finding about their own summary fields.

### 2.2 Brake pressure is 100% dead — but ABS gives it back

`sensorsbreakpressurefront` and `sensorsbreakpressurerear` are **exactly 0 on all 100 rides**. The corner
style classifier (F05) as specified is dead. **Replacement, and it is arguably better:**

| `ridingabsbraking` | n (moving) | mean accel | P(decelerating) | throttle |
|---|---|---|---|---|
| 1 (armed) | 220,556 | +0.010 | 35% | 19% |
| 2 | 22,410 | +0.022 | 41% | 17% |
| **3** | **60** | **−2.22 m/s²** | **93%** | **4.5%** |

**`ridingabsbraking == 3` is an unambiguous hard-braking / ABS-regulation event** (p05 = −4.7 m/s² ≈ 0.48 g).
**33 of 100 rides contain at least one.** Code 2 is not a clean brake flag — don't use it as one.
Braking intensity otherwise comes from `d(v)/dt` on the vehicle-bus speed, which is clean.

### 2.3 Road Pulse via vertical acceleration is dead

`sensorsaccelerationvertical` is **flat on 91% of rides** and non-zero on 2.8% of points. Same for
`sensorsaccelerationlateral` (flat on 91%). The "every bike is a road-surface sensor" feature cannot be
built from these channels on this fleet. Rebuild it on: **ABS-3 event density**, speed-variance anomalies,
and `positionmapmatchedhorizontalaccuracy` — or present it as roadmap and say plainly which channel it needs.

### 2.4 A units bug in BMW's own README

`sensorsaccelerationlongitudinal` is documented as **m/s²**. Regressed against `d(v)/dt` over 244,437
points: **corr 0.78, slope 5.47** — it is **in g**, not m/s² (a m/s² channel would give slope ≈ 1;
attenuation from noise pulls 9.81 down to 5.5). The manifest's `accelerationMax` (median 0.47, max 1.84)
and `decelerationMax` (median 0.36, max 0.82) are g values too.
**Mentioning this to BMW on site is free credibility** — and silently getting it wrong is a 10× error.

### 2.5 Lean-angle sign and the standstill trap

- **Positive `sensorsbankingangle` = RIGHT-hand corner** (corr +0.53 with clockwise yaw rate). Documented nowhere.
- At standstill, lean p05 = **−14.7°** — that is the **side stand** (bikes park leaning left). Drop every
  lean sample with `ridingvehiclespeed < 0.5`, or the rider's "left lean" profile is a parked motorcycle.

---

## 3. SAMPLING AND SHAPE OF THE DATA

- **~1 Hz** (median interval 1.04 s). At 60–100 km/h that is **3–6 samples per corner.** Consequences:
  - Corner-level features: fine (we get 5,747 corners from one rider).
  - Sub-corner phase features (brake → apex → throttle, F05's original form): **not reliable.** Do not promise them.
  - **Resample by distance, not by time**, before computing corner rhythm (F19).
- **40 of 100 rides contain gaps > 10 s.** Always split on gaps before differentiating anything.
- Trip duration median 37.8 min, max **601 min**. Rides are not homogeneous.
- **Use `positionrawelevation`** (flat on 1% of rides), **not** `positionmapmatchedelevation` (flat on 36%).

## 4. WHO USER A ACTUALLY IS — and why it matters

| | |
|---|---|
| Rides < 20 km | **51 of 101** |
| Rides 20–100 km | 30 |
| Rides > 100 km | 20 |
| Rides with > 500 m elevation range | 16 |
| Alpine rides (max elev > 1200 m) | 11 |
| Weekend share | 20% |
| **Distinct `bikeId`** | **20 bikes over 101 rides** |

Two things follow.

**(a) User A is an internal test rider on 20 different motorcycles.** `bikeId` is present — Machine DNA
(F14) is computable — but bike is now a **confounder for skill**: lean p95 on an S1000RR and on an R18 are
not the same measurement. Any rider-skill estimate must control for `bikeId`. Say this before a judge says
it. It is also an opportunity nobody else will take: same rider, 20 bikes, is a clean natural experiment
for separating the bike effect from the rider effect.

**(b) Half his recorded data is commuting.** The fun is concentrated in ~20 rides. Per-rider fun data is
**sparse**, which is the empirical argument for the crowd layer — not a design preference.

## 5. THE GROUND TRUTH WE WERE LOOKING FOR — it is in the planned routes

`plannedRoutes/` holds **89 GPX routes this rider deliberately built**. This is the revealed-preference
label `07_VALIDATION.md` needed.

- Median length **163 km** (p25 108, p75 217, max 538).
- **43 of 89 (48%) are round trips** — start within 2 km of end.
- 37 of 89 contain shaping/supporting points → the rider explicitly pulled the route onto specific roads.
- Route names, chosen by the rider: **Grossglockner · Nockalm · Obertauern · Felbertauern · Turracher ·
  Saalbach · Fünf Seen Rundfahrt · Kochel am See · Naturns**.

> **This is the single best slide in the deck, and it is free.**
> *"We didn't have to guess what this rider wants. He named his own routes — and he named them after
> passes, not destinations: Grossglockner, Nockalm, Obertauern, Felbertauern. Eighty-nine planned routes,
> median 163 km, and half of them end where they started. He isn't going anywhere. The road is the
> destination — which is exactly BMW use case #2."*

And the sharpest contrast in the whole dataset:

> *"Half of what he records is a commute under 20 km. Everything he plans is a 163 km alpine loop.
> **Riders record commuting and plan riding** — so the product belongs in the planning, not the tracking."*

**`isFavorite` exists in BMW's schema but is `False` on all 101 rides for user A.** Check B and C
immediately — a single rider with favourites turns `07_VALIDATION.md` from proxy labels into real ones.

## 6. NINE FEATURES THE DATA HANDED US THAT WE HAD NOT THOUGHT OF

Ranked by value. Full detail in `analysis/out/unused_signal.csv`.

| ID | Channel | The feature | Why it matters |
|---|---|---|---|
| **F75** | `ridingabsbraking == 3` | **Limit-event density per km.** 33/100 rides contain one | A direct, physical measurement of a rider exceeding available grip. Per-rider it is the safety gate; crowd-aggregated it marks genuinely treacherous corners. **Replaces the dead brake channel and is better than it.** |
| **F79** | `ridingtotalmileage` | **Lifetime odometer = rider EXPERIENCE** (0 → 49,917 km here) | Experience is not skill. Two riders with identical lean p95 and 5,000 vs 50,000 km are different risks. This is the cold-start prior we said in `02_CONCEPT.md` §7 that we did not have — and it is one column. |
| **F77/F78** | `ridinggear`, `ridingenginespeed` | **Mood detector.** Gear × RPM × speed | Short-shifting vs revving out separates a touring mood from a sporting mood **on the same road, same rider, same day** — the thing the Thrill Dial is trying to ask them. And RPM survives 1 Hz far better than acceleration does. |
| **F80** | `sensorstirepressurefront/rear` | **Measured warm-up.** dP/dt over the first 10 min | Turns the warm-up ramp (F45) from motorcycling folklore into an instrumented gate: cold tyres are visible in the data. |
| **F54+** | `sensorsoutsidetemperature` | **On-bike ambient temperature**, real on 95% of rides, p05 11.5 °C / p95 32.5 °C | Better than a weather API: it is ground truth at the exact time and place the rider was there. Retro-fit it to score past rides. |
| **F81** | `sensorsenginetemperature` | **Congestion detector** — coolant rising while speed is low | Traffic, from the bike, with no traffic feed. |
| **F83** | `positionmapmatchedhorizontalaccuracy` | **Free enclosure proxy** — GPS accuracy degrades under canopy and in steep valleys | An empirical stand-in for the "clear road view" green flag we were going to approximate from land cover. |
| **F82** | `energyrange` | Range in metres, live on 95% of rides | Makes fuel-stop planning (F50) computable now rather than roadmap. |
| **F76** | `ridingasccontrol` | Traction-control state | **Weaker than hoped** — code 2 (756 points) shows *lower* lean and *lower* throttle than baseline, so it is not a clean slip event. Do not oversell it. |

## 7. WHAT IS STILL BLOCKED, AND WHY IT IS URGENT

**`exd_download (1).zip` (384 MB) is a truncated download** — no end-of-central-directory record, no central
directory. It contains `datasetHackathon.zip` → the **entire crowd data lake**:

- `trips-samples-1`: **77,700 rides / 26.7 M trackpoints** (DE/AT/CH)
- `trips-samples-2`: **7,999 rides / 2.4 M trackpoints** (Munich / Alpine foothills)
- `exampleUserB` (73 rides) and `exampleUserC` (224 rides)

Without it, **six features are blocked**: F10 pace index, F29 crowd speed, F30 crowd lean, F31 flow index,
F32 detour ratio, F33 gem detection — i.e. **the entire "Usage of BMW Crowd Data" judging criterion.**
Re-download it before anything else.

One limitation to design around now: the anonymized lake's `timestampinmillis` is **shifted by a random
per-trip offset**, so crowd trips **cannot be joined to historical weather**. Example-user timestamps are
real, so the weather join works there. Plan the validation accordingly.

## 8. REVISED PRIORITIES, given the evidence

1. **Re-download the crowd archive.** Six features and one whole judging criterion depend on it.
2. **Build the demo around use case #2 (the loop).** 48% of this rider's planned routes are round trips,
   median 163 km. The data says the loop is what riders actually plan.
3. **Add F75 (ABS limit events) and F79 (odometer experience) to the P0 spine.** Both are single columns,
   both are strong, both are things no other team will have looked for.
4. **Re-verify the L/R asymmetry on users B and C before it goes in the pitch.** If it holds for one of
   them, it is still the best demo moment available. If it holds for none, present the method and the
   interval — not the claim.
5. **Keep the physics slide exactly as it is.** corr 0.73 over 5,747 corners, with the hang-off explanation
   for the 0.8 ratio, is the most defensible thing in the deck.
6. **Tell BMW about the `m/s²` vs `g` error in their README**, and ask whether `ridingabsbraking == 3` is
   the true ABS-regulation code. Both signal that you read their data properly.
