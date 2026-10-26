"""Who to call today (R14 backlog #7): the names that need a call this week, with the reason and the action, ranked by
materiality.

Signals, each with its weight (1 watch … 5 call today) and the relation it reads:
  conduct   cheque returns, missed payroll runs (salary delays), inflow falls        deposits.dep_month; dd_account_conduct,
                                                                                    dd_returned_cheque (Deal Desk obligors)
  bureau    new past due or default at other banks, other-bank debt doubled,
            enquiry spike                                                           bureau.bureau_corp_quarter
  covenant  breach at the last test, headroom under 10%                             ews.corp_covenant (via the Book)
  EWS       band high or critical, band worsened since the previous quarter         ews.corp_exposure
  tier      a named monitoring trigger hit on a plan; tier High                     deal_desk.dd_monitoring_plan (via the Book)
  arrears   days past due on our facilities                                         ews.corp_exposure
Materiality = EAD × min(1, total weight / 10): exposure weighted by how strong the evidence is. Defaulted names are in workout,
not on the call list. Deterministic writer for the reason and the action (PLAN_R13 N3).
"""
from __future__ import annotations

import functools
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from backend.intel.calls import reads, signals

SEVERE = ("high", "critical")
BAND_RANK = {"none": 0, "not scored": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}

#: id -> (label, weight, action)
SIGNALS: dict[str, tuple[str, int, str]] = {
    "bureau_default": ("Default reported at another bank", 5, "Call the CFO today: confirm the other-bank default and our standstill position; send to Early Warning."),
    "dpd": ("Days past due on our facilities", 4, "Call the treasurer: agree the date the arrears clear; stop new drawings until they do."),
    "payroll": ("Payroll run missed", 4, "Call the owner: ask why salaries were not paid through us and how liquidity stands this month."),
    "bureau_dpd": ("New past due at other banks", 4, "Call the CFO: ask which bank is past due and why; request the latest cash-flow forecast."),
    "ews_severe": ("Early Warning high or critical", 4, "Call the RM and the client this week: walk the Early Warning reasons and agree actions."),
    "trigger": ("Monitoring trigger hit", 4, "Call the client: the plan's named trigger fired; agree the remedy the plan sets."),
    "covenant_breach": ("Covenant in breach", 3, "Call the CFO: request the compliance certificate and a remedy plan before the next test."),
    "cheques": ("Cheques returned", 3, "Call the treasurer: confirm the returned cheques are regularised and the cause."),
    "overdraft_excess": ("Account in excess of limit", 3, "Call the treasurer: agree how the excess is cleared and whether the limit fits the cycle."),
    "inflow_fall": ("Account inflows down sharply", 3, "Ask where receipts are now routed; request aged receivables and the order book."),
    "ews_worse": ("Early Warning band worsened", 2, "Ask the RM for a client update on what changed this quarter."),
    "covenant_headroom": ("Covenant headroom under 10%", 2, "Ask for management accounts early: the next test is close."),
    "bureau_debt": ("Other-bank debt doubled", 2, "Ask what the new borrowing at other banks funds; check our ranking and security."),
    "bureau_enquiries": ("Several new bureau enquiries", 1, "Ask whether the client is refinancing elsewhere."),
    "tier_high": ("Monitoring tier High", 1, "Keep the High-tier call cadence: monthly contact."),
}


def _frame_book() -> tuple[pd.DataFrame, list[str]]:
    from backend.dealdesk.book import core
    f, pending = core.frame()
    f = f[~f.defaulted.astype(bool)]
    band_rank = f.ews_band.astype(str).str.lower().map(BAND_RANK).fillna(0)
    f = f.assign(_band=band_rank, _tierhigh=(f.tier == "High"), _trig=f.flag_stress_driver.astype(bool))
    g = f.groupby("borrower_id")
    out = pd.DataFrame({
        "borrower_name": g.borrower_name.first(), "sector": g.sector.first(), "source": g.source.first(),
        "ead_sar_mn": g.ead_sar_mn.sum(), "facilities": g.facility_id.count(), "stage": g.stage.max(),
        "dpd_days": g.dpd_days.max() if "dpd_days" in f.columns else 0, "band_rank": g._band.max(),
        "covenants_breached": g.covenants_breached.sum(), "covenant_min_headroom_pct": g.covenant_min_headroom_pct.min(),
        "tier_high": g._tierhigh.any(), "trigger": g._trig.any(),
        "trigger_label": f.assign(_t=f.trigger_hit.where(f.trigger_hit.map(lambda x: isinstance(x, str) and bool(x)))).groupby("borrower_id")._t.first(),
        "proposal_id": f.assign(_p=f.proposal_id.where(f.proposal_id.map(lambda x: isinstance(x, str) and bool(x)))).groupby("borrower_id")._p.first(),
        "as_of_quarter": g.as_of_quarter.first(),
    })
    out["top_facility"] = f.loc[f.groupby("borrower_id").ead_sar_mn.idxmax().dropna(), ["borrower_id", "facility_id"]].set_index("borrower_id").facility_id
    out["covenant_quarter"] = f.covenant_quarter.dropna().iloc[0] if f.covenant_quarter.notna().any() else None
    return out, list(pending)


