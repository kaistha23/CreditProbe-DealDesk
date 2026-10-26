"""The Lenses monitoring agent `lenses.monitoring` on the agents_v5 runtime (PLAN_R11_AGENTS K1-K4, A1-A7).

Registered on import of the package: its tools, the agent definition (job description and budgets from
`backend.agentic.registry.Agent`, classify, deterministic plans, adapt, conclude) and the approval appliers.

  conclude(run)          findings with evidence (step ids), the narrative with every figure cited [S#], the output
                         (the proposed set, or the alerts with their explanations)
  record_and_notify      the run's alerts onto the panel (monitoring store) and the notifications bell (runtime notify)
  appliers               approving a monitoring set creates or updates the lens and its schedule; approving changes
                         retires or re-thresholds metrics and refreshes the lens
  edit_metric / decide   the panel's accept / edit / reject per metric and its approve / reject (through the runtime's
                         approvals, maker-checker and expiry included)
  panel(scope)           proposed / active / alerts for the Lenses panel
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.agentic.registry import Agent
from backend.agents_v5.lenses import monitor as MON
from backend.agents_v5.lenses import mstore, plans
from backend.agents_v5.lenses import tools as T
from backend.agents_v5.runtime import (
    AgentDef,
    Conclusion,
    Finding,
    Run,
    ToolContext,
    get_agent,
    register_agent,
    register_applier,
    register_tool,
)
from backend.agents_v5.runtime import approvals as RA
from backend.lenses_v5 import fmt

AGENT_ID = "lenses.monitoring"
#: identity roles (backend.identity_v5 seed directory) -> runtime approval ranks
AGENT_ROLE = {"Administrator": "ADMIN", "Head of Risk": "CRO", "Head of Credit": "CCO", "Risk Manager": "RISK_MANAGER",
              "Corporate Credit Manager": "CREDIT_OFFICER", "Retail Credit Manager": "CREDIT_OFFICER", "Relationship Manager": "RM",
              "Credit Analyst (corporate)": "ANALYST", "Credit Analyst (retail)": "ANALYST", "Model Validation Analyst": "ANALYST",
              "Internal Auditor": "VIEWER"}
#: who may approve a monitoring set (the risk side; the runtime's rank check alone would also admit credit officers)
APPROVER_ROLES = ("ADMIN", "CRO", "CCO", "RISK_MANAGER")
NOTIFY_USERS = ("faisal.alqahtani", "abdullah.alzahrani")
_APPROVER = threading.local()


def agent_role(user: dict[str, Any]) -> str:
    if user.get("agent_role"):
        return RA.norm_role(user["agent_role"])
    if user.get("is_admin"):
        return "ADMIN"
    role = str(user.get("role") or "")
    if not role and user.get("username"):
        try:
            from backend.identity_v5.directory import seed_users
            role = next((u.get("role", "") for u in seed_users() if u["username"] == user["username"]), "")
        except Exception:  # noqa: BLE001
            role = ""
    return AGENT_ROLE.get(role, RA.norm_role(role) or "VIEWER")


def spec() -> Agent:
    return Agent(
        agent_id=AGENT_ID, business_name="Monitoring agent",
        purpose=("Plan what is worth monitoring on a book, segment, sector or lens from its composition, the risk appetite, the "
                 "CBUAE CRM regulation, recent movement and materiality, with thresholds back-tested over 8 quarters; once a risk "
                 "approver accepts the set, run it on a schedule: detect material moves, investigate them, explain them with "
                 "evidence and notify; propose retiring or re-thresholding metrics that never fire or fire constantly."),
        when_to_use=("set up monitoring for a book, segment, sector or lens", "the scheduled monitoring run", "review a monitoring set"),
        when_not_to_use=("building a lens by hand (the lens assistant)", "changing a limit or the risk appetite"),
        allowed_capabilities=("read", "propose"), allowed_tools=tuple(t.name for t in T.TOOLS),
        allowed_data_domains=("lenses", "early_warning", "whatif", "regulatory", "risk_appetite"),
        maximum_steps=64, timeout_seconds=240, max_model_calls=4, max_rows_scanned=2_000_000, autonomy_level=1,
        human_approval_requirements=(T.KIND_SET, T.KIND_CHANGES),
        escalation_rules=("alerts to the set's owner and approver", "high-severity alerts also to the risk team on scheduled runs"),
        owner="Credit Risk")


def scope_of(ctx: dict[str, Any]) -> str:
    sc = ctx.get("scope") or {}
    return str(sc.get("scope_key") or "")


def href(run: Run) -> str:
    sc = run.context.get("scope") or {}
    out = run.output or {}
    lid = out.get("lens_id") or sc.get("lens_id")
    return f"/lenses/{lid}?monitor=alerts" if lid else "/lenses?monitor=1"


SYSTEM = ("You plan for the Lenses Monitoring agent of a corporate bank in the UAE. To set up monitoring, read the five sources "
          "(composition, risk appetite, regulation, movement, materiality), build candidates, back-test, rank and propose. To run "
          "monitoring, load the approved set, compute and detect; the runtime adds the investigations. Never state a figure; "
          "changes to a lens or a schedule are proposals only.")


# ------------------------------------------------------------------ conclusion
def _sid(run: Run, tool: str) -> str:
    s = run.done(tool)
    return s.id if s else ""


def _steps_for(run: Run, key: str) -> dict[str, Any]:
    """The investigation steps of one alert: {segment, rating, borrower, driver, ews, whatif} -> step."""
    out: dict[str, Any] = {}
    for s in run.plan.steps if run.plan else []:
        if s.status != "done" or (s.inputs or {}).get("alert") != key:
            continue
        name = {"lenses_decompose": (s.inputs or {}).get("by", "segment"), "lenses_driver": "driver", "lenses_ews_read": "ews",
                "lenses_whatif_read": "whatif"}.get(s.tool)
        if name:
            out[name] = s
    return out


def explanations(run: Run) -> list[dict[str, Any]]:
    det = run.done("lenses_detect")
    comp = run.done("lenses_compute")
    if not det or not comp:
        return []
    alerts = {a["key"]: a for a in (det.output or {}).get("alerts", [])}
    out = []
    for k in (det.output or {}).get("investigate", []):
        a = alerts.get(k)
        st = _steps_for(run, k)
        if a is None or not st:
            continue
        ids = {"compute": comp.id, **{n: s.id for n, s in st.items()}}
        get = {n: (st[n].output or {}) if n in st else {} for n in ("segment", "rating", "borrower", "driver", "ews", "whatif")}
        e = MON.explain(a, get["segment"], get["rating"], get["borrower"], get["driver"], get["ews"], get["whatif"],
                        {n: ids.get(n, comp.id) for n in ("compute", "segment", "rating", "borrower", "driver", "ews", "whatif")})
        e["alert"] = {x: a[x] for x in ("key", "label", "period", "value", "display", "severity", "status", "threshold_text")}
        e["evidence"] = [ids[n] for n in ("compute", "segment", "rating", "borrower", "driver", "ews", "whatif") if n in ids]
        e["decomposition"] = {"segment": get["segment"].get("rows", [])[:5], "rating": get["rating"].get("rows", [])[:5],
                              "borrower": get["borrower"].get("rows", [])[:5],
                              "driver": {x: get["driver"].get(x) for x in ("numerator_part", "denominator_part", "main")} if get["driver"].get("available") else None,
                              "ews": get["ews"].get("names", [])[:5],
                              "whatif": {x: get["whatif"].get(x) for x in ("segment", "ecl", "uplift")} if get["whatif"].get("available") else None,
                              "unit": get["segment"].get("unit_of_contribution", a["unit"])}
        out.append(e)
    return out


SEV = {"high": "major", "alert": "minor"}


def conclude(run: Run) -> Conclusion:
    gt = run.plan.goal_type if run.plan else "setup"
    sc = run.context.get("scope") or {}
    if gt == "setup":
        return _conclude_setup(run, sc)
    if gt == "run":
        return _conclude_run(run, sc)
    return _conclude_review(run, sc)


def _conclude_setup(run: Run, sc: dict[str, Any]) -> Conclusion:
    rk, bt, pr = run.done("lenses_rank"), run.done("lenses_backtest"), run.done("lenses_propose_set")
    data = (rk.output if rk else None) or {}
    s, dropped = data.get("set") or [], data.get("dropped") or []
    findings, lines = [], []
    if s:
        lines.append(f"For {sc.get('lens_name') or sc.get('label', 'the scope')} the agent proposes {len(s)} metrics to monitor, ranked by value [{rk.id}].")
        for m in s[:3]:
            lines.append(f"#{m['rank']} {m['label']}: {m['why'].rstrip('.')} [{rk.id}]. {m['threshold_text']}; back-test {m['backtest']['fired']} of "
                         f"{m['backtest']['quarters']} quarters [{rk.id}].")
        red = [d for d in dropped if d["reason"] in ("same_signal", "correlated")]
        if red:
            lines.append(f"{len(red)} candidates were dropped as redundant, for example {red[0]['label']}: "
                         f"{red[0]['why'][:1].lower()}{red[0]['why'][1:].rstrip('.')} [{rk.id}].")
        if pr and (pr.output or {}).get("proposal_id"):
            lines.append("Nothing changes until a risk approver accepts the set; approval creates the monitoring lens and its schedule.")
        for m in s:
            sev = "major" if (m.get("appetite") and m["now"] is not None and m["threshold"].get("limit") and m["now"] >= m["threshold"]["limit"]) else "info"
            findings.append(Finding(title=f"#{m['rank']} {m['label']}", severity=sev, kind="proposed_metric",
                                    detail=f"{m['why']} {m['threshold_text']}; back-test {m['backtest']['label']}.",
                                    evidence=[x for x in (rk.id, bt.id if bt else "") if x], data={"key": m["key"], "value": m["value"]}))
        for d in dropped:
            if d["reason"] in ("same_signal", "correlated"):
                findings.append(Finding(title=f"Dropped: {d['label']}", severity="info", kind="dropped_metric", detail=d["why"], evidence=[rk.id],
                                        data={"key": d["key"], "reason": d["reason"]}))
    else:
        lines.append("No metric could be planned for this scope.")
    pid = ((pr.output if pr else None) or {}).get("proposal_id")
    out = {"kind": "setup", "scope": {k: sc.get(k) for k in ("book", "filters", "scope_key", "label", "lens_id", "lens_name", "period")},
           "set": s, "dropped": dropped, "skipped_appetite": ((run.done("lenses_risk_appetite").output or {}).get("skipped", [])
                                                            if run.done("lenses_risk_appetite") else []),
           "proposal_id": pid, "approval_ids": list(run.proposals),
           "headline": f"{len(s)} metrics proposed for {sc.get('lens_name') or sc.get('label', 'the scope')}" if s else "No monitoring set proposed"}
    return Conclusion(findings=findings, narrative="\n\n".join(lines), output=out)


def _conclude_run(run: Run, sc: dict[str, Any]) -> Conclusion:
    ls, det = run.done("lenses_load_set"), run.done("lenses_detect")
    setd = ((ls.output if ls else None) or {}).get("set")
    lines, findings = [], []
    ex = explanations(run)
    alerts = ((det.output if det else None) or {}).get("alerts", [])
    if not setd:
        lines.append("There is no approved monitoring set for this scope yet; set one up first.")
    else:
        n = len(((run.done("lenses_compute").output or {}).get("computed", [])) if run.done("lenses_compute") else [])
        lines.append(f"{len(alerts)} of {n} monitored metrics are past their threshold [{det.id}]." if det else "Detection did not run.")
        for e in ex:
            lines.append(" ".join(e["lines"]))
            findings.append(Finding(title=e["headline"], severity=SEV.get(e["severity"], "minor"), kind="alert", detail=" ".join(e["lines"]),
                                    evidence=e["evidence"], data={"key": e["alert"]["key"], "status": e["alert"]["status"]}))
        for a in alerts:
            if a["key"] not in {e["alert"]["key"] for e in ex}:
                findings.append(Finding(title=f"{a['label']}: {a['display']}", severity=SEV.get(a["severity"], "minor"), kind="alert",
                                        detail=f"{a['threshold_text']} ({a['status']}).", evidence=[det.id], data={"key": a["key"], "status": a["status"]}))
        over = (det.output or {}).get("not_investigated", []) if det else []
        if over:
            lines.append(f"{len(over)} further alerts were listed but not investigated (the per-run budget) [{det.id}].")
    rv = run.done("lenses_review")
    ch = ((rv.output if rv else None) or {}).get("changes", [])
    if ch:
        lines.append(f"The set review proposes {len(ch)} changes (retire or re-threshold) with their evidence [{rv.id}].")
    fresh = [a for a in alerts if a["status"] in ("new", "worsened")]
    headline = (f"{len(fresh)} new alert{'s' if len(fresh) != 1 else ''} on {setd['label']}: {fresh[0]['label']} {fresh[0]['display']}" if fresh and setd
                else f"No new alerts on {setd['label']}" if setd else "No approved monitoring set")
    out = {"kind": "run", "scope": {k: sc.get(k) for k in ("book", "filters", "scope_key", "label", "lens_id", "period")},
           "set_id": (setd or {}).get("set_id"), "lens_id": (setd or {}).get("lens_id"),
           "alerts": [{k: a[k] for k in ("key", "label", "period", "display", "severity", "status", "threshold_text")} for a in alerts],
           "explanations": ex, "not_investigated": ((det.output or {}).get("not_investigated", []) if det else []), "changes": ch,
           "approval_ids": list(run.proposals), "headline": headline}
    return Conclusion(findings=findings, narrative="\n\n".join(lines), output=out)


def _conclude_review(run: Run, sc: dict[str, Any]) -> Conclusion:
    rv = run.done("lenses_review")
    ch = ((rv.output if rv else None) or {}).get("changes", [])
    lines = [f"{len(ch)} changes proposed to the set [{rv.id}]." if ch else "Every metric in the set still fires at a useful rate."] if rv else \
        ["There is no approved monitoring set for this scope yet."]
    findings = [Finding(title=f"{c['action'].capitalize()}: {c['label']}", severity="minor", kind="set_change", detail=c["why"], evidence=[rv.id],
                        data={"key": c["key"], "action": c["action"]}) for c in ch] if rv else []
    return Conclusion(findings=findings, narrative="\n\n".join(lines),
                      output={"kind": "review", "scope": {k: sc.get(k) for k in ("book", "filters", "scope_key", "label", "lens_id")}, "changes": ch,
                              "approval_ids": list(run.proposals), "headline": f"{len(ch)} changes proposed" if ch else "No changes"})


# ------------------------------------------------------------------ alerts onto the panel and the bell
def record_and_notify(ctx: ToolContext) -> dict[str, Any]:
    from backend.agents_v5.runtime import notify, store
    run = store.load_run(ctx.run_id)
    if run is None:
        return {"recorded": 0, "fresh": 0, "notified": 0, "summary": "The run is not stored yet."}
    det = run.done("lenses_detect")
    ls = run.done("lenses_load_set")
    s = ((ls.output if ls else None) or {}).get("set") or {}
    if not det or not s:
        return {"recorded": 0, "fresh": 0, "notified": 0, "summary": "No alerts to record."}
    ex = {e["alert"]["key"]: e for e in explanations(run)}
    st = mstore.get()
    st.delete_run_alerts(run.run_id)          # idempotent within a run
    recorded, fresh = 0, []
    for a in (det.output or {}).get("alerts", []):
        if a["status"] == "repeat":
            continue
        e = ex.get(a["key"])
        st.add_alert(set_id=s["set_id"], run_id=run.run_id, metric_key=a["key"], label=a["label"], period=a["period"], severity=a["severity"],
                     status=a["status"], value=a["value"], display=a["display"], headline=e["headline"] if e else f"{a['label']}: {a['display']}",
                     explanation=e["lines"] if e else [f"{a['label']} is {a['display']} in {MON.period_label(a['period'])}: {a['threshold_text'].lower()}."],
                     detail={"evidence": e.get("evidence") if e else [det.id], "decomposition": e.get("decomposition") if e else None,
                             "threshold_text": a["threshold_text"], "run_id": run.run_id})
        recorded += 1
        if a["status"] in ("new", "worsened"):
            fresh.append(a)
    sent = 0
    if fresh and not st.notified(run.run_id):
        who = [u for u in (s.get("created_by"), s.get("approved_by")) if u and not u.startswith("agent:")]
        if run.trigger == "scheduled":
            who = [u for u in who if u not in NOTIFY_USERS]      # the runtime notifies the risk team at the end of a scheduled run
        high = sum(1 for a in fresh if a["severity"] == "high")
        title = (f"Monitoring agent: {len(fresh)} new alert{'s' if len(fresh) != 1 else ''} on {s.get('label', 'a monitoring set')}"
                 + (f" ({high} high)" if high else ""))
        first = ex.get(fresh[0]["key"])
        body = " ".join(first["lines"]) if first else f"{fresh[0]['label']} {fresh[0]['display']}"
        lid = s.get("lens_id")
        if who:
            sent = notify.send(title, body, f"/lenses/{lid}?monitor=alerts" if lid else "/lenses?monitor=1", users=who)
        st.mark_notified(run.run_id)
    return {"recorded": recorded, "fresh": len(fresh), "notified": sent,
            "summary": f"Recorded {recorded} alerts ({len(fresh)} new or worse) on the panel" + (f"; notified {sent} people." if sent else ".")
            if recorded else "No alerts to record."}


# ------------------------------------------------------------------ approvals: appliers, the panel's edit and decision
def _approver() -> str:
    return getattr(_APPROVER, "user", "") or "approvals queue"


def apply_set(change: dict[str, Any]) -> dict[str, Any]:
    """Applier for `lenses.monitoring_set`: the lens (create or new version) and the schedule. Called by the runtime
    only after a person with the approver role approves."""
    from backend.agents_v5.lenses import apply as AP
    from backend.agents_v5.runtime import schedules
    from backend.lenses_v5.store import Store
    st = mstore.get()
    p = st.proposal(change["proposal_id"])
    if p is None:
        raise KeyError(change["proposal_id"])
    pay, sc = p["payload"], p["payload"]["scope"]
    ms = [dict(m, status="active") for m in pay["metrics"] if m.get("status") != "rejected"]
    if not ms:
        raise ValueError("Every metric was rejected: nothing to monitor.")
    owner = p["requested_by"] or _approver()
    lens = AP.apply_set(store=Store(), scope_key=sc["scope_key"], book=sc["book"], filters=sc["filters"], label=pay["label"], metrics=ms,
                        owner=owner, team="", approver=_approver())
    prev = st.active_set(sc["scope_key"])
    if prev and (prev.get("schedule") or {}).get("id"):
        schedules.remove(prev["schedule"]["id"])
    cron = AP.CRON[sc["book"]]
    ctx = {"lens_id": sc.get("lens_id") or "", "goal_type": "run"} if sc.get("lens_id") else {"book": sc["book"], "filters": sc["filters"], "goal_type": "run"}
    row = schedules.schedule(AGENT_ID, cron, f"Run monitoring for {sc.get('lens_name') or sc['label']}", ctx, planner="deterministic", user=owner)
    sched = {"id": row["id"], "cron": cron, "text": T.schedule_text(sc["book"]), "goal": row["goal"]}
    s = st.save_set(scope_key=sc["scope_key"], book=sc["book"], filters=sc["filters"], label=pay["label"], metrics=ms, lens_id=lens["lens_id"],
                    schedule=sched, created_by=owner, approved_by=_approver())
    st.update_proposal(p["proposal_id"], status="approved", decided_by=_approver(), decided_at=time.time())
    return {"set_id": s["set_id"], "version": s["version"], "lens": lens, "schedule": sched}


def apply_changes(change: dict[str, Any]) -> dict[str, Any]:
    """Applier for `lenses.monitoring_changes`: retire or re-threshold, a new set version and a new lens version."""
    from backend.agents_v5.lenses import apply as AP
    from backend.lenses_v5.store import Store
    st = mstore.get()
    p = st.proposal(change["proposal_id"])
    if p is None:
        raise KeyError(change["proposal_id"])
    pay, sc = p["payload"], p["payload"]["scope"]
    cur = st.get_set(pay["set_id"])
    if cur is None or cur["status"] != "active":
        raise ValueError("The set this proposal changes is no longer active.")
    ms, done = [dict(m) for m in cur["metrics"]], []
    for c in pay["changes"]:
        if c.get("status") == "rejected":
            continue
        for m in ms:
            if m["key"] != c["key"]:
                continue
            if c["action"] == "retire":
                m["status"], m["retired"] = "rejected", True
            else:
                m["threshold"], m["threshold_text"] = c["to"], c["to_text"]
                m["backtest"] = c["evidence"].get("new_backtest", m.get("backtest"))
            done.append(f"{c['action']} {m['label']}")
    keep = [m for m in ms if m.get("status") != "rejected"]
    lens = AP.apply_set(store=Store(), scope_key=sc["scope_key"], book=sc["book"], filters=sc["filters"], label=cur["label"], metrics=keep,
                        owner=cur["created_by"], team="", approver=_approver())
    s = st.save_set(scope_key=sc["scope_key"], book=sc["book"], filters=sc["filters"], label=cur["label"], metrics=ms, lens_id=lens["lens_id"],
                    schedule=cur["schedule"], created_by=cur["created_by"], approved_by=_approver())
    st.update_proposal(p["proposal_id"], status="approved", decided_by=_approver(), decided_at=time.time())
    return {"set_id": s["set_id"], "version": s["version"], "lens": lens, "changes": done}


class NotAllowed(PermissionError):
    pass


def approval_for(proposal_id: str) -> dict[str, Any] | None:
    for row in RA.listing(agent=AGENT_ID):
        if (row.get("change") or {}).get("proposal_id") == proposal_id:
            return row
    return None


def _status(p: dict[str, Any]) -> dict[str, Any]:
    """A panel proposal with its approval's state (the runtime's approvals are the record of the decision)."""
    a = approval_for(p["proposal_id"])
    out = {k: p[k] for k in ("proposal_id", "kind", "scope_key", "requested_by", "created_at", "run_id", "set_id")} | {"payload": p["payload"]}
    if a:
        out.update({"approval_id": a["id"], "status": a["status"], "approver_role": a["approver_role"], "expires_at": a["expires_at"],
                    "decided_by": a["decided_by"], "decided_at": a["decided_at"], "maker": a["maker"], "note": a.get("note", ""),
                    "applied": a.get("applied")})
    else:
        out.update({"approval_id": None, "status": p["status"], "approver_role": p["approver_role"], "expires_at": p["expires_at"],
                    "decided_by": p["decided_by"], "decided_at": p["decided_at"], "maker": p["maker"], "note": p["note"], "applied": None})
    return out


def edit_metric(proposal_id: str, key: str, action: str, user: dict[str, Any], threshold: dict[str, Any] | None = None) -> dict[str, Any]:
    """Accept, reject or edit (the threshold) one proposed metric before the decision; an edit is back-tested at once."""
    st = mstore.get()
    p = st.proposal(proposal_id)
    if p is None or p["kind"] != "monitoring_set":
        raise KeyError(proposal_id)
    v = _status(p)
    if v["status"] != "pending":
        raise NotAllowed(f"The proposal is {v['status']}.")
    if not user.get("username"):
        raise NotAllowed("Sign in to review proposals.")
    m = next((x for x in p["payload"]["metrics"] if x["key"] == key), None)
    if m is None:
        raise KeyError(key)
    if action in ("accept", "reject"):
        m["status"] = "accepted" if action == "accept" else "rejected"
    elif action == "edit":
        th = dict(m["threshold"])
        for k in ("k", "level", "trigger", "limit"):
            if threshold and k in threshold and k in th:
                th[k] = float(threshold[k])
        if threshold and threshold.get("logic") in ("change", "zscore") and th["logic"] in ("change", "zscore"):
            th["logic"] = threshold["logic"]
        if th.get("logic") == "appetite" and th["trigger"] > th["limit"]:
            raise ValueError("The trigger cannot be above the limit.")
        m.update({k: v2 for k, v2 in T.rebacktest(m, th).items() if k in ("threshold", "threshold_text", "backtest", "noise", "expected_alert_rate")})
        m["status"], m["edited_by"] = "edited", user["username"]
    else:
        raise ValueError("action must be accept, reject or edit")
    st.update_proposal(proposal_id, payload=p["payload"])
    return _status(st.proposal(proposal_id))  # type: ignore[arg-type]


def may_decide(user: dict[str, Any]) -> bool:
    return bool(user.get("username")) and agent_role(user) in APPROVER_ROLES


def decide(proposal_id: str, decision: str, user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Approve or reject through the runtime's approvals (maker-checker, expiry, one decision); approval applies it."""
    st = mstore.get()
    p = st.proposal(proposal_id)
    if p is None:
        raise KeyError(proposal_id)
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    if not may_decide(user):
        raise NotAllowed("Only a risk approver (Head of Risk, Head of Credit or Risk Manager) can decide a monitoring set.")
    a = approval_for(proposal_id)
    if a is None:
        raise NotAllowed("This proposal has no approval in the queue.")
    _APPROVER.user = user["username"]
    try:
        row = RA.decide(a["id"], decision=decision, user=user["username"], role=agent_role(user), note=note)
    except (RA.NotAuthorised, RA.MakerChecker) as e:
        raise NotAllowed(str(e)) from e
    except (RA.AlreadyDecided, RA.Expired) as e:
        raise NotAllowed(str(e)) from e
    finally:
        _APPROVER.user = ""
    applied = row.get("applied") or {}
    if decision == "approve" and not applied.get("applied"):
        raise NotAllowed(f"Approved, but it could not be applied: {applied.get('error') or applied.get('note') or 'no applier'}.")
    if decision == "reject":
        st.update_proposal(proposal_id, status="rejected", decided_by=user["username"], decided_at=time.time(), note=note[:500])
    return {"proposal": _status(st.proposal(proposal_id)), "applied": applied.get("result") or {}}  # type: ignore[arg-type]


