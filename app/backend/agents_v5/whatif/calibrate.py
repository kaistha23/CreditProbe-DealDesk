"""Graded scenarios with stated shocks and a basis (PLAN_R11_AGENTS W2, N5).

Every shock size is computed from history, never typed:

* MEV shocks: the year-on-year moves of each series since 1990 (the What-If MEV store, the same measure
  `whatif_v5.likelihood` uses). A grade is a tail share of the adverse moves:
    Mild      the move reached or exceeded in 25% of years           ("consistent with recent experience")
    Moderate  the move reached or exceeded in 10% of years           ("historically plausible")
    Severe    the worst move on record                                ("severe but historically observed")
    Tail      1.25 x the worst move on record                         (a reverse-stress tail beyond history)
  Sizes are rounded away from zero to the series' step (5% for prices, 0.5pp for rates of growth or
  unemployment, 25bps for policy rates), so a grade is never milder than its quantile.
* Sector stress: the same shares of the segment's own credit-cycle index falls within a year
  (`cycle_model.json`, fitted on observed defaults), capped at the engine's 4 sd.
* Rating: the book's own year-on-year rating migrations (What-If domain history): the Severe grade adds the
  notch move that at least 5% of exposure-years made, the Tail grade one notch more.
* Horizon: Mild 1 year, Moderate 2, Severe 3, Tail all 5 years of the path (a stated grading assumption).

The grade table and each figure's source are returned with the scenario, so the basis can be cited.
"""
from __future__ import annotations

import functools
import math
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5.domain import cycle, mev, store

GRADES = [
    {"key": "mild", "name": "Mild", "share": 0.25, "horizon": 1},
    {"key": "moderate", "name": "Moderate", "share": 0.10, "horizon": 2},
    {"key": "severe", "name": "Severe", "share": None, "horizon": 3},
    {"key": "tail", "name": "Tail", "share": None, "horizon": 5, "beyond": 1.25},
]
STEP = {"pct": 5.0, "pp": 0.5, "bps": 25.0}
#: The MEVs each theme moves together (each at its own historical grade).
THEME_SERIES = {
    "oil": ["brent", "gdp_nonoil"],
    "slowdown": ["gdp_real", "gdp_nonoil", "brent", "unemployment"],
    "rates": ["repo", "saibor_3m"],
    "real_estate": ["re_price"],
    "unemployment": ["unemployment"],
}
#: How the compound parser names each series (the agent's sentences read back exactly).
PHRASE = {"gdp_real": "real GDP growth", "gdp_nonoil": "non-oil GDP growth", "brent": "oil price", "cpi": "inflation",
          "unemployment": "unemployment", "repo": "repo rate", "saibor_3m": "SAIBOR", "gov_spend": "government spending",
          "re_price": "real estate prices", "current_account": "current account", "credit_growth": "credit growth"}
THEME_NAMES = {"oil": "oil price shock", "slowdown": "regional slowdown", "rates": "rates shock",
               "real_estate": "real estate correction", "unemployment": "unemployment shock"}
SECTOR_CAP = 4.0
#: Growth-rate series: graded on the shortfall against their own trailing 5-year average.
GROWTH_SERIES = ("gdp_real", "gdp_nonoil", "credit_growth", "cpi")


def _round_away(x: float, step: float) -> float:
    return math.copysign(step * math.ceil(abs(x) / step - 1e-9), x) if x else 0.0


@functools.lru_cache(maxsize=32)
def mev_moves(key: str) -> pd.Series:
    """Year-on-year moves of a series in its shock unit (as `likelihood._mev_item` measures them)."""
    s = mev.BY_KEY[key]
    a = mev.annual()[key].loc[:2025].dropna()
    if key in GROWTH_SERIES:
        # A growth rate's shock is a shortfall against its path: growth against its average of the previous 5 years
        # (the year-on-year change of a growth rate counts base effects, e.g. 2023 after 2022).
        return (a - a.shift(1).rolling(5, min_periods=3).mean()).dropna()
    if s.shock_unit == "pct":
        return ((a / a.shift(1) - 1) * 100).dropna()
    if s.shock_unit == "bps":
        return ((a - a.shift(1)) * 100).dropna()
    return (a - a.shift(1)).dropna()


