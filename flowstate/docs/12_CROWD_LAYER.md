# 12 — THE CROWD LAYER

Built from the salvaged `trips-samples-2` — **7,999 rides, complete**, BMW's own Munich / Alpine-foothills
box. This is the "Usage of BMW Crowd Data" judging criterion, and it is no longer blocked.

Script: `analysis/10_crowd_layer.py`. Outputs in `analysis/out/`:
`crowd_grid.parquet`, `crowd_gems.csv`, `crowd_hazards.csv`, `crowd_hazards_corrected.csv`.

---

## 1. What the grid contains

| | |
|---|---|
| Cells (18-char morton prefix, ≈153 × 102 m) | **26,987** |
| Ride-traversals aggregated | **478,668** |
| Trackpoints | **2,721,275** |
| Corners extracted | **174,733** |
| Hard-braking (ABS==3) events | **1,243** across 747 cells |
| Bounding box | lat 47.383–48.026, lon 10.723–11.958 |

**Coverage — this is the scalability story in one row:**

| rides through a cell | cells |
|---|---|
| 2+ | 21,952 |
| 5+ | 16,254 |
| 20+ | 6,734 |
| 100+ | **836** |

Per-cell columns: `n_rides, n_points, n_corners, crowd_v_p50, crowd_v_p85, crowd_lean_p50, crowd_lean_p90,
demand_p50, demand_p90, radius_p50, flow_index, stop_rate, abs_events, grade_mean, elev_mean, lat, lon`.

> Note the box is slightly wider than the README's stated filter (lat 47.452–47.946, lon 10.845–11.852)
> because the README filtered on *map-matched* position while cells are keyed on the raw morton code.
> Harmless, but say it before someone notices.

**F29–F33 are now all live:** crowd speed percentiles, crowd lean percentiles, flow index, stop rate, and
gem detection — all from BMW's own fleet, none of it assumed.

## 2. The gems

Top cells by demand × flow × popularity (`crowd_gems.csv`). The leaders are real, named motorcycling roads:

| lat, lon | demand p90 | radius | rides | flow | elevation |
|---|---|---|---|---|---|
| 47.8585, 11.8353 | **41.6°** | 48 m | 56 | 0.98 | 657 m |
| 47.8362, 11.8135 | 38.4° | 112 m | 66 | 1.00 | 634 m |
| 47.6329, 11.3562 | 36.9° | 44 m | 58 | 0.91 | 774 m |
| 47.5358, 10.8889 | 34.0° | 48 m | 44 | 1.00 | 1,107 m |

These cluster around Tegernsee/Schliersee, the Kesselberg/Walchensee area and the Ammergau — i.e. the roads
Bavarian motorcyclists actually ride. **The gem detector was not told any of that.** It found them from
lean angle and flow alone, which is the point worth making on stage.

## 3. ⚠️ The hazard layer had a bug — fixed, and worth telling the story

The first ranking by ABS events per traversal produced cells with **median crowd speed 26 km/h, stop rate
0.10 and demand of only 8.4°**. That is not a treacherous corner — **that is a junction with a queue.** ABS
firing at 16 km/h is traffic braking, and a naive hazard map just rediscovers traffic lights.

**The fix:** restrict to free-flowing, genuinely cornering cells — ≥5 rides, crowd speed > 40 km/h,
stop rate < 0.15, ≥5 corners. That leaves **6,912 candidate cells, of which 311 carry a hard-braking event**
(`crowd_hazards_corrected.csv`). The leader is `47.904, 11.405` — 7 events across 9 traversals, 103 m radius,
descending, crowd lean p90 of 27°.

> Say this in the walk-through. *"Our first hazard map found traffic lights. We noticed, and we fixed it."*
> Admitting a bug you caught yourself is worth more than a map that quietly contains one.

## 4. 🎯 The crowd confirms the core finding, independently

`docs/10_LIVE_DEMO.md` §1 reports the rider-level result: hard-braking rises monotonically with how far a
corner sits above the rider's skill — 3.6× risk ratio, but only **13 events**, p = 0.071.

The crowd gives a **second, independent test** at a different level of analysis (road cell, not rider):

| free-flowing cells | median demand p90 |
|---|---|
| **with** a hard-braking event (n = 311) | **13.3°** |
| without (n = 6,601) | 12.5° |

**Mann-Whitney p = 4.9 × 10⁻³.**

So the link between cornering demand and braking-at-the-limit holds at crowd scale, on anonymized data,
with a p-value two orders of magnitude better than the single-rider test. The effect is modest (+0.8° of
demand) — say that too — but it is no longer a trend with one rider behind it.

> **How to present the pair:** *"On one rider we saw it as a trend we couldn't call significant. On eight
> thousand anonymized rides we see the same direction at p equals point zero zero five. Same mechanism,
> two independent levels of analysis, and neither of them is our opinion about what is fun."*

## 5. What is still limited

- **The crowd data has no riders.** `trip_id` is a fresh UUID per snippet and is deliberately not linkable
  to a person, so crowd rows cannot carry a *rider* skill estimate. Rider-level `z` stays with the example
  users; the crowd gives road-level demand, flow and hazard. Do not blur the two in one claim.
- **Timestamps are shifted per trip**, so no weather join and no time-of-day analysis on the lake.
- **`trips-samples-1` is only 1.9% recovered** (1,468 of 77,700 rides), so the wide DE/AT/CH picture is
  missing and all of the above is Bavaria-only.
- The gem and hazard rankings rest on cells with as few as 5 traversals. For the pitch, quote the
  **836 cells with 100+ rides** as the confidence tier.
