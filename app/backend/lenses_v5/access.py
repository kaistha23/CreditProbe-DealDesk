"""Who may see and change a lens (MAIL_API.md section 3, as every v5 module).

Templates and unowned lenses are visible to everyone. Otherwise the Administrator sees everything; a user sees
what they own, what their team owns and has saved, and what was shared with them (through Mail, type "lens",
or recorded in the lens's own shares). Only the owner (or the Administrator) changes a lens; everyone else
duplicates it.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request

from backend.scorecard_v5 import access as _shared_access

KIND = "lens"
ANON = {"username": "", "name": "", "team": "", "is_admin": False}


def user(request: Request) -> dict[str, Any]:
    return _shared_access.user(request)


def viewing_as(request: Request) -> str:
    return _shared_access.viewing_as(request)


def _mail_shared(request: Request) -> set[str]:
    from backend.identity_v5.client import COOKIE
    import json
    import time
    import urllib.error
    import urllib.request
    token = request.cookies.get(COOKIE)
    if not token:
        return set()
    hit = _CACHE.get(token)
    if hit and time.monotonic() - hit[0] < 5:
        return hit[1]
    out: set[str] = set()
    try:
        req = urllib.request.Request(_shared_access.core_base() + f"/api/v1/mail/shared-with-me?type={KIND}", headers={"Cookie": f"{COOKIE}={token}"})
        with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310 - fixed loopback origin
            for o in json.loads(resp.read().decode()).get("objects", []):
                if o.get("type") == KIND:
                    out.add(o.get("id", ""))
    except (urllib.error.URLError, OSError, ValueError):
        pass
    _CACHE[token] = (time.monotonic(), out)
    return out


_CACHE: dict[str, tuple[float, set[str]]] = {}


def shared_ids(request: Request | None, store: Any, u: dict[str, Any]) -> set[str]:
    ids = set(store.shared_with(u.get("username", ""), u.get("team", ""))) if store and u.get("username") else set()
    if request is not None:
        ids |= _mail_shared(request)
    return ids


def can_see(u: dict[str, Any], lens: dict[str, Any], request: Request | None, store: Any) -> bool:
    if lens["kind"] in ("template", "featured") or not lens["owner"] or u.get("is_admin") or not u.get("username"):
        return True
    if lens["owner"] == u.get("username"):
        return True
    if lens.get("team") and lens["team"] == u.get("team") and lens.get("saved"):
        return True
    return lens["lens_id"] in shared_ids(request, store, u)


def can_write(u: dict[str, Any], owner: str) -> bool:
    return not owner or not u.get("username") or owner == u.get("username") or bool(u.get("is_admin"))
