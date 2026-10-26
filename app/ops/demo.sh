#!/bin/bash
# PLAN_R14 Session U (K8): the Mac demo launcher — every service, and the UI from the production build.
#
#   ops/demo.sh start      build the UI if the commit changed (ops/r14_build_ui.sh --if-needed), then start the
#                          services and serve the UI with `next start` (production: no development overlay, no
#                          "N · Issues" badge can appear)
#   ops/demo.sh stop       stop everything ops/v5.sh started
#   ops/demo.sh status     what is up
#   ops/demo.sh build      force a fresh UI build
#
# The UI port defaults to 6600 (Anne's demo URL http://127.0.0.1:6600); set V5_UI_PORT to change it. The other
# ports are ops/v5.sh's. Nothing is installed: the build uses frontend/node_modules as it is (N9).
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
export V5_UI_PORT="${V5_UI_PORT:-6600}"
export V5_UI_MODE=prod
export CP_DEMO_PASSWORD_IS_USERNAME="${CP_DEMO_PASSWORD_IS_USERNAME:-1}"   # R14 x (K3): a new demo store under var/ seeds password = username

case "${1:-start}" in
  build)  "$V5/ops/r14_build_ui.sh" ;;
  start)
    "$V5/ops/r14_build_ui.sh" --if-needed
    # R16 i: the OCR add-on for photographed pages, offline from vendor/wheels, once (never stops the demo)
    "$V5/ops/r16_install_ocr.sh" --check >/dev/null 2>&1 || "$V5/ops/r16_install_ocr.sh" || echo "WARNING: OCR add-on not installed: photos cannot be read (Word and PDF still can)"
    "$V5/ops/v5.sh" start
    echo "Demo: http://127.0.0.1:$V5_UI_PORT (production build)"
    ;;
  stop)   "$V5/ops/v5.sh" stop ;;
  status) "$V5/ops/v5.sh" status ;;
  *) echo "usage: $0 start|stop|status|build"; exit 2 ;;
esac
