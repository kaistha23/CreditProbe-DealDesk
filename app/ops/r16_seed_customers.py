"""R16 d: seed demo customers 1 and 2 (fictional) into Data Domains through the R12 store.

    python ops/r16_seed_customers.py           publish (idempotent: a relation whose R16 rows are already current is skipped)
    python ops/r16_seed_customers.py --check   exit 1 when a relation's committed R16 rows differ from what this script builds

Every row comes from the same generator as the documents (ops/r16_customers/c1.py, c2.py: spec() and bank()), so the
Bank's data and the customer's documents agree. Rows are published with backend.dealdesk.data.store.publish as a later
version of the registered relations (actor "R16-d:seed"), so `python -m backend.dealdesk.data.build --check` keeps
comparing the R12 build with version 1 and stays green. A full R12 rebuild (`python -m backend.dealdesk.data.build`)
drops these rows: run this script again afterwards. The Borrower 360 overlay (data/dealdesk/demo_customers/bank_b360/)
is written by ops/r16_customers/b360.py.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.dealdesk.data import schema as S  # noqa: E402
from backend.dealdesk.data import store  # noqa: E402
from ops.r16_customers import c1, c2  # noqa: E402

ACTOR = "R16-d:seed"
AT = "2026-10-21T16:00:00Z"
BUILD_ACTOR, BUILD_STAMP = "E:data-build", "2026-10-18T20:30:00Z"


def _fin_rows(pid: str, eid: str, name: str, sp: dict) -> list[dict]:
    out = []
    for lab, fs in sp["fs"].items():
        if lab == "FY2023":
            continue
        a = sp["audit"].get(lab, {})
        interim = lab.startswith("9M")
        out.append({"proposal_id": pid, "entity_id": eid, "entity_name": name, "entity_scope": "standalone", "period_label": lab,
                    "year": int(lab[-4:]), "period_kind": "interim" if interim else "audited", "period_end": "2026-09-30" if interim else f"{lab[-4:]}-12-31",
                    "months": 9 if interim else 12, "currency": "SAR", "auditor": a.get("auditor", ""), "auditor_panel": "listed" if a else "",
                    "opinion": "unaudited" if interim else ("clean" if a.get("opinion") == "Unqualified" else "clean"),
                    "qualification_basis": "Emphasis of matter: certified amounts overdue from a government-linked employer; EOT pending" if "emphasis" in a.get("opinion", "") else "",
                    "revenue_mn": fs["revenue"], "gross_profit_mn": fs["gross_profit"], "operating_profit_mn": fs["operating_profit"],
                    "net_profit_mn": fs["net_profit"], "ebitda_mn": fs["ebitda"], "finance_cost_mn": fs["finance_cost"], "total_assets_mn": fs["total_assets"],
                    "current_assets_mn": fs["current_assets"], "cash_mn": fs["cash"], "receivables_mn": fs["trade_receivables"],
                    "retention_receivables_mn": fs.get("retention_receivables", 0.0), "contract_assets_mn": fs.get("contract_assets", 0.0),
                    "inventory_mn": fs["inventory"], "due_from_related_mn": fs["due_from_related"], "current_liabilities_mn": fs["current_liabilities"],
                    "due_to_related_mn": fs["due_to_related"], "intangibles_mn": 0.0, "shareholder_accounts_mn": 0.0, "noncore_investments_mn": 0.0,
                    "bank_debt_st_mn": round(fs["short_term_borrowings"] + fs["current_portion_ltd"], 3), "bank_debt_lt_mn": fs["long_term_borrowings"],
                    "total_liabilities_mn": fs["total_liabilities"], "net_worth_mn": fs["total_equity"], "contingent_liabilities_mn": None,
                    "operating_cash_flow_mn": fs.get("operating_cash_flow"), "cash_cycle_days": None,
                    "staff_count": sp["co"]["nitaqat"]["total"],
                    "source": "In-house management accounts (unaudited)" if interim else f"Audited financial statements {lab} ({a.get('auditor', '')})"})
    if "c2" == sp["key"]:
        ag = {r["customer"]: r for r in sp["rec_ageing"]["rows"]}
        tot = sum(sum(r[k] for k in ("b0_90", "b91_180", "b181_365", "over_365")) for r in ag.values())
        top = max(sum(r[k] for k in ("b0_90", "b91_180", "b181_365", "over_365")) for r in ag.values())
        m9 = out[-1]
        m9.update({"ageing_0_90_mn": round(sum(r["b0_90"] for r in ag.values()), 3), "ageing_91_180_mn": round(sum(r["b91_180"] for r in ag.values()), 3),
                   "ageing_181_365_mn": round(sum(r["b181_365"] for r in ag.values()), 3), "ageing_over_365_mn": round(sum(r["over_365"] for r in ag.values()), 3),
                   "top1_receivable_pct": round(100 * top / tot, 1), "backlog_mn": 705.4, "contingent_liabilities_mn": 125.0})
    else:
        ag = sp["rec_ageing"]["rows"]
        tot = sum(sum(r[k] for k in ("b0_90", "b91_180", "b181_365", "over_365")) for r in ag)
        top = sum(ag[0][k] for k in ("b0_90", "b91_180", "b181_365", "over_365"))
        out[-1].update({"ageing_0_90_mn": round(sum(r["b0_90"] for r in ag), 3), "ageing_91_180_mn": round(sum(r["b91_180"] for r in ag), 3),
                        "ageing_181_365_mn": round(sum(r["b181_365"] for r in ag), 3), "ageing_over_365_mn": 0.0,
                        "top1_receivable_pct": round(100 * top / tot, 1), "contingent_liabilities_mn": 21.5})
    return out


def _proposal(key: str, sp: dict, b: dict, P: dict) -> dict:
    from backend.dealdesk.data import demo
    fs = sp["fs"]
    years = []
    for lab in ("FY2023", "FY2024", "FY2025"):
        f = fs[lab]
        debt = f["short_term_borrowings"] + f["current_portion_ltd"] + f["long_term_borrowings"]
        years.append((int(lab[2:]), "actual", f["revenue"], f["ebitda"], round(debt, 3), round(f["finance_cost"] + f["current_portion_ltd"], 3),
                      f["total_equity"], round(f["current_assets"] / f["current_liabilities"], 2), "audited"))
    if key == "c1":
        ask = {"facility_type": "revolver", "structure": "murabaha", "amount": 95, "tenor_years": 1, "margin_bps": 175, "upfront_fee_bps": 20,
               "funded_share_pct": 64, "unfunded_type": "performance_lg", "utilisation_pct": 80, "amortisation": "bullet", "guarantee_id": "G1",
               "guarantee_coverage_pct": 100, "commission_bps": 60}
        guar = [{"guarantee_id": "G1", "type": "personal", "guarantor": "Fahad Saad Al-Naseem", "guarantor_rating": "BBB-", "coverage_pct": 100,
                 "offered_in_ask": True}]
        coll = [{"collateral_id": "C1", "type": "real_estate", "value": 31.5, "currency": "SAR", "valuation_date": "2025-08-14", "pledged_in_ask": True}]
        prop = demo.proposal("R16-C1", name=sp["co"]["name"], oid=b["cif"], sector="Wholesale Trade", sub="Medical Supplies Distribution", rating="BBB",
                             group_id="CG9001", group_name="Naseem Holding Group", existing=True, region="Riyadh", sector_code="G4646", rm=b["rm"],
                             received="2026-10-13", case="renewal", purpose="Existing working-capital facilities approved under CC/2025/031; annual renewal due 30/11/2026",
                             years=years, existing_exposure=101.5, collateral=coll, guarantees=guar, status="approved", connected=["CB09005", "CB09004"], ask=ask)
    else:
        ask = {"facility_type": "performance_lg", "structure": "conventional", "amount": 160, "tenor_years": 1, "margin_bps": 0, "commission_bps": 70,
               "upfront_fee_bps": 25, "funded_share_pct": 44, "unfunded_type": "performance_lg", "utilisation_pct": 100, "amortisation": "bullet",
               "guarantee_id": "G1", "guarantee_coverage_pct": 100}
        guar = [{"guarantee_id": "G1", "type": "personal", "guarantor": "Turki Hamad Al-Sawaed", "guarantor_rating": "BB", "coverage_pct": 100,
                 "offered_in_ask": True}]
        prop = demo.proposal("R16-C2", name=sp["co"]["name"], oid=b["cif"], sector="Construction", sub="Building and Infrastructure Contracting", rating="BB+",
                             group_id="CG9002", group_name="Sawaed Group", existing=True, region="Eastern Province", sector_code="F4100", rm=b["rm"],
                             received="2026-10-06", case="renewal_and_new", purpose="Existing general limit approved under CC/2024/207; annual renewal due 30/11/2026",
                             years=years, existing_exposure=178.0, guarantees=guar, status="approved", connected=["CB09003"], ask=ask,
                             covenants=[{"type": "DSCR", "threshold": 1.2}, {"type": "Net debt / EBITDA", "threshold": 5.0}])
    prop["obligor"]["cr_number"] = sp["co"]["cr_number"]
    prop["source"] = "r16_customer"
    return prop


def build() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}

    def add(rel, items):
        rows.setdefault(rel, []).extend(items)
    for key, mod in (("c1", c1), ("c2", c2)):
        sp = mod.spec()
        b = mod.bank(sp)
        P = mod.proposal_text(sp, b)
        pid, cif = b["proposal_id"], b["cif"]
        lim0 = b["limits"][0]
        ge_total = sum(g["total_existing_mn"] for g in b["group_exposure"])
        cap = {"c1": (110.0, 155.0), "c2": (185.0, 300.0)}[key]
        add("dd_deal", [{"proposal_id": pid, "source": "r12_demo", "product": "corporate" if key == "c1" else "contracting",
                         "deal_name": f"{sp['co']['short']} — customer file", "obligor_id": cif, "obligor_name": sp["co"]["name"],
                         "group_id": sp["co"]["group_id"], "group_name": sp["co"]["group_name"], "case_type": "renewal" if key == "c1" else "renewal_and_new",
                         "status": "approved", "workflow_state": "approved", "rm": b["rm"], "credit_analyst": "", "business_unit": "Corporate Banking", "branch": b["branch"],
                         "received_date": P["header"]["date"], "committee_date": "", "approval_authority": P["authority"], "currency": "SAR",
                         "existing_limits_mn": lim0["existing_mn"], "proposed_limits_mn": lim0["existing_mn"], "group_exposure_mn": ge_total,
                         "group_cap_existing_mn": cap[0], "group_cap_proposed_mn": cap[0], "rating_existing": b["rating_existing"], "rating_proposed": b["rating_existing"],
                         "cif": cif, "group_no": sp["co"]["group_id"], "account_opened_date": b["opened"], "related_party_flag": 1,
                         "related_party_cif": b["connected"]["cif"], "purpose_code": b["purpose_code"], "industry_code": b["industry_code"].split(" ")[0],
                         "collateral_code": b["collateral_code"], "review_date": b["review_date"], "ao": b["rm"], "ro": b["ro"],
                         "proposal_json": json.dumps(_proposal(key, sp, b, P), ensure_ascii=False)}])
        # the Bank's file holds the existing limits; the ask arrives with the RM's request / the uploaded business request
        lims = []
        for L in b["limits"]:
            L = dict(L)
            L["proposed_mn"] = L["existing_mn"]
            lims.append(L)
        lims = [L for L in lims if L["existing_mn"] > 0 or L["level"] == 0]
        add("dd_facility_limit", lims)
        keep = {L["limit_id"] for L in lims} | {"ALL"}
        add("dd_security", [s for s in b["security"] if s["existing_flag"] == 1 and s["limit_id"] in keep])
        add("dd_tnc", [t for t in b["tnc"] if t["existing_status"] != "new" and t["limit_id"] in keep])
        add("dd_reference", b["references"])
        add("dd_group_exposure", [dict(g, funded_proposed_mn=g["funded_existing_mn"], total_proposed_mn=g["total_existing_mn"]) for g in b["group_exposure"]])
        add("dd_account_conduct", b["conduct"])
        add("dd_returned_cheque", b["returned_cheques"])
        add("dd_customer_account", b["accounts"])
        add("b360_entity", b["entities"])
        add("b360_edge", b["edges"])
        add("b360_shareholder", b["holders"])
        add("b360_board", b["board"])
        subj = b["entities"][1 if key == "c1" else 0]["entity_id"]
        add("dd_financials_detail", _fin_rows(pid, subj, sp["co"]["name"], sp))
        # bureau as the Bank holds it (consistent with the SIMAH documents)
        sc = sp["simah_company"]
        fac = sc["facilities"]
        rep = [{"report_id": f"BR-{pid}-CO", "proposal_id": pid, "entity_id": subj, "entity_name": sp["co"]["name"], "entity_kind": "company", "bureau": "SIMAH",
                "report_date": sc["date"], "provided_flag": 1, "not_provided_reason": "", "facilities_n": len(fac),
                "outstanding_mn": round(sum(x["outstanding"] for x in fac), 3), "overdue_mn": 0.0, "overdue_days_max": 0, "returned_cheques_n": 0,
                "returned_cheques_mn": 0.0, "returned_cheque_dates": "", "score": sc["score"], "court_cases_n": 0, "court_cases_mn": 0.0,
                "worst_status": "current", "note": sc.get("enquiry_text", "")}]
        for i, p in enumerate(sp["people"], 1):
            s = p["simah"]
            bad = [g for g in s.get("guarantees", []) if g["status"] != "Current"]
            rep.append({"report_id": f"BR-{pid}-P{i}", "proposal_id": pid, "entity_id": f"XP-{key.upper()}-0{i}", "entity_name": p["name"],
                        "entity_kind": "guarantor", "bureau": "SIMAH", "report_date": s["date"], "provided_flag": 1, "not_provided_reason": "",
                        "facilities_n": len(s["facilities"]), "outstanding_mn": round(sum(x["outstanding"] for x in s["facilities"]), 3),
                        "overdue_mn": 0.0, "overdue_days_max": 0 if not bad else (89 if key == "c2" else 120), "returned_cheques_n": 0,
                        "returned_cheques_mn": 0.0, "returned_cheque_dates": "", "score": s["score"], "court_cases_n": 0, "court_cases_mn": 0.0,
                        "worst_status": s["worst"], "note": "; ".join(f"Guarantee of {g['beneficiary']} at {g['lender']}: {g['status']}" for g in bad)})
        add("bureau_entity_report", rep)
        ours = [x for x in fac if x["lender"] == c1.BANK]
        nf = ("Letters of credit", "Letters of guarantee", "Performance bonds", "Advance payment guarantees", "Letters of credit (incl. acceptances)")
        fl = sum(x["limit"] for x in fac if x["product"] not in nf)
        fo = sum(x["outstanding"] for x in fac if x["product"] not in nf)
        add("bureau_cbrbr", [{"proposal_id": pid, "entity_id": subj, "entity_name": sp["co"]["name"], "report_date": sc["date"],
                              "funded_limit_mn": round(fl, 3), "funded_outstanding_mn": round(fo, 3),
                              "non_funded_limit_mn": round(sum(x["limit"] for x in fac) - fl, 3), "non_funded_outstanding_mn": round(sum(x["outstanding"] for x in fac) - fo, 3),
                              "total_limit_mn": round(sum(x["limit"] for x in fac), 3), "total_outstanding_mn": round(sum(x["outstanding"] for x in fac), 3),
                              "banks_n": len({x["lender"] for x in fac}), "classification": "regular"}])
        del ours
        obs = []
        for ob in sp["other_banks"]:
            lim = sum(x["limit"] for x in ob["facilities"])
            out = sum(x["outstanding"] for x in ob["statement"])
            bl = sum(x["limit"] for x in fac if x["lender"] == ob["bank"])
            bo = sum(x["outstanding"] for x in fac if x["lender"] == ob["bank"])
            obs.append({"proposal_id": pid, "bank_name": ob["bank"], "entity_id": subj, "entity_name": sp["co"]["name"],
                        "facility_types": "; ".join(x["facility"] for x in ob["facilities"]), "declared_limit_mn": round(lim, 3), "declared_outstanding_mn": round(out, 3),
                        "bureau_limit_mn": round(bl, 3), "bureau_outstanding_mn": round(bo, 3), "difference_mn": round(bo - out, 3), "fal_provided_flag": 1,
                        "fal_date": ob["offer_date"], "security_text": ob["security"], "reconciliation_note": "Statement reconciles with the bureau.", "clarified_flag": 1})
        add("other_bank_facility", obs)
        top = sp["top"]["customers"]
        add("dd_business_profile", [{"proposal_id": pid, "item_id": f"BP-{key}-{i}", "entity_id": subj, "item_kind": "top_customer", "label": t["name"],
                                     "share_pct": t["share"], "value_mn": t["sales"], "year": sp["top"]["year"],
                                     "text": f"{t['name']}: {t['share']:.1f}% of FY{sp['top']['year']} sales, terms {t['terms']} ({t['relationship']}, as per business).",
                                     "attribution": "as_per_business"} for i, t in enumerate(top, 1)])
        if key == "c2":
            prj = []
            for p in sp["projects"]["rows"]:
                ip = sp["ipcs"] if p.get("contract") else []
                paid = [i for i in ip if i["paid"]]
                unpaid = [i for i in ip if not i["paid"]]
                prj.append({"project_id": f"PJ-C2-{p['id']}", "proposal_id": pid, "obligor_id": cif, "project_name": p["name"], "status": p["status"],
                            "financed_flag": 1 if p["id"] == "P1" else 0, "limit_id": "G4" if p["id"] == "P1" else "", "employer": p["employer"],
                            "employer_entity_id": "XE-C2-04" if p["id"] == "P1" else "", "main_contractor": sp["co"]["name"], "consultant": p.get("consultant", ""),
                            "scope": p["name"], "location": "Eastern Province", "contract_value_original_mn": p["value"], "contract_value_revised_mn": p["value"],
                            "start_date": p["start"], "completion_original": p.get("completion_contract", p["completion_shown"]), "completion_revised": p["completion_shown"],
                            "eot_days": 153 if p["id"] == "P1" else 0, "eot_formalised_flag": 0 if p["id"] == "P1" else 1, "work_done_pct": p["done_pct"],
                            "planned_pct": 63.0 if p["id"] == "P1" else p["done_pct"], "billed_mn": p["billed"], "received_mn": p["received"],
                            "due_mn": round(sum(i["net"] for i in unpaid), 3) if ip else None, "retention_mn": p["retention"],
                            "advance_mn": 48.6 if p["id"] == "P1" else None, "last_cert_no": ip[-1]["k"] if ip else None, "last_cert_date": ip[-1]["certified"] if ip else "",
                            "last_payment_date": paid[-1]["paid"] if paid else "", "payment_delay_days": 129 if ip else 0, "pending_certs_n": len(unpaid),
                            "demand_letter_flag": 0, "lg_requirements": "APG 10%, PB 10%" if ip else "", "payment_terms": "56 days from certification" if ip else "",
                            "expected_margin_pct": None, "backlog_mn": round(p["value"] * (1 - p["done_pct"] / 100), 3),
                            "narrative": "Certificates IPC-08 to IPC-11 paid 118-129 days after due; IPC-12 to IPC-17 unpaid; EOT of five months requested 14/04/2026, not approved in writing." if ip else ""})
            add("dd_project", prj)
    return rows


def _norm(df):
    df = df.drop(columns=[c for c in ("rel_version", "published_at") if c in df.columns]).copy()
    return json.dumps(sorted(df.astype(object).where(df.notna(), None).to_dict("records"), key=lambda r: json.dumps(r, sort_keys=True, default=str)),
                      sort_keys=True, default=str)


def run(check: bool = False) -> int:
    rows = build()
    changed = []
    for rel, items in rows.items():
        spec = S.RELATIONS[rel]
        keys = spec["keys"]
        new = store.conform(rel, items)
        new[S.PERIOD] = new[S.PERIOD].fillna(S.AS_OF)
        cur = store.dd_frame(rel)
        kset = {tuple(str(r[k]) for k in keys) for r in new[keys].astype(str).to_dict("records")}
        mine = cur[[tuple(str(v) for v in t) in kset for t in cur[keys].astype(str).itertuples(index=False, name=None)]] if len(cur) else cur
        if len(mine) == len(new) and _norm(mine.reindex(columns=new.columns)) == _norm(new):
            continue
        changed.append(rel)
        if check:
            continue
        man = store.read_manifest(spec["folder"]).get("relations", {})
        if rel not in man:   # a new R16 relation: version 1 is the R12 build's (empty), as `build --check` expects
            store.publish(rel, [], mode="replace", actor=BUILD_ACTOR, at=BUILD_STAMP)
        store.publish(rel, items, mode="upsert", actor=ACTOR, at=AT)
        print(f"published {rel}: {len(items)} rows")
    if check:
        print("R16 SEED CHECK", "PASS" if not changed else f"FAIL {changed}")
        return 1 if changed else 0
    from backend.dealdesk.data import contract
    contract.main()
    print("R16 seed:", "nothing to do" if not changed else f"{len(changed)} relations updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(run("--check" in sys.argv))
