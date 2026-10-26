"""The Borrower 360 book list (PLAN_R4 B2): every borrower or customer on a book at a period.

One row per corporate borrower (corp_borrower joined to its facilities) or retail
customer (ret_customer joined to its accounts) on book at the period. Amounts are
stated aggregations over the owner's exposures at that period (sums of limit, EAD
and ECL; worst stage and DPD); the Early Warning score is the Early Warning
service's own customer definition, the highest exposure score, banded by the rule
set's floors (backend/ews_domain/ews_rules.py). Nothing else is computed.

The rows for a book and period are materialised once as an in-memory table, so
paging, sorting on any column, search and every filter are one SQL query each.
The only names interpolated into SQL are this module's own table and column
names; every value is a parameter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.b360 import paths
from backend.b360.store import _LOCK, book_periods, clean, conn, rows
from backend.ews_domain import ews_rules as ews
from backend.v5common import ratings


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    unit: str = "text"
    default: bool = True
    #: The SQL that sorts this column, when it is not the column itself.
    order: str = ""


#: Rating bands on the global scale, best to worst.
RATING_BANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AAA to AA-", ("AAA", "AA+", "AA", "AA-")),
    ("A+ to A-", ("A+", "A", "A-")),
    ("BBB+ to BBB-", ("BBB+", "BBB", "BBB-")),
    ("BB+ to BB-", ("BB+", "BB", "BB-")),
    ("B+ to B-", ("B+", "B", "B-")),
    ("CCC to C", ("CCC", "CC", "C")),
    ("D", ("D",)),
)
SCORE_BANDS = ("A", "B", "C", "D", "E")
DPD_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0", 0, 0), ("1-29", 1, 29), ("30-59", 30, 59), ("60-89", 60, 89), ("90+", 90, None))
EWS_BANDS = ("none", "low", "moderate", "high", "critical")

COLUMNS: dict[str, list[Column]] = {
    "corporate": [
        Column("id", "Borrower ID", "id"),
        Column("name", "Borrower"),
        Column("group_name", "Group", default=False),
        Column("segment", "Sector"),
        Column("subsegment", "Sub-sector", default=False),
        Column("region", "Region"),
        Column("branch", "Branch", default=False),
        Column("business_unit", "Business unit", default=False),
        Column("rm", "Relationship manager", default=False),
        Column("tier", "Relationship tier", default=False),
        Column("products", "Products", default=False),
        Column("rating", "Rating", "rating", order="rating_rank"),
        Column("exposures", "Facilities", "int", default=False),
        Column("limit_mn", "Limit", "sar_mn", default=False),
        Column("ead", "EAD", "sar_mn"),
        Column("ecl", "ECL", "sar_mn"),
        Column("stage", "Stage", "int"),
        Column("dpd", "DPD", "days"),
        Column("ews_score", "EW score", "int"),
        Column("ews_band", "EW band", "ews_band", order="ews_rank"),
        Column("watchlist", "Watchlist", "flag", default=False),
        Column("sicr_codes", "SICR", "chips"),
        Column("utp_codes", "UTP", "chips"),
        Column("watch_status", "Watch status"),
    ],
    "retail": [
        Column("id", "Customer ID", "id"),
        Column("segment", "Segment"),
        Column("subsegment", "Employment", default=False),
        Column("region", "Region"),
        Column("branch", "Branch", default=False),
        Column("products", "Products"),
        Column("tenure", "Tenure (months)", "int", default=False),
        Column("behaviour_score", "Behaviour score", "num", default=False),
        Column("rating", "Score band", "rating"),
        Column("exposures", "Accounts", "int", default=False),
        Column("limit_mn", "Limit", "sar_mn", default=False),
        Column("ead", "EAD", "sar_mn"),
        Column("ecl", "ECL", "sar_mn"),
        Column("stage", "Stage", "int"),
        Column("dpd", "DPD", "days"),
        Column("ews_score", "EW score", "int"),
        Column("ews_band", "EW band", "ews_band", order="ews_rank"),
        Column("sicr_codes", "SICR", "chips"),
        Column("utp_codes", "UTP", "chips"),
    ],
}

#: The default order: the Early Warning ranking the landing page always had.
DEFAULT_SORT = ("ews_score", "desc")

#: Filters, by query parameter; `segment`/`subsegment` are sector/sub-sector on the corporate
#: book and customer segment/employment type on the retail book.
FILTERS = ("segment", "subsegment", "region", "branch", "product", "band", "stage", "ews", "dpd",
           "sicr", "utp", "watch", "rm", "card")


def labels(domain_id: str) -> dict[str, str]:
    corporate = domain_id == "corporate"
    return {"segment": "Sector" if corporate else "Segment", "subsegment": "Sub-sector" if corporate else "Employment",
            "region": "Region", "branch": "Branch", "product": "Product",
            "band": "Rating band" if corporate else "Score band", "stage": "Stage", "ews": "Early Warning band",
            "dpd": "DPD", "ead": "EAD (SAR m)",
            "sicr": "SICR reason", "utp": "UTP reason", "watch": "Watch status", "rm": "Relationship manager",
            "owner": "borrower" if corporate else "customer", "owners": "borrowers" if corporate else "customers",
            "exposures": "facilities" if corporate else "accounts"}


# ------------------------------------------------------------------ branch (B4 reference domain, when present)

def branch_source(domain_id: str) -> str | None:
    """The parquet file of the branch / RM reference domain for this book (backend/branch_domain), if it is on disk.

    It is keyed to the spine by owner and period: one branch per borrower-quarter or customer-month, in the
    owner's own book region; corporate rows also carry the business unit and relationship manager.
    """
    try:
        from backend.branch_domain import paths as bpaths
    except ImportError:
        return None
    path = bpaths.release_dir() / (bpaths.CORPORATE_FILE if domain_id == "corporate" else bpaths.RETAIL_FILE)
    return path.as_posix() if path.is_file() else None


def has_branch(domain_id: str) -> bool:
    return branch_source(domain_id) is not None


BRANCH_COLUMNS = ("branch", "business_unit", "rm")


def columns(domain_id: str) -> list[Column]:
    return [c for c in COLUMNS[domain_id] if c.key not in BRANCH_COLUMNS or has_branch(domain_id)]


# ------------------------------------------------------------------ the materialised book

def _ews_case(domain_id: str, score: str) -> tuple[str, str]:
    bands = ews.bands(domain_id)
    band = "CASE " + " ".join(f"WHEN {score} >= {int(f)} THEN '{n}'" for f, n in bands) + " ELSE 'none' END"
    rank = "CASE " + " ".join(f"WHEN {score} >= {int(f)} THEN {EWS_BANDS.index(n)}" for f, n in bands) + " ELSE 0 END"
    return band, rank


def _table(domain_id: str, period: str, overlay: bool = False) -> str:
    """The in-memory table of the book at `period` (built on first use). overlay=True (R16 d) also holds the demo
    customers of paths.OVERLAY: used only for a search, so the book list, its cards and totals stay the book's."""
    name = f"b360_list_{domain_id}_{re.sub(r'[^0-9A-Za-z]', '_', period)}" + ("_all" if overlay else "")
    with _LOCK:
        c = conn()
        if c.execute("SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = ?", [name]).fetchone()[0]:
            return name
        band, rank = _ews_case(domain_id, "COALESCE(e.score, 0)")
        br = branch_source(domain_id)
        if domain_id == "corporate":
            branch_join = (f"LEFT JOIN (SELECT borrower_id, branch_name AS branch, business_unit, rm_name AS rm "
                           f"FROM read_parquet('{br}') WHERE reporting_quarter = ?) br USING (borrower_id)") if br else ""
            sql = f"""
              CREATE TEMP TABLE {name}_base AS
              WITH f AS (SELECT borrower_id, COUNT(*) AS exposures, SUM(limit_sar_mn) AS limit_mn,
                                SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl, MAX(stage) AS stage, MAX(dpd_days) AS dpd,
                                list_sort(list_distinct(list(upper(left(product_type, 1)) || replace(substr(product_type, 2), '_', ' ')))) AS product_list
                         FROM corp_facility WHERE reporting_quarter = ? GROUP BY 1),
                   e AS (SELECT borrower_id, MAX(ews_score) AS score FROM ews_corp WHERE reporting_quarter = ? GROUP BY 1)
              SELECT b.borrower_id AS id, b.borrower_name AS name, b.group_id, b.group_name,
                     b.sector AS segment, b.sub_sector AS subsegment, b.region,
                     {"br.branch" if br else "NULL::VARCHAR"} AS branch,
                     {"br.business_unit" if br else "NULL::VARCHAR"} AS business_unit,
                     {"br.rm" if br else "NULL::VARCHAR"} AS rm,
                     b.relationship_tier AS tier, array_to_string(f.product_list, ', ') AS products, f.product_list,
                     b.rating_current AS rating, {ratings.sql_rank("b.rating_current")} AS rating_rank,
                     f.exposures, f.limit_mn, f.ead, f.ecl, f.stage, f.dpd,
                     COALESCE(e.score, 0)::INTEGER AS ews_score, {band} AS ews_band, {rank} AS ews_rank,
                     COALESCE(b.watchlist_flag, 0)::INTEGER AS watchlist, lower(b.borrower_id) AS _id,
                     lower(COALESCE(b.borrower_name, '')) AS _name
              FROM corp_borrower b JOIN f USING (borrower_id) LEFT JOIN e USING (borrower_id) {branch_join}
              WHERE b.reporting_quarter = ? AND NOT list_contains(?::VARCHAR[], b.borrower_id)"""
        else:
            branch_join = (f"LEFT JOIN (SELECT customer_id, branch_name AS branch FROM read_parquet('{br}') "
                           f"WHERE reporting_month = ?) br USING (customer_id)") if br else ""
            sql = f"""
              CREATE TEMP TABLE {name}_base AS
              WITH f AS (SELECT customer_id, COUNT(*) AS exposures, SUM(limit_sar_mn) AS limit_mn,
                                SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl, MAX(stage) AS stage, MAX(dpd_days) AS dpd,
                                list_sort(list_distinct(list(product))) AS product_list
                         FROM ret_account WHERE reporting_month = ? GROUP BY 1),
                   e AS (SELECT customer_id, MAX(ews_score) AS score FROM ews_ret WHERE reporting_month = ? GROUP BY 1)
              SELECT c.customer_id AS id, NULL::VARCHAR AS name, c.customer_segment AS segment,
                     c.employment_type AS subsegment, c.region,
                     {"br.branch" if br else "NULL::VARCHAR"} AS branch,
                     c.tenure_months AS tenure, c.behaviour_score,
                     array_to_string(f.product_list, ', ') AS products, f.product_list,
                     c.score_band AS rating, c.score_band AS rating_rank,
                     f.exposures, f.limit_mn, f.ead, f.ecl, f.stage, f.dpd,
                     COALESCE(e.score, 0)::INTEGER AS ews_score, {band} AS ews_band, {rank} AS ews_rank,
                     lower(c.customer_id) AS _id, '' AS _name
              FROM ret_customer c JOIN f USING (customer_id) LEFT JOIN e USING (customer_id) {branch_join}
              WHERE c.reporting_month = ?"""
        from backend.b360.store import overlay_ids   # R16 d: demo customers stay out of the book list and its totals
        c.execute(sql, [period, period] + ([period] if br else []) + [period] + ([[] if overlay else list(overlay_ids())] if domain_id == "corporate" else []))
        # PLAN_R9 B: P2 classification (SICR / UTP reasons, restructured, watch status, missing financials).
        from backend.b360 import intel
        frame, _ = intel.build(domain_id, period)
        c.register(f"{name}_intel_df", frame)
        c.execute(f"""CREATE TEMP TABLE {name} AS SELECT t.*, COALESCE(i.sicr_flag, 0) AS sicr_flag,
                          COALESCE(i.utp_flag, 0) AS utp_flag, i.sicr_codes, i.utp_codes,
                          COALESCE(i.restructured, 0) AS restructured, COALESCE(i.watch_status, 'None') AS watch_status,
                          COALESCE(i.missing_fs, 0) AS missing_fs
                      FROM {name}_base t LEFT JOIN {name}_intel_df i USING (id)""")
        c.unregister(f"{name}_intel_df")
        c.execute(f"DROP TABLE {name}_base")
        return name


