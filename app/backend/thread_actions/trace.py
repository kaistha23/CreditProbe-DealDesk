"""Trace (R16 t, M7): where an answer came from, in four lists and plain words.

    sources    every source the module attached (relation rows, queries, documents, runs, engines)
    queries    the SQL that ran, with the relations it reads (parsed from FROM / JOIN)
    relations  each Data Domains relation touched, with its domain and label from the registry, and whether it
               is registered (an unregistered name is shown as such, never hidden)
    rows       the row keys the figures point at (relation + key + period)

Deterministic: same document, same trace.
"""
from __future__ import annotations

import functools
import re
from typing import Any

_FROM = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", re.I)


@functools.lru_cache(maxsize=1)
def _registry() -> dict[str, tuple[str, str]]:
    """relation -> (domain, label) from the Data Domains registry (backend/data_builder/registry.py)."""
    out: dict[str, tuple[str, str]] = {}
    try:
        from backend.data_builder.registry import DOMAINS
        for dom, spec in DOMAINS.items():
            for rel, r in (spec.get("relations") or {}).items():
                out.setdefault(rel, (dom, (r or {}).get("label", rel) if isinstance(r, dict) else rel))
    except Exception:  # the trace still shows what the module sent
        pass
    try:
        from backend.dealdesk.data.schema import RELATIONS
        for rel, r in RELATIONS.items():
            out.setdefault(rel, (r["domain"], r["label"]))
    except Exception:
        pass
    return out


#: The module conversations query named views over registered relations (backend/*/convo_domain.py `Relation(...)`):
#: a view is shown with the relation it reads, not as "not registered".
VIEWS: dict[str, tuple[str, str, str]] = {
    "exposures": ("what_if", "What-If book exposures (IFRS 9 inputs, collateral)", "whatif_corporate"),
    "history": ("what_if", "What-If book history by period", "whatif_corporate"),
    "mev_history": ("what_if", "Macro variables, history", "whatif_mev_annual"),
    "mev_paths": ("what_if", "Macro variables, scenario paths", "whatif_mev_annual"),
    "observations": ("scorecard", "Scorecard observations (scores, outcomes)", "SME-ANN"),
    "variables": ("scorecard", "Scorecard characteristics", "SME-ANN"),
    "bins": ("scorecard", "Scorecard characteristic bins", "SME-ANN"),
    "grades": ("scorecard", "Scorecard grades", "SME-ANN"),
    "lens_figures": ("cockpit", "The lens's figures", "corp_borrower_quarter"),
    "scope_exposures": ("cockpit", "Exposures in the lens's scope", "corp_borrower_quarter"),
    "proposals": ("deal_desk", "Deal register (view)", "dd_deal"),
    "proposal_checks": ("deal_desk", "Proposal checks (view)", "dd_proposal_quality"),
}


def relations_in_sql(sql: str) -> list[str]:
    seen: list[str] = []
    for m in _FROM.finditer(sql or ""):
        name = m.group(1).split(".")[-1].strip('"`')
        if name.lower() in ("select", "lateral", "unnest") or name in seen:
            continue
        seen.append(name)
    return seen


def trace(doc: dict[str, Any], turn_index: int | None = None) -> dict[str, Any]:
    reg = _registry()
    turns = doc["turns"] if turn_index is None else [doc["turns"][turn_index]]
    sources: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    rels: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    def touch(name: str, via: str, domain: str = "", n: int | None = None) -> None:
        if not name:
            return
        d, label = reg.get(name, (domain, ""))
        view = VIEWS.get(name) if name not in reg else None
        if view:
            d, label = view[0], f"{view[1]}, a view over {view[2]}"
        r = rels.setdefault(name, {"relation": name, "domain": d or domain, "label": label or name,
                                   "registered": name in reg or bool(view), "via": [], "rows": 0})
        if via not in r["via"]:
            r["via"].append(via)
        if n:
            r["rows"] += n

    for t in turns:
        for s in t.get("sources") or []:
            sources.append(s)
            if s.get("sql"):
                read = relations_in_sql(s["sql"])
                queries.append({"label": s.get("label", "Query"), "sql": s["sql"], "relations": read, "rows": s.get("rows")})
                for name in read:
                    touch(name, "query")
            if s.get("relation"):
                touch(s["relation"], s["kind"], s.get("domain", ""), s.get("rows") if s["kind"] != "query" else None)
            if s.get("keys") and s.get("relation"):
                rows.append({"relation": s["relation"], "keys": s["keys"], "period": s.get("period", ""),
                             "label": s.get("label", "")})
    tables = sum(1 for t in turns for b in t["blocks"] if b["kind"] == "table")
    table_rows = sum(len(b["rows"]) for t in turns for b in t["blocks"] if b["kind"] == "table")
    rel_list = sorted(rels.values(), key=lambda r: (not r["registered"], r["relation"]))
    unreg = [r["relation"] for r in rel_list if not r["registered"]]
    return {"plain_words": _plain(len(turns), sources, queries, rel_list, rows, tables, table_rows, unreg),
            "sources": sources, "queries": queries, "relations": rel_list, "rows": rows,
            "counts": {"sources": len(sources), "queries": len(queries), "relations": len(rel_list), "rows": len(rows),
                       "tables": tables, "table_rows": table_rows, "unregistered": len(unreg)}}


def _plain(n_turns: int, sources, queries, rels, rows, tables: int, table_rows: int, unreg: list[str]) -> list[str]:
    what = "This answer" if n_turns == 1 else f"These {n_turns} answers"
    if not sources:
        return [f"{what} {'carries' if n_turns == 1 else 'carry'} no source list from the module: the figures are as shown on screen.",
                "Nothing here was looked up in Data Domains for this trace."]
    if rels:
        out = [f"{what} drew on {len(rels)} Data Domains relation{'s' if len(rels) != 1 else ''}"
               + (f" through {len(queries)} quer{'ies' if len(queries) != 1 else 'y'}" if queries else "")
               + (f" and {len(rows)} named row{'s' if len(rows) != 1 else ''}" if rows else "") + "."]
    else:
        out = [f"{what} named no Data Domains relation; {'its' if n_turns == 1 else 'their'} "
               f"{len(sources)} source{'s' if len(sources) != 1 else ''} (engine steps, runs and checks) {'is' if len(sources) == 1 else 'are'} listed below."]
    if tables:
        out.append(f"{tables} table{'s' if tables != 1 else ''} with {table_rows} row{'s' if table_rows != 1 else ''} {'are' if tables != 1 else 'is'} shown.")
    if unreg:
        out.append(f"Not registered in Data Domains: {', '.join(unreg[:5])}{' …' if len(unreg) > 5 else ''}.")
    elif rels:
        out.append("Every relation named is registered in Data Domains.")
    return out
