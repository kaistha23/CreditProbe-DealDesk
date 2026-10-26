"""Every monitoring metric, per scorecard, period and segment (R16 M8). Deterministic: same domain, same rows.

The statistics are the validation engine's own (`engine._auc`, `engine._psi`, `engine.rate`, `engine.thresholds_for`)
so a monitoring line and a validation test on the same window always agree (one engine per fact, N2). The limits that
the validation engine does not carry (migration, data quality, use, cycle, findings) are the bank's policy in
`policy.json`.

Outcome metrics use only periods whose 12-month window has closed ("matured"); population metrics use every period.
"""
from __future__ import annotations

import json
import math
import pathlib
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from backend.scorecard_v5 import engine
from backend.scorecard_v5.domain import build as dbuild

HERE = pathlib.Path(__file__).resolve().parent
POLICY: dict[str, Any] = json.loads((HERE / "policy.json").read_text())
RED, AMBER, GREEN, NA = engine.RED, engine.AMBER, engine.GREEN, engine.NA


def limits(sid: str) -> dict[str, dict[str, Any]]:
    """Every limit a monitoring metric is rated against: the validation engine's thresholds plus the policy's."""
    th = engine.thresholds_for(sid)
    out = {k: dict(v) for k, v in th.items()}
    for k, v in POLICY["limits"].items():
        out[k] = dict(v)
        out[k]["text"] = engine.threshold_text(out[k]) if v["kind"] in ("low", "high") else ""
    return out


def _lag(sid: str) -> int:
    return 4 if dbuild.SCORECARDS[sid]["frequency"] == "quarterly" else 12


def _woe_iv(b: np.ndarray, y: np.ndarray, nb: int) -> float:
    good = np.bincount(b[y == 0], minlength=nb).astype(float) + 0.5
    bad = np.bincount(b[y == 1], minlength=nb).astype(float) + 0.5
    g, d = good / good.sum(), bad / bad.sum()
    return float(((g - d) * np.log(g / d)).sum())


def _binom_light(n: int, d: int, p: float) -> tuple[str, float]:
    if n == 0:
        return NA, 1.0
    pv = float(stats.binom.sf(d - 1, n, p))
    return (GREEN if pv >= 0.05 else AMBER if pv >= 0.01 else RED), pv


def _row(sid: str, criterion: str, metric: str, period: str, value: Any, status: str, lim: dict[str, Any] | None, *, segment: str = "",
         sample: str = "", n: int | None = None, defaults: int | None = None, observed: float | None = None,
         expected: float | None = None, note: str = "") -> dict[str, Any]:
    v = None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
    return {"scorecard_id": sid, "criterion": criterion, "metric": metric, "period": period, "segment": segment, "sample": sample,
            "value": v, "status": status, "n": n, "defaults": defaults, "observed": observed, "expected": expected,
            "threshold": (lim or {}).get("text", ""), "note": note}


