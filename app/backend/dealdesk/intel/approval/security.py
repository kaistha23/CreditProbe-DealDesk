"""Security optimiser (R14 backlog #3, R13 Session IA).

The recovery value (LGD effect) and the capital value (CRM eligibility, RWA) of each security item, and the cheapest
security package that clears the hurdle.

Method
  * Items: the obligor's collateral items and guarantees (dd_deal.proposal_json security block, the same record the
    engine prices), and the cash margin at the optimiser's steps (10%, 20%, 30%). The register view (dd_security:
    perfection, valuation and net-worth dates) is attached where the deal has rows.
  * Standalone value: the ask with no security at all, then the ask with this item alone (engine.analyse, every other
    term as asked). Recovery value = the item's recognised value (value x (1 - haircut), discounted over the recovery
    period at the LGD parameter rate); LGD, EL, RWA, capital, RAROC and SVA are the engine's, as deltas.
  * Marginal value in the ask: the ask without this item (only for items the ask pledges).
  * CRM eligibility (standardised approach): cash and pledged cash are eligible financial collateral (exposure
    reduced); a guarantee is eligible by substitution when its risk weight is below the obligor's; real estate counts
    through the IPRE LTV bands only for real-estate finance; other collateral lowers LGD (economic capital, EL) but not
    the SA risk weight (lgd.collateral.eligible_sa).
  * Cost of a package: the value the client ties up, in SAR million: collateral at market value, a guarantee at the
    covered amount, a cash margin at the cash blocked. The parameter set carries no fee schedule for security, so this
    is the measure (stated in every answer). Packages are evaluated in increasing cost; the first whose engine run
    clears the hurdle and every hard limit is the cheapest package.
  * R14 G (K30) combinations: every package evaluated (cheapest first, up to MAX_EVALS within the time budget) is
    returned with its cost, LGD, RWA, RAROC and SVA, not only each item alone.
  * R14 G (K30) add-ons: security the obligor does not offer today but could add, each run through the same engine on a
    copy of the deal: a guarantee from the group parent (catalogue REQ-PARENT, rated two notches above the obligor),
    a mortgage over real estate worth the facility amount (Real estate haircut and recovery period of the LGD table), and
    the assignment of contract proceeds (receivables assignment at 100%, credit_protection.receivables_assignment).
    Each is shown alone and on top of the ask; they are what-ifs to negotiate, not items on file.
"""
from __future__ import annotations

import copy
import itertools
import time
from typing import Any

from backend.dealdesk import engine, params
from backend.dealdesk.intel.approval import common as C

CASH_STEPS = (10, 20, 30)
MAX_EVALS = 80
MAX_COMBOS = 40
ADD_RE_COVER = 1.0  # hypothetical real estate worth 1.0 x the facility amount


def _bare(t: dict[str, Any]) -> dict[str, Any]:
    return {**t, "collateral_ids": [], "guarantee_id": None, "guarantee_coverage_pct": 0, "cash_margin_pct": 0,
            "receivables_assignment_pct": 0, "insurance_cover_pct": 0}


def _m(a: dict[str, Any]) -> dict[str, float]:
    m = a["metrics"]
    return {"lgd_y1": m["lgd_y1"], "el_lifetime_pv": m["el_lifetime_pv"], "rwa_y1": m["rwa_y1"], "capital_y1": m["capital_y1"],
            "lifetime_raroc": m["lifetime_raroc"], "sva": m["sva"]}


UNITS = {"lgd_y1": "share", "el_lifetime_pv": "SAR m", "rwa_y1": "SAR m", "capital_y1": "SAR m", "lifetime_raroc": "share", "sva": "SAR m"}
LABELS = {"lgd_y1": "LGD year 1", "el_lifetime_pv": "Lifetime EL (PV)", "rwa_y1": "RWA year 1", "capital_y1": "Capital year 1",
          "lifetime_raroc": "Lifetime RAROC", "sva": "SVA"}


def _deltas(pid: str, with_: dict[str, float], without: dict[str, float], terms: dict[str, Any]) -> dict[str, Any]:
    return {k: C.efig(pid, with_[k] - without[k], UNITS[k], f"Change in {LABELS[k]}", "engine.analyse (with minus without)", terms)
            for k in UNITS}


