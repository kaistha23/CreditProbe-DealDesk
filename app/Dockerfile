# CreditProbe AI -- Deal Desk edition, one container.
#
# Runs the same services ops/demo.sh runs on a Mac (Deal Desk API, Core/Workspace, Data Builder, Playbook and
# Policy Docs, Admin, Agents, the Cockpit API) plus the production UI, inside one Linux container.
# Built by the launchers (Start-Windows.bat / Start-Mac.command) through ../docker-compose.yml.
#
# Works on Intel/AMD (amd64) and Apple Silicon / ARM (arm64): every Python wheel is taken from PyPI.

FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NEXT_TELEMETRY_DISABLED=1

# curl/lsof/procps: ops/v5.sh health checks and port checks. fonts-liberation: the UI build's offline fonts.
# libglib2.0-0, libgomp1: OpenCV and ONNX Runtime (OCR of photos and scanned PDFs).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl lsof procps util-linux ca-certificates fonts-liberation \
      libglib2.0-0 libgomp1 tini \
 && rm -rf /var/lib/apt/lists/*

# Node.js 22 from the official image (no npm registry setup needed).
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version

WORKDIR /app

# 1. Python dependencies (cached layer: only the lock files first).
COPY ops/requirements.lock.txt ops/requirements-ocr.txt /app/ops/
RUN python -m venv /app/.venv \
 && /app/.venv/bin/pip install --upgrade pip \
 && /app/.venv/bin/pip install -r ops/requirements.lock.txt \
 && /app/.venv/bin/pip install $(grep -v '^#' ops/requirements-ocr.txt | grep -v '^\s*$' | grep -v '^rapidocr') \
 && /app/.venv/bin/pip install --no-deps rapidocr-onnxruntime==1.4.4

# 2. Frontend dependencies (cached layer).
COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN cd /app/frontend && npm ci --no-audit --no-fund

# 3. The application.
COPY . /app
RUN chmod +x /app/ops/*.sh \
 && sed -i 's/\r$//' /app/ops/*.sh \
 && /app/.venv/bin/python -m backend.dealdesk.intake.ocr --selftest

# 4. The production UI. NEXT_PUBLIC_* service origins are fixed here (http://127.0.0.1:85xx), which is why the
#    compose file publishes the same port numbers on the host.
ENV V5_EDITION=dealdesk
RUN NODE_OPTIONS=--max-old-space-size=3072 /app/ops/r14_build_ui.sh

ENV V5_BIND_HOST=0.0.0.0 \
    V5_UI_PORT=6600 \
    V5_UI_MODE=prod \
    CP_DEMO_PASSWORD_IS_USERNAME=1 \
    CP_USERS_LOCAL=/app/var/USERS_LOCAL.md \
    V5_HEALTH_WAIT_S=900

EXPOSE 6600 8500 8504 8505 8506 8508 8510 8517
VOLUME ["/app/var"]

HEALTHCHECK --interval=20s --timeout=10s --start-period=900s --retries=5 \
  CMD curl -fsS http://127.0.0.1:6600/login >/dev/null && curl -fsS http://127.0.0.1:8508/api/v1/dealdesk/desk/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/ops/docker_entrypoint.sh"]
