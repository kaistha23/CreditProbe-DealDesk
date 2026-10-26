"""R14 session p: the proposal-check demo deal R14-RWQ (PLAN_R14 p, K31 point 3). Every name here is invented.

    R14-RWQ  Ruwaq Gulf Contracting Company (Dammam) — renewal and increase of a contractor's limits from SAR 150.0m to
              SAR 190.0m with a new finance-against-payment-certificates line. The bank's data carries exactly the facts the
              half-baked RM proposal in data/dealdesk/demo_proposals/ misstates or leaves out (answer_key.json): 4 returned
              cheques in 12 months, account turnover of SAR 300m a year, SAR 64.0m due from a related party, no UBO bureau
              report, an unperfected parent guarantee, a land valuation of 15 Apr 2025, group exposure of SAR 226.0m, financed
              projects behind programme, a prior committee condition not complied and pricing below the hurdle.

Built with the R12 build helpers (backend/dealdesk/data/demo.py: proposal, entity, holder, conduct, bureau_rows, docs, ...) and
published as a later version of each relation by `ops/r14_p_publish_demo.py` (actor "p:r14-sample", upsert), the way the R12/R13
sessions publish after the build (B, C, Q, S): `python -m backend.dealdesk.data.build --check` compares the build with version 1
and stays green. After a full rebuild, run the script again.

    R, deals = rows()          # {relation: [row]} and {pid: {"proposal", "deal"}} for R14-RWQ only
"""
from __future__ import annotations

PID = "R14-RWQ"
SUBJ, PARENT, SISTER, RELCO = "XE-RWQ-01", "XE-RWQ-00", "XE-RWQ-02", "XE-RWQ-03"
EMP1, EMP2 = "XE-RWQ-E1", "XE-RWQ-E2"
UBO, UBO2 = "XP-RWQ-01", "XP-RWQ-02"
NAME = "Ruwaq Gulf Contracting Company"
GROUP, GROUP_NAME = "XG-RWQ", "Ruwaq Holding Group"
RM = "Tariq Al-Mansouri"
ANALYST = "Lina Haddad"
PRIOR_REF = "CC-2025-207"


