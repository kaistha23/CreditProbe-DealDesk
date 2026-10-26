"""Obligor PD from the What-If corporate XGBoost model (DEAL_DESK_PROMPT.md 3.2a). PD only, read-only.

The model (data/whatif_v5/models/corporate/pd.json, xgb-1.0.0) predicts the logit of the annual
conditional PD h(s, t) per scenario s and year t <= 5, one row per facility, offset by the logit
of the bank's 12-month PD input. Deal Desk scores it through What-If's own functions
(`xgb.long_rows`, `xgb.predict`), so the same feature vector gives the same score bit for bit.

Rules applied here:
  * obligor PD only: the facility-term features (product, LGD input, collateral type, secured
    share, haircut, EAD, CCF, undrawn share) are frozen at the obligor's reference profile and
    never moved by deal terms; leverage and DSCR are not model features, so no deal term reaches
    the model at all;
  * scored once per obligor (and per notch shift for stress), cached; the optimiser reads PD from
    a monotone interpolation over a leverage x DSCR grid of cached scores;
  * the monotonicity check runs on that grid and logs any isotonic smoothing;
  * the out-of-range guard compares the feature vector with the training range;
  * years 6-10 extend the model's year-5 hazard by the migration matrix's hazard shape.
"""
from __future__ import annotations

import functools
import json
import threading
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk import params, paths
from backend.v5common.ratings import RATING_ORDER, rank

BOOK = "corporate"
PERIOD = paths.AS_OF
TERM_FEATURES = ("product_code", "lgd_input", "collateral_code", "secured_share", "haircut_pct", "log_ead", "ccf",
                 "undrawn_share")
OBLIGOR_FEATURES = ("segment_code", "subsegment_code", "stage", "grade_rank", "pd_ttc", "pd_12m_input", "dpd", "nfo")
RANGES_FILE = paths.DATA / "model" / "feature_ranges.json"
LEVERAGE_GRID = (0.5, 1.5, 2.5, 3.5, 4.5, 6.0, 8.0)
DSCR_GRID = (0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.5)
GRADES = [r for r in RATING_ORDER if r != "D"]
_LOCK = threading.Lock()
_CACHE: dict[tuple, dict[str, Any]] = {}


def _xgb():
    from backend.whatif_v5.models import xgb
    return xgb


@functools.lru_cache(maxsize=1)
def model_meta() -> dict[str, Any]:
    xgb = _xgb()
    meta = json.loads((xgb.MODEL_DIR / BOOK / "models.json").read_text())
    e = meta["models"]["pd"]
    return {"version": meta["version"], "trained": meta["trained"], "file": f"data/whatif_v5/models/{BOOK}/{e['file']}",
            "sha256": e["sha256"], "target": e["target"], "features": e["features"], "monotone": meta.get("monotone", "none")}


@functools.lru_cache(maxsize=1)
def _domain_frame() -> pd.DataFrame:
    from backend.whatif_v5.domain import store
    return store.frame(BOOK, PERIOD)


def _static(f: pd.DataFrame) -> pd.DataFrame:
    xgb = _xgb()
    return xgb.static_frame(BOOK, f, xgb.encodings_cached(BOOK))


@functools.lru_cache(maxsize=32)
def segment_profile(segment: str) -> dict[str, float]:
    """The segment's EAD-weighted median facility-term profile (stage 1, 2026Q2), modal categories."""
    f = _domain_frame()
    s = f[(f["segment"] == segment) & (f["stage"] == 1) & (f["ead"] > 0)]
    if s.empty:
        s = f[(f["stage"] == 1) & (f["ead"] > 0)]
    xs = _static(s)
    out: dict[str, float] = {}
    w = s["ead"].to_numpy()
    for k in TERM_FEATURES:
        v = xs[k].to_numpy(dtype=float)
        if k in ("product_code", "collateral_code"):
            out[k] = float(pd.Series(w, index=v).groupby(level=0).sum().idxmax())
        else:
            order = np.argsort(v, kind="mergesort")
            cw = np.cumsum(w[order])
            out[k] = float(v[order][np.searchsorted(cw, cw[-1] / 2.0)])
    out["segment_code"] = float(xs["segment_code"].iloc[0])
    out["subsegment_mode"] = float(xs["subsegment_code"].mode().iloc[0])
    ratio = (s["pd12_book"] / s["pd_ttc"]).replace([np.inf, -np.inf], np.nan).dropna()
    out["pit_ttc_ratio"] = float(np.average(ratio, weights=s.loc[ratio.index, "ead"])) if len(ratio) else 1.0
    return out


