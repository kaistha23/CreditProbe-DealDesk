"""RAROC drift: every live facility's one-year RAROC at origination against now, with attribution (PLAN_R12 §1.6, I7/I8).

Sources (all registered Data Domains relations, read through `sources`):
  now          Early Warning `corp_exposure` at the latest quarter (limit, drawn, EAD, PD, LGD, collateral, band)
  rating now   ECL runs `ecl_facility`, the current run (the books at their as-of)
  origination  Origination `orig_facility` (margin, fees, rating, PD, FTP, tenor, collateral, hurdle, limit)
  promises     `promises.frame()` (deposits domain routing undertakings + dd_promise from approval conditions)
Parameters: desk_params (tax, opex, risk weights), capital, returns, ftp, relationship.book (Finance).

One-year RAROC (same basis as the R9 portfolio view, extended):
    D = u x L                       drawn;  EAD = L x (u + ccf x (1 - u))
    RAP = ((m x D + fees + xs) x (1 - opex) - PD x LGD x EAD - f x D) x (1 - tax)
    RAROC = RAP / (EAD x RW(rating) x k) + capital benefit
where m is the margin, fees the upfront fee per year of tenor, xs the cross-sell income the promises carry and
f the funding drift (the FTP change not passed through by the base-rate reset).

Attribution is sequential, origination -> now, in the order PD migration (PD and risk weight), LGD, funding,
fees, utilisation (utilisation and limit), unrealised cross-sell; the six components add up exactly to the drift.
"""
from __future__ import annotations

import functools
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk import desk_params, params
from backend.dealdesk.book import promises as _promises
from backend.dealdesk.book import sources

COMPONENTS = ("pd_migration", "lgd", "funding", "fees", "utilisation", "cross_sell")
LABELS = {"pd_migration": "PD migration", "lgd": "LGD", "funding": "Funding", "fees": "Fees",
          "utilisation": "Utilisation", "cross_sell": "Unrealised cross-sell"}


def book_params() -> dict[str, Any]:
    return params.rows("relationship")["book"]


def grades() -> list[str]:
    return [r["rating"] for r in params.rows("pd_master_scale")]


def notch(r: pd.Series) -> pd.Series:
    g = {x: i for i, x in enumerate(grades())}
    return r.map(lambda x: g.get(str(x).replace("CCC+", "CCC").replace("CCC-", "CCC"), np.nan))


def _ftp_now(tenor_years: pd.Series) -> pd.Series:
    f = params.rows("ftp")
    base = float(np.interp(f["reference_tenor"], f["tenors"], f["base"]["SAR"]))
    lp = np.interp(tenor_years.to_numpy(dtype=float), f["tenors"], f["liquidity_premium_bps"]["SAR"]) / 1e4
    return pd.Series(base + lp, index=tenor_years.index)


def raroc(m, fee, xs, fund, pd_, lgd, L, u, ccf, rw, k, opex, tax, benefit):
    D = u * L
    ead = L * (u + ccf * (1 - u))
    rap = ((m * D + fee + xs) * (1 - opex) - pd_ * lgd * ead - fund * D) * (1 - tax)
    cap = ead * rw * k
    return np.where(cap > 0, rap / np.where(cap > 0, cap, 1) + benefit, np.nan)


def _next_anniversary(orig: pd.Series, ref: pd.Timestamp) -> pd.Series:
    y = pd.Series(ref.year, index=orig.index)
    cand = pd.to_datetime(dict(year=y, month=orig.dt.month, day=orig.dt.day.clip(upper=28)))
    return cand.where(cand > ref, cand + pd.DateOffset(years=1))


