"""The XGBoost method: models trained on the What-If domain, a scenario applied by changing features.

Models (per book), each a gradient-boosted tree ensemble (XGBoost, fixed seed,
saved as JSON with its sha256 checked on load):
  pd    target logit of the annual conditional PD h(s, t), one row per exposure,
        period, scenario s and year t, with the log-odds of the bank's 12-month PD
        input as the offset (base margin): the trees learn the adjustment by year
        and by credit cycle
  lgd   target LGD(s, t), same rows
  ecl12 / ecllt   target 12-month and lifetime ECL coverage (ECL / EAD), one row
        per exposure and period: the ECL components, used as a cross-check on the card

Features: the IFRS 9 inputs (segment, sub-segment, product, stage, rating or
scores, notches from origination, TTC PD, the 12-month PD and LGD inputs,
collateral type, secured share, haircut, EAD, CCF, undrawn share, DPD), the
year t, the segment's credit-cycle index in year t of the path (the 11 MEVs
through the estimated elasticities) and the cycle anchor (the weighted year-1
index the 12-month PD is calibrated at). The ECL-component models also see the
base path's MEVs.
The lifetime PD, the scenario term structures and the ECL columns are never
features (they are what the models predict).

Two splits, both reported on the model card: random 70/30 over exposure-periods,
and out-of-time (the first 70% of periods train, the last 30% test). The served
models are the random-split models.

Applying a scenario: rating notches change the grade, the TTC PD (masterscale)
and the notches from origination (behaviour score for retail); sector stress
moves the segment's cycle index; an MEV shock replaces the path's MEVs and the
cycle index; the models then predict. PD/LGD/CCF deltas and staging are applied
by the engine exactly as for the Delta method. The starting ECL is the models'
own prediction without the scenario, shown next to the reported ECL.
"""
from __future__ import annotations

import functools
import hashlib
import json
import pathlib
import threading
import time
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5 import paths
from backend.whatif_v5.domain import cycle, mev, store
from backend.whatif_v5.models.engine import PD_CAP, Context, Method, Start, grade_scale

MODEL_DIR = paths.V5 / "data" / "whatif_v5" / "models"
METHOD_VERSION = "xgb-1.0.0"
SEED = 20261011
PARAMS = {"objective": "reg:squarederror", "tree_method": "hist", "max_depth": 6, "eta": 0.08,
          "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 20, "lambda": 1.0,
          "seed": SEED, "nthread": 1}
ROUNDS = 400
LOGIT_FLOOR = 1e-6
SCN_CODE = {"base": 0, "upturn": 1, "downturn": 2}
MEV_KEYS = [s.key for s in mev.SERIES]
_LOCK = threading.Lock()


class ModelError(RuntimeError):
    pass


def static_features(domain: str) -> list[str]:
    common = ["segment_code", "subsegment_code", "product_code", "stage", "grade_rank", "pd_ttc", "pd_12m_input",
              "lgd_input", "collateral_code", "secured_share", "haircut_pct", "log_ead", "ccf", "undrawn_share", "dpd"]
    return common + (["nfo"] if domain == "corporate" else ["behaviour_score", "application_score"])


def path_features() -> list[str]:
    # Macro reaches the PD and LGD models through the segment's credit-cycle index on the path
    # (built from the 11 MEVs by the estimated elasticities). No scenario label and no raw MEV
    # levels: with 20 periods x 3 paths the trees would otherwise memorise path combinations
    # instead of learning the cycle. (A monotone constraint on the cycle index was tried and
    # dropped: it cost 10% bias and R2 0.99 -> 0.86; the signs hold without it, see the card.)
    # cycle_anchor: the probability-weighted year-1 cycle index of the segment's three unshocked paths
    # at the period -- the point each exposure's 12-month PD is calibrated at. PD depends on the
    # path's cycle relative to it; a shock moves cycle_z, never the anchor.
    return ["year", "cycle_z", "cycle_anchor"]


def monotone(domain: str, target: str) -> str:
    feats = features(domain, target)
    sign = {"cycle_z": "-1", "cycle_anchor": "1"}
    return "(" + ",".join(sign.get(f, "0") for f in feats) + ")"


