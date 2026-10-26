"""Runtime state of the proposal check: uploaded proposals (var/dealdesk/proposal_check/uploads), the last result per deal
(cache), the "Send back to RM" log, and publishing results to Data Domains (dd_proposal_quality, upsert by quality_id).

Nothing here is read as data by the checks themselves except the uploaded Word files (the RM's paper).
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
from datetime import datetime, timezone
from typing import Any

V5 = pathlib.Path(__file__).resolve().parents[3]
ROOT = pathlib.Path(os.environ.get("PROPOSAL_CHECK_STATE") or (V5 / "var" / "dealdesk" / "proposal_check"))
_LOCK = threading.Lock()
_CACHE: dict[str, dict[str, Any]] = {}


def _dir(*p: str) -> pathlib.Path:
    d = ROOT.joinpath(*p)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(pid: str, name: str, data: bytes) -> pathlib.Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:80] or "proposal.docx"
    p = _dir("uploads", pid) / safe
    p.write_bytes(data)
    (_dir("uploads", pid) / "_latest.txt").write_text(safe)
    return p


def latest_upload(pid: str) -> tuple[bytes, str] | None:
    d = ROOT / "uploads" / pid
    f = d / "_latest.txt"
    if not f.exists():
        return None
    p = d / f.read_text().strip()
    return (p.read_bytes(), p.name) if p.exists() else None


def remember(res: dict[str, Any]) -> None:
    with _LOCK:
        _CACHE[res["proposal_id"]] = res


def last(pid: str) -> dict[str, Any] | None:
    return _CACHE.get(pid)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def send_back(pid: str, run_id: str, queries: list[dict[str, Any]], to: str, by: str = "credit reviewer") -> dict[str, Any]:
    rec = {"proposal_id": pid, "run_id": run_id, "to": to, "by": by, "at": now(), "queries": queries}
    with _LOCK:
        p = _dir() / "sent.jsonl"
        with p.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def sent(pid: str | None = None) -> list[dict[str, Any]]:
    p = ROOT / "sent.jsonl"
    if not p.exists():
        return []
    out = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return [r for r in out if pid is None or r["proposal_id"] == pid]


def publish(rows: list[dict[str, Any]], actor: str = "p:proposal-check") -> dict[str, Any]:
    """Upsert the rows into dd_proposal_quality (Data Domains). Best-effort: a publishing problem never fails the check."""
    try:
        from backend.dealdesk.data import store
        return store.publish("dd_proposal_quality", rows, mode="upsert", actor=actor)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
