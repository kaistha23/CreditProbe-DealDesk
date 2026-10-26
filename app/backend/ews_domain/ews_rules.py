"""
Governed early-warning rules (EWS rule set v1) over the published books.

Deterministic, versioned SQL over fields the release actually publishes. No
field is invented: where the specification names a signal the candidate book
does not carry directly (a salary-credit feed), the rule is a stated PROXY and
the limitation travels with every card, cohort and metric that uses it.

Each rule is a SQL boolean over the latest-period grid view (`grid.py`
aliases), a severity weight and a reason label. The severity of an entity is
the sum of the weights of the rules it trips, banded by the book's own floors
(`BAND_FLOORS`): critical, high, moderate, then low from 1, else none.

Versions. gw-ews-1.3.0 is live (PLAN_R5 Session E, the Early Warning story,
docs/v5/EWS_STORY.md). gw-ews-1.2.0 (Bureau and Open Banking signals, INBOX Item 3) is recorded. gw-ews-1.1.0 (v5/main) and 1.0.0 stay recorded. 1.1.0 was (INBOX Item 1, 2026-10-10): retail takes the
docs/v5/EWS_UAT.md section 7 recalibration and a working R-SCORE-DOWN (a fall
of 2 or more behaviour bands); corporate adds C-DEFAULT and the recalibrated
weights from ops/ews_calibration.py --v110. gw-ews-1.0.0 stays recorded,
unchanged, in `RULESETS` and on the model page's log.
"""

from __future__ import annotations

from typing import Any

RULESET_VERSION = "gw-ews-1.3.0"

#: gw-ews-1.0.0, as restored and run until 2026-10-10. Recorded, not used.
RULES_1_0_0: dict[str, list[dict[str, Any]]] = {
    "retail": [
        {"id": "R-DPD", "label": "Payment arrears (DPD > 0)",
         "sql": "dpd_days > 0", "weight": 3},
        {"id": "R-SCORE-LOW", "label": "Weak behaviour score band (D/E)",
         "sql": "score_band IN ('D', 'E')", "weight": 1},
        {"id": "R-SCORE-DOWN", "label": "Behaviour score deteriorated",
         "sql": "score_migration = 'Deteriorated'", "weight": 2},
        {"id": "R-UTIL", "label": "High utilisation (>= 85%)",
         "sql": "utilisation_pct >= 85", "weight": 2},
        {"id": "R-MINPAY", "label": "Persistent minimum payment (payment ratio < 35%)",
         "sql": "payment_ratio_pct < 35", "weight": 1},
        {"id": "R-SALARY", "label": "Salary-interruption proxy (salaried, cyclical employer, payment ratio < 35%)",
         "sql": ("employment_type IN ('Salaried-Private', 'Salaried-Government') "
                 "AND employer_sector_group = 'Cyclical' AND payment_ratio_pct < 35"),
         "weight": 2,
         "limitation": ("The candidate book publishes no salary-credit feed. "
                        "This proxy combines employment type, employer sector "
                        "cyclicality and a low payment ratio; it is a governed "
                        "stand-in, not an observed salary interruption.")},
    ],
    "corporate": [
        {"id": "C-WATCH", "label": "On watchlist", "sql": "watchlist_flag = 1",
         "weight": 3},
        {"id": "C-DOWNGRADE", "label": "Rating downgraded this quarter",
         "sql": "rating_notches_moved > 0", "weight": 2},
        {"id": "C-COVENANT", "label": "Covenant breach", "sql": "covenant_breaches > 0",
         "weight": 2},
        {"id": "C-DPD", "label": "Past due (DPD > 0)", "sql": "dpd_days > 0",
         "weight": 3},
        {"id": "C-SICR", "label": "SICR flag raised", "sql": "sicr_flag = 1",
         "weight": 2},
        {"id": "C-UTIL", "label": "High utilisation (>= 90%)",
         "sql": "utilisation_pct >= 90", "weight": 1},
    ],
}

BAND_FLOORS_1_0_0 = {"corporate": (2, 4, 6), "retail": (2, 4, 6)}

_SALARY = RULES_1_0_0["retail"][5]

