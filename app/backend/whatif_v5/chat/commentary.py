"""The AI commentary on a result: brief, and every figure in it must be in the evidence.

The deterministic commentary is always built. When the assistant model is
available it is asked for a short commentary from the same evidence packet;
every number in its text is checked against the packet (5318's
`narrative.check`), and if any is not there the deterministic text is
published instead, with the reason recorded.
"""
from __future__ import annotations

import re
from typing import Any

from backend.v5common import emphasis
from backend.whatif_v5.chat import provider
from backend.whatif_v5.models.scenario import DRIVER_LABELS


def money(v: float) -> str:
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1000:
        return f"{sign}SAR {a / 1000:,.2f}bn"
    if a >= 1:
        return f"{sign}SAR {a:,.1f}m"
    return f"{sign}SAR {a * 1000:,.0f}k"


def packet(result: dict[str, Any], likelihood: dict[str, Any] | None) -> dict[str, Any]:
    c = result["cards"]
    drivers = [b for b in result["waterfall"] if b["kind"] == "driver" and b.get("active") and abs(b["value"]) >= 0.05]
    drivers.sort(key=lambda b: -abs(b["value"]))
    change = c["change"]
    return {
        "scenario": [s["restatement"] for s in result["steps"]],
        "population": result["population"]["label"],
        "method": result["method_name"],
        "reported_ecl": money(c["reported_ecl"]), "start_ecl": money(c["start_ecl"]),
        "model_error_pct": round(c["model_error_pct"], 2),
        "scenario_ecl": money(c["scenario_ecl"]), "change": money(change), "change_pct": round(c["change_pct"], 1),
        "drivers": [{"driver": b["label"], "amount": money(b["value"]),
                     "share_pct": round(b["value"] / change * 100, 1) if change else 0.0} for b in drivers],
        "stage_moves": c["moves"],
        "coverage_before_pct": round(c["coverage_before"], 2), "coverage_after_pct": round(c["coverage_after"], 2),
        "cet1_after_pct": round(c["capital_cet1_after_pct"], 2),
        "top_segments": [{"segment": r["segment"], "change": money(r["change"])} for r in
                         sorted(result["by_segment"], key=lambda r: -r["change"]) if abs(r["change"]) >= 0.05][:3],
        "likelihood": (likelihood or {}).get("label", ""),
    }


def deterministic(result: dict[str, Any], likelihood: dict[str, Any] | None) -> str:
    p = packet(result, likelihood)
    c = result["cards"]
    scen = "; ".join(p["scenario"])
    parts = [f"**Scenario.** {scen[:1].upper() + scen[1:]}, applied to {p['population']}."]
    direction = "rises" if c["change"] > 0 else "falls" if c["change"] < 0 else "does not move"
    parts.append(f"**ECL.** Under the {p['method']}, ECL {direction} from {p['start_ecl']} to {p['scenario_ecl']} "
                 f"({p['change_pct']:+.1f}%, {p['change']}). Coverage moves from {p['coverage_before_pct']:.2f}% to "
                 f"{p['coverage_after_pct']:.2f}%.")
    if p["drivers"]:
        lead = p["drivers"][0]
        rest = ", ".join(f"{d['driver']} {d['amount']}" for d in p["drivers"][1:4])
        parts.append(f"**What drove it.** {lead['driver']} contributes {lead['amount']} ({lead['share_pct']:.0f}% of the "
                     f"change)" + (f"; then {rest}." if rest else ".")
                     + " The bars are exact Shapley values and add up to the change.")
    mv = c["moves"]
    moved = mv["1->2"] + mv["1->3"] + mv["2->3"]
    if moved:
        parts.append(f"**Staging.** {mv['1->2']:,} move from Stage 1 to 2, {mv['2->3']:,} from 2 to 3 and "
                     f"{mv['1->3']:,} from 1 to 3 under the SICR rules.")
    if abs(c["model_error"]) > 1e-9:
        parts.append(f"**Model note.** The {p['method']} recomputes the starting ECL at {p['start_ecl']} against "
                     f"{p['reported_ecl']} reported ({p['model_error_pct']:+.2f}%); the change is measured from its own start.")
    if p["top_segments"] and c["change"]:
        parts.append("**Where.** Largest increases: " + ", ".join(f"{s['segment']} {s['change']}" for s in p["top_segments"]) + ".")
    if p["likelihood"]:
        parts.append(f"**Likelihood.** {p['likelihood']} (see below).")
    return "\n\n".join(parts)


def _numbers(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?", text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def check(text: str, pkt: dict[str, Any]) -> list[float]:
    """Numbers in `text` that are not in the evidence packet (at 0-3 dp, +-0.5%); small integers allowed."""
    allowed: list[float] = []
    for n in _numbers(repr(pkt)):
        allowed.append(n)
    bad = []
    for n in _numbers(text):
        if abs(n) <= 10 and float(n).is_integer():
            continue
        if any(abs(n - a) <= max(0.005 * abs(a), 0.05) for a in allowed):
            continue
        bad.append(n)
    return bad


TOOL = {"name": "write_commentary", "description": "Write the brief commentary on a What-If result.",
        "input_schema": {"type": "object", "required": ["paragraphs"], "properties": {
            "paragraphs": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}}}}}
SYSTEM = ("You are the What-If assistant in a bank's credit-risk system. Write a brief commentary (at most 130 words, "
          "2-5 short paragraphs) on an IFRS 9 scenario result: what the scenario is, how ECL moved, which components "
          "drove it (the Shapley drivers), and the staging effect. Use ONLY figures that appear in the evidence, "
          "written exactly as there. No recommendations about provisions. Plain English for a credit committee. "
          + emphasis.RULE)


def commentary(result: dict[str, Any], likelihood: dict[str, Any] | None) -> dict[str, Any]:
    det = deterministic(result, likelihood)
    pkt = packet(result, likelihood)
    if not provider.available():
        return {"text": emphasis.emphasise(det), "source": "deterministic"}
    import json
    got = provider.structured("commentary", SYSTEM, "Evidence:\n" + json.dumps(pkt, indent=1), TOOL)
    if not got or not got.get("paragraphs"):
        return {"text": emphasis.emphasise(det), "source": "deterministic", "note": "The assistant model did not answer in time."}
    text = "\n\n".join(str(p) for p in got["paragraphs"])
    bad = check(text, pkt)
    if bad:
        return {"text": det, "source": "deterministic",
                "note": f"The model's commentary used figures not in the evidence ({', '.join(f'{b:g}' for b in bad[:4])}); "
                        "the checked commentary is shown instead."}
    return {"text": emphasis.emphasise(text), "source": "model", "model": provider.model_id()}


_ = DRIVER_LABELS
