"""Round A, step 2: check the file against the checklist. Rules, not the model.

Ported from the Credit Request Agent (docs/v5/reference/credit-request-agent.html): the market checklists CHECK (KSA, UAE,
each with the Bank's own data items), CONTENT (what a full business request rests on: the item, what cannot be assessed
without it, the documents it needs, its weight, critical or not, existing customers only), `completeness()` (the weighted
score and the gaps), the could-not-assess list (critical first, then by weight), the re-run delta ("20% → 35% (+15)") and
"Now covered since the last run".

    run(read_docs, market, existing, as_of, prev=None)   -> {received, missing, expired, status, comp, delta, now_covered, lines}
    gaps_md(check) / with_gaps(md, check)                -> the completeness line and "What this request could not assess"

R16's reader speaks its own document types (backend/dealdesk/intake/doctypes.py); R16_TO_CHECK maps them onto these ids so the
rule reader and the model reader are judged by the same list.
"""
from __future__ import annotations

import re
from typing import Any

BANK_DATA = [
    ("internal_rating", "Internal risk rating sheet"), ("relationship_profile", "Deposit and relationship profile"),
    ("approval_history", "Previous approval and covenant compliance"), ("group_structure", "Group structure"),
    ("guarantor_networth", "Guarantor net worth statement"), ("site_visit", "RM site visit report"),
]

CHECK: dict[str, list[tuple[str, str]]] = {
    "KSA": [
        ("request_letter", "Facility request letter (signed)"), ("cr", "Commercial Registration"), ("aoa", "Articles of Association"),
        ("owner_ids", "Owners' IDs"), ("vat_cert", "VAT certificate"), ("zakat_cert", "Zakat certificate"), ("nitaqat", "Nitaqat / GOSI certificate"),
        ("vat_returns", "VAT returns, last 12 months"), ("simah_company", "SIMAH report, company"), ("simah_owners", "SIMAH reports, owners"),
        ("audited_fs", "Audited financials, 2 years"), ("mgmt_accounts", "Management accounts, current year"), ("bank_statements", "Bank statements, 12 months"),
        ("ageing", "Receivables / payables ageing"), ("board_resolution", "Board / partners' resolution to borrow"),
        ("other_bank_letters", "Other banks' facility letters"), ("project_list", "Project list / backlog"), ("collateral_docs", "Collateral documents"),
        *BANK_DATA,
    ],
    "UAE": [
        ("request_letter", "Facility request letter (signed)"), ("trade_licence", "Trade licence"), ("moa", "Memorandum of Association"),
        ("owner_ids", "Owners' Emirates IDs / passports"), ("vat_cert", "VAT registration (TRN)"), ("vat_returns", "VAT returns, last 12 months"),
        ("aecb_company", "AECB report, company"), ("aecb_owners", "AECB reports, owners"), ("audited_fs", "Audited financials, 2 years"),
        ("mgmt_accounts", "Management accounts, current year"), ("bank_statements", "Bank statements, 12 months"), ("ageing", "Receivables / payables ageing"),
        ("board_resolution", "Board / partners' resolution to borrow"), ("other_bank_letters", "Other banks' facility letters"),
        ("project_list", "Project list / backlog"), ("collateral_docs", "Collateral documents"),
        *BANK_DATA,
    ],
}

