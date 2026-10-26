"""The Deal Desk service (port 8508).

One process serves two prefixes:

  /api/v1/dealdesk/...        the engine (docs/v5/DEALDESK_API.md): Session C1's app when it is in
                              this checkout, the contract-shaped reference engine until then
  /api/v1/dealdesk/desk/...   the thread layer (this package): the conversation, the screen bundles,
                              saved analyses, the Word report and the Playbook section

    GET  /desk/health
    GET  /desk/proposals/{id}/analysis      the bundle a thread opens with: the ask and the current terms
                                            (compute), the iso-RAROC grid, the amount curve, the tornado and
                                            the stress table, and the thread's state
    POST /desk/proposals/{id}/state         {terms?, recommended?, optimisation?} the thread's working terms
    GET  /desk/proposals/{id}/thread        the conversation and its state
    POST /desk/proposals/{id}/thread        {question} -> one answered turn
    POST /desk/proposals/{id}/optimise      {fixed?, bounds?, weights?, allow_soft?} the Optimise button: the engine's
                                            optimisation and the commentary on it as a thread turn
    POST /desk/ask                          {question} -> an answer on the pipeline and portfolio headroom
    POST /desk/ingest                       a credit memo (.docx) -> proposal fields with source and confidence
    POST /desk/proposals                    {fields, source} a proposal from the form or a confirmed memo
    POST /desk/analyses                     {proposal_id, name, terms?} save
    GET  /desk/analyses, GET/DELETE /desk/analyses/{id}
    GET  /desk/proposals/{id}/report.docx   the 5-page Word report
    GET  /desk/analyses/{id}/report.docx
    GET  /desk/section?type=&id=            a Playbook section (PLAYBOOK_API.md 3)

Every figure is produced by the engine through `engine.py`.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import Response

from backend.dealdesk_thread import convo, engine, ingest, paths, report_docx
from backend.dealdesk_thread import store as store_mod
from backend.dealdesk_thread.store import Store

PREFIX = "/api/v1/dealdesk/desk"
VERSION = "dealdesk-thread-1.0.0"
MARGINS = list(range(100, 551, 50))
TENORS = list(range(1, 11))
AMOUNT_STEPS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2)

app = FastAPI(title="CreditProbe v5 Deal Desk", version=VERSION)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "deal_desk", run_paths=r"/optimise$")
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

# The process trace of every thread turn (PLAN_R5 G4, docs/v5/THREAD_API.md 2.2): GET /desk/trace/{id} + X-Trace-Id.
from backend.convo import trace as _trace  # noqa: E402
_trace.install(app, PREFIX)
# Deal Desk edition: the model telemetry (tokens, time, model per call and per turn) at GET /desk/telemetry/...
from backend.convo import telemetry_api as _telemetry_api  # noqa: E402
_telemetry_api.install(app, PREFIX, "deal_desk")

STORE: Store | None = None


def store() -> Store:
    global STORE
    if STORE is None:
        STORE = Store()
    return STORE


@app.on_event("startup")
def _seed_on_startup() -> None:  # Deal Desk edition: two desk threads and two analyses on an empty store (never raises)
    from backend.dealdesk_thread import seed
    seed.apply(store())


def refuse(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error_code": code, "message": message})


def user(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request) or {}
    except Exception:  # noqa: BLE001 - no identity service: anonymous
        return {}


def _proposal(pid: str) -> dict:
    try:
        return engine.get(f"/proposals/{pid}")["proposal"]
    except engine.EngineError as e:
        raise refuse(e.status, "DEALDESK_PROPOSAL_NOT_FOUND" if e.status == 404 else "DEALDESK_ENGINE", str(e)) from None


@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": "creditprobe-v5-dealdesk", "port": paths.API_PORT, "version": VERSION,
            "engine": engine.source(), "assistant": convo.describe(), "imports_cockpit": False}


def heat_axis(ask: dict[str, Any]) -> tuple[str, list[float], list[int]]:
    """R7 U2: the heatmap's price lever and its values, chosen so the ask always sits on the grid.

    A funded ask is priced on margin: 100 to 550 bps as before, shifted down for an ask under 100 bps (DD-14, DD-15)
    and up for one over 550. An unfunded ask (an LG or LC, margin 0: DD-07, DD-09) is priced on commission, so the
    grid runs over commission instead of a margin that does not move its RAROC.
    """
    tenors = list(range(1, max(10, int(ask.get("tenor_years") or 1)) + 1))
    unfunded = ask.get("facility_type") in ("performance_lg", "financial_lg", "trade_lc") or (not ask.get("margin_bps") and ask.get("commission_bps"))
    if unfunded:
        c = float(ask.get("commission_bps") or 0)
        start = max(0, int(c // 25) * 25 - 100)
        return "commission_bps", [start + 25 * i for i in range(10)], tenors
    m = float(ask.get("margin_bps") or 0)
    start = 100
    if m < 100:
        start = max(0, int(m // 50) * 50 - 50)
    elif m > 550:
        start = int(m // 50) * 50 - 400
    return "margin_bps", [start + 50 * i for i in range(10)], tenors


def bundle(pid: str, terms: dict | None) -> dict[str, Any]:
    """Everything a deal's screens draw, from engine calls only."""
    p = _proposal(pid)
    ask = p["ask"]
    rec = engine.Recorder()
    t0 = time.perf_counter()
    ask_res = rec.post("/compute", {"proposal_id": pid})
    cur = rec.post("/compute", {"proposal_id": pid, "terms": terms}) if terms else ask_res
    hx, hxs, hys = heat_axis({**ask, **(terms or {})})
    heat = rec.post("/grid", {"proposal_id": pid, "terms": terms, "x": hx, "x_values": hxs, "y": "tenor_years",
                              "y_values": hys, "metric": "lifetime_raroc"})
    curve = rec.post("/grid", {"proposal_id": pid, "terms": terms, "x": "amount", "x_values": [round(ask["amount"] * s, 3) for s in AMOUNT_STEPS],
                               "metric": "lifetime_raroc"})
    tornado = rec.post("/tornado", {"proposal_id": pid, "terms": terms})
    stress = rec.post("/stress", {"proposal_id": pid, "terms": terms, "scenario": "all"})
    from backend.dealdesk_thread import proposal_full
    return {"proposal": p, "proposal_full": proposal_full.full(p), "ask": ask_res, "current": cur, "heatmap": heat, "amount_curve": curve, "tornado": tornado, "stress": stress,
            "trace_ids": rec.trace_ids, "ms": round((time.perf_counter() - t0) * 1000, 1)}


