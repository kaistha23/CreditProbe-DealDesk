"""FIELD_MAPPING + EWS field catalogue + the explicit gap report."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend.ews_domain.build_packages import (CORP_SRC, EWS_CORP, EWS_RET,  # noqa: E402
                                               OUT, RET_SRC, conn)
from backend.ews_domain import ews_rules as ews  # noqa: E402
from backend.ews_domain.paths import EVIDENCE  # noqa: E402

SRC_TABLES = {
    "corporate": ["corp_facility_quarter", "corp_borrower_quarter",
                  "corp_collateral_quarter", "corp_covenant_quarter"],
    "retail": ["retail_account_month", "retail_customer_month",
               "retail_behaviour_month", "retail_collateral_month"],
}
DERIVED = {
    "covenant_breaches": "SUM(breach_flag) over corp_covenant_quarter per facility_id x reporting_quarter - the same aggregate grid.py joins as alias cov",
    "collateral_value_sar_mn": "SUM of the frozen collateral allocated/collateral value per exposure x period - the same aggregate grid.py joins",
    "collateral_ltv_pct": "AVG(ltv_pct) of the frozen collateral rows per exposure x period - the same aggregate grid.py joins",
    "ews_score": "sum of the live gw-ews-1.0.0 rule weights, unchanged",
    "ews_reasons": "concat_ws('; ') of the labels of the live rules that are true, unchanged",
    "ews_band": "ews.bands(book) applied to ews_score",
    "ews_ruleset_version": "literal gw-ews-1.0.0",
}
PROVENANCE = {"ews_release_id", "source_release_id", "source_dataset_release_id",
              "source_table", "ews_grain"}
RENAMED = {
    "customer_score_band": "retail_customer_month.score_band (owner grain; the account's own score_band is kept unrenamed)",
    "customer_worst_dpd_days": "retail_customer_month.worst_dpd_days",
    "customer_worst_stage": "retail_customer_month.worst_stage",
}


def main() -> None:
    c = conn()
    now = dt.datetime.now(dt.UTC).isoformat()
    src_cols: dict[str, dict[str, list[str]]] = {}
    for domain, tables in SRC_TABLES.items():
        src_cols[domain] = {}
        for t in tables:
            for col, _ in c.execute(f"SELECT column_name, column_type FROM (DESCRIBE {t})").fetchall():
                src_cols[domain].setdefault(col, []).append(t)
    mapping: dict = {"document": "FIELD_MAPPING", "written_utc": now, "domains": {}}
    for domain, release, src in (("corporate", EWS_CORP, CORP_SRC),
                                 ("retail", EWS_RET, RET_SRC)):
        prefix = "corp" if domain == "corporate" else "retail"
        out: dict[str, dict] = {}
        for fname in (f"ews_{prefix}_exposure.parquet", f"ews_{prefix}_owner.parquet"):
            path = OUT / release / fname
            cols = c.execute(
                f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet('{path}'))").fetchall()
            table: dict[str, dict] = {}
            for col, typ in cols:
                if col in PROVENANCE:
                    kind, origin = "provenance", "added by this package"
                elif col in DERIVED:
                    kind, origin = "derived", DERIVED[col]
                elif col in RENAMED:
                    kind, origin = "copied_renamed", RENAMED[col]
                elif col in src_cols[domain]:
                    kind, origin = "copied_unchanged", " | ".join(src_cols[domain][col])
                else:
                    kind, origin = "UNCLASSIFIED", ""
                table[col] = {"type": typ, "kind": kind, "source": origin}
            out[fname] = table
        mapping["domains"][domain] = {"ews_release_id": release,
                                      "source_release_id": src, "tables": out}
    (EVIDENCE / "FIELD_MAPPING.json").write_text(json.dumps(mapping, indent=1))

    # ----------------------------------------------------- EWS field catalogue
    cat: dict = {"document": "EWS_FIELD_CATALOGUE", "written_utc": now,
                 "ruleset_version": ews.RULESET_VERSION,
                 "bands": {d: [{"score_at_least": f, "band": n} for f, n in ews.bands(d)] for d in ews.BAND_FLOORS},
                 "bands_else": "none", "domains": {}}
    for domain, release in (("corporate", EWS_CORP), ("retail", EWS_RET)):
        prefix = "corp" if domain == "corporate" else "retail"
        path = OUT / release / f"ews_{prefix}_exposure.parquet"
        have = {r[0] for r in c.execute(
            f"SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet('{path}'))").fetchall()}
        rules = []
        for r in ews.RULES[domain]:
            needed = sorted(ews._columns(r["sql"]))
            missing = [n for n in needed if n not in have]
            rules.append({"id": r["id"], "label": r["label"], "sql": r["sql"],
                          "weight": r["weight"], "requires": needed,
                          "missing_on_this_release": missing,
                          "status": "LIVE" if not missing else "DECLARED_NOT_LIVE",
                          "limitation": r.get("limitation", "")})
        cat["domains"][domain] = {
            "ews_release_id": release,
            "ews_columns": ["ews_score", "ews_reasons", "ews_band",
                            "ews_ruleset_version"],
            "rules": rules,
            "live_count": sum(1 for r in rules if r["status"] == "LIVE"),
            "declared_not_live": [r["id"] for r in rules if r["status"] != "LIVE"]}
    (EVIDENCE / "EWS_FIELD_CATALOGUE.json").write_text(json.dumps(cat, indent=1))
    print(json.dumps({d: {"live": v["live_count"],
                          "not_live": v["declared_not_live"]}
                      for d, v in cat["domains"].items()}, indent=1))
    unclassified = [(d, t, col) for d, dv in mapping["domains"].items()
                    for t, tv in dv["tables"].items()
                    for col, cv in tv.items() if cv["kind"] == "UNCLASSIFIED"]
    print("unclassified columns:", unclassified)


if __name__ == "__main__":
    main()
