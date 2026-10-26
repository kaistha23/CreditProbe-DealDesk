"""R14 i API: deal intelligence D6-D13 (prefix /api/v1/dealdesk/intel2), mounted by one include_router line in the R14
block of backend/dealdesk/api.py.

  GET  /intel2/{id}/frontier        D6  negotiation frontier
  GET  /intel2/{id}/premortem       D7  default pre-mortem
  GET  /intel2/{id}/precedents      D8  precedent explorer
  GET  /intel2/{id}/pricing         D9  pricing benchmark
  GET  /intel2/{id}/revenue         D10 revenue truth check
  GET  /intel2/{id}/renewal-diff    D11 renewal diff
  GET  /intel2/{id}/contagion       D12 group contagion on the deal
  GET  /intel2/{id}/rehearsal       D13 committee rehearsal (K29)
  POST /intel2/{id}/publish         the deal's D6-D13 results into Data Domains (dd_deal_intel)
  GET  /intel2/intents              the intent descriptors Noor's Ask uses

Query: structure=selected (default: the selected structure, else the Optimise recommended one) | recommended | ask;
terms=<JSON> (the page's own terms, wins). {id}: dd_deal id; twin aliases (PRP-B-ASB / TWIN-A, PRP-A-GMC / TWIN-B).
Every figure is {value, unit, source} with Data Domains lineage; every text is a deterministic writer's (N4).
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.dealdesk import engine, params, pd_model, trace
from backend.dealdesk.intel2 import ENGINES
from backend.dealdesk.intel2 import common as C

PREFIX = "/api/v1/dealdesk/intel2"
router = APIRouter(prefix=PREFIX, tags=["r14-intel2"])

INTENTS = [
    {"id": "dealdesk.intel2.frontier", "code": "D6", "label": "Negotiation frontier", "path": PREFIX + "/{deal_id}/frontier",
     "examples": ["What is 10% cash margin worth in bps?", "Give me three counter-offers the client will accept."]},
    {"id": "dealdesk.intel2.premortem", "code": "D7", "label": "Default pre-mortem", "path": PREFIX + "/{deal_id}/premortem",
     "examples": ["How could this deal go bad?", "What would warn us first?"]},
    {"id": "dealdesk.intel2.precedents", "code": "D8", "label": "Precedent explorer", "path": PREFIX + "/{deal_id}/precedents",
     "examples": ["Show me the closest past deals.", "What did we decide on deals like this and how did they perform?"]},
    {"id": "dealdesk.intel2.pricing", "code": "D9", "label": "Pricing benchmark", "path": PREFIX + "/{deal_id}/pricing",
     "examples": ["Is this margin in line with the book?", "Where does the pricing sit against similar deals?"]},
    {"id": "dealdesk.intel2.revenue", "code": "D10", "label": "Revenue truth check", "path": PREFIX + "/{deal_id}/revenue",
     "examples": ["Is the reported revenue real?", "Does account turnover support the revenue?"]},
    {"id": "dealdesk.intel2.renewal_diff", "code": "D11", "label": "Renewal diff", "path": PREFIX + "/{deal_id}/renewal-diff",
     "examples": ["What changed since the last approval?", "Show the renewal diff."]},
    {"id": "dealdesk.intel2.contagion", "code": "D12", "label": "Group contagion on the deal", "path": PREFIX + "/{deal_id}/contagion",
     "examples": ["Are any connected parties in Stage 3?", "What happens to this deal if the group fails?"]},
    {"id": "dealdesk.intel2.rehearsal", "code": "D13", "label": "Committee rehearsal", "path": PREFIX + "/{deal_id}/rehearsal",
     "examples": ["Rehearse the committee for this deal.", "What will committee ask and how do we answer?"]},
]


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def _terms(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        t = json.loads(raw)
    except ValueError:
        raise HTTPException(422, {"message": "terms must be a JSON object"}) from None
    if not isinstance(t, dict):
        raise HTTPException(422, {"message": "terms must be a JSON object"})
    return {k: v for k, v in t.items() if k in engine.TERM_KEYS}


def run(code: str, pid: str, structure: str = "selected", terms: dict[str, Any] | None = None, request: Request | None = None) -> dict[str, Any]:
    key, fn = ENGINES[code]
    try:
        out = fn(pid, structure, terms)
    except C.UnknownDeal:
        raise HTTPException(404, f"No deal {pid}.") from None
    except engine.TermsError as e:
        raise HTTPException(422, {"errors": e.errors, "message": str(e)}) from None
    out = engine.public(out)
    out["feature"] = code
    try:
        tid = trace.record(f"intel2.{key}", {"deal_id": pid, "structure": structure}, out, params.versions(), pd_model.model_meta()["version"],
                           _user(request) if request else "")
    except Exception:  # noqa: BLE001 - tracing never blocks an answer
        tid = None
    return {"trace_id": tid, **out}


@router.get("/intents")
def intents() -> dict[str, Any]:
    return {"intents": INTENTS}


def _mk(code: str, key: str):  # noqa: ANN202
    def handler(pid: str, request: Request, structure: str = Query("selected", pattern="^(selected|recommended|ask)$"),
                terms: str | None = Query(None)) -> dict[str, Any]:
        return run(code, pid, structure, _terms(terms), request)
    handler.__name__ = f"get_{key.replace('-', '_')}"
    return handler


for _code, (_key, _fn) in ENGINES.items():
    router.add_api_route(f"/{{pid}}/{_key}", _mk(_code, _key), methods=["GET"], name=f"intel2_{_key}")


@router.post("/{pid}/publish")
def publish(pid: str) -> dict[str, Any]:
    from backend.dealdesk.data import store
    from backend.dealdesk.intel2 import publish as P
    try:
        rows = P.rows_for(C.resolve_id(pid))
    except C.UnknownDeal:
        raise HTTPException(404, f"No deal {pid}.") from None
    r = store.publish("dd_deal_intel", rows, mode="upsert", actor="R14-I")
    return {"published": True, "relation": "dd_deal_intel", "rows": len(rows), "version": r.get("version")}
