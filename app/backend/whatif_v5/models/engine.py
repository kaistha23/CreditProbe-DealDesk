"""The What-If ECL engine: one engine, two methods (Delta, XGBoost), exact attribution.

A method supplies the starting term structures (marginal PD and LGD by
scenario and year) and the *transmission* of the feature-level drivers
(rating, sector, MEV) to hazards and LGD. The engine applies the
parameter-level drivers (PD, LGD, CCF/EAD) and the staging re-assessment the
same way for both methods, measures ECL per scenario and weights it.

Attribution: v(S) is the probability-weighted ECL of every exposure with only
the drivers in S switched on. The waterfall bars are the exact Shapley values
of v over the drivers the scenario uses (2^k evaluations, k <= 7); they add
up to v(all) - v(none) to floating-point precision, per exposure and in total.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from backend.v5common import ratings
from backend.whatif_v5 import capital
from backend.whatif_v5.domain import cycle, mev, store
from backend.whatif_v5.models.scenario import DRIVER_LABELS, DRIVERS, Scenario, Scope

PD_CAP = 0.9999
CORP_STAGE3_RANK = ratings.rank("CC")
CORP_STAGE2_RANK = ratings.rank("CCC")
CORP_SICR_NOTCHES = 2
RETAIL_SCORE_FLOOR = 520.0
RETAIL_BAND_WIDTH = 80.0
RULE_B_RATIO = 2.0
RULE_B_FLOOR = 0.005
FEATURE_DRIVERS = ("rating", "sector", "mev")
W = np.array([mev.WEIGHTS[s] for s in store.SCENARIOS])


class RunError(ValueError):
    pass


# ------------------------------------------------------------------ helpers

def hazards(mpd: np.ndarray) -> np.ndarray:
    surv = 1.0 - np.cumsum(mpd, axis=2)
    prev = np.concatenate([np.ones(mpd.shape[:2] + (1,)), surv[:, :, :-1]], axis=2)
    return np.where(prev > 1e-15, mpd / np.where(prev > 1e-15, prev, 1.0), 0.0).clip(0, PD_CAP)


def marginal(h: np.ndarray) -> np.ndarray:
    surv = np.cumprod(1 - h, axis=2)
    prev = np.concatenate([np.ones(h.shape[:2] + (1,)), surv[:, :, :-1]], axis=2)
    return prev * h


def scope_mask(frame: pd.DataFrame, scope: Scope) -> np.ndarray:
    m = np.ones(len(frame), dtype=bool)
    if scope.segments:
        m &= frame["segment"].isin(scope.segments).to_numpy()
    if scope.subsegments:
        m &= frame["subsegment"].isin(scope.subsegments).to_numpy()
    if scope.products:
        m &= frame["product"].isin(scope.products).to_numpy()
    if scope.owners:
        m &= frame["owner_id"].isin(scope.owners).to_numpy()
    if scope.exposures:
        m &= frame["exposure_id"].isin(scope.exposures).to_numpy()
    if scope.stages:
        m &= frame["stage"].isin(scope.stages).to_numpy()
    if scope.grades:
        m &= frame["grade"].isin(scope.grades).to_numpy()
    return m


def grade_scale(domain: str, frame: pd.DataFrame) -> dict[str, float]:
    """Masterscale: average TTC PD per grade at the period (corporate ratings; retail score bands)."""
    order = ratings.RATING_ORDER if domain == "corporate" else ("A", "B", "C", "D", "E")
    perf = frame[frame["stage"] < 3]
    col = "pd_ttc" if domain == "corporate" else "pd12_book"
    means = perf.groupby("grade")[col].mean().to_dict()
    default = "D" if domain == "corporate" else None      # retail band D is a score band, not default
    known = {g: float(p) for g, p in means.items() if g in order and g != default and p > 0}
    out: dict[str, float] = {}
    idx = sorted(order.index(g) for g in known)
    logs = {order.index(g): math.log(p) for g, p in known.items()}
    for i, g in enumerate(order):
        if g == default:
            out[g] = 1.0
        elif g in known:
            out[g] = known[g]
        elif idx:
            lower = [j for j in idx if j < i]
            upper = [j for j in idx if j > i]
            if lower and upper:
                a, b = max(lower), min(upper)
            elif upper:
                a, b = (upper + upper)[:2] if len(upper) < 2 else sorted(upper)[:2]
            else:
                a, b = (lower + lower)[-2:] if len(lower) < 2 else sorted(lower)[-2:]
            slope = (logs[b] - logs[a]) / (b - a) if b != a else 0.0
            out[g] = min(0.99, math.exp(logs[a] + slope * (i - a)))
    return out


# ------------------------------------------------------------------ method interface

@dataclass
class Start:
    """What a method gives the engine for a population."""
    mpd: np.ndarray        # (n, 3, 5) marginal PD
    lgd: np.ndarray        # (n, 3, 5)
    label: str


class Method:
    key = "delta"
    name = "Delta method"

    def start(self, ctx: "Context") -> Start:  # pragma: no cover - interface
        raise NotImplementedError

    def transmit(self, ctx: "Context", on: frozenset[str]) -> tuple[np.ndarray, np.ndarray]:
        """Hazards and LGD with the feature-level drivers in `on` (subset of rating/sector/mev) applied."""
        raise NotImplementedError  # pragma: no cover


@dataclass
class Context:
    domain: str
    period: str
    frame: pd.DataFrame          # the population in scope (all steps' masks are subsets)
    scenario: Scenario
    masks: list[np.ndarray]      # one per step
    notches: np.ndarray          # cumulative rating notches per row
    sector_dz: np.ndarray        # (n,) cycle-index shift from sector stress
    mev_dz: np.ndarray           # (n, 3, 5) cycle-index shift from MEV shocks
    re_move: np.ndarray          # (n, 3, 5) relative real-estate price move (for collateral LGD)
    grade_new: np.ndarray        # stressed grade label
    rank_new: np.ndarray
    ms: dict[str, float]
    rating_factor: np.ndarray    # masterscale PD ratio
    coll_dlgd: np.ndarray | None = None   # (n,) LGD added by the collateral channel (absolute)
    coll: dict | None = None              # the collateral channel's inputs and outputs per row (for the explanation)
    start: Start | None = None
    base_h: np.ndarray | None = None


def build_context(scenario: Scenario, frame: pd.DataFrame, population: np.ndarray) -> Context:
    domain = scenario.domain
    f = frame.loc[population].reset_index(drop=True)
    n = len(f)
    masks = [scope_mask(f, st.scope) for st in scenario.steps]
    notches = np.zeros(n, dtype=int)
    sector = np.zeros(n)
    mev_shock_rows: dict[tuple, np.ndarray] = {}
    for st, m in zip(scenario.steps, masks):
        notches += np.where(m, st.shocks.rating, 0)
        sector += np.where(m, st.shocks.sector, 0.0)
        if st.shocks.mev:
            key = tuple(sorted(st.shocks.mev.items())) + ((("__horizon__", st.shocks.horizon),) if st.shocks.horizon else ())
            mev_shock_rows[key] = mev_shock_rows.get(key, np.zeros(n, dtype=bool)) | m
    # MEV: the change in each segment's cycle index along each scenario path.
    mev_dz = np.zeros((n, 3, 5))
    re_move = np.zeros((n, 3, 5))
    if mev_shock_rows:
        model = cycle.load(domain)
        sy = int(np.floor(mev.period_year_fraction(scenario.period) + 0.5))
        segs = f["segment"].astype(str).to_numpy()
        base_lv = mev.paths_from(sy)
        for shock_items, rows in mev_shock_rows.items():
            shocks = dict(shock_items)
            horizon = int(shocks.pop("__horizon__", 0) or 0)
            for j, s in enumerate(store.SCENARIOS):
                base_f = base_lv[s + "_features"]
                shocked_f = mev.shocked_features(sy, s, shocks)
                for seg in np.unique(segs[rows]):
                    sel = rows & (segs == seg)
                    mev_dz[sel, j, :] += cycle.mev_dz(model, seg, base_f, shocked_f)
                if "re_price" in shocks:
                    re_move[rows, j, :] += shocks["re_price"] / 100.0
            if horizon:
                # R10 C1: the macro shock lasts `horizon` years, then each path reverts to its base.
                mev_dz[rows, :, horizon:] = 0.0
                re_move[rows, :, horizon:] = 0.0
    # Rating: masterscale ratio, grade moves inside the performing scale (stops at C / band E).
    ms = grade_scale(domain, frame)
    order = list(ratings.RATING_ORDER) if domain == "corporate" else ["A", "B", "C", "D", "E"]
    worst = order.index("C") if domain == "corporate" else len(order) - 1
    grades = f["grade"].astype(str).to_numpy()
    rank_old = np.array([order.index(g) if g in order else -1 for g in grades])
    movable = (rank_old >= 0) & ((grades != "D") if domain == "corporate" else True)
    rank_new = np.where(movable, np.clip(rank_old + notches, 0, worst), rank_old)
    grade_new = np.array([order[r] if r >= 0 else g for r, g in zip(rank_new, grades)], dtype=object)
    p_old = np.array([ms.get(g, np.nan) for g in grades])
    p_new = np.array([ms.get(g, np.nan) for g in grade_new])
    factor = np.where(movable & (p_old > 0) & np.isfinite(p_new), p_new / np.where(p_old > 0, p_old, 1.0), 1.0)
    coll_pct = np.zeros(n)
    hair_pp = np.zeros(n)
    for st, m in zip(scenario.steps, masks):
        coll_pct += np.where(m, st.shocks.collateral, 0.0)
        hair_pp += np.where(m, st.shocks.haircut, 0.0)
    coll = collateral_channel(domain, f, coll_pct, hair_pp, frame)
    return Context(domain=domain, period=scenario.period, frame=f, scenario=scenario, masks=masks,
                   notches=notches, sector_dz=-sector, mev_dz=mev_dz, re_move=re_move,
                   grade_new=grade_new, rank_new=rank_new, ms=ms, rating_factor=factor,
                   coll_dlgd=coll["dlgd"], coll=coll)


#: Corporate: the book holds no unsecured facilities to measure an unsecured LGD on, so the newly
#: unsecured slice carries the Basel / SAMA foundation-IRB senior unsecured LGD.
CORP_UNSECURED_LGD = 0.45


def unsecured_lgd(domain: str, book: pd.DataFrame) -> float:
    """The LGD the newly unsecured part of an exposure carries."""
    if domain == "corporate":
        return CORP_UNSECURED_LGD
    u = book[(book["collateral_type"] == "Unsecured") & (book["stage"] < 3)]
    w = u["ead"].to_numpy(dtype=float)
    return float(np.average(u["lgd_pct_book"].to_numpy(dtype=float), weights=w) / 100.0) if w.sum() > 0 else 0.6


def collateral_channel(domain: str, f: pd.DataFrame, coll_pct: np.ndarray, hair_pp: np.ndarray,
                       book: pd.DataFrame | None = None) -> dict[str, np.ndarray | float]:
    """Collateral value and haircut shocks -> LGD (both methods).

        cover0 = allocated collateral C0, or the full haircut-adjusted value MV x (1 - h) where C0 is capped at EAD
        k      = (1 + dC) x (1 - h - dh) / (1 - h)          the move in haircut-adjusted value
        C1     = min(EAD, cover0 x k)
        s0, s1 = C0 / EAD, C1 / EAD                         secured share before and after
        dLGD   = LGD_unsecured x (s0 - s1)                  the newly unsecured slice loses at the unsecured LGD

    Exact at zero shock (C1 = C0). Applied to every scenario and year of the LGD term structure.
    """
    n = len(f)
    zero = np.zeros(n)
    lgd_u = unsecured_lgd(domain, book if book is not None else f)
    if not (np.any(coll_pct) or np.any(hair_pp)):
        return {"dlgd": zero, "s0": zero, "s1": zero, "lgd_u": lgd_u, "c0": zero, "c1": zero}
    ead = f["ead"].to_numpy(dtype=float)
    c0 = f["collateral_allocated"].to_numpy(dtype=float)
    mv = f["collateral_value"].to_numpy(dtype=float)
    h = np.clip(f["haircut_pct"].to_numpy(dtype=float) / 100.0, 0.0, 0.99)
    adj0 = mv * (1 - h)
    capped = (ead > 1e-12) & (c0 >= ead - 1e-9)
    cover0 = np.where(capped, np.maximum(adj0, c0), c0)
    k = (1 + coll_pct / 100.0) * np.clip(1 - h - hair_pp / 100.0, 0.0, 1.0) / (1 - h)
    c1 = np.minimum(ead, np.maximum(cover0 * k, 0.0))
    safe = np.where(ead > 1e-12, ead, 1.0)
    s0 = np.where(ead > 1e-12, np.clip(c0 / safe, 0, 1), 0.0)
    s1 = np.where(ead > 1e-12, np.clip(c1 / safe, 0, 1), 0.0)
    return {"dlgd": lgd_u * (s0 - s1), "s0": s0, "s1": s1, "lgd_u": lgd_u, "c0": c0, "c1": c1}


# ------------------------------------------------------------------ evaluation

def _stage_after(ctx: Context, on: frozenset[str], pd12_new: np.ndarray, pd12_start: np.ndarray) -> np.ndarray:
    f = ctx.frame
    base = f["stage"].to_numpy()
    if "staging" not in on:
        return base.copy()
    dpd = f["dpd"].to_numpy()
    defaulted = (base >= 3) | (f["default_flag"].to_numpy() == 1)
    if ctx.domain == "corporate":
        rank = ctx.rank_new if "rating" in on else np.array([ratings.rank(g) for g in f["grade"]])
        notches = ctx.notches if "rating" in on else 0
        known = rank < len(ratings.RATING_ORDER)
        s3 = (dpd >= 90) | defaulted | (known & (rank >= CORP_STAGE3_RANK))
        s2 = (dpd >= 30) | (known & (rank >= CORP_STAGE2_RANK)) | ((f["nfo"].to_numpy() + notches) >= CORP_SICR_NOTCHES)
    else:
        score = f["behaviour_score"].to_numpy(dtype=float)
        if "rating" in on:
            score = score - RETAIL_BAND_WIDTH * ctx.notches
        s3 = (dpd >= 90) | defaulted
        s2 = (dpd >= 30) | (np.nan_to_num(score, nan=1e9) < RETAIL_SCORE_FLOOR)
    rule_b = (pd12_new >= RULE_B_RATIO * pd12_start) & (pd12_new >= pd12_start + RULE_B_FLOOR)
    s2 = s2 | rule_b
    stage = np.where(s3, 3, np.where(s2, 2, 1))
    stage = np.maximum(stage, base)          # a shock never cures
    # Direct migrations (in step order), deterministic: worst stressed PD first (best first for a cure).
    ids = f["exposure_id"].to_numpy()
    for st, m in zip(ctx.scenario.steps, ctx.masks):
        for mv in st.shocks.stage:
            pool = np.flatnonzero(m & (base == mv["from"]) & (stage == mv["from"]))
            want = int(round(len(np.flatnonzero(m & (base == mv["from"]))) * mv["share"] / 100.0))
            if not want or not len(pool):
                continue
            worse = mv["to"] > mv["from"]
            order = np.lexsort((ids[pool], -pd12_new[pool] if worse else pd12_new[pool]))
            stage[pool[order[:want]]] = mv["to"]
    return stage


def evaluate(ctx: Context, method: Method, on: frozenset[str], cache: dict) -> dict[str, np.ndarray]:
    key = on
    if key in cache:
        return cache[key]
    f = ctx.frame
    n = len(f)
    feat_on = frozenset(d for d in on if d in FEATURE_DRIVERS)
    tkey = ("transmit", feat_on)
    if tkey not in cache:
        cache[tkey] = method.transmit(ctx, feat_on)
    h, lgd = cache[tkey]
    h = h.copy()
    lgd = lgd.copy()
    base_stage = f["stage"].to_numpy()
    defaulted_start = base_stage >= 3
    if "pd" in on:
        for st, m in zip(ctx.scenario.steps, ctx.masks):
            sh = st.shocks.pd
            if not sh:
                continue
            sel = m & ~defaulted_start
            v = float(sh["value"])
            if sh["mode"] == "relative":
                h[sel] = h[sel] * (1 + v / 100.0)
            elif sh["mode"] == "pp":
                h[sel] = h[sel] + v / 100.0
            else:
                h[sel] = h[sel] + v / 10000.0
        h = np.clip(h, 0.0, PD_CAP)
    mpd = marginal(h)
    mpd[defaulted_start] = ctx.start.mpd[defaulted_start]
    if "lgd" in on:
        for st, m in zip(ctx.scenario.steps, ctx.masks):
            sh = st.shocks.lgd
            if not sh:
                continue
            v = float(sh["value"])
            lgd[m] = lgd[m] + v / 100.0 if sh["mode"] == "pp" else lgd[m] * (1 + v / 100.0)
        lgd = np.clip(lgd, 0.0, 1.0)
    if "collateral" in on and ctx.coll_dlgd is not None and ctx.coll_dlgd.any():
        lgd = np.clip(lgd + ctx.coll_dlgd[:, None, None], 0.0, 1.0)
    ead = f["ead"].to_numpy(dtype=float).copy()
    if "ccf" in on:
        undrawn = f["undrawn"].to_numpy(dtype=float)
        ccf = f["ccf"].to_numpy(dtype=float).copy()
        for st, m in zip(ctx.scenario.steps, ctx.masks):
            if st.shocks.ead:
                ead[m] = np.maximum(ead[m] * (1 + st.shocks.ead / 100.0), 0.0)
            sh = st.shocks.ccf
            if not sh:
                continue
            v = float(sh["value"])
            if sh["mode"] == "ead_pct":
                ead[m] = ead[m] * (1 + v / 100.0)
                continue
            new = np.clip(ccf[m] + v / 100.0 if sh["mode"] == "pp" else ccf[m] * (1 + v / 100.0), 0.0, 1.0)
            ead[m] = np.maximum(ead[m] + (new - ccf[m]) * undrawn[m], 0.0)
            ccf[m] = new
    pd12_start = (W[None, :] * ctx.start.mpd[:, :, 0]).sum(1)
    pd12_new = (W[None, :] * mpd[:, :, 0]).sum(1)
    stage = _stage_after(ctx, on, pd12_new, pd12_start)
    new3 = (stage == 3) & ~defaulted_start
    if new3.any():
        mpd[new3] = 0.0
        mpd[new3, :, 0] = 1.0
    e12 = mpd[:, :, 0] * lgd[:, :, 0] * ead[:, None]
    elt = (mpd * lgd).sum(2) * ead[:, None]
    ecl_s = np.where((stage == 1)[:, None], e12, elt)
    out = {"ecl_s": ecl_s, "ecl": (W[None, :] * ecl_s).sum(1), "stage": stage, "ead": ead,
           "pd12": np.where(stage == 3, 1.0, (W[None, :] * mpd[:, :, 0]).sum(1)),
           "lgd1": (W[None, :] * lgd[:, :, 0]).sum(1)}
    cache[key] = out
    return out


def shapley(ctx: Context, method: Method, drivers: list[str], cache: dict) -> dict[str, np.ndarray]:
    k = len(drivers)
    out = {d: np.zeros(len(ctx.frame)) for d in drivers}
    if not k:
        return out
    vals: dict[frozenset, np.ndarray] = {}
    for r in range(k + 1):
        for combo in itertools.combinations(drivers, r):
            s = frozenset(combo)
            vals[s] = evaluate(ctx, method, s, cache)["ecl"]
    fact = math.factorial
    for d in drivers:
        others = [x for x in drivers if x != d]
        for r in range(len(others) + 1):
            wgt = fact(r) * fact(k - r - 1) / fact(k)
            for combo in itertools.combinations(others, r):
                s = frozenset(combo)
                out[d] += wgt * (vals[s | {d}] - vals[s])
    return out


# ------------------------------------------------------------------ the run

def run(scenario: Scenario, method: Method, frame: pd.DataFrame, population: np.ndarray,
        labels: dict[str, str]) -> dict[str, Any]:
    if not population.any():
        raise RunError("Nothing is in scope: no exposure matches.")
    ctx = build_context(scenario, frame, population)
    if not any(m.any() for m in ctx.masks) and scenario.steps:
        raise RunError("None of the named segments, borrowers or facilities is in the population in scope.")
    ctx.start = method.start(ctx)
    ctx.base_h = hazards(ctx.start.mpd)
    cache: dict = {}
    drivers = [d for d in DRIVERS if d in scenario.drivers()]
    if drivers and "staging" not in drivers:
        drivers.append("staging")            # re-assessment is always part of a scenario
    v0 = evaluate(ctx, method, frozenset(), cache)
    v1 = evaluate(ctx, method, frozenset(drivers), cache)
    contrib = shapley(ctx, method, drivers, cache)
    return assemble(ctx, method, v0, v1, contrib, drivers, labels)


def _group(frame: pd.DataFrame, by: str, values: dict[str, np.ndarray]) -> pd.DataFrame:
    g = pd.DataFrame({by: frame[by].to_numpy(), **values})
    return g.groupby(by, sort=False).sum(numeric_only=True)


def assemble(ctx: Context, method: Method, v0: dict, v1: dict, contrib: dict[str, np.ndarray],
             drivers: list[str], labels: dict[str, str]) -> dict[str, Any]:
    f = ctx.frame
    reported = f["ecl_final"].to_numpy(dtype=float)
    start = v0["ecl"]
    scen = v1["ecl"]
    ead0, ead1 = f["ead"].to_numpy(dtype=float), v1["ead"]
    st0, st1 = f["stage"].to_numpy(), v1["stage"]
    lgd0_pct = f["lgd_pct_book"].to_numpy(dtype=float)
    rwa0 = capital.rwa(ctx.domain, f["product"], st0, v0["pd12"], v0["lgd1"] * 100, ead0, start)
    rwa1 = capital.rwa(ctx.domain, f["product"], st1, v1["pd12"], v1["lgd1"] * 100, ead1, scen)
    R, S, X = float(reported.sum()), float(start.sum()), float(scen.sum())
    bars = [{"key": "reported", "label": "Reported ECL", "value": R, "kind": "total"},
            {"key": "model_start", "label": f"Start recomputed ({method.name})", "value": S - R, "kind": "model",
             "total_after": S}]
    for d in DRIVERS:
        bars.append({"key": d, "label": DRIVER_LABELS[d], "value": float(contrib[d].sum()) if d in contrib else 0.0,
                     "kind": "driver", "active": d in contrib})
    bars.append({"key": "scenario", "label": "Scenario ECL", "value": X, "kind": "total"})
    attributed = sum(float(c.sum()) for c in contrib.values())
    cet1 = capital.CET1_RATIO
    rwa_book0 = float(rwa0.sum())
    cards = {
        "reported_ecl": R, "start_ecl": S, "model_error": S - R,
        "model_error_pct": (S - R) / R * 100 if R else 0.0,
        "scenario_ecl": X, "change": X - S, "change_pct": (X - S) / S * 100 if S else 0.0,
        "ead_before": float(ead0.sum()), "ead_after": float(ead1.sum()),
        "coverage_before": S / float(ead0.sum()) * 100 if ead0.sum() else 0.0,
        "coverage_after": X / float(ead1.sum()) * 100 if ead1.sum() else 0.0,
        "stage_before": {str(s): int((st0 == s).sum()) for s in (1, 2, 3)},
        "stage_after": {str(s): int((st1 == s).sum()) for s in (1, 2, 3)},
        "stage_ead_before": {str(s): float(ead0[st0 == s].sum()) for s in (1, 2, 3)},
        "stage_ead_after": {str(s): float(ead1[st1 == s].sum()) for s in (1, 2, 3)},
        "moves": {"1->2": int(((st0 == 1) & (st1 == 2)).sum()), "1->3": int(((st0 == 1) & (st1 == 3)).sum()),
                  "2->3": int(((st0 == 2) & (st1 == 3)).sum()), "2->1": int(((st0 == 2) & (st1 == 1)).sum())},
        "rwa_before": rwa_book0, "rwa_after": float(rwa1.sum()),
        "capital_cet1_before_pct": cet1 * 100,
        "capital_cet1_after_pct": ((cet1 * rwa_book0 - (X - S)) / float(rwa1.sum()) * 100) if rwa1.sum() else 0.0,
        "capital_impact": (X - S) + cet1 * (float(rwa1.sum()) - rwa_book0),
        "exposures": int(len(f)), "owners": int(f["owner_id"].nunique()),
    }
    by_scn = {s: {"before": float(v0["ecl_s"][:, j].sum()), "after": float(v1["ecl_s"][:, j].sum()),
                  "weight": float(W[j])} for j, s in enumerate(store.SCENARIOS)}
    seg = _group(f, "segment", {"ead_before": ead0, "ead_after": ead1, "ecl_before": start, "ecl_after": scen,
                                "reported": reported})
    seg = seg.sort_values("ecl_after", ascending=False)
    by_segment = [{"segment": str(i), **{k: float(v) for k, v in r.items()},
                   "change": float(r["ecl_after"] - r["ecl_before"])} for i, r in seg.iterrows()]
    order = list(ratings.RATING_ORDER) if ctx.domain == "corporate" else ["A", "B", "C", "D", "E"]
    g_after = ctx.grade_new if "rating" in drivers else f["grade"].to_numpy()
    rb = pd.DataFrame({"g": f["grade"].to_numpy(), "ead": ead0, "ecl": start}).groupby("g").sum()
    ra = pd.DataFrame({"g": g_after, "ead": ead1, "ecl": scen}).groupby("g").sum()
    by_rating = [{"grade": g, "ead_before": float(rb["ead"].get(g, 0.0)), "ead_after": float(ra["ead"].get(g, 0.0)),
                  "ecl_before": float(rb["ecl"].get(g, 0.0)), "ecl_after": float(ra["ecl"].get(g, 0.0)),
                  "pd_masterscale_pct": round(ctx.ms.get(g, float("nan")) * 100, 4) if g in ctx.ms else None}
                 for g in order if g in rb.index or g in ra.index]
    mig_n = [[int(((st0 == a) & (st1 == b)).sum()) for b in (1, 2, 3)] for a in (1, 2, 3)]
    mig_e = [[float(ead1[(st0 == a) & (st1 == b)].sum()) for b in (1, 2, 3)] for a in (1, 2, 3)]
    delta = scen - start
    top = np.argsort(-delta, kind="mergesort")[:25]
    names = f["owner_name"].to_numpy() if "owner_name" in f else np.array([None] * len(f))
    movers = [{"exposure_id": str(f["exposure_id"].iat[i]), "owner_id": str(f["owner_id"].iat[i]),
               "owner_name": names[i] if isinstance(names[i], str) else None,
               "segment": str(f["segment"].iat[i]), "grade_before": str(f["grade"].iat[i]),
               "grade_after": str(g_after[i]), "stage_before": int(st0[i]), "stage_after": int(st1[i]),
               "ead": float(ead1[i]), "ecl_before": float(start[i]), "ecl_after": float(scen[i]),
               "change": float(delta[i]),
               "drivers": {d: float(contrib[d][i]) for d in contrib}} for i in top if delta[i] > 1e-12]
    seg_attr = _group(f, "segment", {d: contrib[d] for d in contrib}) if contrib else pd.DataFrame()
    attribution_by_segment = [{"segment": str(i), **{k: float(v) for k, v in r.items()}}
                              for i, r in seg_attr.iterrows()] if len(seg_attr) else []
    return {
        "method": method.key, "method_name": method.name, "cards": cards, "waterfall": bars,
        "reconciliation": {"start_plus_drivers": S + attributed, "scenario": X,
                           "difference": S + attributed - X, "reconciles": abs(S + attributed - X) <= 1e-6 * max(1.0, abs(X))},
        "by_scenario": by_scn, "by_segment": by_segment, "by_rating": by_rating,
        "rating_order": [r["grade"] for r in by_rating],
        "migration": {"counts": mig_n, "ead": mig_e, "stages": [1, 2, 3]},
        "top_movers": movers, "attribution_by_segment": attribution_by_segment,
        "drivers": drivers,
        "lgd_book_avg_pct": float(np.average(lgd0_pct, weights=np.maximum(ead0, 1e-12))) if len(f) else 0.0,
    }


Transmit = Callable[[Context, frozenset], tuple[np.ndarray, np.ndarray]]
