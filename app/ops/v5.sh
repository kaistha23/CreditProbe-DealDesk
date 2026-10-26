#!/bin/bash
# CreditProbe v5 -- one app: start | stop | status
#
#   UI (one URL, one navigation)   http://127.0.0.1:5500
#   Cockpit API (frozen Round H)   http://127.0.0.1:8500   via ops/cockpit.sh
#   Early Warning API              http://127.0.0.1:8501   backend.ews_domain.api
#   Borrower 360 API               http://127.0.0.1:8502   backend.b360.api
#   What-If API                    http://127.0.0.1:8503   backend.whatif_v5.api
#   Data Builder API               http://127.0.0.1:8504   backend.data_builder.api
#   Workspace API                  http://127.0.0.1:8505   backend.workspace_v5.api
#   Scorecard Validation API       http://127.0.0.1:8507   backend.scorecard_v5.api
#   Deal Desk API                  http://127.0.0.1:8508   backend.dealdesk_thread.api
#   Playbook and Policy Docs API   http://127.0.0.1:8506   backend.playbook_v5.api
#   Lenses API                     http://127.0.0.1:8509   backend.lenses_v5.api
#   Admin API (PLAN_R5 A)          http://127.0.0.1:8510   backend.admin.api
#   Queries and BRF API (R9 F)     http://127.0.0.1:8516   backend.queries_v5.api
#   Agents API (R11 G)             http://127.0.0.1:8517   backend.agents_v5.api
#
# Only processes v5 started are ever stopped (pid files under var/run). A busy
# port that is not ours stops the start; nothing else is killed.
set -u
# Every service polls SQLite; give each process room for its files and sockets (macOS gives
# a Finder-launched shell only 256 descriptors per process).
ulimit -n 8192 2>/dev/null || ulimit -n 4096 2>/dev/null || true
V5="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$V5/var/run"; LOGS="$V5/var/logs"
mkdir -p "$RUN" "$LOGS"
EWS_PORT="${EWS_API_PORT:-8501}"
UI_PORT="${V5_UI_PORT:-5500}"
B360_PORT="${B360_API_PORT:-8502}"
WHATIF_PORT="${WHATIF_API_PORT:-8503}"
DATA_PORT="${DATA_BUILDER_PORT:-8504}"
WORKSPACE_PORT="${WORKSPACE_API_PORT:-8505}"
SCORECARD_PORT="${SCORECARD_API_PORT:-8507}"
DEALDESK_PORT="${DEALDESK_API_PORT:-8508}"
PLAYBOOK_PORT="${PLAYBOOK_API_PORT:-8506}"
LENSES_PORT="${LENSES_API_PORT:-8509}"
ADMIN_PORT="${ADMIN_API_PORT:-8510}"
QUERIES_PORT="${QUERIES_API_PORT:-8516}"
AGENTS_PORT="${AGENTS_API_PORT:-8517}"
# Each service calls its siblings at these origins. They follow the ports above, so an install on other ports (the
# Deal Desk edition beside R16 on the Mac) never reaches another install's services.
H5=127.0.0.1
export CORE_API_ORIGIN="${CORE_API_ORIGIN:-http://$H5:$WORKSPACE_PORT}"
export PLAYBOOK_API_ORIGIN="${PLAYBOOK_API_ORIGIN:-http://$H5:$PLAYBOOK_PORT}"
export DEALDESK_API_ORIGIN="${DEALDESK_API_ORIGIN:-http://$H5:$DEALDESK_PORT}"
export DATA_BUILDER_API_ORIGIN="${DATA_BUILDER_API_ORIGIN:-http://$H5:$DATA_PORT}"
export COCKPIT_API_ORIGIN="${COCKPIT_API_ORIGIN:-http://$H5:${V5_COCKPIT_API_PORT:-8500}}"
export EWS_API_ORIGIN="${EWS_API_ORIGIN:-http://$H5:$EWS_PORT}"
export WHATIF_API_ORIGIN="${WHATIF_API_ORIGIN:-http://$H5:$WHATIF_PORT}"
export SCORECARD_API_ORIGIN="${SCORECARD_API_ORIGIN:-http://$H5:$SCORECARD_PORT}"
export LENSES_API_ORIGIN="${LENSES_API_ORIGIN:-http://$H5:$LENSES_PORT}"
# The active versioned policy pack Policy Docs writes and the Cockpit reads (FX-7).
POLICY_PACK="${POLICY_ACTIVE_PACK:-$V5/var/policy/active_pack.json}"
ORIGINS="http://127.0.0.1:$UI_PORT,http://localhost:$UI_PORT"

