"""Severity calibration: mild, moderate and severe for every driver, from the empirical distribution of its move
over the one-year scenario horizon (PLAN_R13 §S.1, J5).

For a driver with observed one-year moves x_1..x_n, written in the adverse direction (a = -x for a fall that hurts,
a = x for a rise that hurts), with Q(p) the empirical quantile (linear interpolation between order statistics,
Hyndman-Fan type 7, numpy's default):

    mild      = Q(0.75)                          about 1 year in 4
    moderate  = Q(0.92)  (band Q(0.90)..Q(0.93)) about 1 in 10 to 1 in 15
    severe    = max(Q(0.96), worst observed episode)   1 in 25 or worse

The observed frequency of each threshold is the share of observations at least that adverse, with the years (or
sector-quarters) it happened. The cross-check (Anne's rule of thumb) compares mild with the average adverse move:
mild / mean(a | a > 0) should be 1.10-1.20.

Fallback: when fewer than MIN_OBS independent observations exist, or the data cannot measure the driver (a mark is
not a price; a workout is unfinished), the severity is the labelled expert / ICAAP-style value instead, and the
rejected estimate is kept beside it.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from backend.scenarios import data

MIN_OBS = 15
P_MILD, P_MOD, P_MOD_BAND, P_SEV = 0.75, 0.92, (0.90, 0.93), 0.96
SEVERITIES = ("mild", "moderate", "severe")
RULE_BAND = (1.10, 1.20)
#: drivers calibrated for comparison only (never a severity in force)
SENSITIVITY_ONLY = frozenset({"revenue_relative"})
SHORT = {"brent": "oil", "gdp_real": "real GDP", "gdp_nonoil": "non-oil GDP", "saibor": "SAIBOR", "sector_cycle": "sector cycle",
         "pd_multiplier": "sector PD", "revenue": "revenue", "revenue_relative": "relative revenue", "margin": "margin",
         "rating": "rating", "utilisation": "utilisation", "collateral": "collateral", "re_price": "real-estate prices",
         "lgd": "downturn LGD", "customer": "customer loss", "payment_delay": "payment delay", "project_delay": "project delay"}
EXPERT = "expert (R11 Risk Models assumption; no ICAAP set loaded)"


@dataclass
class Obs:
    """One-year moves in the adverse direction, with a label for each (a year, or 'sector quarter')."""
    values: np.ndarray
    labels: list[str]
    n_independent: int
    episodes: pd.Series            # aggregate episodes (label -> adverse move); the worst is the 'worst observed episode'
    unit_note: str = ""


@dataclass
class Driver:
    key: str
    label: str
    unit: str                      # unit of the adverse move: "%", "pp", "bps", "x", "notches", "months", "days", "share"
    adverse: str                   # e.g. "a fall", "a rise"
    source: str                    # relation(s)
    window: str
    observe: Callable[[], Obs] | None
    fallback: tuple[float, float, float]
    fallback_label: str = EXPERT
    force_fallback: str = ""       # a reason the data cannot measure this driver even when n is large
    families: tuple[str, ...] = ()
    decimals: int = 1
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ the observations

def _annual_changes(key: str, kind: str) -> Obs:
    s = data.macro_annual()[key].dropna()
    if kind == "pct_fall":
        ch = (s / s.shift(1) - 1).dropna() * 100
        a = -ch
    elif kind == "slowdown":
        ch = (s - s.shift(1)).dropna()
        a = -ch
    elif kind == "rise_bps":
        ch = (s - s.shift(1)).dropna() * 100
        a = ch
    else:
        raise KeyError(kind)
    lab = [str(int(y)) for y in a.index]
    return Obs(a.to_numpy(float), lab, len(a), pd.Series(a.to_numpy(float), index=lab))


def _yoy_panel(frame: pd.DataFrame, unit: str, value: str, adverse: Callable[[pd.Series, pd.Series], pd.Series],
               group: str | None = None, agg_weight: str | None = None) -> Obs:
    """Four-quarter moves per unit (overlapping quarterly windows); n_independent counts non-overlapping years per unit.
    Episodes: the group (sector) average of the adverse move per quarter."""
    f = frame[[unit, "t", "reporting_quarter", value] + ([group] if group and group != unit else [])].dropna(subset=[value])
    prev = f[[unit, "t", value]].assign(t=lambda d: d["t"] + data.LAG)
    m = f.merge(prev, on=[unit, "t"], suffixes=("", "_prev"))
    m["a"] = adverse(m[value], m[f"{value}_prev"])
    m = m[np.isfinite(m["a"])]
    per_unit = m.groupby(unit)["t"].nunique()
    n_ind = int((per_unit // data.LAG).sum())
    lab = (m[group] + " " + m["reporting_quarter"]).tolist() if group else (m[unit] + " " + m["reporting_quarter"]).tolist()
    if group and group != unit:
        ep = m.groupby([group, "reporting_quarter"])["a"].mean()
    else:
        ep = m.set_index([unit, "reporting_quarter"])["a"]
    ep.index = [f"{g} {q}" for g, q in ep.index]
    return Obs(m["a"].to_numpy(float), lab, n_ind, ep)


def _brent() -> Obs:
    return _annual_changes("brent", "pct_fall")


def _gdp_real() -> Obs:
    return _annual_changes("gdp_real", "slowdown")


def _gdp_nonoil() -> Obs:
    return _annual_changes("gdp_nonoil", "slowdown")


def _saibor() -> Obs:
    return _annual_changes("saibor_3m", "rise_bps")


def _re_price() -> Obs:
    return _annual_changes("re_price", "pct_fall")


def _sector_cycle() -> Obs:
    z = data.cycle_model()["segment_z"]
    rows = [{"sector": s, "reporting_quarter": q, "t": data.quarter_index(q), "z": v} for s, d in z.items() for q, v in d.items()]
    f = pd.DataFrame(rows)
    return _yoy_panel(f, "sector", "z", lambda now, before: before - now)


def _pd_multiplier() -> Obs:
    f = data.sector_quarter()
    return _yoy_panel(f, "sector", "pd", lambda now, before: now / before)


def _revenue() -> Obs:
    b = data.borrower()
    b = b[b["revenue_sar_mn"] > 0]
    return _yoy_panel(b, "borrower_id", "revenue_sar_mn", lambda now, before: -(now / before - 1) * 100, group="sector")


def _revenue_relative() -> Obs:
    """The borrower's revenue growth below its sector's median growth in the same quarter (an idiosyncratic shortfall)."""
    b = data.borrower()
    b = b[b["revenue_sar_mn"] > 0]
    prev = b[["borrower_id", "t", "revenue_sar_mn"]].assign(t=lambda d: d["t"] + data.LAG)
    m = b.merge(prev, on=["borrower_id", "t"], suffixes=("", "_prev"))
    g = (m["revenue_sar_mn"] / m["revenue_sar_mn_prev"] - 1) * 100
    m = m.assign(rel=-(g - g.groupby([m["sector"], m["reporting_quarter"]]).transform("median")))
    m = m.assign(rel_level=m["rel"])
    n_ind = int((m.groupby("borrower_id")["t"].nunique() // data.LAG).sum())
    ep = m.groupby(["sector", "reporting_quarter"])["rel"].quantile(0.9)
    ep.index = [f"{a} {q} (P90 of its borrowers)" for a, q in ep.index]
    return Obs(m["rel"].to_numpy(float), (m["sector"] + " " + m["reporting_quarter"]).tolist(), n_ind, ep)


def _margin() -> Obs:
    b = data.borrower()
    return _yoy_panel(b, "borrower_id", "ebitda_margin_pct", lambda now, before: -(now - before) * 100, group="sector")


def _rating() -> Obs:
    b = data.borrower()
    b = b[b["rank"] < 19]
    return _yoy_panel(b, "borrower_id", "rank", lambda now, before: (now - before).astype(float), group="sector")


def _utilisation() -> Obs:
    f = data.facility()
    f = f[(f["stage"] < 3) & (f["limit_sar_mn"] > 0)]
    return _yoy_panel(f, "facility_id", "utilisation_pct", lambda now, before: now - before, group="sector")


@functools.lru_cache(maxsize=1)
def _collateral_frame() -> pd.DataFrame:
    c = pd.read_parquet(data.CORP / "corp_collateral_quarter.parquet",
                        columns=["collateral_id", "reporting_quarter", "collateral_type", "sector", "market_value_sar_mn"])
    c["t"] = c["reporting_quarter"].map(data.quarter_index)
    return c


def _collateral() -> Obs:
    c = _collateral_frame()
    c = c[c["market_value_sar_mn"] > 0]
    return _yoy_panel(c, "collateral_id", "market_value_sar_mn", lambda now, before: -(now / before - 1) * 100,
                      group="collateral_type")


# ------------------------------------------------------------------ the drivers

def drivers() -> list[Driver]:
    w = data.window()
    bank = f"{w['bank_from']}–{w['bank_to']} (four-quarter moves)"
    rd = data.resolved_defaults()
    return [
        Driver("brent", "Oil price (Brent), one-year fall", "%", "a fall", "U.S. EIA Brent spot (whatif.mev_annual, annual average)",
               f"{w['macro_from']}–{w['macro_to']}", _brent, (15.0, 30.0, 45.0), families=("macro",), decimals=0),
        Driver("gdp_real", "Real GDP growth, one-year slowdown", "pp", "a slowdown", "IMF WEO real GDP growth (whatif.mev_annual)",
               f"{w['macro_from']}–{w['macro_to']}", _gdp_real, (1.5, 3.0, 4.5), decimals=1),
        Driver("gdp_nonoil", "Non-oil real GDP growth, one-year slowdown", "pp", "a slowdown",
               "IMF non-oil real GDP growth via FRED SAUNGDPXORPCHPT (whatif.mev_annual)", f"{w['nonoil_from']}–{w['macro_to']}",
               _gdp_nonoil, (1.5, 3.0, 4.5), families=("macro",), decimals=1),
        Driver("saibor", "3-month SAIBOR, one-year rise", "bps", "a rise", "SAMA 3-month SAIBOR (whatif.mev_annual)",
               f"{w['saibor_from']}–{w['macro_to']}", _saibor, (100.0, 200.0, 300.0), families=("macro",), decimals=0),
        Driver("sector_cycle", "Sector credit-cycle index, one-year fall", "sd", "a fall",
               "What-If sector credit-cycle index (Vasicek-implied Z from observed PDs, cycle_model.json)", bank, _sector_cycle,
               (0.5, 1.0, 1.5), families=("sector",), decimals=2),
        Driver("pd_multiplier", "Sector 12-month PD, one-year multiplier", "x", "a rise",
               "cockpit.corp_facility_quarter (EAD-weighted pd_pit_12m, performing facilities, by sector)", bank, _pd_multiplier,
               (1.25, 1.5, 2.0), decimals=2),
        Driver("revenue", "Borrower revenue, one-year fall", "%", "a fall", "cockpit.corp_borrower_quarter (revenue_sar_mn)",
               bank, _revenue, (10.0, 20.0, 30.0), families=("borrower",), decimals=1),
        Driver("revenue_relative", "Borrower revenue shortfall against its sector (sensitivity only)", "%", "a shortfall",
               "cockpit.corp_borrower_quarter (revenue_sar_mn against the sector median)", bank, _revenue_relative,
               (10.0, 20.0, 30.0), decimals=1),
        Driver("margin", "Borrower EBITDA margin, one-year fall", "bps", "a fall", "cockpit.corp_borrower_quarter (ebitda_margin_pct)",
               bank, _margin, (150.0, 300.0, 450.0), families=("borrower",), decimals=0),
        Driver("rating", "Borrower rating, one-year downgrade", "notches", "a downgrade", "cockpit.corp_borrower_quarter (rating_current)",
               bank, _rating, (1.0, 2.0, 3.0), families=("rating",), decimals=0),
        Driver("utilisation", "Facility utilisation, one-year rise", "pp", "a rise", "cockpit.corp_facility_quarter (utilisation_pct)",
               bank, _utilisation, (5.0, 10.0, 25.0), decimals=1),
        Driver("collateral", "Collateral value, one-year fall", "%", "a fall", "cockpit.corp_collateral_quarter (market_value_sar_mn)",
               bank, _collateral, (20.0, 30.0, 40.0), families=("collateral",), decimals=0,
               force_fallback="the bank's collateral values are appraisal marks (revalued every few quarters, within one expansion), "
                              "not a market price index, so their moves do not measure a price shock"),
        Driver("re_price", "Real-estate prices, one-year fall", "%", "a fall", "GASTAT real-estate price index (whatif.mev_annual)",
               f"{w['re_price_from']}–{w['macro_to']}", _re_price, (10.0, 20.0, 30.0), families=("collateral",), decimals=0),
        Driver("lgd", "LGD in a downturn, add-on", "pp", "a rise", "cockpit.corp_facility_quarter (write_off_sar_mn, recovery_sar_mn)",
               bank, None, (3.0, 6.0, 10.0), fallback_label="expert overlay (Risk Models): no downturn LGD can be estimated",
               force_fallback=(f"only {rd['resolved_facilities']:,} of {rd['defaulted_facilities']:,} defaulted facilities have a booked "
                               f"recovery or write-off, all since {rd['first_resolution']}, and real-estate workouts take about 2.5 years"),
               decimals=0),
        Driver("customer", "Largest customer, share of its revenue lost", "share", "a loss", "no relation holds customer-level revenue",
               "none", None, (1 / 3, 2 / 3, 1.0), force_fallback="no customer-level revenue history exists in the bank data",
               families=("borrower",), decimals=2),
        Driver("payment_delay", "Customer payment delay", "days", "a delay", "no relation holds receivable days by quarter", "none",
               None, (30.0, 60.0, 90.0), force_fallback="receivable days are not in the quarterly borrower history", families=("borrower",),
               decimals=0),
        Driver("project_delay", "Project milestone delay", "months", "a delay", "no relation holds project milestone history", "none",
               None, (3.0, 6.0, 12.0), force_fallback="no project milestone history exists in the bank data", families=("borrower",),
               decimals=0),
    ]


BY_KEY: dict[str, Driver] = {}


def quantile(values: np.ndarray, p: float) -> float:
    return float(np.quantile(np.asarray(values, float), p))


def frequency(obs: Obs, threshold: float) -> dict[str, Any]:
    hit = obs.values >= threshold - 1e-12
    n = len(obs.values)
    labs = [l for l, h in zip(obs.labels, hit) if h]
    share = float(hit.mean()) if n else 0.0
    return {"count": int(hit.sum()), "of": n, "share": share, "one_in": (1 / share) if share > 0 else None,
            "labels": labs if len(labs) <= 12 else labs[-12:], "labels_total": len(labs)}


def _fmt(v: float, unit: str, dp: int) -> str:
    if unit == "x":
        return f"×{v:.{dp}f}"
    if unit == "share":
        return f"{v * 100:.0f}%"
    if unit == "notches":
        return f"{v:.0f} notch" + ("" if abs(v - 1) < 1e-9 else "es")
    sp = "" if unit in ("%",) else " "
    return f"{v:,.{dp}f}{sp}{unit}"


DISCRETE_TAIL = {"mild": 1 - P_MILD, "moderate": 1 - P_MOD, "severe": 1 - P_SEV}


def _discrete(est: dict[str, Any], obs: Obs) -> None:
    """Whole notches: each severity is the smallest whole move n >= 1 at least as rare as its tail (P(a >= n) <= 25%,
    8%, 4%); severe is also at least the worst episode, and one notch beyond moderate when the history holds it."""
    v = obs.values
    share = lambda n: float((v >= n - 1e-12).mean())  # noqa: E731
    top = int(np.floor(v.max())) if len(v) else 1
    pick = {}
    for s, tail in DISCRETE_TAIL.items():
        n = next((k for k in range(1, max(top, 1) + 1) if share(k) <= tail), max(top, 1))
        pick[s] = float(n)
    pick["severe"] = max(pick["severe"], float(np.ceil(est["worst_episode"] - 1e-9)))
    if pick["severe"] <= pick["moderate"] and share(pick["moderate"] + 1) > 0:
        pick["severe"] = pick["moderate"] + 1
        est["severe_basis"] = f"one notch beyond moderate (seen in {share(pick['severe']) * 100:.2f}% of observations)"
    else:
        est["severe_basis"] = "P96"
    est["discrete_share"] = {int(k): share(k) for k in range(1, top + 1)}
    est.update(pick)
    est["freq"] = {s: frequency(obs, x) for s, x in pick.items()}


def calibrate_driver(d: Driver, obs: Obs | None = None) -> dict[str, Any]:
    """One driver's three severities with their evidence (the row the memo, the chat and the ladder read)."""
    if obs is None and d.observe is not None:
        obs = d.observe()
    est: dict[str, Any] | None = None
    if obs is not None and len(obs.values):
        v = obs.values
        mild, mod = quantile(v, P_MILD), quantile(v, P_MOD)
        band = (quantile(v, P_MOD_BAND[0]), quantile(v, P_MOD_BAND[1]))
        p96 = quantile(v, P_SEV)
        worst_lab = str(obs.episodes.idxmax()) if len(obs.episodes) else ""
        worst = float(obs.episodes.max()) if len(obs.episodes) else float(v.max())
        sev = max(p96, worst)
        adverse = v[v > 0]
        avg = float(adverse.mean()) if len(adverse) else 0.0
        if d.unit == "x":
            adverse = v[v > 1] - 1
            avg = float(adverse.mean()) if len(adverse) else 0.0
            ratio = (mild - 1) / avg if avg > 0 else None
        else:
            ratio = mild / avg if avg > 0 else None
        est = {"mild": mild, "moderate": mod, "moderate_band": band, "p96": p96, "severe": sev,
               "severe_basis": "worst observed episode" if worst >= p96 else "P96", "worst_episode": worst,
               "worst_episode_label": worst_lab, "n": int(len(v)), "n_independent": int(obs.n_independent),
               "mean_adverse": avg, "rule_ratio": ratio, "share_adverse": float((v > (1 if d.unit == "x" else 0)).mean()),
               "freq": {s: frequency(obs, x) for s, x in (("mild", mild), ("moderate", mod), ("severe", sev))},
               "median": quantile(v, 0.5), "min": float(v.min()), "max": float(v.max())}
    if est is not None and d.unit == "notches":
        _discrete(est, obs)
    reason = d.force_fallback
    if not reason and (est is None or est["n_independent"] < MIN_OBS):
        n = est["n_independent"] if est else 0
        reason = f"only {n} independent one-year observations (fewer than {MIN_OBS})"
    if not reason and est is not None and est["moderate"] <= (1.0 if d.unit == "x" else 0.0):
        reason = (f"the history holds no adverse tail: {100 - est['share_adverse'] * 100:.0f}% of the {est['n']:,} observed "
                  f"one-year moves went the good way and the P92 move is {_fmt(est['moderate'], d.unit, d.decimals)} "
                  f"(one expansion, no contraction)")
    used = "fallback" if reason else "empirical"
    vals = dict(zip(SEVERITIES, d.fallback)) if reason else {s: est[s] for s in SEVERITIES}  # type: ignore[index]
    row = {"key": d.key, "label": d.label, "unit": d.unit, "adverse": d.adverse, "source": d.source, "window": d.window,
           "families": list(d.families), "method": used, "values": vals, "estimate": est,
           "fallback_reason": reason or None, "fallback_label": d.fallback_label if reason else None,
           "fallback_values": dict(zip(SEVERITIES, d.fallback)),
           "display": {s: _fmt(vals[s], d.unit, d.decimals) for s in SEVERITIES}, "decimals": d.decimals}
    row["text"] = describe(row)
    return row


