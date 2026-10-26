"""Sign in to the Core service for the browser tests (smoke, sweep): returns the session cookie.

The password is read from the environment (CP_SMOKE_PASSWORD, one password for every user, for a test store)
or from ~/CreditProbe_Workspace/USERS_LOCAL.md (or CP_USERS_LOCAL), where the service wrote the initial
passwords. Nothing is printed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

CORE = os.environ.get("CORE_API_ORIGIN", "http://127.0.0.1:8505").rstrip("/")


def users_local_path() -> Path:
    env = os.environ.get("CP_USERS_LOCAL")
    return Path(env).expanduser() if env else Path.home() / "CreditProbe_Workspace" / "USERS_LOCAL.md"


def password_for(username: str) -> str:
    if os.environ.get("CP_SMOKE_PASSWORD"):
        return os.environ["CP_SMOKE_PASSWORD"]
    if os.environ.get("CP_TEST_PASSWORD"):
        return os.environ["CP_TEST_PASSWORD"]
    text = users_local_path().read_text(encoding="utf-8")
    m = re.search(rf"\|\s*`{re.escape(username)}`\s*\|[^|]*\|\s*`([^`]+)`", text)
    if not m:
        raise RuntimeError(f"No password for {username} in {users_local_path()}")
    return m.group(1)


def login(username: str = "anne") -> dict:
    """Sign in over HTTP; returns {"cookie": value, "me": {...}}."""
    if os.environ.get("CP_MINT_SESSION") == "1":
        # A session minted in the local identity store (cloud session without the users file); no password used.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from r10_chat_audit import session as mint
        tok = mint()
        req = urllib.request.Request(f"{CORE}/api/v1/auth/me", headers={"Cookie": f"cp_session={tok}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                me = json.loads(r.read())
        except Exception:  # noqa: BLE001
            me = {"username": username}
        return {"cookie": tok, "me": me}
    body = json.dumps({"username": username, "password": password_for(username)}).encode()
    req = urllib.request.Request(f"{CORE}/api/v1/auth/login", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed loopback origin
        cookie = re.search(r"cp_session=([^;]+)", r.headers.get("set-cookie", ""))
        me = json.loads(r.read())
    if not cookie:
        raise RuntimeError("Sign-in returned no session cookie.")
    return {"cookie": cookie.group(1), "me": me}


def add_session(context, username: str = "anne") -> dict:
    """Give a Playwright browser context a signed-in session for `username`."""
    got = login(username)
    context.add_cookies([{"name": "cp_session", "value": got["cookie"], "domain": "127.0.0.1", "path": "/",
                          "httpOnly": True, "sameSite": "Lax"}])
    return got["me"]


def api_get(path: str, cookie: str):
    req = urllib.request.Request(f"{CORE}{path}", headers={"Cookie": f"cp_session={cookie}"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read())


def api_post(path: str, body: dict, cookie: str):
    req = urllib.request.Request(f"{CORE}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Cookie": f"cp_session={cookie}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
        return json.loads(r.read())
