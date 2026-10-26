"""Round G: cross-deal signals read off the graph (deterministic rules, no model).

Rules, for the borrower X of a deal (or any customer node):

  counterparty_distress   a counterparty Y of X (buyer, supplier, guarantor, shareholder, employer, related party, group member,
                          a company sharing X's owner or guarantor) is in default, classified, past due, restructured or on watch,
                          or is the borrower of a declined deal, or of a pending deal while in difficulty. Severity: default,
                          classified or declined → high; past due, restructured or watch → medium.
  borrower_is_counterparty  X is a supplier, buyer, employer or guarantor of Z (Z's own file or the Bank's data says so) and Z is
                          the borrower of another deal. High when Z is in difficulty (X's buyer defaulting is X's problem), low
                          otherwise (the deals are joined).
  counterparty_in_pipeline  a counterparty Y of X is the borrower of another deal, with no difficulty known (low): the deals are
                          joined through the graph.

Each signal carries the link's evidence (document, page, line, date, or the Data Domains relation and quarter) and the
standing's evidence, and one plain sentence. Seeded demo links are marked synthetic.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.dealdesk.graph import store as G

DISTRESS = {"default": ("high", "in default"), "classified": ("high", "classified"), "past_due": ("medium", "past due"),
            "restructured": ("medium", "restructured"), "watch": ("medium", "on watch")}
SEV_RANK = {"high": 0, "medium": 1, "low": 2}

#: X —rel→ Y: Y's role for X
OUT_ROLE = {"has_buyer": "buyer", "has_supplier": "supplier", "guaranteed_by": "guarantor", "has_shareholder": "shareholder",
            "has_employer": "employer", "related_party": "related party", "contagion_link": "linked borrower", "has_ubo": "owner"}
#: Z —rel→ X: X's role for Z (borrower_is_counterparty)
IN_ROLE = {"has_supplier": "supplier", "has_buyer": "buyer", "has_employer": "employer", "guaranteed_by": "guarantor", "has_shareholder": "shareholder"}
#: people and parents shared with X make a connected company
VIA = ("guaranteed_by", "has_shareholder", "has_ubo", "has_director")
ROLE_ORDER = {"buyer": 0, "employer": 1, "supplier": 2, "guarantor": 3, "shareholder": 4, "group member": 5, "related party": 6,
              "connected": 7, "linked borrower": 8, "owner": 9}

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = threading.RLock()
TTL = 120


def clear() -> None:
    with _LOCK:
        _CACHE.clear()


def _ev_edge(e: dict[str, Any]) -> dict[str, Any]:
    return {"edge_id": e["edge_id"], "rel": e["rel"], "source_kind": e["source_kind"], "source_label": e.get("source_label") or "",
            "doc_id": e.get("doc_id"), "doc_label": e.get("doc_label"), "page": e.get("page"), "line": e.get("line"), "date": e.get("seen_date"),
            "author": e.get("author") or "", "synthetic": bool(e.get("synthetic")), "proposal_id": e.get("proposal_id"), "attrs": e.get("attrs") or {}}


def _ev_status(s: dict[str, Any]) -> dict[str, Any]:
    return {"status": s["status"], "label": DISTRESS.get(s["status"], ("medium", s["status"]))[1], "note": s.get("note") or "",
            "source_kind": s["source_kind"], "source_label": s.get("source_label") or "", "doc_label": s.get("doc_label"), "page": s.get("page"),
            "date": s.get("seen_date"), "synthetic": bool(s.get("synthetic"))}


def where(ev: dict[str, Any], short: bool = False) -> str:
    """'C2-25 · Top customers and suppliers, p. 1, line 18, 21 Oct 2026' or 'Group links (borrower_360.b360_edge, 2026Q2)'."""
    from backend.dealdesk.graph.text import dmy
    if ev.get("doc_label"):
        bits = [ev["doc_label"]]
        if ev.get("page"):
            bits.append(f"page {ev['page']}")
        if ev.get("line"):
            bits.append(f"line {ev['line']}")
    else:
        lab = ev.get("source_label") or "the Bank's data"
        bits = [lab.split(" (")[0] if short else lab]
    if ev.get("date"):
        bits.append(dmy(ev["date"]))
    return ", ".join(str(b) for b in bits) + (" (seeded link)" if ev.get("synthetic") else "")


def _distress(y: str, statuses: dict[str, list[dict[str, Any]]], deals: dict[str, list[dict[str, Any]]], focal_pid: str) -> list[dict[str, Any]]:
    out = [_ev_status(s) for s in statuses.get(y, []) if s["status"] in DISTRESS]
    other = [d for d in deals.get(y, []) if d["proposal_id"] != focal_pid]
    for d in other:
        if d.get("status") == "declined":
            out.append({"status": "declined", "label": "in a declined deal", "note": f"Deal {d['proposal_id']} was declined",
                        "source_kind": "deal", "source_label": f"Deal Desk register ({d['proposal_id']})", "proposal_id": d["proposal_id"],
                        "date": d.get("received_date"), "synthetic": False})
    best: dict[str, dict[str, Any]] = {}
    for s in out:  # one line per standing (the latest evidence first)
        best.setdefault(s["status"], s)
    return sorted(best.values(), key=lambda s: SEV_RANK[_sev(s["status"])])


def _sev(status: str) -> str:
    return "high" if status == "declined" else DISTRESS.get(status, ("low", ""))[0]


def _role_label(role: str, via: str = "") -> str:
    return f"connected through {via}" if role == "connected" else role


def for_node(x: str, focal_pid: str = "") -> list[dict[str, Any]]:
    """Every signal for the customer node x (as the borrower of focal_pid when given)."""
    key = f"n:{x}:{focal_pid}"
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    out = _for_node(x, focal_pid)
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def _for_node(x: str, focal_pid: str) -> list[dict[str, Any]]:
    ex = G.edges_of([x])
    cps: dict[str, dict[str, Any]] = {}  # y -> {roles, edges, via}

    def add(y: str, role: str, edges: list[dict[str, Any]], via: str = "", direction: str = "out") -> None:
        if not y or y == x:
            return
        d = cps.setdefault(y, {"roles": [], "edges": [], "via": "", "direction": direction, "by_role": {}})
        if role not in d["roles"]:
            d["roles"].append(role)
        br = d["by_role"].setdefault(role, [])
        br += [e for e in edges if all(e["edge_id"] != f["edge_id"] for f in br)]
        if via and not d["via"]:
            d["via"] = via
        for e in edges:
            if all(e["edge_id"] != f["edge_id"] for f in d["edges"]):
                d["edges"].append(e)
        if direction == "out":
            d["direction"] = "out"

    reverse: dict[str, dict[str, Any]] = {}
    groups, projects, links = [], [], []
    for e in ex:
        if e["src"] == x and e["rel"] in OUT_ROLE:
            add(e["dst"], OUT_ROLE[e["rel"]], [e])
        elif e["dst"] == x and e["rel"] == "related_party":
            add(e["src"], "related party", [e])
        elif e["dst"] == x and e["rel"] in IN_ROLE:
            r = reverse.setdefault(e["src"], {"roles": [], "edges": [], "by_role": {}})
            if IN_ROLE[e["rel"]] not in r["roles"]:
                r["roles"].append(IN_ROLE[e["rel"]])
            r["edges"].append(e)
            r["by_role"].setdefault(IN_ROLE[e["rel"]], []).append(e)
        if e["src"] == x and e["rel"] == "member_of":
            groups.append(e)
        if e["src"] == x and e["rel"] == "has_project":
            projects.append(e)
        if e["src"] == x and e["rel"] in VIA:
            links.append(e)
    # group members
    if groups:
        for e in G.edges_of([g["dst"] for g in groups], ("member_of",)):
            if e["src"] != x:
                add(e["src"], "group member", [next(g for g in groups if g["dst"] == e["dst"]), e])
    # project employers
    if projects:
        pe = {p["dst"]: p for p in projects}
        for e in G.edges_of(list(pe), ("employer",)):
            if e["src"] in pe:
                add(e["dst"], "employer", [pe[e["src"]], e])
    # companies sharing an owner, guarantor or director (persons and parent companies)
    if links:
        hubs = {e["dst"]: e for e in links}
        hub_nodes = G.nodes(hubs)
        for e in G.edges_of(list(hubs), VIA):
            if e["dst"] in hubs and e["src"] != x:
                add(e["src"], "connected", [hubs[e["dst"]], e], via=(hub_nodes.get(e["dst"]) or {}).get("name", ""))
    ids = set(cps) | set(reverse)
    info = G.nodes(ids | {x})
    statuses = G.statuses_of(ids)
    deals = G.deals_of(ids)
    me = info.get(x, {})
    out: list[dict[str, Any]] = []
    for y, d in cps.items():
        ny = info.get(y)
        if not ny or ny["kind"] in ("bank", "project", "collateral", "group", "deal"):
            continue
        role = sorted(d["roles"], key=lambda r: ROLE_ORDER.get(r, 9))[0]
        dist = _distress(y, statuses, deals, focal_pid)
        other = [dl for dl in deals.get(y, []) if dl["proposal_id"] != focal_pid]
        if dist:
            sev = _sev(dist[0]["status"])
            out.append(_signal("counterparty_distress", sev, x, me, focal_pid, y, ny, role, d, dist, other))
        elif other:
            out.append(_signal("counterparty_in_pipeline", "low", x, me, focal_pid, y, ny, role, d, [], other))
    for z, d in reverse.items():
        nz = info.get(z)
        if not nz or nz["kind"] != "company":
            continue
        other = [dl for dl in deals.get(z, []) if dl["proposal_id"] != focal_pid]
        if not other:
            continue
        dist = _distress(z, statuses, deals, focal_pid)
        sev = _sev(dist[0]["status"]) if dist else "low"
        role = sorted(d["roles"], key=lambda r: ROLE_ORDER.get(r, 9))[0]
        out.append(_signal("borrower_is_counterparty", sev, x, me, focal_pid, z, nz, role, {**d, "via": ""}, dist, other))
    out.sort(key=lambda s: (SEV_RANK[s["severity"]], 0 if s["other_deals"] else 1,
                            0 if s["evidence"] and s["evidence"][0]["source_kind"] in ("upload", "agent") else 1,
                            ROLE_ORDER.get(s["counterparty"]["role"], 9), s["counterparty"]["name"]))
    return out


def _signal(rule: str, sev: str, x: str, me: dict[str, Any], focal_pid: str, y: str, ny: dict[str, Any], role: str, d: dict[str, Any],
            dist: list[dict[str, Any]], other: list[dict[str, Any]]) -> dict[str, Any]:
    first = d.get("by_role", {}).get(role) or []
    rest = [e for e in d["edges"] if all(e["edge_id"] != f["edge_id"] for f in first)]
    key = lambda e: (e["source_kind"] != "upload", str(e.get("seen_date") or ""))  # noqa: E731
    edges = [_ev_edge(e) for e in sorted(first, key=key) + sorted(rest, key=key)]
    xn, yn = me.get("name") or x, ny["name"]
    rl = _role_label(role, d.get("via") or "")
    deal_txt = ", ".join(f"{o['proposal_id']} ({o.get('status') or 'open'})" for o in other[:3])
    if rule == "counterparty_distress":
        st = dist[0]
        what = (f"{st['label']} (per {where(st, short=True)})" if st["status"] != "declined"
                else f"the borrower in a declined deal ({st.get('proposal_id')})")
        if st["status"] != "declined" and other:
            what += f", and the borrower in {deal_txt}"
        head = f"{yn}, {('a ' + rl) if not rl.startswith('connected') else rl}, is {what}"
        sentence = f"{yn}, {_article(rl)} of {xn}, is {what}."
    elif rule == "borrower_is_counterparty":
        what = (f"is {dist[0]['label'] if dist[0]['status'] != 'declined' else 'in a declined deal'}" if dist else "is also a borrower")
        head = f"{xn} is {_article(role)} of {yn}, which {what}: {deal_txt}"
        sentence = f"{xn} is {_article(role)} of {yn}; {yn} {what} in {deal_txt}." if not dist else \
                   f"{xn} is {_article(role)} of {yn}, which {what}; {yn} is the borrower in {deal_txt}."
    else:
        head = f"{yn}, {_article(rl)} of {xn}, is the borrower in {deal_txt}"
        sentence = f"{yn}, {_article(rl)} of {xn}, is also a borrower: {deal_txt}."
    link_where = where(edges[0], short=True) if edges else ""
    sid = "SG-" + G.hid(rule, x, y, focal_pid, n=12)
    return {"signal_id": sid, "rule": rule, "severity": sev, "title": head, "sentence": sentence + (f" Link: {link_where}." if link_where else ""),
            "focal": {"node_id": x, "name": xn, "proposal_id": focal_pid or None, "cif": me.get("cif")},
            "counterparty": {"node_id": y, "name": yn, "kind": ny["kind"], "role": role, "roles": d["roles"], "role_label": rl, "cif": ny.get("cif"),
                             "via": d.get("via") or ""},
            "standing": dist, "other_deals": [{"proposal_id": o["proposal_id"], "status": o.get("status"), "name": o.get("name")} for o in other],
            "evidence": edges[:6], "synthetic": any(e["synthetic"] for e in edges) or any(s.get("synthetic") for s in dist),
            "href": f"/deal-desk/{focal_pid}?b360=1" if focal_pid else (f"/deal-desk/customer-packs?cif={me.get('cif')}" if me.get("cif") else "")}


def _article(role: str) -> str:
    if role.startswith("connected"):
        return f"a company {role}"
    return ("an " if role[:1] in "aeiou" else "a ") + role


def for_deal(pid: str) -> list[dict[str, Any]]:
    d = G.deal(pid)
    if not d:
        return []
    return for_node(d["node_id"], pid)


def all_signals(min_severity: str = "medium") -> list[dict[str, Any]]:
    """Every deal's signals at or above min_severity (the brief's source)."""
    key = f"all:{min_severity}"
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    lim = SEV_RANK[min_severity]
    out = []
    for d in G.deals():
        out += [s for s in for_node(d["node_id"], d["proposal_id"]) if SEV_RANK[s["severity"]] <= lim]
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def summary(sigs: list[dict[str, Any]]) -> dict[str, int]:
    return {"high": sum(1 for s in sigs if s["severity"] == "high"), "medium": sum(1 for s in sigs if s["severity"] == "medium"),
            "low": sum(1 for s in sigs if s["severity"] == "low"), "total": len(sigs)}
