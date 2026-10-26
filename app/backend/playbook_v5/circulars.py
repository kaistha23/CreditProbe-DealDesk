"""The seeded circular: C-2026-03, strengthening the assessment of significant increase in credit risk.

Written in the form of a supervisory circular as the bank's Credit Risk Policy unit implements it: reference,
date, addressees, purpose, the amended clauses in full, the effective date and the transitional rule. It amends
RP-5.1 (retail SICR) and CP-3.3 (corporate SICR) and adds CP-3.4 (sector watch for construction contractors).
Each clause carries `summary`, the short phrase an explanation of a movement quotes ("RP-5.1 now treats ...").
"""
from __future__ import annotations

from typing import Any

C_2026_03: dict[str, Any] = {
    "id": "pd_circ_c_2026_03",
    "reference": "C-2026-03",
    "title": "Circular C-2026-03: Strengthening the assessment of significant increase in credit risk",
    "kind": "circular",
    "book": "both",
    "issued": "2026-06-10",
    "effective_from": "2026-07-01",
    "issuer": "Chief Risk Officer, Credit Risk Policy",
    "approved_by": "noura.alharbi",
    "addressees": "Heads of Corporate Credit, Retail Credit, IFRS 9 and Model Validation; Early Warning owners",
    "purpose": (
        "Following the supervisory review of IFRS 9 staging practice across the sector and the guidance on "
        "forward-looking assessment of significant increase in credit risk (SICR), the Bank tightens its staging "
        "triggers. Rating and score migration is to be recognised earlier and consistently across both books, and "
        "contractors with weak debt service are placed under a sector watch."),
    "summary": (
        "Amends RP-5.1 so that a fall of two or more behavioural risk grades (a 2-notch downgrade) or a fall of more "
        "than 90 points since origination is SICR; amends CP-3.3 so that placement on the watchlist is SICR in "
        "addition to a 2-notch downgrade; adds CP-3.4, a sector watch for construction contractors with DSCR below "
        "1.10x. Effective 1 July 2026, applied from the 2026Q3 reporting date with no restatement of prior periods."),
    "clauses": [
        {"clause": "RP-5.1", "book": "retail", "section": "RP-5", "section_title": "Staging and provisioning",
         "title": "Significant increase in credit risk",
         "rule": ("An account moves to Stage 2 on any of: 30 days past due; a behavioural score below 520; a fall of "
                  "two or more behavioural risk grades since origination (a 2-notch downgrade); a fall of more than 90 "
                  "points from the score at origination; or a restructure under RP-4.2."),
         "thresholds": {"dpd_days": 30, "behaviour_score_floor": 520, "grade_notches_from_origination": 2,
                        "score_fall_points": 90},
         "applies_to": ["stage", "sicr_flag", "dpd_days", "behaviour_score"], "owner": "Head of IFRS 9",
         "last_reviewed": "2026-06-10", "levers": ["tighten a SICR trigger", "add a trigger"],
         "summary": "RP-5.1 now treats a 2-notch downgrade as SICR",
         "previous": ("An account moves to Stage 2 on any of: 30 days past due; a behavioural score below 520; a fall "
                      "of more than 105 points from the score at origination; or a restructure under RP-4.2.")},
        {"clause": "CP-3.3", "book": "corporate", "section": "CP-3", "section_title": "Rating, watchlist and early warning",
         "title": "Significant increase in credit risk",
         "rule": ("A facility moves to Stage 2 on any of: 30 days past due; an internal grade at or below CCC; a fall "
                  "of two or more notches from the rating at origination; or placement of the borrower on the "
                  "watchlist under CP-3.1. Default is recognised at 90 days past due or at an internal grade at or "
                  "below CC."),
         "thresholds": {"dpd_days": 30, "grade_floor": "CCC", "notches_from_origination": 2, "watchlist": True},
         "applies_to": ["stage", "sicr_flag", "dpd_days", "rating_current", "watchlist_flag"],
         "owner": "Head of IFRS 9", "last_reviewed": "2026-06-10",
         "levers": ["tighten the notch trigger", "add a qualitative trigger"],
         "summary": "CP-3.3 now treats a 2-notch downgrade or a watchlist placement as SICR",
         "previous": ("A facility moves to Stage 2 on any of: 30 days past due; an internal grade at or below CCC; or "
                      "a fall of two or more notches from the rating at origination. Default is recognised at 90 days "
                      "past due or at an internal grade at or below CC.")},
        {"clause": "CP-3.4", "book": "corporate", "section": "CP-3", "section_title": "Rating, watchlist and early warning",
         "title": "Sector watch: construction contractors",
         "rule": ("A borrower in the Construction sector with a debt service coverage ratio below 1.10x at two "
                  "consecutive quarter-ends is placed on the watchlist, re-rated out of cycle within 30 days, and "
                  "assessed for Stage 2 under CP-3.3. New money to such a borrower needs Head of Credit approval."),
         "thresholds": {"dscr_x": 1.10, "consecutive_quarters": 2, "re_rating_days": 30},
         "applies_to": ["sector", "dscr_x", "watchlist_flag", "rating_current", "stage"],
         "owner": "Chief Credit Officer", "last_reviewed": "2026-06-10",
         "levers": ["change the DSCR floor", "widen to other sectors"],
         "summary": "CP-3.4 places construction contractors with DSCR below 1.10x under a sector watch",
         "previous": None},
    ],
    "transitional": ("Exposures that meet a new trigger at 30 September 2026 move to Stage 2 at that date. Prior "
                     "periods are not restated. Model Validation reviews the effect on the staging back-test by "
                     "31 December 2026."),
}

