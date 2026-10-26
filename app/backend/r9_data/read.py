"""Read API of the R9 shared data domains (contract: docs/STATUS_R9_DATA.md).

    from backend.r9_data import read as r9
    r9.table("dep_month", book="corporate", ids=["CB00001"])
    r9.classification("corporate", ids=["CF000011"])      # sicr_reasons / utp_reasons / ews_signals parsed to lists
    r9.ecl_run("2026Q3", "corporate")                       # equals the books at their as-of
    r9.anomalies()                                          # the planted ECL input anomalies
    r9.graph("CB00001")                                     # {"nodes": [...], "edges": [...]} one hop + group
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from backend.r9_data.paths import DOMAIN_TABLES, RUN_CURRENT, RUN_PRIOR, release_dir

TABLES: dict[str, str] = {t: d for d, ts in DOMAIN_TABLES.items() for t in ts}
_ID = {"dep_account": "obligor_id", "dep_month": "obligor_id", "dep_counterparty": "obligor_id",
       "dep_derived": "obligor_id", "orig_facility": "exposure_id", "cls_exposure": "exposure_id",
       "cls_reason": "exposure_id", "col_item": "exposure_id", "col_guarantee": "obligor_id",
       "col_restructured": "exposure_id", "col_related_party": "obligor_id", "col_crwa": "exposure_id",
       "ecl_facility": "exposure_id", "ecl_anomaly": "exposure_id"}


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((release_dir() / "manifest.json").read_text())


def as_of(book: str) -> str:
    """The as-of period of a book in this release (corporate quarter, retail month)."""
    return manifest()["as_of"][book]


def path(name: str) -> str:
    if name not in TABLES:
        raise KeyError(f"unknown R9 table {name!r}; known: {sorted(TABLES)}")
    return str(release_dir() / f"{name}.parquet")


@lru_cache(maxsize=32)
def _frame(name: str) -> pd.DataFrame:
    return pd.read_parquet(path(name))


def table(name: str, book: str | None = None, period: str | None = None, ids: list[str] | None = None,
          id_column: str | None = None) -> pd.DataFrame:
    """Any R9 table, optionally filtered by book, period (month / run / period column) and ids.

    `ids` filters on the table's natural id column (obligor_id or exposure_id), or `id_column` if given;
    an id list may mix obligor and exposure ids — a row matches if either column matches.
    """
    f = _frame(name)
    if book and "book" in f.columns:
        f = f[f.book == book]
    if period:
        for c in ("month", "run_id", "period", "book_period"):
            if c in f.columns:
                f = f[f[c] == period]
                break
    if ids is not None:
        ids = list(ids)
        if id_column:
            f = f[f[id_column].isin(ids)]
        else:
            m = pd.Series(False, index=f.index)
            for c in ("obligor_id", "exposure_id"):
                if c in f.columns:
                    m |= f[c].isin(ids)
            f = f[m]
    return f.reset_index(drop=True)


# --- deposits
def deposit_accounts(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("dep_account", book, ids=ids)


def deposit_months(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("dep_month", book, ids=ids)


def deposit_counterparties(book: str | None = None, ids: list[str] | None = None, month: str | None = None) -> pd.DataFrame:
    return table("dep_counterparty", book, period=month, ids=ids)


def deposit_derived(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("dep_derived", book, ids=ids)


# --- origination
def origination(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("orig_facility", book, ids=ids)


# --- classification
def classification(book: str | None = None, ids: list[str] | None = None, parse: bool = True) -> pd.DataFrame:
    f = table("cls_exposure", book, ids=ids)
    if parse:
        f = f.copy()
        for c in ("sicr_reasons", "utp_reasons", "ews_signals"):
            f[c] = f[c].map(json.loads)
    return f


def reasons(book: str | None = None, ids: list[str] | None = None, kind: str | None = None) -> pd.DataFrame:
    f = table("cls_reason", book, ids=ids)
    return f[f.kind == kind].reset_index(drop=True) if kind else f


# --- collateral
def collateral(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("col_item", book, ids=ids)


def guarantees(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("col_guarantee", book, ids=ids)


def restructured(book: str | None = None) -> pd.DataFrame:
    return table("col_restructured", book)


def related_parties(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("col_related_party", book, ids=ids)


def large_exposures() -> pd.DataFrame:
    return table("col_large_exposure")


def crwa(book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    return table("col_crwa", book, ids=ids)


# --- relationships
def graph(obligor_id: str, hops: int = 1) -> dict:
    """The obligor's network: every link touching it (and, for hops=2, touching its neighbours), plus the nodes."""
    links = _frame("rel_link")
    nodes = _frame("rel_node").set_index("node_id")
    seen = {obligor_id}
    sel = links.iloc[0:0]
    for _ in range(max(1, hops)):
        sel = links[links.src_id.isin(seen) | links.dst_id.isin(seen)]
        seen |= set(sel.src_id) | set(sel.dst_id)
    ns = nodes.reindex(sorted(seen)).reset_index()
    ns["name"] = ns["name"].fillna(ns["node_id"])
    ns["node_type"] = ns["node_type"].fillna("company")
    return {"nodes": ns.where(ns.notna(), None).to_dict("records"),
            "edges": sel.where(sel.notna(), None).to_dict("records")}


# --- ECL runs
def ecl_run(run_id: str = RUN_CURRENT, book: str | None = None, ids: list[str] | None = None) -> pd.DataFrame:
    if run_id not in (RUN_CURRENT, RUN_PRIOR):
        raise KeyError(f"ECL runs are {RUN_PRIOR} and {RUN_CURRENT}")
    return table("ecl_facility", book, period=run_id, ids=ids)


def anomalies() -> pd.DataFrame:
    return table("ecl_anomaly")
