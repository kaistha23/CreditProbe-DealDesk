"""The Early Warning triage agent on the agents_v5 runtime: tools, agent definition, conclusion, memory, schedule.

- Tools (A1) wrap the reads and engines in `tools.py`; each returns a `ToolResult` whose `figures` hold every number
  the narrative may cite. Chained steps read earlier results through `ctx.results`.
- `conclude(run)` (A3) turns the results into findings with evidence step ids, a narrative where each figure cites
  its step ([S#]), the module's output (verdict per name, the summary, the RM action notes) and records the verdicts
  and notes in the agent's memory for follow-up on later runs.
- Proposals (A4) are queued by the proposal-only tools through the runtime's `propose()`; approving one records the
  decision for the staging process and never writes a stage (`_applier`).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Callable

from backend.agentic.registry import Agent
from backend.agents_v5.ews import decide as dec
from backend.agents_v5.ews import plans, store
from backend.agents_v5.ews import tools as T
from backend.agents_v5.runtime import (PROPOSAL_ONLY, READ_ONLY, AgentDef, Conclusion, Finding, Run, Tool,
                                       ToolContext, ToolResult, register_agent, register_applier, register_tool)

logger = logging.getLogger(__name__)
AGENT_ID = plans.AGENT_ID
MODULE = "early_warning"
#: R15 L5: the steps that close a triage run (decision, ECL sizing, follow-up, proposals, summary)
CLOSING = ("crm_assess", "triage_decide", "ecl_impact", "triage_followup", "propose_utp", "propose_sicr",
           "propose_watchlist", "triage_summary")
SEV = {"utp": "critical", "sicr": "major", "watchlist": "minor", "watch": "info", "noise": "info"}


# ---------------------------------------------------------------- wrappers: inputs + earlier results -> ToolResult

#: run id -> tool -> the full tool data. The step keeps a slim copy (counts, and per-name data for small scopes),
#: so a period run's trace stays small; chained steps and the conclusion read the full data from here.
_RESULTS: dict[str, dict[str, Any]] = {}
#: per-name collections kept on the step only up to this many names
SLIM_NAMES = 25
_BULKY = ("by_owner", "names", "by_sub_sector", "outcomes", "previous", "actions", "owners", "pending_proposals",
          "proposals", "stage3_ids", "duplicates", "already_on_watchlist", "sub_sectors")


def _stash(ctx: ToolContext) -> dict[str, Any]:
    key = ctx.run_id or "adhoc"
    if key not in _RESULTS:
        _RESULTS[key] = {}
        while len(_RESULTS) > 8:
            _RESULTS.pop(next(iter(_RESULTS)))
    return _RESULTS[key]


def _slim(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if k in _BULKY and isinstance(v, (dict, list)) and len(v) > SLIM_NAMES:
            out[k] = {"note": f"{len(v):,} entries; the per-name results are on the findings"}
        else:
            out[k] = v
    return out


def _stashing(fn: Callable[[dict[str, Any], ToolContext], ToolResult]) -> Callable[[dict[str, Any], ToolContext], ToolResult]:
    def run(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
        res = fn(inputs, ctx)
        name = getattr(run, "tool_name", "")
        if name:
            _stash(ctx)[name] = res.data
        res.data = _slim(res.data)
        return res
    return run


def _r(ctx: ToolContext, tool: str) -> dict[str, Any]:
    if not tool:
        return {}
    got = _stash(ctx).get(tool)
    return got if isinstance(got, dict) else (ctx.results.get(tool) or {})


def _goal_of(ctx: ToolContext) -> str:
    """The run's goal text (a model plan's context may not carry the borrower or sector the goal names)."""
    try:
        from backend.agents_v5.runtime import store as rs
        r = rs.load_run(ctx.run_id) if ctx.run_id else None
        return r.goal if r else ""
    except Exception:  # noqa: BLE001
        return ""


def _scope(inputs: dict[str, Any], ctx: ToolContext) -> tuple[str, str, list[str]]:
    w = _r(ctx, "ews_warned_names")
    if not w:  # a model plan that did not start with the warned names: read them once, as the written plan does
        gt, p = plans.parse_goal(_goal_of(ctx), ctx.context)
        p1 = {"domain": p["domain"], "period": p["period"], "include_followed": gt == "period"}
        if gt in ("borrower", "sector"):
            p1[gt] = p[gt]
        w = T.warned_names(**p1)
        _stash(ctx)["ews_warned_names"] = w
    return (inputs.get("domain") or "corporate", inputs.get("period") or w.get("period", ""),
            list(inputs.get("owners") or w.get("owners") or []))


def _today(ctx: ToolContext, inputs: dict[str, Any]) -> str:
    return str(inputs.get("today") or ctx.context.get("today") or "")


def _empty(summary: str = "Nothing in scope for this step.") -> ToolResult:
    return ToolResult(summary=summary, figures={}, data={"by_owner": {}})


def _counts(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def t_warned(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    keys = ("domain", "period", "sector", "borrower", "include_followed", "max_names")
    out = T.warned_names(**{k: inputs[k] for k in keys if k in inputs})
    figs = {k: out.get(k) for k in ("warned_total", "warned_ead", "stage3", "stage3_ead", "live", "revisit",
                                    "budget_skipped") if out.get(k) is not None}
    figs["in_scope"] = len(out.get("owners") or [])
    return ToolResult(summary=out["summary"], figures=figs, data=out, rows_scanned=out.get("rows_scanned", 0))


def _per_owner(fn: Callable[..., dict[str, Any]], **extra: Any) -> Callable[[dict[str, Any], ToolContext], ToolResult]:
    def run(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
        d, per, owners = _scope(inputs, ctx)
        if not owners:
            return _empty()
        kw = {k: inputs[k] for k in extra if k in inputs}
        out = fn(d, per, owners, **kw)
        return ToolResult(summary=out.get("summary", ""), figures={"names": len(owners)}, data=out,
                          rows_scanned=out.get("rows_scanned", 0))
    return run


def t_bureau(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from backend.agents_v5.runtime import ToolUnavailable
    d, per, owners = _scope(inputs, ctx)
    if not owners:
        return _empty()
    out = T.bureau(d, per, owners)
    if out.get("skipped"):
        raise ToolUnavailable(out["skipped"])
    xd = sum(1 for v in out["by_owner"].values() if v.get("external_default"))
    return ToolResult(summary=out["summary"], figures={"names": len(owners), "external_default": xd}, data=out,
                      rows_scanned=out.get("rows_scanned", 0))


def t_peers(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    d, per, _ = _scope(inputs, ctx)
    subs = list(inputs.get("sub_sectors") or _r(ctx, "ews_warned_names").get("sub_sectors") or [])
    if not subs:
        return _empty()
    out = T.sector_peers(d, per, subs)
    return ToolResult(summary=out["summary"], figures={"sub_sectors": len(subs), "stressed": len(out["stressed"])},
                      data=out, rows_scanned=out.get("rows_scanned", 0))


def t_history(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    d, _, owners = _scope(inputs, ctx)
    # names now in Stage 3 are outside triage, but an earlier verdict or open action on them still needs closing
    owners = owners + list(_r(ctx, "ews_warned_names").get("stage3_ids") or [])
    out = T.history(d, owners, ctx.run_id)
    return ToolResult(summary=out["summary"], figures={"previous": len(out["previous"]), "actions": len(out["actions"]),
                                                       "pending": len(out["pending_proposals"])},
                      data=out, rows_scanned=out.get("rows_scanned", 0))


def t_assess(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    w = _r(ctx, "ews_warned_names")
    names = w.get("names") or {}
    if not names:
        return _empty()
    out = T.assess(names, _r(ctx, "ews_rules_trend").get("by_owner") or {}, _r(ctx, "b360_evidence").get("by_owner") or {},
                   _r(ctx, "conduct_account").get("by_owner") or {}, _r(ctx, "bureau_external").get("by_owner") or {},
                   _r(ctx, "ews_sector_peers").get("by_sub_sector") or {}, _r(ctx, "ews_changes").get("by_owner") or {},
                   domain=_r(ctx, "ews_warned_names").get("domain") or "corporate")
    fired = sum(1 for v in out["by_owner"].values() if v["indicators"])
    figs: dict[str, Any] = {"names": len(names), "with_indicator": fired}
    if len(names) <= 20:  # a borrower or a small sector: the indicator values the narrative quotes
        figs["thresholds"] = dict(out["thresholds"])
        figs["values"] = {o: {i["code"]: i["fields"] for i in v["indicators"]} for o, v in out["by_owner"].items()}
    return ToolResult(summary=out["summary"], figures=figs, data=out)


def t_decide(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    names = _r(ctx, "ews_warned_names").get("names") or {}
    if not names:
        return ToolResult(summary="No warned name to decide.", figures={}, data={"by_owner": {}, "counts": {}})
    out = T.decide(names, _r(ctx, "crm_assess").get("by_owner") or {}, _r(ctx, "ews_rules_trend").get("by_owner") or {},
                   _today(ctx, inputs))
    return ToolResult(summary=out["summary"], figures=dict(out["counts"]), data=out)


def t_ecl(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    d, per, _ = _scope(inputs, ctx)
    out = T.ecl_impact(d, per, _r(ctx, "triage_decide").get("by_owner") or {})
    figs: dict[str, Any] = {"totals": out.get("totals") or {}}
    verdicts = _r(ctx, "triage_decide").get("by_owner") or {}
    for o, x in (out.get("by_owner") or {}).items():
        if verdicts.get(o, {}).get("verdict") in ("sicr", "utp"):
            figs[o] = {"ead": x["ead"], "move": x["proposal_move"], "expected_uplift": x["expected_uplift"]}
    return ToolResult(summary=out["summary"], figures=figs, data=out, rows_scanned=out.get("rows_scanned", 0))


def t_followup(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    names = _r(ctx, "ews_warned_names").get("names") or {}
    out = T.followup(names, _r(ctx, "triage_decide").get("by_owner") or {}, _r(ctx, "b360_evidence").get("by_owner") or {},
                     _r(ctx, "triage_history"), _today(ctx, inputs),
                     defaulted=_r(ctx, "ews_warned_names").get("stage3_ids") or [])
    figs: dict[str, Any] = dict(out["counts"])
    for x in out["outcomes"]:
        if x.get("outcome") == "escalated":
            figs[x["borrower_id"]] = {"overdue_days": x.get("overdue_days", 0)}
    return ToolResult(summary=out["summary"], figures=figs, data=out)


def _t_propose(kind: str) -> Callable[[dict[str, Any], ToolContext], ToolResult]:
    def run(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
        fn = {"utp": T.propose_utp, "sicr": T.propose_sicr, "watchlist": T.propose_watchlist}[kind]
        out = fn(names=_r(ctx, "ews_warned_names").get("names") or {},
                 verdicts=_r(ctx, "triage_decide").get("by_owner") or {},
                 assessed=_r(ctx, "crm_assess").get("by_owner") or {},
                 impact=_r(ctx, "ecl_impact").get("by_owner") or {}, history=_r(ctx, "triage_history"),
                 b360=_r(ctx, "b360_evidence").get("by_owner") or {}, run_id=ctx.run_id, today=_today(ctx, inputs),
                 user=ctx.user, scope=scope_of(ctx.context))
        figs = {"proposed": len(out.get("proposals") or []), "already_pending": len(out.get("duplicates") or []),
                "already_on_watchlist": len(out.get("already_on_watchlist") or [])}
        return ToolResult(summary=out["summary"], figures=figs, data=out)
    return run


def t_summary(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    out = T.summary(_r(ctx, "ews_warned_names"), _r(ctx, "triage_decide"), _r(ctx, "ecl_impact"), _r(ctx, "triage_followup"))
    f = out["figures"]
    f["proposals"] = sum(len(_r(ctx, t).get("proposals") or []) for t in ("propose_utp", "propose_sicr",
                                                                          "propose_watchlist"))
    f["already_pending"] = sum(len(_r(ctx, t).get("duplicates") or []) for t in ("propose_utp", "propose_sicr",
                                                                                "propose_watchlist"))
    return ToolResult(summary=out["line"], figures={k: v for k, v in f.items() if k != "followup"}, data=out)


def _schema(**props: str) -> dict[str, Any]:
    return {"type": "object", "properties": {k: {"type": t} for k, t in props.items()}}


SCOPE = _schema(domain="string", period="string")
TOOLS: tuple[Tool, ...] = (
    Tool("ews_warned_names", MODULE, "The warned borrowers in scope (the period, a sector or one borrower), Stage 3 "
         "set aside, plus names this agent follows up from earlier runs. Always the first step.",
         _schema(domain="string", period="string", sector="string", borrower="string", include_followed="boolean",
                 max_names="integer"), READ_ONLY, t_warned, engine="backend.ews_domain.reader (EWS release)"),
    Tool("ews_rules_trend", MODULE, "The EWS rules fired per name and the six-period score trend.", SCOPE, READ_ONLY,
         _per_owner(T.rules_trend), engine="EWS release, gw-ews rule set"),
    Tool("b360_evidence", "borrower_360", "Borrower 360 facts per name: exposure, group, rating, financials, collateral, "
         "covenants, RM; open conditions where the build has them.", _schema(domain="string", period="string",
                                                                              profile="boolean"),
         READ_ONLY, _per_owner(T.b360_evidence, profile=False), engine="EWS release + backend.b360.service"),
    Tool("conduct_account", MODULE, "Account conduct: turnover against revenue (routing), inflow trend, returned "
         "payments, overdraft behaviour, balance buffer.", SCOPE, READ_ONLY, _per_owner(T.conduct),
         engine="EWS release (Open Banking fields)"),
    Tool("bureau_external", "bureau", "Bureau: external exposure, external DPD, default at another lender, enquiries.",
         SCOPE, READ_ONLY, t_bureau, engine="EWS release (bureau fields)"),
    Tool("ews_sector_peers", MODULE, "Peers in the same sub-sector: warned share against the book, its trend, sector "
         "stress.", SCOPE, READ_ONLY, t_peers, engine="EWS release"),
    Tool("ews_changes", MODULE, "What changed since last period: score, reasons, DPD, stage, rating, cures.", SCOPE,
         READ_ONLY, _per_owner(T.changes), engine="EWS release"),
    Tool("triage_history", MODULE, "Earlier triage of these names: last verdict, open RM actions, pending proposals.",
         _schema(domain="string"), READ_ONLY, t_history, engine="agent memory + approvals queue"),
    Tool("crm_assess", "regulatory", "The CBUAE CRM indicator engine: Art. 6 (UTP) and Art. 7 (SICR) indicators on the "
         "gathered evidence, each with its clause, the fields read and the threshold.", _schema(), READ_ONLY, t_assess,
         engine="backend.agents_v5.ews.indicators over the policy pack pd_cbuae_crm"),
    Tool("triage_decide", MODULE, "The written decision table: verdict (noise, watch, watchlist, SICR, UTP) with the "
         "reason, and the RM action note with owner and due date.", _schema(today="string"), READ_ONLY, t_decide,
         engine="backend.agents_v5.ews.decide"),
    Tool("ecl_impact", "risk_intel", "ECL impact of each proposal: the EWS ECL-impact computation (P3-ECL-01) and the "
         "book's lifetime ECL.", SCOPE, READ_ONLY, t_ecl, engine="backend.risk_intel.ecl_impact"),
    Tool("triage_followup", MODULE, "Revisit followed names: cured, worsened, overdue; escalate RM, then credit "
         "officer, then CCO.", _schema(today="string"), READ_ONLY, t_followup, engine="backend.agents_v5.ews.followup"),
    Tool("propose_utp", MODULE, "Queue unlikely-to-pay proposals for the CCO. Never writes a stage.", _schema(),
         PROPOSAL_ONLY, _t_propose("utp"), engine="approvals queue"),
    Tool("propose_sicr", MODULE, "Queue SICR (Stage 2) proposals for the CCO. Never writes a stage.", _schema(),
         PROPOSAL_ONLY, _t_propose("sicr"), engine="approvals queue"),
    Tool("propose_watchlist", MODULE, "Queue watch-list entries for the credit officer.", _schema(), PROPOSAL_ONLY,
         _t_propose("watchlist"), engine="approvals queue"),
    Tool("triage_summary", MODULE, "The portfolio summary of the run.", _schema(), READ_ONLY, t_summary),
)


# ---------------------------------------------------------------- the agent definition

def spec() -> Agent:
    return Agent(
        agent_id=AGENT_ID, business_name="Early Warning triage",
        purpose=("Triage the period's early warnings name by name against the CBUAE CRM SICR and UTP indicators, size "
                 "the ECL impact of each proposal, draft the RM action notes, follow up names from earlier runs and "
                 "escalate; SICR and UTP only as proposals for a person to approve."),
        when_to_use=("after each EWS refresh", "triage a borrower or a retail customer", "triage a sector or a product"),
        when_not_to_use=("changing a stage or a flag", "pool-level retail staging (this agent works name by name)"),
        allowed_capabilities=("read", "propose"), allowed_tools=tuple(t.name for t in TOOLS),
        allowed_data_domains=("early_warning", "borrower_360", "bureau", "open_banking", "risk_intel", "regulatory"),
        maximum_steps=20, timeout_seconds=120, max_model_calls=4, max_rows_scanned=2_000_000, autonomy_level=1,
        human_approval_requirements=tuple(T.KIND.values()),
        escalation_rules=("RM until the due date", "credit officer once overdue",
                          "CCO 14 days after the due date, or on a worsening already with the credit officer"),
        owner="Credit Risk")


def scope_of(ctx: dict[str, Any]) -> str:
    d = ctx.get("domain") or "corporate"
    tgt = ctx.get("borrower") or ctx.get("sector") or ""
    return f"{d}:{tgt}" if tgt else d


def href(run: Run) -> str:
    return f"/early-warning?domain={run.context.get('domain') or 'corporate'}&agent_run={run.run_id}"


SYSTEM = ("You plan for the Early Warning triage agent of a corporate bank in the UAE. Gather the evidence for each "
          "warned name (rules and trend, Borrower 360, account conduct, bureau, sector peers, changes, earlier triage), "
          "then call crm_assess and triage_decide. Never decide a verdict yourself and never state a figure. SICR and "
          "UTP are proposals only. Start with ews_warned_names.")


# ---------------------------------------------------------------- conclusion

def _sid(run: Run) -> dict[str, str]:
    return {s.tool: s.id for s in (run.plan.steps if run.plan else []) if s.status == "done"}


def _data(run: Run, tool: str) -> dict[str, Any]:
    full = (_RESULTS.get(run.run_id or "adhoc") or {}).get(tool)
    if isinstance(full, dict):
        return full
    s = run.done(tool)
    out = (s.output if s and isinstance(s.output, dict) else None) or {}
    return {k: ({} if isinstance(v, dict) and set(v) == {"note"} else v) for k, v in out.items()}


def conclude(run: Run) -> Conclusion:
    # the full results are on the steps (compacted only when very large); re-read big ones from the tools' data
    ids = _sid(run)
    res = {t: _data(run, t) for t in ids}
    w, d = res.get("ews_warned_names") or {}, res.get("triage_decide") or {}
    names, verdicts = w.get("names") or {}, d.get("by_owner") or {}
    a = (res.get("crm_assess") or {}).get("by_owner") or {}
    imp = (res.get("ecl_impact") or {}).get("by_owner") or {}
    follow = {x["borrower_id"]: x for x in (res.get("triage_followup") or {}).get("outcomes") or []}
    b3 = (res.get("b360_evidence") or {}).get("by_owner") or {}
    props: dict[str, dict[str, Any]] = {}
    pend = {(p["borrower_id"], p["kind"]): p for p in (res.get("triage_history") or {}).get("pending_proposals") or []}
    for t in ("propose_utp", "propose_sicr", "propose_watchlist"):
        for p in (res.get(t) or {}).get("proposals") or []:
            props[p["borrower_id"]] = {**p, "step": ids.get(t)}
        for o in (res.get(t) or {}).get("duplicates") or []:  # pending from an earlier run: still decidable here
            old = pend.get((o, t.split("_", 1)[1]))
            if old and o not in props:
                props[o] = {"borrower_id": o, "approval_id": old["id"], "approver_role": old.get("approver_role"),
                            "expires": old.get("expires_at"), "pending_since_earlier_run": True, "step": ids.get(t)}
    findings: list[Finding] = []
    summ = res.get("triage_summary") or {}
    if summ and not (run.plan and run.plan.goal_type == "borrower"):
        findings.append(Finding(title="Portfolio summary", severity="info", detail=summ.get("line", ""),
                                evidence=[x for x in (ids.get("triage_summary"), ids.get("triage_decide"),
                                                      ids.get("ecl_impact")) if x],
                                kind="ews.summary", data={"figures": summ.get("figures")}))
    if w.get("not_found"):
        findings.append(Finding(title=f"{w['not_found']} not found", severity="info", detail=w.get("summary", ""),
                                evidence=[ids["ews_warned_names"]], kind="ews.not_found"))
    if run.plan and run.plan.goal_type == "borrower" and not names and w.get("stage3"):
        findings.append(Finding(title=f"{(w.get('stage3_ids') or ['The borrower'])[0]}: already Stage 3",
                                severity="info", evidence=[ids["ews_warned_names"]], kind="ews.stage3",
                                detail="Already Stage 3 or in default: outside triage; the recovery and provisioning "
                                       "process holds it."))
    src = {"b360.evidence": "b360_evidence", "conduct.account": "conduct_account", "bureau.external": "bureau_external",
           "ews.sector_peers": "ews_sector_peers"}
    order = sorted(verdicts, key=lambda o: (-dec.RANK[verdicts[o]["verdict"]], -(names.get(o, {}).get("ead") or 0), o))
    for o in order:
        v, n = verdicts[o], names.get(o, {})
        inds = (a.get(o) or {}).get("indicators") or []
        ev = [ids[t] + f":by_owner.{o}" for t in ("ews_rules_trend", "b360_evidence") if t in ids]
        for i in inds:
            if i["code"] in v["basis"] and src.get(i["source"]) in ids:
                ev.append(ids[src[i["source"]]] + f":by_owner.{o}")
        if o in imp and "ecl_impact" in ids:
            ev.append(ids["ecl_impact"] + f":by_owner.{o}")
        if v["verdict"] == "noise" and "ews_changes" in ids:
            ev.append(ids["ews_changes"] + f":by_owner.{o}")
        ev.insert(0, ids["triage_decide"] + f":by_owner.{o}")
        findings.append(Finding(
            title=f"{n.get('borrower_name') or o}: {v['label']}", severity=SEV[v["verdict"]], detail=v["reason"],
            evidence=list(dict.fromkeys(ev)), kind=f"ews.verdict.{v['verdict']}",
            data={"borrower_id": o, "borrower_name": n.get("borrower_name"), "verdict": v["verdict"],
                  "label": v["label"], "confidence": v["confidence"], "articles": v["articles"],
                  "indicators": [{k: i[k] for k in ("code", "kind", "strength", "label", "fields", "threshold")}
                                 | {"article": i["article"]["ref"], "in_basis": i["code"] in v["basis"]}
                                 | ({"excerpt": i["article"]["excerpt"]} if i["code"] in v["basis"] else {})
                                 for i in inds],
                  "stage": n.get("stage"), "band": n.get("band"), "score": n.get("score"), "ead": n.get("ead"),
                  "sector": n.get("sector"), "sub_sector": n.get("sub_sector"), "revisit": bool(n.get("revisit")),
                  "ecl_impact": imp.get(o), "action_note": v.get("note"), "proposal": props.get(o),
                  "followup": {k: x for k, x in (follow.get(o) or {}).items() if k != "actions"} or None,
                  "links": (b3.get(o) or {}).get("links"),
                  "ews": _ews_detail(o, res, ids)}))
    for o, x in follow.items():
        if o not in verdicts:
            findings.append(Finding(title=f"{o}: follow-up carried", severity="info", detail=x.get("why", ""),
                                    evidence=[ids["triage_followup"]], kind="ews.followup",
                                    data={"borrower_id": o, "followup": {k: v for k, v in x.items() if k != "actions"}}))
    text = narrative(run, ids, res)
    single0 = bool(run.plan and run.plan.goal_type == "borrower")
    headline = (plain_headline(summ.get("figures")) if summ.get("figures") and not single0 else "") \
        or summ.get("line") or w.get("summary") or ""
    output = {"headline": headline, "summary": summ.get("figures"),
              "table": triage_table(findings, ids), "plain_words": PLAIN_WORDS, "terms": TERMS,
              "sources": {sid: T_LABEL.get(t, t.replace("_", " ")) for t, sid in ids.items()},
              "period": w.get("period"), "prior_period": w.get("prior_period"),
              "verdicts": {o: v["verdict"] for o, v in verdicts.items()},
              "followup": (res.get("triage_followup") or {}).get("counts"),
              "notes": sum(1 for v in verdicts.values() if v.get("note")),
              "approvals": [p["approval_id"] for p in props.values() if not p.get("pending_since_earlier_run")]}
    single = bool(run.plan and run.plan.goal_type == "borrower")
    for p in props.values():  # proposals queued by this run; for one borrower also its pending one, to decide here
        if p.get("pending_since_earlier_run") and not single:
            continue
        if p["approval_id"] not in run.proposals:
            run.proposals.append(p["approval_id"])
    try:
        output["recorded"] = record(run, w, verdicts, res.get("triage_followup") or {}, names)
    except Exception as exc:  # noqa: BLE001 -- memory is best effort; the run stands
        logger.warning("ews triage memory not recorded: %s", exc)
        output["recorded"] = {"error": str(exc)}
    _RESULTS.pop(run.run_id, None)
    return Conclusion(findings=findings, narrative=text, output=output, proposals=[])


def _m(v: float) -> str:
    return f"SAR {v:,.1f} m"


# ---------------------------------------------------------------- R15 L5/L6: plain words, the ranked table, detail

#: Spelled out on first use, everywhere the triage speaks (answer, table, chips).
TERMS = {
    "UTP": "Unlikely to pay: the bank expects the borrower will not repay in full; proposed move to Stage 3 "
           "(credit-impaired, lifetime ECL at the loss floor).",
    "SICR": "Significant increase in credit risk since the loan was granted; proposed move from Stage 1 to Stage 2 "
            "(lifetime ECL instead of 12-month ECL).",
    "Watchlist": "Kept under closer review by the RM and credit; no stage move.",
    "EAD": "Exposure at default: what the bank would lose before recoveries if the borrower defaulted today.",
    "ECL move": "The change in expected credit loss (provision) if the proposal is approved.",
}
VERDICT_PLAIN = {"utp": "Unlikely to pay (UTP) → Stage 3", "sicr": "Significant increase in credit risk (SICR) → Stage 2",
                 "watchlist": "Watchlist (no stage move)", "watch": "Watch", "noise": "Noise (explained)"}
PLAIN_WORDS = [  # the shared block's rule: 3-4 lines, at most 60 words (K34)
    "Reads every borrower flagged this period and tests each against the CBUAE rules for SICR and unlikely to pay.",
    "Produces a verdict per borrower, the ECL each proposal adds and an action for the RM.",
    "Nothing changes on its own: a credit officer approves or rejects every proposal.",
    "Takes about 10–30 seconds; a slow model is dropped after 40 seconds.",
]
T_LABEL = {
    "ews_warned_names": "Warned borrowers this period", "ews_rules_trend": "Warning rules and score trend",
    "b360_evidence": "Borrower 360 facts", "conduct_account": "Account conduct (open banking)",
    "bureau_external": "Credit bureau", "ews_sector_peers": "Sector peers", "ews_changes": "Changes since last period",
    "triage_history": "Earlier triage", "crm_assess": "CBUAE CRM indicator test", "triage_decide": "Decision table",
    "ecl_impact": "ECL impact", "triage_followup": "Follow-up", "propose_utp": "UTP proposals",
    "propose_sicr": "SICR proposals", "propose_watchlist": "Watchlist proposals", "triage_summary": "Summary",
}


def plain_headline(f: dict[str, Any] | None) -> str:
    """One sentence a credit committee reads first (figures from the summary step)."""
    if not f:
        return ""
    n_prop = int(f.get("utp", 0)) + int(f.get("sicr", 0))
    ecl = float(f.get("proposal_ecl", float(f.get("utp_ecl", 0.0)) + float(f.get("sicr_ecl", 0.0))))
    if not n_prop:
        return (f"{f.get('reviewed', 0)} warnings reviewed: no borrower needs a stage move; "
                f"{f.get('watchlist', 0)} go on the watchlist.")
    return (f"{f.get('utp', 0)} borrowers look unlikely to pay (UTP → Stage 3) and {f.get('sicr', 0)} show a significant "
            f"increase in credit risk (SICR → Stage 2): ECL +{_m(ecl)} if approved, out of {f.get('warned', 0)} warnings.")


def triage_table(findings: list[Finding], ids: dict[str, str], limit: int = 30) -> list[dict[str, Any]]:
    """The ranked table: UTP, SICR, then watchlist; within each, the largest ECL move first, then EAD."""
    rows = []
    for f in findings:
        d = f.data or {}
        v = d.get("verdict")
        if v not in ("utp", "sicr", "watchlist"):
            continue
        imp = d.get("ecl_impact") or {}
        note = d.get("action_note") or {}
        prop = d.get("proposal") or {}
        basis = [i for i in d.get("indicators") or [] if i.get("in_basis")]
        rows.append({
            "borrower_id": d.get("borrower_id"), "borrower_name": d.get("borrower_name") or d.get("borrower_id"),
            "verdict": v, "verdict_plain": VERDICT_PLAIN[v], "sector": d.get("sector"), "stage": d.get("stage"),
            "ead": imp.get("ead", d.get("ead")), "ecl_move": imp.get("proposal_move") if v in ("utp", "sicr") else 0.0,
            "action": note.get("action") or "", "owner": note.get("owner") or "", "due": note.get("due") or "",
            "rule": "; ".join(f"{i.get('article')}: {i.get('label')}" for i in basis[:3]),
            "articles": d.get("articles") or [],
            "evidence": list(dict.fromkeys(e.split(":", 1)[0] for e in f.evidence)),
            "approval_id": prop.get("approval_id"),
        })
    rank = {"utp": 0, "sicr": 1, "watchlist": 2}
    rows.sort(key=lambda r: (rank[r["verdict"]], -(r["ecl_move"] or 0), -(r["ead"] or 0), r["borrower_id"] or ""))
    return rows[:limit]


def _ews_detail(o: str, res: dict[str, dict[str, Any]], ids: dict[str, str]) -> dict[str, Any]:
    """The borrower's early-warning indicators behind its verdict, each with the step (S-chip) that read it."""
    rt = ((res.get("ews_rules_trend") or {}).get("by_owner") or {}).get(o) or {}
    b = ((res.get("b360_evidence") or {}).get("by_owner") or {}).get(o) or {}
    c = ((res.get("conduct_account") or {}).get("by_owner") or {}).get(o) or {}
    bu = ((res.get("bureau_external") or {}).get("by_owner") or {}).get(o) or {}
    ex, ow = b.get("exposure") or {}, b.get("owner") or {}
    per = (res.get("ews_warned_names") or {}).get("period") or (res.get("ews_rules_trend") or {}).get("period")
    out: dict[str, Any] = {"period": per}
    if rt:
        out["rules"] = [{"label": r.get("label"), "weight": r.get("weight")} for r in rt.get("rules") or []]
        out["score"], out["band"], out["change"] = rt.get("score"), rt.get("band"), rt.get("change")
        out["series"] = rt.get("series") or []
        out["rules_step"] = ids.get("ews_rules_trend")
    if ex or ow:
        out["dpd"], out["stage"] = ex.get("dpd"), ex.get("stage")
        out["rating"], out["rating_previous"] = ow.get("rating_current"), ow.get("rating_previous")
        out["covenant_breaches"] = ex.get("covenant_breaches")
        out["b360_step"] = ids.get("b360_evidence")
    if c:
        out["conduct"] = {k: c.get(k) for k in ("returned_payments_q", "inflow_trend_pct", "overdraft_utilisation_pct",
                                                 "buffer_months", "turnover_to_revenue_pct") if c.get(k) is not None}
        out["conduct_step"] = ids.get("conduct_account")
    if bu.get("available"):
        out["bureau"] = {k: bu.get(k) for k in ("external_dpd_days", "external_default", "enquiries_q",
                                                 "external_exposure_sar_mn")}
        out["bureau_step"] = ids.get("bureau_external")
    return out


