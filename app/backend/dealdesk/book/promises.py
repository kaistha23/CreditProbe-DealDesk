"""Promises against delivery (PLAN_R12 §1.6, I8 part 3).

Two kinds of promise, both measured against the deposits domain (`dep_month`, registered):
  * routing undertakings on the book (deposits domain `dep_derived.routing_required_x`: "route n x the limit
    through our accounts"), measured as the trailing-12-month credit turnover against n x the obligor's limits;
  * commitments written as approval conditions on Deal Desk deals (Session E's `dd_condition`, and any
    `dd_promise` rows already published): routing, deposit balances, payroll and cross-sell lines, measured
    against the same deposits data ("promised SAR 50m, delivered 12m").

The measured promises are published as `dd_promise`. Their realised share is what relationship RAROC uses in
place of the flat 90% when `relationship.committed_realisation_basis` is "actual" (see `realisation()`).
"""
from __future__ import annotations

import functools
import re
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk import params
from backend.dealdesk.book import sources

KINDS = ("routing", "deposits", "payroll", "cross_sell")


def _bp() -> dict[str, Any]:
    return params.rows("relationship")["book"]


@functools.lru_cache(maxsize=1)
def _deposits_12m() -> pd.DataFrame:
    m = sources.live("dep_month", ["book", "obligor_id", "month", "avg_balance_sar_mn", "credit_turnover_sar_mn", "payroll_flag",
                                   "payroll_sar_mn"])
    m = m[m.book == "corporate"]
    last = sorted(m.month.unique())[-12:]
    m = m[m.month.isin(last)]
    g = m.groupby("obligor_id").agg(turnover_12m=("credit_turnover_sar_mn", "sum"), avg_balance_12m=("avg_balance_sar_mn", "mean"),
                                    payroll_months=("payroll_flag", "sum"), payroll_12m=("payroll_sar_mn", "sum"))
    g["avg_balance_3m"] = m[m.month.isin(last[-3:])].groupby("obligor_id").avg_balance_sar_mn.mean()
    g["period"] = f"{last[0]}..{last[-1]}" if last else ""
    g["window_from"] = f"{last[0]}-01" if last else None
    g["window_to"] = pd.Period(last[-1]).end_time.date().isoformat() if last else None
    return g.reset_index()


def routing_promises(f: pd.DataFrame) -> pd.DataFrame:
    """Routing undertakings on the book, one row per obligor, measured on the trailing 12 months."""
    d = sources.live("dep_derived", ["book", "obligor_id", "routing_required_x", "routing_actual_x"])
    d = d[(d.book == "corporate") & (d.routing_required_x > 0)]
    lim = f.groupby("borrower_id").agg(limit_sar_mn=("limit_sar_mn", "sum"), months_elapsed=("months_elapsed", "max"),
                                       borrower_name=("borrower_name", "first")).reset_index()
    t = d.merge(lim, left_on="obligor_id", right_on="borrower_id", how="inner").merge(_deposits_12m(), on="obligor_id", how="left")
    t["promised_value"] = t.routing_required_x * t.limit_sar_mn
    t["measured_value"] = t.turnover_12m.fillna(0.0)
    t["realisation"] = (t.measured_value / t.promised_value.where(t.promised_value > 0)).fillna(0.0)
    t["due"] = t.months_elapsed >= 12
    t["kind"] = "routing"
    t["promise_id"] = "PR-RT-" + t.obligor_id
    t["description"] = ("Route " + t.routing_required_x.map(lambda x: f"{x:.1f}") + "x the limits through our accounts (SAR "
                        + t.promised_value.map(lambda x: f"{x:,.0f}") + "m a year)")
    t["unit"] = "SAR m credit turnover, 12 months"
    t["source"] = "deposits.dep_derived (undertaking) and deposits.dep_month (delivery)"
    t["measure_relation"] = "deposits.dep_month"
    t["proposal_id"] = None
    t["condition_id"] = None
    t["facility_id"] = None
    return t[["promise_id", "kind", "obligor_id", "borrower_name", "facility_id", "proposal_id", "condition_id", "description",
              "promised_value", "measured_value", "realisation", "unit", "due", "period", "source", "routing_required_x", "routing_actual_x",
              "window_from", "window_to", "measure_relation"]]


