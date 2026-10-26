"""Playbook AI: the conversations of a report (PLAN_R4, 17:35 update).

Three conversations, each a scoped turn of the shared forked Cockpit loop (`backend/ai_work` on `backend/convo`):

  start      the chat at the top of Playbook. "I want to draft a corporate ECL report" opens a thread that
             discusses scope and structure, proposes the sections (each with what goes in and where its data
             comes from), takes changes ("add a section on concentrations", "drop the scenarios", "make it
             retail") and creates the report on "create it" (or the Create button), drafting every section from
             the books. Questions ("what is corporate ECL this quarter?") are answered from the books.
  section    each section's own thread, opened in the lower half of the section. Its data access follows the
             section: Early Warning sections read Early Warning, IFRS 9 / ECL / portfolio sections the Cockpit
             books, What-If sections the What-If engine and library (a worked scenario imports with its waterfall,
             segment table and commentary), scorecard sections the validations, borrower sections Borrower 360.
             It brainstorms what must go in, drafts, revises, answers questions, and puts an answer into the
             section on request ("add this to the section").
  report     the right-hand assistant: a conversation over the whole report. Commands (draft, revise, import,
             status, reviewers, due date) still act; everything else is answered with the report's outline and
             the data behind it. Its suggestion chips are shortcuts only.

The process flow (templates, sections, status, comments, versions, Word export) is unchanged.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from backend.ai_work import agent, tools
from backend.convo.spec import PlanStep, Tool, ToolContext, ToolResult
from backend.playbook_v5 import assistant, content, proposal, store, templates

# ------------------------------------------------------------- section scope

_KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("ews", ("early warning", "emerging risk", "watch", "alert", "warning")),
    ("whatif", ("scenario", "what-if", "what if", "stress", "drivers", "management action", "overlay")),
    ("scorecard", ("scorecard", "discrimination", "calibration", "stability", "variables", "overrides",
                   "validation", "verdict", "scope and data", "findings")),
    ("borrower", ("borrower", "request and recommendation", "financial analysis", "facilities and security",
                  "risk rating", "conditions", "credit memo")),
]
KIND_LABEL = {"ews": "Early Warning data", "whatif": "What-If engine and saved scenarios", "scorecard": "Scorecard data",
              "borrower": "Borrower 360", "books": "Cockpit books"}

OUTLINE: dict[str, list[str]] = {
    "ews": ["The headline: how many names are high or critical now against the prior period, and their exposure",
            "The movement by band, and the reasons driving it (the rule set's top triggers)",
            "The named list: high and critical names with EAD, stage and the reason for each",
            "Where the warnings concentrate (sector or product)",
            "What the committee is asked to do: out-of-cycle reviews (CP-3.2), watchlist decisions"],
    "whatif": ["The scenario definition: the shocks, their calibration against history and their likelihood",
               "The result: ECL before and after, the change and the coverage move",
               "The waterfall: which step of the scenario moves ECL and by how much",
               "The segments that carry the change",
               "Management actions and the capital impact"],
    "scorecard": ["The verdict: fit for use or not, with the tests that are red or amber",
                  "Discrimination: Gini/AUC and KS against development",
                  "Calibration: observed against expected by grade (binomial and traffic light)",
                  "Stability: PSI on the score and the variables",
                  "Findings with their remedies and owners"],
    "borrower": ["The request and the recommendation in one paragraph",
                 "The borrower: sector, region, group and rating with its outlook",
                 "Exposure and security: EAD, ECL, stage and collateral by facility",
                 "Early Warning: band, score and the reasons",
                 "Policy compliance and the conditions the approval carries"],
    "books": ["The headline: ECL, coverage and Stage 2 share now against the prior period",
              "What moved ECL: stage migration, new exposure, parameter changes",
              "Where it sits: the sectors (or products) carrying the most ECL and their share",
              "Concentration and appetite: largest sector against the CP-1.3 limit",
              "The outlook and what the committee should note"],
}


def section_kind(report: dict[str, Any], section: dict[str, Any]) -> str:
    t = section["title"].lower()
    if report.get("template") == "validation-report":
        return "scorecard"
    for kind, words in _KINDS:
        if any(w in t for w in words):
            if kind == "borrower" and report.get("template") != "borrower-credit-memo" and "borrower" not in t:
                continue
            return kind
    if report.get("template") == "borrower-credit-memo" and "policy" not in t:
        return "borrower"
    if report.get("template") == "scenario-report":
        return "whatif"
    return "books"


def _books(report: dict[str, Any]) -> list[str]:
    b = report.get("book") or "corporate"
    return ["corporate", "retail"] if b == "both" else [b]


def section_domains(report: dict[str, Any], section: dict[str, Any]) -> list[str]:
    kind = section_kind(report, section)
    books = _books(report)
    if kind == "ews":
        return ["ews", *books]
    if kind == "whatif":
        return ["whatif", *books]
    if kind == "scorecard":
        return ["scorecard"]
    if kind == "borrower":
        return ["b360", "corporate", "ews"]
    return [*books, "ews"]


def _text_of(blocks: list[dict[str, Any]], limit: int = 2500) -> str:
    out = []
    for b in blocks or []:
        if b.get("kind") in ("paragraph", "callout", "heading"):
            out.append(str(b.get("text", "")))
        elif b.get("kind") == "bullets":
            out += [f"- {x}" for x in b.get("items") or []]
        elif b.get("kind") == "table":
            out.append(f"[table: {b.get('title', '')}, {len(b.get('rows') or [])} rows]")
        elif b.get("kind") == "chart":
            out.append(f"[chart: {b.get('title', '')}]")
    return "\n".join(out)[:limit]


def _outline_tool(report: dict[str, Any], section: dict[str, Any]) -> Tool:
    kind = section_kind(report, section)

    def run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        items = OUTLINE[kind]
        return ToolResult(summary=(f"For “{section['title']}”, I would cover:\n"
                                   + "\n".join(f"{i}. {x}." for i, x in enumerate(items, 1))
                                   + f"\n\nWhat the {KIND_LABEL[kind]} say now:"),
                          data={"section": section["title"], "kind": kind, "items": items,
                                "data_access": KIND_LABEL[kind]})
    return Tool("section_outline", "What a section of this kind must cover (a checklist for brainstorming).",
                {"type": "object", "properties": {}}, run, message="Outlining the section")


def section_scope(report: dict[str, Any], section: dict[str, Any]) -> agent.Scope:
    kind = section_kind(report, section)
    m = re.search(r"\b(CB\d{5})\b", report["title"].upper())
    focus: dict[str, Any] = {"book": _books(report)[0]}
    sector = assistant._context(report).get("sector")
    if sector and focus["book"] == "corporate":
        focus["segment"] = sector
    others = ", ".join(f"“{s['title']}” ({s['status']})" for s in report["sections"] if s["id"] != section["id"])
    ctx = (f"Report: “{report['title']}” ({templates.name(report['template'])}, {report.get('book') or 'corporate'} "
           f"book, {report.get('period') or ''}). This thread belongs to the section “{section['title']}”"
           + (f" about borrower {m.group(1)}" if m else "") + f". Other sections: {others}.\n"
           f"The section's current text:\n{_text_of(section.get('blocks') or []) or '(empty)'}")
    return agent.Scope(
        domains=[*section_domains(report, section), "product"], name=f"the section “{section['title']}” of “{report['title']}”",
        focus=focus, context=ctx, extra_tools=[_outline_tool(report, section)],
        charter=("You are the writing partner for one section of a bank's credit report in CreditProbe's Playbook. "
                 "You brainstorm what the section must say, answer questions with real figures from the section's "
                 "data, and propose wording the author can put into the section. Be concrete: name the figures, "
                 "the movements and the names that matter."),
        plan_hook=lambda q, intent: _brainstorm_plan(kind, focus, q, m) or (
            [PlanStep("borrower_profile", {"borrower_id": m.group(1)})] if m and kind == "borrower"
            and intent.kind == "book" else []),
        plan_only_hook=lambda q, intent: bool(BRAINSTORM.search(q)) or bool(m and kind == "borrower"
                                                                            and intent.kind == "book"))


def _brainstorm_plan(kind: str, focus: dict[str, Any], q: str, m: Any = None) -> list[PlanStep]:
    """Brainstorming a section: the checklist, then the one headline query that grounds it."""
    if not BRAINSTORM.search(q):
        return []
    book = focus.get("book") or "corporate"
    head = {"ews": PlanStep("ews_headline", {"book": book, **({"segment": focus["segment"]} if focus.get("segment") else {})}),
            "whatif": PlanStep("whatif_library", {"book": book}),
            "scorecard": PlanStep("scorecard_overview", {}),
            "borrower": PlanStep("borrower_profile", {"borrower_id": m.group(1)}) if m else None,
            "books": PlanStep("book_figures", {"book": book, **({"segment": focus["segment"]} if focus.get("segment") else {})})}[kind]
    return [PlanStep("section_outline", {}), *([head] if head else [])]


BRAINSTORM = re.compile(r"\bwhat (should|must|do i|do we|would you|to|goes)\b.*\b(go|include|cover|put|say|write)|"
                        r"\bbrainstorm|\bideas?\b|\boutline\b|\bstructure\b|\bwhat goes in\b|\bwhat should this\b|"
                        r"\bhow should (i|we) (write|structure|approach)", re.I)

# ----------------------------------------------------------------- helpers

_UNIT_FMT = {"sar_mn": "sar", "pct": "pct", "int": "int", "num": "num", "text": "text"}


def table_block(t: dict[str, Any]) -> dict[str, Any]:
    """An answer table (SAR million, percent) as a report block (riyals, fractions)."""
    cols = t.get("columns") or []
    rows = []
    for r in (t.get("rows") or [])[:40]:
        row = {}
        for c in cols:
            v = r.get(c["key"])
            u = c.get("unit", "text")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                v = v * 1e6 if u == "sar_mn" else v / 100 if u == "pct" else v
            elif v is not None and not isinstance(v, str):
                v = str(v)
            row[c["key"]] = v
        rows.append(row)
    return {"kind": "table", "title": str(t.get("title") or "")[:200],
            "columns": [{"key": c["key"], "label": c.get("label") or c["key"],
                         "format": _UNIT_FMT.get(c.get("unit", "text"), "text")} for c in cols], "rows": rows}


def reply_blocks(text: str, tables: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What an answer becomes in a section: its prose (markdown tables as real tables, PLAN_R5 P2), charts, tables."""
    out: list[dict[str, Any]] = proposal.markdown_blocks(proposal.split_fenced(text or "")[0])
    out += [b for b in blocks if b.get("kind") in ("chart", "kpis", "table", "rag")]
    out += [table_block(t) for t in tables]
    return out[: store.MAX_BLOCKS]


