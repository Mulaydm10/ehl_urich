# BMW Motorrad RideFit — app

BMW-only Android ride app (React + TypeScript + Vite + Tailwind, packaged with
Capacitor). It merges the FLOWSTATE "fun-fit" routing engine, the BMW
Motorrad ConnectedRide feature set (garage, vehicle status, rides + telemetry,
cloud-sync-shaped data, GPX import/export, route handoff, group ride, offline
maps) and honest phone-only states.

## Architecture

```
React screens -> AppState provider -> BmwApi interface
                                        |-- httpApi  -> FastAPI  /api/*, /api/bmw/*
                                        `-- mockApi  -> bundled offline fallback
```

At startup the app probes the backend `/health`. If it is unreachable the app
falls back to bundled data and shows an honest "engine not reachable" state
instead of inventing telemetry. The FLOWSTATE routing engine is never mocked
inside the app — when the server is down no route is drawn.

## Run the backend (FLOWSTATE + BMW services)

The FastAPI wrapper lives in `../flowstate/app/api.py`.

```bash
cd ../flowstate
# Deterministic mock, on a dev box with no NDA data bake:
FLOWSTATE_MOCK=1 python3 -m uvicorn api:app --app-dir app --host 127.0.0.1 --port 8090
# Real engine, on the Mac that has the bake — binds the tailnet address only and
# refuses to start on the mock:
./run_api.sh
```

**Never bind `0.0.0.0` and never use `tailscale funnel` / `serve --funnel`.** On a
conference network the Mac also holds a public address, and the engine serves
NDA-derived data. The phone reaches `run_api.sh`'s tailnet address as long as it is
signed in to the same tailnet.

## Run the frontend (dev)

```bash
npm install
# Point dev + build at the backend:
VITE_BACKEND_URL=http://127.0.0.1:8090 npm run dev
npm run lint
npm run build
```

## Configure the backend URL from inside the app

The server address is user-configurable at runtime in **More -> Backend**
(persisted in `localStorage`), so a shipped APK can be pointed at the
Mac-hosted server over Tailscale (e.g. `http://100.x.y.z:8090`) without a
rebuild. Leave it empty to use the address the build shipped with
(`VITE_BACKEND_URL`).

## Maps

Maps are real tile-backed Leaflet maps (`src/components/BaseMap.tsx`), not
vector renders. Four keyless basemaps are selectable in-map on any interactive
map — Satellite (Esri World Imagery + boundary/place labels), Dark (Esri Dark
Gray Canvas), Terrain (OpenTopoMap) and Street (OpenStreetMap). No API key and
no account is needed; each style carries its provider's required attribution.
CARTO is deliberately not used — its basemaps now watermark keyless requests.

Route geometry, FLOWSTATE flow colouring, refusal pins and markers draw on top
of the basemap (`RouteMap`, `FlowMap`). `LiveMap` adds the device's own GPS
position from the Geolocation API with an accuracy radius and a follow toggle.
When permission is denied or the device has no receiver it says so rather than
showing a fabricated position.

## Voice assistant

`src/components/VoiceAssistant.tsx` is a mic button above the tab bar. Speech
in and out uses the browser's Web Speech API; there is also a text box, because
Android WebView has no recogniser and refuses the mic.

Where the answer comes from depends on the server:

* **Cloud assistant** — when the backend has an OpenAI key, the prompt goes to
  `POST /api/assistant`. The model calls this app's own functions
  (`plan_route`, `plan_loop`, `compare_routes`, `suggest_stops`, `garage`,
  `bike_status`, `season_stats`, `list_rides`, `ride_debrief`, `start_ride`,
  `stop_ride`, `group_ride`, `offline_maps`, `handoff_route`, `open_screen`,
  `select_bike`), the server runs them against the same FLOWSTATE engine and
  BMW services the REST API uses, and the reply carries both the spoken
  sentence and UI actions — so "plan me a two hour flow loop from Tegernsee
  and show it" actually plans it and opens the screen.
* **On-device** — with no key, or with the backend unreachable, the panel falls
  back to `src/services/voiceIntents.ts`, which only reads data already loaded.
  It never fabricates an answer, and the footer says which layer replied.

To enable the cloud assistant on the Mac, before `./run_api.sh`:

```bash
export OPENAI_API_KEY=sk-...          # or: export OPENAI_API_KEY_FILE=~/.openai-key
export OPENAI_MODEL=gpt-4o-mini       # optional, this is the default
```

The key stays on the Mac. It is never sent to the phone and never compiled into
the APK — the app only ever sees the spoken text and the UI actions.
`GET /api/assistant/status` reports whether it is configured.

## Build the Android debug APK

```bash
npm run build
npx cap sync android
# android/local.properties must contain: sdk.dir=/path/to/Android/sdk
cd android && ./gradlew assembleDebug
# -> android/app/build/outputs/apk/debug/app-debug.apk
```

Capacitor is configured with `cleartext: true` so the app can reach a plain
HTTP backend over Tailscale.

## Not yet validated

Physical BMW Bluetooth / TFT pairing is not exercised here — the emulator has
no Bluetooth radio. It needs a real Android phone next to the bike.

The phone-to-Mac path has not been verified from the build VM either: the VM
was deliberately left off the tailnet, so the Mac's tailnet address is only
reachable from the phone. Confirm it on the device.

## Note for Claude (Mac)

What this branch needs live on the Mac to be demoed end to end:

```
Backend URL   http://100.80.210.100:8090       (tailnet address only)
Health check  GET /health -> {"ok": true, "engine": "service"}
Start         cd ~/ehl_urich/flowstate && ./run_api.sh
Stop          pkill -f "uvicorn api:app"
```

- `engine` must read `service`. `FLOWSTATE_MOCK=1` forces the mock and is for
  deliberate mock testing only — never for the demo.
- The API does not come back after a reboot; re-run `run_api.sh`.
- On the phone: install Tailscale, sign in to the same account, then set
  **More -> Backend** to `http://100.80.210.100:8090`. Cleartext HTTP is
  already allowed in the Capacitor config, so no rebuild is needed.
- If conference Wi-Fi blocks Tailscale, use the phone's hotspot with the Mac
  joined to it.
- Map tiles are fetched from Esri / OpenTopoMap / OpenStreetMap directly by the
  phone, so the phone needs general internet access, not just the tailnet.
- The BMW endpoints are still the local stand-in (`bmw_cloud.py`), not the real
  ConnectedRide cloud, and route handoff sends nothing to a bike.
- No credentials, tokens, VINs or API keys are committed anywhere in this
  branch; keep it that way.