#: what a full business request normally contains, the evidence each part needs (groups: all needed; within a group: any one),
#: and its weight. Verbatim from the reference page.
CONTENT: list[dict[str, Any]] = [
    {"sec": "Header", "item": "Proposed internal rating and PD against the previous rating", "cannot": "Propose a rating or PD, so pricing and approval authority cannot be set", "need": [["internal_rating"]], "w": 3, "crit": True},
    {"sec": "Header, 5", "item": "Verified legal identity, ownership and registration validity", "cannot": "Verify legal identity, ownership or registration validity", "need": [["cr", "trade_licence"]], "w": 2, "crit": True},
    {"sec": "1", "item": "The customer's signed request for the facilities", "cannot": "Confirm the ask against a signed customer request", "need": [["request_letter"]], "w": 2, "crit": True},
    {"sec": "3", "item": "Confirmation of borrowing powers and authorised signatories", "cannot": "Confirm borrowing powers and authorised signatories", "need": [["aoa", "moa"], ["board_resolution"]], "w": 1},
    {"sec": "3", "item": "Collateral and its valuation", "cannot": "Value the collateral or compute loan-to-value", "need": [["collateral_docs"]], "w": 1},
    {"sec": "3", "item": "Guarantor's net worth behind the personal guarantee", "cannot": "Assess what the personal guarantee is worth", "need": [["guarantor_networth"]], "w": 1},
    {"sec": "4", "item": "Exposure with other lenders and repayment history from the credit bureau", "cannot": "Show exposure with other banks, total leverage across lenders, or repayment history", "need": [["simah_company", "aecb_company"]], "w": 3, "crit": True},
    {"sec": "4", "item": "Other lenders' terms, covenants and security", "cannot": "Compare other lenders' terms, covenants and security", "need": [["other_bank_letters"]], "w": 1},
    {"sec": "4", "item": "Group structure, connected parties and group exposure", "cannot": "Assess group exposure and connected-party risk", "need": [["group_structure"]], "w": 1},
    {"sec": "5", "item": "Project backlog and revenue visibility", "cannot": "Assess backlog, revenue visibility or project concentration", "need": [["project_list"]], "w": 2},
    {"sec": "5", "item": "Site visit observations on operations and assets", "cannot": "Report independent observations of operations and assets", "need": [["site_visit"]], "w": 1},
    {"sec": "4", "item": "Account conduct: turnover, utilisation, excesses, returned cheques", "cannot": "Analyse turnover, utilisation, excesses or returned cheques", "need": [["bank_statements"]], "w": 3, "crit": True},
    {"sec": "4", "item": "Deposits, share of wallet and relationship RAROC", "cannot": "Show deposits, share of wallet or relationship RAROC against the hurdle", "need": [["relationship_profile"]], "w": 2, "existing_only": True},
    {"sec": "4", "item": "Covenant and condition compliance under the current approval", "cannot": "Test covenant compliance under the current approval", "need": [["approval_history"]], "w": 2, "existing_only": True},
    {"sec": "6", "item": "Two-year financial analysis from audited statements", "cannot": "Spread audited financials or compute leverage, margins, DSCR and cash flow", "need": [["audited_fs"]], "w": 3, "crit": True},
    {"sec": "6", "item": "Current-year trading since the last audit", "cannot": "Show current-year trading since the last audit", "need": [["mgmt_accounts"]], "w": 2},
    {"sec": "6", "item": "Revenue reconciled to VAT returns", "cannot": "Reconcile revenue to VAT filings", "need": [["vat_returns"]], "w": 1},
    {"sec": "6, 7", "item": "Receivable quality and debtor concentration", "cannot": "Assess receivable quality, overdue balances or debtor concentration", "need": [["ageing"]], "w": 2},
    {"sec": "7", "item": "Owners' personal credit history", "cannot": "Check the owners' personal credit history", "need": [["simah_owners", "aecb_owners"]], "w": 1},
    {"sec": "8", "item": "Owners' KYC", "cannot": "Complete KYC on the owners", "need": [["owner_ids"]], "w": 1},
    {"sec": "8", "item": "Tax and regulatory compliance (VAT, Zakat, Saudization)", "cannot": "Confirm VAT, Zakat and Saudization compliance", "need": [["vat_cert"], ["zakat_cert"], ["nitaqat"]], "w": 1},
]

