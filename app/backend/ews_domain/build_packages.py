"""Build the independent Corporate / Retail EWS packages from the frozen books.

The frozen Cockpit lake is opened READ ONLY. Base-field values are copied
unchanged; the only added columns are source provenance and the EWS columns
that `ews_rules` (the live rule set, gw-ews-1.1.0; 1.0.0 is recorded there)
computes on the published grid view. No value is imputed.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.ews_domain import ews_rules as ews  # noqa: E402

from backend.ext_domains.paths import BUREAU, EXTERNAL, OPEN_BANKING  # noqa: E402
from backend.ews_domain.paths import (CORP_SRC, DATASETS as OUT, EWS_CORP,  # noqa: E402
                                      EWS_RET, RET_SRC, SOURCE_LAKE as FROZEN)


#: The external domains (synthetic Bureau and Open Banking), keyed to the same
#: owners and periods (backend/ext_domains). Read-only; owner-grain inputs.
EXT = {"bureau_retail_month": BUREAU, "bureau_corp_quarter": BUREAU,
       "openbanking_retail_month": OPEN_BANKING, "openbanking_corp_quarter": OPEN_BANKING}


def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    for t, rel in EXT.items():
        c.execute(f"CREATE VIEW {t} AS SELECT * EXCLUDE (tenant_id, external_first_flag) "
                  f"FROM read_parquet('{EXTERNAL / rel / (t + '.parquet')}')")
    for ds, tables in ((CORP_SRC, ["corp_borrower_quarter", "corp_facility_quarter",
                                   "corp_collateral_quarter", "corp_covenant_quarter"]),
                       (RET_SRC, ["retail_account_month", "retail_customer_month",
                                  "retail_behaviour_month", "retail_collateral_month"])):
        for t in tables:
            c.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{FROZEN/ds/(t+'.parquet')}')")
    return c


def available(c: duckdb.DuckDBPyConnection, relation: str) -> set[str]:
    return {r[0] for r in c.execute(f"SELECT column_name FROM (DESCRIBE {relation})").fetchall()}


def write(c: duckdb.DuckDBPyConnection, relation: str, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c.execute(f"COPY ({relation}) TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------- corporate
# EXPOSURE GRAIN: one row per facility_id x reporting_quarter, exactly the
# grain `grid.py` scores. Borrower MONEY aggregates are NOT copied down here;
# only the two borrower RULE INPUTS the rule set reads (watchlist_flag, a
# flag, and rating_notches_moved, a count) travel on the facility row, so no
# balance is multiplied by the facility count.
CORP_EXPOSURE = f"""
SELECT f.* EXCLUDE (tenant_id, dataset_release_id),
       f.tenant_id, '{EWS_CORP}' AS ews_release_id,
       '{CORP_SRC}' AS source_release_id,
       f.dataset_release_id AS source_dataset_release_id,
       'corp_facility_quarter' AS source_table,
       'facility_quarter' AS ews_grain,
       b.watchlist_flag, b.rating_notches_moved,
       cov.covenant_breaches,
       c.collateral_value_sar_mn, c.collateral_ltv_pct,
       bur.external_exposure_sar_mn, bur.external_dpd_days, bur.external_default_flag, bur.enquiries_q,
       ob.operating_inflows_sar_mn, ob.inflow_trend_pct, ob.balance_buffer_months, ob.returned_payments_q
FROM corp_facility_quarter f
LEFT JOIN corp_borrower_quarter b
       ON b.borrower_id = f.borrower_id
      AND b.reporting_quarter = f.reporting_quarter
LEFT JOIN (SELECT facility_id, reporting_quarter,
                  SUM(breach_flag) AS covenant_breaches
           FROM corp_covenant_quarter GROUP BY 1, 2) cov
       ON cov.facility_id = f.facility_id
      AND cov.reporting_quarter = f.reporting_quarter
LEFT JOIN (SELECT facility_id, reporting_quarter,
                  SUM(allocated_value_sar_mn) AS collateral_value_sar_mn,
                  AVG(ltv_pct) AS collateral_ltv_pct
           FROM corp_collateral_quarter GROUP BY 1, 2) c
       ON c.facility_id = f.facility_id
      AND c.reporting_quarter = f.reporting_quarter
LEFT JOIN bureau_corp_quarter bur
       ON bur.borrower_id = f.borrower_id AND bur.reporting_quarter = f.reporting_quarter
LEFT JOIN openbanking_corp_quarter ob
       ON ob.borrower_id = f.borrower_id AND ob.reporting_quarter = f.reporting_quarter
"""

# OWNER GRAIN: the borrower master, every base field copied unchanged.
CORP_OWNER = f"""
SELECT b.*, '{EWS_CORP}' AS ews_release_id,
       '{CORP_SRC}' AS source_release_id,
       'corp_borrower_quarter' AS source_table,
       'borrower_quarter' AS ews_grain
