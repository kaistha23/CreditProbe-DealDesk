"""One computation per deal for the group, conduct, governance and SWOT blocks (shared by the API, the papers and Noor).

`bundle(pid)` computes the facts, conduct, cap test, flags and SWOT once, with the lineage of every read, and keeps
the result for ten minutes per (deal, parameter version). `overlay_analysis` prices the deal at the overlaid rating
next to the base rating, for the reviewer to see what the overlay costs.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Any

from backend.dealdesk import params
from backend.dealdesk.group import conduct as C, deal, exposure as X, facts as F, flags as FL, sources as S, swot as SW

TTL_SECONDS = 600
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_LOCK = threading.RLock()


def _version() -> str:
    try:
        return repr(sorted(params.versions().items())) + FL.rules()["version"]
    except Exception:  # noqa: BLE001
        return FL.rules()["version"]


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
    X.clear_cache()


def bundle(pid: str, refresh: bool = False) -> dict[str, Any]:
    key = (pid, _version())
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and not refresh and time.time() - hit[0] < TTL_SECONDS:
            return hit[1]
    deal.get(pid)  # KeyError for an unknown deal, before any work
    S.reset()
    fx = F.build(pid)
    cd = C.build(pid)
    gaps: list[str] = []
    try:
        st = F.structure(deal.get(pid))
        cap = X.cap_test(pid, st=st)
    except Exception as e:  # noqa: BLE001 -- the engine cannot price this deal (bad terms): no cap test
        cap = None
        gaps.append(f"Group cap test not run: {e}")
    ev = FL.evaluate(pid, fx, cd, cap)
    sw = SW.build(pid, fx, cd, ev, cap)
    try:
        from backend.dealdesk.group import figures as FG
        figs = FG.build(pid)
    except Exception as e:  # noqa: BLE001
        figs = {}
        gaps.append(f"Traced figures not built: {e}")
    lineage = S.used()
    missing = S.missing()
    if missing:
        gaps.append("Not published in Data Domains yet: " + ", ".join(missing) + ".")
    out = {"proposal_id": pid, "as_of": deal.AS_OF, "facts": fx, "conduct": cd, "cap_test": cap, "governance": ev, "swot": sw,
           "figures": figs, "lineage": lineage, "not_published": missing, "gaps": gaps}
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def overlay_analysis(pid: str) -> dict[str, Any]:
    """Price the ask at the base rating and at the overlaid rating (the reviewer's what-if; nothing is stored)."""
    from backend.dealdesk import engine
    b = bundle(pid)
    ov = b["governance"]["overlay"]
    p = deal.get(pid)
    base = engine.analyse(p)["metrics"]
    out = {"overlay": ov, "base": {k: base.get(k) for k in ("pd_12m", "lifetime_raroc", "hurdle", "sva", "capital_y1", "el_y1")}}
    if ov["notches"]:
        q = copy.deepcopy(p)
        q["obligor"]["internal_rating"] = ov["overlaid_rating"]
        q["obligor"].pop("pd_master_scale", None)
        try:
            m = engine.analyse(q)["metrics"]
            out["overlaid"] = {k: m.get(k) for k in ("pd_12m", "lifetime_raroc", "hurdle", "sva", "capital_y1", "el_y1")}
        except Exception as e:  # noqa: BLE001
            out["overlaid"] = None
            out["note"] = f"The engine could not price the overlaid rating: {e}"
    else:
        out["overlaid"] = out["base"]
    return out


def publish(pid: str) -> dict[str, Any]:
    """Publish this deal's governance and conduct findings (`dd_review_finding`) and SWOT (`dd_swot`) to Data Domains."""
    b = bundle(pid, refresh=True)
    rows = FL.findings_rows(b["governance"])
    new_ids = {r["finding_id"] for r in rows}
    try:  # C's earlier findings on this deal that no longer hold are superseded, not deleted
        old = S.records(S.read("dd_review_finding", None, proposal_id=pid, raised_by="C"))
    except Exception:  # noqa: BLE001
        old = []
    for r in old:
        if r["finding_id"] not in new_ids and r.get("status") == "open":
            r = {k: v for k, v in r.items() if k not in ("rel_version", "published_at")}
            r["status"] = "superseded"
            rows.append(r)
    f = S.publish("dd_review_finding", rows)
    mt = SW.mitigants(pid, None, "ask", b["swot"], b["governance"])
    sw_rows = SW.rows(b["swot"], mt)
    keep = {r["swot_id"] for r in sw_rows}
    try:  # the deal's SWOT is replaced as a whole: points no longer found are dropped from the relation
        allr = [{k: v for k, v in r.items() if k not in ("rel_version", "published_at")}
                for r in S.records(S.read("dd_swot", None)) if not (r["proposal_id"] == pid and r["swot_id"] not in keep)]
        others = [r for r in allr if r["proposal_id"] != pid]
        s = S.publish("dd_swot", others + sw_rows, mode="replace")
    except Exception:  # noqa: BLE001
        s = S.publish("dd_swot", sw_rows)
    return {"proposal_id": pid, "findings": f, "swot": s}
