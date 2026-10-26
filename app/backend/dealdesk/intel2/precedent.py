"""D8 Precedent explorer: the five closest past deals, what was decided, with what conditions, how they performed,
on a stated similarity basis; flags when this decision would be inconsistent with them.

Method (deterministic)
  * Past deals: governance.gov_decision (credit decisions on book borrowers, fictional seed; outcomes over the four
    quarters after the decision read live from the corporate book: worst stage, default, DPD, rating notches) and the
    decided Deal Desk deals (dd_deal status approved / declined / counter_offered, conditions from dd_condition).
  * Similarity (0-1, weights stated in every answer): sector 0.35; rating 0.25 x (1 - notches / 4); product family
    0.15 (revolving / term / trade, from the past borrower's book facilities at the decision quarter); size 0.15 x
    (1 - |ln(amount ratio)| / ln 4); collateral 0.10 (main collateral type, cockpit col_item for book borrowers, the
    pledged items for Deal Desk deals). A component that cannot be measured scores 0 and is named "not recorded".
  * The five highest scores (ties: newest decision first) are returned; each with the basis per component.
  * This deal's decision: approve when the selected structure clears the hurdle with no hard-limit breach, otherwise
    counter-offer (decline when the rating is below the floor or more than one hard limit breaches), as in Decision
    consistency. Inconsistent = at least three of the five went the other way (approve vs decline).
"""
from __future__ import annotations

import functools
import json
import math
from typing import Any

from backend.dealdesk.intel2 import common as C

W = {"sector": 0.35, "rating": 0.25, "product": 0.15, "size": 0.15, "collateral": 0.10}
FAMILY = {"revolver": "revolving", "term_loan": "term", "performance_lg": "trade", "financial_lg": "trade", "trade_lc": "trade"}
BOOK_FAMILY = {"revolving_credit": "revolving", "working_capital": "revolving", "overdraft": "revolving", "term_loan": "term",
               "asset_finance": "term", "project_finance": "term", "trade_finance": "trade", "supply_chain_finance": "trade"}
BOOK_COLL = {"Residential Property": "real_estate", "Real Estate": "real_estate", "Receivables": "receivables", "Motor Vehicle": "plant_equipment",
             "Plant and Equipment": "plant_equipment", "Cash Deposit": "cash", "Corporate Guarantee": "guarantee"}
DEC_WORD = {"approved": "approved", "approved_with_conditions": "approved with conditions", "declined": "declined",
            "counter_offered": "counter-offered"}
DEC_RANK = {"approved": 2, "approved_with_conditions": 2, "counter_offered": 1, "declined": 0}


def _rank(r: str) -> int | None:
    from backend.v5common.ratings import rank
    try:
        return rank(r)
    except Exception:  # noqa: BLE001
        return None


@functools.lru_cache(maxsize=2)
def _pool(ver: str) -> str:
    from backend.intel.governance import common as G
    d = G.decisions_with_outcomes()
    f = G.facilities()
    f = f[["borrower_id", "reporting_quarter", "facility_id", "limit_sar_mn"]].merge(
        C.frame("corp_facility_quarter", reporting_quarter="2026Q2")[["facility_id", "product_type"]], on="facility_id", how="left")
    f["family"] = f["product_type"].map(BOOK_FAMILY)
    fam = (f.dropna(subset=["family"]).groupby(["borrower_id", "reporting_quarter", "family"])["limit_sar_mn"].sum().reset_index()
           .sort_values(["borrower_id", "reporting_quarter", "limit_sar_mn", "family"], ascending=[True, True, False, True])
           .drop_duplicates(["borrower_id", "reporting_quarter"]))
    famd = {(r.borrower_id, r.reporting_quarter): r.family for r in fam.itertuples()}
    col = C.frame("col_item", book="corporate")
    col["kind"] = col["type"].map(BOOK_COLL)
    cm = (col.groupby(["obligor_id", "kind"])["value_sar_mn"].sum().reset_index().sort_values(["obligor_id", "value_sar_mn"], ascending=[True, False])
          .drop_duplicates("obligor_id"))
    coll = dict(zip(cm["obligor_id"], cm["kind"]))
    out = []
    for r in C.records(d):
        out.append({"kind": "history", "id": r["decision_id"], "name": r["borrower_name"], "borrower_id": r["borrower_id"], "sector": r["sector"],
                    "rating": r["rating_at_decision"], "amount": C.finite(r["limit_sar_mn"]), "family": famd.get((r["borrower_id"], r["decision_quarter"])),
                    "collateral": coll.get(r["borrower_id"]), "decision": r["decision"], "date": r["decided_on"], "quarter": r["decision_quarter"],
                    "case_type": r["case_type"], "level": r["required_level"],
                    "conditions": {"set": r["conditions_set"], "met": r["conditions_met"], "breached": r["conditions_breached"]},
                    "exceptions": r.get("exception_types"),
                    "outcome": None if r.get("worst_stage") is None else {
                        "worst_stage": r["worst_stage"], "default_12m": r["default_12m"], "max_dpd": r["max_dpd"],
                        "notches_12m": r["notches_12m"], "quarters": r["quarters_observed"], "to": r["outcome_quarter"]}})
    return json.dumps(out, default=str)


