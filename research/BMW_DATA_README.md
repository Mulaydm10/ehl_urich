# Anonymized Data Lake

> **Important:** The actual dataset described in this README (all mentioned CSV/GPX files) is **not** part of repository/archive — it will be provided separately as an additional archive (`datasetHackathon.zip`) for the Hackathon.

Geographically-filtered extracts of anonymized trip trackpoint data from BMW test rides (no customer data), prepared for hackathon use. Both collections contain CSV files with the 43-column schema of the source data described below. One file per trip snippet (a piece of a ride). One row per trackpoint.

## Files

### `trips-samples-1`

Where the **raw GPS** position falls inside a bounding
box covering roughly Germany/Austria/Switzerland:

```
positionRawLatitude  BETWEEN 45.736860 AND 49.908787
positionRawLongitude BETWEEN 7.250977  AND 15.303955
```

- Rides (distinct `trip_id`): **77.700**
- Track points: **26.7 Mio**

<img src="./trips-samples-1-2.png" height="200px" alt="trips-samples-1 detail"/> <img src="./trips-samples-1-1.png" height="200px" alt="trips-samples-1 overview"/>

### `trips-samples-2`

A smaller data set derived from `trips-samples-1` further filtered on
the position to a tighter bounding box roughly covering the
Munich / Alpine foothills area:

```
latitude_mapmatched  (positionMapMatchedLatitude)  BETWEEN 47.452237 AND 47.945786
longitude_mapmatched (positionMapMatchedLongitude) BETWEEN 10.844879 AND 11.851501
```

- Rides (distinct `trip_id`): **7.999**
- Track points: **2.4 Mio**

<img src="./trips-samples-2-2.png" height="200px" alt="trips-samples-2 detail"/> <img src="./trips-samples-2-1.png" height="200px" alt="trips-samples-2 overview"/>

## Column Reference

All columns are inherited unchanged from the anonymized source CSVs. Units
below follow standard automotive/GPS telemetry conventions used throughout
this dataset; where a field is a status/enum code rather than a physical
quantity, it is noted as such.

**Data source, per column:**
- Columns 2–16 (all `positionmapmatched*` / `positionraw*` geolocation fields) come from the **smartphone's** GPS, not the motorcycle.
- Columns 17–41 (`energy*`, `riding*`, `sensors*`) come from the **motorcycle's own onboard sensors** (vehicle bus), not the smartphone.
- `timestampinmillis` (column 1) is recorded by the **smartphone**, but for this hackathon dataset has been shifted by a random per-trip offset for privacy (see `ts_offset.csv` / `../../../dataTransformers/shift_timestamps.py`), so absolute values no longer reflect the real recording time.