def features(domain: str, target: str) -> list[str]:
    if target in ("ecl12", "ecllt"):
        return static_features(domain) + ["cycle_z_y1"] + [f"mev_{k}" for k in MEV_KEYS]
    return static_features(domain) + path_features()


# ------------------------------------------------------------------ encoding

def encodings(domain: str) -> dict[str, dict[str, int]]:
    f = store.frame(domain)
    enc = {}
    for col, name in (("segment", "segment_code"), ("subsegment", "subsegment_code"), ("product", "product_code"),
                      ("collateral_type", "collateral_code")):
        enc[name] = {v: i for i, v in enumerate(sorted(store.history(domain, [col])[col].astype(str).unique()))}
    return enc


def static_frame(domain: str, f: pd.DataFrame, enc: dict[str, dict[str, int]]) -> pd.DataFrame:
    x = pd.DataFrame(index=f.index)
    for col, name in (("segment", "segment_code"), ("subsegment", "subsegment_code"), ("product", "product_code"),
                      ("collateral_type", "collateral_code")):
        x[name] = f[col].astype(str).map(enc[name]).fillna(-1).astype(float)
    x["stage"] = f["stage"].astype(float)
    x["grade_rank"] = f["grade_rank"].astype(float)
    x["pd_ttc"] = f["pd_ttc"].astype(float)
    x["pd_12m_input"] = f["pd12_book"].astype(float)
    x["lgd_input"] = f["lgd_pct_book"].astype(float) / 100.0
    x["secured_share"] = f["secured_share"].astype(float)
    x["haircut_pct"] = f["haircut_pct"].astype(float)
    x["log_ead"] = np.log1p(f["ead"].astype(float).clip(lower=0) * 1000.0)
    x["ccf"] = f["ccf"].astype(float)
    x["undrawn_share"] = (f["undrawn"] / f["limit"].where(f["limit"] > 0, np.nan)).fillna(0).astype(float)
    x["dpd"] = f["dpd"].astype(float)
    if domain == "corporate":
        x["nfo"] = f["nfo"].astype(float)
    else:
        x["behaviour_score"] = f["behaviour_score"].astype(float)
        x["application_score"] = f["application_score"].astype(float)
    return x


@functools.lru_cache(maxsize=64)
def path_table(domain: str, period: str) -> dict[str, Any]:
    """MEV features and segment cycle index per scenario and year for a period's paths."""
    model = cycle.load(domain)
    sy = int(np.floor(mev.period_year_fraction(period) + 0.5))
    p = mev.paths_from(sy)
    feats = {s: p[s + "_features"].reset_index(drop=True) for s in store.SCENARIOS}
    return {"start_year": sy, "features": feats, "model": model}


def segment_z(model: dict, segment: str, feats: pd.DataFrame) -> np.ndarray:
    return cycle.z_path(model, segment, feats)


def long_rows(domain: str, period: str, f: pd.DataFrame, xs: pd.DataFrame, pairs: list[tuple[str, int]] | None = None,
              mev_override: dict[str, pd.DataFrame] | None = None, z_shift: np.ndarray | None = None) -> pd.DataFrame:
    """One row per exposure x (scenario, year); `pairs` defaults to all 15."""
    pt = path_table(domain, period)
    feats = mev_override or pt["features"]
    pairs = pairs or [(s, t) for s in store.SCENARIOS for t in store.YEARS]
    segs = f["segment"].astype(str).to_numpy()
    useg, inv = np.unique(segs, return_inverse=True)
    zmat = {s: np.stack([segment_z(pt["model"], seg, feats[s]) for seg in useg]) for s in store.SCENARIOS}  # (nseg, 5)
    base_z = {s: np.stack([segment_z(pt["model"], seg, pt["features"][s]) for seg in useg]) for s in store.SCENARIOS}
    anchor = sum(mev.WEIGHTS[s] * base_z[s][:, 0] for s in store.SCENARIOS)[inv]
    blocks = []
    for s, t in pairs:
        b = xs.copy()
        b["year"] = float(t)
        b["scenario_code"] = float(SCN_CODE[s])
        z = zmat[s][inv, t - 1].copy()
        if z_shift is not None:
            z = z + z_shift
        b["cycle_z"] = z
        b["cycle_anchor"] = anchor
        row = feats[s].iloc[t - 1]
        for k in MEV_KEYS:
            b[f"mev_{k}"] = float(row[k])
        blocks.append(b)
    return pd.concat(blocks, ignore_index=True)


