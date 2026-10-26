#!/bin/bash
# The Early Warning story's regeneration path (PLAN_R5 Session E, docs/v5/EWS_STORY.md), in order:
#   1. the corporate book: story(original) x 0.01            ops/ews_story_book.py
#   2. the rescale reconciliation, rerun on story(original)   ops/reconcile_rescale.py
#   3. Bureau and Open Banking, with the story groups         backend/ext_domains/build.py
#   4. the Early Warning releases, rule set gw-ews-1.3.0      backend/ews_domain/build_packages.py
#   5. the story check (targets, constraints, the story)      ops/ews_story_calibration.py --check
#   6. downstream domains read from the books                 What-If, Scorecard
#   7. Deal Desk: its domain and the golden workbook inputs
# Deterministic: a rerun writes the same bytes.
set -euo pipefail
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5"
PY=.venv/bin/python
$PY ops/ews_story_book.py > var/logs/ews_story_book.log
$PY ops/reconcile_rescale.py | tail -1
$PY backend/ext_domains/build.py > /dev/null
$PY backend/ews_domain/build_packages.py > var/logs/ews_build_packages.log
$PY ops/ews_story_calibration.py --check > var/logs/ews_story_check.json
echo "story check PASS"
$PY ops/whatif_build_domain.py | tail -1
PYTHONPATH=. $PY backend/scorecard_v5/domain/build.py | tail -1
# Deal Desk reads the book at 2026Q2 (portfolio EL, segment PD profiles): its domain and the golden
# workbook's inputs follow; the workbook's results are recomputed by its own formulas (LibreOffice).
$PY ops/dealdesk_build.py | tail -1
$PY ops/dealdesk_golden.py | tail -1
