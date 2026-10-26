"""Build the demo deal from the extracted fields: the Deal Desk proposal schema, every default labelled."""
from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from typing import Any

from backend.dealdesk import desk_params, paths, proposals
from backend.dealdesk.try_docs import extract as X
from backend.dealdesk.try_docs import tables as T
from backend.dealdesk_thread import ingest
from backend.dealdesk_thread.proposal_full import FACILITY

#: deal fields the engine needs; when the proposal does not state them these values are used and shown as defaults
DEAL_DEFAULTS: dict[str, tuple[Any, str]] = {
    "name": ("Participant proposal", "the borrower's name was not found"),
    "sector": ("Wholesale Trade", "no sector stated: Wholesale Trade sector parameters used"),
    "internal_rating": ("BB", "no internal rating stated: BB (the middle of the book) used"),
    "amount": (100.0, "no amount found: SAR 100m used"),
    "margin_bps": (250, "no margin found: 250 bps used"),
}
PREFIX = "TRY-"


def aed_sar() -> float:
    return float(desk_params.rows()["aed_sar"])


def fields_from(read: dict[str, Any], data: bytes | None) -> dict[str, dict[str, Any]]:
    """Field -> {value, source, confidence}: the Deal Desk reader for Word files, the free-text reader for every layout."""
    found: dict[str, dict[str, Any]] = {}
    if data is not None and read["name"].lower().endswith(".docx"):
        try:
            r = ingest.extract(data, read["name"])
            for f in r["fields"]:
                if f["value"] is not None and f["confidence"] >= 0.9:
                    found[f["field"]] = {**f, "reader": "Deal Desk form"}
        except Exception:  # noqa: BLE001 - not the Deal Desk layout: the free-text reader alone
            pass
    if "sector" in found and found["sector"]["value"] not in X.SECTORS:
        sec = X.sector_of_code(str(found["sector"]["value"])) or X._sector(str(found["sector"]["value"]))  # noqa: SLF001
        if sec:
            found["sector"]["value"] = sec
        else:
            found.pop("sector")
    if "name" in found:
        found["name"]["value"] = X.clean_name(str(found["name"]["value"]))
    for k, f in X.free_text(read["text"], read.get("tables")).items():
        cur = found.get(k)
        bad_name = k == "name" and cur and len(str(cur["value"])) > 80
        if cur is None or f["confidence"] > cur["confidence"] or bad_name or (k == "group_name" and len(str(cur["value"])) > 80):
            found[k] = {**f, "reader": "free text"}
    return found


UNFUNDED = ("performance_lg", "financial_lg", "trade_lc")


