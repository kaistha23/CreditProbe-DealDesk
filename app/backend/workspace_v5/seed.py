"""The seed: users, an investigation, a project, saved analyses, documents and
inbox items, tied to the v5 corporate book. (Mail has its own seed in backend.mail_v5.)

Deterministic: fixed ids, fixed timestamps, and every figure computed by
`book` from the releases (read-only). Applied once, on a store that has never
been seeded; every insert is INSERT OR IGNORE on a fixed id, so applying it
twice changes nothing. Seeded rows carry demo=1 in the store; the flag is never shown.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.identity_v5 import directory
from backend.workspace_v5 import book, paths
from backend.workspace_v5.book import bn, mn, pct

P1, P0 = "2026Q2", "2026Q1"
SECTOR = "Construction"
BORROWER = "CB01045"

CO, RM, ANNE = "sara.aldosari", "abdullah.alzahrani", "anne"
NAME = {CO: "Sara Al-Dosari", RM: "Abdullah Al-Zahrani", ANNE: "Anne"}
USERS = [(u["username"], u["name"], u["role"], u["initials"], u["position"]) for u in directory.seed_users()]

INV_ID = "construction-ecl-rise-q2-2026"
PROJECT_ID = "q2-2026-committee-pack"
A_SECTOR = "ead-by-sector-2026q2"
A_SUBSECTOR = "construction-ecl-by-subsector-2026q1-q2"
DOC_PACK = "committee-pack-q2-2026-draft"
DOC_MEMO = "credit-memo-cb01045"

#: Deep links into the live v5 modules.
EWS_LINK = {"label": "Early Warning · Corporate · Construction", "type": "early-warning",
            "href": "/early-warning?domain=corporate&segment=Construction"}
B360_LINK = {"label": "Borrower 360 · CB01045 Rabigh Continental Contracting · 2026Q2", "type": "borrower-360",
             "href": "/borrower-360?domain=corporate&customer_id=CB01045&period=2026Q2"}
WHATIF_LINK = {"label": "What-If · Corporate · rating downgrade scenario", "type": "what-if",
               "href": "/what-if?domain=corporate&scenario=rating"}
INV_LINK = {"label": "Investigation · Construction ECL rise, Q2 2026", "type": "investigation",
            "href": f"/investigations/{INV_ID}"}
PROJECT_LINK = {"label": "Project · Q2 2026 committee pack", "type": "project", "href": f"/projects/{PROJECT_ID}"}
DOC_PACK_LINK = {"label": "Document · Q2 2026 committee pack (draft)", "type": "document",
                 "href": f"/documents/{DOC_PACK}"}
DOC_MEMO_LINK = {"label": "Document · Credit memo, CB01045", "type": "document", "href": f"/documents/{DOC_MEMO}"}
A_SECTOR_LINK = {"label": "Analysis · EAD by sector, 2026Q2", "type": "analysis", "href": f"/analyses/{A_SECTOR}"}

SOURCE = f"{paths.EWS_CORP}/ews_corp_exposure.parquet (Cockpit book {paths.CORP_BOOK})"


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def facts() -> dict[str, Any]:
    """Every figure the seed quotes, computed from the book."""
    s1, s0 = book.sector(SECTOR, P1), book.sector(SECTOR, P0)
    b1, b0 = book.borrower(BORROWER, P1), book.borrower(BORROWER, P0)
    t1, t0 = book.portfolio(P1), book.portfolio(P0)
    stages = book.stage_mix(SECTOR, P0, P1)
    subs = book.sub_sectors(SECTOR, P0, P1)
    secs = book.sectors(P1)
    return {"s1": s1, "s0": s0, "b1": b1, "b0": b0, "t1": t1, "t0": t0, "stages": stages, "subs": subs,
            "sectors": secs}


def investigation_figures(f: dict[str, Any]) -> list[dict[str, Any]]:
    s1, s0 = f["s1"], f["s0"]
    src = "ews_corp_exposure"
    return [
        {"key": "ead_2026Q2", "label": "Construction EAD", "period": P1, "value": s1["ead"], "unit": "sar_mn",
         "source": f"{src}.ead_sar_mn"},
        {"key": "ecl_2026Q2", "label": "Construction ECL", "period": P1, "value": s1["ecl"], "unit": "sar_mn",
         "source": f"{src}.ecl_sar_mn"},
        {"key": "ead_2026Q1", "label": "Construction EAD", "period": P0, "value": s0["ead"], "unit": "sar_mn",
         "source": f"{src}.ead_sar_mn"},
        {"key": "ecl_2026Q1", "label": "Construction ECL", "period": P0, "value": s0["ecl"], "unit": "sar_mn",
         "source": f"{src}.ecl_sar_mn"},
        {"key": "ecl_change", "label": "ECL change", "period": f"{P0} → {P1}", "value": s1["ecl"] - s0["ecl"],
         "unit": "sar_mn", "source": "difference"},
        {"key": "coverage_2026Q2", "label": "ECL coverage", "period": P1, "value": s1["coverage_pct"], "unit": "pct",
         "source": "ECL / EAD"},
        {"key": "coverage_2026Q1", "label": "ECL coverage", "period": P0, "value": s0["coverage_pct"], "unit": "pct",
         "source": "ECL / EAD"},
        {"key": "borrowers_2026Q2", "label": "Borrowers", "period": P1, "value": s1["borrowers"], "unit": "int",
         "source": f"{src}.borrower_id"},
    ]


def borrower_sentence(b: dict[str, Any]) -> str:
    return (f"Exposure {mn(b['exposure'])} at {P1} per the book ({b['facilities']} facilities); upgraded "
            f"{b['rating_previous']} → {b['rating']} this quarter; the Early Warning rule set {b['ews_ruleset']} "
            f"scores it {b['ews_band']} (score {b['ews_score']}).")


def apply(con: sqlite3.Connection) -> None:
    f = facts()
    s1, s0, b1, b0, t1, t0 = f["s1"], f["s0"], f["b1"], f["b0"], f["t1"], f["t0"]
    d_ecl = s1["ecl"] - s0["ecl"]
    st = {r["stage"]: r for r in f["stages"]}
    top_sub = f["subs"][0]
    share = next(r["share_pct"] for r in f["sectors"] if r["sector"] == SECTOR)
    ins = con.execute

    for u in USERS:
        ins("INSERT OR IGNORE INTO users(id, name, title, initials, position) VALUES(?,?,?,?,?)", u)

    # ------------------------------------------------------------ investigation
    inv_summary = (f"Construction ECL rose from {mn(s0['ecl'])} at {P0} to {mn(s1['ecl'])} at {P1} "
                   f"(+{mn(d_ecl)}, +{pct(100 * d_ecl / s0['ecl'])}) while EAD moved from {mn(s0['ead'])} to "
                   f"{mn(s1['ead'])}; coverage {pct(s0['coverage_pct'], 2)} → {pct(s1['coverage_pct'], 2)}. ")
    ins("INSERT OR IGNORE INTO investigations(id, title, summary, sector, period, compare_period, status, owner_id, "
        "project_id, figures, links, created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
        (INV_ID, "Construction ECL rise, Q2 2026", inv_summary, SECTOR, P1, P0, "in_review", CO, PROJECT_ID,
         _j(investigation_figures(f)), _j([EWS_LINK, B360_LINK, WHATIF_LINK, A_SECTOR_LINK]),
         "2026-07-03T08:40:00Z", "2026-07-05T14:00:00Z"))
    notes = [
        (1, CO, "note", "2026-07-03T08:40:00Z",
         f"Opened from the Early Warning sector view. Per the book ({paths.EWS_CORP}), Construction EAD is "
         f"{mn(s1['ead'])} at {P1} against {mn(s0['ead'])} at {P0} "
         f"(+{pct(100 * (s1['ead'] / s0['ead'] - 1))}), but ECL is {mn(s1['ecl'])} against {mn(s0['ecl'])}: up "
         f"{mn(d_ecl)} (+{pct(100 * d_ecl / s0['ecl'])}). The rise is ECL, not volume."),
        (2, RM, "note", "2026-07-03T11:05:00Z",
         f"Stage 3 drives it: stage 3 EAD {mn(st[3]['ead_before'])} → {mn(st[3]['ead_after'])} and stage 3 ECL "
         f"{mn(st[3]['ecl_before'])} → {mn(st[3]['ecl_after'])}. The largest sub-sector move is "
         f"{top_sub['sub_sector']} (ECL {mn(top_sub['ecl_before'])} → {mn(top_sub['ecl_after'])})."),
        (3, RM, "note", "2026-07-04T09:30:00Z",
         f"@{NAME[CO]} please take CB01045 {b1['name']} into the committee pack as a Borrower 360 "
         f"review. {borrower_sentence(b1)} Still on the watchlist ({b1['quarters_on_watchlist']} quarters)."),
        (4, CO, "status", "2026-07-05T14:00:00Z",
         "Status changed from open to in review. Sent to the Risk Manager with the committee pack."),
    ]
    for nid, author, kind, at, body in notes:
        ins("INSERT OR IGNORE INTO investigation_notes(id, investigation_id, author_id, body, kind, created_at, demo) "
            "VALUES(?,?,?,?,?,?,1)", (nid, INV_ID, author, body, kind, at))

    # ------------------------------------------------------------------ project
    ins("INSERT OR IGNORE INTO projects(id, name, description, owner_id, status, due_at, period, members, links, "
        "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
        (PROJECT_ID, "Q2 2026 committee pack",
         f"Everything the Q2 2026 credit committee needs on the corporate book at {P1}: the Early Warning summary, "
         "the Borrower 360 reviews and a What-If downgrade scenario, assembled into the committee pack.",
         RM, "active", "2026-07-09", P1, _j([RM, CO, ANNE]), _j([EWS_LINK, B360_LINK, WHATIF_LINK]),
         "2026-07-02T08:00:00Z", "2026-07-07T09:00:00Z"))
    tasks = [
        (1, "Early Warning summary",
         f"Construction sector view on the corporate book at {P1} (rule set {b1['ews_ruleset']}): summarise for the "
         "pack.", "done", CO, EWS_LINK),
        (2, "Borrower 360 reviews", f"CB01045 {b1['name']}. {borrower_sentence(b1)}", "in_progress", CO, B360_LINK),
        (3, "What-If downgrade scenario",
         "Corporate book, rating scenario: one-notch downgrade, with the ECL, stage and capital impact for the "
         "committee.", "todo", RM, WHATIF_LINK),
        (4, "Construction ECL investigation", inv_summary, "in_progress", CO, INV_LINK),
        (5, "Draft the committee pack", "Assemble the sections and circulate for review.", "in_progress", RM,
         DOC_PACK_LINK),
        (6, "UAT walk-through", "Walk every link in the pack and confirm each opens the right view.", "todo", ANNE,
         {"label": "My workspace", "href": "/workspace", "type": "workspace"}),
    ]
    for pos, title, detail, status, who, link in tasks:
        ins("INSERT OR IGNORE INTO project_items(id, project_id, position, title, detail, kind, status, assignee_id, "
            "href, link_label, demo) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
            (pos, PROJECT_ID, pos, title, detail, "task", status, who, link["href"], link["label"]))

    # ----------------------------------------------------------------- analyses
    # Saved analyses, investigation threads and the S3-2 projects: backend.workspace_v5.seed_r3 (after the inbox).

    # ---------------------------------------------------------------- documents
    pack_sections = [
        {"heading": "Purpose",
         "body": "Draft for the Q2 2026 credit committee. Every figure is quoted "
                 f"from the v5 corporate book at {P1} ({paths.CORP_BOOK}; Early Warning release {paths.EWS_CORP})."},
        {"heading": "Portfolio overview",
         "body": f"Corporate book EAD {mn(t1['ead'])} ({bn(t1['ead'])}) and ECL {mn(t1['ecl'])} at {P1}, against "
                 f"EAD {mn(t0['ead'])} and ECL {mn(t0['ecl'])} at {P0}. {SECTOR} is the largest sector: "
                 f"{mn(s1['ead'])} EAD, {pct(share)} of the book."},
        {"heading": "Early Warning summary",
         "body": f"{SECTOR} ECL rose from {mn(s0['ecl'])} at {P0} to {mn(s1['ecl'])} at {P1} (+{mn(d_ecl)}) on "
                 f"broadly flat EAD ({mn(s0['ead'])} → {mn(s1['ead'])}); coverage {pct(s0['coverage_pct'], 2)} → "
                 f"{pct(s1['coverage_pct'], 2)}. Stage 3 ECL {mn(st[3]['ecl_before'])} → {mn(st[3]['ecl_after'])}. "
                 "See the Construction investigation and the Early Warning sector view."},
        {"heading": "Borrower 360 reviews",
         "body": f"CB01045 {b1['name']} ({b1['sector']} · {b1['sub_sector']}; group {b1['group_name']}). "
                 f"{borrower_sentence(b1)} Exposure was {mn(b0['exposure'])} at {P0}. Outlook "
                 f"{b1['rating_outlook']}; on the watchlist for {b1['quarters_on_watchlist']} quarters."},
        {"heading": "What-If: one-notch downgrade",
         "body": "To be run on the corporate book with the What-If rating scenario: the ECL, stage and capital "
                 "impact of a one-notch downgrade. No figures yet; this section is filled in when the scenario "
                 "has been run."},
        {"heading": "Recommendations (draft)",
         "body": f"1. Note the {SECTOR} ECL rise and keep the sector under monthly review.\n"
                 f"2. Retain CB01045 on the watchlist despite the upgrade (outlook {b1['rating_outlook']}).\n"
                 "3. Take the What-If downgrade result to the committee before the limits review."},
    ]
    ins("INSERT OR IGNORE INTO documents(id, title, kind, status, owner_id, project_id, summary, sections, links, "
        "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
        (DOC_PACK, "Q2 2026 committee pack (draft)", "Committee pack", "draft", RM, PROJECT_ID,
         f"Draft committee pack for the corporate book at {P1}: portfolio overview, Early Warning summary, "
         "Borrower 360 reviews and the What-If downgrade scenario.", _j(pack_sections),
         _j([EWS_LINK, B360_LINK, WHATIF_LINK, INV_LINK, PROJECT_LINK]), "2026-07-06T16:00:00Z",
         "2026-07-07T08:30:00Z"))
    memo_sections = [
        {"heading": "Borrower",
         "body": f"CB01045 {b1['name']}: {b1['sector']} · {b1['sub_sector']}; group {b1['group_name']}."},
        {"heading": "Exposure and ECL",
         "body": f"Exposure (EAD) {mn(b1['exposure'])} at {P1} across {b1['facilities']} facilities "
                 f"({', '.join(b1['facility_ids'])}), against {mn(b0['exposure'])} across {b0['facilities']} at "
                 f"{P0}. ECL {mn(b1['ecl'], 2)} at {P1}."},
        {"heading": "Rating",
         "body": f"Upgraded {b1['rating_previous']} → {b1['rating']} at {P1}, after a downgrade "
                 f"{b0['rating_previous']} → {b0['rating']} at {P0}. Outlook {b1['rating_outlook']}."},
        {"heading": "Financials",
         "body": f"Leverage {b1['leverage_x']:.2f}x at {P1} ({b0['leverage_x']:.2f}x at {P0}); DSCR "
                 f"{b1['dscr_x']:.2f}x ({b0['dscr_x']:.2f}x)."},
        {"heading": "Early Warning",
         "body": f"The Early Warning rule set {b1['ews_ruleset']} scores it {b1['ews_band']} (score "
                 f"{b1['ews_score']}) at {P1}."},
        {"heading": "Recommendation (draft)",
         "body": "Maintain limits. Retain on the watchlist until the outlook improves; review again at 2026Q3, "
                 "after the What-If downgrade scenario has been run."},
    ]
    ins("INSERT OR IGNORE INTO documents(id, title, kind, status, owner_id, project_id, summary, sections, links, "
        "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
        (DOC_MEMO, "Credit memo: Rabigh Continental Contracting (CB01045)", "Credit memo", "in_review", CO, PROJECT_ID,
         f"Annual-style review of CB01045 at {P1}. {borrower_sentence(b1)}", _j(memo_sections),
         _j([B360_LINK, EWS_LINK, WHATIF_LINK]), "2026-07-06T12:00:00Z", "2026-07-07T09:15:00Z"))

    # -------------------------------------------------------------------- inbox
    release = (f"Corporate release {paths.EWS_CORP} now covers {P1} (rule set {b1['ews_ruleset']}). "
               f"{SECTOR} ECL {mn(s1['ecl'])} at {P1}.")
    items = [
        (1, CO, "mention", f"{NAME[RM]} mentioned you in “Construction ECL rise, Q2 2026”",
         notes[2][4][:240], f"/investigations/{INV_ID}", RM, "2026-07-04T09:30:00Z", f"investigation:{INV_ID}"),
        (2, CO, "assignment", "Assigned: Borrower 360 reviews (Q2 2026 committee pack)",
         f"CB01045 {b1['name']}. {borrower_sentence(b1)}", f"/projects/{PROJECT_ID}", RM, "2026-07-05T14:00:00Z",
         f"project:{PROJECT_ID}"),
        (3, CO, "notification", f"Early Warning {P1} release published", release, EWS_LINK["href"], None,
         "2026-07-01T06:00:00Z", "early-warning"),
        (4, RM, "assignment", "Assigned: What-If downgrade scenario (Q2 2026 committee pack)",
         "Corporate book, rating scenario: one-notch downgrade.", f"/projects/{PROJECT_ID}", CO,
         "2026-07-05T14:05:00Z", f"project:{PROJECT_ID}"),
        (5, RM, "notification", f"{NAME[CO]} set “Construction ECL rise, Q2 2026” to in review",
         "Sent to the Risk Manager with the committee pack.", f"/investigations/{INV_ID}", CO,
         "2026-07-05T14:00:00Z", f"investigation:{INV_ID}"),
        (6, ANNE, "assignment", "Assigned: UAT walk-through (Q2 2026 committee pack)",
         "Walk every link in the pack and confirm each opens the right view.", f"/projects/{PROJECT_ID}", RM,
         "2026-07-07T09:00:00Z", f"project:{PROJECT_ID}"),
        (7, ANNE, "mention", f"{NAME[CO]} mentioned you in “Credit memo: Rabigh Continental Contracting”",
         "@Anne please check the memo's Borrower 360 and Early Warning links.", f"/documents/{DOC_MEMO}", CO,
         "2026-07-07T09:15:00Z", f"document:{DOC_MEMO}"),
        (8, ANNE, "notification", f"Early Warning {P1} release published", release, EWS_LINK["href"], None,
         "2026-07-01T06:00:00Z", "early-warning"),
    ]
    for iid, uid, kind, title, body, href, actor, at, source in items:
        ins("INSERT OR IGNORE INTO inbox_items(id, user_id, kind, title, body, href, actor_id, created_at, read, demo, "
            "source) VALUES(?,?,?,?,?,?,?,?,0,1,?)", (iid, uid, kind, title, body, href, actor, at, source))

    from backend.workspace_v5 import seed_r3

    seed_r3.apply(con, f)
