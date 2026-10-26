#!/bin/bash
# The whole comparison in one go: the Opus baseline, then the open model, then the report.
#
#   CONVO_ANTHROPIC_API_KEY=sk-ant-... ops/runpod/lab.sh baseline            # Deal Desk on Opus -> var/model_lab/opus-baseline
#   ops/runpod/lab.sh candidate qwen38-27b-bf16                              # Deal Desk on the vLLM model -> var/model_lab/<name>
#   ops/runpod/lab.sh compare qwen38-27b-bf16 [--judge]                      # the report, var/model_lab/compare_opus-baseline_vs_<name>.md
#
# Each run restarts the Deal Desk service with the right gateway (the experiment name goes into every telemetry
# row), runs ops/model_lab.py over the golden questions, drafts and bank forms, and leaves the service up.
# STAGES and DEALS narrow a run (e.g. STAGES=thread,draft DEALS=DD-01,R12-TWA).
set -euo pipefail
V5="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$V5"
export V5_EDITION="${V5_EDITION:-dealdesk}" V5_UI_PORT="${V5_UI_PORT:-6600}" V5_UI_MODE=prod
STAGES="${STAGES:-thread,desk,draft,bankform}"
DEALS="${DEALS:-}"
restart_dealdesk() {
  ops/v5.sh stop-modules >/dev/null 2>&1 || true
  ops/v5.sh start-modules
}
case "${1:-}" in
  baseline)
    [ -n "${CONVO_ANTHROPIC_API_KEY:-}" ] || { echo "STOP: CONVO_ANTHROPIC_API_KEY is needed for the Opus baseline."; exit 1; }
    export CONVO_PROVIDER=anthropic CONVO_MODEL="${CONVO_MODEL:-claude-opus-5}" CONVO_EXPERIMENT=opus-baseline
    unset CONVO_OPENAI_BASE_URL
    restart_dealdesk
    .venv/bin/python ops/model_lab.py run --experiment opus-baseline --stages "$STAGES" ${DEALS:+--deals "$DEALS"}
    ;;
  candidate)
    NAME="${2:?name, e.g. qwen38-27b-bf16}"
    export CONVO_PROVIDER=openai CONVO_EXPERIMENT="$NAME"
    export CONVO_OPENAI_BASE_URL="${CONVO_OPENAI_BASE_URL:-http://127.0.0.1:8000/v1}"
    curl -fsS -m 10 "$CONVO_OPENAI_BASE_URL/models" >/dev/null || { echo "STOP: no model server at $CONVO_OPENAI_BASE_URL (start ops/runpod/vllm_qwen38_27b.sh)."; exit 1; }
    restart_dealdesk
    .venv/bin/python ops/model_lab.py run --experiment "$NAME" --stages "$STAGES" ${DEALS:+--deals "$DEALS"}
    ;;
  compare)
    NAME="${2:?name}"; shift 2
    .venv/bin/python ops/model_lab.py compare --baseline opus-baseline --candidate "$NAME" "$@"
    ;;
  *) echo "usage: $0 baseline | candidate <name> | compare <name> [--judge]"; exit 2 ;;
esac
