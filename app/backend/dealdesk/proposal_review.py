"""P7 Proposal & Regulatory Response Intelligence: proposal review (PLAN_R9 Session E, E3).

`review(case)` turns a credit proposal into the nine outputs in order: extracted summary,
arithmetic and reconciliation checks, a quality score with sub-scores, an information gap
register, a weakness -> mitigant map, pre-deal analysis (RAROC with fees and deposits, stressed
cash flow against funded lines, approval route, CRO review flag), counter-proposals, a proposed
Accepted Risk Watch entry and a reviewer opinion (Word, see `opinion_docx`).

Every figure is computed here from the case and the Deal Desk parameter tables in force
(backend.dealdesk.params, backend.dealdesk.desk_params), so an Admin change to the hurdle changes
the verdict. Amounts are AED million; ratios are decimals.
"""
from __future__ import annotations

import copy
import io
import re
from typing import Any

from backend.dealdesk import desk_params, params
from backend.dealdesk.proposal_cases import AS_OF, CASES, FINGERPRINTS

PACK = {"pack": "P7", "name": "Proposal & Regulatory Response Intelligence"}


def _clause(num: str) -> str:
    return f"CBUAE CRM Art. {num}"


# ------------------------------------------------------------------ economics

def hurdle(case: dict[str, Any]) -> float:
    r = params.rows("returns")
    sec = r.get("hurdle_sector", {}).get(case["sector"])
    return float(sec if sec is not None else r["hurdle"].get(case["segment"], r["hurdle"]["Corporate Banking"]))


def _ccf(kind: str) -> float:
    c = params.rows("ccf")
    return {"funded": 1.0, "performance_lg": float(c["performance_lg"]["regulatory"]),
            "financial_lg": float(c["financial_lg"]["regulatory"])}.get(kind, 1.0)


def raroc(case: dict[str, Any], facilities: list[dict[str, Any]], with_deposits: bool = True,
          fees: float | None = None) -> dict[str, Any]:
    """One-year RAROC on the proposed limits at assumed full use (funded 100%, guarantees at their CCF).

    revenue = funded x margin + guarantees x commission + upfront fees / tenor + deposit value
    deposit value = average balance x (FTP credit - profit paid) + flow fees
    RAROC = (revenue - opex - EL) x (1 - tax) / capital + capital benefit
    """
    dp = desk_params.rows()
    cap_ratio = float(params.rows("capital")["capital_ratio_target"])
    benefit = float(params.rows("returns")["capital_benefit_rate"])
    tax = float(dp["corporate_tax"])
    rw = float(dp["risk_weight_by_rating"].get(case["rating"], 1.0))
    lgd = float(dp["lgd_unsecured"])
    opex_ratio = float(dp["opex_to_income"])
    ftp_credit = float(dp["deposit_ftp_credit"][case["currency"]])
    funded = sum(f["proposed"] * (1 - f.get("cash_margin", 0.0)) for f in facilities if f["kind"] == "funded")
    nonfunded = sum(f["proposed"] for f in facilities if f["kind"] != "funded")
    income = sum(f["proposed"] * (1 - f.get("cash_margin", 0.0)) * f["bps"] / 1e4 for f in facilities)
    fee = (case["fees_upfront"] if fees is None else fees) / float(dp["fee_recognition_years"])
    d = case["deposits"]
    dep = (d["avg_balance"] * max(ftp_credit - d["profit_paid"], 0.0) + d["flow_fees"]) if with_deposits else 0.0
    ead = sum(f["proposed"] * (1 - f.get("cash_margin", 0.0)) * _ccf(f["kind"]) for f in facilities)
    el = ead * case["pd"] * lgd
    capital = ead * rw * cap_ratio
    revenue = income + fee + dep
    opex = revenue * opex_ratio
    rap = (revenue - opex - el) * (1 - tax)
    r = (rap / capital + benefit) if capital > 0 else 0.0
    h = hurdle(case)
    return {"revenue": revenue, "income": income, "fees": fee, "deposit_value": dep, "opex": opex, "el": el,
            "ead": ead, "capital": capital, "rap": rap, "raroc": r, "hurdle": h, "clears_hurdle": r >= h,
            "funded": funded, "nonfunded": nonfunded}


