"""R13 Session IA API: approval intelligence (prefix /api/v1/dealdesk/intel/approval), mounted by one include_router line
in the R13 block of backend/dealdesk/api.py.

  GET /intel/approval/{id}/challenger    the 5-7 questions committee will ask, answered from data, and what the proposal avoids
  GET /intel/approval/{id}/reverse       for a failing deal: the smallest change that makes it approvable, as a counter-offer
  GET /intel/approval/{id}/security      recovery and capital value of each security item; the cheapest package that clears
  GET /intel/approval/{id}/consistency   similar deals decided differently, explained or not ({id} = "book": every pair)
  GET /intel/approval/intents            the intent descriptors Noor's Ask uses to call these

{id} is a Data Domains deal id (dd_deal: DD-*, PL-*, R12-*); twin aliases PRP-B-ASB / TWIN-A (R12-TWA) and PRP-A-GMC / TWIN-B
(R12-TWB) are accepted. Every figure is {value, unit, source} with Data Domains lineage (N5); every text is written by a
deterministic writer (N3). Each response carries a trace id (backend.dealdesk.trace).
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request

from backend.dealdesk import engine, params, pd_model, trace
from backend.dealdesk.intel.approval import challenger, common, consistency, reverse, security

PREFIX = "/api/v1/dealdesk/intel/approval"
router = APIRouter(prefix=PREFIX, tags=["r13-intel-approval"])

INTENTS = [
    {"id": "dealdesk.approval.challenger", "label": "Committee challenger", "path": PREFIX + "/{deal_id}/challenger",
     "examples": ["What will committee ask about this deal?", "Which questions does the proposal avoid?"],
     "answers": "The 5-7 questions committee will ask, each answered from data with its source, and the questions the proposal avoids."},
    {"id": "dealdesk.approval.reverse", "label": "Reverse solver", "path": PREFIX + "/{deal_id}/reverse",
     "examples": ["What is the smallest change that gets this approved?", "Give me a counter-offer for this declined deal."],
     "answers": "The smallest change in amount, tenor, security, price or covenants that makes the deal approvable, as an RM-ready counter-offer."},
    {"id": "dealdesk.approval.security", "label": "Security optimiser", "path": PREFIX + "/{deal_id}/security",
     "examples": ["Which collateral actually helps?", "What is the cheapest security package that clears the hurdle?"],
     "answers": "Recovery value, LGD effect, CRM eligibility and RWA effect of each security item, and the cheapest package that clears."},
    {"id": "dealdesk.approval.consistency", "label": "Decision consistency", "path": PREFIX + "/{deal_id}/consistency",
     "examples": ["Were similar deals decided differently?", "Are our approvals consistent?"],
     "answers": "Similar deals (sector, rating, size, structure) decided differently, with the differences that explain it or fail to."},
]


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        return ""


def _run(call: str, request: Request, pid: str, fn: Callable[..., dict[str, Any]], *a: Any) -> dict[str, Any]:
    try:
        out = fn(*a)
    except common.UnknownDeal:
        raise HTTPException(404, f"No deal {pid}.") from None
    except engine.TermsError as e:
        raise HTTPException(422, {"errors": e.errors, "message": str(e)}) from None
    out = engine.public(out)
    try:
        tid = trace.record(call, {"deal_id": pid}, out, params.versions(), pd_model.model_meta()["version"], _user(request))
    except Exception:  # noqa: BLE001 - tracing never blocks an answer
        tid = None
    return {"trace_id": tid, **out}


@router.get("/intents")
def intents() -> dict[str, Any]:
    return {"intents": INTENTS}


@router.get("/{pid}/challenger")
def get_challenger(pid: str, request: Request) -> dict[str, Any]:
    return _run("intel.approval.challenger", request, pid, challenger.challenge, pid)


@router.get("/{pid}/reverse")
def get_reverse(pid: str, request: Request, max_seconds: float = Query(25.0, ge=5.0, le=60.0)) -> dict[str, Any]:
    return _run("intel.approval.reverse", request, pid, reverse.solve, pid, max_seconds)


@router.get("/{pid}/security")
def get_security(pid: str, request: Request) -> dict[str, Any]:
    return _run("intel.approval.security", request, pid, security.optimise, pid)


@router.get("/{pid}/consistency")
def get_consistency(pid: str, request: Request) -> dict[str, Any]:
    if pid.lower() == "book":
        return _run("intel.approval.consistency.book", request, pid, consistency.book)
    return _run("intel.approval.consistency", request, pid, consistency.consistency, pid)