def mev_grade(key: str, grade: dict[str, Any]) -> dict[str, Any]:
    s = mev.BY_KEY[key]
    ch = mev_moves(key)
    adverse = -1 if s.direction > 0 else +1          # a fall hurts a "rise is good" series
    moves = ch * adverse                              # adverse moves are positive
    worst = float(moves.max())
    worst_year = int(moves.idxmax())
    measure = "shortfall against the previous 5-year average" if key in GROWTH_SERIES else "year-on-year move"
    if grade["share"] is not None:
        q = float(np.quantile(moves, 1 - grade["share"]))
        raw = max(q, 0.0)
        how = f"{s.name}: the adverse {measure} reached in {grade['share'] * 100:.0f}% of {len(moves)} years since {int(ch.index.min())}"
    else:
        raw = worst * grade.get("beyond", 1.0)
        how = (f"{s.name}: the worst {measure} on record ({worst * adverse:+.1f} in {worst_year})" if "beyond" not in grade
               else f"{s.name}: {grade['beyond']:g} x the worst {measure} on record ({worst * adverse:+.1f} in {worst_year})")
    unit = s.shock_unit
    size = _round_away(raw * adverse, STEP[unit])
    if unit == "pct":
        size = max(size, -95.0)
    seen = int((moves >= abs(size) - 1e-9).sum())
    return {"series": key, "name": s.name, "unit": unit, "value": size, "raw": raw * adverse, "basis": how,
            "grade_share_pct": (grade["share"] or 0) * 100, "beyond": grade.get("beyond", 0.0),
            "years_seen": seen, "years": int(len(moves)), "worst": worst * adverse, "worst_year": worst_year,
            "source": "What-If MEV store (IMF, SAMA, GASTAT, EIA), annual"}


@functools.lru_cache(maxsize=4)
def _cycle(domain: str) -> dict[str, Any]:
    return cycle.load(domain)


def sector_grade(domain: str, segment: str, grade: dict[str, Any]) -> dict[str, Any]:
    model = _cycle(domain)
    series = pd.Series(model.get("segment_z", {}).get(segment) or model["book_z"])
    lag = 4 if domain == "corporate" else 12
    drop = (series.shift(lag) - series).dropna()
    drop = drop[drop > 0] if (drop > 0).any() else drop.abs()
    worst = float(drop.max()) if len(drop) else 1.0
    if grade["share"] is not None and len(drop):
        raw = float(np.quantile(drop, 1 - grade["share"]))
        how = f"the fall of the {segment} credit-cycle index reached in {grade['share'] * 100:.0f}% of {len(drop)} falling periods"
    else:
        raw = worst * grade.get("beyond", 1.0)
        how = (f"the worst one-year fall of the {segment} credit-cycle index ({worst:.2f} sd)" if "beyond" not in grade
               else f"{grade['beyond']:g} x the worst one-year fall of the {segment} credit-cycle index ({worst:.2f} sd)")
    size = round(min(SECTOR_CAP, _round_away(raw, 0.1)), 1)
    return {"segment": segment, "value": size, "raw": raw, "basis": how, "worst": worst, "periods": int(len(drop)),
            "grade_share_pct": (grade["share"] or 0) * 100, "beyond": grade.get("beyond", 0.0), "step_sd": 0.1,
            "source": f"credit-cycle model ({domain}), fitted on observed defaults"}


@functools.lru_cache(maxsize=4)
def rating_notches(domain: str) -> dict[str, Any]:
    """The notch move at least 5% of performing exposure-years made in a year (the book's own history)."""
    h = store.history(domain, ["exposure_id", "grade_rank", "stage"])
    ps = store.periods(domain)
    lag = 4 if domain == "corporate" else 12
    rows = []
    for a, b in zip(ps, ps[lag:]):
        x = h[(h["period"] == a) & (h["stage"] < 3)].set_index("exposure_id")["grade_rank"]
        y = h[h["period"] == b].set_index("exposure_id")["grade_rank"]
        both = pd.concat([x.rename("a"), y.rename("b")], axis=1, join="inner").dropna()
        rows.append((both["b"] - both["a"]).to_numpy())
    mv = np.concatenate(rows) if rows else np.zeros(1)
    n = 1
    while n < 4 and (mv >= n + 1).mean() >= 0.05:
        n += 1
    return {"notches": n, "share": float((mv >= n).mean()), "observations": int(len(mv)),
            "basis": f"{(mv >= n).mean() * 100:.1f}% of {len(mv):,} performing exposure-years moved {n} or more notches down in a year",
            "source": f"What-If domain history ({domain})"}


