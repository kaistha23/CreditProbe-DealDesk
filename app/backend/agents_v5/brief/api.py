"""Noor's endpoints (PLAN_R12 N1), mounted on the Deal Desk service by one line in its `# R12 routers` block.

    GET  /api/v1/noor/brief?persona=&module=&top=     the role-based brief (or a module brief)
    POST /api/v1/noor/brief                           same, with the Cockpit attention cards the page read {attention: [...]}
    POST /api/v1/noor/why                             {item_id, item?}  -> trace steps, one-line answer, one Plotly figure
    POST /api/v1/noor/options                         {item_id, item?}  -> three options with engine numbers
    POST /api/v1/noor/script                          {item_id, item?}  -> the spoken script, 40–70 s, en + ar (R14 K10)
    POST /api/v1/noor/drivers                         {item_id, item?}  -> who drives it: the named borrowers behind the line
    POST /api/v1/noor/committee                       {item, option}    -> the committee item (pending CCO decision)
    GET  /api/v1/noor/committee                       recent committee items Noor created
    GET  /api/v1/noor/settings, PUT (administrator)   name and voice
    GET  /api/v1/noor/voice, PUT                      the reader's own voice choice {on, language} (R13 H, J1)
    GET  /api/v1/noor/personas                        the "Viewing as" personas and whether this account may switch
    POST /api/v1/noor/brief/prepare                   (administrator) today's brief for everyone, with a bell notification
    POST /api/v1/noor/route                           {question, lines?, domain?} -> which engine answers it (R13 H, J2):
                                                      a brief line, What-If, Lenses, Deal Desk or the Cockpit; never a refusal
    POST /api/v1/noor/here                            {question, context: {deal_id, step, structures}, force?} -> the
                                                      answer in the page context (R15 a, L9), or {here: false, reason}
    POST /api/v1/noor/here/fix                        {deal_id, from_key, target?} -> the cheapest fix (stress-proof, read only)

Identity comes from the Core service session; `persona` is honoured only for administrator and demo accounts (I17:
the switch is for demos), everyone else gets the persona of their own role.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.agents_v5.brief import service
from backend.agents_v5.brief.items import PERSONAS, persona_for

router = APIRouter(prefix="/api/v1/noor", tags=["noor"])


def _who(request: Request) -> dict[str, Any]:
    if os.environ.get("NOOR_TRUST_HEADERS") == "1" and request.headers.get("x-noor-user"):
        return {"username": request.headers["x-noor-user"], "name": request.headers.get("x-noor-name", ""),
                "role": request.headers.get("x-noor-role", ""), "is_admin": request.headers.get("x-noor-admin") == "1"}
    try:
        from backend.identity_v5.client import current_user
        u = current_user(request) or {}
    except Exception:  # noqa: BLE001
        u = {}
    return dict(u)


def may_switch(u: dict[str, Any]) -> bool:
    """Demo and admin accounts only (I17)."""
    if u.get("is_admin"):
        return True
    name = str(u.get("username") or "").lower()
    return name.startswith("demo") or "demo" in str(u.get("role") or "").lower() or \
        os.environ.get("NOOR_DEMO_SWITCH") == "1"


def _persona(u: dict[str, Any], asked: str) -> str:
    return persona_for(u.get("role"), asked if (asked and may_switch(u)) else None)


@router.get("/brief")
def get_brief(request: Request, persona: str = Query(""), module: str = Query(""), top: int = Query(5)) -> dict[str, Any]:
    u = _who(request)
    return service.brief(persona=_persona(u, persona), user=u, module=module, top=top)


@router.post("/brief")
def post_brief(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    u = _who(request)
    att = body.get("attention") or []
    if not isinstance(att, list):
        raise HTTPException(422, "attention must be a list of Cockpit attention cards.")
    return service.brief(persona=_persona(u, str(body.get("persona") or "")), user=u, module=str(body.get("module") or ""),
                         attention=att[:20], top=int(body.get("top") or 5), polish=bool(body.get("polish")),
                         hour=_hour(body.get("hour")))


def _hour(v: Any) -> int | None:
    """The reader's own clock hour (the greeting is "Good morning" by the viewer's clock, not the server's)."""
    try:
        h = int(v)
    except (TypeError, ValueError):
        return None
    return h if 0 <= h <= 23 else None


def _item(body: dict[str, Any]) -> dict[str, Any]:
    iid = str(body.get("item_id") or (body.get("item") or {}).get("id") or "")
    if not iid:
        raise HTTPException(422, "item_id is needed.")
    got = service.find_item(iid, persona=str(body.get("persona") or ""), item=body.get("item"),
                            attention=body.get("attention"))
    if got is None:
        raise HTTPException(404, "That line is no longer in the brief.")
    return got


