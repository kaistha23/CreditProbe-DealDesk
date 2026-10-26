"""The What-If API -- its own app on its own port (8503), prefix /api/v1/whatif.

Conversational What-If (PLAN_R2 item 6): a thread per conversation, a turn per
question, answered by the What-If assistant (backend/whatif_v5/chat, a fork of
the Cockpit's conversational architecture) on the What-If IFRS 9 domain.

    GET  /health
    GET  /meta?domain=                      periods, labels, segments, methods, MEVs, assistant
    GET  /library?domain=                   standard + saved scenarios (the repository)
    POST /threads                           {domain, period?, question?, library_id?, cohort_id?} -> thread (+ first run)
    GET  /threads?domain=                   recent threads visible to the caller
    GET  /threads/{id}                      thread, transcript, active run
    POST /threads/{id}/runs                 {question} -> run (202)
    POST /threads/{id}/title                {title}
    GET  /runs/{id}                         run status (and answer when settled)
    GET  /runs/{id}/events?cursor=          SSE: the run's committed events, then run.settled
    POST /scenarios                         {thread_id, name?, tags?} save the thread's scenario
    GET  /scenarios/{id}
    DELETE /scenarios/{id}
    GET  /threads/{id}/report.docx          5-page Word report of the thread's current scenario
    GET  /scenarios/{id}/report.docx
    GET  /threads/{id}/export.xlsx          the last result's tables
    GET  /models/{book}/{method}            model card (delta | xgboost)
    GET  /reports                           the caller's report pack ("Add to report")
    POST /reports/items                     {thread_id | scenario_id}
    DELETE /reports/items/{id}
    GET  /reports/pack.docx                 the pack as one Word document
    GET  /mev                               the MEV store: series, sources, history, paths
    GET  /cohort/{object_id}                an Early Warning cohort (read-only)
    GET  /cohort/{object_id}/summary        the cohort's dashboard: key figures, mixes, warning bands and
                                            reasons, top 20 owners, reconciliation to Early Warning
    GET  /threads/{id}/summary              the thread header: the same summary for the thread's population
                                            (its cohort, its scenario's scope, or the whole book)

Reads the What-If domain, the books and the Early Warning store read-only.
Writes only its own thread store (var/whatif/whatif_chat.sqlite).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import Response, StreamingResponse

from backend.house_style import user_label
from backend.whatif_v5 import cohorts, paths
from backend.whatif_v5.chat import access, library, orchestrator, provider
from backend.whatif_v5.chat import states as st
from backend.whatif_v5.chat.store import BusyError, Store
from backend.whatif_v5.chat.worker import Worker
from backend.whatif_v5.domain import mev, store as dstore
from backend.whatif_v5.models import cards, runner, xgb
from backend.whatif_v5.models.scenario import Scenario

PREFIX = "/api/v1/whatif"
ENGINE_VERSION = "whatif-v5-2.0.0"

app = FastAPI(title="CreditProbe v5 What-If", version=ENGINE_VERSION)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "what_if", run_paths=r"/whatif/scenarios$")
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

STORE: Store | None = None
WORKER: Worker | None = None


def store() -> Store:
    global STORE, WORKER
    if STORE is None:
        STORE = Store()
        library.seed(STORE)
        WORKER = Worker(STORE)
        WORKER.start()
    return STORE


@app.on_event("startup")
def _startup() -> None:
    store()
    # PLAN_R13 §S: warm the scenario engine (about 10 s, deterministic) so the first calibrated answer is quick.
    import threading

    def _warm() -> None:
        try:
            from backend.scenarios import engine as se
            se.build()
        except Exception:  # noqa: BLE001 - a cold start only makes the first answer slower
            pass
    threading.Thread(target=_warm, name="scenario-engine-warm", daemon=True).start()


def refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


def _domain(domain: str) -> str:
    d = str(domain or "corporate").strip().lower()
    if d not in dstore.BOOKS:
        raise refuse(422, "WHATIF_UNKNOWN_BOOK", f"'{domain}' is not a book. The books are corporate and retail.")
    return d


def _thread(request: Request, thread_id: str, write: bool = False) -> dict:
    t = store().thread(thread_id)
    if t is None:
        raise refuse(404, "WHATIF_THREAD_NOT_FOUND", f"{thread_id} is not a What-If thread.")
    u = access.user(request)
    if not access.can_see(u, t["owner"], t["team"], "whatif-thread", thread_id, request):
        raise refuse(403, "WHATIF_NOT_ALLOWED", "This thread belongs to someone else and was not shared with you.")
    if write and not access.can_write(u, t["owner"]) and not access.can_see(u, t["owner"], t["team"], "whatif-thread", thread_id, request):
        raise refuse(403, "WHATIF_NOT_ALLOWED", "Read only.")
    return t


# ------------------------------------------------------------------ meta

def _convo_describe() -> dict[str, Any]:
    """The forked Cockpit agent's model (backend/convo): the questions in a What-If thread go through it."""
    from backend.convo import provider as convo_provider
    return convo_provider.describe()


