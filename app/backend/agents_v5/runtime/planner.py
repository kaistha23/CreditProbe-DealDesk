"""Two planners, one plan schema (A2).

- **Deterministic**: the agent's written plan for the goal type. Always built: it runs when no
  model key is present and it is the reference the model plan is checked against.
- **Model**: the app's model key path (`backend.convo.provider`: CONVO/COCKPIT key from the
  environment, put there from the Keychain by ops/v5.sh; never printed), with tool use. The
  model sees the agent's available tools plus `submit_plan`. It may call read-only tools to
  look before it plans (those calls run through the same executor path and become done
  steps); it finishes by calling `submit_plan`. The plan is validated: known, allowed tools
  only; within the step budget; tools the reference requires are added back if dropped.
  Anything invalid falls back to the deterministic plan, with the reason in `plan.notes`.

Tests install `backend.convo.provider.Scripted` (the recorded-model harness).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from backend.agents_v5.runtime import tools as T
from backend.agents_v5.runtime.agents import AgentDef, get_agent
from backend.agents_v5.runtime.types import DONE, FAILED, Plan

SUBMIT = "submit_plan"
SUBMIT_TOOL = {
    "name": SUBMIT,
    "description": ("Submit the plan: the ordered tool calls that answer the goal. Every figure will come from these "
                    "tools; you never produce a number. List tools you deliberately leave out in `skipped`."),
    "input_schema": {
        "type": "object",
        "properties": {
            "goal_type": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "tool": {"type": "string"}, "inputs": {"type": "object"}, "why": {"type": "string"}},
                "required": ["tool"]}},
            "skipped": {"type": "array", "items": {"type": "object", "properties": {
                "tool": {"type": "string"}, "reason": {"type": "string"}}}},
        },
        "required": ["steps"],
    },
}

RULES = """Rules:
- You plan; engines compute. Never state or invent a figure.
- Use only the tools listed. A tool marked unavailable must not be planned; list it in `skipped` with the reason.
- Tools marked [proposal_only] queue a change for a person to approve; they never change state.
- Keep within {max_steps} steps. Finish by calling submit_plan exactly once."""


class PlanInvalid(ValueError):
    pass


def _agent(agent: AgentDef | str) -> AgentDef:
    a = get_agent(agent) if isinstance(agent, str) else agent
    if a is None:
        raise KeyError(f"No agent {agent!r}.")
    return a


def deterministic(goal: str, agent: AgentDef | str, context: dict[str, Any] | None = None) -> Plan:
    a = _agent(agent)
    ctx = dict(context or {})
    gt = a.classify(goal, ctx)
    p = a.deterministic_plan(goal, gt, ctx)
    p.planner, p.goal_type, p.agent, p.goal, p.context = "deterministic", gt, a.agent_id, goal, ctx
    validate(p, a)
    return p


def validate(p: Plan, a: AgentDef) -> None:
    """Schema and policy checks shared by both planners."""
    if not isinstance(p.steps, list) or not p.steps:
        raise PlanInvalid("The plan has no steps.")
    if len(p.steps) > a.spec.maximum_steps:
        raise PlanInvalid(f"{len(p.steps)} steps exceed the agent's budget of {a.spec.maximum_steps}.")
    seen = set()
    for s in p.steps:
        if not s.id or s.id in seen:
            raise PlanInvalid(f"Step id {s.id!r} is missing or repeated.")
        seen.add(s.id)
        if not a.spec.may_use(s.tool):
            raise PlanInvalid(f"{s.tool} is not one of this agent's tools.")
        if T.get_tool(s.tool) is None:
            raise PlanInvalid(f"{s.tool} is not a registered tool.")
        if not isinstance(s.inputs, dict):
            raise PlanInvalid(f"{s.id}: inputs must be an object.")


def _tool_menu(a: AgentDef) -> tuple[list[dict[str, Any]], list[str]]:
    menu, lines = [], []
    for name in a.spec.allowed_tools:
        t = T.get_tool(name)
        if t is None:
            continue
        ok, why = t.is_available()
        lines.append(f"- {name}: {'available' if ok else 'UNAVAILABLE (' + why + ')'}")
        if ok:
            menu.append(t.anthropic_schema())
    return menu, lines


#: R15 L4: planning never hangs. A model that has not answered within this many seconds (in total) is dropped
#: and the written (deterministic) plan runs instead, with the reason in the plan notes.
PLAN_SECONDS = int(os.environ.get("AGENTS_V5_PLAN_SECONDS") or 40)


def _timed(fn: Any, seconds: float) -> Any:
    """Run `fn()` in a worker thread; TimeoutError after `seconds` (the worker is abandoned, a daemon)."""
    box: dict[str, Any] = {}

    def go() -> None:
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=go, daemon=True, name="agents-v5-plan")
    th.start()
    th.join(max(0.1, seconds))
    if th.is_alive():
        raise TimeoutError
    if "e" in box:
        raise box["e"]
    return box.get("v")


def model(goal: str, agent: AgentDef | str, context: dict[str, Any] | None = None, *, provider: Any = None,
          budget: Any = None, probe: Any = None) -> Plan:
    """The model planner. `probe(plan, tool, inputs)` runs a look-ahead tool call (the executor's
    step runner); without it the model may only submit a plan."""
    from backend.convo import provider as prov
    a = _agent(agent)
    ctx = dict(context or {})
    reference = deterministic(goal, a, ctx)
    pv = provider or prov.default()
    if pv is None:
        reference.notes.append("No model key on this host: the deterministic planner ran.")
        return reference

    menu, lines = _tool_menu(a)
    system = "\n\n".join(x for x in [
        a.system_prompt or f"You are the planner for the CreditProbe agent '{a.spec.business_name}'. {a.spec.purpose}",
        "Goal types: " + "; ".join(f"{k}: {v}" for k, v in a.goal_types.items()),
        "Tools on this build:\n" + "\n".join(lines),
        RULES.format(max_steps=a.spec.maximum_steps)] if x)
    messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(
        {"goal": goal, "context": ctx, "reference_goal_type": reference.goal_type}, default=str)}]
    plan = Plan(goal=goal, agent=a.agent_id, planner="model", context=ctx, goal_type=reference.goal_type)
    max_calls = max(1, int(a.spec.max_model_calls))
    t_start = time.monotonic()
    for call in range(max_calls):
        if budget is not None:
            from backend.agents_v5.runtime.budget import MODEL_CALLS
            if not budget.try_spend(MODEL_CALLS):
                break
        left = PLAN_SECONDS - (time.monotonic() - t_start)
        if left <= 0:
            reference.notes.append(f"The model planner took longer than {PLAN_SECONDS} s; the written plan ran.")
            return reference
        try:
            reply = _timed(lambda: pv.step(f"agents_v5.plan.{a.agent_id}", system, messages, menu + [SUBMIT_TOOL]),
                           left)
        except TimeoutError:
            reference.notes.append(f"The model did not answer within {PLAN_SECONDS} s (it may not be available on "
                                   "this machine); the written plan ran.")
            return reference
        except Exception as e:  # noqa: BLE001 - provider failure falls back, with the reason
            reference.notes.append(f"Model planner failed ({type(e).__name__}); the deterministic planner ran.")
            return reference
        plan.notes.append(f"model:{pv.model()}") if call == 0 else None
        uses = reply.tool_uses()
        if not uses:
            messages += [{"role": "assistant", "content": reply.content},
                         {"role": "user", "content": "Call submit_plan with the plan."}]
            continue
        submit = next((u for u in uses if u["name"] == SUBMIT), None)
        if submit is not None:
            return _accept(plan, submit.get("input") or {}, a, reference)
        # look-ahead tool calls: run them as done steps, feed the results back
        results = []
        for u in uses:
            out = {"error": "look-ahead is not available here"}
            t = T.get_tool(u["name"])
            if t is None or not a.spec.may_use(u["name"]):
                out = {"error": f"{u['name']} is not one of this agent's tools"}
            elif not t.read_only:
                out = {"error": "proposal-only tools cannot be called while planning"}
            elif probe is not None and len(plan.steps) < a.spec.maximum_steps:
                s = plan.add(u["name"], u.get("input") or {}, why="model look-ahead", added_by="model:look-ahead")
                probe(plan, s)
                out = {"step": s.id, "status": s.status, "summary": s.summary, "figures": s.figures,
                       "error": s.error} if s.status in (DONE, FAILED) else {"step": s.id, "status": s.status,
                                                                              "reason": s.summary}
            results.append({"type": "tool_result", "tool_use_id": u.get("id", ""),
                            "content": json.dumps(out, default=str)[:4000]})
        messages += [{"role": "assistant", "content": reply.content}, {"role": "user", "content": results}]
    reference.notes.append("The model did not submit a plan within its call budget; the deterministic planner ran.")
    return reference


def _accept(plan: Plan, body: dict[str, Any], a: AgentDef, reference: Plan) -> Plan:
    try:
        steps = body.get("steps")
        if not isinstance(steps, list) or not steps:
            raise PlanInvalid("submit_plan had no steps.")
        done_tools = {(s.tool, json.dumps(s.inputs, sort_keys=True, default=str)) for s in plan.steps}
        for raw in steps:
            if not isinstance(raw, dict) or not isinstance(raw.get("tool"), str):
                raise PlanInvalid("Each step needs a tool name.")
            inputs = raw.get("inputs") or {}
            if not isinstance(inputs, dict):
                raise PlanInvalid(f"{raw['tool']}: inputs must be an object.")
            if (raw["tool"], json.dumps(inputs, sort_keys=True, default=str)) in done_tools:
                continue     # already run as a look-ahead
            plan.add(raw["tool"], inputs, why=str(raw.get("why") or ""))
        for sk in body.get("skipped") or []:
            if isinstance(sk, dict) and sk.get("tool"):
                plan.notes.append(f"Skipped {sk['tool']}: {sk.get('reason') or 'not needed'}")
        if body.get("goal_type") in a.goal_types:
            plan.goal_type = body["goal_type"]
        # the deterministic reference: required tools the model dropped are added back
        req = a.required_tools(plan.goal_type, plan.context) if a.required_tools else []
        have = set(plan.shape())
        for name in req:
            t = T.get_tool(name)
            if name not in have and t is not None and t.is_available()[0]:
                ref = next((s for s in reference.steps if s.tool == name), None)
                plan.add(name, ref.inputs if ref else {}, why="required by the reference plan",
                         added_by="reference:required")
        validate(plan, a)
        missing = [t for t in reference.shape() if t not in plan.shape()]
        if missing:
            plan.notes.append("Differs from the reference plan: leaves out " + ", ".join(sorted(set(missing))))
        return plan
    except PlanInvalid as e:
        reference.notes.append(f"Model plan rejected ({e}); the deterministic planner ran.")
        return reference


def plan(goal: str, agent: AgentDef | str, context: dict[str, Any] | None = None, *, planner: str = "auto",
         provider: Any = None, budget: Any = None, probe: Any = None) -> Plan:
    """`planner`: auto (model when a key is present, else deterministic) | model | deterministic."""
    if planner == "deterministic":
        return deterministic(goal, agent, context)
    return model(goal, agent, context, provider=provider, budget=budget, probe=probe)
