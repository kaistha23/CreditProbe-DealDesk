"""D6 Negotiation frontier: the give-and-get table for the RM.

Method (deterministic, engine.analyse on the structure the panel reads; N4)
  * Price lever: the margin (bps) on a funded facility, the commission (bps) on an unfunded one.
  * Worth of 1 bp: SVA(price + 100 bps) - SVA(price), divided by 100 (SVA is affine in the price, engine.breakeven_margin).
  * Worth of each concession, in bps of price that leave the bank's SVA unchanged:
      cash margin +10 percentage points of the amount   (lowers LGD, EL and capital)
      tenor one year shorter                            (less lifetime PD and capital; grace capped below the tenor)
      amount SAR 10m smaller                             (less capital and EL; less income)
    worth_bps = (SVA with the concession - SVA as selected) / SVA per bp. Positive = the bank can give that many bps.
  * Gap to the hurdle: -SVA / SVA per bp (bps of price the deal is short; negative = room above the hurdle).
  * Counter-offers: six packages a client usually accepts (price at most +25 bps; cash margin at most +20 pp; tenor
    at most one year shorter; amount at most 10% smaller): price +25; cash +20 & price +10; tenor -1 & price +10;
    amount -10% & price +10; cash +10; cash +10 & tenor -1. Each is priced by engine.analyse (not approximated).
    Acceptable = clears the hurdle with no hard-limit breach. Ranked by SVA (value to the bank); the top three are
    returned. Client cost (labelled assumptions, `CLIENT_COST`): price bps x drawn amount; cash margin x amount x 2%
    carry; one year less tenor = 0.5% of the amount a year of refinancing effort; amount cut = 1% of the cut (unmet need).
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import engine
from backend.dealdesk.intel2 import common as C

CLIENT_COST = {"carry_pct": 2.0, "tenor_pct": 0.5, "amount_pct": 1.0}
PACKAGES = [
    ("price", "Price +25 bps", {"price": 25}),
    ("cash_price", "Cash margin +20% and price +10 bps", {"cash": 20, "price": 10}),
    ("tenor_price", "One year shorter and price +10 bps", {"tenor": -1, "price": 10}),
    ("amount_price", "Amount 10% smaller and price +10 bps", {"amount_pct": -10, "price": 10}),
    ("cash", "Cash margin +10%", {"cash": 10}),
    ("cash_tenor", "Cash margin +10% and one year shorter", {"cash": 10, "tenor": -1}),
]


def _price_key(t: dict[str, Any]) -> str:
    funded = t["facility_type"] not in engine.UNFUNDED and float(t.get("funded_share_pct", 100) or 0) > 0
    return "margin_bps" if funded else "commission_bps"


def _apply(t: dict[str, Any], pk: str, ch: dict[str, Any]) -> dict[str, Any] | None:
    x = dict(t)
    if "price" in ch:
        x[pk] = float(x.get(pk) or 0) + ch["price"]
    if "cash" in ch:
        c = float(x.get("cash_margin_pct") or 0) + ch["cash"]
        if c > 100:
            return None
        x["cash_margin_pct"] = c
    if "tenor" in ch:
        n = int(x["tenor_years"]) + ch["tenor"]
        if n < 1:
            return None
        x["tenor_years"] = n
        if int(x.get("grace_years") or 0) >= n:
            x["grace_years"] = max(0, n - 1)
    if "amount_pct" in ch:
        x["amount"] = round(float(x["amount"]) * (1 + ch["amount_pct"] / 100.0), 4)
    if "amount_abs" in ch:
        a = float(x["amount"]) - ch["amount_abs"]
        if a <= 0:
            return None
        x["amount"] = round(a, 4)
    return x


def _run(p: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    a = engine.analyse(p, t, validate=False)
    return {"sva": a["metrics"]["sva"], "raroc": a["metrics"]["lifetime_raroc"], "hurdle": a["metrics"]["hurdle"],
            "clears": bool(a["metrics"]["clears_hurdle"]), "hard": [c["label"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"],
            "approval": a["approval"]["level"], "terms": a["terms"]}


@functools.lru_cache(maxsize=64)
def _frontier(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    t = engine.merge_terms(p, st["terms"])
    pk = _price_key(t)
    base = _run(p, t)
    up = _run(p, {**t, pk: float(t.get(pk) or 0) + 100})
    per_bp = (up["sva"] - base["sva"]) / 100.0
    fx = engine.fx(t["currency"])
    ten_sar = 10.0 / fx  # SAR 10m in deal currency
    gives = [("cash", "Cash margin +10% of the amount", {"cash": 10}, "pp"),
             ("tenor", "Tenor one year shorter", {"tenor": -1}, "year"),
             ("amount", "Amount SAR 10m smaller", {"amount_abs": ten_sar}, "SAR 10m")]
    worth = []
    for key, label, ch, per in gives:
        tt = _apply(t, pk, ch)
        if tt is None:
            worth.append({"key": key, "label": label, "available": False, "why": "Not possible on this structure."})
            continue
        r = _run(p, tt)
        d = r["sva"] - base["sva"]
        w = d / per_bp if per_bp else None
        worth.append({"key": key, "label": label, "available": True, "per": per,
                      "worth_bps": C.efig(pid, round(w, 1) if w is not None else None, "bps", f"{label}: worth in bps of {pk.split('_')[0]}",
                                          "intel2.frontier", {"structure": st["kind"], **ch}),
                      "sva_change": C.efig(pid, round(d, 4), f"{t['currency']} m", "SVA change", "intel2.frontier", {"structure": st["kind"], **ch}),
                      "raroc_after": C.efig(pid, r["raroc"], "share", "Lifetime RAROC after", "intel2.frontier", {"structure": st["kind"], **ch})})
    gap = -base["sva"] / per_bp if per_bp else None
    amount = float(t["amount"])
    offers = []
    for key, label, ch in PACKAGES:
        tt = _apply(t, pk, ch)
        if tt is None:
            continue
        r = _run(p, tt)
        cost = (ch.get("price", 0) * amount * fx * float(t.get("utilisation_pct") or 100) / 100.0 / 1e4
                + ch.get("cash", 0) / 100.0 * amount * fx * CLIENT_COST["carry_pct"] / 100.0
                + (-ch.get("tenor", 0)) * amount * fx * CLIENT_COST["tenor_pct"] / 100.0
                + (-ch.get("amount_pct", 0)) / 100.0 * amount * fx * CLIENT_COST["amount_pct"] / 100.0)
        offers.append({"key": key, "label": label, "acceptable": r["clears"] and not r["hard"], "hard_breaches": r["hard"],
                       "terms_change": ch, "approval": r["approval"],
                       "sva": C.efig(pid, r["sva"], f"{t['currency']} m", "SVA", "intel2.frontier", {"structure": st["kind"], **ch}),
                       "raroc": C.efig(pid, r["raroc"], "share", "Lifetime RAROC", "intel2.frontier", {"structure": st["kind"], **ch}),
                       "client_cost": C.efig(pid, round(cost, 4), "SAR m a year", "Client cost (assumptions in the method)", "intel2.frontier", {"structure": st["kind"], **ch}),
                       "_sva": r["sva"]})
    ok = sorted([o for o in offers if o["acceptable"]], key=lambda o: (-o["_sva"], o["key"]))
    rest = sorted([o for o in offers if not o["acceptable"]], key=lambda o: (-o["_sva"], o["key"]))
    top = (ok + rest)[:3]
    for i, o in enumerate(top, 1):
        o["rank"] = i
    for o in offers:
        o.pop("_sva", None)
    price_word = "margin" if pk == "margin_bps" else "commission"
    w = {x["key"]: (x["worth_bps"]["value"] if x.get("available") else None) for x in worth}
    if gap is not None and abs(gap) < 1:
        gap_line = f"It sits right at the {C.pct(base['hurdle'])} hurdle: any price cut must be paid for."
    elif gap is not None and gap > 0:
        gap_line = f"It is {gap:,.0f} bps of {price_word} short of the {C.pct(base['hurdle'])} hurdle."
    elif gap is not None:
        gap_line = f"It clears the {C.pct(base['hurdle'])} hurdle with {-gap:,.0f} bps of {price_word} to spare."
    else:
        gap_line = "Price does not move its value on this structure."
    n_ok = len(ok)
    best = top[0] if top else None
    head = (f"On {C.the(st)}: {gap_line} "
            + (f"Best counter-offer: {best['label'].lower()} (RAROC {C.pct(best['raroc']['value'])}, SVA {C.mn(best['sva']['value'], t['currency'], 2)})"
               + ("." if best["acceptable"] else ", which still does not clear.") if best else ""))

    def _wb(k: str) -> str:
        v = w.get(k)
        return "n/a" if v is None else f"{0.0 if abs(v) < 0.5 else v:+,.0f} bps"
    plain = C.plain(
        "What each thing the client can give is worth to the bank, in basis points of price.",
        f"Here, 10% cash margin is worth {_wb('cash')}, one year less tenor {_wb('tenor')}, SAR 10m less {_wb('amount')}; "
        + (f"{n_ok} of {len(offers)} ready offers clear the hurdle." if offers else "no ready offer could be priced."),
        "Lead with offer 1; if the client refuses price, trade cash margin or tenor, not margin.")
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {k: st[k] for k in ("kind", "label", "note")},
           "price_lever": pk, "headline": head, "plain": plain,
           "base": {"sva": C.efig(pid, base["sva"], f"{t['currency']} m", "SVA", "intel2.frontier", C.terms_of(st)),
                    "raroc": C.efig(pid, base["raroc"], "share", "Lifetime RAROC", "intel2.frontier", C.terms_of(st)),
                    "hurdle": C.efig(pid, base["hurdle"], "share", "Hurdle", "intel2.frontier", C.terms_of(st)),
                    "price": C.efig(pid, float(t.get(pk) or 0), "bps", price_word.capitalize(), "intel2.frontier", C.terms_of(st)),
                    "sva_per_bp": C.efig(pid, per_bp, f"{t['currency']} m per bp", "SVA per bp of price", "intel2.frontier", C.terms_of(st)),
                    "gap_bps": C.efig(pid, round(gap, 1) if gap is not None else None, "bps", "Price short of the hurdle (negative = room)",
                                      "intel2.frontier", C.terms_of(st))},
           "worth": worth, "offers": top, "all_offers": offers, "assumptions": CLIENT_COST,
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def frontier(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_frontier(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
