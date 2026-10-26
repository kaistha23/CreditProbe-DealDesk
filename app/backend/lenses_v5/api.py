"""The Lenses API: its own app on its own port (8509), prefix /api/v1/lenses (PLAN_R5 Session L).

    GET  /health
    GET  /meta?book=                         catalogue (metrics, dimensions, distributions), periods, templates, examples
    GET  /lenses?book=                       {mine, shared, templates} as cards with thumbnails
    POST /plan                               {request, book?, persona?} -> R16 M5 metric plan for a persona request, or {persona: null}
    POST /lenses                             {request, book?} or {template} -> {lens, thread_id, run}: asking opens a lens;
                                             {request, book?, plan: {persona, include: [ids]}} builds from an approved plan
    GET  /lenses/{id}                        the lens: meta, spec, versions, head, can_edit
    GET  /lenses/{id}/render?period=         KPI row, tiles (Plotly figure, table, trace), commentary
    POST /lenses/{id}/edit                   {op: delete|move|chart|metric|dim|rename|add|kpis|scope|period|custom_ratio, ...}
    POST /lenses/{id}/command                {text}: an edit in words, applied without the assistant (the composer uses the thread)
    POST /lenses/{id}/undo | /redo           move through the versions
    POST /lenses/{id}/restore                {version}
    POST /lenses/{id}/save                   {name, description, tags}; a template is saved as the caller's own copy
    POST /lenses/{id}/duplicate
    POST /lenses/{id}/share                  {users: [], teams: [], note}: through Mail (type "lens")
    POST /lenses/{id}/playbook               {report_id | new_report}: a Playbook section with the lens figures
    GET  /playbook/reports                   the caller's editable reports
    GET  /playbook/sources?q=  /playbook/section?id=   Playbook pulls a lens by id (live figures)
    GET  /lenses/{id}/export.xlsx | export.pdf          house style
    POST /lenses/{id}/schedule               {cadence: daily|weekly|monthly, recipients: []} a refresh note through Mail
    POST /lenses/{id}/tiles/{tile_id}/handoff {target: cockpit|whatif}
    POST /custom/validate                    {book, num, den, filters, label}: the engine runs the ratio
    DELETE /lenses/{id}
    /convo/...                               the lens assistant (CONVO_API.md): threads, runs, SSE events

Reads the books, EWS, Scorecard and Deal Desk domains read-only (engine.py). Writes only var/lenses_v5/lenses.sqlite
and var/convo/lenses.sqlite.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.convo import provider
from backend.convo.service import ConvoService
from backend.house_style import generated_by
from backend.lenses_v5 import access, convo_domain, crm_intel, exports, paths, personas, planner, seed, outbound
from backend.lenses_v5.catalogue import public as catalogue_public
from backend.lenses_v5.engine import ENGINE, LensError
from backend.lenses_v5.render import render
from backend.lenses_v5.store import Store

PREFIX = "/api/v1/lenses"
VERSION = "lenses-v5-1.0.0"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(title="CreditProbe v5 Lenses", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["*"], expose_headers=["Content-Disposition"])

STORE: Store | None = None
_LOCK = threading.Lock()


def store() -> Store:
    global STORE
    with _LOCK:
        if STORE is None:
            STORE = Store()
            seed.ensure(STORE)
        return STORE


convo_domain.STORE = store
SVC = ConvoService("lenses", [convo_domain.DOMAIN], store_path=paths.convo_store_path())
app.include_router(SVC.router, prefix=f"{PREFIX}/convo")


@app.on_event("startup")
def _startup() -> None:
    ENGINE.load()
    store()
    SVC.start()
    threading.Thread(target=crm_intel.warm, name="crm-warm", daemon=True).start()


def refuse(status: int, message: str) -> HTTPException:
    return HTTPException(status, message)


def _visible(request: Request, lens_id: str) -> dict[str, Any]:
    lens = store().lens(lens_id)
    if lens is None or not access.can_see(access.user(request), lens, request, store()):
        raise refuse(404, "That lens does not exist.")
    return lens


def _writable(request: Request, lens_id: str) -> dict[str, Any]:
    name = access.viewing_as(request)
    if name:
        raise refuse(403, f"Read only while viewing as {name}.")
    lens = _visible(request, lens_id)
    if lens["kind"] in ("template", "featured"):
        raise refuse(409, "Templates are read only: save a copy to change it.")
    if not access.can_write(access.user(request), lens["owner"]):
        raise refuse(403, "Only the owner can change this lens. Duplicate it to make your own.")
    return lens


def _guard(fn):
    try:
        return fn()
    except LensError as e:
        raise refuse(422, str(e)) from e


def _card(lens: dict[str, Any], me: str = "") -> dict[str, Any]:
    spec = store().spec(lens["lens_id"])
    return {"lens_id": lens["lens_id"], "name": lens["name"], "description": lens["description"], "tags": [t for t in lens["tags"] if not t.startswith("lenses-seed")], "book": lens["book"],
            "kind": lens["kind"], "owner": lens["owner"], "saved": lens["saved"], "updated_at": lens["updated_at"], "version": lens["head"],
            "scope_label": spec.get("scope_label", ""), "tiles": len(spec.get("tiles") or []), "thumb": lens["thumb"] or seed.thumb(spec),
            "schedule": lens["schedule"], "mine": bool(me) and lens["owner"] == me, "template_key": lens.get("template_key", "")}


@app.get(f"{PREFIX}/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": VERSION, "engine_loaded_s": round(ENGINE.loaded_at, 2),
            "periods": {b: ENGINE.as_of(b) for b in ("corporate", "retail")}, "lenses": len(store().lenses()),
            "assistant": provider.describe()}


@app.get(f"{PREFIX}/meta")
def meta(book: str = Query("corporate")) -> dict[str, Any]:
    b = book if book in ("corporate", "retail") else "corporate"
    return {"book": b, **catalogue_public(b), "periods": ENGINE.periods(b), "as_of": ENGINE.as_of(b),
            "values": {d: ENGINE.values(b, d) for d in planner.SCOPE_DIMS[b]},
            "examples": ["Construction sector dashboard", "Makkah retail cards", "Stage 2 migration by RM", "Real Estate concentration",
                         "Retail personal finance by region", "Early Warning critical names"],
            "assistant": provider.describe()}


@app.get(f"{PREFIX}/lenses")
def lenses(request: Request, book: str = Query("")) -> dict[str, Any]:
    u = access.user(request)
    me = u.get("username", "")
    shared_ids = access.shared_ids(request, store(), u)
    mine, shared, templates, featured = [], [], [], []
    for lens in store().lenses():
        if book in ("corporate", "retail") and lens["book"] != book:
            continue
        if lens["kind"] in ("template", "featured") and lens.get("template_key") in seed.FEATURED_KEYS:
            featured.append(_card(lens, me))
        if lens["kind"] == "featured":
            continue
        if lens["kind"] == "template":
            templates.append(_card(lens, me))
        elif me and lens["owner"] == me:
            mine.append(_card(lens, me))
        elif lens["lens_id"] in shared_ids or (lens["saved"] and access.can_see(u, lens, None, None) and lens["owner"] != me and lens["owner"]
                                               and (u.get("is_admin") or (lens.get("team") and lens.get("team") == u.get("team")))):
            shared.append(_card(lens, me))
        elif not me and lens["saved"]:
            mine.append(_card(lens, me))
    order = {k: i for i, k in enumerate(seed.TEMPLATE_KEYS)}
    templates.sort(key=lambda c: order.get(c["template_key"], 99))
    mine.sort(key=lambda c: (not c["saved"], -c["updated_at"]))
    forder = {k: i for i, k in enumerate(seed.FEATURED_KEYS)}
    featured.sort(key=lambda c: forder.get(c["template_key"], 99))
    return {"featured": featured, "mine": mine[:60], "shared": shared[:60], "templates": templates}


@app.post(f"{PREFIX}/lenses", status_code=201)
def create(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    name = access.viewing_as(request)
    if name:
        raise refuse(403, f"Read only while viewing as {name}.")
    u = access.user(request)
    text = str(body.get("request") or "").strip()[:500]
    tpl = str(body.get("template") or "")
    if tpl:
        t = store().lens(tpl) or store().template(tpl)
        if t is None or t["kind"] not in ("template", "featured"):
            raise refuse(404, "That template does not exist.")
        spec = store().spec(t["lens_id"])
        text = text or f"Open the {t['name']} template"
    elif not text:
        raise refuse(422, "Describe the dashboard you want.")
    elif isinstance(body.get("plan"), dict):
        # R16 M5: "Build this dashboard" on an approved persona plan (the plan is re-run here, never taken from the client)
        pl = body["plan"]
        inc = pl.get("include")
        p = _guard(lambda: personas.plan(text, str(body.get("book") or ""), persona=str(pl.get("persona") or "")))
        if p is None:
            raise refuse(422, "That plan names no persona I know.")
        spec = _guard(lambda: personas.spec_from_plan(p, [str(x) for x in inc] if isinstance(inc, list) else None))
    else:
        spec = _guard(lambda: planner.build_spec(text, str(body.get("book") or "")))
    lens = store().create(owner=u.get("username", ""), team=u.get("team", ""), spec=spec, name=spec["title"],
                          description=f"Built from: {text}"[:300], tags=[spec["book"]])
    opened = SVC.open_thread(domain="lenses", scope={"lens_id": lens["lens_id"], "book": spec["book"]}, owner=u.get("username", ""),
                             team=u.get("team", ""), title=spec["title"][:80], question=text, origin="lenses-home")
    store().update(lens["lens_id"], thread_id=opened["thread"]["thread_id"], thumb=seed.thumb(spec))
    return {"lens": _card(store().lens(lens["lens_id"]), u.get("username", "")), "thread_id": opened["thread"]["thread_id"],
            "run": opened["run"]}


@app.post(f"{PREFIX}/plan")
def persona_plan(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """R16 M5: the metric plan for a request that names a persona (CRO, analyst, CCO, branch or RM head): per measure its
    definition, formula, SQL and source relation, or "not available" with why. {persona: null} when none is named.
    With `lens_id` (the lens assistant) the plan keeps that lens's book and scope."""
    text = str(body.get("request") or "").strip()[:500]
    book, filters = str(body.get("book") or ""), None
    if body.get("lens_id"):
        _visible(request, str(body["lens_id"]))
        spec = store().spec(str(body["lens_id"]))
        book, filters = spec["book"], spec.get("filters") or []
    p = _guard(lambda: personas.plan(text, book, persona=str(body.get("persona") or ""), filters=filters))
    return p or {"persona": None, "personas": personas.personas_public()}


