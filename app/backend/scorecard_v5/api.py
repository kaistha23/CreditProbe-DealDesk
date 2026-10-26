"""The Scorecard Validation API: its own app on its own port (8507), prefix /api/v1/scorecard.

Choose a scorecard, agree the plan, run it, review, report (PLAN_R3 S2).

    GET  /health
    GET  /meta                              scorecards, test groups, thresholds, the assistant
    GET  /validations                       past validations visible to the caller
    GET  /validations/{id}                  one validation: plan, sections, tests, tables, Plotly figures, findings, review
    POST /validations/{id}/review           {conclusion: fit | conditions | not_fit, note}
    GET  /validations/{id}/report.docx      the Word validation report (house style)
    GET  /validations/{id}/export.xlsx      the results as a house-style workbook
    POST /validations/{id}/playbook         {report_id | new_report} hand the section and the Word report to Playbook
    GET  /playbook/reports                  the caller's editable Playbook reports (for the Add-to-report dialog)
    GET  /playbook/sources?q=               validations Playbook may import by name (PLAYBOOK_API.md section 8)
    GET  /playbook/section?id=              one validation as a Playbook section
    POST /threads                           {scorecard_id?, question?} -> thread
    GET  /threads                           recent threads visible to the caller
    GET  /threads/{id}                      thread, transcript, validations
    POST /threads/{id}/messages             {text} -> the assistant's answer (a turn)
    POST /threads/{id}/title                {title}
    DELETE /threads/{id}                    remove a conversation and its validations (never a seeded one)

R16 M8, scorecard monitoring against the CBUAE MMSG criteria (backend/scorecard_v5/monitoring):
    GET  /monitor/front                     "Scorecards today": plain words, health line per scorecard, the 5-10 breaches that matter
    GET  /monitor/scorecards/{sid}          the deep dive: tests over time, segment drill, characteristics, root cause, actions, findings
    GET  /monitor/register                  the findings register (seed relation + run time), overdue flags
    POST /monitor/register/{finding_id}     {status?, owner?, due_on?, note?} update a finding
    GET  /monitor/schedule                  monitoring schedule per scorecard and where the alerts go
    GET  /monitor/brief                     red breaches on Tier 1 models, for Noor's brief
    GET  /validations/{id}/conclusion       the rule-based proposed conclusion and the maker-checker record
    POST /validations/{id}/conclusion       maker: {conclusion: fit | conditions | not_fit, note}
    POST /validations/{id}/conclusion/decide  checker (not the maker; risk, validation or admin team): {approve: bool, note}
    GET  /validations/{id}/mmsg.docx        the MMSG validation report (Word, house style)

Reads the scorecard domain read-only. Writes only its own store (var/scorecard_v5/scorecard.sqlite).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import Response

from backend.convo import trace
from backend.house_style import generated_by
from backend.scorecard_v5 import access, assistant, engine, export_xlsx, paths, playbook, report_docx, seed
from backend.scorecard_v5.store import Store
from backend.scorecard_v5.monitoring import front as mon_front, report as mon_report

PREFIX = "/api/v1/scorecard"
VERSION = "scorecard-v5-1.0.0"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(title="CreditProbe v5 Scorecard Validation", version=VERSION)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "scorecard")
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                   allow_headers=["*"], expose_headers=["Content-Disposition"])
# The process trace of a thread turn (PLAN_R5 G4, docs/v5/THREAD_API.md 2.2): GET /trace/{id} + X-Trace-Id middleware.
trace.install(app, PREFIX)

STORE: Store | None = None
_LOCK = threading.Lock()


def store() -> Store:
    global STORE
    with _LOCK:
        if STORE is None:
            STORE = Store()
            seed.ensure(STORE)
        return STORE


@app.on_event("startup")
def _startup() -> None:
    store()


def refuse(status: int, message: str) -> HTTPException:
    return HTTPException(status, message)


def _guard_write(request: Request) -> dict[str, Any]:
    """The signed-in user for a write; refused while the Administrator is viewing as someone."""
    name = access.viewing_as(request)
    if name:
        raise refuse(403, f"Read only while viewing as {name}.")
    return access.user(request)


class Ctx(assistant.Context):
    def __init__(self, owner: str, team: str, thread_id: str):
        self.owner, self.team, self.thread_id = owner, team, thread_id

    def result(self, validation_id: str) -> dict[str, Any] | None:
        v = store().validation(validation_id)
        return v["result"] if v else None

    def prior(self, scorecard_id: str, before_id: str) -> list[dict[str, Any]]:
        cur = store().validation(before_id, full=False)
        out = []
        for v in store().validations():
            if v["scorecard_id"] == scorecard_id and v["validation_id"] != before_id and v["created_at"] < (cur["created_at"] if cur else time.time()):
                out.append({"validation_id": v["validation_id"], "as_of": v["as_of"], "created": time.strftime("%d %b %Y", time.gmtime(v["created_at"]))})
        return out

    def turns(self) -> list[dict[str, Any]]:
        return store().turns(self.thread_id)

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        trace.step("querying", "Running the validation tests")
        res = engine.run(plan)
        sc = res["scorecard"]
        title = f"{sc['name']} v{sc['version']}: validation as of {plan['as_of']}"
        v = store().add_validation(thread_id=self.thread_id, scorecard_id=plan["scorecard_id"], owner=self.owner, team=self.team, title=title, plan=res["plan"], result=res)
        # R16 M8: the validation's red and amber tests enter the findings register with an owner and a due date.
        # An open finding an earlier CreditProbe validation raised on the same test is superseded by the new one (no duplicates).
        new = mon_report.findings_from(v["validation_id"], plan["scorecard_id"], res, mon_front.today())
        titles = {f["title"] for f in new}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for old in store().findings():
            if old.get("origin") == "validation" and old["scorecard_id"] == plan["scorecard_id"] and old["status"] != "closed" and old["title"] in titles:
                old["status"] = "closed"
                old["history"] = list(old.get("history") or []) + [{"by": "CreditProbe", "at": now, "change": {"status": "closed"},
                                                                     "note": f"superseded by {v['validation_id']}"}]
                store().put_finding(old)
        for f in new:
            store().put_finding(f)
        return {"validation_id": v["validation_id"], "summary": res["summary"], "sample": res["sample"], "key_charts": res.get("key_charts", [])}


def _thread_row(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t[k] for k in ("thread_id", "owner", "scorecard_id", "title", "created_at", "updated_at") if k in t} | {"stage": t.get("stage") or t.get("state", {}).get("stage", "choose")}


def _visible_thread(request: Request, thread_id: str, write: bool = False) -> dict[str, Any]:
    t = store().thread(thread_id)
    if not t:
        raise refuse(404, "That validation thread does not exist.")
    u = access.user(request)
    if not access.can_see(u, t["owner"], t["team"], thread_id, request) and not _validation_shared(request, thread_id) and not _checker(u):
        raise refuse(404, "That validation thread does not exist.")
    if write and not access.can_write(u, t["owner"]):
        raise refuse(403, "Only the owner or the Administrator can continue this thread.")
    return t


def _checker(u: dict[str, Any]) -> bool:
    """R16 M8: Risk and Model Validation read every validation (they check its conclusion; four eyes)."""
    return bool(u.get("username")) and u.get("team") in ("risk", "validation")


def _validation_shared(request: Request, thread_id: str) -> bool:
    return any((access.KIND, v["validation_id"]) in access.shared_with_me(request) for v in store().validation_for_thread(thread_id))


def _visible_validation(request: Request, validation_id: str, full: bool = True) -> dict[str, Any]:
    v = store().validation(validation_id, full=full)
    if not v:
        raise refuse(404, "That validation does not exist.")
    if not access.can_see(access.user(request), v["owner"], v["team"], validation_id, request) and not _checker(access.user(request)):
        raise refuse(404, "That validation does not exist.")
    return v


def _validation_row(v: dict[str, Any]) -> dict[str, Any]:
    sc = engine.scorecards_by_id()[v["scorecard_id"]]
    return {"validation_id": v["validation_id"], "thread_id": v["thread_id"], "scorecard_id": v["scorecard_id"], "scorecard": sc["name"], "version": sc["version"],
            "type": sc["type"], "book": sc["book"], "title": v["title"], "as_of": v["as_of"], "overall": v["overall"], "counts": v["counts"], "owner": v["owner"],
            "created_at": v["created_at"], "review": v["review"], "plan": v["plan"]}


@app.get(f"{PREFIX}/health")
def health() -> dict[str, Any]:
    n = len(store().validations())
    return {"status": "ok", "version": VERSION, "engine": engine.ENGINE_VERSION, "validations": n,
            "scorecards": [s["scorecard_id"] for s in engine.scorecards()], "assistant": {"planner": "deterministic", "model_available": False}}


@app.get(f"{PREFIX}/meta")
def meta() -> dict[str, Any]:
    return {"scorecards": engine.scorecards(), "groups": [{"group": g, "title": engine.GROUP_TITLES[g], "what": assistant.WHAT[g]} for g in engine.GROUPS],
            "thresholds": {sid: {k: {"label": v["label"], "text": v["text"]} for k, v in engine.thresholds_for(sid).items()} for sid in ("RET-APP", "RET-BEH", "SME-ANN")},
            "assistant": {"planner": "deterministic", "model_available": False}, "examples": [
                "Validate the SME scorecard", "Validate the retail application scorecard", "Validate the retail behavioural scorecard", "Which scorecards can you validate?"]}


@app.get(f"{PREFIX}/validations")
def validations(request: Request) -> dict[str, Any]:
    u = access.user(request)
    rows = [_validation_row(v) for v in store().validations() if access.can_see(u, v["owner"], v["team"], v["validation_id"], request)]
    return {"validations": rows}


@app.get(f"{PREFIX}/validations/{{validation_id}}")
def validation(validation_id: str, request: Request) -> dict[str, Any]:
    v = _visible_validation(request, validation_id)
    return _validation_row(v) | {"result": v["result"], "seed": v["seed"]}


@app.post(f"{PREFIX}/validations/{{validation_id}}/review")
def review(validation_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _guard_write(request)
    v = _visible_validation(request, validation_id, full=False)
    u = access.user(request)
    if u.get("username") and not access.can_write(u, v["owner"]) and not u.get("is_admin"):
        raise refuse(403, "Only the owner or the Administrator can record the review.")
    concl = str(body.get("conclusion") or "")
    if concl not in report_docx.CONCLUSIONS:
        raise refuse(422, "conclusion must be fit, conditions or not_fit.")
    rec = {"status": "reviewed", "conclusion": concl, "note": str(body.get("note") or "")[:2000], "reviewer": u.get("name") or u.get("username") or "",
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    store().set_review(validation_id, rec)
    return {"review": rec}


@app.get(f"{PREFIX}/validations/{{validation_id}}/report.docx")
def report(validation_id: str, request: Request) -> Response:
    v = _visible_validation(request, validation_id)
    body = report_docx.build(v, generated_by=generated_by(request), reference=validation_id)
    return Response(body, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{validation_id}.docx"'})


@app.get(f"{PREFIX}/validations/{{validation_id}}/export.xlsx")
def export(validation_id: str, request: Request) -> Response:
    v = _visible_validation(request, validation_id)
    return Response(export_xlsx.build(v, generated_by=generated_by(request)), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{validation_id}.xlsx"'})


@app.get(f"{PREFIX}/playbook/reports")
def playbook_reports(request: Request) -> dict[str, Any]:
    return playbook.reports(request)


@app.post(f"{PREFIX}/validations/{{validation_id}}/playbook")
def to_playbook(validation_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _guard_write(request)
    v = _visible_validation(request, validation_id)
    if bool(body.get("report_id")) == bool(body.get("new_report")):
        raise refuse(422, "Send either report_id or new_report.")
    docx = report_docx.build(v, generated_by=generated_by(request), reference=validation_id)
    return playbook.import_section(request, v, body, docx)


@app.get(f"{PREFIX}/playbook/sources")
def playbook_sources(request: Request, q: str = Query("")) -> dict[str, Any]:
    u = access.user(request)
    out = []
    for v in store().validations():
        if not access.can_see(u, v["owner"], v["team"], v["validation_id"], request):
            continue
        row = _validation_row(v)
        text = f"{row['title']} {row['scorecard']} {row['as_of']}".lower()
        if q and not all(w in text for w in q.lower().split()):
            continue
        full = store().validation(v["validation_id"])
        out.append(playbook.source(full))
    return {"sources": out[:50]}


@app.get(f"{PREFIX}/playbook/section")
def playbook_section(request: Request, id: str = Query(...)) -> dict[str, Any]:
    v = _visible_validation(request, id)
    return {"source": playbook.source(v), "section": playbook.section(v)}


# ---------------------------------------------------------------- threads


def _thread_view(t: dict[str, Any]) -> dict[str, Any]:
    vs = store().validation_for_thread(t["thread_id"])
    sc = engine.scorecards_by_id().get(t["scorecard_id"]) if t["scorecard_id"] else None
    return {"thread_id": t["thread_id"], "title": t["title"], "owner": t["owner"], "team": t["team"], "scorecard_id": t["scorecard_id"],
            "scorecard": sc, "created_at": t["created_at"], "updated_at": t["updated_at"], "stage": t["state"].get("stage", "choose"),
            "plan": t["state"].get("plan"), "validation_id": t["state"].get("validation_id"), "turns": store().turns(t["thread_id"]),
            "validations": [_validation_row(v) for v in vs]}


def _turn(t: dict[str, Any], text: str) -> dict[str, Any]:
    state = dict(t["state"])
    ctx = Ctx(t["owner"], t["team"], t["thread_id"])
    answer = assistant.respond(state, text, ctx)
    trace.attach(answer)
    store().add_turn(t["thread_id"], text, answer)
    sid = state.get("scorecard_id") or t["scorecard_id"]
    title = t["title"]
    if title == "New validation" and sid:
        title = f"{engine.scorecards_by_id()[sid]['name']} validation"
    store().save_thread(t["thread_id"], state, title=title, scorecard_id=sid or "")
    return answer


@app.post(f"{PREFIX}/threads")
def create_thread(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    u = _guard_write(request)
    t = store().create_thread(owner=u.get("username", ""), team=u.get("team", ""))
    q = str(body.get("question") or "").strip()
    if not q and body.get("scorecard_id") in engine.scorecards_by_id():
        q = f"Validate the {engine.scorecards_by_id()[body['scorecard_id']]['name']}"
    if q:
        _turn(t, q[:2000])
        t = store().thread(t["thread_id"])
    return _thread_view(t)


@app.get(f"{PREFIX}/threads")
def threads(request: Request) -> dict[str, Any]:
    u = access.user(request)
    return {"threads": [_thread_row(t) for t in store().threads() if access.can_see(u, t["owner"], t["team"], t["thread_id"], request)]}


@app.get(f"{PREFIX}/threads/{{thread_id}}")
def thread(thread_id: str, request: Request) -> dict[str, Any]:
    return _thread_view(_visible_thread(request, thread_id))


@app.post(f"{PREFIX}/threads/{{thread_id}}/messages")
def message(thread_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _guard_write(request)
    t = _visible_thread(request, thread_id, write=True)
    text = str(body.get("text") or "").strip()
    if not text:
        raise refuse(422, "Say something to continue.")
    try:
        _turn(t, text[:2000])
    except ValueError as e:
        raise refuse(422, str(e)) from e
    return _thread_view(store().thread(thread_id))


@app.post(f"{PREFIX}/threads/{{thread_id}}/title")
def title(thread_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _guard_write(request)
    _visible_thread(request, thread_id, write=True)
    name = str(body.get("title") or "").strip()[:200]
    if not name:
        raise refuse(422, "A title is needed.")
    store().rename(thread_id, name)
    return {"title": name}


@app.delete(f"{PREFIX}/threads/{{thread_id}}")
def delete_thread(thread_id: str, request: Request) -> dict[str, Any]:
    _guard_write(request)
    _visible_thread(request, thread_id, write=True)
    if any(v["seed"] for v in (store().validation(x["validation_id"], full=False) for x in store().validation_for_thread(thread_id)) if v):
        raise refuse(409, "The seeded validations are kept.")
    store().delete_thread(thread_id)
    return {"deleted": thread_id}


# ---------------------------------------------------------------- R16 M8: monitoring against the MMSG criteria

CHECKER_TEAMS = ("risk", "validation", "admin")


def _who(u: dict[str, Any]) -> str:
    return u.get("name") or u.get("username") or "Signed-out user"


@app.get(f"{PREFIX}/monitor/front")
def monitor_front() -> dict[str, Any]:
    on = mon_front.today()
    hl = mon_front.health(on, store())
    br = mon_front.breaches(on, store(), hl)
    reg = mon_front.register(on, store())
    return {"as_of": on.isoformat(), "plain_words": mon_front.plain_words(hl, br), "health": hl, "breaches": br,
            "counts": {"scorecards": len(hl), "red": sum(b["status"] == "red" for b in br), "amber": sum(b["status"] == "amber" for b in br),
                       "open_findings": sum(r["status"] != "closed" for r in reg), "overdue_findings": sum(r["overdue"] for r in reg)},
            "schedule": list(mon_front.schedule().values()), "criteria": mon_front.compute.POLICY["criteria"],
            "sources": ["scorecard_monitoring.sc_monitor_metric", "scorecard_monitoring.sc_model_inventory", "scorecard_monitoring.sc_findings_register", "scorecard_monitoring.sc_monitor_schedule"]}


@app.get(f"{PREFIX}/monitor/scorecards/{{sid}}")
def monitor_scorecard(sid: str, request: Request) -> dict[str, Any]:
    try:
        d = mon_front.deep_dive(sid, mon_front.today(), store())
    except KeyError as e:
        raise refuse(404, "That scorecard is not monitored.") from e
    u = access.user(request)
    own = {v["validation_id"]: v for v in store().validations()}
    d["validations"] = [x for x in d["validations"] if x["validation_id"] in own and (
        _checker(u) or access.can_see(u, own[x["validation_id"]]["owner"], own[x["validation_id"]]["team"], x["validation_id"], request))]
    return d


@app.get(f"{PREFIX}/monitor/register")
def monitor_register(scorecard_id: str = Query("")) -> dict[str, Any]:
    rows = mon_front.register(mon_front.today(), store())
    if scorecard_id:
        rows = [r for r in rows if r["scorecard_id"] == scorecard_id]
    return {"findings": rows, "as_of": mon_front.today().isoformat()}


@app.post(f"{PREFIX}/monitor/register/{{finding_id}}")
def monitor_register_update(finding_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _guard_write(request)
    cur = next((r for r in mon_front.register(mon_front.today(), store()) if r["finding_id"] == finding_id), None)
    if not cur:
        raise refuse(404, "That finding is not in the register.")
    rec = {k: cur[k] for k in ("finding_id", "scorecard_id", "source_ref", "criterion", "severity", "title", "text", "remediation", "owner",
                                "raised_on", "due_on", "status") if k in cur}
    if "status" in body:
        if body["status"] not in ("open", "in_progress", "closed"):
            raise refuse(422, "status must be open, in_progress or closed.")
        rec["status"] = body["status"]
    if body.get("owner"):
        rec["owner"] = str(body["owner"])[:120]
    if body.get("due_on"):
        try:
            rec["due_on"] = mon_front.dt.date.fromisoformat(str(body["due_on"])[:10]).isoformat()
        except ValueError as e:
            raise refuse(422, "due_on must be a date (YYYY-MM-DD).") from e
    hist = list(cur.get("history") or [])
    hist.append({"by": _who(u), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "change": {k: body[k] for k in ("status", "owner", "due_on") if k in body},
                 "note": str(body.get("note") or "")[:500]})
    rec["history"] = hist
    rec["origin"] = cur.get("origin") if cur.get("origin") != "register" else "register"
    store().put_finding(rec)
    return next(r for r in mon_front.register(mon_front.today(), store()) if r["finding_id"] == finding_id)


@app.get(f"{PREFIX}/monitor/schedule")
def monitor_schedule() -> dict[str, Any]:
    return {"schedule": list(mon_front.schedule().values())}


@app.get(f"{PREFIX}/monitor/brief")
def monitor_brief() -> dict[str, Any]:
    return {"items": mon_front.brief_items(mon_front.today(), store())}


def _conclusion_view(v: dict[str, Any]) -> dict[str, Any]:
    full = store().validation(v["validation_id"])
    dive = mon_front.deep_dive(v["scorecard_id"], mon_front.today(), store())
    prop = mon_report.proposed_conclusion(full["result"], dive)
    rec = store().conclusion(v["validation_id"]) or {"state": "not_proposed"}
    return {"validation_id": v["validation_id"], "proposed": prop, "record": rec, "checker_teams": list(CHECKER_TEAMS),
            "conclusions": mon_report.CONCLUSIONS}


@app.get(f"{PREFIX}/validations/{{validation_id}}/conclusion")
def conclusion_get(validation_id: str, request: Request) -> dict[str, Any]:
    return _conclusion_view(_visible_validation(request, validation_id, full=False))


@app.post(f"{PREFIX}/validations/{{validation_id}}/conclusion")
def conclusion_propose(validation_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _guard_write(request)
    v = _visible_validation(request, validation_id, full=False)
    concl = str(body.get("conclusion") or "")
    if concl not in mon_report.CONCLUSIONS:
        raise refuse(422, "conclusion must be fit, conditions or not_fit.")
    cur = store().conclusion(validation_id) or {}
    if cur.get("state") == "approved":
        raise refuse(409, "This conclusion is already approved by a checker.")
    plan = v["plan"]
    rec = {"state": "proposed", "scorecard_id": v["scorecard_id"], "conclusion": concl, "note": str(body.get("note") or "")[:2000],
           "maker": _who(u), "maker_username": u.get("username", ""), "maker_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "full": sum(bool(x) for x in (plan.get("tests") or {}).values()) >= 4, "history": list(cur.get("history") or [])}
    rec["history"].append({"step": "proposed", "by": rec["maker"], "at": rec["maker_at"], "conclusion": concl})
    store().put_conclusion(validation_id, rec)
    return _conclusion_view(v)


@app.post(f"{PREFIX}/validations/{{validation_id}}/conclusion/decide")
def conclusion_decide(validation_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _guard_write(request)
    v = _visible_validation(request, validation_id, full=False)
    cur = store().conclusion(validation_id)
    if not cur or cur.get("state") != "proposed":
        raise refuse(409, "There is no proposed conclusion waiting for a checker.")
    if (u.get("username") or "") == (cur.get("maker_username") or "") :
        raise refuse(403, "Four eyes: the checker must be someone other than the maker.")
    if not (u.get("is_admin") or u.get("team") in CHECKER_TEAMS):
        raise refuse(403, "Only Risk, Model Validation or the Administrator can check a validation conclusion.")
    approve = bool(body.get("approve"))
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rec = {**cur, "state": "approved" if approve else "returned", "checker": _who(u), "checker_username": u.get("username", ""), "checker_at": now,
           "checker_note": str(body.get("note") or "")[:2000]}
    rec["history"] = list(cur.get("history") or []) + [{"step": rec["state"], "by": rec["checker"], "at": now}]
    store().put_conclusion(validation_id, rec)
    if approve:
        # The approved conclusion is also the validation's review (the earlier single-step record stays readable everywhere).
        store().set_review(validation_id, {"status": "reviewed", "conclusion": rec["conclusion"], "note": rec["note"], "reviewer": f"{rec['maker']} (maker), {rec['checker']} (checker)",
                                           "at": now})
    return _conclusion_view(v)


@app.get(f"{PREFIX}/validations/{{validation_id}}/mmsg.docx")
def mmsg_report(validation_id: str, request: Request) -> Response:
    v = _visible_validation(request, validation_id)
    prior = None
    for o in store().validations():
        if o["scorecard_id"] == v["scorecard_id"] and o["created_at"] < v["created_at"]:
            prior = store().validation(o["validation_id"])
            break
    body = mon_report.build(v, generated_by=generated_by(request), conclusion=store().conclusion(validation_id), prior=prior,
                            on=mon_front.today(), store=store())
    return Response(body, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{validation_id}-mmsg.docx"'})
