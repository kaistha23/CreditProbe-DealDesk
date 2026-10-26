"""The executor (A1, A3, A4, A5): runs a plan's steps through the tools, adapts, concludes.

- Each step: budget check (steps, clock, rows) -> availability (an unavailable tool is
  SKIPPED with "not available on this build") -> the tool -> output summary, figures,
  duration, the engine's trace id. A proposal-only tool's change goes to the approvals queue.
- After each step the agent's `adapt` may add steps (recorded with the rule that added them).
- The run is saved after every step, so the drawer ticks steps off live.
- On budget exhaustion the run stops with partial findings and says so (PARTIAL).
- `conclude` gives findings, narrative, output and proposals; the narrative passes the
  citation check (uncited figures are removed and reported).
"""
from __future__ import annotations

import dataclasses

import json
import threading
import time
import traceback
from typing import Any

from backend.agents_v5.runtime import approvals, citations, notify, planner, store
from backend.agents_v5.runtime import tools as T
from backend.agents_v5.runtime.agents import AgentDef, get_agent
from backend.agents_v5.runtime.budget import ROWS, TASKS, Exhausted, for_agent
from backend.agents_v5.runtime.types import (
    COMPLETED,
    DONE,
    FAILED,
    PARTIAL,
    PENDING,
    QUEUED,
    R_FAILED,
    R_RUNNING,
    RUNNING,
    SKIPPED,
    Plan,
    Run,
    Step,
    new_id,
    now_iso,
)

MAX_OUTPUT_CHARS = 400_000


def _compact(data: Any) -> Any:
    try:
        s = json.dumps(data, default=str)
    except (TypeError, ValueError):
        return {"note": "output not serialisable"}
    if len(s) <= MAX_OUTPUT_CHARS:
        return json.loads(s)
    return {"note": f"output of {len(s):,} characters stored in summary form", "keys": list(data)[:40]
            if isinstance(data, dict) else []}


