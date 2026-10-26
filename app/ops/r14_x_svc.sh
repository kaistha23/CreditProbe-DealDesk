#!/bin/bash
# R14 x (cloud walk, 8 GB container): stop or (re)start one v5 module service started by ops/v5.sh, so the walk can keep
# only the services its steps use (STATUS_R13_MERGE §8: Deal Desk + Chromium were OOM-killed with every service up).
#   ops/r14_x_svc.sh stop scorecard playbook queries agents data_builder lenses
#   ops/r14_x_svc.sh start dealdesk
# Same command line, ports, CORS origins and pid files as ops/v5.sh (no model key: none in the cloud). On the Mac use
# ops/demo.sh / ops/v5.sh as usual.
set -u
V5="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$V5/var/run"; LOGS="$V5/var/logs"; mkdir -p "$RUN" "$LOGS"
UI_PORT="${V5_UI_PORT:-5500}"
ORIGINS="http://127.0.0.1:$UI_PORT,http://localhost:$UI_PORT"
declare -A MOD=([dealdesk]=backend.dealdesk_thread.api [playbook]=backend.playbook_v5.api [lenses]=backend.lenses_v5.api
                [admin]=backend.admin.api [queries]=backend.queries_v5.api [agents]=backend.agents_v5.api
                [scorecard]=backend.scorecard_v5.api [data_builder]=backend.data_builder.api [b360]=backend.b360.api
                [whatif]=backend.whatif_v5.api [workspace]=backend.workspace_v5.api)
declare -A PORT=([dealdesk]=8508 [playbook]=8506 [lenses]=8509 [admin]=8510 [queries]=8516 [agents]=8517 [scorecard]=8507
                 [data_builder]=8504 [b360]=8502 [whatif]=8503 [workspace]=8505)
declare -A HEALTH=([dealdesk]=/api/v1/dealdesk/desk/health [playbook]=/api/v1/playbook/health [lenses]=/api/v1/lenses/health
                   [admin]=/api/v1/admin/health [queries]=/api/v1/queries/health [agents]=/api/v1/agents/health
                   [scorecard]=/api/v1/scorecard/health [data_builder]=/api/v1/data/health [b360]=/api/v1/b360/health
                   [whatif]=/api/v1/whatif/health [workspace]=/api/v1/workspace/health)
declare -A PREFIX=([dealdesk]=DEALDESK [playbook]=PLAYBOOK [lenses]=LENSES [admin]=ADMIN [queries]=QUERIES [agents]=AGENTS_V5
                   [scorecard]=SCORECARD [data_builder]=DATA_BUILDER [b360]=B360 [whatif]=WHATIF [workspace]=WORKSPACE)
cmd="$1"; shift
for name in "$@"; do
  mod="${MOD[$name]}"; port="${PORT[$name]}"; pidfile="$RUN/$name.pid"
  if [ "$cmd" = stop ] || [ "$cmd" = restart ]; then
    if [ -f "$pidfile" ]; then kill "$(cat "$pidfile")" 2>/dev/null; rm -f "$pidfile"; fi
    pkill -f "uvicorn $mod:app" 2>/dev/null
    sleep 1; echo "$name stopped"
  fi
  if [ "$cmd" = start ] || [ "$cmd" = restart ]; then
    cd "$V5" || exit 1
    p="${PREFIX[$name]}"
    env "${p}_PORT=$port" "${p}_API_PORT=$port" "${p}_CORS_ORIGINS=$ORIGINS" CONVO_MODEL=claude-opus-5 \
      POLICY_ACTIVE_PACK="$V5/var/policy/active_pack.json" \
      nohup "$V5/.venv/bin/python" -m uvicorn "$mod:app" --host 127.0.0.1 --port "$port" >"$LOGS/$name.log" 2>&1 </dev/null &
    echo $! >"$pidfile"
    for _ in $(seq 1 90); do curl -fsS "http://127.0.0.1:$port${HEALTH[$name]}" >/dev/null 2>&1 && break; sleep 1; done
    curl -fsS "http://127.0.0.1:$port${HEALTH[$name]}" >/dev/null 2>&1 && echo "$name ready on $port" || echo "$name NOT healthy"
  fi
done
