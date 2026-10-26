"""The Lenses monitoring agent's tools on the agents_v5 runtime (A1: the agent plans, engines compute).

Each tool wraps a deterministic engine: the lens engine (DuckDB over the books), the risk-appetite file (read-only), the
CBUAE CRM library and breach checks, the Early Warning release and the What-If Delta method. Each returns a
`ToolResult` with a one-line summary, the `figures` the narrative may cite, the data, and the rows the lens engine
returned (the rows budget). The two proposal-only tools put a change in the approvals queue and change nothing else.

Chaining: the scope is resolved when the plan is made and travels in the run context (`context["scope"]`); later
steps read earlier results through `ctx.results[<tool>]`.
"""
from __future__ import annotations

import re
from typing import Any

from backend.agents_v5.lenses import metrics as M
from backend.agents_v5.lenses import monitor as MON
from backend.agents_v5.lenses import mstore
from backend.agents_v5.lenses import planning as P
from backend.agents_v5.lenses import sources as S
from backend.agents_v5.lenses import thresholds as TH
from backend.agents_v5.runtime import PROPOSAL_ONLY, READ_ONLY, Tool, ToolContext, ToolResult
from backend.lenses_v5 import fmt
from backend.lenses_v5 import planner as lens_planner
from backend.lenses_v5.catalogue import DIMS
from backend.lenses_v5.engine import ENGINE

MODULE = "lenses"
MAX_INVESTIGATE = 6          # alerts investigated per run (A5); the rest are listed with their figures only
APPROVER_ROLE = "RISK_MANAGER"
KIND_SET = "lenses.monitoring_set"
KIND_CHANGES = "lenses.monitoring_changes"


def _schema(**props: Any) -> dict[str, Any]:
    return {"type": "object", "properties": props}


class _Rows:
    """Counts the rows the lens engine returns during one tool call (charged to the run's rows budget)."""

    def __enter__(self):
        self.rows = 0
        self._orig = ENGINE.q
        me = self

        def q(sql: str):
            out = me._orig(sql)
            me.rows += len(out)
            return out
        ENGINE.q = q  # type: ignore[method-assign]
        return self

    def __exit__(self, *exc):
        ENGINE.q = self._orig  # type: ignore[method-assign]


def _label_numbers(*texts: str) -> list[float]:
    """Numbers that are part of names ("Average PD (12m)", "Top 20 obligors"): the tool output carries them, so the
    citation check can tell a label from a figure."""
    out: list[float] = []
    for t in texts:
        out += [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t or "")]
    return out


period_label = MON.period_label


# ------------------------------------------------------------------ scope
def scope_key(book: str, filters: list[dict[str, Any]], lens_id: str = "") -> str:
    if lens_id:
        return f"lens:{lens_id}"
    parts = [f"{f['dim']}={'|'.join(sorted(f['values']))}" for f in sorted(filters, key=lambda f: f["dim"])]
    return f"{book}:" + (";".join(parts) or "all")


def resolve_scope(goal: str, ctx: dict[str, Any]) -> dict[str, Any]:
    """The book, segment filters or lens the goal is about (the lens planner's own detectors; a lens id wins)."""
    lens_id = str(ctx.get("lens_id") or "")
    kpis: list[str] = []
    name = ""
    if lens_id:
        from backend.lenses_v5.store import Store
        st = Store()
        lens = st.lens(lens_id)
        if lens is None:
            raise ValueError(f"Lens {lens_id} does not exist.")
        spec = st.spec(lens_id)
        book, filters, kpis, name = spec["book"], spec.get("filters") or [], spec.get("kpis") or [], lens["name"]
    elif ctx.get("book") in ("corporate", "retail") and isinstance(ctx.get("filters"), list):
        book, filters = ctx["book"], [f for f in ctx["filters"] if isinstance(f, dict) and f.get("dim") and f.get("values")]
        ENGINE.where(book, filters)
    else:
        book = lens_planner.detect_book(goal, default=str(ctx.get("book") or "corporate"))
        filters = lens_planner.detect_filters(goal, book)
    period = str(ctx.get("period") or "")
    if period not in ENGINE.periods(book):
        period = ENGINE.as_of(book)
    return {"book": book, "filters": filters, "scope_key": scope_key(book, filters, lens_id), "label": lens_planner.scope_label(book, filters),
            "lens_id": lens_id, "lens_name": name, "lens_kpis": kpis, "period": period}


