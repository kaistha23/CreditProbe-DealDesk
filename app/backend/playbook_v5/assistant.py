"""The Playbook assistant: starts documents, drafts and revises sections, imports work, moves the status.

It reads the request in the user's own words, deterministically: which section ("the executive summary"), which
action (draft, revise, import, send for review), and which object ("the construction attention item", "Borrower
360 for CB01312"). Drafted text and figures come from the books (`content`), so a section the assistant writes
quotes the same numbers as the modules. With PLAYBOOK_ANTHROPIC_API_KEY set, revisions of prose ("make it more
formal") are written by the model; figures never are.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import date, timedelta
from typing import Any

from backend.playbook_v5 import content, resolvers, store, templates

SECTORS = ["Construction", "Real Estate", "Manufacturing", "Oil & Gas", "Trade", "Transport", "Healthcare",
           "Hospitality", "Utilities", "Telecom", "Agriculture", "Retail Trade", "Services", "Technology"]
SUGGEST = ["Draft every empty section", "Import the Early Warning list", "Add Borrower 360 for CB01312",
           "Make the executive summary shorter", "Send for review"]


def _context(r: dict[str, Any]) -> dict[str, Any]:
    t = r["title"]
    m = re.search(r"\b(CB\d{5})\b", t.upper())
    sector = next((s for s in sorted(SECTORS, key=len, reverse=True) if s.lower() in t.lower()), None)
    try:
        known = set(content.corp().sector.unique())
        sector = sector if sector in known else None
    except Exception:  # noqa: BLE001
        pass
    return {"borrower": m.group(1) if m else None, "sector": sector, "book": r.get("book") or "corporate",
            "template": r["template"]}


def _first_para(sec: dict[str, Any]) -> str:
    for b in sec.get("blocks") or []:
        if b["kind"] == "paragraph":
            return b["text"].split("\n\n")[0]
    return ""


# ------------------------------------------------------------------ drafting


def draft_blocks(r: dict[str, Any], title: str) -> list[dict[str, Any]]:
    """Blocks for one section of this report, from the books."""
    ctx = _context(r)
    t = title.lower()
    sector, borrower = ctx["sector"], ctx["borrower"]
    if borrower:
        try:
            for name, blocks in content.borrower_sections(borrower):
                if name.lower() == t or name.lower() in t or t in name.lower():
                    return blocks
        except LookupError:
            pass
    if sector:
        for name, blocks in content.sector_section(sector):
            if name.lower() == t:
                return blocks
    if "executive summary" in t or t in ("summary", "summary and verdict"):
        others = [s for s in r["sections"] if s["title"].lower() != t and s.get("blocks")]
        now, before = content.corp_totals(), content.corp_totals(content.CORP_PRIOR)
        lead = (f"Corporate ECL is {content.mn_words(now['ecl'])} at {content.CORP_PERIOD} "
                f"({content.mn_words(now['ecl'] - before['ecl'])} on the quarter; coverage {now['coverage'] * 100:.2f}%), "
                f"with Stage 2 at {now['stage2_share'] * 100:.1f}% of EAD.")
        if r.get("book") == "retail":
            rt = content.retail_totals()
            lead = (f"Retail ECL is {content.mn_words(rt['ecl'])} at {content.RETAIL_PERIOD} on "
                    f"{content.mn_words(rt['ead'])} of EAD; Stage 2 is {rt['stage2_share'] * 100:.1f}% of EAD.")
        points = [f"**{s['title']}:** {_first_para(s)[:300]}" for s in others[:5] if _first_para(s)]
        return [{"kind": "paragraph", "text": lead}, *([{"kind": "bullets", "items": points}] if points else [])]
    if "stage migration" in t and r.get("book") != "retail":
        now, before = content.corp_totals(), content.corp_totals(content.CORP_PRIOR)
        return [{"kind": "paragraph", "text": (
            f"Stage 2 is {now['stage2_share'] * 100:.1f}% of corporate EAD at {content.CORP_PERIOD}, against "
            f"{before['stage2_share'] * 100:.1f}% at {content.CORP_PRIOR}. The chart shows the stage mix of EAD in "
            "both quarters.")}, content.stage_chart(sector)]
    if re.search(r"\becl by (sector|product)\b", t):
        if r.get("book") == "retail":
            return content.retail_section()[1]
        tbl = content.sector_table()
        top = tbl["rows"][0]
        return [{"kind": "paragraph", "text": (
            f"{top['sector']} carries the largest share of corporate EAD ({top['share'] * 100:.1f}%). The table "
            "gives EAD, ECL and coverage by sector with the movement on the quarter.")}, tbl]
    if any(w in t for w in ("portfolio overview", "credit quality and ecl", "credit quality", "composition", "results",
                            "ecl overview")):
        if r.get("book") == "retail":
            return content.retail_section()[1]
        return content.portfolio_section()[1]
    if any(w in t for w in ("early warning", "emerging risks")):
        return content.ews_section(sector=sector)[1]
    if "concentration" in t:
        tbl = content.sector_table()
        top = tbl["rows"][0]
        return [{"kind": "paragraph", "text": (
            f"The largest sector is {top['sector']} at {top['share'] * 100:.1f}% of corporate EAD against the 18% "
            "limit in CP-1.3. No sector is above its limit.")} if top["share"] <= 0.18 else
            {"kind": "paragraph", "text": f"{top['sector']} is above the CP-1.3 sector limit."}, tbl]
    if "risk appetite" in t:
        now = content.corp_totals()
        top = content.sector_table()["rows"][0]
        return [{"kind": "rag", "title": "Credit risk appetite", "items": [
            {"test": "Largest sector share of EAD (CP-1.3)", "value": top["share"], "format": "pct",
             "threshold": "limit 18%; amber above 15%", "status": "green" if top["share"] <= 0.15 else
             ("amber" if top["share"] <= 0.18 else "red"), "comment": top["sector"]},
            {"test": "Stage 2 share of EAD", "value": now["stage2_share"], "format": "pct",
             "threshold": "amber above 20%; red above 30%", "status": "green" if now["stage2_share"] <= 0.2 else
             ("amber" if now["stage2_share"] <= 0.3 else "red"), "comment": ""},
            {"test": "ECL coverage", "value": now["coverage"], "format": "pct", "threshold": "amber above 4%; red above 6%",
             "status": "green" if now["coverage"] <= 0.04 else ("amber" if now["coverage"] <= 0.06 else "red"),
             "comment": ""}]}]
    if "borrowers for decision" in t:
        rows = content.ews_rows(top=8)
        return [{"kind": "paragraph", "text": "Borrowers on a high or critical Early Warning with the largest exposure, "
                                              "for decision or noting by the committee."},
                {"kind": "table", "title": "For decision",
                 "columns": [{"key": "borrower_id", "label": "Borrower", "format": "text"},
                             {"key": "name", "label": "Name", "format": "text"},
                             {"key": "rating", "label": "Rating", "format": "rating"},
                             {"key": "band", "label": "Band", "format": "text"},
                             {"key": "ead", "label": "EAD", "format": "sar"},
                             {"key": "ecl", "label": "ECL", "format": "sar"}], "rows": rows}]
    if any(w in t for w in ("scenario", "drivers")):
        s = sector or "Construction"
        cons = content.corp_totals(content.CORP_PERIOD, s)
        shock = cons["ecl"] * 0.3
        return [{"kind": "paragraph", "text": (
            f"What-If, Delta method: a 30% rise in {s} PDs adds about **{content.mn_words(shock)}** to ECL (first-order, "
            f"on {content.mn_words(cons['ecl'])} of sector ECL). Import the What-If scenario for the full decomposition.")},
            {"kind": "kpis", "items": [{"label": f"{s} ECL now", "value": content.sar(cons["ecl"]), "format": "sar"},
                                       {"label": "Under PD +30%", "value": content.sar(cons["ecl"] + shock),
                                        "format": "sar", "delta": content.sar(shock), "status": "amber"}]}]
    if "policy" in t:
        return [{"kind": "paragraph", "text": (
            "Policy checks against the active pack (pp-2026.2, including circular C-2026-03): concentration "
            "(CP-1.1 to CP-1.3), covenants (CP-2.1 to CP-2.3), staging (CP-3.3) and the construction sector watch "
            "(CP-3.4). Open Policy Docs for the clauses in full.")}]
    if any(w in t for w in ("recommendation", "actions", "outlook", "conditions")):
        return [{"kind": "bullets", "items": [
            "Note the quarter's ECL movement and its main contributors.",
            "Re-rate high and critical Early Warning names out of cycle (CP-3.2).",
            "Reflect circular C-2026-03 in the 2026Q3 staging and report the Stage 2 effect.",
            "Bring the What-If stress results to the next committee."]}]
    if r["template"] == "validation-report":
        return [{"kind": "paragraph", "text": (
            f"{title}: import the results from Scorecard Validation (“import the scorecard validation”); the tests, "
            "thresholds and red/amber/green verdicts arrive with their charts and tables.")}]
    return [{"kind": "paragraph", "text": f"{title}: to be completed."}]


# ------------------------------------------------------------------ revising


def _model(prompt: str) -> str | None:
    key = os.environ.get("PLAYBOOK_ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    try:
        import anthropic

        # Closed after the call: one client per paragraph otherwise keeps its sockets open until the GC runs.
        with anthropic.Anthropic(api_key=key) as client:
            msg = client.messages.create(model=os.environ.get("PLAYBOOK_MODEL", "claude-opus-5"), max_tokens=1200,
                                         messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        return store.BANNED.sub("", text) or None
    except Exception:  # noqa: BLE001 - the deterministic revision stands in
        return None


def revise_blocks(blocks: list[dict[str, Any]], how: str) -> list[dict[str, Any]]:
    out = []
    for b in blocks:
        b = dict(b)
        if b["kind"] == "paragraph":
            text = b["text"]
            llm = _model(f"Revise this credit report paragraph ({how}). Keep every number exactly. Plain prose, "
                         f"markdown bold allowed, no preamble:\n\n{text}")
            if llm:
                b["text"] = llm[: store.MAX_TEXT]
            elif how == "shorter":
                sents = re.split(r"(?<=[.!?])\s+", text)
                b["text"] = " ".join(sents[: max(1, (len(sents) + 1) // 2)])
            elif how == "bullets":
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
                out.append({"kind": "bullets", "items": sents[:40]})
                continue
            elif how == "formal":
                b["text"] = (text.replace("isn't", "is not").replace("doesn't", "does not").replace("it's", "it is")
                             .replace("can't", "cannot").replace(" won't", " will not"))
                if not b["text"].startswith("The committee"):
                    b["text"] = b["text"]
            elif how == "longer":
                b["text"] = text + ("\n\nThe figures are taken from the bank's books at the reporting date and link "
                                    "back to their source in CreditProbe; movements are measured against the prior period.")
        out.append(b)
    return out


# ------------------------------------------------------------------- parsing

def _find_section(r: dict[str, Any], text: str) -> dict[str, Any] | None:
    t = text.lower()
    best, score = None, 0
    for s in r["sections"]:
        words = [w for w in re.split(r"\W+", s["title"].lower()) if len(w) > 2 and w not in ("and", "the")]
        n = sum(1 for w in words if w in t)
        if s["title"].lower() in t:
            n += 10
        if n > score:
            best, score = s, n
    return best


_IMPORT_TYPES = [(("cbuae", "crm compliance", "compliance summary", "regulatory breach"), "crm-compliance"),
                 (("attention",), "attention-item"), (("early warning", "warning list", "ews", "watch list"), "early-warning-list"),
                 (("borrower 360", "borrower", "b360", "cb0", "cb1", "rc0"), "borrower"),
                 (("what-if", "what if", "whatif", "scenario", "stress"), "whatif-scenario"),
                 (("data domains", "data builder", "extract"), "data-extract"), (("analysis", "analyses"), "analysis"),
                 (("investigation",), "investigation"), (("cockpit", "answer", "thread"), "cockpit-thread"),
                 (("scorecard", "validation"), "scorecard-validation")]


def _import_type(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b[cr][bc]\d{4,6}\b", t):
        return "borrower"
    for words, typ in _IMPORT_TYPES:
        if any(w in t for w in words):
            return typ
    return None


_TARGET = {"attention-item": ["credit quality", "early warning", "movements", "portfolio overview"],
           "early-warning-list": ["early warning", "emerging risks"],
           "borrower": ["borrowers for decision", "borrower profile"],
           "whatif-scenario": ["scenarios", "results", "scenario definition"],
           "whatif-thread": ["scenarios", "results"], "data-extract": ["composition", "portfolio overview"],
           "analysis": ["portfolio overview", "composition"], "investigation": ["credit quality", "emerging risks"],
           "scorecard-validation": ["summary and verdict", "discrimination"], "cockpit-thread": [],
           "crm-compliance": ["policy compliance", "regulatory", "compliance", "emerging risks", "credit quality"]}


def import_into(con: sqlite3.Connection, me: str, r: dict[str, Any], type_: str, id_: str, cookie: str | None,
                position: str = "") -> tuple[dict[str, Any], str, str]:
    src, title, blocks = resolvers.resolve(type_, id_, cookie)
    # Into the template section that fits, when it is still empty; otherwise a new section after it.
    if not position:
        for want in _TARGET.get(type_, []):
            tgt = next((s for s in r["sections"] if s["title"].lower() == want), None)
            if tgt is not None:
                if tgt["status"] == "empty":
                    rep = store.update_section(con, me, r["id"], tgt["id"], blocks=blocks, action="import",
                                               summary=f"Imported {src['label']} into “{tgt['title']}”",
                                               status="imported")
                    _set_source(con, r["id"], tgt["id"], src)
                    return store.report(con, r["id"], me), tgt["id"], tgt["title"]
                position = f"after:{tgt['id']}"
                break
    rep, sid, _ = store.add_section(con, me, r["id"], title, blocks, position or "end", src, action="import",
                                    summary=f"Imported {src['label']}")
    return rep, sid, title


def _set_source(con: sqlite3.Connection, rid: str, sid: str, src: dict[str, Any]) -> None:
    row = store._row(con, rid)
    secs = store._l(row["sections"], [])
    for s in secs:
        if s["id"] == sid:
            s["source"] = store.clean_source(src)
    con.execute("UPDATE reports SET sections=? WHERE id=?", (store._j(secs), rid))


def _date_in(text: str) -> str | None:
    m = re.search(r"\b(20\d\d-\d\d-\d\d)\b", text)
    if m:
        return m.group(1)
    t = text.lower()
    if "tomorrow" in t:
        return (date.today() + timedelta(days=1)).isoformat()
    m = re.search(r"in (\d+) days?", t)
    if m:
        return (date.today() + timedelta(days=int(m.group(1)))).isoformat()
    if "next week" in t:
        return (date.today() + timedelta(days=7)).isoformat()
    return None


def _users_in(text: str) -> list[str]:
    t = text.lower()
    out = []
    for u, info in store._USERS.items():
        first = info["name"].split()[0].lower()
        if u in t or info["name"].lower() in t or re.search(rf"\b{re.escape(first)}\b", t):
            out.append(u)
    return out


# --------------------------------------------------------------------- turns


def report_turn(con: sqlite3.Connection, me: str, report_id: str, text: str, cookie: str | None) -> dict[str, Any]:
    text = store.clean_text(text, "Message", 4000)
    if not text:
        raise store.Invalid("Write a message.")
    tid = f"th_{report_id}"
    r = store.report(con, report_id, me)
    user_msg = store.add_message(con, tid, report_id, "user", me, text)
    t = text.lower()
    actions: list[dict[str, Any]] = []
    reply = ""
    try:
        if re.search(r"\b(send|submit)\b.*\breview\b", t) or t.strip() in ("send for review", "submit"):
            if not r["reviewers"]:
                names = _users_in(text)
                if names:
                    store.update_report(con, me, report_id, {"reviewers": [n for n in names if n != me]})
            store.set_status(con, me, report_id, "in_review", "")
            reply, actions = "Sent for review.", [{"kind": "status", "label": "In review"}]
        elif re.search(r"\bapprove", t):
            store.set_status(con, me, report_id, "approved", "")
            reply, actions = "Approved.", [{"kind": "status", "label": "Approved"}]
        elif re.search(r"\bpresent", t):
            store.set_status(con, me, report_id, "presented", "")
            reply, actions = "Marked as presented.", [{"kind": "status", "label": "Presented"}]
        elif re.search(r"\b(reopen|send back|back to draft)\b", t):
            store.set_status(con, me, report_id, "draft", "")
            reply, actions = "Back to Draft.", [{"kind": "status", "label": "Draft"}]
        elif re.search(r"\bdue\b", t) and _date_in(text):
            d = _date_in(text)
            store.update_report(con, me, report_id, {"due_date": d})
            reply = f"Due date set to {d}."
        elif re.search(r"\breviewers?\b", t) and _users_in(text):
            names = [n for n in _users_in(text) if n != r["owner"]["username"]]
            store.update_report(con, me, report_id, {"reviewers": names})
            reply = "Reviewers: " + ", ".join(store.person(n)["name"] for n in names) + "."
        elif re.search(r"\b(import|bring in|pull in|attach)\b", t) or (re.search(r"\badd\b", t) and _import_type(text)):
            typ = _import_type(text)
            got = resolvers.sources(cookie, typ or "", text)
            cands = got["sources"]
            if not cands:
                why = "; ".join(u["reason"] for u in got["unavailable"]) or "nothing matched"
                reply = f"I could not find anything to import ({why}). Use Import to browse what is available."
            else:
                pick = cands[0]
                rep, sid, title = import_into(con, me, r, pick["type"], pick["id"], cookie)
                reply = f"Imported {pick['label']} into “{title}”, with its charts and tables."
                actions = [{"kind": "imported", "section_id": sid, "label": title}]
        elif re.search(r"\b(shorter|shorten|longer|expand|more formal|formal|bullet|tighten|concise)\b", t):
            sec = _find_section(r, text)
            if sec is None or not sec.get("blocks"):
                reply = "Which section? Name it, for example “make the executive summary shorter”."
            else:
                how = ("shorter" if re.search(r"shorter|shorten|tighten|concise", t) else "longer" if re.search(
                    r"longer|expand", t) else "bullets" if "bullet" in t else "formal")
                store.update_section(con, me, report_id, sec["id"], blocks=revise_blocks(sec["blocks"], how),
                                     action="revise", summary=f"Revised “{sec['title']}” ({how})")
                reply = f"Revised “{sec['title']}” ({how})."
                actions = [{"kind": "section_revised", "section_id": sec["id"], "label": sec["title"]}]
        elif re.search(r"\b(draft|write|fill|complete|prepare|redo|rewrite)\b", t):
            every = re.search(r"\b(all|every|each|empty|remaining|whole|everything)\b", t)
            targets = [s for s in r["sections"] if s["status"] == "empty"] if every else []
            if not every:
                sec = _find_section(r, text)
                targets = [sec] if sec else []
            if not targets:
                reply = ("Every section already has text. Name one to redraft, for example “redraft the portfolio "
                         "overview”." if every else "Which section? For example “draft the executive summary”.")
            # Summaries last, so they summarise the drafted sections.
            targets.sort(key=lambda s: 1 if "summary" in s["title"].lower() else 0)
            for sec in targets:
                cur = store.report(con, report_id, me)
                store.update_section(con, me, report_id, sec["id"], blocks=draft_blocks(cur, sec["title"]),
                                     action="draft", summary=f"Drafted “{sec['title']}”", status="drafted")
                actions.append({"kind": "section_drafted", "section_id": sec["id"], "label": sec["title"]})
            if targets:
                reply = "Drafted " + ", ".join(f"“{s['title']}”" for s in targets) + " from the books."
        elif re.search(r"\b(summar|status|where are we|overview of the report)\b", t):
            filled = sum(1 for s in r["sections"] if s.get("blocks"))
            reply = (f"“{r['title']}” is {r['status_label']}, version {r['version']}: {filled} of {len(r['sections'])} "
                     f"sections have text. Owner {r['owner']['name']}; reviewers "
                     f"{', '.join(p['name'] for p in r['reviewers']) or 'none yet'}; due {r['due_date'] or 'not set'}.")
        else:
            reply = ("I can draft or revise a section, import work from across CreditProbe (Cockpit answers, "
                     "investigations, attention items, Early Warning lists, Borrower 360, What-If, Data Domains, analyses), "
                     "and move the report through review. Try one of the suggestions.")
    except (store.Invalid, store.NotPermitted, store.NotFound) as exc:
        reply = str(exc)
    bot = store.add_message(con, tid, report_id, "assistant", None, reply, actions, SUGGEST[:4])
    return {"messages": [user_msg, bot], "report": store.report(con, report_id, me)}


def start_turn(con: sqlite3.Connection, me: str, text: str, cookie: str | None,
               thread_id: str | None = None) -> dict[str, Any]:
    """The chat box on the Playbook home: start a document, or answer."""
    text = store.clean_text(text, "Message", 4000)
    if not text:
        raise store.Invalid("Write a message.")
    from backend.playbook_v5 import ai
    talk = ai.start_conversation(con, me, text, thread_id, cookie)
    if talk is not None:
        return talk
    from backend.convo import trace as _trace
    _trace.step("planning", "Choosing the template and the sections")
    tpl = templates.guess(text)
    m = re.search(r"\b(CB\d{5})\b", text.upper())
    sector = next((s for s in sorted(SECTORS, key=len, reverse=True) if s.lower() in text.lower()), None)
    wants = re.search(r"\b(draft|start|create|write|prepare|new|build|make)\b", text.lower())
    if m and not tpl:
        tpl = "borrower-credit-memo"
    if sector and not tpl:
        tpl = "portfolio-review"
    if not (tpl and (wants or m or sector)):
        # R14 n (K16): a message typed inside an open thread continues it; only a new question opens a new thread.
        thread_id = thread_id or store.new_id("th")
        u = store.add_message(con, thread_id, None, "user", me, text)
        b = store.add_message(con, thread_id, None, "assistant", None,
                              "Tell me what to start, for example “Draft a credit memo for CB01312”, “Start a portfolio "
                              "review of the Construction sector” or “Prepare the Q3 credit committee pack”. Or open a "
                              "report below and continue it.", [], ["Draft a credit memo for CB01312",
                                                                    "Start a portfolio review of Real Estate",
                                                                    "Prepare a risk committee report"])
        return {"thread_id": thread_id, "report": None, "messages": [u, b]}
    book = "retail" if re.search(r"\bretail\b", text.lower()) else "corporate"
    period = content.RETAIL_PERIOD if book == "retail" else content.CORP_PERIOD
    if tpl == "borrower-credit-memo" and m:
        try:
            nm = content.borrowers()
            name = str(nm[nm.borrower_id == m.group(1)].borrower_name.iloc[-1])
        except (IndexError, KeyError):
            name = ""
        title = f"{m.group(1)} credit memo" + (f": {name}" if name else "")
    elif sector and tpl == "portfolio-review":
        title = f"{sector} sector review, {period}"
    else:
        title = f"{templates.name(tpl)}, {period}"
    rep = store.create_report(con, me, title, tpl, book, period, origin="template")
    rid = rep["id"]
    tid = f"th_{rid}"
    u = store.add_message(con, tid, rid, "user", me, text)
    _trace.step("querying", "Reading the books and drafting each section")
    drafted = []
    order = sorted(rep["sections"], key=lambda s: 1 if "summary" in s["title"].lower() else 0)
    for sec in order:
        cur = store.report(con, rid, me)
        blocks = draft_blocks(cur, sec["title"])
        if blocks and not blocks[0].get("text", "").endswith("to be completed."):
            store.update_section(con, me, rid, sec["id"], blocks=blocks, action="draft",
                                 summary=f"Drafted “{sec['title']}”", status="drafted")
            drafted.append({"kind": "section_drafted", "section_id": sec["id"], "label": sec["title"]})
    _trace.step("answering", "Writing the reply")
    b = store.add_message(con, tid, rid, "assistant", None,
                          f"Started “{title}” from the {templates.name(tpl)} template and drafted {len(drafted)} of "
                          f"{len(rep['sections'])} sections from the books. Ask me to revise any section, import work, "
                          "or send it for review.", [{"kind": "created", "label": title}, *drafted], SUGGEST[:4])
    return {"thread_id": tid, "report": store.report(con, rid, me), "messages": [u, b]}
