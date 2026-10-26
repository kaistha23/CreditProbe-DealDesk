"""R16 i: is the uploaded customer already a customer of the Bank? If so, pull everything the Bank holds.

Match: the CR number read from the documents against the deals in Data Domains (`dd_deal`: CIF and the obligor's CR
number in the deal record), then the obligor name. A match gives the deal (`proposal_id`) and the CIF, and the pull reads
the registered relations only (N3): accounts (`dd_customer_account`), 24 months of conduct (`dd_account_conduct`),
returned cheques, facilities and utilisation (`dd_facility_limit`), security, limit history (`dd_reference`), group
exposure, the group graph (`b360_entity` / `b360_edge` / `b360_shareholder`), bureau and other banks, and the Borrower 360
profile (rating history, EWS) when the B360 service knows the CIF. Every block says which relation it came from.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from backend.dealdesk.intake.extract import norm


def _read(rel: str, **flt: Any) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data import store
        return store.dd_read(rel, **flt)
    except Exception:  # noqa: BLE001 - relation not registered on this branch / empty: the block says so
        return []


def _num(x: Any) -> float:
    try:
        v = float(x)
        return 0.0 if v != v else v
    except (TypeError, ValueError):
        return 0.0


def match(cr_number: str, name: str) -> dict[str, Any] | None:
    cr = re.sub(r"\D", "", cr_number or "")
    nn = norm(name or "")
    best = None
    for d in _read("dd_deal"):
        pj = d.get("proposal_json") or {}
        ob = pj.get("obligor") if isinstance(pj, dict) else None
        dcr = re.sub(r"\D", "", str((ob or {}).get("cr_number") or d.get("cr_number") or ""))
        if cr and dcr and dcr == cr:
            return {"proposal_id": d["proposal_id"], "cif": d.get("cif") or (ob or {}).get("obligor_id") or d.get("obligor_id") or "",
                    "name": d.get("obligor_name") or "", "group_id": d.get("group_id") or "", "group_name": d.get("group_name") or "",
                    "how": f"CR number {cr} on deal {d['proposal_id']}", "deal": d}
        if nn and norm(d.get("obligor_name") or "") == nn and best is None:
            best = {"proposal_id": d["proposal_id"], "cif": d.get("cif") or d.get("obligor_id") or "", "name": d.get("obligor_name") or "",
                    "group_id": d.get("group_id") or "", "group_name": d.get("group_name") or "",
                    "how": f"name on deal {d['proposal_id']}", "deal": d}
    if best is None and cr:  # the group graph carries the licence (CR) number of every entity the Bank knows
        for e in _read("b360_entity"):
            if re.sub(r"\D", "", str(e.get("licence_no") or "")) == cr and e.get("borrower_id"):
                cif = str(e["borrower_id"])
                pid = ""
                for rel in ("dd_customer_account", "dd_account_conduct", "dd_group_exposure"):
                    rows = _read(rel, obligor_id=cif) if rel != "dd_group_exposure" else [r for r in _read(rel) if r.get("entity_id") == e.get("entity_id")]
                    pid = next((str(r.get("proposal_id")) for r in rows if r.get("proposal_id")), "")
                    if pid:
                        break
                deal = next((d for d in _read("dd_deal", proposal_id=pid)), {}) if pid else {}
                return {"proposal_id": pid, "cif": cif, "name": e.get("entity_name") or "", "group_id": e.get("group_id") or "",
                        "group_name": e.get("group_name") or deal.get("group_name") or "", "how": f"CR number {cr} (CIF {cif})", "deal": deal}
    if best is None and cr:
        for a in _read("dd_customer_account"):
            if re.sub(r"\D", "", str(a.get("cr_number") or "")) == cr:
                return {"proposal_id": a.get("proposal_id") or "", "cif": a.get("obligor_id") or a.get("cif") or "", "name": a.get("customer_name") or "",
                        "group_id": "", "group_name": "", "how": f"CR number {cr} on the Bank's accounts", "deal": {}}
    return best


def _b360(cif: str) -> dict[str, Any]:
    try:
        from backend.b360 import service as B
        c = B.customer("corporate", cif)
    except Exception:  # noqa: BLE001 - B360 overlay absent: say so
        return {}
    if not isinstance(c, dict):
        return {}
    prof = c.get("profile") or {}
    tabs = c.get("tabs") or {}
    out: dict[str, Any] = {"profile": {k: prof.get(k) for k in ("name", "rating", "rating_previous", "exposure", "limit", "facilities", "worst_dpd",
                                                               "worst_stage", "ews_score", "ews_band", "segment", "group_name", "as_of") if k in prof}}
    rat = (tabs.get("ratings") or {}).get("series") or []
    out["rating_history"] = [{"period": r.get("period"), "rating": r.get("rating_current"), "pd_ttc_12m": r.get("pd_ttc_12m"),
                              "outlook": r.get("rating_outlook")} for r in rat[-8:] if isinstance(r, dict)]
    ews = (tabs.get("ews") or {}).get("series") or []
    last = ews[-1] if ews else {}
    out["ews"] = {"band": prof.get("ews_band") or last.get("band"), "score": prof.get("ews_score", last.get("score")),
                  "reasons": last.get("reasons") or "", "history": [{"period": e.get("period"), "band": e.get("band")} for e in ews[-8:]]}
    return out


def pull(m: dict[str, Any], as_of: dt.date) -> dict[str, Any]:
    pid, cif = m.get("proposal_id") or "", m.get("cif") or ""
    deal = m.get("deal") or {}
    out: dict[str, Any] = {"existing": True, "proposal_id": pid, "cif": cif, "name": m.get("name"), "how": m.get("how"),
                           "group_id": m.get("group_id"), "group_name": m.get("group_name"),
                           "since": deal.get("account_opened_date") or "", "rating": deal.get("rating_existing") or "",
                           "rm": deal.get("rm") or "", "sources": []}
    # accounts (current and deposit) with balances and turnover
    acc = _read("dd_customer_account", proposal_id=pid) if pid else []
    if not acc and cif:
        acc = _read("dd_customer_account", obligor_id=cif)
    out["accounts"] = acc
    if acc:
        out["sources"].append("dd_customer_account")
    # 24 months of conduct
    cond = sorted(_read("dd_account_conduct", obligor_id=cif) if cif else [], key=lambda r: str(r.get("month")))
    if not cond and pid:
        cond = sorted(_read("dd_account_conduct", proposal_id=pid), key=lambda r: str(r.get("month")))
    out["conduct"] = cond[-24:]
    if cond:
        out["sources"].append("dd_account_conduct")
        by_year: dict[int, float] = {}
        for r in cond:
            y = int(str(r.get("month"))[:4])
            by_year[y] = by_year.get(y, 0.0) + _num(r.get("credit_turnover_mn"))
        months_in = {}
        for r in cond:
            y = int(str(r.get("month"))[:4])
            months_in[y] = months_in.get(y, 0) + 1
        out["credits_by_year"] = {y: round(v, 2) for y, v in by_year.items() if months_in.get(y) == 12}
        last12 = cond[-12:]
        out["last12"] = {"credits_mn": round(sum(_num(r.get("credit_turnover_mn")) for r in last12), 2),
                         "debits_mn": round(sum(_num(r.get("debit_turnover_mn")) for r in last12), 2),
                         "avg_balance_mn": round(sum(_num(r.get("avg_balance_mn")) for r in last12) / len(last12), 2),
                         "utilisation_avg_pct": round(sum(_num(r.get("utilisation_pct")) for r in last12) / len(last12), 1),
                         "utilisation_peak_pct": round(max(_num(r.get("utilisation_pct")) for r in last12), 1),
                         "past_due_months": sum(1 for r in last12 if _num(r.get("past_due_days_max")) > 0),
                         "past_due_days_max": int(max(_num(r.get("past_due_days_max")) for r in last12)),
                         "returned_cheques_n": int(sum(_num(r.get("returned_cheques_n")) for r in last12)),
                         "returned_cheques_mn": round(sum(_num(r.get("returned_cheques_mn")) for r in last12), 2),
                         "from": last12[0].get("month"), "to": last12[-1].get("month")}
        if out["last12"]["returned_cheques_n"]:
            out["returned_cheques_12m"] = {"n": out["last12"]["returned_cheques_n"], "mn": out["last12"]["returned_cheques_mn"]}
    rc = _read("dd_returned_cheque", proposal_id=pid) if pid else []
    out["returned_cheques"] = rc
    other = [r for r in rc if r.get("obligor_id") and r.get("obligor_id") != cif]
    if other:
        out["connected_cheques"] = {"n": len(other), "mn": round(sum(_num(r.get("amount_mn")) for r in other), 2),
                                    "obligors": sorted({str(r.get("obligor_id")) for r in other}),
                                    "dates": sorted(str(r.get("return_date")) for r in other)}
    if rc:
        out["sources"].append("dd_returned_cheque")
    fac = sorted(_read("dd_facility_limit", proposal_id=pid) if pid else [], key=lambda r: (_num(r.get("level")), _num(r.get("seq"))))
    out["facilities"] = [{k: f.get(k) for k in ("limit_id", "parent_limit_id", "level", "limit_name", "product_code", "funded_flag", "existing_mn",
                                                 "outstanding_mn", "cash_margin_pct", "tenor_text", "particulars")} for f in fac]
    if fac:
        out["sources"].append("dd_facility_limit")
        lv = min(_num(f.get("level")) for f in fac)
        top = [f for f in fac if _num(f.get("level")) == lv]
        ex = sum(_num(f.get("existing_mn")) for f in top)
        os_ = sum(_num(f.get("outstanding_mn")) for f in top)
        out["facilities_total"] = {"existing_mn": round(ex, 2), "outstanding_mn": round(os_, 2), "utilisation_pct": round(os_ / ex * 100, 1) if ex else None}
    sec = _read("dd_security", proposal_id=pid) if pid else []
    out["security"] = [{k: s.get(k) for k in ("kind", "provider", "amount_mn", "value_mn", "perfection_status", "existing_flag", "note")} for s in sec]
    ref = _read("dd_reference", proposal_id=pid) if pid else []
    out["limit_history"] = sorted([{k: r.get(k) for k in ("kind", "ref_no", "ref_date", "authority", "amount_mn", "group_cap_mn", "text")} for r in ref],
                                  key=lambda r: str(r.get("ref_date")))
    ge = _read("dd_group_exposure", proposal_id=pid) if pid else []
    out["group_exposure"] = ge
    if ge:
        out["sources"].append("dd_group_exposure")
    # group graph
    gid = m.get("group_id") or ""
    ents = _read("b360_entity", group_id=gid) if gid else []
    if ents:
        out["sources"].append("b360_entity")
        ids = {e["entity_id"] for e in ents}
        edges = [e for e in _read("b360_edge", group_id=gid)] if gid else []
        holders = [h for h in _read("b360_shareholder") if h.get("entity_id") in ids]
        out["group"] = {"entities": [{k: e.get(k) for k in ("entity_id", "entity_name", "role", "parent_entity_id", "activity", "borrower_id",
                                                               "credit_status", "credit_status_note")} for e in ents],
                        "edges": [{k: e.get(k) for k in ("rel_type", "source_id", "target_id", "ownership_pct", "amount_mn", "detail")} for e in edges],
                        "shareholders": [{k: h.get(k) for k in ("entity_id", "holder_name", "holder_kind", "share_pct", "ubo_flag")} for h in holders]}
        me = next((e for e in ents if e.get("borrower_id") == cif), None)
        out["shareholders"] = [h["holder_name"] for h in holders if me and h.get("entity_id") == me["entity_id"]]
        weak = [e for e in ents if re.search(r"(?i)classif|substandard|doubtful|loss|default|litig|stage ?3|watch", f"{e.get('credit_status')} {e.get('credit_status_note')}")]
        out["connected_weak"] = [{"id": e["entity_id"], "name": e.get("entity_name"), "relation": e.get("role"),
                                  "status": (e.get("credit_status_note") or str(e.get("credit_status") or "").replace("_", " ")), "source": "b360_entity"} for e in weak]
    bur = _read("bureau_entity_report", proposal_id=pid) if pid else []
    out["bureau"] = [{k: b.get(k) for k in ("entity_name", "entity_kind", "bureau", "report_date", "outstanding_mn", "overdue_mn", "worst_status", "score", "note")} for b in bur]
    cb = _read("bureau_cbrbr", proposal_id=pid) if pid else []
    out["cbrbr"] = cb
    ob = _read("other_bank_facility", proposal_id=pid) if pid else []
    out["other_banks"] = [{k: b.get(k) for k in ("bank_name", "entity_name", "facility_types", "declared_limit_mn", "bureau_limit_mn", "bureau_outstanding_mn",
                                                  "difference_mn", "reconciliation_note")} for b in ob]
    for name, rows in (("bureau_entity_report", bur), ("bureau_cbrbr", cb), ("other_bank_facility", ob), ("dd_security", sec), ("dd_reference", ref)):
        if rows:
            out["sources"].append(name)
    names = {k: e.get("entity_name") for e in (out.get("group") or {}).get("entities", []) for k in (e.get("borrower_id"), e.get("entity_id")) if k}
    for a in out["accounts"]:
        a["holder"] = "Customer" if a.get("obligor_id") in ("", None, cif) else (names.get(a.get("obligor_id")) or a.get("obligor_id"))
    b = _b360(cif) if cif else {}
    if b:
        out["b360"] = b
        out["sources"].append("borrower_360")
    return out


def not_found(cr: str, name: str) -> dict[str, Any]:
    return {"existing": False, "how": f"no deal or account of the Bank carries CR {cr or 'n/a'}" + (f" or the name {name}" if name else ""),
            "sources": []}