def section_proposal(text: str, mat: dict[str, Any]) -> dict[str, Any]:
    """PLAN_R5 P3: the structured proposal an answer carries beside its chat text (only what belongs in the report)."""
    p = proposal.build(text, mat)
    return {"kind": "section_proposal", "blocks": p["blocks"][: store.MAX_BLOCKS], "placement": p["placement"],
            "source": p["source"]}


def merge_answer(con: sqlite3.Connection, me: str, report_id: str, section_id: str, msg: dict[str, Any],
                 request: str = "") -> tuple[dict[str, Any], str, int]:
    """Merge one answer's proposal into its section (one version). Returns (report, where, version)."""
    mat = next((a for a in msg.get("actions") or [] if a.get("kind") == "answer"), None)
    if msg.get("role") != "assistant" or mat is None or mat.get("refused"):
        raise store.Invalid("Only an answer can be added to a section.")
    prop = next((a for a in msg.get("actions") or [] if a.get("kind") == "section_proposal"), None) \
        or section_proposal(msg.get("text") or "", mat)
    if not prop.get("blocks"):
        raise store.Invalid("This answer proposes nothing for the report.")
    r = store.report(con, report_id, me)
    sec = _find(r, section_id)
    place = proposal.placement_of(request) if request else prop.get("placement") or {"mode": "end"}
    blocks, where = proposal.merge(sec["title"], sec.get("blocks") or [], prop, place)
    if len(blocks) > store.MAX_BLOCKS:
        raise store.Invalid(f"A section has up to {store.MAX_BLOCKS} blocks; shorten it before adding more.")
    rep = store.update_section(con, me, report_id, section_id, blocks=blocks, action="assistant-merge",
                               summary=f"Added the assistant's proposal to “{sec['title']}” ({where})")
    return rep, where, int(rep["version"])


