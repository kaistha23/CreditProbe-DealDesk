"""Auth and user directory routes, mounted on the Core service (backend.workspace_v5.api, port 8505).

  POST /api/v1/auth/login     {username, password}  sets cookie cp_session
  POST /api/v1/auth/logout
  GET  /api/v1/auth/me        401 when not signed in (for services)
  GET  /api/v1/auth/session   200 either way (for the browser's first check)
  POST /api/v1/auth/view-as   {username|null}        Administrator only
  GET  /api/v1/users          the directory (needs a session)
  GET  /api/v1/users/{username}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.identity_v5 import store
from backend.identity_v5.client import cookie_name as _cookie_name

COOKIE = "cp_session"
router = APIRouter(prefix="/api/v1")


@dataclass
class Ctx:
    """Who is calling. `me` signed in; `user` the effective user the data is shown for."""
    me: dict[str, Any]
    user: dict[str, Any]
    is_admin: bool
    viewing_as: dict[str, Any] | None
    token: str

    @property
    def username(self) -> str:
        return self.user["username"]

    @property
    def actor(self) -> str:
        return self.me["username"]


def run(fn, *args, **kwargs):
    """Run a store function in one transaction and translate its errors to HTTP."""
    try:
        with store.db() as con:
            return fn(con, *args, **kwargs)
    except store.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except store.NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc
    except store.Invalid as exc:
        raise HTTPException(422, str(exc)) from exc


def optional_ctx(request: Request) -> Ctx | None:
    token = request.cookies.get(_cookie_name())
    if not token:
        return None
    with store.db() as con:
        info = store.session_info(con, token)
    if info is None:
        return None
    return Ctx(me=info["user"], user=info["effective_user"], is_admin=info["is_admin"],
               viewing_as=info["viewing_as"], token=token)


def require_ctx(request: Request) -> Ctx:
    ctx = optional_ctx(request)
    if ctx is None:
        raise HTTPException(401, "not signed in")
    return ctx


def require_admin(ctx: Ctx = Depends(require_ctx)) -> Ctx:
    if not ctx.is_admin:
        raise HTTPException(403, "Administrator only.")
    return ctx


class LoginIn(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class ViewAsIn(BaseModel):
    username: str | None = None


def _me_payload(info: dict[str, Any]) -> dict[str, Any]:
    return {"user": info["user"], "effective_user": info["effective_user"], "viewing_as": info["viewing_as"],
            "is_admin": info["is_admin"]}


@router.post("/auth/login")
def login(payload: LoginIn, response: Response) -> dict[str, Any]:
    try:
        with store.db() as con:
            token, user = store.login(con, payload.username, payload.password)
    except store.NotPermitted as exc:
        msg = str(exc)
        raise HTTPException(429 if msg.startswith("Too many") else 401, msg) from exc
    response.set_cookie(_cookie_name(), token, httponly=True, samesite="lax", path="/", max_age=store.SESSION_HOURS * 3600)
    return {"user": user, "effective_user": user, "viewing_as": None, "is_admin": user["is_admin"]}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    run(store.logout, request.cookies.get(_cookie_name()))
    response.delete_cookie(_cookie_name(), path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return {"user": ctx.me, "effective_user": ctx.user, "viewing_as": ctx.viewing_as, "is_admin": ctx.is_admin}


@router.get("/auth/session")
def session(request: Request) -> dict[str, Any]:
    """Like /auth/me, but answers 200 with `authenticated: false` instead of 401, so the sign-in check on a
    page load is not a failed request."""
    ctx = optional_ctx(request)
    if ctx is None:
        return {"authenticated": False}
    return {"authenticated": True, "user": ctx.me, "effective_user": ctx.user, "viewing_as": ctx.viewing_as,
            "is_admin": ctx.is_admin}


class PreferencesIn(BaseModel):
    presenter_name: str | None = Field(default=None, max_length=200)


@router.get("/auth/preferences")
def get_preferences(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    """The signed-in user's own preferences (PLAN_R6 B4: the presenter's "Showing to" name)."""
    return {"preferences": run(store.preferences, ctx.actor)}


@router.put("/auth/preferences")
def put_preferences(payload: PreferencesIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    return {"preferences": run(store.set_preferences, ctx.actor, values)}


@router.post("/auth/view-as")
def view_as(payload: ViewAsIn, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    info = run(store.set_view_as, ctx.token, payload.username)
    return _me_payload(info)


@router.get("/users")
def list_users(ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    users = run(store.users)
    return {"users": users, "count": len(users)}


@router.get("/users/{username}")
def get_user(username: str, ctx: Ctx = Depends(require_ctx)) -> dict[str, Any]:
    return run(store.get_user, username)
