"""Build the scorecard data domain (scorecard-saudi-v1), keyed to the spine.

Three scorecards, each scored on real book rows:

  RET-APP  Retail application scorecard   account-month (accounts opened in the last 12 months)
  RET-BEH  Retail behavioural scorecard   account-month (live, not in default)
  SME-ANN  SME scorecard                  borrower-quarter (the SME segment of the corporate book)

Every row carries the book's own identifiers and period (customer_id RC######, account_id RA#######,
borrower_id CB#####) and its characteristics are the book's, the Bureau domain's and the Open Banking
domain's values for that owner and period. The outcome ("default within 12 months") is generated
deterministically from those characteristics plus hidden factors (the books hold a point-in-time default
flag, which is not a performance window), with an explicit drift schedule so that a validation has
something to find. Scores come from scorecards fitted here (WoE, IV, points) on the development sample.

Run:  .venv/bin/python -m backend.scorecard_v5.domain.build
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit, logit, ndtri
from sklearn.linear_model import LogisticRegression

from backend.scorecard_v5 import paths
from backend.scorecard_v5.domain import binning

BUILD_VERSION = "1.0.0"
MASTER_SEED = 20261011
PDO, BASE_SCORE, BASE_ODDS = 40.0, 600.0, 50.0       # 600 points at 50:1 good:bad, 40 points to double the odds
FACTOR = PDO / math.log(2)
OFFSET = BASE_SCORE - FACTOR * math.log(BASE_ODDS)
SME_REVENUE_CUT = 30.0   # SAR million: the SME segment is the borrowers whose latest-quarter revenue is below this

# ----------------------------------------------------------------------------- scorecards

SCORECARDS: dict[str, dict[str, Any]] = {
    "RET-APP": {
        "name": "Retail Application Scorecard", "version": "2.1", "type": "application", "segment": "Retail",
        "book": "retail", "owner_key": "customer_id", "unit_key": "account_id", "period_col": "reporting_month",
        "frequency": "monthly", "target_odr": 0.024,
        "development": ("2025-01", "2025-04"), "monitoring": ("2025-05", "2025-08"),
        "segment_col": "product", "has_overrides": True, "sample_pct": 100,
        "description": "Scores new retail accounts at the point of decision: bureau, Open Banking and application data.",
    },
    "RET-BEH": {
        "name": "Retail Behavioural Scorecard", "version": "3.0", "type": "behavioural", "segment": "Retail",
        "book": "retail", "owner_key": "customer_id", "unit_key": "account_id", "period_col": "reporting_month",
        "frequency": "monthly", "target_odr": 0.031,
        "development": ("2025-01", "2025-04"), "monitoring": ("2025-05", "2025-08"),
        "segment_col": "product", "has_overrides": False, "sample_pct": 35,
        "description": "Scores the live retail book every month on account conduct, bureau and Open Banking data.",
    },
    "SME-ANN": {
        "name": "SME Scorecard", "version": "1.4", "type": "application", "segment": "SME",
        "book": "corporate", "owner_key": "borrower_id", "unit_key": "borrower_id", "period_col": "reporting_quarter",
        "frequency": "quarterly", "target_odr": 0.030,
        "development": ("2021Q4", "2023Q2"), "monitoring": ("2023Q3", "2025Q2"),
        "segment_col": "sector", "has_overrides": True, "sample_pct": 100,
        "description": "Grades SME borrowers (revenue under SAR 30 million) on financials, qualitative score, bureau and Open Banking.",
    },
}

#: (name, label, kind) per scorecard. A variable not selected by the fit stays a candidate in the domain.
CANDIDATES: dict[str, list[tuple[str, str, str]]] = {
    "RET-APP": [
        ("bureau_score", "Bureau score", "numeric"), ("enquiries_3m", "Bureau enquiries, last 3 months", "numeric"),
        ("external_facilities", "External facilities", "numeric"), ("external_leverage_x", "External leverage (x)", "numeric"),
        ("employment_type", "Employment type", "categorical"), ("product", "Product", "categorical"),
        ("origination_channel", "Origination channel", "categorical"), ("region", "Region", "categorical"),
        ("customer_segment", "Customer segment", "categorical"), ("tenure_months", "Customer tenure (months)", "numeric"),
        ("limit_sar_k", "Credit limit (SAR thousand)", "numeric"), ("salaried_flag", "Salary credited (Open Banking)", "numeric"),
        ("balance_buffer_months", "Balance buffer (months)", "numeric"), ("returned_payments_3m", "Returned payments, last 3 months", "numeric"),
    ],
    "RET-BEH": [
        ("utilisation_pct", "Utilisation (%)", "numeric"), ("dpd_days", "Days past due", "numeric"),
        ("months_on_book", "Months on book", "numeric"), ("behaviour_score", "Behaviour score (book)", "numeric"),
        ("bureau_score", "Bureau score", "numeric"), ("external_dpd_days", "External days past due", "numeric"),
        ("enquiries_3m", "Bureau enquiries, last 3 months", "numeric"), ("returned_payments_3m", "Returned payments, last 3 months", "numeric"),
        ("salary_interruption_flag", "Salary interruption (Open Banking)", "numeric"),
        ("balance_buffer_months", "Balance buffer (months)", "numeric"), ("product", "Product", "categorical"),
        ("employment_type", "Employment type", "categorical"), ("delinquency_bucket", "Delinquency bucket", "categorical"),
    ],
    "SME-ANN": [
        ("leverage_x", "Leverage (x)", "numeric"), ("dscr_x", "Debt service cover (x)", "numeric"),
        ("interest_cover_x", "Interest cover (x)", "numeric"), ("current_ratio_x", "Current ratio (x)", "numeric"),
        ("ebitda_margin_pct", "EBITDA margin (%)", "numeric"),
        ("return_on_assets_pct", "Return on assets (%)", "numeric"), ("cash_conversion_pct", "Cash conversion (%)", "numeric"),
        ("revenue_growth_pct", "Revenue growth, year on year (%)", "numeric"), ("qualitative_score", "Qualitative score", "numeric"),
        ("enquiries_q", "Bureau enquiries, quarter", "numeric"), ("external_dpd_days", "External days past due", "numeric"),
        ("balance_buffer_months", "Balance buffer (months)", "numeric"),
        ("returned_payments_q", "Returned payments, quarter", "numeric"), ("sector", "Sector", "categorical"),
        ("relationship_tier", "Relationship tier", "categorical"), ("region", "Region", "categorical"),
    ],
}

#: Drift planted in the generating process, by period offset into the monitoring window. Tests and the
#: manifest read it; nothing on a screen does.
PLANTED = {
    "RET-APP": {"level_shift": [0.0, 0.0, 0.03, 0.08], "partner_extra_logit": 0.35, "partner_from": "2025-08",
                "enquiry_loading_decay_from": "2025-06"},
    "RET-BEH": {"level_shift": [0.15, 0.35, 0.60, 0.85], "open_months_shift_per_month": 0.04},
    "SME-ANN": {"source": "book borrower default path, rolled forward four quarters", "sector_stress": ["Construction", "Real Estate"]},
}

# ----------------------------------------------------------------------------- helpers


def _u(keys: pd.Series, salt: str) -> np.ndarray:
    """A deterministic uniform in (0,1) per key (independent of row order and sampling)."""
    h = pd.util.hash_pandas_object(keys.astype(str) + "|" + salt + f"|{MASTER_SEED}", index=False).to_numpy(dtype=np.uint64)
    return np.clip((h >> np.uint64(11)).astype(np.float64) / float(1 << 53), 1e-12, 1 - 1e-12)


def _normal(keys: pd.Series, salt: str) -> np.ndarray:
    return ndtri(_u(keys, salt))


def _std(x: pd.Series, dev: pd.Series) -> np.ndarray:
    med = float(np.nanmedian(x[dev]))
    iqr = float(np.nanpercentile(x[dev], 75) - np.nanpercentile(x[dev], 25)) or 1.0
    return np.clip((x.to_numpy(dtype=float) - med) / (iqr / 1.349), -3.0, 3.0)


def _periods(frame: pd.DataFrame, col: str) -> list[str]:
    return sorted(frame[col].unique())


def _add(periods: list[str], p: str, n: int) -> str | None:
    i = periods.index(p) + n
    return periods[i] if 0 <= i < len(periods) else None


# ----------------------------------------------------------------------------- source frames


def _retail_frame() -> pd.DataFrame:
    lake = paths.LAKE / paths.RETAIL_RELEASE
    acc = pd.read_parquet(lake / "retail_account_month.parquet", columns=[
        "account_id", "customer_id", "reporting_month", "product", "origination_channel", "months_on_book", "customer_segment",
        "employment_type", "region", "limit_sar_mn", "utilisation_pct", "default_flag", "dpd_days", "delinquency_bucket",
        "pd_pit_12m", "behaviour_score"])
    cust = pd.read_parquet(lake / "retail_customer_month.parquet", columns=["customer_id", "reporting_month", "tenure_months"])
    bur = pd.read_parquet(paths.EXTERNAL / paths.BUREAU / "bureau_retail_month.parquet", columns=[
        "customer_id", "reporting_month", "bureau_score", "external_dpd_days", "external_facilities", "external_leverage_x", "enquiries_3m"])
    ob = pd.read_parquet(paths.EXTERNAL / paths.OPEN_BANKING / "openbanking_retail_month.parquet", columns=[
        "customer_id", "reporting_month", "salaried_flag", "salary_interruption_flag", "inflow_trend_pct", "balance_buffer_months",
        "returned_payments_3m"])
    f = acc.merge(cust, on=["customer_id", "reporting_month"], how="left").merge(bur, on=["customer_id", "reporting_month"], how="left") \
        .merge(ob, on=["customer_id", "reporting_month"], how="left")
    f["limit_sar_k"] = f["limit_sar_mn"] * 1000.0
    return f


def _sme_frame() -> pd.DataFrame:
    lake = paths.LAKE / paths.CORP_RELEASE
    b = pd.read_parquet(lake / "corp_borrower_quarter.parquet", columns=[
        "borrower_id", "reporting_quarter", "sector", "region", "relationship_tier", "revenue_sar_mn", "leverage_x", "dscr_x",
        "interest_cover_x", "current_ratio_x", "quick_ratio_x", "ebitda_margin_pct", "return_on_assets_pct", "cash_conversion_pct",
        "qualitative_score"])
    fac = pd.read_parquet(lake / "corp_facility_quarter.parquet", columns=["borrower_id", "reporting_quarter", "default_flag", "pd_pit_12m", "ead_sar_mn"])
    g = fac.groupby(["borrower_id", "reporting_quarter"]).agg(book_default=("default_flag", "max"), pd_pit_12m=("pd_pit_12m", "mean"),
                                                             ead_sar_mn=("ead_sar_mn", "sum")).reset_index()
    bur = pd.read_parquet(paths.EXTERNAL / paths.BUREAU / "bureau_corp_quarter.parquet", columns=[
        "borrower_id", "reporting_quarter", "external_dpd_days", "enquiries_q"])
    ob = pd.read_parquet(paths.EXTERNAL / paths.OPEN_BANKING / "openbanking_corp_quarter.parquet", columns=[
        "borrower_id", "reporting_quarter", "inflow_trend_pct", "balance_buffer_months", "returned_payments_q"])
    f = b.merge(g, on=["borrower_id", "reporting_quarter"], how="left").merge(bur, on=["borrower_id", "reporting_quarter"], how="left") \
        .merge(ob, on=["borrower_id", "reporting_quarter"], how="left")
    qs = sorted(f.reporting_quarter.unique())
    lag = f[["borrower_id", "reporting_quarter", "revenue_sar_mn"]].copy()
    lag["reporting_quarter"] = lag.reporting_quarter.map(lambda q: _add(qs, q, 4))
    lag = lag.dropna(subset=["reporting_quarter"]).rename(columns={"revenue_sar_mn": "rev_lag"})
    f = f.merge(lag, on=["borrower_id", "reporting_quarter"], how="left")
    f["revenue_growth_pct"] = (f.revenue_sar_mn / f.rev_lag - 1.0) * 100.0
    latest = f[f.reporting_quarter == qs[-1]].set_index("borrower_id").revenue_sar_mn
    sme = set(latest[latest < SME_REVENUE_CUT].index)
    f = f[f.borrower_id.isin(sme)].copy()
    # The corporate book's first quarter is its burn-in: the qualitative score, cash conversion and current ratio are
    # initial constants there. It is not scored.
    f = f[f.reporting_quarter != qs[0]].copy()
    # the book's own borrower default path (any facility in default), the anchor of the SME outcome path
    f.attrs["book_default_path"] = f.groupby("reporting_quarter").book_default.mean().to_dict()
    return f.drop(columns=["rev_lag"])


# ----------------------------------------------------------------------------- the generating process


def _drivers(sid: str, f: pd.DataFrame, dev: pd.Series) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Standardised, signed drivers of the latent risk (positive = riskier). Returns (z, the parts)."""
    P: dict[str, np.ndarray] = {}
    cat = lambda col, m: f[col].map(m).fillna(0.0).to_numpy(dtype=float)  # noqa: E731
    if sid == "RET-APP":
        P["bureau"] = -0.95 * _std(f.bureau_score, dev)
        P["enquiries"] = 0.30 * _std(f.enquiries_3m, dev)
        P["ext_leverage"] = 0.22 * _std(f.external_leverage_x, dev)
        P["returned"] = 0.26 * _std(f.returned_payments_3m, dev)
        P["buffer"] = -0.20 * _std(f.balance_buffer_months, dev)
        P["employment"] = cat("employment_type", {"Self-employed": 0.35, "Non-salaried": 0.55, "Salaried-Private": 0.05, "Salaried-Government": -0.25})
        P["product"] = cat("product", {"Credit Card": 0.25, "Buy Now Pay Later": 0.55, "Personal Finance": 0.20, "Auto Finance": -0.05, "Mortgage": -0.35})
        P["channel"] = cat("origination_channel", {"Partner": 0.20, "Digital": 0.05, "Branch": -0.10})
        P["tenure"] = -0.18 * _std(f.tenure_months, dev)
    elif sid == "RET-BEH":
        P["dpd"] = 0.65 * np.log1p(f.dpd_days.to_numpy(dtype=float)) / 2.0
        P["util"] = 0.50 * _std(f.utilisation_pct, dev)
        P["behaviour"] = -0.80 * _std(f.behaviour_score, dev)
        P["bureau"] = -0.45 * _std(f.bureau_score, dev)
        P["ext_dpd"] = 0.35 * np.log1p(f.external_dpd_days.to_numpy(dtype=float)) / 2.0
        P["returned"] = 0.30 * _std(f.returned_payments_3m, dev)
        P["salary"] = 0.45 * f.salary_interruption_flag.fillna(0).to_numpy(dtype=float)
        P["mob"] = -0.15 * _std(f.months_on_book, dev)
        P["product"] = cat("product", {"Credit Card": 0.25, "Buy Now Pay Later": 0.50, "Personal Finance": 0.20, "Auto Finance": -0.05, "Mortgage": -0.40})
    else:
        P["leverage"] = 0.55 * _std(f.leverage_x, dev)
        P["dscr"] = -0.55 * _std(f.dscr_x, dev)
        P["icr"] = -0.25 * _std(f.interest_cover_x, dev)
        P["margin"] = -0.30 * _std(f.ebitda_margin_pct, dev)
        P["quality"] = -0.55 * _std(f.qualitative_score, dev)
        P["growth"] = -0.18 * np.nan_to_num(_std(f.revenue_growth_pct.fillna(f.revenue_growth_pct.median()), dev))
        P["returned"] = 0.30 * _std(f.returned_payments_q, dev)
        P["ext_dpd"] = 0.35 * np.log1p(f.external_dpd_days.to_numpy(dtype=float)) / 2.0
        P["enquiries"] = 0.15 * _std(f.enquiries_q, dev)
        P["sector"] = cat("sector", {"Construction": 0.35, "Real Estate": 0.30, "Hospitality": 0.25, "Retail Trade": 0.15, "Healthcare": -0.20,
                                      "Power and Utilities": -0.30, "Telecommunications": -0.20})
    strength = STRENGTH[sid]
    P = {k: v * strength for k, v in P.items()}
    return sum(P.values()), P


