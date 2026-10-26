"""PLAN_R12 Session P: the product policy values the analytics test against.

Read from `dd_parameter` (table `products`, key, value) when Session E publishes them there, else from the
product template (E's `templates.py`, key `policy`), else these defaults. Every value carries where it came
from, so the (i) can name it.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.products import source

DEFAULTS: dict[str, Any] = {
    # contracting and project limits
    "project.cover_ratio_min": 1.25,           # remaining contract proceeds / funded outstanding (T&C "cover ratio")
    "project.finance_pct_max": 0.80,           # % of a certified payment certificate that may be financed
    "project.last_certificates_unfinanced": 2,  # the last n certificates are not financed
    "project.delay_days": [30, 60, 90],
    "project.slip_watch_pts": 10.0,            # time elapsed % minus work done % that flags a slipping project
    "project.employer_concentration_max": 0.60,  # top-2 employers' share of remaining backlog
    # LG types -> CCF table row (data/dealdesk/params/v1/ccf.json via dd_parameter)
    "lg.ccf_row": {"bid_bond": "performance_lg", "apg": "performance_lg", "pb": "performance_lg", "rb": "performance_lg",
                   "financial_lg": "financial_lg", "lc": "trade_lc", "lcm": "trade_lc"},
    # escrow
    "escrow.cover_ratio_min": 1.20,
    "escrow.retention_pct": 0.05,              # held in escrow until completion
    "escrow.release_tolerance_pts": 0.0,       # release allowed only when progress >= milestone
    # syndication
    "syndication.max_hold_pct": 25.0,          # final hold cap as share of the facility
    # SME fast track
    "sme.max_amount_sar_mn": 5.0,
    "sme.max_tenor_years": 5,
    "sme.max_grade_auto": "G5",               # auto-approve up to this grade
    "sme.max_grade_eligible": "G6",           # G7-G8 are exceptions to the full flow
    "sme.max_returned_payments_q": 2,
    "sme.min_interest_cover_x": 2.0,
    "sme.excluded_sectors": ["Metals and Mining"],
    "sme.collateral_above_sar_mn": 2.0,
    "sme.doa": [
        {"level": "SME Credit Officer", "max_sar_mn": 1.0},
        {"level": "SME Credit Manager", "max_sar_mn": 3.0},
        {"level": "Head of SME Credit", "max_sar_mn": 5.0},
    ],
}


_CACHE: dict[str, Any] = {"token": None, "at": 0.0, "value": {}}


def _from_parameters() -> dict[str, Any]:
    import time
    token = id(source._override)
    if _CACHE["token"] == token and time.monotonic() - _CACHE["at"] < 30:
        return _CACHE["value"]
    out = _read_parameters()
    _CACHE.update(token=token, at=time.monotonic(), value=out)
    return out


def _read_parameters() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in source.read("dd_parameter", table_name="products"):
        k, v = r.get("param_key"), r.get("value")
        if k:
            if isinstance(v, str) and v[:1] in "[{":
                try:
                    import json
                    v = json.loads(v)
                except ValueError:
                    pass
            out[str(k)] = {"value": v, "src": {"domain": "Deal Desk", "relation": "dd_parameter",
                                               "key": {"table_name": "products", "param_key": k}, "column": "value"}}
    return out


def _from_template(product: str) -> dict[str, Any]:
    try:
        from backend.dealdesk.products import templates  # Session E
    except Exception:  # noqa: BLE001
        return {}
    get = getattr(templates, "get", None) or getattr(templates, "template", None)
    try:
        t = get(product) if callable(get) else getattr(templates, "TEMPLATES", {}).get(product)
    except Exception:  # noqa: BLE001
        return {}
    pol = (t or {}).get("policy") if isinstance(t, dict) else None
    return {k: {"value": v, "src": {"domain": "Deal Desk", "relation": "product_template", "key": {"product": product, "policy": k}}}
            for k, v in (pol or {}).items()}


def value(key: str, product: str = "") -> tuple[Any, dict[str, Any]]:
    """(value, source) of one policy value."""
    for layer in (_from_parameters(), _from_template(product) if product else {}):
        if key in layer:
            return layer[key]["value"], layer[key]["src"]
    return DEFAULTS[key], {"domain": "Deal Desk", "relation": "products_policy_default", "key": {"key": key},
                           "note": "Session P default until the value is published in dd_parameter"}


def v(key: str, product: str = "") -> Any:
    return value(key, product)[0]
