"""Seeded mail of the Deal Desk edition (seed mail-2-dd): eight threads and one draft, all about deals.

Credit's queries on DD-02, the committee calendar for 29 Oct 2026, the DD-06 counter-offer, the conditions overdue on
DD-07, the credit response on R16-C2, a policy circular on construction exposure, the welcome thread and R16-C1's
business request. Objects attached are Deal Desk proposals, a project, documents. No Early Warning, What-If, Borrower
360 or Cockpit anywhere. Deterministic: fixed ids and timestamps; applied once per SEED_VERSION_DEALDESK.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.mail_v5 import store
from backend.identity_v5 import directory
from backend.mail_v5.seed import _file, _obj, _p, _when

ANNE, FAISAL, NOURA, KHALID, REEM, ABDULLAH, SARA, OMAR, LAMA = (
    "anne", "faisal.alqahtani", "noura.alharbi", "khalid.alotaibi", "reem.alshehri", "abdullah.alzahrani",
    "sara.aldosari", "omar.alghamdi", "lama.almutairi")
NAWAF, ABEER, HIND = "nawaf.alotaibi", "abeer.alomari", "hind.alsubaie"

COMMITTEE = "29 Oct 2026"
P3 = "credit-committee-2026-10-29"

_NAMES = {u["username"]: u["name"] for u in directory.seed_users()}


def _name(u: str) -> str:
    return _NAMES.get(u, u)


LABELS = (("Deals", "#2563eb"), ("Committee", "#7c3aed"), ("Conditions", "#d97706"), ("Credit queries", "#dc2626"),
          ("Policy", "#0d9488"))


def _deals() -> dict[str, dict[str, Any]]:
    """The deals the threads name, from Deal Desk's registry; a fixed table when it cannot be read."""
    out: dict[str, dict[str, Any]] = {
        "DD-02": {"obligor_name": "Taif Central Engineering", "sector": "Construction", "rating": "BB", "amount_sar_mn": 16.0},
        "DD-06": {"obligor_name": "Dhahran Continental Industries", "sector": "Manufacturing", "rating": "BB+", "amount_sar_mn": 25.0},
        "DD-07": {"obligor_name": "Unayzah Trading", "sector": "Wholesale Trade", "rating": "BBB-", "amount_sar_mn": 12.0},
        "R12-TWA": {"obligor_name": "Al Sahel Building Materials Trading LLC", "sector": "Wholesale Trade", "rating": "BB",
                    "amount_sar_mn": 170.0},
        "R16-C1": {"obligor_name": "Dar Al Naseem Medical Supplies Co.", "sector": "Wholesale Trade", "rating": "BBB", "amount_sar_mn": 30.0},
        "R16-C2": {"obligor_name": "Sawaed Al Bina Contracting Co.", "sector": "Construction", "rating": "BB+", "amount_sar_mn": 45.0},
        "PL-10": {"obligor_name": "Al Madinah Specialist Hospital Company", "sector": "Healthcare", "rating": "A", "amount_sar_mn": 120.0},
        "PL-22": {"obligor_name": "Al Faisaliah Contracting", "sector": "Construction", "rating": "BBB-", "amount_sar_mn": 35.0},
    }
    try:
        from backend.dealdesk import proposals, registry_lookup
        for d in registry_lookup.all_deals():
            pid = d.get("proposal_id")
            if pid in out:
                s = proposals.summary(d)
                out[pid].update({k: s[k] for k in ("obligor_name", "sector", "rating", "amount_sar_mn") if s.get(k) is not None})
    except Exception:  # noqa: BLE001 - Deal Desk's registry; the seed still reads
        pass
    return out


def _m(x: float) -> str:
    return f"SAR {x:,.1f}m"


