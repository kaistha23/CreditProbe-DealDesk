"""The Lenses query engine: every figure on a lens is a DuckDB query over the books, with its SQL as the trace.

One in-memory DuckDB per process, loaded read-only from:
  - the Early Warning releases' enriched exposure relation (data/ews: the book rows with EWS score, band and
    reasons, branch, RM and current rating; `backend.ews_domain.reader.enriched`), and
  - the Cockpit lake's corp_borrower_quarter (DSCR, leverage, group) for corporate,
  - the Scorecard domain (data/scorecard_v5) and the Deal Desk domain (data/dealdesk).

Nothing is written back. `trace` on every result names the SQL that ran, the relations and releases it read,
the period and the row count, which the (i) on each tile shows.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

import duckdb

from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import DIMS, DISTRIBUTIONS, METRICS, Dim, Metric, order_sql

V5_PALETTE = ["#2563A8", "#C2410C", "#0E8A6A", "#7C3AED", "#A16207", "#0891B2", "#BE185D", "#3F6212",
              "#64748B", "#B45309", "#1D4ED8", "#047857"]
STAGE_COLOURS = {"Stage 1": "#0E8A6A", "Stage 2": "#A16207", "Stage 3": "#A92A25"}
BAND_COLOURS = {"critical": "#A92A25", "high": "#C2410C", "moderate": "#A16207", "low": "#64748B", "none": "#CBD5E1"}
TABLE = {"corporate": "corp", "retail": "ret"}
WINDOW = {"corporate": 8, "retail": 12}


BUILD = "lenses-engine-2"   # R13 L: new_write_off_sar_mn (a write-off counted once)
PPY = {"corporate": 4, "retail": 12}   # periods per year


class LensError(ValueError):
    """A lens request the engine cannot answer (an unknown metric, a value not in the book)."""


def _q(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


class Engine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.con: duckdb.DuckDBPyConnection | None = None
        self.sources: dict[str, list[str]] = {}
        self._periods: dict[str, list[str]] = {}
        self._values: dict[tuple[str, str], list[str]] = {}
        self.loaded_at = 0.0

    # ------------------------------------------------------------------ loading
    def load(self) -> None:
        with self._lock:
            if self.con is not None:
                return
            from backend.ews_domain import reader as rd
            from backend.ews_domain.paths import EWS_CORP, EWS_RET
            from backend.spine.books import book
            from backend.lenses_v5 import paths
            t0 = time.time()
            corp_book = book("corporate")
            bor = corp_book.path("corp_borrower_quarter")
            sc = paths.SCORECARD_DOMAIN
            dd = paths.DEALDESK_DOMAIN
            inputs = [p for p in (rd.DATASETS / EWS_CORP).glob("*.parquet")] + [p for p in (rd.DATASETS / EWS_RET).glob("*.parquet")] + \
                [p for p in __import__("backend.branch_domain.paths", fromlist=["release_dir"]).release_dir().glob("*.parquet")] + \
                [bor, sc / "SME-ANN.parquet", sc / "RET-BEH.parquet", dd / "dd_proposal.parquet", dd / "dd_result.parquet"]
            import hashlib
            import pathlib
            fp = hashlib.sha256(("|".join(f"{p}:{p.stat().st_size}:{int(p.stat().st_mtime)}" for p in sorted(map(pathlib.Path, inputs)) if p.exists())
                                 + "|" + BUILD).encode()).hexdigest()[:16]
            db = paths.engine_path()
            db.parent.mkdir(parents=True, exist_ok=True)
            stamp = db.with_suffix(".fingerprint")
            if not db.exists() or not stamp.exists() or stamp.read_text().strip() != fp:
                for f in (db, db.with_suffix(".duckdb.wal")):
                    if f.exists():
                        f.unlink()
                self._build(db, rd, bor, sc, dd)
                stamp.write_text(fp)
            con = duckdb.connect(str(db), read_only=True, config={"memory_limit": "384MB", "threads": "2"})
            self.sources = {
                "corporate": [EWS_CORP, corp_book.release_id, "scorecard-saudi-v1 (SME-ANN)", "dd-saudi-v1"],
                "retail": [EWS_RET, "v4-saudi-retail-20m-v5"],
            }
            self.con = con
            self.loaded_at = time.time() - t0

    def _build(self, db, rd, bor, sc, dd) -> None:
        """Materialise the lens relations once into var/lenses_v5/engine.duckdb (rebuilt when a source changes)."""
        con = duckdb.connect(str(db), config={"memory_limit": "1GB", "threads": "2"})
        con.execute(f"""CREATE TABLE corp AS SELECT
            e.reporting_quarter AS period, e.facility_id AS exposure_id, e.borrower_id AS owner_id, e.borrower_name AS owner_name,
            e.sector, e.sub_sector, e.region, e.relationship_tier, e.product_type, e.limit_sar_mn, e.drawn_sar_mn AS drawn,
            e.ead_sar_mn, e.ecl_sar_mn, e.stage, e.default_flag, e.dpd_days, e.pd_pit_12m, e.lgd_pct, e.write_off_sar_mn,
            e.utilisation_pct, e.collateral_ltv_pct, e.watchlist_flag, e.rating_notches_moved, e.covenant_breaches,
            e.ews_score, e.ews_band, e.ews_reasons, e.branch_name, e.business_unit, e.rm_name, e.rating_current,
            b.dscr_x, b.leverage_x, b.group_name
          FROM {rd.enriched('corporate')} e
          LEFT JOIN (SELECT borrower_id, reporting_quarter, dscr_x, leverage_x, group_name FROM read_parquet('{bor}')) b
            ON b.borrower_id = e.borrower_id AND b.reporting_quarter = e.reporting_quarter""")
        beh = rd.support("retail", "behaviour")
        con.execute(f"""CREATE TABLE ret AS SELECT
            e.reporting_month AS period, e.account_id AS exposure_id, e.customer_id AS owner_id, e.customer_id AS owner_name,
            e.product, e.sub_product, e.region, e.customer_segment, e.employment_type, e.delinquency_bucket, e.score_band,
            e.vintage_year, e.origination_channel, e.months_on_book, e.limit_sar_mn, e.balance_sar_mn AS drawn,
            e.ead_sar_mn, e.ecl_sar_mn, e.stage, e.default_flag, e.dpd_days, e.pd_pit_12m, e.lgd_pct, e.write_off_sar_mn,
            e.utilisation_pct, e.collateral_ltv_pct, e.ews_score, e.ews_band, e.ews_reasons, e.branch_name,
            e.behaviour_score, e.missed_payments_12m
          FROM {rd.enriched('retail')} e""")
        del beh
        # A write-off is a flow: count it in the period it is first written off. The corporate book carries the same
        # written-off amount on every quarter the facility stays at 360 DPD (2 to 11 quarters), which summed as a flow
        # multiplied write-offs and the cost of risk (R13 L ratio audit).
        for t in ("corp", "ret"):
            con.execute(f"""CREATE TABLE {t}_x AS SELECT *, CASE WHEN COALESCE(write_off_sar_mn, 0) > 0 AND COALESCE(
                LAG(write_off_sar_mn) OVER (PARTITION BY exposure_id ORDER BY period), 0) = 0 THEN write_off_sar_mn ELSE 0 END
                AS new_write_off_sar_mn FROM {t}""")
            con.execute(f"DROP TABLE {t}")
            con.execute(f"ALTER TABLE {t}_x RENAME TO {t}")
        con.execute(f"CREATE TABLE sc_corporate AS SELECT borrower_id AS owner_id, period, score, pd_model, y12, matured "
                    f"FROM read_parquet('{sc / 'SME-ANN.parquet'}')")
        con.execute(f"CREATE TABLE sc_retail AS SELECT account_id AS exposure_id, period, score, pd_model, y12, matured "
                    f"FROM read_parquet('{sc / 'RET-BEH.parquet'}')")
        con.execute(f"CREATE TABLE dd AS SELECT p.*, r.lifetime_raroc_pct, r.hurdle_pct, r.sva_sar_mn, r.approval_level "
                    f"FROM read_parquet('{dd / 'dd_proposal.parquet'}') p "
                    f"LEFT JOIN (SELECT * FROM read_parquet('{dd / 'dd_result.parquet'}') WHERE view = 'ask') r USING (proposal_id)")
        con.close()

    def q(self, sql: str) -> list[dict[str, Any]]:
        self.load()
        with self._lock:
            cur = self.con.execute(sql)  # type: ignore[union-attr]
            names = [d[0] for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    # ------------------------------------------------------------------ the book's shape
    def periods(self, book: str) -> list[str]:
        if book not in self._periods:
            self._periods[book] = [r["period"] for r in self.q(f"SELECT DISTINCT period FROM {TABLE[book]} ORDER BY 1")]
        return self._periods[book]

    def as_of(self, book: str) -> str:
        return self.periods(book)[-1]

    def window(self, book: str, period: str, n: int | None = None) -> list[str]:
        ps = self.periods(book)
        i = ps.index(period) if period in ps else len(ps) - 1
        n = n or WINDOW[book]
        return ps[max(0, i - n + 1): i + 1]

    def prior(self, book: str, period: str) -> str | None:
        ps = self.periods(book)
        i = ps.index(period)
        return ps[i - 1] if i > 0 else None

    def values(self, book: str, dim: str) -> list[str]:
        key = (book, dim)
        if key not in self._values:
            d = DIMS[dim]
            rows = self.q(f"SELECT DISTINCT {d.sql} AS k FROM {TABLE[book]} WHERE period = {_q(self.as_of(book))} AND {d.sql} IS NOT NULL ORDER BY 1")
            self._values[key] = [str(r["k"]) for r in rows]
        return self._values[key]

    # ------------------------------------------------------------------ SQL builders
    def where(self, book: str, filters: list[dict[str, Any]] | None) -> str:
        parts = []
        for f in filters or []:
            d = DIMS.get(f.get("dim", ""))
            if d is None or book not in d.books:
                raise LensError(f"'{f.get('dim')}' is not a dimension of the {book} book.")
            vals = [str(v) for v in f.get("values") or []]
            if vals:
                parts.append(f"{d.sql} IN ({', '.join(_q(v) for v in vals)})")
        return " AND ".join(parts) or "TRUE"

    def metric(self, key: str, book: str) -> Metric:
        m = METRICS.get(key)
        if m is None:
            raise LensError(f"'{key}' is not a metric in the catalogue.")
        if book not in m.books:
            raise LensError(f"{m.label} is not available for the {book} book.")
        return m

    def agg(self, m: Metric, extra: str = "") -> str:
        """The SQL aggregate of an in-table metric (sum, distinct, wavg, ratio)."""
        cond = " AND ".join(c for c in (m.cond, extra) if c)
        if m.kind == "sum":
            e = m.expr
            return f"SUM(CASE WHEN {cond} THEN {e} END)" if cond else f"SUM({e})"
        if m.kind == "distinct":
            return f"COUNT(DISTINCT CASE WHEN {cond} THEN owner_id END)" if cond else "COUNT(DISTINCT owner_id)"
        if m.kind == "wavg":
            c = f"{cond} AND {m.expr} IS NOT NULL" if cond else f"{m.expr} IS NOT NULL"
            return (f"(SUM(CASE WHEN {c} THEN {m.expr} * ead_sar_mn END) / NULLIF(SUM(CASE WHEN {c} THEN ead_sar_mn END), 0) * {m.scale})")
        if m.kind == "ratio":
            return f"({self.agg(METRICS[m.num], extra)} / NULLIF({self.agg(METRICS[m.den], extra)}, 0) * {m.scale})"
        raise LensError(f"{m.label} is not an in-table metric.")

    def custom_agg(self, c: dict[str, Any], book: str) -> str:
        num, den = self.metric(c["num"], book), self.metric(c["den"], book)
        for m in (num, den):
            if m.kind not in ("sum", "distinct"):
                raise LensError(f"{m.label} cannot be a numerator or denominator: pick an amount or a count.")
        filt = self.where(book, c.get("filters"))
        return f"({self.agg(num, filt if filt != 'TRUE' else '')} / NULLIF({self.agg(den)}, 0) * {float(c.get('scale', 100))})"

    # ------------------------------------------------------------------ series: metric values by period (and a dimension)
    def series(self, book: str, filters: list[dict[str, Any]] | None, periods: list[str], keys: list[str],
               dim: str = "", custom: dict[str, dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], str]:
        """Rows {period, k?, <key>: value} for in-table, cost-of-risk and custom metrics. Returns (rows, sql)."""
        T = TABLE[book]
        custom = custom or {}
        ms = {k: self.metric(k, book) for k in keys if k not in custom}
        want = list(periods)
        sel = []
        for k, m in ms.items():
            if m.kind in ("sum", "distinct", "wavg", "ratio"):
                sel.append(f"{self.agg(m)} AS \"{k}\"")
        for k, c in custom.items():
            sel.append(f"{self.custom_agg(c, book)} AS \"{k}\"")
        rows: list[dict[str, Any]] = []
        sql = ""
        d = DIMS.get(dim) if dim else None
        if sel:
            gk = f", {d.sql} AS k" if d else ""
            gb = "period, k" if d else "period"
            sql = (f"SELECT period{gk}, {', '.join(sel)} FROM {T} WHERE period IN ({', '.join(_q(p) for p in want)}) "
                   f"AND {self.where(book, filters)} GROUP BY {gb} ORDER BY {gb}")
            rows = self.q(sql)
        else:
            rows = [] if d else [{"period": p} for p in want]
        # cost of risk: trailing 12 months, flows exposure by exposure (cost_of_risk below)
        cor = [k for k, m in ms.items() if m.kind == "cor"]
        if cor:
            vals, cor_sql = self.cost_of_risk(book, filters, periods, dim)
            sql = (sql + ";\n" if sql else "") + cor_sql
            idx = {(r["period"], r.get("k")): r for r in rows}
            for (p, k), v in vals.items():
                tgt = idx.get((p, k))
                if tgt is None:
                    tgt = {"period": p, **({"k": k} if d else {})}
                    rows.append(tgt)
                    idx[(p, k)] = tgt
                for c in cor:
                    tgt[c] = v["bps"]
            if d:
                rows.sort(key=lambda r: (r["period"], str(r.get("k"))))
        rows = [r for r in rows if r["period"] in periods]
        # domain metrics (scorecard, deal desk)
        ext = [k for k, m in ms.items() if m.kind in ("scorecard", "dealdesk")]
        for k in ext:
            ext_rows, ext_sql = self.domain_metric(book, filters, periods, ms[k], dim)
            sql = (sql + ";\n" if sql else "") + ext_sql
            idx = {(r["period"], r.get("k")): r for r in rows}
            for er in ext_rows:
                tgt = idx.get((er["period"], er.get("k")))
                if tgt is None:
                    tgt = {"period": er["period"], **({"k": er["k"]} if d else {})}
                    rows.append(tgt)
                    idx[(er["period"], er.get("k"))] = tgt
                tgt[k] = er["v"]
        units = {k: (custom[k].get("unit", "pct") if k in custom else ms[k].unit) for k in keys}
        for r in rows:
            for k in keys:
                if k in r:
                    r[k] = fmt.round_for(r[k], units[k])
        return rows, sql

    def cor_flows(self, book: str, filters: list[dict[str, Any]] | None, lo: str, hi: str,
                  key_sql: str = "") -> tuple[list[dict[str, Any]], str]:
        """Per period and segment: the ECL build, the new write-offs and the EAD of the exposures in scope.

        Flows are taken exposure by exposure between consecutive periods:
          build_t = ECL_t - ECL_t-1 for an exposure in the book at both (ECL_t for one that arrived at t), and
                    - ECL_t-1 for one that left after t-1 (repaid or written off: its allowance is released);
          wo_t    = new write-offs (counted once, in the period first written off).
        The scope and the segment are read on the row the flow belongs to (period t; t-1 for a release), so an
        exposure moving into a filtered scope (Stage 3, a high Early Warning band) brings only its ECL build, not
        its whole stock of ECL. The first period loaded carries EAD only (it is the opening balance)."""
        T = TABLE[book]
        w = self.where(book, filters)
        k = key_sql or "NULL"
        sql = (f"WITH P AS (SELECT period, ROW_NUMBER() OVER (ORDER BY period) AS ix FROM (SELECT DISTINCT period FROM {T})), "
               f"B AS (SELECT t.period, P.ix, t.ecl_sar_mn AS ecl, COALESCE(t.new_write_off_sar_mn, 0) AS wo, t.ead_sar_mn AS ead, "
               f"({w}) AS ins, {k} AS k, LAG(P.ix) OVER w AS lix, LAG(t.ecl_sar_mn) OVER w AS lecl, LEAD(P.ix) OVER w AS nix "
               f"FROM {T} t JOIN P USING (period) WHERE t.period BETWEEN {_q(lo)} AND {_q(hi)} "
               f"WINDOW w AS (PARTITION BY t.exposure_id ORDER BY P.ix)), "
               f"L AS (SELECT MIN(ix) AS lo, MAX(ix) AS hi FROM B), "
               f"F AS (SELECT ix, k, ecl - CASE WHEN lix = ix - 1 THEN COALESCE(lecl, 0) ELSE 0 END AS build, wo, ead "
               f"FROM B, L WHERE ins AND ix > L.lo "
               f"UNION ALL SELECT ix + 1 AS ix, k, -COALESCE(ecl, 0) AS build, 0 AS wo, 0 AS ead FROM B, L "
               f"WHERE ins AND (nix IS NULL OR nix <> ix + 1) AND ix + 1 <= L.hi "
               f"UNION ALL SELECT ix, k, 0 AS build, 0 AS wo, ead FROM B, L WHERE ins AND ix = L.lo) "
               f"SELECT P.period, F.k, SUM(F.build) AS build, SUM(F.wo) AS wo, SUM(F.ead) AS ead, MIN(F.ix) = (SELECT lo FROM L) AS opening "
               f"FROM F JOIN P USING (ix) GROUP BY P.period, F.k ORDER BY 1, 2")
        return self.q(sql), sql

    def cost_of_risk(self, book: str, filters: list[dict[str, Any]] | None, periods: list[str],
                     dim: str = "") -> tuple[dict[tuple[str, Any], dict[str, Any]], str]:
        """Cost of risk at each period, trailing 12 months, in bps (annual by construction):
            CoR_t = sum over the last 12 months / 4 quarters of (build + wo) / average EAD (opening and period ends) x 10,000
        A window shorter than a year (the first periods of the history) is annualised by periods-per-year / periods
        and flagged `partial`. Returns {(period, k): {bps, build, wo, avg_ead, periods, partial}} and the SQL."""
        n = PPY[book]
        ps = self.periods(book)
        if not periods:
            return {}, ""
        i0 = max(0, ps.index(periods[0]) - n)
        d = DIMS.get(dim) if dim else None
        rows, sql = self.cor_flows(book, filters, ps[i0], periods[-1], d.sql if d else "")
        by: dict[Any, dict[str, dict[str, Any]]] = {}
        for r in rows:
            by.setdefault(r.get("k"), {})[r["period"]] = r
        out: dict[tuple[str, Any], dict[str, Any]] = {}
        for k, per in by.items():
            for p in periods:
                j = ps.index(p)
                win = [q for q in ps[max(0, j - n + 1): j + 1] if q in per and not per[q]["opening"]]
                eads = [per[q]["ead"] for q in ps[max(0, j - n): j + 1] if q in per and per[q]["ead"]]
                if not win or not eads or p not in per:
                    continue
                build = sum(per[q]["build"] or 0 for q in win)
                wo = sum(per[q]["wo"] or 0 for q in win)
                avg = sum(eads) / len(eads)
                if not avg:
                    continue
                out[(p, k)] = {"bps": (build + wo) / avg * 10000 * n / len(win), "build": build, "wo": wo, "avg_ead": avg,
                               "periods": len(win), "partial": len(win) < n}
        return out, sql

    def domain_metric(self, book: str, filters: list[dict[str, Any]] | None, periods: list[str], m: Metric,
                      dim: str = "") -> tuple[list[dict[str, Any]], str]:
        T = TABLE[book]
        d = DIMS.get(dim) if dim else None
        if m.kind == "scorecard":
            key = "owner_id" if book == "corporate" else "exposure_id"
            gk = f", MIN({d.sql}) AS k" if d else ""
            sql = (f"SELECT s.period{', x.k' if d else ''}, {m.expr} AS v FROM sc_{book} s JOIN "
                   f"(SELECT period, {key}{gk} FROM {T} WHERE period IN ({', '.join(_q(p) for p in periods)}) "
                   f"AND {self.where(book, filters)} GROUP BY period, {key}) x ON x.{key} = s.{key} AND x.period = s.period "
                   f"GROUP BY s.period{', x.k' if d else ''} ORDER BY 1")
            return self.q(sql), sql
        # deal desk: proposals in scope (sector, sub-sector, region filters apply); they sit at their own quarter
        conds = []
        for f in filters or []:
            if f.get("dim") in ("sector", "sub_sector", "region") and f.get("values"):
                conds.append(f"p.{f['dim']} IN ({', '.join(_q(v) for v in f['values'])})")
        gk = f", p.{dim} AS k" if dim in ("sector", "sub_sector", "region") else ""
        sql = (f"SELECT p.reporting_quarter AS period{gk}, {m.expr.replace('r.', 'p.')} AS v FROM dd p "
               f"WHERE {' AND '.join(conds) or 'TRUE'} GROUP BY p.reporting_quarter{', k' if gk else ''} ORDER BY 1")
        rows = [r for r in self.q(sql) if r["period"] in periods]
        return rows, sql

    # ------------------------------------------------------------------ trace
    def trace(self, book: str, sql: str, period: str, rows: int, relation: str = "") -> dict[str, Any]:
        src = list(self.sources.get(book, [])[:2])
        if "sc_" in sql:
            src.append("scorecard-saudi-v1")
        if " dd " in sql or "FROM dd" in sql:
            src.append("dd-saudi-v1")
        return {"sql": sql, "relations": [relation or TABLE[book]], "sources": src,
                "period": period, "row_count": rows, "engine": "duckdb", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


ENGINE = Engine()


def label_of(dim: Dim, k: Any) -> str:
    return "Not set" if k is None else str(k)


def finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def dim_order(dim: Dim) -> str:
    return order_sql(dim)


def distribution_meta(col: str) -> dict[str, Any]:
    if col not in DISTRIBUTIONS:
        raise LensError(f"'{col}' has no distribution.")
    return DISTRIBUTIONS[col]
