"""Group facts for one deal, from the Borrower 360 relations (PLAN_R12 §1.4, I24).

    parent, subsidiaries, sister companies           rel_group_quarter, rel_edge_quarter (GROUP)
    shareholders and UBOs with %                     b360_shareholder (E) | rel_person_role (Owner) + GROUP edges
    board and key persons, links to other borrowers  b360_board (E) | rel_person_role (Director, Chairman, CEO)
    insider and staff links                          b360_insider_link (E)
    ownership changes                                b360_ownership_change (E) | rel_group_quarter history
    shared collateral                                rel_shared_collateral
    connected parties classified / in arrears /      corp_facility_quarter, cls_exposure, cls_reason (SICR-LITIGATION),
    in litigation                                    bureau_corp_quarter, corp_exposure (EWS band),
                                                     bureau_entity_report (E, court cases)

Every block carries `source`: the relation(s) and the row keys it was read from.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.dealdesk.group import deal, sources as S

AS_OF = deal.AS_OF
KEY_ROLES = ("Chairman", "CEO", "Director", "Managing Director", "CFO", "Board member", "Key person")
HISTORY_QUARTERS = 8  # ownership-change look-back (two years)


def _quarters_back(q: str, n: int) -> str:
    y, k = int(q[:4]), int(q[-1])
    idx = y * 4 + (k - 1) - n
    return f"{idx // 4}Q{idx % 4 + 1}"


def _src(relation: str, **keys: Any) -> dict[str, Any]:
    loc = S.locate(relation) or {}
    return {"domain": loc.get("domain"), "relation": relation, "keys": {k: v for k, v in keys.items() if v is not None}}


# ------------------------------------------------------------------ book attributes of borrowers


def borrower_attrs(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Name, rating, watchlist, EAD, worst stage, max DPD (4 quarters), EWS band, classification and litigation."""
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    b = S.read("corp_borrower_quarter", ["borrower_id", "borrower_name", "sector", "rating_current", "watchlist_flag",
                                          "watchlist_reason", "restructured_flag"], borrower_id=ids, reporting_quarter=AS_OF)
    qs = [_quarters_back(AS_OF, i) for i in range(4)]
    f = S.read("corp_facility_quarter", ["facility_id", "borrower_id", "reporting_quarter", "ead_sar_mn", "limit_sar_mn",
                                          "stage", "dpd_days", "default_flag"], borrower_id=ids, reporting_quarter=qs)
    e = S.read("corp_exposure", ["borrower_id", "ews_band", "ews_score"], borrower_id=ids, reporting_quarter=AS_OF)
    c = S.read("cls_exposure", ["obligor_id", "stage", "utp_flag", "watch_status", "restructured_flag"], obligor_id=ids)
    r = S.read("cls_reason", ["obligor_id", "code", "text"], obligor_id=ids)
    bu = S.read("bureau_corp_quarter", ["borrower_id", "external_dpd_days", "external_default_flag"], borrower_id=ids,
                reporting_quarter=AS_OF)
    out: dict[str, dict[str, Any]] = {}
    for row in S.records(b):
        out[row["borrower_id"]] = {"borrower_id": row["borrower_id"], "name": row["borrower_name"], "sector": row["sector"],
                                   "rating": row["rating_current"], "watchlist": bool(row["watchlist_flag"]),
                                   "watchlist_reason": row.get("watchlist_reason"), "ead": 0.0, "limit": 0.0,
                                   "worst_stage": None, "max_dpd_4q": 0, "default": False, "ews_band": "none",
                                   "classified": False, "in_arrears": False, "in_litigation": False, "utp": False,
                                   "restructured": bool(row.get("restructured_flag")), "external_dpd": None,
                                   "external_default": False, "reasons": []}
    now = f[f["reporting_quarter"] == AS_OF] if len(f) else f
    for bid, g in (now.groupby("borrower_id") if len(now) else []):
        if bid in out:
            out[bid]["ead"] = float(g["ead_sar_mn"].sum())
            out[bid]["limit"] = float(g["limit_sar_mn"].sum())
            out[bid]["worst_stage"] = int(g["stage"].max())
            out[bid]["default"] = bool(g["default_flag"].max())
    for bid, g in (f.groupby("borrower_id") if len(f) else []):
        if bid in out:
            out[bid]["max_dpd_4q"] = int(g["dpd_days"].max())
    order = {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
    for bid, g in (e.groupby("borrower_id") if len(e) else []):
        if bid in out:
            bands = [x for x in g["ews_band"].dropna().tolist()]
            out[bid]["ews_band"] = max(bands, key=lambda x: order.get(x, 0)) if bands else "none"
    for bid, g in (c.groupby("obligor_id") if len(c) else []):
        if bid in out:
            out[bid]["utp"] = bool(g["utp_flag"].fillna(0).max())
            out[bid]["restructured"] = out[bid]["restructured"] or bool(g["restructured_flag"].fillna(0).max())
    for bid, g in (r.groupby("obligor_id") if len(r) else []):
        if bid in out:
            codes = sorted(set(g["code"].dropna()))
            out[bid]["reasons"] = codes
            out[bid]["in_litigation"] = any("LITIGATION" in x for x in codes)
    for row in S.records(bu):
        if row["borrower_id"] in out:
            out[row["borrower_id"]]["external_dpd"] = row.get("external_dpd_days")
            out[row["borrower_id"]]["external_default"] = bool(row.get("external_default_flag"))
    # court cases from E's per-entity bureau report, when published
    ber = S.read("bureau_entity_report", None, entity_id=ids) if any(str(i).startswith("XE-") for i in ids) else None
    for row in (S.records(ber) if ber is not None else []):
        bid = S.pick(row, "entity_id", "borrower_id", "obligor_id")
        if bid in out and (S.pick(row, "court_cases_n", "court_cases", default=0) or 0) > 0:
            out[bid]["in_litigation"] = True
            out[bid]["reasons"] = sorted(set(out[bid]["reasons"]) | {"BUREAU-COURT-CASE"})
    for a in out.values():
        basis = [x for x, ok in (("stage 3", (a["worst_stage"] or 0) >= 3), ("in default", a["default"]),
                                 ("unlikely to pay", a["utp"]), ("default on the bureau", a["external_default"])) if ok]
        a["classified"] = bool(basis)
        a["classified_basis"] = basis
        a["in_arrears"] = bool(a["max_dpd_4q"] >= 30 or (a["external_dpd"] or 0) >= 30)
        a["status"] = ("classified" if a["classified"] else "in litigation" if a["in_litigation"]
                       else "in arrears" if a["in_arrears"] else "watchlist" if a["watchlist"] else "performing")
        a["href"] = f"/borrower-360?domain=corporate&customer_id={a['borrower_id']}&period={AS_OF}"
    return out


# ------------------------------------------------------------------ structure


def structure(p: dict[str, Any]) -> dict[str, Any]:
    ob = p["obligor"]
    focal = deal.focal_id(p)
    rg = S.read("rel_group_quarter", None, reporting_quarter=AS_OF, borrower_id=focal) if focal else pd.DataFrame()
    gid = str(rg["group_id"].iloc[0]) if len(rg) else str(ob.get("group_id") or "")
    members = S.read("rel_group_quarter", None, reporting_quarter=AS_OF, group_id=gid) if gid else pd.DataFrame()
    mem = S.records(members)
    attrs = borrower_attrs([m["borrower_id"] for m in mem] + ([focal] if focal else []))
    parent_id = next((m["borrower_id"] for m in mem if m["role"] == "parent"), None)
    me = next((m for m in mem if m["borrower_id"] == focal), None)

    def node(m: dict[str, Any], relation: str) -> dict[str, Any]:
        a = attrs.get(m["borrower_id"], {})
        return {"borrower_id": m["borrower_id"], "name": a.get("name") or m["borrower_id"], "link": relation,
                "role": m.get("role"), "ownership_pct": m.get("ownership_pct"), "ead": a.get("ead", 0.0),
                "rating": a.get("rating"), "status": a.get("status", "not in book"), "ews_band": a.get("ews_band", "none"),
                "href": a.get("href")}

    parent = None
    subsidiaries, sisters = [], []
    if mem:
        if focal and parent_id == focal:
            subsidiaries = [node(m, "subsidiary" if m["role"] == "subsidiary" else "affiliate") for m in mem if m["borrower_id"] != focal]
        else:
            if parent_id:
                parent = node(next(m for m in mem if m["borrower_id"] == parent_id), "parent")
            sisters = [node(m, "sister") for m in mem if m["borrower_id"] not in (focal, parent_id)]
    # the focal's own holdings by GROUP edges (it may own companies outside the relationship group)
    own = S.read("rel_edge_quarter", ["edge_id", "rel_type", "source_borrower_id", "target_borrower_id", "ownership_pct",
                                      "relation_detail"], reporting_quarter=AS_OF, rel_type="GROUP",
                 source_borrower_id=focal) if focal else pd.DataFrame()
    known = {x["borrower_id"] for x in subsidiaries + sisters} | {parent_id, focal}
    extra = [r for r in S.records(own) if r["target_borrower_id"] not in known]
    if extra:
        xa = borrower_attrs([r["target_borrower_id"] for r in extra])
        attrs.update(xa)
        for r in extra:
            subsidiaries.append(node({"borrower_id": r["target_borrower_id"], "role": r["relation_detail"],
                                      "ownership_pct": r["ownership_pct"]}, "subsidiary"))
    group_name = (mem[0]["group_name"] if mem else None) or ob.get("group_name") or ob.get("name")
    return {"group_id": gid or None, "group_name": group_name, "standalone": not mem,
            "focal": {"borrower_id": focal or None, "name": ob.get("name"), "in_book": focal in attrs,
                      "role": (me or {}).get("role"), "ownership_pct": (me or {}).get("ownership_pct")},
            "parent": parent, "subsidiaries": subsidiaries, "sisters": sisters, "members": len(mem) or 1,
            "member_ids": sorted({m["borrower_id"] for m in mem} | ({focal} if focal else set())),
            "attrs": attrs,
            "source": [_src("rel_group_quarter", reporting_quarter=AS_OF, group_id=gid or None),
                       _src("rel_edge_quarter", reporting_quarter=AS_OF, rel_type="GROUP", source_borrower_id=focal or None),
                       _src("corp_borrower_quarter", reporting_quarter=AS_OF), _src("corp_facility_quarter", reporting_quarter=AS_OF)]}


# ------------------------------------------------------------------ people


def _people_rows(ids: list[str]) -> list[dict[str, Any]]:
    d = S.read("rel_person_role", ["person_id", "person_name", "borrower_id", "role", "ownership_pct", "valid_from_quarter",
                                    "valid_to_quarter"], borrower_id=ids)
    out = []
    for r in S.records(d):
        if r.get("valid_to_quarter") and str(r["valid_to_quarter"]) < AS_OF:
            continue
        out.append(r)
    return out


def shareholders(p: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    e = pd.DataFrame()  # book borrowers: the relationship domain (R12 demo entities: facts_entity.py)
    rows: list[dict[str, Any]] = []
    if len(e):
        for r in S.records(e):
            rows.append({"name": S.pick(r, "owner_name", "shareholder_name", "name"),
                         "pct": S.pick(r, "ownership_pct", "pct", "share_pct"),
                         "ubo": bool(S.pick(r, "ubo_flag", "is_ubo", "beneficial_owner", default=False)),
                         "nationality": S.pick(r, "nationality"), "kind": S.pick(r, "owner_kind", "owner_type", default="person"),
                         "borrower_id": S.pick(r, "owner_borrower_id", "owner_cif"), "person_id": S.pick(r, "person_id", "owner_id"),
                         "source": "b360_shareholder"})
        src = []
    else:
        src = []
        if focal:
            for r in _people_rows([focal]):
                if r["role"] == "Owner":
                    rows.append({"name": r["person_name"], "pct": r["ownership_pct"], "ubo": (r["ownership_pct"] or 0) >= 25,
                                 "nationality": None, "kind": "person", "borrower_id": None, "person_id": r["person_id"],
                                 "source": "rel_person_role"})
            src.append(_src("rel_person_role", borrower_id=focal, role="Owner"))
            g = S.read("rel_edge_quarter", ["source_borrower_id", "ownership_pct"], reporting_quarter=AS_OF, rel_type="GROUP",
                       target_borrower_id=focal)
            ga = borrower_attrs(g["source_borrower_id"].tolist()) if len(g) else {}
            for r in S.records(g):
                rows.append({"name": ga.get(r["source_borrower_id"], {}).get("name") or r["source_borrower_id"],
                             "pct": r["ownership_pct"], "ubo": False, "nationality": None, "kind": "company",
                             "borrower_id": r["source_borrower_id"], "person_id": None, "source": "rel_edge_quarter"})
            src.append(_src("rel_edge_quarter", reporting_quarter=AS_OF, rel_type="GROUP", target_borrower_id=focal))
            # a person owning the parent is the ultimate owner behind a company shareholder
            parents = [r["borrower_id"] for r in rows if r["kind"] == "company" and r["borrower_id"]]
            if parents:
                for r in _people_rows(parents):
                    if r["role"] == "Owner":
                        via = next(x for x in rows if x["borrower_id"] == r["borrower_id"])
                        eff = (r["ownership_pct"] or 0) * (via["pct"] or 0) / 100
                        rows.append({"name": r["person_name"], "pct": None, "indirect_pct": round(eff, 2), "ubo": eff >= 25,
                                     "nationality": None, "kind": "person", "borrower_id": None, "person_id": r["person_id"],
                                     "via": via["name"], "source": "rel_person_role"})
                src.append(_src("rel_person_role", borrower_id=parents, role="Owner"))
    direct = sum((r["pct"] or 0) for r in rows if r.get("pct") is not None)
    ubos = [r for r in rows if r["ubo"]]
    return {"rows": rows, "identified_pct": round(direct, 2), "ubo_count": len(ubos),
            "ubo_identified": bool(ubos), "provided_by": "b360_shareholder" if len(e) else "relationship domain", "source": src}


def board(p: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    e = pd.DataFrame()  # book borrowers: the relationship domain (R12 demo entities: facts_entity.py)
    people: dict[str, dict[str, Any]] = {}
    src = []
    if len(e):
        for r in S.records(e):
            key = str(S.pick(r, "person_id", "person_name", "name"))
            d = people.setdefault(key, {"person_id": S.pick(r, "person_id"), "name": S.pick(r, "person_name", "name"),
                                        "roles": [], "other_ids": set(), "other_text": []})
            d["roles"].append(S.pick(r, "role", default="Director"))
            other = S.pick(r, "other_borrower_ids", "other_directorship_ids")
            if other:
                d["other_ids"] |= {x.strip() for x in str(other).replace(";", ",").split(",") if x.strip()}
            txt = S.pick(r, "other_directorships")
            if txt:
                d["other_text"].append(str(txt))
    if focal:
        for r in _people_rows([focal]):
            if r["role"] == "Owner":
                continue
            d = people.setdefault(r["person_id"], {"person_id": r["person_id"], "name": r["person_name"], "roles": [],
                                                   "other_ids": set(), "other_text": []})
            if r["role"] not in d["roles"]:
                d["roles"].append(r["role"])
        src.append(_src("rel_person_role", borrower_id=focal))
    pids = [d["person_id"] for d in people.values() if d["person_id"]]
    links = S.read("rel_person_role", ["person_id", "borrower_id", "role"], person_id=pids) if pids else pd.DataFrame()
    for r in S.records(links):
        if r["borrower_id"] != focal:
            for d in people.values():
                if d["person_id"] == r["person_id"]:
                    d["other_ids"].add(r["borrower_id"])
    other_attrs = borrower_attrs(sorted({x for d in people.values() for x in d["other_ids"]}))
    out = []
    for d in people.values():
        others = [{"borrower_id": x, "name": other_attrs.get(x, {}).get("name", x), "status": other_attrs.get(x, {}).get("status", "not in book"),
                   "ews_band": other_attrs.get(x, {}).get("ews_band", "none"), "ead": other_attrs.get(x, {}).get("ead", 0.0),
                   "href": other_attrs.get(x, {}).get("href")} for x in sorted(d["other_ids"])]
        out.append({"person_id": d["person_id"], "name": d["name"], "roles": d["roles"], "other_borrowers": others,
                    "other_directorships": "; ".join(d["other_text"]) or None,
                    "linked_to_stressed": [o["name"] for o in others if o["status"] in ("classified", "in litigation", "in arrears")
                                           or o["ews_band"] in ("high", "critical")]})
    out.sort(key=lambda x: (min((KEY_ROLES.index(r) if r in KEY_ROLES else 9) for r in x["roles"]) if x["roles"] else 9, x["name"] or ""))
    if pids:
        src.append(_src("rel_person_role", person_id=pids))
    return {"rows": out, "people": len(out), "linked_people": sum(1 for x in out if x["other_borrowers"]),
            "other_borrowers": sorted({o["borrower_id"] for x in out for o in x["other_borrowers"]}),
            "attrs": other_attrs, "source": src}


def insiders(p: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    e = pd.DataFrame()  # the insider register covers the R12 demo entities only (facts_entity.py)
    rows = [{"party": S.pick(r, "party_name", "person_name", "name"), "borrower_id": S.pick(r, "borrower_id", "obligor_id"),
             "link": S.pick(r, "link_type", "relation", "insider_type", default="insider"),
             "role": S.pick(r, "role", "staff_role", "position"), "detail": S.pick(r, "detail", "description", "note"),
             "pct": S.pick(r, "ownership_pct", "pct")} for r in S.records(e)]
    return {"rows": rows, "count": len(rows), "provided": False,
            "note": "The insider and staff register (b360_insider_link) covers the R12 demo groups; not provided for this book borrower.",
            "source": []}


def ownership_changes(p: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    e = pd.DataFrame()  # book borrowers: rel_group_quarter history (R12 demo entities: facts_entity.py)
    rows = [{"date": str(S.pick(r, "change_date", "date", "effective_date", default="")), "from": S.pick(r, "from_owner", "previous_owner"),
             "to": S.pick(r, "to_owner", "new_owner"), "pct": S.pick(r, "pct", "ownership_pct", "share_pct"),
             "detail": S.pick(r, "detail", "description", "note"), "source": "b360_ownership_change"} for r in S.records(e)]
    src: list[dict[str, Any]] = []
    if not rows and focal:
        then = _quarters_back(AS_OF, HISTORY_QUARTERS)
        h = S.read("rel_group_quarter", ["reporting_quarter", "group_id", "role", "ownership_pct", "parent_borrower_id"],
                   borrower_id=focal, reporting_quarter=[then, AS_OF])
        a = {r["reporting_quarter"]: r for r in S.records(h)}
        x, y = a.get(then), a.get(AS_OF)
        if y and not x:
            rows.append({"date": AS_OF, "from": "standalone", "to": f"member of group {y['group_id']}", "pct": y["ownership_pct"],
                         "detail": f"Joined the group after {then}.", "source": "rel_group_quarter"})
        elif x and y and (x["parent_borrower_id"] != y["parent_borrower_id"] or abs((x["ownership_pct"] or 0) - (y["ownership_pct"] or 0)) >= 5):
            rows.append({"date": AS_OF, "from": f"{x['parent_borrower_id']} ({x['ownership_pct']:.1f}%)",
                         "to": f"{y['parent_borrower_id']} ({y['ownership_pct']:.1f}%)", "pct": y["ownership_pct"],
                         "detail": f"Parent or holding changed between {then} and {AS_OF}.", "source": "rel_group_quarter"})
        src.append(_src("rel_group_quarter", borrower_id=focal, reporting_quarter=[then, AS_OF]))
    return {"rows": rows, "count": len(rows), "lookback": f"{HISTORY_QUARTERS} quarters", "source": src}


def shared_collateral(p: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    if not focal:
        return {"assets": [], "count": 0, "over_pledged": 0, "source": []}
    mine = S.read("rel_shared_collateral", ["collateral_id"], reporting_quarter=AS_OF, borrower_id=focal)
    cids = sorted(set(mine["collateral_id"])) if len(mine) else []
    allc = S.read("rel_shared_collateral", None, reporting_quarter=AS_OF, collateral_id=cids) if cids else pd.DataFrame()
    recs = S.records(allc)
    at = borrower_attrs([r["borrower_id"] for r in recs])
    assets: dict[str, dict[str, Any]] = {}
    for r in recs:
        a = assets.setdefault(r["collateral_id"], {"collateral_id": r["collateral_id"], "type": r["collateral_type"],
                                                   "market_value": r["market_value_sar_mn"], "claims": [], "total_pct": 0.0})
        a["claims"].append({"borrower_id": r["borrower_id"], "name": at.get(r["borrower_id"], {}).get("name", r["borrower_id"]),
                            "facility_id": r["facility_id"], "claim": r["claim_sar_mn"], "allocation_pct": r["allocation_pct"],
                            "status": at.get(r["borrower_id"], {}).get("status"), "is_self": r["borrower_id"] == focal})
        a["total_pct"] += r["allocation_pct"] or 0
    for a in assets.values():
        a["total_pct"] = round(a["total_pct"], 2)
        a["over_pledged"] = a["total_pct"] > 100.0
        a["co_claimants"] = sum(1 for c in a["claims"] if not c["is_self"])
    return {"assets": list(assets.values()), "count": len(assets), "over_pledged": sum(1 for a in assets.values() if a["over_pledged"]),
            "co_claimant_ids": sorted({c["borrower_id"] for a in assets.values() for c in a["claims"] if not c["is_self"]}),
            "source": [_src("rel_shared_collateral", reporting_quarter=AS_OF, collateral_id=cids or None)]}


def guarantees(st: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    if not focal:
        return {"rows": [], "source": []}
    g1 = S.read("rel_edge_quarter", ["edge_id", "source_borrower_id", "target_borrower_id", "facility_id", "guarantee_amount_sar_mn",
                                     "relation_detail"], reporting_quarter=AS_OF, rel_type="GUARANTEES", target_borrower_id=focal)
    g2 = S.read("rel_edge_quarter", ["edge_id", "source_borrower_id", "target_borrower_id", "facility_id", "guarantee_amount_sar_mn",
                                     "relation_detail"], reporting_quarter=AS_OF, rel_type="GUARANTEES", source_borrower_id=focal)
    recs = S.records(g1) + S.records(g2)
    perf = S.read("col_guarantee", ["guarantor_cif", "obligor_id", "amount_sar_mn", "perfected"], obligor_id=focal)
    unperfected = [r for r in S.records(perf) if not r.get("perfected")]
    rows = [{"direction": "received" if r["target_borrower_id"] == focal else "given", "guarantor_id": r["source_borrower_id"],
             "guaranteed_id": r["target_borrower_id"], "facility_id": r["facility_id"], "amount": r["guarantee_amount_sar_mn"],
             "basis": r["relation_detail"]} for r in recs]
    return {"rows": rows, "unperfected": [{"guarantor_id": r["guarantor_cif"], "amount": r["amount_sar_mn"]} for r in unperfected],
            "source": [_src("rel_edge_quarter", reporting_quarter=AS_OF, rel_type="GUARANTEES", borrower_id=focal),
                       _src("col_guarantee", obligor_id=focal)]}


def connected_parties(st: dict[str, Any], bd: dict[str, Any], sc: dict[str, Any], gu: dict[str, Any],
                      sh: dict[str, Any]) -> dict[str, Any]:
    focal = st["focal"]["borrower_id"]
    why: dict[str, set[str]] = {}

    def add(bid: str | None, reason: str) -> None:
        if bid and bid != focal:
            why.setdefault(bid, set()).add(reason)

    for m in st["member_ids"]:
        add(m, "group")
    for x in bd["other_borrowers"]:
        add(x, "common director or key person")
    for x in sc.get("co_claimant_ids", []):
        add(x, "shared collateral")
    for g in gu["rows"]:
        add(g["guarantor_id"] if g["direction"] == "received" else g["guaranteed_id"], "guarantee")
    for r in sh["rows"]:
        add(r.get("borrower_id"), "shareholder")
    rp = S.read("col_related_party", ["party_cif", "party_name", "relation"], obligor_id=focal) if focal else pd.DataFrame()
    for r in S.records(rp):
        add(r["party_cif"], "related-party register")
    attrs = {**st["attrs"], **bd.get("attrs", {})}
    need = [k for k in why if k not in attrs]
    if need:
        attrs.update(borrower_attrs(need))
    rows = []
    for bid, rs in why.items():
        a = attrs.get(bid)
        if not a:
            continue
        rows.append({"borrower_id": bid, "name": a["name"], "links": sorted(rs), "ead": a["ead"], "rating": a["rating"],
                     "status": a["status"], "classified": a["classified"], "in_arrears": a["in_arrears"],
                     "in_litigation": a["in_litigation"], "watchlist": a["watchlist"], "ews_band": a["ews_band"],
                     "max_dpd_4q": a["max_dpd_4q"], "worst_stage": a["worst_stage"], "reasons": a["reasons"],
                     "classified_basis": a.get("classified_basis", []), "href": a["href"]})
    sev = {"classified": 0, "in litigation": 1, "in arrears": 2, "watchlist": 3, "performing": 4}
    rows.sort(key=lambda r: (sev.get(r["status"], 9), -r["ead"], r["borrower_id"]))
    bad = [r for r in rows if r["status"] in ("classified", "in litigation", "in arrears")]
    return {"rows": rows, "count": len(rows), "classified": sum(r["classified"] for r in rows),
            "in_arrears": sum(r["in_arrears"] for r in rows), "in_litigation": sum(r["in_litigation"] for r in rows),
            "adverse": [r["borrower_id"] for r in bad], "adverse_ead": round(sum(r["ead"] for r in bad), 4),
            "source": [_src("col_related_party", obligor_id=focal), _src("cls_exposure"), _src("cls_reason"),
                       _src("bureau_corp_quarter", reporting_quarter=AS_OF), _src("corp_exposure", reporting_quarter=AS_OF),
                       _src("bureau_entity_report")]}


def build(pid: str) -> dict[str, Any]:
    """Every group fact for one deal (no exposure test: see exposure.py). A deal whose obligor is a Borrower 360
    entity (the R12 demo groups) reads the entity relations (facts_entity.py); a book borrower reads the
    relationship domain."""
    p = deal.get(pid)
    from backend.dealdesk.group import facts_entity
    subj = facts_entity.subject(p)
    if subj is not None:
        out = facts_entity.build(pid, p, subj)
        out.pop("_attrs", None)
        return out
    st = structure(p)
    sh = shareholders(p, st)
    bd = board(p, st)
    ins = insiders(p, st)
    oc = ownership_changes(p, st)
    sc = shared_collateral(p, st)
    gu = guarantees(st)
    cp = connected_parties(st, bd, sc, gu, sh)
    st = {k: v for k, v in st.items() if k != "attrs"}
    bd = {k: v for k, v in bd.items() if k != "attrs"}
    return {"proposal_id": pid, "obligor": {"id": deal.focal_id(p), "name": p["obligor"]["name"],
                                              "existing": bool(p["obligor"].get("existing"))},
            "as_of": AS_OF, "mode": "book", "structure": st, "shareholders": sh, "board": bd, "insiders": ins, "ownership_changes": oc,
            "shared_collateral": sc, "guarantees": gu, "connected_parties": cp}
