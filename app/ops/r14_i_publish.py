"""R14 i: publish session i's Data Domains rows.

    .venv/bin/python ops/r14_i_publish.py --seed       the build's rows for dd_external_turnover and dd_deal_intel
                                                       (same actor and stamp as backend.dealdesk.data.build, so
                                                       `build --check` compares equal), then the contract document
    .venv/bin/python ops/r14_i_publish.py --results [DEAL ...]
                                                       D6-D13 engine results per deal into dd_deal_intel (upsert, actor
                                                       R14-I, a later version: build --check compares version 1)

Run after a full `python -m backend.dealdesk.data.build` too (the build writes the seed and the catalogue only).
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def seed() -> None:
    from backend.dealdesk.data import build, contract, store
    from backend.dealdesk.intel2 import seed as i_seed
    rows = {rel: store.dd_read(rel) for rel in ("dd_deal", "dd_financials_detail", "dd_account_conduct", "other_bank_facility")}
    out = i_seed.build(rows)
    for rel, rs in out.items():
        r = store.publish(rel, rs, mode="replace", actor=build.ACTOR, at=build.STAMP)
        print(f"{rel}: {r['rows']} rows, version {r.get('version')}")
    contract.main()


def results(deals: list[str]) -> None:
    from backend.dealdesk.data import store
    from backend.dealdesk.intel2 import publish
    from backend.dealdesk.intel.approval import common as C
    ids = deals or ["R12-TWA", "R12-TWB", "DD-06"]
    if ids == ["all"]:
        ids = C.all_ids()
    rows = []
    for pid in ids:
        try:
            rows += publish.rows_for(pid)
        except Exception as e:  # noqa: BLE001 - one deal the engines cannot read does not stop the rest
            print(f"{pid}: skipped ({e})")
    r = store.publish("dd_deal_intel", rows, mode="upsert", actor="R14-I")
    print(f"dd_deal_intel: {len(rows)} result rows for {len(ids)} deals, version {r.get('version')}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--seed" in a:
        seed()
    if "--results" in a:
        results([x for x in a if not x.startswith("--")])
