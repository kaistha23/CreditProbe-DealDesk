"""Model cards for the two What-If methods, in the Early Warning model card's layout.

  1 Model summary   2 Data   3 Inputs (features)   4 How it works / training
  5 Validation      6 Sensitivities   7 Limitations   8 Version log

The numbers come from files written when the models were built:
  data/whatif_v5/<book>/cycle_model.json        the credit-cycle (MEV) model
  data/whatif_v5/models/<book>/card.json        XGBoost metrics, calibration, importance, SHAP
  data/whatif_v5/models/<book>/validation.json  engine checks and ECL sensitivities for both methods
"""
from __future__ import annotations

import json
from typing import Any

from backend.whatif_v5.domain import cycle, mev, store
from backend.whatif_v5.models import delta, xgb
from backend.whatif_v5.models.runner import LABELS

VERSION_LOG = [
    {"version": "delta-1.0.0", "date": "2026-10-11", "change": "First release on the What-If IFRS 9 domain: term "
     "structures by scenario and year, credit-cycle MEV transmission, exact Shapley attribution."},
    {"version": "xgb-1.0.0", "date": "2026-10-11", "change": "First release: PD, LGD and ECL-component models trained "
     "on the What-If domain; random and out-of-time splits; TreeSHAP."},
]


def _validation(book: str) -> dict[str, Any]:
    path = xgb.MODEL_DIR / book / "validation.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _mev_rows(book: str) -> list[dict[str, Any]]:
    model = cycle.load(book)
    st = mev.feature_stats()
    rows = []
    for d in mev.describe():
        k = d["key"]
        rows.append({**d, "elasticity_prior": model["gamma_prior"][k], "elasticity": model["gamma"][k],
                     "elasticity_data_only": model["gamma_data_only"][k], "feature_sd": st[k]["sd"]})
    return rows


def _common(book: str) -> dict[str, Any]:
    lab = LABELS[book]
    man = store.manifest(book)
    return {"book": lab["book"], "domain": book, "as_of": store.as_of(book), "periods": man["periods"],
            "rows": man["rows"], "grain": man["grain"], "scenario_weights": man["scenario_weights"],
            "horizon_years": man["horizon_years"], "source_release": man["source_release"],
            "mev": _mev_rows(book), "mev_access_note": mev.manifest().get("access_note", "")}


def delta_card(book: str) -> dict[str, Any]:
    lab = LABELS[book]
    model = cycle.load(book)
    val = _validation(book)
    seg_rows = [{"segment": k, "beta": v["beta"], "beta_data_only": v["beta_data"], "periods": v["periods"]}
                for k, v in sorted(model["betas"].items())]
    return {
        "method": "delta", "name": f"What-If Delta method — {lab['book']}", "version": delta.METHOD_VERSION,
        "status": "active", **_common(book),
        "summary": {
            "purpose": ("Re-measures IFRS 9 expected credit loss under a stated scenario by moving the bank's own "
                        "PD, LGD and EAD inputs deterministically, and says which driver moved ECL by how much."),
            "intended_users": "Credit risk, finance (IFRS 9), the risk and credit committees.",
            "not_for": "Reported provisions, regulatory capital returns or pricing; it is a what-if tool.",
            "kind": "Deterministic re-measurement on the IFRS 9 term structures",
        },
        "inputs": [
            {"group": "Exposure", "fields": f"{lab['exposure']} ID, {lab['owner']} ID, {lab['segment'].lower()}, "
                                              f"{lab['subsegment'].lower()}, product, stage, DPD"},
            {"group": "Credit quality", "fields": "rating and rating at origination (corporate); behaviour and "
                                                    "application scores, score band (retail); TTC PD"},
            {"group": "Exposure at default", "fields": "limit, drawn, undrawn, CCF, EAD"},
            {"group": "Collateral", "fields": "collateral type, value, haircut, secured share"},
            {"group": "IFRS 9 term structures", "fields": "marginal PD years 1-5 and LGD years 1-5 under base, "
                                                           "upturn and downturn; scenario weights 50/20/30"},
            {"group": "Macroeconomic variables", "fields": f"{len(mev.SERIES)} Saudi series (section 2)"},
        ],
        "how_it_works": [
            "Starting point: the stored term structures, so the starting ECL recomputed by this method equals the "
            "reported ECL exactly.",
            "PD shock: every annual hazard x (1 + change) for a relative shock, or + the change for pp/bps.",
            "LGD shock: every LGD + pp (or x (1 + change)), capped at 0 and 100%.",
            "CCF / EAD: EAD = drawn + CCF x undrawn, so a CCF move changes EAD by the move x undrawn; an EAD % "
            "shock scales EAD directly.",
            "Rating: notches move the grade on the global rating scale (stopping at C; retail moves score bands "
            "of 80 points, stopping at E); every hazard x masterscale PD(new grade) / PD(old grade).",
            "Sector stress and MEVs: the exposure's credit-cycle index Z moves (sector stress by its stated "
            "standard deviations; an MEV shock by the estimated elasticities x the segment's beta); every hazard "
            "moves along the one-factor model, hazard' = Phi(Phi^-1(hazard) - sqrt(rho/(1-rho)) dZ); LGD moves "
            "with the cycle (x (1 - 0.10 dZ)) and real-estate collateral with real-estate prices.",
            "Staging re-assessed under the book's SICR rules: DPD 30/90; corporate rating CCC (Stage 2) or CC and "
            "worse (Stage 3), 2+ notches below origination (Stage 2); retail behaviour score below 520 (Stage 2); "
            "plus Rule B: 12-month PD at least 2x the starting PD and +0.5pp. A scenario never cures.",
            "ECL per scenario = sum over years of marginal PD x LGD x EAD (12 months for Stage 1, 5-year lifetime "
            "for Stages 2-3); weighted by the scenario weights. Undiscounted, as the books measure it.",
            "Attribution: the exact Shapley value of each driver (PD, LGD, CCF/EAD, staging, rating, sector, MEV) "
            "over the drivers the scenario uses; the bars add up to the change exactly.",
        ],
        "cycle_model": {"r2": model["r2"], "lambda": model["lambda"], "periods": model["periods"],
                        "book_z": model["book_z"], "fitted_z": model["fitted_z"], "segments": seg_rows,
                        "how": ("Credit-cycle index Z per segment and period from the observed default rate "
                                "(Vasicek inversion against the long-run rate); Z regressed on the standardised MEVs "
                                "by ridge regression shrunk toward reference sensitivities, signs constrained; segment "
                                "betas from each segment's Z on the book's Z, shrunk toward 1.")},
        "validation": val.get("delta", {}),
        "sensitivities": val.get("sensitivity_delta", []),
        "limitations": [
            "The scenario paths are 5 annual steps; quarterly or monthly paths are not modelled.",
            "ECL is undiscounted, as the books measure it; the effective interest rate is not applied.",
            ("The retail book's 20 months do not identify the MEV elasticities on their own (fit R² "
             f"{cycle.load('retail')['r2']:.2f}); retail uses the reference sensitivities.") if book == "retail" else
            f"The corporate cycle model explains {model['r2'] * 100:.0f}% of the book's cycle index over "
            f"{len(model['periods'])} quarters; segment betas rest on the same history.",
            "MEV history was read from public mirrors of IMF, SAMA, GASTAT and EIA data (the build machine could not "
            "reach the primary sites); some recent values are single-source and are flagged in the MEV store.",
            "Capital figures are illustrative (IRB-style formula on the What-If inputs), not a regulatory return.",
            "Direct stage migrations pick exposures deterministically (worst PD first), not at random.",
        ],
        "versions": VERSION_LOG,
    }


