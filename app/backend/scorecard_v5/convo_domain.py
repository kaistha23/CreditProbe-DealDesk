"""The Scorecard Validation domain for the shared conversational layer (backend/convo, PLAN_R4 A2).

The forked Cockpit agent answers questions about a scorecard at scorecard, variable,
bin and sample grain: the scored observations (the sample), the variables and their
development bins (WoE, points), the master scale, and the thread's finished
validation (every test with its value, threshold and verdict). The validation
engine's statistics are tools: a prioritised diagnosis, Gini by segment, PSI/CSI
for one variable, the override analysis and calibration by grade. The standard flow
(choose -> plan -> run -> review -> report) stays in `assistant.respond`.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable

import numpy as np
import pandas as pd

from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult
from backend.scorecard_v5 import engine
from backend.scorecard_v5.assistant import GLOSSARY, SEG_WORDS
from backend.scorecard_v5.domain import build

#: validation_id -> result (set by the API to its store; tests set their own)
RESULT: Callable[[str], dict[str, Any] | None] = lambda vid: None


def _sid(scope: dict[str, Any]) -> str:
    return scope.get("scorecard_id") or "RET-APP"


def _plan(scope: dict[str, Any]) -> dict[str, Any]:
    return scope.get("plan") or engine.default_plan(_sid(scope))


def _result(scope: dict[str, Any]) -> dict[str, Any] | None:
    vid = scope.get("validation_id")
    return RESULT(vid) if vid else None


def _frame(sid: str) -> pd.DataFrame:
    return engine.domain(sid).frame


def _window(f: pd.DataFrame, win: list[str], matured: bool = True) -> pd.DataFrame:
    m = (f["period"] >= win[0]) & (f["period"] <= win[1])
    if matured:
        m &= f["matured"].astype(bool)
    return f[m]


# ------------------------------------------------------------------ relations

def _observations(scope: dict[str, Any]) -> pd.DataFrame:
    f = _frame(_sid(scope))
    return f.drop(columns=[c for c in ("scorecard_id",) if c in f.columns]).copy()


def _variables(scope: dict[str, Any]) -> pd.DataFrame:
    sp = engine.domain(_sid(scope)).spec
    return pd.DataFrame([{"variable": v["name"], "label": v["label"], "type": v["type"], "iv_development": v["iv"],
                          "coefficient": v["coef"], "bins": len(v["bins"]),
                          "points_min": min(b["points"] for b in v["bins"]), "points_max": max(b["points"] for b in v["bins"])}
                         for v in sp["variables"]])


def _bins(scope: dict[str, Any]) -> pd.DataFrame:
    sp = engine.domain(_sid(scope)).spec
    rows = []
    for v in sp["variables"]:
        for i, b in enumerate(v["bins"]):
            rows.append({"variable": v["name"], "bin": i, "bin_label": b.get("label", str(i)), "n_development": b["n"],
                         "share_development": b["share"], "bad_rate_development": b["bad_rate"], "woe": b["woe"],
                         "points": b["points"]})
    return pd.DataFrame(rows)


def _grades(scope: dict[str, Any]) -> pd.DataFrame:
    sp = engine.domain(_sid(scope)).spec
    g = sp["grades"]
    if g and isinstance(g[0], dict):
        return pd.DataFrame(g)
    return pd.DataFrame({"grade": g})


def _tests(scope: dict[str, Any]) -> pd.DataFrame:
    r = _result(scope)
    if not r:
        return pd.DataFrame(columns=["test_id", "group", "label", "value", "threshold", "status", "comment"])
    return pd.DataFrame([{"test_id": x["id"], "group": s["id"], "label": x["label"],
                          "value": x["value"] if isinstance(x["value"], (int, float)) else None,
                          "value_text": str(x["value"]), "threshold": x.get("threshold", ""), "status": x["status"],
                          "comment": x["comment"]} for s in r["sections"] for x in s["tests"]])


def relations(scope: dict[str, Any]) -> list[Relation]:
    sid = _sid(scope)
    sc = build.SCORECARDS[sid]
    sp = engine.domain(sid).spec
    unit = "account-month" if sc["frequency"] == "monthly" else "borrower-quarter"
    return [
        Relation("observations", f"The scored sample of the {sc['name']}: one row per {unit}, {sp['periods'][0]} to "
                                 f"{sp['periods'][-1]}; y12 = default within 12 months (final only where matured)",
                 _observations, grain=unit,
                 columns={"sample": "development | monitoring | ...", "matured": "outcome window closed",
                          "y12": "1 = defaulted within 12 months", "score": "scorecard points (low = risky)",
                          "pd_grade": "master-scale PD of the grade", "pd_model": "model PD",
                          "override_direction": "none | upgrade | downgrade", **{f"bin_{v['name']}": f"bin index of {v['name']}"
                                                                                for v in sp["variables"]}}),
        Relation("variables", "The scorecard's variables: development IV, coefficient, number of bins, points range",
                 _variables, grain="variable"),
        Relation("bins", "Development bins of every variable: count, share, bad rate, WoE and points", _bins,
                 grain="variable x bin"),
        Relation("grades", "The master scale grades", _grades, grain="grade"),
        Relation("tests", "The thread's finished validation: every test with value, threshold, verdict and comment "
                          "(empty before the validation has run)", _tests, grain="test"),
    ]


# ------------------------------------------------------------------ tools (the engine's statistics)

def _gini(y: np.ndarray, s: np.ndarray) -> float | None:
    if len(y) < 2 or y.sum() == 0 or y.sum() == len(y):
        return None
    return 2 * engine._auc(y, s) - 1


def t_segment_gini(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    sid = _sid(ctx.scope)
    plan = _plan(ctx.scope)
    by = str(args.get("segment_by") or plan.get("segment_by") or build.SCORECARDS[sid]["segment_col"])
    by = SEG_WORDS.get(by, by)
    f = _frame(sid)
    if by not in f.columns:
        return ToolResult(summary=f"'{by}' is not a column; options: {', '.join(engine.segment_options(sid))}", data={})
    win = plan["monitoring"] if args.get("window", "monitoring") == "monitoring" else plan["development"]
    w = _window(f, win)
    rows = []
    for k, g in w.groupby(by):
        y, s = g["y12"].to_numpy(float), g["score"].to_numpy(float)
        gi = _gini(y, s)
        rows.append({by: k, "observations": int(len(g)), "defaults": int(y.sum()),
                     "default_rate_pct": round(float(y.mean() * 100), 2) if len(g) else None,
                     "gini_pct": round(gi * 100, 1) if gi is not None else None})
    rows.sort(key=lambda r: (r["gini_pct"] is None, r["gini_pct"] if r["gini_pct"] is not None else 0))
    tot = _gini(w["y12"].to_numpy(float), w["score"].to_numpy(float))
    dev = _window(f, plan["development"])
    dev_g = _gini(dev["y12"].to_numpy(float), dev["score"].to_numpy(float))
    return ToolResult(summary=f"Gini by {by} on the {args.get('window', 'monitoring')} window {win[0]} to {win[1]}",
                      data={"segment_by": by, "window": win, "overall_gini_pct": round(tot * 100, 1) if tot is not None else None,
                            "development_gini_pct": round(dev_g * 100, 1) if dev_g is not None else None,
                            "observations": int(len(w)), "defaults": int(w["y12"].sum())}, rows=rows)


def t_variable_psi(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    sid = _sid(ctx.scope)
    plan = _plan(ctx.scope)
    sp = engine.domain(sid).spec
    name = str(args.get("variable") or "")
    var = next((v for v in sp["variables"] if v["name"] == name or v["label"].lower() == name.lower()), None)
    if var is None:
        var = next((v for v in sp["variables"] if name and name.lower() in (v["name"] + " " + v["label"]).lower()), None)
    if var is None:
        return ToolResult(summary="Unknown variable", data={"variables": [v["name"] for v in sp["variables"]]})
    f = _frame(sid)
    col = f"bin_{var['name']}"
    dev = _window(f, plan["development"], matured=False)
    mon = _window(f, plan["monitoring"], matured=False)
    asof = f[f["period"] == plan["as_of"]]
    rows = []
    psi_m = psi_a = 0.0
    for i, b in enumerate(var["bins"]):
        d = max(float((dev[col] == i).mean()), 1e-6)
        m = max(float((mon[col] == i).mean()), 1e-6)
        a = max(float((asof[col] == i).mean()), 1e-6) if len(asof) else 1e-6
        cm = (m - d) * math.log(m / d)
        ca = (a - d) * math.log(a / d)
        psi_m += cm
        psi_a += ca
        md = _window(f, plan["monitoring"])
        br = md.loc[md[col] == i, "y12"]
        rows.append({"bin": b.get("label", str(i)), "share_development_pct": round(d * 100, 2),
                     "share_monitoring_pct": round(m * 100, 2), "share_as_of_pct": round(a * 100, 2),
                     "psi_contribution": round(cm, 4), "bad_rate_development_pct": round(b["bad_rate"] * 100, 2),
                     "bad_rate_monitoring_pct": round(float(br.mean() * 100), 2) if len(br) else None,
                     "woe": round(b["woe"], 3), "points": round(b["points"], 1)})
    by_period = []
    for p, g in f[f["period"] >= plan["development"][0]].groupby("period"):
        v = 0.0
        for i in range(len(var["bins"])):
            d = max(float((dev[col] == i).mean()), 1e-6)
            c = max(float((g[col] == i).mean()), 1e-6)
            v += (c - d) * math.log(c / d)
        by_period.append({"period": p, "psi": round(v, 4)})
    status = "stable" if psi_m < 0.10 else "moderate shift" if psi_m < 0.25 else "major shift"
    return ToolResult(summary=f"PSI (CSI) of {var['label']}: monitoring {psi_m:.3f} ({status}), as of {plan['as_of']} {psi_a:.3f}",
                      data={"variable": var["name"], "label": var["label"], "csi_monitoring": round(psi_m, 4),
                            "csi_as_of": round(psi_a, 4), "reading": status, "iv_development": round(var["iv"], 4),
                            "psi_by_period": by_period[-12:]}, rows=rows)


def t_overrides(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    sid = _sid(ctx.scope)
    plan = _plan(ctx.scope)
    if not build.SCORECARDS[sid]["has_overrides"]:
        return ToolResult(summary="This scorecard's data records no overrides.", data={"has_overrides": False})
    f = _frame(sid)
    w = _window(f, plan["monitoring"], matured=False)
    rate = float(w["override_flag"].mean())
    mat = _window(f, plan["monitoring"])
    rows = []
    for d, g in mat.groupby("override_direction"):
        rows.append({"direction": d, "observations": int(len(g)), "defaults": int(g["y12"].sum()),
                     "default_rate_pct": round(float(g["y12"].mean() * 100), 2),
                     "grade_pd_pct": round(float(g["pd_grade"].mean() * 100), 2),
                     "observed_to_expected": round(float(g["y12"].mean() / g["pd_grade"].mean()), 2) if g["pd_grade"].mean() else None})
    reasons = (w[w["override_flag"] == 1].groupby("override_reason").size().sort_values(ascending=False).head(8))
    return ToolResult(summary=f"Override rate {rate * 100:.2f}% on the monitoring window",
                      data={"override_rate_pct": round(rate * 100, 2), "overrides": int(w["override_flag"].sum()),
                            "observations": int(len(w)), "reasons": {str(k): int(v) for k, v in reasons.items()}},
                      rows=rows)


def t_calibration(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    from scipy.stats import binom
    sid = _sid(ctx.scope)
    plan = _plan(ctx.scope)
    w = _window(_frame(sid), plan["monitoring"])
    rows = []
    for g, d in w.groupby("grade"):
        n, k, p = len(d), int(d["y12"].sum()), float(d["pd_grade"].mean())
        pv = float(binom.sf(k - 1, n, p)) if n else None
        rows.append({"grade": g, "observations": n, "defaults": k, "observed_dr_pct": round(k / n * 100, 3) if n else None,
                     "grade_pd_pct": round(p * 100, 3), "observed_to_expected": round(k / n / p, 2) if n and p else None,
                     "binomial_p_value": round(pv, 4) if pv is not None else None})
    rows.sort(key=lambda r: r["grade"])
    tot_o = float(w["y12"].mean()) if len(w) else 0.0
    tot_e = float(w["pd_grade"].mean()) if len(w) else 0.0
    return ToolResult(summary=f"Calibration by grade on {plan['monitoring'][0]} to {plan['monitoring'][1]}",
                      data={"observed_dr_pct": round(tot_o * 100, 3), "expected_dr_pct": round(tot_e * 100, 3),
                            "observed_to_expected": round(tot_o / tot_e, 3) if tot_e else None}, rows=rows)


def t_diagnose(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    res = _result(ctx.scope)
    ran_here = False
    if res is None:
        res = engine.run(_plan(ctx.scope))
        ran_here = True
    fs = engine.findings(res)
    tests = {x["id"]: x for s in res["sections"] for x in s["tests"]}
    rows = [{"priority": i + 1, "status": f["status"], "test": f["label"], "group": engine.GROUP_TITLES.get(f["group"], f["group"]),
             "value": tests[f["test"]]["value"] if isinstance(tests[f["test"]]["value"], (int, float)) else str(tests[f["test"]]["value"]),
             "threshold": tests[f["test"]].get("threshold", ""), "finding": f["text"], "remedy": f["action"]}
            for i, f in enumerate(fs)]
    return ToolResult(summary=(f"{res['summary']['counts']['red']} red, {res['summary']['counts']['amber']} amber, "
                               f"{res['summary']['counts']['green']} green of {res['summary']['tests']} tests"
                               + (" (default plan, not saved)" if ran_here else "")),
                      data={"counts": res["summary"]["counts"], "overall": res["summary"]["overall"],
                            "as_of": res["plan"]["as_of"], "monitoring": res["plan"]["monitoring"],
                            "green_tests": [x["label"] for x in tests.values() if x["status"] == "green"]},
                      rows=rows, blocks=[{"type": "findings", "items": fs}] if fs else [])


TOOLS = [
    Tool("diagnose", "The validation's red and amber tests in priority order, each with value, threshold, the finding "
         "and the remedy (runs the default plan if the thread has no validation yet; nothing is saved).",
         {"type": "object", "properties": {}}, t_diagnose, message="Diagnosing the scorecard"),
    Tool("segment_gini", "Gini (and default rate) by segment on the monitoring or development window.",
         {"type": "object", "properties": {"segment_by": {"type": "string"},
                                           "window": {"type": "string", "enum": ["monitoring", "development"]}}},
         t_segment_gini, message="Measuring Gini by segment"),
    Tool("variable_psi", "PSI/CSI of one variable: bin shares development vs monitoring vs as-of, contribution per bin, "
         "bad rate per bin, and PSI by period.",
         {"type": "object", "required": ["variable"], "properties": {"variable": {"type": "string"}}}, t_variable_psi,
         message="Measuring the variable's stability"),
    Tool("override_analysis", "Override rate, reasons, and default performance of upgrades and downgrades against "
         "their grade PD.", {"type": "object", "properties": {}}, t_overrides, message="Analysing overrides"),
    Tool("calibration_by_grade", "Observed against expected default rate by grade with the binomial p-value.",
         {"type": "object", "properties": {}}, t_calibration, message="Checking calibration by grade"),
]

KNOWLEDGE = {k: v for k, v in GLOSSARY.items()}
KNOWLEDGE["remedies"] = " ".join(f"{k}: {v}" for k, v in engine.ACTIONS.items())
KNOWLEDGE["thresholds"] = "Default thresholds: " + "; ".join(
    f"{t['label']}: {t['text']}" for t in engine.thresholds_for("RET-APP").values())


# ------------------------------------------------------------------ deterministic planner

def _variable_in(q: str, sid: str) -> str:
    sp = engine.domain(sid).spec
    low = q.lower()
    for v in sp["variables"]:
        if v["name"].lower() in low or v["label"].lower() in low or v["name"].replace("_", " ").lower() in low:
            return v["name"]
    return ""


def planner(q: str, ctx: ToolContext) -> Plan:
    low = q.lower()
    sid = _sid(ctx.scope)
    var = _variable_in(q, sid)
    if re.search(r"\b(psi|csi|stabil|drift|shift)", low) and var:
        return Plan([PlanStep("variable_psi", {"variable": var})], _write_psi)
    if re.search(r"\bgini\b", low) and re.search(r"segment|by |per |each", low):
        seg = next((v for k, v in SEG_WORDS.items() if re.search(rf"\b{k}", low)), "")
        return Plan([PlanStep("segment_gini", {"segment_by": seg} if seg else {})], _write_gini)
    if re.search(r"override", low):
        return Plan([PlanStep("override_analysis", {})], _write_overrides)
    if re.search(r"calibrat|by grade|observed|expected|binomial", low):
        return Plan([PlanStep("calibration_by_grade", {})], _write_calibration)
    for key in GLOSSARY:
        if re.search(rf"\b(what is|what does|define|meaning of)\b.*\b{key}", low):
            return Plan([PlanStep("read_knowledge", {"topic": key})],
                        lambda res, key=key: {"markdown": f"**{key.upper() if len(key) < 5 else key.title()}.** {res[0]['out'].get('text', '')}"})
    return Plan([PlanStep("diagnose", {}), PlanStep("segment_gini", {})], _write_diagnosis)


def _rows(r: dict) -> list[dict]:
    return (r.get("artifact") or {}).get("rows") or []


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _write_diagnosis(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    rows = _rows(res[0])
    c = d.get("counts") or {}
    head = (f"**Verdict: {str(d.get('overall', '')).upper()}.** {c.get('red', 0)} red, {c.get('amber', 0)} amber and "
            f"{c.get('green', 0)} green tests (as of {d.get('as_of')}, monitoring {d.get('monitoring', ['', ''])[0]} to "
            f"{d.get('monitoring', ['', ''])[1]}).")
    if not rows:
        return {"markdown": head + " Nothing needs action: keep the scorecard in use and re-run at the next reporting date."}
    lines = [f"{r['priority']}. **{r['test']}** ({r['status']}, {r['group']}): {r['finding']} *Remedy:* {r['remedy']}"
             for r in rows[:8]]
    g = res[1]["out"].get("data") or {} if len(res) > 1 else {}
    seg = _rows(res[1]) if len(res) > 1 else []
    tail = ""
    if seg and g.get("overall_gini_pct") is not None:
        weak = next((s for s in seg if s["gini_pct"] is not None), None)
        if weak:
            tail = (f"\n\nRanking power overall is a Gini of {g['overall_gini_pct']:g}% against {g['development_gini_pct']:g}% "
                    f"at development; the weakest {g['segment_by'].replace('_', ' ')} is **{weak[g['segment_by']]}** at "
                    f"{weak['gini_pct']:g}%.")
    green = d.get("green_tests") or []
    return {"markdown": head + "\n\n**What is wrong, in priority order:**\n\n" + "\n".join(lines) + tail +
            (f"\n\nStill sound: {', '.join(green[:6])}." if green else ""),
            "charts": ([{"artifact_id": res[1]["out"]["artifact_id"], "kind": "hbar", "x": g.get("segment_by"),
                         "y": ["gini_pct"], "title": f"Gini by {str(g.get('segment_by', '')).replace('_', ' ')} (%)"}]
                       if seg and g.get("segment_by") else [])}


def _write_gini(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    rows = _rows(res[0])
    if not rows:
        return {"markdown": res[0]["out"].get("summary", "")}
    by = d["segment_by"]
    valid = [r for r in rows if r["gini_pct"] is not None]
    lo, hi = valid[0], valid[-1]
    return {"markdown": f"**Gini by {by.replace('_', ' ')}** ({d['window'][0]} to {d['window'][1]}): overall "
                        f"{d['overall_gini_pct']:g}% (development {d['development_gini_pct']:g}%). Strongest **{hi[by]}** at "
                        f"{hi['gini_pct']:g}%, weakest **{lo[by]}** at {lo['gini_pct']:g}% on {lo['observations']:,} "
                        f"observations and {lo['defaults']:,} defaults.",
            "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": f"Gini by {by.replace('_', ' ')}"}],
            "charts": [{"artifact_id": res[0]["out"]["artifact_id"], "kind": "hbar", "x": by, "y": ["gini_pct"],
                        "title": f"Gini by {by.replace('_', ' ')} (%)"}]}


def _write_psi(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    rows = _rows(res[0])
    if not rows:
        return {"markdown": res[0]["out"].get("summary", "")}
    top = max(rows, key=lambda r: abs(r["psi_contribution"]))
    return {"markdown": f"**{d['label']}**: CSI {d['csi_monitoring']:g} on the monitoring window ({d['reading']}), "
                        f"{d['csi_as_of']:g} at the as-of period. The largest contribution is the bin **{top['bin']}** "
                        f"({top['share_development_pct']:g}% at development, {top['share_monitoring_pct']:g}% in monitoring).",
            "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": f"{d['label']}: bin shares and PSI"}],
            "charts": [{"artifact_id": res[0]["out"]["artifact_id"], "kind": "grouped", "x": "bin",
                        "y": ["share_development_pct", "share_monitoring_pct"], "title": f"{d['label']}: bin shares (%)"}]}


def _write_overrides(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    rows = _rows(res[0])
    if not d.get("override_rate_pct") and not rows:
        return {"markdown": res[0]["out"].get("summary", "")}
    up = next((r for r in rows if r["direction"] == "upgrade"), None)
    md = f"**Overrides**: {d['override_rate_pct']:g}% of decisions ({d['overrides']:,} of {d['observations']:,})."
    if up:
        md += (f" Upgrades defaulted at {up['default_rate_pct']:g}% against a grade PD of {up['grade_pd_pct']:g}% "
               f"({up['observed_to_expected']:g}x expected).")
    return {"markdown": md, "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": "Override performance"}]}


def _write_calibration(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    rows = _rows(res[0])
    bad = [r for r in rows if r["binomial_p_value"] is not None and r["binomial_p_value"] < 0.01]
    md = (f"**Calibration**: observed default rate {d['observed_dr_pct']:g}% against {d['expected_dr_pct']:g}% expected "
          f"(O/E {d['observed_to_expected']:g}).")
    if bad:
        md += " Under-predicted grades (binomial p < 0.01): " + ", ".join(
            f"**{r['grade']}** ({r['observed_dr_pct']:g}% vs {r['grade_pd_pct']:g}%)" for r in bad) + "."
    return {"markdown": md, "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": "Calibration by grade"}],
            "charts": [{"artifact_id": res[0]["out"]["artifact_id"], "kind": "grouped", "x": "grade",
                        "y": ["observed_dr_pct", "grade_pd_pct"], "title": "Observed vs grade PD (%)"}]}


def suggestions(scope: dict[str, Any], state: dict[str, Any]) -> list[dict[str, str]]:
    sid = _sid(scope)
    sp = engine.domain(sid).spec
    v = sp["variables"][0]["label"]
    out = [{"label": "What is wrong with my scorecard?", "send": "What is wrong with my scorecard?"},
           {"label": "Gini by segment", "send": "Show the Gini by segment"},
           {"label": f"PSI for {v}", "send": f"PSI for {v}"}]
    if build.SCORECARDS[sid]["has_overrides"]:
        out.append({"label": "Override analysis", "send": "Run the override analysis"})
    return out


CHARTER = ("You are the Scorecard Validation assistant in CreditProbe, a Saudi bank's credit-risk system: a model "
           "validator who explains any validation result in depth (discrimination, calibration, stability, variables, "
           "overrides) at scorecard, variable, bin and sample grain, diagnoses problems with their causes and remedies "
           "in priority order, and runs extra analyses on request. Quote thresholds and verdicts exactly as the tests "
           "table states them.")

DOMAIN = Domain(key="scorecard", title="Scorecard Validation", charter=CHARTER, relations=relations, tools=TOOLS,
                knowledge=KNOWLEDGE, planner=planner, suggestions=suggestions,
                scope_label=lambda s: f"the {build.SCORECARDS[_sid(s)]['name']}"
                + (f" (validation {s['validation_id']})" if s.get("validation_id") else ""),
                scope_key=lambda s: f"{_sid(s)}|{s.get('validation_id') or ''}",
                state_brief=lambda st: (f"Validation {st['validation_id']} has run." if st.get("validation_id")
                                        else "No validation has run in this thread yet."))
