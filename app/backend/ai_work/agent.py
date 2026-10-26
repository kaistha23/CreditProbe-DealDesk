"""One scoped conversational turn on the shared layer `backend/convo` (docs/v5/CONVO_API.md).

Playbook (report, section and start threads), Project threads and Cockpit help each describe a scope -- which data
domains, documents, instructions and context a conversation may use -- and `converse` runs one turn of the
forked Cockpit loop (understand, plan, query, answer, validate, publish) on a convo `Domain` built for that scope:

  relations   the scope's tables only (DuckDB, locked, SELECT only): the Cockpit books, the Early Warning
              release, the What-If library, the borrower table, project documents
  tools       backend/ai_work/tools.py (the module engines): book figures, Early Warning lists and bands, What-If
              scenario runs with their waterfall, scorecard verdicts and findings, Borrower 360 profiles
  planner     the deterministic plan used with no model key (`understand` + `plan` below)

A question that needs a domain outside the scope is refused before the loop runs, naming the scope. The callers
keep their own threads, so the agent runs inline with a collecting emitter (the stages are kept in the reply).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.ai_work import tools
from backend.ai_work.tools import BOOKS, DOMAINS, Result
from backend.convo import provider as prov
from backend.convo.agent import Agent
from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult


@dataclass
class Scope:
    """What a conversation may read. `domains` are keys of tools.DOMAINS; `focus` is {book, period, segment}."""
    domains: list[str]
    name: str = "CreditProbe"
    instructions: str = ""
    documents: list[dict[str, Any]] = field(default_factory=list)
    focus: dict[str, Any] = field(default_factory=dict)
    context: str = ""
    charter: str = ""
    knowledge: dict[str, str] = field(default_factory=dict)
    extra_tools: list[Tool] = field(default_factory=list)
    #: (question, intent) -> extra PlanSteps for the deterministic planner (a caller's own tools)
    plan_hook: Any = None
    #: (question, intent) -> True when the caller's plan_hook replaces the data plan
    plan_only_hook: Any = None
    #: what the refusal calls this conversation ("This project only uses ...")
    noun: str = "conversation"


@dataclass
class Intent:
    kind: str
    book: str | None = None
    period: str | None = None
    segment: str | None = None
    stage: int | None = None
    bands: list[str] | None = None
    n: int | None = None
    borrower: str | None = None
    scenario: str | None = None
    by: str | None = None
    outside: list[str] = field(default_factory=list)
    book_named: bool = False
    measures: list[str] | None = None
    question: str = ""
    why: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "", False) and k != "question"}


# --------------------------------------------------------------- understand

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "retail": (r"\bretail\b", r"\bmortgages?\b", r"\bcredit cards?\b", r"\bpersonal finance\b", r"\bauto finance\b",
               r"\bconsumer\b"),
    "corporate": (r"\bcorporate\b", r"\bsectors?\b", r"\bsub-?sectors?\b", r"\bborrowers?\b", r"\bfacilit(y|ies)\b"),
    "ews": (r"\bearly warning\b", r"\bews\b", r"\bwatch-?list\b", r"\bwarnings?\b", r"\balerts?\b", r"\bhigh-alert\b"),
    "whatif": (r"\bwhat-?if\b", r"\bscenarios?\b", r"\bstress\b", r"\bshocks?\b", r"\boil\b", r"\brecession\b",
               r"\brates? up\b", r"\bunemployment\b", r"\bhouse prices?\b"),
    "bureau": (r"\bbureau\b", r"\bsimah\b", r"\benquir(y|ies)\b"),
    "open_banking": (r"\bopen banking\b", r"\binflows?\b", r"\bsalary\b"),
    "scorecard": (r"\bscorecards?\b", r"\bgini\b", r"\bpsi\b", r"\bauc\b"),
}
_WORDS_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "twenty": 20, "fifteen": 15, "dozen": 12}
HELP = re.compile(r"\bhow (does|do|do i|can i|should i|to)\b|\bwalk me through\b|\bwhat is (the )?(what-if|playbook|"
                  r"cockpit|early warning|borrower 360|projects?|deal desk|data builder|scorecard|policy docs|mail)\b|"
                  r"\bwhat can i do\b|\bhow it works\b|\bshow me how\b", re.I)


DOC_WORDS = re.compile(r"\b(documents?|memo|terms of reference|according to|says?|said|mentions?|policy|report|"
                       r"minutes|notes?|file|upload(ed)?)\b", re.I)


def _names_module(question: str) -> bool:
    from backend.ai_work import knowledge
    return knowledge.find(question) is not None or bool(re.search(r"\bcreditprobe\b", question, re.I))


def mentioned(question: str) -> list[str]:
    q = question.lower()
    try:
        for s in tools.segments("corporate"):
            q = q.replace(s.lower(), " corporate ")
        for s in tools.segments("retail"):
            q = q.replace(s.lower(), " retail ")
    except Exception:  # noqa: BLE001 - the books are optional for keyword routing
        pass
    out = [d for d, pats in _KEYWORDS.items() if any(re.search(p, q) for p in pats)]
    # R10 C4: "borrowers" / "facilities" alone do not name the corporate book when another domain is named
    if "corporate" in out and len(out) > 1 and not re.search(r"\b(corporate|sub-?sectors?|sectors?)\b", q):
        out.remove("corporate")
    return out


def _segment(book: str, q: str) -> str | None:
    try:
        named = [s for s in tools.segments(book) if s.lower() in q]
    except Exception:  # noqa: BLE001
        return None
    return max(named, key=len) if named else None


def understand(message: str, scope: Scope, history: list[dict[str, Any]] | None = None) -> Intent:
    q = message.lower()
    asked = mentioned(message)
    books_in_scope = [b for b in BOOKS if b in scope.domains]
    book = next((b for b in BOOKS if b in asked), None)
    book_named = book is not None
    if book is None:
        prev = next((h.get("understood", {}).get("book") for h in reversed(history or [])
                     if isinstance(h.get("understood"), dict) and h["understood"].get("book")), None)
        book = scope.focus.get("book") or prev or (books_in_scope[0] if books_in_scope else "corporate")
    period = None
    try:
        from backend.workspace_v5 import compute
        period = compute.period_in(book, message)
    except Exception:  # noqa: BLE001
        pass
    seg = _segment(book, q) or (scope.focus.get("segment") if scope.focus.get("book") in (None, book) else None)
    stage = None
    m = re.search(r"\bstage\s*([123])\b", q)
    if m:
        stage = int(m.group(1))
    bands = None
    if re.search(r"\bcritical\b", q) and not re.search(r"\bhigh\b", q):
        bands = ["critical"]
    elif re.search(r"\b(high[- ]alert|high|severe|red)\b", q):
        bands = ["high", "critical"]
    n = None
    names = r"\b(clients?|borrowers?|customers?|names?|obligors?|accounts?)\b"
    m = re.search(r"\b(\d{1,2})\b(?!\s*(?:%|bps|days|q\d))", re.sub(r"stage\s*[123]", "", q))
    if m and re.search(names, q):
        n = int(m.group(1))
    else:
        m = re.search(r"\b(" + "|".join(_WORDS_N) + r")\b", q)
        if m and re.search(names, q):
            n = _WORDS_N[m.group(1)]
    m = re.search(r"\b(CB\d{5})\b", message.upper())
    borrower = m.group(1) if m else None
    by = None
    m = re.search(r"\bby (sector|sub-?sector|product|stage|region|score band)", q) or \
        re.search(r"\b(?:which|what|top|largest|biggest) (sector|sub-?sector|product|region)s?\b", q)
    if m:
        by = {"sub-sector": "sub_sector", "subsector": "sub_sector", "score band": "score_band",
              "product": "product_type" if book == "corporate" else "product"}.get(m.group(1), m.group(1))
    scenario = tools.scenario_key(book, q) if "whatif" in asked else None
    lists_names = re.search(r"\b(list|which|who|names?|top|give me|show me)\b", q) and re.search(names, q)
    if HELP.search(message) and "product" in scope.domains and _names_module(message):
        kind = "help"
    elif borrower:
        kind = "borrower"
    elif lists_names and ("ews" in asked or bands or ("ews" in scope.domains and stage is not None)):
        kind = "ews_clients"
        asked = list(dict.fromkeys([*asked, "ews"]))
    elif "whatif" in asked:
        kind = "whatif"
    elif "scorecard" in asked:
        kind = "scorecard"
    elif "ews" in asked:
        kind = "ews"
    else:
        kind = "book"
    outside: list[str] = []
    if kind != "help":
        outside = [d for d in asked if d not in scope.domains
                   and not (d == "corporate" and kind == "borrower" and "b360" in scope.domains)]
        if kind in ("ews_clients", "ews") and "ews" not in scope.domains:
            outside = list(dict.fromkeys([*outside, "ews"]))
    measures = None
    if kind == "book":
        from backend.workspace_v5.responder import _measures_asked
        measures = _measures_asked(q)
    why = kind == "book" and bool(re.search(r"\b(why|drove|drives|driver|drivers|explain|rise|rose|increase|"
                                            r"increased|fell|fall|moved?|movement|contribut)", q))
    return Intent(kind, book, period, seg, stage, bands, n, borrower, scenario, by, outside, book_named, measures,
                  message if kind == "help" else "", why)


def question_of(intent: Intent) -> str:
    return intent.question


# --------------------------------------------------------------------- plan


def plan(intent: Intent, scope: Scope) -> list[tuple[str, dict[str, Any]]]:
    b = intent.book or "corporate"
    if intent.kind == "ews_clients":
        books = [b] if intent.book_named or scope.focus.get("book") else \
            [x for x in BOOKS if x in scope.domains] or [b]
        return [("ews_clients", {"book": x, "bands": intent.bands or ["high", "critical"], "stage": intent.stage,
                                 "segment": intent.segment if x == b else None, "n": intent.n or 10,
                                 "period": intent.period if x == b else None}) for x in books]
    if intent.kind == "ews":
        return [("ews_headline", {"book": b, "period": intent.period, "segment": intent.segment})]
    if intent.kind == "borrower":
        return [("borrower_profile", {"borrower_id": intent.borrower})]
    if intent.kind == "whatif":
        if intent.scenario:
            return [("whatif_scenario", {"book": b, "key": intent.scenario})]
        return [("whatif_library", {"book": b})]
    if intent.kind == "scorecard":
        return [("scorecard_overview", {})]
    if intent.kind == "help":
        return [("product_walkthrough", {"question": question_of(intent)})]
    calls: list[tuple[str, dict[str, Any]]] = []
    if any(x in scope.domains for x in BOOKS):
        bk = b if b in scope.domains else next(x for x in BOOKS if x in scope.domains)
        calls.append(("book_figures", {"book": bk, "period": intent.period, "segment": intent.segment, "by": intent.by,
                                       "measures": intent.measures}))
        if intent.why:
            calls.append(("ecl_movement", {"book": bk, "period": intent.period, "segment": intent.segment,
                                           "by": None}))
        if "ews" in scope.domains and not intent.by and not intent.why:
            calls.append(("ews_headline", {"book": bk, "period": None, "segment": intent.segment}))
    return calls


# --------------------------------------------------------------- the domain

def _relations(scope: Scope):
    doms = set(scope.domains)

    def build(_s: dict[str, Any]) -> list[Relation]:
        from backend.workspace_v5 import compute
        out: list[Relation] = []
        if "corporate" in doms:
            f = compute.frame("corporate")
            keep = [c for c in ["facility_id", "borrower_id", "reporting_quarter", "sector", "sub_sector", "region",
                                "product_type", "stage", "ead_sar_mn", "ecl_sar_mn", "limit_sar_mn", "dpd_days"]
                    if c in f.columns]
            out.append(Relation("corporate_facilities", "The Cockpit corporate book: one row per facility and quarter",
                                lambda _s, f=f, keep=keep: f[keep], "facility x reporting_quarter",
                                {"ead_sar_mn": "EAD, SAR million", "ecl_sar_mn": "ECL, SAR million",
                                 "stage": "IFRS 9 stage 1-3"}))
        if "retail" in doms:
            f = compute.frame("retail")
            keep = [c for c in ["account_id", "customer_id", "reporting_month", "product", "sub_product", "region",
                                "stage", "ead_sar_mn", "ecl_sar_mn", "dpd_days", "score_band", "employment_type"]
                    if c in f.columns]
            out.append(Relation("retail_accounts", "The Cockpit retail book: one row per account and month",
                                lambda _s, f=f, keep=keep: f[keep], "account x reporting_month",
                                {"ead_sar_mn": "EAD, SAR million", "ecl_sar_mn": "ECL, SAR million"}))
        if "ews" in doms:
            for book in BOOKS:
                if book in doms or not (doms & set(BOOKS)):
                    d = tools._ews(book)
                    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
                    last = sorted(d[pcol].unique())[-4:]
                    out.append(Relation(f"ews_{book}", f"Early Warning on the {book} book, last four periods: score, "
                                        "band and reasons per facility/account",
                                        lambda _s, d=d, pcol=pcol, last=last: d[d[pcol].isin(last)],
                                        "facility (account) x period", {"ews_reasons": "'; '-separated reasons"}))
        if "whatif" in doms:
            from backend.whatif_v5.chat import library
            rows = [{"book": b, "key": e["key"], "name": e["name"], "description": e["description"]}
                    for b in BOOKS for e in library.STANDARD[b]]
            out.append(Relation("whatif_library", "The What-If standard scenarios",
                                lambda _s, rows=rows: pd.DataFrame(rows), "scenario"))
        if "b360" in doms or "corporate" in doms:
            from backend.playbook_v5 import content
            b = content.borrowers()
            cols = [c for c in ["borrower_id", "borrower_name", "reporting_quarter", "sector", "region",
                                "rating_current", "outlook"] if c in b.columns]
            out.append(Relation("corporate_borrowers", "Corporate borrowers by quarter: name, sector, region, rating",
                                lambda _s, b=b, cols=cols: b[cols], "borrower x reporting_quarter"))
        if scope.documents:
            rows = [{"document": d.get("name", ""), "paragraph": i, "text": p.strip()[:2000]}
                    for d in scope.documents for i, p in enumerate(re.split(r"\n\s*\n", d.get("text") or ""))
                    if len(p.strip()) > 40]
            out.append(Relation("documents", "The project's documents, one row per paragraph",
                                lambda _s, rows=rows: pd.DataFrame(rows or [{"document": "", "paragraph": 0, "text": ""}]),
                                "document x paragraph"))
        if not out:
            out.append(Relation("scope", "This conversation's scope", lambda _s: pd.DataFrame([{"scope": scope.name}])))
        return out
    return build


def to_tool_result(r: Result) -> ToolResult:
    return ToolResult(summary=r.text, data={"figures": r.figures[:12], **{k: v for k, v in r.extra.items()
                                                                          if k != "passages"}},
                      rows=(r.table or {}).get("rows") or None,
                      blocks=[{"type": "work_result", "tool": r.tool, "domain": r.domain, "text": r.text,
                               "figures": r.figures, "table": r.table, "citations": r.citations,
                               "blocks": r.blocks, "args": r.args}])


def _wrap(name: str) -> Tool:
    _fn, _need, desc, schema = tools.REGISTRY[name]

    def run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        r = tools.call(name, {k: v for k, v in args.items() if v is not None}, ctx.scope.get("domains") or [])
        return to_tool_result(r)
    return Tool(name, desc, schema, run, message={"ews_clients": "Listing Early Warning clients",
                                                  "whatif_scenario": "Running the scenario",
                                                  "book_figures": "Reading the books"}.get(name, ""))


def document_tool(scope: Scope) -> Tool:
    def run(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        return to_tool_result(tools.document_passages(str(args.get("question") or ctx.question), scope.documents,
                                                      str(scope.focus.get("segment") or "")))
    return Tool("search_documents", "The paragraphs of the project's documents that best match a question.",
                {"type": "object", "properties": {"question": {"type": "string"}}}, run, message="Reading the documents")


def domain_for(scope: Scope, key: str = "work") -> Domain:
    dom_names = ", ".join(DOMAINS.get(d, d) for d in scope.domains if d != "product") or "its documents"
    charter = (scope.charter or "You are CreditProbe's assistant for a Saudi bank's credit-risk team.") + (
        f" You may use only these data domains: {dom_names}. If a question needs anything else, say it is outside "
        "this conversation's scope." + (f"\n\nInstructions:\n{scope.instructions[:3000]}" if scope.instructions else "")
        + (f"\n\nContext:\n{scope.context[:6000]}" if scope.context else ""))
    toolset = [_wrap(n) for n in tools.REGISTRY if tools.allowed(n, scope.domains)] + list(scope.extra_tools)
    if scope.documents:
        toolset.append(document_tool(scope))

    def planner(question: str, ctx: ToolContext) -> Plan:
        intent = understand(question, scope, ctx.state.get("history") or [])
        only = bool(scope.plan_only_hook and scope.plan_only_hook(question, intent))
        steps = [] if only else [PlanStep(n, {k: v for k, v in a.items() if v is not None})
                                 for n, a in plan(intent, scope)]
        if scope.documents and not only and (intent.kind == "book" or DOC_WORDS.search(question)):
            steps.append(PlanStep("search_documents", {"question": question}))
        if scope.plan_hook:
            steps += scope.plan_hook(question, intent) or []

        def write(results: list[dict[str, Any]]) -> dict[str, Any]:
            parts = []
            for r in results:
                if r["error"]:
                    continue
                s = r["out"].get("summary") or ""
                if r["tool"] == "search_documents" and s:
                    s = "From the project documents: " + s
                parts.append(s)
            errs = [r["out"].get("error") for r in results if r["error"]]
            md = "\n\n".join(p for p in parts if p)
            if not md:
                md = ("; ".join(e for e in errs if e) + "." if errs else
                      f"I answer from {dom_names}. Ask about EAD, ECL, Stage 2 or coverage, the Early Warning bands or "
                      "named clients, a What-If scenario, a borrower (for example CB01312) or the scorecards.")
            return {"markdown": md}
        return Plan(steps, write)

    return Domain(key=key, title=scope.name, charter=charter, relations=_relations(scope), tools=toolset,
                  knowledge=dict(scope.knowledge), planner=planner,
                  scope_label=lambda s: scope.name,
                  scope_key=lambda s: f"{key}|{','.join(sorted(scope.domains))}|"
                                      f"{'/'.join(str(d.get('id', d.get('name', ''))) for d in scope.documents)}")


class _Collect:
    """An emitter that keeps the stages (the callers store their own threads)."""

    def __init__(self):
        self.open_stage = ""
        self.stages: list[str] = []
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, stage: str = "", status: str = "", message: str = "", detail=None):
        self.events.append({"event": event_type, "stage": stage, "status": status, "message": message})

    def stage(self, name: str, message: str = "") -> None:
        if self.open_stage != name:
            self.open_stage = name
            self.stages.append(name)

    def close(self) -> None:
        self.open_stage = ""


# ------------------------------------------------------------------ publish


def refusal(scope: Scope, outside: list[str]) -> dict[str, Any]:
    allowed = [DOMAINS[d] for d in scope.domains if d in DOMAINS and d != "product"]
    names = [DOMAINS.get(d, d) for d in outside]
    text = (f"This {scope.noun} only uses {', '.join(allowed) or 'its documents'}. {' and '.join(names)} "
            f"{'is' if len(names) == 1 else 'are'} outside its scope, so I will not answer from "
            f"{'it' if len(names) == 1 else 'them'} here.")
    return {"text": text, "refused": True, "outside": outside, "domains_used": [], "citations": [], "figures": [],
            "table": None, "tables": [], "blocks": [], "module_blocks": [], "understood": {},
            "stages": ["understanding", "publishing"], "validation": {"removed": []}, "source": "refusal",
            "suggestions": []}


def _unit(col: str, v: Any) -> str:
    if isinstance(v, str):
        return "text"
    if col.endswith("_sar_mn") or col in ("ead", "ecl"):
        return "sar_mn"
    if col.endswith("pct"):
        return "pct"
    return "num"


def publish(out, intent: Intent | None, em: _Collect, scope: Scope) -> dict[str, Any]:
    text = ""
    tables: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    cites: list[dict[str, Any]] = []
    used: list[str] = []
    module_blocks: list[dict[str, Any]] = []
    for b in out.blocks:
        t = b.get("type")
        if t == "answer":
            text = b.get("markdown", "")
        elif t == "work_result":
            if b.get("table") and b["table"].get("rows"):
                tables.append(dict(b["table"], tool=b["tool"]))
            blocks += b.get("blocks") or []
            figures += b.get("figures") or []
            cites += b.get("citations") or []
            used.append(b.get("domain"))
        elif t == "table" and str(b.get("artifact_id", "")).startswith("q"):
            rows = b.get("rows") or []
            tables.append({"title": b.get("title") or "Query result", "key": None, "tool": "run_query",
                           "columns": [{"key": c["key"], "label": c["label"],
                                        "unit": _unit(c["key"], rows[0].get(c["key"]) if rows else None)}
                                       for c in b.get("columns") or []], "rows": rows})
        elif t == "chart":
            rows = b.get("rows") or []
            kind = b.get("kind") or "bar"
            xs = [r.get(b["x"]) for r in rows]
            data = []
            for y in b.get("y") or []:
                ys = [r.get(y) for r in rows]
                tr = {"type": "scatter" if kind == "line" else "bar", "name": (b.get("labels") or {}).get(y, y)}
                tr.update({"x": ys, "y": xs, "orientation": "h"} if kind == "hbar" else {"x": xs, "y": ys})
                data.append(tr)
            blocks.append({"kind": "chart", "title": b.get("title") or "", "figure": {
                "data": data, "layout": {"barmode": "stack" if kind == "stacked" else "group"}}})
        else:
            module_blocks.append(b)
    seen, uniq = set(), []
    for c in cites + ([{"kind": "instructions", "label": "Project instructions"}] if scope.instructions else []):
        k = (c.get("label"), c.get("href"), c.get("doc_id"))
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return {"text": text, "refused": False, "outside": [], "domains_used": list(dict.fromkeys(u for u in used if u)),
            "citations": uniq, "figures": figures[:12], "table": tables[0] if tables else None, "tables": tables,
            "blocks": blocks, "module_blocks": module_blocks, "understood": intent.as_dict() if intent else {},
            "stages": em.stages, "validation": out.validation, "source": out.source,
            "suggestions": [s.get("send") or s.get("label") for s in out.suggestions][:4],
            "evidence": out.evidence}


def converse(message: str, scope: Scope, history: list[dict[str, Any]] | None = None,
             purpose: str = "work", lead: str = "", user: dict[str, Any] | None = None) -> dict[str, Any]:
    """One turn. `history` is [{role, text, understood?}] oldest first. Returns the published reply."""
    history = history or []
    intent = understand(message, scope, history)
    if intent.outside:
        return refusal(scope, intent.outside)
    dom = domain_for(scope, purpose)
    turns, q = [], None
    for h in history:
        if h.get("role") == "user":
            q = h.get("text")
        elif q and h.get("text"):
            turns.append({"question": q, "answer": {"blocks": [{"type": "answer", "markdown": h["text"]}]}})
            q = None
    em = _Collect()
    agent = Agent(dom, thread={"thread_id": purpose, "domain": dom.key}, scope={"domains": list(scope.domains)},
                  state={"history": [{"understood": h.get("understood")} for h in history if h.get("understood")]},
                  question=message, emitter=em, history=turns, user=user or {})
    out = agent.run()
    reply = publish(out, intent, em, scope)
    reply["tools"] = agent.trace
    if lead and reply["text"]:
        reply["text"] = lead + "\n\n" + reply["text"]
    return reply


def model_available() -> bool:
    return prov.default() is not None
