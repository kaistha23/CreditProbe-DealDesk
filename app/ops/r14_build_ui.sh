#!/bin/bash
# PLAN_R14 Session U (K8): the production UI build for the Mac demo (and the cloud walk-through).
#
#   ops/r14_build_ui.sh            build frontend/.next for `next start` (no development overlay can appear)
#   ops/r14_build_ui.sh --if-needed   build only when the source commit or the service origins changed
#
# NEXT_PUBLIC_* are inlined at build time, so the service origins are taken from the same port variables as
# ops/v5.sh (defaults 8500–8517). Uses the existing frontend/node_modules only: nothing is installed or upgraded
# (N9: no new runtime packages on the Mac). Fonts: the real Google fonts when fonts.googleapis.com answers, else
# the offline Liberation faces (ops/next_font_offline.cjs; the cloud container). A stamp in
# frontend/.next/r14_build.json records the commit and origins the build was made for.
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5/frontend"

[ -x node_modules/.bin/next ] || { echo "STOP: frontend/node_modules has no next; run the usual setup first (this script installs nothing)."; exit 1; }

H=127.0.0.1
export NEXT_PUBLIC_COCKPIT_V4_API="http://$H:${V5_COCKPIT_API_PORT:-8500}"
export NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_COCKPIT_V4_API"
export NEXT_PUBLIC_EWS_API="http://$H:${EWS_API_PORT:-8501}"
export NEXT_PUBLIC_B360_API="http://$H:${B360_API_PORT:-8502}"
export NEXT_PUBLIC_WHATIF_API="http://$H:${WHATIF_API_PORT:-8503}"
export NEXT_PUBLIC_DATA_API="http://$H:${DATA_BUILDER_PORT:-8504}"
export NEXT_PUBLIC_WORKSPACE_API="http://$H:${WORKSPACE_API_PORT:-8505}"
export NEXT_PUBLIC_PLAYBOOK_API="http://$H:${PLAYBOOK_API_PORT:-8506}"
export NEXT_PUBLIC_SCORECARD_API="http://$H:${SCORECARD_API_PORT:-8507}"
export NEXT_PUBLIC_DEALDESK_API="http://$H:${DEALDESK_API_PORT:-8508}"
export NEXT_PUBLIC_LENSES_API="http://$H:${LENSES_API_PORT:-8509}"
export NEXT_PUBLIC_ADMIN_API="http://$H:${ADMIN_API_PORT:-8510}"
export NEXT_PUBLIC_QUERIES_API="http://$H:${QUERIES_API_PORT:-8516}"
export NEXT_PUBLIC_AGENTS_API="http://$H:${AGENTS_API_PORT:-8517}"
# The edition is inlined too (src/lib/navigation.ts, next.config.ts): dealdesk (default) or full. V5_EDITION is
# ops/v5.sh's variable; it decides the build as well, so the UI and the services agree.
export NEXT_PUBLIC_CP_EDITION="${NEXT_PUBLIC_CP_EDITION:-${V5_EDITION:-dealdesk}}"

# The stamp is the last commit that touched the frontend (not HEAD): an ops or backend commit does not rebuild the UI.
SHA="$(git -C "$V5" log -1 --format=%H -- frontend 2>/dev/null || git -C "$V5" rev-parse HEAD 2>/dev/null || echo unknown)"
DIRTY="$( (git -C "$V5" status --porcelain -- frontend 2>/dev/null || true) | (grep -v '^??' || true) | wc -l | tr -d ' ')"
ORIGINS="$(env | grep '^NEXT_PUBLIC_' | sort | tr '\n' ' ')"
STAMP=".next/r14_build.json"

if [ "${1:-}" = "--if-needed" ] && [ -f "$STAMP" ] && [ -f .next/BUILD_ID ] && [ "$DIRTY" = "0" ]; then
  # Current when the stamped commit already contains the last frontend commit (the stamp may be a later commit).
  STAMPED="$(sed -n 's/.*"sha": "\([0-9a-f]*\)".*/\1/p' "$STAMP" | head -1)"
  if [ -n "$STAMPED" ] && { [ "$STAMPED" = "$SHA" ] || git -C "$V5" merge-base --is-ancestor "$SHA" "$STAMPED" 2>/dev/null; } \
     && grep -qF "\"origins\": \"$ORIGINS\"" "$STAMP"; then
    echo "UI build is current ($SHA, built at $STAMPED)."; exit 0
  fi
fi

FONT_ENV=()
if ! curl -fsS -m 5 -o /dev/null "https://fonts.googleapis.com/css2?family=Geist:wght@100..900&display=swap" 2>/dev/null; then
  mkdir -p "$V5/var/fonts"
  for f in LiberationSans-Regular.ttf LiberationMono-Regular.ttf; do
    [ -f "$V5/var/fonts/$f" ] || cp "/usr/share/fonts/truetype/liberation/$f" "$V5/var/fonts/$f" 2>/dev/null || true
  done
  if [ -f "$V5/var/fonts/LiberationSans-Regular.ttf" ]; then
    FONT_ENV=(NEXT_FONT_GOOGLE_MOCKED_RESPONSES="$V5/ops/next_font_offline.cjs")
    echo "Google fonts unreachable: building with the offline faces."
  fi
fi

echo "Building the production UI for $SHA ..."
env ${FONT_ENV[@]+"${FONT_ENV[@]}"} NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=3072}" NEXT_TELEMETRY_DISABLED=1 npx --no-install next build --webpack
printf '{"sha": "%s", "dirty_files": %s, "built_at": "%s", "origins": "%s"}\n' "$SHA" "$DIRTY" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ORIGINS" >"$STAMP"
echo "UI build ready: frontend/.next (serve with ops/demo.sh start, i.e. next start)."
