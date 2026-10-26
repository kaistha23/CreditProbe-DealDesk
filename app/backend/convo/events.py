"""The persisted event sequence of a conversational run, and its SSE frames.

Forked from the Cockpit (`backend/cockpit_v4/events.py`, frozen; copied, never
imported). Every event is committed before it is streamed, carries a monotonic
`seq` within its run and is replayable from a cursor; heartbeats are not stored;
one foreground stage at a time.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

EVENT_SCHEMA_VERSION = "convo-events-1"

RUN_ACCEPTED = "run.accepted"
RUN_STARTED = "run.started"
STAGE_STARTED = "stage.started"
STAGE_COMPLETED = "stage.completed"
TOOL_STARTED = "tool.started"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"
MODEL_REQUESTED = "model.requested"
MODEL_RESPONSE = "model.response_received"
ANSWER_VALIDATED = "answer.validated"
ANSWER_READY = "answer.ready"
RUN_FAILED = "run.failed"
RUN_SETTLED = "run.settled"

TERMINAL_EVENTS = (ANSWER_READY, RUN_FAILED)

#: The Cockpit's stages: understand, plan, query, answer, validate, publish.
STAGES: tuple[tuple[str, str], ...] = (
    ("accepted", "Question received"),
    ("understanding", "Understanding the question"),
    ("planning", "Planning the analysis"),
    ("querying", "Querying the data"),
    ("answering", "Writing the answer"),
    ("validating", "Checking every figure"),
    ("publishing", "Publishing"),
)
STAGE_LABELS = dict(STAGES)


@dataclass
class Event:
    seq: int
    event_type: str
    stage: str = ""
    status: str = ""
    public_message: str = ""
    elapsed_ms: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": EVENT_SCHEMA_VERSION, "seq": self.seq, "event_type": self.event_type, "stage": self.stage,
                "stage_label": STAGE_LABELS.get(self.stage, ""), "status": self.status,
                "public_message": self.public_message, "elapsed_ms": self.elapsed_ms, "detail": self.detail}


def frame(payload: dict[str, Any]) -> str:
    return f"id: {payload['seq']}\nevent: {payload['event_type']}\ndata: {json.dumps(payload)}\n\n"


class Emitter:
    def __init__(self, store, run_id: str):
        self.store = store
        self.run_id = run_id
        self.t0 = time.monotonic()
        self.open_stage = ""

    def emit(self, event_type: str, stage: str = "", status: str = "", message: str = "",
             detail: dict[str, Any] | None = None) -> Event:
        return self.store.append_event(self.run_id, event_type, stage=stage, status=status, message=message,
                                       elapsed_ms=int((time.monotonic() - self.t0) * 1000), detail=detail or {})

    def stage(self, name: str, message: str = "") -> None:
        if self.open_stage == name:
            return
        if self.open_stage:
            self.emit(STAGE_COMPLETED, self.open_stage, "completed", detail={"step": _step(self.open_stage)})
        self.open_stage = name
        self.emit(STAGE_STARTED, name, "running", message or STAGE_LABELS.get(name, name), {"step": _step(name)})

    def close(self) -> None:
        if self.open_stage:
            self.emit(STAGE_COMPLETED, self.open_stage, "completed", detail={"step": _step(self.open_stage)})
            self.open_stage = ""


def _step(stage: str) -> str:
    """The G4 step key of a stage (docs/v5/THREAD_API.md)."""
    from backend.convo.trace import step_of
    return step_of(stage)
