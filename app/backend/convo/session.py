"""The query tool: one locked DuckDB session per (domain, scope), SELECT only.

Forked from the Cockpit (`catalog.open_session`, `execute_tool`; frozen, copied in
spirit, never imported). The same boundary holds: the session holds ONE domain's
relations, materialised as in-memory tables, and is then locked
(`enable_external_access = false`, `lock_configuration = true`) before any
authored SQL is admitted, so a query can read those tables and nothing else.
The SQL that runs is byte-for-byte the SQL the assistant wrote (wrapped only in a
row cap); a refusal names the check that refused it, and the assistant writes the
replacement. Nothing here repairs a query.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.convo.spec import Domain, Relation

MAX_ROWS = 500
TIMEOUT_S = 20.0
MAX_SESSIONS = 8

_FORBIDDEN = re.compile(r"\b(insert|update|delete|create|drop|alter|copy|attach|detach|pragma|set|install|load|export|"
                        r"import|call|checkpoint|vacuum|use|grant|truncate|replace)\b", re.I)
_FILE_FUNCS = re.compile(r"\b(read_\w+|glob|sniff_csv|parquet_\w+|query_table|getenv)\s*\(", re.I)


class QueryRefused(ValueError):
    def __init__(self, check: str, message: str):
        super().__init__(message)
        self.check = check


@dataclass
class Session:
    domain: str
    key: str
    con: Any
    relations: dict[str, Relation]
    counts: dict[str, int]
    columns: dict[str, list[tuple[str, str]]]
    lock: threading.Lock
    built_s: float

    def catalog(self) -> list[dict[str, Any]]:
        out = []
        for name, rel in self.relations.items():
            out.append({"relation": name, "description": rel.description, "grain": rel.grain, "rows": self.counts[name],
                        "columns": [{"name": c, "type": t, "description": rel.columns.get(c, "")}
                                    for c, t in self.columns[name]]})
        return out

    def query(self, sql: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
        text = check_sql(sql, set(self.relations))
        wrapped = f"SELECT * FROM ({text}) AS q LIMIT {int(max_rows) + 1}"
        t0 = time.monotonic()
        with self.lock:
            timer = threading.Timer(TIMEOUT_S, self.con.interrupt)
            timer.start()
            try:
                cur = self.con.execute(wrapped)
                cols = [d[0] for d in cur.description]
                raw = cur.fetchall()
            except Exception as e:  # noqa: BLE001 - every engine error goes back to the author, named
                msg = str(e).split("\n")[0][:400]
                if "interrupt" in msg.lower():
                    raise QueryRefused("runtime", f"The query ran longer than {TIMEOUT_S:.0f}s and was stopped.") from e
                raise QueryRefused("runtime", msg) from e
            finally:
                timer.cancel()
        truncated = len(raw) > max_rows
        rows = [{c: _plain(v) for c, v in zip(cols, r)} for r in raw[:max_rows]]
        return {"columns": cols, "rows": rows, "row_count": len(rows), "truncated": truncated,
                "ms": int((time.monotonic() - t0) * 1000)}


def _plain(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, bool)):
        return v
    if isinstance(v, float):
        return None if v != v else v
    try:
        import decimal
        if isinstance(v, decimal.Decimal):
            return float(v)
    except ImportError:  # pragma: no cover
        pass
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return str(v)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)


def check_sql(sql: str, relations: set[str]) -> str:
    """The structure check. Returns the statement to run (comments and a trailing ';' removed)."""
    text = _strip_comments(str(sql or "")).strip().rstrip(";").strip()
    if not text:
        raise QueryRefused("sql_structure", "The query is empty.")
    if ";" in text:
        raise QueryRefused("sql_structure", "One statement per query.")
    if not re.match(r"^(select|with)\b", text, re.I):
        raise QueryRefused("sql_structure", "Only SELECT (or WITH ... SELECT) queries are allowed.")
    # Keywords inside string literals are data, not statements.
    bare = re.sub(r"'(?:[^']|'')*'", "''", text)
    m = _FORBIDDEN.search(bare)
    if m:
        raise QueryRefused("sql_structure", f"'{m.group(1)}' is not allowed: queries are read-only.")
    m = _FILE_FUNCS.search(bare)
    if m:
        raise QueryRefused("relation_authorization", f"{m.group(1)}() is not allowed: query the domain's relations only.")
    return text


_SESSIONS: dict[tuple[str, str], Session] = {}
_LOCK = threading.Lock()


def open_session(domain: Domain, scope: dict[str, Any], policy=None) -> Session:
    # The caller's data access policy is part of the key: two users with different policies never share rows.
    fp = "" if policy is None or policy.unrestricted or not policy.row_restricted else "|access:" + policy.fingerprint
    key = (domain.key, domain.scope_key(scope) + fp)
    with _LOCK:
        hit = _SESSIONS.get(key)
    if hit is not None:
        return hit
    s = _build(domain, scope, key[1], policy if fp else None)
    with _LOCK:
        _SESSIONS[key] = s
        while len(_SESSIONS) > MAX_SESSIONS:
            _, old = next(iter(_SESSIONS.items()))
            _SESSIONS.pop(next(iter(_SESSIONS)))
            try:
                old.con.close()
            except Exception:  # noqa: BLE001
                pass
    return s


def _build(domain: Domain, scope: dict[str, Any], key: str, policy=None) -> Session:
    import duckdb

    t0 = time.monotonic()
    con = duckdb.connect(database=":memory:")
    con.execute("SET threads TO 2")
    con.execute("SET memory_limit = '1024MB'")
    rels: dict[str, Relation] = {}
    counts: dict[str, int] = {}
    cols: dict[str, list[tuple[str, str]]] = {}
    for rel in domain.relations(scope):
        df = rel.load(scope)
        if policy is not None:   # PLAN_R5 A1: only the rows the caller's policy allows enter the session
            from backend.access import filter_df
            df = filter_df(df, policy)
        tmp = f"__src_{rel.name}"
        con.register(tmp, df)
        con.execute(f'CREATE TABLE "{rel.name}" AS SELECT * FROM "{tmp}"')
        con.unregister(tmp)
        rels[rel.name] = rel
        counts[rel.name] = int(con.execute(f'SELECT COUNT(*) FROM "{rel.name}"').fetchone()[0])
        cols[rel.name] = [(r[0], r[1]) for r in con.execute(f'DESCRIBE "{rel.name}"').fetchall()]
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return Session(domain=domain.key, key=key, con=con, relations=rels, counts=counts, columns=cols,
                   lock=threading.Lock(), built_s=round(time.monotonic() - t0, 3))


def reset() -> None:
    with _LOCK:
        for s in _SESSIONS.values():
            try:
                s.con.close()
            except Exception:  # noqa: BLE001
                pass
        _SESSIONS.clear()
