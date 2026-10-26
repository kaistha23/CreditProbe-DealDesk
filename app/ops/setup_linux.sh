#!/bin/bash
# CreditProbe v5 -- one-time environment setup on Linux (cloud session).
#
#   ops/setup_linux.sh          create .venv, install the locked Python deps,
#                               Playwright (browser venv = .venv), npm ci
#
# The Mac uses /opt/homebrew Python 3.12 and a separate workspace venv for
# Playwright (HANDOFF.md, "Mac-only pieces"). Here both live in .venv and the
# gate is pointed at it through BROWSER_PY. Nothing outside the repo is
# written except pip/npm caches. No secret is read or written: export
# COCKPIT_ANTHROPIC_API_KEY in the environment if Ask is needed.
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5"
mkdir -p var/run var/logs var/pytest

PY312="$(command -v python3.12 || true)"
[ -n "$PY312" ] || { echo "STOP: python3.12 not found (v5 is locked to 3.12)."; exit 1; }

if [ ! -x .venv/bin/python ]; then
  "$PY312" -m venv .venv
fi
.venv/bin/pip install -q --progress-bar off --upgrade pip
.venv/bin/pip install -q --progress-bar off -r ops/requirements.lock.txt
# R16 (i): the OCR add-on from vendor/wheels, offline (photographed pages); never fatal to the setup
ops/r16_install_ocr.sh >/dev/null 2>&1 || echo "WARNING: OCR add-on not installed (ops/r16_install_ocr.sh)"
# Playwright for the browser smoke test and the UAT sweep. The container has a
# Chromium under /opt/pw-browsers; do not download another.
.venv/bin/pip install -q --progress-bar off "playwright==1.56.0"
if [ -d /opt/pw-browsers ]; then
  echo "Playwright browsers: /opt/pw-browsers (preinstalled)"
else
  PLAYWRIGHT_BROWSERS_PATH="$V5/var/pw-browsers" .venv/bin/python -m playwright install chromium
fi

( cd frontend && npm ci --no-audit --no-fund )

for tool in lsof curl node; do
  command -v "$tool" >/dev/null || echo "WARNING: $tool not found; ops/v5.sh needs it."
done

echo
echo "SETUP COMPLETE"
echo "  start:  ops/v5.sh start      (UI 5500, Cockpit API 8500, EWS API 8501)"
echo "  gate:   BROWSER_PY=.venv/bin/python .venv/bin/python -m ops.gate ews"
echo "  sweep:  .venv/bin/python ops/uat_sweep.py"
