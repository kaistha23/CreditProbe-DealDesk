"""Build the Deal Desk data domain: parameter tables, 15 credit proposals, their credit memos, manifest.

    python3 ops/dealdesk_build.py           write data/dealdesk (deterministic: same book, same files)
    python3 ops/dealdesk_build.py --check   rebuild into a scratch folder and compare with the committed files

Existing borrowers are pre-filled from the corporate book at 2026Q2 (rating, connected group,
existing exposure and facilities, pledged collateral, financials). New-to-bank names carry DN###
obligor ids. Every proposal is checked against the live book by the engine, not here.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
from datetime import datetime, timezone

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.dealdesk import paths, portfolio, seed  # noqa: E402

AS_OF = paths.AS_OF
BUILT = datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc)

SECTOR_CODE = {"Construction": "F42", "Real Estate": "L68", "Manufacturing": "C25", "Wholesale Trade": "G46",
               "Healthcare": "Q86", "Telecommunications": "J61", "Power and Utilities": "D35",
               "Transport and Logistics": "H52", "Chemicals": "C20"}


def terms(**kw):
    base = {"facility_type": "term_loan", "structure": "conventional", "currency": "SAR", "amount": 50.0,
            "tenor_years": 5, "grace_years": 0, "amortisation": "equal", "balloon_pct": 0, "margin_bps": 200,
            "upfront_fee_bps": 50, "commitment_fee_bps": 0, "commission_bps": 0, "utilisation_pct": 100,
            "funded_share_pct": 100, "unfunded_type": "performance_lg", "cash_margin_pct": 0, "collateral_ids": [],
            "guarantee_id": None, "guarantee_coverage_pct": 0, "covenant_package": "standard"}
    base.update(kw)
    return base


def fin(rev, margin, debt, ds, nw, cr, growth=0.05, start=2023):
    """Three actual years and three projections from a 2025 base."""
    out = []
    for i, y in enumerate(range(start, start + 6)):
        g = (1 + growth) ** (y - 2025)
        out.append({"year": y, "kind": "actual" if y <= 2025 else "projection",
                    "revenue": round(rev * g, 2), "ebitda": round(rev * margin * g, 2),
                    "total_debt": round(debt * (1 - 0.04 * (y - 2025)), 2), "debt_service": round(ds * (1 - 0.03 * (y - 2025)), 2),
                    "net_worth": round(nw * (1 + 0.06 * (y - 2025)), 2), "current_ratio": round(cr, 2)})
    return out


def coll(cid, typ, value, cur="SAR", date="2026-06-30", ask=True):
    return {"collateral_id": cid, "type": typ, "value": value, "currency": cur, "valuation_date": date, "pledged_in_ask": ask}


def guar(gid, typ, guarantor, rating, cov, ask=False):
    return {"guarantee_id": gid, "type": typ, "guarantor": guarantor, "guarantor_rating": rating,
            "coverage_pct": cov, "offered_in_ask": ask}


#: The 15 proposals. `existing` names a book borrower: the engine pre-fills its record.
SPECS = [
    {"id": "DD-01", "case": "clears_easily", "rm": "Khalid Al-Otaibi", "received": "2026-10-04", "status": "new",
     "purpose": "Working capital to deliver a five-year medical supply contract with the Ministry of Health",
     "obligor": {"obligor_id": "DN001", "name": "Al Rayyan Medical Supply Company", "cr_number": "1010487213",
                 "sector": "Healthcare", "sub_sector": "Medical Devices", "segment": "Healthcare", "region": "Riyadh",
                 "internal_rating": "A-", "external_rating": "A-", "gre": False, "sme": False, "simah_flag": "clear", "gov_linked": True,
                 "group_id": "DG001", "group_name": "Al Rayyan Holding", "connected_parties": []},
     "financials": fin(820, 0.17, 210, 62, 540, 1.8),
     "ask": terms(structure="murabaha", amount=60, tenor_years=3, margin_bps=220, upfront_fee_bps=75,
                  collateral_ids=["C1"], covenant_package="standard"),
     "collateral": [coll("C1", "receivables", 95.0)], "guarantees": [],
     "ancillary": {"cash_management": 0.6, "payroll": 0.3, "fx": 0.1, "trade": 0.4}},

    {"id": "DD-02", "case": "existing_contractor", "rm": "Sara Al-Dosari", "received": "2026-10-05", "status": "in_review",
     "existing": "CB01338", "purpose": "Equipment and mobilisation for a road maintenance contract in Qassim",
     "obligor": {"sector": "Construction", "segment": "Construction", "simah_flag": "clear"},
     "ask": terms(structure="tawarruq", amount=16, tenor_years=6, grace_years=1, margin_bps=240, upfront_fee_bps=75,
                  collateral_ids=["C1"]),
     "collateral": [coll("C1", "plant_equipment", 12.0, date="2026-08-15")],
     "guarantees": [guar("G1", "personal", "Principal shareholder", "BB", 100)],
     "ancillary": {"cash_management": 0.05, "payroll": 0.04, "fx": 0.0, "trade": 0.02}},

    {"id": "DD-03", "case": "large_exposure", "rm": "Khalid Al-Otaibi", "received": "2026-10-06", "status": "new",
     "purpose": "Construction of a cold storage hub in Dammam for the group's logistics network",
     "obligor": {"obligor_id": "DN003", "name": "Al Khobar Modern Cold Storage Company", "cr_number": "2050931144",
                 "sector": "Transport and Logistics", "sub_sector": "Cold Chain", "segment": "Transport and Logistics",
                 "region": "Eastern Province", "internal_rating": "BBB", "gre": False, "sme": False, "simah_flag": "clear",
                 "group_id": "CG9317-006", "group_name": "Al Khobar Modern Logistics Group", "connected_parties": []},
     "financials": fin(640, 0.22, 260, 70, 410, 1.5),
     "ask": terms(structure="murabaha", amount=180, tenor_years=7, grace_years=1, margin_bps=210, upfront_fee_bps=60,
                  collateral_ids=["C1"]),
     "collateral": [coll("C1", "real_estate", 150.0, date="2026-07-20")], "guarantees": [
         guar("G1", "corporate", "Al Khobar Modern Logistics Group (parent)", "BBB", 50)],
     "ancillary": {"cash_management": 0.5, "payroll": 0.2, "fx": 0.1, "trade": 0.3}},

    {"id": "DD-04", "case": "concentrated_sector", "rm": "Abdullah Al-Zahrani", "received": "2026-10-06", "status": "new",
     "purpose": "Ijara financing of a completed Grade A office tower in north Riyadh",
     "obligor": {"obligor_id": "DN004", "name": "Al Nakheel Commercial Properties Company", "cr_number": "1010662590",
                 "sector": "Real Estate", "sub_sector": "Commercial Property", "segment": "Real Estate", "region": "Riyadh",
                 "internal_rating": "BB+", "gre": False, "sme": False, "simah_flag": "clear",
                 "group_id": "DG004", "group_name": "Al Nakheel Holding", "connected_parties": [], "real_estate_finance": True},
     "financials": fin(140, 0.62, 150, 30, 520, 1.3, growth=0.03),
     "ask": terms(structure="ijara", amount=150, tenor_years=7, amortisation="balloon", balloon_pct=40, margin_bps=260,
                  upfront_fee_bps=80, collateral_ids=["C1"]),
     "collateral": [coll("C1", "real_estate", 240.0, date="2026-05-31")], "guarantees": [],
     "ancillary": {"cash_management": 0.2, "payroll": 0.0, "fx": 0.0, "trade": 0.0}},

    {"id": "DD-05", "case": "infeasible", "rm": "Sara Al-Dosari", "received": "2026-10-07", "status": "new",
     "purpose": "Working capital for a subcontract on a municipal infrastructure package",
     "obligor": {"obligor_id": "DN005", "name": "Najd Al Bunyan Contracting Company", "cr_number": "1010775031",
                 "sector": "Construction", "sub_sector": "Civil Infrastructure", "segment": "Construction", "region": "Riyadh",
                 "internal_rating": "B-", "gre": False, "sme": False, "simah_flag": "watch",
                 "group_id": "DG005", "group_name": "Najd Al Bunyan Contracting", "connected_parties": []},
     "financials": fin(310, 0.12, 95, 27, 120, 1.1, growth=0.02),
     "ask": terms(structure="tawarruq", amount=45, tenor_years=5, grace_years=1, margin_bps=330, upfront_fee_bps=60),
     "collateral": [], "guarantees": [],
     "ancillary": {"cash_management": 0.05, "payroll": 0.05, "fx": 0.0, "trade": 0.0}},

    {"id": "DD-06", "case": "existing_manufacturer", "rm": "Khalid Al-Otaibi", "received": "2026-10-03", "status": "counter_offered",
     "existing": "CB02729", "purpose": "Revolving working capital for steel fabrication orders",
     "obligor": {"sector": "Manufacturing", "segment": "Manufacturing", "simah_flag": "clear"},
     "ask": terms(facility_type="revolver", structure="murabaha", amount=25, tenor_years=3, amortisation="bullet",
                  margin_bps=190, upfront_fee_bps=40, commitment_fee_bps=25, utilisation_pct=60, collateral_ids=["C1"]),
     "collateral": [coll("C1", "receivables", 20.0)], "guarantees": [],
     "ancillary": {"cash_management": 0.08, "payroll": 0.05, "fx": 0.02, "trade": 0.06}},

    {"id": "DD-07", "case": "existing_trader_lc", "rm": "Sara Al-Dosari", "received": "2026-10-02", "status": "approved",
     "existing": "CB05080", "purpose": "Import letters of credit for building supplies from China and Turkey",
     "obligor": {"sector": "Wholesale Trade", "segment": "Wholesale Trade", "simah_flag": "clear"},
     "ask": terms(facility_type="trade_lc", structure="murabaha", currency="USD", amount=8, tenor_years=1,
                  amortisation="bullet", margin_bps=0, upfront_fee_bps=25, commission_bps=80, utilisation_pct=75,
                  cash_margin_pct=10, covenant_package="none"),
     "collateral": [], "guarantees": [],
     "ancillary": {"cash_management": 0.04, "payroll": 0.02, "fx": 0.08, "trade": 0.10}},

    {"id": "DD-08", "case": "healthcare_ijara", "rm": "Abdullah Al-Zahrani", "received": "2026-10-07", "status": "new",
     "purpose": "Ijara of diagnostic imaging equipment for a new hospital wing in Jeddah",
     "obligor": {"obligor_id": "DN008", "name": "Jeddah Al Shifa Hospital Company", "cr_number": "4030558761",
                 "sector": "Healthcare", "sub_sector": "Hospitals", "segment": "Healthcare", "region": "Makkah",
                 "internal_rating": "BBB-", "gre": False, "sme": False, "simah_flag": "clear",
                 "group_id": "DG008", "group_name": "Al Shifa Healthcare Group", "connected_parties": []},
     "financials": fin(560, 0.21, 190, 52, 380, 1.4),
     "ask": terms(structure="ijara", amount=70, tenor_years=6, grace_years=0, margin_bps=215, upfront_fee_bps=60,
                  collateral_ids=["C1"]),
     "collateral": [coll("C1", "plant_equipment", 82.0, date="2026-09-01")], "guarantees": [],
     "ancillary": {"cash_management": 0.3, "payroll": 0.4, "fx": 0.05, "trade": 0.1}},

    {"id": "DD-09", "case": "gov_supplier_lg", "rm": "Khalid Al-Otaibi", "received": "2026-10-08", "status": "new",
     "purpose": "Performance guarantee for an electrical works contract with a government entity",
     "obligor": {"obligor_id": "DN009", "name": "Tabuk Electromechanical Services Company", "cr_number": "3550210478",
                 "sector": "Construction", "sub_sector": "Electromechanical", "segment": "Construction", "region": "Tabuk",
                 "internal_rating": "BBB", "gre": False, "sme": False, "simah_flag": "clear", "gov_linked": True,
                 "group_id": "DG009", "group_name": "Tabuk Electromechanical Services", "connected_parties": []},
     "financials": fin(380, 0.15, 70, 20, 210, 1.6),
     "ask": terms(facility_type="performance_lg", amount=40, tenor_years=3, amortisation="bullet", margin_bps=0,
                  upfront_fee_bps=20, commission_bps=90, utilisation_pct=100, cash_margin_pct=10, covenant_package="none"),
     "collateral": [], "guarantees": [],
     "ancillary": {"cash_management": 0.1, "payroll": 0.15, "fx": 0.0, "trade": 0.05}},

    {"id": "DD-10", "case": "sme_kafalah", "rm": "Sara Al-Dosari", "received": "2026-10-08", "status": "new",
     "purpose": "Purchase of packaging machinery for a food-grade plastics workshop",
     "obligor": {"obligor_id": "DN010", "name": "Al Qassim Precision Plastics Establishment", "cr_number": "1131049982",
                 "sector": "Manufacturing", "sub_sector": "Industrial Products", "segment": "Manufacturing", "region": "Qassim",
                 "internal_rating": "BB-", "gre": False, "sme": True, "simah_flag": "clear",
                 "group_id": "DG010", "group_name": "Al Qassim Precision Plastics", "connected_parties": []},
     "financials": fin(38, 0.18, 6, 1.9, 14, 1.3),
     "ask": terms(structure="murabaha", amount=8, tenor_years=5, grace_years=1, margin_bps=300, upfront_fee_bps=100,
                  guarantee_id="G1", guarantee_coverage_pct=80, collateral_ids=["C1"]),
     "collateral": [coll("C1", "plant_equipment", 6.5, date="2026-09-10")],
     "guarantees": [guar("G1", "kafalah", "Kafalah programme", "AA-", 80, ask=True)],
     "ancillary": {"cash_management": 0.01, "payroll": 0.01, "fx": 0.0, "trade": 0.0}},

    {"id": "DD-11", "case": "existing_contractor_lg", "rm": "Abdullah Al-Zahrani", "received": "2026-10-01", "status": "declined",
     "existing": "CB00808", "purpose": "Working capital line with a performance-guarantee sub-limit for marine works",
     "obligor": {"sector": "Construction", "segment": "Construction", "simah_flag": "adverse"},
     "ask": terms(facility_type="revolver", structure="tawarruq", amount=24, tenor_years=3, amortisation="bullet",
                  margin_bps=380, upfront_fee_bps=80, commitment_fee_bps=30, commission_bps=120, utilisation_pct=70,
                  funded_share_pct=50, unfunded_type="performance_lg", cash_margin_pct=5, collateral_ids=["C1"]),
     "collateral": [coll("C1", "real_estate", 14.0, date="2026-04-30")], "guarantees": [],
     "ancillary": {"cash_management": 0.04, "payroll": 0.06, "fx": 0.0, "trade": 0.03}},

    {"id": "DD-12", "case": "existing_logistics_musharaka", "rm": "Khalid Al-Otaibi", "received": "2026-10-09", "status": "new",
     "existing": "CB04811", "purpose": "Diminishing Musharaka for a bonded warehouse at King Abdulaziz Port",
     "obligor": {"sector": "Transport and Logistics", "segment": "Transport and Logistics", "simah_flag": "clear"},
     "ask": terms(structure="musharaka", currency="USD", amount=7, tenor_years=7, grace_years=1, margin_bps=230,
                  upfront_fee_bps=60, collateral_ids=["C1"]),
     "collateral": [coll("C1", "real_estate", 32.0, date="2026-08-01")],
     "guarantees": [guar("G1", "personal", "Managing partner", "BBB", 100)],
     "ancillary": {"cash_management": 0.05, "payroll": 0.03, "fx": 0.06, "trade": 0.05}},

    {"id": "DD-13", "case": "existing_clinic_guaranteed", "rm": "Sara Al-Dosari", "received": "2026-10-09", "status": "in_review",
     "existing": "CB01399", "purpose": "Fit-out of three outpatient clinics in Makkah and Taif",
     "obligor": {"sector": "Healthcare", "segment": "Healthcare", "simah_flag": "clear"},
     "ask": terms(structure="tawarruq", amount=22, tenor_years=5, grace_years=1, margin_bps=200, upfront_fee_bps=50,
                  guarantee_id="G1", guarantee_coverage_pct=60),
     "collateral": [coll("C1", "cash", 3.0, ask=False)],
     "guarantees": [guar("G1", "corporate", "Al Jouf Arabian Medical Holding (parent)", "BBB+", 60, ask=True)],
     "ancillary": {"cash_management": 0.05, "payroll": 0.08, "fx": 0.0, "trade": 0.02}},

    {"id": "DD-14", "case": "below_market_margin", "rm": "Abdullah Al-Zahrani", "received": "2026-10-10", "status": "new",
     "purpose": "Debottlenecking capex at a downstream polymers plant in Jubail",
     "obligor": {"obligor_id": "DN014", "name": "Jubail Advanced Polymers Company", "cr_number": "2055117390",
                 "sector": "Chemicals", "sub_sector": "Petrochemicals", "segment": "Chemicals", "region": "Eastern Province",
                 "internal_rating": "AA-", "external_rating": "A", "gre": False, "sme": False, "simah_flag": "clear",
                 "group_id": "DG014", "group_name": "Jubail Advanced Polymers", "connected_parties": []},
     "financials": fin(2400, 0.24, 900, 210, 3100, 2.1),
     "ask": terms(currency="USD", amount=50, tenor_years=7, grace_years=2, margin_bps=70, upfront_fee_bps=30),
     "collateral": [coll("C1", "plant_equipment", 300.0, cur="USD", date="2026-03-31", ask=False)], "guarantees": [],
     "ancillary": {"cash_management": 0.4, "payroll": 0.3, "fx": 0.5, "trade": 0.3}},

    {"id": "DD-15", "case": "out_of_range", "rm": "Khalid Al-Otaibi", "received": "2026-10-10", "status": "new",
     "purpose": "Grid reinforcement programme for the Eastern Province transmission network",
     "obligor": {"obligor_id": "DN015", "name": "Eastern Grid Services Company", "cr_number": "2050871256",
                 "sector": "Power and Utilities", "sub_sector": "Transmission", "segment": "Power and Utilities",
                 "region": "Eastern Province", "internal_rating": "AAA", "external_rating": "AA-", "gre": True, "sme": False,
                 "simah_flag": "clear", "group_id": "DG015", "group_name": "Eastern Grid Services", "connected_parties": []},
     "financials": fin(5200, 0.41, 6100, 980, 14000, 1.2, growth=0.04),
     "ask": terms(structure="murabaha", amount=240, tenor_years=10, grace_years=2, margin_bps=85, upfront_fee_bps=25),
     "collateral": [], "guarantees": [guar("G1", "government", "Ministry of Energy letter of support", "A+", 100, ask=False)],
     "ancillary": {"cash_management": 0.8, "payroll": 0.5, "fx": 0.1, "trade": 0.2}},
]


def existing_obligor(bid: str, extra: dict) -> tuple[dict, list[dict]]:
    """Pre-fill from the book: identity, rating, connected group, exposure, facilities, pledged collateral, financials."""
    r = portfolio.borrower(bid)
    if r is None:
        raise SystemExit(f"{bid} is not in the corporate book at {AS_OF}")
    rec = r["record"]
    h = portfolio.borrower_history(bid)
    years = []
    for y in (2023, 2024, 2025):
        q = h[h["reporting_quarter"] == f"{y}Q4"]
        if q.empty:
            continue
        q = q.iloc[0]
        nw = (q["ebit_sar_mn"] / (q["return_on_assets_pct"] / 100.0) - q["total_debt_sar_mn"]) if q["return_on_assets_pct"] > 0 else q["total_debt_sar_mn"]
        years.append({"year": y, "kind": "actual", "revenue": round(float(q["revenue_sar_mn"]), 3),
                      "ebitda": round(float(q["ebitda_sar_mn"]), 3), "total_debt": round(float(q["total_debt_sar_mn"]), 3),
                      "debt_service": round(float(q["ebitda_sar_mn"] / q["dscr_x"]), 3),
                      "net_worth": round(float(max(nw, 0.5 * q["total_debt_sar_mn"])), 3),
                      "current_ratio": round(float(q["current_ratio_x"]), 3), "source": f"corp_borrower_quarter {y}Q4"})
    last = years[-1]
    for i, y in enumerate((2026, 2027, 2028), start=1):
        g = 1.04 ** i
        years.append({"year": y, "kind": "projection", "revenue": round(last["revenue"] * g, 3),
                      "ebitda": round(last["ebitda"] * g, 3), "total_debt": round(last["total_debt"] * (1 - 0.04 * i), 3),
                      "debt_service": round(last["debt_service"] * (1 - 0.03 * i), 3),
                      "net_worth": round(last["net_worth"] * (1 + 0.05 * i), 3), "current_ratio": last["current_ratio"],
                      "source": "RM projection: 4% growth on the 2025 actuals"})
    ob = {"obligor_id": bid, "existing": True, "name": rec["borrower_name"],
          "cr_number": "10" + hashlib.sha256(bid.encode()).hexdigest()[:8].translate(str.maketrans("abcdef", "123456")),
          "group_id": rec["connected_group_id"], "group_name": rec["connected_group_name"],
          "legacy_group_id": rec["group_id"], "connected_parties": [],
          "sector": rec["sector"], "sub_sector": rec["sub_sector"], "sector_code": SECTOR_CODE.get(rec["sector"], ""),
          "segment": rec["sector"], "region": rec["region"], "sme": False, "gre": False,
          "internal_rating": rec["rating_current"], "external_rating": None,
          "pd_master_scale": seed.MASTER_SCALE[rec["rating_current"]], "simah_flag": extra.get("simah_flag", "clear"),
          "existing_exposure_sar_mn": round(r["ead"], 4),
          "existing_facilities": [{"facility_id": f["facility_id"], "product": f["product_type"], "limit": round(f["limit_sar_mn"], 4),
                                   "drawn": round(f["drawn_sar_mn"], 4), "ead": round(f["ead_sar_mn"], 4), "stage": int(f["stage"])}
                                  for f in r["facilities"]],
          "existing_collateral": [{"collateral_id": c["collateral_id"], "facility_id": c["facility_id"],
                                   "type": portfolio.COLLATERAL_KEY.get(c["collateral_type"], c["collateral_type"]),
                                   "value": round(c["market_value_sar_mn"], 4)} for c in r["collateral"]],
          "prefilled_from": f"{paths.CORP_RELEASE} {AS_OF}"}
    members = portfolio.frames()["borrower"]
    ob["connected_parties"] = sorted(members.loc[members["connected_group_id"] == ob["group_id"], "borrower_id"].tolist())
    return ob, years


def build_proposals() -> list[dict]:
    snap = portfolio.snapshot()
    out = []
    for s in SPECS:
        if s.get("existing"):
            ob, years = existing_obligor(s["existing"], s["obligor"])
        else:
            ob = {"existing": False, "external_rating": None, **s["obligor"]}
            ob.setdefault("sector_code", "")
            ob["sector_code"] = SECTOR_CODE.get(ob["sector"], "")
            ob["pd_master_scale"] = seed.MASTER_SCALE[ob["internal_rating"]]
            ob["existing_exposure_sar_mn"] = 0.0
            ob["existing_facilities"] = []
            if ob["group_id"].startswith("CG"):
                members = portfolio.frames()["borrower"]
                ob["connected_parties"] = sorted(members.loc[members["connected_group_id"] == ob["group_id"], "borrower_id"].tolist())
                ob["group_existing_exposure_sar_mn"] = round(float(snap["by_group"].get(ob["group_id"], 0.0)), 4)
            years = s["financials"]
            for y in years:
                y["source"] = "Audited financial statements" if y["kind"] == "actual" else "Management projections"
        ob.setdefault("gov_linked", s["obligor"].get("gov_linked", False))
        ob.setdefault("real_estate_finance", s["obligor"].get("real_estate_finance", False))
        cur = s["ask"]["currency"]
        covs = {"none": [], "standard": [{"type": "DSCR", "threshold": 1.20}, {"type": "Net debt / EBITDA", "threshold": 4.0},
                                         {"type": "Interest cover", "threshold": 2.5}]}.get(s["ask"]["covenant_package"], [])
        out.append({
            "proposal_id": s["id"], "status": s["status"], "rm": s["rm"], "business_unit": "SME Banking" if ob.get("sme") else
            ("Government and GRE" if ob.get("gre") else "Corporate Banking"), "received": s["received"], "purpose": s["purpose"],
            "obligor": ob, "financials": {"currency": "SAR", "unit": "SAR m", "years": years},
            "ask": s["ask"],
            "security": {"collateral": s["collateral"], "guarantees": s["guarantees"],
                         "covenant_package": s["ask"]["covenant_package"], "covenants": covs},
            "business_case": {"ancillary_income_sar_mn_pa": s["ancillary"], "currency": "SAR"},
            "memo": f"{s['id']}.docx", "case": s["case"], "deal_currency": cur,
        })
    return out


# ------------------------------------------------------------------ memos (house style)

def write_memo(p: dict, path: pathlib.Path) -> None:
    from backend.house_style import Meta
    from backend.house_style import docx as hd
    ob, ask = p["obligor"], p["ask"]
    meta = Meta(f"Credit proposal {p['proposal_id']}: {ob['name']}", book="corporate", period=AS_OF,
                subject=f"{ob['sector']} · {ob['internal_rating']}", generated_by=p["rm"], generated_at=BUILT,
                reference=p["proposal_id"])
    doc = hd.document(meta, kind="Credit memo", subtitle=p["purpose"],
                      details=[("Relationship manager", p["rm"]), ("Business unit", p["business_unit"]),
                               ("Received", p["received"]), ("Obligor", ob["name"])])
    hd.heading(doc, "1. Obligor")
    hd.table(doc, ["Field", "Value"], [
        ["Obligor name", ob["name"]], ["CR number", ob["cr_number"]], ["Obligor ID", ob["obligor_id"]],
        ["Existing client", "Yes" if ob.get("existing") else "No"],
        ["Group", f"{ob['group_name']} ({ob['group_id']})"], ["Sector", ob["sector"]], ["Sub-sector", ob["sub_sector"]],
        ["Sector code", ob.get("sector_code", "")], ["Region", ob["region"]], ["Internal rating", ob["internal_rating"]],
        ["External rating", ob.get("external_rating") or "Unrated"], ["SIMAH", ob["simah_flag"].capitalize()],
        ["Existing exposure (SAR m)", f"{ob.get('existing_exposure_sar_mn', 0.0):,.2f}"]])
    hd.heading(doc, "2. Financials (SAR m)")
    ys = p["financials"]["years"]
    hd.table(doc, ["Item"] + [f"{y['year']}{'' if y['kind'] == 'actual' else ' P'}" for y in ys],
             [[lab] + [f"{y[k]:,.2f}" for y in ys] for lab, k in
              (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("Total debt", "total_debt"), ("Debt service", "debt_service"),
               ("Net worth", "net_worth"), ("Current ratio (x)", "current_ratio"))], right_from=1)
    hd.heading(doc, "3. Request")
    lab = {"term_loan": "Term finance", "revolver": "Revolving working capital", "performance_lg": "Performance LG",
           "financial_lg": "Financial LG", "trade_lc": "Import LC"}
    base = "SAIBOR" if ask["currency"] == "SAR" else "SOFR"
    hd.table(doc, ["Term", "Requested"], [
        ["Facility type", lab[ask["facility_type"]]], ["Structure", ask["structure"].capitalize()],
        ["Currency", ask["currency"]], [f"Amount ({ask['currency']} m)", f"{ask['amount']:,.2f}"],
        ["Tenor (years)", str(ask["tenor_years"])], ["Grace period (years)", str(ask["grace_years"])],
        ["Amortisation", ask["amortisation"] + (f" ({ask['balloon_pct']}% balloon)" if ask["amortisation"] == "balloon" else "")],
        ["Margin", f"{base} + {ask['margin_bps']} bps"], ["Upfront fee", f"{ask['upfront_fee_bps']} bps"],
        ["Commitment fee", f"{ask['commitment_fee_bps']} bps"], ["LG/LC commission", f"{ask['commission_bps']} bps p.a."],
        ["Expected utilisation", f"{ask['utilisation_pct']}%"], ["Funded share", f"{ask['funded_share_pct']}%"],
        ["Cash margin", f"{ask['cash_margin_pct']}%"]])
    hd.heading(doc, "4. Security")
    cs = p["security"]["collateral"]
    if cs:
        hd.table(doc, ["ID", "Type", "Value", "Currency", "Valuation date", "Offered"],
                 [[c["collateral_id"], c["type"].replace("_", " "), f"{c['value']:,.2f}", c["currency"], c["valuation_date"],
                   "Yes" if c["pledged_in_ask"] else "Available"] for c in cs])
    else:
        hd.para(doc, "Collateral: none offered.")
    gs = p["security"]["guarantees"]
    if gs:
        hd.table(doc, ["ID", "Type", "Guarantor", "Rating", "Coverage", "Offered"],
                 [[g["guarantee_id"], g["type"], g["guarantor"], g["guarantor_rating"], f"{g['coverage_pct']}%",
                   "Yes" if g["offered_in_ask"] else "Available"] for g in gs])
    hd.para(doc, f"Covenant package: {p['security']['covenant_package']}.")
    hd.heading(doc, "5. Business case")
    anc = p["business_case"]["ancillary_income_sar_mn_pa"]
    hd.table(doc, ["Ancillary income (SAR m p.a.)", "Amount"],
             [[k.replace("_", " ").capitalize(), f"{v:,.2f}"] for k, v in anc.items()], right_from=1)
    hd.heading(doc, "6. Relationship manager's recommendation")
    hd.para(doc, f"{p['rm']} recommends the facility as requested: {p['purpose'].lower()}.")
    path.write_bytes(hd.to_bytes(doc))


def build(out: pathlib.Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pdir = out / "params" / "v1"
    pdir.mkdir(parents=True, exist_ok=True)
    for name, tab in seed.tables().items():
        (pdir / f"{name}.json").write_text(json.dumps(tab, indent=1, sort_keys=False) + "\n")
    props = build_proposals()
    (out / "proposals.json").write_text(json.dumps({"as_of": AS_OF, "proposals": props}, indent=1) + "\n")
    mdir = out / "memos"
    mdir.mkdir(exist_ok=True)
    for p in props:
        write_memo(p, mdir / p["memo"])
    from backend.dealdesk import relations
    rel = relations.write(out, props)
    files = sorted(q for q in out.rglob("*") if q.is_file() and q.name != "manifest.json" and q.suffix != ".parquet")
    manifest = {
        "domain": "dealdesk", "as_of": AS_OF, "built": BUILT.isoformat(),
        "provenance": ("Proposals and memos are generated by ops/dealdesk_build.py. Existing borrowers are pre-filled from "
                       f"the corporate book {paths.CORP_RELEASE} at {AS_OF}; new-to-bank names, their financials, asks "
                       "and security are constructed test cases. Parameter tables are seeded Saudi defaults (backend/dealdesk/seed.py)."),
        "spine": {"book": paths.CORP_RELEASE, "connected_groups": "data/relationships/rel-saudi-v1/rel_group_quarter.parquet"},
        "proposals": len(props), "existing": sum(1 for p in props if p["obligor"]["existing"]),
        "files": {str(q.relative_to(out)): hashlib.sha256(q.read_bytes()).hexdigest() for q in files
                  if q.suffix != ".docx" and q.parent.name not in ("model", "dd-saudi-v1")},
        "model_ranges": "model/feature_ranges.json (pd_model.build_ranges over the What-If corporate domain; ops/dealdesk_build.py --ranges)",
        "memos": sorted(p["memo"] for p in props),
        "relations": {k: {"rows": v["rows"], "content_sha256": v["content_sha256"]} for k, v in rel["relations"].items()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def main() -> int:
    if "--ranges" in sys.argv:
        from backend.dealdesk import pd_model
        (paths.DATA / "model").mkdir(parents=True, exist_ok=True)
        pd_model.RANGES_FILE.write_text(json.dumps(pd_model.build_ranges(), indent=1) + "\n")
        print(f"feature ranges -> {pd_model.RANGES_FILE}")
        return 0
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as d:
            m = build(pathlib.Path(d) / "dealdesk")
        committed = json.loads((paths.DATA / "manifest.json").read_text())
        same = m["files"] == committed["files"] and m["relations"] == committed.get("relations")
        print("DEALDESK BUILD CHECK", "PASS" if same else "FAIL")
        return 0 if same else 1
    if paths.DATA.exists():
        for sub in ("memos", "params", "dd-saudi-v1"):
            shutil.rmtree(paths.DATA / sub, ignore_errors=True)
    m = build(paths.DATA)
    print(f"Deal Desk domain: {m['proposals']} proposals ({m['existing']} existing borrowers), "
          f"{len(m['memos'])} memos, {sum(1 for k in m['files'] if k.startswith('params'))} parameter tables -> {paths.DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
