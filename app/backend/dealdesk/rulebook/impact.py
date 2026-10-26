"""What a policy would do to the live pipeline: the Deal Desk checks run on every pending deal with and without the change.

    imp = assess(changes, overlay_in_force)
    imp["pipeline"]        {"pending": 46, "by_sector": [{"sector": "Construction", "pending": 13, "would_fail": 7}, ...]}
    imp["deals"]           one row per pending deal the change touches: today's result, the result if applied, the failing checks
    imp["if_applied"]      plain lines: what fails, what is flagged, what every later deal is checked against
    imp["if_not_applied"]  plain lines: what goes on unflagged
    imp["parameters"]      each threshold: value in force -> proposed, the Deal Desk table it lives in
    imp["checks"]          the Deal Desk checks it moves; imp["deal_types"] the sectors and products it reaches
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from backend.dealdesk.rulebook import checks as CK
from backend.dealdesk.rulebook import facts as FA
from backend.dealdesk.rulebook.interpret import lc

PRODUCT = {"term_loan": "Term loans", "revolver": "Revolving facilities", "performance_lg": "Guarantees", "trade_lc": "Trade (LCs)",
           "overdraft": "Overdrafts", "working_capital": "Working capital"}


def proposed_overlay(overlay: dict[str, list[dict[str, Any]]], changes: list[dict[str, Any]], assessment_id: str, reference: str,
                     seq: int) -> dict[str, list[dict[str, Any]]]:
    out = {k: list(v) for k, v in overlay.items()}
    for c in changes:
        out.setdefault(c["param"], []).append({"segment": c["segment"], "value": c["value"], "clause": c.get("clause", ""),
                                               "quote": c.get("quote", ""), "assessment_id": assessment_id, "reference": reference, "seq": seq})
    return out


def assess(changes: list[dict[str, Any]], overlay: dict[str, list[dict[str, Any]]], assessment_id: str = "", reference: str = "",
           seq: int = 10**6, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = FA.pending() if rows is None else rows
    desk = CK._desk()  # noqa: SLF001
    params = sorted({c["param"] for c in changes}, key=list(CK.PARAMS).index)
    new = proposed_overlay(overlay, changes, assessment_id, reference, seq)
    deals, by_sector, fail_sector = [], Counter(), Counter()
    newly = 0
    for f in rows:
        by_sector[f.get("sector") or "Unknown"] += 1
        if not params:
            continue
        now = CK.evaluate(f, overlay, params, desk)
        after = CK.evaluate(f, new, params, desk)
        fails_now = [r for r in now if r["result"] == "fail"]
        fails_after = [r for r in after if r["result"] == "fail"]
        moved = [a for a, b in zip(after, now) if a["threshold"] != b["threshold"]]
        if not moved:
            continue
        new_fails = [a for a, b in zip(after, now) if a["result"] == "fail" and b["result"] != "fail"]
        cleared = [b for a, b in zip(after, now) if b["result"] == "fail" and a["result"] == "pass"]
        if new_fails:
            newly += 1
            fail_sector[f.get("sector") or "Unknown"] += 1
        deals.append({"proposal_id": f["proposal_id"], "customer": f.get("customer"), "rm": f.get("rm"), "status": f.get("status"),
                      "sector": f.get("sector"), "product": PRODUCT.get(f.get("facility_type"), f.get("facility_type") or ""),
                      "amount": f.get("amount"), "currency": f.get("currency"),
                      "today": "fail" if fails_now else "pass", "if_applied": "fail" if fails_after else "pass",
                      "new_failures": [{"check": a["check"], "label": a["label"], "why": a["why"], "clause": a["clause"], "quote": a["quote"]}
                                       for a in new_fails],
                      "already_failing": [{"check": b["check"], "label": b["label"], "why": b["why"]} for b in fails_now],
                      "cleared": [{"check": b["check"], "label": b["label"]} for b in cleared],
                      "checks": [{"check": a["check"], "label": a["label"], "value": a["value"], "unit": a["unit"],
                                  "today": {"threshold": b["threshold"], "result": b["result"]},
                                  "if_applied": {"threshold": a["threshold"], "result": a["result"]}} for a, b in zip(after, now)]})
    deals.sort(key=lambda d: (not d["new_failures"], d["sector"] or "", d["proposal_id"]))
    total = len(rows)
    reached = Counter(d["sector"] or "Unknown" for d in deals)
    sectors = [{"sector": s, "pending": n, "reached": reached.get(s, 0), "would_fail": fail_sector.get(s, 0)}
               for s, n in sorted(by_sector.items(), key=lambda kv: (-kv[1], kv[0]))]
    failing = [d for d in deals if d["new_failures"]]
    parameters = []
    for c in changes:
        d = CK.PARAMS[c["param"]]
        sample = next((f for f in rows if CK._matches(c["segment"], f)), {"sector": c["segment"], "facility_type": "term_loan"})  # noqa: SLF001
        cur, src, _ = CK.threshold(c["param"], sample, overlay, desk)
        parameters.append({"param": c["param"], "check": d["check"], "label": d["label"], "segment": c["segment"], "unit": d["unit"],
                           "current": cur, "current_display": CK.fmt(cur, d["unit"]) if cur is not None else "no requirement",
                           "proposed": c["value"], "proposed_display": c.get("display") or CK.fmt(c["value"], d["unit"]),
                           "direction": _direction(d["op"], cur, c["value"], d["unit"]), "where": d["where"], "source_in_force": src,
                           "clause": c.get("clause", ""), "quote": c.get("quote", "")})
    seg_names = sorted({c["segment"] for c in changes if c["segment"] != "all"}) or ["all corporate deals"]
    products = sorted({d["product"] for d in deals if d["product"]})
    fail_line = (f"{len(failing)} of the {total} pending deals would fail" +
                 (f" ({', '.join(f'{n} {s.lower()}' for s, n in fail_sector.most_common())})" if failing else "") + ".")
    head = f"{total} pending, " + ", ".join(f"{s['pending']} {s['sector'].lower()}" for s in sectors if s["sector"] in seg_names) \
        if seg_names != ["all corporate deals"] else f"{total} pending"
    if_applied = [f"{head}: {fail_line}" if failing else f"{head}: no pending deal would fail; {len(deals)} would be checked against the new thresholds."]
    if failing:
        if_applied.append(f"Each of the {len(failing)} is flagged on its deal with the clause cited, and its RM sees the check that fails.")
    if_applied.append("Every later deal is checked against: " + "; ".join(f"{lc(p['label'])} {p['proposed_display']}"
                                                                      f"{' (' + p['segment'] + ')' if p['segment'] != 'all' else ''}" for p in parameters) + ".")
    if_not = [f"Deal Desk keeps checking against the thresholds in force: " + "; ".join(f"{lc(p['label'])} {p['current_display']}" for p in parameters) + "."]
    if failing:
        if_not.append(f"The {len(failing)} deal{'s' if len(failing) != 1 else ''} that breach the new requirement go on unflagged "
                      f"({', '.join(d['proposal_id'] for d in failing[:8])}{'…' if len(failing) > 8 else ''}).")
    if_not.append("The document stays on record in Policy Docs; nothing reaches the checks or the pipeline.")
    return {"pipeline": {"pending": total, "reached": len(deals), "would_fail": len(failing), "by_sector": sectors,
                         "headline": if_applied[0]},
            "deals": deals, "if_applied": if_applied, "if_not_applied": if_not, "parameters": parameters,
            "checks": [{"check": CK.PARAMS[p]["check"], "label": CK.PARAMS[p]["label"], "param": p} for p in params],
            "deal_types": {"sectors": seg_names, "products": products},
            "method": "Deal Desk policy checks on every pending deal, with and without the change (engine facts, no model)"}


def _direction(op: str, cur: Any, new: Any, unit: str) -> str:
    if cur is None:
        return "new"
    if unit == "grade":
        a = CK.RATINGS.index(cur) if cur in CK.RATINGS else 99
        b = CK.RATINGS.index(new) if new in CK.RATINGS else 99
        return "same" if a == b else ("tighter" if b < a else "looser")
    if abs(float(cur) - float(new)) < 1e-9:
        return "same"
    tighter = float(new) > float(cur) if op == ">=" else float(new) < float(cur)
    return "tighter" if tighter else "looser"
