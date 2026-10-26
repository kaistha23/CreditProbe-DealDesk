"""Quarterly transition models for Deal Desk forward risk (PLAN_R11 Session F, F1).

Two binary models on the corporate facility-quarter panel (the books Early Warning and What-If read):

  stage2   P(Stage 2 or worse at q+1 | Stage 1 at q)
  dpd30    P(30+ DPD at q+1 | under 30 DPD at q)

Features are only what a new deal also has: rating and TTC PD, sector, region, size, utilisation,
collateral cover, product and facility class, months on book (0 for a new deal), the obligor's DPD
history and worst stage on its other facilities, its financial ratios, the Early Warning signals the
book holds at obligor level, and the sector's position in the credit cycle (its Stage 2 and 30+ shares
and last quarter's flows, all known at q).

Left out on purpose (STATUS_R11_FORWARD D14): quarters on book (the book's facilities in their first quarter move to
Stage 2 at 22% against 3% afterwards, a cohort a new deal does not belong to), the current ratio (the book's sits in a
narrow 1.42-1.84 band where any dip marks distress, so a proposal's audited 1.2-1.5 would read as distress) and interest
cover (no proposal carries it; DSCR covers debt service).

Training (in the session only; xgboost is NOT a runtime dependency, N3):
    python -m backend.dealdesk.transition_model train
fits gradient-boosted trees with monotone constraints, validates out of time (train on the origin
quarters up to 2025Q1, test on the last 4), calibrates isotonically and exports to
data/dealdesk/model/transition/: the trees as xgboost JSON, the calibration as a table, the model
card, the back-test and the as-of book statistics the scorer needs.

Scoring (runtime): `Forest` is a pure numpy evaluator of the JSON trees (the What-If pattern,
backend/whatif_v5/models/xgb.py) that also returns per-feature contributions (Saabas path
attribution in log-odds), so drivers need no extra library either.
"""
from __future__ import annotations

import functools
import hashlib
import json
import math
from typing import Any

import numpy as np

from backend.dealdesk import paths

MODEL_DIR = paths.DATA / "model" / "transition"
VERSION = "dd-transition-1.0.0"
SEED = 20261017
TARGETS = ("stage2", "dpd30")
TARGET_LABEL = {"stage2": "P(Stage 2 or worse at q+1 | Stage 1 at q)",
                "dpd30": "P(30+ DPD at q+1 | under 30 DPD at q)"}
OOT_QUARTERS = 4
CAL_QUARTERS = 2  # the first two OOT quarters fit the isotonic map; the last two test it

#: (name, plain-language label, monotone sign: +1 risk rises with the value, -1 falls, 0 free)
FEATURES: list[tuple[str, str, int]] = [
    ("grade_rank", "Internal rating (notches from AAA)", 1),
    ("log_pd_ttc", "TTC PD of the rating", 1),
    ("sector_code", "Sector", 0),
    ("region_code", "Region", 0),
    ("product_code", "Product", 0),
    ("funded", "Funded facility", 0),
    ("log_limit", "Facility size", 0),
    ("utilisation_pct", "Utilisation", 1),
    ("collateral_cover_pct", "Collateral cover after haircut", -1),
    ("obl_dpd_max_4q", "Obligor's worst DPD in the last 4 quarters", 1),
    ("obl_stage_max", "Obligor's worst stage on other facilities", 1),
    ("leverage_x", "Leverage (debt / EBITDA)", 1),
    ("dscr_x", "Debt service cover", -1),
    ("ebitda_margin_pct", "EBITDA margin", -1),
    ("watchlist_flag", "On watchlist", 1),
    ("rating_notches_moved", "Rating move this quarter (negative = downgrade)", -1),
    ("external_dpd_days", "Past due at other lenders (bureau)", 1),
    ("enquiries_q", "Bureau enquiries this quarter", 1),
    ("inflow_trend_pct", "Operating inflows, change on the year", -1),
    ("balance_buffer_months", "Operating balance buffer (months)", -1),
    ("returned_payments_q", "Returned payments this quarter", 1),
    ("sec_s2_share", "Sector Stage 2 share of the book", 1),
    ("sec_dpd30_share", "Sector 30+ DPD share of the book", 1),
    ("sec_s2_flow", "Sector Stage 1 to 2 flow last quarter", 1),
    ("sec_dpd30_flow", "Sector flow into 30+ DPD last quarter", 1),
]
FEATURE_NAMES = [f[0] for f in FEATURES]
LABELS = {f[0]: f[1] for f in FEATURES}
#: Features a deal's terms move (the rest describe the obligor and its sector).
STRUCTURE_FEATURES = ("utilisation_pct", "collateral_cover_pct", "log_limit", "product_code", "funded")
PRODUCT_OF_FACILITY = {"term_loan": "term_loan", "revolver": "revolving_credit", "performance_lg": "trade_finance",
                       "financial_lg": "trade_finance", "trade_lc": "trade_finance"}
