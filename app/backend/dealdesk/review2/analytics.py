"""PLAN_R12 §1.3 point 2 additions: the analyses the bank's proposals carry and R11 did not.

  adjusted_ratios      net worth, leverage, working capital and current ratio after netting related-party balances,
                       intangibles, shareholder accounts and non-core investments; every adjustment shown
  receivables          ageing, concentration (top 1 / 2 / n) and retention
  auditor              auditor quality (approved panel), opinion and the basis of qualification, entity scope
  bureau_matrix        bureau per entity and UBO, CBRBR, other banks × entity, declared against bureau
  earlier_conditions   status of the conditions of the previous approval ("routing 2x: 33% achieved")
  insider_links        staff and insider links, nominee holdings

Each returns {"rows" / tables ..., "findings": [...], "source": lineage}. A finding is
{code, point, severity, title, finding, evidence: [{source, text, ref}], value, threshold, policy_ref}.
Amounts are millions in the deal currency; shares are decimals.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

#: Review thresholds, each with the policy clause that sets it (bank configuration, PLAN §0 exception).
T = {
    "recv_over_365_share": (0.20, "Credit Policy 5.4.2 Receivables over 365 days above 20% are provided for in the adjusted view"),
    "top2_share": (0.50, "Credit Policy 5.4.3 Concentration: top 2 counterparties above 50%"),
    "rp_share_ca": (0.25, "Credit Policy 5.4.4 Related-party balances above 25% of current assets"),
    "adj_leverage": (3.0, "Credit Policy 5.3.2 Adjusted leverage (total debt / adjusted net worth) above 3.0x"),
    "adj_current_ratio": (1.0, "Credit Policy 5.3.3 Adjusted current ratio below 1.0x"),
    "reconcile_tol": (0.05, "Credit Policy 6.2.2 Declared other-bank limits reconcile with the bureau within 5%"),
    "cash_cycle_days": (180, "Credit Policy 5.4.5 Cash conversion cycle above 180 days"),
}


def _f(rule: str) -> tuple[float, str]:
    return T[rule]


def fm(x: float | None, ccy: str = "", dp: int = 1) -> str:
    if x is None:
        return "not provided"
    s = f"{abs(x):,.{dp}f}m"
    return f"{'-' if x < 0 else ''}{ccy + ' ' if ccy else ''}{s}"


def pc(x: float | None, dp: int = 0) -> str:
    return "not provided" if x is None else f"{x * 100:.{dp}f}%"


def xx(x: float | None) -> str:
    return "not provided" if x is None else f"{x:.2f}x"


def finding(code: str, point: int, severity: str, title: str, text: str, evidence: list[dict[str, Any]], value: Any = None,
            threshold: Any = None, policy_ref: str = "") -> dict[str, Any]:
    return {"code": code, "point": point, "severity": severity, "title": title, "finding": text, "evidence": evidence,
            "measured": value, "threshold": threshold, "policy_ref": policy_ref}


def _ev(source: str, text: str, ref: dict[str, Any]) -> dict[str, Any]:
    return {"source": source, "text": text, "ref": ref}


def _last_audited(fin: dict[str, Any]) -> dict[str, Any]:
    ys = [y for y in fin.get("years") or [] if str(y.get("kind")) in ("audited", "actual")]
    return ys[-1] if ys else ((fin.get("years") or [{}])[-1])


def _prior_audited(fin: dict[str, Any]) -> dict[str, Any] | None:
    ys = [y for y in fin.get("years") or [] if str(y.get("kind")) in ("audited", "actual")]
    return ys[-2] if len(ys) > 1 else None


# ------------------------------------------------------------------ adjusted ratios

ADJ_ITEMS = (
    ("intangibles", "Intangibles and internally generated goodwill", ("net_worth",)),
    ("related_party_receivable", "Due from related parties", ("net_worth", "current_assets")),
    ("shareholder_accounts", "Shareholder current accounts and withdrawals", ("net_worth", "current_assets")),
    ("noncore_investments", "Non-core investments (property and other)", ("net_worth",)),
)


def adjusted_ratios(d: dict[str, Any]) -> dict[str, Any]:
    fin, ccy, ref = d["financials"], d["subject"]["currency"], d["lineage"]["financials"]
    y = _last_audited(fin)
    py = _prior_audited(fin)
    nw, debt, ca, cl = y.get("net_worth"), y.get("total_debt"), y.get("current_assets"), y.get("current_liabilities")
    if cl is None and ca is not None and y.get("current_ratio"):
        cl = ca / y["current_ratio"]
    adjustments, total_nw, total_ca = [], 0.0, 0.0
    for key, label, applies in ADJ_ITEMS:
        amt = y.get(key)
        if amt is None or not amt:
            continue
        if key == "intangibles" and y.get("goodwill_internal") and not y.get("intangibles"):
            amt = y["goodwill_internal"]
        adjustments.append({"item": label, "field": key, "amount": round(float(amt), 3), "applies_to": list(applies),
                            "basis": "netted off as not available to creditors" if "net_worth" in applies else "",
                            "source": ref, "year": y.get("year")})
        if "net_worth" in applies:
            total_nw += float(amt)
        if "current_assets" in applies:
            total_ca += float(amt)
    wc = (ca - cl) if ca is not None and cl is not None else y.get("working_capital")
    adj_nw = (nw - total_nw) if nw is not None else None
    adj_ca = (ca - total_ca) if ca is not None else None
    adj_wc = (adj_ca - cl) if adj_ca is not None and cl is not None else ((wc - total_ca) if wc is not None else None)

    def row(name: str, reported: float | None, adjusted: float | None, unit: str, prior: float | None = None) -> dict[str, Any]:
        return {"ratio": name, "reported": None if reported is None else round(reported, 4), "adjusted": None if adjusted is None else round(adjusted, 4),
                "change": None if reported is None or adjusted is None else round(adjusted - reported, 4), "unit": unit,
                "prior": None if prior is None else round(prior, 4), "source": ref}

    lev = (debt / nw) if debt is not None and nw else None
    adj_lev = (debt / adj_nw) if debt is not None and adj_nw and adj_nw > 0 else None
    cr = (ca / cl) if ca is not None and cl else y.get("current_ratio")
    adj_cr = (adj_ca / cl) if adj_ca is not None and cl else None
    p_nw = py.get("net_worth") if py else None
    rows = [row("Net worth", nw, adj_nw, ccy, p_nw), row("Leverage (total debt / net worth)", lev, adj_lev, "x",
                                                          (py["total_debt"] / py["net_worth"]) if py and py.get("total_debt") is not None and py.get("net_worth") else None),
            row("Working capital", wc, adj_wc, ccy, y.get("working_capital_prior")), row("Current ratio", cr, adj_cr, "x"),
            row("Current assets", ca, adj_ca, ccy)]
    rows = [r for r in rows if r["reported"] is not None or r["adjusted"] is not None]
    missing = [lbl for k, lbl in (("net_worth", "net worth"), ("current_liabilities", "current liabilities"), ("total_debt", "total debt"))
               if y.get(k) is None and not (k == "current_liabilities" and cl is not None)]
    out: dict[str, Any] = {"year": y.get("year"), "rows": rows, "adjustments": adjustments, "missing": missing, "source": ref, "findings": []}
    parts = []
    if adj_nw is not None and adjustments:
        parts.append(f"if {', '.join(a['item'].lower() for a in adjustments if 'net_worth' in a['applies_to'])} "
                     f"({fm(total_nw, ccy)}) are netted off, adjusted net worth is {fm(adj_nw, ccy)} (reported {fm(nw, ccy)})")
    if adj_lev is not None and lev is not None:
        parts.append(f"leverage {xx(adj_lev)} (reported {xx(lev)})")
    if adj_ca is not None and total_ca:
        parts.append(f"adjusted current assets {fm(adj_ca, ccy)} (reported {fm(ca, ccy)})")
    if adj_cr is not None:
        parts.append(f"current ratio {xx(adj_cr)} (reported {xx(cr)})")
    if adj_wc is not None and total_ca:
        parts.append(f"working capital {fm(adj_wc, ccy)} (reported {fm(wc, ccy)})")
    if not adjustments:
        parts = []
    out["headline"] = ("FY%s: " % y.get("year") + "; ".join(parts) + ".") if parts else (
        "No adjustment items in the financials; ratios as reported." if not adjustments else
        f"Adjustment items of {fm(total_nw or total_ca, ccy)} identified; {', '.join(missing)} not provided, so adjusted ratios cannot be completed.")
    out["headline"] = out["headline"][0].upper() + out["headline"][1:]
    ev = [_ev("Audited financials", f"{a['item']}: {fm(a['amount'], ccy)} (FY{a['year']})", ref) for a in adjustments]
    thr, pol = _f("adj_leverage")
    if adj_lev is not None and adj_lev > thr:
        out["findings"].append(finding("ADJ-01", 4, "major", "Adjusted leverage above appetite",
                                       f"Adjusted leverage {xx(adj_lev)} against {thr:.1f}x after netting {fm(total_nw, ccy)} (reported {xx(lev)}).",
                                       ev, round(adj_lev, 3), thr, pol))
    if adj_nw is not None and adj_nw <= 0:
        out["findings"].append(finding("ADJ-02", 4, "critical", "Adjusted net worth negative",
                                       f"Adjusted net worth {fm(adj_nw, ccy)} after netting {fm(total_nw, ccy)} (reported {fm(nw, ccy)}).", ev,
                                       round(adj_nw, 3), 0, pol))
    thr, pol = _f("adj_current_ratio")
    if adj_cr is not None and adj_cr < thr:
        out["findings"].append(finding("ADJ-03", 4, "major", "Adjusted current ratio below 1.0x",
                                       f"Adjusted current ratio {xx(adj_cr)} (reported {xx(cr)}) once {fm(total_ca, ccy)} of related-party and shareholder balances leave current assets.",
                                       ev, round(adj_cr, 3), thr, pol))
    if adjustments and (nw is None or cl is None) and total_ca and ca:
        share = total_ca / ca
        out["findings"].append(finding("ADJ-04", 4, "major" if share > 0.25 else "minor", "Current assets carry related-party and shareholder balances",
                                       f"{fm(total_ca, ccy)} ({pc(share)}) of current assets of {fm(ca, ccy)} are due from related parties and shareholders; "
                                       f"adjusted current assets {fm(adj_ca, ccy)}; {', '.join(missing) or 'liabilities'} not provided to complete the adjusted ratios.",
                                       ev, round(share, 4), _f("rp_share_ca")[0], _f("rp_share_ca")[1]))
    return out


# ------------------------------------------------------------------ receivables

def receivables(d: dict[str, Any]) -> dict[str, Any]:
    fin, ccy, ref = d["financials"], d["subject"]["currency"], d["lineage"]["financials"]
    y = _last_audited(fin)
    buckets = [("0-90 days", "recv_0_90"), ("91-180 days", "recv_91_180"), ("181-365 days", "recv_181_365"), ("over 365 days", "recv_over_365")]
    vals = [(lbl, y.get(k)) for lbl, k in buckets]
    tot = y.get("receivables") or (sum(v for _, v in vals if v is not None) if any(v is not None for _, v in vals) else None)
    ageing = [{"bucket": lbl, "amount": v, "share": (v / tot) if v is not None and tot else None} for lbl, v in vals if v is not None]
    over = y.get("recv_over_365")
    over_share = (over / tot) if over is not None and tot else y.get("recv_over_365_share")
    conc = {"top1_share": y.get("top1_share"), "top2_share": y.get("top2_share"), "topn_share": y.get("topn_share"), "topn_n": y.get("topn_n"),
            "names": y.get("top_names") or [], "basis": y.get("concentration_basis") or "receivables by customer"}
    ret = {"receivable": y.get("retention_receivable"), "overdue": y.get("retention_overdue"), "by_year": y.get("retention_by_year") or []}
    rp = y.get("related_party_receivable")
    rp_share = y.get("related_party_share_ca") or ((rp / y["current_assets"]) if rp is not None and y.get("current_assets") else None)
    out: dict[str, Any] = {"year": y.get("year"), "total": tot, "ageing": ageing, "over_365_share": over_share, "concentration": conc,
                           "retention": ret, "related_party": {"amount": rp, "share_of_current_assets": rp_share,
                                                               "share_of_total_assets": y.get("related_party_share_ta")},
                           "cash_cycle_days": y.get("cash_cycle_days"), "source": ref, "findings": []}
    bits = []
    if ageing:
        bits.append(f"receivables {fm(tot, ccy)}, " + ", ".join(f"{a['bucket']} {pc(a['share'])}" for a in ageing if a["share"] is not None))
    elif over_share is not None:
        bits.append(f"{pc(over_share)} of receivables over 1 year")
    if conc["top2_share"] is not None:
        bits.append(f"top 2 {conc['basis'].split(' by ')[0]} {pc(conc['top2_share'])}" + (f" ({', '.join(n['name'] + ' ' + pc(n['share']) for n in conc['names'][:2])})" if conc["names"] else ""))
    if ret["receivable"]:
        bits.append(f"retentions {fm(ret['receivable'], ccy)}" + (f", {fm(ret['overdue'], ccy)} past the defects-liability period" if ret["overdue"] else ""))
    if rp_share is not None:
        bits.append(f"due from related parties {fm(rp, ccy) if rp is not None else ''} ({pc(rp_share)} of current assets)".replace("  ", " "))
    if out["cash_cycle_days"]:
        bits.append(f"cash cycle {out['cash_cycle_days']:.0f} days")
    out["headline"] = (f"FY{y.get('year')}: " + "; ".join(bits) + ".") if bits else "Receivables ageing, concentration and retention not provided."
    ev = [_ev("Audited financials (notes)", out["headline"], ref)]
    thr, pol = _f("recv_over_365_share")
    if over_share is not None and over_share > thr:
        out["findings"].append(finding("RCV-01", 4, "major", "Receivables over 365 days", f"{pc(over_share)} of receivables are over 365 days "
                                       f"(threshold {pc(thr)}); the adjusted view provides for them.", ev, round(over_share, 4), thr, pol))
    thr, pol = _f("top2_share")
    if conc["top2_share"] is not None and conc["top2_share"] > thr:
        out["findings"].append(finding("RCV-02", 4, "major", "Concentration in two counterparties",
                                       f"Top 2 {conc['basis']} = {pc(conc['top2_share'])} (threshold {pc(thr)}).", ev, conc["top2_share"], thr, pol))
    if ret["overdue"]:
        out["findings"].append(finding("RCV-03", 4, "major", "Retentions past their release date",
                                       f"Retentions of {fm(ret['overdue'], ccy)} on completed projects are past the defects-liability period yet carried as not due.",
                                       ev, ret["overdue"], 0, "Credit Policy 8.1.5 Retention receivables"))
    thr, pol = _f("rp_share_ca")
    if rp_share is not None and rp_share > thr:
        out["findings"].append(finding("RCV-04", 4, "critical" if rp_share > 0.5 else "major", "Receivables due from related parties",
                                       f"Due from related parties {fm(rp, ccy)} = {pc(rp_share)} of current assets (threshold {pc(thr)}).", ev, rp_share, thr, pol))
    thr, pol = _f("cash_cycle_days")
    if out["cash_cycle_days"] and out["cash_cycle_days"] > thr:
        out["findings"].append(finding("RCV-05", 4, "minor", "Long cash conversion cycle", f"Cash cycle {out['cash_cycle_days']:.0f} days (threshold {thr} days).",
                                       ev, out["cash_cycle_days"], thr, pol))
    return out


# ------------------------------------------------------------------ auditor

def auditor(d: dict[str, Any]) -> dict[str, Any]:
    fin, ccy, ref = d["financials"], d["subject"]["currency"], d["lineage"]["financials"]
    name, listed, op = fin.get("auditor"), fin.get("auditor_listed"), (fin.get("opinion") or "").lower() or None
    basis, amt, scope = fin.get("qualification_basis"), fin.get("qualification_amount"), fin.get("entity_scope")
    score = 3
    if listed is False:
        score -= 1
    if op in ("qualified", "adverse", "disclaimer"):
        score -= 1 if op == "qualified" else 2
    if scope and "standalone" not in scope:
        score -= 1
    grade = {3: "A", 2: "B", 1: "C"}.get(max(score, 1), "C") if name or op else None
    out: dict[str, Any] = {"auditor": name, "approved_panel": listed, "opinion": op, "qualification_basis": basis, "qualification_amount": amt,
                           "entity_scope": scope, "grade": grade, "source": ref, "findings": []}
    if not name and not op:
        out["headline"] = "Auditor and audit opinion not provided."
    else:
        h = f"{name or 'Auditor not named'} ({'on' if listed else 'not on' if listed is False else 'panel status not provided for'} the approved panel); opinion {op or 'not provided'}"
        if basis:
            h += f", qualified on: {basis.rstrip('. ')}" + (f" ({fm(amt, ccy)})" if amt else "")
        if scope:
            h += f"; {scope} statements"
        out["headline"] = h + f". Audit quality grade {grade}."
    ev = [_ev("Audited financials", out["headline"], ref)]
    if op in ("qualified", "adverse", "disclaimer"):
        out["findings"].append(finding("AUD-01", 4, "critical" if op != "qualified" else "major", f"Audit opinion {op}",
                                       f"The FY audit opinion is {op}" + (f"; basis: {basis.rstrip('. ')}" + (f" ({fm(amt, ccy)})" if amt else "") if basis else "; basis not provided") +
                                       ". Net worth is adjusted for the qualified amount.", ev, op, "unqualified",
                                       "Credit Policy 5.2.4 Qualified opinions and their basis"))
    if listed is False:
        out["findings"].append(finding("AUD-02", 4, "major", "Auditor not on the approved panel", f"{name} is not on the bank's approved auditor list.", ev,
                                       name, "approved panel", "Credit Policy 5.2.5 Approved auditors"))
    return out


# ------------------------------------------------------------------ bureau and other banks

CLASSIFIED = ("substandard", "doubtful", "loss")


def bureau_matrix(d: dict[str, Any]) -> dict[str, Any]:
    bu, ccy, lin = d["bureau"], d["subject"]["currency"], d["lineage"]
    ents = bu.get("entities") or []
    cb = bu.get("cbrbr") or []
    ob = bu.get("other_banks") or []
    banks = sorted({r["bank"] for r in ob if r.get("bank")})
    entities = sorted({r["entity"] for r in ob if r.get("entity")})
    matrix = [{"bank": b, **{e: next((r.get("bureau_limit") if r.get("bureau_limit") is not None else r.get("declared_limit")
                                     for r in ob if r["bank"] == b and r["entity"] == e), None) for e in entities}} for b in banks]
    tol, pol = _f("reconcile_tol")
    recon = []
    for r in ob:
        dcl, bur = r.get("declared_limit"), r.get("bureau_limit")
        gap = None if dcl is None or bur is None else bur - dcl
        status = ("not declared" if (dcl is None or dcl == 0) and bur else "not in bureau" if bur is None and dcl is not None else
                  "reconciles" if gap is not None and abs(gap) <= tol * max(abs(bur), 1e-9) else "not reconciled" if gap is not None else "not provided")
        recon.append({"bank": r.get("bank"), "entity": r.get("entity"), "declared": dcl, "bureau": bur, "gap": None if gap is None else round(gap, 3),
                      "gap_share": None if gap is None or not dcl else round(gap / dcl, 4), "status": status, "letter": r.get("letter")})
    tot_d = sum(r["declared"] for r in recon if r["declared"] is not None) if any(r["declared"] is not None for r in recon) else None
    tot_b = sum(r["bureau"] for r in recon if r["bureau"] is not None) if any(r["bureau"] is not None for r in recon) else None
    out: dict[str, Any] = {"entities": ents, "cbrbr": cb, "matrix": {"banks": banks, "entities": entities, "rows": matrix},
                           "reconciliation": recon, "totals": {"declared": tot_d, "bureau": tot_b,
                                                               "gap": None if tot_d is None or tot_b is None else round(tot_b - tot_d, 3)},
                           "not_provided": [e["entity"] for e in ents if not e.get("provided", True)],
                           "source": {"bureau": lin["bureau"], "cbrbr": lin["cbrbr"], "other_banks": lin["other_banks"]}, "findings": []}
    bits = [f"{len(ents)} bureau report{'s' if len(ents) != 1 else ''}"]
    rc = sum(int(e.get("returned_cheques") or 0) for e in ents)
    if rc:
        bits.append(f"{rc} returned cheques")
    cls = [e for e in ents + cb if str(e.get("classification") or "").lower() in CLASSIFIED]
    seen: set[str] = set()
    cls = [e for e in cls if not (e["entity"] in seen or seen.add(e["entity"]))]
    if cls:
        bits.append("classified: " + ", ".join(f"{e['entity']} {e['classification']}" for e in cls[:3]))
    pdue = [e for e in ents if "past due" in str(e.get("classification") or "").lower()]
    if pdue:
        bits.append("past due in the bureau: " + ", ".join(f"{e['entity']} {e['classification'].replace(' past due', '')}" for e in pdue[:3]))
    if out["totals"]["gap"] is not None:
        bits.append(f"other-bank limits declared {fm(tot_d, ccy)} against bureau {fm(tot_b, ccy)} (gap {fm(out['totals']['gap'], ccy)})")
    out["headline"] = "; ".join(bits) + "."
    ev_b = lambda t: [_ev("Credit bureau and CBRBR", t, lin["bureau"])]  # noqa: E731
    for r in recon:
        if r["status"] in ("not reconciled", "not declared"):
            out["findings"].append(finding("BUR-01", 2, "critical" if (r["gap"] or 0) > 0.25 * max(r["declared"] or 0, 1e-9) or r["declared"] is None else "major",
                                           "Other-bank limits do not reconcile with the bureau",
                                           (f"{r['bank']} / {r['entity']}: not declared by the client; the bureau shows {fm(r['bureau'], ccy)}"
                                            if r["status"] == "not declared" else
                                            f"{r['bank']} / {r['entity']}: client declared {fm(r['declared'], ccy)}, bureau shows {fm(r['bureau'], ccy)}"
                                            + (f" (gap {fm(r['gap'], ccy)}" + (f", {pc(r['gap_share'])})" if r["gap_share"] is not None else ")") if r["gap"] is not None else ""))
                                           + "; not clarified.",
                                           ev_b("Declared against CBRBR"), r["gap"], tol, pol))
    for e in ents:
        if int(e.get("returned_cheques") or 0) > 0:
            out["findings"].append(finding("BUR-03", 2, "major", "Returned cheques in the bureau",
                                           f"{e['entity']}: {int(e['returned_cheques'])} returned cheques" + (f" ({e['returned_cheque_dates']})" if e.get("returned_cheque_dates") else "") + ".",
                                           ev_b(e["entity"]), int(e["returned_cheques"]), 0, "Credit Policy 6.1.3 Returned cheques"))
        if str(e.get("classification") or "").lower() in CLASSIFIED:
            out["findings"].append(finding("BUR-04", 6, "critical", "Group or connected entity classified",
                                           f"{e['entity']} ({e.get('role')}) classified {e['classification']}" + (f", outstanding {fm(e.get('outstanding'), ccy)}" if e.get("outstanding") else "")
                                           + (f", litigation {fm(e.get('litigation'), ccy)}" if e.get("litigation") else "") + ".",
                                           ev_b(e["entity"]), e["classification"], "Regular", "CBUAE CRM Art. 6.12 Connected obligors"))
        if int(e.get("court_cases") or 0) > 0 and str(e.get("classification") or "").lower() not in CLASSIFIED:
            out["findings"].append(finding("BUR-06", 6, "major", "Court cases in the bureau", f"{e['entity']}: {int(e['court_cases'])} court case(s).",
                                           ev_b(e["entity"]), int(e["court_cases"]), 0, "Credit Policy 6.1.4 Litigation"))
    return out


# ------------------------------------------------------------------ status of earlier conditions

def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(str(b)[:10]) - dt.date.fromisoformat(str(a)[:10])).days


def earlier_conditions(d: dict[str, Any]) -> dict[str, Any]:
    ref = d["lineage"]["earlier"]
    rows = []
    for c in d.get("earlier") or []:
        req, ach, unit = c.get("required"), c.get("achieved"), c.get("unit")
        status, measure, pct_ = c.get("status"), "", None
        try:
            if unit == "date":
                if ach:
                    late = _days(req, ach)
                    status = status or ("complied" if late <= 0 else "complied late")
                    measure = f"due {req}, met {ach}" + (f" ({late} days late)" if late > 0 else "")
                else:
                    status, measure = status or "not complied", f"due {req}, not met"
            elif unit == "flag":
                status = status or ("complied" if ach else "not complied")
                measure = "complied" if ach else "breached"
            elif req not in (None, "") and ach is not None:
                pct_ = float(ach) / float(req) if float(req) else None
                status = status or ("complied" if pct_ is not None and pct_ >= 1 else "not complied")
                measure = f"{float(ach):g}{unit or ''} against {float(req):g}{unit or ''}: {pc(pct_)} achieved"
        except (TypeError, ValueError):
            measure = str(ach)
        if not measure:
            measure = f"checked {c['measured_at']}" if c.get("measured_at") else "no measurement recorded"
        rows.append({**c, "text": str(c.get("text") or "").rstrip(". "), "status": status or "open", "measure": measure, "achieved_share": None if pct_ is None else round(pct_, 4), "source": ref})
    prom = []
    for pr in d.get("promises") or []:
        pct_ = (_num(pr.get("delivered_pct")) or 0) / 100.0 if pr.get("delivered_pct") is not None else None
        prom.append({"promise_id": pr.get("promise_id"), "kind": pr.get("kind"), "text": str(pr.get("text") or "").rstrip(". "),
                     "promised": _num(pr.get("promised_mn")), "delivered": _num(pr.get("delivered_mn")), "delivered_share": pct_,
                     "status": pr.get("status"), "window": f"{pr.get('window_from')} to {pr.get('window_to')}", "committee_ref": pr.get("committee_ref"),
                     "source": {"relation": "dd_promise", "key": {"promise_id": pr.get("promise_id")}, "period": pr.get("reporting_quarter")}})
    out: dict[str, Any] = {"rows": rows, "promises": prom, "source": ref, "findings": []}
    nc = [r for r in rows if r["status"] in ("not complied", "complied late")]
    out["headline"] = (f"{len(rows)} condition{'s' if len(rows) != 1 else ''} of the previous approval; " +
                       (f"{len(nc)} not complied: " + "; ".join(f"{r['text']} ({r['measure'] if not r['measure'].startswith(('checked', 'no measurement')) else r['status']})" for r in nc) if nc else "all complied") + ".") if rows else \
        "No conditions recorded on the previous approval."
    routed = any("rout" in str(r.get("text") or "").lower() or "rout" in str(r.get("metric") or "") for r in nc)
    for pr in prom:
        if pr["delivered_share"] is not None and pr["delivered_share"] < 0.8 and not (pr["kind"] == "routing" and routed):
            out["findings"].append(finding("TRK-02", 8, "major", "Promised business not delivered",
                                           f"{pr['text']}: delivered {fm(pr['delivered'])} of {fm(pr['promised'])} ({pc(pr['delivered_share'])}) in {pr['window']}"
                                           + (f" ({pr['committee_ref']})" if pr.get("committee_ref") else "") + ".",
                                           [_ev("Promises register", pr["text"], pr["source"])], pr["delivered_share"], 0.8,
                                           "Credit Policy 9.4 Relationship commitments measured against account flows"))
    for r in nc:
        out["findings"].append(finding("TRK-01", 8, "major" if r["status"] == "not complied" else "minor", "Earlier condition not complied",
                                       (f"{r['text']}: {r['status']}, {r['measure']}." if r["measure"].startswith(("checked", "no measurement")) else
                                        f"{r['text']}: {r['measure']} (status: {r['status']})."),
                                       [_ev("Conditions register", r["measure"], ref)],
                                       r.get("achieved"), r.get("required"), f"Previous approval ({r.get('committee_ref') or 'committee'})"))
    return out


# ------------------------------------------------------------------ insider and staff links

def insider_links(d: dict[str, Any]) -> dict[str, Any]:
    ref = d["lineage"]["insider"]
    rows = [{**r, "kind": r.get("kind") or ("staff" if "staff" in str(r.get("person") or r.get("link") or "").lower() else "insider"), "source": ref}
            for r in d.get("insider") or []]
    out: dict[str, Any] = {"rows": rows, "source": ref, "findings": []}
    out["headline"] = ("; ".join(f"{r['person']} holds {pc(r['share'])} of {r['party']} ({r['link']})" if r.get("share") is not None
                                 else f"{r['person']}: {r['link']} in {r['party']}" for r in rows) + ".") if rows else "No staff or insider links found."
    for r in rows:
        if r["kind"] == "staff":
            out["findings"].append(finding("INS-01", 6, "critical", "Staff interest in a party to the deal",
                                           f"{r['person']} holds {pc(r['share'])} of {r['party']}; the conflict must be declared and the approval taken above the staff member's line.",
                                           [_ev(r.get("source_note") or "Staff interest declarations", out["headline"], ref)], r.get("share"), 0,
                                           "Credit Policy 10.2 Staff and insider lending; CBUAE CRM Art. 6.12"))
        elif r["kind"] == "related":
            out["findings"].append(finding("INS-02", 6, "major", "Undisclosed related holding",
                                           f"{r['person']} holds {pc(r['share'])} of {r['party']} ({r['link']}), not disclosed in the proposal.",
                                           [_ev(r.get("source_note") or "Connected-party register", out["headline"], ref)], r.get("share"), 0,
                                           "Credit Policy 10.3 Related parties"))
    return out


def _num(x: Any) -> float | None:
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ conduct against claimed turnover; projections against history

def conduct_check(d: dict[str, Any]) -> dict[str, Any]:
    c, ccy, ref = d.get("conduct") or {}, d["subject"]["currency"], d["lineage"].get("conduct")
    y = _last_audited(d["financials"])
    rev, turn = y.get("revenue"), c.get("turnover")
    share = c.get("turnover_to_revenue") if c.get("turnover_to_revenue") is not None else ((turn / rev) if turn and rev else None)
    out: dict[str, Any] = {"turnover": turn, "revenue": rev, "turnover_to_revenue": share, "months": c.get("months"),
                           "returned_cheques": c.get("returned_cheques"), "source": ref, "findings": []}
    out["headline"] = (f"Account credit turnover {fm(turn, ccy)} over {c.get('months')} months against reported revenue of {fm(rev, ccy)} (FY{y.get('year')}): "
                       f"{pc(share)} routed through the bank." if share is not None and turn else
                       (f"Account turnover covers {pc(share)} of reported revenue." if share is not None else "Account conduct not available for this obligor."))
    if share is not None and share < 0.5:
        out["findings"].append(finding("CND-01", 2, "major" if share < 0.35 else "minor", "Conduct does not support the reported turnover",
                                       out["headline"] + " The rest of the business is banked elsewhere or not evidenced.",
                                       [_ev("Account conduct", out["headline"], ref)], round(share, 4), 0.5,
                                       "Credit Policy 6.3.2 Turnover through the account against reported sales"))
    return out


def projections_check(d: dict[str, Any]) -> dict[str, Any]:
    ys = d["financials"].get("years") or []
    hist = [y for y in ys if str(y.get("kind")) in ("audited", "actual") and y.get("revenue")]
    proj = [y for y in ys if str(y.get("kind")) == "projection" and y.get("revenue")]
    ref = d["lineage"]["financials"]
    out: dict[str, Any] = {"historical": [{"year": y["year"], "revenue": y["revenue"], "ebitda": y.get("ebitda")} for y in hist],
                           "projected": [{"year": y["year"], "revenue": y["revenue"], "ebitda": y.get("ebitda")} for y in proj], "source": ref, "findings": []}
    if len(hist) < 2 or not proj:
        out["headline"] = "Projections not provided; nothing to test against history." if not proj else "Fewer than two audited years: projections not tested."
        return out
    def cagr(a: dict[str, Any], b: dict[str, Any]) -> float:
        n = max(int(b["year"]) - int(a["year"]), 1)
        return (b["revenue"] / a["revenue"]) ** (1 / n) - 1 if a["revenue"] > 0 else 0.0
    g_h, g_p = cagr(hist[0], hist[-1]), cagr(hist[-1], proj[-1])
    m_h = max((y["ebitda"] / y["revenue"] for y in hist if y.get("ebitda") is not None), default=None)
    m_p = max((y["ebitda"] / y["revenue"] for y in proj if y.get("ebitda") is not None), default=None)
    out.update({"revenue_cagr_history": round(g_h, 4), "revenue_cagr_projected": round(g_p, 4), "best_margin_history": m_h, "best_margin_projected": m_p})
    out["headline"] = (f"Revenue grew {pc(g_h, 1)} a year over FY{hist[0]['year']}-FY{hist[-1]['year']}; the projections assume {pc(g_p, 1)} a year to "
                       f"FY{proj[-1]['year']}" + (f"; best EBITDA margin {pc(m_h, 1)} achieved against {pc(m_p, 1)} projected" if m_h is not None and m_p is not None else "") + ".")
    if g_p > max(2 * g_h, g_h + 0.05) and g_p > 0.08:
        out["findings"].append(finding("PRJ-H1", 4, "major", "Projections well above the track record (hockey stick)", out["headline"],
                                       [_ev("Financial spreading", out["headline"], ref)], round(g_p, 4), round(max(2 * g_h, g_h + 0.05), 4),
                                       "Credit Policy 3.4 Projections tested against history"))
    if m_h is not None and m_p is not None and m_p > m_h + 0.03:
        out["findings"].append(finding("PRJ-H2", 4, "minor", "Projected margin never reached",
                                       f"Projected EBITDA margin {pc(m_p, 1)} against a best of {pc(m_h, 1)} in the audited years.",
                                       [_ev("Financial spreading", out["headline"], ref)], round(m_p, 4), round(m_h + 0.03, 4),
                                       "Credit Policy 3.4 Projections tested against history"))
    return out


def all_for(d: dict[str, Any]) -> dict[str, Any]:
    return {"adjusted": adjusted_ratios(d), "receivables": receivables(d), "auditor": auditor(d), "bureau": bureau_matrix(d),
            "earlier": earlier_conditions(d), "insider": insider_links(d), "conduct": conduct_check(d), "projections": projections_check(d)}
