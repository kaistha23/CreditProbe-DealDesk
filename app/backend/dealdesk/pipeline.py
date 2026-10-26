"""R11 Session L: the pending pipeline and each deal's approval options (PLAN_R11 L2, L4).

The pipeline is every pending Deal Desk proposal (DD-01..15 and uploads with status new, in review or
counter-offered) plus a seeded set of fictional pending applications (PL-01..), stored in
data/dealdesk/pipeline/pipeline.json. The set is built with the same machinery and the same book as the DD
set (ops/dealdesk_build.py: `terms`, `fin`, `coll`, `guar`, `existing_obligor`, `build_proposals`), so every
one runs through the same engine. It shows only in Pipeline mode: `proposals.all_proposals()` never sees it.

    python3 -m backend.dealdesk.pipeline --build    write data/dealdesk/pipeline (proposals, options, manifest)
    python3 -m backend.dealdesk.pipeline --check    rebuild into a scratch folder and compare

Options per deal (L4): decline; approve as asked; approve the Optimise recommended structure (the
optimiser's "closest to the ask that clears", as the Optimise view shows it); approve at a reduced amount
(up to two points of the optimiser's frontier below the recommended amount). Each option carries the
engine's own metrics (SVA, RWA, EL, EAD, PV risk-adjusted profit and capital) and the deal-level limit
results, so the portfolio optimiser never recomputes a deal: it only adds them up.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import importlib.util
import json

import numpy as np
import pathlib
import sys
import tempfile
import threading
from typing import Any

from backend.dealdesk import engine, params, paths, pd_model, portfolio, proposals
from backend.dealdesk.seed import bucket

PIPE_DIR = paths.DATA / "pipeline"
PENDING = ("new", "in_review", "counter_offered")
#: Deal-level hard limits: a breach makes the option unavailable. The portfolio limits (single name,
#: connected group, large exposure, sector, budgets) are the optimiser's own constraints, across the selection.
DEAL_LEVEL = ("min_rating", "max_tenor", "ltv", "dscr", "debt_ebitda", "balloon", "structure")
PORTFOLIO_LEVEL = ("single_name", "group_connected", "group_large_exposure", "sector_policy", "sector_appetite",
                   "rating_bucket", "collateral_type", "bu_rwa_budget", "bu_el_budget")
UNSECURED_GUARANTEES = ("corporate", "personal")
_LOCK = threading.Lock()


def _ops():
    """ops/dealdesk_build.py, the DD set's seed machinery, loaded as a module."""
    path = paths.V5 / "ops" / "dealdesk_build.py"
    spec = importlib.util.spec_from_file_location("_dealdesk_build_for_pipeline", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ------------------------------------------------------------------ the seeded pipeline set (fictional names)

def specs(b) -> list[dict[str, Any]]:
    """About 25 pending applications spread over sector, size, rating and structure so the limits bind:
    construction and real estate near the combined cap, a few sub-investment-grade names, one connected
    group (Al Kharj National Engineering Group, already on the book) with two new applications, and one
    name below the minimum rating."""
    T, F, C, G = b.terms, b.fin, b.coll, b.guar

    def new(oid, name, sector, sub, region, rating, group_id=None, group_name=None, **kw):
        return {"obligor_id": oid, "name": name, "cr_number": "70" + hashlib.sha256(oid.encode()).hexdigest()[:8].translate(
                    str.maketrans("abcdef", "123456")), "sector": sector, "sub_sector": sub, "segment": sector, "region": region,
                "internal_rating": rating, "external_rating": None, "gre": kw.get("gre", False), "sme": False,
                "simah_flag": kw.get("simah", "clear"), "gov_linked": kw.get("gov", False),
                "group_id": group_id or f"DG{oid[2:]}", "group_name": group_name or name.replace(" Company", "") + " Holding",
                "connected_parties": [], "real_estate_finance": kw.get("ref", False)}

    KH = ("CG6292-094", "Al Kharj National Engineering Group")
    rm = ["Khalid Al-Otaibi", "Sara Al-Dosari", "Abdullah Al-Zahrani"]
    out = [
        ("PL-01", "Ring road interchange package for the Riyadh municipality",
         new("DP001", "Al Masar Infrastructure Contracting Company", "Construction", "Civil Infrastructure", "Riyadh", "BBB"),
         F(1400, 0.14, 300, 60, 650, 1.4), T(structure="tawarruq", amount=220, tenor_years=5, grace_years=1, margin_bps=250,
                                             upfront_fee_bps=60, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 150.0, date="2026-08-31")], [], {"cash_management": 0.5, "payroll": 0.4, "fx": 0.0, "trade": 0.1}),
        ("PL-02", "Working capital for school building contracts in Riyadh and Kharj",
         new("DP002", "Wadi Hanifa Building Company", "Construction", "Buildings", "Riyadh", "BB-"),
         F(600, 0.12, 120, 24, 210, 1.2), T(structure="murabaha", amount=90, tenor_years=4, margin_bps=360, upfront_fee_bps=80,
                                            collateral_ids=["C1"]),
         [C("C1", "receivables", 60.0)], [], {"cash_management": 0.1, "payroll": 0.15, "fx": 0.0, "trade": 0.05}),
        ("PL-03", "Performance guarantees for a Red Sea marina and breakwater contract",
         new("DP003", "Red Sea Marine Works Company", "Construction", "Marine Works", "Makkah", "BBB-"),
         F(820, 0.13, 150, 30, 400, 1.3), T(facility_type="performance_lg", amount=150, tenor_years=3, amortisation="bullet",
                                            margin_bps=0, upfront_fee_bps=25, commission_bps=110, cash_margin_pct=10,
                                            covenant_package="none"),
         [], [], {"cash_management": 0.2, "payroll": 0.2, "fx": 0.0, "trade": 0.1}),
        ("PL-04", "Equipment for mountain road works in Asir",
         new("DP004", "Tihama Roads Contracting Company", "Construction", "Civil Infrastructure", "Asir", "B+"),
         F(300, 0.13, 70, 14, 110, 1.1), T(structure="tawarruq", amount=45, tenor_years=5, grace_years=1, margin_bps=430,
                                           upfront_fee_bps=90, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 40.0, date="2026-07-15")], [], {"cash_management": 0.03, "payroll": 0.05, "fx": 0.0, "trade": 0.0}),
        ("PL-05", "Ijara of a completed residential compound in north Riyadh",
         new("DP005", "Al Olaya Residential Developments Company", "Real Estate", "Residential Property", "Riyadh", "BB+", ref=True),
         F(120, 0.60, 100, 18, 480, 1.3, growth=0.03), T(structure="ijara", amount=180, tenor_years=7, amortisation="balloon",
                                                         balloon_pct=40, margin_bps=270, upfront_fee_bps=70, collateral_ids=["C1"]),
         [C("C1", "real_estate", 300.0, date="2026-06-30")], [], {"cash_management": 0.1, "payroll": 0.0, "fx": 0.0, "trade": 0.0}),
        ("PL-06", "Refinancing of a seafront hotel and serviced apartments on the Jeddah corniche",
         new("DP006", "Jeddah Corniche Hospitality Properties Company", "Real Estate", "Commercial Property", "Makkah", "BBB-", ref=True),
         F(110, 0.58, 60, 11, 420, 1.4, growth=0.03), T(structure="murabaha", amount=140, tenor_years=9, grace_years=1,
                                                        margin_bps=230, upfront_fee_bps=60, collateral_ids=["C1"]),
         [C("C1", "real_estate", 260.0, date="2026-05-31")], [], {"cash_management": 0.15, "payroll": 0.05, "fx": 0.0, "trade": 0.0}),
        ("PL-07", "Grade A logistics park next to the Dammam second industrial city",
         new("DP007", "Dammam Logistics Parks Company", "Real Estate", "Industrial Property", "Eastern Province", "A-", ref=True),
         F(160, 0.55, 80, 14, 700, 1.6, growth=0.04), T(structure="musharaka", amount=200, tenor_years=10, grace_years=2,
                                                        margin_bps=180, upfront_fee_bps=50, collateral_ids=["C1"]),
         [C("C1", "real_estate", 330.0, date="2026-08-15")], [], {"cash_management": 0.3, "payroll": 0.05, "fx": 0.05, "trade": 0.05}),
        ("PL-08", "Mobilisation and equipment for a water transmission pipeline contract",
         new("DP008", "Al Kharj National Engineering Contracting Company", "Construction", "Utilities Construction", "Riyadh", "BB",
             group_id=KH[0], group_name=KH[1]),
         F(1500, 0.13, 380, 76, 600, 1.3), T(structure="tawarruq", amount=180, tenor_years=5, grace_years=1, margin_bps=310,
                                             upfront_fee_bps=75, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 120.0, date="2026-09-01")], [G("G1", "corporate", "Al Kharj National Engineering Group (parent)", "BB", 50)],
         {"cash_management": 0.3, "payroll": 0.3, "fx": 0.0, "trade": 0.1}),
        ("PL-09", "Development finance for staff housing at the group's Kharj yard",
         new("DP009", "Al Kharj National Engineering Properties Company", "Real Estate", "Residential Property", "Riyadh", "BB",
             group_id=KH[0], group_name=KH[1], ref=True),
         F(90, 0.62, 40, 8, 380, 1.3, growth=0.03), T(structure="murabaha", amount=160, tenor_years=7, grace_years=1,
                                                      amortisation="balloon", balloon_pct=30, margin_bps=290, upfront_fee_bps=70,
                                                      collateral_ids=["C1"]),
         [C("C1", "real_estate", 250.0, date="2026-07-31")], [], {"cash_management": 0.05, "payroll": 0.0, "fx": 0.0, "trade": 0.0}),
        ("PL-10", "Ijara of surgical and imaging equipment for a specialist hospital",
         new("DP010", "Al Madinah Specialist Hospital Company", "Healthcare", "Hospitals", "Madinah", "A"),
         F(700, 0.22, 160, 32, 520, 1.5), T(structure="ijara", amount=120, tenor_years=7, margin_bps=215, upfront_fee_bps=50,
                                            collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 140.0, date="2026-09-10")], [], {"cash_management": 0.3, "payroll": 0.4, "fx": 0.05, "trade": 0.05}),
        ("PL-11", "Second float glass line in Yanbu",
         new("DP011", "Yanbu Glass Industries Company", "Manufacturing", "Building Materials", "Madinah", "BBB+"),
         F(900, 0.20, 250, 50, 700, 1.6), T(amount=160, tenor_years=6, grace_years=1, margin_bps=235, upfront_fee_bps=50,
                                            collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 180.0, date="2026-06-30")], [], {"cash_management": 0.3, "payroll": 0.2, "fx": 0.1, "trade": 0.3}),
        ("PL-12", "Specialty chemicals plant expansion at Ras Al Khair",
         new("DP012", "Ras Al Khair Specialty Chemicals Company", "Chemicals", "Specialty Chemicals", "Eastern Province", "AA-"),
         F(2600, 0.23, 700, 140, 3300, 2.0), T(currency="USD", amount=40, tenor_years=10, grace_years=2, margin_bps=160,
                                               upfront_fee_bps=30),
         [], [], {"cash_management": 0.4, "payroll": 0.2, "fx": 0.4, "trade": 0.3}),
        ("PL-13", "Desalination capacity for the Northern Borders water network",
         new("DP013", "Northern Water Desalination Company", "Power and Utilities", "Water", "Northern Borders", "A+", gre=True, gov=True),
         F(1900, 0.38, 1800, 300, 4200, 1.2, growth=0.04), T(structure="murabaha", amount=230, tenor_years=10, grace_years=2,
                                                             margin_bps=150, upfront_fee_bps=30),
         [], [G("G1", "government", "Ministry of Environment, Water and Agriculture letter of support", "A+", 100)],
         {"cash_management": 0.6, "payroll": 0.3, "fx": 0.0, "trade": 0.1}),
        ("PL-14", "Fibre-to-the-home roll-out in Hail and Qassim",
         new("DP014", "Hail Fibre Networks Company", "Telecommunications", "Fixed Networks", "Hail", "BBB"),
         F(520, 0.30, 220, 44, 380, 1.3), T(structure="tawarruq", amount=110, tenor_years=6, grace_years=1, margin_bps=255,
                                            upfront_fee_bps=55),
         [], [], {"cash_management": 0.2, "payroll": 0.1, "fx": 0.0, "trade": 0.05}),
        ("PL-15", "Tier III data centre fit-out in Riyadh",
         new("DP015", "Riyadh Cloud Data Centres Company", "Information Technology", "Data Centres", "Riyadh", "BB+"),
         F(380, 0.32, 140, 28, 300, 1.4), T(structure="ijara", amount=130, tenor_years=7, grace_years=1, margin_bps=260,
                                            upfront_fee_bps=70, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 120.0, date="2026-09-05")], [], {"cash_management": 0.15, "payroll": 0.1, "fx": 0.05, "trade": 0.0}),
        ("PL-16", "Import letters of credit for steel and cement",
         new("DP016", "Jeddah Building Supplies Trading Company", "Wholesale Trade", "Building Supplies", "Makkah", "BB"),
         F(950, 0.06, 90, 18, 160, 1.3), T(facility_type="trade_lc", structure="murabaha", currency="USD", amount=20, tenor_years=1,
                                           amortisation="bullet", margin_bps=0, upfront_fee_bps=25, commission_bps=95,
                                           utilisation_pct=75, cash_margin_pct=10, covenant_package="none"),
         [], [], {"cash_management": 0.1, "payroll": 0.05, "fx": 0.15, "trade": 0.2}),
        ("PL-17", "Refurbishment of a mountain resort in Taif",
         new("DP017", "Taif Mountain Resorts Company", "Hospitality", "Resorts", "Makkah", "B"),
         F(210, 0.24, 90, 18, 160, 1.0), T(structure="murabaha", amount=70, tenor_years=5, grace_years=1, margin_bps=460,
                                           upfront_fee_bps=100, collateral_ids=["C1"]),
         [C("C1", "real_estate", 95.0, date="2026-04-30")], [], {"cash_management": 0.03, "payroll": 0.05, "fx": 0.0, "trade": 0.0}),
        ("PL-18", "Cold storage and packing lines for date processing",
         new("DP018", "Al Jouf Date Processing Company", "Agriculture and Agri-processing", "Food Processing", "Northern Borders", "BB-"),
         F(240, 0.16, 50, 10, 120, 1.3), T(structure="murabaha", amount=40, tenor_years=5, grace_years=1, margin_bps=330,
                                           upfront_fee_bps=80, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 30.0, date="2026-08-20")], [], {"cash_management": 0.05, "payroll": 0.05, "fx": 0.0, "trade": 0.05}),
        ("PL-19", "Mining services fleet for phosphate operations",
         new("DP019", "Northern Borders Phosphate Services Company", "Metals and Mining", "Mining Services", "Northern Borders", "B"),
         F(420, 0.18, 120, 24, 180, 1.1), T(structure="ijara", amount=60, tenor_years=4, margin_bps=440, upfront_fee_bps=90,
                                            collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 70.0, date="2026-07-01")], [], {"cash_management": 0.05, "payroll": 0.08, "fx": 0.0, "trade": 0.0}),
        ("PL-20", "Revolving working capital for a hypermarket chain",
         new("DP020", "Al Nahda Hypermarkets Company", "Retail Trade", "Grocery", "Eastern Province", "BBB-"),
         F(1800, 0.07, 160, 32, 420, 0.9), T(facility_type="revolver", structure="murabaha", amount=80, tenor_years=3,
                                             amortisation="bullet", margin_bps=245, upfront_fee_bps=40, commitment_fee_bps=25,
                                             utilisation_pct=60),
         [], [], {"cash_management": 0.4, "payroll": 0.3, "fx": 0.05, "trade": 0.2}),
        ("PL-21", "Ijara of a heavy haulage truck fleet",
         new("DP021", "Eastern Haulage Company", "Transport and Logistics", "Road Freight", "Eastern Province", "BB"),
         F(330, 0.19, 80, 16, 170, 1.2), T(structure="ijara", amount=55, tenor_years=5, margin_bps=300, upfront_fee_bps=70,
                                           collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 65.0, date="2026-09-12")], [], {"cash_management": 0.08, "payroll": 0.06, "fx": 0.0, "trade": 0.0}),
        ("PL-22", "Performance guarantee for a Kharj substation contract",
         {"existing": "CB00723", "sector": "Construction", "segment": "Construction", "simah_flag": "clear"}, None,
         T(facility_type="performance_lg", amount=20, tenor_years=3, amortisation="bullet", margin_bps=0, upfront_fee_bps=20,
           commission_bps=100, cash_margin_pct=10, covenant_package="none"),
         [], [], {"cash_management": 0.03, "payroll": 0.02, "fx": 0.0, "trade": 0.02}),
        ("PL-23", "Fit-out of a retail podium in Dammam",
         {"existing": "CB03526", "sector": "Real Estate", "segment": "Real Estate", "simah_flag": "clear"}, None,
         T(structure="murabaha", amount=10, tenor_years=5, margin_bps=260, upfront_fee_bps=60, collateral_ids=["C1"]),
         [C("C1", "real_estate", 18.0, date="2026-06-15")], [], {"cash_management": 0.02, "payroll": 0.0, "fx": 0.0, "trade": 0.0}),
        ("PL-24", "Room renovation programme",
         {"existing": "CB01723", "sector": "Hospitality", "segment": "Hospitality", "simah_flag": "clear"}, None,
         T(structure="tawarruq", amount=12, tenor_years=5, margin_bps=320, upfront_fee_bps=70),
         [], [], {"cash_management": 0.02, "payroll": 0.02, "fx": 0.0, "trade": 0.0}),
        ("PL-25", "Seasonal working capital for Ramadan stock",
         {"existing": "CB05102", "sector": "Wholesale Trade", "segment": "Wholesale Trade", "simah_flag": "clear"}, None,
         T(facility_type="revolver", structure="murabaha", amount=30, tenor_years=3, amortisation="bullet", margin_bps=205,
           upfront_fee_bps=35, commitment_fee_bps=20, utilisation_pct=55),
         [], [], {"cash_management": 0.05, "payroll": 0.02, "fx": 0.03, "trade": 0.06}),
        ("PL-26", "Store refits in the Eastern Province",
         {"existing": "CB04054", "sector": "Retail Trade", "segment": "Retail Trade", "simah_flag": "clear"}, None,
         T(structure="murabaha", amount=12, tenor_years=3, margin_bps=480, upfront_fee_bps=90),
         [], [], {"cash_management": 0.02, "payroll": 0.02, "fx": 0.0, "trade": 0.0}),
        ("PL-27", "Earthmoving fleet for a subcontract in Al Jouf",
         new("DP027", "Qurayyat Earthmoving Company", "Construction", "Earthworks", "Northern Borders", "CCC", simah="watch"),
         F(150, 0.10, 60, 12, 40, 0.9, growth=0.0), T(structure="tawarruq", amount=25, tenor_years=2, margin_bps=560,
                                                      upfront_fee_bps=120, collateral_ids=["C1"]),
         [C("C1", "plant_equipment", 18.0, date="2026-03-31")], [], {"cash_management": 0.01, "payroll": 0.02, "fx": 0.0, "trade": 0.0}),
    ]
    res = []
    for i, (pid, purpose, ob, fins, ask, coll, guars, anc) in enumerate(out):
        s = {"id": pid, "case": "pipeline", "rm": rm[i % 3], "received": f"2026-10-{12 + i % 6:02d}",
             "status": "in_review" if i % 4 == 1 else "new", "purpose": purpose, "ask": ask, "collateral": coll,
             "guarantees": guars, "ancillary": anc}
        if "existing" in ob:
            s["existing"] = ob.pop("existing")
            s["obligor"] = ob
        else:
            s["obligor"] = ob
            s["financials"] = fins
        res.append(s)
    return res


