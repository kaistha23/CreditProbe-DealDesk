"""The process trace of one answer: Understand -> Plan -> Query -> Answer -> Validate -> Publish (PLAN_R5 G4).

Every module shows the Cockpit's process trace with its running timer while it answers. Runs on the convo store
already stream their stage events over SSE; modules whose turn is ONE HTTP request (Playbook, Scorecard, Projects,
Deal Desk asks, Lenses, Admin) cannot stream, so they record the steps in a `TraceRecorder` registered under the
client's `X-Trace-Id`, and the browser polls `GET <prefix>/trace/{trace_id}` while the request is in flight. The
settled snapshot is stored in the answer (`answer["trace"]`), so a reloaded thread still shows "Answered in 4.2s".

Contract: docs/v5/THREAD_API.md section 2.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any

from contextvars import ContextVar

from fastapi import APIRouter, HTTPException, Request  # noqa: F401

#: convo stage -> G4 step key
STEP_OF = {
    "understanding": "understand",
    "planning": "plan",
    "querying": "query",
    "answering": "answer",
    "validating": "validate",
    "publishing": "publish",
    # What-If's engine stages (backend/whatif_v5/chat/events.py)
    "computing": "query",
    "attributing": "answer",
    "assessing": "validate",
}
STEP_LABELS = {
    "understand": "Understand",
    "plan": "Plan",
    "query": "Query",
    "answer": "Answer",
    "validate": "Validate",
    "publish": "Publish",
}
STEP_ORDER = tuple(STEP_LABELS)
TTL_SECONDS = 600
_ID = re.compile(r"^[A-Za-z0-9_.:-]{4,80}$")


def step_of(stage: str) -> str:
    """The G4 step a convo stage belongs to ('' for `accepted` and unknown stages)."""
    if stage in STEP_LABELS:
        return stage
    return STEP_OF.get(stage, "")


class TraceRecorder:
    """A convo emitter (emit / stage / close / open_stage) that keeps the steps with their timestamps.

    Pass it as the Agent's emitter, or wrap another emitter (`inner=`) and every call is forwarded to it too.
    Times are milliseconds from the recorder's start (the turn's start).
    """

    def __init__(self, trace_id: str | None = None, inner: Any = None, clock=time.monotonic):
        self.trace_id = trace_id if trace_id and _ID.match(trace_id) else new_id()
        self.inner = inner
        self._clock = clock
        self._t0 = clock()
        self._lock = threading.Lock()
        self.steps: list[dict[str, Any]] = []
        self.state = "running"
        self.elapsed_ms = 0
        self.open_stage = ""
        self.touched = time.time()

    # ----------------------------------------------------------- emitter protocol
    def _now(self) -> int:
        return int(round((self._clock() - self._t0) * 1000))

    def emit(self, event_type: str, stage: str = "", status: str = "", message: str = "",
             detail: dict[str, Any] | None = None):
        key = step_of(stage)
        with self._lock:
            cur = self._current()
            if key and cur is not None and cur["key"] == key and message:
                cur["detail"] = message[:160]
            if status == "failed" and cur is not None and event_type in ("tool.failed", "run.failed"):
                cur["failures"] = cur.get("failures", 0) + 1
            if event_type == "run.failed":
                self._close_open("failed")
                self.state = "failed"
            self.elapsed_ms = max(self.elapsed_ms, self._now())
            self.touched = time.time()
        if self.inner is not None:
            return self.inner.emit(event_type, stage, status, message, detail)
        return None

    def stage(self, name: str, message: str = "") -> None:
        key = step_of(name)
        if self.inner is not None:
            self.inner.stage(name, message)
        if self.open_stage == name:
            return
        self.open_stage = name
        if not key:
            return
        with self._lock:
            cur = self._current()
            if cur is not None and cur["key"] == key and cur["state"] == "running":
                if message:
                    cur["detail"] = message[:160]
                return
            self._close_open("done")
            now = self._now()
            self.steps.append({"key": key, "label": STEP_LABELS[key], "state": "running", "started_ms": now,
                               "ended_ms": None, "detail": (message or "")[:160], "failures": 0})
            self.elapsed_ms = max(self.elapsed_ms, now)
            self.touched = time.time()

    def close(self) -> None:
        if self.inner is not None and hasattr(self.inner, "close"):
            self.inner.close()
        self.open_stage = ""
        with self._lock:
            self._close_open("done")

    # ----------------------------------------------------------- results
    def _current(self) -> dict[str, Any] | None:
        return self.steps[-1] if self.steps else None

    def _close_open(self, state: str) -> None:
        now = self._now()
        for s in self.steps:
            if s["state"] == "running":
                s["state"] = state
                s["ended_ms"] = now

    def finish(self, failed: bool = False) -> dict[str, Any]:
        """Close the open step and settle the trace; returns the snapshot to store in the answer."""
        with self._lock:
            if not self.steps:
                # A turn that never named a step still did something: one honest Answer step.
                self.steps.append({"key": "answer", "label": "Answer", "state": "running", "started_ms": 0,
                                   "ended_ms": None, "detail": "", "failures": 0})
            self._close_open("failed" if failed else "done")
            self.state = "failed" if failed else "done"
            self.elapsed_ms = max(self.elapsed_ms, self._now())
            self.touched = time.time()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            elapsed = self.elapsed_ms if self.state != "running" else max(self.elapsed_ms, self._now())
            return {"trace_id": self.trace_id, "state": self.state, "elapsed_ms": elapsed,
                    "steps": [dict(s) for s in self.steps]}


# ------------------------------------------------------------------ registry (in-process; poll-only)

_REG: dict[str, TraceRecorder] = {}
_REG_LOCK = threading.Lock()


def new_id() -> str:
    return "tr-" + uuid.uuid4().hex[:16]


def register(rec: TraceRecorder) -> TraceRecorder:
    cutoff = time.time() - TTL_SECONDS
    with _REG_LOCK:
        for k in [k for k, r in _REG.items() if r.touched < cutoff]:
            _REG.pop(k, None)
        _REG[rec.trace_id] = rec
    return rec


def lookup(trace_id: str) -> TraceRecorder | None:
    with _REG_LOCK:
        return _REG.get(trace_id)


def recorder_for(request: Request | None = None, inner: Any = None, trace_id: str | None = None) -> TraceRecorder:
    """A registered recorder for this request's turn, under the client's `X-Trace-Id` (a fresh id if absent)."""
    tid = trace_id or (request.headers.get("x-trace-id") if request is not None else None)
    return register(TraceRecorder(tid, inner=inner))


# ------------------------------------------------------------------ the request's own trace (one-request turns)

_CURRENT: ContextVar["TraceRecorder | None"] = ContextVar("convo_trace", default=None)


def current() -> TraceRecorder | None:
    """The trace of the turn this request is answering (set by TraceMiddleware from X-Trace-Id), if any."""
    return _CURRENT.get()


def step(stage: str, message: str = "") -> None:
    """Name the step the current turn is in (no-op outside a traced request). For deterministic engines."""
    rec = _CURRENT.get()
    if rec is not None:
        rec.stage(stage, message)


def attach(answer: dict[str, Any] | None) -> dict[str, Any] | None:
    """Store the current turn's settled trace in `answer['trace']` (no-op outside a traced request)."""
    rec = _CURRENT.get()
    if rec is not None and isinstance(answer, dict):
        if rec.steps and rec.steps[-1]["key"] != "publish":
            rec.stage("publishing")
        answer["trace"] = rec.finish()
    return answer


