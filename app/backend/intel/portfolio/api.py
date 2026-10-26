"""PLAN_R13 §I session ID routes: portfolio steering (prefix /api/v1/intel/portfolio).

  GET  /                          the five engines, their intents and endpoints
  GET  /headroom    ?level=appetite|trigger|limit     growth headroom map (#14)
  GET  /exits       ?limit=25&min_freed=1.0           exit and sell-down list (#15)
  GET  /rwa         ?limit=30                         RWA finder (#16)
  GET  /ecl-bridge  ?window=8                         ECL bridge forecast (#17)
  GET  /workout     ?limit=30                         stressed names to pick from (#11)
  GET  /workout/{borrower_id}                         workout optimiser for one name (#11)
  POST /publish                                       write the computed views (with lineage) to var/intel/portfolio

Every response: headline, summary (deterministic writer), kpis, rows, data_limits, method, lineage, digest.
Mounted by one line in backend/dealdesk/api.py. Read-only on Data Domains.
"""
from __future__ import annotations

import functools
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.intel.portfolio import common as C

PREFIX = "/api/v1/intel/portfolio"
router = APIRouter(prefix=PREFIX, tags=["intel-portfolio"])

ENGINES = [
    {"key": "headroom", "backlog": 14, "title": "Growth headroom map", "path": f"{PREFIX}/headroom",
     "ask": "Where can we still lend next quarter?"},
    {"key": "exits", "backlog": 15, "title": "Exit and sell-down list", "path": f"{PREFIX}/exits",
     "ask": "Which names should we reduce or not renew?"},
    {"key": "rwa", "backlog": 16, "title": "RWA finder", "path": f"{PREFIX}/rwa",
     "ask": "Where can we save capital in the book?"},
    {"key": "ecl_bridge", "backlog": 17, "title": "ECL bridge forecast", "path": f"{PREFIX}/ecl-bridge",
     "ask": "What will next quarter's ECL be?"},
    {"key": "workout", "backlog": 11, "title": "Workout optimiser", "path": f"{PREFIX}/workout/{{borrower_id}}",
     "ask": "What is the best workout for this name?"},
]


@functools.lru_cache(maxsize=8)
def _headroom(level: str) -> dict[str, Any]:
    from backend.intel.portfolio import headroom
    return headroom.compute(level)


@functools.lru_cache(maxsize=8)
def _exits(limit: int, min_freed: float) -> dict[str, Any]:
    from backend.intel.portfolio import exits
    return exits.compute(limit, min_freed)


@functools.lru_cache(maxsize=4)
def _rwa(limit: int) -> dict[str, Any]:
    from backend.intel.portfolio import rwa
    return rwa.compute(limit)


@functools.lru_cache(maxsize=4)
def _bridge(window: int) -> dict[str, Any]:
    from backend.intel.portfolio import ecl_bridge
    return ecl_bridge.compute(window)


@functools.lru_cache(maxsize=256)
def _workout(bid: str) -> dict[str, Any]:
    from backend.intel.portfolio import workout
    return workout.compute(bid)


@router.get("")
@router.get("/")
def index() -> dict[str, Any]:
    return {"engines": ENGINES, "version": C.VERSION, "as_of": C.AS_OF_QUARTER}


@router.get("/headroom")
def headroom(level: str = Query("appetite", pattern="^(appetite|trigger|limit)$")) -> dict[str, Any]:
    return _headroom(level)


@router.get("/exits")
def exits(limit: int = Query(25, ge=1, le=200), min_freed: float = Query(1.0, ge=0.0)) -> dict[str, Any]:
    return _exits(limit, float(min_freed))


@router.get("/rwa")
def rwa(limit: int = Query(30, ge=1, le=500)) -> dict[str, Any]:
    return _rwa(limit)


@router.get("/ecl-bridge")
def ecl_bridge(window: int = Query(8, ge=2, le=19)) -> dict[str, Any]:
    return _bridge(window)


@functools.lru_cache(maxsize=8)
def _candidates(limit: int) -> dict[str, Any]:
    from backend.intel.portfolio import workout
    return workout.candidates(limit)


@router.get("/workout")
def workout_candidates(limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
    return _candidates(limit)


@router.get("/workout/{borrower_id}")
def workout(borrower_id: str) -> dict[str, Any]:
    try:
        return _workout(borrower_id)
    except KeyError:
        raise HTTPException(404, f"{borrower_id} is not an obligor of the corporate book at {C.AS_OF_QUARTER}") from None


def out_dir() -> pathlib.Path:
    import os
    d = pathlib.Path(os.environ.get("INTEL_VAR") or C.V5 / "var" / "intel" / "portfolio")
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/publish")
def publish() -> dict[str, Any]:
    """Data Domains has no contract relation for these views yet: they are published as computed views with lineage."""
    d = out_dir()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    views = {"intel_growth_headroom": _headroom("appetite"), "intel_exit_list": _exits(25, 1.0), "intel_rwa_finder": _rwa(30),
             "intel_ecl_bridge": _bridge(8)}
    written = []
    for name, body in views.items():
        p = d / f"{name}.json"
        p.write_text(json.dumps({"view": name, "published_at": now, "kind": "computed_view", **body}, indent=1, default=str))
        written.append({"view": name, "path": str(p.relative_to(C.V5)) if C.V5 in p.parents else str(p), "digest": body["digest"],
                        "rows": len(body["rows"]), "lineage": [f"{x['domain']}.{x['relation']}" for x in body["lineage"]]})
    return {"published_at": now, "views": written}
