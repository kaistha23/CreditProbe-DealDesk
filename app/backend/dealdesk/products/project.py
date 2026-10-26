"""PLAN_R12 Session P (I28): contracting and project-limit analytics.

  status_table     financed-projects status (anatomy §2.9): employer, consultant, contract value original and revised,
                   start and completion, work done against plan, extension of time (formalised or not), billed,
                   received, due and how late, last payment certificate, remaining contract proceeds, retention
  cash_flow        the monthly project cash flow (costs, receipts, advance, retention), cumulative position, the
                   deficit and its peak month (anatomy §2.13); base scenario of `dd_project_cashflow`
  delay_stress     receipts (not the advance) delayed 30 / 60 / 90 days: peak deficit, month, extra funding, stressed
                   cover ratio, and whether the peak stays within the funded limit
  cover_ratio      remaining contract proceeds / funded outstanding (the T&C "cover ratio", anatomy §2.5)
  lg_book          bid bond, APG, performance bond, retention bond (and LC / LCM / other LGs) with their CCFs and EAD
  employer_credit  backlog and receivables by employer, concentration, payment delay, bureau

Relations (contract `docs/v5/R12_DATA_CONTRACT.md`): dd_project, dd_project_cashflow, dd_facility_limit,
bureau_entity_report. All amounts SAR million. Every figure carries its lineage.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from backend.dealdesk.products import policy, source

PRODUCT = "contracting"
LG_TYPES = {"bid_bond": "Bid bond", "apg": "Advance payment guarantee", "pb": "Performance bond", "rb": "Retention bond",
            "lg": "Other guarantee", "lg_cash": "Guarantee against cash", "financial_lg": "Financial guarantee",
            "lc": "Letter of credit", "lcm": "LC margin / usance (LCM)"}
_LG_ALIAS = {"bb": "bid_bond", "bid bond": "bid_bond", "bid_bond": "bid_bond", "tender bond": "bid_bond",
             "apg": "apg", "advance payment guarantee": "apg", "pb": "pb", "performance bond": "pb", "performance_lg": "pb",
             "rb": "rb", "retention bond": "rb", "lg": "lg", "lg_cash": "lg_cash", "financial_lg": "financial_lg",
             "financial guarantee": "financial_lg", "lc_sight": "lc", "lc_usance": "lc", "lc": "lc", "trade_lc": "lc", "lcm": "lcm"}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return d if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return d


def _pct(x: Any) -> float | None:
    """A share as a fraction, whether the relation stores 62.5 or 0.625 (contract `%` columns are 0-100)."""
    if x is None or x == "":
        return None
    v = _f(x)
    return v / 100.0 if v > 1.5 else v


def _date(x: Any) -> dt.date | None:
    if not x:
        return None
    if isinstance(x, dt.date):
        return x
    s = str(x)[:10]
    try:
        return dt.date.fromisoformat(s if len(s) == 10 else s + "-01")
    except ValueError:
        return None


def _bool(x: Any) -> bool | None:
    if x is None or x == "":
        return None
    if isinstance(x, str):
        return x.strip().lower() in ("1", "true", "yes", "y")
    return bool(x)


def _m(v: float, ccy: str = "SAR") -> str:
    return f"{ccy} {v:,.1f}m"


def _mon(m: str | None) -> str:
    d = _date(m) if m else None
    return d.strftime("%b %Y") if d else str(m)


def _month_key(x: Any) -> str:
    d = _date(x)
    return d.strftime("%Y-%m") if d else str(x)[:7]


def lg_type(x: Any) -> str | None:
    if x is None:
        return None
    return _LG_ALIAS.get(str(x).strip().lower().replace("-", " "))


# ------------------------------------------------------------------ financed projects status


def _as_of(rows: list[dict[str, Any]], as_of: dt.date | None) -> dt.date:
    if as_of:
        return as_of
    q = next((r.get("reporting_quarter") for r in rows if r.get("reporting_quarter")), None)
    if q and len(str(q)) == 6 and str(q)[4] == "Q":
        y, n = int(str(q)[:4]), int(str(q)[5])
        return dt.date(y, 3 * n, 30 if n in (2, 3) else 31)
    ds = [d for d in (_date(r.get("last_cert_date")) for r in rows) if d]
    return max(ds) if ds else dt.date.today()


def project_row(r: dict[str, Any], as_of: dt.date, funded_outstanding: float = 0.0) -> dict[str, Any]:
    rel = "dd_project"
    orig = _f(r.get("contract_value_original_mn"))
    rev = _f(r.get("contract_value_revised_mn")) or orig
    wd = _pct(r.get("work_done_pct")) or 0.0
    plan = _pct(r.get("planned_pct"))
    received, due, billed = _f(r.get("received_mn")), _f(r.get("due_mn")), _f(r.get("billed_mn"))
    start, end0 = _date(r.get("start_date")), _date(r.get("completion_original"))
    end1 = _date(r.get("completion_revised")) or end0
    elapsed = None
    if start and end1 and end1 > start:
        elapsed = max(0.0, min(1.0, (as_of - start).days / (end1 - start).days))
    eot_days = int(_f(r.get("eot_days")))
    if not eot_days and end0 and end1 and end1 > end0:
        eot_days = (end1 - end0).days
    formal = _bool(r.get("eot_formalised_flag"))
    last_cert = _date(r.get("last_cert_date"))
    days_due = int(_f(r.get("payment_delay_days"))) if r.get("payment_delay_days") is not None else \
        ((as_of - last_cert).days if (due > 0 and last_cert) else 0)
    remaining = max(0.0, rev - received)
    ref = plan if plan is not None else elapsed
    slip = None if ref is None else round((ref - wd) * 100, 1)
    status = str(r.get("status") or "").lower()
    flags = []
    watch = float(policy.v("project.slip_watch_pts", PRODUCT))
    if slip is not None and slip >= watch and status != "new":
        flags.append(f"Work done {wd:.0%} against {ref:.0%} {'planned' if plan is not None else 'of time elapsed'} ({slip:.0f} points behind)")
    if eot_days and formal is False:
        flags.append(f"Extension of time of {eot_days} days not formalised")
    if end1 and as_of > end1 and wd < 0.999 and status != "completed":
        flags.append(f"Past the completion date {end1.isoformat()} at {wd:.0%} work done")
    if due > 0 and days_due > 90:
        flags.append(f"{_m(due)} certified and unpaid for {days_due} days")
    if _bool(r.get("demand_letter_flag")):
        flags.append("Demand or claim letter on file")
    s = lambda c: source.src(rel, r, c)  # noqa: E731
    return {
        "project_id": r.get("project_id"), "project_name": r.get("project_name") or r.get("project_id"), "status": status or None,
        "employer": r.get("employer"), "employer_entity_id": r.get("employer_entity_id"), "consultant": r.get("consultant"),
        "currency": "SAR", "limit_id": r.get("limit_id"),
        "contract_value_original": orig, "contract_value_revised": rev, "variation_pct": (rev / orig - 1) if orig else None,
        "start_date": start.isoformat() if start else None, "completion_date_original": end0.isoformat() if end0 else None,
        "completion_date_revised": end1.isoformat() if end1 else None,
        "wd_pct": wd, "planned_pct": plan, "time_elapsed_pct": elapsed, "slip_pts": slip,
        "eot_days": eot_days, "eot_formalised": formal,
        "eot_label": "None" if not eot_days else f"{eot_days} days, " + ("formalised" if formal else "not formalised" if formal is False else "status not provided"),
        "billed": billed, "amount_received": received, "amount_due": due, "days_due": days_due,
        "retention": _f(r.get("retention_mn")), "advance": _f(r.get("advance_mn")), "pending_certs": int(_f(r.get("pending_certs_n"))),
        "last_certificate": {"no": r.get("last_cert_no"), "date": last_cert.isoformat() if last_cert else None,
                             "last_payment": r.get("last_payment_date")},
        "remaining_proceeds": remaining, "backlog": _f(r.get("backlog_mn")) if r.get("backlog_mn") is not None else max(0.0, rev - billed),
        "financed": bool(_bool(r.get("financed_flag")) if r.get("financed_flag") is not None else True),
        "funded_outstanding": funded_outstanding, "narrative": r.get("narrative"), "flags": flags,
        "src": {"contract_value_revised": s("contract_value_revised_mn"), "wd_pct": s("work_done_pct"), "amount_received": s("received_mn"),
                "amount_due": s("due_mn"), "eot_days": s("eot_days"), "last_certificate": s("last_cert_date"),
                "remaining_proceeds": source.derived(s("contract_value_revised_mn"), s("received_mn"),
                                                     method="contract value revised - received")},
    }


def status_table(projects: list[dict[str, Any]], as_of: dt.date | None = None,
                 funded_by_project: dict[str, float] | None = None) -> dict[str, Any]:
    d = _as_of(projects, as_of)
    fb = funded_by_project or {}
    rows = [project_row(r, d, fb.get(str(r.get("project_id")), 0.0)) for r in projects]
    fin = [r for r in rows if r["financed"]]
    tot = lambda k, rs=rows: sum(x[k] for x in rs)  # noqa: E731
    return {"as_of": d.isoformat(), "rows": rows,
            "totals": {"projects": len(rows), "financed": len(fin), "contract_value_revised": tot("contract_value_revised"),
                       "amount_received": tot("amount_received"), "amount_due": tot("amount_due"),
                       "remaining_proceeds": tot("remaining_proceeds"), "backlog": tot("backlog"),
                       "with_flags": sum(1 for r in rows if r["flags"]),
                       "eot_not_formalised": sum(1 for r in rows if r["eot_days"] and r["eot_formalised"] is False),
                       "src": source.derived(*[r["src"]["contract_value_revised"] for r in rows], method="sum over the projects")}}


# ------------------------------------------------------------------ project cash flow and delay stress


def _series(cf: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[float]], list[dict[str, Any]]]:
    """Monthly sums over the base scenario. Contract receipts include the advance received; it is split out so a
    payment delay moves the employer's payments, not the advance."""
    by: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    srcs: list[dict[str, Any]] = []
    for r in cf:
        if str(r.get("scenario") or "base").lower() != "base":
            continue
        m = _month_key(r.get("month"))
        adv = _f(r.get("advance_in_mn"))
        by[m]["costs"] += _f(r.get("cost_total_mn"))
        by[m]["advance"] += adv
        by[m]["receipts"] += _f(r.get("receipts_mn")) - adv
        by[m]["retention"] += _f(r.get("retention_held_mn"))
        srcs.append(source.src("dd_project_cashflow", r))
    months = sorted(by)
    return months, {k: [by[m][k] for m in months] for k in ("costs", "receipts", "advance", "retention")}, srcs