| # | Column | Description | Unit | Source | Always Given? |
|---|---|---|---|---|---|
| 1 | `timestampinmillis` | Trackpoint timestamp | ms (Unix epoch, milliseconds) | Smartphone (shifted, see above) | Always |
| 2 | `positionmapmatchedlatitude` | Latitude after map-matching to the road network | ° (WGS84 decimal degrees) | Smartphone | Optional |
| 3 | `positionmapmatchedlongitude` | Longitude after map-matching to the road network | ° (WGS84 decimal degrees) | Smartphone | Optional |
| 4 | `positionmapmatchedelevation` | Elevation at the map-matched position | meter | Smartphone | Optional |
| 5 | `positionmapmatchedheading` | Direction of travel at the map-matched position | ° (0–360, from North) | Smartphone | Optional |
| 6 | `positionmapmatchedhorizontalaccuracy` | Estimated horizontal accuracy of the map-matched position | m | Smartphone | Optional |
| 7 | `positionmapmatchedverticalaccuracy` | Estimated vertical accuracy of the map-matched position | m | Smartphone | Optional |
| 8 | `positionmapmatchedspeed` | Speed at the map-matched position | m/s | Smartphone | Optional |
| 9 | `positionrawlatitude` | Raw (unprocessed) GPS latitude (`0.0` together with longitude `0.0` = no-fix sentinel) | ° (WGS84 decimal degrees) | Smartphone | Optional |
| 10 | `positionrawlongitude` | Raw (unprocessed) GPS longitude (`0.0` together with latitude `0.0` = no-fix sentinel) | ° (WGS84 decimal degrees) | Smartphone | Optional |
| 11 | `positionrawelevation` | Raw GPS elevation (unreliable/absent when the raw fix is missing) | meter | Smartphone | Optional |
| 12 | `positionrawheading` | Raw GPS direction of travel (unreliable/absent when the raw fix is missing) | ° (0–360, from North) | Smartphone | Optional |
| 13 | `positionrawhorizontalaccuracy` | Estimated horizontal accuracy of the raw GPS fix (unreliable/absent when the raw fix is missing) | meter | Smartphone | Optional |
| 14 | `positionrawverticalaccuracy` | Estimated vertical accuracy of the raw GPS fix (unreliable/absent when the raw fix is missing) | meter | Smartphone | Optional |
| 15 | `positionrawspeed` | Raw GPS speed (unreliable/absent when the raw fix is missing) | m/s | Smartphone | Optional |
| 16 | `positionrawstatus` | Raw GPS fix status/quality code | status code (unitless enum) | Smartphone | Always |
| 17 | `energyactualconsumptioncombustion` | Instantaneous fuel consumption | l/100km | Motorcycle sensor | Optional |
| 18 | `energyaverageconsumptioncombustion` | Average fuel consumption (trip) | l/100km | Motorcycle sensor | Optional |
| 19 | `energyaverageconsumptionelectric` | Average electric energy consumption (trip) | kWh/100km | Motorcycle sensor | Optional |
| 20 | `energyaverageconsumptionforrangecalculationcombustion` | Average fuel consumption used for range estimation | l/100km | Motorcycle sensor | Optional |
| 21 | `energyenergylevel` | Remaining fuel/battery level | % | Motorcycle sensor | Optional |
| 22 | `energyrange` | Estimated remaining range | meter | Motorcycle sensor | Always |
| 23 | `ridingabsbraking` | ABS (anti-lock braking) active indicator | status code (0/1) | Motorcycle sensor | Always |
| 24 | `ridingasccontrol` | ASC (automatic stability/traction control) active indicator | status code (0/1) | Motorcycle sensor | Always |
| 25 | `ridingenginespeed` | Engine rotational speed | RPM | Motorcycle sensor | Always |
| 26 | `ridinggear` | Currently engaged gear | gear number (unitless) | Motorcycle sensor | Always |
| 27 | `ridingthrottlevalue` | Throttle/accelerator position | % (0–100 open) | Motorcycle sensor | Always |
| 28 | `ridingtotalmileage` | Total vehicle odometer reading | meter | Motorcycle sensor | Always |
| 29 | `ridingtrip1` | Trip odometer 1 | meter | Motorcycle sensor | Always |
| 30 | `ridingtrip2` | Trip odometer 2 | meter | Motorcycle sensor | Optional |
| 31 | `ridingvehiclespeed` | Vehicle speed (from vehicle bus, not GPS) | m/s | Motorcycle sensor | Always |
| 32 | `sensorsaccelerationlateral` | Lateral acceleration (side-to-side) | m/s² | Motorcycle sensor | Optional |
| 33 | `sensorsaccelerationlongitudinal` | Longitudinal acceleration (forward/backward) | m/s² | Motorcycle sensor | Always |
| 34 | `sensorsaccelerationvertical` | Vertical acceleration (up/down) | m/s² | Motorcycle sensor | Optional |
| 35 | `sensorsbankingangle` | Lean/banking angle of the motorcycle | ° | Motorcycle sensor | Always |
| 36 | `sensorsbreakpressurefront` | Front brake line/caliper pressure | bar | Motorcycle sensor | Optional |
| 37 | `sensorsbreakpressurerear` | Rear brake line/caliper pressure | bar | Motorcycle sensor | Optional |
| 38 | `sensorsenginetemperature` | Engine temperature | °C | Motorcycle sensor | Optional |
| 39 | `sensorsoutsidetemperature` | Ambient/outside air temperature | °C | Motorcycle sensor | Optional |
| 40 | `sensorstirepressurefront` | Front tire pressure | bar | Motorcycle sensor | Optional |
| 41 | `sensorstirepressurerear` | Rear tire pressure | bar | Motorcycle sensor | Optional |
| 42 | `trip_id` | Anonymized per-segment ride identifier (fresh UUID, not linkable to the original user/trip) | UUID (unitless) | Generated (anonymization pipeline) | Always |
| 43 | `morton_code` | Morton (Z-order) code interleaving lat/lon bits, used for spatial indexing/clustering | code (unitless) | Derived (from smartphone GPS lat/lon) | Always |