def facility_lines(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The facilities table as deal lines (type, funded or not, pricing) and its total; parents of sub-limits are kept for
    display and left out of the pricing and type shares (`parent`)."""
    rows = T.facilities(text)
    shape: dict[str, Any] = {"total": None}
    if rows:
        tot = next((r for r in rows if r["total"]), None)
        shape["total"] = tot["proposed"] if tot else None
        body = [r for r in rows if not r["total"]]
        for i, r in enumerate(body):
            nxt = body[i + 1] if i + 1 < len(body) else None
            r["parent"] = bool(nxt and nxt["level"] > r["level"]) or (r["pricing_bps"] is None and r["commission_bps"] is None
                                                                        and bool(re.search(r"umbrella|project limit|interchangeable", r["facility"] + " " + r["particulars"], re.I)))
            t = X.facility_type_of(r["facility"])
            if r.get("bps") is not None:
                r["commission_bps" if t in UNFUNDED and not re.search(r"funded", r["facility"], re.I) else "pricing_bps"] = int(round(r["bps"]))
            if re.search(r"\(funded\)|overdraft|finance against", r["facility"], re.I):
                t = "revolver"
            if t in UNFUNDED and r["pricing_bps"] is not None and r["commission_bps"] is None:
                t = "revolver"  # trust receipts, finance against certificates: funded
            r["facility_type"] = t
            r["funded"] = t not in UNFUNDED
        return body, shape
    old = X.facilities_table(text)
    for r in old:
        t = X.facility_type_of(r["facility"])
        if re.search(r"\(funded\)|overdraft|finance against", r["facility"], re.I):
            t = "revolver"
        bps = r.pop("pricing_bps", None)
        r.update(facility_type=t, parent=False, level=0, particulars="", total=False,
                 pricing_bps=None if t in UNFUNDED else bps, commission_bps=bps if t in UNFUNDED else None)
        r["funded"] = t not in UNFUNDED
    return old, shape


def build(read: dict[str, Any], data: bytes | None, sid: str) -> dict[str, Any]:
    """{proposal, fields, defaults, lines, currency}: the deal in the Deal Desk schema (SAR), ready for the engine."""
    found = fields_from(read, data)
    ccy = X.currency_of(read["text"])
    rate = aed_sar() if ccy == "AED" else 1.0
    defaults: list[dict[str, str]] = []
    flat = {k: v["value"] for k, v in found.items()}
    lines, shape = facility_lines(read["text"])
    if lines:
        body = [ln for ln in lines if not ln.get("parent")]
        priced = [ln for ln in body if ln["pricing_bps"] is not None or ln["commission_bps"] is not None]
        use = priced or body
        tot = shape["total"] or sum(ln["proposed"] or 0 for ln in lines if not ln.get("parent"))
        if tot and tot > 0:
            flat["amount"] = tot
            found["amount"] = {"field": "amount", "label": "Amount (million)", "value": tot, "confidence": 0.96, "reader": "free text",
                               "source": "facilities table, total proposed" if shape["total"] else f"facilities table ({len(lines)} lines, proposed)"}
        funded = [ln for ln in use if ln["funded"]]
        unf = [ln for ln in use if not ln["funded"]]
        wsum = lambda xs, k: sum((x["proposed"] or 0) * x[k] for x in xs if x[k] is not None)  # noqa: E731
        wamt = lambda xs, k: sum((x["proposed"] or 0) for x in xs if x[k] is not None)  # noqa: E731
        if wamt(funded, "pricing_bps") > 0 and "margin_bps" not in found:
            flat["margin_bps"] = int(round(wsum(funded, "pricing_bps") / wamt(funded, "pricing_bps")))
            found["margin_bps"] = {"field": "margin_bps", "label": "Margin (bps)", "value": flat["margin_bps"], "confidence": 0.9,
                                   "reader": "free text", "source": "facilities table (funded lines, amount-weighted spread)"}
        elif wamt(use, "pricing_bps") > 0 and "margin_bps" not in found:
            flat["margin_bps"] = int(round(wsum(use, "pricing_bps") / wamt(use, "pricing_bps")))
            found["margin_bps"] = {"field": "margin_bps", "label": "Margin (bps)", "value": flat["margin_bps"], "confidence": 0.9,
                                   "reader": "free text", "source": "facilities table (amount-weighted pricing)"}
        if wamt(unf, "commission_bps") > 0:
            flat["commission_bps"] = int(round(wsum(unf, "commission_bps") / wamt(unf, "commission_bps")))
            found["commission_bps"] = {"field": "commission_bps", "label": "Commission (bps)", "value": flat["commission_bps"],
                                       "confidence": 0.9, "reader": "free text",
                                       "source": "facilities table (LG and LC lines, amount-weighted commission)"}
        by_type: dict[str, float] = {}
        for ln in use:
            by_type[ln["facility_type"]] = by_type.get(ln["facility_type"], 0) + (ln["proposed"] or 0)
        if by_type and max(by_type.values()) > 0:
            flat["facility_type"] = max(by_type, key=lambda k: by_type[k])
            found["facility_type"] = {"field": "facility_type", "label": "Facility", "value": flat["facility_type"],
                                      "source": "facilities table (largest share)", "confidence": 0.9, "reader": "free text"}
        sm = sum(ln["proposed"] or 0 for ln in use) or 1
        shape["funded_share_pct"] = round(100 * sum(ln["proposed"] or 0 for ln in funded) / sm, 1)
        unf_amt = {}
        for ln in unf:
            unf_amt[ln["facility_type"]] = unf_amt.get(ln["facility_type"], 0) + (ln["proposed"] or 0)
        shape["unfunded_type"] = max(unf_amt, key=lambda k: unf_amt[k]) if unf_amt else None
    fin = T.financials(read["text"], str(flat.get("name") or ""))
    if fin:
        for k, v in fin["values"].items():
            cur = found.get(k)
            if cur is None or cur.get("confidence", 0) < 0.99:
                found[k] = {"field": k, "label": ingest.FIELDS[k][0], "value": v, "confidence": 0.99, "reader": "free text",
                            "source": f"financials table '{fin['title']}', {fin['period']}"}
                flat[k] = v
    for k, (v, why) in DEAL_DEFAULTS.items():
        if flat.get(k) in (None, ""):
            flat[k] = v
            defaults.append({"field": k, "label": ingest.FIELDS[k][0], "value": v, "why": why})
    ft = flat.get("facility_type") or "term_loan"
    if not flat.get("tenor_years"):
        flat["tenor_years"] = 1 if ft != "term_loan" else 5
        defaults.append({"field": "tenor_years", "label": "Tenor (years)", "value": flat["tenor_years"],
                         "why": f"no tenor stated: {flat['tenor_years']} year{'s' if flat['tenor_years'] != 1 else ''} used for {FACILITY.get(ft, ft).lower()}"})
    flat["tenor_years"] = max(1, min(10, int(flat["tenor_years"])))
    if flat.get("internal_rating") not in proposals.GRADES:
        flat["internal_rating"] = "BB"
    # money: the deal is booked in SAR; AED amounts converted at the Deal Desk rate
    conv = []
    for k in ("amount", "revenue", "ebitda", "total_debt", "debt_service", "net_worth", "collateral_value"):
        if isinstance(flat.get(k), (int, float)) and rate != 1.0:
            flat[k] = round(float(flat[k]) * rate, 3)
            conv.append(k)
    if conv:
        defaults.append({"field": "currency", "label": "Currency", "value": "SAR",
                         "why": f"amounts in AED converted to SAR at {rate} (Deal Desk aed_sar): {', '.join(conv)}"})
    if ccy == "USD":
        flat["currency"] = "USD"
    else:
        flat["currency"] = "SAR"
    flat["amount"] = max(0.01, min(1e6, float(flat["amount"])))
    flat["margin_bps"] = max(0, min(2000, int(flat["margin_bps"])))
    if flat.get("grace_years") and flat["grace_years"] >= flat["tenor_years"]:
        flat["grace_years"] = 0
    p = ingest.proposal_from_fields({k: v for k, v in flat.items() if k in ingest.FIELDS}, {"filename": read["name"], "try_docs": sid},
                                    strict=False)
    p = copy.deepcopy(p)
    # a figure the proposal does not state is 0 for the engine and labelled; the review marks the checks that need it
    # "not verifiable" (engines.review), so a zero never reads as a breach
    for k in ("revenue", "ebitda", "total_debt", "debt_service", "net_worth", "current_ratio"):
        if flat.get(k) in (None, ""):
            defaults.append({"field": k, "label": ingest.FIELDS[k][0], "value": 0.0,
                             "why": f"{ingest.FIELDS[k][0].split(' (')[0]} not stated in the proposal: 0 used, so the ratios that need it are not tested"})
    ask = p["ask"]
    if lines:
        ask["funded_share_pct"] = shape["funded_share_pct"]
        if shape.get("unfunded_type"):
            ask["unfunded_type"] = shape["unfunded_type"]
        if ask["facility_type"] not in ("term_loan", "revolver") and ask["funded_share_pct"] > 0:
            ask["facility_type"] = "revolver" if any(ln["facility_type"] == "revolver" for ln in lines) else "term_loan"
    if ask["facility_type"] in ("performance_lg", "financial_lg", "trade_lc"):
        ask["unfunded_type"] = ask["facility_type"]
        ask["funded_share_pct"] = 0
    ob = p["obligor"]
    ob["internal_rating"] = flat["internal_rating"]
    ob["pd_master_scale"] = __import__("backend.dealdesk.seed", fromlist=["MASTER_SCALE"]).MASTER_SCALE.get(flat["internal_rating"])
    ob["segment"] = ob.get("segment") or ob["sector"]
    p["received"] = datetime.now(UTC).strftime("%Y-%m-%d")
    p["status"] = "new"
    p["demo_session"] = sid
    p["memo_language"] = read["language"]
    errs = proposals.validate(p)
    if errs:
        raise ValueError("The deal could not be built: " + "; ".join(f"{e['field']} {e['message']}" for e in errs))
    fields = [{"field": k, "label": ingest.FIELDS[k][0] if k in ingest.FIELDS else k, "value": v["value"], "source": v["source"],
               "reader": v.get("reader", "")} for k, v in found.items() if k in ingest.FIELDS]
    return {"proposal": p, "fields": fields, "defaults": defaults, "lines": lines, "currency": ccy, "aed_sar": rate if ccy == "AED" else None}


# ------------------------------------------------------------------ the demo deal in the Deal Desk store

def deal_id(sid: str) -> str:
    return PREFIX + sid.split("-")[-1][:8].upper()


def save(p: dict[str, Any], sid: str) -> str:
    """The demo deal in the Deal Desk proposals store under its own id (TRY-…), so every engine reads it like any deal."""
    pid = deal_id(sid)
    p = copy.deepcopy(p)
    p["proposal_id"] = pid
    ob = p["obligor"]
    ob["obligor_id"] = ob.get("obligor_id") or "DN" + pid
    ob["group_id"] = ob.get("group_id") or "DG" + pid
    ob["group_name"] = ob.get("group_name") or ob["name"]
    p["deal_currency"] = p["ask"]["currency"]
    with proposals._LOCK:  # noqa: SLF001 - the store's own lock; the demo row is removed by session.wipe
        con = proposals._db()  # noqa: SLF001
        try:
            con.execute("DELETE FROM proposals WHERE id = ?", (pid,))
            con.execute("INSERT INTO proposals VALUES (?, ?, ?, ?)", (pid, json.dumps(p), datetime.now(UTC).isoformat(), "try-docs"))
            con.commit()
        finally:
            con.close()
    return pid


def data_domain_rows(p: dict[str, Any], scope: str) -> dict[str, list[dict[str, Any]]]:
    """The deal as Data Domains rows (dd_proposal, dd_proposal_facility, dd_obligor_financials) under the demo scope."""
    pid, ob, ask = p["proposal_id"], p["obligor"], p["ask"]
    q = paths.AS_OF
    prop = [{"proposal_id": pid, "reporting_quarter": q, "scope": scope, "obligor_name": ob["name"], "sector": ob["sector"],
             "internal_rating": ob["internal_rating"], "existing": False, "facility_type": ask["facility_type"], "currency": ask["currency"],
             "amount_mn": ask["amount"], "tenor_years": ask["tenor_years"], "margin_bps": ask["margin_bps"], "status": p["status"]}]
    fac = [{"proposal_id": pid, "line_id": "L1", "reporting_quarter": q, "scope": scope, "facility_type": ask["facility_type"],
            "amount_mn": ask["amount"], "funded_share_pct": ask["funded_share_pct"], "margin_bps": ask["margin_bps"]}]
    fin = [{"proposal_id": pid, "year": y["year"], "reporting_quarter": q, "scope": scope, "kind": y["kind"],
            **{k: y.get(k) for k in ("revenue", "ebitda", "total_debt", "debt_service", "net_worth", "current_ratio")}}
           for y in p["financials"]["years"]]
    return {"dd_proposal": prop, "dd_proposal_facility": fac, "dd_obligor_financials": fin}