# The edition (Deal Desk edition, October 2026). `dealdesk` (the default on the dealdesk-edition branch) starts the
# services Deal Desk and its panels use -- the Cockpit API (the data books, the policy pack and the legacy API the
# Studio and Trace screens read; its Ask is not in the navigation), Data Builder, the Core service, Deal Desk,
# Playbook and Policy Docs, Admin and the agents -- and leaves Early Warning, Borrower 360, What-If, the Scorecard,
# Lenses and Queries/BRF down, since the edition's navigation does not reach them. V5_EDITION=full starts everything.
EDITION="${V5_EDITION:-dealdesk}"
in_edition() {   # in_edition <service>: 0 when this edition runs the service
  [ "$EDITION" = "full" ] && return 0
  case "$1" in ews|b360|whatif|scorecard|lenses|queries) return 1 ;; *) return 0 ;; esac
}

# One v5 module service: name, module, port, health path, env prefix.
start_svc() {
  in_edition "$1" || { echo "$1: not in the $EDITION edition (skipped)."; return 0; }
  local name="$1" module="$2" port="$3" health="$4" prefix="$5" pidfile="$RUN/$1.pid" owner
  owner="$(port_owner "$port")"
  if [ -n "$owner" ]; then
    if [ -f "$pidfile" ] && [ "$(cat "$pidfile")" = "$owner" ]; then
      echo "$name already running on $port (pid $owner)."; return 0
    fi
    echo "STOP: port $port is held by pid $owner, which v5 did not start."; return 1
  fi
  cd "$V5" || return 1
  env "${prefix}_PORT=$port" "${prefix}_API_PORT=$port" "${prefix}_CORS_ORIGINS=$ORIGINS" \
    nohup "$V5/.venv/bin/python" -m uvicorn "$module:app" \
      --host "${V5_BIND_HOST:-127.0.0.1}" --port "$port" >"$LOGS/$name.log" 2>&1 </dev/null &
  echo $! >"$pidfile"
  # A fresh store seeds itself on the first start (the Core service took three minutes on a Mac), so the wait is
  # generous: V5_HEALTH_WAIT_S seconds (default 600), and a service that dies is reported at once.
  for _ in $(seq 1 "${V5_HEALTH_WAIT_S:-600}"); do
    curl -fsS "http://127.0.0.1:$port$health" >/dev/null 2>&1 && {
      echo "$name ready on http://127.0.0.1:$port"; return 0; }
    kill -0 "$(cat "$pidfile")" 2>/dev/null || { echo "$name exited; see $LOGS/$name.log"; return 1; }
    sleep 1
  done
  echo "$name did not become healthy in ${V5_HEALTH_WAIT_S:-600}s; see $LOGS/$name.log"; return 1
}

stop_svc() {
  local name="$1" module="$2" pidfile="$RUN/$1.pid"
  [ -f "$pidfile" ] || { echo "$name: not started by v5."; return 0; }
  local pid; pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null && ps -o command= -p "$pid" | grep -q "$module"; then
    kill "$pid"
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    echo "$name stopped (pid $pid)."
  fi
  rm -f "$pidfile"
}

