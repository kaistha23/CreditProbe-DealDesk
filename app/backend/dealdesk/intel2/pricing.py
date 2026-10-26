"""D9 Pricing benchmark: where the proposed margin sits against the book for the same rating, sector, product and
tenor, and against the breakeven margin.

Method (deterministic)
  * Book: origination.orig_facility (corporate book, margin over the benchmark at origination, tenor, rating at
    origination) joined on exposure_id to cockpit.corp_facility_quarter at the book quarter (sector, product type,
    funded / non-funded class).
  * Peers: same rating bucket (IG / BB / B / CCC-C on the master scale), same sector, same product family (revolving:
    revolving credit, working capital, overdraft; term: term loan, asset and project finance; trade and guarantees:
    trade finance, supply-chain finance and the non-funded class) and same tenor band (<= 12, 13-36, 37-60, > 60
    months). If fewer than 30 peers match, the tenor band is dropped, then the product family, then the sector; the
    basis used is stated.
  * Percentile: share of peers priced strictly below the deal's price plus half the ties (mid-rank), 0-100.
  * Price: the margin on a funded facility, the commission on an unfunded one, on the selected structure.
  * Breakeven: the price at which SVA = 0 (lifetime RAROC = hurdle) on the same structure (engine.breakeven_margin, or
    engine.breakeven on the commission for unfunded lines).
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import engine
from backend.dealdesk.intel2 import common as C

QUARTER = "2026Q2"
MIN_PEERS = 30
FAMILY = {"revolver": "revolving", "term_loan": "term", "performance_lg": "trade", "financial_lg": "trade", "trade_lc": "trade"}
BOOK_FAMILY = {"revolving_credit": "revolving", "working_capital": "revolving", "overdraft": "revolving", "term_loan": "term",
               "asset_finance": "term", "project_finance": "term", "trade_finance": "trade", "supply_chain_finance": "trade"}
FAMILY_LABEL = {"revolving": "revolving and working capital", "term": "term finance", "trade": "trade and guarantees"}


def _band(months: float) -> str:
    return "<=12m" if months <= 12 else "13-36m" if months <= 36 else "37-60m" if months <= 60 else ">60m"


def _bucket(r: str) -> str | None:
    try:
        return C.C.rating_bucket(r)
    except Exception:  # noqa: BLE001 - grades off the master scale (letter scores) are not comparable
        return None


@functools.lru_cache(maxsize=2)
def _book(ver: str):  # noqa: ANN202
    o = C.frame("orig_facility", book="corporate")
    f = C.frame("corp_facility_quarter", reporting_quarter=QUARTER)[["facility_id", "sector", "product_type", "facility_class"]]
    b = o.merge(f, left_on="exposure_id", right_on="facility_id", how="inner")
    b["bucket"] = b["orig_rating"].map(_bucket)
    b["family"] = b["product_type"].map(BOOK_FAMILY)
    b.loc[b["facility_class"] == "non_funded", "family"] = "trade"
    b["band"] = b["tenor_months"].map(_band)
    b["price_bps"] = b["orig_margin_pct"] * 100.0
    return b[b["bucket"].notna()].reset_index(drop=True)


@functools.lru_cache(maxsize=64)
def _pricing(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    t = engine.merge_terms(p, st["terms"])
    tsrc = {"structure": st["kind"]}
    funded = t["facility_type"] not in engine.UNFUNDED and float(t.get("funded_share_pct") or 0) > 0
    pk = "margin_bps" if funded else "commission_bps"
    price = float(t.get(pk) or 0)
    ob = p["obligor"]
    want = {"bucket": _bucket(ob["internal_rating"]), "sector": ob["sector"], "family": FAMILY.get(t["facility_type"], "term"),
            "band": _band(int(t["tenor_years"]) * 12)}
    book = _book("v")
    steps = [("rating", "sector", "product", "tenor"), ("rating", "sector", "product"), ("rating", "sector"), ("rating",)]
    col = {"rating": "bucket", "sector": "sector", "product": "family", "tenor": "band"}
    peers, used = book.iloc[0:0], steps[-1]
    for s in steps:
        m = book
        for k in s:
            m = m[m[col[k]] == want[col[k]]]
        if len(m) >= MIN_PEERS or s == steps[-1]:
            peers, used = m, s
            break
    n = len(peers)
    vals = sorted(peers["price_bps"].tolist())
    below = sum(1 for v in vals if v < price - 1e-9)
    ties = sum(1 for v in vals if abs(v - price) <= 1e-9)
    pctl = 100.0 * (below + 0.5 * ties) / n if n else None
    q = (lambda x: float(peers["price_bps"].quantile(x))) if n else (lambda x: None)
    if funded:
        be = engine.breakeven_margin(p, t)
    else:
        r = engine.breakeven(p, t, "commission_bps")
        be = r.get("value") if r.get("feasible") else None
    a = C.analysis(pid, st["terms"])
    basis = {"rating bucket": want["bucket"], "sector": want["sector"], "product": FAMILY_LABEL[want["family"]], "tenor": want["band"]}
    basis_used = {k: v for k, v in basis.items() if {"rating bucket": "rating", "sector": "sector", "product": "product", "tenor": "tenor"}[k] in used}
    dropped = [k for k in basis if k not in basis_used]
    src_peer = {"domain": "origination", "relation": "orig_facility", "key": {"exposure_id": peers.iloc[0]["exposure_id"]} if n else {},
                "column": "orig_margin_pct", "filter": basis_used, "rows": n, "method": "percentile of orig_margin_pct x 100 among peers"}
    word = "margin" if funded else "commission"
    pos = ("below the cheapest quarter of the book" if pctl is not None and pctl < 25 else "in the middle of the book" if pctl is not None and pctl <= 75
           else "above most of the book" if pctl is not None else "not comparable")
    gap = (price - be) if be is not None else None
    head = (f"The {word} of {price:,.0f} bps on {C.the(st)} sits at the {C.ordinal(pctl)} percentile of {n:,} similar book facilities "
            f"({', '.join(f'{k} {v}' for k, v in basis_used.items())}); median {q(0.5):,.0f} bps. "
            + (f"Breakeven is {be:,.0f} bps, so the price " + ("sits at breakeven." if abs(gap) < 1 else f"is {abs(gap):,.0f} bps {'above' if gap >= 0 else 'below'} it.") if be is not None else
               "No breakeven price exists on this structure (price does not move its value).")) if n else "No comparable book facilities."
    plain = C.plain(
        f"This compares our {word} with what similar borrowers pay, and with the {word} that just pays for the risk.",
        f"At {price:,.0f} bps it is {pos} ({C.ordinal(pctl)} percentile, median {q(0.5):,.0f} bps)"
        + (f"; it needs {be:,.0f} bps to pay for its risk." if be is not None else ".") if n else "No similar book facilities were found.",
        ("Price is below what the risk needs: raise it or add security before committee." if gap is not None and gap < -0.5 else
         "Price pays for the risk; there is little room to cut it." if gap is not None and gap < 10 else
         "There is room to negotiate on price if the client pushes."))
    out = {"proposal_id": pid, "obligor": ob["name"], "structure": {k: st[k] for k in ("kind", "label", "note")}, "price_lever": pk,
           "headline": head, "plain": plain, "basis": basis, "basis_used": basis_used, "dropped": dropped,
           "price": C.efig(pid, price, "bps", f"Proposed {word}", "intel2.pricing", tsrc),
           "percentile": C.fig(round(pctl, 1) if pctl is not None else None, "percentile", src_peer, "Percentile among peers"),
           "peers": C.fig(n, "facilities", src_peer, "Peer facilities"),
           "quartiles": {k: C.fig(round(q(x), 1) if n else None, "bps", src_peer, lab)
                         for k, x, lab in (("p10", 0.1, "10th percentile"), ("p25", 0.25, "25th percentile"), ("p50", 0.5, "Median"),
                                           ("p75", 0.75, "75th percentile"), ("p90", 0.9, "90th percentile"))},
           "breakeven": C.efig(pid, round(be, 1) if be is not None else None, "bps", f"Breakeven {word}",
                               "engine.breakeven_margin" if funded else "engine.breakeven", tsrc),
           "gap_to_breakeven": C.efig(pid, round(gap, 1) if gap is not None else None, "bps", "Price above breakeven (negative = below)", "intel2.pricing", tsrc),
           "raroc": C.efig(pid, a["metrics"]["lifetime_raroc"], "share", "Lifetime RAROC", "engine.analyse", tsrc),
           "hurdle": C.efig(pid, a["metrics"]["hurdle"], "share", "Hurdle", "engine.analyse", tsrc),
           "histogram": _hist(vals, price),
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def _hist(vals: list[float], price: float) -> list[dict[str, Any]]:
    if not vals:
        return []
    w = 10
    lo, hi = w * int(min(vals + [price]) // w), w * (int(max(vals + [price]) // w) + 1)
    out = []
    for x in range(lo, hi, w):
        out.append({"from_bps": x, "to_bps": x + w, "n": sum(1 for v in vals if x <= v < x + w), "deal": x <= price < x + w})
    return out


def pricing(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_pricing(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
