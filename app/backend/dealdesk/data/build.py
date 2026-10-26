"""R12 Session E: build every R12 relation (python3 -m backend.dealdesk.data.build [--check]).

    --schema   write every relation empty (the SCHEMA READY state)
    (default)  populate the fictional demo data (DATA READY) and regenerate the contract document
    --check    rebuild into a scratch root and compare content hashes with the committed manifests

Sources, in order:
  1. the PL set, moved from data/dealdesk/pipeline/pipeline.json into dd_pipeline (the one place that file is read;
     backend.dealdesk.pipeline reads dd_pipeline through the readers);
  2. the deal register dd_deal over DD-01..15 (proposals.json), PL-01..27 and the R12 demo deals (demo.py);
  3. the R12 demo deals' relations (demo.py);
  4. seeds from the versioned parameter tables: dd_stress_scenario and dd_stress_sensitivity (params/v1/
     stress_scenarios.json), dd_parameter_provenance (dd_parameter), dd_policy and dd_policy_clause (the fictional
     Sandstone Harbour Bank policy in demo_inputs/policy), dd_document_rule;
  5. engine-computed rows: the rating-notch stress family for the R12 demo deals (dd_stress_result) and the RAROC drift
     of twin A's renewed limits (dd_raroc_drift).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any

from backend.dealdesk.data import schema as S

V5 = pathlib.Path(__file__).resolve().parents[3]
STAMP = "2026-10-18T20:30:00Z"   # fixed publish time of the demo build, so a rebuild is byte-stable
ACTOR = "E:data-build"


def _pipeline_rows() -> list[dict[str, Any]]:
    src = V5 / "data" / "dealdesk" / "pipeline" / "pipeline.json"
    props = json.loads(src.read_text())["proposals"]
    out = []
    for p in props:
        ob, a = p["obligor"], p["ask"]
        out.append({"proposal_id": p["proposal_id"], "status": p["status"], "rm": p["rm"], "business_unit": p["business_unit"],
                    "received_date": p["received"], "purpose": p.get("purpose", ""), "obligor_id": ob["obligor_id"],
                    "obligor_name": ob["name"], "existing_flag": int(bool(ob.get("existing"))), "sector": ob["sector"],
                    "sub_sector": ob.get("sub_sector", ""), "region": ob.get("region", ""), "internal_rating": ob["internal_rating"],
                    "group_id": ob.get("group_id", ""), "group_name": ob.get("group_name", ""), "facility_type": a["facility_type"],
                    "structure": a["structure"], "currency": a["currency"], "amount": float(a["amount"]), "tenor_years": int(a["tenor_years"]),
                    "margin_bps": float(a["margin_bps"]), "existing_ead_sar_mn": float(ob.get("existing_exposure_sar_mn", 0.0)),
                    "proposal_json": json.dumps(p, ensure_ascii=False)})
    return out


_PRODUCT_OF = {"performance_lg": "contracting"}


def _deal_rows(pipeline: list[dict[str, Any]], demo_deals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    seeded = json.loads((V5 / "data" / "dealdesk" / "proposals.json").read_text())["proposals"]
    rows = []
    for src, items in (("deal_desk", seeded), ("pipeline", [json.loads(r["proposal_json"]) for r in pipeline])):
        for p in items:
            ob, a = p["obligor"], p["ask"]
            prod = "sme" if ob.get("sme") else _PRODUCT_OF.get(a["facility_type"], "corporate")
            rows.append({"proposal_id": p["proposal_id"], "source": src, "product": prod,
                         "deal_name": f"{ob['name']} — {a['facility_type'].replace('_', ' ')}", "obligor_id": ob["obligor_id"],
                         "obligor_name": ob["name"], "group_id": ob.get("group_id", ""), "group_name": ob.get("group_name", ""),
                         "case_type": "renewal" if ob.get("existing") else "new", "status": p["status"],
                         "workflow_state": {"new": "submitted", "in_review": "in_review", "counter_offered": "in_review",
                                            "approved": "approved", "declined": "declined"}.get(p["status"], "submitted"),
                         "rm": p["rm"], "business_unit": p["business_unit"], "received_date": p["received"], "currency": a["currency"],
                         "existing_limits_mn": float(ob.get("existing_exposure_sar_mn") or 0.0),
                         "proposed_limits_mn": float(a["amount"]) * (1.0 if a["currency"] == "SAR" else 3.75),
                         "rating_existing": ob["internal_rating"] if ob.get("existing") else "", "rating_proposed": ob["internal_rating"],
                         "industry_code": ob.get("sector_code", ""), "related_party_flag": int(bool(ob.get("connected_parties"))),
                         "proposal_json": ""})
    for pid, d in demo_deals.items():
        p, h = d["proposal"], d["deal"]
        ob = p["obligor"]
        rows.append({"proposal_id": pid, "source": "r12_demo", "obligor_id": ob["obligor_id"], "obligor_name": ob["name"],
                     "group_id": ob["group_id"], "group_name": ob["group_name"], "status": p["status"], "rm": p["rm"],
                     "business_unit": p["business_unit"], "received_date": p["received"], "currency": "SAR",
                     "proposal_json": json.dumps(p, ensure_ascii=False), **h})
    return rows


def _stress_seed() -> tuple[list[dict], list[dict]]:
    ss = json.loads((V5 / "data" / "dealdesk" / "params" / "v1" / "stress_scenarios.json").read_text())
    fam = {"macro": "macro", "sector": "macro", "obligor": "borrower", "collateral": "collateral", "rating": "rating",
           "combined": "combined", "custom": "custom"}
    scen = [{"scenario_id": s["id"], "version": 1, "family": fam.get(s["group"], s["group"]), "severity": s.get("severity", ""),
             "label": s["label"], "scope": "bank", "proposal_id": "", "shocks_json": s.get("shocks") or {k: s[k] for k in ("compose", "sector_scenario") if k in s}, "source": "seed",
             "owner": ss["owner"], "status": "approved", "maker": ss["owner"], "checker": ss.get("approved_by", ""),
             "effective_date": ss["effective_from"]} for s in ss["scenarios"]]
    sens = []
    for driver, spec in ss["transmission"].items():
        if not isinstance(spec, dict) or "by_sector" not in spec:
            continue
        for sector, beta in [("default", spec["default"])] + sorted(spec["by_sector"].items()):
            sens.append({"sensitivity_id": f"{sector}:{driver}", "version": 1, "sector": sector, "driver": driver, "beta": float(beta),
                         "method": "expert", "source": spec.get("basis", "Risk Models assumption")[:300], "owner": ss["owner"],
                         "effective_date": ss["effective_from"], "model_card_ref": ""})
    for s in ss["scenarios"]:
        rv = (s.get("shocks") or {}).get("revenue_pct")
        drv = {"oil_30": ("oil", -0.30), "gdp_3": ("non_oil_gdp", -0.03)}.get(s["id"])
        if drv and isinstance(rv, dict):
            for sector, v in [("default", rv["default"])] + sorted(rv["by_sector"].items()):
                sens.append({"sensitivity_id": f"{sector}:{drv[0]}", "version": 1, "sector": sector, "driver": drv[0],
                             "beta": round(float(v) / drv[1], 4), "method": "expert", "source": s.get("basis", "")[:300],
                             "owner": ss["owner"], "effective_date": ss["effective_from"], "model_card_ref": ""})
    return scen, sens


def _provenance() -> list[dict]:
    import pandas as pd
    p = pd.read_parquet(V5 / S.DD_DIR / "dd_parameter.parquet")
    return [{"table_name": r.table_name, "param_key": r.param_key, "param_version": str(r.version), "source_kind": "seed",
             "set_by": r.owner, "set_on": str(r.effective_date)[:10]} for r in p.itertuples()]


def _policy() -> tuple[list[dict], list[dict]]:
    f = V5 / "demo_inputs" / "policy" / "Fictional_Bank_Credit_Policy.docx"
    from docx import Document
    doc = Document(str(f))
    clauses, heading = [], ""
    for para in doc.paragraphs:
        t = para.text.strip()
        if para.style.name.startswith("Heading"):
            heading = t
        m = re.match(r"^(\d+\.\d+) (.+)$", t)
        if m:
            clauses.append({"policy_id": "POL-CR-01", "version": 1, "clause": m.group(1), "heading": heading, "quote": m.group(2)[:400]})
    sets = {"4.2": ("risk_appetite", "dscr.limit", "1.25"), "4.3": ("risk_appetite", "debt_ebitda.limit", "3.5"),
            "4.5": ("risk_appetite", "balloon.limit", "0.4"), "9.1": ("returns", "hurdle", "0.12")}
    for c in clauses:
        t, k, v = sets.get(c["clause"], ("", "", ""))
        c.update(sets_table=t, sets_key=k, sets_value=v)
    pol = [{"policy_id": "POL-CR-01", "version": 1, "title": "Sandstone Harbour Bank Corporate Credit Policy v4.2 (fictional)",
            "effective_date": "2026-07-01", "uploaded_by": "Credit Risk Policy unit", "uploaded_at": "2026-07-01T08:00:00Z",
            "status": "trial", "source_file": "demo_inputs/policy/Fictional_Bank_Credit_Policy.docx",
            "docx_file": "demo_inputs/policy/Fictional_Bank_Credit_Policy.docx", "clauses_n": len(clauses),
            "summary": "Fictional corporate credit policy used for the demo: governance, application, acceptance criteria, limits, security, monitoring, pricing."}]
    return pol, clauses


def _engine_rows(demo_deals: dict[str, dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """The rating −1/−2/−3 family for every demo deal and the RAROC drift of twin A's limits (engine-computed)."""
    from backend.dealdesk import engine, params
    from backend.dealdesk.seed import GRADES
    pv = params.version_tag()
    res = []
    for pid, d in demo_deals.items():
        p = d["proposal"]
        base = engine.analyse(p)
        for n, sev in ((1, "mild"), (2, "moderate"), (3, "severe")):
            a = engine.analyse(p, shocks={"notches": n}, validate=False)
            m = a["metrics"]
            r = GRADES[min(len(GRADES) - 1, GRADES.index(p["obligor"]["internal_rating"]) + n)]
            breaks = [b for b, ok in (("dscr", m["dscr_post"] < 1.2), ("hurdle", m["lifetime_raroc"] < m["hurdle"]),
                                     ("limit", bool(a["approval"]["hard_breaches"]))) if ok]
            res.append({"result_id": f"SR-{pid}-notch_{n}", "proposal_id": pid, "run_id": "E-seed-2026-10-18", "scenario_id": f"notch_{n}",
                        "scenario_version": 1, "family": "rating", "severity": sev, "applicable_flag": 1, "revenue_change_pct": 0.0,
                        "dscr_x": round(m["dscr_post"], 4), "leverage_x": round(m["debt_ebitda_post"], 4), "rating": r,
                        "pd_12m": m["pd_12m"], "raroc_pct": round(m["lifetime_raroc"] * 100, 4),
                        "ltv_pct": None if m.get("ltv") is None else round(m["ltv"] * 100, 2),
                        "covenant_breach_flag": int(m["dscr_post"] < 1.2), "breaks": ";".join(breaks), "run_at": STAMP, "param_version": pv})
        _ = base
    # twin A: RAROC at the 2025 renewal (rating BB+, full routing realised) vs now (BB, 33% routing realised)
    p = demo_deals["R12-TWA"]["proposal"]
    import copy
    orig = copy.deepcopy(p)
    orig["obligor"]["internal_rating"] = "BB+"
    from backend.dealdesk.seed import MASTER_SCALE
    orig["obligor"]["pd_master_scale"] = MASTER_SCALE["BB+"]
    r0 = engine.analyse(orig)["metrics"]
    r_pd = engine.analyse(p)["metrics"]
    xs = copy.deepcopy(p)
    xs["business_case"]["ancillary_income_sar_mn_pa"] = {k: v * 0.33 for k, v in p["business_case"]["ancillary_income_sar_mn_pa"].items()}
    r_now = engine.analyse(xs)["metrics"]
    o, mid, now = r0["lifetime_raroc"] * 100, r_pd["lifetime_raroc"] * 100, r_now["lifetime_raroc"] * 100
    drift = [{"drift_id": "DR-TWA-ALL", "facility_id": "R12-TWA:L0", "proposal_id": "R12-TWA", "obligor_id": p["obligor"]["obligor_id"],
              "origination_date": "2025-08-20", "raroc_orig_pct": round(o, 4), "raroc_now_pct": round(now, 4), "hurdle_pct": round(r0["hurdle"] * 100, 4),
              "drift_pp": round(now - o, 4), "attr_pd_pp": round(mid - o, 4), "attr_lgd_pp": 0.0, "attr_funding_pp": 0.0, "attr_fees_pp": 0.0,
              "attr_utilisation_pp": 0.0, "attr_cross_sell_pp": round(now - mid, 4), "renewal_date": "2026-10-31"}]
    return res, drift


