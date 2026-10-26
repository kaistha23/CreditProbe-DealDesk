"""R14 E: one deal lookup, one structure resolver and one cached analysis, shared by the approval, economics, capacity
and findings engines (so a tile, a step and a paper read the same figures for the same structure).

structure:
  None / "ask"        the deal as proposed
  "recommended"       E's counter-offer (backend.dealdesk.findings.counter_offer): pricing to the hurdle, amount cut to
                      capacity, every critical/major finding cured or flagged
  "counter:<id>"      a Review counter-proposal (review_counter, e.g. counter:CP-D1)
  {terms}             a user structure: any ask fields to override
"""
from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any

from backend.dealdesk import engine, params, proposals

ALIASES = {"PRP-B-ASB": "R12-TWA", "PRP-A-GMC": "R12-TWB", "TWIN-A": "R12-TWA", "TWIN-B": "R12-TWB"}
_LOCK = threading.Lock()
_AN: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
TTL = 600.0


class UnknownDeal(KeyError):
    pass


def resolve_id(pid: str) -> str:
    return ALIASES.get(str(pid).upper(), pid) if pid else pid


def proposal(pid: str) -> dict[str, Any]:
    pid = resolve_id(pid)
    try:
        return copy.deepcopy(proposals.get(pid))
    except Exception as e:  # noqa: BLE001 - any lookup failure is "no such deal"
        raise UnknownDeal(pid) from e


def version() -> str:
    try:
        return params.version_tag()
    except Exception:  # noqa: BLE001
        return "?"


def _ask_terms(p: dict[str, Any]) -> dict[str, Any]:
    return engine.merge_terms(p, None)


def structure_terms(pid: str, structure: Any = None) -> dict[str, Any]:
    """{key, label, terms} for a structure spec (see module docstring). terms = full engine terms."""
    pid = resolve_id(pid)
    p = proposal(pid)
    if structure in (None, "", "ask", "as_proposed"):
        return {"key": "ask", "label": "As proposed", "terms": _ask_terms(p)}
    if isinstance(structure, dict):
        t = engine.merge_terms(p, {k: v for k, v in structure.items() if k not in ("label", "key")})
        return {"key": structure.get("key") or "user", "label": structure.get("label") or "Your structure", "terms": t}
    s = str(structure)
    if s == "recommended":
        from backend.dealdesk.findings.counter import counter_offer
        co = counter_offer(pid)
        return {"key": "recommended", "label": co["label"], "terms": co["structure"]["terms"]}
    if s.startswith("counter:"):
        cid = s.split(":", 1)[1]
        from backend.dealdesk import review_workspace as RW
        w = RW.review(pid)
        for c in (w.get("counter") or {}).get("counter_proposals") or []:
            if c["id"] == cid:
                st = c["structure"]
                over = {k: st[k] for k in ("amount", "tenor_years", "margin_bps", "commission_bps", "funded_share_pct",
                                           "cash_margin_pct", "covenant_package") if st.get(k) is not None}
                return {"key": s, "label": c["title"], "terms": engine.merge_terms(p, over)}
        raise KeyError(f"no counter-proposal {cid} for {pid}")
    raise ValueError(f"unknown structure {structure!r}")


def analysis(pid: str, terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """engine.analyse on (deal, terms), cached per parameter version."""
    pid = resolve_id(pid)
    tkey = json.dumps(terms or {}, sort_keys=True, default=str)
    key = (pid, tkey, version())
    with _LOCK:
        hit = _AN.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    p = proposal(pid)
    a = engine.analyse(p, terms, validate=False)
    with _LOCK:
        if len(_AN) > 256:
            _AN.clear()
        _AN[key] = (time.time(), a)
    return a


def clear() -> None:
    with _LOCK:
        _AN.clear()
