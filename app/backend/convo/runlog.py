"""Every conversational turn in every module, logged for Admin -> Agent Operations (PLAN_R5 A3).

One JSON line per turn in var/convo/agent_runs.jsonl (CONVO_RUNLOG overrides): when, module, domain, user, question,
the process steps with their elapsed times, the tools called, the model or planner, latency, outcome, and the
figures the validator checked or removed. Writing never fails a turn.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

V5 = pathlib.Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()


def path() -> pathlib.Path:
    if os.environ.get("CONVO_RUNLOG"):
        return pathlib.Path(os.environ["CONVO_RUNLOG"])
    if os.environ.get("PYTEST_CURRENT_TEST"):   # test turns never reach the live Agent Operations log
        return V5 / "var" / "pytest" / "agent_runs.jsonl"
    return V5 / "var" / "convo" / "agent_runs.jsonl"


class StageClock:
    """Wraps a turn's emitter and records when each process step starts (the emitter is otherwise untouched)."""

    def __init__(self, inner: Any):
        self._inner = inner
        self._t0 = time.monotonic()
        self.steps: list[dict[str, Any]] = []

    def stage(self, name: str, message: str = "") -> Any:
        now = round((time.monotonic() - self._t0) * 1000)
        if self.steps:
            self.steps[-1]["ms"] = now - self.steps[-1]["at_ms"]
        self.steps.append({"stage": name, "at_ms": now, "ms": 0})
        return self._inner.stage(name, message)

    def close(self) -> list[dict[str, Any]]:
        now = round((time.monotonic() - self._t0) * 1000)
        if self.steps and not self.steps[-1]["ms"]:
            self.steps[-1]["ms"] = now - self.steps[-1]["at_ms"]
        return self.steps

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_inner", "_t0", "steps"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)


def record(**row: Any) -> None:
    try:
        # A caller may bring its own run_id (the Agent, so its model calls in llm_calls.jsonl share it).
        row = {"run_id": row.pop("run_id", None) or ("AR-" + uuid.uuid4().hex[:10]),
               "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **row}
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 - logging never fails a turn
        pass


def read(limit: int = 2000) -> list[dict[str, Any]]:
    p = path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
