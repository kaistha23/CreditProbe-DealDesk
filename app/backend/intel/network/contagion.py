"""Contagion map (R14 backlog #9): if a named borrower fails, who else is hit, by how much, and through what.

Channels, each from a booked relation at the quarter (rel-saudi-v1) and each with a stated transmission rule:

  guarantee   facilities the failed name guarantees lose that support: LGD rises by GUARANTEE_LGD_RELIEF of the
              guaranteed share of EAD; at risk = the guaranteed amount (capped at EAD)
  group       group members cross-default: controlled members (parent, >= 50% held) CONTROL_NOTCHES notches, affiliates
              one; at risk = EAD x (1 controlled, 0.5 affiliate)
  collateral  co-claimants on an asset the failed name also pledged: a forced sale realises less, their collateral
              falls by the calibrated collateral shock; at risk = their claim x that fall
  supplier    suppliers that lose the failed name as a buyer: notches by revenue share (>= 30%: 2, 10-30%: 1, below:
              listed only); at risk = EAD x revenue share
  customer    buyers that lose it as a supplier (>= 30% of purchases: 1 notch); at risk = EAD x purchase share / 2
  employer    contractors paid by the same project employer as the failed contractor (or, when the failed name is
              itself the employer, the contractors it pays — then they are its suppliers): listed with exposure, not
              shocked (a co-contractor's failure is an employer delay risk, not a loss)

The failed name itself goes to Stage 3 (default). All ECL numbers come from the What-If engine in one run.
"""
from __future__ import annotations

from typing import Any

import math

from backend.b360.store import clean
from backend.intel.network import calibration, common, links, whatif_bridge as wb, writer

GUARANTEE_LGD_RELIEF = 0.5
CONTROL_NOTCHES = 2
SUPPLIER_BANDS = ((30.0, 2), (10.0, 1))
BUYER_SHARE = 30.0
MAX_DRAWN = 40
KINDS = {"focal": "Failed name", "guarantee": "Guaranteed by it", "group": "Same group", "collateral": "Shared collateral",
         "supplier": "Sells to it", "customer": "Buys from it", "employer": "Same project employer"}


class ContagionError(ValueError):
    pass


