"""One middleware every v5 service installs (PLAN_R5 A1):

    from backend.access import install
    install(app, "early_warning")                                   # the whole service is one module
    install(app, "playbook", routes={"/api/v1/policy": "policy_docs"})   # path prefix -> module

For each request it resolves the caller's effective policy (the `cp_session` cookie -> Core -> Admin policies) and:
  1. refuses a module the policy does not open (403 ACCESS_MODULE);
  2. refuses an action the policy does not grant (403 ACCESS_ACTION): exports (.xlsx/.docx/.csv, /export),
     sending (mail send, share), approving, running a model (the service names its run paths);
  3. sets the policy for the request (`enforce.current()`), so engines and the conversational agent filter at source;
  4. filters the response: JSON rows outside the policy are dropped (lists, and the counts beside them), names and
     IDs are masked; Excel exports lose the rows outside the policy.
Requests with no session (tests, service-to-service calls) are not restricted; every browser request has one.
"""
from __future__ import annotations

import json
import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.access import enforce, policy as pol
from backend.identity_v5.client import cookie_name as _cookie_name

EXEMPT = re.compile(r"(/health$|/api/v1/auth/|/api/v1/users(/|$)|/api/v1/access/|/openapi\.json$|/docs$)")
EXPORT = re.compile(r"(/export|\.xlsx$|\.docx$|\.csv$|\.pdf$|/download)", re.I)
SEND = re.compile(r"(/mail/send|/mail/messages$|/share$|/send$)", re.I)
APPROVE = re.compile(r"(/approve$|/sign-?off$|/decide$)", re.I)


def _user(request: Request) -> dict[str, Any] | None:
    """The effective user of the request's session, read from the Core store directly (same machine, read-only):
    no network call, so enforcement never fails open because the Core service is slow. Falls back to the identity
    client when the store is not on this machine."""
    token = request.cookies.get(_cookie_name())
    if not token:
        return None
    import hashlib
    con = pol._ro(pol.core_store_path())  # noqa: SLF001
    if con is not None:
        try:
            r = con.execute("SELECT s.username, s.view_as, s.expires_at, u.is_admin FROM sessions s JOIN users u "
                            "ON u.username = s.username WHERE s.token_hash=?",
                            (hashlib.sha256(token.encode("utf-8")).hexdigest(),)).fetchone()
            if r is None:
                return None
            name = r["view_as"] if (r["view_as"] and r["is_admin"]) else r["username"]
            return pol.core_user(name)
        except Exception:  # noqa: BLE001
            pass
        finally:
            con.close()
    try:
        from backend.identity_v5.client import current_user
        return current_user(request)
    except Exception:  # noqa: BLE001 - no identity service: anonymous
        return None


def refuse(code: str, message: str) -> JSONResponse:
    return JSONResponse({"detail": {"error_code": code, "message": message}}, status_code=403)


class AccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, module: str, routes: dict[str, str] | None = None, run_paths: str = ""):
        super().__init__(app)
        self.module = module
        self.routes = sorted((routes or {}).items(), key=lambda kv: -len(kv[0]))
        self.run_re = re.compile(run_paths, re.I) if run_paths else None

    def module_for(self, path: str) -> str:
        for prefix, mod in self.routes:
            if path.startswith(prefix):
                return mod
        return self.module

    def action_for(self, request: Request) -> str | None:
        path = request.url.path
        if EXPORT.search(path):
            return "export"
        if request.method == "POST" and SEND.search(path):
            return "send"
        if request.method == "POST" and APPROVE.search(path):
            return "approve"
        if request.method == "POST" and self.run_re is not None and self.run_re.search(path):
            return "run_model"
        return None

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or EXEMPT.search(path):
            return await call_next(request)
        user = _user(request)
        p = pol.for_user(user) if user else pol.UNRESTRICTED
        module = self.module_for(path)
        if module and not p.allows_module(module):
            return refuse("ACCESS_MODULE", f"Your data access policy does not include {pol.MODULES.get(module, module)}.")
        action = self.action_for(request)
        if action and not p.allows_action(action):
            return refuse("ACCESS_ACTION", f"Your data access policy does not allow: {pol.ACTIONS[action]}.")
        with enforce.use(p):
            response = await call_next(request)
            if p.unrestricted or not p.row_restricted or response.status_code >= 400:
                return response
            ctype = response.headers.get("content-type", "")
            if ctype.startswith("application/json"):
                body = b"".join([chunk async for chunk in response.body_iterator])
                try:
                    data = enforce.filter_json(json.loads(body or b"null"), p)
                except ValueError:
                    return _rebuild(response, body)
                return _rebuild(response, json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
            if ctype.startswith("text/csv"):
                body = b"".join([chunk async for chunk in response.body_iterator])
                return _rebuild(response, enforce.filter_csv(body, p))
            if "spreadsheetml" in ctype:
                body = b"".join([chunk async for chunk in response.body_iterator])
                return _rebuild(response, enforce.filter_xlsx(body, p))
            return response


def _rebuild(response: Response, body: bytes) -> Response:
    headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length",)}
    return Response(content=body, status_code=response.status_code, headers=headers,
                    media_type=response.media_type)


def install(app, module: str, routes: dict[str, str] | None = None, run_paths: str = "") -> None:
    """Add the access middleware to a FastAPI app (call before the CORS middleware is added, so CORS stays
    outermost and refusals carry the CORS headers)."""
    app.add_middleware(AccessMiddleware, module=module, routes=routes, run_paths=run_paths)