def narrative(run: Run, ids: dict[str, str], res: dict[str, dict[str, Any]]) -> str:
    """Every sentence with a figure cites the step whose `figures` hold it."""
    w = res.get("ews_warned_names") or {}
    if w.get("not_found"):
        return f"{w['not_found']} is not on the book for this period."
    out: list[str] = []
    S = lambda t: f"[{ids[t]}]" if t in ids else ""  # noqa: E731
    summ = (res.get("triage_summary") or {}).get("figures")
    single = bool(run.plan and run.plan.goal_type == "borrower")
    if summ and not single:
        out.append(plain_headline(summ).rstrip(".") + f" {S('triage_summary')}.")
        out.append(f"{summ['reviewed']} of {summ['warned']} warnings reviewed, {summ['stage3_outside']} already "
                   f"Stage 3 and outside triage {S('triage_summary')}.")
        out.append(f"Verdicts: {summ['noise']} noise, {summ['watch']} watch, {summ['watchlist']} watchlist, "
                   f"{summ['sicr']} SICR proposals (significant increase in credit risk: Stage 1 to Stage 2) and "
                   f"{summ['utp']} UTP proposals (unlikely to pay: to Stage 3) {S('triage_summary')}.")
        parts = []
        if summ["sicr"]:
            parts.append(f"SICR proposals cover EAD {_m(summ['sicr_ead'])} with ECL +{_m(summ['sicr_ecl'])}")
        if summ["utp"]:
            parts.append(f"UTP proposals cover EAD {_m(summ['utp_ead'])} with ECL +{_m(summ['utp_ecl'])}")
        if parts:
            out.append("; ".join(parts) + f" {S('triage_summary')}.")
        conc = summ.get("concentration") or []
        if conc:
            out.append("The proposals concentrate in " + ", ".join(
                f"{c['segment']} ({c['names']} names, EAD {_m(c['ead'])})" for c in conc) + f" {S('triage_summary')}.")
    elif single and (res.get("triage_decide") or {}).get("by_owner"):
        o, v = next(iter(res["triage_decide"]["by_owner"].items()))
        nm = (w.get("names") or {}).get(o, {}).get("borrower_name")
        out.append(f"{nm + ' (' + o + ')' if nm else o}: {v['label']}.")
        out.append(v["reason"].rstrip(".") + f" {S('crm_assess')}.")
        if v.get("note"):
            who = v["note"]["owner"] + ("" if "branch" in v["note"]["owner"] else f" ({v['note']['owner_role']})")
            out.append(f"Action for {who}: {v['note']['action']}")
    elif w:
        out.append(w.get("summary", "").rstrip(".") + f" {S('ews_warned_names')}.")
    if w.get("budget_skipped"):
        out.append(f"{w['budget_skipped']} warned names were beyond the name budget and are carried to the next run "
                   f"{S('ews_warned_names')}.")
    d = res.get("triage_decide") or {}
    imp = (res.get("ecl_impact") or {}).get("by_owner") or {}
    names = w.get("names") or {}
    top = sorted([o for o, v in (d.get("by_owner") or {}).items() if v["verdict"] in ("utp", "sicr")],
                 key=lambda o: (-dec.RANK[d["by_owner"][o]["verdict"]], -(imp.get(o, {}).get("proposal_move") or 0)))[:5]
    for o in ([] if single else top[:3]) + (top if single else []):
        v, x = d["by_owner"][o], imp.get(o)
        nm = names.get(o, {}).get("borrower_name")
        nm = f"{nm} ({o})" if nm else o
        if x and single:
            out.append(f"EAD {_m(x['ead'])}; ECL move if approved +{_m(x['proposal_move'])} {S('ecl_impact')}.")
        elif x:
            out.append(f"{nm}: {v['label']} on {', '.join(v['articles'])}; EAD {_m(x['ead'])}, ECL move "
                       f"+{_m(x['proposal_move'])} {S('ecl_impact')}.")
        elif not single:
            out.append(f"{nm}: {v['label']} on {', '.join(v['articles'])}.")
    f = res.get("triage_followup") or {}
    if f.get("outcomes"):
        c = f.get("counts") or {}
        out.append("Follow-up: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(c.items()))
                   + f" {S('triage_followup')}.")
        esc = sorted([x for x in f["outcomes"] if x.get("outcome") == "escalated"],
                     key=lambda x: (-["RM", "CREDIT_OFFICER", "CCO"].index(x["escalate_to"]), -x.get("overdue_days", 0)))
        for x in esc[:3]:
            out.append(f"{x.get('borrower_name') or x['borrower_id']} ({x['borrower_id']}) goes to the "
                       f"{x['role_label'].lower()}: the action is {x.get('overdue_days', 0)} days overdue"
                       + (f" and the name worsened from {x['previous']} to {x['current']}" if x.get("worsened") else "")
                       + f" {S('triage_followup')}.")
    n_prop = sum(len((res.get(t) or {}).get("proposals") or []) for t in ("propose_utp", "propose_sicr",
                                                                           "propose_watchlist"))
    if n_prop:
        out.append(f"{n_prop} proposals wait in the approvals queue; no stage was changed {S('triage_summary')}.")
    dup = sum(len((res.get(t) or {}).get("duplicates") or []) for t in ("propose_utp", "propose_sicr",
                                                                         "propose_watchlist"))
    if dup:
        out.append((f"{dup} proposals were" if dup > 1 else "The proposal was") + " already pending from an earlier "
                   f"run and {'were' if dup > 1 else 'was'} not raised again {S('triage_summary')}.")
    return " ".join(x for x in out if x)


