"""The Data Builder reader: read-only DuckDB scans over the registry's parquet files.

Nothing here writes. A relation is opened only if the registry names it and its
file resolves inside `<v5>/data`. Every column a caller names (to show, sort
or filter on) is checked against the relation's schema before it reaches SQL,
identifiers are quoted, and every value is a bound parameter.
"""
from __future__ import annotations

import functools
import json
import math
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import duckdb

from backend.data_builder import dictionary
from backend.data_builder.paths import DATA, V5
from backend.data_builder.registry import DOMAINS

OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "in", "contains")
_CMP = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
NUMERIC = ("integer", "number", "flag")
MAX_PAGE = 500


class Refused(Exception):
    """A request the service will not run (unknown domain, relation, column, operator or period)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- relations

def spec(domain: str, relation: str) -> dict[str, Any]:
    dom = DOMAINS.get(domain)
    if dom is None:
        raise Refused(f"{domain!r} is not a Data Builder domain; they are {sorted(DOMAINS)}.", 404)
    rel = dom["relations"].get(relation)
    if rel is None:
        raise Refused(f"{relation!r} is not a relation of {domain!r}; they are {sorted(dom['relations'])}.", 404)
    return rel


#: Read-only roots besides data/: the What-If IFRS 9 domain, rebuilt from the books into var/ (PLAN_R4 18:58).
GLOB_ROOTS = ((V5 / "var" / "whatif_v5").resolve(),)


def _file(rel: dict[str, Any]) -> pathlib.Path:
    path = (V5 / rel["path"]).resolve() if not rel.get("glob") else (V5 / rel["path"]).parent.resolve() / pathlib.Path(rel["path"]).name
    if rel.get("glob"):
        # One relation over the files of one folder (one per period), only under the What-If root.
        folder = path.parent
        if not any(r == folder or r in folder.parents for r in GLOB_ROOTS) or not any(folder.glob(path.name)):
            raise Refused(f"{rel['path']} has no readable files.", 503)
        return path
    if DATA not in path.parents or not path.is_file():
        raise Refused(f"{rel['path']} is not a readable file under {DATA}.", 503)
    return path


def source(domain: str, relation: str) -> str:
    path = str(_file(spec(domain, relation))).replace("'", "''")
    return f"read_parquet('{path}')"


@functools.lru_cache(maxsize=1)
def _db() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def cursor() -> duckdb.DuckDBPyConnection:
    """A cursor of its own per call, so concurrent requests do not share state."""
    return _db().cursor()


def q(sql: str, args: list[Any] | None = None) -> list[dict[str, Any]]:
    cur = cursor()
    try:
        res = cur.execute(sql, args or [])
        names = [d[0] for d in res.description]
        return [dict(zip(names, map(_clean, row), strict=True)) for row in res.fetchall()]
    finally:
        cur.close()


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@functools.cache
def schema(domain: str, relation: str) -> list[dict[str, Any]]:
    rel = spec(domain, relation)
    cur = cursor()
    try:
        described = cur.execute(f"DESCRIBE SELECT * FROM {source(domain, relation)}").fetchall()
    finally:
        cur.close()
    return [dictionary.describe(rel, name, str(storage)) for name, storage, *_ in described]


@functools.cache
def facts(domain: str, relation: str) -> dict[str, Any]:
    """Row count and periods of one relation (the files are immutable releases)."""
    rel = spec(domain, relation)
    src = source(domain, relation)
    rows = q(f"SELECT COUNT(*) AS n FROM {src}")[0]["n"]
    periods: list[str] = []
    if rel.get("period_column"):
        pc = ident(rel["period_column"])
        periods = [str(r["p"]) for r in q(f"SELECT DISTINCT {pc} AS p FROM {src} WHERE {pc} IS NOT NULL ORDER BY 1")]
    return {"rows": int(rows), "periods": periods, "latest_period": periods[-1] if periods else None}


def release_of(rel: dict[str, Any]) -> str:
    return rel.get("release") or pathlib.PurePosixPath(rel["path"]).parent.name


def domains_payload() -> dict[str, Any]:
    """Every live domain; in the Deal Desk edition only the domains Deal Desk reads, relabelled for the RM
    (backend/v5common/edition.py), with a domain's relations narrowed to the ones Deal Desk uses."""
    from backend.v5common import edition as _ed
    only = _ed.DEALDESK_DOMAINS if _ed.is_dealdesk() else None
    out = []
    order = {d: i for i, d in enumerate(_ed.DEALDESK_DOMAIN_ORDER)} if only else {}
    for dom_id, dom in DOMAINS.items():
        if only is not None and dom_id not in only:
            continue
        spec = (only or {}).get(dom_id, {})
        allow = set(spec.get("relations") or [])
        relations = []
        for rel_id, rel in dom["relations"].items():
            if allow and rel_id not in allow:
                continue
            f = facts(dom_id, rel_id)
            relations.append({
                "relation": rel_id, "label": rel["label"], "book": rel["book"],
                "description": rel.get("description") or _manifest_description(rel),
                "grain": rel.get("grain") or _manifest_grain(rel),
                "rows": f["rows"], "periods": f["periods"], "latest_period": f["latest_period"],
                "period_column": rel.get("period_column"), "key_columns": rel["key_columns"],
                "columns": len(schema(dom_id, rel_id)), "release_id": release_of(rel),
            })
        out.append({"domain": dom_id, "label": spec.get("label") or dom["label"], "status": dom["status"],
                    "description": spec.get("description") or dom.get("description", ""), "relations": relations,
                    "rows": sum(r["rows"] for r in relations)})
    if only is not None:
        out.sort(key=lambda d: order.get(d["domain"], 99))
    return {"domains": out}


