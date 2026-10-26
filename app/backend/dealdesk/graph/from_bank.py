"""Round G: what the Bank holds → graph statements, each traced to its Data Domains relation and quarter.

    deals()        every deal on the desk (deal_list.all_rows): the borrower's node and the deal's live status
    deal(pid)      the deal's neighbourhood from the Bank's data:
                     group membership and parent/subsidiary links      borrower_360.rel_group_quarter, rel_edge_quarter (GROUP)
                     suppliers and guarantors in the Bank's book        borrower_360.rel_edge_quarter (SUPPLIES, GUARANTEES)
                     owners, directors                                  borrower_360.rel_person_role
                     the deal's group file (entities, owners, guarantees, borrower_360.b360_entity, b360_edge, b360_shareholder,
                       suppliers, buyers, employers, related parties)    b360_board
                     other banks' lines                                 bureau.other_bank_facility
                     bureau standing of entities and UBOs               bureau.bureau_entity_report
                     the contagion map of the focal borrower            network_intel.net_contagion_link
    book_status()  the standing of every node the Bank books (default, classified, past due, watch, restructured), from the
                   corporate book (group.facts.borrower_attrs: corp_facility_quarter, cls_exposure, bureau_corp_quarter)

Origins: "bank:deals" and "bank:<pid>", "bank:book". Reads through backend.dealdesk.group.sources (Data Domains only).
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from backend.dealdesk.graph import store as G

AS_OF = "2026Q2"
AS_OF_DATE = "2026-06-30"


def _read(rel: str, **flt: Any) -> list[dict[str, Any]]:
    from backend.dealdesk.group import sources as S
    try:
        return S.records(S.read(rel, **flt))
    except Exception:  # noqa: BLE001 - a relation not published reads as empty
        return []


def _ev(origin: str, rel: str, label: str, pid: str = "", date: str = AS_OF_DATE, key: str = "", period: str = AS_OF) -> dict[str, Any]:
    from backend.dealdesk.group import sources as S
    dom = (S.locate(rel) or {}).get("domain") or ""
    return {"source_kind": "bank", "source_label": f"{label} ({dom}.{rel}, {period})" if dom else f"{label} ({rel}, {period})",
            "doc_id": None, "doc_label": None, "doc_type": rel, "proposal_id": pid or None, "page": None, "line": None,
            "seen_date": date, "author": "Data Domains", "origin": origin, "key": key}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ deals

def deals(c: sqlite3.Connection) -> int:
    """Register every deal on the desk (its borrower's node and live status)."""
    from backend.dealdesk import deal_list
    try:
        rows = deal_list.all_rows()
    except Exception:  # noqa: BLE001
        rows = []
    full: dict[str, dict[str, Any]] = {}
    try:
        from backend.dealdesk import registry_lookup
        full = {p.get("proposal_id"): p for p in registry_lookup.all_deals()}
    except Exception:  # noqa: BLE001
        pass
    for r in rows:
        ob = (full.get(r["proposal_id"]) or {}).get("obligor") or {}
        nid = G.upsert_node(c, r.get("obligor_name") or ob.get("name") or r["proposal_id"], "company", cif=r.get("obligor_id") or ob.get("obligor_id") or "",
                            cr=re.sub(r"\D", "", str(ob.get("cr_number") or "")),
                            attrs={"sector": r.get("sector") or ob.get("sector"), "group_name": r.get("group_name") or ob.get("group_name"),
                                   "existing": bool(r.get("existing"))})
        G.set_deal(c, r["proposal_id"], nid, name=r.get("obligor_name") or "", status=r.get("status") or "", source=r.get("source") or "",
                   rm=r.get("rm") or "", received_date=str(r.get("received") or ""), origin="bank:deals")
    return len(rows)


# ------------------------------------------------------------------------------------------------ one deal's neighbourhood

_ENT_STATUS = {"classified_substandard": ("classified", "Classified substandard"), "classified_doubtful": ("classified", "Classified doubtful"),
               "classified_loss": ("default", "Classified loss"), "default": ("default", "In default"), "past_due": ("past_due", "Past due"),
               "watch": ("watch", "On watch"), "restructured": ("restructured", "Restructured")}


def deal(c: sqlite3.Connection, pid: str) -> dict[str, int]:
    from backend.dealdesk.group import deal as D
    origin = f"bank:{pid}"
    n = {"edges": 0, "statuses": 0}
    try:
        p = D.get(pid)
    except Exception:  # noqa: BLE001
        return n
    ob = p.get("obligor") or {}
    oid = str(ob.get("obligor_id") or "")
    x = G.upsert_node(c, ob.get("name") or pid, "company", cif=oid, cr=re.sub(r"\D", "", str(ob.get("cr_number") or "")))

    def edge(src: str, rel: str, dst: str, ev: dict[str, Any], attrs: dict[str, Any] | None = None) -> None:
        if G.add_edge(c, src, rel, dst, ev, {k: v for k, v in (attrs or {}).items() if v not in (None, "")}):
            n["edges"] += 1

    def company(bid: str, name: str = "") -> str:
        return G.upsert_node(c, name or bid, "company", cif=bid)

    names: dict[str, str] = {}
    if re.fullmatch(r"CB\d+", oid):
        # group membership in the book
        gm = _read("rel_group_quarter", borrower_id=oid, reporting_quarter=AS_OF)
        for g in gm[:1]:
            gid = G.upsert_node(c, g.get("group_name") or g["group_id"], "group", attrs={"group_id": g["group_id"]})
            members = _read("rel_group_quarter", group_id=g["group_id"], reporting_quarter=AS_OF)
            ids = [m["borrower_id"] for m in members]
            names.update(_book_names(ids))
            for m in members:
                edge(company(m["borrower_id"], names.get(m["borrower_id"], "")), "member_of", gid,
                     _ev(origin, "rel_group_quarter", "Group membership", pid, key=m["borrower_id"]),
                     {"role": m.get("role"), "ownership_pct": _f(m.get("ownership_pct")), "parent": m.get("parent_borrower_id")})
        # suppliers, guarantees, parent/subsidiary links touching the borrower
        e1 = _read("rel_edge_quarter", source_borrower_id=oid, reporting_quarter=AS_OF)
        e2 = _read("rel_edge_quarter", target_borrower_id=oid, reporting_quarter=AS_OF)
        rows = e1 + e2
        names.update(_book_names([r["source_borrower_id"] for r in rows] + [r["target_borrower_id"] for r in rows]))
        for r in rows:
            s, t, typ = r["source_borrower_id"], r["target_borrower_id"], r["rel_type"]
            ev = _ev(origin, "rel_edge_quarter", {"SUPPLIES": "Supplier link", "GUARANTEES": "Guarantee", "GROUP": "Group link"}.get(typ, typ.title()),
                     pid, key=r["edge_id"])
            sn, tn = company(s, names.get(s, "")), company(t, names.get(t, ""))
            if typ == "SUPPLIES":
                edge(tn, "has_supplier", sn, ev, {"purchase_share_pct": _f(r.get("purchase_share_pct")), "revenue_share_pct": _f(r.get("revenue_share_pct")),
                                                  "annual_value_sar_mn": _f(r.get("annual_value_sar_mn"))})
            elif typ == "GUARANTEES":
                edge(tn, "guaranteed_by", sn, ev, {"amount_sar_mn": _f(r.get("guarantee_amount_sar_mn")), "basis": r.get("relation_detail")})
            elif typ == "GROUP":
                edge(tn, "has_shareholder", sn, ev, {"pct": _f(r.get("ownership_pct")), "role": r.get("relation_detail")})
        # owners and directors
        for r in _read("rel_person_role", borrower_id=oid):
            if r.get("valid_to_quarter"):
                continue
            pp = G.upsert_node(c, r.get("person_name") or r["person_id"], "person", attrs={"person_id": r["person_id"]})
            role = str(r.get("role") or "")
            edge(x, "has_shareholder" if role.lower() == "owner" else "has_director", pp,
                 _ev(origin, "rel_person_role", "Persons and roles", pid, key=f"{r['person_id']}:{role}", period=str(r.get("valid_from_quarter") or AS_OF)),
                 {"role": role, "pct": _f(r.get("ownership_pct"))})
        # the contagion map (network_intel)
        for r in _read("net_contagion_link", focal_borrower_id=oid):
            edge(x, "contagion_link", company(r["borrower_id"], r.get("name") or ""), _ev(origin, "net_contagion_link", "Contagion map", pid, key=r["borrower_id"]),
                 {"channels": r.get("channels"), "why": r.get("why"), "at_risk_sar_mn": _f(r.get("at_risk_sar_mn"))})
    # the deal's group file (R12/R16 entity groups)
    gid_txt = str(ob.get("group_id") or "")
    ents = [e for e in _read("b360_entity") if gid_txt and e.get("group_id") == gid_txt]
    if not ents and oid:
        subj = [e for e in _read("b360_entity") if e.get("borrower_id") == oid or e.get("entity_id") == oid]
        if subj:
            ents = [e for e in _read("b360_entity") if e.get("group_id") == subj[0].get("group_id")]
    if ents:
        eid_node: dict[str, str] = {}
        gname = ents[0].get("group_name") or gid_txt
        gnode = G.upsert_node(c, gname, "group", attrs={"group_id": ents[0].get("group_id")})
        for e in ents:
            is_subj = e.get("entity_id") == oid or e.get("borrower_id") == oid or str(e.get("role")) == "subject"
            nid = x if is_subj else G.upsert_node(c, e["entity_name"], "company", cif=str(e.get("borrower_id") or ""),
                                                  cr=re.sub(r"\D", "", str(e.get("licence_no") or "")))
            eid_node[e["entity_id"]] = nid
            if e.get("role") not in ("employer",):
                edge(nid, "member_of", gnode, _ev(origin, "b360_entity", "Group entities", pid, key=e["entity_id"]), {"role": e.get("role")})
            st = _ENT_STATUS.get(str(e.get("credit_status") or ""))
            if st:
                G.add_status(c, nid, st[0], f"{st[1]}: {e.get('credit_status_note') or ''}".strip(": "),
                             _ev(origin, "b360_entity", "Group entities", pid, key=e["entity_id"]))
                n["statuses"] += 1
        people = {r["holder_id"]: r["holder_name"] for r in _read("b360_shareholder") if str(r.get("holder_id", "")).startswith("XP")}
        people.update({r["person_id"]: r["person_name"] for r in _read("b360_board")})
        gids = {e.get("group_id") for e in ents}
        short = {str(g).split("-")[-1].replace("XG", "") for g in gids}
        for r in _read("b360_edge"):
            if r.get("group_id") not in gids and r.get("group_id") not in short:
                continue

            def ref(i: str) -> str | None:
                if i in eid_node:
                    return eid_node[i]
                if i.startswith("XP") and people.get(i):
                    return G.upsert_node(c, people[i], "person", attrs={"person_id": i})
                return None
            s, t = ref(str(r["source_id"])), ref(str(r["target_id"]))
            if not s or not t:
                continue
            ev = _ev(origin, "b360_edge", "Group links", pid, key=r["edge_id"])
            typ = r["rel_type"]
            attrs = {"detail": r.get("detail"), "pct": _f(r.get("ownership_pct")), "amount_mn": _f(r.get("amount_mn")),
                     "annual_value_mn": _f(r.get("annual_value_mn"))}
            if typ == "owns":
                edge(t, "has_shareholder", s, ev, attrs)
            elif typ == "guarantees":
                edge(t, "guaranteed_by", s, ev, attrs)
            elif typ == "supplies":
                edge(t, "has_supplier", s, ev, attrs)
            elif typ == "buys_from":
                edge(t, "has_buyer", s, ev, attrs)
            elif typ == "employer_of":
                edge(t, "has_employer", s, ev, attrs)
            elif typ == "common_director":
                edge(t, "has_director", s, ev, attrs)
            elif typ == "related_party":
                edge(s, "related_party", t, ev, attrs)
    # other banks and the bureau (per deal)
    ent_by_id = {e["entity_id"]: e for e in _read("b360_entity")}
    for r in _read("other_bank_facility", proposal_id=pid):
        e = ent_by_id.get(r.get("entity_id"))
        who = x if (r.get("entity_id") == oid or not e) else G.upsert_node(c, r.get("entity_name") or e["entity_name"], "company")
        bank = G.upsert_node(c, r["bank_name"], "bank")
        edge(who, "borrows_from", bank, _ev(origin, "other_bank_facility", "Other banks' facilities", pid, key=f"{r['bank_name']}:{r.get('entity_id')}"),
             {"limit_mn": _f(r.get("declared_limit_mn")), "outstanding_mn": _f(r.get("declared_outstanding_mn")), "facility_types": r.get("facility_types")})
    for r in _read("bureau_entity_report", proposal_id=pid):
        od = _f(r.get("overdue_days_max")) or 0
        court = _f(r.get("court_cases_n")) or 0
        ws = str(r.get("worst_status") or "")
        if od <= 0 and court <= 0 and ws in ("", "current"):
            continue
        kind = "person" if str(r.get("entity_kind")) in ("ubo", "person", "guarantor") else "company"
        who = x if r.get("entity_id") == oid else G.upsert_node(c, r.get("entity_name") or r["entity_id"], kind)
        code = "default" if re.search(r"(?i)default|loss|written", ws) else "classified" if re.search(r"(?i)substandard|doubtful|classified", ws) else "past_due"
        note = ", ".join(x_ for x_ in (f"{int(od)} days overdue" if od else "", f"{int(court)} court case{'s' if court != 1 else ''}" if court else "",
                                       ws if ws not in ("", "current") else "") if x_)
        G.add_status(c, who, code, f"Bureau ({r.get('bureau') or 'SIMAH'}, {r.get('report_date') or ''}): {note}",
                     _ev(origin, "bureau_entity_report", "Bureau report", pid, date=str(r.get("report_date") or AS_OF_DATE), key=r["report_id"]))
        n["statuses"] += 1
    return n


def _book_names(ids: list[str]) -> dict[str, str]:
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    return {r["borrower_id"]: r["borrower_name"] for r in _read("corp_borrower_quarter", borrower_id=ids, reporting_quarter=AS_OF)}


# ------------------------------------------------------------------------------------------------ standing in the book

def book_status(c: sqlite3.Connection) -> int:
    """The book's standing of every node with a corporate-book id (CB…), as at the book quarter."""
    from backend.dealdesk.group import facts as F
    ids = [r["cif"] for r in c.execute("SELECT DISTINCT cif FROM node WHERE cif LIKE 'CB%'")]
    if not ids:
        return 0
    try:
        attrs = F.borrower_attrs(ids)
    except Exception:  # noqa: BLE001
        return 0
    node_of = {r["cif"]: r["node_id"] for r in c.execute("SELECT node_id, cif FROM node WHERE cif LIKE 'CB%' AND kind = 'company'")}
    n = 0
    for bid, a in attrs.items():
        nid = node_of.get(bid)
        if not nid:
            continue
        c.execute("UPDATE node SET attrs = json_patch(attrs, ?) WHERE node_id = ?",
                  (json.dumps({"rating": a.get("rating"), "sector": a.get("sector"), "ead_sar_mn": a.get("ead"), "book_status": a.get("status")}, default=str), nid))
        facts = f"rating {a.get('rating')}, stage {a.get('worst_stage')}, {a.get('max_dpd_4q') or 0} days past due (4 quarters)"
        ev = _ev("bank:book", "corp_facility_quarter", "Corporate book", date=AS_OF_DATE, key=bid)
        ev["source_label"] = f"Corporate book (cockpit.corp_facility_quarter, classification.cls_exposure, {AS_OF})"
        code = None
        if a.get("default"):
            code, note = "default", f"In default in the Bank's book: {facts}"
        elif a.get("classified"):
            code, note = "classified", f"Classified ({', '.join(a.get('classified_basis') or [])}): {facts}"
        elif a.get("watchlist"):
            code, note = "watch", f"On the watchlist ({a.get('watchlist_reason') or 'no reason given'}): {facts}"
        elif a.get("restructured"):
            code, note = "restructured", f"Restructured: {facts}"
        elif a.get("in_arrears") or (a.get("max_dpd_4q") or 0) > 30:
            code, note = "past_due", f"In arrears: {facts}; bureau {a.get('external_dpd') or 0} days past due elsewhere"
        if code:
            G.add_status(c, nid, code, note, ev)
            n += 1
    return n
