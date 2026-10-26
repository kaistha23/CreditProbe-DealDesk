"""The deal the business request asks for: who the customer is, the engine-ready proposal, and its Data Domains rows.

    m = match(request, docs)          # {proposal_id, cif, group_id, name, cr_number, existing, how}
    p = proposal(request, docs, m)    # the Deal Desk proposal record (proposals.json shape), every default labelled
    publish(p, request, docs, m, case_id)   # dd_deal + the request's facilities, security and terms (+ projects from the
                                            # uploaded project list, contracts and payment certificates)

An existing customer is matched by CR number (printed on the request and on almost every document), then CIF, then
name; the deal takes the customer's proposal id from the demo contract so the bank's data (accounts, conduct, limits,
group, bureau) joins. A customer the bank does not know gets a new id CR-<hash>.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from typing import Any

from backend.dealdesk import paths, proposals

ACTOR = "R16-c:credit_response"


def customers() -> list[dict[str, Any]]:
    try:
        from ops.r16_customers import ids
        return list(ids.CUSTOMERS)
    except Exception:  # noqa: BLE001 - the demo contract is not merged
        return []


def _norm(s: str) -> str:
    s = re.sub(r"\b(co|company|llc|ltd|est|establishment|the)\b\.?", " ", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def _crs(text: str) -> list[str]:
    return re.findall(r"(?<!\d)(\d{10})(?!\d)", text or "")


def match(request: dict[str, Any], docs: list[dict[str, Any]] | None = None, text: str = "") -> dict[str, Any]:
    h = request.get("header") or {}
    name = (request.get("fields") or {}).get("name") or h.get("customer") or ""
    cr = re.sub(r"\D", "", h.get("cr_no") or "")
    cands = [cr] if len(cr) == 10 else []
    cands += _crs(text)
    for d in docs or []:
        c = str((d.get("fields") or {}).get("cr_number") or "")
        if re.fullmatch(r"\d{10}", c):
            cands.append(c)
    cif = (h.get("cif") or "").strip()
    for c in customers():
        how = None
        if c.get("cr_number") and c["cr_number"] in cands[:1]:
            how = f"CR number {c['cr_number']} on the request"
        elif c.get("cif") and cif and c["cif"].lower() == cif.lower():
            how = f"CIF {cif} on the request"
        elif name and _norm(c["name"]) == _norm(name):
            how = "customer name on the request"
        elif c.get("cr_number") and c["cr_number"] in cands:
            how = f"CR number {c['cr_number']} on the supporting documents"
        if how:
            return {"proposal_id": c["proposal_id"], "cif": c.get("cif") or "", "group_id": c.get("group_id") or "", "group_name": c.get("group_name") or "",
                    "name": c["name"], "cr_number": c.get("cr_number") or "", "existing": bool(c.get("cif")), "sector": c.get("sector") or "",
                    "how": how, "customer_key": c.get("key")}
    # the bank's deal register by name (a customer outside the demo contract)
    try:
        from backend.dealdesk.house_style.bankform import source as S
        for r in S.read("dd_deal"):
            if name and _norm(r.get("obligor_name")) == _norm(name):
                return {"proposal_id": "", "cif": r.get("cif") or r.get("obligor_id") or "", "group_id": r.get("group_id") or "",
                        "group_name": r.get("group_name") or "", "name": r.get("obligor_name"), "cr_number": cands[0] if cands else "",
                        "existing": True, "sector": "", "how": f"name in the deal register ({r['proposal_id']})", "customer_key": None}
    except Exception:  # noqa: BLE001
        pass
    return {"proposal_id": "", "cif": cif, "group_id": "", "group_name": h.get("group") or "", "name": name, "cr_number": cands[0] if cands else "",
            "existing": False, "sector": "", "how": "not found in the bank's data: new to bank", "customer_key": None}


def new_id(sha: str) -> str:
    return "CR-" + sha[:8].upper()


# ------------------------------------------------------------------ the engine's proposal

def _mn(x: Any) -> float | None:
    try:
        return None if x in (None, "") else round(float(x) / 1e6, 4)
    except (TypeError, ValueError):
        return None


def financial_years(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    years = []
    for d in docs:
        if d.get("doc_type") not in ("audited_fs", "inhouse_fs"):
            continue
        f = d["fields"]
        end = str(f.get("fiscal_year") or f.get("period_to") or "")
        if not end[:4].isdigit():
            continue
        months = 12
        if d["doc_type"] == "inhouse_fs" and f.get("period_from"):
            try:
                months = (int(end[:4]) - int(str(f["period_from"])[:4])) * 12 + int(end[5:7]) - int(str(f["period_from"])[5:7]) + 1
            except ValueError:
                months = 12
        ann = 12.0 / months if months else 1.0
        rev = _mn(f.get("revenue")) or 0.0
        op = _mn(f.get("operating_profit")) or 0.0
        dep = _mn(f.get("depreciation")) or 0.0
        debt = (_mn(f.get("short_term_borrowings")) or 0.0) + (_mn(f.get("long_term_borrowings")) or 0.0) + (_mn(f.get("current_portion_ltd")) or 0.0)
        fc = _mn(f.get("finance_cost")) or 0.0
        ca, cl = _mn(f.get("current_assets")), _mn(f.get("current_liabilities"))
        years.append({"year": int(end[:4]), "kind": "actual" if d["doc_type"] == "audited_fs" else "interim", "months": months,
                      "revenue": round(rev * ann, 3), "ebitda": round((op + dep) * ann, 3), "total_debt": round(debt, 3),
                      "debt_service": round(fc * ann + (_mn(f.get("current_portion_ltd")) or 0.0), 3), "net_worth": _mn(f.get("total_equity")) or 0.0,
                      "current_ratio": round(ca / cl, 2) if ca and cl else 0.0, "source": d["name"]})
    years.sort(key=lambda y: (y["year"], y["kind"] != "actual"))
    return years


def proposal(request: dict[str, Any], docs: list[dict[str, Any]], m: dict[str, Any], pid: str) -> dict[str, Any]:
    from backend.dealdesk_thread import ingest
    f = dict(request.get("fields") or {})
    f.setdefault("name", m.get("name") or "Customer not named")
    if m.get("sector"):
        f["sector"] = m["sector"]
    f.setdefault("sector", "Construction")
    f.setdefault("internal_rating", "BB")
    fac = [r for r in request.get("facilities") or [] if not r.get("total")]
    top = [r for r in fac if r.get("level") == 1]
    new_lines = [r for r in top if (r.get("existing_mn") or 0) == 0 and (r.get("proposed_mn") or 0) > 0]
    tot = request.get("totals") or {}
    ex, pr = tot.get("existing") or 0.0, tot.get("proposed") or 0.0
    new_money = sum(r.get("proposed_mn") or 0.0 for r in new_lines)
    incr = round(pr - ex, 4) if pr and ex else 0.0
    amount = new_money or (incr if incr > 0 else pr) or f.get("amount") or 0.0
    f["amount"] = round(amount, 4)
    try:
        p = ingest.proposal_from_fields(f, {"kind": "credit_response", "document": request.get("document")}, strict=False)
    except Exception:  # noqa: BLE001 - a field the form parser refuses: the bare defaults
        p = ingest.proposal_from_fields({"name": f["name"], "amount": f["amount"]}, {"kind": "credit_response"}, strict=False)
    try:
        base = copy.deepcopy(proposals.get(pid)) if pid else None
    except Exception:  # noqa: BLE001
        base = None
    if isinstance(base, dict) and base.get("obligor"):
        p["obligor"] = {**p["obligor"], **{k: v for k, v in base["obligor"].items() if v not in (None, "", [])}}
        if base.get("financials", {}).get("years"):
            p["financials"] = base["financials"]
    ob = p["obligor"]
    ob["name"] = m.get("name") or f["name"]
    ob["obligor_id"] = m.get("cif") or ob.get("obligor_id") or ("DN" + pid)
    ob["group_id"] = m.get("group_id") or ob.get("group_id") or ("DG" + pid)
    ob["group_name"] = m.get("group_name") or request.get("header", {}).get("group") or ob.get("group_name") or ob["name"]
    ob["existing"] = bool(m.get("existing"))
    ob["cr_number"] = m.get("cr_number") or ob.get("cr_number") or ""
    ob["internal_rating"] = f.get("internal_rating") or ob.get("internal_rating") or "BB"
    ob["sector"] = f.get("sector") or ob.get("sector")
    ob["existing_exposure_sar_mn"] = round(tot.get("outstanding") or 0.0, 4)
    ob["existing_facilities"] = [{"facility": r["limit_name"], "limit_sar_mn": r.get("existing_mn") or 0.0, "outstanding_sar_mn": r.get("outstanding_mn") or 0.0}
                                 for r in top if (r.get("existing_mn") or 0) > 0]
    yrs = financial_years(docs)
    if yrs:
        p["financials"] = {"currency": "SAR", "years": [{k: y[k] for k in ("year", "kind", "revenue", "ebitda", "total_debt", "debt_service", "net_worth", "current_ratio")}
                                                        for y in yrs if y["kind"] == "actual"] or [{k: y[k] for k in ("year", "kind", "revenue", "ebitda", "total_debt",
                                                                                                                     "debt_service", "net_worth", "current_ratio")} for y in yrs]}
    a = p["ask"]
    a["amount"] = f["amount"]
    new_seq = {r["seq"] for r in new_lines}
    lines = [r for r in fac if r.get("parent") in new_seq] or new_lines or [r for r in fac if r.get("level") == 2] or top
    funded = sum(r.get("proposed_mn") or 0.0 for r in lines if _funded(r))
    total_lines = sum(r.get("proposed_mn") or 0.0 for r in lines) or 1.0
    a["funded_share_pct"] = int(round(100.0 * funded / total_lines))
    a["facility_type"] = f.get("facility_type") or a.get("facility_type")
    if a["facility_type"] in ("performance_lg", "financial_lg", "trade_lc") and a["funded_share_pct"] >= 50:
        a["facility_type"] = "revolver"
    a["unfunded_type"] = "performance_lg" if a["facility_type"] in ("term_loan", "revolver") else a["facility_type"]
    a["tenor_years"] = int(f.get("tenor_years") or a.get("tenor_years") or 1)
    if f.get("margin_bps"):
        a["margin_bps"] = int(f["margin_bps"])
    if f.get("commission_bps"):
        a["commission_bps"] = int(f["commission_bps"])
    a["cash_margin_pct"] = float(f.get("cash_margin_pct") or 0.0)
    a["currency"] = "SAR"
    gu = []
    for s in request.get("security") or []:
        if s["kind"] in ("personal_guarantee", "corporate_guarantee"):
            gu.append({"guarantee_id": f"G{len(gu) + 1}", "type": "personal" if s["kind"] == "personal_guarantee" else "corporate",
                       "guarantor": s.get("provider") or "not named", "guarantor_rating": ob["internal_rating"], "coverage_pct": 100.0, "offered_in_ask": True})
    if gu:
        p["security"]["guarantees"] = gu
        a["guarantee_id"], a["guarantee_coverage_pct"] = "G1", 100.0
    p["proposal_id"] = pid
    p["status"] = "in_review"
    p["rm"] = f.get("rm") or p.get("rm") or ""
    p["received"] = (request.get("header") or {}).get("date") or datetime.now(UTC).date().isoformat()
    p["purpose"] = f.get("purpose") or (request.get("action") or {}).get("purpose") or ""
    p["case"] = "credit_response"
    p["deal_currency"] = "SAR"
    p["request"] = {"document": request.get("document"), "method": request.get("method"), "totals": {k: tot.get(k) for k in ("existing", "outstanding", "proposed")},
                    "new_money_mn": new_money, "increase_mn": incr, "amount_basis": "new limits" if new_money else ("increase" if incr > 0 else "total proposed")}
    return p


def _funded(r: dict[str, Any]) -> bool:
    pc = (r.get("product_code") or "").upper()
    n = r.get("limit_name", "").lower()
    return pc in ("OD", "TL", "RCF", "STL", "WCF", "TR") or pc.startswith("DMCCM") or bool(re.search(r"overdraft|finance|loan|murabaha|tawarruq|funded", n))


# ------------------------------------------------------------------ the store and Data Domains

def save_store(p: dict[str, Any]) -> None:
    """The deal in the Deal Desk proposal store, so every engine reads it like any deal (as the try-docs demo does)."""
    with proposals._LOCK:  # noqa: SLF001
        con = proposals._db()  # noqa: SLF001
        try:
            con.execute("DELETE FROM proposals WHERE id = ?", (p["proposal_id"],))
            con.execute("INSERT INTO proposals VALUES (?, ?, ?, ?)", (p["proposal_id"], json.dumps(p, default=str), datetime.now(UTC).isoformat(), "credit-response"))
            con.commit()
        finally:
            con.close()


def _store():
    try:
        from backend.dealdesk.data import schema, store
    except Exception:  # noqa: BLE001
        return None
    return store if "dd_deal" in schema.RELATIONS else None


def _existing(rel: str, pid: str) -> list[dict[str, Any]]:
    """The Bank's own rows of a deal relation as they were before the first credit response wrote to it (snapshot kept
    under var/, so a second run never reads its own output as the Bank's data)."""
    snap = paths.VAR / "credit_response" / "_bank" / pid / f"{rel}.json"
    if snap.exists():
        return json.loads(snap.read_text())
    try:
        from backend.dealdesk.house_style.bankform import source as S
        rows = [{k: v for k, v in r.items() if k not in ("rel_version", "published_at", "_src")} for r in S.read(rel, proposal_id=pid)]
    except Exception:  # noqa: BLE001
        rows = []
    if rel != "dd_deal" or not any(r.get("source") == "credit_response" for r in rows):
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(json.dumps(rows, default=str))
    return rows


