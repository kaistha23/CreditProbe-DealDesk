"""Clean vs exception: the explicit criteria the renewal autopilot applies (R14 backlog #5, PLAN_R13 §I).

A renewal is CLEAN when no CREDIT criterion fires; any credit criterion firing makes it an EXCEPTION, which goes to the CCO
with the full paper. COMMERCIAL criteria (RAROC below hurdle, a promise unmet) never make a renewal an exception on their own:
they are actions the RM carries into the renewal (the repricing margin from the Book's repricing engine, the promise to
re-commit) and are printed on the one-page note as renewal conditions. Each criterion names its metric, operator, threshold and the relation it reads, so the queue can show exactly why.
Thresholds are parameters (one dict), not buried in code.
"""
from __future__ import annotations

from typing import Any

#: id -> definition. `column` is a column of the prepared review frame (pack.prepare).
CRITERIA: list[dict[str, Any]] = [
    {"id": "stage", "label": "IFRS 9 stage 2 or 3", "column": "stage", "op": ">=", "threshold": 2,
     "source": "ews.corp_exposure.stage"},
    {"id": "dpd", "label": "Days past due on the facility", "column": "dpd_days", "op": ">", "threshold": 0,
     "source": "ews.corp_exposure.dpd_days"},
    {"id": "ews", "label": "Early Warning band high or critical", "column": "ews_severe", "op": "=", "threshold": 1,
     "source": "ews.corp_exposure.ews_band"},
    {"id": "watchlist", "label": "On the watchlist or restructured", "column": "watch_or_restructured", "op": "=", "threshold": 1,
     "source": "ews.corp_exposure.watchlist_flag / restructured_flag"},
    {"id": "downgrade", "label": "Rating down 2+ notches since origination", "column": "notches", "op": ">=", "threshold": 2,
     "source": "ecl_runs.ecl_facility.rating vs origination.orig_facility"},
    {"id": "covenant_breach", "label": "A covenant in breach at the last test", "column": "covenants_breached", "op": ">", "threshold": 0,
     "source": "ews.corp_covenant.breach_flag"},
    {"id": "covenant_headroom", "label": "Covenant headroom below 10%", "column": "covenant_min_headroom_pct", "op": "<", "threshold": 10.0,
     "source": "ews.corp_covenant.headroom_pct"},
    {"id": "conditions", "label": "An approval condition overdue or not complied", "column": "conditions_overdue", "op": ">", "threshold": 0,
     "source": "deal_desk.dd_condition"},
    {"id": "promise", "label": "A routing or cross-sell promise unmet", "column": "promise_unmet", "op": "=", "threshold": 1,
     "source": "deal_desk.dd_promise", "kind": "commercial"},
    {"id": "raroc", "label": "RAROC below the hurdle", "column": "raroc_gap_pp", "op": "<", "threshold": 0.0,
     "source": "book drift (raroc_now − hurdle)", "kind": "commercial"},
    {"id": "ebitda_fall", "label": "EBITDA down more than 15% year on year", "column": "ebitda_yoy_pct", "op": "<", "threshold": -15.0,
     "source": "cockpit.corp_borrower_quarter.ebitda_sar_mn"},
    {"id": "leverage_up", "label": "Leverage up more than 1.0x year on year", "column": "leverage_change_x", "op": ">", "threshold": 1.0,
     "source": "cockpit.corp_borrower_quarter.leverage_x"},
    {"id": "dscr_low", "label": "DSCR below the policy floor 1.20x (CP-2.1)", "column": "dscr_x", "op": "<", "threshold": 1.20,
     "source": "cockpit.corp_borrower_quarter.dscr_x"},
    {"id": "bureau_dpd", "label": "Past due at other banks (bureau)", "column": "bureau_dpd_days", "op": ">", "threshold": 0,
     "source": "bureau.bureau_corp_quarter.external_dpd_days"},
    {"id": "bureau_default", "label": "Default reported at another bank (bureau)", "column": "bureau_default", "op": "=", "threshold": 1,
     "source": "bureau.bureau_corp_quarter.external_default_flag"},
    {"id": "bureau_debt", "label": "Debt at other banks more than doubled in the quarter", "column": "bureau_exposure_change_pct", "op": ">", "threshold": 100.0,
     "source": "bureau.bureau_corp_quarter.external_exposure_sar_mn"},
    {"id": "cheques", "label": "Cheques returned in the last 3 months", "column": "cheques_returned_3m", "op": ">", "threshold": 0,
     "source": "deposits.dep_month.cheques_returned_count"},
    {"id": "inflow_fall", "label": "Account inflows down more than 30% (last 3 months vs prior 6)", "column": "inflow_change_pct", "op": "<", "threshold": -30.0,
     "source": "deposits.dep_month.credit_turnover_sar_mn"},
    {"id": "payroll", "label": "Payroll run missed in the last 3 months", "column": "payroll_missed_3m", "op": ">", "threshold": 0,
     "source": "deposits.dep_month.payroll_flag"},
    {"id": "tier_high", "label": "Monitoring tier High", "column": "tier_high", "op": "=", "threshold": 1,
     "source": "deal_desk.dd_monitoring_plan.tier"},
    {"id": "trigger", "label": "A named monitoring trigger hit", "column": "trigger_flag", "op": "=", "threshold": 1,
     "source": "deal_desk.dd_monitoring_plan.named_triggers"},
    {"id": "findings", "label": "Open high or critical review finding", "column": "findings_high_open", "op": ">", "threshold": 0,
     "source": "deal_desk.dd_review_finding"},
]

for _c in CRITERIA:
    _c.setdefault("kind", "credit")

BY_ID = {c["id"]: c for c in CRITERIA}
CREDIT = [c["id"] for c in CRITERIA if c["kind"] == "credit"]
COMMERCIAL = [c["id"] for c in CRITERIA if c["kind"] == "commercial"]

_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, "=": lambda a, b: a == b}


def fires(c: dict[str, Any], value: Any) -> bool:
    """A criterion fires on a known value only; an unknown value never fires (it is reported as a data limit)."""
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    if v != v:
        return False
    return bool(_OPS[c["op"]](v, float(c["threshold"])))


def describe() -> list[dict[str, Any]]:
    return [{k: c[k] for k in ("id", "label", "op", "threshold", "source", "kind")} for c in CRITERIA]
