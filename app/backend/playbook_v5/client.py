"""Push a section into a Playbook report from another v5 service (docs/v5/PLAYBOOK_API.md section 2).

    from backend.playbook_v5.client import import_section, explain
    out = import_section(request, body)          # forwards the caller's cp_session; returns the 201 body
    ex = explain("retail", "stage2")             # the policy lookup (section 9); None when Playbook is down
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import HTTPException, Request
from backend.identity_v5.client import cookie_name as _cookie_name


def base() -> str:
    return (os.environ.get("PLAYBOOK_API_ORIGIN") or "http://127.0.0.1:8506").rstrip("/")


def import_section(request: Request, body: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    token = request.cookies.get(_cookie_name()) or ""
    headers = {"Content-Type": "application/json", "Cookie": f"{_cookie_name()}={token}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:80]
    req = urllib.request.Request(base() + "/api/v1/playbook/imports", data=json.dumps(body).encode(), method="POST",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 - fixed loopback origin
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = "Playbook refused the import."
        try:
            detail = json.loads(exc.read() or b"{}").get("detail", detail)
        except ValueError:
            pass
        raise HTTPException(exc.code, detail) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise HTTPException(503, "Playbook is temporarily unavailable. Please try again in a moment.") from exc


def explain(book: str, measure: str, driver: str = "", segment: str = "", period: str = "") -> dict[str, Any] | None:
    q = urllib.parse.urlencode({k: v for k, v in {"book": book, "measure": measure, "driver": driver,
                                                  "segment": segment, "period": period}.items() if v})
    try:
        with urllib.request.urlopen(base() + "/api/v1/policy/explain?" + q, timeout=3) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
