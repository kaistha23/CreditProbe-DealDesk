"""R14 E (K19 #5, K22 #1, K24): the counter-offer that addresses every critical and major finding.

counter_offer(pid):
  1. amount cut to capacity (capacity engine: borrowing base for WC/trade lines, DSCR and leverage for term loans);
  2. priced to clear the hurdle with that amount held (Deal Desk optimiser, closest structure to the ask that clears every
     hard limit and the hurdle; engine breakeven margin when the optimiser finds none);
  3. every open critical and major finding listed with its cure (structure, condition precedent, security, covenant,
     explanation, governance) or "not curable by structure".
It is the Review counter-proposal (structure "recommended") every step, the Recommendation and the papers read.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

from backend.dealdesk import engine, optimizer
from backend.dealdesk.economics import deal as D

_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()
TTL = 600.0


def _structure(pid: str, amount_ccy: float | None) -> tuple[dict[str, Any], str]:
    p = D.proposal(pid)
    fixed = {"amount": round(float(amount_ccy), 4)} if amount_ccy is not None else None
    for soft in (False, True):
        try:
            r = optimizer.optimize(p, fixed=fixed, objective="closest", allow_soft=soft, counter_offers=False)
        except Exception:  # noqa: BLE001 - an infeasible problem falls through to the breakeven price
            r = {}
        best = r.get("closest")
        if best:
            return dict(best["terms"]), "Deal Desk optimiser (closest to the ask clearing the hurdle and every hard limit" + \
                (", soft limits allowed)" if soft else ")")
    t = engine.merge_terms(p, fixed or None)
    try:
        be = engine.breakeven(p, t, "margin_bps")
        if be.get("value") is not None and be.get("feasible"):
            t["margin_bps"] = int(-(-float(be["value"]) // 1))
            return t, "Engine breakeven margin at the hurdle (the optimiser found no structure)"
    except Exception:  # noqa: BLE001
        pass
    return t, "As proposed (no structure clears the hurdle at this amount)"


def counter_offer(pid: str, refresh: bool = False) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    key = (pid, D.version())
    with _LOCK:
        hit = _CACHE.get(key)
    if hit and not refresh and time.time() - hit[0] < TTL:
        return hit[1]
    from backend.dealdesk.capacity import capacity
    from backend.dealdesk.findings.collect import deal_findings
    p = D.proposal(pid)
    fx = engine.fx(p["ask"]["currency"])
    cap = capacity(pid, "ask")
    capacity_cured = True
    if cap["within"]:
        amt = None
        amount_note = "Amount as proposed (within capacity)"
    elif cap["capacity_sar_mn"] > 0:
        amt = math.floor(cap["capacity_sar_mn"] / fx * 10) / 10  # down to 0.1m so the cut amount is within capacity
        amount_note = (f"Amount cut from {p['ask']['currency']} {p['ask']['amount']:,.1f}m to {p['ask']['currency']} {amt:,.1f}m "
                       f"({cap['method_label'].lower()})")
    else:
        amt = None
        capacity_cured = False
        amount_note = "Amount not cut: there is no capacity to cut to (not curable by structure)"
    ask_a = D.analysis(pid, engine.merge_terms(p, None))
    ask_ok = bool(ask_a["metrics"]["clears_hurdle"]) and not any(c["status"] == "breach" and c["kind"] == "hard" for c in ask_a["constraints"])
    if amt is None and ask_ok:
        terms, method = engine.merge_terms(p, None), "As proposed (clears the hurdle and every hard limit)"
    else:
        terms, method = _structure(pid, amt)
    a = D.analysis(pid, terms)
    m = a["metrics"]
    from backend.dealdesk.approval import approval_authority
    from backend.dealdesk.economics.core import covenant_headroom
    appr = approval_authority(pid, terms)
    cap2 = capacity(pid, terms)
    fs = deal_findings(pid)
    cures = []
    for f in fs["findings"]:
        if f["status"] != "open" or f["severity"] not in ("critical", "major"):
            continue
        cu = f.get("cure") or {}
        if f["category"] == "capacity" and not capacity_cured:
            cu = {**cu, "kind": "not_curable", "kind_label": "Not curable by structure"}
        cures.append({"finding_id": f["id"], "title": f["title"], "severity": f["severity"], "category": f["category_label"],
                      "cure_kind": cu.get("kind"), "cure_kind_label": cu.get("kind_label"), "cure": cu.get("text"),
                      "owner": cu.get("owner"), "when": cu.get("when"), "curable": cu.get("kind") != "not_curable"})
    not_cur = [c for c in cures if not c["curable"]]
    cps = [c for c in cures if c["cure_kind"] == "cp"]
    changes = []
    ask = engine.merge_terms(p, None)
    for k in ("amount", "tenor_years", "margin_bps", "upfront_fee_bps", "commission_bps", "cash_margin_pct", "covenant_package",
              "funded_share_pct", "guarantee_coverage_pct"):
        if ask.get(k) != terms.get(k):
            changes.append({"field": k, "ask": ask.get(k), "value": terms.get(k)})
    from backend.dealdesk.deposit_requirement.docs import change_entry  # Round D: the Deposit requirement term's change
    changes += [x for x in [change_entry(ask, terms)] if x]
    ccy = p["ask"]["currency"]
    unfunded = terms.get("facility_type") in ("performance_lg", "financial_lg", "trade_lc") or float(terms.get("funded_share_pct") or 100) <= 0
    price = (f"commission {int(terms.get('commission_bps') or 0)} bps" if unfunded else f"margin {int(terms['margin_bps'])} bps")
    same = not changes
    lead = (f"No counter-offer needed: {ccy} {float(terms['amount']):,.1f}m as proposed" if same else
            f"Counter-offer: {ccy} {float(terms['amount']):,.1f}m"
            + (f" (from {float(ask['amount']):,.1f}m)" if abs(float(terms["amount"]) - float(ask["amount"])) > 1e-6 else ""))
    head = (lead + f", {price}: RAROC {m['lifetime_raroc']:.1%} vs hurdle {m['hurdle']:.1%}"
            + (f"; {len(cures) - len(not_cur)} of {len(cures)} critical and major findings cured" if cures else "; no critical or major finding")
            + (f"; {len(not_cur)} not curable by structure" if not_cur else "") + f"; approval {appr['level']}.")
    out = {"proposal_id": pid, "label": "As proposed (no counter-offer needed)" if same else "Counter-offer (Review)", "headline": head,
           "needed": not same,
           "structure": {"terms": terms, "changes": changes, "method": method, "amount_note": amount_note},
           "economics": {"lifetime_raroc": m["lifetime_raroc"], "hurdle": m["hurdle"], "clears_hurdle": bool(m["clears_hurdle"]),
                         "sva": m["sva"], "sva_basis": "lifetime", "rwa_y1": m["rwa_y1"], "el_y1": m["el_y1"],
                         "dscr_post": m["dscr_post"], "debt_ebitda_post": m["debt_ebitda_post"], "amount_sar_mn": m["amount_sar_mn"]},
           "covenants": covenant_headroom(pid, a),
           "approval": {"level": appr["level"], "rank": appr["rank"], "rule": appr["rule"]},
           "capacity": {"method": cap2["method"], "capacity_sar_mn": cap2["capacity_sar_mn"], "within": cap2["within"],
                        "cured": capacity_cured, "formula": cap["formula"]},
           "cures": cures, "not_curable": not_cur, "conditions_precedent": [c["cure"] for c in cps],
           "source": "backend.dealdesk.findings.counter (capacity engine + optimiser + findings engine)"}
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
