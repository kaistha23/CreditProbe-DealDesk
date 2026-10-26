"""The inputs of the financial-quality detector, read from Data Domains through the shared readers (PLAN_R13 N5).

    load(pid)          a deal: dd_financials_detail (or dd_obligor_financials), dd_project, dd_account_conduct (or dep_month),
                       dd_tnc (audit covenant), dd_document (audited statements received), dd_business_profile (turnover at
                       other banks), bureau_entity_report, dd_deal
    load_book(fid)     a back-book facility up for renewal: corp_borrower_quarter (the borrower's reported financials) and
                       dep_month (account turnover)

Every period carries its lineage {relation, key, period} so each signal names the row it was computed from.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.data import schema as S
from backend.dealdesk.review2 import publish as P

#: dd_financials_detail columns -> the detector's field names (amounts in millions of the deal currency)
DETAIL = ("revenue", "gross_profit", "operating_profit", "net_profit", "ebitda", "finance_cost", "total_assets", "current_assets", "cash",
          "receivables", "retention_receivables", "contract_assets", "inventory", "due_from_related", "current_liabilities", "due_to_related",
          "intangibles", "shareholder_accounts", "noncore_investments", "bank_debt_st", "bank_debt_lt", "total_liabilities", "net_worth",
          "contingent_liabilities", "operating_cash_flow", "ageing_0_90", "ageing_91_180", "ageing_181_365", "ageing_over_365", "backlog")
PCT = ("top1_receivable_pct", "top2_receivable_pct", "top5_receivable_pct")


def _n(x: Any) -> float | None:
    try:
        if x is None or x == "" or isinstance(x, bool):
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _one(relation: str, **f: Any) -> dict[str, Any] | None:
    rows = P.read(relation, **f)
    return rows[0] if rows else None


def src(relation: str, key: dict[str, Any], period: Any = None) -> dict[str, Any]:
    return {"relation": relation, "key": key, "period": period or S.AS_OF}


# ------------------------------------------------------------------------------------------------ deals

def _detail_years(pid: str, deal: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, float]]]:
    rows = P.read("dd_financials_detail", proposal_id=pid)
    if not rows:
        return [], [], []
    oid = (deal or {}).get("obligor_id")
    mine = [r for r in rows if oid and r.get("entity_id") == oid]
    if not mine:
        ents = P.read("b360_entity", group_id=deal["group_id"]) if deal and deal.get("group_id") else []
        subj = {e["entity_id"] for e in ents if e.get("role") == "subject"}
        mine = [r for r in rows if r.get("entity_id") in subj] or [r for r in rows if r.get("entity_scope") in ("standalone", "branch")] or rows
    years, interim = [], []
    for r in sorted(mine, key=lambda r: (str(r.get("period_end") or r.get("year")), str(r.get("period_kind")))):
        y: dict[str, Any] = {"year": r.get("year"), "label": r.get("period_label") or f"FY{r.get('year')}", "kind": r.get("period_kind") or "audited",
                             "period_end": r.get("period_end"), "months": int(_n(r.get("months")) or 12), "entity_id": r.get("entity_id"),
                             "entity_name": r.get("entity_name"), "scope": r.get("entity_scope"), "auditor": r.get("auditor") or None,
                             "panel": r.get("auditor_panel") or None, "opinion": str(r.get("opinion") or "").lower() or None,
                             "basis": r.get("qualification_basis") or None, "statement_source": r.get("source"),
                             "src": src("dd_financials_detail", {"proposal_id": pid, "entity_id": r.get("entity_id"), "period_label": r.get("period_label")},
                                        r.get("reporting_quarter"))}
        for k in DETAIL:
            y[k] = _n(r.get(f"{k}_mn"))
        y["cash_cycle_days"] = _n(r.get("cash_cycle_days"))
        for k in PCT:
            v = _n(r.get(k))
            y[k.replace("_pct", "")] = None if v is None else (v / 100.0 if abs(v) > 1.0 else v)
        (interim if y["kind"] == "interim" else years if y["kind"] == "audited" else []).append(y)
    amounts = [(f"{r.get('period_label')}:{k}", v) for r in rows for k in DETAIL if (v := _n(r.get(f"{k}_mn"))) is not None]
    return years, interim, amounts


def _summary_years(pid: str) -> tuple[list[dict[str, Any]], list[tuple[str, float]]]:
    rows = P.read("dd_obligor_financials", proposal_id=pid)
    years = []
    for r in sorted(rows, key=lambda r: int(r.get("year") or 0)):
        if str(r.get("kind") or "actual") not in ("actual", "audited"):
            continue
        years.append({"year": r.get("year"), "label": f"FY{r.get('year')}", "kind": "audited", "period_end": f"{r.get('year')}-12-31", "months": 12,
                      "entity_id": r.get("obligor_id"), "entity_name": None, "scope": "standalone", "auditor": None, "panel": None, "opinion": None,
                      "basis": None, "statement_source": r.get("source"), "revenue": _n(r.get("revenue_sar_mn")), "ebitda": _n(r.get("ebitda_sar_mn")),
                      "net_worth": _n(r.get("net_worth_sar_mn")), "total_debt": _n(r.get("total_debt_sar_mn")), "current_ratio": _n(r.get("current_ratio_x")),
                      "src": src("dd_obligor_financials", {"proposal_id": pid, "year": r.get("year")}, r.get("reporting_quarter"))})
    amounts = [(f"{r.get('year')}:{k}", v) for r in rows for k in ("revenue_sar_mn", "ebitda_sar_mn", "net_worth_sar_mn", "total_debt_sar_mn", "debt_service_sar_mn")
               if (v := _n(r.get(k))) is not None]
    return years, amounts


def _conduct(pid: str, oid: str | None) -> dict[str, Any] | None:
    rows = sorted(P.read("dd_account_conduct", proposal_id=pid), key=lambda r: str(r.get("month")))[-12:]
    if rows:
        return {"months": len(rows), "first": rows[0]["month"], "last": rows[-1]["month"],
                "turnover": round(sum(_n(r.get("credit_turnover_mn")) or 0.0 for r in rows), 3),
                "routed": round(sum(_n(r.get("routed_business_mn")) or 0.0 for r in rows), 3),
                "src": src("dd_account_conduct", {"proposal_id": pid, "month": f"{rows[0]['month']}..{rows[-1]['month']}"}, rows[-1].get("reporting_quarter"))}
    return _dep_month(oid) if oid else None


def _dep_month(oid: str) -> dict[str, Any] | None:
    try:
        rows = sorted(P.read("dep_month", obligor_id=oid), key=lambda r: str(r.get("month")))[-12:]
    except Exception:  # noqa: BLE001 - not a book obligor
        rows = []
    if not rows:
        return None
    return {"months": len(rows), "first": rows[0]["month"], "last": rows[-1]["month"],
            "turnover": round(sum(_n(r.get("credit_turnover_sar_mn")) or 0.0 for r in rows), 3), "routed": None,
            "src": src("dep_month", {"obligor_id": oid, "month": f"{rows[0]['month']}..{rows[-1]['month']}"}, rows[-1].get("as_of_date"))}


def _covenant_days(pid: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
    for rel, idk in (("dd_tnc", "tnc_id"), ("dd_condition", "condition_id")):
        for r in P.read(rel, proposal_id=pid):
            t = str(r.get("text") or "")
            m = re.search(r"audited[^.;]*?within (\d+) days", t, re.I)
            if m:
                return int(m.group(1)), src(rel, {"proposal_id": pid, idk: r.get(idk)}, r.get("reporting_quarter")), t
    return None, None, None


def _audited_received(pid: str, oid: str | None) -> tuple[str | None, dict[str, Any] | None]:
    docs = [r for r in P.read("dd_document", proposal_id=pid) if r.get("doc_type") == "audited_fs" and str(r.get("status")) == "received"]
    mine = [r for r in docs if oid and r.get("entity_id") == oid] or docs
    dated = [r for r in mine if r.get("received_date")]
    if not dated:
        return None, None
    r = max(dated, key=lambda r: str(r["received_date"]))
    return str(r["received_date"])[:10], src("dd_document", {"document_id": r.get("document_id")}, r.get("reporting_quarter"))


def _other_turnover(pid: str) -> list[dict[str, Any]]:
    out = []
    for r in P.read("dd_business_profile", proposal_id=pid):
        if str(r.get("item_kind")) == "bank_turnover" and _n(r.get("value_mn")) is not None:
            out.append({"bank": r.get("label"), "value": _n(r.get("value_mn")), "year": r.get("year"), "attribution": r.get("attribution"),
                        "src": src("dd_business_profile", {"proposal_id": pid, "item_id": r.get("item_id")}, r.get("reporting_quarter"))})
    return out


def _cbrbr(pid: str, oid: str | None) -> dict[str, Any] | None:
    """The subject's central-bank risk bureau line (funded and non-funded outstanding across banks)."""
    rows = [r for r in P.read("bureau_cbrbr", proposal_id=pid) if oid and r.get("entity_id") == oid]
    if not rows:
        return None
    r = max(rows, key=lambda r: str(r.get("report_date")))
    return {"date": r.get("report_date"), "funded_os": _n(r.get("funded_outstanding_mn")), "nf_os": _n(r.get("non_funded_outstanding_mn")),
            "banks": r.get("banks_n"), "entity": r.get("entity_name"),
            "src": src("bureau_cbrbr", {"proposal_id": pid, "entity_id": oid, "report_date": r.get("report_date")}, r.get("reporting_quarter"))}


