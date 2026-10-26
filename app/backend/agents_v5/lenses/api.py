"""The Monitoring agent panel's routes: prefix /api/v1/agents/lenses, on the agents service (port 8517).

The generic agent API (runs, approvals, schedules) is the runtime's (`backend.agents_v5.api`). These routes add what
the Lenses panel needs on top: the panel view for a scope (pending proposal, active set, alerts, recent runs), the
three goals as one-click calls (synchronous, deterministic planner unless asked), the per-metric accept / edit /
reject before a decision, and the decision itself (through the runtime's approvals: role, maker-checker, expiry).

    GET  /monitoring?book=&filters=&lens_id=
    POST /monitoring/plan     {book, filters, lens_id, goal?, planner?}
    POST /monitoring/run      {book, filters, lens_id, period?}
    POST /monitoring/review   {book, filters, lens_id}
    POST /proposals/{proposal_id}/metrics/{key}   {action: accept|reject|edit, threshold?}
    POST /proposals/{proposal_id}/decision        {decision: approve|reject, note?}

`mount_on_agents_service()` adds the router to the agents service's app when that service imports this package (it
imports every module agent while it starts); `app` serves the routes on their own for tests.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from typing import Any

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.agents_v5.lenses import agent as A
from backend.agents_v5.lenses import tools as T
from backend.lenses_v5.engine import LensError

PREFIX = "/api/v1/agents/lenses"
router = APIRouter(prefix=PREFIX, tags=["agents-lenses"])


def _user(request: Request) -> dict[str, Any]:
    import os
    if os.environ.get("AGENTS_V5_TRUST_HEADERS") == "1" and request.headers.get("x-agents-user"):
        return {"username": request.headers["x-agents-user"], "agent_role": request.headers.get("x-agents-role", "VIEWER")}
    from backend.lenses_v5 import access
    return access.user(request)


def _writer(request: Request) -> dict[str, Any]:
    from backend.lenses_v5 import access
    name = access.viewing_as(request)
    if name:
        raise HTTPException(403, f"Read only while viewing as {name}.")
    u = _user(request)
    if not u.get("username"):
        raise HTTPException(401, "Sign in to use the Monitoring agent.")
    return u


def _ctx(book: str = "", filters: Any = None, lens_id: str = "") -> dict[str, Any]:
    if isinstance(filters, str):
        try:
            filters = json.loads(filters or "[]")
        except json.JSONDecodeError as e:
            raise HTTPException(422, "filters must be a JSON list of {dim, values}.") from e
    if lens_id:
        return {"lens_id": lens_id}
    return {"book": book if book in ("corporate", "retail") else "corporate",
            "filters": [f for f in (filters or []) if isinstance(f, dict) and f.get("dim") and f.get("values")]}


def _scope(ctx: dict[str, Any], goal: str = "") -> dict[str, Any]:
    try:
        return T.resolve_scope(goal, ctx)
    except (ValueError, LensError) as e:
        raise HTTPException(404 if ctx.get("lens_id") else 422, str(e)) from e


@router.get("/monitoring")
def monitoring(request: Request, book: str = Query("corporate"), filters: str = Query("[]"), lens_id: str = Query("")) -> dict[str, Any]:
    sc = _scope(_ctx(book, filters, lens_id))
    out = A.panel({k: sc[k] for k in ("book", "filters", "scope_key", "label", "lens_id", "lens_name", "period")})
    out["can_decide"] = A.may_decide(_user(request))
    out["me"] = _user(request).get("username", "")
    return out


def _go(request: Request, body: dict[str, Any], goal_type: str, default_goal: str, planner: str = "deterministic") -> dict[str, Any]:
    u = _writer(request)
    ctx = _ctx(body.get("book", ""), body.get("filters"), str(body.get("lens_id") or ""))
    sc = _scope(ctx)
    ctx.update({"goal_type": goal_type, "scope": sc})
    if body.get("period"):
        ctx["period"] = str(body["period"])
        ctx["scope"] = _scope({**ctx, "scope": None})
    goal = str(body.get("goal") or default_goal.format(label=sc["lens_name"] or sc["label"]))[:400]
    run = A.run(goal, ctx, planner=planner, user=u["username"])
    d = run.to_dict(with_output=False)
    d["output"] = run.output
    return d


@router.post("/monitoring/plan")
def plan(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    mode = str(body.get("planner") or "deterministic")
    if mode not in ("auto", "model", "deterministic"):
        raise HTTPException(422, "planner: auto, model or deterministic.")
    return _go(request, body, "setup", "Set up monitoring for {label}", planner=mode)


@router.post("/monitoring/run")
def run_now(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _go(request, body, "run", "Run monitoring for {label}")


@router.post("/monitoring/review")
def review(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return _go(request, body, "review", "Review the monitoring set for {label}")


@router.post("/proposals/{proposal_id}/metrics/{key}")
def edit_metric(proposal_id: str, key: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _writer(request)
    try:
        return A.edit_metric(proposal_id, key, str(body.get("action") or ""), u, body.get("threshold"))
    except KeyError as e:
        raise HTTPException(404, "That proposal or metric does not exist.") from e
    except A.NotAllowed as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/proposals/{proposal_id}/decision")
def decision(proposal_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _writer(request)
    try:
        return A.decide(proposal_id, str(body.get("decision") or ""), u, str(body.get("note") or ""))
    except KeyError as e:
        raise HTTPException(404, "That proposal does not exist.") from e
    except A.NotAllowed as e:
        msg = str(e)
        raise HTTPException(409 if ("already" in msg or "expired" in msg or "could not be applied" in msg) else 403, msg) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------ mounting
_MOUNTED: set[int] = set()


def mount(app: FastAPI) -> bool:
    if id(app) in _MOUNTED or any(getattr(r, "path", "").startswith(PREFIX) for r in app.router.routes):
        return False
    app.include_router(router)
    _MOUNTED.add(id(app))
    return True


def mount_on_agents_service() -> None:
    """The agents service imports every module agent before it creates its app; mount once the app exists."""
    mod = sys.modules.get("backend.agents_v5.api")
    if mod is None:
        return
    if getattr(mod, "app", None) is not None:
        mount(mod.app)
        return

    def _wait() -> None:
        for _ in range(600):
            app_ = getattr(sys.modules.get("backend.agents_v5.api"), "app", None)
            if app_ is not None:
                mount(app_)
                return
            time.sleep(0.05)
    threading.Thread(target=_wait, name="lenses-monitoring-mount", daemon=True).start()


app = FastAPI(title="CreditProbe v5 Monitoring agent (Lenses)")
try:
    from backend.lenses_v5.paths import UI_ORIGINS
except Exception:  # noqa: BLE001
    UI_ORIGINS = ["http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=UI_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
mount(app)