def _position(months: list[str], costs: list[float], inflow: list[float]) -> dict[str, Any]:
    cum, c, deficit = [], 0.0, []
    for i in range(len(months)):
        c += inflow[i] - costs[i]
        cum.append(c)
        deficit.append(max(0.0, -c))
    peak = max(deficit) if deficit else 0.0
    pm = months[deficit.index(peak)] if deficit and peak > 0 else None
    return {"cumulative": cum, "deficit": deficit, "peak_deficit": peak, "peak_month": pm,
            "months_in_deficit": sum(1 for x in deficit if x > 0)}


def _shift(xs: list[float], days: int) -> list[float]:
    """Receipts delayed by `days` (30 days = one month; fractions split between the two months). The tail beyond the
    horizon is received after the last month and drops out of the window."""
    k, frac = divmod(days / 30.0, 1.0)
    k = int(k)
    out = [0.0] * len(xs)
    for i, x in enumerate(xs):
        for j, w in ((i + k, 1 - frac), (i + k + 1, frac)):
            if w and j < len(xs):
                out[j] += x * w
    return out


def cash_flow(cf: list[dict[str, Any]]) -> dict[str, Any]:
    months, s, srcs = _series(cf)
    inflow = [s["receipts"][i] + s["advance"][i] for i in range(len(months))]
    pos = _position(months, s["costs"], inflow)
    return {"months": months, **s, "net": [inflow[i] - s["costs"][i] for i in range(len(months))], **pos,
            "total_costs": sum(s["costs"]), "total_receipts": sum(s["receipts"]), "total_advance": sum(s["advance"]),
            "retention_held": sum(s["retention"]), "projects": sorted({str(r.get("project_id")) for r in cf}),
            "src": source.derived(*srcs, method="cumulative (receipts - costs), base scenario; deficit = max(0, -cumulative)")}


