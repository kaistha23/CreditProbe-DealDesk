"""Run a scenario on the What-If domain with a chosen method: the one entry point.

A run is deterministic: the same scenario (steps, period, population) and the
same method give the same numbers, so the run id is a hash of the request and
a run can always be recomputed from it.
"""
from __future__ import annotations

import collections
import hashlib
import json
import threading
import time
from typing import Any

import numpy as np

from backend.whatif_v5 import cohorts
from backend.whatif_v5.domain import mev, store
from backend.whatif_v5.models import engine
from backend.whatif_v5.models.delta import Delta
from backend.whatif_v5.models.scenario import Scenario, describe_shocks

LABELS: dict[str, dict[str, str]] = {
    "corporate": {"book": "Corporate", "segment": "Sector", "segments": "Sectors", "subsegment": "Sub-sector",
                  "owner": "Borrower", "owners": "Borrowers", "exposure": "Facility", "exposures": "Facilities",
                  "grade": "Rating", "grade_notch": "notch", "period": "Quarter", "frequency": "quarterly"},
    "retail": {"book": "Retail", "segment": "Product", "segments": "Products", "subsegment": "Sub-product",
               "owner": "Customer", "owners": "Customers", "exposure": "Account", "exposures": "Accounts",
               "grade": "Behaviour score band", "grade_notch": "band", "period": "Month", "frequency": "monthly"},
}
METHODS = ("delta", "xgboost")
_CACHE: collections.OrderedDict[str, dict] = collections.OrderedDict()
_LOCK = threading.Lock()


class RunError(ValueError):
    pass


def method(key: str) -> engine.Method:
    if key == "delta":
        return Delta()
    if key == "xgboost":
        from backend.whatif_v5.models import xgb
        return xgb.XGBoostMethod()
    raise RunError(f"'{key}' is not a method. The methods are the Delta method and XGBoost.")


def population(scenario: Scenario, frame) -> tuple[np.ndarray, dict[str, Any] | None]:
    if not scenario.cohort_id:
        return np.ones(len(frame), dtype=bool), None
    try:
        frozen = cohorts.open_cohort(scenario.cohort_id)
    except cohorts.CohortError as e:
        raise RunError(str(e)) from e
    if frozen["domain_id"] != scenario.domain:
        raise RunError(f"Cohort {scenario.cohort_id} is a {frozen['domain_id']} cohort.")
    ids = set(frozen["exposure_ids"])
    return frame["exposure_id"].isin(ids).to_numpy(), cohorts.public(frozen)


def run_key(scenario: Scenario, method_key: str) -> str:
    body = {"scenario": scenario.key(), "period": scenario.period, "domain": scenario.domain,
            "cohort": scenario.cohort_id, "method": method_key}
    return "wr-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def run(scenario: Scenario, method_key: str) -> dict[str, Any]:
    rid = run_key(scenario, method_key)
    with _LOCK:
        if rid in _CACHE:
            _CACHE.move_to_end(rid)
            return _CACHE[rid]
    t0 = time.time()
    try:
        period = store.resolve_period(scenario.domain, scenario.period)
    except store.DomainError as e:
        raise RunError(str(e)) from e
    scenario.period = period
    frame = store.frame(scenario.domain, period)
    pop, cohort = population(scenario, frame)
    labels = LABELS[scenario.domain]
    m = method(method_key)
    try:
        result = engine.run(scenario, m, frame, pop, labels)
    except engine.RunError as e:
        raise RunError(str(e)) from e
    result.update({
        "run_id": rid, "domain": scenario.domain, "period": period, "labels": labels,
        "scenario": scenario.to_dict(),
        "steps": [{"instruction": s.instruction, "restatement": s.restatement,
                   "shocks": describe_shocks(s.shocks, labels), "scope": s.scope.describe(labels)}
                  for s in scenario.steps],
        "population": {"kind": "cohort" if cohort else "book", "cohort": cohort,
                       "label": (f"Early Warning cohort {scenario.cohort_id}" if cohort else f"the {labels['book'].lower()} book")},
        "method_version": getattr(m, "version", ""),
        "scenario_weights": mev.WEIGHTS,
        "seconds": round(time.time() - t0, 2),
    })
    with _LOCK:
        _CACHE[rid] = result
        while len(_CACHE) > 24:
            _CACHE.popitem(last=False)
    return result