def undo_merge(con: sqlite3.Connection, me: str, report_id: str, section_id: str, version: int | None = None) -> dict[str, Any]:
    """One undo: the section as it was before the merge (version - 1), recorded as a new version."""
    r = store.report(con, report_id, me)
    sec = _find(r, section_id)
    if version is None:
        row = con.execute("SELECT version FROM report_versions WHERE report_id=? AND action='assistant-merge' "
                          "AND summary LIKE ? ORDER BY version DESC LIMIT 1",
                          (report_id, f"%“{sec['title']}”%")).fetchone()
        if row is None:
            raise store.Invalid("There is no merge to undo in this section.")
        version = int(row["version"])
    before = store.version(con, report_id, int(version) - 1)["report"]
    old = next((s for s in before["sections"] if s["id"] == section_id), None)
    if old is None:
        raise store.Invalid("The section did not exist before that version.")
    return store.update_section(con, me, report_id, section_id, blocks=old.get("blocks") or [], action="undo",
                                summary=f"Undid the merge into “{sec['title']}” (back to version {int(version) - 1})",
                                status=old.get("status") or None)


def _material(reply: dict[str, Any]) -> dict[str, Any]:
    """The rich part of a reply kept on the message (tables, figures, charts, links, what was understood)."""
    tables = [dict(t, rows=t["rows"][:40]) for t in reply.get("tables") or []][:4]
    return {"kind": "answer", "tables": tables, "table_blocks": [table_block(t) for t in tables],
            "figures": reply.get("figures") or [], "blocks": (reply.get("blocks") or [])[:4],
            "citations": reply.get("citations") or [], "refused": bool(reply.get("refused")),
            "understood": reply.get("understood") or {}, "stages": reply.get("stages") or [],
            "source": reply.get("source") or "", "removed": (reply.get("validation") or {}).get("removed") or []}


def _history(con: sqlite3.Connection, thread_id: str) -> list[dict[str, Any]]:
    out = []
    for m in store.thread(con, thread_id)[-12:]:
        und = next((a.get("understood") for a in m.get("actions") or [] if a.get("kind") == "answer"), None)
        out.append({"role": m["role"], "text": m["text"], **({"understood": und} if und else {})})
    return out


def section_thread_id(report_id: str, section_id: str) -> str:
    return f"th_{report_id}__{section_id}"


def _find(r: dict[str, Any], section_id: str) -> dict[str, Any]:
    sec = next((s for s in r["sections"] if s["id"] == section_id), None)
    if sec is None:
        raise store.NotFound(f"There is no section {section_id!r} in this report.")
    return sec


# ------------------------------------------------------------ section turns

_APPLY = re.compile(r"\b(add|insert|put|use|paste|drop)\b.*\b(this|that|it|the (table|list|answer|chart|text))\b.*"
                    r"\b(section|in|into|here)\b|^(add|insert) (this|that|it)\b|\buse (this|that)\b|"
                    r"^\s*replace\b.*\b(with|by) (this|that|it)\b", re.I)
_DRAFT = re.compile(r"^\s*(please\s+|can you\s+|could you\s+)?(draft|write|fill|redraft|rewrite|prepare)\b|"
                    r"\bdraft (it|this|the section)\b", re.I)
_REVISE = re.compile(r"\b(shorter|shorten|longer|expand|more formal|formal|bullets?|tighten|concise)\b", re.I)
_IMPORT_SCN = re.compile(r"\b(import|bring in|pull in|add)\b.*\b(scenario|what-?if|stress|oil|recession|rates|"
                         r"downgrade|unemployment|house prices?)\b", re.I)

SECTION_CHIPS = {
    "ews": ["What should go in this section?", "Who are the critical names and why?", "Draft it from the data",
            "Add this to the section"],
    "whatif": ["What should go in this section?", "Import the oil price shock scenario", "Explain the waterfall",
               "Draft it from the data"],
    "scorecard": ["What should go in this section?", "What is wrong with the scorecards?", "Draft it from the data"],
    "borrower": ["What should go in this section?", "Summarise this borrower's risk", "Draft it from the data"],
    "books": ["What should go in this section?", "What drove ECL this quarter?", "ECL by sector",
              "Draft it from the data"],
}


