"""Agent definitions (A2, A5).

An agent is `backend.agentic.registry.Agent` (the job description: allowed tools, step,
time, model-call and rows budgets, approval requirements) plus the four things the runtime
needs from the module that owns it:

- `classify(goal, context) -> goal_type`;
- `deterministic_plan(goal, goal_type, context) -> Plan` (the written plan per goal type;
  the reference the model plan is checked against);
- `adapt(run, step) -> [Adaptation]` (optional): steps to add after a step's result;
- `conclude(run) -> Conclusion`: findings with evidence, the narrative (every figure
  cited as [S#]), the agent's output (e.g. the committee pack) and proposals.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.agentic.registry import Agent
from backend.agents_v5.runtime.types import Finding, Plan, Run, Step


@dataclass
class Adaptation:
    tool: str
    inputs: dict[str, Any] = field(default_factory=dict)
    why: str = ""
    rule: str = ""


@dataclass
class ProposalSpec:
    """A change the agent wants made; it becomes a pending approval (A4)."""

    kind: str                   # e.g. "dealdesk.condition_set", "dealdesk.counter_offer"
    title: str
    change: dict[str, Any]
    approver_role: str
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    expires_hours: int = 72
    risk: str = "medium"


@dataclass
class Conclusion:
    findings: list[Finding] = field(default_factory=list)
    narrative: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    proposals: list[ProposalSpec] = field(default_factory=list)


@dataclass
class AgentDef:
    spec: Agent
    module: str
    goal_types: dict[str, str]
    classify: Callable[[str, dict[str, Any]], str]
    deterministic_plan: Callable[[str, str, dict[str, Any]], Plan]
    conclude: Callable[[Run], Conclusion]
    adapt: Callable[[Run, Step], list[Adaptation]] | None = None
    required_tools: Callable[[str, dict[str, Any]], list[str]] | None = None
    scope_of: Callable[[dict[str, Any]], str] = lambda ctx: str(ctx.get("scope") or "")
    system_prompt: str = ""
    notify_users: tuple[str, ...] = ()
    href: Callable[[Run], str] | None = None      # where people look for the result (the module)
    #: R15 L5: tools that close the run (decision, proposals, summary). When the step budget runs out first, the
    #: executor skips the remaining evidence steps and runs these within `closing_reserve` extra steps, so a run
    #: always ends with its proposals and summary. 0 = off (the run stops PARTIAL, as before).
    closing_tools: tuple[str, ...] = ()
    closing_reserve: int = 0

    @property
    def agent_id(self) -> str:
        return self.spec.agent_id

    def describe(self) -> dict[str, Any]:
        s = self.spec
        return {"agent_id": s.agent_id, "name": s.business_name, "purpose": s.purpose, "module": self.module,
                "goal_types": self.goal_types, "tools": list(s.allowed_tools),
                "budgets": {"steps": s.maximum_steps, "timeout_seconds": s.timeout_seconds,
                            "model_calls": s.max_model_calls, "rows_scanned": s.max_rows_scanned},
                "approvals": list(s.human_approval_requirements)}


_AGENTS: dict[str, AgentDef] = {}
_LOCK = threading.Lock()


def register_agent(a: AgentDef) -> AgentDef:
    with _LOCK:
        _AGENTS[a.agent_id] = a
    return a


def get_agent(agent_id: str) -> AgentDef | None:
    return _AGENTS.get(agent_id)


def agents() -> list[AgentDef]:
    return list(_AGENTS.values())
