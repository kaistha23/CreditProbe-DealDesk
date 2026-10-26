"""PLAN_R12 Session P: lineage of every product figure (PLAN_R12 §0 rule 3, N5).

`figures(out)` walks a product response and returns every number with the nearest `src` above it;
`check(out)` lists the numbers with no source and the sources that name a relation not registered in Data Domains.
`for_proposal(pid)` runs it over the three deal sections. The SME lane is checked per application.

`CASES` are the lineage cases Session E's harness (tests/…/test_r12_lineage) can pick up: each a callable returning
a product response to walk.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

#: sources that are bank configuration, not data (PLAN_R12 §0: "the only exception")
CONFIG = {"products_policy_default", "product_template"}
#: keys whose numbers are presentation (counts of rows, step numbers, priorities), not business figures
STRUCTURAL = {"step", "priority", "projects", "financed", "with_flags", "eot_not_formalised", "breaches", "total", "count",
              "in_lane", "to_full_flow", "ready_to_approve", "months_in_deficit", "lenders", "delay_days", "units_total", "units_sold",
              "exceptions", "days_due", "max_days_due", "agent_info_age_days", "eot_days", "tenor_years", "returned_cheques", "court_cases"}


def registered() -> set[str]:
    try:
        from backend.data_builder.registry import DOMAINS
    except Exception:  # noqa: BLE001
        return set()
    return {r for d in DOMAINS.values() for r in (d.get("relations") or {})}


def _rels(src: Any) -> list[str]:
    if not isinstance(src, dict):
        return []
    r = src.get("relation")
    out = r if isinstance(r, list) else [r] if r else []
    for i in src.get("inputs") or []:
        out += _rels(i)
    for v in src.values():
        if isinstance(v, dict) and "relation" in v:
            out += _rels(v)
    return out


def figures(o: Any, path: str = "", src: Any = None) -> Iterator[tuple[str, float, Any]]:
    if isinstance(o, dict):
        here = o.get("src", src)
        if isinstance(here, dict) and "relation" not in here and here:   # per-field sources
            here_map = here
        else:
            here_map = None
        for k, v in o.items():
            if k in ("src", "min_src", "trace_id"):
                continue
            s = (here_map.get(k) if here_map and k in here_map else
                 (next(iter(here_map.values())) if here_map else here))
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                if k not in STRUCTURAL:
                    yield f"{path}.{k}", float(v), s
            else:
                yield from figures(v, f"{path}.{k}", s)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                yield f"{path}[{i}]", float(v), src
            else:
                yield from figures(v, f"{path}[{i}]", src)


def check(out: dict[str, Any], known: set[str] | None = None) -> dict[str, Any]:
    known = registered() if known is None else known
    unsourced, unregistered, n = [], set(), 0
    for p, _, s in figures(out):
        n += 1
        rels = _rels(s)
        if not rels:
            unsourced.append(p)
            continue
        for r in rels:
            if r not in known and r not in CONFIG:
                unregistered.add(r)
    return {"figures": n, "unsourced": unsourced, "unregistered": sorted(unregistered), "ok": not unsourced and not unregistered}


def for_proposal(pid: str) -> dict[str, Any]:
    from backend.dealdesk.products import escrow, project, syndication
    known = registered()
    out = {}
    for name, fn in (("project", project.analyse), ("escrow", escrow.analyse), ("syndication", syndication.analyse)):
        r = fn(pid)
        out[name] = {"has_data": r.get("has_data", False), **check(r, known)} if r.get("has_data") else {"has_data": False}
    return {"proposal_id": pid, "sections": out, "ok": all(v.get("ok", True) for v in out.values())}


def _case_sme() -> list[dict[str, Any]]:
    from backend.dealdesk.products import sme
    return [sme.decide(a) for a in sme.applications()]


CASES: dict[str, Callable[[], Any]] = {
    "products.sme": _case_sme,
}


# ------------------------------------------------------------------ Session E's harness format


def as_figures(out: Any) -> list[dict[str, Any]]:
    """Every figure of a product response in Session E's lineage format ({"value", "source"}): a derived figure is
    traced to the rows it is computed from (one figure per input row); bank configuration is left out."""
    from backend.dealdesk.data import store

    def concrete(s: Any) -> list[dict[str, Any]]:
        if not isinstance(s, dict):
            return []
        if isinstance(s.get("relation"), str) and s.get("key") and not s.get("derived"):
            return [s]
        return [x for i in s.get("inputs") or [] for x in concrete(i)]
    figs = []
    for p, v, s in figures(out):
        for c in concrete(s)[:3]:
            rel = c["relation"]
            if rel in CONFIG:
                continue
            try:
                dom = store.domain_of(rel)
            except Exception:  # noqa: BLE001
                dom = c.get("domain")
            figs.append({"path": p, "value": v, "source": {"domain": dom, "relation": rel, "key": c["key"], "column": c.get("column")}})
    return figs
