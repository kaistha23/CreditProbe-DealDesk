"""R14 F demo rows for the full data build (backend/dealdesk/data/build.py `_flow_rows`) and for
`ops/r14_f_publish_seed.py`, which publishes only these three relations. Deterministic: engine results on the committed
sources, a fixed time stamp, no review cache or user state."""
from __future__ import annotations

from typing import Any

from backend.dealdesk import engine
from backend.dealdesk.stressproof import structures as ST

DEALS = ("R12-TWA", "R12-TWB", "DD-06")
ACTOR = "F:data-build"


def _structures(stamp: str) -> list[dict[str, Any]]:
    out = []
    for pid in DEALS:
        p = ST.deal(pid)
        cands = [c for c in ST.candidates(pid, p, None) if c["role"] in ("ask", "recommended")]
        for c in cands:
            r = ST.measure(p, c, None)
            out.append(ST._row_out(pid, r, False, ACTOR, stamp))
    return out


def _proof(stamp: str) -> list[dict[str, Any]]:
    from backend.dealdesk.stressproof import solver as SV
    pid = "DD-06"
    p = ST.deal(pid)
    sol = SV.solve(pid, "ask", "moderate")
    a0 = engine.analyse(p, sol["start"]["terms"])
    a1 = engine.analyse(ST.with_covenants(p, sol["covenants"]), sol["terms"])
    return [{"proof_id": "SP-SEED-DD06", "proposal_id": pid, "from_structure_key": "ask", "new_structure_key": "proofed_seed",
             "target_severity": "moderate", "changes_json": sol["changes"], "survives_flag": int(not sol["uncured"]),
             "first_break_before": sol["first_before"], "raroc_before_pct": a0["metrics"]["lifetime_raroc"] * 100,
             "raroc_after_pct": a1["metrics"]["lifetime_raroc"] * 100, "sva_before_mn": a0["metrics"]["sva"], "sva_after_mn": a1["metrics"]["sva"],
             "cost_text": "; ".join(c["text"] for c in sol["changes"]), "interpretation": "Seed run of the reverse solver on the ask (data build).",
             "regime_label": "", "sensitivity_version": "", "run_by": ACTOR, "run_at": stamp}]



def _monitoring(stamp: str) -> list[dict[str, Any]]:
    p = ST.deal("DD-06")
    return [{"monitoring_proposal_id": "MP14-SEED-DD06", "subject_kind": "deal", "proposal_id": "DD-06", "obligor_id": p["obligor"].get("obligor_id", ""),
             "obligor_name": p["obligor"]["name"], "facility_ref": "ALL", "source_screen": "deal", "tier": "High", "previous_tier": "",
             "reason": "Stress verdict Restructure: a 10% revenue fall breaks Debt/EBITDA against the 4.00x policy limit (Stress Lab ladder).",
             "evidence_json": [{"label": "Stress verdict", "value": "Restructure (tier High)", "relation": "dd_stress_result"}],
             "review_frequency": "quarterly", "triggers_json": [{"metric": "leverage_x", "operator": ">", "threshold": 3.75,
                                                                 "label": "Debt/EBITDA above 3.75x"}],
             "owner": "Credit Risk monitoring", "due_date": "2027-01-18", "status": "proposed", "maker": "Credit analyst (seed)",
             "made_at": stamp, "checker": "", "decided_at": None, "decision_note": "", "triggers_hit_json": []}]


def rows(stamp: str) -> dict[str, list[dict[str, Any]]]:
    return {"dd_structure_set": _structures(stamp), "dd_stress_proof": _proof(stamp), "dd_monitoring_proposal": _monitoring(stamp)}