@app.get(f"{PREFIX}/lenses/{{lens_id}}")
def lens(lens_id: str, request: Request) -> dict[str, Any]:
    lens = _visible(request, lens_id)
    u = access.user(request)
    return {**_card(lens, u.get("username", "")), "spec": store().spec(lens_id), "head": lens["head"], "latest": lens["version"],
            "versions": store().versions(lens_id), "thread_id": lens["thread_id"],
            "can_edit": lens["kind"] not in ("template", "featured") and access.can_write(u, lens["owner"]) and not access.viewing_as(request)}


@app.get(f"{PREFIX}/lenses/{{lens_id}}/render")
def render_lens(lens_id: str, request: Request, period: str = Query(""), version: int = Query(0)) -> dict[str, Any]:
    lens = _visible(request, lens_id)
    v = version or lens["head"]
    spec = store().spec(lens_id, v)
    out = _guard(lambda: render(spec, period, cache_key=f"{lens_id}:{v}"))
    out = {**out, "commentary": _model_commentary(lens, v, out) or out["commentary"]}
    return {**out, "lens_id": lens_id, "version": v, "title": spec.get("title"), "name": lens["name"], "intel": spec.get("intel")}


def _model_commentary(lens: dict[str, Any], version: int, r: dict[str, Any]) -> dict[str, Any] | None:
    """The assistant model's own reading of this version (validated against the turn's figures), when it wrote one
    for the lens at its as-of period; otherwise the deterministic commentary stays."""
    if not lens.get("thread_id") or r["period"] != store().spec(lens["lens_id"], version).get("period", r["period"]):
        return None
    try:
        turns = SVC.store.turns(lens["thread_id"])
    except Exception:  # noqa: BLE001
        return None
    for t in reversed(turns):
        ans = t.get("answer") or {}
        blocks = ans.get("blocks") or []
        if ans.get("source") == "model" and any(b.get("type") == "lens_update" and b.get("version") == version for b in blocks):
            md = next((b.get("markdown", "") for b in blocks if b.get("type") == "answer"), "")
            if md.strip():
                return {"markdown": md, "source": "model"}
    return None


