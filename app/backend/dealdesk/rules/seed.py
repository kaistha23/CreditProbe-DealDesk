"""The bank's global rules, seeded from the style of the two SIB proposals.

SIB's own documents are not in this repository (synthetic data only until they arrive), so these are synthetic stand-ins:
plausible house rules of the kind a Saudi/UAE corporate credit proposal follows (section order, headings, how risks and
mitigants are tabulated, units, voice). No SIB text. Each is stored like any other rule (scope: the bank; author:
CreditProbe; origin: seed:sib-style) and can be edited or removed from Policy Docs -> Global rules.
"""
from __future__ import annotations

import sqlite3

SEED_AUTHOR = "creditprobe"
SEED_AUTHOR_NAME = "CreditProbe (seeded from the SIB proposals' style)"
SEED_VERSION = "sib-style-v1"

#: (id, document, section, section_label, kind, params, text)
RULES: list[tuple[str, str, str, str, str, dict, str]] = [
    ("GR-01", "both", "", "", "section_order", {"section": "Action requested", "position": "first"},
     "Open with the action requested: what is asked, for whom, how much and for how long, before any background."),
    ("GR-02", "proposal", "", "", "section_order", {"section": "Recommendation", "before": "Signatures"},
     "Put the recommendation directly before the signatures, after every analysis section."),
    ("GR-03", "proposal", "risks", "Risks and mitigants", "heading", {"section": "risks", "heading": "Key Risks and Mitigants"},
     "Head the risks section “Key Risks and Mitigants”."),
    ("GR-04", "proposal", "risks", "Risks and mitigants", "table", {"section": "risks", "header": ["Risk", "Mitigant"]},
     "Tabulate risks and mitigants in two columns, Risk | Mitigant, one risk per row; a risk without a mitigant says so."),
    ("GR-05", "both", "", "", "units", {"money_suffix": "m"},
     "Write amounts in millions as SAR 12.5m (currency first, “m” for millions, one decimal)."),
    ("GR-06", "both", "", "", "units", {"percent": "%"},
     "Write percentages with the % sign (12.5%), not “per cent”."),
    ("GR-07", "both", "", "", "wording", {"use": "obligor", "instead_of": "client"},
     "Say “obligor”, not “client”."),
    ("GR-08", "proposal", "", "", "include_section", {"heading": "Key strengths"},
     "Always include a “Key strengths” section before the recommendation."),
    ("GR-09", "both", "bureau", "Credit bureau", "must_mention", {"phrase": "SIMAH"},
     "Always state the SIMAH status of the obligor and its guarantors."),
    ("GR-10", "both", "", "", "instruction", {},
     "Write in the third person (“the Bank”, “the Company”); never “we” or “I”."),
    ("GR-11", "proposal", "", "", "instruction", {},
     "Each weakness names its mitigant and the condition or covenant that addresses it."),
    ("GR-12", "request", "action", "Action requested", "heading", {"section": "action", "heading": "Action Requested"},
     "Head the first section “Action Requested”."),
]


def ensure(con: sqlite3.Connection) -> None:
    """Seed once per store (a removed seed rule stays removed: its id is on record)."""
    if con.execute("SELECT 1 FROM rules WHERE origin='seed:sib-style' LIMIT 1").fetchone():
        return
    from backend.dealdesk.rules import store
    for rid, doc, sec, lab, kind, params, text in RULES:
        store.create(text=text, kind=kind, params=params, scope="bank", document=doc, section=sec, section_label=lab, author=SEED_AUTHOR,
                     source_instruction="Seeded from the house style of the two SIB proposals (synthetic stand-ins, no SIB text).",
                     source={"via": "seed", "version": SEED_VERSION}, origin="seed:sib-style", rule_id=rid, con=con)
    con.execute("UPDATE rules SET author_name=? WHERE origin='seed:sib-style'", (SEED_AUTHOR_NAME,))
    con.commit()