@functools.lru_cache(maxsize=1)
def _ews_prev() -> pd.DataFrame:
    e = reads.read("ews", "corp_exposure", ["borrower_id", "reporting_quarter", "ews_band"])
    q = sorted(e.reporting_quarter.astype(str).unique())
    last, prev = q[-1], q[-2]
    e = e[e.reporting_quarter.isin([last, prev])].assign(r=e.ews_band.astype(str).str.lower().map(BAND_RANK).fillna(0))
    p = e.pivot_table(index="borrower_id", columns="reporting_quarter", values="r", aggfunc="max")
    return pd.DataFrame({"band_now": p.get(last), "band_prev": p.get(prev), "ews_quarter": last, "ews_quarter_prev": prev})


def _dd_conduct(limits: list[str]) -> pd.DataFrame:
    """Deal Desk obligors' conduct (dd_account_conduct, dd_returned_cheque): latest month vs the prior 3, unregularised returns."""
    from backend.dealdesk.book import sources as bs
    pending: list[str] = []
    c = bs.dd_or_empty("dd_account_conduct", pending)
    rc = bs.dd_or_empty("dd_returned_cheque", pending)
    if pending:
        limits.append(f"Deal Desk conduct relations not available: {', '.join(pending)}.")
    rows = {}
    if len(c):
        c = c.sort_values("month")
        for ob, g in c.groupby("obligor_id"):
            last = g.iloc[-1]
            prior = g.iloc[-4:-1]
            base = float(prior.credit_turnover_mn.mean()) if len(prior) else np.nan
            chg = (float(last.credit_turnover_mn) / base - 1) * 100 if base and base > 0.01 else np.nan
            rows[ob] = {"dd_month": last.month, "dd_inflow_change_pct": chg, "dd_past_due_days": float(last.past_due_days_max or 0),
                        "dd_proposal_id": last.proposal_id}
    if len(rc):
        un = rc[pd.to_numeric(rc.regularised_flag, errors="coerce").fillna(1) == 0]
        for ob, g in un.groupby("obligor_id"):
            rows.setdefault(ob, {})
            rows[ob].update({"dd_cheques_unregularised": int(len(g)), "dd_cheques_mn": float(g.amount_mn.sum()),
                             "dd_cheque_reason": str(g.sort_values("return_date").reason.iloc[-1])})
    return pd.DataFrame.from_dict(rows, orient="index")


class _Row(dict):
    """A record with attribute access and a `.name` (fast stand-in for a pandas row)."""

    def __init__(self, d: dict[str, Any], name: Any):
        super().__init__(d)
        self.name = name

    def __getattr__(self, k: str) -> Any:
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k) from None