def master_pd(rating: str) -> float:
    for r in params.rows("pd_master_scale"):
        if r["rating"] == rating:
            return float(r["pd_ttc"])
    raise KeyError(rating)


def feature_vector(p: dict[str, Any]) -> tuple[dict[str, float], str, dict[str, Any]]:
    """The model row for an obligor: (features, segment, provenance of each feature group)."""
    xgb = _xgb()
    enc = xgb.encodings_cached(BOOK)
    ob = p["obligor"]
    seg = ob.get("segment") or ob["sector"]
    if seg not in enc["segment_code"]:
        seg = "Wholesale Trade" if "trad" in seg.lower() else "Manufacturing"
    rating = ob["internal_rating"]
    if ob.get("existing"):
        f = _domain_frame()
        mine = f[(f["owner_id"] == ob["obligor_id"]) & (f["ead"] > 0)]
        if not mine.empty:
            ref = mine.sort_values(["stage", "ead"], ascending=[True, False]).iloc[[0]]
            xs = _static(ref).iloc[0].to_dict()
            feats = {k: float(xs[k]) for k in xs}
            feats.update({"stage": 1.0, "dpd": 0.0})
            prov = {"profile": f"own facility {ref['exposure_id'].iloc[0]} (largest performing, {PERIOD})",
                    "obligor": f"book record {ob['obligor_id']} {PERIOD}", "segment": str(ref["segment"].iloc[0])}
            return feats, str(ref["segment"].iloc[0]), prov
    prof = segment_profile(seg)
    sub = enc["subsegment_code"].get(ob.get("sub_sector", ""), prof["subsegment_mode"])
    ttc = master_pd(rating)
    feats = {k: prof[k] for k in TERM_FEATURES}
    feats.update({"segment_code": float(enc["segment_code"][seg]), "subsegment_code": float(sub), "stage": 1.0,
                  "grade_rank": float(rank(rating)), "pd_ttc": ttc,
                  "pd_12m_input": float(min(0.99, ttc * prof["pit_ttc_ratio"])), "dpd": 0.0, "nfo": 0.0})
    prov = {"profile": f"{seg} median facility profile, stage 1, {PERIOD}",
            "obligor": f"rating {rating}: master-scale TTC PD x {seg} PIT/TTC ratio {prof['pit_ttc_ratio']:.4f}",
            "segment": seg}
    return feats, seg, prov


def shift(feats: dict[str, float], notches: int) -> dict[str, float]:
    """A rating move as What-If applies it: grade, TTC PD, notches from origination, PD input by the master-scale ratio."""
    if not notches:
        return dict(feats)
    g0 = GRADES[int(min(len(GRADES) - 1, feats["grade_rank"]))]
    i1 = int(np.clip(GRADES.index(g0) + notches, 0, len(GRADES) - 1))
    g1 = GRADES[i1]
    out = dict(feats)
    factor = master_pd(g1) / master_pd(g0)
    out["grade_rank"] = float(rank(g1))
    out["pd_ttc"] = master_pd(g1)
    out["nfo"] = feats["nfo"] + notches
    out["pd_12m_input"] = float(min(0.99, feats["pd_12m_input"] * factor))
    return out


def score_hazards(feats: dict[str, float], segment: str) -> np.ndarray:
    """(3 scenarios, 5 years) annual conditional PD from the model, exactly as What-If scores a row."""
    xgb = _xgb()
    f = pd.DataFrame({"segment": [segment]})
    xs = pd.DataFrame([{k: feats[k] for k in xgb.static_features(BOOK)}])
    long = xgb.long_rows(BOOK, PERIOD, f, xs)
    h = xgb.expit(xgb.predict(BOOK, "pd", long)).reshape(3, 5)
    from backend.whatif_v5.models.engine import PD_CAP
    return np.clip(h, 0.0, PD_CAP)