@functools.lru_cache(maxsize=2)
def universe(ref: str | None = None) -> pd.DataFrame:
    """One row per live corporate facility at the as-of, with origination and now side by side."""
    e = sources.live("ews_exposure", ["facility_id", "borrower_id", "borrower_name", "reporting_quarter", "product_type", "sector",
                                      "sub_sector", "region", "relationship_tier", "limit_sar_mn", "drawn_sar_mn", "undrawn_sar_mn",
                                      "utilisation_pct", "ead_sar_mn", "stage", "dpd_days", "pd_pit_12m", "lgd_pct", "ecl_sar_mn",
                                      "collateral_value_sar_mn", "watchlist_flag", "rating_notches_moved", "covenant_breaches",
                                      "ews_score", "ews_reasons", "ews_band"])
    q = e.reporting_quarter.max()
    e = e[(e.reporting_quarter == q) & (e.limit_sar_mn > 0)].copy()
    o = sources.live("orig_facility")
    o = o[o.book == "corporate"].drop(columns=["book"]).rename(columns={"exposure_id": "facility_id", "obligor_id": "orig_obligor_id"})
    c = sources.live("ecl_facility", ["run_id", "book", "exposure_id", "rating", "pd_12m_pct"])
    c = c[c.book == "corporate"]
    c = c[c.run_id == c.run_id.max()][["exposure_id", "rating", "run_id"]].rename(columns={"exposure_id": "facility_id", "rating": "rating_now",
                                                                                         "run_id": "ecl_run"})
    cl = sources.live("cls_exposure", ["book", "exposure_id", "watch_status", "sicr_flag", "restructured_flag"])
    cl = cl[cl.book == "corporate"].drop(columns=["book"]).rename(columns={"exposure_id": "facility_id"})
    f = e.merge(o, on="facility_id", how="inner").merge(c, on="facility_id", how="left").merge(cl, on="facility_id", how="left")
    f["as_of_quarter"] = q
    as_of = pd.Timestamp(f.as_of_date.iloc[0]) if len(f) else pd.Timestamp(date.today())
    basis = str(book_params().get("reference_date", "as_of"))
    refd = pd.Timestamp(ref) if ref else (pd.Timestamp(date.today()) if basis == "today" else as_of)
    f["ref_date"] = refd.date().isoformat()
    od = pd.to_datetime(f.orig_date)
    maturity = od + pd.to_timedelta(f.tenor_months * 30.4375, unit="D")
    ann = _next_anniversary(od, refd)
    renew = ann.where((maturity <= refd) | (ann < maturity), maturity)
    f["renewal_date"] = renew.dt.date.astype(str)
    f["renewal_kind"] = np.where((maturity > refd) & (renew == maturity), "Maturity", "Annual review")
    f["months_to_renewal"] = ((renew - refd).dt.days / 30.4375).round(1)
    f["months_elapsed"] = ((refd - od).dt.days / 30.4375).round(1)
    f["notches"] = notch(f.rating_now) - notch(f.orig_rating)
    return f.reset_index(drop=True)


def _inputs(f: pd.DataFrame, xs_o: pd.Series, xs_n: pd.Series) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bp = book_params()
    dp = desk_params.rows()
    ret = params.rows("returns")
    k = float(params.rows("capital")["capital_ratio_target"])
    common = {"k": k, "opex": float(dp["opex_to_income"]), "tax": float(dp["corporate_tax"]), "benefit": float(ret["capital_benefit_rate"])}
    rwm = dp["risk_weight_by_rating"]
    L_n = f.limit_sar_mn
    u_n = (f.drawn_sar_mn / L_n).clip(0, 1)
    und = (f.limit_sar_mn - f.drawn_sar_mn).clip(lower=0)
    ccf = ((f.ead_sar_mn - f.drawn_sar_mn) / und.where(und > 1e-9)).clip(0, 1).fillna(0.5)
    u_o = float(bp["utilisation_at_origination"])
    ead_o = f.orig_limit_sar_mn * (u_o + ccf * (1 - u_o))
    h = float(bp["lgd_collateral_haircut"])
    lgd_n = (f.lgd_pct / 100).clip(0.05, 1.0)
    cov_n = (f.collateral_value_sar_mn / f.ead_sar_mn.where(f.ead_sar_mn > 0)).clip(0, 1).fillna(0)
    cov_o = (f.orig_collateral_sar_mn / ead_o.where(ead_o > 0)).clip(0, 1).fillna(0)
    lgd_o = (lgd_n * (1 - h * cov_o) / (1 - h * cov_n)).clip(0.05, 1.0)
    tenor_y = (f.tenor_months / 12).clip(lower=1)
    fee_o = f.orig_fees_sar_mn / tenor_y
    fee_n = fee_o.where(f.months_elapsed < f.tenor_months.clip(lower=12), 0.0)
    fund_n = (_ftp_now(f.tenor_months / 12) - f.ftp_pct / 100) * (1 - float(bp["ftp_pass_through"]))
    orig = {"m": f.orig_margin_pct / 100, "fee": fee_o, "xs": xs_o, "fund": 0.0 * fee_o, "pd_": f.orig_pd_pct / 100, "lgd": lgd_o,
            "L": f.orig_limit_sar_mn, "u": pd.Series(u_o, index=f.index), "ccf": ccf, "rw": f.orig_rating.map(rwm).fillna(1.0)}
    now = {"m": f.orig_margin_pct / 100, "fee": fee_n, "xs": xs_n, "fund": fund_n, "pd_": f.pd_pit_12m.clip(0, 1), "lgd": lgd_n,
           "L": L_n, "u": u_n, "ccf": ccf, "rw": f.rating_now.map(rwm).fillna(f.orig_rating.map(rwm)).fillna(1.0)}
    return orig, now, common


