"""The demo session: upload, the six visible steps (each timed), and the wipe on exit.

    s = session.start(("proposal.pdf", b"..."), ("policy.docx", b"..."), mode="deterministic")
    for step in session.STEP_KEYS[1:]:
        session.run_step(s["session_id"], step)
    session.wipe(s["session_id"])              # every file and row of the session removed

Everything a session writes is under var/dealdesk/try_docs/<sid>/ except what the engines it calls write for the demo
deal (the deal row, review conditions, the review memo, the house-style draft, caches); `wipe` finds and removes those
by the deal id and the borrower's name. Sessions older than TTL_HOURS are wiped when the next one starts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.try_docs import deal as D
from backend.dealdesk.try_docs import reader as R

TTL_HOURS = 4
STEPS = [
    ("read", "Read your documents"),
    ("policy", "Learn your policy"),
    ("extract", "Extract the proposal into a deal"),
    ("review", "Review against your policy"),
    ("counter", "Counter-proposal and committee paper"),
    ("draft", "Draft in your memo's language"),
]
STEP_KEYS = [k for k, _ in STEPS]
MODES = ("deterministic", "model")
_LOCK = threading.RLock()

NOTICE = ("Confidential demo session. Your documents are read on this laptop only (CreditProbe runs locally, not in "
          "the cloud) and nothing is sent anywhere in no-model mode. The session keeps its files in one folder and the demo "
          "deal in the local store; both are wiped when you leave (Exit and wipe), and any session left open is wiped after "
          f"{TTL_HOURS} hours. The learned policy is a demo-only version: it changes nothing in the bank's parameters unless a "
          "checker approves it.")
MODEL_NOTICE = ("Model mode: the draft wording is polished by the language model through the Anthropic API, so the draft text "
                "leaves this laptop. Use no-model mode for sensitive documents.")


class SessionError(ValueError):
    pass


def root() -> Path:
    return paths.VAR / "try_docs" / "sessions"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def model_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def capabilities() -> dict[str, Any]:
    ocr = R.ocr_status()
    return {"notice": NOTICE, "model_notice": MODEL_NOTICE, "model_available": model_available(), "modes": list(MODES),
            "default_mode": "deterministic", "ocr": ocr, "accepted": list(R.ACCEPTED), "steps": [{"key": k, "label": lb} for k, lb in STEPS],
            "fallback": fallback_files(), "ttl_hours": TTL_HOURS, "integrations": integrations()}


def integrations() -> dict[str, str]:
    """Which engines a run uses: Session B's review and F's committee paper when merged, else the R11 ones."""
    from backend.dealdesk.try_docs import engines
    return engines.which()


def fallback_files() -> dict[str, Any]:
    """The prepared fallback case: the fictional twin proposals and Session O's fictional policy."""
    from backend.dealdesk.try_docs import rehearse
    return rehearse.fallback()


# ------------------------------------------------------------------ state

def _dir(sid: str) -> Path:
    if not re.fullmatch(r"TRYS-\d{14}-[0-9a-f]{8}", sid):
        raise SessionError("No such demo session.")
    return root() / sid


