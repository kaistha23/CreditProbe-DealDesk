#!/bin/bash
# The Deal Desk edition on a Linux box (RunPod pod, or any Ubuntu with python3.12 and node 22): one command.
#
#   set -a; . var/runpod.env; set +a          (from ops/runpod/env.example)
#   ops/runpod/start_dealdesk.sh              setup once (venv, npm ci, OCR), build the UI for the edition, start
#                                             the services with the gateway from the environment
#   ops/runpod/start_dealdesk.sh stop|status
#
# The UI is http://127.0.0.1:${V5_UI_PORT:-6600} on the pod (reach it over an SSH tunnel:
# `ssh -L 6600:127.0.0.1:6600 root@<pod>`; nothing is exposed on the pod's public interface). The model lab
# (ops/model_lab.py) runs on the pod itself and needs no UI.
set -euo pipefail
V5="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$V5"
export V5_EDITION="${V5_EDITION:-dealdesk}" V5_UI_PORT="${V5_UI_PORT:-6600}" V5_UI_MODE=prod
export CP_DEMO_PASSWORD_IS_USERNAME="${CP_DEMO_PASSWORD_IS_USERNAME:-1}"
case "${1:-start}" in
  stop)   exec ops/v5.sh stop ;;
  status) ops/v5.sh status; echo; echo "gateway: $(curl -fsS "http://127.0.0.1:${DEALDESK_API_PORT:-8508}/api/v1/dealdesk/desk/health" 2>/dev/null || echo 'Deal Desk down')" ;;
  start)
    [ -x .venv/bin/python ] && [ -d frontend/node_modules ] || ops/setup_linux.sh
    ops/r14_build_ui.sh --if-needed
    if [ "${CONVO_PROVIDER:-auto}" = "openai" ] || [ -n "${CONVO_OPENAI_BASE_URL:-}" ]; then
      curl -fsS -m 5 "${CONVO_OPENAI_BASE_URL:-http://127.0.0.1:8000/v1}/models" >/dev/null 2>&1 \
        || echo "WARNING: no model server answers at ${CONVO_OPENAI_BASE_URL:-http://127.0.0.1:8000/v1} yet; Deal Desk will fall back to the deterministic planner until it does (start ops/runpod/vllm_qwen38_27b.sh)."
    fi
    ops/v5.sh start
    echo
    echo "Deal Desk edition up. Gateway: $(curl -fsS "http://127.0.0.1:${DEALDESK_API_PORT:-8508}/api/v1/dealdesk/desk/health" | python3 -c 'import json,sys; a=json.load(sys.stdin)["assistant"]; print(a)')"
    echo "UI: http://127.0.0.1:$V5_UI_PORT (SSH tunnel). Lab: .venv/bin/python ops/model_lab.py run --experiment ${CONVO_EXPERIMENT:-<name>}"
    ;;
  *) echo "usage: $0 start|stop|status"; exit 2 ;;
esac