#: which inputs each component moves, in attribution order
STEPS = {"pd_migration": ("pd_", "rw"), "lgd": ("lgd",), "funding": ("fund",), "fees": ("fee",), "utilisation": ("u", "L"),
         "cross_sell": ("xs",)}


def attribute(f: pd.DataFrame, xs_o: pd.Series, xs_n: pd.Series) -> pd.DataFrame:
    orig, now, common = _inputs(f, xs_o, xs_n)
    cur = dict(orig)
    out = pd.DataFrame(index=f.index)
    r0 = raroc(**cur, **common)
    out["raroc_orig"] = r0
    out["raroc_orig_deal"] = raroc(**{**cur, "xs": 0 * cur["fee"]}, **common)
    prev = r0
    for comp, keys in STEPS.items():
        for kk in keys:
            cur[kk] = now[kk]
        r = raroc(**cur, **common)
        out[f"d_{comp}"] = r - prev
        prev = r
    out["raroc_now"] = prev
    out["raroc_now_deal"] = raroc(**{**cur, "xs": 0 * cur["fee"]}, **common)
    out["drift"] = out.raroc_now - out.raroc_orig
    # the linear pieces the repricing solver needs: RAROC = a x margin + b at today's inputs
    D = now["u"] * now["L"]
    ead = now["L"] * (now["u"] + now["ccf"] * (1 - now["u"]))
    capd = ead * now["rw"] * common["k"]
    out["slope_margin"] = (D * (1 - common["opex"]) * (1 - common["tax"]) / capd.where(capd > 0)).fillna(0)
    out["slope_lgd"] = (-(now["pd_"] * ead) * (1 - common["tax"]) / capd.where(capd > 0)).fillna(0)
    out["slope_fee"] = ((1 - common["opex"]) * (1 - common["tax"]) / capd.where(capd > 0)).fillna(0)
    out["capital_now_sar_mn"] = capd
    out["lgd_now"] = now["lgd"]
    out["lgd_orig"] = orig["lgd"]
    out["util_now"] = now["u"]
    out["fee_now_sar_mn"] = now["fee"]
    out["fund_drift_pct"] = now["fund"]
    out["xs_promised_sar_mn"] = xs_o
    out["xs_realised_sar_mn"] = xs_n
    return out


@functools.lru_cache(maxsize=2)
def frame(ref: str | None = None) -> pd.DataFrame:
    """The universe with drift attribution and hurdle flags (cached per reference date)."""
    f = universe(ref).copy()
    pr = _promises.by_facility(f)
    f = f.merge(pr, on="facility_id", how="left")
    for c in ("xs_promised_sar_mn", "xs_realised_sar_mn"):
        f[c] = f[c].fillna(0.0)
    a = attribute(f, f.pop("xs_promised_sar_mn"), f.pop("xs_realised_sar_mn"))
    f = pd.concat([f, a], axis=1)
    ret = params.rows("returns")
    h_sec = ret.get("hurdle_sector", {})
    default_h = f.sector.map(lambda s: float(h_sec.get(s, ret["hurdle"]["Corporate Banking"])))
    f["hurdle"] = (f.hurdle_rate_pct / 100).where(f.hurdle_rate_pct.notna(), default_h)
    f["hurdle_source"] = np.where(f.hurdle_rate_pct.notna(), "origination", "returns")
    f["above_orig"] = f.raroc_orig >= f.hurdle
    f["above_now"] = f.raroc_now >= f.hurdle
    f["main_driver"] = f[[f"d_{c}" for c in COMPONENTS]].idxmin(axis=1).str[2:]
    # defaulted exposures (Stage 3, PD 100%) are in workout: their RAROC is not a pricing number and is kept out of the book drift
    f["defaulted"] = (f.stage >= 3) | (f.pd_pit_12m >= 0.999)
    return f


def drift_rows(f: pd.DataFrame) -> list[dict[str, Any]]:
    """The dd_raroc_drift publication (contract columns): one row per book facility and period, RAROC in %, drift in points.
    Deal Desk deals' rows are their owners' (the deal's own drift row); the Book does not echo them."""
    if "source" in f.columns:
        f = f[f.source != "deal_desk"]
    t = pd.DataFrame({
        "drift_id": "RD-" + f.facility_id + "-" + f.as_of_quarter.astype(str), "facility_id": f.facility_id,
        "proposal_id": f["proposal_id"] if "proposal_id" in f.columns else None, "obligor_id": f.borrower_id,
        "origination_date": f.orig_date.astype(str), "raroc_orig_pct": f.raroc_orig * 100, "raroc_now_pct": f.raroc_now * 100,
        "hurdle_pct": f.hurdle * 100, "drift_pp": f.drift * 100,
        **{f"attr_{'pd' if c == 'pd_migration' else c}_pp": f[f"d_{c}"] * 100 for c in COMPONENTS},
        "renewal_date": f.renewal_date, "reporting_quarter": f.as_of_quarter.astype(str)})
    return t.replace({np.nan: None}).to_dict("records")