def _outcomes(sid: str, f: pd.DataFrame, periods: list[str], spec: dict[str, Any]) -> pd.DataFrame:
    """Add the latent risk, the 12-month default outcome (where its window has closed) and the overrides."""
    pc, unit, owner = spec["period_col"], spec["unit_key"], spec["owner_key"]
    horizon = 12 if spec["frequency"] == "monthly" else 4
    d0, d1 = spec["development"]
    dev = (f[pc] >= d0) & (f[pc] <= d1)
    z_base, parts = _drivers(sid, f, dev)
    # a persistent hidden factor per customer / borrower (what the scorecard cannot see)
    hidden = 0.85 * _normal(f[owner], "hidden-owner") + 0.45 * _normal(f[unit].astype(str) + f[pc], "hidden-row")
    pidx = f[pc].map({p: i for i, p in enumerate(periods)}).to_numpy()
    mat_last = len(periods) - 1 - horizon                      # last period whose window has closed
    shift = np.zeros(len(f))
    plan = PLANTED[sid]
    m0 = periods.index(spec["monitoring"][0])
    if sid in ("RET-APP", "RET-BEH"):
        for k, s in enumerate(plan["level_shift"]):
            shift[pidx == m0 + k] = s
        if sid == "RET-BEH":
            late = pidx > m0 + 3
            shift[late] = plan["level_shift"][-1] + plan["open_months_shift_per_month"] * (pidx[late] - (m0 + 3))
        if sid == "RET-APP":
            partner_from = periods.index(plan["partner_from"])
            shift += np.where((f.origination_channel == "Partner").to_numpy() & (pidx >= partner_from), plan["partner_extra_logit"], 0.0)
            decay = periods.index(plan["enquiry_loading_decay_from"])
            enq_part = parts["enquiries"]
            shift += np.where(pidx >= decay, -enq_part * np.minimum((pidx - decay + 1) / 3.0, 1.0), 0.0)
    else:
        # the SME path follows the book's own borrower default rate over the next four quarters
        path = f.attrs["book_default_path"]
        fwd = {}
        for i, p in enumerate(periods):
            nxt = [path[periods[j]] for j in range(i + 1, min(i + 1 + horizon, len(periods)))]
            fwd[p] = float(np.mean(nxt)) if nxt else float(path[p])
        dev_rate = float(np.mean([fwd[p] for p in periods if d0 <= p <= d1]))
        shift = 0.6 * np.array(f[pc].map(lambda p: logit(fwd[p] * 0.9) - logit(dev_rate * 0.9)), dtype=float)
        stress = f.sector.isin(plan["sector_stress"]).to_numpy() & (pidx >= periods.index("2023Q3"))
        shift += np.where(stress, 0.30, 0.0)
    # overrides (application-type scorecards): decided on the score, outcome worse where the override was an upgrade
    z = z_base + hidden + shift
    if spec["has_overrides"]:
        z = z  # the override uplift is applied after grades exist (see _overrides)
    # the intercept makes the development sample's default rate equal to the target
    lo, hi = -12.0, 4.0
    zd = z[dev.to_numpy()]
    for _ in range(60):
        mid = (lo + hi) / 2
        if expit(zd + mid).mean() > spec["target_odr"]:
            hi = mid
        else:
            lo = mid
    a0 = (lo + hi) / 2
    f = f.copy()
    f["_z"] = z + a0
    f["_pidx"] = pidx
    f["matured"] = pidx <= mat_last
    return f