def _items(p: dict[str, Any], ask: dict[str, Any]) -> list[dict[str, Any]]:
    lg = params.rows("lgd")
    out = []
    for c in p["security"]["collateral"]:
        par = lg["collateral"].get(c["type"], {})
        out.append({"id": c["collateral_id"], "kind": "collateral", "type": c["type"], "label": par.get("label", c["type"]),
                    "value_sar_mn": float(c.get("value") or 0) * engine.fx(c.get("currency", "SAR")), "currency": c.get("currency", "SAR"),
                    "in_ask": c["collateral_id"] in ask.get("collateral_ids", []), "haircut": par.get("haircut"),
                    "recovery_years": par.get("recovery_years"), "eligible_sa_param": bool(par.get("eligible_sa"))})
    for g in p["security"]["guarantees"]:
        out.append({"id": g["guarantee_id"], "kind": "guarantee", "type": g["type"],
                    "label": f"{g['type'].title()} guarantee: {g['guarantor']} ({g['guarantor_rating']})",
                    "coverage_pct": float(g.get("coverage_pct") or 100), "in_ask": ask.get("guarantee_id") == g["guarantee_id"]})
    return out


def _with(t: dict[str, Any], it: dict[str, Any], amount_pct: float | None = None) -> dict[str, Any]:
    t = dict(t)
    if it["kind"] == "collateral":
        t["collateral_ids"] = sorted(set(t.get("collateral_ids") or []) | {it["id"]})
    elif it["kind"] == "guarantee":
        t["guarantee_id"], t["guarantee_coverage_pct"] = it["id"], it["coverage_pct"]
    elif it["kind"] == "cash":
        t["cash_margin_pct"] = amount_pct
    return t


def _without(t: dict[str, Any], it: dict[str, Any]) -> dict[str, Any]:
    t = dict(t)
    if it["kind"] == "collateral":
        t["collateral_ids"] = [c for c in t.get("collateral_ids") or [] if c != it["id"]]
    elif it["kind"] == "guarantee":
        t["guarantee_id"], t["guarantee_coverage_pct"] = None, 0
    elif it["kind"] == "cash":
        t["cash_margin_pct"] = 0
    return t


def _eligibility(p: dict[str, Any], it: dict[str, Any], a_with: dict[str, Any], d_rwa: float) -> dict[str, Any]:
    rw = a_with["capital"]["rw_obligor"]
    if it["kind"] == "cash" or it.get("type") == "cash":
        return {"eligible": True, "basis": "Eligible financial collateral: the SA exposure is reduced by the cash (currency-mismatch haircut where it applies)."}
    if it["kind"] == "guarantee":
        g = (a_with["lgd"] or {}).get("guarantee") or {}
        rwg = g.get("sa_rw")
        ok = rwg is not None and rwg < rw
        return {"eligible": bool(ok), "basis": (f"Substitution: guarantor risk weight {rwg:.0%} below the obligor's {rw:.0%}." if ok else
                                                f"No substitution relief: guarantor risk weight {'not recognised' if rwg is None else f'{rwg:.0%}'} "
                                                f"is not below the obligor's {rw:.0%}; the guarantee lowers EL and economic capital only.")}
    if it.get("type") == "real_estate" and p["obligor"].get("real_estate_finance"):
        return {"eligible": True, "basis": "Real-estate finance: the risk weight follows the IPRE LTV bands."}
    return {"eligible": bool(it.get("eligible_sa_param")) or d_rwa < -1e-9,
            "basis": f"{it.get('label', it.get('type'))} is not eligible collateral under the standardised approach: it lowers LGD "
                     "(EL, economic capital) but not the SA risk weight."}


def _cost(it: dict[str, Any], amount_sar: float, cash_pct: float = 0.0) -> float:
    if it["kind"] == "collateral":
        return it["value_sar_mn"]
    if it["kind"] == "guarantee":
        return amount_sar * it["coverage_pct"] / 100.0
    return amount_sar * cash_pct / 100.0


def _eff(pid: str, d_sva: float, cost: float, t: dict[str, Any]) -> dict[str, Any] | None:
    if cost <= 1e-9:
        return None
    return C.efig(pid, d_sva / cost, "SAR m SVA per SAR m tied up", "SVA per SAR tied up", "engine.analyse / cost measure", t)


