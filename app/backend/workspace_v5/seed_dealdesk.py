"""The Workspace seed of the Deal Desk edition (PLAN_DEALDESK_EDITION Round C).

The product is Deal Desk, so the Work panels show deals and nothing else: three projects about deals (a counter-offer
going to committee, a credit review, the committee of 29 Oct 2026), two investigations saved from Deal Desk threads,
four analyses that are Deal Desk results, and an inbox of mentions and assignments about those deals. Nothing here
names Early Warning, the Cockpit, What-If, Borrower 360 or an ECL investigation.

Figures: the proposals come from the deal registry (backend.dealdesk), the RAROC figures from the engine computed
in-process at seed time, the sector headroom from the portfolio snapshot relation; when a reader or the engine is
not available the figures Deal Desk itself shows for these deals are written in their place. Fixed ids and
timestamps; every insert is INSERT OR IGNORE, so applying the seed twice changes nothing. Seeded rows carry demo=1.
"""
from __future__ import annotations

import io
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.identity_v5 import directory
from backend.workspace_v5 import store
from backend.workspace_v5.book import mn, pct

USERS = [(u["username"], u["name"], u["role"], u["initials"], u["position"]) for u in directory.seed_users()]

KHALID, SARA, ABDULLAH, NOURA = "khalid.alotaibi", "sara.aldosari", "abdullah.alzahrani", "noura.alharbi"
REEM, FAISAL, ANNE = "reem.alshehri", "faisal.alqahtani", "anne"
NAME = {u[0]: u[1] for u in USERS}

PERIOD = "2026Q2"
COMMITTEE = "2026-10-29"

P1, P2, P3 = "dd-06-counter-offer", "dd-02-credit-review", "credit-committee-2026-10-29"
INV_RE, INV_RWQ = "dd-04-real-estate-headroom", "r14-rwq-proposal-check"
A_DD02, A_DD06, A_HEADROOM, A_BREACHES = ("dd-02-optimised-counter-offer", "dd-06-ask-vs-recommended",
                                          "real-estate-headroom-2026q2", "proposals-breaching-hard-limit")
DOC_DD06 = "pd-dd-06-proposal-bank-form"

#: What Deal Desk shows for these deals; written when the engine or a reader cannot answer at seed time.
FALLBACK: dict[str, Any] = {
    "dd02_ask": {"raroc": 13.0, "hurdle": 16.0, "margin_bps": 240, "tenor_years": 6, "cash_margin_pct": 0},
    "dd02_counter": {"raroc": 16.5, "hurdle": 16.0, "margin_bps": 240, "tenor_years": 6, "cash_margin_pct": 20, "deposit_pct": 20},
    "dd06_ask": {"raroc": 10.3, "hurdle": 15.0, "margin_bps": 190, "commitment_fee_bps": 25, "cash_margin_pct": 0,
                 "approval": "Chief Risk Officer"},
    "dd06_recommended": {"raroc": 15.0, "hurdle": 15.0, "margin_bps": 190, "commitment_fee_bps": 30, "cash_margin_pct": 30,
                         "deposit_pct": 30, "approval": "Head of Credit"},
    "real_estate": {"ead_sar_mn": 16141.3, "share_pct": 10.5, "limit_pct": 10.0, "headroom_sar_mn": -856.9},
    "breaches": [{"proposal_id": "DD-03", "obligor": "Al Khobar Modern Cold Storage Company", "breach": "Connected group",
                  "raroc": 13.2},
                 {"proposal_id": "DD-05", "obligor": "Najd Al Bunyan Contracting Company", "breach": "DSCR after the deal",
                  "raroc": 11.2}],
}
DEALS_FALLBACK: dict[str, dict[str, Any]] = {
    "DD-02": {"obligor_name": "Taif Central Engineering", "sector": "Construction", "rating": "BB", "amount_sar_mn": 16.0,
              "rm": "Sara Al-Dosari", "status": "in_review", "tenor_years": 6},
    "DD-04": {"obligor_name": "Al Nakheel Commercial Properties Company", "sector": "Real Estate", "rating": "BB+",
              "amount_sar_mn": 150.0, "rm": "Abdullah Al-Zahrani", "status": "new", "tenor_years": 7},
    "DD-06": {"obligor_name": "Dhahran Continental Industries", "sector": "Manufacturing", "rating": "BB+",
              "amount_sar_mn": 25.0, "rm": "Khalid Al-Otaibi", "status": "counter_offered", "tenor_years": 3},
    "R12-TWA": {"obligor_name": "Al Sahel Building Materials Trading LLC", "sector": "Wholesale Trade", "rating": "BB",
                "amount_sar_mn": 170.0, "rm": "Nasser Al-Harbi", "status": "in_review", "tenor_years": 3},
    "R14-RWQ": {"obligor_name": "Ruwaq Gulf Contracting Company", "sector": "Construction", "rating": "BB",
                "amount_sar_mn": 40.0, "rm": "Tariq Al-Mansour", "status": "new", "tenor_years": 4},
    "PL-10": {"obligor_name": "Al Madinah Specialist Hospital Company", "sector": "Healthcare", "rating": "A",
              "amount_sar_mn": 120.0, "rm": "Khalid Al-Otaibi", "status": "in_review", "tenor_years": 8},
    "PL-22": {"obligor_name": "Al Faisaliah Contracting", "sector": "Construction", "rating": "BBB-",
              "amount_sar_mn": 35.0, "rm": "Khalid Al-Otaibi", "status": "in_review", "tenor_years": 5},
}