def build_set() -> list[dict[str, Any]]:
    b = _ops()
    b.SPECS = specs(b)
    out = b.build_proposals()
    for p in out:
        p["memo"] = ""
        p["source"] = "pipeline"
    return out


# ------------------------------------------------------------------ the pending pipeline

@functools.lru_cache(maxsize=1)
def seeded_set() -> dict[str, dict[str, Any]]:
    """The PL set, read from Data Domains (deal_desk.dd_pipeline) through the R12 readers (PLAN_R12 §0).
    pipeline.json stays the build artefact of `--build` / `--check`; backend.dealdesk.data.build moves it into dd_pipeline."""
    from backend.dealdesk.data import deals  # R12-E
    return deals.pipeline_set()


def get(pid: str) -> dict[str, Any]:
    """A pipeline-set application or any Deal Desk proposal."""
    s = seeded_set()
    if pid in s:
        return copy.deepcopy(s[pid])
    return proposals.get(pid)


def pending() -> list[dict[str, Any]]:
    """Every pending deal: Deal Desk proposals (seeded and uploaded) with a pending status, the R12 demo deals with a
    pending status (R14 U, K17: the twins, R12-ESC, R12-SYN… are pending applications like any other, so the Pipeline
    tab and the Deal Desk list count the same deals), then the pipeline set."""
    dd = [p for p in proposals.all_proposals().values() if p.get("status") in PENDING]
    seen = {p["proposal_id"] for p in dd}
    demo = [copy.deepcopy(p) for k, p in sorted(_demo_set().items()) if k not in seen and p.get("status") in PENDING]
    pl = [copy.deepcopy(p) for p in seeded_set().values()]
    return sorted(dd, key=lambda p: p["proposal_id"]) + demo + pl


