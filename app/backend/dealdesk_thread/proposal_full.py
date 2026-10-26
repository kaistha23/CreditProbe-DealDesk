"""The proposal in full, as the business submitted it (PLAN_R5 D5).

Every deal analysis (the screen, the Word report and the Playbook section) starts with this: the obligor
and its group, the rating and its date, every facility line with amount, currency, tenor, pricing, fees,
repayment, security, guarantees and covenants, the purpose, the RM, the existing exposure and the memo
reference. One builder, three renderings, so they never disagree.

Rating date: a proposal carries `obligor.rating_date` when the memo gives one; otherwise an existing
borrower's rating is the 2026Q2 book's (dated the quarter end, 2026-06-30) and a new-to-bank rating is
the one assigned in the credit memo on the date the proposal was received.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import fmt

FACILITY = {"term_loan": "Term finance", "revolver": "Revolving working capital", "performance_lg": "Performance LG",
            "financial_lg": "Financial LG", "trade_lc": "Trade LC"}
UNFUNDED = ("performance_lg", "financial_lg", "trade_lc")
COLLATERAL = {"cash": "Cash deposit", "real_estate": "Real estate", "plant_equipment": "Plant and equipment",
              "receivables": "Receivables", "shares": "Listed shares", "vehicles": "Vehicles", "corporate_guarantee": "Corporate guarantee"}
GUARANTEE = {"corporate": "Corporate", "personal": "Personal", "government": "Government", "kafalah": "Kafalah", "bank": "Bank"}
PRODUCT = {"asset_finance": "Asset finance", "working_capital": "Working capital", "term_loan": "Term finance", "trade": "Trade",
           "project_finance": "Project finance", "revolver": "Revolving credit", "lg": "Letter of guarantee", "lc": "Letter of credit"}
AS_OF_BOOK = "2026-06-30"
LINES = {"cash_management": "cash management", "payroll": "payroll", "fx": "FX", "trade": "trade", "deposits": "deposits"}


def rating_date(p: dict[str, Any]) -> tuple[str, str]:
    ob = p["obligor"]
    if ob.get("rating_date"):
        return ob["rating_date"], "credit memo"
    if ob.get("existing"):
        return AS_OF_BOOK, "2026Q2 book"
    return p.get("received", ""), "new to bank, credit memo"


def _repayment(t: dict[str, Any]) -> str:
    if t["facility_type"] in UNFUNDED:
        return "Contingent: no scheduled repayment; expires at maturity"
    if t["facility_type"] == "revolver":
        return f"Revolving, {fmt.num(t.get('utilisation_pct', 100))}% expected utilisation, repaid at maturity"
    g = int(t.get("grace_years", 0))
    grace = f" after {g} grace year{'s' if g != 1 else ''}" if g else ""
    a = t.get("amortisation", "equal")
    if a == "bullet":
        return "Bullet at maturity"
    if a == "balloon":
        return f"Equal instalments{grace}, {fmt.num(t.get('balloon_pct', 0))}% balloon at maturity"
    if a == "sculpted":
        return f"Sculpted to cash flow{grace}"
    return f"Equal annual instalments{grace}"


def _base(t: dict[str, Any]) -> str:
    return "SOFR" if t["currency"] == "USD" else "SAIBOR"


def facility_lines(p: dict[str, Any], t: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The proposed facility lines (funded and unfunded parts are separate lines, `DD-nn-F` / `DD-nn-U`)."""
    t = t or p["ask"]
    sec = p["security"]
    coll = {c["collateral_id"]: c for c in sec.get("collateral", [])}
    pledged = [coll[c] for c in t.get("collateral_ids", []) if c in coll]
    security = [f"{COLLATERAL.get(c['type'], c['type'])} {fmt.amount(c['value'], c.get('currency', 'SAR'))}"
                f" (valued {c.get('valuation_date', '')})" for c in pledged]
    if float(t.get("cash_margin_pct", 0) or 0):
        security.append(f"Cash margin {fmt.num(t['cash_margin_pct'])}% of the amount")
    guar = []
    for g in sec.get("guarantees", []):
        if g.get("offered_in_ask") or g["guarantee_id"] == t.get("guarantee_id"):
            cov = t.get("guarantee_coverage_pct") if g["guarantee_id"] == t.get("guarantee_id") else g.get("coverage_pct")
            guar.append(f"{GUARANTEE.get(g['type'], g['type'])} guarantee from {g.get('guarantor') or 'the guarantor'}"
                        f" ({g.get('guarantor_rating', 'unrated')}), {fmt.num(cov)}% cover")
    covs = [f"{c['type']} {('≥ ' if 'DSCR' in c['type'] or 'cover' in c['type'].lower() else '≤ ')}{fmt.times(c['threshold'])}"
            if isinstance(c.get("threshold"), (int, float)) else str(c.get("type")) for c in sec.get("covenants", [])]
    ftype = t["facility_type"]
    funded = 0.0 if ftype in UNFUNDED else float(t.get("funded_share_pct", 100)) / 100
    parts = []
    if funded > 0:
        parts.append(("F", ftype, float(t["amount"]) * funded))
    if funded < 1:
        parts.append(("U", ftype if ftype in UNFUNDED else t.get("unfunded_type", "performance_lg"), float(t["amount"]) * (1 - funded)))
    out = []
    for suffix, kind, amt in parts:
        unf = kind in UNFUNDED
        pricing = (f"{fmt.bps(t.get('commission_bps', 0))} commission p.a." if unf
                   else f"{_base(t)} + {fmt.bps(t['margin_bps'])}{' (fixed)' if t.get('rate_type') == 'fixed' else ''}")
        fees = [f"Upfront {fmt.bps(t.get('upfront_fee_bps', 0))}"]
        if not unf and (ftype == "revolver" or float(t.get("commitment_fee_bps", 0) or 0)):
            fees.append(f"commitment {fmt.bps(t.get('commitment_fee_bps', 0))} on undrawn")
        if float(t.get("prepayment_fee_bps", 0) or 0):
            fees.append(f"prepayment {fmt.bps(t['prepayment_fee_bps'])}")
        out.append({
            "line_id": f"{p['proposal_id']}-{suffix}", "facility": FACILITY.get(kind, kind),
            "structure": str(t.get("structure", "")).capitalize(), "currency": t["currency"],
            "amount": fmt.amount(amt, t["currency"]), "amount_value": amt,
            "tenor": f"{int(t['tenor_years'])} years", "pricing": pricing, "fees": ", ".join(fees),
            "repayment": _repayment({**t, "facility_type": kind}),
            "security": "; ".join(security) or "Unsecured",
            "guarantees": "; ".join(guar) or "None",
            "covenants": ("No financial covenants" if t.get("covenant_package") == "none" and not covs else
                          f"{str(t.get('covenant_package', 'standard')).capitalize()} package: " + ("; ".join(covs) if covs else "no named covenants")),
        })
    return out


