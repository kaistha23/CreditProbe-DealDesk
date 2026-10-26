"""The persisted event sequence of a What-If run, and the SSE frames built from it.

Forked from the Cockpit (`backend/cockpit_v4/events.py`, frozen; copied, never
imported) and re-keyed to What-If's stages. The same rules hold:
  * every event is committed to the store BEFORE it is streamed, carries a
    monotonic `seq` within its run, and is replayable from a cursor, so a
    browser that reconnects reads the rows the worker wrote and never invents
    a step;
  * heartbeats are transport liveness only and are not stored;
  * one foreground stage at a time; entering a stage closes the previous one.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

EVENT_SCHEMA_VERSION = "whatif-events-1"

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
RUN_SETTLED = "run.settled"            # sent by the stream itself when the run is terminal

EVENT_TYPES = (RUN_ACCEPTED, RUN_STARTED, STAGE_STARTED, STAGE_COMPLETED, TOOL_STARTED, TOOL_COMPLETED,
               TOOL_FAILED, MODEL_REQUESTED, MODEL_RESPONSE, ANSWER_VALIDATED, ANSWER_READY, RUN_FAILED)
TERMINAL_EVENTS = (ANSWER_READY, RUN_FAILED)

#: What-If's stages, in order, with the words the UI shows.
STAGES: tuple[tuple[str, str], ...] = (
    ("accepted", "Question received"),
    ("understanding", "Reading the statement"),
    ("planning", "Planning the scenario"),
    ("querying", "Querying the What-If data"),
    ("answering", "Writing the answer"),
    ("computing", "Re-measuring ECL"),
    ("attributing", "Attributing the change"),
    ("assessing", "Checking history"),
    ("validating", "Validating the answer"),
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

    def frame(self) -> str:
        return f"id: {self.seq}\nevent: {self.event_type}\ndata: {json.dumps(self.to_dict())}\n\n"


class Emitter:
    """Writes a run's events through the store; tracks the one open stage."""

    def __init__(self, store, run_id: str):
        self.store = store
        self.run_id = run_id
        self.t0 = time.monotonic()
        self.open_stage = ""

    def _elapsed(self) -> int:
        return int((time.monotonic() - self.t0) * 1000)

    def emit(self, event_type: str, stage: str = "", status: str = "", message: str = "",
             detail: dict[str, Any] | None = None) -> Event:
        return self.store.append_event(self.run_id, event_type, stage=stage, status=status, message=message,
                                       elapsed_ms=self._elapsed(), detail=detail or {})

    def stage(self, name: str, message: str = "") -> None:
        if self.open_stage == name:
            return
        if self.open_stage:
            self.emit(STAGE_COMPLETED, self.open_stage, "completed")
        self.open_stage = name
        self.emit(STAGE_STARTED, name, "running", message or STAGE_LABELS.get(name, name))

    def close(self) -> None:
        if self.open_stage:
            self.emit(STAGE_COMPLETED, self.open_stage, "completed")
            self.open_stage = ""