def _after(lens_id: str, change: str) -> dict[str, Any]:
    lens = store().lens(lens_id)
    store().update(lens_id, thumb=seed.thumb(store().spec(lens_id)))
    return {"lens_id": lens_id, "version": lens["head"], "latest": lens["version"], "change": change, "versions": store().versions(lens_id)}


@app.post(f"{PREFIX}/lenses/{{lens_id}}/edit")
def edit(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    lens = _writable(request, lens_id)
    spec = store().spec(lens_id)
    new, change = _guard(lambda: planner.apply_op(spec, body))
    store().commit(lens_id, new, change, access.user(request).get("username", ""))
    del lens
    return _after(lens_id, change)


@app.post(f"{PREFIX}/lenses/{{lens_id}}/command")
def command(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _writable(request, lens_id)
    spec = store().spec(lens_id)
    new, changes = _guard(lambda: planner.apply_command(spec, str(body.get("text") or "")))
    store().commit(lens_id, new, "; ".join(changes), access.user(request).get("username", ""))
    return _after(lens_id, "; ".join(changes))


@app.post(f"{PREFIX}/lenses/{{lens_id}}/undo")
def undo(lens_id: str, request: Request) -> dict[str, Any]:
    _writable(request, lens_id)
    store().move_head(lens_id, -1)
    return _after(lens_id, "undo")


@app.post(f"{PREFIX}/lenses/{{lens_id}}/redo")
def redo(lens_id: str, request: Request) -> dict[str, Any]:
    _writable(request, lens_id)
    store().move_head(lens_id, +1)
    return _after(lens_id, "redo")


@app.post(f"{PREFIX}/lenses/{{lens_id}}/restore")
def restore(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _writable(request, lens_id)
    v = int(body.get("version") or 0)
    if not any(x["version"] == v for x in store().versions(lens_id)):
        raise refuse(404, f"Version {v} does not exist.")
    store().restore(lens_id, v, access.user(request).get("username", ""))
    return _after(lens_id, f"restored version {v}")


@app.post(f"{PREFIX}/lenses/{{lens_id}}/save")
def save(lens_id: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    u = access.user(request)
    lens = _visible(request, lens_id)
    if access.viewing_as(request):
        raise refuse(403, "Read only while viewing as another user.")
    name = str(body.get("name") or lens["name"]).strip()[:120] or lens["name"]
    desc = str(body.get("description") or lens["description"] or "")[:600]
    tags = [str(t).strip()[:30] for t in (body.get("tags") or lens["tags"] or []) if str(t).strip()][:8]
    if lens["kind"] in ("template", "featured") or not access.can_write(u, lens["owner"]):
        new = store().create(owner=u.get("username", ""), team=u.get("team", ""), spec=store().spec(lens_id), name=name, description=desc,
                             tags=tags, saved=True, change=f"Saved from {lens['name']}")
        store().update(new["lens_id"], thumb=seed.thumb(store().spec(new["lens_id"])))
        return {"lens_id": new["lens_id"], "saved": True, "copied": True}
    store().update(lens_id, name=name, description=desc, tags=tags, saved=True)
    return {"lens_id": lens_id, "saved": True, "copied": False}


@app.post(f"{PREFIX}/lenses/{{lens_id}}/duplicate")
def duplicate(lens_id: str, request: Request) -> dict[str, Any]:
    u = access.user(request)
    lens = _visible(request, lens_id)
    new = store().create(owner=u.get("username", ""), team=u.get("team", ""), spec=store().spec(lens_id), name=f"{lens['name']} (copy)",
                         description=lens["description"], tags=lens["tags"], change=f"Duplicated from {lens['name']}")
    return {"lens_id": new["lens_id"]}


@app.delete(f"{PREFIX}/lenses/{{lens_id}}")
def delete(lens_id: str, request: Request) -> dict[str, Any]:
    _writable(request, lens_id)
    store().archive(lens_id)
    return {"deleted": lens_id}


@app.post(f"{PREFIX}/lenses/{{lens_id}}/share")
def share(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    lens = _visible(request, lens_id)
    u = access.user(request)
    users = outbound.expand(list(body.get("users") or []), list(body.get("teams") or []), exclude=u.get("username", ""))
    if not users:
        raise refuse(422, "Choose at least one person or team to share with.")
    spec = store().spec(lens_id)
    out = outbound.mail_share(request, users, str(body.get("note") or ""), outbound.mail_object(lens, spec))
    for x in body.get("users") or []:
        store().share(lens_id, "user", str(x), u.get("username", ""))
    for x in body.get("teams") or []:
        store().share(lens_id, "team", str(x), u.get("username", ""))
    return {"shared_with": users, "mail": out}


@app.get(f"{PREFIX}/playbook/reports")
def playbook_reports(request: Request) -> dict[str, Any]:
    return outbound.playbook_reports(request)


@app.post(f"{PREFIX}/lenses/{{lens_id}}/playbook")
def to_playbook(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if access.viewing_as(request):
        raise refuse(403, "Read only while viewing as another user.")
    lens = _visible(request, lens_id)
    if bool(body.get("report_id")) == bool(body.get("new_report")):
        raise refuse(422, "Send either report_id or new_report.")
    spec = store().spec(lens_id)
    r = render(spec, cache_key=f"{lens_id}:{lens['head']}")
    return outbound.playbook_import(request, lens, spec, r, body)


@app.get(f"{PREFIX}/playbook/sources")
def playbook_sources(request: Request, q: str = Query("")) -> dict[str, Any]:
    u = access.user(request)
    out = []
    for lens in store().lenses():
        if lens["kind"] in ("template", "featured") or not lens["saved"] or not access.can_see(u, lens, request, store()):
            continue
        if q and not all(w in f"{lens['name']} {lens['description']}".lower() for w in q.lower().split()):
            continue
        out.append(outbound.source(lens, store().spec(lens["lens_id"])))
    return {"sources": out[:50]}


@app.get(f"{PREFIX}/playbook/section")
def playbook_section(request: Request, id: str = Query(...)) -> dict[str, Any]:
    lens = _visible(request, id)
    spec = store().spec(id)
    r = render(spec, cache_key=f"{id}:{lens['head']}")
    return {"source": outbound.source(lens, spec), "section": outbound.section(lens, spec, r)}


@app.get(f"{PREFIX}/lenses/{{lens_id}}/export.xlsx")
def export_xlsx(lens_id: str, request: Request, period: str = Query("")) -> Response:
    lens = _visible(request, lens_id)
    spec = store().spec(lens_id)
    r = render(spec, period, cache_key=f"{lens_id}:{lens['head']}")
    body = exports.xlsx(lens, spec, r, generated_by(request))
    return Response(body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{lens_id}.xlsx"'})


@app.get(f"{PREFIX}/lenses/{{lens_id}}/export.pdf")
def export_pdf(lens_id: str, request: Request, period: str = Query("")) -> Response:
    lens = _visible(request, lens_id)
    spec = store().spec(lens_id)
    r = render(spec, period, cache_key=f"{lens_id}:{lens['head']}")
    body = exports.pdf(lens, spec, r, generated_by(request))
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{lens_id}.pdf"'})


@app.post(f"{PREFIX}/lenses/{{lens_id}}/schedule")
def schedule(lens_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    lens = _visible(request, lens_id)
    if access.viewing_as(request):
        raise refuse(403, "Read only while viewing as another user.")
    cad = str(body.get("cadence") or "")
    if cad == "off":
        store().update(lens_id, schedule=None)
        return {"schedule": None}
    if cad not in ("daily", "weekly", "monthly"):
        raise refuse(422, "cadence must be daily, weekly, monthly or off.")
    u = access.user(request)
    recipients = outbound.expand(list(body.get("recipients") or []), list(body.get("teams") or []), exclude="")
    days = {"daily": 1, "weekly": 7, "monthly": 30}[cad]
    sch = {"cadence": cad, "recipients": recipients or [u.get("username", "")], "by": u.get("username", ""), "set_at": time.time(),
           "next_at": time.time() + days * 86400, "note": f"A refresh note with the lens figures goes out {cad} through Mail."}
    others = [x for x in sch["recipients"] if x != u.get("username")]
    if others:
        # The first refresh note goes now, through Mail, with the lens's current figures.
        spec = store().spec(lens_id)
        r = render(spec, cache_key=f"{lens_id}:{lens['head']}")
        figures = "; ".join(f"{k['label']} {k['display']}" for k in r["kpis"][:8])
        note = (f"Refresh note ({cad}) for the lens {lens['name']} as of {r['period']}: {figures}. "
                f"The lens opens with every chart and its queries.")
        try:
            outbound.mail_share(request, others, note, outbound.mail_object(lens, spec))
            sch["last_sent_at"] = time.time()
        except HTTPException:
            sch["last_sent_at"] = None
    store().update(lens_id, schedule=sch)
    return {"schedule": sch}


@app.post(f"{PREFIX}/lenses/{{lens_id}}/tiles/{{tile_id}}/handoff")
def handoff(lens_id: str, tile_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _visible(request, lens_id)
    spec = store().spec(lens_id)
    from backend.convo.spec import ToolContext
    ctx = ToolContext(domain=convo_domain.DOMAIN, thread={}, state={}, scope={"lens_id": lens_id}, user=access.user(request),
                      question=f"{tile_id} {body.get('target', 'cockpit')}", execute=False)
    del spec
    r = _guard(lambda: convo_domain.t_handoff(ctx, {"tile": tile_id, "target": str(body.get("target") or "cockpit")}))
    return {"summary": r.summary, **r.blocks[0]}


@app.post(f"{PREFIX}/custom/validate")
def custom_validate(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    b = str(body.get("book") or "corporate")
    c = {"key": "custom-check", "label": str(body.get("label") or "Custom ratio"), "num": body.get("num"), "den": body.get("den"),
         "filters": body.get("filters") or [], "scale": float(body.get("scale", 100)), "unit": "pct" if float(body.get("scale", 100)) == 100 else "ratio"}
    v = _guard(lambda: planner.validate_custom(b, c))
    from backend.lenses_v5 import fmt
    return {"valid": True, "value": v, "display": fmt.fmt_value(v, c["unit"]), "period": ENGINE.as_of(b)}


def _json(x: Any) -> str:
    return json.dumps(x)


# ------------------------------------------------------------------ PLAN_R9 D: P1 CBUAE CRM Intelligence
@app.get(f"{PREFIX}/crm/library")
def crm_library() -> dict[str, Any]:
    """The CBUAE CRM metric library (Lenses -> Library)."""
    return crm_intel.library()


@app.post(f"{PREFIX}/crm/upload")
async def crm_upload(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """A circular dropped into the Lenses chat -> obligations by article, mapped to the library (available / partial / data gap)."""
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise refuse(413, "The file is larger than 25 MB.")
    try:
        return crm_intel.read_upload(file.filename or "circular.pdf", data)
    except crm_intel.UploadError as exc:
        raise refuse(422, str(exc)) from exc


@app.post(f"{PREFIX}/crm/dashboard", status_code=201)
def crm_dashboard(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """'Create the dashboard': the CBUAE CRM Lens, built and saved at once (a new lens every time, so it works twice)."""
    name = access.viewing_as(request)
    if name:
        raise refuse(403, f"Read only while viewing as {name}.")
    u = access.user(request)
    book = str(body.get("book") or "corporate")
    if book not in ("corporate", "retail"):
        book = "corporate"
    spec = _guard(lambda: crm_intel.dashboard_spec(book))
    if body.get("upload_id"):
        spec["intel"]["upload_id"] = str(body["upload_id"])[:32]
    stamp = time.strftime("%d %b %Y %H:%M")
    lens = store().create(owner=u.get("username", ""), team=u.get("team", ""), spec=spec, name=f"CBUAE CRM dashboard · {stamp}",
                          description="Built from the CBUAE Credit Risk Management Standards (P1 CBUAE CRM Intelligence).",
                          tags=[book, "cbuae crm", "regulatory"])
    try:
        opened = SVC.open_thread(domain="lenses", scope={"lens_id": lens["lens_id"], "book": book}, owner=u.get("username", ""),
                                 team=u.get("team", ""), title=spec["title"][:80], origin="lenses-crm")
        store().update(lens["lens_id"], thread_id=opened["thread"]["thread_id"], saved=1, thumb=seed.thumb(spec))
    except Exception:  # noqa: BLE001 - the lens opens without its thread rather than fail the demo moment
        store().update(lens["lens_id"], saved=1)
    return {"lens": _card(store().lens(lens["lens_id"]), u.get("username", "")), "lens_id": lens["lens_id"],
            "href": f"/lenses/{lens['lens_id']}", "findings": spec["intel"]["findings"]}
