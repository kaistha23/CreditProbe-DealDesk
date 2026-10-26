"""Borrower 360 relationships: the graph around one borrower or customer, and the analytics beside it.

Read-only, from the relationship domain (data/relationships/rel-saudi-v1) and the books. Corporate: group (parent,
subsidiaries, affiliates), supplier, customer (buyer), guarantor, shared-collateral and shared owner or director links.
Retail: household and employer.

A node is a book borrower (or customer) with its Early Warning band and exposure at the period, or a person who owns
or directs two or more of the companies drawn. An edge is a relationship valid at the period. `kind` is how the edge
reads from the focal borrower outward: a supply edge toward the focal is a *supplier*, one away from it a *customer*,
so the legend can filter the two apart; deeper edges follow their direction relative to the borrower in the middle.

Positions are computed here (a deterministic spring layout), so the same borrower draws the same picture every time.
"""
from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from backend.b360 import paths, service
from backend.b360.store import NotFound, book_periods, clean, rows
from backend.ews_domain import ews_rules as ews

MAX_NODES = 60
TREND_QUARTERS = 8
KINDS = {"group": "Group", "supplier": "Supplier", "customer": "Customer", "guarantor": "Guarantor",
         "collateral": "Shared collateral", "person": "Owner or director", "household": "Household", "employer": "Employer"}
BANDS = ("critical", "high", "moderate", "low", "none")
#: Early Warning bands that count as "in Early Warning" for the contagion view.
WARNED = ("moderate", "high", "critical")


def policy_limit() -> dict[str, Any]:
    """CP-1.2, the connected group limit, from the credit policy itself."""
    pol = json.loads(paths.V5.joinpath("backend", "cockpit_v4", "credit_policy.json").read_text())
    for section in pol["books"]["corporate"]["sections"]:
        for clause in section["clauses"]:
            if clause["clause"] == "CP-1.2":
                return {"clause": "CP-1.2", "title": clause["title"], "rule": clause["rule"],
                        "limit_sar_mn": float(clause["thresholds"]["connected_group_ead_sar_mn"])}
    raise NotFound("The credit policy has no clause CP-1.2.")


def _ids(ids: list[str]) -> list[str]:
    return sorted(set(ids))


# ------------------------------------------------------------------ layout


def layout(node_ids: list[str], hops: dict[str, int], edges: list[tuple[str, str, float]], focal: str) -> dict[str, tuple[float, float]]:
    """A deterministic spring layout, the focal node at the centre. Positions in [-1, 1]."""
    n = len(node_ids)
    if n == 1:
        return {focal: (0.0, 0.0)}
    idx = {k: i for i, k in enumerate(node_ids)}
    rng = np.random.default_rng(int.from_bytes(focal.encode()[-4:].ljust(4, b"0"), "little"))
    pos = np.zeros((n, 2))
    by_hop: dict[int, list[str]] = {}
    for k in node_ids:
        by_hop.setdefault(hops.get(k, 3), []).append(k)
    for h, ks in by_hop.items():
        for j, k in enumerate(sorted(ks)):
            ang = 2 * math.pi * (j + 0.5 * (h % 2)) / max(len(ks), 1)
            r = 0.0 if k == focal else 0.55 * (h if h else 1) + 0.04 * rng.standard_normal()
            pos[idx[k]] = (r * math.cos(ang), r * math.sin(ang))
    area = 4.0
    kconst = 1.25 * math.sqrt(area / n)
    temp = 0.35
    for _ in range(260):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.maximum(np.linalg.norm(delta, axis=-1), 1e-3)
        force = (kconst ** 2 / dist ** 2)[..., None] * delta
        disp = force.sum(axis=1)
        for a, b, w in edges:
            i, j = idx[a], idx[b]
            d = pos[i] - pos[j]
            dd = max(np.linalg.norm(d), 1e-3)
            f = (dd / kconst) * d * max(0.4, min(w, 2.0))
            disp[i] -= f
            disp[j] += f
        length = np.maximum(np.linalg.norm(disp, axis=1), 1e-9)
        pos += disp / length[:, None] * np.minimum(length, temp)[:, None]
        pos[idx[focal]] = (0.0, 0.0)
        temp *= 0.97
    # no two names closer than dmin: a label and a marker never sit on another
    dmin = min(0.34, 1.7 / math.sqrt(n))
    for _ in range(60):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                d = pos[i] - pos[j]
                dist = float(np.linalg.norm(d))
                if dist < dmin:
                    moved = True
                    push = (d / dist if dist > 1e-6 else np.array([1.0, 0.0])) * (dmin - dist) / 2
                    if i != idx[focal]:
                        pos[i] += push
                    if j != idx[focal]:
                        pos[j] -= push
        if not moved:
            break
    scale = np.abs(pos).max() or 1.0
    pos = pos / scale
    return {k: (round(float(pos[idx[k], 0]), 4), round(float(pos[idx[k], 1]), 4)) for k in node_ids}


