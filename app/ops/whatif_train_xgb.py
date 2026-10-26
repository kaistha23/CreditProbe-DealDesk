"""Train the What-If XGBoost models on the What-If domain and write their model card.

    .venv/bin/python ops/whatif_train_xgb.py [corporate|retail]

Writes data/whatif_v5/models/<book>/:
  pd.json lgd.json ecl12.json ecllt.json   the served models (random 70/30 split), XGBoost JSON
  models.json                              versions, sha256 of every file, features, encodings
  card.json                                metrics on both splits, calibration, importance, SHAP, sensitivities

Deterministic: fixed seed, fixed sampling, the same domain gives the same models.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

import xgboost as xgbl  # noqa: E402

from backend.whatif_v5.domain import mev, store  # noqa: E402
from backend.whatif_v5.models import xgb  # noqa: E402

TRAIN_THREADS = 4
SHAP_ROWS = 4000


def build_long(domain: str, rng: np.random.Generator, enc) -> pd.DataFrame:
    """One random (scenario, year) pair per exposure-period, plus targets (the PD model uses the performing rows)."""
    parts = []
    for p in store.periods(domain):
        f = store.frame(domain, p)
        f = f[(f["ead"] > 0)].reset_index(drop=True)
        xs = xgb.static_frame(domain, f, enc)
        h = xgb.hazard_targets(f)
        lgd = np.stack([f[store.lgd_cols(s)].to_numpy(dtype=float) for s in store.SCENARIOS], axis=1)
        s_idx = rng.integers(0, 3, len(f))
        t_idx = rng.integers(0, 5, len(f))
        pt = xgb.path_table(domain, p)
        segs = f["segment"].astype(str).to_numpy()
        z = {(seg, s): xgb.segment_z(pt["model"], seg, pt["features"][s]) for seg in np.unique(segs)
             for s in store.SCENARIOS}
        b = xs.copy()
        b["year"] = (t_idx + 1).astype(float)
        b["scenario_code"] = s_idx.astype(float)
        names = store.SCENARIOS
        b["cycle_z"] = [z[(seg, names[si])][ti] for seg, si, ti in zip(segs, s_idx, t_idx)]
        b["cycle_anchor"] = [sum(mev.WEIGHTS[sc] * z[(seg, sc)][0] for sc in names) for seg in segs]
        for k in xgb.MEV_KEYS:
            mat = np.stack([pt["features"][s][k].to_numpy() for s in names])  # (3, 5)
            b[f"mev_{k}"] = mat[s_idx, t_idx]
        b["y_pd"] = xgb.logit(h[np.arange(len(f)), s_idx, t_idx])
        b["y_hazard"] = h[np.arange(len(f)), s_idx, t_idx]
        b["y_lgd"] = lgd[np.arange(len(f)), s_idx, t_idx]
        b["period"] = p
        b["exposure_id"] = f["exposure_id"].to_numpy()
        b["performing"] = ((f["stage"] < 3) & (f["pd12_book"] < 1)).to_numpy()
        parts.append(b)
    return pd.concat(parts, ignore_index=True)


def build_wide(domain: str, enc) -> pd.DataFrame:
    parts = []
    for p in store.periods(domain):
        f = store.frame(domain, p)
        f = f[(f["ead"] > 0)].reset_index(drop=True)
        xs = xgb.static_frame(domain, f, enc)
        pt = xgb.path_table(domain, p)
        segs = f["segment"].astype(str).to_numpy()
        z = {seg: xgb.segment_z(pt["model"], seg, pt["features"]["base"])[0] for seg in np.unique(segs)}
        xs["cycle_z_y1"] = [z[s] for s in segs]
        for k in xgb.MEV_KEYS:
            xs[f"mev_{k}"] = float(pt["features"]["base"][k].iloc[0])
        xs["y_ecl12"] = (f["ecl_12m"] / f["ead"]).to_numpy()
        xs["y_ecllt"] = (f["ecl_lifetime"] / f["ead"]).to_numpy()
        xs["period"] = p
        parts.append(xs)
    return pd.concat(parts, ignore_index=True)


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    err = p - y
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    return {"rows": int(len(y)), "rmse": float(np.sqrt((err ** 2).mean())), "mae": float(np.abs(err).mean()),
            "r2": float(1 - (err ** 2).sum() / ss_tot), "mean_actual": float(y.mean()), "mean_predicted": float(p.mean())}


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, float]]:
    order = np.argsort(p, kind="mergesort")
    out = []
    for i, chunk in enumerate(np.array_split(order, bins)):
        out.append({"decile": i + 1, "predicted": float(p[chunk].mean()), "actual": float(y[chunk].mean()),
                    "rows": int(len(chunk))})
    return out


CURRENT = {"target": ""}


def _dm(x: pd.DataFrame, feats: list[str], label=None) -> xgbl.DMatrix:
    margin = xgb.offset(CURRENT["target"], x)
    return xgbl.DMatrix(x[feats].to_numpy(dtype=np.float32), label=label, feature_names=feats, base_margin=margin)


def fit(x: pd.DataFrame, y: np.ndarray, feats: list[str], mono: str | None = None) -> xgbl.Booster:
    params = {**xgb.PARAMS, "nthread": TRAIN_THREADS}
    if mono:
        params["monotone_constraints"] = mono
    return xgbl.train(params, _dm(x, feats, y), num_boost_round=xgb.ROUNDS)


def pred(b: xgbl.Booster, x: pd.DataFrame, feats: list[str]) -> np.ndarray:
    return b.predict(_dm(x, feats))


def shap_summary(b: xgbl.Booster, x: pd.DataFrame, feats: list[str], rng) -> dict:
    idx = rng.choice(len(x), size=min(SHAP_ROWS, len(x)), replace=False)
    sub = x.iloc[np.sort(idx)]
    contrib = b.predict(_dm(sub, feats), pred_contribs=True)
    phi = contrib[:, :-1]
    mean_abs = np.abs(phi).mean(0)
    total = mean_abs.sum() or 1.0
    order = np.argsort(-mean_abs)
    top = [feats[i] for i in order[:12]]
    pts_idx = rng.choice(len(sub), size=min(300, len(sub)), replace=False)
    points = {}
    for i in order[:10]:
        v = sub[feats[i]].to_numpy(dtype=float)[pts_idx]
        lo, hi = np.nanpercentile(v, 1), np.nanpercentile(v, 99)
        norm = np.clip((v - lo) / (hi - lo), 0, 1) if hi > lo else np.full(len(v), 0.5)
        points[feats[i]] = {"shap": [round(float(s), 5) for s in phi[pts_idx, i]],
                            "value_norm": [round(float(s), 4) for s in norm]}
    return {"rows": int(len(sub)), "base_value": float(contrib[:, -1].mean()),
            "features": [{"feature": feats[i], "mean_abs_shap": float(mean_abs[i]), "share_pct": float(mean_abs[i] / total * 100)}
                         for i in order], "top": top, "beeswarm": points,
            "additivity_max_error": float(np.abs(contrib.sum(1) - pred(b, sub, feats)).max())}


def importance(b: xgbl.Booster, feats: list[str]) -> list[dict]:
    gain = b.get_score(importance_type="total_gain")
    total = sum(gain.values()) or 1.0
    return sorted([{"feature": f, "gain": float(gain.get(f, 0.0)), "share_pct": float(gain.get(f, 0.0) / total * 100)}
                   for f in feats], key=lambda r: -r["gain"])


def sensitivity(domain: str, b_pd: xgbl.Booster, enc) -> list[dict]:
    """Average 12-month PD of the performing book at the as-of when each MEV moves by -1/+1 sd (base path, year 1)."""
    f = store.frame(domain)
    f = f[(f["stage"] < 3) & (f["ead"] > 0)].reset_index(drop=True)
    xs = xgb.static_frame(domain, f, enc)
    long = xgb.long_rows(domain, store.as_of(domain), f, xs, pairs=[("base", 1)])
    feats = xgb.features(domain, "pd")
    CURRENT["target"] = "pd"
    base = xgb.expit(pred(b_pd, long, feats))
    w = f["ead"].to_numpy()
    out = []
    st = mev.feature_stats()
    model = xgb.path_table(domain, store.as_of(domain))["model"]
    for s in mev.SERIES:
        row = {"mev": s.key, "name": s.name, "sd": st[s.key]["sd"]}
        for sign, label in ((-1, "adverse_1sd"), (+1, "favourable_1sd")):
            move = sign * s.direction * st[s.key]["sd"]
            alt = long.copy()
            if f"mev_{s.key}" in alt:
                alt[f"mev_{s.key}"] = alt[f"mev_{s.key}"] + move
            gam = model["gamma"][s.key] / st[s.key]["sd"] * s.direction
            segs = f["segment"].astype(str).to_numpy()
            betas = np.array([model["betas"].get(g, {"beta": 1.0})["beta"] for g in segs])
            alt["cycle_z"] = alt["cycle_z"] + betas * gam * move
            p = xgb.expit(pred(b_pd, alt, feats))
            row[label + "_pd_change_pct"] = float((np.average(p, weights=w) / np.average(base, weights=w) - 1) * 100)
        out.append(row)
    return out


def train(domain: str) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(xgb.SEED)
    enc = xgb.encodings(domain)
    long = build_long(domain, rng, enc)
    wide = build_wide(domain, enc)
    periods = store.periods(domain)
    cut = periods[int(round(len(periods) * 0.7)) - 1]
    split_rng = np.random.default_rng(xgb.SEED + 1)
    long_train = split_rng.random(len(long)) < 0.7
    wide_train = split_rng.random(len(wide)) < 0.7
    out_dir = xgb.MODEL_DIR / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    perf = long["performing"].to_numpy()
    long_pd = long[perf].reset_index(drop=True)
    pd_train = long_train[perf]
    targets = {"pd": (long_pd, "y_pd", pd_train), "lgd": (long, "y_lgd", long_train),
               "ecl12": (wide, "y_ecl12", wide_train), "ecllt": (wide, "y_ecllt", wide_train)}
    models_meta = {}
    card_targets = {}
    served = {}
    for name, (data, ycol, train_mask) in targets.items():
        CURRENT["target"] = name
        feats = xgb.features(domain, name)
        y = data[ycol].to_numpy(dtype=float)
        # random split (served)
        mono = None   # see xgb.path_features: no monotone constraint
        b = fit(data[train_mask], y[train_mask], feats, mono)
        p_test = pred(b, data[~train_mask], feats)
        p_train = pred(b, data[train_mask], feats)
        # out-of-time split
        oot_train = (data["period"] <= cut).to_numpy()
        b_oot = fit(data[oot_train], y[oot_train], feats, mono)
        p_oot = pred(b_oot, data[~oot_train], feats)
        entry = {"target": ycol, "features": feats}
        if name == "pd":
            prob = lambda v: xgb.expit(v)  # noqa: E731
            ya, yo = data["y_hazard"].to_numpy()[~train_mask], data["y_hazard"].to_numpy()[~oot_train]
            entry.update({
                "random": {"train_logit": metrics(y[train_mask], p_train), "test_logit": metrics(y[~train_mask], p_test),
                           "test_probability": metrics(ya, prob(p_test))},
                "out_of_time": {"test_logit": metrics(y[~oot_train], p_oot), "test_probability": metrics(yo, prob(p_oot))},
                "calibration": calibration(ya, prob(p_test)), "calibration_out_of_time": calibration(yo, prob(p_oot))})
        else:
            entry.update({
                "random": {"train": metrics(y[train_mask], p_train), "test": metrics(y[~train_mask], p_test)},
                "out_of_time": {"test": metrics(y[~oot_train], p_oot)},
                "calibration": calibration(y[~train_mask], p_test),
                "calibration_out_of_time": calibration(y[~oot_train], p_oot)})
        entry["importance"] = importance(b, feats)
        entry["shap"] = shap_summary(b, data[~train_mask], feats, np.random.default_rng(xgb.SEED + 2))
        path = out_dir / f"{name}.json"
        b.save_model(str(path))
        body = path.read_bytes()
        models_meta[name] = {"file": path.name, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                             "features": feats, "target": ycol}
        card_targets[name] = entry
        served[name] = b
        print(f"  {domain} {name}: test {json.dumps({k: round(v, 4) for k, v in (entry['random'].get('test') or entry['random']['test_probability']).items()})}")
    # numpy evaluator equals xgboost on a sample
    sample = long_pd[~pd_train].head(2000)
    forest = xgb.Forest(json.loads((out_dir / "pd.json").read_text()))
    CURRENT["target"] = "pd"
    np_err = float(np.abs(forest.predict(sample[xgb.features(domain, "pd")].to_numpy(dtype=np.float32), xgb.offset("pd", sample))
                          - pred(served["pd"], sample, xgb.features(domain, "pd"))).max())
    sens = sensitivity(domain, served["pd"], enc)
    meta = {"version": xgb.METHOD_VERSION, "book": domain, "trained": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": xgb.SEED, "params": xgb.PARAMS, "monotone": "none", "rounds": xgb.ROUNDS, "train_threads": TRAIN_THREADS,
            "encodings": enc, "models": models_meta}
    (out_dir / "models.json").write_text(json.dumps(meta, indent=1, sort_keys=True))
    card = {"version": xgb.METHOD_VERSION, "book": domain, "trained": meta["trained"],
            "rows": {"pd_lgd": int(len(long)), "ecl": int(len(wide)), "periods": periods,
                     "out_of_time_cut": cut, "random_train_share": 0.7},
            "targets": card_targets, "sensitivity": sens, "numpy_evaluator_max_error": np_err,
            "training_seconds": round(time.time() - t0, 1)}
    (out_dir / "card.json").write_text(json.dumps(card, indent=1))
    print(f"  {domain}: trained in {time.time() - t0:.0f}s; numpy evaluator max error {np_err:.2e}")
    return card


if __name__ == "__main__":
    for d in (sys.argv[1:] or list(store.BOOKS)):
        train(d)
