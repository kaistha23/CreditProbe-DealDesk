"""The What-If agent's tools (A1): each wraps an existing What-If engine call and returns its figures.

    whatif_book_profile       the population in scope: EAD, reported ECL, coverage, stage mix, largest segments
    whatif_design_scenarios   3-4 graded scenarios with stated shocks and their basis (calibrate.py), each read back
                              through the existing compound parser (chat.language.read)
    whatif_run_scenario       runner.run (Delta or XGBoost) + likelihood.assess; attributions by segment, stage, driver
    whatif_test_action        a management action as a further run on top of a scenario: its ECL and capital effect
    whatif_size_overlay       the management overlay range from the scenario runs (no figure of its own)
    whatif_compare            scenarios and actions in one table

Runs of one agent run share a board (`ctx.results["__whatif_board"]`): the designed scenarios and every result, so a
later step reads earlier engine outputs instead of recomputing them. Nothing here changes state.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from backend.agents_v5.runtime import READ_ONLY, Tool, ToolContext, ToolResult, register_tool
from backend.agents_v5.whatif import calibrate
from backend.v5common import ratings
from backend.whatif_v5 import likelihood
from backend.whatif_v5.chat import language
from backend.whatif_v5.domain import store as dstore
from backend.whatif_v5.models import engine, runner
from backend.whatif_v5.models.scenario import DRIVER_LABELS, Scenario, Scope, Step, parse_shocks

MODULE = "whatif"
BOARD = "__whatif_board"
METHOD_NAMES = {"delta": "Delta method", "xgboost": "XGBoost"}


def board(ctx: ToolContext) -> dict[str, Any]:
    return ctx.results.setdefault(BOARD, {"scenarios": {}, "runs": {}, "actions": {}, "order": []})


def _domain(inputs: dict, ctx: ToolContext) -> str:
    return str(inputs.get("domain") or ctx.context.get("domain") or "corporate")


def _period(domain: str, inputs: dict, ctx: ToolContext) -> str:
    return dstore.resolve_period(domain, str(inputs.get("period") or ctx.context.get("period") or ""))


def _cohort(ctx: ToolContext) -> str:
    return str(ctx.context.get("cohort_id") or "")


def _vocab(domain: str) -> dict[str, Any]:
    f = dstore.frame(domain)
    return {"domain": domain, "segments": sorted(f["segment"].astype(str).unique()),
            "subsegments": sorted(f["subsegment"].astype(str).unique()), "labels": runner.LABELS[domain],
            "has_scenario": False}


# ------------------------------------------------------------------ 1. the book

def book_profile(inputs: dict, ctx: ToolContext) -> ToolResult:
    domain = _domain(inputs, ctx)
    period = _period(domain, inputs, ctx)
    f = dstore.frame(domain, period)
    sc = Scenario(domain=domain, period=period, steps=[], cohort_id=_cohort(ctx))
    pop, _ = runner.population(sc, f)
    f = f[pop]
    segs = [s for s in inputs.get("segments") or [] if s]
    ead, ecl = float(f["ead"].sum()), float(f["ecl_final"].sum())
    by_seg = (f.groupby("segment").agg(ead=("ead", "sum"), ecl=("ecl_final", "sum"), n=("exposure_id", "count"))
              .sort_values("ead", ascending=False))
    rows = [{"segment": str(i), "ead": float(r["ead"]), "ecl": float(r["ecl"]), "exposures": int(r["n"]),
             "share_ead_pct": float(r["ead"]) / ead * 100 if ead else 0.0,
             "coverage_pct": float(r["ecl"]) / float(r["ead"]) * 100 if r["ead"] else 0.0} for i, r in by_seg.iterrows()]
    stage = {str(s): {"n": int((f["stage"] == s).sum()), "ead": float(f.loc[f["stage"] == s, "ead"].sum())} for s in (1, 2, 3)}
    figures = {"ead": ead, "ecl": ecl, "coverage_pct": ecl / ead * 100 if ead else 0.0, "exposures": int(len(f)),
               "stage2_ead": stage["2"]["ead"], "stage3_ead": stage["3"]["ead"],
               "stage2_n": stage["2"]["n"], "stage3_n": stage["3"]["n"]}
    for r in rows:
        if r["segment"] in segs:
            figures[f"{r['segment']}_ead"] = r["ead"]
            figures[f"{r['segment']}_ecl"] = r["ecl"]
            figures[f"{r['segment']}_share_ead_pct"] = r["share_ead_pct"]
            figures[f"{r['segment']}_coverage_pct"] = r["coverage_pct"]
    lab = runner.LABELS[domain]
    data = {"domain": domain, "period": period, "labels": lab, "by_segment": rows, "stage": stage, **figures,
            "population": f"Early Warning cohort {_cohort(ctx)}" if _cohort(ctx) else f"the {lab['book'].lower()} book"}
    board(ctx)["book"] = data
    return ToolResult(summary=f"{lab['book']} book {period}: EAD SAR {ead:,.0f}m, reported ECL SAR {ecl:,.1f}m "
                              f"({figures['coverage_pct']:.2f}% coverage), {len(f):,} {lab['exposures'].lower()}",
                      figures=figures, data=data, rows_scanned=int(len(f)))


# ------------------------------------------------------------------ 2. scenarios

def design_scenarios(inputs: dict, ctx: ToolContext) -> ToolResult:
    domain = _domain(inputs, ctx)
    period = _period(domain, inputs, ctx)
    themes = [t for t in inputs.get("themes") or [] if t in calibrate.THEME_SERIES]
    segs = [s for s in inputs.get("segments") or [] if s]
    if not themes and not segs:
        themes = ["slowdown"]
    n = max(3, min(4, int(inputs.get("count") or 4)))
    designed = calibrate.graded(domain, themes, segs, n)
    vocab = _vocab(domain)
    out, figures = [], {}
    # The user's own sized shocks, when the goal named them, are kept as a scenario "as stated".
    stated = str(inputs.get("stated") or "").strip()
    if stated:
        r = language.read(stated, vocab)
        if r.steps:
            designed.append({"key": "stated", "name": "As stated in the goal", "grade": "As stated",
                             "steps": [{"shocks": s.shocks.to_dict(), "scope": s.scope.to_dict(), "restatement": s.restatement}
                                       for s in r.steps],
                             "sentence": "; ".join(s.restatement for s in r.steps),
                             "basis": [{"kind": "goal", "what": stated, "basis": "the shocks named in the goal"}], "horizon": 0})
    for sc in designed:
        # Read the plain-words definition back through the existing compound parser: the restatement the user
        # would get by typing it, and a check that the parser and the structured shocks agree.
        reading = language.read(sc["sentence"], vocab)
        parsed = [(s.shocks.to_dict(), s.scope.to_dict()) for s in reading.steps]
        wanted = [(parse_shocks(st["shocks"]).to_dict(), Scope.from_dict(st["scope"]).to_dict()) for st in sc["steps"]]
        sc["parser"] = {"restatement": [s.restatement for s in reading.steps], "agrees": parsed == wanted,
                        "unread": reading.unread}
        sc["period"] = period
        sc["domain"] = domain
        board(ctx)["scenarios"][sc["key"]] = sc
        if sc["key"] not in board(ctx)["order"]:
            board(ctx)["order"].append(sc["key"])
        figures[f"{sc['key']}:horizon"] = sc.get("horizon", 0)
        for st in sc["steps"]:
            for k, v in st["shocks"].items():
                if isinstance(v, (int, float)):
                    figures[f"{sc['key']}:{st['restatement']}:{k}"] = v
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, (int, float)):
                            figures[f"{sc['key']}:{st['restatement']}:{k}:{k2}"] = v2
        for b in sc["basis"]:
            for k, v in b.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    figures[f"{sc['key']}:{b['what']}:{k}"] = v
        out.append(sc)
    agree = sum(1 for s in out if s["parser"]["agrees"])
    figures["scenarios"] = len(out)
    figures["parser_agrees"] = agree
    return ToolResult(summary=f"{len(out)} scenarios of graded severity ({', '.join(s['grade'] for s in out)}); "
                              f"the compound parser reads {agree} of {len(out)} back exactly",
                      figures=figures, data={"scenarios": out, "themes": themes, "segments": segs})


def scenario_obj(sc: dict[str, Any], cohort_id: str = "", extra: list[Step] | None = None) -> Scenario:
    steps = [Step(instruction=st["restatement"], restatement=st["restatement"], shocks=parse_shocks(st["shocks"]),
                  scope=Scope.from_dict(st["scope"])) for st in sc["steps"]]
    return Scenario(domain=sc["domain"], period=sc["period"], steps=steps + list(extra or []), name=sc["name"],
                    cohort_id=cohort_id)


def _attributions(res: dict[str, Any]) -> dict[str, Any]:
    drivers = [{"driver": b["key"], "label": b["label"], "value": b["value"]}
               for b in res["waterfall"] if b["kind"] == "driver" and b.get("active")]
    segs = sorted(({"segment": r["segment"], "change": r["change"], "ecl_before": r["ecl_before"],
                    "ecl_after": r["ecl_after"]} for r in res["by_segment"]), key=lambda r: -r["change"])
    c = res["cards"]
    stage = {"before": c["stage_before"], "after": c["stage_after"], "ead_before": c["stage_ead_before"],
             "ead_after": c["stage_ead_after"], "moves": c["moves"]}
    return {"drivers": drivers, "segments": segs, "stage": stage}


def _run_figures(res: dict[str, Any], lik: dict[str, Any], attr: dict[str, Any]) -> dict[str, Any]:
    c = res["cards"]
    f = {k: c[k] for k in ("reported_ecl", "start_ecl", "scenario_ecl", "change", "change_pct", "coverage_before",
                           "coverage_after", "rwa_before", "rwa_after", "capital_cet1_before_pct",
                           "capital_cet1_after_pct", "capital_impact", "ead_before", "ead_after")}
    f["coverage_change_bps"] = (c["coverage_after"] - c["coverage_before"]) * 100
    f["stage2_after"] = c["stage_after"]["2"]
    f["stage3_after"] = c["stage_after"]["3"]
    f["stage2_before"] = c["stage_before"]["2"]
    f["moves_1_2"] = c["moves"]["1->2"]
    f["moves_2_3"] = c["moves"]["2->3"]
    f["moves_1_3"] = c["moves"]["1->3"]
    f["stage2_ead_after"] = c["stage_ead_after"]["2"]
    f["likelihood_level"] = lik.get("level", 0)
    for d in attr["drivers"]:
        f[f"driver:{d['driver']}"] = d["value"]
    for s in attr["segments"][:5]:
        f[f"segment:{s['segment']}"] = s["change"]
    return f


def run_scenario(inputs: dict, ctx: ToolContext) -> ToolResult:
    key = str(inputs.get("scenario") or "")
    method = str(inputs.get("method") or ctx.context.get("method") or "delta")
    if method not in runner.METHODS:
        raise ValueError(f"{method} is not a What-If method.")
    b = board(ctx)
    sc = b["scenarios"].get(key)
    if sc is None:
        raise KeyError(f"Scenario {key!r} has not been designed in this run.")
    obj = scenario_obj(sc, _cohort(ctx))
    t0 = time.time()
    res = runner.run(obj, method)
    lik = likelihood.assess(scenario_obj(sc, _cohort(ctx)))
    attr = _attributions(res)
    figures = _run_figures(res, lik, attr)
    for s in attr["segments"]:
        figures[f"segment:{s['segment']}"] = s["change"]
    from backend.whatif_v5.chat.orchestrator import slim
    data = {"scenario_key": key, "name": sc["name"], "grade": sc["grade"], "method": method,
            "method_name": METHOD_NAMES[method], "scenario": obj.to_dict(), "run_id": res["run_id"],
            "result": slim(res), "likelihood": lik, "attribution": attr, "basis": sc["basis"],
            "sentence": sc["sentence"], "seconds": round(time.time() - t0, 2)}
    b["runs"][f"{key}:{method}"] = data
    c = res["cards"]
    return ToolResult(summary=f"{sc['name']} ({METHOD_NAMES[method]}): ECL SAR {c['start_ecl']:,.1f}m -> "
                              f"{c['scenario_ecl']:,.1f}m ({c['change_pct']:+.1f}%), CET1 {c['capital_cet1_after_pct']:.2f}%; "
                              f"{lik.get('label', '')}",
                      figures=figures, data=data, rows_scanned=int(c["exposures"]), trace_id=res["run_id"])


# ------------------------------------------------------------------ 3. management actions

ACTIONS = {
    "limit_cut": "Cut undrawn limits in the most affected {segment_word}",
    "cash_margin": "Raise cash margins on weaker names in the most affected {segment_word}",
    "no_new_money": "Stop new money below {floor}",
    "collateral_top": "Add collateral on the top {n} exposures by ECL increase",
    "package": "All four actions together",
}
DEFAULT_SIZE = {"limit_cut": 25.0, "cash_margin": 10.0, "collateral_top": 25.0, "no_new_money": 100.0}


def _floor(domain: str) -> tuple[str, list[str]]:
    """The grades below the new-money floor: corporate below B+; retail score bands D and E."""
    if domain == "corporate":
        order = list(ratings.RATING_ORDER)
        i = order.index("B+")
        return "B+", [g for g in order[i + 1:] if g != "D"]
    return "band C", ["D", "E"]


def _weak(domain: str) -> list[str]:
    if domain == "corporate":
        order = list(ratings.RATING_ORDER)
        return [g for g in order[order.index("BB-"):] if g != "D"]
    return ["C", "D", "E"]


def action_steps(action: str, ref: dict[str, Any], domain: str, size: float | None, n_top: int = 10,
                 n_seg: int = 1, segments: list[str] | None = None) -> tuple[list[Step], dict[str, Any]]:
    """The action as What-If steps, targeted from the reference run (or the goal's own segments), and its definition."""
    attr = ref["attribution"]
    top_segs = list(segments or []) or [s["segment"] for s in attr["segments"] if s["change"] > 0][:max(1, n_seg)]
    seg_word = runner.LABELS[domain]["segment"].lower()
    book = dstore.frame(domain, ref["result"]["period"])
    if action == "limit_cut":
        x = float(size if size is not None else DEFAULT_SIZE[action])
        sh = {"ccf": {"mode": "relative", "value": -x}}
        if not segments:
            # A limit cut only bites where undrawn commitment counts in EAD (CCF > 0): the most affected such segment.
            und = (book["ccf"] * book["undrawn"]).groupby(book["segment"]).sum()     # the undrawn that counts in EAD
            ranked = [s["segment"] for s in attr["segments"] if s["change"] > 0 and float(und.get(s["segment"], 0.0)) > 0]
            top_segs = ranked[:max(1, n_seg)] or top_segs
        scope = {"segments": top_segs}
        what = f"Cut undrawn limits by {x:g}% in {', '.join(top_segs)} (drawn balances unchanged)"
        defn = {"lever": f"undrawn limit -{x:g}%", "size": x, "targets": top_segs,
                "basis": f"the {seg_word} with the largest ECL increase in the reference run"}
    elif action == "cash_margin":
        x = float(size if size is not None else DEFAULT_SIZE[action])
        lgd_u = engine.unsecured_lgd(domain, book)
        dlgd = -round(x * lgd_u, 2)
        sh = {"lgd": {"mode": "pp", "value": dlgd}}
        scope = {"segments": top_segs[:3] if len(top_segs) > 1 else top_segs, "grades": _weak(domain)}
        what = (f"Cash margin of {x:g}% of EAD on {', '.join(scope['grades'][:1])} and worse in {', '.join(scope['segments'])}: "
                f"LGD {dlgd:+g}pp")
        defn = {"lever": f"cash margin {x:g}% of EAD", "size": x, "lgd_unsecured_pct": lgd_u * 100, "lgd_pp": dlgd,
                "targets": scope["segments"], "grades": scope["grades"],
                "basis": f"cash replaces {x:g}% of the exposure that would lose the unsecured LGD ({lgd_u * 100:.0f}%, "
                         "the engine's unsecured LGD); cash loses nothing"}
    elif action == "no_new_money":
        floor, grades = _floor(domain)
        sh = {"ccf": {"mode": "pp", "value": -100.0}}
        scope = {"grades": grades, **({"segments": list(segments)} if segments else {})}
        what = (f"No new money below {floor}: undrawn commitments of {grades[0]} and worse cancelled"
                + (f" in {', '.join(segments)}" if segments else ""))
        defn = {"lever": f"no new money below {floor}", "size": 100.0, "grades": grades,
                "basis": "undrawn commitments cannot be drawn (CCF to zero); drawn balances unchanged"}
    elif action == "collateral_top":
        x = float(size if size is not None else DEFAULT_SIZE[action])
        secured = set(book.loc[book["collateral_value"] > 0, "exposure_id"].astype(str))
        movers = [x for x in ref["result"].get("top_movers") or []
                  if (not segments or x["segment"] in segments) and x["exposure_id"] in secured]
        ids = [m["exposure_id"] for m in movers[:n_top]]
        sh = {"collateral": x}
        scope = {"exposures": ids}
        what = f"Collateral +{x:g}% on the top {len(ids)} {runner.LABELS[domain]['exposures'].lower()} by ECL increase"
        defn = {"lever": f"collateral +{x:g}% of market value", "size": x, "targets": ids,
                "basis": "the secured exposures with the largest ECL increase in the reference run"}
    else:
        raise ValueError(f"{action} is not a management action.")
    st = Step(instruction=what, restatement=what, shocks=parse_shocks(sh), scope=Scope.from_dict(scope))
    defn.update({"action": action, "what": what, "shocks": sh, "scope": scope})
    return [st], defn


def test_action(inputs: dict, ctx: ToolContext) -> ToolResult:
    action = str(inputs.get("action") or "")
    on = str(inputs.get("on") or "severe")
    method = str(inputs.get("method") or "delta")
    b = board(ctx)
    ref = b["runs"].get(f"{on}:{method}")
    if ref is None:
        raise KeyError(f"The reference scenario {on!r} has not been run with the {method} method.")
    sc = b["scenarios"][on]
    domain = sc["domain"]
    size = inputs.get("size")
    size = float(size) if size not in (None, "") else None
    segs = [x for x in inputs.get("segments") or [] if x]
    if action == "package":
        steps, defs = [], []
        for a in ("limit_cut", "cash_margin", "no_new_money", "collateral_top"):
            s, d = action_steps(a, ref, domain, None, segments=segs)
            steps += s
            defs.append(d)
        defn = {"action": "package", "what": "All four actions together: " + "; ".join(d["what"] for d in defs),
                "parts": defs}
    else:
        steps, defn = action_steps(action, ref, domain, size, segments=segs)
    obj = scenario_obj(sc, _cohort(ctx), steps)
    res = runner.run(obj, method)
    c, r = res["cards"], ref["result"]["cards"]
    eff = {"ecl_effect": c["scenario_ecl"] - r["scenario_ecl"],
           "ecl_effect_pct": (c["scenario_ecl"] - r["scenario_ecl"]) / r["scenario_ecl"] * 100 if r["scenario_ecl"] else 0.0,
           "capital_effect": c["capital_impact"] - r["capital_impact"],
           "cet1_effect_pp": c["capital_cet1_after_pct"] - r["capital_cet1_after_pct"],
           "rwa_effect": c["rwa_after"] - r["rwa_after"], "ead_effect": c["ead_after"] - r["ead_after"],
           "stage2_effect": c["stage_after"]["2"] - r["stage_after"]["2"]}
    figures = {**eff, "scenario_ecl": c["scenario_ecl"], "change": c["change"], "capital_cet1_after_pct": c["capital_cet1_after_pct"],
               "capital_impact": c["capital_impact"], "rwa_after": c["rwa_after"], "ead_after": c["ead_after"],
               "reference_ecl": r["scenario_ecl"], "reference_cet1_pct": r["capital_cet1_after_pct"],
               "coverage_after": c["coverage_after"], "stage2_after": c["stage_after"]["2"]}
    for k in ("size", "lgd_pp", "lgd_unsecured_pct"):
        if isinstance(defn.get(k), (int, float)):
            figures[f"lever_{k}"] = defn[k]
    for i, p in enumerate(defn.get("parts", [])):
        for k in ("size", "lgd_pp", "lgd_unsecured_pct"):
            if isinstance(p.get(k), (int, float)):
                figures[f"part{i}_{k}"] = p[k]
    if defn.get("targets") and action == "collateral_top":
        figures["targets_n"] = len(defn["targets"])
    from backend.whatif_v5.chat.orchestrator import slim
    data = {"action": action, "on": on, "method": method, "definition": defn, "effects": eff,
            "scenario": obj.to_dict(), "run_id": res["run_id"], "result": slim(res), "reference_run_id": ref["run_id"],
            "attribution": _attributions(res)}
    b["actions"][f"{action}:{on}:{method}"] = data
    return ToolResult(summary=f"{defn['what']}: ECL {eff['ecl_effect']:+,.1f}m against {sc['name']}, capital "
                              f"{eff['capital_effect']:+,.1f}m, CET1 {eff['cet1_effect_pp']:+.2f}pp",
                      figures=figures, data=data, rows_scanned=int(c["exposures"]), trace_id=res["run_id"])


# ------------------------------------------------------------------ 4. overlay and comparison

def _scoped_change(run: dict[str, Any], segments: list[str]) -> float:
    if not segments:
        return float(run["result"]["cards"]["change"])
    return float(sum(r["change"] for r in run["result"]["by_segment"] if r["segment"] in segments))


def size_overlay(inputs: dict, ctx: ToolContext) -> ToolResult:
    """Overlay range from the runs: low = the plausible (moderate) scenario's ECL increase (the lower of the two methods
    when both ran), high = the severe scenario's (the higher of the two methods when both ran); point = the midpoint.
    In scope: the named segments' ECL change, else the whole population's."""
    b = board(ctx)
    segs = [s for s in inputs.get("segments") or [] if s]
    low_key, high_key = str(inputs.get("low") or "moderate"), str(inputs.get("high") or "severe")
    lows = {m: _scoped_change(b["runs"][f"{low_key}:{m}"], segs) for m in runner.METHODS if f"{low_key}:{m}" in b["runs"]}
    highs = {m: _scoped_change(b["runs"][f"{high_key}:{m}"], segs) for m in runner.METHODS if f"{high_key}:{m}" in b["runs"]}
    if not lows or not highs:
        raise KeyError("The overlay needs the moderate and severe runs.")
    low, high = min(lows.values()), max(highs.values())
    lo_m, hi_m = min(lows, key=lows.get), max(highs, key=highs.get)
    pkg = b["actions"].get(f"package:{high_key}:delta")
    high_after = _scoped_change({"result": {"cards": {"change": pkg["result"]["cards"]["change"]},
                                            "by_segment": pkg["result"]["by_segment"]}}, segs) if pkg else None
    ref = b["runs"][f"{low_key}:{lo_m}"]["result"]
    ead = float(sum(r["ead_before"] for r in ref["by_segment"] if r["segment"] in segs)) if segs else float(ref["cards"]["ead_before"])
    start = float(sum(r["ecl_before"] for r in ref["by_segment"] if r["segment"] in segs)) if segs else float(ref["cards"]["start_ecl"])
    point = (low + high) / 2
    figures = {"overlay_low": low, "overlay_high": high, "overlay_point": point,
               "overlay_low_bps": low / ead * 1e4 if ead else 0.0, "overlay_high_bps": high / ead * 1e4 if ead else 0.0,
               "overlay_point_bps": point / ead * 1e4 if ead else 0.0, "scope_ead": ead, "scope_ecl": start,
               "overlay_point_pct_of_ecl": point / start * 100 if start else 0.0}
    for m, v in lows.items():
        figures[f"low_{m}"] = v
    for m, v in highs.items():
        figures[f"high_{m}"] = v
    if high_after is not None:
        figures["overlay_high_after_actions"] = high_after
        figures["actions_relief"] = high - high_after
    lik = {k: b["runs"][f"{k}:delta"]["likelihood"].get("label", "") for k in (low_key, high_key) if f"{k}:delta" in b["runs"]}
    data = {**figures, "low_scenario": low_key, "high_scenario": high_key, "low_method": lo_m, "high_method": hi_m,
            "segments": segs, "likelihood": lik,
            "rule": ("low = the ECL increase of the moderate (historically plausible) scenario, the lower of the methods run; "
                     "high = the ECL increase of the severe (worst observed) scenario, the higher of the methods run; "
                     "point = the midpoint" + ("; in scope: " + ", ".join(segs) if segs else ""))}
    b["overlay"] = data
    return ToolResult(summary=f"Overlay range SAR {low:,.1f}m to {high:,.1f}m (point {point:,.1f}m, "
                              f"{figures['overlay_point_bps']:.0f}bps of EAD)", figures=figures, data=data)


def compare(inputs: dict, ctx: ToolContext) -> ToolResult:
    b = board(ctx)
    rows: list[dict[str, Any]] = []
    figures: dict[str, Any] = {}
    for key in b["order"]:
        for m in runner.METHODS:
            run = b["runs"].get(f"{key}:{m}")
            if not run:
                continue
            c = run["result"]["cards"]
            rows.append({"row": f"{run['name']}" + (" (XGBoost)" if m == "xgboost" else ""), "kind": "Scenario",
                         "ecl_after": c["scenario_ecl"], "ecl_change": c["change"], "ecl_change_pct": c["change_pct"],
                         "coverage_after_pct": c["coverage_after"], "stage2_after": c["stage_after"]["2"],
                         "cet1_after_pct": c["capital_cet1_after_pct"], "capital_impact": c["capital_impact"],
                         "likelihood": run["likelihood"].get("label", "")})
    for k, a in b["actions"].items():
        c = a["result"]["cards"]
        e = a["effects"]
        rows.append({"row": a["definition"]["what"] if a["action"] != "package" else "All four actions together",
                     "kind": f"Action ({b['scenarios'][a['on']]['grade'].lower()})", "ecl_after": c["scenario_ecl"],
                     "ecl_change": c["change"], "ecl_change_pct": c["change_pct"], "coverage_after_pct": c["coverage_after"],
                     "stage2_after": c["stage_after"]["2"], "cet1_after_pct": c["capital_cet1_after_pct"],
                     "capital_impact": c["capital_impact"], "action_ecl_effect": e["ecl_effect"],
                     "action_capital_effect": e["capital_effect"], "likelihood": ""})
    for i, r in enumerate(rows):
        for k, v in r.items():
            if isinstance(v, (int, float)):
                figures[f"r{i}:{k}"] = v
    b["comparison"] = rows
    return ToolResult(summary=f"{len(rows)} rows: {sum(1 for r in rows if r['kind'] == 'Scenario')} scenario runs and "
                              f"{sum(1 for r in rows if r['kind'] != 'Scenario')} management actions",
                      figures=figures, data={"rows": rows})


# ------------------------------------------------------------------ registration

def _avail() -> tuple[bool, str]:
    try:
        dstore.periods("corporate")
        return True, ""
    except dstore.DomainError as e:
        return False, f"the What-If domain is not built on this host ({e})"


OBJ = {"type": "object"}
TOOLS = [
    Tool("whatif_book_profile", MODULE, "The population in scope: EAD, reported ECL, coverage, stage mix and the largest "
         "segments (What-If domain, read-only).",
         {**OBJ, "properties": {"domain": {"type": "string", "enum": ["corporate", "retail"]}, "period": {"type": "string"},
                                "segments": {"type": "array", "items": {"type": "string"}}}}, READ_ONLY, book_profile,
         _avail, "backend.whatif_v5.domain.store.frame"),
    Tool("whatif_design_scenarios", MODULE, "Design 3-4 scenarios of graded severity (Mild, Moderate, Severe, Tail) for themes "
         "(oil, slowdown, rates, real_estate, unemployment) and/or named segments; every shock size comes from history, "
         "with its basis; each is read back through the What-If compound parser.",
         {**OBJ, "properties": {"domain": {"type": "string"}, "themes": {"type": "array", "items": {"type": "string"}},
                                "segments": {"type": "array", "items": {"type": "string"}},
                                "count": {"type": "integer", "minimum": 3, "maximum": 4},
                                "stated": {"type": "string", "description": "the goal's own sized shocks, if any"}}},
         READ_ONLY, design_scenarios, _avail, "backend.agents_v5.whatif.calibrate + backend.whatif_v5.chat.language.read"),
    Tool("whatif_run_scenario", MODULE, "Run one designed scenario with the Delta method or XGBoost (the What-If engine), "
         "assess its likelihood on history and attribute the ECL change by driver, segment and stage.",
         {**OBJ, "properties": {"scenario": {"type": "string"}, "method": {"type": "string", "enum": ["delta", "xgboost"]}},
          "required": ["scenario"]}, READ_ONLY, run_scenario, _avail, "backend.whatif_v5.models.runner.run"),
    Tool("whatif_test_action", MODULE, "Test a management action as a further run on top of a scenario: limit_cut, cash_margin, "
         "no_new_money, collateral_top or package (all four). Returns its ECL and capital effect.",
         {**OBJ, "properties": {"action": {"type": "string", "enum": list(ACTIONS)}, "on": {"type": "string"},
                                "size": {"type": "number"}, "method": {"type": "string"},
                                "segments": {"type": "array", "items": {"type": "string"}}}, "required": ["action"]},
         READ_ONLY, test_action, _avail, "backend.whatif_v5.models.runner.run"),
    Tool("whatif_size_overlay", MODULE, "Size the management overlay range from the scenario runs (moderate to severe), "
         "with the effect of the management actions.",
         {**OBJ, "properties": {"segments": {"type": "array", "items": {"type": "string"}}, "low": {"type": "string"},
                                "high": {"type": "string"}}}, READ_ONLY, size_overlay, _avail, "the runs of this agent run"),
    Tool("whatif_compare", MODULE, "Compare every scenario and management action of this run in one table.",
         {**OBJ, "properties": {}}, READ_ONLY, compare, _avail, "the runs of this agent run"),
]


def register() -> None:
    for t in TOOLS:
        register_tool(t)


__all__ = ["ACTIONS", "BOARD", "TOOLS", "action_steps", "board", "register", "scenario_obj"]
