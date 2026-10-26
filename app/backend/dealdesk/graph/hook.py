"""Round G: the hooks that feed the graph from uploads.

For Round A (the agentic intake) — push what the agent read:

    from backend.dealdesk.graph.hook import push_documents

    result = push_documents(
        docs,                              # the documents the agent read, in R16's intake schema (below)
        borrower_name="Saqr Al Wadi Contracting Co.",
        cr_number="1010…",                 # optional: resolves the borrower to the Bank's customer and to other deals
        cif="",                            # optional: the Bank's customer id when known
        proposal_id="DD-…",                # optional: the deal the pack belongs to (joins the deal to the graph)
        run_id="AR-…",                     # the agent's run id; a re-run with the same id replaces that run's statements
        author="Noor (agentic intake)",
        as_of="2026-10-23",                # the date to stamp on a statement whose document carries no date of its own
    )
    # -> {"origin": "agent:AR-…", "documents": 16, "edges": 41, "statuses": 2, "facts": 23,
    #     "signals": {"high": 1, "medium": 0, "low": 2, "total": 3}, "borrower_node": "C-…"}

    A document: {"doc_id": "D3", "doc_type": "top_customers_suppliers", "doc_label": "Top customers and suppliers",
                 "file_name": "…", "pages": 2,
                 "fields": {"customers": {"value": [{"name": …, "sales": …, "share_pct": …}], "page": 1, "line": 12},
                            "customer_name": {"value": "…"}, …}}
    `fields` follows backend/dealdesk/intake/doctypes.py (field names and list columns); a field may be a plain value or
    {value, page, line}. Figures are stored exactly as given; the graph computes nothing.

    Every statement is stored with the document, page, line, date and author, under the origin "agent:<run_id>"; the call is
    idempotent per run, safe to call from a worker thread, and never raises on a bad document (it is skipped and counted).

For R16's intake (New proposal → Customer documents): `feed_intake_state(st)` is called by
backend/dealdesk/intake/service.publish after every change of a customer file (origin "intake:<IN-…>").
"""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

from backend.dealdesk.graph import from_docs as FD
from backend.dealdesk.graph import store as G

log = logging.getLogger(__name__)


def push_documents(docs: list[dict[str, Any]], *, borrower_name: str, cr_number: str = "", cif: str = "", proposal_id: str = "",
                   intake_id: str = "", run_id: str = "", author: str = "agentic intake", as_of: str = "",
                   source_kind: str = "agent") -> dict[str, Any]:
    """Map the documents an agent read into the graph (see the module docstring). Returns counts and the borrower's signals."""
    from backend.dealdesk.graph import build, signals
    build.ensure()
    origin = "agent:" + (run_id or intake_id or proposal_id or G.hid(borrower_name, cr_number, n=10))
    ctx = {"subject_name": borrower_name, "cr": re.sub(r"\D", "", cr_number or ""), "cif": cif, "proposal_id": proposal_id or None,
           "intake_id": intake_id or None, "origin": origin, "source_kind": source_kind, "author": author, "as_of": as_of or G.now()[:10]}
    out = {"origin": origin, "documents": 0, "skipped": 0, "edges": 0, "statuses": 0, "facts": 0}
    with G.tx() as c:
        G.clear_origin(c, origin)
        bnode = G.upsert_node(c, borrower_name, "company", cif=cif, cr=ctx["cr"])
        if proposal_id and not c.execute("SELECT 1 FROM deal WHERE proposal_id = ?", (proposal_id,)).fetchone():
            G.set_deal(c, proposal_id, bnode, name=borrower_name, status="new", source="agent", origin=origin)
        for d in docs or []:
            try:
                n = FD.ingest(c, d, ctx)
            except Exception as e:  # noqa: BLE001 - a malformed document is skipped, never fatal
                log.warning("graph push: %s skipped: %s", d.get("doc_id"), e)
                out["skipped"] += 1
                continue
            out["documents"] += 1
            for k in ("edges", "statuses", "facts"):
                out[k] += n[k]
    build.refresh_book()
    signals.clear()
    out["borrower_node"] = bnode
    out["signals"] = signals.summary(signals.for_node(bnode, proposal_id))
    return out


def ingest_intake_state(c: sqlite3.Connection, st: dict[str, Any]) -> dict[str, int]:
    """One R16 customer file (var/dealdesk/intake/<iid>/state.jsonl) → statements under origin intake:<iid>."""
    from backend.dealdesk.intake import service as IS
    iid = st["intake_id"]
    origin = f"intake:{iid}"
    G.clear_origin(c, origin)
    docs = [d for d in st.get("documents") or [] if d.get("doc_type") not in ("unreadable", "unknown")]
    if not docs:
        return {"documents": 0, "edges": 0}
    prof = IS._profile(docs)  # noqa: SLF001 - the file's own reading of the customer's name and CR
    if not prof.get("customer_name"):
        return {"documents": 0, "edges": 0}
    ctx = {"subject_name": prof["customer_name"], "cr": prof.get("cr_number") or "", "cif": "", "proposal_id": st.get("proposal_id") or None,
           "intake_id": iid, "origin": origin, "source_kind": "upload", "author": st.get("created_by") or "intake reader", "as_of": st.get("as_of") or ""}
    pid = st.get("proposal_id") or ""
    if pid:
        bnode = G.upsert_node(c, prof["customer_name"], "company", cr=ctx["cr"])
        if not c.execute("SELECT 1 FROM deal WHERE proposal_id = ?", (pid,)).fetchone():
            G.set_deal(c, pid, bnode, name=prof["customer_name"], status="new", source="uploaded", origin=origin)
    edges = 0
    for d in docs:
        edges += FD.ingest(c, d, ctx)["edges"]
    return {"documents": len(docs), "edges": edges}


def feed_intake_state(st: dict[str, Any]) -> None:
    """Best effort: called after an intake publish; a graph problem never fails the upload."""
    try:
        from backend.dealdesk.graph import build, signals
        build.ensure()
        with G.tx() as c:
            ingest_intake_state(c, st)
        build.refresh_book()
        signals.clear()
    except Exception as e:  # noqa: BLE001
        log.warning("graph: intake %s not fed: %s", st.get("intake_id"), e)
