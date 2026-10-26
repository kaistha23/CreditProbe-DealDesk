"""The profile state, the learning events and the drafts (var/dealdesk/house_style, git-ignored).

The committed corpus (memos, cases, exemplars) is re-read when it changes (`corpus.fingerprint`); uploads and RM edits are
events appended to events.jsonl and applied to the cached state as they arrive (the incremental update). A rebuild
replays the corpus and every event, so the result is the same either way.
"""
from __future__ import annotations

import json
import pathlib
import threading
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.house_style import corpus, profile, retrieve

_LOCK = threading.RLock()
_CACHE: dict[str, Any] = {}


def root() -> pathlib.Path:
    return paths.VAR / "house_style"


def _events_path() -> pathlib.Path:
    return root() / "events.jsonl"


def events() -> list[dict[str, Any]]:
    f = _events_path()
    if not f.exists():
        return []
    out = []
    for line in f.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _load() -> dict[str, Any]:
    with _LOCK:
        fp = corpus.fingerprint() + "|" + str(paths.VAR)
        if _CACHE.get("fp") != fp:
            docs = corpus.load(include_uploads=False)
            evs = events()
            state = profile.build(docs, evs)
            _CACHE.clear()
            _CACHE.update({"fp": fp, "docs": docs + [e["doc"] for e in evs if e.get("type") == "doc"], "state": state,
                           "index": None, "n_events": len(evs)})
        return _CACHE


def state() -> dict[str, Any]:
    return _load()["state"]


def corpus_docs() -> list[dict[str, Any]]:
    return _load()["docs"]


def state_key() -> str:
    c = _load()
    return f"{c['fp']}|{c['n_events']}"


def corpus_key() -> str:
    """Changes only when a document is added (the band of the house's own memos does not move with RM edits)."""
    c = _load()
    return f"{c['fp']}|{len(c['docs'])}"


def index() -> retrieve.Index:
    c = _load()
    if c.get("index") is None:
        c["index"] = retrieve.Index(c["docs"])
    return c["index"]


def reset() -> None:
    with _LOCK:
        _CACHE.clear()
        from backend.dealdesk.house_style import fidelity
        fidelity._BAND_CACHE.clear()


def record(ev: dict[str, Any]) -> dict[str, Any]:
    """Append a learning event and apply it to the cached state (incremental)."""
    with _LOCK:
        c = _load()
        root().mkdir(parents=True, exist_ok=True)
        with _events_path().open("a") as fh:
            fh.write(json.dumps(ev) + "\n")
        profile.apply_event(c["state"], ev)
        c["n_events"] += 1
        if ev.get("type") == "doc":
            c["docs"].append(ev["doc"])
            c["index"] = None
        return c["state"]


# ---------------------------------------------------------------------------------------------- drafts

def _draft_path(did: str) -> pathlib.Path:
    safe = "".join(ch for ch in did if ch.isalnum() or ch in "-_")
    return root() / "drafts" / f"{safe}.json"


_DRAFT_LOCKS: dict[str, threading.RLock] = {}


def draft_lock(did: str) -> threading.RLock:
    """One draft's read-modify-write is serialised (a slow regenerate and an accept never overwrite each other)."""
    with _LOCK:
        return _DRAFT_LOCKS.setdefault(did, threading.RLock())


def save(d: dict[str, Any]) -> dict[str, Any]:
    import os
    import tempfile
    p = _draft_path(d["draft_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(d))
    os.replace(tmp, p)  # atomic: a reader never sees half a draft
    return d


def get(did: str) -> dict[str, Any] | None:
    p = _draft_path(did)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except ValueError:
        return None


def latest(pid: str) -> dict[str, Any] | None:
    d = root() / "drafts"
    if not d.exists():
        return None
    best: tuple[tuple[str, int], dict[str, Any]] | None = None
    for f in d.glob("*.json"):
        try:
            x = json.loads(f.read_text())
        except ValueError:
            continue
        if x.get("proposal_id") == pid:
            rank = (x.get("created", ""), f.stat().st_mtime_ns)
            if best is None or rank > best[0]:
                best = (rank, x)
    return best[1] if best else None
