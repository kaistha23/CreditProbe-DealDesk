"""Tools: the only way an agent touches an engine (A1).

A tool wraps one deterministic engine call. Its callable takes the step inputs plus a
`ToolContext` and returns a `ToolResult`:
- `summary`: one line in words;
- `figures`: every number the narrative may cite, by name (the citation check reads these);
- `data`: the engine output (stored with the step; the drawer and the pack read it);
- `rows_scanned`: charged to the run's rows budget;
- `proposal`: for proposal-only tools, the change to put in the approvals queue (A4).

`available()` lets a tool say it is not on this build (an R11 engine branch not merged yet);
the executor then skips the step explicitly with that reason.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

READ_ONLY = "read_only"
PROPOSAL_ONLY = "proposal_only"
MODES = (READ_ONLY, PROPOSAL_ONLY)

NOT_AVAILABLE = "not available on this build"


class ToolUnavailable(RuntimeError):
    """Raised by a tool that discovers at call time that its engine is missing."""


@dataclass
class ToolResult:
    summary: str = ""
    figures: dict[str, Any] = field(default_factory=dict)
    data: Any = None
    rows_scanned: int = 0
    proposal: dict[str, Any] | None = None
    trace_id: str = ""


@dataclass
class ToolContext:
    run_id: str = ""
    agent: str = ""
    user: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)   # tool name -> last data, for chained steps


@dataclass
class Tool:
    name: str
    module: str
    description: str
    input_schema: dict[str, Any]
    mode: str
    fn: Callable[..., ToolResult]
    available: Callable[[], tuple[bool, str]] = field(default=lambda: (True, ""))
    engine: str = ""         # what it wraps, for the trace ("POST /api/v1/dealdesk/compute")

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"Tool {self.name}: mode must be one of {MODES}.")
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError(f"Tool name {self.name!r}: letters, digits and underscores only.")

    @property
    def read_only(self) -> bool:
        return self.mode == READ_ONLY

    def is_available(self) -> tuple[bool, str]:
        try:
            ok, why = self.available()
        except Exception as e:  # noqa: BLE001 - an availability probe never breaks planning
            return False, f"{NOT_AVAILABLE} ({type(e).__name__})"
        return bool(ok), ("" if ok else (why or NOT_AVAILABLE))

    def anthropic_schema(self) -> dict[str, Any]:
        """The tool as the model planner sees it (description and input schema only)."""
        return {"name": self.name, "description": f"[{self.mode}] {self.description}",
                "input_schema": self.input_schema or {"type": "object", "properties": {}}}

    def describe(self) -> dict[str, Any]:
        ok, why = self.is_available()
        return {"name": self.name, "module": self.module, "description": self.description,
                "input_schema": self.input_schema, "mode": self.mode, "engine": self.engine,
                "available": ok, "unavailable_reason": why}


_TOOLS: dict[str, Tool] = {}
_LOCK = threading.Lock()


def register_tool(tool: Tool | None = None, **fields: Any) -> Tool:
    """Register a tool (a `Tool`, or its fields as keywords). Re-registering a name replaces it."""
    t = tool or Tool(**fields)
    with _LOCK:
        _TOOLS[t.name] = t
    return t


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def tools(module: str = "") -> list[Tool]:
    return [t for t in _TOOLS.values() if not module or t.module == module]


def _clear_for_tests() -> None:
    with _LOCK:
        _TOOLS.clear()
