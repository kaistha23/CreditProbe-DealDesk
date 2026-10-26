"""D12 Group contagion on the deal: connected parties in Stage 3 or litigation, their exposure, and what happens to
this deal if they fail.

Method (deterministic; reads the R12 group facts, which read Borrower 360 and the book through Data Domains)
  * Connected parties: backend.dealdesk.group.service.bundle(deal).facts.connected_parties - every borrower linked to
    the obligor by group membership, guarantee, shared collateral, board or ownership, with its book status at the
    quarter (classified = Stage 3 / default / unlikely to pay; in litigation; in arrears; watchlist) and EAD.
  * Adverse = classified, in litigation or in arrears. Each adverse party is "failed" one at a time, then all together.
  * Transmission to this deal, per link (the R13 contagion-map rules, backend.intel.network.contagion):
      guarantee given by the obligor for the party -> the guarantee is called: new debt of the guaranteed amount,
                                                      Debt/EBITDA rises by amount / EBITDA (latest actual year)
      guarantee received from the party             -> the support is lost: the deal is re-priced without it
      group (parent / controlled)                   -> cross-default: 2 notches; affiliate 1 notch
      any other link to a failed name               -> 1 notch (watchlist by association)
      shared collateral                             -> collateral value falls by the calibrated collateral shock
    The notches and collateral shock are applied by engine.analyse(shocks=...) on the selected structure; the result
    is RAROC, SVA, whether it still clears the hurdle and the approval level after.
  * Conditions: the group-governance flags' conditions (e.g. no new money while the party is classified).
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import engine
from backend.dealdesk.intel2 import common as C

ADVERSE = ("classified", "in litigation", "in arrears")
NOTCHES = {"group": 2, "parent": 2, "subsidiary": 2, "sister": 1, "affiliate": 1}
COLLATERAL_SHOCK = -0.25  # shared collateral: forced-sale fall when a co-claimant fails (R12 ladder, severe)
QUARTER = "2026Q2"


def _book_src(relation: str, column: str, **key: Any) -> dict[str, Any]:
    from backend.dealdesk.group import sources as S
    loc = S.locate(relation) or {}
    return {"domain": loc.get("domain"), "relation": relation, "key": key, "column": column, "period": QUARTER}


def _bundle(pid: str) -> dict[str, Any]:
    from backend.dealdesk.group import service
    return service.bundle(pid)


def _effect(p: dict[str, Any], t: dict[str, Any], notches: int, cshock: float, drop_guarantor: str | None) -> dict[str, Any]:
    tt = dict(t)
    if drop_guarantor and tt.get("guarantee_id"):
        g = next((g for g in p["security"]["guarantees"] if g["guarantee_id"] == tt["guarantee_id"]), None)
        if g and drop_guarantor.lower() in str(g.get("guarantor", "")).lower():
            tt["guarantee_id"], tt["guarantee_coverage_pct"] = None, 0
    a = engine.analyse(p, tt, validate=False, shocks={"notches": notches, "collateral_shock": cshock} if (notches or cshock) else None)
    m = a["metrics"]
    return {"raroc": m["lifetime_raroc"], "sva": m["sva"], "clears": bool(m["clears_hurdle"]), "approval": a["approval"]["level"],
            "hard": [c["label"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"],
            "rating": a.get("pd", {}).get("rating_used") if a.get("pd") else None, "lev": C.finite(m["debt_ebitda_post"]),
            "dscr": C.finite(m["dscr_post"])}


def _stat(r: dict[str, Any]) -> str:
    bits = [r["status"]] + ([f"stage {r['worst_stage']}"] if r.get("worst_stage") else [])
    return ", ".join(bits)


@functools.lru_cache(maxsize=64)
def _contagion(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    t = engine.merge_terms(p, st["terms"])
    tsrc = {"structure": st["kind"]}
    b = _bundle(pid)
    facts = b.get("facts") or {}
    cp = facts.get("connected_parties") or {}
    gu = (facts.get("guarantees") or {}).get("rows") or []
    sc = (facts.get("shared_collateral") or {}).get("rows") or []
    me = (facts.get("obligor") or {}).get("borrower_id") or p["obligor"].get("obligor_id")
    base = _effect(p, t, 0, 0.0, None)
    la = engine.latest_actual(p)
    ebitda = C.finite(la.get("ebitda"))
    flags = [f for f in ((b.get("governance") or {}).get("flags") or []) if str(f.get("code", "")).startswith("GOV-CONN")]
    parties, adverse = [], []
    for r in cp.get("rows") or []:
        status = r.get("status") or "performing"
        links = r.get("links") or []
        bid = r["borrower_id"]
        if str(bid).startswith("CB"):
            exp_src = _book_src("corp_facility_quarter", "ead_sar_mn", borrower_id=bid, reporting_quarter=QUARTER)
        else:  # R12 fictional group entities: their exposure is on the deal's group-exposure table
            ge = C.rows("dd_group_exposure", proposal_id=pid, entity_id=bid)
            exp_src = C.row_source("dd_group_exposure", ge[0], "outstanding_mn") if ge else C.deal_source(pid, "group.service.bundle")
        row = {"borrower_id": bid, "name": r["name"], "status": status, "worst_stage": r.get("worst_stage"),
               "in_litigation": bool(r.get("in_litigation")), "classified_basis": r.get("classified_basis") or [], "links": links,
               "rating": r.get("rating"), "max_dpd_4q": r.get("max_dpd_4q"), "href": r.get("href"),
               "exposure": C.fig(round(float(r.get("ead") or 0), 4), "SAR m", exp_src, "Bank exposure to the party (EAD, sum of its facilities)"),
               "adverse": status in ADVERSE}
        if row["adverse"]:
            given = sum(float(g.get("amount") or 0) for g in gu if g.get("direction") == "given" and g.get("guaranteed_id") == bid)
            received = any(g.get("direction") == "received" and g.get("guarantor_id") == bid for g in gu)
            shared = any(bid in (x.get("other_ids") or [x.get("borrower_id")]) for x in sc) if sc else False
            n = max([NOTCHES.get(l, 0) for l in links] + [1])
            eff = _effect(p, t, n, COLLATERAL_SHOCK if shared else 0.0, r["name"] if received else None)
            lev_add = (given / ebitda) if (given and ebitda) else 0.0
            ch = []
            if given:
                ch.append(f"the obligor's guarantee of {C.mn(given)} for it is called (Debt/EBITDA +{lev_add:.2f}x)")
            if received:
                ch.append("its guarantee for this deal is lost")
            if shared:
                ch.append("shared collateral is sold at a discount")
            ch.append(f"{n} notch{'es' if n != 1 else ''} of downgrade by association")
            row["effect"] = {
                "channels": ch, "notches": n, "guarantee_called": C.fig(round(given, 4), "SAR m",
                                                                       _book_src("col_guarantee", "amount_sar_mn", obligor_id=bid) if given else exp_src,
                                                                       "Guarantee the obligor gave for it"),
                "raroc_after": C.efig(pid, eff["raroc"], "share", "Lifetime RAROC if it fails", "intel2.contagion", {**tsrc, "notches": n}),
                "sva_after": C.efig(pid, eff["sva"], f"{t['currency']} m", "SVA if it fails", "intel2.contagion", {**tsrc, "notches": n}),
                "leverage_after": C.efig(pid, round((eff["lev"] or 0) + lev_add, 4) if eff["lev"] is not None else None, "x",
                                         "Debt/EBITDA if it fails", "intel2.contagion", {**tsrc, "notches": n, "guarantee_called": given}),
                "clears_after": eff["clears"], "approval_after": eff["approval"], "hard_after": eff["hard"]}
            adverse.append((row, n, given, received, shared))
        parties.append(row)
    combined = None
    if adverse:
        n = min(3, max(a[1] for a in adverse) + (len(adverse) - 1))
        given = sum(a[2] for a in adverse)
        eff = _effect(p, t, n, COLLATERAL_SHOCK if any(a[4] for a in adverse) else 0.0,
                      next((a[0]["name"] for a in adverse if a[3]), None))
        combined = {"parties": [a[0]["name"] for a in adverse], "notches": n,
                    "raroc_after": C.efig(pid, eff["raroc"], "share", "Lifetime RAROC if all adverse parties fail", "intel2.contagion", {**tsrc, "notches": n}),
                    "sva_after": C.efig(pid, eff["sva"], f"{t['currency']} m", "SVA if all fail", "intel2.contagion", {**tsrc, "notches": n}),
                    "clears_after": eff["clears"], "approval_after": eff["approval"], "hard_after": eff["hard"],
                    "guarantees_called": round(given, 4)}
    adv_ead = sum(float(a[0]["exposure"]["value"] or 0) for a in adverse)
    conds = [{"text": f["condition"]["text"], "kind": f["condition"].get("kind"), "due": f["condition"].get("due"), "finding_id": f.get("finding_id")}
             for f in flags if f.get("condition")]
    if adverse:
        adverse.sort(key=lambda a: (-float(a[0]["exposure"]["value"] or 0), a[0]["name"]))
        names = ", ".join(f"{a[0]['name']} ({_stat(a[0])}, linked by {', '.join(a[0]['links'])})" for a in adverse)
        head = (f"{len(adverse)} connected part{'ies are' if len(adverse) != 1 else 'y is'} in trouble: {names}; bank exposure {C.mn(adv_ead)}. "
                f"If {'they fail' if len(adverse) > 1 else 'it fails'}, this deal's RAROC goes from {C.pct(base['raroc'])} to "
                f"{C.pct(combined['raroc_after']['value'])}" + (" and it no longer clears the hurdle." if not combined["clears_after"] and base["clears"]
                                                             else " and it still clears the hurdle." if combined["clears_after"] else "; it does not clear the hurdle either way."))
        first = adverse[0][0]
        plain = C.plain(
            "This checks whether companies linked to the borrower are already in trouble and what their failure would do to this deal.",
            f"{first['name']} is {_stat(first)} with {C.mn(first['exposure']['value'])} owed to us; "
            f"if it fails, RAROC falls to {C.pct(first['effect']['raroc_after']['value'])}.",
            (f"Make it a condition: {C.clip(conds[0]['text'].split(';')[0].rstrip('.'), 14)}." if conds else "Add a cross-default and agree a regularisation plan before limits are loaded."))
    else:
        head = (f"No connected party of {p['obligor']['name']} is classified, in litigation or in arrears "
                f"({len(parties)} connected part{'ies' if len(parties) != 1 else 'y'} checked).")
        plain = C.plain("This checks whether companies linked to the borrower are already in trouble and what their failure would do to this deal.",
                        f"None of the {len(parties)} connected parties is in Stage 3, litigation or arrears today.",
                        "Nothing to add for the group; keep the cross-default clause standard.")
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {k: st[k] for k in ("kind", "label", "note")},
           "headline": head, "plain": plain, "parties": sorted(parties, key=lambda r: (not r["adverse"], r["name"])),
           "adverse_count": len(adverse),
           "adverse_exposure": C.fig(round(adv_ead, 4), "SAR m", _book_src("corp_facility_quarter", "ead_sar_mn", reporting_quarter=QUARTER),
                                     "Bank exposure to the adverse parties"),
           "base": {"raroc": C.efig(pid, base["raroc"], "share", "Lifetime RAROC today", "intel2.contagion", tsrc),
                    "clears": base["clears"], "approval": base["approval"]},
           "combined": combined, "conditions": conds, "sources": cp.get("source") or [],
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def contagion(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_contagion(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
