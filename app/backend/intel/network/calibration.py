"""Mild / moderate / severe magnitudes for the event translator, and where they came from.

PLAN_R13 §S builds data-driven severities (origin/v5/r13-scenarios). When its calibrated table is present, the event
translator reads it; until then it uses the What-If engine's current calibration and says so in every answer:

- sector stress in cycle-index standard deviations: `backend.whatif_v5.chat.language.SEVERITY` (0.5 / 1 / 2);
- macro magnitudes (Brent, non-oil GDP, rates), rating notches, collateral and real-estate falls: the R12 stress
  ladder seed the What-If and Stress Lab share (`backend.dealdesk.stress2.catalogue.seed_ladder`).

§S (origin/v5/r13-scenarios) publishes its calibration to Data Domains as `dd_scenario_calibration` (one row per
driver and severity, adverse magnitudes); once merged it is read from there (`S_KEYS` maps §S drivers to the What-If
shock and its sign). An override for tests and what-ifs: R13_SEVERITIES (or a file at one of CANDIDATES) shaped
{"source": "...", "method": "...", "window": "...", "drivers": {"<driver>": {"mild": x, "moderate": y, "severe": z}}}
with signed What-If values, driver keys as in FALLBACK_KEYS.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from backend.intel.network.common import V5

LEVELS = ("mild", "moderate", "severe")
CANDIDATES = (
    "data/whatif_v5/scenarios/severities.json",
    "data/whatif_v5/scenarios/calibrated_severities.json",
    "var/whatif_v5/scenarios/severities.json",
)
#: driver -> (seed ladder shock key, unit, multiplier from the seed's unit to the What-If unit)
FALLBACK_KEYS: dict[str, tuple[str, str, float]] = {
    "brent": ("oil_pct", "% of the Brent level", 1.0),
    "gdp_nonoil": ("gdp_pct", "pp of non-oil GDP growth", 1.0),
    "repo": ("rate_bps", "bps", 1.0),
    "notches": ("notches", "rating notches", 1.0),
    "collateral": ("collateral_pct", "% of collateral value", 100.0),
    "re_price": ("real_estate_pct", "% of real-estate prices", 1.0),
    "payment_delay_days": ("receivable_days", "days", 1.0),
}


def _from_s() -> dict[str, Any] | None:
    env = os.environ.get("R13_SEVERITIES")
    paths = ([pathlib.Path(env)] if env else []) + [V5 / c for c in CANDIDATES]
    for p in paths:
        try:
            if p.is_file():
                doc = json.loads(p.read_text())
                if isinstance(doc.get("drivers"), dict):
                    doc.setdefault("path", p.relative_to(V5).as_posix() if p.is_relative_to(V5) else p.as_posix())
                    return doc
        except (OSError, ValueError):
            continue
    return _from_s_relation()


#: R13 §S driver key -> (IC driver key, sign that turns §S's adverse magnitude into the What-If shock)
S_KEYS: dict[str, tuple[str, float]] = {
    "brent": ("brent", -1.0), "gdp_nonoil": ("gdp_nonoil", -1.0), "saibor": ("repo", 1.0), "rating": ("notches", 1.0),
    "collateral": ("collateral", -1.0), "re_price": ("re_price", -1.0), "payment_delay": ("payment_delay_days", 1.0),
    "sector_cycle": ("sector_sd", 1.0),
}


def _s_rows() -> list[dict[str, Any]]:
    """R13 §S's published calibration (Data Domains: dd_scenario_calibration); empty until §S is merged."""
    try:
        from backend.dealdesk.data.store import dd_read
        return dd_read("dd_scenario_calibration")
    except Exception:  # noqa: BLE001 - the relation is registered only once §S merges
        return []


