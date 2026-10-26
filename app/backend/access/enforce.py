"""Applying a policy to data: DataFrames (convo relations, engine inputs), JSON payloads (API responses, tool
results), SQL (DuckDB predicates) and Excel exports. Every function is a no-op for an unrestricted policy.

The current request's policy lives in a context variable (`use(policy)`, `current()`), set by the middleware for
HTTP requests and by the conversational agent for every turn, so engines deep in a service can ask for it.
"""
from __future__ import annotations

import contextvars
import io
import re
from contextlib import contextmanager
from typing import Any, Iterator

import pandas as pd

from backend.access import dims
from backend.access.policy import UNRESTRICTED, Policy

_CURRENT: contextvars.ContextVar[Policy] = contextvars.ContextVar("cp_access_policy", default=UNRESTRICTED)

#: Columns / keys that carry a book customer or exposure ID.
ID_KEYS = ("borrower_id", "customer_id", "obligor_id", "owner_id", "facility_id", "account_id", "group_id", "id",
           "object_id", "exposure_id", "counterparty_id")
NAME_KEYS = ("borrower_name", "customer_name", "obligor_name", "owner_name", "name", "group_name", "obligor",
             "counterparty_name")
_ID_RE = re.compile(r"^(CB\d{5}|CF\d{6}|CFN\d{5}|CG\d{1,5}|RC\d{6}|RA\d{6}(?:\d|[BM]\d)?)$")
_SECTOR_KEYS = {"sector": "sectors", "region": "regions", "branch_id": "branches", "rm_id": "rm_ids"}
MASKED_NAME = "Name withheld"


def current() -> Policy:
    return _CURRENT.get()


@contextmanager
def use(policy: Policy) -> Iterator[Policy]:
    tok = _CURRENT.set(policy)
    try:
        yield policy
    finally:
        _CURRENT.reset(tok)


def is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def mask_id(value: str) -> str:
    return value[:2] + "•" * (len(value) - 4) + value[-2:] if len(value) > 4 else "••"


# ------------------------------------------------------------------ DataFrames
def id_column(df: pd.DataFrame) -> str | None:
    for k in ID_KEYS:
        if k in df.columns:
            sample = df[k].dropna().astype(str).head(20)
            if len(sample) and sample.map(is_id).mean() > 0.5:
                return k
    return None


def filter_df(df: pd.DataFrame, policy: Policy | None = None) -> pd.DataFrame:
    """Keep the rows the policy allows (by the frame's customer/exposure ID column) and mask name/ID columns."""
    p = policy or current()
    if p.unrestricted or not p.row_restricted or df is None or not len(df):
        return df
    col = id_column(df)
    if col is None:
        return df
    books = {dims.book_of(x) for x in df[col].dropna().astype(str).str[:2].unique()}
    if (books and None not in books and not p.mask_names and not p.mask_ids
            and all(p.allows_book(b) and p.allowed_ids(b) is None for b in books)):
        return df   # every book in the frame is wholly visible to this user: no copy
    vals = df[col].astype(str)
    uniq = vals.unique()
    ok = {v for v in uniq if p.allows_id(v)}
    out = df[vals.isin(ok)].copy()
    if p.mask_names:
        for k in NAME_KEYS:
            if k in out.columns and not pd.api.types.is_numeric_dtype(out[k]):
                out[k] = MASKED_NAME
    if p.mask_ids:
        for k in ID_KEYS:
            if k in out.columns:
                out[k] = out[k].astype(str).map(lambda v: mask_id(v) if is_id(v) else v)
    return out


def sql_predicate(column: str, book: str, policy: Policy | None = None) -> str:
    """A DuckDB predicate on a customer-ID column ('TRUE' when every row is allowed)."""
    p = policy or current()
    if p.unrestricted:
        return "TRUE"
    if not p.allows_book(book):
        return "FALSE"
    ids = p.allowed_ids(book)
    if ids is None:
        return "TRUE"
    if not ids:
        return "FALSE"
    return f"{column} IN (" + ",".join(f"'{i}'" for i in sorted(ids) if _ID_RE.match(i)) + ")"


