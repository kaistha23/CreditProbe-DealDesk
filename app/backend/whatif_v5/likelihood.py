"""How likely is a scenario? Measured on history, never presented as a probability.

For each shock of the scenario, the same move is looked for in history:
  rating      the year-on-year average notch move of the exposures in scope (What-If domain,
              every period with a period one year earlier), EAD-weighted; and the share of
              exposure-years that moved at least that many notches
  pd          the year-on-year change in the scope's EAD-weighted 12-month PD
  lgd         the year-on-year change in the scope's EAD-weighted LGD (pp)
  ccf / ead   the year-on-year change in the scope's EAD (%)
  sector      the fall in the segment's credit-cycle index over a year (sd), from observed defaults
  stage       the largest share of Stage 1 (or 2) that moved within a year
  mev         the annual change of the series since 1990 (or since the series starts): how many
              years moved at least as far in the same direction (IMF, SAMA, GASTAT, EIA history)

Wording (the worst across shocks is the scenario's): "Consistent with recent experience" (seen in at
least 20% of the history), "Historically plausible" (5-20%), "Severe but historically observed"
(seen, under 5%), "Outside observed history" (never seen). A severe scenario is never refused.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5.domain import cycle, mev, store
from backend.whatif_v5.models.engine import scope_mask
from backend.whatif_v5.models.scenario import Scenario

LABELS = ["Consistent with recent experience", "Historically plausible", "Severe but historically observed",
          "Outside observed history"]


def label_for(share: float, seen: bool) -> int:
    if share >= 0.20:
        return 0
    if share >= 0.05:
        return 1
    if seen:
        return 2
    return 3


@functools.lru_cache(maxsize=2)
def panel(domain: str) -> pd.DataFrame:
    cols = ["exposure_id", "owner_id", "segment", "subsegment", "product", "stage", "grade", "grade_rank", "ead",
            "pd12_book", "lgd_pct_book"]
    h = store.history(domain, cols)
    periods = store.periods(domain)
    lag = 4 if domain == "corporate" else 12
    pos = {p: i for i, p in enumerate(periods)}
    h["t"] = h["period"].map(pos)
    prev = h[["exposure_id", "t", "grade_rank", "stage", "pd12_book", "lgd_pct_book", "ead"]].copy()
    prev["t"] = prev["t"] + lag
    m = h.merge(prev, on=["exposure_id", "t"], suffixes=("", "_prev"), how="left")
    return m


def _scope_frame(domain: str, scenario: Scenario, step_scope) -> pd.DataFrame:
    p = panel(domain)
    mask = scope_mask(p, step_scope)
    return p[mask]


def _yoy_series(frame: pd.DataFrame, col: str, weight: str = "ead") -> pd.Series:
    """Per period, the EAD-weighted average of (col - col_prev) over exposures seen a year earlier."""
    f = frame[frame[f"{col}_prev"].notna() & (frame["stage_prev"] < 3)]
    if f.empty:
        return pd.Series(dtype=float)
    w = f[weight].clip(lower=1e-12)
    d = f[col] - f[f"{col}_prev"]
    return (d * w).groupby(f["period"]).sum() / w.groupby(f["period"]).sum()


def _level_yoy(frame: pd.DataFrame, col: str, relative: bool) -> pd.Series:
    """Per period, the change in the EAD-weighted level over exposures performing at both dates."""
    f = frame[frame[f"{col}_prev"].notna() & (frame["stage_prev"] < 3) & (frame["stage"] < 3)]
    if f.empty:
        return pd.Series(dtype=float)
    w = f["ead"].clip(lower=1e-12)
    now = (f[col] * w).groupby(f["period"]).sum() / w.groupby(f["period"]).sum()
    wp = f["ead_prev"].clip(lower=1e-12)
    before = (f[f"{col}_prev"] * wp).groupby(f["period"]).sum() / wp.groupby(f["period"]).sum()
    return (now / before - 1) * 100 if relative else (now - before)


def _verdict(items: list[dict[str, Any]]) -> dict[str, Any]:
    worst = max((i["level"] for i in items), default=0)
    return {"label": LABELS[worst], "level": worst, "items": items,
            "note": "Measured on history; not a probability. A severe scenario is still run."}


def _fmt_period(p: str) -> str:
    return p


def assess(scenario: Scenario) -> dict[str, Any]:
    domain = scenario.domain
    items: list[dict[str, Any]] = []
    unit_word = "quarters" if domain == "corporate" else "months"
    for step in scenario.steps:
        sh = step.shocks
        f = _scope_frame(domain, scenario, step.scope)
        where = "the book" if step.scope.is_book() else ", ".join(step.scope.segments + step.scope.subsegments
                                                                   + step.scope.owners + step.scope.exposures) or "the scope"
        n_hist = f["period"].nunique()
        if sh.rating:
            s = _yoy_series(f, "grade_rank")
            n = sh.rating
            seen = s[s >= n] if n > 0 else s[s <= n]
            worst_p = (s.idxmax() if n > 0 else s.idxmin()) if len(s) else None
            ind = f[f["grade_rank_prev"].notna() & (f["stage_prev"] < 3)]
            moved = ((ind["grade_rank"] - ind["grade_rank_prev"]) >= n).mean() if n > 0 else \
                ((ind["grade_rank"] - ind["grade_rank_prev"]) <= n).mean()
            single = bool(step.scope.exposures or step.scope.owners)
            share = float(moved) if single else (len(seen) / len(s) if len(s) else 0.0)
            text = (f"A {abs(n)}-notch {'downgrade' if n > 0 else 'upgrade'} of {where}: the worst average year-on-year "
                    f"move in {len(s)} periods was {s.max() if n > 0 else s.min():+.2f} notches ({worst_p}); "
                    f"{moved * 100:.1f}% of individual exposure-years moved {abs(n)} or more notches that way.") if len(s) else \
                f"A {abs(n)}-notch move of {where}: no year-on-year history in scope."
            items.append({"shock": "rating", "text": text, "share": share,
                          "level": label_for(share, bool(len(seen)) or (single and moved > 0))})
        if sh.pd:
            s = _level_yoy(f, "pd12_book", relative=True)
            v = sh.pd["value"] if sh.pd["mode"] == "relative" else None
            if v is None:
                pp = sh.pd["value"] if sh.pd["mode"] == "pp" else sh.pd["value"] / 100
                s = _level_yoy(f, "pd12_book", relative=False) * 100
                seen = s[s >= pp] if pp > 0 else s[s <= pp]
                text = (f"12-month PD {pp:+g}pp on {where}: the largest year-on-year change in {len(s)} periods was "
                        f"{s.max():+.2f}pp ({s.idxmax()}).") if len(s) else "No PD history in scope."
            else:
                seen = s[s >= v] if v > 0 else s[s <= v]
                text = (f"PD {v:+g}% on {where}: the largest year-on-year change in the EAD-weighted 12-month PD in "
                        f"{len(s)} periods was {s.max():+.1f}% ({s.idxmax()}); {len(seen)} period(s) reached it.") if len(s) else "No PD history in scope."
            share = len(seen) / len(s) if len(s) else 0.0
            items.append({"shock": "pd", "text": text, "share": share, "level": label_for(share, bool(len(seen)))})
        if sh.lgd:
            s = _level_yoy(f, "lgd_pct_book", relative=sh.lgd["mode"] == "relative")
            v = sh.lgd["value"]
            seen = s[s >= v] if v > 0 else s[s <= v]
            unit = "%" if sh.lgd["mode"] == "relative" else "pp"
            text = (f"LGD {v:+g}{unit} on {where}: the largest year-on-year LGD change in {len(s)} periods was "
                    f"{s.max():+.2f}{unit} ({s.idxmax()}).") if len(s) else "No LGD history in scope."
            share = len(seen) / len(s) if len(s) else 0.0
            items.append({"shock": "lgd", "text": text, "share": share, "level": label_for(share, bool(len(seen)))})
        if sh.ccf or sh.ead:
            s = _level_yoy(f, "ead", relative=True) if "ead_prev" in f else pd.Series(dtype=float)
            v = sh.ead if sh.ead else (sh.ccf["value"] * 0.3 if sh.ccf["mode"] == "pp" else sh.ccf["value"] * 0.1)
            seen = s[s >= v] if v > 0 else s[s <= v]
            text = (f"An EAD increase of about {v:+.1f}% on {where}: EAD grew {s.max():+.1f}% at most year on year "
                    f"({s.idxmax()}) in {len(s)} periods.") if len(s) else "No EAD history in scope."
            share = len(seen) / len(s) if len(s) else 0.0
            items.append({"shock": "ccf", "text": text, "share": share, "level": label_for(share, bool(len(seen)))})
        if sh.sector:
            model = cycle.load(domain)
            segz = model.get("segment_z", {})
            segs = step.scope.segments or ["(book)"]
            for seg in segs:
                series = pd.Series(segz.get(seg) or model["book_z"])
                lag = 4 if domain == "corporate" else 12
                drop = (series.shift(lag) - series).dropna()
                seen = drop[drop >= sh.sector]
                share = len(seen) / len(drop) if len(drop) else 0.0
                text = (f"Sector stress of {sh.sector:g} sd on {seg}: its credit-cycle index (from observed defaults) "
                        f"fell by up to {drop.max():.2f} sd within a year ({drop.idxmax()}) in {len(drop)} periods.") \
                    if len(drop) else f"Sector stress on {seg}: too little history."
                items.append({"shock": "sector", "text": text, "share": share, "level": label_for(share, bool(len(seen)))})
        for mv in sh.stage:
            f2 = f[f["stage_prev"] == mv["from"]]
            per = f2.groupby("period").apply(lambda g: float((g["stage"] == mv["to"]).mean() * 100), include_groups=False)
            seen = per[per >= mv["share"]]
            share = len(seen) / len(per) if len(per) else 0.0
            text = (f"{mv['share']:g}% of Stage {mv['from']} to Stage {mv['to']} on {where}: the most in a year was "
                    f"{per.max():.1f}% ({per.idxmax()}).") if len(per) else "No staging history in scope."
            items.append({"shock": "stage", "text": text, "share": share, "level": label_for(share, bool(len(seen)))})
        for key, move in sh.mev.items():
            items.append(_mev_item(key, move))
    if not items:
        return {"label": "No shock", "level": 0, "items": [], "note": "The scenario has no shocks yet."}
    out = _verdict(items)
    out["history"] = f"{panel(domain)['period'].nunique()} {unit_word} of the What-If domain; MEVs annual since {mev.HISTORY_FROM}"
    return out


def _mev_item(key: str, move: float) -> dict[str, Any]:
    s = mev.BY_KEY[key]
    a = mev.annual()[key].loc[:2025].dropna()
    man = {m["key"]: m for m in mev.manifest().get("series", [])}
    src = man.get(key, {}).get("source", "")
    if s.shock_unit == "pct":
        ch = (a / a.shift(1) - 1).dropna() * 100
        unit = "%"
    elif s.shock_unit == "bps":
        ch = (a - a.shift(1)).dropna() * 100
        unit = "bps"
    else:
        ch = (a - a.shift(1)).dropna()
        unit = "pp"
    seen = ch[ch <= move] if move < 0 else ch[ch >= move]
    years = ", ".join(str(int(y)) for y in seen.index[-4:])
    share = len(seen) / len(ch) if len(ch) else 0.0
    worst = ch.min() if move < 0 else ch.max()
    worst_y = int(ch.idxmin() if move < 0 else ch.idxmax()) if len(ch) else None
    text = (f"{s.name} {move:+g}{unit}: a year-on-year move at least that large happened in {len(seen)} of {len(ch)} "
            f"years since {int(ch.index.min())}" + (f" (most recently {years})" if len(seen) else "")
            + f"; the largest was {worst:+.1f}{unit} in {worst_y}. Source: {src.split('(')[0].strip() or 'MEV store'}.")
    return {"shock": f"mev:{key}", "text": text, "share": share, "level": label_for(share, bool(len(seen))),
            "years_seen": [int(y) for y in seen.index], "years_total": int(len(ch))}
