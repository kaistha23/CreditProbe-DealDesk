#!/bin/bash
# Deal Desk edition: the integration check after merging the parallel rounds (A, B+G, D, K+P, S+E, W+T).
# Backend suites one directory at a time (memory), the frozen guard, the type check and UI tests, the production
# build, the edition walk, then each round's own walk, against one running stack. One line per result in
# var/verify/summary.txt; full logs beside it. Run from the repo root.
set -u
V5="$(cd "$(dirname "$0")/.." && pwd)"; cd "$V5"
OUT="$V5/var/verify"; mkdir -p "$OUT"; : >"$OUT/summary.txt"
say() { echo "$(date -u +%H:%M:%S) $*" | tee -a "$OUT/summary.txt"; }
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers CP_TEST_PASSWORD=anne

suites="agent_intake graph dealdesk_kp paperws convo_efficiency intelligence_studio dealdesk dealdesk_ui rm_request credit_response
house_style intake proposal_check workspace core playbook admin noor convo model_lab"
for s in $suites; do
  [ -d "tests/v5/$s" ] || { say "SKIP tests/v5/$s (absent)"; continue; }
  timeout 2400 .venv/bin/python -m pytest "tests/v5/$s" -q -p no:warnings -x --timeout=900 \
    --deselect tests/v5/agents/test_dealdesk_committee.py::test_golden_run >"$OUT/pytest_$s.log" 2>&1
  rc=$?; say "pytest tests/v5/$s rc=$rc $(tail -1 "$OUT/pytest_$s.log" | cut -c1-120)"
done
.venv/bin/python ops/frozen_guard.py >"$OUT/frozen.log" 2>&1; say "frozen_guard rc=$? $(head -c 60 "$OUT/frozen.log")"
(cd frontend && npx tsc --noEmit -p tsconfig.json) >"$OUT/tsc.log" 2>&1; say "tsc rc=$? lines=$(wc -l <"$OUT/tsc.log")"
(cd frontend && npm test) >"$OUT/npm.log" 2>&1; say "npm test rc=$? $(grep -E '^# (pass|fail)' "$OUT/npm.log" | tr '\n' ' ')"

ops/r14_build_ui.sh >"$OUT/build.log" 2>&1; say "build rc=$?"
V5_UI_PORT=6600 V5_UI_MODE=prod V5_HEALTH_WAIT_S=900 ops/v5.sh start >"$OUT/start.log" 2>&1; say "start rc=$?"

.venv/bin/python ops/dealdesk_edition_walk.py --out var/walk/integrated_edition >"$OUT/walk_edition.log" 2>&1
say "walk edition rc=$? $(grep -E '^(PASS|FAIL)' "$OUT/walk_edition.log")"
for w in d bg kp se wt a; do
  args=(--ui http://127.0.0.1:6600 --out "var/walk/integrated_$w")
  timeout 2400 .venv/bin/python "ops/round_${w}_walk.py" "${args[@]}" >"$OUT/walk_$w.log" 2>&1
  say "walk round-$w rc=$? $(tail -1 "$OUT/walk_$w.log" | cut -c1-140)"
done
V5_UI_PORT=6600 ops/v5.sh stop >"$OUT/stop.log" 2>&1
git checkout -- data/dealdesk 2>/dev/null
say "DONE"
