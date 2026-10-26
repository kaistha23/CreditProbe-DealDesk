"""The agents service (PLAN_R11_AGENTS Contract): port 8517, prefix /api/v1/agents.

    POST /api/v1/agents/{agent_id}/runs             body {goal, context, planner?, wait?} -> the run
    GET  /api/v1/agents/runs/{run_id}               the full run (plan, steps, findings, narrative, output)
    GET  /api/v1/agents/runs?agent=&scope=          recent runs
    POST /api/v1/agents/approvals/{id}/decision     body {decision: approve|reject, note}
    GET  /api/v1/agents/approvals?agent=&status=&run_id=
    GET  /api/v1/agents                             registered agents and tools (availability on this build)
    GET/POST /api/v1/agents/schedules, PATCH/DELETE /api/v1/agents/schedules/{id}
    POST /api/v1/agents/events/{event}              fire `@after:<event>` schedules (e.g. ews_refresh)

Each module's agent registers on import: `backend.agents_v5.{dealdesk,ews,whatif,lenses}`.
The model key is read by `backend.convo.provider` from this process's environment only.
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.agents_v5.runtime import approvals, executor, schedules, store
from backend.agents_v5.runtime import tools as T
from backend.agents_v5.runtime.agents import agents, get_agent

logger = logging.getLogger(__name__)
PREFIX = "/api/v1/agents"
VERSION = "agents-v5-1.0.0"
AGENT_PACKAGES = ("backend.agents_v5.dealdesk", "backend.agents_v5.ews", "backend.agents_v5.whatif",
                  "backend.agents_v5.lenses")
LOADED: dict[str, str] = {}


def load_agents() -> dict[str, str]:
    for name in AGENT_PACKAGES:
        if name in LOADED and LOADED[name] == "loaded":
            continue
        try:
            importlib.import_module(name)
            LOADED[name] = "loaded"
        except ModuleNotFoundError as e:
            LOADED[name] = "not on this build" if name.split(".")[-1] in str(e) else f"error: {e}"
        except Exception as e:  # noqa: BLE001 - one module's agent never takes the service down
            LOADED[name] = f"error: {type(e).__name__}: {str(e)[:200]}"
            logger.exception("agent package %s failed to load", name)
    return dict(LOADED)


load_agents()

_origins = [o for o in (os.environ.get("AGENTS_V5_CORS_ORIGINS") or os.environ.get("AGENTS_CORS_ORIGINS") or
                        "http://127.0.0.1:5500,http://localhost:5500").split(",") if o]
app = FastAPI(title="CreditProbe Agents", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

if os.environ.get("AGENTS_V5_SCHEDULER", "on") != "off":
    schedules.start_ticker()


def _who(request: Request) -> tuple[str, str]:
    """(username, role). Identity from the Core service; test headers only when explicitly trusted."""
    if os.environ.get("AGENTS_V5_TRUST_HEADERS") == "1" and request.headers.get("x-agents-user"):
        return request.headers["x-agents-user"], request.headers.get("x-agents-role", "VIEWER")
    try:
        from backend.identity_v5.client import current_user
        u = current_user(request) or {}
    except Exception:  # noqa: BLE001
        u = {}
    role = u.get("agent_role") or u.get("role") or ("Administrator" if u.get("is_admin") else "")
    return str(u.get("username") or ""), approvals.norm_role(role or "VIEWER")


def _planner_info() -> dict[str, Any]:
    from backend.convo import provider as prov
    return prov.describe()


@app.get("/health")
@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "agents_v5", "version": VERSION, "agents": [a.agent_id for a in agents()],
            "packages": LOADED, **_planner_info()}


@app.get(PREFIX)
def list_agents() -> dict[str, Any]:
    return {"agents": [a.describe() for a in agents()], "tools": [t.describe() for t in T.tools()],
            "packages": LOADED, **_planner_info()}


@app.post(PREFIX + "/{agent_id}/runs")
def create_run(agent_id: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    a = get_agent(agent_id)
    if a is None:
        raise HTTPException(404, f"No agent {agent_id}.")
    goal = str(body.get("goal") or "").strip()
    if not goal:
        raise HTTPException(422, "A goal is needed.")
    ctx = body.get("context") or {}
    if not isinstance(ctx, dict):
        raise HTTPException(422, "context must be an object.")
    mode = body.get("planner") or "auto"
    if mode not in ("auto", "model", "deterministic"):
        raise HTTPException(422, "planner: auto, model or deterministic.")
    user, _ = _who(request)
    run = executor.start(a, goal, ctx, planner_mode=mode, trigger=str(body.get("trigger") or "on_demand"),
                         user=user, background=not bool(body.get("wait")))
    return run.to_dict()


@app.get(PREFIX + "/runs")
def list_runs(agent: str = "", scope: str = "", limit: int = 30) -> dict[str, Any]:
    return {"runs": store.list_runs(agent=agent, scope=scope, limit=max(1, min(limit, 200))),
            "schedules": schedules.listing(agent)}


@app.get(PREFIX + "/runs/{run_id}")
def get_run(run_id: str, compact: bool = False) -> dict[str, Any]:
    r = store.load_run(run_id)
    if r is None:
        raise HTTPException(404, f"No run {run_id}.")
    d = r.to_dict(with_output=not compact)
    d["approvals"] = [approvals.get(pid) for pid in r.proposals if approvals.get(pid)]
    return d


@app.get(PREFIX + "/runs/{run_id}/pack.docx")
def pack_docx(run_id: str, request: Request) -> Response:
    """The Deal Desk committee pack as Word (the house report pattern)."""
    r = store.load_run(run_id)
    if r is None or not (r.output or {}).get("decision"):
        raise HTTPException(404, f"No committee pack for {run_id}.")
    from backend.agents_v5.dealdesk.pack_docx import pack_docx as build
    data, name = build(r, _who(request)[0])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get(PREFIX + "/approvals")
def list_approvals(agent: str = "", status: str = "", run_id: str = "", scope: str = "") -> dict[str, Any]:
    return {"approvals": approvals.listing(agent=agent, status=status, run_id=run_id, scope=scope)}


@app.post(PREFIX + "/approvals/{approval_id}/decision")
def decide(approval_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    user, role = _who(request)
    try:
        return approvals.decide(approval_id, decision=str(body.get("decision") or ""), user=user, role=role,
                                note=str(body.get("note") or ""))
    except KeyError:
        raise HTTPException(404, f"No approval {approval_id}.") from None
    except (approvals.NotAuthorised, approvals.MakerChecker) as e:
        raise HTTPException(403, str(e)) from None
    except (approvals.AlreadyDecided, approvals.Expired) as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.get(PREFIX + "/schedules")
def list_schedules(agent: str = "") -> dict[str, Any]:
    return {"schedules": schedules.listing(agent)}


@app.post(PREFIX + "/schedules")
def create_schedule(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    user, role = _who(request)
    if approvals.ROLE_RANK.get(role, 0) < approvals.ROLE_RANK["ANALYST"]:
        raise HTTPException(403, "Scheduling an agent needs at least an analyst role.")
    try:
        return schedules.schedule(str(body.get("agent") or ""), str(body.get("cron") or ""),
                                  str(body.get("goal") or ""), body.get("context") or {},
                                  planner=str(body.get("planner") or "deterministic"), user=user)
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except schedules.CronInvalid as e:
        raise HTTPException(422, f"cron: {e}") from None


@app.patch(PREFIX + "/schedules/{sid}")
def patch_schedule(sid: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    row = schedules.set_enabled(sid, bool(body.get("enabled", True)))
    if row is None:
        raise HTTPException(404, f"No schedule {sid}.")
    return row


@app.delete(PREFIX + "/schedules/{sid}")
def delete_schedule(sid: str) -> dict[str, Any]:
    if not schedules.remove(sid):
        raise HTTPException(404, f"No schedule {sid}.")
    return {"deleted": sid}


@app.post(PREFIX + "/events/{event}")
def fire_event(event: str) -> dict[str, Any]:
    return {"event": event, "runs": schedules.fire_event(event)}
