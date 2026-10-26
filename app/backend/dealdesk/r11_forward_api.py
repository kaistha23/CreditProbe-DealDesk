"""R11 Session F routes: forward risk on a proposed deal (prefix /api/v1/dealdesk).

  POST /proposals/{pid}/forward-risk   body {structures?: [{key?, label, role?, terms}], terms?, el_view?, capital_basis?}
                                       (role from `key` when absent: ask, recommended, alternative_n; `terms` alone =
                                       the picked structure, scored next to the Optimise structures)
  GET  /forward-risk/model-card        the transition models' card, back-test and as-of book statistics

Mounted by one line in the "# R11 routers" block of backend/dealdesk/api.py. Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from backend.dealdesk import engine, forward_risk, params, pd_model, proposals, trace
from backend.dealdesk import transition_model as tm

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-forward-risk"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "")
    except Exception:  # noqa: BLE001 - answers without the Core service
        return ""


@router.post("/proposals/{pid}/forward-risk")
def post_forward_risk(pid: str, request: Request, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    body = body or {}
    try:
        p = proposals.get(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None
    if not tm.available():
        raise HTTPException(503, "The transition models are not exported (data/dealdesk/model/transition).")
    ev = body.get("el_view") or "economic"
    if ev not in ("economic", "accounting"):
        raise engine.TermsError([{"field": "el_view", "message": "economic or accounting"}])
    cb = body.get("capital_basis")
    if cb not in (None, "regulatory", "economic", "max"):
        raise engine.TermsError([{"field": "capital_basis", "message": "regulatory, economic or max"}])
    structures = body.get("structures")
    if structures is not None and (not isinstance(structures, list) or not all(isinstance(s, dict) for s in structures)):
        raise engine.TermsError([{"field": "structures", "message": "a list of {label, role, terms}"}])
    picked = body.get("terms")
    if picked is not None and not isinstance(picked, dict):
        raise engine.TermsError([{"field": "terms", "message": "the picked structure's terms"}])
    if picked and not structures:
        # the thread sends the structure on screen: score it next to the Optimise structures
        structures = forward_risk.default_structures(p, {"el_view": ev, "capital_basis": cb}) + [
            {"label": "Selected structure", "key": "selected", "role": "alternative", "terms": picked}]
    out = engine.public(forward_risk.forward_risk(p, structures, el_view=ev, capital_basis=cb))
    tid = trace.record("forward_risk", {"proposal_id": pid, **body}, out, params.versions(),
                       f"{pd_model.model_meta()['version']} + {tm.meta()['version']}", _user(request))
    return {"trace_id": tid, **out}


@router.get("/forward-risk/model-card")
def get_model_card() -> dict[str, Any]:
    if not tm.available():
        raise HTTPException(503, "The transition models are not exported (data/dealdesk/model/transition).")
    m = tm.meta()
    return engine.public({"version": m["version"], "trained": m["trained"], "as_of": m["as_of"], "features": m["features"],
                          "card": tm.card(), "backtest": tm.backtest()["by_quarter"], "chain": m["chain"],
                          "book": {t: {k: v for k, v in m["models"][t].items() if k not in ("calibration", "file", "sha256")}
                                   for t in tm.TARGETS},
                          "calibration": {t: m["models"][t]["calibration"] for t in tm.TARGETS},
                          "files": {t: {"file": f"data/dealdesk/model/transition/{m['models'][t]['file']}",
                                        "sha256": m["models"][t]["sha256"]} for t in tm.TARGETS},
                          "source": m["source"]})
