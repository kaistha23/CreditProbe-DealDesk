#!/bin/bash
# vLLM serving GLM-5.3-Flash (320B total / 18B active, MIT) for the "go big" comparison: 2x H200 141GB (bf16 does not
# fit; use the FP8 checkpoint) or 4x H100 80GB. The parser names below are vLLM's for the GLM-4.5/5 family; check
# `vllm serve --help | grep -A3 tool-call-parser` on the pod's vLLM version and adjust PARSER if the name moved.
set -euo pipefail
V5="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$V5/var/logs"
MODEL="${MODEL:-zai-org/GLM-5.3-Flash-FP8}"
SERVED="${SERVED:-GLM-5.3-Flash}"
TP="${TP:-2}"
MAXLEN="${MAXLEN:-65536}"
PARSER="${PARSER:-glm45}"
exec vllm serve "$MODEL" --served-model-name "$SERVED" --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size "$TP" --max-model-len "$MAXLEN" --gpu-memory-utilization "${UTIL:-0.90}" \
  --enable-auto-tool-choice --tool-call-parser "$PARSER" --reasoning-parser "$PARSER" --max-num-seqs 8 \
  2>&1 | tee "$V5/var/logs/vllm.log"