#: gw-ews-1.1.0, as run 2026-10-10 on v5/main. Recorded, not used.
RULES_1_1_0: dict[str, list[dict[str, Any]]] = {
    "retail": [
        {"id": "R-DPD", "label": "Payment arrears (DPD > 0)",
         "sql": "dpd_days > 0", "weight": 4},
        {"id": "R-SCORE-LOW", "label": "Weak behaviour score band (E)",
         "sql": "score_band = 'E'", "weight": 1},
        # 1.0.0 compared score_migration to 'Deteriorated' (the book writes
        # 'DETERIORATED') and so never fired; any fall would fire on 55% of
        # accounts. 1.1.0 limits it to a fall of 2 or more behaviour bands
        # since last month (A best .. E worst), on the customer's bands.
        {"id": "R-SCORE-DOWN", "label": "Behaviour score fell 2 or more bands",
         "sql": ("(customer_score_band_previous = 'A' AND customer_score_band IN ('C', 'D', 'E')) "
                 "OR (customer_score_band_previous = 'B' AND customer_score_band IN ('D', 'E')) "
                 "OR (customer_score_band_previous = 'C' AND customer_score_band = 'E')"),
         "weight": 2},
        {"id": "R-UTIL", "label": "High utilisation (>= 85%)",
         "sql": "utilisation_pct >= 85", "weight": 2},
        {"id": "R-MINPAY", "label": "Persistent minimum payment (payment ratio < 30%)",
         "sql": "payment_ratio_pct < 30", "weight": 1},
        dict(_SALARY),
    ],
    # ops/ews_calibration.py --v110: the best of 25,920 combinations that meets
    # the targets with every already-bad borrower warned, no rule switched
    # off and a non-empty critical band (evidence/v5/ews/calibration/
    # ruleset_1_1_0.json). The book carries no 1-29 DPD values, so DPD > 59
    # reads 90+ here.
    "corporate": [
        {"id": "C-WATCH", "label": "On watchlist", "sql": "watchlist_flag = 1",
         "weight": 1},
        {"id": "C-DOWNGRADE", "label": "Rating downgraded this quarter",
         "sql": "rating_notches_moved > 0", "weight": 2},
        {"id": "C-COVENANT", "label": "Covenant breach", "sql": "covenant_breaches > 0",
         "weight": 1},
        {"id": "C-DPD", "label": "Past due (DPD > 59)", "sql": "dpd_days > 59",
         "weight": 2},
        {"id": "C-SICR", "label": "SICR flag raised", "sql": "sicr_flag = 1",
         "weight": 1},
        {"id": "C-UTIL", "label": "High utilisation (>= 95%)",
         "sql": "utilisation_pct >= 95", "weight": 1},
        # New in 1.1.0 (INBOX Item 1.2).
        {"id": "C-DEFAULT", "label": "Stage 3 or in default",
         "sql": "stage = 3 OR default_flag = 1", "weight": 2},
    ],
}

BAND_FLOORS_1_1_0 = {"corporate": (4, 7, 9), "retail": (3, 5, 7)}

_R = {r["id"]: r for r in RULES_1_1_0["retail"]}
_C = {r["id"]: r for r in RULES_1_1_0["corporate"]}

#: gw-ews-1.2.0, as run 2026-10-10 .. 2026-10-11 (INBOX Item 3, A5). Recorded, not used: Bureau and Open Banking signals
#: from the synthetic external domains (backend/ext_domains). Calibrated by
#: ops/ews_calibration.py --v120 (evidence/v5/ews/calibration/ruleset_1_2_0.json).
#: R-SALARY (a proxy that was never live) is REPLACED by R-OB-SALARY, the
#: observed salary-credit signal; no rule is switched off.
RULES_1_2_0: dict[str, list[dict[str, Any]]] = {
    "retail": [
        _R["R-DPD"], _R["R-SCORE-LOW"], _R["R-SCORE-DOWN"], _R["R-UTIL"], _R["R-MINPAY"],
        {"id": "R-BUR-SCORE", "label": "Bureau score below 560",
         "sql": "bureau_score < 560", "weight": 2},
        {"id": "R-BUR-EXTDPD", "label": "Past due at another lender (external DPD > 59)",
         "sql": "external_dpd_days > 59", "weight": 1},
        {"id": "R-BUR-ENQ", "label": "5 or more bureau enquiries in 3 months",
         "sql": "enquiries_3m >= 5", "weight": 2},
        {"id": "R-OB-SALARY", "label": "Salary credit missing this month (salaried customer)",
         "sql": "salary_interruption_flag = 1", "weight": 1},
        {"id": "R-OB-BUFFER", "label": "Balance buffer under 1 month of obligations",
         "sql": "balance_buffer_months < 1.0", "weight": 2},
        {"id": "R-OB-INFLOW", "label": "Account inflows fell by 30 per cent or more in 3 months",
         "sql": "inflow_trend_pct <= -30", "weight": 2},
    ],
    "corporate": [
        # C-DOWNGRADE FIXED in 1.2.0: the book writes rating_notches_moved
        # POSITIVE for an upgrade and NEGATIVE for a downgrade (rating_migration
        # agrees on every row), so "> 0" (1.0.0, 1.1.0) fired on upgrades.
        {**_C["C-WATCH"], "weight": 2},
        {"id": "C-DOWNGRADE", "label": "Rating downgraded this quarter",
         "sql": "rating_notches_moved < 0", "weight": 1},
        _C["C-COVENANT"], _C["C-DPD"], _C["C-SICR"],
        {"id": "C-UTIL", "label": "High utilisation (>= 98%)", "sql": "utilisation_pct >= 98", "weight": 1},
        _C["C-DEFAULT"],
        {"id": "C-BUR-EXTDPD", "label": "Past due at another lender (external DPD > 59)",
         "sql": "external_dpd_days > 59", "weight": 2},
        {"id": "C-OB-INFLOW", "label": "Operating inflows fell by 20 per cent or more on the quarter",
         "sql": "inflow_trend_pct <= -20", "weight": 1},
    ],
}

