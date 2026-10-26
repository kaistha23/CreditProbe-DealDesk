"""Early Warning card levels and drill journeys (PLAN_R4 B4).

A LEVEL is the dimension the top cards are cut by; its JOURNEY is the sequence of dimensions a reader drills
through before the customer list. The drill filter so far (`dims`) is a prefix of the journey:

  Corporate  sector   Sector -> borrowers                       (the original drill: see drill.level)
             region   Region -> Branch -> Sector -> borrowers
             branch   Branch -> Sector -> borrowers
             rating   Rating grade -> Sector -> borrowers      (global rating order)
             rm       Business unit -> Relationship manager -> borrowers
             product  Product -> Sector -> borrowers
  Retail     product  Product -> customers                      (the original drill: see drill.level)
             region   Region -> Branch -> Product -> customers
             branch   Branch -> Product -> customers
             band     Score band -> Product -> customers
             salaried Salaried / Non-Salaried -> Product -> customers
             vintage  Vintage -> Product -> customers

Every card carries the same figures as drill.level's cards (drill.kpis / reasons / by_source over the same
scope), so a level's cards add up to the book: exposure and exposures always; customers too when the dimension
is a customer attribute (`owner` in drill.DIMS). Product and vintage are exposure attributes, so a customer with
two products is counted in each, exactly as on the original product cards.
"""
from __future__ import annotations

from typing import Any

from backend.ews_domain import drill
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

LEVELS: dict[str, dict[str, dict[str, Any]]] = {
    "corporate": {
        "sector": {"label": "Sector", "journey": ["sector"]},
        "region": {"label": "Region", "journey": ["region", "branch", "sector"]},
        "branch": {"label": "Branch", "journey": ["branch", "sector"]},
        "rating": {"label": "Rating grade", "journey": ["rating", "sector"]},
        "rm": {"label": "RM / business unit", "journey": ["bu", "rm"]},
        "product": {"label": "Product", "journey": ["product", "sector"]},
    },
    "retail": {
        "product": {"label": "Product", "journey": ["product"]},
        "region": {"label": "Region", "journey": ["region", "branch", "product"]},
        "branch": {"label": "Branch", "journey": ["branch", "product"]},
        "band": {"label": "Score band", "journey": ["band", "product"]},
        "salaried": {"label": "Salaried / Non-Salaried", "journey": ["salaried", "product"]},
        "vintage": {"label": "Vintage", "journey": ["vintage", "product"]},
    },
}
DEFAULT_LEVEL = {"corporate": "sector", "retail": "product"}


def levels_meta(domain_id: str) -> dict[str, Any]:
    rd.domain_spec(domain_id)
    dims = drill.DIMS[domain_id]
    return {"domain_id": domain_id, "default": DEFAULT_LEVEL[domain_id],
            "levels": [{"key": k, "label": v["label"], "journey": v["journey"],
                        "journey_labels": [dims[d]["label"] for d in v["journey"]]}
                       for k, v in LEVELS[domain_id].items()],
            "dims": {k: {"label": d["label"], "plural": d["plural"], "owner": d["owner"]} for k, d in dims.items()}}


def _journey(domain_id: str, level: str) -> list[str]:
    rd.domain_spec(domain_id)
    if level not in LEVELS[domain_id]:
        raise rd.ReadRefused(f"{level!r} is not a level of the {domain_id} book; they are "
                             f"{sorted(LEVELS[domain_id])}.")
    return list(LEVELS[domain_id][level]["journey"])


def _ordered(domain_id: str, dim: str, keys: list[str], table: dict, chosen: str) -> list[str]:
    order = drill.DIMS[domain_id][dim].get("order")
    if order == "rating":
        from backend.v5common import ratings
        return sorted(keys, key=ratings.sort_key)
    if order == "key":
        names = list(drill.DIMS[domain_id][dim].get("names", {}))
        return sorted(keys, key=lambda k: (names.index(k) if k in names else len(names), k))
    return sorted(keys, key=lambda g: (-table[(chosen, g)].get("exposure_severe", 0), g))


