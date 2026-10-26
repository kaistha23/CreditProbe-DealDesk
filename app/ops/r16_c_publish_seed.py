"""R16 c: the demo rows of dd_credit_request and dd_credit_response (customer 2, fictional).

    .venv/bin/python ops/r16_c_publish_seed.py --from CRS-...    snapshot a finished case into backend/dealdesk/credit_response/seed_rows.json
    .venv/bin/python ops/r16_c_publish_seed.py                   publish the committed snapshot (fixed time, actor R16-c:seed)

The snapshot renames the case to CRS-SEED-C2 and fixes every timestamp, so a re-publish is byte-stable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STAMP = "2026-10-21T18:00:00Z"
SEED_ID = "CRS-SEED-C2"


def snapshot(cid: str) -> dict[str, int]:
    from backend.dealdesk.credit_response import relation as RL
    from backend.dealdesk.credit_response import service as SV
    c = SV.get(cid)
    rows = {"dd_credit_request": RL.request_rows(c), "dd_credit_response": RL.response_rows(c)}
    from backend.dealdesk.data import store
    deals = {r["proposal_id"] for r in store.dd_read("dd_deal", columns=["proposal_id"])}
    out: dict[str, list[dict]] = {}
    for rel, rs in rows.items():
        fixed = []
        for r in rs:
            r = {k: (v.replace(cid, SEED_ID) if isinstance(v, str) else v) for k, v in r.items()}
            if r.get("proposal_id") and r["proposal_id"] not in deals:
                r["proposal_id"] = ""  # the deal is not in the committed register (it is created at run time): every reference resolves
            for k in ("read_at", "created_at"):
                if k in r:
                    r[k] = STAMP
            fixed.append(r)
        out[rel] = fixed
    RL.SEED.write_text(json.dumps(out, indent=1, default=str, sort_keys=True))
    return {k: len(v) for k, v in out.items()}


def publish() -> dict[str, int]:
    from backend.dealdesk.credit_response import relation as RL
    from backend.dealdesk.data import store
    rows = RL.seed_rows()
    return {rel: store.publish(rel, rs, mode="replace", actor=RL.SEED_ACTOR, at=STAMP)["rows"] for rel, rs in rows.items()}


def main(argv: list[str]) -> int:
    if "--from" in argv:
        print("SNAPSHOT", snapshot(argv[argv.index("--from") + 1]))
    print("PUBLISHED", publish())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