BAND_FLOORS_1_2_0: dict[str, tuple[int, int, int]] = {"corporate": (5, 9, 11), "retail": (4, 7, 9)}

_R2 = {r["id"]: r for r in RULES_1_2_0["retail"]}
_C2 = {r["id"]: r for r in RULES_1_2_0["corporate"]}

#: gw-ews-1.3.0, live (PLAN_R5 Session E): the Early Warning story. Calibrated by
#: ops/ews_story_calibration.py (evidence/v5/ews/calibration/ruleset_1_3_0.json) to the same targets
#: and constraints, plus at least 2 improving and 2 deteriorating segments per level.
#:   * R-MINPAY reads CHANGE as well as level: the book's payment ratio drifts down in every product in
#:     the last four months, and a level threshold alone fired on 0 customers in March and 7,710 in August.
#:   * C-OB-INFLOW compares with the same quarter a year earlier: quarterly revenue is seasonal, and the
#:     change on the previous quarter fired on 360-530 borrowers every Q1.
#:   * Three corporate external signals join (bureau enquiries, operating balance buffer, returned
#:     payments): the payment-chain signals behind the Construction story.
RULES: dict[str, list[dict[str, Any]]] = {
    "retail": [
        {**_R2["R-DPD"], "weight": 3}, _R2["R-SCORE-LOW"], _R2["R-SCORE-DOWN"], _R2["R-UTIL"],
        {"id": "R-MINPAY", "label": "Payment ratio below 30% and down 10 points or more in 3 months",
         "sql": "payment_ratio_pct < 30 AND payment_ratio_change_3m <= -10", "weight": 1},
        {"id": "R-BUR-SCORE", "label": "Bureau score below 580", "sql": "bureau_score < 580", "weight": 1},
        _R2["R-BUR-EXTDPD"], _R2["R-BUR-ENQ"],
        {**_R2["R-OB-SALARY"], "weight": 2},
        {**_R2["R-OB-BUFFER"], "weight": 1},
        {"id": "R-OB-INFLOW", "label": "Account inflows fell by 40 per cent or more in 3 months",
         "sql": "inflow_trend_pct <= -40", "weight": 1},
    ],
    "corporate": [
        {**_C2["C-WATCH"], "weight": 1}, _C2["C-DOWNGRADE"], _C2["C-COVENANT"], _C2["C-DPD"], _C2["C-SICR"],
        _C2["C-UTIL"], _C2["C-DEFAULT"],
        {**_C2["C-BUR-EXTDPD"], "weight": 3},
        {"id": "C-BUR-ENQ", "label": "2 or more bureau enquiries this quarter",
         "sql": "enquiries_q >= 2", "weight": 1},
        {"id": "C-OB-INFLOW", "label": "Operating inflows fell by 30 per cent or more on the year",
         "sql": "inflow_trend_pct <= -30", "weight": 1},
        {"id": "C-OB-BUFFER", "label": "Operating balance under 1 month of obligations",
         "sql": "balance_buffer_months < 1.0", "weight": 1},
        {"id": "C-OB-RETURNED", "label": "2 or more returned payments this quarter",
         "sql": "returned_payments_q >= 2", "weight": 1},
    ],
}

#: (moderate, high, critical) score floors per book; low is any score from 1.
BAND_FLOORS: dict[str, tuple[int, int, int]] = {"corporate": (4, 8, 10), "retail": (3, 5, 7)}