@functools.lru_cache(maxsize=1)
def _migration() -> tuple[np.ndarray, list[str]]:
    rows = params.rows("pd_migration")
    cols = GRADES + ["D"]
    m = np.zeros((len(cols), len(cols)))
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            m[i, j] = r["to"][c]
    m[-1, -1] = 1.0
    return m, cols


def matrix_hazards(rating: str, years: int = 10) -> np.ndarray:
    """Conditional annual default hazards from the migration matrix (cumulative PD by matrix power)."""
    m, cols = _migration()
    v = np.zeros(len(cols))
    v[cols.index(rating)] = 1.0
    cum = []
    for _ in range(years):
        v = v @ m
        cum.append(v[-1])
    cum = np.asarray(cum)
    prev = np.concatenate([[0.0], cum[:-1]])
    return (cum - prev) / np.maximum(1 - prev, 1e-12)


def stage2_probability(rating: str, years: int = 10) -> np.ndarray:
    """P(performing and at least `sicr_notches` below origination) / P(performing), by year."""
    m, cols = _migration()
    k = int(params.table("pd_migration").get("sicr_notches", 3))
    i0 = cols.index(rating)
    v = np.zeros(len(cols))
    v[i0] = 1.0
    out = []
    for _ in range(years):
        v = v @ m
        perf = 1 - v[-1]
        out.append(float(v[i0 + k:-1].sum() / perf) if perf > 0 and i0 + k < len(cols) - 1 else 0.0)
    return np.asarray(out)


def term_structure(h: np.ndarray, rating: str, years: int) -> dict[str, Any]:
    """Probability-weighted marginal and cumulative PD by year; years > 5 follow the matrix hazard shape."""
    from backend.whatif_v5.domain import mev
    w = np.array([mev.WEIGHTS[s] for s in ("base", "upturn", "downturn")])
    mh = matrix_hazards(rating, max(years, 5))
    T = max(years, 1)
    hz = np.zeros((3, T))
    for t in range(T):
        if t < 5:
            hz[:, t] = h[:, t]
        else:
            hz[:, t] = np.clip(h[:, 4] * mh[t] / max(mh[4], 1e-12), 0.0, 0.9999)
    surv = np.cumprod(1 - hz, axis=1)
    prev = np.concatenate([np.ones((3, 1)), surv[:, :-1]], axis=1)
    marg_s = hz * prev
    marg = (w[:, None] * marg_s).sum(0)
    cum = np.cumsum(marg)
    return {"marginal": marg, "cumulative": cum, "survival": 1 - cum, "by_scenario": marg_s, "weights": w,
            "source": ["model" if t < 5 else "model year 5 x migration shape" for t in range(T)]}


# ------------------------------------------------------------------ cached obligor PD, monotone grid

