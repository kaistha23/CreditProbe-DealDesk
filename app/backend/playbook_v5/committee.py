"""Committee-pack playbooks (PLAN_R9 Session D4): five repeatable packs, each with its steps, the data it reads and
its output, and "Run" producing the Word document from the books and the CBUAE CRM checks at the moment it runs.

  ecl-committee           ECL committee pack
  watchlist-committee     Watchlist committee pack
  arw-quarterly           Accepted Risk Watch quarterly review
  auditor-query           Auditor query response (30+ DPD in Stage 1, Art. 7.8 / 7.10)
  credit-review-opinion   Credit review opinion (portfolio, CBUAE CRM compliance)

Deterministic: no model call; the same books give the same document.
"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd

MN = 1e6  # the books are in SAR million; the Word formats take SAR

PLAYBOOKS: list[dict[str, Any]] = [
    {"id": "ecl-committee", "name": "ECL committee pack", "audience": "ECL / provisioning committee", "frequency": "Quarterly",
     "steps": ["Stage mix and movement against the prior quarter", "ECL and coverage by stage",
               "Stage 3 provisions against the CBUAE floors (Art. 9.23, 9.24)", "SICR: 30+ DPD still in Stage 1 (Art. 7.8)",
               "Decisions requested"],
     "data": ["Books: facility stage, DPD, EAD, ECL (corporate quarter, retail month)", "CBUAE CRM breach checks"],
     "output": "Word pack: summary, stage and ECL tables, floor shortfall, SICR exceptions, decisions"},
    {"id": "watchlist-committee", "name": "Watchlist committee pack", "audience": "Watchlist committee", "frequency": "Monthly",
     "steps": ["Names on the watchlist and their exposure", "Stage and DPD of each", "Cross-default exposure (Art. 6.12)",
               "Actions and owners"],
     "data": ["Books: borrower watchlist flag, facility stage, DPD, EAD, ECL", "CBUAE CRM check CRM-6.12"],
     "output": "Word pack: watchlist summary, top names table, cross-default list, actions"},
    {"id": "arw-quarterly", "name": "Accepted Risk Watch quarterly review", "audience": "CRO", "frequency": "Quarterly",
     "steps": ["Names accepted at approval with a no-SICR rationale", "Watch items on track / due / missed",
               "Escalation rule: 2+ missed or one critical → Bank Watchlist and SICR assessment", "ECL if Tier 1 moved to Stage 2"],
     "data": ["Accepted Risk Watch (watch domain, Session C)", "Books: stage, EAD, ECL"],
     "output": "Word review: tiers, items, escalations, ECL sensitivity"},
    {"id": "auditor-query", "name": "Auditor query response", "audience": "External auditor", "frequency": "On request",
     "steps": ["Restate the query: wholesale facilities 30+ DPD still in Stage 1", "List them with DPD, EAD and ECL",
               "Rebuttal evidence required (Art. 7.8, 7.10): CCO and CRO sign-off", "Draft response"],
     "data": ["Books: facility stage and DPD", "CBUAE CRM check CRM-7.8"],
     "output": "Word response: the query, the population, the rebuttal check, the answer"},
    {"id": "credit-review-opinion", "name": "Credit review opinion", "audience": "Board Risk Committee", "frequency": "Semi-annual",
     "steps": ["Scope and method", "Portfolio quality (stage mix, NPL ratio against the 5% trigger, Art. 12.3)",
               "CBUAE CRM compliance by article", "Opinion and recommendations"],
     "data": ["Books (both)", "CBUAE CRM breach checks, all articles"],
     "output": "Word opinion: scope, quality, compliance table, opinion"},
]
BY_ID = {p["id"]: p for p in PLAYBOOKS}


def catalogue() -> dict[str, Any]:
    return {"playbooks": PLAYBOOKS, "pack": "P1 CBUAE CRM Intelligence"}


def _stage_table(b: str) -> tuple[list[dict[str, Any]], dict[str, float], str]:
    from backend.regulatory import crm_checks

    ctx = crm_checks.context(b)
    fac = ctx.fac
    prev = ctx.prev
    rows = []
    tot_ead = float(fac["ead_sar_mn"].sum()) or 1.0
    pe = float(prev["ead_sar_mn"].sum()) if prev is not None else 0.0
    for s in (1, 2, 3):
        cur = fac[fac["stage"] == s]
        ead, ecl = float(cur["ead_sar_mn"].sum()), float(cur["ecl_sar_mn"].sum())
        p_share = (float(prev[prev["stage"] == s]["ead_sar_mn"].sum()) / pe) if prev is not None and pe else None
        rows.append({"stage": f"Stage {s}", "n": int(len(cur)), "ead": ead * MN, "share": ead / tot_ead,
                     "prev_share": p_share, "ecl": ecl * MN, "cov": (ecl / ead) if ead else 0.0})
    tot = {"ead": tot_ead * MN, "ecl": float(fac["ecl_sar_mn"].sum()) * MN, "n": int(len(fac)),
           "dpd30_s1": int(((fac["dpd_days"] >= 30) & (fac["stage"] == 1)).sum())}
    return rows, tot, ctx.period


STAGE_COLS = [{"key": "stage", "label": "Stage", "format": "text"}, {"key": "n", "label": "Count", "format": "int"},
              {"key": "ead", "label": "EAD", "format": "sar"}, {"key": "share", "label": "Share of EAD", "format": "pct"},
              {"key": "prev_share", "label": "Prior period share", "format": "pct"}, {"key": "ecl", "label": "ECL", "format": "sar"},
              {"key": "cov", "label": "Coverage", "format": "pct"}]


def _checks_table(res: dict[str, Any], ids: tuple[str, ...] = ()) -> dict[str, Any]:
    rows = [{"article": c["article"].replace("CBUAE CRM ", ""), "rule": c["title"], "book": c["book"].capitalize(),
             "breaches": c["breaches"], "ead": c["ead_sar_mn"] * MN, "shortfall": c["shortfall_sar_mn"] * MN,
             "status": "Breach" if c["breaches"] else "Compliant"}
            for c in res["checks"] if not ids or c["check_id"] in ids]
    return {"kind": "table", "title": "CBUAE CRM checks",
            "columns": [{"key": "article", "label": "Article", "format": "text"}, {"key": "rule", "label": "Rule", "format": "text"},
                        {"key": "book", "label": "Book", "format": "text"}, {"key": "breaches", "label": "Breaches", "format": "int"},
                        {"key": "ead", "label": "EAD", "format": "sar"}, {"key": "shortfall", "label": "Provision shortfall", "format": "sar"},
                        {"key": "status", "label": "Status", "format": "text"}], "rows": rows}


def _breach_rows(res: dict[str, Any], check_id: str, book: str = "corporate", n: int = 20) -> dict[str, Any]:
    rows = [{"entity": r["entity_id"], "borrower": r["borrower_id"], "measured": str(r["measured"]), "required": str(r["required"]),
             "ead": r["ead_sar_mn"] * MN, "ecl": r["ecl_sar_mn"] * MN}
            for r in res["breaches"] if r["check_id"] == check_id and r["book"] == book]
    rows.sort(key=lambda r: -r["ead"])
    return {"kind": "table", "title": f"Largest {min(n, len(rows))} of {len(rows)} ({check_id})",
            "columns": [{"key": "entity", "label": "Facility", "format": "text"}, {"key": "borrower", "label": "Borrower", "format": "text"},
                        {"key": "measured", "label": "Measured", "format": "text"}, {"key": "required", "label": "Required", "format": "text"},
                        {"key": "ead", "label": "EAD", "format": "sar"}, {"key": "ecl", "label": "ECL", "format": "sar"}],
            "rows": rows[:n], "note": "Source: CreditProbe books; CBUAE CRM breach checks."}


def _check(res: dict[str, Any], cid: str, book: str = "corporate") -> dict[str, Any]:
    return next((c for c in res["checks"] if c["check_id"] == cid and c["book"] == book),
                {"breaches": 0, "ead_sar_mn": 0.0, "shortfall_sar_mn": 0.0, "borrowers": 0, "article": "", "title": cid})


def _sar(v_mn: float) -> str:
    from backend.playbook_v5 import formats

    return formats.sar(v_mn * MN)


def build(playbook_id: str, user: str = "") -> dict[str, Any]:
    """The report (Playbook report shape) for one committee playbook, from the books now."""
    from backend.regulatory import crm_checks

    p = BY_ID[playbook_id]
    res = crm_checks.run()
    stages, tot, period = _stage_table("corporate")
    s3 = stages[2]["share"]
    secs: list[dict[str, Any]] = []
    kpis = {"kind": "kpis", "items": [
        {"label": "EAD", "value": tot["ead"], "format": "sar"}, {"label": "ECL", "value": tot["ecl"], "format": "sar"},
        {"label": "Coverage", "value": tot["ecl"] / tot["ead"] if tot["ead"] else 0, "format": "pct"},
        {"label": "Stage 2 share", "value": stages[1]["share"], "format": "pct",
         "delta": (stages[1]["share"] - stages[1]["prev_share"]) if stages[1]["prev_share"] is not None else None},
        {"label": "Stage 3 share", "value": s3, "format": "pct", "status": "red" if s3 > 0.05 else "green"},
        {"label": "CBUAE CRM breaches", "value": res["totals"]["breaches"], "format": "int",
         "status": "red" if res["totals"]["high"] else "amber" if res["totals"]["breaches"] else "green"}]}
    stage_tbl = {"kind": "table", "title": f"Stage mix, corporate book, {period}", "columns": STAGE_COLS, "rows": stages}
    floor = _check(res, "CRM-9.23")
    dpd30 = _check(res, "CRM-7.8")
    xdef = _check(res, "CRM-6.12")
    if playbook_id == "ecl-committee":
        secs = [
            {"title": "Summary", "blocks": [kpis, {"kind": "paragraph", "text":
                f"ECL stands at {_sar(tot['ecl'] / MN)} on {_sar(tot['ead'] / MN)} of exposure. Stage 3 is {s3 * 100:.1f}% of EAD "
                f"({'above' if s3 > 0.05 else 'within'} the 5% Board-report trigger, Art. 12.3). The Stage 3 wholesale floor "
                f"check finds {floor['breaches']:,} facilities below the floor with a shortfall of {_sar(floor['shortfall_sar_mn'])} (Art. 9.23)."}]},
            {"title": "Stage mix and ECL", "blocks": [stage_tbl]},
            {"title": "Stage 3 provisions against the CBUAE floors", "blocks": [
                _checks_table(res, ("CRM-9.23", "CRM-9.24", "CRM-10.8")), _breach_rows(res, "CRM-9.23")]},
            {"title": "SICR exceptions", "blocks": [{"kind": "paragraph", "text":
                f"{dpd30['breaches']:,} facilities are 30+ days past due and still in Stage 1 (Art. 7.8), EAD {_sar(dpd30['ead_sar_mn'])}. "
                "Each needs a documented rebuttal approved by the CCO and the CRO (Art. 7.10) or a transfer to Stage 2."},
                _breach_rows(res, "CRM-7.8", n=15)]},
            {"title": "Decisions requested", "blocks": [{"kind": "bullets", "items": [
                f"Top up Stage 3 provisions by {_sar(floor['shortfall_sar_mn'])} to meet the Art. 9.23 floors, or approve documented exceptions.",
                f"Transfer the {dpd30['breaches']:,} unrebutted 30+ DPD facilities to Stage 2, or record CCO and CRO rebuttals.",
                "Confirm the Stage 1 + 2 provision check against 1.5% of credit RWA (Art. 9.21) for the quarter."]}]},
        ]
    elif playbook_id == "watchlist-committee":
        ctx = crm_checks.context("corporate")
        bor = ctx.borrowers if ctx.borrowers is not None else pd.DataFrame(columns=["borrower_id", "watchlist_flag"])
        wl = set(bor[bor["watchlist_flag"] == 1]["borrower_id"]) if "watchlist_flag" in bor else set()
        f = ctx.fac[ctx.fac["borrower_id"].isin(wl)]
        g = f.groupby("borrower_id").agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"), stage=("stage", "max"),
                                         dpd=("dpd_days", "max")).reset_index().sort_values("ead", ascending=False)
        rows = [{"borrower": r.borrower_id, "stage": f"Stage {int(r.stage)}", "dpd": int(r.dpd), "ead": r.ead * MN, "ecl": r.ecl * MN}
                for r in g.head(25).itertuples()]
        secs = [
            {"title": "Summary", "blocks": [{"kind": "kpis", "items": [
                {"label": "Names on the watchlist", "value": len(wl), "format": "int"},
                {"label": "Watchlist EAD", "value": float(f["ead_sar_mn"].sum()) * MN, "format": "sar"},
                {"label": "Watchlist ECL", "value": float(f["ecl_sar_mn"].sum()) * MN, "format": "sar"},
                {"label": "In Stage 3", "value": int((g["stage"] == 3).sum()), "format": "int"}]}]},
            {"title": "Largest watchlist names", "blocks": [{"kind": "table", "title": f"Top {len(rows)} by EAD, {ctx.period}", "columns": [
                {"key": "borrower", "label": "Borrower", "format": "text"}, {"key": "stage", "label": "Worst stage", "format": "text"},
                {"key": "dpd", "label": "Max DPD", "format": "int"}, {"key": "ead", "label": "EAD", "format": "sar"},
                {"key": "ecl", "label": "ECL", "format": "sar"}], "rows": rows}]},
            {"title": "Cross-default (Art. 6.12)", "blocks": [{"kind": "paragraph", "text":
                f"{xdef['borrowers']:,} borrowers are in default on a material facility while other facilities are not in Stage 3 "
                f"(EAD {_sar(xdef['ead_sar_mn'])})."}, _breach_rows(res, "CRM-6.12", n=15)]},
            {"title": "Actions", "blocks": [{"kind": "bullets", "items": [
                "Confirm each name's action plan and owner; names without one are escalated to the CRO.",
                "Apply cross-default to the listed borrowers or record why the facility is not material (Art. 6.12).",
                "Review Stage 3 names for the Art. 9.23 floors before quarter end."]}]},
        ]
    elif playbook_id == "arw-quarterly":
        secs = [
            {"title": "Summary", "blocks": [kpis, {"kind": "paragraph", "text":
                "Accepted Risk Watch holds the names approved with accepted concerns and a recorded no-SICR rationale. Each concern is a "
                "dated watch item; 2 or more missed items, or one critical item, move the name to the Bank Watchlist with a SICR assessment."}]},
            {"title": "Escalation rule", "blocks": [{"kind": "bullets", "items": [
                "Tier 1: material concerns, monthly tracking; Tier 2: quarterly; Tier 3: annual review.",
                "2+ missed items or one critical item → Bank Watchlist and SICR assessment (Art. 7.11).",
                "The rationale for not recognising SICR is re-confirmed at each review."]}]},
            {"title": "ECL sensitivity", "blocks": [stage_tbl, {"kind": "callout", "tone": "info", "text":
                "The watch items and tiers are read from the Accepted Risk Watch domain (Session C). Where it is not loaded, this section "
                "shows the book's stage mix as the base for the Tier 1 → Stage 2 sensitivity."}]},
        ]
    elif playbook_id == "auditor-query":
        secs = [
            {"title": "The query", "blocks": [{"kind": "paragraph", "text":
                "Provide the wholesale facilities 30 or more days past due that remain in Stage 1 at the reporting date, with the evidence "
                "that rebuts the presumption of a significant increase in credit risk (CBUAE CRM Art. 7.8, 7.10)."}]},
            {"title": "Population", "blocks": [{"kind": "paragraph", "text":
                f"At {period}, {dpd30['breaches']:,} corporate facilities ({dpd30['borrowers']:,} borrowers) are 30+ DPD in Stage 1, "
                f"EAD {_sar(dpd30['ead_sar_mn'])}."}, _breach_rows(res, "CRM-7.8", n=25)]},
            {"title": "Rebuttal check", "blocks": [{"kind": "bullets", "items": [
                "A rebuttal must be documented and approved by both the CCO and the CRO (Art. 7.10).",
                "Facilities without both sign-offs are transferred to Stage 2 at the next run.",
                "Rebuttal sign-offs are not yet held in the books; the list above is the population to evidence."]}]},
            {"title": "Draft response", "blocks": [{"kind": "paragraph", "text":
                f"The Bank identified {dpd30['breaches']:,} wholesale facilities 30+ DPD in Stage 1 at {period}. For each, the Bank will "
                "provide the approved rebuttal (CCO and CRO) or confirm the transfer to Stage 2. The population and its EAD are attached."}]},
        ]
    else:  # credit-review-opinion
        npl = s3
        secs = [
            {"title": "Scope and method", "blocks": [{"kind": "paragraph", "text":
                "A review of the corporate and retail books at the reporting date against the CBUAE Credit Risk Management Standards, "
                "using CreditProbe's deterministic breach checks (each tied to its article) and the books' stage, DPD, ECL and collateral."}]},
            {"title": "Portfolio quality", "blocks": [kpis, stage_tbl]},
            {"title": "CBUAE CRM compliance", "blocks": [_checks_table(res)]},
            {"title": "Opinion", "blocks": [{"kind": "callout", "tone": "warning" if res["totals"]["high"] else "info", "text":
                f"{res['totals']['checks_in_breach']} of {res['totals']['checks']} checks are in breach ({res['totals']['breaches']:,} "
                f"breaches, {res['totals']['high']:,} high severity). NPL ratio {npl * 100:.1f}% "
                f"({'above' if npl > 0.05 else 'within'} the 5% trigger)."},
                {"kind": "bullets", "items": [
                    f"Close the Art. 9.23 floor shortfall of {_sar(floor['shortfall_sar_mn'])}.",
                    "Evidence or transfer the 30+ DPD Stage 1 population (Art. 7.8, 7.10).",
                    "Apply cross-default across borrower groups (Art. 6.12).",
                    "Repeat the data-domain checks (Art. 9.21 CRWA floor, 7.7 deferrals, 4.3 annual reviews) each quarter."]}]},
        ]
    return {"title": f"{p['name']} · {period}", "template_name": p["name"], "status_label": "Draft", "version": 1,
            "owner": {"name": user or "CreditProbe"}, "reviewers": [], "book": "corporate", "period": period,
            "due_date": None, "sections": secs, "history": [], "generated_at": int(time.time())}


def run_docx(playbook_id: str, user: str = "") -> tuple[bytes, str]:
    from backend.playbook_v5 import export_docx

    rep = build(playbook_id, user)
    data = export_docx.build(rep, generated_by=user or "CreditProbe")
    fname = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in rep["title"].replace("·", "-"))[:80].strip()
    return data, fname