class Execution:
    """One run in progress."""

    def __init__(self, agent: AgentDef, run: Run):
        self.agent, self.run = agent, run
        self.budget = for_agent(agent.spec)
        self.ctx = T.ToolContext(run_id=run.run_id, agent=agent.agent_id, user=run.user, context=run.context)

    # ---- one step
    def run_step(self, plan: Plan, s: Step) -> None:
        tool = T.get_tool(s.tool)
        if tool is None:
            s.status, s.summary = SKIPPED, "No such tool on this build"
            return
        ok, why = tool.is_available()
        if not ok:
            s.status, s.summary = SKIPPED, why[:1].upper() + why[1:]
            return
        self.budget.check_clock(completed=self._completed(), remaining=self._remaining(plan))
        self.budget.spend(TASKS, completed=self._completed(), remaining=self._remaining(plan))
        s.status = RUNNING
        self._save()
        t0 = time.monotonic()
        try:
            res = tool.fn(dict(s.inputs), self.ctx)
            if not isinstance(res, T.ToolResult):
                raise TypeError(f"{tool.name} returned {type(res).__name__}, not a ToolResult.")
            s.summary, s.figures, s.trace_id = res.summary, dict(res.figures or {}), res.trace_id or ""
            s.output = _compact(res.data)
            self.ctx.results[tool.name] = res.data
            s.status = DONE
            if res.rows_scanned:
                self.budget.spend(ROWS, int(res.rows_scanned), completed=self._completed(),
                                  remaining=self._remaining(plan))
            if res.proposal is not None:
                if tool.read_only:
                    raise PermissionError(f"{tool.name} is read-only and cannot propose a change.")
                self._propose(res.proposal, [s.id])
        except T.ToolUnavailable as e:
            why = str(e) or T.NOT_AVAILABLE
            s.status, s.summary = SKIPPED, why[:1].upper() + why[1:]
        except Exhausted:
            raise
        except Exception as e:  # noqa: BLE001 - a failed step is recorded; the run goes on
            s.status, s.error = FAILED, f"{type(e).__name__}: {str(e)[:300]}"
            s.summary = s.summary or f"{tool.name} failed"
        finally:
            s.duration_ms = int((time.monotonic() - t0) * 1000)

    def _propose(self, p: dict[str, Any], evidence: list[str]) -> None:
        row = approvals.propose(p.get("change") or {}, p.get("approver_role") or "CREDIT_OFFICER",
                                kind=p.get("kind", ""), title=p.get("title", ""), reason=p.get("reason", ""),
                                evidence=list(p.get("evidence") or evidence), agent=self.agent.agent_id,
                                run_id=self.run.run_id, maker=self.run.user or f"agent:{self.agent.agent_id}",
                                scope=self.run.scope, expires_hours=int(p.get("expires_hours", 72)),
                                risk=p.get("risk", "medium"))
        self.run.proposals.append(row["id"])

    def _completed(self) -> str:
        p = self.run.plan
        return ", ".join(s.tool for s in p.steps if s.status == DONE) if p else ""

    def _remaining(self, plan: Plan) -> str:
        return ", ".join(s.tool for s in plan.steps if s.status == PENDING)

    def _save(self) -> None:
        self.run.budget = self.budget.to_dict()
        store.save_run(self.run)

    # ---- the plan
    def _loop(self, plan: Plan, only: set[str] | None = None) -> None:
        run, a = self.run, self.agent
        i = 0
        while i < len(plan.steps):
            s = plan.steps[i]
            i += 1
            if s.status != PENDING:
                continue
            if only is not None and s.tool not in only:
                s.status, s.summary = SKIPPED, "Left out so the run could finish its decision, proposals and summary"
                continue
            self.run_step(plan, s)
            if s.status == DONE and a.adapt is not None:
                have = {(x.tool, json.dumps(x.inputs, sort_keys=True, default=str)) for x in plan.steps}
                for ad in a.adapt(run, s) or []:
                    key = (ad.tool, json.dumps(ad.inputs, sort_keys=True, default=str))
                    if key in have or not a.spec.may_use(ad.tool):
                        continue
                    plan.add(ad.tool, ad.inputs, why=ad.why, added_by=ad.rule or "adapt")
                    have.add(key)
            self._save()

    def _close(self, plan: Plan, e: Exhausted) -> bool:
        """R15 L5: the step budget ran out before the run closed. Skip the remaining evidence steps, add any closing
        tool the plan lacks, and run only the closing tools within the agent's reserve. False = not applicable."""
        a = self.agent
        if e.meter != TASKS or a.closing_reserve <= 0 or not a.closing_tools:
            return False
        closing = set(a.closing_tools)
        req = set(a.required_tools(plan.goal_type, plan.context) if a.required_tools else []) & closing
        have = set(plan.shape())
        for name in [t for t in a.closing_tools if t in req and t not in have]:
            if T.get_tool(name) is not None:
                plan.add(name, {}, why="required to close the run", added_by="closing:required")
        lim = self.budget.limits
        self.budget.limits = dataclasses.replace(lim, tasks=int(lim.tasks) + int(a.closing_reserve),
                                                 scans=int(lim.scans) + int(a.closing_reserve))
        self.budget.exhausted = None
        plan.notes.append(f"The step budget ({lim.tasks}) ran out before the decision; the remaining evidence steps "
                          f"were left out and the run closed with its decision, proposals and summary.")
        self._loop(plan, only=closing)
        return True

    def execute(self, plan: Plan) -> Run:
        run, a = self.run, self.agent
        run.plan, run.status = plan, R_RUNNING
        t0 = time.monotonic()
        self._save()
        try:
            try:
                self._loop(plan)
            except Exhausted as e:
                if not self._close(plan, e):
                    raise
            run.status = COMPLETED
        except Exhausted as e:
            run.status, run.stopped = PARTIAL, e.sentence()
            for s in plan.steps:
                if s.status in (PENDING, RUNNING):
                    s.status, s.summary = SKIPPED, f"not run: the {e.meter.replace('_', ' ')} budget ran out"
        try:
            c = a.conclude(run)
            figs = {s.id: s.figures for s in plan.steps if s.status == DONE}
            narrative, chk = citations.enforce(c.narrative, figs)
            run.findings, run.narrative, run.output, run.citation_check = c.findings, narrative, c.output, chk
            if run.stopped:
                run.narrative = (run.narrative + "\n\n" + run.stopped).strip()
            for ps in c.proposals:
                self._propose({"change": ps.change, "approver_role": ps.approver_role, "kind": ps.kind,
                               "title": ps.title, "reason": ps.reason, "evidence": ps.evidence,
                               "expires_hours": ps.expires_hours, "risk": ps.risk}, ps.evidence)
        except Exception as e:  # noqa: BLE001
            run.status = R_FAILED
            run.stopped = f"The agent could not conclude: {type(e).__name__}: {str(e)[:300]}"
            run.output = {**(run.output or {}), "error_trace": traceback.format_exc()[-1500:]}
        run.finished_at = now_iso()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        if isinstance(run.output, dict):
            run.output.setdefault("timing", {})["run_ms"] = run.duration_ms
            run.output["timing"]["steps"] = [{"id": s.id, "tool": s.tool, "ms": s.duration_ms} for s in plan.steps]
        self._save()
        if run.trigger == "scheduled":
            href = a.href(run) if a.href else f"/trace/agent/{run.run_id}"
            notify.send(f"{a.spec.business_name}: {run.output.get('headline') or run.status}",
                        (run.narrative or "")[:400], href, users=a.notify_users or None)
        return run


