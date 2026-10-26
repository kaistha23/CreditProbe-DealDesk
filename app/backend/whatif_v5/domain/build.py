"""Build the What-If IFRS 9 data domain from the v5 books and the Saudi MEVs.

One row per facility (corporate, every quarter) or account (retail, every
month), the same IDs as the books. The construction reproduces the books'
ECL exactly, row by row (docs/v5/WHATIF_DESIGN.md section 3):

  * scenario weights base 50% / upturn 20% / downturn 30%;
  * the cycle index Z(s, t) of the exposure's segment along each scenario's
    5-year MEV path (cycle.py);
  * annual conditional PD h(s,t) = Phi((a - sqrt(rho) Z(s,t)) / sqrt(1-rho)),
    with `a` solved so the weighted year-1 PD is the book's pd_pit_12m, and
    years 2-5 scaled by one `k` so the weighted 5-year cumulative PD is the
    book's pd_lifetime; marginal PD(s,t) = survival(s,t-1) * h(s,t);
  * LGD(s,t) = book LGD x a downturn factor (1 + 0.10 x (Z_base - Z_s)) x a
    collateral factor (real-estate collateral moves with the real-estate
    price path) x a calibration constant: c1 for year 1, c2 for years 2-5,
    solved so the weighted 12-month and lifetime ECL are the book's;
  * Stage 3: PD 1 in year 1 in every scenario; LGD calibrated to the book ECL;
  * final ECL = weighted 12-month ECL (Stage 1) or lifetime ECL (Stages 2, 3).

Deterministic: same books and MEVs, same bytes.
"""
from __future__ import annotations

import json
import time
import zlib
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri

from backend.v5common import ratings
from backend.whatif_v5 import paths
from backend.whatif_v5.domain import cycle, mev, store

LGD_DOWNTURN_PER_Z = 0.10
RE_COLLATERAL = {"Real Estate", "Residential Property"}
RETAIL_HAIRCUT = {"Residential Property": 20.0, "Motor Vehicle": 40.0}
SCORE_BANDS = ("A", "B", "C", "D", "E")
DOMAIN_VERSION = "whatif-ifrs9-1.0.0"


def _file(release: str, name: str) -> str:
    return str(paths.LAKE / release / f"{name}.parquet")


def _q(sql: str, params: list | None = None) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


# ------------------------------------------------------------------ raw books

def corporate_raw() -> pd.DataFrame:
    rel = paths.CORP_RELEASE
    return _q(f"""
        SELECT f.reporting_quarter AS period, f.facility_id AS exposure_id, f.borrower_id AS owner_id,
               f.borrower_name AS owner_name, f.sector AS segment, f.sub_sector AS subsegment,
               f.product_type AS product, f.facility_class, f.stage, f.dpd_days AS dpd, f.default_flag,
               f.limit_sar_mn AS "limit", f.drawn_sar_mn AS drawn, f.undrawn_sar_mn AS undrawn,
               f.ead_sar_mn AS ead, f.pd_pit_12m AS pd12_book, f.pd_lifetime AS pdlt_book,
               f.lgd_pct AS lgd_pct_book, f.ecl_12m_sar_mn AS ecl12_book, f.ecl_lifetime_sar_mn AS ecllt_book,
               f.ecl_sar_mn AS ecl_book,
               b.rating_current AS grade, b.rating_at_origination, b.rating_notches_from_origination AS nfo,
               b.pd_ttc_12m AS pd_ttc,
               c.collateral_type, c.market_value_sar_mn AS collateral_value, c.haircut_pct,
               c.allocated_value_sar_mn AS collateral_allocated
        FROM '{_file(rel, 'corp_facility_quarter')}' f
        LEFT JOIN '{_file(rel, 'corp_borrower_quarter')}' b
          ON b.borrower_id = f.borrower_id AND b.reporting_quarter = f.reporting_quarter
        LEFT JOIN '{_file(rel, 'corp_collateral_quarter')}' c
          ON c.facility_id = f.facility_id AND c.reporting_quarter = f.reporting_quarter
        ORDER BY f.reporting_quarter, f.facility_id""")