def _deals(pid: str) -> list[dict[str, Any]]:
    out = []
    for r in C.rows("dd_deal", columns=["proposal_id", "status", "obligor_name", "obligor_id", "committee_date", "approval_authority", "case_type",
                                       "reporting_quarter", "rel_version"]):
        if r["proposal_id"] == pid or r.get("status") not in DEC_RANK:
            continue
        try:
            p = C.proposal(r["proposal_id"])
        except Exception:  # noqa: BLE001
            continue
        a = p["ask"]
        conds = C.rows("dd_condition", proposal_id=r["proposal_id"])
        types = [x["type"] for x in p["security"]["collateral"] if x["collateral_id"] in (a.get("collateral_ids") or [])]
        out.append({"kind": "deal", "id": r["proposal_id"], "name": r["obligor_name"], "borrower_id": r.get("obligor_id"),
                    "sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"],
                    "amount": float(a["amount"]) * (1.0 if a.get("currency", "SAR") == "SAR" else 3.75),
                    "family": FAMILY.get(a["facility_type"]), "collateral": types[0] if types else None, "decision": r["status"],
                    "date": r.get("committee_date") or "", "quarter": "", "case_type": r.get("case_type"), "level": r.get("approval_authority"),
                    "conditions": {"set": len(conds), "texts": [c["text"] for c in conds[:4]]}, "outcome": None, "_row": r})
    return out


