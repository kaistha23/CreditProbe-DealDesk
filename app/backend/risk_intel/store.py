"""Session C's own small state: PD-by-bucket parameters (Admin) and actions taken from the panels.

JSON files under var/risk_intel (git-ignored). Each write is versioned with who and when.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import threading
from typing import Any

V5 = pathlib.Path(__file__).resolve().parents[2]
ROOT = pathlib.Path(os.environ.get("RISK_INTEL_STORE") or V5 / "var" / "risk_intel").resolve()
_LOCK = threading.Lock()

#: P3 defaults (PLAN_R9 C1): 12-month probability that a name in the bucket defaults, management estimate.
PD_DEFAULTS = {"critical": 70.0, "high": 40.0, "moderate": 15.0, "low": 3.0}
BUCKET_LABELS = {"critical": "Critical", "high": "High", "moderate": "Medium", "low": "Low"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _read(name: str, default: Any) -> Any:
    p = ROOT / name
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, value: Any) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / (name + ".tmp")
    tmp.write_text(json.dumps(value, indent=1, default=str))
    tmp.replace(ROOT / name)


def pd_by_bucket() -> dict[str, Any]:
    with _LOCK:
        d = _read("pd_by_bucket.json", None)
    if not d:
        return {"values": dict(PD_DEFAULTS), "basis": "management estimate", "version": 1,
                "updated_by": "system", "updated_at": None, "history": []}
    return d


def set_pd_by_bucket(values: dict[str, Any], user: str = "admin") -> dict[str, Any]:
    clean: dict[str, float] = {}
    for k in PD_DEFAULTS:
        v = float(values.get(k, PD_DEFAULTS[k]))
        if not 0 <= v <= 100:
            raise ValueError(f"{BUCKET_LABELS[k]}: a probability between 0% and 100% is required.")
        clean[k] = round(v, 2)
    if not (clean["critical"] >= clean["high"] >= clean["moderate"] >= clean["low"]):
        raise ValueError("The probabilities must not increase from Critical down to Low.")
    with _LOCK:
        cur = _read("pd_by_bucket.json", None) or {"values": dict(PD_DEFAULTS), "version": 1, "history": []}
        hist = list(cur.get("history") or [])
        hist.append({"version": cur.get("version", 1), "values": cur.get("values"), "updated_by": cur.get("updated_by"),
                     "updated_at": cur.get("updated_at")})
        new = {"values": clean, "basis": "management estimate", "version": int(cur.get("version", 1)) + 1,
               "updated_by": user, "updated_at": _now(), "history": hist[-20:]}
        _write("pd_by_bucket.json", new)
    return new


def actions() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_read("actions.json", []))


def add_action(kind: str, payload: dict[str, Any], user: str = "admin") -> dict[str, Any]:
    with _LOCK:
        rows = list(_read("actions.json", []))
        row = {"id": f"ACT-{len(rows) + 1:04d}", "kind": kind, "at": _now(), "by": user, **payload}
        rows.append(row)
        _write("actions.json", rows)
    return row
