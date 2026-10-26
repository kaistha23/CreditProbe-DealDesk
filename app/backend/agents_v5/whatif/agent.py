"""The What-If scenario agent `whatif.scenarios` (PLAN_R11_AGENTS Session W).

Goal in plain words -> graded scenarios with stated shocks and basis -> runs (Delta, an XGBoost cross-check) with
likelihood and attributions -> management actions as further runs (ECL and capital effect) -> overlay range ->
comparison -> ECL committee note. The plan is data (`deterministic_plan`); `adapt` adds steps the results call for.
Two proposals (A4): the scenario set as the quarter's official sensitivity, and the overlay range for the ECL
committee. Results land in the What-If thread as the existing result cards (`thread.post`).
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from backend.agentic.registry import Agent
from backend.agents_v5.runtime import (AgentDef, Adaptation, Conclusion, Finding, Plan, ProposalSpec, Run, Step,
                                       register_agent, register_applier)
from backend.agents_v5.runtime.citations import check as citation_check
from backend.agents_v5.whatif import goals, note, thread
from backend.agents_v5.whatif import tools as W

AGENT_ID = "whatif.scenarios"
GOAL_TYPES = {
    "impact_and_actions": "What a theme or sector shock would do to the book and which management actions help",
    "provision_adequacy": "Whether the reported ECL is enough under graded scenarios",
    "overlay": "What management overlay range the scenario runs support, with its rationale",
    "sensitivity": "A graded sensitivity set for the quarter",
}
SCENARIOS = ("mild", "moderate", "severe", "tail")
ACTIONS = ("limit_cut", "cash_margin", "no_new_money", "collateral_top")
#: Severity label only (never a figure in the narrative): a scenario that takes the illustrative CET1 below the
#: Basel III minimum plus the capital conservation buffer (4.5% + 2.5%) is critical.
CET1_FLOOR_PCT = 7.0
#: A model spread larger than this share of the Delta change on the moderate scenario adds an XGBoost severe run.
MODEL_SPREAD = 0.25

SPEC = Agent(
    agent_id=AGENT_ID,
    business_name="What-If scenario agent",
    purpose=("Turns a plain-words goal into graded What-If scenarios with stated shocks and basis, runs them through the "
             "What-If engines, tests management actions, sizes a management overlay and drafts the ECL committee note."),
    when_to_use=("a question about what a theme or sector shock would do to the book and what to do about it",
                 "provisioning adequacy under graded scenarios", "sizing a management overlay"),
    when_not_to_use=("a single scenario with its shocks named: the What-If chat runs it as today",),
    allowed_capabilities=("scenario_analysis",),
    allowed_tools=tuple(t.name for t in W.TOOLS),
    allowed_data_domains=("whatif_v5",),
    allowed_methods=("delta", "xgboost"),
    maximum_steps=24,
    timeout_seconds=900,
    max_model_calls=4,
    max_rows_scanned=2_500_000,
    human_approval_requirements=("whatif.sensitivity_set", "whatif.management_overlay"),
    escalation_rules=("the official sensitivity set is approved by the CCO",),
    owner="Credit Risk",
)


def _ctx_goal(goal: str, ctx: dict[str, Any]) -> goals.Goal:
    g = goals.detect(goal, str(ctx.get("domain") or "corporate"))
    if ctx.get("themes"):
        g.themes = [t for t in ctx["themes"] if t]
    if ctx.get("segments"):
        g.segments = [s for s in ctx["segments"] if s]
    if not g.is_goal:
        # Asked to run as an agent anyway: treat it as an impact-and-actions goal on what it names.
        g.kind = g.kind or "impact_and_actions"
        g.segments = g.segments or goals.segments_in(goal, str(ctx.get("domain") or "corporate"))
        g.themes = g.themes or [k for k, p in goals.THEMES.items() if __import__("re").search(p, goal.lower())] or \
            ([] if g.segments else ["slowdown"])
    return g


def _stated_reads(goal: str, domain: str) -> bool:
    from backend.whatif_v5.chat import language
    return bool(language.read(goal, W._vocab(domain)).steps)


def classify(goal: str, ctx: dict[str, Any]) -> str:
    return str(ctx.get("goal_type") or _ctx_goal(goal, ctx).kind or "impact_and_actions")


def deterministic_plan(goal: str, goal_type: str, ctx: dict[str, Any]) -> Plan:
    g = _ctx_goal(goal, ctx)
    domain = str(ctx.get("domain") or "corporate")
    p = Plan(goal=goal, agent=AGENT_ID, planner="deterministic", context=ctx, goal_type=goal_type)
    p.add("whatif_book_profile", {"domain": domain, "segments": g.segments}, "the population in scope and its reported ECL")
    p.add("whatif_design_scenarios", {"domain": domain, "themes": g.themes, "segments": g.segments, "count": 4,
                                      **({"stated": goal} if g.has_size else {})},
          "graded scenarios, every shock sized from history, read back through the compound parser")
    for k in SCENARIOS:
        p.add("whatif_run_scenario", {"scenario": k, "method": "delta"}, f"the {k} scenario: ECL, capital, likelihood, drivers")
    if g.has_size and _stated_reads(goal, domain):
        p.add("whatif_run_scenario", {"scenario": "stated", "method": "delta"}, "the goal's own shocks, as stated")
    p.add("whatif_run_scenario", {"scenario": "moderate", "method": "xgboost"}, "model risk: the moderate scenario on XGBoost")
    if goal_type != "sensitivity":
        for a in ACTIONS:
            p.add("whatif_test_action", {"action": a, "on": "severe", "method": "delta", "segments": g.segments},
                  f"management action {a.replace('_', ' ')} on the severe scenario")
        p.add("whatif_test_action", {"action": "package", "on": "severe", "method": "delta", "segments": g.segments},
              "all four actions together")
    p.add("whatif_size_overlay", {"segments": g.segments, "low": "moderate", "high": "severe"},
          "the overlay range from the runs")
    p.add("whatif_compare", {}, "scenarios and actions in one table")
    p.notes.append(f"goal: {g.kind or goal_type}; themes: {', '.join(g.themes) or 'none'}; "
                   f"segments: {', '.join(g.segments) or 'the book'}")
    return p


def required_tools(goal_type: str, ctx: dict[str, Any]) -> list[str]:
    return ["whatif_design_scenarios", "whatif_run_scenario", "whatif_size_overlay", "whatif_compare"]


def _insert_before_tail(run: Run, tool: str, inputs: dict[str, Any], why: str, rule: str) -> None:
    """Add a step before the overlay and the comparison (they read every run), with a fresh id."""
    p = run.plan
    if p is None or any(s.tool == tool and s.inputs == inputs for s in p.steps):
        return
    s = Step(id=p.next_step_id(), tool=tool, inputs=dict(inputs), why=why, added_by=rule)
    at = next((i for i, x in enumerate(p.steps) if x.status == "pending" and x.tool in ("whatif_size_overlay", "whatif_compare")),
              len(p.steps))
    p.steps.insert(at, s)


def adapt(run: Run, step: Step) -> list[Adaptation]:
    if step.tool == "whatif_run_scenario" and step.inputs.get("method") == "xgboost" and run.plan \
            and step.inputs.get("scenario") == "moderate":
        d = next((s for s in run.plan.steps if s.tool == "whatif_run_scenario" and s.status == "done"
                  and s.inputs.get("scenario") == "moderate" and s.inputs.get("method") == "delta"), None)
        if d is not None:
            a, b = float(d.figures.get("change", 0.0)), float(step.figures.get("change", 0.0))
            if abs(a) > 1e-9 and abs(b - a) > MODEL_SPREAD * abs(a):
                _insert_before_tail(run, "whatif_run_scenario", {"scenario": "severe", "method": "xgboost"},
                                    f"the two methods differ by more than {MODEL_SPREAD:.0%} on the moderate scenario: run "
                                    "the severe scenario on XGBoost too, so the overlay's high end covers model risk",
                                    "model_spread->xgboost_severe")
    return []


# ------------------------------------------------------------------ conclude

def _findings(run: Run, ix: dict[str, Any]) -> list[Finding]:
    F: list[Finding] = []
    for key in SCENARIOS + ("stated",):
        hit = ix["runs"].get(f"{key}:delta")
        if not hit:
            continue
        s, r = hit
        c = r["result"]["cards"]
        sev = "critical" if c["capital_cet1_after_pct"] < CET1_FLOOR_PCT else "major" if c["change_pct"] > 25 else \
            "minor" if c["change_pct"] > 5 else "info"
        F.append(Finding(title=f"{r['name']}: ECL {note.sm(c['change'])} ({c['change_pct']:+.1f}%)", severity=sev,
                         detail=f"CET1 {c['capital_cet1_after_pct']:.2f}%, Stage 2 {c['stage_after']['2']:,}; "
                                f"{r['likelihood'].get('label', '')}.",
                         evidence=[s.id], kind="scenario",
                         data={"scenario": key, "run_id": r["run_id"]}))
    for k, (s, a) in ix["actions"].items():
        e = a["effects"]
        F.append(Finding(title=f"{a['definition']['what'] if a['action'] != 'package' else 'All four actions'}: "
                               f"ECL {note.sm(e['ecl_effect'])}",
                         severity="info", detail=f"Capital {note.sm(e['capital_effect'])}, CET1 {e['cet1_effect_pp']:+.2f}pp.",
                         evidence=[s.id], kind="action", data={"action": a["action"], "run_id": a["run_id"]}))
    if ix["overlay"]:
        s, o = ix["overlay"]
        F.append(Finding(title=f"Overlay range {note.m(o['overlay_low'])} to {note.m(o['overlay_high'])}", severity="major",
                         detail=o["rule"], evidence=[s.id], kind="overlay"))
    xm, dm = ix["runs"].get("moderate:xgboost"), ix["runs"].get("moderate:delta")
    if xm and dm:
        F.append(Finding(title="Model cross-check on the moderate scenario", severity="minor",
                         detail=f"XGBoost {note.sm(xm[1]['result']['cards']['change'])}, Delta {note.sm(dm[1]['result']['cards']['change'])}.",
                         evidence=[xm[0].id, dm[0].id], kind="model_risk"))
    if ix["design"]:
        s, d = ix["design"]
        off = [sc["name"] for sc in d["scenarios"] if not sc["parser"]["agrees"]]
        if off:
            F.append(Finding(title="Compound parser reads some definitions differently", severity="info",
                             detail="Run on the structured shocks: " + ", ".join(off) + ".", evidence=[s.id], kind="parser"))
    return F


def conclude(run: Run) -> Conclusion:
    ix = note.index(run)
    g = _ctx_goal(run.goal, run.context)
    kind = run.plan.goal_type if run.plan else g.kind
    text = note.committee_note(run, kind, run.goal)
    figs = {s.id: s.figures for s in (run.plan.steps if run.plan else []) if s.status == "done"}
    chk = citation_check(text, figs)
    output: dict[str, Any] = {
        "headline": note.headline(run, ix, kind).split(" [")[0],
        "goal": g.to_dict(), "goal_type": kind, "committee_note": text, "note_citation_check": chk,
        "comparison": ix["compare"][1]["rows"] if ix["compare"] else [],
        "overlay": ix["overlay"][1] if ix["overlay"] else None,
        "scenarios": [{"key": sc["key"], "name": sc["name"], "sentence": sc["sentence"], "basis": sc["basis"],
                       "parser": sc["parser"]} for sc in (ix["design"][1]["scenarios"] if ix["design"] else [])],
        "runs": {k: {"step": s.id, "run_id": r["run_id"], "scenario": r["scenario"], "method": r["method"]}
                 for k, (s, r) in ix["runs"].items()},
        "actions": {k: {"step": s.id, "run_id": a["run_id"], "definition": a["definition"], "effects": a["effects"]}
                    for k, (s, a) in ix["actions"].items()},
    }
    proposals: list[ProposalSpec] = []
    if ix["design"] and ix["runs"]:
        s, d = ix["design"]
        sset = [{"name": sc["name"], "domain": sc["domain"], "period": sc["period"],
                 "scenario": next((r["scenario"] for k, (_, r) in ix["runs"].items() if k == f"{sc['key']}:delta"), None),
                 "description": sc["sentence"], "basis": [b.get("basis", "") for b in sc["basis"]]} for sc in d["scenarios"]]
        proposals.append(ProposalSpec(
            kind="whatif.sensitivity_set", title="Save this scenario set as the quarter's official sensitivity",
            change={"scenarios": [x for x in sset if x["scenario"]], "period": d["scenarios"][0]["period"],
                    "domain": d["scenarios"][0]["domain"], "goal": run.goal, "agent_run": run.run_id},
            approver_role="CCO", reason="Graded scenarios with stated shocks and basis; every run reproduces from its definition.",
            evidence=[s.id] + [x.id for (x, _) in ix["runs"].values()], expires_hours=168, risk="medium"))
    if ix["overlay"]:
        s, o = ix["overlay"]
        proposals.append(ProposalSpec(
            kind="whatif.management_overlay",
            title=f"Note a management overlay range of {note.m(o['overlay_low'])} to {note.m(o['overlay_high'])} for the ECL committee",
            change={"low": o["overlay_low"], "high": o["overlay_high"], "point": o["overlay_point"], "segments": o["segments"],
                    "rule": o["rule"], "agent_run": run.run_id, "goal": run.goal},
            approver_role="CCO", reason=o["rule"], evidence=[s.id], expires_hours=168, risk="high"))
    posted = thread.post(run, ix, text, output)
    output["thread"] = posted
    return Conclusion(findings=_findings(run, ix), narrative=note.narrative(run, kind), output=output, proposals=proposals)


# ------------------------------------------------------------------ appliers (run only when a person approves)

def _register_file() -> pathlib.Path:
    from backend.whatif_v5 import paths
    p = paths.V5 / "var" / "agents_v5" / "whatif" / "overlays.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def apply_sensitivity_set(change: dict[str, Any]) -> dict[str, Any]:
    """Approved: the scenarios go into the What-If scenario repository, tagged as the quarter's sensitivity."""
    from backend.whatif_v5.chat.store import Store
    st = Store()
    saved = []
    for i, x in enumerate(change.get("scenarios") or []):
        sid = f"sens-{change.get('domain')}-{change.get('period')}-{i + 1}"
        st.save_scenario({"scenario_id": sid, "owner": "", "team": "", "name": x["name"],
                          "description": x.get("description", ""), "domain": x["domain"], "period": x["period"],
                          "method": "delta", "scenario": x["scenario"], "tags": ["official-sensitivity", str(change.get("period"))],
                          "standard": False, "created_at": time.time()})
        saved.append(sid)
    return {"saved": saved}