def import_scenario_blocks(report: dict[str, Any], text: str, cookie: str | None) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
    """A worked What-If scenario for a section: a saved scenario from the What-If service when one matches, else
    the library scenario run through the engine. Returns (blocks, label, source)."""
    from backend.playbook_v5 import resolvers
    t = text.lower()
    try:
        got = resolvers.sources(cookie, "whatif-scenario", "")
        cands = [s for s in got["sources"] if s["type"] == "whatif-scenario"]
        words = [w for w in re.findall(r"[a-z]{4,}", t) if w not in ("import", "scenario", "bring", "worked", "section",
                                                                     "what", "into", "this", "with", "from")]
        pick = next((s for s in cands if any(w in s["label"].lower() for w in words)), None)
        if pick:
            src, title, blocks = resolvers.resolve("whatif-scenario", pick["id"], cookie)
            if any(b.get("kind") == "chart" and (b.get("figure") or {}).get("data", [{}])[0].get("type") == "waterfall"
                   for b in blocks):
                return blocks, src["label"], src
    except Exception:  # noqa: BLE001 - the What-If service may not run here; the engine is local
        pass
    book = _books(report)[0]
    key = tools.scenario_key(book, t) or ("oil-shock" if book == "corporate" else "unemployment")
    r = tools.whatif_scenario(book, key)
    f = {x["key"]: x["value"] for x in r.figures}
    rows = r.table["rows"]
    top = rows[:3]
    commentary = (f"**{r.extra['scenario']}.** Under the Delta method the scenario takes {book} ECL from "
                  f"SAR {f['reported_ecl']:,.1f}m to SAR {f['scenario_ecl']:,.1f}m at {r.extra['period']}, a change of "
                  f"SAR {f['change']:,.1f}m ({f['change_pct']:+.2f}%), with coverage moving from "
                  f"{f['coverage_before']:.2f}% to {f['coverage_after']:.2f}%. The change is concentrated in "
                  + ", ".join(f"{x['segment']} (SAR {x['change']:,.1f}m)" for x in top) + ".")
    kpis = {"kind": "kpis", "items": [
        {"label": "ECL before", "value": f["reported_ecl"] * 1e6, "format": "sar"},
        {"label": "ECL under the scenario", "value": f["scenario_ecl"] * 1e6, "format": "sar",
         "delta": f["change"] * 1e6, "status": "amber"},
        {"label": "Change", "value": f["change_pct"] / 100, "format": "pct"}]}
    blocks = [{"kind": "paragraph", "text": commentary}, kpis, *r.blocks, table_block(r.table)]
    src = {"type": "whatif-scenario", "id": f"library:{book}:{key}", "label": f"What-If: {r.extra['scenario']}",
           "href": f"/what-if?domain={book}"}
    return blocks, f"What-If: {r.extra['scenario']}", src


def section_turn(me: str, report_id: str, section_id: str, text: str, cookie: str | None) -> dict[str, Any]:
    """One turn in a section's thread. The conversation runs outside the store lock; writes take it briefly."""
    text = store.clean_text(text, "Message", 4000)
    if not text:
        raise store.Invalid("Write a message.")
    tid = section_thread_id(report_id, section_id)
    with store.db() as con:
        r = store.report(con, report_id, me)
        sec = _find(r, section_id)
        hist = _history(con, tid)
        user_msg = store.add_message(con, tid, report_id, "user", me, text)
    kind = section_kind(r, sec)
    chips = SECTION_CHIPS[kind]
    actions: list[dict[str, Any]] = []
    reply_text = ""
    write: tuple[str, Any] | None = None
    if _APPLY.search(text) and not _DRAFT.search(text):
        last = next((m for m in reversed(store_thread(tid)) if m["role"] == "assistant"
                     and any(a.get("kind") == "answer" and not a.get("refused") for a in m.get("actions") or [])), None)
        if last is None:
            reply_text = "There is no answer in this thread to add yet. Ask a question first, then add the answer."
        else:
            write = ("apply", last)
    elif _IMPORT_SCN.search(text) and kind in ("whatif", "books"):
        blocks, label, src = import_scenario_blocks(r, text, cookie)
        write = ("import", (blocks, label, src))
    elif _DRAFT.search(text):
        write = ("draft", None)
    elif _REVISE.search(text) and sec.get("blocks"):
        how = ("shorter" if re.search(r"shorter|shorten|tighten|concise", text, re.I) else
               "longer" if re.search(r"longer|expand", text, re.I) else
               "bullets" if re.search(r"bullet", text, re.I) else "formal")
        write = ("revise", how)
    reply: dict[str, Any] = {}
    if write is None and not reply_text:
        reply = agent.converse(text, section_scope(r, sec), hist, purpose="playbook-section")
        reply_text = proposal.split_fenced(reply["text"])[0]
        mat = _material(reply)
        actions = [mat]
        if not reply.get("refused"):
            prop = section_proposal(reply["text"], mat)
            if prop["blocks"]:
                actions += [prop, {"kind": "can_apply", "section_id": section_id, "label": sec["title"]}]
        chips = (reply.get("suggestions") or [])[:2] + [c for c in chips if c not in (reply.get("suggestions") or [])]
    with store.db() as con:
        if write is not None:
            what, arg = write
            cur = store.report(con, report_id, me)
            sec = _find(cur, section_id)
            if what == "apply":
                _rep, where, ver = merge_answer(con, me, report_id, section_id, arg, text)
                reply_text = f"Added the proposal to “{sec['title']}” {where}. Undo restores the section as it was."
                actions = [{"kind": "section_revised", "section_id": section_id, "label": sec["title"]},
                           {"kind": "merged", "section_id": section_id, "label": sec["title"], "version": ver,
                            "where": where}]
            elif what == "import":
                blocks, label, src = arg
                store.update_section(con, me, report_id, section_id,
                                     blocks=[*(sec.get("blocks") or []), *blocks][: store.MAX_BLOCKS], action="import",
                                     summary=f"Imported {label} into “{sec['title']}”",
                                     status="imported" if sec["status"] == "empty" else None)
                if src:
                    assistant._set_source(con, report_id, section_id, src)
                reply_text = (f"Imported {label} into “{sec['title']}”: the commentary, the key figures, the ECL "
                              "waterfall and the change by segment.")
                actions = [{"kind": "imported", "section_id": section_id, "label": sec["title"]}]
            elif what == "draft":
                blocks = assistant.draft_blocks(cur, sec["title"])
                store.update_section(con, me, report_id, section_id, blocks=blocks, action="draft",
                                     summary=f"Drafted “{sec['title']}”", status="drafted")
                reply_text = (f"Drafted “{sec['title']}” from the {KIND_LABEL[kind]}: "
                              + (assistant._first_para({"blocks": blocks})[:400] or "see the section above."))
                actions = [{"kind": "section_drafted", "section_id": section_id, "label": sec["title"]}]
            elif what == "revise":
                store.update_section(con, me, report_id, section_id, blocks=assistant.revise_blocks(sec["blocks"], arg),
                                     action="revise", summary=f"Revised “{sec['title']}” ({arg})")
                reply_text = f"Revised “{sec['title']}” ({arg})."
                actions = [{"kind": "section_revised", "section_id": section_id, "label": sec["title"]}]
        bot = store.add_message(con, tid, report_id, "assistant", None, reply_text, actions, chips[:4])
        rep = store.report(con, report_id, me)
    return {"thread_id": tid, "messages": [user_msg, bot], "report": rep}