Sentinel values: some numeric columns may contain out-of-range sentinel
values (e.g. very large negative numbers) when a sensor reading was not
available for a given trackpoint — treat implausible outliers accordingly
when analyzing the data.

**Why `positionraw*` can be missing:** the smartphone's GPS receiver can
momentarily fail to produce a fix — cold-start delay right after the app/
phone wakes up, tunnels, dense urban canyons, the phone being tucked away in
a jacket/tank bag, etc. When that happens the phone reports `0.0`/`0.0`
instead of a real coordinate. The anonymization pipeline treats that pair as a
documented no-fix sentinel: it backfills the raw lat/lon from the
map-matched position when that one is valid, and drops the row entirely if
both are `0.0`/`0.0`. The other `positionraw*` fields
(elevation/heading/accuracy/speed) ride along with the same fix and are
equally unreliable/absent whenever it's missing.

**"Always Given?" methodology:** derived empirically from a random sample of
trips (~131k trackpoints). A column was marked
`Optional` if it is either backed by a documented missing-fix sentinel
(`positionraw*`: `0`/`0` lat-lon per the anonymization pipeline;
`positionmapmatched*`: `0`/`0` lat-lon and a `-1` accuracy sentinel were
observed), or if it stays exactly flat at `0` for the *entire* trip in a
notable share of sampled trips — implausible for a genuinely continuously
varying signal, and indicative of a sensor/feature not present on every
bike model (e.g. `sensorsbreakpressurefront`/`rear` ~99% flat, TPMS-only
`sensorstirepressurefront`/`rear` ~16–17% flat, `sensorsenginetemperature`
~67% flat, all `energy*consumption*` fields 93–100% flat,
`ridingtrip2` ~92% flat — the second trip counter is rarely used/reset).
Everything else varied within essentially every sampled trip and is marked
`Always`.

---

## Personalized example-user data (`./exampleUser*`)

In contrast to `./anonymizedDataLake` (anonymized, geo-filtered, and
timestamp-shifted crowd data), the `exampleUserA` / `exampleUserB` /
`exampleUserC` folders hold the **personalized, non-anonymized** data of
individual riders — their real recorded rides and their planned routes. Use
these when you need faithful, per-user data (e.g. to reconstruct a single
rider's history).

| Folder | Recorded trips | Planned routes |
|---|---|---|
| `exampleUserA` | 100 | 89 |
| `exampleUserB` | 73 | — |
| `exampleUserC` | 224 | — |

Recorded trips of the three example users:

<img src="./exampleUserA_trips.png" height="200px" alt="exampleUserA recorded trips"/> <img src="./exampleUserB_trips.png" height="200px" alt="exampleUserB recorded trips"/> <img src="./exampleUserC_trips.png" height="200px" alt="exampleUserC recorded trips"/>

Each example-user folder can contain up to two subfolders:

### `recordedTrips/` — recorded rides (CSV)

One CSV per recorded ride, named `<itemId>.csv` (the ride's `CloudRecordedTrack`
id). One row per trackpoint, ordered by ascending `timestampinmillis`.

- **Same 43-column schema** as the anonymized CSVs — see the Column Reference
  table above; columns, order and meaning are identical.
- **Not anonymized and not shifted:** unlike the anonymized data lake,
  `timestampinmillis` keeps its **real recording time**, and
  `ridingtotalmileage` / `ridingtrip1` / `ridingtrip2` keep their **real
  odometer values** (no per-trip privacy offset applied). `trip_id` here is the
  ride's own `itemId`, so trackpoints *are* linkable back to the source
  ride/user.
- A `recordedTracks-<userId>.csv` (or `cloudRecordedTracks-<userId>.csv`)
  manifest — the raw `CloudRecordedTrack` metadata index the per-ride CSVs were
  built from — may sit alongside the per-ride files.

### `plannedRoutes/` — planned routes (GPX)

Standard GPX 1.1 route files, as exported/imported by the BMW Motorrad Connected
app. A route may use any of three point types, which the app treats differently
on import:

| GPX element | Name | Handling in the BMW Motorrad Connected app |
|---|---|---|
| `<wpt>` | Waypoint | An intermediate **destination** — a stop the route must reach. |
| `<rtept>` | Route point | On import the user decides per point whether it becomes a **waypoint** (destination) or a **shaping point** (pulls the route through a location without being a stop). |
| `<trkpt>` | Track point | A **supporting point** — shaping-point-like (the route is drawn along it) but it **must not be passed/visited** as a stop. |
