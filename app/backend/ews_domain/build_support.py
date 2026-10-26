"""Audit every base field the frozen books publish, and copy the support
relations the Phase A packages did not carry into their OWN support datasets.

Phase A copied the two exposure tables and the two owner masters. The frozen
books also publish corporate collateral and covenant detail and retail
behaviour and collateral detail, each at its OWN grain. Those relations are
copied here field for field, at their own grain, into separate files: nothing
is aggregated down onto an exposure row, so no money column is flattened.

The frozen lake is opened READ ONLY. No value is changed, imputed or derived.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.ews_domain.paths import (CORP_SRC, DATASETS as OUT, EVIDENCE as EV,  # noqa: E402
                                      EWS_CORP, EWS_RET, RET_SRC,
                                      SOURCE_LAKE as FROZEN)

SUPPORT = [
    (EWS_CORP, CORP_SRC, "corp_collateral_quarter", "ews_corp_collateral.parquet",
     ["facility_id", "reporting_quarter"], "corporate"),
    (EWS_CORP, CORP_SRC, "corp_covenant_quarter", "ews_corp_covenant.parquet",
     ["facility_id", "reporting_quarter"], "corporate"),
    (EWS_RET, RET_SRC, "retail_behaviour_month", "ews_retail_behaviour.parquet",
     ["account_id", "reporting_month"], "retail"),
    (EWS_RET, RET_SRC, "retail_collateral_month", "ews_retail_collateral.parquet",
     ["account_id", "reporting_month"], "retail"),
]


def sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cols(c: duckdb.DuckDBPyConnection, sql: str) -> dict[str, str]:
    d = c.execute(f"SELECT * FROM ({sql}) LIMIT 0").description
    return {r[0]: str(r[1]) for r in d}


def main() -> int:
    c = duckdb.connect()
    frozen_tables = {}
    for ds in (CORP_SRC, RET_SRC):
        for p in sorted((FROZEN / ds).glob("*.parquet")):
            frozen_tables[p.stem] = f"SELECT * FROM read_parquet('{p}')"
    ews_files = {}
    for rel in (EWS_CORP, EWS_RET):
        for p in sorted((OUT / rel).glob("*.parquet")):
            ews_files[f"{rel}/{p.name}"] = f"SELECT * FROM read_parquet('{p}')"

    audit = {
        "document": "BASE_FIELD_AUDIT",
        "scope": "every column of every frozen source table, against the columns the EWS packages carry",
        "frozen_source_opened_read_only": str(FROZEN),
        "frozen_tables": {},
        "ews_package_files_before_support": {k: sorted(cols(c, v)) for k, v in ews_files.items()},
    }
    carried = {n for v in ews_files.values() for n in cols(c, v)}
    for t, sql in frozen_tables.items():
        tc = cols(c, sql)
        audit["frozen_tables"][t] = {
            "columns": tc,
            "column_count": len(tc),
            "rows": c.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()[0],
            "carried_by_phase_a": sorted(n for n in tc if n in carried),
            "not_carried_by_phase_a": sorted(n for n in tc if n not in carried),
        }

    built = []
    for rel, src, table, out_name, key, domain in SUPPORT:
        sql = frozen_tables[table]
        dest = OUT / rel / out_name
        grain_cols = ", ".join(key)
        c.execute(
            f"COPY (SELECT t.*, '{rel}' AS ews_release_id, '{src}' AS source_release_id, "
            f"'{table}' AS source_table, '{' x '.join(key)}' AS ews_grain "
            f"FROM ({sql}) t) TO '{dest}' (FORMAT PARQUET)"
        )
        out_sql = f"SELECT * FROM read_parquet('{dest}')"
        rows = c.execute(f"SELECT COUNT(*) FROM ({out_sql})").fetchone()[0]
        src_rows = c.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()[0]
        src_cols = cols(c, sql)
        out_cols = cols(c, out_sql)
        # every original column, same name and same parquet type, same row count
        same_types = {n: (src_cols[n], out_cols.get(n)) for n in src_cols
                      if out_cols.get(n) != src_cols[n]}
        diff = c.execute(
            "SELECT COUNT(*) FROM ("
            f"SELECT {', '.join(src_cols)} FROM ({sql}) EXCEPT SELECT {', '.join(src_cols)} FROM ({out_sql})"
            ")").fetchone()[0]
        dup = c.execute(
            f"SELECT COUNT(*) FROM (SELECT {grain_cols} FROM ({out_sql}) GROUP BY ALL HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        periods = [r[0] for r in c.execute(
            f"SELECT DISTINCT {key[1]} FROM ({out_sql}) ORDER BY 1").fetchall()]
        built.append({
            "release_id": rel, "domain_id": domain, "file": out_name,
            "source_table": table, "source_release_id": src,
            "grain": " x ".join(key),
            "rows": rows, "source_rows": src_rows, "rows_equal": rows == src_rows,
            "original_columns": sorted(src_cols),
            "original_column_count": len(src_cols),
            "added_provenance_columns": ["ews_release_id", "source_release_id", "source_table", "ews_grain"],
            "type_mismatches": same_types,
            "rows_in_source_not_in_copy": diff,
            "duplicate_grain_keys": dup,
            "periods": periods, "period_count": len(periods),
            "sha256": sha(dest), "bytes": dest.stat().st_size,
            "aggregated": False,
            "note": "field-for-field copy at the source grain; no aggregate, no join onto an exposure row",
        })
    audit["support_datasets_built"] = built
    audit["remaining_not_carried"] = {}
    carried2 = set(carried)
    for b in built:
        carried2 |= set(b["original_columns"])
    for t, info in audit["frozen_tables"].items():
        left = [n for n in info["columns"] if n not in carried2]
        if left:
            audit["remaining_not_carried"][t] = left
    (EV / "BASE_FIELD_AUDIT.json").write_text(json.dumps(audit, indent=1, default=str))
    print(json.dumps({
        "built": [(b["file"], b["rows"], b["original_column_count"], b["rows_equal"],
                   b["rows_in_source_not_in_copy"], b["duplicate_grain_keys"]) for b in built],
        "remaining_not_carried": audit["remaining_not_carried"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
