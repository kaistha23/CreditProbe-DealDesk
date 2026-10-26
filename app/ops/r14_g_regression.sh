#!/bin/bash
# PLAN_R14 Session G (from ops/r13_m_regression.sh): the full backend regression, one suite after the other (the container has 7 GB; suites run alone).
#   ops/r13_m_regression.sh [suite ...]     results in var/pytest/r13_m/<suite>.log and a summary line per suite
set -u
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5"
OUT=var/pytest/r14_g; mkdir -p "$OUT"
PY=.venv/bin/python
SUITES=(
  "g:tests/v5/panels_g"
  "cockpit:tests/cockpit_v4"
  "queries:tests/v5/queries"
  "r13:tests/v5/dealdesk/test_r13_fin_quality.py tests/v5/dealdesk/test_r13_ib.py tests/v5/dealdesk/test_r13_intel_approval.py tests/v5/dealdesk/test_r13_landing_materiality.py tests/v5/scenarios tests/v5/intel tests/v5/intel_network tests/intel_portfolio tests/v5/lenses/test_r13_ratios.py"
  "r12:tests/v5/dealdesk/test_r12_ui_shell.py tests/v5/dealdesk/test_r12_review.py tests/v5/dealdesk/test_r12_group.py tests/v5/dealdesk/test_r12_stress.py tests/v5/dealdesk/test_r12_papers.py tests/v5/dealdesk/test_r12_papers_data.py tests/v5/dealdesk/test_r12_params.py tests/v5/dealdesk/test_r12_book.py tests/v5/dealdesk/test_r12_products.py tests/v5/dealdesk/test_r12_try.py tests/v5/dealdesk/test_r12_calibration.py tests/v5/noor"
  "lineage:backend/tests/test_r12_lineage.py"
  "dealdesk:tests/v5/dealdesk --ignore-glob=*test_r12_* --ignore-glob=*test_r13_*"
  "dealdesk_ui:tests/v5/dealdesk_ui"
  "dealdesk_legacy:tests/dealdesk"
  "house_style:tests/v5/house_style"
  "agents:tests/v5/agents"
  "agents_ews:tests/v5/agents_ews"
  "agents_whatif:tests/v5/agents_whatif"
  "agents_lenses:tests/v5/agents_lenses"
  "ews:tests/v5/ews"
  "whatif:tests/v5/whatif tests/v5/convo/test_whatif_mixed.py"
  "lenses:tests/v5/lenses"
  "sync:tests/v5/test_sync_*.py"
  "data_builder:tests/v5/data_builder"
  "b360:tests/v5/b360"
)
want=("$@")
for entry in "${SUITES[@]}"; do
  name="${entry%%:*}"; args="${entry#*:}"
  if [ ${#want[@]} -gt 0 ] && [[ ! " ${want[*]} " == *" $name "* ]]; then continue; fi
  start=$(date +%s)
  # shellcheck disable=SC2086
  $PY -m pytest -q -p no:cacheprovider --junitxml="$OUT/$name.xml" $args > "$OUT/$name.log" 2>&1
  rc=$?
  echo "$(date -u +%H:%M) $name rc=$rc $(( $(date +%s) - start ))s :: $($PY -c "import sys,xml.etree.ElementTree as E;r=E.parse(sys.argv[1]).getroot();r=r if r.tag=='testsuite' else r[0];print('tests',r.get('tests'),'failures',r.get('failures'),'errors',r.get('errors'),'skipped',r.get('skipped'))" "$OUT/$name.xml" 2>/dev/null)" | tee -a "$OUT/summary.txt"
done