def obligor_pd(p: dict[str, Any], notches: int = 0) -> dict[str, Any]:
    key = (p["proposal_id"], p["obligor"]["internal_rating"], p["obligor"].get("obligor_id"), notches, params.version_tag())
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit
    feats, seg, prov = feature_vector(p)
    f2 = shift(feats, notches)
    rating = GRADES[int(min(len(GRADES) - 1, f2["grade_rank"]))]
    # Rules 4-5: the score on a leverage x DSCR grid. Neither is a model feature, so every grid point is
    # the same vector; the check below still runs on the grid and would smooth any fall in PD.
    grid = np.empty((len(LEVERAGE_GRID), len(DSCR_GRID), 3, 5))
    distinct: dict[bytes, np.ndarray] = {}
    for i, _lev in enumerate(LEVERAGE_GRID):
        for j, _d in enumerate(DSCR_GRID):
            vec = f2  # post-deal leverage/DSCR would enter here if they were model features
            k = json.dumps(vec, sort_keys=True).encode()
            if k not in distinct:
                distinct[k] = score_hazards(vec, seg)
            grid[i, j] = distinct[k]
    pd12 = grid[..., 0]
    from backend.whatif_v5.domain import mev
    w = np.array([mev.WEIGHTS[s] for s in ("base", "upturn", "downturn")])
    pd12w = (pd12 * w).sum(-1)
    adjustments = monotone_check(pd12w)
    out = {"features": f2, "segment": seg, "provenance": prov, "rating": rating, "hazards": grid[0, 0],
           "grid": {"leverage": list(LEVERAGE_GRID), "dscr": list(DSCR_GRID), "pd_12m": pd12w.tolist(),
                    "distinct_scores": len(distinct)},
           "monotonicity": {"status": "pass" if not adjustments else "smoothed", "grid_points": int(pd12w.size),
                            "distinct_scores": len(distinct), "adjustments": adjustments,
                            "note": "Leverage and DSCR are not features of the model: PD is flat on the grid."},
           "pd_12m": float((w * grid[0, 0][:, 0]).sum()), "master_scale_pd_12m": master_pd(rating),
           "pd_ttc": master_pd(rating), "out_of_range": out_of_range(f2, p)}
    with _LOCK:
        _CACHE[key] = out
    return out


def monotone_check(pd12: np.ndarray) -> list[dict[str, Any]]:
    """PD must not fall as leverage rises (axis 0) or as DSCR falls (axis 1 reversed). Isotonic fix, logged."""
    from sklearn.isotonic import IsotonicRegression
    adj = []
    for j in range(pd12.shape[1]):
        col = pd12[:, j]
        if np.any(np.diff(col) < -1e-15):
            fit = IsotonicRegression(increasing=True).fit_transform(np.arange(len(col)), col)
            adj.append({"axis": "leverage", "dscr": DSCR_GRID[j], "before": col.tolist(), "after": fit.tolist()})
            pd12[:, j] = fit
    for i in range(pd12.shape[0]):
        row = pd12[i, :]
        if np.any(np.diff(row) > 1e-15):
            fit = IsotonicRegression(increasing=False).fit_transform(np.arange(len(row)), row)
            adj.append({"axis": "dscr", "leverage": LEVERAGE_GRID[i], "before": row.tolist(), "after": fit.tolist()})
            pd12[i, :] = fit
    return adj


def pd_at(o: dict[str, Any], leverage: float, dscr: float) -> float:
    """Monotone (PCHIP) interpolation of the cached grid: the smooth PD the optimiser reads."""
    from scipy.interpolate import PchipInterpolator
    g = np.asarray(o["grid"]["pd_12m"])
    lev = np.clip(leverage, LEVERAGE_GRID[0], LEVERAGE_GRID[-1])
    d = np.clip(dscr, DSCR_GRID[0], DSCR_GRID[-1])
    col = np.array([PchipInterpolator(LEVERAGE_GRID, g[:, j])(lev) for j in range(g.shape[1])])
    return float(PchipInterpolator(DSCR_GRID, col)(d))


# ------------------------------------------------------------------ out-of-range guard (rule 6)

@functools.lru_cache(maxsize=1)
def training_ranges() -> dict[str, Any]:
    if RANGES_FILE.exists():
        return json.loads(RANGES_FILE.read_text())
    return build_ranges()


def build_ranges() -> dict[str, Any]:
    """Per-feature min, max, 1st and 99th percentile over the model's training domain (all 20 periods)."""
    from backend.whatif_v5.domain import store
    parts = []
    for per in store.periods(BOOK):
        f = store.frame(BOOK, per)
        f = f[f["ead"] > 0]
        parts.append(_static(f))
    x = pd.concat(parts, ignore_index=True)
    out = {"source": f"What-If {BOOK} domain {store.periods(BOOK)[0]}-{store.periods(BOOK)[-1]}, {len(x)} rows",
           "features": {}}
    for k in x.columns:
        v = x[k].to_numpy(dtype=float)
        out["features"][k] = {"min": float(np.nanmin(v)), "max": float(np.nanmax(v)),
                              "p01": float(np.nanpercentile(v, 1)), "p99": float(np.nanpercentile(v, 99))}
    b = pd.read_parquet(paths.book_relation("corp_borrower_quarter"), columns=["leverage_x", "dscr_x", "current_ratio_x"])
    out["financials"] = {k: {"min": float(b[k].min()), "max": float(b[k].max()), "p01": float(b[k].quantile(0.01)),
                             "p99": float(b[k].quantile(0.99))} for k in b.columns}
    return out