def apply(con: sqlite3.Connection) -> None:
    # Re-seeding replaces the previous seed's rows (only rows with a seed id), never a user's own mail.
    for r in con.execute("SELECT seq FROM mail_messages WHERE id LIKE 'm_seed_%'").fetchall():
        for t in ("mail_recipients", "mail_attachments"):
            con.execute(f"DELETE FROM {t} WHERE message_seq=?", (r["seq"],))
    con.execute("DELETE FROM mail_messages WHERE id LIKE 'm_seed_%'")
    con.execute("DELETE FROM mail_threads WHERE id LIKE 't_seed_%'")
    con.execute("DELETE FROM mail_state WHERE thread_id LIKE 't_seed_%'")
    con.execute("DELETE FROM mail_notifications WHERE thread_id LIKE 't_seed_%'")

    d = _deals()
    dd02, dd06, dd07, twa, c1, c2 = d["DD-02"], d["DD-06"], d["DD-07"], d["R12-TWA"], d["R16-C1"], d["R16-C2"]

    def prop(pid: str, summary: str, href: str | None = None) -> dict[str, Any]:
        x = d[pid]
        return _obj("dealdesk-proposal", pid, f"{pid} {x['obligor_name']}", href or f"/deal-desk/{pid}", summary,
                    sector=x["sector"], rating=x["rating"], amount_sar_mn=x["amount_sar_mn"])

    O_DD02 = prop("DD-02", f"{dd02['sector']}, {dd02['rating']}, {_m(dd02['amount_sar_mn'])} term loan, 6 years; in review.")
    O_DD06 = prop("DD-06", f"{dd06['sector']}, {dd06['rating']}, {_m(dd06['amount_sar_mn'])} revolving Murabaha, 3 years; "
                  "counter-offer: SAIBOR + 190 bps, commitment fee 30 bps, 30% cash margin, RAROC 15.0% vs 15.0% hurdle.")
    O_DD07 = prop("DD-07", f"{dd07['sector']}, {dd07['rating']}; approved; 2 conditions overdue since 15 Oct.",
                  "/deal-desk/review?view=conditions")
    O_C1 = prop("R16-C1", f"{c1['sector']}, {c1['rating']}, {_m(c1['amount_sar_mn'])}; approved. The RM's business request.")
    O_P3 = _obj("project", P3, "Project: Credit committee 29 Oct 2026", f"/projects/{P3}",
                "Four deals: R12-TWA, DD-06, PL-10, PL-22. One paper per deal, due 29 Oct.")
    O_C2_RESPONSE = _obj("document", "r16-c2-credit-response", f"Credit response: R16-C2 {c2['obligor_name']}",
                         "/deal-desk/R16-C2", f"Approved at {_m(c2['amount_sar_mn'])} on the recommended structure, with conditions.")
    O_CIRCULAR = _obj("document", "pd_circ_construction_exposure", "Circular: construction sector exposure (Oct 2026)",
                      "/policy-docs", "Construction exposure to stay within 13% of the corporate book; new names above "
                      "SAR 25m need Head of Credit approval.")
    F_QUERIES = _file(con, "f_seed_dd02_queries", "DD-02 Credit queries.txt", "text/plain", NOURA,
                      f"Credit queries on DD-02 {dd02['obligor_name']} ({_m(dd02['amount_sar_mn'])} term loan)\n"
                      "Raised: 20 Oct 2026. Answers due: 27 Oct 2026.\n\n"
                      "Q1. Receivables ageing on the two government contracts, by bucket, at 30 Sep 2026.\n"
                      "Q2. The guarantor's net worth statement, signed, with the supporting valuations.\n"
                      "Q3. The use of the SAR 4.0m retention release: working capital or distribution?\n")

    threads: list[dict[str, Any]] = [
        {"id": "t_seed_dd02_queries", "subject": f"DD-02 {dd02['obligor_name']}: Credit's 3 queries",
         "kind": "share", "labels": {SARA: ["Credit queries", "Deals"], NOURA: ["Credit queries"]}, "starred": {SARA},
         "messages": [
             (NOURA, [SARA], [KHALID], "2026-10-20T07:50:00Z",
              f"Sara,\n\nCredit has read the request on DD-02 {dd02['obligor_name']} ({dd02['sector']}, {dd02['rating']}, "
              f"{_m(dd02['amount_sar_mn'])} term loan over 6 years). Three queries before the review on 27 Oct: the receivables "
              "ageing on the two government contracts; the guarantor's net worth statement with its valuations; and what the "
              "SAR 4.0m retention release is used for.\n\nThe queries are attached and the deal is linked.", [O_DD02],
              {"files": [F_QUERIES]}),
             (SARA, [NOURA], [KHALID], "2026-10-20T10:15:00Z",
              "Noura,\n\nThe ageing is with the RM today. The guarantor's statement is signed but the valuations are from 2024; "
              "I have asked for an update. On the retention release the customer says working capital; I will get it in "
              "writing.", []),
             (KHALID, [SARA, NOURA], [], "2026-10-21T06:40:00Z",
              "Sara, add the answers to the project as you get them so the review on 27 Oct has them in one place. The "
              "optimised counter-offer (20% lien-marked cash deposit, RAROC 16.5%) stands whatever the answers say.", []),
         ], "read": {NOURA: 3, SARA: 3, KHALID: 3}},
        {"id": "t_seed_committee_calendar", "subject": f"Credit committee {COMMITTEE}: agenda and papers",
         "kind": "share", "labels": {ABDULLAH: ["Committee"], NOURA: ["Committee"], FAISAL: ["Committee"], KHALID: ["Committee"]},
         "starred": {ABDULLAH},
         "messages": [
             (ABDULLAH, [KHALID, SARA, NOURA, FAISAL], [ANNE], "2026-10-16T10:00:00Z",
              f"Colleagues,\n\nFour deals go to the credit committee on {COMMITTEE}: R12-TWA {twa['obligor_name']} "
              f"({_m(twa['amount_sar_mn'])}), DD-06 {dd06['obligor_name']} ({_m(dd06['amount_sar_mn'])}), PL-10 "
              f"{d['PL-10']['obligor_name']} ({_m(d['PL-10']['amount_sar_mn'])}) and PL-22 {d['PL-22']['obligor_name']} "
              f"({_m(d['PL-22']['amount_sar_mn'])}). One paper per deal, on the engine's recommended structure, in Playbook by "
              "27 Oct. The project holds the tasks.", [O_P3]),
             (KHALID, [ABDULLAH], [NOURA], "2026-10-16T12:20:00Z",
              "DD-06 and PL-10 are mine. The DD-06 paper follows the counter-offer; PL-10 is a new name at A, so the paper is "
              "short.", []),
             (NOURA, [ABDULLAH, KHALID, SARA], [FAISAL], "2026-10-17T08:05:00Z",
              "R12-TWA is the one to watch: SAR 170m to a trading name at BB. Abdullah, please put the twin-deal comparison in "
              "the paper.", []),
         ], "read": {ABDULLAH: 3, KHALID: 3, NOURA: 3, SARA: 1, FAISAL: 0, ANNE: 0}},
        {"id": "t_seed_dd06_counter", "subject": f"DD-06 {dd06['obligor_name']}: counter-offer",
         "kind": "share", "labels": {KHALID: ["Deals"], SARA: ["Deals"]}, "starred": {KHALID},
         "messages": [
             (KHALID, [SARA, ABDULLAH], [NOURA], "2026-10-20T08:45:00Z",
              f"Sara, Abdullah,\n\nThe counter-offer on DD-06 {dd06['obligor_name']} ({dd06['sector']}, {dd06['rating']}): "
              f"{_m(dd06['amount_sar_mn'])} revolving working capital Murabaha over 3 years at SAIBOR + 190 bps, commitment fee 30 "
              "bps, 30% cash margin lien-marked. Lifetime RAROC 15.0% against the 15.0% hurdle; approval sits with the Head of "
              "Credit. The ask (no cash margin, 25 bps fee) was at 10.3%.\n\nThe deal is linked. I take it to the customer "
              "on Thursday.", [O_DD06]),
             (ABDULLAH, [KHALID], [SARA, NOURA], "2026-10-20T11:00:00Z",
              "Khalid, the 30% cash margin is the deposit condition Treasury asked about. Please confirm it is lien-marked "
              "cash, not relationship balances, before the committee paper says so.", []),
             (SARA, [KHALID, ABDULLAH], [], "2026-10-21T09:10:00Z",
              "Confirmed with Treasury: a lien-marked cash margin account, opened before drawdown. I have put it on the "
              "project as a task for Khalid to confirm with the customer.", []),
         ], "read": {KHALID: 2, ABDULLAH: 3, SARA: 3, NOURA: 1}},
        {"id": "t_seed_dd07_conditions", "subject": f"DD-07 {dd07['obligor_name']}: 2 conditions overdue",
         "kind": "share", "labels": {NOURA: ["Conditions"], SARA: ["Conditions"]}, "starred": set(),
         "messages": [
             (NOURA, [SARA], [KHALID], "2026-10-21T06:00:00Z",
              f"Sara,\n\nDD-07 {dd07['obligor_name']} was approved with four conditions. Two are overdue since 15 Oct: the "
              "insurance schedule and the assignment of receivables. Please chase the RM and tell me by Thursday whether the "
              "line stays available.", [O_DD07]),
             (SARA, [NOURA], [KHALID], "2026-10-21T08:30:00Z",
              "The RM has the insurance schedule and files it today. The assignment of receivables is with the customer's "
              "lawyers; I will set a new date of 28 Oct on the condition and flag it if it slips again.", []),
         ], "read": {NOURA: 2, SARA: 2, KHALID: 0}},
        {"id": "t_seed_r16c2_response", "subject": f"R16-C2 {c2['obligor_name']}: credit response",
         "kind": "share", "labels": {NOURA: ["Deals"], KHALID: ["Deals"]}, "starred": set(),
         "messages": [
             (NOURA, [KHALID, SARA], [ABDULLAH], "2026-10-15T13:20:00Z",
              f"Khalid, Sara,\n\nCredit's response on R16-C2 {c2['obligor_name']} ({c2['sector']}, {c2['rating']}): approved at "
              f"{_m(c2['amount_sar_mn'])} on the recommended structure, with the conditions in the response. The pricing holds "
              "the hurdle; the project receivables are assigned.\n\nThe response document is attached.", [O_C2_RESPONSE]),
             (KHALID, [NOURA], [SARA, ABDULLAH], "2026-10-15T15:05:00Z",
              "Thank you Noura. The RM sends the facility letter this week; conditions tracked on the deal.", []),
         ], "read": {NOURA: 2, KHALID: 2, SARA: 1, ABDULLAH: 1}},
        {"id": "t_seed_construction_circular", "subject": "Circular: construction sector exposure (Oct 2026)",
         "kind": "message", "labels": {FAISAL: ["Policy"], NOURA: ["Policy"], ABDULLAH: ["Policy"]}, "starred": {NOURA},
         "messages": [
             (FAISAL, [NOURA, ABDULLAH], [KHALID, SARA], "2026-10-14T06:30:00Z",
              "Colleagues,\n\nThe circular on construction sector exposure is in Policy Docs. Construction stays within 13% of "
              "the corporate book; a new construction name above SAR 25m needs Head of Credit approval; contractors with more "
              "than half their receivables from one public principal carry a receivables assignment as a standard condition."
              "\n\nPlease tell me which pending deals it touches: PL-22 and R14-RWQ at least.", [O_CIRCULAR]),
             (NOURA, [FAISAL], [ABDULLAH, KHALID, SARA], "2026-10-14T09:10:00Z",
              "PL-22 Al Faisaliah is an existing name, so the approval rule does not bite; the receivables assignment does. "
              "R14-RWQ is new and above SAR 25m: Head of Credit, once its proposal check clears grade C.", []),
         ], "read": {FAISAL: 2, NOURA: 2, ABDULLAH: 1, KHALID: 0, SARA: 0}},
        {"id": "t_seed_welcome", "subject": "CreditProbe Mail is live",
         "kind": "message", "labels": {}, "starred": set(),
         "messages": [
             (ANNE, [FAISAL, NOURA, KHALID, REEM, ABDULLAH, SARA, OMAR, LAMA, NAWAF, ABEER, HIND], [], "2026-10-01T06:00:00Z",
              "Hello all,\n\nCreditProbe Mail is the place to send deals, proposals and committee papers to each other. Use "
              "Share on any deal or analysis, or write a message and attach a Deal Desk object.\n\nAnne", []),
         ], "read": {ANNE: 1, FAISAL: 1, NOURA: 1, KHALID: 1, REEM: 1, ABDULLAH: 1, SARA: 1, OMAR: 1, LAMA: 1, NAWAF: 1,
                     ABEER: 1, HIND: 1}},
        {"id": "t_seed_r16c1_request", "subject": f"R16-C1 {c1['obligor_name']}: business request",
         "kind": "share", "labels": {NAWAF: ["Deals"], SARA: ["Deals"]}, "starred": set(),
         "messages": [
             (NAWAF, [SARA], [KHALID], "2026-10-12T07:15:00Z",
              f"Sara,\n\nThe business request on R16-C1 {c1['obligor_name']} ({c1['sector']}, {c1['rating']}, "
              f"{_m(c1['amount_sar_mn'])}) is on the deal: purpose, group, financials, facilities and security as the customer "
              "gave them. Please read it before Credit does and tell me what is thin.", [O_C1]),
             (SARA, [NAWAF], [KHALID], "2026-10-12T10:40:00Z",
              "Nawaf, the security section needs the valuation date on the warehouse and the insurer's name. The rest reads "
              "well; Credit approved on the structure as asked.", []),
         ], "read": {NAWAF: 2, SARA: 2, KHALID: 1}},
    ]

    for th in threads:
        first_at = th["messages"][0][3]
        con.execute("INSERT INTO mail_threads(id, subject, created_by, created_at, last_at) VALUES(?,?,?,?,?)",
                    (th["id"], th["subject"], th["messages"][0][0], first_at, th["messages"][-1][3]))
        seqs: list[int] = []
        prev: tuple[str, str, str] | None = None
        for i, msg in enumerate(th["messages"], 1):
            sender, to, cc, at, body, objs = msg[:6]
            extra = msg[6] if len(msg) > 6 else {}
            att = [{"kind": "object", "object": o} for o in objs] + [{"kind": "file", "file_id": f} for f in extra.get("files", [])]
            html = _p(body)
            if prev is not None:
                html += (f"<blockquote><p>On {_when(prev[1])} UTC, {_name(prev[0])} wrote:</p>{prev[2]}</blockquote>")
            res = store._insert_message(con, th["id"], sender, to, cc, html,
                                        f"m_seed_{th['id'][7:]}_{i - 1}" if i > 1 else None, att,
                                        kind=th["kind"] if i == 1 else "message", sent_at=at,
                                        mid=f"m_seed_{th['id'][7:]}_{i}", bcc=extra.get("bcc", []))
            seqs.append(res["seq"])
            prev = (sender, at, html)
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

    con.execute("UPDATE mail_state SET archived=1 WHERE thread_id='t_seed_welcome' AND username=?", (ANNE,))
    from backend.mail_v5 import seed as full_seed
    gone = [lab for lab, _c in full_seed.LABELS if lab not in {l for l, _c in LABELS}]   # the full product's labels (Early Warning, What-If, Models…)
    for u in (SARA, KHALID, ABDULLAH, NOURA, FAISAL, REEM, OMAR, LAMA, ANNE, NAWAF, ABEER, HIND):
        for lab in gone:
            con.execute("DELETE FROM mail_labels WHERE owner=? AND name=?", (u, lab))
        for lab, colour in LABELS:
            con.execute("INSERT OR IGNORE INTO mail_labels(owner, name, color) VALUES(?,?,?)", (u, lab, colour))
            con.execute("UPDATE mail_labels SET color=? WHERE owner=? AND name=?", (colour, u, lab))
    con.execute("DELETE FROM mail_drafts WHERE id LIKE 'd_seed_%'")
    con.execute("INSERT INTO mail_drafts(id, owner, data, updated_at) VALUES(?,?,?,?)",
                ("d_seed_khalid", KHALID, json.dumps({
                    "to": [NOURA], "cc": [ABDULLAH], "bcc": [], "subject": f"DD-06 {dd06['obligor_name']}: customer's answer on the counter-offer",
                    "body_html": _p("Noura,\n\nDraft: the customer's answer on the 30% cash margin and the 30 bps commitment "
                                    "fee goes here after Thursday's meeting, with the deal attached."),
                    "attachments": [{"kind": "object", "object": O_DD06}], "mode": "new", "thread_id": None,
                    "in_reply_to": None}), "2026-10-22T14:00:00Z"))
