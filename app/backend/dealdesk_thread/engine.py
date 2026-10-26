"""The one door to the Deal Desk engine (DEAL_DESK_PROMPT 3.7, docs/v5/DEALDESK_API.md).

The thread layer and the conversation call the engine only through here, on
the engine's own HTTP contract (paths under /api/v1/dealdesk), in-process. The
Session C1 engine app (`backend.dealdesk.api:app`) is used when it is
importable; until then the contract-shaped reference engine stands in with
the same paths and schemas. `DEALDESK_ENGINE=reference` forces the reference
engine (tests).

Every response carries a `trace_id`; a `Recorder` keeps the calls of one turn
so the validator can check that each figure in an answer came from one.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

PREFIX = "/api/v1/dealdesk"

_LOCK = threading.Lock()
_APP: Any = None
_CLIENT: Any = None
_SOURCE = ""


class EngineError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def app() -> Any:
    """The engine's ASGI app: C1's when present, else the reference engine."""
    global _APP, _SOURCE
    with _LOCK:
        if _APP is None:
            if os.environ.get("DEALDESK_ENGINE", "").lower() != "reference":
                try:
                    from backend.dealdesk.api import app as c1  # type: ignore[import-not-found]
                    _APP, _SOURCE = c1, "backend.dealdesk"
                except Exception:  # noqa: BLE001 - not merged yet, or broken: the reference engine
                    _APP = None
            if _APP is None:
                from backend.dealdesk_thread import reference
                _APP, _SOURCE = reference.app, "reference"
        return _APP


def source() -> str:
    app()
    return _SOURCE


def _client() -> Any:
    global _CLIENT
    a = app()
    with _LOCK:
        if _CLIENT is None:
            from fastapi.testclient import TestClient
            _CLIENT = TestClient(a, raise_server_exceptions=True)
        return _CLIENT


def request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    r = _client().request(method, PREFIX + path, json=body, params={k: v for k, v in (params or {}).items() if v not in (None, "")})
    try:
        out = r.json()
    except ValueError:
        out = {}
    if r.status_code >= 400:
        d = out.get("detail") if isinstance(out, dict) else None
        msg = d if isinstance(d, str) else (d or {}).get("message") if isinstance(d, dict) else f"Engine refused ({r.status_code})."
        raise EngineError(r.status_code, str(msg))
    return out


class Recorder:
    """The engine calls of one turn or one screen request, with their trace IDs and results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, path: str, **params: Any) -> dict:
        return self._do("GET", path, None, params)

    def post(self, path: str, body: dict) -> dict:
        return self._do("POST", path, body, None)

    def _do(self, method: str, path: str, body: dict | None, params: dict | None) -> dict:
        t0 = time.perf_counter()
        out = request(method, path, body, params)
        self.calls.append({"call": f"{method} {path}", "trace_id": out.get("trace_id"), "ms": round((time.perf_counter() - t0) * 1000, 1),
                           "result": out})
        return out

    @property
    def trace_ids(self) -> list[str]:
        return [c["trace_id"] for c in self.calls if c.get("trace_id")]


# Convenience calls (DEALDESK_API.md section 1).

def get(path: str, **params: Any) -> dict:
    return request("GET", path, None, params)


def post(path: str, body: dict) -> dict:
    return request("POST", path, body)
