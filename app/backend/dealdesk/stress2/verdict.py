"""The stress verdict -> action rule and the monitoring tier (PLAN_R12 §1.5, I22-4; Anne accepted the rule as written).

| Worst severity that still breaks something | Verdict                          | Tier     | Review     |
|---|---|---|---|
| Mild (or the structure fails before stress) | Restructure                     | High (provisional, until restructured) | quarterly |
| Moderate                                     | Approve with enhanced monitoring | High     | quarterly  |
| Severe only                                  | Approve, standard monitoring     | Medium   | semi-annual |
| None                                         | Approve                          | Standard | annual     |

"Breaks" means a new breach (one the base row does not already have) of DSCR 1.0 or its limit, Debt/EBITDA, LTV,
a covenant, the minimum rating, Stage 1, the checked RAROC hurdle, or a hard limit. For the rating family, Stage 2
at the policy's SICR notch count is the scenario's own definition and is not counted (its RAROC, limits and
minimum-rating tests are). The driver is the shock behind the mildest breaking rows; it becomes a named trigger.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import stress_lab as sl
from backend.dealdesk.stress2.ladder import SEV_RANK

RULES = [
    {"severity": "mild", "verdict": "Restructure", "tier": "High", "review_months": 3,
     "action": "Cannot recommend as asked: the Structure step opens with the fix (tighter covenant, more collateral, shorter tenor or a lower amount)."},
    {"severity": "moderate", "verdict": "Approve with enhanced monitoring", "tier": "High", "review_months": 3,
     "action": "Monitoring tier High: quarterly review, tighter Early Warning thresholds, the stressed driver as a named trigger."},
    {"severity": "severe", "verdict": "Approve, standard monitoring", "tier": "Medium", "review_months": 6,
     "action": "Monitoring tier Medium: semi-annual review, the driver watched."},
    {"severity": "none", "verdict": "Approve", "tier": "Standard", "review_months": 12,
     "action": "Monitoring tier Standard: annual review."},
]
RULE_BY_SEV = {r["severity"]: r for r in RULES}

#: scenario family / shock -> the driver it stresses
DRIVER_LABEL = {
    "revenue": "Revenue", "margin": "EBITDA margin", "customer": "Largest-customer concentration", "payment_delay": "Payment delays",
    "project_delay": "Project delays", "rates": "Benchmark rates", "collateral": "Collateral value", "rating": "Rating",
    "guarantee": "Guarantee enforceability", "dscr": "Debt service cover", "pricing": "Pricing (RAROC below the hurdle before stress)",
}


def driver_of(row: dict[str, Any]) -> str:
    sid = row["id"]
    res = row.get("resolved") or {}
    if row.get("family") == "rating":
        return "rating"
    if sid.startswith("cust"):
        return "customer"
    if sid.startswith("paydelay"):
        return "payment_delay"
    if sid.startswith("delay"):
        return "project_delay"
    if sid.startswith("margin"):
        return "margin"
    if sid.startswith("rates"):
        return "rates"
    if sid == "guarantee_void":
        return "guarantee"
    if sid.startswith(("coll", "re_")) and abs(res.get("revenue_pct", 0.0)) < 1e-12:
        return "collateral"
    if abs(res.get("revenue_pct", 0.0)) > 1e-12:
        return "revenue"
    if res.get("rate_bps"):
        return "rates"
    if res.get("notches"):
        return "rating"
    return "revenue"


def verdict(rows: list[dict[str, Any]], base: dict[str, Any], base_fails: set[str]) -> dict[str, Any]:
    breaking = [r for r in rows if r["applicable"] and r.get("breaks")]
    by_sev: dict[str, list[dict[str, Any]]] = {}
    for r in breaking:
        sev = r["severity"] if r["severity"] in ("mild", "moderate", "severe") else "severe"
        by_sev.setdefault(sev, []).append(r)
    if base_fails:
        worst = "mild"
        rule = RULE_BY_SEV["mild"]
        first = {"id": "base", "label": "Base (no stress)", "tests": sorted(base_fails, key=sl.METRIC_CELLS.index), "severity": "none"}
        why = "the structure already fails " + ", ".join(sl.CELL_LABELS[c] for c in first["tests"]) + " before any stress"
    elif breaking:
        worst = min(by_sev, key=lambda s: SEV_RANK[s])
        rule = RULE_BY_SEV[worst]
        rs = sorted(by_sev[worst], key=lambda r: (-len(r["breaks"]), r["label"]))
        first = {"id": rs[0]["id"], "label": rs[0]["label"], "tests": rs[0]["breaks"], "severity": worst}
        why = f"{rs[0]['label']} ({worst}) breaks " + ", ".join(sl.CELL_LABELS[c] for c in rs[0]["breaks"])
    else:
        worst = "none"
        rule = RULE_BY_SEV["none"]
        first = None
        why = "no applicable scenario breaks a test"
    drivers: list[str] = []
    for r in by_sev.get(worst, []) if worst != "none" else []:
        d = driver_of(r)
        if d not in drivers:
            drivers.append(d)
    if base_fails and "dscr" in base_fails:
        drivers.insert(0, "dscr")
    if base_fails and "raroc" in base_fails:
        drivers.insert(0, "pricing")
    return {"verdict": rule["verdict"], "action": rule["action"], "worst_breaking_severity": worst, "first_break": first, "why": why,
            "drivers": drivers, "driver_labels": [DRIVER_LABEL[d] for d in drivers],
            "breaking": {s: [r["id"] for r in v] for s, v in by_sev.items()}, "rule": RULES,
            "restructure": rule["verdict"] == "Restructure"}


def tier_for(v: dict[str, Any], rows: list[dict[str, Any]], rv: dict[str, Any] | None, lab: sl.Lab, facts: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.monitoring import rules as mr
    sev = v["worst_breaking_severity"]
    rule = RULE_BY_SEV[sev]
    tier = rule["tier"]
    triggers = mr.triggers_for(tier, v["drivers"], rows, rv, lab, facts)
    return {"tier": tier, "review_frequency_months": rule["review_months"], "provisional": rule["verdict"] == "Restructure",
            "drivers": v["drivers"], "driver_labels": v["driver_labels"], "triggers": triggers,
            "ews_thresholds": mr.ews_thresholds(tier),
            "reason": (f"Stress verdict {rule['verdict']}: {v['why']}." if sev != "none" else "Stress verdict Approve: no applicable scenario breaks a test."),
            "note": "Provisional until the structure is fixed and stressed again." if rule["verdict"] == "Restructure" else ""}
