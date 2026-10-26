"""R11 specialist agents (PLAN_R11_AGENTS.md).

`runtime/` is the shared runtime (Session G): tools, plans, the executor, the run store,
the approvals bridge, budgets and schedules. Each module's agent lives in its own package
(`dealdesk/` here; `ews/`, `whatif/`, `lenses/` from Sessions E, W and K) and registers its
tools and agent on import. The service is `backend.agents_v5.api` on port 8517.

A1: the agent plans; engines compute. Nothing in this package produces a credit figure.
"""
