"""Group facts for deals whose group is described entity by entity in Borrower 360 (the R12 demo groups: b360_entity,
b360_edge, b360_shareholder, b360_board, b360_insider_link, b360_ownership_change; with dd_group_exposure,
dd_security and bureau_entity_report). Same output shape as facts.py (book borrowers), so flags, SWOT and the UI
read one shape.

A group entity that is also a book borrower (`borrower_id`) carries its book attributes as well (EAD, stage, DPD,
EWS band, litigation indicator).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.dealdesk.group import deal, facts as F, sources as S

AS_OF = deal.AS_OF
AS_OF_DATE = "2026-06-30"
STATUS_MAP = {"performing": "performing", "past_due": "in arrears", "litigation": "in litigation",
              "classified_substandard": "classified", "classified_doubtful": "classified", "classified_loss": "classified"}
EDGE_OUT = {"owns": "owns", "guarantees": "guarantees", "supplies": "supplies", "buys_from": "buys from",
            "employer_of": "employer of", "shared_collateral": "shares collateral with", "common_director": "common director",
            "related_party": "related party"}


def _src(relation: str, **keys: Any) -> dict[str, Any]:
    return F._src(relation, **keys)


def subject(p: dict[str, Any]) -> dict[str, Any] | None:
    """The deal's obligor as a Borrower 360 entity, or None (a book borrower outside the demo groups)."""
    oid = deal.focal_id(p)
    if not oid:
        return None
    r = S.records(S.read("b360_entity", None, entity_id=oid))
    if not r:
        r = S.records(S.read("b360_entity", None, borrower_id=oid))
    return r[0] if r else None


def _years_before(d: str, n: int) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return date(y - n, m, min(dd, 28)).isoformat()


def entity_attrs(ents: list[dict[str, Any]], pid: str) -> dict[str, dict[str, Any]]:
    ids = [e["entity_id"] for e in ents]
    ge = {r["entity_id"]: r for r in S.records(S.read("dd_group_exposure", None, proposal_id=pid))}
    br = {}
    for r in S.records(S.read("bureau_entity_report", None, proposal_id=pid, entity_id=ids)):
        br[r["entity_id"]] = r
    book = F.borrower_attrs([e["borrower_id"] for e in ents if e.get("borrower_id")])
    out = {}
    for e in ents:
        b = book.get(e.get("borrower_id") or "", {})
        g = ge.get(e["entity_id"], {})
        bu = br.get(e["entity_id"], {})
        cs = str(e.get("credit_status") or "performing")
        classified = cs.startswith("classified") or bool(b.get("classified"))
        arrears = cs == "past_due" or bool(b.get("in_arrears")) or (bu.get("overdue_days_max") or 0) >= 30
        lit = cs == "litigation" or bool(b.get("in_litigation")) or (bu.get("court_cases_n") or 0) > 0
        basis = [x for x, ok in ((cs.replace("_", " "), cs.startswith("classified")),) if ok] + b.get("classified_basis", [])
        st = "classified" if classified else "in litigation" if lit else "in arrears" if arrears else \
            ("watchlist" if b.get("watchlist") else "performing")
        reasons = list(b.get("reasons", []))
        if (bu.get("court_cases_n") or 0) > 0:
            reasons.append("BUREAU-COURT-CASE")
        out[e["entity_id"]] = {
            "borrower_id": e["entity_id"], "book_id": e.get("borrower_id"), "name": e["entity_name"], "sector": e.get("activity"),
            "rating": b.get("rating"), "watchlist": bool(b.get("watchlist")),
            "ead": float(g.get("outstanding_mn") or b.get("ead") or 0.0), "limit": float(g.get("total_existing_mn") or b.get("limit") or 0.0),
            "worst_stage": b.get("worst_stage"), "max_dpd_4q": int(max(b.get("max_dpd_4q") or 0, bu.get("overdue_days_max") or 0)),
            "default": bool(b.get("default")), "ews_band": b.get("ews_band", "none"), "classified": classified,
            "classified_basis": basis, "in_arrears": arrears, "in_litigation": lit, "utp": bool(b.get("utp")),
            "restructured": bool(b.get("restructured")), "external_dpd": bu.get("overdue_days_max"), "external_default": False,
            "reasons": sorted(set(reasons)), "status": st, "credit_status": cs, "credit_status_note": e.get("credit_status_note"),
            "role": e.get("role"), "country": e.get("country"), "legal_status": e.get("legal_status"),
            "incorporation_date": e.get("incorporation_date"), "licence_no": e.get("licence_no"), "staff_count": e.get("staff_count"),
            "href": b.get("href")}
    return out


