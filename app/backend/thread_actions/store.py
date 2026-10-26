"""Where the thread actions keep what they make (R16 t, M7).

    var/thread_actions/memos/<memo_id>.docx   the Word file      (THREAD_ACTIONS_DIR overrides var/thread_actions)
    var/thread_actions/memos/<memo_id>.json   the document it was written from and its row
    ta_memo, ta_action                        Data Domains relations (backend/thread_actions/relations.py), upsert

Publishing to Data Domains is best effort: a memo is still delivered if the relation write fails (the error is
logged and reported in the response as `recorded: false`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import re
import threading
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)
V5 = pathlib.Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_ID = re.compile(r"^T[MA]-\d{8}-[0-9a-f]{6}$")


def root() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("THREAD_ACTIONS_DIR") or (V5 / "var" / "thread_actions"))
    (p / "memos").mkdir(parents=True, exist_ok=True)
    return p


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def new_id(prefix: str, at: datetime, salt: str) -> str:
    h = hashlib.sha256(f"{prefix}|{stamp(at)}|{salt}|{os.urandom(4).hex()}".encode()).hexdigest()[:6]
    return f"{prefix}-{at:%Y%m%d}-{h}"


def valid_id(memo_id: str) -> bool:
    return bool(_ID.match(memo_id or ""))


def _publish(relation: str, row: dict[str, Any]) -> bool:
    try:
        from backend.dealdesk.data import store as dd
        dd.publish(relation, [row], mode="upsert", actor="t")
        return True
    except Exception as e:  # pragma: no cover - logged, never fatal for the user
        log.warning("thread actions: %s not recorded: %s", relation, e)
        return False


def save_memo(memo_id: str, data: bytes, row: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    d = root() / "memos"
    row = {**row, "memo_id": memo_id, "file_sha256": hashlib.sha256(data).hexdigest(), "file_bytes": len(data)}
    with _LOCK:
        (d / f"{memo_id}.docx").write_bytes(data)
        (d / f"{memo_id}.json").write_text(json.dumps({"row": row, "doc": doc}, ensure_ascii=False, indent=1))
    row["recorded"] = _publish("ta_memo", {k: v for k, v in row.items() if k != "recorded"})
    return row


def memo_file(memo_id: str) -> pathlib.Path | None:
    if not valid_id(memo_id):
        return None
    p = root() / "memos" / f"{memo_id}.docx"
    return p if p.exists() else None


def memo_row(memo_id: str) -> dict[str, Any] | None:
    if not valid_id(memo_id):
        return None
    p = root() / "memos" / f"{memo_id}.json"
    return json.loads(p.read_text())["row"] if p.exists() else None


def memos(module: str = "", thread_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    out = []
    for p in sorted((root() / "memos").glob("TM-*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            r = json.loads(p.read_text())["row"]
        except Exception:
            continue
        if (module and r.get("module") != module) or (thread_id and r.get("thread_id") != thread_id):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def log_action(module: str, thread_id: str, answer_id: str, action: str, target: str, by: str) -> dict[str, Any]:
    at = now()
    row = {"action_id": new_id("TA", at, f"{module}|{thread_id}|{action}"), "module": module, "thread_id": thread_id[:120],
           "answer_id": answer_id[:120], "action": action, "target": target[:300], "created_by": by, "created_at": stamp(at)}
    with _LOCK, (root() / "actions.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    row["recorded"] = _publish("ta_action", {k: v for k, v in row.items() if k != "recorded"})
    return row
