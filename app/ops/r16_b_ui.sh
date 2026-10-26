#!/bin/bash
# R16 b (cloud walk): rebuild the production UI and restart `next start` on the UI port, leaving the services as they are.
#   ops/r16_b_ui.sh            stop the UI, ops/r14_build_ui.sh, start the UI (var/run/ui.pid)
set -u
V5="$(cd "$(dirname "$0")/.." && pwd)"
UI_PORT="${V5_UI_PORT:-5500}"
pkill -f "next start --port $UI_PORT" 2>/dev/null; pkill -f "next-server" 2>/dev/null; sleep 2
"$V5/ops/r14_build_ui.sh" || exit 1
cd "$V5/frontend" && V5_UI_MODE=prod setsid nohup npx next start --port "$UI_PORT" --hostname 127.0.0.1 >"$V5/var/logs/ui.log" 2>&1 </dev/null &
echo $! > "$V5/var/run/ui.pid"
for _ in $(seq 1 60); do curl -fsS "http://127.0.0.1:$UI_PORT/" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -o /dev/null "http://127.0.0.1:$UI_PORT/" && echo "UI ready on $UI_PORT" || echo "UI NOT ready"