def resolve_period(domain_id: str, period: str = "") -> str:
    periods = book_periods(domain_id)
    if not period:
        return periods[-1]
    if period not in periods:
        raise ValueError(f"{period!r} is not a period of the {domain_id} book; it runs {periods[0]}..{periods[-1]}.")
    return period


# ------------------------------------------------------------------ the query

@dataclass
class View:
    domain_id: str
    period: str = ""
    q: str = ""
    filters: dict[str, str] = field(default_factory=dict)
    ead_min: float | None = None
    ead_max: float | None = None
    sort: str = ""
    dir: str = ""


def _where(v: View) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []
    q = (v.q or "").strip().lower()
    if q:
        parts.append("(_id LIKE ? OR _name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    f = {k: str(x).strip() for k, x in (v.filters or {}).items() if x not in (None, "") and str(x).strip()}
    for key in ("segment", "subsegment", "region"):
        if key in f:
            parts.append(f"{key} = ?")
            params.append(f[key])
    if "branch" in f:
        if not has_branch(v.domain_id):
            raise ValueError("The branch filter needs the branch reference domain, which is not on this book yet.")
        parts.append("branch = ?")
        params.append(f["branch"])
    if "product" in f:
        parts.append("list_contains(product_list, ?)")
        params.append(f["product"])
    if "band" in f:
        if v.domain_id == "corporate":
            grades = dict(RATING_BANDS).get(f["band"]) or ((f["band"],) if f["band"] in ratings.RATING_ORDER else None)
            if not grades:
                raise ValueError(f"{f['band']!r} is not a rating band; use one of {[b for b, _ in RATING_BANDS]}.")
            parts.append(f"rating IN ({', '.join('?' for _ in grades)})")
            params += list(grades)
        else:
            if f["band"] not in SCORE_BANDS:
                raise ValueError(f"{f['band']!r} is not a score band; use one of {list(SCORE_BANDS)}.")
            parts.append("rating = ?")
            params.append(f["band"])
    if "stage" in f:
        if f["stage"] not in ("1", "2", "3"):
            raise ValueError(f"{f['stage']!r} is not a stage; use 1, 2 or 3.")
        parts.append("stage = ?")
        params.append(int(f["stage"]))
    if "ews" in f:
        if f["ews"] not in EWS_BANDS:
            raise ValueError(f"{f['ews']!r} is not an Early Warning band; use one of {list(EWS_BANDS)}.")
        parts.append("ews_band = ?")
        params.append(f["ews"])
    if "dpd" in f:
        bucket = next((b for b in DPD_BUCKETS if b[0] == f["dpd"]), None)
        if bucket is None:
            raise ValueError(f"{f['dpd']!r} is not a DPD bucket; use one of {[b[0] for b in DPD_BUCKETS]}.")
        parts.append("dpd >= ?" + ("" if bucket[2] is None else " AND dpd <= ?"))
        params += [bucket[1]] + ([] if bucket[2] is None else [bucket[2]])
    if "sicr" in f:
        parts.append("list_contains(string_split(COALESCE(sicr_codes, ''), ', '), ?)")
        params.append(f["sicr"])
    if "utp" in f:
        parts.append("list_contains(string_split(COALESCE(utp_codes, ''), ', '), ?)")
        params.append(f["utp"])
    if "watch" in f:
        parts.append("watch_status = ?")
        params.append(f["watch"])
    if "rm" in f:
        if not has_branch(v.domain_id) or v.domain_id != "corporate":
            raise ValueError("The relationship manager filter needs the branch reference domain on the corporate book.")
        parts.append("rm = ?")
        params.append(f["rm"])
    if "card" in f:
        from backend.b360 import intel
        if f["card"] not in intel.CARD_SQL:
            raise ValueError(f"{f['card']!r} is not a card; use one of {list(intel.CARD_SQL)}.")
        parts.append("(" + intel.CARD_SQL[f["card"]] + ")")
    if v.ead_min is not None:
        parts.append("ead >= ?")
        params.append(float(v.ead_min))
    if v.ead_max is not None:
        parts.append("ead <= ?")
        params.append(float(v.ead_max))
    # PLAN_R5 A1: only the customers the caller's data access policy allows (lists, totals and exports alike).
    from backend.access import sql_predicate
    pred = sql_predicate("id", "retail" if "retail" in str(v.domain_id) else "corporate")
    if pred != "TRUE":
        parts.append(pred)
    return ("WHERE " + " AND ".join(parts)) if parts else "", params


def _order(v: View) -> tuple[str, str, str]:
    cols = {c.key: c for c in columns(v.domain_id)}
    sort = v.sort or DEFAULT_SORT[0]
    if sort not in cols:
        raise ValueError(f"{sort!r} is not a column of the {v.domain_id} list; columns are {list(cols)}.")
    direction = (v.dir or ("desc" if not v.sort else "asc")).lower()
    if direction not in ("asc", "desc"):
        raise ValueError("dir is asc or desc.")
    expr = cols[sort].order or sort
    tail = ", ead DESC NULLS LAST" if sort == "ews_score" and not v.sort else ""
    return f"ORDER BY {expr} {direction.upper()} NULLS LAST{tail}, id ASC", sort, direction


PUBLIC = ["id", "name", "group_id", "group_name", "segment", "subsegment", "region", "branch", "business_unit", "rm", "tier", "products",
          "tenure", "behaviour_score", "rating", "exposures", "limit_mn", "ead", "ecl", "stage", "dpd", "ews_score",
          "ews_band", "watchlist", "sicr_flag", "utp_flag", "sicr_codes", "utp_codes", "restructured", "watch_status",
          "missing_fs"]


def _select(domain_id: str, table: str) -> str:
    with _LOCK:
        have = {r[0] for r in conn().execute(f"DESCRIBE {table}").fetchall()}
    return ", ".join(c for c in PUBLIC if c in have)


def _public_columns(domain_id: str) -> list[dict[str, Any]]:
    return [{"key": c.key, "label": c.label, "unit": c.unit, "default": c.default} for c in columns(domain_id)]


def page(v: View, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    period = resolve_period(v.domain_id, v.period)
    v.period = period
    book_table = _table(v.domain_id, period)
    # R16 d: a search also finds the demo customers (paths.OVERLAY); the book total below stays the book's
    table = _table(v.domain_id, period, overlay=True) if (v.q or "").strip() and v.domain_id == "corporate" else book_table
    where, params = _where(v)
    order, sort, direction = _order(v)
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 50), 500))
    agg = rows(f"SELECT COUNT(*) AS n, SUM(ead) AS ead, SUM(ecl) AS ecl, SUM(limit_mn) AS limit_mn, "
               f"SUM(exposures) AS exposures FROM {table} {where}", params)[0]
    from backend.access import sql_predicate   # PLAN_R5 A1: the "book" a restricted user sees is their part of it
    pred = sql_predicate("id", "retail" if "retail" in str(v.domain_id) else "corporate")
    book = rows(f"SELECT COUNT(*) AS n, SUM(ead) AS ead FROM {book_table}" + (f" WHERE {pred}" if pred != "TRUE" else ""))[0]
    found = rows(f"SELECT {_select(v.domain_id, table)} FROM {table} {where} {order} LIMIT ? OFFSET ?",
                 params + [limit, offset])
    return clean({
        "domain_id": v.domain_id, "period": period, "periods": list(book_periods(v.domain_id)),
        "total": agg["n"], "totals": {"ead": agg["ead"] or 0.0, "ecl": agg["ecl"] or 0.0,
                                      "limit": agg["limit_mn"] or 0.0, "exposures": agg["exposures"] or 0},
        "book_total": book["n"], "book_ead": book["ead"] or 0.0,
        "offset": offset, "limit": limit, "sort": sort, "dir": direction,
        "columns": _public_columns(v.domain_id),
        "rows": found, "labels": labels(v.domain_id), "branch_available": has_branch(v.domain_id),
    })


