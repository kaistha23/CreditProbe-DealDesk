"""My workspace as each user's home page (PLAN_R3 S3-4): what is waiting on me, in one read.

`GET /api/v1/workspace/home` gathers, for the signed-in (effective) user:

  tasks        open project tasks assigned to me, and unread assignments from the inbox
  mentions     the latest mentions of me
  mail         unread count and the latest unread conversations
  mine         my analyses, investigations and projects (owned or member)
  recent       the most recently changed items I can see, across kinds
  books        the books I cover (the page reads the Early Warning alerts and the Playbook
               reviews for them from their own services)

Nothing here duplicates a page: every row is a link into the page that owns it, and each list is
short (the page owns the full list).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from backend.workspace_v5 import store
from backend.identity_v5.client import cookie_name as _cookie_name

LIST = 6


def _when(item: dict[str, Any]) -> str:
    return item.get("updated_at") or item.get("created_at") or ""


def _ids(people: list[dict[str, Any] | None]) -> set[str]:
    return {p["id"] for p in people if p}


def build(con, me: str, user: dict[str, Any], projects: list[dict[str, Any]], investigations: list[dict[str, Any]],
          analyses: list[dict[str, Any]], documents: list[dict[str, Any]]) -> dict[str, Any]:
    um = store.user_map(con)
    visible_projects = {p["id"]: p for p in projects}
    tasks = []
    for r in con.execute("SELECT i.*, p.name AS project_name FROM project_items i JOIN projects p ON p.id = i.project_id "
                         "WHERE i.assignee_id=? AND i.status != 'done' ORDER BY i.status DESC, i.position, i.id", (me,)):
        if r["project_id"] not in visible_projects:
            continue
        tasks.append({"id": int(r["id"]), "title": r["title"], "detail": r["detail"], "status": r["status"],
                      "project": {"id": r["project_id"], "name": r["project_name"]},
                      "href": r["href"] or f"/projects/{r['project_id']}", "link_label": r["link_label"]})
    inbox = store.inbox(con, me)
    items = inbox["items"]
    assignments = [i for i in items if i["kind"] == "assignment"][:LIST]
    mentions = [i for i in items if i["kind"] == "mention"][:LIST]
    unread_mail = [i for i in items if i["kind"] == "message" and not i["read"]][:LIST]
    counts = store.mail_counts(me)

    def mine(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        out = []
        for r in rows:
            owner = (r.get("owner") or {}).get("id")
            if owner == me or me in _ids(r.get("members") or []):
                out.append({"id": r["id"], "title": r.get("title") or r.get("name"), "kind": kind,
                            "status": r.get("status"), "period": r.get("period"), "owner": r.get("owner"),
                            "when": _when(r), "href": f"/{kind}s/{r['id']}" if kind != "analysis" else f"/analyses/{r['id']}"})
        return sorted(out, key=lambda x: x["when"], reverse=True)

    recent = []
    for kind, rows, title_key, base in (("project", projects, "name", "/projects/"),
                                        ("investigation", investigations, "title", "/investigations/"),
                                        ("analysis", analyses, "title", "/analyses/"),
                                        ("document", documents, "title", "/documents/")):
        for r in rows:
            recent.append({"id": r["id"], "kind": kind, "title": r.get(title_key) or r.get("title") or r.get("name"),
                           "owner": r.get("owner"), "when": _when(r), "href": base + r["id"]})
    recent.sort(key=lambda x: (x["when"], x["id"]), reverse=True)
    my_projects = mine(projects, "project")
    return {
        "user": {**um.get(me, {"id": me}), "books": user.get("books") or ["corporate", "retail"],
                 "team": user.get("team"), "role": user.get("role")},
        "tasks": {"open": tasks, "assignments": assignments,
                  "total": len(tasks) + sum(1 for a in assignments if not a["read"])},
        "mentions": {"items": mentions, "unread": inbox["unread"].get("mention", 0)},
        "mail": {"unread": counts.get("unread", inbox["unread"].get("message", 0)), "items": unread_mail},
        "mine": {"analyses": mine(analyses, "analysis")[:LIST], "investigations": mine(investigations, "investigation")[:LIST],
                 "projects": my_projects[:LIST],
                 "counts": {"analyses": len(mine(analyses, "analysis")),
                            "investigations": len(mine(investigations, "investigation")),
                            "projects": len(my_projects)}},
        "recent": recent[:8],
    }


def playbook_origin() -> str:
    return (os.environ.get("PLAYBOOK_API_ORIGIN") or "http://127.0.0.1:8506").rstrip("/")


def reviews(token: str, me: str) -> dict[str, Any]:
    """Playbook reports in review where I am a reviewer (docs/v5/PLAYBOOK_API.md), read with my session.

    Playbook is its own service; when it cannot be reached the home page says so instead of failing.
    """
    def get(path: str) -> Any:
        req = urllib.request.Request(playbook_origin() + path, headers={"Cookie": f"{_cookie_name()}={token}"})
        with urllib.request.urlopen(req, timeout=4) as r:  # noqa: S310 - fixed loopback origin
            return json.loads(r.read().decode("utf-8"))
    try:
        listed = get("/api/v1/playbook/reports?status=in_review").get("reports", [])
    except Exception:  # noqa: BLE001 - Playbook down or not deployed
        return {"available": False, "items": []}
    items = []
    for rep in listed[:30]:
        try:
            full = get(f"/api/v1/playbook/reports/{urllib.request.quote(rep['id'])}")
        except Exception:  # noqa: BLE001
            continue
        names = [x if isinstance(x, str) else (x or {}).get("username") for x in full.get("reviewers") or []]
        if me in names:
            items.append({"id": rep["id"], "title": rep.get("title"), "status": rep.get("status"),
                          "due_date": rep.get("due_date"), "owner": rep.get("owner"),
                          "href": rep.get("href") or f"/playbook?report={rep['id']}"})
    return {"available": True, "items": items}
