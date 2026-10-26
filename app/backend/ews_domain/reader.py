"""The EWS-only data reader.

Reads the two independent EWS releases under `paths.DATASETS`
(v5: data/ews/) and NOTHING else. The frozen Cockpit lake, the
Cockpit grid view, the Cockpit catalogue and the Cockpit runtime are not
imported, not opened and not reachable from here: `_relation()` refuses any
path that is not inside this domain's own dataset root, so a typo cannot
quietly fall back onto the book the Cockpit is serving.

Every figure is an aggregate of the release's own rows. `ews_score`,
`ews_band` and `ews_reasons` are read as the package already computed them
(gw-ews-1.0.0); no weight, threshold or band is recomputed here.
"""
from __future__ import annotations

import pathlib
import threading
from typing import Any

import duckdb

from backend.ews_domain.paths import DATASETS, EWS_CORP, EWS_RET  # noqa: E402

BANDS = ("critical", "high", "moderate", "low")
SEVERE = ("critical", "high")

DPD_BANDS: tuple[dict[str, Any], ...] = (
    {"key": "0-30", "label": "0-30 DPD", "low": 0, "high": 30},
    {"key": "1-10", "label": "1-10 DPD", "low": 1, "high": 10},
    {"key": "30-60", "label": "30-60 DPD", "low": 30, "high": 60},
)
DPD_OVERLAP = ("0-30 contains 1-10, so the bands are counted independently "
               "and are not added together.")

DOMAINS: dict[str, dict[str, Any]] = {
    "corporate": {
        "release_id": EWS_CORP,
        "source_release_id": "v4-saudi-corporate-20q-v4",
        "exposure": "ews_corp_exposure.parquet",
        "owner": "ews_corp_owner.parquet",
        "support": {"collateral": "ews_corp_collateral.parquet",
                    "covenant": "ews_corp_covenant.parquet"},
        "period": "reporting_quarter",
        "key": "facility_id",
        "owner_key": "borrower_id",
        "owner_name": "borrower_name",
        "exposure_grain": "facility",
        "owner_grain": "borrower",
        "segment": "sector",
        "subsegment": "sub_sector",
        "segment_label": "sector",
        "subsegment_label": "sub-sector",
        "alternate": "relationship_tier",
        "period_label": "quarter",
    },
    "retail": {
        "release_id": EWS_RET,
        "source_release_id": "v4-saudi-retail-20m-v5",
        "exposure": "ews_retail_exposure.parquet",
        "owner": "ews_retail_owner.parquet",
        "support": {"behaviour": "ews_retail_behaviour.parquet",
                    "collateral": "ews_retail_collateral.parquet"},
        "period": "reporting_month",
        "key": "account_id",
        "owner_key": "customer_id",
        "owner_name": None,
        "exposure_grain": "account",
        "owner_grain": "customer",
        "segment": "product",
        "subsegment": "sub_product",
        "segment_label": "product",
        "subsegment_label": "sub-product",
        "alternate": "delinquency_bucket",
        "period_label": "month",
    },
}

_LOCK = threading.RLock()
_CONN: duckdb.DuckDBPyConnection | None = None


class ReadRefused(Exception):
    """A read that would leave this domain's own datasets."""


def domain_spec(domain_id: str) -> dict[str, Any]:
    if domain_id not in DOMAINS:
        raise ReadRefused(f"{domain_id!r} is not an EWS domain; they are "
                          f"{sorted(DOMAINS)}.")
    return DOMAINS[domain_id]


def _relation(domain_id: str, file_name: str) -> str:
    """A read-only parquet scan, proven to be inside our own dataset root."""
    spec = domain_spec(domain_id)
    path = (DATASETS / spec["release_id"] / file_name).resolve()
    if DATASETS not in path.parents or not path.is_file():
        raise ReadRefused(f"{path} is not a file of this EWS domain's own "
                          f"release under {DATASETS}.")
    return f"read_parquet('{path}')"


