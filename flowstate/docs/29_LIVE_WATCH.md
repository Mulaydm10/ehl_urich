# Watching the bike test live (prompt for Claude on the Mac)

During the physical test the rider has the phone at the bike; the laptop is on
the same tailnet running the backend. Everything the phone's radio and the
mySPIN client do is mirrored to three places at once, so the laptop can see the
same stream the rider sees:

1. **In-app** — Handoff → Bike link → *Radio log*.
2. **Phone logcat** — `adb logcat -s BikeLink:D MySpin:D`.
3. **Backend trail** — `GET /api/bmw/link/debug` on the Mac.

## Prompt for Claude

> You are watching a live BMW Motorrad bike-link test. The rider is next to an
> R 1300 GS with the RideFit app (`com.bmwmotorrad.ridefit`). The backend runs
> on this Mac at `http://100.80.210.100:8090` (tailnet only). Your job is to
> watch the event trail, say plainly what is happening, and flag the moment
> anything fails — do not guess or fill in values the bike never sent.
>
> Start the backend:
>
> ```bash
> cd ~/ehl_urich/flowstate && export OPENAI_API_KEY=...   # for the assistant
> ./run_api.sh
> ```
>
> Poll the trail continuously (each event has a monotonic `seq`; keep the last
> `nextSeq` and pass it as `since` so nothing is missed and nothing repeats):
>
> ```bash
> while :; do
>   curl -s "http://100.80.210.100:8090/api/bmw/link/debug?since=$SINCE&limit=200" | jq .
>   sleep 2
> done
> ```
>
> Current vehicle-data snapshot (latest value per key + granted/denied keys):
>
> ```bash
> curl -s http://100.80.210.100:8090/api/bmw/link/telemetry | jq .
> ```
>
> If the phone is on USB, also tail the device directly:
>
> ```bash
> adb logcat -s BikeLink:D MySpin:D
> ```

## What the events mean

Every event carries `seq`, `at`, `op`, `level`, `source`, `session`. Phone
events arrive at the backend with their original `seq`/`at` under `phoneSeq`/
`phoneAt` and their payload under `detail`.

### Radio / Bluetooth (`BikeLink`)

| `op` | Meaning | Watch for |
| --- | --- | --- |
| `plugin.load` | App started; `adapterPresent`, `sdk` level | `adapterPresent:false` = no radio, nothing else can work |
| `permission.request` / `permission.result` | Android runtime Bluetooth/location grant | `granted:false` — user must accept, everything downstream will be empty |
| `adapter.state` | Bluetooth on/off | `enabled:false` = ask the rider to turn Bluetooth on |
| `bonded.list` | Paired Classic devices, with `iccCandidates` | `iccCandidates:0` next to the bike means the phone is **not paired** with the head unit yet — pair in Android settings first |
| `scan.start` / `device` / `scan.failed` | BLE advertisers with RSSI | Useful context only; the bike's route link is **not** BLE GATT |
| `icc.probe` | RFCOMM socket attempt on a BMW UUID | `ok:true` + `elapsedMs` = the channel the real BMW app uses accepted us (the single most informative result of the test). An `IOException` naming *read failed* / *socket closed* usually means the head unit refused an unknown app |
| `gatt.services` | Full GATT tree after a BLE connect | Evidence dump; a route characteristic would show up here if one existed |
| `route.refused` | Transfer blocked with `PROTOCOL_UNVERIFIED` | **Expected today.** Route handoff really travels over mySPIN/Ice, not GATT, so we refuse rather than write bytes blindly |

### Vehicle data (`MySpin`)

| `op` | Meaning | Watch for |
| --- | --- | --- |
| `myspin.load` | Is the Bosch SDK present in this build? | `sdkPresent:false` — the proprietary SDK is not bundled, so no vehicle data is possible on this APK. Everything below will be absent, and that is the honest state, not a bug |
| `myspin.register` | `registerApplication()` result | `ok:false` or an exception = the app never entered a mySPIN session |
| `myspin.connection` | Head unit connected/disconnected, plus `isTwoWheeler` | `connected:true, isTwoWheeler:true` = we are talking to a motorcycle head unit |
| `myspin.access` | Per-key `canAccessVehicleData` result | The core result: `granted:true/false` per `key`. Expect the three generic keys at best (`geolocation`, `is_moving`, `is_night`) and `denied` on `display_vehicle_speed`, `display_engine_speed`, `actual_gear_position`, `fuel_level`, `lean_angle`. **Denied is the expected outcome for an unregistered app** — it is the evidence we want, not a failure to fix at the bike |
| `myspin.listener` | Subscribed to a granted key | Only appears for keys the head unit allowed |
| `vehicle.data` | An actual callback from the bike, with `values` | This is the *only* event that proves bike-sourced telemetry. If it never appears, the gauges in the app are phone-measured |
| `myspin.error` | Reflection/SDK failure with `detail` | Report verbatim; it tells us which SDK signature differs |

## Reading the app's gauges honestly

The Ride screen's live tiles are badged with their source, and the badge is the
truth of where each number came from:

- **Phone GPS** — speed from the phone's GNSS fix.
- **Phone sensors** — lean from the gyro, g-force from the accelerometer.
- **Bike · mySPIN** — the head unit actually delivered it (a `vehicle.data`
  event exists for that key).
- **Bike only · not granted** — the bike owns this signal and refused us.

A bike reading expires after 4 s of silence and the tile falls back to the
phone, so a frozen value never masquerades as live.

## What this test can and cannot prove

It **can** prove: whether the phone is paired with the head unit, whether the
RFCOMM channel the BMW app uses opens for us, whether mySPIN registration is
accepted, and exactly which vehicle-data keys BMW grants a third-party app.

It **cannot** prove route handoff to the TFT (we don't speak Ice/mySPIN
projection yet) and it will not produce bike-sourced speed/RPM/gear unless
Bosch/BMW have registered this package + signing certificate. Nothing in the
app fabricates those values in the meantime.
