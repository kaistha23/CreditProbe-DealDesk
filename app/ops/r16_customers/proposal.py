"""R16 d: the bank-form proposal (PROPOSAL_ANATOMY): the business request ("Action requested", RM voice) and the full
reference proposal (business request + credit division comments + recommendation + signature blocks).

Per-customer content comes from cN.proposal_text(sp, bank) -> dict; this module lays it out the same way for all four.
"""
from __future__ import annotations

import pathlib
from typing import Any

from ops.r16_customers import fin, render
from ops.r16_customers.fin import fmt_date as D
from ops.r16_customers.ids import BANK


def m(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:,.{nd}f}"


def header_fields(sp, b, P) -> list[tuple[str, str]]:
    c = sp["co"]
    h = P["header"]
    return [("Unit / branch", f"{b['unit']} / {b['branch']}"), ("Customer", c["name"]), ("CIF / base no.", b.get("cif") or "New to bank"),
            ("Group", f"{c.get('group_name') or '—'} ({c.get('group_id') or '—'})"), ("Date account opened", D(b.get("opened")) if b.get("opened") else "—"),
            ("Related / connected party", h["related"]), ("Date", D(h["date"])), ("AO / RO", f"{b['rm']} / {b['ro']}"),
            ("Purpose code", b["purpose_code"]), ("Request type", h["type"]), ("Review date", D(b["review_date"])),
            ("Industry code", b["industry_code"]), ("Collateral code", b["collateral_code"]),
            ("Rating (existing / proposed)", f"{b['rating_existing']} / {b['rating_proposed']}"), ("CR number", c["cr_number"])]


def facilities_table(b) -> dict:
    rows = []
    # the bank form prints the sub-limits first and the total as the last row
    lims = [L for L in b["limits"] if L["level"] > 0] + [L for L in b["limits"] if L["level"] == 0]
    for L in lims:
        ind = "" if L["level"] <= 1 else "   "
        part = []
        if L.get("commission_pct_pa") is not None:
            part.append(f"Comm. {L['commission_pct_pa']:.2f}%" + (" p.q." if "quarter" in (L.get("particulars") or "") else " p.a."))
        if L.get("benchmark"):
            part.append(f"{L['benchmark']} + {L['spread_pct']:.2f}%, floor {L['floor_pct']:.2f}%")
        if L.get("tenor_text"):
            part.append(L["tenor_text"])
        if L.get("particulars") and "quarter" not in L["particulars"]:
            part.append(L["particulars"])
        rows.append([ind + L["limit_name"], m(L["existing_mn"]), m(L["outstanding_mn"]), m(L["proposed_mn"]),
                     "" if L.get("cash_margin_pct") in (None, 0.0) else f"{L['cash_margin_pct']:.0f}%", "; ".join(part)])
    # limit groups (level <= 1: the total and each general / project limit) shaded, as in the bank form
    bold = [i for i, L in enumerate(lims) if L["level"] <= 1]
    return {"cols": ["Facility (SAR m)", "Existing", "Outstanding", "Proposed", "Cash margin", "Particulars"], "rows": rows,
            "widths": [0.27, 0.085, 0.12, 0.095, 0.085, 0.345], "font": 7, "bold_rows": bold}


def cycle_table(sp, cols=("FY2024", "FY2025", "9M2026")) -> dict:
    """Working-capital cycle re-performed by credit (days on the period's revenue / cost of revenue, 9M on 273 days)."""
    fs = sp["fs"]
    def days(c):
        return 273 if c.startswith("9M") else 365
    rows = []
    def add(label, f):
        rows.append([label] + [f(fs[c], days(c)) for c in cols])
    add("Receivable days (trade receivables / revenue)", lambda f, d: f"{d * f['trade_receivables'] / f['revenue']:.0f}")
    if any((fs[c].get("contract_assets") or 0) + (fs[c].get("retention_receivables") or 0) > 0 for c in cols):
        add("Days incl. contract assets and retention", lambda f, d: f"{d * (f['trade_receivables'] + (f.get('contract_assets') or 0) + (f.get('retention_receivables') or 0)) / f['revenue']:.0f}")
    add("Inventory days (inventory / cost of revenue)", lambda f, d: f"{d * f['inventory'] / f['cost_of_sales']:.0f}")
    add("Payable days (trade payables / cost of revenue)", lambda f, d: f"{d * f['trade_payables'] / f['cost_of_sales']:.0f}")
    add("Cash cycle (days)", lambda f, d: f"{d * (f['trade_receivables'] / f['revenue'] + (f['inventory'] - f['trade_payables']) / f['cost_of_sales']):.0f}")
    add("Trade receivables, % of current assets", lambda f, d: f"{100 * f['trade_receivables'] / f['current_assets']:.0f}%")
    add("Interest cover (EBITDA / finance cost)", lambda f, d: f"{f['ebitda'] / f['finance_cost']:.1f}x")
    return {"cols": ["Re-performed by credit"] + list(cols), "rows": rows, "widths": [0.4] + [0.6 / len(cols)] * len(cols)}