def delay_stress(cf: list[dict[str, Any]], funded_outstanding: float, remaining_proceeds: float, funded_limit: float | None,
                 days: list[int] | None = None) -> dict[str, Any]:
    base = cash_flow(cf)
    months = base["months"]
    rows = [{"delay_days": 0, "label": "Base", "peak_deficit": base["peak_deficit"], "peak_month": base["peak_month"],
             "extra_funding": 0.0, "deficit": base["deficit"]}]
    for d in days or list(policy.v("project.delay_days", PRODUCT)):
        inflow = [a + b for a, b in zip(_shift(base["receipts"], int(d)), base["advance"], strict=True)]
        pos = _position(months, base["costs"], inflow)
        rows.append({"delay_days": int(d), "label": f"Payments {int(d)} days late", "peak_deficit": pos["peak_deficit"],
                     "peak_month": pos["peak_month"], "extra_funding": pos["peak_deficit"] - base["peak_deficit"],
                     "deficit": pos["deficit"]})
    mn = float(policy.v("project.cover_ratio_min", PRODUCT))
    for r in rows:
        fo = funded_outstanding + r["extra_funding"]
        r["funded_outstanding"] = fo
        r["cover_ratio"] = (remaining_proceeds / fo) if fo > 0 else None
        r["cover_ok"] = r["cover_ratio"] is None or r["cover_ratio"] >= mn
        r["within_limit"] = None if funded_limit is None else r["peak_deficit"] <= funded_limit + 1e-9
        r["headroom"] = None if funded_limit is None else funded_limit - r["peak_deficit"]
    breaks = next((r for r in rows if (r["within_limit"] is False) or not r["cover_ok"]), None)
    return {"months": months, "rows": rows, "cover_ratio_min": mn, "funded_limit": funded_limit,
            "first_break": None if breaks is None else {"delay_days": breaks["delay_days"],
                                                        "what": "peak deficit exceeds the funded limit" if breaks["within_limit"] is False
                                                        else f"cover ratio below {mn:.2f}x"},
            "src": base["src"]}


