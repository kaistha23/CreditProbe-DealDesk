#!/usr/bin/env python3
"""R14 session p: publish the proposal-check demo deal R14-RWQ into Data Domains (later version, actor p:r14-sample, upsert).

    .venv/bin/python ops/r14_p_publish_demo.py          # idempotent; re-run after a full R12 data build

The rows come from backend/dealdesk/proposal_check/demo_deal.py (built with the R12 demo helpers). The R12 build check
(`python -m backend.dealdesk.data.build --check`) compares the build with version 1 of each relation, so it stays green.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

STAMP = "2026-10-19T18:30:00Z"


def _same(rel: str, rows: list[dict], pid: str) -> bool:
    """True when the relation already holds exactly these rows for the demo deal (so a re-run publishes nothing)."""
    import pandas as pd

    from backend.dealdesk.data import schema, store
    keys = schema.RELATIONS[rel]["keys"]
    new = store.conform(rel, rows).drop(columns=["rel_version", "published_at"], errors="ignore")
    new[schema.PERIOD] = new[schema.PERIOD].fillna(schema.AS_OF)
    new = new.astype(object).where(new.notna(), "").astype(str)
    cur = store.conform(rel, store.dd_frame(rel))
    cur = cur.astype(object).where(cur.notna(), "").astype(str)
    k_new = set(new[keys].astype(str).agg("\x1f".join, axis=1))
    cur = cur[cur[keys].astype(str).agg("\x1f".join, axis=1).isin(k_new)].drop(columns=["rel_version", "published_at"], errors="ignore")
    if len(cur) != len(new):
        return False
    a = new.sort_values(keys).reset_index(drop=True).astype(str)
    b = cur.sort_values(keys).reset_index(drop=True)[a.columns].astype(str)
    return bool((a == b).all().all()) and isinstance(pd, object)


def main() -> int:
    from backend.dealdesk.data import store
    from backend.dealdesk.proposal_check import demo_deal
    rows = demo_deal.all_rows()
    for rel, rs in sorted(rows.items()):
        try:
            same = _same(rel, rs, demo_deal.PID)
        except Exception:  # noqa: BLE001 - compare failed: publish
            same = False
        if same:
            print(f"  {rel:24s} unchanged")
            continue
        r = store.publish(rel, rs, mode="upsert", actor="p:r14-sample", at=STAMP)
        print(f"  {rel:24s} +{r['written']:3d} rows -> v{r['version']} ({r['rows']} rows)")
    print("R14-RWQ published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
