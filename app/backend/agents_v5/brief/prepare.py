"""The brief before the working day (I11: "scheduled before the working day").

    .venv/bin/python -m backend.agents_v5.brief.prepare [--date 2026-10-19] [--no-notify]

Builds each signed-up person's brief for their own role (the directory in `backend.identity_v5.directory`), keeps it
under `var/noor/prepared/<date>/<username>.json`, and drops one notification in their bell ("Your brief for today: …")
that opens Noor's panel on the brief (`/?noor=brief`). Run it from the Mac's scheduler (launchd or cron) at 06:30, or
press "Prepare today's briefs" (`POST /api/v1/noor/brief/prepare`, administrator). Deterministic (N6); no model call.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any

from backend.agents_v5.brief import service


def people() -> list[dict[str, Any]]:
    from backend.identity_v5.directory import seed_users
    return seed_users()


def prepare(today: date | None = None, *, notify: bool = True, hour: int = 7) -> dict[str, Any]:
    today = today or date.today()
    folder = service.home() / "prepared" / today.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    done: list[dict[str, Any]] = []
    for u in people():
        b = service.brief(role=str(u.get("role") or ""), user=u, today=today, hour=hour)
        (folder / f"{u['username']}.json").write_text(json.dumps(b, ensure_ascii=False, default=str))
        sent = 0
        if notify and b["items"]:
            from backend.agents_v5.runtime import notify as N
            first = b["items"][0]["title"]
            sent = N.send(f"{b['assistant']}: your brief for {b['date_label']}",
                          f"{len(b['items'])} things today. First: {first}", "/?noor=brief", users=[u["username"]])
        done.append({"username": u["username"], "persona": b["persona"], "lines": len(b["items"]), "more": b["n_more"],
                     "notified": bool(sent)})
    return {"date": today.isoformat(), "people": done}


def prepared(username: str, today: date | None = None) -> dict[str, Any] | None:
    p = service.home() / "prepared" / (today or date.today()).isoformat() / f"{username}.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args()
    out = prepare(date.fromisoformat(a.date) if a.date else None, notify=not a.no_notify)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