@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    out = {"status": "ok", "app": "creditprobe-v5-whatif", "port": paths.API_PORT, "engine": ENGINE_VERSION,
           "domain": {}, "models": xgb.available(), "assistant": provider.describe(),
           "convo": _convo_describe(),
           "reads_books": "read-only", "reads_ews_store": "read-only", "imports_cockpit": False}
    for b in dstore.BOOKS:
        try:
            out["domain"][b] = {"as_of": dstore.as_of(b), "periods": len(dstore.periods(b)),
                                "built": (dstore.files_dir(b) / f"{dstore.as_of(b)}.parquet").exists()}
        except dstore.DomainError as e:
            out["domain"][b] = {"error": str(e)}
    out["as_of"] = {b: v.get("as_of") for b, v in out["domain"].items()}
    return out


@app.get(PREFIX + "/meta")
def meta(domain: str = Query("corporate")) -> dict[str, Any]:
    d = _domain(domain)
    v = orchestrator.vocabulary(d)
    man = dstore.manifest(d)
    return {"domain": d, "as_of": dstore.as_of(d), "periods": dstore.periods(d), "labels": runner.LABELS[d],
            "segments": v["segments"], "subsegments": v["subsegments"],
            "methods": [{"key": "delta", "name": "Delta method"}, {"key": "xgboost", "name": "XGBoost"}],
            "scenario_weights": man["scenario_weights"], "mev": mev.describe(), "assistant": provider.describe(),
            "drivers": ["pd", "lgd", "ccf", "staging", "rating", "sector", "mev"],
            "examples": [c["send"] for c in orchestrator.brainstorm_chips({"domain": d})]}


@app.get(PREFIX + "/mev")
def mev_store() -> dict[str, Any]:
    a = mev.annual()
    hist = {s.key: [{"year": int(y), "value": float(v)} for y, v in a[s.key].dropna().items()] for s in mev.SERIES}
    sy = 2026
    p = mev.paths_from(sy)
    paths_ = {sc: {s.key: [float(x) for x in p[sc][s.key]] for s in mev.SERIES} for sc in mev.SCENARIOS}
    return {"series": mev.describe(), "history": hist, "paths": {"start_year": sy, "years": list(range(sy, sy + 5)),
                                                                   "levels": paths_}, "weights": mev.WEIGHTS,
            "manifest": mev.manifest()}


@app.get(PREFIX + "/scenario-engine")
def scenario_engine(section: str = Query("")) -> dict[str, Any]:
    """PLAN_R13 §S: the calibrated severities, joint scenarios, satellite models and the book translation."""
    from backend.scenarios import chat as scn
    from backend.scenarios import engine as se
    res = se.build()
    if section:
        if section not in res:
            raise refuse(404, "unknown_section", f"'{section}' is not a section of the scenario engine.")
        return {"section": section, "value": res[section]}
    return {"version": res["version"], "window": res["window"], "limits": res["limits"], "headline": scn.headline(res),
            "block": scn.scenario_block(res), "calibration": res["calibration"], "joint": res["joint"]["joint"],
            "analogues": res["joint"]["analogues"], "satellite": res["satellite"], "reproducibility": res["reproducibility"]}


@app.get(PREFIX + "/scenario-engine/regime")
def scenario_regime() -> dict[str, Any]:
    """R14 m (K12): the current-regime block (latest Brent dated, 3/12-month change, 35-year percentile, growth vintages,
    regime label, oil reversal sizes) every scenario answer opens with."""
    from backend.scenarios import regime
    r = regime.current()
    return {"regime": r, "block": regime.block(r), "markdown": regime.markdown(r)}


@app.get(PREFIX + "/scenario-engine/recommend")
def scenario_recommend(book: str = Query("corporate")) -> dict[str, Any]:
    """R14 m (K12): scenarios recommended for the current regime and the revenue channel (deterministic)."""
    from backend.scenarios import recommend
    if book not in ("corporate", "retail"):
        raise refuse(404, "WHATIF_UNKNOWN_BOOK", f"'{book}' is not a book.")
    return recommend.recommend(book)