def apply_overlay(change: dict[str, Any]) -> dict[str, Any]:
    """Approved: the overlay range is recorded for the ECL committee (no ECL figure is changed)."""
    p = _register_file()
    rows = json.loads(p.read_text()) if p.exists() else []
    rows.append({**change, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    p.write_text(json.dumps(rows, indent=1))
    return {"recorded": len(rows)}


AGENT = AgentDef(spec=SPEC, module="whatif", goal_types=GOAL_TYPES, classify=classify,
                 deterministic_plan=deterministic_plan, conclude=conclude, adapt=adapt, required_tools=required_tools,
                 scope_of=lambda ctx: str(ctx.get("thread_id") or ctx.get("domain") or "corporate"),
                 system_prompt=("You plan for the CreditProbe What-If scenario agent. Design graded scenarios with "
                                "whatif_design_scenarios, run each with whatif_run_scenario (scenario keys mild, moderate, "
                                "severe, tail; method delta, plus xgboost on moderate), test management actions on the "
                                "severe scenario with whatif_test_action, then whatif_size_overlay and whatif_compare. "
                                "You never produce a figure."),
                 href=lambda run: f"/what-if/thread/{run.context['thread_id']}" if run.context.get("thread_id") else "/what-if")


def register() -> None:
    W.register()
    register_agent(AGENT)
    register_applier("whatif.sensitivity_set", apply_sensitivity_set)
    register_applier("whatif.management_overlay", apply_overlay)


__all__ = ["AGENT", "AGENT_ID", "SPEC", "classify", "conclude", "deterministic_plan", "register"]
