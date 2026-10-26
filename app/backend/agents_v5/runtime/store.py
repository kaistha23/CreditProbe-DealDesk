"""Run, approval and schedule storage (A3).

JSON files under `var/agents_v5/` (override with AGENTS_V5_HOME): one file per run so a run
being written never blocks reading another, plus small JSON tables for approvals and
schedules. Writes are atomic (temp file + rename). The agentic DB tables
(`backend.models.platform.AgentRun/AgentApproval`) are keyed to the Cockpit's analysis runs
and its SQLAlchemy session, which this small service does not run; their semantics are
reused (approvals.ROLE_RANK, may_decide, AlreadyDecided, budgets) rather than their tables.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from backend.agents_v5.runtime.types import Run

V5 = Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()


def home() -> Path:
    p = Path(os.environ.get("AGENTS_V5_HOME") or (V5 / "var" / "agents_v5"))
    (p / "runs").mkdir(parents=True, exist_ok=True)
    return p


def _write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{threading.get_ident()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, default=str, indent=1))
    os.replace(tmp, path)


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ runs

def save_run(run: Run) -> None:
    with _LOCK:
        _write(home() / "runs" / f"{run.run_id}.json", run.to_dict())


def load_run(run_id: str) -> Run | None:
    if not run_id or "/" in run_id or ".." in run_id:
        return None
    d = _read(home() / "runs" / f"{run_id}.json", None)
    return Run.from_dict(d) if d else None


def list_runs(*, agent: str = "", scope: str = "", limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = sorted((home() / "runs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        d = _read(f, None)
        if not d:
            continue
        if agent and d.get("agent") != agent:
            continue
        if scope and d.get("scope") != scope:
            continue
        plan = d.get("plan") or {}
        steps = plan.get("steps") or []
        out.append({"run_id": d["run_id"], "agent": d.get("agent"), "goal": d.get("goal"), "scope": d.get("scope"),
                    "trigger": d.get("trigger"), "status": d.get("status"), "planner": plan.get("planner"),
                    "created_at": d.get("created_at"), "finished_at": d.get("finished_at"),
                    "duration_ms": d.get("duration_ms"), "steps": len(steps),
                    "steps_done": sum(1 for s in steps if s.get("status") == "done"),
                    "findings": len(d.get("findings") or []), "proposals": len(d.get("proposals") or []),
                    "headline": (d.get("output") or {}).get("headline", "")})
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ tables (approvals, schedules)

def table(name: str) -> dict[str, Any]:
    return _read(home() / f"{name}.json", {})


def put(name: str, key: str, row: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        t = table(name)
        t[key] = row
        _write(home() / f"{name}.json", t)
    return row


def update(name: str, key: str, fn) -> dict[str, Any] | None:
    """Read-modify-write one row under the lock; `fn(row)` returns the new row."""
    with _LOCK:
        t = table(name)
        if key not in t:
            return None
        t[key] = fn(dict(t[key]))
        _write(home() / f"{name}.json", t)
        return t[key]


def delete(name: str, key: str) -> bool:
    with _LOCK:
        t = table(name)
        if key not in t:
            return False
        del t[key]
        _write(home() / f"{name}.json", t)
        return True
