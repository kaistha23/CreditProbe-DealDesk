"""IC network and events API, under /api/v1/intel/network (mounted on the Borrower 360 app, port 8502).

  GET  /health
  GET  /events/catalogue                         event families, severities, magnitudes and their calibration source
  POST /event        {text | family+params, severity?, period?}     the event translator (#8)
  GET  /contagion/{borrower}?period=&severity=   the contagion map if that borrower fails (#9)
  GET  /employers?period=&limit=&sector=         employers ranked by exposure held through their contractors
  GET  /employer/{employer}?period=              employer exposure (#10): a book id or name, or a Deal Desk employer

Every answer carries `text` (deterministic headline and lines), `limits` (what the data cannot tell), `lineage`
and, for the three engines, `view` (the computed view it was published as).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from backend.b360.store import NotFound
from backend.intel.network import calibration, contagion as ct, employer as em, events as ev, whatif_bridge as wb

PREFIX = "/api/v1/intel/network"
router = APIRouter(prefix=PREFIX, tags=["intel-network"])


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (NotFound, LookupError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ev.EventError, ct.ContagionError, em.EmployerError, ValueError) as exc:
        msg = str(exc)
        raise HTTPException(404 if msg.startswith("No ") else 400, msg) from exc
    except wb.BridgeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/health")
def health() -> dict[str, Any]:
    cal = calibration.table()
    return {"status": "ok", "service": "intel-network", "calibration": cal["source"], "calibration_label": cal["label"]}


@router.get("/events/catalogue")
def catalogue() -> dict[str, Any]:
    return _guard(ev.catalogue)


@router.post("/event")
def event(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return _guard(ev.translate_event, body)


@router.get("/contagion/{borrower}")
def contagion(borrower: str, period: str | None = Query(None), severity: str = Query("moderate")) -> dict[str, Any]:
    return _guard(ct.contagion, borrower, period, severity)


@router.get("/employers")
def employers(period: str | None = Query(None), limit: int = Query(15, ge=1, le=100),
              sector: str | None = Query(None)) -> dict[str, Any]:
    return _guard(em.ranking, period, limit, sector)


@router.get("/employer/{employer}")
def employer(employer: str, period: str | None = Query(None)) -> dict[str, Any]:
    return _guard(em.exposure, employer, period)
