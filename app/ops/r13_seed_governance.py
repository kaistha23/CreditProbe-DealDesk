"""R13 IE: seed the fictional governance history (gov_decision, gov_approval_step, gov_policy_exception) into Data Domains.

Usage: .venv/bin/python ops/r13_seed_governance.py
Deterministic; safe to re-run (mode replace). See backend/intel/governance/seed.py for what is seeded vs read from the book.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.intel.governance import seed  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(seed.seed(), indent=1, default=str))