def _j(v: Any) -> str:
    return store._j(v)


def deal_link(pid: str, label: str) -> dict[str, str]:
    return {"label": label, "href": f"/deal-desk/{pid}", "type": "dealdesk-proposal"}


# ------------------------------------------------------------------ facts


def deals() -> dict[str, dict[str, Any]]:
    """The deals the seed names, as Deal Desk's registry summarises them (the fallback table when it cannot be read)."""
    out = {k: dict(v) for k, v in DEALS_FALLBACK.items()}
    try:
        from backend.dealdesk import proposals, registry_lookup
        for d in registry_lookup.all_deals():
            pid = d.get("proposal_id")
            if pid in out:
                s = proposals.summary(d)
                out[pid].update({k: s[k] for k in ("obligor_name", "sector", "rating", "amount_sar_mn", "rm", "status",
                                                   "tenor_years") if s.get(k) is not None})
    except Exception:  # noqa: BLE001 - the registry is Deal Desk's; the seed still reads
        pass
    return out


def _metrics(pid: str, terms: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import engine, proposals
        p = proposals.get(pid)
        a = engine.analyse(p, terms)
        m, t = a["metrics"], a["terms"]
        return {"raroc": round(100 * float(m["lifetime_raroc"]), 1), "hurdle": round(100 * float(m["hurdle"]), 1),
                "margin_bps": int(round(float(t.get("margin_bps") or 0))), "tenor_years": int(t.get("tenor_years") or 0),
                "commitment_fee_bps": int(round(float(t.get("commitment_fee_bps") or 0))),
                # Round D: the cash cover is the cash margin plus a lien-marked deposit (the Deposit requirement term)
                "cash_margin_pct": int(round(float(t.get("cash_margin_pct") or 0) + (float(t.get("deposit_pct") or 0) if t.get("deposit_type") == "lien_cash" else 0))),
                "deposit_pct": int(round(float(t.get("deposit_pct") or 0))) if t.get("deposit_type") == "lien_cash" else 0,
                "sva": round(float(m["sva"]), 2), "approval": (a.get("approval") or {}).get("level") or ""}
    except Exception:  # noqa: BLE001 - engine not importable or the proposal gone: the figures Deal Desk shows
        return None


def _real_estate() -> dict[str, Any]:
    try:
        from backend.dealdesk.group import sources as S
        rows = S.records(S.read("dd_portfolio_snapshot", None, dimension="sector", dimension_key="Real Estate"))
        r = rows[0]
        return {"ead_sar_mn": float(r["ead_sar_mn"]), "share_pct": float(r["share_pct"]), "limit_pct": float(r["limit_pct"]),
                "headroom_sar_mn": float(r["headroom_sar_mn"])}
    except Exception:  # noqa: BLE001
        return dict(FALLBACK["real_estate"])


def facts() -> dict[str, Any]:
    f: dict[str, Any] = {"deals": deals()}
    f["dd02_ask"] = _metrics("DD-02", None) or dict(FALLBACK["dd02_ask"])
    f["dd02_counter"] = _metrics("DD-02", {"deposit_type": "lien_cash", "deposit_pct": 20}) or dict(FALLBACK["dd02_counter"])  # Round D
    f["dd06_ask"] = _metrics("DD-06", None) or dict(FALLBACK["dd06_ask"])
    # the optimiser's closest feasible structure: its commitment fee is 30.3 bps (30 bps prices a hair under the hurdle)
    f["dd06_recommended"] = _metrics("DD-06", {"margin_bps": 190, "commitment_fee_bps": 30.3, "deposit_type": "lien_cash", "deposit_pct": 30}) \
        or dict(FALLBACK["dd06_recommended"])
    f["real_estate"] = _real_estate()
    f["breaches"] = [dict(b) for b in FALLBACK["breaches"]]
    return f


# --------------------------------------------------------------- helpers


def _docx(title: str, subtitle: str, sections: list[tuple[str, list[str], list[Any] | None]], by: str) -> bytes:
    """A short Word document in the house style with the same bytes on every seed (fixed timestamps)."""
    import zipfile

    from backend.house_style import Meta
    from backend.house_style import docx as hd

    stamp = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    meta = Meta(title=title, book="corporate", period=PERIOD, subject="Deal Desk", generated_by=by, generated_at=stamp)
    doc = hd.document(meta, kind="Credit proposal", subtitle=subtitle, cover="block")
    for heading, paras, tbl in sections:
        hd.heading(doc, heading, 1)
        for p in paras:
            hd.para(doc, p)
        if tbl:
            hd.table(doc, tbl[0], tbl[1], kinds=tbl[2])
    fixed = datetime(2026, 10, 20, 9, 0)
    doc.core_properties.created = fixed
    doc.core_properties.modified = fixed
    doc.core_properties.last_printed = fixed
    buf = io.BytesIO()
    doc.save(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2026, 10, 20, 9, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, zin.read(item.filename))
    return out.getvalue()


def _project(con: sqlite3.Connection, pid: str, name: str, description: str, owner: str, members: list[str],
             due: str, links: list[dict[str, str]], created: str, updated: str, instructions: str,
             focus: dict[str, Any]) -> None:
    con.execute("INSERT OR IGNORE INTO projects(id, name, description, owner_id, status, due_at, period, members, links, "
                "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                (pid, name, description, owner, "active", due, PERIOD, _j(list(dict.fromkeys([owner, *members]))),
                 _j(links), created, updated))
    store.set_project_scope(con, pid, instructions, ["dealdesk", "corporate"], focus)