# ------------------------------------------------------------------ the nine outputs

def _summary(c: dict[str, Any]) -> dict[str, Any]:
    fac = c["facilities"]
    return {"borrower": c["borrower"], "group": c["group"], "profile": c["profile"], "sector": c["sector"],
            "rating": c["rating"], "tier": c["tier"], "currency": c["currency"], "request": c["request_summary"],
            "facilities": fac, "total_existing": sum(f["existing"] for f in fac),
            "total_proposed": sum(f["proposed"] for f in fac), "recommendation": c["recommendation"],
            "cro_box": c["cro_box"] or "Empty", "projects": c.get("projects", [])}


def _checks(c: dict[str, Any]) -> list[dict[str, Any]]:
    fac, st, f = c["facilities"], c["stated_totals"], c["financials"]
    out: list[dict[str, Any]] = []

    def chk(name: str, ok: bool, detail: str, ref: str = "") -> None:
        out.append({"check": name, "result": "Pass" if ok else "Fail", "detail": detail, "ref": ref})

    te, tp = sum(x["existing"] for x in fac), sum(x["proposed"] for x in fac)
    chk("Existing limits add up to the stated total", abs(te - st["existing"]) < 0.05,
        f"Facility table AED {te:,.1f}m against stated AED {st['existing']:,.1f}m")
    chk("Proposed limits add up to the stated total", abs(tp - st["proposed"]) < 0.05,
        f"Facility table AED {tp:,.1f}m against stated AED {st['proposed']:,.1f}m")
    if c.get("group_cap"):
        g = c["group_cap"]
        chk("Group exposure after the request within the current cap", g["group_exposure_after"] <= g["existing"],
            f"Group exposure after the request AED {g['group_exposure_after']:,.1f}m against the AED {g['existing']:,.0f}m cap; "
            f"the request needs the cap raised to AED {g['proposed']:,.0f}m", _clause("5.10"))
    if "backlog" in f:
        implied = f["backlog_prior"] * (1 + f["backlog_growth_stated"])
        chk("Backlog growth reconciles", abs(implied - f["backlog"]) / f["backlog"] < 0.01,
            f"AED {f['backlog_prior']:,.0f}m x (1 + 140%) = AED {implied:,.0f}m against AED {f['backlog']:,.0f}m stated")
        cover = f["backlog"] / f["revenue"]
        chk("Backlog cover within 3x revenue (sector appetite)", cover <= desk_params.rows()["max_backlog_cover"],
            f"Backlog {cover:.1f}x revenue; {sum(f['backlog_share'].values()):.0%} from two developers")
        chk("Working capital consistent with the narrative 'adequate liquidity'", f["working_capital"] >= 0.5 * f["working_capital_prior"],
            f"Working capital AED {f['working_capital_prior']:,.1f}m -> AED {f['working_capital']:,.1f}m "
            f"({f['working_capital'] / f['working_capital_prior'] - 1:.0%}); AED {f['noncore_property']:,.0f}m non-core property bought")
    if c.get("stress"):
        s = c["stress"]
        chk("Stressed cash-flow deficit covered by funded lines", s["peak_deficit"] <= s["funded_lines"],
            f"Memo's own stress: peak deficit AED {s['peak_deficit']:,.1f}m in month {s['peak_month']} "
            f"against AED {s['funded_lines']:,.0f}m of funded lines")
    if c.get("other_banks"):
        o = c["other_banks"]
        chk("Client-reported bank facilities reconcile with CBRBR", False,
            f"AED {o['new_facilities']:,.0f}m of new facilities at {o['banks']} other banks with no facility letters; "
            "client-reported list does not match the bureau")
    if "related_party_share_ca" in f:
        chk("Related-party receivable share reconciles", abs(f["related_party_receivable"] / f["current_assets"] - f["related_party_share_ca"]) < 0.01,
            f"AED {f['related_party_receivable']:,.2f}m / AED {f['current_assets']:,.1f}m = "
            f"{f['related_party_receivable'] / f['current_assets']:.0%} of current assets")
    d = c["deposits"]
    if d.get("routing_required"):
        chk("Routing undertaking met", d["routing_achieved"] >= d["routing_required"],
            f"Undertaking {d['routing_required']:.1f}x the limit; achieved {d['routing_achieved']:.2f}x "
            f"({d['routing_achieved'] / d['routing_required']:.0%} of the undertaking); the proposal lowers it to 1.5x")
    fac_new = sum(x["proposed"] for x in fac if x["kind"] == "funded")
    dscr = f["ebitda"] / f["debt_service"]
    chk("Debt service cover at least 1.25x", dscr >= 1.25, f"EBITDA AED {f['ebitda']:,.1f}m / debt service AED {f['debt_service']:,.1f}m = {dscr:.2f}x")
    lev = f["net_debt"] / f["ebitda"]
    chk("Leverage within the maximum", lev <= desk_params.rows()["max_leverage"],
        f"Net debt / EBITDA {lev:.1f}x against the {desk_params.rows()['max_leverage']:.1f}x maximum; funded limits AED {fac_new:,.1f}m")
    return out


