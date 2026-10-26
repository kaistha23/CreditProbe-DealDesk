#!/bin/bash
# v5 Cockpit (frozen Round H code) -- start | stop | status
#
# Runs the frozen scripts/cockpit_v4/{start,stop,status}.py unchanged, with
# v5's own ports, runtime directory and data directory. Nothing outside
# ~/CreditProbe_Workspace/v5 is read or written, except the Keychain item
# named below, which is read into this process's environment only.
set -u
V5="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="$V5/var/runtime/cockpit"
API_PORT="${V5_COCKPIT_API_PORT:-8500}"
UI_PORT="${V5_UI_PORT:-5500}"
MODEL="claude-opus-5"
PRICE_CARD="$V5/config/cockpit_v4/price_card.claude-opus-5.json"
KEYCHAIN_SERVICE="creditprobe-cockpit-v4"
KEYCHAIN_ACCOUNT="COCKPIT_ANTHROPIC_API_KEY"

cd "$V5" || exit 1
export DATA_ANALYTICS_DIR="$V5/data/analytics"
export COCKPIT_V4_NAMESPACE="cockpit_v4"
export COCKPIT_AGENTIC_V3_NAMESPACE="cockpit_v4"
export AI_COCKPIT_REASONING_MODEL="$MODEL"
export COCKPIT_V4_PRICE_CARD="$PRICE_CARD"