def retail_raw() -> pd.DataFrame:
    rel = paths.RETAIL_RELEASE
    f = _q(f"""
        SELECT a.reporting_month AS period, a.account_id AS exposure_id, a.customer_id AS owner_id,
               a.product AS segment, a.sub_product AS subsegment, a.product, a.secured_flag,
               a.stage, a.dpd_days AS dpd, a.default_flag,
               a.limit_sar_mn AS "limit", a.balance_sar_mn AS drawn,
               GREATEST(a.limit_sar_mn - a.balance_sar_mn, 0) AS undrawn,
               a.ead_sar_mn AS ead, a.pd_pit_12m AS pd12_book, a.pd_lifetime AS pdlt_book,
               a.lgd_pct AS lgd_pct_book, a.ecl_12m_sar_mn AS ecl12_book, a.ecl_lifetime_sar_mn AS ecllt_book,
               a.ecl_sar_mn AS ecl_book, a.score_band AS grade, a.behaviour_score,
               c.collateral_type, c.collateral_value_sar_mn AS collateral_value, c.ltv_pct
        FROM '{_file(rel, 'retail_account_month')}' a
        LEFT JOIN '{_file(rel, 'retail_collateral_month')}' c
          ON c.account_id = a.account_id AND c.reporting_month = a.reporting_month
        ORDER BY a.reporting_month, a.account_id""")
    f["owner_name"] = None
    return f


def _hash_noise(ids: pd.Series, salt: str) -> np.ndarray:
    """A standard-normal draw per id, from its hash: reproducible on any machine."""
    u = ids.astype(str).map(lambda s: (zlib.crc32((salt + s).encode()) + 0.5) / 2 ** 32).to_numpy()
    return ndtri(np.clip(u, 1e-9, 1 - 1e-9))


def prepare(domain: str, raw: pd.DataFrame) -> pd.DataFrame:
    f = raw.copy()
    for c in ("limit", "drawn", "undrawn", "ead", "pd12_book", "pdlt_book", "lgd_pct_book", "ecl12_book",
              "ecllt_book", "ecl_book", "collateral_value"):
        f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0).astype(float)
    f["stage"] = pd.to_numeric(f["stage"], errors="coerce").fillna(1).astype(int)
    f["dpd"] = pd.to_numeric(f["dpd"], errors="coerce").fillna(0).astype(int)
    f["default_flag"] = pd.to_numeric(f["default_flag"], errors="coerce").fillna(0).astype(int)
    f["grade"] = f["grade"].fillna("").astype(str)
    f["ccf"] = np.where(f["undrawn"] > 1e-12, ((f["ead"] - f["drawn"]) / f["undrawn"].where(f["undrawn"] > 1e-12, 1.0)).clip(0, 1), 0.0)
    if domain == "corporate":
        f["grade_rank"] = f["grade"].map(ratings.rank).astype(int)
        f["nfo"] = pd.to_numeric(f["nfo"], errors="coerce").fillna(0).astype(int)
        f["rating_at_origination"] = f["rating_at_origination"].fillna("").astype(str)
        f["pd_ttc"] = pd.to_numeric(f["pd_ttc"], errors="coerce").astype(float)
        f["haircut_pct"] = pd.to_numeric(f["haircut_pct"], errors="coerce").fillna(0.0).astype(float)
        f["collateral_allocated"] = pd.to_numeric(f["collateral_allocated"], errors="coerce").fillna(0.0).astype(float)
        f["collateral_type"] = f["collateral_type"].fillna("Unsecured").astype(str)
        f["behaviour_score"] = np.nan
        f["application_score"] = np.nan
    else:
        order = {b: i for i, b in enumerate(SCORE_BANDS)}
        f["grade_rank"] = f["grade"].map(lambda g: order.get(g, len(SCORE_BANDS))).astype(int)
        f["nfo"] = 0
        f["rating_at_origination"] = ""
        f["behaviour_score"] = pd.to_numeric(f["behaviour_score"], errors="coerce").astype(float)
        # Application score: the books carry none. Derived per account from its first observed
        # behaviour score plus a reproducible account-level draw (sd 30 points), clipped 300-900.
        first = f.sort_values("period").groupby("exposure_id")["behaviour_score"].first()
        noise = pd.Series(_hash_noise(pd.Series(first.index), "app-score"), index=first.index)
        app = (first + 30.0 * noise).clip(300, 900).round(0)
        f["application_score"] = f["exposure_id"].map(app).astype(float)
        f["collateral_type"] = f["collateral_type"].fillna("Unsecured").astype(str)
        f["haircut_pct"] = f["collateral_type"].map(RETAIL_HAIRCUT).fillna(0.0).astype(float)
        f["collateral_allocated"] = np.minimum(f["collateral_value"] * (1 - f["haircut_pct"] / 100.0), f["ead"])
        # Retail TTC PD: the 20-month average 12m PD of the product and score band (performing accounts).
        perf = f[f["stage"] < 3]
        ttc = perf.groupby(["product", "grade"])["pd12_book"].mean()
        f["pd_ttc"] = pd.Series(list(zip(f["product"], f["grade"]))).map(ttc).to_numpy()
        prod_ttc = perf.groupby("product")["pd12_book"].mean()
        f["pd_ttc"] = f["pd_ttc"].fillna(f["product"].map(prod_ttc)).astype(float)
    f["pd_ttc"] = f["pd_ttc"].fillna(f["pd12_book"].where(f["pd12_book"] < 1, np.nan)).fillna(0.01)
    f["secured_share"] = np.where(f["ead"] > 1e-12, (f["collateral_allocated"] / f["ead"].where(f["ead"] > 1e-12, 1.0)).clip(0, 1), 0.0)
    f["rho"] = cycle.rho(domain, f["pd_ttc"].to_numpy(), f["product"].to_numpy())
    return f


