"""R14 E (K19 #5, K24 #3): how each finding is cured — by structure, condition precedent, security, covenant,
explanation or governance — or "not curable by structure". Deterministic rules on the finding's category and code."""
from __future__ import annotations

import re
from typing import Any

KINDS = {"structure": "Structure", "cp": "Condition precedent (prior to limit loading)", "security": "Security",
         "covenant": "Covenant", "explanation": "Explanation required", "governance": "Governance", "not_curable": "Not curable by structure"}


def _c(kind: str, text: str, owner: str = "RM", when: str = "before committee") -> dict[str, Any]:
    return {"kind": kind, "kind_label": KINDS[kind], "text": text, "owner": owner, "when": when}


def _doc_name(title: str) -> str:
    return re.split(r":\s*(not provided|expired|pending)", title, maxsplit=1)[0].strip()


def cure_for(pid: str, f: dict[str, Any], cap: dict[str, Any] | None = None) -> dict[str, Any]:
    code, cat, title, text = str(f.get("code") or ""), f["category"], str(f.get("title") or ""), str(f.get("text") or "")
    low = (title + " " + text).lower()
    if f.get("severity") == "info":
        return _c("explanation", "For information: no cure needed; read with the other findings.", "Credit", "—")
    if code == "CAPACITY" or cat == "capacity":
        c = (cap or {}).get("capacity_sar_mn")
        if c is not None and c <= 0:
            return _c("not_curable", "No capacity on the working-capital cycle or cash flow: the amount cannot be cut to a level the "
                                     "borrower can carry; decline or restructure with new equity or security.", "Credit", "at committee")
        return _c("structure", f"Amount cut to capacity: SAR {c:,.1f}m ({cap.get('method_label', '')}).", "Credit", "counter-offer")
    if cat == "pricing":
        return _c("structure", "Margin and fees raised to clear the hurdle (counter-offer pricing at breakeven or above).", "RM", "counter-offer")
    if cat == "covenants":
        return _c("covenant", "Covenant reset with at least 15% headroom at base and step-downs, or the amount cut so the ratio clears.",
                  "Credit", "counter-offer")
    if cat == "documents":
        return _c("cp", f"Prior to limit loading: obtain {_doc_name(title)} (current, in the bank's format).", "RM", "prior to limit loading")
    if "not perfected" in low or "perfected" in low and "security" in low:
        return _c("cp", "Prior to limit loading: perfect every guarantee and assignment; no drawdown before perfection.", "Legal", "prior to limit loading")
    if cat == "governance" and ("classified" in low or "litigation" in low or "arrears" in low or "court" in low):
        return _c("not_curable", "Group risk (connected party classified, in arrears or in litigation) is not cured by this deal's "
                                 "structure; committee accepts it with a cross-default clause and a group cap, or declines.", "Committee", "at committee")
    if code in ("DATA-05",) or "returned cheque" in low:
        return _c("explanation", "RM to explain the returned cheques (dates, amounts, reasons, regularisation) and correct the memo; "
                                 "monthly conduct trigger: any returned cheque goes to Early Warning.", "RM", "before committee")
    if cat == "conduct" and ("bureau" in low or "reconcile" in low or "declared" in low or "cbrbr" in low):
        return _c("cp", "Prior to committee: facility offer letters from every other bank and a reconciliation to the CBRBR; "
                        "limits re-sized on the reconciled debt.", "RM", "before committee")
    if cat == "governance" and ("insider" in low or "staff" in low):
        return _c("governance", "Conflict declared in writing; the staff member excluded from the deal; approval one level above "
                                "the staff member's reporting line.", "Compliance", "before committee")
    if cat == "governance" and ("classified" in low or "litigation" in low or "arrears" in low or "court" in low):
        return _c("not_curable", "Group risk (connected party classified, in arrears or in litigation) is not cured by this deal's "
                                 "structure; committee accepts it with a cross-default clause and a group cap, or declines.", "Committee", "at committee")
    if cat == "governance" and "ownership" in low:
        return _c("cp", "Prior to limit loading: KYC refreshed for the new owners and the ownership change disclosed.", "RM", "prior to limit loading")
    if cat == "financial_quality":
        if "auditor changed" in low or "change of auditor" in low:
            return _c("covenant", "Condition: no change of auditor without the bank's consent; auditor on the approved panel from the "
                                  "next audit; RM to explain the change.", "Credit", "with the approval")
        if "audit opinion" in low or "qualified" in low:
            return _c("explanation", "Explanation and provision required for the qualification; condition: clean opinion from an "
                                     "approved-panel auditor at the next year end.", "RM", "before committee")
        if "related-party" in low or "related party" in low:
            return _c("covenant", "Covenant: related-party balances below 20% of net worth, settlement plan, subordination of "
                                  "shareholder accounts.", "Credit", "with the approval")
        if "auditor" in low:
            return _c("covenant", "Condition: auditor on the bank's approved panel from the next audit.", "Credit", "with the approval")
        if "late" in low:
            return _c("covenant", "Covenant: audited statements within 120 days of year end; breach is an event of default.", "Credit", "with the approval")
        if "cash conversion" in low or "operating cash flow" in low:
            return _c("covenant", "Quarterly cash-flow reporting and a minimum cash-conversion trigger in monitoring.", "Credit", "with the approval")
        if "bureau" in low or "turnover" in low:
            return _c("explanation", "RM to reconcile the statements to the bureau and the account turnover; limits sized on the "
                                     "reconciled figures.", "RM", "before committee")
        if "leverage" in low or "net worth" in low:
            return _c("covenant", "Covenant on adjusted leverage (related parties netted) with step-downs.", "Credit", "with the approval")
        return _c("explanation", "Explanation required from the borrower; tracked as a monitoring trigger.", "RM", "before committee")
    if cat == "track_record":
        return _c("explanation", "Explanation of the unmet earlier condition and a revised, measurable condition with a date; "
                                 "not curable by this deal's structure.", "RM", "before committee")
    if cat == "memo":
        return _c("explanation", "RM to rewrite the memo section in the bank's voice (both sides of each risk).", "RM", "before committee")
    if cat == "data":
        return _c("explanation", "RM to correct the memo to the records and explain the difference.", "RM", "before committee")
    if f.get("condition"):
        return _c("cp", f"Condition: {f['condition']}", "RM", "prior to limit loading")
    return _c("explanation", "Explanation required before committee.", "RM", "before committee")
