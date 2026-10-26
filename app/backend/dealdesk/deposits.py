"""Deposits in Deal Desk (PLAN_R9 Session E, E2).

For a proposal's obligor: the "Account behaviour" panel (24 months of balances, turnover, returned
cheques, payroll, overdraft use, top counterparties), the deposit value added to relationship RAROC
(average balances x (FTP credit - profit paid) + flow fees), and cash-flow debt capacity beside the
EBITDA-based capacity.

Source: the `deposits` domain of Session A (backend.r9_data.read, docs/STATUS_R9_DATA.md). Until that
domain is merged, a deterministic fixture with the same columns stands in (`source` says which).
New-to-bank obligors have no account history.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from backend.dealdesk import desk_params, engine, params, proposals

FLOW_FEE_RATE = 0.0005  # flow fees on credit turnover (cash management, transfers), a year
# R15 b (L8 (a)): behavioural haircut on the average balance (demo policy, labelled): only the stable 75% of the
# balances earns the FTP credit; the rest is treated as volatile money that may leave within the year.
BEHAVIOURAL_HAIRCUT = 0.25


def _months(n: int = 24) -> list[str]:
    out, y, m = [], 2026, 6
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _fixture(obligor_id: str, revenue: float) -> dict[str, Any]:
    seed = int(hashlib.sha256(obligor_id.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    base = max(revenue * rng.uniform(0.03, 0.08), 1.0)
    rows = []
    for i, mth in enumerate(_months()):
        avg = base * (1 + 0.15 * np.sin(i / 3.0) + rng.normal(0, 0.05))
        credit = revenue / 12 * rng.uniform(0.45, 0.75)
        ret = int(rng.poisson(0.4))
        rows.append({"month": mth, "avg_balance_sar_mn": round(float(avg), 3), "eom_balance_sar_mn": round(float(avg * rng.uniform(0.8, 1.2)), 3),
                     "min_balance_sar_mn": round(float(avg * 0.55), 3), "max_balance_sar_mn": round(float(avg * 1.5), 3),
                     "credit_turnover_sar_mn": round(float(credit), 3), "debit_turnover_sar_mn": round(float(credit * rng.uniform(0.92, 1.03)), 3),
                     "cheques_returned_count": ret, "cheques_returned_sar_mn": round(ret * float(rng.uniform(0.05, 0.4)), 3),
                     "payroll_sar_mn": round(float(revenue / 12 * 0.06), 3), "excess_days": int(rng.poisson(0.6)),
                     "peak_od_use_pct": round(float(rng.uniform(20, 85)), 1)})
    cps = [{"rank": k + 1, "counterparty_name": nm, "direction": d, "amount_sar_mn": round(float(revenue / 12 * w), 3), "category": cat}
           for k, (nm, d, w, cat) in enumerate([("Principal customer", "in", 0.18, "customer"), ("Government receivable", "in", 0.09, "government"),
                                                 ("Main supplier", "out", 0.16, "supplier"), ("Group company", "out", 0.05, "related"),
                                                 ("Second customer", "in", 0.07, "customer")])]
    return {"months": rows, "counterparties": cps, "profit_rate": 0.012, "source": "Account fixture (deposits domain pending)"}


def _domain(obligor_id: str) -> dict[str, Any] | None:
    try:
        from backend.r9_data import read as r9  # Session A's domain, when merged
    except Exception:  # noqa: BLE001 -- domain not merged yet
        return None
    try:
        m = r9.deposit_months("corporate", [obligor_id])
        if m is None or not len(m):
            return None
        m = m.sort_values("month")
        acc = r9.deposit_accounts("corporate", [obligor_id])
        cps = r9.deposit_counterparties("corporate", [obligor_id], None)
        last = cps[cps["month"] == cps["month"].max()].sort_values("rank") if len(cps) else cps
        rate = float(acc["profit_rate_pct"].fillna(0).mean()) / 100 if len(acc) else 0.0
        cols = ["month", "avg_balance_sar_mn", "eom_balance_sar_mn", "min_balance_sar_mn", "max_balance_sar_mn", "credit_turnover_sar_mn",
                "debit_turnover_sar_mn", "cheques_returned_count", "cheques_returned_sar_mn", "payroll_sar_mn", "excess_days", "peak_od_use_pct"]
        return {"months": m[[c for c in cols if c in m.columns]].to_dict("records"),
                "counterparties": last[["rank", "counterparty_name", "direction", "amount_sar_mn", "category"]].to_dict("records") if len(last) else [],
                "profit_rate": rate, "source": "Deposits domain (Data Domains: deposits)"}
    except Exception:  # noqa: BLE001 -- contract mismatch: fall back rather than break the deal page
        return None


def behaviour(proposal_id: str) -> dict[str, Any]:
    p = proposals.get(proposal_id)
    ob = p["obligor"]
    fin = engine.latest_actual(p)
    a = engine.analyse(p)
    m = a["metrics"]
    dp = desk_params.rows()
    ftp_credit = float(dp["deposit_ftp_credit"]["SAR"])
    zakat = float(params.rows("returns")["zakat_rate"])
    h = float(m["hurdle"])
    tenor = max(1, int(round(float(p["ask"].get("tenor_years", 3)))))
    annuity = sum(1 / (1 + h) ** t for t in range(1, tenor + 1))
    # Debt capacity: EBITDA-based (max leverage) and cash-flow based (EBITDA less debt service at the cover, as an annuity)
    ebitda_cap = max(0.0, float(dp["max_leverage"]) * float(fin["ebitda"]) - float(fin["total_debt"]))
    free = max(0.0, float(fin["ebitda"]) / float(dp["cash_flow_cover"]) - float(fin["debt_service"]))
    cash_cap = free * annuity
    out: dict[str, Any] = {"proposal_id": proposal_id, "obligor_id": ob["obligor_id"], "obligor": ob["name"],
                           "new_to_bank": not ob.get("existing"), "currency": "SAR",
                           "raroc": {"lifetime": m["lifetime_raroc"], "relationship": m["relationship_raroc"], "hurdle": h},
                           "debt_capacity": {"ebitda_based_sar_mn": ebitda_cap, "cash_flow_based_sar_mn": cash_cap,
                                             "ask_sar_mn": float(m["amount_sar_mn"]), "max_leverage": float(dp["max_leverage"]),
                                             "cash_flow_cover": float(dp["cash_flow_cover"])}}
    if not ob.get("existing"):
        out.update({"source": "New to bank: no account history", "months": [], "counterparties": [], "metrics": None,
                    "deposit_value_sar_mn": 0.0})
        out["raroc"]["relationship_with_deposits"] = m["relationship_raroc"]
        return out
    d = _domain(ob["obligor_id"]) or _fixture(ob["obligor_id"], float(fin["revenue"]))
    months = d["months"]
    last12 = months[-12:]
    avg_bal = float(np.mean([x["avg_balance_sar_mn"] for x in last12]))
    credit = float(np.sum([x["credit_turnover_sar_mn"] for x in last12]))
    returned = int(np.sum([x["cheques_returned_count"] for x in last12]))
    bal = np.array([x["avg_balance_sar_mn"] for x in months], dtype=float)
    stable_bal = avg_bal * (1.0 - BEHAVIOURAL_HAIRCUT)
    dep_value = stable_bal * max(ftp_credit - d["profit_rate"], 0.0) + credit * FLOW_FEE_RATE
    pv_dep = dep_value * (1 - zakat) * annuity
    rel_dep = float(m["relationship_raroc"]) + (pv_dep / float(m["pv_capital"]) if m["pv_capital"] else 0.0)
    out.update({"source": d["source"], "months": months, "counterparties": d["counterparties"],
                "metrics": {"avg_balance_12m_sar_mn": avg_bal, "credit_turnover_12m_sar_mn": credit,
                            "turnover_to_revenue": credit / float(fin["revenue"]) if fin["revenue"] else None,
                            "returned_cheques_12m": returned, "balance_volatility": float(bal.std() / bal.mean()) if bal.mean() else None,
                            "profit_rate": d["profit_rate"], "ftp_credit": ftp_credit,
                            "behavioural_haircut": BEHAVIOURAL_HAIRCUT, "stable_balance_sar_mn": stable_bal,
                            "flow_fee_rate": FLOW_FEE_RATE, "flow_fees_sar_mn": credit * FLOW_FEE_RATE,
                            "pv_deposit_value_sar_mn": pv_dep, "annuity": annuity, "tenor_years": tenor, "zakat_rate": zakat},
                "deposit_value_sar_mn": dep_value,
                "deposit_formula": (f"Deposit value a year = stable balance SAR {stable_bal:,.1f}m (average SAR {avg_bal:,.1f}m less the "
                                    f"{BEHAVIOURAL_HAIRCUT:.0%} behavioural haircut) × (FTP credit {ftp_credit:.2%} − profit paid "
                                    f"{d['profit_rate']:.2%}) + flow fees {FLOW_FEE_RATE:.2%} × credit turnover SAR {credit:,.0f}m = "
                                    f"SAR {dep_value:,.2f}m; present value over {tenor} years at the {h:.1%} hurdle after zakat = "
                                    f"SAR {pv_dep:,.2f}m, divided by the same capital as the deal.")})
    out["raroc"]["relationship_with_deposits"] = rel_dep
    return out