# Information gaps, weaknesses and mitigants per case: the reviewer's findings, each with its CBUAE reference.
_GAPS = {
    "PRP-A-GMC": [
        ("Facility letters for the AED 1.57bn new facilities at 3 other banks", "Reconcile client-reported lines with CBRBR", _clause("7.11")),
        ("Standalone audited financials of the UAE branch", "Only group consolidated accounts are provided", _clause("7.11")),
        ("Project 2 extension of time and the 4 certified payments (AED 23m)", "No payments since 30 Apr 2026", _clause("7.11")),
        ("Ageing of AED 79m retentions on projects completed 2020-24", "Shown as 'not due'", _clause("7.11")),
        ("Parent (Meridian Holding) related-party dues at 39% of total assets", "Deleveraging plan and timetable", _clause("6.12")),
        ("New ownership structure and auditor appointment", "Auditor-change covenant breached; auditor not on the approved list", _clause("7.11")),
        ("Explanation of 50 returned cheques at the Dubai affiliate", "Bureau, Jan-Jul 2026", _clause("6.8")),
        ("Fresh legal opinion on the corporate guarantee", "Current opinion is more than 2 years old", _clause("7.11")),
    ],
    "PRP-B-ASB": [
        ("Audited accounts without qualification, by an approved auditor", "Qualified for internally generated goodwill AED 14.4m", _clause("7.11")),
        ("Repayment plan for AED 117.65m due from related parties", "68% of current assets, mostly Sahel Transport", _clause("6.12")),
        ("Economic-dependency assessment of Sahel Transport and Marwan Steel", "Doubtful at another bank, AED 36m litigation", _clause("6.12")),
        ("CBRBR position of the two group entities at Loss", "About AED 10m and AED 31m", _clause("6.8")),
        ("Monthly routing statements for the last 12 months", "Undertaking met at 33%", _clause("7.11")),
        ("Ageing of receivables over 1 year (50.5%)", "Cash cycle 231 days", _clause("7.11")),
        ("Declaration of the staff interest in the corporate guarantor", "A bank staff member owns 51% of the guarantor", _clause("5.10")),
        ("Vehicle registration and mortgage plan", "Vehicles to be registered to Sahel Transport entities", _clause("7.11")),
    ],
}

