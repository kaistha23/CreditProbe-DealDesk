"""One deal registry over Data Domains: DD proposals, PL pipeline applications and the R12 demo deals.

    from backend.dealdesk.data import deals
    deals.get("R12-TWA")      # engine-ready proposal record (proposals.json shape), from dd_deal.proposal_json
    deals.get("PL-07")        # from dd_pipeline.proposal_json
    deals.get("DD-01")        # proposals.get (seeded and user proposals)
    deals.register()          # dd_deal rows (product template, workflow state, header block) for every deal
    deals.product_of("R12-SYN")  -> "syndicated"
"""
from __future__ import annotations

import copy
import json
from typing import Any

from backend.dealdesk.data.store import dd_read


def _demo() -> dict[str, dict[str, Any]]:
    out = {}
    for r in dd_read("dd_deal", parse_json=False, source="r12_demo"):
        if r.get("proposal_json"):
            out[r["proposal_id"]] = json.loads(r["proposal_json"])
    return out


def pipeline_set() -> dict[str, dict[str, Any]]:
    """The PL set, in id order, from dd_pipeline."""
    rows = sorted(dd_read("dd_pipeline", parse_json=False), key=lambda r: r["proposal_id"])
    return {r["proposal_id"]: json.loads(r["proposal_json"]) for r in rows if r.get("proposal_json")}


def demo_ids() -> list[str]:
    return sorted(_demo())


def get(pid: str) -> dict[str, Any]:
    d = _demo()
    if pid in d:
        return copy.deepcopy(d[pid])
    pl = pipeline_set()
    if pid in pl:
        return copy.deepcopy(pl[pid])
    from backend.dealdesk import proposals
    return proposals.get(pid)


def register(**filters: Any) -> list[dict[str, Any]]:
    """dd_deal rows without the heavy proposal_json column."""
    from backend.dealdesk.data import schema as S
    cols = [c for c in S.column_names("dd_deal") if c != "proposal_json"]
    return dd_read("dd_deal", columns=cols, **filters)


def product_of(pid: str) -> str:
    r = register(proposal_id=pid)
    return r[0]["product"] if r else "corporate"
