# 27 · Bike link (local Bluetooth to the TFT / ConnectedRide Navigator)

The bike link is the **local** channel between the phone and the motorcycle.
It is separate from the BMW cloud (`api.connectedride.bmwgroup.com`), which is
not covered here.

Honesty rule for every layer: **a result with `ok: true` means a physical device
acknowledged the bytes.** Stand-ins always return `ok: false, standIn: true` and
say "stand-in" in their message. Nothing in this repo may report a bike connection
or route transfer that did not happen.

## Pieces

| Layer | Where | Role |
|---|---|---|
| Backend | `flowstate/app/bike_link.py`, `/api/bmw/link/*` in `api.py` | Transport-agnostic contract. `StandInTransport` (default) simulates and labels itself; `NativeBleTransport` (`FLOWSTATE_BIKE_LINK=native`) has no radio and only mirrors what the phone reports via `POST /api/bmw/link/native/report`. |
| Android plugin | `app/android/.../BikeLinkPlugin.java`, registered in `MainActivity.java` | Capacitor plugin: adapter state, BLE scan, connect/disconnect, connection state, `sendRoute` (chunked GATT write). Permissions in `AndroidManifest.xml` (`BLUETOOTH_SCAN`/`CONNECT`, legacy `BLUETOOTH`/`BLUETOOTH_ADMIN` + location for API < 31). |
| TS wrapper | `app/src/services/bikeLink.ts` | One `BikeLinkClient` with three implementations picked by `resolveBikeLink`: native (Android), backend (browser + backend up), offline (says nothing can be sent). |
| UI | `app/src/components/BikeLinkPanel.tsx`, `screens/Handoff.tsx`, `screens/More.tsx` | Adapter status, scan results, pair/connect, connection state, "Send route to bike" showing the real outcome. |

## Verified (on this VM, no radio)

- Backend endpoints respond with `FLOWSTATE_MOCK=1` on `:8092`; stand-in scan →
  pair → connect → send all carry `standIn: true` and send returns
  `ok: false, status: "stand_in"`.
- Native mode without a phone report: send returns `ok: false, status: "failed"`.
  After a phone reports `connection.state = connected`, send returns
  `status: "pending_phone"`; after the phone reports the transfer, `sent`.
- Frontend lints and builds; the Handoff screen shows "Stand-in — nothing sent to
  the bike" for the stand-in transport and "Simulated connection" when the
  stand-in is "connected".
- The Android plugin compiles against compileSdk 34 (see PR notes for the exact
  build state; Maven Central rate-limiting can make the first Gradle run flaky).

## NOT verified — needs a real phone next to a real bike

- **Any BLE I/O.** The analysis emulator and this VM have no Bluetooth radio.
  Scan, connect, service discovery and writes have never run against hardware.
- **The bike's route-transfer protocol.** The real link is Bosch mySPIN
  (`com.bmw.connride.mona.myspin.MySpinICEService`) plus BLE for ConnectedRide
  Control / accessories. The wire protocol was **not captured**; no GATT UUIDs or
  opcodes are known. `ROUTE_GATT` in `bikeLink.ts` is therefore `null` and the
  plugin rejects `sendRoute` with `PROTOCOL_UNVERIFIED` until a
  `serviceUuid`/`characteristicUuid` pair is sourced on a real bike. The
  "GPX over a GATT characteristic" write path is a seam, not a claim about
  BMW's protocol; a mySPIN SDK integration may be required instead.
- In-app pairing/unpairing on Android (the plugin only connects to bonded or
  advertised devices; bonding is left to the system Bluetooth settings).
- `hasSensorBox` / `hasV2bCapability`: only known from vehicle static data;
  reported as `null`/unverified until read from the bike.
- Behaviour on a phone with Bluetooth present but disabled, and on API < 31
  permission flows (code paths exist, untested).

## Phone-side test procedure

Prereqs: Android 12+ phone, BMW with a 6.5″ TFT or ConnectedRide Navigator,
backend reachable from the phone (Tailscale, `VITE_BACKEND_URL` set at build time,
backend started with `FLOWSTATE_BIKE_LINK=native`).

1. Build and install: `cd app && npm run build && npx cap sync android` and
   `./gradlew installDebug` in `app/android` (needs `local.properties`, never commit it).
2. Bike ignition on, phone Bluetooth on. Open **More → Bike link**: expect
   "Phone Bluetooth" and "Not connected" (not "Stand-in").
   - Bluetooth off → expect "Bluetooth is turned off on this phone".
   - On a device without BLE → expect "No Bluetooth adapter on this device".
3. Tap **Scan for bike**. Accept the permission prompt. Note which advertised
   names/addresses appear and their RSSI; record them in this doc.
4. Tap **Connect** on the bike. Expect "Connected · <name>". Check the backend
   mirrored it: `GET /api/bmw/link/status` → `connection.state == "connected"`.
5. Capture the GATT table (nRF Connect or `adb logcat | grep BikeLink`) and
   record every service/characteristic UUID here. Identify the route/navigation
   characteristic, if one exists; otherwise the transfer has to go through mySPIN.
6. Fill `ROUTE_GATT` in `bikeLink.ts` with the sourced UUIDs, rebuild, go to
   **Send to bike → Send route to bike**. Expect:
   - the TFT/Navigator actually shows the route, and
   - the UI says "Sent to …" with `ok: true`, and `GET /api/bmw/link/status`
     shows the transfer as `sent`.
   If the bike does not show the route, the UI must say "Not sent" — file it as
   a protocol finding, do not soften the message.
7. Walk out of range: expect "Not connected" within a few seconds and the backend
   to mirror `disconnected`.

Record results (device names, UUIDs, what the TFT showed) in this file under a
"Findings" heading before flipping any capability to `verified: true`.