def _fired(r: Any) -> list[tuple[str, Any, dict[str, Any]]]:
    """(signal id, value, source) for each signal that fires on a borrower row."""
    S = reads.src
    bid = r.name
    q = r.get("as_of_quarter")
    out: list[tuple[str, Any, dict[str, Any]]] = []
    bq = r.get("bureau_quarter")
    cm = r.get("conduct_months")

    def ok(v: Any) -> bool:
        return v is not None and not (isinstance(v, float) and v != v)

    if ok(r.get("bureau_default")) and r.bureau_default > 0 and not (r.get("bureau_default_prev") or 0) > 0:
        out.append(("bureau_default", 1, S("bureau", "bureau_corp_quarter", {"borrower_id": bid, "reporting_quarter": bq}, "external_default_flag", bq)))
    dpd = max(float(r.get("dpd_days") or 0), float(r.get("dd_past_due_days") or 0) if ok(r.get("dd_past_due_days")) else 0.0)
    if dpd > 0:
        out.append(("dpd", dpd, S("ews", "corp_exposure", {"borrower_id": bid, "reporting_quarter": q}, "dpd_days", q, "max over facilities")
                    if float(r.get("dpd_days") or 0) > 0 else S("deal_desk", "dd_account_conduct", {"obligor_id": bid, "month": r.get("dd_month")}, "past_due_days_max", r.get("dd_month"))))
    if ok(r.get("payroll_missed_3m")) and r.payroll_missed_3m > 0:
        out.append(("payroll", r.payroll_missed_3m, S("deposits", "dep_month", {"obligor_id": bid}, "payroll_flag", cm, "months without payroll in the last 3, payroll customer")))
    if ok(r.get("bureau_dpd_days")) and r.bureau_dpd_days > 0 and not (r.get("bureau_dpd_days_prev") or 0) > 0:
        out.append(("bureau_dpd", r.bureau_dpd_days, S("bureau", "bureau_corp_quarter", {"borrower_id": bid, "reporting_quarter": bq}, "external_dpd_days", bq)))
    if (r.get("band_rank") or 0) >= 3:
        out.append(("ews_severe", "critical" if r.band_rank >= 4 else "high", S("ews", "corp_exposure", {"borrower_id": bid, "reporting_quarter": q}, "ews_band", q, "worst over facilities")))
    if bool(r.get("trigger")):
        out.append(("trigger", r.get("trigger_label") or "named trigger", S("deal_desk", "dd_monitoring_plan", {"obligor_id": bid}, "named_triggers")))
    if (r.get("covenants_breached") or 0) > 0:
        out.append(("covenant_breach", r.covenants_breached, S("ews", "corp_covenant", {"borrower_id": bid}, "breach_flag", r.get("covenant_quarter"), "sum over facilities")))
    chq = float(r.get("cheques_returned_3m") or 0) if ok(r.get("cheques_returned_3m")) else 0.0
    if chq > 0:
        out.append(("cheques", chq, S("deposits", "dep_month", {"obligor_id": bid}, "cheques_returned_count", cm, "sum, last 3 months")))
    elif ok(r.get("dd_cheques_unregularised")) and r.dd_cheques_unregularised > 0:
        out.append(("cheques", r.dd_cheques_unregularised, S("deal_desk", "dd_returned_cheque", {"obligor_id": bid}, "regularised_flag", None, "count not regularised")))
    if ok(r.get("excess_days_3m")) and r.excess_days_3m >= 15:
        out.append(("overdraft_excess", r.excess_days_3m, S("deposits", "dep_month", {"obligor_id": bid}, "excess_days", cm, "sum, last 3 months")))
    infl = r.get("inflow_change_pct") if ok(r.get("inflow_change_pct")) else r.get("dd_inflow_change_pct")
    if ok(infl) and infl < -30:
        src = (S("deposits", "dep_month", {"obligor_id": bid}, "credit_turnover_sar_mn", cm, "last-3-month mean vs prior-6-month mean")
               if ok(r.get("inflow_change_pct")) else S("deal_desk", "dd_account_conduct", {"obligor_id": bid}, "credit_turnover_mn", r.get("dd_month"), "latest month vs prior 3"))
        out.append(("inflow_fall", round(float(infl), 1), src))
    if ok(r.get("band_now")) and ok(r.get("band_prev")) and r.band_now > r.band_prev and r.band_now >= 2 and (r.get("band_rank") or 0) < 3:
        out.append(("ews_worse", f"{int(r.band_prev)}→{int(r.band_now)}", S("ews", "corp_exposure", {"borrower_id": bid}, "ews_band", f"{r.get('ews_quarter_prev')}→{r.get('ews_quarter')}", "band rank, worst facility")))
    hr = r.get("covenant_min_headroom_pct")
    if ok(hr) and 0 <= hr < 10 and not (r.get("covenants_breached") or 0) > 0:
        out.append(("covenant_headroom", round(float(hr), 1), S("ews", "corp_covenant", {"borrower_id": bid}, "headroom_pct", r.get("covenant_quarter"), "min over covenants")))
    if ok(r.get("bureau_exposure_change_pct")) and r.bureau_exposure_change_pct > 100:
        out.append(("bureau_debt", round(float(r.bureau_exposure_change_pct)), S("bureau", "bureau_corp_quarter", {"borrower_id": bid}, "external_exposure_sar_mn", f"{r.get('bureau_quarter_prev')}→{bq}", "quarter on quarter change %")))
    if ok(r.get("bureau_enquiries")) and r.bureau_enquiries >= 3 and r.bureau_enquiries > (r.get("bureau_enquiries_prev") or 0):
        out.append(("bureau_enquiries", r.bureau_enquiries, S("bureau", "bureau_corp_quarter", {"borrower_id": bid, "reporting_quarter": bq}, "enquiries_q", bq)))
    if bool(r.get("tier_high")) and not bool(r.get("trigger")):
        out.append(("tier_high", "High", S("deal_desk", "dd_monitoring_plan", {"obligor_id": bid}, "tier")))
    return out


