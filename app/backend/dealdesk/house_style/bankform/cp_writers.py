"""Deterministic writers for the CreditProbe sections the bank's papers do not have (PLAN_R12 §1.3 point 3):
RAROC and SVA with the optimiser's alternatives; forward risk; the stress verdict and monitoring tier; precedent n-of-N; SWOT with
the weakness-to-mitigant map; group and governance. Each reads Data Domains (dd_result, dd_forward_risk, dd_stress_result,
dd_monitoring_plan, dd_precedent, dd_swot, b360_*); where a relation is still empty the section says "not available".
For forward risk and precedent the engine is the fallback (it computes from the same registered relations), labelled as such.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.house_style.bankform.blocks import BL, H, P, T
from backend.dealdesk.house_style.bankform.ctx import Deal, d, num, pct, xx
from backend.dealdesk.house_style.bankform.writers import _asof, one, status_phrase, totals

Out = tuple[list[dict[str, Any]], list[str]]
VIEW_LABEL = {"ask": "As asked", "recommended": "Recommended (optimiser)"}


def _engine_result_raw(D: Deal) -> list[dict[str, Any]]:
    """The dd_result rows computed the way relations.py computes them (engine.analyse on the ask, the optimiser's closest structure),
    for a deal whose priced result is not yet published (the R12 deals)."""
    try:
        from backend.dealdesk import engine, optimizer
        from backend.dealdesk.data import deals
        p = deals.get(D.pid)
        a = engine.analyse(p)
        r = optimizer.optimize(p, counter_offers=False)
        esc = None if r["feasible"] else optimizer.optimize(p, allow_soft=True, counter_offers=False)
        if r["ask"]["clears"]:
            decision, rec = "approve_as_asked", r["closest"]
        elif r["feasible"]:
            decision, rec = "counter_offer", r["closest"]
        elif esc is not None and esc["feasible"]:
            decision, rec = "escalate", esc["closest"]
        else:
            decision, rec = "decline", None
        src = {"domain": "Deal Desk", "relation": "engine.analyse and optimizer on dd_deal", "row": D.pid, "period": str(D.get("reporting_quarter", default=""))}

        def row(view: str, x: dict[str, Any], note: str, terms: Any = None) -> dict[str, Any]:
            m = x["metrics"]
            return {"proposal_id": D.pid, "view": view, "pd_12m": m["pd_12m"], "lgd_y1": m["lgd_y1"], "ead_y1_sar_mn": m["ead_y1"], "el_y1_sar_mn": m["el_y1"],
                    "capital_y1_sar_mn": m["capital_y1"], "lifetime_raroc_pct": m["lifetime_raroc"] * 100, "hurdle_pct": m["hurdle"] * 100, "sva_sar_mn": m["sva"],
                    "breakeven_margin_bps": engine.breakeven_margin(p, terms) if terms is not None else engine.breakeven_margin(p),
                    "approval_level": x["approval"]["level"], "decision": decision, "trace_note": note, "reporting_quarter": src["period"], "_src": src}
        out = [row("ask", a, "")]
        if rec is not None:
            asked = engine.merge_terms(p, None)
            def _v(x: Any) -> str:
                return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)
            diff = [f"{k.replace('_', ' ')} {_v(asked.get(k))} to {_v(v)}" for k, v in (rec.get("terms") or {}).items()
                    if isinstance(v, (int, float, str)) and not isinstance(v, bool) and asked.get(k) != v][:5]
            out.append(row("recommended", engine.analyse(p, rec["terms"]), "; ".join(diff) or "the optimiser's closest structure to the ask", rec["terms"]))
        return out
    except Exception:  # noqa: BLE001 - the engine cannot price this deal: the section says so
        return []


def w_raroc(D: Deal) -> Out:
    rs = D.rows("dd_result")
    if not rs:
        return [P(f"RAROC and SVA not available: no priced result in Data Domains (dd_result {D.status.get('dd_result', 'missing')}) as at {_asof(D)}.")], ["dd_result"]
    order = sorted(rs, key=lambda r: {"ask": 0, "recommended": 1}.get(str(r.get("view")), 2))
    rows = [[VIEW_LABEL.get(str(r.get("view")), str(r.get("view")).replace("_", " ").capitalize()), D.m(r.get("ead_y1_sar_mn")), pct(r.get("pd_12m"), 2),
             pct(r.get("lgd_y1")), D.m(r.get("el_y1_sar_mn"), 2), D.m(r.get("capital_y1_sar_mn")), f"{num(r.get('lifetime_raroc_pct')) or 0:,.1f}%",
             f"{num(r.get('hurdle_pct')) or 0:,.1f}%", D.m(r.get("sva_sar_mn"), 2), f"{num(r.get('breakeven_margin_bps')) or 0:,.0f}",
             str(r.get("decision") or "–").replace("_", " ")] for r in order]
    blocks = [T(["Structure", "EAD", "PD 12m", "LGD", "EL y1", "Capital", "RAROC", "Hurdle", "SVA", "Break-even (bps)", "Decision"], rows,
                source=D.src("dd_result"), widths=[3.0, 1.3, 1.3, 1.1, 1.2, 1.4, 1.3, 1.3, 1.2, 1.6, 2.3], size=6.8)]
    ask = next((r for r in order if r.get("view") == "ask"), order[0])
    q = d(ask.get("reporting_quarter")) or _asof(D)
    ra, hu = num(ask.get("lifetime_raroc_pct")) or 0, num(ask.get("hurdle_pct")) or 0
    blocks.append(P(f"As asked, lifetime RAROC is {ra:,.1f}% against a {hu:,.1f}% hurdle ({'+' if ra >= hu else ''}{ra - hu:,.1f} points) with SVA of {D.money(ask.get('sva_sar_mn'), 2)}, "
                    f"priced at {q}."))
    for r in order:
        if r is ask:
            continue
        rr = num(r.get("lifetime_raroc_pct")) or 0
        blocks.append(P(f"{VIEW_LABEL.get(str(r.get('view')), str(r.get('view')))}: RAROC {rr:,.1f}% (as asked {ra:,.1f}%) and SVA {D.money(r.get('sva_sar_mn'), 2)}"
                        + (f" with {r.get('trace_note')}" if r.get("trace_note") else "") + f", per the optimiser run of {q}."))
    blocks.append(P(f"Approval authority per the engine: {ask.get('approval_level') or 'not available'} for EAD of {D.money(ask.get('ead_y1_sar_mn'))} ({q})."))
    return blocks, []


_ENGINE: dict[tuple[str, str], Any] = {}


def _cached(kind: str, D: Deal, fn) -> Any:
    k = (kind, D.pid)
    if k not in _ENGINE:
        _ENGINE[k] = fn(D)
    return _ENGINE[k]


def _engine_forward(D: Deal) -> dict[str, Any] | None:
    return _cached("forward", D, _engine_forward_raw)


def _engine_forward_raw(D: Deal) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import forward_risk as fr
        try:
            from backend.dealdesk.data import deals
            rec = deals.get(D.pid)
        except Exception:  # noqa: BLE001 - before Session E's registry: the R11 proposals
            from backend.dealdesk import proposals
            rec = proposals.get(D.pid)
        out = fr.forward_risk(rec, levers=False)
        h = out["headline"]
        return {"p_stage2_next_q": h["p_stage2_next_q"], "p_dpd30_next_q": h["p_dpd30_next_q"], "ecl_day1": h["ecl_day1"], "ecl_q4": h["ecl_q4"],
                "ews_band": h["ews_band"], "ews_score": h["ews_score"], "as_of": out.get("as_of"), "_src": {"domain": "Deal Desk", "relation": "engine.forward_risk on dd_deal",
                                                                                                             "row": D.pid, "period": out.get("as_of") or ""}}
    except Exception:  # noqa: BLE001 - the engine knows only proposals in its registry
        return None


def w_forward(D: Deal) -> Out:
    r = D.one("dd_forward_risk") or _engine_forward(D)
    if not r:
        return [P(f"Forward risk (P(Stage 2), P(30+), ECL, EWS) not available for {D.pid} in Data Domains as at {_asof(D)}.")], ["dd_forward_risk"]
    q = d(r.get("as_of")) or _asof(D)
    src = D.src("dd_forward_risk") if D.rows("dd_forward_risk") else "Deal Desk · engine.forward_risk on dd_deal"
    blocks = [T(["Measure", "Value", "Basis"], [["P(Stage 2) next quarter", pct(r.get("p_stage2_next_q"), 2), "transition model on the corporate book"],
                                               ["P(30+ DPD) next quarter", pct(r.get("p_dpd30_next_q"), 2), "transition model on the corporate book"],
                                               ["ECL day 1", D.money(r.get("ecl_day1"), 2), "engine PD, LGD and EAD"],
                                               ["Expected ECL in 4 quarters", D.money(r.get("ecl_q4"), 2), "stage path x stage ECL"],
                                               ["EWS on the deal", f"{r.get('ews_band')} ({r.get('ews_score')})", "EWS rules on the post-deal profile"]],
                source=src, widths=[5.0, 3.0, 9.0])]
    blocks.append(P(f"P(Stage 2) next quarter of {pct(r.get('p_stage2_next_q'), 2)} and P(30+ DPD) of {pct(r.get('p_dpd30_next_q'), 2)} as at {q}; "
                    f"expected ECL rises from {D.money(r.get('ecl_day1'), 2)} on day 1 to {D.money(r.get('ecl_q4'), 2)} in 4 quarters."))
    blocks.append(P(f"EWS on the deal: band {r.get('ews_band')} with a score of {r.get('ews_score')} as at {q}."))
    return blocks, []


def w_stress(D: Deal) -> Out:
    rs = D.rows("dd_stress_result")
    plan = D.one("dd_monitoring_plan")
    blocks, gaps = [], []
    if rs:
        blocks.append(T(["Family", "Severity", "Scenario", "Breaks", "What breaks", "Value"],
                        [[r.get("family"), r.get("severity"), r.get("scenario"), "Yes" if str(r.get("breaks")) in ("1", "True", "true") else "No",
                          r.get("what_breaks") or "–", "–" if r.get("value") is None else r.get("value")] for r in rs],
                        source=D.src("dd_stress_result"), widths=[2.2, 2.0, 4.4, 1.4, 4.4, 1.6]))
        br = [r for r in rs if str(r.get("breaks")) in ("1", "True", "true")]
        sev = {"mild": 0, "moderate": 1, "severe": 2}
        if br:
            w = min(br, key=lambda r: sev.get(str(r.get("severity")), 3))
            blocks.append(P(f"{len(br)} of {len(rs)} stress cases break a limit as at {_asof(D)}; the first break is {w.get('what_breaks')} under "
                            f"'{w.get('scenario')}' at {w.get('severity')} severity ({w.get('value')})."))
        else:
            blocks.append(P(f"None of the {len(rs)} stress cases breaks DSCR, a covenant, Stage 2 or the hurdle as at {_asof(D)}."))
    else:
        gaps.append("dd_stress_result")
        blocks.append(P(f"Stress ladder results not available in Data Domains (dd_stress_result {D.status.get('dd_stress_result', 'missing')}) as at {_asof(D)}."))
    if plan:
        blocks.append(P(f"Verdict: **{plan.get('verdict')}**; monitoring tier **{plan.get('tier')}** with {str(plan.get('review_frequency') or 'not provided').lower()} review, "
                        f"set by {plan.get('set_by')} on {d(plan.get('set_on'))} because {str(plan.get('reason') or 'reason not provided').lower()}."))
        blocks.append(P(f"Named triggers pushed to Early Warning on {d(plan.get('set_on'))}: {plan.get('thresholds') or 'not provided'} (drivers: {plan.get('drivers') or 'not provided'})."))
    else:
        gaps.append("dd_monitoring_plan")
        blocks.append(P(f"Verdict and monitoring tier not available: dd_monitoring_plan {D.status.get('dd_monitoring_plan', 'missing')} as at {_asof(D)}."))
    return blocks, gaps


def _engine_precedent(D: Deal) -> dict[str, Any] | None:
    return _cached("precedent", D, _engine_precedent_raw)


def _engine_precedent_raw(D: Deal) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import review_precedent as rp
        te, to, tp = totals(D)
        out = rp.precedent({"sector": D.get("sector"), "rating": D.get("internal_rating"), "amount_sar": tp})
        hs = [x for x in out.get("horizons", []) if x.get("N")]
        if not hs:
            return None
        h = hs[0]
        return {"n": h.get("stage2"), "of_n": h.get("N"), "horizon": f"{h.get('quarters')} quarters", "outcome": "reached Stage 2",
                "basis": f"{out.get('sector')}, rating within 2 notches of {out.get('rating')}, size 0.25x-4x", "as_of": h.get("anchor"),
                "dpd30": h.get("dpd30"), "book_rate": h.get("book_stage2_rate"), "window": h.get("window"),
                "_src": {"domain": "Deal Desk", "relation": "engine.review_precedent on corp_facility_quarter", "row": D.pid, "period": h.get("window") or ""}}
    except Exception:  # noqa: BLE001
        return None


def w_precedent(D: Deal) -> Out:
    r = D.one("dd_precedent") or _engine_precedent(D)
    if not r or r.get("of_n") in (None, 0):
        return [P(f"Precedent n-of-N not available for {D.get('sector', default='this sector')} at rating {D.get('internal_rating', default='not provided')} as at {_asof(D)}.")], ["dd_precedent"]
    n, N = int(num(r.get("n")) or 0), int(num(r.get("of_n")) or 0)
    out = [P(f"Precedent: {n} of {N} comparable borrowers ({r.get('basis')}) {r.get('outcome')} within {r.get('horizon')}, a rate of {pct(n / N if N else 0)}, "
             f"per the book at {d(r.get('as_of')) or r.get('as_of') or _asof(D)}" + (f" (window {r.get('window')})" if r.get("window") else "") + ".")]
    if r.get("book_rate") is not None:
        out.append(P(f"The book's rate over the same window is {pct(r.get('book_rate'))}" + (f"; {int(num(r.get('dpd30')) or 0)} of {N} went 30+ days past due" if r.get("dpd30") is not None else "")
                     + f", per engine.review_precedent at {r.get('as_of')}."))
    return out, []


def w_swot(D: Deal) -> Out:
    rs = D.rows("dd_swot")
    if not rs:
        return [P(f"SWOT not available: not yet published to Data Domains (dd_swot {D.status.get('dd_swot', 'missing')}) as at {_asof(D)}.")], ["dd_swot"]
    blocks = []
    for k, lab in (("strength", "Strengths"), ("weakness", "Weaknesses"), ("opportunit", "Opportunities"), ("threat", "Threats")):
        xs = [r for r in rs if str(r.get("kind", "")).lower().startswith(k[:5])]
        if xs:
            blocks.append(H(lab))
            blocks.append(BL([f"{one(r.get('text'))} (per dd_swot; evidence: {r.get('evidence') or 'not linked'})." for r in xs]))
    wm = [r for r in rs if str(r.get("kind", "")).lower().startswith("weak")]
    if wm:
        blocks.append(H("Which structure answers which weakness"))
        blocks.append(T(["Weakness", "Mitigant in the structure"], [[r.get("text"), r.get("mitigant") or "not provided"] for r in wm], source=D.src("dd_swot"), widths=[8.5, 8.5]))
    return blocks, []


def w_group(D: Deal) -> Out:
    sh, bd, ins = D.rows("b360_shareholder"), D.rows("b360_board"), D.rows("b360_insider_link")
    ents, shared = D.rows("b360_entity"), D.rows("rel_shared_collateral")
    if not any((sh, bd, ins, ents)):
        return [P(f"Group and governance facts not available: Borrower 360 relations for {D.group or D.name} are empty as at {_asof(D)}.")], ["b360_shareholder"]
    blocks, flags = [], []
    if ents:
        blocks.append(P(f"{len(ents)} group entities per Borrower 360 as at {_asof(D)}, with total exposure of {D.money(sum(num(r.get('exposure_total')) or 0 for r in ents))} at the bank."))
    ubo = [r for r in sh if str(r.get("ubo_flag")) in ("1", "True", "true")]
    if ubo:
        blocks.append(P("UBOs: " + "; ".join(f"{r.get('holder')} ({pct(r.get('pct'))} of {r.get('entity')})" for r in ubo) + f", per b360_shareholder at {_asof(D)}."))
    for r in ins:
        flags.append(f"Insider link: {r.get('person')} holds {pct(r.get('share_pct'))} of {r.get('entity')} and is a {r.get('link_kind')} ({d(r.get('as_of')) or _asof(D)}).")
    for r in D.rows("b360_ownership_change"):
        flags.append(f"Ownership change: {pct(r.get('pct'))} of {r.get('entity')} moved to {r.get('to_holder')} on {d(r.get('date'))}.")
    for r in ents:
        if str(r.get("classification", "")).lower() not in ("", "regular", "none") or str(r.get("litigation")) in ("1", "True"):
            flags.append(f"Connected party {r.get('entity')}: {status_phrase(r.get('classification') or 'litigation')} with {D.money(r.get('exposure_total')) or D.money(0)} of exposure at the bank ({_asof(D)}).")
    for r in D.rows("bureau_entity_report"):
        if (num(r.get("returned_cheques")) or 0) >= 10 or (num(r.get("court_cases")) or 0) >= 2:
            flags.append(f"Connected-party conduct: {r.get('entity')} with {int(num(r.get('returned_cheques')) or 0)} returned cheques and {int(num(r.get('court_cases')) or 0)} court cases "
                         f"per the bureau of {d(r.get('report_date'))}.")
    if shared:
        flags.append(f"{len(shared)} shared collateral item(s) with other borrowers per rel_shared_collateral ({_asof(D)}).")
    blocks.append(H("Governance and conduct red flags"))
    blocks.append(BL(flags) if flags else P(f"No governance or conduct red flag in Borrower 360 as at {_asof(D)}."))
    blocks.append(P(f"Rating overlay suggested by the red flags: {min(len(flags), 3)} notch(es), capped at 3, on {_asof(D)}."))
    ce, cp, gt = num(D.get("group_cap_existing")), num(D.get("group_cap_proposed")), num(D.get("group_exposure_total"))
    if gt is not None and ce:
        over = gt - ce
        blocks.append(P(f"Group cap test at {_asof(D)}: exposure {D.money(gt)} against the approved cap of {D.money(ce)} ("
                        + (f"breach of {D.money(over)}; an increase to {D.money(cp)} is an explicit ask with its approval authority)." if over > 0 else f"headroom {D.money(-over)}).")))
    return blocks, []


__all__ = ["w_raroc", "w_forward", "w_stress", "w_precedent", "w_swot", "w_group", "xx"]


# ------------------------------------------------------------------ product sections (PLAN_R12 §1.8; the product template decides)

def _na_product(D: Deal, what: str) -> Out:
    return [P(f"Not applicable: {D.name} is not a {what} deal per the product template (dd_deal) as at {_asof(D)}.")], []


def w_syndication(D: Deal) -> Out:
    r = D.one("dd_syndication")
    if not r:
        return _na_product(D, "syndicated")
    a = _asof(D)
    tot, com, hold = num(r.get("total_facility_mn")), num(r.get("our_commitment_mn")), num(r.get("final_hold_mn"))
    blocks = [T(["Item", "Value"], [["Facility", r.get("facility_name")], ["Borrower", r.get("borrower")], ["Total facility", D.money(tot)],
                                    ["Our commitment / share", f"{D.money(com)} ({pct(r.get('our_share_pct'))})"], ["Final hold after sell-down", D.money(hold)],
                                    ["Role / agent", f"{str(r.get('role') or '').capitalize()} / {r.get('agent_bank')}"],
                                    ["Mandated lead arrangers", str(r.get("mla_banks") or "").replace(";", "; ")], ["Lenders", r.get("lenders_n")],
                                    ["Margin / participation fee", f"{num(r.get('margin_bps')) or 0:,.0f} bps / {num(r.get('upfront_fee_bps')) or 0:,.0f} bps"],
                                    ["Tenor / signing", f"{num(r.get('tenor_years')) or 0:,.0f} years / {d(r.get('signing_date'))}"]],
                source=D.src("dd_syndication"), widths=[5.0, 12.0])]
    blocks.append(P(f"Our commitment of {D.money(com)} is {pct(r.get('our_share_pct'))} of the {D.money(tot)} facility; the sell-down of {D.money(r.get('sell_down_mn'))} "
                    f"by {d(r.get('sell_down_by'))} brings the final hold to {D.money(hold)} ({pct((hold or 0) / tot if tot else 0)} of the facility), as at {a}."))
    blocks.append(P(f"Waivers need {pct(r.get('majority_lenders_pct'))} of the lenders; our final hold of {pct((hold or 0) / tot if tot else 0)} gives no blocking vote, as at {a}."))
    blocks.append(BL([f"Security as per the agent: {one(r.get('security_text'))} ({'pari passu' if str(r.get('pari_passu_flag')) in ('1', 'True') else 'not pari passu'}, {a}).",
                      f"Covenants as per the facility agreement: {one(r.get('covenants_text'))} ({a}).",
                      f"Information from the agent as per business: {one(r.get('info_from_agent'))}."]))
    return blocks, []


def w_escrow(D: Deal) -> Out:
    r = D.one("dd_escrow_account")
    if not r:
        return _na_product(D, "escrow")
    a = _asof(D)
    units, sold = num(r.get("units_total")) or 0, num(r.get("units_sold")) or 0
    sales, coll, recv = num(r.get("sales_value_mn")) or 0, num(r.get("collected_mn")) or 0, num(r.get("receivable_mn")) or 0
    blocks = [P(f"{r.get('project_name')} by {r.get('developer')}: {int(sold)} of {int(units)} units sold off-plan ({pct(sold / units if units else 0)}) for {D.money(sales)}; "
                f"{D.money(coll)} collected ({pct(coll / sales if sales else 0)}) and {D.money(recv)} still due from buyers, as at {a}."),
              P(f"Construction is {pct(r.get('construction_pct'))} complete against a cost of {D.money(r.get('construction_cost_mn'))}; {pct(r.get('retention_pct'))} of each "
                f"collection is retained until handover; minimum cover ratio {xx(r.get('cover_ratio_min_x'))}, per dd_escrow_account at {a}.")]
    wf = r.get("waterfall_json") or []
    if isinstance(wf, list) and wf:
        blocks.append(H("Release waterfall"))
        blocks.append(T(["Step", "Use", "Rule"], [[x.get("seq"), x.get("use"), x.get("rule")] for x in wf if isinstance(x, dict)], source=D.src("dd_escrow_account"),
                        widths=[1.2, 6.0, 9.8]))
    from backend.dealdesk.house_style.bankform import source as S
    mv = sorted(S.read("dd_escrow", escrow_id=r.get("escrow_id")), key=lambda x: str(x.get("month")))
    if mv:
        last = mv[-6:]
        blocks.append(T(["Month", "Collections", "To construction", "Debt service", "To developer", "Retention", "Balance", "Loan o/s"],
                        [[d(x.get("month")), D.m(x.get("collections_mn")), D.m(x.get("release_construction_mn")), D.m(x.get("release_debt_service_mn")),
                          D.m(x.get("release_developer_mn")), D.m(x.get("retention_added_mn")), D.m(x.get("closing_balance_mn")), D.m(x.get("loan_outstanding_mn"))]
                         for x in last], source=f"Deal Desk · dd_escrow · {len(mv)} rows", size=7))
        lx = mv[-1]
        bal, loan = num(lx.get("closing_balance_mn")) or 0, num(lx.get("loan_outstanding_mn")) or 0
        blocks.append(P(f"Escrow balance of {D.money(bal)} and buyer receivables of {D.money(recv)} against a loan of {D.money(loan)} at {d(lx.get('month'))}, "
                        f"a cover of {xx((bal + recv) / loan if loan else 0)} before the cost to complete; "
                        f"{D.money(sum(num(x.get('release_developer_mn')) or 0 for x in mv))} released to the developer over {len(mv)} months."))
    blocks.append(P(f"Release rules as per the escrow agreement: {one(r.get('release_rules'))} ({a})."))
    return blocks, []


def w_sme_decision(D: Deal) -> Out:
    r = D.one("dd_sme_application")
    if not r:
        return _na_product(D, "SME programme")
    a = _asof(D)
    rules = r.get("rules_json") or []
    blocks = [P(f"{r.get('applicant')} ({r.get('programme')}, {r.get('sector')}, {r.get('years_in_business')} years in business) applies for {D.money(r.get('amount_mn'))} over "
                f"{r.get('tenor_months')} months against annual sales of {D.money(r.get('annual_sales_mn'))}, submitted {d(r.get('submitted_date'))}."),
              P(f"Scorecard {r.get('scorecard_id')}: {r.get('score')} points, grade {r.get('grade')}, PD {pct(r.get('pd'), 2)}; {int(num(r.get('rules_failed')) or 0)} of {len(rules)} "
                f"policy rules failed; decision **{str(r.get('decision') or '').replace('_', ' ')}** at {r.get('doa_level')}"
                + (f" on {d(r.get('decided_date'))}." if r.get("decided_date") else f" (pending as at {a})."))]
    if isinstance(rules, list) and rules:
        blocks.append(T(["Rule", "Value", "Limit", "Result"], [[str(x.get("rule", "")).replace("_", " "), x.get("value"), x.get("limit"), "Pass" if x.get("pass") else "Fail"]
                                                            for x in rules if isinstance(x, dict)], source=D.src("dd_sme_application"), widths=[7.0, 3.0, 3.0, 4.0]))
    if r.get("conditions_text"):
        blocks.append(P(f"Conditions as per the scorecard decision of {d(r.get('decided_date')) or a}: {one(r.get('conditions_text'))}."))
    if str(r.get("exception_flag")) in ("1", "True"):
        blocks.append(P(f"An exception sends the application to the full flow, per dd_sme_application at {a}."))
    return blocks, []