def store_thread(thread_id: str) -> list[dict[str, Any]]:
    with store.db() as con:
        return store.thread(con, thread_id)


def section_thread(con: sqlite3.Connection, me: str, report_id: str, section_id: str) -> dict[str, Any]:
    r = store.report(con, report_id, me)
    sec = _find(r, section_id)
    kind = section_kind(r, sec)
    return {"thread_id": section_thread_id(report_id, section_id), "report_id": report_id, "section_id": section_id,
            "kind": kind, "data_access": KIND_LABEL[kind], "domains": section_domains(r, sec),
            "suggestions": SECTION_CHIPS[kind], "messages": store.thread(con, section_thread_id(report_id, section_id))}


def apply_message(con: sqlite3.Connection, me: str, report_id: str, section_id: str, message_id: str) -> dict[str, Any]:
    """Put one answer from a section thread into the section (the "Add to section" button): its proposal only."""
    m = con.execute("SELECT * FROM thread_messages WHERE id=? AND report_id=?", (message_id, report_id)).fetchone()
    if m is None:
        raise store.NotFound("There is no such message in this report.")
    rep, where, ver = merge_answer(con, me, report_id, section_id, store.message_row(m))
    rep["merged"] = {"section_id": section_id, "version": ver, "where": where}
    return rep


# -------------------------------------------------------- report assistant

_QUESTION = re.compile(r"\?\s*$|^\s*(what|why|how|which|who|where|when|is|are|does|do|did|can you explain|explain|"
                       r"tell me|compare|summari[sz]e|give me|show me|list)\b", re.I)
_COMMANDS = re.compile(r"^\s*(please\s+|can you\s+|could you\s+)?(draft|write|fill|complete|prepare|redo|rewrite|"
                       r"redraft|import|bring in|pull in|attach|add|send|submit|approve|present|reopen|set|make|"
                       r"shorten|tighten|expand|turn)\b|\bsend for review\b|\bdue\b.*\b20\d\d-\d\d-\d\d\b", re.I)


def is_conversation(text: str) -> bool:
    """A question or a discussion goes to the conversation; a command keeps the deterministic action."""
    if _COMMANDS.search(text) and not re.match(r"^\s*(what|why|how|which|who)\b", text, re.I):
        return False
    return bool(_QUESTION.search(text)) or not _COMMANDS.search(text)


def _report_tool(report: dict[str, Any]) -> Tool:
    def run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        rows = [{"section": s["title"], "status": s["status"], "blocks": len(s.get("blocks") or []),
                 "text": _text_of(s.get("blocks") or [], 600)} for s in report["sections"]]
        empty = [r["section"] for r in rows if r["status"] == "empty"]
        summ = (f"“{report['title']}” is {report['status_label']}, version {report['version']}; "
                f"{len(rows) - len(empty)} of {len(rows)} sections have text"
                + (f"; still empty: {', '.join(empty)}" if empty else "") + f". Owner {report['owner']['name']}; "
                f"reviewers {', '.join(p['name'] for p in report['reviewers']) or 'none yet'}; due "
                f"{report['due_date'] or 'not set'}.")
        return ToolResult(summary=summ, data={"empty": empty}, rows=rows)
    return Tool("read_report", "The report's sections: title, status and current text.", {"type": "object", "properties": {}},
                run, message="Reading the report")


def report_scope(report: dict[str, Any]) -> agent.Scope:
    books = _books(report)
    outline = "\n".join(f"- {s['title']} ({s['status']}): {_text_of(s.get('blocks') or [], 300)}"
                        for s in report["sections"])
    asks_report = re.compile(r"\b(report|section|missing|gaps?|empty|left|progress|status|summari[sz]e|"
                             r"consistent|review|ready)\b", re.I)
    return agent.Scope(
        domains=[*books, "ews", "whatif", "scorecard", "b360", "product"], name=f"the report “{report['title']}”",
        focus={"book": books[0]}, extra_tools=[_report_tool(report)],
        context=(f"Report “{report['title']}” ({templates.name(report['template'])}), {report['status_label']}, "
                 f"version {report['version']}. Sections:\n{outline}"),
        charter=("You are the assistant for a whole credit report in CreditProbe's Playbook. You discuss the report "
                 "with its author: what it says, what is missing, whether its figures hold against the books, and "
                 "what the committee will ask. Quote figures only from the tools of this turn."),
        plan_hook=lambda q, intent: [PlanStep("read_report", {})] if asks_report.search(q) else [],
        plan_only_hook=lambda q, intent: bool(asks_report.search(q)) and intent.kind == "book")


