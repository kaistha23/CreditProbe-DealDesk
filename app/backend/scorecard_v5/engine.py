"""The validation engine: every number the module reports is computed here, deterministically.

Input: a plan (scorecard, development / monitoring / as-of windows, segment dimension, which test groups,
threshold overrides). Output: sections of tests (value, stated threshold, red / amber / green verdict, a
sentence), tables and Plotly figures (plain dicts, lists only, so they travel as JSON to the browser,
to Playbook and into the Word report).

Test groups and their tests (PLAN_R3, Session S2):
  discrimination  Gini and its change since development, KS, Gini by segment (AUC, KS, CAP, ROC)
  calibration     observed vs expected default rate, binomial traffic light by grade, Hosmer-Lemeshow, Brier skill
  stability       score PSI, CSI by variable, score drift, segment mix
  variables       IV, WoE monotonicity, correlation, VIF
  overrides       override rate and the outcome of upgrades (only where the data has overrides)

Outcome tests use only periods whose 12-month window has closed ("matured"). Stability tests use every
period up to the as-of, because they need no outcome.
"""
from __future__ import annotations

import json
import math
import time
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from backend.scorecard_v5 import charts as chart_style, paths
from backend.scorecard_v5.domain import binning, build

ENGINE_VERSION = "scorecard-validation-1.0.0"
GROUPS = ["discrimination", "calibration", "stability", "variables", "overrides"]
GROUP_TITLES = {"discrimination": "Discrimination", "calibration": "Calibration and accuracy", "stability": "Stability",
                "variables": "Variables", "overrides": "Overrides"}
RED, AMBER, GREEN, NA = "red", "amber", "green", "na"
PALETTE = {"navy": "#0B2A4A", "blue": "#2F80ED", "teal": "#12A594", "amber": "#E8A317", "red": "#D64545", "green": "#2E9E5B",
           "grey": "#8A94A6", "purple": "#7C5CFC", "orange": "#F2711C"}
RAG_COLOUR = {GREEN: PALETTE["green"], AMBER: PALETTE["amber"], RED: PALETTE["red"], NA: PALETTE["grey"]}
# The charts a validation shows in its thread and leads its report with (PLAN_R10 C3), in reading order:
# ROC and CAP; Gini and KS by period and by segment; observed against expected by grade; PSI by period,
# CSI by variable; override outcomes. Each is in the result only when its test group ran.
KEY_CHARTS = ["roc", "cap", "gini_trend", "ks_trend", "gini_segment", "ks_segment", "oe_grade", "psi_trend", "csi_bar", "ovr_outcome"]

# ---------------------------------------------------------------------------- thresholds (stated, per test)
# kind "high": higher is better (green at or above `green`, amber at or above `amber`); "low": lower is better;
# "band": green when inside `green` (lo, hi), amber when inside `amber` (lo, hi).
THRESHOLDS: dict[str, dict[str, Any]] = {
    "gini": {"label": "Gini on the monitoring sample", "kind": "high", "green": 0.40, "amber": 0.30, "format": "pct"},
    "gini_change": {"label": "Fall in Gini since development", "kind": "low", "green": 0.05, "amber": 0.10, "format": "pct"},
    "ks": {"label": "KS on the monitoring sample", "kind": "high", "green": 0.30, "amber": 0.20, "format": "pct"},
    "gini_segment": {"label": "Weakest segment Gini (segments with 30+ defaults)", "kind": "high", "green": 0.30, "amber": 0.20, "format": "pct"},
    "oe_ratio": {"label": "Observed to expected default rate", "kind": "band", "green": (0.85, 1.15), "amber": (0.70, 1.30), "format": "num"},
    "binomial": {"label": "Binomial traffic light by grade (grades red / amber)", "kind": "custom", "format": "text"},
    "hl": {"label": "Hosmer-Lemeshow test p-value", "kind": "high", "green": 0.05, "amber": 0.01, "format": "num4"},
    "brier": {"label": "Brier skill score against the development default rate", "kind": "high", "green": 0.02, "amber": 0.0, "format": "num4"},
    "psi": {"label": "Score PSI at the as-of period", "kind": "low", "green": 0.10, "amber": 0.25, "format": "num4"},
    "csi": {"label": "Largest variable CSI at the as-of period", "kind": "low", "green": 0.10, "amber": 0.25, "format": "num4"},
    "drift": {"label": "Mean score drift at the as-of period (development standard deviations)", "kind": "low", "green": 0.25, "amber": 0.50, "format": "num"},
    "mix": {"label": "Segment mix PSI at the as-of period", "kind": "low", "green": 0.10, "amber": 0.25, "format": "num4"},
    "iv": {"label": "Model variables with monitoring IV below 0.02", "kind": "low", "green": 0, "amber": 1, "format": "int"},
    "monotone": {"label": "Numeric variables whose WoE is no longer monotone", "kind": "low", "green": 0, "amber": 1, "format": "int"},
    "corr": {"label": "Largest absolute correlation between WoE variables", "kind": "low", "green": 0.50, "amber": 0.70, "format": "num"},
    "vif": {"label": "Largest variance inflation factor", "kind": "low", "green": 5.0, "amber": 10.0, "format": "num"},
    "override_rate": {"label": "Override rate on the monitoring sample", "kind": "low", "green": 0.05, "amber": 0.10, "format": "pct"},
    "override_upgrade": {"label": "Upgrade overrides: observed to expected default rate", "kind": "low", "green": 1.5, "amber": 2.5, "format": "num"},
}
PER_CARD = {"RET-BEH": {"gini": {"green": 0.45, "amber": 0.35}}, "SME-ANN": {"gini": {"green": 0.50, "amber": 0.40}}}


def threshold_text(t: dict[str, Any]) -> str:
    f = lambda v: f"{v * 100:g}%" if t["format"] == "pct" else f"{v:g}"  # noqa: E731
    if t["kind"] == "high":
        return f"green ≥ {f(t['green'])}, amber ≥ {f(t['amber'])}, red below"
    if t["kind"] == "low":
        return f"green ≤ {f(t['green'])}, amber ≤ {f(t['amber'])}, red above"
    if t["kind"] == "band":
        return f"green {t['green'][0]:g} to {t['green'][1]:g}, amber {t['amber'][0]:g} to {t['amber'][1]:g}, red outside"
    return "green: no grade red and at most one amber; amber: no grade red; red: any grade red (p < 0.01 under-prediction)"