def demo_r14() -> None:  # noqa: PLR0915 - one fictional deal, written out like the twins
    from backend.dealdesk.data import demo as Dm
    add, entity, holder = Dm.add, Dm.entity, Dm.holder
    pid, g, gn = PID, GROUP, GROUP_NAME
    entity(PARENT, "Ruwaq Holding Company", g, gn, "parent", parent_entity_id="", country="Saudi Arabia", legal_status="Closed JSC",
           activity="Holding company: contracting, building materials and real estate", licence_no="CR-2050-6612", licence_expiry="2027-08-31",
           incorporation_date="2004-05-09", incorporation_place="Dammam", staff_count=60, listed_flag=0, credit_status="performing")
    entity(SUBJ, NAME, g, gn, "subject", parent_entity_id=PARENT, country="Saudi Arabia", legal_status="LLC",
           activity="Building and infrastructure contracting (grade 2)", licence_no="CR-2050-7781", licence_expiry="2027-03-31",
           incorporation_date="2009-11-15", incorporation_place="Dammam", staff_count=1180, listed_flag=0, credit_status="performing")
    entity(SISTER, "Ruwaq Ready-Mix Company", g, gn, "sister", parent_entity_id=PARENT, country="Saudi Arabia", legal_status="LLC",
           activity="Ready-mix concrete supply", licence_no="CR-2050-8034", licence_expiry="2027-01-31", incorporation_date="2013-02-20",
           incorporation_place="Dammam", staff_count=210, listed_flag=0, credit_status="performing")
    entity(RELCO, "Ruwaq Real Estate Development Company", g, gn, "sister", parent_entity_id=PARENT, country="Saudi Arabia", legal_status="LLC",
           activity="Residential real estate development", licence_no="CR-2050-9120", licence_expiry="2026-12-31", incorporation_date="2018-06-03",
           incorporation_place="Dammam", staff_count=35, listed_flag=0, credit_status="watch",
           credit_status_note="Owes the subject SAR 64.0m for works on its own villas; 210 days past due as per the subject's ageing.")
    entity(EMP1, "Al Bariq Developments Company", "XG-RWQ-E1", "Al Bariq Developments Company", "employer", parent_entity_id="", country="Saudi Arabia",
           legal_status="Closed JSC", activity="Residential master developer", licence_no="CR-2050-3301", licence_expiry="2028-02-28",
           incorporation_date="2011-04-10", incorporation_place="Khobar", staff_count=240, listed_flag=0, credit_status="performing")
    entity(EMP2, "Eastern Schools Projects Company", "XG-RWQ-E2", "Eastern Schools Projects Company", "employer", parent_entity_id="",
           country="Saudi Arabia", legal_status="Closed JSC", activity="Education projects owner", licence_no="CR-2050-4410",
           licence_expiry="2027-11-30", incorporation_date="2016-09-01", incorporation_place="Dammam", staff_count=90, listed_flag=0,
           credit_status="performing")
    holder(PARENT, UBO, "Sultan Hamad Al-Ruwaqi", "person", "Saudi", 70.0, 1, 1961, 70.0, "2004-05-09")
    holder(PARENT, UBO2, "Huda Sultan Al-Ruwaqi", "person", "Saudi", 30.0, 1, 1988, 30.0, "2016-01-01")
    for eid in (SUBJ, SISTER, RELCO):
        holder(eid, PARENT, "Ruwaq Holding Company", "company", "Saudi Arabia", 100.0, 0, None, None, "2009-11-15")
    add("b360_board", entity_id=SUBJ, person_id=UBO, person_name="Sultan Hamad Al-Ruwaqi", role="chairman", nationality="Saudi", appointed="2009-11-15",
        key_person_flag=1, other_directorships=[{"entity_id": PARENT, "entity_name": "Ruwaq Holding Company", "role": "chairman"},
                                                {"entity_id": RELCO, "entity_name": "Ruwaq Real Estate Development Company", "role": "chairman"}],
        linked_borrower_ids="")
    add("b360_board", entity_id=SUBJ, person_id="XP-RWQ-03", person_name="Adnan Fawzi Khoury", role="gm", nationality="Lebanese", appointed="2017-02-01",
        key_person_flag=1, other_directorships=[], linked_borrower_ids="")
    add("b360_board", entity_id=SUBJ, person_id="XP-RWQ-04", person_name="Ravi Menon Pillai", role="cfo", nationality="Indian", appointed="2021-07-01",
        key_person_flag=0, other_directorships=[], linked_borrower_ids="")
    add("b360_edge", edge_id=f"REL-{SUBJ}-{RELCO}", rel_type="related_party", source_id=SUBJ, target_id=RELCO, group_id="RWQ",
        detail="Subject built villas for the sister; SAR 64.0m receivable")
    add("b360_edge", edge_id=f"SUP-{SISTER}-{SUBJ}", rel_type="supplies", source_id=SISTER, target_id=SUBJ, group_id="RWQ", annual_value_mn=41.0,
        detail="Ready-mix concrete supplied to the subject's projects")
    add("b360_edge", edge_id=f"GUA-{PARENT}-{SUBJ}", rel_type="guarantees", source_id=PARENT, target_id=SUBJ, group_id="RWQ", amount_mn=190.0,
        detail="Parent corporate guarantee for all limits (not yet perfected)")
    for tgt, det in ((EMP1, "Employer of Al Bariq Residences"), (EMP2, "Employer of Eastern Schools Package 2")):
        add("b360_edge", edge_id=f"EMP-{tgt}-{SUBJ}", rel_type="employer_of", source_id=tgt, target_id=SUBJ, group_id="RWQ", detail=det)

    years = [(2023, "actual", 300.0, 33.0, 120.0, 22.0, 102.0, 1.18, "Audited financial statements"),
             (2024, "actual", 330.0, 36.0, 132.0, 24.0, 110.0, 1.16, "Audited financial statements"),
             (2025, "actual", 360.0, 38.0, 150.0, 27.0, 118.0, 1.15, "Audited financial statements")]
    guar = [{"guarantee_id": "G1", "type": "corporate", "guarantor": "Ruwaq Holding Company", "guarantor_rating": "BB",
             "coverage_pct": 100, "offered_in_ask": True}]
    coll = [{"collateral_id": "C1", "type": "real_estate", "value": 95.0, "currency": "SAR", "valuation_date": "2025-04-15", "pledged_in_ask": True}]
    prop = Dm.proposal(pid, name=NAME, oid=SUBJ, sector="Construction", sub="Building Contracting", rating="BB", group_id=g, group_name=gn,
                       existing=True, region="Eastern Province", sector_code="F4100", rm=RM, received="2026-10-12", case="renewal_and_increase",
                       purpose="Renewal of the existing contracting limits and a new SAR 40.0m line of finance against certified payment certificates",
                       years=years, existing_exposure=150.0, collateral=coll, guarantees=guar, status="new",
                       covenants=[{"type": "DSCR", "threshold": 1.25}, {"type": "Net debt / EBITDA", "threshold": 3.5}],
                       ask={"facility_type": "revolver", "structure": "conventional", "amount": 40, "tenor_years": 1, "margin_bps": 150,
                            "upfront_fee_bps": 20, "utilisation_pct": 80, "amortisation": "bullet", "guarantee_id": "G1", "guarantee_coverage_pct": 100})
    Dm.deal(pid, prop, product="contracting", deal_name=f"{NAME} — renewal and increase", case_type="renewal_and_increase",
            workflow_state="submitted", credit_analyst=ANALYST, branch="Dammam Corporate Centre", committee_date="2026-11-12",
            approval_authority="", existing_limits_mn=150.0, proposed_limits_mn=190.0, group_exposure_mn=226.0, group_cap_existing_mn=200.0,
            group_cap_proposed_mn=240.0, rating_existing="BB", rating_proposed="BB", cif="CIF-0074412", group_no="GRP-1377",
            account_opened_date="2011-03-06", related_party_flag=0, related_party_cif="", purpose_code="P34 Contracting guarantees",
            industry_code="F4100", collateral_code="CG / RE / ASG", review_date="2027-10-31", ao=RM, ro="Bader Al-Qahtani")
    L = [("L0", "", 0, "Total limits", "", 0, 150.0, 128.0, 190.0, None, None, "", None, None, "", "", "", ""),
         ("L1", "L0", 1, "Overdraft", "OD", 1, 20.0, 17.5, 20.0, 0.0, None, "3M SAIBOR", 2.25, 6.00, "12 months", "On demand", "", "Renewal"),
         ("L2", "L0", 1, "Project limit 1: Al Bariq Residences", "", 0, 60.0, 52.0, 60.0, None, None, "", None, None, "To completion + 12 months", "", "PJ-RWQ-1", "Renewal"),
         ("L2.1", "L2", 2, "Performance and advance-payment LGs", "PB", 0, 60.0, 52.0, 60.0, 10.0, 0.90, "", None, None, "", "", "PJ-RWQ-1", ""),
         ("L3", "L0", 1, "Project limit 2: Eastern Schools Package 2", "", 0, 40.0, 33.0, 30.0, None, None, "", None, None, "To completion + 12 months", "", "PJ-RWQ-2", "Reduced"),
         ("L3.1", "L3", 2, "Performance LGs", "PB", 0, 40.0, 33.0, 30.0, 10.0, 0.90, "", None, None, "", "", "PJ-RWQ-2", ""),
         ("L4", "L0", 1, "General LG line", "LG", 0, 30.0, 25.5, 40.0, 10.0, 0.85, "", None, None, "Up to 24 months", "", "", "Increase"),
         ("L5", "L0", 1, "Finance against certified payment certificates (new)", "DMCCM_PC", 1, 0.0, 0.0, 40.0, 0.0, None, "3M SAIBOR", 1.50, 5.50,
          "Up to 120 days per drawing", "From the employer's payment of the certificate", "", "New; 80% of certified amount")]
    for i, (lid, par, lev, nm, code, fund, ex, out, pr, cm, com, bm, sp, fl, ten, rep, prj, part) in enumerate(L):
        add("dd_facility_limit", proposal_id=pid, limit_id=lid, parent_limit_id=par, level=lev, seq=i + 1, limit_name=nm, product_code=code,
            funded_flag=fund, currency="SAR", existing_mn=ex, outstanding_mn=out, proposed_mn=pr, cash_margin_pct=cm, commission_pct_pa=com,
            benchmark=bm, spread_pct=sp, floor_pct=fl, tenor_text=ten, repayment_text=rep, project_id=prj, interchangeable_flag=0, particulars=part)
    for sid, lim, kind, prov, pe, amt, nw, nwd, perf, dl, lo, vd, val, ex, note in [
            ("S1", "ALL", "personal_guarantee", "Sultan Hamad Al-Ruwaqi", UBO, 190.0, 410.0, "2026-03-31", "perfected", "", "2025-11-02", "", None, 1,
             "Personal guarantee of the UBO; net-worth statement of 31 Mar 2026"),
            ("S2", "ALL", "corporate_guarantee", "Ruwaq Holding Company", PARENT, 190.0, 260.0, "2025-12-31", "pending", "2026-06-30", "", "", None, 0,
             "Board resolution of the guarantor not received; perfection deadline of 30 Jun 2026 passed"),
            ("S3", "L2", "assignment_project_proceeds", NAME, SUBJ, 210.0, None, "", "perfected", "", "", "", None, 1,
             "Assignment of Al Bariq Residences proceeds acknowledged by the employer"),
            ("S4", "ALL", "mortgage_real_estate", "Ruwaq Holding Company", PARENT, 95.0, None, "", "perfected", "", "", "2025-04-15", 95.0, 1,
             "First-degree mortgage over a 24,000 sqm plot in Dammam 2nd Industrial City; valuation by Coastline Valuers on 15 Apr 2025"),
            ("S5", "ALL", "security_cheque", NAME, SUBJ, 190.0, None, "", "pending", "2026-12-31", "", "", None, 0,
             "Undated security cheque for the new total")]:
        add("dd_security", proposal_id=pid, security_id=sid, limit_id=lim, kind=kind, provider=prov, provider_entity_id=pe, amount_mn=amt, currency="SAR",
            net_worth_mn=nw, net_worth_statement_date=nwd, perfection_status=perf, perfection_deadline=dl, legal_opinion_date=lo, valuation_date=vd,
            value_mn=val, insurance_expiry="", pari_passu_flag=0, existing_flag=ex, note=note)
    tnc = [("L5", "disbursement", "Finance against certified payment certificates at 80% of the certified amount; the last certificate of each project is not financed.", "new"),
           ("L5", "settlement", "Employer payments received in the collection account with the bank and applied first to the related drawing.", "new"),
           ("L2", "existing_condition", "Submit quarterly project status reports with certified payment certificates.", "not_complied"),
           ("ALL", "reporting", "Audited statements within 120 days of year end; interim statements within 60 days of the half year.", "complied"),
           ("ALL", "covenant", "DSCR not below 1.25x and total debt / EBITDA not above 3.5x, tested on the audited statements.", "new"),
           ("ALL", "purpose", "No LGs or funded drawings in favour of related parties.", "complied")]
    seqs: dict[str, int] = {}
    for i, (lim, cat, txt, st) in enumerate(tnc):
        seqs[lim] = seqs.get(lim, 0) + 1
        add("dd_tnc", proposal_id=pid, tnc_id=f"T{i + 1}", limit_id=lim, seq=seqs[lim], category=cat, text=txt, existing_status=st)
    for eid, nm, fe, te, fp, tp, out in [(SUBJ, NAME, 20.0, 150.0, 60.0, 190.0, 128.0),
                                         (SISTER, "Ruwaq Ready-Mix Company", 22.0, 22.0, 22.0, 22.0, 19.5),
                                         (RELCO, "Ruwaq Real Estate Development Company", 14.0, 14.0, 14.0, 14.0, 14.0),
                                         (PARENT, "Ruwaq Holding Company", 0.0, 0.0, 0.0, 0.0, 0.0)]:
        add("dd_group_exposure", proposal_id=pid, group_id=g, entity_id=eid, entity_name=nm, funded_existing_mn=fe, total_existing_mn=te,
            funded_proposed_mn=fp, total_proposed_mn=tp, outstanding_mn=out)
    for rid, kind, no, dt, auth, amt, cap, txt in [
            ("R1", "committee_decision", PRIOR_REF, "2025-10-22", "Credit Committee (CC level 2)", 150.0, 200.0,
             "Renewal at SAR 150.0m; group cap SAR 200.0m; quarterly project status reports with certified payment certificates required."),
            ("R2", "limit_history", "CC-2024-163", "2024-10-17", "Credit Committee (CC level 2)", 130.0, 180.0, "General LG line increased to SAR 30.0m."),
            ("R3", "credit_file_request", "CFR-2026-0611", "2026-10-13", "", None, None,
             "Requested: UBO bureau report, parent guarantee board resolution, updated valuation, payment certificates of project 1.")]:
        add("dd_reference", proposal_id=pid, ref_id=rid, kind=kind, ref_no=no, ref_date=dt, authority=auth, amount_mn=amt, group_cap_mn=cap, text=txt)
    prj = [("PJ-RWQ-1", "Al Bariq Residences", "delayed", 1, "L2", "Al Bariq Developments Company", EMP1, "Gulfline Consulting Engineers",
            "180 villas and community centre", "Khobar", 420.0, 438.0, "2024-01-15", "2026-07-31", "2027-03-31", 243, 0, 72.0, 88.0, 315.0, 262.0, 21.0,
            31.5, 0.0, 27, "2026-08-31", "2026-06-20", 95, 2, 0, "PB 10%, APG 10%", "Monthly certificates, 45 days", 7.0,
            "Past the planned completion of 2026-07-31 at 72% work done (88% planned); an extension of time of 243 days was requested and is not "
            "formalised; two certified payments (SAR 21.0m) pending, the last payment received on 2026-06-20."),
           ("PJ-RWQ-2", "Eastern Schools Package 2", "ongoing", 1, "L3", "Eastern Schools Projects Company", EMP2, "Gulfline Consulting Engineers",
            "Four schools", "Dammam", 260.0, 260.0, "2025-02-01", "2027-06-30", "2027-06-30", 0, 0, 46.0, 48.0, 119.6, 108.0, 4.2, 12.0, 8.0, 19,
            "2026-09-15", "2026-09-30", 15, 0, 0, "PB 10%", "Monthly certificates, 45 days", 6.5, "On programme within 2 pp of plan; receipts current.")]
    pcols = ("project_id", "project_name", "status", "financed_flag", "limit_id", "employer", "employer_entity_id", "consultant", "scope", "location",
             "contract_value_original_mn", "contract_value_revised_mn", "start_date", "completion_original", "completion_revised", "eot_days",
             "eot_formalised_flag", "work_done_pct", "planned_pct", "billed_mn", "received_mn", "due_mn", "retention_mn", "advance_mn", "last_cert_no",
             "last_cert_date", "last_payment_date", "payment_delay_days", "pending_certs_n", "demand_letter_flag", "lg_requirements", "payment_terms",
             "expected_margin_pct", "narrative")
    for p in prj:
        d = dict(zip(pcols, p))
        d["backlog_mn"] = round(d["contract_value_revised_mn"] - d["billed_mn"], 1)
        add("dd_project", proposal_id=pid, obligor_id=SUBJ, main_contractor="", **d)
    cols = ("revenue_mn", "gross_profit_mn", "operating_profit_mn", "net_profit_mn", "ebitda_mn", "finance_cost_mn", "total_assets_mn",
            "current_assets_mn", "cash_mn", "receivables_mn", "retention_receivables_mn", "contract_assets_mn", "inventory_mn",
            "due_from_related_mn", "current_liabilities_mn", "due_to_related_mn", "intangibles_mn", "shareholder_accounts_mn",
            "noncore_investments_mn", "bank_debt_st_mn", "bank_debt_lt_mn", "total_liabilities_mn", "net_worth_mn",
            "contingent_liabilities_mn", "operating_cash_flow_mn", "cash_cycle_days", "ageing_0_90_mn", "ageing_91_180_mn",
            "ageing_181_365_mn", "ageing_over_365_mn", "top1_receivable_pct", "top2_receivable_pct", "top5_receivable_pct", "backlog_mn")
    fd = [("FY2023", 2023, "audited", "2023-12-31", 12, (300.0, 36.0, 21.0, 9.8, 33.0, 8.1, 352.0, 288.0, 14.0, 152.0, 22.0, 61.0, 18.0, 41.0, 208.0, 6.0,
                                                        0.0, 0.0, 4.0, 84.0, 36.0, 250.0, 102.0, 166.0, 18.0, 142, 104.0, 26.0, 14.0, 8.0, 24.0, 41.0, 66.0, 610.0)),
          ("FY2024", 2024, "audited", "2024-12-31", 12, (330.0, 38.6, 22.8, 9.9, 36.0, 9.4, 389.0, 322.0, 12.0, 178.0, 25.0, 66.0, 19.0, 52.0, 231.0, 6.0,
                                                        0.0, 0.0, 4.0, 92.0, 40.0, 279.0, 110.0, 181.0, 9.0, 151, 118.0, 33.0, 17.0, 10.0, 25.0, 43.0, 68.0, 640.0)),
          ("FY2025", 2025, "audited", "2025-12-31", 12, (360.0, 41.4, 24.5, 9.2, 38.0, 10.8, 431.0, 362.0, 10.0, 210.0, 29.0, 70.0, 20.0, 64.0, 254.0, 7.0,
                                                        0.0, 0.0, 4.0, 104.0, 46.0, 313.0, 118.0, 196.0, -6.0, 163, 132.0, 40.0, 24.0, 14.0, 26.0, 45.0, 70.0, 655.0)),
          ("6M2026", 2026, "interim", "2026-06-30", 6, (171.0, 19.3, 11.0, 3.6, 18.2, 6.1, 448.0, 377.0, 8.0, 219.0, 31.0, 72.0, 21.0, 66.0, 266.0, 7.0,
                                                       0.0, 0.0, 4.0, 110.0, 44.0, 327.0, 121.0, 201.0, -3.0, 171, 136.0, 41.0, 26.0, 16.0, 26.0, 46.0, 71.0, 670.0))]
    for lab, yr, kind, end, mo, vals in fd:
        add("dd_financials_detail", proposal_id=pid, entity_id=SUBJ, entity_name=NAME, entity_scope="subject", period_label=lab, year=yr,
            period_kind=kind, period_end=end, months=mo, currency="SAR", auditor="Harbour Gate Auditors" if kind == "audited" else "",
            auditor_panel="listed" if kind == "audited" else "", opinion="clean" if kind == "audited" else "unaudited", qualification_basis="",
            staff_count=1180, source="Audited financial statements" if kind == "audited" else "Interim management accounts as per business",
            **dict(zip(cols, vals)))
    for i, (kind, lab, sh, val, yr, txt, att) in enumerate([
            ("activity_mix", "Residential buildings", 61.0, 219.6, 2025, "Residential buildings 61% of FY2025 revenue (FY2024 58%).", "audited"),
            ("activity_mix", "Education and public buildings", 39.0, 140.4, 2025, "Education and public buildings 39% (FY2024 42%).", "audited"),
            ("sales_terms", "Sales terms", None, None, 2026, "Monthly certified payment certificates paid in 45 days; 10% retention released 12 months after handover; 10% advance recovered pro rata.", "verified"),
            ("purchase_terms", "Purchase terms", None, None, 2026, "Steel and cement on 60-90 days open account; 30% of purchases from the sister ready-mix company.", "as_per_business"),
            ("top_customer", "Al Bariq Developments Company", 42.0, 275.0, 2026, "Al Bariq Developments Company 42% of the backlog (SAR 275.0m of SAR 655.0m).", "verified"),
            ("staff", "Staff", None, None, 2026, "1,180 staff, of which 940 site labour, as per business.", "as_per_business"),
            ("geopolitical", "Input costs", None, None, 2026, "Business conveys steel prices rose 11% in 2026 and contracts carry no escalation clause.", "as_per_business")]):
        add("dd_business_profile", proposal_id=pid, item_id=f"BP{i + 1}", entity_id=SUBJ, item_kind=kind, label=lab, share_pct=sh, value_mn=val, year=yr,
            text=txt, attribution=att)
    # 24 months of conduct (Oct 2024 - Sep 2026): credit turnover about SAR 300m a year; 4 returned cheques in the last 12 months
    Dm.conduct(pid, SUBJ, "2024-10", 24, base_turnover=24.0, growth=0.002, limits=150.0, util=(0.78, 0.92), routed_share=0.55,
               returned={"2025-11": (1, 0.6), "2026-02": (1, 1.1), "2026-05": (1, 0.9), "2026-08": (1, 0.7)}, past_due={"2026-07": (12, 1.4)},
               avg_bal=(9.0, 3.0), months_out=15)
    Dm.bureau_rows(pid, [
        (SUBJ, NAME, "company", "2026-10-06", 1, "", 9, 286.0, 0.0, 0, 4, 3.3, "2025-11-10;2026-02-10;2026-05-10;2026-08-10", 602, 0, 0.0, "current", "Four returned cheques in 12 months (SAR 3.3m)"),
        (PARENT, "Ruwaq Holding Company", "company", "2026-10-06", 1, "", 2, 18.0, 0.0, 0, 0, 0.0, "", 655, 0, 0.0, "current", ""),
        (SISTER, "Ruwaq Ready-Mix Company", "company", "2026-10-06", 1, "", 3, 39.0, 0.0, 0, 0, 0.0, "", 640, 0, 0.0, "current", ""),
        (RELCO, "Ruwaq Real Estate Development Company", "company", "2026-10-06", 1, "", 2, 31.0, 2.4, 47, 1, 0.5, "2026-06-18", 548, 1, 1.9, "30 days", "One court case by a supplier (SAR 1.9m)"),
        (UBO, "Sultan Hamad Al-Ruwaqi", "ubo", "", 0, "Not provided: requested on 13 Oct 2026 (CFR-2026-0611)", None, None, None, None, None, None, "", None, None, None, "", "")])
    for eid, nm, fl, fo, nl, no, banks, cls in [(SUBJ, NAME, 110.0, 92.0, 210.0, 168.0, 3, "regular"),
                                                 (SISTER, "Ruwaq Ready-Mix Company", 40.0, 31.0, 10.0, 8.0, 2, "regular"),
                                                 (RELCO, "Ruwaq Real Estate Development Company", 35.0, 31.0, 0.0, 0.0, 1, "watch")]:
        add("bureau_cbrbr", proposal_id=pid, entity_id=eid, entity_name=nm, report_date="2026-09-30", funded_limit_mn=fl, funded_outstanding_mn=fo,
            non_funded_limit_mn=nl, non_funded_outstanding_mn=no, total_limit_mn=fl + nl, total_outstanding_mn=fo + no, banks_n=banks, classification=cls)
    for bank, eid, nm, ft, dl, do, bl, bo, fal, fd_, secu, note, clar in [
            ("Coastal Commerce Bank", SUBJ, NAME, "PB;APG;OD", 90.0, 71.0, 90.0, 72.0, 1, "2026-02-11", "Parent CG", "Agrees within SAR 1.0m.", 1),
            ("Red Sea Investment Bank", SUBJ, NAME, "LC;STL", 40.0, 28.0, 40.0, 29.5, 1, "2025-12-02", "Parent CG", "Agrees within SAR 1.5m.", 1)]:
        add("other_bank_facility", proposal_id=pid, bank_name=bank, entity_id=eid, entity_name=nm, facility_types=ft, declared_limit_mn=dl,
            declared_outstanding_mn=do, bureau_limit_mn=bl, bureau_outstanding_mn=bo, difference_mn=round(bo - do, 2), fal_provided_flag=fal,
            fal_date=fd_, security_text=secu, reconciliation_note=note, clarified_flag=clar)
    Dm.docs(pid, "contracting", "renewal_and_increase", {SUBJ: NAME, PARENT: "Ruwaq Holding Company", SISTER: "Ruwaq Ready-Mix Company",
                                                          RELCO: "Ruwaq Real Estate Development Company"},
            ubos={UBO: "Sultan Hamad Al-Ruwaqi"}, guarantors={PARENT: "Ruwaq Holding Company", UBO: "Sultan Hamad Al-Ruwaqi"},
            banks=["Coastal Commerce Bank", "Red Sea Investment Bank"],
            projects={"PJ-RWQ-1": "Al Bariq Residences", "PJ-RWQ-2": "Eastern Schools Package 2"},
            missing={("bureau_ubo", UBO): ("pending", "Requested on 13 Oct 2026 (CFR-2026-0611)"),
                     ("payment_certificate", "PJ-RWQ-1"): ("pending", "Two certificates certified and not paid; copies not provided")})
    Dm.flow(pid, [("", "draft", RM, "rm", "2026-10-10T08:00:00Z", "Drafted by the RM in the bank form."),
                  ("draft", "submitted", RM, "rm", "2026-10-12T11:40:00Z", "Submitted to credit.")])
    Dm.conds(pid, [
        ("CO-RWQ-1", "L2", "reporting", "Submit quarterly project status reports with certified payment certificates.", "RM", "2026-01-31", "quarterly", "", "",
         None, None, "2026-09-30", "not_complied", "prior_approval", PRIOR_REF),
        ("CO-RWQ-2", "ALL", "reporting", "Submit audited financial statements within 120 days of year end.", "RM", "2026-04-30", "annual", "", "", None, None,
         "2026-04-21", "met", "prior_approval", PRIOR_REF),
        ("CO-RWQ-3", "ALL", "security", "Perfect the parent corporate guarantee (board resolution of the guarantor).", "Credit administration", "2026-06-30",
         "once", "", "", None, None, "2026-09-30", "not_complied", "prior_approval", PRIOR_REF)])