@app.get(PREFIX + "/proposals/{pid}/analysis")
def analysis(pid: str) -> dict[str, Any]:
    st = store().state(pid)
    out = bundle(pid, st.get("terms"))
    out["state"] = st
    return out


@app.post(PREFIX + "/proposals/{pid}/state")
def set_state(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _proposal(pid)
    st = store().state(pid)
    for k in ("terms", "recommended", "optimisation"):
        if k in body:
            st[k] = body[k]
    store().set_state(pid, st)
    return st


@app.get(PREFIX + "/proposals/{pid}/thread")
def thread(pid: str) -> dict[str, Any]:
    _proposal(pid)
    return {"proposal_id": pid, "turns": store().turns(pid), "state": store().state(pid)}


@app.post(PREFIX + "/proposals/{pid}/thread")
def ask(pid: str, request: Request, body: dict = Body(...)) -> dict[str, Any]:
    p = _proposal(pid)
    q = str(body.get("question") or "").strip()
    if not q:
        raise refuse(422, "DEALDESK_EMPTY_QUESTION", "Ask a question.")
    u = user(request)
    answer = convo.answer(store(), p, q, u, history=store().turns(pid))
    _trace.attach(answer)
    tid = store().add_turn(pid, str(u.get("username") or ""), q, answer)
    return {"turn_id": tid, "question": q, "answer": answer, "state": store().state(pid)}


@app.post(PREFIX + "/proposals/{pid}/optimise")
def optimise(pid: str, request: Request, body: dict = Body(default={})) -> dict[str, Any]:
    """The Optimise button: the engine's optimisation and the assistant's commentary on it, kept as a thread turn."""
    p = _proposal(pid)
    u = user(request)
    try:
        opt, answer = convo.optimise_turn(store(), p, body or {}, u)
    except engine.EngineError as e:
        raise refuse(e.status, "DEALDESK_ENGINE", str(e)) from None
    _trace.attach(answer)
    tid = store().add_turn(pid, str(u.get("username") or ""), "Optimise", answer)
    return {"optimisation": opt, "turn": {"turn_id": tid, "question": "Optimise", "answer": answer}, "state": store().state(pid)}


@app.post(PREFIX + "/ask")
def ask_desk(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """A question on the Deal Desk thread. R14 n (K16): without `thread_id` it opens a NEW desk thread (title from
    the question, top of Recent work); with one, it continues that thread (only input typed inside an open thread
    does). The fixed "desk" id is gone."""
    q = str(body.get("question") or "").strip()
    if not q:
        raise refuse(422, "DEALDESK_EMPTY_QUESTION", "Ask a question.")
    u = user(request)
    me = str(u.get("username") or "")
    tid = str(body.get("thread_id") or "").strip()
    th = store().desk_thread(tid) if tid else None
    if tid and th is None:
        raise refuse(404, "DEALDESK_NO_THREAD", f"No Deal Desk thread {tid}.")
    if th is None:
        th = store().create_desk_thread(me, q)
    key = store_mod.desk_key(th["thread_id"])
    answer = convo.answer(store(), None, q, u, history=store().turns(key))
    _trace.attach(answer)
    turn = store().add_turn(key, me, q, answer)
    store().touch_desk_thread(th["thread_id"])
    answer["turn_id"] = turn
    answer["thread_id"] = th["thread_id"]
    answer["thread_title"] = th["title"]
    return answer


@app.post(PREFIX + "/desk-threads")
def new_desk_thread(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """Open a new desk thread for a question (the landing does this, then asks inside it once)."""
    q = str(body.get("question") or "").strip()
    if not q:
        raise refuse(422, "DEALDESK_EMPTY_QUESTION", "Ask a question.")
    return store().create_desk_thread(str(user(request).get("username") or ""), q)


@app.get(PREFIX + "/desk-threads")
def list_desk_threads(request: Request, limit: int = 20, mine: bool = True) -> dict[str, Any]:
    me = str(user(request).get("username") or "")
    return {"threads": store().desk_threads(me if (mine and me) else None, max(1, min(limit, 100)))}


@app.get(PREFIX + "/desk-threads/{thread_id}")
def get_desk_thread(thread_id: str) -> dict[str, Any]:
    th = store().desk_thread(thread_id)
    if th is None:
        raise refuse(404, "DEALDESK_NO_THREAD", f"No Deal Desk thread {thread_id}.")
    return {**th, "turns_list": store().turns(store_mod.desk_key(thread_id))}


@app.get(PREFIX + "/desk-thread")
def desk_thread(thread: str = "") -> dict[str, Any]:
    """One desk thread's turns (R14 n: `?thread=<id>`). Without an id: no turns (the old shared thread is retired)."""
    if not thread:
        return {"turns": []}
    return {"turns": store().turns(store_mod.desk_key(thread)), "thread": store().desk_thread(thread)}


@app.get(PREFIX + "/recent")
def recent(request: Request, limit: int = 20) -> dict[str, Any]:
    """D3: every saved or optimised analysis (time, user, proposal, outcome, RAROC, link back to its thread) and the
    "continue where you left off" row (the user's latest thread)."""
    names = {}
    # R14 U (K17): names for every deal the desk knows (dd_deal + uploads), so an R12 or PL deal has its obligor too.
    for path in ("/deals", "/proposals"):
        try:
            names = {x["proposal_id"]: x for x in engine.get(path)["proposals"]}
            break
        except (engine.EngineError, KeyError):
            continue
    rows: list[dict[str, Any]] = []
    for a in store().analyses():
        m = a.get("metrics") or {}
        rows.append({"kind": "saved", "id": a["analysis_id"], "time": a["created"], "user": a.get("owner") or "", "proposal_id": a["proposal_id"],
                     "obligor": a.get("obligor") or names.get(a["proposal_id"], {}).get("obligor_name", ""), "name": a.get("name", ""),
                     "outcome": ("Clears the hurdle" if m.get("clears_hurdle") else "Below the hurdle"),
                     "approval": (a.get("approval") or {}).get("level"), "lifetime_raroc": m.get("lifetime_raroc"), "sva": m.get("sva"),
                     "href": f"/deal-desk/{a['proposal_id']}?analysis={a['analysis_id']}", "report": f"{PREFIX}/analyses/{a['analysis_id']}/report.docx"})
    for t in store().recent_turns(200):
        ans = t["answer"] or {}
        if t["proposal_id"] == "desk" or t["proposal_id"].startswith(store_mod.DESK_PREFIX) or not (ans.get("intent") == "optimise" or ans.get("action") == "optimise"):
            continue
        sm = ans.get("summary") or {}
        feas = sm.get("feasible")
        rows.append({"kind": "optimised", "id": t["turn_id"], "time": t["created"], "user": t["owner"] or "", "proposal_id": t["proposal_id"],
                     "obligor": names.get(t["proposal_id"], {}).get("obligor_name", ""), "name": t["question"],
                     "outcome": "Counter-offer found" if feas else ("No structure clears" if feas is False else "Optimised"),
                     "approval": sm.get("approval"), "lifetime_raroc": sm.get("lifetime_raroc"), "sva": sm.get("sva"),
                     "href": f"/deal-desk/{t['proposal_id']}?turn={t['turn_id']}", "report": None})
    rows.sort(key=lambda r: -float(r["time"] or 0))
    me = str(user(request).get("username") or "")
    # R14 n (K16): desk turns live under `desk:<thread_id>`; the old shared "desk" turns are history only.
    last = next((t for t in store().recent_turns(50, owner=me or None) if t["proposal_id"] != "desk"), None)
    cont = None
    if last:
        pid = last["proposal_id"]
        if pid.startswith(store_mod.DESK_PREFIX):
            th = store().desk_thread(pid[len(store_mod.DESK_PREFIX):]) or {}
            cont = {"proposal_id": "desk", "thread_id": th.get("thread_id"), "obligor": "Deal Desk",
                    "title": th.get("title") or last["question"], "question": last["question"], "time": last["created"],
                    "turns": th.get("turns", 0), "href": th.get("href") or "/deal-desk"}
        else:
            cont = {"proposal_id": pid, "obligor": names.get(pid, {}).get("obligor_name", ""),
                    "question": last["question"], "time": last["created"], "turns": len(store().turns(pid)),
                    "href": f"/deal-desk/{pid}"}
    threads = store().desk_threads(me or None, 6)
    return {"recent": rows[: max(1, min(limit, 100))], "continue": cont, "threads": threads}


@app.post(PREFIX + "/ingest")
async def ingest_memo(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise refuse(422, "DEALDESK_EMPTY_FILE", "The file is empty.")
    try:
        return ingest.extract(data, file.filename or "memo.docx")
    except ingest.IngestError as e:
        raise refuse(422, "DEALDESK_UNREADABLE_MEMO", str(e)) from None


@app.get(PREFIX + "/groups")
def groups(q: str = "", limit: int = 20) -> dict[str, Any]:
    """PLAN_R6 D1: type-ahead over the corporate book's connected groups."""
    return {"groups": ingest.groups(q, max(1, min(limit, 50)))}


@app.post(PREFIX + "/proposals", status_code=201)
def create(body: dict = Body(...)) -> dict[str, Any]:
    """A proposal from the form or from a confirmed memo extraction, in the engine's Proposal schema."""
    try:
        proposal = ingest.proposal_from_fields(body.get("fields") or {}, body.get("source") or {}, long=body.get("long") or None)
    except ingest.IngestError as e:
        raise refuse(422, "DEALDESK_BAD_PROPOSAL", str(e)) from None
    return engine.post("/proposals", proposal)["proposal"]


@app.post(PREFIX + "/analyses", status_code=201)
def save(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    pid = str(body.get("proposal_id") or "")
    p = _proposal(pid)
    st = store().state(pid)
    terms = body.get("terms") or st.get("terms")
    res = engine.post("/compute", {"proposal_id": pid, "terms": terms})
    u = user(request)
    name = str(body.get("name") or f"{p['obligor']['name']} · {pid}")[:200]
    return store().save_analysis(pid, str(u.get("username") or ""), str(u.get("team") or ""), name,
                                 {"terms": res["terms"], "metrics": res["metrics"], "approval": res["approval"], "trace_id": res["trace_id"],
                                  "obligor": p["obligor"]["name"], "optimisation_trace": (st.get("optimisation") or {}).get("trace_id")})


@app.get(PREFIX + "/analyses")
def analyses() -> dict[str, Any]:
    return {"analyses": store().analyses()}


@app.get(PREFIX + "/analyses/{aid}")
def get_analysis(aid: str) -> dict[str, Any]:
    a = store().analysis(aid)
    if not a:
        raise refuse(404, "DEALDESK_ANALYSIS_NOT_FOUND", f"{aid} is not a saved Deal Desk analysis.")
    return a


@app.delete(PREFIX + "/analyses/{aid}")
def delete_analysis(aid: str) -> dict[str, Any]:
    store().remove_analysis(aid)
    return {"deleted": aid}


def _docx(request: Request, pid: str, terms: dict | None, ref: str) -> Response:
    try:
        from backend.house_style import user_label
        by = user_label(user(request))
    except Exception:  # noqa: BLE001
        by = ""
    data, filename = report_docx.build(pid, terms, store().state(pid), store().turns(pid), generated_by=by, reference=ref)
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get(PREFIX + "/proposals/{pid}/report.docx")
def report(pid: str, request: Request) -> Response:
    _proposal(pid)
    return _docx(request, pid, store().state(pid).get("terms"), pid)


@app.get(PREFIX + "/analyses/{aid}/report.docx")
def analysis_report(aid: str, request: Request) -> Response:
    a = get_analysis(aid)
    return _docx(request, a["proposal_id"], a["terms"], aid)


@app.get(PREFIX + "/section")
def section(type: str = Query(...), id: str = Query(...)) -> dict[str, Any]:  # noqa: A002 - PLAYBOOK_API names it type
    if type == "dealdesk-analysis":
        a = get_analysis(id)
        return report_docx.section(a["proposal_id"], a["terms"], id)
    if type == "dealdesk-proposal":
        _proposal(id)
        return report_docx.section(id, store().state(id).get("terms"), id)
    raise refuse(422, "DEALDESK_BAD_SECTION", "type must be dealdesk-analysis or dealdesk-proposal.")


# The engine on the same port: everything under /api/v1/dealdesk that is not /desk.
app.mount("/", engine.app())
