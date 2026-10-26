"""Publish the detector's findings to dd_review_finding (category financial_quality) through backend.dealdesk.data.

One row per flagged signal (finding_id Q-<deal>-<code>) plus one grade row (Q-<deal>-GRADE, severity info). A recompute
replaces the deal's earlier financial-quality rows (replace_where on proposal_id + category), so a signal that no longer
breaches its threshold leaves the relation. Review point 4 (re-performed analysis); audit signals sit under point 4 too.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.dealdesk.fin_quality import engine as E

CATEGORY = "financial_quality"
RAISED_BY = "Q"
REVIEW_POINT = {"related_party": 6, "receivables": 4, "earnings": 4, "balance_sheet": 4, "audit": 4, "statistical": 4, "conduct": 2}


def _key(src: dict[str, Any] | None) -> str | None:
    if not src:
        return None
    return ";".join(f"{k}={v}" for k, v in (src.get("key") or {}).items()) or None


def rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    pid = res["subject"]["proposal_id"]
    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = []
    for s in res["signals"]:
        if s["flag"] is not True:
            continue
        num = s["value"] if isinstance(s["value"], (int, float)) and not isinstance(s["value"], bool) else None
        thr = s["threshold"] if isinstance(s["threshold"], (int, float)) and not isinstance(s["threshold"], bool) else None
        out.append({"finding_id": f"Q-{pid}-{s['code']}", "proposal_id": pid, "review_point": REVIEW_POINT.get(s["family"], 4), "category": CATEGORY,
                    "severity": s["severity"], "title": f"{s['family_label']}: {s['label']}", "finding_text": s["text"],
                    "claim_text": f"Threshold {s['threshold_display']} ({s['policy_ref']})", "claim_value": thr, "evidence_value": num,
                    "evidence_unit": s["unit"], "evidence_domain": "dealdesk", "evidence_relation": (s.get("source") or {}).get("relation"),
                    "evidence_key": _key(s.get("source")), "status": "open", "rating_notch": 0, "raised_by": RAISED_BY, "raised_at": now})
    g = res["grade"]
    out.append({"finding_id": f"Q-{pid}-GRADE", "proposal_id": pid, "review_point": 4, "category": CATEGORY, "severity": "info",
                "title": f"Financial quality grade {g['grade']}", "finding_text": res["headline"],
                "claim_text": g["rule"], "claim_value": None, "evidence_value": float(g["points"]), "evidence_unit": "points",
                "evidence_domain": "dealdesk", "evidence_relation": "dd_financials_detail" if res["mode"] == "detail" else "dd_obligor_financials",
                "evidence_key": f"proposal_id={pid}", "status": "open", "rating_notch": 0, "raised_by": RAISED_BY, "raised_at": now})
    return out


def publish(pid: str) -> dict[str, Any]:
    from backend.dealdesk.data import publish as dd_publish
    res = E.assess(pid)
    rs = rows(res)
    out = dd_publish("dd_review_finding", rs, mode="replace_where", actor=RAISED_BY, where={"proposal_id": pid, "category": CATEGORY})
    try:
        from backend.dealdesk.review2 import source as RS
        RS.clear()
    except Exception:  # noqa: BLE001
        pass
    return {"relation": "dd_review_finding", "rows": len(rs), "grade": res["grade"]["grade"], "result": out if isinstance(out, (dict, str, int)) else None}


def published(pid: str) -> list[dict[str, Any]]:
    from backend.dealdesk.review2 import publish as P
    return [r for r in P.read("dd_review_finding", proposal_id=pid) if r.get("category") == CATEGORY]