#: Every rule set this service has run, newest first.
RULESETS: dict[str, dict[str, Any]] = {
    "gw-ews-1.3.0": {"status": "active", "rules": RULES, "band_floors": BAND_FLOORS,
                     "effective": "2026-10-12 (v5/r5)",
                     "change": ("The Early Warning story (docs/v5/EWS_STORY.md). Bureau and Open Banking signals "
                                "generated per segment story instead of one book-wide shock. Retail: R-MINPAY needs "
                                "a fall of 10 points in 3 months as well as a ratio under 30%; R-BUR-SCORE under "
                                "580; R-OB-INFLOW at -40%; R-DPD weight 3, R-OB-SALARY 2, R-OB-BUFFER 1; bands "
                                "3/5/7. Corporate: C-OB-INFLOW year on year at -30%; new C-BUR-ENQ, C-OB-BUFFER, "
                                "C-OB-RETURNED; C-WATCH weight 1, C-BUR-EXTDPD 3; bands 4/8/10 "
                                "(ops/ews_story_calibration.py).")},
    "gw-ews-1.2.0": {"status": "superseded", "rules": RULES_1_2_0, "band_floors": BAND_FLOORS_1_2_0,
                     "effective": "2026-10-10 (v5/next)",
                     "change": ("Bureau and Open Banking go live (domains keyed to the spine). Retail: "
                                "R-BUR-SCORE, R-BUR-EXTDPD, R-BUR-ENQ, R-OB-SALARY (replaces the R-SALARY proxy), "
                                "R-OB-BUFFER, R-OB-INFLOW; bands 4/7/9. Corporate: C-BUR-EXTDPD, C-OB-INFLOW; "
                                "C-DOWNGRADE FIXED to fire on downgrades (rating_notches_moved < 0; it fired on "
                                "upgrades up to 1.1.0); C-WATCH weight 2, C-DOWNGRADE weight 1, C-UTIL >= 98%; "
                                "bands 5/9/11 (ops/ews_calibration.py --v120).")},
    "gw-ews-1.1.0": {"status": "superseded", "rules": RULES_1_1_0, "band_floors": BAND_FLOORS_1_1_0,
                     "effective": "2026-10-10",
                     "change": ("Retail: EWS_UAT section 7 recalibration; R-SCORE-DOWN limited to a fall of "
                                "2+ behaviour bands. Corporate: new rule C-DEFAULT (Stage 3 or default flag) "
                                "and recalibrated weights and bands (ops/ews_calibration.py --v110).")},
    "gw-ews-1.0.0": {"status": "superseded", "rules": RULES_1_0_0, "band_floors": BAND_FLOORS_1_0_0,
                     "effective": "restoration",
                     "change": "As restored; R-SCORE-DOWN never fired (case mismatch)."},
}


def bands(domain_id: str) -> tuple[tuple[int, str], ...]:
    """`((floor, name), ...)` worst first, for one book."""
    mod, high, crit = BAND_FLOORS[domain_id]
    return ((crit, "critical"), (high, "high"), (mod, "moderate"), (1, "low"))


def floor(domain_id: str, band: str) -> int:
    return next(f for f, n in bands(domain_id) if n == band)


def band_of(domain_id: str, score: float | int | None) -> str:
    s = int(score or 0)
    for f, name in bands(domain_id):
        if s >= f:
            return name
    return "none"


def score_sql(domain_id: str, available: set[str]) -> tuple[str, str]:
    """`(score_expr, reasons_expr)` using only rules whose columns exist."""
    parts, reasons = [], []
    for rule in RULES[domain_id]:
        needed = _columns(rule["sql"])
        if not needed <= available:
            continue
        parts.append(f"(CASE WHEN {rule['sql']} THEN {rule['weight']} ELSE 0 END)")
        reasons.append(f"CASE WHEN {rule['sql']} THEN '{rule['label']}' END")
    score = " + ".join(parts) or "0"
    reason = ("concat_ws('; ', " + ", ".join(reasons) + ")") if reasons else "''"
    return score, reason


def band_sql(score: str, domain_id: str) -> str:
    whens = " ".join(f"WHEN ({score}) >= {f} THEN '{name}'"
                     for f, name in bands(domain_id))
    return f"CASE {whens} ELSE 'none' END"


def _columns(sql: str) -> set[str]:
    import re

    unquoted = re.sub(r"'[^']*'", "", sql)
    words = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", unquoted))
    keywords = {"in", "and", "or", "not", "null", "is", "case", "when", "then",
                "else", "end", "true", "false"}
    return {w for w in words if w not in keywords and not w.isupper()}


def describe(domain_id: str) -> list[dict[str, Any]]:
    return [{k: v for k, v in r.items()} for r in RULES[domain_id]]


__all__ = ["BAND_FLOORS", "RULESETS", "RULESET_VERSION", "RULES", "RULES_1_0_0", "RULES_1_1_0", "RULES_1_2_0",
           "band_of", "band_sql", "bands", "describe", "floor", "score_sql"]
