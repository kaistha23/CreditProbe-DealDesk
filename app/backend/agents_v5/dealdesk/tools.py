"""The Committee Preparation agent's tools: each wraps one Deal Desk or R11 engine route (A1).

Read-only tools return the engine's output (`data`), a one-line summary and the named figures the
narrative may cite. The two proposal-only tools queue a change for a person (A4).
"""
from __future__ import annotations

from typing import Any

from backend.agents_v5.dealdesk import engines as E
from backend.agents_v5.runtime import (
    NOT_AVAILABLE,
    PROPOSAL_ONLY,
    READ_ONLY,
    Tool,
    ToolContext,
    ToolResult,
    ToolUnavailable,
    register_tool,
)

MODULE = "dealdesk"
PID = {"type": "object", "properties": {"proposal_id": {"type": "string", "description": "DD-xx, an uploaded id, or a "
                                                         "prepared case id (PRP-A-GMC, PRP-B-ASB)"}},
       "required": ["proposal_id"]}


def _with(extra: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": {**PID["properties"], **extra}, "required": ["proposal_id"]}


def _pid(inputs: dict[str, Any], ctx: ToolContext) -> str:
    pid = str(inputs.get("proposal_id") or ctx.context.get("proposal_id") or "").strip()
    if not pid:
        raise ValueError("proposal_id is required.")
    return pid


def _route(method: str, template: str):
    def probe() -> tuple[bool, str]:
        return (True, "") if E.has_route(method, template) else (False, NOT_AVAILABLE)
    return probe


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    try:
        return E.call(method, path, body)
    except E.EngineError as e:
        if e.status == 404 and "Not Found" in e.detail:
            raise ToolUnavailable(NOT_AVAILABLE) from None
        if e.status == 503:
            raise ToolUnavailable(f"{NOT_AVAILABLE} ({e.detail})") from None
        raise


def is_case(pid: str) -> bool:
    return pid.upper().startswith("PRP-")


#: the ask's facility type -> the book products it renews
RENEWS = {"trade_lc": ("trade_finance",), "revolver": ("revolving_credit", "working_capital"),
          "term_loan": ("term_loan",), "working_capital": ("working_capital", "revolving_credit"),
          "lg": ("guarantee", "trade_finance"), "performance_lg": ("guarantee", "trade_finance")}


def renewed_facilities(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Existing facilities of the same family as the ask: what a renewal replaces."""
    fam = RENEWS.get(str(p["ask"].get("facility_type") or ""), ())
    return [f for f in p["obligor"].get("existing_facilities") or [] if f.get("product") in fam]


def recommended_terms(ctx: ToolContext) -> dict[str, Any] | None:
    o = ctx.results.get("dd_optimise") or {}
    rec = o.get("closest") or o.get("max_sva")
    return dict(rec["terms"]) if rec and rec.get("terms") else None


# ------------------------------------------------------------------ ingest and extract

def ingest(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    if is_case(pid):
        subs = _call("get", "/review/r11/subjects")["subjects"]
        s = next((x for x in subs if x["id"] == pid), None)
        if s is None:
            raise KeyError(f"No prepared case {pid}.")
        return ToolResult(summary=f"Prepared case {s['name']}: {s['currency']} {s['amount']:,.1f}m, {s['sector']}, "
                                  f"rating {s['rating']}",
                          figures={"amount": s["amount"]},
                          data={"kind": "case", "proposal_id": pid, "name": s["name"], "sector": s["sector"],
                                "rating": s["rating"], "amount": s["amount"], "currency": s["currency"],
                                "existing": True, "existing_facilities": 0, "purpose": "", "renewal": False,
                                "file": s.get("file")})
    p = _call("get", f"/proposals/{pid}")["proposal"]
    o, ask = p["obligor"], p["ask"]
    facs = o.get("existing_facilities") or []
    purpose = str(p.get("purpose") or "")
    renewal = bool(o.get("existing")) and (bool(renewed_facilities(p)) or "renew" in purpose.lower())
    data = {"kind": "dd", "proposal_id": pid, "name": o["name"], "obligor_id": o.get("obligor_id"),
            "sector": o.get("sector"), "rating": o.get("internal_rating"), "existing": bool(o.get("existing")),
            "existing_facilities": len(facs), "existing_exposure_sar_mn": o.get("existing_exposure_sar_mn") or 0.0,
            "renewal": renewal, "purpose": purpose, "status": p.get("status"), "rm": p.get("rm"),
            "currency": ask.get("currency"), "amount": ask.get("amount"), "tenor_years": ask.get("tenor_years"),
            "facility_type": ask.get("facility_type"), "structure": ask.get("structure"),
            "margin_bps": ask.get("margin_bps"), "group": o.get("group_name"), "simah_flag": o.get("simah_flag"),
            "ask": ask, "memo": p.get("memo")}
    who = "existing client" if data["existing"] else "new to bank"
    return ToolResult(summary=f"{o['name']} ({who}, {o.get('sector')}, {o.get('internal_rating')}): "
                              f"{ask.get('currency')} {ask.get('amount')}m {str(ask.get('facility_type')).replace('_', ' ')}"
                              f" over {ask.get('tenor_years')} years",
                      figures={"amount": ask.get("amount"), "tenor_years": ask.get("tenor_years"),
                               "margin_bps": ask.get("margin_bps"),
                               "existing_exposure_sar_mn": data["existing_exposure_sar_mn"],
                               "existing_facilities": len(facs)},
                      data=data)


# ------------------------------------------------------------------ spreading and financials

def spreading(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    p = _call("get", f"/proposals/{pid}")["proposal"]
    years = [y for y in (p.get("financials") or {}).get("years", []) if isinstance(y, dict)]
    if not years:
        raise ValueError("The proposal has no financials to spread.")
    rows = []
    for y in years:
        r = {k: y.get(k) for k in ("year", "kind", "revenue", "ebitda", "total_debt", "debt_service", "net_worth",
                                   "current_ratio")}
        r["ebitda_margin"] = (y["ebitda"] / y["revenue"]) if y.get("revenue") else None
        r["debt_ebitda"] = (y["total_debt"] / y["ebitda"]) if y.get("ebitda") else None
        r["dscr"] = (y["ebitda"] / y["debt_service"]) if y.get("debt_service") else None
        rows.append(r)
    actual = [r for r in rows if r.get("kind") in (None, "actual", "audited")] or rows
    last = actual[-1]
    first = actual[0]
    growth = (last["revenue"] / first["revenue"]) ** (1 / max(1, len(rows) - 1)) - 1 if first.get("revenue") else None
    figs = {"revenue": last["revenue"], "ebitda": last["ebitda"], "ebitda_margin": last["ebitda_margin"],
            "debt_ebitda": last["debt_ebitda"], "dscr": last["dscr"], "revenue_cagr": growth,
            "year": last["year"]}
    return ToolResult(summary=f"{len(rows)} years spread ({len(actual)} actual to {last['year']}); latest revenue "
                              f"{last['revenue']:,.1f}m, EBITDA margin {last['ebitda_margin']:.1%}, "
                              f"Debt/EBITDA {last['debt_ebitda']:.2f}x",
                      figures={k: v for k, v in figs.items() if v is not None},
                      data={"years": rows, "unit": (p.get("financials") or {}).get("unit"),
                            "source": years[-1].get("source")})


# ------------------------------------------------------------------ conduct (existing borrowers)

def conduct(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    from backend.dealdesk import review_facts as RF
    f = RF.facts(pid)
    book = f.get("book")
    if not book:
        return ToolResult(summary="No facilities in the corporate book for this obligor", figures={},
                          data={"book": None})
    figs = {k: book.get(k) for k in ("ead", "stage_max", "dpd_max_4q", "limit", "utilisation") if
            isinstance(book.get(k), (int, float))}
    return ToolResult(summary=f"Book: EAD {book.get('ead', 0):,.2f}m, highest stage {book.get('stage_max')}, "
                              f"max DPD over 4 quarters {book.get('dpd_max_4q')} days",
                      figures=figs, data={"book": book, "conduct": f.get("conduct"), "bureau": f.get("bureau")},
                      rows_scanned=int(book.get("rows", 0) or 0))


def last_approval(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Renewal: the ask against the facilities approved last time (the book's existing facilities)."""
    pid = _pid(inputs, ctx)
    p = _call("get", f"/proposals/{pid}")["proposal"]
    facs = renewed_facilities(p) or p["obligor"].get("existing_facilities") or []
    if not facs:
        return ToolResult(summary="No earlier approval on record", data={"facilities": []})
    lim = sum(float(x.get("limit") or 0) for x in facs)
    ead = sum(float(x.get("ead") or 0) for x in facs)
    ask = float(p["ask"].get("amount") or 0)
    return ToolResult(summary=f"Last approval: {len(facs)} facilities of this kind, limits {lim:,.1f}m (EAD {ead:,.1f}m); "
                              f"the ask is {ask:,.1f}m ({(ask / lim - 1) if lim else 0:+.0%} on the approved limits)",
                      figures={"approved_limits": lim, "approved_ead": ead, "ask": ask,
                               "change_vs_limits": (ask / lim - 1) if lim else 0.0, "facilities": len(facs)},
                      data={"facilities": facs})


# ------------------------------------------------------------------ analysis and Optimise

def analysis(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {"proposal_id": pid}
    if inputs.get("terms"):
        body["terms"] = inputs["terms"]
    a = _call("post", "/compute", body)
    m, ap = a["metrics"], a.get("approval") or {}
    hard = list(ap.get("hard_breaches") or [])
    return ToolResult(summary=f"As asked: RAROC {m['lifetime_raroc']:.1%} vs hurdle {m['hurdle']:.1%}, SVA "
                              f"{m['sva']:,.2f}m, RWA {m['rwa_y1']:,.1f}m; approval at {ap.get('level')}"
                              + (f"; hard breaches: {', '.join(hard)}" if hard else ""),
                      figures={k: m.get(k) for k in ("lifetime_raroc", "hurdle", "sva", "rwa_y1", "day_one_ecl",
                                                     "pd_12m", "dscr_post", "debt_ebitda_post", "ltv",
                                                     "breakeven_margin_bps", "amount_sar_mn", "el_y1")
                               if isinstance(m.get(k), (int, float))},
                      data={"metrics": m, "approval": ap, "terms": a.get("terms"), "hard_breaches": hard},
                      trace_id=a.get("trace_id", ""))


def optimise(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {"proposal_id": pid, "objective": "both"}
    if inputs.get("fixed"):
        body["fixed"] = inputs["fixed"]
    o = _call("post", "/optimize", body)
    rec = o.get("closest") or o.get("max_sva")
    figs: dict[str, Any] = {"feasible": 1 if o.get("feasible") else 0,
                            "structures": sum(1 for x in (o.get("closest"), o.get("max_sva")) if x)
                            + len(o.get("alternatives") or []), "counter_offers": len(o.get("counter_offers") or [])}
    if rec:
        rm = rec["metrics"]
        figs.update({"rec_raroc": rm["lifetime_raroc"], "rec_sva": rm["sva"], "rec_rwa": rm["rwa_y1"],
                     "rec_amount": rm["amount_sar_mn"], "hurdle": rm["hurdle"], "rec_ecl": rm.get("day_one_ecl")})
    if o.get("max_sva"):
        figs["max_sva"] = o["max_sva"]["metrics"]["sva"]
    if rec:
        ch = rec.get("changes") or []
        summ = (f"Recommended ({rec.get('label') or 'closest to the ask'}): RAROC {rec['metrics']['lifetime_raroc']:.1%},"
                f" SVA {rec['metrics']['sva']:,.2f}m" + (f"; {len(ch)} changes to the ask" if ch else "; the ask itself"))
    else:
        summ = "No structure clears every hard limit" + (
            f"; {len(o.get('relaxation') or [])} relaxations suggested" if o.get("relaxation") else "")
    figs = {k: v for k, v in figs.items() if isinstance(v, (int, float))}
    return ToolResult(summary=summ, figures=figs,
                      data={k: o.get(k) for k in ("feasible", "ask", "closest", "max_sva", "alternatives",
                                                  "counter_offers", "relaxation", "binding", "single_lever",
                                                  "searched", "trace_id")},
                      trace_id=o.get("trace_id", ""))


def counter_search(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Optimise with the condition a review finding implies fixed (e.g. a 10% cash margin)."""
    pid = _pid(inputs, ctx)
    fixed = dict(inputs.get("fixed") or {})
    o = _call("post", "/optimize", {"proposal_id": pid, "objective": "both", "fixed": fixed or None})
    rec = o.get("closest") or o.get("max_sva")
    label = inputs.get("condition") or ", ".join(f"{k} {v}" for k, v in fixed.items()) or "re-optimised"
    if not rec:
        return ToolResult(summary=f"With {label}: no structure clears every hard limit", figures={"feasible": 0},
                          data={"condition": label, "fixed": fixed, "structure": None})
    m = rec["metrics"]
    return ToolResult(summary=f"With {label}: RAROC {m['lifetime_raroc']:.1%}, SVA {m['sva']:,.2f}m, "
                              f"Day-1 ECL {m.get('day_one_ecl', 0):,.3f}m",
                      figures={"raroc": m["lifetime_raroc"], "sva": m["sva"], "ecl": m.get("day_one_ecl"),
                               "rwa": m["rwa_y1"], "amount": m["amount_sar_mn"], "hurdle": m["hurdle"], "feasible": 1},
                      data={"condition": label, "fixed": fixed, "structure": rec}, trace_id=o.get("trace_id", ""))


# ------------------------------------------------------------------ R11 engines

def forward_risk(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {}
    rec = inputs.get("terms") or recommended_terms(ctx)
    o = ctx.results.get("dd_optimise") or {}
    if rec and (o.get("closest") or o.get("max_sva")):
        structs = []
        for s, role, label in ((o.get("closest"), "recommended", "Closest to the ask"),
                               (o.get("max_sva"), "alternative", "Maximum value")):
            if s:
                structs.append({"label": label, "role": role, "terms": s["terms"]})
        body["structures"] = structs
    f = _call("post", f"/proposals/{pid}/forward-risk", body)
    h, b = f.get("headline") or {}, f.get("book") or {}
    ews = f.get("ews") or {}
    figs = {"p_stage2_next_q": h.get("p_stage2_next_q"), "p_dpd30_next_q": h.get("p_dpd30_next_q"),
            "ecl_day1": h.get("ecl_day1"), "ecl_q4": h.get("ecl_q4"), "ews_score": ews.get("score"),
            "book_p_stage2": b.get("p_stage2_next_q"), "book_p_dpd30": b.get("p_dpd30_next_q")}
    return ToolResult(summary=str(f.get("answer") or "Forward risk computed"),
                      figures={k: v for k, v in figs.items() if isinstance(v, (int, float))},
                      data={k: f.get(k) for k in ("answer", "headline", "book", "ecl_optimal", "best_lever", "ews",
                                                  "structures", "model", "as_of")},
                      trace_id=f.get("trace_id", ""))


def stress_lab(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {"resilience": True, "breakevens": True}
    rec = inputs.get("terms") or recommended_terms(ctx)
    if rec:
        body["recommended_terms"] = rec
    if inputs.get("scenarios"):
        body["scenarios"] = list(inputs["scenarios"])
    s = _call("post", f"/proposals/{pid}/stress", body)
    sm = s.get("summary") or {}
    sev = sm.get("severe") or {}
    figs: dict[str, Any] = {"applicable": sm.get("applicable"), "survived": sm.get("survived"),
                            "failed": len(sm.get("failed") or []), "worst_dscr": sm.get("worst_dscr"),
                            "worst_raroc": sm.get("worst_raroc"), "max_ecl": sm.get("max_ecl"),
                            "stage2_count": sm.get("stage2_count"), "severe_survives": 1 if sev.get("survives") else 0}
    for be in s.get("breakevens") or []:
        first = be.get("first") or {}
        if isinstance(first.get("value"), (int, float)):
            figs[f"breakeven_{be.get('driver')}"] = first["value"]
    return ToolResult(summary=str(s.get("answer") or "Stress Lab run"),
                      figures={k: v for k, v in figs.items() if isinstance(v, (int, float))},
                      data={k: s.get(k) for k in ("answer", "summary", "breakevens", "resilience", "structure",
                                                  "basis")}, trace_id=s.get("trace_id", ""))


def stress_table(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """The existing Analysis stress table (used when the Stress Lab is not on this build)."""
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {"proposal_id": pid, "scenario": "all"}
    rec = inputs.get("terms") or recommended_terms(ctx)
    if rec:
        body["terms"] = rec
    s = _call("post", "/stress", body)
    rows = s.get("scenarios") or s.get("rows") or []
    fails = [r for r in rows if isinstance(r, dict) and (r.get("clears_hurdle") is False or r.get("breaches"))]
    return ToolResult(summary=f"{len(rows)} stress scenarios; {len(fails)} fail the hurdle or a limit",
                      figures={"scenarios": len(rows), "failed": len(fails)}, data=s, trace_id=s.get("trace_id", ""))


def resilience_search(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """After a stress failure: run the failed scenarios on each Optimise structure; keep the most resilient."""
    pid = _pid(inputs, ctx)
    failed = list(inputs.get("scenarios") or (((ctx.results.get("dd_stress_lab") or {}).get("summary") or {})
                                              .get("failed") or []))
    o = ctx.results.get("dd_optimise") or {}
    cands = []
    for key, label in (("closest", "Closest to the ask"), ("max_sva", "Maximum value")):
        if o.get(key):
            cands.append((label, o[key]["terms"]))
    for i, x in enumerate(o.get("counter_offers") or []):
        cands.append((x.get("label") or f"Counter-offer {i + 1}", x["terms"]))
    for i, x in enumerate(o.get("alternatives") or []):
        cands.append((x.get("label") or f"Alternative {i + 1}", x["terms"]))
    if not failed or not cands:
        return ToolResult(summary="No failed scenarios or no structures to search", figures={},
                          data={"best": None, "candidates": []})
    rows = []
    for label, terms in cands[:6]:
        s = _call("post", f"/proposals/{pid}/stress", {"terms": terms, "scenarios": failed, "resilience": False,
                                                       "breakevens": False})
        sm = s.get("summary") or {}
        an = analysis({"proposal_id": pid, "terms": terms}, ctx).figures
        rows.append({"label": label, "terms": terms, "survived": sm.get("survived", 0),
                     "of": sm.get("applicable", len(failed)), "worst_dscr": sm.get("worst_dscr"),
                     "raroc": an.get("lifetime_raroc"), "sva": an.get("sva"), "hurdle": an.get("hurdle")})
    best = max(rows, key=lambda r: (r["survived"], r.get("sva") or -1e9))
    if not best["survived"]:
        return ToolResult(summary=f"None of the {len(rows)} structures survives the {len(failed)} failed scenarios",
                          figures={"best_survived": 0, "of": len(failed), "candidates": len(rows)},
                          data={"best": None, "candidates": rows, "scenarios": failed})
    return ToolResult(summary=f"Most resilient: {best['label']}, survives {best['survived']} of {best['of']} of the "
                              f"failed scenarios (RAROC {best['raroc']:.1%})",
                      figures={"best_survived": best["survived"], "of": best["of"], "best_raroc": best["raroc"],
                               "best_sva": best["sva"], "candidates": len(rows)},
                      data={"best": best, "candidates": rows, "scenarios": failed})


def pipeline_test(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    body: dict[str, Any] = {}
    rec = inputs.get("terms") or recommended_terms(ctx)
    if rec:
        body["terms"] = rec
    r = _call("post", f"/proposals/{pid}/pipeline-test", body)
    makes = r.get("makes_cut", r.get("fits"))
    displaced = r.get("displaced") or r.get("displaces") or []
    bf = r.get("binds_first") or {}
    figs = {k: r.get(k) for k in ("rank", "ranked", "sva_per_100m_rwa", "value_change")}
    figs.update({"displaced": len(displaced) if isinstance(displaced, list) else 0,
                 "resized": len(r.get("resized") or []), "makes_cut": 1 if makes else 0,
                 "binds_first_times": bf.get("times"), "binds_first_headroom": bf.get("headroom")})
    summary = str(r.get("verdict") or r.get("answer") or ("Makes the cut" if makes else "Does not make the cut"))
    if bf.get("text"):
        summary += f"; {bf['text']}"
    return ToolResult(summary=summary, figures={k: v for k, v in figs.items() if isinstance(v, (int, float))},
                      data={k: r.get(k) for k in ("makes_cut", "fits", "verdict", "rank", "ranked", "sva_per_100m_rwa",
                                                  "displaced", "resized", "value_change", "binds_first", "limits",
                                                  "pipeline", "basis")},
                      trace_id=str(r.get("trace_id", "")))


def pipeline_compare(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """The pipeline-level selection without forcing the deal in, next to the test's forced-in result."""
    r = _call("post", "/pipeline/optimise", {})
    sm = r.get("summary") or {}
    pid = _pid(inputs, ctx)
    dec = next((d for d in r.get("decisions") or [] if d.get("proposal_id") == pid), None)
    figs = {k: sm.get(k) for k in ("deals", "selected", "sva", "rwa_used", "rwa_budget", "el_used", "raroc_new")}
    t = ctx.results.get("dd_pipeline_test") or {}
    if isinstance(t.get("value_change"), (int, float)):
        figs["value_change_forced"] = t["value_change"]
    return ToolResult(summary=str(r.get("headline") or "Pipeline optimised") + (
                          f"; this deal: {dec.get('decision') or dec.get('option')}" if dec else ""),
                      figures={k: v for k, v in figs.items() if isinstance(v, (int, float))},
                      data={"headline": r.get("headline"), "summary": sm, "decision": dec, "binding": r.get("binding"),
                            "soft_breaches": r.get("soft_breaches")}, trace_id=str(r.get("trace_id", "")))


def review(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    r = _call("post", f"/proposals/{pid}/review", {})
    ans = r.get("answer") or {}
    counts = ans.get("counts") or {}
    v = r.get("verdicts") or {}
    figs = {"critical": counts.get("critical", 0), "major": counts.get("major", 0), "minor": counts.get("minor", 0),
            "checks": len(r.get("checks") or []), "contradicted": v.get("contradicted", 0),
            "unverifiable": v.get("unverifiable", 0), "exception": v.get("exception", 0),
            "conditions": len((r.get("conditions") or {}).get("items") or []),
            "counter_proposals": len((r.get("counter") or {}).get("counter_proposals") or [])}
    cps = (r.get("counter") or {}).get("counter_proposals") or []
    if cps:
        figs.update({"cp_raroc": cps[0].get("raroc"), "cp_sva": cps[0].get("sva"), "cp_amount": cps[0].get("amount"),
                     "cp_ecl": cps[0].get("ecl_day1")})
    ask = (r.get("counter") or {}).get("ask") or {}
    figs.update({"ask_raroc": ask.get("raroc"), "ask_sva": ask.get("sva"), "ask_hurdle": ask.get("hurdle")})
    return ToolResult(summary=str(ans.get("headline") or ans.get("decision") or "Reviewed"),
                      figures={k: x for k, x in figs.items() if isinstance(x, (int, float))},
                      data={k: r.get(k) for k in ("subject", "answer", "findings", "verdicts", "doa", "counter",
                                                  "conditions", "precedent", "memo", "by_category")}
                      | {"unverifiable_checks": [c for c in r.get("checks") or [] if c.get("verdict") == "unverifiable"]})


def precedent(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    rv = ctx.results.get("dd_review") or _call("post", f"/proposals/{pid}/review", {})
    pr = rv.get("precedent") or {}
    hz = pr.get("horizons") or []
    if not hz:
        return ToolResult(summary="No comparable deals found in the book", data=pr)
    h = hz[0]
    return ToolResult(summary=f"{h['N']} similar deals ({h['match']}): {h['stage2']} of {h['N']} reached Stage 2 and "
                              f"{h['dpd30']} of {h['N']} 30+ DPD within {h['quarters']} quarters",
                      figures={"n": h["N"], "stage2": h["stage2"], "dpd30": h["dpd30"],
                               "stage2_rate": h["stage2_rate"], "dpd30_rate": h["dpd30_rate"],
                               "book_stage2_rate": h.get("book_stage2_rate"), "quarters": h["quarters"]},
                      data=pr)


def house_style_draft(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    d = _call("post", f"/proposals/{pid}/draft", {"use_model": bool(inputs.get("use_model", True))})
    sc = d.get("score") or {}
    return ToolResult(summary=f"House-style draft {d.get('draft_id')}: {len(d.get('sections') or [])} sections, "
                              f"style score {sc.get('total')}" + (" (within the house band)" if sc.get("within_band")
                                                                  else ""),
                      figures={"style_score": sc.get("total"), "sections": len(d.get("sections") or []),
                               "lint": len(d.get("lint") or [])},
                      data={"draft_id": d.get("draft_id"), "title": d.get("title"), "score": sc, "lint": d.get("lint"),
                            "sections": [{"key": s.get("key"), "heading": s.get("heading"),
                                          "judgement": s.get("judgement")} for s in d.get("sections") or []],
                            "docx": f"/api/v1/dealdesk/drafts/{d.get('draft_id')}/docx"})


# ------------------------------------------------------------------ proposals (A4)

def propose_conditions(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    rv = ctx.results.get("dd_review") or {}
    items = list((rv.get("conditions") or {}).get("items") or [])
    if not items:
        return ToolResult(summary="No conditions to track")
    ids = [c["id"] for c in items]
    return ToolResult(summary=f"Proposed: track {len(ids)} conditions with owners and due dates",
                      figures={"conditions": len(ids)},
                      proposal={"kind": "dealdesk.conditions", "approver_role": "CREDIT_OFFICER",
                                "title": f"Track {len(ids)} conditions for {pid}",
                                "reason": "Conditions precedent, covenants and watch items from the proposal review.",
                                "change": {"proposal_id": pid, "condition_ids": ids,
                                           "conditions": [{"id": c["id"], "what": c.get("what"), "owner": c.get("owner"),
                                                           "due_date": c.get("due_date")} for c in items]}})


def propose_counter_offer(inputs: dict[str, Any], ctx: ToolContext) -> ToolResult:
    pid = _pid(inputs, ctx)
    offer = inputs.get("offer") or {}
    if not offer:
        return ToolResult(summary="No counter-offer to send")
    return ToolResult(summary=f"Proposed: send the counter-offer '{offer.get('label')}' to the RM",
                      figures={k: offer[k] for k in ("raroc", "sva") if isinstance(offer.get(k), (int, float))},
                      proposal={"kind": "dealdesk.counter_offer", "approver_role": "CREDIT_OFFICER",
                                "title": f"Send counter-offer to the RM for {pid}: {offer.get('label')}",
                                "reason": offer.get("why") or "The ask does not clear as proposed.",
                                "change": {"proposal_id": pid, "offer": offer}})


def _apply_conditions(change: dict[str, Any]) -> dict[str, Any]:
    done = []
    for cid in change.get("condition_ids") or []:
        try:
            E.call("patch", "/conditions", {"id": cid, "note": "Tracked: approved from the committee preparation"})
            done.append(cid)
        except E.EngineError:
            continue
    return {"tracked": len(done)}


def _apply_counter(change: dict[str, Any]) -> dict[str, Any]:
    offer = change.get("offer") or {}
    note = f"Counter-offer sent to the RM: {offer.get('label')}"
    if is_case(str(change.get("proposal_id") or "")):
        return {"status": "recorded", "note": note + " (prepared case: no Deal Desk status to change)"}
    E.call("post", f"/proposals/{change['proposal_id']}/status", {"status": "counter_offered", "note": note})
    return {"status": "counter_offered"}


R = "read_only"


def register() -> None:
    from backend.agents_v5.runtime import register_applier
    specs = [
        ("dd_ingest", "Ingest and extract the proposal: obligor, ask, existing relationship, renewal or new.", PID,
         READ_ONLY, ingest, ("get", "/proposals/{pid}"), "GET /proposals/{id}"),
        ("dd_spreading", "Spread the financial statements: revenue, EBITDA, margin, Debt/EBITDA, DSCR by year.", PID,
         READ_ONLY, spreading, ("get", "/proposals/{pid}"), "GET /proposals/{id} financials"),
        ("dd_conduct", "Existing borrowers only: book exposure, stage, DPD history, conduct and bureau.", PID,
         READ_ONLY, conduct, ("post", "/proposals/{pid}/review"), "review_facts.facts"),
        ("dd_last_approval", "Renewals: the ask against the facilities approved last time.", PID, READ_ONLY,
         last_approval, ("get", "/proposals/{pid}"), "GET /proposals/{id} existing facilities"),
        ("dd_analysis", "Deal analysis as asked (or for given terms): RAROC, SVA, RWA, ECL, approval level, breaches.",
         _with({"terms": {"type": "object"}}), READ_ONLY, analysis, ("post", "/compute"), "POST /compute"),
        ("dd_optimise", "Optimise: all structures and the recommended deal (closest to the ask), counter-offers.",
         _with({"fixed": {"type": "object"}}), READ_ONLY, optimise, ("post", "/optimize"), "POST /optimize"),
        ("dd_counter_search", "Counter-proposal search: Optimise with a condition fixed (e.g. cash margin 10%).",
         _with({"fixed": {"type": "object"}, "condition": {"type": "string"}}), READ_ONLY, counter_search,
         ("post", "/optimize"), "POST /optimize (fixed)"),
        ("dd_forward_risk", "Forward risk: P(Stage 2) and P(30+ DPD) next quarter, expected ECL path, EWS on the deal.",
         _with({"terms": {"type": "object"}}), READ_ONLY, forward_risk, ("post", "/proposals/{pid}/forward-risk"),
         "POST /proposals/{id}/forward-risk"),
        ("dd_stress_lab", "Stress Lab: scenarios, breakevens (reverse stress), asked vs recommended resilience.",
         _with({"terms": {"type": "object"}, "scenarios": {"type": "array", "items": {"type": "string"}}}), READ_ONLY,
         stress_lab, ("post", "/proposals/{pid}/stress"), "POST /proposals/{id}/stress"),
        ("dd_stress_table", "The existing Analysis stress table (fallback when the Stress Lab is not on this build).",
         _with({"terms": {"type": "object"}}), READ_ONLY, stress_table, ("post", "/stress"), "POST /stress"),
        ("dd_resilience_search", "After a stress failure: the failed scenarios on each Optimise structure; the most "
         "resilient one.", _with({"scenarios": {"type": "array", "items": {"type": "string"}}}), READ_ONLY,
         resilience_search, ("post", "/proposals/{pid}/stress"), "POST /proposals/{id}/stress x structures"),
        ("dd_pipeline_test", "Test against the pipeline: does the deal make the cut, what it displaces, binding limit.",
         _with({"terms": {"type": "object"}}), READ_ONLY, pipeline_test, ("post", "/proposals/{pid}/pipeline-test"),
         "POST /proposals/{id}/pipeline-test"),
        ("dd_pipeline_compare", "Pipeline-level comparison: optimise the whole pipeline with and without the deal.",
         _with({"forced": {"type": "boolean"}}), READ_ONLY, pipeline_compare, ("post", "/pipeline/optimise"),
         "POST /pipeline/optimise"),
        ("dd_review", "Proposal review: claims ledger, findings by severity, policy and DoA, connected parties, "
         "counter-proposals, conditions.", PID, READ_ONLY, review, ("post", "/proposals/{pid}/review"),
         "POST /proposals/{id}/review"),
        ("dd_precedent", "Precedent: similar deals in the book and their Stage 2 and 30+ DPD rates.", PID, READ_ONLY,
         precedent, ("post", "/proposals/{pid}/review"), "review precedent"),
        ("dd_house_style_draft", "Draft the proposal in the bank's house style (facts from data), with a style score.",
         _with({"use_model": {"type": "boolean"}}), READ_ONLY, house_style_draft, ("post", "/proposals/{pid}/draft"),
         "POST /proposals/{id}/draft"),
        ("dd_propose_conditions", "Propose the conditions to track (a credit officer approves).", PID, PROPOSAL_ONLY,
         propose_conditions, ("patch", "/conditions"), "PATCH /conditions (on approval)"),
        ("dd_propose_counter_offer", "Propose sending a counter-offer to the RM (a credit officer approves).",
         _with({"offer": {"type": "object"}}), PROPOSAL_ONLY, propose_counter_offer,
         ("post", "/proposals/{pid}/status"), "POST /proposals/{id}/status (on approval)"),
    ]
    for name, desc, schema, mode, fn, (m, tpl), eng in specs:
        register_tool(Tool(name=name, module=MODULE, description=desc, input_schema=schema, mode=mode, fn=fn,
                           available=_route(m, tpl), engine=eng))
    register_applier("dealdesk.conditions", _apply_conditions)
    register_applier("dealdesk.counter_offer", _apply_counter)


TOOL_NAMES = ("dd_ingest", "dd_spreading", "dd_conduct", "dd_last_approval", "dd_analysis", "dd_optimise",
              "dd_counter_search", "dd_forward_risk", "dd_stress_lab", "dd_stress_table", "dd_resilience_search",
              "dd_pipeline_test", "dd_pipeline_compare", "dd_review", "dd_precedent", "dd_house_style_draft",
              "dd_propose_conditions", "dd_propose_counter_offer")
