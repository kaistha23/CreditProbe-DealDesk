"""Per-call model telemetry for every domain conversation (Deal Desk edition, model lab).

Every provider step (Anthropic or an OpenAI-compatible server such as vLLM, llama.cpp, LM Studio or MLX) writes one
row through `record()`. The row carries what the model lab needs to compare a run on Opus with the same run on an
open-weight model: who asked (module, domain, thread, run), which stage (`purpose`), which provider and model, the
prompt version (a hash of the system prompt and the tool schemas, so a prompt change is visible as a version change),
the token counts the server reported (input, output, reasoning, cached), wall time, whether the call worked, the
stop reason and the tools the model chose.

Two sinks, both under var/convo (CONVO_TELEMETRY_DIR overrides; tests write under var/pytest):

  llm_calls.jsonl         one JSON line per call -- the file backend/convo/provider.py has always written, with the
                          new columns added (old readers keep working: every old field is still there)
  llm_telemetry.sqlite    the same rows in one table, so `summary()` can aggregate per run, stage and model without
                          re-reading the log; the model lab (ops/model_lab.py) and the telemetry API read this

The key is never read here. Writing never fails a turn.

Context: a turn sets `use(module=..., domain=..., thread_id=..., run_id=...)` around its work (backend/convo/agent.py
does this), so every call made during the turn is tagged with it. `CONVO_EXPERIMENT` (an environment variable, or
`experiment=` on `use`) labels a whole session of runs, e.g. "opus-baseline" or "qwen38-27b-fp8".
"""
from __future__ import annotations

import contextlib
import contextvars
import csv
import hashlib
import io
import json
import os
import pathlib
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

V5 = pathlib.Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_CTX: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("convo_llm_ctx", default={})

COLUMNS = ("call_id", "at", "run_id", "thread_id", "module", "domain", "request_path", "experiment", "purpose", "provider", "model",
           "served_model", "quant", "prompt_version", "input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens",
           "ms", "ttft_ms", "ok", "error", "stop", "tools", "n_messages", "n_tools_offered", "max_tokens")


def directory() -> pathlib.Path:
    if os.environ.get("CONVO_TELEMETRY_DIR"):
        return pathlib.Path(os.environ["CONVO_TELEMETRY_DIR"])
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return V5 / "var" / "pytest" / "telemetry"
    return V5 / "var" / "convo"


def log_path() -> pathlib.Path:
    return directory() / "llm_calls.jsonl"


def db_path() -> pathlib.Path:
    return directory() / "llm_telemetry.sqlite"


# ------------------------------------------------------------------ context

def context() -> dict[str, Any]:
    return dict(_CTX.get())


@contextlib.contextmanager
def use(**ctx: Any) -> Iterator[dict[str, Any]]:
    """Tag every model call made inside the block (module, domain, thread_id, run_id, experiment, ...)."""
    merged = {**_CTX.get(), **{k: v for k, v in ctx.items() if v is not None}}
    merged.setdefault("experiment", os.environ.get("CONVO_EXPERIMENT", ""))
    token = _CTX.set(merged)
    try:
        yield merged
    finally:
        _CTX.reset(token)


def new_run_id() -> str:
    return "AR-" + uuid.uuid4().hex[:10]


def prompt_version(system: str, tools: list[dict[str, Any]]) -> str:
    """A short stable hash of the prompt shape: the system text and the tool names and schemas."""
    h = hashlib.sha1()
    h.update((system or "").encode("utf-8", "replace"))
    for t in tools or []:
        h.update(json.dumps({"n": t.get("name"), "s": t.get("input_schema") or t.get("parameters")}, sort_keys=True,
                            default=str).encode())
    return h.hexdigest()[:12]


# ------------------------------------------------------------------ writing

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
  call_id TEXT PRIMARY KEY, at TEXT, run_id TEXT, thread_id TEXT, module TEXT, domain TEXT, request_path TEXT, experiment TEXT,
  purpose TEXT, provider TEXT, model TEXT, served_model TEXT, quant TEXT, prompt_version TEXT,
  input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, cached_tokens INTEGER,
  ms INTEGER, ttft_ms INTEGER, ok INTEGER, error TEXT, stop TEXT, tools TEXT, n_messages INTEGER,
  n_tools_offered INTEGER, max_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS llm_calls_run ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS llm_calls_exp ON llm_calls(experiment, model);
