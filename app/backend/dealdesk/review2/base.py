"""The R11 review layer (claims ledger, the rule book, DoA, counter-proposals, conditions as triggers, precedent) for any deal.

R11 deals (DD-nn, the prepared cases PRP-*) run the R11 workspace unchanged. Deals that only the R12 deal registry knows
(PL-nn pipeline applications, the R12 demo deals R12-*) get the same facts built from their engine-ready record
(backend.dealdesk.data.deals.get): the same rules, DoA and precedent run on them; counter-proposals are priced when the
optimiser can resolve the deal and are otherwise left to the Structure step.
"""
from __future__ import annotations

import functools
import re
from typing import Any

from backend.dealdesk import review_facts as RF
from backend.dealdesk import review_workspace as W


def record(sid: str) -> dict[str, Any] | None:
    try:
        from backend.dealdesk.data import deals
        if registry_source(sid) in ("pipeline", "r12_demo"):
            return deals.get(sid)
        return deals.get(sid) if not RF.known(sid) else None
    except Exception:  # noqa: BLE001 - not a registered deal
        return None


def registry_source(sid: str) -> str | None:
    """dd_deal.source for the deal: deal_desk (R11 proposals), pipeline (PL) or r12_demo; None when not registered."""
    try:
        from backend.dealdesk.review2 import publish as P
        rows = P.read("dd_deal", columns=["proposal_id", "source"], proposal_id=sid)
        return rows[0].get("source") if rows else None
    except Exception:  # noqa: BLE001
        return None


def is_r11(sid: str) -> bool:
    """R11 deals run the R11 workspace; deals only the R12 registry holds (PL, R12-*) never touch the R11 proposal file."""
    if registry_source(sid) in ("pipeline", "r12_demo"):
        return False
    return RF.known(sid)


def known(sid: str) -> bool:
    return is_r11(sid) or record(sid) is not None


@functools.lru_cache(maxsize=32)
def _ledger(sid: str, size: int) -> dict[str, Any]:
    from backend.dealdesk.review_ledger import ledger
    p = record(sid)
    try:
        from backend.dealdesk_thread.ingest import write_memo
        data = write_memo(p) if p else None
    except Exception:  # noqa: BLE001 - no memo can be written for this record
        data = None
    return ledger(data) if data else {"lines": [], "claims": [], "sections": [], "counts": {"lines": 0, "figures": 0, "assertions": 0}}


_NO_LEDGER = {"lines": [], "claims": [], "sections": [], "counts": {"lines": 0, "figures": 0, "assertions": 0}}


def facts_from_record(sid: str, p: dict[str, Any], with_ledger: bool = True) -> dict[str, Any]:
    """review_facts._dd_facts for a record the R11 proposal store does not hold."""
    from backend.dealdesk import proposals
    led = _ledger(sid, len(str(p))) if with_ledger else _NO_LEDGER
    o, a = p["obligor"], p["ask"]
    try:
        fx = proposals.fx(a["currency"])
    except Exception:  # noqa: BLE001
        fx = 1.0
    book = RF._book_obligor(o["obligor_id"]) if o.get("existing") and o.get("obligor_id") else None
    acts = [y for y in p["financials"]["years"] if y.get("kind") == "actual"]
    last = acts[-1] if acts else p["financials"]["years"][0]
    covenants = {re.sub(r"[^a-z]+", "_", c["type"].lower()).strip("_"): c["threshold"] for c in (p.get("security") or {}).get("covenants") or []}
    try:
        from backend.dealdesk import engine
        m = engine.analyse(p, None)["metrics"]
        metrics = {k: m.get(k) for k in ("dscr_post", "debt_ebitda_post", "ltv", "lifetime_raroc", "hurdle", "clears_hurdle", "sva",
                                         "day_one_ecl", "rwa_y1", "amount_sar_mn")}
    except Exception:  # noqa: BLE001
        metrics = {}
    claim_index = (lambda cl: {})  # noqa: E731
    if with_ledger:
        from backend.dealdesk.review_ledger import claim_index
    f = {"subject": {"kind": "dd", "id": sid, "name": o["name"], "group": o.get("group_name"), "sector": o.get("sector"),
                     "rating": o.get("internal_rating"), "tier": "", "currency": a["currency"], "as_of": RF.BOOK_AS_OF,
                     "amount_ccy": a["amount"], "amount_sar": a["amount"] * fx, "existing_ccy": (o.get("existing_exposure_sar_mn") or 0.0) / fx},
         "dd": p, "obligor": o, "ask": a, "fin": RF._fin_by_col(p), "fin_last": last, "covenants": covenants,
         "collateral": (p.get("security") or {}).get("collateral") or [], "guarantees": (p.get("security") or {}).get("guarantees") or [],
         "book": book, "connected": RF._connected(p) if o.get("existing") else [], "conduct": None,
         "metrics": metrics, "memo": {k: c["value"] for k, c in claim_index(led["claims"]).items()}, "params": RF._params(), "as_of": RF.BOOK_AS_OF,
         "ledger": led}
    return f


