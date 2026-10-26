"""Deterministic plans per goal type (A2): the written reference plan the model planner is checked against.

Goal types: `period` ("Triage this period's warnings", scheduled after each EWS refresh), `borrower`
("Triage CB00123" or a borrower's name) and `sector` ("Triage Construction").

The written plan gathers the evidence and decides; what follows depends on what it found (`adapt`):
- ECL impact and the proposal steps are added only for the verdicts that need them (UTP, SICR, watchlist);
- follow-up is added only when this agent has followed any of the names before (an earlier verdict or an open action);
- the summary closes every plan.
Steps chain through the runtime's `ctx.results` (each tool reads what the earlier tools returned).
"""
from __future__ import annotations

import re
from typing import Any

from backend.agents_v5.runtime import Adaptation, Plan

AGENT_ID = "ews.triage"
GOAL_TYPES = {
    "period": "Triage this period's warnings (all warned borrowers, plus names followed up from earlier runs).",
    "borrower": "Triage one borrower (id like CB00123, or its name).",
    "sector": "Triage the warned borrowers of one sector.",
}

#: The evidence and decision steps every goal type runs, in order.
BASE = ("ews_warned_names", "ews_rules_trend", "b360_evidence", "conduct_account", "bureau_external",
        "ews_sector_peers", "ews_changes", "triage_history", "crm_assess", "triage_decide")
WHY = {
    "ews_rules_trend": "Which rules fired and how the score moved over six periods.",
    "b360_evidence": "Borrower 360: exposure, group, collateral, covenants, open conditions.",
    "conduct_account": "Account conduct: turnover against revenue, returned payments, overdraft behaviour, routing.",
    "bureau_external": "The bureau where the books have it.",
    "ews_sector_peers": "Peers in the same sector: is it the name or the sector?",
    "ews_changes": "What changed since last period.",
    "triage_history": "What this agent found before: verdicts, open actions, pending proposals.",
    "crm_assess": "Test the evidence against the CBUAE CRM SICR (Art. 7) and UTP (Art. 6) indicators.",
    "triage_decide": "Decide noise / watch / watchlist / SICR / UTP and draft the RM action notes.",
}


def parse_goal(goal: str, context: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """`(goal_type, params)` from the goal text and context. Context wins over the text."""
    ctx = dict(context or {})
    text = (goal or "").strip()
    params: dict[str, Any] = {"domain": ctx.get("domain") or "corporate", "period": ctx.get("period") or ""}
    if ctx.get("borrower"):
        return "borrower", {**params, "borrower": str(ctx["borrower"])}
    if ctx.get("sector"):
        return "sector", {**params, "sector": str(ctx["sector"])}
    m = re.search(r"\bCB\d{4,6}\b", text, re.I)
    if m:
        return "borrower", {**params, "borrower": m.group(0).upper()}
    m = re.search(r"\bRC\d{5,7}\b", text, re.I)
    if m:
        return "borrower", {**params, "domain": "retail", "borrower": m.group(0).upper()}
    if re.search(r"\bretail\b", text, re.I) and not ctx.get("domain"):
        params["domain"] = "retail"
    m = re.match(r"^\s*triage\s+(?:the\s+)?(.+?)(?:\s+sector)?\s*$", text, re.I)
    if m and not re.search(r"period|quarter|warnings|book|portfolio|month|this", m.group(1), re.I):
        target = m.group(1).strip().strip("'\"")
        for dom in dict.fromkeys([params["domain"], "corporate", "retail"]):
            hit = next((s for s in _sectors(dom) if s.lower() == target.lower()), None)
            if hit:
                return "sector", {**params, "domain": dom if not ctx.get("domain") else params["domain"], "sector": hit}
        return "borrower", {**params, "borrower": target}
    return "period", params


def _sectors(domain: str) -> list[str]:
    try:
        from backend.ews_domain import reader as rd
        col = rd.domain_spec(domain)["segment"]
        return [r["s"] for r in rd.q(f'SELECT DISTINCT "{col}" AS s FROM {rd.exposure(domain)}')]
    except Exception:  # noqa: BLE001
        return []


def classify(goal: str, context: dict[str, Any]) -> str:
    gt, params = parse_goal(goal, context)
    context.update({k: v for k, v in params.items() if v and k not in context})
    return gt


def deterministic_plan(goal: str, goal_type: str, context: dict[str, Any]) -> Plan:
    _, p = parse_goal(goal, context)
    d, per = p["domain"], p["period"]
    p1: dict[str, Any] = {"domain": d, "period": per,
                          "max_names": int(context.get("max_names") or (800 if d == "retail" else 1500))}
    if goal_type == "borrower":
        p1.update(borrower=p.get("borrower") or context.get("borrower", ""), include_followed=False)
    elif goal_type == "sector":
        p1.update(sector=p.get("sector") or context.get("sector", ""), include_followed=False)
    else:
        p1.update(include_followed=True)
    plan = Plan(goal=goal, agent=AGENT_ID, planner="deterministic", context=context, goal_type=goal_type)
    plan.add("ews_warned_names", p1, {
        "period": "Who is warned this period; set aside Stage 3; add names followed up from earlier runs.",
        "borrower": "Find the borrower, its warning and its stage.",
        "sector": "The warned borrowers of the sector."}[goal_type])
    for tool in BASE[1:]:
        inputs = {"domain": d} if tool not in ("crm_assess", "triage_decide") else {}
        if tool == "b360_evidence" and goal_type == "borrower":
            inputs["profile"] = True
        plan.add(tool, inputs, WHY[tool])
    return plan


def adapt(run: Any, step: Any) -> list[Adaptation]:
    """After the decision: size and propose only what the verdicts need; follow up only names already followed."""
    if step.tool != "triage_decide":
        return []
    counts = step.figures or {}
    h = run.done("triage_history")
    hist = (h.figures or {}) if h else {}
    d = (run.plan.steps[0].inputs or {}).get("domain", "corporate") if run.plan else "corporate"
    out: list[Adaptation] = []
    if counts.get("utp") or counts.get("sicr") or counts.get("watchlist"):
        out.append(Adaptation("ecl_impact", {"domain": d}, "Size the ECL impact of each proposal (EWS method).",
                              "proposals->ecl_impact"))
    if hist.get("previous") or hist.get("actions"):
        out.append(Adaptation("triage_followup", {}, "Revisit names followed before: cured, worsened, overdue; "
                              "escalate.", "followed->followup"))
    for kind, tool in (("utp", "propose_utp"), ("sicr", "propose_sicr"), ("watchlist", "propose_watchlist")):
        if counts.get(kind):
            out.append(Adaptation(tool, {}, f"{counts[kind]} {kind} verdicts: proposals to the approvals queue.",
                                  f"{kind}->propose"))
    out.append(Adaptation("triage_summary", {}, "The portfolio summary.", "always->summary"))
    return out


def required_tools(goal_type: str, context: dict[str, Any]) -> list[str]:
    """What a model plan must keep: the warning, the indicator engine and the decision table."""
    return ["ews_warned_names", "crm_assess", "triage_decide"]


__all__ = ["AGENT_ID", "BASE", "GOAL_TYPES", "adapt", "classify", "deterministic_plan", "parse_goal", "required_tools"]