def numbered(items: list[str], start: int = 1) -> list[str]:
    return [f"{i}. {t}" for i, t in enumerate(items, start)]


def flat(items: list) -> list[str]:
    """Security / T&C lists may be grouped per limit: {"group": "For the general limit (SAR 160.0m)", "items": [...]}."""
    out: list[str] = []
    for it in items:
        out += it["items"] if isinstance(it, dict) else [it]
    return out


def grouped_blocks(items: list, kind: str) -> list[dict]:
    """Per limit group (anatomy §2.4-2.5): a 'For …:' line, then the items; T&Cs numbered continuously across groups."""
    bl: list[dict] = []
    k = 1
    for it in items:
        grp, xs = (it["group"], it["items"]) if isinstance(it, dict) else (None, [it])
        if grp:
            bl.append({"p": f"<b>{grp}:</b>", "html": True})
        if kind == "n":
            bl.append({"n": numbered(xs, k)})
            k += len(xs)
        else:
            bl.append({"b": xs})
    return bl


def fin_table(sp, cols=("FY2024", "FY2025", "9M2026")) -> dict:
    fs = sp["fs"]
    def r(k):
        return [fs[c].get(k) for c in cols]
    rows = []
    def add(label, vals, nd=1, pct=False, x=False):
        out = []
        for v in vals:
            if v is None:
                out.append("—")
            elif pct:
                out.append(f"{v:.1f}%")
            elif x:
                out.append(f"{v:.2f}x")
            else:
                out.append(f"{v:,.{nd}f}")
        rows.append([label] + out)
    rv = r("revenue")
    add("Revenue", rv)
    gr = [None] + [None if i == 0 else None for i in range(len(cols) - 1)]
    prev = {"FY2025": "FY2024", "FY2024": "FY2023"}
    gr = [100 * (fs[c]["revenue"] / fs[prev[c]]["revenue"] - 1) if c in prev and prev[c] in fs else None for c in cols]
    add("Revenue growth", gr, pct=True)
    add("Gross profit", r("gross_profit"))
    add("Gross margin", [100 * fs[c]["gross_profit"] / fs[c]["revenue"] for c in cols], pct=True)
    add("Operating profit", r("operating_profit"))
    add("Net profit", r("net_profit"))
    add("Net margin", [100 * fs[c]["net_profit"] / fs[c]["revenue"] for c in cols], pct=True)
    add("EBITDA", r("ebitda"))
    add("Total assets", r("total_assets"))
    add("Bank debt, short term", [fs[c]["short_term_borrowings"] + fs[c]["current_portion_ltd"] for c in cols])
    add("Bank debt, long term", r("long_term_borrowings"))
    add("Net worth (TNW)", r("total_equity"))
    add("Leverage (TL / TNW)", [fs[c]["total_liabilities"] / fs[c]["total_equity"] for c in cols], x=True)
    add("Gearing (bank debt / TNW)", [(fs[c]["short_term_borrowings"] + fs[c]["current_portion_ltd"] + fs[c]["long_term_borrowings"]) / fs[c]["total_equity"] for c in cols], x=True)
    add("Working capital", [fs[c]["current_assets"] - fs[c]["current_liabilities"] for c in cols])
    add("Current ratio", [fs[c]["current_assets"] / fs[c]["current_liabilities"] for c in cols], x=True)
    add("Operating cash flow", [fs[c].get("operating_cash_flow") for c in cols])
    return {"cols": ["SAR m"] + list(cols), "rows": rows, "widths": [0.4] + [0.6 / len(cols)] * len(cols)}


