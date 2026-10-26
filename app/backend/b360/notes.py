"""Derived notes for the Documents & notes tab, derived deterministically from facts.

v5 holds no credit files and no officer's notes. So that the tab shows what a
relationship file would look like, each note here is GENERATED from one fact
in the releases -- a watchlist entry, a rating change, a covenant
breach, a stage or DPD movement, an Early Warning band change, an external
signal. The same inputs always give the same notes.
Only facts up to and including the period being viewed are used.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.v5common import ratings

KIND_ORDER = {"Early Warning": 0, "Watchlist": 1, "Rating": 2, "Behaviour": 2, "Covenant": 3, "Stage": 4,
              "Arrears": 5, "Bureau": 6, "Open Banking": 7, "Account": 8}


def _as_of(period: str) -> str:
    from backend.b360.service import as_of
    return as_of(period)


def _n(v: Any) -> str:
    return "—" if v is None or v != v else f"{float(v):.0f}"


def _note(period: str, kind: str, title: str, text: str, source: str) -> dict[str, Any]:
    return {"period": period, "date": _as_of(period), "kind": kind, "title": title, "text": text,
            "source": source}


def _prev_map(frame: pd.DataFrame, key: str, period_col: str, value: str) -> pd.DataFrame:
    f = frame[[period_col, key, value]].sort_values([key, period_col]).copy()
    f["prev"] = f.groupby(key)[value].shift(1)
    return f


def _exposure_notes(domain_id: str, exp: pd.DataFrame, P: str, K: str, owner_rel: str) -> list[dict[str, Any]]:
    out = []
    word = "Facility" if domain_id == "corporate" else "Account"
    st = _prev_map(exp, K, P, "stage")
    for r in st.itertuples(index=False):
        prev, cur = getattr(r, "prev"), getattr(r, "stage")
        if pd.notna(prev) and int(prev) != int(cur):
            worse = int(cur) > int(prev)
            out.append(_note(getattr(r, P), "Stage", f"{word} {getattr(r, K)} {'moved down' if worse else 'moved up'} "
                             f"to stage {int(cur)}",
                             f"IFRS 9 stage {int(prev)} → {int(cur)} on {getattr(r, K)}.",
                             f"{owner_rel}.stage"))
    dp = _prev_map(exp, K, P, "dpd_days")
    for r in dp.itertuples(index=False):
        prev, cur = getattr(r, "prev"), int(getattr(r, "dpd_days"))
        prev = 0 if pd.isna(prev) else int(prev)
        for floor in (30, 90):
            if cur >= floor > prev:
                out.append(_note(getattr(r, P), "Arrears", f"{word} {getattr(r, K)} reached {floor}+ days past due",
                                 f"Days past due {prev} → {cur}.", f"{owner_rel}.dpd_days"))
        if prev >= 30 and cur == 0:
            out.append(_note(getattr(r, P), "Arrears", f"{word} {getattr(r, K)} brought up to date",
                             f"Days past due {prev} → 0.", f"{owner_rel}.dpd_days"))
    return out


def derive(domain_id: str, owner_id: str, b: dict[str, pd.DataFrame], series: list[dict[str, Any]],
           period: str) -> list[dict[str, Any]]:
    corporate = domain_id == "corporate"
    P = "reporting_quarter" if corporate else "reporting_month"
    K = "facility_id" if corporate else "account_id"
    notes: list[dict[str, Any]] = []
    o = b["owner"].sort_values(P)

    if corporate:
        prev_watch = 0
        for r in o.to_dict("records"):
            w = int(r.get("watchlist_flag") or 0)
            if w and not prev_watch:
                notes.append(_note(r[P], "Watchlist", "Placed on the watchlist",
                                   f"Reason recorded: {r.get('watchlist_reason') or 'none given'}.",
                                   "corp_borrower_quarter.watchlist_flag, watchlist_reason"))
            elif prev_watch and not w:
                notes.append(_note(r[P], "Watchlist", "Removed from the watchlist",
                                   "The watchlist flag was cleared this quarter.",
                                   "corp_borrower_quarter.watchlist_flag"))
            prev_watch = w
            moved = int(r.get("rating_notches_moved") or 0)
            if moved:
                frm, to = r.get("rating_previous"), r.get("rating_current")
                worse = ratings.notches(frm, to) > 0
                notes.append(_note(r[P], "Rating", f"Rating {'downgraded' if worse else 'upgraded'} {frm} → {to}",
                                   f"{abs(moved)} notch{'es' if abs(moved) != 1 else ''}; outlook "
                                   f"{r.get('rating_outlook')}; driver: {r.get('rating_driver') or 'not stated'}.",
                                   "corp_borrower_quarter.rating_current, rating_previous"))
        for r in b["cov"].to_dict("records"):
            if int(r.get("breach_flag") or 0) and int(r.get("consecutive_breaches") or 0) == 1:
                notes.append(_note(r[P], "Covenant", f"{r['covenant_type']} covenant breached on {r['facility_id']}",
                                   f"Observed {r['observed_value']:,.3f} against threshold {r['threshold_value']:,.3f}"
                                   f" (headroom {r['headroom_pct']:.1f}%).",
                                   "corp_covenant_quarter.breach_flag"))
            if r.get("waiver_status") == "GRANTED" and r.get("waiver_quarter") == r[P]:
                notes.append(_note(r[P], "Covenant", f"Waiver granted: {r['covenant_type']} on {r['facility_id']}",
                                   "A waiver of the breach was granted this quarter.",
                                   "corp_covenant_quarter.waiver_status, waiver_quarter"))
        notes += _exposure_notes(domain_id, b["exp"], P, K, "corp_facility_quarter")
        prev = None
        for r in b["bureau"].sort_values(P).to_dict("records"):
            if int(r.get("external_dpd_days") or 0) > 59 and (prev is None or int(prev.get("external_dpd_days") or 0) <= 59):
                notes.append(_note(r[P], "Bureau", "Past due at another lender",
                                   f"Bureau shows external DPD of {int(r['external_dpd_days'])} days.",
                                   "bureau_corp_quarter.external_dpd_days"))
            prev = r
        for r in b["ob"].sort_values(P).to_dict("records"):
            if (r.get("inflow_trend_pct") or 0) <= -25:
                notes.append(_note(r[P], "Open Banking", "Operating inflows fell sharply",
                                   f"Operating inflows {r['inflow_trend_pct']:+.1f}% on the quarter.",
                                   "openbanking_corp_quarter.inflow_trend_pct"))
    else:
        for r in o.to_dict("records"):
            if r.get("score_band_previous") and r.get("score_band") != r.get("score_band_previous"):
                worse = str(r["score_band"]) > str(r["score_band_previous"])
                notes.append(_note(r[P], "Behaviour", f"Behaviour band {'fell' if worse else 'rose'} "
                                   f"{r['score_band_previous']} → {r['score_band']}",
                                   f"Behaviour score {_n(r.get('behaviour_score_previous'))} → "
                                   f"{_n(r.get('behaviour_score'))}.",
                                   "retail_customer_month.score_band"))
        acc = b["exp"].groupby(K).agg(first=(P, "min"), product=("product", "first")).reset_index()
        for r in acc.to_dict("records"):
            notes.append(_note(r["first"], "Account", f"{r['product']} account {r[K]} first on book",
                               "First month this account appears in the book.", "retail_account_month.account_id"))
        notes += _exposure_notes(domain_id, b["exp"], P, K, "retail_account_month")
        prev = None
        for r in b["bureau"].sort_values(P).to_dict("records"):
            score = r.get("bureau_score")
            if score is not None and score < 560 and (prev is None or (prev.get("bureau_score") or 900) >= 560):
                notes.append(_note(r[P], "Bureau", "Bureau score fell below 560",
                                   f"Bureau score {int(score)}.", "bureau_retail_month.bureau_score"))
            if int(r.get("external_dpd_days") or 0) > 59 and (prev is None or int(prev.get("external_dpd_days") or 0) <= 59):
                notes.append(_note(r[P], "Bureau", "Past due at another lender",
                                   f"External DPD {int(r['external_dpd_days'])} days "
                                   f"({r.get('worst_external_status')}).", "bureau_retail_month.external_dpd_days"))
            prev = r
        for r in b["ob"].sort_values(P).to_dict("records"):
            if int(r.get("salary_interruption_flag") or 0):
                notes.append(_note(r[P], "Open Banking", "Salary credit missing",
                                   "Salaried customer with no salary credit observed this month.",
                                   "openbanking_retail_month.salary_interruption_flag"))
    prev_band = None
    for p in series:
        if prev_band is not None and p["band"] != prev_band:
            notes.append(_note(p["period"], "Early Warning", f"Early Warning band {prev_band} → {p['band']}",
                               f"Score {p['score']}; rules fired: {p['reasons'] or 'none'}.",
                               "ews release: ews_score, ews_reasons"))
        prev_band = p["band"]
    notes = [n for n in notes if n["period"] <= period]
    notes.sort(key=lambda n: (n["period"], -KIND_ORDER.get(n["kind"], 9), n["title"]), reverse=True)
    return notes
