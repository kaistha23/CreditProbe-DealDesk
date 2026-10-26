#!/bin/bash
# Anne: pull a v5 branch from GitHub and open it for UAT.
#   ~/CreditProbe_Workspace/v5/ops/uat_pull.sh            # v5/main (accepted Early Warning)
#   ~/CreditProbe_Workspace/v5/ops/uat_pull.sh v5/next    # the next integration
set -euo pipefail
BRANCH="${1:-v5/main}"
V5="$(cd "$(dirname "$0")/.." && pwd)"
cd "$V5"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "STOP: this checkout has uncommitted changes. Nothing was pulled."; git status --short --untracked-files=no; exit 1
fi
git fetch origin "$BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git checkout -q "$BRANCH"
else
  git checkout -q -b "$BRANCH" "origin/$BRANCH"
fi
git pull --ff-only origin "$BRANCH"
if git lfs version >/dev/null 2>&1; then git lfs pull; fi
# Frontend dependencies follow the lockfile (v5/next adds Plotly).
LOCK_SHA="$(shasum -a 256 frontend/package-lock.json 2>/dev/null || sha256sum frontend/package-lock.json)"
LOCK_SHA="${LOCK_SHA%% *}"
mkdir -p var
if [ "$(cat var/npm-lock.sha 2>/dev/null)" != "$LOCK_SHA" ]; then
  echo "== frontend dependencies changed: npm ci"
  ( cd frontend && npm ci --no-audit --no-fund ) && echo "$LOCK_SHA" > var/npm-lock.sha
fi
# Python dependencies follow the lock (v5/r2-whatif adds XGBoost, SHAP, scikit-learn).
PYLOCK_SHA="$(shasum -a 256 ops/requirements.lock.txt 2>/dev/null || sha256sum ops/requirements.lock.txt)"
PYLOCK_SHA="${PYLOCK_SHA%% *}"
if [ "$(cat var/pip-lock.sha 2>/dev/null)" != "$PYLOCK_SHA" ]; then
  echo "== Python dependencies changed: pip install -r ops/requirements.lock.txt"
  .venv/bin/pip install -q -r ops/requirements.lock.txt && echo "$PYLOCK_SHA" > var/pip-lock.sha
fi
# The What-If IFRS 9 domain is rebuilt from the books and the MEVs (about a minute), never pulled.
if [ -f ops/whatif_build_domain.py ]; then .venv/bin/python ops/whatif_build_domain.py --if-needed; fi
echo "== quick gate checks"
.venv/bin/python ops/frozen_guard.py
TMPDIR="$V5/var/pytest" .venv/bin/python -m pytest tests/v5/test_sync_*.py \
  -p no:cacheprovider --basetemp="$V5/var/pytest/uat_pull" -q
echo "== starting v5"
ops/v5.sh stop >/dev/null 2>&1 || true
ops/v5.sh start >/dev/null
.venv/bin/python - <<'PY'
import json, urllib.request
for d in ("corporate", "retail"):
    j = json.load(urllib.request.urlopen(f"http://127.0.0.1:8501/api/v1/ews/level?domain={d}", timeout=120))
    h = j["headline"]
    print(f"{d.upper():9s} as of {j['period']}: {h['customers']:,} {j['labels']['owners']} · warned {h['customers_warned']:,} · "
          f"high/critical {h['high_or_critical']:,} · already bad {h['current_bad']:,} · forward risk {h['forward_risk']:,} · "
          f"exposure SAR {h['exposure']:,.0f}m · rule set {j['ruleset']}")
PY
echo
echo "READY FOR UAT   $BRANCH @ $(git rev-parse --short HEAD)   http://127.0.0.1:5500"