def rows() -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """The demo deal's rows, captured without touching the build's own demo set."""
    from backend.dealdesk.data import demo as Dm
    saved_r, saved_d = {k: list(v) for k, v in Dm.R.items()}, dict(Dm.DEALS)
    Dm.R.clear()
    Dm.DEALS.clear()
    try:
        demo_r14()
        return {k: list(v) for k, v in Dm.R.items()}, dict(Dm.DEALS)
    finally:
        Dm.R.clear()
        Dm.R.update(saved_r)
        Dm.DEALS.clear()
        Dm.DEALS.update(saved_d)


def deal_row() -> dict:
    """The dd_deal row of R14-RWQ in the build's shape (backend/dealdesk/data/build.py _deal_rows)."""
    import json
    _, deals = rows()
    d = deals[PID]
    p, h = d["proposal"], d["deal"]
    ob = p["obligor"]
    return {"proposal_id": PID, "source": "r12_demo", "obligor_id": ob["obligor_id"], "obligor_name": ob["name"], "group_id": ob["group_id"],
            "group_name": ob["group_name"], "status": p["status"], "rm": p["rm"], "business_unit": p["business_unit"], "received_date": p["received"],
            "currency": "SAR", "proposal_json": json.dumps(p, ensure_ascii=False), **h}


