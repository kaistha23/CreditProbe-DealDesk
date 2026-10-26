"""R16 d: identifiers of the four fictional demo customers (all names invented; none is a real company or person)."""
from __future__ import annotations

BANK = "Sandstone Harbour Bank"          # "the Bank" (the fictional bank of the R12 policy library)
AS_OF = "2026-10-21"                     # demo day; documents are dated on or before it

CUSTOMERS = [
    {"key": "c1", "folder": "c1_dar_al_naseem", "proposal_id": "R16-C1", "cif": "CB09001", "group_id": "CG9001",
     "name": "Dar Al Naseem Medical Supplies Co.", "short": "Dar Al Naseem", "cr_number": "1010384527",
     "vat_number": "300384527100003", "city": "Riyadh", "sector": "Wholesale Trade", "sub_sector": "Medical Supplies Distribution",
     "case": "existing", "case_label": "Existing customer, renewal + increase", "part": "A",
     "group_name": "Naseem Holding Group"},
    {"key": "c2", "folder": "c2_sawaed_al_bina", "proposal_id": "R16-C2", "cif": "CB09002", "group_id": "CG9002",
     "name": "Sawaed Al Bina Contracting Co.", "short": "Sawaed Al Bina", "cr_number": "2050117342",
     "vat_number": "302050117300003", "city": "Dammam", "sector": "Construction", "sub_sector": "Building and Infrastructure Contracting",
     "case": "existing", "case_label": "Existing customer, new project limit", "part": "B",
     "group_name": "Sawaed Group"},
    {"key": "c3", "folder": "c3_nukhba_polymer", "proposal_id": "R16-C3", "cif": "", "group_id": "",
     "name": "Nukhba Polymer Industries Co.", "short": "Nukhba Polymer", "cr_number": "2055104486",
     "vat_number": "302055104400003", "city": "Jubail", "sector": "Manufacturing", "sub_sector": "Plastics and Polymer Products",
     "case": "new_to_bank", "case_label": "New-to-bank manufacturer, takeover of another bank's facilities", "part": "A (optional)",
     "group_name": ""},
    {"key": "c4", "folder": "c4_sanad_facility", "proposal_id": "R16-C4", "cif": "", "group_id": "",
     "name": "Sanad Smart Facility Services Co.", "short": "Sanad Facility", "cr_number": "1010712290",
     "vat_number": "301010712200003", "city": "Riyadh", "sector": "Services", "sub_sector": "Facility Management",
     "case": "new_to_bank_sme", "case_label": "New-to-bank SME, thin file", "part": "A (optional)",
     "group_name": ""},
]
BY_KEY = {c["key"]: c for c in CUSTOMERS}
