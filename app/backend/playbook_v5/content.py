"""Report content from the books: the sections the seed quotes and the assistant drafts.

Every figure comes from the v5 books read-only: the corporate Early Warning release (the Cockpit corporate book's
facilities with their Early Warning score and band), the corporate borrower table, and the retail account book.
Amounts are SAR million in the books and SAR (riyals) in blocks (format `sar`); rates are fractions (`pct`).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from backend.playbook_v5 import paths

CORP_PERIOD = "2026Q2"
CORP_PRIOR = "2026Q1"
RETAIL_PERIOD = "2026-08"
STAGE_COLOURS = ["#5B8C5A", "#E0A100", "#C2410C"]
RATING_ORDER = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-",
                "CCC+", "CCC", "CCC-", "CC", "C", "D"]


@lru_cache(maxsize=1)
def corp() -> pd.DataFrame:
    cols = ["facility_id", "borrower_id", "borrower_name", "reporting_quarter", "product_type", "sector", "sub_sector",
            "region", "ead_sar_mn", "ecl_sar_mn", "stage", "dpd_days", "pd_pit_12m", "lgd_pct", "limit_sar_mn",
            "drawn_sar_mn", "collateral_value_sar_mn", "collateral_ltv_pct", "covenant_breaches", "ews_score",
            "ews_band", "ews_reasons", "watchlist_flag"]
    return pd.read_parquet(paths.EWS / paths.EWS_CORP / "ews_corp_exposure.parquet", columns=cols)


@lru_cache(maxsize=1)
def borrowers() -> pd.DataFrame:
    return pd.read_parquet(paths.LAKE / paths.CORP_BOOK / "corp_borrower_quarter.parquet")


@lru_cache(maxsize=1)
def retail() -> pd.DataFrame:
    cols = ["account_id", "customer_id", "reporting_month", "product", "employment_type", "ead_sar_mn", "ecl_sar_mn",
            "stage", "dpd_days"]
    return pd.read_parquet(paths.LAKE / paths.RETAIL_BOOK / "retail_account_month.parquet", columns=cols)


def sar(mn: float) -> float:
    return round(float(mn) * 1e6, 0)


def mn_words(mn: float) -> str:
    v = float(mn)
    return f"SAR {v / 1000:,.2f}bn" if abs(v) >= 1000 else f"SAR {v:,.1f}m"


@lru_cache(maxsize=1)
def corp_ruleset() -> str:
    cols = ["ews_ruleset_version"]
    v = pd.read_parquet(paths.EWS / paths.EWS_CORP / "ews_corp_exposure.parquet", columns=cols)
    return str(v.ews_ruleset_version.iloc[-1])


def quarters(n: int = 8) -> list[str]:
    return sorted(corp().reporting_quarter.unique())[-n:]


# ------------------------------------------------------------- portfolio


def corp_totals(period: str = CORP_PERIOD, sector: str | None = None) -> dict[str, Any]:
    e = corp()
    q = e[e.reporting_quarter == period]
    if sector:
        q = q[q.sector == sector]
    ead, ecl = float(q.ead_sar_mn.sum()), float(q.ecl_sar_mn.sum())
    s2 = float(q[q.stage == 2].ead_sar_mn.sum())
    s3 = float(q[q.stage == 3].ead_sar_mn.sum())
    warned = q[q.ews_band.isin(["high", "critical"])]
    return {"period": period, "ead": ead, "ecl": ecl, "coverage": ecl / ead if ead else 0.0,
            "stage2_share": s2 / ead if ead else 0.0, "stage3_share": s3 / ead if ead else 0.0,
            "borrowers": int(q.borrower_id.nunique()), "facilities": int(len(q)),
            "warned_borrowers": int(warned.borrower_id.nunique()), "warned_ead": float(warned.ead_sar_mn.sum())}


def _kpis(now: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "kpis", "items": [
        {"label": "EAD", "value": sar(now["ead"]), "format": "sar", "delta": sar(now["ead"] - before["ead"])},
        {"label": "ECL", "value": sar(now["ecl"]), "format": "sar", "delta": sar(now["ecl"] - before["ecl"]),
         "status": "amber" if now["ecl"] > before["ecl"] * 1.05 else "green"},
        {"label": "Coverage", "value": now["coverage"], "format": "pct", "delta": now["coverage"] - before["coverage"]},
        {"label": "Stage 2 share of EAD", "value": now["stage2_share"], "format": "pct",
         "delta": now["stage2_share"] - before["stage2_share"],
         "status": "amber" if now["stage2_share"] > before["stage2_share"] else "green"},
        {"label": "Stage 3 share of EAD", "value": now["stage3_share"], "format": "pct",
         "delta": now["stage3_share"] - before["stage3_share"]},
        {"label": "Borrowers on high or critical warning", "value": now["warned_borrowers"], "format": "int",
         "delta": now["warned_borrowers"] - before["warned_borrowers"]},
    ]}


def trend_chart(sector: str | None = None, n: int = 8) -> dict[str, Any]:
    qs = quarters(n)
    rows = [corp_totals(q, sector) for q in qs]
    return {"kind": "chart", "title": f"{'ECL and EAD' if not sector else sector + ': ECL and EAD'}, last {n} quarters",
            "figure": {"data": [
                {"type": "bar", "name": "EAD (SAR bn)", "x": qs, "y": [round(r["ead"] / 1000, 3) for r in rows],
                 "marker": {"color": "#9DB7C9"}, "yaxis": "y"},
                {"type": "scatter", "mode": "lines+markers", "name": "ECL (SAR m)", "x": qs,
                 "y": [round(r["ecl"], 1) for r in rows], "marker": {"color": "#C2410C"}, "line": {"width": 3},
                 "yaxis": "y2"}],
                "layout": {"yaxis": {"title": {"text": "EAD, SAR bn"}},
                           "yaxis2": {"title": {"text": "ECL, SAR m"}, "overlaying": "y", "side": "right"},
                           "legend": {"orientation": "h"}, "margin": {"t": 30}}},
            "note": "Corporate book, quarter-end EAD and ECL."}


def stage_chart(sector: str | None = None, period: str = CORP_PERIOD, prior: str = CORP_PRIOR) -> dict[str, Any]:
    e = corp()
    data = []
    for i, st in enumerate((1, 2, 3)):
        ys = []
        for p in (prior, period):
            q = e[(e.reporting_quarter == p) & (e.stage == st)]
            if sector:
                q = q[q.sector == sector]
            ys.append(round(float(q.ead_sar_mn.sum()) / 1000, 3))
        data.append({"type": "bar", "name": f"Stage {st}", "x": [prior, period], "y": ys,
                     "marker": {"color": STAGE_COLOURS[i]}})
    return {"kind": "chart", "title": f"{sector + ': ' if sector else ''}EAD by stage, {prior} and {period} (SAR bn)",
            "figure": {"data": data, "layout": {"barmode": "stack", "legend": {"orientation": "h"},
                                                "yaxis": {"title": {"text": "SAR bn"}}}}}


def sector_table(period: str = CORP_PERIOD, prior: str = CORP_PRIOR, top: int = 12) -> dict[str, Any]:
    e = corp()
    rows = []
    total = float(e[e.reporting_quarter == period].ead_sar_mn.sum())
    for sec, g in e[e.reporting_quarter == period].groupby("sector"):
        p = e[(e.reporting_quarter == prior) & (e.sector == sec)]
        ead, ecl = float(g.ead_sar_mn.sum()), float(g.ecl_sar_mn.sum())
        rows.append({"sector": str(sec), "ead": sar(ead), "share": ead / total, "ecl": sar(ecl),
                     "coverage": ecl / ead if ead else 0.0,
                     "stage2": float(g[g.stage == 2].ead_sar_mn.sum()) / ead if ead else 0.0,
                     "ecl_change": sar(ecl - float(p.ecl_sar_mn.sum()))})
    rows.sort(key=lambda r: -r["ead"])
    return {"kind": "table", "title": f"Corporate book by sector, {period}",
            "columns": [{"key": "sector", "label": "Sector", "format": "text"},
                        {"key": "ead", "label": "EAD", "format": "sar"},
                        {"key": "share", "label": "Share of EAD", "format": "pct"},
                        {"key": "ecl", "label": "ECL", "format": "sar"},
                        {"key": "coverage", "label": "Coverage", "format": "pct"},
                        {"key": "stage2", "label": "Stage 2 share", "format": "pct"},
                        {"key": "ecl_change", "label": f"ECL change on {prior}", "format": "sar"}],
            "rows": rows[:top], "note": "Sector limit: 18% of the corporate book (CP-1.3)."}


def portfolio_section(period: str = CORP_PERIOD, prior: str = CORP_PRIOR) -> tuple[str, list[dict[str, Any]]]:
    now, before = corp_totals(period), corp_totals(prior)
    top = sector_table(period, prior)["rows"][0]
    text = (f"At {period} the corporate book holds **{mn_words(now['ead'])} of EAD** across {now['borrowers']:,} "
            f"borrowers and {now['facilities']:,} facilities, with **ECL of {mn_words(now['ecl'])}** "
            f"({now['coverage'] * 100:.2f}% coverage). ECL moved by {mn_words(now['ecl'] - before['ecl'])} on {prior}; "
            f"Stage 2 is {now['stage2_share'] * 100:.1f}% of EAD against {before['stage2_share'] * 100:.1f}% a quarter "
            f"earlier. The largest sector is {top['sector']} at {top['share'] * 100:.1f}% of EAD.")
    return "Portfolio overview", [{"kind": "paragraph", "text": text}, _kpis(now, before), trend_chart(),
                                  stage_chart(), sector_table(period, prior)]


# ----------------------------------------------------------- early warning


def ews_rows(period: str = CORP_PERIOD, sector: str | None = None, top: int = 15) -> list[dict[str, Any]]:
    e = corp()
    q = e[e.reporting_quarter == period]
    if sector:
        q = q[q.sector == sector]
    g = q.groupby(["borrower_id", "borrower_name", "sector"]).agg(
        ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"), score=("ews_score", "max"), stage=("stage", "max"),
        dpd=("dpd_days", "max")).reset_index()
    band = q.sort_values("ews_score", ascending=False).drop_duplicates("borrower_id").set_index("borrower_id")
    g["band"] = g.borrower_id.map(band.ews_band)
    g["reason"] = g.borrower_id.map(band.ews_reasons.astype(str))
    g = g[g.band.isin(["high", "critical"])].sort_values(["score", "ead"], ascending=[False, False]).head(top)
    b = borrowers()
    bq = b[b.reporting_quarter == period].set_index("borrower_id")
    out = []
    for r in g.itertuples():
        reason = str(r.reason).split(";")[0].split("|")[0].strip(" []'\"") if r.reason else ""
        out.append({"borrower_id": r.borrower_id, "name": r.borrower_name, "sector": r.sector,
                    "rating": str(bq.rating_current.get(r.borrower_id, "")), "band": str(r.band).capitalize(),
                    "score": float(r.score), "ead": sar(r.ead), "ecl": sar(r.ecl), "stage": float(r.stage),
                    "dpd": float(r.dpd), "reason": reason[:120]})
    return out


def ews_section(period: str = CORP_PERIOD, prior: str = CORP_PRIOR, sector: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    e = corp()
    rows = ews_rows(period, sector)
    q = e[e.reporting_quarter == period]
    p = e[e.reporting_quarter == prior]
    if sector:
        q, p = q[q.sector == sector], p[p.sector == sector]
    bands = ["low", "moderate", "high", "critical"]
    cnt = {bd: int(q[q.ews_band == bd].borrower_id.nunique()) for bd in bands}
    cnt0 = {bd: int(p[p.ews_band == bd].borrower_id.nunique()) for bd in bands}
    hc, hc0 = cnt["high"] + cnt["critical"], cnt0["high"] + cnt0["critical"]
    scope = f"{sector} borrowers" if sector else "corporate borrowers"
    ruleset = str(corp_ruleset())
    text = (f"Early Warning (rule set {ruleset}) flags **{hc} {scope} as high or critical** at {period}, "
            f"against {hc0} at {prior}: {cnt['critical']} critical and {cnt['high']} high. The list below is ordered by "
            "score; each name links to its Borrower 360 page in CreditProbe.")
    chart = {"kind": "chart", "title": f"Borrowers by Early Warning band, {prior} and {period}",
             "figure": {"data": [{"type": "bar", "name": prior, "x": [b.capitalize() for b in bands],
                                  "y": [cnt0[b] for b in bands], "marker": {"color": "#9DB7C9"}},
                                 {"type": "bar", "name": period, "x": [b.capitalize() for b in bands],
                                  "y": [cnt[b] for b in bands], "marker": {"color": "#1F4E6B"}}],
                        "layout": {"barmode": "group", "legend": {"orientation": "h"}}}}
    table = {"kind": "table", "title": f"High and critical warnings, {period}",
             "columns": [{"key": "borrower_id", "label": "Borrower", "format": "text"},
                         {"key": "name", "label": "Name", "format": "text"},
                         {"key": "sector", "label": "Sector", "format": "text"},
                         {"key": "rating", "label": "Rating", "format": "rating"},
                         {"key": "band", "label": "Band", "format": "text"},
                         {"key": "score", "label": "Score", "format": "int"},
                         {"key": "ead", "label": "EAD", "format": "sar"},
                         {"key": "ecl", "label": "ECL", "format": "sar"},
                         {"key": "stage", "label": "Stage", "format": "int"},
                         {"key": "dpd", "label": "DPD", "format": "int"}],
             "rows": rows, "note": f"Customer score is the highest facility score; bands per rule set {ruleset}."}
    return "Early Warning", [{"kind": "paragraph", "text": text}, chart, table]


# ------------------------------------------------------------------ sector


def sector_section(sector: str = "Construction", period: str = CORP_PERIOD,
                   prior: str = CORP_PRIOR) -> list[tuple[str, list[dict[str, Any]]]]:
    e = corp()
    now, before = corp_totals(period, sector), corp_totals(prior, sector)
    book = corp_totals(period)
    share = now["ead"] / book["ead"]
    s = e[(e.sector == sector) & e.reporting_quarter.isin([prior, period])]
    pv = s.pivot_table(index="sub_sector", columns="reporting_quarter", values=["ead_sar_mn", "ecl_sar_mn"],
                       aggfunc="sum").fillna(0)
    subs = []
    for sub in pv.index:
        c0, c1 = float(pv.loc[sub, ("ecl_sar_mn", prior)]), float(pv.loc[sub, ("ecl_sar_mn", period)])
        e1 = float(pv.loc[sub, ("ead_sar_mn", period)])
        subs.append({"sub_sector": str(sub), "ead": sar(e1), "share": e1 / book["ead"], "ecl_before": sar(c0),
                     "ecl_after": sar(c1), "ecl_change": sar(c1 - c0), "coverage": c1 / e1 if e1 else 0.0})
    subs.sort(key=lambda r: -r["ecl_change"])
    summary = (f"{sector} is **{share * 100:.1f}% of corporate EAD** ({mn_words(now['ead'])}) at {period}, against the "
               f"18% sector limit in CP-1.3. ECL rose from {mn_words(before['ecl'])} to **{mn_words(now['ecl'])}** "
               f"({(now['ecl'] / before['ecl'] - 1) * 100:+.1f}%), and coverage from {before['coverage'] * 100:.2f}% to "
               f"{now['coverage'] * 100:.2f}%. Stage 2 is {now['stage2_share'] * 100:.1f}% of the sector's EAD "
               f"(book: {book['stage2_share'] * 100:.1f}%). {now['warned_borrowers']} {sector.lower()} borrowers are on "
               "a high or critical Early Warning.")
    drivers = {"kind": "chart", "title": f"{sector}: ECL change by sub-sector, {prior} to {period} (SAR m)",
               "figure": {"data": [{"type": "bar", "orientation": "h", "y": [r["sub_sector"] for r in subs],
                                    "x": [round(r["ecl_change"] / 1e6, 2) for r in subs],
                                    "marker": {"color": ["#C2410C" if r["ecl_change"] > 0 else "#5B8C5A"
                                                         for r in subs]}}],
                          "layout": {"xaxis": {"title": {"text": "SAR m"}}, "margin": {"l": 160}}}}
    sub_table = {"kind": "table", "title": f"{sector} by sub-sector",
                 "columns": [{"key": "sub_sector", "label": "Sub-sector", "format": "text"},
                             {"key": "ead", "label": f"EAD {period}", "format": "sar"},
                             {"key": "share", "label": "Share of book", "format": "pct"},
                             {"key": "ecl_before", "label": f"ECL {prior}", "format": "sar"},
                             {"key": "ecl_after", "label": f"ECL {period}", "format": "sar"},
                             {"key": "ecl_change", "label": "Change", "format": "sar"},
                             {"key": "coverage", "label": "Coverage", "format": "pct"}],
                 "rows": subs, "note": "Sub-sector limit: 7% of the corporate book (CP-1.3)."}
    rag = {"kind": "rag", "title": "Against policy", "items": [
        {"test": "Sector share of corporate EAD (CP-1.3)", "value": share, "format": "pct",
         "threshold": "limit 18%; amber above 15%", "status": "red" if share > 0.18 else ("amber" if share > 0.15 else "green"),
         "comment": "Closed to new names while above the limit." if share > 0.18 else ""},
        {"test": "Largest sub-sector share (CP-1.3)", "value": max(r["share"] for r in subs), "format": "pct",
         "threshold": "limit 7%; amber above 6%",
         "status": "red" if max(r["share"] for r in subs) > 0.07 else ("amber" if max(r["share"] for r in subs) > 0.06 else "green"),
         "comment": ""},
        {"test": "Stage 2 share against the book", "value": now["stage2_share"], "format": "pct",
         "threshold": f"amber above the book ({book['stage2_share'] * 100:.1f}%)",
         "status": "amber" if now["stage2_share"] > book["stage2_share"] else "green", "comment": ""}]}
    return [("Summary", [{"kind": "paragraph", "text": summary}, _kpis(now, before), rag]),
            ("Composition", [sub_table, stage_chart(sector, period, prior)]),
            ("Credit quality", [trend_chart(sector), drivers]),
            ("Movements", [{"kind": "paragraph", "text": (
                f"The largest increase came from {subs[0]['sub_sector']} "
                f"({subs[0]['ecl_change'] / 1e6:+.1f}m). Movements are split exactly across sub-sectors; the "
                "attention drawer in the Cockpit shows the same split by borrower.")}, ews_section(period, prior, sector)[1][2]]),
            ("Outlook", [{"kind": "bullets", "items": [
                ("Keep the sector closed to new names while it is above its CP-1.3 limit; review at the next committee."
                 if share > 0.18 else f"Hold new {sector.lower()} lending to strategic names: the sector is within its "
                 f"CP-1.3 limit ({share * 100:.1f}% against 18%) but its ECL and Stage 2 are rising fastest in the book."),
                "Re-rate the high and critical Early Warning names out of cycle (CP-3.2).",
                "Run the What-If construction PD stress before the Q3 pack and attach it to this review.",
            ]}])]


# ---------------------------------------------------------------- borrower


def borrower_sections(borrower_id: str = "CB01312", period: str = CORP_PERIOD) -> list[tuple[str, list[dict[str, Any]]]]:
    e = corp()
    b = borrowers()
    x = e[(e.borrower_id == borrower_id) & (e.reporting_quarter == period)]
    if x.empty:
        raise LookupError(f"{borrower_id} has no exposure at {period}")
    hist = b[b.borrower_id == borrower_id].sort_values("reporting_quarter").tail(8)
    r = hist.iloc[-1]
    name = str(r.borrower_name)
    ead, ecl = float(x.ead_sar_mn.sum()), float(x.ecl_sar_mn.sum())
    top = x.sort_values("ews_score", ascending=False).iloc[0]
    rec = (f"**{name} ({borrower_id})**, {r.sub_sector} in {r.region}, part of {r.group_name}. Exposure "
           f"{mn_words(ead)} across {len(x)} facilities, ECL {mn_words(ecl)}. Rated **{r.rating_current}** "
           f"(from {r.rating_previous} last quarter and {r.rating_at_origination} at origination; outlook "
           f"{str(r.rating_outlook).lower()}), on the watchlist for {int(r.quarters_on_watchlist)} quarters. "
           f"Early Warning: {str(top.ews_band)} ({int(top.ews_score)}).")
    recommendation = ("**Recommendation:** renew the working capital lines at the current limits for 12 months, no new "
                      "money, with a DSCR covenant reset and quarterly management accounts; keep the borrower on the "
                      "watchlist and re-rate out of cycle after the Q3 accounts.")
    fin = {"kind": "table", "title": "Financials, last 8 quarters (SAR m, ratios x)",
           "columns": [{"key": "q", "label": "Quarter", "format": "text"},
                       {"key": "rev", "label": "Revenue", "format": "num"},
                       {"key": "ebitda", "label": "EBITDA", "format": "num"},
                       {"key": "debt", "label": "Total debt", "format": "num"},
                       {"key": "lev", "label": "Leverage", "format": "num"},
                       {"key": "dscr", "label": "DSCR", "format": "num"},
                       {"key": "icr", "label": "Interest cover", "format": "num"},
                       {"key": "rating", "label": "Rating", "format": "rating"}],
           "rows": [{"q": h.reporting_quarter, "rev": float(h.revenue_sar_mn), "ebitda": float(h.ebitda_sar_mn),
                     "debt": float(h.total_debt_sar_mn), "lev": float(h.leverage_x), "dscr": float(h.dscr_x),
                     "icr": float(h.interest_cover_x), "rating": str(h.rating_current)} for h in hist.itertuples()]}
    ratio_chart = {"kind": "chart", "title": "DSCR and leverage, last 8 quarters",
                   "figure": {"data": [
                       {"type": "scatter", "mode": "lines+markers", "name": "DSCR (x)",
                        "x": list(hist.reporting_quarter), "y": [round(float(v), 3) for v in hist.dscr_x],
                        "marker": {"color": "#1F4E6B"}},
                       {"type": "scatter", "mode": "lines+markers", "name": "Leverage (x)",
                        "x": list(hist.reporting_quarter), "y": [round(float(v), 3) for v in hist.leverage_x],
                        "marker": {"color": "#C2410C"}}],
                       "layout": {"legend": {"orientation": "h"}}}}
    fac = {"kind": "table", "title": f"Facilities at {period}",
           "columns": [{"key": "id", "label": "Facility", "format": "text"},
                       {"key": "product", "label": "Product", "format": "text"},
                       {"key": "limit", "label": "Limit", "format": "sar"},
                       {"key": "ead", "label": "EAD", "format": "sar"},
                       {"key": "stage", "label": "Stage", "format": "int"},
                       {"key": "pd", "label": "PD 12m", "format": "pct"},
                       {"key": "lgd", "label": "LGD", "format": "pct"},
                       {"key": "ecl", "label": "ECL", "format": "sar"},
                       {"key": "coll", "label": "Collateral", "format": "sar"}],
           "rows": [{"id": f.facility_id, "product": str(f.product_type).replace("_", " "), "limit": sar(f.limit_sar_mn),
                     "ead": sar(f.ead_sar_mn), "stage": float(f.stage), "pd": float(f.pd_pit_12m),
                     "lgd": float(f.lgd_pct) / 100, "ecl": sar(f.ecl_sar_mn), "coll": sar(f.collateral_value_sar_mn or 0)}
                    for f in x.sort_values("ead_sar_mn", ascending=False).itertuples()]}
    rating_rag = {"kind": "rag", "title": "Policy checks", "items": [
        {"test": "Notches from origination (CP-3.3 SICR: two or more)", "value": float(r.rating_notches_from_origination),
         "format": "int", "threshold": "Stage 2 at -2 or worse", "status": "red" if r.rating_notches_from_origination <= -2 else "green",
         "comment": "Significant increase in credit risk." if r.rating_notches_from_origination <= -2 else ""},
        {"test": "DSCR covenant (CP-2.1: at least 1.25x)", "value": float(r.dscr_x), "format": "num",
         "threshold": "breach below 1.25x; CP-2.3 below 1.0x", "status": "red" if r.dscr_x < 1.0 else ("amber" if r.dscr_x < 1.25 else "green"),
         "comment": "Debt service below policy: unlikeliness to pay assessment (CP-2.3)." if r.dscr_x < 1.0 else ""},
        {"test": "Leverage covenant (CP-2.1: at most 4.0x)", "value": float(r.leverage_x), "format": "num",
         "threshold": "breach above 4.0x", "status": "red" if r.leverage_x > 4 else "green", "comment": ""},
        {"test": "Watchlist (CP-3.1)", "value": float(r.quarters_on_watchlist), "format": "int",
         "threshold": "quarterly review while on the watchlist", "status": "amber" if r.watchlist_flag else "green",
         "comment": str(r.watchlist_reason) if r.watchlist_flag else ""}]}
    return [("Request and recommendation", [{"kind": "paragraph", "text": rec}, {"kind": "callout", "tone": "warning",
                                                                                 "text": recommendation}]),
            ("Borrower profile", [{"kind": "kpis", "items": [
                {"label": "Exposure (EAD)", "value": sar(ead), "format": "sar"},
                {"label": "ECL", "value": sar(ecl), "format": "sar"},
                {"label": "Rating", "value": None, "format": "rating", "note": str(r.rating_current)},
                {"label": "Early Warning score", "value": float(top.ews_score), "format": "int",
                 "status": "red" if top.ews_band in ("high", "critical") else "amber"}]},
                {"kind": "bullets", "items": [f"Group: {r.group_name} ({r.group_id})", f"Sector: {r.sector}, {r.sub_sector}",
                                              f"Region: {r.region}; relationship tier {r.relationship_tier}",
                                              f"Rating driver: {r.rating_driver}"]}]),
            ("Financial analysis", [{"kind": "paragraph", "text": (
                f"Revenue {float(r.revenue_sar_mn):,.1f}m and EBITDA {float(r.ebitda_sar_mn):,.1f}m in the latest quarter "
                f"(margin {float(r.ebitda_margin_pct):.1f}%). DSCR fell to **{float(r.dscr_x):.2f}x** and leverage is "
                f"**{float(r.leverage_x):.2f}x** net debt to EBITDA; interest cover {float(r.interest_cover_x):.2f}x.")},
                ratio_chart, fin]),
            ("Facilities and security", [fac]),
            ("Risk rating", [rating_rag]),
            ("Early Warning", [{"kind": "paragraph", "text": (
                f"Highest facility score {int(top.ews_score)} ({top.ews_band}). Main reason: "
                f"{str(top.ews_reasons).split(';')[0].strip(' []') or 'see Early Warning'}.")}])]


# ------------------------------------------------------------------ retail


def retail_totals(month: str = RETAIL_PERIOD) -> dict[str, Any]:
    r = retail()
    q = r[r.reporting_month == month]
    ead, ecl = float(q.ead_sar_mn.sum()), float(q.ecl_sar_mn.sum())
    return {"period": month, "ead": ead, "ecl": ecl, "coverage": ecl / ead if ead else 0.0,
            "stage2_share": float(q[q.stage == 2].ead_sar_mn.sum()) / ead if ead else 0.0,
            "accounts": int(len(q)), "customers": int(q.customer_id.nunique())}


def retail_section(month: str = RETAIL_PERIOD) -> tuple[str, list[dict[str, Any]]]:
    r = retail()
    months = sorted(r.reporting_month.unique())
    prior = months[months.index(month) - 1]
    now, before = retail_totals(month), retail_totals(prior)
    q = r[r.reporting_month == month]
    by = q.groupby("product").agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum")).sort_values("ead", ascending=False)
    rows = [{"product": str(k).replace("_", " ").title(), "ead": sar(v.ead), "ecl": sar(v.ecl),
             "coverage": float(v.ecl / v.ead) if v.ead else 0.0} for k, v in by.iterrows()]
    text = (f"The retail book holds {mn_words(now['ead'])} of EAD over {now['accounts']:,} accounts at {month}, with ECL "
            f"of {mn_words(now['ecl'])} ({now['coverage'] * 100:.2f}% coverage). Stage 2 is "
            f"{now['stage2_share'] * 100:.1f}% of EAD ({before['stage2_share'] * 100:.1f}% at {prior}).")
    return "Retail book", [{"kind": "paragraph", "text": text},
                           {"kind": "table", "title": f"Retail book by product, {month}",
                            "columns": [{"key": "product", "label": "Product", "format": "text"},
                                        {"key": "ead", "label": "EAD", "format": "sar"},
                                        {"key": "ecl", "label": "ECL", "format": "sar"},
                                        {"key": "coverage", "label": "Coverage", "format": "pct"}], "rows": rows}]