def _scope(ctx: ToolContext) -> dict[str, Any]:
    sc = ctx.context.get("scope")
    if not sc:
        goal = str(ctx.context.get("goal") or "")
        if not goal and ctx.run_id:
            from backend.agents_v5.runtime import store
            r = store.load_run(ctx.run_id)
            goal = r.goal if r else ""
        sc = resolve_scope(goal, ctx.context)
        ctx.context["scope"] = sc
    return sc


def t_scope(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    return ToolResult(summary=f"Scope: {sc['label']}" + (f" (lens {sc['lens_name']})" if sc["lens_name"] else "")
                      + f", as of {period_label(sc['period'])}.", data=sc, figures={})


# ------------------------------------------------------------------ the five sources
def t_composition(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    with _Rows() as r:
        c = S.composition(sc["book"], sc["filters"], sc["period"])
    tops = ", ".join(f"{s['segment']} {fmt.pct(s['share'])}" for s in c["top_segments"][:3])
    grow = ", ".join(f"{s['segment']} {s['growth_4q']:+.1f}%" for s in c["growth_segments"])
    summ = f"Largest {DIMS[c['segment_dim']].label.lower()}s: {tops}." + (f" Growing faster than the scope ({c['book_growth_4q']:+.1f}%): {grow}." if grow else "")
    figs = {"book_growth_4q": c["book_growth_4q"], "ead": c["ead"], **{f"share.{s['segment']}": s["share"] for s in c["top_segments"]},
            **{f"growth.{s['segment']}": s["growth_4q"] for s in c["growth_segments"]}}
    return ToolResult(summary=summ, figures=figs, data=c, rows_scanned=r.rows)


def t_appetite(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    a = S.appetite(sc["book"])
    return ToolResult(summary=f"{len(a['measurable'])} portfolio limits measurable on the books; {len(a['skipped'])} rows are deal-level "
                              f"or need data the books do not carry.",
                      figures={"measurable": len(a["measurable"]), "skipped": len(a["skipped"]),
                               **{f"limit.{x['row']}": x["limit"] for x in a["measurable"]}, **{f"trigger.{x['row']}": x["trigger"] for x in a["measurable"]}},
                      data=a)


def t_regulation(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    with _Rows() as r:
        g = S.regulation(sc["book"], sc["period"])
    br = [c for c in g["checks"] if c["breaches"]]
    summ = (f"{len(g['metrics'])} CRM library metrics measurable; {len(br)} of {len(g['checks'])} CRM checks in breach now"
            + (f" ({', '.join(c['check_id'] + ' ' + fmt.count(c['breaches']) for c in br[:3])})." if br else "."))
    figs = {"metrics": len(g["metrics"]), "checks": len(g["checks"]), "in_breach": len(br), **{f"breaches.{c['check_id']}": c["breaches"] for c in g["checks"]}}
    return ToolResult(summary=summ, figures=figs, data=g, rows_scanned=r.rows)


def t_movement(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    with _Rows() as r:
        m = S.movement(sc["book"], sc["filters"], sc["period"])
    summ = "Largest unusual moves: " + ", ".join(f"{x['label']} ({x['z']:+.1f} sd)" for x in m["top_movers"][:3]) + "."
    return ToolResult(summary=summ, figures={f"z.{x['metric']}": x["z"] for x in m["top_movers"]}, data=m, rows_scanned=r.rows)


def t_candidates(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    res = ctx.results
    empty: dict[str, Any] = {"measurable": [], "skipped": [], "metrics": [], "checks": [], "top_movers": [], "top_segments": [],
                             "growth_segments": [], "segment_dim": S.segment_dim(sc["book"], sc["filters"]), "period": sc["period"], "book_growth_4q": 0}
    with _Rows() as r:
        cs = P.candidates(sc["book"], sc["filters"], res.get("lenses_composition") or empty, res.get("lenses_risk_appetite") or empty,
                          res.get("lenses_regulation") or empty, res.get("lenses_movement") or empty, sc.get("lens_kpis"))
    by: dict[str, int] = {}
    for c in cs:
        for s in c["sources"]:
            by[s] = by.get(s, 0) + 1
    missing = [t for t in ("lenses_composition", "lenses_risk_appetite", "lenses_regulation", "lenses_movement") if t not in res]
    summ = f"{len(cs)} candidate metrics (" + ", ".join(f"{k} {v}" for k, v in sorted(by.items())) + ")." + \
        (f" Not read in this run: {', '.join(missing)}." if missing else "")
    return ToolResult(summary=summ, figures={"candidates": len(cs), **{f"from.{k}": v for k, v in by.items()}}, data={"candidates": cs, "by_source": by},
                      rows_scanned=r.rows)


def t_materiality(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    cands = (ctx.results.get("lenses_candidates") or {}).get("candidates", [])
    out = {}
    with _Rows() as r:
        for c in cands:
            out[c["def"]["key"]] = M.at_stake(M.from_dict(c["def"]), sc["period"])
    lab = {c["def"]["key"]: c["def"]["label"] for c in cands}
    big = sorted([kv for kv in out.items() if max(kv[1]["ead"], kv[1]["ecl"]) < 0.99], key=lambda kv: -max(kv[1]["ead"], kv[1]["ecl"]))[:3]
    summ = "Most material segments: " + ", ".join(f"{lab[k]} ({fmt.pct(v['ead'] * 100)} of EAD, {fmt.pct(v['ecl'] * 100)} of ECL)" for k, v in big) + "."
    return ToolResult(summary=summ, figures={f"{k}.{x}": v[x] for k, v in out.items() for x in ("ead", "ecl")}, data={"at_stake": out},
                      rows_scanned=r.rows)


def t_backtest(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    cands = (ctx.results.get("lenses_candidates") or {}).get("candidates", [])
    with _Rows() as r:
        out = [P.assess(c, sc["period"], {}) for c in cands]
    noise: dict[str, int] = {}
    for a in out:
        noise[a["noise"]] = noise.get(a["noise"], 0) + 1
    summ = f"Back-tested {len(out)} thresholds over 8 quarters: " + ", ".join(f"{v} {k}" for k, v in sorted(noise.items())) + "."
    return ToolResult(summary=summ, figures={"tested": len(out), **{f"noise.{k}": v for k, v in noise.items()}},
                      data={"assessed": out, "noise": noise}, rows_scanned=r.rows)


def metric_figures(m: dict[str, Any]) -> dict[str, Any]:
    """Every number the rationale and threshold text of a proposed metric show."""
    f: dict[str, Any] = {"now": m.get("now"), "value": m.get("value"), "fired": m["backtest"]["fired"], "quarters": m["backtest"]["quarters"],
                         "rate": m["backtest"]["rate"], "ead_share": m["at_stake"]["ead"], "ecl_share": m["at_stake"]["ecl"],
                         "labels": _label_numbers(m["label"]), "seed": m.get("seed_figures") or {}, "z": m.get("z_last"),
                         "history": m["threshold"].get("history")}
    if m.get("now") is not None and m.get("prev") is not None:
        f["change"] = m["now"] - m["prev"]
        if m["prev"]:
            f["change_rel"] = (m["now"] - m["prev"]) / abs(m["prev"]) * 100
    for k in ("k", "level", "trigger", "limit"):
        if k in m["threshold"]:
            f[f"threshold_{k}"] = m["threshold"][k]
    return f


def t_rank(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    assessed = (ctx.results.get("lenses_backtest") or {}).get("assessed", [])
    max_set = int(inputs.get("max_set") or P.MAX_SET)
    kept, dropped = P.rank(assessed, max_set)
    final = P.finalise(kept)
    for m, c in zip(final, kept, strict=True):
        m["prev"] = c["prev"]
    same = sum(1 for d in dropped if d["reason"] == "same_signal")
    corr = sum(1 for d in dropped if d["reason"] == "correlated")
    figs: dict[str, Any] = {"kept": len(final), "dropped": len(dropped), "same_signal": same, "correlated": corr, "below_cut": len(dropped) - same - corr,
                            "redundant": same + corr}
    for m in final:
        figs[f"#{m['rank']}"] = metric_figures(m)
    for d in dropped:
        if d.get("correlation") is not None:
            figs[f"corr.{d['key']}"] = d["correlation"]
    return ToolResult(summary=f"Kept {len(final)} metrics; dropped {same} with the same signal, {corr} correlated and "
                              f"{len(dropped) - same - corr} below the cut.", figures=figs, data={"set": final, "dropped": dropped})


def _lite(m: dict[str, Any]) -> dict[str, Any]:
    keep = ("key", "rank", "label", "unit", "book", "def", "definition", "scope", "frequency", "threshold", "threshold_text", "threshold_how",
            "why", "sources", "backtest", "noise", "expected_alert_rate", "value", "value_parts", "now", "now_display", "at_stake", "appetite",
            "regulation", "status", "series", "prev")
    return {k: m.get(k) for k in keep}


def schedule_text(book: str) -> str:
    return "quarterly, after each corporate quarter-end release" if book == "corporate" else "monthly, after each retail month-end release"


def t_propose_set(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    r = ctx.results.get("lenses_rank") or {}
    ms = r.get("set") or []
    if not ms:
        return ToolResult(summary="Nothing to propose: no metric made the set.")
    payload = {"scope": {k: sc.get(k) for k in ("book", "filters", "scope_key", "label", "lens_id", "lens_name", "period")},
               "label": f"Monitoring: {sc.get('lens_name') or sc['label']}", "metrics": [_lite(m) for m in ms],
               "dropped": [{k: d.get(k) for k in ("key", "label", "reason", "why", "value", "kept", "correlation")} for d in r.get("dropped") or []],
               "skipped_appetite": (ctx.results.get("lenses_risk_appetite") or {}).get("skipped", [])}
    p = mstore.get().add_proposal(kind="monitoring_set", scope_key=sc["scope_key"], payload=payload, run_id=ctx.run_id,
                                  requested_by=ctx.user, approver_role=APPROVER_ROLE)
    change = {"proposal_id": p["proposal_id"], "scope_key": sc["scope_key"], "label": payload["label"], "metrics": len(ms),
              "lens": "create or update the monitoring lens", "schedule": schedule_text(sc["book"])}
    return ToolResult(summary=f"Proposed {len(ms)} metrics for approval; nothing changes until a risk approver accepts them.",
                      figures={"metrics": len(ms)}, data={"proposal_id": p["proposal_id"], "payload_metrics": len(ms)},
                      proposal={"kind": KIND_SET, "title": f"Monitoring set: {len(ms)} metrics for {sc['label']}", "change": change,
                                "approver_role": APPROVER_ROLE, "expires_hours": 7 * 24, "risk": "low",
                                "reason": "Approval creates or updates the monitoring lens and its schedule."})


# ------------------------------------------------------------------ the scheduled run
def t_load_set(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    s = mstore.get().active_set(sc["scope_key"])
    if s is None:
        return ToolResult(summary="No approved monitoring set for this scope yet: set one up first.", data={"set": None, "metrics": []},
                          figures={"metrics": 0})
    ms = [m for m in s["metrics"] if m.get("status") != "rejected"]
    return ToolResult(summary=f"Active set v{s['version']}: {len(ms)} metrics.", figures={"metrics": len(ms), "version": s["version"]},
                      data={"set": {k: s[k] for k in ("set_id", "label", "lens_id", "version", "book", "filters", "created_by", "approved_by")},
                            "metrics": ms})


def t_compute(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    ls = ctx.results.get("lenses_load_set") or {}
    with _Rows() as r:
        cm = MON.compute(ls.get("metrics") or [], sc["period"])
    figs: dict[str, Any] = {}
    for c in cm:
        f: dict[str, Any] = {"value": c["value"], "labels": _label_numbers(c["label"])}
        if c["value"] is not None and c["prev"] is not None:
            f["change"] = c["value"] - c["prev"]
            if c["prev"]:
                f["change_rel"] = (c["value"] - c["prev"]) / abs(c["prev"]) * 100
        for k in ("k", "level", "trigger", "limit"):
            if k in c["threshold"]:
                f[k] = c["threshold"][k]
        ev = c["evaluation"]
        if ev.get("measure") is not None:
            f["measure"] = ev["measure"]
        figs[c["key"]] = f
    return ToolResult(summary=f"Computed {len(cm)} metrics as of {period_label(cm[0]['period']) if cm else period_label(sc['period'])}.",
                      figures=figs, data={"computed": cm}, rows_scanned=r.rows)


def t_detect(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ls = ctx.results.get("lenses_load_set") or {}
    cm = (ctx.results.get("lenses_compute") or {}).get("computed", [])
    sid = (ls.get("set") or {}).get("set_id", "")
    hist = {c["key"]: mstore.get().alert_history(sid, c["key"]) for c in cm} if sid else {}
    alerts = MON.detect(cm, hist)
    todo = [a for a in alerts if a["status"] in ("new", "worsened")]
    inv, over = todo[:MAX_INVESTIGATE], todo[MAX_INVESTIGATE:]
    high = sum(1 for a in alerts if a["severity"] == "high")
    summ = (f"{len(alerts)} of {len(cm)} metrics past their threshold ({high} high)" + (f"; investigating {len(inv)}" if inv else "")
            + (f" ({len(over)} over the per-run budget)" if over else "") + ".")
    return ToolResult(summary=summ, figures={"alerts": len(alerts), "metrics": len(cm), "high": high, "investigate": len(inv), "over_budget": len(over),
                                             "new": sum(1 for a in alerts if a["status"] == "new")},
                      data={"alerts": alerts, "investigate": [a["key"] for a in inv], "not_investigated": [a["key"] for a in over]})


def _alert(ctx: ToolContext, key: str) -> dict[str, Any]:
    for a in (ctx.results.get("lenses_detect") or {}).get("alerts", []):
        if a["key"] == key:
            return a
    raise ValueError(f"No alert {key} in this run.")


def _rows_figs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {f"{i}.{k}": r.get(k) for i, r in enumerate(rows) for k in ("contribution", "numerator_part", "denominator_part", "now_bps", "before_bps")
            if r.get(k) is not None}


def t_decompose(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    a = _alert(ctx, str(inputs.get("alert") or ""))
    by = str(inputs.get("by") or "segment")
    with _Rows() as r:
        d = MON.decompose(a, by)
    u = d.get("unit_of_contribution", a["unit"])
    summ = f"{a['label']} by {d['by'].replace('_', ' ')}: " + (", ".join(f"{x['name']} {MON._c(x['contribution'], u)}" for x in d["rows"][:2])  # noqa: SLF001
                                                              or "no movement") + "."
    figs = {"total": d.get("total"), "sum_of_parts": d.get("sum_of_parts"), **_rows_figs(d.get("rows", [])),
            "labels": _label_numbers(*[x["name"] for x in d.get("rows", [])])}
    return ToolResult(summary=summ, figures=figs, data={**d, "alert": a["key"], "kind": inputs.get("by") or "segment"}, rows_scanned=r.rows)


def t_driver(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    a = _alert(ctx, str(inputs.get("alert") or ""))
    with _Rows() as r:
        d = MON.driver(a)
    if not d.get("available"):
        return ToolResult(summary=f"{a['label']} is not a ratio: no numerator and denominator split.", data={**d, "alert": a["key"]}, rows_scanned=r.rows)
    return ToolResult(summary=f"{a['label']}: numerator {MON._c(d['numerator_part'], a['unit'])}, denominator {MON._c(d['denominator_part'], a['unit'])}.",  # noqa: SLF001
                      figures={k: d[k] for k in ("numerator_part", "denominator_part", "numerator_change", "denominator_change")},
                      data={**d, "alert": a["key"]}, rows_scanned=r.rows)


def t_ews(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    a = _alert(ctx, str(inputs.get("alert") or ""))
    with _Rows() as r:
        bor = MON.decompose(a, "borrower")
        e = MON.ews_read(a, [x["key"] for x in bor.get("rows", [])])
    summ = f"Early Warning on the names behind {a['label']}: {e.get('warned', 0)} of {e.get('of', 0)} warned." if e.get("names") else "No names to read."
    return ToolResult(summary=summ, figures={"warned": e.get("warned", 0), "of": e.get("of", 0),
                                             **{f"score.{n['owner_id']}": n["score"] for n in e.get("names", [])}},
                      data={**e, "alert": a["key"]}, rows_scanned=r.rows)


def t_whatif(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    a = _alert(ctx, str(inputs.get("alert") or ""))
    with _Rows() as r:
        seg = str(inputs.get("segment") or "")
        if not seg:
            rows = [x for x in MON.decompose(a, "segment").get("rows", []) if (x.get("contribution") or 0) > 0]
            seg = rows[0]["key"] if rows else ""
        w = MON.whatif_read(a, seg)
    if not (w.get("available") and w.get("uplift") is not None):
        return ToolResult(summary="No segment to stress.", data={**w, "alert": a["key"]}, rows_scanned=r.rows)
    return ToolResult(summary=f"PD +20% on {w['segment']} adds {fmt.amount(w['uplift'])} of ECL (What-If Delta method).",
                      figures={"uplift": w["uplift"], "ecl": w["ecl"], "pd_shock_pct": 20}, data={**w, "alert": a["key"]}, rows_scanned=r.rows)


def t_notify(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from backend.agents_v5.lenses import agent
    out = agent.record_and_notify(ctx)
    return ToolResult(summary=out["summary"], figures={"recorded": out["recorded"], "fresh": out["fresh"], "notified": out["notified"]}, data=out)


def t_review(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    ls = ctx.results.get("lenses_load_set") or {}
    sid = (ls.get("set") or {}).get("set_id", "")
    hist = {m["key"]: mstore.get().alert_history(sid, m["key"]) for m in ls.get("metrics") or []} if sid else {}
    with _Rows() as r:
        changes = MON.review(ls.get("metrics") or [], hist, sc["period"])
    ret = sum(1 for c in changes if c["action"] == "retire")
    figs = {"retire": ret, "rethreshold": len(changes) - ret,
            **{f"{c['key']}.fired": c["evidence"]["backtest"]["fired"] for c in changes},
            **{f"{c['key']}.new_fired": c["evidence"]["new_backtest"]["fired"] for c in changes if c["evidence"].get("new_backtest")}}
    return ToolResult(summary=f"{ret} to retire, {len(changes) - ret} to re-threshold.", figures=figs, data={"changes": changes}, rows_scanned=r.rows)


def t_propose_changes(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    sc = _scope(ctx)
    ls = ctx.results.get("lenses_load_set") or {}
    changes = (ctx.results.get("lenses_review") or {}).get("changes") or []
    if not changes or not ls.get("set"):
        return ToolResult(summary="Nothing to change in the set.")
    payload = {"scope": {k: sc.get(k) for k in ("book", "filters", "scope_key", "label", "lens_id", "period")}, "set_id": ls["set"]["set_id"],
               "changes": [{**c, "status": "proposed"} for c in changes]}
    p = mstore.get().add_proposal(kind="monitoring_changes", scope_key=sc["scope_key"], payload=payload, run_id=ctx.run_id,
                                  requested_by=ctx.user or "scheduler", approver_role=APPROVER_ROLE, set_id=ls["set"]["set_id"])
    ret = sum(1 for c in changes if c["action"] == "retire")
    return ToolResult(summary=f"Proposed {len(changes)} changes to the set for approval.", figures={"changes": len(changes)},
                      data={"proposal_id": p["proposal_id"]},
                      proposal={"kind": KIND_CHANGES, "title": f"Monitoring set changes for {sc['label']}: retire {ret}, re-threshold {len(changes) - ret}",
                                "change": {"proposal_id": p["proposal_id"], "scope_key": sc["scope_key"], "set_id": ls["set"]["set_id"],
                                           "changes": [{"action": c["action"], "label": c["label"]} for c in changes]},
                                "approver_role": APPROVER_ROLE, "expires_hours": 7 * 24, "risk": "low",
                                "reason": "Metrics that never fire or fire constantly, with their back-test evidence."})


def rebacktest(metric: dict[str, Any], threshold: dict[str, Any]) -> dict[str, Any]:
    """An edited threshold is back-tested at once (the panel shows the new alert rate before approval)."""
    d = M.from_dict(metric["def"])
    g = M.grid(d.book, ENGINE.as_of(d.book), n=17)
    s, _ = M.series(d, g)
    bt = TH.backtest(g, s, threshold, d.unit)
    return {"threshold": threshold, "threshold_text": TH.describe(threshold, d.unit), "backtest": bt, "noise": TH.noise(bt), "expected_alert_rate": bt["rate"]}


ALERT_IN = _schema(alert={"type": "string", "description": "the alert's metric key from lenses_detect"})
TOOLS: tuple[Tool, ...] = (
    Tool("lenses_scope", MODULE, "Resolve the goal's scope: the book, a segment or sector, or an existing lens (its scope and KPIs).", _schema(), READ_ONLY,
         t_scope, engine="backend.lenses_v5.planner (detect_book, detect_filters), Lenses store"),
    Tool("lenses_composition", MODULE, "Concentrations, large exposures and growth segments of the scope.", _schema(), READ_ONLY, t_composition,
         engine="lens engine (DuckDB over the books)"),
    Tool("lenses_risk_appetite", MODULE, "Risk-appetite limits and triggers the books can measure (Deal Desk risk_appetite.json, read-only).", _schema(),
         READ_ONLY, t_appetite, engine="data/dealdesk/params/v1/risk_appetite.json"),
    Tool("lenses_regulation", MODULE, "CBUAE CRM library metrics the catalogue measures and the CRM breach checks now.", _schema(), READ_ONLY, t_regulation,
         engine="backend.lenses_v5.crm_intel, backend.regulatory.crm_checks"),
    Tool("lenses_movement", MODULE, "Which catalogue metrics moved most last quarter (z-score against their last 8 moves) and which are volatile.",
         _schema(), READ_ONLY, t_movement, engine="lens engine"),
    Tool("lenses_candidates", MODULE, "Candidate metrics from composition, risk appetite, regulation, movement and the lens's own KPIs.", _schema(),
         READ_ONLY, t_candidates, engine="backend.agents_v5.lenses.planning"),
    Tool("lenses_materiality", MODULE, "The share of EAD and ECL each candidate speaks for.", _schema(), READ_ONLY, t_materiality, engine="lens engine"),
    Tool("lenses_backtest", MODULE, "Pick each candidate's threshold (absolute, change, z-score or risk-appetite distance) and back-test it over 8 quarters.",
         _schema(), READ_ONLY, t_backtest, engine="backend.agents_v5.lenses.thresholds over the lens engine"),
    Tool("lenses_rank", MODULE, "Rank by value (materiality, appetite, regulation, movement, signal quality) and drop redundant metrics with the reason.",
         _schema(max_set={"type": "integer", "minimum": 3, "maximum": 20}), READ_ONLY, t_rank, engine="backend.agents_v5.lenses.planning"),
    Tool("lenses_propose_set", MODULE, "Put the ranked monitoring set in the approvals queue; approval creates or updates the lens and its schedule.",
         _schema(), PROPOSAL_ONLY, t_propose_set, engine="approvals queue"),
    Tool("lenses_load_set", MODULE, "Load the approved monitoring set for the scope.", _schema(), READ_ONLY, t_load_set, engine="monitoring store"),
    Tool("lenses_compute", MODULE, "Compute every monitored metric now and evaluate its threshold.", _schema(), READ_ONLY, t_compute, engine="lens engine"),
    Tool("lenses_detect", MODULE, "Detect material moves (thresholds that fire); new and worsened ones are investigated.", _schema(), READ_ONLY, t_detect,
         engine="backend.agents_v5.lenses.thresholds"),
    Tool("lenses_decompose", MODULE, "Decompose an alert's change by segment, rating or borrower (exactly additive where the metric is).",
         _schema(alert={"type": "string"}, by={"type": "string", "enum": ["segment", "rating", "borrower", "sector", "region", "rm_name", "rating_current"]}),
         READ_ONLY, t_decompose, engine="lens engine"),
    Tool("lenses_driver", MODULE, "Split an alert's change into numerator and denominator effects.", ALERT_IN, READ_ONLY, t_driver, engine="lens engine"),
    Tool("lenses_ews_read", MODULE, "Early Warning band, score and reasons of the names behind an alert.", ALERT_IN, READ_ONLY, t_ews,
         engine="Early Warning release (enriched relation in the lens engine)"),
    Tool("lenses_whatif_read", MODULE, "What-If Delta read: the ECL uplift at PD +20% of the segment behind an alert.",
         _schema(alert={"type": "string"}, segment={"type": "string"}), READ_ONLY, t_whatif, engine="What-If Delta method (catalogue ecl_pd20_uplift)"),
    Tool("lenses_notify", MODULE, "Record the alerts with their explanations on the Monitoring agent panel and notify the set's owner and approver.",
         _schema(), READ_ONLY, t_notify, engine="monitoring store, notifications (Workspace inbox, the bell)"),
    Tool("lenses_review", MODULE, "Find metrics that never fire or fire constantly and work out a retire or re-threshold with evidence.", _schema(),
         READ_ONLY, t_review, engine="backend.agents_v5.lenses.monitor"),
    Tool("lenses_propose_changes", MODULE, "Put retire and re-threshold changes in the approvals queue.", _schema(), PROPOSAL_ONLY, t_propose_changes,
         engine="approvals queue"),
)
