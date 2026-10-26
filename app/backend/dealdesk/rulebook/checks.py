"""The Deal Desk policy checks a regulation or an internal credit policy can move.

Each check reads one fact of a deal (facts.py) against one threshold. The value in force comes from the Deal Desk table that
owns it (uae_desk, returns: Admin -> Deal Desk Parameters) or, for a threshold Deal Desk did not have, from the rulebook's
own seed below; an approved policy adds a version on top (store.thresholds()), for every deal or for one sector, with the
clause it came from. "Run the checks with and without the change" is `evaluate(fact, overlay)` with the two overlays.
"""
from __future__ import annotations

from typing import Any

RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-",
           "CCC+", "CCC", "CCC-", "CC", "C", "D"]

#: param -> the check it moves
PARAMS: dict[str, dict[str, Any]] = {
    "min_dscr": {"check": "PC-DSCR", "label": "Minimum DSCR after the new facility", "metric": "dscr_post", "op": ">=", "unit": "x",
                 "table": "uae_desk", "key": "cash_flow_cover", "where": "Admin -> Deal Desk Parameters: cash-flow cover (uae_desk.cash_flow_cover)"},
    "max_leverage": {"check": "PC-LEV", "label": "Maximum debt / EBITDA after the new facility", "metric": "debt_ebitda_post", "op": "<=",
                     "unit": "x", "table": "uae_desk", "key": "max_leverage", "where": "Admin -> Deal Desk Parameters: maximum leverage (uae_desk.max_leverage)"},
    "min_collateral_cover": {"check": "PC-COVER", "label": "Minimum collateral cover (pledged collateral / financing)", "metric": "collateral_cover",
                             "op": ">=", "unit": "%", "table": "rulebook", "key": "min_collateral_cover",
                             "where": "Not a Deal Desk parameter today: the policy adds it"},
    "max_ltv": {"check": "PC-LTV", "label": "Maximum financing-to-value (LTV: amount / pledged collateral)", "metric": "ltv", "op": "<=",
                "unit": "%", "table": "rulebook", "key": "max_ltv", "where": "Not a Deal Desk parameter today: the policy adds it"},
    "max_tenor_years": {"check": "PC-TENOR", "label": "Maximum tenor", "metric": "tenor_years", "op": "<=", "unit": "years", "table": "uae_desk",
                        "key": "tenor_cap_years", "where": "Admin -> Deal Desk Parameters: tenor caps by product (uae_desk.tenor_cap_years)"},
    "max_valuation_age_days": {"check": "PC-VAL", "label": "Collateral valuation no older than", "metric": "valuation_age_days", "op": "<=",
                               "unit": "days", "table": "rulebook", "key": "max_valuation_age_days",
                               "where": "Credit policy (documents.json validity of the valuation report)"},
    "min_raroc": {"check": "PC-RAROC", "label": "Lifetime RAROC at least the hurdle", "metric": "lifetime_raroc", "op": ">=", "unit": "%",
                  "table": "returns", "key": "hurdle_sector", "where": "Admin -> Deal Desk Parameters: hurdle by segment and sector (returns)"},
    "min_rating": {"check": "PC-RATING", "label": "Minimum internal rating", "metric": "rating", "op": ">=", "unit": "grade", "table": "rulebook",
                   "key": "min_rating", "where": "Not a Deal Desk parameter today: the policy adds it"},
}
#: the rulebook's own seed for thresholds Deal Desk had no table for (None: no requirement in force)
SEED = {"min_collateral_cover": None, "max_ltv": None, "max_valuation_age_days": 365, "min_rating": None}
TENOR_CLASS = {"term_loan": "Term finance", "revolver": "Term finance", "trade_lc": "Working capital", "overdraft": "Working capital",
               "working_capital": "Working capital", "performance_lg": "Guarantees", "bid_bond": "Guarantees", "guarantee": "Guarantees",
               "advance_payment_lg": "Guarantees", "vehicle": "Vehicle finance"}


def _desk() -> dict[str, Any]:
    try:
        from backend.dealdesk import desk_params
        return desk_params.rows()
    except Exception:  # noqa: BLE001
        return {}


