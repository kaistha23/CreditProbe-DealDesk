"""R14 Session F API (prefix /api/v1/dealdesk), one include_router line in the `# R14 routers` block of backend/dealdesk/api.py.

Structure set and selection (K23, K25)
    GET  /proposals/{id}/structure-set                  Ask, Recommended, Alternatives, Your structures; the selected one; the sticky bar
    POST /proposals/{id}/structure-set/select           {key}: the selection (dd_structure_set selected_flag)
    POST /proposals/{id}/structure-set                  {label, terms, covenants?, select?}: save your own structure
Stress over structures and stress-proofing (K20, K23)
    POST /proposals/{id}/stress-matrix                  {keys?, force?}: structures x mild / moderate / severe
    POST /proposals/{id}/stress-proof                   {from_key?, target?}: the smallest change set that survives the target
    GET  /proposals/{id}/stress-proofs                  dd_stress_proof rows for the deal
Recommendation (K24) and pipeline test (K21)
    GET  /proposals/{id}/recommendation-r14             the Recommendation step content on the selected structure
    GET  /proposals/{id}/pipeline-lines?key=            the pipeline test on the selected structure, read on this deal's own lines
Monitoring (K35)
    GET  /monitoring/proposals/prefill                  ?proposal_id= | obligor_id=&source=&facility_ref=&obligor_name=&reason=
    POST /monitoring/proposals                          {proposal_id | obligor_id, tier, reason, review_frequency, triggers, owner, due_date, ...}
    POST /monitoring/proposals/{mid}/decide             {approve, note}: maker-checker
    GET  /monitoring/page                               the Monitoring page
    GET  /monitoring/proposals/obligor/{obligor_id}     the line Early Warning and Borrower 360 show
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk import engine, params, pd_model, trace
from backend.dealdesk.stressproof import matrix as MX
from backend.dealdesk.stressproof import monitoring as MON
from backend.dealdesk.stressproof import pipeline_lines as PL
from backend.dealdesk.stressproof import recommendation as REC
from backend.dealdesk.stressproof import solver as SV
from backend.dealdesk.stressproof import structures as ST

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-flow-r14"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        return ""


def _traced(call: str, request: Request, inputs: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out = engine.public(out)
    tid = trace.record(call, inputs, out, params.versions(), pd_model.model_meta()["version"], _user(request))
    return {"trace_id": tid, **out}


def _deal(pid: str) -> None:
    try:
        ST.deal(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None


# ------------------------------------------------------------------ structure set

@router.get("/proposals/{pid}/structure-set")
def structure_set(pid: str, request: Request) -> dict[str, Any]:
    _deal(pid)
    return _traced("structure_set", request, {"proposal_id": pid}, ST.structure_set(pid))


@router.post("/proposals/{pid}/structure-set/select")
def select(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _deal(pid)
    key = str((body or {}).get("key") or "")
    try:
        out = ST.select(pid, key, _user(request) or str((body or {}).get("by") or ""))
    except KeyError:
        raise HTTPException(404, f"No structure {key!r} on {pid}.") from None
    return _traced("structure_select", request, {"proposal_id": pid, "key": key}, out)


@router.post("/proposals/{pid}/structure-set")
def save_structure(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _deal(pid)
    body = body or {}
    if not isinstance(body.get("terms"), dict):
        raise engine.TermsError([{"field": "terms", "message": "an object of deal terms"}])
    out = ST.add(pid, str(body.get("label") or ""), "user", body["terms"], body.get("covenants"), origin="Built in Structure it yourself",
                 by=_user(request), select_it=bool(body.get("select")))
    return _traced("structure_save", request, {"proposal_id": pid, **body}, out)


# ------------------------------------------------------------------ stress matrix and stress-proofing

@router.post("/proposals/{pid}/stress-matrix")
def stress_matrix(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _deal(pid)
    body = body or {}
    keys, force = body.get("keys"), body.get("force")
    for name, v in (("keys", keys), ("force", force)):
        if v is not None and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise engine.TermsError([{"field": name, "message": "a list of structure keys"}])
    try:
        out = MX.run(pid, keys, force)
    except KeyError:
        raise HTTPException(404, "None of the structures asked for is on this deal.") from None
    return _traced("stress_matrix", request, {"proposal_id": pid, **body}, out)


@router.post("/proposals/{pid}/stress-proof")
def stress_proof(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _deal(pid)
    body = body or {}
    try:
        out = SV.proof(pid, body.get("from_key"), str(body.get("target") or "moderate"), by=_user(request))
    except SV.ProofError as e:
        raise HTTPException(422, str(e)) from None
    except KeyError:
        raise HTTPException(404, f"No structure {body.get('from_key')!r} on {pid}.") from None
    return _traced("stress_proof", request, {"proposal_id": pid, **body}, out)


@router.get("/proposals/{pid}/stress-proofs")
def stress_proofs(pid: str, request: Request) -> dict[str, Any]:
    _deal(pid)
    from backend.dealdesk.data import store
    try:
        rows = store.dd_read("dd_stress_proof", proposal_id=pid)
    except Exception:  # noqa: BLE001
        rows = []
    return _traced("stress_proofs", request, {"proposal_id": pid}, {"proposal_id": pid, "rows": rows})


# ------------------------------------------------------------------ recommendation and pipeline lines

@router.get("/proposals/{pid}/recommendation-r14")
def recommendation(pid: str, request: Request) -> dict[str, Any]:
    _deal(pid)
    return _traced("recommendation_r14", request, {"proposal_id": pid}, REC.build(pid))


@router.get("/proposals/{pid}/pipeline-lines")
def pipeline_lines(pid: str, request: Request, key: str | None = Query(None)) -> dict[str, Any]:
    _deal(pid)
    try:
        out = PL.run(pid, key)
    except KeyError as e:
        raise HTTPException(404, f"Not in the pipeline: {e.args[0] if e.args else pid}.") from None
    return _traced("pipeline_lines", request, {"proposal_id": pid, "key": key}, out)


# ------------------------------------------------------------------ monitoring

@router.get("/monitoring/proposals/prefill")
def monitoring_prefill(request: Request, proposal_id: str | None = Query(None), obligor_id: str | None = Query(None),
                       source: str = Query("deal"), facility_ref: str = Query("ALL"), obligor_name: str = Query(""),
                       reason: str = Query("")) -> dict[str, Any]:
    if not (proposal_id or obligor_id):
        raise HTTPException(422, "proposal_id or obligor_id is required")
    ev = [{"label": "From the list", "value": reason, "relation": source}] if reason else None
    out = MON.prefill(proposal_id, obligor_id, source, facility_ref, ev, obligor_name)
    return _traced("monitoring_prefill", request, {"proposal_id": proposal_id, "obligor_id": obligor_id, "source": source}, out)


@router.post("/monitoring/proposals")
def monitoring_propose(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    body = body or {}
    try:
        out = MON.propose(body, _user(request) or str(body.get("maker") or ""))
    except MonitoringErrorTypes as e:
        raise HTTPException(422, str(e)) from None
    return _traced("monitoring_propose", request, body, out)


@router.post("/monitoring/proposals/{mid}/decide")
def monitoring_decide(mid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    body = body or {}
    try:
        out = MON.decide(mid, bool(body.get("approve")), _user(request) or str(body.get("checker") or ""), str(body.get("note") or ""))
    except KeyError:
        raise HTTPException(404, f"No monitoring proposal {mid}.") from None
    except MonitoringErrorTypes as e:
        raise HTTPException(409, str(e)) from None
    return _traced("monitoring_decide", request, {"id": mid, **body}, out)


@router.get("/monitoring/page")
def monitoring_page(request: Request) -> dict[str, Any]:
    return _traced("monitoring_page", request, {}, MON.page(_user(request)))


@router.get("/monitoring/proposals/obligor/{obligor_id}")
def monitoring_obligor(obligor_id: str, request: Request) -> dict[str, Any]:
    return _traced("monitoring_obligor", request, {"obligor_id": obligor_id}, MON.for_obligor(obligor_id))


MonitoringErrorTypes = (MON.MonitoringError,)