# ------------------------------------------------------------------ JSON payloads
def _record_id(d: dict[str, Any]) -> str | None:
    for k in ID_KEYS:
        v = d.get(k)
        if is_id(v):
            return v
    return None


def _dim_ok(d: dict[str, Any], p: Policy) -> bool:
    """An aggregate row keyed by a sector/region/branch/RM (no customer ID) is kept only when that value is inside
    the policy's scope for a book where the field is restricted. Rows naming a book the user lacks are dropped."""
    book = d.get("book")
    if isinstance(book, str) and book in ("corporate", "retail") and not p.allows_book(book):
        return False
    return True


def filter_json(obj: Any, policy: Policy | None = None) -> Any:
    p = policy or current()
    if p.unrestricted or not p.row_restricted:
        return obj
    return _walk(obj, p)


def _walk(obj: Any, p: Policy) -> Any:
    if isinstance(obj, list):
        out = []
        for x in obj:
            if isinstance(x, dict):
                rid = _record_id(x)
                if rid is not None and not p.allows_id(rid):
                    continue
                if not _dim_ok(x, p):
                    continue
            out.append(_walk(x, p))
        return out
    if isinstance(obj, dict):
        d = {k: _walk(v, p) for k, v in obj.items()}
        # A list that was filtered: its sibling count follows (total/count/row_count of the same object).
        for k, v in obj.items():
            if isinstance(v, list) and isinstance(d.get(k), list) and len(d[k]) != len(v):
                for ck in ("count", "row_count", "n", "total", "returned"):
                    if isinstance(obj.get(ck), int) and obj[ck] == len(v):
                        d[ck] = len(d[k])
        if _record_id(obj) is not None:
            if p.mask_names:
                for k in NAME_KEYS:
                    if isinstance(d.get(k), str) and d.get(k):
                        d[k] = MASKED_NAME
            if p.mask_ids:
                for k in ID_KEYS:
                    if is_id(d.get(k)):
                        d[k] = mask_id(d[k])
        return d
    return obj


def filter_rows(rows: list[dict[str, Any]] | None, policy: Policy | None = None) -> list[dict[str, Any]] | None:
    if rows is None:
        return None
    return filter_json(rows, policy)


# ------------------------------------------------------------------ Excel exports
def filter_xlsx(content: bytes, policy: Policy | None = None) -> bytes:
    """Delete every row whose cells carry a customer/exposure ID the policy does not allow; mask names and IDs."""
    p = policy or current()
    if p.unrestricted or not p.row_restricted:
        return content
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content))
    for ws in wb.worksheets:
        name_cols: set[int] = set()
        drop: list[int] = []
        for row in ws.iter_rows():
            ids = [c for c in row if is_id(c.value)]
            if not ids:
                for c in row:
                    if isinstance(c.value, str) and c.value.strip().lower() in (
                            "name", "borrower", "borrower name", "customer name", "obligor", "obligor name", "group name"):
                        name_cols.add(c.column)
                continue
            if not all(p.allows_id(c.value) for c in ids):
                drop.append(row[0].row)
                continue
            if p.mask_names:
                for c in row:
                    if c.column in name_cols and isinstance(c.value, str):
                        c.value = MASKED_NAME
            if p.mask_ids:
                for c in ids:
                    c.value = mask_id(c.value)
        for r in reversed(drop):
            ws.delete_rows(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filter_csv(content: bytes, policy: Policy | None = None) -> bytes:
    """Drop CSV lines carrying a customer/exposure ID outside the policy (IDs and names masked where it masks)."""
    p = policy or current()
    if p.unrestricted or not p.row_restricted:
        return content
    import csv

    text = content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    out = io.StringIO()
    w = csv.writer(out)
    name_cols: set[int] = set()
    for i, row in enumerate(rows):
        ids = [v for v in row if is_id(v)]
        if not ids:
            if i == 0:
                name_cols = {j for j, v in enumerate(row) if v.strip().lower() in NAME_KEYS}
            w.writerow(row)
            continue
        if not all(p.allows_id(v) for v in ids):
            continue
        row = [MASKED_NAME if (p.mask_names and j in name_cols) else (mask_id(v) if p.mask_ids and is_id(v) else v)
               for j, v in enumerate(row)]
        w.writerow(row)
    return out.getvalue().encode("utf-8")