FROM corp_borrower_quarter b
"""

# ------------------------------------------------------------------ retail
# EXPOSURE GRAIN: one row per account_id x reporting_month. The ACCOUNT is
# the canonical retail exposure key; no facility id is invented. Behaviour
# fields are already account grain. The customer-grain score fields the rule
# set reads travel as declared OWNER INPUTS; customer total_ead / total_ecl
# are NOT copied down, so no balance is multiplied by accounts_held.
RET_EXPOSURE = f"""
SELECT a.* EXCLUDE (tenant_id, dataset_release_id),
       a.tenant_id, '{EWS_RET}' AS ews_release_id,
       '{RET_SRC}' AS source_release_id,
       a.dataset_release_id AS source_dataset_release_id,
       'retail_account_month' AS source_table,
       'account_month' AS ews_grain,
       bh.payment_ratio_pct, bh.utilisation_change_pp, bh.missed_payments_12m,
       bh.delinquency_streak_months, bh.balance_growth_pct,
       bh.cash_advance_ratio_pct, bh.overlimit_flag, bh.inflow_change_pct,
       bh.bureau_inquiries_6m, bh.repayment_behaviour_score,
       pr.payment_ratio_change_3m,
       cm.score_migration, cm.score_band AS customer_score_band,
       cm.score_band_previous AS customer_score_band_previous,
       cm.behaviour_score_change, cm.worst_dpd_days AS customer_worst_dpd_days,
       cm.worst_stage AS customer_worst_stage, cm.tenure_months,
       cm.accounts_held,
       col.collateral_value_sar_mn, col.collateral_ltv_pct,
       bur.bureau_score, bur.external_dpd_days, bur.worst_external_status, bur.external_facilities,
       bur.external_balance_sar_mn, bur.external_leverage_x, bur.enquiries_3m, bur.new_external_default,
       ob.salaried_flag, ob.salary_credit_flag, ob.salary_interruption_flag, ob.total_inflows_sar_k,
       ob.inflow_trend_pct, ob.balance_buffer_months, ob.returned_payments_3m,
       ob.gambling_bnpl_spend_share_pct
FROM retail_account_month a
LEFT JOIN retail_behaviour_month bh
       ON bh.account_id = a.account_id
      AND bh.reporting_month = a.reporting_month
LEFT JOIN (SELECT account_id, reporting_month,
                  -- gw-ews-1.3.0: the change in the payment ratio over 3 months, in points
                  -- (EWS_STORY.md section 1.3: a level threshold sat on a book-wide drift).
                  payment_ratio_pct - LAG(payment_ratio_pct, 3) OVER (
                      PARTITION BY account_id ORDER BY reporting_month) AS payment_ratio_change_3m
           FROM retail_behaviour_month) pr
       ON pr.account_id = a.account_id
      AND pr.reporting_month = a.reporting_month
LEFT JOIN retail_customer_month cm
       ON cm.customer_id = a.customer_id
      AND cm.reporting_month = a.reporting_month
LEFT JOIN (SELECT account_id, reporting_month,
                  SUM(collateral_value_sar_mn) AS collateral_value_sar_mn,
                  AVG(ltv_pct) AS collateral_ltv_pct
           FROM retail_collateral_month GROUP BY 1, 2) col
       ON col.account_id = a.account_id
      AND col.reporting_month = a.reporting_month
LEFT JOIN bureau_retail_month bur
       ON bur.customer_id = a.customer_id AND bur.reporting_month = a.reporting_month
LEFT JOIN openbanking_retail_month ob
       ON ob.customer_id = a.customer_id AND ob.reporting_month = a.reporting_month
"""

RET_OWNER = f"""
SELECT cm.*, '{EWS_RET}' AS ews_release_id,
       '{RET_SRC}' AS source_release_id,
       'retail_customer_month' AS source_table,
       'customer_month' AS ews_grain
FROM retail_customer_month cm
"""


def scored(c, base_sql: str, domain_id: str) -> tuple[str, dict]:
    """`base_sql` with the live rule set's columns appended, as grid.py does."""
    c.execute(f"CREATE OR REPLACE VIEW _base AS {base_sql}")
    have = available(c, "_base")
    score, reasons = ews.score_sql(domain_id, have)
    live, dropped = [], []
    for rule in ews.RULES[domain_id]:
        needed = ews._columns(rule["sql"])
        (live if needed <= have else dropped).append(
            {"id": rule["id"], "label": rule["label"], "weight": rule["weight"],
             "sql": rule["sql"], "requires": sorted(needed),
             "missing": sorted(needed - have)})
    band = ews.band_sql("g1.ews_score", domain_id)
    sql = (f"SELECT g1.*, {band} AS ews_band FROM ("
           f"SELECT g0.*, ({score}) AS ews_score, {reasons} AS ews_reasons, "
           f"'{ews.RULESET_VERSION}' AS ews_ruleset_version "
           f"FROM _base g0) g1")
    return sql, {"live": [r for r in live if not r["missing"]],
                 "not_live": [r for r in dropped],
                 "score_expr": score, "band_expr": ews.band_sql("ews_score", domain_id),
                 "band_floors": list(ews.BAND_FLOORS[domain_id])}


