#!/usr/bin/env bash
# Serve the FLOWSTATE + BMW backend to the phone over Tailscale, and to nothing
# else. Same rule as run_demo.sh: the crowd data is under NDA, so never bind
# 0.0.0.0 and never `tailscale funnel` / `serve --funnel`.
set -euo pipefail
cd "$(dirname "$0")"

V="${FS_PY:-/Users/mulaydm10/ehl_urich/.venv/bin/python}"
ADDR="${FS_ADDR:-100.80.210.100}"          # this Mac on the tailnet
PORT="${FS_PORT:-8090}"
# This script is the Mac/demo launcher: refuse to start rather than fall back to
# the mock engine. FLOWSTATE_MOCK=1 still forces the mock explicitly.
export FLOWSTATE_REQUIRE_REAL="${FLOWSTATE_REQUIRE_REAL:-1}"

# NOTE FOR CLAUDE (Mac): the voice assistant's brain is server-side. Export
# OPENAI_API_KEY (or OPENAI_API_KEY_FILE pointing at a file holding it) before
# running this, and /api/assistant goes live: OpenAI calls the app's own tools
# against this same engine and the phone gets back speech plus UI actions. The
# key must stay here — it is never sent to the phone and never in the APK.
# Without it /api/assistant/status reports disabled and the app answers
# on-device instead of inventing numbers.

case "${1:-}" in
  --lan)   ADDR=$(ipconfig getifaddr en0 || echo 127.0.0.1) ;;
  --local) ADDR=127.0.0.1 ;;
esac

echo "backend on http://$ADDR:$PORT  (engine loads the bake if data/cache/demo.pkl is present)"
exec "$V" -m uvicorn api:app --app-dir app --host "$ADDR" --port "$PORT"
