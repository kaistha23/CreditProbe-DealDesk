"""PLAN_R12 Session P (I28): escrow / project-account financing.

  waterfall    the escrow's ordered release waterfall (`dd_escrow_account.waterfall_json`) with what each step has actually
               received from collections to date (`dd_escrow` monthly releases and retention)
  releases     the release rules tested month by month: construction releases within certified progress x construction
               cost; retention at the account's share of collections; developer surplus only while the cover ratio
               meets the minimum; no release beyond the balance
  cover        (escrow balance + instalments still to collect) / (loan outstanding + cost to complete), against the
               account's minimum (the contract's definition)
  collections  units sold, sales value, collected and receivable, monthly collections

Relations: dd_escrow_account (one row per account), dd_escrow (one row per account per month). SAR million.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.products import policy, source
from backend.dealdesk.products.project import _f, _m, _month_key, _pct

PRODUCT = "escrow"
ACC, MOV = "dd_escrow_account", "dd_escrow"
#: waterfall step -> the dd_escrow column that records what it received
_STEP_COL = (("construction", "release_construction_mn"), ("contractor", "release_construction_mn"),
             ("retention", "retention_added_mn"), ("debt", "release_debt_service_mn"), ("bank", "release_debt_service_mn"),
             ("finance", "release_debt_service_mn"), ("developer", "release_developer_mn"), ("surplus", "release_developer_mn"))


def _col_for(use: str) -> str | None:
    u = (use or "").lower()
    return next((c for k, c in _STEP_COL if k in u), None)


def cover(acc: dict[str, Any], last: dict[str, Any] | None) -> dict[str, Any]:
    mn = _f(acc.get("cover_ratio_min_x")) or float(policy.v("escrow.cover_ratio_min", PRODUCT))
    bal = _f((last or {}).get("closing_balance_mn"))
    loan = _f((last or {}).get("loan_outstanding_mn"))
    rec = _f(acc.get("receivable_mn"))
    prog = _pct((last or {}).get("construction_pct") if (last or {}).get("construction_pct") is not None else acc.get("construction_pct")) or 0.0
    ctc = _f(acc.get("construction_cost_mn")) * (1 - prog)
    den = loan + ctc
    ratio = (bal + rec) / den if den > 0 else None
    srcs = [source.src(ACC, acc, "receivable_mn"), source.src(ACC, acc, "construction_cost_mn")]
    if last:
        srcs += [source.src(MOV, last, "closing_balance_mn"), source.src(MOV, last, "loan_outstanding_mn")]
    return {"escrow_balance": bal, "receivable": rec, "to_collect": rec, "loan_outstanding": loan, "cost_to_complete": ctc,
            "ratio": ratio, "min": mn, "ok": ratio is None or ratio >= mn,
            "text": "No loan outstanding or cost to complete" if ratio is None else
            f"Escrow balance {_m(bal)} and instalments still to collect {_m(rec)} cover the loan outstanding {_m(loan)} and the "
            f"cost to complete {_m(ctc)} {ratio:.2f}x (minimum {mn:.2f}x)",
            "src": source.derived(*srcs, method="(escrow balance + receivable) / (loan outstanding + construction cost x (1 - progress))")}


def waterfall(acc: dict[str, Any], months: list[dict[str, Any]]) -> dict[str, Any]:
    steps = acc.get("waterfall_json") or []
    if isinstance(steps, str):
        import json
        try:
            steps = json.loads(steps)
        except ValueError:
            steps = []
    coll = sum(_f(m.get("collections_mn")) for m in months)
    tiers, used = [], set()
    for i, s in enumerate(sorted(steps, key=lambda x: _f(x.get("seq"), 99))):
        col = _col_for(str(s.get("use")))
        got = sum(_f(m.get(col)) for m in months) if col and col not in used else None
        if col:
            used.add(col)
        tiers.append({"priority": int(_f(s.get("seq"), i + 1)), "bucket": s.get("use"), "rule": s.get("rule"),
                      "allocated": got, "share": None,
                      "src": source.derived(*[source.src(MOV, m, col) for m in months], method=f"sum of {col}") if col and months
                      else source.src(ACC, acc, "waterfall_json")})
    paid = sum(t["allocated"] or 0.0 for t in tiers)
    for t in tiers:   # share of what the waterfall has paid out (releases may also be funded by loan drawdowns)
        t["share"] = (t["allocated"] / paid) if (t["allocated"] is not None and paid) else None
    bal = _f(months[-1].get("closing_balance_mn")) if months else 0.0
    return {"collections": coll, "paid_out": paid, "tiers": tiers, "unallocated": bal,
            "src": source.derived(*[source.src(MOV, m, "collections_mn") for m in months], method="collections to date")
            if months else source.src(ACC, acc)}


def releases(acc: dict[str, Any], months: list[dict[str, Any]], cover_min: float) -> dict[str, Any]:
    cost = _f(acc.get("construction_cost_mn"))
    ret = _pct(acc.get("retention_pct")) or float(policy.v("escrow.retention_pct", PRODUCT))
    rows, cum_cons = [], 0.0
    for m in months:
        cons, debt, dev = _f(m.get("release_construction_mn")), _f(m.get("release_debt_service_mn")), _f(m.get("release_developer_mn"))
        coll, kept = _f(m.get("collections_mn")), _f(m.get("retention_added_mn"))
        prog = _pct(m.get("construction_pct")) or 0.0
        cum_cons += cons
        breaches = []
        if cost and cons and cum_cons > prog * cost + 1e-6:
            breaches.append(f"construction released {_m(cum_cons)} to date against certified progress {prog:.0%} x cost {_m(cost)} = {_m(prog * cost)}")
        if coll and kept < coll * ret * 0.99 - 0.01:   # rounding of the published amounts is not a breach
            breaches.append(f"retention {_m(kept)} below {ret:.0%} of collections ({_m(coll * ret)})")
        if dev > 0:
            c = cover(acc, m)
            if c["ratio"] is not None and c["ratio"] < cover_min:
                breaches.append(f"developer surplus {_m(dev)} released at cover {c['ratio']:.2f}x (minimum {cover_min:.2f}x)")
        if _f(m.get("closing_balance_mn")) < -1e-6:
            breaches.append("escrow balance below zero")
        rows.append({"release_id": m.get("month"), "date": _month_key(m.get("month")), "purpose": "Monthly releases",
                     "amount": cons + debt + dev, "construction": cons, "debt_service": debt, "developer": dev, "collections": coll,
                     "retention": kept, "progress_pct": prog, "milestone_pct": None, "consultant_certified": None,
                     "compliant": not breaches, "breaches": breaches, "src": source.src(MOV, m)})
    rules = [str(acc.get("release_rules")).strip()] if acc.get("release_rules") else []
    rules += [f"Construction releases within certified progress x construction cost ({_m(cost)})",
              f"Retention of {ret:.0%} of each collection until handover",
              f"Developer surplus only while the cover ratio is at least {cover_min:.2f}x"]
    out = [r for r in rows if r["amount"] or r["breaches"]]
    return {"src": source.derived(*[r["src"] for r in out], method="sum of releases") if out else None,
            "rows": out, "released": sum(r["amount"] for r in out), "breaches": sum(1 for r in out if not r["compliant"]),
            "rules": rules}


def collections(acc: dict[str, Any], months: list[dict[str, Any]]) -> dict[str, Any]:
    units, sold = int(_f(acc.get("units_total"))), int(_f(acc.get("units_sold")))
    contracted, collected = _f(acc.get("sales_value_mn")), _f(acc.get("collected_mn"))
    series = [{"month": _month_key(m.get("month")), "collected": _f(m.get("collections_mn")), "due": None, "overdue": None,
               "units_sold_cum": m.get("units_sold_cum"), "src": source.src(MOV, m, "collections_mn")} for m in months]
    return {"src": source.src(ACC, acc, "sales_value_mn"), "units_total": units, "units_sold": sold,
            "sold_pct": sold / units if units else None, "sales_value_contracted": contracted, "collected_to_date": collected,
            "collected_pct": collected / contracted if contracted else None, "to_collect": _f(acc.get("receivable_mn")),
            "unsold_inventory_value": None, "series": series, "buyer_arrears": None, "collection_rate_last": None}


def analyse(proposal_id: str) -> dict[str, Any]:
    accs = source.read(ACC, proposal_id=proposal_id)
    if not accs:
        return {"proposal_id": proposal_id, "product": PRODUCT, "has_data": False, "answer": "No escrow account is recorded for this deal."}
    acc = accs[0]
    months = sorted(source.read(MOV, escrow_id=acc.get("escrow_id")), key=lambda m: _month_key(m.get("month")))
    last = months[-1] if months else None
    cov = cover(acc, last)
    col = collections(acc, months)
    wf = waterfall(acc, months)
    rl = releases(acc, months, cov["min"])
    prog = _pct(last.get("construction_pct") if last else acc.get("construction_pct"))
    ans = (f"{acc.get('project_name') or 'The project'}: {col['units_sold']} of {col['units_total']} units sold"
           + (f" ({col['sold_pct']:.0%})" if col["sold_pct"] is not None else "")
           + (f", {col['collected_pct']:.0%} of sales value collected" if col["collected_pct"] is not None else "")
           + (f", construction {prog:.0%} complete" if prog is not None else "")
           + (f"; cover ratio {cov['ratio']:.2f}x against {cov['min']:.2f}x" if cov["ratio"] is not None else "")
           + (f"; {rl['breaches']} month{'s' if rl['breaches'] != 1 else ''} with a release outside the rules" if rl["breaches"]
              else "; every release within the rules") + ".")
    return {"proposal_id": proposal_id, "product": PRODUCT, "has_data": True, "answer": ans,
            "account": {"escrow_id": acc.get("escrow_id"), "account_ref": acc.get("account_no"), "project_name": acc.get("project_name"),
                        "developer": acc.get("developer"), "escrow_agent": acc.get("escrow_agent"),
                        "construction_progress_pct": prog, "construction_cost": _f(acc.get("construction_cost_mn")),
                        "currency": "SAR", "src": source.src(ACC, acc)},
            "collections": col, "cover": cov, "waterfall": wf, "releases": rl}