start_modules() {
  # The What-If IFRS 9 domain (var/whatif_v5) is rebuilt from the books when missing. Every edition builds it:
  # Deal Desk's PD model reads it (backend/dealdesk/pd_model.py), whether or not the What-If service runs.
  [ -f "$V5/ops/whatif_build_domain.py" ] && "$V5/.venv/bin/python" "$V5/ops/whatif_build_domain.py" --if-needed >"$LOGS/whatif_domain.log" 2>&1
  start_svc b360 backend.b360.api "$B360_PORT" /api/v1/b360/health B360 || return 1
  # The What-If assistant uses the Cockpit's model key when the Mac has it (Keychain, as ops/cockpit.sh
  # reads it). It goes into this one process's environment only: never argv, never a file.
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export WHATIF_ANTHROPIC_API_KEY="$key" CONVO_ANTHROPIC_API_KEY="$key"; fi
    export WHATIF_MODEL="${WHATIF_MODEL:-claude-opus-5}"
    start_svc whatif backend.whatif_v5.api "$WHATIF_PORT" /api/v1/whatif/health WHATIF ) || return 1
  start_svc data_builder backend.data_builder.api "$DATA_PORT" /api/v1/data/health DATA_BUILDER || return 1
  # Project threads answer through the forked Cockpit conversation (backend/convo): the Cockpit's key, env only.
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export CONVO_ANTHROPIC_API_KEY="$key"; fi
    start_svc workspace backend.workspace_v5.api "$WORKSPACE_PORT" /api/v1/workspace/health WORKSPACE ) || return 1
  start_svc scorecard backend.scorecard_v5.api "$SCORECARD_PORT" /api/v1/scorecard/health SCORECARD || return 1
  # Deal Desk: the assistant uses the Cockpit's model key the same way What-If does (environment only).
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export CONVO_ANTHROPIC_API_KEY="$key"; fi
    export CONVO_MODEL="${CONVO_MODEL:-claude-opus-5}"
    start_svc dealdesk backend.dealdesk_thread.api "$DEALDESK_PORT" /api/v1/dealdesk/desk/health DEALDESK ) || return 1
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export PLAYBOOK_ANTHROPIC_API_KEY="$key" CONVO_ANTHROPIC_API_KEY="$key"; fi
    export POLICY_ACTIVE_PACK="$POLICY_PACK"
    start_svc playbook backend.playbook_v5.api "$PLAYBOOK_PORT" /api/v1/playbook/health PLAYBOOK ) || return 1
  # Lenses (PLAN_R5 Session L): the lens assistant uses the Cockpit's model key the same way (environment only).
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export CONVO_ANTHROPIC_API_KEY="$key"; fi
    export CONVO_MODEL="${CONVO_MODEL:-claude-opus-5}"
    start_svc lenses backend.lenses_v5.api "$LENSES_PORT" /api/v1/lenses/health LENSES ) || return 1
  # Admin (PLAN_R5 A): access policies, workflows, users, Agent Operations, AI Studio, settings, audit log.
  # Its assistant uses the Cockpit's model key the same way (environment only).
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export CONVO_ANTHROPIC_API_KEY="$key"; fi
    start_svc admin backend.admin.api "$ADMIN_PORT" /api/v1/admin/health ADMIN ) || return 1
  # Queries and BRF studio (PLAN_R9 Session F): reads the books only; no model key.
  start_svc queries backend.queries_v5.api "$QUERIES_PORT" /api/v1/queries/health QUERIES || return 1
  # R11 agents (PLAN_R11_AGENTS G): the model planner uses the Cockpit's model key the same way (environment only);
  # without it every agent runs its deterministic planner.
  ( key="${COCKPIT_ANTHROPIC_API_KEY:-}"
    if [ -z "$key" ] && command -v security >/dev/null 2>&1; then
      key="$(security find-generic-password -s creditprobe-cockpit-v4 -a COCKPIT_ANTHROPIC_API_KEY -w 2>/dev/null | tr -d '\r\n')"
    fi
    if printf '%s' "$key" | grep -qE '^sk-ant-[^[:space:]]+$'; then export CONVO_ANTHROPIC_API_KEY="$key"; fi
    export CONVO_MODEL="${CONVO_MODEL:-claude-opus-5}"
    start_svc agents backend.agents_v5.api "$AGENTS_PORT" /api/v1/agents/health AGENTS_V5 ) || return 1
}

stop_modules() {
  stop_svc agents backend.agents_v5.api
  stop_svc queries backend.queries_v5.api
  stop_svc admin backend.admin.api
  stop_svc lenses backend.lenses_v5.api
  stop_svc playbook backend.playbook_v5.api
  stop_svc scorecard backend.scorecard_v5.api
  stop_svc dealdesk backend.dealdesk_thread.api
  stop_svc workspace backend.workspace_v5.api
  stop_svc data_builder backend.data_builder.api
  stop_svc whatif backend.whatif_v5.api
  stop_svc b360 backend.b360.api
}

