"""Round A: where agent runs live. One JSON per run under var/dealdesk/agent_intake/runs/<run_id>.json, the texts each
document was read into under texts/<intake_id>/<doc>.json (the figure check and a revise read them again), and the original
files under files/<intake_id>/. DEALDESK_AGENT_INTAKE_ROOT overrides the root (tests).

A run in progress is held in memory (the API polls it while the steps run); it is written to disk at each step and
while the draft streams (at most twice a second).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()
LIVE: dict[str, dict[str, Any]] = {}
_LAST: dict[str, float] = {}


class NotFound(KeyError):
    pass


def root() -> Path:
    p = Path(os.environ.get("DEALDESK_AGENT_INTAKE_ROOT") or (V5 / "var" / "dealdesk" / "agent_intake"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(rid: str) -> str:
    if not re.fullmatch(r"AR-[A-Za-z0-9]{6,24}", rid or ""):
        raise NotFound(rid)
    return rid


def path(rid: str) -> Path:
    return root() / "runs" / f"{_safe(rid)}.json"


def save(run: dict[str, Any], force: bool = True) -> None:
    rid = run["run_id"]
    t = time.monotonic()
    if not force and t - _LAST.get(rid, 0) < 0.5:
        return
    _LAST[rid] = t
    with _LOCK:
        p = path(rid)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(run, ensure_ascii=False, default=str))
        tmp.replace(p)


def get(rid: str) -> dict[str, Any]:
    if rid in LIVE:
        return LIVE[rid]
    p = path(rid)
    if not p.exists():
        raise NotFound(rid)
    run = json.loads(p.read_text())
    if run.get("status") in ("queued", "running", "revising"):  # not held by this process: the service stopped mid-run
        run["status"] = "failed" if run.get("status") != "revising" else "done"
        run["error"] = "The run was interrupted (the service restarted). Run the agent again."
        for s in run.get("steps") or []:
            if s.get("status") == "running":
                s["status"] = "failed"
        if (run.get("draft") or {}).get("status") == "streaming":
            run["draft"]["status"] = "done"
            run["draft"]["text"] = run["draft"].get("md") or ""
        save(run)
    return run


def listing(limit: int = 20, proposal_id: str = "") -> list[dict[str, Any]]:
    d = root() / "runs"
    out = []
    for p in sorted(d.glob("AR-*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if d.exists() else []:
        try:
            r = json.loads(p.read_text())
        except ValueError:
            continue
        if proposal_id and r.get("proposal_id") != proposal_id:
            continue
        out.append({k: r.get(k) for k in ("run_id", "parent_run_id", "intake_id", "proposal_id", "customer", "created_at", "status", "market")}
                   | {"documents_n": len(r.get("documents") or []), "completeness": ((r.get("check") or {}).get("comp") or {}).get("pct")})
        if len(out) >= limit:
            break
    return out


def texts_dir(iid: str) -> Path:
    p = root() / "texts" / re.sub(r"[^A-Za-z0-9\-]", "_", iid)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_pages(iid: str, doc_id: str, pages: list[str]) -> None:
    (texts_dir(iid) / f"{doc_id}.json").write_text(json.dumps(pages, ensure_ascii=False))


def pages(iid: str, doc_id: str) -> list[str]:
    p = texts_dir(iid) / f"{doc_id}.json"
    return json.loads(p.read_text()) if p.exists() else []


def files_dir(iid: str) -> Path:
    p = root() / "files" / re.sub(r"[^A-Za-z0-9\-]", "_", iid)
    p.mkdir(parents=True, exist_ok=True)
    return p