def _sector(pid: str, deal: dict[str, Any] | None) -> str | None:
    try:
        from backend.dealdesk.data import deals
        return (deals.get(pid) or {}).get("obligor", {}).get("sector")
    except Exception:  # noqa: BLE001
        return None


def load(pid: str) -> dict[str, Any]:
    deal = _one("dd_deal", proposal_id=pid)
    oid = (deal or {}).get("obligor_id")
    years, interim, amounts = _detail_years(pid, deal)
    mode = "detail"
    if not years:
        years, amounts = _summary_years(pid)
        interim, mode = [], "summary" if years else "none"
    cov, cov_src, cov_text = _covenant_days(pid)
    rec, rec_src = _audited_received(pid, oid)
    return {"kind": "deal", "id": pid, "proposal_id": pid, "facility_id": None, "obligor_id": oid,
            "name": (deal or {}).get("obligor_name") or pid, "group": (deal or {}).get("group_name"), "sector": _sector(pid, deal),
            "currency": (deal or {}).get("currency") or "SAR", "as_of_date": S.AS_OF_DATE, "period": S.AS_OF, "mode": mode,
            "years": years, "interim": interim, "amounts": amounts, "projects": P.read("dd_project", proposal_id=pid),
            "conduct": _conduct(pid, oid), "other_turnover": _other_turnover(pid), "cbrbr": _cbrbr(pid, oid), "covenant_days": cov, "covenant_src": cov_src,
            "covenant_text": cov_text, "audited_received": rec, "audited_src": rec_src,
            "deal_src": src("dd_deal", {"proposal_id": pid}, (deal or {}).get("reporting_quarter"))}


