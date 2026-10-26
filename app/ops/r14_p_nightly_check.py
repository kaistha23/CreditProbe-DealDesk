#!/usr/bin/env python3
"""R14 session p (K33): the nightly re-check of every pending proposal. Publishes dd_proposal_quality and prints the deals whose
score changed since the last check ("score changed" flags in the batch table).

    .venv/bin/python ops/r14_p_nightly_check.py            # schedule nightly (cron / launchd) on the bank's server; not scheduled in the demo
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main() -> int:
    from backend.dealdesk.proposal_check import batch
    out = batch.run_all(publish=True)
    s = out["summary"]
    print(json.dumps({k: s[k] for k in ("pending", "checked", "errors", "average_score", "critical", "queries_open", "changed", "elapsed_s")}))
    for r in out["table"]:
        if r["score_changed"]:
            print(f"  score changed: {r['proposal_id']} {r['previous_score']} -> {r['score']}")
    return 0 if not out["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