# ------------------------------------------------------------------ the cycle model

def implied_history(domain: str, f: pd.DataFrame) -> pd.DataFrame:
    """Each segment's cycle index per period from its OBSERVED DEFAULT RATE (cycle.py).

    Default = an exposure performing (Stage 1-2) at the previous period and in Stage 3 now.
    Annual observed default rate (ODR) = defaults over the last 4 quarters (12 months) / the
    performing exposures they came from. Z = (Phi^-1(long-run ODR) - sqrt(1-rho) Phi^-1(ODR)) / sqrt(rho),
    rho the segment's EAD-weighted asset correlation.
    """
    window = 4 if domain == "corporate" else 12
    g = f[["period", "exposure_id", "segment", "stage", "ead", "rho"]].sort_values(["exposure_id", "period"]).copy()
    g["prev"] = g.groupby("exposure_id")["stage"].shift(1)
    trans = g[g["prev"].notna() & (g["prev"] < 3)]
    by = trans.groupby(["segment", "period"]).agg(at_risk=("stage", "size"),
                                                  defaults=("stage", lambda s: int((s == 3).sum())))
    rows = []
    rho_seg = f[f["stage"] < 3].groupby("segment").apply(
        lambda x: float(np.average(x["rho"], weights=np.maximum(x["ead"], 1e-12))), include_groups=False)
    ead_seg = f.groupby(["segment", "period"])["ead"].sum()
    periods = sorted(f["period"].unique())
    for seg, sub in by.groupby(level=0):
        sub = sub.droplevel(0).reindex(periods[1:]).fillna(0)
        roll = sub.rolling(window, min_periods=1).sum()
        n_q = sub["at_risk"].rolling(window, min_periods=1).count()
        # annualise: per-period hazard over the window, compounded to a year
        per_q = (roll["defaults"] / roll["at_risk"].where(roll["at_risk"] > 0, 1.0)) * (window / n_q)
        odr = per_q.clip(1e-4, 0.5)
        lr = float((sub["defaults"].sum() / max(sub["at_risk"].sum(), 1.0)) * window)
        lr = float(np.clip(lr, 1e-4, 0.5))
        r = float(rho_seg.get(seg, 0.12))
        z = (ndtri(lr) - np.sqrt(1 - r) * ndtri(odr.to_numpy())) / np.sqrt(r)
        for p, zz, o in zip(odr.index, z, odr.to_numpy()):
            rows.append({"period": p, "segment": seg, "z": float(zz), "odr": float(o), "lr_odr": lr,
                         "ead": float(ead_seg.get((seg, p), 0.0))})
    return pd.DataFrame(rows)


