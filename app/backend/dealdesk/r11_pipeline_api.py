"""R11 Session L API (PLAN_R11 Contracts): the pending pipeline, the pipeline optimiser, the pipeline test and the
risk appetite, under /api/v1/dealdesk. Mounted by one `include_router` line in the "# R11 routers" block of api.py.

    GET  /pipeline                        pending deals (Deal Desk, uploads, the pipeline set) and the budget defaults
    POST /pipeline/optimise               {deal_ids?, rwa_budget?, el_budget?} -> the exact selection, limits, frontier
    POST /proposals/{id}/pipeline-test    {terms?, deal_ids?, rwa_budget?, el_budget?} -> does it make the cut
    GET  /risk-appetite                   the book today against every limit (value, appetite, trigger, limit, status, basis)

Every response carries a calculation trace ID (GET /traces/{id}), as the engine's own endpoints do.
"""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from backend.dealdesk import engine, params, pd_model, pipeline, risk_appetite_view, trace

PREFIX = "/api/v1/dealdesk"
_SOLVE_LOCK = threading.Lock()


_WARMED: list[bool] = []


def _warm() -> None:
    """Solve the default pipeline once in the background (at start-up, or when Pipeline mode first lists the deals),
    so Optimise pipeline answers from the cache (results are cached on their inputs). Off with DEALDESK_PIPELINE_WARM=0."""
    import os
    if os.environ.get("DEALDESK_PIPELINE_WARM", "1") == "0" or _WARMED:
        return
    _WARMED.append(True)

    def run() -> None:
        try:
            with _SOLVE_LOCK:
                pipeline.optimise()
        except Exception:  # noqa: BLE001 - a warm-up failure only means the first click computes
            pass
    threading.Thread(target=run, name="dealdesk-pipeline-warm", daemon=True).start()


router = APIRouter(prefix=PREFIX, tags=["dealdesk-r11-pipeline"], on_startup=[_warm])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "")
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        return ""


def _traced(call: str, request: Request, inputs: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out = engine._clean(out)
    tid = trace.record(call, inputs, out, params.versions(), pd_model.model_meta()["version"], _user(request))
    return {"trace_id": tid, **out}


def _num(body: dict[str, Any], key: str) -> float | None:
    v = body.get(key)
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise engine.TermsError([{"field": key, "message": "must be a number (SAR m)"}]) from None
    if f < 0:
        raise engine.TermsError([{"field": key, "message": "must be zero or more (SAR m)"}])
    return f


def _ids(body: dict[str, Any]) -> list[str] | None:
    ids = body.get("deal_ids")
    if ids is None:
        return None
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        raise engine.TermsError([{"field": "deal_ids", "message": "a list of proposal IDs"}])
    return ids


@router.get("/pipeline")
def get_pipeline(request: Request) -> dict[str, Any]:
    _warm()
    return _traced("pipeline", request, {}, pipeline.listing())


@router.post("/pipeline/optimise")
def optimise_pipeline(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    ids = _ids(body)
    rwa, el = _num(body, "rwa_budget"), _num(body, "el_budget")
    try:
        with _SOLVE_LOCK:
            out = pipeline.optimise(ids, rwa, el)
    except KeyError as e:
        raise HTTPException(404, f"Not pending in the pipeline: {e.args[0]}.") from None
    return _traced("pipeline_optimise", request, {"deal_ids": ids, "rwa_budget": rwa, "el_budget": el}, out)


@router.post("/proposals/{pid}/pipeline-test")
def pipeline_test(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    try:
        pipeline.get(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None
    terms = body.get("terms")
    if terms is not None and not isinstance(terms, dict):
        raise engine.TermsError([{"field": "terms", "message": "an object of deal terms"}])
    ids = _ids(body)
    rwa, el = _num(body, "rwa_budget"), _num(body, "el_budget")
    try:
        with _SOLVE_LOCK:
            out = pipeline.pipeline_test(pid, terms, ids, rwa, el)
    except KeyError as e:
        raise HTTPException(404, f"Not pending in the pipeline: {e.args[0]}.") from None
    return _traced("pipeline_test", request, {"proposal_id": pid, "terms": terms, "deal_ids": ids, "rwa_budget": rwa,
                                              "el_budget": el}, out)


@router.get("/risk-appetite")
def risk_appetite(request: Request) -> dict[str, Any]:
    return _traced("risk_appetite", request, {}, risk_appetite_view.book_view())
