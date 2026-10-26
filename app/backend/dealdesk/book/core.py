"""The Book: every approved facility with tier, drift, EWS, covenants and conditions, promises and renewal (PLAN_R12 §1.6).

Filters: going bad (the landing card), repricing list, promises unmet, tier High. Counts for U's landing cards.
Everything is read through `sources` (registered relations); decisions are published through E's publisher.
"""
from __future__ import annotations

import functools
import json
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk.book import drift, promises, repricing, sources

TIERS = ("High", "Medium", "Standard")
FILTERS = ("all", "going_bad", "repricing", "promises_unmet", "tier_high", "renewals_due", "conditions_due",
           "material_going_bad", "material_renewals")
#: R13 X (J9): defaults when a parameter version predates the materiality keys
MATERIALITY_DEFAULTS = {"materiality_floor_sar_mn": 50.0, "materiality_drift_below_hurdle": 0.02}


def _bp() -> dict[str, Any]:
    return drift.book_params()


# ------------------------------------------------------------------ monitoring plans (dd_monitoring_plan, D's relation via E)

def _col(t: pd.DataFrame, *names: str) -> str | None:
    return next((n for n in names if n in t.columns), None)


def _json(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


FREQ_MONTHS = {"quarterly": 3, "semi_annual": 6, "semi-annual": 6, "annual": 12}


def plans(pending: list[str], f: pd.DataFrame | None = None) -> pd.DataFrame:
    """The current monitoring plan per book facility (contract: dd_monitoring_plan; D's names tolerated).

    A plan names a facility (`facility_ref` / `facility_id`) or a whole deal (`ALL` or a limit id): a deal plan applies to
    every book facility of the deal's obligor. The current plan is the latest active version."""
    cols = ["facility_id", "tier", "plan_reason", "plan_set_by", "plan_set_on", "plan_version", "plan_drivers", "plan_review_months",
            "plan_proposal_id", "plan_triggers", "plan_id", "previous_tier"]
    t = sources.dd_or_empty("dd_monitoring_plan", pending)
    if not len(t) or "tier" not in t.columns:
        return pd.DataFrame(columns=cols)
    t = t.copy()
    if "status" in t.columns:
        t = t[t.status.fillna("active").astype(str).str.lower() != "superseded"]
    when = _col(t, "set_at", "set_on")
    ver = _col(t, "version", "rel_version")
    t = t.sort_values([c for c in (ver, when) if c], kind="stable")
    fref = t[_col(t, "facility_ref", "facility_id")] if _col(t, "facility_ref", "facility_id") else pd.Series(None, index=t.index)
    book_ids = set(f.facility_id) if f is not None else set()
    by_ob = f.groupby("borrower_id").facility_id.apply(list).to_dict() if f is not None else {}
    by_deal = (f[f.deal_id.notna()].groupby("deal_id").facility_id.apply(list).to_dict()
               if f is not None and "deal_id" in f.columns else {})
    rows = []
    for (_, r), ref in zip(t.iterrows(), fref):
        if isinstance(ref, str) and ref in book_ids:
            targets = [ref]
        elif r.get("proposal_id") in by_deal:
            targets = by_deal[r.get("proposal_id")]
        else:
            targets = by_ob.get(r.get("obligor_id"), [])
        trig = _json(r.get("named_triggers")) if "named_triggers" in t.columns else None
        if trig is None and "triggers" in t.columns:
            trig = _json(r.get("triggers"))
        freq = r.get("review_frequency")
        months = FREQ_MONTHS.get(str(freq).lower()) if isinstance(freq, str) else r.get("review_frequency_months")
        for fid in targets:
            rows.append({"facility_id": fid, "own": bool(isinstance(ref, str) and ref == fid), "tier": r.get("tier"), "plan_reason": r.get("reason"), "plan_set_by": r.get("set_by"),
                         "plan_set_on": str(r.get(when))[:10] if when and r.get(when) is not None else None,
                         "plan_version": r.get(ver) if ver else None, "plan_drivers": _json(r.get("drivers")),
                         "plan_review_months": months, "plan_proposal_id": r.get("proposal_id"), "plan_triggers": trig,
                         "plan_id": r.get("plan_id"), "previous_tier": r.get("previous_tier")})
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows)
    # a facility's own plan wins over a deal-wide one; otherwise the latest (rows are in publication order)
    out = out.sort_values("own", kind="stable")
    return out.groupby("facility_id").tail(1).drop(columns=["own"]).reset_index(drop=True)


