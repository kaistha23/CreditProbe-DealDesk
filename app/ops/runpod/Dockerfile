# CreditProbe, Deal Desk edition: the application image (no model inside; the model server is vLLM beside it).
#
#   docker build -f ops/runpod/Dockerfile -t creditprobe-dealdesk .
#   docker run --network host --env-file var/runpod.env -v creditprobe-var:/app/var creditprobe-dealdesk
#
# Not yet built in the cloud session (no Docker there): the first build is a check of this file. The shell path
# (ops/runpod/start_dealdesk.sh on a plain pod) is the one that has run.
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl git lsof tesseract-ocr tesseract-ocr-ara poppler-utils ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN python3.12 -m venv .venv && .venv/bin/pip install --no-cache-dir -r ops/requirements.lock.txt \
    && (ops/r16_install_ocr.sh || echo "OCR add-on skipped") \
    && cd frontend && npm ci --no-audit --no-fund \
    && cd /app && V5_EDITION=dealdesk NEXT_PUBLIC_CP_EDITION=dealdesk ops/r14_build_ui.sh

ENV V5_EDITION=dealdesk V5_UI_PORT=6600 V5_UI_MODE=prod CP_DEMO_PASSWORD_IS_USERNAME=1 \
    CONVO_PROVIDER=openai CONVO_OPENAI_BASE_URL=http://127.0.0.1:8000/v1
EXPOSE 6600
CMD ["bash", "-lc", "ops/v5.sh start && tail -f var/logs/dealdesk.log"]