# ---------------------------------------------------------------- memory (never the books)

def record(run: Run, w: dict[str, Any], verdicts: dict[str, Any], follow: dict[str, Any],
           names: dict[str, Any]) -> dict[str, Any]:
    domain = w.get("domain") or run.context.get("domain") or "corporate"
    today = str(run.context.get("today") or dt.datetime.now(dt.UTC).date().isoformat())
    created = dt.datetime.now(dt.UTC).isoformat(timespec="microseconds")
    rows = [{"borrower_id": o, "borrower_name": names.get(o, {}).get("borrower_name"), "verdict": v["verdict"],
             "reason": v["reason"], "detail": {"label": v["label"], "articles": v["articles"],
                                               "stage": names.get(o, {}).get("stage")}}
            for o, v in verdicts.items()]
    store.record_verdicts(run.run_id, domain, w.get("period", ""), created, rows)
    open_by = {x["borrower_id"] for x in store.open_actions(domain=domain)}
    notes = 0
    for v in verdicts.values():
        if v.get("note") and v["note"]["borrower_id"] not in open_by:
            store.add_action(run.run_id, domain, v["note"])
            notes += 1
    esc = closed = 0
    for x in follow.get("outcomes") or []:
        if x.get("outcome") == "escalated":
            from backend.agents_v5.ews.followup import LADDER
            store.escalate_action(x["action_id"], level=LADDER.index(x["escalate_to"]), owner_role=x["escalate_to"],
                                  owner=x["owner"], due=x["new_due"], at=today, why=x["why"])
            esc += 1
        for aid in x.get("close") or []:
            store.close_action(aid, at=today, why=x["why"],
                               status="defaulted" if x.get("outcome") == "defaulted" else "cured")
            closed += 1
    notified = _notify_escalations(run, follow.get("outcomes") or [])
    return {"verdicts": len(rows), "notes": notes, "escalated": esc, "closed": closed, "notified": notified}