def _from_s_relation() -> dict[str, Any] | None:
    rows = _s_rows()
    if not rows:
        return None
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("driver") not in S_KEYS or r.get("severity") not in LEVELS:
            continue
        key, sign = S_KEYS[r["driver"]]
        d = by.setdefault(key, {"unit": r.get("unit"), "basis": f"R13 §S {r.get('method')} ({r.get('label')})",
                                "method": r.get("method"), "window": r.get("window"), "source": r.get("source"),
                                "fallback_reason": r.get("fallback_reason"), "evidence": {}})
        d[r["severity"]] = sign * float(r["value"])
        d["evidence"][r["severity"]] = {"percentile": r.get("percentile"), "n_obs": r.get("n_obs"),
                                        "freq_count": r.get("freq_count"), "freq_labels": list(r.get("freq_labels") or [])}
    by = {k: v for k, v in by.items() if all(lv in v for lv in LEVELS)}
    if not by:
        return None
    emp = sorted(k for k, v in by.items() if v["method"] == "empirical")
    fp = next((r.get("fingerprint") for r in rows if r.get("fingerprint")), None)
    return {"source": "R13 §S calibrated severities", "drivers": by, "path": "Data Domains: dd_scenario_calibration",
            "note": ("Severities from R13 §S (dd_scenario_calibration"
                     + (f", fingerprint {str(fp)[:12]}" if fp else "") + "): mild P75, moderate P92, severe max(P96, worst "
                     f"episode) of observed one-year moves for {', '.join(emp) or 'no driver'}; the other drivers carry §S's "
                     "labelled fallback (expert or regulatory) where the data cannot support a percentile.")}


def _fallback() -> dict[str, Any]:
    from backend.dealdesk.stress2.catalogue import seed_ladder
    from backend.whatif_v5.chat.language import SEVERITY

    ladder = seed_ladder()
    drivers: dict[str, dict[str, Any]] = {}
    for drv, (key, unit, mult) in FALLBACK_KEYS.items():
        vals = {}
        for r in ladder:
            if key in r["shocks"] and r["severity"] in LEVELS and r["family"] != "combined":
                vals[r["severity"]] = float(r["shocks"][key]) * mult
        if all(lv in vals for lv in LEVELS):
            drivers[drv] = {**vals, "unit": unit, "basis": f"R12 stress ladder seed ({key})"}
    drivers["sector_sd"] = {lv: float(SEVERITY[lv]) for lv in LEVELS}
    drivers["sector_sd"].update({"unit": "sd of the sector cycle index",
                                 "basis": "What-If language.SEVERITY"})
    return {"source": "whatif_current", "label": "What-If engine's current calibration",
            "note": ("§S calibrated severities are not available on this branch yet; these are the What-If engine's "
                     "current calibration (sector stress 0.5/1/2 sd) and the R12 stress ladder seed for macro, rating "
                     "and collateral magnitudes. They are expert values, not percentiles of history."),
            "path": "backend/whatif_v5/chat/language.py · backend/dealdesk/stress2/catalogue.py", "drivers": drivers}


def table() -> dict[str, Any]:
    s = _from_s()
    if s:
        fb = _fallback()["drivers"]
        drivers = {**fb, **{k: v for k, v in s["drivers"].items() if isinstance(v, dict) and all(lv in v for lv in LEVELS)}}
        return {"source": "r13_s", "label": s.get("source") or "R13 §S calibrated severities",
                "note": s.get("note") or ("Calibrated severities from R13 §S: " + str(s.get("method") or "empirical percentiles")
                                          + (f", data window {s['window']}" if s.get("window") else "") + "."),
                "path": s.get("path"), "drivers": drivers,
                "s_drivers": sorted(k for k in s["drivers"] if k in drivers)}
    return _fallback()


def magnitude(driver: str, severity: str, tab: dict[str, Any] | None = None) -> float:
    tab = tab or table()
    if severity not in LEVELS:
        raise ValueError(f"Severity must be one of {', '.join(LEVELS)}.")
    return float(tab["drivers"][driver][severity])