def report_conversation(me: str, report_id: str, text: str) -> dict[str, Any]:
    """A question about the report: the conversation runs outside the store lock."""
    text = store.clean_text(text, "Message", 4000)
    if not text:
        raise store.Invalid("Write a message.")
    tid = f"th_{report_id}"
    with store.db() as con:
        r = store.report(con, report_id, me)
        hist = _history(con, tid)
        user_msg = store.add_message(con, tid, report_id, "user", me, text)
    reply = agent.converse(text, report_scope(r), hist, purpose="playbook-report")
    chips = (reply.get("suggestions") or [])[:2] + [s for s in assistant.SUGGEST if s not in (reply.get("suggestions") or [])]
    with store.db() as con:
        bot = store.add_message(con, tid, report_id, "assistant", None, reply["text"], [_material(reply)], chips[:4])
        return {"messages": [user_msg, bot], "report": store.report(con, report_id, me)}


# ------------------------------------------------------------- start chat

_INTENT = re.compile(r"\b(i want|i'd like|i would like|i need|we need|help me|can we|could we|let's|lets|"
                     r"thinking|planning|i'm preparing|i am preparing|we should|should i)\b", re.I)
_CONFIRM = re.compile(r"^\s*(yes|yep|ok|okay|sure|go ahead|do it|create( it| the report)?|looks good|"
                      r"that works|perfect|great|start it|build it)\b", re.I)
_ADD = re.compile(r"\b(add|include)\b(?: a| an| the)?(?: section)?(?: on| about| for| covering)?\s+(.+)", re.I)
_DROP = re.compile(r"\b(drop|remove|delete|without|skip)\b(?: the)?(?: section)?(?: on| about)?\s+(.+)", re.I)

ECL_SECTIONS = ["Executive summary", "ECL overview", "Stage migration", "ECL by sector", "Early Warning",
                "Scenarios and overlays", "Policy and staging", "Recommendations"]
WHAT_GOES = {
    "books": "ECL, coverage and stage mix against the prior period, from the Cockpit books",
    "ews": "high and critical names, the movement and the reasons, from Early Warning",
    "whatif": "a worked What-If scenario with its waterfall and segment table",
    "scorecard": "the validation verdicts and findings, from Scorecard Validation",
    "borrower": "the borrower's profile, facilities and rating, from Borrower 360",
}


COVERS: list[tuple[str, str]] = [
    ("executive summary", "the headline figures, what moved and what the committee is asked to note"),
    ("summary", "the headline figures and the verdict"),
    ("ecl overview", "ECL, coverage and stage mix against the prior period, from the Cockpit books"),
    ("stage migration", "Stage 2 and Stage 3 movements on the quarter and what drove them"),
    ("by sector", "ECL and coverage by sector with the quarter's movement"),
    ("by product", "ECL and coverage by product with the month's movement"),
    ("concentration", "the largest sectors against the CP-1.3 limit"),
    ("risk appetite", "the appetite metrics against their thresholds, red/amber/green"),
    ("policy", "the clauses behind staging and limits, including circular C-2026-03"),
    ("recommendation", "the actions the committee is asked to take"),
    ("actions", "the actions taken and proposed, with owners"),
    ("outlook", "where the book is heading and what to watch"),
]


def covers(title: str, kind: str) -> str:
    t = title.lower()
    return next((c for k, c in COVERS if k in t), WHAT_GOES[kind])


def _ecl_report(text: str) -> bool:
    return bool(re.search(r"\b(ecl|ifrs ?9|provision(s|ing)?|impairment|expected credit loss)\b", text, re.I))


def proposal_for(text: str) -> dict[str, Any] | None:
    tpl = templates.guess(text)
    sector = next((s for s in sorted(assistant.SECTORS, key=len, reverse=True) if s.lower() in text.lower()), None)
    m = re.search(r"\b(CB\d{5})\b", text.upper())
    if _ecl_report(text) and tpl in (None, "portfolio-review"):
        tpl = "ecl-report"
    if m and not tpl:
        tpl = "borrower-credit-memo"
    if sector and not tpl:
        tpl = "portfolio-review"
    if not tpl and not re.search(r"\b(report|pack|memo|review|paper|document)\b", text, re.I):
        return None
    tpl = tpl or "portfolio-review"
    book = "retail" if re.search(r"\bretail\b", text, re.I) else "corporate"
    period = content.RETAIL_PERIOD if book == "retail" else content.CORP_PERIOD
    titles = ECL_SECTIONS if tpl == "ecl-report" else templates.sections(tpl)
    if tpl == "ecl-report" and book == "retail":
        titles = [t.replace("ECL by sector", "ECL by product") for t in titles]
    if tpl == "borrower-credit-memo" and m:
        title = f"{m.group(1)} credit memo"
    elif sector and tpl == "portfolio-review":
        title = f"{sector} sector review, {period}"
    elif tpl == "ecl-report":
        title = f"{book.capitalize()} IFRS 9 ECL report, {period}"
    else:
        title = f"{templates.name(tpl)}, {period}"
    fake = {"template": "borrower-credit-memo" if tpl == "borrower-credit-memo" else tpl, "title": title, "book": book}
    secs = [{"title": t, "kind": section_kind(fake, {"title": t}), "covers": ""} for t in titles]
    for s in secs:
        s["covers"] = covers(s["title"], s["kind"])
    return {"template": "portfolio-review" if tpl == "ecl-report" else tpl, "label": "IFRS 9 ECL report"
            if tpl == "ecl-report" else templates.name(tpl), "title": title, "book": book, "period": period,
            "sections": secs, "borrower": m.group(1) if m else None, "sector": sector}