_NUM = re.compile(r"(?:SAR|AED|USD)\s*([\d.,]+)\s*(m|mn|million|bn)?|([\d.]+)\s*x\b", re.I)


def _kind_of(text: str) -> str | None:
    t = text.lower()
    if "rout" in t or "turnover" in t:
        return "routing"
    if "payroll" in t or "salar" in t:
        return "payroll"
    if "deposit" in t or "balance" in t:
        return "deposits"
    if any(w in t for w in ("cross-sell", "cross sell", "fx", "trade", "cash management")):
        return "cross_sell"
    return None


def _target(text: str) -> tuple[float | None, str]:
    m = _NUM.search(text or "")
    if not m:
        return None, ""
    if m.group(3):
        return float(m.group(3)), "x"
    v = float(m.group(1).replace(",", ""))
    return (v * 1000 if (m.group(2) or "").lower() == "bn" else v), "SAR m"


#: dd_condition kinds that are commitments to measure (others are covenants, CPs, reporting, security)
PROMISE_CONDITION_KINDS = ("routing", "undertaking")
_STATUS_IN = {"met": "Met", "partly_met": "Partly met", "unmet": "Unmet", "open": "Not due"}
_STATUS_OUT = {v: k for k, v in _STATUS_IN.items()} | {"Not measured": "open"}


@functools.lru_cache(maxsize=4)
def _conduct_raw(_ver: str) -> pd.DataFrame:
    try:
        return sources.dd("dd_account_conduct")
    except sources.DataPending:
        return pd.DataFrame(columns=["obligor_id", "month"])


def _in_window(ob: str, wf: Any, wt: Any, ver: str) -> pd.DataFrame | None:
    """The demo obligor's conduct months inside the promise's own measurement window, or None."""
    if not wf or not wt:
        return None
    c = _conduct_raw(ver)
    if not len(c):
        return None
    c = c[(c.obligor_id == ob) & (c.month >= str(wf)[:7]) & (c.month <= str(wt)[:7])]
    return c if len(c) else None


@functools.lru_cache(maxsize=4)
def _conduct_12m(_ver: str) -> pd.DataFrame:
    """Account conduct of the R12 demo obligors (not in the Saudi book): Session E's dd_account_conduct."""
    try:
        c = sources.dd("dd_account_conduct")
    except sources.DataPending:
        return pd.DataFrame(columns=["obligor_id"])
    if not len(c):
        return pd.DataFrame(columns=["obligor_id"])
    last = sorted(c.month.dropna().unique())[-12:]
    c = c[c.month.isin(last)]
    g = c.groupby("obligor_id").agg(turnover_12m=("credit_turnover_mn", "sum"), avg_balance_12m=("avg_balance_mn", "mean"),
                                    routed_12m=("routed_business_mn", "sum"), limits=("limits_mn", "max"))
    g["avg_balance_3m"] = c[c.month.isin(last[-3:])].groupby("obligor_id").avg_balance_mn.mean()
    g["period"] = f"{last[0]}..{last[-1]}" if last else ""
    g["window_from"] = f"{last[0]}-01" if last else None
    g["window_to"] = (pd.Period(last[-1]).end_time.date().isoformat() if last else None)
    return g.reset_index()


def _deal_obligors(pending: list[str]) -> dict[str, str]:
    d = sources.dd_or_empty("dd_deal", pending)
    if not len(d) or "obligor_id" not in d.columns:
        return {}
    return dict(zip(d.proposal_id, d.obligor_id))


