"""R12 Session D API (prefix /api/v1/dealdesk), mounted by one include_router line in the `# R12 routers` block of
backend/dealdesk/api.py. Additive only: the R11 Stress Lab endpoints (/stress/scenarios, /proposals/{id}/stress) stay.

Stress Lab (ladder)
    GET  /stress2/catalogue?proposal_id=          families, the scenarios in force, sensitivity versions
    POST /proposals/{id}/stress2                  the ladder run: rows, reverse stress, chain, verdict, tier, commentary
    POST /proposals/{id}/stress2/chain/{sid}      one scenario's transmission chain and the "how was it built" answer
    POST /stress2/ask                             {proposal_id, question, terms?}: "how was this scenario built"
    GET  /proposals/{id}/stress2/notches          the rating family applied directly, R11 vs checked RAROC (O4)
    GET  /proposals/{id}/stress2/results          dd_stress_result rows for the deal
Scenario editor and sets
    POST /stress2/scenarios                       save (deal: in force; bank: pending the checker)
    GET  /stress2/scenarios/pending               bank versions awaiting a checker
    POST /stress2/scenarios/{sid}/decide          {version, approve, reason}: maker-checker
    POST /stress2/scenarios/{sid}/retire          {reason, proposal_id?}
    GET  /stress2/scenarios/{sid}/history
    GET  /stress2/import/template?fmt=csv|json
    POST /stress2/import                          {content, set, authority, fmt?}
    GET  /stress2/sensitivities                   current version rows and every version
    POST /stress2/sensitivities/override          {sensitivity_id, sector, value, reason}
    POST /stress2/sensitivities/{version}/decide  {approve, reason}
Monitoring plan and Early Warning
    POST /proposals/{id}/monitoring-plan          at approval: {terms?, reason?} -> dd_monitoring_plan (+ dd_stress_result)
    GET  /proposals/{id}/monitoring-plan          current plan and its history
    POST /proposals/{id}/monitoring-plan/tier     {tier, reason}: change with a reason (logged)
    GET  /monitoring/plans                        every current plan (the Book)
    GET  /monitoring/ews/{customer_id}            the EWS customer page panel
    GET  /monitoring/cards                        Book cards (alerts raised, drivers watched)
    GET  /monitoring/tier-high-movers             for Noor's brief
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk import engine, params, pd_model, proposals, trace
from backend.dealdesk.monitoring import plan as mp
from backend.dealdesk.stress2 import catalogue as cat
from backend.dealdesk.stress2 import chain as ch
from backend.dealdesk.stress2 import editor as ed
from backend.dealdesk.stress2 import ladder, store

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-stress-r12"])


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


def _p(pid: str) -> dict[str, Any]:
    try:
        return store.deal(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None


def _ed(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ed.EditorError as e:
        raise HTTPException(422, {"errors": e.errors, "message": str(e)}) from None


def _who(request: Request, body: dict[str, Any], key: str) -> str:
    return _user(request) or str(body.get(key) or "")


def _kw(body: dict[str, Any]) -> dict[str, Any]:
    ev = body.get("el_view") or "economic"
    cb = body.get("capital_basis") or None
    if ev not in ("economic", "accounting"):
        raise engine.TermsError([{"field": "el_view", "message": "economic or accounting"}])
    if cb not in (None, "regulatory", "economic", "max"):
        raise engine.TermsError([{"field": "capital_basis", "message": "regulatory, economic or max"}])
    return {"el_view": ev, "capital_basis": cb}


# ------------------------------------------------------------------ the ladder

@router.get("/stress2/catalogue")
def catalogue(request: Request, proposal_id: str | None = Query(None)) -> dict[str, Any]:
    return _traced("stress2_catalogue", request, {"proposal_id": proposal_id}, cat.catalogue(proposal_id))


@router.post("/proposals/{pid}/stress2")
def stress2(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    p = _p(pid)
    body = body or {}
    kw = _kw(body)
    sc = body.get("scenarios")
    if sc is not None and not (isinstance(sc, list) and all(isinstance(x, str) for x in sc)):
        raise engine.TermsError([{"field": "scenarios", "message": "a list of scenario ids"}])
    engine.analyse(p, body.get("terms"), **kw)  # bad terms are a 422, as /compute
    out = ladder.run(p, body.get("terms"), scenario_ids=sc, structure_label=body.get("structure_label"),
                     reverse=bool(body.get("reverse", True)), sensitivity_version=body.get("sensitivity_version"),
                     publish=bool(body.get("publish", True)), include_chain=bool(body.get("include_chain", False)), **kw)
    return _traced("stress2", request, {"proposal_id": pid, **body}, out)


@router.post("/proposals/{pid}/stress2/chain/{sid}")
def chain(pid: str, sid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _p(pid)
    out = ch.explain(pid, sid, (body or {}).get("terms"))
    if out["row"] is None:
        raise HTTPException(404, out["answer"])
    return _traced("stress2_chain", request, {"proposal_id": pid, "scenario": sid}, out)


@router.post("/stress2/ask")
def ask(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    pid = str(body.get("proposal_id") or "")
    _p(pid)
    out = ch.answer_question(pid, str(body.get("question") or ""), body.get("terms"))
    return _traced("stress2_ask", request, body, out)


@router.get("/proposals/{pid}/stress2/notches")
def notches(pid: str, request: Request, up_to: int = Query(4, ge=1, le=8)) -> dict[str, Any]:
    from backend.dealdesk import stress_lab as sl
    from backend.dealdesk.stress2 import raroc_check
    p = _p(pid)
    lab = sl.Lab(p, None)
    return _traced("stress2_notches", request, {"proposal_id": pid}, {"proposal_id": pid, "rows": raroc_check.notch_ladder(lab, up_to)})


@router.get("/proposals/{pid}/stress2/results")
def results(pid: str, request: Request) -> dict[str, Any]:
    _p(pid)
    rows = store.read("dd_stress_result", proposal_id=pid)
    return _traced("stress2_results", request, {"proposal_id": pid},
                   {"proposal_id": pid, "rows": rows[-200:], "runs": sorted({r["run_id"] for r in rows}), "backend": store.backend("dd_stress_result")})


# ------------------------------------------------------------------ the editor

@router.post("/stress2/scenarios")
def save_scenario(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    scope = body.get("scope") or "deal"
    if scope == "deal" and body.get("proposal_id"):
        _p(str(body["proposal_id"]))
    row = _ed(ed.save, body.get("scenario") or body, scope=scope, maker=_who(request, body, "maker"),
              proposal_id=body.get("proposal_id"), reason=str(body.get("reason") or ""), scenario_id=body.get("scenario_id"))
    return _traced("stress2_save", request, body, {"scenario": row})


@router.get("/stress2/scenarios/pending")
def pending(request: Request) -> dict[str, Any]:
    return _traced("stress2_pending", request, {}, {"pending": ed.pending()})


@router.post("/stress2/scenarios/{sid}/decide")
def decide(sid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    row = _ed(ed.decide, sid, int(body.get("version") or 0), checker=_who(request, body, "checker"),
              approve=bool(body.get("approve")), reason=str(body.get("reason") or ""))
    return _traced("stress2_decide", request, {"scenario_id": sid, **body}, {"scenario": row})


@router.post("/stress2/scenarios/{sid}/retire")
def retire(sid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    row = _ed(ed.retire, sid, maker=_who(request, body or {}, "maker"), reason=str((body or {}).get("reason") or ""),
              proposal_id=(body or {}).get("proposal_id"))
    return _traced("stress2_retire", request, {"scenario_id": sid, **(body or {})}, {"scenario": row})


@router.get("/stress2/scenarios/{sid}/history")
def history(sid: str, request: Request) -> dict[str, Any]:
    return _traced("stress2_history", request, {"scenario_id": sid}, {"scenario_id": sid, "versions": ed.history(sid)})


@router.get("/stress2/import/template")
def template(request: Request, fmt: str = Query("csv")) -> dict[str, Any]:
    if fmt not in ("csv", "json"):
        raise HTTPException(422, "fmt is csv or json")
    return _traced("stress2_template", request, {"fmt": fmt}, ed.template(fmt))


@router.post("/stress2/import")
def import_set(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    out = _ed(ed.import_set, str(body.get("content") or ""), set_name=str(body.get("set") or ""),
              authority=str(body.get("authority") or ""), maker=_who(request, body, "maker"), fmt=body.get("fmt"))
    return _traced("stress2_import", request, {k: v for k, v in body.items() if k != "content"}, out)


@router.get("/stress2/sensitivities")
def sensitivities(request: Request, version: str | None = Query(None)) -> dict[str, Any]:
    s = cat.Sensitivities(version)
    rows = sorted(({k: v for k, v in r.items()} for r in s.rows.values()), key=lambda r: (r["sensitivity_id"], r["sector"]))
    return _traced("stress2_sensitivities", request, {"version": version},
                   {"version": s.version, "rows": rows, "versions": cat.sensitivity_versions(), "meta": {k: list(v) for k, v in cat.SENS_META.items()}})


@router.post("/stress2/sensitivities/override")
def override(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        val = float(body.get("value"))
    except (TypeError, ValueError):
        raise HTTPException(422, "value must be a number") from None
    out = _ed(ed.propose_sensitivity, str(body.get("sensitivity_id") or ""), str(body.get("sector") or "*"), val,
              maker=_who(request, body, "maker"), reason=str(body.get("reason") or ""))
    return _traced("stress2_override", request, body, out)


@router.post("/stress2/sensitivities/{version}/decide")
def decide_sens(version: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    out = _ed(ed.decide_sensitivity, version, checker=_who(request, body, "checker"), approve=bool(body.get("approve")),
              reason=str(body.get("reason") or ""))
    return _traced("stress2_decide_sens", request, {"version": version, **body}, out)


# ------------------------------------------------------------------ monitoring plan and Early Warning

def _pe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except mp.PlanError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/proposals/{pid}/monitoring-plan")
def plan_publish(pid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _p(pid)
    body = body or {}
    out = _pe(mp.publish_at_approval, pid, body.get("terms"), approved_by=_who(request, body, "approved_by"),
              reason=str(body.get("reason") or ""), **_kw(body))
    return _traced("monitoring_plan_publish", request, {"proposal_id": pid, **body}, out)


@router.get("/proposals/{pid}/monitoring-plan")
def plan_get(pid: str, request: Request) -> dict[str, Any]:
    _p(pid)
    return _traced("monitoring_plan", request, {"proposal_id": pid},
                   {"proposal_id": pid, "plan": mp.current(pid), "history": mp.history(pid), "backend": store.backend("dd_monitoring_plan")})


@router.post("/proposals/{pid}/monitoring-plan/tier")
def plan_tier(pid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _p(pid)
    out = _pe(mp.change_tier, pid, str(body.get("tier") or ""), by=_who(request, body, "by"), reason=str(body.get("reason") or ""))
    return _traced("monitoring_tier", request, {"proposal_id": pid, **body}, out)


@router.get("/monitoring/plans")
def plans(request: Request) -> dict[str, Any]:
    return _traced("monitoring_plans", request, {}, {"plans": mp.all_current(), "backend": store.backend("dd_monitoring_plan")})


@router.get("/monitoring/ews/{customer_id}")
def ews_panel(customer_id: str, request: Request, period: str = Query("")) -> dict[str, Any]:
    from backend.ews_link import adapter
    return _traced("monitoring_ews", request, {"customer_id": customer_id, "period": period}, adapter.panel(customer_id, period))


@router.get("/monitoring/cards")
def cards(request: Request) -> dict[str, Any]:
    from backend.ews_link import adapter
    return _traced("monitoring_cards", request, {}, adapter.evaluate_all())


@router.get("/monitoring/tier-high-movers")
def movers(request: Request) -> dict[str, Any]:
    from backend.ews_link import adapter
    return _traced("monitoring_movers", request, {}, {"movers": adapter.tier_high_movers()})
