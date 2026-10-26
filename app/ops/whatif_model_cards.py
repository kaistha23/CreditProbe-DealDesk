"""Validate both What-If methods on the engine and write their ECL sensitivities.

    .venv/bin/python ops/whatif_model_cards.py [corporate|retail]

Writes data/whatif_v5/models/<book>/validation.json:
  delta / xgboost   zero-shock reproduction, Shapley additivity, monotonicity, determinism
  sensitivity_*     book ECL change for a 1-sd adverse move in each MEV, and for the standard shocks
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.whatif_v5.domain import mev, store  # noqa: E402
from backend.whatif_v5.models import runner, xgb  # noqa: E402
from backend.whatif_v5.models.scenario import Scenario, Scope, Step, parse_shocks  # noqa: E402


def scen(book: str, shocks: dict, scope: dict | None = None) -> Scenario:
    return Scenario(domain=book, period="", steps=[Step("", "", parse_shocks(shocks), Scope.from_dict(scope))] if shocks else [])


def checks(book: str, method: str) -> dict:
    out: dict = {}
    r0 = runner.run(scen(book, {}), method)
    c = r0["cards"]
    out["zero_shock"] = {"reported": c["reported_ecl"], "start": c["start_ecl"], "scenario": c["scenario_ecl"],
                         "start_minus_reported": c["start_ecl"] - c["reported_ecl"],
                         "scenario_minus_start": c["scenario_ecl"] - c["start_ecl"]}
    pd_steps = []
    for v in (10, 25, 50, 100):
        r = runner.run(scen(book, {"pd": {"mode": "relative", "value": v}}), method)
        pd_steps.append({"pd_change_pct": v, "ecl_change_pct": r["cards"]["change_pct"]})
    out["pd_monotonic"] = {"steps": pd_steps,
                           "pass": all(a["ecl_change_pct"] <= b["ecl_change_pct"] for a, b in zip(pd_steps, pd_steps[1:]))}
    notch = []
    for n in (1, 2, 3):
        r = runner.run(scen(book, {"rating": n}), method)
        notch.append({"notches": n, "ecl_change_pct": r["cards"]["change_pct"]})
    out["rating_monotonic"] = {"steps": notch, "pass": all(a["ecl_change_pct"] <= b["ecl_change_pct"] for a, b in zip(notch, notch[1:]))}
    combo = runner.run(scen(book, {"pd": {"mode": "relative", "value": 20}, "lgd": {"mode": "pp", "value": 5},
                                   "rating": 1, "mev": {"gdp_real": -2}, "ccf": {"mode": "pp", "value": 10},
                                   "sector": 1.0}), method)
    out["shapley_additivity"] = {"difference": combo["reconciliation"]["difference"],
                                 "pass": combo["reconciliation"]["reconciles"]}
    runner._CACHE.clear()
    again = runner.run(scen(book, {"pd": {"mode": "relative", "value": 20}, "lgd": {"mode": "pp", "value": 5},
                                   "rating": 1, "mev": {"gdp_real": -2}, "ccf": {"mode": "pp", "value": 10},
                                   "sector": 1.0}), method)
    out["determinism"] = {"pass": again["cards"]["scenario_ecl"] == combo["cards"]["scenario_ecl"]}
    return out


def sensitivity(book: str, method: str) -> list[dict]:
    st = mev.feature_stats()
    rows = []
    for s in mev.SERIES:
        sd = st[s.key]["sd"]
        move = -s.direction * sd
        if s.shock_unit == "pct":
            # price features are % deviations from the reference level: a 1-sd move is that many % of the level
            shock = max(-90.0, move)
        elif s.shock_unit == "bps":
            shock = move * 100.0
        else:
            shock = move
        r = runner.run(scen(book, {"mev": {s.key: round(shock, 4)}}), method)
        rows.append({"mev": s.key, "name": s.name, "adverse_1sd_shock": round(shock, 4),
                     "unit": s.shock_unit, "ecl_change": r["cards"]["change"], "ecl_change_pct": r["cards"]["change_pct"]})
    return rows


def main() -> int:
    for book in (sys.argv[1:] or list(store.BOOKS)):
        t0 = time.time()
        out = {"book": book, "as_of": store.as_of(book)}
        for method in ("delta", "xgboost"):
            out[method] = checks(book, method)
            out[f"sensitivity_{method}"] = sensitivity(book, method)
            print(f"{book} {method}: zero {out[method]['zero_shock']['start_minus_reported']:+.2f}, "
                  f"pd monotonic {out[method]['pd_monotonic']['pass']}, rating monotonic {out[method]['rating_monotonic']['pass']}, "
                  f"additivity {out[method]['shapley_additivity']['difference']:.1e}")
        (xgb.MODEL_DIR / book / "validation.json").write_text(json.dumps(out, indent=1))
        print(f"{book}: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
