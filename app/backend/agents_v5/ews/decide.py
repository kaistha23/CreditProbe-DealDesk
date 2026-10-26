"""The triage decision table: CBUAE indicators -> verdict, and the RM action note.

Verdicts, worst first: `utp` (propose unlikely-to-pay), `sicr` (propose SICR / Stage 2), `watchlist` (put or keep on
the watch list, Art. 7.6), `watch` (monitor next period), `noise` (explained, with the reason). The table is written
here once; the deterministic planner and the model planner both call it as the `triage.decide` tool, so no verdict is
ever produced by a model. SICR and UTP are proposals (A4): this module never writes a stage.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

ORDER = ("noise", "watch", "watchlist", "sicr", "utp")
LABEL = {"noise": "Noise", "watch": "Watch", "watchlist": "Watchlist", "sicr": "Propose SICR", "utp": "Propose UTP"}
RANK = {v: i for i, v in enumerate(ORDER)}

#: Rules whose firing restates a status the bank already holds (no new information on its own).
STATUS_RULES = {"C-WATCH", "C-SICR", "C-BUR-ENQ", "C-UTIL"}
#: Retail rules that are not a CBUAE indicator on their own (usage and enquiry signals, a low but stable band).
SOFT_RULES = {"R-UTIL", "R-BUR-ENQ", "R-SCORE-LOW"}

#: Days the RM has to act, per verdict; the escalation ladder (followup.py) counts from the due date.
DUE_DAYS = {"utp": 5, "sicr": 10, "watchlist": 20, "watch": 45}

ACTIONS = {
    "utp": ("Prepare the unlikeliness-to-pay assessment for the credit officer: confirm each Art. 6 indicator with "
            "documents, update the repayment-capacity view and propose the recovery strategy."),
    "sicr": ("Document the SICR assessment (Art. 7.9) for the approver: confirm the indicators with the borrower, obtain "
             "current financials and covenant certificates, and state any rebuttal evidence (Art. 7.10)."),
    "watchlist": ("Place the borrower on the watch list (Art. 7.6): agree the monitoring triggers, call the borrower on "
                  "the drivers below and report back before the next review."),
    "watch": "Review at the next monitoring cycle; no action needed now beyond checking the drivers below.",
}


def decide(name: dict[str, Any]) -> dict[str, Any]:
    """`name`: stage, band, score, watchlist, indicators, rules (fired), changes. Returns verdict, reason, confidence."""
    inds = name.get("indicators") or []
    stage = int(name.get("stage") or 0)
    band = name.get("band") or "none"
    ch = name.get("changes") or {}
    rules = {r["rule_id"] for r in name.get("rules") or []}
    utp_hard = [i for i in inds if i["kind"] == "utp" and i["strength"] == "hard"]
    utp_soft = [i for i in inds if i["kind"] == "utp" and i["strength"] == "soft"]
    sicr_hard = [i for i in inds if i["kind"] == "sicr" and i["strength"] == "hard"]
    sicr_soft = [i for i in inds if i["kind"] == "sicr" and i["strength"] == "soft"]
    worsening = bool((ch.get("score_change") or 0) > 0 or ch.get("new_reasons"))

    def out(verdict: str, reason: str, basis: list[dict[str, Any]], confidence: str) -> dict[str, Any]:
        return {"verdict": verdict, "label": LABEL[verdict], "reason": reason, "confidence": confidence,
                "basis": [i["code"] for i in basis], "articles": sorted({i["article"]["ref"] for i in basis})}

    if utp_hard or len(utp_soft) >= 2:
        basis = utp_hard + utp_soft
        return out("utp", "Unlikeliness-to-pay indicators: " + "; ".join(i["label"] for i in basis) + ".",
                   basis, "high" if utp_hard else "medium")
    if stage <= 1:
        if sicr_hard or len(sicr_soft) + len(utp_soft) >= 2:
            basis = sicr_hard + sicr_soft + utp_soft
            return out("sicr", "SICR indicators on a Stage 1 borrower: " + "; ".join(i["label"] for i in basis) + ".",
                       basis, "high" if sicr_hard or len(basis) >= 3 else "medium")
        if sicr_soft or utp_soft:
            basis = sicr_soft + utp_soft
            return out("watchlist", "One indicator, not yet enough for SICR: " + basis[0]["label"]
                       + ". Watch-list it as the precursor (Art. 7.6).", basis, "medium")
    else:  # Stage 2: SICR is already recognised; the question is UTP (Art. 7.2)
        if utp_soft or (len(sicr_soft) >= 2 and worsening):
            basis = utp_soft + sicr_soft
            return out("watchlist", "Already Stage 2 and deteriorating towards unlikeliness to pay (Art. 7.2): "
                       + "; ".join(i["label"] for i in basis) + ".", basis, "medium")
        if sicr_soft:
            return out("watch", "Already Stage 2; live SICR drivers, no UTP indicator: "
                       + "; ".join(i["label"] for i in sicr_soft) + ".", sicr_soft, "medium")
    # No CBUAE indicator in the evidence: explain the warning.
    if ch.get("dpd_cured") or ch.get("cured_flag"):
        return out("noise", f"One-off arrears already cured: {ch.get('dpd_prior', 0)} DPD last period, current now; "
                   "no other SICR or UTP indicator in the evidence.", [], "high")
    if rules and rules <= STATUS_RULES | {"C-DOWNGRADE"}:
        return out("noise", "The warning restates what the bank already holds (" + ", ".join(sorted(rules))
                   + "); conduct, bureau, covenants and collateral show no SICR or UTP indicator.", [], "high")
    if rules and rules <= SOFT_RULES:
        return out("noise", "The warning comes from usage and enquiry signals only (" + ", ".join(sorted(rules))
                   + "), which are not CBUAE indicators on their own; payments, income, bureau and collateral show "
                   "no SICR or UTP indicator.", [], "high")
    if band in ("high", "critical") or (ch.get("score_change") or 0) >= 3:
        return out("watch", f"Score {name.get('score')} ({band}) with no CBUAE indicator in the evidence yet; "
                   "re-check next period.", [], "low")
    return out("noise", "No SICR or UTP indicator in the evidence; the score comes from "
               + (", ".join(sorted(rules)) or "no rule") + " only.", [], "medium")


def action_note(subject: dict[str, Any], verdict: dict[str, Any], today: dt.date) -> dict[str, Any] | None:
    v = verdict["verdict"]
    if v == "noise":
        return None
    rm = subject.get("rm") or {}
    due = today + dt.timedelta(days=DUE_DAYS[v])
    drivers = [i["label"] for i in subject.get("indicators") or [] if i["code"] in verdict["basis"]] or \
              [r["label"] for r in subject.get("rules") or []]
    return {"borrower_id": subject["borrower_id"], "borrower_name": subject.get("borrower_name"),
            "verdict": v, "owner": rm.get("rm_name") or "Relationship manager (unassigned)",
            "owner_id": rm.get("rm_id"), "owner_role": "RM", "branch": rm.get("branch_name"),
            "domain": subject.get("domain") or "corporate",
            "due": due.isoformat(), "created": today.isoformat(), "level": 0,
            "action": ACTIONS[v], "drivers": drivers[:6], "articles": verdict["articles"]}


__all__ = ["ACTIONS", "DUE_DAYS", "LABEL", "ORDER", "RANK", "action_note", "decide"]
