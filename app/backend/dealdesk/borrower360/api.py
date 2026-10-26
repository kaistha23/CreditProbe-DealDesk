"""Round B: Borrower 360 inside the deal and the customer file.

    GET /api/v1/dealdesk/borrower-360?cif=<id>            the customer's 360 (Deal Desk's borrower links land on it)
    GET /api/v1/dealdesk/borrower-360/deal/{pid}          the 360 of a deal's borrower
    (both take refresh=true to rebuild past the ten-minute cache)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.dealdesk.borrower360 import service as S

PREFIX = "/api/v1/dealdesk/borrower-360"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-borrower-360"])


@router.get("")
def by_cif(cif: str = Query(..., min_length=1), refresh: bool = Query(False)) -> dict[str, Any]:
    try:
        return S.for_cif(cif, refresh)
    except S.NotFound as e:
        raise HTTPException(404, str(e)) from None


@router.get("/deal/{pid}")
def by_deal(pid: str, refresh: bool = Query(False)) -> dict[str, Any]:
    try:
        return S.for_deal(pid, refresh)
    except S.NotFound as e:
        raise HTTPException(404, str(e)) from None