def _cut(f: pd.DataFrame, col: str) -> list[dict[str, Any]]:
    w = f.ead_sar_mn
    g = f.assign(w_ao=w * f.above_orig, w_an=w * f.above_now, **{f"w_{c}": w * f[f"d_{c}"] for c in COMPONENTS},
                 w_drift=w * f.drift).groupby(col)
    t = g.agg(ead_sar_mn=("ead_sar_mn", "sum"), facilities_count=("facility_id", "count"), w_ao=("w_ao", "sum"), w_an=("w_an", "sum"),
              raroc_orig=("raroc_orig", "median"), raroc_now=("raroc_now", "median"), hurdle=("hurdle", "mean"), w_drift=("w_drift", "sum"),
              **{f"w_{c}": (f"w_{c}", "sum") for c in COMPONENTS}).reset_index()
    t["share_above_orig"] = t.w_ao / t.ead_sar_mn
    t["share_above_now"] = t.w_an / t.ead_sar_mn
    t["drift"] = t.w_drift / t.ead_sar_mn
    for c in COMPONENTS:
        t[c] = t[f"w_{c}"] / t.ead_sar_mn
    t = t.drop(columns=[x for x in t.columns if x.startswith("w_")]).rename(columns={col: "group"})
    return t.replace({np.nan: None}).to_dict("records")


def summary(ref: str | None = None) -> dict[str, Any]:
    """The RAROC drift view (renamed from Portfolio RAROC at origination): book totals, attribution and cuts."""
    fa = frame(ref)
    f = fa[~fa.defaulted]
    w = f.ead_sar_mn
    total = float(w.sum())
    share_o = float((w * f.above_orig).sum() / total) if total else 0.0
    share_n = float((w * f.above_now).sum() / total) if total else 0.0
    attr = [{"component": c, "label": LABELS[c], "value": float((w * f[f"d_{c}"]).sum() / total) if total else 0.0} for c in COMPONENTS]
    decayed = f[f.above_orig & ~f.above_now]
    by_sector = _cut(f, "sector")
    worst = sorted(by_sector, key=lambda r: r["share_above_now"])[:2]
    order = grades()
    by_rating = sorted(_cut(f, "orig_rating"), key=lambda r: order.index(r["group"]) if r["group"] in order else 99)
    f = f.assign(vintage=f.orig_date.astype(str).str[:4])
    top = sorted(attr, key=lambda r: r["value"])[:2]
    drift_avg = float((w * f.drift).sum() / total) if total else 0.0
    text = (f"{share_o:.0%} of the corporate book by EAD cleared its hurdle at origination; now {share_n:.0%} does. "
            f"The EAD-weighted one-year RAROC has moved {drift_avg * 100:+.1f} points since origination, mostly from "
            f"{LABELS[top[0]['component']]} ({top[0]['value'] * 100:+.1f} points) and {LABELS[top[1]['component']]} "
            f"({top[1]['value'] * 100:+.1f} points). {len(decayed):,} facilities (SAR {decayed.ead_sar_mn.sum():,.0f}m EAD) cleared "
            f"at origination and no longer do, mostly in {', '.join(r['group'] for r in worst)}. "
            f"{int(fa.defaulted.sum()):,} defaulted facilities (SAR {fa[fa.defaulted].ead_sar_mn.sum():,.0f}m EAD) are in workout and "
            f"left out of the drift.")
    return {"as_of": str(f.as_of_quarter.iloc[0]) if len(f) else "", "ref_date": str(f.ref_date.iloc[0]) if len(f) else "",
            "facilities": int(len(f)), "ead_sar_mn": total,
            "defaulted_count": int(fa.defaulted.sum()), "defaulted_ead_sar_mn": float(fa[fa.defaulted].ead_sar_mn.sum()),
            "share_above_hurdle_orig": share_o, "share_above_hurdle_now": share_n,
            "median_raroc_orig": float(f.raroc_orig.median()), "median_raroc_now": float(f.raroc_now.median()),
            "drift": drift_avg, "attribution": attr,
            "mean_raroc_orig": float((w * f.raroc_orig).sum() / total) if total else None,
            "mean_raroc_now": float((w * f.raroc_now).sum() / total) if total else None,
            "by_sector": by_sector, "by_rating": by_rating, "by_vintage": _cut(f, "vintage"), "by_product": _cut(f, "product_type"),
            "decayed_count": int(len(decayed)), "decayed_ead_sar_mn": float(decayed.ead_sar_mn.sum()), "summary": text,
            "sources": sources.lineage(), "method": __doc__.split("\n\n")[2].strip()}
