"""Round S: the Intelligence Studio API on the Deal Desk service.

    GET /api/v1/dealdesk/intelligence-studio                 every section (headline, plain words, the eight sections)
    GET /api/v1/dealdesk/intelligence-studio/{section}       one section: customers, documents, proposals, rules,
                                                             policies, reader, corrections, governance (?module=)
Read-only.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.dealdesk.intelligence_studio import service

PREFIX = "/api/v1/dealdesk/intelligence-studio"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-intelligence-studio"])
SECTIONS = {"customers": service.customers, "documents": service.documents, "proposals": service.proposals, "rules": service.rules,
            "policies": service.policies, "reader": service.reader, "corrections": service.corrections}


@router.get("")
def overview(module: str = Query("", description="model governance for one module (deal_desk, ...); empty = all")) -> dict[str, Any]:
    return service.overview(module)


@router.get("/{section}")
def section(section: str, module: str = Query("")) -> dict[str, Any]:
    if section == "governance":
        return service.governance(module)
    fn = SECTIONS.get(section)
    if fn is None:
        raise HTTPException(404, f"No section {section}. Sections: {', '.join([*SECTIONS, 'governance'])}.")
    return fn()