def _label_sample(f: pd.DataFrame, spec: dict[str, Any]) -> pd.Series:
    pc = spec["period_col"]
    d0, d1 = spec["development"]
    m0, m1 = spec["monitoring"]
    return np.select([(f[pc] >= d0) & (f[pc] <= d1), (f[pc] >= m0) & (f[pc] <= m1)], ["development", "monitoring"], default="open")


# ----------------------------------------------------------------------------- the scorecard fit


def _fit(sid: str, f: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    dev = f[f["sample"] == "development"]
    y = dev["y12"].to_numpy(dtype=float)
    fitted: dict[str, dict[str, Any]] = {}
    for name, label, kind in CANDIDATES[sid]:
        fit = binning.fit_categorical(dev[name], y, name) if kind == "categorical" else binning.fit_numeric(dev[name], y, name)
        if fit is None:
            continue
        fit.update({"name": name, "label": label})
        fitted[name] = fit
    # selection: IV >= 0.02, then drop the weaker of any pair of WoE variables correlated above 0.70
    woe = {n: np.asarray([fitted[n]["bins"][k]["woe"] for k in binning.assign(fitted[n], dev[n])]) for n in fitted}
    chosen = [n for n in sorted(fitted, key=lambda n: -fitted[n]["iv"]) if fitted[n]["iv"] >= 0.02]
    keep: list[str] = []
    for n in chosen:
        if all(abs(np.corrcoef(woe[n], woe[k])[0, 1]) < 0.70 for k in keep):
            keep.append(n)
    # the coefficient on every WoE (ln good/bad) must be positive; drop the offender and refit
    while True:
        X = np.column_stack([woe[n] for n in keep])
        lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(X, 1.0 - y)    # model ln(odds of good)
        bad_sign = [n for n, c in zip(keep, lr.coef_[0]) if c <= 0]
        if not bad_sign:
            break
        keep.remove(min(bad_sign, key=lambda n: fitted[n]["iv"]))
    coef = dict(zip(keep, map(float, lr.coef_[0])))
    intercept = float(lr.intercept_[0])
    n = len(keep)
    variables = []
    for name in keep:
        v = fitted[name]
        for b in v["bins"]:
            b["points"] = FACTOR * (coef[name] * b["woe"] + intercept / n) + OFFSET / n
        variables.append({"name": name, "label": v["label"], "type": v["type"], "iv": v["iv"], "coef": coef[name],
                          "direction": v["direction"], "bins": v["bins"]})
    others = [{"name": nme, "label": fitted[nme]["label"], "iv": fitted[nme]["iv"], "type": fitted[nme]["type"]} for nme in fitted if nme not in keep]
    return {"variables": variables, "excluded": others, "intercept": intercept}


def _score(spec_vars: list[dict[str, Any]], f: pd.DataFrame) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    score = np.zeros(len(f))
    bins: dict[str, np.ndarray] = {}
    for v in spec_vars:
        idx = binning.assign(binning.edges_ok(v), f[v["name"]])
        bins[v["name"]] = idx
        pts = np.asarray([b["points"] for b in v["bins"]])
        score += pts[idx]
    return score, bins


def _grades(score_dev: np.ndarray, y_dev: np.ndarray) -> list[dict[str, Any]]:
    """Eight grades by development score quantiles (G1 safest). Grade PD = development default rate of the grade."""
    qs = [0.10, 0.25, 0.42, 0.58, 0.72, 0.85, 0.94]
    cuts = np.unique(np.quantile(score_dev, qs))
    edges = [-math.inf, *cuts, math.inf]
    out = []
    n_g = len(edges) - 1
    for i in range(n_g):
        sel = (score_dev >= edges[i]) & (score_dev < edges[i + 1])
        pd_ = (y_dev[sel].sum() + 0.5) / (sel.sum() + 1.0)
        out.append({"low": None if math.isinf(edges[i]) else float(edges[i]), "high": None if math.isinf(edges[i + 1]) else float(edges[i + 1]),
                    "pd_dev": float(pd_), "n_dev": int(sel.sum())})
    # grades run from the highest score (G1) to the lowest; enforce a monotone PD
    out = list(reversed(out))
    run = 0.0
    for i, g in enumerate(out):
        run = max(run, g["pd_dev"])
        g["pd"] = run
        g["grade"] = f"G{i + 1}"
    return out


def _grade_of(score: np.ndarray, grades: list[dict[str, Any]]) -> np.ndarray:
    out = np.empty(len(score), dtype=object)
    for g in grades:
        lo = -np.inf if g["low"] is None else g["low"]
        hi = np.inf if g["high"] is None else g["high"]
        out[(score >= lo) & (score < hi)] = g["grade"]
    return out


def _overrides(f: pd.DataFrame, sid: str, grades: list[dict[str, Any]]) -> pd.DataFrame:
    """Credit-officer overrides of the scorecard grade (application-type scorecards)."""
    g_rank = f["grade"].str[1:].astype(int).to_numpy()
    n_g = len(grades)
    u = _u(f[CARD_KEY[sid]].astype(str) + f[CARD_PERIOD[sid]], "override")
    up_p = np.where(g_rank >= n_g - 2, 0.085 if sid == "SME-ANN" else 0.065, 0.004)     # approved against a weak grade
    down_p = np.where(g_rank <= 2, 0.030, 0.003)                                          # declined against a strong grade
    up = u < up_p
    down = (~up) & (u > 1 - down_p)
    f["override_flag"] = (up | down).astype(np.int8)
    f["override_direction"] = np.where(up, "upgrade", np.where(down, "downgrade", "none"))
    r = _u(f[CARD_KEY[sid]].astype(str) + f[CARD_PERIOD[sid]], "override-reason")
    reasons = ["Strong relationship", "Collateral support", "Guarantee", "Policy exception", "Verified additional income"] if sid != "SME-ANN" \
        else ["Strong relationship", "Collateral support", "Group guarantee", "Contract backlog", "Management quality"]
    f["override_reason"] = np.where(f.override_flag == 1, np.array(reasons, dtype=object)[np.minimum((r * len(reasons)).astype(int), len(reasons) - 1)], "")
    lvl = _u(f[CARD_KEY[sid]].astype(str) + f[CARD_PERIOD[sid]], "override-level")
    f["override_level"] = np.where(f.override_flag == 1, np.where(lvl < 0.55, "Branch", np.where(lvl < 0.85, "Regional", "Head Office")), "")
    return f


STRENGTH = {"RET-APP": 0.55, "RET-BEH": 0.65, "SME-ANN": 0.50}
CARD_KEY = {"RET-APP": "account_id", "RET-BEH": "account_id", "SME-ANN": "borrower_id"}
CARD_PERIOD = {"RET-APP": "reporting_month", "RET-BEH": "reporting_month", "SME-ANN": "reporting_quarter"}

OUT_COLS_BASE = ["period", "sample", "matured", "y12", "score", "grade", "pd_grade", "pd_model"]


def build_one(sid: str, source: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    spec = SCORECARDS[sid]
    pc, unit, owner = spec["period_col"], spec["unit_key"], spec["owner_key"]
    f = source.copy()
    periods = sorted(f[pc].unique())
    if sid == "RET-APP":
        f = f[(f.months_on_book <= 12) & (f.default_flag == 0)]
    elif sid == "RET-BEH":
        f = f[(f.default_flag == 0)]
        f = f[(pd.util.hash_pandas_object(f.account_id, index=False).to_numpy() % 100) < spec["sample_pct"]]
    else:
        f = f[f.book_default == 0] if "book_default" in f else f
    f = f.reset_index(drop=True)
    f.attrs.update(source.attrs)
    for name, _, kind in CANDIDATES[sid]:       # the values the domain stores are the values the scorecard is fitted on
        if kind == "numeric":
            f[name] = f[name].astype("float32").astype("float64")
    f = _outcomes(sid, f, periods, spec)
    f["sample"] = _label_sample(f, spec)
    # the outcome: a draw per owner and period against the latent probability; only where the window has closed
    p = expit(f["_z"].to_numpy())
    if spec["has_overrides"]:
        pass
    f["_p_true"] = p
    # first pass: scorecard fit needs development outcomes (override uplift is applied after grading)
    draw = _u(f[unit].astype(str) + "|" + f[pc], "outcome")
    f["y12"] = np.where(f["matured"], (draw < p).astype(float), np.nan)
    fit = _fit(sid, f, spec)
    score, bins = _score(fit["variables"], f)
    f["score"] = score.round(1)
    dev_mask = (f["sample"] == "development").to_numpy()
    grades = _grades(score[dev_mask], f.loc[dev_mask, "y12"].to_numpy(dtype=float))
    f["grade"] = _grade_of(score, grades)
    f["pd_grade"] = f["grade"].map({g["grade"]: g["pd"] for g in grades}).astype(float)
    ln_odds = (score - OFFSET) / FACTOR
    f["pd_model"] = 1.0 / (1.0 + np.exp(ln_odds))
    if spec["has_overrides"]:
        f = _overrides(f, sid, grades)
        # an upgrade override approves a weaker credit than the grade says: the outcome is drawn against a higher risk
        uplift = np.where(f.override_direction == "upgrade", 0.55, np.where(f.override_direction == "downgrade", -0.35, 0.0))
        p2 = expit(f["_z"].to_numpy() + uplift)
        f["y12"] = np.where(f["matured"], (draw < p2).astype(float), np.nan)
    else:
        f["override_flag"], f["override_direction"], f["override_reason"], f["override_level"] = 0, "none", "", ""
    for name, idx in bins.items():
        f[f"bin_{name}"] = idx.astype(np.int8)
    out_cols = [owner] + ([unit] if unit != owner else []) + [pc, "sample", "matured", "y12", "score", "grade", "pd_grade", "pd_model",
                spec["segment_col"], "override_flag", "override_direction", "override_reason", "override_level"]
    out_cols = list(dict.fromkeys(out_cols))
    var_cols = list(dict.fromkeys([v["name"] for v in fit["variables"]] + [n for n, _, _ in CANDIDATES[sid]]))
    keep = list(dict.fromkeys(out_cols + var_cols + [f"bin_{n}" for n in bins]))
    out = f[keep].rename(columns={pc: "period"}).copy()
    out["scorecard_id"] = sid
    for c in out.select_dtypes("float64").columns:
        if c not in ("y12", "pd_model", "pd_grade"):
            out[c] = out[c].astype("float32")
    for c in ("grade", "sample", "override_direction", "override_reason", "override_level"):
        out[c] = out[c].astype("category")
    spec_out = {"scorecard_id": sid, **{k: v for k, v in spec.items() if k not in ("target_odr",)},
                "points": {"base_score": BASE_SCORE, "base_odds": BASE_ODDS, "pdo": PDO, "factor": FACTOR, "offset": OFFSET},
                "intercept": fit["intercept"], "variables": fit["variables"], "excluded": fit["excluded"], "grades": grades,
                "candidates": [{"name": n, "label": l, "type": k} for n, l, k in CANDIDATES[sid]],
                "periods": periods, "rows": int(len(out)), "development_rows": int(dev_mask.sum()),
                "development_defaults": int(np.nansum(f.loc[dev_mask, "y12"])),
                "last_matured": next(p for p in reversed(periods) if p in set(f.loc[f.matured, pc]))}
    return out, spec_out


def build() -> dict[str, Any]:
    t0 = time.time()
    paths.DOMAIN.mkdir(parents=True, exist_ok=True)
    retail, sme = _retail_frame(), _sme_frame()
    manifest: dict[str, Any] = {"release_id": paths.RELEASE, "build_version": BUILD_VERSION, "seed": MASTER_SEED,
                                "origin": "SYNTHETIC_DEMO", "sme_revenue_cut_sar_mn": SME_REVENUE_CUT, "scorecards": {},
                                "keys": {"retail": ["customer_id", "account_id", "reporting_month"], "corporate": ["borrower_id", "reporting_quarter"]},
                                "planted": PLANTED,
                                "sources": {"retail": paths.RETAIL_RELEASE, "corporate": paths.CORP_RELEASE, "bureau": paths.BUREAU,
                                            "open_banking": paths.OPEN_BANKING},
                                "note": "Scorecard outcomes are generated from the books' characteristics plus hidden factors; the books' "
                                        "point-in-time default flag is not a performance window and is not used as the outcome."}
    for sid in SCORECARDS:
        src = sme if sid == "SME-ANN" else retail
        frame, spec = build_one(sid, src)
        frame.to_parquet(paths.DOMAIN / f"{sid}.parquet", index=False, compression="zstd")
        (paths.DOMAIN / f"{sid}.spec.json").write_text(json.dumps(spec, indent=1, default=_json))
        manifest["scorecards"][sid] = {"rows": spec["rows"], "development_rows": spec["development_rows"],
                                       "development_defaults": spec["development_defaults"], "periods": spec["periods"],
                                       "variables": [v["name"] for v in spec["variables"]]}
        print(f"{sid}: {spec['rows']:,} rows, {len(spec['variables'])} variables, dev defaults {spec['development_defaults']}", flush=True)
    manifest["fingerprint"] = _fingerprint()
    (paths.DOMAIN / "manifest.json").write_text(json.dumps(manifest, indent=1, default=_json))
    print(f"built in {time.time() - t0:.0f}s -> {paths.DOMAIN}")
    return manifest


def _fingerprint() -> str:
    h = hashlib.sha256()
    for sid in SCORECARDS:
        f = pd.read_parquet(paths.DOMAIN / f"{sid}.parquet")
        h.update(pd.util.hash_pandas_object(f.drop(columns=[c for c in f.columns if f[c].dtype == object]), index=False).to_numpy().tobytes())
        h.update((paths.DOMAIN / f"{sid}.spec.json").read_bytes())
    return h.hexdigest()


def _json(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if math.isnan(float(o)) or math.isinf(float(o)) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    raise TypeError(type(o))


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