def _demo_set() -> dict[str, dict[str, Any]]:
    """dd_deal's R12 demo deals with their Data Domains status (empty before the R12 build)."""
    try:
        from backend.dealdesk.data import deals
        reg = {r["proposal_id"]: r for r in deals.register(source="r12_demo")}
        out = {}
        for k, p in deals._demo().items():
            q = dict(p, source="r12_demo")
            if reg.get(k, {}).get("status"):
                q["status"] = reg[k]["status"]
            out[k] = q
        return out
    except Exception:  # noqa: BLE001
        return {}


def source(p: dict[str, Any]) -> str:
    if p.get("source") == "pipeline":
        return "Pipeline set"
    if p.get("source") == "r12_demo":
        return "Reference deal"
    return "Deal Desk" if len(p["proposal_id"]) == 5 and p["proposal_id"].startswith("DD-") else "Uploaded"


def row(p: dict[str, Any]) -> dict[str, Any]:
    s = proposals.summary(p)
    s["source"] = source(p)
    s["region"] = p["obligor"].get("region", "")
    s["group_id"] = p["obligor"].get("group_id", "")
    s["group_name"] = p["obligor"].get("group_name", "")
    s["purpose"] = p.get("purpose", "")
    return s


# ------------------------------------------------------------------ options

def _key(p: dict[str, Any]) -> str:
    body = json.dumps({k: v for k, v in p.items() if k not in ("status",)}, sort_keys=True, default=str)
    meta = json.dumps({"params": params.versions(), "model": pd_model.model_meta()["version"], "algo": OPTIONS_VERSION}, sort_keys=True)
    return hashlib.sha256((body + meta).encode()).hexdigest()[:20]