def out_of_range(feats: dict[str, float], p: dict[str, Any] | None = None) -> dict[str, Any]:
    r = training_ranges()
    rows = []
    for k, v in feats.items():
        lim = r["features"].get(k)
        if lim is None or k in ("stage", "dpd"):
            continue
        st = "out_of_range" if v < lim["min"] or v > lim["max"] else "edge" if v < lim["p01"] or v > lim["p99"] else "in_range"
        rows.append({"feature": k, "value": v, **lim, "status": st, "kind": "model"})
    if p is not None:
        ys = [y for y in p["financials"]["years"] if y["kind"] == "actual"]
        if ys:
            y = ys[-1]
            fin = {"leverage_x": y["total_debt"] / y["ebitda"] if y["ebitda"] > 0 else np.inf,
                   "dscr_x": y["ebitda"] / y["debt_service"] if y["debt_service"] > 0 else np.inf,
                   "current_ratio_x": y.get("current_ratio", np.nan)}
            for k, v in fin.items():
                lim = r["financials"][k]
                if not np.isfinite(v):
                    continue
                st = "out_of_range" if v < lim["min"] or v > lim["max"] else "edge" if v < lim["p01"] or v > lim["p99"] else "in_range"
                rows.append({"feature": k, "value": float(v), **lim, "status": st, "kind": "financial (book range)"})
    model_rows = [x for x in rows if x["kind"] == "model"]
    status = ("out_of_range" if any(x["status"] == "out_of_range" for x in model_rows)
              else "edge" if any(x["status"] == "edge" for x in model_rows) else "in_range")
    return {"status": status, "flagged": [x["feature"] for x in rows if x["status"] != "in_range"], "features": rows,
            "range_source": r["source"]}


def model_card(p: dict[str, Any] | None = None) -> dict[str, Any]:
    xgb = _xgb()
    card = xgb.card(BOOK)["targets"]["pd"]
    meta = model_meta()
    out = {"model": meta, "role": "Obligor 12-month PIT PD and 5-year term structure only",
           "target": "logit of the annual conditional PD h(s, t), offset by the logit of the bank's 12-month PD",
           "scores": "facilities; Deal Desk freezes the facility-term features at the obligor's reference profile",
           "frozen_features": list(TERM_FEATURES), "obligor_features": list(OBLIGOR_FEATURES),
           "path_features": ["year", "cycle_z", "cycle_anchor"],
           "deal_terms_in_model": [], "leverage_dscr_features": False,
           "training": {"domain": "What-If corporate IFRS 9 domain", "periods": "2021Q3-2026Q2", "rows": 384009,
                        "split": "random 70/30 (served), out-of-time cut 2024Q4"},
           "calibration": {"random_test": card["random"]["test_probability"], "out_of_time_test": card["out_of_time"]["test_probability"],
                           "deciles": card["calibration"]},
           "importance": card["importance"][:8], "monotone_constraints": meta["monotone"],
           "years_after_5": "model year-5 hazard x the migration matrix hazard shape",
           "limitations": ["The target is the bank's stored IFRS 9 PD term structure, not observed defaults.",
                           "No financial-statement or SIMAH features: post-deal leverage and DSCR act through limits only.",
                           "Out-of-time calibration under-predicts low-risk deciles by 5-20%."]}
    if p is not None:
        o = obligor_pd(p)
        out["proposal"] = {"proposal_id": p["proposal_id"], "features": o["features"], "provenance": o["provenance"],
                           "pd_12m": o["pd_12m"], "master_scale_pd_12m": o["master_scale_pd_12m"],
                           "monotonicity": o["monotonicity"], "out_of_range": o["out_of_range"]}
    return out