def thresholds_for(sid: str, overrides: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    out = {k: dict(v) for k, v in THRESHOLDS.items()}
    for k, v in PER_CARD.get(sid, {}).items():
        out[k].update(v)
    for k, v in (overrides or {}).items():
        if k in out and isinstance(v, dict):
            out[k].update({kk: vv for kk, vv in v.items() if kk in ("green", "amber")})
    for t in out.values():
        t["text"] = threshold_text(t)
    return out


def rate(value: float | None, t: dict[str, Any]) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NA
    k = t["kind"]
    if k == "high":
        return GREEN if value >= t["green"] else AMBER if value >= t["amber"] else RED
    if k == "low":
        return GREEN if value <= t["green"] else AMBER if value <= t["amber"] else RED
    if k == "band":
        g, a = t["green"], t["amber"]
        return GREEN if g[0] <= value <= g[1] else AMBER if a[0] <= value <= a[1] else RED
    return NA


# ---------------------------------------------------------------------------- the domain


class Domain:
    def __init__(self, sid: str):
        self.sid = sid
        self.spec = json.loads((paths.DOMAIN / f"{sid}.spec.json").read_text())
        for v in self.spec["variables"]:
            binning.edges_ok(v)
        self.frame = pd.read_parquet(paths.DOMAIN / f"{sid}.parquet")
        for c in ("grade", "sample", "override_direction", "override_reason", "override_level"):
            self.frame[c] = self.frame[c].astype(str)
        self.owner_key = self.spec["owner_key"]
        self.unit_key = self.spec["unit_key"]


@lru_cache(maxsize=4)
def domain(sid: str) -> Domain:
    return Domain(sid)


def scorecards() -> list[dict[str, Any]]:
    out = []
    for sid, s in build.SCORECARDS.items():
        sp = domain(sid).spec
        out.append({"scorecard_id": sid, "name": s["name"], "version": s["version"], "type": s["type"], "segment": s["segment"],
                    "book": s["book"], "frequency": s["frequency"], "description": s["description"], "rows": sp["rows"],
                    "periods": [sp["periods"][0], sp["periods"][-1]], "development": list(s["development"]),
                    "monitoring": list(s["monitoring"]), "last_matured": sp["last_matured"], "as_of": sp["periods"][-1],
                    "variables": [{"name": v["name"], "label": v["label"], "iv": round(v["iv"], 4)} for v in sp["variables"]],
                    "has_overrides": bool(s["has_overrides"]), "owner_key": s["owner_key"], "unit_key": s["unit_key"],
                    "segment_options": segment_options(sid)})
    return out


def segment_options(sid: str) -> list[str]:
    d = domain(sid)
    cats = [n for n, _, k in build.CANDIDATES[sid] if k == "categorical" and n in d.frame.columns and n != "delinquency_bucket"]
    first = build.SCORECARDS[sid]["segment_col"]
    return [first] + [c for c in cats if c != first]


def default_plan(sid: str) -> dict[str, Any]:
    s = build.SCORECARDS[sid]
    sp = domain(sid).spec
    return {"scorecard_id": sid, "development": list(s["development"]), "monitoring": list(s["monitoring"]),
            "as_of": sp["periods"][-1], "segment_by": s["segment_col"], "tests": {g: (g != "overrides" or bool(s["has_overrides"])) for g in GROUPS},
            "thresholds": {}, "notes": []}


# ---------------------------------------------------------------------------- statistics


def _auc(y: np.ndarray, score: np.ndarray) -> float:
    """AUC of the risk ordering (a low score is risky) by rank."""
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = stats.rankdata(-score)             # a higher rank = a higher risk
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _ks_and_curves(y: np.ndarray, score: np.ndarray, points: int = 120) -> dict[str, Any]:
    order = np.argsort(score, kind="stable")                      # riskiest (lowest score) first
    ys = y[order]
    n1, n0 = ys.sum(), len(ys) - ys.sum()
    cb = np.cumsum(ys) / max(n1, 1)
    cg = np.cumsum(1 - ys) / max(n0, 1)
    cp = np.arange(1, len(ys) + 1) / len(ys)
    ks = float(np.max(np.abs(cb - cg)))
    pick = np.unique(np.linspace(0, len(ys) - 1, points).astype(int))
    return {"ks": ks, "ks_score": float(score[order][int(np.argmax(np.abs(cb - cg)))]),
            "fpr": cg[pick].round(5).tolist(), "tpr": cb[pick].round(5).tolist(), "pop": cp[pick].round(5).tolist(),
            "score": score[order][pick].round(1).tolist()}


def _disc(frame: pd.DataFrame) -> dict[str, Any] | None:
    y = frame["y12"].to_numpy(dtype=float)
    if len(y) < 50 or y.sum() < 5 or y.sum() == len(y):
        return None
    s = frame["score"].to_numpy(dtype=float)
    auc = _auc(y, s)
    n1, n0 = y.sum(), len(y) - y.sum()
    q1, q2 = auc / (2 - auc), 2 * auc * auc / (1 + auc)
    se = math.sqrt(max((auc * (1 - auc) + (n1 - 1) * (q1 - auc * auc) + (n0 - 1) * (q2 - auc * auc)) / (n1 * n0), 0))
    out = {"n": int(len(y)), "defaults": int(n1), "auc": auc, "gini": 2 * auc - 1, "auc_ci": (auc - 1.96 * se, auc + 1.96 * se)}
    out.update(_ks_and_curves(y, s))
    return out


def _wilson(d: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = d / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(c - h, 0.0), min(c + h, 1.0))


def _psi(ref: np.ndarray, cur: np.ndarray) -> float:
    r = np.maximum(ref / max(ref.sum(), 1), 1e-4)
    c = np.maximum(cur / max(cur.sum(), 1), 1e-4)
    return float(((c - r) * np.log(c / r)).sum())


def _fig(data: list[dict[str, Any]], title: str, xt: str = "", yt: str = "", **layout: Any) -> dict[str, Any]:
    lay = {"title": {"text": title, "x": 0.01, "font": {"size": 14}}, "margin": {"l": 64, "r": 24, "t": 48, "b": 84},
           "xaxis": {"title": {"text": xt}, "automargin": True}, "yaxis": {"title": {"text": yt}, "automargin": True, "zeroline": False},
           "legend": {"orientation": "h", "y": -0.34}, "hovermode": "closest", "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)"}
    lay.update(layout)
    return {"data": data, "layout": lay}


def _line(name: str, x: list, y: list, colour: str, **kw: Any) -> dict[str, Any]:
    return {"type": "scatter", "mode": kw.pop("mode", "lines"), "name": name, "x": x, "y": y, "line": {"color": colour, "width": 2.5}, **kw}


def _hline(y: float, colour: str, name: str, x0: Any = 0, x1: Any = 1) -> dict[str, Any]:
    return {"type": "scatter", "mode": "lines", "name": name, "x": [x0, x1], "y": [y, y], "line": {"color": colour, "width": 1.5, "dash": "dash"},
            "hoverinfo": "skip"}


def _item(tid: str, group: str, value: Any, status: str, th: dict[str, Any], comment: str, label: str | None = None, fmt: str | None = None) -> dict[str, Any]:
    return {"id": tid, "group": group, "label": label or th["label"], "value": None if value is None else (round(float(value), 6) if isinstance(value, (int, float, np.floating)) else value),
            "format": fmt or th["format"], "threshold": th.get("text", ""), "status": status, "comment": comment}


# ---------------------------------------------------------------------------- the run


def run(plan: dict[str, Any], progress=None) -> dict[str, Any]:
    t0 = time.time()
    sid = plan["scorecard_id"]
    d = domain(sid)
    spec = d.spec
    base = default_plan(sid)
    plan = {**base, **{k: v for k, v in plan.items() if v is not None}}
    plan["tests"] = {**base["tests"], **(plan.get("tests") or {})}
    th = thresholds_for(sid, plan.get("thresholds"))
    f = d.frame
    d0, d1 = plan["development"]
    m0, m1 = plan["monitoring"]
    as_of = plan["as_of"]
    seg_col = plan["segment_by"] if plan["segment_by"] in f.columns else build.SCORECARDS[sid]["segment_col"]
    dev = f[(f.period >= d0) & (f.period <= d1)]
    mon = f[(f.period >= m0) & (f.period <= m1) & f.matured]
    cur = f[f.period == as_of]
    if len(mon) == 0 or len(dev) == 0:
        raise ValueError("The monitoring or development window holds no observations with a closed 12-month outcome.")
    dev_m = dev[dev.matured]
    last_mat = mon.period.max()
    sections: list[dict[str, Any]] = []
    tests_run: list[dict[str, Any]] = []

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    info = {"development": {"from": d0, "to": d1, "n": int(len(dev_m)), "defaults": int(dev_m.y12.sum())},
            "monitoring": {"from": m0, "to": m1, "n": int(len(mon)), "defaults": int(mon.y12.sum())},
            "as_of": {"period": as_of, "n": int(len(cur))}, "last_matured": last_mat, "segment_by": seg_col,
            "open_periods": [p for p in spec["periods"] if p > last_mat]}
    # -------------------------------------------------------------------- discrimination
    if plan["tests"].get("discrimination"):
        say("Testing discrimination")
        t, tables, charts = [], [], []
        dm, dd = _disc(mon), _disc(dev_m)
        assert dm and dd, "not enough defaults to measure discrimination"
        st = rate(dm["gini"], th["gini"])
        t.append(_item("gini", "discrimination", dm["gini"], st, th["gini"],
                       f"Gini {dm['gini']:.1%} (AUC {dm['auc']:.3f}, 95% interval {dm['auc_ci'][0]:.3f} to {dm['auc_ci'][1]:.3f}) on {dm['n']:,} "
                       f"observations and {dm['defaults']:,} defaults; development {dd['gini']:.1%}."))
        drop = dd["gini"] - dm["gini"]
        t.append(_item("gini_change", "discrimination", max(drop, 0.0), rate(max(drop, 0.0), th["gini_change"]), th["gini_change"],
                       f"Gini moved from {dd['gini']:.1%} in development to {dm['gini']:.1%} in monitoring ({-drop * 100:+.1f} points)."))
        t.append(_item("ks", "discrimination", dm["ks"], rate(dm["ks"], th["ks"]), th["ks"],
                       f"KS {dm['ks']:.1%} at a score of {dm['ks_score']:.0f}; development {dd['ks']:.1%}."))
        # by segment
        rows, worst = [], None
        for seg, g in mon.groupby(seg_col):
            r = _disc(g)
            if r is None:
                rows.append({"segment": str(seg), "n": int(len(g)), "defaults": int(g.y12.sum()), "auc": None, "gini": None, "ks": None, "status": NA})
                continue
            ok = r["defaults"] >= 30
            stt = rate(r["gini"], th["gini_segment"]) if ok else NA
            if ok and (worst is None or r["gini"] < worst[1]):
                worst = (str(seg), r["gini"])
            rows.append({"segment": str(seg), "n": r["n"], "defaults": r["defaults"], "auc": r["auc"], "gini": r["gini"], "ks": r["ks"], "status": stt})
        rows.sort(key=lambda r: -r["n"])
        if worst:
            t.append(_item("gini_segment", "discrimination", worst[1], rate(worst[1], th["gini_segment"]), th["gini_segment"],
                           f"The weakest segment is {worst[0]} with a Gini of {worst[1]:.1%}."))
        tables.append({"id": "disc_segment", "title": f"Discrimination by {seg_col.replace('_', ' ')} (monitoring sample)",
                       "columns": [{"key": "segment", "label": seg_col.replace("_", " ").title(), "format": "text"}, {"key": "n", "label": "Observations", "format": "int"},
                                   {"key": "defaults", "label": "Defaults", "format": "int"}, {"key": "auc", "label": "AUC", "format": "num4"},
                                   {"key": "gini", "label": "Gini", "format": "pct"}, {"key": "ks", "label": "KS", "format": "pct"},
                                   {"key": "status", "label": "Verdict", "format": "rag"}], "rows": rows,
                       "note": "Segments with fewer than 30 defaults are shown without a verdict."})
        # per period
        per = []
        for p, g in f[(f.period >= d0) & f.matured & (f.period <= last_mat)].groupby("period"):
            r = _disc(g)
            if r:
                per.append({"period": p, "gini": r["gini"], "ks": r["ks"], "n": r["n"], "sample": "development" if p <= d1 else "monitoring"})
        tables.append({"id": "disc_period", "title": "Gini and KS by period",
                       "columns": [{"key": "period", "label": "Period", "format": "text"}, {"key": "sample", "label": "Sample", "format": "text"},
                                   {"key": "n", "label": "Observations", "format": "int"}, {"key": "gini", "label": "Gini", "format": "pct"},
                                   {"key": "ks", "label": "KS", "format": "pct"}],
                       "rows": per, "note": "Only periods whose 12-month window has closed."})
        gl = th["gini"]
        charts.append({"id": "roc", "title": "ROC curve", "figure": _fig([
            _line("Development", dd["fpr"], dd["tpr"], PALETTE["grey"]), _line("Monitoring", dm["fpr"], dm["tpr"], PALETTE["blue"]),
            {"type": "scatter", "mode": "lines", "name": "No skill", "x": [0, 1], "y": [0, 1], "line": {"color": PALETTE["grey"], "dash": "dot", "width": 1}}],
            "ROC curve", "False positive rate (cumulative goods)", "True positive rate (cumulative defaults)"),
            "note": f"AUC {dm['auc']:.3f} on monitoring, {dd['auc']:.3f} in development."})
        charts.append({"id": "cap", "title": "CAP curve", "figure": _fig([
            _line("Development", dd["pop"], dd["tpr"], PALETTE["grey"]), _line("Monitoring", dm["pop"], dm["tpr"], PALETTE["teal"]),
            _line("Perfect model", [0, dm["defaults"] / dm["n"], 1], [0, 1, 1], PALETTE["navy"], line={"color": PALETTE["navy"], "dash": "dot", "width": 1}),
            {"type": "scatter", "mode": "lines", "name": "Random", "x": [0, 1], "y": [0, 1], "line": {"color": PALETTE["grey"], "dash": "dot", "width": 1}}],
            "Cumulative accuracy profile", "Share of observations (riskiest first)", "Share of defaults captured"),
            "note": "Riskiest observations first; the further above the diagonal, the better the ranking."})
        charts.append({"id": "ks", "title": "KS: cumulative goods and bads by score", "figure": _fig([
            _line("Defaults", dm["score"], dm["tpr"], PALETTE["red"]), _line("Non-defaults", dm["score"], dm["fpr"], PALETTE["green"])],
            "KS separation (monitoring)", "Score", "Cumulative share"), "note": f"The largest gap is {dm['ks']:.1%}."})
        charts.append({"id": "gini_trend", "title": "Gini by period", "figure": _fig([
            {"type": "bar", "name": "Gini", "x": [r["period"] for r in per], "y": [round(r["gini"], 4) for r in per],
             "marker": {"color": [PALETTE["grey"] if r["sample"] == "development" else RAG_COLOUR[rate(r["gini"], th["gini"])] for r in per]},
             "hovertemplate": "%{x}: %{y:.1%}<extra></extra>"},
            _hline(gl["green"], PALETTE["green"], "Green threshold", per[0]["period"], per[-1]["period"]),
            _hline(gl["amber"], PALETTE["amber"], "Amber threshold", per[0]["period"], per[-1]["period"])],
            "Gini by period (grey: development)", "", "Gini", yaxis={"tickformat": ".0%", "title": {"text": "Gini"}}), "note": ""})
        kl = th["ks"]
        charts.append({"id": "ks_trend", "title": "KS by period", "figure": _fig([
            {"type": "bar", "name": "KS", "x": [r["period"] for r in per], "y": [round(r["ks"], 4) for r in per],
             "marker": {"color": [PALETTE["grey"] if r["sample"] == "development" else RAG_COLOUR[rate(r["ks"], kl)] for r in per]},
             "hovertemplate": "%{x}: KS %{y:.1%}<extra></extra>"},
            _hline(kl["green"], PALETTE["green"], "Green threshold", per[0]["period"], per[-1]["period"]),
            _hline(kl["amber"], PALETTE["amber"], "Amber threshold", per[0]["period"], per[-1]["period"])],
            "KS by period", "", "KS", yaxis={"tickformat": ".0%", "title": {"text": "KS"}}), "note": ""})
        sr = [r for r in rows if r["gini"] is not None]
        charts.append({"id": "gini_segment", "title": f"Gini by {seg_col.replace('_', ' ')}", "figure": _fig([
            {"type": "bar", "orientation": "h", "name": "Gini", "y": [r["segment"] for r in sr][::-1], "x": [round(r["gini"], 4) for r in sr][::-1],
             "marker": {"color": [RAG_COLOUR[r["status"]] if r["status"] != NA else PALETTE["grey"] for r in sr][::-1]},
             "hovertemplate": "%{y}: %{x:.1%}<extra></extra>"}], "Gini by segment (monitoring)", "Gini", "", xaxis={"tickformat": ".0%"}), "note": ""})
        charts.append({"id": "ks_segment", "title": f"KS by {seg_col.replace('_', ' ')}", "figure": _fig([
            {"type": "bar", "orientation": "h", "name": "KS", "y": [r["segment"] for r in sr][::-1], "x": [round(r["ks"], 4) for r in sr][::-1],
             "marker": {"color": [PALETTE["blue"] if r["status"] != NA else PALETTE["grey"] for r in sr][::-1]},
             "hovertemplate": "%{y}: KS %{x:.1%}<extra></extra>"}], "KS by segment (monitoring)", "KS", "", xaxis={"tickformat": ".0%"}), "note": ""})
        sections.append({"id": "discrimination", "title": GROUP_TITLES["discrimination"], "tests": t, "tables": tables, "charts": charts})
        tests_run += t
    # -------------------------------------------------------------------- calibration
    if plan["tests"].get("calibration"):
        say("Testing calibration and accuracy")
        t, tables, charts = [], [], []
        exp_all = float(mon.pd_grade.mean())
        obs_all = float(mon.y12.mean())
        oe = obs_all / exp_all
        t.append(_item("oe_ratio", "calibration", oe, rate(oe, th["oe_ratio"]), th["oe_ratio"],
                       f"Observed default rate {obs_all:.2%} against {exp_all:.2%} expected from the grade PDs ({oe:.2f} times)."))
        grades = sorted(mon.grade.unique(), key=lambda g: int(g[1:]))
        rows, reds, ambers, chi = [], 0, 0, 0.0
        for g in grades:
            gg = mon[mon.grade == g]
            n, dfl, pdg = len(gg), int(gg.y12.sum()), float(gg.pd_grade.iloc[0])
            p = float(stats.binom.sf(dfl - 1, n, pdg)) if n else 1.0
            stt = GREEN if p >= 0.05 else AMBER if p >= 0.01 else RED
            reds += stt == RED
            ambers += stt == AMBER
            lo, hi = _wilson(dfl, n)
            chi += (dfl - n * pdg) ** 2 / max(n * pdg * (1 - pdg), 1e-9)
            rows.append({"grade": g, "n": n, "defaults": dfl, "odr": dfl / n if n else 0.0, "pd": pdg, "ratio": (dfl / n) / pdg if n else None,
                         "ci_low": lo, "ci_high": hi, "p_value": p, "status": stt})
        bt = th["binomial"]
        bst = RED if reds else AMBER if ambers > 1 else GREEN
        t.append(_item("binomial", "calibration", f"{reds} red, {ambers} amber of {len(grades)}", bst, bt,
                       f"{reds} grade(s) are red (the grade PD is too low at the 1% level) and {ambers} amber (at the 5% level). "
                       + ("; ".join(f"{r['grade']} {r['odr']:.2%} against {r['pd']:.2%}" for r in rows if r["status"] == RED) or "No grade is red.")))
        df_hl = len(grades)
        hl_p = float(stats.chi2.sf(chi, df_hl))
        t.append(_item("hl", "calibration", hl_p, rate(hl_p, th["hl"]), th["hl"], f"Hosmer-Lemeshow chi-square {chi:.1f} on {df_hl} degrees of freedom (out-of-sample, grade PDs fixed)."))
        yv, pv = mon.y12.to_numpy(dtype=float), mon.pd_grade.to_numpy(dtype=float)
        brier = float(np.mean((pv - yv) ** 2))
        ref = float(np.mean((dev_m.y12.mean() - yv) ** 2))
        bss = 1 - brier / ref
        t.append(_item("brier", "calibration", bss, rate(bss, th["brier"]), th["brier"],
                       f"Brier score {brier:.5f} against {ref:.5f} for a constant development default rate of {dev_m.y12.mean():.2%}."))
        tables.append({"id": "cal_grade", "title": "Observed vs expected default rate by grade (monitoring sample)",
                       "columns": [{"key": "grade", "label": "Grade", "format": "text"}, {"key": "n", "label": "Observations", "format": "int"},
                                   {"key": "defaults", "label": "Defaults", "format": "int"}, {"key": "odr", "label": "Observed", "format": "pct2"},
                                   {"key": "pd", "label": "Expected PD", "format": "pct2"}, {"key": "ratio", "label": "O / E", "format": "num"},
                                   {"key": "p_value", "label": "Binomial p", "format": "num4"}, {"key": "status", "label": "Light", "format": "rag"}],
                       "rows": rows, "note": "Expected PD is the development default rate of the grade. p is the one-sided binomial probability of at least the observed defaults."})
        pr = []
        for p, g in f[(f.period >= d0) & f.matured & (f.period <= last_mat)].groupby("period"):
            n, dfl, e = len(g), int(g.y12.sum()), float(g.pd_grade.mean())
            pv_ = float(stats.binom.sf(dfl - 1, n, e))
            pr.append({"period": p, "sample": "development" if p <= d1 else "monitoring", "n": n, "defaults": dfl, "odr": dfl / n, "pd": e,
                       "status": GREEN if pv_ >= 0.05 else AMBER if pv_ >= 0.01 else RED})
        tables.append({"id": "cal_period", "title": "Observed vs expected default rate by period",
                       "columns": [{"key": "period", "label": "Period", "format": "text"}, {"key": "sample", "label": "Sample", "format": "text"},
                                   {"key": "n", "label": "Observations", "format": "int"}, {"key": "defaults", "label": "Defaults", "format": "int"},
                                   {"key": "odr", "label": "Observed", "format": "pct2"}, {"key": "pd", "label": "Expected", "format": "pct2"},
                                   {"key": "status", "label": "Light", "format": "rag"}], "rows": pr, "note": "Light: binomial test of the period as a whole."})
        charts.append({"id": "oe_grade", "title": "Observed vs expected by grade", "figure": _fig([
            {"type": "bar", "name": "Expected PD", "x": [r["grade"] for r in rows], "y": [r["pd"] for r in rows], "marker": {"color": PALETTE["grey"]},
             "hovertemplate": "%{x} expected: %{y:.2%}<extra></extra>"},
            {"type": "scatter", "mode": "markers", "name": "Observed (95% interval)", "x": [r["grade"] for r in rows], "y": [r["odr"] for r in rows],
             "marker": {"color": [RAG_COLOUR[r["status"]] for r in rows], "size": 11, "line": {"color": PALETTE["navy"], "width": 1}},
             "error_y": {"type": "data", "symmetric": False, "array": [r["ci_high"] - r["odr"] for r in rows], "arrayminus": [r["odr"] - r["ci_low"] for r in rows],
                         "color": PALETTE["navy"]}, "hovertemplate": "%{x} observed: %{y:.2%}<extra></extra>"}],
            "Observed vs expected default rate by grade", "Grade (G1 safest)", "Default rate", yaxis={"tickformat": ".1%", "title": {"text": "Default rate"}}), "note": "Marker colour is the binomial traffic light."})
        charts.append({"id": "oe_trend", "title": "Observed vs expected over time", "figure": _fig([
            _line("Expected", [r["period"] for r in pr], [r["pd"] for r in pr], PALETTE["grey"], mode="lines+markers"),
            _line("Observed", [r["period"] for r in pr], [r["odr"] for r in pr], PALETTE["red"], mode="lines+markers",
                  marker={"color": [RAG_COLOUR[r["status"]] for r in pr], "size": 9})],
            "Observed vs expected default rate by period", "", "Default rate", yaxis={"tickformat": ".1%", "title": {"text": "Default rate"}}), "note": ""})
        sections.append({"id": "calibration", "title": GROUP_TITLES["calibration"], "tests": t, "tables": tables, "charts": charts})
        tests_run += t
    # -------------------------------------------------------------------- stability
    if plan["tests"].get("stability"):
        say("Testing stability")
        t, tables, charts = [], [], []
        cuts = np.unique(np.quantile(dev.score.to_numpy(dtype=float), np.linspace(0, 1, 11)[1:-1]))
        def score_bins(frame: pd.DataFrame) -> np.ndarray:
            return np.bincount(np.searchsorted(cuts, frame.score.to_numpy(dtype=float), side="right"), minlength=len(cuts) + 1).astype(float)
        ref = score_bins(dev)
        periods = [p for p in spec["periods"] if p >= d0 and p <= as_of]
        psi_rows, drift_rows = [], []
        dmean, dstd = float(dev.score.mean()), float(dev.score.std())
        for p in periods:
            g = f[f.period == p]
            v = _psi(ref, score_bins(g))
            zdrift = (float(g.score.mean()) - dmean) / dstd
            sample = "development" if p <= d1 else ("monitoring" if p <= m1 else "open")
            psi_rows.append({"period": p, "sample": sample, "n": int(len(g)), "psi": v, "status": rate(v, th["psi"])})
            drift_rows.append({"period": p, "mean_score": float(g.score.mean()), "drift": zdrift})
        cur_psi = next(r for r in psi_rows if r["period"] == as_of)
        t.append(_item("psi", "stability", cur_psi["psi"], cur_psi["status"], th["psi"],
                       f"Score PSI {cur_psi['psi']:.3f} at {as_of} against the development score distribution; the largest in the window is {max(r['psi'] for r in psi_rows):.3f}."))
        cur_drift = next(r for r in drift_rows if r["period"] == as_of)["drift"]
        t.append(_item("drift", "stability", abs(cur_drift), rate(abs(cur_drift), th["drift"]), th["drift"],
                       f"The mean score is {cur_drift:+.2f} development standard deviations from development at {as_of}."))
        # CSI by variable (using the stored bin indices)
        var_rows, heat = [], []
        for v in spec["variables"]:
            col = f"bin_{v['name']}"
            nb = len(v["bins"])
            rdist = np.bincount(dev[col].to_numpy(), minlength=nb).astype(float)
            per_p = []
            for p in periods:
                if p <= d1:
                    per_p.append(0.0)
                    continue
                per_p.append(_psi(rdist, np.bincount(f.loc[f.period == p, col].to_numpy(), minlength=nb).astype(float)))
            heat.append(per_p)
            cdist = np.bincount(cur[col].to_numpy(), minlength=nb).astype(float)
            c = _psi(rdist, cdist)
            r_, c_ = np.maximum(rdist / rdist.sum(), 1e-4), np.maximum(cdist / cdist.sum(), 1e-4)
            contrib = (c_ - r_) * np.log(c_ / r_)
            k = int(np.argmax(contrib))
            var_rows.append({"variable": v["label"], "name": v["name"], "csi": c, "status": rate(c, th["csi"]),
                             "largest_shift": f"{v['bins'][k]['label']}: {r_[k]:.1%} → {c_[k]:.1%}"})
        mx = max(var_rows, key=lambda r: r["csi"])
        t.append(_item("csi", "stability", mx["csi"], mx["status"], th["csi"], f"{mx['variable']} has the largest CSI ({mx['csi']:.3f}); its biggest shift is {mx['largest_shift']}."))
        # segment mix
        mix_ref = dev[seg_col].value_counts()
        mix_cur = cur[seg_col].value_counts()
        cats = sorted(set(mix_ref.index) | set(mix_cur.index))
        ra = np.array([mix_ref.get(c, 0) for c in cats], dtype=float)
        ca = np.array([mix_cur.get(c, 0) for c in cats], dtype=float)
        mix_v = _psi(ra, ca)
        rr_, cc_ = np.maximum(ra / ra.sum(), 1e-4), np.maximum(ca / ca.sum(), 1e-4)
        kk = int(np.argmax(np.abs((cc_ - rr_) * np.log(cc_ / rr_))))
        t.append(_item("mix", "stability", mix_v, rate(mix_v, th["mix"]), th["mix"],
                       f"Mix by {seg_col.replace('_', ' ')} moved with a PSI of {mix_v:.3f} between development and {as_of}; "
                       f"the largest shift is {cats[kk]} from {rr_[kk]:.1%} to {cc_[kk]:.1%} of observations."))
        tables.append({"id": "psi_period", "title": "Score PSI and drift by period",
                       "columns": [{"key": "period", "label": "Period", "format": "text"}, {"key": "sample", "label": "Sample", "format": "text"},
                                   {"key": "n", "label": "Observations", "format": "int"}, {"key": "psi", "label": "PSI", "format": "num4"},
                                   {"key": "mean_score", "label": "Mean score", "format": "num"}, {"key": "drift", "label": "Drift (SD)", "format": "num"},
                                   {"key": "status", "label": "Verdict", "format": "rag"}],
                       "rows": [{**a, **{k: v for k, v in b.items() if k != "period"}} for a, b in zip(psi_rows, drift_rows)],
                       "note": "Development periods are the reference, so their PSI is the in-sample baseline."})
        tables.append({"id": "csi_var", "title": f"CSI by variable at {as_of}",
                       "columns": [{"key": "variable", "label": "Variable", "format": "text"}, {"key": "csi", "label": "CSI", "format": "num4"},
                                   {"key": "largest_shift", "label": "Largest shift", "format": "text"}, {"key": "status", "label": "Verdict", "format": "rag"}],
                       "rows": sorted(var_rows, key=lambda r: -r["csi"]), "note": "Characteristic stability index against the development distribution."})
        charts.append({"id": "psi_trend", "title": "Score PSI by period", "figure": _fig([
            {"type": "bar", "name": "PSI", "x": [r["period"] for r in psi_rows], "y": [round(r["psi"], 5) for r in psi_rows],
             "marker": {"color": [PALETTE["grey"] if r["sample"] == "development" else RAG_COLOUR[r["status"]] for r in psi_rows]},
             "hovertemplate": "%{x}: PSI %{y:.3f}<extra></extra>"},
            _hline(th["psi"]["green"], PALETTE["green"], "0.10", psi_rows[0]["period"], psi_rows[-1]["period"]),
            _hline(th["psi"]["amber"], PALETTE["red"], "0.25", psi_rows[0]["period"], psi_rows[-1]["period"])],
            "Score PSI against development", "", "PSI"), "note": "Open periods have no closed outcome window but are monitored for stability."})
        edges_lbl = [f"<{cuts[0]:.0f}"] + [f"{cuts[i]:.0f}–{cuts[i + 1]:.0f}" for i in range(len(cuts) - 1)] + [f"≥{cuts[-1]:.0f}"]
        cs = score_bins(cur)
        charts.append({"id": "score_dist", "title": "Score distribution", "figure": _fig([
            {"type": "bar", "name": "Development", "x": edges_lbl, "y": (ref / ref.sum()).round(4).tolist(), "marker": {"color": PALETTE["grey"]}},
            {"type": "bar", "name": as_of, "x": edges_lbl, "y": (cs / cs.sum()).round(4).tolist(), "marker": {"color": PALETTE["blue"]}}],
            "Score distribution: development vs " + as_of, "Score band (development deciles)", "Share of observations",
            barmode="group", yaxis={"tickformat": ".0%", "title": {"text": "Share of observations"}}), "note": ""})
        charts.append({"id": "csi_bar", "title": "CSI by variable", "figure": _fig([
            {"type": "bar", "orientation": "h", "name": "CSI", "y": [r["variable"] for r in sorted(var_rows, key=lambda r: r["csi"])],
             "x": [round(r["csi"], 5) for r in sorted(var_rows, key=lambda r: r["csi"])],
             "marker": {"color": [RAG_COLOUR[r["status"]] for r in sorted(var_rows, key=lambda r: r["csi"])]},
             "hovertemplate": "%{y}: CSI %{x:.3f}<extra></extra>"}], f"CSI by variable at {as_of}", "CSI", ""), "note": ""})
        charts.append({"id": "csi_heat", "title": "CSI by variable over time", "figure": _fig([
            {"type": "heatmap", "x": periods, "y": [r["variable"] for r in var_rows], "z": [[round(v, 4) for v in row] for row in heat],
             "colorscale": [[0, "#EAF4EC"], [0.2, "#F7E3A1"], [0.5, "#F2A65A"], [1, "#D64545"]], "zmin": 0, "zmax": 0.4,
             "hovertemplate": "%{y}<br>%{x}: CSI %{z:.3f}<extra></extra>", "colorbar": {"title": {"text": "CSI"}}}],
            "CSI by variable and period (development periods are the reference)", "", "", yaxis={"automargin": True}), "note": ""})
        charts.append({"id": "drift", "title": "Mean score over time", "figure": _fig([
            _line("Mean score", [r["period"] for r in drift_rows], [round(r["mean_score"], 2) for r in drift_rows], PALETTE["purple"], mode="lines+markers"),
            _hline(dmean, PALETTE["grey"], "Development mean", periods[0], periods[-1])], "Mean score by period", "", "Mean score"), "note": ""})
        sections.append({"id": "stability", "title": GROUP_TITLES["stability"], "tests": t, "tables": tables, "charts": charts})
        tests_run += t
    # -------------------------------------------------------------------- variables
    if plan["tests"].get("variables"):
        say("Testing the variables")
        t, tables, charts = [], [], []
        rows, weak, nonmono = [], 0, 0
        woe_charts = []
        for v in spec["variables"]:
            col = f"bin_{v['name']}"
            y_ = dev_m.y12.to_numpy(dtype=float)
            nb = len(v["bins"])
            bd = np.bincount(dev_m[col].to_numpy(), weights=y_, minlength=nb)
            gd = np.bincount(dev_m[col].to_numpy(), weights=1 - y_, minlength=nb)
            bm = np.bincount(mon[col].to_numpy(), weights=mon.y12.to_numpy(dtype=float), minlength=nb)
            gm = np.bincount(mon[col].to_numpy(), weights=1 - mon.y12.to_numpy(dtype=float), minlength=nb)
            def woe_iv(b: np.ndarray, g: np.ndarray) -> tuple[np.ndarray, float]:
                pb, pg = (b + 0.5) / (b.sum() + 0.5), (g + 0.5) / (g.sum() + 0.5)
                w = np.log(pg / pb)
                return w, float(((pg - pb) * w).sum())
            w_d, iv_d = woe_iv(bd, gd)
            w_m, iv_m = woe_iv(bm, gm)
            weak += iv_m < 0.02
            mono_status, rho = NA, None
            if v["type"] == "numeric" and v.get("direction"):
                keep = [k for k, b in enumerate(v["bins"]) if not b.get("missing") and (bm[k] + gm[k]) >= 30]
                if len(keep) >= 3:
                    rates = (bm[keep] / (bm[keep] + gm[keep]))
                    rho = float(stats.spearmanr(np.arange(len(keep)), rates).statistic) * v["direction"]
                    mono_status = GREEN if rho >= 0.7 else RED
                    nonmono += mono_status == RED
            rows.append({"variable": v["label"], "name": v["name"], "iv_dev": iv_d, "iv_mon": iv_m, "iv_spec": v["iv"],
                         "iv_status": GREEN if iv_m >= 0.10 else AMBER if iv_m >= 0.02 else RED, "monotone_rho": rho, "monotone": mono_status})
            labels = [b["label"] for b in v["bins"]]
            woe_charts.append({"id": f"woe_{v['name']}", "title": f"WoE: {v['label']}", "figure": _fig([
                {"type": "bar", "name": "Development", "x": labels, "y": w_d.round(4).tolist(), "marker": {"color": PALETTE["grey"]}},
                {"type": "bar", "name": "Monitoring", "x": labels, "y": w_m.round(4).tolist(), "marker": {"color": PALETTE["teal"]}}],
                f"Weight of evidence: {v['label']} (IV {iv_d:.3f} development, {iv_m:.3f} monitoring)", "Bin", "WoE", barmode="group",
                xaxis={"tickangle": -25, "automargin": True}), "note": ""})
        t.append(_item("iv", "variables", weak, rate(weak, th["iv"]), th["iv"], f"{weak} of {len(rows)} model variables carry less than 0.02 IV on the monitoring sample."))
        t.append(_item("monotone", "variables", nonmono, rate(nonmono, th["monotone"]), th["monotone"],
                       "Monotone means the bad rate still moves the way it did in development across the bins that hold 30+ observations."
                       if not nonmono else "Not monotone: " + ", ".join(r["variable"] for r in rows if r["monotone"] == RED) + "."))
        W = np.column_stack([np.asarray([b["woe"] for b in v["bins"]])[mon[f"bin_{v['name']}"].to_numpy()] for v in spec["variables"]])
        C = np.corrcoef(W, rowvar=False)
        names = [v["label"] for v in spec["variables"]]
        off = np.abs(C - np.eye(len(C)))
        i, j = np.unravel_index(np.argmax(off), off.shape)
        t.append(_item("corr", "variables", off.max(), rate(float(off.max()), th["corr"]), th["corr"], f"{names[i]} and {names[j]} are the most correlated pair ({C[i, j]:.2f})."))
        vif = np.diag(np.linalg.inv(C + np.eye(len(C)) * 1e-9))
        k = int(np.argmax(vif))
        t.append(_item("vif", "variables", vif[k], rate(float(vif[k]), th["vif"]), th["vif"], f"{names[k]} has the largest VIF ({vif[k]:.2f})."))
        for r, vf in zip(rows, vif):
            r["vif"] = float(vf)
        tables.append({"id": "var_table", "title": "Variable diagnostics",
                       "columns": [{"key": "variable", "label": "Variable", "format": "text"}, {"key": "iv_dev", "label": "IV development", "format": "num4"},
                                   {"key": "iv_mon", "label": "IV monitoring", "format": "num4"}, {"key": "iv_status", "label": "IV verdict", "format": "rag"},
                                   {"key": "monotone_rho", "label": "Monotonicity", "format": "num"}, {"key": "monotone", "label": "Monotone", "format": "rag"},
                                   {"key": "vif", "label": "VIF", "format": "num"}],
                       "rows": rows, "note": "IV verdict: green from 0.10, amber 0.02 to 0.10, red below 0.02. Monotonicity is the rank correlation of the bin order with the bad rate, in the development direction."})
        charts.append({"id": "iv_bar", "title": "Information value", "figure": _fig([
            {"type": "bar", "name": "Development", "x": names, "y": [round(r["iv_dev"], 4) for r in rows], "marker": {"color": PALETTE["grey"]}},
            {"type": "bar", "name": "Monitoring", "x": names, "y": [round(r["iv_mon"], 4) for r in rows], "marker": {"color": PALETTE["blue"]}},
            _hline(0.02, PALETTE["red"], "0.02", names[0], names[-1])], "Information value by variable", "", "IV", barmode="group",
            xaxis={"tickangle": -25, "automargin": True}), "note": ""})
        charts.append({"id": "corr", "title": "Correlation of WoE variables", "figure": _fig([
            {"type": "heatmap", "x": names, "y": names, "z": C.round(3).tolist(), "zmin": -1, "zmax": 1,
             "colorscale": [[0, "#2F80ED"], [0.5, "#FFFFFF"], [1, "#D64545"]], "hovertemplate": "%{y} × %{x}: %{z:.2f}<extra></extra>"}],
            "Correlation of WoE-transformed variables (monitoring sample)", "", "", xaxis={"tickangle": -30, "automargin": True}), "note": ""})
        charts.append({"id": "vif", "title": "Variance inflation factors", "figure": _fig([
            {"type": "bar", "x": names, "y": [round(float(x), 3) for x in vif], "marker": {"color": [RAG_COLOUR[rate(float(x), th["vif"])] for x in vif]}, "name": "VIF"},
            _hline(th["vif"]["green"], PALETTE["green"], "5", names[0], names[-1]), _hline(th["vif"]["amber"], PALETTE["red"], "10", names[0], names[-1])],
            "VIF by variable", "", "VIF", xaxis={"tickangle": -25, "automargin": True}), "note": ""})
        charts += woe_charts
        sections.append({"id": "variables", "title": GROUP_TITLES["variables"], "tests": t, "tables": tables, "charts": charts})
        tests_run += t
    # -------------------------------------------------------------------- overrides
    if plan["tests"].get("overrides"):
        t, tables, charts = [], [], []
        if not spec["has_overrides"]:
            t.append(_item("override_rate", "overrides", None, NA, th["override_rate"], "Not applicable: this scorecard scores a live book every month and its data records no overrides."))
        else:
            say("Testing overrides")
            orate = float(mon.override_flag.mean())
            t.append(_item("override_rate", "overrides", orate, rate(orate, th["override_rate"]), th["override_rate"],
                           f"{int(mon.override_flag.sum()):,} of {len(mon):,} decisions were overridden ({orate:.1%}): "
                           f"{int((mon.override_direction == 'upgrade').sum()):,} approved against the grade, {int((mon.override_direction == 'downgrade').sum()):,} declined against it."))
            up = mon[mon.override_direction == "upgrade"]
            if len(up) >= 30:
                o_, e_ = float(up.y12.mean()), float(up.pd_grade.mean())
                ratio = o_ / e_
                t.append(_item("override_upgrade", "overrides", ratio, rate(ratio, th["override_upgrade"]), th["override_upgrade"],
                               f"Upgraded decisions defaulted at {o_:.2%} against {e_:.2%} expected for their grades ({ratio:.2f} times)."))
            rows = []
            for dname, g in mon.groupby("override_direction"):
                rows.append({"direction": {"none": "No override", "upgrade": "Approved against the grade (upgrade)", "downgrade": "Declined against the grade (downgrade)"}[dname],
                             "n": int(len(g)), "defaults": int(g.y12.sum()), "odr": float(g.y12.mean()), "pd": float(g.pd_grade.mean())})
            tables.append({"id": "ovr_outcome", "title": "Outcome by override decision (monitoring sample)",
                           "columns": [{"key": "direction", "label": "Decision", "format": "text"}, {"key": "n", "label": "Observations", "format": "int"},
                                       {"key": "defaults", "label": "Defaults", "format": "int"}, {"key": "odr", "label": "Observed", "format": "pct2"},
                                       {"key": "pd", "label": "Expected", "format": "pct2"}], "rows": rows, "note": ""})
            ov = mon[mon.override_flag == 1]
            rr = ov.groupby(["override_reason"]).agg(n=("override_flag", "size"), defaults=("y12", "sum")).reset_index().sort_values("n", ascending=False)
            tables.append({"id": "ovr_reason", "title": "Overrides by reason",
                           "columns": [{"key": "override_reason", "label": "Reason", "format": "text"}, {"key": "n", "label": "Overrides", "format": "int"},
                                       {"key": "defaults", "label": "Defaults", "format": "int"}], "rows": rr.to_dict("records"), "note": ""})
            lv = ov.groupby("override_level").agg(n=("override_flag", "size"), defaults=("y12", "sum")).reset_index().sort_values("n", ascending=False)
            tables.append({"id": "ovr_level", "title": "Overrides by approval level",
                           "columns": [{"key": "override_level", "label": "Level", "format": "text"}, {"key": "n", "label": "Overrides", "format": "int"},
                                       {"key": "defaults", "label": "Defaults", "format": "int"}], "rows": lv.to_dict("records"), "note": ""})
            per = f[(f.period >= m0) & (f.period <= as_of)].groupby("period").override_flag.mean()
            charts.append({"id": "ovr_rate", "title": "Override rate by period", "figure": _fig([
                {"type": "bar", "name": "Override rate", "x": per.index.tolist(), "y": per.round(4).tolist(), "marker": {"color": PALETTE["orange"]}},
                _hline(th["override_rate"]["green"], PALETTE["green"], "5%", per.index[0], per.index[-1]),
                _hline(th["override_rate"]["amber"], PALETTE["red"], "10%", per.index[0], per.index[-1])],
                "Override rate by period", "", "Override rate", yaxis={"tickformat": ".0%", "title": {"text": "Override rate"}}), "note": ""})
            charts.append({"id": "ovr_outcome", "title": "Default rate by override decision", "figure": _fig([
                {"type": "bar", "name": "Observed", "x": [r["direction"] for r in rows], "y": [r["odr"] for r in rows], "marker": {"color": PALETTE["red"]}},
                {"type": "bar", "name": "Expected", "x": [r["direction"] for r in rows], "y": [r["pd"] for r in rows], "marker": {"color": PALETTE["grey"]}}],
                "Observed vs expected default rate by decision", "", "Default rate", barmode="group", yaxis={"tickformat": ".1%", "title": {"text": "Default rate"}}), "note": ""})
        sections.append({"id": "overrides", "title": GROUP_TITLES["overrides"], "tests": t, "tables": tables, "charts": charts})
        tests_run += t
    counts = {s: sum(1 for x in tests_run if x["status"] == s) for s in (GREEN, AMBER, RED, NA)}
    overall = RED if counts[RED] else AMBER if counts[AMBER] else GREEN
    for sec in sections:
        ss = [x["status"] for x in sec["tests"] if x["status"] != NA]
        sec["status"] = NA if not ss else RED if RED in ss else AMBER if AMBER in ss else GREEN
    result = {"engine_version": ENGINE_VERSION, "plan": plan, "scorecard": {k: v for k, v in scorecards_by_id()[sid].items()},
              "sample": info, "summary": {"overall": overall, "counts": counts, "tests": len(tests_run)}, "sections": sections,
              "thresholds": {k: {"label": v["label"], "text": v["text"]} for k, v in th.items()}, "seconds": round(time.time() - t0, 2)}
    result["findings"] = findings(result)
    drawn = {c["id"] for sec in sections for c in sec["charts"]}
    result["key_charts"] = [c for c in KEY_CHARTS if c in drawn]
    return chart_style.style_result(json.loads(json.dumps(result, default=_jd)))


def scorecards_by_id() -> dict[str, dict[str, Any]]:
    return {s["scorecard_id"]: s for s in scorecards()}


def _jd(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


ACTIONS = {
    "gini": "Review the rank-ordering: re-run the development with the latest matured window and compare the variable set.",
    "gini_change": "Investigate which variables lost power (see the CSI and WoE charts) before the next committee.",
    "ks": "Check the score separation by segment; consider a segment-specific scorecard if one segment drives the loss.",
    "gini_segment": "The weakest segment needs its own diagnosis or a segment overlay.",
    "oe_ratio": "Recalibrate the grade PDs on the latest matured window; the ranking is intact only if the Gini tests are green.",
    "binomial": "Recalibrate the grades flagged red and document the interim PD overlay until the recalibration is approved.",
    "hl": "Recalibrate the master scale; the model under-predicts across the grade range.",
    "brier": "The grade PDs carry no more information than a flat rate: rebuild or recalibrate.",
    "psi": "The population has moved: confirm the cause (mix, channel, policy) and consider a redevelopment sample.",
    "csi": "Review the variable with the largest CSI and the policy or data change behind it.",
    "drift": "The average score has moved away from development; check for an origination or data-feed change.",
    "mix": "The segment mix has changed; test the scorecard on the new mix before relying on its PDs.",
    "iv": "Replace or re-bin the variables that no longer separate good from bad.",
    "monotone": "Re-bin the variables whose WoE order has broken.",
    "corr": "Drop or combine one of the correlated variables at the next redevelopment.",
    "vif": "Remove the collinear variable at the next redevelopment.",
    "override_rate": "Review override authority levels and reasons; a high rate means the scorecard is not trusted at the point of decision.",
    "override_upgrade": "Tighten approval authority for upgrade overrides: they default well above their grade.",
}


def findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for sec in result["sections"]:
        for x in sec["tests"]:
            if x["status"] in (RED, AMBER):
                out.append({"test": x["id"], "group": sec["id"], "label": x["label"], "status": x["status"], "text": x["comment"], "action": ACTIONS.get(x["id"], "")})
    out.sort(key=lambda r: (0 if r["status"] == RED else 1))
    return out