def condition_promises(f: pd.DataFrame, pending: list[str]) -> pd.DataFrame:
    """Commitments from approved deals: the published dd_promise rows, plus routing and undertaking conditions
    (dd_condition) not yet carried as a promise; each measured again on the deposits data."""
    rows: list[dict[str, Any]] = []
    obl = _deal_obligors(pending)
    pub = sources.dd_or_empty("dd_promise", pending)
    have = set()
    if len(pub) and "promise_id" in pub.columns:
        pub = pub[~pub.promise_id.astype(str).str.startswith("PR-RT-")]
        for r in pub.to_dict("records"):
            have.add((r.get("proposal_id"), r.get("kind")))
            mult = r.get("multiple_of_limit")
            rows.append({"promise_id": r["promise_id"], "kind": r.get("kind"), "obligor_id": r.get("obligor_id") or obl.get(r.get("proposal_id")),
                         "proposal_id": r.get("proposal_id"), "condition_id": None, "description": r.get("text"),
                         "promised_value": mult if (mult == mult and mult is not None and not (r.get("promised_mn") == r.get("promised_mn")
                                                                                              and r.get("promised_mn") is not None)) else r.get("promised_mn"),
                         "unit": "x" if (mult == mult and mult is not None and not (r.get("promised_mn") == r.get("promised_mn")
                                                                                    and r.get("promised_mn") is not None)) else "SAR m",
                         "promised_mn": r.get("promised_mn"), "multiple_of_limit": mult, "committee_ref": r.get("committee_ref"),
                         "published_delivered_mn": r.get("delivered_mn"), "published_status": r.get("status"),
                         "due_date": r.get("window_to"), "window_from": r.get("window_from"), "window_to": r.get("window_to"),
                         "source": "deal_desk.dd_promise"})
    cond = sources.dd_or_empty("dd_condition", pending)
    if len(cond) and "kind" in cond.columns:
        for r in cond[cond.kind.isin(PROMISE_CONDITION_KINDS)].to_dict("records"):
            text = str(r.get("text") or "")
            kind = "routing" if r.get("kind") == "routing" else _kind_of(text)
            if not kind or (r.get("proposal_id"), kind) in have:
                continue
            metric = str(r.get("trigger_metric") or "")
            th = r.get("trigger_threshold")
            if th is not None and th == th:
                val, unit = float(th), ("x" if "multiple" in metric or metric.endswith("_x") else "SAR m")
            else:
                val, unit = _target(text)
            rows.append({"promise_id": f"PR-{r['condition_id']}", "kind": kind, "obligor_id": obl.get(r.get("proposal_id")),
                         "proposal_id": r.get("proposal_id"), "condition_id": r.get("condition_id"), "description": text,
                         "promised_value": val, "unit": unit, "due_date": r.get("due_date"), "source": "deal_desk.dd_condition"})
    if not rows:
        return pd.DataFrame(columns=["promise_id"])
    t = pd.DataFrame(rows)
    dep = _deposits_12m().set_index("obligor_id")
    con = _conduct_12m(sources.version("dd_account_conduct")).set_index("obligor_id")
    lim = f.groupby("borrower_id").limit_sar_mn.sum()

    def measure(r: pd.Series) -> tuple[Any, Any, str, str]:
        ob = r.get("obligor_id")
        pv = r.get("promised_value")
        if ob in dep.index:
            d, rel, base, turnover, routed = dep.loc[ob], "deposits.dep_month", lim.get(ob, np.nan), "turnover_12m", "turnover_12m"
        elif ob in con.index:
            d, rel, base, turnover, routed = con.loc[ob], "deal_desk.dd_account_conduct", con.loc[ob].limits, "turnover_12m", "routed_12m"
            w = _in_window(ob, r.get("window_from"), r.get("window_to"), sources.version("dd_account_conduct"))
            if w is not None:  # the promise's own window (as approved), not the trailing 12 months
                d = pd.Series({"routed_12m": w.routed_business_mn.sum(), "turnover_12m": w.credit_turnover_mn.sum(),
                               "avg_balance_3m": w.sort_values("month").avg_balance_mn.tail(3).mean()})
        else:
            return None, pv, "", "no account history yet"
        if r.kind == "routing":
            promised = float(pv) * float(base) if r.get("unit") == "x" and pv is not None and base == base else pv
            return d[routed], promised, rel, "business routed, 12 months"
        if r.kind == "deposits":
            return d.avg_balance_3m, pv, rel, "average balance, 3 months"
        if r.kind == "payroll" and "payroll_12m" in d.index:
            return d.payroll_12m, pv, rel, "payroll through our accounts, 12 months"
        return None, pv, rel, "measured by the product system (not in Data Domains yet)"

    t["target_multiple"] = pd.to_numeric(t.promised_value.where(t.get("unit", pd.Series("", index=t.index)) == "x"), errors="coerce")
    m = t.apply(measure, axis=1, result_type="expand")
    t["measured_value"], t["promised_value"], t["measure_relation"], t["measure"] = m[0], m[1], m[2], m[3]
    t.loc[t.target_multiple.notna() & t.measure_relation.astype(str).ne(""), "unit"] = "SAR m"
    t["realisation"] = (pd.to_numeric(t.measured_value, errors="coerce") / pd.to_numeric(t.promised_value, errors="coerce")).replace(
        [np.inf, -np.inf], np.nan)
    ref = pd.Timestamp(f.ref_date.iloc[0]) if len(f) else pd.Timestamp.today()
    dd_ = pd.to_datetime(t.get("due_date"), errors="coerce")
    t["due"] = dd_.isna() | (dd_ <= ref)
    t["period"] = dep.period.iloc[0] if len(dep) else ""
    if "window_from" in t.columns:
        w = t.window_from.notna() & t.window_to.notna()
        t.loc[w, "period"] = t.loc[w, "window_from"].astype(str).str[:7] + ".." + t.loc[w, "window_to"].astype(str).str[:7]
    return t


