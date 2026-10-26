"""P2: the facts a drafted section may use, from the books and the proposal (never from an exemplar).

Two sources:
  - a Deal Desk proposal (`proposals.get`: DD-01..15 and user proposals), the corporate book's facilities and the
    engine's analysis when the book is available;
  - a prepared UAE case (`proposal_cases`: PRP-A-GMC, PRP-B-ASB).

Every fact: {id, key, label, value, unit, display, source, derived (formula, when computed), kind (number|text)}. Ids are
F1.. across the memo so a citation is unique. A derived figure carries its formula (N5: every number computed, not typed).
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.house_style import stylo

FACILITY = {"term_loan": "term finance facility", "revolver": "revolving working capital facility",
            "performance_lg": "performance letter of guarantee line", "financial_lg": "financial letter of guarantee line",
            "trade_lc": "trade letter of credit line"}


class Facts:
    def __init__(self, ccy: str, style: dict[str, Any] | None = None):
        self.ccy = ccy
        self.style = style or {}
        self.items: list[dict[str, Any]] = []
        self.by_section: dict[str, list[str]] = {}

    def add(self, section: str, key: str, label: str, value: Any, unit: str, source: str, derived: str | None = None,
            ccy: str | None = None) -> dict[str, Any] | None:
        if value is None or value == "" or (isinstance(value, float) and value != value):
            return None
        f = {"id": f"F{len(self.items) + 1}", "key": key, "label": label, "value": value, "unit": unit,
             "display": self.display(value, unit, ccy), "source": source, "derived": derived, "currency": ccy or self.ccy,
             "kind": "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else "text", "section": section}
        self.items.append(f)
        self.by_section.setdefault(section, []).append(f["id"])
        return f

    def display(self, v: Any, unit: str, ccy: str | None = None) -> str:
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return str(v)
        if unit == "ccy m":
            return stylo.fmt_money(v, ccy or self.ccy, self.style)
        if unit == "ratio":
            return stylo.fmt_pct(v, self.style)
        if unit == "%":
            return stylo.fmt_pct(v, self.style, ratio=False)
        if unit == "x":
            return f"{v:.2f}x"
        if unit == "bps":
            return f"{int(round(v))} bps"
        if unit == "years":
            return f"{int(v)} year{'s' if int(v) != 1 else ''}"
        if unit == "count":
            return f"{int(v):,}"
        return f"{v:,.1f}"

    def get(self, key: str) -> dict[str, Any] | None:
        return next((f for f in self.items if f["key"] == key), None)

    def section(self, key: str) -> list[dict[str, Any]]:
        ids = set(self.by_section.get(key, []))
        return [f for f in self.items if f["id"] in ids]


def _r(x: float, d: int = 4) -> float:
    return round(float(x), d)


# ---------------------------------------------------------------------------------------------- Deal Desk proposals

def from_proposal(p: dict[str, Any], style: dict[str, Any] | None = None, analysis: dict[str, Any] | None = None) -> Facts:
    ob, a = p["obligor"], p["ask"]
    pid = p.get("proposal_id", "")
    ccy = a.get("currency", "SAR")
    F = Facts(ccy, style)
    src = f"Proposal {pid}"
    fin_ccy = (p.get("financials") or {}).get("currency") or "SAR"  # the book and the spreading are in SAR

    def fx(c: str) -> float:
        from backend.dealdesk import proposals
        try:
            return proposals.fx(c)
        except Exception:  # noqa: BLE001 - parameters unavailable: no conversion
            return 1.0
    amount_sar = float(a["amount"]) * fx(ccy)
    book = f"Corporate book {ob.get('prefilled_from') or ''}".strip()
    F.add("obligor", "name", "Obligor", ob.get("name"), "text", src)
    F.add("obligor", "cr", "CR number", ob.get("cr_number"), "text", src)
    F.add("obligor", "sector", "Sector", (ob.get("sector") or "") + (f" ({ob['sub_sector']})" if ob.get("sub_sector") else ""), "text", src)
    F.add("obligor", "region", "Region", ob.get("region"), "text", src)
    F.add("obligor", "group", "Group", ob.get("group_name"), "text", src)
    F.add("obligor", "rating", "Internal rating", ob.get("internal_rating"), "text", src)
    F.add("obligor", "existing", "Existing client", "existing client" if ob.get("existing") else "new to the bank", "text", src)
    if ob.get("existing_exposure_sar_mn"):
        F.add("obligor", "existing_exposure", "Existing exposure", _r(ob["existing_exposure_sar_mn"], 1), "ccy m", book, ccy="SAR")
    F.add("conduct", "bureau", "Credit bureau (SIMAH)", ob.get("simah_flag"), "text", src)
    ex = ob.get("existing_facilities") or []
    if ex:
        lim = sum(float(f.get("limit") or 0) for f in ex)
        drawn = sum(float(f.get("drawn") or 0) for f in ex)
        F.add("conduct", "facilities_n", "Existing facilities", len(ex), "count", book)
        F.add("conduct", "facilities_limit", "Existing limits", _r(lim, 1), "ccy m", book, "sum of the existing facility limits", ccy="SAR")
        F.add("conduct", "facilities_drawn", "Drawn", _r(drawn, 1), "ccy m", book, "sum of the drawn balances", ccy="SAR")
        if lim:
            F.add("conduct", "utilisation", "Utilisation", _r(drawn / lim), "ratio", book, "drawn / existing limits")
        st2 = sum(1 for f in ex if int(f.get("stage") or 1) >= 2)
        F.add("conduct", "stage", "IFRS 9 stage of existing facilities", "all Stage 1" if not st2 else f"{st2} in Stage 2 or worse", "text", book)
    lim0 = sum(float(f.get("limit") or 0) for f in ex)
    if lim0:
        F.add("facilities", "limits_existing_f", "Existing limits", _r(lim0, 1), "ccy m", book, "sum of the existing facility limits", ccy="SAR")
    F.add("facilities", "amount_f", "Amount requested", _r(a["amount"], 1), "ccy m", src)
    if lim0:
        F.add("facilities", "limits_after_f", "Total limits after the request", _r(lim0 + amount_sar, 1), "ccy m", src,
              "existing limits + amount requested" + (f" at {ccy}/SAR {fx(ccy):g}" if ccy != "SAR" else ""), ccy="SAR")
    # financials: the latest actual year, and growth on the year before
    years = sorted((y for y in p.get("financials", {}).get("years", []) if y.get("kind") == "actual"), key=lambda y: y["year"])
    if years:
        y = years[-1]
        fs = f"Financials {y['year']} ({y.get('source', 'proposal')})"
        F.add("financials", "fin_year", "Latest actual year", f"FY{y['year']}", "text", fs)
        rev, eb, td, ds = y.get("revenue"), y.get("ebitda"), y.get("total_debt"), y.get("debt_service")
        F.add("financials", "revenue", f"Revenue FY{y['year']}", _r(rev, 1) if rev else None, "ccy m", fs, ccy=fin_ccy)
        if len(years) > 1 and years[-2].get("revenue"):
            F.add("financials", "revenue_growth", "Revenue growth", _r(rev / years[-2]["revenue"] - 1), "ratio", fs,
                  f"revenue FY{y['year']} / FY{years[-2]['year']} - 1")
        F.add("financials", "ebitda", f"EBITDA FY{y['year']}", _r(eb, 1) if eb else None, "ccy m", fs, ccy=fin_ccy)
        if rev and eb:
            F.add("financials", "ebitda_margin", "EBITDA margin", _r(eb / rev), "ratio", fs, "EBITDA / revenue")
        F.add("financials", "total_debt", "Total debt", _r(td, 1) if td else None, "ccy m", fs, ccy=fin_ccy)
        if td and eb:
            F.add("financials", "leverage", "Debt/EBITDA", _r(td / eb, 2), "x", fs, "total debt / EBITDA")
        if eb and ds:
            F.add("financials", "dscr", "DSCR", _r(eb / ds, 2), "x", fs, "EBITDA / debt service")
        F.add("financials", "net_worth", "Net worth", _r(y.get("net_worth"), 1) if y.get("net_worth") else None, "ccy m", fs, ccy=fin_ccy)
        F.add("financials", "current_ratio", "Current ratio", _r(y.get("current_ratio"), 2) if y.get("current_ratio") else None, "x", fs)
    # the request
    F.add("request", "purpose", "Purpose", p.get("purpose"), "text", src)
    F.add("request", "facility", "Facility", FACILITY.get(a["facility_type"], a["facility_type"].replace("_", " ")), "text", src)
    F.add("request", "structure", "Structure", str(a.get("structure", "")).capitalize(), "text", src)
    F.add("request", "amount", "Amount requested", _r(a["amount"], 1), "ccy m", src)
    F.add("request", "tenor", "Tenor", int(a["tenor_years"]), "years", src)
    if a.get("grace_years"):
        F.add("request", "grace", "Grace", int(a["grace_years"]), "years", src)
    F.add("request", "repayment", "Repayment", str(a.get("amortisation", "")), "text", src)
    bench = "SOFR" if ccy == "USD" else ("EIBOR" if ccy == "AED" else "SAIBOR")
    F.add("request", "benchmark", "Benchmark", bench, "text", src)
    if a.get("margin_bps"):
        F.add("request", "margin", "Margin", int(a["margin_bps"]), "bps", src)
    if a.get("commission_bps"):
        F.add("request", "commission", "Commission", int(a["commission_bps"]), "bps", src)
    if a.get("upfront_fee_bps"):
        F.add("request", "upfront_fee", "Upfront fee", int(a["upfront_fee_bps"]), "bps", src)
    # security
    sec = p.get("security", {})
    ids = a.get("collateral_ids")
    coll = [c for c in sec.get("collateral", []) if (c.get("collateral_id") in ids if ids is not None else c.get("pledged_in_ask", True))]
    if coll:
        cv = sum(float(c.get("value") or 0) * fx(c.get("currency") or "SAR") for c in coll)
        F.add("security", "collateral_type", "Collateral", ", ".join(sorted({str(c["type"]).replace("_", " ") for c in coll})), "text", src)
        F.add("security", "collateral_value", "Collateral value", _r(cv, 1), "ccy m", src, ccy="SAR")
        if cv:
            F.add("security", "ltv", "LTV", _r(amount_sar / cv), "ratio", src,
                  "amount requested / collateral value" + (f", both in SAR at {ccy}/SAR {fx(ccy):g}" if ccy != "SAR" else ""))
    else:
        F.add("security", "collateral_type", "Collateral", "none offered", "text", src)
    for i, gu in enumerate(sec.get("guarantees", [])[:3]):
        sfx = "" if i == 0 else f"_{i + 1}"
        F.add("security", f"guarantee{sfx}", "Guarantee", f"{gu.get('type', '')} guarantee of {gu.get('guarantor', '')}".strip(), "text", src)
        F.add("security", f"guarantee_cover{sfx}", "Guarantee cover", float(gu.get("coverage_pct") or 0), "%", src)
    F.add("security", "covenant_package", "Covenant package", sec.get("covenant_package", "none"), "text", src)
    for c in sec.get("covenants", [])[:3]:
        F.add("security", f"cov_{c['type']}", f"{c['type']} covenant", float(c["threshold"]), "x", src)
    anc = (p.get("business_case") or {}).get("ancillary_income_sar_mn_pa") or {}
    if anc:
        F.add("business", "ancillary", "Ancillary income p.a.", _r(sum(float(v) for v in anc.values()), 2), "ccy m", src,
              "sum of " + ", ".join(k.replace("_", " ") for k in anc), ccy="SAR")
    F.add("business", "purpose_b", "Purpose", p.get("purpose"), "text", src)
    F.add("business", "bu", "Business unit", p.get("business_unit"), "text", src)
    if analysis:
        m = analysis.get("metrics", {})
        es = f"Deal Desk engine ({analysis.get('trace_id') or 'analyse'})"
        F.add("recommendation", "raroc", "Lifetime RAROC", _r(m.get("lifetime_raroc"), 4) if m.get("lifetime_raroc") is not None else None, "ratio", es)
        F.add("recommendation", "hurdle", "Hurdle", _r(m.get("hurdle"), 4) if m.get("hurdle") is not None else None, "ratio", es)
        F.add("recommendation", "approval", "Approval level", (analysis.get("approval") or {}).get("level"), "text", es)
    F.add("recommendation", "rm", "Relationship manager", p.get("rm"), "text", src)
    F.add("recommendation", "amount_r", "Amount requested", _r(a["amount"], 1), "ccy m", src)
    F.add("recommendation", "facility_r", "Facility", FACILITY.get(a["facility_type"], a["facility_type"]), "text", src)
    F.add("recommendation", "purpose_r", "Purpose", p.get("purpose"), "text", src)
    _risk_signals(F)
    return F


def _risk_signals(F: Facts) -> None:
    """Risk facts computed from the section facts (the RM judges them; the draft only states them)."""
    lev, dscr, ltv = F.get("leverage"), F.get("dscr"), F.get("ltv")
    for f in (lev, dscr, ltv, F.get("utilisation"), F.get("revenue_growth")):
        if f:
            F.add("risks", f["key"] + "_r", f["label"], f["value"], f["unit"], f["source"], f.get("derived"))
    cov = F.get("collateral_type")
    if cov:
        F.add("risks", "collateral_r", "Collateral", cov["value"], "text", cov["source"])


# ---------------------------------------------------------------------------------------------- prepared UAE cases

def from_case(c: dict[str, Any], style: dict[str, Any] | None = None) -> Facts:
    F = Facts(c.get("currency", "AED"), style)
    src = f"Proposal {c['case_id']} ({c['file_name']})"
    fin = c["financials"]
    F.add("obligor", "name", "Borrower", c["borrower"], "text", src)
    F.add("obligor", "group", "Group", c["group"], "text", src)
    F.add("obligor", "profile", "Profile", c["profile"], "text", src)
    F.add("obligor", "sector", "Sector", c["sector"], "text", src)
    F.add("obligor", "rating", "Internal rating", c["rating"], "text", src)
    F.add("obligor", "tier", "Tier", c["tier"], "text", src)
    F.add("obligor", "segment_u", "Business unit", c["rm"], "text", src)
    for i, item in enumerate(c["request_summary"], start=1):
        F.add("request", f"req_{i}", f"Request item {i}", item, "text", src)
    tot = c["stated_totals"]
    F.add("request", "total_existing", "Total existing limits", tot["existing"], "ccy m", src)
    F.add("request", "total_proposed", "Total proposed limits", tot["proposed"], "ccy m", src)
    F.add("request", "total_change", "Increase in total limits", round(tot["proposed"] - tot["existing"], 1), "ccy m", src,
          "total proposed - total existing")
    gc = c.get("group_cap")
    if gc:
        F.add("facilities", "cap_existing", "Group exposure cap", gc["existing"], "ccy m", src)
        F.add("facilities", "cap_proposed", "Proposed group exposure cap", gc["proposed"], "ccy m", src)
        F.add("facilities", "group_after", "Group exposure after this request", gc["group_exposure_after"], "ccy m", src)
    for i, f in enumerate(c["facilities"], start=1):
        F.add("facilities", f"fac_{i}", f["name"], f"{f['name']}: {F.display(f['existing'], 'ccy m')} existing, "
              f"{F.display(f['proposed'], 'ccy m')} proposed, {f['bps']} bps", "text", src)
    F.add("facilities", "fees", "Upfront fees", c.get("fees_upfront"), "ccy m", src)
    for key, label in (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("debt_service", "Debt service"), ("net_debt", "Net debt")):
        F.add("financials", key, label, fin.get(key), "ccy m", src)
    if fin.get("revenue") and fin.get("ebitda"):
        F.add("financials", "ebitda_margin", "EBITDA margin", _r(fin["ebitda"] / fin["revenue"]), "ratio", src, "EBITDA / revenue")
    if fin.get("ebitda") and fin.get("debt_service"):
        F.add("financials", "dscr", "DSCR", _r(fin["ebitda"] / fin["debt_service"], 2), "x", src, "EBITDA / debt service")
    if fin.get("ebitda") and fin.get("net_debt"):
        F.add("financials", "leverage", "Net debt/EBITDA", _r(fin["net_debt"] / fin["ebitda"], 2), "x", src, "net debt / EBITDA")
    if fin.get("backlog"):
        F.add("financials", "backlog", "Backlog", fin["backlog"], "ccy m", src)
        F.add("financials", "backlog_prior", "Backlog, prior year", fin.get("backlog_prior"), "ccy m", src)
        F.add("financials", "backlog_growth", "Backlog growth (stated)", fin.get("backlog_growth_stated"), "ratio", src)
        if fin.get("revenue"):
            F.add("financials", "backlog_cover", "Backlog / revenue", _r(fin["backlog"] / fin["revenue"], 1), "x", src, "backlog / revenue")
    for key, label in (("working_capital", "Working capital"), ("working_capital_prior", "Working capital, prior year"),
                       ("noncore_property", "Non-core property"), ("retentions_not_due", "Retentions not yet due"),
                       ("current_assets", "Current assets"), ("related_party_receivable", "Related-party receivable"),
                       ("goodwill_internal", "Internally generated goodwill"), ("shareholder_withdrawals", "Shareholder withdrawals")):
        F.add("financials", key, label, fin.get(key), "ccy m", src)
    for key, label in (("parent_related_party_share", "Related-party share of receivables (parent)"),
                       ("related_party_share_ca", "Related-party share of current assets"), ("receivables_over_1y", "Receivables over 1 year")):
        F.add("financials", key, label, fin.get(key), "ratio", src)
    if fin.get("cash_cycle_days"):
        F.add("financials", "cash_cycle", "Cash conversion cycle (days)", fin["cash_cycle_days"], "count", src)
    for k, (cust, share) in enumerate((fin.get("backlog_share") or {}).items(), start=1):
        F.add("business", f"backlog_share_{k}", f"Backlog share: {cust}", share, "ratio", src)
    for i, pr in enumerate(c.get("projects") or [], start=1):
        F.add("business", f"project_{i}", pr["name"], f"{pr['name']}: {pr['status']}", "text", src)
    ob = c.get("other_banks") or {}
    if ob:
        F.add("business", "other_banks", "New facilities at other banks", ob.get("new_facilities"), "ccy m", src)
        F.add("business", "other_banks_n", "Other banks", ob.get("banks"), "count", src)
        F.add("business", "facility_letters", "Facility letters obtained", ob.get("facility_letters"), "count", src)
    d = c.get("deposits") or {}
    F.add("conduct", "avg_balance", "Average deposit balance", d.get("avg_balance"), "ccy m", src)
    F.add("conduct", "flow_fees", "Flow fees p.a.", d.get("flow_fees"), "ccy m", src)
    F.add("conduct", "turnover", "Account turnover to revenue", d.get("turnover_to_revenue"), "ratio", src)
    if d.get("routing_required"):
        F.add("conduct", "routing_required", "Routing undertaking (times the limit)", d["routing_required"], "x", src)
        F.add("conduct", "routing_achieved", "Routing achieved (times the limit)", d.get("routing_achieved"), "x", src)
    if d.get("returned_cheque_note"):
        F.add("conduct", "returned_cheques", "Returned cheques (bureau)", d["returned_cheque_note"], "text", src)
    st = c.get("stress") or {}
    if st:
        F.add("risks", "peak_deficit", "Stressed peak cash deficit", st.get("peak_deficit"), "ccy m", src)
        F.add("risks", "peak_month", "Month of the peak deficit", st.get("peak_month"), "count", src)
        F.add("risks", "funded_lines", "Funded lines", st.get("funded_lines"), "ccy m", src)
    F.add("recommendation", "rec", "Relationship recommendation", c.get("recommendation"), "text", src)
    F.add("recommendation", "total_proposed_r", "Total proposed limits", tot["proposed"], "ccy m", src)
    F.add("recommendation", "rating_r", "Internal rating", c["rating"], "text", src)
    return F


def get_proposal(pid: str) -> dict[str, Any]:
    """A proposal record: the R11 proposals (DD-nn, user proposals), else the one deal registry over Data Domains (R12 deals, PL)."""
    from backend.dealdesk import proposals
    try:
        return proposals.get(pid)
    except KeyError:
        try:
            from backend.dealdesk.data import deals
            return deals.get(pid)
        except Exception:  # noqa: BLE001 - before Session E's registry
            raise KeyError(pid) from None


def memo_meta(pid: str) -> dict[str, Any]:
    """Bank, memo type, segment, currency and title for a proposal or a prepared case."""
    from backend.dealdesk import proposal_cases as pc
    from backend.dealdesk.house_style import corpus
    if pid in pc.CASES:
        c = pc.CASES[pid]
        kind, seg = corpus.classify(" ".join(c["request_summary"]), c["sector"])
        return {"pid": pid, "source": "case", "bank": "house-uae", "kind": kind, "segment": seg, "currency": c["currency"],
                "name": c["borrower"], "sector": c["sector"], "rating": c["rating"], "title": f"Credit Proposal: {c['borrower']}"}
    p = get_proposal(pid)
    ob = p["obligor"]
    _, seg = corpus.classify(p.get("purpose", ""), ob.get("sector", ""))
    kind = "increase" if ob.get("existing") else "new"
    ccy = p["ask"].get("currency", "SAR")
    bank = "house-uae" if ccy == "AED" else "house-ksa"
    return {"pid": pid, "source": "proposal", "bank": bank, "kind": kind, "segment": seg, "currency": ccy, "name": ob["name"],
            "sector": ob.get("sector", ""), "rating": ob.get("internal_rating", ""), "title": f"Credit proposal {pid}: {ob['name']}"}


def gather(pid: str, style: dict[str, Any] | None = None, with_engine: bool = True) -> Facts:
    from backend.dealdesk import proposal_cases as pc
    if pid in pc.CASES:
        return from_case(pc.CASES[pid], style)
    p = get_proposal(pid)
    analysis = None
    if with_engine:
        try:
            from backend.dealdesk import engine
            analysis = engine.analyse(p)
        except Exception:  # noqa: BLE001 - the engine needs the What-If domain; the draft stands on the proposal alone
            analysis = None
    return from_proposal(p, style, analysis)