def start_year(period: str) -> int:
    return int(np.floor(mev.period_year_fraction(period) + 0.5))


# ------------------------------------------------------------------ term structures

def _bisect(fun, lo: np.ndarray, hi: np.ndarray, iters: int = 64) -> np.ndarray:
    for _ in range(iters):
        mid = (lo + hi) / 2
        above = fun(mid) > 0
        hi = np.where(above, mid, hi)
        lo = np.where(above, lo, mid)
    return (lo + hi) / 2


def term_structures(domain: str, f: pd.DataFrame, model: dict[str, Any], period: str) -> pd.DataFrame:
    n = len(f)
    sy = start_year(period)
    paths_ = mev.paths_from(sy)
    W = np.array([mev.WEIGHTS[s] for s in store.SCENARIOS])
    segs = f["segment"].astype(str).to_numpy()
    # Z(s, t) per row: (n, 3, 5)
    Z = np.zeros((n, 3, 5))
    re_level = np.zeros((3, 5))
    re0 = mev.levels_at_period(period)["re_price"]
    for j, s in enumerate(store.SCENARIOS):
        feats = paths_[s + "_features"]
        re_level[j] = paths_[s]["re_price"].to_numpy() / re0 - 1.0
        for seg in np.unique(segs):
            Z[segs == seg, j, :] = cycle.z_path(model, seg, feats)
    r = f["rho"].to_numpy()[:, None, None]
    sr, s1r = np.sqrt(r), np.sqrt(1 - r)
    pd12 = f["pd12_book"].to_numpy()
    pdlt = np.maximum(f["pdlt_book"].to_numpy(), pd12)
    defaulted = (f["stage"].to_numpy() >= 3) | (pd12 >= 1.0)
    live = ~defaulted & (pd12 > 0)

    def h_of(a):  # (n,) -> (n,3,5) unscaled hazards
        return ndtr((a[:, None, None] - sr * Z) / s1r)

    # a: weighted year-1 PD equals the book's pd12
    target = np.where(live, pd12, 0.01)
    a = _bisect(lambda a_: (W[None, :] * ndtr((a_[:, None] - sr[:, :, 0] * Z[:, :, 0]) / s1r[:, :, 0])).sum(1) - target,
                np.full(n, -15.0), np.full(n, 15.0))
    g = h_of(a)

    def cum5(k):
        h = g.copy()
        h[:, :, 1:] = np.minimum(cycle.PD_CAP, h[:, :, 1:] * k[:, None, None])
        surv = np.cumprod(1 - h, axis=2)
        return (W[None, :] * (1 - surv[:, :, -1])).sum(1)

    kmax = cycle.PD_CAP / np.maximum(g[:, :, 1:].min(axis=(1, 2)), 1e-12)
    k = _bisect(lambda k_: cum5(k_) - np.where(live, pdlt, 0.0), np.zeros(n), kmax)
    k = np.where(live & (pdlt > pd12 + 1e-12), k, 0.0)
    h = g.copy()
    h[:, :, 1:] = np.minimum(cycle.PD_CAP, h[:, :, 1:] * k[:, None, None])
    surv = np.cumprod(1 - h, axis=2)
    prev = np.concatenate([np.ones((n, 3, 1)), surv[:, :, :-1]], axis=2)
    mpd = prev * h
    mpd[defaulted] = 0.0
    mpd[defaulted, :, 0] = 1.0
    mpd[~live & ~defaulted] = 0.0

    # LGD paths
    L = f["lgd_pct_book"].to_numpy() / 100.0
    zbase = Z[:, 0:1, :]
    down = 1.0 + LGD_DOWNTURN_PER_Z * (zbase - Z)
    re_secured = f["collateral_type"].isin(RE_COLLATERAL).to_numpy() * f["secured_share"].to_numpy()
    coll = 1.0 - re_secured[:, None, None] * np.broadcast_to(re_level[None, :, :], (n, 3, 5))
    factor = np.clip(down * coll, 0.5, 2.0)
    base_lgd = np.minimum(L[:, None, None] * factor, 1.0)
    ead = f["ead"].to_numpy()
    safe_ead = np.where(ead > 0, ead, 1.0)
    y1 = (W[None, :] * mpd[:, :, 0] * base_lgd[:, :, 0]).sum(1)
    later = (W[None, :, None] * mpd[:, :, 1:] * base_lgd[:, :, 1:]).sum((1, 2))
    e12 = f["ecl12_book"].to_numpy() / safe_ead
    elt = f["ecllt_book"].to_numpy() / safe_ead
    efin = f["ecl_book"].to_numpy() / safe_ead
    c1 = np.where(y1 > 1e-15, e12 / np.where(y1 > 1e-15, y1, 1.0), 1.0)
    c2 = np.where(later > 1e-15, (elt - c1 * y1) / np.where(later > 1e-15, later, 1.0), 1.0)
    # Stage 3: one calibration so the weighted ECL is the book's final ECL.
    c3 = np.where(y1 > 1e-15, efin / np.where(y1 > 1e-15, y1, 1.0), 1.0)
    c1 = np.where(defaulted, c3, c1)
    c2 = np.where(defaulted, 1.0, c2)
    lgd = base_lgd.copy()
    lgd[:, :, 0] *= c1[:, None]
    lgd[:, :, 1:] *= c2[:, None, None]

    out = pd.DataFrame(index=f.index)
    out["cycle_a"] = a
    out["term_k"] = k
    out["lgd_cal_y1"] = c1
    out["lgd_cal_y2_5"] = c2
    for j, s in enumerate(store.SCENARIOS):
        for t in range(5):
            out[f"pd_{s}_y{t + 1}"] = mpd[:, j, t]
            out[f"lgd_{s}_y{t + 1}"] = lgd[:, j, t]
    for t in range(5):
        out[f"pd_weighted_y{t + 1}"] = (W[None, :] * mpd[:, :, t]).sum(1)
    out["pd_12m"] = out["pd_weighted_y1"]
    out["pd_lifetime"] = sum(out[f"pd_weighted_y{t}"] for t in range(1, 6))
    for j, s in enumerate(store.SCENARIOS):
        out[f"w_{s}"] = W[j]
    stage1 = f["stage"].to_numpy() == 1
    e12_s = mpd[:, :, 0] * lgd[:, :, 0] * ead[:, None]
    elt_s = (mpd * lgd).sum(2) * ead[:, None]
    for j, s in enumerate(store.SCENARIOS):
        out[f"ecl_{s}"] = np.where(stage1, e12_s[:, j], elt_s[:, j])
    out["ecl_12m"] = (W[None, :] * e12_s).sum(1)
    out["ecl_lifetime"] = (W[None, :] * elt_s).sum(1)
    out["ecl_weighted"] = np.where(stage1, out["ecl_12m"], out["ecl_lifetime"])
    return out


