"""R11 Session E: the Early Warning triage agent `ews.triage` (PLAN_R11_AGENTS E1-E4).

Importing the package registers its tools, the agent definition, the approval appliers (record only; a stage is never
written) and the scheduled run after each EWS refresh (`@after:ews_refresh`) with the agents_v5 runtime.
"""
from backend.agents_v5.ews import agent as _agent

DEF = _agent.register()
try:
    _agent.ensure_schedule()
except Exception:  # noqa: BLE001 -- a store that cannot be written never stops the agent loading
    pass
