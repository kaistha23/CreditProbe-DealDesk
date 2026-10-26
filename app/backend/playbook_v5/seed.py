"""The Playbook and Policy Docs seed: three reports, the two documents moved from the old Documents page, the policy
library (the Corporate and Retail Credit Policy and circular C-2026-03) and the first two versions of the pack.

Deterministic: fixed ids and timestamps, every figure computed from the books by `content` (read-only). Applied
once, on a store that has never been seeded.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.playbook_v5 import circulars, content, policy, store

P1, P0 = content.CORP_PERIOD, content.CORP_PRIOR
KHALID, NOURA, FAISAL, SARA, ABDULLAH, REEM, OMAR = ("khalid.alotaibi", "noura.alharbi", "faisal.alqahtani",
                                                     "sara.aldosari", "abdullah.alzahrani", "reem.alshehri",
                                                     "omar.alghamdi")
CCP, SECTOR_REVIEW, MEMO = "rp_ccp_q2_2026", "rp_construction_review_q2_2026", "rp_memo_cb01312"
MOVED_PACK, MOVED_MEMO = "rp_committee_pack_q2_2026_draft", "rp_memo_cb01045"

ATTN = {"type": "attention-item", "id": "corporate-construction-ecl", "label": "Attention: Construction ECL rise",
        "href": "/?domain=corporate", "summary": "Construction ECL rose most in the book this quarter."}
EWS = {"type": "early-warning-list", "id": "ews-corporate-2026Q2", "label": "Early Warning: corporate book, 2026Q2",
       "href": "/early-warning?domain=corporate&period=2026Q2"}
EWS_CONS = {"type": "early-warning-list", "id": "ews-corporate-construction-2026Q2",
            "label": "Early Warning: Construction, 2026Q2",
            "href": "/early-warning?domain=corporate&segment=Construction&period=2026Q2"}
B360 = {"type": "borrower", "id": "CB01312", "label": "Borrower 360: Al Kharj Gulf Engineering (CB01312)",
        "href": "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2"}
ANALYSIS = {"type": "analysis", "id": "ead-by-sector-2026q2", "label": "Analysis: EAD by sector, 2026Q2",
            "href": "/analyses/ead-by-sector-2026q2"}


def _set(con: sqlite3.Connection, rid: str, sections: list[dict[str, Any]], status: str, history: list[tuple],
         comments: list[tuple], updated: str) -> None:
    con.execute("UPDATE reports SET sections=?, status=? WHERE id=?", (store._j(sections), status, rid))
    for at, who, frm, to, note in history:
        con.execute("INSERT INTO report_history(report_id, at, who, from_status, to_status, note) VALUES(?,?,?,?,?,?)",
                    (rid, at, who, frm, to, note))
        store._snapshot(con, rid, who, "status", f"{store.STATUS_LABEL[frm]} to {store.STATUS_LABEL[to]}")
    for i, (at, who, body, sec_idx) in enumerate(comments):
        con.execute("INSERT INTO report_comments(id, report_id, section_id, at, author, body) VALUES(?,?,?,?,?,?)",
                    (f"cm_{rid}_{i}", rid, sections[sec_idx]["id"] if sec_idx is not None else None, at, who, body))
    con.execute("UPDATE report_versions SET at=? WHERE report_id=? AND at>?", (updated, rid, updated))
    con.execute("UPDATE reports SET updated_at=? WHERE id=?", (updated, rid))


def _sec(title: str, blocks: list[dict[str, Any]], who: str, sid: str, source: dict[str, Any] | None = None,
         at: str = "2026-10-08T09:00:00Z") -> dict[str, Any]:
    s = store.make_section(title, blocks, who, source, section_id=sid)
    s["updated_at"] = at
    for i, b in enumerate(s["blocks"]):
        b["id"] = f"{sid}_b{i}"
    return s


def _thread(con: sqlite3.Connection, rid: str, items: list[tuple]) -> None:
    for i, (at, role, who, text, actions) in enumerate(items):
        con.execute("INSERT INTO thread_messages(id, thread_id, report_id, role, author, at, text, actions, suggestions) "
                    "VALUES(?,?,?,?,?,?,?,?,?)", (f"msg_{rid}_{i}", f"th_{rid}", rid, role, who, at, text,
                                                 store._j(actions), "[]"))


# ----------------------------------------------------------------- reports


def committee_pack(con: sqlite3.Connection) -> None:
    store.create_report(con, ABDULLAH, "Q2 2026 credit committee pack", "credit-committee-pack", "corporate", P1,
                        "2026-10-15", [NOURA, FAISAL], report_id=CCP, at="2026-10-05T07:30:00Z")
    now, before = content.corp_totals(P1), content.corp_totals(P0)
    cons, cons0 = content.corp_totals(P1, "Construction"), content.corp_totals(P0, "Construction")
    port_t, port_b = content.portfolio_section()
    ews_t, ews_b = content.ews_section()
    memo = content.borrower_sections()[0][1]
    shock = cons["ecl"] * 0.30
    exec_text = (f"Corporate ECL rose by **{content.mn_words(now['ecl'] - before['ecl'])}** to "
                 f"{content.mn_words(now['ecl'])} in {P1} ({now['coverage'] * 100:.2f}% coverage), with Construction "
                 f"contributing {content.mn_words(cons['ecl'] - cons0['ecl'])}. Stage 2 is "
                 f"{now['stage2_share'] * 100:.1f}% of EAD. {now['warned_borrowers']} borrowers are on a high or "
                 "critical Early Warning. The committee is asked to note the movement, approve the CB01312 renewal on "
                 "the conditions in the memo, and endorse the construction sector actions.")
    secs = [
        _sec("Executive summary", [{"kind": "paragraph", "text": exec_text},
                                   {"kind": "callout", "tone": "warning", "text": (
                                       "Circular C-2026-03 tightens the SICR triggers from 1 July 2026 (RP-5.1, CP-3.3) "
                                       "and adds a construction sector watch (CP-3.4). Expect further Stage 2 migration "
                                       "at 2026Q3.")}], ABDULLAH, f"{CCP}_s1"),
        _sec(port_t, port_b, ABDULLAH, f"{CCP}_s2", ANALYSIS),
        _sec(ews_t, ews_b, SARA, f"{CCP}_s3", EWS),
        _sec("Borrowers for decision", [*memo, {"kind": "paragraph", "text": (
            "Full credit memo: **CB01312 credit memo** in Playbook (approved by the Head of Credit).")}],
             SARA, f"{CCP}_s4", B360),
        _sec("Scenarios", [{"kind": "paragraph", "text": (
            f"What-If, Delta method: a 30% rise in Construction PDs adds about **{content.mn_words(shock)}** to ECL "
            f"(first-order, on {content.mn_words(cons['ecl'])} of sector ECL). The full decomposition by stage, "
            "rating and borrower is in the What-If thread.")},
            {"kind": "kpis", "items": [
                {"label": "Construction ECL now", "value": content.sar(cons["ecl"]), "format": "sar"},
                {"label": "Under PD +30%", "value": content.sar(cons["ecl"] + shock), "format": "sar",
                 "delta": content.sar(shock), "status": "amber"},
                {"label": "Book ECL under the scenario", "value": content.sar(now["ecl"] + shock), "format": "sar",
                 "delta": content.sar(shock)}]}],
            ABDULLAH, f"{CCP}_s5", {"type": "whatif-scenario", "id": "construction-pd-30",
                                    "label": "What-If: Construction PD +30% (Delta method)",
                                    "href": "/what-if?domain=corporate"}),
        _sec("Recommendations", [{"kind": "bullets", "items": [
            "Note the 2026Q2 ECL movement and the Construction contribution.",
            "Approve the CB01312 renewal at current limits, no new money, on the memo's conditions.",
            "Endorse out-of-cycle re-rating of high and critical Early Warning names (CP-3.2).",
            "Ask Finance to reflect circular C-2026-03 in the 2026Q3 ECL and report the Stage 2 effect.",
        ]}], ABDULLAH, f"{CCP}_s6"),
    ]
    _set(con, CCP, secs, "in_review",
         [("2026-10-09T14:00:00Z", ABDULLAH, "draft", "in_review", "Ready for the Head of Credit and Head of Risk.")],
         [("2026-10-10T08:20:00Z", NOURA, "Please add the CB01312 policy checks to the borrower section.", 3),
          ("2026-10-10T09:05:00Z", FAISAL, "Scenario section: show the book-level ECL under the stress as well.", 4),
          ("2026-10-10T11:40:00Z", ABDULLAH, "Both done in version 9.", None)], "2026-10-10T11:40:00Z")
    _thread(con, CCP, [
        ("2026-10-05T07:31:00Z", "user", ABDULLAH, "Start the Q2 2026 credit committee pack for the corporate book.", []),
        ("2026-10-05T07:31:05Z", "assistant", None,
         "Started from the credit committee pack template with six sections. I drafted the portfolio overview from the "
         "2026Q2 book and imported the Early Warning list.", [{"kind": "section_drafted", "section_id": f"{CCP}_s2",
                                                                "label": "Portfolio overview"}]),
        ("2026-10-09T13:40:00Z", "user", ABDULLAH, "Draft the executive summary.", []),
        ("2026-10-09T13:40:04Z", "assistant", None, "Drafted the executive summary from the sections below.",
         [{"kind": "section_drafted", "section_id": f"{CCP}_s1", "label": "Executive summary"}]),
    ])


def sector_review(con: sqlite3.Connection) -> None:
    store.create_report(con, SARA, "Construction sector review, Q2 2026", "portfolio-review", "corporate", P1,
                        "2026-10-20", [KHALID], report_id=SECTOR_REVIEW, at="2026-10-07T10:00:00Z")
    parts = content.sector_section("Construction")
    srcs = [ATTN, None, ATTN, EWS_CONS, None]
    secs = [_sec(t, b, SARA, f"{SECTOR_REVIEW}_s{i + 1}", srcs[i]) for i, (t, b) in enumerate(parts)]
    _set(con, SECTOR_REVIEW, secs, "draft", [],
         [("2026-10-09T10:15:00Z", KHALID, "Add the What-If construction stress before this goes to review.", 4)],
         "2026-10-09T10:15:00Z")
    _thread(con, SECTOR_REVIEW, [
        ("2026-10-07T10:01:00Z", "user", SARA, "Start a portfolio review of the Construction sector for Q2 2026.", []),
        ("2026-10-07T10:01:06Z", "assistant", None,
         "Started a portfolio review and drafted every section from the 2026Q2 book: the sector summary against "
         "CP-1.3, the sub-sector composition, the credit quality trend and the movements.", []),
        ("2026-10-07T10:05:00Z", "user", SARA, "Import the Construction attention item.", []),
        ("2026-10-07T10:05:03Z", "assistant", None, "Imported the attention item into Credit quality.",
         [{"kind": "imported", "section_id": f"{SECTOR_REVIEW}_s3", "label": "Credit quality"}]),
    ])


def credit_memo(con: sqlite3.Connection) -> None:
    store.create_report(con, SARA, "CB01312 credit memo: Al Kharj Gulf Engineering", "borrower-credit-memo",
                        "corporate", P1, "2026-10-12", [KHALID, NOURA], report_id=MEMO, at="2026-10-06T08:00:00Z")
    parts = content.borrower_sections("CB01312")
    secs = [_sec(t, b, SARA, f"{MEMO}_s{i + 1}", B360 if t in ("Borrower profile", "Facilities and security") else None)
            for i, (t, b) in enumerate(parts)]
    secs.insert(6, _sec("Policy compliance", [
        {"kind": "paragraph", "text": (
            "CB01312 is a construction contractor with DSCR below 1.10x at two consecutive quarter-ends, so it falls under "
            "the **CP-3.4 sector watch** (circular C-2026-03, effective 1 Jul 2026): it stays on the watchlist, is re-rated "
            "out of cycle within 30 days, and any new money needs Head of Credit approval. It is four notches below its "
            "rating at origination, so it is Stage 2 under CP-3.3.")},
        {"kind": "bullets", "items": ["CP-1.1 single obligor and CP-1.2 group limits: within limit.",
                                      "CP-2.1 covenants: DSCR and leverage in breach; waiver needed under CP-2.2.",
                                      "CP-3.4 sector watch: applies (C-2026-03)."]}],
        SARA, f"{MEMO}_s7", {"type": "circular", "id": "pd_circ_c_2026_03",
                             "label": "Circular C-2026-03 (SICR and construction sector watch)",
                             "href": "/policy-docs?doc=pd_circ_c_2026_03"}))
    secs.append(_sec("Conditions", [{"kind": "bullets", "items": [
        "Renewal of the working capital lines at current limits for 12 months; no new money.",
        "DSCR covenant reset to 1.10x for four quarters, then 1.25x (CP-2.2 waiver, Head of Credit).",
        "Quarterly management accounts within 45 days of quarter-end.",
        "Out-of-cycle re-rating after the 2026Q3 accounts (CP-3.4).",
    ]}], SARA, f"{MEMO}_s9"))
    _set(con, MEMO, secs, "approved",
         [("2026-10-08T12:00:00Z", SARA, "draft", "in_review", ""),
          ("2026-10-09T16:30:00Z", NOURA, "in_review", "approved", "Approved on the stated conditions.")],
         [("2026-10-09T09:10:00Z", KHALID, "Conditions read well. Add the CP-2.2 waiver reference.", 7),
          ("2026-10-09T16:29:00Z", NOURA, "Approved. Take it to the committee as a noting item.", None)],
         "2026-10-09T16:30:00Z")
    _thread(con, MEMO, [
        ("2026-10-06T08:00:30Z", "user", SARA, "Draft a credit memo for CB01312.", []),
        ("2026-10-06T08:00:36Z", "assistant", None,
         "Started a borrower credit memo for Al Kharj Gulf Engineering (CB01312) and drafted the profile, financial "
         "analysis, facilities, rating and Early Warning sections from the 2026Q2 book and Borrower 360.", []),
    ])


def moved_documents(con: sqlite3.Connection) -> None:
    """The two documents of the old Documents page (Workspace service), moved here with their text and links."""
    from backend.workspace_v5 import seed as ws_seed
    from backend.workspace_v5 import store as ws_store

    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    mem.executescript(ws_store.SCHEMA)
    ws_seed.apply(mem)
    for doc_id, rid, template, reviewers in ((ws_seed.DOC_PACK, MOVED_PACK, "credit-committee-pack", [NOURA]),
                                             (ws_seed.DOC_MEMO, MOVED_MEMO, "borrower-credit-memo", [KHALID])):
        r = mem.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        sections = [_sec(s["heading"], [{"kind": "paragraph", "text": p} for p in s["body"].split("\n") if p.strip()],
                         r["owner_id"], f"{rid}_s{i + 1}", at=r["updated_at"])
                    for i, s in enumerate(json.loads(r["sections"]))]
        links = json.loads(r["links"])
        if links:
            sections.append(_sec("Links", [{"kind": "bullets", "items": [f"{x['label']}: {x['href']}" for x in links]}],
                                 r["owner_id"], f"{rid}_links", at=r["updated_at"]))
        store.create_report(con, r["owner_id"], r["title"], template, "corporate", P1, None, reviewers,
                            origin="import", sections=sections, report_id=rid, at=r["created_at"])
        hist = [(r["updated_at"], r["owner_id"], "draft", "in_review", "")] if r["status"] == "in_review" else []
        _set(con, rid, sections, r["status"] if r["status"] in store.STATUSES else "draft", hist, [], r["updated_at"])
    mem.close()


# ----------------------------------------------------------- policy library


def policy_library(con: sqlite3.Connection) -> None:
    pack = policy.default_pack()
    for book, ref in (("corporate", "CCP-2026"), ("retail", "RCP-2026")):
        b = pack["books"][book]
        clauses = [{**c, "book": book, "section": s["section"], "section_title": s["title"]}
                   for s in b["sections"] for c in s["clauses"]]
        policy.insert_document(con, {
            "id": f"pd_policy_{book}", "title": b["title"], "kind": "policy", "reference": ref, "book": book,
            "effective_from": b["approved_on"], "approved_by": b["approved_by"],
            "summary": (f"The Bank's {b['title']}, approved by the {b['approved_by']} on {b['approved_on']}; next review "
                        f"{b['next_review']}. {len(clauses)} clauses in {len(b['sections'])} sections. Scope: {b['scope']}"),
            "text": "\n".join(f"{c['clause']} {c['title']}. {c['rule']}" for c in clauses), "clauses": clauses},
            ABDULLAH, "reference", at=f"{b['approved_on']}T09:00:00Z")
    c = circulars.C_2026_03
    text = "\n".join([c["title"], c["purpose"], *[f"{x['clause']} {x['title']}\n{x['rule']}" for x in c["clauses"]],
                      c["transitional"]])
    policy.insert_document(con, {"id": c["id"], "title": c["title"], "kind": "circular", "reference": c["reference"],
                                 "book": "both", "effective_from": c["effective_from"], "approved_by": c["approved_by"],
                                 "summary": c["summary"], "text": text, "clauses": c["clauses"]},
                           ABDULLAH, "active", at=f"{c['issued']}T10:00:00Z")
    interp, _ = policy.interpret_against(policy.default_pack(), text, [], c["title"])
    con.execute("UPDATE policy_documents SET interpretation=?, decided_at=?, decided_by=?, decision_note=? WHERE id=?",
                (store._j(interp), "2026-06-12T09:00:00Z", NOURA, "Added to the Cockpit from 1 July 2026.", c["id"]))
    con.execute("INSERT INTO policy_pack_versions(version, label, created_at, created_by, effective_from, approved_by, "
                "change, documents, pack, active) VALUES(1,?,?,?,?,?,?,?,?,0)",
                ("pp-2026.1", "2026-01-22T09:00:00Z", ABDULLAH, "2026-01-22", NOURA,
                 "Board-approved Corporate and Retail Credit Policy (CCP-2026, RCP-2026)", "[]",
                 store._j(policy.build_pack(con, [], "pp-2026.1"))))
    con.execute("INSERT INTO policy_pack_versions(version, label, created_at, created_by, effective_from, approved_by, "
                "change, documents, pack, active) VALUES(2,?,?,?,?,?,?,?,?,1)",
                ("pp-2026.2", "2026-06-12T09:00:00Z", NOURA, c["effective_from"], NOURA,
                 f"Added {c['reference']} (SICR triggers, construction sector watch)", store._j([c["id"]]),
                 store._j(policy.build_pack(con, [c["id"]], "pp-2026.2"))))
    policy_files(con)


def policy_files(con: sqlite3.Connection) -> None:
    """The Word and PDF of each policy and of the circular, generated in the house style."""
    try:
        from backend.playbook_v5 import policy_document as pdoc
    except Exception:  # noqa: BLE001 - the library still lists the documents and their clauses
        return
    pack = policy.default_pack()
    pack["pack_version"] = "pp-2026.1"
    for book, ref in (("corporate", "CCP-2026"), ("retail", "RCP-2026")):
        for ext, fn, ctype in (("docx", pdoc.policy_docx, policy._ctype("x.docx")),
                               ("pdf", pdoc.policy_pdf, "application/pdf")):
            store.save_file(con, ABDULLAH, "policy", f"pd_policy_{book}", f"{ref} {pack['books'][book]['title']}.{ext}",
                            ctype, fn(pack, book), at="2026-01-22T09:00:00Z")
    c = circulars.C_2026_03
    for ext, fn, ctype in (("docx", pdoc.circular_docx, policy._ctype("x.docx")),
                           ("pdf", pdoc.circular_pdf, "application/pdf")):
        store.save_file(con, ABDULLAH, "policy", c["id"], f"{c['reference']} SICR and construction sector watch.{ext}",
                        ctype, fn(c), at=f"{c['issued']}T10:00:00Z")


BM1230 = Path(__file__).resolve().parent / "data" / "bm1230.json"


def ensure_bm1230(con: sqlite3.Connection) -> bool:
    """CBO circular BM-1230's annexure as an active Regulatory document, in a new pack version (R6 policy, P2).

    Idempotent and additive: an existing store keeps its documents and versions; the regulation is added once, and
    a regulation someone has withdrawn stays withdrawn. Returns True when it added something.
    """
    data = json.loads(BM1230.read_text(encoding="utf-8"))
    row = con.execute("SELECT status FROM policy_documents WHERE id=?", (data["id"],)).fetchone()
    added = False
    if row is None:
        meta = {"issuer": data["issuer"], "jurisdiction": data["jurisdiction"], "category": data["category"],
                "source_file": data["source_file"], "method": "seed", "question": None,
                "summary": f"{data['issuer']} circular {data['reference']}, annexure: {data['title']}."}
        text = "\n".join(f"{c['clause']} {c['title']}. {c['rule']}" for c in data["clauses"])
        policy.insert_document(con, {
            "id": data["id"], "title": data["title"], "kind": "regulation", "reference": data["reference"],
            "book": "both", "effective_from": data["effective_from"], "approved_by": NOURA,
            "summary": (f"Regulatory (Oman). {data['issuer']}, circular {data['reference']}: the Credit Management "
                        f"Prudential Framework, {len(data['clauses'])} paragraphs on regulatory default, SICR, the loan "
                        "review mechanism, restructuring/rescheduling, classification and ECL provisioning, and "
                        "write-off. Effective " + data["effective_from"] + "."),
            "text": text, "clauses": data["clauses"]}, ABDULLAH, "active", meta, at=f"{data['effective_from']}T08:00:00Z")
        pdf = Path(__file__).resolve().parents[2] / data["source_file"]
        if pdf.is_file():
            store.save_file(con, ABDULLAH, "policy", data["id"], pdf.name, "application/pdf", pdf.read_bytes(),
                            at=f"{data['effective_from']}T08:00:00Z")
        added = True
    elif row["status"] != "active":
        return False
    try:
        current = store._l(policy.active_version(con)["documents"], [])
    except store.NotFound:
        return added
    if data["id"] not in current:
        policy.new_version(con, NOURA, [*current, data["id"]],
                           f"Added {data['issuer']} circular {data['reference']} (Credit Management – Prudential "
                           "Framework, Regulatory, Oman)", data["effective_from"], NOURA)
        added = True
    return added


CBUAE_CRM = Path(__file__).resolve().parent / "data" / "cbuae_crm.json"
BM1230_ID = "pd_cbo_bm1230"
CBUAE_CRM_ID = "pd_cbuae_crm"
#: When the swap was recorded in the seed (R7, PLAN_R7 C1, 12 Oct 2026).
R7_AT = "2026-10-12T13:00:00Z"
R7_EFFECTIVE = "2026-10-12"


def ensure_cbuae_crm(con: sqlite3.Connection) -> bool:
    """The CBUAE Credit Risk Management Standards as the active Regulatory document, and CBO BM-1230 withdrawn from
    the active pack (R7, Session C, C1). One new pack version does both.

    Idempotent and additive: the Standards are inserted once; BM-1230 stays in the library as Withdrawn, with its
    pack history (the versions that held it stay on record); a Standards document someone has withdrawn stays
    withdrawn; a BM-1230 someone re-adds later is not withdrawn again (the swap runs once, when it inserts the
    Standards). Returns True when it changed something.
    """
    data = json.loads(CBUAE_CRM.read_text(encoding="utf-8"))
    row = con.execute("SELECT status FROM policy_documents WHERE id=?", (data["id"],)).fetchone()
    if row is not None:
        if row["status"] != "active":
            return False
        try:
            current = store._l(policy.active_version(con)["documents"], [])
        except store.NotFound:
            return False
        if data["id"] in current:
            return False
        policy.new_version(con, NOURA, [*current, data["id"]],
                           "Added the CBUAE Credit Risk Management Standards (Regulatory, UAE)", R7_EFFECTIVE, NOURA)
        return True
    meta = {"issuer": data["issuer"], "jurisdiction": data["jurisdiction"], "category": data["category"],
            "source_file": data["source_file"], "method": "seed", "question": None,
            "summary": f"{data['issuer']}: {data['title']}, Articles 1-13."}
    text = "\n".join(f"{c['clause']} {c['title']}. {c['rule']}" for c in data["clauses"])
    policy.insert_document(con, {
        "id": data["id"], "title": data["title"], "kind": "regulation", "reference": data["reference"],
        "book": "both", "effective_from": R7_EFFECTIVE, "approved_by": NOURA,
        "summary": (f"Regulatory (UAE). {data['issuer']}, {data['title']}: {len(data['clauses'])} paragraphs in "
                    "Articles 1-13 on credit risk governance, the framework, oversight functions, underwriting, the "
                    "definition of default, SICR, restructuring, classification and provisioning, credit risk "
                    "mitigation, portfolio management and reporting, non-performing assets and write-off, and models. "
                    f"Effective {R7_EFFECTIVE}; replaces CBO BM-1230 in the active pack."),
        "text": text, "clauses": data["clauses"]}, ABDULLAH, "active", meta, at=R7_AT)
    pdf = Path(__file__).resolve().parents[2] / data["source_file"]
    if pdf.is_file():
        store.save_file(con, ABDULLAH, "policy", data["id"], pdf.name, "application/pdf", pdf.read_bytes(), at=R7_AT)
    try:
        current = store._l(policy.active_version(con)["documents"], [])
    except store.NotFound:
        return True
    bm = con.execute("SELECT status FROM policy_documents WHERE id=?", (BM1230_ID,)).fetchone()
    change = "Added the CBUAE Credit Risk Management Standards (Regulatory, UAE)"
    if bm is not None and bm["status"] == "active":
        con.execute("UPDATE policy_documents SET status='withdrawn', decided_at=?, decided_by=?, decision_note=? "
                    "WHERE id=?", (R7_AT, NOURA, "Withdrawn: CBO BM-1230 is not in force for the Bank. Replaced in the "
                                   "active pack by the CBUAE Credit Risk Management Standards.", BM1230_ID))
        change = ("Withdrew CBO circular BM-1230 (not in force); added the CBUAE Credit Risk Management Standards "
                  "(Regulatory, UAE)")
    docs = [d for d in current if d != BM1230_ID] + [data["id"]]
    policy.new_version(con, NOURA, docs, change, R7_EFFECTIVE, NOURA, at=R7_AT)
    return True


def apply(con: sqlite3.Connection) -> None:
    policy_library(con)
    ensure_bm1230(con)
    ensure_cbuae_crm(con)
    committee_pack(con)
    sector_review(con)
    credit_memo(con)
    moved_documents(con)


# ------------------------------------------------------- Deal Desk edition

DD06_PAPER = "rp_dd06_committee_paper"
DD06 = {"type": "dealdesk-proposal", "id": "DD-06", "label": "Deal Desk: DD-06 Dhahran Continental Industries",
        "href": "/deal-desk/DD-06"}


def dd06_committee_paper(con: sqlite3.Connection) -> None:
    """The Deal Desk edition's one seeded report: the DD-06 counter-offer as a committee paper, in review."""
    store.create_report(con, KHALID, "DD-06 committee paper (draft)", "committee-paper", "corporate", "2026Q2",
                        "2026-10-29", [ABDULLAH], report_id=DD06_PAPER, at="2026-10-20T09:30:00Z")
    at = "2026-10-22T14:10:00Z"
    secs = [
        _sec("Decision sought", [{"kind": "paragraph", "text": (
            "Approval of a **SAR 25.0m** revolving working capital Murabaha for Dhahran Continental Industries (DD-06; "
            "Manufacturing, rated BB+) over 3 years, on the counter-offer structure: SAIBOR + 190 bps, commitment fee 30 bps, "
            "30% cash margin lien-marked. Approval level per the Delegation of Authority: Head of Credit.")}],
             KHALID, f"{DD06_PAPER}_s1", DD06, at),
        _sec("Structure and economics", [
            {"kind": "paragraph", "text": (
                "The ask (SAIBOR + 190 bps, 25 bps commitment fee, no cash margin) prices at lifetime RAROC 10.3% against the "
                "15.0% hurdle. The counter-offer keeps the margin and adds a 30% cash margin and a 30 bps commitment fee: "
                "lifetime RAROC **15.0%** against the **15.0%** hurdle, SVA nil.")},
            {"kind": "kpis", "items": [
                {"label": "Amount", "value": 25_000_000, "format": "sar"},
                {"label": "Margin", "value": 190, "format": "bps"},
                {"label": "Commitment fee", "value": 30, "format": "bps"},
                {"label": "Lifetime RAROC", "value": 0.15, "format": "pct", "status": "amber"},
                {"label": "Hurdle", "value": 0.15, "format": "pct"}]}],
             KHALID, f"{DD06_PAPER}_s2", DD06, at),
        _sec("Risks and mitigants", [{"kind": "bullets", "items": [
            "Exposure after the deal SAR 43.4m (existing SAR 18.4m and the new SAR 25.0m limit): above the SAR 25.0m row, so "
            "the Head of Credit decides.",
            "Pricing at the hurdle, not above it: the cash margin carries the economics; a lower utilisation lowers the fee "
            "income, not the RAROC.",
            "Rating BB+ against a BB- row minimum: within policy.",
        ]}], KHALID, f"{DD06_PAPER}_s3", None, at),
        _sec("Conditions", [{"kind": "bullets", "items": [
            "Cash margin of 30% of the limit held in a lien-marked account before the first drawdown.",
            "Quarterly management accounts within 45 days of quarter-end; audited accounts within 120 days.",
            "Utilisation reviewed at six months; the 30 bps commitment fee on the undrawn limit.",
        ]}], KHALID, f"{DD06_PAPER}_s4", None, at),
    ]
    _set(con, DD06_PAPER, secs, "in_review",
         [("2026-10-22T14:10:00Z", KHALID, "draft", "in_review", "For the Risk Manager before the 29 Oct committee.")],
         [("2026-10-22T16:00:00Z", ABDULLAH, "Confirm with Treasury that the cash margin is lien-marked cash, not "
                                              "relationship balances, before this goes to the Head of Credit.", 3)],
         "2026-10-22T16:00:00Z")
    _thread(con, DD06_PAPER, [
        ("2026-10-20T09:30:30Z", "user", KHALID, "Draft the committee paper for DD-06 on the counter-offer.", []),
        ("2026-10-20T09:30:36Z", "assistant", None,
         "Started a committee paper for DD-06 Dhahran Continental Industries and drafted the decision sought and the "
         "structure and economics from the deal's analysis (the ask against the recommended structure).",
         [{"kind": "section_drafted", "section_id": f"{DD06_PAPER}_s2", "label": "Structure and economics"}]),
    ])


def apply_dealdesk(con: sqlite3.Connection) -> None:
    """The Deal Desk edition's seed: the policy library and its files exactly as the full product's, and the DD-06
    committee paper. Not the Cockpit's reports and not `moved_documents` (it rebuilds the Cockpit documents)."""
    policy_library(con)
    ensure_bm1230(con)
    ensure_cbuae_crm(con)
    dd06_committee_paper(con)
