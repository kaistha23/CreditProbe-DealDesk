"""P5 Network Intelligence on the Borrower 360 relationship graph (PLAN_R9 Session B, item 7).

Adds to the graph built by `graph.py`:
- each borrower node's classification (Stage, SICR, UTP, watch status, from `intel`) and a colour key;
- the off-book links prepared for the two proposal cases (PLAN_R9 §Proposals), drawn on two seeded
  borrowers: L1 group, guarantors and shareholders; L2 sponsors, sister companies and nominee holdings;
  L3 counterparties from deposit flows;
- the insights: group exposure, impaired nodes, single-counterparty concentration, staff or related-party
  flags, and "cross-default assessment required (Art 6.12)", Powered by P5.
"""
from __future__ import annotations

import math
from typing import Any

from backend.b360 import intel

PACK = {"id": "P5", "name": "Network Intelligence"}

#: Classification -> colour band (re-uses the graph's band palette): impaired red, SICR amber, watch yellow.
CLASS_BAND = {"Default": "critical", "UTP": "critical", "Stage 3": "critical", "SICR": "high", "Stage 2": "high",
              "Watch": "moderate", "Performing": "none"}
CLASS_ORDER = ("Default", "Stage 3", "UTP", "Stage 2", "SICR", "Watch", "Performing")

#: The two prepared proposal networks, keyed by the seeded book borrower. Amounts AED million.
CASES: dict[str, dict[str, Any]] = {
    "CB00009": {
        "case": "Case B: trader", "proposal": "Al Sahel Building Materials Trading LLC",
        "nodes": [
            ("X:SAHEL-TR", "Sahel Transport LLC", 1, "Performing", 0.0, "Related party; vehicles to be registered here"),
            ("X:SPONSOR", "Sahel Transport 51% sponsor", 2, "Watch", 0.0, "Individual sponsor; linked to Marwan Steel"),
            ("X:MARWAN", "Marwan Steel General Trading", 2, "Default", 0.0,
             "Doubtful at another bank; litigation AED 36m; group holds 25% through nominees"),
            ("X:LOSS-1", "Group entity (CBRBR Loss) 1", 3, "Default", 10.0, "CBRBR: Loss, about AED 10m"),
            ("X:LOSS-2", "Group entity (CBRBR Loss) 2", 3, "Default", 31.0, "CBRBR: Loss, about AED 31m"),
            ("X:GUAR-STAFF", "Corporate guarantor (51% staff-owned)", 1, "Performing", 0.0,
             "A bank staff member owns 51%: conflict of interest, refer to compliance (Art 5.10)"),
        ],
        "edges": [
            ("@", "X:SAHEL-TR", "customer", "AED 71.6m receivable · 68% of current assets", True),
            ("X:SPONSOR", "X:SAHEL-TR", "group", "owns 51%", True),
            ("X:SPONSOR", "X:MARWAN", "person", "linked sponsor", False),
            ("@", "X:MARWAN", "group", "holds 25% through nominees", True),
            ("X:MARWAN", "X:LOSS-1", "group", "group entity", True),
            ("X:MARWAN", "X:LOSS-2", "group", "group entity", True),
            ("X:GUAR-STAFF", "@", "guarantor", "corporate guarantee · staff-owned 51%", True),
        ],
        "flags": [
            ("Related-party concentration", "AED 117.65m due from related parties, 68% of current assets, mostly Sahel Transport."),
            ("Connected obligor in default", "Marwan Steel is Doubtful at another bank and in litigation over AED 36m; two group entities are at Loss in CBRBR."),
            ("Staff link", "A bank staff member owns 51% of a corporate guarantor (Art 5.10)."),
            ("Routing", "Routing undertaking of 2× the limit met at only 33%."),
        ],
        "single_counterparty": ("Sahel Transport LLC", 68.0, "of current assets"),
    },
    "CB00724": {
        "case": "Case A: contractor", "proposal": "Gulf Meridian Contracting LLC",
        "nodes": [
            ("X:MERIDIAN-H", "Meridian Holding (parent, Kuwait)", 1, "Watch", 0.0,
             "Related-party dues 39% of total assets; deleveraging; guarantee perfection deferred"),
            ("X:AFFILIATE", "Dubai affiliate", 1, "SICR", 0.0, "50 returned cheques for insufficient funds, Jan–Jul 2026"),
            ("X:ARWA", "Arwa Developments", 2, "Performing", 0.0, "44% of backlog; AED 212.4m villa project request"),
            ("X:ELC", "Emirates Logistics City", 2, "Performing", 0.0, "25% of backlog"),
            ("X:BANKS", "3 other banks (AED 1.57bn new facilities)", 3, "Watch", 1570.0, "No facility letters; CBRBR gaps"),
        ],
        "edges": [
            ("X:MERIDIAN-H", "@", "group", "parent · corporate guarantee not perfected", True),
            ("X:MERIDIAN-H", "X:AFFILIATE", "group", "sister company", True),
            ("@", "X:ARWA", "customer", "44% of AED 8.2bn backlog", True),
            ("@", "X:ELC", "customer", "25% of backlog", True),
            ("X:BANKS", "@", "supplier", "AED 1.57bn new facilities, no letters", True),
        ],
        "flags": [
            ("Parent stress", "Meridian Holding related-party dues at 39% of total assets (Art 7.11h)."),
            ("Affiliate cheque returns", "50 returned cheques at the Dubai affiliate, Jan–Jul 2026."),
            ("Undisclosed borrowing", "AED 1.57bn of new facilities at 3 other banks with no facility letters."),
        ],
        "single_counterparty": ("Arwa Developments", 44.0, "of backlog"),
    },
}