# --------------------------------------------------------------- corporate


def _edge_strength(e: dict[str, Any]) -> float:
    t = e["rel_type"]
    if t == "GROUP":
        return 1.0 + (e.get("ownership_pct") or 0) / 100
    if t == "GUARANTEES":
        return 0.8 + min((e.get("guarantee_amount_sar_mn") or 0) / 10, 1.0)
    if t == "SUPPLIES":
        return 0.5 + max(e.get("purchase_share_pct") or 0, e.get("revenue_share_pct") or 0) / 100
    return 0.6


def _edges_touching(period: str, ids: list[str], types: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT * FROM rel_edge WHERE reporting_quarter = ? AND (list_contains(?, source_borrower_id) "
           "OR list_contains(?, target_borrower_id))")
    out = rows(sql, [period, ids, ids])
    return [e for e in out if not types or e["rel_type"] in types]


def _node_attrs(period: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    got = rows("""
        WITH f AS (SELECT borrower_id, COUNT(*) AS facilities, SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl,
                          MAX(stage) AS worst_stage, MAX(dpd_days) AS worst_dpd
                   FROM corp_facility WHERE reporting_quarter = ? AND list_contains(?, borrower_id) GROUP BY 1),
             e AS (SELECT borrower_id, MAX(ews_score) AS score
                   FROM ews_corp WHERE reporting_quarter = ? AND list_contains(?, borrower_id) GROUP BY 1)
        SELECT b.borrower_id, b.borrower_name, b.sector, b.sub_sector, b.region, b.rating_current, b.watchlist_flag,
               b.group_id AS book_group_id, b.group_name AS book_group_name,
               f.facilities, f.ead, f.ecl, f.worst_stage, f.worst_dpd, e.score
        FROM corp_borrower b LEFT JOIN f USING (borrower_id) LEFT JOIN e USING (borrower_id)
        WHERE b.reporting_quarter = ? AND list_contains(?, b.borrower_id)""", [period, ids, period, ids, period, ids])
    out = {}
    for r in got:
        r["ews_band"] = ews.band_of("corporate", r.get("score"))
        out[r["borrower_id"]] = r
    return out


def _persons(ids: list[str]) -> list[dict[str, Any]]:
    return rows("SELECT person_id, person_name, borrower_id, role, ownership_pct FROM rel_person "
                "WHERE list_contains(?, borrower_id) ORDER BY person_id, borrower_id, role", [ids])


def _group_of(period: str, owner_id: str) -> list[dict[str, Any]]:
    return rows("""SELECT * FROM rel_group WHERE reporting_quarter = ? AND group_id =
                   (SELECT group_id FROM rel_group WHERE reporting_quarter = ? AND borrower_id = ?)
                   ORDER BY CASE role WHEN 'parent' THEN 0 WHEN 'subsidiary' THEN 1 ELSE 2 END, borrower_id""",
                [period, period, owner_id])


def corporate_graph(owner_id: str, period: str, depth: int = 1, kinds: tuple[str, ...] | None = None,
                    max_nodes: int = MAX_NODES) -> dict[str, Any]:
    period = service.resolve("corporate", owner_id, period)
    depth = 2 if depth >= 2 else 1
    focal = owner_id
    members = _group_of(period, focal)
    hops: dict[str, int] = {focal: 0}
    for m in members:
        hops.setdefault(m["borrower_id"], 1)
    edges: dict[str, dict[str, Any]] = {}

    def take(found: list[dict[str, Any]]) -> None:
        for e in found:
            edges[e["edge_id"]] = e

    frontier = [focal]
    take(_edges_touching(period, [focal]))
    group_ids = [m["borrower_id"] for m in members]
    if group_ids:
        take([e for e in _edges_touching(period, group_ids, ("GROUP",))])
    for e in list(edges.values()):
        for end in (e["source_borrower_id"], e["target_borrower_id"]):
            hops.setdefault(end, 1)
    truncated: dict[str, Any] = {}
    if depth == 2:
        # one more step from each first-ring borrower, the strongest few edges per neighbour
        ring = [k for k, h in hops.items() if h == 1 and k != focal]
        more = _edges_touching(period, ring, ("SUPPLIES", "GUARANTEES", "GROUP", "SHARES_COLLATERAL"))
        per: dict[str, list[dict[str, Any]]] = {}
        for e in more:
            for end in (e["source_borrower_id"], e["target_borrower_id"]):
                if end in ring:
                    per.setdefault(end, []).append(e)
        for k, es in per.items():
            for e in sorted(es, key=lambda x: -_edge_strength(x))[:4]:
                edges.setdefault(e["edge_id"], e)
                for end in (e["source_borrower_id"], e["target_borrower_id"]):
                    hops.setdefault(end, 2)
    # keep the focal, then the strongest-connected names, within the node cap
    if len(hops) > max_nodes:
        score: dict[str, float] = {k: 0.0 for k in hops}
        for e in edges.values():
            for end in (e["source_borrower_id"], e["target_borrower_id"]):
                score[end] += _edge_strength(e)
        keep = {focal} | set(m for m in group_ids)
        for k in sorted(hops, key=lambda k: (hops[k], -score[k], k)):
            if len(keep) >= max_nodes:
                break
            keep.add(k)
        truncated = {"shown": len(keep), "available": len(hops),
                     "note": f"The strongest {len(keep)} of {len(hops)} related names are drawn."}
        hops = {k: h for k, h in hops.items() if k in keep}
    edges = {k: e for k, e in edges.items()
             if e["source_borrower_id"] in hops and e["target_borrower_id"] in hops}
    node_ids = _ids(list(hops))
    attrs = _node_attrs(period, node_ids)
    missing = [k for k in node_ids if k not in attrs]
    for k in missing:  # a related name the book has no row for at this quarter: drop it with its edges
        hops.pop(k, None)
    edges = {k: e for k, e in edges.items() if e["source_borrower_id"] in hops and e["target_borrower_id"] in hops}
    node_ids = _ids(list(hops))

    # kind of each edge, read from the focal outward
    out_edges: list[dict[str, Any]] = []
    for e in sorted(edges.values(), key=lambda x: (x["rel_type"], x["edge_id"])):
        s_, t_ = e["source_borrower_id"], e["target_borrower_id"]
        t = e["rel_type"]
        if t == "GROUP":
            kind, label = "group", f"{'owns' if (e.get('ownership_pct') or 0) >= 50 else 'holds'} {e['ownership_pct']:.1f}%"
        elif t == "SUPPLIES":
            kind = "supplier" if hops.get(s_, 9) >= hops.get(t_, 9) else "customer"
            label = f"{e['purchase_share_pct']:.1f}% of buyer's purchases · {e['revenue_share_pct']:.1f}% of supplier's revenue"
        elif t == "GUARANTEES":
            kind, label = "guarantor", f"guarantees {e['facility_id']} · SAR {e['guarantee_amount_sar_mn']:,.2f}m"
        else:
            kind, label = "collateral", f"both claim {e['collateral_id']}"
        out_edges.append({"id": e["edge_id"], "source": s_, "target": t_, "type": t, "kind": kind, "label": label,
                          "directed": t in ("SUPPLIES", "GUARANTEES", "GROUP"),
                          "ownership_pct": e.get("ownership_pct"), "purchase_share_pct": e.get("purchase_share_pct"),
                          "revenue_share_pct": e.get("revenue_share_pct"),
                          "annual_value_sar_mn": e.get("annual_value_sar_mn"), "facility_id": e.get("facility_id"),
                          "guarantee_amount_sar_mn": e.get("guarantee_amount_sar_mn"),
                          "collateral_id": e.get("collateral_id"), "detail": e.get("relation_detail")})

    # persons who own or direct two or more of the companies drawn
    people: dict[str, dict[str, Any]] = {}
    for p in _persons(node_ids):
        d = people.setdefault(p["person_id"], {"person_id": p["person_id"], "name": p["person_name"], "roles": []})
        d["roles"].append({"borrower_id": p["borrower_id"], "role": p["role"], "ownership_pct": p["ownership_pct"]})
    shared_people = {pid: d for pid, d in people.items() if len({r["borrower_id"] for r in d["roles"]}) >= 2}
    for pid, d in shared_people.items():
        for r in d["roles"]:
            label = f"{r['role'].lower()}" + (f" ({r['ownership_pct']:.1f}%)" if r["ownership_pct"] else "")
            out_edges.append({"id": f"EP-{pid}-{r['borrower_id']}-{r['role']}", "source": f"P:{pid}", "target": r["borrower_id"],
                              "type": "PERSON", "kind": "person", "label": label, "directed": False,
                              "ownership_pct": r["ownership_pct"], "detail": r["role"]})

    # nodes
    nodes: list[dict[str, Any]] = []
    for k in node_ids:
        a = attrs[k]
        nodes.append({"id": k, "type": "borrower", "name": a["borrower_name"], "sector": a["sector"], "sub_sector": a["sub_sector"],
                      "region": a["region"], "rating": a["rating_current"], "ews_band": a["ews_band"],
                      "ews_score": a["score"], "exposure": a["ead"] or 0.0, "ecl": a["ecl"] or 0.0,
                      "facilities": a["facilities"], "worst_stage": a["worst_stage"], "watchlist": bool(a["watchlist_flag"]),
                      "hop": hops[k], "is_focal": k == focal,
                      "href": f"/borrower-360?domain=corporate&customer_id={k}&period={period}"})
    for pid, d in sorted(shared_people.items()):
        nodes.append({"id": f"P:{pid}", "type": "person", "name": d["name"], "roles": d["roles"], "hop": 1, "is_focal": False,
                      "exposure": 0.0, "ews_band": "none"})
    drawn = [e for e in out_edges]
    all_ids = [n["id"] for n in nodes]
    pos = layout(all_ids, {n["id"]: n["hop"] for n in nodes},
                 [(e["source"], e["target"], _edge_strength({"rel_type": e["type"], **{
                     k: e.get(k) for k in ("ownership_pct", "purchase_share_pct", "revenue_share_pct",
                                           "guarantee_amount_sar_mn")}}) / 2) for e in drawn], focal)
    for n in nodes:
        n["x"], n["y"] = pos[n["id"]]
    legend = {k: {"label": KINDS[k], "count": sum(1 for e in drawn if e["kind"] == k)} for k in
              ("group", "supplier", "customer", "guarantor", "collateral", "person")}
    focal_node = next(n for n in nodes if n["id"] == focal)
    result = {"domain_id": "corporate", "customer_id": focal, "period": period, "depth": depth, "focal": focal_node,
              "nodes": nodes, "edges": drawn, "legend": legend, "truncated": truncated,
              "bands": list(BANDS), "money_unit": "SAR million"}
    result["analytics"] = corporate_analytics(focal, period, nodes, drawn, members)
    return clean(result)


def corporate_analytics(focal: str, period: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
                        members: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {n["id"]: n for n in nodes}
    # ---- connected group against CP-1.2
    pol = policy_limit()
    group: dict[str, Any] = {"policy": pol, "standalone": not members}
    if members:
        gid = members[0]["group_id"]
        mem_ids = [m["borrower_id"] for m in members]
        attrs = _node_attrs(period, mem_ids)
        tot = sum((attrs[m["borrower_id"]]["ead"] or 0.0) for m in members if m["borrower_id"] in attrs)
        ecl = sum((attrs[m["borrower_id"]]["ecl"] or 0.0) for m in members if m["borrower_id"] in attrs)
        trend = rows("""SELECT reporting_quarter AS period, SUM(ead_sar_mn) AS ead FROM corp_facility
                        WHERE list_contains(?, borrower_id) AND reporting_quarter <= ? GROUP BY 1 ORDER BY 1 DESC LIMIT ?""",
                     [mem_ids, period, TREND_QUARTERS])
        trend.reverse()
        group.update({
            "group_id": gid, "group_name": members[0]["group_name"], "legacy_group_id": members[0]["legacy_group_id"],
            "legacy_group_name": members[0]["legacy_group_name"], "members": len(members), "exposure": tot, "ecl": ecl,
            "utilisation_pct": 100 * tot / pol["limit_sar_mn"], "headroom": pol["limit_sar_mn"] - tot,
            "status": "breach" if tot > pol["limit_sar_mn"] else "watch" if tot > 0.8 * pol["limit_sar_mn"] else "within",
            "trend": trend,
            "rows": [{"borrower_id": m["borrower_id"], "name": attrs[m["borrower_id"]]["borrower_name"], "role": m["role"],
                      "ownership_pct": m["ownership_pct"], "exposure": attrs[m["borrower_id"]]["ead"] or 0.0,
                      "share_pct": 100 * (attrs[m["borrower_id"]]["ead"] or 0.0) / tot if tot else None,
                      "rating": attrs[m["borrower_id"]]["rating_current"], "ews_band": attrs[m["borrower_id"]]["ews_band"],
                      "ews_score": attrs[m["borrower_id"]]["score"], "is_self": m["borrower_id"] == focal}
                     for m in members if m["borrower_id"] in attrs]})
    # ---- supplier and customer concentration (from the focal's own edges, whatever the depth drawn)
    own = _edges_touching(period, [focal], ("SUPPLIES",))
    ids = _ids([e["source_borrower_id"] for e in own] + [e["target_borrower_id"] for e in own] + [focal])
    attrs = _node_attrs(period, ids)

    def partner(e: dict[str, Any], me: str) -> dict[str, Any]:
        other = e["target_borrower_id"] if e["source_borrower_id"] == me else e["source_borrower_id"]
        a = attrs.get(other, {})
        return {"borrower_id": other, "name": a.get("borrower_name"), "sector": a.get("sector"), "region": a.get("region"),
                "ews_band": a.get("ews_band"), "ews_score": a.get("score"), "exposure": a.get("ead") or 0.0,
                "rating": a.get("rating_current"), "purchase_share_pct": e["purchase_share_pct"],
                "revenue_share_pct": e["revenue_share_pct"], "annual_value_sar_mn": e["annual_value_sar_mn"]}

    sup = sorted((partner(e, focal) for e in own if e["target_borrower_id"] == focal), key=lambda r: -r["purchase_share_pct"])
    cus = sorted((partner(e, focal) for e in own if e["source_borrower_id"] == focal), key=lambda r: -r["revenue_share_pct"])

    def conc(items: list[dict[str, Any]], key: str, other_label: str, threshold: float) -> dict[str, Any]:
        shares = [i[key] for i in items]
        inbook = sum(shares)
        hhi = sum((s / 100) ** 2 for s in shares) + ((100 - inbook) / 100) ** 2 * 0  # the unnamed rest is not one party
        return {"rows": items, "count": len(items), "in_book_share_pct": inbook, "other_share_pct": max(0.0, 100 - inbook),
                "other_label": other_label, "largest_share_pct": max(shares) if shares else 0.0,
                "largest": items[0]["borrower_id"] if items else None, "hhi": round(10000 * hhi), "threshold_pct": threshold,
                "flag": bool(shares and max(shares) > threshold)}

    suppliers = conc(sup, "purchase_share_pct", "Suppliers outside the bank's book", 40.0)
    customers = conc(cus, "revenue_share_pct", "Customers outside the bank's book", 30.0)
    # ---- contagion: related names in Early Warning
    related = []
    seen = set()
    for e in edges:
        if e["type"] == "PERSON":
            continue
        for end in (e["source"], e["target"]):
            if end != focal and end in by_id and by_id[end]["type"] == "borrower" and end not in seen:
                seen.add(end)
    for k in sorted(seen):
        n = by_id[k]
        kinds = sorted({e["kind"] for e in edges if k in (e["source"], e["target"]) and e["type"] != "PERSON"})
        related.append({"borrower_id": k, "name": n["name"], "kinds": [KINDS[x] for x in kinds], "ews_band": n["ews_band"],
                        "ews_score": n["ews_score"], "exposure": n["exposure"], "rating": n["rating"],
                        "watchlist": n["watchlist"], "hop": n["hop"]})
    by_band = {b: 0 for b in BANDS}
    exp_band = {b: 0.0 for b in BANDS}
    for r in related:
        by_band[r["ews_band"]] = by_band.get(r["ews_band"], 0) + 1
        exp_band[r["ews_band"]] = exp_band.get(r["ews_band"], 0.0) + r["exposure"]
    related.sort(key=lambda r: (BANDS.index(r["ews_band"]) if r["ews_band"] in BANDS else 9, -r["exposure"], r["borrower_id"]))
    warned = [r for r in related if r["ews_band"] in WARNED]
    contagion = {"related": len(related), "in_early_warning": len(warned), "by_band": by_band, "exposure_by_band": exp_band,
                 "exposure_in_early_warning": sum(r["exposure"] for r in warned),
                 "high_or_critical": sum(1 for r in related if r["ews_band"] in ("high", "critical")),
                 "rows": related, "focal_band": by_id[focal]["ews_band"]}
    # ---- shared collateral
    shared = rows("""SELECT s.collateral_id, s.collateral_type, s.borrower_id, s.facility_id, s.market_value_sar_mn,
                            s.claim_sar_mn, s.allocation_pct
                     FROM rel_shared s WHERE s.reporting_quarter = ? AND s.collateral_id IN
                       (SELECT collateral_id FROM rel_shared WHERE reporting_quarter = ? AND borrower_id = ?)
                     ORDER BY s.collateral_id, s.borrower_id""", [period, period, focal])
    owners = _node_attrs(period, _ids([s["borrower_id"] for s in shared])) if shared else {}
    assets: dict[str, dict[str, Any]] = {}
    for s_ in shared:
        a = assets.setdefault(s_["collateral_id"], {"collateral_id": s_["collateral_id"], "type": s_["collateral_type"],
                                                    "market_value": s_["market_value_sar_mn"], "claims": [], "total_pct": 0.0})
        o = owners.get(s_["borrower_id"], {})
        a["claims"].append({"borrower_id": s_["borrower_id"], "name": o.get("borrower_name"), "facility_id": s_["facility_id"],
                            "claim": s_["claim_sar_mn"], "allocation_pct": s_["allocation_pct"], "ews_band": o.get("ews_band"),
                            "is_self": s_["borrower_id"] == focal})
        a["total_pct"] += s_["allocation_pct"]
    for a in assets.values():
        a["over_pledged"] = a["total_pct"] > 100.0
        a["total_pct"] = round(a["total_pct"], 2)
    collateral = {"assets": list(assets.values()), "count": len(assets), "over_pledged": sum(1 for a in assets.values() if a["over_pledged"])}
    # ---- guarantees to and from the focal
    g = rows("""SELECT * FROM rel_edge WHERE reporting_quarter = ? AND rel_type = 'GUARANTEES'
                AND (source_borrower_id = ? OR target_borrower_id = ?) ORDER BY edge_id""", [period, focal, focal])
    gids = _ids([e["source_borrower_id"] for e in g] + [e["target_borrower_id"] for e in g])
    ga = _node_attrs(period, gids) if gids else {}
    guarantees = {"rows": [{"direction": "received" if e["target_borrower_id"] == focal else "given",
                            "guarantor_id": e["source_borrower_id"], "guarantor": ga.get(e["source_borrower_id"], {}).get("borrower_name"),
                            "guaranteed_id": e["target_borrower_id"], "guaranteed": ga.get(e["target_borrower_id"], {}).get("borrower_name"),
                            "facility_id": e["facility_id"], "amount": e["guarantee_amount_sar_mn"], "basis": e["relation_detail"],
                            "guarantor_band": ga.get(e["source_borrower_id"], {}).get("ews_band")} for e in g]}
    pe = [p for p in nodes if p["type"] == "person"]
    people_rows = [{"person_id": p["id"][2:], "name": p["name"], "roles": ", ".join(
        f"{r['role']} of {r['borrower_id']}" + (f" ({r['ownership_pct']:.1f}%)" if r["ownership_pct"] else "") for r in p["roles"])}
        for p in pe]
    # ---- employees in the retail book (cross-domain)
    emp = rows("""SELECT COUNT(DISTINCT customer_id) AS customers FROM rel_employer
                  WHERE employer_borrower_id = ? AND reporting_month = (SELECT MAX(reporting_month) FROM rel_employer
                  WHERE reporting_month <= ?)""", [focal, _month_of_quarter(period)])[0]
    workforce = {"customers": emp["customers"]}
    if emp["customers"]:
        w = rows("""WITH c AS (SELECT DISTINCT customer_id FROM rel_employer WHERE employer_borrower_id = ? AND reporting_month = ?)
                    SELECT COUNT(*) AS accounts, SUM(ead_sar_mn) AS ead, SUM(CASE WHEN stage >= 2 THEN ead_sar_mn ELSE 0 END) AS ead_s2
                    FROM ret_account WHERE reporting_month = ? AND customer_id IN (SELECT customer_id FROM c)""",
                 [focal, _month_of_quarter(period), _month_of_quarter(period)])[0]
        workforce.update({"accounts": w["accounts"], "exposure": w["ead"] or 0.0, "stage2_exposure": w["ead_s2"] or 0.0,
                          "stage2_share_pct": 100 * (w["ead_s2"] or 0) / w["ead"] if w["ead"] else None,
                          "month": _month_of_quarter(period)})
    return {"group": group, "suppliers": suppliers, "customers": customers, "contagion": contagion,
            "collateral": collateral, "guarantees": guarantees, "people": {"rows": people_rows}, "workforce": workforce}


def _month_of_quarter(period: str) -> str:
    y, q = int(period[:4]), int(period[-1])
    return f"{y}-{3 * q:02d}"


# ------------------------------------------------------------------ retail


def retail_graph(owner_id: str, period: str, depth: int = 1, kinds: tuple[str, ...] | None = None,
                 max_nodes: int = MAX_NODES) -> dict[str, Any]:
    period = service.resolve("retail", owner_id, period)
    hh = rows("""SELECT * FROM rel_household WHERE reporting_month = ? AND household_id IN
                 (SELECT household_id FROM rel_household WHERE reporting_month = ? AND customer_id = ?)
                 ORDER BY CASE role WHEN 'head' THEN 0 WHEN 'spouse' THEN 1 ELSE 2 END, customer_id""", [period, period, owner_id])
    emp = rows("SELECT * FROM rel_employer WHERE reporting_month = ? AND customer_id = ?", [period, owner_id])
    cust_ids = _ids([owner_id] + [h["customer_id"] for h in hh])
    c = rows("""WITH a AS (SELECT customer_id, COUNT(*) AS accounts, SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl,
                           MAX(stage) AS worst_stage, MAX(dpd_days) AS worst_dpd
                    FROM ret_account WHERE reporting_month = ? AND list_contains(?, customer_id) GROUP BY 1),
                  e AS (SELECT customer_id, MAX(ews_score) AS score FROM ews_ret WHERE reporting_month = ?
                        AND list_contains(?, customer_id) GROUP BY 1)
                SELECT r.customer_id, r.customer_segment, r.employment_type, r.region, r.score_band, r.behaviour_score,
                       a.accounts, a.ead, a.ecl, a.worst_stage, a.worst_dpd, e.score
                FROM ret_customer r LEFT JOIN a USING (customer_id) LEFT JOIN e USING (customer_id)
                WHERE r.reporting_month = ? AND list_contains(?, r.customer_id)""", [period, cust_ids, period, cust_ids, period, cust_ids])
    cattr = {r["customer_id"]: r for r in c}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for cid in cust_ids:
        a = cattr[cid]
        band = ews.band_of("retail", a.get("score"))
        role = next((h["role"] for h in hh if h["customer_id"] == cid), None)
        nodes.append({"id": cid, "type": "customer", "name": cid, "segment": a["customer_segment"], "sub_sector": a["employment_type"],
                      "region": a["region"], "rating": a["score_band"], "ews_band": band, "ews_score": a.get("score"),
                      "exposure": a["ead"] or 0.0, "ecl": a["ecl"] or 0.0, "facilities": a["accounts"], "worst_stage": a["worst_stage"],
                      "household_role": role, "hop": 0 if cid == owner_id else 1, "is_focal": cid == owner_id,
                      "href": f"/borrower-360?domain=retail&customer_id={cid}&period={period}"})
        if cid != owner_id and hh:
            edges.append({"id": f"EH-{owner_id}-{cid}", "source": owner_id, "target": cid, "type": "HOUSEHOLD", "kind": "household",
                          "label": f"same household ({role})", "directed": False, "detail": role})
    employer = None
    if emp:
        eid = emp[0]["employer_borrower_id"]
        cp = _corp_period(period)
        ea = _node_attrs(cp, [eid]).get(eid)
        if ea:
            employer = ea
            nodes.append({"id": eid, "type": "borrower", "name": ea["borrower_name"], "sector": ea["sector"], "sub_sector": ea["sub_sector"],
                          "region": ea["region"], "rating": ea["rating_current"], "ews_band": ea["ews_band"], "ews_score": ea["score"],
                          "exposure": ea["ead"] or 0.0, "ecl": ea["ecl"] or 0.0, "facilities": ea["facilities"],
                          "watchlist": bool(ea["watchlist_flag"]), "hop": 1, "is_focal": False,
                          "href": f"/borrower-360?domain=corporate&customer_id={eid}&period={cp}"})
            edges.append({"id": f"EE-{owner_id}-{eid}", "source": eid, "target": owner_id, "type": "EMPLOYER", "kind": "employer",
                          "label": "employs", "directed": True, "detail": "salaried employee"})
    pos = layout([n["id"] for n in nodes], {n["id"]: n["hop"] for n in nodes}, [(e["source"], e["target"], 1.0) for e in edges], owner_id)
    for n in nodes:
        n["x"], n["y"] = pos[n["id"]]
    legend = {k: {"label": KINDS[k], "count": sum(1 for e in edges if e["kind"] == k)} for k in ("household", "employer")}
    focal_node = next(n for n in nodes if n["id"] == owner_id)
    household = {"household_id": hh[0]["household_id"] if hh else None, "members": len(hh),
                 "exposure": sum(n["exposure"] for n in nodes if n["type"] == "customer"),
                 "ecl": sum(n["ecl"] for n in nodes if n["type"] == "customer"),
                 "in_early_warning": sum(1 for n in nodes if n["type"] == "customer" and n["ews_band"] in WARNED),
                 "rows": [{"customer_id": n["id"], "role": n.get("household_role") or "self", "exposure": n["exposure"], "ecl": n["ecl"],
                           "rating": n["rating"], "ews_band": n["ews_band"], "ews_score": n["ews_score"], "is_self": n["is_focal"]}
                          for n in nodes if n["type"] == "customer"]}
    emp_block: dict[str, Any] = {"employer": None}
    if employer:
        eid = employer["borrower_id"]
        colleagues = rows("""WITH c AS (SELECT DISTINCT customer_id FROM rel_employer WHERE employer_borrower_id = ? AND reporting_month = ?)
                             SELECT COUNT(DISTINCT customer_id) AS customers, SUM(ead_sar_mn) AS ead,
                                    SUM(CASE WHEN stage >= 2 THEN ead_sar_mn ELSE 0 END) AS ead_s2
                             FROM ret_account WHERE reporting_month = ? AND customer_id IN (SELECT customer_id FROM c)""",
                          [eid, period, period])[0]
        emp_block = {"employer": {"borrower_id": eid, "name": employer["borrower_name"], "sector": employer["sector"],
                                  "ews_band": employer["ews_band"], "ews_score": employer["score"], "exposure": employer["ead"] or 0.0,
                                  "rating": employer["rating_current"]},
                     "colleagues": colleagues["customers"], "colleagues_exposure": colleagues["ead"] or 0.0,
                     "colleagues_stage2_share_pct": 100 * (colleagues["ead_s2"] or 0) / colleagues["ead"] if colleagues["ead"] else None}
    return clean({"domain_id": "retail", "customer_id": owner_id, "period": period, "depth": 1, "focal": focal_node, "nodes": nodes,
                  "edges": edges, "legend": legend, "truncated": {}, "bands": list(BANDS), "money_unit": "SAR million",
                  "analytics": {"household": household, "employer": emp_block}})


def _corp_period(month: str) -> str:
    """The corporate quarter that holds a retail month (cross-domain comparisons use the common quarter-end)."""
    quarters = book_periods("corporate")
    y, m = int(month[:4]), int(month[5:7])
    want = f"{y}Q{(m - 1) // 3 + 1}"
    return want if want in quarters else quarters[-1]


def build(domain_id: str, owner_id: str, period: str, depth: int = 1) -> dict[str, Any]:
    if domain_id == "corporate":
        from backend.b360 import network   # PLAN_R9 B7: classification, prepared case links, P5 insights
        return clean(network.enrich(corporate_graph(owner_id, period, depth)))
    return retail_graph(owner_id, period, depth)
