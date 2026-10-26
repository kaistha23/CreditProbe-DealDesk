"""R14 session p: runtime cache of session f's pipeline test for the bank-form proposal's pipeline fit (CP2). The test runs the whole
pipeline optimiser (15-50 s per deal); its few result lines are kept under var/dealdesk/papers/pipeline/, keyed by the deal, the
structure's terms, the parameter version and the dd_deal / dd_structure_set versions, so a changed deal or structure recomputes.
A cache of computed results, not data: the papers' figures still come from the engines and Data Domains.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Callable

DIR = pathlib.Path(__file__).resolve().parents[3] / "var" / "dealdesk" / "papers" / "pipeline"
KEEP = ("verdict", "value_text", "displaces_text", "closest_limit", "makes_cut", "rank", "ranked", "label_line")


def key(pid: str, st: dict[str, Any]) -> str:
    try:
        from backend.dealdesk import params
        pv = params.version_tag()
    except Exception:  # noqa: BLE001
        pv = ""
    try:
        from backend.dealdesk.data import store
        dv = f"{store.version_of('dd_deal')}.{store.version_of('dd_structure_set')}"
    except Exception:  # noqa: BLE001
        dv = ""
    blob = json.dumps({"pid": pid, "key": st.get("key"), "terms": st.get("terms") or {}, "pv": pv, "dv": dv}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def get_or_run(pid: str, st: dict[str, Any], run: Callable[[], dict[str, Any] | None]) -> dict[str, Any] | None:
    f = DIR / f"{pid}-{key(pid, st)}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except ValueError:
            pass
    r = run()
    if r is None:
        return None
    keep = {k: r.get(k) for k in KEEP}
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(keep, default=str))
    except OSError:
        pass
    return keep
