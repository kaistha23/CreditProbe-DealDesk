"""The conversational service a module mounts: store + worker + router (the Cockpit's route contract).

    svc = ConvoService("scorecard", [scorecard_domain], store_path=...)
    app.include_router(svc.router, prefix="/api/v1/scorecard/convo")
    svc.start()                      # on the app's startup (one worker thread pool)

Routes (relative to the prefix):
    GET  /health
    GET  /domains                                   the domains this service answers, with chips
    POST /threads        {domain, scope?, title?, question?, mode?}   -> 201 {thread, run?}
    GET  /threads?domain=                           recent threads the caller may see
    GET  /threads/{id}                              thread, transcript (turns), active run id
    POST /threads/{id}/runs  {question, mode?: "ask"|"execute", idem_key?}  -> 202 run
    GET  /runs/{id}                                 run status (+ answer when settled)
    GET  /runs/{id}/events?cursor=                  SSE: committed events, then run.settled
    GET  /runs/{id}/artifacts                       the run's evidence (queries and tool outputs)
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.convo import agent, events as ev, provider
from backend.convo import states as st
from backend.convo.spec import Domain
from backend.convo.store import BusyError, Store, default_path


def _user(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request) or {}
    except Exception:  # noqa: BLE001 - no identity service: anonymous (sees unowned threads)
        return {}


def can_see(u: dict[str, Any], t: dict[str, Any]) -> bool:
    if not t.get("owner") or u.get("is_admin") or not u.get("username"):
        return True
    return t["owner"] == u.get("username") or (bool(t.get("team")) and t.get("team") == u.get("team"))


class Worker:
    def __init__(self, svc: "ConvoService", threads: int = 2):
        self.svc = svc
        self.n = threads
        self.stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self.svc.store.recover()
        for i in range(self.n):
            t = threading.Thread(target=self.serve_forever, name=f"convo-{self.svc.name}-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def serve_forever(self) -> None:
        while not self.stop.is_set():
            run = self.svc.store.claim_next()
            if run is None:
                time.sleep(0.05)
                continue
            agent.answer(self.svc.store, run["run_id"], self.svc.domains)

    def drain(self, timeout: float = 120.0) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            run = self.svc.store.claim_next()
            if run is None:
                return
            agent.answer(self.svc.store, run["run_id"], self.svc.domains)


def refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


class ConvoService:
    def __init__(self, name: str, domains: list[Domain], store_path=None, worker_threads: int = 2):
        self.name = name
        self.domains = {d.key: d for d in domains}
        self.store = Store(store_path or default_path(name), prefix=name[:2])
        self.worker = Worker(self, worker_threads)
        self._started = False
        self.router = self._router()

    def start(self) -> None:
        if not self._started:
            self._started = True
            self.worker.start()

    def thread_or_404(self, request: Request, thread_id: str) -> dict[str, Any]:
        t = self.store.thread(thread_id)
        if t is None:
            raise refuse(404, "CONVO_THREAD_NOT_FOUND", f"{thread_id} is not a thread.")
        if not can_see(_user(request), t):
            raise refuse(403, "CONVO_NOT_ALLOWED", "This thread belongs to someone else.")
        return t

    def open_thread(self, *, domain: str, scope: dict, owner: str = "", team: str = "", title: str = "",
                    question: str = "", mode: str = "ask", origin: str = "chat") -> dict[str, Any]:
        if domain not in self.domains:
            raise refuse(422, "CONVO_UNKNOWN_DOMAIN", f"'{domain}' is not a domain of this service.")
        t = self.store.create_thread(domain=domain, scope=scope or {}, owner=owner, team=team, title=title,
                                     origin=origin)
        run = self.store.accept_run(t["thread_id"], owner, question.strip(), mode) if question.strip() else None
        return {"thread": t, "run": run}

    def _router(self) -> APIRouter:
        r = APIRouter()
        svc = self

        @r.get("/health")
        def health() -> dict[str, Any]:
            return {"status": "ok", "service": f"convo-{svc.name}", "domains": sorted(svc.domains),
                    "assistant": provider.describe(), "imports_cockpit": False}

        @r.get("/domains")
        def domains(scope: str = Query("{}")) -> dict[str, Any]:
            try:
                sc = json.loads(scope or "{}")
            except ValueError:
                sc = {}
            return {"domains": [{"key": d.key, "title": d.title, "knowledge": sorted(d.knowledge),
                                 "tools": [{"name": t.name, "action": t.action} for t in d.tools],
                                 "suggestions": d.suggestions(sc, {})} for d in svc.domains.values()],
                    "assistant": provider.describe()}

        @r.post("/threads", status_code=201)
        def create(request: Request, body: dict = Body(...)) -> dict[str, Any]:
            u = _user(request)
            return svc.open_thread(domain=str(body.get("domain") or ""), scope=body.get("scope") or {},
                                   owner=u.get("username", ""), team=u.get("team", ""), title=str(body.get("title") or ""),
                                   question=str(body.get("question") or ""), mode=_mode(body.get("mode")),
                                   origin=str(body.get("origin") or "chat"))

        @r.get("/threads")
        def threads(request: Request, domain: str = Query(""), limit: int = Query(50)) -> dict[str, Any]:
            u = _user(request)
            return {"threads": [t for t in svc.store.threads(domain or None, limit) if can_see(u, t)]}

        @r.get("/threads/{thread_id}")
        def thread(request: Request, thread_id: str) -> dict[str, Any]:
            t = svc.thread_or_404(request, thread_id)
            return {"thread": t, "turns": svc.store.turns(thread_id), "active_run": svc.store.active_run(thread_id)}

        @r.post("/threads/{thread_id}/runs", status_code=202)
        def ask(request: Request, thread_id: str, body: dict = Body(...)) -> dict[str, Any]:
            t = svc.thread_or_404(request, thread_id)
            q = str(body.get("question") or "").strip()
            if not q:
                raise refuse(422, "CONVO_EMPTY", "Ask a question.")
            try:
                return svc.store.accept_run(t["thread_id"], _user(request).get("username", ""), q[:4000],
                                            _mode(body.get("mode")), str(body.get("idem_key") or ""))
            except BusyError as e:
                raise refuse(409, "CONVO_BUSY", f"A turn is still running on this thread ({e.run_id}).") from e

        @r.get("/runs/{run_id}")
        def run(request: Request, run_id: str) -> dict[str, Any]:
            rr = svc.store.run(run_id)
            if rr is None:
                raise refuse(404, "CONVO_RUN_NOT_FOUND", f"{run_id} is not a run.")
            svc.thread_or_404(request, rr["thread_id"])
            return rr

        @r.get("/runs/{run_id}/artifacts")
        def artifacts(request: Request, run_id: str) -> dict[str, Any]:
            rr = svc.store.run(run_id)
            if rr is None:
                raise refuse(404, "CONVO_RUN_NOT_FOUND", f"{run_id} is not a run.")
            svc.thread_or_404(request, rr["thread_id"])
            return {"artifacts": svc.store.artifacts(run_id)}

        @r.get("/runs/{run_id}/events")
        async def events(request: Request, run_id: str, cursor: int = Query(0)) -> StreamingResponse:
            rr = svc.store.run(run_id)
            if rr is None:
                raise refuse(404, "CONVO_RUN_NOT_FOUND", f"{run_id} is not a run.")
            last = request.headers.get("last-event-id")
            cur = int(last) if last and last.isdigit() else int(cursor or 0)

            async def gen():
                nonlocal cur
                idle = 0
                while True:
                    rows = svc.store.events_since(run_id, cur)
                    for p in rows:
                        cur = p["seq"]
                        yield ev.frame(p)
                    run_now = svc.store.run(run_id)
                    if run_now and run_now["terminal"] and not svc.store.events_since(run_id, cur):
                        yield (f"event: {ev.RUN_SETTLED}\ndata: "
                               f"{json.dumps({'state': run_now['state'], 'run_id': run_id, 'seq': cur})}\n\n")
                        return
                    if await request.is_disconnected():
                        return
                    idle = idle + 1 if not rows else 0
                    if idle and idle % 100 == 0:
                        yield ": heartbeat\n\n"
                    await asyncio.sleep(0.15)

            return StreamingResponse(gen(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        return r


def _mode(m: Any) -> str:
    return "execute" if str(m or "").lower() == "execute" else "ask"


__all__ = ["ConvoService", "Worker", "can_see", "st"]
