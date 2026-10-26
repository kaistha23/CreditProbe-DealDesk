"""R12 Session E: the fictional demo deals (PLAN_R12 §4, N7). Every name here is invented.

    R12-TWA  Twin A  Al Sahel Building Materials Group — trading group renewal: related-party receivables, a qualified
                     audit, an unmet routing undertaking and an insider-linked guarantor.
    R12-TWB  Twin B  Gulf Meridian Contracting — new project limit for Saadiyat Crest Developments: financed-project
                     delays, backlog concentrated in two employers, high branch-level leverage, a group cap increase.
    R12-SYN  Najd Petrochem Syndicate Participation (participant, 10% of SAR 3.0bn)
    R12-ESC  Marina Vista Off-plan Escrow (escrow-account development loan)
    R12-SME1..3  three SME fast-track applications (approve, refer, decline)

`rows()` returns {relation: [row, ...]} for every R12 relation these deals feed. Amounts are SAR million.
Dates sit before the demo's today (2026-10-18); the book quarter is 2026Q2.
"""
from __future__ import annotations

import json
import math
from typing import Any

from backend.dealdesk.seed import MASTER_SCALE

R: dict[str, list[dict[str, Any]]] = {}


def add(rel: str, **row: Any) -> dict[str, Any]:
    R.setdefault(rel, []).append(row)
    return row


