"""One stress run over the selected structures (K20, K23 (2)-(3)): structures x mild / moderate / severe.

Each structure goes through the R12 Stress Lab ladder (`stress2.ladder.run`, which runs the R11 Lab and the engine),
never a copy of it, so every cell traces to dd_stress_result rows. A structure that fails before any stress (below
the hurdle, a hard limit, a base covenant breach or above capacity) is marked "fails before stress" and is stressed
only on request (`force`).

Survival at a severity: no applicable scenario of that severity (or milder) newly breaks DSCR (1.0 or its limit),
Debt/EBITDA against policy, LTV, a covenant, the minimum rating, Stage 1 or a hard limit. Stressed RAROC is shown in
every cell but is not a survival test: pricing is set at base and repriced at the next review (the margin ratchet
covers a downgrade). For the rating family, Stage 2 at the SICR notch count is the shock's own definition (ladder rule).
"""
from __future__ import annotations

import re

import hashlib
import json
import math
import threading
from typing import Any

from backend.dealdesk.stress2 import ladder
from backend.dealdesk.stressproof import adapters as AD
from backend.dealdesk.stressproof import interpret
from backend.dealdesk.stressproof import structures as ST

SEVERITIES = ("mild", "moderate", "severe")
SEV_RANK = {"none": -1, "mild": 0, "moderate": 1, "severe": 2}
SURVIVAL_TESTS = ("dscr", "debt_ebitda", "ltv", "covenants", "rating", "stage", "limits")
TEST_LABEL = {"dscr": "DSCR", "debt_ebitda": "Debt/EBITDA (policy)", "ltv": "LTV", "covenants": "Covenants", "rating": "Minimum rating",
              "stage": "Stage", "limits": "Hard limits", "raroc": "RAROC"}
_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _fin(v: Any) -> float | None:
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)


def sev_of(row: dict[str, Any]) -> str:
    s = row.get("severity")
    return s if s in SEVERITIES else "severe"


def survival_breaks(row: dict[str, Any]) -> list[str]:
    return [b for b in row.get("breaks") or [] if b in SURVIVAL_TESTS]


def regime_label_for(row: dict[str, Any], reg: dict[str, Any]) -> str:
    """In a high-oil supply-shock regime an oil fall is an oil reversal from today's level, not a fall from the average."""
    if reg.get("key") == "high_oil_supply_shock" and str(row.get("id", "")).startswith("oil_") and reg.get("brent"):
        try:
            mv = float(row["id"].split("_")[1])
        except (IndexError, ValueError):
            mv = None
        to = None if mv is None else reg["brent"] * (1 - mv / 100.0)
        return f"Oil reversal from USD {reg['brent']:,.0f}" + (f" to USD {to:,.0f}" if to else "")
    return plain_label(row)


_SCALE = re.compile(r"\s*\(×\s*([0-9.]+)\)\s*$")
_PCTL = re.compile(r"\b(P\d{2})\b")
_ODDS = re.compile(r"about (1 in \d+)")


def plain_label(row: dict[str, Any]) -> str:
    """R15 b (L8 (b)): "Own-sector slowdown (×0.64)" -> "Own-sector slowdown: 64% of the moderate shock (revenue −16.0%,
    receivable days +38; P75 of the sector's history, about 1 in 4)". The sizes come from the ladder's own step."""
    lab = str(row.get("label") or "")
    m = _SCALE.search(lab)
    if not m:
        return lab
    k = float(m.group(1))
    head = lab[: m.start()].rstrip()
    sizes = ""
    for st in row.get("steps") or []:
        disp = str(st.get("display") or "")
        if "receivable days" in disp or "revenue" in disp:
            sizes = disp.split(", margin")[0]
            break
    basis = str(row.get("basis") or "")
    pc, odds = _PCTL.search(basis), _ODDS.search(basis)
    hist = ""
    if pc:
        hist = f"{pc.group(1)} of the sector's history" + (f", about {odds.group(1)}" if odds else "")
    inner = "; ".join(x for x in (sizes, hist) if x)
    return f"{head}: {k * 100:.0f}% of the moderate shock" + (f" ({inner})" if inner else "")


def ladder_for(p: dict[str, Any], c: dict[str, Any], *, scenario_ids: list[str] | None = None, publish: bool = True) -> dict[str, Any]:
    q = ST.with_covenants(p, c.get("covenants"))
    key = hashlib.sha1(json.dumps([p["proposal_id"], c["terms"], c.get("covenants"), scenario_ids], sort_keys=True, default=str).encode()).hexdigest()
    with _LOCK:
        hit = _RUNS.get(key)
    if hit:
        return hit
    out = ladder.run(q, c["terms"], scenario_ids=scenario_ids, structure_label=c["label"], reverse=False, publish=publish, include_chain=False)
    with _LOCK:
        if len(_RUNS) > 200:
            _RUNS.clear()
        _RUNS[key] = out
    return out


