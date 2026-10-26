"""R12 Session C routes: group, governance, conduct and SWOT on a deal (prefix /api/v1/dealdesk). Additive only (N1).

  GET  /proposals/{pid}/group                 group facts (structure, shareholders and UBOs, board and links, insiders,
                                              ownership changes, shared collateral, guarantees, connected parties) and the
                                              group cap test with the increase-cap ask and its DoA
  GET  /proposals/{pid}/group/conduct         the conduct block
  GET  /proposals/{pid}/group/governance      governance and conduct red flags, rating overlay, condition templates, and the
                                              findings as `dd_review_finding` rows
  GET  /proposals/{pid}/group/overlay         the deal priced at the base and at the overlaid rating
  GET  /proposals/{pid}/group/cap-test        the cap test for the ask, or POST with {terms} for any structure
  GET  /proposals/{pid}/group/swot            SWOT with evidence links
  POST /proposals/{pid}/group/mitigants       weakness-to-mitigant map for {terms?, label?} (default: the ask)
  POST /proposals/{pid}/group/publish         publish findings (dd_review_finding) and SWOT (dd_swot) to Data Domains
  GET  /proposals/{pid}/group/all             everything above in one call (U's Structure and Review steps)

Every response carries `lineage`: the Data Domains relations and row keys it was computed from.
Mounted by one line in the "# R12 routers" block of backend/dealdesk/api.py.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from backend.dealdesk.group import exposure as X, flags as FL, service, sources as S, swot as SW

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-group"])


def _bundle(pid: str, refresh: bool = False) -> dict[str, Any]:
    try:
        return service.bundle(pid, refresh=refresh)
    except KeyError:
        raise HTTPException(404, f"No deal {pid}.") from None


def _with(b: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"proposal_id": b["proposal_id"], "as_of": b["as_of"], **kw, "figures": b.get("figures", {}), "lineage": b["lineage"], "not_published": b["not_published"],
            "gaps": b["gaps"]}


@router.get("/proposals/{pid}/group")
def get_group(pid: str, refresh: bool = Query(False)) -> dict[str, Any]:
    b = _bundle(pid, refresh)
    return _with(b, facts=b["facts"], cap_test=b["cap_test"])


@router.get("/proposals/{pid}/group/conduct")
def get_conduct(pid: str) -> dict[str, Any]:
    b = _bundle(pid)
    return _with(b, conduct=b["conduct"])


@router.get("/proposals/{pid}/group/governance")
def get_governance(pid: str) -> dict[str, Any]:
    b = _bundle(pid)
    return _with(b, governance=b["governance"], findings=FL.findings_rows(b["governance"]))


@router.get("/proposals/{pid}/group/overlay")
def get_overlay(pid: str) -> dict[str, Any]:
    b = _bundle(pid)
    return _with(b, **service.overlay_analysis(pid))


@router.get("/proposals/{pid}/group/cap-test")
def get_cap_test(pid: str) -> dict[str, Any]:
    b = _bundle(pid)
    return _with(b, cap_test=b["cap_test"])


@router.post("/proposals/{pid}/group/cap-test")
def post_cap_test(pid: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    b = _bundle(pid)
    try:
        S.reset()
        r = X.cap_test(pid, (body or {}).get("terms"))
    except KeyError:
        raise HTTPException(404, f"No deal {pid}.") from None
    except Exception as e:  # noqa: BLE001 -- bad terms
        raise HTTPException(422, str(e)) from None
    return _with(b, cap_test=r) | {"lineage": b["lineage"] + S.used()}


@router.get("/proposals/{pid}/group/swot")
def get_swot(pid: str) -> dict[str, Any]:
    b = _bundle(pid)
    return _with(b, swot=b["swot"])


@router.post("/proposals/{pid}/group/mitigants")
def post_mitigants(pid: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    body = body or {}
    b = _bundle(pid)
    try:
        m = SW.mitigants(pid, body.get("terms"), str(body.get("label") or ("chosen" if body.get("terms") else "ask")), b["swot"], b["governance"])
    except Exception as e:  # noqa: BLE001 -- bad terms
        raise HTTPException(422, str(e)) from None
    return _with(b, mitigants=m)


@router.post("/proposals/{pid}/group/publish")
def post_publish(pid: str) -> dict[str, Any]:
    _bundle(pid)
    return service.publish(pid)


@router.get("/proposals/{pid}/group/all")
def get_all(pid: str, refresh: bool = Query(False)) -> dict[str, Any]:
    b = _bundle(pid, refresh)
    m = SW.mitigants(pid, None, "ask", b["swot"], b["governance"])
    return _with(b, facts=b["facts"], cap_test=b["cap_test"], conduct=b["conduct"], governance=b["governance"], swot=b["swot"],
                 mitigants=m)