def _proposal_text(p: dict[str, Any], lead: str) -> str:
    lines = [lead, "",
             f"**Scope.** The {p['book']} book at {p['period']}" + (f", {p['sector']}" if p.get("sector") else "")
             + (f", borrower {p['borrower']}" if p.get("borrower") else "") + ". Every figure comes from the books "
             "and links back to its screen.", "", f"**Proposed structure: {p['title']}**"]
    lines += [f"{i}. **{s['title']}**: {s['covers']}" for i, s in enumerate(p["sections"], 1)]
    lines += ["", "Change anything (\"add a section on concentrations\", \"drop the scenarios\", \"make it retail\"), "
                  "ask about the data, or say **create it** and I will create the report and draft every section."]
    return "\n".join(lines)


def _facts(p: dict[str, Any]) -> str:
    try:
        if p["book"] == "retail":
            rt = content.retail_totals()
            return (f"Where the book stands: retail ECL is {content.mn_words(rt['ecl'])} at {content.RETAIL_PERIOD} on "
                    f"{content.mn_words(rt['ead'])} of EAD, with Stage 2 at {rt['stage2_share'] * 100:.1f}% of EAD.")
        now, before = content.corp_totals(content.CORP_PERIOD, p.get("sector")), content.corp_totals(
            content.CORP_PRIOR, p.get("sector"))
        scope = p.get("sector") or "Corporate"
        return (f"Where the book stands: {scope} ECL is {content.mn_words(now['ecl'])} at {content.CORP_PERIOD} "
                f"({content.mn_words(now['ecl'] - before['ecl'])} on the quarter), coverage "
                f"{now['coverage'] * 100:.2f}%, Stage 2 {now['stage2_share'] * 100:.1f}% of EAD.")
    except Exception:  # noqa: BLE001 - the structure stands without the headline
        return ""


def _discussion(text: str, p: dict[str, Any]) -> str:
    """With a model: the forked agent discusses scope and structure from the books (validated figures). Without
    one, the composed headline stands in."""
    if not agent.model_available():
        return ""
    plan = "\n".join(f"{i}. {s['title']}: {s['covers']}" for i, s in enumerate(p["sections"], 1))
    scope = agent.Scope(
        domains=[p["book"], "ews", "whatif"], name="Playbook: planning a report", focus={"book": p["book"]},
        context=f"The user asked: {text}\nThe structure proposed below this message:\n{plan}",
        charter=("You help a credit-risk professional scope a report in CreditProbe's Playbook. In three to five "
                 "sentences: say what this report should establish for its audience, the two or three facts from the "
                 "books that will shape it (query them), and ask one question about scope (period, segment or "
                 "audience). Do not repeat the section list; it is shown under your message."))
    try:
        got = agent.converse(f"Scope this report with me: {text}", scope, [], purpose="playbook-scope")
    except Exception:  # noqa: BLE001 - the composed lead stands in
        return ""
    return got["text"] if got.get("source") == "model" and not got.get("refused") else ""


def _restructure_tool(prop: dict[str, Any]) -> Tool:
    """The model's way to change the planned report's sections (no report is created or changed)."""
    def run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        titles = [str(t).strip()[:120] for t in args.get("sections") or [] if str(t).strip()][:20]
        if not titles:
            raise ValueError("Name the sections, in order.")
        fake = {"template": prop["template"], "title": prop["title"], "book": prop["book"]}
        secs = []
        for t in titles:
            kind = section_kind(fake, {"title": t})
            secs.append({"title": t, "kind": kind, "covers": covers(t, kind)})
        new = {**{k: v for k, v in prop.items() if k != "kind"}, "sections": secs,
               **({"title": str(args["title"])[:200]} if args.get("title") else {})}
        return ToolResult(summary="The planned report now has: " + "; ".join(titles) + ".",
                          data={"sections": titles}, blocks=[{"type": "proposal_update", "proposal": new}])
    return Tool("restructure_report", "Change the planned report's sections (and optionally its title) before it is "
                "created. Give the complete new list of section titles in order.",
                {"type": "object", "required": ["sections"], "properties": {
                    "sections": {"type": "array", "items": {"type": "string"}}, "title": {"type": "string"}}},
                run, message="Restructuring the report")


