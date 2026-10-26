"""R13 IB routes: who to call today (prefix /api/v1/intel/calls).

  GET /calls          ?limit=25&offset=0&signal=&sector=&min_weight=&today=&scope=material|all   the ranked call list with reason and action
                      (R14 G: material = relationship EAD at or above the J9 floor, the default)
  GET /calls/signals  the signals, their weights and actions

Mounted by one line in the "# R13 routers" block of backend/dealdesk/api.py (the Deal Desk service hosts it, so the EWS tools
menu calls the Deal Desk origin). Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.intel.calls import engine

PREFIX = "/api/v1/intel/calls"
router = APIRouter(prefix=PREFIX, tags=["intel-calls"])


@router.get("")
def get_calls(limit: int = Query(25, ge=1, le=500), offset: int = Query(0, ge=0), signal: str = "", sector: str = "",
              min_weight: int = Query(0, ge=0, le=5), today: str | None = None,
              scope: str = Query("material", pattern="^(material|all)$")) -> dict[str, Any]:
    try:
        return engine.calls(limit, offset, signal, sector, min_weight, today, scope)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/signals")
def get_signals() -> dict[str, Any]:
    return {"signals": [{"id": k, "label": v[0], "weight": v[1], "action": v[2]} for k, v in engine.SIGNALS.items()],
            "method": (engine.__doc__ or "").strip()}