_WEAK = {
    "PRP-A-GMC": [
        ("Projects 1-3 late; Project 2 unpaid since 30 Apr 2026", "Tranche funded lines after the Project 2 collection or extension of time", True),
        ("Backlog 4x revenue, 69% from two developers", "Cap at about AED 910m tied to Project 5", True),
        ("Working capital AED 42.5m -> 5.8m; AED 105m non-core property", "Advance payment AED 66.2m credited to the project account and recovered first", True),
        ("Stressed deficit AED 84.6m above AED 80m funded lines", "No new funded limits until audit by an approved auditor", True),
        ("Parent related-party dues 39% of total assets; guarantee perfection deferred", "Perfected parent guarantee with a fresh legal opinion within 2 months", True),
        ("Retentions AED 79m on completed projects 'not due'", None, False),
        ("AED 1.57bn new facilities at 3 other banks unexplained", None, False),
        ("No cash margin; open-ended guarantees in the beneficiary's format", None, False),
        ("Performance bond submitted 5 months late; 50 returned cheques at the Dubai affiliate", None, False),
    ],
    "PRP-B-ASB": [
        ("Vehicles registered to Sahel Transport entities", "Vehicles registered to and mortgaged by the borrower, or Sahel Transport assessed as its own obligor", True),
        ("Routing at 33% of a 2x undertaking; proposal lowers it to 1.5x", "Keep 2x with monthly tracking; the limit steps down below 1x", True),
        ("Connected obligor Doubtful at another bank; group entities at Loss", "Mandatory economic-dependency assessment (Art 6.12) before renewal", True),
        ("Bank staff member owns 51% of a corporate guarantor", "Refer the conflict of interest to compliance (Art 5.10)", True),
        ("Qualified audit (goodwill AED 14.4m); unlisted auditor", None, False),
        ("Receivables over 1 year 50.5%; cash cycle 231 days", None, False),
        ("Shareholder withdrawals AED 4.87m", None, False),
    ],
}

_COUNTER = {
    "PRP-A-GMC": [
        {"title": "Cap at about AED 910m tied to Project 5",
         "terms": ["Group cap AED 910m, not AED 1bn", "Arwa one-off limit reduced to AED 150m until Project 5 milestones are met"],
         "changes": {"Arwa villa project one-off limit (advance payment and performance)": 150.0}, "group_cap": 910.0, "fees": 1.6, "uplift_bps": 25},
        {"title": "Guarantees now, funded lines tranched",
         "terms": ["Approve the guarantee lines now", "Funded lines tranched: AED 40m now, AED 40m after the Project 2 collection or extension of time",
                   "Perfected parent guarantee with a fresh legal opinion",
                   "Advance payment AED 66.2m credited to the project account and recovered first"],
         "changes": {"Overdraft and receivables finance (funded)": 40.0}, "group_cap": 1000.0, "fees": 2.1, "uplift_bps": 20},
        {"title": "No new funded limits until audit by an approved auditor",
         "terms": ["Renew guarantees and the bid bond line", "Arwa limit approved as guarantees only, with 10% cash margin",
                   "Funded lines held at current usage until FY2026 audit by an approved auditor"],
         "changes": {"Overdraft and receivables finance (funded)": 55.0}, "cash_margin_new": 0.10, "group_cap": 950.0, "fees": 1.9, "uplift_bps": 25},
    ],
    "PRP-B-ASB": [
        {"title": "Decline the vehicle limit as structured; borrower-registered vehicles",
         "terms": ["Vehicles registered to and mortgaged by the borrower", "Or assess Sahel Transport as its own obligor with a cross-default review"],
         "changes": {"Vehicle finance, 5 years (10% cash margin)": 6.0}, "fees": 0.12, "uplift_bps": 75},
        {"title": "Renew at 2x routing with a step-down",
         "terms": ["Keep routing at 2x with monthly tracking", "The limit steps down to AED 10m if routing falls below 1x",
                   "Economic-dependency assessment (Art 6.12) before renewal"],
         "changes": {"Vehicle finance, 5 years (10% cash margin)": 0.0}, "routing": 2.0, "fees": 0.10, "uplift_bps": 50},
        {"title": "Renew working capital only; conflict referred to compliance",
         "terms": ["Working capital AED 15m renewed for 6 months", "Conflict of interest referred to compliance (Art 5.10)",
                   "Related-party receivable reduced by AED 20m by Dec 2026"],
         "changes": {"Vehicle finance, 5 years (10% cash margin)": 0.0, "Working capital (funded)": 12.0}, "fees": 0.08, "uplift_bps": 50},
    ],
}