def _last_proposal(msgs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for m in reversed(msgs):
        for a in m.get("actions") or []:
            if a.get("kind") == "proposal":
                return a
            if a.get("kind") == "created":
                return None
    return None


def _create_from(con: sqlite3.Connection, me: str, p: dict[str, Any]) -> dict[str, Any]:
    secs = [store.make_section(s["title"], [], me, status="empty") for s in p["sections"]]
    rep = store.create_report(con, me, p["title"], p["template"], p["book"], p["period"], origin="template",
                              sections=secs)
    rid = rep["id"]
    order = sorted(rep["sections"], key=lambda s: 1 if "summary" in s["title"].lower() else 0)
    drafted = []
    for sec in order:
        cur = store.report(con, rid, me)
        blocks = assistant.draft_blocks(cur, sec["title"])
        if blocks and not blocks[0].get("text", "").endswith("to be completed."):
            store.update_section(con, me, rid, sec["id"], blocks=blocks, action="draft",
                                 summary=f"Drafted “{sec['title']}”", status="drafted")
            drafted.append({"kind": "section_drafted", "section_id": sec["id"], "label": sec["title"]})
    return {"report": store.report(con, rid, me), "drafted": drafted}


def start_conversation(con: sqlite3.Connection, me: str, text: str, thread_id: str | None,
                       cookie: str | None) -> dict[str, Any] | None:
    """The top chat as a conversation. Returns None when the message is a direct command the existing start path
    serves ("Draft a credit memo for CB01143" creates it straight away)."""
    text = store.clean_text(text, "Message", 4000)
    if not text:
        raise store.Invalid("Write a message.")
    prior = store.thread(con, thread_id) if thread_id else []
    prop = _last_proposal(prior)
    if not prior:
        direct = re.match(r"^\s*(please\s+)?(draft|start|create|write|prepare|build|make)\b", text, re.I)
        if direct and not _INTENT.search(text) and not _ecl_report(text):
            return None
    tid = thread_id if prior else store.new_id("th")
    user_msg = store.add_message(con, tid, None, "user", me, text)
    actions: list[dict[str, Any]] = []
    sugg: list[str] = []
    report = None
    if prop and _CONFIRM.search(text):
        made = _create_from(con, me, prop)
        report = made["report"]
        tid_r = f"th_{report['id']}"
        reply = (f"Created “{report['title']}” with {len(report['sections'])} sections and drafted "
                 f"{len(made['drafted'])} of them from the books. Every section has its own assistant below its text "
                 "for brainstorming, questions and redrafting.")
        actions = [{"kind": "created", "label": report["title"], "report_id": report["id"]}, *made["drafted"]]
        store.add_message(con, tid_r, report["id"], "user", me, text)
        store.add_message(con, tid_r, report["id"], "assistant", None, reply, actions, assistant.SUGGEST[:4])
        sugg = []
    elif prop and (_ADD.search(text) or _DROP.search(text) or re.search(r"\b(make it|switch to|for the) (retail|corporate)\b",
                                                                        text, re.I)):
        p = dict(prop)
        p["sections"] = list(p["sections"])
        changed = []
        m = re.search(r"\b(retail|corporate)\b", text, re.I)
        if re.search(r"\b(make it|switch to|for the) (retail|corporate)\b", text, re.I) and m:
            p["book"] = m.group(1).lower()
            p["period"] = content.RETAIL_PERIOD if p["book"] == "retail" else content.CORP_PERIOD
            p["title"] = re.sub(r"\b(Corporate|Retail)\b", p["book"].capitalize(), p["title"])
            p["title"] = re.sub(r"20\d\d(Q[1-4]|-\d\d)", p["period"], p["title"])
            changed.append(f"switched to the {p['book']} book at {p['period']}")
        a = _ADD.search(text)
        if a and not m:
            name = re.sub(r"[.!?]+$", "", a.group(2)).strip()
            name = name[:1].upper() + name[1:]
            fake = {"template": p["template"], "title": p["title"], "book": p["book"]}
            kind = section_kind(fake, {"title": name})
            pos = next((i for i, s in enumerate(p["sections"]) if re.search(r"recommend|action|conclusion", s["title"], re.I)),
                       len(p["sections"]))
            p["sections"].insert(pos, {"title": name, "kind": kind, "covers": covers(name, kind)})
            changed.append(f"added “{name}”")
        d = _DROP.search(text)
        if d:
            want = d.group(2).lower()
            keep = [s for s in p["sections"] if not any(w in s["title"].lower() for w in re.findall(r"[a-z]{4,}", want))]
            gone = [s["title"] for s in p["sections"] if s not in keep]
            if gone:
                p["sections"] = keep
                changed.append("dropped " + ", ".join(f"“{g}”" for g in gone))
        reply = _proposal_text(p, ("Done: " + "; ".join(changed) + ".") if changed else "Here is the structure.")
        actions = [{"kind": "proposal", **{k: v for k, v in p.items() if k != "kind"}}]
        sugg = ["Create it", "Add a section on concentrations", "What should the executive summary say?"]
    else:
        p = None if prop or agent.HELP.search(text) else proposal_for(text)
        if p:
            label = p["label"] if p["label"].startswith("IFRS") else p["label"].lower()
            article = "An" if label[:1].lower() in "aeio" or label.startswith("IFRS") else "A"
            lead = _discussion(text, p) or (f"{article} {label} for the {p['book']} book. " + _facts(p)).strip()
            reply = _proposal_text(p, lead)
            actions = [{"kind": "proposal", **p}]
            sugg = ["Create it", "Add a section on concentrations", "Drop the scenarios", "What should it conclude?"]
        else:
            ctx = ""
            if prop:
                ctx = "The report being planned: " + prop["title"] + ". Sections: " + ", ".join(
                    s["title"] for s in prop["sections"]) + "."
            scope = agent.Scope(domains=["corporate", "retail", "ews", "whatif", "scorecard", "b360", "product"],
                                name="Playbook: planning a report", context=ctx,
                                extra_tools=[_restructure_tool(prop)] if prop else [],
                                charter=("You help a credit-risk professional plan a report in CreditProbe's Playbook: "
                                         "what it should cover, how to structure it and what the data says. Quote "
                                         "figures only from the tools of this turn. When the user wants the planned "
                                         "report's sections changed, call restructure_report with the full new list."))
            got = agent.converse(text, scope, [{"role": m["role"], "text": m["text"]} for m in prior[-8:]],
                                 purpose="playbook-start")
            reply = got["text"]
            actions = [_material(got)]
            new_prop = next((b["proposal"] for b in got.get("module_blocks") or [] if b.get("type") == "proposal_update"),
                            None)
            if new_prop or prop:
                actions.append({"kind": "proposal", **{k: v for k, v in (new_prop or prop).items() if k != "kind"}})
                sugg = ["Create it", *(got.get("suggestions") or [])[:2]]
            else:
                sugg = ["I want to draft a corporate ECL report", "Draft a credit memo for CB01312",
                        "Prepare the Q3 credit committee pack"]
    bot = store.add_message(con, tid, report["id"] if report else None, "assistant", None, reply, actions, sugg[:4])
    return {"thread_id": tid, "report": report, "messages": [user_msg, bot]}
