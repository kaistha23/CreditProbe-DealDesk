"""Batch proposal check (K33 / D2): run the K31 checks on every pending proposal, rank them, roll up by RM, publish.

    out = run_all(publish=True)     # {"table": [...], "rm": [...], "summary": {...}, "changed": [...]}
    PENDING = statuses checked: new, in_review, counter_offered (dd_deal.status)

What is checked per deal (same order as engine.check_record): the latest uploaded Word proposal, else the RM's memo on file,
else the submission record in dd_deal. Deterministic: the same documents and data give the same table (ranks, scores).
"score changed" compares with the last proposal_score row published for the deal in dd_proposal_quality.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any

from backend.dealdesk.house_style.bankform import source as S
from backend.dealdesk.proposal_check import engine, store

PENDING = ("new", "in_review", "counter_offered")
DEFECT_LABEL = {"undisclosed_returned_cheques": "Returned cheques not disclosed", "turnover_overstated": "Turnover overstated",
                "related_party_receivables_as_trade": "Related-party receivables as trade", "ubo_bureau_missing": "UBO bureau report missing",
                "unperfected_guarantee": "Unperfected guarantee", "stale_valuation": "Stale valuation", "group_exposure_total_wrong": "Group exposure total wrong",
                "covenant_without_numbers": "Covenants without numbers", "missing_project_status": "Project status missing",
                "vague_sales_terms": "Vague sales terms", "prior_condition_misstated": "Prior condition misstated",
                "pricing_exception_undisclosed": "Pricing exception not disclosed", "missing_section": "Missing section",
                "facilities_total_wrong": "Facilities total wrong"}


def pending() -> list[dict[str, Any]]:
    return sorted([d for d in S.read("dd_deal") if str(d.get("status")) in PENDING], key=lambda d: str(d["proposal_id"]))


def _previous_scores() -> dict[str, float]:
    out: dict[str, float] = {}
    from backend.dealdesk.proposal_check.engine import STAMP
    for r in S.read("dd_proposal_quality", check="proposal_score"):
        pid = str(r.get("proposal_id"))
        if str(r.get("checked_at") or "") == STAMP:  # the build's demo rows are not a previous check of the deal
            continue
        if r.get("score") is not None and str(r.get("checked_at") or "") >= str(out.get(pid + "@", "")):
            out[pid], out[pid + "@"] = float(r["score"]), str(r.get("checked_at") or "")  # type: ignore[assignment]
    return {k: v for k, v in out.items() if not k.endswith("@")}


def row(res: dict[str, Any], prev: float | None = None) -> dict[str, Any]:
    sent = {q["n"] for s in store.sent(res["proposal_id"]) if s["run_id"] == res["run_id"] for q in s["queries"]}
    d = res["defects"]
    top = Counter(f["defect_type"] for f in d).most_common(1)
    return {"proposal_id": res["proposal_id"], "customer": res["customer"], "rm": res["rm"], "branch": res["branch"], "sector": res["sector"],
            "status": res["status"], "document": res["document"], "document_kind": res["document_kind"], "run_id": res["run_id"],
            "score": res["score"], "grade": res["grade"], "defects": len(d), "critical": res["critical"],
            "undisclosed": sum(1 for f in d if f["category"] == "disclosure"), "contradicted": sum(1 for f in d if f["title"].startswith("RM claim contradicted")),
            "queries_open": len([q for q in res["queries"] if q["n"] not in sent]), "sections_present": res["sections_present"],
            "top_defect": DEFECT_LABEL.get(top[0][0], top[0][0].replace("_", " ")) if top else "",
            "previous_score": prev, "score_changed": prev is not None and abs(prev - res["score"]) >= 0.05, "headline": res["headline"]}


def rm_view(table: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for r in table:
        by.setdefault(r["rm"] or "—", []).append(r)
    out = []
    for rm, rs in by.items():
        types = Counter(f["defect_type"] for r in rs for f in results[r["proposal_id"]]["defects"])
        out.append({"rm": rm, "proposals": len(rs), "average_score": round(sum(r["score"] for r in rs) / len(rs), 1),
                    "critical": sum(r["critical"] for r in rs), "queries_open": sum(r["queries_open"] for r in rs),
                    "recurring": [(DEFECT_LABEL.get(k, k), v) for k, v in types.most_common(3)],
                    "deals": [r["proposal_id"] for r in rs]})
    return sorted(out, key=lambda r: (r["average_score"], r["rm"]))


_LAST: dict[str, Any] = {}


def run_all(publish: bool = True) -> dict[str, Any]:
    t0 = time.perf_counter()
    prev = _previous_scores()
    results: dict[str, dict[str, Any]] = {}
    errors = []
    for d in pending():
        pid = str(d["proposal_id"])
        try:
            results[pid] = engine.check_record(pid)
            store.remember(results[pid])
        except Exception as e:  # noqa: BLE001 - one deal's problem never stops the batch
            errors.append({"proposal_id": pid, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    table = [row(r, prev.get(pid)) for pid, r in results.items()]
    table.sort(key=lambda r: (-r["critical"], r["score"], r["proposal_id"]))
    for i, r in enumerate(table):
        r["rank"] = i + 1
    pub = None
    if publish and results:
        at = store.now()
        rows = [x | {"checked_at": at} for r in results.values() for x in r["rows"]]
        pub = store.publish(rows, actor="p:batch-check")
    rms = rm_view(table, results)
    out = {"summary": {"pending": len(table), "checked": len(results), "errors": len(errors), "average_score": round(sum(r["score"] for r in table) / len(table), 1) if table else None,
                       "critical": sum(r["critical"] for r in table), "with_critical": sum(1 for r in table if r["critical"]),
                       "queries_open": sum(r["queries_open"] for r in table), "changed": sum(1 for r in table if r["score_changed"]),
                       "elapsed_s": round(time.perf_counter() - t0, 2), "published": pub,
                       "method": "K31 checks on every pending proposal (deterministic rules + bank data; no model)"},
           "table": table, "rm": rms, "errors": errors,
           "filters": {"rm": sorted({r["rm"] for r in table}), "branch": sorted({r["branch"] for r in table}), "sector": sorted({r["sector"] for r in table})}}
    _LAST.clear()
    _LAST.update(out)
    return out


def last() -> dict[str, Any] | None:
    return dict(_LAST) if _LAST else None