def _fmt_value(sid: str, v: Any) -> str:
    if sid == "bureau_default":
        return "new this quarter"
    if sid == "dpd" or sid == "bureau_dpd":
        return f"{float(v):.0f} days"
    if sid == "inflow_fall":
        return f"{float(v):+.0f}%"
    if sid == "bureau_debt":
        return f"+{float(v):.0f}%"
    if sid == "covenant_headroom":
        return f"{float(v):.1f}% headroom"
    if sid == "overdraft_excess":
        return f"{float(v):.0f} days in 3 months"
    if sid in ("payroll",):
        return f"{float(v):.0f} month{'s' if float(v) != 1 else ''}"
    if sid in ("cheques", "covenant_breach", "bureau_enquiries"):
        return f"{float(v):.0f}"
    return str(v)


LIMITS = [
    "Conduct is monthly (deposits.dep_month to its last month): a salary run paid a few days late inside the month cannot be seen; a missed month can.",
    "Bureau is quarterly (bureau.bureau_corp_quarter): a past due reported this week appears after the next bureau load.",
    "Signals are compared with the previous period only (new since last quarter or month); a long-standing problem shows once it is already in arrears, Early Warning or covenants.",
    "Defaulted names are in workout and are not on the call list.",
    "No RM is recorded on back-book facilities; Deal Desk deals carry their RM.",
]


@functools.lru_cache(maxsize=2)
def _build(ver: str) -> tuple[pd.DataFrame, tuple[str, ...]]:
    limits: list[str] = []
    b, pending = _frame_book()
    s = signals.borrower_signals()
    t = b.join(s, how="left").join(_ews_prev(), how="left")
    dd = _dd_conduct(limits)
    if len(dd):
        t = t.join(dd, how="left")
    rows = []
    for bid, r in zip(t.index, t.to_dict("records")):
        r = _Row(r, bid)
        fired = _fired(r)
        if not fired:
            continue
        w = sum(SIGNALS[sid][1] for sid, _, _ in fired)
        fired.sort(key=lambda x: -SIGNALS[x[0]][1])
        rows.append({"borrower_id": bid, "weight": w, "max_weight": SIGNALS[fired[0][0]][1], "fired": fired})
    c = pd.DataFrame(rows).set_index("borrower_id") if rows else pd.DataFrame(columns=["weight", "max_weight", "fired"])
    t = t.join(c, how="inner")
    t["materiality_sar_mn"] = t.ead_sar_mn * np.minimum(1.0, t.weight / 10.0)
    t = t.sort_values(["materiality_sar_mn", "max_weight"], ascending=False)
    return t, tuple(pending + limits)


def _version() -> str:
    try:
        from backend.dealdesk.book import core
        return core.data_version()
    except Exception:  # noqa: BLE001
        return ""


def _floor() -> float:
    """R14 G: the J9 materiality floor (relationship EAD, Deal Desk Parameters → relationship · book)."""
    try:
        from backend.dealdesk.book import core
        return float(core.materiality()["materiality_floor_sar_mn"])
    except Exception:  # noqa: BLE001 - parameters unavailable: the J9 default
        return 50.0