"""


def _connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=5.0)
    con.executescript(_SCHEMA)
    return con


def record(row: dict[str, Any]) -> dict[str, Any]:
    """Write one call row (the provider's fields merged with the turn context). Returns the full row."""
    ctx = context()
    full: dict[str, Any] = {
        "call_id": "LC-" + uuid.uuid4().hex[:12],
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "run_id": ctx.get("run_id", ""), "thread_id": ctx.get("thread_id", ""), "module": ctx.get("module", ""),
        "domain": ctx.get("domain", ""), "request_path": ctx.get("request_path", ""),
        "experiment": ctx.get("experiment") or os.environ.get("CONVO_EXPERIMENT", ""),
    }
    full.update({k: v for k, v in row.items() if v is not None})
    full.setdefault("ok", True)
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(full, ensure_ascii=False, default=str)
        with _LOCK:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            con = _connect()
            try:
                con.execute(
                    "INSERT OR REPLACE INTO llm_calls (" + ",".join(COLUMNS) + ") VALUES (" + ",".join("?" * len(COLUMNS)) + ")",
                    [_cell(full.get(c)) for c in COLUMNS])
                con.commit()
            finally:
                con.close()
    except Exception:  # noqa: BLE001 - telemetry never fails a model call
        pass
    return full


def _cell(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return v


# ------------------------------------------------------------------ reading

def rows(where: dict[str, Any] | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    if not db_path().exists():
        return []
    con = _connect()
    try:
        con.row_factory = sqlite3.Row
        sql, args = "SELECT * FROM llm_calls", []
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
            args = list(where.values())
        sql += " ORDER BY at DESC LIMIT ?"
        args.append(int(limit))
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def summary(group_by: tuple[str, ...] = ("experiment", "model", "purpose"), where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Calls, tokens and latency aggregated by the given columns (any of COLUMNS)."""
    if not db_path().exists():
        return []
    cols = [c for c in group_by if c in COLUMNS] or ["model"]
    con = _connect()
    try:
        con.row_factory = sqlite3.Row
        sql = ("SELECT " + ", ".join(cols) + ", COUNT(*) AS calls, SUM(ok) AS ok_calls, "
               "SUM(COALESCE(input_tokens,0)) AS input_tokens, SUM(COALESCE(output_tokens,0)) AS output_tokens, "
               "SUM(COALESCE(reasoning_tokens,0)) AS reasoning_tokens, SUM(COALESCE(cached_tokens,0)) AS cached_tokens, "
               "SUM(COALESCE(ms,0)) AS ms, AVG(ms) AS avg_ms, MAX(ms) AS max_ms, COUNT(DISTINCT run_id) AS runs "
               "FROM llm_calls")
        args: list[Any] = []
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
            args = list(where.values())
        sql += " GROUP BY " + ", ".join(cols) + " ORDER BY " + ", ".join(cols)
        out = []
        for r in con.execute(sql, args):
            d = dict(r)
            d["avg_ms"] = round(d["avg_ms"] or 0)
            out.append(d)
        return out
    finally:
        con.close()


def per_run(where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One line per turn (run_id): calls, tokens, wall time of the model calls, and the stages touched."""
    if not db_path().exists():
        return []
    con = _connect()
    try:
        con.row_factory = sqlite3.Row
        sql = ("SELECT run_id, MIN(at) AS at, experiment, module, domain, thread_id, model, provider, COUNT(*) AS calls, "
               "SUM(ok) AS ok_calls, SUM(COALESCE(input_tokens,0)) AS input_tokens, SUM(COALESCE(output_tokens,0)) AS output_tokens, "
               "SUM(COALESCE(reasoning_tokens,0)) AS reasoning_tokens, SUM(COALESCE(ms,0)) AS model_ms, "
               "GROUP_CONCAT(DISTINCT purpose) AS purposes FROM llm_calls")
        args: list[Any] = []
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
            args = list(where.values())
        sql += " GROUP BY run_id ORDER BY MIN(at)"
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def export_csv(where: dict[str, Any] | None = None) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(COLUMNS))
    w.writeheader()
    for r in reversed(rows(where, limit=1_000_000)):
        w.writerow({c: r.get(c) for c in COLUMNS})
    return buf.getvalue()


class Timer:
    """`with Timer() as t:` then `t.ms`."""

    def __enter__(self) -> "Timer":
        self.t0 = time.monotonic()
        self.ms = 0
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ms = int((time.monotonic() - self.t0) * 1000)