def _tasks(con: sqlite3.Connection, pid: str, first_id: int, tasks: list[tuple[str, str, str, str, dict[str, str]]]) -> None:
    for i, (title, detail, status, who, link) in enumerate(tasks):
        con.execute("INSERT OR IGNORE INTO project_items(id, project_id, position, title, detail, kind, status, assignee_id, "
                    "href, link_label, demo) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
                    (first_id + i, pid, i + 1, title, detail, "task", status, who, link["href"], link["label"]))


def _turn(role: str, text: str, at: str, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"role": role, "text": text, "at": at, "artifacts": artifacts or []}


def _answer(narrative: str, headline: str, figures: list[dict[str, Any]], table: dict[str, Any] | None,
            chart: dict[str, Any] | None = None, source: str = "Deal Desk engine") -> dict[str, Any]:
    out = {"narrative": narrative, "headline": headline, "figures": figures, "table": table or {}, "period": PERIOD,
           "engine": "dealdesk", "source": source,
           "recompute_note": "Computed by the Deal Desk engine on the proposal's terms; open the deal to run it again."}
    if chart:
        out["chart"] = chart
    return out


def _deal_terms_text(m: dict[str, Any], funded: bool = True) -> str:
    bits = [f"SAIBOR + {m['margin_bps']} bps", f"{m['tenor_years']} years"]
    if m.get("commitment_fee_bps"):
        bits.append(f"commitment fee {m['commitment_fee_bps']} bps")
    if m.get("deposit_pct"):
        bits.append(f"lien-marked cash deposit {m['deposit_pct']}% of the limit")
    elif m.get("cash_margin_pct"):
        bits.append(f"cash margin {m['cash_margin_pct']}%")
    return ", ".join(bits)


# ------------------------------------------------------------------ seed


def apply(con: sqlite3.Connection) -> None:
    old = con.row_factory
    con.row_factory = sqlite3.Row  # the store's readers take rows by name
    try:
        _apply(con, facts())
    finally:
        con.row_factory = old


