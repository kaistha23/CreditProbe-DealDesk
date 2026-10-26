"""PLAN_R12 Session P routes: product analytics (prefix /api/v1/dealdesk/products).

  GET  /products/{pid}/project            financed-projects status, cash-flow deficit and peak month, payment-delay
                                          stress (30/60/90 days), cover ratio, LGs with CCFs, employer credit
  GET  /products/{pid}/escrow             escrow waterfall, release rules, cover ratio, collections
  GET  /products/{pid}/syndication        our share, hold and sell-down, role, analytics on our share
  GET  /products/sme/fast-track           the SME lane: every application with its decision (?status=)
  GET  /products/sme/fast-track/count     the landing card count (Session U)
  GET  /products/sme/fast-track/{aid}     one application: score, rules, DoA, decision, conditions, short paper
  POST /products/sme/fast-track/{aid}/decide   records the decision (publishes it where the contract defines a relation)
  GET  /products/{pid}/sections           the deal's product (E's template) and the product sections that have data
  GET  /products/{pid}/lineage            every figure of the product sections with its domain, relation and row

Mounted by one line in the "# R12 routers" block of backend/dealdesk/api.py. Additive only (N1). Each GET answers
with a trace id (`backend.dealdesk.trace`).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.dealdesk.products import escrow, lineage, project, sme, source, syndication

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-products"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "")
    except Exception:  # noqa: BLE001 - answers without the Core service
        return ""


def _traced(kind: str, inputs: dict[str, Any], out: dict[str, Any], user: str) -> dict[str, Any]:
    try:
        from backend.dealdesk import params, trace
        tid = trace.record(kind, inputs, out, params.versions(), "products-r12", user)
    except Exception:  # noqa: BLE001 - a trace never breaks an answer
        tid = None
    return {"trace_id": tid, "data_available": source.available(), **out}


@router.get("/products/sme/fast-track")
def sme_lane(request: Request, status: str = Query(default="")) -> dict[str, Any]:
    return _traced("products_sme_lane", {"status": status}, sme.lane(status), _user(request))


@router.get("/products/sme/fast-track/count")
def sme_count() -> dict[str, Any]:
    return {"data_available": source.available(), **sme.counts()}


@router.get("/products/sme/fast-track/{aid}")
def sme_one(aid: str, request: Request) -> dict[str, Any]:
    d = sme.get(aid)
    if d is None:
        raise HTTPException(404, f"No SME application {aid}.")
    return _traced("products_sme", {"application_id": aid}, d, _user(request))


@router.post("/products/sme/fast-track/{aid}/decide")
def sme_decide(aid: str, request: Request) -> dict[str, Any]:
    d = sme.get(aid)
    if d is None:
        raise HTTPException(404, f"No SME application {aid}.")
    pub = sme.publish_decision(d, _user(request))
    return _traced("products_sme_decide", {"application_id": aid}, {**d, "published": pub}, _user(request))


@router.get("/products/{pid}/project")
def get_project(pid: str, request: Request) -> dict[str, Any]:
    return _traced("products_project", {"proposal_id": pid}, project.analyse(pid), _user(request))


@router.get("/products/{pid}/escrow")
def get_escrow(pid: str, request: Request) -> dict[str, Any]:
    return _traced("products_escrow", {"proposal_id": pid}, escrow.analyse(pid), _user(request))


@router.get("/products/{pid}/syndication")
def get_syndication(pid: str, request: Request) -> dict[str, Any]:
    return _traced("products_syndication", {"proposal_id": pid}, syndication.analyse(pid), _user(request))


@router.get("/products/{pid}/sections")
def get_sections(pid: str) -> dict[str, Any]:
    """Which product sections a deal shows: its product template (E) and the sections that have data."""
    product = "corporate"
    try:
        from backend.dealdesk.data import deals
        product = deals.product_of(pid)
    except Exception:  # noqa: BLE001
        pass
    has = {"project": bool(source.read("dd_project", proposal_id=pid) or source.read("dd_project_cashflow", proposal_id=pid)),
           "escrow": bool(source.read("dd_escrow_account", proposal_id=pid)),
           "syndication": bool(source.read("dd_syndication", proposal_id=pid)),
           "sme": bool(source.read("dd_sme_application", proposal_id=pid))}
    order = {"contracting": ["project"], "escrow": ["escrow"], "syndicated": ["syndication"], "sme": ["sme"]}.get(product, [])
    sections = [s for s in order if has[s]] + [s for s, ok in has.items() if ok and s not in order]
    return {"proposal_id": pid, "product": product, "sections": sections}


@router.get("/products/{pid}/lineage")
def get_lineage(pid: str) -> dict[str, Any]:
    return lineage.for_proposal(pid)