def cover_ratio(remaining_proceeds: float, funded_outstanding: float, srcs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    mn, psrc = policy.value("project.cover_ratio_min", PRODUCT)
    ratio = (remaining_proceeds / funded_outstanding) if funded_outstanding > 0 else None
    return {"remaining_proceeds": remaining_proceeds, "funded_outstanding": funded_outstanding, "ratio": ratio, "min": float(mn),
            "ok": ratio is None or ratio >= float(mn),
            "text": "No funded outstanding against the projects" if ratio is None else
            f"Remaining contract proceeds {_m(remaining_proceeds)} cover funded outstanding {_m(funded_outstanding)} "
            f"{ratio:.2f}x (minimum {float(mn):.2f}x)",
            "src": source.derived(*(srcs or []), method="remaining contract proceeds / funded outstanding (dd_facility_limit)"),
            "min_src": psrc}


# ------------------------------------------------------------------ the limit tree: LGs, funded limit and outstanding


def _ccf_rows() -> dict[str, dict[str, float]]:
    try:
        from backend.dealdesk import params
        return params.rows("ccf")
    except Exception:  # noqa: BLE001
        return {"performance_lg": {"regulatory": 0.5, "economic": 0.5}, "financial_lg": {"regulatory": 1.0, "economic": 1.0},
                "trade_lc": {"regulatory": 0.2, "economic": 0.2}}


def _code(r: dict[str, Any]) -> str | None:
    return lg_type(r.get("product_code"))


def lg_book(limits: list[dict[str, Any]]) -> dict[str, Any]:
    ccf, row_map = _ccf_rows(), dict(policy.v("lg.ccf_row", PRODUCT))
    row_map.setdefault("lg", "performance_lg")
    row_map.setdefault("lg_cash", "performance_lg")
    out = []
    for r in limits:
        t = _code(r)
        if t is None or _bool(r.get("funded_flag")):
            continue
        amt = _f(r.get("proposed_mn"))
        cm = _pct(r.get("cash_margin_pct")) or (1.0 if t == "lg_cash" else 0.0)
        crow = row_map.get(t, "performance_lg")
        reg, eco = float(ccf.get(crow, {}).get("regulatory", 0.5)), float(ccf.get(crow, {}).get("economic", 0.5))
        net = amt * (1 - cm)
        out.append({"limit_id": r.get("limit_id"), "parent_limit_id": r.get("parent_limit_id"), "type": t, "label": LG_TYPES[t],
                    "name": r.get("limit_name"), "project_id": r.get("project_id"), "existing": _f(r.get("existing_mn")),
                    "outstanding": _f(r.get("outstanding_mn")), "proposed": amt, "cash_margin_pct": cm,
                    "commission_pct_pa": r.get("commission_pct_pa"), "ccf_row": crow, "ccf_regulatory": reg, "ccf_economic": eco,
                    "ead_regulatory": net * reg, "ead_economic": net * eco,
                    "src": {"proposed": source.src("dd_facility_limit", r, "proposed_mn"),
                            "ccf": {"domain": "Deal Desk", "relation": "dd_parameter", "key": {"table_name": "ccf", "param_key": crow}}}})
    by: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for x in out:
        for k in ("proposed", "outstanding", "ead_regulatory", "ead_economic"):
            by[x["type"]][k] += x[k]
    srcs = [x["src"]["proposed"] for x in out]
    return {"src": source.derived(*srcs, {"relation": "dd_parameter", "key": {"table_name": "ccf"}}, method="LG limits x CCF")
            if srcs else None,
            "rows": out, "by_type": [{"type": k, "label": LG_TYPES[k], **v} for k, v in by.items()],
            "total_proposed": sum(x["proposed"] for x in out), "total_ead_regulatory": sum(x["ead_regulatory"] for x in out)}


def _funded_tops(limits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Funded limits at the top of the funded tree (a sub-limit sits inside its parent; a level-0 umbrella is skipped
    when it also carries non-funded lines)."""
    fl = [r for r in limits if _bool(r.get("funded_flag")) and _code(r) is None and int(_f(r.get("level"), 1)) >= 1]
    ids = {r.get("limit_id") for r in fl}
    return [r for r in fl if r.get("parent_limit_id") not in ids]


def funded_limit(limits: list[dict[str, Any]]) -> float | None:
    tops = _funded_tops(limits)
    return sum(_f(r.get("proposed_mn")) for r in tops) if tops else None


def funded_outstanding(limits: list[dict[str, Any]]) -> float:
    return sum(_f(r.get("outstanding_mn")) for r in _funded_tops(limits))


def funded_by_project(limits: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in limits:
        if r.get("project_id") and _bool(r.get("funded_flag")) and _code(r) is None:
            out[str(r["project_id"])] += _f(r.get("outstanding_mn"))
    return dict(out)


# ------------------------------------------------------------------ employer credit


def employer_credit(status: dict[str, Any], bureau: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    by: dict[str, dict[str, Any]] = {}
    for r in status["rows"]:
        e = r["employer"] or "Not provided"
        b = by.setdefault(e, {"employer": e, "entity_id": r.get("employer_entity_id"), "projects": 0, "backlog": 0.0, "amount_due": 0.0,
                              "max_days_due": 0, "contract_value": 0.0, "rating": None, "src": []})
        b["projects"] += 1
        b["backlog"] += r["backlog"]
        b["amount_due"] += r["amount_due"]
        b["contract_value"] += r["contract_value_revised"]
        b["max_days_due"] = max(b["max_days_due"], r["days_due"])
        b["src"].append(r["src"]["wd_pct"])
    total = sum(b["backlog"] for b in by.values()) or 0.0
    rows = sorted(by.values(), key=lambda b: -b["backlog"])
    for b in rows:
        b["backlog_share"] = b["backlog"] / total if total else None
        br = [x for x in (bureau or []) if (b["entity_id"] and x.get("entity_id") == b["entity_id"])
              or str(x.get("entity_name") or "").strip().lower() == str(b["employer"]).lower()]
        x = br[0] if br else None
        b["bureau"] = None if x is None else (
            {"provided": False, "reason": x.get("not_provided_reason"), "src": source.src("bureau_entity_report", x)}
            if _bool(x.get("provided_flag")) is False else
            {"provided": True, "overdue": _f(x.get("overdue_mn")), "returned_cheques": int(_f(x.get("returned_cheques_n"))),
             "score": x.get("score"), "court_cases": int(_f(x.get("court_cases_n"))), "worst_status": x.get("worst_status"),
             "src": source.src("bureau_entity_report", x)})
        b["src"] = source.derived(*b["src"], method="sum over projects of the remaining backlog (dd_project.backlog_mn)")
    mx = float(policy.v("project.employer_concentration_max", PRODUCT))
    n_top = 2 if len(rows) > 2 else 1   # with two employers or fewer the top-2 share is trivially 100%
    top = sum(b["backlog_share"] or 0 for b in rows[:n_top])
    text = ("No projects" if not rows else
            (f"The top 2 employers hold {top:.0%} of the remaining backlog" if n_top == 2
             else f"{rows[0]['employer']} holds {top:.0%} of the remaining backlog")
            + f" ({'above' if top > mx else 'within'} the {mx:.0%} guide)")
    return {"src": source.derived(*[r["src"] for r in rows], method="employer backlog over the projects") if rows else None,
            "rows": rows, "total_backlog": total, "top_share": top, "top_n": n_top,
            "top2_share": sum(b["backlog_share"] or 0 for b in rows[:2]), "concentration_max": mx, "concentrated": top > mx, "text": text}


# ------------------------------------------------------------------ the section


def analyse(proposal_id: str, as_of: dt.date | None = None) -> dict[str, Any]:
    projects = source.read("dd_project", proposal_id=proposal_id)
    cf = source.read("dd_project_cashflow", proposal_id=proposal_id)
    limits = source.read("dd_facility_limit", proposal_id=proposal_id)
    bureau = source.read("bureau_entity_report", proposal_id=proposal_id)
    st = status_table(projects, as_of, funded_by_project(limits))
    fin = [r for r in st["rows"] if r["financed"]]
    rem = sum(r["remaining_proceeds"] for r in fin)
    fo = funded_outstanding(limits) or sum(r["funded_outstanding"] for r in fin)
    flim = funded_limit(limits)
    lsrc = [source.src("dd_facility_limit", r, "outstanding_mn") for r in _funded_tops(limits)]
    cov = cover_ratio(rem, fo, [r["src"]["remaining_proceeds"] for r in fin] + lsrc)
    cfa = cash_flow(cf) if cf else None
    stress = delay_stress(cf, fo, rem, flim) if cf else None
    emp = employer_credit(st, bureau)
    lgs = lg_book(limits)
    return {"proposal_id": proposal_id, "product": PRODUCT, "has_data": bool(projects or cf),
            "answer": answer(st, cov, cfa, stress, emp),
            "status": st, "cover_ratio": cov, "cash_flow": cfa, "delay_stress": stress, "employer_credit": emp,
            "lgs": lgs, "funded_limit": flim,
            "src": source.derived(*lsrc, method="top-level funded limits") if lsrc else None}


def _when(days: int) -> str:
    return "in the base case" if days == 0 else f"at {days} days"


def answer(st: dict[str, Any], cov: dict[str, Any], cfa: dict[str, Any] | None, stress: dict[str, Any] | None,
           emp: dict[str, Any]) -> str:
    if not st["rows"] and not cfa:
        return "No financed projects or project cash flow are recorded for this deal."
    parts = []
    t = st["totals"]
    if t["projects"]:
        parts.append(f"{t['projects']} project{'s' if t['projects'] != 1 else ''} ({t['with_flags']} flagged"
                     + (f", {t['eot_not_formalised']} with an extension of time not formalised" if t["eot_not_formalised"] else "") + ")")
    if cov["ratio"] is not None:
        parts.append(f"cover ratio {cov['ratio']:.2f}x against {cov['min']:.2f}x")
    if cfa and cfa["peak_month"]:
        parts.append(f"peak project deficit {_m(cfa['peak_deficit'])} in {_mon(cfa['peak_month'])}")
    if stress:
        fb = stress["first_break"]
        worst = stress["rows"][-1]
        parts.append(f"at {worst['delay_days']} days' payment delay the peak deficit is {_m(worst['peak_deficit'])}"
                     + (f"; breaks {_when(fb['delay_days'])} ({fb['what']})" if fb else "; no break"))
    if emp["rows"] and emp["concentrated"]:
        parts.append(emp["text"][:1].lower() + emp["text"][1:] if emp["text"].startswith("The") else emp["text"])
    s = "; ".join(parts)
    return s[:1].upper() + s[1:] + "."
