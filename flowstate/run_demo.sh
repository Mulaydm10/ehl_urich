#!/usr/bin/env bash
# Serve the demo to the phone over Tailscale, and to nothing else.
#
# `--server.address=0.0.0.0` binds EVERY interface. On the conference network
# this Mac also holds a routable public address, so 0.0.0.0 publishes an app
# backed by NDA data to the open internet. Bind the tailnet address instead.
# Never `tailscale funnel` / `tailscale serve --funnel` for the same reason.
set -euo pipefail
cd "$(dirname "$0")"

V=/Users/mulaydm10/ehl_urich/.venv/bin/python
ADDR="${FS_ADDR:-100.80.210.100}"          # this Mac on the tailnet
PORT="${FS_PORT:-8501}"

case "${1:-}" in
  --lan)   ADDR=$(ipconfig getifaddr en0 || echo 127.0.0.1)
           echo "LAN mode: $ADDR — conference Wi-Fi usually isolates clients,"
           echo "so prefer the phone's own hotspot with the Mac joined to it." ;;
  --local) ADDR=127.0.0.1 ;;
esac

echo "open http://$ADDR:$PORT on the phone"
exec "$V" -m streamlit run app/streamlit_app.py \
  --server.address="$ADDR" --server.port="$PORT" \
  --server.headless=true --browser.gatherUsageStats=false
