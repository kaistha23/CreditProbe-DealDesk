"""Attention-item chart data (v5 item 4), mounted on the Core service.

  GET /api/v1/attention/charts?domain=&family=&segment=&period=&comparison=

Needs a session. The item itself comes from the frozen Cockpit feed; this route only returns what explains it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.attention_v5 import charts
from backend.identity_v5.api import Ctx, require_ctx

router = APIRouter(prefix="/api/v1/attention")


@router.get("/charts")
def attention_charts(domain: str = Query(..., pattern="^(corporate|retail)$"), family: str = Query(..., max_length=80),
                     segment: str = Query(..., max_length=200), period: str | None = Query(None, max_length=10),
                     comparison: str | None = Query(None, max_length=10), ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    try:
        return charts.charts(domain, family, segment, period, comparison)
    except charts.Unavailable as exc:
        raise HTTPException(404, str(exc)) from exc
