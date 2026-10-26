"""Who may see what (MAIL_API.md section 3): the Administrator sees everything; everyone else
sees what they own, what was shared with them, and what their team owns. Items with no owner
(standard scenarios, threads made before sign-in existed) are visible to everyone."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import Request

from backend.identity_v5.client import COOKIE, current_user

ANON = {"username": "", "name": "", "team": "", "is_admin": False}
_SHARED: dict[str, tuple[float, set[tuple[str, str]]]] = {}


def user(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return u or dict(ANON)


def core_base() -> str:
    return (os.environ.get("CORE_API_ORIGIN") or "http://127.0.0.1:8505").rstrip("/")


def shared_with_me(request: Request) -> set[tuple[str, str]]:
    token = request.cookies.get(COOKIE)
    if not token:
        return set()
    hit = _SHARED.get(token)
    if hit and time.monotonic() - hit[0] < 5:
        return hit[1]
    out: set[tuple[str, str]] = set()
    try:
        req = urllib.request.Request(core_base() + "/api/v1/mail/shared-with-me?type=whatif-scenario&type=whatif-thread",
                                     headers={"Cookie": f"{COOKIE}={token}"})
        with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 - fixed loopback origin
            for o in json.loads(resp.read().decode()).get("objects", []):
                out.add((o.get("type", ""), o.get("id", "")))
    except (urllib.error.URLError, OSError, ValueError):
        pass
    _SHARED[token] = (time.monotonic(), out)
    return out


def can_see(u: dict[str, Any], owner: str, team: str, kind: str, oid: str, request: Request | None = None) -> bool:
    if not owner or u.get("is_admin") or not u.get("username"):
        return True
    if owner == u.get("username"):
        return True
    if team and team == u.get("team"):
        return True
    return request is not None and (kind, oid) in shared_with_me(request)


def can_write(u: dict[str, Any], owner: str) -> bool:
    return not owner or not u.get("username") or owner == u.get("username") or bool(u.get("is_admin"))