def calls(limit: int = 25, offset: int = 0, signal: str = "", sector: str = "", min_weight: int = 0, today: str | None = None,
          scope: str = "material") -> dict[str, Any]:
    """scope='material' (default, R14 G): names whose relationship EAD is at or above the J9 floor — a CCO's call list;
    scope='all': every name with a signal (the RM-level list)."""
    if scope not in ("material", "all"):
        raise ValueError("scope must be material or all")
    t, notes = _build(_version())
    floor = _floor()
    whole = t
    below = t[t.ead_sar_mn < floor]
    if scope == "material":
        t = t[t.ead_sar_mn >= floor]
    if signal:
        if signal not in SIGNALS:
            raise ValueError(f"signal must be one of {', '.join(SIGNALS)}")
        t = t[t.fired.map(lambda f: any(x[0] == signal for x in f))]
    if sector:
        t = t[t.sector == sector]
    if min_weight:
        t = t[t.max_weight >= min_weight]
    d0 = date.fromisoformat(today) if today else date.today()
    page = t.iloc[offset: offset + limit]
    out = []
    for rank, (bid, r) in enumerate(page.iterrows(), start=offset + 1):
        fired = r.fired
        top = fired[0][0]
        reason = "; ".join(f"{SIGNALS[sid][0]} ({_fmt_value(sid, v)})" for sid, v, _ in fired[:3]) + (f" and {len(fired) - 3} more" if len(fired) > 3 else "")
        call_by = d0 if SIGNALS[top][1] >= 5 else d0 + timedelta(days=(4 - d0.weekday()) % 7 if SIGNALS[top][1] >= 3 else 7)
        out.append({
            "rank": rank, "borrower_id": bid, "borrower_name": r.borrower_name, "sector": r.sector, "source": r.source,
            "proposal_id": r.get("proposal_id") if isinstance(r.get("proposal_id"), str) else (r.get("dd_proposal_id") if isinstance(r.get("dd_proposal_id"), str) else None),
            "top_facility": r.get("top_facility"),
            "ead_sar_mn": reads.num(r.ead_sar_mn, reads.src("ews", "corp_exposure", {"borrower_id": bid, "reporting_quarter": r.as_of_quarter}, "ead_sar_mn", r.as_of_quarter, "sum over live facilities"), "SAR m"),
            "materiality_sar_mn": reads.computed(r.materiality_sar_mn, "EAD × min(1, signal weight / 10)", [], "SAR m"),
            "weight": int(r.weight), "urgency": "today" if SIGNALS[top][1] >= 5 else "this week" if SIGNALS[top][1] >= 3 else "next week",
            "call_by": call_by.isoformat(),
            "signals": [{"id": sid, "label": SIGNALS[sid][0], "weight": SIGNALS[sid][1], "value": reads.num(v, src), "text": _fmt_value(sid, v)} for sid, v, src in fired],
            "reason": reason, "action": SIGNALS[top][2],
            "open": (f"/deal-desk/{r.proposal_id}?from=early-warning" if isinstance(r.get("proposal_id"), str)
                     else f"/borrower-360?domain=corporate&customer_id={bid}&from=early-warning"),
        })
    by_sig = {k: int(t.fired.map(lambda f, k=k: any(x[0] == k for x in f)).sum()) for k in SIGNALS}
    if not by_sig.get("payroll"):
        notes = tuple(notes) + ("No payroll customer missed a monthly run in the last 3 months of deposits.dep_month; payment dates are not "
                                "in the relation, so a salary delay inside a month is not visible.",)
    n_today = int((t.max_weight >= 5).sum())
    n_week = int(((t.max_weight >= 3) & (t.max_weight < 5)).sum())
    head = out[:3]
    lead = (f"{len(t):,} material names (relationship EAD at least SAR {floor:,.0f}m) need a call" if scope == "material"
            else f"{len(t):,} names need a call")
    summary = (f"{lead} ({n_today:,} today, {n_week:,} this week; SAR {t.ead_sar_mn.sum():,.0f}m EAD). "
               + ("Start with " + "; ".join(f"{x['borrower_name']} (SAR {x['ead_sar_mn']['value']:,.0f}m: {x['signals'][0]['label'].lower()})" for x in head) + "."
                  if head else "")) if len(t) else (f"No material name (relationship EAD at least SAR {floor:,.0f}m) needs a call this week on the signals available."
                                                     if scope == "material" else "Nobody needs a call this week on the signals available.")
    if scope == "material" and len(below):
        summary += f" {len(below):,} smaller names with a signal stay with their RMs (full list)."
    return reads.clean({"summary": summary, "total": int(len(t)), "today": n_today, "this_week": n_week, "rows": out, "by_signal": by_sig,
                        "scope": scope, "materiality_floor_sar_mn": floor, "whole_book_total": int(len(whole)), "below_floor": int(len(below)),
                        "material_ead_sar_mn": float(t.ead_sar_mn.sum()),
                        "signals": [{"id": k, "label": v[0], "weight": v[1], "action": v[2]} for k, v in SIGNALS.items()],
                        "method": "Materiality = EAD × min(1, total signal weight / 10); urgency from the strongest signal (5 today, 3–4 this week, 1–2 next week).",
                        "data_limits": LIMITS + [n for n in notes if n], "offset": offset, "limit": limit, "sources": reads.lineage(),
                        "as_of": {"book": str(t.as_of_quarter.iloc[0]) if len(t) else "", "conduct": str(t.conduct_months.dropna().iloc[0]) if len(t) and t.conduct_months.notna().any() else "",
                                  "bureau": str(t.bureau_quarter.dropna().iloc[0]) if len(t) and t.bureau_quarter.notna().any() else ""}})


def clear() -> None:
    _build.cache_clear()
    _ews_prev.cache_clear()
