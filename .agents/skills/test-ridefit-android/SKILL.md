---
name: test-ridefit-android
description: Test RideFit cloud-assistant and map flows on a headless Android emulator, including HTTP backend setup, model access and honest outage recovery.
---

# RideFit Android runtime testing

## Environment
- Android SDK is typically `$HOME/Android/sdk`; use `adb devices` and select the intended serial explicitly.
- Reinstall the rebuilt APK with `adb -s emulator-5554 install -r app/android/app/build/outputs/apk/debug/app-debug.apk`; launch `com.bmwmotorrad.ridefit/.MainActivity`.
- Mirror a headless emulator with official scrcpy, setting `ADB` if adb is not on PATH. If distro packages are unavailable, use an official Genymobile release. Maximize the mirror with wmctrl before recording.
- The emulator reaches VM-host services through `10.0.2.2`. Set the backend in More → Backend and click Connect. On Linux use `FLOWSTATE_MOCK=1`; distinguish live HTTP connection from real route-engine/physical-BMW data.
- Start API from `flowstate`: `FLOWSTATE_MOCK=1 python3 -m uvicorn api:app --app-dir app --host 127.0.0.1 --port 8091`. The emulator's `10.0.2.2` is the host's loopback, so `127.0.0.1` is enough. Never bind `0.0.0.0` and never use `tailscale funnel`; on the Mac mini (real engine, NDA-derived data) only `flowstate/run_api.sh` is used, which binds the tailnet address.
- If HTTP calls fail, inspect logcat for mixed-content/cleartext errors. Capacitor's app origin scheme and HTTP backend compatibility matter; Android INTERNET permission alone is insufficient.

## Devin Secrets Needed
- `OPENAI_API_KEY` for real-model assistant testing; bind via secret environment reference, never print it.
- A local OpenAI-compatible stub may be used only when explicitly authorized; label its coverage as wiring/tool-loop testing, not real-model quality. Real model uses no OPENAI_URL override.

## Interaction and assertions
- Use floating microphone button → text input → Ask. Android WebView speech recognition may refuse access; a no-audio emulator cannot prove audible speech.
- Slow emulator input may drop characters with bulk desktop typing or adb input text. Enter characters individually through adb if needed; verify the complete submitted transcript before asserting the result. Avoid recording minutes of input setup.
- Planned route results are on Plan → Fun-fit (Thrill), not the separate Route planner. Start the assistant from Ride, verify automatic navigation, then scroll without pressing Plan/Build to prove the result came from assistant tools.
- Reopen the assistant after navigation to inspect retained reply and cloud/on-device footer.
- For outage testing, stop the actual assistant dependency (API for real OpenAI), not an unused local stub. Verify unreachable/answered-on-device wording, restart API with its previous credential/mode, and test recovery.
- Core map styles are Satellite, Dark, Terrain, Street through the map layers control. Keep screenshots of distinct rendered tiles and no API-key error watermark.
- Coordinate with other sessions before stopping/restarting shared services. A mid-run model/stub swap invalidates assistant evidence and requires a fresh recording.