def all_rows(v: View) -> tuple[list[dict[str, Any]], str, str]:
    """Every row of the view, in its order (for the workbook)."""
    period = resolve_period(v.domain_id, v.period)
    v.period = period
    table = _table(v.domain_id, period)
    where, params = _where(v)
    order, sort, direction = _order(v)
    return rows(f"SELECT {_select(v.domain_id, table)} FROM {table} {where} {order}", params), sort, direction


def options(domain_id: str, period: str = "") -> dict[str, Any]:
    """The values every filter can take on this book at this period, with how many owners carry each."""
    period = resolve_period(domain_id, period)
    table = _table(domain_id, period)

    def counts(col: str) -> list[dict[str, Any]]:
        return [{"value": r["v"], "count": r["n"]} for r in
                rows(f"SELECT {col} AS v, COUNT(*) AS n FROM {table} WHERE {col} IS NOT NULL GROUP BY 1 ORDER BY 1")]

    subs = [{"value": r["v"], "parent": r["p"], "count": r["n"]} for r in
            rows(f"SELECT subsegment AS v, segment AS p, COUNT(*) AS n FROM {table} WHERE subsegment IS NOT NULL "
                 f"GROUP BY 1, 2 ORDER BY 2, 1")]
    products = [{"value": r["v"], "count": r["n"]} for r in
                rows(f"SELECT p AS v, COUNT(*) AS n FROM (SELECT unnest(product_list) AS p FROM {table}) GROUP BY 1 ORDER BY 1")]
    if domain_id == "corporate":
        have = {r["value"]: r["count"] for r in counts("rating")}
        bands = [{"value": b, "count": sum(have.get(g, 0) for g in grades)} for b, grades in RATING_BANDS]
    else:
        have = {r["value"]: r["count"] for r in counts("rating")}
        bands = [{"value": b, "count": have.get(b, 0)} for b in SCORE_BANDS]
    stage = {r["value"]: r["count"] for r in counts("stage")}
    ewsb = {r["value"]: r["count"] for r in counts("ews_band")}
    dpd = [{"value": key, "count": rows(f"SELECT COUNT(*) AS n FROM {table} WHERE dpd >= ?"
                                         + ("" if hi is None else " AND dpd <= ?"),
                                         [lo] + ([] if hi is None else [hi]))[0]["n"]}
           for key, lo, hi in DPD_BUCKETS]
    rng = rows(f"SELECT MIN(ead) AS lo, MAX(ead) AS hi FROM {table}")[0]
    return clean({
        "domain_id": domain_id, "period": period, "periods": list(book_periods(domain_id)),
        "labels": labels(domain_id),
        "segment": counts("segment"), "subsegment": subs, "region": counts("region"),
        "branch": counts("branch") if has_branch(domain_id) else [], "branch_available": has_branch(domain_id),
        "product": products, "band": bands,
        "stage": [{"value": str(s), "count": stage.get(s, 0)} for s in (1, 2, 3)],
        "ews": [{"value": b, "count": ewsb.get(b, 0)} for b in EWS_BANDS],
        "dpd": dpd, "ead": {"min": rng["lo"], "max": rng["hi"]},
        **_intel_options(table, domain_id),
        "columns": _public_columns(domain_id),
    })


