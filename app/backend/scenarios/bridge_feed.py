"""The macro leg for the ECL bridge forecast (R13 ID gap 4; PLAN_R14 §m items, §g "ECL bridge on §S").

The ECL bridge forecast (backend/intel/portfolio/ecl_bridge.py, owned by session g in R14) forecasts stage movers from
the EWS model and says "macro scenarios come from the scenario engine, not this bridge". This is the hook it reads for
the macro bar: the §S calibrated book translation at a severity (dd_scenario_result), with the current regime and the
macro vintage, so the bridge never computes its own macro.

    from backend.scenarios import bridge_feed
    leg = bridge_feed.macro_leg("moderate")   # {"ecl_change_mn", "by_sector", "scenario", "regime", "vintage", "relations"}
"""
from __future__ import annotations

from typing import Any

from backend.scenarios import calibrate


def macro_leg(severity: str = "moderate") -> dict[str, Any]:
    if severity not in calibrate.SEVERITIES:
        raise KeyError(severity)
    from backend.scenarios import conditioned, engine, regime
    res = engine.build()
    t = res["translation"][severity]
    r = regime.current()
    fam = conditioned.families(r)
    scen = (conditioned.scenario_line(fam["reversal"][severity]["values"]) if fam else
            ", ".join(f"{k} {v:.1f}" for k, v in t["values"].items()))
    return {"severity": severity, "ecl_start_mn": t["ecl_start"], "ecl_change_mn": t["ecl_change"],
            "ecl_band_mn": t.get("ecl_band"), "stage2_share_start": t["stage2_share_start"],
            "stage2_share_stressed": t["stage2_share_stressed"], "as_of": t["as_of"],
            "by_sector": [{"sector": s["sector"], "ecl_change_mn": s["ecl_change"]} for s in t["sectors"]],
            "scenario": scen, "regime": r["label"], "vintage": r["vintage_line"],
            "line": (f"Macro ({severity}, {r['label']}): ECL {t['ecl_change']:+,.0f}m on SAR {t['ecl_start']:,.0f}m "
                     f"({scen}); §S calibrated severities, dd_scenario_result."),
            "relations": ["dd_scenario_result", "dd_scenario_calibration", "dd_macro_regime"],
            "engine_version": res["version"], "fingerprint": res["reproducibility"]["fingerprint"]}