def business_request_blocks(sp, b, P) -> list[dict]:
    n = iter(range(1, 30))
    bl: list[dict] = [{"h": f"{next(n)}. Action requested"}, {"p": P["action"]},
                      {"h": f"{next(n)}. Facilities"}, {"table": facilities_table(b)}, {"p": P.get("fees", "")},
                      {"h": f"{next(n)}. Security and support"}, *grouped_blocks(P["security"], "b"),
                      {"h": f"{next(n)}. Terms and conditions"}, *grouped_blocks(P["tnc"], "n")]
    if b.get("group_exposure"):
        bl += [{"h": f"{next(n)}. Group exposure"},
               {"table": {"cols": ["Entity", "Funded existing", "Total existing", "Funded proposed", "Total proposed", "Outstanding"],
                          "rows": [[g["entity_name"], m(g["funded_existing_mn"]), m(g["total_existing_mn"]), m(g["funded_proposed_mn"]),
                                    m(g["total_proposed_mn"]), m(g["outstanding_mn"])] for g in b["group_exposure"]]
                          + [["Group total", m(sum(g["funded_existing_mn"] for g in b["group_exposure"])), m(sum(g["total_existing_mn"] for g in b["group_exposure"])),
                              m(sum(g["funded_proposed_mn"] for g in b["group_exposure"])), m(sum(g["total_proposed_mn"] for g in b["group_exposure"])),
                              m(sum(g["outstanding_mn"] for g in b["group_exposure"]))]], "bold_last": True,
                          "widths": [0.3, 0.14, 0.14, 0.14, 0.14, 0.14]}}]
    bl += [{"p": x} for x in P.get("references", [])]
    bl += [{"h": f"{next(n)}. Background"}] + [{"p": x} for x in P["background"]]
    if P.get("shareholders"):
        bl += [{"table": {"cols": ["Shareholder", "Born", "Nationality", "Share", "UBO"], "rows": P["shareholders"], "widths": [0.4, 0.12, 0.16, 0.16, 0.16]}}]
    bl += [{"h": f"{next(n)}. Relationship with the Bank"}] + [{"p": x} for x in P["relationship"]]
    if P.get("conduct_table"):
        bl += [{"table": P["conduct_table"]}]
    if P.get("projects"):
        bl += [{"h": f"{next(n)}. Status of financed projects"}] + [{"table": P["projects_table"]}] + [{"p": x} for x in P["projects"]]
    bl += [{"h": f"{next(n)}. Financials (as per audited and in-house statements)"}, {"table": fin_table(sp)}]
    au = sp.get("audit") or {}
    if au:
        yrs = sorted(au)
        bl += [{"p": "Auditor: " + "; ".join(f"{y} {au[y].get('auditor', '—')}, {str(au[y].get('opinion', 'opinion not stated')).lower()}"
                                    + (f" (signed {D(au[y]['signed'])})" if au[y].get("signed") else "") for y in yrs)
                + (f". 9M2026 in-house, prepared by {sp['inhouse_by']} (unaudited)." if sp.get("inhouse_by") else ".")}]
    bl += [{"h": f"{next(n)}. RM's justification"}] + [{"p": x} for x in P["justification"]]
    bl += [{"sig": [(b["rm"], "Relationship Manager"), (P["unit_head"], "Unit Head, " + b["unit"])]}]
    return bl


def credit_blocks(P) -> list[dict]:
    bl: list[dict] = [{"pagebreak": 1}, {"h": "CREDIT DIVISION COMMENTS"},
                      {"p": "Independent review of the business request against the documents on file and the Bank's own records. "
                            "Figures in SAR million unless stated; prior period in brackets."}]
    for title, items in P["credit"]:
        bl.append({"h": title})
        for it in items:
            if isinstance(it, dict):
                bl.append(it)
            elif isinstance(it, list):
                bl.append({"b": it, "html": True})
            else:
                bl.append({"p": it, "html": True})
    bl += [{"h": "Key strengths"}, {"b": P["strengths"]}]
    bl += [{"h": "CREDIT DIVISION RECOMMENDATION"}, {"p": P["recommendation_lead"], "html": True}]
    bl += [{"n": numbered(P["recommendation"]), "html": True}]
    bl += [{"h2": "Additional conditions (prior to limit loading unless stated)"}, {"n": [f"{chr(96 + i)}) {t}" for i, t in enumerate(P["conditions"], 1)], "html": True}]
    bl += [{"sig": [(P["analyst"], "Credit Analyst"), (P["vp"], "VP Credit"), ("", "Chief Credit Officer")]},
           {"h2": "CRO review / comments"}, {"p": " "}, {"h2": "Credit committee approval / instructions"},
           {"p": f"Approval authority: {P['authority']}."}, {"sig": [("", "Chairman, Credit Committee"), ("", "Member"), ("", "Member")]}]
    return bl


