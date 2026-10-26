"""The signals of the financial-quality detector (PLAN_R13 §Q). Each signal is one number read against one threshold:

    {code, family, label, value, display, unit, threshold, op, threshold_display, flag, severity, period, source, sources,
     text, basis, note, inputs}

  flag      True (breaches the threshold), False (inside it) or None (not assessable: the inputs are not in Data Domains)
  severity  critical | high | medium | low | info (only meaningful when flag is True; "none" otherwise)
  text      one sentence in the credit voice: the figure, the period, the threshold and, where there is one, the prior year
  source    the Data Domains row it was computed from {relation, key, period}; `sources` lists every row used

Families, in the order the panel and the papers show them: related_party, receivables, earnings, balance_sheet, audit,
statistical, conduct.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from backend.dealdesk.fin_quality import inputs as I
from backend.dealdesk.fin_quality import stats

FAMILIES = {"related_party": "Related-party balances", "receivables": "Receivables quality", "earnings": "Earnings quality",
            "balance_sheet": "Balance-sheet signals", "audit": "Audit signals", "statistical": "Statistical screens",
            "conduct": "Revenue and debt against conduct and bureau"}

#: thresholds, each with the clause that sets it (bank configuration; Credit Policy numbering as in review2.analytics)
TH = {
    "rp_ca": (0.20, "Credit Policy 5.4.4 Related-party balances above 20% of current assets"),
    "rp_nw": (0.20, "Credit Policy 5.4.4 Related-party balances above 20% of net worth"),
    "adj_lev": (3.0, "Credit Policy 5.3.2 Adjusted leverage (total liabilities / adjusted net worth) above 3.0x"),
    "dso_rise": (15, "Credit Policy 5.4.1 Days sales outstanding up more than 15 days on the prior year"),
    "over180": (0.25, "Credit Policy 5.4.2 Receivables over 180 days above 25% of receivables"),
    "not_due_completed": (0.0, "Credit Policy 8.1.5 Retention and receivables on completed projects past the defects-liability period"),
    "top5": (0.60, "Credit Policy 5.4.3 Concentration: top 5 debtors above 60% of receivables"),
    "retention_build": (0.0, "Credit Policy 8.1.5 Retention receivables growing faster than revenue"),
    "accruals": (0.05, "Sloan (1996) accruals screen: (net income - operating cash flow) / average total assets above 5%"),
    "cash_conv": (0.50, "Credit Policy 5.5.1 Operating cash flow below 50% of EBITDA"),
    "margin_jump": (0.03, "Credit Policy 5.5.2 Margin change more than 3 points away from the sector median"),
    "other_income": (0.25, "Credit Policy 5.5.3 Non-operating income above 25% of net profit"),
    "intangibles": (0.20, "Credit Policy 5.3.4 Intangibles growing more than 20% a year without an acquisition"),
    "equity_bridge": (0.05, "Credit Policy 5.3.5 Net worth movement not explained by profit above 5% of opening net worth"),
    "shareholder": (0.10, "Credit Policy 5.3.6 Shareholder current accounts above 10% of net worth"),
    "wc_gap": (0.0, "Credit Policy 5.3.7 Long-dated assets funded by short-term debt (working-capital mismatch)"),
    "noncore": (0.25, "Credit Policy 5.3.8 Non-core investments above 25% of net worth"),
    "auditor_panel": ("listed", "Credit Policy 5.2.5 Approved auditors"),
    "opinion": ("clean", "Credit Policy 5.2.4 Qualified opinions and their basis"),
    "auditor_change": ("same", "Credit Policy 5.2.6 Change of auditor"),
    "audit_late": (120, "Credit Policy 5.2.3 Audited statements within 120 days of year end"),
    "beneish": (stats.M_THRESHOLD, "Beneish (1999) M-score cut-off -1.78"),
    "benford": (stats.MAD_THRESHOLD, "Nigrini (2012) first-digit MAD above 0.015 (nonconformity)"),
    "turnover_low": (0.80, "Credit Policy 6.3.2 Account turnover (all banks) below 80% of reported revenue"),
    "turnover_own": (0.50, "Credit Policy 6.3.2 Turnover through the bank below 50% of reported revenue"),
    "bureau_debt": (0.20, "Credit Policy 6.2.3 Funded debt in the CBRBR more than 20% above the bank debt in the latest statements"),
    "bureau_contingent": (0.20, "Credit Policy 6.2.3 Non-funded exposure in the CBRBR more than 20% above the contingent liabilities reported"),
}


# ------------------------------------------------------------------------------------------------ formatting

def _n(x: Any) -> float | None:
    return I._n(x)  # noqa: SLF001


def m(x: float | None, ccy: str) -> str:
    return "not provided" if x is None else f"{ccy} {x:,.1f}m"


def pc(x: float | None, dp: int = 1) -> str:
    return "not provided" if x is None else f"{x * 100:,.{dp}f}%"


def xx(x: float | None) -> str:
    return "not provided" if x is None else f"{x:,.2f}x"


def _disp(v: Any, unit: str) -> str:
    if v is None:
        return "not assessable"
    if unit == "share":
        return pc(v)
    if unit == "x":
        return xx(v)
    if unit == "days":
        return f"{(v if abs(v) >= 0.5 else 0.0):,.0f} days"
    if unit == "pts":
        return f"{v * 100:+,.1f} pts"
    if unit == "score":
        return f"{v:,.2f}"
    if unit == "mad":
        return f"{v:.4f}"
    if unit == "mn":
        return f"{v:,.1f}m"
    return str(v)


def sig(code: str, family: str, label: str, value: Any, unit: str, threshold: Any, op: str, flag: bool | None, severity: str, period: str | None,
        source: dict[str, Any] | None, text: str, basis: str, policy: str, note: str = "", sources: list[dict[str, Any]] | None = None,
        inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    tdisp = {"share": pc(threshold, 0) if isinstance(threshold, float) else str(threshold), "x": xx(threshold) if isinstance(threshold, float) else str(threshold),
             "days": f"{threshold} days" if threshold is not None else "", "pts": f"{threshold * 100:.0f} pts" if isinstance(threshold, float) else str(threshold),
             "score": f"{threshold:.2f}" if isinstance(threshold, float) else str(threshold), "mad": f"{threshold:.3f}" if isinstance(threshold, float) else str(threshold),
             "mn": (f"{threshold:,.1f}m" if isinstance(threshold, float) else str(threshold))}.get(unit, str(threshold))
    return {"code": code, "family": family, "family_label": FAMILIES[family], "label": label,
            "value": None if value is None else (round(value, 6) if isinstance(value, float) else value), "display": _disp(value, unit), "unit": unit,
            "threshold": threshold, "op": op, "threshold_display": f"{op} {tdisp}".strip(), "flag": flag,
            "severity": severity if flag else ("none" if flag is False else "not_assessable"), "period": period, "source": source,
            "sources": sources or ([source] if source else []), "text": text, "basis": basis, "policy_ref": policy, "note": note,
            "inputs": inputs or {}}


def na(code: str, family: str, label: str, unit: str, threshold: Any, op: str, why: str, basis: str, policy: str, x: dict[str, Any],
       source: dict[str, Any] | None = None) -> dict[str, Any]:
    return sig(code, family, label, None, unit, threshold, op, None, "info", None, source or x.get("deal_src"),
               f"{label}: not assessable as at {_asof(x)}; {why}.", basis, policy)


def _asof(x: dict[str, Any]) -> str:
    s = str(x.get("as_of_date") or "")
    try:
        d = dt.date.fromisoformat(s[:10])
        return f"{d.day} {d.strftime('%b')} {d.year}"
    except ValueError:
        return s


def _last(x: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ys = x.get("years") or []
    return (ys[-1] if ys else None), (ys[-2] if len(ys) > 1 else None)


def _need(y: dict[str, Any] | None, *keys: str) -> list[str]:
    if y is None:
        return list(keys)
    return [k for k in keys if _n(y.get(k)) is None]


def _missing(keys: list[str]) -> str:
    return ", ".join(k.replace("_", " ") for k in keys) + " not provided in the statements on file"


# ------------------------------------------------------------------------------------------------ related parties

def related_party(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    ccy, out = x["currency"], []
    lab1, lab2, lab3 = "Related-party balances / current assets", "Related-party balances / net worth", "Net worth and leverage after netting related parties"
    miss = _need(y, "due_from_related", "current_assets")
    if miss:
        out.append(na("RP-01", "related_party", lab1, "share", TH["rp_ca"][0], ">", _missing(miss), "due from related parties / current assets", TH["rp_ca"][1], x))
    else:
        rp, ca = y["due_from_related"], y["current_assets"]
        v = rp / ca if ca else None
        pv = (p["due_from_related"] / p["current_assets"]) if p and _n(p.get("due_from_related")) is not None and p.get("current_assets") else None
        flag = v is not None and v > TH["rp_ca"][0]
        out.append(sig("RP-01", "related_party", lab1, v, "share", TH["rp_ca"][0], ">", flag, "high" if (v or 0) > 0.40 else "medium", y["label"], y["src"],
                       f"Due from related parties of {m(rp, ccy)} is {pc(v)} of current assets of {m(ca, ccy)} at {y['label']}"
                       + (f" (PY {pc(pv)})" if pv is not None else "") + f", against a threshold of {pc(TH['rp_ca'][0], 0)}.",
                       "due from related parties / current assets", TH["rp_ca"][1], sources=[y["src"]] + ([p["src"]] if p else []),
                       inputs={"due_from_related": rp, "current_assets": ca, "prior_share": pv}))
    miss = _need(y, "due_from_related", "net_worth")
    if miss:
        out.append(na("RP-02", "related_party", lab2, "share", TH["rp_nw"][0], ">", _missing(miss), "due from related parties / reported net worth", TH["rp_nw"][1], x))
        out.append(na("RP-03", "related_party", lab3, "x", TH["adj_lev"][0], ">", _missing(miss), "total liabilities / (net worth - due from related parties)", TH["adj_lev"][1], x))
        return out
    rp, nw = y["due_from_related"], y["net_worth"]
    v = rp / nw if nw else None
    pv = (p["due_from_related"] / p["net_worth"]) if p and _n(p.get("due_from_related")) is not None and p.get("net_worth") else None
    trend = [f"{q['label']} {m(q['due_from_related'], ccy)}" for q in x["years"] if _n(q.get("due_from_related")) is not None]
    sev = "critical" if (v or 0) > 1.0 else "high"
    out.append(sig("RP-02", "related_party", lab2, v, "share", TH["rp_nw"][0], ">", v is not None and v > TH["rp_nw"][0], sev, y["label"], y["src"],
                   f"Due from related parties of {m(rp, ccy)} is {pc(v)} of reported net worth of {m(nw, ccy)} at {y['label']}"
                   + (f" (PY {pc(pv)})" if pv is not None else "") + f", against a threshold of {pc(TH['rp_nw'][0], 0)}"
                   + (f"; the balance moved {', '.join(trend)}" if len(trend) > 1 else "") + ".",
                   "due from related parties / reported net worth", TH["rp_nw"][1], sources=[q["src"] for q in x["years"]],
                   inputs={"due_from_related": rp, "net_worth": nw, "prior_share": pv, "trend": trend}))
    tl = _n(y.get("total_liabilities"))
    if tl is None and _n(y.get("total_assets")) is not None:
        tl = y["total_assets"] - nw
    adj = nw - rp
    lev, adj_lev = (tl / nw if tl is not None and nw else None), (tl / adj if tl is not None and adj > 0 else None)
    if adj <= 0:
        out.append(sig("RP-03", "related_party", lab3, adj, "mn", 0.0, "<=", True, "critical", y["label"], y["src"],
                       f"After netting due from related parties of {m(rp, ccy)}, adjusted net worth is {m(adj, ccy)} at {y['label']} (reported {m(nw, ccy)}); "
                       f"leverage is not meaningful on a negative adjusted net worth (reported {xx(lev)}).",
                       "net worth - due from related parties; total liabilities / adjusted net worth", TH["adj_lev"][1],
                       inputs={"net_worth": nw, "adjusted_net_worth": adj, "total_liabilities": tl, "leverage": lev, "adjusted_leverage": None}))
    elif adj_lev is None:
        out.append(na("RP-03", "related_party", lab3, "x", TH["adj_lev"][0], ">", "total liabilities not provided", "total liabilities / adjusted net worth", TH["adj_lev"][1], x))
    else:
        out.append(sig("RP-03", "related_party", lab3, adj_lev, "x", TH["adj_lev"][0], ">", adj_lev > TH["adj_lev"][0], "high", y["label"], y["src"],
                       f"After netting due from related parties of {m(rp, ccy)}, adjusted net worth is {m(adj, ccy)} and leverage (total liabilities / net worth) "
                       f"{xx(adj_lev)} at {y['label']} (reported {m(nw, ccy)} and {xx(lev)}), against {xx(TH['adj_lev'][0])}.",
                       "total liabilities / (net worth - due from related parties)", TH["adj_lev"][1],
                       inputs={"net_worth": nw, "adjusted_net_worth": adj, "total_liabilities": tl, "leverage": lev, "adjusted_leverage": adj_lev}))
    return out


# ------------------------------------------------------------------------------------------------ receivables

def _dso(y: dict[str, Any]) -> float | None:
    r, rev = _n(y.get("receivables")), _n(y.get("revenue"))
    return r / (rev * 12.0 / (y.get("months") or 12)) * 365 if r is not None and rev else None


def _completed_not_due(x: dict[str, Any]) -> list[dict[str, Any]]:
    """Completed projects past their defects-liability period that still carry retention or certified amounts as not due."""
    out = []
    asof = dt.date.fromisoformat(str(x["as_of_date"])[:10])
    for r in x.get("projects") or []:
        if str(r.get("status")) != "completed":
            continue
        end = str(r.get("completion_revised") or r.get("completion_original") or "")[:10]
        try:
            dlp_end = dt.date.fromisoformat(end).replace(year=dt.date.fromisoformat(end).year + 1)
        except ValueError:
            continue
        amt = (_n(r.get("retention_mn")) or 0.0) + (_n(r.get("due_mn")) or 0.0)
        if dlp_end < asof and amt > 0:
            out.append({"project_id": r.get("project_id"), "project": r.get("project_name"), "completed": end, "dlp_end": dlp_end.isoformat(),
                        "retention": _n(r.get("retention_mn")) or 0.0, "due": _n(r.get("due_mn")) or 0.0, "amount": round(amt, 3),
                        "months_past": (asof.year - dlp_end.year) * 12 + asof.month - dlp_end.month,
                        "src": I.src("dd_project", {"project_id": r.get("project_id")}, r.get("reporting_quarter"))})
    return out


def receivables(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    ccy, out = x["currency"], []
    # RC-01 days sales outstanding trend
    pts = [(q["label"], _dso(q)) for q in x["years"] if _dso(q) is not None]
    lab = "Days sales outstanding trend"
    if len(pts) < 2:
        out.append(na("RC-01", "receivables", lab, "days", TH["dso_rise"][0], "rise >", "receivables and revenue for two audited years not provided",
                      "receivables / revenue x 365, year on year", TH["dso_rise"][1], x))
    else:
        rise = pts[-1][1] - pts[-2][1]
        out.append(sig("RC-01", "receivables", lab, rise, "days", TH["dso_rise"][0], "rise >", rise > TH["dso_rise"][0], "medium", y["label"], y["src"],
                       f"Days sales outstanding {', '.join(f'{lb} {v:,.0f}' for lb, v in pts)} days; {pts[-1][0]} {pts[-1][1]:,.0f} days (PY {pts[-2][1]:,.0f}), "
                       f"a change of {(rise if abs(rise) >= 0.5 else 0.0):+,.0f} days against a threshold of +{TH['dso_rise'][0]} days.",
                       "receivables / revenue x 365 (interim annualised), year on year", TH["dso_rise"][1], sources=[q["src"] for q in x["years"]],
                       inputs={"dso": dict(pts)}))
    # RC-02 ageing
    lab = "Receivables over 180 days"
    miss = _need(y, "receivables", "ageing_181_365", "ageing_over_365")
    if miss:
        out.append(na("RC-02", "receivables", lab, "share", TH["over180"][0], ">", _missing(miss), "(181-365 + over 365 days) / receivables", TH["over180"][1], x))
    else:
        rec = y["receivables"]
        old = y["ageing_181_365"] + y["ageing_over_365"]
        v = old / rec if rec else None
        pv = ((p["ageing_181_365"] + p["ageing_over_365"]) / p["receivables"]) if p and not _need(p, "receivables", "ageing_181_365", "ageing_over_365") and p["receivables"] else None
        out.append(sig("RC-02", "receivables", lab, v, "share", TH["over180"][0], ">", v is not None and v > TH["over180"][0], "high" if (v or 0) > 0.40 else "medium",
                       y["label"], y["src"],
                       f"Receivables over 180 days of {m(old, ccy)} are {pc(v)} of receivables of {m(rec, ccy)} at {y['label']}"
                       + (f" (PY {pc(pv)})" if pv is not None else "") + f"; over 365 days {m(y['ageing_over_365'], ccy)} ({pc(y['ageing_over_365'] / rec if rec else None)}).",
                       "(181-365 + over 365 days) / receivables", TH["over180"][1], inputs={"over_180": old, "receivables": rec}))
    # RC-03 balances "not due" on completed projects
    lab = "Balances not due on completed projects"
    if not x.get("projects"):
        out.append(na("RC-03", "receivables", lab, "mn", TH["not_due_completed"][0], ">", "no project schedule in dd_project (not a contractor, or not provided)",
                      "retention and certified amounts of completed projects past the defects-liability period", TH["not_due_completed"][1], x))
    else:
        nd = _completed_not_due(x)
        tot = round(sum(r["amount"] for r in nd), 3)
        ret = _n((y or {}).get("retention_receivables"))
        if nd:
            text = (f"{len(nd)} completed project(s) past the 12-month defects-liability period carry {m(tot, ccy)} reported as not due at {_asof(x)}: "
                    + "; ".join(f"{r['project']} (completed {r['completed']}, defects period ended {r['dlp_end']}, retention {m(r['retention'], ccy)}"
                                + (f", certified {m(r['due'], ccy)}" if r["due"] else "") + ")" for r in nd)
                    + (f"; {pc(tot / ret)} of retention receivables of {m(ret, ccy)} at {y['label']}" if ret and y else "") + ".")
        else:
            n_c = sum(1 for r in x["projects"] if str(r.get("status")) == "completed")
            text = (f"{n_c} completed project(s) in the schedule as at {_asof(x)}; none carries retention or certified amounts past its defects-liability period "
                    f"(0 of {len(x['projects'])} projects).")
        out.append(sig("RC-03", "receivables", lab, tot, "mn", TH["not_due_completed"][0], ">", tot > 0, "high", _asof(x),
                       nd[0]["src"] if nd else I.src("dd_project", {"proposal_id": x["proposal_id"]}), text,
                       "retention + certified amounts of completed projects whose completion + 12 months is before the as-of date", TH["not_due_completed"][1],
                       sources=[r["src"] for r in nd] + ([y["src"]] if y else []), inputs={"projects": nd, "retention_receivables": ret}))
    # RC-04 concentration
    lab = "Top-5 debtor concentration"
    if y is None or y.get("top5_receivable") is None:
        out.append(na("RC-04", "receivables", lab, "share", TH["top5"][0], ">", "debtor concentration not provided", "top 5 debtors / receivables", TH["top5"][1], x))
    else:
        v, pv = y["top5_receivable"], (p or {}).get("top5_receivable")
        out.append(sig("RC-04", "receivables", lab, v, "share", TH["top5"][0], ">", v > TH["top5"][0], "medium", y["label"], y["src"],
                       f"The top 5 debtors account for {pc(v)} of receivables at {y['label']}" + (f" (PY {pc(pv)})" if pv is not None else "")
                       + (f", the top 2 for {pc(y.get('top2_receivable'))}" if y.get("top2_receivable") is not None else "") + f", against {pc(TH['top5'][0], 0)}.",
                       "top 5 debtors / receivables", TH["top5"][1], inputs={"top5": v, "top2": y.get("top2_receivable"), "prior_top5": pv}))
    # RC-05 retention build-up
    lab = "Retention build-up against revenue"
    rs = [q for q in x["years"] if _n(q.get("retention_receivables")) and _n(q.get("revenue"))]
    if len(rs) < 3:
        why = "fewer than three audited years with retention receivables" if any(_n(q.get("retention_receivables")) for q in x["years"]) else "no retention receivables reported"
        out.append(na("RC-05", "receivables", lab, "pts", TH["retention_build"][0], ">", why, "retention growth - revenue growth, last two years", TH["retention_build"][1], x))
    else:
        gaps = []
        for a, b in zip(rs[-3:-1], rs[-2:], strict=True):
            gaps.append((b["label"], b["retention_receivables"] / a["retention_receivables"] - 1, b["revenue"] / a["revenue"] - 1))
        worst = min(g[1] - g[2] for g in gaps)
        flag = all(g[1] - g[2] > TH["retention_build"][0] for g in gaps)
        out.append(sig("RC-05", "receivables", lab, worst, "pts", TH["retention_build"][0], ">", flag, "medium", rs[-1]["label"], rs[-1]["src"],
                       "Retention receivables " + "; ".join(f"grew {pc(g[1])} in {g[0]} against revenue growth of {pc(g[2])}" for g in gaps)
                       + f"; retentions {m(rs[-1]['retention_receivables'], ccy)} at {rs[-1]['label']} (PY {m(rs[-2]['retention_receivables'], ccy)}), "
                         f"{pc(rs[-1]['retention_receivables'] / rs[-1]['revenue'])} of revenue.",
                       "retention growth minus revenue growth in each of the last two years (flag when both are positive)", TH["retention_build"][1],
                       sources=[q["src"] for q in rs[-3:]], inputs={"growth": [{"period": g[0], "retention": g[1], "revenue": g[2]} for g in gaps]}))
    return out


# ------------------------------------------------------------------------------------------------ earnings

def earnings(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    ccy, out = x["currency"], []
    book = x["kind"] == "book"
    # EQ-01 accruals
    lab = "Accruals ratio"
    ni_key = "operating_profit" if book else "net_profit"
    miss = _need(y, ni_key, "operating_cash_flow", "total_assets")
    if miss:
        out.append(na("EQ-01", "earnings", lab, "share", TH["accruals"][0], ">", _missing(miss), "(net income - operating cash flow) / average total assets", TH["accruals"][1], x))
    else:
        ta = (y["total_assets"] + p["total_assets"]) / 2 if p and _n(p.get("total_assets")) else y["total_assets"]
        v = (y[ni_key] - y["operating_cash_flow"]) / ta if ta else None
        pv = None
        if p and not _need(p, ni_key, "operating_cash_flow", "total_assets"):
            pv = (p[ni_key] - p["operating_cash_flow"]) / p["total_assets"]
        out.append(sig("EQ-01", "earnings", lab, v, "share", TH["accruals"][0], ">", v is not None and v > TH["accruals"][0],
                       "high" if (v or 0) > 0.10 else "medium", y["label"], y["src"],
                       f"{'Operating profit' if book else 'Net profit'} of {m(y[ni_key], ccy)} against operating cash flow of {m(y['operating_cash_flow'], ccy)} in {y['label']} "
                       f"gives an accruals ratio of {pc(v)} of average total assets of {m(ta, ccy)}" + (f" (PY {pc(pv)})" if pv is not None else "")
                       + f", against {pc(TH['accruals'][0], 0)}.",
                       "(net income - operating cash flow) / average total assets" + (" (book: operating profit; total assets derived from return on assets)" if book else ""),
                       TH["accruals"][1], sources=[y["src"]] + ([p["src"]] if p else []), inputs={"income": y[ni_key], "ocf": y["operating_cash_flow"], "avg_assets": ta}))
    # EQ-02 cash conversion
    lab = "Cash conversion (operating cash flow / EBITDA)"
    miss = _need(y, "operating_cash_flow", "ebitda")
    if miss:
        out.append(na("EQ-02", "earnings", lab, "share", TH["cash_conv"][0], "<", _missing(miss), "operating cash flow / EBITDA", TH["cash_conv"][1], x))
    else:
        conv = [(q["label"], q["operating_cash_flow"] / q["ebitda"]) for q in x["years"] if not _need(q, "operating_cash_flow", "ebitda") and q["ebitda"]]
        v = conv[-1][1] if conv else None
        neg = sum(1 for q in x["years"] if (_n(q.get("operating_cash_flow")) or 0) < 0)
        out.append(sig("EQ-02", "earnings", lab, v, "share", TH["cash_conv"][0], "<", v is not None and v < TH["cash_conv"][0],
                       "high" if y["operating_cash_flow"] < 0 else "medium", y["label"], y["src"],
                       f"Operating cash flow of {m(y['operating_cash_flow'], ccy)} against EBITDA of {m(y['ebitda'], ccy)} in {y['label']}: cash conversion {pc(v)}"
                       + (f" (PY {pc(conv[-2][1])})" if len(conv) > 1 else "") + f", against {pc(TH['cash_conv'][0], 0)}"
                       + (f"; operating cash flow negative in {neg} of {len(x['years'])} audited years" if neg else "") + ".",
                       "operating cash flow / EBITDA", TH["cash_conv"][1], sources=[q["src"] for q in x["years"]], inputs={"by_year": dict(conv)}))
    # EQ-03 margin jump against sector peers
    lab = "Margin change against sector peers"
    def margin(q: dict[str, Any]) -> float | None:
        if q.get("ebitda_margin") is not None:
            return q["ebitda_margin"]
        e, r = _n(q.get("ebitda")), _n(q.get("revenue"))
        return e / r if e is not None and r else None
    if not (y and p and margin(y) is not None and margin(p) is not None):
        out.append(na("EQ-03", "earnings", lab, "pts", TH["margin_jump"][0], "|gap| >", "EBITDA margin for two audited years not provided",
                      "EBITDA margin change - sector median change", TH["margin_jump"][1], x))
    else:
        peer = I.sector_margin_change(x.get("sector"), int(p["year"]), int(y["year"]))
        d = margin(y) - margin(p)
        if not peer:
            out.append(na("EQ-03", "earnings", lab, "pts", TH["margin_jump"][0], "|gap| >", f"no sector peers in the corporate book for {x.get('sector') or 'this sector'}",
                          "EBITDA margin change - sector median change", TH["margin_jump"][1], x))
        else:
            gap = d - peer["median"]
            out.append(sig("EQ-03", "earnings", lab, gap, "pts", TH["margin_jump"][0], "|gap| >", abs(gap) > TH["margin_jump"][0], "medium", y["label"], y["src"],
                           f"EBITDA margin {pc(margin(y))} in {y['label']} (PY {pc(margin(p))}), a change of {d * 100:+,.1f} points against a median of "
                           f"{peer['median'] * 100:+,.1f} points for {peer['n']} {peer['sector']} borrowers in the corporate book between {p['year']}Q4 and {y['year']}Q4.",
                           "EBITDA margin change minus the sector median change (corporate book, Q4 to Q4)", TH["margin_jump"][1], sources=[y["src"], p["src"], peer["src"]],
                           inputs={"margin": margin(y), "prior_margin": margin(p), "peer_median_change": peer["median"], "peers": peer["n"]}))
    # EQ-04 other income share
    lab = "Non-operating income / net profit"
    miss = _need(y, "net_profit", "operating_profit", "finance_cost")
    if miss:
        out.append(na("EQ-04", "earnings", lab, "share", TH["other_income"][0], ">", _missing(miss), "(net profit - (operating profit - finance cost)) / net profit", TH["other_income"][1], x))
    else:
        oi = y["net_profit"] - (y["operating_profit"] - y["finance_cost"])
        v = oi / y["net_profit"] if y["net_profit"] > 0 else None
        out.append(sig("EQ-04", "earnings", lab, v, "share", TH["other_income"][0], ">", v is not None and v > TH["other_income"][0], "medium", y["label"], y["src"],
                       f"Net profit of {m(y['net_profit'], ccy)} against operating profit after finance cost of {m(y['operating_profit'] - y['finance_cost'], ccy)} in {y['label']}: "
                       f"non-operating items of {m(oi, ccy)}" + (f" ({pc(v)} of net profit)" if v is not None else "") + f", against {pc(TH['other_income'][0], 0)}.",
                       "(net profit - (operating profit - finance cost)) / net profit; negative when zakat and tax exceed other income", TH["other_income"][1],
                       inputs={"non_operating": oi, "net_profit": y["net_profit"]}))
    return out


# ------------------------------------------------------------------------------------------------ balance sheet

def balance_sheet(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    ccy, out = x["currency"], []
    # BS-01 intangibles created internally
    lab = "Intangibles and internally created goodwill"
    if y is None or _n(y.get("intangibles")) is None or _n(y.get("net_worth")) is None:
        out.append(na("BS-01", "balance_sheet", lab, "share", TH["intangibles"][0], "growth >", "intangibles not provided", "intangibles growth year on year", TH["intangibles"][1], x))
    else:
        it, pit = y["intangibles"], _n((p or {}).get("intangibles"))
        g = (it / pit - 1) if pit else (0.0 if not it else None)
        flag = g is not None and g > TH["intangibles"][0] and it > 0
        out.append(sig("BS-01", "balance_sheet", lab, g, "share", TH["intangibles"][0], "growth >", flag if g is not None else None,
                       "medium" if it / y["net_worth"] > 0.10 else "low", y["label"], y["src"],
                       f"Intangibles and goodwill of {m(it, ccy)} at {y['label']}" + (f" (PY {m(pit, ccy)}, {pc(g)})" if g is not None else "")
                       + f", {pc(it / y['net_worth'] if y['net_worth'] else None)} of net worth"
                       + ("; no acquisition is recorded in the statements on file, so the increase is internally created." if (g or 0) > 0 else "."),
                       "intangibles growth year on year, with their share of net worth", TH["intangibles"][1], inputs={"intangibles": it, "prior": pit}))
    # BS-02 revaluations: net worth movement not explained by profit
    lab = "Net worth movement not explained by profit (revaluation or injection)"
    if not (y and p) or _need(y, "net_worth", "net_profit") or _need(p, "net_worth"):
        out.append(na("BS-02", "balance_sheet", lab, "share", TH["equity_bridge"][0], ">", "net worth and net profit for two audited years not provided",
                      "(net worth change - net profit) / opening net worth", TH["equity_bridge"][1], x))
    else:
        unexpl = (y["net_worth"] - p["net_worth"]) - y["net_profit"]
        v = unexpl / p["net_worth"] if p["net_worth"] else None
        out.append(sig("BS-02", "balance_sheet", lab, v, "share", TH["equity_bridge"][0], ">", v is not None and v > TH["equity_bridge"][0], "medium", y["label"], y["src"],
                       f"Net worth moved from {m(p['net_worth'], ccy)} to {m(y['net_worth'], ccy)} in {y['label']} against net profit of {m(y['net_profit'], ccy)}: "
                       f"{m(unexpl, ccy)} not explained by profit ({pc(v)} of opening net worth; negative means distributions), against {pc(TH['equity_bridge'][0], 0)}.",
                       "(net worth change - net profit) / opening net worth; a positive gap points to a revaluation or a capital injection", TH["equity_bridge"][1],
                       sources=[y["src"], p["src"]], inputs={"unexplained": unexpl}))
    # BS-03 shareholder current accounts
    lab = "Shareholder current accounts / net worth"
    if y is None or _n(y.get("shareholder_accounts")) is None or not _n(y.get("net_worth")):
        out.append(na("BS-03", "balance_sheet", lab, "share", TH["shareholder"][0], ">", "shareholder current accounts not provided", "shareholder accounts / net worth", TH["shareholder"][1], x))
    else:
        v = y["shareholder_accounts"] / y["net_worth"]
        out.append(sig("BS-03", "balance_sheet", lab, v, "share", TH["shareholder"][0], ">", v > TH["shareholder"][0], "medium", y["label"], y["src"],
                       f"Shareholder current accounts of {m(y['shareholder_accounts'], ccy)} are {pc(v)} of net worth of {m(y['net_worth'], ccy)} at {y['label']}, "
                       f"against {pc(TH['shareholder'][0], 0)}; not available to creditors unless subordinated.",
                       "shareholder current accounts / net worth", TH["shareholder"][1], inputs={"shareholder_accounts": y["shareholder_accounts"]}))
    # BS-04 working-capital mismatch: long-dated assets funded short term
    lab = "Working-capital mismatch (long-dated assets on short-term funding)"
    miss = _need(y, "current_assets", "current_liabilities", "total_assets", "net_worth")
    if miss:
        out.append(na("BS-04", "balance_sheet", lab, "mn", TH["wc_gap"][0], ">", _missing(miss),
                      "slow current assets - (net worth + non-current liabilities - non-current assets)", TH["wc_gap"][1], x))
    else:
        tl = _n(y.get("total_liabilities")) if _n(y.get("total_liabilities")) is not None else y["total_assets"] - y["net_worth"]
        ncl, nca = tl - y["current_liabilities"], y["total_assets"] - y["current_assets"]
        nltf = y["net_worth"] + ncl - nca
        parts = [("due from related parties", _n(y.get("due_from_related")) or 0.0), ("receivables over 365 days", _n(y.get("ageing_over_365")) or 0.0),
                 ("retention receivables", _n(y.get("retention_receivables")) or 0.0)]
        slow = sum(v for _, v in parts)
        gap = slow - nltf
        st = _n(y.get("bank_debt_st"))
        out.append(sig("BS-04", "balance_sheet", lab, gap, "mn", TH["wc_gap"][0], ">", gap > TH["wc_gap"][0], "high", y["label"], y["src"],
                       f"Long-dated current assets of {m(slow, ccy)} ({pc(slow / y['current_assets'] if y['current_assets'] else None)} of current assets) at {y['label']} ("
                       + ", ".join(f"{lb} {m(v, ccy)}" for lb, v in parts if v)
                       + f") against net long-term funds of {m(nltf, ccy)} (net worth {m(y['net_worth'], ccy)} plus non-current liabilities {m(ncl, ccy)} "
                         f"less non-current assets {m(nca, ccy)}, of which non-core investments {m(_n(y.get('noncore_investments')) or 0.0, ccy)}): "
                       + (f"a gap of {m(gap, ccy)} funded short term" + (f", {pc(gap / st)} of short-term bank debt of {m(st, ccy)}" if st else "") if gap > 0
                          else f"covered with {m(-gap, ccy)} to spare") + ".",
                       "(due from related parties + receivables over 365 days + retentions) - (net worth + non-current liabilities - non-current assets)",
                       TH["wc_gap"][1], inputs={"slow_assets": slow, "net_long_term_funds": nltf, "short_term_bank_debt": st}))
    # BS-05 non-core investments
    lab = "Non-core investments / net worth"
    if y is None or _n(y.get("noncore_investments")) is None or not _n(y.get("net_worth")):
        out.append(na("BS-05", "balance_sheet", lab, "share", TH["noncore"][0], ">", "non-core investments not provided", "non-core investments / net worth", TH["noncore"][1], x))
    else:
        v = y["noncore_investments"] / y["net_worth"]
        out.append(sig("BS-05", "balance_sheet", lab, v, "share", TH["noncore"][0], ">", v > TH["noncore"][0], "medium", y["label"], y["src"],
                       f"Non-core investments of {m(y['noncore_investments'], ccy)} are {pc(v)} of net worth of {m(y['net_worth'], ccy)} at {y['label']}, against {pc(TH['noncore'][0], 0)}.",
                       "non-core investments (property, associates) / net worth", TH["noncore"][1], inputs={"noncore": y["noncore_investments"]}))
    return out


# ------------------------------------------------------------------------------------------------ audit

def audit(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    out = []
    no_audit = y is None or not (y.get("auditor") or y.get("opinion"))
    why = "auditor and opinion not in the record (" + ("corporate book: requested at renewal" if x["kind"] == "book" else "statements not on file") + ")"
    if no_audit:
        out.append(na("AU-01", "audit", "Auditor tier", "text", "listed", "is not", why, "auditor on the bank's approved panel", TH["auditor_panel"][1], x))
        out.append(na("AU-02", "audit", "Audit opinion", "text", "clean", "is not", why, "opinion on the latest audited statements", TH["opinion"][1], x))
    else:
        panel = str(y.get("panel") or "").lower() or None
        out.append(sig("AU-01", "audit", "Auditor tier", panel or "not provided", "text", "listed", "is not", None if panel is None else panel != "listed", "medium",
                       y["label"], y["src"],
                       f"{y['label']} statements audited by {y.get('auditor') or 'an auditor not named'}, "
                       + ({"listed": "on the bank's approved panel", "unlisted": "not on the bank's approved panel"}.get(panel or "", "panel status not provided") + "."),
                       "auditor on the bank's approved (listed) panel", TH["auditor_panel"][1], inputs={"auditor": y.get("auditor"), "panel": panel}))
        op = y.get("opinion") or "not provided"
        bad = op in ("qualified", "adverse", "disclaimer")
        out.append(sig("AU-02", "audit", "Audit opinion", op, "text", "clean", "is not", bad, "critical", y["label"], y["src"],
                       f"The {y['label']} audit opinion is {op}" + (f"; basis of qualification as per the auditor: {str(y.get('basis')).rstrip('.')}" if bad and y.get("basis") else
                                                                    "; basis not provided" if bad else "") + ".",
                       "opinion on the latest audited statements (clean / qualified / adverse / disclaimer)", TH["opinion"][1],
                       inputs={"opinion": op, "basis": y.get("basis")}))
    # AU-03 change of auditor
    lab = "Change of auditor"
    if no_audit or not p or not p.get("auditor"):
        out.append(na("AU-03", "audit", lab, "text", "same", "is not", "auditor for two audited years not provided", "auditor of the last two audited years", TH["auditor_change"][1], x))
    else:
        changed = str(p["auditor"]).strip().lower() != str(y.get("auditor") or "").strip().lower()
        worse = changed and (str(y.get("panel") or "") == "unlisted" or (y.get("opinion") in ("qualified", "adverse", "disclaimer")))
        out.append(sig("AU-03", "audit", lab, "changed" if changed else "unchanged", "text", "same", "is not", changed, "high" if worse else "medium", y["label"], y["src"],
                       (f"The auditor changed from {p['auditor']} ({p.get('panel') or 'panel not provided'}, {p.get('opinion') or 'opinion not provided'} opinion in {p['label']}) "
                        f"to {y.get('auditor')} ({y.get('panel') or 'panel not provided'}, {y.get('opinion') or 'opinion not provided'} opinion in {y['label']})"
                        + ("; the change coincides with a move off the approved panel or a qualified opinion" if worse else "") + "." if changed else
                        f"{y.get('auditor')} audited both {p['label']} and {y['label']} (no change of auditor)."),
                       "auditor of the last two audited years", TH["auditor_change"][1], sources=[p["src"], y["src"]],
                       inputs={"from": p["auditor"], "to": y.get("auditor")}))
    # AU-04 late audited statements
    lab = "Audited statements delivered late"
    cov = x.get("covenant_days") or TH["audit_late"][0]
    pol = (f"Terms and conditions: audited statements within {cov} days of year end" if x.get("covenant_days") else TH["audit_late"][1])
    if y is None or not x.get("audited_received") or not y.get("period_end"):
        out.append(na("AU-04", "audit", lab, "days", cov, ">", "date the audited statements were received not recorded in dd_document",
                      "days from year end to receipt of the audited statements", pol, x))
    else:
        days = (dt.date.fromisoformat(x["audited_received"]) - dt.date.fromisoformat(str(y["period_end"])[:10])).days
        late = days - cov
        out.append(sig("AU-04", "audit", lab, float(days), "days", cov, ">", days > cov, "high" if late > 90 else "medium", y["label"], x.get("audited_src") or y["src"],
                       f"The {y['label']} audited statements were received on {x['audited_received']}, {days} days after the year end of {str(y['period_end'])[:10]}, "
                       f"against {cov} days" + (" in the terms and conditions" if x.get("covenant_days") else " in policy") + (f" ({late} days late)." if late > 0 else "."),
                       "days from year end to receipt of the audited statements (dd_document)", pol,
                       sources=[s for s in (x.get("audited_src"), x.get("covenant_src"), y["src"]) if s], inputs={"days": days, "covenant_days": cov}))
    return out


# ------------------------------------------------------------------------------------------------ statistical screens

def statistical(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, p = _last(x)
    out = []
    lab = "Beneish M-score"
    if not (y and p) or x["kind"] == "book":
        out.append(na("ST-01", "statistical", lab, "score", stats.M_THRESHOLD, ">", "two audited years with the full statements are needed" if x["kind"] != "book" else
                      "the book record carries no balance sheet detail (receivables, current assets, gross profit)", "Beneish (1999) 8-variable M-score", TH["beneish"][1], x))
    else:
        b = stats.beneish(y, p)
        if b["score"] is None:
            out.append(na("ST-01", "statistical", lab, "score", stats.M_THRESHOLD, ">", "inputs not provided for " + ", ".join(b["missing"]),
                          "Beneish (1999) 8-variable M-score", TH["beneish"][1], x))
            out[-1]["note"] = b["note"]
        else:
            flag = b["score"] > stats.M_THRESHOLD
            c = b["components"]
            out.append(sig("ST-01", "statistical", lab, b["score"], "score", stats.M_THRESHOLD, ">", flag, "medium", y["label"], y["src"],
                           f"Beneish M-score of {b['score']:.2f} for {y['label']} on {p['label']} against a cut-off of {stats.M_THRESHOLD:.2f} "
                           f"(DSRI {c['DSRI']:.2f}, GMI {c['GMI']:.2f}, SGI {c['SGI']:.2f}, TATA {c['TATA']:.3f}, LVGI {c['LVGI']:.2f}); a screen, not evidence.",
                           "Beneish (1999) 8-variable M-score of the last audited year on the prior year", TH["beneish"][1], note=b["note"],
                           sources=[y["src"], p["src"]], inputs=b))
    lab = "Benford first-digit test"
    vals = [v for _, v in x.get("amounts") or []]
    lines = len({k.split(":", 1)[-1] for k, _ in x.get("amounts") or []})
    bf = stats.benford(vals, lines=lines)
    rel = x["years"][-1]["src"]["relation"] if x.get("years") else "dd_financials_detail"
    if bf["mad"] is None:
        s = na("ST-02", "statistical", lab, "mad", stats.MAD_THRESHOLD, ">", bf["note"].rstrip("."), "Nigrini (2012) first-digit MAD", TH["benford"][1], x)
        s["note"], s["inputs"] = bf["note"], bf
        out.append(s)
    else:
        flag = bf["mad"] > stats.MAD_THRESHOLD and bf["chi2"] > stats.CHI2_CRIT_8DF_5PCT and bf["reliable"]
        out.append(sig("ST-02", "statistical", lab, bf["mad"], "mad", stats.MAD_THRESHOLD, ">", flag, "low", _asof(x),
                       I.src(rel, {("proposal_id" if x["kind"] == "deal" else "borrower_id"): x["proposal_id"] or x["obligor_id"]}),
                       f"First digits of {bf['n']} reported amounts on file as at {_asof(x)}: MAD {bf['mad']:.4f} ({bf['band']}), chi-square {bf['chi2']:.1f} "
                       f"against {stats.CHI2_CRIT_8DF_5PCT} at 5%" + ("" if bf["reliable"] else f"; reliable only with {stats.BENFORD_RELIABLE_N}+ amounts over {stats.BENFORD_MIN_LINES}+ line items (here {bf['n']} over {lines}), so not flagged")
                       + ("; flagged only when both the MAD and the chi-square reject conformity" if bf["mad"] > stats.MAD_THRESHOLD and not flag and bf["reliable"] else "") + ".",
                       "mean absolute deviation of first-digit shares from Benford's law (flag: MAD above 0.015 and chi-square above 15.507, 100+ amounts)", TH["benford"][1], note=bf["note"], inputs=bf))
    return out


# ------------------------------------------------------------------------------------------------ revenue against conduct

def conduct(x: dict[str, Any]) -> list[dict[str, Any]]:
    y, _ = _last(x)
    ccy = x["currency"]
    c = x.get("conduct")
    lab = "Reported revenue against account turnover"
    if not c or y is None or not _n(y.get("revenue")):
        return [na("CD-01", "conduct", lab, "share", TH["turnover_low"][0], "<", "account conduct or reported revenue not available",
                   "credit turnover (this bank + other banks) over 12 months / reported revenue", TH["turnover_low"][1], x)]
    rev = y["revenue"]
    own = c["turnover"]
    others = x.get("other_turnover") or []
    oth = sum(o["value"] for o in others)
    share_own = own / rev
    if others:
        v = (own + oth) / rev
        flag, thr, pol = v < TH["turnover_low"][0], TH["turnover_low"][0], TH["turnover_low"][1]
        sev = "high" if v < 0.5 else "medium"
        banks = ", ".join(str(o["bank"]) + " " + m(o["value"], ccy) for o in others)
        text = (f"Credit turnover of {m(own, ccy)} through the bank over the {c['months']} months {c['first']} to {c['last']} ({pc(share_own)} of {y['label']} revenue of "
                f"{m(rev, ccy)}) and {m(oth, ccy)} through {len(others)} other bank(s) as per the statements provided by business "
                f"({banks}): {pc(v)} of reported revenue routed through banks, against {pc(thr, 0)}.")
    else:
        v = share_own
        flag, thr, pol = v < TH["turnover_own"][0], TH["turnover_own"][0], TH["turnover_own"][1]
        sev = "medium"
        text = (f"Credit turnover of {m(own, ccy)} through the bank over the {c['months']} months {c['first']} to {c['last']} is {pc(v)} of {y['label']} reported revenue of "
                f"{m(rev, ccy)}, against {pc(thr, 0)}; turnover at other banks not provided.")
    if v > 1.5:
        flag, sev = True, "medium"
        text = text.rstrip(".") + "; turnover above 150% of revenue points to inter-account transfers or drawdowns counted as receipts."
    return [sig("CD-01", "conduct", lab, v, "share", thr, "<", flag, sev, y["label"], c["src"], text,
                "credit turnover over the last 12 months (this bank" + (" + other banks' statements" if others else "") + ") / last audited revenue", pol,
                sources=[c["src"], y["src"]] + [o["src"] for o in others],
                inputs={"own_turnover": own, "other_turnover": oth, "revenue": rev, "own_share": share_own, "routed_business": c.get("routed")})]


def bureau(x: dict[str, Any]) -> list[dict[str, Any]]:
    """Debt and contingent liabilities in the latest statements against the central-bank risk bureau (CBRBR)."""
    ccy, out = x["currency"], []
    cb = x.get("cbrbr")
    stmts = [q for q in (x.get("years") or []) + (x.get("interim") or []) if q.get("period_end")]
    st = max(stmts, key=lambda q: str(q["period_end"])) if stmts else None
    for code, lab, key, fields, th in (("CD-02", "Bank debt in the statements against the bureau", "funded_os", ("bank_debt_st", "bank_debt_lt"), "bureau_debt"),
                                       ("CD-03", "Contingent liabilities in the statements against the bureau", "nf_os", ("contingent_liabilities",), "bureau_contingent")):
        thr, pol = TH[th]
        basis = ("CBRBR funded outstanding / (short + long-term bank debt in the latest statements) - 1" if code == "CD-02" else
                 "CBRBR non-funded outstanding / contingent liabilities in the latest statements - 1")
        if not cb or cb.get(key) is None or st is None or all(_n(st.get(f)) is None for f in fields):
            out.append(na(code, "conduct", lab, "share", thr, ">", "the CBRBR line of the borrower or the statement figure not provided", basis, pol, x))
            continue
        rep = sum(_n(st.get(f)) or 0.0 for f in fields)
        bur = cb[key]
        v = (bur / rep - 1) if rep else None
        what = "funded outstanding" if code == "CD-02" else "non-funded outstanding"
        stated = "bank debt" if code == "CD-02" else "contingent liabilities"
        out.append(sig(code, "conduct", lab, v, "share", thr, ">", v is not None and v > thr, "high" if (v or 0) > 0.5 else "medium", st["label"], cb["src"],
                       f"The CBRBR shows {what} of {m(bur, ccy)} across {cb.get('banks') or 'n'} banks on {cb.get('date')} against {stated} of {m(rep, ccy)} "
                       f"in the {st['label']} statements" + (f": {pc(v)} more in the bureau" if v is not None and v > 0 else f": {pc(-v) if v is not None else 'not provided'} less in the bureau")
                       + f", against a tolerance of {pc(thr, 0)}.",
                       basis + "; the statements' date and the bureau date differ, hence the tolerance", pol, sources=[cb["src"], st["src"]],
                       inputs={"bureau": bur, "reported": rep, "bureau_date": cb.get("date"), "statement": st["label"]}))
    return out


ALL: list[Callable[[dict[str, Any]], list[dict[str, Any]]]] = [related_party, receivables, earnings, balance_sheet, audit, statistical, conduct, bureau]


def run(x: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in ALL:
        try:
            out += f(x)
        except Exception as e:  # noqa: BLE001 - one family's data problem never takes the detector down
            out.append(na(f"{f.__name__[:2].upper()}-ERR", f.__name__ if f.__name__ in FAMILIES else "statistical", FAMILIES.get(f.__name__, f.__name__),
                          "text", None, "", f"the inputs could not be read ({type(e).__name__})", "", "", x))
    return out