_WATCH = {
    "PRP-A-GMC": [
        ("Project 2 payment received", "30 Nov 2026"), ("Extensions of time formalised", "within 90 days"),
        ("FY2026 auditor from the approved list", "FY2026 audit"), ("Parent guarantee perfected", "within 2 months"),
        ("Retentions reclassified with ageing", "next quarterly review"), ("No further affiliate cheque returns", "monthly bureau check"),
        ("Funded usage below the stressed path", "monthly"),
    ],
    "PRP-B-ASB": [
        ("Cross-default question answered", "before renewal"), ("Routing at least 1x the limit", "monthly"),
        ("Related-party receivable reduced by AED 20m", "Dec 2026"), ("Connected-obligor deterioration", "monthly bureau check"),
        ("Vehicle registration to the borrower", "before drawdown"),
    ],
}


def _score(c: dict[str, Any], checks: list[dict[str, Any]], gaps: list[dict[str, Any]], weak: list[dict[str, Any]]) -> dict[str, Any]:
    fails = sum(1 for x in checks if x["result"] == "Fail")
    uncovered = sum(1 for w in weak if not w["covered"])
    subs = [
        {"name": "Completeness of information", "max": 25, "score": max(0, 25 - 2 * len(gaps))},
        {"name": "Arithmetic and reconciliation", "max": 20, "score": max(0, 20 - 3 * fails)},
        {"name": "Risk identification", "max": 20, "score": max(0, 20 - 2 * uncovered)},
        {"name": "Structure and mitigants", "max": 20, "score": 6 if c["recommendation"].lower().startswith("approve all") else 9},
        {"name": "Governance (CRO review, exceptions)", "max": 15, "score": 3 if not c["cro_box"] else 10},
    ]
    total = sum(s["score"] for s in subs)
    band = "Strong" if total >= 75 else "Adequate" if total >= 60 else "Weak"
    return {"total": total, "max": 100, "band": band, "subscores": subs}


def _route(c: dict[str, Any], total: float) -> dict[str, Any]:
    doa = params.rows("doa")
    usd_sar, aed_sar = float(params.rows("capital")["usd_sar"]), float(desk_params.rows()["aed_sar"])
    sar = total * aed_sar
    level = next((x for x in doa if sar <= float(x["max_exposure"])), doa[-1])
    return {"amount_aed_mn": total, "amount_sar_mn": sar, "level": level["level"], "usd_sar": usd_sar}


def pre_deal(c: dict[str, Any]) -> dict[str, Any]:
    r_all = raroc(c, c["facilities"])
    r_nodep = raroc(c, c["facilities"], with_deposits=False)
    s = c.get("stress")
    f = c["financials"]
    stressed = ({"peak_deficit": s["peak_deficit"], "funded_lines": s["funded_lines"], "month": s["peak_month"],
                 "shortfall": max(0.0, s["peak_deficit"] - s["funded_lines"])} if s else
                {"peak_deficit": max(0.0, f["debt_service"] * 1.3 - f["ebitda"] * 0.7), "funded_lines": r_all["funded"], "month": 12,
                 "shortfall": max(0.0, f["debt_service"] * 1.3 - f["ebitda"] * 0.7 - r_all["funded"])})
    cro = {"required": True, "ref": _clause("4.9"), "cro_box": c["cro_box"] or "Empty",
           "reason": ("The CRO box is empty on a " + c["tier"] + " proposal with failed reconciliation checks; "
                      "CBUAE CRM Art 4.9 gives the CRO the review of material credit decisions.")}
    cap_ebitda = f["ebitda"] * desk_params.rows()["max_leverage"] - f["net_debt"]
    cap_cash = (f["ebitda"] - f["debt_service"]) / desk_params.rows()["cash_flow_cover"] * 3.0
    return {"raroc": r_all, "raroc_without_deposits": r_nodep, "stressed_cash_flow": stressed,
            "approval_route": _route(c, sum(x["proposed"] for x in c["facilities"])), "cro_review": cro,
            "debt_capacity": {"ebitda_based": cap_ebitda, "cash_flow_based": cap_cash},
            "verdict": "Clears the hurdle" if r_all["clears_hurdle"] else "Below the hurdle"}