def all_rows() -> dict[str, list[dict]]:
    """Every relation's rows for R14-RWQ: the demo rows, its dd_deal row and its engine-computed rating-notch stress rows."""
    from backend.dealdesk.data import build
    R, deals = rows()
    out = {k: list(v) for k, v in R.items()}
    out["dd_deal"] = [deal_row()]
    out["dd_stress_result"] = build._engine_rows_for(deals) if hasattr(build, "_engine_rows_for") else _notch_rows(deals)
    return out


def _notch_rows(deals: dict) -> list[dict]:
    from backend.dealdesk import engine, params
    from backend.dealdesk.seed import GRADES
    pv = params.version_tag()
    out = []
    for pid, d in deals.items():
        p = d["proposal"]
        for n, sev in ((1, "mild"), (2, "moderate"), (3, "severe")):
            a = engine.analyse(p, shocks={"notches": n}, validate=False)
            m = a["metrics"]
            r = GRADES[min(len(GRADES) - 1, GRADES.index(p["obligor"]["internal_rating"]) + n)]
            breaks = [b for b, ok in (("dscr", m["dscr_post"] < 1.2), ("hurdle", m["lifetime_raroc"] < m["hurdle"]),
                                     ("limit", bool(a["approval"]["hard_breaches"]))) if ok]
            out.append({"result_id": f"SR-{pid}-notch_{n}", "proposal_id": pid, "run_id": "p-seed-2026-10-19", "scenario_id": f"notch_{n}",
                        "scenario_version": 1, "family": "rating", "severity": sev, "applicable_flag": 1, "revenue_change_pct": 0.0,
                        "dscr_x": round(m["dscr_post"], 4), "leverage_x": round(m["debt_ebitda_post"], 4), "rating": r,
                        "pd_12m": m["pd_12m"], "raroc_pct": round(m["lifetime_raroc"] * 100, 4),
                        "ltv_pct": None if m.get("ltv") is None else round(m["ltv"] * 100, 2),
                        "covenant_breach_flag": int(m["dscr_post"] < 1.2), "breaks": ";".join(breaks), "run_at": "2026-10-19T18:00:00Z",
                        "param_version": pv})
    return out