def _apply(con: sqlite3.Connection, f: dict[str, Any]) -> None:
    d = f["deals"]
    dd02, dd04, dd06 = d["DD-02"], d["DD-04"], d["DD-06"]
    a02, c02, a06, r06 = f["dd02_ask"], f["dd02_counter"], f["dd06_ask"], f["dd06_recommended"]
    re_ = f["real_estate"]
    over = -re_["headroom_sar_mn"]
    ins = con.execute

    for u in USERS:
        ins("INSERT OR IGNORE INTO users(id, name, title, initials, position) VALUES(?,?,?,?,?)", u)

    L_DD02 = deal_link("DD-02", f"Deal Desk · DD-02 {dd02['obligor_name']}")
    L_DD04 = deal_link("DD-04", f"Deal Desk · DD-04 {dd04['obligor_name']}")
    L_DD06 = deal_link("DD-06", f"Deal Desk · DD-06 {dd06['obligor_name']}")
    L_RWQ = deal_link("R14-RWQ", f"Deal Desk · R14-RWQ {d['R14-RWQ']['obligor_name']}")
    L_REVIEW = {"label": "Deal Desk · Review", "href": "/deal-desk/review", "type": "dealdesk"}
    L_CONDITIONS = {"label": "Deal Desk · Conditions", "href": "/deal-desk/review?view=conditions", "type": "dealdesk"}

    # ------------------------------------------------------------- projects
    _project(con, P1, "DD-06 Dhahran Continental: counter-offer to committee",
             f"DD-06 {dd06['obligor_name']} ({dd06['sector']}, {dd06['rating']}): {mn(dd06['amount_sar_mn'])} revolving "
             f"working capital Murabaha, {dd06['tenor_years']} years. The ask prices at RAROC {a06['raroc']:.1f}% against a "
             f"{a06['hurdle']:.1f}% hurdle; the recommended structure ({_deal_terms_text(r06)}) reaches "
             f"{r06['raroc']:.1f}% and sits with the {r06['approval'] or 'Head of Credit'}. Counter-offer sent to the RM on 20 Oct; "
             f"to the credit committee of 29 Oct 2026.",
             KHALID, [SARA, ABDULLAH, NOURA], COMMITTEE, [L_DD06, L_REVIEW], "2026-10-15T07:30:00Z", "2026-10-22T14:10:00Z",
             f"Answer for proposal DD-06 {dd06['obligor_name']} unless another deal is named. Quote the engine's figures "
             "(RAROC, hurdle, approval level) with the terms they were computed on. Cite the bank-form proposal in the "
             "project documents where it applies.", {"proposal_id": "DD-06", "period": PERIOD})
    _tasks(con, P1, 1, [
        ("Confirm the cash margin and deposit condition",
         f"The recommended structure holds a {r06['cash_margin_pct']}% lien-marked cash deposit (the Deposit requirement term) and a commitment fee of "
         f"{r06['commitment_fee_bps']} bps; confirm the deposit condition with Treasury before the paper goes out.",
         "in_progress", SARA, L_DD06),
        ("Refresh the bank-form proposal",
         "Rebuild the proposal on the recommended terms and attach the latest version to the project.", "in_progress",
         KHALID, L_DD06),
        ("RM to confirm the structure with the customer",
         f"{dd06['rm']} to take the counter-offer ({_deal_terms_text(r06)}) to {dd06['obligor_name']} and record the answer "
         "on the deal.", "todo", KHALID, L_DD06),
        ("Committee paper", "Draft the committee paper in Playbook from the deal's analysis.", "todo", ABDULLAH,
         {"label": "Playbook · committee paper", "href": "/playbook", "type": "report"}),
    ])

    _project(con, P2, "DD-02 Taif Central Engineering: credit review",
             f"DD-02 {dd02['obligor_name']} ({dd02['sector']}, {dd02['rating']}): {mn(dd02['amount_sar_mn'])} term loan, "
             f"{dd02['tenor_years']} years, in review. The ask prices at RAROC {a02['raroc']:.1f}% against a {a02['hurdle']:.1f}% "
             f"hurdle; the optimised counter-offer (lien-marked cash deposit {c02['cash_margin_pct']}%) reaches {c02['raroc']:.1f}%. Credit has "
             "raised three queries on the request.",
             SARA, [KHALID, NOURA], "2026-10-27", [L_DD02, L_REVIEW], "2026-10-08T08:00:00Z", "2026-10-22T09:45:00Z",
             f"Answer for proposal DD-02 {dd02['obligor_name']} unless another deal is named. Quote the engine's figures "
             "with their terms. Credit's queries and the conditions precedent are tracked as tasks here.",
             {"proposal_id": "DD-02", "period": PERIOD})
    _tasks(con, P2, 11, [
        ("Answer Credit's 3 queries",
         "Receivables ageing on the two government contracts; the guarantor's net worth statement; the use of the "
         "SAR 4.0m retention release.", "in_progress", SARA, L_DD02),
        ("Conditions precedent list",
         "Assignment of contract proceeds, the updated insurance schedule and the cash margin account opened before "
         "drawdown.", "todo", SARA, L_CONDITIONS),
        ("Site visit note", "Write up the 19 Oct site visit to the Taif yard and attach it to the deal.", "todo", KHALID,
         L_DD02),
    ])

    committee_deals = [("R12-TWA", 21), ("DD-06", 22), ("PL-10", 23), ("PL-22", 24)]
    _project(con, P3, "Credit committee 29 Oct 2026",
             "The four deals going to the credit committee of 29 Oct 2026: "
             + "; ".join(f"{pid} {d[pid]['obligor_name']} ({d[pid]['sector']}, {mn(d[pid]['amount_sar_mn'])})"
                         for pid, _ in committee_deals)
             + ". One paper per deal, each on the engine's recommended structure.",
             ABDULLAH, [KHALID, SARA, NOURA, FAISAL], COMMITTEE,
             [deal_link(pid, f"Deal Desk · {pid} {d[pid]['obligor_name']}") for pid, _ in committee_deals],
             "2026-10-16T10:00:00Z", "2026-10-23T08:15:00Z",
             "Answer for the deals on the 29 Oct 2026 committee agenda (R12-TWA, DD-06, PL-10, PL-22). Quote each deal's "
             "amount, rating, RAROC against hurdle and approval level from the engine.",
             {"committee_date": COMMITTEE, "proposal_ids": [pid for pid, _ in committee_deals]})
    owners = {"R12-TWA": ABDULLAH, "DD-06": KHALID, "PL-10": KHALID, "PL-22": SARA}
    _tasks(con, P3, 21, [
        (f"{pid} {d[pid]['obligor_name']}: committee paper",
         f"{d[pid]['sector']}, {d[pid]['rating']}, {mn(d[pid]['amount_sar_mn'])}; RM {d[pid]['rm']}. Paper due "
         f"{COMMITTEE}.", "in_progress" if pid in ("R12-TWA", "DD-06") else "todo", owners[pid],
         deal_link(pid, f"Deal Desk · {pid} {d[pid]['obligor_name']}"))
        for pid, _ in committee_deals
    ])

    # ------------------------------------------------- the DD-06 proposal (bank form, draft)
    try:
        from backend.workspace_v5 import docs
        data = _docx(
            f"Credit proposal: {dd06['obligor_name']} (DD-06)", "Bank form · draft on the recommended structure",
            [("Action requested", [
                f"Approval of a {mn(dd06['amount_sar_mn'])} revolving working capital Murabaha for {dd06['obligor_name']} "
                f"({dd06['sector']}, rated {dd06['rating']}), {dd06['tenor_years']} years, on the recommended structure: "
                f"{_deal_terms_text(r06)}.",
                f"Approval level per the Delegation of Authority: {r06['approval'] or 'Head of Credit'}."], None),
             ("Terms and economics", ["The ask against the recommended structure, as the engine computed them."],
              [["Structure", "Margin (bps)", "Commitment fee (bps)", "Cash margin %", "Lifetime RAROC %", "Hurdle %"],
               [["The ask", a06["margin_bps"], a06.get("commitment_fee_bps", 0), a06["cash_margin_pct"], a06["raroc"], a06["hurdle"]],
                ["Recommended", r06["margin_bps"], r06.get("commitment_fee_bps", 0), r06["cash_margin_pct"], r06["raroc"], r06["hurdle"]]],
               ["text", "int", "int", "pct1", "pct1", "pct1"]]),
             ("Conditions", [
                 f"Cash margin of {r06['cash_margin_pct']}% of the limit held in a lien-marked account before the first drawdown.",
                 "Quarterly management accounts within 45 days of quarter-end; annual audited accounts within 120 days.",
                 "Utilisation reviewed at six months; the commitment fee applies to the undrawn limit."], None)],
            f"{NAME[KHALID]} (Corporate Credit Manager)")
        name = "DD-06 credit proposal (bank form, draft).docx"
        store.add_project_file(con, KHALID, P1, name, data, docs.extract(name, data), docs.KINDS[".docx"], file_id=DOC_DD06,
                               at="2026-10-20T09:05:00Z", demo=True)
    except Exception:  # noqa: BLE001 - the Word library missing: the project stands without the file
        pass

    # ------------------------------------------------------- investigations
    re_turns = [
        _turn("user", "How much real-estate headroom is left this quarter, and does DD-04 fit?", "2026-10-19T07:40:00Z"),
        _turn("assistant",
              f"Real Estate is {pct(re_['share_pct'], 1)} of the corporate book at {PERIOD} against a {pct(re_['limit_pct'], 1)} "
              f"appetite limit: {mn(over)} over the limit, so there is no headroom this quarter. DD-04 {dd04['obligor_name']} asks "
              f"for {mn(dd04['amount_sar_mn'])}, which would take the sector further over.", "2026-10-19T07:40:20Z",
              [{"kind": "figures", "title": f"Real Estate against appetite, {PERIOD}", "period": PERIOD, "figures": [
                  {"key": "ead", "label": "Real Estate EAD", "value": re_["ead_sar_mn"], "unit": "sar_mn"},
                  {"key": "share", "label": "Share of the corporate book", "value": re_["share_pct"], "unit": "pct"},
                  {"key": "limit", "label": "Appetite limit", "value": re_["limit_pct"], "unit": "pct"},
                  {"key": "over", "label": "Over the limit", "value": over, "unit": "sar_mn"},
                  {"key": "ask", "label": "DD-04 ask", "value": dd04["amount_sar_mn"], "unit": "sar_mn"}]},
               {"kind": "object", "type": "dealdesk-proposal", "id": "DD-04", "label": L_DD04["label"], "href": L_DD04["href"]}]),
        _turn("user", "What would make it approvable?", "2026-10-19T07:44:00Z"),
        _turn("assistant",
              "A sector limit over appetite is a soft breach: the deal can go to the committee with a sector exception, "
              "or wait for the Real Estate book to run off below the limit. A smaller ask does not clear the breach while "
              "the sector is over.", "2026-10-19T07:44:25Z"),
    ]
    store.import_investigation(
        con, ABDULLAH, source={"type": "dealdesk-thread", "id": "DD-04", "label": L_DD04["label"], "href": L_DD04["href"]},
        title="DD-04 Al Nakheel: real-estate appetite headroom", turns=re_turns,
        summary=(f"Real Estate is {pct(re_['share_pct'], 1)} of the corporate book at {PERIOD}, above the "
                 f"{pct(re_['limit_pct'], 1)} appetite limit by {mn(over)}. DD-04 {dd04['obligor_name']} asks for "
                 f"{mn(dd04['amount_sar_mn'])}; the sector has no headroom this quarter."),
        continue_href="/deal-desk/DD-04", sector="Real Estate", period=PERIOD, inv_id=INV_RE,
        at="2026-10-19T07:45:00Z", demo=True, status="in_review")
    con.execute("UPDATE investigations SET figures=? WHERE id=?", (_j([
        {"key": "re_ead", "label": "Real Estate EAD", "period": PERIOD, "value": re_["ead_sar_mn"], "unit": "sar_mn",
         "source": "dd_portfolio_snapshot.ead_sar_mn"},
        {"key": "re_share", "label": "Share of the corporate book", "period": PERIOD, "value": re_["share_pct"], "unit": "pct",
         "source": "dd_portfolio_snapshot.share_pct"},
        {"key": "re_limit", "label": "Appetite limit", "period": PERIOD, "value": re_["limit_pct"], "unit": "pct",
         "source": "dd_portfolio_snapshot.limit_pct"},
        {"key": "re_over", "label": "Over the limit", "period": PERIOD, "value": over, "unit": "sar_mn",
         "source": "dd_portfolio_snapshot.headroom_sar_mn"},
        {"key": "dd04_ask", "label": "DD-04 ask", "period": PERIOD, "value": dd04["amount_sar_mn"], "unit": "sar_mn",
         "source": "proposal DD-04"}]), INV_RE))
    for nid, who, at, body in [
        (1, ABDULLAH, "2026-10-19T08:10:00Z",
         f"Real Estate is {mn(over)} over the {pct(re_['limit_pct'], 1)} limit at {PERIOD}. DD-04 cannot be booked without "
         "a sector exception; I am taking it to the Head of Credit before the RM goes back to the customer."),
        (2, NOURA, "2026-10-20T11:30:00Z",
         "No sector exception for a new-to-bank name while the sector is over appetite. Keep DD-04 in the pipeline and "
         "re-run the headroom at 2026Q3."),
    ]:
        con.execute("INSERT OR IGNORE INTO investigation_notes(id, investigation_id, author_id, body, kind, created_at, demo) "
                    "VALUES(?,?,?,?,?,?,1)", (nid, INV_RE, who, body, "note", at))

    rwq = d["R14-RWQ"]
    rwq_turns = [
        _turn("user", "Run the proposal check on R14-RWQ.", "2026-10-21T06:50:00Z"),
        _turn("assistant",
              f"R14-RWQ {rwq['obligor_name']} ({rwq['sector']}, {rwq['rating']}, {mn(rwq['amount_sar_mn'])}): proposal check score "
              "75.5, grade C. Four critical findings: the group chart is missing, the bank statements cover eight months not "
              "twelve, the guarantor's net worth is unsupported, and the bureau report shows 4 returned cheques in the last "
              "12 months. The request is half-baked: send it back to the RM before Credit reads it.", "2026-10-21T06:50:30Z",
              [{"kind": "figures", "title": "Proposal check, R14-RWQ", "period": PERIOD, "figures": [
                  {"key": "score", "label": "Score", "value": 75.5, "unit": "num"},
                  {"key": "critical", "label": "Critical findings", "value": 4, "unit": "int"},
                  {"key": "cheques", "label": "Returned cheques, 12 months", "value": 4, "unit": "int"}]},
               {"kind": "object", "type": "dealdesk-proposal", "id": "R14-RWQ", "label": L_RWQ["label"], "href": L_RWQ["href"]}]),
        _turn("user", "If the RM adds the group chart and the full statements?", "2026-10-21T06:55:00Z"),
        _turn("assistant",
              "The score moves from 75.5 to 76 and the grade stays C: the returned cheques and the unsupported guarantor "
              "net worth are the findings that hold it there. Both need the customer's documents, not the RM's.",
              "2026-10-21T06:55:20Z"),
    ]
    store.import_investigation(
        con, SARA, source={"type": "dealdesk-thread", "id": "R14-RWQ", "label": L_RWQ["label"], "href": L_RWQ["href"]},
        title="R14-RWQ Ruwaq Gulf: half-baked proposal check", turns=rwq_turns,
        summary=(f"Proposal check on R14-RWQ {rwq['obligor_name']} ({mn(rwq['amount_sar_mn'])}, {rwq['sector']}): score 75.5 "
                 "→ 76 with the RM's fixes, grade C, 4 critical findings, 4 returned cheques in 12 months. Sent back to the RM."),
        continue_href="/deal-desk/R14-RWQ", sector=rwq["sector"], period=PERIOD, inv_id=INV_RWQ,
        at="2026-10-21T06:56:00Z", demo=True, status="open")
    for nid, who, at, body in [
        (3, SARA, "2026-10-21T07:20:00Z",
         "Returned the request to the RM with the four findings. The returned cheques need an explanation letter from "
         "the customer and the bank's statement of the account."),
        (4, KHALID, "2026-10-22T08:05:00Z",
         "Agreed. Nothing goes to Credit under grade C. Re-run the check when the group chart and the twelve-month "
         "statements are in."),
    ]:
        con.execute("INSERT OR IGNORE INTO investigation_notes(id, investigation_id, author_id, body, kind, created_at, demo) "
                    "VALUES(?,?,?,?,?,?,1)", (nid, INV_RWQ, who, body, "note", at))

    # ------------------------------------------------------------- analyses
    terms_cols = [{"key": "structure", "label": "Structure", "unit": "text"}, {"key": "margin_bps", "label": "Margin (bps)", "unit": "int"},
                  {"key": "tenor_years", "label": "Tenor (years)", "unit": "int"},
                  {"key": "cash_margin_pct", "label": "Cash margin %", "unit": "pct"},
                  {"key": "raroc_pct", "label": "Lifetime RAROC %", "unit": "pct"}, {"key": "hurdle_pct", "label": "Hurdle %", "unit": "pct"}]

    def term_row(label: str, m: dict[str, Any]) -> dict[str, Any]:
        return {"structure": label, "margin_bps": m["margin_bps"], "tenor_years": m["tenor_years"],
                "cash_margin_pct": m["cash_margin_pct"], "raroc_pct": m["raroc"], "hurdle_pct": m["hurdle"],
                "commitment_fee_bps": m.get("commitment_fee_bps", 0)}

    def term_figs(m: dict[str, Any], prefix: str, label: str) -> list[dict[str, Any]]:
        return [{"key": f"{prefix}_raroc", "label": f"Lifetime RAROC, {label}", "value": m["raroc"], "unit": "pct"},
                {"key": f"{prefix}_hurdle", "label": "Hurdle", "value": m["hurdle"], "unit": "pct"}]

    store.create_analysis(
        con, SARA, title=f"DD-02 optimised: counter-offer at RAROC {c02['raroc']:.1f}%",
        question=f"What counter-offer clears the hurdle on DD-02 {dd02['obligor_name']}?", origin="dealdesk", book="corporate",
        period=PERIOD, answer=_answer(
            f"DD-02 {dd02['obligor_name']}: the ask ({_deal_terms_text(a02)}) prices at lifetime RAROC {a02['raroc']:.1f}% against a "
            f"{a02['hurdle']:.1f}% hurdle. The optimiser's closest structure keeps the amount, tenor and margin and adds a "
            f"{c02['cash_margin_pct']}% lien-marked cash deposit: RAROC {c02['raroc']:.1f}%, clearing the hurdle.",
            f"A **{c02['cash_margin_pct']}% lien-marked cash deposit** on the ask takes DD-02 from RAROC {a02['raroc']:.1f}% to "
            f"**{c02['raroc']:.1f}%** against a {c02['hurdle']:.1f}% hurdle.",
            term_figs(a02, "ask", "the ask") + term_figs(c02, "counter", "the counter-offer"),
            {"key": "structure", "columns": terms_cols, "rows": [term_row("The ask", a02), term_row("Counter-offer", c02)]},
            {"title": "Lifetime RAROC against the hurdle", "x": "structure", "y": "raroc_pct"}),
        spec=None, origin_link={"type": "dealdesk-proposal", "label": L_DD02["label"], "href": L_DD02["href"]},
        notes="Engine figures on the proposal's terms; the counter-offer is the optimiser's closest feasible structure.",
        source="Deal Desk engine (backend.dealdesk.engine)", analysis_id=A_DD02, at="2026-10-14T10:20:00Z", demo=True)
    con.execute("UPDATE analyses SET project_id=? WHERE id=?", (P2, A_DD02))

    store.create_analysis(
        con, KHALID, title="DD-06: the ask against the recommended structure",
        question=f"How does the ask on DD-06 {dd06['obligor_name']} compare with the recommended structure?", origin="dealdesk",
        book="corporate", period=PERIOD, answer=_answer(
            f"DD-06 {dd06['obligor_name']}: the ask ({_deal_terms_text(a06)}) prices at lifetime RAROC {a06['raroc']:.1f}% against a "
            f"{a06['hurdle']:.1f}% hurdle and needs the {a06['approval'] or 'Chief Risk Officer'}. The recommended structure "
            f"({_deal_terms_text(r06)}) reaches {r06['raroc']:.1f}% and sits with the {r06['approval'] or 'Head of Credit'}.",
            f"The recommended structure lifts DD-06 from RAROC {a06['raroc']:.1f}% to **{r06['raroc']:.1f}%** against a "
            f"{r06['hurdle']:.1f}% hurdle, with a **{r06['cash_margin_pct']}% lien-marked cash deposit** and a {r06['commitment_fee_bps']} bps "
            "commitment fee.",
            term_figs(a06, "ask", "the ask") + term_figs(r06, "recommended", "the recommended structure"),
            {"key": "structure", "columns": terms_cols + [{"key": "commitment_fee_bps", "label": "Commitment fee (bps)", "unit": "int"}],
             "rows": [term_row("The ask", a06), term_row("Recommended", r06)]},
            {"title": "Lifetime RAROC against the hurdle", "x": "structure", "y": "raroc_pct"}),
        spec=None, origin_link={"type": "dealdesk-proposal", "label": L_DD06["label"], "href": L_DD06["href"]},
        notes="Engine figures on both sets of terms; approval levels from the Delegation of Authority.",
        source="Deal Desk engine (backend.dealdesk.engine)", analysis_id=A_DD06, at="2026-10-20T08:40:00Z", demo=True)
    con.execute("UPDATE analyses SET project_id=? WHERE id=?", (P1, A_DD06))

    store.create_analysis(
        con, ABDULLAH, title=f"Real-estate appetite headroom at {PERIOD}",
        question=f"How much real-estate headroom is left at {PERIOD}?", origin="dealdesk", book="corporate", period=PERIOD,
        answer=_answer(
            f"Real Estate holds {mn(re_['ead_sar_mn'])} of corporate EAD at {PERIOD}, {pct(re_['share_pct'], 1)} of the book against a "
            f"{pct(re_['limit_pct'], 1)} appetite limit: {mn(over)} over. DD-04 {dd04['obligor_name']} asks for "
            f"{mn(dd04['amount_sar_mn'])} in the sector.",
            f"Real Estate is **{pct(re_['share_pct'], 1)}** of the corporate book at {PERIOD} against a {pct(re_['limit_pct'], 1)} "
            f"limit: **{mn(over)} over**, so no headroom for DD-04's {mn(dd04['amount_sar_mn'])} ask.",
            [{"key": "ead", "label": "Real Estate EAD", "value": re_["ead_sar_mn"], "unit": "sar_mn"},
             {"key": "share_pct", "label": "Share of the corporate book", "value": re_["share_pct"], "unit": "pct"},
             {"key": "limit_pct", "label": "Appetite limit", "value": re_["limit_pct"], "unit": "pct"},
             {"key": "over", "label": "Over the limit", "value": over, "unit": "sar_mn"}],
            {"key": "measure", "columns": [{"key": "measure", "label": "Measure", "unit": "text"},
                                           {"key": "value", "label": "Value", "unit": "text"}],
             "rows": [{"measure": "Real Estate EAD", "value": mn(re_["ead_sar_mn"])},
                      {"measure": "Share of the corporate book", "value": pct(re_["share_pct"], 1)},
                      {"measure": "Appetite limit", "value": pct(re_["limit_pct"], 1)},
                      {"measure": "Headroom", "value": f"−{mn(over)} (over the limit)"},
                      {"measure": "DD-04 ask", "value": mn(dd04["amount_sar_mn"])}]},
            source="dd_portfolio_snapshot (Deal Desk data)"),
        spec=None, origin_link={"type": "dealdesk-thread", "label": L_DD04["label"], "href": L_DD04["href"]},
        notes="Sector share and limit from the portfolio snapshot at the as-of quarter; soft limit.",
        source="dd_portfolio_snapshot", analysis_id=A_HEADROOM, at="2026-10-19T07:50:00Z", demo=True)
    con.execute("UPDATE analyses SET investigation_id=? WHERE id=?", (INV_RE, A_HEADROOM))

    br = f["breaches"]
    store.create_analysis(
        con, NOURA, title="Proposals breaching a hard limit",
        question="Which proposals breach a hard limit at the ask?", origin="dealdesk", book="corporate", period=PERIOD,
        answer=_answer(
            f"{len(br)} proposals breach a hard limit at the ask: " + "; ".join(
                f"{b['proposal_id']} {b['obligor']} ({b['breach']}, lifetime RAROC {b['raroc']:.1f}%)" for b in br)
            + ". Neither can be approved on the ask's terms.",
            f"**{len(br)} proposals** breach a hard limit at the ask: " + " and ".join(
                f"{b['proposal_id']} ({b['breach']}, RAROC **{b['raroc']:.1f}%**)" for b in br) + ".",
            [{"key": "n", "label": "Proposals breaching a hard limit", "value": len(br), "unit": "int"}],
            {"key": "proposal_id", "columns": [{"key": "proposal_id", "label": "Proposal", "unit": "text"},
                                               {"key": "obligor", "label": "Obligor", "unit": "text"},
                                               {"key": "breach", "label": "Hard breach", "unit": "text"},
                                               {"key": "raroc", "label": "Lifetime RAROC %", "unit": "pct"}],
             "rows": [dict(b) for b in br]}),
        spec=None, origin_link={"type": "dealdesk", "label": "Deal Desk · Review", "href": "/deal-desk/review"},
        notes="Hard limits from the credit policy constraints; the engine evaluates every pipeline proposal at the ask.",
        source="Deal Desk engine (backend.dealdesk.engine)", analysis_id=A_BREACHES, at="2026-10-18T09:00:00Z", demo=True)

    # ----------------------------------------------------------------- inbox
    items = [
        (1, KHALID, "mention", f"{NAME[SARA]} mentioned you in “DD-06 Dhahran Continental: counter-offer to committee”",
         f"@Khalid please confirm DD-06's deposit condition: {r06['cash_margin_pct']}% cash margin, lien-marked, before drawdown.",
         f"/projects/{P1}", SARA, "2026-10-21T09:10:00Z", f"project:{P1}"),
        (2, KHALID, "assignment", "Committee pack for 29 Oct: PL-10 paper due",
         f"PL-10 {d['PL-10']['obligor_name']} ({d['PL-10']['sector']}, {mn(d['PL-10']['amount_sar_mn'])}): committee paper due "
         f"{COMMITTEE}.", f"/projects/{P3}", ABDULLAH, "2026-10-16T10:05:00Z", f"project:{P3}"),
        (3, ABDULLAH, "assignment", "Committee pack for 29 Oct: R12-TWA paper due",
         f"R12-TWA {d['R12-TWA']['obligor_name']} ({d['R12-TWA']['sector']}, {mn(d['R12-TWA']['amount_sar_mn'])}): committee paper "
         f"due {COMMITTEE}.", f"/projects/{P3}", NOURA, "2026-10-16T10:30:00Z", f"project:{P3}"),
        (4, SARA, "assignment", "Assigned: answer Credit's 3 queries on DD-02",
         "Receivables ageing, the guarantor's net worth statement and the retention release; Credit needs them before "
         "the 27 Oct review.", f"/projects/{P2}", NOURA, "2026-10-20T08:00:00Z", f"project:{P2}"),
        (5, SARA, "mention", f"{NAME[KHALID]} mentioned you in “R14-RWQ Ruwaq Gulf: half-baked proposal check”",
         "@Sara nothing goes to Credit under grade C; re-run the check when the twelve-month statements are in.",
         f"/investigations/{INV_RWQ}", KHALID, "2026-10-22T08:05:00Z", f"investigation:{INV_RWQ}"),
        (6, ABDULLAH, "notification", f"{NAME[NOURA]} answered on “DD-04 Al Nakheel: real-estate appetite headroom”",
         "No sector exception for a new-to-bank name while the sector is over appetite; re-run at 2026Q3.",
         f"/investigations/{INV_RE}", NOURA, "2026-10-20T11:30:00Z", f"investigation:{INV_RE}"),
        (7, NOURA, "notification", "DD-07 Unayzah Trading: 2 conditions overdue",
         "The insurance schedule and the assignment of receivables were due 15 Oct; the RM has not filed them.",
         "/deal-desk/review?view=conditions", None, "2026-10-21T06:00:00Z", "dealdesk:DD-07"),
        (8, ANNE, "assignment", "Assigned: DD-06 committee paper (Playbook)",
         "Review the DD-06 committee paper draft before it goes to the Head of Credit.", "/playbook", KHALID,
         "2026-10-22T14:10:00Z", "playbook:dd-06"),
    ]
    for iid, uid, kind, title, body, href, actor, at, source in items:
        ins("INSERT OR IGNORE INTO inbox_items(id, user_id, kind, title, body, href, actor_id, created_at, read, demo, "
            "source) VALUES(?,?,?,?,?,?,?,?,0,1,?)", (iid, uid, kind, title, body, href, actor, at, source))