def build(pid: str, p: dict[str, Any], subj: dict[str, Any]) -> dict[str, Any]:
    sid = subj["entity_id"]
    gid = subj.get("group_id") or p["obligor"].get("group_id")
    ents = S.records(S.read("b360_entity", None, group_id=gid)) if gid else [subj]
    if not any(e["entity_id"] == sid for e in ents):
        ents.append(subj)
    by = {e["entity_id"]: e for e in ents}
    edges = S.records(S.read("b360_edge", None, group_id=gid)) if gid else []
    extra = sorted({x for e in edges for x in (e["source_id"], e["target_id"]) if x and str(x).startswith("XE-") and x not in by})
    if extra:
        for e in S.records(S.read("b360_entity", None, entity_id=extra)):
            by[e["entity_id"]] = e
    attrs = entity_attrs(list(by.values()), pid)

    # ---- structure
    parent_id = subj.get("parent_entity_id") or None

    def node(eid: str, relation: str, pct: float | None = None) -> dict[str, Any]:
        a = attrs.get(eid, {})
        return {"borrower_id": eid, "name": a.get("name", eid), "link": relation, "role": by.get(eid, {}).get("role"),
                "ownership_pct": pct, "ead": a.get("ead", 0.0), "rating": a.get("rating"), "status": a.get("status", "performing"),
                "ews_band": a.get("ews_band", "none"), "href": a.get("href"), "activity": by.get(eid, {}).get("activity"),
                "country": by.get(eid, {}).get("country"), "book_id": a.get("book_id")}

    own = {(e["source_id"], e["target_id"]): e.get("ownership_pct") for e in edges if e["rel_type"] == "owns"}
    parent = node(parent_id, "parent", own.get((parent_id, sid))) if parent_id and parent_id in by else None
    members = [e for e in by.values() if e.get("group_id") == gid]
    subs = [node(e["entity_id"], "subsidiary", own.get((sid, e["entity_id"]))) for e in members if e.get("parent_entity_id") == sid]
    sisters = [node(e["entity_id"], "sister" if e.get("role") in ("sister", "subsidiary") else (e.get("role") or "associate"),
                    own.get((parent_id, e["entity_id"])) if parent_id else None)
               for e in members if e["entity_id"] not in (sid, parent_id) and e.get("parent_entity_id") != sid
               and e.get("role") in ("sister", "subsidiary", "associate")]
    st = {"group_id": gid, "group_name": subj.get("group_name") or p["obligor"].get("group_name"), "standalone": len(members) <= 1,
          "focal": {"borrower_id": sid, "name": subj["entity_name"], "in_book": bool(subj.get("borrower_id")), "role": subj.get("role"),
                    "ownership_pct": own.get((parent_id, sid)) if parent_id else None, "book_id": subj.get("borrower_id"),
                    "licence_no": subj.get("licence_no"), "incorporation_date": subj.get("incorporation_date"),
                    "incorporation_place": subj.get("incorporation_place"), "legal_status": subj.get("legal_status"),
                    "activity": subj.get("activity"), "staff_count": subj.get("staff_count")},
          "parent": parent, "subsidiaries": subs, "sisters": sisters, "members": len(members),
          "member_ids": sorted(e["entity_id"] for e in members),
          "source": [_src("b360_entity", group_id=gid), _src("b360_edge", group_id=gid), _src("dd_group_exposure", proposal_id=pid)]}

    # ---- shareholders and UBOs
    shr = S.records(S.read("b360_shareholder", None, entity_id=sid))
    rows = [{"name": r["holder_name"], "pct": r.get("share_pct"), "ubo": bool(r.get("ubo_flag")), "nationality": r.get("nationality"),
             "kind": r.get("holder_kind") or "person", "borrower_id": r["holder_id"] if str(r.get("holder_id", "")).startswith("XE-") else None,
             "person_id": r["holder_id"], "birth_year": r.get("birth_year"), "since": r.get("since"),
             "nominee": bool(r.get("nominee_flag")), "indirect_pct": r.get("ubo_effective_pct"), "source": "b360_shareholder"} for r in shr]
    srcs = [_src("b360_shareholder", entity_id=sid)]
    comp = [r["person_id"] for r in rows if r["kind"] == "company"]
    if comp:  # look through company holders to their owners
        for r in S.records(S.read("b360_shareholder", None, entity_id=comp)):
            via = next(x for x in rows if x["person_id"] == r["entity_id"])
            if any(x["person_id"] == r["holder_id"] for x in rows):
                continue
            eff = r.get("ubo_effective_pct") or ((r.get("share_pct") or 0) * (via["pct"] or 0) / 100)
            rows.append({"name": r["holder_name"], "pct": None, "indirect_pct": round(eff, 2), "ubo": bool(r.get("ubo_flag")),
                         "nationality": r.get("nationality"), "kind": r.get("holder_kind") or "person", "borrower_id": None,
                         "person_id": r["holder_id"], "via": via["name"], "birth_year": r.get("birth_year"), "source": "b360_shareholder"})
        srcs.append(_src("b360_shareholder", entity_id=comp))
    direct = sum((r["pct"] or 0) for r in rows if r.get("pct") is not None)
    sh = {"rows": rows, "identified_pct": round(direct, 2), "ubo_count": sum(1 for r in rows if r["ubo"]),
          "ubo_identified": any(r["ubo"] for r in rows), "provided_by": "b360_shareholder", "source": srcs}

    # ---- board and key persons
    bd_rows = S.records(S.read("b360_board", None, entity_id=sid))
    linked_ids = sorted({x.strip() for r in bd_rows for x in str(r.get("linked_borrower_ids") or "").split(";") if x.strip()})
    la = F.borrower_attrs([x for x in linked_ids if not x.startswith("XE-")])
    xe = [x for x in linked_ids if x.startswith("XE-") and x not in attrs]
    if xe:
        attrs.update(entity_attrs(S.records(S.read("b360_entity", None, entity_id=xe)), pid))
    la.update({k: v for k, v in attrs.items() if k in linked_ids})
    people: dict[str, dict[str, Any]] = {}
    for r in bd_rows:
        d = people.setdefault(r["person_id"], {"person_id": r["person_id"], "name": r["person_name"], "roles": [], "other": set(),
                                               "dirs": [], "key": False, "nationality": r.get("nationality"), "appointed": r.get("appointed")})
        d["roles"].append(str(r.get("role") or "director").replace("_", " ").capitalize() if str(r.get("role")) not in ("ceo", "cfo", "gm")
                          else str(r["role"]).upper())
        d["key"] = d["key"] or bool(r.get("key_person_flag"))
        d["other"] |= {x.strip() for x in str(r.get("linked_borrower_ids") or "").split(";") if x.strip()}
        od = r.get("other_directorships") or []
        if isinstance(od, str):
            import json
            try:
                od = json.loads(od)
            except ValueError:
                od = []
        d["dirs"] += [f"{x.get('role', 'director')} of {x.get('entity_name') or x.get('entity_id')}" for x in od if isinstance(x, dict)]
    bd_out = []
    for d in people.values():
        others = [{"borrower_id": x, "name": la.get(x, {}).get("name", x), "status": la.get(x, {}).get("status", "not in book"),
                   "ews_band": la.get(x, {}).get("ews_band", "none"), "ead": la.get(x, {}).get("ead", 0.0), "href": la.get(x, {}).get("href")}
                  for x in sorted(d["other"])]
        bd_out.append({"person_id": d["person_id"], "name": d["name"], "roles": d["roles"], "key_person": d["key"],
                       "nationality": d["nationality"], "appointed": d["appointed"], "other_borrowers": others,
                       "other_directorships": "; ".join(d["dirs"]) or None,
                       "linked_to_stressed": [o["name"] for o in others if o["status"] in ("classified", "in litigation", "in arrears")
                                              or o["ews_band"] in ("high", "critical")]})
    order = {"Chairman": 0, "CEO": 1, "GM": 2, "Director": 3, "CFO": 4}
    bd_out.sort(key=lambda x: (min(order.get(r, 9) for r in x["roles"]) if x["roles"] else 9, x["name"]))
    bd = {"rows": bd_out, "people": len(bd_out), "linked_people": sum(1 for x in bd_out if x["other_borrowers"]),
          "other_borrowers": linked_ids, "attrs": la, "source": [_src("b360_board", entity_id=sid)]}

    # ---- insiders, ownership changes
    ins_rows = S.records(S.read("b360_insider_link", None, entity_id=list(by)))
    ins = {"rows": [{"party": r["person_name"], "borrower_id": r["entity_id"], "entity": attrs.get(r["entity_id"], {}).get("name"),
                     "link": str(r.get("link_kind") or "insider").replace("_", " "), "role": r.get("staff_role"),
                     "relationship": r.get("relationship"), "pct": r.get("share_pct"), "disclosed": bool(r.get("disclosed_flag")),
                     "detected_by": r.get("detected_by"), "detail": r.get("note")} for r in ins_rows],
           "count": len(ins_rows), "provided": True, "source": [_src("b360_insider_link", entity_id=list(by))]}
    since = _years_before(AS_OF_DATE, 2)
    oc_rows = [r for r in S.records(S.read("b360_ownership_change", None, entity_id=list(by))) if str(r.get("change_date") or "") >= since]
    oc = {"rows": [{"date": r["change_date"], "entity": attrs.get(r["entity_id"], {}).get("name", r["entity_id"]),
                    "holder": r["holder_name"], "from": f"{r.get('from_pct') or 0:.1f}%", "to": f"{r.get('to_pct') or 0:.1f}%",
                    "pct": r.get("to_pct"), "kind": r.get("kind"), "disclosed": bool(r.get("disclosed_flag")),
                    "detail": r.get("note"), "source": "b360_ownership_change"} for r in sorted(oc_rows, key=lambda r: r["change_date"])],
          "count": len(oc_rows), "lookback": "2 years", "source": [_src("b360_ownership_change", entity_id=list(by))]}

    # ---- shared collateral, guarantees and their perfection
    sc_e = [e for e in edges if e["rel_type"] == "shared_collateral"]
    assets = [{"collateral_id": e["edge_id"], "type": e.get("detail") or "shared collateral", "market_value": e.get("amount_mn"),
               "claims": [{"borrower_id": x, "name": attrs.get(x, {}).get("name", x), "is_self": x == sid, "status": attrs.get(x, {}).get("status")}
                          for x in (e["source_id"], e["target_id"])], "total_pct": None, "over_pledged": False,
               "co_claimants": 1} for e in sc_e if sid in (e["source_id"], e["target_id"])]
    sc = {"assets": assets, "count": len(assets), "over_pledged": 0,
          "co_claimant_ids": sorted({c["borrower_id"] for a in assets for c in a["claims"] if not c["is_self"]}),
          "source": [_src("b360_edge", group_id=gid, rel_type="shared_collateral")]}
    sec = S.records(S.read("dd_security", None, proposal_id=pid))
    g_rows = [{"direction": "received" if e["target_id"] == sid else "given", "guarantor_id": e["source_id"], "guaranteed_id": e["target_id"],
               "facility_id": None, "amount": e.get("amount_mn"), "basis": e.get("detail")}
              for e in edges if e["rel_type"] == "guarantees" and sid in (e["source_id"], e["target_id"])]
    for s_ in sec:
        if s_.get("kind") in ("personal_guarantee", "corporate_guarantee"):
            g_rows.append({"direction": "received", "guarantor_id": s_.get("provider_entity_id") or s_.get("provider"),
                           "guarantor": s_.get("provider"), "guaranteed_id": sid, "facility_id": s_.get("limit_id"),
                           "amount": s_.get("amount_mn"), "basis": s_["kind"].replace("_", " "), "perfection": s_.get("perfection_status"),
                           "net_worth_mn": s_.get("net_worth_mn"), "net_worth_statement_date": s_.get("net_worth_statement_date"),
                           "pari_passu": bool(s_.get("pari_passu_flag"))})
    unperf = [{"guarantor_id": s_.get("provider") or s_.get("provider_entity_id"), "amount": s_.get("amount_mn") or 0.0,
               "kind": s_.get("kind"), "deadline": s_.get("perfection_deadline")}
              for s_ in sec if s_.get("perfection_status") in ("pending", "not_perfected")]
    gu = {"rows": g_rows, "unperfected": unperf, "source": [_src("b360_edge", group_id=gid, rel_type="guarantees"),
                                                            _src("dd_security", proposal_id=pid)]}

    # ---- connected parties: every related entity and person-linked borrower with its status
    why: dict[str, set[str]] = {}
    for e in members:
        if e["entity_id"] != sid:
            why.setdefault(e["entity_id"], set()).add("group")
    for e in edges:
        if sid in (e["source_id"], e["target_id"]):
            other = e["target_id"] if e["source_id"] == sid else e["source_id"]
            if other and str(other).startswith("XE-"):
                why.setdefault(other, set()).add(EDGE_OUT.get(e["rel_type"], e["rel_type"]))
    for x in linked_ids:
        why.setdefault(x, set()).add("common director or key person")
    allattrs = {**attrs, **la}
    cps = []
    for k, rs in why.items():
        a = allattrs.get(k)
        if not a:
            continue
        cps.append({"borrower_id": k, "name": a["name"], "links": sorted(rs), "ead": a.get("ead", 0.0), "rating": a.get("rating"),
                    "status": a["status"], "classified": a["classified"], "in_arrears": a["in_arrears"], "in_litigation": a["in_litigation"],
                    "watchlist": a.get("watchlist", False), "ews_band": a.get("ews_band", "none"), "max_dpd_4q": a.get("max_dpd_4q", 0),
                    "worst_stage": a.get("worst_stage"), "reasons": a.get("reasons", []), "classified_basis": a.get("classified_basis", []),
                    "note": a.get("credit_status_note"), "href": a.get("href")})
    sev = {"classified": 0, "in litigation": 1, "in arrears": 2, "watchlist": 3, "performing": 4}
    cps.sort(key=lambda r: (sev.get(r["status"], 9), -r["ead"], r["borrower_id"]))
    bad = [r for r in cps if r["status"] in ("classified", "in litigation", "in arrears")]
    cp = {"rows": cps, "count": len(cps), "classified": sum(r["classified"] for r in cps), "in_arrears": sum(r["in_arrears"] for r in cps),
          "in_litigation": sum(r["in_litigation"] for r in cps), "adverse": [r["borrower_id"] for r in bad],
          "adverse_ead": round(sum(r["ead"] for r in bad), 4),
          "source": [_src("b360_entity", group_id=gid), _src("bureau_entity_report", proposal_id=pid), _src("dd_group_exposure", proposal_id=pid)]}
    return {"proposal_id": pid, "obligor": {"id": sid, "name": p["obligor"]["name"], "existing": bool(p["obligor"].get("existing"))},
            "as_of": AS_OF, "mode": "entity", "structure": st, "shareholders": sh, "board": {k: v for k, v in bd.items() if k != "attrs"},
            "insiders": ins, "ownership_changes": oc, "shared_collateral": sc, "guarantees": gu, "connected_parties": cp,
            "_attrs": allattrs}