def business_request_model(sp, b, P) -> dict:
    return {"title": "CREDIT PROPOSAL — ACTION REQUESTED", "subtitle": f"{sp['co']['name']} · {P['header']['type']}", "style": "proposal",
            "issuer": BANK, "issuer_lines": [f"{b['unit']} · business request to Credit", f"Credit file request {P['cfr']}"],
            "ref": f"Date {D(P['header']['date'])} · RM {b['rm']}", "fields": header_fields(sp, b, P), "blocks": business_request_blocks(sp, b, P)}


def reference_model(sp, b, P) -> dict:
    mdl = business_request_model(sp, b, P)
    mdl["title"] = "CREDIT PROPOSAL — REFERENCE (BUSINESS REQUEST, CREDIT COMMENTS, RECOMMENDATION)"
    mdl["blocks"] = mdl["blocks"] + credit_blocks(P)
    return mdl


def br_fields(sp, b, P) -> dict:
    lim = [L for L in b["limits"] if L["level"] == 2]
    return {"customer_name": sp["co"]["name"], "cr_number": sp["co"]["cr_number"], "cif": b.get("cif") or "", "request_date": P["header"]["date"],
            "rm": b["rm"], "action_requested": P["action"], "total_existing": fin.sar(b["limits"][0]["existing_mn"]),
            "total_proposed": fin.sar(b["limits"][0]["proposed_mn"]),
            "facilities": [{"limit": L["limit_name"], "existing": fin.sar(L["existing_mn"]), "outstanding": fin.sar(L["outstanding_mn"]),
                            "proposed": fin.sar(L["proposed_mn"]), "cash_margin_pct": L.get("cash_margin_pct"),
                            "pricing": (f"{L['benchmark']} + {L['spread_pct']:.2f}%" if L.get("benchmark") else (f"{L['commission_pct_pa']:.2f}%" if L.get("commission_pct_pa") is not None else "")),
                            "tenor": L.get("tenor_text", "")} for L in lim],
            "security": [{"item": s} for s in flat(P["security"])], "conditions": [{"item": t} for t in flat(P["tnc"])]}


def write(sp, b, P, folder: pathlib.Path, br_alone: bool, images: bool = True) -> dict:
    out: dict[str, Any] = {}
    ref = reference_model(sp, b, P)
    (folder / "reference").mkdir(parents=True, exist_ok=True)
    render.docx(ref, folder / "reference" / "reference_proposal.docx")
    render.pdf(ref, folder / "reference" / "reference_proposal.pdf")
    out["reference"] = {"docx": "reference/reference_proposal.docx", "pdf": "reference/reference_proposal.pdf"}
    if br_alone:
        br = business_request_model(sp, b, P)
        d = folder / "business_request"
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            f.unlink()
        render.docx(br, d / "business_request.docx")
        render.pdf(br, d / "business_request.pdf")
        imgs = []
        if images:
            from pypdf import PdfReader
            n = len(PdfReader(str(d / "business_request.pdf")).pages)
            for pg in range(1, n + 1):
                img = render.photo(render.page_png(d / "business_request.pdf", pg), seed=f"br-{sp['key']}-{pg}", mode="photo" if pg % 2 else "scan")
                render.save_jpg(img, d / f"business_request_p{pg}.jpg")
                imgs.append(f"business_request/business_request_p{pg}.jpg")
        out["business_request"] = {"docx": "business_request/business_request.docx", "pdf": "business_request/business_request.pdf", "images": imgs,
                                   "fields": br_fields(sp, b, P)}
    return out
