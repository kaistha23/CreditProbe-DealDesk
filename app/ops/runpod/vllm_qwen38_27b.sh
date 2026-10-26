#!/bin/bash
# vLLM serving Qwen3.8-27B for the Deal Desk edition (one 80 GB GPU: H100 / A100 80GB / H200).
#
#   ops/runpod/vllm_qwen38_27b.sh                 bf16 weights (≈ 54 GB) on one 80 GB GPU
#   QUANT=fp8 ops/runpod/vllm_qwen38_27b.sh       Qwen/Qwen3.8-27B-FP8 (≈ 28 GB): more KV cache, 2 RMs' worth of context
#   MTP=1 ops/runpod/vllm_qwen38_27b.sh           multi-token prediction (the model's own speculative decoding), faster output
#
# The model card (huggingface.co/Qwen/Qwen3.8-27B, Apache 2.0, 262K context): thinking is on by default and is turned
# off per request by chat_template_kwargs.enable_thinking=false, which backend/convo/openai_provider.py sends.
# Tool calls: --tool-call-parser qwen3_xml (qwen3_coder is the same parser) with --enable-auto-tool-choice; the
# reasoning parser keeps any <think> block out of the content. Logs to var/logs/vllm.log; the API is
# http://127.0.0.1:8000/v1 (the gateway's default). vLLM >= 0.11 with Qwen3.8 support; `pip install -U vllm`.
set -euo pipefail
V5="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$V5/var/logs"
QUANT="${QUANT:-bf16}"
case "$QUANT" in
  fp8)  MODEL="${MODEL:-Qwen/Qwen3.8-27B-FP8}" ;;
  *)    MODEL="${MODEL:-Qwen/Qwen3.8-27B}" ;;
esac
SERVED="${SERVED:-$MODEL}"
MAXLEN="${MAXLEN:-65536}"            # 64K per request is enough for every Deal Desk call; raise for whole packs
UTIL="${UTIL:-0.90}"
TP="${TP:-1}"
EXTRA=()
if [ "${MTP:-0}" = "1" ]; then EXTRA+=(--speculative-config '{"method": "mtp", "num_speculative_tokens": 1}'); fi

echo "vLLM: $MODEL (quant $QUANT) served as $SERVED, max-model-len $MAXLEN, tp $TP"
exec vllm serve "$MODEL" \
  --served-model-name "$SERVED" \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size "$TP" \
  --max-model-len "$MAXLEN" \
  --gpu-memory-utilization "$UTIL" \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml \
  --reasoning-parser qwen3 \
  --max-num-seqs 16 \
  "${EXTRA[@]}" 2>&1 | tee "$V5/var/logs/vllm.log"