SERIES = {
    "corporate": {"period": "reporting_quarter", "segment": "sector",
                  "sub_segment": "sub_sector", "key": "facility_id",
                  "owner": "borrower_id"},
    "retail": {"period": "reporting_month", "segment": "product",
               "sub_segment": "sub_product", "key": "account_id",
               "owner": "customer_id"},
}


def series_sql(domain_id: str, dims: list[str]) -> str:
    s = SERIES[domain_id]
    cols = ", ".join([s["period"], *dims, "ews_band"])
    return (f"SELECT {cols}, COUNT(*) AS n, "
            f"COUNT(DISTINCT {s['owner']}) AS owners, "
            f"SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn, "
            f"SUM(CASE WHEN ews_band IN ('high', 'critical') "
            f"THEN ead_sar_mn ELSE 0 END) AS severe_ead_sar_mn "
            f"FROM _exposure GROUP BY ALL ORDER BY ALL")


def reasons_sql(domain_id: str) -> str:
    s = SERIES[domain_id]
    return (f"SELECT {s['period']}, trim(reason) AS reason, COUNT(*) AS n, "
            f"SUM(ead_sar_mn) AS ead_sar_mn FROM ("
            f"SELECT {s['period']}, ead_sar_mn, "
            f"unnest(string_split(ews_reasons, '; ')) AS reason "
            f"FROM _exposure WHERE ews_reasons <> '') "
            f"WHERE trim(reason) <> '' GROUP BY 1, 2 ORDER BY 1, 3 DESC")


def build(c, domain_id: str, release: str, exposure_sql: str,
          owner_sql: str) -> dict:
    s = SERIES[domain_id]
    out = OUT / release
    scored_sql, rule_status = scored(c, exposure_sql, domain_id)
    c.execute(f"CREATE OR REPLACE VIEW _exposure AS {scored_sql}")
    files: dict[str, dict] = {}
    plan = [
        # ORDER BY: the same book always writes the same bytes.
        (f"ews_{'corp' if domain_id == 'corporate' else 'retail'}_exposure.parquet",
         f"SELECT * FROM _exposure ORDER BY {s['period']}, {s['key']}",
         s["key"] + " x " + s["period"]),
        (f"ews_{'corp' if domain_id == 'corporate' else 'retail'}_owner.parquet",
         f"SELECT * FROM ({owner_sql}) ORDER BY {s['period']}, {s['owner']}",
         s["owner"] + " x " + s["period"]),
        ("ews_series_portfolio.parquet", series_sql(domain_id, []), s["period"] + " x ews_band"),
        ("ews_series_segment.parquet", series_sql(domain_id, [s["segment"]]),
         s["period"] + " x " + s["segment"] + " x ews_band"),
        ("ews_series_subsegment.parquet",
         series_sql(domain_id, [s["segment"], s["sub_segment"]]),
         s["period"] + " x " + s["segment"] + " x " + s["sub_segment"] + " x ews_band"),
        ("ews_reason_period.parquet", reasons_sql(domain_id),
         s["period"] + " x reason"),
    ]
    for name, sql, grain in plan:
        path = out / name
        write(c, sql, path)
        rows = c.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
        files[name] = {"rows": int(rows), "grain": grain,
                       "sha256": sha256(path), "bytes": path.stat().st_size,
                       "sql": " ".join(sql.split())}
    periods = [r[0] for r in c.execute(
        f"SELECT DISTINCT {s['period']} FROM _exposure ORDER BY 1").fetchall()]
    return {"release_id": release, "domain_id": domain_id,
            "source_release_id": CORP_SRC if domain_id == "corporate" else RET_SRC,
            "files": files, "periods": periods,
            "latest_period": periods[-1], "period_count": len(periods),
            "rule_status": rule_status}


def main() -> None:
    c = conn()
    manifest = {
        "document": "EWS_PACKAGE_MANIFEST",
        "built_utc": __import__("datetime").datetime.now(
            __import__("datetime").UTC).isoformat(),
        "builder": "backend/ews_domain/build_packages.py",
        "ruleset": ews.RULESET_VERSION,
        "ruleset_file_sha256": sha256(
            pathlib.Path(__file__).with_name("ews_rules.py")),
        "units": "SAR million (sar_mn suffix), percent (pct), days, counts - "
                 "exactly the frozen source units, unconverted",
        "currency": "SAR",
        "frozen_source_opened_read_only": str(FROZEN),
        "packages": {},
    }
    manifest["packages"]["corporate"] = build(
        c, "corporate", EWS_CORP, CORP_EXPOSURE, CORP_OWNER)
    manifest["packages"]["retail"] = build(
        c, "retail", EWS_RET, RET_EXPOSURE, RET_OWNER)
    path = OUT / "EWS_PACKAGE_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=1))
    print(json.dumps({d: {"files": {k: v["rows"] for k, v in p["files"].items()},
                          "periods": p["period_count"],
                          "latest": p["latest_period"],
                          "live_rules": [r["id"] for r in p["rule_status"]["live"]],
                          "not_live": [r["id"] for r in p["rule_status"]["not_live"]]}
                      for d, p in manifest["packages"].items()}, indent=1))


if __name__ == "__main__":
    main()
