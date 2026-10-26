"""Round G: the graph store, one SQLite file under var/dealdesk/graph/ (DEALDESK_GRAPH_ROOT overrides the folder).

Tables
    node     one row per entity: company, person, bank, project, collateral, group, deal (name, normalised name, CIF, CR, the
             name embedding of names.vector, attributes as JSON)
    edge     one row per piece of evidence that two entities are linked: (src, rel, dst) with the document, page, line and date
             that showed it, or the Data Domains relation and row it was read from; `origin` names the feed that wrote it
             ("pack:c1", "intake:IN-…", "agent:<run>", "bank:R16-C1", "seed:links") so a feed is replaced as a whole
    status   what is known about an entity's credit standing (default, classified, past due, watch, restructured, declined
             deal), each with its evidence and date
    fact     a figure learned from a document (revenue, net profit, equity, SIMAH score…), copied exactly as read, with the
             document, page and date
    deal     the deals the graph joins (proposal id → the borrower's node, status)
    removed  edges a person removed (by id, author, date); a rebuild never brings them back
    meta     build version and timestamps

Everything learned is stored with its source, author and date, can be listed (api.py), and can be removed (`remove_edge`).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from backend.dealdesk.graph import names as N

V5 = pathlib.Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()

KINDS = ("company", "person", "bank", "project", "collateral", "group", "deal")

SCHEMA = """
CREATE TABLE IF NOT EXISTS node (
  node_id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, norm TEXT NOT NULL, cif TEXT, cr TEXT,
  attrs TEXT NOT NULL DEFAULT '{}', vec BLOB, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS node_norm ON node(norm);
CREATE INDEX IF NOT EXISTS node_cif ON node(cif);
CREATE INDEX IF NOT EXISTS node_cr ON node(cr);
CREATE TABLE IF NOT EXISTS edge (
  edge_id TEXT PRIMARY KEY, src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL, attrs TEXT NOT NULL DEFAULT '{}',
  source_kind TEXT NOT NULL, source_label TEXT, doc_id TEXT, doc_label TEXT, doc_type TEXT, intake_id TEXT, proposal_id TEXT,
  page INTEGER, line INTEGER, seen_date TEXT, author TEXT, origin TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT);
CREATE INDEX IF NOT EXISTS edge_src ON edge(src);
CREATE INDEX IF NOT EXISTS edge_dst ON edge(dst);
CREATE INDEX IF NOT EXISTS edge_origin ON edge(origin);
CREATE TABLE IF NOT EXISTS status (
  status_id TEXT PRIMARY KEY, node_id TEXT NOT NULL, status TEXT NOT NULL, note TEXT, source_kind TEXT NOT NULL, source_label TEXT,
  doc_id TEXT, doc_label TEXT, page INTEGER, line INTEGER, seen_date TEXT, author TEXT, origin TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0,
  created_at TEXT);
CREATE INDEX IF NOT EXISTS status_node ON status(node_id);
CREATE INDEX IF NOT EXISTS status_origin ON status(origin);
CREATE TABLE IF NOT EXISTS fact (
  fact_id TEXT PRIMARY KEY, node_id TEXT NOT NULL, field TEXT NOT NULL, label TEXT, value_text TEXT, value_num REAL, unit TEXT,
  period TEXT, source_kind TEXT NOT NULL, source_label TEXT, doc_id TEXT, doc_label TEXT, doc_type TEXT, intake_id TEXT, proposal_id TEXT,
  page INTEGER, line INTEGER, seen_date TEXT, author TEXT, origin TEXT NOT NULL, created_at TEXT);
CREATE INDEX IF NOT EXISTS fact_node ON fact(node_id);
CREATE INDEX IF NOT EXISTS fact_origin ON fact(origin);
CREATE TABLE IF NOT EXISTS deal (
  proposal_id TEXT PRIMARY KEY, node_id TEXT NOT NULL, name TEXT, status TEXT, workflow_state TEXT, source TEXT, rm TEXT,
  received_date TEXT, origin TEXT NOT NULL, updated_at TEXT);
CREATE INDEX IF NOT EXISTS deal_node ON deal(node_id);
CREATE TABLE IF NOT EXISTS removed (edge_id TEXT PRIMARY KEY, removed_by TEXT, removed_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def root() -> pathlib.Path:
    # a scratch Data Domains copy (tests: DEALDESK_R12_ROOT) gets its own graph, so it never overwrites the real one
    scratch = os.environ.get("DEALDESK_R12_ROOT")
    base = pathlib.Path(scratch) / "var" / "dealdesk" / "graph" if scratch else V5 / "var" / "dealdesk" / "graph"
    p = pathlib.Path(os.environ.get("DEALDESK_GRAPH_ROOT") or base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> pathlib.Path:
    return root() / "graph.sqlite"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(db_path(), timeout=30, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    return c


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        c = _connect()
        try:
            yield c
        finally:
            c.close()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _LOCK:
        c = _connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        finally:
            c.close()


def hid(*parts: Any, n: int = 16) -> str:
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:n]


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    if "attrs" in d:
        try:
            d["attrs"] = json.loads(d["attrs"] or "{}")
        except ValueError:
            d["attrs"] = {}
    d.pop("vec", None)
    return d


# ------------------------------------------------------------------------------------------------ nodes

PREFIX = {"company": "C", "person": "P", "bank": "B", "project": "J", "collateral": "K", "group": "G", "deal": "D"}


def _kind_ok(a: str, b: str) -> bool:
    return a == b


def find(c: sqlite3.Connection, name: str, kind: str, cif: str = "", cr: str = "") -> dict[str, Any] | None:
    """The node an identity resolves to: by CIF, then CR, then the normalised name, then the name embedding."""
    if cif:
        r = c.execute("SELECT * FROM node WHERE cif = ? AND kind = ?", (cif, kind)).fetchone()
        if r:
            return _row(r)
    if cr:
        r = c.execute("SELECT * FROM node WHERE cr = ? AND kind = ?", (cr, kind)).fetchone()
        if r:
            return _row(r)
    nm = N.norm(name)
    if not nm:
        return None
    r = c.execute("SELECT * FROM node WHERE norm = ? AND kind = ? ORDER BY (cif IS NULL OR cif = ''), node_id LIMIT 1", (nm, kind)).fetchone()
    if r:
        return _row(r)
    if kind in ("company", "person", "bank"):
        fw = N.first_word(name)
        v = N.vector(name)
        best, score = None, 0.0
        for r in c.execute("SELECT * FROM node WHERE kind = ? AND norm LIKE ?", (kind, (fw.split(" ")[0] if fw else "") + "%")):
            if N.first_word(r["name"]) != fw:
                continue
            ok, s = N.same(name, r["name"], v, N.unpack(r["vec"]))
            if ok and s > score:
                best, score = r, s
        if best is not None:
            return _row(best)
    return None


def upsert_node(c: sqlite3.Connection, name: str, kind: str, *, cif: str = "", cr: str = "", attrs: dict[str, Any] | None = None,
                node_id: str = "") -> str:
    """The node id for an identity, created when unknown; known CIF/CR and attributes are merged in."""
    name = N.clean_display(name)
    cif = str(cif or "").strip()
    cr = str(cr or "").strip()
    hit = None
    if node_id:
        hit = _row(c.execute("SELECT * FROM node WHERE node_id = ?", (node_id,)).fetchone())
    if hit is None:
        hit = find(c, name, kind, cif, cr)
    t = now()
    if hit is None:
        nid = node_id or f"{PREFIX.get(kind, 'N')}-{hid(kind, N.norm(name) or name, n=10)}"
        if c.execute("SELECT 1 FROM node WHERE node_id = ?", (nid,)).fetchone():  # same normalised name, another kind
            nid = f"{nid}-{hid(cif, cr, n=4)}"
        c.execute("INSERT INTO node(node_id, kind, name, norm, cif, cr, attrs, vec, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (nid, kind, name, N.norm(name), cif or None, cr or None, json.dumps(attrs or {}, default=str), N.pack(N.vector(name)), t, t))
        return nid
    upd: dict[str, Any] = {}
    if cif and not hit.get("cif"):
        upd["cif"] = cif
    if cr and not hit.get("cr"):
        upd["cr"] = cr
    if attrs:
        merged = {**(hit.get("attrs") or {}), **{k: v for k, v in attrs.items() if v not in (None, "")}}
        if merged != hit.get("attrs"):
            upd["attrs"] = json.dumps(merged, default=str)
    if upd:
        upd["updated_at"] = t
        c.execute(f"UPDATE node SET {', '.join(f'{k} = ?' for k in upd)} WHERE node_id = ?", (*upd.values(), hit["node_id"]))
    return hit["node_id"]


def node(node_id: str) -> dict[str, Any] | None:
    with conn() as c:
        return _row(c.execute("SELECT * FROM node WHERE node_id = ?", (node_id,)).fetchone())


def nodes(ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted(set(ids))
    if not ids:
        return {}
    with conn() as c:
        q = ",".join("?" * len(ids))
        return {r["node_id"]: _row(r) for r in c.execute(f"SELECT * FROM node WHERE node_id IN ({q})", ids)}  # type: ignore[misc]


def by_cif(cif: str) -> dict[str, Any] | None:
    with conn() as c:
        r = c.execute("SELECT * FROM node WHERE cif = ? ORDER BY kind = 'company' DESC LIMIT 1", (cif,)).fetchone()
        return _row(r)


def search(q: str, limit: int = 20) -> list[dict[str, Any]]:
    nm = N.norm(q)
    with conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM node WHERE norm LIKE ? OR cif = ? OR cr = ? ORDER BY kind, name LIMIT ?",
                                           (f"%{nm}%", q, q, limit))]  # type: ignore[misc]


# ------------------------------------------------------------------------------------------------ statements

def add_edge(c: sqlite3.Connection, src: str, rel: str, dst: str, ev: dict[str, Any], attrs: dict[str, Any] | None = None) -> str | None:
    """One piece of evidence for src —rel→ dst. `ev`: source_kind, source_label, origin and, for a document, doc_id, doc_label,
    doc_type, intake_id, proposal_id, page, line, seen_date, author; synthetic=True for a seeded demo link."""
    if src == dst:
        return None
    eid = "E-" + hid(ev["origin"], src, rel, dst, ev.get("doc_id") or ev.get("source_label"), ev.get("line") or "", ev.get("key") or "")
    if c.execute("SELECT 1 FROM removed WHERE edge_id = ?", (eid,)).fetchone():
        return None
    c.execute("""INSERT OR REPLACE INTO edge(edge_id, src, rel, dst, attrs, source_kind, source_label, doc_id, doc_label, doc_type, intake_id,
                 proposal_id, page, line, seen_date, author, origin, synthetic, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (eid, src, rel, dst, json.dumps(attrs or {}, default=str), ev["source_kind"], ev.get("source_label") or "", ev.get("doc_id"),
               ev.get("doc_label"), ev.get("doc_type"), ev.get("intake_id"), ev.get("proposal_id"), ev.get("page"), ev.get("line"),
               ev.get("seen_date"), ev.get("author") or "", ev["origin"], 1 if ev.get("synthetic") else 0, now()))
    return eid


def add_status(c: sqlite3.Connection, node_id: str, status: str, note: str, ev: dict[str, Any]) -> str:
    sid = "S-" + hid(ev["origin"], node_id, status, ev.get("doc_id") or ev.get("source_label"), ev.get("line") or "", note[:60])
    c.execute("""INSERT OR REPLACE INTO status(status_id, node_id, status, note, source_kind, source_label, doc_id, doc_label, page, line,
                 seen_date, author, origin, synthetic, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (sid, node_id, status, note, ev["source_kind"], ev.get("source_label") or "", ev.get("doc_id"), ev.get("doc_label"), ev.get("page"),
               ev.get("line"), ev.get("seen_date"), ev.get("author") or "", ev["origin"], 1 if ev.get("synthetic") else 0, now()))
    return sid


def add_fact(c: sqlite3.Connection, node_id: str, field: str, label: str, value: Any, unit: str, period: str, ev: dict[str, Any]) -> str:
    fid = "F-" + hid(ev["origin"], node_id, field, period, ev.get("doc_id") or "")
    num = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    c.execute("""INSERT OR REPLACE INTO fact(fact_id, node_id, field, label, value_text, value_num, unit, period, source_kind, source_label, doc_id,
                 doc_label, doc_type, intake_id, proposal_id, page, line, seen_date, author, origin, created_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (fid, node_id, field, label, "" if num is not None else str(value), num, unit, period, ev["source_kind"], ev.get("source_label") or "",
               ev.get("doc_id"), ev.get("doc_label"), ev.get("doc_type"), ev.get("intake_id"), ev.get("proposal_id"), ev.get("page"), ev.get("line"),
               ev.get("seen_date"), ev.get("author") or "", ev["origin"], now()))
    return fid


def set_deal(c: sqlite3.Connection, pid: str, node_id: str, *, name: str, status: str, workflow_state: str = "", source: str = "", rm: str = "",
             received_date: str = "", origin: str = "bank:deals") -> None:
    c.execute("""INSERT OR REPLACE INTO deal(proposal_id, node_id, name, status, workflow_state, source, rm, received_date, origin, updated_at)
                 VALUES (?,?,?,?,?,?,?,?,?,?)""", (pid, node_id, name, status, workflow_state, source, rm, received_date, origin, now()))


def clear_origin(c: sqlite3.Connection, origin: str, prefix: bool = False) -> None:
    op, val = ("LIKE", origin + "%") if prefix else ("=", origin)
    for t in ("edge", "status", "fact"):
        c.execute(f"DELETE FROM {t} WHERE origin {op} ?", (val,))
    c.execute(f"DELETE FROM deal WHERE origin {op} ?", (val,))


# ------------------------------------------------------------------------------------------------ reads

def edges_of(ids: Iterable[str], rels: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    ids = sorted(set(ids))
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    sql = f"SELECT * FROM edge WHERE (src IN ({q}) OR dst IN ({q}))"
    args: list[Any] = [*ids, *ids]
    if rels:
        sql += f" AND rel IN ({','.join('?' * len(rels))})"
        args += list(rels)
    with conn() as c:
        return [_row(r) for r in c.execute(sql + " ORDER BY seen_date DESC, edge_id", args)]  # type: ignore[misc]


def statuses_of(ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    ids = sorted(set(ids))
    out: dict[str, list[dict[str, Any]]] = {}
    if not ids:
        return out
    q = ",".join("?" * len(ids))
    with conn() as c:
        for r in c.execute(f"SELECT * FROM status WHERE node_id IN ({q}) ORDER BY seen_date DESC, status_id", ids):
            out.setdefault(r["node_id"], []).append(dict(r))
    return out


def facts_of(node_id: str) -> list[dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM fact WHERE node_id = ? ORDER BY period DESC, field", (node_id,))]


def deals() -> list[dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM deal ORDER BY proposal_id")]


def deal(pid: str) -> dict[str, Any] | None:
    with conn() as c:
        r = c.execute("SELECT * FROM deal WHERE proposal_id = ?", (pid,)).fetchone()
        return dict(r) if r else None


def deals_of(node_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    ids = sorted(set(node_ids))
    out: dict[str, list[dict[str, Any]]] = {}
    if not ids:
        return out
    q = ",".join("?" * len(ids))
    with conn() as c:
        for r in c.execute(f"SELECT * FROM deal WHERE node_id IN ({q}) ORDER BY proposal_id", ids):
            out.setdefault(r["node_id"], []).append(dict(r))
    return out


def edge(edge_id: str) -> dict[str, Any] | None:
    with conn() as c:
        return _row(c.execute("SELECT * FROM edge WHERE edge_id = ?", (edge_id,)).fetchone())


def remove_edge(edge_id: str, by: str, note: str = "") -> bool:
    """Remove one link (it stays removed across rebuilds); the removal is recorded with its author and date."""
    with tx() as c:
        hit = c.execute("SELECT 1 FROM edge WHERE edge_id = ?", (edge_id,)).fetchone()
        if not hit:
            return False
        c.execute("DELETE FROM edge WHERE edge_id = ?", (edge_id,))
        c.execute("INSERT OR REPLACE INTO removed(edge_id, removed_by, removed_at, note) VALUES (?,?,?,?)", (edge_id, by, now(), note))
    return True


def removed() -> list[dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM removed ORDER BY removed_at DESC")]


def meta_get(k: str) -> str | None:
    with conn() as c:
        r = c.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return r["v"] if r else None


def meta_set(c: sqlite3.Connection, k: str, v: str) -> None:
    c.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)", (k, v))


def counts() -> dict[str, Any]:
    with conn() as c:
        out = {t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("node", "edge", "status", "fact", "deal", "removed")}
        out["nodes_by_kind"] = {r[0]: r[1] for r in c.execute("SELECT kind, count(*) FROM node GROUP BY kind ORDER BY kind")}
        out["edges_by_source"] = {r[0]: r[1] for r in c.execute("SELECT source_kind, count(*) FROM edge GROUP BY source_kind ORDER BY 1")}
        out["edges_by_rel"] = {r[0]: r[1] for r in c.execute("SELECT rel, count(*) FROM edge GROUP BY rel ORDER BY 1")}
        return out
