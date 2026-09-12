# NOTES — running scratch log

## Data schema — MEASURED, not assumed (exampleUserA, 100 rides, 508,183 points)

43 columns, one row per trackpoint, **~1 Hz** (median interval 1.04 s). Full detail: `docs/08_DATA_FINDINGS.md`.

| Channel | Column | Unit (MEASURED) | Usable? |
|---|---|---|---|
| lean angle | `sensorsbankingangle` | **degrees, signed, POSITIVE = RIGHT corner** | YES — flat on only 4% of rides, range ±43.8° |
| speed | `ridingvehiclespeed` | m/s (vehicle bus) | ⚠️ **DEAD ON 27 OF 100 RIDES** — all three speed channels (`ridingvehiclespeed`, `positionmapmatchedspeed`, `positionrawspeed`) are flat zero on the same 27 rides = **26% of all trackpoints**. GPS position and lean are still fine on those rides, so fall back to GPS-derived speed. Ask BMW about it. |
| long. accel | `sensorsaccelerationlongitudinal` | **g — README says m/s² and is WRONG** (slope 5.47 vs d(v)/dt, would be ~1 if m/s²) | YES, with the right unit |
| lat. accel | `sensorsaccelerationlateral` | — | **DEAD** — flat on 91% of rides |
| vert. accel | `sensorsaccelerationvertical` | — | **DEAD** — flat on 91%; kills Road Pulse as designed |
| brake pressure | `sensorsbreakpressurefront/rear` | — | **DEAD** — exactly 0 on all 100 rides |
| braking events | `ridingabsbraking` | code 0–3 | **YES, code 3 = real hard braking** (mean −2.22 m/s², 93% decelerating, 33/100 rides) |
| traction control | `ridingasccontrol` | code 0–3 | WEAK — code 2 does not look like a slip event |
| throttle | `ridingthrottlevalue` | % 0–100 | YES — varies on 96% of rides |
| gear / RPM | `ridinggear`, `ridingenginespeed` | gear, RPM | YES — both vary on 96% |
| elevation | `positionrawelevation` | m | **YES — use this one** (flat on 1%); `positionmapmatchedelevation` is flat on 36% |
| heading | **`positionrawheading`** | ° 0–360 | **USE THIS ONE.** Map-matched heading is quantised to road-segment bearings — **38% of moving samples read exactly zero yaw**, vs **6%** for raw. Switching channels moves the physics-bridge correlation 0.576 → 0.602 and the errors-in-variables slope 0.92 → **1.08**, i.e. straddling the perfect 1.0. |
| ambient temp | `sensorsoutsidetemperature` | °C | YES — real on 95% of rides, p05 11.5 / p95 32.5 |
| tyre pressure | `sensorstirepressurefront/rear` | bar | YES — varies on ~89%; gives measured tyre warm-up |
| odometer | `ridingtotalmileage` | m (0 → 49,917 km) | YES — lifetime experience proxy |
| timestamp | `timestampinmillis` | ms epoch | **REAL for example users** (2021-07-23 → 2026-08-07); **SHIFTED in the anonymized lake — no weather join there** |
| energy | `energy*` | — | DEAD except `energyrange` (metres, live on 95%) |
| `ridingtrip2`, `positionrawstatus` | | | DEAD — 100% flat zero |

### Traps found the hard way
1. **Side stand:** lean at standstill has p05 = −14.7° — that is a parked bike. Drop all lean where `ridingvehiclespeed < 0.5`.
2. **40 of 100 rides have gaps > 10 s.** Split on gaps before differentiating anything.
3. **20 distinct `bikeId` across 101 rides** — user A is an internal test rider. Bike confounds skill; control for it.
4. `morton_code` is a 32-digit string — read it as text or parquet/int conversion overflows.
5. **27 rides have no speed at all** (see the table) — any per-ride aggregate must report how many rides it actually used, or a quarter of the archive silently vanishes.
6. Console is cp1252: run scripts with `PYTHONIOENCODING=utf-8` or route names crash the print.

## Demo region

- bbox: **not yet locked.** The data argues for the Munich / Alpine foothills box used by `trips-samples-2`:
  lat 47.452237–47.945786, lon 10.844879–11.851501 — it is BMW's own choice of interesting area,
  and user A's routes run straight through it (Kochel am See, Fünf Seen Rundfahrt).

## Open questions for BMW on site

1. Is `sensorsaccelerationlongitudinal` in g? The README says m/s²; the data says g. *(evidence ready)*
2. Is `ridingabsbraking == 3` the true ABS-regulation code, and what are 0/1/2?
3. Do users B or C have any ride with `isFavorite = true`? It is False on all 101 of user A's.
4. Are `sensorsaccelerationlateral/vertical` and brake pressure absent by bike model, or lost in the export?
5. Which use case do you care about more — A→B or the X-hour loop? (Our data says riders plan loops: 48%.)
6. Can `bikeId` be resolved to a model family, even coarsely (GS / RR / R / Tour)?

## Things that broke

- `exd_download (1).zip` (384 MB): **truncated download**, no central directory — the whole crowd data lake
  plus users B and C are inside it. Re-download required.
- Read tool cannot render PDFs here (no poppler). Use PyMuPDF (`import fitz`).
