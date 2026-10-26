"""Borrower-level signals from the registered domains (R13 IB): financials refresh, bureau changes, account conduct.

Each function returns one row per borrower (index `borrower_id`) with the period it was read for, so every number can be traced
to (domain, relation, key, column, period). Shared by the renewal autopilot and "who to call today".
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from backend.intel.calls import reads

FIN_COLS = ["borrower_id", "reporting_quarter", "revenue_sar_mn", "ebitda_sar_mn", "leverage_x", "dscr_x", "interest_cover_x",
            "current_ratio_x", "total_debt_sar_mn", "operating_cash_flow_sar_mn"]


@functools.lru_cache(maxsize=1)
def financials() -> pd.DataFrame:
    """Latest quarter and the same quarter a year earlier (cockpit.corp_borrower_quarter)."""
    b = reads.read("cockpit", "corp_borrower_quarter", FIN_COLS)
    q = sorted(b.reporting_quarter.astype(str).unique())
    last, prev = q[-1], (q[-5] if len(q) >= 5 else q[0])
    a = b[b.reporting_quarter == last].set_index("borrower_id")
    p = b[b.reporting_quarter == prev].set_index("borrower_id")
    out = pd.DataFrame(index=a.index)
    out["fin_quarter"] = last
    out["fin_quarter_prev"] = prev
    for c in ("revenue_sar_mn", "ebitda_sar_mn", "leverage_x", "dscr_x", "interest_cover_x", "current_ratio_x", "total_debt_sar_mn"):
        out[c] = a[c].astype(float)
        out[c + "_prev"] = p[c].reindex(a.index).astype(float)
    eb_prev = out.ebitda_sar_mn_prev.where(out.ebitda_sar_mn_prev.abs() > 1e-9)
    out["ebitda_yoy_pct"] = (out.ebitda_sar_mn / eb_prev - 1.0) * 100.0
    out.loc[eb_prev <= 0, "ebitda_yoy_pct"] = np.nan  # a fall from a loss is not a percentage
    rv_prev = out.revenue_sar_mn_prev.where(out.revenue_sar_mn_prev > 0)
    out["revenue_yoy_pct"] = (out.revenue_sar_mn / rv_prev - 1.0) * 100.0
    out["leverage_change_x"] = out.leverage_x - out.leverage_x_prev
    return out


@functools.lru_cache(maxsize=1)
def bureau() -> pd.DataFrame:
    """Latest bureau quarter against the previous one (bureau.bureau_corp_quarter)."""
    b = reads.read("bureau", "bureau_corp_quarter", ["borrower_id", "reporting_quarter", "external_exposure_sar_mn", "external_dpd_days",
                                                      "external_default_flag", "enquiries_q"])
    q = sorted(b.reporting_quarter.astype(str).unique())
    last, prev = q[-1], q[-2]
    a = b[b.reporting_quarter == last].set_index("borrower_id")
    p = b[b.reporting_quarter == prev].set_index("borrower_id").reindex(a.index)
    out = pd.DataFrame(index=a.index)
    out["bureau_quarter"] = last
    out["bureau_quarter_prev"] = prev
    out["bureau_dpd_days"] = a.external_dpd_days.astype(float)
    out["bureau_dpd_days_prev"] = p.external_dpd_days.astype(float)
    out["bureau_default"] = a.external_default_flag.astype(float)
    out["bureau_default_prev"] = p.external_default_flag.astype(float)
    out["bureau_exposure_sar_mn"] = a.external_exposure_sar_mn.astype(float)
    out["bureau_exposure_prev_sar_mn"] = p.external_exposure_sar_mn.astype(float)
    prev_x = out.bureau_exposure_prev_sar_mn.where(out.bureau_exposure_prev_sar_mn > 0.01)
    out["bureau_exposure_change_pct"] = (out.bureau_exposure_sar_mn / prev_x - 1.0) * 100.0
    out["bureau_enquiries"] = a.enquiries_q.astype(float)
    out["bureau_enquiries_prev"] = p.enquiries_q.astype(float)
    return out


@functools.lru_cache(maxsize=1)
def conduct() -> pd.DataFrame:
    """Account conduct (deposits.dep_month, corporate book): last 3 months against the prior 6.

    * inflow change: mean monthly credit turnover, last 3 vs prior 6 months;
    * cheques returned in the last 3 months (count and SAR m);
    * payroll missed: months in the last 3 with no payroll run, for a payroll customer (payroll in at least 5 of the prior 6).
      The relation is monthly: a run paid a few days late inside the same month cannot be seen (stated as a data limit).
    """
    d = reads.read("deposits", "dep_month", ["book", "obligor_id", "month", "credit_turnover_sar_mn", "cheques_returned_count",
                                              "cheques_returned_sar_mn", "cheque_return_reason", "payroll_flag", "payroll_sar_mn", "excess_days"])
    d = d[d.book.astype(str) == "corporate"]
    months = sorted(d.month.astype(str).unique())
    last3, prior6 = months[-3:], months[-9:-3]
    r = d[d.month.isin(last3)].groupby("obligor_id")
    p = d[d.month.isin(prior6)].groupby("obligor_id")
    out = pd.DataFrame({"inflow_3m_avg_sar_mn": r.credit_turnover_sar_mn.mean(), "cheques_returned_3m": r.cheques_returned_count.sum(),
                        "cheques_returned_3m_sar_mn": r.cheques_returned_sar_mn.sum(), "payroll_runs_3m": r.payroll_flag.sum(),
                        "excess_days_3m": r.excess_days.sum()})
    out["inflow_prior6_avg_sar_mn"] = p.credit_turnover_sar_mn.mean()
    out["payroll_runs_prior6"] = p.payroll_flag.sum()
    base = out.inflow_prior6_avg_sar_mn.where(out.inflow_prior6_avg_sar_mn > 0.01)
    out["inflow_change_pct"] = (out.inflow_3m_avg_sar_mn / base - 1.0) * 100.0
    payroll_customer = out.payroll_runs_prior6.fillna(0) >= 5
    out["payroll_missed_3m"] = np.where(payroll_customer, 3 - out.payroll_runs_3m.fillna(0), 0)
    last_reason = (d[d.month.isin(last3) & (d.cheques_returned_count > 0)].sort_values("month").groupby("obligor_id").cheque_return_reason.last())
    out["cheque_reason"] = last_reason
    out["conduct_months"] = f"{last3[0]}..{last3[-1]} vs {prior6[0]}..{prior6[-1]}" if prior6 else ""
    out.index.name = "borrower_id"
    return out


def borrower_signals() -> pd.DataFrame:
    """financials + bureau + conduct, one row per borrower."""
    return financials().join(bureau(), how="outer").join(conduct(), how="outer")


def clear() -> None:
    financials.cache_clear()
    bureau.cache_clear()
    conduct.cache_clear()
