"""Budgets (A5): `backend.agentic.budgets.Budget`, sized from the agent's registry fields."""
from __future__ import annotations

from backend.agentic import budgets as B
from backend.agentic.registry import Agent


def for_agent(spec: Agent) -> B.Budget:
    """steps -> TASKS, timeout -> RUNTIME, model calls -> MODEL_CALLS, rows scanned -> ROWS."""
    return B.Budget(limits=B.Limits(iterations=1, tasks=int(spec.maximum_steps), repairs=0,
                                    model_calls=int(spec.max_model_calls), scans=int(spec.maximum_steps),
                                    rows=int(spec.max_rows_scanned), output_chars=200_000,
                                    runtime_seconds=int(spec.timeout_seconds)))


Exhausted = B.Exhausted
TASKS, MODEL_CALLS, ROWS, RUNTIME = B.TASKS, B.MODEL_CALLS, B.ROWS, B.RUNTIME
