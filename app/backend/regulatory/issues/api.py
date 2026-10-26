"""Issue-view endpoints (PLAN_R14 r, K2/K4), mounted on the Deal Desk service next to Noor's brief.

    GET /api/v1/regulatory/issues              every open issue (checks in breach, ECL data issues, large exposures)
    GET /api/v1/regulatory/issues/{issue_id}   one issue view: headline, plain words, rule, bank vs requirement,
                                               tables, shortfall bridge, concentration, impact, actions, source, gaps
Deterministic (no model call): the same books give the same view.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.regulatory.issues import service

router = APIRouter(prefix="/api/v1/regulatory/issues", tags=["regulatory-issues"])


@router.get("")
def list_issues(today: str = Query("")) -> dict[str, Any]:
    return service.list_issues(today or None)


@router.get("/{issue_id:path}")
def get_issue(issue_id: str, today: str = Query("")) -> dict[str, Any]:
    try:
        return service.get(issue_id, today or None)
    except service.UnknownIssue:
        raise HTTPException(404, "That issue is not on the books any more.") from None
