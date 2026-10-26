"""The ECL committee note and the run narrative (W2): every figure cites the step that computed it.

The note is written from the steps' outputs only. Each figure is printed next to its step id ([S4]); the runtime's
citation check (`runtime.citations.check`) must pass on the whole note, not only on the narrative (tested).
"""
from __future__ import annotations

from typing import Any

from backend.agents_v5.runtime.types import DONE, Run, Step
from backend.whatif_v5 import capital


def m(v: float, dec: int = 1) -> str:
    return f"SAR {v:,.{dec}f}m"


def sm(v: float, dec: int = 1) -> str:
    return f"{'+' if v >= 0 else '-'}SAR {abs(v):,.{dec}f}m"


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def period_label(p: str) -> str:
    """2026Q2 stays; 2026-08 reads Aug 2026 (a month number is not a figure)."""
    if len(p) == 7 and p[4] == "-" and p[5:].isdigit():
        return f"{MONTHS[int(p[5:]) - 1]} {p[:4]}"
    return p


def steps(run: Run, tool: str) -> list[Step]:
    return [s for s in (run.plan.steps if run.plan else []) if s.tool == tool and s.status == DONE]


def index(run: Run) -> dict[str, Any]:
    """The run's outputs by role, each with its step id."""
    out: dict[str, Any] = {"book": None, "design": None, "runs": {}, "actions": {}, "overlay": None, "compare": None}
    for s in run.plan.steps if run.plan else []:
        if s.status != DONE or not isinstance(s.output, dict):
            continue
        if s.tool == "whatif_book_profile":
            out["book"] = (s, s.output)
        elif s.tool == "whatif_design_scenarios":
            out["design"] = (s, s.output)
        elif s.tool == "whatif_run_scenario":
            out["runs"][f"{s.output['scenario_key']}:{s.output['method']}"] = (s, s.output)
        elif s.tool == "whatif_test_action":
            out["actions"][f"{s.output['action']}:{s.output['on']}:{s.output['method']}"] = (s, s.output)
        elif s.tool == "whatif_size_overlay":
            out["overlay"] = (s, s.output)
        elif s.tool == "whatif_compare":
            out["compare"] = (s, s.output)
    return out


def _order(ix: dict[str, Any]) -> list[str]:
    if ix["design"]:
        return [sc["key"] for sc in ix["design"][1]["scenarios"]]
    return sorted({k.split(":")[0] for k in ix["runs"]})


def headline(run: Run, ix: dict[str, Any], kind: str) -> str:
    ov = ix["overlay"]
    sev = ix["runs"].get("severe:delta")
    mod = ix["runs"].get("moderate:delta")
    if kind == "overlay" and ov:
        s, o = ov
        return (f"A management overlay of {m(o['overlay_low'])} to {m(o['overlay_high'])} is defensible, "
                f"point {m(o['overlay_point'])} ({o['overlay_point_bps']:.0f}bps of {', '.join(o['segments']) + ' ' if o['segments'] else ''}EAD) [{s.id}].")
    if kind == "provision_adequacy" and mod and sev:
        (s1, a), (s2, b) = mod, sev
        return (f"Reported ECL of {m(a['result']['cards']['reported_ecl'])} covers the base case; the moderate scenario "
                f"needs {sm(a['result']['cards']['change'])} more [{s1.id}] and the severe one "
                f"{sm(b['result']['cards']['change'])} [{s2.id}].")
    if sev:
        s, b = sev
        c = b["result"]["cards"]
        return (f"The severe case raises ECL by {sm(c['change'])} ({c['change_pct']:+.1f}%) and takes CET1 to "
                f"{c['capital_cet1_after_pct']:.2f}% [{s.id}].")
    return "The scenario set is complete."


