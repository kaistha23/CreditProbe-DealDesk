#!/usr/bin/env bash
# R16 v: install Noor's offline neural voice add-on (Kokoro for English, Piper for Arabic). No network needed.
#
#   ops/r16_install_tts.sh                 # into the backend's Python (.venv if present, else python3)
#   PY=/path/to/python ops/r16_install_tts.sh
#   ops/r16_install_tts.sh --pack DIR      # take the model files from a Mac pack folder (e.g. var/r16_tts)
#   ops/r16_install_tts.sh --fetch         # no pack at hand: download the model files first (needs the internet)
#
# 1. pip installs the pinned wheels from vendor/wheels (--no-index: nothing is downloaded).
# 2. checks the model files in var/tts (sha256 against vendor/tts/MANIFEST.tsv), copying them from --pack if given.
# 3. speaks one English and one Arabic line into var/tts_cache, so the first click in the app is quick.
# Then restart the Deal Desk service; Settings -> Voice lists the neural voices. Nothing speaks unless clicked.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

PACK=""; FETCH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pack) PACK="${2:?--pack needs a folder}"; shift 2 ;;
    --fetch) FETCH=1; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

if [ -z "${PY:-}" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY="$(command -v python3)"; fi
fi
VER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "== Python: $PY ($VER, $(uname -s) $(uname -m))"

EXTRA=()
# kokoro-onnx 0.6.1 declares Python < 3.14; it is pure Python and runs on 3.14 (onnxruntime ships cp314 wheels).
[ "$VER" = "3.14" ] && EXTRA+=(--ignore-requires-python)

echo "== 1/3 wheels (offline, vendor/wheels)"
"$PY" -m pip install --no-index --find-links "$ROOT/vendor/wheels" ${EXTRA[@]+"${EXTRA[@]}"} -r "$ROOT/vendor/wheels/requirements-tts.txt"

echo "== 2/3 model files (var/tts)"
if [ -n "$PACK" ]; then "$PY" -m ops.r16_tts_files unpack "$PACK" || true; fi
if [ "$FETCH" = 1 ]; then "$PY" -m ops.r16_tts_files fetch || true; fi
if ! "$PY" -m ops.r16_tts_files verify; then
  echo "STOP: a required model file is missing or wrong. Copy the Mac pack's var/r16_tts folder and run"
  echo "      ops/r16_install_tts.sh --pack var/r16_tts   (or --fetch where the internet is allowed)."
  exit 1
fi

echo "== 3/3 a first line in each language (warms the cache)"
"$PY" - <<'EOF'
from backend.agents_v5.voice import engine
st = engine.status()
print("  engines:", st["engines"], "| model:", st["model"])
for vid, text in (("am_michael", "Good morning. The voice add-on is installed, and it runs on this computer."),
                  ("ar_JO-kareem-medium", "صباح الخير. الصوت يعمل على هذا الجهاز.")):
    v = engine.BY_ID[vid]
    if not st["engines"][v.engine]:
        print(f"  {vid}: not available ({', '.join(st['missing'])})")
        continue
    out = engine.speak(text, vid)
    print(f"  {vid}: {len(out['audio'])} bytes, {'cached' if out['cached'] else 'made'} in {out.get('took', 0)} s")
EOF
echo "== done. Restart the Deal Desk service, then open Settings -> Voice and press Listen."
