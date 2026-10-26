"""R13 IB routes: covenant designer (prefix /api/v1/dealdesk/intel/covenants).

  GET /covenants/{deal}     proposed covenants and thresholds for a Deal Desk deal (proposal id) or a book facility/borrower
                            (CF…/CB…): lead time, hit rate, false-alarm rate and precision from the bank's history, against the
                            template thresholds and the bank's as-set covenants; with the full candidate grid per covenant.
  GET /covenants/method     the method and its parameters
  (R14 G, K32: ?min_headroom=15 sets the minimum cushion from today's value; levels stay inside designer.BOUNDS)

Mounted by one line in the "# R13 routers" block of backend/dealdesk/api.py. Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.dealdesk.intel.covenants import designer

PREFIX = "/api/v1/dealdesk/intel/covenants"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-intel-covenants"])


@router.get("/method")
def get_method() -> dict[str, Any]:
    return {"method": (designer.__doc__ or "").strip(), "window_quarters": designer.WINDOW, "horizon_quarters": designer.HORIZON,
            "max_false_alarm": designer.MAX_FALSE_ALARM, "lead_target_quarters": list(designer.LEAD_TARGET),
            "min_early_hit": designer.MIN_EARLY_HIT, "min_headroom_pct": designer.MIN_HEADROOM_PCT,
            "bounds": {k: list(v) for k, v in designer.BOUNDS.items()}, "covenants": {k: v["label"] for k, v in designer.COVENANTS.items()}}


@router.get("/{deal}")
def get_design(deal: str, grid: bool = True,
               min_headroom: float = Query(designer.MIN_HEADROOM_PCT, ge=0.0, le=60.0)) -> dict[str, Any]:
    try:
        out = designer.design(deal, min_headroom)
    except KeyError:
        raise HTTPException(404, f"No deal or book facility {deal}.") from None
    if not grid:
        for c in out["covenants"]:
            c.pop("grid", None)
    return out
