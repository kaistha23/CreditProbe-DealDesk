"""Generic, domain-scoped fork of the frozen Cockpit conversational architecture (PLAN_R4, G2).

A module describes its domain (`spec.Domain`: relations, tools, knowledge, planner)
and mounts `service.ConvoService`, or calls `agent.Agent` inline from its own thread
store. The contract is in docs/v5/CONVO_API.md. Nothing here imports the Cockpit.
"""
from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult  # noqa: F401
