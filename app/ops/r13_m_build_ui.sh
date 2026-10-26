#!/bin/bash
# PLAN_R13 Session M: production UI build for the cloud walk-through, with the service origins inlined
# (NEXT_PUBLIC_* are read at build time; without NEXT_PUBLIC_COCKPIT_V4_API the home falls back to the pre-V4 page).
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5/frontend"
export NEXT_PUBLIC_COCKPIT_V4_API=http://127.0.0.1:8500 NEXT_PUBLIC_API_URL=http://127.0.0.1:8500
export NEXT_PUBLIC_EWS_API=http://127.0.0.1:8501 NEXT_PUBLIC_B360_API=http://127.0.0.1:8502 NEXT_PUBLIC_WHATIF_API=http://127.0.0.1:8503
export NEXT_PUBLIC_DATA_API=http://127.0.0.1:8504 NEXT_PUBLIC_WORKSPACE_API=http://127.0.0.1:8505 NEXT_PUBLIC_SCORECARD_API=http://127.0.0.1:8507
export NEXT_PUBLIC_DEALDESK_API=http://127.0.0.1:8508 NEXT_PUBLIC_PLAYBOOK_API=http://127.0.0.1:8506 NEXT_PUBLIC_LENSES_API=http://127.0.0.1:8509
export NEXT_PUBLIC_ADMIN_API=http://127.0.0.1:8510 NEXT_PUBLIC_QUERIES_API=http://127.0.0.1:8516 NEXT_PUBLIC_AGENTS_API=http://127.0.0.1:8517
mkdir -p "$V5/var/fonts"
for f in LiberationSans-Regular.ttf LiberationMono-Regular.ttf; do
  [ -f "$V5/var/fonts/$f" ] || cp "/usr/share/fonts/truetype/liberation/$f" "$V5/var/fonts/$f"
done
NEXT_FONT_GOOGLE_MOCKED_RESPONSES="$V5/ops/next_font_offline.cjs" NODE_OPTIONS=--max-old-space-size=3072 npx next build --webpack
