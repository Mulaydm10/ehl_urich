# BMW Motorrad "Best Route" – research & EDA findings (Sat 12 Sep)

Confirmed facts are marked (C); inferences (I).

## 1. Challenge (C) – see decks/bmw_short.pdf, decks/bmw_short2.pdf
- Two use cases: (1) A→B best route, (2) "ride around current location for X hours". One or both.
- Deliverables: exact definition of "good route"; overview of all data sources + how weighted/combined;
  visual tool (route planner); dynamic solution; pitch + demo + algorithm walk-through. Explainability + live demo = bonus.
- Criteria: BMW crowd data, BMW personal rider data, external sources, scalability/efficiency, fun-score calculation, rider safety.
- BMW flags. RED: inner city, standstills, bad weather (rain & temp), bad road conditions.
  GREEN: curves, high lean angle, 50 < speed < 120, scenic views, flow, elevation, clear road view.
- Hints: "think beyond GPS – elevation, curves per km, road surface type"; "lean angle × acceleration? smile factor? you decide".
- Submission: pitch deck + GitHub repo (Entire enabled) + live demo, Sunday 12:00.

## 2. Data (C)
- Crowd: `anonymizedDataLake/trips-samples-1` 77,700 snippets / 26.4 M pts (DE/AT/CH); `trips-samples-2` 7,999 / 2.7 M (Munich–Alps). 43 cols, ~1 Hz.
- Personal: exampleUserA 100 trips + 89 planned GPX routes (routeOptions: windingness, hilliness, optimization, avoidances); B 73 trips; C 224 trips.
- Raw data is under NDA and NOT in this repo (14 GB). Derived per-trip / per-1km-cell tables are in `derived/*.parquet` (built by eda/crowd.py).

### Data traps (C)
- Crowd snippets are short: median 5.5 min / ~300 pts, 90 % < 10 min, 60 % have no stop. Ride composition can only be learned from personal data.
- Crowd timestamps are shifted: hour-of-day and month are uniform → no temporal features from crowd. Personal timestamps are real.
- 46–51 % of crowd snippets have elevation = 0 → use external DEM (SRTM) for elevation.
- ABS/ASC columns are status codes (0–3, mostly constant 1), not intervention events. Brake pressure always 0. Ask BMW.
- 13–15 % of snippets have p90 speed > 130 km/h; densest cells are the A8/A95 autobahn (113–127 km/h, lean 1–3°). Density ≠ fun.
- Cell 47.82/12.09: mean lean 46°, 90 % of time > 20°, 58 trips – almost certainly a test track (I). Exclude.
- Stray points to lon 139.8 – filter bbox.
- Manifest `itemId` does not match per-ride CSV file names for user A – link via start time/position.
- Lateral acceleration range ±0.35 looks like g not m/s² (I).

## 3. Crowd findings (C)
- Region: AT median lean p90 14°, 2.9 corners/min, 86 km/h; CH 13.5°, 1.7, 72; DE 9.6°, 1.3, 101. 64 % of snippets are DE.
- Lean vs speed (1-km cells): mean lean peaks at 60–80 km/h (7.5°), 4.1° at 100–130, 3.6° > 130. corr(lean, speed) = −0.25, corr(lean, traffic) = −0.19.
  → fun ∝ curvature at ~40–85 km/h; the highway half of BMW's 50–120 band is dead weight.
- Crowd fun map: 1,333 cells (of 13,498 with > 300 pts) have mean lean > 12°, 542 > 15°. Clusters: Allgäu (47.43/10.2), Kesselberg/Walchensee (47.52–47.63/11.29–11.36),
  Dolomites (46.4–46.6/11.4–11.5), Trentino/Garda (45.9/11.1–11.2, most re-ridden), Carinthia (46.7/13.2). 53 % of high-lean cells ridden by ≥ 10 distinct trips.

## 4. Personal findings – rider fingerprints (C unless noted)
User A (Munich, 20 bikes, touring):
- 43 % rides < 10 km (commutes; 27 rides on one 5 km pair), 40 tours; loops 21. Peak Aug/Jun, weekday mornings.
- Lean flat ~5° from 20–80 km/h, drops to 2.7° at 100–130 → fun band 40–80 km/h.
- Corners on the throttle: in > 20° lean throttle p50 23 %, coasting 10 %, slight positive longitudinal accel. Smooth roll-on style.
- Low revs: p50 2.7–3.7k rpm every gear, > 6,000 rpm 0.5 % of time.
- Within tours lean peaks at 20–60 % of ride and after 2–3 h, last 20 % drops to 3.7° → "acts" (I: place best twisties mid-ride).
- Stops don't change style (pre/post lean 4.95/4.7). 73 mid-ride stops ≥ 3 min, 10 above 1,000 m (37 min at 2,420 m) → scenic-stop behaviour.
- Weather-insensitive (lean identical 0–40 °C), 8 rides < 5 °C.
- Bike changes behaviour more than route (max lean 25° vs 37° across bikes) → normalise per bike.
- Re-ridden far-from-home roads: 707 cells on ≥ 3 trips; Pass Thurn area on 9–10 trips. GPX: "Ötztalstraße B186" in 18 planned routes.
- Declared GPX prefs mild (74/89 windingness=medium, 69 fastest vs 5 winding) vs sportier revealed behaviour.
User B: sporty commuter – lean p90 13°, 31 % rides with p90 lean > 15°, 2.2 corners/min on > 30 km, median ride 8 km, Mar–May.
User C: highest revs – rpm p90 4.8k (5.9k at 75th pct), lean p90 12.7°, 38 % sporty rides, 224 rides, afternoons.
Vs crowd: A leans at 62nd pct, B/C at 81st; all three slower than crowd (27–36th pct speed).

## 5. Concept direction (I)
Rhythm/tempo match (curvature-vs-time → corners/min, variance) + sonified 20 s route preview + composed "acts" under fatigue budget
+ deterministic safety gate (weather/wind-vs-heading/sun glare/inner city) + crowd fun map validation. Rider fingerprint = per-rider
weights over {curvature@moderate speed, elevation, scenic stops, pace, road re-use, detour appetite}, bike-normalised.
Demo: 3D terrain flythrough (Mapbox/MapLibre) with fun-heat ribbon, deck.gl crowd hex map, rider A→B→C fingerprint morph.

## 6. Open questions for BMW
ABS/ASC code semantics; lateral accel units; missing elevation; test-track cell; are B/C also internal testers.
