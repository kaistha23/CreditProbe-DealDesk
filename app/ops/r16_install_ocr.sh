#!/bin/bash
# R16: install the OCR add-on (rapidocr-onnxruntime) OFFLINE from vendor/wheels into the repo's .venv.
#   ops/r16_install_ocr.sh            install (idempotent) and run a one-line smoke test
#   ops/r16_install_ocr.sh --check    only report whether OCR is importable
# No network is used (--no-index). Wheels: macOS arm64 (Python 3.12, macOS 14+) and Linux x86_64 (Python 3.12).
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5"
PY="${PY:-.venv/bin/python}"
[ -x "$PY" ] || { echo "STOP: $PY not found (run the normal setup first)."; exit 1; }
check() { "$PY" -c "import rapidocr_onnxruntime, cv2, onnxruntime; print('OCR ready: rapidocr', 'onnxruntime', onnxruntime.__version__, 'cv2', cv2.__version__)"; }
if [ "${1:-}" = "--check" ]; then check; exit $?; fi
W="$V5/vendor/wheels"
PKGS=$(grep -v '^#' ops/requirements-ocr.txt | grep -v '^\s*$' | grep -v '^rapidocr')
# shellcheck disable=SC2086
"$PY" -m pip install --no-index --find-links "$W" $PKGS
"$PY" -m pip install --no-index --find-links "$W" --no-deps rapidocr-onnxruntime==1.4.4
check
"$PY" -m backend.dealdesk.intake.ocr --selftest || { echo "OCR self-test failed"; exit 1; }
echo "OCR INSTALLED"
