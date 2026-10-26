"""R11 Session R: the proposal review API (prefix /api/v1/dealdesk), mounted by one include_router line in api.py.

  POST  /proposals/{id}/review/memo         review an uploaded memo (.docx) against the proposal's data
  POST  /proposals/{id}/review              the review workspace (answer, memo lines marked, findings, DoA, counter-proposals,
                                            conditions, precedent); {"refresh": true} recomputes
  GET   /proposals/{id}/review/sheet        the one-page committee decision sheet
  GET   /proposals/{id}/review/sheet.docx   the same in Word (house style)
  POST  /proposals/{id}/review/draft        RM "Draft from data": factual memo sections filled, judgement sections left to the RM
  GET   /proposals/{id}/review/draft.docx   the draft in Word
  GET   /review/r11/subjects                every reviewable proposal (prepared cases and Deal Desk proposals) with its decision
  GET   /review/r11/rules                   the rule book (data/dealdesk/review/rules.json)
  GET   /conditions                         tracked triggers (?deal_id=), status from data, with the summary line
  GET   /conditions/summary                 "Conditions due: n across m deals" for the Deal Desk landing
  PATCH /conditions/{cid}  (or PATCH /conditions with "id")   status / owner / due_date / note
  GET   /conditions/{cid}/history           the edit log of a trigger

GET /review/cases (R9) is unchanged; its rows gain the R11 decision through proposal_review.cases() (additive).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from backend.dealdesk import review_conditions as RCN
from backend.dealdesk import review_rules as RR
from backend.dealdesk import review_workspace as W

PREFIX = "/api/v1/dealdesk"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix=PREFIX, tags=["r11-review"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _known(pid: str) -> str:
    from backend.dealdesk import review_facts as RF
    if not RF.known(pid):
        raise HTTPException(404, f"No proposal {pid}.")
    return pid


@router.post("/proposals/{pid}/review")
def review(pid: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    _known(pid)
    return W.review(pid, refresh=bool((body or {}).get("refresh")))


@router.post("/proposals/{pid}/review/memo")
async def review_memo(pid: str, file: UploadFile = File(...)) -> dict[str, Any]:
    """Review an uploaded memo (.docx) against the proposal's data: the memo replaces the stored one for this review."""
    _known(pid)
    data = await file.read()
    if not (file.filename or "").lower().endswith(".docx") or data[:2] != b"PK":
        raise HTTPException(422, "Upload the credit memo as a .docx file.")
    from backend.dealdesk import review_facts as RF
    try:
        from backend.dealdesk.review_ledger import ledger
        ledger(data)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "The memo could not be read. Upload a .docx credit memo.") from None
    RF.save_uploaded_memo(pid, data)
    return W.review(pid, refresh=True)


@router.get("/proposals/{pid}/review/sheet")
def sheet(pid: str) -> dict[str, Any]:
    return W.sheet(_known(pid))


@router.get("/proposals/{pid}/review/sheet.docx")
def sheet_docx(pid: str, request: Request) -> Response:
    data, name = W.sheet_docx(_known(pid), _user(request))
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/proposals/{pid}/review/draft")
def draft(pid: str) -> dict[str, Any]:
    return W.draft(_known(pid))


@router.get("/proposals/{pid}/review/draft.docx")
def draft_docx(pid: str, request: Request) -> Response:
    data, name = W.draft_docx(_known(pid), _user(request))
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/review/r11/subjects")
def subjects() -> dict[str, Any]:
    out = []
    for s in W.subjects():
        try:
            q = W.quick(s["id"])
            out.append({**s, **{k: v for k, v in q.items() if not k.startswith("_")}})
        except Exception:  # noqa: BLE001 - listed without a decision
            out.append({**s, "decision": None})
    return {"subjects": out, "clean_memos": list(W.CLEAN_MEMOS)}


@router.get("/review/r11/rules")
def rules() -> dict[str, Any]:
    b = RR.rulebook()
    return {"version": b["version"], "effective_from": b.get("effective_from"), "categories": b["categories"],
            "rules": [{k: r.get(k) for k in ("id", "category", "title", "tests", "severity", "on_fail", "threshold", "unit", "policy_ref",
                                             "crm_article", "doa_rank", "scope", "enabled")} for r in b["rules"]]}


@router.get("/conditions")
def conditions(deal_id: str = Query(default="")) -> dict[str, Any]:
    W.ensure_conditions()
    return RCN.listing(deal_id or None)


@router.get("/conditions/summary")
def conditions_summary() -> dict[str, Any]:
    W.ensure_conditions()
    return RCN.listing(None)["summary"]


def _patch(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        t = RCN.patch(cid, body, _user(request))
    except KeyError:
        raise HTTPException(404, f"No condition {cid}.") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return RCN.evaluate_trigger(t, RCN.facts_for(t["deal_id"]))


@router.patch("/conditions/{cid:path}")
def patch_condition(cid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if cid.endswith("/history"):
        raise HTTPException(405, "Use GET for the history.")
    return _patch(cid, body, request)


@router.patch("/conditions")
def patch_condition_body(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not body.get("id"):
        raise HTTPException(422, "id is required.")
    return _patch(str(body["id"]), {k: v for k, v in body.items() if k != "id"}, request)


@router.get("/conditions/{cid:path}/history")
def condition_history(cid: str) -> dict[str, Any]:
    return {"id": cid, "history": RCN.history(cid)}