def scorecard(sid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """(metric rows, characteristic rows, facts) for one scorecard."""
    d = engine.domain(sid)
    spec, f = d.spec, d.frame
    s = dbuild.SCORECARDS[sid]
    L = limits(sid)
    d0, d1 = s["development"]
    periods = list(spec["periods"])
    seg_col = s["segment_col"]
    unit = s["unit_key"]
    dev = f[(f.period >= d0) & (f.period <= d1)]
    dev_m = dev[dev.matured]
    matured = sorted(f.loc[f.matured, "period"].unique())
    last_mat = matured[-1]
    win_n = POLICY["outcome_window"][s["frequency"]]
    window = [p for p in matured if p > d1][-win_n:]
    win = f[f.period.isin(window) & f.matured]
    as_of = periods[-1]
    sample = {p: ("development" if p <= d1 else "monitoring" if p in matured else "open") for p in periods}
    rows: list[dict[str, Any]] = []
    R = rows.append
    wlabel = f"{window[0]}..{window[-1]}"

    # ------------------------------------------------------------ discrimination
    dd = engine._disc(dev_m)
    for p in matured:
        g = f[(f.period == p) & f.matured]
        r = engine._disc(g)
        if not r:
            continue
        R(_row(sid, "discrimination", "gini", p, r["gini"], engine.rate(r["gini"], L["gini"]), L["gini"], sample=sample[p], n=r["n"], defaults=r["defaults"]))
        R(_row(sid, "discrimination", "ks", p, r["ks"], engine.rate(r["ks"], L["ks"]), L["ks"], sample=sample[p], n=r["n"], defaults=r["defaults"]))
        if p > d1:
            rel = max((dd["gini"] - r["gini"]) / dd["gini"], 0.0)
            R(_row(sid, "discrimination", "gini_drop_rel", p, rel, engine.rate(rel, L["gini_drop_rel"]), L["gini_drop_rel"], sample=sample[p],
                   observed=r["gini"], expected=dd["gini"]))
    wd = engine._disc(win)
    R(_row(sid, "discrimination", "gini_window", window[-1], wd["gini"], engine.rate(wd["gini"], L["gini"]), L["gini"], segment="", sample="window",
           n=wd["n"], defaults=wd["defaults"], expected=dd["gini"], note=wlabel))
    for seg, g in win.groupby(seg_col, observed=True):
        r = engine._disc(g)
        if r is None:
            R(_row(sid, "discrimination", "gini_segment", window[-1], None, NA, L["gini_segment"], segment=str(seg), sample="window",
                   n=int(len(g)), defaults=int(g.y12.sum()), note=wlabel))
            continue
        st = engine.rate(r["gini"], L["gini_segment"]) if r["defaults"] >= 30 else NA
        R(_row(sid, "discrimination", "gini_segment", window[-1], r["gini"], st, L["gini_segment"], segment=str(seg), sample="window",
               n=r["n"], defaults=r["defaults"], note=wlabel))

    # ------------------------------------------------------------ calibration
    for p in matured:
        g = f[(f.period == p) & f.matured]
        n, dfl, e = len(g), int(g.y12.sum()), float(g.pd_grade.mean())
        oe = (dfl / n) / e if n and e else None
        R(_row(sid, "calibration", "oe_ratio", p, oe, engine.rate(oe, L["oe_ratio"]), L["oe_ratio"], sample=sample[p], n=n, defaults=dfl,
               observed=dfl / n if n else None, expected=e))
    reds = ambers = 0
    chi = 0.0
    grades = sorted(win.grade.unique(), key=lambda g: int(g[1:]))
    for gr in grades:
        g = win[win.grade == gr]
        n, dfl, pdg = len(g), int(g.y12.sum()), float(g.pd_grade.iloc[0])
        st, pv = _binom_light(n, dfl, pdg)
        reds += st == RED
        ambers += st == AMBER
        chi += (dfl - n * pdg) ** 2 / max(n * pdg * (1 - pdg), 1e-9)
        R(_row(sid, "calibration", "oe_grade", window[-1], (dfl / n) / pdg if n else None, st, None, segment=gr, sample="window", n=n, defaults=dfl,
               observed=dfl / n if n else None, expected=pdg, note=f"binomial p {pv:.4f}"))
    bst = RED if reds else AMBER if ambers > 1 else GREEN
    R(_row(sid, "calibration", "binomial_red", window[-1], float(reds), bst, L["binomial"], sample="window", note=f"{reds} red, {ambers} amber of {len(grades)} grades; {wlabel}"))
    hl_p = float(stats.chi2.sf(chi, len(grades)))
    R(_row(sid, "calibration", "hl_p", window[-1], hl_p, engine.rate(hl_p, L["hl"]), L["hl"], sample="window", note=f"chi-square {chi:.1f} on {len(grades)} df; {wlabel}"))
    for seg, g in win.groupby(seg_col, observed=True):
        n, dfl, e = len(g), int(g.y12.sum()), float(g.pd_grade.mean())
        st, pv = _binom_light(n, dfl, e)
        R(_row(sid, "calibration", "oe_segment", window[-1], (dfl / n) / e if n and e else None, st, None, segment=str(seg), sample="window",
               n=n, defaults=dfl, observed=dfl / n if n else None, expected=e, note=f"binomial p {pv:.4f}"))

    # ------------------------------------------------------------ stability
    cuts = np.unique(np.quantile(dev.score.to_numpy(dtype=float), np.linspace(0, 1, 11)[1:-1]))

    def sbins(fr: pd.DataFrame) -> np.ndarray:
        return np.bincount(np.searchsorted(cuts, fr.score.to_numpy(dtype=float), side="right"), minlength=len(cuts) + 1).astype(float)
    ref = sbins(dev)
    var_ref = {v["name"]: np.bincount(dev[f"bin_{v['name']}"].to_numpy(), minlength=len(v["bins"])).astype(float) for v in spec["variables"]}
    for p in periods:
        g = f[f.period == p]
        v = engine._psi(ref, sbins(g))
        R(_row(sid, "stability", "psi", p, v, engine.rate(v, L["psi"]), L["psi"], sample=sample[p], n=int(len(g))))
        if p > d1:
            cs = {k: engine._psi(r, np.bincount(g[f"bin_{k}"].to_numpy(), minlength=len(r)).astype(float)) for k, r in var_ref.items()}
            k = max(cs, key=cs.get)
            R(_row(sid, "stability", "csi_max", p, cs[k], engine.rate(cs[k], L["csi"]), L["csi"], sample=sample[p], segment=k))
    cur = f[f.period == as_of]
    for seg, g in cur.groupby(seg_col, observed=True):
        dg = dev[dev[seg_col] == seg]
        if len(dg) < 50:
            R(_row(sid, "stability", "psi_segment", as_of, None, NA, L["psi"], segment=str(seg), sample=sample[as_of], n=int(len(g)),
                   note="not in the development sample"))
            continue
        v = engine._psi(sbins(dg), sbins(g))
        R(_row(sid, "stability", "psi_segment", as_of, v, engine.rate(v, L["psi"]), L["psi"], segment=str(seg), sample=sample[as_of], n=int(len(g))))

    # ------------------------------------------------------------ overrides
    if s["has_overrides"]:
        for p in periods:
            g = f[f.period == p]
            r_ = float(g.override_flag.mean())
            R(_row(sid, "overrides", "override_rate", p, r_, engine.rate(r_, L["override_rate"]), L["override_rate"], sample=sample[p],
                   n=int(len(g)), defaults=int(g.override_flag.sum())))
        mon_m = f[(f.period > d1) & f.matured]
        up = mon_m[mon_m.override_direction == "upgrade"]
        if len(up) >= 30:
            o_, e_ = float(up.y12.mean()), float(up.pd_grade.mean())
            R(_row(sid, "overrides", "override_upgrade_oe", last_mat, o_ / e_, engine.rate(o_ / e_, L["override_upgrade"]), L["override_upgrade"],
                   sample="monitoring", n=int(len(up)), defaults=int(up.y12.sum()), observed=o_, expected=e_,
                   note=f"matured monitoring periods {mon_m.period.min()}..{mon_m.period.max()}"))
        last = f[(f.period == as_of) & (f.override_flag == 1)]
        mm = mon_m[mon_m.override_flag == 1]
        for reason, g in last.groupby("override_reason", observed=True):
            if not str(reason):
                continue
            gm = mm[mm.override_reason == reason]
            R(_row(sid, "overrides", "override_reason_share", as_of, len(g) / max(len(last), 1), NA, None, segment=str(reason), sample=sample[as_of],
                   n=int(len(g)), observed=float(gm.y12.mean()) if len(gm) else None, expected=float(gm.pd_grade.mean()) if len(gm) else None,
                   note="observed / expected: matured monitoring overrides with this reason"))

    # ------------------------------------------------------------ migration and concentration
    lag = _lag(sid)
    gnum = f.grade.str[1:].astype(int)
    f2 = f.assign(_g=gnum)
    pos = {p: i for i, p in enumerate(periods)}
    dev_share = dev.grade.value_counts(normalize=True)
    for p in periods:
        g = f2[f2.period == p]
        share = g.grade.value_counts(normalize=True)
        top = share.idxmax()
        R(_row(sid, "migration", "grade_max_share", p, float(share.max()), engine.rate(float(share.max()), L["grade_max_share"]), L["grade_max_share"],
               segment=str(top), sample=sample[p], n=int(len(g))))
        shift = (share.reindex(dev_share.index, fill_value=0) - dev_share).abs()
        R(_row(sid, "migration", "grade_share_shift", p, float(shift.max()), engine.rate(float(shift.max()), L["grade_share_shift"]), L["grade_share_shift"],
               segment=str(shift.idxmax()), sample=sample[p], n=int(len(g)),
               observed=float(share.get(shift.idxmax(), 0.0)), expected=float(dev_share.get(shift.idxmax(), 0.0))))
        i = pos[p]
        # Migration needs the same unit re-graded: the behavioural card re-scores the book monthly and the SME card re-grades
        # every borrower each quarter; the retail application card grades an account once at decision (not applicable).
        if i >= lag and (s["type"] != "application" or s["frequency"] == "quarterly"):
            q = periods[i - lag]
            a = f2.loc[f2.period == q, [unit, "_g"]].drop_duplicates(unit)
            b = g[[unit, "_g"]].drop_duplicates(unit)
            m = a.merge(b, on=unit, suffixes=("_a", "_b"))
            if len(m) >= 50:
                mv = float((np.abs(m["_g_b"] - m["_g_a"]) >= 2).mean())
                down = float(((m["_g_b"] - m["_g_a"]) >= 2).mean())
                R(_row(sid, "migration", "migration_2notch", p, mv, engine.rate(mv, L["migration_2notch"]), L["migration_2notch"], sample=sample[p],
                       n=int(len(m)), observed=down, note=f"against {q}; observed = share downgraded two or more grades"))

    # ------------------------------------------------------------ data quality
    inputs = [v["name"] for v in spec["variables"]]
    unseen_bins = {k: np.where(r == 0)[0] for k, r in var_ref.items()}
    for p in periods:
        g = f[f.period == p]
        miss = {k: float(g[k].isna().mean()) for k in inputs if k in g.columns}
        k = max(miss, key=miss.get) if miss else ""
        R(_row(sid, "data_quality", "missing_inputs", p, miss.get(k, 0.0), engine.rate(miss.get(k, 0.0), L["missing_inputs"]), L["missing_inputs"],
               segment=k, sample=sample[p], n=int(len(g))))
        un = np.zeros(len(g), dtype=bool)
        for kk, idx in unseen_bins.items():
            if len(idx):
                un |= g[f"bin_{kk}"].isin(idx).to_numpy()
        R(_row(sid, "data_quality", "unseen_bins", p, float(un.mean()) if len(g) else 0.0, engine.rate(float(un.mean()) if len(g) else 0.0, L["unseen_bins"]),
               L["unseen_bins"], sample=sample[p], n=int(len(g))))
        if p in matured:
            mo = float(g.loc[g.matured, "y12"].isna().mean())
            R(_row(sid, "data_quality", "missing_outcome", p, mo, engine.rate(mo, L["missing_outcome"]), L["missing_outcome"], sample=sample[p], n=int(g.matured.sum())))

    # ------------------------------------------------------------ use against intended scope
    approved = sorted(str(x) for x in dev[seg_col].value_counts()[lambda c: c > 0].index)
    for p in periods:
        g = f[f.period == p]
        out = ~g[seg_col].astype(str).isin(approved)
        v = float(out.mean())
        worst = g.loc[out, seg_col].astype(str).value_counts()
        R(_row(sid, "usage", "out_of_scope", p, v, engine.rate(v, L["out_of_scope"]), L["out_of_scope"], segment=str(worst.index[0]) if len(worst) else "",
               sample=sample[p], n=int(len(g)), defaults=int(out.sum())))

    # ------------------------------------------------------------ characteristics
    chars: list[dict[str, Any]] = []
    mon_m = f[(f.period > d1) & f.matured]
    for v in spec["variables"]:
        k, nb = v["name"], len(v["bins"])
        iv_d = _woe_iv(dev_m[f"bin_{k}"].to_numpy(), dev_m.y12.to_numpy(dtype=int), nb)
        iv_m = _woe_iv(mon_m[f"bin_{k}"].to_numpy(), mon_m.y12.to_numpy(dtype=int), nb)
        for p in periods:
            g = f[f.period == p]
            c = engine._psi(var_ref[k], np.bincount(g[f"bin_{k}"].to_numpy(), minlength=nb).astype(float)) if p > d1 else 0.0
            un = float(g[f"bin_{k}"].isin(unseen_bins[k]).mean()) if len(unseen_bins[k]) else 0.0
            chars.append({"scorecard_id": sid, "variable": k, "label": v["label"], "in_model": True, "period": p, "sample": sample[p],
                          "csi": c, "missing_pct": float(g[k].isna().mean()), "unseen_pct": un, "iv_dev": iv_d, "iv_mon": iv_m,
                          "status": engine.rate(c, L["csi"]) if p > d1 else NA})
    for cand in spec.get("candidates", []):
        k = cand["name"]
        if k in inputs or k not in f.columns:
            continue
        for p in periods:
            g = f[f.period == p]
            chars.append({"scorecard_id": sid, "variable": k, "label": cand.get("label", k), "in_model": False, "period": p, "sample": sample[p],
                          "csi": None, "missing_pct": float(g[k].isna().mean()), "unseen_pct": None, "iv_dev": cand.get("iv"), "iv_mon": None,
                          "status": NA})
    facts = {"scorecard_id": sid, "development": [d0, d1], "window": window, "last_matured": last_mat, "as_of": as_of, "segment_col": seg_col,
             "approved_segments": approved, "dev_gini": dd["gini"], "lag": lag, "periods": periods}
    return rows, chars, facts


def all_scorecards() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    rows, chars, facts = [], [], {}
    for sid in dbuild.SCORECARDS:
        r, c, fa = scorecard(sid)
        rows += r
        chars += c
        facts[sid] = fa
    m = pd.DataFrame(rows)
    c = pd.DataFrame(chars)
    for col in ("value", "observed", "expected"):
        m[col] = m[col].astype(float).round(6)
    for col in ("csi", "missing_pct", "unseen_pct", "iv_dev", "iv_mon"):
        c[col] = c[col].astype(float).round(6)
    m["n"] = m["n"].astype("Int64")
    m["defaults"] = m["defaults"].astype("Int64")
    return m, c, facts
