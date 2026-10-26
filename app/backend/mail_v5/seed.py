"""Seeded mail: realistic threads between the seeded users about the v5 books (seed mail-2: 14 threads, all 9 users).

Deterministic: fixed thread and message ids and timestamps; every figure is computed from the books (read-only)
by backend.workspace_v5.book and the retail Early Warning release. Applied once per SEED_VERSION.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import lru_cache
from html import escape
from typing import Any

import pandas as pd

from backend.identity_v5 import paths as id_paths
from backend.mail_v5 import store
from backend.workspace_v5 import book, paths
from backend.workspace_v5.book import bn, mn, pct

P1, P0 = "2026Q2", "2026Q1"
M1, M0 = "2026-06", "2026-05"
ANNE, FAISAL, NOURA, KHALID, REEM, ABDULLAH, SARA, OMAR, LAMA = (
    "anne", "faisal.alqahtani", "noura.alharbi", "khalid.alotaibi", "reem.alshehri", "abdullah.alzahrani",
    "sara.aldosari", "omar.alghamdi", "lama.almutairi")
RETAIL_EWS = paths.EWS / "ews-saudi-retail-20m-v5e1" / "ews_retail_exposure.parquet"


@lru_cache(maxsize=1)
def _retail() -> dict[str, Any]:
    r = pd.read_parquet(RETAIL_EWS, columns=["reporting_month", "stage", "ead_sar_mn", "product"])

    def month(m: str) -> dict[str, Any]:
        x = r[r.reporting_month == m]
        total = float(x.ead_sar_mn.sum())
        s2 = float(x[x.stage == 2].ead_sar_mn.sum())
        by = {p: 100 * float(g[g.stage == 2].ead_sar_mn.sum()) / float(g.ead_sar_mn.sum())
              for p, g in x.groupby("product")}
        return {"ead": total, "s2": s2, "s2_pct": 100 * s2 / total, "by_product": by}
    return {M1: month(M1), M0: month(M0)}


def _obj(otype: str, oid: str, label: str, href: str, summary: str = "", **meta: Any) -> dict[str, Any]:
    return {"type": otype, "id": oid, "label": label, "href": href, "summary": summary, "meta": meta}


def _p(text: str) -> str:
    return "".join(f"<p>{escape(par)}</p>" for par in text.strip().split("\n\n"))


def apply(con: sqlite3.Connection) -> None:
    # Re-seeding replaces the previous seed's rows (only rows with a seed id), never a user's own mail.
    for r in con.execute("SELECT seq FROM mail_messages WHERE id LIKE 'm_seed_%'").fetchall():
        for t in ("mail_recipients", "mail_attachments"):
            con.execute(f"DELETE FROM {t} WHERE message_seq=?", (r["seq"],))
    con.execute("DELETE FROM mail_messages WHERE id LIKE 'm_seed_%'")
    con.execute("DELETE FROM mail_threads WHERE id LIKE 't_seed_%'")
    con.execute("DELETE FROM mail_state WHERE thread_id LIKE 't_seed_%'")
    con.execute("DELETE FROM mail_notifications WHERE thread_id LIKE 't_seed_%'")

    s1, s0 = book.sector("Construction", P1), book.sector("Construction", P0)
    d_ecl = s1["ecl"] - s0["ecl"]
    stages = {r["stage"]: r for r in book.stage_mix("Construction", P0, P1)}
    subs = book.sub_sectors("Construction", P0, P1)
    top_sub = subs[0]
    b = book.borrower("CB01312", P1)
    b0 = book.borrower("CB01312", P0)
    t1, t0 = book.portfolio(P1), book.portfolio(P0)
    rt = _retail()
    r1, r0 = rt[M1], rt[M0]
    worst = sorted(r1["by_product"].items(), key=lambda kv: -kv[1])[:2]

    A_SUB = _obj("analysis", "construction-ecl-by-subsector-2026q1-q2",
                 "Construction ECL by sub-sector, 2026Q1 vs 2026Q2",
                 "/analyses/construction-ecl-by-subsector-2026q1-q2",
                 f"{top_sub['sub_sector']} moved most: ECL {mn(top_sub['ecl_before'])} to {mn(top_sub['ecl_after'])}.")
    INV = _obj("investigation", "construction-ecl-rise-q2-2026", "Investigation: Construction ECL rise, Q2 2026",
               "/investigations/construction-ecl-rise-q2-2026",
               f"Construction ECL {mn(s0['ecl'])} to {mn(s1['ecl'])}.")
    B360 = _obj("borrower", "CB01312", f"CB01312 {b['name']}",
                f"/borrower-360?domain=corporate&customer_id=CB01312&period={P1}",
                f"Exposure {mn(b['exposure'])}, Early Warning {b['ews_band']} (score {b['ews_score']}), "
                f"rating {b['rating']}.", domain="corporate", period=P1)
    EWS_RETAIL = _obj("early-warning-list", "retail-2026-06-stage2", "Early Warning: retail book, 2026-06",
                      "/early-warning?domain=retail", f"Stage 2 is {pct(r1['s2_pct'], 2)} of retail EAD at {M1}.",
                      domain="retail", period=M1)
    EWS_CONS = _obj("early-warning-list", "corporate-2026q2-construction", "Early Warning: Construction, 2026Q2",
                    "/early-warning?domain=corporate&segment=Construction", "Construction sector view, corporate book.",
                    domain="corporate", period=P1)
    PACK = _obj("document", "committee-pack-q2-2026-draft", "Q2 2026 committee pack (draft)",
                "/documents/committee-pack-q2-2026-draft",
                f"Corporate EAD {bn(t1['ead'])}, ECL {bn(t1['ecl'])} at {P1}.")
    PROJECT = _obj("project", "q2-2026-committee-pack", "Project: Q2 2026 committee pack",
                   "/projects/q2-2026-committee-pack", "Sections, owners and due dates for the pack.")
    WHATIF = _obj("whatif-scenario", "rating", "What-If: one-notch downgrade, corporate book",
                  "/what-if?domain=corporate&scenario=rating", "Book-wide rating scenario on the corporate book.")

    threads: list[dict[str, Any]] = [
        {"id": "t_seed_construction", "subject": f"Construction ECL up {mn(d_ecl, 0)} in {P1}",
         "kind": "share", "labels": {ABDULLAH: ["Committee"], SARA: ["Follow-up"]}, "starred": {SARA},
         "messages": [
             (ABDULLAH, [SARA, KHALID], [NOURA], "2026-07-06T07:55:00Z",
              f"Sara, Khalid,\n\nConstruction ECL is {mn(s1['ecl'])} at {P1} against {mn(s0['ecl'])} at {P0}: up "
              f"{mn(d_ecl)} (+{pct(100 * d_ecl / s0['ecl'])}). EAD rose only {pct(100 * (s1['ead'] / s0['ead'] - 1))} ({mn(s0['ead'])} to "
              f"{mn(s1['ead'])}), so this is mainly a credit-quality move, not volume. Coverage went from "
              f"{pct(s0['coverage_pct'], 2)} to {pct(s1['coverage_pct'], 2)}.\n\nCan you each take a look at where it "
              "sits and come back to me before Thursday?", [INV, A_SUB]),
             (SARA, [ABDULLAH], [KHALID], "2026-07-06T09:20:00Z",
              f"Abdullah,\n\nStage 3 drives it. Stage 3 ECL went from {mn(stages[3]['ecl_before'])} to "
              f"{mn(stages[3]['ecl_after'])} and stage 3 EAD from {mn(stages[3]['ead_before'])} to "
              f"{mn(stages[3]['ead_after'])}. The biggest sub-sector move is {top_sub['sub_sector']} "
              f"(ECL {mn(top_sub['ecl_before'])} to {mn(top_sub['ecl_after'])}). The table is attached; I will "
              "add the borrower-level detail to the investigation.", [A_SUB, EWS_CONS]),
             (KHALID, [ABDULLAH, SARA], [], "2026-07-06T11:40:00Z",
              "Agreed with Sara's read. I would keep the sector under monthly review and bring it to the "
              "committee as an item for noting, not for decision. Please add the borrower-level list to the "
              "investigation so I can check the largest names with the relationship managers.", []),
         ], "read": {ABDULLAH: 3, SARA: 3, KHALID: 3, NOURA: 0}},
        {"id": "t_seed_cb01312", "subject": f"CB01312 {b['name']}: critical on Early Warning",
         "kind": "share", "labels": {KHALID: ["Follow-up"]}, "starred": {KHALID},
         "messages": [
             (SARA, [KHALID], [NOURA], "2026-07-07T06:30:00Z",
              f"Khalid,\n\nCB01312 {b['name']} (Construction, {b['sub_sector']}) is critical on Early Warning at "
              f"{P1} (score {b['ews_score']}, rule set {b['ews_ruleset']}). Exposure is {mn(b['exposure'])} across "
              f"{b['facilities']} facilities ({mn(b0['exposure'])} at {P0}), ECL {mn(b['ecl'], 2)}. Rating "
              f"{b0['rating']} to {b['rating']}, outlook {b['rating_outlook']}.\n\nThe Borrower 360 page is linked. "
              "I suggest we meet the client before the committee.", [B360]),
             (KHALID, [SARA], [], "2026-07-07T08:10:00Z",
              "Thanks Sara. Please add the relationship graph view when you have it, I want to see who the "
              "suppliers and buyers are before we speak to them. I will ask the relationship manager for a "
              "meeting on Thursday.", []),
             (SARA, [KHALID], [], "2026-07-07T09:05:00Z",
              "Will do. I will also check the group exposure against the connected-party limit.", []),
         ], "read": {SARA: 3, KHALID: 2, NOURA: 0}},
        {"id": "t_seed_retail_stage2", "subject": f"Retail Stage 2 build, {M1}",
         "kind": "share", "labels": {REEM: ["Committee"]}, "starred": {REEM},
         "messages": [
             (OMAR, [REEM], [ABDULLAH], "2026-07-08T05:50:00Z",
              f"Reem,\n\nRetail Stage 2 EAD is {mn(r1['s2'])} at {M1}, {pct(r1['s2_pct'], 2)} of the book, up from "
              f"{mn(r0['s2'])} ({pct(r0['s2_pct'], 2)}) at {M0}. By product, {worst[0][0]} "
              f"({pct(worst[0][1], 1)} of its EAD) and {worst[1][0]} ({pct(worst[1][1], 1)}) carry it. The "
              "Early Warning view is attached.", [EWS_RETAIL]),
             (REEM, [OMAR], [ABDULLAH], "2026-07-08T07:30:00Z",
              "Thanks Omar. Is this a roll-in from Stage 1 on delinquency, or SICR on score migration? "
              "I need to know before I speak to the cards team.", []),
             (OMAR, [REEM], [ABDULLAH], "2026-07-08T09:00:00Z",
              "I am splitting the Stage 2 build between score migration and delinquency in the Early Warning "
              "drill-down. I will share the cohort with you once the split is done.", []),
         ], "read": {OMAR: 3, REEM: 2, ABDULLAH: 0}},
        {"id": "t_seed_pack", "subject": "Q2 2026 committee pack: sections and owners",
         "kind": "share", "labels": {NOURA: ["Committee"], FAISAL: ["Committee"]}, "starred": set(),
         "messages": [
             (NOURA, [FAISAL, ABDULLAH, KHALID, REEM], [ANNE], "2026-07-07T07:15:00Z",
              f"Colleagues,\n\nThe draft Q2 2026 committee pack is in the project. The corporate book stands at EAD "
              f"{bn(t1['ead'])} and ECL {bn(t1['ecl'])} at {P1} (EAD {bn(t0['ead'])}, ECL {bn(t0['ecl'])} at "
              f"{P0}). Sections and owners: corporate (Khalid), retail (Reem), portfolio and What-If (Abdullah), "
              "model validation (Lama). Please send your sections by 9 July.", [PACK, PROJECT]),
             (FAISAL, [NOURA], [ABDULLAH], "2026-07-07T10:00:00Z",
              "Noura, I want a What-If downgrade scenario in the pack, with the capital effect. Abdullah, can "
              "you run the one-notch book-wide scenario and share it?", []),
             (ABDULLAH, [FAISAL], [NOURA], "2026-07-07T11:30:00Z",
              "Yes. I will run it on the corporate book and send the result by mail.", [WHATIF]),
         ], "read": {NOURA: 3, FAISAL: 2, ABDULLAH: 3, KHALID: 0, REEM: 0, ANNE: 0}},
        {"id": "t_seed_validation", "subject": "Rating model validation: schedule for Q3",
         "kind": "message", "labels": {}, "starred": set(),
         "messages": [
             (LAMA, [FAISAL], [NOURA], "2026-07-08T12:00:00Z",
              "Faisal,\n\nThe corporate rating model has no independent validation in the Q2 cycle. I propose "
              "discrimination, calibration and stability testing in Q3, using the rating migrations already in "
              "the corporate book. Retail scorecards follow in Q4. Please confirm the scope.", []),
         ], "read": {LAMA: 1, FAISAL: 0, NOURA: 0}},
        {"id": "t_seed_welcome", "subject": "CreditProbe Mail is live",
         "kind": "message", "labels": {}, "starred": set(),
         "messages": [
             (ANNE, [FAISAL, NOURA, KHALID, REEM, ABDULLAH, SARA, OMAR, LAMA], [], "2026-07-01T06:00:00Z",
              "Hello all,\n\nCreditProbe Mail is now the place to send findings, scenarios and borrower pages "
              "to each other. Use Share on any screen, or write a message and attach a CreditProbe object.\n\n"
              "Anne", []),
         ], "read": {ANNE: 1, FAISAL: 1, NOURA: 1, KHALID: 1, REEM: 1, ABDULLAH: 1, SARA: 1, OMAR: 1, LAMA: 1}},
    ]

    # ------------------------------------------------------------------ R3 threads (seed mail-2)
    ecl_bn = f"SAR {t1['ecl'] / 1000:,.2f}bn"
    A_EAD = _obj("analysis", "ead-by-sector-2026q2", "EAD by sector, 2026Q2", "/analyses/ead-by-sector-2026q2",
                 f"Corporate EAD {bn(t1['ead'])} at {P1}.")
    A_STAGE = _obj("analysis", "construction-stage-mix-2026q1-q2", "Construction stage mix, 2026Q1 vs 2026Q2",
                   "/analyses/construction-stage-mix-2026q1-q2",
                   f"Stage 3 ECL {mn(stages[3]['ecl_before'])} to {mn(stages[3]['ecl_after'])}.")
    OIL = _obj("whatif-scenario", "std-corporate-oil-shock", "What-If: oil price -40% (Brent), corporate book",
               "/what-if?domain=corporate&open=std-corporate-oil-shock",
               f"Reported ECL {ecl_bn}. Delta method SAR 7.96bn (+2.06%); XGBoost SAR 7.86bn (+0.91%).",
               domain="corporate", period=P1, model="delta")
    SCV = _obj("scorecard-validation", "retail-application-2026", "Scorecard validation: retail application scorecard",
               "/scorecard-validation?scorecard=retail-application",
               "Plan: discrimination, calibration, stability and variables, with red/amber/green thresholds.",
               scorecard="retail-application")
    REPORT = _obj("report", "committee-pack-q2-2026-draft", "Q2 2026 credit committee pack (Word)",
                  "/documents/committee-pack-q2-2026-draft",
                  f"Corporate EAD {bn(t1['ead'])}, ECL {bn(t1['ecl'])} at {P1}; retail Stage 2 {pct(r1['s2_pct'], 2)} at {M1}.")
    F_CIRC = _file(con, "f_seed_c2026_03", "C-2026-03 SICR circular (summary).txt", "text/plain", FAISAL,
                   "Circular C-2026-03: significant increase in credit risk (SICR)\n"
                   "Effective: 1 Jul 2026\n\n"
                   "RP-5.1 (amended): a downgrade of two notches or more since origination is a significant increase\n"
                   "in credit risk. The exposure moves to Stage 2 and carries lifetime ECL.\n"
                   "RP-5.2: Early Warning band 'critical' for two consecutive months is reviewed for Stage 2.\n"
                   "Scope: corporate and retail books. First reporting under the circular: 2026Q3.\n")
    sub_csv = "sub_sector,ecl_2026q1_sar_mn,ecl_2026q2_sar_mn,change_sar_mn\n" + "".join(
        f"{x['sub_sector']},{x['ecl_before']:.1f},{x['ecl_after']:.1f},{x['ecl_after'] - x['ecl_before']:.1f}\n"
        for x in subs)
    F_SUBS = _file(con, "f_seed_construction_subsectors", "Construction ECL by sub-sector 2026Q1-Q2.csv", "text/csv",
                   KHALID, sub_csv)

    threads += [
        {"id": "t_seed_policy", "subject": "Circular C-2026-03: a two-notch downgrade is now SICR (RP-5.1)",
         "kind": "message", "labels": {FAISAL: ["Policy"], NOURA: ["Policy"], LAMA: ["Policy", "Models"]},
         "starred": {ABDULLAH},
         "messages": [
             (FAISAL, [NOURA, ABDULLAH], [KHALID, REEM, LAMA], "2026-07-02T06:40:00Z",
              "Colleagues,\n\nCircular C-2026-03 takes effect on 1 Jul 2026. RP-5.1 now treats a downgrade of two "
              "notches or more since origination as a significant increase in credit risk, so those exposures move to "
              "Stage 2 with lifetime ECL. The first quarter reported under it is 2026Q3.\n\nThe summary is attached. "
              "Please tell me which books and Early Warning rules it touches in your area.", [], {"files": [F_CIRC]}),
             (NOURA, [FAISAL], [ABDULLAH, KHALID, REEM, LAMA], "2026-07-02T08:15:00Z",
              "Thanks Faisal. On the corporate side the rule bites where ratings migrated in the last two quarters; "
              "Construction is the first place to look. Khalid, Reem: please list the segments in your books where "
              "the two-notch rule changes the staging, before the committee.", []),
             (LAMA, [FAISAL], [NOURA], "2026-07-02T10:05:00Z",
              "Faisal, model validation will test the new staging rule in the Q3 cycle: the share of Stage 2 driven "
              "by RP-5.1, and whether the rating model's notches are stable enough to carry it.", []),
         ], "read": {FAISAL: 3, NOURA: 3, ABDULLAH: 2, KHALID: 1, REEM: 0, LAMA: 3}},
        {"id": "t_seed_whatif_oil", "subject": "What-If: oil price -40% on the corporate book",
         "kind": "share", "labels": {FAISAL: ["Committee"], ABDULLAH: ["What-If"]}, "starred": {FAISAL},
         "messages": [
             (ABDULLAH, [FAISAL], [NOURA, KHALID], "2026-07-09T07:20:00Z",
              f"Faisal,\n\nI ran the standard oil shock (Brent 40% below the base path in every year) on the corporate "
              f"book at {P1}. Reported ECL is {ecl_bn}. The Delta method gives SAR 7.96bn (+2.06%) and XGBoost "
              "SAR 7.86bn (+0.91%). Likelihood: severe but historically observed (Brent fell 47.1% in 2015; 1 of 35 "
              "years).\n\nThe scenario is attached and opens in What-If.", [OIL]),
             (FAISAL, [ABDULLAH], [NOURA, KHALID], "2026-07-09T09:45:00Z",
              "Thank you Abdullah. Put the Delta number in the pack as the headline and show XGBoost as the "
              "challenger. Add the one-notch downgrade next to it so the committee sees both.", []),
             (ABDULLAH, [FAISAL], [NOURA, KHALID], "2026-07-09T10:30:00Z",
              "Will do. Both scenarios will be in the What-If section of the pack by Sunday.", []),
         ], "read": {ABDULLAH: 3, FAISAL: 3, NOURA: 1, KHALID: 0}},
        {"id": "t_seed_scorecard", "subject": "Retail application scorecard: validation plan and thresholds",
         "kind": "share", "labels": {LAMA: ["Models"], REEM: ["Models"]}, "starred": {LAMA},
         "messages": [
             (LAMA, [REEM], [OMAR, FAISAL], "2026-07-13T06:10:00Z",
              "Reem,\n\nHere is the validation plan for the retail application scorecard. Discrimination: Gini, AUC "
              "and KS by product (green at Gini 40% or more, amber 30% to 40%, red below 30%). Calibration: "
              "Hosmer-Lemeshow, binomial and traffic-light tests by grade, Brier score. Stability: PSI and CSI by "
              "variable (green below 0.10, amber 0.10 to 0.25, red above 0.25). Variables: IV, WoE monotonicity, "
              "correlation and VIF. Outcome: default within 12 months.\n\nThe validation is attached. Please confirm "
              "the samples: development 2024, monitoring the last four quarters.", [SCV]),
             (REEM, [LAMA], [OMAR, FAISAL], "2026-07-13T08:00:00Z",
              "Agreed, Lama. Please add the behavioural scorecard in the same cycle. Omar can give you the account "
              "and customer IDs for the monitoring sample from the Early Warning release.", []),
             (LAMA, [REEM], [OMAR, FAISAL], "2026-07-13T09:30:00Z",
              "Done: behavioural added. I will send the Word report into Playbook when the tests are run.", []),
         ], "read": {LAMA: 3, REEM: 3, OMAR: 1, FAISAL: 0}},
        {"id": "t_seed_ews_weekly", "subject": "Early Warning: critical names this week, Construction",
         "kind": "share", "labels": {KHALID: ["Early Warning"], SARA: ["Early Warning"]}, "starred": set(),
         "messages": [
             (SARA, [KHALID], [ABDULLAH], "2026-07-14T05:45:00Z",
              f"Khalid,\n\nThe weekly Early Warning list for Construction at {P1} is attached. CB01312 {b['name']} is "
              f"still critical (score {b['ews_score']}); exposure {mn(b['exposure'])}. I have added the borrower page "
              "so you can open it from here.", [EWS_CONS, B360], {"bcc": [NOURA]}),
         ], "read": {SARA: 1, KHALID: 0, ABDULLAH: 1, NOURA: 0}},
        {"id": "t_seed_minutes", "subject": "Q2 2026 committee: minutes and actions",
         "kind": "share", "labels": {NOURA: ["Committee"], FAISAL: ["Committee"], KHALID: ["Committee"]},
         "starred": {NOURA},
         "messages": [
             (NOURA, [FAISAL, KHALID, REEM, ABDULLAH, LAMA], [ANNE], "2026-07-16T12:30:00Z",
              f"Colleagues,\n\nThe committee noted the Q2 2026 pack: corporate EAD {bn(t1['ead'])} and ECL "
              f"{bn(t1['ecl'])} at {P1}; Construction ECL {mn(s1['ecl'])} against {mn(s0['ecl'])} at {P0}; retail "
              f"Stage 2 {pct(r1['s2_pct'], 2)} of EAD at {M1}.\n\nActions: Khalid, monthly review of Construction and "
              "the CB01312 client meeting. Reem, split the retail Stage 2 build between score migration and "
              "delinquency. Abdullah, oil -40% and the one-notch downgrade in the next pack. Lama, scorecard "
              "validation in Q3.", [REPORT]),
         ], "read": {NOURA: 1, FAISAL: 1, KHALID: 0, REEM: 0, ABDULLAH: 0, LAMA: 0, ANNE: 0}},
        {"id": "t_seed_overlay", "subject": "Construction: a management overlay for Q3?",
         "kind": "message", "labels": {NOURA: ["Follow-up"], KHALID: ["Committee"]}, "starred": set(),
         "messages": [
             (KHALID, [NOURA], [FAISAL, SARA], "2026-07-20T07:00:00Z",
              f"Noura,\n\nConstruction ECL is {mn(s1['ecl'])} at {P1} against {mn(s0['ecl'])} at {P0}. Most of it is "
              f"Stage 3, and {top_sub['sub_sector']} moved most. With C-2026-03 from 1 July, more names will move to "
              "Stage 2 in Q3. Do we want an overlay for the sector, or let the model carry it?\n\nThe sub-sector "
              "table is attached.", [A_SUB, A_STAGE], {"files": [F_SUBS]}),
             (NOURA, [KHALID], [FAISAL, SARA], "2026-07-20T09:40:00Z",
              "No overlay yet. The model already carries the Stage 3 move. Bring the Q3 staging under the circular "
              "first and we decide then.", []),
         ], "read": {KHALID: 2, NOURA: 2, FAISAL: 1, SARA: 0}},
        {"id": "t_seed_access", "subject": "Access: retail book data for scorecard validation",
         "kind": "message", "labels": {}, "starred": set(),
         "messages": [
             (LAMA, [ANNE], [], "2026-07-12T06:00:00Z",
              "Anne,\n\nFor the scorecard validation I need read access to the retail book and the Early Warning "
              "release (accounts and customers, 2024 to 2026-06). Could you enable it?", []),
             (ANNE, [LAMA], [], "2026-07-12T07:30:00Z",
              "Done, Lama. You now cover corporate and retail. Mail me if anything is missing.", []),
             (LAMA, [ANNE], [], "2026-07-12T07:50:00Z", "Thank you, it works.", []),
         ], "read": {LAMA: 3, ANNE: 2}},
        {"id": "t_seed_retail_cohort", "subject": "Retail risk build-up: the cohort behind Stage 2",
         "kind": "share", "labels": {REEM: ["Follow-up"]}, "starred": set(),
         "messages": [
             (OMAR, [REEM, ABDULLAH], [], "2026-07-21T06:20:00Z",
              f"Reem, Abdullah,\n\nThe split you asked for: Stage 2 EAD is {mn(r1['s2'])} at {M1} against "
              f"{mn(r0['s2'])} at {M0}. {worst[0][0]} and {worst[1][0]} carry most of it. The Early Warning cohort "
              "is attached, ready to export to What-If.", [EWS_RETAIL]),
         ], "read": {OMAR: 1, REEM: 0, ABDULLAH: 1}},
    ]

    for th in threads:
        first_at = th["messages"][0][3]
        con.execute("INSERT INTO mail_threads(id, subject, created_by, created_at, last_at) VALUES(?,?,?,?,?)",
                    (th["id"], th["subject"], th["messages"][0][0], first_at, th["messages"][-1][3]))
        seqs: list[int] = []
        prev: tuple[str, str, str] | None = None  # (sender, sent_at, body_html) of the message before
        for i, msg in enumerate(th["messages"], 1):
            sender, to, cc, at, body, objs = msg[:6]
            extra = msg[6] if len(msg) > 6 else {}
            att = [{"kind": "object", "object": o} for o in objs] + [{"kind": "file", "file_id": f} for f in extra.get("files", [])]
            html = _p(body)
            if prev is not None:  # a reply quotes the message it answers, as a mail client does
                html += (f"<blockquote><p>On {_when(prev[1])} UTC, {escape(_name(prev[0]))} wrote:</p>{prev[2]}"
                         "</blockquote>")
            res = store._insert_message(con, th["id"], sender, to, cc, html, f"m_seed_{th['id'][7:]}_{i - 1}" if i > 1 else None,
                                        att, kind=th["kind"] if i == 1 else "message", sent_at=at,
                                        mid=f"m_seed_{th['id'][7:]}_{i}", bcc=extra.get("bcc", []))
            seqs.append(res["seq"])
            prev = (sender, at, html)
        # read markers: users in `read` have read the first N messages of the thread
        users = {m[0] for m in th["messages"]} | {u for m in th["messages"] for u in m[1] + m[2]} | {
            u for m in th["messages"] if len(m) > 6 for u in m[6].get("bcc", [])}
        for u in users:
            n = th["read"].get(u, 0)
            store._state(con, th["id"], u)
            con.execute("UPDATE mail_state SET last_read_seq=?, starred=?, labels=? WHERE thread_id=? AND username=?",
                        (seqs[n - 1] if n else 0, 1 if u in th["starred"] else 0,
                         json.dumps(th["labels"].get(u, [])), th["id"], u))
            for lab in th["labels"].get(u, []):
                con.execute("INSERT OR IGNORE INTO mail_labels(owner, name) VALUES(?,?)", (u, lab))
        # notifications for what is still unread
        for u in users:
            n = th["read"].get(u, 0)
            for msg, seq in list(zip(th["messages"], seqs))[n:]:
                sender, to, cc, at = msg[:4]
                bcc = msg[6].get("bcc", []) if len(msg) > 6 else []
                if sender != u and (u in to or u in cc or u in bcc):
                    con.execute("INSERT INTO mail_notifications(username, kind, title, href, from_user, thread_id,"
                                " created_at, read) VALUES(?,?,?,?,?,?,?,0)",
                                (u, th["kind"], f"{_name(sender)} sent you: {th['subject']}"[:240],
                                 f"/messages?thread={th['id']}", sender, th["id"], at))

    # An archived thread for Anne, and drafts for Sara and Abdullah.
    con.execute("UPDATE mail_state SET archived=1 WHERE thread_id='t_seed_welcome' AND username=?", (ANNE,))
    for u in (SARA, KHALID, ABDULLAH, NOURA, FAISAL, REEM, OMAR, LAMA, ANNE):
        for lab, colour in LABELS:
            con.execute("INSERT OR IGNORE INTO mail_labels(owner, name, color) VALUES(?,?,?)", (u, lab, colour))
            con.execute("UPDATE mail_labels SET color=? WHERE owner=? AND name=?", (colour, u, lab))
    con.execute("DELETE FROM mail_drafts WHERE id LIKE 'd_seed_%'")
    con.execute("INSERT INTO mail_drafts(id, owner, data, updated_at) VALUES(?,?,?,?)",
                ("d_seed_sara", SARA, json.dumps({
                    "to": [KHALID], "cc": [], "bcc": [], "subject": "CB01312: relationship graph and group limit check",
                    "body_html": _p("Khalid,\n\nDraft: I will attach the relationship graph and the group limit check "
                                    "for CB01312 here once the checks are done."),
                    "attachments": [{"kind": "object", "object": B360}], "mode": "new", "thread_id": None,
                    "in_reply_to": None}), "2026-07-07T09:30:00Z"))
    con.execute("INSERT INTO mail_drafts(id, owner, data, updated_at) VALUES(?,?,?,?)",
                ("d_seed_abdullah", ABDULLAH, json.dumps({
                    "to": [FAISAL], "cc": [NOURA], "bcc": [], "subject": "Oil -40% and one-notch downgrade: capital effect",
                    "body_html": _p("Faisal,\n\nDraft: both scenarios side by side, with the capital effect, for the "
                                    "What-If section of the pack."),
                    "attachments": [{"kind": "object", "object": OIL}, {"kind": "object", "object": WHATIF}],
                    "mode": "new", "thread_id": None, "in_reply_to": None}), "2026-07-10T08:00:00Z"))


LABELS = (("Committee", "#2563eb"), ("Follow-up", "#d97706"), ("Early Warning", "#dc2626"), ("Policy", "#0d9488"),
          ("Models", "#7c3aed"), ("What-If", "#16a34a"))


def _file(con: sqlite3.Connection, fid: str, name: str, ctype: str, uploader: str, text: str) -> str:
    """A seeded file attachment: fixed id, deterministic bytes, stored like an upload."""
    data = text.encode("utf-8")
    d = id_paths.files_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / fid).write_bytes(data)
    con.execute("DELETE FROM mail_files WHERE id=?", (fid,))
    con.execute("INSERT INTO mail_files(id, name, size, content_type, sha256, uploader, created_at) VALUES(?,?,?,?,?,?,?)",
                (fid, name, len(data), ctype, hashlib.sha256(data).hexdigest(), uploader, "2026-07-01T00:00:00Z"))
    return fid


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _when(iso: str) -> str:
    """'7 Jul 2026, 08:31', the same words the Mail client uses."""
    return f"{int(iso[8:10])} {_MONTHS[int(iso[5:7]) - 1]} {iso[:4]}, {iso[11:16]}"


_NAMES = {"anne": "Anne", "faisal.alqahtani": "Faisal Al-Qahtani", "noura.alharbi": "Noura Al-Harbi",
          "khalid.alotaibi": "Khalid Al-Otaibi", "reem.alshehri": "Reem Al-Shehri",
          "abdullah.alzahrani": "Abdullah Al-Zahrani", "sara.aldosari": "Sara Al-Dosari",
          "omar.alghamdi": "Omar Al-Ghamdi", "lama.almutairi": "Lama Al-Mutairi"}


def _name(u: str) -> str:
    return _NAMES[u]
