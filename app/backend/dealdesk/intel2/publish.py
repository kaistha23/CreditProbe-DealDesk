"""R14 i: the D6-D13 results of one deal as dd_deal_intel rows (headline + the items that matter), with lineage.

Used by `ops/r14_i_publish.py --results` and by POST /api/v1/dealdesk/intel2/{id}/publish. Each row's basis_json names
the relations and engine calls the item comes from; the numbers are the engines' own (no recomputation).
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.intel2 import ENGINES
from backend.dealdesk.intel2.seed import CATALOGUE

LABEL = {c[0]: c[1] for c in CATALOGUE}
WHERE = {c[0]: c[2] for c in CATALOGUE}
BASIS = {c[0]: c[4] for c in CATALOGUE}
RUN_AT = "2026-10-19T18:00:00Z"  # fixed so a re-publish of unchanged results is byte-stable


def _items(code: str, r: dict[str, Any]) -> list[tuple[str, str, float | None, str, str]]:
    """(kind, label, value, unit, text) per item."""
    out: list[tuple[str, str, float | None, str, str]] = []
    if code == "D6":
        out += [("offer", o["label"], o["sva"]["value"], "SAR m SVA", f"RAROC {o['raroc']['value']:.4f}; acceptable {o['acceptable']}") for o in r.get("offers", [])]
        out += [("worth", w["label"], (w.get("worth_bps") or {}).get("value"), "bps", "") for w in r.get("worth", []) if w.get("available")]
    elif code == "D7":
        out += [("path", x["driver"], x["probability"]["value"], "share a year", f"{x['speed']}; first warning: {x['first_warning']}") for x in r.get("paths", [])]
    elif code == "D8":
        out += [("precedent", f"{x['name']} ({x['id']})", x["similarity"]["value"], "similarity", f"{x['decision']}; {x['performance']}") for x in r.get("precedents", [])]
    elif code == "D9":
        out += [("percentile", "Margin percentile among peers", r["percentile"]["value"], "percentile", ", ".join(f"{k} {v}" for k, v in r["basis_used"].items())),
                ("breakeven", "Breakeven price", r["breakeven"]["value"], "bps", "")]
    elif code == "D10":
        out += [("coverage", "Inflows / reported revenue", (r.get("coverage") or {}).get("value"), "share", r.get("verdict", "")),
                ("gap", "Revenue not backed by inflows", (r.get("gap") or {}).get("value"), "SAR m", "")]
    elif code == "D11":
        out += [("change", f"{x['area']}: {x['item']}", None, "", f"{x['then']} -> {x['now']} ({x['direction']})") for x in r.get("rows", []) if x["direction"] == "worse"]
    elif code == "D12":
        out += [("party", x["name"], x["exposure"]["value"], "SAR m", f"{x['status']}; {', '.join(x['links'])}") for x in r.get("parties", []) if x["adverse"]]
    elif code == "D13":
        out += [("question", q["question"][:200], q["score"], "score", f"{q['status']}: {q['suggested_answer'][:300]}") for q in r.get("questions", [])]
    return out


def rows_for(pid: str) -> list[dict[str, Any]]:
    rows = []
    for code, (_, fn) in ENGINES.items():
        r = fn(pid)
        st = (r.get("structure") or {}).get("kind", "")
        base = {"proposal_id": pid, "feature": code, "feature_label": LABEL[code], "structure": st, "basis_json": [BASIS[code]],
                "where": WHERE[code], "engine_version": "r14-i1", "run_at": RUN_AT}
        rows.append({**base, "result_id": f"{pid}:{code}:0", "item_seq": 0, "item_kind": "headline", "label": LABEL[code], "value": None,
                     "unit": "", "text": r.get("headline", "")})
        for i, (kind, label, value, unit, text) in enumerate(_items(code, r), 1):
            rows.append({**base, "result_id": f"{pid}:{code}:{i}", "item_seq": i, "item_kind": kind, "label": label,
                         "value": float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None, "unit": unit, "text": text})
    return rows
