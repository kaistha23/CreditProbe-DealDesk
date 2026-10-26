"""R13 Session Q: publish the financial-quality findings of every Deal Desk deal to dd_review_finding (category
financial_quality), the way the orchestrator seeds the demo (ops/r12_seed_demo.py).

    python ops/r13_fq_publish.py                 # every deal in dd_deal with statements on file
    python ops/r13_fq_publish.py R12-TWA R12-TWB # just these

Writes through backend.dealdesk.data.publish (a new dd_review_finding version per deal). Prints one line per deal; no
secret is read or printed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str]) -> int:
    from backend.dealdesk import fin_quality as FQ
    from backend.dealdesk.data import dd_read
    pids = argv or [r["proposal_id"] for r in dd_read("dd_deal", columns=["proposal_id"])]
    for pid in pids:
        r = FQ.assess(pid)
        if r["mode"] == "none":
            print(f"{pid}: no statements on file, skipped")
            continue
        out = FQ.publish(pid)
        print(f"{pid}: grade {out['grade']}, {out['rows']} row(s) published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