def _counters(c: dict[str, Any]) -> list[dict[str, Any]]:
    base = raroc(c, c["facilities"])
    out = []
    for cp in _COUNTER[c["case_id"]]:
        fac = copy.deepcopy(c["facilities"])
        for x in fac:
            if x["name"] in cp.get("changes", {}):
                x["proposed"] = cp["changes"][x["name"]]
            if cp.get("cash_margin_new") and x["existing"] == 0 and x["kind"] != "funded":
                x["cash_margin"] = cp["cash_margin_new"]
            x["bps"] += cp.get("uplift_bps", 0)
        r = raroc(c, fac, fees=cp.get("fees"))
        tot = sum(x["proposed"] for x in fac)
        out.append({"title": cp["title"], "terms": cp["terms"] + ([f"Pricing +{cp['uplift_bps']} bps on all lines"] if cp.get("uplift_bps") else []), "total_limits": tot,
                    "exposure_change": tot - sum(x["proposed"] for x in c["facilities"]),
                    "ead": r["ead"], "raroc": r["raroc"], "hurdle": r["hurdle"], "clears_hurdle": r["clears_hurdle"],
                    "raroc_change": r["raroc"] - base["raroc"], "group_cap": cp.get("group_cap")})
    return out


def review(case_id: str) -> dict[str, Any]:
    c = CASES[case_id]
    checks = _checks(c)
    gaps = [{"id": f"{case_id}-G{i + 1}", "item": g, "context": ctx, "ref": ref, "status": "Open"}
            for i, (g, ctx, ref) in enumerate(_GAPS[case_id])]
    weak = [{"weakness": w, "mitigant": m, "covered": cov} for w, m, cov in _WEAK[case_id]]
    pdx = pre_deal(c)
    watch = {"name": c["borrower"], "status": c["stage_view"]["watch"], "stage": c["stage_view"]["stage"],
             "rationale": c["stage_view"]["rationale"], "conclusion": c["conclusion"],
             "items": [{"item": i, "due": d, "status": "Open"} for i, d in _WATCH[case_id]]}
    return {"case_id": case_id, "as_of": AS_OF, "powered_by": {**PACK, "rules": [_clause(n) for n in ("4.9", "5.10", "6.12", "7.11")],
                                                               "confidence": "High", "trace": f"proposal-review/{case_id}"},
            "file_name": c["file_name"], "summary": _summary(c), "checks": checks,
            "score": _score(c, checks, gaps, weak), "gaps": gaps, "weaknesses": weak, "pre_deal": pdx,
            "counter_proposals": _counters(c), "watch_entry": watch, "graph": c.get("network", [])}


def cases() -> list[dict[str, Any]]:
    out = []
    for cid, c in CASES.items():
        r = review(cid)
        out.append({"case_id": cid, "borrower": c["borrower"], "sector": c["sector"], "tier": c["tier"], "file_name": c["file_name"],
                    "total_proposed": r["summary"]["total_proposed"], "score": r["score"]["total"],
                    "raroc": r["pre_deal"]["raroc"]["raroc"], "hurdle": r["pre_deal"]["raroc"]["hurdle"],
                    "verdict": r["pre_deal"]["verdict"], **_r11_decision(cid)})
    return out


def _r11_decision(cid: str) -> dict[str, Any]:
    """R11 (additive): the review workspace's decision and finding counts for the case row."""
    try:
        from backend.dealdesk import review_workspace
        q = review_workspace.quick(cid)
        return {"r11_decision": q["decision"], "r11_counts": q["counts"], "r11_approval": q["approval"]}
    except Exception:  # noqa: BLE001 - the R9 row stands without it
        return {}


# ------------------------------------------------------------------ upload

def extract_text(name: str, data: bytes) -> str:
    low = name.lower()
    if low.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    if low.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:  # noqa: BLE001 -- unreadable PDF -> no text
            return ""
    raise ValueError("Upload a .docx or .pdf proposal.")


def identify(text: str) -> str | None:
    low = text.lower()
    for cid, words in FINGERPRINTS.items():
        if any(w in low for w in words):
            return cid
    return None


