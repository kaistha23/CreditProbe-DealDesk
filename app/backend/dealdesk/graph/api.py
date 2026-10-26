"""Round G: the graph and cross-deal intelligence on the Deal Desk service.

    GET    /api/v1/dealdesk/graph                       status: counts by kind, source and relation; built at; build stats
    POST   /api/v1/dealdesk/graph/rebuild               rebuild every derived feed (keeps agent pushes and removals)
    GET    /api/v1/dealdesk/graph/deal/{pid}            the deal's borrower: signals and one-hop neighbourhood with evidence
    GET    /api/v1/dealdesk/graph/customer?cif=         the same for a customer by the Bank's id
    GET    /api/v1/dealdesk/graph/signals?min=medium    every deal's signals (the brief's source)
    GET    /api/v1/dealdesk/graph/node/{node_id}        one entity: links, standing, figures, deals
    GET    /api/v1/dealdesk/graph/search?q=             entities by name, CIF or CR
    DELETE /api/v1/dealdesk/graph/edge/{edge_id}        remove a link (recorded with author and date; a rebuild keeps it removed)
    GET    /api/v1/dealdesk/graph/removed               the links people removed
    POST   /api/v1/dealdesk/graph/push                  Round A's hook over HTTP: {docs, borrower_name, cr_number, cif, proposal_id,
                                                        run_id, author, as_of} → hook.push_documents
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk.graph import build, hook, signals as SG, store as G

PREFIX = "/api/v1/dealdesk/graph"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-graph"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def neighbourhood(node_id: str, limit: int = 120) -> dict[str, Any]:
    """One hop around a node: the linked entities and every piece of evidence for each link."""
    edges = [e for e in G.edges_of([node_id]) if e["src"] == node_id or e["dst"] == node_id][:limit]
    ids = {e["src"] for e in edges} | {e["dst"] for e in edges} | {node_id}
    nodes = G.nodes(ids)
    st = G.statuses_of(ids)
    deals = G.deals_of(ids)
    return {"center": node_id,
            "nodes": [{**n, "standing": [s["status"] for s in st.get(i, [])], "deals": [d["proposal_id"] for d in deals.get(i, [])]} for i, n in nodes.items()],
            "edges": [{k: e.get(k) for k in ("edge_id", "src", "rel", "dst", "attrs", "source_kind", "source_label", "doc_id", "doc_label", "page", "line",
                                             "seen_date", "author", "origin", "synthetic", "proposal_id")} for e in edges]}


def _for(node_id: str | None, pid: str = "") -> dict[str, Any]:
    if not node_id:
        raise HTTPException(404, "Not in the graph yet.")
    sig = SG.for_node(node_id, pid)
    return {"node": G.node(node_id), "proposal_id": pid or None, "signals": sig, "summary": SG.summary(sig), "graph": neighbourhood(node_id),
            "built_at": G.meta_get("built_at")}


@router.get("")
def status() -> dict[str, Any]:
    build.ensure()
    stats = G.meta_get("build_stats")
    return {"counts": G.counts(), "built_at": G.meta_get("built_at"), "version": G.meta_get("version"),
            "build_stats": json.loads(stats) if stats else None, "store": str(G.db_path())}


@router.post("/rebuild")
def rebuild() -> dict[str, Any]:
    return build.rebuild()


@router.get("/deal/{pid}")
def deal(pid: str) -> dict[str, Any]:
    build.ensure()
    d = G.deal(pid)
    if not d:
        raise HTTPException(404, f"No deal {pid} in the graph.")
    return _for(d["node_id"], pid)


@router.get("/customer")
def customer(cif: str = Query(...)) -> dict[str, Any]:
    build.ensure()
    n = G.by_cif(cif)
    return _for(n["node_id"] if n else None)


@router.get("/signals")
def all_signals(min: str = Query("medium")) -> dict[str, Any]:  # noqa: A002 - the query word
    build.ensure()
    if min not in SG.SEV_RANK:
        raise HTTPException(400, "min is high, medium or low.")
    sig = SG.all_signals(min)
    return {"signals": sig, "summary": SG.summary(sig), "deals": len({s["focal"]["proposal_id"] for s in sig})}


@router.get("/node/{node_id}")
def node(node_id: str) -> dict[str, Any]:
    build.ensure()
    n = G.node(node_id)
    if not n:
        raise HTTPException(404, "No such entity.")
    return {"node": n, "standing": G.statuses_of([node_id]).get(node_id, []), "facts": G.facts_of(node_id),
            "deals": G.deals_of([node_id]).get(node_id, []), "graph": neighbourhood(node_id)}


@router.get("/search")
def search(q: str = Query(..., min_length=2)) -> dict[str, Any]:
    build.ensure()
    return {"nodes": G.search(q)}


@router.delete("/edge/{edge_id}")
def remove(edge_id: str, request: Request, note: str = Query("")) -> dict[str, Any]:
    if not G.remove_edge(edge_id, _user(request) or "unknown", note):
        raise HTTPException(404, "No such link.")
    SG.clear()
    try:
        from backend.dealdesk.borrower360 import service as B360
        B360.clear()
    except Exception:  # noqa: BLE001
        pass
    return {"removed": edge_id}


@router.get("/removed")
def removed() -> dict[str, Any]:
    return {"removed": G.removed()}


@router.post("/push")
def push(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not body.get("borrower_name") or not isinstance(body.get("docs"), list):
        raise HTTPException(400, "borrower_name and docs (a list) are required.")
    out = hook.push_documents(body["docs"], borrower_name=str(body["borrower_name"]), cr_number=str(body.get("cr_number") or ""),
                              cif=str(body.get("cif") or ""), proposal_id=str(body.get("proposal_id") or ""), intake_id=str(body.get("intake_id") or ""),
                              run_id=str(body.get("run_id") or ""), author=str(body.get("author") or _user(request) or "agentic intake"),
                              as_of=str(body.get("as_of") or ""))
    try:
        from backend.dealdesk.borrower360 import service as B360
        B360.clear()
    except Exception:  # noqa: BLE001
        pass
    return out
