"""R12 Session I routes: the Book (prefix /api/v1/dealdesk/book).

  GET  /book                         ?filter=all|going_bad|repricing|promises_unmet|tier_high|renewals_due|conditions_due
                                     &q=&sector=&tier=&limit=&offset=&ref_date=     the Book rows
  GET  /book/counts                  counts for U's landing cards and the Book filters
  GET  /book/facility/{fid}          one facility: drift waterfall, promises, covenants, plan history, reprice/optimiser
  GET  /book/drift                   RAROC drift (renamed from Portfolio RAROC at origination)
  GET  /book/promises                promises against delivery (dd_promise view)
  POST /book/facility/{fid}/tier     {tier, reason}       new dd_monitoring_plan version
  POST /book/facility/{fid}/ews      {reason}             send to Early Warning (dd_monitoring_plan, referral)
  POST /book/facility/{fid}/renewal  {note?}              reopen on Proposal with last year's file (dd_workflow_event)
  GET  /book/facility/{fid}/open     the deal page link
  GET  /book/feedback                sector hurdle override proposals, margin ratchet, realisation in use
  POST /book/feedback/hurdles        {sector, hurdle, reason}       maker proposes
  POST /book/feedback/hurdles/{id}   {approve, note?}               checker decides (different person)
  POST /book/publish                 publish dd_raroc_drift and dd_promise for the current period

Mounted by one line in the "# R12 routers" block of backend/dealdesk/api.py. Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk.book import actions, core, drift, feedback, promises, sources

PREFIX = "/api/v1/dealdesk/book"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-book"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        u = current_user(request) or {}
        return u.get("display_name") or u.get("username") or "Deal Desk user"
    except Exception:  # noqa: BLE001 - answers without the Core service
        return "Deal Desk user"


def _pending(e: sources.DataPending) -> HTTPException:
    return HTTPException(503, f"{e.relation} is not in Data Domains yet: {e.why}")


@router.get("")
def get_book(filter: str = "all", q: str = "", sector: str = "", tier: str = "", limit: int = Query(50, ge=1, le=500),
             offset: int = Query(0, ge=0), ref_date: str | None = None) -> dict[str, Any]:
    try:
        return core.listing(filter, q, sector, tier, limit, offset, ref_date)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/counts")
def get_counts(ref_date: str | None = None) -> dict[str, Any]:
    return core.counts(ref_date)


@router.get("/drift")
def get_drift(ref_date: str | None = None) -> dict[str, Any]:
    return drift.summary(ref_date)


@router.get("/promises")
def get_promises(status: str = "", kind: str = "", limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    f, pending = core.frame()
    t = promises.frame(f, pending)
    if status:
        t = t[t.status == status]
    if kind:
        t = t[t.kind == kind]
    t = t.sort_values("realisation", na_position="last")
    return {"total": int(len(t)), "by_status": t.status.value_counts().to_dict(), "rows": promises.display_rows(t.head(limit)),
            "realisation": feedback.realisation(), "pending": pending, "sources": sources.lineage()}


@router.get("/facility/{fid}")
def get_facility(fid: str, ref_date: str | None = None) -> dict[str, Any]:
    try:
        return core.facility(fid, ref_date)
    except KeyError:
        raise HTTPException(404, f"No facility {fid} in the Book.") from None


def _act(fn, *a: Any) -> dict[str, Any]:
    try:
        return fn(*a)
    except KeyError as e:
        raise HTTPException(404, f"No facility {e.args[0]} in the Book.") from None
    except actions.ActionError as e:
        raise HTTPException(422, str(e)) from None
    except sources.DataPending as e:
        raise _pending(e) from None


@router.post("/facility/{fid}/tier")
def post_tier(fid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _act(actions.set_tier, fid, str(body.get("tier", "")), str(body.get("reason", "")), _user(request))


@router.post("/facility/{fid}/ews")
def post_ews(fid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _act(actions.send_to_ews, fid, str(body.get("reason", "")), _user(request))


@router.post("/facility/{fid}/renewal")
def post_renewal(fid: str, request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return _act(actions.start_renewal, fid, _user(request), str((body or {}).get("note", "")))


@router.get("/facility/{fid}/open")
def get_open(fid: str) -> dict[str, Any]:
    return _act(actions.open_deal, fid)


@router.get("/feedback")
def get_feedback(ref_date: str | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pb = params.rows("pricing_behaviour")
    return {"hurdles": feedback.hurdle_overrides(ref_date), "realisation": feedback.realisation(),
            "ratchet": {"lever": "margin_ratchet_bps_per_notch", "max_bps_per_notch": pb.get("margin_ratchet_max_bps_per_notch", 0),
                        "text": "Rating-linked margin ratchet: a Pricing lever on every deal; origination RAROC prices the expected "
                                "migration from the one-year migration matrix."}}


@router.post("/feedback/hurdles")
def post_hurdle(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return feedback.propose(str(body.get("sector", "")), float(body.get("hurdle", 0)), _user(request), str(body.get("reason", "")))
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from None


@router.post("/feedback/hurdles/{hid}")
def post_hurdle_decision(hid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    checker = str(body.get("checker") or _user(request))
    try:
        return feedback.decide(hid, checker, bool(body.get("approve")), str(body.get("note", "")))
    except KeyError:
        raise HTTPException(404, f"No proposal {hid}.") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/publish")
def post_publish() -> dict[str, Any]:
    from backend.dealdesk.book import publish
    try:
        return publish.run()
    except sources.DataPending as e:
        raise _pending(e) from None