def grade_scenario(domain: str, themes: list[str], segments: list[str], grade: dict[str, Any]) -> dict[str, Any]:
    """One graded scenario: its shocks (structured), its plain-words sentence and the basis of every size."""
    series: list[str] = []
    for th in themes:
        for k in THEME_SERIES.get(th, []):
            if k not in series:
                series.append(k)
    basis: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    words: list[str] = []
    mev_shocks: dict[str, float] = {}
    for k in series:
        g = mev_grade(k, grade)
        if g["value"]:
            mev_shocks[k] = g["value"]
            basis.append({"kind": "history", "what": f"{g['name']} {_fmt(g['value'], g['unit'])}", **g})
    horizon = grade["horizon"]
    if mev_shocks:
        sh: dict[str, Any] = {"mev": mev_shocks}
        if horizon:
            sh["horizon"] = horizon
        steps.append({"shocks": sh, "scope": {}, "restatement": ", ".join(
            f"{mev.BY_KEY[k].name} {_fmt(v, mev.BY_KEY[k].shock_unit)}" for k, v in mev_shocks.items())
            + (f" for {horizon} year{'s' if horizon != 1 else ''}" if horizon else " over the 5-year path")})
        words.append(steps[-1]["restatement"])
    for seg in segments:
        g = sector_grade(domain, seg, grade)
        sh = {"sector": g["value"]}
        rating = 0
        if grade["key"] in ("severe", "tail"):
            r = rating_notches(domain)
            rating = r["notches"] + (1 if grade["key"] == "tail" else 0)
            sh["rating"] = rating
            basis.append({"kind": "book history", "what": f"{seg} downgrade {rating} notch{'es' if rating != 1 else ''}",
                          "value": rating, **{k: v for k, v in r.items() if k != "notches"}})
        if horizon:
            sh["horizon"] = horizon
        basis.append({"kind": "book history", "what": f"{seg} sector stress {g['value']:.1f} sd", **g})
        restate = f"{seg}: sector stress {g['value']:.1f} sd" + (f", downgrade {rating} notch{'es' if rating != 1 else ''}" if rating else "") \
            + (f" for {horizon} year{'s' if horizon != 1 else ''}" if horizon else "")
        steps.append({"shocks": sh, "scope": {"segments": [seg]}, "restatement": restate})
        words.append(restate)
    if not segments and not series and grade["key"] in ("severe", "tail") and domain == "corporate":
        r = rating_notches(domain)
        n = r["notches"] + (1 if grade["key"] == "tail" else 0)
        steps.append({"shocks": {"rating": n}, "scope": {}, "restatement": f"downgrade the book {n} notch{'es' if n != 1 else ''}"})
        basis.append({"kind": "book history", "what": f"book downgrade {n} notch{'es' if n != 1 else ''}", "value": n,
                      **{k: v for k, v in r.items() if k != "notches"}})
        words.append(steps[-1]["restatement"])
    theme_name = " and ".join(THEME_NAMES.get(t, t) for t in themes) or (", ".join(segments) + " stress")
    return {"key": grade["key"], "name": f"{grade['name']} {theme_name}", "grade": grade["name"], "steps": steps,
            "sentence": "; ".join(words), "basis": basis, "horizon": horizon}


def _fmt(v: float, unit: str) -> str:
    return f"{v:+g}%" if unit == "pct" else f"{v:+g}pp" if unit == "pp" else f"{v:+g}bps"


def graded(domain: str, themes: list[str], segments: list[str], n: int = 4) -> list[dict[str, Any]]:
    """`n` grades, strictly ordered: a size that rounds to the previous grade's is raised one step past it."""
    out: list[dict[str, Any]] = []
    prev: dict[tuple, float] = {}
    for g in GRADES[:n]:
        sc = grade_scenario(domain, themes, segments, g)
        for st in sc["steps"]:
            seg = tuple(st["scope"].get("segments", []))
            for k, v in list(st["shocks"].get("mev", {}).items()):
                unit = mev.BY_KEY[k].shock_unit
                p = prev.get(("mev", k))
                if p is not None and abs(v) <= abs(p) + 1e-9:
                    st["shocks"]["mev"][k] = v = math.copysign(abs(p) + STEP[unit], p)
                    for b in sc["basis"]:
                        if b.get("series") == k:
                            b["value"] = v
                            b["what"] = f"{b['name']} {_fmt(v, unit)}"
                            b["basis"] += f"; raised one step past the {out[-1]['grade']} grade so the grades stay ordered"
                prev[("mev", k)] = v
            if "sector" in st["shocks"]:
                v, p = st["shocks"]["sector"], prev.get(("sector", seg))
                if p is not None and v <= p + 1e-9:
                    st["shocks"]["sector"] = v = min(SECTOR_CAP, round(p + 0.1, 1))
                    for b in sc["basis"]:
                        if b.get("segment") in seg and "sector stress" in b["what"]:
                            b["value"] = v
                            b["what"] = f"{seg[0]} sector stress {v:.1f} sd"
                            b["basis"] += f"; raised 0.1 sd past the {out[-1]['grade']} grade so the grades stay ordered"
                prev[("sector", seg)] = v
            st["restatement"] = _restate(st)
        sc["sentence"] = "; ".join(st["restatement"] for st in sc["steps"])
        out.append(sc)
    return out


def _restate(st: dict[str, Any]) -> str:
    sh = st["shocks"]
    parts: list[str] = []
    seg = st["scope"].get("segments", [])
    for k, v in sh.get("mev", {}).items():
        parts.append(f"{PHRASE.get(k, k)} {_fmt(v, mev.BY_KEY[k].shock_unit)}")
    if sh.get("sector"):
        parts.append(f"sector stress {sh['sector']:.1f} sd")
    if sh.get("rating"):
        n = sh["rating"]
        parts.append(f"downgrade {n} notch{'es' if n != 1 else ''}" if not seg else f"downgrade {n} notch{'es' if n != 1 else ''}")
    h = sh.get("horizon", 0)
    tail = f" for {h} year{'s' if h != 1 else ''}" if h else " over the 5-year path"
    text = ", ".join(parts) + tail
    return f"{', '.join(seg)}: {text}" if seg else (text if sh.get("mev") else f"the book: {text}")


__all__ = ["GRADES", "THEME_SERIES", "graded", "grade_scenario", "mev_grade", "rating_notches", "sector_grade"]
