"""Deterministic plans per goal type (A2), the tools a model plan must keep, and the adaptations (the plan grows with
what it finds: one investigation per material move, then the record, the notification and the set review).

  setup    "Set up monitoring for the corporate book" (or a segment, a sector, a lens): plan what is worth monitoring
  run      "Run monitoring" (the scheduled goal): compute, detect, investigate, explain, notify, review the set
  review   "Review the monitoring set": retire or re-threshold metrics that never fire or fire constantly
"""
from __future__ import annotations

import re
from typing import Any

from backend.agents_v5.lenses import tools as T
from backend.agents_v5.runtime import Adaptation, Plan, Run, Step

GOAL_TYPES = {
    "setup": "Plan what is worth monitoring on a book, segment, sector or lens: candidates from composition, risk appetite, "
             "regulation, recent movement and materiality; thresholds back-tested over 8 quarters; ranked and de-duplicated; "
             "proposed for approval.",
    "run": "Run the approved monitoring set: compute, detect material moves, investigate each (segment, rating, borrower, "
           "driver, Early Warning, What-If), explain with evidence, notify, and review the set.",
    "review": "Review the approved set: propose retiring or re-thresholding metrics that never fire or fire constantly.",
}

SETUP = [
    ("lenses_scope", {}, "Find the book, segment or lens the goal is about"),
    ("lenses_composition", {}, "Concentrations, large exposures and growth segments"),
    ("lenses_risk_appetite", {}, "Risk-appetite limits and triggers"),
    ("lenses_regulation", {}, "CBUAE CRM metrics and breach checks"),
    ("lenses_movement", {}, "What moved most last quarter and what is volatile"),
    ("lenses_candidates", {}, "Candidate metrics from the five sources"),
    ("lenses_materiality", {}, "Share of EAD and ECL at stake"),
    ("lenses_backtest", {}, "Thresholds and their alert rate over 8 quarters"),
    ("lenses_rank", {}, "Rank by value and drop redundant metrics"),
    ("lenses_propose_set", {}, "Ask a risk approver to accept the set"),
]
RUN = [
    ("lenses_scope", {}, "The scope of the monitoring set"),
    ("lenses_load_set", {}, "The approved metrics and thresholds"),
    ("lenses_compute", {}, "Compute every metric now"),
    ("lenses_detect", {}, "Which moves are material"),
]
REVIEW = [
    ("lenses_scope", {}, "The scope of the monitoring set"),
    ("lenses_load_set", {}, "The approved metrics and thresholds"),
    ("lenses_review", {}, "Never-firing and always-firing metrics"),
    ("lenses_propose_changes", {}, "Propose retiring or re-thresholding"),
]
PLANS = {"setup": SETUP, "run": RUN, "review": REVIEW}
REQUIRED = {"setup": ["lenses_scope", "lenses_candidates", "lenses_backtest", "lenses_rank", "lenses_propose_set"],
            "run": ["lenses_scope", "lenses_load_set", "lenses_compute", "lenses_detect"],
            "review": ["lenses_scope", "lenses_load_set", "lenses_review", "lenses_propose_changes"]}


def classify(goal: str, ctx: dict[str, Any] | None = None) -> str:
    c = ctx or {}
    if c.get("goal_type") in GOAL_TYPES:
        return c["goal_type"]
    g = goal.lower()
    if re.search(r"\b(retire|re-?threshold|tune|prune|review (the )?(monitoring )?set|still earn)", g):
        return "review"
    if re.search(r"\b(run|check|scan|execute)\b.*\bmonitor", g) or g.strip() in ("run monitoring", "monitor now"):
        return "run"
    return "setup"


def deterministic_plan(goal: str, goal_type: str, ctx: dict[str, Any]) -> Plan:
    """The written plan. The scope is resolved here (once) and travels in the run context for every tool."""
    if not ctx.get("scope"):
        ctx["scope"] = T.resolve_scope(goal, ctx)
    ctx.setdefault("goal", goal)
    p = Plan(goal=goal, agent="lenses.monitoring", planner="deterministic", context=ctx, goal_type=goal_type)
    for tool, inputs, why in PLANS[goal_type]:
        p.add(tool, dict(inputs), why=why)
    return p


def required_tools(goal_type: str, ctx: dict[str, Any]) -> list[str]:
    return list(REQUIRED.get(goal_type, []))


def investigation(alert: dict[str, Any]) -> list[Adaptation]:
    k, lab = alert["key"], alert["label"]
    rule = f"investigate:{k}"
    return [
        Adaptation("lenses_decompose", {"alert": k, "by": "segment"}, f"Which segments moved {lab}", rule),
        Adaptation("lenses_decompose", {"alert": k, "by": "rating"}, f"Which rating grades moved {lab}", rule),
        Adaptation("lenses_decompose", {"alert": k, "by": "borrower"}, f"Which names moved {lab}", rule),
        Adaptation("lenses_driver", {"alert": k}, "Numerator or denominator", rule),
        Adaptation("lenses_ews_read", {"alert": k}, "Early Warning on the names behind it", rule),
        Adaptation("lenses_whatif_read", {"alert": k}, "ECL sensitivity of the segment behind it", rule),
    ]


def adapt(run: Run, step: Step) -> list[Adaptation]:
    """After detect: one investigation per new or worsened alert (up to the per-run budget), then record and notify,
    then review the set and propose changes. A setup run whose scope has no data adapts to nothing."""
    if step.tool != "lenses_detect":
        return []
    det = step.output or {}
    alerts = {a["key"]: a for a in det.get("alerts", [])}
    out: list[Adaptation] = []
    for k in det.get("investigate", []):
        if k in alerts:
            out += investigation(alerts[k])
    out.append(Adaptation("lenses_notify", {"after": "investigation"}, "Record the alerts with their explanations and notify", "always"))
    out.append(Adaptation("lenses_review", {"after": "investigation"}, "Does every metric still earn its place", "always"))
    out.append(Adaptation("lenses_propose_changes", {"after": "investigation"}, "Propose retiring or re-thresholding", "always"))
    return out