@router.post("/brief/prepare")
def post_prepare(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Prepare today's brief for everyone and notify them (the before-the-working-day run, on demand)."""
    u = _who(request)
    if not u.get("is_admin"):
        raise HTTPException(403, "Only an administrator prepares everyone's brief.")
    from backend.agents_v5.brief import prepare
    return prepare.prepare(notify=bool(body.get("notify", True)))


@router.post("/why")
def post_why(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return service.why(_item(body))


@router.post("/script")
def post_script(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """R14 n (K10): the spoken script for one brief line {item_id, item?} -> {en, ar, seconds_en, seconds_ar, facts}."""
    return service.issue_script(_item(body))


@router.post("/drivers")
def post_drivers(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return service.who_drives(_item(body))


@router.post("/options")
def post_options(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return service.what_to_do(_item(body))


@router.post("/committee")
def post_committee(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _who(request)
    if not u.get("username"):
        raise HTTPException(401, "Sign in to send an item to committee.")
    item = _item(body)
    return service.send_to_committee(item, body.get("option"), user=str(u.get("username")), role=str(u.get("role") or ""))


@router.get("/committee")
def get_committee(limit: int = Query(20)) -> dict[str, Any]:
    return {"items": service.committee_items(max(1, min(limit, 100)))}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return service.settings()


@router.put("/settings")
def put_settings(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _who(request)
    if not u.get("is_admin"):
        raise HTTPException(403, "Only an administrator changes the assistant's name and voice.")
    try:
        return service.save_settings(body, by=str(u.get("username") or ""))
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("/personas")
def get_personas(request: Request) -> dict[str, Any]:
    u = _who(request)
    return {"personas": [{"id": k, **v} for k, v in PERSONAS.items()], "own": persona_for(u.get("role")),
            "can_switch": may_switch(u)}


@router.post("/route")
def post_route(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Which engine answers a typed question (R13 H, J2 (b)). Deterministic; nothing is refused."""
    from backend.agents_v5.brief import route
    lines = body.get("lines") or []
    if not isinstance(lines, list):
        raise HTTPException(422, "lines must be a list of brief lines.")
    q = str(body.get("question") or "")
    if not q.strip():
        raise HTTPException(422, "question is needed.")
    ctx = _context(body) if body.get("context") else None
    return route.route(q[:2000], [x for x in lines[:40] if isinstance(x, dict)], domain=str(body.get("domain") or ""),
                       context=ctx if ctx and ctx.get("deal_id") else None)


def _context(body: dict[str, Any]) -> dict[str, Any]:
    c = body.get("context") or {}
    if not isinstance(c, dict):
        raise HTTPException(422, "context must be an object {deal_id, step, structures}.")
    keys = c.get("structures") or []
    if not isinstance(keys, list):
        raise HTTPException(422, "context.structures must be a list of structure keys.")
    return {"deal_id": str(c.get("deal_id") or "")[:40] or None, "step": str(c.get("step") or "")[:24] or None,
            "structures": [str(k)[:60] for k in keys[:8]], "stress_on_screen": bool(c.get("stress_on_screen")),
            "module": str(c.get("module") or "")[:24], "path": str(c.get("path") or "")[:200]}


@router.post("/here")
def post_here(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """R15 a (L9): answer in the page context (the deal, the step, the stress run on screen). Deterministic."""
    from backend.agents_v5.brief import here
    q = str(body.get("question") or "").strip()
    if not q:
        raise HTTPException(422, "question is needed.")
    ctx = _context(body)
    try:
        return here.answer(q[:2000], ctx, force=bool(body.get("force")))
    except KeyError:
        raise HTTPException(404, f"No deal {ctx.get('deal_id')}.") from None


@router.post("/here/fix")
def post_here_fix(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    from backend.agents_v5.brief import here
    pid, key = str(body.get("deal_id") or ""), str(body.get("from_key") or "")
    target = str(body.get("target") or "moderate")
    if not pid or not key or target not in ("mild", "moderate", "severe"):
        raise HTTPException(422, "deal_id, from_key and target (mild, moderate or severe) are needed.")
    try:
        return here.cheapest_fix(pid, key, target)
    except KeyError:
        raise HTTPException(404, f"No structure {key!r} on {pid}.") from None
    except Exception as e:  # noqa: BLE001 - the solver's own refusal (ProofError) reads as a plain line
        return {"deal_id": pid, "from_key": key, "target": target, "line": f"Stress-proof could not run here: {e}", "changes": [],
                "uncured": [], "asks": [], "survives": False, "basis": "Stress-proof solver"}


@router.get("/voice")
def get_voice(request: Request) -> dict[str, Any]:
    u = _who(request)
    return service.user_voice(str(u.get("username") or ""))


@router.put("/voice")
def put_voice(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _who(request)
    try:
        return service.save_user_voice(str(u.get("username") or ""), body)
    except ValueError as e:
        raise HTTPException(422 if u.get("username") else 401, str(e)) from None
