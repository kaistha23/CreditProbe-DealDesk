"""Who is calling? For any v5 service other than the Core service (8505).

The browser sends the `cp_session` cookie to every v5 port (same host). A
service asks the Core service who it belongs to:

    from backend.identity_v5.client import current_user, require_user
    user = current_user(request)    # the effective user (dict) or None
    user = require_user(request)    # raises HTTP 401 when not signed in

Results are cached for CACHE_SECONDS per session cookie. For local development
without the Core service, set CP_IDENTITY_FALLBACK_USER=anne (never in a
delivered environment).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException, Request

COOKIE = "cp_session"  # the default; read cookie_name() at call time
CACHE_SECONDS = 5.0
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def core_base() -> str:
    return (os.environ.get("CORE_API_ORIGIN") or "http://127.0.0.1:8505").rstrip("/")


def _fallback() -> dict[str, Any] | None:
    name = os.environ.get("CP_IDENTITY_FALLBACK_USER", "").strip()
    if not name:
        return None
    return {"username": name, "name": name, "role": "Administrator" if name == "anne" else "User",
            "is_admin": name == "anne", "books": ["corporate", "retail"], "team": "admin" if name == "anne" else "",
            "initials": name[:2].upper(), "fallback": True}


def user_for_cookie(token: str | None) -> dict[str, Any] | None:
    if not token:
        return _fallback()
    now = time.monotonic()
    hit = _cache.get(token)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    user: dict[str, Any] | None
    try:
        req = urllib.request.Request(core_base() + "/api/v1/auth/me", headers={"Cookie": f"{cookie_name()}={token}"})
        with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 - fixed loopback origin
            user = json.loads(resp.read().decode("utf-8")).get("effective_user")
    except urllib.error.HTTPError as exc:
        user = None if exc.code == 401 else _fallback()
    except (urllib.error.URLError, OSError, ValueError):
        user = _fallback()
    _cache[token] = (now, user)
    return user


def current_user(request: Request) -> dict[str, Any] | None:
    return user_for_cookie(request.cookies.get(cookie_name()))


def require_user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "not signed in")
    return user

def cookie_name() -> str:
    """The session cookie's name: `cp_session`, or CP_SESSION_COOKIE when one install must not share its sign-in with
    another on the same host (the Deal Desk edition beside R16 on the Mac: cookies are per host, not per port)."""
    return (os.environ.get("CP_SESSION_COOKIE") or "cp_session").strip() or "cp_session"
