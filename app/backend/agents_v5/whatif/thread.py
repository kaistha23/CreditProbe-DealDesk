"""The agent's results in the What-If thread, as the existing result cards (W3).

One turn is appended to the thread the goal came from (`context.thread_id`) through the What-If chat store's own
`append_turn`; the blocks are the types the What-If thread already renders: text, table, result, likelihood and
commentary. The thread's scenario state is not changed: the user's own scenario, Save, Word and Excel stay as they
were (N1). Without a thread, nothing is posted and the run is read in the drawer.
"""
from __future__ import annotations

from typing import Any

from backend.agents_v5.runtime.types import Run
from backend.agents_v5.whatif import note

COLUMNS = [("row", "Scenario or action"), ("kind", "Kind"), ("ecl_after", "ECL after (SAR m)"),
           ("ecl_change", "ECL change (SAR m)"), ("ecl_change_pct", "ECL change %"),
           ("coverage_after_pct", "Coverage after %"), ("stage2_after", "Stage 2 after"),
           ("cet1_after_pct", "CET1 after %"), ("capital_impact", "Capital needed (SAR m)"),
           ("likelihood", "Likelihood")]


def blocks(run: Run, ix: dict[str, Any], text: str, output: dict[str, Any]) -> list[dict[str, Any]]:
    B: list[dict[str, Any]] = []
    n = len(run.plan.steps) if run.plan else 0
    B.append({"type": "text", "markdown": f"**Scenario agent.** {output['headline']}\n\n"
                                          f"The agent planned and ran {n} steps; the full plan, each step's inputs and "
                                          "outputs and the proposals are in the agent drawer."})
    rows = output.get("comparison") or []
    if rows:
        cols = [{"key": k, "label": lab} for k, lab in COLUMNS]
        B.append({"type": "table", "title": "Scenarios and management actions", "artifact_id": f"{run.run_id}-compare",
                  "columns": cols, "rows": [{k: r.get(k, "") for k, _ in COLUMNS} for r in rows], "row_count": len(rows)})
    order = [sc["key"] for sc in ix["design"][1]["scenarios"]] if ix["design"] else []
    for key in order:
        hit = ix["runs"].get(f"{key}:delta")
        if not hit:
            continue
        s, r = hit
        basis = "; ".join(b["basis"] for b in r["basis"] if b.get("basis"))
        B.append({"type": "text", "markdown": f"**{r['name']}.** {r['sentence']}.\n\n*Basis:* {basis}."})
        B.append({"type": "result", "result": r["result"]})
        B.append({"type": "likelihood", **r["likelihood"]})
    if ix["actions"]:
        acols = [{"key": "action", "label": "Management action (on the severe scenario)"},
                 {"key": "ecl_effect", "label": "ECL effect (SAR m)"}, {"key": "capital_effect", "label": "Capital effect (SAR m)"},
                 {"key": "cet1_effect_pp", "label": "CET1 effect (pp)"}, {"key": "ead_effect", "label": "EAD effect (SAR m)"}]
        arows = [{"action": a["definition"]["what"] if a["action"] != "package" else "All four actions together",
                  **{k: a["effects"][k] for k in ("ecl_effect", "capital_effect", "cet1_effect_pp", "ead_effect")}}
                 for _, (s, a) in ix["actions"].items()]
        B.append({"type": "table", "title": "Management actions", "artifact_id": f"{run.run_id}-actions",
                  "columns": acols, "rows": arows, "row_count": len(arows)})
    B.append({"type": "commentary", "source": "deterministic", "text": text})
    return B


def post(run: Run, ix: dict[str, Any], text: str, output: dict[str, Any]) -> dict[str, Any]:
    tid = str(run.context.get("thread_id") or "")
    if not tid and run.trigger not in ("scheduled", "event"):
        return {"posted": False, "reason": "no What-If thread in the context"}
    try:
        from backend.whatif_v5.chat.store import Store
        st = Store()
        if not tid:
            # A scheduled run lands where people look: its own What-If thread (A6), named after the goal.
            b = ix["book"][1] if ix["book"] else {}
            t = st.create_thread(owner=str(run.context.get("owner") or ""), team="", domain=str(b.get("domain") or
                                 run.context.get("domain") or "corporate"), period=str(b.get("period") or ""),
                                 title=f"Scenario agent: {run.goal}"[:90], origin="agent")
            tid = t["thread_id"]
            run.context["thread_id"] = tid
        t = st.thread(tid)
        if t is None:
            return {"posted": False, "reason": f"{tid} is not a What-If thread"}
        if run.user and t.get("owner") and t["owner"] != run.user:
            return {"posted": False, "reason": "only the thread's owner can post into it"}
        ans = {"blocks": blocks(run, ix, text, output), "suggestions": [], "question_display": f"Run as agent: {run.goal}",
               "state": {}, "agent_run": {"run_id": run.run_id, "agent": run.agent}, "tools": [
                   {"tool": s.tool, "ms": s.duration_ms} for s in (run.plan.steps if run.plan else [])]}
        n = st.append_turn(tid, run.run_id, f"Run as agent: {run.goal}", ans)
        return {"posted": True, "thread_id": tid, "turn": n}
    except Exception as e:  # noqa: BLE001 - the run's result stands in the drawer even if the thread write fails
        return {"posted": False, "reason": f"{type(e).__name__}: {str(e)[:200]}"}


_ = note
__all__ = ["blocks", "post"]
