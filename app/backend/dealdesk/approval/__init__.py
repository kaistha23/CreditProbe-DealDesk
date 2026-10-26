"""R14 E (K18, K19, K25 #4, D14): approval authority and approval path.

    from backend.dealdesk.approval import approval_authority
    approval_authority("R12-TWA")                 # the ask
    approval_authority("R12-TWA", "recommended")  # E's counter-offer
    approval_authority("R12-TWA", {"amount": 60}) # a user structure

Returns the level, the DoA rule that set it, every reason with the level it needs, exposure after the deal, the
exceptions, expected time to decision (median days of past decisions at that level, gov_decision) and the documents
still missing for the committee pack (open documents findings, dd_review_finding).
"""
from __future__ import annotations

import statistics
from typing import Any

from backend.dealdesk.approval.core import decide, for_proposal, level_of  # noqa: F401 - public API
from backend.dealdesk.economics import deal as D


def _expected_days(rank: int) -> dict[str, Any]:
    try:
        from backend.dealdesk.data.store import dd_read
        rows = dd_read("gov_decision", columns=["required_level_rank", "turnaround_days"])
        xs = [float(r["turnaround_days"]) for r in rows if int(r.get("required_level_rank") or 0) == int(rank)
              and r.get("turnaround_days") is not None]
        if xs:
            return {"value": round(statistics.median(xs), 1), "unit": "days", "n": len(xs),
                    "source": {"relation": "gov_decision", "column": "turnaround_days", "filter": {"required_level_rank": int(rank)},
                               "method": "median of past decisions at this level (fictional seed)"}}
    except Exception:  # noqa: BLE001
        pass
    return {"value": None, "unit": "days", "n": 0, "source": {"relation": "gov_decision", "method": "no history"}}


def _documents_missing(pid: str) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data.store import dd_read
        rows = dd_read("dd_review_finding", proposal_id=pid)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows:
        if str(r.get("category") or "").startswith("documents") and (r.get("status") or "open") == "open":
            out.append({"finding_id": r["finding_id"], "title": r.get("title"), "severity": r.get("severity"),
                        "source": {"relation": "dd_review_finding", "key": {"finding_id": r["finding_id"]}}})
    return out


def approval_authority(pid: str, structure: Any = None) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    st = D.structure_terms(pid, structure)
    a = D.analysis(pid, st["terms"])
    p = D.proposal(pid)
    d = for_proposal(p, a)
    rows = sorted(d["reasons"], key=lambda r: -int(r["rank"]))
    return {"proposal_id": pid, "structure": {"key": st["key"], "label": st["label"]},
            "level": d["level"], "rank": d["rank"], "rule": d["rule"], "binding": d["binding"], "reasons": rows,
            "exposure_after_sar_mn": d["exposure_after_sar_mn"], "existing_exposure_sar_mn": d["existing_exposure_sar_mn"],
            "new_limit_sar_mn": d["new_limit_sar_mn"], "exceptions": d["exceptions"],
            "hard_breaches": d["hard_breaches"], "soft_breaches": d["soft_breaches"], "approvable": d["approvable"],
            "expected_days": _expected_days(d["rank"]), "documents_missing": _documents_missing(pid),
            "path": [{"rank": r, "level": level_of(r)} for r in range(1, int(d["rank"]) + 1)],
            "source": d["source"]}