def cell(rows: list[dict[str, Any]], sev: str, obligor: str = "") -> dict[str, Any]:
    at = [r for r in rows if r["applicable"] and sev_of(r) == sev]
    if not at:
        return {"severity": sev, "scenarios": 0, "passes": True, "breaking": [], "worst_raroc": None, "min_dscr": None,
                "min_covenant_headroom": None, "worst_stage": None, "limits": [], "first_break": None}
    br = [r for r in at if survival_breaks(r)]
    heads = [c["headroom"] for r in at for c in r.get("covenants") or [] if c.get("headroom") is not None and math.isfinite(c["headroom"])]
    limits = sorted({interpret.short_limit(x, obligor) for r in at for x in (r.get("limits") or {}).get("new_labels", [])})
    first = None
    if br:
        f = sorted(br, key=lambda r: (-len(survival_breaks(r)), r["label"]))[0]
        first = {"id": f["id"], "label": f.get("regime_label") or plain_label(f), "tests": survival_breaks(f),
                 "test_labels": [TEST_LABEL[t] for t in survival_breaks(f)]}
    return {"severity": sev, "scenarios": len(at), "passes": not br, "breaking": [r["id"] for r in br],
            "worst_raroc": min((_fin(r["metrics"]["lifetime_raroc"]) for r in at if _fin(r["metrics"]["lifetime_raroc"]) is not None), default=None),
            "min_dscr": min((_fin(r["metrics"]["dscr"]) for r in at if _fin(r["metrics"]["dscr"]) is not None), default=None),
            "min_covenant_headroom": min(heads) if heads else None,
            "worst_stage": max(int(r["metrics"]["stage"]) for r in at), "limits": limits, "first_break": first}


def survives_up_to(cells: list[dict[str, Any]]) -> str:
    best = "none"
    for c in cells:
        if not c["passes"]:
            break
        best = c["severity"]
    return best


def one(p: dict[str, Any], row: dict[str, Any], force: bool, reg: dict[str, Any]) -> dict[str, Any]:
    base = {"key": row["key"], "label": row["label"], "role": row["role"], "raroc": row["raroc"], "hurdle": row["hurdle"],
            "sva": row["sva"], "sva_basis": row["sva_basis"], "dscr": _fin(row["dscr"]), "covenant_headroom": row["covenant_headroom"],
            "capacity": row["capacity"], "approval": row["approval"], "fails_before_stress": row["fails_before_stress"],
            "base_reason": row["not_recommendable_reason"]}
    if row["fails_before_stress"] and not force:
        return {**base, "status": "fails_before_stress", "stressed": False, "cells": [], "survives_up_to": "none",
                "interpretation": interpret.not_stressed(row)}
    out = ladder_for(p, row)
    rows = out["rows"]
    for r in rows:
        r["regime_label"] = regime_label_for(r, reg)
    cells = [cell(rows, s, p["obligor"]["name"]) for s in SEVERITIES]
    up = survives_up_to(cells)
    v = out["verdict"]
    drivers = v.get("driver_labels") or []
    res = {**base, "status": "stressed", "stressed": True, "cells": cells, "survives_up_to": up, "run_id": out["run_id"],
           "verdict": v["verdict"], "tier": out["tier"]["tier"], "drivers": drivers,
           "scenarios": [{"id": r["id"], "label": r["regime_label"], "family": r["family"], "severity": sev_of(r), "applicable": r["applicable"],
                          "breaks": survival_breaks(r), "raroc": _fin(r["metrics"]["lifetime_raroc"]) if r["applicable"] else None,
                          "dscr": _fin(r["metrics"]["dscr"]) if r["applicable"] else None,
                          "stage": r["metrics"]["stage"] if r["applicable"] else None,
                          "debt_ebitda": _fin(r["metrics"].get("debt_ebitda")) if r["applicable"] else None,
                          "covenants": [{"type": c["type"], "value": _fin(c.get("value")), "threshold": c["threshold"], "headroom": _fin(c.get("headroom")),
                                         "status": c["status"]} for c in r.get("covenants") or []] if r["applicable"] else [],
                          "limits": [interpret.short_limit(x, p["obligor"]["name"]) for x in (r.get("limits") or {}).get("new_labels", [])] if r["applicable"] else [],
                          "na_reason": r.get("na_reason")} for r in rows],
           "sensitivity_version": out["sensitivity_version"], "forced": bool(row["fails_before_stress"] and force)}
    res["interpretation"] = interpret.structure(row, res, out)
    return res


def run(pid: str, keys: list[str] | None = None, force: list[str] | None = None) -> dict[str, Any]:
    """POST /proposals/{pid}/stress-matrix: {keys?, force?}; default = the selected structure and the ask."""
    s = ST.structure_set(pid)
    p = ST.deal(pid)
    reg = AD.regime()
    by = {r["key"]: r for r in s["rows"]}
    keys = [k for k in (keys or [s["selected"]] + (["ask"] if s["selected"] != "ask" else [])) if k in by]
    if not keys:
        raise KeyError("no structure")
    force = set(force or [])
    cols = [one(p, by[k], k in force, reg) for k in keys]
    sample = next((c for c in cols if c["stressed"]), None)
    drivers = []
    for c in cols:
        for d in c.get("drivers") or []:
            if d not in drivers:
                drivers.append(d)
    return {"proposal_id": pid, "obligor": s["obligor"], "keys": keys, "structures": cols, "severities": list(SEVERITIES),
            "regime": reg, "regime_line": AD.regime_line(reg), "drivers": drivers,
            "survival_rule": ("Survives a severity when no scenario of that severity or milder newly breaks DSCR, Debt/EBITDA against "
                              "policy, LTV, a covenant, the minimum rating, Stage 1 or a hard limit. Stressed RAROC is shown, not tested: "
                              "pricing is set at base."),
            "sensitivity_version": sample["sensitivity_version"] if sample else None,
            "plain_words": interpret.matrix_plain(cols, reg), "how_to_read": interpret.matrix_read(cols), "basis": "R12 Stress Lab ladder (stress2.ladder) on each structure; dd_stress_result rows per run."}


def first_break(res: dict[str, Any]) -> str:
    for c in res.get("cells") or []:
        if c["first_break"]:
            return f"{c['first_break']['label']} ({c['severity']}): {', '.join(c['first_break']['test_labels'])}"
    if res.get("status") == "fails_before_stress":
        return "Fails before stress: " + res.get("base_reason", "")
    return ""


def clear() -> None:
    with _LOCK:
        _RUNS.clear()

