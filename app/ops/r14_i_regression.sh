#!/bin/bash
# R14 i: the checks session i runs before a push (services stopped: 8 GB container).
# Summary in var/pytest/r14_i/summary.txt.
cd "$(dirname "$0")/.." || exit 1
S=var/pytest/r14_i; mkdir -p $S; : > $S/summary.txt
run() { name=$1; shift; timeout 4000 .venv/bin/python -m pytest -q -p no:warnings "$@" > $S/$name.log 2>&1; echo "$name exit=$? $(grep -cE 'PASSED|FAILED' $S/$name.log >/dev/null; tail -3 $S/$name.log | tr '\n' ' ')" >> $S/summary.txt; }
run intel tests/v5/intel tests/v5/intel_network tests/intel_portfolio
run lineage backend/tests/test_r12_lineage.py
run dealdesk tests/v5/dealdesk
.venv/bin/python -m backend.dealdesk.data.build --check > $S/build_check.log 2>&1; echo "build_check exit=$? $(tail -1 $S/build_check.log)" >> $S/summary.txt
.venv/bin/python ops/frozen_guard.py > $S/frozen.log 2>&1; echo "frozen exit=$? $(tail -1 $S/frozen.log)" >> $S/summary.txt
(cd frontend && npm test > ../$S/npm.log 2>&1); echo "npm exit=$? $(grep -E '^# (pass|fail)' $S/npm.log | tr '\n' ' ')" >> $S/summary.txt
echo DONE >> $S/summary.txt