def _register_rows(pid: str) -> list[dict[str, Any]]:
    out = []
    for r in C.rows("dd_security", proposal_id=pid):
        out.append({"security_id": r["security_id"], "kind": r["kind"], "provider": r["provider"], "perfection_status": r["perfection_status"],
                    "valuation_date": r.get("valuation_date") or None, "net_worth_statement_date": r.get("net_worth_statement_date") or None,
                    "note": r.get("note") or None,
                    "amount": C.rfig("dd_security", r, "amount_mn", f"{r.get('currency') or 'SAR'} m", "Amount") if r.get("amount_mn") is not None else None,
                    "value": C.rfig("dd_security", r, "value_mn", f"{r.get('currency') or 'SAR'} m", "Value") if r.get("value_mn") is not None else None,
                    "net_worth": C.rfig("dd_security", r, "net_worth_mn", f"{r.get('currency') or 'SAR'} m", "Net worth") if r.get("net_worth_mn") is not None else None})
    return out


def optimise(pid: str, max_seconds: float = 20.0) -> dict[str, Any]:
    t0 = time.time()
    pid = C.resolve_id(pid)
    p = C.proposal(pid)
    a_ask = C.analysis(pid)
    ask = a_ask["terms"]
    ccy = ask["currency"]
    amount_sar = float(ask["amount"]) * engine.fx(ccy)
    bare_t = _bare(ask)
    a_bare = C.analysis(pid, bare_t)
    m_bare = _m(a_bare)
    items = _items(p, ask)
    rows = []
    for it in items:
        tw = _with(bare_t, it)
        aw = C.analysis(pid, tw)
        mw = _m(aw)
        rec = next((r["recognised_sar_mn"] for r in aw["lgd"]["collateral"] if r["collateral_id"] == it["id"]), None)
        row = {**{k: v for k, v in it.items() if k not in ("eligible_sa_param",)},
               "value": C.efig(pid, it.get("value_sar_mn"), "SAR m", "Market value", "proposal_json.security") if it["kind"] == "collateral" else None,
               "recovery_value": C.efig(pid, rec, "SAR m", "Recognised recovery value (PV)", "engine.analyse", tw) if rec is not None else None,
               "standalone": _deltas(pid, mw, m_bare, tw),
               "cost_sar_mn": C.efig(pid, _cost(it, amount_sar), "SAR m", "Value tied up", "intel.security cost measure", tw),
               "crm": _eligibility(p, it, aw, mw["rwa_y1"] - m_bare["rwa_y1"]),
               "clears_alone": C.approvable(aw)}
        row["sva_per_sar_tied"] = _eff(pid, mw["sva"] - m_bare["sva"], _cost(it, amount_sar), tw)
        if it["kind"] == "guarantee":
            g = aw["lgd"].get("guarantee") or {}
            row["recovery_value"] = C.efig(pid, aw["metrics"]["ead_y1"] * it["coverage_pct"] / 100 * (1 - (g.get("lgd") or 0)), "SAR m",
                                           "Covered EAD x (1 - guarantor LGD)", "engine.analyse", tw)
        if it["in_ask"]:
            two = _without(ask, it)
            row["marginal_in_ask"] = _deltas(pid, _m(a_ask), _m(C.analysis(pid, two)), ask)
        rows.append(row)
    for pct in CASH_STEPS:
        it = {"id": f"CASH-{pct}", "kind": "cash", "type": "cash_margin", "label": f"Cash margin {pct}%", "in_ask": float(ask["cash_margin_pct"]) == pct}
        tw = _with(bare_t, it, pct)
        aw = C.analysis(pid, tw)
        mw = _m(aw)
        rows.append({**it, "value": C.efig(pid, amount_sar * pct / 100, "SAR m", "Cash blocked", "engine.analyse", tw),
                     "recovery_value": C.efig(pid, aw["lgd"]["cash_margin_sar_mn"], "SAR m", "Cash recognised", "engine.analyse", tw),
                     "standalone": _deltas(pid, mw, m_bare, tw), "cost_sar_mn": C.efig(pid, amount_sar * pct / 100, "SAR m", "Value tied up",
                                                                                         "intel.security cost measure", tw),
                     "crm": _eligibility(p, it, aw, mw["rwa_y1"] - m_bare["rwa_y1"]), "clears_alone": C.approvable(aw),
                     "sva_per_sar_tied": _eff(pid, mw["sva"] - m_bare["sva"], amount_sar * pct / 100, tw)})
    rows.sort(key=lambda r: r["standalone"]["sva"]["value"], reverse=True)

    # cheapest package that clears
    coll = [it for it in items if it["kind"] == "collateral"]
    gopts = [None] + [it for it in items if it["kind"] == "guarantee"]
    packs = []
    for r in range(len(coll) + 1):
        for sub in itertools.combinations(coll, r):
            for g in gopts:
                for cash in (0, *CASH_STEPS):
                    cost = sum(c["value_sar_mn"] for c in sub) + (_cost(g, amount_sar) if g else 0.0) + amount_sar * cash / 100.0
                    packs.append((cost, len(sub) + (g is not None) + (cash > 0), sub, g, cash))
    packs.sort(key=lambda x: (round(x[0], 6), x[1]))
    cheapest, best, evals = None, None, 0
    combos: list[dict[str, Any]] = []
    for cost, n, sub, g, cash in packs:
        if evals >= MAX_EVALS or time.time() - t0 > max_seconds or (cheapest is not None and len(combos) >= MAX_COMBOS):
            break
        t = {**bare_t, "collateral_ids": sorted(c["id"] for c in sub), "guarantee_id": g["id"] if g else None,
             "guarantee_coverage_pct": g["coverage_pct"] if g else 0, "cash_margin_pct": cash}
        a = C.analysis(pid, t)
        evals += 1
        cand = (cost, t, a)
        if len(combos) < MAX_COMBOS:
            combos.append(_package(pid, p, cand, ccy, cleared=C.approvable(a), label=f"Package {len(combos) + 1}"))
        if best is None or a["metrics"]["sva"] > best[2]["metrics"]["sva"]:
            best = cand
        if C.approvable(a) and cheapest is None:
            cheapest = cand
    ask_cost = (sum(it["value_sar_mn"] for it in items if it["kind"] == "collateral" and it["in_ask"])
                + sum(_cost(it, amount_sar) for it in items if it["kind"] == "guarantee" and it["in_ask"])
                + amount_sar * float(ask["cash_margin_pct"]) / 100.0)
    pack = _package(pid, p, cheapest or best, ccy, cleared=cheapest is not None)
    ask_pack = _package(pid, p, (ask_cost, ask, a_ask), ccy, cleared=C.approvable(a_ask), label="As asked")
    if cheapest:
        saving = ask_cost - cheapest[0]
        if C.approvable(a_ask) and saving > 1e-6:
            head = (f"The ask ties up {C.mn(ask_cost)} of security; {C.mn(cheapest[0])} is enough to clear the hurdle and every limit "
                    f"({pack['text']}), so {C.mn(saving)} could be released or kept as headroom.")
        elif C.approvable(a_ask):
            head = f"The security in the ask ({C.mn(ask_cost)} tied up) is already the cheapest package that clears the hurdle and every limit."
        else:
            head = (f"Cheapest package that clears the hurdle and every limit: {pack['text']} ({C.mn(cheapest[0])} tied up, "
                    f"against {C.mn(ask_cost)} in the ask, which does not clear).")
    else:
        bm = best[2]["metrics"] if best else None
        hb = [x["label"] for x in C.hard_breaches(best[2])] if best else []
        head = ("No security package from the obligor's own items clears the hurdle and every limit; the best "
                + (f"reaches lifetime RAROC {C.pct(bm['lifetime_raroc'])} against {C.pct(bm['hurdle'])}" if bm else "is not available")
                + (f" but still breaches {', '.join(hb)}" if hb else "")
                + ". The rest has to come from " + ("the amount or the limit (reverse solver)." if hb else "price or structure (reverse solver)."))
    top = rows[0] if rows else None
    addons = _addons(pid, p, ask, bare_t, a_ask, m_bare, amount_sar, ccy)
    tied = _tied_text(ask_pack, pack, ccy)
    return {"proposal_id": pid, "obligor": p["obligor"]["name"], "currency": ccy, "headline": head,
            "combinations": combos, "add_ons": addons, "tied_up_text": tied,
            "needs_price": cheapest is None,
            "reverse_href": f"/deal-desk/{pid}?intel=reverse",
            "items": rows, "unsecured": {k: C.efig(pid, v, UNITS[k], LABELS[k], "engine.analyse (no security)", bare_t) for k, v in m_bare.items()},
            "ask_package": ask_pack, "cheapest_package": pack if cheapest else None, "best_package": pack if not cheapest else None,
            "most_valuable_item": top and {"id": top["id"], "label": top["label"], "sva": top["standalone"]["sva"]},
            "register": _register_rows(pid), "evaluations": evals, "packages_considered": len(packs),
            "cost_measure": "Value the client ties up (SAR m): collateral at market value, guarantees at the covered amount, cash margin at the cash blocked. "
                            "No security fee schedule exists in the parameter set.",
            "method": __doc__.split("Method", 1)[1].strip(), "seconds": round(time.time() - t0, 2)}


