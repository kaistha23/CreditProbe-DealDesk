"""Workflow items and approvals reach people where they work (PLAN_R5 A1): each open workflow item and each change
waiting for an approver becomes an assignment in the assignee's My workspace (the Workspace inbox) and a notification
in Mail (the bell). Delivered once; written straight into the Workspace and Core stores on this machine.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from backend.admin import store

PAGE = {"policy": "/workflow?tab=access", "workflow": "/workflow?tab=workflows", "user": "/users", "studio": "/ai-studio",
        "setting": "/settings", "param": "/settings", "role": "/users", "team": "/users"}


def _delivered(con: sqlite3.Connection) -> set[str]:
    r = con.execute("SELECT value FROM meta WHERE key='notified'").fetchone()
    return set(json.loads(r["value"])) if r else set()


def _save(con: sqlite3.Connection, done: set[str]) -> None:
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('notified', ?)", (json.dumps(sorted(done)),))


def _messages(con: sqlite3.Connection) -> list[tuple[str, str, str, str, str, str]]:
    """(key, username, title, body, href, actor) for everything that should be on someone's desk now."""
    out = []
    for it in store.items(con):
        if it.get("status") != "open":
            continue
        who = it.get("escalated_to") or it.get("assignee")
        out.append((f"item:{it['item_id']}:{who}", who, it["title"], f"Due {it['due_at'][:10]} ({it['workflow_id']}).",
                    "/workflow?tab=items", "anne"))
    approvers = [u["id"] for u in store.live_list(con, "user") if u["body"].get("role") in store.APPROVER_ROLES
                 and u["body"].get("status") == "active"]
    for ch in store.changes(con, status="submitted"):
        for a in approvers:
            if a != ch["maker"]:
                out.append((f"change:{ch['change_id']}:{a}", a, f"Approve: {ch['title']}",
                            f"{ch['kind_label']} change {ch['change_id']} by {ch['maker']} waits for a second approver.",
                            PAGE.get(ch["kind"], "/workflow"), ch["maker"]))
    return out


def deliver() -> int:
    """Deliver what is not delivered yet. Never fails the caller; returns how many were delivered."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("WORKSPACE_STORE"):
        return 0   # a test never writes into the machine's real Workspace store
    try:
        from backend.identity_v5 import store as ids
        from backend.workspace_v5 import store as ws
        with store.db() as con:
            done = _delivered(con)
            todo = [m for m in _messages(con) if m[0] not in done]
            if not todo:
                return 0
            at = store.now()
            with ws.db() as wcon:
                for key, user, title, body, href, actor in todo:
                    ws._add_inbox(wcon, user, "assignment", title, body, href, actor, at, "admin")  # noqa: SLF001
            with ids.db() as ccon:
                for key, user, title, body, href, actor in todo:
                    ccon.execute("INSERT INTO mail_notifications(username, kind, title, href, from_user, thread_id, created_at)"
                                 " VALUES(?,?,?,?,?,?,?)", (user, "assignment", title[:240], href, actor, None, at))
            _save(con, done | {m[0] for m in todo})
            return len(todo)
    except Exception:  # noqa: BLE001 - delivery is best effort; the items stay listed on Workflow -> Live items
        return 0


def summary() -> dict[str, Any]:
    with store.db() as con:
        return {"delivered": len(_delivered(con))}