#: R16 document types (backend/dealdesk/intake/doctypes.py) onto the checklist ids
R16_TO_CHECK: dict[str, tuple[str, ...]] = {
    "facility_request_letter": ("request_letter",), "commercial_registration": ("cr",), "articles_of_association": ("aoa",),
    "national_id": ("owner_ids",), "vat_certificate": ("vat_cert",), "zakat_certificate": ("zakat_cert",), "nitaqat_certificate": ("nitaqat",),
    "vat_returns": ("vat_returns",), "simah_company": ("simah_company",), "simah_consumer": ("simah_owners",), "audited_fs": ("audited_fs",),
    "inhouse_fs": ("mgmt_accounts",), "bank_statement": ("bank_statements",), "receivables_ageing": ("ageing",), "payables_ageing": ("ageing",),
    "board_resolution": ("board_resolution",), "other_bank_offer_letter": ("other_bank_letters",), "other_bank_statement": ("other_bank_letters",),
    "project_list": ("project_list",), "valuation_report": ("collateral_docs",), "title_deed": ("collateral_docs",),
    "insurance_policy": ("collateral_docs",), "site_visit_report": ("site_visit",), "personal_net_worth": ("guarantor_networth",),
}

LABEL: dict[str, str] = {}
for _m in ("KSA", "UAE"):  # the KSA wording first; the UAE-only ids added
    for _k, _v in CHECK[_m]:
        LABEL.setdefault(_k, _v)
ALL_IDS = tuple(LABEL)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ids_for(market: str) -> list[tuple[str, str]]:
    return CHECK.get(market, CHECK["KSA"])


def run(docs: list[dict[str, Any]], market: str, existing: bool, as_of: str, prev: dict[str, Any] | None = None) -> dict[str, Any]:
    """docs: [{id, name, result: {checklist_ids, expiry_date, ...}}] (the reconciled read). Received / missing / expired per
    checklist line (expired: a stated expiry date before as_of), then the completeness score and, against `prev` (the
    previous run's comp), the delta and what is now covered."""
    have: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        for k in (d.get("result") or {}).get("checklist_ids") or []:
            have.setdefault(k, []).append(d)
    out: dict[str, Any] = {"received": [], "missing": [], "expired": [], "status": {}, "lines": []}
    for k, label in ids_for(market):
        ds = have.get(k)
        if not ds:
            out["status"][k] = {"st": "missing", "label": label}
            out["missing"].append(label)
            out["lines"].append({"id": k, "label": label, "status": "missing", "docs": [], "note": ""})
            continue
        exp = next((d for d in ds if ISO.match(str(d["result"].get("expiry_date") or "")) and str(d["result"]["expiry_date"]) < as_of), None)
        if exp is not None and all(d is exp or (ISO.match(str(d["result"].get("expiry_date") or "")) and str(d["result"]["expiry_date"]) < as_of)
                                   for d in ds):
            note = f"{exp['id']}, expired {exp['result']['expiry_date']}"
            out["status"][k] = {"st": "expired", "label": label, "note": note}
            out["expired"].append(f"{label} ({note})")
            out["lines"].append({"id": k, "label": label, "status": "expired", "docs": [d["id"] for d in ds], "note": note})
        else:
            out["status"][k] = {"st": "ok", "label": label}
            out["received"].append(f"{label} ({', '.join(d['id'] for d in ds)})")
            out["lines"].append({"id": k, "label": label, "status": "received", "docs": [d["id"] for d in ds], "note": ""})
    out["total"] = len(ids_for(market))
    out["comp"] = completeness(out, market, existing)
    out["comp"]["gaps"] = sorted_gaps(out["comp"])
    out.update(delta(prev, out["comp"]))
    return out


def completeness(out: dict[str, Any], market: str, existing: bool) -> dict[str, Any]:
    keys = {k for k, _ in ids_for(market)}
    tot = got = 0.0
    gaps: list[dict[str, Any]] = []
    for c in CONTENT:
        if c.get("existing_only") and not existing:
            continue
        groups = [[k for k in g if k in keys] for g in c["need"]]
        groups = [g for g in groups if g]
        if not groups:
            continue
        tot += c["w"]
        res = []
        for g in groups:
            st = [out["status"].get(k) or {"st": "missing", "label": k} for k in g]
            ok = next((x for x in st if x["st"] == "ok"), None)
            res.append({"st": "ok"} if ok else (next((x for x in st if x["st"] == "expired"), None) or st[0]))
        share = sum(1 if r["st"] == "ok" else 0.5 if r["st"] == "expired" else 0 for r in res) / len(res)
        got += c["w"] * share
        bad = [r for r in res if r["st"] != "ok"]
        if bad:
            because = "; ".join(f"{r['label']} expired ({r['note']})" if r["st"] == "expired" else f"{r['label']} missing" for r in bad)
            blocking = [r["label"] for r in bad]
            gaps.append({**{k: c[k] for k in ("sec", "item", "cannot", "w")}, "crit": bool(c.get("crit")), "because": because,
                         "blocking": blocking, "partial": share > 0})
    pct = int(100 * got / tot + 0.5) if tot else 0  # Math.round, as the reference
    return {"pct": int(pct), "gaps": gaps, "crit": sum(1 for g in gaps if g["crit"] and not g["partial"])}


