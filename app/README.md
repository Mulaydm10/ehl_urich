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
# Deterministic mock (no NDA data bake required):
FLOWSTATE_MOCK=1 python3 -m uvicorn api:app --app-dir app --host 0.0.0.0 --port 8090
# Real engine (on the Mac that has the NDA data bake): omit FLOWSTATE_MOCK.
```

Bind to `0.0.0.0` so the phone can reach it over Tailscale.

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
