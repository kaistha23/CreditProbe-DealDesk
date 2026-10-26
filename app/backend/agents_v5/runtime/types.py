"""The plan schema every planner produces and the executor runs (A2, A3).

Plan -> Steps -> (tool output) -> Findings with evidence refs -> narrative -> proposals.
Everything is plain JSON so runs store, replay and render without translation.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Any

PLAN_SCHEMA_VERSION = "agents-v5-plan-1"

# step status
PENDING, RUNNING, DONE, SKIPPED, FAILED = "pending", "running", "done", "skipped", "failed"
STEP_STATUSES = (PENDING, RUNNING, DONE, SKIPPED, FAILED)

# run status
QUEUED, R_RUNNING, COMPLETED, PARTIAL, R_FAILED = "queued", "running", "completed", "partial", "failed"

SEVERITIES = ("critical", "major", "minor", "info")


def new_id(prefix: str) -> str:
    return f"{prefix}_{time.strftime('%Y%m%d%H%M%S', time.gmtime())}_{secrets.token_hex(3)}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Step:
    """One tool call in a plan. `id` is the citation handle (S1, S2, ...)."""

    id: str
    tool: str
    inputs: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    # filled by the executor
    status: str = PENDING
    summary: str = ""
    figures: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    duration_ms: int = 0
    error: str = ""
    added_by: str = ""          # "" = in the original plan; else the adaptation rule that added it
    trace_id: str = ""          # the engine's own calculation trace, when it returns one

    def to_dict(self, *, with_output: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not with_output:
            d.pop("output", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Step:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class Plan:
    goal: str
    agent: str
    planner: str                    # "deterministic" | "model" | "recorded"
    steps: list[Step] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    goal_type: str = ""
    notes: list[str] = field(default_factory=list)   # e.g. explicit skips, fallbacks
    schema: str = PLAN_SCHEMA_VERSION

    def next_step_id(self) -> str:
        return f"S{len(self.steps) + 1}"

    def add(self, tool: str, inputs: dict[str, Any] | None = None, why: str = "", added_by: str = "") -> Step:
        s = Step(id=self.next_step_id(), tool=tool, inputs=dict(inputs or {}), why=why, added_by=added_by)
        self.steps.append(s)
        return s

    def shape(self) -> list[str]:
        return [s.tool for s in self.steps]

    def to_dict(self, *, with_output: bool = True) -> dict[str, Any]:
        return {"schema": self.schema, "goal": self.goal, "agent": self.agent, "planner": self.planner,
                "goal_type": self.goal_type, "context": self.context, "notes": list(self.notes),
                "steps": [s.to_dict(with_output=with_output) for s in self.steps]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Plan:
        return cls(goal=d.get("goal", ""), agent=d.get("agent", ""), planner=d.get("planner", ""),
                   steps=[Step.from_dict(s) for s in d.get("steps", [])], context=dict(d.get("context") or {}),
                   goal_type=d.get("goal_type", ""), notes=list(d.get("notes") or []),
                   schema=d.get("schema", PLAN_SCHEMA_VERSION))


@dataclass
class Finding:
    """A finding; `evidence` lists step ids (and optional field paths) that support it."""

    title: str
    severity: str = "info"
    detail: str = ""
    evidence: list[str] = field(default_factory=list)   # e.g. ["S3", "S5:metrics.raroc"]
    kind: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Run:
    run_id: str
    agent: str
    goal: str
    context: dict[str, Any]
    trigger: str = "on_demand"      # on_demand | scheduled | chat | event
    scope: str = ""                 # e.g. "DD-07" or "corporate"
    status: str = QUEUED
    plan: Plan | None = None
    findings: list[Finding] = field(default_factory=list)
    narrative: str = ""
    output: dict[str, Any] = field(default_factory=dict)       # agent-specific (e.g. the committee pack)
    proposals: list[str] = field(default_factory=list)          # approval ids
    budget: dict[str, Any] = field(default_factory=dict)
    stopped: str = ""               # why the run stopped early, in words
    user: str = ""
    created_at: str = field(default_factory=now_iso)
    finished_at: str = ""
    duration_ms: int = 0
    model: str = ""
    citation_check: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, with_output: bool = True) -> dict[str, Any]:
        return {"run_id": self.run_id, "agent": self.agent, "goal": self.goal, "context": self.context,
                "trigger": self.trigger, "scope": self.scope, "status": self.status,
                "plan": self.plan.to_dict(with_output=with_output) if self.plan else None,
                "findings": [f.to_dict() for f in self.findings], "narrative": self.narrative,
                "output": self.output if with_output else {}, "proposals": list(self.proposals),
                "budget": self.budget, "stopped": self.stopped, "user": self.user,
                "created_at": self.created_at, "finished_at": self.finished_at,
                "duration_ms": self.duration_ms, "model": self.model, "citation_check": self.citation_check}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Run:
        r = cls(run_id=d["run_id"], agent=d.get("agent", ""), goal=d.get("goal", ""),
                context=dict(d.get("context") or {}))
        for k in ("trigger", "scope", "status", "narrative", "output", "proposals", "budget", "stopped", "user",
                  "created_at", "finished_at", "duration_ms", "model", "citation_check"):
            if k in d and d[k] is not None:
                setattr(r, k, d[k])
        r.plan = Plan.from_dict(d["plan"]) if d.get("plan") else None
        r.findings = [Finding(**f) for f in d.get("findings") or []]
        return r

    def step(self, sid: str) -> Step | None:
        if not self.plan:
            return None
        return next((s for s in self.plan.steps if s.id == sid), None)

    def done(self, tool: str) -> Step | None:
        """The last completed step of a tool (agents read results through this)."""
        if not self.plan:
            return None
        hits = [s for s in self.plan.steps if s.tool == tool and s.status == DONE]
        return hits[-1] if hits else None