#: Words that identify the books' segments, so an interpretation can say which segments a clause touches.
SEGMENT_WORDS = {
    "Construction": ("construction", "contractor"), "Real Estate": ("real estate", "property developer"),
    "Manufacturing": ("manufactur",), "Trade": ("trade finance", "wholesale", "retail trade"),
    "Oil & Gas": ("oil", "petrochemical"), "Supply chain finance": ("supply chain", "receivables"),
    "Credit cards": ("credit card", "card limit"), "Personal finance": ("personal finance", "personal loan"),
    "Mortgage": ("mortgage", "home finance"), "Auto finance": ("auto finance", "vehicle"),
    "Buy now pay later": ("bnpl", "buy now pay later"), "Non-salaried customers": ("non-salaried", "self-employed"),
    "Salaried customers": ("salaried",),
}

#: Words that tie a clause to the Early Warning rules (rule set gw-ews-1.3.0).
EWS_RULES = [
    (("downgrade", "notch", "grade"), "C-DOWNGRADE", "Rating downgraded this quarter", "corporate"),
    (("score", "behavioural", "behaviour", "grade"), "R-SCORE-DOWN", "Behaviour score fell 2 or more bands", "retail"),
    (("watchlist", "watch list"), "C-WATCH", "On watchlist", "corporate"),
    (("covenant", "dscr", "debt service", "leverage"), "C-COVENANT", "Covenant breach", "corporate"),
    (("days past due", "dpd", "arrears", "past due"), "C-DPD", "Past due (DPD > 59)", "corporate"),
    (("days past due", "dpd", "arrears", "past due"), "R-DPD", "Payment arrears (DPD > 0)", "retail"),
    (("sicr", "significant increase", "stage 2"), "C-SICR", "SICR flag raised", "corporate"),
    (("utilisation", "utilization", "limit usage"), "C-UTIL", "High utilisation", "corporate"),
    (("utilisation", "utilization", "card limit"), "R-UTIL", "High utilisation (>= 85%)", "retail"),
    (("default", "stage 3", "write-off"), "C-DEFAULT", "Stage 3 or in default", "corporate"),
    (("salary",), "R-OB-SALARY", "Salary credit missing this month (salaried customer)", "retail"),
    (("bureau", "simah", "enquir"), "R-BUR-ENQ", "5 or more bureau enquiries in 3 months", "retail"),
]