def describe(row: dict[str, Any]) -> str:
    """One deterministic sentence of evidence per driver."""
    est = row["estimate"]
    dsp = row["display"]
    if row["method"] == "fallback":
        base = (f"{row['label']}: mild {dsp['mild']}, moderate {dsp['moderate']}, severe {dsp['severe']}, "
                f"{row['fallback_label']}, because {row['fallback_reason']}.")
        if est:
            base += (f" The rejected estimate from {row['window']} was P75 {_fmt(est['mild'], row['unit'], row['decimals'])}, "
                     f"P92 {_fmt(est['moderate'], row['unit'], row['decimals'])}.")
        return base
    mod = est["freq"]["moderate"]
    basis = est["severe_basis"]
    sev = f"the worst observed episode, {est['worst_episode_label']}" if basis == "worst observed episode" else basis
    txt = (f"{row['label']}: mild {dsp['mild']} (P75), moderate {dsp['moderate']} (P92), severe {dsp['severe']} ({sev}); "
           f"a move at least moderate happened in {mod['count']:,} of {mod['of']:,} {'years' if est['n'] == est['n_independent'] else 'observations'}")
    if est["n"] == est["n_independent"] and mod["labels"]:
        txt += f" ({', '.join(mod['labels'][-5:])})"
    txt += f"; window {row['window']}, {est['n_independent']:,} independent observations."
    return txt


def rule_check(row: dict[str, Any]) -> str:
    est = row["estimate"]
    if not est or est.get("rule_ratio") is None:
        return "not applicable (no estimate)"
    r = est["rule_ratio"]
    lo, hi = RULE_BAND
    if lo <= r <= hi:
        return f"consistent: mild is {(r - 1) * 100:.0f}% beyond the average adverse move (rule of thumb 10–20%)"
    return (f"outside the rule of thumb: mild is {(r - 1) * 100:+.0f}% against the average adverse move "
            f"(rule of thumb +10% to +20%); the percentile rule is kept")


@functools.lru_cache(maxsize=1)
def calibrate_all() -> dict[str, dict[str, Any]]:
    out = {}
    for d in drivers():
        BY_KEY[d.key] = d
        row = calibrate_driver(d)
        row["rule_check"] = rule_check(row)
        out[d.key] = row
    return out


@functools.lru_cache(maxsize=1)
def drivers_by_key() -> dict[str, Driver]:
    return {d.key: d for d in drivers()}