#: named-trigger metrics the Book can test on a book facility (metric -> column, scale)
METRICS = {"utilisation_pct": ("utilisation_pct", 1.0), "ews_score": ("ews_score", 1.0), "dpd_days": ("dpd_days", 1.0),
           "rating_notches": ("notches", 1.0), "notches": ("notches", 1.0), "covenant_breaches": ("covenants_breached", 1.0),
           "pd_12m_pct": ("pd_pit_12m", 100.0), "routing_multiple": ("routing_multiple", 1.0), "raroc_pct": ("raroc_now", 100.0), "collateral_ltv_pct": ("collateral_ltv_pct", 1.0)}
_OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "=": lambda a, b: a == b}


def _driver_hit(f: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """A named trigger on the plan ({metric, operator, threshold, label}) breached by today's facility value."""
    hit = pd.Series(False, index=f.index)
    label = pd.Series(None, index=f.index, dtype=object)
    if "plan_triggers" not in f.columns:
        return hit, label
    for i, trig in enumerate(f.plan_triggers):
        if not isinstance(trig, list):
            continue
        for x in trig:
            if not isinstance(x, dict):
                continue
            m = METRICS.get(str(x.get("metric")))
            op = _OPS.get(str(x.get("operator") or x.get("op") or ">"))
            th = x.get("threshold")
            if not m or not op or th is None or m[0] not in f.columns:
                continue
            try:
                v = float(f[m[0]].iat[i]) * m[1]
                if op(v, float(th)):
                    hit.iat[i] = True
                    label.iat[i] = x.get("label") or f"{x.get('metric')} {x.get('operator') or x.get('op')} {th}"
                    break
            except (TypeError, ValueError):
                pass
    return hit, label


# ------------------------------------------------------------------ covenants and conditions

@functools.lru_cache(maxsize=1)
def covenants() -> pd.DataFrame:
    c = sources.live("ews_covenant", ["covenant_id", "facility_id", "reporting_quarter", "covenant_type", "threshold_value", "observed_value",
                                      "headroom_pct", "test_status", "breach_flag", "waiver_status", "consecutive_breaches"])
    q = c.reporting_quarter.max()
    c = c[c.reporting_quarter == q]
    g = c.groupby("facility_id").agg(covenants=("covenant_id", "count"), covenants_breached=("breach_flag", "sum"),
                                     covenant_min_headroom_pct=("headroom_pct", "min")).reset_index()
    g["covenant_quarter"] = q
    return g


def _next_quarter_end(ref: pd.Timestamp) -> str:
    return (ref + pd.offsets.QuarterEnd(1)).date().isoformat()


CLOSED = ("met", "closed", "satisfied", "waived", "done", "complied")


def conditions(pending: list[str], ref: pd.Timestamp) -> pd.DataFrame:
    """Open conditions per deal (dd_condition is keyed by deal; continuing covenants have no due date)."""
    t = sources.dd_or_empty("dd_condition", pending)
    if not len(t) or "proposal_id" not in t.columns:
        return pd.DataFrame(columns=["key", "conditions_open", "conditions_due", "conditions_overdue", "key_kind"])
    key = "proposal_id"
    st = t[_col(t, "status")].astype(str).str.lower() if _col(t, "status") else pd.Series("open", index=t.index)
    open_ = ~st.isin(list(CLOSED))
    due = pd.to_datetime(t[_col(t, "due_date", "due")], errors="coerce") if _col(t, "due_date", "due") else pd.Series(pd.NaT, index=t.index)
    month_end = ref + pd.offsets.MonthEnd(1)
    breached = st.isin(["breached", "not_complied"])
    t = t.assign(key=t[key], o=open_, d=open_ & ((due <= month_end) | breached), od=open_ & ((due < ref) | breached))
    g = t.groupby("key").agg(conditions_open=("o", "sum"), conditions_due=("d", "sum"), conditions_overdue=("od", "sum")).reset_index()
    g["key_kind"] = key
    return g


# ------------------------------------------------------------------ the Book frame

def _approved_deals(pending: list[str]) -> pd.DataFrame:
    """Deal Desk deals approved (dd_deal status / workflow state), with their obligor, so a book facility finds its deal file."""
    p = sources.dd_or_empty("dd_deal", pending)
    if not len(p) or "proposal_id" not in p.columns:
        return pd.DataFrame(columns=["proposal_id", "obligor_id"])
    st = p.get("status", pd.Series("", index=p.index)).astype(str).str.lower()
    wf = p.get("workflow_state", pd.Series("", index=p.index)).astype(str).str.lower()
    return p[st.str.contains("approv") | wf.str.contains("approv")]


def _txt(v: Any) -> str | None:
    return None if v is None or v is pd.NA or (isinstance(v, float) and v != v) or str(v) in ("", "<NA>", "nan", "None") else str(v)


#: dd_deal case types whose existing limits are on the book
BOOKED_CASES = ("renewal", "renewal_and_new", "additional", "amendment")


def deal_rows(pending: list[str], f: pd.DataFrame) -> pd.DataFrame:
    """Approved Deal Desk facilities outside the Saudi book release (the R12 demo deals' existing limits): one row per deal
    (its total existing limits), from dd_deal, dd_facility_limit and the published dd_raroc_drift."""
    d = sources.dd_or_empty("dd_deal", pending)
    if not len(d) or "existing_limits_mn" not in d.columns:
        return pd.DataFrame()
    book_ob = set(f.borrower_id)
    d = d[(pd.to_numeric(d.existing_limits_mn, errors="coerce") > 0) & ~d.obligor_id.isin(book_ob)
          & (d.case_type.isin(BOOKED_CASES) | d.status.astype(str).str.contains("approv"))]
    if not len(d):
        return pd.DataFrame()
    lim = sources.dd_or_empty("dd_facility_limit", pending)
    dr = sources.dd_or_empty("dd_raroc_drift", pending)
    if len(dr) and "proposal_id" in dr.columns:
        dr = dr[dr.proposal_id.isin(d.proposal_id) & ~dr.drift_id.astype(str).str.startswith("RD-")]  # the deal's own drift, not a Book echo
        dr = dr.drop_duplicates("proposal_id", keep="last").set_index("proposal_id")
    rows = []
    for r in d.to_dict("records"):
        r = {k: (None if (v is pd.NA or (isinstance(v, float) and v != v)) else v) for k, v in r.items()}
        pid = r["proposal_id"]
        top = lim[(lim.proposal_id == pid) & (lim.level == 0)] if len(lim) and "level" in lim.columns else pd.DataFrame()
        out_mn = float(top.outstanding_mn.iloc[0]) if len(top) and top.outstanding_mn.notna().iloc[0] else np.nan
        sector = None
        try:
            from backend.dealdesk.data import deals
            sector = deals.get(pid)["obligor"].get("sector")
        except Exception:  # noqa: BLE001
            pass
        x = dr.loc[pid] if len(dr) and pid in dr.index else None
        pc = (lambda k: float(x[k]) / 100 if x is not None and x[k] == x[k] and x[k] is not None else np.nan)
        row = {"facility_id": f"{pid}:L0", "borrower_id": r["obligor_id"], "borrower_name": r["obligor_name"], "sector": sector or "",
               "product_type": r.get("product") or "", "limit_sar_mn": float(r["existing_limits_mn"]),
               "ead_sar_mn": out_mn if out_mn == out_mn else float(r["existing_limits_mn"]),
               "drawn_sar_mn": out_mn, "orig_date": (_txt(x["origination_date"]) if x is not None else None) or r.get("account_opened_date"),
               "orig_rating": r.get("rating_existing") or None, "rating_now": r.get("rating_proposed") or None, "stage": 1,
               "pd_pit_12m": np.nan, "ews_band": "not scored", "ews_score": np.nan, "ews_reasons": "Not in the Early Warning release",
               "watch_status": None, "raroc_orig": pc("raroc_orig_pct"), "raroc_now": pc("raroc_now_pct"), "hurdle": pc("hurdle_pct"),
               "drift": pc("drift_pp"), "d_pd_migration": pc("attr_pd_pp"), "d_lgd": pc("attr_lgd_pp"), "d_funding": pc("attr_funding_pp"),
               "d_fees": pc("attr_fees_pp"), "d_utilisation": pc("attr_utilisation_pp"), "d_cross_sell": pc("attr_cross_sell_pp"),
               "renewal_date": (_txt(x["renewal_date"]) if x is not None else None) or r.get("review_date") or None,
               "deal_id": pid, "plan_proposal_id_seed": pid, "source": "deal_desk", "defaulted": False,
               "as_of_quarter": f.as_of_quarter.iloc[0] if len(f) else "", "ref_date": f.ref_date.iloc[0] if len(f) else "",
               "renewal_kind": "Annual review"}
        rows.append(row)
    t = pd.DataFrame(rows)
    g = drift.grades()
    idx = {x: i for i, x in enumerate(g)}
    t["notches"] = t.rating_now.map(idx) - t.orig_rating.map(idx)
    refd = pd.Timestamp(t.ref_date.iloc[0]) if len(t) and t.ref_date.iloc[0] else pd.Timestamp.today()
    t["months_to_renewal"] = ((pd.to_datetime(t.renewal_date, errors="coerce") - refd).dt.days / 30.4375).round(1)
    t["months_elapsed"] = ((refd - pd.to_datetime(t.orig_date, errors="coerce")).dt.days / 30.4375).round(1)
    t["above_orig"] = t.raroc_orig >= t.hurdle
    t["above_now"] = t.raroc_now >= t.hurdle
    comp = t[[f"d_{c}" for c in drift.COMPONENTS]]
    t["main_driver"] = [str(r.idxmin())[2:] if r.notna().any() else None for _, r in comp.astype(float).iterrows()]
    pr = promises.frame(f, pending)
    pr = pr[~pr.promise_id.astype(str).str.startswith("PR-RT-")]
    if len(pr) and "obligor_id" in pr.columns:
        st = pr.groupby("obligor_id").agg(promise_realisation=("realisation", "min"),
                                          promise_status=("status", lambda s: "Unmet" if (s == "Unmet").any() else s.iloc[0]))
        t = t.merge(st, left_on="borrower_id", right_index=True, how="left")
        t["condition_promise_unmet"] = t.promise_status == "Unmet"
        rt = pr[pr.kind == "routing"].groupby("obligor_id").measured_value.sum()
        t["routing_multiple"] = t.borrower_id.map(rt) / t.limit_sar_mn
    return t


@functools.lru_cache(maxsize=4)
def _frame_cached(ref: str | None, _ver: str) -> tuple[pd.DataFrame, tuple[str, ...]]:
    pending: list[str] = []
    f = drift.frame(ref).copy()
    f["source"] = "book"
    f["deal_id"] = None
    refd = pd.Timestamp(f.ref_date.iloc[0]) if len(f) else pd.Timestamp.today()
    dl = deal_rows(pending, f)
    if len(dl):
        f = pd.concat([f, dl.drop(columns=["plan_proposal_id_seed"])], ignore_index=True)
    pl = plans(pending, f)
    f = f.merge(pl, on="facility_id", how="left")
    f["tier_set"] = f.tier.notna()
    f["tier"] = f.tier.fillna("Not set")
    f = f.merge(covenants(), on="facility_id", how="left")
    f["covenants"] = f.covenants.fillna(0).astype(int)
    f["covenants_breached"] = f.covenants_breached.fillna(0).astype(int)
    f["covenant_next_test"] = _next_quarter_end(refd)
    cd = conditions(pending, refd)
    for c in ("conditions_open", "conditions_due", "conditions_overdue"):
        f[c] = 0
    appr = _approved_deals(pending)
    f["proposal_id"] = f.deal_id.where(f.deal_id.notna(), f.plan_proposal_id)
    if len(appr) and "obligor_id" in appr.columns:
        by_ob = appr.groupby("obligor_id").proposal_id.last()
        f["proposal_id"] = f.proposal_id.fillna(f.borrower_id.map(by_ob))
    if len(cd):
        m = f[["proposal_id"]].merge(cd.drop(columns=["key_kind"]), left_on="proposal_id", right_on="key", how="left")
        for c in ("conditions_open", "conditions_due", "conditions_overdue"):
            f[c] = m[c].fillna(0).astype(int).to_numpy()
    bp = _bp()
    lo, hi = bp["repricing_window_months"]
    bands = set(bp["ews_warning_bands"])
    live_ = ~f.defaulted
    f["flag_drift_below_hurdle"] = live_ & f.above_orig & ~f.above_now
    f["flag_downgrade"] = live_ & (f.notches >= int(bp["downgrade_notches"]))
    f["flag_ews"] = live_ & f.ews_band.isin(bands)
    hit, lab = _driver_hit(f)
    f["flag_stress_driver"] = live_ & hit
    f["trigger_hit"] = lab
    f["flag_promise_unmet"] = live_ & ((f.promise_status == "Unmet") | f.condition_promise_unmet.fillna(False).astype(bool))
    flags = ["flag_drift_below_hurdle", "flag_downgrade", "flag_ews", "flag_stress_driver", "flag_promise_unmet"]
    # going bad: a risk signal, or an approval-condition promise unmet (book routing undertakings alone sit on "promises unmet")
    f["going_bad"] = f[flags[:4]].any(axis=1) | (live_ & f.condition_promise_unmet.fillna(False).astype(bool))
    f["going_bad_score"] = f[flags].sum(axis=1)
    f["renewal_in_window"] = f.months_to_renewal.between(lo, hi)
    f["renewal_due"] = (pd.to_datetime(f.renewal_date, errors="coerce") - refd).dt.days.between(0, int(bp["renewals_due_days"]))
    rp = repricing.solve(f)
    f = pd.concat([f, rp], axis=1)
    dd_ = f.source == "deal_desk"
    if dd_.any():  # a Deal Desk deal: the optimiser's own reprice or restructure on its file
        for i in f.index[dd_ & (f.raroc_now < f.hurdle)]:
            o = repricing.optimiser_cached(str(f.at[i, "deal_id"]))
            f.at[i, "action"], f.at[i, "action_text"] = repricing.optimiser_action(o)
            if o and o.get("lifetime_raroc") is not None:
                f.at[i, "recoverable_raroc"] = max(0.0, min(float(o["lifetime_raroc"]), float(f.at[i, "hurdle"])) - float(f.at[i, "raroc_now"]))
    f["on_repricing_list"] = live_ & (f.raroc_now < f.hurdle) & f.renewal_in_window
    _materiality(f, bp)
    return f, tuple(pending)


def materiality(bp: dict[str, Any] | None = None) -> dict[str, float]:
    """The materiality floor (relationship EAD, SAR m) and the drift gap below hurdle that make a name material (J9)."""
    bp = bp if bp is not None else _bp()
    return {k: float(bp.get(k, v)) for k, v in MATERIALITY_DEFAULTS.items()}


def _materiality(f: pd.DataFrame, bp: dict[str, Any]) -> None:
    """R13 X (J9): the landing counters count material names, not the whole back book.

    Material going bad = live and (tier High, or relationship EAD at or above the floor and (Early Warning high or critical,
    or RAROC drifted below hurdle by at least the drift gap)). Material renewal = live, renewal or review in the window
    (renewals_due_days) and relationship EAD at or above the floor. Relationship EAD = the borrower's EAD over all facilities.
    """
    m = materiality(bp)
    live_ = ~f.defaulted
    f["relationship_ead_sar_mn"] = f.groupby("borrower_id").ead_sar_mn.transform("sum")
    above = f.relationship_ead_sar_mn >= m["materiality_floor_sar_mn"]
    gap = (f.hurdle - f.raroc_now) >= m["materiality_drift_below_hurdle"] - 1e-12
    f["material_drift"] = f.flag_drift_below_hurdle & gap
    f["material_going_bad"] = live_ & ((f.tier == "High") | (above & (f.flag_ews | f.material_drift)))
    f["material_renewal"] = live_ & above & f.renewal_due


def data_version() -> str:
    """Changes when a Deal Desk relation the Book reads is republished or a parameter table is edited."""
    from backend.dealdesk import params
    pv = ",".join(str(params.table(n).get("version")) for n in ("returns", "relationship", "market_bounds", "pd_migration"))
    return "|".join(sources.version(r) for r in ("dd_monitoring_plan", "dd_condition", "dd_promise", "dd_deal", "dd_account_conduct",
                                                  "dd_raroc_drift", "dd_facility_limit")) + "|" + pv


def frame(ref: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    f, pending = _frame_cached(ref, data_version())
    return f, list(pending)


def refresh() -> None:
    """Drop every Book cache that holds Deal Desk relation data (after a publish or a parameter edit)."""
    _frame_cached.cache_clear()
    drift.frame.cache_clear()
    promises._actual_share.cache_clear()  # noqa: SLF001
    promises._conduct_raw.cache_clear()  # noqa: SLF001
    promises._conduct_12m.cache_clear()  # noqa: SLF001
    repricing.optimiser_cached.cache_clear()


def _reasons(r: pd.Series) -> list[str]:
    out = []
    if r.flag_drift_below_hurdle:
        out.append(f"RAROC {r.raroc_orig:.1%} at origination, {r.raroc_now:.1%} now against a {r.hurdle:.0%} hurdle")
    if r.flag_downgrade:
        out.append(f"Downgraded {int(r.notches)} notches ({r.orig_rating} to {r.rating_now})")
    if r.flag_ews:
        out.append(f"Early Warning {r.ews_band}")
    if r.flag_stress_driver:
        out.append(f"Monitoring trigger hit: {r.trigger_hit}")
    if r.flag_promise_unmet:
        out.append(f"Promise unmet: {r.promise_realisation:.0%} delivered" if r.promise_realisation == r.promise_realisation else "Promise unmet")
    return out


ROW_COLS = ["facility_id", "source", "borrower_id", "borrower_name", "sector", "product_type", "limit_sar_mn", "ead_sar_mn", "orig_date",
            "orig_rating", "rating_now", "notches", "stage", "tier", "tier_set", "plan_reason", "plan_set_by", "plan_set_on",
            "hurdle", "raroc_orig", "raroc_now", "drift", *[f"d_{c}" for c in drift.COMPONENTS], "main_driver",
            "ews_band", "ews_score", "ews_reasons", "watch_status", "covenants", "covenants_breached", "covenant_min_headroom_pct",
            "covenant_next_test", "conditions_open", "conditions_due", "conditions_overdue", "promise_status", "promise_realisation",
            "renewal_date", "renewal_kind", "months_to_renewal", "going_bad", "defaulted", "on_repricing_list", "recoverable_raroc",
            "recoverable_sva_sar_mn", "action", "action_text", "new_margin_bps", "margin_change_bps", "renewal_fee_bps",
            "extra_collateral_sar_mn", "proposal_id", "relationship_ead_sar_mn"]


def _rows(t: pd.DataFrame) -> list[dict[str, Any]]:
    cols = [c for c in ROW_COLS if c in t.columns]
    out = t[cols].replace({np.nan: None}).to_dict("records")
    for r, (_, s) in zip(out, t.iterrows()):
        r["reasons"] = _reasons(s)
    return out


def select(f: pd.DataFrame, flt: str) -> pd.DataFrame:
    if flt == "going_bad":
        return f[f.going_bad].sort_values(["going_bad_score", "ead_sar_mn"], ascending=False)
    if flt == "repricing":
        return f[f.on_repricing_list].sort_values(["recoverable_raroc", "ead_sar_mn"], ascending=False)
    if flt == "promises_unmet":
        return f[f.flag_promise_unmet].sort_values(["promise_realisation", "ead_sar_mn"], ascending=[True, False])
    if flt == "tier_high":
        return f[f.tier == "High"].sort_values("ead_sar_mn", ascending=False)
    if flt == "renewals_due":
        return f[f.renewal_due].sort_values("renewal_date")
    if flt == "material_going_bad":
        return f[f.material_going_bad].sort_values(["going_bad_score", "relationship_ead_sar_mn", "ead_sar_mn"], ascending=False)
    if flt == "material_renewals":
        return f[f.material_renewal].sort_values(["renewal_date", "relationship_ead_sar_mn"], ascending=[True, False])
    if flt == "conditions_due":
        return f[(f.conditions_due > 0) | (f.covenants_breached > 0)].sort_values(["conditions_overdue", "covenants_breached"], ascending=False)
    return f.sort_values("ead_sar_mn", ascending=False)


def listing(flt: str = "all", q: str = "", sector: str = "", tier: str = "", limit: int = 50, offset: int = 0,
            ref: str | None = None) -> dict[str, Any]:
    if flt not in FILTERS:
        raise ValueError(f"filter must be one of {', '.join(FILTERS)}")
    f, pending = frame(ref)
    t = select(f, flt)
    if q:
        ql = q.lower()
        t = t[t.borrower_name.str.lower().str.contains(ql, regex=False) | t.facility_id.str.lower().str.contains(ql, regex=False)
              | t.borrower_id.str.lower().str.contains(ql, regex=False)]
    if sector:
        t = t[t.sector == sector]
    if tier:
        t = t[t.tier == tier]
    page = t.iloc[offset: offset + limit]
    return clean({"filter": flt, "total": int(len(t)), "ead_sar_mn": float(t.ead_sar_mn.sum()), "offset": offset, "limit": limit,
            "rows": _rows(page), "as_of": str(f.as_of_quarter.iloc[0]) if len(f) else "", "ref_date": str(f.ref_date.iloc[0]) if len(f) else "",
            "pending": pending, "sectors": sorted(x for x in f.sector.dropna().unique().tolist() if x), "sources": sources.lineage()})


def counts(ref: str | None = None) -> dict[str, Any]:
    """For U's landing cards (Existing deals going bad; Renewals and reviews due; Conditions and covenants due) and the Book tabs."""
    f, pending = frame(ref)
    out = {k: int(len(select(f, k))) for k in FILTERS}
    gb = f[f.going_bad]
    out.update({"going_bad_ead_sar_mn": float(gb.ead_sar_mn.sum()),
                "going_bad_by_reason": {k[5:]: int(f[k].sum()) for k in ("flag_drift_below_hurdle", "flag_downgrade", "flag_ews",
                                                                          "flag_stress_driver", "flag_promise_unmet")},
                "renewals_due_repricing": int((f.renewal_due & ~f.above_now & ~f.defaulted).sum()),
                "material_going_bad_names": int(f[f.material_going_bad].borrower_id.nunique()),
                "material_renewals_names": int(f[f.material_renewal].borrower_id.nunique()),
                "materiality": materiality(),
                "defaulted": int(f.defaulted.sum()), "as_of": str(f.as_of_quarter.iloc[0]) if len(f) else "", "pending": pending})
    return out


def _src(domain: str, relation: str, key: dict[str, Any], column: str, period: Any = None) -> dict[str, Any]:
    return {"domain": domain, "relation": relation, "key": key, "period": period, "column": column}


def _sources_of(r: pd.Series) -> dict[str, dict[str, Any]]:
    """Where each step of a facility's drift comes from: the input row the step moves (PLAN_R12 §0 rule 3)."""
    if r.source == "deal_desk":
        k = {"proposal_id": r.deal_id}
        col = {"orig": "raroc_orig_pct", "now": "raroc_now_pct", "pd_migration": "attr_pd_pp", "lgd": "attr_lgd_pp",
               "funding": "attr_funding_pp", "fees": "attr_fees_pp", "utilisation": "attr_utilisation_pp", "cross_sell": "attr_cross_sell_pp"}
        return {c: _src("deal_desk", "dd_raroc_drift", k, v) for c, v in col.items()}
    o = {"exposure_id": r.facility_id}
    e = {"facility_id": r.facility_id, "reporting_quarter": r.as_of_quarter}
    return {"orig": _src("origination", "orig_facility", o, "orig_margin_pct"),
            "pd_migration": _src("ecl_runs", "ecl_facility", {"exposure_id": r.facility_id, "run_id": r.ecl_run}, "rating", r.ecl_run),
            "lgd": _src("ews", "corp_exposure", e, "lgd_pct", r.as_of_quarter),
            "funding": _src("origination", "orig_facility", o, "ftp_pct"),
            "fees": _src("origination", "orig_facility", o, "orig_fees_sar_mn"),
            "utilisation": _src("ews", "corp_exposure", e, "drawn_sar_mn", r.as_of_quarter),
            "cross_sell": _src("deposits", "dep_derived", {"obligor_id": r.borrower_id}, "routing_actual_x"),
            "now": _src("ews", "corp_exposure", e, "pd_pit_12m", r.as_of_quarter)}


def clean(x: Any) -> Any:
    """JSON-safe: NaN and infinities become None, numpy scalars become Python numbers."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def facility(fid: str, ref: str | None = None) -> dict[str, Any]:
    return clean(_facility(fid, ref))


def _facility(fid: str, ref: str | None = None) -> dict[str, Any]:
    f, pending = frame(ref)
    t = f[f.facility_id == fid]
    if not len(t):
        raise KeyError(fid)
    r = t.iloc[0]
    row = _rows(t)[0]
    waterfall: list[dict[str, Any]] = []
    if r.raroc_orig == r.raroc_orig and r.raroc_now == r.raroc_now:
        src = _sources_of(r)
        waterfall = [{"step": "RAROC at origination", "value": float(r.raroc_orig), "source": src["orig"]}]
        waterfall += [{"step": drift.LABELS[c], "value": float(r[f"d_{c}"]) if r[f"d_{c}"] == r[f"d_{c}"] else 0.0, "source": src[c]}
                      for c in drift.COMPONENTS]
        waterfall.append({"step": "RAROC now", "value": float(r.raroc_now), "source": src["now"]})
    pr = promises.frame(f[f.borrower_id == r.borrower_id] if r.source == "book" else f, [])
    prom = promises.display_rows(pr[pr.obligor_id == r.borrower_id])
    cov = sources.live("ews_covenant")
    cov = cov[(cov.facility_id == fid) & (cov.reporting_quarter == cov.reporting_quarter.max())]
    hist = []
    try:
        mp = sources.dd("dd_monitoring_plan")
        if len(mp):
            fc = _col(mp, "facility_ref", "facility_id")
            m = (mp[fc] == fid) if fc else pd.Series(False, index=mp.index)
            if "obligor_id" in mp.columns:
                m |= mp.obligor_id == r.borrower_id
            hist = mp[m].replace({np.nan: None}).to_dict("records")
    except sources.DataPending:
        pass
    return {"facility": row, "waterfall": waterfall,
            "inputs": {k: (None if v != v else v) for k, v in {
                "lgd_orig": float(r.lgd_orig), "lgd_now": float(r.lgd_now), "utilisation_now": float(r.util_now),
                "fee_now_sar_mn": float(r.fee_now_sar_mn), "funding_drift_pct": float(r.fund_drift_pct),
                "orig_margin_pct": float(r.orig_margin_pct), "orig_pd_pct": float(r.orig_pd_pct), "pd_now_pct": float(r.pd_pit_12m) * 100,
                "ftp_orig_pct": float(r.ftp_pct), "tenor_months": float(r.tenor_months), "orig_limit_sar_mn": float(r.orig_limit_sar_mn)}.items()},
            "source": r.source, "drift_source": ("deal_desk.dd_raroc_drift" if r.source == "deal_desk" else "book drift (this service)"),
            "promises": prom, "covenants": cov.replace({np.nan: None}).to_dict("records"), "plan_history": hist,
            "repricing": repricing.detail(r), "pending": pending, "sources": sources.lineage()}
