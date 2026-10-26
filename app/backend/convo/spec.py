"""What a domain hands the conversational layer: its relations, tools, knowledge and planner.

A domain is the only thing a module writes to get a Cockpit-style conversation.
The layer (store, events, worker, the agent loop, validation, the router) is
the same for every module; the domain decides what the assistant can see and
do, and nothing outside it is reachable:

  relations   the tables the assistant may query (DuckDB, one locked session per
              domain and scope; SELECT only; no file or network access)
  tools       the module's engines, called by the assistant like the Cockpit's
              tools (a scenario engine, a validation test). A tool marked
              `action=True` changes something (runs a scenario, writes a report)
              and is offered only on a turn the user asked to execute.
  knowledge   method notes the assistant can read (how a number is made), by topic
  planner     the deterministic plan used when no model key is present (the sweep
              and the tests run on it): the same tools, the same validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd


@dataclass
class Relation:
    name: str
    description: str
    #: scope -> the rows. Called once per (domain, scope key) and cached in the session.
    load: Callable[[dict[str, Any]], pd.DataFrame]
    grain: str = ""
    columns: dict[str, str] = field(default_factory=dict)


@dataclass
class ToolResult:
    """What a tool returns. `data` goes back to the model (compact JSON); `rows` become an
    artifact the answer can show as a table or chart and whose figures it may quote;
    `blocks` are module-specific answer blocks published as they are (a scenario proposal)."""
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] | None = None       # merged into the thread state when the turn settles
    title: str = ""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[["ToolContext", dict[str, Any]], ToolResult]
    action: bool = False
    message: str = ""                          # what the process panel shows while it runs


@dataclass
class ToolContext:
    domain: "Domain"
    thread: dict[str, Any]
    state: dict[str, Any]                      # the thread state as this turn sees it (tools may read it)
    scope: dict[str, Any]
    user: dict[str, Any]
    question: str
    execute: bool


@dataclass
class PlanStep:
    tool: str                                   # "run_query", "read_knowledge", "inspect_catalog" or a domain tool
    args: dict[str, Any]


@dataclass
class Plan:
    """The deterministic planner's answer: tool calls, then a writer that composes the final
    answer from what they returned (the same shape the model's `finalize_answer` sends)."""
    steps: list[PlanStep]
    write: Callable[[list[dict[str, Any]]], dict[str, Any]]


@dataclass
class Domain:
    key: str
    title: str
    #: The domain's charter: who the assistant is and what it is for (the system prompt's first part).
    charter: str
    relations: Callable[[dict[str, Any]], list[Relation]]
    tools: list[Tool] = field(default_factory=list)
    knowledge: dict[str, str] = field(default_factory=dict)
    planner: Callable[[str, "ToolContext"], Plan] | None = None
    #: scope -> a short label ("the corporate book at 2026Q2")
    scope_label: Callable[[dict[str, Any]], str] = lambda s: ""
    #: scope -> the session cache key (relations are rebuilt when it changes)
    scope_key: Callable[[dict[str, Any]], str] = lambda s: repr(sorted(s.items()))
    #: (scope, state) -> follow-up chips shown when the thread opens or after a turn
    suggestions: Callable[[dict[str, Any], dict[str, Any]], list[dict[str, str]]] = lambda s, st: []
    #: Extra context lines for the system prompt from the thread state (the pending scenario, the last result).
    state_brief: Callable[[dict[str, Any]], str] = lambda st: ""
    max_steps: int = 8

    def tool(self, name: str) -> Tool | None:
        return next((t for t in self.tools if t.name == name), None)
