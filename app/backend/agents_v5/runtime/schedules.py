"""Scheduled runs (A6).

`schedule(agent, cron, goal, context)` stores a schedule. `cron` is a 5-field cron expression
(minute hour day-of-month month day-of-week, UTC; `*`, lists, ranges and `*/n`) or an event
trigger `@after:<event>` (for example `@after:ews_refresh`), fired by `fire_event(event)`.
`tick(now)` runs what is due (once per matching minute); the API runs it on a background
thread. Scheduled runs use the deterministic planner unless the schedule says otherwise and
notify through the existing notification path when they finish.

`backend.agentic.schedules` is cadence-based (monthly, on publish) and DB-backed for the
Cockpit's proactive review; its cadence words are accepted here as aliases.
"""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from typing import Any

from backend.agents_v5.runtime import store
from backend.agents_v5.runtime.agents import get_agent
from backend.agents_v5.runtime.types import new_id, now_iso

TABLE = "schedules"
ALIASES = {"daily": "0 5 * * *", "weekly": "0 5 * * 1", "monthly": "0 5 1 * *", "quarterly": "0 5 1 1,4,7,10 *"}
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]


class CronInvalid(ValueError):
    pass


def _field(spec: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
            if step < 1:
                raise CronInvalid("step must be >= 1")
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a < lo or b > hi or a > b:
            raise CronInvalid(f"{part} is outside {lo}-{hi}")
        out.update(range(a, b + 1, step))
    return out


def parse(cron: str) -> list[set[int]] | str:
    cron = ALIASES.get(cron.strip().lower(), cron.strip())
    if cron.startswith("@after:"):
        if len(cron) <= 7:
            raise CronInvalid("an event name is needed after @after:")
        return cron
    parts = cron.split()
    if len(parts) != 5:
        raise CronInvalid("five fields: minute hour day-of-month month day-of-week")
    try:
        return [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _RANGES, strict=True)]
    except ValueError as e:
        raise CronInvalid(str(e)) from None


def matches(cron: str, at: datetime) -> bool:
    p = parse(cron)
    if isinstance(p, str):
        return False
    dow = (at.weekday() + 1) % 7   # cron: Sunday = 0
    return at.minute in p[0] and at.hour in p[1] and at.day in p[2] and at.month in p[3] and dow in p[4]


def schedule(agent: str, cron: str, goal: str, context: dict[str, Any] | None = None, *, planner: str = "deterministic",
             user: str = "", enabled: bool = True) -> dict[str, Any]:
    if get_agent(agent) is None:
        raise KeyError(f"No agent {agent!r}.")
    parse(cron)
    sid = new_id("sch")
    row = {"id": sid, "agent": agent, "cron": cron, "goal": goal, "context": dict(context or {}), "planner": planner,
           "user": user, "enabled": enabled, "created_at": now_iso(), "last_fired": "", "last_run": "", "runs": 0}
    return store.put(TABLE, sid, row)


def listing(agent: str = "") -> list[dict[str, Any]]:
    return [r for r in store.table(TABLE).values() if not agent or r["agent"] == agent]


def set_enabled(sid: str, enabled: bool) -> dict[str, Any] | None:
    return store.update(TABLE, sid, lambda r: {**r, "enabled": bool(enabled)})


def remove(sid: str) -> bool:
    return store.delete(TABLE, sid)


def _fire(row: dict[str, Any], stamp: str, *, background: bool) -> str:
    from backend.agents_v5.runtime import executor
    run = executor.start(row["agent"], row["goal"], row.get("context") or {}, planner_mode=row.get("planner") or
                         "deterministic", trigger="scheduled", user="", background=background)
    store.update(TABLE, row["id"], lambda r: {**r, "last_fired": stamp, "last_run": run.run_id,
                                              "runs": int(r.get("runs", 0)) + 1})
    return run.run_id


def tick(at: datetime | None = None, *, background: bool = True) -> list[str]:
    at = (at or datetime.now(UTC)).replace(second=0, microsecond=0)
    stamp = at.strftime("%Y-%m-%dT%H:%M")
    fired = []
    for row in listing():
        if not row.get("enabled") or row.get("last_fired") == stamp:
            continue
        try:
            if matches(row["cron"], at):
                fired.append(_fire(row, stamp, background=background))
        except CronInvalid:
            continue
    return fired


def fire_event(event: str, *, background: bool = True) -> list[str]:
    """Run every enabled schedule bound to `@after:<event>` (e.g. after an EWS refresh)."""
    stamp = now_iso()
    return [_fire(r, stamp, background=background) for r in listing()
            if r.get("enabled") and r["cron"] == f"@after:{event}"]


_THREAD: threading.Thread | None = None


def start_ticker(interval_s: float = 30.0) -> None:
    global _THREAD
    if _THREAD is not None:
        return

    def _loop() -> None:
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001 - the ticker never dies
                pass
            time.sleep(interval_s)

    _THREAD = threading.Thread(target=_loop, name="agents-v5-scheduler", daemon=True)
    _THREAD.start()
