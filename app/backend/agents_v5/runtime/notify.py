"""Notifications through the existing path: the Workspace inbox (`kind = notification`),
which feeds the header bell. Best effort: a failed notification never fails a run."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
SENT: list[dict[str, Any]] = []      # the last notifications this process sent (tests, the API)


APPROVER_TITLES = ("administrator", "head of", "chief", "credit officer", "cro", "cco")


def _audience(users: list[str] | tuple[str, ...] | None, audience_role: str) -> list[str]:
    """Named users; else, for an approval, the people who approve (by title); else everyone."""
    if users:
        return list(users)
    try:
        from backend.workspace_v5 import store as ws
        with ws.db() as con:
            rows = [dict(r) for r in ws.users(con)]
        ids = [str(r["id"]) for r in rows]
        if audience_role:
            approvers = [str(r["id"]) for r in rows
                         if any(t in str(r.get("title") or "").lower() for t in APPROVER_TITLES)]
            return approvers or ids[:1]
        return ids
    except Exception:  # noqa: BLE001
        return []


def send(title: str, body: str, href: str, *, users: list[str] | tuple[str, ...] | None = None,
         audience_role: str = "") -> int:
    row = {"title": title[:200], "body": body[:600], "href": href, "users": list(users or []), "role": audience_role}
    SENT.append(row)
    del SENT[:-50]
    if os.environ.get("AGENTS_V5_NOTIFY", "on") == "off":
        return 0
    try:
        from backend.workspace_v5 import store as ws
        targets = _audience(users, audience_role)
        with ws.db() as con:
            for uid in targets:
                ws._add_inbox(con, uid, "notification", row["title"], row["body"], href, None, ws.now(),
                              "agents_v5")
        return len(targets)
    except Exception as e:  # noqa: BLE001 - best effort
        logger.info("agents_v5 notification not delivered: %s", type(e).__name__)
        return 0
