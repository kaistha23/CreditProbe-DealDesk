"""R11 Session S: the Stress Lab API (prefix /api/v1/dealdesk), mounted on the engine app by one
include_router line in backend/dealdesk/api.py (# R11 routers).

    GET  /stress/scenarios            the scenario table (groups, shocks, basis, severity) and its transmission
    POST /proposals/{id}/stress       scenarios, reverse stress and asked-vs-recommended resilience on a structure

POST body (all optional):
    terms               the structure to stress (default: the ask)
    recommended_terms   the Optimise recommended structure (default: the optimiser's, as the deal view picks it)
    scenarios           scenario ids (default: all)
    custom              a shock spec, or text such as "revenue -20% and rates +150 bps"
    resilience          run asked and recommended (default true)
    breakevens          reverse stress (default true)
    el_view, capital_basis, structure_label
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from backend.dealdesk import engine, params, pd_model, proposals, stress_lab, trace

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-stress"])


def _traced(call: str, request: Request, inputs: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out = engine.public(out)
    user = ""
    try:
        from backend.identity_v5.client import current_user
        user = (current_user(request) or {}).get("username", "")
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        user = ""
    tid = trace.record(call, inputs, out, params.versions(), pd_model.model_meta()["version"], user)
    return {"trace_id": tid, **out}


@router.get("/stress/scenarios")
def stress_scenarios(request: Request) -> dict[str, Any]:
    return _traced("stress_scenarios", request, {}, stress_lab.scenarios_catalogue())


@router.post("/stress/parse")
def stress_parse(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Parse a typed shock ("revenue -20% and rates +150 bps") without running it."""
    return _traced("stress_parse", request, body, stress_lab.parse_custom(str(body.get("text") or "")))


@router.post("/proposals/{pid}/stress")
def proposal_stress(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    try:
        p = proposals.get(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None
    body = body or {}
    ev = body.get("el_view") or "economic"
    cb = body.get("capital_basis") or None
    if ev not in ("economic", "accounting"):
        raise engine.TermsError([{"field": "el_view", "message": "economic or accounting"}])
    if cb not in (None, "regulatory", "economic", "max"):
        raise engine.TermsError([{"field": "capital_basis", "message": "regulatory, economic or max"}])
    sc = body.get("scenarios")
    if sc is not None and not (isinstance(sc, list) and all(isinstance(x, str) for x in sc)):
        raise engine.TermsError([{"field": "scenarios", "message": "a list of scenario ids"}])
    custom = body.get("custom")
    if custom is not None and not isinstance(custom, (str, dict)):
        raise engine.TermsError([{"field": "custom", "message": "text or a shock spec"}])
    # validate the structure the way /compute does (bad terms are a 422)
    engine.analyse(p, body.get("terms"), el_view=ev, capital_basis=cb)
    r = stress_lab.run(p, body.get("terms"), scenario_ids=sc, custom=custom or None,
                       recommended=body.get("recommended_terms"), resilience=bool(body.get("resilience", True)),
                       breakevens=bool(body.get("breakevens", True)), el_view=ev, capital_basis=cb,
                       structure_label=body.get("structure_label"))
    return _traced("stress_lab", request, {"proposal_id": pid, **body}, r)