# Stop the production UI (`next start`): the process group from var/run/ui.pid (Linux: its own session via setsid;
# Mac: the pid and its children), then whatever still listens on the UI port (a server whose pid file is gone).
stop_ui() {
  if [ -f "$V5/var/run/ui.pid" ]; then
    UIPID="$(cat "$V5/var/run/ui.pid")"
    kill -- "-$UIPID" 2>/dev/null || { pkill -P "$UIPID" 2>/dev/null; kill "$UIPID" 2>/dev/null; }
    rm -f "$V5/var/run/ui.pid"
  fi
  # The listener on the port, and any `next start` / next-server whose working directory is this checkout's
  # frontend (lsof cannot always see the socket owner, e.g. in a sandbox; a server orphaned by an earlier stop).
  for _ in 1 2 3; do
    PIDS="$(lsof -nP -tiTCP:"$UI_PORT" -sTCP:LISTEN 2>/dev/null || true)"
    # anchored patterns, so a shell whose command line mentions these words is never matched; never self or parent
    for pid in $(pgrep -f "^[^ ]*(node|npx|next)[^ ]* .*next start --port $UI_PORT" 2>/dev/null; pgrep -f "^next-server" 2>/dev/null); do
      case "$pid" in "$$"|"$PPID") continue ;; esac
      cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
      case "$cwd" in "$V5"/*|"$V5") PIDS="$PIDS $pid" ;; esac
    done
    PIDS="$(echo $PIDS | tr ' ' '\n' | sort -u | tr '\n' ' ')"
    [ -n "${PIDS// /}" ] || break
    kill $PIDS 2>/dev/null || true
    sleep 1
  done
  rm -f "$V5/var/run/ui.build"
}

case "${1:-start}" in
  start)
    if [ -z "${COCKPIT_ANTHROPIC_API_KEY:-}" ]; then
      # The named account only: an unfiltered lookup returns whichever item
      # the Keychain lists first, which is how a stale key was served before.
      COCKPIT_ANTHROPIC_API_KEY="$(security find-generic-password \
        -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w 2>/dev/null | tr -d '\r\n')"
      export COCKPIT_ANTHROPIC_API_KEY
    fi
    if ! printf '%s' "${COCKPIT_ANTHROPIC_API_KEY:-}" | grep -qE '^sk-ant-[^[:space:]]+$'; then
      echo "Credential: not a well-formed key -- dashboards work, Ask will not."
      # The frozen launcher refuses an empty credential outright. With no key
      # at all (Linux, no Keychain) pass a fixed non-secret placeholder so the
      # dashboards still start; Ask then reports that the key is invalid.
      if [ -z "${COCKPIT_ANTHROPIC_API_KEY:-}" ]; then
        COCKPIT_ANTHROPIC_API_KEY="no-key-dashboards-only"
        export COCKPIT_ANTHROPIC_API_KEY
      fi
    fi
    if [ "${V5_UI_MODE:-dev}" = "prod" ]; then
      # A small container (the cloud session: `next dev` with every service up exceeds its memory) runs the UI
      # from a production build (`npx next build` in frontend/ first): the API through the frozen launcher with
      # --no-ui, then `next start` on the UI port, its pid in var/run/ui.pid.
      # Idempotent: an API already up on its port is kept (the frozen launcher would refuse to start a second one
      # and stop the whole start); a UI already up is kept too.
      if curl -fsS -o /dev/null "http://127.0.0.1:$API_PORT/health" 2>/dev/null; then
        echo "Cockpit API already running on http://127.0.0.1:$API_PORT."
      else
        "$V5/.venv/bin/python" "$V5/scripts/cockpit_v4/start.py" \
          --runtime-dir "$RUNTIME" --api-port "$API_PORT" --ui-port "$UI_PORT" \
          --model "$MODEL" --price-card "$PRICE_CARD" --no-open --no-prompt --no-ui || exit 1
      fi
      mkdir -p "$V5/var/run" "$V5/var/logs"
      BUILD_ID="$(cat "$V5/frontend/.next/BUILD_ID" 2>/dev/null || echo none)"
      if curl -fsS -o /dev/null "http://127.0.0.1:$UI_PORT/login" 2>/dev/null; then
        # A UI serving an older build than frontend/.next (rebuilt while it ran) would 500 on its chunks: restart it.
        if [ "$(cat "$V5/var/run/ui.build" 2>/dev/null)" = "$BUILD_ID" ]; then
          echo "UI already running on http://127.0.0.1:$UI_PORT (production build $BUILD_ID)"; exit 0
        fi
        echo "UI on http://127.0.0.1:$UI_PORT serves an older build: restarting it."
        stop_ui
      fi
      rm -f "$V5/var/run/ui.pid"
      # `setsid` exists on Linux only (macOS has none): on a Mac `next start` is simply backgrounded, and `stop`
      # kills the process tree from the pid file.
      SETSID="$(command -v setsid || true)"
      ( cd "$V5/frontend" && NEXT_PUBLIC_COCKPIT_V4_API="http://127.0.0.1:$API_PORT" \
          $SETSID nohup npx next start --port "$UI_PORT" --hostname "${V5_BIND_HOST:-127.0.0.1}" >"$V5/var/logs/ui.log" 2>&1 </dev/null &
        echo $! >"$V5/var/run/ui.pid" )
      echo "$BUILD_ID" >"$V5/var/run/ui.build"
      for _ in $(seq 1 60); do
        curl -fsS -o /dev/null "http://127.0.0.1:$UI_PORT/login" 2>/dev/null && { echo "UI ready on http://127.0.0.1:$UI_PORT (production build)"; exit 0; }
        sleep 1
      done
      echo "UI did not become ready; see $V5/var/logs/ui.log"; exit 1
    fi
    exec "$V5/.venv/bin/python" "$V5/scripts/cockpit_v4/start.py" \
      --runtime-dir "$RUNTIME" --api-port "$API_PORT" --ui-port "$UI_PORT" \
      --model "$MODEL" --price-card "$PRICE_CARD" --no-open --no-prompt
    ;;
  stop)
    stop_ui
    exec "$V5/.venv/bin/python" "$V5/scripts/cockpit_v4/stop.py" --runtime-dir "$RUNTIME" ;;
  status) exec "$V5/.venv/bin/python" "$V5/scripts/cockpit_v4/status.py" --runtime-dir "$RUNTIME" ;;
  *) echo "usage: $0 start|stop|status"; exit 2 ;;
esac