def frame(f: pd.DataFrame, pending: list[str] | None = None) -> pd.DataFrame:
    pending = pending if pending is not None else []
    a = routing_promises(f)
    b = condition_promises(f, pending)
    t = pd.concat([a, b], ignore_index=True) if len(b) else a
    lo = float(_bp()["promise_unmet_below"])
    t["status"] = np.select([~t.due.astype(bool), t.realisation >= 1.0, t.realisation >= lo], ["Not due", "Met", "Partly met"], "Unmet")
    t.loc[t.realisation.isna() & t.due.astype(bool), "status"] = "Not measured"
    return t


def by_facility(f: pd.DataFrame) -> pd.DataFrame:
    """Per facility: the cross-sell income the promises carried at origination and what was realised (pro rata to limit)."""
    t_all = frame(f)
    bps = float(_bp()["routing_income_bps_of_turnover"]) / 1e4
    cond = t_all[~t_all.promise_id.astype(str).str.startswith("PR-RT-")]
    cond_unmet = set(cond.obligor_id[cond.status == "Unmet"].dropna()) | set(cond.facility_id[cond.status == "Unmet"].dropna())
    t = t_all[t_all.promise_id.astype(str).str.startswith("PR-RT-")].copy()
    t["inc_promised"] = t.promised_value * bps
    t["inc_realised"] = t.promised_value.clip(lower=0) * t.realisation.clip(0, 1) * bps
    t.loc[~t.due.astype(bool), "inc_realised"] = t.loc[~t.due.astype(bool), "inc_promised"]
    share = f.limit_sar_mn / f.groupby("borrower_id").limit_sar_mn.transform("sum")
    x = f[["facility_id", "borrower_id"]].assign(share=share).merge(
        t[["obligor_id", "inc_promised", "inc_realised", "realisation", "status", "measured_value"]], left_on="borrower_id", right_on="obligor_id", how="left")
    out = pd.DataFrame({"facility_id": x.facility_id, "xs_promised_sar_mn": x.inc_promised * x.share,
                        "xs_realised_sar_mn": x.inc_realised * x.share, "promise_realisation": x.realisation,
                        "promise_status": x.status})
    out["condition_promise_unmet"] = x.facility_id.isin(cond_unmet) | x.borrower_id.isin(cond_unmet)
    # business routed over the last 12 months as a multiple of the obligor's limits (named-trigger metric routing_multiple)
    ob_lim = f.groupby("borrower_id").limit_sar_mn.transform("sum")
    out["routing_multiple"] = (x.measured_value / ob_lim.where(ob_lim > 0).to_numpy()).to_numpy()
    out["promise_count"] = x.borrower_id.map(t_all.groupby("obligor_id").size()).fillna(0).astype(int)
    return out


