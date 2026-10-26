"""In-process access to the Deal Desk engine API (the same routes and code the screens call).

The agent never re-implements an engine: each tool calls a Deal Desk route through FastAPI's
TestClient on `backend.dealdesk.api.app` (read-only routes, plus the two routes an approved
proposal applies). A route that is not mounted on this build means the R11 engine behind it
has not been merged yet: the tool reports "not available on this build".
"""
from __future__ import annotations

import re
import threading
from typing import Any

PREFIX = "/api/v1/dealdesk"
_CLIENT: Any = None
_LOCK = threading.Lock()
#: one engine call at a time from this process: the in-process client is shared by background runs
_CALL = threading.RLock()


class EngineError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


def app():
    from backend.dealdesk.api import app as a
    return a


def client():
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            from fastapi.testclient import TestClient
            _CLIENT = TestClient(app(), raise_server_exceptions=False)
        return _CLIENT


def has_route(method: str, template: str) -> bool:
    """`template` uses {pid}-style placeholders, e.g. "/proposals/{pid}/pipeline-test"."""
    from starlette.routing import Match
    path = re.sub(r"\{[^}]+\}", "DD-01", PREFIX + template)
    scope = {"type": "http", "path": path, "method": method.upper(), "root_path": "", "headers": [],
             "query_string": b""}
    for r in app().routes:
        try:
            m, _ = r.matches(scope)
        except Exception:  # noqa: BLE001 - a route that cannot match this scope
            continue
        if m == Match.FULL:
            return True
    return False


def call(method: str, path: str, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    c = client()
    kw: dict[str, Any] = {}
    if body is not None:
        kw["json"] = body
    if params:
        kw["params"] = params
    with _CALL:
        r = getattr(c, method.lower())(PREFIX + path, **kw)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text[:300]
        raise EngineError(r.status_code, str(detail)[:400])
    return r.json()