port_owner() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1; }

start_ews() {
  in_edition ews || { echo "ews: not in the $EDITION edition (skipped)."; return 0; }
  local pidfile="$RUN/ews.pid" owner
  owner="$(port_owner "$EWS_PORT")"
  if [ -n "$owner" ]; then
    if [ -f "$pidfile" ] && [ "$(cat "$pidfile")" = "$owner" ]; then
      echo "Early Warning API already running on $EWS_PORT (pid $owner)."; return 0
    fi
    echo "STOP: port $EWS_PORT is held by pid $owner, which v5 did not start."; return 1
  fi
  # One simple command in the background (not a `cd && ...` list, which would
  # background a whole subshell that holds the caller's terminal open), so $!
  # is uvicorn's own pid.
  cd "$V5" || return 1
  EWS_API_PORT="$EWS_PORT" EWS_CORS_ORIGINS="http://127.0.0.1:$UI_PORT,http://localhost:$UI_PORT" \
    nohup "$V5/.venv/bin/python" -m uvicorn backend.ews_domain.api:app \
      --host "${V5_BIND_HOST:-127.0.0.1}" --port "$EWS_PORT" >"$LOGS/ews.log" 2>&1 </dev/null &
  echo $! >"$pidfile"
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:$EWS_PORT/api/v1/ews/health" >/dev/null 2>&1 && {
      echo "Early Warning API ready on http://127.0.0.1:$EWS_PORT"; return 0; }
    sleep 1
  done
  echo "Early Warning API did not become healthy; see $LOGS/ews.log"; return 1
}

stop_ews() {
  local pidfile="$RUN/ews.pid"
  [ -f "$pidfile" ] || { echo "Early Warning API: not started by v5."; return 0; }
  local pid; pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null && ps -o command= -p "$pid" | grep -q "backend.ews_domain.api"; then
    kill "$pid"
    # Wait until it has really gone, so a start that follows finds the port free.
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    echo "Early Warning API stopped (pid $pid)."
  fi
  rm -f "$pidfile"
}

# Deal Desk edition, Round C: an Agent Operations run log written by the full product (UAT 1 on the Mac) holds
# What-If, Lenses and Early Warning turns; it is archived once (moved, not deleted) when the edition first starts.
archive_full_runlog() {
  [ "$EDITION" = "dealdesk" ] || return 0
  local log="$V5/var/convo/agent_runs.jsonl" stamp="$V5/var/convo/.dealdesk_edition"
  if [ -s "$log" ] && [ ! -f "$stamp" ]; then
    mkdir -p "$V5/var/archive"
    mv "$log" "$V5/var/archive/agent_runs-full-$(date +%Y%m%d-%H%M%S).jsonl"
    echo "Agent Operations: the full product's run log was archived to var/archive (the edition starts its own)."
  fi
  mkdir -p "$V5/var/convo" && touch "$stamp"
}

