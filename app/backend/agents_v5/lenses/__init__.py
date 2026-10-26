"""R11 Session K: the Lenses monitoring agent `lenses.monitoring` (PLAN_R11_AGENTS K1-K4).

Importing the package registers its tools, the agent definition and the approval appliers with the agents_v5
runtime, and mounts the panel's routes (`api.router`) on the agents service when that service is the importer.
"""
from backend.agents_v5.lenses import agent as _agent

DEF = _agent.register()

try:
    from backend.agents_v5.lenses import api as _api
    _api.mount_on_agents_service()
except Exception:  # noqa: BLE001 - the panel routes never stop the agent loading
    pass
