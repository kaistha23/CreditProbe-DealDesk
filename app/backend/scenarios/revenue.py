"""The revenue channel (R14 K12 (3); PLAN_R14 §m (4)): is the book's stress coming from falling borrower revenue?

Two measures per sector, read from registered relations (Data Domains), never from a side door:
  * account turnover: credit turnover (inflows) on the corporate borrowers' accounts, the last three months against the
    same three months a year earlier (`deposits.dep_month`, monthly, the bank's own account data);
  * reported revenue: the borrowers' revenue in the latest quarter against the same quarter a year earlier
    (`cockpit.corp_borrower_quarter`, the financials the rating rests on);
weighted by the sector's EAD in the latest quarter (`cockpit.corp_facility_quarter`).

The book's stress "comes from revenue" when the sectors whose account turnover fell at least FALL_PCT % hold at least
SHARE_PCT % of EAD. The sector shock offered is the sector's own measured turnover fall (mild), 1.5x it (moderate) and 2x
it (severe), capped at 60%; the multipliers are a labelled rule, the base is measured. When reported revenue rises while
turnover falls, the gap is said (reported financials lag the accounts, or overstate).

For a deal (Stress Lab, What-If on one borrower), `deal_line` reads the obligor's own conduct (`deal_desk.dd_account_conduct`)
and its statements (`deal_desk.dd_financials_detail`) when the deal has them, else its sector line.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

FALL_PCT = 10.0
SHARE_PCT = 15.0
MULT = {"mild": 1.0, "moderate": 1.5, "severe": 2.0}
CAP = 60.0
RELATIONS = ["deposits.dep_month", "cockpit.corp_borrower_quarter", "cockpit.corp_facility_quarter",
             "deal_desk.dd_account_conduct", "deal_desk.dd_financials_detail"]


def _path(domain: str, relation: str):
    from backend.data_builder import registry
    from backend.whatif_v5 import paths as wpaths
    return wpaths.V5 / registry.DOMAINS[domain]["relations"][relation]["path"]


@functools.lru_cache(maxsize=1)
def turnover() -> pd.DataFrame:
    d = pd.read_parquet(_path("deposits", "dep_month"), columns=["book", "obligor_id", "month", "credit_turnover_sar_mn"])
    return d[d["book"] == "corporate"].drop(columns="book")


def _months_back(last: str, n: int) -> list[str]:
    p = pd.Period(last, freq="M")
    return [str(p - k) for k in range(n - 1, -1, -1)]


@functools.lru_cache(maxsize=1)
def by_sector() -> dict[str, Any]:
    from backend.scenarios import data
    q = data.quarters()[-1]
    b = data.borrower()
    f = data.facility()
    sec = b[b["reporting_quarter"] == q][["borrower_id", "sector"]]
    ead = f[f["reporting_quarter"] == q].groupby("sector")["ead_sar_mn"].sum()
    t = turnover()
    last = str(t["month"].max())
    cur_m = _months_back(last, 3)
    prev_m = [str(pd.Period(m, freq="M") - 12) for m in cur_m]
    tt = t.merge(sec, left_on="obligor_id", right_on="borrower_id")
    cur = tt[tt["month"].isin(cur_m)].groupby("sector")["credit_turnover_sar_mn"].sum()
    prv = tt[tt["month"].isin(prev_m)].groupby("sector")["credit_turnover_sar_mn"].sum()
    to_yoy = (cur / prv - 1) * 100
    # borrower shares with turnover down >= FALL_PCT
    pb = tt[tt["month"].isin(cur_m)].groupby(["sector", "obligor_id"])["credit_turnover_sar_mn"].sum()
    pp = tt[tt["month"].isin(prev_m)].groupby(["sector", "obligor_id"])["credit_turnover_sar_mn"].sum()
    bg = ((pb / pp - 1) * 100).replace([np.inf, -np.inf], np.nan).dropna()
    share_down = bg.groupby(level=0).apply(lambda s: float((s <= -FALL_PCT).mean() * 100))
    y, n = q.split("Q")
    qp = f"{int(y) - 1}Q{n}"
    rv = b[b["reporting_quarter"].isin([q, qp]) & (b["revenue_sar_mn"] > 0)]
    rp = rv.pivot_table(index="borrower_id", columns="reporting_quarter", values="revenue_sar_mn", aggfunc="sum").dropna()
    rp = rp.join(sec.set_index("borrower_id"))
    rev_yoy = rp.groupby("sector").apply(lambda g: float((g[q].sum() / g[qp].sum() - 1) * 100))
    rows = []
    tot = float(ead.sum())
    for s in sorted(ead.index):
        tv = float(to_yoy.get(s, np.nan))
        rows.append({"sector": s, "ead_mn": round(float(ead[s]), 1), "ead_share_pct": round(float(ead[s]) / tot * 100, 2),
                     "turnover_yoy_pct": round(tv, 1), "borrowers_down_pct": round(float(share_down.get(s, np.nan)), 1),
                     "reported_revenue_yoy_pct": round(float(rev_yoy.get(s, np.nan)), 1),
                     "gap_pp": round(float(rev_yoy.get(s, np.nan)) - tv, 1)})
    rows.sort(key=lambda r: r["turnover_yoy_pct"])
    falling = [r for r in rows if r["turnover_yoy_pct"] <= -FALL_PCT]
    fshare = sum(r["ead_share_pct"] for r in falling)
    book_to = float((cur.sum() / prv.sum() - 1) * 100)
    book_rev = float((rp[q].sum() / rp[qp].sum() - 1) * 100)
    lead = fshare >= SHARE_PCT
    return {"window": {"turnover": f"{cur_m[0]}–{cur_m[-1]} against {prev_m[0]}–{prev_m[-1]}", "revenue": f"{q} against {qp}",
                       "ead_quarter": q, "last_month": last},
            "sectors": rows, "falling": [r["sector"] for r in falling], "falling_ead_share_pct": round(fshare, 1),
            "book_turnover_yoy_pct": round(book_to, 1), "book_reported_revenue_yoy_pct": round(book_rev, 1),
            "revenue_led": lead, "rule": (f"sectors whose account turnover fell at least {FALL_PCT:.0f}% hold at least "
                                          f"{SHARE_PCT:.0f}% of EAD"), "relations": RELATIONS}


def shocks(sector_row: dict[str, Any]) -> dict[str, float]:
    base = max(FALL_PCT, -float(sector_row["turnover_yoy_pct"]))
    return {sev: round(min(CAP, base * m), 1) for sev, m in MULT.items()}


def summary_line(r: dict[str, Any] | None = None) -> str:
    r = r or by_sector()
    if not r["falling"]:
        return (f"Revenue channel: account turnover is not falling by {FALL_PCT:.0f}% or more in any sector "
                f"({r['window']['turnover']}; book {r['book_turnover_yoy_pct']:+.1f}%), so revenue is not the lead stress.")
    top = [x for x in r["sectors"] if x["sector"] in r["falling"]][:4]
    secs = ", ".join(f"{x['sector']} {x['turnover_yoy_pct']:+.0f}%" for x in top)
    gap = (f" Reported revenue still shows {r['book_reported_revenue_yoy_pct']:+.1f}% ({r['window']['revenue']}): the "
           f"financials lag the accounts." if r["book_reported_revenue_yoy_pct"] > r["book_turnover_yoy_pct"] + 3 else "")
    verdict = ("so the book's stress comes from falling revenue" if r["revenue_led"]
               else "below the share that makes revenue the lead stress")
    return (f"Revenue channel: account turnover fell in {len(r['falling'])} sectors holding {r['falling_ead_share_pct']:.0f}% "
            f"of EAD ({secs}; {r['window']['turnover']}, deposits.dep_month), {verdict}.{gap}")


def sector_line(sector: str) -> dict[str, Any] | None:
    return next((x for x in by_sector()["sectors"] if x["sector"] == sector), None)


def deal_line(proposal_id: str, sector: str | None = None) -> dict[str, Any]:
    """The deal's own revenue evidence: its account conduct (credit turnover, last 6 months vs the same months a year
    earlier) and its statements (latest revenue vs the year before), else its sector line."""
    from backend.dealdesk.data import store
    out: dict[str, Any] = {"proposal_id": proposal_id, "sector": sector}
    try:
        c = pd.DataFrame(store.dd_read("dd_account_conduct", proposal_id=proposal_id))
    except Exception:  # noqa: BLE001 - a deal without conduct rows reads its sector
        c = pd.DataFrame()
    if len(c):
        last = sorted(c["month"].unique())[-6:]
        prev = [str(pd.Period(m, freq="M") - 12) for m in last]
        a = float(c[c["month"].isin(last)]["credit_turnover_mn"].sum())
        b = float(c[c["month"].isin(prev)]["credit_turnover_mn"].sum())
        if b > 0:
            out["turnover_yoy_pct"] = round((a / b - 1) * 100, 1)
            out["turnover_window"] = f"{last[0]}–{last[-1]}"
    try:
        f = pd.DataFrame(store.dd_read("dd_financials_detail", proposal_id=proposal_id))
    except Exception:  # noqa: BLE001
        f = pd.DataFrame()
    if len(f):
        a = f[f["period_kind"] == "audited"].sort_values("year")
        a = a.drop_duplicates("year", keep="last")
        if len(a) >= 2 and float(a.iloc[-2]["revenue_mn"] or 0) > 0:
            out["revenue_yoy_pct"] = round((float(a.iloc[-1]["revenue_mn"]) / float(a.iloc[-2]["revenue_mn"]) - 1) * 100, 1)
            out["revenue_window"] = f"{a.iloc[-1]['period_label']} against {a.iloc[-2]['period_label']}"
    if sector:
        out["sector_line"] = sector_line(sector)
    return out


def reset() -> None:
    turnover.cache_clear()
    by_sector.cache_clear()


def relation_rows(r: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """dd_revenue_channel: one row per sector (Data Domains, N3)."""
    r = r or by_sector()
    out = []
    for x in r["sectors"]:
        sh = shocks(x)
        out.append({"sector": x["sector"], "version": 1, "ead_mn": x["ead_mn"], "ead_share_pct": x["ead_share_pct"],
                    "turnover_yoy_pct": x["turnover_yoy_pct"], "borrowers_down_pct": x["borrowers_down_pct"],
                    "reported_revenue_yoy_pct": x["reported_revenue_yoy_pct"], "gap_pp": x["gap_pp"],
                    "falling_flag": int(x["sector"] in r["falling"]), "shock_mild_pct": sh["mild"],
                    "shock_moderate_pct": sh["moderate"], "shock_severe_pct": sh["severe"],
                    "window": f"turnover {r['window']['turnover']}; revenue {r['window']['revenue']}",
                    "revenue_led_flag": int(r["revenue_led"])})
    return out