def _notify_escalations(run: Run, outcomes: list[dict[str, Any]]) -> int:
    """One digest per escalation target through the existing notification path (the bell): who now owns what."""
    from backend.agents_v5.ews.followup import LADDER_LABEL
    from backend.agents_v5.runtime import notify
    sent = 0
    for role in ("CCO", "CREDIT_OFFICER"):
        hits = [x for x in outcomes if x.get("outcome") == "escalated" and x.get("escalate_to") == role]
        if not hits:
            continue
        names = ", ".join(f"{x.get('borrower_name') or x['borrower_id']}" for x in hits[:5])
        more = f" and {len(hits) - 5} more" if len(hits) > 5 else ""
        notify.send(f"Early Warning triage: {len(hits)} overdue or worsening actions escalated to the "
                    f"{LADDER_LABEL[role].lower()}", f"{names}{more}. Open the triage run for the evidence and the actions.",
                    href(run), audience_role=role)
        sent += 1
    return sent


def _applier(kind: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def apply(change: dict[str, Any]) -> dict[str, Any]:
        """An approved proposal is recorded for the staging process. The agent never writes a stage or a flag."""
        with store.db() as con:
            con.execute("UPDATE proposals SET status = 'approved' WHERE borrower_id = ? AND kind = ? "
                        "AND status = 'pending'", [change.get("borrower_id"), kind])
        return {"stage_changed": False, "recorded_for": "the staging process",
                "note": f"{T.TITLE[kind]} approved for {change.get('borrower_name') or change.get('borrower_id')}; "
                        "the official stage is set by the staging process, not by the agent."}
    return apply


def ensure_schedule() -> list[str]:
    """The scheduled runs after each EWS refresh (`@after:ews_refresh`), one per book, created once."""
    from backend.agents_v5.runtime import schedules
    ids = []
    for book in ("corporate", "retail"):
        have = [s for s in schedules.listing(AGENT_ID) if s.get("cron") == "@after:ews_refresh"
                and (s.get("context") or {}).get("domain") == book]
        if have:
            ids.append(str(have[0].get("id")))
            continue
        row = schedules.schedule(AGENT_ID, "@after:ews_refresh", "Triage this period's warnings", {"domain": book},
                                 planner="deterministic", user="system")
        ids.append(str(row.get("id")))
    return ids


DEF: AgentDef | None = None


def _wrapped(t: Tool) -> Tool:
    fn = _stashing(t.fn)
    fn.tool_name = t.name  # type: ignore[attr-defined]
    return Tool(t.name, t.module, t.description, t.input_schema, t.mode, fn, t.available, t.engine)


def register() -> AgentDef:
    global DEF
    for t in TOOLS:
        register_tool(_wrapped(t))
    for kind, k in T.KIND.items():
        register_applier(k, _applier(kind))
    DEF = register_agent(AgentDef(
        spec=spec(), module=MODULE, goal_types=plans.GOAL_TYPES, classify=plans.classify,
        deterministic_plan=plans.deterministic_plan, conclude=conclude, adapt=plans.adapt,
        required_tools=plans.required_tools, scope_of=scope_of, system_prompt=SYSTEM, href=href,
        # R15 L5: a triage run always ends with its proposals and summary, whatever the plan spent on evidence
        closing_tools=CLOSING, closing_reserve=len(CLOSING)))
    return DEF


def run(goal: str = "Triage this period's warnings", context: dict[str, Any] | None = None, *,
        planner: str = "deterministic", trigger: str = "on_demand", user: str = "") -> Run:
    from backend.agents_v5.runtime import start
    if DEF is None:
        register()
    return start(AGENT_ID, goal, dict(context or {}), planner_mode=planner, trigger=trigger, user=user)


__all__ = ["AGENT_ID", "DEF", "TOOLS", "conclude", "ensure_schedule", "narrative", "record", "register", "run",
           "scope_of", "spec"]
