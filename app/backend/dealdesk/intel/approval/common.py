"""Shared plumbing for the approval-intelligence engines (R13 Session IA).

Every number an engine returns is a *figure*: {"value", "unit", "source"}. The source is either

  * a Data Domains row (store.trace: domain, relation, key, period, version, plus the column), or
  * an engine run on a Data Domains deal: {"domain": "deal_desk", "relation": "dd_deal", "key": {"proposal_id"},
    "column": "proposal_json", "engine": "engine.analyse" | ..., "terms": "ask" | {...}, "param_versions": {...}}

so `backend.dealdesk.data.lineage.untraced(output)` is empty for every response (N5). The engine source resolves
because the deal row it ran on is a registered relation row.
"""
from __future__ import annotations

import copy
import functools
import json
from typing import Any

from backend.dealdesk import engine, params
from backend.dealdesk.data import deals as DEALS
from backend.dealdesk.data.store import dd_read, trace
from backend.dealdesk.seed import GRADES, bucket
from backend.v5common.ratings import rank

ALIASES = {"PRP-B-ASB": "R12-TWA", "PRP-A-GMC": "R12-TWB", "TWIN-A": "R12-TWA", "TWIN-B": "R12-TWB"}
SEV_ORDER = {"critical": 0, "high": 1, "major": 1, "medium": 2, "minor": 3, "low": 3, "info": 4}
STRESS_SEV = ("mild", "moderate", "severe")


class UnknownDeal(KeyError):
    pass


def resolve_id(pid: str) -> str:
    return ALIASES.get(pid.upper(), pid) if pid else pid


@functools.lru_cache(maxsize=1)
def _register() -> dict[str, dict[str, Any]]:
    return {r["proposal_id"]: r for r in DEALS.register()}


def register_row(pid: str) -> dict[str, Any]:
    r = _register().get(pid)
    if r is None:  # a deal registered since the cache was filled
        _register.cache_clear()
        r = _register().get(pid)
    if r is None:
        raise UnknownDeal(pid)
    return r


def all_ids() -> list[str]:
    return sorted(_register())


@functools.lru_cache(maxsize=128)
def _proposal(pid: str) -> str:
    try:
        return json.dumps(DEALS.get(pid))
    except Exception as e:  # noqa: BLE001 - any lookup failure is "no such deal"
        raise UnknownDeal(pid) from e


def proposal(pid: str) -> dict[str, Any]:
    pid = resolve_id(pid)
    register_row(pid)
    return json.loads(_proposal(pid))


def clear() -> None:
    _register.cache_clear()
    _proposal.cache_clear()
    _analysis.cache_clear()


# ------------------------------------------------------------------ figures and lineage

def deal_source(pid: str, engine_call: str = "engine.analyse", terms: Any = "ask", note: str = "") -> dict[str, Any]:
    src = trace("dd_deal", register_row(pid))
    src["column"] = "proposal_json"
    src["engine"] = engine_call
    src["terms"] = terms
    src["param_versions"] = params.versions()
    if note:
        src["note"] = note
    return src


def row_source(relation: str, row: dict[str, Any], column: str | None = None) -> dict[str, Any]:
    src = trace(relation, row)
    if column:
        src["column"] = column
    return src


def fig(value: Any, unit: str, source: dict[str, Any], label: str = "") -> dict[str, Any]:
    v = value
    if isinstance(v, float):
        v = float(round(v, 6))
    out = {"value": v, "unit": unit, "source": source}
    if label:
        out["label"] = label
    return out


def efig(pid: str, value: Any, unit: str, label: str = "", engine_call: str = "engine.analyse", terms: Any = "ask") -> dict[str, Any]:
    return fig(value, unit, deal_source(pid, engine_call, terms), label)


def rfig(relation: str, row: dict[str, Any], column: str, unit: str = "", label: str = "") -> dict[str, Any]:
    return fig(row[column], unit, row_source(relation, row, column), label)


# ------------------------------------------------------------------ engine runs (cached on the deal and the terms)

def _key(terms: dict[str, Any] | None) -> str:
    return json.dumps(terms or {}, sort_keys=True, default=str)


@functools.lru_cache(maxsize=512)
def _analysis(pid: str, tkey: str, pv: str) -> dict[str, Any]:
    p = proposal(pid)
    a = engine.analyse(p, json.loads(tkey) or None, validate=False)
    a = {k: v for k, v in a.items() if not k.startswith("_")}
    return a


def analysis(pid: str, terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """engine.analyse on the deal (cached per parameter versions); a deep copy so callers may mutate."""
    return copy.deepcopy(_analysis(resolve_id(pid), _key(terms), json.dumps(params.versions(), sort_keys=True)))


def hard_breaches(a: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]


def soft_breaches(a: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] != "hard"]


def approvable(a: dict[str, Any]) -> bool:
    return bool(a["metrics"]["clears_hurdle"]) and not hard_breaches(a)


# ------------------------------------------------------------------ Data Domains readers

def rows(relation: str, **filters: Any) -> list[dict[str, Any]]:
    try:
        return dd_read(relation, **filters)
    except Exception:  # noqa: BLE001 - a relation not yet published reads as empty
        return []


def latest_stress(pid: str) -> dict[str, Any]:
    """The latest dd_stress_result run for the deal and its verdict under the R12 rule (stress2.verdict.RULES):
    the mildest severity at which a scenario still breaks something decides the verdict and tier."""
    from backend.dealdesk.stress2.verdict import RULE_BY_SEV
    rs = rows("dd_stress_result", proposal_id=pid)
    if not rs:
        return {"run_id": None, "rows": [], "worst_breaking_severity": None, "verdict": None, "tier": None, "breaking": []}
    last = max(rs, key=lambda r: (str(r.get("run_at") or ""), str(r.get("run_id") or "")))["run_id"]
    run = [r for r in rs if r["run_id"] == last]
    breaking = [r for r in run if r.get("breaks") and int(r.get("applicable_flag") or 0)]
    sev = next((s for s in STRESS_SEV if any(r["severity"] == s for r in breaking)), "none")
    rule = RULE_BY_SEV[sev]
    return {"run_id": last, "rows": run, "breaking": breaking, "worst_breaking_severity": sev,
            "verdict": rule["verdict"], "tier": rule["tier"], "action": rule["action"]}


def rating_bucket(r: str) -> str:
    return bucket(r)


def notch_gap(a: str, b: str) -> int | None:
    try:
        return abs(rank(a) - rank(b))
    except Exception:  # noqa: BLE001
        try:
            return abs(GRADES.index(a) - GRADES.index(b))
        except ValueError:
            return None


def pct(x: float | None, dp: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{dp}f}%"


def mn(x: float | None, ccy: str = "SAR", dp: int = 1) -> str:
    return "n/a" if x is None else f"{ccy} {x:,.{dp}f}m"
