"""Publish the scenario engine to Data Domains (N5): the calibration, the joint scenarios, the satellite models, the
book results, and the calibrated Stress Lab ladder (`dd_stress_scenario`, set R13-S1).

    python -m backend.scenarios.publish            recompute and publish (idempotent: replace_where version = 1)
    python -m backend.scenarios.publish --tiers    also recompute the tier distribution across the demo deals

Readers: `rows(relation)` reads back through `backend.dealdesk.data.dd_read`; What-If and the memo read the engine
directly, and every figure they print names the relation it is published in.
"""
from __future__ import annotations

import sys
from typing import Any

from backend.scenarios import VERSION, engine

REL_VERSION = 1
OWNER = "S"


def calibration_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    fp = res["reproducibility"]["fingerprint"]
    out = []
    for key, r in res["calibration"].items():
        est = r["estimate"] or {}
        for sev in ("mild", "moderate", "severe"):
            fr = (est.get("freq") or {}).get(sev) or {}
            pct = ({"mild": "P75", "moderate": "P92", "severe": f"max(P96, worst episode): {est.get('severe_basis', '')}"}[sev]
                   if r["method"] == "empirical" else str(r["fallback_label"]))
            out.append({"driver": key, "severity": sev, "version": REL_VERSION, "label": r["label"], "unit": r["unit"],
                        "value": float(r["values"][sev]), "method": r["method"], "percentile": pct,
                        "estimate": float(est[sev]) if est.get(sev) is not None else None,
                        "n_obs": est.get("n"), "n_independent": est.get("n_independent"),
                        "freq_count": fr.get("count"), "freq_share": fr.get("share"), "freq_labels": fr.get("labels") or [],
                        "worst_episode": (f"{est['worst_episode_label']}: {est['worst_episode']:.4g}" if est else None),
                        "window": r["window"], "source": r["source"], "fallback_reason": r["fallback_reason"],
                        "rule_check": r.get("rule_check"), "engine_version": VERSION, "fingerprint": fp})
    return out


def joint_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    j = res["joint"]
    out = []
    for sev, sc in j["joint"].items():
        for k, v in sc["values"].items():
            out.append({"scenario_id": f"joint_{sev}", "driver": k, "version": REL_VERSION,
                        "kind": "analogue" if sc["band"] is None else "copula", "severity": sev, "value": v,
                        "unit": j["units"][k], "composite_percentile": (sum(sc["band"]) / 2 if sc["band"] else None),
                        "basis": sc["basis"], "engine_version": VERSION})
    for a in j["analogues"]:
        for k, v in a["values"].items():
            out.append({"scenario_id": f"analogue_{a['year']}", "driver": k, "version": REL_VERSION, "kind": "analogue",
                        "severity": None, "value": v, "unit": j["units"][k], "composite_percentile": a["percentile"],
                        "basis": f"the {a['year']} moves as observed", "engine_version": VERSION})
    for sev, vals in j["independent_tails"].items():
        for k, v in vals.items():
            out.append({"scenario_id": f"independent_{sev}", "driver": k, "version": REL_VERSION, "kind": "independent",
                        "severity": sev, "value": v, "unit": j["units"][k], "composite_percentile": None,
                        "basis": "each driver at its own severity (shown for comparison only; never used)", "engine_version": VERSION})
    return out


def satellite_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for m in ("pd", "migration"):
        f = res["satellite"][m]
        common = {"model": m, "version": REL_VERSION, "n_obs": f["n"], "r2": f["r2"], "r2_within": f["r2_within"],
                  "lambda": f["lambda_b"], "oos_rmse": f["oos"]["rmse"], "oos_rmse_naive": f["oos"]["rmse_naive"],
                  "window": f"{f['from']}–{f['to']}", "engine_version": VERSION}
        out.append({**common, "term": "const", "estimate": f["const"], "std_error": None, "band_low": None, "band_high": None,
                    "identified_flag": None, "note": "common level (unpenalised)"})
        for s, v in f["sector_effects"].items():
            out.append({**common, "term": f"sector:{s}", "estimate": v, "std_error": None, "band_low": None, "band_high": None,
                        "identified_flag": None, "note": "sector effect (ridge, lambda 1)"})
        for k, c in f["coef"].items():
            out.append({**common, "term": k, "estimate": c["beta"], "std_error": c["se"], "band_low": c["band90"][0],
                        "band_high": c["band90"][1], "identified_flag": int(c["identified"]), "note": c["why"]})
    return out