def _long_lines(p: dict[str, Any]) -> list[dict[str, Any]]:
    """PLAN_R6 D1: a long form with several facility lines shows each line with its own amount, tenor, pricing and fees."""
    ask = p["ask"]
    out = []
    for i, ln in enumerate(p.get("facility_lines_long") or [], start=1):
        ft = ln.get("facility_type") or "term_loan"
        t = {**ask, **{k: v for k, v in ln.items() if v not in (None, "") and k != "purpose"},
             "funded_share_pct": 0 if ft in UNFUNDED else 100, "unfunded_type": ft if ft in UNFUNDED else ask.get("unfunded_type", "performance_lg")}
        for k in ("amount", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps", "tenor_years", "grace_years"):
            try:
                t[k] = float(t.get(k) or 0) if k == "amount" else int(float(t.get(k) or 0))
            except (TypeError, ValueError):
                t[k] = 0
        t["tenor_years"] = t["tenor_years"] or 1
        for row in facility_lines(p, t):
            row["line_id"] = f"{p['proposal_id']}-L{i}"
            if ln.get("purpose"):
                row["purpose"] = str(ln["purpose"])
            out.append(row)
    return out


def full(p: dict[str, Any]) -> dict[str, Any]:
    """The complete proposal as submitted, as labelled, formatted rows."""
    ob = p["obligor"]
    rd, rsrc = rating_date(p)
    ext = ob.get("external_rating")
    group = ob.get("group_name") or "None"
    if ob.get("group_id"):
        group += f" ({ob['group_id']})"
    connected = [c for c in ob.get("connected_parties", []) if c != ob.get("obligor_id")]
    obligor_rows = [
        ("Obligor", f"{ob['name']}" + (f" ({ob['obligor_id']}, existing borrower)" if ob.get("existing") else " (new to bank)")),
        ("CR number", ob.get("cr_number") or "–"),
        ("Group", group),
        ("Connected parties", ", ".join(connected) if connected else "None besides the obligor"),
        ("Sector", f"{ob['sector']}" + (f" · {ob['sub_sector']}" if ob.get("sub_sector") else "") + (f" ({ob['sector_code']})" if ob.get("sector_code") else "")),
        ("Region", ob.get("region") or "–"),
        ("Internal rating", f"{ob['internal_rating']}, rated {rd} ({rsrc})"),
        ("External rating", ext or "Unrated"),
        ("Master-scale PD", fmt.pct(ob.get("pd_master_scale"))),
        ("SIMAH", str(ob.get("simah_flag", "")).capitalize() or "–"),
    ]
    ex = ob.get("existing_facilities") or []
    existing = [{"facility_id": f.get("facility_id", ""), "product": PRODUCT.get(f.get("product", ""), str(f.get("product", "")).replace("_", " ").capitalize()),
                 "limit": fmt.sar(f.get("limit")), "drawn": fmt.sar(f.get("drawn")), "ead": fmt.sar(f.get("ead")),
                 "stage": f"Stage {f.get('stage')}" if f.get("stage") else "–"} for f in ex]
    anc = (p.get("business_case") or {}).get("ancillary_income_sar_mn_pa") or {}
    deal_rows = [
        ("Proposal", f"{p['proposal_id']} · received {p.get('received', '')} · status {str(p.get('status', '')).replace('_', ' ')}"),
        ("Purpose", p.get("purpose") or "–"),
        ("Relationship manager", f"{p.get('rm', '')} · {p.get('business_unit', '')}"),
        ("Existing exposure", fmt.sar(ob.get("existing_exposure_sar_mn") or 0) + (f" across {len(ex)} facilit{'ies' if len(ex) != 1 else 'y'}" if ex else "")),
        ("Ancillary business (RM projection, p.a.)", ", ".join(f"{LINES.get(k, k.replace('_', ' '))} {fmt.sar(v)}" for k, v in anc.items()) or "None"),
        ("Credit memo", f"{p.get('memo') or p['proposal_id'] + '.docx'}"),
    ]
    # PLAN_R6 D1: everything entered on the form shows here, and every default is stated
    yrs = (p.get("financials") or {}).get("years") or []
    if yrs:
        y = yrs[-1]
        deal_rows.insert(4, ("Financials (latest year)", f"{y.get('year')}: revenue {fmt.sar(y.get('revenue'))}, EBITDA {fmt.sar(y.get('ebitda'))}, "
                                                         f"total debt {fmt.sar(y.get('total_debt'))}, debt service {fmt.sar(y.get('debt_service'))}, "
                                                         f"net worth {fmt.sar(y.get('net_worth'))}"))
    sec = p.get("security") or {}
    if not sec.get("collateral") and not sec.get("guarantees"):
        deal_rows.append(("Security", "None offered"))
    if not sec.get("covenants"):
        deal_rows.append(("Covenants", "None proposed"))
    # PLAN_R6 D1 (D2 session): every long-form field is shown
    lf = p.get("long_form") or {}
    if lf:
        if ob.get("ownership"):
            obligor_rows.insert(4, ("Ownership", "; ".join(f"{o.get('holder')} {o.get('share')}" for o in ob["ownership"])))
        if ob.get("external_agency"):
            obligor_rows = [(a, f"{b} ({ob['external_agency']})" if a == "External rating" else b) for a, b in obligor_rows]
        if len(yrs) > 1:
            deal_rows = [r for r in deal_rows if r[0] != "Financials (latest year)"]
            for y in reversed(yrs):
                deal_rows.insert(4, (f"Financials {y.get('year')}", ", ".join(
                    f"{lab.lower() if lab != 'EBITDA' else lab} {fmt.sar(y.get(k))}" for k, lab in
                    (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("net_income", "Net income"), ("total_debt", "Total debt"),
                     ("cash", "Cash"), ("equity", "Equity"), ("operating_cash_flow", "Operating cash flow"), ("capex", "Capex"),
                     ("interest", "Interest"), ("debt_service", "Debt service")) if y.get(k) is not None)))
        total_coll = sum(float(c.get("value") or 0) for c in sec.get("collateral", []))
        amount = float(p["ask"].get("amount") or 0)
        for c in sec.get("collateral", []):
            ltv = f", LTV {fmt.num(round(100 * amount / total_coll, 1))}% on all collateral" if total_coll else ""
            deal_rows.append((f"Collateral {c['collateral_id']}", f"{COLLATERAL.get(c['type'], c['type'])} {fmt.amount(c['value'], c.get('currency', 'SAR'))}"
                              f", valued {c.get('valuation_date') or 'date not stated'}{ltv}"))
        for g in sec.get("guarantees", []):
            deal_rows.append((f"Guarantee {g['guarantee_id']}", f"{GUARANTEE.get(g['type'], g['type'])} from {g.get('guarantor')}, "
                              f"{fmt.num(g.get('coverage_pct'))}% cover" + (" (priced)" if g["guarantee_id"] == p["ask"].get("guarantee_id") else "")))
        deal_rows.append(("Assignment of receivables", "Yes" if sec.get("receivables_assignment") else "No"))
        deal_rows.append(("Cash margin", f"{fmt.num(p['ask'].get('cash_margin_pct') or 0)}% of the amount"))
        if sec.get("covenants"):
            deal_rows.append(("Covenants", "; ".join(f"{c['type']} {fmt.times(c['threshold'])}" for c in sec["covenants"])))
        if sec.get("conditions"):
            deal_rows.append(("Conditions", sec["conditions"]))
        if len(p.get("facility_lines_long") or []) > 1:
            deal_rows.append(("Pricing basis", f"{len(p['facility_lines_long'])} lines priced as one aggregate ask: "
                              f"{fmt.amount(amount, p['ask']['currency'])}, margin {fmt.bps(p['ask']['margin_bps'])} amount-weighted, "
                              f"longest tenor {int(p['ask']['tenor_years'])} years"))
    if p.get("assumed"):
        deal_rows.append(("Assumed", "; ".join(p["assumed"])))
    return {"title": "The proposal as submitted", "obligor": [{"label": a, "value": b} for a, b in obligor_rows],
            "facility_lines": (_long_lines(p) if len(p.get("facility_lines_long") or []) > 1 else facility_lines(p)), "deal": [{"label": a, "value": b} for a, b in deal_rows],
            "existing_facilities": existing, "memo_href": f"/api/v1/dealdesk/proposals/{p['proposal_id']}/memo.docx"}


LINE_COLUMNS = [("line_id", "Line"), ("facility", "Facility"), ("structure", "Structure"), ("amount", "Amount"), ("tenor", "Tenor"),
                ("pricing", "Pricing"), ("fees", "Fees"), ("repayment", "Repayment"), ("security", "Security"),
                ("guarantees", "Guarantees"), ("covenants", "Covenants")]

__all__ = ["full", "facility_lines", "rating_date", "LINE_COLUMNS", "FACILITY"]