# ------------------------------------------------------------------ the panel
def panel(scope: dict[str, Any]) -> dict[str, Any]:
    from backend.agents_v5.runtime import store
    st = mstore.get()
    sk = scope["scope_key"]
    props = [_status(p) for p in st.proposals(sk) if p["status"] != "superseded"]
    s = st.active_set(sk)
    runs = store.list_runs(agent=AGENT_ID, scope=sk, limit=8)
    metrics = [dict(m) for m in (s["metrics"] if s else []) if m.get("status") != "rejected"]
    for r in runs:                       # the active set shows each metric as the latest run computed it
        full = store.load_run(r["run_id"]) if r.get("status") in ("completed", "partial") else None
        comp = full.done("lenses_compute") if full else None
        if comp and full.plan and full.plan.goal_type == "run":
            now = {c["key"]: c for c in (comp.output or {}).get("computed", [])}
            for m in metrics:
                c = now.get(m["key"])
                if c:
                    m.update({"now_display": c["display"], "now_period": c["period"], "firing": bool(c["evaluation"].get("fired"))})
            break
    return {"scope": scope, "pending": [p for p in props if p["status"] == "pending"],
            "decided": [p for p in props if p["status"] != "pending"][:5],
            "active": None if s is None else {k: s[k] for k in ("set_id", "label", "lens_id", "version", "approved_by", "approved_at", "created_by", "schedule")}
            | {"metrics": metrics, "retired": [m for m in s["metrics"] if m.get("retired")]},
            "alerts": st.alerts(s["set_id"], limit=30) if s else [], "runs": runs,
            "agent": {"agent_id": AGENT_ID, "name": "Monitoring agent", "approver": "Head of Risk, Head of Credit or Risk Manager"}}


# ------------------------------------------------------------------ registration and a direct entry point
DEF: AgentDef | None = None


def register() -> AgentDef:
    global DEF
    for t in T.TOOLS:
        register_tool(t)
    register_applier(T.KIND_SET, apply_set)
    register_applier(T.KIND_CHANGES, apply_changes)
    DEF = register_agent(AgentDef(spec=spec(), module=T.MODULE, goal_types=plans.GOAL_TYPES, classify=plans.classify,
                                  deterministic_plan=plans.deterministic_plan, conclude=conclude, adapt=plans.adapt,
                                  required_tools=plans.required_tools, scope_of=scope_of, system_prompt=SYSTEM,
                                  notify_users=NOTIFY_USERS, href=href))
    return DEF


def run(goal: str, context: dict[str, Any] | None = None, *, planner: str = "deterministic", trigger: str = "on_demand", user: str = "",
        provider: Any = None) -> Run:
    from backend.agents_v5.runtime import start
    if get_agent(AGENT_ID) is None:
        register()
    return start(AGENT_ID, goal, dict(context or {}), planner_mode=planner, trigger=trigger, user=user, provider=provider)


def fmt_amount(v: Any) -> str:
    return fmt.amount(v)
