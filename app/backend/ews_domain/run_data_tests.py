"""Data tests for the new EWS packages against the frozen Cockpit books.

Every test is a query over the frozen source and over the new package. Raw
true exit: the process exits non-zero if any test fails.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.ews_domain.build_packages import (CORP_SRC, EWS_CORP, EWS_RET,  # noqa: E402
                                               FROZEN, OUT, RET_SRC, conn)
from backend.ews_domain import ews_rules as ews  # noqa: E402

from backend.ews_domain.paths import EVIDENCE as EV  # noqa: E402
RESULTS: list[dict] = []


def check(name: str, domain: str, expect, got, detail: str = "") -> bool:
    ok = expect == got
    RESULTS.append({"test": name, "domain": domain, "status": "PASS" if ok else "FAIL",
                    "expected": expect, "observed": got, "detail": detail})
    return ok


def one(c, sql):
    return c.execute(sql).fetchone()[0]


SPEC = {
    "corporate": {"release": EWS_CORP, "src": CORP_SRC, "period": "reporting_quarter",
                  "key": "facility_id", "owner": "borrower_id",
                  "exposure_file": "ews_corp_exposure.parquet",
                  "owner_file": "ews_corp_owner.parquet",
                  "src_exposure": "corp_facility_quarter",
                  "src_owner": "corp_borrower_quarter",
                  "segment": "sector", "sub_segment": "sub_sector",
                  "latest": "2026Q2"},
    "retail": {"release": EWS_RET, "src": RET_SRC, "period": "reporting_month",
               "key": "account_id", "owner": "customer_id",
               "exposure_file": "ews_retail_exposure.parquet",
               "owner_file": "ews_retail_owner.parquet",
               "src_exposure": "retail_account_month",
               "src_owner": "retail_customer_month",
               "segment": "product", "sub_segment": "sub_product",
               "latest": "2026-08"},
}


def register(c, domain: str) -> dict:
    s = SPEC[domain]
    out = OUT / s["release"]
    c.execute(f"CREATE OR REPLACE VIEW e AS SELECT * FROM read_parquet('{out/s['exposure_file']}')")
    c.execute(f"CREATE OR REPLACE VIEW o AS SELECT * FROM read_parquet('{out/s['owner_file']}')")
    c.execute(f"CREATE OR REPLACE VIEW se AS SELECT * FROM {s['src_exposure']}")
    c.execute(f"CREATE OR REPLACE VIEW so AS SELECT * FROM {s['src_owner']}")
    return s


def base_fields(c, domain: str) -> list[str]:
    """Columns the EWS exposure row shares with the frozen source table."""
    s = SPEC[domain]
    src = {r[0] for r in c.execute(f"SELECT column_name FROM (DESCRIBE se)").fetchall()}
    new = {r[0] for r in c.execute(f"SELECT column_name FROM (DESCRIBE e)").fetchall()}
    return sorted(src & new)


def id_alignment(c, domain: str) -> dict:
    s = register(c, domain)
    p, k, ow = s["period"], s["key"], s["owner"]
    rep: dict = {"domain": domain, "ews_release_id": s["release"],
                 "source_release_id": s["src"]}
    # masters and periods
    for label, new_rel, src_rel, cols in (
            ("exposure_period_keys", "e", "se", [k, p]),
            ("owner_period_keys", "o", "so", [ow, p])):
        sel = ", ".join(cols)
        n_new = one(c, f"SELECT COUNT(*) FROM (SELECT DISTINCT {sel} FROM {new_rel})")
        n_src = one(c, f"SELECT COUNT(*) FROM (SELECT DISTINCT {sel} FROM {src_rel})")
        missing = one(c, f"SELECT COUNT(*) FROM (SELECT {sel} FROM {src_rel} EXCEPT SELECT {sel} FROM {new_rel})")
        extra = one(c, f"SELECT COUNT(*) FROM (SELECT {sel} FROM {new_rel} EXCEPT SELECT {sel} FROM {src_rel})")
        rep[label] = {"frozen": n_src, "ews": n_new, "missing_from_ews": missing,
                      "not_in_frozen": extra}
        check(f"{label}: EWS key set equals frozen key set", domain,
              {"missing": 0, "extra": 0}, {"missing": missing, "extra": extra})
    # distinct master ids
    for label, rel, col in (("distinct_exposure_ids", "e", k),
                            ("distinct_exposure_ids_src", "se", k),
                            ("distinct_owner_ids", "o", ow),
                            ("distinct_owner_ids_src", "so", ow)):
        rep[label] = one(c, f"SELECT COUNT(DISTINCT {col}) FROM {rel}")
    check("distinct exposure ids match frozen", domain,
          rep["distinct_exposure_ids_src"], rep["distinct_exposure_ids"])
    check("distinct owner ids match frozen", domain,
          rep["distinct_owner_ids_src"], rep["distinct_owner_ids"])
    # duplicates
    dup_e = one(c, f"SELECT COUNT(*) FROM (SELECT {k}, {p} FROM e GROUP BY 1,2 HAVING COUNT(*) > 1)")
    dup_o = one(c, f"SELECT COUNT(*) FROM (SELECT {ow}, {p} FROM o GROUP BY 1,2 HAVING COUNT(*) > 1)")
    rep["duplicate_exposure_keys"] = dup_e
    rep["duplicate_owner_keys"] = dup_o
    check("no duplicate exposure key x period", domain, 0, dup_e)
    check("no duplicate owner key x period", domain, 0, dup_o)
    # orphans: every exposure's owner exists in the owner master for that period
    orphan = one(c, f"SELECT COUNT(*) FROM e LEFT JOIN o ON o.{ow} = e.{ow} AND o.{p} = e.{p} WHERE o.{ow} IS NULL")
    rep["orphan_exposures_without_owner_row"] = orphan
    orphan_src = one(c, f"SELECT COUNT(*) FROM se LEFT JOIN so ON so.{ow} = se.{ow} AND so.{p} = se.{p} WHERE so.{ow} IS NULL")
    rep["orphan_exposures_in_frozen_source"] = orphan_src
    check("orphan exposures equal frozen source behaviour", domain, orphan_src, orphan)
    # relationship: owner -> exposure mapping identical to frozen
    rel_diff = one(c, f"SELECT COUNT(*) FROM ((SELECT DISTINCT {ow}, {k}, {p} FROM se) EXCEPT (SELECT DISTINCT {ow}, {k}, {p} FROM e))")
    rel_diff2 = one(c, f"SELECT COUNT(*) FROM ((SELECT DISTINCT {ow}, {k}, {p} FROM e) EXCEPT (SELECT DISTINCT {ow}, {k}, {p} FROM se))")
    rep["owner_to_exposure_relationship_diff"] = {"frozen_not_in_ews": rel_diff,
                                                  "ews_not_in_frozen": rel_diff2}
    check("owner->exposure->period relationships identical", domain,
          {"a": 0, "b": 0}, {"a": rel_diff, "b": rel_diff2})
    # calendar
    per_new = [r[0] for r in c.execute(f"SELECT DISTINCT {p} FROM e ORDER BY 1").fetchall()]
    per_src = [r[0] for r in c.execute(f"SELECT DISTINCT {p} FROM se ORDER BY 1").fetchall()]
    rep["periods_ews"] = per_new
    rep["periods_frozen"] = per_src
    rep["latest_period"] = per_new[-1]
    check("period calendar identical to frozen", domain, per_src, per_new)
    check("period count is 20", domain, 20, len(per_new))
    check("latest period as user stated", domain, s["latest"], per_new[-1])
    # units / currency carried unchanged
    rep["reporting_currency"] = sorted({r[0] for r in c.execute("SELECT DISTINCT reporting_currency FROM e").fetchall()})
    rep["reporting_currency_frozen"] = sorted({r[0] for r in c.execute("SELECT DISTINCT reporting_currency FROM se").fetchall()})
    check("reporting currency unchanged", domain, rep["reporting_currency_frozen"],
          rep["reporting_currency"])
    return rep


def base_field_parity(c, domain: str) -> dict:
    """Value-for-value equality of every shared base field, nulls included."""
    s = register(c, domain)
    p, k = s["period"], s["key"]
    cols = base_fields(c, domain)
    rows = []
    for col in cols:
        # NULL-safe mismatch count on the exposure key, in both directions.
        mism = one(c, f"""SELECT COUNT(*) FROM e JOIN se
            ON se.{k} = e.{k} AND se.{p} = e.{p}
            WHERE e."{col}" IS DISTINCT FROM se."{col}" """)
        nulls_new = one(c, f'SELECT COUNT(*) FROM e WHERE "{col}" IS NULL')
        nulls_src = one(c, f'SELECT COUNT(*) FROM se WHERE "{col}" IS NULL')
        t_new = one(c, f"SELECT column_type FROM (DESCRIBE e) WHERE column_name = '{col}'")
        t_src = one(c, f"SELECT column_type FROM (DESCRIBE se) WHERE column_name = '{col}'")
        rows.append({"column": col, "mismatches": mism, "nulls_ews": nulls_new,
                     "nulls_frozen": nulls_src, "type_ews": t_new,
                     "type_frozen": t_src,
                     "type_identical": t_new == t_src})
        check(f"base field value equality: {col}", domain, 0, mism)
        check(f"null count identical: {col}", domain, nulls_src, nulls_new)
        check(f"type identical: {col}", domain, t_src, t_new)
    # money totals per period must reconcile exactly (no multiplied balances)
    totals = []
    for col in ("ead_sar_mn", "ecl_sar_mn", "balance_sar_mn", "drawn_sar_mn",
                "limit_sar_mn"):
        if col not in cols:
            continue
        diff = c.execute(f"""SELECT COUNT(*) FROM (
            SELECT e.{p} AS period, SUM(e."{col}") AS a, b AS b FROM e
            JOIN (SELECT {p} AS period, SUM("{col}") AS b FROM se GROUP BY 1) t
              ON t.period = e.{p} GROUP BY e.{p}, b
            HAVING abs(a - b) > 1e-6)""").fetchone()[0]
        totals.append({"column": col, "periods_not_reconciling": diff})
        check(f"period totals reconcile: {col}", domain, 0, diff)
    return {"domain": domain, "shared_base_fields": len(cols),
            "fields": rows, "money_totals": totals,
            "owner_aggregates_not_copied_to_exposure": [
                col for col in ("total_ead_sar_mn", "total_ecl_sar_mn",
                                "revenue_sar_mn", "ebitda_sar_mn",
                                "total_debt_sar_mn")
                if col not in {r[0] for r in c.execute("SELECT column_name FROM (DESCRIBE e)").fetchall()}]}


def ews_tests(c, domain: str) -> dict:
    """The EWS columns line up with the actual rule definitions."""
    s = register(c, domain)
    p = s["period"]
    have = {r[0] for r in c.execute("SELECT column_name FROM (DESCRIBE e)").fetchall()}
    live = [r for r in ews.RULES[domain] if ews._columns(r["sql"]) <= have]
    not_live = [r for r in ews.RULES[domain] if not ews._columns(r["sql"]) <= have]
    rep = {"domain": domain, "ruleset_version": ews.RULESET_VERSION,
           "live_rules": [r["id"] for r in live],
           "not_live_rules": [{"id": r["id"],
                               "missing_columns": sorted(ews._columns(r["sql"]) - have)}
                              for r in not_live],
           "per_rule": []}
    # recompute each rule independently and compare to its weight contribution
    score_expr = " + ".join(
        f"(CASE WHEN {r['sql']} THEN {r['weight']} ELSE 0 END)" for r in live) or "0"
    bad = one(c, f"SELECT COUNT(*) FROM e WHERE ews_score IS DISTINCT FROM ({score_expr})")
    check("ews_score equals the independent sum of live rule weights", domain, 0, bad)
    bands = " ".join(f"WHEN ews_score >= {f} THEN '{n}'" for f, n in ews.bands(domain))
    bad_band = one(c, f"SELECT COUNT(*) FROM e WHERE ews_band IS DISTINCT FROM (CASE {bands} ELSE 'none' END)")
    check("ews_band equals the banded score (the book's band floors)", domain, 0, bad_band)
    for r in live:
        trips = one(c, f"SELECT COUNT(*) FROM e WHERE {r['sql']}")
        named = one(c, f"SELECT COUNT(*) FROM e WHERE ews_reasons LIKE '%{r['label']}%'")
        rep["per_rule"].append({"id": r["id"], "label": r["label"],
                                "sql": r["sql"], "weight": r["weight"],
                                "exposures_tripping_all_periods": trips,
                                "rows_naming_it_in_ews_reasons": named})
        check(f"reason label present exactly where {r['id']} is true", domain,
              trips, named)
    for r in not_live:
        absent = one(c, f"SELECT COUNT(*) FROM e WHERE ews_reasons LIKE '%{r['label']}%'")
        check(f"{r['id']} is not scored and never named", domain, 0, absent)
    # series reconcile against the exposure table, every period present
    for name, dims in (("ews_series_portfolio.parquet", []),
                       ("ews_series_segment.parquet", [s["segment"]]),
                       ("ews_series_subsegment.parquet", [s["segment"], s["sub_segment"]])):
        path = OUT / s["release"] / name
        c.execute(f"CREATE OR REPLACE VIEW sr AS SELECT * FROM read_parquet('{path}')")
        gb = ", ".join([p, *dims, "ews_band"])
        diff = one(c, f"""SELECT COUNT(*) FROM (
            SELECT {gb}, COUNT(*) AS n, SUM(ead_sar_mn) AS ead FROM e GROUP BY ALL) a
            FULL JOIN (SELECT {gb}, n, ead_sar_mn AS ead FROM sr) b
            USING ({gb}) WHERE a.n IS DISTINCT FROM b.n OR abs(coalesce(a.ead,0) - coalesce(b.ead,0)) > 1e-6""")
        check(f"{name} reconciles to the exposure table", domain, 0, diff)
        nper = one(c, f"SELECT COUNT(DISTINCT {p}) FROM sr")
        check(f"{name} carries all 20 periods", domain, 20, nper)
        zero = one(c, "SELECT COUNT(*) FROM sr WHERE n = 0")
        check(f"{name} has no synthetic zero rows", domain, 0, zero)
    # reason series reconciles to the exposure reasons
    rpath = OUT / s["release"] / "ews_reason_period.parquet"
    c.execute(f"CREATE OR REPLACE VIEW rr AS SELECT * FROM read_parquet('{rpath}')")
    diff = one(c, f"""SELECT COUNT(*) FROM (
        SELECT {p}, trim(reason) AS reason, COUNT(*) AS n FROM (
          SELECT {p}, unnest(string_split(ews_reasons, '; ')) AS reason FROM e
          WHERE ews_reasons <> '') WHERE trim(reason) <> '' GROUP BY 1,2) a
        FULL JOIN rr b USING ({p}, reason) WHERE a.n IS DISTINCT FROM b.n""")
    check("ews_reason_period reconciles to the exposure reasons", domain, 0, diff)
    rep["periods_in_reason_series"] = one(c, f"SELECT COUNT(DISTINCT {p}) FROM rr")
    check("reason series carries all 20 periods", domain, 20,
          rep["periods_in_reason_series"])
    rep["band_counts_latest"] = c.execute(
        f"SELECT ews_band, COUNT(*), round(SUM(ead_sar_mn), 3) FROM e "
        f"WHERE {p} = '{s['latest']}' GROUP BY 1 ORDER BY 1").fetchall()
    rep["severe_ead_by_period"] = c.execute(
        f"SELECT {p}, round(SUM(CASE WHEN ews_band IN ('high','critical') "
        f"THEN ead_sar_mn ELSE 0 END), 3) FROM e GROUP BY 1 ORDER BY 1").fetchall()
    check("severe EAD history has 20 non-synthetic points", domain, 20,
          len([x for x in rep["severe_ead_by_period"] if x[1] is not None]))
    return rep


def main() -> int:
    now = dt.datetime.now(dt.UTC).isoformat()
    c = conn()
    ida, parity, ewsrep = {}, {}, {}
    for domain in ("corporate", "retail"):
        ida[domain] = id_alignment(c, domain)
        parity[domain] = base_field_parity(c, domain)
        ewsrep[domain] = ews_tests(c, domain)
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    (EV / "ID_ALIGNMENT.json").write_text(json.dumps(
        {"document": "ID_ALIGNMENT", "written_utc": now,
         "frozen_source": str(FROZEN), "domains": ida}, indent=1, default=str))
    (EV / "BASE_FIELD_PARITY.json").write_text(json.dumps(
        {"document": "BASE_FIELD_PARITY", "written_utc": now,
         "method": ("every column shared between the new EWS exposure table and "
                    "the frozen source exposure table, compared value for value "
                    "on the canonical key x period with IS DISTINCT FROM so that "
                    "NULL == NULL and NULL != value; plus parquet type equality, "
                    "null counts and per-period money totals"),
         "units": "unconverted frozen units: SAR million for *_sar_mn, percent "
                  "for *_pct, days for dpd_days",
         "domains": parity}, indent=1, default=str))
    (EV / "DATA_TESTS.json").write_text(json.dumps(
        {"document": "DATA_TESTS", "written_utc": now,
         "runner": "backend/ews_domain/run_data_tests.py",
         "paid_inference_calls": 0, "model_calls": 0,
         "total": len(RESULTS),
         "passed": len(RESULTS) - len(failed), "failed": len(failed),
         "exit_code": 1 if failed else 0,
         "ews_signal_audit": ewsrep,
         "failures": failed, "results": RESULTS}, indent=1, default=str))
    print(f"tests={len(RESULTS)} passed={len(RESULTS)-len(failed)} failed={len(failed)}")
    for r in failed[:20]:
        print("FAIL", r["domain"], r["test"], r["expected"], "!=", r["observed"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