def view(domain_id: str, level: str, period: str = "", dims: dict[str, str] | None = None) -> dict[str, Any]:
    """One step of a journey: the headline of the current drill filter and the cards of the next dimension."""
    journey = _journey(domain_id, level)
    dims = {k: str(v) for k, v in (dims or {}).items() if v not in (None, "")}
    depth = len(dims)
    if set(dims) != set(journey[:depth]):
        raise rd.ReadRefused(f"the drill filter {sorted(dims)} is not a step of the {level} journey {journey}.")
    dims = {k: dims[k] for k in journey[:depth]}
    scope = drill.Scope(domain_id, dims=dims, enriched=True)
    labels = drill._labels(domain_id)
    dim_defs = drill.DIMS[domain_id]
    window, prior_of = drill._periods_window(domain_id, period, drill.TREND_POINTS)
    chosen = window[-1]
    prior = prior_of.get(chosen, "")
    all_periods = rd.periods(domain_id)

    head = drill.kpis(scope, window, None, prior_of)
    head_prev = drill.kpis(scope, [prior], None, {prior: all_periods[all_periods.index(prior) - 1]
                                                  if prior and all_periods.index(prior) else ""}) if prior else {}
    now = head.get((chosen, "__all__"), {})
    before = head_prev.get((prior, "__all__")) if prior else None
    top = drill.reasons(scope, chosen, prior).get("__all__", [])

    next_dim = journey[depth] if depth < len(journey) else None
    children: list[dict[str, Any]] = []
    if next_dim:
        expr = drill.dim_expr(domain_id, next_dim)
        table = drill.kpis(scope, window, expr, prior_of)
        prev_table = drill.kpis(scope, [prior], expr) if prior else {}
        tops = drill.reasons(scope, chosen, prior, limit=3, group=expr)
        keys = _ordered(domain_id, next_dim, [g for (p, g) in table if p == chosen], table, chosen)
        for g in keys:
            card = drill._card(drill.dim_value_label(domain_id, next_dim, g), g, table[(chosen, g)],
                               prev_table.get((prior, g)), drill._trend(table, window, g), tops.get(g, []), now,
                               labels)
            card["dim"] = next_dim
            children.append(card)
        per = drill.by_source(scope, chosen, expr)
        for c in children:
            c["by_source"] = per.get(str(c["key"]), [])
    now["by_source"] = drill.by_source(scope, chosen).get("__all__", [])

    portfolio = f"{labels['portfolio']} by {LEVELS[domain_id][level]['label'].lower()}"
    breadcrumbs = [{"label": portfolio, "dims": {}}]
    acc: dict[str, str] = {}
    for k in journey[:depth]:
        acc[k] = dims[k]
        breadcrumbs.append({"label": drill.dim_value_label(domain_id, k, dims[k]), "dim": k, "dims": dict(acc)})
    name = breadcrumbs[-1]["label"] if depth else labels["portfolio"]
    move = drill._movement(now, before)

    owner_dim = bool(next_dim and dim_defs[next_dim]["owner"])
    reconcile = {
        "exposure": sum(c.get("exposure", 0.0) for c in children),
        "facilities": sum(c.get("facilities", 0) for c in children),
        "customers": sum(c.get("customers", 0) for c in children),
        "customers_add_up": owner_dim,
    } if next_dim else None
    return {
        "domain_id": domain_id, "release_id": scope.spec["release_id"], "ruleset": ews.RULESET_VERSION,
        "level": level, "level_label": LEVELS[domain_id][level]["label"], "journey": journey,
        "journey_labels": [dim_defs[d]["label"] for d in journey], "dims": dims, "depth": depth,
        "next_dim": next_dim, "next_label": dim_defs[next_dim]["plural"] if next_dim else None,
        "leaf": next_dim is None,
        "period": chosen, "prior_period": prior, "periods": all_periods, "trend_periods": window,
        "frequency": "quarterly" if domain_id == "corporate" else "monthly",
        "money_unit": "SAR million", "scope": scope.as_dict(), "labels": labels,
        "name": name, "breadcrumbs": breadcrumbs,
        "headline": now, "previous": before, "movement": move,
        "trend": drill._trend(head, window, "__all__"), "top_reasons": top,
        "commentary": drill.commentary(name, now, move, top, labels["period"], labels["owner"]),
        "children": children, "children_kind": next_dim, "classifications": [],
        "rating_mix": drill.rating_mix(scope, chosen), "reconcile": reconcile,
        "definitions": drill.definitions(domain_id),
    }
