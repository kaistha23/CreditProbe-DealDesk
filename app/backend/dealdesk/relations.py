"""The Deal Desk domain as parquet relations, for Data Builder (PLAN_R4 18:58 update).

    data/dealdesk/dd-saudi-v1/
      dd_proposal.parquet              one row per proposal: ids, new-to-bank or existing, ask terms, status
      dd_proposal_facility.parquet     facility lines: the proposed funded/unfunded lines and, for existing
                                       borrowers, their book facilities (CF ids)
      dd_obligor_financials.parquet    one row per proposal and financial year (actuals and projections)
      dd_collateral_guarantee.parquet  collateral items and guarantees offered or available
      dd_parameter.parquet             every parameter table flattened: table, key, value, unit, owner, version
      dd_portfolio_snapshot.parquet    the book at the as-of quarter by limit dimension, with limits and headroom
      dd_result.parquet                the last priced result per proposal: the ask and the recommended structure
      manifest.json                    dictionary (description and unit of every column), row counts, content hashes

Written by ops/dealdesk_build.py from data/dealdesk/proposals.json, the parameter tables
(backend/dealdesk/seed.py) and the engine. Every row carries `reporting_quarter` (the spine's as-of quarter).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import pandas as pd

from backend.dealdesk import paths

RELEASE = "dd-saudi-v1"
Q = "reporting_quarter"

DICTIONARY: dict[str, dict[str, str]] = {
    "proposal_id": {"description": "Deal Desk proposal identifier (DD-nn seeded, DD-1nn added by users).", "unit": ""},
    Q: {"description": "As-of quarter of the corporate book the proposal is checked against.", "unit": ""},
    "obligor_id": {"description": "Obligor: the book borrower id (CB#####) for an existing borrower, DN### for a new-to-bank name.", "unit": ""},
    "obligor_name": {"description": "Obligor's legal name.", "unit": ""},
    "cr_number": {"description": "Commercial registration number.", "unit": ""},
    "existing_flag": {"description": "1 when the obligor is an existing borrower in the corporate book.", "unit": "flag (0/1)"},
    "new_to_bank_flag": {"description": "1 when the obligor is new to the bank.", "unit": "flag (0/1)"},
    "status": {"description": "Pipeline status: new, in_review, counter_offered, approved or declined.", "unit": ""},
    "rm": {"description": "Relationship manager who submitted the proposal.", "unit": ""},
    "business_unit": {"description": "Business unit (sets the hurdle rate).", "unit": ""},
    "received_date": {"description": "Date the proposal was received.", "unit": ""},
    "case_type": {"description": "The test case the proposal represents (e.g. large_exposure, infeasible).", "unit": ""},
    "sector": {"description": "Obligor's sector (the book's sector names).", "unit": ""},
    "sub_sector": {"description": "Obligor's sub-sector.", "unit": ""},
    "sector_code": {"description": "ISIC-style sector code.", "unit": ""},
    "region": {"description": "Obligor's region.", "unit": ""},
    "internal_rating": {"description": "Internal rating (global order AAA to C).", "unit": ""},
    "external_rating": {"description": "External rating where the obligor has one; empty when unrated.", "unit": ""},
    "group_id": {"description": "Connected group (relationship-domain ownership group, CG… for book groups, DG… for new ones).", "unit": ""},
    "group_name": {"description": "Connected group name.", "unit": ""},
    "simah_flag": {"description": "SIMAH bureau flag: clear, watch or adverse.", "unit": ""},
    "sme_flag": {"description": "1 when the obligor is an SME.", "unit": "flag (0/1)"},
    "gre_flag": {"description": "1 when the obligor is a government-related entity.", "unit": "flag (0/1)"},
    "existing_ead_sar_mn": {"description": "Obligor's EAD in the corporate book at the as-of quarter before the deal.", "unit": "SAR million"},
    "facility_type": {"description": "Facility type: term_loan, revolver, performance_lg, financial_lg or trade_lc.", "unit": ""},
    "structure": {"description": "Structure: conventional, murabaha, tawarruq, ijara or musharaka.", "unit": ""},
    "currency": {"description": "Deal currency (SAR or USD).", "unit": ""},
    "amount": {"description": "Requested amount in the deal currency.", "unit": "million (deal currency)"},
    "amount_sar_mn": {"description": "Requested amount in SAR (USD at 3.75).", "unit": "SAR million"},
    "tenor_years": {"description": "Tenor.", "unit": "years"},
    "grace_years": {"description": "Profit-only years at the start.", "unit": "years"},
    "amortisation": {"description": "Amortisation profile: equal, bullet or balloon.", "unit": ""},
    "balloon_pct": {"description": "Share repaid at maturity when the profile is balloon.", "unit": "%"},
    "margin_bps": {"description": "Margin over SAIBOR (SAR) or SOFR (USD).", "unit": "bps"},
    "upfront_fee_bps": {"description": "Upfront fee on the amount.", "unit": "bps"},
    "commitment_fee_bps": {"description": "Commitment fee on the undrawn balance.", "unit": "bps"},
    "commission_bps": {"description": "LG/LC commission per year on the unfunded outstanding.", "unit": "bps"},
    "utilisation_pct": {"description": "Drawn share (revolver) or expected usage (LG/LC).", "unit": "%"},
    "funded_share_pct": {"description": "Funded share of the amount; the rest is unfunded.", "unit": "%"},
    "cash_margin_pct": {"description": "Cash margin held as collateral, as a share of the amount.", "unit": "%"},
    "covenant_package": {"description": "Covenant package: none, standard or enhanced.", "unit": ""},
    "guarantee_id": {"description": "Guarantee included in the ask, if any.", "unit": ""},
    "guarantee_coverage_pct": {"description": "Share of the exposure the guarantee covers.", "unit": "%"},
    "memo_file": {"description": "The credit memo document (data/dealdesk/memos).", "unit": ""},
    "purpose": {"description": "Purpose of the facility.", "unit": ""},
    "line_id": {"description": "Facility line: DD-nn-F (proposed funded), DD-nn-U (proposed unfunded), or the book facility id.", "unit": ""},
    "line_kind": {"description": "proposed or existing (a book facility of an existing borrower).", "unit": ""},
    "facility_id": {"description": "Book facility id (CF######) for existing lines; empty for proposed lines.", "unit": ""},
    "funded_flag": {"description": "1 for a funded line, 0 for an unfunded (LG/LC) line (book facility class for existing lines).", "unit": "flag (0/1)"},
    "limit_sar_mn": {"description": "Line limit.", "unit": "SAR million"},
    "drawn_sar_mn": {"description": "Drawn balance (existing lines at the as-of quarter).", "unit": "SAR million"},
    "ead_sar_mn": {"description": "Exposure at default.", "unit": "SAR million"},
    "stage": {"description": "IFRS 9 stage of an existing book facility.", "unit": ""},
    "year": {"description": "Financial year.", "unit": ""},
    "kind": {"description": "actual or projection.", "unit": ""},
    "revenue_sar_mn": {"description": "Revenue.", "unit": "SAR million"},
    "ebitda_sar_mn": {"description": "EBITDA.", "unit": "SAR million"},
    "total_debt_sar_mn": {"description": "Total financial debt.", "unit": "SAR million"},
    "debt_service_sar_mn": {"description": "Annual debt service (principal and profit).", "unit": "SAR million"},
    "net_worth_sar_mn": {"description": "Net worth.", "unit": "SAR million"},
    "current_ratio_x": {"description": "Current assets / current liabilities.", "unit": "x"},
    "source": {"description": "Where the figure comes from.", "unit": ""},
    "item_id": {"description": "Collateral (C…) or guarantee (G…) id within the proposal.", "unit": ""},
    "item_kind": {"description": "collateral or guarantee.", "unit": ""},
    "item_type": {"description": "Collateral type (cash, real_estate, plant_equipment, receivables, shares, vehicles) or guarantee type (corporate, personal, government, kafalah, bank).", "unit": ""},
    "value": {"description": "Collateral market value in its own currency.", "unit": "million (item currency)"},
    "value_sar_mn": {"description": "Collateral market value in SAR.", "unit": "SAR million"},
    "valuation_date": {"description": "Collateral valuation date.", "unit": ""},
    "haircut_pct": {"description": "Haircut applied to the collateral value (lgd parameter table).", "unit": "%"},
    "guarantor": {"description": "Guarantor's name.", "unit": ""},
    "guarantor_rating": {"description": "Guarantor's rating.", "unit": ""},
    "coverage_pct": {"description": "Guarantee coverage of the exposure.", "unit": "%"},
    "offered_in_ask_flag": {"description": "1 when the item is part of the client's ask, 0 when only available.", "unit": "flag (0/1)"},
    "table_name": {"description": "Parameter table.", "unit": ""},
    "param_key": {"description": "Path of the value inside the table (dot-separated).", "unit": ""},
    "value_text": {"description": "The parameter value as text.", "unit": ""},
    "value_num": {"description": "The parameter value when numeric.", "unit": ""},
    "param_unit": {"description": "Unit of the parameter value.", "unit": ""},
    "owner": {"description": "Named owner of the table (Treasury, Finance, Risk Models, CFO, Risk).", "unit": ""},
    "version": {"description": "Table version.", "unit": ""},
    "effective_date": {"description": "Date the version takes effect.", "unit": ""},
    "dimension": {"description": "Limit dimension: sector, rating_bucket, collateral_type or group.", "unit": ""},
    "dimension_key": {"description": "The sector, bucket, collateral type or connected group.", "unit": ""},
    "dimension_name": {"description": "Display name (groups).", "unit": ""},
    "share_pct": {"description": "Share of the corporate book's EAD.", "unit": "%"},
    "limit_pct": {"description": "Concentration limit as a share of the book, where one applies.", "unit": "%"},
    "limit_sar_mn_cap": {"description": "Absolute limit, where one applies (connected group).", "unit": "SAR million"},
    "headroom_sar_mn": {"description": "New EAD the dimension can take before its limit.", "unit": "SAR million"},
    "limit_kind": {"description": "hard or soft (soft limits can be exceeded with escalation).", "unit": ""},
    "view": {"description": "ask (the client's terms) or recommended (closest-to-ask structure that clears the hurdle and the limits).", "unit": ""},
    "pd_12m": {"description": "12-month PD from the XGBoost model after the covenant overlay.", "unit": "probability (0-1)"},
    "lgd_y1": {"description": "Year-1 facility LGD.", "unit": "probability (0-1)"},
    "ead_y1_sar_mn": {"description": "Year-1 EAD.", "unit": "SAR million"},
    "el_y1_sar_mn": {"description": "Year-1 expected loss.", "unit": "SAR million"},
    "el_lifetime_sar_mn": {"description": "Expected loss over the life (undiscounted).", "unit": "SAR million"},
    "rwa_y1_sar_mn": {"description": "Year-1 risk-weighted assets (SAMA Standardised Approach).", "unit": "SAR million"},
    "capital_y1_sar_mn": {"description": "Year-1 allocated capital (basis max of regulatory and economic, plus operational).", "unit": "SAR million"},
    "lifetime_raroc_pct": {"description": "Lifetime RAROC: PV(risk-adjusted profit) / PV(capital).", "unit": "%"},
    "hurdle_pct": {"description": "Hurdle rate.", "unit": "%"},
    "sva_sar_mn": {"description": "Shareholder value added: PV(risk-adjusted profit - hurdle x capital).", "unit": "SAR million"},
    "breakeven_margin_bps": {"description": "Margin at which lifetime RAROC equals the hurdle (funded deals).", "unit": "bps"},
    "approval_level": {"description": "Required approval level (Delegation of Authority).", "unit": ""},
    "decision": {"description": "approve_as_asked, counter_offer, escalate (only with a soft-limit breach) or decline.", "unit": ""},
    "hard_breaches": {"description": "Hard limits breached by this structure, separated by semicolons.", "unit": ""},
    "soft_breaches": {"description": "Soft limits breached by this structure, separated by semicolons.", "unit": ""},
    "param_version": {"description": "Parameter version the result was priced with.", "unit": ""},
    "model_version": {"description": "PD model version.", "unit": ""},
    "trace_note": {"description": "How the row was produced.", "unit": ""},
}

LABELS = {
    "dd_proposal": ("Credit proposals", ["proposal_id", Q], "one row per proposal"),
    "dd_proposal_facility": ("Proposal facility lines", ["proposal_id", "line_id", Q], "one row per proposal facility line"),
    "dd_obligor_financials": ("Obligor financials", ["proposal_id", "year", Q], "one row per proposal and financial year"),
    "dd_collateral_guarantee": ("Collateral and guarantees", ["proposal_id", "item_id", Q], "one row per collateral item or guarantee"),
    "dd_parameter": ("Parameter tables", ["table_name", "param_key", Q], "one row per parameter value"),
    "dd_portfolio_snapshot": ("Portfolio snapshot and headroom", ["dimension", "dimension_key", Q], "one row per limit dimension and key"),
    "dd_result": ("Priced results", ["proposal_id", "view", Q], "one row per proposal and view (ask, recommended)"),
}


def _flat(prefix: str, x: Any, out: list[tuple[str, Any]]) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            _flat(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(x, list) and x and all(isinstance(v, dict) for v in x):
        for i, v in enumerate(x):
            key = v.get("name") or v.get("rating") or v.get("from") or v.get("level") or str(i)
            _flat(f"{prefix}.{key}" if prefix else str(key), v, out)
    else:
        out.append((prefix, x))


def _unit_of(key: str) -> str:
    k = key.lower()
    if "_bps" in k:
        return "bps"
    if "sar_mn" in k or k.endswith("max_exposure"):
        return "SAR million"
    if "years" in k:
        return "years"
    if any(w in k for w in ("haircut", "_rate", "ratio", "pd_ttc", "lgd", "ccf", "share", "realisation", "hurdle", "multiplier")):
        return "fraction (0-1)"
    return ""


def frames(props: list[dict[str, Any]], with_results: bool = True) -> dict[str, pd.DataFrame]:
    from backend.dealdesk import engine, optimizer, params, pd_model, portfolio
    from backend.dealdesk.seed import tables
    q = paths.AS_OF
    fx = float(params.rows("capital")["usd_sar"])
    P, F, FIN, CG, RES = [], [], [], [], []
    lg = params.rows("lgd")["collateral"]
    bf = portfolio.frames()["facility"]
    book_class = dict(zip(bf["facility_id"], bf["facility_class"]))
    for p in props:
        ob, a = p["obligor"], p["ask"]
        cx = 1.0 if a["currency"] == "SAR" else fx
        pid = p["proposal_id"]
        P.append({"proposal_id": pid, Q: q, "obligor_id": ob["obligor_id"], "obligor_name": ob["name"], "cr_number": ob.get("cr_number", ""),
                  "existing_flag": int(bool(ob.get("existing"))), "new_to_bank_flag": int(not ob.get("existing")),
                  "status": p["status"], "rm": p["rm"], "business_unit": p["business_unit"], "received_date": p["received"],
                  "case_type": p.get("case", ""), "purpose": p.get("purpose", ""), "sector": ob["sector"], "sub_sector": ob.get("sub_sector", ""),
                  "sector_code": ob.get("sector_code", ""), "region": ob.get("region", ""), "internal_rating": ob["internal_rating"],
                  "external_rating": ob.get("external_rating") or "", "group_id": ob.get("group_id", ""), "group_name": ob.get("group_name", ""),
                  "simah_flag": ob.get("simah_flag", ""), "sme_flag": int(bool(ob.get("sme"))), "gre_flag": int(bool(ob.get("gre"))),
                  "existing_ead_sar_mn": float(ob.get("existing_exposure_sar_mn", 0.0)),
                  "facility_type": a["facility_type"], "structure": a["structure"], "currency": a["currency"],
                  "amount": float(a["amount"]), "amount_sar_mn": float(a["amount"]) * cx, "tenor_years": int(a["tenor_years"]),
                  "grace_years": int(a["grace_years"]), "amortisation": a["amortisation"], "balloon_pct": float(a["balloon_pct"]),
                  "margin_bps": float(a["margin_bps"]), "upfront_fee_bps": float(a["upfront_fee_bps"]),
                  "commitment_fee_bps": float(a["commitment_fee_bps"]), "commission_bps": float(a["commission_bps"]),
                  "utilisation_pct": float(a["utilisation_pct"]), "funded_share_pct": float(a["funded_share_pct"]),
                  "cash_margin_pct": float(a["cash_margin_pct"]), "covenant_package": a["covenant_package"],
                  "guarantee_id": a.get("guarantee_id") or "", "guarantee_coverage_pct": float(a.get("guarantee_coverage_pct") or 0),
                  "memo_file": p.get("memo", "")})
        unf = a["facility_type"] in engine.UNFUNDED
        fs = 0.0 if unf else float(a["funded_share_pct"]) / 100
        amt = float(a["amount"]) * cx
        if fs > 0:
            F.append({"proposal_id": pid, "line_id": f"{pid}-F", Q: q, "line_kind": "proposed", "facility_id": "",
                      "facility_type": a["facility_type"], "funded_flag": 1, "currency": a["currency"], "limit_sar_mn": amt * fs,
                      "drawn_sar_mn": 0.0, "ead_sar_mn": 0.0, "tenor_years": int(a["tenor_years"]), "stage": 0})
        if fs < 1:
            F.append({"proposal_id": pid, "line_id": f"{pid}-U", Q: q, "line_kind": "proposed", "facility_id": "",
                      "facility_type": a["facility_type"] if unf else a["unfunded_type"], "funded_flag": 0, "currency": a["currency"],
                      "limit_sar_mn": amt * (1 - fs), "drawn_sar_mn": 0.0, "ead_sar_mn": 0.0, "tenor_years": int(a["tenor_years"]), "stage": 0})
        for f in ob.get("existing_facilities", []):
            F.append({"proposal_id": pid, "line_id": f["facility_id"], Q: q, "line_kind": "existing", "facility_id": f["facility_id"],
                      "facility_type": f["product"], "funded_flag": int(book_class.get(f["facility_id"], "funded") == "funded"), "currency": "SAR", "limit_sar_mn": float(f["limit"]),
                      "drawn_sar_mn": float(f["drawn"]), "ead_sar_mn": float(f["ead"]), "tenor_years": 0, "stage": int(f["stage"])})
        for y in p["financials"]["years"]:
            FIN.append({"proposal_id": pid, "obligor_id": ob["obligor_id"], "year": int(y["year"]), Q: q, "kind": y["kind"],
                        "revenue_sar_mn": float(y["revenue"]), "ebitda_sar_mn": float(y["ebitda"]), "total_debt_sar_mn": float(y["total_debt"]),
                        "debt_service_sar_mn": float(y["debt_service"]), "net_worth_sar_mn": float(y.get("net_worth") or 0.0),
                        "current_ratio_x": float(y.get("current_ratio") or 0.0), "source": y.get("source", "")})
        for c in p["security"]["collateral"]:
            cur = c.get("currency", "SAR")
            CG.append({"proposal_id": pid, "item_id": c["collateral_id"], Q: q, "item_kind": "collateral", "item_type": c["type"],
                       "value": float(c["value"]), "currency": cur, "value_sar_mn": float(c["value"]) * (1.0 if cur == "SAR" else fx),
                       "valuation_date": c.get("valuation_date", ""), "haircut_pct": float(lg[c["type"]]["haircut"]) * 100,
                       "guarantor": "", "guarantor_rating": "", "coverage_pct": 0.0, "offered_in_ask_flag": int(bool(c.get("pledged_in_ask")))})
        for g in p["security"]["guarantees"]:
            CG.append({"proposal_id": pid, "item_id": g["guarantee_id"], Q: q, "item_kind": "guarantee", "item_type": g["type"],
                       "value": 0.0, "currency": "", "value_sar_mn": 0.0, "valuation_date": "", "haircut_pct": 0.0,
                       "guarantor": g.get("guarantor", ""), "guarantor_rating": g.get("guarantor_rating", ""),
                       "coverage_pct": float(g.get("coverage_pct") or 0), "offered_in_ask_flag": int(bool(g.get("offered_in_ask")))})
    # parameters (the seeded tables, flattened)
    PAR = []
    for name, tab in tables().items():
        rows: list[tuple[str, Any]] = []
        _flat("", tab["rows"], rows)
        extra = {k: v for k, v in tab.items() if k not in ("rows", "name", "owner", "version", "effective_from", "approved_by", "description")}
        _flat("", extra, rows)
        for k, v in rows:
            num = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            PAR.append({"table_name": name, "param_key": k, Q: q, "value_text": json.dumps(v) if not isinstance(v, str) else v,
                        "value_num": num, "param_unit": _unit_of(k), "owner": tab["owner"], "version": tab["version"],
                        "effective_date": tab["effective_from"]})
    # portfolio snapshot with limits
    s = portfolio.snapshot()
    tot = s["total_ead"]
    L = {x["name"]: x for x in params.rows("risk_appetite")}
    SNAP = []
    for k, v in sorted(s["by_sector"].items()):
        lim = L["sector_appetite"]["limits"].get(k, L["sector_policy"]["limit"])
        SNAP.append({"dimension": "sector", "dimension_key": k, "dimension_name": k, Q: q, "ead_sar_mn": float(v), "share_pct": v / tot * 100,
                     "limit_pct": lim * 100, "limit_sar_mn_cap": None, "headroom_sar_mn": (lim * tot - v) / (1 - lim),
                     "limit_kind": "soft" if k in L["sector_appetite"]["limits"] else "hard"})
    for k, v in sorted(s["by_bucket"].items()):
        lim = L["rating_bucket"]["limits"].get(k)
        SNAP.append({"dimension": "rating_bucket", "dimension_key": k, "dimension_name": k, Q: q, "ead_sar_mn": float(v), "share_pct": v / tot * 100,
                     "limit_pct": None if lim is None else lim * 100, "limit_sar_mn_cap": None,
                     "headroom_sar_mn": None if lim is None or lim >= 1 else (lim * tot - v) / (1 - lim), "limit_kind": "soft"})
    for k, v in sorted(s["by_collateral"].items()):
        lim = L["collateral_type"]["limits"].get(k)
        SNAP.append({"dimension": "collateral_type", "dimension_key": k, "dimension_name": k.replace("_", " "), Q: q, "ead_sar_mn": float(v),
                     "share_pct": v / tot * 100, "limit_pct": None if lim is None else lim * 100, "limit_sar_mn_cap": None,
                     "headroom_sar_mn": None if lim is None else (lim * tot - v) / (1 - lim), "limit_kind": "soft" if lim is not None else ""})
    glim = L["group_connected"]["limit"]
    for k, v in sorted(s["by_group"].items()):
        SNAP.append({"dimension": "group", "dimension_key": k, "dimension_name": s["group_names"].get(k, ""), Q: q, "ead_sar_mn": float(v),
                     "share_pct": v / tot * 100, "limit_pct": None, "limit_sar_mn_cap": glim, "headroom_sar_mn": glim - v, "limit_kind": "hard"})
    # priced results
    if with_results:
        mv, pv = pd_model.model_meta()["version"], params.version_tag()
        for p in props:
            a = engine.analyse(p)
            be = engine.breakeven_margin(p)
            r = optimizer.optimize(p, counter_offers=False)
            esc = None
            if not r["feasible"]:
                esc = optimizer.optimize(p, allow_soft=True, counter_offers=False)
            if r["ask"]["clears"]:
                decision, rec = "approve_as_asked", r["closest"]
            elif r["feasible"]:
                decision, rec = "counter_offer", r["closest"]
            elif esc is not None and esc["feasible"]:
                decision, rec = "escalate", esc["closest"]
            else:
                decision, rec = "decline", None

            def row(view: str, m: dict, appr: dict, hard: list, soft: list, bev: float | None, note: str) -> dict:
                return {"proposal_id": p["proposal_id"], "view": view, Q: q, "pd_12m": m["pd_12m"], "lgd_y1": m["lgd_y1"],
                        "ead_y1_sar_mn": m["ead_y1"], "el_y1_sar_mn": m["el_y1"], "el_lifetime_sar_mn": m["el_lifetime"],
                        "rwa_y1_sar_mn": m["rwa_y1"], "capital_y1_sar_mn": m["capital_y1"], "lifetime_raroc_pct": m["lifetime_raroc"] * 100,
                        "hurdle_pct": m["hurdle"] * 100, "sva_sar_mn": m["sva"], "breakeven_margin_bps": bev,
                        "approval_level": appr["level"], "decision": decision, "hard_breaches": ";".join(hard), "soft_breaches": ";".join(soft),
                        "param_version": pv, "model_version": mv, "trace_note": note}
            RES.append(row("ask", a["metrics"], a["approval"], a["approval"]["hard_breaches"], a["approval"]["soft_breaches"], be,
                           "engine.analyse on the ask"))
            if rec is not None:
                ra = engine.analyse(p, rec["terms"])
                RES.append(row("recommended", ra["metrics"], ra["approval"], ra["approval"]["hard_breaches"], ra["approval"]["soft_breaches"],
                               engine.breakeven_margin(p, rec["terms"]), "optimizer closest to ask" + (" with escalation" if decision == "escalate" else "")))
    out = {"dd_proposal": pd.DataFrame(P), "dd_proposal_facility": pd.DataFrame(F), "dd_obligor_financials": pd.DataFrame(FIN),
           "dd_collateral_guarantee": pd.DataFrame(CG), "dd_parameter": pd.DataFrame(PAR), "dd_portfolio_snapshot": pd.DataFrame(SNAP)}
    if with_results:
        out["dd_result"] = pd.DataFrame(RES)
    for k, df in out.items():
        out[k] = df.sort_values(LABELS[k][1][:-1]).reset_index(drop=True)
    return out


def content_hash(df: pd.DataFrame) -> str:
    """A hash of the values (rounded to 1e-9), independent of the parquet writer's version."""
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(9)
    return hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()


def write(out_root: pathlib.Path, props: list[dict[str, Any]]) -> dict[str, Any]:
    d = out_root / RELEASE
    d.mkdir(parents=True, exist_ok=True)
    fr = frames(props)
    rel_meta = {}
    for name, df in fr.items():
        df.to_parquet(d / f"{name}.parquet", index=False)
        rel_meta[name] = {"label": LABELS[name][0], "key_columns": LABELS[name][1], "grain": LABELS[name][2], "rows": int(len(df)),
                          "columns": list(df.columns), "content_sha256": content_hash(df)}
    used = {c for df in fr.values() for c in df.columns}
    manifest = {"release_id": RELEASE, "domain": "deal_desk", "as_of": paths.AS_OF, "period_column": Q,
                "relations": rel_meta, "dictionary": {k: v for k, v in DICTIONARY.items() if k in used},
                "documents": "Credit memos (.docx) stay as files in data/dealdesk/memos, one per proposal (memo_file)."}
    missing = sorted(used - set(DICTIONARY))
    if missing:
        raise ValueError(f"columns without a dictionary entry: {missing}")
    (d / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest
