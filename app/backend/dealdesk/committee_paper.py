"""PLAN_R12 Session F (I27): the committee paper. It replaces the one-page decision sheet for committee use (the sheet stays for
quick reads): a 2-page decision summary up front (ask, verdict, key numbers, conditions, monitoring tier, approval authority),
then the full bank-form paper in committee order, with signature blocks and approval authority. Word and PDF.

    cp = build("DD-31")                  # {"summary": [sections], "paper": <bank-form paper in committee order>, "density": [...]}
    data, name = docx("DD-31")           # check.docx(data) == []
    data, name = pdf("DD-31")

Every figure comes from Data Domains through `bankform.source` (N5); the summary's density check says no line is without a
number or a source (the voice rules of `bankform.voice`, plus a source under every table).
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.house_style.bankform import ctx, paper as bf, render, voice
from backend.dealdesk.house_style.bankform import writers as W
from backend.dealdesk.house_style.bankform.blocks import BL, KV, NL, P, SIGN, T, BOX
from backend.dealdesk.house_style.bankform.ctx import d, num, pct, xx

KIND = "Committee paper"


def _sec(key: str, heading: str, blocks: list[dict[str, Any]], voice_: str = "credit") -> dict[str, Any]:
    return {"key": key, "n": None, "heading": heading, "voice": voice_, "part": "summary", "blocks": blocks, "gaps": []}


def summary(D: ctx.Deal) -> list[dict[str, Any]]:
    asof = d(D.get("as_of")) or str(D.as_of)
    te, to, tp = W.totals(D)
    res = {r.get("view"): r for r in D.rows("dd_result")}
    ask, rec = res.get("ask"), res.get("recommended")
    plan = D.one("dd_monitoring_plan")
    out = []
    # 1. the ask (business voice)
    a = W.asks(D)
    out.append(_sec("s_ask", "The ask", [
        KV([("Customer", D.name), ("Group", D.group or "not provided"), ("Rating existing / proposed", f"{D.get('internal_rating', default='–')} / {D.get('proposed_rating', 'internal_rating', default='–')}"),
            ("Request", str(D.get("request_kind", "case_type", default="–")).capitalize()), ("Total limits", f"{D.money(te)} → {D.money(tp)}"),
            ("Approval authority", W.approval_authority(D))], cols=2),
        P(f"Business requests approval, as at {asof}, to " + ("; ".join(a) if a else "the facilities in section 3 (lines not provided)") + "."),
    ], "business"))
    # 2. verdict
    vb = []
    if plan:
        # R12 M: this is the plan in force (dd_monitoring_plan); a new stress verdict and tier are published at approval.
        vb.append(P(f"Monitoring plan in force: verdict **{plan.get('verdict')}**; monitoring tier **{plan.get('tier')}** ({str(plan.get('review_frequency') or 'not provided').lower()} review), "
                    f"set by {plan.get('set_by')} on {d(plan.get('set_on'))} because {str(plan.get('reason') or 'reason not provided').lower().rstrip('.')}. "
                    f"The stress verdict of this review (Stress step, per dd_stress_result) sets the new tier at approval, as at {asof}."))
    else:
        vb.append(P(f"Verdict and monitoring tier not available: the stress verdict is not yet published to Data Domains as at {asof}."))
    items = W.recommendation_items(D)
    vb.append(P(f"Credit division recommends approval of total limits of {D.money(tp)} with the {len(items)} decisions in the recommendation, as at {asof}."))
    fs = D.rows("dd_review_finding")
    if fs:
        crit = [f for f in fs if f.get("severity") == "critical"]
        maj = [f for f in fs if f.get("severity") == "major"]
        vb.append(P(f"Review findings per dd_review_finding: {len(crit)} critical, {len(maj)} major, {len(fs) - len(crit) - len(maj)} minor as at {asof}."))
        top = (crit + maj)[:4]
        if top:
            vb.append(BL([f"{f.get('title')}: {str(f.get('text', '')).rstrip('.')} ({f.get('severity')}, per dd_review_finding, {asof})." for f in top]))
    # R13 Q: the Financial quality paragraph (grade and the most severe signals; the full list is in the synopsis)
    fqs = _fin_quality_sentence(D)
    if fqs:
        vb.append(P(fqs))
    out.append(_sec("s_verdict", "Verdict", vb))
    # 3. key numbers
    rows = [["Total limits", f"{D.money(te)} → {D.money(tp)}", D.src("dd_facility_limit") if D.rows("dd_facility_limit") else D.src("dd_proposal")]]
    gt, ce, cp = num(D.get("group_exposure_total")), num(D.get("group_cap_existing")), num(D.get("group_cap_proposed"))
    if gt is not None:
        rows.append(["Group exposure / cap", f"{D.money(gt)} / {D.money(cp or ce)}" + (f" (existing cap {D.money(ce)})" if cp and ce and cp != ce else ""), D.src("dd_proposal")])
    if ask:
        rows.append(["RAROC as asked / hurdle", f"{num(ask.get('lifetime_raroc_pct')) or 0:.1f}% / {num(ask.get('hurdle_pct')) or 0:.1f}%; SVA {D.money(ask.get('sva_sar_mn'), 2)}", D.src("dd_result")])
    if rec:
        rows.append(["RAROC recommended", f"{num(rec.get('lifetime_raroc_pct')) or 0:.1f}%; SVA {D.money(rec.get('sva_sar_mn'), 2)}", D.src("dd_result")])
        rows.append(["PD 12m / LGD / EAD", f"{pct(rec.get('pd_12m'), 2)} / {pct(rec.get('lgd_y1'))} / {D.money(rec.get('ead_y1_sar_mn'))}", D.src("dd_result")])
    from backend.dealdesk.house_style.bankform import cp_writers as CW
    fr = D.one("dd_forward_risk") or CW._engine_forward(D)  # noqa: SLF001
    if fr:
        rows.append(["P(Stage 2) / P(30+) next quarter", f"{pct(fr.get('p_stage2_next_q'), 2)} / {pct(fr.get('p_dpd30_next_q'), 2)}; EWS {fr.get('ews_band')}",
                     D.src("dd_forward_risk") if D.rows("dd_forward_risk") else "Deal Desk · engine.forward_risk on dd_deal"])
    fin = W.fin_rows(D)
    aud = sorted([x for x in fin if W._actual(x) and str(x.get("entity_scope") or "standalone") == "standalone"], key=lambda x: int(x.get("year") or 0))
    if aud:
        c = aud[-1]
        adj = W.adjusted(c)
        rows.append([f"Revenue FY{c.get('year')}", D.money(c.get("revenue")) + (f" (PY {D.money(aud[-2].get('revenue'))})" if len(aud) > 1 else ""), D.src("dd_financials_detail")])
        rows.append([f"Leverage FY{c.get('year')} reported / adjusted", f"{xx(c.get('_lev')) or 'not provided'} / " + (xx(adj.get('adj_leverage')) if adj.get('adj_leverage') is not None else ("not meaningful (adjusted net worth negative)" if (adj.get('adj_net_worth') or 0) <= 0 else "not provided")), D.src("dd_financials_detail")])
        rows.append([f"Net worth FY{c.get('year')} reported / adjusted", f"{D.money(c.get('net_worth'))} / {D.money(adj.get('adj_net_worth')) or 'n/a'}", D.src("dd_financials_detail")])
    br = [r for r in D.rows("dd_stress_result") if str(r.get("breaks")) in ("1", "True", "true")]
    if br:
        sev = {"mild": 0, "moderate": 1, "severe": 2}
        w = min(br, key=lambda r: sev.get(str(r.get("severity")), 3))
        rows.append(["First stress break", f"{w.get('what_breaks')} under {w.get('scenario')} ({w.get('severity')})", D.src("dd_stress_result")])
    pr = D.one("dd_precedent") or CW._engine_precedent(D)  # noqa: SLF001
    if pr:
        rows.append(["Precedent", f"{pr.get('n')} of {pr.get('of_n')} {pr.get('outcome')} within {pr.get('horizon')}",
                     D.src("dd_precedent") if D.rows("dd_precedent") else "Deal Desk · engine.review_precedent on the corporate book"])
    docs = D.rows("dd_document")
    if docs:
        miss = [x for x in docs if str(x.get("status")) in ("pending", "expired", "missing")]
        rows.append(["Documents", f"{len(miss)} of {len(docs)} pending or expired", D.src("dd_document")])
    fq = _fin_quality(D)
    if fq:
        rows.append(["Financial quality grade", f"{fq['grade']['grade']}: {fq['grade']['flagged']} of {fq['grade']['signals']} signals flagged"
                     + (" (limited data)" if fq["grade"]["limited"] else ""), "CreditProbe financial-quality screen on dd_financials_detail"
                     if fq["mode"] == "detail" else "CreditProbe financial-quality screen on dd_obligor_financials"])
    from backend.dealdesk.deposit_requirement.docs import committee_rows  # Round D
    rows += committee_rows(D)
    out.append(_sec("s_numbers", "Key numbers", [T(["Measure", "Value", "Source"], rows, source=f"Data Domains as at {asof}", widths=[4.6, 6.4, 6.0], size=7.5)]))
    # 4. conditions and monitoring
    ac = W.additional_conditions(D)
    cb = [NL(ac[:8])] if ac else [P(f"No condition precedent beyond the terms in section 5 as at {asof}.")]
    if len(ac) > 8:
        from backend.dealdesk.house_style.bankform.registry import COMMITTEE_ORDER
        cb.append(P(f"{len(ac) - 8} further conditions are listed in the recommendation (section {COMMITTEE_ORDER.index('recommendation') + 1} of the full paper), as at {asof}."))
    if plan:
        cb.append(P(f"Monitoring tier {plan.get('tier')}: named triggers {plan.get('thresholds') or 'not provided'}, pushed to Early Warning on {d(plan.get('set_on'))}."))
    out.append(_sec("s_conditions", "Conditions precedent and monitoring", cb))
    # 5. decision and signatures
    out.append(_sec("s_decision", "Committee decision", [
        P(f"Approval authority: **{W.approval_authority(D)}** for total limits of {D.money(tp)} and group exposure of {D.money(gt) if gt is not None else 'not provided'}, as at {asof}.", exempt=True),
        SIGN([("Chief Credit Officer", ""), ("Chief Risk Officer", ""), ("Committee chair", "")]),
        BOX("Decision: [ ] Approved as recommended   [ ] Approved with amendments   [ ] Declined   [ ] Deferred", 2),
    ], "form"))
    return out


def _fin_quality(D: ctx.Deal) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import fin_quality as FQ
        r = FQ.assess(D.pid)
        return r if r["mode"] != "none" else None
    except Exception:  # noqa: BLE001 - the screen never takes the paper down
        return None


def _fin_quality_sentence(D: ctx.Deal) -> str | None:
    """One paragraph: the grade sentence of the screen and its three most severe signals with their numbers."""
    r = _fin_quality(D)
    if not r:
        return None
    from backend.dealdesk import fin_quality as FQ
    head = FQ.paragraph(r, max_lines=0)[0].rstrip(".")
    from backend.dealdesk.fin_quality.engine import rank
    top = sorted([s for s in r["signals"] if s["flag"] is True], key=rank)[:3]
    if top:
        head += "; most severe: " + ", ".join(f"{s['label'].lower()} {s['display']} against {s['threshold_display']} ({s['period']}, {s['severity']})" for s in top)
    return head + " (Financial quality in the synopsis, section " + str(__import__("backend.dealdesk.house_style.bankform.registry", fromlist=["x"]).COMMITTEE_ORDER.index("synopsis") + 1) + ")."


def density(summary_secs: list[dict[str, Any]]) -> list[str]:
    """No line without a number or a source: the voice rules on every summary sentence; every table carries its source."""
    out: list[str] = []
    for s in summary_secs:
        out += voice.check_section(s)
        for b in s["blocks"]:
            if b["t"] == "table" and not b.get("source"):
                out.append(f"{s['key']}: a table without its source")
            if b["t"] == "table":
                for r in b["rows"]:
                    if len(r) >= 3 and not str(r[-1]).strip():
                        out.append(f"{s['key']}: row '{r[0]}' without a source")
    return out


def build(pid: str, polish_text: bool = False) -> dict[str, Any]:
    D = ctx.load(pid)
    full = bf.write(pid, order="committee", polish_text=polish_text, D=D)
    summ = summary(D)
    return {"proposal_id": pid, "kind": "committee_paper", "summary": summ, "paper": full, "density": density(summ),
            "approval_authority": W.approval_authority(D), "coverage": full["coverage"], "voice": full["voice"], "gaps": full["gaps"]}


def _parts(cp: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"title": "Decision summary", "sections": cp["summary"], "numbered": False},
            {"title": "Full paper", "sections": cp["paper"]["sections"], "numbered": True}]


def docx(pid: str, generated_by: str = "", cp: dict[str, Any] | None = None) -> tuple[bytes, str]:
    cp = cp or build(pid)
    return render.docx(cp["paper"], kind=KIND, generated_by=generated_by, parts=_parts(cp))


def pdf(pid: str, generated_by: str = "", cp: dict[str, Any] | None = None) -> tuple[bytes, str]:
    cp = cp or build(pid)
    return render.pdf(cp["paper"], kind=KIND, generated_by=generated_by, parts=_parts(cp))


def summary_docx(pid: str, generated_by: str = "", cp: dict[str, Any] | None = None) -> tuple[bytes, str]:
    """The decision summary alone (for the 2-page check and a quick print)."""
    cp = cp or build(pid)
    return render.docx(cp["paper"], kind=KIND, generated_by=generated_by, parts=_parts(cp)[:1])


# ------------------------------------------------------------------ lineage (PLAN_R12 §0, N5)

LINEAGE_COLUMNS = {
    "dd_deal": ("group_exposure_mn", "group_cap_existing_mn", "group_cap_proposed_mn", "existing_limits_mn", "proposed_limits_mn"),
    "dd_facility_limit": ("existing_mn", "outstanding_mn", "proposed_mn"),
    "dd_security": ("amount_mn", "net_worth_mn"),
    "dd_financials_detail": ("revenue_mn", "net_profit_mn", "net_worth_mn", "due_from_related_mn", "receivables_mn"),
    "bureau_cbrbr": ("funded_outstanding_mn", "non_funded_outstanding_mn"),
    "bureau_entity_report": ("outstanding_mn", "overdue_mn", "returned_cheques_n"),
    "other_bank_facility": ("declared_outstanding_mn", "bureau_outstanding_mn"),
    "dd_project": ("contract_value_revised_mn", "work_done_pct", "received_mn", "due_mn"),
    "dd_account_conduct": ("credit_turnover_mn", "avg_balance_mn", "returned_cheques_n"),
    "dd_group_exposure": ("total_proposed_mn",),
}


def lineage_figures(pid: str) -> dict[str, Any]:
    """The paper's figures, each traced to its relation, row and column (backend.dealdesk.data.lineage.figure): what the papers
    print in the facilities, security, financials, bureau, other-bank, project, conduct and group-exposure sections."""
    from backend.dealdesk.data.lineage import figure
    from backend.dealdesk.house_style.bankform import source
    D = ctx.load(pid)
    out: dict[str, list[dict[str, Any]]] = {}
    for rel, cols in LINEAGE_COLUMNS.items():
        rows = source.read(rel, proposal_id=pid)
        figs = []
        for r in rows:
            raw = {k: v for k, v in r.items() if k != "_src"}
            for c in cols:
                if isinstance(raw.get(c), (int, float)) and not isinstance(raw.get(c), bool):
                    figs.append(figure(rel, raw, c))
        if figs:
            out[rel] = figs
    return {"proposal_id": pid, "customer": D.name, "figures": out}