def radial(focal: str, drawn: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """A star: the failed name in the centre, linked names on two rings, one arc per channel (deterministic).

    Arcs are sized by the number of names in the channel; inside an arc names alternate between the inner and outer
    ring so labels do not sit on each other. Positions in [-1, 1].
    """
    order = ("guarantee", "group", "collateral", "supplier", "customer", "employer")
    by: dict[str, list[dict[str, Any]]] = {}
    for x in drawn:
        by.setdefault(x["channels"][0] if x["channels"][0] in order else "employer", []).append(x)
    total = max(1, len(drawn))
    pos: dict[str, tuple[float, float]] = {focal: (0.0, 0.0)}
    start = math.pi / 2
    for ch in order:
        xs = by.get(ch, [])
        if not xs:
            continue
        span = 2 * math.pi * len(xs) / total
        for i, x in enumerate(xs):
            a = start + span * (i + 0.5) / len(xs)
            r = 0.62 if i % 2 == 0 else 0.98
            pos[x["borrower_id"]] = (round(r * math.cos(a), 4), round(r * math.sin(a), 4))
        start += span
    return pos


def _add(names: dict[str, dict[str, Any]], bid: str, channel: str, exposure: float, at_risk: float, why: str,
         notches: int = 0, **extra: Any) -> None:
    n = names.setdefault(bid, {"borrower_id": bid, "channels": [], "exposure": 0.0, "at_risk": 0.0, "notches": 0, "why": []})
    n["channels"].append(channel)
    n["exposure"] = max(n["exposure"], exposure)
    n["at_risk"] = max(n["at_risk"], at_risk)
    n["notches"] = max(n["notches"], notches)
    n["why"].append(why)
    for k, v in extra.items():
        n.setdefault(k, v)


def contagion(borrower: str, period: str | None = None, severity: str = "moderate", publish: bool = True) -> dict[str, Any]:
    period = common.resolve_quarter(period)
    hit = common.find_borrower(period, borrower)
    if not hit:
        raise ContagionError(f"No corporate book borrower matches {borrower!r}.")
    focal = hit[0]["borrower_id"]
    cal = calibration.table()
    if severity not in calibration.LEVELS:
        raise ContagionError(f"Severity is one of {', '.join(calibration.LEVELS)}.")
    coll_shock = float(cal["drivers"]["collateral"][severity])
    attrs0 = common.borrowers(period, [focal])
    if focal not in attrs0:
        raise ContagionError(f"{focal} has no row at {period}.")
    fa = attrs0[focal]
    names: dict[str, dict[str, Any]] = {}
    lgd_steps: dict[int, list[str]] = {}
    coll_facilities: list[str] = []
    # guarantees given by the failed name
    for g in links.guarantees_by(period, focal):
        ead = float(g["facility_ead"] or 0.0)
        amt = float(g["guarantee_amount_sar_mn"] or 0.0)
        if g["obligor_id"] == focal:
            continue
        share = min(1.0, amt / ead) if ead else 0.0
        pp = int(round(100 * GUARANTEE_LGD_RELIEF * share))
        if pp > 0 and g["facility_id"]:
            lgd_steps.setdefault(pp, []).append(g["facility_id"])
        _add(names, g["obligor_id"], "guarantee", ead, min(amt, ead),
             f"{g['facility_id']} guaranteed by it for {writer.m(amt, 2)}", facility_id=g["facility_id"])
    # group
    for mem in links.group_members(period, focal):
        b = mem["borrower_id"]
        if b == focal:
            continue
        controlled = (mem["role"] == "parent") or (mem.get("parent_borrower_id") == focal and (mem.get("ownership_pct") or 0) >= 50) \
            or (mem["role"] == "subsidiary" and (mem.get("ownership_pct") or 0) >= 50)
        _add(names, b, "group", 0.0, 0.0, f"{mem['role']} in {mem['group_name']}"
             + (f" ({mem['ownership_pct']:.0f}% held)" if mem.get("ownership_pct") else ""),
             CONTROL_NOTCHES if controlled else 1, weight=1.0 if controlled else 0.5)
    # shared collateral
    assets: dict[str, list[dict[str, Any]]] = {}
    for s in links.shared_collateral(period, focal):
        assets.setdefault(s["collateral_id"], []).append(s)
    for cid, claims in assets.items():
        for s in claims:
            if s["borrower_id"] == focal:
                continue
            claim = float(s["claim_sar_mn"] or 0.0)
            coll_facilities.append(s["facility_id"])
            _add(names, s["borrower_id"], "collateral", claim, claim * abs(coll_shock) / 100,
                 f"shares {cid} ({s['collateral_type']}), claim {writer.m(claim, 2)}")
    # suppliers and customers
    contractors_paid = []
    for e in links.supplies_into(period, [focal]):
        share = float(e["revenue_share_pct"] or 0.0)
        n = next((k for thr, k in SUPPLIER_BANDS if share >= thr), 0)
        tag = "employer" if e["supplier_sector"] == links.CONTRACTOR_SECTOR and fa["sector"] != links.CONTRACTOR_SECTOR else "supplier"
        if tag == "employer":
            contractors_paid.append(e["supplier_id"])
        _add(names, e["supplier_id"], "supplier" if tag == "supplier" else "employer", 0.0, 0.0,
             (f"contractor paid by it, {share:.1f}% of revenue" if tag == "employer" else f"sells {share:.1f}% of its revenue to it"),
             n, weight=share / 100)
    for e in links.supplies_from(period, [focal]):
        share = float(e["purchase_share_pct"] or 0.0)
        _add(names, e["buyer_id"], "customer", 0.0, 0.0, f"buys {share:.1f}% of its inputs from it",
             1 if share >= BUYER_SHARE else 0, weight=share / 200)
    # contractors of the same project employer (the failed name is a contractor)
    if fa["sector"] == links.CONTRACTOR_SECTOR:
        employers = [e["buyer_id"] for e in links.supplies_from(period, [focal]) if e["buyer_sector"] != links.CONTRACTOR_SECTOR]
        for e in links.supplies_into(period, employers):
            if e["supplier_id"] == focal or e["supplier_sector"] != links.CONTRACTOR_SECTOR:
                continue
            _add(names, e["supplier_id"], "employer", 0.0, 0.0, f"also a contractor of {e['buyer_id']}", 0, weight=0.0,
                 employer_id=e["buyer_id"])
    attrs = common.borrowers(period, list(names) + [focal])
    for bid, n in names.items():
        a = attrs.get(bid, {})
        n.update({"name": a.get("borrower_name"), "sector": a.get("sector"), "rating": a.get("rating_current"),
                  "ews_band": a.get("ews_band"), "ead": a.get("ead", 0.0), "stage": a.get("worst_stage")})
        if not n["exposure"]:
            n["exposure"] = n["ead"]
        if "weight" in n and not n["at_risk"]:
            n["at_risk"] = n["ead"] * float(n["weight"])
    names = {k: v for k, v in names.items() if k in attrs}
    # one What-If run: the failed name defaults, the channels transmit
    steps = [wb.step(f"{fa['borrower_name']} defaults", {"stage": [{"from": 1, "to": 3, "share": 100},
                                                                   {"from": 2, "to": 3, "share": 100}]}, owners=[focal])]
    by_notch: dict[int, list[str]] = {}
    for bid, n in names.items():
        if n["notches"]:
            by_notch.setdefault(n["notches"], []).append(bid)
    for k, ids in sorted(by_notch.items()):
        steps.append(wb.step(f"Linked names −{k} notch", {"rating": k}, owners=ids))
    for pp, fids in sorted(lgd_steps.items()):
        steps.append(wb.step(f"Guarantee lost: LGD +{pp}pp", {"lgd": {"mode": "pp", "value": pp}}, exposures=fids))
    if coll_facilities and coll_shock:
        steps.append(wb.step(f"Shared collateral {coll_shock:+g}%", {"collateral": coll_shock}, exposures=coll_facilities))
    res = wb.run(period, steps, name=f"Failure of {focal}")
    per = wb.by_owner(res["rows"])
    rows = res["rows"]
    others = rows[rows["owner_id"] != focal]
    tot_o = wb.totals(others)
    focal_d = float(per.loc[focal, "d_ecl"]) if focal in per.index else 0.0
    out_names = []
    for bid, n in names.items():
        r = per.loc[bid] if bid in per.index else None
        out_names.append({"borrower_id": bid, "name": n["name"], "sector": n["sector"], "rating": n["rating"],
                          "ews_band": n["ews_band"], "channels": sorted(set(n["channels"])), "why": "; ".join(n["why"][:3]),
                          "exposure": float(n["exposure"]), "ead": float(n["ead"]), "at_risk": float(n["at_risk"]),
                          "notches": n["notches"], "d_ecl": float(r["d_ecl"]) if r is not None else 0.0,
                          "to_stage2": int(r["to_stage2"]) if r is not None else 0,
                          "to_stage3": int(r["to_stage3"]) if r is not None else 0,
                          "href": f"/borrower-360?domain=corporate&customer_id={bid}"})
    out_names.sort(key=lambda x: (-x["d_ecl"], -x["at_risk"], x["borrower_id"]))
    channels = []
    for ch in ("guarantee", "group", "collateral", "supplier", "customer", "employer"):
        sub = [x for x in out_names if ch in x["channels"]]
        channels.append({"channel": ch, "label": KINDS[ch], "names": len(sub), "exposure": sum(x["exposure"] for x in sub),
                         "at_risk": sum(x["at_risk"] for x in sub), "d_ecl": sum(x["d_ecl"] for x in sub)})
    totals = {"names": len(out_names), "exposure": sum(x["exposure"] for x in out_names),
              "at_risk": sum(x["at_risk"] for x in out_names), "d_ecl_second": tot_o["ecl_change"],
              "d_ecl_focal": focal_d, "to_stage2": tot_o["to_stage2_n"], "to_stage3": tot_o["to_stage3_n"],
              "focal_ead": fa["ead"], "total_exposure_with_focal": fa["ead"] + sum(x["exposure"] for x in out_names)}
    # the network view: Plotly-ready coordinates from a deterministic star layout
    drawn = out_names[:MAX_DRAWN]
    pos = radial(focal, drawn)
    nodes = [{"id": focal, "name": fa["borrower_name"], "kind": "focal", "x": pos[focal][0], "y": pos[focal][1],
              "exposure": fa["ead"], "d_ecl": focal_d, "ews_band": fa["ews_band"]}]
    edges = []
    for x in drawn:
        bid = x["borrower_id"]
        nodes.append({"id": bid, "name": x["name"], "kind": x["channels"][0], "channels": x["channels"], "x": pos[bid][0],
                      "y": pos[bid][1], "exposure": x["exposure"], "at_risk": x["at_risk"], "d_ecl": x["d_ecl"],
                      "ews_band": x["ews_band"]})
        edges.append({"source": focal, "target": bid, "kind": x["channels"][0], "at_risk": x["at_risk"],
                      "label": x["why"]})
    cov = links.coverage(period)
    limits = [
        f"Relationship coverage: {cov['any_link_pct']:.1f}% of corporate borrowers have at least one link in rel-saudi-v1; "
        "supplier and customer links are observed only through payments routed via the bank.",
        "Links are one step from the failed name; a second failure among them is not chained.",
        f"Transmission rules are expert: guarantee support {GUARANTEE_LGD_RELIEF:.0%} of the guaranteed share of LGD, "
        f"controlled group members {CONTROL_NOTCHES} notches, suppliers 1–2 notches by revenue share, buyers 1 notch "
        f"at ≥{BUYER_SHARE:.0f}% of purchases, shared collateral {coll_shock:+g}% ({severity}, {cal['label']}).",
        "Off-book counterparties (other banks' customers, the Deal Desk demo entities) are not in the book run.",
    ]
    out = {"period": res["period"], "severity": severity, "focal": {"borrower_id": focal, "name": fa["borrower_name"],
                                                                   "sector": fa["sector"], "rating": fa["rating_current"],
                                                                   "ead": fa["ead"], "ecl": fa["ecl"],
                                                                   "ews_band": fa["ews_band"], "group": fa.get("group_name")},
           "totals": totals, "channels": channels, "names": out_names[:60],
           "network": {"nodes": nodes, "edges": edges, "kinds": KINDS, "drawn": len(drawn), "available": len(out_names)},
           "limits": limits, "coverage": cov, "calibration": {k: cal[k] for k in ("source", "label", "note", "path")},
           "engine": {"method": res["method"], "drivers": res["drivers"], "seconds": res["seconds"],
                      "steps": [s.to_dict() for s in steps]},
           "lineage": [common.src("rel_edge", period, ["GUARANTEES", "SUPPLIES"]), common.src("rel_group", period),
                       common.src("rel_shared", period), common.src("corp_facility", period, ["ead_sar_mn", "lgd_pct"]),
                       common.src("corp_borrower", period), common.src("ews_corp", period), wb.source(res["period"])],
           "money_unit": common.MONEY}
    out["text"] = writer.contagion_text(out)
    if publish:
        out["view"] = common.publish_view("contagion", focal, out, {"borrower": focal, "period": period,
                                                                    "severity": severity, "calibration": cal["source"]})
    out["data_domains"] = _registered(focal, out)  # R14 G: the registered view (net_contagion_view), when published
    return clean(out)


def _registered(focal: str, out: dict[str, Any]) -> dict[str, Any] | None:
    from backend.intel.network import views
    reg = views.registered("net_contagion_view", focal_borrower_id=focal)
    if not reg:
        return None
    r = reg["row"]
    same = bool(out.get("view", {}).get("content_sha256") and out["view"]["content_sha256"] == r.get("content_sha256")
                and out["severity"] == r.get("severity"))
    return {"source": reg["source"], "published_at": r.get("published_at"), "same_as_published": same,
            "note": ("Registered in Data Domains as Network intelligence · net_contagion_view" +
                     ("" if same else f" (published at {r.get('severity')} severity; this answer is recomputed live)"))}