def committee_note(run: Run, kind: str, goal_text: str) -> str:
    ix = index(run)
    L: list[str] = []
    L.append("### ECL committee note")
    L.append(f"*Goal:* {goal_text.strip()}")
    L.append("")
    L.append("**Answer.** " + headline(run, ix, kind))
    if ix["book"]:
        s, b = ix["book"]
        L.append("")
        L.append(f"**Population.** {b['population'].capitalize()} at {period_label(b['period'])}: EAD {m(b['ead'], 0)}, reported ECL "
                 f"{m(b['ecl'])}, coverage {b['coverage_pct']:.2f}% [{s.id}].")
    if ix["design"]:
        s, d = ix["design"]
        L.append("")
        L.append(f"**Scenarios.** {len(d['scenarios'])} scenarios of graded severity, every shock sized from history [{s.id}]:")
        for sc in d["scenarios"]:
            basis = "; ".join(b["basis"] for b in sc["basis"] if b.get("basis"))
            L.append(f"- *{sc['name']}*: {sc['sentence']} [{s.id}]. Basis: {basis} [{s.id}].")
    order = _order(ix)
    if ix["runs"]:
        L.append("")
        L.append("**Results (Delta method).**")
        for key in order:
            hit = ix["runs"].get(f"{key}:delta")
            if not hit:
                continue
            s, r = hit
            c = r["result"]["cards"]
            L.append(f"- *{r['name']}*: ECL {m(c['start_ecl'])} to {m(c['scenario_ecl'])} ({sm(c['change'])}, "
                     f"{c['change_pct']:+.1f}%), coverage {c['coverage_before']:.2f}% to {c['coverage_after']:.2f}%, "
                     f"Stage 2 count {c['stage_before']['2']:,} to {c['stage_after']['2']:,}, CET1 "
                     f"{c['capital_cet1_after_pct']:.2f}%, capital needed {m(c['capital_impact'])}; "
                     f"{r['likelihood'].get('label', '').lower()} [{s.id}].")
    sev = ix["runs"].get("severe:delta")
    if sev:
        s, r = sev
        drv = sorted(r["attribution"]["drivers"], key=lambda d: -abs(d["value"]))[:3]
        seg = [x for x in r["attribution"]["segments"] if x["change"] > 0][:3]
        if drv:
            L.append("")
            L.append("**Drivers (severe).** " + ", ".join(f"{d['label']} {sm(d['value'])}" for d in drv)
                     + f"; largest increases in " + ", ".join(f"{x['segment']} ({sm(x['change'])})" for x in seg) + f" [{s.id}].")
    xm, dm = ix["runs"].get("moderate:xgboost"), ix["runs"].get("moderate:delta")
    if xm and dm:
        (sx, x), (sd, d) = xm, dm
        L.append("")
        L.append(f"**Model risk.** On the moderate scenario XGBoost moves ECL by {sm(x['result']['cards']['change'])} "
                 f"[{sx.id}] against {sm(d['result']['cards']['change'])} for the Delta method [{sd.id}].")
    if ix["actions"]:
        L.append("")
        L.append("**Management actions (on the severe scenario).**")
        for k, (s, a) in ix["actions"].items():
            e = a["effects"]
            what = a["definition"]["what"] if a["action"] != "package" else "All four actions together"
            L.append(f"- {what}: ECL {sm(e['ecl_effect'])}, capital {sm(e['capital_effect'])}, CET1 "
                     f"{e['cet1_effect_pp']:+.2f}pp [{s.id}].")
    if ix["overlay"]:
        s, o = ix["overlay"]
        L.append("")
        L.append(f"**Management overlay.** Range {m(o['overlay_low'])} to {m(o['overlay_high'])}, point "
                 f"{m(o['overlay_point'])} ({o['overlay_low_bps']:.0f} to {o['overlay_high_bps']:.0f}bps of EAD in scope) [{s.id}].")
        L.append(f"Rationale: the low end is the {o['low_scenario']} scenario ({o['likelihood'].get(o['low_scenario'], '').lower()}), "
                 f"the high end the {o['high_scenario']} scenario ({o['likelihood'].get(o['high_scenario'], '').lower()}); "
                 "the base ECL's macro paths do not carry either, so an overlay inside this range is supported by the runs.")
        if "overlay_high_after_actions" in o:
            L.append(f"With all four management actions the severe case needs {m(o['overlay_high_after_actions'])}, "
                     f"a relief of {m(o['actions_relief'])} [{s.id}].")
    L.append("")
    L.append("**Decision sought.** Approve the scenario set as the quarter's official sensitivity and note the overlay "
             "range; both are proposals in the approvals queue and nothing is booked until approved.")
    L.append("")
    L.append("**Limitations.** Capital is illustrative (an IRB foundation-style risk weight and an assumed CET1 ratio, "
             "not the bank's capital); horizons are a stated grading assumption; no peer data is on this build.")
    return "\n".join(L)


def narrative(run: Run, kind: str) -> str:
    """The run's short narrative (the drawer): the answer and the key figures, each cited."""
    ix = index(run)
    parts = [headline(run, ix, kind)]
    if ix["design"]:
        s, d = ix["design"]
        parts.append(f"{len(d['scenarios'])} graded scenarios were designed from history [{s.id}].")
    pkg = ix["actions"].get("package:severe:delta")
    if pkg:
        s, a = pkg
        parts.append(f"All four management actions together change the severe ECL by {sm(a['effects']['ecl_effect'])} "
                     f"and capital by {sm(a['effects']['capital_effect'])} [{s.id}].")
    if ix["overlay"] and kind != "overlay":
        s, o = ix["overlay"]
        parts.append(f"Overlay range {m(o['overlay_low'])} to {m(o['overlay_high'])} [{s.id}].")
    return " ".join(parts)


def limitations() -> list[str]:
    return capital.assumptions()


__all__ = ["committee_note", "headline", "index", "narrative"]
