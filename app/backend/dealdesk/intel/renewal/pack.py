"""The annual review, prepared automatically for every renewal due in the window (R14 backlog #5).

For each facility the Book says is due for renewal or review in the next N days (default 90), refresh:
  financials (cockpit.corp_borrower_quarter, latest quarter vs a year earlier), conduct (deposits.dep_month), bureau
  (bureau.bureau_corp_quarter), conditions status (dd_condition via the Book), covenants (ews.corp_covenant via the Book),
  RAROC drift (the Book's drift), stress tier (dd_monitoring_plan) and review findings (dd_review_finding),
then classify clean vs exception with `criteria.CRITERIA`.

The Book frame (backend.dealdesk.book.core) is the single source of the facility, renewal date and Book signals; this module
adds the borrower refresh and the classification and never recomputes what the Book already holds.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk.book import core, sources as book_sources
from backend.dealdesk.intel.renewal import criteria
from backend.intel.calls import reads, signals

WINDOW_DAYS = 90


def _findings(pending: list[str]) -> pd.Series:
    """Open high/critical review findings per deal (dd_review_finding)."""
    t = book_sources.dd_or_empty("dd_review_finding", pending)
    if not len(t) or "proposal_id" not in t.columns:
        return pd.Series(dtype=float)
    sev = t.severity.astype(str).str.lower()
    st = t.status.astype(str).str.lower() if "status" in t.columns else pd.Series("open", index=t.index)
    m = sev.isin(["high", "critical"]) & ~st.isin(["resolved", "closed", "waived"])
    return t[m].groupby("proposal_id").size().astype(float)


@functools.lru_cache(maxsize=4)
def _prepare_cached(ref: str | None, days: int, ver: str) -> tuple[pd.DataFrame, tuple[str, ...]]:
    f, pending = core.frame(ref)
    pending = list(pending)
    refd = pd.Timestamp(f.ref_date.iloc[0]) if len(f) else pd.Timestamp.today()
    to_ren = (pd.to_datetime(f.renewal_date, errors="coerce") - refd).dt.days
    t = f[to_ren.between(0, days) & ~f.defaulted.astype(bool)].copy()
    t["days_to_renewal"] = to_ren[t.index]
    s = signals.borrower_signals()
    t = t.join(s, on="borrower_id", rsuffix="_sig")
    t["ews_severe"] = t.ews_band.astype(str).str.lower().isin(["high", "critical"]).astype(float)
    wl = pd.to_numeric(t.get("watchlist_flag"), errors="coerce").fillna(0)
    rs = pd.to_numeric(t.get("restructured_flag"), errors="coerce").fillna(0)
    t["watch_or_restructured"] = ((wl > 0) | (rs > 0)).astype(float)
    t["promise_unmet"] = t.flag_promise_unmet.astype(float)
    t["raroc_gap_pp"] = (t.raroc_now - t.hurdle) * 100.0
    t["tier_high"] = (t.tier == "High").astype(float)
    t["trigger_flag"] = t.flag_stress_driver.astype(float)
    fd = _findings(pending)
    t["findings_high_open"] = t.proposal_id.map(fd).fillna(0.0) if len(fd) else 0.0
    fired: list[list[str]] = []
    unknown: list[list[str]] = []
    for _, r in t.iterrows():
        fr, un = [], []
        for c in criteria.CRITERIA:
            v = r.get(c["column"])
            if v is None or (isinstance(v, float) and v != v):
                un.append(c["id"])
            elif criteria.fires(c, v):
                fr.append(c["id"])
        fired.append(fr)
        unknown.append(un)
    t["fired"] = fired
    t["unknown"] = unknown
    t["credit_fired"] = t.fired.map(lambda x: [i for i in x if i in criteria.CREDIT])
    t["commercial_fired"] = t.fired.map(lambda x: [i for i in x if i in criteria.COMMERCIAL])
    t["n_fired"] = t.credit_fired.map(len)
    t["classification"] = np.where(t.n_fired > 0, "exception", "clean")
    return t, tuple(pending)


def prepare(ref: str | None = None, days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, list[str]]:
    t, p = _prepare_cached(ref, int(days), core.data_version())
    return t, list(p)


def clear() -> None:
    _prepare_cached.cache_clear()
    signals.clear()


# ------------------------------------------------------------------ one facility's review, every number with its source

def _q(r: pd.Series) -> str:
    return str(r.get("as_of_quarter") or "")


def review(r: pd.Series) -> dict[str, Any]:
    """The prepared annual review for one facility: sections of sourced numbers + the criteria result."""
    fid, bid = r.facility_id, r.borrower_id
    q = _q(r)
    E = {"facility_id": fid, "reporting_quarter": q}
    B = {"borrower_id": bid}
    fq, fqp = r.get("fin_quarter"), r.get("fin_quarter_prev")
    bq = r.get("bureau_quarter")
    cm = r.get("conduct_months")
    S = reads.src
    n = reads.num
    fin = {
        "revenue_sar_mn": n(r.get("revenue_sar_mn"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "revenue_sar_mn", fq), "SAR m"),
        "ebitda_sar_mn": n(r.get("ebitda_sar_mn"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "ebitda_sar_mn", fq), "SAR m"),
        "ebitda_prev_sar_mn": n(r.get("ebitda_sar_mn_prev"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fqp}, "ebitda_sar_mn", fqp), "SAR m"),
        "leverage_x": n(r.get("leverage_x"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "leverage_x", fq), "x"),
        "leverage_prev_x": n(r.get("leverage_x_prev"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fqp}, "leverage_x", fqp), "x"),
        "dscr_x": n(r.get("dscr_x"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "dscr_x", fq), "x"),
        "interest_cover_x": n(r.get("interest_cover_x"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "interest_cover_x", fq), "x"),
        "current_ratio_x": n(r.get("current_ratio_x"), S("cockpit", "corp_borrower_quarter", {**B, "reporting_quarter": fq}, "current_ratio_x", fq), "x"),
    }
    fin["ebitda_yoy_pct"] = reads.computed(r.get("ebitda_yoy_pct"), "ebitda / ebitda a year earlier − 1", [fin["ebitda_sar_mn"], fin["ebitda_prev_sar_mn"]], "%")
    fin["leverage_change_x"] = reads.computed(r.get("leverage_change_x"), "leverage − leverage a year earlier", [fin["leverage_x"], fin["leverage_prev_x"]], "x")
    con = {
        "inflow_3m_avg_sar_mn": n(r.get("inflow_3m_avg_sar_mn"), S("deposits", "dep_month", {"obligor_id": bid}, "credit_turnover_sar_mn", cm, "mean of the last 3 months"), "SAR m"),
        "inflow_prior6_avg_sar_mn": n(r.get("inflow_prior6_avg_sar_mn"), S("deposits", "dep_month", {"obligor_id": bid}, "credit_turnover_sar_mn", cm, "mean of the prior 6 months"), "SAR m"),
        "cheques_returned_3m": n(r.get("cheques_returned_3m"), S("deposits", "dep_month", {"obligor_id": bid}, "cheques_returned_count", cm, "sum, last 3 months"), "count"),
        "payroll_missed_3m": n(r.get("payroll_missed_3m"), S("deposits", "dep_month", {"obligor_id": bid}, "payroll_flag", cm, "months without payroll, payroll customers"), "months"),
        "utilisation_pct": n(r.get("utilisation_pct"), S("ews", "corp_exposure", E, "utilisation_pct", q), "%"),
        "dpd_days": n(r.get("dpd_days"), S("ews", "corp_exposure", E, "dpd_days", q), "days"),
    }
    con["inflow_change_pct"] = reads.computed(r.get("inflow_change_pct"), "last-3-month mean inflow / prior-6-month mean − 1",
                                              [con["inflow_3m_avg_sar_mn"], con["inflow_prior6_avg_sar_mn"]], "%")
    bur = {
        "external_exposure_sar_mn": n(r.get("bureau_exposure_sar_mn"), S("bureau", "bureau_corp_quarter", {**B, "reporting_quarter": bq}, "external_exposure_sar_mn", bq), "SAR m"),
        "external_exposure_change_pct": n(r.get("bureau_exposure_change_pct"), S("bureau", "bureau_corp_quarter", B, "external_exposure_sar_mn", bq, "quarter on quarter change"), "%"),
        "external_dpd_days": n(r.get("bureau_dpd_days"), S("bureau", "bureau_corp_quarter", {**B, "reporting_quarter": bq}, "external_dpd_days", bq), "days"),
        "external_default_flag": n(r.get("bureau_default"), S("bureau", "bureau_corp_quarter", {**B, "reporting_quarter": bq}, "external_default_flag", bq)),
        "enquiries_q": n(r.get("bureau_enquiries"), S("bureau", "bureau_corp_quarter", {**B, "reporting_quarter": bq}, "enquiries_q", bq), "count"),
    }
    cov = {
        "covenants": n(r.get("covenants"), S("ews", "corp_covenant", {"facility_id": fid}, "covenant_id", r.get("covenant_quarter"), "count"), "count"),
        "covenants_breached": n(r.get("covenants_breached"), S("ews", "corp_covenant", {"facility_id": fid}, "breach_flag", r.get("covenant_quarter"), "sum"), "count"),
        "min_headroom_pct": n(r.get("covenant_min_headroom_pct"), S("ews", "corp_covenant", {"facility_id": fid}, "headroom_pct", r.get("covenant_quarter"), "min"), "%"),
        "conditions_open": n(r.get("conditions_open"), S("deal_desk", "dd_condition", {"proposal_id": r.get("proposal_id")}, "status", None, "count open"), "count"),
        "conditions_overdue": n(r.get("conditions_overdue"), S("deal_desk", "dd_condition", {"proposal_id": r.get("proposal_id")}, "due_date/status", None, "count overdue or not complied"), "count"),
    }
    raroc_src = (S("deal_desk", "dd_raroc_drift", {"proposal_id": r.get("deal_id")}, "raroc_now_pct") if r.get("source") == "deal_desk"
                 else S("computed", "book_drift", {"facility_id": fid}, "raroc_now", q, "Book drift: origination RAROC moved by PD, LGD, funding, fees, utilisation, cross-sell"))
    risk = {
        "stage": n(r.get("stage"), S("ews", "corp_exposure", E, "stage", q)),
        "rating_now": n(r.get("rating_now"), S("ecl_runs", "ecl_facility", {"exposure_id": fid, "run_id": r.get("ecl_run")}, "rating", r.get("ecl_run"))),
        "rating_at_origination": n(r.get("orig_rating"), S("origination", "orig_facility", {"exposure_id": fid}, "orig_rating")),
        "notches_down": n(r.get("notches"), S("computed", "book", {"facility_id": fid}, "notches", q, "master-scale index now − at origination")),
        "ews_band": n(r.get("ews_band"), S("ews", "corp_exposure", E, "ews_band", q)),
        "ews_score": n(r.get("ews_score"), S("ews", "corp_exposure", E, "ews_score", q)),
        "raroc_now_pct": n((r.get("raroc_now") or np.nan) * 100 if r.get("raroc_now") is not None else None, raroc_src, "%"),
        "raroc_orig_pct": n((r.get("raroc_orig") or np.nan) * 100 if r.get("raroc_orig") is not None else None,
                            S("origination", "orig_facility", {"exposure_id": fid}, "orig_margin_pct", None, "origination RAROC"), "%"),
        "hurdle_pct": n((r.get("hurdle") or np.nan) * 100 if r.get("hurdle") is not None else None, S("deal_desk", "dd_parameter", {"table": "returns"}, "hurdle"), "%"),
        "tier": n(r.get("tier"), S("deal_desk", "dd_monitoring_plan", {"facility_ref": fid, "proposal_id": r.get("plan_proposal_id")}, "tier")),
        "findings_high_open": n(r.get("findings_high_open"), S("deal_desk", "dd_review_finding", {"proposal_id": r.get("proposal_id")}, "severity", None, "open high/critical"), "count"),
    }
    results = []
    for c in criteria.CRITERIA:
        v = r.get(c["column"])
        known = not (v is None or (isinstance(v, float) and v != v))
        results.append({"id": c["id"], "label": c["label"], "op": c["op"], "threshold": c["threshold"], "value": reads.py(v) if known else None,
                        "fired": c["id"] in r.fired, "known": known, "reads": c["source"], "kind": c["kind"]})
    limits = []
    if r.get("tier") in (None, "Not set"):
        limits.append("No monitoring plan or stress run on file for this facility: the stress tier is not set, so the tier criteria cannot fire.")
    if not reads.py(r.get("proposal_id")) or str(r.get("proposal_id")) in ("nan", "<NA>", "None"):
        limits.append("No Deal Desk file: approval conditions and review findings are not recorded for this facility.")
    if any(c in r.unknown for c in ("ebitda_fall", "leverage_up", "dscr_low")):
        limits.append("Borrower financials are not in the corporate book for this obligor: the financial criteria were not tested.")
    if "cheques" in r.unknown:
        limits.append("No account conduct in the deposits domain for this obligor.")
    return reads.clean({
        "facility_id": fid, "borrower_id": bid, "borrower_name": r.borrower_name, "sector": r.get("sector"), "product": r.get("product_type"),
        "limit_sar_mn": n(r.get("limit_sar_mn"), S("ews", "corp_exposure", E, "limit_sar_mn", q), "SAR m"),
        "ead_sar_mn": n(r.get("ead_sar_mn"), S("ews", "corp_exposure", E, "ead_sar_mn", q), "SAR m"),
        "renewal_date": r.get("renewal_date"), "renewal_kind": r.get("renewal_kind"), "days_to_renewal": r.get("days_to_renewal"),
        "classification": r.classification, "fired": list(r.credit_fired), "commercial": list(r.commercial_fired), "proposal_id": r.get("proposal_id"), "as_of_quarter": q,
        "financials": fin, "conduct": con, "bureau": bur, "covenants_conditions": cov, "risk": risk, "criteria": results,
        "data_limits": limits,
    })