def result_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for sev, t in res["translation"].items():
        out.append({"severity": sev, "sector": "*", "version": REL_VERSION, "ead_mn": t["ead_start"], "ecl_start_mn": t["ecl_start"],
                    "ecl_stressed_mn": t["ecl_stressed"], "ecl_change_mn": t["ecl_change"], "ecl_change_low_mn": t["ecl_band"][0],
                    "ecl_change_high_mn": t["ecl_band"][1], "pd_start": t["pd_start"], "pd_stressed": t["pd_stressed"],
                    "stage2_share_start": t["stage2_share_start"], "stage2_share_stressed": t["stage2_share_stressed"],
                    "rwa_change_mn": t["rwa_change"], "capital_impact_mn": t["capital_impact"], "as_of": t["as_of"],
                    "engine_version": VERSION})
        for s in t["sectors"]:
            out.append({"severity": sev, "sector": s["sector"], "version": REL_VERSION, "ead_mn": s["ead"], "ecl_start_mn": s["ecl_start"],
                        "ecl_stressed_mn": s["ecl_stressed"], "ecl_change_mn": s["ecl_change"], "pd_start": s["pd_start"],
                        "pd_stressed": s["pd_stressed"], "stage2_share_start": s["stage2_share_start"],
                        "stage2_share_stressed": s["stage2_share_stressed"], "as_of": t["as_of"], "engine_version": VERSION})
    return out


def regime_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.scenarios import regime
    return regime.relation_rows()


def revenue_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.scenarios import revenue
    return revenue.relation_rows()


def mev_annual_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.scenarios import regime
    return regime.mev_annual_rows()


def mev_latest_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.scenarios import regime
    return regime.mev_latest_rows()


def backtest_rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.whatif_v5 import backtest
    return backtest.relation_rows()


RELATIONS = {"dd_scenario_calibration": calibration_rows, "dd_scenario_joint": joint_rows,
             "dd_satellite_model": satellite_rows, "dd_scenario_result": result_rows,
             # R14 m (K12, §m (7)): the current regime, the revenue channel and the What-If back-test
             "dd_macro_regime": regime_rows, "dd_revenue_channel": revenue_rows, "whatif_backtest": backtest_rows,
             "whatif_mev_annual": mev_annual_rows, "whatif_mev_latest": mev_latest_rows}


R14_RELATIONS = frozenset({"dd_macro_regime", "dd_revenue_channel", "whatif_backtest", "whatif_mev_annual", "whatif_mev_latest"})


def publish_all(res: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk.data import store
    from backend.scenarios import ladder
    res = res or engine.build()
    out = {}
    for rel, fn in RELATIONS.items():
        rows = fn(res)
        actor = "m:r14-m1" if rel in R14_RELATIONS else f"{OWNER}:{VERSION}"
        out[rel] = store.publish(rel, rows, mode="replace_where", actor=actor, where={"version": REL_VERSION})
    out["dd_stress_scenario"] = ladder.publish()
    return out


def rows(relation: str, **filters: Any) -> list[dict[str, Any]]:
    from backend.dealdesk.data import store
    return store.dd_read(relation, **filters)


def main(argv: list[str]) -> int:
    out = publish_all()
    for rel, r in out.items():
        print(rel, {k: r.get(k) for k in ("version", "rows", "written", "published", "already") if k in r})
    if "--tiers" in argv:
        from backend.scenarios import tiers
        rep = tiers.compare(write=True)
        print("tiers before", rep["before"]["counts"], "after", rep["after"]["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
