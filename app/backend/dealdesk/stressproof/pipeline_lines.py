"""Test against pipeline, explained (K21): run on the selected structure (labelled), SVA on the one basis (adapters),
"PL-03 resized" explained and counted, plain wording for the closest limit, and the marginal effect read on THIS
deal's own lines (its obligor, group, sector, rating bucket, collateral type and product), before -> after, limit,
headroom and the RAG status, instead of the book's largest group and sector.

The pipeline solve itself is R11 Session L's (`pipeline.pipeline_test`); this module only reads and explains it."""
from __future__ import annotations

from typing import Any

from backend.dealdesk import engine, pipeline
from backend.dealdesk.stressproof import adapters as AD
from backend.dealdesk.stressproof import structures as ST

PURPOSE = ("Would this deal get a slot in this quarter's pipeline under the RWA and EL budget, and what does it push out?")
LINE_LABEL = {"single_name": "Obligor", "group_connected": "Group", "group_large_exposure": "Group large exposure",
              "sector_policy": "Sector (policy)", "sector_appetite": "Sector (appetite)", "rating_bucket": "Rating bucket",
              "collateral_type": "Collateral type", "max_tenor": "Product tenor", "structure": "Product structure"}
RAG_LEGEND = {"green": "within the limit with room", "amber": "within the limit, close to it (trigger zone)", "red": "past the limit"}


def _rag(c: dict[str, Any]) -> str:
    if c["status"] == "breach":
        return "red"
    v, lim = c.get("value"), c.get("limit")
    if isinstance(v, (int, float)) and isinstance(lim, (int, float)) and lim:
        return "amber" if abs(v) / abs(lim) >= 0.9 else "green"
    return "green"


def own_lines(a: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    deal = None
    for c in a["constraints"]:
        if c["name"] not in LINE_LABEL:
            continue
        deal = c.get("deal", deal)
        v, lim, before = c.get("value"), c.get("limit"), c.get("before")
        num = isinstance(v, (int, float)) and isinstance(lim, (int, float))
        head = (lim - v) if num else None
        dv = c.get("deal")
        times = None
        if num and dv and isinstance(before, (int, float)):
            step = v - before
            times = head / step if step > 1e-12 else None
        out.append({"line": LINE_LABEL[c["name"]], "name": c["name"], "scope": c.get("scope"), "before": before, "after": v, "limit": lim,
                    "unit": c.get("unit"), "headroom": head, "room_times_deal": times, "kind": c["kind"], "rag": _rag(c),
                    "changed": bool(num and isinstance(before, (int, float)) and abs(v - before) > 1e-12)})
    return out


def run(pid: str, key: str | None = None) -> dict[str, Any]:
    s = ST.structure_set(pid)
    by = {r["key"]: r for r in s["rows"]}
    sel = by.get(key or s["selected"]) or by[s["selected"]]
    p = ST.deal(pid)
    pipeline.get(pid)  # KeyError for a deal the pipeline cannot open (404)
    res = pipeline.pipeline_test(pid, sel["terms"])
    a = engine.analyse(ST.with_covenants(p, sel.get("covenants")), sel["terms"])
    sva = AD.sva(a, pid)
    lines = own_lines(a)
    resized = []
    for d in res.get("resized") or []:
        resized.append({**d, "text": f"{d['proposal_id']} ({d['obligor']}) resized from “{d['from']}” to “{d['to']}” so this deal fits the budget"})
    displaced_n = len(res.get("displaced") or []) + len(resized)
    bf = res.get("binds_first")
    closest = None
    if bf:
        sc = "" if bf["scope"] in ("book", "new business") else f" ({bf['scope']})"
        closest = (f"Closest limit: {bf['label'].lower()}{sc}, room left {bf['times']:,.1f}× this deal" if bf["times"] >= 0
                   else f"Closest limit: {bf['label'].lower()}{sc} is already past its limit")
    gain = res.get("value_change")
    value_text = None if gain is None else (
        f"Pipeline value (SVA of the approved deals less the appetite charge) {'+' if gain >= 0 else '−'}SAR {abs(gain):,.2f}m with this deal in; "
        f"this deal's own SVA is SAR {0.0 if abs(sva['value']) < 0.005 else sva['value']:,.2f}m ({sva['basis'].replace('_', '-')} basis); the difference comes from the deals resized or "
        "displaced and the appetite charge moving.")
    plain = ["This checks whether this deal gets a slot in this quarter's pipeline under the capital and loss budgets, and what it pushes out.",
             (f"On the {sel['label']} structure {'it makes the cut' if res['makes_cut'] else 'it does not make the cut'}"
              + (f" and {displaced_n} other deal{'s' if displaced_n != 1 else ''} change{'s' if displaced_n == 1 else ''}." if displaced_n else ", no other deal changes.")),
             closest or "No limit binds.",
             "The lines below are this deal's own: its obligor, group, sector, rating bucket and product."]
    return {"proposal_id": pid, "purpose": PURPOSE, "structure": {"key": sel["key"], "label": sel["label"]},
            "label_line": f"Tested on: {sel['label']} ({sel['origin']})", "verdict": res["verdict"], "makes_cut": res["makes_cut"],
            "fits": res["fits"], "rank": res["rank"], "ranked": res["ranked"], "sva": sva, "value_change": gain, "value_text": value_text,
            "displaced": res.get("displaced") or [], "resized": resized, "displaces_count": displaced_n,
            "displaces_text": (", ".join([d["proposal_id"] + " out" for d in res.get("displaced") or []] + [d["proposal_id"] + " resized" for d in resized])
                               or "No deal drops out or is resized"),
            "closest_limit": closest, "binds_first": bf,
            "closest_short": None if not bf else {"label": bf["label"], "room": (f"room left {bf['times']:,.1f}× this deal" if bf["times"] >= 0 else "already past its limit"),
                                                  "scope": bf["scope"]}, "lines": lines, "rag_legend": RAG_LEGEND, "pipeline": res.get("pipeline"),
            "plain_words": plain, "basis": res.get("basis")}
