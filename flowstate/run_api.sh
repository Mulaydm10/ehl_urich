#!/usr/bin/env bash
# Serve the FLOWSTATE + BMW backend to the phone over Tailscale, and to nothing
# else. Same rule as run_demo.sh: the crowd data is under NDA, so never bind
# 0.0.0.0 and never `tailscale funnel` / `serve --funnel`.
set -euo pipefail
cd "$(dirname "$0")"

V="${FS_PY:-/Users/mulaydm10/ehl_urich/.venv/bin/python}"
ADDR="${FS_ADDR:-100.80.210.100}"          # this Mac on the tailnet
PORT="${FS_PORT:-8090}"

case "${1:-}" in
  --lan)   ADDR=$(ipconfig getifaddr en0 || echo 127.0.0.1) ;;
  --local) ADDR=127.0.0.1 ;;
esac

echo "backend on http://$ADDR:$PORT  (engine loads the bake if data/cache/demo.pkl is present)"
exec "$V" -m uvicorn api:app --app-dir app --host "$ADDR" --port "$PORT"