def _same(a: str, b: str) -> bool:
    x, y = _norm(a), _norm(b)
    return bool(x and y and (x == y or x in y or y in x))


def facility_rows(pid: str, request: dict[str, Any], src: str) -> list[dict[str, Any]]:
    """The request's facility table as dd_facility_limit rows; a seeded existing limit keeps its id, product and outstanding."""
    seeded = _existing("dd_facility_limit", pid)
    out, used = [], set()
    ids: dict[int, str] = {}
    for r in request.get("facilities") or []:
        if r.get("total"):  # the request's "Total facilities" row is the sum of the lines, not a limit (publish's engine ask skips it too)
            continue
        hit = next((s for s in seeded if s.get("limit_id") not in used and _same(s.get("limit_name") or s.get("name") or "", r["limit_name"])), None)
        lid = str(hit["limit_id"]) if hit else f"L{r['seq']:02d}"
        if hit:
            used.add(hit["limit_id"])
        ids[r["seq"]] = lid
        out.append({"proposal_id": pid, "limit_id": lid, "parent_limit_id": ids.get(r.get("parent")) or "", "level": r["level"], "seq": r["seq"],
                    "limit_name": r["limit_name"], "product_code": r.get("product_code") or (hit or {}).get("product_code") or "",
                    "funded_flag": 1 if _funded(r) else 0, "currency": "SAR", "existing_mn": r.get("existing_mn"),
                    "outstanding_mn": r.get("outstanding_mn") if r.get("outstanding_mn") is not None else (hit or {}).get("outstanding_mn"),
                    "proposed_mn": r.get("proposed_mn"), "cash_margin_pct": r.get("cash_margin_pct"), "commission_pct_pa": r.get("commission_pct_pa"),
                    "benchmark": r.get("benchmark") or "", "spread_pct": r.get("spread_pct"), "floor_pct": r.get("floor_pct"),
                    "tenor_text": r.get("tenor_text") or "", "repayment_text": r.get("repayment_text") or "", "project_id": "",
                    "interchangeable_flag": 0, "particulars": (r.get("particulars") or "")[:300]})
    for s in seeded:  # an existing limit the request does not mention: kept, flagged
        if s.get("limit_id") in used or re.match(r"^\s*(grand\s+)?total", str(s.get("limit_name") or s.get("name") or ""), re.I):
            continue
        row = {k: s.get(k) for k in ("proposal_id", "limit_id", "parent_limit_id", "level", "seq", "limit_name", "product_code", "funded_flag", "currency",
                                     "existing_mn", "outstanding_mn", "proposed_mn", "cash_margin_pct", "commission_pct_pa", "benchmark", "spread_pct",
                                     "floor_pct", "tenor_text", "repayment_text", "project_id", "interchangeable_flag", "particulars")}
        row["seq"] = 100 + len(out)
        row["particulars"] = f"{row.get('particulars') or ''} [held by the Bank; not in the business request]".strip()
        out.append(row)
    return out