def _intel_options(table: str, domain_id: str) -> dict[str, Any]:
    """PLAN_R9 B2: the SICR reason, UTP reason, watch status and RM filters, with counts."""
    from backend.b360 import intel

    def code_counts(col: str, catalogue: dict) -> list[dict[str, Any]]:
        have = {r["v"]: r["n"] for r in rows(f"SELECT v, COUNT(*) AS n FROM (SELECT unnest(string_split({col}, ', ')) AS v FROM {table} "
                                             f"WHERE COALESCE({col}, '') <> '') GROUP BY 1")}
        codes = sorted(have) if not any(k in have for k in catalogue) else [k for k in catalogue if have.get(k)] + \
            sorted(k for k in have if k not in catalogue)
        return [{"value": k, "label": intel.label(k), "count": have.get(k, 0)} for k in codes]
    watch = {r["v"]: r["n"] for r in rows(f"SELECT watch_status AS v, COUNT(*) AS n FROM {table} GROUP BY 1")}
    rm = (rows(f"SELECT rm AS value, COUNT(*) AS count FROM {table} WHERE rm IS NOT NULL GROUP BY 1 ORDER BY 1")
          if domain_id == "corporate" and has_branch(domain_id) else [])
    return {"sicr": code_counts("sicr_codes", intel.SICR), "utp": code_counts("utp_codes", intel.UTP),
            "watch": [{"value": w, "count": watch.get(w, 0)} for w in intel.WATCH], "rm": rm}


