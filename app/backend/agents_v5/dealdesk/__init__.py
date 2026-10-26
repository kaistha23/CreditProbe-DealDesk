"""Deal Desk "Committee Preparation" agent (Session G2). Registers its tools and agent on import."""
from backend.agents_v5.dealdesk.agent import AGENT_ID, register

register()

__all__ = ["AGENT_ID"]