def hazard_targets(f: pd.DataFrame) -> np.ndarray:
    """(n, 3, 5) annual conditional PDs from the stored marginal PDs."""
    mpd = np.stack([f[store.pd_cols(s)].to_numpy(dtype=float) for s in store.SCENARIOS], axis=1)
    surv = 1.0 - np.cumsum(mpd, axis=2)
    prev = np.concatenate([np.ones(mpd.shape[:2] + (1,)), surv[:, :, :-1]], axis=2)
    return np.where(prev > 1e-12, mpd / np.where(prev > 1e-12, prev, 1.0), 0.0).clip(0, PD_CAP)


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, LOGIT_FLOOR, 1 - LOGIT_FLOOR)
    return np.log(p / (1 - p))


def expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# ------------------------------------------------------------------ a numpy tree evaluator

class Forest:
    """Evaluates an XGBoost JSON model with numpy: same predictions without the xgboost library."""

    def __init__(self, model_json: dict[str, Any]):
        learner = model_json["learner"]
        self.base = float(np.asarray(json.loads(learner["learner_model_param"]["base_score"])
                                     if learner["learner_model_param"]["base_score"].startswith("[")
                                     else learner["learner_model_param"]["base_score"], dtype=float).ravel()[0])
        self.trees = []
        for t in learner["gradient_booster"]["model"]["trees"]:
            self.trees.append((np.asarray(t["left_children"], dtype=np.int64),
                               np.asarray(t["right_children"], dtype=np.int64),
                               np.asarray(t["split_indices"], dtype=np.int64),
                               np.asarray(t["split_conditions"], dtype=np.float32),
                               np.asarray(t["default_left"], dtype=bool),
                               np.asarray(t["base_weights"], dtype=np.float32)))

    def predict(self, x: np.ndarray, margin: np.ndarray | None = None) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        n = len(x)
        out = np.full(n, self.base, dtype=np.float64) if margin is None else np.asarray(margin, dtype=np.float64).copy()
        rows = np.arange(n)
        for left, right, idx, cond, dleft, weight in self.trees:
            node = np.zeros(n, dtype=np.int64)
            while True:
                leaf = left[node] == -1
                if leaf.all():
                    break
                v = x[rows, idx[node]]
                go_left = np.where(np.isnan(v), dleft[node], v < cond[node])
                nxt = np.where(go_left, left[node], right[node])
                node = np.where(leaf, node, nxt)
            out += weight[node]
        return out


@functools.lru_cache(maxsize=16)
def load_model(domain: str, target: str) -> tuple[Any, list[str]]:
    d = MODEL_DIR / domain
    meta = json.loads((d / "models.json").read_text())
    entry = meta["models"][target]
    path = d / entry["file"]
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != entry["sha256"]:
        raise ModelError(f"{path.name} does not match its recorded sha256; refusing to use it.")
    try:
        import xgboost as xgbl
        booster = xgbl.Booster(params={"nthread": 4})
        booster.load_model(bytearray(body))
        return ("xgboost", booster), entry["features"]
    except Exception:  # noqa: BLE001 - the numpy evaluator gives the same predictions
        return ("numpy", Forest(json.loads(body))), entry["features"]


def offset(target: str, x: pd.DataFrame) -> np.ndarray | None:
    """The PD model's offset: the log-odds of the bank's 12-month PD input (the trees learn the adjustment)."""
    return logit(x["pd_12m_input"].to_numpy(dtype=float)) if target == "pd" else None