def build_rows() -> dict[str, list[dict[str, Any]]]:
    from backend.dealdesk.data import demo
    R, D = demo.build_all()
    out: dict[str, list[dict[str, Any]]] = {k: list(v) for k, v in R.items()}
    pl = _pipeline_rows()
    out["dd_pipeline"] = pl
    out["dd_deal"] = _deal_rows(pl, D)
    out["dd_stress_scenario"], out["dd_stress_sensitivity"] = _stress_seed()
    out["dd_parameter_provenance"] = _provenance()
    out["dd_policy"], out["dd_policy_clause"] = _policy()
    out["dd_document_rule"] = [dict(zip(("rule_id", "product", "segment", "case_type", "doc_type", "doc_label", "scope", "validity_days",
                                         "mandatory_flag", "policy_id", "clause"), r)) for r in demo.RULES]
    out["dd_stress_result"], out["dd_raroc_drift"] = _engine_rows(D)
    out.update(_scenario_rows())
    out.update(_governance_rows())
    out.update(_flow_rows())
    from backend.dealdesk.proposal_check import seed as pq_seed  # R14 p: dd_proposal_quality on the demo pack
    out["dd_proposal_quality"] = pq_seed.build_rows(out)
    out.update(_intel2_rows(out))  # R14 i
    out.update(_network_rows())  # R14 G: network_intel views, from the committed snapshot
    from backend.thread_actions import relations as ta_relations  # R16 t (M7): thread memos and actions seed
    out.update(ta_relations.demo_rows())
    from backend.dealdesk.rm_request import seed as br_seed  # R16 b: one request on a fictional seed customer; the writer adds rows at runtime
    out["dd_business_request"] = br_seed.build_rows(STAMP)
    from backend.dealdesk.intake import seed as intake_seed  # R16 i: customer-file relations (fictional demo rows)
    out.update(intake_seed.build(out))
    out.update(_credit_response_rows())  # R16 c: the committed customer-2 snapshot
    out.setdefault("dd_customer_account", [])  # R16 d: rows are a later version published by ops/r16_seed_customers.py
    return out