def _package(pid: str, p: dict[str, Any], c: tuple | None, ccy: str, cleared: bool, label: str = "Cheapest package") -> dict[str, Any] | None:
    if c is None:
        return None
    cost, t, a = c
    parts = []
    items = {x["collateral_id"]: x for x in p["security"]["collateral"]}
    for cid in t.get("collateral_ids") or []:
        x = items[cid]
        parts.append(f"{cid} {str(x['type']).replace('_', ' ')} ({x.get('currency', 'SAR')} {float(x.get('value') or 0):,.1f}m)")
    if t.get("guarantee_id"):
        g = next((g for g in p["security"]["guarantees"] if g["guarantee_id"] == t["guarantee_id"]), None)
        parts.append(f"{t['guarantee_id']} {g['type'] if g else ''} guarantee at {float(t['guarantee_coverage_pct']):.0f}%".replace("  ", " "))
    if float(t.get("cash_margin_pct") or 0):
        parts.append(f"cash margin {float(t['cash_margin_pct']):.0f}%")
    m = a["metrics"]
    return {"label": label, "clears": cleared, "text": ", ".join(parts) or "no security",
            "collateral_ids": t.get("collateral_ids") or [], "guarantee_id": t.get("guarantee_id"), "cash_margin_pct": t.get("cash_margin_pct"),
            "cost_sar_mn": C.efig(pid, cost, "SAR m", "Value tied up", "intel.security cost measure", t),
            "lifetime_raroc": C.efig(pid, m["lifetime_raroc"], "share", "Lifetime RAROC", "engine.analyse", t),
            "lgd_y1": C.efig(pid, m["lgd_y1"], "share", "LGD year 1", "engine.analyse", t),
            "rwa_y1": C.efig(pid, m["rwa_y1"], "SAR m", "RWA year 1", "engine.analyse", t),
            "sva": C.efig(pid, m["sva"], f"{ccy} m", "SVA", "engine.analyse", t),
            "hard_breaches": [x["label"] for x in C.hard_breaches(a)]}



