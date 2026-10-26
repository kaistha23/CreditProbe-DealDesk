"""Regime-conditioned scenarios and calibration (R14 K12 (2), (5); PLAN_R14 §m (3), (5)).

Two questions the R13 §S engine answered unconditionally:

1. **Severity conditional on the starting level** (`conditional_brent`): the distribution of Brent's 12-month moves
   that *start* from a level at or above P80 of the 35-year window (monthly EIA averages, every month a start), against
   all starts. Starts overlap, so the independent count is the number of non-overlapping 12-month windows among them.
   When it is at least `calibrate.MIN_OBS` the conditional percentiles are used; otherwise the answer says the data
   cannot support a conditional calibration and the oil leg is sized on the dated post-spike reversals instead
   (`regime.reversal_sizes`).

2. **Scenario families in the current regime** (`families`, `translate_all`): in a high-oil regime the book is stressed
   under (a) the conflict and trade disruption, i.e. the joint model's growth and rate moves at each severity with no oil
   fall (oil is high in a disruption), and (b) the oil reversal from today's level (mild half-way to the pre-shock level,
   moderate back to it, severe the median past post-spike reversal) with the joint model's growth moves at the same
   severity. Both run through the same translation as §S (`translate.run`), so the numbers are comparable.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np

from backend.scenarios import calibrate, joint, regime

SEVS = calibrate.SEVERITIES


@functools.lru_cache(maxsize=1)
def conditional_brent() -> dict[str, Any]:
    s = regime.monthly()
    w = regime.window_35y(s.index.max())
    p80 = float(np.quantile(w.to_numpy(), regime.HIGH_PCT / 100))
    fwd = (s.shift(-12) / s - 1) * 100
    starts = fwd.loc[w.index].dropna()
    falls = -starts
    high = falls[s.loc[falls.index] >= p80]

    def stats(x) -> dict[str, Any]:
        if not len(x):
            return {"n": 0}
        idx = list(x.index)
        ind, last = 0, None
        for p in idx:
            if last is None or (p - last).n >= 12:
                ind += 1
                last = p
        q = {k: float(np.quantile(x.to_numpy(), p)) for k, p in (("mild", calibrate.P_MILD), ("moderate", calibrate.P_MOD),
                                                                   ("severe", calibrate.P_SEV))}
        return {"n": int(len(x)), "n_independent": ind, "fall_pct": {k: round(v, 1) for k, v in q.items()},
                "share_falling": round(float((x > 0).mean() * 100), 1), "median_fall_pct": round(float(x.median()), 1)}

    allm, hi = stats(falls), stats(high)
    usable = hi.get("n_independent", 0) >= calibrate.MIN_OBS
    years = sorted({p.year for p in high.index})
    text = (f"Brent 12-month moves starting at or above P{regime.HIGH_PCT:.0f} (USD {p80:.0f}) of {w.index.min()}–{w.index.max()}: "
            f"{hi.get('n', 0)} monthly starts, {hi.get('n_independent', 0)} independent; P75 / P92 / P96 fall "
            + (" / ".join(f"{hi['fall_pct'][k]:.0f}%" for k in SEVS) if hi.get("n") else "n/a")
            + f" (all starts: {allm['n']} starts, " + " / ".join(f"{allm['fall_pct'][k]:.0f}%" for k in SEVS) + "). ")
    text += ("Enough independent observations: the conditional percentiles are used." if usable else
             f"{hi.get('n_independent', 0)} independent observations is fewer than {calibrate.MIN_OBS}, so the data cannot support "
             "a calibration conditional on the starting level; the oil leg is sized on the dated post-spike reversals "
             "instead (" + ", ".join(f"{h['label']} {h['fall_pct']:.0f}%" for h in regime.spike_reversals()) + ").")
    return {"driver": "brent", "threshold_usd": round(p80, 2), "window": f"{w.index.min()}–{w.index.max()}",
            "conditional": hi, "unconditional": allm, "usable": usable, "start_years": years, "text": text,
            "min_obs": calibrate.MIN_OBS, "relation": regime.RELATIONS["monthly"]}


def families(r: dict[str, Any] | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """family -> severity -> {values (adverse moves: brent % fall, gdp pp slowdown, saibor bps rise), basis}."""
    r = r or regime.current()
    j = joint.build()["joint"]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    if not regime.is_high(r):
        return out
    out["disruption"] = {}
    out["reversal"] = {}
    for sev in SEVS:
        jv = j[sev]["values"]
        out["disruption"][sev] = {"values": {"brent": 0.0, "gdp_real": jv["gdp_real"], "gdp_nonoil": jv["gdp_nonoil"],
                                             "saibor": max(0.0, jv["saibor"])},
                                  "basis": f"the joint {sev} year's growth and rate moves ({j[sev]['basis']}) with no oil fall"}
        rv = r["reversal"][sev]
        out["reversal"][sev] = {"values": {"brent": -rv["fall_pct"], "gdp_real": jv["gdp_real"], "gdp_nonoil": jv["gdp_nonoil"],
                                           "saibor": max(0.0, jv["saibor"])},
                                "basis": f"Brent USD {r['brent']['latest']['value']:.0f} → {rv['to_usd']:.0f} ({rv['basis']}) with the "
                                         f"joint {sev} year's growth moves"}
    return out


FAMILY_LABEL = {"disruption": "Conflict and trade disruption", "reversal": "Oil reversal from today's level"}


@functools.lru_cache(maxsize=1)
def translate_all() -> dict[str, Any]:
    from backend.scenarios import translate
    fam = families()
    out: dict[str, Any] = {}
    for name, by in fam.items():
        out[name] = {}
        for sev, sc in by.items():
            res = translate.run(sc["values"], sev)
            res = {k: v for k, v in res.items() if k not in ("dx", "dy_pd", "dy_migration")}
            res["basis"] = sc["basis"]
            res["sectors"] = res["sectors"][:5]
            out[name][sev] = res
    return out


def scenario_line(values: dict[str, float]) -> str:
    parts = []
    if values.get("brent"):
        parts.append(f"Oil −{values['brent']:.0f}% from today")
    else:
        parts.append("Oil stays high")
    parts.append(f"real GDP −{values['gdp_real']:.1f} pp, non-oil GDP −{values['gdp_nonoil']:.1f} pp")
    parts.append(f"SAIBOR +{values['saibor']:.0f} bps" if values.get("saibor", 0) >= 5 else "SAIBOR flat")
    return ", ".join(parts)


def reset() -> None:
    conditional_brent.cache_clear()
    translate_all.cache_clear()