def critical(g: dict[str, Any]) -> bool:
    return bool(g.get("crit")) and not g.get("partial")


def sorted_gaps(comp: dict[str, Any]) -> list[dict[str, Any]]:
    """Critical first (red), then the important ones (grey), each group by weight."""
    return sorted(comp["gaps"], key=lambda g: (0 if critical(g) else 1, -g["w"]))


def _key(g: dict[str, Any]) -> str:
    return g["item"] + ("~" if g.get("partial") else "")


def delta(prev: dict[str, Any] | None, comp: dict[str, Any]) -> dict[str, Any]:
    """Against the previous run: "20% → 35% (+15)", the critical count before and after, and what is now covered
    (a gap of the last run that is gone, or now only in part)."""
    if not prev:
        return {"prev_pct": None, "delta_pts": None, "prev_crit": None, "now_covered": []}
    now = {_key(g) for g in comp["gaps"]}
    covered = []
    for g in prev.get("gaps") or []:
        if _key(g) in now:
            continue
        still = next((x for x in comp["gaps"] if x["item"] == g["item"]), None)
        covered.append({"item": g["item"], "cannot": g["cannot"], "in_part": still is not None,
                        "text": f"{g['cannot']} (now in part)" if still is not None else g["cannot"]})
    return {"prev_pct": prev.get("pct"), "delta_pts": comp["pct"] - int(prev.get("pct") or 0), "prev_crit": prev.get("crit"), "now_covered": covered}


def meter_text(check: dict[str, Any]) -> str:
    """'Completeness 20% → 35% (+15)' or 'Completeness 35%'."""
    c = check["comp"]
    d = check.get("delta_pts")
    if check.get("prev_pct") is not None and d:
        return f"Completeness {check['prev_pct']}% → {c['pct']}% ({'+' if d > 0 else ''}{d})"
    return f"Completeness {c['pct']}%"


def gaps_md(check: dict[str, Any]) -> str:
    c = check["comp"]
    md = (f"**Completeness: {c['pct']}%** of the evidence a full request rests on"
          + (f"; {c['crit']} critical gap{'' if c['crit'] == 1 else 's'}." if c["gaps"] else ". All items supported.") + "\n\n")
    if not c["gaps"]:
        return md
    md += ("## What this request could not assess\nThe documents on file did not allow me to do the following. "
           "Items marked Critical are ones Credit would normally return the request for.\n\n")
    for g in sorted_gaps(c):
        md += (f"- {'**Critical:** ' if critical(g) else ''}{g['cannot']}{' (only in part)' if g['partial'] else ''} — {g['because']}. "
               f"[Section {g['sec']}]\n")
    return md


GAP_HEAD = re.compile(r"^##\s*1[.)\s]", re.M)


def with_gaps(md: str, check: dict[str, Any]) -> str:
    """The completeness line and the could-not-assess block, under the header (before section 1)."""
    block = gaps_md(check) + "\n"
    m = GAP_HEAD.search(md)
    return md[:m.start()] + block + md[m.start():] if m else block + md


def strip_gaps(md: str) -> str:
    """The draft without the system's block (the model revises the rest; the block is put back as it was)."""
    a = md.find("**Completeness:")
    if a < 0:
        return md
    m = GAP_HEAD.search(md, a)
    return md[:a] + (md[m.start():] if m else "")