def _manifest_relation(rel: dict[str, Any]) -> dict[str, Any]:
    if rel.get("manifest_kind") != "cockpit":
        return {}
    stem = pathlib.PurePosixPath(rel["path"]).stem
    m = dictionary._load(rel["manifest"])
    return next((r for r in m.get("relations", []) if r.get("relation") == stem), {})


def _manifest_description(rel: dict[str, Any]) -> str:
    return _manifest_relation(rel).get("description", "")


def _manifest_grain(rel: dict[str, Any]) -> str:
    return _manifest_relation(rel).get("grain", "")


# ---------------------------------------------------------------- the query

@dataclass
class View:
    """One validated request: what to show, of which rows, in which order."""
    domain: str
    relation: str
    period: str | None = None
    compare_period: str | None = None
    search: str = ""
    filters: list[dict[str, Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    sort: str | None = None
    desc: bool = False


def parse_filters(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise Refused(f"filters must be a JSON list of {{column, op, value}}: {exc}") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(f, dict) for f in data):
        raise Refused("filters must be a JSON list of {column, op, value}.")
    return data


def parse_columns(raw: str | None) -> list[str]:
    return [c.strip() for c in (raw or "").split(",") if c.strip()]


class Plan:
    """The SQL for one View, with its bound arguments and the columns it returns."""

    def __init__(self, view: View):
        self.view = view
        self.rel = spec(view.domain, view.relation)
        self.schema = schema(view.domain, view.relation)
        self.by_name = {c["name"]: c for c in self.schema}
        self.src = source(view.domain, view.relation)
        self.pcol = self.rel.get("period_column")
        f = facts(view.domain, view.relation)
        for p in (view.period, view.compare_period):
            if p and p not in f["periods"]:
                raise Refused(f"{p!r} is not a period of {view.relation}; they run "
                              f"{f['periods'][0] if f['periods'] else '-'} to {f['latest_period'] or '-'}.")
        if view.compare_period and not self.pcol:
            raise Refused(f"{view.relation} has no period column to compare on.")
        self.period = view.period or (f["latest_period"] if view.compare_period else None)
        self.compare = view.compare_period
        for c in view.columns:
            self._col(c, "column")
        self.where, self.args = self._where()
        self.out_columns = self._out_columns()
        self.order = self._order()

    # -- validation
    def _col(self, name: Any, what: str) -> dict[str, Any]:
        if not isinstance(name, str) or name not in self.by_name:
            raise Refused(f"Unknown {what} {name!r} for {self.view.relation}; it has "
                          f"{len(self.schema)} columns (see /schema).")
        return self.by_name[name]

    def _value(self, col: dict[str, Any], value: Any) -> Any:
        if value is None:
            return None
        if col["type"] in NUMERIC:
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise Refused(f"{col['name']} is numeric; {value!r} is not a number.") from exc
        return str(value)

    # -- WHERE (applies to the primary period's rows)
    def _where(self) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        args: list[Any] = []
        if self.period and self.pcol:
            where.append(f"{ident(self.pcol)} = ?")
            args.append(self.period)
        term = (self.view.search or "").strip().lower()
        if term:
            text_cols = [c["name"] for c in self.schema if c["type"] == "text"]
            if text_cols:
                where.append("(" + " OR ".join(f"contains(lower({ident(c)}), ?)" for c in text_cols) + ")")
                args.extend([term] * len(text_cols))
            else:
                where.append("FALSE")
        for f in self.view.filters:
            col = self._col(f.get("column"), "filter column")
            op = f.get("op", "eq")
            if op not in OPS:
                raise Refused(f"Unknown filter operator {op!r}; use one of {', '.join(OPS)}.")
            name, value = ident(col["name"]), f.get("value")
            if op == "contains":
                where.append(f"contains(lower(CAST({name} AS VARCHAR)), ?)")
                args.append(str(value if value is not None else "").lower())
            elif op == "in":
                items = value if isinstance(value, list) else [v.strip() for v in str(value or "").split(",")]
                items = [self._value(col, v) for v in items if v is not None and str(v).strip() != ""]
                if not items:
                    raise Refused(f"Filter 'in' on {col['name']} needs at least one value.")
                where.append(f"{name} IN ({', '.join('?' for _ in items)})")
                args.extend(items)
            elif value is None or (isinstance(value, str) and value == "" and col["type"] in NUMERIC):
                if op not in ("eq", "neq"):
                    raise Refused(f"Filter {op!r} on {col['name']} needs a value.")
                where.append(f"{name} IS {'' if op == 'eq' else 'NOT '}NULL")
            else:
                where.append(f"{name} {_CMP[op]} ?")
                args.append(self._value(col, value))
        return where, args

    # -- the columns returned
    def _out_columns(self) -> list[dict[str, Any]]:
        chosen = self.view.columns or [c["name"] for c in self.schema]
        if not self.compare:
            return [{**self.by_name[c], "role": "key" if self.by_name[c]["key"] else "value", "base": c}
                    for c in chosen]
        keys = [k for k in self.rel["key_columns"] if k != self.pcol]
        out = [{**self.by_name[k], "role": "key", "base": k} for k in keys]
        for c in chosen:
            if c in keys or c == self.pcol:
                continue
            meta = self.by_name[c]
            out.append({**meta, "role": "value", "base": c, "period_of": self.period})
            out.append({**meta, "name": f"{c}__cmp", "label": f"{meta['label']} ({self.compare})",
                        "role": "compare", "base": c, "period_of": self.compare})
            if meta["type"] in ("integer", "number"):
                out.append({**meta, "name": f"{c}__delta", "label": f"{meta['label']} change",
                            "role": "delta", "base": c,
                            "description": f"{meta['label']} in {self.period} minus {self.compare}."})
        out.append({"name": "_presence", "label": "In both periods", "type": "text", "unit": "", "role": "presence",
                    "base": "_presence", "key": False, "period": False, "source": "registry",
                    "storage_type": "VARCHAR",
                    "description": f"'both' when the row exists in {self.period} and {self.compare}; "
                                   f"'new' when it has no {self.compare} row."})
        return out

    def _order(self) -> str:
        # Without a compare period the ORDER BY runs on the relation itself, so
        # any of its columns may sort; with one, only the columns being returned.
        names = {c["name"] for c in self.out_columns} if self.compare else set(self.by_name)
        keys = [k for k in self.rel["key_columns"] if not self.compare or k != self.pcol]
        parts: list[str] = []
        if self.view.sort:
            if self.view.sort not in names:
                raise Refused(f"Unknown sort column {self.view.sort!r} for {self.view.relation}.")
            parts.append(f"{ident(self.view.sort)} {'DESC' if self.view.desc else 'ASC'} NULLS LAST")
        parts += [ident(k) for k in keys if k != self.view.sort]
        return "ORDER BY " + ", ".join(parts) if parts else ""

    # -- SQL
    def _body(self) -> str:
        where = (" WHERE " + " AND ".join(self.where)) if self.where else ""
        if not self.compare:
            cols = ", ".join(ident(c["name"]) for c in self.out_columns)
            return f"SELECT {cols} FROM {self.src}{where}"
        keys = [k for k in self.rel["key_columns"] if k != self.pcol]
        sel = []
        for c in self.out_columns:
            n, base = c["name"], ident(c["base"])
            if c["role"] == "key":
                sel.append(f"a.{base} AS {ident(n)}")
            elif c["role"] == "value":
                sel.append(f"a.{base} AS {ident(n)}")
            elif c["role"] == "compare":
                sel.append(f"b.{base} AS {ident(n)}")
            elif c["role"] == "delta" and self.by_name[c["base"]]["type"] == "integer":
                sel.append(f"(a.{base} - b.{base}) AS {ident(n)}")
            elif c["role"] == "delta":
                sel.append(f"(CAST(a.{base} AS DOUBLE) - CAST(b.{base} AS DOUBLE)) AS {ident(n)}")
            elif c["role"] == "presence":
                sel.append(f"CASE WHEN b.{ident(keys[0])} IS NULL THEN 'new' ELSE 'both' END AS {ident(n)}")
        on = " AND ".join(f"a.{ident(k)} IS NOT DISTINCT FROM b.{ident(k)}" for k in keys)
        return (f"WITH a AS (SELECT * FROM {self.src}{where}), "
                f"b AS (SELECT * FROM {self.src} WHERE {ident(self.pcol)} = ?) "
                f"SELECT {', '.join(sel)} FROM a LEFT JOIN b ON {on}")

    def body_args(self) -> list[Any]:
        return self.args + ([self.compare] if self.compare else [])

    def count(self) -> int:
        where = (" WHERE " + " AND ".join(self.where)) if self.where else ""
        return int(q(f"SELECT COUNT(*) AS n FROM {self.src}{where}", self.args)[0]["n"])

    def _ordered(self) -> str:
        if self.compare:
            return f"SELECT * FROM ({self._body()}) t {self.order}"
        return f"{self._body()} {self.order}"

    def page(self, limit: int, offset: int) -> list[dict[str, Any]]:
        sql = f"{self._ordered()} LIMIT ? OFFSET ?"
        return q(sql, self.body_args() + [int(limit), int(offset)])

    def stream(self, cap: int | None = None, chunk: int = 20000) -> Iterator[list[tuple[Any, ...]]]:
        sql = self._ordered() + (" LIMIT ?" if cap else "")
        cur = cursor()
        try:
            res = cur.execute(sql, self.body_args() + ([int(cap)] if cap else []))
            while True:
                batch = res.fetchmany(chunk)
                if not batch:
                    break
                yield [tuple(_clean(v) for v in row) for row in batch]
        finally:
            cur.close()

    def describe_view(self) -> dict[str, Any]:
        return {"domain": self.view.domain, "relation": self.view.relation, "period": self.period,
                "compare_period": self.compare, "search": self.view.search or "", "filters": self.view.filters,
                "sort": self.view.sort, "desc": self.view.desc,
                "compare_basis": (f"Rows of {self.period} that match; their {self.compare} values are joined on "
                                  f"{', '.join(k for k in self.rel['key_columns'] if k != self.pcol)}."
                                  if self.compare else None)}