KEEP = ["period", "exposure_id", "owner_id", "owner_name", "segment", "subsegment", "product", "stage", "dpd",
        "default_flag", "grade", "grade_rank", "rating_at_origination", "nfo", "behaviour_score", "application_score",
        "collateral_type", "collateral_value", "haircut_pct", "collateral_allocated", "secured_share",
        "limit", "drawn", "undrawn", "ead", "ccf", "pd_ttc", "rho", "lgd_pct_book",
        "pd12_book", "pdlt_book", "ecl12_book", "ecllt_book", "ecl_book"]


def control_totals(frame: pd.DataFrame) -> dict[str, float]:
    """Per-period control totals: what the sync test and a rebuild on another machine must reproduce."""
    out = {"rows": int(len(frame)), "ead": float(frame["ead"].sum()), "ecl_final": float(frame["ecl_final"].sum()),
           "ecl_weighted": float(frame["ecl_weighted"].sum()), "ecl_12m": float(frame["ecl_12m"].sum()),
           "ecl_lifetime": float(frame["ecl_lifetime"].sum()), "pd_12m": float(frame["pd_12m"].sum()),
           "pd_lifetime": float(frame["pd_lifetime"].sum())}
    for s in store.SCENARIOS:
        out[f"ecl_{s}"] = float(frame[f"ecl_{s}"].sum())
    return out


