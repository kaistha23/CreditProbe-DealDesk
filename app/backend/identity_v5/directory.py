"""The seeded user directory (plan R2 item 1). The username is the stable ID.

`team` drives "my team's items": admin | risk | corporate | retail | validation.
"""
from __future__ import annotations

from typing import Any

TEAMS = ("admin", "risk", "corporate", "retail", "validation", "audit")

# username, name, role, title, department, initials, books, team, is_admin
_ROWS: list[tuple[str, str, str, str, str, str, list[str], str, bool]] = [
    ("anne", "Anne", "Administrator", "Administrator", "Credit Risk", "AN", ["corporate", "retail"], "admin", True),
    ("faisal.alqahtani", "Faisal Al-Qahtani", "Head of Risk", "Head of Risk", "Risk Management", "FQ",
     ["corporate", "retail"], "risk", False),
    ("noura.alharbi", "Noura Al-Harbi", "Head of Credit", "Head of Credit", "Credit", "NH",
     ["corporate", "retail"], "risk", False),
    ("khalid.alotaibi", "Khalid Al-Otaibi", "Corporate Credit Manager", "Corporate Credit Manager",
     "Corporate Credit", "KO", ["corporate"], "corporate", False),
    ("reem.alshehri", "Reem Al-Shehri", "Retail Credit Manager", "Retail Credit Manager", "Retail Credit", "RS",
     ["retail"], "retail", False),
    ("abdullah.alzahrani", "Abdullah Al-Zahrani", "Risk Manager", "Risk Manager", "Portfolio Risk", "AZ",
     ["corporate", "retail"], "risk", False),
    ("sara.aldosari", "Sara Al-Dosari", "Credit Analyst (corporate)", "Credit Analyst", "Corporate Credit", "SD",
     ["corporate"], "corporate", False),
    ("omar.alghamdi", "Omar Al-Ghamdi", "Credit Analyst (retail)", "Credit Analyst", "Retail Credit", "OG",
     ["retail"], "retail", False),
    ("lama.almutairi", "Lama Al-Mutairi", "Model Validation Analyst", "Model Validation Analyst",
     "Model Validation", "LM", ["corporate", "retail"], "validation", False),
    # PLAN_R5 A2/A7: two Riyadh relationship managers (RM0005, RM0011 in the Branches and RMs domain) and an
    # internal auditor, so the Admin console's data access policies can be shown on real sign-ins.
    ("nawaf.alotaibi", "Nawaf Al-Otaibi", "Relationship Manager", "Relationship Manager",
     "Corporate Banking Central", "NO", ["corporate"], "corporate", False),
    ("abeer.alomari", "Abeer Al-Omari", "Relationship Manager", "Relationship Manager",
     "Corporate Banking Central", "AO", ["corporate"], "corporate", False),
    ("hind.alsubaie", "Hind Al-Subaie", "Internal Auditor", "Internal Auditor", "Internal Audit", "HS",
     ["corporate", "retail"], "audit", False),
]

#: Users added after the first seed (a store seeded earlier gets them on its next start, with new passwords).
DIRECTORY_VERSION = "r5-12"

USERNAMES = [r[0] for r in _ROWS]


def seed_users() -> list[dict[str, Any]]:
    return [
        {"username": u, "name": n, "role": role, "title": title, "department": dept, "initials": ini,
         "books": books, "team": team, "is_admin": adm, "position": i}
        for i, (u, n, role, title, dept, ini, books, team, adm) in enumerate(_ROWS)
    ]