@app.get(PREFIX + "/scenario-engine/revenue")
def scenario_revenue() -> dict[str, Any]:
    """R14 m (K12 (3)): account turnover and reported revenue by sector, and whether the book's stress comes from revenue."""
    from backend.scenarios import revenue
    r = revenue.by_sector()
    return {**r, "line": revenue.summary_line(r)}


@app.get(PREFIX + "/scenario-engine/conditional")
def scenario_conditional() -> dict[str, Any]:
    """R14 m (K12 (5)): the Brent severity conditional on the starting level, and whether n allows it."""
    from backend.scenarios import conditioned
    return conditioned.conditional_brent()


@app.get(PREFIX + "/scenario-engine/backtest")
def scenario_backtest() -> dict[str, Any]:
    """R14 m (§m (7)): What-If ECL estimate against the full ECL engine, quarter by quarter (relation whatif_backtest)."""
    from backend.whatif_v5 import backtest
    rep = backtest.load()
    if rep is None:
        raise refuse(404, "WHATIF_NO_BACKTEST", "The What-If back-test has not been run yet (python -m backend.whatif_v5.backtest).")
    return rep


@app.get(PREFIX + "/scenario-engine/memo.docx")
def scenario_engine_memo(request: Request) -> Response:
    from backend.house_style import generated_by
    from backend.scenarios import memo
    body = memo.build(generated_by=generated_by(request))
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="CreditProbe_scenario_methodology_memo.docx"'})


@app.get(PREFIX + "/models/{book}/{method}")
def model_card(book: str, method: str) -> dict[str, Any]:
    b = _domain(book)
    if method not in ("delta", "xgboost"):
        raise refuse(404, "WHATIF_UNKNOWN_METHOD", f"'{method}' is not a method.")
    try:
        return cards.card(b, method)
    except xgb.ModelError as e:
        raise refuse(404, "WHATIF_MODEL_NOT_BUILT", str(e)) from e


# ------------------------------------------------------------------ library

def _scenario_row(r: dict) -> dict:
    return {k: r[k] for k in ("scenario_id", "owner", "team", "name", "description", "domain", "period", "method",
                              "ecl_before", "ecl_after", "change", "change_pct", "tags", "created_at", "standard",
                              "thread_id", "cohort_id")} | {"steps": [s.get("restatement") or s.get("instruction")
                                                                     for s in r["scenario"].get("steps", [])]}


@app.get(PREFIX + "/library")
def library_list(request: Request, domain: str = Query("corporate")) -> dict[str, Any]:
    d = _domain(domain)
    u = access.user(request)
    rows = [r for r in store().scenarios() if r["domain"] == d
            and access.can_see(u, r["owner"], r["team"], "whatif-scenario", r["scenario_id"], request)]
    return {"domain": d, "standard": [_scenario_row(r) for r in rows if r["standard"]],
            "saved": [_scenario_row(r) for r in rows if not r["standard"]]}


