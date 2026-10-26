"""Publish the CBUAE CRM breach checks as the `regulatory` data domain (PLAN_R7 C3).

    .venv/bin/python ops/build_crm_breaches.py          # writes data/regulatory/cbuae-crm-v1/

Two relations, computed by `backend.regulatory.crm_checks` on the books' latest periods:
  crm_breach  one row per breach (article, check, entity, measured vs required, EAD/ECL, severity)
  crm_check   one row per check and book (tested, breaches, status, EAD/ECL, shortfall)
plus a manifest with the column dictionary. Deterministic: the same books give the same files. The sync test
(tests/v5/test_sync_regulatory.py) recomputes the engine and compares.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.regulatory import crm_checks  # noqa: E402

OUT = ROOT / "data" / "regulatory" / "cbuae-crm-v1"

DICTIONARY = {
    "breach_id": "The breach's id: check, entity and a sequence number when one entity breaches a check more than once.",
    "check_id": "The check's id (CRM-<article paragraph>), e.g. CRM-9.23.",
    "article": "The paragraph of the CBUAE Credit Risk Management Standards the check tests, e.g. CBUAE CRM Art. 9.23.",
    "title": "The check in a few words.",
    "rule": "The rule of the Standards the check tests, in one sentence.",
    "book": "The book checked: corporate (quarterly) or retail (monthly).",
    "period": "The book's period checked: a quarter (corporate, 2026Q2) or a month (retail, 2026-08).",
    "entity_type": "What breaches: a facility (corporate), an account (retail) or the book (a book-level rule).",
    "entity_id": "The facility (CF…), account (RA…) or book id that breaches.",
    "owner_id": "The borrower (CB…) or customer (RC…) behind the entity; the book id for a book-level rule.",
    "measured": "The value measured on the books (as text: a stage, a number of days or months, a percentage, an amount).",
    "required": "The value the Standards require (as text, in the same unit as measured).",
    "unit": "The unit of measured and required.",
    "ead_sar_mn": {"description": "Exposure at default of the breaching entity (for a book rule, of the book's Stage 3).",
                   "unit": "SAR million"},
    "ecl_sar_mn": {"description": "Expected credit loss held on the breaching entity.", "unit": "SAR million"},
    "shortfall_sar_mn": {"description": "Provision shortfall against the Standards' floor (0 for a non-provision check).",
                         "unit": "SAR million"},
    "severity": "high, medium or low.",
    "detail": "What the check found, in one line.",
    "level": "The level the check works at: facility, account or book.",
    "tested": "How many entities of the book the check tested (1 for a book-level rule).",
    "breaches": "How many entities breach the check.",
    "status": "breach or compliant.",
}


def frames(res: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    res = res or crm_checks.run()
    b = pd.DataFrame(res["breaches"]).rename(columns={"borrower_id": "owner_id"})
    b["measured"] = b["measured"].astype(str)
    b["required"] = b["required"].astype(str)
    seq = b.groupby(["check_id", "entity_id"]).cumcount() + 1
    b.insert(0, "breach_id", b["check_id"] + ":" + b["entity_id"] + ":" + seq.astype(str))
    b = b[["breach_id", "check_id", "article", "title", "book", "period", "entity_type", "entity_id", "owner_id",
           "measured", "required", "unit", "ead_sar_mn", "ecl_sar_mn", "shortfall_sar_mn", "severity", "detail"]]
    c = pd.DataFrame(res["checks"])[["check_id", "article", "title", "rule", "book", "period", "level", "severity",
                                     "tested", "breaches", "status", "ead_sar_mn", "ecl_sar_mn", "shortfall_sar_mn"]]
    return b.reset_index(drop=True), c.reset_index(drop=True)


def main() -> int:
    res = crm_checks.run()
    b, c = frames(res)
    OUT.mkdir(parents=True, exist_ok=True)
    b.to_parquet(OUT / "crm_breach.parquet", index=False)
    c.to_parquet(OUT / "crm_check.parquet", index=False)
    manifest = {
        "release_id": "cbuae-crm-v1", "domain_label": "Regulatory", "origin": "SYNTHETIC_DEMO", "not_client_data": True,
        "builder": "ops/build_crm_breaches.py (backend.regulatory.crm_checks)",
        "document": "CBUAE Credit Risk Management Standards", "periods": res["periods"],
        "keyed_to": {"corporate": "facility_id / borrower_id of the corporate book",
                     "retail": "account_id / customer_id of the retail book"},
        "dictionary": DICTIONARY,
        "relations": [{"relation": "crm_breach", "rows": len(b)}, {"relation": "crm_check", "rows": len(c)}],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"{len(b)} breaches, {len(c)} checks -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