def facts(sid: str, with_ledger: bool = True) -> dict[str, Any]:
    if is_r11(sid):
        return RF.facts(sid)
    p = record(sid)
    if p is None:
        raise KeyError(sid)
    return facts_from_record(sid, p, with_ledger)


def review(sid: str, refresh: bool = False) -> dict[str, Any]:
    if is_r11(sid):
        return W.review(sid, refresh=refresh)
    from backend.dealdesk import review_conditions as RCN
    from backend.dealdesk import review_counter as RC
    from backend.dealdesk import review_precedent as RP
    from backend.dealdesk import review_rules as RR
    f = facts(sid)
    checks = RR.run(f)
    findings = sorted([c for c in checks if c["verdict"] in ("contradicted", "exception")],
                      key=lambda c: (W.SEV_RANK.get(c["severity"] or "minor", 3), 0 if c["verdict"] == "contradicted" else 1, c["rule_id"]))
    doa = RR.required_doa(f, checks)
    # the R11 counter-proposal pricer resolves deals through the R11 proposal store only; for PL and R12 deals the optimiser
    # alternatives are priced in the Structure step (no R11 file is opened for them)
    counter = {"counter_proposals": [], "ask": None, "basis": "Counter-proposals for this deal are priced in the Structure step."}
    _ = RC
    try:
        triggers = RCN.capture_from(sid, f, checks)
        RCN.upsert(triggers, deal_id=sid)
        RCN.remember_facts(sid, f)
        cond = RCN.listing(sid)
    except Exception:  # noqa: BLE001
        cond = {"items": [], "summary": {}}
    m = f.get("metrics") or {}
    prec = RP.precedent({"sector": f["subject"]["sector"], "rating": f["subject"]["rating"], "amount_sar": f["subject"]["amount_sar"]},
                        {"leverage": m.get("debt_ebitda_post"), "dscr": m.get("dscr_post"), "watchlist": (f.get("book") or {}).get("watchlist")})
    by_cat = {cat: {v: sum(1 for c in checks if c["category"] == cat and c["verdict"] == v) for v in RR.VERDICTS} for cat in RR.CATEGORIES}
    return {"subject": f["subject"], "as_of": f["as_of"], "answer": W.answer(findings, counter, doa),
            "memo": {"file": f"{sid} (written from the record)", "generated": True, "sections": W._memo_view(f["ledger"], checks), "counts": f["ledger"]["counts"]},
            "claims": f["ledger"]["claims"], "findings": findings, "checks": checks, "by_category": by_cat,
            "verdicts": {v: sum(1 for c in checks if c["verdict"] == v) for v in RR.VERDICTS}, "doa": doa, "counter": counter,
            "conditions": cond, "precedent": prec}
