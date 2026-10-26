# The Deal Desk edition on RunPod: the model lab

Goal: run CreditProbe (Deal Desk edition) on a pod, once on Opus and once on Qwen3.8-27B served by vLLM, over the same
deals, and get one report with the quality and the tokens and time of each. Synthetic and anonymised data only on the
pod (the demo books and customers in this repo are synthetic; no SIB document goes to RunPod).

## Pod

| Model | GPU | Template | Disk |
|---|---|---|---|
| Qwen3.8-27B bf16 (≈ 54 GB) | 1 × H100 80GB or A100 80GB (H200 141GB for more KV cache) | RunPod PyTorch 2.x (CUDA 12.x, Ubuntu 22.04) | 150 GB volume |
| Qwen3.8-27B-FP8 (≈ 28 GB) | 1 × H100 / A100 80GB | same | 100 GB |
| GLM-5.3-Flash FP8 (the "go big" option) | 2 × H200 141GB, or 4 × H100 80GB | same | 400 GB |

Expose nothing publicly: SSH only (`ssh -L 6600:127.0.0.1:6600 root@<pod>` to see the UI from your laptop).

## Once, on the pod

```bash
apt-get update && apt-get install -y python3.12 python3.12-venv git lsof curl tesseract-ocr poppler-utils
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs
git clone -b dealdesk-edition https://github.com/tuhinchatterjee/creditprobe-v5 /workspace/creditprobe-v5
cd /workspace/creditprobe-v5
ops/setup_linux.sh                                     # venv, locked deps, OCR add-on, Playwright, npm ci
pip install -U vllm                                    # the pod's own python; Qwen3.8 needs a recent vLLM
cp ops/runpod/env.example var/runpod.env && nano var/runpod.env    # the gateway; CONVO_EXPERIMENT per run
```

## Serve the model

```bash
ops/runpod/vllm_qwen38_27b.sh               # bf16; or QUANT=fp8 …; MTP=1 … for speculative decoding
curl -s http://127.0.0.1:8000/v1/models     # must list the served model before the next step
```

## Start CreditProbe and run the lab

```bash
set -a; . var/runpod.env; set +a
ops/runpod/start_dealdesk.sh                # builds the UI for the edition once, starts the services, prints the gateway
export CONVO_ANTHROPIC_API_KEY=sk-ant-...   # for the baseline and the judge only; environment, never a file
ops/runpod/lab.sh baseline                  # Deal Desk on Opus         -> var/model_lab/opus-baseline
ops/runpod/lab.sh candidate qwen38-27b-bf16 # Deal Desk on the vLLM model -> var/model_lab/qwen38-27b-bf16
ops/runpod/lab.sh compare qwen38-27b-bf16 --judge
cat var/model_lab/compare_opus-baseline_vs_qwen38-27b-bf16.md
```

Each candidate is a name and a vLLM start: `QUANT=fp8 ops/runpod/vllm_qwen38_27b.sh` then
`CONVO_OPENAI_QUANT=fp8 ops/runpod/lab.sh candidate qwen38-27b-fp8`; `MTP=1` for the speculative-decoding timing;
`CONVO_OPENAI_THINKING=on` for the thinking variant (more reasoning tokens, slower). `STAGES=thread,draft` or
`DEALS=DD-01,R12-TWA` narrow a run while tuning.

What to read in the report: the validation pass rate (every figure traced) and the figure overlap first (an open
model that invents a figure is caught by the validator and the answer loses the sentence; the overlap says how much
survived), then the model-written draft sections and their rejection reasons, then tokens and model time by stage
(what the Mac box will have to do), then the judge's faithfulness and preference.

## What the pod does not measure

Mac latency. The pod gives tokens per call per stage; the Mac's time is tokens ÷ the Mac's measured speed for that
model and quant (prefill and generation differ). One day on real Apple hardware (an M5 Max MacBook Pro with
llama.cpp or MLX, `CONVO_OPENAI_BASE_URL=http://127.0.0.1:8080/v1`) settles the box.

## Telemetry while it runs

`curl -s http://127.0.0.1:8508/api/v1/dealdesk/desk/telemetry/summary?by=experiment,purpose | python3 -m json.tool`,
or the CSV at `/api/v1/dealdesk/desk/telemetry/export.csv`. Files: `var/convo/llm_calls.jsonl`,
`var/convo/llm_telemetry.sqlite`, `var/convo/agent_runs.jsonl`.

## Container (optional)

`ops/runpod/Dockerfile` builds an image with the app ready (no model inside); vLLM runs as its own container or on the
host. It has not been built in the cloud session (no Docker there), so treat the first build as a check of the file.