def classify(n: dict[str, Any], detail: dict[str, Any] | None) -> str:
    stage = int(n.get("worst_stage") or (detail or {}).get("stage") or 1)
    if stage >= 3:
        return "Stage 3"
    if detail and detail.get("utp"):
        return "UTP"
    if stage == 2:
        return "Stage 2"
    if detail and detail.get("sicr"):
        return "SICR"
    if n.get("watchlist") or (detail and detail.get("watch_status") not in (None, "None")):
        return "Watch"
    return "Performing"


def enrich(g: dict[str, Any]) -> dict[str, Any]:
    """Classification on every node, the prepared case overlay, and the P5 insights (corporate graphs)."""
    if g.get("domain_id") != "corporate":
        return g
    period, focal = g["period"], g["customer_id"]
    _, detail = intel.build("corporate", period)
    for n in g["nodes"]:
        if n["type"] == "borrower":
            n["classification"] = classify(n, detail.get(n["id"]))
            n["class_band"] = CLASS_BAND[n["classification"]]
    case = CASES.get(focal)
    if case:
        _overlay(g, case)
    g["network_intelligence"] = insights(g, detail, case)
    return g


def _overlay(g: dict[str, Any], case: dict[str, Any]) -> None:
    focal = g["customer_id"]
    by_ring: dict[int, list[tuple]] = {}
    for x in case["nodes"]:
        by_ring.setdefault(x[2], []).append(x)
    for ring, xs in by_ring.items():
        for i, (nid, name, level, cls, exposure, note) in enumerate(xs):
            a = math.pi * (0.15 + 0.7 * (i + 0.5) / len(xs)) + (ring - 1) * 0.35
            r = 0.55 + 0.32 * ring
            g["nodes"].append({"id": nid, "type": "external", "name": name, "hop": level, "is_focal": False,
                               "level": f"L{level}", "exposure": exposure, "ecl": 0.0, "ews_band": CLASS_BAND[cls],
                               "classification": cls, "class_band": CLASS_BAND[cls], "rating": None, "ews_score": None,
                               "sector": "Off book", "note": note, "href": "",
                               "x": round(r * math.cos(a), 4), "y": round(-r * math.sin(a), 4)})
    for k, (s, t, kind, label, directed) in enumerate(case["edges"]):
        g["edges"].append({"id": f"EX-{focal}-{k}", "source": focal if s == "@" else s, "target": focal if t == "@" else t,
                           "type": "EXTERNAL", "kind": kind, "label": label, "directed": directed, "detail": "prepared case"})
    for kind in {e[2] for e in case["edges"]}:
        if kind in g.get("legend", {}):
            g["legend"][kind]["count"] += sum(1 for e in case["edges"] if e[2] == kind)
    g["case"] = {"case": case["case"], "proposal": case["proposal"]}


def insights(g: dict[str, Any], detail: dict[str, Any], case: dict[str, Any] | None) -> dict[str, Any]:
    nodes = [n for n in g["nodes"] if n["type"] in ("borrower", "external")]
    focal = g["customer_id"]
    a = g.get("analytics", {})
    out: list[dict[str, Any]] = []
    grp = a.get("group") or {}
    if not grp.get("standalone") and grp.get("exposure") is not None:
        out.append({"key": "group_exposure", "title": "Group exposure",
                    "text": f"{grp.get('group_name')}: {grp.get('members')} members, EAD SAR {grp['exposure']:,.1f}m, "
                            f"{grp.get('utilisation_pct', 0):.0f}% of the connected-group limit ({grp.get('status')}).",
                    "severity": "high" if grp.get("status") == "breach" else "medium" if grp.get("status") == "watch" else "low"})
    impaired = [n for n in nodes if n["id"] != focal and n.get("classification") in ("Default", "Stage 3", "UTP")]
    if impaired:
        out.append({"key": "impaired", "title": "Impaired related names",
                    "text": f"{len(impaired)} related name(s) impaired: " + ", ".join(str(n["name"]) for n in impaired[:5]) + ".",
                    "severity": "high", "ids": [n["id"] for n in impaired]})
    conc = []
    for side in ("suppliers", "customers"):
        s = a.get(side) or {}
        if s.get("flag"):
            conc.append(f"largest {side[:-1]} {s.get('largest')} at {s.get('largest_share_pct', 0):.1f}%")
    if case:
        nm, share, of = case["single_counterparty"]
        conc.append(f"{nm} at {share:.0f}% {of}")
    if conc:
        out.append({"key": "concentration", "title": "Single-counterparty concentration", "text": "; ".join(conc) + ".",
                    "severity": "high"})
    for title, text in (case or {}).get("flags", []):
        out.append({"key": "flag", "title": title, "text": text, "severity": "high"})
    cross = bool(impaired)
    if cross:
        out.append({"key": "cross_default", "title": "Cross-default assessment required (Art 6.12)",
                    "text": "A connected obligor is impaired: assess economic dependency and cross-default before renewal "
                            "(CBUAE CRM Art. 6.12).", "severity": "high"})
    counts = {c: sum(1 for n in nodes if n.get("classification") == c) for c in CLASS_ORDER}
    return {"insights": out, "cross_default_required": cross, "classification_counts": counts,
            "case": g.get("case"), "levels": {"L1": "group, guarantors, shareholders",
                                               "L2": "sister companies, sponsors, nominee holdings",
                                               "L3": "counterparties from deposit flows"},
            "powered_by": {**PACK, "articles": ["CBUAE CRM Art. 6.12", "CBUAE CRM Art. 5.10", "CBUAE CRM Art. 7.11h"],
                           "confidence": "High" if not case else "Medium",
                           "trace": f"b360.network/corporate/{g['period']}/{focal}"}}
