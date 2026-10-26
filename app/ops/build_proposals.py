"""Build the `proposals` data domain (PLAN_R9 Session E) and the two prepared proposal files.

    python3 ops/build_proposals.py           write data/proposals/proposals-uae-v1 and demo_inputs/proposals/*.docx
    python3 ops/build_proposals.py --check   fail if the published domain differs from the review engine now

Relations (AED million): proposal (one row per proposal), proposal_facility (one row per facility),
proposal_finding (one row per check, gap, weakness and watch item). Built from
backend.dealdesk.proposal_review at the seeded parameters (v1).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.dealdesk import proposal_review as pr  # noqa: E402
from backend.dealdesk.proposal_cases import AS_OF, CASES  # noqa: E402

OUT = V5 / "data" / "proposals" / "proposals-uae-v1"
DOCS = V5 / "demo_inputs" / "proposals"

DICTIONARY = {
    "proposal_id": "Proposal identifier (PRP-…).", "borrower": "Borrower name.", "group_name": "Economic group.",
    "sector": "Sector.", "rating": "Internal rating (global order AAA … C).", "tier": "Review tier.",
    "currency": "Currency of the limits.", "total_existing_mn": "Existing limits, millions.", "total_proposed_mn": "Proposed limits, millions.",
    "quality_score": "Proposal quality score out of 100.", "raroc_seed": "Relationship RAROC with fees and deposits at the seeded parameters.",
    "hurdle_seed": "Hurdle at the seeded parameters.", "watch_status": "Proposed watch status.", "as_of": "Review date.",
    "facility": "Facility name.", "kind": "funded, performance_lg or financial_lg.", "existing_mn": "Existing limit, millions.",
    "proposed_mn": "Proposed limit, millions.", "pricing_bps": "Margin or commission, basis points.",
    "finding_id": "Finding identifier.", "finding_type": "check, gap, weakness or watch.", "text": "The finding.",
    "result": "Pass / Fail (checks), Open (gaps and watch items), Covered / Uncovered (weaknesses).",
    "reference": "CBUAE CRM article or the due date.",
}


def frames() -> dict[str, pd.DataFrame]:
    """At the seeded parameters (v1): Admin edits under var/ are set aside while the domain is built."""
    from backend.dealdesk import params, paths
    keep = paths.VAR
    paths.VAR = V5 / "var" / "proposals_build_seed_only"
    params.reload()
    try:
        return _frames()
    finally:
        paths.VAR = keep
        params.reload()


def _frames() -> dict[str, pd.DataFrame]:
    props, facs, finds = [], [], []
    for cid, c in CASES.items():
        r = pr.review(cid)
        props.append({"proposal_id": cid, "borrower": c["borrower"], "group_name": c["group"], "sector": c["sector"],
                      "rating": c["rating"], "tier": c["tier"], "currency": c["currency"],
                      "total_existing_mn": round(r["summary"]["total_existing"], 4), "total_proposed_mn": round(r["summary"]["total_proposed"], 4),
                      "quality_score": int(r["score"]["total"]), "raroc_seed": round(r["pre_deal"]["raroc"]["raroc"], 6),
                      "hurdle_seed": round(r["pre_deal"]["raroc"]["hurdle"], 6), "watch_status": r["watch_entry"]["status"], "as_of": AS_OF})
        for f in c["facilities"]:
            facs.append({"proposal_id": cid, "facility": f["name"], "kind": f["kind"], "existing_mn": f["existing"],
                         "proposed_mn": f["proposed"], "pricing_bps": int(f["bps"]), "as_of": AS_OF})
        n = 0
        for x in r["checks"]:
            n += 1
            finds.append({"proposal_id": cid, "finding_id": f"{cid}-F{n:02d}", "finding_type": "check", "text": x["check"], "result": x["result"], "reference": x["ref"], "as_of": AS_OF})
        for g in r["gaps"]:
            n += 1
            finds.append({"proposal_id": cid, "finding_id": f"{cid}-F{n:02d}", "finding_type": "gap", "text": g["item"], "result": "Open", "reference": g["ref"], "as_of": AS_OF})
        for w in r["weaknesses"]:
            n += 1
            finds.append({"proposal_id": cid, "finding_id": f"{cid}-F{n:02d}", "finding_type": "weakness", "text": w["weakness"],
                          "result": "Covered" if w["covered"] else "Uncovered", "reference": w["mitigant"] or "", "as_of": AS_OF})
        for w in r["watch_entry"]["items"]:
            n += 1
            finds.append({"proposal_id": cid, "finding_id": f"{cid}-F{n:02d}", "finding_type": "watch", "text": w["item"], "result": "Open", "reference": w["due"], "as_of": AS_OF})
    return {"proposal": pd.DataFrame(props), "proposal_facility": pd.DataFrame(facs), "proposal_finding": pd.DataFrame(finds)}


def main() -> int:
    fr = frames()
    if "--check" in sys.argv:
        bad = []
        for k, df in fr.items():
            got = pd.read_parquet(OUT / f"{k}.parquet")
            try:
                pd.testing.assert_frame_equal(got, df, check_dtype=False)
            except AssertionError as e:
                bad.append(f"{k}: {str(e)[:200]}")
        print("PROPOSALS DOMAIN", "FAIL " + "; ".join(bad) if bad else "PASS")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for k, df in fr.items():
        df.to_parquet(OUT / f"{k}.parquet", index=False)
    (OUT / "manifest.json").write_text(json.dumps({"domain": "proposals", "as_of": AS_OF, "currency": "AED",
                                                    "rows": {k: len(v) for k, v in fr.items()}, "dictionary": DICTIONARY}, indent=1))
    DOCS.mkdir(parents=True, exist_ok=True)
    for cid, c in CASES.items():
        (DOCS / c["file_name"]).write_bytes(pr.proposal_docx(cid))
    print("proposals domain:", {k: len(v) for k, v in fr.items()}, "->", OUT, "; files ->", DOCS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