def _save(s: dict[str, Any]) -> None:
    d = _dir(s["session_id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.json.tmp"
    tmp.write_text(json.dumps(s, ensure_ascii=False, default=str))
    tmp.replace(d / "state.json")


def get(sid: str) -> dict[str, Any]:
    f = _dir(sid) / "state.json"
    if not f.exists():
        raise SessionError("No such demo session (it may have been wiped).")
    return json.loads(f.read_text())


def _upload(sid: str, kind: str) -> tuple[str, bytes]:
    d = _dir(sid) / "uploads"
    s = get(sid)
    name = s["documents"][kind]["name"]
    return name, (d / f"{kind}{Path(name).suffix.lower()}").read_bytes()


def view(s: dict[str, Any]) -> dict[str, Any]:
    """The session as the UI shows it (no uploaded bytes, no internal paths)."""
    steps = s["steps"]
    done = [st for st in steps.values() if st["status"] == "done"]
    return {"session_id": s["session_id"], "created_at": s["created_at"], "mode": s["mode"], "notice": NOTICE,
            "model_notice": MODEL_NOTICE if s["mode"] == "model" else None,
            "documents": {k: {kk: vv for kk, vv in v.items() if kk != "text"} for k, v in s["documents"].items()},
            "deal_id": s.get("deal_id"), "steps": [steps[k] for k in STEP_KEYS],
            "next": next((k for k in STEP_KEYS if steps[k]["status"] in ("pending", "error")), None),
            "total_seconds": round(sum(st.get("seconds") or 0 for st in done), 2),
            "complete": all(steps[k]["status"] == "done" for k in STEP_KEYS)}


# ------------------------------------------------------------------ start

def start(proposal: tuple[str, bytes], policy: tuple[str, bytes] | None, mode: str = "deterministic", by: str = "") -> dict[str, Any]:
    if mode not in MODES:
        raise SessionError("mode is deterministic (no model) or model.")
    if mode == "model" and not model_available():
        mode = "deterministic"
    sweep()
    t0 = time.perf_counter()
    key = hashlib.sha256(proposal[1] + (policy[1] if policy else b"")).hexdigest()[:4] + os.urandom(2).hex()
    sid = f"TRYS-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{key}"
    docs: dict[str, Any] = {}
    errors: list[str] = []
    for kind, f in (("proposal", proposal), ("policy", policy)):
        if f is None:
            continue
        try:
            r = R.read(*f)
        except R.ReadError as e:
            errors.append(str(e))
            continue
        docs[kind] = {**r, "kind": kind, "sha256": hashlib.sha256(f[1]).hexdigest(), "bytes": len(f[1])}
    if "proposal" not in docs:
        raise SessionError(errors[0] if errors else "Upload a proposal.")
    d = _dir(sid)
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    for kind, f in (("proposal", proposal), ("policy", policy)):
        if f is not None and kind in docs:
            (d / "uploads" / f"{kind}{Path(f[0]).suffix.lower()}").write_bytes(f[1])
    sec = round(time.perf_counter() - t0, 2)
    steps = {k: {"key": k, "label": lb, "status": "pending", "seconds": None, "summary": "", "result": None} for k, lb in STEPS}
    lang = docs["proposal"]["language"]
    steps["read"].update(status="done", seconds=sec, result={"documents": [
        {"kind": k, "name": v["name"], "method": v["method"], "pages": v["pages"], "language": v["language"], "characters": v["characters"]}
        for k, v in docs.items()], "errors": errors},
        summary=f"Read {docs['proposal']['name']} ({docs['proposal']['method']}, {'Arabic' if lang == 'ar' else 'English'}, "
                f"{docs['proposal']['characters']:,} characters)"
                + (f" and {docs['policy']['name']} ({docs['policy']['method']})" if "policy" in docs else "; no policy uploaded: CreditProbe defaults apply")
                + (f". {' '.join(errors)}" if errors else "."))
    if "policy" not in docs:
        steps["policy"].update(status="done", seconds=0.0, summary="No policy uploaded: every parameter uses the CreditProbe default, labelled.",
                               result=None)
    s = {"session_id": sid, "created_at": _now(), "by": by, "mode": mode, "documents": docs, "steps": steps, "deal_id": None,
         "borrower_name": None}
    with _LOCK:
        _save(s)
    if "policy" not in docs:
        from backend.dealdesk.try_docs import policy as PO
        s["steps"]["policy"]["result"] = PO.defaults_only()
        _save(s)
    return view(s)


# ------------------------------------------------------------------ steps

def run_step(sid: str, step: str) -> dict[str, Any]:
    if step not in STEP_KEYS or step == "read":
        raise SessionError(f"Unknown step {step}.")
    with _LOCK:
        s = get(sid)
        i = STEP_KEYS.index(step)
        before = [k for k in STEP_KEYS[:i] if s["steps"][k]["status"] != "done"]
        if before:
            raise SessionError(f"Run {s['steps'][before[0]]['label'].lower()} first.")
        st = s["steps"][step]
        st.update(status="running")
        t0 = time.perf_counter()
        try:
            result, summary = _RUN[step](s)
            st.update(status="done", result=result, summary=summary, error=None)
        except Exception as e:  # noqa: BLE001 - a step that fails says why; the session stays usable
            st.update(status="error", error=str(e) or type(e).__name__, summary=f"Could not {st['label'].lower()}: {e}")
        st["seconds"] = round(time.perf_counter() - t0, 2)
        _save(s)
        return view(s)


def run_all(sid: str) -> dict[str, Any]:
    v = get_view(sid)
    for k in STEP_KEYS[1:]:
        if get(sid)["steps"][k]["status"] != "done":
            v = run_step(sid, k)
            if get(sid)["steps"][k]["status"] != "done":
                break
    return v


def get_view(sid: str) -> dict[str, Any]:
    return view(get(sid))


def _policy(s: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from backend.dealdesk.try_docs import policy as PO
    name, data = _upload(s["session_id"], "policy")
    r = PO.learn(name, data, s["documents"]["policy"])
    from backend.dealdesk.try_docs import engines
    r["published"] = engines.publish_demo_policy(s["session_id"], r, name)
    return r, r["summary"]


def _extract(s: dict[str, Any]) -> tuple[dict[str, Any], str]:
    name, data = _upload(s["session_id"], "proposal")
    b = D.build(s["documents"]["proposal"], data, s["session_id"])
    pid = D.save(b["proposal"], s["session_id"])
    s["deal_id"] = pid
    s["borrower_name"] = b["proposal"]["obligor"]["name"]
    p = b["proposal"]
    from backend.dealdesk.try_docs import engines
    pub = engines.publish_demo_deal({**p, "proposal_id": pid}, s["session_id"])
    from backend.dealdesk.try_docs import memo
    memo.save_review_memo(pid, s["documents"]["proposal"], data)
    a = p["ask"]
    read = [f for f in b["fields"]]
    summary = (f"{p['obligor']['name']}: {p['obligor']['sector']}, rated {p['obligor']['internal_rating']}; "
               f"{a['currency']} {a['amount']:,.1f}m {a['facility_type'].replace('_', ' ')}, {a['tenor_years']} year"
               f"{'s' if a['tenor_years'] != 1 else ''}, {a['margin_bps']} bps. {len(read)} fields read, {len(b['defaults'])} defaults labelled.")
    return {"deal_id": pid, "fields": read, "defaults": b["defaults"], "lines": b["lines"], "currency_in_proposal": b["currency"],
            "aed_sar": b["aed_sar"], "assumed": p.get("assumed", []), "published": pub,
            "deal": {"name": p["obligor"]["name"], "sector": p["obligor"]["sector"], "rating": p["obligor"]["internal_rating"],
                     "facility_type": a["facility_type"], "currency": a["currency"], "amount": a["amount"], "tenor_years": a["tenor_years"],
                     "margin_bps": a["margin_bps"], "funded_share_pct": a["funded_share_pct"],
                     "financials": p["financials"]["years"][-1]}}, summary


def _review(s: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from backend.dealdesk.try_docs import engines
    pol = s["steps"]["policy"].get("result") or {}
    ex = s["steps"]["extract"].get("result") or {}
    r = engines.review(s["deal_id"], pol.get("rules", []), [d["field"] for d in ex.get("defaults", [])])
    r["published"] = engines.publish_demo_findings(s["session_id"], s["deal_id"], r)
    return r, r["summary"]


def _counter(s: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from backend.dealdesk.try_docs import engines
    r = engines.counter_and_paper(s["deal_id"])
    return r, r["summary"]


def _draft(s: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from backend.dealdesk.try_docs import memo
    r = memo.draft(s["deal_id"], s["documents"]["proposal"]["language"], use_model=s["mode"] == "model",
                   review=s["steps"]["review"]["result"], counter=s["steps"]["counter"]["result"],
                   policy=s["steps"]["policy"].get("result"))
    return r, r["summary"]


_RUN = {"policy": _policy, "extract": _extract, "review": _review, "counter": _counter, "draft": _draft}


# ------------------------------------------------------------------ wipe

_TEXT = (".json", ".jsonl", ".txt", ".md", ".csv", ".log")


def _scrub_sqlite(db: Path, needles: list[str]) -> int:
    n = 0
    try:
        con = sqlite3.connect(db)
    except sqlite3.Error:
        return 0
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            if not cols:
                continue
            where = " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?' for c in cols for _ in needles)
            args = [f"%{x}%" for _ in cols for x in needles]
            n += con.execute(f'DELETE FROM "{t}" WHERE {where}', args).rowcount
        con.commit()
    except sqlite3.Error:
        pass
    finally:
        con.close()
    return n


def _scrub_file(f: Path, needles: list[str]) -> str | None:
    if any(x in f.name for x in needles):
        f.unlink(missing_ok=True)
        return "deleted"
    if f.suffix.lower() not in _TEXT or f.stat().st_size > 50 * 1024 * 1024:
        return None
    try:
        text = f.read_text(errors="ignore")
    except OSError:
        return None
    if not any(x in text for x in needles):
        return None
    if f.suffix.lower() == ".jsonl" or f.suffix.lower() in (".log", ".csv", ".txt"):
        keep = [ln for ln in text.splitlines(keepends=True) if not any(x in ln for x in needles)]
        f.write_text("".join(keep))
        return "lines removed"
    try:
        obj = json.loads(text)
    except ValueError:
        f.unlink(missing_ok=True)
        return "deleted"
    if isinstance(obj, dict):
        hit = [k for k in obj if any(x in k for x in needles)]
        if hit and not any(x in json.dumps({k: v for k, v in obj.items() if k not in hit}, ensure_ascii=False) for x in needles):
            for k in hit:
                obj.pop(k)
            f.write_text(json.dumps(obj, ensure_ascii=False))
            return "keys removed"
    f.unlink(missing_ok=True)
    return "deleted"


def _clear_caches() -> None:
    import functools
    import importlib
    for mod in ("backend.dealdesk.review_facts", "backend.dealdesk.review_workspace", "backend.dealdesk.proposals",
                "backend.dealdesk.review_conditions", "backend.dealdesk.house_style.store"):
        try:
            m = importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
        for v in vars(m).values():
            if isinstance(v, functools._lru_cache_wrapper) and v.__module__ == mod:  # noqa: SLF001
                try:
                    v.cache_clear()
                except Exception:  # noqa: BLE001
                    pass
        cache = getattr(m, "_CACHE", None)
        if isinstance(cache, dict):
            cache.clear()


def needles_of(s: dict[str, Any] | None, sid: str) -> list[str]:
    out = [sid]
    if s and s.get("deal_id"):
        out.append(s["deal_id"])
    if s and s.get("borrower_name") and len(s["borrower_name"]) >= 6 and s["borrower_name"] != D.DEAL_DEFAULTS["name"][0]:
        out.append(s["borrower_name"])
    return out


def wipe(sid: str) -> dict[str, Any]:
    """Remove every trace of the session: its folder, the demo deal and everything the engines wrote for it."""
    t0 = time.perf_counter()
    d = _dir(sid)
    try:
        s = get(sid)
    except SessionError:
        s = None
    needles = needles_of(s, sid)
    ids = needles[:2] if s and s.get("deal_id") else needles[:1]
    since = (datetime.fromisoformat(s["created_at"]).timestamp() - 1) if s else time.time()
    from backend.dealdesk.try_docs import engines
    unpublished = engines.unpublish_demo_deal(sid, (s or {}).get("deal_id"))
    with _LOCK:
        shutil.rmtree(d, ignore_errors=True)
        rows = 0
        files: dict[str, str] = {}
        if paths.VAR.exists():
            for f in sorted(paths.VAR.rglob("*")):
                if not f.is_file():
                    continue
                if f.suffix in (".sqlite", ".db", ".sqlite3"):
                    rows += _scrub_sqlite(f, ids)
                    continue
                # the borrower's name only in files written during the session (the app's own demo data may share it)
                r = _scrub_file(f, needles if f.stat().st_mtime >= since else ids)
                if r:
                    files[str(f.relative_to(paths.VAR))] = r
        _clear_caches()
    return {"session_id": sid, "wiped": True, "rows_removed": rows, "files": files, "unpublished": unpublished,
            "seconds": round(time.perf_counter() - t0, 2), "at": _now()}


def sessions() -> list[str]:
    return sorted(p.name for p in root().glob("TRYS-*")) if root().exists() else []


def sweep(hours: float = TTL_HOURS) -> list[str]:
    """Wipe sessions older than the time to live (a browser closed without Exit)."""
    out = []
    cut = datetime.now(UTC) - timedelta(hours=hours)
    for sid in sessions():
        try:
            created = datetime.strptime(sid.split("-")[1], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        if created < cut:
            wipe(sid)
            out.append(sid)
    return out