OPTIONS_VERSION = "r11-options-3"


def _secured(a: dict[str, Any]) -> bool:
    lg = a["lgd"]
    if float(lg.get("collateral_recognised_sar_mn") or 0) > 0 or float(lg.get("cash_margin_sar_mn") or 0) > 0:
        return True
    g = lg.get("guarantee")
    if g and g.get("type") not in UNSECURED_GUARANTEES:
        return True
    return bool(lg.get("insurance"))


_S2: dict[str, tuple[float, str]] = {}


def _forward():
    """Session F's forward-risk module when it is merged (PLAN_R11 L3), else None."""
    try:
        from backend.dealdesk import forward_risk  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - not merged yet: the plan's fallback applies
        return None
    return forward_risk if hasattr(forward_risk, "structure_risk") or hasattr(forward_risk, "stage2_probability") else None


def _stage2_weight(p: dict[str, Any], terms: dict[str, Any]) -> tuple[float, str]:
    """A deal's Stage 2 weight: F's P(Stage 2 next quarter) for this structure when the forward-risk model is merged,
    else the obligor's current stage (an existing borrower with a Stage 2 facility counts as Stage 2; a new name as Stage 1)."""
    fr = _forward()
    if fr is not None:
        key = hashlib.sha256(json.dumps([p["proposal_id"], p["obligor"].get("obligor_id"), terms], sort_keys=True, default=str)
                             .encode()).hexdigest()
        if key in _S2:
            return _S2[key]
        try:
            if hasattr(fr, "structure_risk"):
                v = fr.structure_risk(p, terms)["p_stage2_next_q"]
            else:
                v = fr.stage2_probability(p, terms)
            if v is not None:
                _S2[key] = (float(v), "forward-risk model: P(Stage 2 next quarter)")
                return _S2[key]
        except Exception:  # noqa: BLE001 - a scoring failure falls back to the current stage
            pass
    st = max([int(f.get("stage", 1)) for f in p["obligor"].get("existing_facilities", [])] or [1])
    return (1.0 if st >= 2 else 0.0), "obligor's current stage"


def _with_stage2(p: dict[str, Any], d: dict[str, Any]) -> dict[str, Any]:
    """Options with the Stage 2 weight of the build in use (F's model when merged); the cached engine figures are unchanged."""
    if _forward() is None:
        return d
    out = copy.deepcopy(d)
    for o in out["options"]:
        o["stage2_weight"], o["stage2_basis"] = _stage2_weight(p, o["terms"])
    return out


