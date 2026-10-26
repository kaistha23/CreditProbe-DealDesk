"""Calculation traces: every engine response carries a trace ID; the trace keeps its inputs,
parameter versions, model version and outputs (var/dealdesk/dealdesk.sqlite)."""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk import paths

_LOCK = threading.Lock()


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.execute("CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, call TEXT, created TEXT, body TEXT)")
    return con


def record(call: str, inputs: dict[str, Any], outputs: Any, param_versions: dict[str, str] | None = None,
           model_version: str | None = None, user: str = "") -> str:
    tid = "DT-" + secrets.token_hex(6)
    body = {"trace_id": tid, "call": call, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "user": user, "inputs": inputs, "param_versions": param_versions or {}, "model_version": model_version,
            "outputs": outputs}
    with _LOCK:
        con = _db()
        try:
            con.execute("INSERT INTO traces VALUES (?, ?, ?, ?)", (tid, call, body["created"], json.dumps(body, default=str)))
            con.commit()
        finally:
            con.close()
    return tid


def get(tid: str) -> dict[str, Any] | None:
    with _LOCK:
        con = _db()
        try:
            row = con.execute("SELECT body FROM traces WHERE id = ?", (tid,)).fetchone()
        finally:
            con.close()
    return json.loads(row[0]) if row else None
