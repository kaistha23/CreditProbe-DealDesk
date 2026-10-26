"""The What-If scenario agent (PLAN_R11_AGENTS Session W): registers its tools and `whatif.scenarios` on import.

    goals.py      goal detection (a goal vs a single scenario), mirrored in the UI
    calibrate.py  graded scenarios: every shock sized from history, with its basis
    tools.py      the tools: book profile, design, run (Delta / XGBoost), management actions, overlay, comparison
    agent.py      the agent: deterministic plan, adaptation, conclusion, proposals and their appliers
    note.py       the ECL committee note and the narrative, every figure cited by step
    thread.py     posts the results into the What-If thread as the existing result cards
"""
from backend.agents_v5.whatif.agent import AGENT, AGENT_ID, register

register()

__all__ = ["AGENT", "AGENT_ID", "register"]