def _flow_rows() -> dict[str, list[dict[str, Any]]]:
    """R14 F: the deal-flow relations, computed by Session F's engines from the committed sources (deterministic):
    the ask and recommended structures of twins A and B and DD-06 (dd_structure_set), a stress-proofing run on DD-06
    (dd_stress_proof) and one monitoring proposal awaiting a checker (dd_monitoring_proposal)."""
    from backend.dealdesk.stressproof import seed
    return seed.rows(STAMP)


def _intel2_rows(rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """R14 i: open-banking / VAT turnover seed (D10) and the D6-D13 catalogue rows (backend/dealdesk/intel2/seed.py)."""
    from backend.dealdesk.intel2 import seed as i_seed
    return i_seed.build(rows)


def _credit_response_rows() -> dict[str, list[dict[str, Any]]]:
    """R16 c: dd_credit_request and dd_credit_response from the committed snapshot (backend/dealdesk/credit_response/seed_rows.json)."""
    from backend.dealdesk.credit_response import relation
    return relation.seed_rows()


def _network_rows() -> dict[str, list[dict[str, Any]]]:
    """R14 G: the published contagion and employer views (net_*), read from the snapshot ops/r14_publish_network_views.py
    commits, so the build does not depend on what the network engines compute later."""
    from backend.intel.network import views
    return views.build_rows()


def _governance_rows() -> dict[str, list[dict[str, Any]]]:
    """R13 IE: the fictional governance history (gov_decision, gov_approval_step, gov_policy_exception), built by the
    same deterministic seed `ops/r13_seed_governance.py` publishes (R13 M: so the full build covers every relation)."""
    from backend.intel.governance import seed as gov_seed
    return {rel: df.to_dict("records") for rel, df in gov_seed.build().items()}


def _scenario_rows() -> dict[str, list[dict[str, Any]]]:
    """R13 Session S: the scenario engine's relations (calibration, joint scenarios, satellite models, book results),
    computed by the engine from the books and the MEVs (deterministic). The calibrated Stress Lab ladder (set R13-S1)
    is a later version of dd_stress_scenario: after a full rebuild run `python -m backend.scenarios.publish`."""
    from backend.scenarios import engine as scn_engine
    from backend.scenarios import publish as scn_publish
    res = scn_engine.build()
    return {rel: fn(res) for rel, fn in scn_publish.RELATIONS.items()}


def publish_all(rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    from backend.dealdesk.data import store
    missing = sorted(set(S.RELATIONS) - set(rows))
    if missing:
        raise SystemExit(f"relations without demo rows: {missing}")
    counts = {}
    for folder in S.MANIFEST:   # the build is the origin of every R12 relation: version history restarts at 1
        m = store.manifest_path(folder)
        if m.exists():
            m.unlink()
    for rel in S.RELATIONS:
        r = store.publish(rel, rows[rel], mode="replace", actor=ACTOR, at=STAMP)
        counts[rel] = r["rows"]
    return counts


def main(argv: list[str]) -> int:
    from backend.dealdesk.data import store
    if "--schema" in argv:
        for rel in S.RELATIONS:
            store.write_empty(rel)
        print(f"SCHEMA: {len(S.RELATIONS)} empty relations written")
        return 0
    if "--check" in argv:
        with tempfile.TemporaryDirectory() as d:
            for folder in S.MANIFEST:
                (pathlib.Path(d) / folder).mkdir(parents=True, exist_ok=True)
            rows = build_rows()   # reads the committed sources, before the root moves
            os.environ["DEALDESK_R12_ROOT"] = d
            os.environ["DEALDESK_R12_HISTORY"] = str(pathlib.Path(d) / "_hist")
            publish_all(rows)
            bad, later = [], []
            for rel, spec in S.RELATIONS.items():
                folder = spec["folder"]
                committed = json.loads((V5 / folder / S.MANIFEST[folder]).read_text())["relations"][rel]
                got = json.loads((pathlib.Path(d) / folder / S.MANIFEST[folder]).read_text())["relations"][rel]["content_sha256"]
                hist = committed.get("history") or [committed]
                if (hist[-1].get("by") or ACTOR) != ACTOR:
                    # another session published a later version (e.g. T's calibrated sensitivities): compare the build
                    # with the first version, which this build wrote
                    later.append(rel)
                    if hist[0].get("by") == ACTOR and hist[0]["content_sha256"] != got:
                        bad.append(rel)
                elif committed["content_sha256"] != got:
                    bad.append(rel)
            if later:
                print("published after the build (compared at version 1):", ", ".join(later))
            del os.environ["DEALDESK_R12_ROOT"]
        print("R12 DATA BUILD CHECK", "PASS" if not bad else f"FAIL {bad}")
        return 0 if not bad else 1
    counts = publish_all(build_rows())
    from backend.dealdesk.data import contract
    contract.main()
    print(f"DATA: {sum(counts.values())} rows in {len(counts)} relations")
    for k, v in counts.items():
        print(f"  {k:28s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