FUNDED_OF_FACILITY = {"term_loan": 1.0, "revolver": 1.0, "performance_lg": 0.0, "financial_lg": 0.0, "trade_lc": 0.0}
XGB_PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "tree_method": "hist", "max_depth": 4, "eta": 0.05,
              "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 50, "lambda": 2.0, "seed": SEED, "nthread": 2}
ROUNDS = 350


# ------------------------------------------------------------------ pure evaluator (runtime)

class Forest:
    """An xgboost binary:logistic JSON model evaluated with numpy, with Saabas contributions.

    `margin(x)` equals xgboost's output_margin; `contributions(x)` returns (n, features + 1) log-odds
    contributions whose row sums equal the margin (the last column is the bias)."""

    def __init__(self, model_json: dict[str, Any], eta: float | None = None):
        learner = model_json["learner"]
        bs = learner["learner_model_param"]["base_score"]
        base = float(np.asarray(json.loads(bs) if bs.startswith("[") else bs, dtype=float).ravel()[0])
        self.base_margin = math.log(base / (1 - base))
        self.n_features = int(learner["learner_model_param"]["num_feature"])
        # xgboost stores leaf weights already scaled by the learning rate and internal-node weights unscaled
        eta = float(XGB_PARAMS["eta"] if eta is None else eta)
        self.trees = []
        for t in learner["gradient_booster"]["model"]["trees"]:
            left = np.asarray(t["left_children"], dtype=np.int64)
            w = np.asarray(t["base_weights"], dtype=np.float64)
            w = np.where(left == -1, w, w * eta)
            self.trees.append((left, np.asarray(t["right_children"], dtype=np.int64),
                               np.asarray(t["split_indices"], dtype=np.int64), np.asarray(t["split_conditions"], dtype=np.float32),
                               np.asarray(t["default_left"], dtype=bool), w))

    def _walk(self, x: np.ndarray, contrib: np.ndarray | None) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        n = len(x)
        out = np.full(n, self.base_margin)
        rows = np.arange(n)
        for left, right, idx, cond, dleft, w in self.trees:
            node = np.zeros(n, dtype=np.int64)
            if contrib is not None:
                contrib[:, -1] += w[0]
            while True:
                leaf = left[node] == -1
                if leaf.all():
                    break
                v = x[rows, idx[node]]
                go_left = np.where(np.isnan(v), dleft[node], v < cond[node])
                nxt = np.where(leaf, node, np.where(go_left, left[node], right[node]))
                if contrib is not None:
                    moved = ~leaf
                    np.add.at(contrib, (rows[moved], idx[node][moved]), w[nxt][moved] - w[node][moved])
                node = nxt
            out += w[node]
        return out

    def margin(self, x: np.ndarray) -> np.ndarray:
        return self._walk(x, None)

    def contributions(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(x)
        c = np.zeros((len(x), self.n_features + 1))
        c[:, -1] = self.base_margin
        self._walk(x, c)
        return c


def expit(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def calibrate(raw: np.ndarray, table: dict[str, list[float]]) -> np.ndarray:
    """Isotonic map exported as breakpoints: piecewise-linear, non-decreasing, clipped to the table ends."""
    return np.clip(np.interp(np.asarray(raw, dtype=float), table["x"], table["y"]), 0.0, 1.0)


@functools.lru_cache(maxsize=1)
def meta() -> dict[str, Any]:
    return json.loads((MODEL_DIR / "transition.json").read_text())


@functools.lru_cache(maxsize=4)
def forest(target: str) -> Forest:
    m = meta()["models"][target]
    body = (MODEL_DIR / m["file"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != m["sha256"]:
        raise RuntimeError(f"{m['file']} does not match its recorded sha256; refusing to use it.")
    return Forest(json.loads(body))


def available() -> bool:
    return (MODEL_DIR / "transition.json").exists()


def matrix(rows: list[dict[str, float]]) -> np.ndarray:
    return np.array([[float(r.get(k, np.nan)) if r.get(k) is not None else np.nan for k in FEATURE_NAMES] for r in rows],
                    dtype=float)


def score(target: str, rows: list[dict[str, float]], with_contributions: bool = False) -> dict[str, Any]:
    """Calibrated probabilities for feature rows (dicts by feature name; missing = NaN, as in training)."""
    x = matrix(rows)
    f = forest(target)
    cal = meta()["models"][target]["calibration"]
    if with_contributions:
        c = f.contributions(x)
        m = c.sum(1)
    else:
        c, m = None, f.margin(x)
    raw = expit(m)
    out = {"raw": raw, "p": calibrate(raw, cal), "margin": m}
    if c is not None:
        out["contributions"] = c
    return out


def card() -> dict[str, Any]:
    return json.loads((MODEL_DIR / "card.json").read_text())


def backtest() -> dict[str, Any]:
    return json.loads((MODEL_DIR / "backtest.json").read_text())


# ------------------------------------------------------------------ panel (training and book lookups)

def _q_index(q: Any) -> Any:
    s = q.astype(str)
    return s.str[:4].astype(int) * 4 + s.str[-1].astype(int) - 1


def build_panel():
    """The facility-quarter panel with features at q and outcomes at q+1. Reads the books read-only."""
    import pandas as pd
    from backend.ews_domain import paths as ews_paths

    ews = ews_paths.DATASETS / ews_paths.EWS_CORP
    e = pd.read_parquet(ews / "ews_corp_exposure.parquet", columns=[
        "facility_id", "borrower_id", "reporting_quarter", "product_type", "facility_class", "sector", "region",
        "limit_sar_mn", "utilisation_pct", "ead_sar_mn", "stage", "dpd_days", "origination_quarter", "watchlist_flag",
        "rating_notches_moved", "external_dpd_days", "enquiries_q", "inflow_trend_pct", "balance_buffer_months",
        "returned_payments_q", "ews_score", "ews_band"])
    b = pd.read_parquet(paths.book_relation("corp_borrower_quarter"), columns=[
        "borrower_id", "reporting_quarter", "rating_current", "pd_ttc_12m", "leverage_x", "dscr_x", "interest_cover_x",
        "current_ratio_x", "ebitda_margin_pct"])
    c = pd.read_parquet(paths.book_relation("corp_collateral_quarter"), columns=["facility_id", "reporting_quarter", "coverage_pct"])
    c = c.groupby(["facility_id", "reporting_quarter"], as_index=False)["coverage_pct"].sum()
    f = e.merge(b, on=["borrower_id", "reporting_quarter"], how="left").merge(c, on=["facility_id", "reporting_quarter"], how="left")
    f["qi"] = _q_index(f["reporting_quarter"])
    f["age_q"] = (f["qi"] - _q_index(f["origination_quarter"])).clip(lower=0)
    f = f.sort_values(["facility_id", "qi"]).reset_index(drop=True)
    g = f.groupby("facility_id")
    f["stage_next"] = g["stage"].shift(-1)
    f["dpd_next"] = g["dpd_days"].shift(-1)
    f["qi_next"] = g["qi"].shift(-1)
    f.loc[f["qi_next"] != f["qi"] + 1, ["stage_next", "dpd_next"]] = np.nan
    # obligor history: worst DPD over the last 4 quarters, worst stage now (all its facilities)
    ob = f.groupby(["borrower_id", "qi"], as_index=False).agg(dpd_max=("dpd_days", "max"), stage_max=("stage", "max"))
    ob = ob.sort_values(["borrower_id", "qi"])
    ob["obl_dpd_max_4q"] = ob.groupby("borrower_id")["dpd_max"].transform(lambda s: s.rolling(4, min_periods=1).max())
    f = f.merge(ob[["borrower_id", "qi", "obl_dpd_max_4q", "stage_max"]], on=["borrower_id", "qi"], how="left")
    f["obl_stage_max"] = f["stage_max"]
    # sector cycle at q (stock) and last quarter's flows (q-1 -> q): known at q
    f["is_s2p"] = (f["stage"] >= 2).astype(float)
    f["is_30"] = (f["dpd_days"] >= 30).astype(float)
    sec = f.groupby(["sector", "qi"]).agg(sec_s2_share=("is_s2p", "mean"), sec_dpd30_share=("is_30", "mean")).reset_index()
    s1 = f[(f["stage"] == 1) & f["stage_next"].notna()]
    fl = s1.assign(y=(s1["stage_next"] >= 2).astype(float)).groupby(["sector", "qi"])["y"].mean().rename("sec_s2_flow")
    d0 = f[(f["dpd_days"] < 30) & f["dpd_next"].notna()]
    fd = d0.assign(y=(d0["dpd_next"] >= 30).astype(float)).groupby(["sector", "qi"])["y"].mean().rename("sec_dpd30_flow")
    flows = pd.concat([fl, fd], axis=1).reset_index()
    flows["qi"] = flows["qi"] + 1  # the flow from q-1 to q is known at q
    sec = sec.merge(flows, on=["sector", "qi"], how="left")
    f = f.merge(sec, on=["sector", "qi"], how="left")
    enc = {"sector": {v: i for i, v in enumerate(sorted(f["sector"].dropna().unique()))},
           "region": {v: i for i, v in enumerate(sorted(f["region"].dropna().unique()))},
           "product": {v: i for i, v in enumerate(sorted(f["product_type"].dropna().unique()))}}
    from backend.v5common.ratings import rank
    f["grade_rank"] = f["rating_current"].map(rank).astype(float)
    f["log_pd_ttc"] = np.log(f["pd_ttc_12m"].clip(lower=1e-5))
    f["sector_code"] = f["sector"].map(enc["sector"]).astype(float)
    f["region_code"] = f["region"].map(enc["region"]).astype(float)
    f["product_code"] = f["product_type"].map(enc["product"]).astype(float)
    f["funded"] = (f["facility_class"] == "funded").astype(float)
    f["log_limit"] = np.log1p(f["limit_sar_mn"].clip(lower=0))
    f["collateral_cover_pct"] = f["coverage_pct"].fillna(0.0)
    return f, enc


# ------------------------------------------------------------------ metrics

def auc(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p))
    sp = p[order]
    i = 0
    r = np.arange(1, len(p) + 1, dtype=float)
    # average ranks for ties
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        r[i:j + 1] = (i + j + 2) / 2.0
        i = j + 1
    ranks[order] = r
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def ks(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-np.asarray(p))
    y = np.asarray(y, dtype=float)[order]
    n1, n0 = y.sum(), len(y) - y.sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float(np.max(np.abs(np.cumsum(y) / n1 - np.cumsum(1 - y) / n0)))


def psi(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    edges = np.unique(np.quantile(a, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    pa = np.histogram(a, edges)[0] / len(a)
    pb = np.histogram(b, edges)[0] / len(b)
    pa, pb = np.clip(pa, 1e-6, None), np.clip(pb, 1e-6, None)
    return float(((pa - pb) * np.log(pa / pb)).sum())


def deciles(y: np.ndarray, p: np.ndarray) -> list[dict[str, float]]:
    order = np.argsort(p, kind="mergesort")
    out = []
    for k, idx in enumerate(np.array_split(order, 10)):
        out.append({"decile": k + 1, "n": int(len(idx)), "predicted": float(np.mean(p[idx])), "actual": float(np.mean(y[idx]))})
    return out


def _isotonic(raw: np.ndarray, y: np.ndarray, max_points: int = 60) -> dict[str, list[float]]:
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw, y)
    xs = np.asarray(iso.X_thresholds_, dtype=float)
    ys = np.asarray(iso.y_thresholds_, dtype=float)
    if len(xs) > max_points:
        keep = np.unique(np.round(np.linspace(0, len(xs) - 1, max_points)).astype(int))
        xs, ys = xs[keep], ys[keep]
    ys = np.maximum.accumulate(ys)
    # a strictly positive floor and anchors at 0 and 1 keep the map defined everywhere
    lo = max(float(ys[0]), 1e-5)
    xs = np.concatenate([[0.0], xs, [1.0]])
    ys = np.concatenate([[min(lo, float(ys[0]) if ys[0] > 0 else lo)], np.maximum(ys, lo), [max(float(ys[-1]), lo)]])
    xs, idx = np.unique(xs, return_index=True)
    return {"x": xs.tolist(), "y": np.maximum.accumulate(ys[idx]).tolist()}


# ------------------------------------------------------------------ training (session only)

def train() -> dict[str, Any]:  # pragma: no cover - run once in the build session
    import time

    import xgboost as xgb

    t0 = time.time()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    f, enc = build_panel()
    qs = sorted(f["qi"].unique())
    last_origin = qs[-2]  # the last quarter with an observed q+1
    oot = qs[-1 - OOT_QUARTERS:-1]
    cal_q, test_q = oot[:CAL_QUARTERS], oot[CAL_QUARTERS:]
    qname = dict(zip(f["qi"], f["reporting_quarter"]))
    mono = "(" + ",".join(str(s) for _, _, s in FEATURES) + ")"
    models, cards, back = {}, {}, {}
    for target in TARGETS:
        if target == "stage2":
            d = f[(f["stage"] == 1) & f["stage_next"].notna()].copy()
            d["y"] = (d["stage_next"] >= 2).astype(int)
        else:
            d = f[(f["dpd_days"] < 30) & f["dpd_next"].notna()].copy()
            d["y"] = (d["dpd_next"] >= 30).astype(int)
        tr = d[d["qi"] < oot[0]]
        x_tr = tr[FEATURE_NAMES].to_numpy(dtype=float)
        # in-time hold-out: a random 20% of the training quarters (by facility, so no leakage across quarters)
        rng = np.random.default_rng(SEED)
        facs = tr["facility_id"].unique()
        hold = set(rng.choice(facs, size=len(facs) // 5, replace=False))
        m_in = tr["facility_id"].isin(hold).to_numpy()
        dtr = xgb.DMatrix(x_tr[~m_in], label=tr["y"].to_numpy()[~m_in], feature_names=FEATURE_NAMES)
        dho = xgb.DMatrix(x_tr[m_in], label=tr["y"].to_numpy()[m_in], feature_names=FEATURE_NAMES)
        params = {**XGB_PARAMS, "monotone_constraints": mono}
        booster = xgb.train(params, dtr, ROUNDS, evals=[(dho, "holdout")], verbose_eval=False)
        raw_path = MODEL_DIR / f"{target}.json"
        booster.save_model(str(raw_path))
        body = raw_path.read_bytes()
        fo = Forest(json.loads(body))
        # equivalence of the numpy evaluator with xgboost, margins and contributions
        x_all = d[FEATURE_NAMES].to_numpy(dtype=float)
        samp = np.random.default_rng(1).choice(len(x_all), size=min(5000, len(x_all)), replace=False)
        xm = xgb.DMatrix(x_all[samp], feature_names=FEATURE_NAMES)
        ref = booster.predict(xm, output_margin=True)
        mine = fo.margin(x_all[samp])
        ctr = fo.contributions(x_all[samp])
        ref_c = booster.predict(xm, pred_contribs=True, approx_contribs=True)
        equiv = {"rows": int(len(samp)), "max_abs_margin_diff": float(np.max(np.abs(ref - mine))),
                 "max_abs_contribution_sum_diff": float(np.max(np.abs(ctr.sum(1) - mine))),
                 "max_abs_contribution_diff_vs_xgboost_saabas": float(np.max(np.abs(ctr - ref_c)))}
        raw_all = expit(fo.margin(x_all))
        d["raw"] = raw_all
        cal_mask = d["qi"].isin(cal_q).to_numpy()
        cal_val = _isotonic(raw_all[cal_mask], d["y"].to_numpy()[cal_mask])
        d["p_val"] = calibrate(raw_all, cal_val)
        # served map: refit on all four out-of-time quarters (the latest experience); discrimination is unaffected
        cal = _isotonic(raw_all[d["qi"].isin(oot).to_numpy()], d["y"].to_numpy()[d["qi"].isin(oot).to_numpy()])
        d["p"] = calibrate(raw_all, cal)

        def block(mask: np.ndarray, col: str = "p") -> dict[str, Any]:
            y, p = d["y"].to_numpy()[mask], d[col].to_numpy()[mask]
            a = auc(y, p)
            return {"n": int(mask.sum()), "events": int(y.sum()), "event_rate": float(y.mean()), "mean_predicted": float(p.mean()),
                    "auc": a, "gini": 2 * a - 1, "ks": ks(y, p)}

        trmask = (d["qi"] < oot[0]).to_numpy()
        ho_mask = trmask & d["facility_id"].isin(hold).to_numpy()
        oot_mask = d["qi"].isin(oot).to_numpy()
        test_mask = d["qi"].isin(test_q).to_numpy()
        imp = booster.get_score(importance_type="total_gain")
        tot = sum(imp.values()) or 1.0
        importance = sorted(({"feature": k, "label": LABELS[k], "share": v / tot} for k, v in imp.items()), key=lambda r: -r["share"])
        # monotonicity proof on the trained trees: perturb each constrained feature up on a sample
        mono_check = []
        xs = x_all[samp].copy()
        base_m = fo.margin(xs)
        for j, (name, _, s) in enumerate(FEATURES):
            if s == 0:
                continue
            col = xs[:, j]
            step = np.nanstd(col) or 1.0
            x2 = xs.copy()
            x2[:, j] = np.where(np.isnan(col), col, col + step)
            dm = (fo.margin(x2) - base_m) * s
            mono_check.append({"feature": name, "sign": s, "min_change": float(np.nanmin(dm[~np.isnan(col)])) if (~np.isnan(col)).any() else 0.0,
                               "violations": int((dm[~np.isnan(col)] < -1e-9).sum())})
        bt = []
        for q in qs[:-1]:
            m = (d["qi"] == q).to_numpy()
            if m.sum() == 0:
                continue
            bt.append({"quarter": qname[q], "next_quarter": qname[q + 1], "n": int(m.sum()), "actual": float(d["y"].to_numpy()[m].mean()),
                       "predicted": float(d["p"].to_numpy()[m].mean()),
                       "predicted_validation_map": float(d["p_val"].to_numpy()[m].mean()), "raw_predicted": float(d["raw"].to_numpy()[m].mean()),
                       "sample": "out-of-time" if q in oot else "training"})
        # book rate at the as-of quarter: the last observed transition and the model's mean on the as-of stock
        cards[target] = {
            "target": TARGET_LABEL[target], "rows": int(len(d)), "events": int(d["y"].sum()),
            "train_quarters": f"{qname[qs[0]]}-{qname[oot[0] - 1]} (origin quarter q)", "oot_quarters": f"{qname[oot[0]]}-{qname[oot[-1]]}",
            "calibration_quarters": [qname[q] for q in cal_q], "calibration_test_quarters": [qname[q] for q in test_q],
            "in_time": block(ho_mask), "out_of_time": block(oot_mask), "out_of_time_raw": block(oot_mask, "raw"),
            "calibration_test": block(test_mask, "p_val"),
            "calibration_note": (f"Validation map fitted on {', '.join(qname[q] for q in cal_q)} and tested on "
                                 f"{', '.join(qname[q] for q in test_q)}; the served map is refitted on all four out-of-time quarters."),
            "calibration_deciles_oot": deciles(d["y"].to_numpy()[oot_mask], d["p"].to_numpy()[oot_mask]),
            "calibration_deciles_test": deciles(d["y"].to_numpy()[test_mask], d["p_val"].to_numpy()[test_mask]),
            "psi_train_vs_oot": psi(d["raw"].to_numpy()[trmask], d["raw"].to_numpy()[oot_mask]),
            "psi_train_vs_last_quarter": psi(d["raw"].to_numpy()[trmask], d["raw"].to_numpy()[(d["qi"] == last_origin).to_numpy()]),
            "importance": importance, "monotone": mono_check, "evaluator_equivalence": equiv,
            "trees": ROUNDS, "params": {k: v for k, v in params.items() if k != "nthread"}}
        back[target] = bt
        models[target] = {"file": raw_path.name, "sha256": hashlib.sha256(body).hexdigest(), "calibration": cal,
                          "book_rate_last_observed": bt[-1]["actual"], "book_rate_last_quarter": bt[-1]["quarter"],
                          "book_mean_predicted_as_of": None}
    # as-of book statistics the scorer needs
    as_of_q = qs[-1]
    cur = f[f["qi"] == as_of_q]
    for target in TARGETS:
        pop = cur[cur["stage"] == 1] if target == "stage2" else cur[cur["dpd_days"] < 30]
        pr = calibrate(expit(Forest(json.loads((MODEL_DIR / models[target]["file"]).read_bytes())).margin(
            pop[FEATURE_NAMES].to_numpy(dtype=float))), models[target]["calibration"])
        models[target]["book_mean_predicted_as_of"] = float(pr.mean())
        models[target]["book_percentiles_as_of"] = {str(k): float(np.percentile(pr, k)) for k in (10, 25, 50, 75, 90)}
    perf = cur[cur["stage"] == 1]
    neutral = {k: float(perf[k].median()) for k in ("enquiries_q", "inflow_trend_pct", "balance_buffer_months", "returned_payments_q",
                                                    "external_dpd_days", "ebitda_margin_pct", "leverage_x", "dscr_x")}
    sector_now = cur.groupby("sector").agg(sec_s2_share=("sec_s2_share", "first"), sec_dpd30_share=("sec_dpd30_share", "first"),
                                           sec_s2_flow=("sec_s2_flow", "first"), sec_dpd30_flow=("sec_dpd30_flow", "first"))
    book_now = {"sec_s2_share": float(cur["is_s2p"].mean()), "sec_dpd30_share": float(cur["is_30"].mean()),
                "sec_s2_flow": float(np.average(sector_now["sec_s2_flow"].fillna(0))), "sec_dpd30_flow": float(np.average(sector_now["sec_dpd30_flow"].fillna(0)))}
    # Stage 2 row of the quarterly chain: cure and default rates observed in the book (all quarters)
    s2 = f[(f["stage"] == 2) & f["stage_next"].notna()]
    s1 = f[(f["stage"] == 1) & f["stage_next"].notna()]
    chain = {"s2_to_s1": float((s2["stage_next"] == 1).mean()), "s2_to_s3": float((s2["stage_next"] == 3).mean()),
             "s1_to_s3_share_of_s2plus": float((s1["stage_next"] == 3).sum() / max(1, (s1["stage_next"] >= 2).sum())),
             "rows_s2": int(len(s2)), "basis": f"observed facility transitions {qname[qs[0]]}-{qname[as_of_q]}"}
    # EWS score distribution of the book at the as-of quarter (borrower level, worst facility)
    bw = cur.groupby("borrower_id")["ews_score"].max()
    ews_book = {"borrowers": int(len(bw)), "score_percentiles": {str(k): float(np.percentile(bw, k)) for k in (25, 50, 75, 90, 95)},
                "band_share": cur.groupby("borrower_id")["ews_band"].first().value_counts(normalize=True).to_dict(),
                "scores": np.bincount(bw.astype(int).to_numpy()).tolist()}
    meta_out = {"version": VERSION, "trained": time.strftime("%Y-%m-%d", time.gmtime()), "as_of": qname[as_of_q],
                "features": [{"name": n, "label": lbl, "monotone": s} for n, lbl, s in FEATURES],
                "encodings": enc, "models": models, "sector_as_of": sector_now.reset_index().to_dict("records"), "book_as_of": book_now,
                "chain": chain, "ews_book": ews_book, "neutral": neutral,
                "neutral_basis": f"median over the Stage 1 facilities of the book at {qname[as_of_q]}",
                "source": {"exposure": "data/ews/ews-saudi-corporate-20q-v4e2/ews_corp_exposure.parquet",
                           "borrower": "data/cockpit_v4_lake/v4-saudi-corporate-20q-v4/corp_borrower_quarter.parquet",
                           "collateral": "data/cockpit_v4_lake/v4-saudi-corporate-20q-v4/corp_collateral_quarter.parquet"},
                "seconds": round(time.time() - t0, 1)}
    (MODEL_DIR / "transition.json").write_text(json.dumps(meta_out, indent=1, default=float))
    card_out = {"version": VERSION, "trained": meta_out["trained"], "method": "xgboost gradient-boosted trees, binary:logistic, "
                f"{ROUNDS} trees of depth {XGB_PARAMS['max_depth']}, monotone constraints; isotonic calibration; numpy evaluator at runtime",
                "split": "out-of-time: train on origin quarters before the last 4; in-time = random 20% of facilities in the training quarters",
                "targets": cards,
                "limitations": [
                    "The book publishes no maturity date: tenor and remaining tenor are not features; tenor reaches forward "
                    "risk through the engine's PD term structure and ECL only.",
                    "The book carries no 1-29 DPD values, so 30+ DPD is the first arrears bucket the model can see.",
                    "30+ DPD events are rare and bunched in 2025Q4-2026Q1: the OOT rate rises several-fold, so the validation "
                    "map (fitted on the first two OOT quarters) under-predicts the last two; the served map is refitted on all four.",
                    "The book makes early-period 30+ DPD almost a deterministic function of DSCR and interest cover "
                    "(in-time AUC near 1.0); the out-of-time AUC is the figure to rely on.",
                    "Guarantees and covenant packages are not book features: they reach forward risk through the engine's PD and ECL, "
                    "not through the transition models.",
                    "A new-to-bank obligor has no open-banking signals or bureau enquiry count in the book: those features take "
                    "the book's Stage 1 median (neutral); bureau past-due comes from the SIMAH flag.",
                    "Quarters on book, current ratio and interest cover are left out: the book's first-quarter cohort and its "
                    "narrow current-ratio band do not transfer to a new deal's audited figures.",
                    "Sector cycle features are as of the book's last quarter (2026Q2) for every deal."]}
    (MODEL_DIR / "card.json").write_text(json.dumps(card_out, indent=1, default=float))
    (MODEL_DIR / "backtest.json").write_text(json.dumps({"version": VERSION, "by_quarter": back}, indent=1, default=float))
    return {"card": card_out, "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        r = train()
        for t, c in r["card"]["targets"].items():
            print(t, "in-time AUC %.3f" % c["in_time"]["auc"], "OOT AUC %.3f" % c["out_of_time"]["auc"],
                  "OOT KS %.3f" % c["out_of_time"]["ks"], "PSI %.3f" % c["psi_train_vs_oot"], c["evaluator_equivalence"])
        print("seconds", r["seconds"])
