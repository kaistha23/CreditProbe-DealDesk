"""Round G: build the graph (once per data version) and keep it fed.

    ensure()     builds the graph when the store is empty or its build version is stale; cheap otherwise
    rebuild()    replaces every derived feed: the deals on the desk and their neighbourhood in the Bank's data, the customer packs
                 read by R16's intake reader, every customer file uploaded on New proposal (var/dealdesk/intake), the seeded
                 demo links, and the book standing of every node; keeps what Round A's agent pushed (hook.push_documents) and
                 what a person removed

Feeds and their origin key in the store:
    bank:deals, bank:<pid>, bank:book     Data Domains (from_bank)
    pack:<key>                            data/dealdesk/demo_customers/<folder>/word/*.docx read by backend.dealdesk.intake
    intake:<IN-…>                         a customer file uploaded on New proposal (R16 intake), fed on every publish
    agent:<run>                           Round A's agentic intake (hook.push_documents)
    seed:links                            data/dealdesk/graph/seed_links.json (synthetic demo links, marked synthetic)
"""
from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import threading
import time
from typing import Any

from backend.dealdesk.graph import from_bank as FB
from backend.dealdesk.graph import from_docs as FD
from backend.dealdesk.graph import store as G

log = logging.getLogger(__name__)
BUILD = "g1"
V5 = pathlib.Path(__file__).resolve().parents[3]
PACKS = V5 / "data" / "dealdesk" / "demo_customers"
SEED = V5 / "data" / "dealdesk" / "graph" / "seed_links.json"
_BUILD_LOCK = threading.Lock()


def version() -> str:
    h = hashlib.sha1(BUILD.encode())
    for p in (SEED, PACKS / "customers.json"):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


DEALS_TTL = 120  # seconds: the deals' live status (approve, decline) reaches the graph within two minutes
_DEALS_AT = [0.0]


def ensure() -> dict[str, Any]:
    """Build the graph if it has never been built on this data version; refresh the deals' live status every two minutes."""
    if G.meta_get("version") == version():
        if time.time() - _DEALS_AT[0] > DEALS_TTL:
            refresh_deals()
        return {"built": False, "version": version()}
    with _BUILD_LOCK:
        if G.meta_get("version") == version():
            return {"built": False, "version": version()}
        out = rebuild()
        _DEALS_AT[0] = time.time()
        return out


def refresh_deals() -> int:
    """Re-read the deals on the desk and their live status (a decline today is a signal today)."""
    from backend.dealdesk.graph import signals
    _DEALS_AT[0] = time.time()
    try:
        with G.tx() as c:
            n = FB.deals(c)
    except Exception as e:  # noqa: BLE001
        log.warning("graph: deals not refreshed: %s", e)
        return 0
    signals.clear()
    return n


def _packs(c: Any) -> dict[str, int]:
    from backend.dealdesk.intake import service as IS
    out = {"documents": 0, "edges": 0}
    f = PACKS / "customers.json"
    if not f.exists():
        return out
    meta = json.loads(f.read_text())
    for cust in meta.get("customers", []):
        folder = PACKS / cust["folder"]
        mf = folder / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text())
        ctx = {"subject_name": cust["name"], "cr": cust.get("cr_number") or "", "cif": cust.get("cif") or "", "proposal_id": cust.get("proposal_id"),
               "origin": f"pack:{cust['key']}", "source_kind": "upload", "author": "intake reader (customer pack)", "as_of": meta.get("as_of") or ""}
        G.clear_origin(c, ctx["origin"])
        for d in m.get("documents", []):
            p = folder / ((d.get("files") or {}).get("docx") or "")
            if not p.is_file():
                continue
            try:
                doc = IS.read_one(p.name, p.read_bytes(), d["doc_id"])
            except Exception as e:  # noqa: BLE001 - one unreadable file never stops the build
                log.warning("graph: pack %s %s not read: %s", cust["key"], d["doc_id"], e)
                continue
            n = FD.ingest(c, doc, ctx)
            out["documents"] += 1
            out["edges"] += n["edges"]
    return out


def _seed_links(c: Any) -> int:
    G.clear_origin(c, "seed:links")
    if not SEED.exists():
        return 0
    data = json.loads(SEED.read_text())
    n = 0
    for lk in data.get("links", []):
        s, y, doc = lk["subject"], lk["counterparty"], lk.get("doc") or {}
        sid = G.upsert_node(c, s["name"], s.get("kind") or "company", cif=s.get("cif") or "", cr=s.get("cr") or "")
        yid = G.upsert_node(c, y["name"], y.get("kind") or "company", cif=y.get("cif") or "", cr=y.get("cr") or "")
        ev = {"source_kind": "upload", "source_label": FD.DOC_LABEL.get(doc.get("doc_type", ""), "Document"), "doc_id": doc.get("doc_id"),
              "doc_label": doc.get("doc_label"), "doc_type": doc.get("doc_type"), "proposal_id": lk.get("proposal_id"), "page": doc.get("page"),
              "line": doc.get("line"), "seen_date": doc.get("date"), "author": lk.get("author") or "seed", "origin": "seed:links", "synthetic": True}
        if G.add_edge(c, sid, lk["rel"], yid, ev, lk.get("attrs") or {}):
            n += 1
    return n


def _intake_files(c: Any) -> int:
    from backend.dealdesk.graph import hook
    from backend.dealdesk.intake import service as IS
    n = 0
    try:
        states = IS._states()  # noqa: SLF001 - the intake store's own list of files
    except Exception:  # noqa: BLE001
        return 0
    for st in states:
        try:
            hook.ingest_intake_state(c, st)
            n += 1
        except Exception as e:  # noqa: BLE001
            log.warning("graph: intake %s not fed: %s", st.get("intake_id"), e)
    return n


def rebuild() -> dict[str, Any]:
    t0 = time.time()
    from backend.dealdesk.graph import signals
    stats: dict[str, Any] = {}
    with G.tx() as c:
        G.clear_origin(c, "bank:", prefix=True)
        stats["deals"] = FB.deals(c)
        stats["bank_edges"] = 0
        for d in [r["proposal_id"] for r in c.execute("SELECT proposal_id FROM deal ORDER BY proposal_id")]:
            stats["bank_edges"] += FB.deal(c, d)["edges"]
        stats["packs"] = _packs(c)
        stats["seed_links"] = _seed_links(c)
        G.clear_origin(c, "intake:", prefix=True)  # re-fed below from the customer files that still exist
        stats["intake_files"] = _intake_files(c)
        stats["book_status"] = FB.book_status(c)
        G.meta_set(c, "version", version())
        G.meta_set(c, "built_at", G.now())
        G.meta_set(c, "build_stats", json.dumps(stats))
    signals.clear()
    stats["seconds"] = round(time.time() - t0, 2)
    stats["built"] = True
    stats["counts"] = G.counts()
    log.info("graph rebuilt: %s", stats)
    return stats


def refresh_book() -> int:
    """Re-read the book standing of every node (after new nodes arrived from an upload)."""
    from backend.dealdesk.graph import signals
    with G.tx() as c:
        G.clear_origin(c, "bank:book")
        n = FB.book_status(c)
    signals.clear()
    return n