# ------------------------------------------------------------------ R14 G (K30): what the obligor could add

def _analyse_mod(p_mod: dict[str, Any], terms: dict[str, Any]) -> dict[str, Any]:
    a = engine.analyse(p_mod, terms, validate=False)
    return {k: v for k, v in a.items() if not k.startswith("_")}


def _addon_specs(p: dict[str, Any], amount_sar: float) -> list[dict[str, Any]]:
    """The items the obligor could add: (id, label, how the deal and the terms change, value tied up)."""
    out: list[dict[str, Any]] = []
    ob = p["obligor"]
    cat = params.rows("credit_protection").get("guarantee_catalogue", {})
    if "REQ-PARENT" in cat and (ob.get("group_id") or not cat["REQ-PARENT"].get("requires_group")):
        from backend.dealdesk.levers import requested_rating
        out.append({"id": "ADD-PARENT", "kind": "guarantee",
                    "label": f"Guarantee from {ob.get('group_name') or 'the group parent'}",
                    "detail": f"covering 100%, guarantor rated {requested_rating(p, 'REQ-PARENT')} (two notches above the obligor)",
                    "terms": {"guarantee_id": "REQ-PARENT", "guarantee_coverage_pct": 100}, "p_add": None, "cost": amount_sar})
    re_val = round(amount_sar * ADD_RE_COVER, 1)
    out.append({"id": "ADD-RE", "kind": "collateral", "label": "Mortgage over real estate",
                "detail": f"a property worth SAR {re_val:,.1f}m, equal to the facility amount, at the real-estate haircut and recovery period",
                "terms": {}, "p_add": {"collateral_id": "ADD-RE", "type": "real_estate", "value": re_val, "currency": "SAR",
                                       "valuation_date": None, "pledged_in_ask": False}, "cost": re_val})
    ra = params.rows("credit_protection").get("receivables_assignment") or {}
    pct = float(min(100.0, ra.get("max_pct", 100)))
    out.append({"id": "ADD-ASSIGN", "kind": "assignment", "label": "Assignment of contract proceeds",
                "detail": f"{pct:.0f}% of the contract proceeds paid to an account with us and assigned to the bank",
                "terms": {"receivables_assignment_pct": pct}, "p_add": None, "cost": amount_sar * pct / 100.0})
    return out


