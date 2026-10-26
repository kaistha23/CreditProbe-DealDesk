#!/bin/bash
# CreditProbe AI - Deal Desk edition: stop (your uploads and work are kept).
cd "$(dirname "$0")" || exit 1
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
echo " Stopping CreditProbe Deal Desk ..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && docker compose ps -q 2>/dev/null | grep -q .; then
  docker compose stop
fi
if [ -x app/.venv/bin/python ]; then
  V5_UI_PORT=6600 app/ops/v5.sh stop >/dev/null 2>&1
fi
echo " Stopped. Start it again with Start-Mac.command."