@app.post(PREFIX + "/scenarios")
def save(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    t = _thread(request, str(body.get("thread_id") or ""), write=True)
    sc = t["state"].get("scenario")
    if not sc:
        raise refuse(422, "WHATIF_NOTHING_TO_SAVE", "This thread has no scenario yet.")
    method = t["state"].get("method") or "delta"
    scenario = Scenario.from_dict(sc)
    try:
        result = runner.run(scenario, method)
    except runner.RunError as e:
        raise refuse(422, "WHATIF_RUN_REFUSED", str(e)) from e
    u = access.user(request)
    thread_for_owner = {**t, "owner": u.get("username") or t["owner"], "team": u.get("team") or t["team"]}
    row = orchestrator.save_scenario(store(), thread_for_owner, scenario, method, result, str(body.get("name") or t["title"]))
    if body.get("tags"):
        row["tags"] = sorted(set(row["tags"]) | {str(x) for x in body["tags"]})
        row = store().save_scenario(row)
    return _scenario_row(row)


@app.get(PREFIX + "/scenarios/{sid}")
def scenario_get(request: Request, sid: str) -> dict[str, Any]:
    r = store().scenario(sid)
    if r is None or not access.can_see(access.user(request), r["owner"], r["team"], "whatif-scenario", sid, request):
        raise refuse(404, "WHATIF_SCENARIO_NOT_FOUND", f"{sid} is not a scenario you can see.")
    return _scenario_row(r) | {"scenario": r["scenario"], "summary": r["summary"]}


@app.delete(PREFIX + "/scenarios/{sid}")
def scenario_delete(request: Request, sid: str) -> dict[str, Any]:
    r = store().scenario(sid)
    if r is None or r["standard"]:
        raise refuse(404, "WHATIF_SCENARIO_NOT_FOUND", f"{sid} is not a saved scenario.")
    if not access.can_write(access.user(request), r["owner"]):
        raise refuse(403, "WHATIF_NOT_ALLOWED", "Only the owner can delete a saved scenario.")
    store().delete_scenario(sid)
    return {"deleted": sid}


# ------------------------------------------------------------------ threads and runs

def _start(thread_id: str, owner: str, question: str, idem: str = "") -> dict:
    try:
        return store().accept_run(thread_id, owner, question, idem)
    except BusyError as e:
        raise refuse(409, "WHATIF_BUSY", f"A turn is still running on this thread ({e.run_id}).") from e


def _run_view(r: dict) -> dict:
    return {"run_id": r["run_id"], "thread_id": r["thread_id"], "state": r["state"], "terminal": r["terminal"],
            "last_event_seq": r["last_event_seq"], "answer": r["answer"] if r["terminal"] else None,
            "error_code": r["error_code"], "events_url": f"{PREFIX}/runs/{r['run_id']}/events"}


@app.post(PREFIX + "/threads", status_code=201)
def thread_create(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    u = access.user(request)
    cohort_id = str(body.get("cohort_id") or "").strip()
    domain = body.get("domain") or "corporate"
    period = str(body.get("period") or "")
    if cohort_id:
        try:
            frozen = cohorts.open_cohort(cohort_id)
        except cohorts.CohortError as e:
            raise refuse(404, "WHATIF_COHORT_NOT_FOUND", str(e)) from e
        domain, period = frozen["domain_id"], frozen["period"]
    d = _domain(domain)
    try:
        period = dstore.resolve_period(d, period)
    except dstore.DomainError as e:
        raise refuse(422, "WHATIF_UNKNOWN_PERIOD", str(e)) from e
    lib = str(body.get("library_id") or "").strip()
    if lib:
        row = store().scenario(lib)
        if row is None or not access.can_see(u, row["owner"], row["team"], "whatif-scenario", lib, request):
            raise refuse(404, "WHATIF_SCENARIO_NOT_FOUND", f"{lib} is not a scenario you can see.")
        if row["domain"] != d:
            raise refuse(422, "WHATIF_RUN_REFUSED", f"{row['name']} is a {row['domain']} scenario.")
    t = store().create_thread(owner=u.get("username", ""), team=u.get("team", ""), domain=d, period=period,
                              cohort_id=cohort_id, origin="ews" if cohort_id else "library" if lib else "chat")
    run = None
    if cohort_id:
        run = _start(t["thread_id"], u.get("username", ""), "::cohort")
        if lib or body.get("question"):
            pass
    elif lib:
        run = _start(t["thread_id"], u.get("username", ""), f"::library {lib}")
    elif body.get("question"):
        run = _start(t["thread_id"], u.get("username", ""), str(body["question"])[:4000],
                     request.headers.get("Idempotency-Key", ""))
    return {"thread_id": t["thread_id"], "domain": d, "period": period, "cohort_id": cohort_id,
            "run": _run_view(run) if run else None}


@app.get(PREFIX + "/threads")
def thread_list(request: Request, domain: str = Query("")) -> dict[str, Any]:
    u = access.user(request)
    rows = [t for t in store().threads(100) if (not domain or t["domain"] == domain)
            and access.can_see(u, t["owner"], t["team"], "whatif-thread", t["thread_id"], request)]
    return {"threads": rows[:30]}


@app.get(PREFIX + "/threads/{thread_id}")
def thread_get(request: Request, thread_id: str) -> dict[str, Any]:
    t = _thread(request, thread_id)
    s = store()
    state = t["state"]
    return {"thread_id": t["thread_id"], "title": t["title"], "domain": t["domain"], "period": t["period"],
            "cohort_id": t["cohort_id"], "origin": t["origin"], "owner": t["owner"], "team": t["team"],
            "created_at": t["created_at"], "updated_at": t["updated_at"],
            "labels": runner.LABELS[t["domain"]], "turns": s.turns(thread_id), "active_run": s.active_run(thread_id),
            "state": {"has_scenario": bool(state.get("scenario")), "method": state.get("method"),
                      "pending": bool(state.get("pending")),
                      "steps": [x.get("restatement") for x in (state.get("scenario") or {}).get("steps", [])],
                      "scenario": state.get("scenario")}}


@app.get(PREFIX + "/threads/{thread_id}/summary")
def thread_summary(request: Request, thread_id: str) -> dict[str, Any]:
    from backend.whatif_v5 import summary
    t = _thread(request, thread_id)
    try:
        return summary.thread(t)
    except cohorts.CohortError as e:
        raise refuse(404, "WHATIF_COHORT_NOT_FOUND", str(e)) from e
    except (summary.SummaryError, dstore.DomainError) as e:
        raise refuse(422, "WHATIF_SUMMARY_REFUSED", str(e)) from e


@app.post(PREFIX + "/threads/{thread_id}/runs", status_code=202)
def run_start(request: Request, thread_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    _thread(request, thread_id, write=True)
    q = str(body.get("question") or "").strip()
    if not q:
        raise refuse(422, "WHATIF_EMPTY", "Type a question or a scenario.")
    if q.startswith("::") and not (q.startswith("::custom ") or q.startswith("::library ") or q == "::execute"):
        raise refuse(422, "WHATIF_EMPTY", "Not a question.")
    u = access.user(request)
    return _run_view(_start(thread_id, u.get("username", ""), q[:4000], request.headers.get("Idempotency-Key", "")))


@app.post(PREFIX + "/threads/{thread_id}/title")
def thread_title(request: Request, thread_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    _thread(request, thread_id, write=True)
    title = str(body.get("title") or "").strip()[:120]
    if not title:
        raise refuse(422, "WHATIF_EMPTY", "A title cannot be empty.")
    store().rename(thread_id, title)
    return {"thread_id": thread_id, "title": title}


@app.get(PREFIX + "/runs/{run_id}")
def run_get(request: Request, run_id: str) -> dict[str, Any]:
    r = store().run(run_id)
    if r is None:
        raise refuse(404, "WHATIF_RUN_NOT_FOUND", f"{run_id} is not a run.")
    _thread(request, r["thread_id"])
    return _run_view(r)


@app.get(PREFIX + "/runs/{run_id}/events")
async def run_events(request: Request, run_id: str, cursor: int = Query(0)) -> StreamingResponse:
    r = store().run(run_id)
    if r is None:
        raise refuse(404, "WHATIF_RUN_NOT_FOUND", f"{run_id} is not a run.")
    _thread(request, r["thread_id"])
    start = int(request.headers.get("Last-Event-ID") or cursor or 0)

    async def stream():
        seen = start
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            rows = store().events_since(run_id, seen)
            for e in rows:
                seen = e["seq"]
                yield f"id: {e['seq']}\nevent: {e['event_type']}\ndata: {json.dumps(e)}\n\n"
            run = store().run(run_id)
            if run and run["terminal"] and not store().events_since(run_id, seen):
                yield f"event: run.settled\ndata: {json.dumps(_run_view(run))}\n\n"
                return
            await asyncio.sleep(0.1)
            idle += 0.1
            if idle >= 5:
                idle = 0
                yield ": heartbeat\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ documents

def _current(t: dict) -> tuple[Scenario, str]:
    sc = t["state"].get("scenario")
    if not sc:
        raise refuse(422, "WHATIF_NOTHING_TO_REPORT", "This thread has no scenario yet.")
    return Scenario.from_dict(sc), (t["state"].get("method") or "delta")


@app.get(PREFIX + "/threads/{thread_id}/report.docx")
def thread_report(request: Request, thread_id: str) -> Response:
    t = _thread(request, thread_id)
    sc, method = _current(t)
    return _docx(sc, method, t["title"], t["owner"], thread_id, user_label(access.user(request)))


@app.get(PREFIX + "/scenarios/{sid}/report.docx")
def scenario_report(request: Request, sid: str) -> Response:
    r = store().scenario(sid)
    if r is None or not access.can_see(access.user(request), r["owner"], r["team"], "whatif-scenario", sid, request):
        raise refuse(404, "WHATIF_SCENARIO_NOT_FOUND", f"{sid} is not a scenario you can see.")
    return _docx(Scenario.from_dict(r["scenario"]), r["method"] or "delta", r["name"], r["owner"], sid,
                 user_label(access.user(request)))


def _docx(sc: Scenario, method: str, title: str, owner: str, ref: str, by: str = "") -> Response:
    from backend.whatif_v5 import report_docx
    try:
        body, name = report_docx.build(sc, method, title, owner, ref, by)
    except runner.RunError as e:
        raise refuse(422, "WHATIF_RUN_REFUSED", str(e)) from e
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get(PREFIX + "/threads/{thread_id}/export.xlsx")
def thread_export(request: Request, thread_id: str) -> Response:
    from backend.whatif_v5 import result_workbook
    t = _thread(request, thread_id)
    sc, method = _current(t)
    result = runner.run(sc, method)
    body = result_workbook.build(result, t["title"], user_label(access.user(request)))
    name = f"whatif_{sc.domain}_{sc.period}_{method}_{result['run_id']}.xlsx"
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------ report pack ("Add to report")

def _item_view(i: dict) -> dict:
    return {k: i[k] for k in ("item_id", "kind", "ref", "name", "domain", "method", "added_at", "change")}


@app.get(PREFIX + "/reports")
def report_pack(request: Request) -> dict[str, Any]:
    u = access.user(request)
    return {"items": [_item_view(i) for i in store().report_items(u.get("username", ""))]}


@app.post(PREFIX + "/reports/items", status_code=201)
def report_add(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    u = access.user(request)
    if body.get("thread_id"):
        t = _thread(request, str(body["thread_id"]))
        sc, method = _current(t)
        name, kind, ref = t["title"], "whatif-thread", t["thread_id"]
    elif body.get("scenario_id"):
        r = store().scenario(str(body["scenario_id"]))
        if r is None or not access.can_see(u, r["owner"], r["team"], "whatif-scenario", r["scenario_id"], request):
            raise refuse(404, "WHATIF_SCENARIO_NOT_FOUND", "Not a scenario you can see.")
        sc, method, name, kind, ref = Scenario.from_dict(r["scenario"]), r["method"] or "delta", r["name"], "whatif-scenario", r["scenario_id"]
    else:
        raise refuse(422, "WHATIF_EMPTY", "Name a thread or a saved scenario.")
    try:
        change = runner.run(sc, method)["cards"]["change"]
    except runner.RunError as e:
        raise refuse(422, "WHATIF_RUN_REFUSED", str(e)) from e
    added = store().add_report_item({"owner": u.get("username", ""), "kind": kind, "ref": ref, "name": name,
                                     "domain": sc.domain, "method": method, "scenario": sc.to_dict(), "change": change})
    return {"added": _item_view(added), "items": [_item_view(i) for i in store().report_items(u.get("username", ""))]}


@app.delete(PREFIX + "/reports/items/{item_id}")
def report_remove(request: Request, item_id: str) -> dict[str, Any]:
    u = access.user(request)
    store().remove_report_item(item_id, u.get("username", ""))
    return {"items": [_item_view(i) for i in store().report_items(u.get("username", ""))]}


@app.get(PREFIX + "/reports/pack.docx")
def report_pack_docx(request: Request) -> Response:
    from backend.whatif_v5 import report_docx
    u = access.user(request)
    items = store().report_items(u.get("username", ""))
    if not items:
        raise refuse(422, "WHATIF_NOTHING_TO_REPORT", "The report pack is empty.")
    body = report_docx.pack([(Scenario.from_dict(i["scenario"]), i["method"], i["name"], i["ref"]) for i in items],
                            user_label(u))
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="whatif_report_pack.docx"'})


# ------------------------------------------------------------------ Early Warning cohorts

@app.get(PREFIX + "/cohort/{object_id}")
def cohort(object_id: str) -> dict[str, Any]:
    from backend.whatif_v5.chat.cohort import summary
    try:
        return summary(object_id)
    except cohorts.CohortError as e:
        raise refuse(404, "WHATIF_COHORT_NOT_FOUND", str(e)) from e


@app.get(PREFIX + "/cohort/{object_id}/summary")
def cohort_dashboard(object_id: str) -> dict[str, Any]:
    from backend.whatif_v5 import summary
    try:
        return summary.cohort(object_id)
    except cohorts.CohortError as e:
        raise refuse(404, "WHATIF_COHORT_NOT_FOUND", str(e)) from e
    except (summary.SummaryError, dstore.DomainError) as e:
        raise refuse(422, "WHATIF_SUMMARY_REFUSED", str(e)) from e


_ = st
