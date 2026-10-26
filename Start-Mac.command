#!/bin/bash
# CreditProbe AI - Deal Desk edition: start on a Mac.
# Uses Docker Desktop when it is installed (recommended). Without Docker it installs and runs natively, which needs
# Python 3.12 and Node.js 22 (Homebrew: brew install python@3.12 node@22).
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/opt/node@22/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

echo ""
echo " CreditProbe AI - Deal Desk edition"
echo " ----------------------------------"
echo ""

ready_banner() {
  echo ""
  echo " READY:  http://127.0.0.1:6600"
  echo " Sign in as  nawaf.alotaibi  (password nawaf.alotaibi)  - Relationship Manager"
  echo "       or  sara.aldosari   (password sara.aldosari)   - Credit Analyst"
  echo ""
  open "http://127.0.0.1:6600"
}

wait_ready() {   # wait_ready <seconds>
  for _ in $(seq 1 $(( $1 / 5 ))); do
    if curl -fs -o /dev/null http://127.0.0.1:8508/api/v1/dealdesk/desk/health && curl -fs -o /dev/null http://127.0.0.1:6600/login; then
      return 0
    fi
    sleep 5
  done
  return 1
}

if [ ! -f settings.env ]; then
  cp settings.env.example settings.env
  echo " First run: TextEdit opens settings.env."
  echo " Paste your Anthropic API key after ANTHROPIC_API_KEY= , save (Cmd+S) and close the window."
  echo " No key? Just close it: the app still runs, without the AI drafting and chat."
  open -e settings.env
  read -r -p " Press Return here when you have saved and closed settings.env. " _
fi

# ---------------------------------------------------------------- Docker route
if command -v docker >/dev/null 2>&1 || [ -d /Applications/Docker.app ]; then
  if ! docker info >/dev/null 2>&1; then
    echo " Starting Docker Desktop ..."
    open -a Docker 2>/dev/null
    for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
  fi
  if docker info >/dev/null 2>&1; then
    echo " Building and starting. The FIRST run downloads and builds everything: 10-20 minutes."
    echo " Later starts take about a minute."
    echo ""
    docker compose up -d --build || { echo " The build or start failed: see the messages above."; read -r -p " Press Return to close." _; exit 1; }
    echo ""
    echo " Waiting for CreditProbe to finish preparing its data (first start: 3-10 minutes) ..."
    if wait_ready 1200; then ready_banner; else
      echo " It is taking longer than expected. Recent log lines:"; docker compose logs --tail 40
      echo " Open http://127.0.0.1:6600 in a few minutes, or run Stop-Mac.command and then Start-Mac.command."
    fi
    echo " You can close this window. CreditProbe keeps running until you run Stop-Mac.command."
    exit 0
  fi
  echo " Docker Desktop did not start. Trying the native route instead."
fi

# ---------------------------------------------------------------- native route (no Docker)
cd "$HERE/app" || exit 1
PY="$(command -v python3.12 || ls /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 2>/dev/null | head -1)"
if [ -z "$PY" ] || ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo " Neither Docker Desktop nor Python 3.12 + Node.js 22 were found."
  echo " Easiest: install Docker Desktop (https://www.docker.com/products/docker-desktop/), open it once,"
  echo " then double-click Start-Mac.command again."
  echo " Or, with Homebrew:  brew install python@3.12 node@22"
  open "https://www.docker.com/products/docker-desktop/"
  read -r -p " Press Return to close." _; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo " First run (native): installing Python packages. This takes 5-10 minutes ..."
  "$PY" -m venv .venv || exit 1
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r ops/requirements.lock.txt || { echo " pip install failed."; read -r -p " Press Return to close." _; exit 1; }
  .venv/bin/pip install -q $(grep -v '^#' ops/requirements-ocr.txt | grep -v '^\s*$' | grep -v '^rapidocr') \
    && .venv/bin/pip install -q --no-deps rapidocr-onnxruntime==1.4.4 \
    || echo " WARNING: OCR could not be installed: photos and scans will not be read (Word, PDF and Excel will)."
fi
if [ ! -x frontend/node_modules/.bin/next ]; then
  echo " Installing the user interface packages ..."
  ( cd frontend && npm ci --no-audit --no-fund ) || { echo " npm ci failed."; read -r -p " Press Return to close." _; exit 1; }
fi

KEY="$(sed -n 's/^ANTHROPIC_API_KEY=//p' "$HERE/settings.env" | tr -d '\r\n" ')"
if printf '%s' "$KEY" | grep -qE '^sk-ant-'; then export COCKPIT_ANTHROPIC_API_KEY="$KEY"; fi
unset KEY
export V5_EDITION=dealdesk V5_UI_PORT=6600 V5_UI_MODE=prod CP_DEMO_PASSWORD_IS_USERNAME=1 \
       CP_USERS_LOCAL="$HERE/app/var/USERS_LOCAL.md" V5_HEALTH_WAIT_S=900
echo " Starting (the first start builds the interface and prepares the data: 5-15 minutes) ..."
ops/demo.sh start
if wait_ready 600; then ready_banner; else echo " Not ready yet: see app/var/logs for details."; fi
echo " You can close this window. CreditProbe keeps running until you run Stop-Mac.command."