def xgb_card(book: str) -> dict[str, Any]:
    lab = LABELS[book]
    tc = xgb.card(book)
    meta = json.loads((xgb.MODEL_DIR / book / "models.json").read_text())
    val = _validation(book)
    t = tc["targets"]
    return {
        "method": "xgboost", "name": f"What-If XGBoost — {lab['book']}", "version": tc["version"], "status": "active",
        **_common(book),
        "summary": {
            "purpose": ("A machine-learning challenger to the Delta method: gradient-boosted trees learn how PD by "
                        "scenario and year, LGD and ECL coverage respond to the IFRS 9 inputs and the MEVs; a "
                        "scenario is applied by changing the inputs and predicting."),
            "intended_users": "Credit risk and model validation, as a second opinion beside the Delta method.",
            "not_for": "Reported provisions or capital; extrapolation far outside the training ranges.",
            "kind": "XGBoost regression (gradient-boosted decision trees)",
        },
        "inputs": [{"group": "Features (PD and LGD models)", "fields": ", ".join(meta["models"]["pd"]["features"])},
                   {"group": "Features (ECL-component models)", "fields": ", ".join(meta["models"]["ecl12"]["features"])}],
        "training": {
            "algorithm": "XGBoost (hist), squared error", "params": meta["params"], "rounds": meta["rounds"],
            "seed": meta["seed"], "trained": meta["trained"], "rows": tc["rows"],
            "targets": {"pd": "logit of the annual conditional PD h(s, t)", "lgd": "LGD(s, t)",
                        "ecl12": "12-month ECL / EAD", "ecllt": "lifetime ECL / EAD"},
            "splits": ("Random: 70% of exposure-periods train, 30% test (served models). Out-of-time: the first "
                       f"70% of periods (to {tc['rows']['out_of_time_cut']}) train, the rest test."),
            "files": {k: {"file": v["file"], "sha256": v["sha256"], "bytes": v["bytes"]}
                      for k, v in meta["models"].items()},
            "determinism": ("Fixed seed and sampling; model files sealed with sha256 and checked on load; the "
                            f"numpy evaluator reproduces XGBoost to {tc['numpy_evaluator_max_error']:.1e}."),
        },
        "validation": {k: {"random": v["random"], "out_of_time": v["out_of_time"], "calibration": v["calibration"],
                           "calibration_out_of_time": v["calibration_out_of_time"]} for k, v in t.items()},
        "importance": {k: v["importance"][:15] for k, v in t.items()},
        "shap": {k: v["shap"] for k, v in t.items()},
        "engine_validation": val.get("xgboost", {}),
        "sensitivities": val.get("sensitivity_xgboost", []),
        "pd_sensitivity_by_mev": tc["sensitivity"],
        "limitations": [
            "The models learn the What-If domain, whose term structures come from the credit-cycle model: their MEV "
            "response cannot be richer than that history.",
            "The starting ECL is the models' own prediction; the gap to the reported ECL is shown on every result.",
            "Trees do not extrapolate: a shock that takes an input beyond its training range is held at the edge "
            "of what the model saw.",
            "Stage, staging rules and direct PD/LGD/CCF deltas are applied by the engine, as for the Delta method.",
            "Its response to macro and sector shocks is weaker than the Delta method's (section 6): the Delta method "
            "applies the estimated elasticities to every exposure, while the trees learn the response from 20 periods "
            "of three paths. The sign of every response agrees; use both methods side by side for macro scenarios.",
        ],
        "versions": VERSION_LOG,
    }


def card(book: str, method: str) -> dict[str, Any]:
    store.book_dir(book)
    if method == "delta":
        return delta_card(book)
    if method == "xgboost":
        return xgb_card(book)
    raise ValueError(f"'{method}' is not a method.")