def conn() -> duckdb.DuckDBPyConnection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            _CONN = duckdb.connect(":memory:")
        return _CONN


def q(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        cur = conn().execute(sql, params or [])
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def exposure(domain_id: str) -> str:
    return _relation(domain_id, domain_spec(domain_id)["exposure"])


def owner(domain_id: str) -> str:
    return _relation(domain_id, domain_spec(domain_id)["owner"])


def branch(domain_id: str) -> str:
    """The branch / RM reference domain (data/branches, keyed to the same book IDs and periods)."""
    from backend.branch_domain import read as branch_read
    from backend.branch_domain.paths import release_dir
    domain_spec(domain_id)
    root = release_dir().resolve()
    path = pathlib.Path(branch_read.path(domain_id)).resolve()
    if root not in path.parents or not path.is_file():
        raise ReadRefused(f"{path} is not a file of the branch reference domain under {root}.")
    return f"read_parquet('{path}')"


def enriched(domain_id: str) -> str:
    """The exposure relation with the level dimensions the book does not carry on the row: branch (both books),
    business unit, RM and current rating (corporate). One row per exposure row, joined on owner and period."""
    spec = domain_spec(domain_id)
    P, O = spec["period"], spec["owner_key"]
    if domain_id == "corporate":
        return (f'(SELECT e.*, b.branch_id, b.branch_name, b.business_unit, b.rm_id, b.rm_name, o.rating_current '
                f'FROM {exposure(domain_id)} e '
                f'LEFT JOIN {branch(domain_id)} b ON b."{O}" = e."{O}" AND b."{P}" = e."{P}" '
                f'LEFT JOIN (SELECT "{O}", "{P}", rating_current FROM {owner(domain_id)}) o '
                f'ON o."{O}" = e."{O}" AND o."{P}" = e."{P}")')
    return (f'(SELECT e.*, b.branch_id, b.branch_name FROM {exposure(domain_id)} e '
            f'LEFT JOIN {branch(domain_id)} b ON b."{O}" = e."{O}" AND b."{P}" = e."{P}")')


def series(domain_id: str, level: str) -> str:
    return _relation(domain_id, f"ews_series_{level}.parquet")


def reason_series(domain_id: str) -> str:
    return _relation(domain_id, "ews_reason_period.parquet")


def support(domain_id: str, name: str) -> str:
    files = domain_spec(domain_id)["support"]
    if name not in files:
        raise ReadRefused(f"{name!r} is not a support relation of {domain_id}; "
                          f"they are {sorted(files)}.")
    return _relation(domain_id, files[name])


def columns(domain_id: str) -> dict[str, str]:
    with _LOCK:
        cur = conn().execute(f"SELECT * FROM {exposure(domain_id)} LIMIT 0")
        return {d[0]: str(d[1]) for d in cur.description}


def periods(domain_id: str) -> list[str]:
    p = domain_spec(domain_id)["period"]
    return [r[p] for r in q(f"SELECT DISTINCT {p} AS {p} FROM "
                            f"{exposure(domain_id)} ORDER BY 1")]


def resolve_period(domain_id: str, wanted: str) -> tuple[str, str, list[str]]:
    """`(period, prior_period, periods)`. An unknown period is refused."""
    all_periods = periods(domain_id)
    chosen = wanted or all_periods[-1]
    if chosen not in all_periods:
        raise ReadRefused(
            f"{chosen!r} is not a period of {domain_spec(domain_id)['release_id']}; "
            f"it runs {all_periods[0]}..{all_periods[-1]}.")
    i = all_periods.index(chosen)
    return chosen, (all_periods[i - 1] if i else ""), all_periods


# ---- governed predicates ---------------------------------------------------
#
# A filter is compiled from a published column of THIS release and one of the
# published operators, parameterised. An unknown column or operator is refused
# rather than interpolated, so no caller can reach a relation or a value this
# domain does not publish.

OPS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def compile_filters(domain_id: str, filters: list[dict[str, Any]],
                    ) -> tuple[str, list[Any], list[str]]:
    cols = columns(domain_id)
    clauses: list[str] = []
    params: list[Any] = []
    described: list[str] = []
    for f in filters or []:
        col = str(f.get("column") or "")
        op = str(f.get("op") or "eq")
        if col not in cols:
            raise ReadRefused(f"{col!r} is not a column of "
                              f"{domain_spec(domain_id)['release_id']}.")
        values = f.get("values")
        value = f.get("value")
        if op in OPS:
            clauses.append(f'"{col}" {OPS[op]} ?')
            params.append(value)
            described.append(f"{col} {OPS[op]} {value}")
        elif op in ("in", "not_in"):
            vals = list(values or [])
            if not vals:
                continue
            marks = ", ".join("?" for _ in vals)
            clauses.append(f'"{col}" {"NOT " if op == "not_in" else ""}IN ({marks})')
            params.extend(vals)
            described.append(f"{col} {'not ' if op == 'not_in' else ''}in {vals}")
        elif op == "between":
            vals = list(values or [])
            if len(vals) != 2:
                raise ReadRefused("between needs exactly two values.")
            clauses.append(f'"{col}" BETWEEN ? AND ?')
            params.extend(vals)
            described.append(f"{col} between {vals[0]} and {vals[1]}")
        elif op == "contains":
            clauses.append(f'CAST("{col}" AS VARCHAR) ILIKE ?')
            params.append(f"%{value}%")
            described.append(f"{col} contains {value!r}")
        elif op == "is_null":
            clauses.append(f'"{col}" IS NULL')
            described.append(f"{col} is empty")
        elif op == "not_null":
            clauses.append(f'"{col}" IS NOT NULL')
            described.append(f"{col} is present")
        elif op in ("is_true", "is_false"):
            clauses.append(f'"{col}" = {1 if op == "is_true" else 0}')
            described.append(f"{col} is {'set' if op == 'is_true' else 'not set'}")
        else:
            raise ReadRefused(f"{op!r} is not a published filter operator.")
    return (" AND ".join(clauses) or "TRUE"), params, described


def dpd_filter(domain_id: str, dpd: str) -> list[dict[str, Any]]:
    if not dpd:
        return []
    band = next((b for b in DPD_BANDS if b["key"] == dpd), None)
    if band is None:
        raise ReadRefused(f"{dpd!r} is not a published delinquency band; they "
                          f"are {[b['key'] for b in DPD_BANDS]}.")
    if "dpd_days" not in columns(domain_id):
        raise ReadRefused("this release publishes no dpd_days.")
    return [{"column": "dpd_days", "op": "between",
             "values": [band["low"], band["high"]]}]


def reason_filter(domain_id: str, reason: str) -> list[dict[str, Any]]:
    """A warning reason, as the rule LABEL the package wrote into
    `ews_reasons`. An unpublished label is refused, never matched loosely."""
    if not reason:
        return []
    known = {r["reason"] for r in q(
        f"SELECT DISTINCT reason FROM {reason_series(domain_id)}")}
    if reason not in known:
        raise ReadRefused(f"{reason!r} is not a warning reason this release "
                          "published.")
    return [{"column": "ews_reasons", "op": "contains", "value": reason}]


def bands_filter(bands: list[str] | None) -> list[dict[str, Any]]:
    wanted = [b for b in (bands or []) if b in BANDS]
    if bands and not wanted:
        raise ReadRefused(f"{bands!r} are not published warning severities; "
                          f"they are {list(BANDS)}.")
    return [{"column": "ews_band", "op": "in", "values": wanted}] if wanted else []


__all__ = ["BANDS", "DPD_BANDS", "DPD_OVERLAP", "DATASETS", "DOMAINS", "SEVERE",
           "ReadRefused", "bands_filter", "columns", "compile_filters", "conn",
           "domain_spec", "dpd_filter", "exposure", "owner", "periods", "q",
           "reason_filter", "reason_series", "resolve_period", "series",
           "support"]