class _Tee:
    """Forwards every emitter call to the module's own emitter AND the request's trace."""

    def __init__(self, inner: Any, rec: TraceRecorder):
        self.inner = inner
        self.rec = rec

    @property
    def open_stage(self) -> str:
        return getattr(self.inner, "open_stage", "")

    @open_stage.setter
    def open_stage(self, v: str) -> None:
        try:
            self.inner.open_stage = v
        except Exception:  # noqa: BLE001 - read-only on some emitters
            pass

    def emit(self, *a, **k):
        try:
            self.rec.emit(*a, **k)
        except Exception:  # noqa: BLE001 - the trace never breaks the answer
            pass
        return self.inner.emit(*a, **k)

    def stage(self, name: str, message: str = "") -> None:
        try:
            self.rec.stage(name, message)
        except Exception:  # noqa: BLE001
            pass
        self.inner.stage(name, message)

    def close(self) -> None:
        if hasattr(self.inner, "close"):
            self.inner.close()

    def __getattr__(self, name: str):
        return getattr(self.inner, name)


def tee(emitter: Any) -> Any:
    """The Agent's emitter, also feeding the request's trace when there is one (backend/convo/agent.py)."""
    rec = _CURRENT.get()
    if rec is None or emitter is rec or isinstance(emitter, (TraceRecorder, _Tee)):
        return emitter
    return _Tee(emitter, rec)