def _option(p: dict[str, Any], kind: str, label: str, terms: dict[str, Any] | None) -> dict[str, Any]:
    a = engine.analyse(p, terms)
    m = a["metrics"]
    cs = {c["name"]: c for c in a["constraints"]}
    deal_hard = [c["name"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard" and c["name"] in DEAL_LEVEL]
    deal_soft = [c["name"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "soft" and c["name"] in DEAL_LEVEL]
    t = a["terms"]
    s2, s2_basis = _stage2_weight(p, t)
    pk = "commission_bps" if t["facility_type"] in ("performance_lg", "financial_lg", "trade_lc") else "margin_bps"
    tb = dict(t)
    tb[pk] = float(t.get(pk) or 0) + 10
    per_bp = (float(engine.analyse(p, tb, validate=False)["metrics"]["sva"]) - float(m["sva"])) / 10.0
    return {
        "kind": kind, "label": label, "terms": engine._clean(t),
        "amount_sar_mn": float(m["amount_sar_mn"]), "held_sar_mn": float(m["held_sar_mn"]),
        "sva": float(m["sva"]), "lifetime_raroc": m["lifetime_raroc"], "clears_hurdle": bool(m["clears_hurdle"]),
        "rwa": float(m["rwa_y1"]), "el": float(m["el_y1"]), "ead": float(m["ead_y1"]),
        "pv_rap": float(m["pv_rap"]), "pv_capital": float(m["pv_capital"]), "hurdle": float(m["hurdle"]),
        "available": not deal_hard, "deal_hard_breaches": deal_hard, "deal_soft_breaches": deal_soft,
        "approval": a["approval"]["level"],
        "secured": _secured(a), "collateral_types": sorted({c["type"] for c in a["lgd"]["collateral"]}),
        "islamic": t["structure"] != "conventional", "tenor_years": int(t["tenor_years"]),
        "stage2_weight": s2, "stage2_basis": s2_basis,
        "price_lever": pk, "sva_per_bp": per_bp if per_bp > 1e-9 else None,
        "engine_single_name": cs["single_name"]["value"], "engine_sector_share": cs["sector_policy"]["value"],
    }


def _distinct(opts: list[dict[str, Any]], o: dict[str, Any]) -> bool:
    return all(abs(x["amount_sar_mn"] - o["amount_sar_mn"]) > 1e-6 or abs(x["sva"] - o["sva"]) > 1e-6 for x in opts)


def compute_options(p: dict[str, Any]) -> dict[str, Any]:
    """The approval options of one deal, every figure from the engine."""
    from backend.dealdesk import optimizer
    opts = [_option(p, "ask", "As asked", None)]
    rec_terms, frontier = None, []
    try:
        o = optimizer.optimize(p, counter_offers=False)
        if o.get("closest"):
            rec_terms = o["closest"]["terms"]
        frontier = o.get("frontier") or []
    except engine.TermsError:
        o = None
    if rec_terms is not None:
        r = _option(p, "recommended", "Recommended structure", rec_terms)
        if _distinct(opts, r):
            opts.append(r)
        else:
            opts[0]["recommended_equals_ask"] = True
        ref = r["amount_sar_mn"]
        X = engine.fx(p["ask"]["currency"])
        lower = sorted({round(float(f["amount"]), 6) for f in frontier if float(f["amount"]) * X < ref - 1e-6})
        picks = []
        if lower:
            picks = [lower[0]] if len(lower) == 1 else [lower[0], lower[len(lower) // 2]] if len(lower) > 2 else lower
        for amt in sorted(set(picks), reverse=True):
            fr = min((f for f in frontier if abs(float(f["amount"]) - amt) < 1e-6), key=lambda f: f["distance"])
            x = _option(p, "reduced", f"Reduced to {amt * X:,.0f}m", fr["terms"])
            if _distinct(opts, x) and len(opts) < 4:
                opts.append(x)
    # Reduced amounts: the optimiser's frontier rarely moves the amount (it reprices first), so the amount
    # frontier is completed on the best clearing structure, down to the smallest amount a client accepts
    # (market_bounds.min_amount_share) and half-way to it.
    base = next((x for x in reversed(opts) if x["kind"] == "recommended"), None) or (opts[0] if opts[0]["clears_hurdle"] else None)
    if base is not None:
        share = float(params.rows("market_bounds")["min_amount_share"])
        for f in (1 - (1 - share) / 2, share):
            if sum(1 for x in opts if x["kind"] == "reduced") >= 2:
                break
            t = dict(base["terms"])
            amt = round(float(t["amount"]) * f, 2)
            t["amount"] = amt
            try:
                x = _option(p, "reduced", f"Reduced to {amt * engine.fx(t['currency']):,.0f}m", t)
            except engine.TermsError:
                continue
            if _distinct(opts, x):
                opts.append(x)
    ob = p["obligor"]
    return {"proposal_id": p["proposal_id"], "key": _key(p), "options": opts,
            "deal": {"obligor_id": ob["obligor_id"], "name": ob["name"], "existing": bool(ob.get("existing")),
                     "group_id": ob.get("group_id") or "", "group_name": ob.get("group_name", ""), "sector": ob["sector"],
                     "region": ob.get("region", ""), "rating": ob["internal_rating"], "bucket": bucket(ob["internal_rating"]),
                     "obligor_book_ead": portfolio.obligor_ead(ob["obligor_id"]) if ob.get("existing") else 0.0,
                     "group_book_ead": _group_book(ob), "connected": _connected(ob)}}


def _group_book(ob: dict[str, Any]) -> float:
    gid = ob.get("group_id")
    if not ob.get("existing") and not str(gid or "").startswith("CG"):
        return 0.0
    return portfolio.group_ead(gid)


def _connected(ob: dict[str, Any]) -> bool:
    """In a connected group of two or more companies (relationship domain), or a group with two applications."""
    gid = ob.get("group_id") or ""
    n = portfolio.snapshot()["group_borrowers"].get(gid, 0)
    if ob.get("existing"):
        return n >= 2
    return gid.startswith("CG") and n >= 1


def _cache_file() -> pathlib.Path:
    d = paths.VAR / "pipeline"
    d.mkdir(parents=True, exist_ok=True)
    return d / "options.json"


@functools.lru_cache(maxsize=1)
def _seeded_options() -> dict[str, Any]:
    f = PIPE_DIR / "options.json"
    return json.loads(f.read_text())["deals"] if f.exists() else {}


_MEM: dict[str, Any] = {}


def options(p: dict[str, Any]) -> dict[str, Any]:
    """A deal's options (engine figures cached) with the Stage 2 weight of this build."""
    return _with_stage2(p, _options(p))


def _options(p: dict[str, Any]) -> dict[str, Any]:
    """Options for a deal: the committed cache (built with the set), then the runtime cache, else computed."""
    k = _key(p)
    pid = p["proposal_id"]
    hit = _MEM.get(pid)
    if hit and hit["key"] == k:
        return hit
    s = _seeded_options().get(pid)
    if s and s["key"] == k:
        _MEM[pid] = s
        return s
    with _LOCK:
        f = _cache_file()
        disk = json.loads(f.read_text()) if f.exists() else {}
        if pid in disk and disk[pid]["key"] == k:
            _MEM[pid] = disk[pid]
            return disk[pid]
    o = compute_options(p)
    with _LOCK:
        f = _cache_file()
        disk = json.loads(f.read_text()) if f.exists() else {}
        disk[pid] = o
        f.write_text(json.dumps(disk))
    _MEM[pid] = o
    return o


# ------------------------------------------------------------------ build

def build(out: pathlib.Path, with_options: bool = True) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    props = build_set()
    (out / "pipeline.json").write_text(json.dumps({"as_of": paths.AS_OF, "proposals": props}, indent=1) + "\n")
    deals = [p for p in proposals.all_proposals().values() if len(p["proposal_id"]) == 5]
    if with_options:
        opts = {p["proposal_id"]: compute_options(p) for p in deals + props}
        (out / "options.json").write_text(json.dumps({"as_of": paths.AS_OF, "version": OPTIONS_VERSION, "deals": opts}, indent=1) + "\n")
    m = {"domain": "dealdesk-pipeline", "as_of": paths.AS_OF, "applications": len(props), "dd_proposals_cached": len(deals),
         "provenance": ("Fictional pending applications built by backend/dealdesk/pipeline.py with the DD seed machinery "
                        "(ops/dealdesk_build.py) on the corporate book " + paths.CORP_RELEASE + " at " + paths.AS_OF +
                        "; options.json caches each deal's engine options (keyed by proposal, parameter and model version)."),
         "files": {q.name: hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(out.glob("*.json")) if q.name != "manifest.json"}}
    (out / "manifest.json").write_text(json.dumps(m, indent=1) + "\n")
    return m


def main(argv: list[str]) -> int:
    if "--check" in argv:
        with tempfile.TemporaryDirectory() as d:
            m = build(pathlib.Path(d) / "pipeline", with_options=False)
        committed = json.loads((PIPE_DIR / "manifest.json").read_text())
        same = m["files"]["pipeline.json"] == committed["files"]["pipeline.json"]
        print("PIPELINE BUILD CHECK", "PASS" if same else "FAIL")
        return 0 if same else 1
    m = build(PIPE_DIR)
    print(f"Pipeline set: {m['applications']} applications -> {PIPE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


# ------------------------------------------------------------------ portfolio optimisation (L4) and the pipeline test (L5)

FRONTIER_STEPS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)
SHADOW_STEP = {"bu_rwa_budget": 100.0, "bu_el_budget": 5.0}
TERMS_SHOWN = (("amount", "amount", ""), ("tenor_years", "tenor", "y"), ("margin_bps", "margin", " bps"),
               ("commission_bps", "commission", " bps"), ("upfront_fee_bps", "fee", " bps"), ("cash_margin_pct", "cash margin", "%"),
               ("guarantee_coverage_pct", "guarantee cover", "%"), ("covenant_package", "covenants", ""), ("structure", "structure", ""))


def _deals(ids: list[str] | None) -> list[dict[str, Any]]:
    ps = pending()
    if ids:
        want = list(dict.fromkeys(ids))
        have = {p["proposal_id"]: p for p in ps}
        missing = [i for i in want if i not in have]
        if missing:
            raise KeyError(", ".join(missing))
        ps = [have[i] for i in want]
    return ps


def _changes(o: dict[str, Any], ask: dict[str, Any]) -> str:
    t = o["terms"]
    out = []
    for k, label, unit in TERMS_SHOWN:
        a, b = ask.get(k), t.get(k)
        if a != b and b is not None and not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(float(a) - float(b)) < 1e-9):
            if isinstance(b, (int, float)):
                out.append(f"{label} {a:g}{unit} to {b:g}{unit}")
            else:
                out.append(f"{label} {a} to {b}")
    return ", ".join(out[:3])


def _opt_public(o: dict[str, Any], j: int) -> dict[str, Any]:
    keys = ("kind", "label", "amount_sar_mn", "sva", "lifetime_raroc", "rwa", "el", "ead", "available", "deal_hard_breaches",
            "deal_soft_breaches", "approval", "clears_hurdle", "secured", "islamic", "tenor_years", "stage2_weight", "stage2_basis")
    return {"index": j, **{k: o[k] for k in keys}, "structure": o["terms"]["structure"], "facility_type": o["terms"]["facility_type"]}


def _margin_key(o: dict[str, Any]) -> str:
    return "commission_bps" if o["terms"]["facility_type"] in ("performance_lg", "financial_lg", "trade_lc") else "margin_bps"


def _sva_per_bp(p: dict[str, Any], o: dict[str, Any]) -> float | None:
    if "sva_per_bp" in o:
        return o["sva_per_bp"]
    k = _margin_key(o)
    t = dict(o["terms"])
    t[k] = float(t.get(k) or 0) + 10
    try:
        a = engine.analyse(p, t, validate=False)
    except engine.TermsError:
        return None
    d = (float(a["metrics"]["sva"]) - float(o["sva"])) / 10.0
    return d if d > 1e-9 else None


def _solve(space, forced=None, b=None, allowed=None, free=None):
    from backend.dealdesk.pipeline_solver import Solver
    return Solver(space, forced=forced, b=b, allowed=allowed, free=free).solve()


def _violated(space, agg) -> list[str]:
    u = space.H @ agg
    return list(dict.fromkeys(f"{space.hard_meta[i]['label']} ({space.hard_meta[i]['scope']})"
                              for i in range(len(u)) if u[i] > space.b[i] + 1e-7))


def _binding(space, res, cap: int = 3) -> list[dict[str, Any]]:
    """Binding hard limits and their shadow prices. A row is a candidate when some value-adding option left out
    (or a larger option of a chosen deal) needs more of it than the selection leaves; each candidate is re-solved
    with the row relaxed by one step, and a row binds when that adds SVA."""
    from backend.dealdesk.pipeline_solver import min_sva
    u = space.H @ res.agg
    slack = space.b - u
    need: dict[int, float] = {}
    for k, d in enumerate(space.deals):
        cur = space.H @ space.V[k][res.choice[k]] if res.choice[k] >= 0 else np.zeros(len(slack))
        cur_sva = d["options"][res.choice[k]]["sva"] if res.choice[k] >= 0 else 0.0
        for j, o in enumerate(d["options"]):
            if j == res.choice[k] or not o["available"] or o["sva"] < min_sva() or o["sva"] <= cur_sva + 1e-9:
                continue
            extra = space.H @ space.V[k][j] - cur
            for i in np.flatnonzero(extra > slack + 1e-9):
                r = slack[i] / extra[i] if extra[i] > 0 else 0.0
                need[i] = min(need.get(i, np.inf), r)
    cands = sorted(need, key=lambda i: need[i])[: cap + 2]
    rows = []
    for i in cands:
        m = space.hard_meta[i]
        step = SHADOW_STEP.get(m["name"], 100.0)
        b2 = space.b.copy()
        b2[i] += step
        r2 = _solve(space, b=b2)
        gain = (r2.objective - res.objective) if r2.feasible else 0.0
        if gain <= 1e-6:
            continue
        per = "SAR 100m of RWA" if m["name"] == "bu_rwa_budget" else "SAR 5m of EL budget" if m["name"] == "bu_el_budget" \
            else "SAR 100m of headroom"
        where = "" if m["scope"] in ("new business", "book") else f" ({_scope_name(space, m)})"
        rows.append({"name": m["name"], "label": m["label"], "scope": m["scope"], "scope_name": _scope_name(space, m),
                     "slack": float(slack[i]), "step": step, "per": per, "shadow_price": gain,
                     "text": f"One more {per} on {m['label'].lower()}{where} adds SAR {gain:,.2f}m of SVA"})
    rows.sort(key=lambda r: -r["shadow_price"])
    return rows[:cap]


def _soft_label(name: str) -> str:
    from backend.dealdesk import risk_appetite_view as rv
    return rv.limits()[name]["label"].replace(" (appetite)", " appetite").replace(" (policy)", " policy")


def _scope_name(space, m: dict[str, Any]) -> str:
    """A readable scope: the obligor's or group's name rather than its id."""
    if m["name"] == "single_name":
        return next((d["deal"]["name"] for d in space.deals if d["deal"]["obligor_id"] == m["scope"]), m["scope"])
    if m["name"] in ("group_connected", "group_large_exposure"):
        return next((d["deal"]["group_name"] for d in space.deals if d["deal"]["group_id"] == m["scope"]), m["scope"])
    return m["scope"]


def _reason(p, d, res_j, space, k, binding_txt: str) -> str:
    opts = d["options"]
    if res_j >= 0:
        o = opts[res_j]
        rr = f"RAROC {o['lifetime_raroc'] * 100:.1f}%, SVA SAR {o['sva']:,.2f}m for SAR {o['rwa']:,.0f}m RWA"
        if o["kind"] == "ask":
            return f"Clears the hurdle as asked: {rr}"
        if o["kind"] == "recommended":
            ch = _changes(o, p["ask"])
            return f"Recommended structure ({ch}): {rr}" if ch else f"Recommended structure: {rr}"
        larger = [x for x in opts if x["available"] and x["amount_sar_mn"] > o["amount_sar_mn"] + 1e-9]
        if not larger or o["sva"] >= max(x["sva"] for x in larger) - 1e-9:
            return f"Reduced to SAR {o['amount_sar_mn']:,.0f}m, where the deal adds the most value: {rr}"
        return f"Reduced to SAR {o['amount_sar_mn']:,.0f}m to fit {binding_txt or 'the limits'}: {rr}"
    av = [o for o in opts if o["available"]]
    if not av:
        br = sorted({b for o in opts for b in o["deal_hard_breaches"]})
        return "Breaches a deal-level hard limit in every structure: " + ", ".join(b.replace("_", " ") for b in br)
    from backend.dealdesk.pipeline_solver import min_sva
    if all(o["sva"] < min_sva() for o in av):
        best = max(av, key=lambda o: o["sva"])
        return f"No structure clears the hurdle with value to spare (best SVA SAR {best['sva']:,.2f}m)"
    best = max((o for o in av if o["sva"] >= min_sva()), key=lambda o: o["sva"])
    dens = best["sva"] / max(best["rwa"], 1e-6) * 100
    return f"Displaced by better uses of {binding_txt or 'the limits'}: SAR {dens:,.2f}m SVA per 100m RWA"


_RESULTS: dict[str, Any] = {}


def optimise(ids: list[str] | None = None, rwa_budget: float | None = None, el_budget: float | None = None,
             frontier: bool = True, gets_in: bool = True) -> dict[str, Any]:
    """The exact pipeline selection. Deterministic, so a result is cached on its inputs (deal keys, budgets, parameters)."""
    ps = _deals(ids)
    deals = [options(p) for p in ps]
    ck = hashlib.sha256(json.dumps([[d["key"] for d in deals], rwa_budget, el_budget, frontier, gets_in,
                                    params.versions(), _ra_digest()], sort_keys=True).encode()).hexdigest()
    if ck in _RESULTS:
        return copy.deepcopy(_RESULTS[ck])
    out = _optimise(ps, deals, rwa_budget, el_budget, frontier, gets_in)
    if len(_RESULTS) > 32:
        _RESULTS.clear()
    _RESULTS[ck] = copy.deepcopy(out)
    return out


def _ra_digest() -> str:
    return hashlib.sha256(json.dumps(params.table("risk_appetite"), sort_keys=True).encode()).hexdigest()[:16]


def _optimise(ps, deals, rwa_budget, el_budget, frontier, gets_in) -> dict[str, Any]:
    from backend.dealdesk import risk_appetite_view as rv
    import time as _t
    t0 = _t.time()
    space = rv.Space(deals, rwa_budget, el_budget)
    res = _solve(space)
    bind = _binding(space, res)
    bind_txt = " and ".join(b["label"].lower() + ("" if b["scope"] in ("new business", "book") else f" ({b['scope_name']})") for b in bind[:2])
    charged = sorted((x for x in res.soft if x["penalty"] > 1e-6), key=lambda x: -x["penalty"])
    soft_txt = " and ".join(_soft_label(x["name"]).lower() + ("" if x["scope"] in ("book", "new business") else f" ({x['scope']})")
                            for x in charged[:2])
    if not bind_txt and soft_txt:
        bind_txt = soft_txt
    sel = [deals[k]["options"][j] for k, j in enumerate(res.choice) if j >= 0]
    decisions = []
    for k, (p, d) in enumerate(zip(ps, deals)):
        j = res.choice[k]
        o = d["options"][j] if j >= 0 else None
        decisions.append({**row(p), "decision": "approve" if j >= 0 else "decline", "option": None if o is None else _opt_public(o, j),
                          "sva": None if o is None else o["sva"], "rwa": None if o is None else o["rwa"],
                          "reason": _reason(p, d, j, space, k, bind_txt), "options": [_opt_public(x, i) for i, x in enumerate(d["options"])],
                          "sva_per_100m_rwa": None if o is None else o["sva"] / max(o["rwa"], 1e-6) * 100})
    # what would get each declined deal in
    if gets_in:
        from backend.dealdesk.pipeline_solver import min_sva
        for k, dec in enumerate(decisions):
            if dec["decision"] == "approve":
                continue
            d = deals[k]
            av = [(j, o) for j, o in enumerate(d["options"]) if o["available"]]
            if not av:
                dec["gets_in"] = {"possible": False, "text": "Restructure to cure " + ", ".join(sorted({b.replace('_', ' ') for _, o in
                                                                                                    [(0, x) for x in d["options"]] for b in o["deal_hard_breaches"]}))}
                continue
            r2 = _solve(space, forced={k})
            jb, ob = max(av, key=lambda x: x[1]["sva"])
            if not r2.feasible:
                agg = res.agg + space.V[k][jb]
                dec["gets_in"] = {"possible": False, "violates": _violated(space, agg),
                                  "text": "Cannot fit with any selection: it breaches " + (", ".join(_violated(space, agg)) or "a hard limit")}
                continue
            jf = r2.choice[k]
            of = d["options"][jf]
            gap = max(res.objective - r2.objective, 0.0) + max(min_sva() - of["sva"], 0.0)
            per_bp = _sva_per_bp(ps[k], of)
            bps = None if per_bp is None else gap / per_bp
            out_ = [deals[i]["proposal_id"] for i, (a, b2) in enumerate(zip(res.choice, r2.choice)) if a >= 0 and b2 < 0]
            txt = f"Needs SAR {gap:,.2f}m more SVA" + (f" (about +{bps:,.0f} bps on {_margin_key(of).split('_')[0]})" if bps is not None else "")
            txt += f"; forced in as {of['label'].lower()} it displaces {', '.join(out_)}" if out_ else ""
            dec["gets_in"] = {"possible": True, "sva_gap": gap, "bps": bps, "price_lever": _margin_key(of), "displaces": out_,
                              "option": of["label"], "text": txt}
    # frontier: SVA against RWA consumed
    fr = []
    if frontier:
        i_r = next(i for i, m in enumerate(space.hard_meta) if m["name"] == "bu_rwa_budget")
        tot_rwa = sum(max([o["rwa"] for o in d["options"] if o["available"]] or [0.0]) for d in deals)
        grid = sorted({round(space.rwa_budget * f, 4) for f in FRONTIER_STEPS} | {round(tot_rwa, 4)})
        for bgt in grid:
            if abs(bgt - space.rwa_budget) < 1e-6:
                r2 = res
            else:
                b2 = space.b.copy()
                b2[i_r] = bgt
                r2 = _solve(space, b=b2)
            if not r2.feasible:
                continue
            fr.append({"rwa_budget": bgt, "rwa_used": float(r2.agg[space.idx["rwa"]]), "sva": r2.sva, "objective": r2.objective,
                       "selected": sum(1 for j in r2.choice if j >= 0), "chosen": abs(bgt - space.rwa_budget) < 1e-6})
    rows = space.rows(res.agg, sel)
    i = space.idx
    m = space.measures(res.agg)
    n_sel = len(sel)
    summ = {"deals": len(ps), "selected": n_sel, "sva": res.sva, "penalty": res.penalty, "objective": res.objective,
            "rwa_used": float(res.agg[i["rwa"]]), "rwa_budget": space.rwa_budget, "el_used": float(res.agg[i["el"]]),
            "el_budget": space.el_budget, "ead_new": float(res.agg[i["ead"]]),
            "ead_pipeline": sum(float(d["options"][0]["ead"]) for d in deals), "raroc_new": m["raroc"],
            "amount_selected": sum(o["amount_sar_mn"] for o in sel), "amount_pipeline": sum(row(p)["amount_sar_mn"] for p in ps)}
    headline = (f"Approve {n_sel} of {len(ps)} deals: SVA SAR {res.sva:,.1f}m, RWA SAR {summ['rwa_used']:,.0f}m of "
                f"{space.rwa_budget:,.0f}m budget" + (f"; binding: {bind_txt}" if bind_txt else ""))
    for x in charged:
        bind.append({"name": x["name"], "label": _soft_label(x["name"]), "scope": x["scope"], "scope_name": x["scope"],
                     "slack": None, "step": None, "per": None, "shadow_price": None, "soft": True, "charge": x["penalty"],
                     "text": _soft_label(x["name"]) + ("" if x["scope"] in ("book", "new business") else f" ({x['scope']})")
                             + f" is taken past its trigger: SAR {x['penalty']:,.2f}m appetite charge"})
    _texts(rows)
    return {"as_of": paths.AS_OF, "headline": headline, "summary": summ, "decisions": decisions, "limits": rows,
            "soft_breaches": res.soft, "binding": bind, "shadow_prices": [b for b in bind if not b.get("soft")], "frontier": fr,
            "solver": {"method": "exact branch-and-bound over deal options (Lagrangian and penalty bounds, hard-row feasibility cuts)",
                       "exact": res.exact, "nodes": res.nodes, "seconds": round(res.seconds, 3), "feasible": res.feasible,
                       "penalty_rate": rv.penalty_rate(), "seconds_total": round(_t.time() - t0, 2)},
            "basis": ("Options per deal are engine results (Deal Desk engine, parameters v1 and the PD model); the portfolio is the "
                      f"corporate book {paths.CORP_RELEASE} at {paths.AS_OF} plus the selection; limits from risk_appetite.json.")}


def pipeline_test(pid: str, terms: dict[str, Any] | None = None, ids: list[str] | None = None,
                  rwa_budget: float | None = None, el_budget: float | None = None) -> dict[str, Any]:
    """L5: re-solve the pipeline with this deal (on the structure picked in Optimise) forced in, and optional."""
    from backend.dealdesk import risk_appetite_view as rv
    p = get(pid)
    others = [x for x in _deals(ids) if x["proposal_id"] != pid]
    base_deals = [options(x) for x in others]
    if terms is None:
        rec = next((o for o in options(p)["options"] if o["kind"] == "recommended"), None)
        terms = rec["terms"] if rec else None
        label = "Recommended structure" if rec else "As asked"
    else:
        label = "Structure picked in Optimise"
    o = _option(p, "picked", label, terms)
    ob = p["obligor"]
    me = {"proposal_id": pid, "key": "test", "options": [o], "deal": options(p)["deal"]}
    deals = base_deals + [me]
    space = rv.Space(deals, rwa_budget, el_budget)
    k = len(deals) - 1
    base_space = rv.Space(base_deals, rwa_budget, el_budget)
    base = _solve(base_space)
    opt = _solve(space, free={k})
    forced = _solve(space, forced={k}) if o["available"] else None
    makes_cut = opt.feasible and opt.choice[k] >= 0
    # rank by SVA per unit RWA among the deals the optimum approves (with this one)
    sel_ref = forced if (forced is not None and forced.feasible) else opt
    dens = [(deals[i]["proposal_id"], deals[i]["options"][j]["sva"] / max(deals[i]["options"][j]["rwa"], 1e-6))
            for i, j in enumerate(sel_ref.choice) if j >= 0]
    mine = o["sva"] / max(o["rwa"], 1e-6)
    if all(d[0] != pid for d in dens):
        dens.append((pid, mine))
    dens.sort(key=lambda x: -x[1])
    rank = next(i for i, d in enumerate(dens) if d[0] == pid) + 1
    displaced, resized = [], []
    if forced is not None and forced.feasible:
        for i, (a, b) in enumerate(zip(base.choice, forced.choice[:-1])):
            if a >= 0 and b < 0:
                displaced.append({"proposal_id": deals[i]["proposal_id"], "obligor": deals[i]["deal"]["name"],
                                  "sva": deals[i]["options"][a]["sva"], "rwa": deals[i]["options"][a]["rwa"]})
            elif a >= 0 and b >= 0 and a != b:
                resized.append({"proposal_id": deals[i]["proposal_id"], "obligor": deals[i]["deal"]["name"],
                                "from": deals[i]["options"][a]["label"], "to": deals[i]["options"][b]["label"]})
    # marginal effect on each limit: the base optimum against the same selection plus this deal
    base_sel = [base_deals[i]["options"][j] for i, j in enumerate(base.choice) if j >= 0]
    agg_b = np.zeros(space.n)
    for i, j in enumerate(base.choice):
        if j >= 0:
            agg_b += space.V[i][j]
    agg_with = agg_b + space.V[k][0]
    r0 = {r["name"] + "|" + r["scope"]: r for r in space.rows(agg_b, base_sel)}
    r1 = space.rows(agg_with, base_sel + [o])
    eff = []
    for r in r1:
        a = r0.get(r["name"] + "|" + r["scope"])
        if a is None or r["direction"] == "deal":
            continue
        dv = None if r["after"] is None or a["after"] is None else float(r["after"]) - float(a["after"])
        eff.append({**r, "before": a["after"], "status_before": a["status"], "delta": dv})
    # the limit that binds first: smallest multiple of this deal that the remaining headroom holds
    u = space.H @ agg_b
    hv = space.H @ space.V[k][0]
    first = None
    for i, m in enumerate(space.hard_meta):
        if hv[i] > 1e-9:
            times = (space.b[i] - u[i]) / hv[i]
            if first is None or times < first["times"]:
                first = {"name": m["name"], "label": m["label"], "scope": _scope_name(space, m), "times": float(times),
                         "headroom": float(space.b[i] - u[i]), "kind": "hard"}
    for r in eff:
        if r["kind"] == "soft" and r["delta"] and r["delta"] > 0 and r["direction"] == "max" and r["limit"] is not None and r["before"] is not None:
            times = (float(r["limit"]) - float(r["before"])) / r["delta"]
            if times >= 0 and (first is None or times < first["times"]):
                first = {"name": r["name"], "label": r["label"], "scope": r["scope"], "times": float(times),
                         "headroom": float(r["limit"]) - float(r["before"]), "kind": "soft"}
    if first is not None:
        sc = "" if first["scope"] in ("book", "new business") else f" ({first['scope']})"
        first["text"] = (f"{first['label']}{sc} binds first: headroom for {first['times']:,.1f}x this deal"
                         if first["times"] >= 0 else f"{first['label']}{sc} is already past its limit")
    rank_st = {"red": 0, "amber": 1, "green": 2, "n/a": 3}

    def moved(r: dict[str, Any]) -> float:
        lim = r["limit"] if isinstance(r["limit"], (int, float)) and r["limit"] else 1.0
        return -abs(r["delta"] or 0.0) / abs(float(lim))
    eff.sort(key=lambda r: (rank_st.get(r["status"], 3), moved(r)))
    _texts(eff)
    gain = None if forced is None or not forced.feasible else forced.objective - base.objective
    if not o["available"]:
        verdict = "Cannot be approved: it breaches " + ", ".join(b.replace("_", " ") for b in o["deal_hard_breaches"])
    elif forced is None or not forced.feasible:
        verdict = "Does not fit: forcing it in breaches " + ", ".join(_violated(space, agg_with) or ["a hard limit"])
    elif makes_cut:
        verdict = f"Makes the cut: ranks {rank} of {len(dens)} by SVA per unit of RWA and adds SAR {gain:,.2f}m to the pipeline's value"
    else:
        verdict = (f"Does not make the cut: forced in, the pipeline's value falls by SAR {-gain:,.2f}m"
                   + (f" and it displaces {', '.join(d['proposal_id'] for d in displaced)}" if displaced else ""))
    return {"proposal_id": pid, "obligor": ob["name"], "structure": {**_opt_public(o, 0), "terms": o["terms"]},
            "makes_cut": bool(makes_cut), "fits": bool(forced is not None and forced.feasible), "verdict": verdict,
            "rank": rank, "ranked": len(dens), "of": len(dens), "sva_per_100m_rwa": mine * 100,
            "displaced": displaced, "resized": resized, "value_change": gain,
            "pipeline": {"deals": len(others), "base_selected": sum(1 for j in base.choice if j >= 0),
                         "base_sva": base.sva, "base_objective": base.objective,
                         "with_selected": None if forced is None or not forced.feasible else sum(1 for j in forced.choice if j >= 0),
                         "with_objective": None if forced is None or not forced.feasible else forced.objective,
                         "optional_objective": opt.objective, "rwa_budget": space.rwa_budget, "el_budget": space.el_budget},
            "limits": eff, "binds_first": first,
            "solver": {"exact": base.exact and opt.exact and (forced is None or forced.exact),
                       "nodes": base.nodes + opt.nodes + (forced.nodes if forced else 0)},
            "basis": "Engine result for this structure; the pending pipeline re-solved exactly with the deal forced in and optional."}


def fmt_value(v: Any, unit: str) -> str:
    """A limit value in its unit, for the thread (the UI formats its own)."""
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    if unit == "share":
        return f"{v * 100:.2f}%" if abs(v) < 0.1 else f"{v * 100:.1f}%"
    if unit == "index":
        return f"{v:.3f}"
    if unit == "bps":
        return f"{v:.1f} bps"
    if unit == "SAR m":
        return f"SAR {v:,.1f}m"
    if unit == "x":
        return f"{v:.2f}x"
    return f"{v:g}"


def _texts(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        r["before_text"] = fmt_value(r.get("before"), r["unit"])
        r["after_text"] = fmt_value(r.get("after"), r["unit"])


def listing() -> dict[str, Any]:
    from backend.dealdesk import risk_appetite_view as rv
    L = rv.limits()
    rows = [row(p) for p in pending()]
    return {"as_of": paths.AS_OF, "deals": rows, "count": len(rows),
            "by_source": {s: sum(1 for r in rows if r["source"] == s) for s in ("Deal Desk", "Uploaded", "Reference deal", "Pipeline set")},
            "budgets": {"rwa": float(L["bu_rwa_budget"]["headroom_sar_mn"]), "el": float(L["bu_el_budget"]["headroom_sar_mn"]),
                        "rwa_basis": L["bu_rwa_budget"]["basis"], "el_basis": L["bu_el_budget"]["basis"]},
            "amount_sar_mn": sum(r["amount_sar_mn"] for r in rows)}
