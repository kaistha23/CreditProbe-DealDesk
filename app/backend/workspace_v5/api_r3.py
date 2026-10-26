"""S3-2 routes on the Core service: analyses (save, refresh), investigations (import, continue), projects (access
rules, documents, threads) and the Playbook sections. Contract: docs/v5/WORKSPACE_API.md.

  GET  /domains
  POST /analyses                                   save a Cockpit answer or a What-If result
  GET  /analyses/{id}/periods                      what it can be refreshed against
  POST /analyses/{id}/refresh                      {period?} -> before / after / comparison (from the data)
  GET  /analyses/{id}/playbook-section             {source, section: {title, blocks}} (PLAYBOOK_API.md section 8)
  POST /investigations/import                      a whole thread from anywhere (Cockpit, What-If, Early Warning,
                                                   Scorecard): {source, title, turns, notes}
  POST /investigations/{id}/turns                  continue: add turns
  GET  /investigations/{id}/playbook-section
  POST /projects/{id}/settings                     name, description, instructions, domains, members
  POST /projects/{id}/documents                    upload (.docx, .pdf, .txt; text extracted)
  GET  /projects/{id}/documents/{doc}              its text      GET .../file  the file      DELETE ...
  POST /projects/{id}/threads                      {title?, question?}
  GET  /projects/{id}/threads/{thread}             POST .../messages {text}: answered from the project's scope
  GET  /projects/{id}/cockpit-context              the Cockpit request context (ui_filters) for a project thread
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.identity_v5.api import Ctx, require_ctx
from backend.workspace_v5 import answer_first, compute, docs, responder, store

router = APIRouter()


def _api():
    from backend.workspace_v5 import api
    return api


def _owner_or_admin(ctx: Ctx, item: dict[str, Any]) -> None:
    owner = (item.get("owner") or {}).get("id")
    if not (ctx.is_admin and ctx.viewing_as is None) and owner != ctx.username:
        raise HTTPException(403, "Only the owner can change this project's settings.")


# ------------------------------------------------------------------ models


class AnalysisIn(BaseModel):
    title: str = Field(default="", max_length=200)
    question: str = Field(default="", max_length=store.MAX_TEXT)
    origin: str = "cockpit"
    book: str | None = None
    period: str | None = Field(default=None, max_length=20)
    #: The Cockpit's published answer: narrative, tables, charts, numeric claims (stored as data, as published).
    answer: dict[str, Any] = Field(default_factory=dict)
    #: For a What-If result: {scenario, method}. The figures are recomputed here by the What-If engine.
    whatif: dict[str, Any] | None = None
    origin_link: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=store.MAX_TEXT)


class RefreshIn(BaseModel):
    period: str | None = Field(default=None, max_length=20)


class TurnIn(BaseModel):
    role: str = "user"
    text: str = Field(default="", max_length=20000)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    at: str | None = None


class SourceIn(BaseModel):
    type: str
    id: str = ""
    label: str = ""
    href: str = ""


class ImportIn(BaseModel):
    source: SourceIn
    title: str = Field(max_length=200)
    turns: list[TurnIn] = Field(default_factory=list, max_length=400)
    notes: list[str] | str | None = None
    summary: str = Field(default="", max_length=store.MAX_TEXT)
    continue_href: str = Field(default="", max_length=500)
    project_id: str | None = None
    period: str | None = None


class TurnsIn(BaseModel):
    turns: list[TurnIn] = Field(min_length=1, max_length=50)


class SettingsIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=store.MAX_TEXT)
    instructions: str | None = Field(default=None, max_length=store.MAX_TEXT)
    domains: list[str] | None = None
    members: list[str] | None = None


class ThreadIn(BaseModel):
    title: str = Field(default="", max_length=200)
    question: str = Field(default="", max_length=4000)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


# ------------------------------------------------------------------ domains


@router.get("/domains")
def domains() -> dict[str, Any]:
    return {"domains": [{"id": k, "label": v} for k, v in responder.DOMAINS.items()]}


# ----------------------------------------------------------------- analyses


def _cockpit_table(t: dict[str, Any]) -> dict[str, Any]:
    cols = [str(c) for c in t.get("columns") or []]
    units = t.get("column_units") or {}
    rows = [dict(r.get("canonical") or {}) for r in t.get("rows") or [] if isinstance(r, dict)]

    def unit(c: str) -> str:
        u = str(units.get(c) or "")
        if "sar" in u.lower() or c.endswith("_sar_mn"):
            return "sar_mn"
        if "pct" in u.lower() or "%" in u or c.endswith("_pct"):
            return "pct"
        vals = [r.get(c) for r in rows if r.get(c) is not None]
        return "int" if vals and all(isinstance(v, int) for v in vals) else (
            "num" if vals and all(isinstance(v, (int, float)) for v in vals) else "text")
    return {"title": str(t.get("title") or ""), "columns": [{"key": c, "label": c.replace("_", " "), "unit": unit(c)}
                                                            for c in cols],
            "rows": rows[:500], "key": cols[0] if cols else None}


@router.post("/analyses", status_code=201)
def create_analysis(payload: AnalysisIn, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    origin = payload.origin
    if origin == "whatif":
        w = payload.whatif or {}
        if not w.get("scenario"):
            raise HTTPException(400, "A What-If analysis needs the scenario it ran.")
        sc = dict(w["scenario"])
        book = str(sc.get("domain") or payload.book or "")
        spec = {"engine": "whatif", "book": book, "method": str(w.get("method") or "delta"),
                "scenario": {k: v for k, v in sc.items() if k in ("domain", "period", "name", "cohort_id", "steps")}}
        try:
            result = compute.compute(spec, payload.period or sc.get("period"))
        except compute.ComputeError as e:
            raise HTTPException(400, str(e)) from e
        f = {x["key"]: x["value"] for x in result["figures"]}
        narrative = (payload.answer.get("narrative") or
                     f"{sc.get('name') or 'Scenario'} on the {book} book at {result['period']} "
                     f"({result['method_name']}): ECL {f['reported_ecl']:,.1f} → {f['scenario_ecl']:,.1f} SAR m "
                     f"({f['change']:+,.1f}).")
        answer = {"narrative": str(narrative)[:store.MAX_TEXT], "figures": result["figures"], "table": result["table"],
                  "chart": result["chart"], "period": result["period"], "engine": "whatif",
                  "source": result["source"], "steps": result.get("steps", [])}
        return answer_first.view(_api()._run(store.create_analysis, ctx.username, title=payload.title or payload.question,
                           question=payload.question, origin="whatif", book=book, period=result["period"],
                           answer=answer, spec=spec, origin_link=payload.origin_link, notes=payload.notes,
                           source=result["source"]))
    if origin != "cockpit":
        raise HTTPException(400, "origin must be cockpit or whatif.")
    book = payload.book if payload.book in compute.CORP_RETAIL else None
    a = payload.answer
    tables = [_cockpit_table(t) for t in (a.get("tables") or []) if isinstance(t, dict)][:10]
    period = payload.period or (compute.period_in(book, payload.question)
                                or compute.period_in(book, str(a.get("narrative") or "")) if book else None)
    if book and not period:
        period = compute.periods(book)[-1]
    spec = compute.infer_book_spec(book, a.get("tables") or []) if book else None
    baseline = None
    if spec:
        try:
            baseline = compute.compute(spec, period)
        except compute.ComputeError:
            spec = None
    if spec and baseline and not compute.reproduces(spec, (a.get("tables") or [])[spec["cockpit_table"]], baseline):
        spec, baseline = None, None
    answer = {"narrative": str(a.get("narrative") or "")[:store.MAX_TEXT], "tables": tables,
              "table": (baseline or {}).get("table") or (tables[0] if tables else None),
              "charts": [c for c in (a.get("charts") or []) if isinstance(c, dict)][:10],
              "figures": (baseline or {}).get("figures") or [],
              "numeric_claims": [c for c in (a.get("numeric_claims") or []) if isinstance(c, dict)][:60],
              "chart": (baseline or {}).get("chart"), "period": period, "engine": "cockpit",
              "baseline": baseline, "run_id": str(a.get("run_id") or "")[:80],
              "recompute_note": "" if spec else ("This answer is kept as the Cockpit published it. Its figures are not a "
                                                 "plain measure-by-dimension cut of the book that the Workspace can "
                                                 "reproduce, so it is refreshed by asking the Cockpit again, not "
                                                 "here.")}
    return answer_first.view(_api()._run(store.create_analysis, ctx.username, title=payload.title or payload.question,
                       question=payload.question, origin="cockpit", book=book, period=period, answer=answer, spec=spec,
                       origin_link=payload.origin_link, notes=payload.notes,
                       source=(baseline or {}).get("source", "Cockpit answer")))


def _visible_analysis(ctx: Ctx, analysis_id: str) -> dict[str, Any]:
    out = _api()._run(store.analysis, analysis_id)
    _api()._guard(ctx, "analysis", out)
    return out


def _saved_result(a: dict[str, Any]) -> dict[str, Any]:
    ans = a.get("answer") or {}
    if ans.get("baseline"):
        return ans["baseline"]
    return {"period": a.get("period"), "figures": ans.get("figures") or [], "table": ans.get("table"),
            "chart": ans.get("chart"), "engine": ans.get("engine"), "source": a.get("source")}


@router.get("/analyses/{analysis_id}/periods")
def analysis_periods(analysis_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    a = _visible_analysis(ctx, analysis_id)
    ps = compute.available_periods(a.get("spec"))
    return {"analysis_id": analysis_id, "refreshable": bool(a.get("spec")) and bool(ps), "periods": ps,
            "latest": ps[-1] if ps else None, "saved_period": a.get("period"),
            "reason": "" if a.get("spec") else (a.get("answer") or {}).get("recompute_note", ""),
            "datasets": [{"id": a.get("book"), "label": responder.DOMAINS.get(a.get("book") or "", a.get("book"))}]
            if a.get("book") else []}


@router.post("/analyses/{analysis_id}/refresh")
def refresh_analysis(analysis_id: str, payload: RefreshIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    a = _visible_analysis(ctx, analysis_id)
    if not a.get("spec"):
        raise HTTPException(409, (a.get("answer") or {}).get("recompute_note") or
                            "This analysis was saved without a recipe that can be recomputed.")
    try:
        after = compute.compute(a["spec"], payload.period)
    except compute.ComputeError as e:
        raise HTTPException(400, str(e)) from e
    before = _saved_result(a)
    comparison = compute.compare(before, after)
    if ctx.viewing_as is None:
        _api()._run(store.record_refresh, ctx.username, analysis_id,
                    {"period": after["period"], "figures": {f["key"]: f["value"] for f in after["figures"]}})
    return {"analysis_id": analysis_id, "before": before, "after": after, "comparison": comparison}


def _fmt(unit: str) -> str:
    return {"sar_mn": "num", "pct": "num", "int": "int", "num": "num"}.get(unit, "text")


def _blocks_for_table(title: str, t: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not t or not t.get("columns"):
        return []
    cols = [{"key": c["key"], "label": c["label"] + (" (SAR m)" if c["unit"] == "sar_mn" else " (%)" if c["unit"] == "pct"
                                                      else ""), "format": _fmt(c["unit"])} for c in t["columns"]][:30]
    return [{"kind": "table", "title": title, "columns": cols,
             "rows": [{c["key"]: r.get(c["key"]) for c in cols} for r in (t.get("rows") or [])[:500]]}]


def _chart_block(title: str, t: dict[str, Any] | None, chart: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not t or not chart:
        return []
    rows = t.get("rows") or []
    return [{"kind": "chart", "title": chart.get("title") or title,
             "figure": {"data": [{"type": "bar", "x": [str(r.get(chart["x"])) for r in rows],
                                  "y": [r.get(chart["y"]) for r in rows]}],
                        "layout": {"title": {"text": chart.get("title") or title}}}}]


def _kpis(figures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not figures:
        return []
    return [{"kind": "kpis", "items": [{"label": f["label"] + (" (SAR m)" if f["unit"] == "sar_mn" else ""),
                                        "value": f["value"], "format": "int" if f["unit"] == "int" else "num"}
                                       for f in figures[:8]]}]


@router.get("/analyses/{analysis_id}/playbook-section")
def analysis_section(analysis_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    a = _visible_analysis(ctx, analysis_id)
    ans = a.get("answer") or {}
    blocks: list[dict[str, Any]] = []
    if a.get("question"):
        blocks.append({"kind": "paragraph", "text": f"**Question:** {a['question']}"})
    if ans.get("narrative"):
        blocks.append({"kind": "paragraph", "text": ans["narrative"]})
    blocks += _kpis(ans.get("figures") or [])
    blocks += _blocks_for_table(a["title"], ans.get("table"))
    blocks += _chart_block(a["title"], ans.get("table"), ans.get("chart"))
    last = (a.get("refreshes") or [])[-1:]
    if last:
        blocks.append({"kind": "callout", "tone": "info",
                       "text": f"Last refreshed against {last[0]['period']} on {last[0]['at'][:10]}."})
    blocks.append({"kind": "paragraph", "text": f"Source: {a.get('source') or ans.get('source') or 'CreditProbe'}; "
                                                 f"period {a.get('period') or ''}."})
    return {"source": {"type": "analysis", "id": a["id"], "label": f"Analysis: {a['title']}",
                       "href": f"/analyses/{a['id']}", "summary": (ans.get("narrative") or "")[:300],
                       "meta": {"book": a.get("book"), "period": a.get("period"), "origin": a.get("origin")}},
            "section": {"title": a["title"], "blocks": blocks[:60]}}


# ----------------------------------------------------------- investigations


@router.post("/investigations/import", status_code=201)
def import_investigation(payload: ImportIn, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    if payload.project_id:
        _api()._guard(ctx, "project", _api()._run(store.project, payload.project_id))
    return _api()._run(store.import_investigation, ctx.username, source=payload.source.model_dump(),
                       title=payload.title, turns=[t.model_dump() for t in payload.turns], notes=payload.notes,
                       summary=payload.summary, continue_href=payload.continue_href, project_id=payload.project_id,
                       period=payload.period)


@router.post("/investigations/{inv_id}/turns", status_code=201)
def add_turns(inv_id: str, payload: TurnsIn, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    _api()._guard(ctx, "investigation", _api()._run(store.investigation, inv_id))
    return _api()._run(store.add_turns, ctx.username, inv_id, [t.model_dump() for t in payload.turns])


@router.get("/investigations/{inv_id}/playbook-section")
def investigation_section(inv_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    inv = _api()._run(store.investigation, inv_id)
    _api()._guard(ctx, "investigation", inv)
    blocks: list[dict[str, Any]] = [{"kind": "paragraph", "text": inv["summary"]}] if inv["summary"] else []
    for t in inv.get("turns") or []:
        if t["role"] == "user":
            blocks.append({"kind": "heading", "level": 3, "text": t["text"][:200]})
        elif t["text"]:
            blocks.append({"kind": "paragraph", "text": t["text"][:8000]})
        for art in t.get("artifacts") or []:
            if art.get("kind") == "table":
                blocks += _blocks_for_table(art.get("title") or "", art)
            elif art.get("kind") == "figures":
                blocks += _kpis(art.get("figures") or [])
    notes = [n["body"] for n in inv.get("timeline") or [] if n["kind"] == "note"]
    if notes:
        blocks.append({"kind": "heading", "level": 3, "text": "Notes"})
        blocks.append({"kind": "bullets", "items": [n[:500] for n in notes[:40]]})
    return {"source": {"type": "investigation", "id": inv["id"], "label": f"Investigation: {inv['title']}",
                       "href": f"/investigations/{inv['id']}", "summary": inv["summary"][:300],
                       "meta": {"period": inv.get("period"), "source": (inv.get("source") or {}).get("type")}},
            "section": {"title": inv["title"], "blocks": blocks[:60]}}


# ----------------------------------------------------------------- projects


def _visible_project(ctx: Ctx, project_id: str) -> dict[str, Any]:
    p = _api()._run(store.project, project_id)
    _api()._guard(ctx, "project", p)
    return p


@router.post("/projects/{project_id}/settings")
def project_settings(project_id: str, payload: SettingsIn, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    p = _visible_project(ctx, project_id)
    _owner_or_admin(ctx, p)
    return _api()._run(store.update_project, ctx.username, project_id, name=payload.name,
                       description=payload.description, instructions=payload.instructions, domains=payload.domains,
                       members=payload.members)


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(project_id: str, file: UploadFile = File(...),
                          ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    _visible_project(ctx, project_id)
    name = (file.filename or "document").split("/")[-1].split("\\")[-1]
    data = await file.read(docs.MAX_BYTES + 1)
    try:
        ext = docs.kind_of(name)
        text = docs.extract(name, data)
    except docs.DocError as e:
        raise HTTPException(400, str(e)) from e
    out = _api()._run(store.add_project_file, ctx.username, project_id, name, data, text, docs.KINDS[ext])
    out.pop("data", None)
    return out


@router.get("/projects/{project_id}/documents/{file_id}")
def project_document(project_id: str, file_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    _visible_project(ctx, project_id)
    out = _api()._run(store.project_file, project_id, file_id)
    out.pop("data", None)
    return out


_TYPES = {"Word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "PDF": "application/pdf",
          "Text": "text/plain; charset=utf-8"}


@router.get("/projects/{project_id}/documents/{file_id}/file")
def project_document_file(project_id: str, file_id: str, ctx: Ctx = Depends(require_ctx)) -> Response:
    _visible_project(ctx, project_id)
    f = _api()._run(store.project_file, project_id, file_id)
    safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in f["name"])
    return Response(f["data"] or b"", media_type=_TYPES.get(f["kind"], "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@router.delete("/projects/{project_id}/documents/{file_id}")
def delete_document(project_id: str, file_id: str, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    p = _visible_project(ctx, project_id)
    _owner_or_admin(ctx, p)
    _api()._run(store.delete_project_file, project_id, file_id)
    return _api()._run(store.project, project_id)


def _answer(ctx: Ctx, project_id: str, thread_id: str, text: str) -> None:
    with store.db() as con:
        p = store.project(con, project_id)
        files = store.project_file_texts(con, project_id)
        history = [{"role": m["role"], "text": m["text"], **({"understood": m["understood"]} if m.get("understood") else {})}
                   for m in store.project_thread(con, project_id, thread_id)["messages"][-12:]]
        store.add_project_message(con, thread_id, "user", ctx.username, text)
    try:
        reply = responder.respond(p, text, files, history)
    except compute.ComputeError as e:
        reply = {"text": f"I could not compute that: {e}", "refused": False, "citations": []}
    from backend.convo import trace as _trace
    _trace.attach(reply)   # the turn's process trace (PLAN_R5 G4) is stored with the answer
    with store.db() as con:
        store.add_project_message(con, thread_id, "assistant", None, reply.pop("text"), payload=reply)


@router.post("/projects/{project_id}/threads", status_code=201)
def new_thread(project_id: str, payload: ThreadIn, ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    _visible_project(ctx, project_id)
    title = payload.title or payload.question[:120] or "New thread"
    tid = _api()._run(store.create_project_thread, ctx.username, project_id, title)
    if payload.question.strip():
        _answer(ctx, project_id, tid, payload.question.strip())
    return _api()._run(store.project_thread, project_id, tid)


@router.get("/projects/{project_id}/threads/{thread_id}")
def project_thread(project_id: str, thread_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    p = _visible_project(ctx, project_id)
    out = _api()._run(store.project_thread, project_id, thread_id)
    out["project"] = {"id": p["id"], "name": p["name"], "domains": p["domains"], "instructions": p["instructions"],
                      "files": [{"id": f["id"], "name": f["name"]} for f in p["files"]]}
    return out


@router.post("/projects/{project_id}/threads/{thread_id}/messages", status_code=201)
def thread_message(project_id: str, thread_id: str, payload: MessageIn,
                   ctx: Ctx = Depends(_api()._writer)) -> dict[str, Any]:
    _visible_project(ctx, project_id)
    _api()._run(store.project_thread, project_id, thread_id)
    _answer(ctx, project_id, thread_id, payload.text.strip())
    return project_thread(project_id, thread_id, ctx)


@router.get("/projects/{project_id}/cockpit-context")
def cockpit_context(project_id: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """What a project thread sends to the frozen Cockpit: the book (the thread's domain) and the project context and
    domain scope in the existing request field `ui_filters`, which the Cockpit pins into its context packet."""
    p = _visible_project(ctx, project_id)
    books = [d for d in p["domains"] if d in compute.CORP_RETAIL]
    return {"available": bool(books), "domain": books[0] if books else None, "books": books,
            "ui_filters": {"workspace_project": {
                "id": p["id"], "name": p["name"], "instructions": p["instructions"][:2000],
                "allowed_domains": p["domains"],
                "allowed_domain_labels": [responder.DOMAINS[d] for d in p["domains"] if d in responder.DOMAINS],
                "focus": p.get("focus") or {}, "documents": [f["name"] for f in p["files"]]}},
            "reason": "" if books else "This project uses no Cockpit book, so its threads do not go to the Cockpit."}