def _months(start: str, n: int) -> list[str]:
    y, m = map(int, start.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def proposal(pid: str, *, name: str, oid: str, sector: str, sub: str, rating: str, group_id: str, group_name: str,
             existing: bool, region: str, sector_code: str, rm: str, received: str, purpose: str, case: str,
             years: list[tuple], ask: dict[str, Any], collateral: list[dict] | None = None, guarantees: list[dict] | None = None,
             existing_exposure: float = 0.0, sme: bool = False, status: str = "in_review", ancillary: dict | None = None,
             covenants: list[dict] | None = None, connected: list[str] | None = None) -> dict[str, Any]:
    """An engine-ready proposal record in the proposals.json shape."""
    base = {"facility_type": "term_loan", "structure": "murabaha", "currency": "SAR", "amount": 100, "tenor_years": 3,
            "grace_years": 0, "amortisation": "equal", "balloon_pct": 0, "margin_bps": 225, "upfront_fee_bps": 50,
            "commitment_fee_bps": 0, "commission_bps": 0, "utilisation_pct": 100, "funded_share_pct": 100,
            "unfunded_type": "performance_lg", "cash_margin_pct": 0, "collateral_ids": [c["collateral_id"] for c in (collateral or []) if c.get("pledged_in_ask")],
            "guarantee_id": None, "guarantee_coverage_pct": 0, "covenant_package": "standard"}
    base.update(ask)
    fin = [{"year": y, "kind": k, "revenue": rv, "ebitda": eb, "total_debt": td, "debt_service": ds, "net_worth": nw,
            "current_ratio": cr, "source": src} for (y, k, rv, eb, td, ds, nw, cr, src) in years]
    return {"proposal_id": pid, "status": status, "rm": rm, "business_unit": "Corporate Banking" if not sme else "SME Banking",
            "received": received, "purpose": purpose,
            "obligor": {"existing": existing, "external_rating": None, "obligor_id": oid, "name": name, "cr_number": "",
                        "sector": sector, "sub_sector": sub, "segment": sector, "region": region, "internal_rating": rating,
                        "gre": False, "sme": sme, "simah_flag": "clear", "gov_linked": False, "group_id": group_id,
                        "group_name": group_name, "connected_parties": connected or [], "real_estate_finance": False,
                        "sector_code": sector_code, "pd_master_scale": MASTER_SCALE[rating],
                        "existing_exposure_sar_mn": existing_exposure, "existing_facilities": []},
            "financials": {"currency": "SAR", "unit": "SAR m", "years": fin},
            "ask": base,
            "security": {"collateral": collateral or [], "guarantees": guarantees or [], "covenant_package": base["covenant_package"],
                         "covenants": covenants or [{"type": "DSCR", "threshold": 1.2}, {"type": "Net debt / EBITDA", "threshold": 4.0}]},
            "business_case": {"ancillary_income_sar_mn_pa": ancillary or {"cash_management": 0.4, "payroll": 0.2, "fx": 0.1, "trade": 0.6},
                              "currency": "SAR"},
            "memo": "", "case": case, "deal_currency": "SAR", "source": "r12_demo"}


DEALS: dict[str, dict[str, Any]] = {}   # pid -> {"proposal": ..., "deal": dd_deal fields}


def deal(pid: str, prop: dict[str, Any], **header: Any) -> None:
    DEALS[pid] = {"proposal": prop, "deal": header}


def entity(eid: str, name: str, group_id: str, group_name: str, role: str, **kw: Any) -> None:
    add("b360_entity", entity_id=eid, entity_name=name, group_id=group_id, group_name=group_name, role=role, **kw)


def holder(eid: str, hid: str, name: str, kind: str, nat: str, pct: float, ubo: int, birth: int | None = None,
           eff: float | None = None, since: str = "", nominee: int = 0) -> None:
    add("b360_shareholder", entity_id=eid, holder_id=hid, holder_name=name, holder_kind=kind, nationality=nat, birth_year=birth,
        share_pct=pct, ubo_flag=ubo, ubo_effective_pct=eff, nominee_flag=nominee, since=since)
    add("b360_edge", edge_id=f"OWN-{hid}-{eid}", rel_type="owns", source_id=hid, target_id=eid,
        group_id=eid.split("-")[1], ownership_pct=pct, detail=f"{name} holds {pct:g}%")


# ====================================================================================== Twin A
def twin_a() -> None:
    pid, g, gn = "R12-TWA", "XG-TWA", "Al Sahel Building Materials Group"
    S, H, RM_, LG, ST = "XE-TWA-01", "XE-TWA-00", "XE-TWA-02", "XE-TWA-03", "XE-TWA-04"
    entity(H, "Al Sahel Holding Company", g, gn, "parent", parent_entity_id="", country="Saudi Arabia", legal_status="Closed JSC",
           activity="Holding of trading and industrial companies", licence_no="CR-7001-4482", licence_expiry="2027-05-31",
           incorporation_date="2006-03-12", incorporation_place="Dammam", staff_count=12, listed_flag=0, credit_status="performing")
    entity(S, "Al Sahel Building Materials Trading LLC", g, gn, "subject", parent_entity_id=H, country="Saudi Arabia", legal_status="LLC",
           activity="Wholesale trading of steel, cement, timber and building materials", licence_no="CR-2050-1177",
           licence_expiry="2027-02-28", incorporation_date="2008-09-01", incorporation_place="Dammam", staff_count=214, listed_flag=0,
           credit_status="performing")
    entity(RM_, "Al Sahel Ready-Mix Concrete Factory", g, gn, "sister", parent_entity_id=H, country="Saudi Arabia", legal_status="LLC",
           activity="Manufacture of ready-mix concrete and blocks", licence_no="CR-2050-3391", licence_expiry="2026-12-31",
           incorporation_date="2013-04-20", incorporation_place="Jubail", staff_count=167, listed_flag=0, credit_status="performing")
    entity(LG, "Al Sahel Logistics Services", g, gn, "sister", parent_entity_id=H, country="Saudi Arabia", legal_status="LLC",
           activity="Road freight and warehousing", licence_no="CR-2050-5520", licence_expiry="2026-09-30", incorporation_date="2016-01-10",
           incorporation_place="Dammam", staff_count=96, listed_flag=0, credit_status="classified_doubtful",
           credit_status_note="Classified doubtful at Peninsula Trade Bank since 2025-11; two court cases filed by lenders (SAR 41.0m). Licence expired 2026-09-30.")
    entity(ST, "Sahel Steel Trading Est.", g, gn, "guarantor", parent_entity_id="", country="Saudi Arabia", legal_status="Sole establishment",
           activity="Trading of rebar and structural steel", licence_no="CR-2050-6012", licence_expiry="2027-08-31",
           incorporation_date="2011-06-05", incorporation_place="Khobar", staff_count=38, listed_flag=0, credit_status="performing")
    F, Sd, Mo, HK = "XP-TWA-01", "XP-TWA-02", "XP-TWA-03", "XP-TWA-04"
    holder(H, F, "Fahad Nasser Al-Sahili", "person", "Saudi", 55.0, 1, 1961, 59.5, "2006-03-12")
    holder(H, Sd, "Saeed Nasser Al-Sahili", "person", "Saudi", 25.0, 1, 1966, 22.5, "2006-03-12")
    holder(H, Mo, "Mona Fahad Al-Sahili", "person", "Saudi", 20.0, 0, 1990, 18.0, "2025-09-14")
    holder(S, H, "Al Sahel Holding Company", "company", "Saudi Arabia", 90.0, 0, None, None, "2008-09-01")
    holder(S, F, "Fahad Nasser Al-Sahili", "person", "Saudi", 10.0, 1, 1961, None, "2008-09-01")
    holder(RM_, H, "Al Sahel Holding Company", "company", "Saudi Arabia", 100.0, 0, None, None, "2013-04-20")
    holder(LG, H, "Al Sahel Holding Company", "company", "Saudi Arabia", 100.0, 0, None, None, "2016-01-10")
    holder(ST, F, "Fahad Nasser Al-Sahili", "person", "Saudi", 80.0, 1, 1961, None, "2011-06-05")
    holder(ST, HK, "Huda Sami Kettani", "person", "Saudi", 20.0, 0, 1979, None, "2019-02-01")
    add("b360_ownership_change", change_id="OC-TWA-1", entity_id=H, change_date="2025-09-14", holder_id=Sd, holder_name="Saeed Nasser Al-Sahili",
        from_pct=45.0, to_pct=25.0, kind="transfer", disclosed_flag=0,
        note="20% transferred to Mona Fahad Al-Sahili; not disclosed in the proposal, seen in the amended MoA dated 2025-09-14.")
    add("b360_ownership_change", change_id="OC-TWA-2", entity_id=H, change_date="2025-09-14", holder_id=Mo, holder_name="Mona Fahad Al-Sahili",
        from_pct=0.0, to_pct=20.0, kind="entry", disclosed_flag=0, note="New shareholder of the holding company.")
    dirs = [{"entity_id": H, "entity_name": "Al Sahel Holding Company", "role": "chairman"},
            {"entity_id": RM_, "entity_name": "Al Sahel Ready-Mix Concrete Factory", "role": "director"},
            {"entity_id": LG, "entity_name": "Al Sahel Logistics Services", "role": "director"},
            {"entity_id": ST, "entity_name": "Sahel Steel Trading Est.", "role": "owner_manager"}]
    add("b360_board", entity_id=S, person_id=F, person_name="Fahad Nasser Al-Sahili", role="chairman", nationality="Saudi",
        appointed="2008-09-01", key_person_flag=1, other_directorships=dirs, linked_borrower_ids="")
    add("b360_board", entity_id=S, person_id="XP-TWA-05", person_name="Rami Adel Haddara", role="gm", nationality="Jordanian",
        appointed="2017-01-15", key_person_flag=1, other_directorships=[], linked_borrower_ids="")
    add("b360_board", entity_id=S, person_id="XP-TWA-06", person_name="Yousef Karim Al-Nairi", role="cfo", nationality="Egyptian",
        appointed="2021-06-01", key_person_flag=0, other_directorships=[], linked_borrower_ids="")
    add("b360_board", entity_id=LG, person_id=Sd, person_name="Saeed Nasser Al-Sahili", role="gm", nationality="Saudi",
        appointed="2016-01-10", key_person_flag=1, other_directorships=[{"entity_id": H, "entity_name": "Al Sahel Holding Company", "role": "director"}],
        linked_borrower_ids="")
    add("b360_insider_link", link_id="IL-TWA-1", entity_id=ST, person_id="XP-BNK-0417", person_name="Omar Khalil Kettani",
        link_kind="staff_relative", bank_staff_id="S-20417", staff_role="Senior Relationship Manager, Trade Finance",
        relationship="spouse of the 20% shareholder Huda Sami Kettani", share_pct=20.0, disclosed_flag=0,
        detected_by="Staff register match on the guarantor's shareholder (surname and family book)",
        note="The guarantor of the renewal is 20% owned by the spouse of a bank staff member; not disclosed in the proposal.")
    for e in (RM_, LG):
        add("b360_edge", edge_id=f"SIS-{S}-{e}", rel_type="related_party", source_id=S, target_id=e, group_id="TWA",
            detail="Sister company under Al Sahel Holding Company")
    add("b360_edge", edge_id=f"SUP-{S}-{RM_}", rel_type="supplies", source_id=S, target_id=RM_, group_id="TWA", annual_value_mn=96.0,
        detail="Cement and aggregates sold to the ready-mix sister (14% of FY2025 revenue)")
    add("b360_edge", edge_id=f"GUA-{ST}-{S}", rel_type="guarantees", source_id=ST, target_id=S, group_id="TWA", amount_mn=180.0,
        detail="Corporate guarantee for the full limits")
    add("b360_edge", edge_id=f"GUA-{F}-{S}", rel_type="guarantees", source_id=F, target_id=S, group_id="TWA", amount_mn=180.0,
        detail="Personal guarantee of the UBO")
    add("b360_edge", edge_id=f"DIR-{F}-{LG}", rel_type="common_director", source_id=F, target_id=LG, group_id="TWA",
        detail="UBO sits on the board of the classified sister")

    years = [(2023, "actual", 612.0, 50.2, 118.0, 26.0, 171.0, 1.46, "Audited financial statements (Qarar Audit, clean)"),
             (2024, "actual", 655.0, 49.6, 131.0, 27.0, 180.0, 1.41, "Audited financial statements (Qarar Audit, clean)"),
             (2025, "actual", 702.0, 48.0, 140.0, 28.0, 187.0, 1.38, "Audited financial statements (Mizan & Partners, qualified)"),
             (2026, "projection", 745.0, 52.0, 136.0, 27.0, 199.0, 1.33, "Management projections as per business"),
             (2027, "projection", 790.0, 56.0, 130.0, 26.0, 213.0, 1.35, "Management projections as per business"),
             (2028, "projection", 838.0, 60.0, 124.0, 25.0, 229.0, 1.37, "Management projections as per business")]
    coll = [{"collateral_id": "C1", "type": "receivables", "value": 120.0, "currency": "SAR", "valuation_date": "2026-06-30", "pledged_in_ask": True}]
    guar = [{"guarantee_id": "G1", "type": "corporate", "guarantor": "Sahel Steel Trading Est.", "guarantor_rating": "BB-", "coverage_pct": 100,
             "offered_in_ask": True},
            {"guarantee_id": "G2", "type": "personal", "guarantor": "Fahad Nasser Al-Sahili", "guarantor_rating": "BB", "coverage_pct": 100,
             "offered_in_ask": True}]
    prop = proposal(pid, name="Al Sahel Building Materials Trading LLC", oid=S, sector="Wholesale Trade", sub="Building Materials",
                    rating="BB", group_id=g, group_name=gn, existing=True, region="Eastern Province", sector_code="G4663",
                    rm="Tamer Al-Jaafari", received="2026-10-01", case="renewal",
                    purpose="Annual renewal of the trade and working-capital limits of the building-materials trading arm",
                    years=years, existing_exposure=178.0, collateral=coll, guarantees=guar,
                    ask={"facility_type": "revolver", "structure": "murabaha", "amount": 170, "tenor_years": 1, "margin_bps": 225,
                         "upfront_fee_bps": 25, "funded_share_pct": 30, "unfunded_type": "performance_lg", "utilisation_pct": 75,
                         "amortisation": "bullet", "guarantee_id": "G1", "guarantee_coverage_pct": 100, "commission_bps": 100})
    deal(pid, prop, product="corporate", deal_name="Al Sahel Building Materials Group — renewal", case_type="renewal",
         workflow_state="queries", credit_analyst="Dana Al-Khatib", branch="Eastern Province Corporate Centre",
         committee_date="2026-10-29", approval_authority="Credit Committee level 2", existing_limits_mn=180.0, proposed_limits_mn=180.0,
         group_exposure_mn=236.0, group_cap_existing_mn=250.0, group_cap_proposed_mn=250.0, rating_existing="BB+", rating_proposed="BB",
         cif="CIF-0048213", group_no="GRP-0911", account_opened_date="2009-02-15", related_party_flag=1, related_party_cif="CIF-0071902",
         purpose_code="P21 Trade finance", industry_code="G4663", collateral_code="RCV / CG / PG", review_date="2027-10-31",
         ao="Tamer Al-Jaafari", ro="Lama Fikri")

    # facility tree
    L = [("L0", "", 0, "Total limits", "", 1, 180.0, 178.0, 180.0, None, None, "", None, None, "", "", ""),
         ("L1", "L0", 1, "Trade umbrella limit (interchangeable)", "", 0, 150.0, 151.0, 150.0, None, None, "", None, None, "12 months", "", "Interchangeable between the sub-limits within SAR 150.0m"),
         ("L1.1", "L1", 2, "LC sight / usance (up to 180 days)", "LC_USANCE", 0, 150.0, 62.0, 150.0, 10.0, 0.75, "", None, None, "Validity up to 12 months; usance up to 180 days", "Settled by LCM or own funds", ""),
         ("L1.2", "L1", 2, "LC maturity / trust receipts (sub-limit)", "LCM", 1, 90.0, 71.0, 90.0, 0.0, None, "3M SAIBOR", 2.25, 5.50, "Up to 120 days per drawing", "Bullet per drawing", "Against LC documents only; no inter-group use"),
         ("L1.3", "L1", 2, "Performance and advance-payment LGs (sub-limit)", "LG", 0, 40.0, 18.0, 40.0, 10.0, 1.00, "", None, None, "Up to 24 months", "", "Single LG cap SAR 10.0m"),
         ("L2", "L0", 1, "Overdraft", "OD", 1, 30.0, 27.0, 20.0, 0.0, None, "3M SAIBOR", 2.50, 6.00, "12 months, on demand", "On demand", "Reduced from SAR 30.0m to SAR 20.0m"),
         ("L3", "L0", 1, "One-off LG against 100% cash margin", "LG_CASH", 0, 0.0, 0.0, 10.0, 100.0, 0.50, "", None, None, "One-off, 12 months", "", "New")]
    for i, (lid, par, lev, nm, code, fund, ex, out, pr, cm, com, bm, sp, fl, ten, rep, part) in enumerate(L):
        add("dd_facility_limit", proposal_id=pid, limit_id=lid, parent_limit_id=par, level=lev, seq=i + 1, limit_name=nm, product_code=code,
            funded_flag=fund, currency="SAR", existing_mn=ex, outstanding_mn=out if lid != "L1" else 151.0, proposed_mn=pr,
            cash_margin_pct=cm, commission_pct_pa=com, benchmark=bm, spread_pct=sp, floor_pct=fl, tenor_text=ten, repayment_text=rep,
            project_id="", interchangeable_flag=1 if par == "L1" else 0, particulars=part)
    sec = [("S1", "ALL", "personal_guarantee", "Fahad Nasser Al-Sahili", F, 180.0, 240.0, "2025-03-31", "perfected", "", "2025-08-12", 1, "Net-worth statement older than 12 months"),
           ("S2", "ALL", "corporate_guarantee", "Sahel Steel Trading Est.", ST, 180.0, 58.0, "2025-12-31", "pending", "2026-12-31", "", 1, "Guarantor 20% owned by the spouse of a bank staff member (b360_insider_link IL-TWA-1); legal opinion not yet obtained"),
           ("S3", "ALL", "corporate_guarantee", "Al Sahel Holding Company", H, 180.0, 312.0, "2025-12-31", "not_perfected", "2026-12-31", "", 0, "New: proposed by credit"),
           ("S4", "ALL", "security_cheque", "Al Sahel Building Materials Trading LLC", S, 180.0, None, "", "perfected", "", "", 1, "Undated security cheque"),
           ("S5", "L1", "assignment_receivables", "Al Sahel Building Materials Trading LLC", S, 120.0, None, "", "pending", "2026-12-31", "", 1, "Assignment of receivables of the top 10 debtors; notices not served"),
           ("S6", "L1", "assignment_insurance", "Al Sahel Building Materials Trading LLC", S, 146.0, None, "", "perfected", "", "", 1, "Inventory insurance assigned; policy expires 2027-03-31"),
           ("S7", "ALL", "subordination", "Al Sahel Holding Company", H, 31.0, None, "", "perfected", "", "2025-08-12", 1, "Subordination of shareholder current account SAR 31.0m"),
           ("S8", "L3", "cash_margin", "Al Sahel Building Materials Trading LLC", S, 10.0, None, "", "not_applicable", "", "", 0, "100% cash margin under lien")]
    for sid, lim, kind, prov, pe, amt, nw, nwd, perf, dl, lo, ex, note in sec:
        add("dd_security", proposal_id=pid, security_id=sid, limit_id=lim, kind=kind, provider=prov, provider_entity_id=pe, amount_mn=amt,
            currency="SAR", net_worth_mn=nw, net_worth_statement_date=nwd, perfection_status=perf, perfection_deadline=dl,
            legal_opinion_date=lo, valuation_date="", value_mn=None, insurance_expiry="2027-03-31" if kind == "assignment_insurance" else "",
            pari_passu_flag=0, existing_flag=ex, note=note)
    tnc = [("L1", "utilisation", "LCs to be opened only for the import of building materials for the company's own trading; no inter-group or related-party beneficiaries.", "complied"),
           ("L1", "settlement", "LCM drawings settled first from the proceeds of the goods financed; maximum 120 days per drawing.", "complied"),
           ("L1", "cap", "Single LG not to exceed SAR 10.0m; total LG outstanding not to exceed SAR 40.0m at any time.", "complied"),
           ("L2", "purpose", "Overdraft for working capital only; no payments to related parties from the overdraft account.", "not_complied"),
           ("ALL", "reporting", "Audited financial statements within 120 days of year end; interim management accounts within 60 days of each half year.", "not_complied"),
           ("ALL", "routing", "Route business through the bank of at least 2 times the total limits per year (SAR 360.0m).", "not_complied"),
           ("ALL", "auditor", "Any change of auditor requires the bank's prior consent; the auditor must be on the bank's approved panel.", "not_complied"),
           ("ALL", "existing_condition", "Subordinate the shareholder current account of SAR 31.0m to the bank's facilities.", "complied"),
           ("ALL", "cover_ratio", "Assigned receivables aged below 120 days to cover at least 100% of LCM and overdraft outstanding.", "new")]
    seqs: dict[str, int] = {}
    for i, (lim, cat, txt, st) in enumerate(tnc):
        seqs[lim] = seqs.get(lim, 0) + 1
        add("dd_tnc", proposal_id=pid, tnc_id=f"T{i + 1}", limit_id=lim, seq=seqs[lim], category=cat, text=txt, existing_status=st)
    for eid, nm, fe, te, fp, tp, out in [(S, "Al Sahel Building Materials Trading LLC", 120.0, 180.0, 110.0, 180.0, 178.0),
                                         (RM_, "Al Sahel Ready-Mix Concrete Factory", 35.0, 56.0, 35.0, 56.0, 41.0),
                                         (LG, "Al Sahel Logistics Services", 0.0, 0.0, 0.0, 0.0, 0.0)]:
        add("dd_group_exposure", proposal_id=pid, group_id=g, entity_id=eid, entity_name=nm, funded_existing_mn=fe, total_existing_mn=te,
            funded_proposed_mn=fp, total_proposed_mn=tp, outstanding_mn=out)
    for rid, kind, no, dt, auth, amt, cap, txt in [
            ("R1", "committee_decision", "CC-2025-118", "2025-08-20", "Credit Committee level 2", 180.0, 250.0, "Renewal approved at SAR 180.0m with a routing undertaking of 2x limits and the subordination of the shareholder account."),
            ("R2", "limit_history", "CC-2024-097", "2024-08-14", "Credit Committee level 2", 165.0, 230.0, "Limits raised from SAR 140.0m to SAR 165.0m."),
            ("R3", "limit_history", "CC-2023-071", "2023-07-30", "Credit Committee level 3", 140.0, 200.0, "Renewal at SAR 140.0m."),
            ("R4", "credit_file_request", "CFR-2026-0412", "2026-08-24", "", None, None, "Credit file requested from business: audited FS FY2025, interim 6M2026, bureau reports, other-bank FALs."),
            ("R5", "email", "EM-2026-1903", "2026-10-08", "", None, None, "Business conveys that the routing shortfall is due to the slowdown in government projects; no plan provided.")]:
        add("dd_reference", proposal_id=pid, ref_id=rid, kind=kind, ref_no=no, ref_date=dt, authority=auth, amount_mn=amt, group_cap_mn=cap, text=txt)

    # financials detail: standalone FY2023-25 audited + 6M2026 interim; combined FY2024-25
    fd = [("FY2023", 2023, "audited", "2023-12-31", 12, "Qarar Audit", "listed", "clean", "",
           612.0, 79.6, 41.0, 22.1, 50.2, 11.8, 498.0, 431.0, 18.0, 236.0, 0.0, 0.0, 131.0, 46.0, 296.0, 7.0, 9.0, 31.0, 22.0, 108.0, 10.0, 327.0, 171.0, 84.0, 21.0, 128,
           150.0, 48.0, 27.0, 11.0, 13.0, 22.0, 39.0),
          ("FY2024", 2024, "audited", "2024-12-31", 12, "Qarar Audit", "listed", "clean", "",
           655.0, 81.9, 40.2, 20.4, 49.6, 13.4, 541.0, 470.0, 15.0, 252.0, 0.0, 0.0, 139.0, 64.0, 334.0, 8.0, 11.0, 31.0, 24.0, 120.0, 11.0, 361.0, 180.0, 91.0, 9.0, 136,
           152.0, 54.0, 32.0, 14.0, 13.0, 22.0, 40.0),
          ("FY2025", 2025, "audited", "2025-12-31", 12, "Mizan & Partners Chartered Accountants", "unlisted", "qualified",
           "Recoverability of SAR 84.0m due from Al Sahel Logistics Services (a sister company classified doubtful by another bank and under litigation) could not be confirmed; no provision was made.",
           702.0, 84.2, 38.6, 17.9, 48.0, 15.9, 587.0, 512.0, 12.0, 270.0, 0.0, 0.0, 146.0, 84.0, 371.0, 9.0, 14.0, 31.0, 26.0, 128.0, 12.0, 400.0, 187.0, 98.0, -6.0, 149,
           151.0, 62.0, 38.0, 19.0, 14.0, 23.0, 41.0),
          ("6M2026", 2026, "interim", "2026-06-30", 6, "", "", "unaudited", "Management accounts, not reviewed by the auditor.",
           338.0, 39.0, 17.1, 7.6, 22.4, 8.4, 611.0, 536.0, 9.0, 281.0, 0.0, 0.0, 149.0, 97.0, 393.0, 10.0, 14.0, 31.0, 26.0, 139.0, 11.0, 417.0, 194.0, 104.0, -4.0, 157,
           146.0, 66.0, 44.0, 25.0, 15.0, 25.0, 43.0)]
    cols = ("revenue_mn", "gross_profit_mn", "operating_profit_mn", "net_profit_mn", "ebitda_mn", "finance_cost_mn", "total_assets_mn",
            "current_assets_mn", "cash_mn", "receivables_mn", "retention_receivables_mn", "contract_assets_mn", "inventory_mn",
            "due_from_related_mn", "current_liabilities_mn", "due_to_related_mn", "intangibles_mn", "shareholder_accounts_mn",
            "noncore_investments_mn", "bank_debt_st_mn", "bank_debt_lt_mn", "total_liabilities_mn", "net_worth_mn",
            "contingent_liabilities_mn", "operating_cash_flow_mn", "cash_cycle_days", "ageing_0_90_mn", "ageing_91_180_mn",
            "ageing_181_365_mn", "ageing_over_365_mn", "top1_receivable_pct", "top2_receivable_pct", "top5_receivable_pct")
    for lab, yr, kind, end, mo, aud, panel, op, basis, *vals in fd:
        add("dd_financials_detail", proposal_id=pid, entity_id=S, entity_name="Al Sahel Building Materials Trading LLC", entity_scope="standalone",
            period_label=lab, year=yr, period_kind=kind, period_end=end, months=mo, currency="SAR", auditor=aud, auditor_panel=panel,
            opinion=op, qualification_basis=basis, backlog_mn=None, staff_count=214,
            source="Audited financial statements" if kind == "audited" else "Interim management accounts as per business",
            **dict(zip(cols, vals)))
    for lab, yr, rev, gp, op_, np_, eb, ta, ca, rcv, inv, dfr, cl, td, nw in [
            ("FY2024", 2024, 846.0, 118.4, 52.1, 24.8, 70.2, 788.0, 602.0, 301.0, 171.0, 18.0, 455.0, 512.0, 276.0),
            ("FY2025", 2025, 905.0, 121.3, 47.9, 18.6, 68.8, 851.0, 655.0, 324.0, 180.0, 21.0, 492.0, 566.0, 285.0)]:
        add("dd_financials_detail", proposal_id=pid, entity_id=g, entity_name="Al Sahel group (combined: trading, ready-mix, logistics)",
            entity_scope="combined", period_label=lab, year=yr, period_kind="audited", period_end=f"{yr}-12-31", months=12, currency="SAR",
            auditor="Mizan & Partners Chartered Accountants" if yr == 2025 else "Qarar Audit", auditor_panel="unlisted" if yr == 2025 else "listed",
            opinion="qualified" if yr == 2025 else "clean", qualification_basis="Combined statements prepared by management; logistics receivable not provided for." if yr == 2025 else "",
            revenue_mn=rev, gross_profit_mn=gp, operating_profit_mn=op_, net_profit_mn=np_, ebitda_mn=eb, total_assets_mn=ta,
            current_assets_mn=ca, receivables_mn=rcv, inventory_mn=inv, due_from_related_mn=dfr, current_liabilities_mn=cl,
            total_liabilities_mn=td, net_worth_mn=nw, staff_count=477, source="Combined financial statements as per business")

    for i, (kind, lab, sh, val, yr, txt, att) in enumerate([
            ("activity_mix", "Steel and rebar", 46.0, 322.9, 2025, "Steel and rebar 46% of FY2025 revenue (FY2024 44%).", "audited"),
            ("activity_mix", "Cement and aggregates", 31.0, 217.6, 2025, "Cement and aggregates 31% (FY2024 33%), of which SAR 96.0m sold to the ready-mix sister.", "audited"),
            ("activity_mix", "Timber, blocks and finishing materials", 23.0, 161.5, 2025, "Timber, blocks and finishing materials 23% (FY2024 23%).", "audited"),
            ("sales_terms", "Post-dated cheques", 52.0, None, 2025, "52% of sales against post-dated cheques of 60-120 days, as per business.", "as_per_business"),
            ("sales_terms", "Open account", 38.0, None, 2025, "38% on open account of up to 90 days, as per business.", "as_per_business"),
            ("sales_terms", "Cash", 10.0, None, 2025, "10% cash sales, as per business.", "as_per_business"),
            ("purchase_terms", "Import LCs", 64.0, None, 2025, "64% of purchases imported under sight and usance LCs (China, Turkey, Oman), as per business.", "as_per_business"),
            ("top_customer", "Government-linked contractors (top 5)", 41.0, None, 2025, "Top 5 debtors 41% of receivables (FY2024 40%); largest 14%.", "audited"),
            ("geopolitical", "Red Sea shipping routes", None, None, 2026, "Business conveys that rerouting of Red Sea shipping added 18-25 days and about 6% to landed steel cost in 2026; not quantified in the projections.", "as_per_business"),
            ("market", "Government project slowdown", None, None, 2026, "Business attributes the routing shortfall and slower collections to delayed government project payments in 2026; no evidence provided.", "as_per_business"),
            # R13 Q: credit turnover at the other banks over Jul 2025-Jun 2026, from the statements business provided (revenue against conduct)
            ("bank_turnover", "Northern Gulf Bank", None, 41.0, 2026, "Credit turnover of SAR 41.0m at Northern Gulf Bank over Jul 2025-Jun 2026 per the statements provided, as per business.", "as_per_business"),
            ("bank_turnover", "Coastal Commerce Bank", None, 36.0, 2026, "Credit turnover of SAR 36.0m at Coastal Commerce Bank over Jul 2025-Jun 2026 per the statements provided, as per business.", "as_per_business")]):
        add("dd_business_profile", proposal_id=pid, item_id=f"BP{i + 1}", entity_id=S, item_kind=kind, label=lab, share_pct=sh, value_mn=val, year=yr,
            text=txt, attribution=att)
    conduct(pid, S, "2024-07", 24, base_turnover=36.0, growth=0.004, limits=180.0, util=(0.78, 0.98), routed_share=0.308,
            returned={"2026-01": (2, 1.1), "2026-02": (1, 0.4), "2026-03": (2, 1.6), "2026-05": (1, 0.9), "2026-06": (1, 0.6)},
            past_due={"2026-03": (12, 2.4), "2026-05": (6, 0.8)}, avg_bal=(9.0, 4.0))
    promise(pid, S, "PR-TWA-1", "routing", "Route business through the bank of at least 2 times the total limits per year (SAR 360.0m).",
            360.0, 2.0, "2025-09-01", "2026-08-31", "CC-2025-118")
    bureau_rows(pid, [
        (S, "Al Sahel Building Materials Trading LLC", "company", "2026-09-21", 1, "", 14, 411.0, 0.0, 0, 7, 4.6, "2026-01-11;2026-01-27;2026-02-19;2026-03-08;2026-03-22;2026-05-14;2026-06-02", 612, 0, 0.0, "current", "Seven returned cheques in 2026 (SAR 4.6m), insufficient funds"),
        (H, "Al Sahel Holding Company", "company", "2026-09-21", 1, "", 2, 18.0, 0.0, 0, 0, 0.0, "", 655, 0, 0.0, "current", ""),
        (RM_, "Al Sahel Ready-Mix Concrete Factory", "company", "2026-09-21", 1, "", 6, 95.0, 1.2, 35, 0, 0.0, "", 598, 0, 0.0, "30 days", "Overdue SAR 1.2m at 35 days with another bank"),
        (LG, "Al Sahel Logistics Services", "company", "2026-09-21", 1, "", 4, 58.0, 38.5, 210, 3, 2.2, "2025-10-03;2025-11-17;2026-01-09", 421, 2, 41.0, "doubtful", "Classified doubtful at Peninsula Trade Bank; two court cases by lenders (SAR 41.0m)"),
        (ST, "Sahel Steel Trading Est.", "guarantor", "2026-09-21", 1, "", 3, 24.0, 0.0, 0, 0, 0.0, "", 664, 0, 0.0, "current", ""),
        (F, "Fahad Nasser Al-Sahili", "ubo", "2026-09-21", 1, "", 5, 12.0, 0.0, 0, 0, 0.0, "", 701, 0, 0.0, "current", ""),
        (Sd, "Saeed Nasser Al-Sahili", "ubo", "", 0, "Not provided: business conveys the shareholder is travelling", None, None, None, None, None, None, "", None, None, None, "", ""),
        (Mo, "Mona Fahad Al-Sahili", "ubo", "", 0, "Not provided: consent not yet signed, as per business", None, None, None, None, None, None, "", None, None, None, "", "")])
    for eid, nm, fl, fo, nl, no, banks, cls in [(S, "Al Sahel Building Materials Trading LLC", 300.0, 236.0, 250.0, 175.0, 5, "regular"),
                                                 (H, "Al Sahel Holding Company", 25.0, 18.0, 0.0, 0.0, 1, "regular"),
                                                 (RM_, "Al Sahel Ready-Mix Concrete Factory", 70.0, 64.0, 46.0, 31.0, 3, "watch"),
                                                 (LG, "Al Sahel Logistics Services", 55.0, 52.0, 10.0, 6.0, 2, "doubtful"),
                                                 (ST, "Sahel Steel Trading Est.", 30.0, 22.0, 5.0, 2.0, 2, "regular")]:
        add("bureau_cbrbr", proposal_id=pid, entity_id=eid, entity_name=nm, report_date="2026-09-30", funded_limit_mn=fl, funded_outstanding_mn=fo,
            non_funded_limit_mn=nl, non_funded_outstanding_mn=no, total_limit_mn=fl + nl, total_outstanding_mn=fo + no, banks_n=banks, classification=cls)
    for bank, eid, nm, ft, dl, do, bl, bo, fal, fd_, secu, note, clar in [
            ("Coastal Commerce Bank", S, "Al Sahel Building Materials Trading LLC", "LC;LCM;OD", 120.0, 88.0, 120.0, 90.0, 1, "2026-03-10", "PG of the UBO", "Within SAR 2.0m of the bureau; timing difference.", 1),
            ("Northern Gulf Bank", S, "Al Sahel Building Materials Trading LLC", "LC;LG", 90.0, 61.0, 90.0, 63.0, 1, "2026-01-22", "PG of the UBO; assignment of receivables", "Within SAR 2.0m of the bureau.", 1),
            ("Peninsula Trade Bank", S, "Al Sahel Building Materials Trading LLC", "STL", 40.0, 0.0, 110.0, 71.0, 0, "", "Not known", "Declared as unutilised SAR 40.0m; the bureau shows SAR 110.0m limit and SAR 71.0m outstanding. Not clarified; FAL not provided.", 0),
            ("Red Sea Investment Bank", S, "Al Sahel Building Materials Trading LLC", "LG", 50.0, 9.0, 50.0, 9.0, 1, "2025-12-05", "Cash margin 10%", "Agrees to the bureau.", 1),
            ("Coastal Commerce Bank", RM_, "Al Sahel Ready-Mix Concrete Factory", "TL;OD", 60.0, 52.0, 60.0, 54.0, 1, "2025-11-30", "Mortgage of the factory plot", "Agrees within SAR 2.0m.", 1),
            ("Peninsula Trade Bank", LG, "Al Sahel Logistics Services", "TL", 0.0, 0.0, 55.0, 52.0, 0, "", "Vehicles", "Not declared; the bureau shows the facility classified doubtful.", 0)]:
        add("other_bank_facility", proposal_id=pid, bank_name=bank, entity_id=eid, entity_name=nm, facility_types=ft, declared_limit_mn=dl,
            declared_outstanding_mn=do, bureau_limit_mn=bl, bureau_outstanding_mn=bo, difference_mn=round(bo - do, 2), fal_provided_flag=fal,
            fal_date=fd_, security_text=secu, reconciliation_note=note, clarified_flag=clar)
    docs(pid, "corporate", "renewal", {S: "Al Sahel Building Materials Trading LLC", H: "Al Sahel Holding Company", RM_: "Al Sahel Ready-Mix Concrete Factory",
                                        LG: "Al Sahel Logistics Services", ST: "Sahel Steel Trading Est."},
         ubos={F: "Fahad Nasser Al-Sahili", Sd: "Saeed Nasser Al-Sahili", Mo: "Mona Fahad Al-Sahili"},
         guarantors={F: "Fahad Nasser Al-Sahili", ST: "Sahel Steel Trading Est.", H: "Al Sahel Holding Company"},
         banks=["Coastal Commerce Bank", "Northern Gulf Bank", "Peninsula Trade Bank", "Red Sea Investment Bank"],
         missing={("bureau_ubo", Sd): ("pending", "Not provided: shareholder travelling, as per business"),
                  ("bureau_ubo", Mo): ("pending", "Consent not yet signed"),
                  ("other_bank_fal", "Peninsula Trade Bank"): ("pending", "FAL not provided; facility not declared in full"),
                  ("guarantor_nw", F): ("expired", "Net-worth statement dated 2025-03-31"),
                  ("legal_opinion", ST): ("pending", "Legal opinion on the corporate guarantee not obtained"),
                  ("trade_licence", LG): ("expired", "Licence expired 2026-09-30"),
                  ("interim_fs", S): ("received", "")})
    flow(pid, [("", "draft", "Tamer Al-Jaafari", "rm", "2026-09-28T09:12:00Z", "Renewal drafted from last year's file."),
               ("draft", "submitted", "Tamer Al-Jaafari", "rm", "2026-10-01T11:40:00Z", "Submitted to credit."),
               ("submitted", "in_review", "Dana Al-Khatib", "credit_reviewer", "2026-10-04T08:05:00Z", "Picked up for review."),
               ("in_review", "queries", "Dana Al-Khatib", "credit_reviewer", "2026-10-08T13:30:00Z", "Three queries sent to the RM.")])
    q = [("Q-TWA-1", "E-TWA-F2", "", [("to_rm", "Dana Al-Khatib", "credit_reviewer", "2026-10-08T13:31:00Z", "Peninsula Trade Bank facility",
                                      "The bureau shows SAR 110.0m limit and SAR 71.0m outstanding at Peninsula Trade Bank against SAR 40.0m declared as unutilised. Please provide the FAL and explain the difference.", "open")]),
         ("Q-TWA-2", "", "DOC-R12-TWA-bureau_ubo-XP-TWA-02", [("to_rm", "Dana Al-Khatib", "credit_reviewer", "2026-10-08T13:33:00Z", "Bureau reports of the UBOs",
                                                                "Bureau reports of Saeed Nasser Al-Sahili and Mona Fahad Al-Sahili are not on file. Please obtain their consent and the reports.", "open")]),
         ("Q-TWA-3", "E-TWA-F3", "", [("to_rm", "Dana Al-Khatib", "credit_reviewer", "2026-10-08T13:36:00Z", "Routing undertaking",
                                      "Routed business was SAR 119.0m in the last 12 months against SAR 360.0m undertaken (33%). Please explain and propose a plan.", "open"),
                                     ("from_rm", "Tamer Al-Jaafari", "rm", "2026-10-09T10:02:00Z", "RE: Routing undertaking",
                                      "Business conveys that the slowdown in government projects reduced trade volumes; the client undertakes to move the Coastal Commerce Bank LC business to us from Q1 2027.", "answered")])]
    queries(pid, q)
    conds(pid, [
        ("CO-TWA-1", "ALL", "routing", "Route business of at least 2x total limits (SAR 360.0m) per year through the bank.", "RM and regional head", "", "annual", "routing_multiple", ">=", 2.0, 0.66, "2026-08-31", "not_complied", "prior_approval", "CC-2025-118"),
        ("CO-TWA-2", "ALL", "reporting", "Submit audited financial statements within 120 days of year end.", "RM", "2026-04-30", "annual", "", "", None, None, "2026-06-15", "not_complied", "prior_approval", "CC-2025-118"),
        ("CO-TWA-3", "ALL", "security", "Subordinate the shareholder current account of SAR 31.0m.", "Credit administration", "2025-10-31", "once", "", "", None, None, "2025-09-30", "met", "prior_approval", "CC-2025-118"),
        ("CO-TWA-4", "ALL", "cp", "Obtain the UBO personal guarantee with a net-worth statement not older than 6 months.", "RM", "2025-09-30", "once", "", "", None, None, "2025-08-12", "met", "prior_approval", "CC-2025-118"),
        ("CO-TWA-5", "ALL", "covenant", "Auditor to remain on the bank's approved panel; change only with the bank's consent.", "RM", "", "annual", "", "", None, None, "2026-06-15", "not_complied", "prior_approval", "CC-2025-118")])
    monitoring(pid, S, "MP-TWA-2025", "Medium", "approve_standard", "severe", ["routing_multiple", "related_party_receivables"],
               [{"metric": "routing_multiple", "operator": "<", "threshold": 1.5, "label": "Routed business below 1.5x limits"}],
               {}, "semi_annual", "2026-02-20", "Credit Committee CC-2025-118", "2025-08-20T10:00:00Z",
               "Set at the 2025 renewal: routing undertaking and related-party receivables watched.", "active", "")
    findings_prior(pid, [
        ("E-TWA-F1", 2, "earlier_conditions", "medium", "Routing undertaking set at the 2025 renewal",
         "At the 2025 renewal the committee required 2x limits routed per year (CC-2025-118 dated 2025-08-20); measured semi-annually.",
         "dd_condition", "condition_id=CO-TWA-1", "resolved", "2025-08-20T10:00:00Z"),
        ("E-TWA-F2", 2, "bureau_reconciliation", "high", "Peninsula Trade Bank facility under-declared",
         "Upon checking the bureau, the facility at Peninsula Trade Bank is SAR 110.0m limit and SAR 71.0m outstanding against SAR 40.0m declared unutilised.",
         "other_bank_facility", "proposal_id=R12-TWA;bank_name=Peninsula Trade Bank;entity_id=XE-TWA-01", "open", "2026-10-08T13:20:00Z"),
        ("E-TWA-F3", 8, "earlier_conditions", "high", "Routing undertaking 33% achieved",
         "Routed business SAR 119.0m in the 12 months to 2026-08-31 against SAR 360.0m undertaken (33%).",
         "dd_promise", "promise_id=PR-TWA-1", "open", "2026-10-08T13:22:00Z")])


# ====================================================================================== Twin B
def twin_b() -> None:
    pid, g, gn = "R12-TWB", "XG-TWB", "Meridian Contracting Group"
    S, P, MEP, PC, E1, E2, E3, E4 = ("XE-TWB-01", "XE-TWB-00", "XE-TWB-02", "XE-TWB-03", "XE-TWB-E1", "XE-TWB-E2", "XE-TWB-E3", "XE-TWB-E4")
    entity(P, "Meridian Contracting Holding Company", g, gn, "parent", parent_entity_id="", country="Kuwait", legal_status="KSCC (closed)",
           activity="General contracting and investments", licence_no="KW-118204", licence_expiry="2027-06-30", incorporation_date="1994-02-14",
           incorporation_place="Kuwait City", staff_count=4100, listed_flag=0, credit_status="performing")
    entity(S, "Gulf Meridian Contracting", g, gn, "subject", parent_entity_id=P, country="Saudi Arabia", legal_status="Branch of a foreign company",
           activity="Building and infrastructure contracting (grade 1)", licence_no="CR-1010-7745", licence_expiry="2027-01-31",
           incorporation_date="2012-10-07", incorporation_place="Riyadh", staff_count=2350, listed_flag=0, credit_status="performing")
    entity(MEP, "Meridian MEP Services", g, gn, "subsidiary", parent_entity_id=P, country="Saudi Arabia", legal_status="LLC",
           activity="Mechanical, electrical and plumbing works", licence_no="CR-1010-8810", licence_expiry="2026-11-30",
           incorporation_date="2017-05-02", incorporation_place="Riyadh", staff_count=610, listed_flag=0, credit_status="past_due",
           credit_status_note="Eleven returned cheques in 2026 (SAR 3.9m) and SAR 6.2m overdue at 64 days with another bank.")
    entity(PC, "Meridian Precast Industries", g, gn, "sister", parent_entity_id=P, country="Saudi Arabia", legal_status="LLC",
           activity="Precast concrete elements", licence_no="CR-2051-0094", licence_expiry="2027-03-31", incorporation_date="2015-08-19",
           incorporation_place="Dammam", staff_count=280, listed_flag=0, credit_status="performing")
    entity(E1, "Saadiyat Crest Developments", "XG-EMP1", "Saadiyat Crest Developments", "employer", parent_entity_id="", country="Saudi Arabia",
           legal_status="Closed JSC", activity="Master developer of residential communities", licence_no="CR-1010-9931",
           licence_expiry="2028-01-31", incorporation_date="2014-03-03", incorporation_place="Riyadh", staff_count=420, listed_flag=0,
           credit_status="performing")
    for eid, nm in ((E2, "Al Wusta Housing Company"), (E3, "Harbourline Real Estate Company"), (E4, "Northgate Education Projects Company")):
        entity(eid, nm, f"XG-{eid[-2:]}", nm, "employer", parent_entity_id="", country="Saudi Arabia", legal_status="Closed JSC",
               activity="Real estate and project owner", licence_no={"Al Wusta Housing Company": "CR-1010-4471", "Harbourline Real Estate Company": "CR-4030-1185", "Northgate Education Projects Company": "CR-2050-7730"}[nm], licence_expiry="2027-12-31",
               incorporation_date="2010-01-01", incorporation_place="Riyadh", staff_count=150, listed_flag=0,
               credit_status="performing" if eid != E3 else "past_due",
               credit_status_note="" if eid != E3 else "Has not paid four certified payments to the contractor since 2026-04-30.")
    J, Sa, MinH = "XP-TWB-01", "XP-TWB-02", "XP-TWB-03"
    holder(P, J, "Jaber Mansour Al-Hamdawi", "person", "Kuwaiti", 62.0, 1, 1958, 62.0, "1994-02-14")
    holder(P, Sa, "Sana Jaber Al-Hamdawi", "person", "Kuwaiti", 23.0, 0, 1984, 23.0, "2009-06-01")
    holder(P, MinH, "Minority shareholders (17 holders)", "company", "Kuwait", 15.0, 0, None, 15.0, "2001-01-01")
    holder(S, P, "Meridian Contracting Holding Company", "company", "Kuwait", 100.0, 0, None, None, "2012-10-07")
    holder(MEP, P, "Meridian Contracting Holding Company", "company", "Kuwait", 85.0, 0, None, None, "2017-05-02")
    holder(MEP, "XP-TWB-04", "Karim Fouad Lahoud", "person", "Lebanese", 15.0, 0, 1975, None, "2017-05-02")
    holder(PC, P, "Meridian Contracting Holding Company", "company", "Kuwait", 100.0, 0, None, None, "2015-08-19")
    add("b360_ownership_change", change_id="OC-TWB-1", entity_id=MEP, change_date="2026-02-11", holder_id=P, holder_name="Meridian Contracting Holding Company",
        from_pct=70.0, to_pct=85.0, kind="transfer", disclosed_flag=1, note="Parent bought 15% from the minority partner; disclosed in the proposal.")
    add("b360_ownership_change", change_id="OC-TWB-2", entity_id=MEP, change_date="2026-02-11", holder_id="XP-TWB-04", holder_name="Karim Fouad Lahoud",
        from_pct=30.0, to_pct=15.0, kind="transfer", disclosed_flag=1, note="Sold 15% to the parent.")
    add("b360_board", entity_id=S, person_id=J, person_name="Jaber Mansour Al-Hamdawi", role="chairman", nationality="Kuwaiti", appointed="2012-10-07",
        key_person_flag=1, other_directorships=[{"entity_id": P, "entity_name": "Meridian Contracting Holding Company", "role": "chairman"},
                                                {"entity_id": PC, "entity_name": "Meridian Precast Industries", "role": "chairman"}], linked_borrower_ids="")
    add("b360_board", entity_id=S, person_id="XP-TWB-05", person_name="Ziad Nabil Haroun", role="gm", nationality="Lebanese", appointed="2019-04-01",
        key_person_flag=1, other_directorships=[{"entity_id": MEP, "entity_name": "Meridian MEP Services", "role": "director"}], linked_borrower_ids="")
    add("b360_board", entity_id=S, person_id="XP-TWB-06", person_name="Priya Raman Iyer", role="cfo", nationality="Indian", appointed="2022-09-15",
        key_person_flag=0, other_directorships=[], linked_borrower_ids="")
    add("b360_insider_link", link_id="IL-TWB-1", entity_id=MEP, person_id="XP-TWB-04", person_name="Karim Fouad Lahoud", link_kind="related_party",
        bank_staff_id="", staff_role="", relationship="minority partner of the subsidiary; brother-in-law of the branch GM", share_pct=15.0,
        disclosed_flag=1, detected_by="Related-party register", note="Related party of management; disclosed.")
    for src, tgt, val, det in ((S, E1, 0.0, "Employer of Crest Gardens Villas Phase 2 (new) and Crest Marina Promenade"),
                               (S, E2, 0.0, "Employer of Al Wusta Residential Towers and Al Wusta Phase 3 infrastructure"),
                               (S, E3, 0.0, "Employer of Harbourline Mixed-Use Podium"), (S, E4, 0.0, "Employer of Northgate Schools Package")):
        add("b360_edge", edge_id=f"EMP-{tgt}-{src}", rel_type="employer_of", source_id=tgt, target_id=src, group_id="TWB", detail=det)
    add("b360_edge", edge_id=f"SUP-{PC}-{S}", rel_type="supplies", source_id=PC, target_id=S, group_id="TWB", annual_value_mn=118.0,
        detail="Precast elements supplied to the branch's projects")
    add("b360_edge", edge_id=f"SUP-{MEP}-{S}", rel_type="supplies", source_id=MEP, target_id=S, group_id="TWB", annual_value_mn=164.0,
        detail="MEP subcontract works")
    add("b360_edge", edge_id=f"GUA-{P}-{S}", rel_type="guarantees", source_id=P, target_id=S, group_id="TWB", amount_mn=514.0,
        detail="Parent corporate guarantee for all limits")

    years = [(2023, "actual", 980.0, 61.0, 214.0, 31.0, 92.0, 1.19, "Audited financial statements (branch)"),
             (2024, "actual", 1120.0, 66.0, 238.0, 35.0, 85.0, 1.17, "Audited financial statements (branch)"),
             (2025, "actual", 1215.0, 70.0, 250.0, 38.0, 79.0, 1.16, "Audited financial statements (branch)"),
             (2026, "projection", 1380.0, 86.0, 262.0, 40.0, 92.0, 1.07, "Management projections as per business"),
             (2027, "projection", 1560.0, 101.0, 255.0, 41.0, 110.0, 1.09, "Management projections as per business"),
             (2028, "projection", 1690.0, 111.0, 240.0, 40.0, 131.0, 1.11, "Management projections as per business")]
    guar = [{"guarantee_id": "G1", "type": "corporate", "guarantor": "Meridian Contracting Holding Company", "guarantor_rating": "BBB-",
             "coverage_pct": 100, "offered_in_ask": True}]
    coll = [{"collateral_id": "C1", "type": "receivables", "value": 180.0, "currency": "SAR", "valuation_date": "2026-09-30", "pledged_in_ask": True}]
    prop = proposal(pid, name="Gulf Meridian Contracting", oid=S, sector="Construction", sub="Building Contracting", rating="BB-",
                    group_id=g, group_name=gn, existing=True, region="Riyadh", sector_code="F4100", rm="Hisham Al-Bazzaz",
                    received="2026-10-05", case="renewal_and_new",
                    purpose="New one-off project limit for Crest Gardens Villas Phase 2 (employer Saadiyat Crest Developments), renewal of the existing limits and a group cap increase",
                    years=years, existing_exposure=246.0, collateral=coll, guarantees=guar,
                    covenants=[{"type": "DSCR", "threshold": 1.2}, {"type": "Net debt / EBITDA", "threshold": 5.0}],
                    ask={"facility_type": "performance_lg", "structure": "conventional", "amount": 223, "tenor_years": 3, "margin_bps": 0,
                         "commission_bps": 95, "upfront_fee_bps": 30, "funded_share_pct": 0, "unfunded_type": "performance_lg",
                         "utilisation_pct": 100, "amortisation": "bullet", "guarantee_id": "G1", "guarantee_coverage_pct": 100})
    deal(pid, prop, product="contracting", deal_name="Gulf Meridian Contracting — new project limit and renewal", case_type="renewal_and_new",
         workflow_state="in_review", credit_analyst="Karim Al-Sabbagh", branch="Riyadh Corporate Centre", committee_date="2026-11-05",
         approval_authority="Board Credit Committee (group cap increase)", existing_limits_mn=318.0, proposed_limits_mn=514.0,
         group_exposure_mn=538.0, group_cap_existing_mn=420.0, group_cap_proposed_mn=560.0, rating_existing="BB-", rating_proposed="BB-",
         cif="CIF-0062177", group_no="GRP-1204", account_opened_date="2013-01-20", related_party_flag=0, related_party_cif="",
         purpose_code="P34 Contracting guarantees", industry_code="F4100", collateral_code="CG / ASG", review_date="2027-10-31",
         ao="Hisham Al-Bazzaz", ro="Nadia Sarhan")
    L = [("L0", "", 0, "Total limits", "", 0, 318.0, 246.0, 514.0, None, None, "", None, None, "", "", "", ""),
         ("L1", "L0", 1, "Bid bond line", "BB", 0, 30.0, 12.0, 30.0, 0.0, 0.75, "", None, None, "Up to 6 months per bond", "", "", "Renewal"),
         ("L2", "L0", 1, "Project limit 1: Al Wusta Residential Towers", "", 0, 85.0, 61.0, 72.0, None, None, "", None, None, "To project completion + 12 months", "", "PJ-TWB-1", "Reduced as work done reaches 96%"),
         ("L2.1", "L2", 2, "Performance and retention LGs", "PB", 0, 85.0, 61.0, 72.0, 5.0, 0.90, "", None, None, "", "", "PJ-TWB-1", ""),
         ("L3", "L0", 1, "Project limit 2: Harbourline Mixed-Use Podium", "", 0, 70.0, 58.0, 64.0, None, None, "", None, None, "To project completion + 12 months", "", "PJ-TWB-2", "Reduced"),
         ("L3.1", "L3", 2, "Advance-payment and performance LGs", "APG", 0, 70.0, 58.0, 64.0, 5.0, 0.90, "", None, None, "", "", "PJ-TWB-2", ""),
         ("L4", "L0", 1, "Project limit 3: Northgate Schools Package", "", 0, 48.0, 41.0, 40.0, None, None, "", None, None, "To project completion + 12 months", "", "PJ-TWB-3", "Reduced"),
         ("L4.1", "L4", 2, "Performance LGs", "PB", 0, 48.0, 41.0, 40.0, 5.0, 0.90, "", None, None, "", "", "PJ-TWB-3", ""),
         ("L5", "L0", 1, "General LG line", "LG", 0, 40.0, 29.0, 40.0, 10.0, 0.85, "", None, None, "Up to 24 months", "", "", ""),
         ("L6", "L0", 1, "Overdraft and finance against payment certificates (funded)", "OD", 1, 45.0, 45.0, 45.0, 0.0, None, "3M SAIBOR", 2.75, 6.25, "12 months", "On receipt of certified payments", "", "Fully utilised"),
         ("L7", "L0", 1, "Project limit 4 (new, one-off): Crest Gardens Villas Phase 2", "", 0, 0.0, 0.0, 223.0, None, None, "", None, None, "30 months + 12 months maintenance", "", "PJ-TWB-4", "New for employer Saadiyat Crest Developments"),
         ("L7.1", "L7", 2, "Advance-payment LG (10% of contract)", "APG", 0, 0.0, 0.0, 69.0, 0.0, 0.95, "", None, None, "Reducing with advance recovery", "", "PJ-TWB-4", ""),
         ("L7.2", "L7", 2, "Performance LG (10% of contract)", "PB", 0, 0.0, 0.0, 69.0, 0.0, 0.95, "", None, None, "To completion + 12 months", "", "PJ-TWB-4", ""),
         ("L7.3", "L7", 2, "Finance against certified payment certificates (80%; last two certificates not financed)", "DMCCM_PC", 1, 0.0, 0.0, 60.0, 0.0, None, "3M SAIBOR", 2.50, 6.00, "Up to 120 days per drawing", "From the employer's payment of the certificate", "PJ-TWB-4", ""),
         ("L7.4", "L7", 2, "LC sight / usance with LCM for project materials", "LCM", 1, 0.0, 0.0, 25.0, 10.0, 0.75, "3M SAIBOR", 2.50, 6.00, "Up to 180 days", "From project proceeds", "PJ-TWB-4", "")]
    for i, (lid, par, lev, nm, code, fund, ex, out, pr, cm, com, bm, sp, fl, ten, rep, prj, part) in enumerate(L):
        add("dd_facility_limit", proposal_id=pid, limit_id=lid, parent_limit_id=par, level=lev, seq=i + 1, limit_name=nm, product_code=code,
            funded_flag=fund, currency="SAR", existing_mn=ex, outstanding_mn=out, proposed_mn=pr, cash_margin_pct=cm, commission_pct_pa=com,
            benchmark=bm, spread_pct=sp, floor_pct=fl, tenor_text=ten, repayment_text=rep, project_id=prj, interchangeable_flag=0, particulars=part)
    for sid, lim, kind, prov, pe, amt, nw, nwd, perf, dl, lo, ex, note in [
            ("S1", "ALL", "corporate_guarantee", "Meridian Contracting Holding Company", P, 514.0, 2140.0, "2025-12-31", "perfected", "", "2024-11-20", 1, "Legal opinion on the foreign guarantee dated 2024-11-20 (23 months old)"),
            ("S2", "L7", "assignment_project_proceeds", "Gulf Meridian Contracting", S, 690.0, None, "", "pending", "2027-02-28", "", 0, "Assignment of Crest Gardens contract proceeds; employer acknowledgement within 2 months of LG issuance"),
            ("S3", "L2", "assignment_project_proceeds", "Gulf Meridian Contracting", S, 410.0, None, "", "perfected", "", "", 1, "Al Wusta Residential Towers proceeds"),
            ("S4", "L3", "assignment_project_proceeds", "Gulf Meridian Contracting", S, 360.0, None, "", "not_perfected", "2025-06-30", "", 1, "Employer acknowledgement never received; deadline passed"),
            ("S5", "ALL", "subordination", "Meridian Contracting Holding Company", P, 140.0, None, "", "perfected", "", "", 1, "Subordination of the head-office account SAR 140.0m"),
            ("S6", "ALL", "security_cheque", "Gulf Meridian Contracting", S, 514.0, None, "", "pending", "2026-12-31", "", 0, "Undated security cheque for the new total")]:
        add("dd_security", proposal_id=pid, security_id=sid, limit_id=lim, kind=kind, provider=prov, provider_entity_id=pe, amount_mn=amt, currency="SAR",
            net_worth_mn=nw, net_worth_statement_date=nwd, perfection_status=perf, perfection_deadline=dl, legal_opinion_date=lo, valuation_date="",
            value_mn=None, insurance_expiry="", pari_passu_flag=1 if kind == "corporate_guarantee" else 0, existing_flag=ex, note=note)
    tnc = [("L7", "utilisation", "Project limit 4 to be used only for Crest Gardens Villas Phase 2; no inter-project or inter-group use.", "new"),
           ("L7", "disbursement", "Finance against certified payment certificates at 80% of the certified amount; the last two certificates are not financed.", "new"),
           ("L7", "settlement", "All proceeds of the project to be received in the project account with the bank and applied first to related liabilities.", "new"),
           ("L7", "cover_ratio", "Funded outstanding under limit 4 covered at least 125% by the remaining contract proceeds at all times.", "new"),
           ("L7", "cap", "APG to reduce in line with advance recovery; PB valid to completion plus 12 months maintenance.", "new"),
           ("L3", "existing_condition", "Obtain the employer's acknowledgement of the assignment of Harbourline project proceeds.", "not_complied"),
           ("ALL", "reporting", "Audited branch and consolidated parent statements within 150 days; quarterly project status reports with payment certificates.", "complied"),
           ("ALL", "routing", "Route at least 60% of the branch's project receipts through the bank.", "complied"),
           ("ALL", "purpose", "No LGs in favour of related parties; LG wording to the bank's standard (no open-ended or on-demand without expiry).", "complied")]
    seqs: dict[str, int] = {}
    for i, (lim, cat, txt, st) in enumerate(tnc):
        seqs[lim] = seqs.get(lim, 0) + 1
        add("dd_tnc", proposal_id=pid, tnc_id=f"T{i + 1}", limit_id=lim, seq=seqs[lim], category=cat, text=txt, existing_status=st)
    for eid, nm, fe, te, fp, tp, out in [(S, "Gulf Meridian Contracting", 45.0, 318.0, 130.0, 514.0, 246.0),
                                         (MEP, "Meridian MEP Services", 8.0, 24.0, 8.0, 24.0, 19.0),
                                         (PC, "Meridian Precast Industries", 0.0, 0.0, 0.0, 0.0, 0.0)]:
        add("dd_group_exposure", proposal_id=pid, group_id=g, entity_id=eid, entity_name=nm, funded_existing_mn=fe, total_existing_mn=te,
            funded_proposed_mn=fp, total_proposed_mn=tp, outstanding_mn=out)
    for rid, kind, no, dt, auth, amt, cap, txt in [
            ("R1", "committee_decision", "BCC-2025-044", "2025-10-16", "Board Credit Committee", 318.0, 420.0, "Renewal at SAR 318.0m; group cap SAR 420.0m; employer acknowledgement of Harbourline assignment required."),
            ("R2", "limit_history", "BCC-2024-031", "2024-10-10", "Board Credit Committee", 296.0, 380.0, "Project limit 3 added."),
            ("R3", "credit_file_request", "CFR-2026-0455", "2026-09-07", "", None, None, "Requested: Crest Gardens contract, BoQ, cash flow, employer financials, payment certificates of projects 1-3."),
            ("R4", "revision", "REV-2", "2026-10-12", "", None, None, "Business revised the APG from 15% to 10% of the contract value after negotiation with the employer.")]:
        add("dd_reference", proposal_id=pid, ref_id=rid, kind=kind, ref_no=no, ref_date=dt, authority=auth, amount_mn=amt, group_cap_mn=cap, text=txt)

    prj = [("PJ-TWB-1", "Al Wusta Residential Towers", "delayed", 1, "L2", "Al Wusta Housing Company", E2, "Arcline Consulting Engineers",
            "Four 22-storey residential towers", "Riyadh", 410.0, 436.0, "2021-03-01", "2024-08-31", "2026-12-31", 540, 0, 96.0, 100.0, 404.0, 371.0, 11.0, 22.0, 0.0, 61, "2026-08-31", "2026-09-28", 41, 1, 0,
            "PB 10%, RB 5%", "Monthly certificates, 45 days", 6.5,
            "About 25 months past the planned completion of 2024-08-31 at 96% work done; an extension of time of 540 days was requested in 2025 and is not formalised by the employer. Receipts are current."),
           ("PJ-TWB-2", "Harbourline Mixed-Use Podium", "delayed", 1, "L3", "Harbourline Real Estate Company", E3, "Delta Axis Engineering",
            "Retail podium and car park", "Jeddah", 360.0, 372.0, "2022-06-01", "2025-11-30", "2027-03-31", 486, 0, 78.0, 96.0, 290.0, 244.0, 23.0, 14.5, 18.0, 44, "2026-07-31", "2026-04-30", 171, 4, 1,
            "APG 10%, PB 10%", "Monthly certificates, 60 days", 7.0,
            "No payment received since 2026-04-30; four certified payments (SAR 23.0m) pending; extension of time of 486 days not formalised; a demand letter for payment was issued to the employer on 2026-09-15."),
           ("PJ-TWB-3", "Northgate Schools Package", "delayed", 1, "L4", "Northgate Education Projects Company", E4, "Arcline Consulting Engineers",
            "Six schools", "Dammam", 240.0, 240.0, "2023-01-15", "2026-01-31", "2027-02-28", 393, 1, 71.7, 100.0, 172.0, 151.0, 9.0, 8.6, 6.0, 29, "2026-09-15", "2026-09-30", 33, 1, 0,
            "PB 10%", "Monthly certificates, 45 days", 5.5, "Past the planned completion of 2026-01-31 at 71.7% work done; an extension of time of 393 days was formalised on 2026-05-20."),
           ("PJ-TWB-4", "Crest Gardens Villas Phase 2", "new", 1, "L7", "Saadiyat Crest Developments", E1, "Lumen Engineering Consultants",
            "240 villas with infrastructure and landscaping", "Riyadh", 690.0, 690.0, "2026-12-01", "2029-05-31", "2029-05-31", 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, "", "", 0, 0, 0,
            "APG 10% (revised from 15%), PB 10%, no RB", "Monthly certificates, 60 days; 10% advance recovered pro rata; 10% retention, half released at handover", 8.0,
            "New project. Scope: 240 villas. Business conveys the employer awarded the contract on 2026-09-18; the contract is signed, the BoQ is provided, the employer's financials are not provided."),
           ("PJ-TWB-5", "Crest Marina Promenade", "ongoing", 0, "", "Saadiyat Crest Developments", E1, "Lumen Engineering Consultants",
            "Waterfront promenade and retail units", "Riyadh", 300.0, 312.0, "2025-09-01", "2027-08-31", "2027-08-31", 0, 0, 18.0, 22.0, 56.0, 49.0, 7.0, 5.6, 25.0, 9, "2026-09-10", "2026-09-30", 0, 0, 0,
            "PB with another bank", "Monthly certificates, 60 days", 7.5, "Guaranteed by Northern Gulf Bank; on programme."),
           ("PJ-TWB-6", "Al Wusta Phase 3 Infrastructure", "ongoing", 0, "", "Al Wusta Housing Company", E2, "Arcline Consulting Engineers",
            "Roads and utilities", "Riyadh", 620.0, 647.0, "2025-04-01", "2028-03-31", "2028-03-31", 0, 0, 16.0, 20.0, 99.0, 88.0, 6.0, 9.9, 40.0, 14, "2026-09-20", "2026-10-05", 0, 0, 0,
            "PB with Coastal Commerce Bank", "Monthly certificates, 45 days", 6.0, "On programme."),
           # R13 Q: completed projects whose retention and final certificates are still carried as not due (financial-quality detector)
           ("PJ-TWB-7", "Al Rimal Clinic Complex", "completed", 0, "", "Al Rimal Health Projects Company", "", "Delta Axis Engineering",
            "Day-surgery clinic and staff housing", "Dammam", 180.0, 186.0, "2020-09-01", "2023-03-31", "2023-06-30", 91, 1, 100.0, 100.0, 186.0, 161.2, 6.2, 18.6, 0.0, 34, "2023-06-30", "2024-02-15", 0, 0, 0,
            "PB 10%, RB 10%", "Monthly certificates, 60 days; 10% retention released 12 months after handover", 6.0,
            "Handed over on 2023-06-30; the 12-month defects-liability period ended on 2024-06-30. Retention of SAR 18.6m and the final certificate of SAR 6.2m are reported as not due, as per business; the final account is not agreed with the employer."),
           ("PJ-TWB-8", "Eastgate Logistics Warehouses", "completed", 0, "", "Eastgate Industrial Parks Company", "", "Arcline Consulting Engineers",
            "Six bonded warehouses and yards", "Riyadh", 172.0, 179.0, "2021-05-01", "2023-12-31", "2024-03-31", 91, 1, 100.0, 100.0, 179.0, 156.3, 4.8, 17.9, 0.0, 30, "2024-03-31", "2024-07-10", 0, 0, 0,
            "PB 10%, RB 10%", "Monthly certificates, 45 days; 10% retention released 12 months after handover", 5.0,
            "Handed over on 2024-03-31; the 12-month defects-liability period ended on 2025-03-31. Retention of SAR 17.9m and the final certificate of SAR 4.8m are reported as not due, as per business; no release request is on file.")]
    pcols = ("project_id", "project_name", "status", "financed_flag", "limit_id", "employer", "employer_entity_id", "consultant", "scope", "location",
             "contract_value_original_mn", "contract_value_revised_mn", "start_date", "completion_original", "completion_revised", "eot_days",
             "eot_formalised_flag", "work_done_pct", "planned_pct", "billed_mn", "received_mn", "due_mn", "retention_mn", "advance_mn", "last_cert_no",
             "last_cert_date", "last_payment_date", "payment_delay_days", "pending_certs_n", "demand_letter_flag", "lg_requirements", "payment_terms",
             "expected_margin_pct", "narrative")
    for p in prj:
        d = dict(zip(pcols, p))
        d["backlog_mn"] = round(d["contract_value_revised_mn"] - d["billed_mn"], 1)
        add("dd_project", proposal_id=pid, obligor_id=S, main_contractor="", **d)
    project_cashflow("PJ-TWB-4", pid, "2026-12", 690.0)

    cols = ("revenue_mn", "gross_profit_mn", "operating_profit_mn", "net_profit_mn", "ebitda_mn", "finance_cost_mn", "total_assets_mn",
            "current_assets_mn", "cash_mn", "receivables_mn", "retention_receivables_mn", "contract_assets_mn", "inventory_mn",
            "due_from_related_mn", "current_liabilities_mn", "due_to_related_mn", "intangibles_mn", "shareholder_accounts_mn",
            "noncore_investments_mn", "bank_debt_st_mn", "bank_debt_lt_mn", "total_liabilities_mn", "net_worth_mn",
            "contingent_liabilities_mn", "operating_cash_flow_mn", "cash_cycle_days", "ageing_0_90_mn", "ageing_91_180_mn",
            "ageing_181_365_mn", "ageing_over_365_mn", "top1_receivable_pct", "top2_receivable_pct", "top5_receivable_pct", "backlog_mn")
    fd = [("FY2023", 2023, "audited", "2023-12-31", 12, "Crescent Audit Partners", "listed", "clean", "", S, "Gulf Meridian Contracting", "branch",
           (980.0, 98.0, 41.0, 18.6, 61.0, 24.0, 812.0, 702.0, 31.0, 214.0, 71.0, 196.0, 38.0, 88.0, 590.0, 41.0, 0.0, 0.0, 22.0, 150.0, 64.0, 720.0, 92.0, 610.0, 22.0, 168, 141.0, 41.0, 20.0, 12.0, 21.0, 38.0, 64.0, 1610.0)),
          ("FY2024", 2024, "audited", "2024-12-31", 12, "Crescent Audit Partners", "listed", "clean", "", S, "Gulf Meridian Contracting", "branch",
           (1120.0, 106.4, 43.7, 16.8, 66.0, 29.5, 941.0, 818.0, 26.0, 252.0, 84.0, 231.0, 41.0, 112.0, 701.0, 48.0, 0.0, 0.0, 22.0, 170.0, 68.0, 856.0, 85.0, 702.0, -14.0, 181, 152.0, 52.0, 30.0, 18.0, 23.0, 41.0, 68.0, 1880.0)),
          ("FY2025", 2025, "audited", "2025-12-31", 12, "Crescent Audit Partners", "listed", "clean", "", S, "Gulf Meridian Contracting", "branch",
           (1215.0, 109.4, 42.5, 14.6, 70.0, 33.8, 1046.0, 912.0, 19.0, 286.0, 97.0, 262.0, 44.0, 128.0, 788.0, 53.0, 0.0, 0.0, 22.0, 190.0, 60.0, 967.0, 79.0, 761.0, -21.0, 192, 158.0, 64.0, 38.0, 26.0, 26.0, 44.0, 71.0, 2150.0)),
          ("6M2026", 2026, "interim", "2026-06-30", 6, "", "", "unaudited", "Management accounts as per business", S, "Gulf Meridian Contracting", "branch",
           (548.0, 50.4, 18.1, 4.9, 31.5, 18.2, 1102.0, 966.0, 14.0, 309.0, 104.0, 279.0, 46.0, 136.0, 842.0, 55.0, 0.0, 0.0, 22.0, 205.0, 58.0, 1019.0, 83.0, 788.0, -9.0, 201, 160.0, 71.0, 46.0, 32.0, 27.0, 46.0, 73.0, 2310.0)),
          ("FY2024", 2024, "audited", "2024-12-31", 12, "Crescent Audit Partners", "listed", "clean", "", P, "Meridian Contracting Holding Company (consolidated)", "consolidated",
           (3480.0, 452.4, 228.0, 141.0, 302.0, 88.0, 4210.0, 2980.0, 212.0, 960.0, 310.0, 820.0, 160.0, 41.0, 2120.0, 12.0, 38.0, 0.0, 260.0, 1180.0, 610.0, 2710.0, 1500.0, 2100.0, 166.0, 151, 590.0, 200.0, 110.0, 60.0, 14.0, 24.0, 47.0, 6900.0)),
          ("FY2025", 2025, "audited", "2025-12-31", 12, "Crescent Audit Partners", "listed", "clean", "", P, "Meridian Contracting Holding Company (consolidated)", "consolidated",
           (3720.0, 465.0, 231.0, 136.0, 309.0, 97.0, 4390.0, 3120.0, 188.0, 1010.0, 336.0, 870.0, 165.0, 44.0, 2240.0, 13.0, 38.0, 0.0, 255.0, 1240.0, 590.0, 2790.0, 1600.0, 2260.0, 142.0, 158, 610.0, 214.0, 121.0, 65.0, 15.0, 26.0, 49.0, 7400.0))]
    for lab, yr, kind, end, mo, aud, panel, op, basis, eid, enm, scope, vals in fd:
        add("dd_financials_detail", proposal_id=pid, entity_id=eid, entity_name=enm, entity_scope=scope, period_label=lab, year=yr, period_kind=kind,
            period_end=end, months=mo, currency="SAR", auditor=aud, auditor_panel=panel, opinion=op, qualification_basis=basis,
            staff_count=2350 if eid == S else 4100, source="Audited financial statements" if kind == "audited" else "Interim management accounts as per business",
            **dict(zip(cols, vals)))
    for i, (kind, lab, sh, val, yr, txt, att) in enumerate([
            ("activity_mix", "Residential buildings", 58.0, 704.7, 2025, "Residential buildings 58% of FY2025 revenue (FY2024 52%).", "audited"),
            ("activity_mix", "Infrastructure", 27.0, 328.1, 2025, "Infrastructure 27% (FY2024 31%).", "audited"),
            ("activity_mix", "Education and public buildings", 15.0, 182.3, 2025, "Education and public buildings 15% (FY2024 17%).", "audited"),
            ("top_customer", "Saadiyat Crest Developments", 44.0, 946.0, 2026, "Saadiyat Crest Developments 44% of the backlog after the new award (SAR 946.0m of SAR 2,150.0m).", "verified"),
            ("top_customer", "Al Wusta Housing Company", 27.0, 580.0, 2026, "Al Wusta Housing Company 27% of the backlog; top 2 employers 71%.", "verified"),
            ("staff", "Staff", None, None, 2026, "2,350 staff at the branch, of which 1,940 site labour, as per business.", "as_per_business"),
            ("geopolitical", "Input costs", None, None, 2026, "Business conveys steel and cement prices rose 9% in 2026; contracts are fixed price with no escalation clause.", "as_per_business"),
            # R13 Q: credit turnover at the other banks over Jul 2025-Jun 2026, from the statements business provided (revenue against conduct)
            ("bank_turnover", "Coastal Commerce Bank", None, 212.0, 2026, "Credit turnover of SAR 212.0m at Coastal Commerce Bank over Jul 2025-Jun 2026 per the statements provided, as per business.", "as_per_business"),
            ("bank_turnover", "Red Sea Investment Bank", None, 96.0, 2026, "Credit turnover of SAR 96.0m at Red Sea Investment Bank over Jul 2025-Jun 2026 per the statements provided, as per business.", "as_per_business")]):
        add("dd_business_profile", proposal_id=pid, item_id=f"BP{i + 1}", entity_id=S, item_kind=kind, label=lab, share_pct=sh, value_mn=val, year=yr,
            text=txt, attribution=att)
    holder(E1, "XE-TWB-E1P", "Crest Capital Holding", "company", "Saudi Arabia", 100.0, 0, None, None, "2014-03-03")
    conduct(pid, S, "2024-07", 24, base_turnover=88.0, growth=0.006, limits=318.0, util=(0.70, 0.82), routed_share=0.64,
            returned={"2026-02": (1, 0.8), "2026-05": (1, 1.3), "2026-08": (1, 0.6)}, past_due={"2026-06": (9, 3.1)}, avg_bal=(21.0, 8.0),
            months_out=27)
    promise(pid, S, "PR-TWB-1", "routing", "Route at least 60% of the branch's project receipts through the bank.", 540.0, None, "2025-10-01", "2026-09-30",
            "BCC-2025-044")
    bureau_rows(pid, [
        (S, "Gulf Meridian Contracting", "company", "2026-09-28", 1, "", 19, 809.0, 0.0, 0, 3, 2.7, "2026-02-11;2026-05-06;2026-08-19", 588, 1, 4.1, "current", "One subcontractor claim (SAR 4.1m)"),
        (P, "Meridian Contracting Holding Company", "company", "", 0, "Not provided: foreign parent, not covered by the bureau, as per business", None, None, None, None, None, None, "", None, None, None, "", ""),
        (MEP, "Meridian MEP Services", "company", "2026-09-28", 1, "", 5, 50.0, 6.2, 64, 11, 3.9, "2026-01-14;2026-01-29;2026-02-25;2026-03-11;2026-03-30;2026-04-21;2026-05-12;2026-06-09;2026-07-07;2026-08-04;2026-09-01", 507, 3, 2.6, "60 days", "Eleven returned cheques in 2026 (SAR 3.9m)"),
        (PC, "Meridian Precast Industries", "company", "2026-09-28", 1, "", 4, 48.0, 0.0, 0, 0, 0.0, "", 671, 0, 0.0, "current", ""),
        (J, "Jaber Mansour Al-Hamdawi", "ubo", "", 0, "Not provided: non-resident UBO, as per business", None, None, None, None, None, None, "", None, None, None, "", ""),
        (E1, "Saadiyat Crest Developments", "company", "2026-09-28", 1, "", 6, 1240.0, 0.0, 0, 0, 0.0, "", 702, 0, 0.0, "current", "Employer of the new project")])
    for eid, nm, fl, fo, nl, no, banks, cls in [(S, "Gulf Meridian Contracting", 300.0, 230.0, 788.0, 579.0, 5, "regular"),
                                                 (MEP, "Meridian MEP Services", 40.0, 31.0, 30.0, 19.0, 2, "watch"),
                                                 (PC, "Meridian Precast Industries", 60.0, 48.0, 15.0, 9.0, 2, "regular"),
                                                 (E1, "Saadiyat Crest Developments", 1600.0, 1240.0, 120.0, 88.0, 5, "regular")]:
        add("bureau_cbrbr", proposal_id=pid, entity_id=eid, entity_name=nm, report_date="2026-09-30", funded_limit_mn=fl, funded_outstanding_mn=fo,
            non_funded_limit_mn=nl, non_funded_outstanding_mn=no, total_limit_mn=fl + nl, total_outstanding_mn=fo + no, banks_n=banks, classification=cls)
    for bank, eid, nm, ft, dl, do, bl, bo, fal, fd_, secu, note, clar in [
            ("Northern Gulf Bank", S, "Gulf Meridian Contracting", "PB;APG;OD", 220.0, 96.0, 220.0, 131.0, 1, "2026-02-18", "Parent CG pari passu", "LG outstanding declared SAR 96.0m; the bureau shows SAR 131.0m. Business attributes it to LGs expired but not returned; not evidenced.", 0),
            ("Coastal Commerce Bank", S, "Gulf Meridian Contracting", "PB;RB;TL", 310.0, 244.0, 310.0, 246.0, 1, "2026-03-30", "Parent CG pari passu; assignment of Al Wusta Phase 3", "Agrees within SAR 2.0m.", 1),
            ("Red Sea Investment Bank", S, "Gulf Meridian Contracting", "LC;LCM;STL", 180.0, 140.0, 180.0, 142.0, 1, "2025-12-11", "Parent CG", "Agrees within SAR 2.0m.", 1),
            ("Peninsula Trade Bank", S, "Gulf Meridian Contracting", "PB", 0.0, 0.0, 60.0, 44.0, 0, "", "Not known", "Not declared; the bureau shows a SAR 60.0m LG line with SAR 44.0m outstanding.", 0),
            ("Coastal Commerce Bank", MEP, "Meridian MEP Services", "OD;LG", 40.0, 30.0, 40.0, 31.0, 1, "2026-01-05", "Parent CG", "Agrees.", 1)]:
        add("other_bank_facility", proposal_id=pid, bank_name=bank, entity_id=eid, entity_name=nm, facility_types=ft, declared_limit_mn=dl,
            declared_outstanding_mn=do, bureau_limit_mn=bl, bureau_outstanding_mn=bo, difference_mn=round(bo - do, 2), fal_provided_flag=fal,
            fal_date=fd_, security_text=secu, reconciliation_note=note, clarified_flag=clar)
    docs(pid, "contracting", "renewal_and_new", {S: "Gulf Meridian Contracting", P: "Meridian Contracting Holding Company", MEP: "Meridian MEP Services",
                                                  PC: "Meridian Precast Industries"},
         ubos={J: "Jaber Mansour Al-Hamdawi"}, guarantors={P: "Meridian Contracting Holding Company"},
         banks=["Northern Gulf Bank", "Coastal Commerce Bank", "Red Sea Investment Bank", "Peninsula Trade Bank"],
         projects={"PJ-TWB-1": "Al Wusta Residential Towers", "PJ-TWB-2": "Harbourline Mixed-Use Podium", "PJ-TWB-3": "Northgate Schools Package",
                   "PJ-TWB-4": "Crest Gardens Villas Phase 2"},
         missing={("bureau_entity", P): ("waived", "Foreign parent not covered by the bureau; audited consolidated statements accepted"),
                  ("bureau_ubo", J): ("pending", "Non-resident UBO, as per business"),
                  ("other_bank_fal", "Peninsula Trade Bank"): ("pending", "Facility not declared"),
                  ("legal_opinion", P): ("expired", "Legal opinion on the foreign guarantee dated 2024-11-20"),
                  ("payment_certificate", "PJ-TWB-2"): ("pending", "Last four certificates certified, not paid; copies not provided"),
                  ("employer_fs", "PJ-TWB-4"): ("pending", "Employer's financial statements not provided")})
    flow(pid, [("", "draft", "Hisham Al-Bazzaz", "rm", "2026-09-30T08:00:00Z", "Drafted with CreditProbe Prepare."),
               ("draft", "submitted", "Hisham Al-Bazzaz", "rm", "2026-10-05T12:10:00Z", "Submitted with the pre-flight check: 2 warnings."),
               ("submitted", "in_review", "Karim Al-Sabbagh", "credit_reviewer", "2026-10-07T07:45:00Z", "Picked up for review.")])
    queries(pid, [("Q-TWB-1", "", "", [("to_rm", "Karim Al-Sabbagh", "credit_reviewer", "2026-10-09T09:10:00Z", "Harbourline payments",
                                       "No payment since 2026-04-30 and four certificates (SAR 23.0m) pending on Harbourline. Please provide the certificates, the demand letter and the employer's reply.", "open")])])
    conds(pid, [
        ("CO-TWB-1", "L3", "security", "Obtain the employer's acknowledgement of the assignment of Harbourline project proceeds.", "RM", "2025-06-30", "once", "", "", None, None, "2026-09-30", "not_complied", "prior_approval", "BCC-2025-044"),
        ("CO-TWB-2", "ALL", "reporting", "Quarterly project status reports with payment certificates.", "RM", "", "quarterly", "", "", None, None, "2026-07-31", "met", "prior_approval", "BCC-2025-044"),
        ("CO-TWB-3", "ALL", "routing", "Route at least 60% of project receipts through the bank.", "RM and regional head", "", "annual", "routed_share_pct", ">=", 60.0, 64.0, "2026-09-30", "met", "prior_approval", "BCC-2025-044")])
    findings_prior(pid, [
        ("E-TWB-F1", 2, "bureau_reconciliation", "high", "LG outstanding at Northern Gulf Bank under-declared",
         "LG outstanding declared SAR 96.0m against SAR 131.0m as per bureau; business attributes the difference to expired LGs not returned, not evidenced.",
         "other_bank_facility", "proposal_id=R12-TWB;bank_name=Northern Gulf Bank;entity_id=XE-TWB-01", "open", "2026-10-09T09:00:00Z")])


# ====================================================================================== syndicated, escrow, SME
def syndicated() -> None:
    pid, S = "R12-SYN", "XE-SYN-01"
    entity(S, "Najd Petrochemical Company", "XG-SYN", "Najd Petrochemical Group", "subject", parent_entity_id="XE-SYN-00", country="Saudi Arabia",
           legal_status="JSC", activity="Polyolefins and aromatics", licence_no="CR-1131-0602", licence_expiry="2028-04-30",
           incorporation_date="2004-05-11", incorporation_place="Jubail", staff_count=1850, listed_flag=1, credit_status="performing")
    entity("XE-SYN-00", "Najd Industrial Investments", "XG-SYN", "Najd Petrochemical Group", "parent", parent_entity_id="", country="Saudi Arabia",
           legal_status="JSC", activity="Industrial holding", licence_no="CR-1010-0203", licence_expiry="2028-01-31", incorporation_date="1998-01-04",
           incorporation_place="Riyadh", staff_count=60, listed_flag=1, credit_status="performing")
    holder(S, "XE-SYN-00", "Najd Industrial Investments", "company", "Saudi Arabia", 51.0, 0, None, None, "2004-05-11")
    holder(S, "XP-SYN-PUB", "Free float (listed)", "company", "Saudi Arabia", 49.0, 0, None, None, "2012-06-01")
    add("b360_board", entity_id=S, person_id="XP-SYN-01", person_name="Abdulrahman Saleh Al-Qaisi", role="chairman", nationality="Saudi", appointed="2019-03-01",
        key_person_flag=0, other_directorships=[{"entity_id": "XE-SYN-00", "entity_name": "Najd Industrial Investments", "role": "director"}], linked_borrower_ids="")
    years = [(2023, "actual", 7400.0, 1620.0, 2400.0, 280.0, 9100.0, 1.6, "Audited (as provided by the agent)"),
             (2024, "actual", 6900.0, 1410.0, 2500.0, 290.0, 9300.0, 1.5, "Audited (as provided by the agent)"),
             (2025, "actual", 7150.0, 1500.0, 2600.0, 300.0, 9450.0, 1.5, "Audited (as provided by the agent)"),
             (2026, "projection", 7600.0, 1610.0, 5300.0, 330.0, 9700.0, 1.5, "Information memorandum"),
             (2027, "projection", 8100.0, 1760.0, 5000.0, 900.0, 10100.0, 1.6, "Information memorandum"),
             (2028, "projection", 8500.0, 1880.0, 4400.0, 880.0, 10500.0, 1.7, "Information memorandum")]
    prop = proposal(pid, name="Najd Petrochemical Company", oid=S, sector="Chemicals", sub="Petrochemicals", rating="BBB",
                    group_id="XG-SYN", group_name="Najd Petrochemical Group", existing=False, region="Eastern Province", sector_code="C2011",
                    rm="Sami Al-Rifai", received="2026-10-10", case="new", status="new",
                    purpose="Participation of SAR 300.0m in a SAR 3.0bn seven-year syndicated term facility for the debottlenecking of the polyolefins plant",
                    years=years, ask={"facility_type": "term_loan", "structure": "conventional", "amount": 3000, "hold_pct": 10, "tenor_years": 7,
                                      "grace_years": 2, "margin_bps": 165, "upfront_fee_bps": 60, "amortisation": "equal"},
                    covenants=[{"type": "Net debt / EBITDA", "threshold": 3.5}, {"type": "DSCR", "threshold": 1.3}])
    deal(pid, prop, product="syndicated", deal_name="Najd Petrochem Syndicate Participation", case_type="new", workflow_state="submitted",
         credit_analyst="Dana Al-Khatib", branch="Corporate and Investment Banking", committee_date="", approval_authority="Credit Committee level 1",
         existing_limits_mn=0.0, proposed_limits_mn=300.0, group_exposure_mn=300.0, group_cap_existing_mn=0.0, group_cap_proposed_mn=0.0,
         rating_existing="", rating_proposed="BBB", cif="CIF-0090311", group_no="GRP-1420", account_opened_date="2026-10-01", related_party_flag=0,
         related_party_cif="", purpose_code="P11 Project capex", industry_code="C2011", collateral_code="Pari passu share of security", review_date="2027-10-31",
         ao="Sami Al-Rifai", ro="Sami Al-Rifai")
    add("dd_syndication", proposal_id=pid, facility_name="SAR 3.0bn seven-year syndicated term facility", borrower="Najd Petrochemical Company",
        total_facility_mn=3000.0, our_commitment_mn=300.0, final_hold_mn=200.0, our_share_pct=10.0, role="participant", agent_bank="Coastal Commerce Bank",
        mla_banks="Coastal Commerce Bank;Northern Gulf Bank;Red Sea Investment Bank", lenders_n=9, sell_down_mn=100.0, sell_down_by="2027-03-31",
        pari_passu_flag=1, security_text="Pari passu share in the mortgage of the plant and the assignment of offtake proceeds through the security agent",
        info_from_agent="Information memorandum dated 2026-09-20; agent's model; quarterly compliance certificates through the agent",
        covenants_text="Net debt / EBITDA at most 3.5x; DSCR at least 1.3x; tested semi-annually on consolidated accounts", majority_lenders_pct=66.7,
        margin_bps=165.0, upfront_fee_bps=60.0, tenor_years=7.0, signing_date="2026-11-30")
    add("dd_facility_limit", proposal_id=pid, limit_id="L1", parent_limit_id="", level=1, seq=1, limit_name="Participation in the syndicated term facility",
        product_code="SYND_TL", funded_flag=1, currency="SAR", existing_mn=0.0, outstanding_mn=0.0, proposed_mn=300.0, cash_margin_pct=0.0,
        commission_pct_pa=None, benchmark="3M SAIBOR", spread_pct=1.65, floor_pct=None, tenor_text="7 years incl. 2 years grace",
        repayment_text="10 equal semi-annual instalments after grace", project_id="", interchangeable_flag=0, particulars="Final hold SAR 200.0m after sell-down")
    add("dd_security", proposal_id=pid, security_id="S1", limit_id="L1", kind="mortgage", provider="Najd Petrochemical Company", provider_entity_id=S,
        amount_mn=3000.0, currency="SAR", net_worth_mn=None, net_worth_statement_date="", perfection_status="pending", perfection_deadline="2027-02-28",
        legal_opinion_date="2026-09-25", valuation_date="2026-08-31", value_mn=6200.0, insurance_expiry="2027-06-30", pari_passu_flag=1, existing_flag=0,
        note="Shared through the security agent; our share 10%")
    bureau_rows(pid, [(S, "Najd Petrochemical Company", "company", "2026-10-02", 1, "", 11, 5900.0, 0.0, 0, 0, 0.0, "", 744, 0, 0.0, "current", "")])
    docs(pid, "syndicated", "new", {S: "Najd Petrochemical Company"}, ubos={}, guarantors={}, banks=[],
         missing={("syndication_ia", S): ("received", ""), ("legal_opinion", S): ("received", "")})
    flow(pid, [("", "draft", "Sami Al-Rifai", "rm", "2026-10-08T10:00:00Z", "Invitation from the MLAs received 2026-09-22."),
               ("draft", "submitted", "Sami Al-Rifai", "rm", "2026-10-10T15:00:00Z", "Submitted; commitment due 2026-11-15.")])
    add("dd_swot", swot_id="E-SYN-S1", proposal_id=pid, quadrant="S", kind="financial", topic="leverage",
        text="Debt / EBITDA 1.7x at FY2025 (FY2024 1.8x), rising to 3.3x after the SAR 3.0bn facility as per the information memorandum.",
        evidence_relation="dd_financials_detail", evidence_key="proposal_id=R12-SYN", finding_id="", mitigant_text="", mitigant_ref="", covered_flag=None)
    add("dd_swot", swot_id="E-SYN-W1", proposal_id=pid, quadrant="W", kind="qualitative", topic="governance",
        text="As a participant we depend on the agent for information; majority-lender threshold 66.7% means our 6.7% final hold cannot block waivers.",
        evidence_relation="dd_syndication", evidence_key="proposal_id=R12-SYN", finding_id="", mitigant_text="Sell-down to SAR 200.0m final hold; quarterly agent reporting as a condition",
        mitigant_ref="L1", covered_flag=1)
    add("dd_swot", swot_id="E-SYN-T1", proposal_id=pid, quadrant="T", kind="qualitative", topic="geopolitics",
        text="Polyolefin margins follow oil and feedstock prices; an oil price fall of 30% cuts sector revenue by 15% in the bank's scenarios.",
        evidence_relation="dd_stress_scenario", evidence_key="scenario_id=oil_30", finding_id="", mitigant_text="", mitigant_ref="", covered_flag=0)
    add("dd_financials_detail", proposal_id=pid, entity_id=S, entity_name="Najd Petrochemical Company (consolidated)", entity_scope="consolidated",
        period_label="FY2025", year=2025, period_kind="audited", period_end="2025-12-31", months=12, currency="SAR", auditor="Crescent Audit Partners",
        auditor_panel="listed", opinion="clean", qualification_basis="", revenue_mn=7150.0, gross_profit_mn=1720.0, operating_profit_mn=890.0,
        net_profit_mn=610.0, ebitda_mn=1500.0, total_assets_mn=16800.0, current_assets_mn=4100.0, cash_mn=1050.0, receivables_mn=1380.0,
        net_worth_mn=9450.0, bank_debt_st_mn=400.0, bank_debt_lt_mn=2200.0, total_liabilities_mn=7350.0, staff_count=1850,
        source="Audited financial statements, as provided by the agent")


def escrow() -> None:
    pid, S = "R12-ESC", "XE-ESC-01"
    entity(S, "Marina Vista Developments", "XG-ESC", "Marina Vista Group", "subject", parent_entity_id="", country="Saudi Arabia", legal_status="LLC",
           activity="Residential real estate development", licence_no="CR-4030-2219", licence_expiry="2027-09-30", incorporation_date="2018-02-01",
           incorporation_place="Jeddah", staff_count=85, listed_flag=0, credit_status="performing")
    holder(S, "XP-ESC-01", "Hani Walid Al-Saffar", "person", "Saudi", 70.0, 1, 1972, 70.0, "2018-02-01")
    holder(S, "XP-ESC-02", "Rana Walid Al-Saffar", "person", "Saudi", 30.0, 1, 1976, 30.0, "2018-02-01")
    add("b360_board", entity_id=S, person_id="XP-ESC-01", person_name="Hani Walid Al-Saffar", role="ceo", nationality="Saudi", appointed="2018-02-01",
        key_person_flag=1, other_directorships=[], linked_borrower_ids="")
    years = [(2023, "actual", 380.0, 104.0, 40.0, 8.0, 240.0, 1.4, "Audited financial statements"),
             (2024, "actual", 455.0, 128.0, 52.0, 10.0, 268.0, 1.3, "Audited financial statements"),
             (2025, "actual", 520.0, 150.0, 60.0, 12.0, 296.0, 1.3, "Audited financial statements"),
             (2026, "projection", 420.0, 82.0, 260.0, 52.0, 340.0, 1.3, "Developer's business plan"),
             (2027, "projection", 610.0, 120.0, 210.0, 88.0, 410.0, 1.4, "Developer's business plan"),
             (2028, "projection", 640.0, 128.0, 60.0, 160.0, 500.0, 1.6, "Developer's business plan")]
    coll = [{"collateral_id": "C1", "type": "real_estate", "value": 520.0, "currency": "SAR", "valuation_date": "2026-07-31", "pledged_in_ask": True},
            {"collateral_id": "C2", "type": "receivables", "value": 742.0, "currency": "SAR", "valuation_date": "2026-09-30", "pledged_in_ask": True}]
    prop = proposal(pid, name="Marina Vista Developments", oid=S, sector="Real Estate", sub="Residential Development", rating="BB+",
                    group_id="XG-ESC", group_name="Marina Vista Group", existing=False, region="Makkah", sector_code="F4110", rm="Lama Fikri",
                    received="2026-10-06", case="new", collateral=coll,
                    purpose="Escrow-account development term loan for Marina Vista Residences (420 units, off-plan)",
                    years=years, ask={"facility_type": "term_loan", "structure": "murabaha", "amount": 250, "tenor_years": 5, "grace_years": 2,
                                      "margin_bps": 275, "upfront_fee_bps": 75, "amortisation": "equal"})
    prop["obligor"]["real_estate_finance"] = True
    deal(pid, prop, product="escrow", deal_name="Marina Vista Off-plan Escrow", case_type="new", workflow_state="in_review", credit_analyst="Karim Al-Sabbagh",
         branch="Western Region Corporate Centre", committee_date="2026-11-12", approval_authority="Credit Committee level 2", existing_limits_mn=0.0,
         proposed_limits_mn=250.0, group_exposure_mn=250.0, group_cap_existing_mn=0.0, group_cap_proposed_mn=0.0, rating_existing="", rating_proposed="BB+",
         cif="CIF-0088540", group_no="GRP-1388", account_opened_date="2025-11-03", related_party_flag=0, related_party_cif="",
         purpose_code="P41 Real estate development", industry_code="F4110", collateral_code="MTG / ESCROW", review_date="2027-10-31", ao="Lama Fikri", ro="Lama Fikri")
    wf = [{"seq": 1, "use": "Construction costs certified by the project consultant", "rule": "Against the consultant's certificate, up to the certified value"},
          {"seq": 2, "use": "Retention", "rule": "5% of each collection held until handover"},
          {"seq": 3, "use": "Debt service of the bank's facility", "rule": "Profit quarterly; principal from the sweep once construction passes 80%"},
          {"seq": 4, "use": "Developer surplus", "rule": "Only when cover ratio stays at or above 1.25x after the release"}]
    add("dd_escrow_account", escrow_id="ESC-01", proposal_id=pid, account_no="ESC-8840-0012", project_name="Marina Vista Residences", developer="Marina Vista Developments",
        escrow_agent="The bank (escrow agent)", units_total=420, units_sold=268, sales_value_mn=1060.0, collected_mn=318.0, receivable_mn=742.0,
        construction_cost_mn=980.0, construction_pct=34.0, retention_pct=5.0, waterfall_json=wf,
        release_rules="Releases only against consultant certificates; no release to the developer before 80% construction and a cover ratio of at least 1.25x.",
        cover_ratio_min_x=1.25)
    bal, loan, coll_cum, cons = 0.0, 0.0, 0.0, 12.0
    for i, m in enumerate(_months("2025-01", 18)):
        c = round(12.0 + i * 0.9, 1)
        coll_cum += c
        ret = round(0.05 * c, 2)
        loan = min(250.0, loan + (14.0 if i >= 3 else 0.0))
        cons = min(34.0, cons + 1.3)
        rc = round(c * 0.72 + (14.0 if i >= 3 else 0.0) * 0.9, 2)
        ds = round(loan * 0.075 / 12, 2)
        bal = round(bal + c + (14.0 if i >= 3 else 0.0) - rc - ds - ret, 2)
        add("dd_escrow", escrow_id="ESC-01", proposal_id=pid, month=m, collections_mn=c, release_construction_mn=rc, release_debt_service_mn=ds,
            release_developer_mn=0.0, retention_added_mn=ret, closing_balance_mn=bal, loan_outstanding_mn=loan, construction_pct=round(cons, 1),
            units_sold_cum=int(120 + i * 8.7))
    add("dd_facility_limit", proposal_id=pid, limit_id="L1", parent_limit_id="", level=1, seq=1, limit_name="Escrow-account development term loan",
        product_code="ESCROW_TL", funded_flag=1, currency="SAR", existing_mn=0.0, outstanding_mn=0.0, proposed_mn=250.0, cash_margin_pct=0.0,
        commission_pct_pa=None, benchmark="3M SAIBOR", spread_pct=2.75, floor_pct=6.0, tenor_text="60 months incl. 24 months grace", repayment_text="Equal quarterly from the escrow sweep after grace",
        project_id="", interchangeable_flag=0, particulars="Drawn against consultant certificates")
    add("dd_security", proposal_id=pid, security_id="S1", limit_id="L1", kind="mortgage", provider="Marina Vista Developments", provider_entity_id=S,
        amount_mn=250.0, currency="SAR", net_worth_mn=None, net_worth_statement_date="", perfection_status="perfected", perfection_deadline="",
        legal_opinion_date="2026-08-15", valuation_date="2026-07-31", value_mn=520.0, insurance_expiry="2027-07-31", pari_passu_flag=0, existing_flag=0,
        note="First-degree mortgage of the land")
    add("dd_security", proposal_id=pid, security_id="S2", limit_id="L1", kind="assignment_receivables", provider="Marina Vista Developments", provider_entity_id=S,
        amount_mn=742.0, currency="SAR", perfection_status="pending", perfection_deadline="2026-12-31", note="Assignment of buyers' instalments into the escrow account")
    add("dd_security", proposal_id=pid, security_id="S3", limit_id="L1", kind="personal_guarantee", provider="Hani Walid Al-Saffar", provider_entity_id="XP-ESC-01",
        amount_mn=250.0, currency="SAR", net_worth_mn=410.0, net_worth_statement_date="2026-06-30", perfection_status="perfected", pari_passu_flag=0, existing_flag=0)
    bureau_rows(pid, [(S, "Marina Vista Developments", "company", "2026-09-30", 1, "", 4, 140.0, 0.0, 0, 0, 0.0, "", 676, 0, 0.0, "current", ""),
                      ("XP-ESC-01", "Hani Walid Al-Saffar", "ubo", "2026-09-30", 1, "", 3, 8.0, 0.0, 0, 0, 0.0, "", 712, 0, 0.0, "current", "")])
    docs(pid, "escrow", "new", {S: "Marina Vista Developments"}, ubos={"XP-ESC-01": "Hani Walid Al-Saffar", "XP-ESC-02": "Rana Walid Al-Saffar"},
         guarantors={"XP-ESC-01": "Hani Walid Al-Saffar"}, banks=[],
         missing={("bureau_ubo", "XP-ESC-02"): ("pending", "Report not yet provided"),
                  ("escrow_agreement", S): ("received", "")})
    flow(pid, [("", "draft", "Lama Fikri", "rm", "2026-10-02T10:00:00Z", ""), ("draft", "submitted", "Lama Fikri", "rm", "2026-10-06T14:00:00Z", ""),
               ("submitted", "in_review", "Karim Al-Sabbagh", "credit_reviewer", "2026-10-11T09:00:00Z", "")])


def sme() -> None:
    apps = [("R12-SME1", "Qamar Precision Workshop", "Manufacturing", "Metal Fabrication", "SME equipment", 4.5, 60, 9, 21.0, 612, 3, 0.0091,
             [("years_in_business", 9, 3, True), ("dscr_x", 1.62, 1.25, True), ("bureau_score", 688, 600, True), ("returned_cheques_12m", 0, 2, True),
              ("amount_to_sales_pct", 21.4, 35.0, True)], "approve", "SME Credit Manager (up to SAR 5.0m)",
             "Hypothecation of the financed CNC machines; personal guarantee of the owner.", 0, "2026-10-12", "2026-10-14"),
            ("R12-SME2", "Dunes Fresh Bakery Supplies", "Wholesale Trade", "Food Distribution", "SME working capital", 2.0, 12, 2, 14.0, 571, 5, 0.0182,
             [("years_in_business", 2, 3, False), ("dscr_x", 1.41, 1.25, True), ("bureau_score", 641, 600, True), ("returned_cheques_12m", 1, 2, True),
              ("amount_to_sales_pct", 14.3, 35.0, True)], "refer", "Refer to the full flow (policy exception: years in business)",
             "Exception to the 3-year minimum; refer to the corporate full flow with the owner's guarantee.", 1, "2026-10-13", ""),
            ("R12-SME3", "Bayt Al Zaitoun Trading", "Retail Trade", "Food Retail", "SME working capital", 3.0, 12, 6, 9.5, 498, 9, 0.0611,
             [("years_in_business", 6, 3, True), ("dscr_x", 0.94, 1.25, False), ("bureau_score", 534, 600, False), ("returned_cheques_12m", 5, 2, False),
              ("amount_to_sales_pct", 31.6, 35.0, True)], "decline", "SME Credit Manager (up to SAR 5.0m)",
             "Declined: DSCR 0.94x below 1.25x, bureau score 534 below 600 and 5 returned cheques in 12 months.", 0, "2026-10-09", "2026-10-11")]
    for i, (pid, nm, sec, sub, prog, amt, ten, yib, sales, score, grade, pd_, rules, dec, doa, cond, exc, sub_d, dec_d) in enumerate(apps):
        oid = f"XE-SME-{i + 1:02d}"
        entity(oid, nm, f"XG-SME{i + 1}", nm, "subject", parent_entity_id="", country="Saudi Arabia", legal_status="Sole establishment",
               activity=sub, licence_no=f"CR-SME-{4100 + i}", licence_expiry="2027-06-30", incorporation_date=f"{2026 - yib}-03-01",
               incorporation_place="Riyadh", staff_count=12 + 6 * i, listed_flag=0, credit_status="performing" if dec != "decline" else "past_due")
        owner = ["Badr Talal Al-Hindi", "Reem Ali Al-Juhani", "Majed Fawaz Al-Sudairi"][i]
        holder(oid, f"XP-SME-{i + 1:02d}", owner, "person", "Saudi", 100.0, 1, 1980 + i, 100.0, f"{2026 - yib}-03-01")
        rating = {3: "BB", 5: "B+", 9: "B-"}[grade]
        ebitda = round(sales * [0.16, 0.11, 0.06][i], 2)
        yrs = [(y, "actual", round(sales * (0.88 + 0.06 * k), 2), round(ebitda * (0.9 + 0.05 * k), 2), round(amt * 0.6, 2), round(ebitda / [3.0, 2.2, 0.94][i], 2),
                round(sales * 0.3, 2), 1.2, "Management accounts") for k, y in enumerate((2023, 2024, 2025))]
        yrs += [(y, "projection", round(sales * (1.05 + 0.05 * k), 2), round(ebitda * (1.05 + 0.05 * k), 2), round(amt * 0.8, 2), round(ebitda / [3.0, 2.2, 0.94][i], 2),
                 round(sales * 0.32, 2), 1.2, "As per applicant") for k, y in enumerate((2026, 2027, 2028))]
        prop = proposal(pid, name=nm, oid=oid, sector=sec, sub=sub, rating=rating, group_id=f"XG-SME{i + 1}", group_name=nm, existing=False,
                        region="Riyadh", sector_code="", rm="Noura Al-Bishi", received=sub_d, case="new", years=yrs, sme=True,
                        status="new" if dec == "refer" else ("approved" if dec == "approve" else "declined"),
                        purpose=prog, ask={"facility_type": "term_loan" if i == 0 else "revolver", "amount": amt, "tenor_years": max(1, ten // 12),
                                           "margin_bps": 325, "upfront_fee_bps": 100, "amortisation": "equal" if i == 0 else "bullet"})
        deal(pid, prop, product="sme", deal_name=f"{nm} — {prog}", case_type="new", workflow_state={"approve": "approved", "refer": "submitted", "decline": "declined"}[dec],
             credit_analyst="SME Credit Centre", branch="SME Centre Riyadh", committee_date="", approval_authority=doa, existing_limits_mn=0.0,
             proposed_limits_mn=amt, group_exposure_mn=amt, group_cap_existing_mn=0.0, group_cap_proposed_mn=0.0, rating_existing="", rating_proposed=rating,
             cif=f"CIF-SME-{77 + i}", group_no="", account_opened_date="2024-01-15", related_party_flag=0, related_party_cif="", purpose_code="P51 SME",
             industry_code="", collateral_code="HYP / PG" if i == 0 else "PG", review_date="2027-10-31", ao="Noura Al-Bishi", ro="Noura Al-Bishi")
        add("dd_sme_application", proposal_id=pid, applicant=nm, obligor_id=oid, programme=prog, product="term_loan" if i == 0 else "revolver", amount_mn=amt,
            tenor_months=ten, sector=sec, years_in_business=yib, annual_sales_mn=sales, scorecard_id="SME-ANN", score=score, grade=grade, pd=pd_,
            rules_json=[{"rule": r, "value": v, "limit": l, "pass": ok} for r, v, l, ok in rules], rules_failed=sum(1 for *_, ok in rules if not ok),
            decision=dec, doa_level=doa, conditions_text=cond, exception_flag=exc, submitted_date=sub_d, decided_date=dec_d)
        add("dd_facility_limit", proposal_id=pid, limit_id="L1", parent_limit_id="", level=1, seq=1, limit_name=prog, product_code="SME_TL", funded_flag=1,
            currency="SAR", existing_mn=0.0, outstanding_mn=0.0, proposed_mn=amt, cash_margin_pct=0.0, benchmark="3M SAIBOR", spread_pct=3.25, floor_pct=6.5,
            tenor_text=f"{ten} months", repayment_text="Monthly" if i == 0 else "Revolving", project_id="", interchangeable_flag=0, particulars="")
        rc = [0, 1, 5][i]
        bureau_rows(pid, [(oid, nm, "company", "2026-10-05", 1, "", 2 + i, round(amt * 0.4, 2), [0.0, 0.0, 0.42][i], [0, 0, 47][i], rc, round(rc * 0.06, 2),
                           ";".join(f"2026-0{k + 2}-1{k}" for k in range(rc)), [688, 641, 534][i], 0, 0.0, ["current", "current", "60 days"][i], "")])
        docs(pid, "sme", "new", {oid: nm}, ubos={f"XP-SME-{i + 1:02d}": owner}, guarantors={f"XP-SME-{i + 1:02d}": owner}, banks=[],
             missing={("audited_fs", oid): ("waived", "Management accounts accepted under the SME programme")} if i else {})
        flow(pid, [("", "submitted", owner, "applicant", f"{sub_d}T09:00:00Z", "Submitted through the SME channel")] +
             ([("submitted", {"approve": "approved", "decline": "declined"}[dec], "SME Credit Centre", "credit_reviewer", f"{dec_d}T12:00:00Z", "Fast-track decision")] if dec_d else []))
        conduct(pid, oid, "2025-07", 12, base_turnover=round(sales / 12 * 0.8, 2), growth=0.005, limits=amt, util=(0.4, 0.7), routed_share=0.5,
                returned={f"2026-0{k + 2}": (1, 0.06) for k in range(rc)}, past_due={"2026-06": (47, 0.42)} if i == 2 else {}, avg_bal=(0.4, 0.2))


# ====================================================================================== shared row writers
def conduct(pid: str, oid: str, start: str, n: int, base_turnover: float, growth: float, limits: float, util: tuple[float, float],
            routed_share: float, returned: dict, past_due: dict, avg_bal: tuple[float, float], months_out: int = 0) -> None:
    for i, m in enumerate(_months(start, n)):
        season = 1.0 + 0.08 * math.sin(i / 12 * 2 * math.pi)
        ct = round(base_turnover * (1 + growth) ** i * season, 2)
        u = util[0] + (util[1] - util[0]) * (0.5 + 0.5 * math.sin(i / 5))
        rn, rv = returned.get(m, (0, 0.0))
        pdd, pdv = past_due.get(m, (0, 0.0))
        add("dd_account_conduct", obligor_id=oid, proposal_id=pid, month=m, credit_turnover_mn=ct, debit_turnover_mn=round(ct * 1.01, 2),
            avg_balance_mn=round(avg_bal[0] + avg_bal[1] * math.cos(i / 4), 2), limits_mn=limits, utilised_mn=round(limits * u, 2),
            utilisation_pct=round(u * 100, 1), past_due_days_max=pdd, past_due_mn=pdv, returned_cheques_n=rn, returned_cheques_mn=rv,
            routed_business_mn=round(ct * routed_share, 2))
        for k in range(rn):
            add("dd_returned_cheque", cheque_id=f"RC-{oid}-{m}-{k + 1}", obligor_id=oid, proposal_id=pid, return_date=f"{m}-{10 + 7 * k:02d}",
                amount_mn=round(rv / rn, 3), reason="insufficient_funds" if k % 3 != 2 else "signature", regularised_flag=1 if k % 2 == 0 else 0)


def promise(pid: str, oid: str, prid: str, kind: str, text: str, promised: float, multiple: float | None, wfrom: str, wto: str, ref: str) -> None:
    rows = [r for r in R["dd_account_conduct"] if r["obligor_id"] == oid and wfrom[:7] <= r["month"] <= wto[:7]]
    delivered = round(sum(r["routed_business_mn"] for r in rows), 2)
    pct = round(delivered / promised * 100, 1)
    add("dd_promise", promise_id=prid, proposal_id=pid, obligor_id=oid, kind=kind, text=text, promised_mn=promised, multiple_of_limit=multiple,
        delivered_mn=delivered, delivered_pct=pct, window_from=wfrom, window_to=wto, measure_relation="dd_account_conduct",
        status="met" if pct >= 100 else ("partly_met" if pct >= 70 else "unmet"), committee_ref=ref)


def bureau_rows(pid: str, rows: list[tuple]) -> None:
    for (eid, nm, kind, dt, prov, why, fac, out, ovd, ovdd, rcn, rcv, rcd, score, cc, ccv, worst, note) in rows:
        add("bureau_entity_report", report_id=f"BR-{pid}-{eid}", proposal_id=pid, entity_id=eid, entity_name=nm, entity_kind=kind, bureau="SIMAH",
            report_date=dt, provided_flag=prov, not_provided_reason=why, facilities_n=fac, outstanding_mn=out, overdue_mn=ovd, overdue_days_max=ovdd,
            returned_cheques_n=rcn, returned_cheques_mn=rcv, returned_cheque_dates=rcd, score=score, court_cases_n=cc, court_cases_mn=ccv,
            worst_status=worst, note=note)


#: the checklist rules (dd_document_rule); docs() instantiates them per deal
RULES = [
    ("DR-01", "*", "*", "*", "trade_licence", "Trade licence / CR (valid)", "each_group_entity", 0, 1, "POL-CR-01", "3.1"),
    ("DR-02", "*", "corporate", "*", "moa", "Memorandum and articles of association with latest amendment", "subject", 0, 1, "POL-CR-01", "3.1"),
    ("DR-03", "*", "corporate", "*", "audited_fs", "Audited financial statements, last 3 years", "subject", 0, 1, "POL-CR-01", "3.3"),
    ("DR-04", "*", "corporate", "*", "interim_fs", "Interim financial statements (not older than 6 months)", "subject", 180, 1, "POL-CR-01", "3.3"),
    ("DR-05", "*", "*", "*", "bureau_entity", "Credit bureau report (dated within 30 days)", "each_group_entity", 30, 1, "POL-CR-01", "3.5"),
    ("DR-06", "*", "*", "*", "bureau_ubo", "Credit bureau report of the UBO (dated within 30 days)", "each_ubo", 30, 1, "POL-CR-01", "3.5"),
    ("DR-07", "*", "corporate", "*", "other_bank_fal", "Other banks' facility offer letters", "each_bank", 365, 1, "POL-CR-01", "3.2"),
    ("DR-08", "*", "*", "*", "guarantor_nw", "Guarantor net-worth statement (not older than 12 months)", "each_guarantor", 365, 1, "POL-CR-01", "3.5"),
    ("DR-09", "*", "*", "*", "legal_opinion", "Legal opinion on enforceability of guarantees (not older than 24 months)", "each_guarantor", 730, 1, "POL-CR-01", "7.4"),
    ("DR-10", "corporate", "corporate", "renewal", "insurance", "Insurance of stocks assigned to the bank", "subject", 365, 1, "POL-CR-01", "7.5"),
    ("DR-11", "contracting", "corporate", "*", "project_contract", "Signed project contract and BoQ", "each_project", 0, 1, "POL-CR-01", "4.7"),
    ("DR-12", "contracting", "corporate", "*", "payment_certificate", "Latest payment certificates (last 3)", "each_project", 120, 1, "POL-CR-01", "4.7"),
    ("DR-13", "contracting", "corporate", "*", "employer_fs", "Employer's financial statements (new projects)", "each_project", 365, 0, "POL-CR-01", "4.7"),
    ("DR-14", "contracting", "corporate", "*", "project_cashflow", "Project cash flow with cost breakdown", "each_project", 0, 1, "POL-CR-01", "4.7"),
    ("DR-15", "escrow", "corporate", "*", "escrow_agreement", "Escrow agreement and project registration", "subject", 0, 1, "POL-CR-01", "7.5"),
    ("DR-16", "escrow", "corporate", "*", "valuation", "Valuation of the land (not older than 12 months)", "subject", 365, 1, "POL-CR-01", "7.3"),
    ("DR-17", "syndicated", "corporate", "*", "syndication_ia", "Information memorandum and facility agreement draft", "subject", 0, 1, "POL-CR-01", "3.1"),
    ("DR-18", "sme", "sme", "*", "sme_application", "SME programme application with owner's KYC", "subject", 0, 1, "POL-CR-01", "3.1"),
]


def docs(pid: str, product: str, case: str, entities: dict[str, str], ubos: dict[str, str], guarantors: dict[str, str], banks: list[str],
         projects: dict[str, str] | None = None, missing: dict | None = None) -> None:
    missing = missing or {}
    seg = "sme" if product == "sme" else "corporate"
    subject = next(iter(entities))
    for rid, prod, sg, cs, dt, lab, scope, valid, mand, pol, cl in RULES:
        if prod not in ("*", product) or sg not in ("*", seg) or (cs != "*" and cs not in case):
            continue
        if product in ("syndicated",) and dt in ("other_bank_fal", "interim_fs", "moa"):
            continue   # lighter documents for participants (PLAN §1.8)
        targets = {"subject": {subject: entities[subject]}, "each_group_entity": entities, "each_ubo": ubos, "each_guarantor": guarantors,
                   "each_bank": {b: b for b in banks}, "each_project": {k: v for k, v in (projects or {}).items() if dt not in ("employer_fs",) or k.endswith("-4")}}[scope]
        for tid, tname in targets.items():
            st, note = missing.get((dt, tid), ("received", ""))
            date = "" if st in ("pending", "waived") else ("2025-03-31" if st == "expired" and dt == "guarantor_nw" else
                                                          "2024-11-20" if st == "expired" and dt == "legal_opinion" else
                                                          "2026-10-02" if dt.startswith("bureau") else "2026-09-15")
            exp = ""
            if valid and date:
                y, mth, d = map(int, date.split("-"))
                import datetime as _d
                exp = (_d.date(y, mth, d) + _d.timedelta(days=valid)).isoformat()
            if st == "expired" and not exp:
                exp = "2026-09-30"
            add("dd_document", document_id=f"DOC-{pid}-{dt}-{tid}", proposal_id=pid, rule_id=rid, doc_type=dt, doc_label=lab, entity_id=tid,
                entity_name=tname, status=st, doc_date=date, expiry_date=exp, received_date="" if st in ("pending", "waived") else "2026-09-20",
                waived_by="Credit Committee secretary" if st == "waived" else "", note=note, file_ref="" if st in ("pending", "waived") else f"DMS/{pid}/{dt}/{tid}")


def flow(pid: str, events: list[tuple]) -> None:
    for i, (fr, to, who, role, at, note) in enumerate(events):
        add("dd_workflow_event", event_id=f"WF-{pid}-{i + 1:02d}", proposal_id=pid, seq=i + 1, from_state=fr, to_state=to, actor=who, actor_role=role, at=at, note=note)


def queries(pid: str, threads: list[tuple]) -> None:
    for qid, fid, did, msgs in threads:
        for i, (dirn, who, role, at, subj, body, st) in enumerate(msgs):
            add("dd_query", query_id=qid, seq=i + 1, proposal_id=pid, finding_id=fid, document_id=did, direction=dirn, author=who, author_role=role,
                sent_at=at, subject=subj, body=body, status=st, mail_ref=f"MAIL-{qid}-{i + 1}")


def conds(pid: str, rows: list[tuple]) -> None:
    for cid, lim, kind, txt, owner, due, freq, met, op, th, mv, mat, st, src, ref in rows:
        add("dd_condition", condition_id=cid, proposal_id=pid, limit_id=lim, kind=kind, text=txt, owner=owner, due_date=due, frequency=freq,
            trigger_metric=met, trigger_operator=op, trigger_threshold=th, measured_value=mv, measured_at=mat, status=st, source=src,
            prior_committee_ref=ref, set_by="Credit Committee" if src == "prior_approval" else "E:seed", set_at="2025-08-20T10:00:00Z" if ref.startswith("CC") else "2025-10-16T10:00:00Z")


def monitoring(pid, oid, plan, tier, verdict, worst, drivers, triggers, overrides, freq, nxt, by, at, reason, status, prev) -> None:
    add("dd_monitoring_plan", plan_id=plan, proposal_id=pid, obligor_id=oid, facility_ref="ALL", tier=tier, stress_verdict=verdict,
        worst_breaking_severity=worst, drivers=drivers, named_triggers=triggers, ews_threshold_overrides=overrides, review_frequency=freq,
        next_review_date=nxt, set_by=by, set_at=at, reason=reason, status=status, previous_tier=prev)


def findings_prior(pid: str, rows: list[tuple]) -> None:
    for fid, pt, cat, sev, title, txt, rel, key, st, at in rows:
        add("dd_review_finding", finding_id=fid, proposal_id=pid, review_point=pt, category=cat, severity=sev, title=title, finding_text=txt,
            evidence_domain={"other_bank_facility": "bureau"}.get(rel, "deal_desk"), evidence_relation=rel, evidence_key=key, status=st,
            rating_notch=0, raised_by="E:seed", raised_at=at)


def project_cashflow(prj: str, pid: str, start: str, value: float) -> None:
    """Base case as per business: 30-month S-curve, 91% cost ratio, 10% advance recovered pro rata, 10% retention,
    certificates paid 2 months after the month of work."""
    n = 30
    w = [math.sin(math.pi * (i + 0.5) / n) ** 2 for i in range(n)]
    tw = sum(w)
    work = [value * x / tw for x in w]
    adv = 0.10 * value
    cum = 0.0
    bill_q: list[float] = []
    for i, m in enumerate(_months(start, n)):
        cost = work[i] * 0.91
        mat, sub, lab, ovh = cost * 0.42, cost * 0.30, cost * 0.18, cost * 0.10
        bill = work[i]
        rec_adv = bill * 0.10
        ret = bill * 0.10
        bill_q.append(bill - rec_adv - ret)
        receipts = (bill_q[i - 2] if i >= 2 else 0.0) + (adv if i == 0 else 0.0)
        net = receipts - cost
        cum += net
        add("dd_project_cashflow", project_id=prj, proposal_id=pid, scenario="base", month_no=i + 1, month=m, cost_materials_mn=round(mat, 3),
            cost_subcontract_mn=round(sub, 3), cost_labour_mn=round(lab, 3), cost_overheads_mn=round(ovh, 3), cost_total_mn=round(cost, 3),
            billing_mn=round(bill, 3), advance_in_mn=round(adv if i == 0 else 0.0, 3), advance_recovery_mn=round(rec_adv, 3),
            retention_held_mn=round(ret, 3), receipts_mn=round(receipts, 3), net_mn=round(net, 3), cumulative_mn=round(cum, 3))


def build_all() -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    R.clear()
    DEALS.clear()
    twin_a()
    twin_b()
    syndicated()
    escrow()
    sme()
    return R, DEALS


def proposal_json(p: dict[str, Any]) -> str:
    return json.dumps(p, sort_keys=False, ensure_ascii=False)