def realisation(f: pd.DataFrame | None = None) -> dict[str, Any]:
    """The realised share of committed promises that are due and measured (capped at 100% per promise)."""
    if f is None:
        from backend.dealdesk.book import drift
        f = drift.universe()
    t = frame(f)
    t = t[t.due.astype(bool) & t.realisation.notna() & (pd.to_numeric(t.promised_value, errors="coerce") > 0)]
    if not len(t):
        return {"share": None, "promises": 0}
    pv = pd.to_numeric(t.promised_value)
    share = float((pv * t.realisation.clip(0, 1)).sum() / pv.sum())
    return {"share": share, "promises": int(len(t)), "by_kind": {k: float((pv[t.kind == k] * t.realisation[t.kind == k].clip(0, 1)).sum()
                                                                        / pv[t.kind == k].sum()) for k in t.kind.unique()}}


@functools.lru_cache(maxsize=1)
def _actual_share() -> tuple[float | None, int]:
    r = realisation()
    return r["share"], r["promises"]


def committed_realisation(rel: dict[str, Any]) -> float:
    """Relationship RAROC's realisation of committed cross-sell: flat (the parameter) or actual (behind a parameter)."""
    flat = float(rel["committed_realisation"])
    if rel.get("committed_realisation_basis", "flat") != "actual":
        return flat
    try:
        share, n = _actual_share()
    except Exception:  # noqa: BLE001 -- the Book's data not readable: keep the approved flat value
        return flat
    if share is None or n < int(rel.get("actual_min_promises", 5)):
        return flat
    return share


def publish_rows(t: pd.DataFrame) -> list[dict[str, Any]]:
    """The dd_promise publication (contract columns): promised and delivered in SAR m a year, delivered %, status.
    `promised_value` is already in SAR m after measuring (a multiple of the limits is converted); the multiple is kept."""
    out = []
    for r in t.replace({np.nan: None}).to_dict("records"):
        promised = r.get("promised_value")
        mult = r.get("routing_required_x")
        if mult is None:
            mult = r.get("multiple_of_limit")
        if mult is None and r.get("unit") == "x":
            mult = r.get("target_multiple")
        out.append({"promise_id": r["promise_id"], "proposal_id": r.get("proposal_id"), "obligor_id": r.get("obligor_id"),
                    "kind": r.get("kind"), "text": r.get("description"),
                    "promised_mn": float(promised) if promised is not None else None,
                    "multiple_of_limit": float(mult) if mult is not None else None,
                    "delivered_mn": float(r["measured_value"]) if r.get("measured_value") is not None else None,
                    "delivered_pct": float(r["realisation"]) * 100 if r.get("realisation") is not None else None,
                    "window_from": r.get("window_from"), "window_to": r.get("window_to"),
                    "measure_relation": r.get("measure_relation") or ("deposits.dep_month" if str(r["promise_id"]).startswith("PR-RT-") else None),
                    "status": _STATUS_OUT.get(r.get("status"), "open"), "committee_ref": r.get("committee_ref")})
    return out


def display_rows(t: pd.DataFrame) -> list[dict[str, Any]]:
    """Promises for the screen: promised and delivered in their unit, delivered share, status, source relation."""
    cols = ["promise_id", "kind", "obligor_id", "facility_id", "proposal_id", "condition_id", "description", "promised_value",
            "measured_value", "realisation", "unit", "status", "period", "source", "measure_relation"]
    return t.reindex(columns=cols).replace({np.nan: None}).to_dict("records")
