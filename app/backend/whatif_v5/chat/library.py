"""The scenario library: standard scenarios per book (seeded) plus the repository of saved ones."""
from __future__ import annotations

from typing import Any

from backend.whatif_v5.domain import store as dstore
from backend.whatif_v5.models.scenario import Scenario, Scope, Step, parse_shocks

STANDARD: dict[str, list[dict[str, Any]]] = {
    "corporate": [
        {"key": "oil-shock", "name": "Oil price shock", "tags": ["macro", "oil"],
         "description": "Brent 40% below the base path in every year, as in 2015 (-47%) and 2020 (-35%).",
         "steps": [("Oil price -40%", {"mev": {"brent": -40}}, {})]},
        {"key": "rates-up", "name": "Rates up 200bps", "tags": ["macro", "rates"],
         "description": "SAMA repo and 3-month SAIBOR 200bps above the base path, as in the 2022 tightening (+400bps).",
         "steps": [("Repo and SAIBOR +200bps", {"mev": {"repo": 200, "saibor_3m": 200}}, {})]},
        {"key": "recession", "name": "Saudi recession", "tags": ["macro", "severe"],
         "description": "Real and non-oil GDP growth 3pp lower, unemployment +2pp and oil -30%: a 2020-type year.",
         "steps": [("Recession", {"mev": {"gdp_real": -3, "gdp_nonoil": -3, "unemployment": 2, "brent": -30}}, {})]},
        {"key": "downgrade-1", "name": "Book-wide 1-notch downgrade", "tags": ["rating"],
         "description": "Every performing borrower one notch worse on the global rating scale.",
         "steps": [("Downgrade 1 notch", {"rating": 1}, {})]},
        {"key": "construction", "name": "Construction sector stress", "tags": ["sector", "construction"],
         "description": "Severe stress on Construction (2 sd of its cycle index) with PD +25%.",
         "steps": [("Severe Construction stress, PD +25%", {"sector": 2.0, "pd": {"mode": "relative", "value": 25}},
                    {"segments": ["Construction"]})]},
        {"key": "real-estate", "name": "Real estate correction", "tags": ["sector", "collateral"],
         "description": "Real-estate prices -20% (collateral) and LGD +5pp on the Real Estate sector.",
         "steps": [("Real estate prices -20%", {"mev": {"re_price": -20}}, {}),
                   ("LGD +5pp on Real Estate", {"lgd": {"mode": "pp", "value": 5}}, {"segments": ["Real Estate"]})]},
        {"key": "parameters", "name": "PD +25%, LGD +5pp", "tags": ["parameters"],
         "description": "A parameter shock to the whole book: PD 25% higher and LGD 5pp higher.",
         "steps": [("PD +25%, LGD +5pp", {"pd": {"mode": "relative", "value": 25}, "lgd": {"mode": "pp", "value": 5}}, {})]},
        {"key": "migration", "name": "10% of Stage 1 to Stage 2", "tags": ["staging"],
         "description": "A tenth of Stage 1 moves to Stage 2 (worst PD first); 12.8% moved in the worst year.",
         "steps": [("10% of Stage 1 to Stage 2", {"stage": [{"from": 1, "to": 2, "share": 10}]}, {})]},
    ],
    "retail": [
        {"key": "unemployment", "name": "Unemployment +2pp", "tags": ["macro"],
         "description": "Unemployment 2pp above the base path in every year.",
         "steps": [("Unemployment +2pp", {"mev": {"unemployment": 2}}, {})]},
        {"key": "rates-up", "name": "Rates up 200bps", "tags": ["macro", "rates"],
         "description": "SAMA repo and 3-month SAIBOR 200bps above the base path.",
         "steps": [("Repo and SAIBOR +200bps", {"mev": {"repo": 200, "saibor_3m": 200}}, {})]},
        {"key": "house-prices", "name": "House prices -20%", "tags": ["collateral", "mortgage"],
         "description": "Real-estate prices 20% lower (collateral on mortgages) with mortgage LGD +5pp.",
         "steps": [("House prices -20%", {"mev": {"re_price": -20}}, {}),
                   ("Mortgage LGD +5pp", {"lgd": {"mode": "pp", "value": 5}}, {"segments": ["Mortgage"]})]},
        {"key": "cards", "name": "Credit card PD +50%", "tags": ["parameters", "cards"],
         "description": "Credit card PD half as high again.",
         "steps": [("Credit card PD +50%", {"pd": {"mode": "relative", "value": 50}}, {"segments": ["Credit Card"]})]},
        {"key": "score-band", "name": "One score band worse", "tags": ["rating"],
         "description": "Every performing customer one behaviour-score band (80 points) worse.",
         "steps": [("Score -1 band", {"rating": 1}, {})]},
        {"key": "recession", "name": "Saudi recession", "tags": ["macro", "severe"],
         "description": "GDP -3pp, non-oil GDP -3pp, unemployment +2pp and oil -30%.",
         "steps": [("Recession", {"mev": {"gdp_real": -3, "gdp_nonoil": -3, "unemployment": 2, "brent": -30}}, {})]},
    ],
}


def scenario_for(book: str, entry: dict[str, Any], period: str = "") -> Scenario:
    steps = [Step(instruction=w, restatement=w, shocks=parse_shocks(sh), scope=Scope.from_dict(sc))
             for w, sh, sc in entry["steps"]]
    return Scenario(domain=book, period=period or dstore.as_of(book), steps=steps, name=entry["name"])


def seed(store) -> int:
    """Insert the standard scenarios that are missing (idempotent; ids are stable)."""
    have = {s["scenario_id"] for s in store.scenarios(standard=True)}
    n = 0
    for book, entries in STANDARD.items():
        for e in entries:
            sid = f"std-{book}-{e['key']}"
            if sid in have:
                continue
            sc = scenario_for(book, e)
            store.save_scenario({"scenario_id": sid, "owner": "", "team": "", "name": e["name"],
                                 "description": e["description"], "domain": book, "period": sc.period,
                                 "method": "delta", "scenario": sc.to_dict(), "tags": e["tags"], "standard": True,
                                 "created_at": 0.0})
            n += 1
    return n
