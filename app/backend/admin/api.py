"""The Admin service (PLAN_R5 Session A), port 8510: a console that runs the bank's CreditProbe.

    /api/v1/access/me                     the caller's effective policy (every user; the v5 shell's route guard)
    /api/v1/admin/...                     Admin only (the access policy's "admin" module)

Every configuration change is maker-checker (draft -> submit -> approve by another Admin or CRO -> live), with
versions, in the audit log. The assistant is a conversational domain on backend/convo, mounted at
/api/v1/admin/convo (the shared thread contract).
"""
from __future__ import annotations

import io
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.access import dims, install, policy as pol, studio as studio_cfg
from backend.admin import logic, notify, seed, store
from backend.admin.assistant import DOMAIN
from backend.convo.service import ConvoService
from backend.identity_v5.client import cookie_name as _cookie_name

UI_ORIGINS = [o.strip() for o in (os.environ.get("ADMIN_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]

app = FastAPI(title="CreditProbe Admin", version="1.0")
install(app, "admin")
app.add_middleware(CORSMiddleware, allow_origins=UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["*"])

CONVO = ConvoService("admin", [DOMAIN])
app.include_router(CONVO.router, prefix="/api/v1/admin/convo")
app.include_router(__import__("backend.intel.governance.api", fromlist=["router"]).router)  # R13 IE: governance and team


@app.on_event("startup")
def _start() -> None:
    store.ensure()
    CONVO.start()
    notify.deliver()   # open workflow items and changes waiting for approval reach My workspace and Mail


# ------------------------------------------------------------------ who is calling
_ME: dict[str, tuple[float, dict[str, Any] | None]] = {}


def who(request: Request) -> dict[str, Any]:
    """{me, user (effective), viewing_as, is_admin} from the Core service; a test fallback with no cookie."""
    token = request.cookies.get(_cookie_name())
    if not token:
        fb = os.environ.get("CP_IDENTITY_FALLBACK_USER", "").strip()
        if fb:
            u = pol.core_user(fb) or {"username": fb, "name": fb, "is_admin": fb == "anne"}
            return {"me": u, "user": u, "viewing_as": None, "is_admin": bool(u.get("is_admin"))}
        raise HTTPException(401, "not signed in")
    hit = _ME.get(token)
    if hit and time.monotonic() - hit[0] < 1:
        info = hit[1]
    else:
        info = None
        base = (os.environ.get("CORE_API_ORIGIN") or "http://127.0.0.1:8505").rstrip("/")
        for attempt in range(2):   # the Core service can be slow under load; a 401 must mean "not signed in"
            try:
                req = urllib.request.Request(base + "/api/v1/auth/me", headers={"Cookie": f"{_cookie_name()}={token}"})
                with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 - fixed loopback origin
                    info = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    break
            except (urllib.error.URLError, OSError, ValueError):
                continue
        if info:
            _ME[token] = (time.monotonic(), info)
    if not info:
        raise HTTPException(401, "not signed in")
    return {"me": info["user"], "user": info["effective_user"], "viewing_as": info.get("viewing_as"),
            "is_admin": bool(info.get("is_admin"))}


def actor(request: Request) -> tuple[str, bool]:
    """The signed-in person who acts (never the viewed-as user); writes are refused while viewing as someone."""
    w = who(request)
    if w["viewing_as"]:
        raise HTTPException(403, f"Read only while viewing as {w['viewing_as'].get('name')}. Return to your own view to act.")
    return w["me"]["username"], bool(w["is_admin"])


def run(fn, *args, **kwargs):
    try:
        with store.db() as con:
            out = fn(con, *args, **kwargs)
        pol.clear_cache()
        studio_cfg.clear_cache()
        if fn in (store.submit, store.approve, store.reject, store.withdraw):
            notify.deliver()
        return out
    except store.NotFound as e:
        raise HTTPException(404, str(e)) from e
    except store.NotPermitted as e:
        raise HTTPException(403, str(e)) from e
    except store.Invalid as e:
        raise HTTPException(422, str(e)) from e


# ------------------------------------------------------------------ health, my access
@app.get("/api/v1/admin/health")
def health() -> dict[str, Any]:
    with store.db() as con:
        counts = {k: len(store.live_list(con, k)) for k in store.KINDS}
        pending = len(store.changes(con, status="submitted"))
    return {"status": "ok", "service": "admin", "counts": counts, "pending_changes": pending,
            "assistant": {"planner": "model" if DOMAIN and __import__("backend.convo.provider", fromlist=["x"]).default() else "deterministic"}}


@app.get("/api/v1/access/me")
def access_me(request: Request) -> dict[str, Any]:
    """The caller's effective policy (the effective user when the Administrator views as someone)."""
    from backend.access import middleware
    u = middleware._user(request)   # the session's effective user, read from the Core store (no cache to go stale)  # noqa: SLF001
    if not u:
        return {"authenticated": False, "policy": pol.UNRESTRICTED.describe(), "modules": {k: True for k in pol.modules()}}
    p = pol.for_user(u)
    return {"authenticated": True, "username": u["username"],
            "policy": p.describe(), "modules": {k: p.allows_module(k) for k in pol.modules()},
            "actions": {k: p.allows_action(k) for k in pol.ACTIONS},
            "cockpit_books": [b for b in ("corporate", "retail") if p.allows_book(b)]}


# ------------------------------------------------------------------ overview
@app.get("/api/v1/admin/overview")
def overview(request: Request) -> dict[str, Any]:
    with store.db() as con:
        rs = logic.runs(con)
        out = {"policies": len(store.live_list(con, "policy")), "workflows": len(store.live_list(con, "workflow")),
               "users": len(store.live_list(con, "user")), "pending": store.changes(con, status="submitted"),
               "drafts": store.changes(con, status="draft"), "items": store.items(con),
               "ai_runs": len(rs), "refused": sum(1 for r in rs if r.get("outcome") == "refused"),
               "killed": [s["id"] for s in store.live_list(con, "studio") if s["body"].get("kill_switch")]}
    w = who(request)
    out["me"] = {"username": w["me"]["username"], "can_approve": run(store.can_approve, w["me"]["username"], w["is_admin"])}
    return out


# ------------------------------------------------------------------ objects and changes (maker-checker)
@app.get("/api/v1/admin/objects/{kind}")
def objects(kind: str) -> dict[str, Any]:
    if kind not in store.KINDS:
        raise HTTPException(404, f"'{kind}' is not configured here.")
    with store.db() as con:
        return {"kind": kind, "label": store.KINDS[kind], "objects": store.live_list(con, kind),
                "changes": store.changes(con, kind=kind, status="draft,submitted")}


@app.get("/api/v1/admin/objects/{kind}/{oid}")
def object_detail(kind: str, oid: str) -> dict[str, Any]:
    with store.db() as con:
        try:
            live = store.get_live(con, kind, oid)
        except store.NotFound as e:
            raise HTTPException(404, str(e)) from e
        return {"object": live, "versions": store.versions(con, kind, oid), "changes": store.changes(con, kind=kind, object_id=oid)}


@app.get("/api/v1/admin/changes")
def list_changes(kind: str = "", status: str = "") -> dict[str, Any]:
    with store.db() as con:
        return {"changes": store.changes(con, kind=kind, status=status)}


@app.post("/api/v1/admin/changes", status_code=201)
def new_change(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    a, _ = actor(request)
    ch = run(store.draft, a, str(payload.get("kind") or ""), str(payload.get("op") or "create"), payload.get("body") or {},
             str(payload.get("title") or ""), str(payload.get("object_id") or ""), str(payload.get("source") or "console"))
    if payload.get("submit"):
        ch = run(store.submit, a, ch["change_id"])
    return ch


@app.put("/api/v1/admin/changes/{cid}")
def edit_change(cid: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    a, _ = actor(request)
    return run(store.update_draft, a, cid, payload.get("body") or {}, str(payload.get("title") or ""))


@app.post("/api/v1/admin/changes/{cid}/submit")
def submit_change(cid: str, request: Request) -> dict[str, Any]:
    a, _ = actor(request)
    return run(store.submit, a, cid)


@app.post("/api/v1/admin/changes/{cid}/approve")
def approve_change(cid: str, request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    a, adm = actor(request)
    return run(store.approve, a, cid, adm, str(payload.get("comment") or ""))


@app.post("/api/v1/admin/changes/{cid}/reject")
def reject_change(cid: str, request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    a, adm = actor(request)
    return run(store.reject, a, cid, str(payload.get("comment") or ""), adm)


@app.post("/api/v1/admin/changes/{cid}/withdraw")
def withdraw_change(cid: str, request: Request) -> dict[str, Any]:
    a, _ = actor(request)
    return run(store.withdraw, a, cid)


# ------------------------------------------------------------------ A1 data access
@app.get("/api/v1/admin/access/options")
def access_options() -> dict[str, Any]:
    o = dims.options()
    rm = dims.corporate()[["rm_id", "rm_name", "branch_id", "branch_name"]].drop_duplicates("rm_id").sort_values("rm_id")
    br = {b: dims.frame(b)[["branch_id", "branch_name"]].dropna().drop_duplicates("branch_id").sort_values("branch_id")
          for b in ("corporate", "retail")}
    return {"fields": o, "rms": rm.to_dict("records"),
            "branches": {b: f.to_dict("records") for b, f in br.items()},
            "modules": [{"key": k, "label": v} for k, v in pol.modules().items()],
            "actions": [{"key": k, "label": v} for k, v in pol.ACTIONS.items()],
            "roles": [{"id": r["id"], "name": r["name"]} for r in seed.ROLES],
            "teams": [{"id": t["id"], "name": t["name"]} for t in seed.TEAMS]}


@app.get("/api/v1/admin/access/preview")
def access_preview(username: str = Query(...)) -> dict[str, Any]:
    return logic.preview(username)


@app.post("/api/v1/admin/access/preview-draft")
def access_preview_draft(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return logic.preview_draft(payload.get("body") or {}, str(payload.get("username") or "sara.aldosari"))


# ------------------------------------------------------------------ A1 workflows
@app.get("/api/v1/admin/workflows/samples")
def wf_samples() -> dict[str, Any]:
    return {"samples": logic.samples(), "doa": logic._doa()}  # noqa: SLF001


@app.post("/api/v1/admin/workflows/simulate")
def wf_simulate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    wf = payload.get("workflow")
    if not wf and payload.get("workflow_id"):
        with store.db() as con:
            wf = store.get_live(con, "workflow", str(payload["workflow_id"]))["body"]
    if not wf:
        raise HTTPException(422, "Name a workflow to simulate.")
    obj = payload.get("object") or next(iter(logic.samples().get(wf.get("object_type"), [])), {})
    return logic.simulate(wf, obj, payload.get("start"))


@app.get("/api/v1/admin/workflows/items")
def wf_items() -> dict[str, Any]:
    with store.db() as con:
        return {"items": store.items(con)}


# ------------------------------------------------------------------ A2 users and teams
@app.get("/api/v1/admin/users")
def users() -> dict[str, Any]:
    with store.db() as con:
        profiles = store.live_list(con, "user")
        changes = store.changes(con, kind="user", status="draft,submitted")
    out = []
    for x in profiles:
        b = x["body"]
        p = pol.build(b["username"], pol.core_user(b["username"]) or {}, b)
        out.append({**b, "version": x["version"], "policies": [{"id": i, "name": n} for i, n in p.policies],
                    "in_core": pol.core_user(b["username"]) is not None})
    return {"users": out, "roles": seed.ROLES, "teams": seed.TEAMS, "changes": changes}


@app.post("/api/v1/admin/users/{username}/reset-password")
def reset_password(username: str, request: Request) -> dict[str, Any]:
    """A local password reset: a new password is written to the local users file (never shown here), sessions end."""
    a, adm = actor(request)
    if not adm:
        raise HTTPException(403, "Only the Administrator resets passwords.")
    from backend.identity_v5 import store as ids
    try:
        with ids.db() as con:
            u = ids.get_user(con, username)
            pw = ids._new_password()  # noqa: SLF001
            con.execute("UPDATE users SET password_hash=? WHERE username=?", (ids.hash_password(pw), username))
            con.execute("DELETE FROM sessions WHERE username=?", (username,))
            ids.audit(con, a, a, "password_reset", username)
            path = ids.paths.users_local_path()
            try:
                text = path.read_text(encoding="utf-8") if path.exists() else ""
                lines = [ln for ln in text.splitlines() if not ln.startswith(f"| `{username}` |")]
                lines.append(f"| `{username}` | {u['name']} | `{pw}` |")
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError:
                pass
    except ids.NotFound as e:
        raise HTTPException(404, str(e)) from e
    run(store.audit, a, "password_reset", "user", username, {})
    return {"ok": True, "message": f"A new password for {u['name']} is in the local users file. Their sessions have ended."}


# ------------------------------------------------------------------ A3 Agent Operations
def _filter_runs(rs, module="", outcome="", user="", q=""):
    out = []
    for r in rs:
        if module and r.get("module") != module:
            continue
        if outcome == "problems" and r.get("outcome") == "completed":
            continue
        if outcome and outcome != "problems" and not str(r.get("outcome", "")).startswith(outcome):
            continue
        if user and r.get("user") != user:
            continue
        if q and q.lower() not in str(r.get("question", "")).lower():
            continue
        out.append(r)
    return out


@app.get("/api/v1/admin/agent-ops/runs")
def ops_runs(module: str = "", outcome: str = "", user: str = "", q: str = "", limit: int = 200) -> dict[str, Any]:
    with store.db() as con:
        rs = logic.runs(con)
    f = _filter_runs(rs, module, outcome, user, q)
    return {"runs": f[:max(1, min(limit, 1000))], "total": len(f), "all": len(rs),
            "modules": sorted({r.get("module", "") for r in rs}), "users": sorted({r.get("user", "") for r in rs if r.get("user")})}


@app.get("/api/v1/admin/agent-ops/runs/{run_id}")
def ops_run(run_id: str) -> dict[str, Any]:
    with store.db() as con:
        r = next((x for x in logic.runs(con) if x.get("run_id") == run_id), None)
    if r is None:
        raise HTTPException(404, f"No AI run '{run_id}'.")
    return r


@app.get("/api/v1/admin/agent-ops/daily")
def ops_daily(module: str = "") -> dict[str, Any]:
    with store.db() as con:
        rs = logic.runs(con)
    return logic.daily(_filter_runs(rs, module))


@app.get("/api/v1/admin/agent-ops/evals")
def ops_evals() -> dict[str, Any]:
    with store.db() as con:
        return {"suites": {m: qs for m, qs in seed.EVALS.items()}, "runs": store.evals(con)}


@app.post("/api/v1/admin/agent-ops/evals/{module}/run")
def ops_eval_run(module: str, request: Request) -> dict[str, Any]:
    """Run a module's evaluation suite. The Admin suite runs in process on the assistant (planner or model); the
    other modules' suites check each scripted question against the module's live configuration (allowed tools,
    guardrails) through the test bench."""
    a, _ = actor(request)
    suite = seed.EVALS.get(module)
    if not suite:
        raise HTTPException(404, f"No evaluation suite for '{module}'.")
    results = []
    for case in suite:
        t0 = time.monotonic()
        if module == "admin":
            from backend.convo.agent import Agent

            class _Q:
                open_stage = ""

                def emit(self, *x, **k):
                    pass

                def stage(self, name, message=""):
                    self.open_stage = name
            ag = Agent(DOMAIN, thread={"thread_id": "eval", "domain": "admin"}, scope={}, state={}, question=case["q"],
                       emitter=_Q(), user={"username": a})
            out = ag.run()
            tools = [t.get("tool") for t in ag.trace if t.get("tool")]
            answered = any(b.get("type") == "answer" and b.get("markdown") for b in out.blocks)
        else:
            with store.db() as con:
                cfg = store.find_live(con, "studio", module)
            b = logic.bench((cfg or {}).get("body", {}), case["q"])
            tools = b["tools_planned"]
            answered = not b["refused"]
        ok = answered and all(t in tools for t in case["expect_tools"])
        results.append({"question": case["q"], "expect_tools": case["expect_tools"], "tools": tools, "pass": ok,
                        "ms": round((time.monotonic() - t0) * 1000)})
    return run(store.save_eval, module, a, results)


@app.post("/api/v1/admin/agent-ops/kill-switch")
def ops_kill(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    a, _ = actor(request)
    return run(store.set_kill_switch, a, str(payload.get("module") or ""), bool(payload.get("on")), str(payload.get("reason") or ""))


# ------------------------------------------------------------------ A4 AI Studio
@app.get("/api/v1/admin/studio")
def studio_list() -> dict[str, Any]:
    with store.db() as con:
        return {"configs": store.live_list(con, "studio"), "changes": store.changes(con, kind="studio", status="draft,submitted")}


@app.post("/api/v1/admin/studio/{module}/test")
def studio_test(module: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    q = str(payload.get("question") or "").strip()
    if not q:
        raise HTTPException(422, "Ask a question to test.")
    with store.db() as con:
        live = store.get_live(con, "studio", module)["body"]
    draft = payload.get("draft")
    return {"question": q, "live": logic.bench(live, q), "draft": logic.bench(draft, q) if draft else None,
            "diff": sorted(k for k in set(live) | set(draft or {}) if draft and live.get(k) != draft.get(k))}


# ------------------------------------------------------------------ A5 settings
@app.get("/api/v1/admin/settings")
def settings() -> dict[str, Any]:
    with store.db() as con:
        return {"settings": store.live_list(con, "setting"), "changes": store.changes(con, kind="setting", status="draft,submitted"),
                "parameters": logic.parameter_register(), "feeds": logic.feeds()}


# ------------------------------------------------------------------ A6 audit log
@app.get("/api/v1/admin/audit")
def audit(actor_: str = Query("", alias="actor"), category: str = "", q: str = "", since: str = "",
          limit: int = 300) -> dict[str, Any]:
    with store.db() as con:
        ev = logic.audit_events(con, logic.runs(con))
    cats = sorted({e["category"] for e in ev})
    actors = sorted({e["actor"] for e in ev if e["actor"]})
    if actor_:
        ev = [e for e in ev if e["actor"] == actor_]
    if category:
        ev = [e for e in ev if e["category"] == category]
    if since:
        ev = [e for e in ev if e["at"] >= since]
    if q:
        ev = [e for e in ev if q.lower() in (e["label"] + " " + e["object"]).lower()]
    return {"events": ev[:max(1, min(limit, 2000))], "total": len(ev), "categories": cats, "actors": actors}


@app.get("/api/v1/admin/audit/export.xlsx")
def audit_export(request: Request, actor_: str = Query("", alias="actor"), category: str = "", q: str = "") -> Response:
    from backend import house_style
    from backend.house_style import xlsx as hx

    data = audit(actor_, category, q, "", 2000)["events"]
    rows = [{"When (UTC)": e["at"], "Who": e["actor"], "What": e["label"], "Category": e["category"], "Object": e["object"],
             "Source": e["source"]} for e in data]
    content = _xlsx(hx, "Audit log", rows, house_style.generated_by(request))
    try:
        a, _ = actor(request)
        run(store.audit, a, "export", "audit", "audit log", {"rows": len(rows)})
    except HTTPException:
        pass
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="creditprobe_audit_log.xlsx"'})


def _xlsx(hx, title: str, rows: list[dict[str, Any]], by: str) -> bytes:
    from backend.house_style import Meta
    meta = Meta(title, book="both", period="All periods", subject="Admin", generated_by=by)
    wb = hx.workbook(meta)
    cols = [hx.Col(k, k) for k in (rows[0].keys() if rows else ["When (UTC)", "Who", "What", "Category", "Object", "Source"])]
    hx.table_sheet(wb, title, meta, cols, rows)
    hx.about_sheet(wb, meta, [("Contents", "Sign-ins, exports, approvals, configuration changes and AI runs")])
    return hx.to_bytes(wb)