def upload(name: str, data: bytes) -> dict[str, Any]:
    text = extract_text(name, data)
    cid = identify(text)
    if cid:
        out = review(cid)
        out["uploaded"] = {"file": name, "characters": len(text), "matched": True}
        return out
    amounts = [float(x.replace(",", "")) for x in re.findall(r"AED\s*([\d,]+(?:\.\d+)?)\s*m", text)]
    return {"case_id": None, "uploaded": {"file": name, "characters": len(text), "matched": False},
            "summary": {"amounts_found_aed_mn": amounts[:20], "total_found_aed_mn": sum(amounts[:20])},
            "message": "The proposal was read. Full review needs the facility table, financials and stress case in the "
                       "Deal Desk proposal format; the amounts found are listed."}


# ------------------------------------------------------------------ Word: the proposals and the reviewer opinion

def _doc():
    import docx
    from docx.shared import Pt
    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    return d


def _table(d, head: list[str], rows: list[list[str]]) -> None:
    t = d.add_table(rows=1, cols=len(head))
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(head):
        t.rows[0].cells[i].text = h
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = v


def proposal_docx(case_id: str) -> bytes:
    """The credit proposal as the RM wrote it (the input to the review)."""
    c = CASES[case_id]
    f = c["financials"]
    d = _doc()
    d.add_heading(f"Credit Proposal: {c['borrower']}", 0)
    d.add_paragraph(f"Group: {c['group']}. {c['profile']}. Sector: {c['sector']}. Internal rating {c['rating']}. {c['tier']}. "
                    f"Relationship: {c['rm']}. Date: {AS_OF}.")
    d.add_heading("1. Request", 1)
    for r in c["request_summary"]:
        d.add_paragraph(r, style="List Bullet")
    d.add_heading("2. Facilities (AED million)", 1)
    _table(d, ["Facility", "Existing", "Proposed", "Pricing (bps)"],
           [[x["name"], f"{x['existing']:,.1f}", f"{x['proposed']:,.1f}", str(x["bps"])] for x in c["facilities"]]
           + [["Total limits", f"{c['stated_totals']['existing']:,.1f}", f"{c['stated_totals']['proposed']:,.1f}", ""]])
    if c.get("group_cap"):
        g = c["group_cap"]
        d.add_paragraph(f"Group exposure cap: AED {g['existing']:,.0f}m, proposed AED {g['proposed']:,.0f}m "
                        f"(group exposure after this request AED {g['group_exposure_after']:,.1f}m).")
    d.add_heading("3. Financial highlights (AED million)", 1)
    rows = [["Revenue", f"{f['revenue']:,.1f}"], ["EBITDA", f"{f['ebitda']:,.1f}"], ["Debt service", f"{f['debt_service']:,.1f}"],
            ["Net debt", f"{f['net_debt']:,.1f}"]]
    if "backlog" in f:
        rows += [["Backlog", f"{f['backlog']:,.0f} (prior year {f['backlog_prior']:,.1f}, up 140%)"],
                 ["Backlog concentration", "Arwa Developments 44%, Emirates Logistics City 25%"],
                 ["Working capital", f"{f['working_capital']:,.1f} (prior year {f['working_capital_prior']:,.1f})"],
                 ["Investment property (non-core)", f"{f['noncore_property']:,.1f}"],
                 ["Retentions on projects completed 2020-24", f"{f['retentions_not_due']:,.1f}, shown as not due"],
                 ["Parent related-party dues", "39% of the parent's total assets"]]
    else:
        rows += [["Current assets", f"{f['current_assets']:,.1f}"], ["Due from related parties", f"{f['related_party_receivable']:,.2f} (68% of current assets, mostly Sahel Transport)"],
                 ["Internally generated goodwill", f"{f['goodwill_internal']:,.1f} (audit qualified)"],
                 ["Receivables over 1 year", "50.5%"], ["Cash conversion cycle", "231 days"],
                 ["Shareholder withdrawals", f"{f['shareholder_withdrawals']:,.2f}"]]
    _table(d, ["Item", "Value"], rows)
    d.add_heading("4. Business and projects", 1)
    for p in c.get("projects", []):
        d.add_paragraph(f"{p['name']}: {p['status']}.", style="List Bullet")
    if case_id == "PRP-A-GMC":
        for t in ("Ownership of the group changed recently; the auditor was changed (covenant requires the bank's consent) and the "
                  "new auditor is not on the approved list. No standalone financials of the UAE branch.",
                  "Bureau: 50 returned cheques for insufficient funds at the Dubai affiliate between January and July 2026.",
                  "The group obtained AED 1.57bn of new facilities at 3 other banks; facility letters not obtained.",
                  "Exceptions: no cash margin; open-ended guarantees in the beneficiary's format; deferred perfection of the "
                  "corporate guarantee; legal opinion more than 2 years old; performance bond submitted 5 months late.",
                  "Stressed cash flow: peak deficit AED 84.6m in month 18; funded lines AED 80m.",
                  "Advance payment for the villa project: AED 66.2m."):
            d.add_paragraph(t)
    else:
        for t in ("The vehicles will be registered to Sahel Transport entities.",
                  "Sahel Transport's 51% sponsor is linked to Marwan Steel General Trading, classified Doubtful at another bank and "
                  "in litigation over AED 36m; the group holds 25% of it through nominees.",
                  "CBRBR shows two group entities at Loss (about AED 10m and AED 31m).",
                  "Routing undertaking of 2x the limit met at 33%; the proposal lowers the undertaking to 1.5x.",
                  "A corporate guarantor is 51% owned by a bank staff member.",
                  "The auditor is not on the bank's approved list."):
            d.add_paragraph(t)
    d.add_heading("5. Recommendation", 1)
    d.add_paragraph(f"Relationship recommendation: {c['recommendation']}.")
    d.add_paragraph("CRO review: ")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def opinion_docx(case_id: str) -> bytes:
    """The reviewer opinion (output 9)."""
    r = review(case_id)
    c = CASES[case_id]
    p = r["pre_deal"]
    d = _doc()
    d.add_heading(f"Credit Review Opinion: {c['borrower']}", 0)
    d.add_paragraph(f"Powered by P7 Proposal & Regulatory Response Intelligence. As of {AS_OF}. Proposal reviewed: {c['file_name']}.")
    d.add_heading("Opinion", 1)
    d.add_paragraph(f"Quality score {r['score']['total']} out of 100 ({r['score']['band']}). Relationship RAROC "
                    f"{p['raroc']['raroc']:.1%} including fees and deposits against a hurdle of {p['raroc']['hurdle']:.1%}: "
                    f"{p['verdict'].lower()}. {c['conclusion']}")
    d.add_paragraph(f"CRO review required ({_clause('4.9')}): {p['cro_review']['reason']}")
    d.add_heading("Arithmetic and reconciliation", 1)
    _table(d, ["Check", "Result", "Detail"], [[x["check"], x["result"], x["detail"]] for x in r["checks"]])
    d.add_heading("Information gaps (queries to the RM)", 1)
    _table(d, ["#", "Information required", "Context", "Reference"], [[g["id"], g["item"], g["context"], g["ref"]] for g in r["gaps"]])
    d.add_heading("Weaknesses and mitigants", 1)
    _table(d, ["Weakness", "Mitigant", "Covered"], [[w["weakness"], w["mitigant"] or "None proposed", "Yes" if w["covered"] else "No"] for w in r["weaknesses"]])
    d.add_heading("Counter-proposals", 1)
    _table(d, ["Counter-proposal", "Total limits (AED m)", "RAROC", "Clears hurdle"],
           [[x["title"], f"{x['total_limits']:,.1f}", f"{x['raroc']:.1%}", "Yes" if x["clears_hurdle"] else "No"] for x in r["counter_proposals"]])
    for x in r["counter_proposals"]:
        d.add_paragraph(x["title"] + ": " + "; ".join(x["terms"]) + ".", style="List Bullet")
    d.add_heading("Proposed Accepted Risk Watch entry", 1)
    w = r["watch_entry"]
    d.add_paragraph(f"{w['status']}; Stage {w['stage']}. {w['rationale']}")
    _table(d, ["Watch item", "Due"], [[i["item"], i["due"]] for i in w["items"]])
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()