class TraceMiddleware:
    """Pure ASGI middleware: a request carrying `X-Trace-Id` gets a registered TraceRecorder as `current()`.

    The turn opens in Understand; whatever the handler (or the Agent inside it) names follows; the trace settles
    when the response is sent, so the poll sees it finish even if the handler never called `attach()`.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        tid = None
        for k, v in scope.get("headers") or []:
            if k == b"x-trace-id":
                tid = v.decode("latin-1")
                break
        if not tid or scope.get("method") == "GET":
            return await self.app(scope, receive, send)
        rec = register(TraceRecorder(tid))
        rec.stage("understanding", "Reading the question")
        token = _CURRENT.set(rec)
        failed = False
        try:
            await self.app(scope, receive, send)
        except Exception:
            failed = True
            raise
        finally:
            _CURRENT.reset(token)
            if rec.state == "running":
                if not failed and rec.steps and rec.steps[-1]["key"] != "publish":
                    rec.stage("publishing")
                rec.finish(failed=failed)


def install(app, prefix: str) -> None:
    """Mount the trace poll route under `prefix` and the middleware on `app` (one call per service)."""
    app.include_router(trace_router(), prefix=prefix)
    app.add_middleware(TraceMiddleware)


def trace_router() -> APIRouter:
    """GET /trace/{trace_id} -> the live (or settled) TraceSnapshot. Mount under the module's API prefix."""
    r = APIRouter()

    @r.get("/trace/{trace_id}")
    def get_trace(trace_id: str):
        rec = lookup(trace_id)
        if rec is None:
            # The browser starts polling as it sends the turn, so the trace may not be registered yet: say "not
            # started" (no steps) rather than 404, which would read as a failed request.
            if not _ID.match(trace_id):
                raise HTTPException(422, {"error_code": "TRACE_BAD_ID", "message": "Not a trace id."})
            return {"trace_id": trace_id, "state": "running", "elapsed_ms": 0, "steps": [], "registered": False}
        return {**rec.snapshot(), "registered": True}

    return r


def from_events(events: list[dict[str, Any]], settled: bool = True) -> dict[str, Any]:
    """Rebuild a snapshot from stored convo events (stage.started / stage.completed with elapsed_ms)."""
    steps: list[dict[str, Any]] = []
    elapsed = 0
    failed = False
    for e in events:
        elapsed = max(elapsed, int(e.get("elapsed_ms") or 0))
        key = step_of(e.get("stage") or "")
        et = e.get("event_type")
        if et == "run.failed":
            failed = True
        if not key:
            continue
        if et == "stage.started":
            if steps and steps[-1]["key"] == key and steps[-1]["state"] == "running":
                steps[-1]["detail"] = (e.get("public_message") or steps[-1]["detail"])[:160]
                continue
            for s in steps:
                if s["state"] == "running":
                    s["state"], s["ended_ms"] = "done", e.get("elapsed_ms", 0)
            steps.append({"key": key, "label": STEP_LABELS[key], "state": "running", "started_ms": e.get("elapsed_ms", 0),
                          "ended_ms": None, "detail": e.get("public_message", "")[:160], "failures": 0})
        elif et == "stage.completed":
            for s in reversed(steps):
                if s["key"] == key and s["state"] == "running":
                    s["state"], s["ended_ms"] = "done", e.get("elapsed_ms", 0)
                    break
    if settled:
        for s in steps:
            if s["state"] == "running":
                s["state"], s["ended_ms"] = ("failed" if failed else "done"), elapsed
    return {"trace_id": "", "state": ("failed" if failed else "done") if settled else "running",
            "elapsed_ms": elapsed, "steps": steps}


__all__ = ["TraceRecorder", "TraceMiddleware", "install", "current", "step", "attach", "tee", "recorder_for", "trace_router", "register", "lookup", "from_events", "step_of",
           "STEP_LABELS", "STEP_ORDER", "new_id"]