def _score(me: dict[str, Any], x: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    parts = []
    s = W["sector"] * (me["sector"] == x["sector"])
    parts.append({"factor": "sector", "weight": W["sector"], "score": round(s, 4), "this": me["sector"], "past": x["sector"]})
    a, b = _rank(me["rating"]), _rank(x["rating"] or "")
    g = abs(a - b) if a is not None and b is not None else None
    sr = W["rating"] * max(0.0, 1 - g / 4) if g is not None else 0.0
    parts.append({"factor": "rating", "weight": W["rating"], "score": round(sr, 4), "this": me["rating"], "past": x["rating"] or "not recorded",
                  "notches": g})
    sp = W["product"] * (me["family"] == x["family"]) if x.get("family") else 0.0
    parts.append({"factor": "product", "weight": W["product"], "score": round(sp, 4), "this": me["family"], "past": x.get("family") or "not recorded"})
    ss = 0.0
    if me["amount"] and x.get("amount"):
        ss = W["size"] * max(0.0, 1 - abs(math.log(me["amount"] / x["amount"])) / math.log(4))
    parts.append({"factor": "size", "weight": W["size"], "score": round(ss, 4), "this": round(me["amount"], 1), "past": round(x["amount"], 1) if x.get("amount") else "not recorded"})
    sc = W["collateral"] * (me["collateral"] == x["collateral"]) if x.get("collateral") and me.get("collateral") else 0.0
    parts.append({"factor": "collateral", "weight": W["collateral"], "score": round(sc, 4), "this": me.get("collateral") or "none",
                  "past": x.get("collateral") or "not recorded"})
    return round(s + sr + sp + ss + sc, 4), parts


@functools.lru_cache(maxsize=64)
def _precedent(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    a = C.analysis(pid, st["terms"])
    t = a["terms"]
    types = [x["type"] for x in p["security"]["collateral"] if x["collateral_id"] in (t.get("collateral_ids") or [])]
    me = {"sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"], "amount": float(a["metrics"]["amount_sar_mn"]),
          "family": FAMILY.get(t["facility_type"]), "collateral": types[0] if types else None}
    pool = json.loads(_pool("v")) + _deals(pid)
    scored = []
    for x in pool:
        if x["kind"] == "deal" and x["id"] == pid:
            continue
        s, parts = _score(me, x)
        scored.append((s, x["date"] or "", x, parts))
    scored.sort(key=lambda z: (-z[0], "" if not z[1] else "".join(chr(255 - ord(c)) for c in z[1]), z[2]["id"]))
    top = scored[:5]
    hard = C.C.hard_breaches(a)
    mine = 2 if C.C.approvable(a) else (0 if any(c["name"] == "min_rating" for c in hard) or len(hard) > 1 else 1)
    items = []
    for s, _, x, parts in top:
        if x["kind"] == "history":
            src = {"domain": "governance", "relation": "gov_decision", "key": {"decision_id": x["id"]}, "column": "decision"}
        else:
            src = C.row_source("dd_deal", x.pop("_row"), "status")
        x.pop("_row", None)
        perf = x.get("outcome")
        if perf:
            ptxt = ("defaulted within 12 months" if perf["default_12m"] else f"reached Stage {perf['worst_stage']}" if perf["worst_stage"] >= 2
                    else "stayed in Stage 1") + (f", {perf['notches_12m']:+d} notch{'es' if abs(perf['notches_12m']) != 1 else ''}" if perf.get("notches_12m") else "") + f" (to {perf['to']})"
        else:
            ptxt = "not yet booked: no performance to read" if x["kind"] == "deal" else "no book quarters after the decision"
        cd = x["conditions"]
        ctxt = ("no conditions" if not cd["set"] else
                f"{cd['set']} condition{'s' if cd['set'] != 1 else ''} set, {cd.get('met', 0)} met, {cd.get('breached', 0)} breached" if "met" in cd else
                (f"{cd['set']} conditions: " + "; ".join(cd.get("texts") or [])[:200]) if cd["set"] else "no conditions recorded")
        basis = ", ".join(f"{q['factor']} " + ("same" if q["score"] >= q["weight"] - 1e-9 else "not recorded" if q["past"] == "not recorded"
                                                  else "close" if q["score"] >= 0.5 * q["weight"] else "differs") for q in parts)
        items.append({"id": x["id"], "kind": x["kind"], "name": x["name"], "decision": DEC_WORD.get(x["decision"], x["decision"]), "date": x["date"],
                      "level": x.get("level"), "conditions": ctxt, "performance": ptxt, "outcome": perf, "similarity_basis": parts, "basis_text": basis,
                      "similarity": C.fig(s, "0-1", src, "Similarity"), "sector": x["sector"], "rating": x["rating"],
                      "amount": C.fig(round(x["amount"], 2) if x.get("amount") else None, "SAR m", src, "Amount decided"),
                      "href": f"/borrower-360?domain=corporate&customer_id={x['borrower_id']}&period=2026Q2" if str(x.get("borrower_id", "")).startswith("CB")
                      else f"/deal-desk/{x['id']}"})
    ranks = [DEC_RANK.get(x["decision"], 1) for _, _, x, _ in top]
    other = sum(1 for r in ranks if (r == 2) != (mine == 2) and r != 1)
    inconsistent = other >= 3
    bad = sum(1 for i in items if i["outcome"] and (i["outcome"]["worst_stage"] >= 2 or i["outcome"]["default_12m"]))
    word = {2: "approve", 1: "counter-offer", 0: "decline"}[mine]
    head = (f"The 5 closest past deals to {p['obligor']['name']} ({me['sector']}, {me['rating']}, SAR {me['amount']:,.0f}m): "
            f"{sum(1 for r in ranks if r == 2)} approved, {sum(1 for r in ranks if r == 0)} declined; {bad} of them later went to Stage 2 or worse. "
            + (f"Approving here would go against {other} of them: explain the difference." if inconsistent and mine == 2 else
               f"Declining here would go against {other} of them: explain the difference." if inconsistent else
               f"A decision to {word} is consistent with them."))
    plain = C.plain(
        "This finds the five past deals most like this one and shows what was decided and how they turned out.",
        f"Closest is {items[0]['name']} ({items[0]['decision']}, similarity {items[0]['similarity']['value']:.2f}); "
        f"{bad} of 5 later slipped to Stage 2 or worse." if items else "No past deals were found.",
        ("Explain in the paper why this deal is different." if inconsistent else
         "Copy the conditions that protected the good cases." if bad else "No precedent argues against this decision."))
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {k: st[k] for k in ("kind", "label", "note")},
           "headline": head, "plain": plain, "this_deal": {**me, "decision": word}, "weights": W, "precedents": items,
           "inconsistent": inconsistent, "pool": {"history": sum(1 for x in pool if x["kind"] == "history"), "deals": sum(1 for x in pool if x["kind"] == "deal")},
           "note": ("Decision history is a fictional seed (governance gov_decision); outcomes are the corporate book's own. "
                    "Deal Desk deals decided recently have no performance yet."),
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def precedent(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_precedent(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
