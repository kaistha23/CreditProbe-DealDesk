"""PLAN_R12 Session B API (prefix /api/v1/dealdesk/review2), mounted by one include_router line in the R12 block of api.py.

  POST  /review2/{id}                       the full review (12 points, findings, analytics, documents, queries, quality, opinion);
                                            body {"refresh": bool, "view": "review" | "prepare"}; an RM login always gets "prepare"
  GET   /review2/{id}/preflight             the Prepare view's pre-flight check (same rules before submission)
  GET   /review2/{id}/findings              findings by severity (?severity=&point=)
  POST  /review2/{id}/signoff               {"role", "decision", "note"}: second-line sign-off, logged
  GET   /review2/{id}/documents             the document checklist
  PATCH /review2/{id}/documents/{item_id}   {"status", "date", "note"}; a received or waived item closes its open query
  GET   /review2/{id}/documents/history     the status log
  POST  /review2/{id}/documents/queries     one RM query per missing or expired required document
  GET   /review2/document-rules             data/dealdesk/params/v1/documents.json
  GET   /review2/queries                    ?deal_id=: every query with its Mail thread and status (replies synced from Mail)
  GET   /review2/queries/summary            open queries and days in review per deal (landing card "In review")
  POST  /review2/queries                    {"deal_id", "question", "kind", "ref_id", "to"}
  POST  /review2/queries/{qid}/answer       {"text"}: the RM's answer (a reply in the Mail thread)
  POST  /review2/queries/{qid}/close        {"note"} · POST /review2/queries/{qid}/reopen
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk import documents as DOC
from backend.dealdesk.review2 import queries as Q
from backend.dealdesk.review2 import source as S
from backend.dealdesk.review2 import workspace as R

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX + "/review2", tags=["r12-review"])

RM_ROLES = ("relationship manager",)


def _who(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request) or {}
    except Exception:  # noqa: BLE001
        return {}


def _is_rm(u: dict[str, Any]) -> bool:
    return str(u.get("role") or "").lower() in RM_ROLES


def _known(did: str) -> str:
    if not S.known(did):
        raise HTTPException(404, f"No deal {did}.")
    return did


def _bad(e: Exception) -> HTTPException:
    return HTTPException(422, str(e))


@router.get("/document-rules")
def document_rules() -> dict[str, Any]:
    return DOC.rulebook()


@router.get("/queries")
def queries(deal_id: str | None = Query(None)) -> dict[str, Any]:
    return Q.listing(deal_id)


@router.get("/queries/summary")
def queries_summary() -> dict[str, Any]:
    import datetime as dt
    items = Q.listing(None)["items"]
    deals: dict[str, dict[str, Any]] = {}
    for q in items:
        d = deals.setdefault(q["deal_id"], {"deal_id": q["deal_id"], "open": 0, "answered": 0, "closed": 0, "first_query": q["created_at"]})
        d["open" if q["status"] in ("queued", "sent") else q["status"]] += 1
        d["first_query"] = min(d["first_query"], q["created_at"])
    now = dt.datetime.now(dt.timezone.utc)
    for d in deals.values():
        d["days_in_review"] = (now - dt.datetime.fromisoformat(d["first_query"])).days
    rows = sorted(deals.values(), key=lambda d: (-d["open"], -d["days_in_review"]))
    n_open = sum(d["open"] for d in rows)
    return {"deals": rows, "open": n_open, "deals_with_open": sum(1 for d in rows if d["open"]),
            "line": f"{n_open} queries open with RMs across {sum(1 for d in rows if d['open'])} deals."}


@router.post("/queries")
def raise_query(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _known(str(body.get("deal_id") or ""))
    try:
        return Q.raise_query(body["deal_id"], body.get("question") or "", body.get("kind") or "information", body.get("ref_id"),
                             body.get("to") or None, _who(request).get("username") or None)
    except ValueError as e:
        raise _bad(e) from e


@router.post("/queries/sync")
def queries_sync(deal_id: str | None = Query(None)) -> dict[str, Any]:
    return Q.sync(deal_id)


@router.post("/queries/{qid}/answer")
def query_answer(qid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return Q.answer(qid, body.get("text") or "", _who(request).get("username") or None)
    except KeyError as e:
        raise HTTPException(404, f"No query {qid}.") from e
    except ValueError as e:
        raise _bad(e) from e


@router.post("/queries/{qid}/close")
def query_close(qid: str, request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    try:
        return Q.close(qid, _who(request).get("username") or "", (body or {}).get("note"))
    except KeyError as e:
        raise HTTPException(404, f"No query {qid}.") from e


@router.post("/queries/{qid}/reopen")
def query_reopen(qid: str, request: Request) -> dict[str, Any]:
    try:
        return Q.reopen(qid, _who(request).get("username") or "")
    except KeyError as e:
        raise HTTPException(404, f"No query {qid}.") from e


@router.post("/{did}")
def review(did: str, request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    _known(did)
    b = body or {}
    view = "prepare" if _is_rm(_who(request)) else (b.get("view") or "review")
    if view not in ("review", "prepare"):
        raise HTTPException(422, "view must be review or prepare")
    return R.review(did, refresh=bool(b.get("refresh")), view=view)


@router.get("/{did}/preflight")
def preflight(did: str) -> dict[str, Any]:
    _known(did)
    return R.preflight(did)


@router.get("/{did}/findings")
def findings(did: str, severity: str | None = Query(None), point: int | None = Query(None)) -> dict[str, Any]:
    _known(did)
    r = R.review(did)
    fs = [f for f in r["findings"] if (not severity or f["severity"] == severity) and (not point or f["point"] == point)]
    return {"deal_id": did, "findings": fs, "counts": r["counts"], "answer": r["answer"]}


@router.post("/{did}/signoff")
def signoff(did: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _known(did)
    u = _who(request)
    if _is_rm(u):
        raise HTTPException(403, "Sign-off is for the credit division.")
    try:
        return R.sign(did, body.get("role") or "", body.get("decision") or "", u.get("username") or "", body.get("note") or "")
    except ValueError as e:
        raise _bad(e) from e


@router.get("/{did}/documents")
def documents(did: str) -> dict[str, Any]:
    _known(did)
    return DOC.checklist(did)


@router.get("/{did}/documents/history")
def documents_history(did: str, item_id: str | None = Query(None)) -> dict[str, Any]:
    _known(did)
    return {"deal_id": did, "log": DOC.history(did, item_id)}


@router.post("/{did}/documents/queries")
def documents_queries(did: str, request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    _known(did)
    return R.queue_missing(did, _who(request).get("username") or None, (body or {}).get("to"))


@router.patch("/{did}/documents/{item_id:path}")
def document_status(did: str, item_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _known(did)
    by = _who(request).get("username") or ""
    try:
        item = DOC.set_status(did, item_id, body.get("status") or "", body.get("date"), body.get("note"), by)
    except KeyError as e:
        raise HTTPException(404, f"No document {item_id} on {did}.") from e
    except ValueError as e:
        raise _bad(e) from e
    if item["status"] in ("received", "waived"):
        Q.close_for_ref(did, item_id, by, f"Document {item['status']}")
    return item