def _addons(pid: str, p: dict[str, Any], ask: dict[str, Any], bare_t: dict[str, Any], a_ask: dict[str, Any],
            m_bare: dict[str, float], amount_sar: float, ccy: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    m_ask = _m(a_ask)
    for sp in _addon_specs(p, amount_sar):
        pm = copy.deepcopy(p)
        if sp["p_add"]:
            pm["security"]["collateral"] = list(pm["security"]["collateral"]) + [sp["p_add"]]
        def _t(base: dict[str, Any]) -> dict[str, Any]:
            t = {**base, **sp["terms"]}
            if sp["p_add"]:
                t["collateral_ids"] = sorted(set(base.get("collateral_ids") or []) | {sp["p_add"]["collateral_id"]})
            return t
        if sp["kind"] == "guarantee" and ask.get("guarantee_id"):
            on_ask = None  # the ask already carries a guarantee: only one guarantee per facility in the engine
        else:
            on_ask = _t(ask)
        try:
            a_alone = _analyse_mod(pm, _t(bare_t))
            a_on = _analyse_mod(pm, on_ask) if on_ask else None
        except Exception:  # noqa: BLE001 - an add-on the engine cannot price is left out, not invented
            continue
        mw = _m(a_alone)
        note = "what-if on a copy of the deal: not an item on file"
        row = {"id": sp["id"], "kind": sp["kind"], "label": sp["label"], "detail": sp["detail"], "hypothetical": True,
               "cost_sar_mn": C.efig(pid, sp["cost"], "SAR m", "Value tied up", "intel.security add-on", {"add_on": sp["id"]}),
               "standalone": {k: C.efig(pid, mw[k] - m_bare[k], UNITS[k], f"Change in {LABELS[k]}", "engine.analyse (add-on, with minus without)",
                                        {"add_on": sp["id"], "note": note}) for k in UNITS},
               "clears_alone": C.approvable(a_alone)}
        if a_on is not None:
            mo = _m(a_on)
            row["on_ask"] = {k: C.efig(pid, mo[k] - m_ask[k], UNITS[k], f"Change in {LABELS[k]} on top of the ask",
                                       "engine.analyse (ask + add-on minus ask)", {"add_on": sp["id"], "note": note}) for k in UNITS}
            row["on_ask_raroc"] = C.efig(pid, mo["lifetime_raroc"], "share", "Lifetime RAROC, ask + add-on", "engine.analyse",
                                         {"add_on": sp["id"], "note": note})
            row["clears_on_ask"] = C.approvable(a_on)
            row["text"] = (f"{sp['label']}, {sp['detail']}: on top of the ask, lifetime RAROC {C.pct(mo['lifetime_raroc'])} "
                           f"({'clears' if C.approvable(a_on) else 'does not clear'} the hurdle {C.pct(a_on['metrics']['hurdle'])}), "
                           f"LGD {(mo['lgd_y1'] - m_ask['lgd_y1']) * 100:+.1f} points, SVA {mo['sva'] - m_ask['sva']:+,.2f}m a year.")
        else:
            row["text"] = (f"{sp['label']}, {sp['detail']}: alone, lifetime RAROC {C.pct(mw['lifetime_raroc'])}, "
                           f"SVA {mw['sva'] - m_bare['sva']:+,.2f}m a year against no security.")
        rows.append(row)
    rows.sort(key=lambda r: (r.get("on_ask") or r["standalone"])["sva"]["value"], reverse=True)
    return rows


def _tied_text(ask_pack: dict[str, Any] | None, pack: dict[str, Any] | None, ccy: str) -> str:
    """'Tied up' in plain words: the client's assets pledged in the ask (and in the cheapest clearing package)."""
    def _one(pk: dict[str, Any]) -> str:
        return f"{C.mn(pk['cost_sar_mn']['value'])}, that is {pk['text']}"
    s = ("'Tied up' is the value of the client's own assets pledged to the bank, which the client cannot use elsewhere: "
         + (f"the ask ties up {_one(ask_pack)}" if ask_pack else "the ask ties up nothing"))
    if pack and ask_pack and abs(pack["cost_sar_mn"]["value"] - ask_pack["cost_sar_mn"]["value"]) > 1e-6:
        s += f"; the {'cheapest package that clears' if pack.get('clears') else 'best package'} ties up {_one(pack)}"
    return s + "."