def new_run(agent: AgentDef | str, goal: str, context: dict[str, Any] | None = None, *, trigger: str = "on_demand",
            user: str = "") -> tuple[AgentDef, Run]:
    a = get_agent(agent) if isinstance(agent, str) else agent
    if a is None:
        raise KeyError(f"No agent {agent!r}.")
    ctx = dict(context or {})
    run = Run(run_id=new_id("agr"), agent=a.agent_id, goal=goal, context=ctx, trigger=trigger, user=user,
              scope=a.scope_of(ctx))
    store.save_run(run)
    return a, run


def execute(plan: Plan, run: Run | None = None, *, user: str = "", trigger: str = "on_demand") -> Run:
    """Run a plan (the contract's `execute(plan)`)."""
    if run is None:
        a, run = new_run(plan.agent, plan.goal, plan.context, trigger=trigger, user=user)
    else:
        a = get_agent(run.agent)
    return Execution(a, run).execute(plan)


def start(agent: AgentDef | str, goal: str, context: dict[str, Any] | None = None, *, planner_mode: str = "auto",
          trigger: str = "on_demand", user: str = "", provider: Any = None, background: bool = False) -> Run:
    """Plan and execute. With `background`, returns the queued run at once (the drawer polls)."""
    a, run = new_run(agent, goal, context, trigger=trigger, user=user)

    def _go() -> Run:
        ex = Execution(a, run)
        try:
            def probe(pl: Plan, st: Step) -> None:   # R15 L4: look-ahead steps show on the run while it plans
                run.plan = pl
                ex.run_step(pl, st)

            p = planner.plan(goal, a, run.context, planner=planner_mode, provider=provider, budget=ex.budget,
                             probe=probe)
        except Exception as e:  # noqa: BLE001
            run.status, run.stopped, run.finished_at = R_FAILED, f"Planning failed: {e}", now_iso()
            store.save_run(run)
            return run
        run.model = next((n.split(":", 1)[1] for n in p.notes if n.startswith("model:")), "")
        run.context = ex.ctx.context = {**run.context, **p.context}   # e.g. the proposal id read from the goal
        run.scope = a.scope_of(run.context)
        return ex.execute(p)

    if background:
        run.status = QUEUED
        store.save_run(run)
        threading.Thread(target=_go, name=f"agent-{run.run_id}", daemon=True).start()
        return run
    return _go()


__all__ = ["Execution", "execute", "new_run", "start", "FAILED", "DONE", "SKIPPED"]
