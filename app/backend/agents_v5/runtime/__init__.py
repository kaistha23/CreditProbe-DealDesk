"""The agents_v5 runtime: the contract of PLAN_R11_AGENTS.md (Session G).

    from backend.agents_v5.runtime import (Tool, ToolResult, ToolContext, register_tool,
        Plan, Step, Finding, Run, plan, execute, propose, schedule)

- `Tool` / `register_tool`: a wrapped engine call (read-only or proposal-only).
- `Plan`, `Step`, `Finding` (evidence = step ids), `Run`.
- `plan(goal, agent, context, planner="auto")`: model planner (key present) or deterministic.
- `execute(plan)`: runs the plan; returns the stored `Run`.
- `propose(change, approver_role, ...)`: a pending approval (never applied directly).
- `schedule(agent, cron, goal, context)`: a scheduled or event-triggered run.
- `register_agent(AgentDef(...))`: the module's agent (classify, deterministic plan, adapt,
  conclude), with `backend.agentic.registry.Agent` as its job description and budgets.
- `start(agent, goal, context)`: plan + execute in one call (what the API does).
"""
from backend.agents_v5.runtime.agents import (
                                              Adaptation,
                                              AgentDef,
                                              Conclusion,
                                              ProposalSpec,
                                              agents,
                                              get_agent,
                                              register_agent,
)
from backend.agents_v5.runtime.approvals import decide, propose, register_applier
from backend.agents_v5.runtime.executor import execute, start
from backend.agents_v5.runtime.planner import plan
from backend.agents_v5.runtime.schedules import fire_event, schedule
from backend.agents_v5.runtime.tools import (
                                              NOT_AVAILABLE,
                                              PROPOSAL_ONLY,
                                              READ_ONLY,
                                              Tool,
                                              ToolContext,
                                              ToolResult,
                                              ToolUnavailable,
                                              get_tool,
                                              register_tool,
)
from backend.agents_v5.runtime.tools import tools as all_tools
from backend.agents_v5.runtime.types import Finding, Plan, Run, Step

__all__ = ["AgentDef", "Adaptation", "Conclusion", "Finding", "NOT_AVAILABLE", "PROPOSAL_ONLY", "Plan",
           "ProposalSpec", "READ_ONLY", "Run", "Step", "Tool", "ToolContext", "ToolResult", "ToolUnavailable",
           "agents", "decide", "execute", "fire_event", "get_agent", "get_tool", "plan", "propose", "register_agent",
           "register_applier", "register_tool", "schedule", "start", "all_tools"]