def base(param: str, fact: dict[str, Any], desk: dict[str, Any] | None = None) -> tuple[Any, str]:
    """The value in force for this deal before any approved policy, and where it comes from."""
    desk = _desk() if desk is None else desk
    if param == "min_dscr":
        return desk.get("cash_flow_cover", 1.25), "uae_desk.cash_flow_cover"
    if param == "max_leverage":
        return desk.get("max_leverage", 4.0), "uae_desk.max_leverage"
    if param == "max_tenor_years":
        caps = desk.get("tenor_cap_years") or {}
        cls = "Real estate" if str(fact.get("sector")) == "Real Estate" and fact.get("facility_type") == "term_loan" else \
            TENOR_CLASS.get(str(fact.get("facility_type")), "Term finance")
        return caps.get(cls), f"uae_desk.tenor_cap_years[{cls}]"
    if param == "min_raroc":
        return fact.get("hurdle"), "returns.hurdle / hurdle_sector (the deal's hurdle)"
    return SEED.get(param), "rulebook seed"


def _matches(segment: str, fact: dict[str, Any]) -> bool:
    s = (segment or "all").strip().lower()
    if s in ("all", "", "*"):
        return True
    sector = str(fact.get("sector") or "").lower()
    if s in ("construction", "contracting", "contractors") and sector == "construction":
        return True
    return s == sector or (len(s) > 3 and s in sector)


def threshold(param: str, fact: dict[str, Any], overlay: dict[str, list[dict[str, Any]]], desk: dict[str, Any] | None = None) -> tuple[Any, str, dict | None]:
    """(value, where from, the overlay entry that set it): a sector entry beats an all-deals entry; the latest of each wins."""
    entries = [e for e in overlay.get(param, []) if _matches(e.get("segment", "all"), fact)]
    if entries:
        entries.sort(key=lambda e: (e.get("segment", "all").lower() not in ("all", "", "*"), e.get("seq", 0)))
        e = entries[-1]
        return e["value"], f"{e.get('reference') or e.get('assessment_id')} {e.get('clause') or ''}".strip(), e
    v, src = base(param, fact, desk)
    return v, src, None


def _cmp(op: str, value: Any, limit: Any, unit: str) -> bool:
    if unit == "grade":
        a = RATINGS.index(value) if value in RATINGS else len(RATINGS)
        b = RATINGS.index(limit) if limit in RATINGS else len(RATINGS)
        return a <= b  # a better grade sits earlier in the scale
    return value >= limit - 1e-9 if op == ">=" else value <= limit + 1e-9


def fmt(v: Any, unit: str) -> str:
    if v is None:
        return "–"
    if unit == "x":
        return f"{float(v):.2f}x"
    if unit == "%":
        x = round(float(v) * 100, 1)
        return f"{x:.0f}%" if x.is_integer() else f"{x:.1f}%"
    if unit == "years":
        return f"{float(v):g} years"
    if unit == "days":
        return f"{int(v)} days"
    return str(v)


def evaluate(fact: dict[str, Any], overlay: dict[str, list[dict[str, Any]]], params: list[str] | None = None,
             desk: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    desk = _desk() if desk is None else desk
    out = []
    for p in params or list(PARAMS):
        d = PARAMS[p]
        limit, src, entry = threshold(p, fact, overlay, desk)
        value = fact.get(d["metric"])
        if limit is None:
            res = "na"
            why = "no requirement in force"
        elif value is None:
            res = "na"
            why = "the deal file does not give it"
        else:
            res = "pass" if _cmp(d["op"], value, limit, d["unit"]) else "fail"
            why = f"{fmt(value, d['unit'])} against {'at least' if d['op'] == '>=' else 'at most'} {fmt(limit, d['unit'])}"
        out.append({"check": d["check"], "param": p, "label": d["label"], "value": value, "threshold": limit, "unit": d["unit"],
                    "result": res, "why": why, "source": src, "clause": (entry or {}).get("clause", ""),
                    "quote": (entry or {}).get("quote", ""), "assessment_id": (entry or {}).get("assessment_id", "")})
    return out
