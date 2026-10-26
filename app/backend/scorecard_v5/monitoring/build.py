"""Publish the scorecard monitoring relations (R16 M8) to data/scorecard_v5/monitoring-saudi-v1.

    .venv/bin/python -m backend.scorecard_v5.monitoring.build            # write
    .venv/bin/python -m backend.scorecard_v5.monitoring.build --check    # recompute and compare, write nothing

Relations (registered in Data Domains, domain "scorecard_monitoring"):
  sc_monitor_metric          one row per scorecard x criterion x metric x period x segment (compute.py)
  sc_monitor_characteristic  one row per scorecard x characteristic x period: CSI, missing, outside-range, IV
  sc_model_inventory         one row per scorecard: tier, owners, intended use and scope, approval, last full validation
  sc_findings_register       the findings register seed: earlier validation and monitoring findings, owner, due date
  sc_monitor_schedule        one row per scorecard: monitoring frequency, last and next run, who the alert goes to

The inventory, the findings seed and the schedule are fictional demo records (names are fictional). Runtime changes
(new findings from a validation, status changes, the maker-checker conclusion) live in the service's own store and are
read on top of the seed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

import pandas as pd

from backend.scorecard_v5 import paths
from backend.scorecard_v5.domain import build as dbuild
from backend.scorecard_v5.monitoring import compute

RELEASE = "monitoring-saudi-v1"
OUT = paths.DOMAIN.parent / RELEASE
BUILD_VERSION = "1.0.0"

OWNERS = {
    "RET-APP": {"model_owner": "Faris Al-Harbi (Head of Retail Credit Risk)", "data_owner": "Huda Al-Sayegh (Retail Data Office)",
                "override_owner": "Khalid Bin Saeed (Retail Credit Policy)"},
    "RET-BEH": {"model_owner": "Faris Al-Harbi (Head of Retail Credit Risk)", "data_owner": "Huda Al-Sayegh (Retail Data Office)",
                "override_owner": "Khalid Bin Saeed (Retail Credit Policy)"},
    "SME-ANN": {"model_owner": "Nadia Al-Rashidi (Head of SME Credit Risk)", "data_owner": "Omar Haddad (Corporate Data Office)",
                "override_owner": "Yousef Al-Amri (SME Credit Policy)"},
}
VALIDATOR = "Lama Al-Mutairi (Model Validation)"
INVENTORY_EXTRA = {
    "RET-APP": {"tier": "Tier 1", "tier_reason": "Decides approve / decline and limits on every new retail account; material by exposure.",
                "intended_use": "Approve / decline and limit setting for new retail accounts in the products it was developed on.",
                "approved_on": "2025-06-15", "approved_by": "Model Oversight Committee, MOC-2025-07",
                "last_full_validation": "2025-06-10", "last_validation_ref": "MV-2025-014", "last_validation_conclusion": "fit"},
    "RET-BEH": {"tier": "Tier 1", "tier_reason": "Drives collections priority, limit management and the retail IFRS 9 staging overlay.",
                "intended_use": "Monthly behavioural grade of live retail accounts that are not in default, in the products it was developed on.",
                "approved_on": "2025-06-29", "approved_by": "Model Oversight Committee, MOC-2025-07",
                "last_full_validation": "2025-06-24", "last_validation_ref": "MV-2025-016", "last_validation_conclusion": "fit"},
    "SME-ANN": {"tier": "Tier 1", "tier_reason": "Grades every SME borrower; the grade sets pricing, approval authority and the SME IFRS 9 PD.",
                "intended_use": "Annual-review grade of SME borrowers (revenue under SAR 30 million) in the sectors it was developed on.",
                "approved_on": "2023-09-20", "approved_by": "Model Oversight Committee, MOC-2023-09",
                "last_full_validation": "2023-10-30", "last_validation_ref": "MV-2023-022", "last_validation_conclusion": "fit"},
}
SCHEDULE = {
    "RET-APP": {"frequency": "monthly", "last_run": "2026-09-12", "next_run": "2026-10-12", "report_to": "Model Oversight Committee (quarterly pack)"},
    "RET-BEH": {"frequency": "monthly", "last_run": "2026-09-12", "next_run": "2026-10-12", "report_to": "Model Oversight Committee (quarterly pack)"},
    "SME-ANN": {"frequency": "quarterly", "last_run": "2026-08-14", "next_run": "2026-11-14", "report_to": "Model Oversight Committee (quarterly pack)"},
}
#: Findings carried from earlier validations and monitoring reports (fictional demo records).
FINDINGS = [
    ("F-2023-022-01", "SME-ANN", "MV-2023-022", "calibration", "High", "Grade PDs under-predict in the riskiest grades",
     "Observed default rates in G7-G8 ran above the grade PDs in the last two development years.",
     "Recalibrate the grade PDs on the latest matured cohorts and re-approve at the Model Oversight Committee.", "2023-11-15", "2024-06-30", "open"),
    ("F-2023-022-02", "SME-ANN", "MV-2023-022", "data_quality", "Medium", "Qualitative score has no written scoring guide",
     "Relationship managers score the qualitative factor without a scale definition, so scores are not comparable across branches.",
     "Issue a scoring guide with anchored examples and re-train relationship managers.", "2023-11-15", "2024-05-15", "in_progress"),
    ("F-2023-022-03", "SME-ANN", "MV-2023-022", "data_quality", "Low", "Revenue growth missing for a sixth of borrowers",
     "Revenue growth (a candidate characteristic) is missing where only one year of financials is on file.",
     "Capture two years of financials at onboarding; keep the characteristic out of the model until coverage is above 95%.", "2023-11-15", "2026-12-31", "open"),
    ("F-2026-MR1-01", "RET-APP", "MR-2026-Q1-RET", "usage", "High", "Buy Now Pay Later scored without validation evidence",
     "Buy Now Pay Later accounts are approved on the application scorecard although the product was absent from development.",
     "Restrict use to the approved products, or validate a BNPL segment and add an overlay until then.", "2026-03-10", "2026-09-30", "open"),
    ("F-2025-014-01", "RET-APP", "MV-2025-014", "overrides", "Medium", "Policy-exception overrides lack evidence",
     "A sample of upgrade overrides with the reason 'Policy exception' had no supporting note on file.",
     "Make the evidence field mandatory for upgrade overrides and review a monthly sample.", "2025-06-10", "2026-12-15", "open"),
    ("F-2025-016-01", "RET-BEH", "MV-2025-016", "stability", "Medium", "No trigger for redevelopment on sustained drift",
     "The monitoring plan has no rule for when sustained drift should start a redevelopment review.",
     "Add the trigger: PSI above 0.25 or calibration red in two consecutive months starts a redevelopment review.", "2025-06-24", "2026-11-30", "open"),
    ("F-2025-016-02", "RET-BEH", "MV-2025-016", "data_quality", "Low", "Salary interruption flag defined differently by two feeds",
     "Open Banking and the payroll feed defined a salary interruption differently.",
     "Use the Open Banking definition in both feeds.", "2025-06-24", "2025-12-31", "closed"),
]


def inventory(facts: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for sid, s in dbuild.SCORECARDS.items():
        e = INVENTORY_EXTRA[sid]
        cycle = compute.POLICY["cycle_months"][e["tier"]]
        rows.append({"scorecard_id": sid, "name": s["name"], "version": s["version"], "type": s["type"], "book": s["book"],
                     "segment_col": facts[sid]["segment_col"], "approved_segments": " | ".join(facts[sid]["approved_segments"]),
                     "development_from": s["development"][0], "development_to": s["development"][1], "dev_gini": round(facts[sid]["dev_gini"], 6),
                     "validator": VALIDATOR, **OWNERS[sid], **e, "validation_cycle_months": cycle, "monitoring_frequency": s["frequency"]})
    return pd.DataFrame(rows)


def findings() -> pd.DataFrame:
    cols = ["finding_id", "scorecard_id", "source_ref", "criterion", "severity", "title", "text", "remediation", "raised_on", "due_on", "status"]
    df = pd.DataFrame(FINDINGS, columns=cols)
    owner = []
    for r in df.itertuples():
        o = OWNERS[r.scorecard_id]
        owner.append(o["data_owner"] if r.criterion == "data_quality" else o["override_owner"] if r.criterion == "overrides" else o["model_owner"])
    df.insert(9, "owner", owner)
    return df


def schedule() -> pd.DataFrame:
    return pd.DataFrame([{"scorecard_id": sid, **v, "alert_to": "Noor's brief (CRO, model validation)"} for sid, v in SCHEDULE.items()])


def frames() -> dict[str, pd.DataFrame]:
    m, c, facts = compute.all_scorecards()
    return {"sc_monitor_metric": m, "sc_monitor_characteristic": c, "sc_model_inventory": inventory(facts),
            "sc_findings_register": findings(), "sc_monitor_schedule": schedule()}, facts


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes()).hexdigest()[:16]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    fr, facts = frames()
    if check:
        bad = []
        for name, df in fr.items():
            p = OUT / f"{name}.parquet"
            if not p.exists():
                bad.append(f"{name}: missing")
                continue
            old = pd.read_parquet(p)
            if _digest(old) != _digest(df):
                bad.append(f"{name}: differs from a fresh computation")
        print("CHECK", "PASS" if not bad else "FAIL", *bad, sep="\n  ")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"release_id": RELEASE, "build_version": BUILD_VERSION, "origin": "SYNTHETIC_DEMO", "source_release": paths.RELEASE,
           "policy": compute.POLICY["version"], "relations": {}, "facts": facts}
    for name, df in fr.items():
        df.to_parquet(OUT / f"{name}.parquet", index=False)
        man["relations"][name] = {"rows": int(len(df)), "digest": _digest(df)}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1, default=str))
    print(json.dumps({k: v["rows"] for k, v in man["relations"].items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