case "${1:-start}" in
  start)
    archive_full_runlog
    start_ews || exit 1
    start_modules || exit 1
    export NEXT_PUBLIC_EWS_API="http://127.0.0.1:$EWS_PORT"
    export NEXT_PUBLIC_B360_API="http://127.0.0.1:$B360_PORT"
    export NEXT_PUBLIC_WHATIF_API="http://127.0.0.1:$WHATIF_PORT"
    export NEXT_PUBLIC_DATA_API="http://127.0.0.1:$DATA_PORT"
    export NEXT_PUBLIC_WORKSPACE_API="http://127.0.0.1:$WORKSPACE_PORT"
    export NEXT_PUBLIC_SCORECARD_API="http://127.0.0.1:$SCORECARD_PORT"
    export NEXT_PUBLIC_DEALDESK_API="http://127.0.0.1:$DEALDESK_PORT"
    export NEXT_PUBLIC_PLAYBOOK_API="http://127.0.0.1:$PLAYBOOK_PORT"
    export NEXT_PUBLIC_LENSES_API="http://127.0.0.1:$LENSES_PORT"
    export NEXT_PUBLIC_ADMIN_API="http://127.0.0.1:$ADMIN_PORT"
    export NEXT_PUBLIC_QUERIES_API="http://127.0.0.1:$QUERIES_PORT"
    export NEXT_PUBLIC_AGENTS_API="http://127.0.0.1:$AGENTS_PORT"
    export COCKPIT_POLICY_PACK_FILE="$POLICY_PACK"
    # The product knowledge base with worked examples on the books, for the Cockpit's product help (FX-13).
    "$V5/.venv/bin/python" "$V5/ops/build_product_knowledge.py" --if-needed >"$LOGS/product_knowledge.log" 2>&1 \
      && export COCKPIT_PRODUCT_KNOWLEDGE_V5="$V5/var/product_knowledge/pack_v5.json"
    "$V5/ops/cockpit.sh" start
    ;;
  stop)
    "$V5/ops/cockpit.sh" stop
    stop_modules
    stop_ews
    ;;
  restart)
    # One module service only (b360, whatif, data_builder, workspace, scorecard, playbook, ews), so a change to
    # one backend does not take the others down.
    case "${2:-}" in
      ews) stop_ews; start_ews ;;
      b360) stop_svc b360 backend.b360.api; start_svc b360 backend.b360.api "$B360_PORT" /api/v1/b360/health B360 ;;
      data_builder) stop_svc data_builder backend.data_builder.api; start_svc data_builder backend.data_builder.api "$DATA_PORT" /api/v1/data/health DATA_BUILDER ;;
      workspace) stop_svc workspace backend.workspace_v5.api; start_svc workspace backend.workspace_v5.api "$WORKSPACE_PORT" /api/v1/workspace/health WORKSPACE ;;
      admin) stop_svc admin backend.admin.api; start_svc admin backend.admin.api "$ADMIN_PORT" /api/v1/admin/health ADMIN ;;
      scorecard) stop_svc scorecard backend.scorecard_v5.api; start_svc scorecard backend.scorecard_v5.api "$SCORECARD_PORT" /api/v1/scorecard/health SCORECARD ;;
      whatif|playbook|lenses) echo "restart $2: use stop-modules/start-modules (it carries the model key)"; exit 2 ;;
      *) echo "usage: $0 restart ews|b360|data_builder|workspace|scorecard"; exit 2 ;;
    esac ;;
  start-modules) start_modules ;;
  stop-modules)  stop_modules ;;
  start-ews) start_ews ;;
  stop-ews)  stop_ews ;;
  status)
    echo "edition: $EDITION"
    "$V5/ops/cockpit.sh" status
    if in_edition ews; then curl -fsS "http://127.0.0.1:$EWS_PORT/api/v1/ews/health" 2>/dev/null && echo || echo "Early Warning API: down"; fi
    for svc in "b360:$B360_PORT:/api/v1/b360/health" "whatif:$WHATIF_PORT:/api/v1/whatif/health" \
               "data_builder:$DATA_PORT:/api/v1/data/health" "workspace:$WORKSPACE_PORT:/api/v1/workspace/health" \
               "scorecard:$SCORECARD_PORT:/api/v1/scorecard/health" \
               "dealdesk:$DEALDESK_PORT:/api/v1/dealdesk/desk/health" \
               "playbook:$PLAYBOOK_PORT:/api/v1/playbook/health" \
               "lenses:$LENSES_PORT:/api/v1/lenses/health" "admin:$ADMIN_PORT:/api/v1/admin/health" "queries:$QUERIES_PORT:/api/v1/queries/health" \
               "agents:$AGENTS_PORT:/api/v1/agents/health"; do
      IFS=: read -r n p h <<<"$svc"
      in_edition "$n" || continue
      curl -fsS "http://127.0.0.1:$p$h" >/dev/null 2>&1 && echo "$n: up on $p" || echo "$n: down"
    done
    ;;
  *) echo "usage: $0 start|stop|status|start-ews|stop-ews|start-modules|stop-modules"; exit 2 ;;
esac