def predict(domain: str, target: str, x: pd.DataFrame) -> np.ndarray:
    (kind, model), feats = load_model(domain, target)
    data = x[feats].to_numpy(dtype=np.float32)
    margin = offset(target, x)
    if kind == "xgboost":
        import xgboost as xgbl
        with _LOCK:
            d = xgbl.DMatrix(data, feature_names=feats, base_margin=margin) if margin is not None else xgbl.DMatrix(data, feature_names=feats)
            return model.predict(d, validate_features=False).astype(np.float64)
    return model.predict(data, margin)


@functools.lru_cache(maxsize=1)
def available() -> dict[str, Any]:
    out = {}
    for domain in store.BOOKS:
        try:
            meta = json.loads((MODEL_DIR / domain / "models.json").read_text())
            out[domain] = {"version": meta["version"], "trained": meta["trained"]}
        except (OSError, KeyError, ValueError):
            out[domain] = None
    return out


# ------------------------------------------------------------------ the method

_BASE_CACHE: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}


class XGBoostMethod(Method):
    key = "xgboost"
    name = "XGBoost"
    version = METHOD_VERSION

    def _predict_paths(self, ctx: Context, xs: pd.DataFrame, rows: np.ndarray, mev_override=None,
                       z_shift=None) -> tuple[np.ndarray, np.ndarray]:
        f = ctx.frame.iloc[rows]
        long = long_rows(ctx.domain, ctx.period, f, xs.iloc[rows].reset_index(drop=True),
                         mev_override=mev_override, z_shift=z_shift)
        n = len(rows)
        h = expit(predict(ctx.domain, "pd", long)).reshape(3, 5, n).transpose(2, 0, 1)
        lgd = np.clip(predict(ctx.domain, "lgd", long), 0.0, 1.0).reshape(3, 5, n).transpose(2, 0, 1)
        return np.clip(h, 0.0, PD_CAP), lgd

    def _static(self, ctx: Context) -> pd.DataFrame:
        if not hasattr(ctx, "_xgb_static"):
            ctx._xgb_static = static_frame(ctx.domain, ctx.frame, encodings_cached(ctx.domain))
        return ctx._xgb_static

    def start(self, ctx: Context) -> Start:
        key = (ctx.domain, ctx.period)
        ids = ctx.frame["exposure_id"].to_numpy()
        with _LOCK:
            cached = _BASE_CACHE.get(key)
        if cached is None or (pd.Index(cached[2]).get_indexer(ids) < 0).any():
            full = store.frame(ctx.domain, ctx.period)
            xs = static_frame(ctx.domain, full, encodings_cached(ctx.domain))
            sub = Context(domain=ctx.domain, period=ctx.period, frame=full, scenario=ctx.scenario, masks=[],
                          notches=np.zeros(len(full), int), sector_dz=np.zeros(len(full)),
                          mev_dz=np.zeros((len(full), 3, 5)), re_move=np.zeros((len(full), 3, 5)),
                          grade_new=full["grade"].to_numpy(), rank_new=full["grade_rank"].to_numpy(), ms={},
                          rating_factor=np.ones(len(full)))
            h, lgd = self._predict_paths(sub, xs, np.arange(len(full)))
            cached = (h, lgd, full["exposure_id"].to_numpy())
            with _LOCK:
                _BASE_CACHE[key] = cached
        pos = pd.Index(cached[2]).get_indexer(ids)
        h, lgd = cached[0][pos].copy(), cached[1][pos].copy()
        defaulted = ctx.frame["stage"].to_numpy() >= 3
        from backend.whatif_v5.models.engine import marginal
        mpd = marginal(h)
        mpd[defaulted] = 0.0
        mpd[defaulted, :, 0] = 1.0
        return Start(mpd=mpd, lgd=lgd, label="XGBoost predictions without the scenario")

    def transmit(self, ctx: Context, on: frozenset[str]) -> tuple[np.ndarray, np.ndarray]:
        h = ctx.base_h.copy()
        lgd = ctx.start.lgd.copy()
        if not on:
            return h, lgd
        f = ctx.frame
        xs = self._static(ctx).copy()
        changed = np.zeros(len(f), dtype=bool)
        if "rating" in on and ctx.notches.any():
            moved = ctx.notches != 0
            changed |= moved
            xs.loc[moved, "grade_rank"] = ctx.rank_new[moved].astype(float)
            if ctx.domain == "corporate":
                xs.loc[moved, "nfo"] = (f["nfo"].to_numpy() + ctx.notches)[moved].astype(float)
                ttc_new = np.array([ctx.ms.get(g, np.nan) for g in ctx.grade_new])
                xs.loc[moved, "pd_ttc"] = np.where(np.isfinite(ttc_new), ttc_new, xs["pd_ttc"].to_numpy())[moved]
                xs.loc[moved, "pd_12m_input"] = np.minimum(0.99, xs["pd_12m_input"].to_numpy() * ctx.rating_factor)[moved]
            else:
                xs.loc[moved, "behaviour_score"] = (f["behaviour_score"].to_numpy() - 80.0 * ctx.notches)[moved]
                ttc_new = np.array([ctx.ms.get(g, np.nan) for g in ctx.grade_new])
                xs.loc[moved, "pd_ttc"] = np.where(np.isfinite(ttc_new), ttc_new, xs["pd_ttc"].to_numpy())[moved]
                xs.loc[moved, "pd_12m_input"] = np.minimum(0.99, xs["pd_12m_input"].to_numpy() * ctx.rating_factor)[moved]
        z_shift = np.zeros(len(f))
        if "sector" in on and ctx.sector_dz.any():
            z_shift += ctx.sector_dz
            changed |= ctx.sector_dz != 0
        mev_rows = np.zeros(len(f), dtype=bool)
        if "mev" in on and ctx.mev_dz.any():
            mev_rows = np.abs(ctx.mev_dz).sum(axis=(1, 2)) > 0
            changed |= mev_rows
        rows = np.flatnonzero(changed & (f["stage"].to_numpy() < 3))
        if not len(rows):
            return h, lgd
        override = None
        if mev_rows.any():
            shocks: dict[str, float] = {}
            for st, m in zip(ctx.scenario.steps, ctx.masks):
                for k, v in st.shocks.mev.items():
                    shocks[k] = shocks.get(k, 0.0) + v
            pt = path_table(ctx.domain, ctx.period)
            override = {s: mev.shocked_features(pt["start_year"], s, shocks).reset_index(drop=True)
                        for s in store.SCENARIOS}
            horizon = max((st.shocks.horizon for st in ctx.scenario.steps if st.shocks.mev), default=0)
            if horizon:
                # R10 C1: after the horizon each path reverts to its base features.
                base_lv = mev.paths_from(pt["start_year"])
                for s in store.SCENARIOS:
                    base_f = base_lv[s + "_features"].reset_index(drop=True)
                    override[s].iloc[horizon:] = base_f.iloc[horizon:len(override[s])].to_numpy()
        # Rows shocked by some but not all channels are predicted in groups so each row sees only its own shocks.
        groups: dict[tuple, list[int]] = {}
        for i in rows:
            groups.setdefault((bool(mev_rows[i]),), []).append(i)
        for (has_mev,), idx in groups.items():
            idx = np.asarray(idx)
            hh, ll = self._predict_paths(ctx, xs, idx, mev_override=override if has_mev else None,
                                         z_shift=z_shift[idx])
            h[idx], lgd[idx] = hh, ll
        return h, lgd


@functools.lru_cache(maxsize=4)
def encodings_cached(domain: str) -> dict[str, dict[str, int]]:
    d = MODEL_DIR / domain
    try:
        return json.loads((d / "models.json").read_text())["encodings"]
    except (OSError, KeyError, ValueError):
        return encodings(domain)


def card(domain: str) -> dict[str, Any]:
    path = MODEL_DIR / domain / "card.json"
    if not path.exists():
        raise ModelError(f"The XGBoost model card for {domain} is not built.")
    return json.loads(path.read_text())


__all__ = ["Forest", "XGBoostMethod", "card", "features", "load_model", "predict"]
_ = (time, pathlib, grade_scale)