SEC_KIND = {"personal_guarantee", "corporate_guarantee", "security_cheque", "assignment_receivables", "assignment_insurance", "assignment_project_proceeds",
            "hypothecation", "subordination", "mortgage", "cash_margin", "promissory_note", "pledge", "noc", "undertaking"}


def security_rows(pid: str, request: dict[str, Any], src: str, lids: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for s in request.get("security") or []:
        lid = next((v for k, v in lids.items() if _same(k, s["group"])), "ALL")
        out.append({"proposal_id": pid, "security_id": f"S{s['seq']:02d}", "limit_id": lid, "kind": s["kind"] if s["kind"] in SEC_KIND else "other",
                    "provider": s.get("provider") or "", "provider_entity_id": "", "amount_mn": s.get("amount_mn"), "currency": "SAR",
                    "net_worth_mn": s.get("net_worth_mn"), "net_worth_statement_date": s.get("net_worth_date"),
                    "perfection_status": {"pending": "pending", "perfected": "perfected"}.get(s["perfection_status"], "not_perfected" if s["perfection_status"] == "not_stated" else "pending"),
                    "perfection_deadline": s.get("deadline"), "legal_opinion_date": None, "valuation_date": None, "value_mn": None, "insurance_expiry": None,
                    "pari_passu_flag": 0, "existing_flag": 1 if s["perfection_status"] == "perfected" else 0, "note": s["text"][:400]})
    return out


def tnc_rows(pid: str, request: dict[str, Any], lids: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    seq: dict[str, int] = {}
    for t in request.get("terms") or []:
        lid = next((v for k, v in lids.items() if _same(k, t["group"])), "ALL")
        seq[lid] = seq.get(lid, 0) + 1
        out.append({"proposal_id": pid, "tnc_id": f"T{t['seq']:02d}", "limit_id": lid, "seq": seq[lid], "category": t["category"], "text": t["text"][:600],
                    "existing_status": t["existing_status"]})
    return out


def deal_row(p: dict[str, Any], request: dict[str, Any], m: dict[str, Any], case_id: str) -> dict[str, Any]:
    ob, h, tot = p["obligor"], request.get("header") or {}, request.get("totals") or {}
    prev = _existing("dd_deal", p["proposal_id"])
    base = dict(prev[-1]) if prev else {}
    for k in ("rel_version", "published_at"):
        base.pop(k, None)
    kind = (h.get("request_kind") or "").lower() or ("renewal_and_new" if (tot.get("existing") or 0) > 0 else "new")
    row = {**base, "proposal_id": p["proposal_id"], "source": base.get("source") or "credit_response", "product": base.get("product") or ("contracting" if ob["sector"] == "Construction" else "corporate"),
           "deal_name": f"{ob['name']}: {(p.get('purpose') or 'business request')[:60]}", "obligor_id": ob["obligor_id"], "obligor_name": ob["name"],
           "group_id": ob["group_id"], "group_name": ob["group_name"], "case_type": kind.replace(" ", "_"), "status": "in_review", "workflow_state": "credit_review",
           "rm": p.get("rm") or base.get("rm") or "", "business_unit": h.get("branch") or base.get("business_unit") or "Corporate Banking",
           "branch": h.get("branch") or base.get("branch") or "", "received_date": _iso(h.get("date")) or base.get("received_date"), "currency": "SAR",
           "existing_limits_mn": tot.get("existing"), "proposed_limits_mn": tot.get("proposed"),
           "rating_existing": h.get("rating_existing") or ob["internal_rating"], "rating_proposed": h.get("rating_proposed") or ob["internal_rating"],
           "cif": m.get("cif") or h.get("cif") or base.get("cif") or "", "group_no": h.get("group_no") or m.get("group_id") or base.get("group_no") or "",
           "account_opened_date": _iso(h.get("account_opened")) or base.get("account_opened_date"), "purpose_code": h.get("purpose_code") or base.get("purpose_code") or "",
           "industry_code": h.get("industry") or base.get("industry_code") or "", "collateral_code": h.get("collateral_code") or base.get("collateral_code") or "",
           "review_date": _iso(h.get("review_date")) or base.get("review_date"), "proposal_json": json.dumps(p, default=str)}
    act = request.get("action") or {}
    if act.get("cap_to") is not None:  # the request's group exposure cap ask ("exposure cap from SAR 185.0m to SAR 300.0m")
        row["group_cap_existing_mn"] = act.get("cap_from") if act.get("cap_from") is not None else base.get("group_cap_existing_mn")
        row["group_cap_proposed_mn"] = act["cap_to"]
    return row


def _iso(s: Any) -> str | None:
    if not s:
        return None
    from backend.dealdesk.credit_response.request import dates
    d = dates(str(s))
    return d[0] if d else None


def publish(p: dict[str, Any], request: dict[str, Any], m: dict[str, Any], case_id: str, extra: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    st = _store()
    pid = p["proposal_id"]
    src = f"business request {request.get('document')} ({request.get('method')})"
    out: dict[str, Any] = {"relations": {}, "published": st is not None}
    fac = facility_rows(pid, request, src)
    lids = {r["limit_name"]: r["limit_id"] for r in fac}
    rows = {"dd_deal": [deal_row(p, request, m, case_id)], "dd_facility_limit": fac, "dd_security": security_rows(pid, request, src, lids),
            "dd_tnc": tnc_rows(pid, request, lids)}
    for rel, idk in (("dd_security", "security_id"), ("dd_tnc", "tnc_id")):
        # the Bank's own rows (security held, existing conditions with their status) stay; the request's items join them
        seeded = [{k: v for k, v in r.items() if k not in ("rel_version", "published_at", "_src")} for r in _existing(rel, pid)
                  if not str(r.get(idk, "")).startswith("RQ-")]
        for r in rows[rel]:
            r[idk] = "RQ-" + r[idk]
        if rel == "dd_security":
            def _dup(x: dict[str, Any], r: dict[str, Any]) -> bool:
                if x.get("kind") != r["kind"]:
                    return False
                if _same(x.get("provider") or "", r["provider"] or "x"):
                    return True
                a, b = x.get("amount_mn"), r.get("amount_mn")  # the same item without a provider on one side: same amount (SAR 6.1m cash margin)
                return (not x.get("provider") or not r.get("provider")) and a is not None and b is not None and abs(float(a) - float(b)) <= 0.1
            rows[rel] = [r for r in rows[rel] if not any(_dup(x, r) for x in seeded)]
        if rel == "dd_tnc":  # a request term that restates a condition the Bank already records (same text) is not a second condition
            rows[rel] = [r for r in rows[rel] if not any(_same(x.get("text") or "", re.sub(r"\s*\((?:existing|new)[^)]*\)\s*\.?$", "", r["text"])) for x in seeded)]
        rows[rel] = seeded + rows[rel]
    for rel, rs in (extra or {}).items():
        if rel == "dd_project":
            # the Bank's own project record stands; the documents add only the projects it does not hold
            bank = [{k: v for k, v in r.items() if k not in ("rel_version", "published_at", "_src")} for r in _existing(rel, pid)]
            rs = bank + [r for r in rs if not any(_same(b.get("project_name") or "", re.sub(r"\s*\[.*?\]\s*$", "", r["project_name"])) for b in bank)]
        rows[rel] = rs
    if st is None:
        d = paths.VAR / "credit_response" / case_id / "data_domains"
        d.mkdir(parents=True, exist_ok=True)
        for rel, rs in rows.items():
            (d / f"{rel}.json").write_text(json.dumps(rs, default=str))
        out["relations"] = {k: len(v) for k, v in rows.items()}
        return out
    for rel, rs in rows.items():
        if rel == "dd_deal":
            r = st.publish(rel, rs, mode="upsert", actor=ACTOR)
        elif not rs and rel not in ("dd_facility_limit",):
            continue
        else:
            r = st.publish(rel, rs, mode="replace_where", where={"proposal_id": pid}, actor=ACTOR)
        out["relations"][rel] = {"rows": len(rs), "version": r.get("version")}
    return out