# ------------------------------------------------------------------------------------------------ the Book (renewals)

BOOK_REL = "corp_borrower_quarter"


def _facility(fid: str) -> dict[str, Any]:
    from backend.dealdesk.book import core
    f, _ = core.frame()
    t = f[f.facility_id == fid]
    if not len(t):
        raise KeyError(fid)
    r = t.iloc[0]
    return {"borrower_id": str(r.borrower_id), "name": str(getattr(r, "borrower_name", "") or r.borrower_id),
            "sector": str(getattr(r, "sector", "") or "") or None}


def load_book(fid: str) -> dict[str, Any]:
    fac = _facility(fid)
    bid = fac["borrower_id"]
    rows = sorted(P.read(BOOK_REL, borrower_id=bid), key=lambda r: str(r.get("reporting_quarter")))
    if not rows:
        # a Book row of a Deal Desk deal (e.g. R12-TWA:L0): the deal's own statements are the better record
        pid = fid.split(":")[0] if ":" in fid else None
        deal = _one("dd_deal", proposal_id=pid) if pid else None
        deal = deal or _one("dd_deal", obligor_id=bid)
        if deal:
            x = load(deal["proposal_id"])
            x["facility_id"] = fid
            return x
    years = []
    for r in rows:
        q = str(r.get("reporting_quarter"))
        if not q.endswith("Q4"):
            continue
        roa = _n(r.get("return_on_assets_pct"))
        ebit = _n(r.get("ebit_sar_mn"))
        ta = (ebit / (roa / 100.0)) if ebit is not None and roa and roa > 0 else None
        years.append({"year": int(q[:4]), "label": f"FY{q[:4]}", "kind": "audited", "period_end": f"{q[:4]}-12-31", "months": 12, "entity_id": bid,
                      "entity_name": r.get("borrower_name"), "scope": "standalone", "auditor": None, "panel": None, "opinion": None, "basis": None,
                      "statement_source": "Corporate book (borrower reported financials)", "revenue": _n(r.get("revenue_sar_mn")),
                      "ebitda": _n(r.get("ebitda_sar_mn")), "operating_profit": ebit, "operating_cash_flow": _n(r.get("operating_cash_flow_sar_mn")),
                      "total_debt": _n(r.get("total_debt_sar_mn")), "cash": _n(r.get("cash_sar_mn")), "total_assets": ta, "total_assets_derived": ta is not None,
                      "current_ratio": _n(r.get("current_ratio_x")), "ebitda_margin": (_n(r.get("ebitda_margin_pct")) or 0) / 100.0 if r.get("ebitda_margin_pct") is not None else None,
                      "src": src(BOOK_REL, {"borrower_id": bid, "reporting_quarter": q}, q)})
    amounts = [(f"{r.get('reporting_quarter')}:{k}", v) for r in rows
               for k in ("revenue_sar_mn", "ebitda_sar_mn", "ebit_sar_mn", "operating_cash_flow_sar_mn", "total_debt_sar_mn", "cash_sar_mn")
               if (v := _n(r.get(k))) is not None]
    name = (rows[-1].get("borrower_name") if rows else None) or fac["name"]
    sector = (rows[-1].get("sector") if rows else None) or fac["sector"]
    return {"kind": "book", "id": fid, "proposal_id": None, "facility_id": fid, "obligor_id": bid, "name": name, "group": rows[-1].get("group_name") if rows else None,
            "sector": sector, "currency": "SAR", "as_of_date": S.AS_OF_DATE, "period": rows[-1].get("reporting_quarter") if rows else S.AS_OF,
            "mode": "book" if years else "none", "years": years, "interim": [], "amounts": amounts, "projects": [], "conduct": _dep_month(bid),
            "other_turnover": [], "cbrbr": None, "covenant_days": None, "covenant_src": None, "covenant_text": None, "audited_received": None, "audited_src": None,
            "deal_src": src(BOOK_REL, {"borrower_id": bid}, rows[-1].get("reporting_quarter") if rows else None)}


def sector_margin_change(sector: str | None, y0: int, y1: int) -> dict[str, Any] | None:
    """The median change in EBITDA margin (points) of the sector's book borrowers between the Q4s of two years."""
    if not sector:
        return None
    try:
        from backend.dealdesk.data import dd_frame
        f = dd_frame(BOOK_REL, columns=["borrower_id", "sector", "reporting_quarter", "ebitda_margin_pct"],
                     reporting_quarter=[f"{y0}Q4", f"{y1}Q4"], sector=sector)
    except Exception:  # noqa: BLE001
        return None
    if f.empty:
        return None
    p = f.pivot_table(index="borrower_id", columns="reporting_quarter", values="ebitda_margin_pct", aggfunc="first").dropna()
    if p.empty or f"{y0}Q4" not in p or f"{y1}Q4" not in p:
        return None
    d = (p[f"{y1}Q4"] - p[f"{y0}Q4"]) / 100.0
    return {"median": float(d.median()), "p90_abs": float(d.abs().quantile(0.9)), "n": int(len(d)), "sector": sector,
            "src": src(BOOK_REL, {"sector": sector, "reporting_quarter": f"{y0}Q4,{y1}Q4"}, f"{y1}Q4")}
