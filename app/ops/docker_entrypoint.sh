#!/bin/bash
# Container entrypoint for the Deal Desk edition: start every edition service and the UI, then stay up.
# The model key comes from ANTHROPIC_API_KEY in ../settings.env (docker compose env_file). Without a key the app runs and
# reads documents with the rule reader and OCR; only the AI drafting and chat (Noor) are unavailable.
set -u
cd /app
mkdir -p var/run var/logs

key="$(printf '%s' "${ANTHROPIC_API_KEY:-}" | tr -d '\r\n" ')"
unset ANTHROPIC_API_KEY
if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then
  export COCKPIT_ANTHROPIC_API_KEY="$key"
  echo "Model key: found (AI drafting and Noor are on)."
else
  unset COCKPIT_ANTHROPIC_API_KEY
  echo "Model key: none in settings.env (the app runs; AI drafting and Noor are off)."
fi
unset key

# A new container has no running services: pid files and the UI build marker left in the volume are stale.
rm -f var/run/*.pid var/run/ui.build

stop_all() { echo "Stopping CreditProbe ..."; /app/ops/v5.sh stop >/dev/null 2>&1; exit 0; }
trap stop_all TERM INT

echo "Starting CreditProbe Deal Desk. The first start prepares the data and takes 3-10 minutes."
if /app/ops/v5.sh start; then
  echo ""
  echo "=============================================================="
  echo " CreditProbe Deal Desk is ready:  http://127.0.0.1:6600"
  echo " Sign in, for example:  nawaf.alotaibi / nawaf.alotaibi (RM)"
  echo "=============================================================="
else
  echo "START FAILED. The last lines of each log:"
  for f in var/logs/*.log; do echo "--- $f"; tail -n 15 "$f"; done
fi

while true; do sleep 3600 & wait $!; done