def cards(domain_id: str, period: str = "") -> dict[str, Any]:
    """PLAN_R9 B1: the top cards: count, exposure (EAD) and % of book EAD, each a filter (`card=`)."""
    from backend.b360 import intel
    from backend.access import sql_predicate
    period = resolve_period(domain_id, period)
    table = _table(domain_id, period)
    pred = sql_predicate("id", "retail" if "retail" in str(domain_id) else "corporate")
    base = "" if pred == "TRUE" else f" AND {pred}"
    book = rows(f"SELECT COUNT(*) AS n, SUM(ead) AS ead, SUM(ecl) AS ecl FROM {table} WHERE TRUE{base}")[0]
    out = []
    for key, label in intel.CARDS:
        r = rows(f"SELECT COUNT(*) AS n, SUM(ead) AS ead, SUM(ecl) AS ecl FROM {table} WHERE ({intel.CARD_SQL[key]}){base}")[0]
        out.append({"key": key, "label": label, "count": r["n"], "ead": r["ead"] or 0.0, "ecl": r["ecl"] or 0.0,
                    "pct_book": (r["ead"] or 0.0) / book["ead"] if book["ead"] else 0.0})
    return clean({"domain_id": domain_id, "period": period, "as_of": intel.period_date(period),
                  "book": {"count": book["n"], "ead": book["ead"] or 0.0, "ecl": book["ecl"] or 0.0},
                  "cards": out, "powered_by": {**intel.PACK, "articles": ["CBUAE CRM Art. 6", "CBUAE CRM Art. 7"],
                                                "confidence": "High", "trace": f"b360.cards/{domain_id}/{period}"}})