def build_book(domain: str, out_dir=None, meta_dir=None, log=print) -> dict[str, Any]:
    t0 = time.time()
    out_dir = out_dir or store.files_dir(domain)
    meta_dir = meta_dir or store.book_dir(domain)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    raw = corporate_raw() if domain == "corporate" else retail_raw()
    f = prepare(domain, raw)
    hist = implied_history(domain, f)
    model = cycle.fit(domain, hist)
    (meta_dir / "cycle_model.json").write_text(json.dumps(model, indent=1, sort_keys=True))
    periods = sorted(f["period"].unique())
    files = {}
    rows = 0
    worst = {"pdlt_abs_err": 0.0, "ecl_abs_err": 0.0, "lgd_max": 0.0}
    for p in periods:
        fp = f[f["period"] == p].reset_index(drop=True)
        ts = term_structures(domain, fp, model, p)
        frame = pd.concat([fp[KEEP], ts], axis=1)
        frame["ecl_final"] = frame["ecl_book"]
        frame["ecl_reconciliation_diff"] = frame["ecl_weighted"] - frame["ecl_book"]
        worst["ecl_abs_err"] = max(worst["ecl_abs_err"], float(frame["ecl_reconciliation_diff"].abs().max()))
        live = (frame["stage"] < 3) & (frame["pd12_book"] < 1)
        worst["pdlt_abs_err"] = max(worst["pdlt_abs_err"], float((frame.loc[live, "pd_lifetime"] - np.maximum(frame.loc[live, "pdlt_book"], frame.loc[live, "pd12_book"])).abs().max() or 0))
        worst["lgd_max"] = max(worst["lgd_max"], float(frame[[c for c in frame.columns if c.startswith("lgd_") and "_y" in c and "cal" not in c]].max().max()))
        frame["tenant_id"] = "creditprobe-v5"
        frame["domain_id"] = domain
        path = out_dir / f"{p}.parquet"
        frame.to_parquet(path, index=False, compression="zstd")
        files[p] = control_totals(frame)
        rows += len(frame)
        log(f"  {domain} {p}: {len(frame):,} rows, ECL {frame['ecl_final'].sum():,.1f}, "
            f"max |weighted - book| {frame['ecl_reconciliation_diff'].abs().max():.2e}")
    columns = list(frame.columns)
    man = {
        "domain": f"whatif_{domain}", "version": DOMAIN_VERSION, "book": domain,
        "grain": "facility x quarter" if domain == "corporate" else "account x month",
        "periods": periods, "rows": rows, "control_totals": files, "columns": columns,
        "keys": {"exposure": "facility_id (CF...)" if domain == "corporate" else "account_id (RA...)",
                 "owner": "borrower_id (CB...)" if domain == "corporate" else "customer_id (RC...)"},
        "source_release": paths.CORP_RELEASE if domain == "corporate" else paths.RETAIL_RELEASE,
        "scenario_weights": mev.WEIGHTS, "horizon_years": 5,
        "reconciliation": {"ecl_final_equals_book": True, **worst},
        "provenance": ("Built from the v5 books (same IDs and periods) and the Saudi MEV store by "
                       "backend/whatif_v5/domain/build.py. The books are the bank's internal books as loaded "
                       "in v5 (origin recorded in the books' own manifests)."),
        "derived_fields": {
            "application_score": "retail only: first observed behaviour score + reproducible account draw (sd 30)",
            "pd_ttc": "corporate: borrower pd_ttc_12m; retail: 20-month average 12m PD of product x score band",
            "haircut_pct": "corporate: book; retail: policy haircut by collateral type (residential 20%, motor 40%)",
            "pd_<scenario>_y<t>": "marginal (unconditional) PD in year t of the scenario's path",
            "lgd_<scenario>_y<t>": "LGD in year t of the scenario's path (calibrated)",
            "ecl_<scenario>": "ECL under the scenario on the exposure's stage horizon",
        },
        "built_seconds": round(time.time() - t0, 1),
    }
    man.pop("built_seconds")
    (meta_dir / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True))
    return man
