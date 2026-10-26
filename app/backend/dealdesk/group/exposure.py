"""Group exposure against the group cap, and the explicit "increase cap" ask with its DoA (PLAN_R12 §1.4, I24).

Two limits apply to a connected group:

* the **connected group limit** of the risk appetite (`risk_appetite.group_connected`, CP-1.2, SAR 500m), and
* the group's **approved exposure cap**, set by committee for that group (the bank papers' "group exposure cap",
  "increase group exposure cap to …"). It is read from Data Domains: the latest committee reference carrying a cap
  (`dd_reference.group_cap_mn`), else the deal register (`dd_deal.group_cap_existing_mn`). A group without an approved
  cap is held to the connected group limit only.

The optimiser constraint (`constraints.evaluate`, `# R12-C`) holds the deal to the tighter of the two, so a cap
breach is a binding constraint like any other (the optimiser shrinks the amount to fit). The cap test here says
what the cap allows, what the ask needs and, when the ask does not fit, the explicit ask to increase the cap with
the approval authority (DoA) that can grant it.
"""
from __future__ import annotations

import functools
from typing import Any

from backend.dealdesk import params
from backend.dealdesk.group import deal, sources as S
from backend.v5common.ratings import rank

AS_OF = deal.AS_OF


@functools.lru_cache(maxsize=512)
def _limits_cached(proposal_id: str, group_id: str, ask_sar: float) -> tuple:
    """(cap tuple | None, group exposure before the deal | None) from Data Domains, once per deal."""
    cap = None
    d = S.records(S.read("dd_deal", ["proposal_id", "group_cap_existing_mn", "group_cap_proposed_mn", "approval_authority"],
                         proposal_id=proposal_id)) if proposal_id else []
    refs = S.records(S.read("dd_reference", None, proposal_id=proposal_id)) if proposal_id else []
    refs = [r for r in refs if r.get("group_cap_mn")]
    if refs:
        r = sorted(refs, key=lambda r: str(r.get("ref_date") or ""))[-1]
        cap = (float(r["group_cap_mn"]), str(r.get("authority") or ""), str(r.get("ref_date") or ""), str(r.get("ref_no") or ""),
               "dd_reference", {"proposal_id": proposal_id, "ref_id": r.get("ref_id")})
    elif d and (d[0].get("group_cap_existing_mn") or 0) > 0:
        cap = (float(d[0]["group_cap_existing_mn"]), "", "", "", "dd_deal", {"proposal_id": proposal_id})
    asked = float(d[0]["group_cap_proposed_mn"]) if d and d[0].get("group_cap_proposed_mn") else None
    ge = S.records(S.read("dd_group_exposure", None, proposal_id=proposal_id)) if proposal_id else []
    before = None
    if ge:
        after = sum(float(r.get("total_proposed_mn") or 0) for r in ge)
        before = max(0.0, after - ask_sar)
    return cap, before, asked, len(ge)


def group_limits(p: dict[str, Any]) -> dict[str, Any] | None:
    """The group's approved exposure cap (dd_reference: latest committee cap, else dd_deal.group_cap_existing_mn) and,
    for a group outside the corporate book, its exposure before this deal (dd_group_exposure: total proposed limits of
    every group entity, less this deal's ask). None when Data Domains holds neither (R11 behaviour)."""
    from backend.dealdesk import engine
    ob = p["obligor"]
    a = p.get("ask") or {}
    try:
        ask_sar = float(a.get("amount") or 0) * engine.fx(a.get("currency", "SAR"))
    except Exception:  # noqa: BLE001
        ask_sar = float(a.get("amount") or 0)
    cap, before, asked, n = _limits_cached(str(p.get("proposal_id") or ""), str(ob.get("group_id") or ""), round(ask_sar, 6))
    if cap is None and before is None:
        return None
    out: dict[str, Any] = {"cap": None, "before_sar_mn": before, "cap_asked_sar_mn": asked,
                           "exposure_source": {"domain": (S.locate("dd_group_exposure") or {}).get("domain", "deal_desk"),
                                               "relation": "dd_group_exposure", "keys": {"proposal_id": p.get("proposal_id")}} if n else None}
    if cap is not None:
        lim, by, on, ref, rel, keys = cap
        out["cap"] = {"limit_sar_mn": lim, "approved_by": by or None, "approved_on": on or None, "committee_ref": ref or None,
                      "source": {"domain": (S.locate(rel) or {}).get("domain", "deal_desk"), "relation": rel, "keys": keys}}
    return out


def cap_for(p: dict[str, Any]) -> dict[str, Any] | None:
    """The approved group exposure cap of the deal's group, or None."""
    g = group_limits(p)
    return (g or {}).get("cap")


def clear_cache() -> None:
    _limits_cached.cache_clear()


def doa_for_group(new_exposure: float, rating: str, beyond_policy: bool) -> dict[str, Any]:
    """The approval authority for a group exposure of `new_exposure` (SAR m): the DoA row by exposure and rating;
    a cap above the connected group limit is a policy exception and goes to the top of the DoA."""
    doa = params.table("doa")
    rows = doa["rows"]
    lvl = next((r for r in rows if new_exposure <= r["max_exposure"] and rank(rating) <= rank(r["min_rating"])), rows[-1])
    reasons = [f"group exposure after the increase SAR {new_exposure:,.1f}m, rating {rating}"]
    if beyond_policy:
        lvl = rows[-1]
        reasons.append("the cap would exceed the connected group limit (CP-1.2): a policy exception")
    return {"level": lvl["level"], "rank": lvl["rank"], "reasons": reasons,
            "source": {"domain": "deal_desk", "relation": "dd_parameter", "keys": {"table_name": "doa", "version": doa.get("version")}}}


def members(st: dict[str, Any]) -> list[dict[str, Any]]:
    """Each member's book exposure (EAD, approved limits; funded and non-funded) at the as-of quarter."""
    ids = st["member_ids"]
    f = S.read("corp_facility_quarter", ["borrower_id", "facility_class", "limit_sar_mn", "ead_sar_mn", "drawn_sar_mn"],
               borrower_id=ids, reporting_quarter=AS_OF) if ids else None
    out: dict[str, dict[str, Any]] = {}
    for r in (S.records(f) if f is not None else []):
        m = out.setdefault(r["borrower_id"], {"borrower_id": r["borrower_id"], "ead": 0.0, "limit": 0.0, "funded_limit": 0.0,
                                              "non_funded_limit": 0.0, "drawn": 0.0})
        m["ead"] += r["ead_sar_mn"] or 0
        m["limit"] += r["limit_sar_mn"] or 0
        m["drawn"] += r["drawn_sar_mn"] or 0
        m["funded_limit" if r["facility_class"] == "funded" else "non_funded_limit"] += r["limit_sar_mn"] or 0
    return sorted(out.values(), key=lambda m: -m["ead"])


def cap_test(pid: str, terms: dict[str, Any] | None = None, st: dict[str, Any] | None = None) -> dict[str, Any]:
    """Group exposure before and after the deal against the connected group limit and the approved cap."""
    from backend.dealdesk import engine
    p = deal.get(pid)
    gl = group_limits(p) or {}
    if st is None:
        from backend.dealdesk.group import facts
        st = facts.structure(p)
    a = engine.analyse(p, terms)
    row = next(c for c in a["constraints"] if c["name"] == "group_connected")
    L = {x["name"]: x for x in params.rows("risk_appetite")}
    ra_limit = float(L["group_connected"]["limit"])
    cap = cap_for(p)
    before, dl = float(row["before"] or 0.0), float(row["deal"] or 0.0)
    after = before + dl
    binding = float(row["limit"])
    if gl.get("exposure_source"):  # a group outside the book: dd_group_exposure, per entity, limits basis
        ge = S.records(S.read("dd_group_exposure", None, proposal_id=pid))
        mem = [{"borrower_id": r["entity_id"], "name": r.get("entity_name") or r["entity_id"], "ead": float(r.get("outstanding_mn") or 0),
                "limit": float(r.get("total_existing_mn") or 0), "funded_limit": float(r.get("funded_existing_mn") or 0),
                "non_funded_limit": float(r.get("total_existing_mn") or 0) - float(r.get("funded_existing_mn") or 0),
                "drawn": float(r.get("outstanding_mn") or 0), "proposed_limit": float(r.get("total_proposed_mn") or 0),
                "funded_proposed": float(r.get("funded_proposed_mn") or 0),
                "is_self": r["entity_id"] == st["focal"]["borrower_id"]} for r in ge]
        mem.sort(key=lambda m: (not m["is_self"], -m["proposed_limit"]))
        basis_src = [gl["exposure_source"]]
    else:
        names = {k: v.get("name") for k, v in st.get("attrs", {}).items()}
        mem = members(st)
        for m in mem:
            m["name"] = names.get(m["borrower_id"], m["borrower_id"])
            m["is_self"] = m["borrower_id"] == st["focal"]["borrower_id"]
        basis_src = [{"domain": "cockpit", "relation": "corp_facility_quarter", "keys": {"reporting_quarter": AS_OF, "borrower_id": st["member_ids"]}},
                     {"domain": "borrower_360", "relation": "rel_group_quarter", "keys": {"group_id": st.get("group_id")}}]
    total_limits = sum(m["limit"] for m in mem)
    funded_limits = sum(m["funded_limit"] for m in mem)
    status = "breach" if after > binding + 1e-9 else "watch" if after > 0.9 * binding else "within"
    out: dict[str, Any] = {
        "proposal_id": pid, "group_id": st.get("group_id"), "group_name": st.get("group_name"), "as_of": AS_OF,
        "before_ead": before, "deal_ead_y1": dl, "after_ead": after, "headroom_before": binding - before,
        "headroom_after": binding - after, "binding_limit": binding,
        "binding": "approved cap" if cap and cap["limit_sar_mn"] < ra_limit - 1e-9 else "connected group limit",
        "connected_group_limit": {"limit_sar_mn": ra_limit, "basis": L["group_connected"]["basis"],
                                  "source": {"domain": "deal_desk", "relation": "dd_parameter",
                                             "keys": {"table_name": "risk_appetite", "param_key": "group_connected"}}},
        "approved_cap": cap, "status": status, "utilisation_pct": 100 * after / binding if binding else None,
        "limits_total_sar_mn": total_limits, "limits_funded_sar_mn": funded_limits, "members": mem,
        "constraint_name": row["name"], "constraint_label": row["label"], "increase_ask": None, "cap_asked_sar_mn": gl.get("cap_asked_sar_mn"),
        "limits_proposed_sar_mn": sum(m.get("proposed_limit", 0.0) for m in mem) if gl.get("exposure_source") else None,
        "basis": "limits (dd_group_exposure)" if gl.get("exposure_source") else "EAD (corporate book)",
        "source": basis_src,
    }
    asked = gl.get("cap_asked_sar_mn")
    if status != "breach" and cap and asked and asked > cap["limit_sar_mn"] + 1e-9:
        # the business asks for a higher cap although the deal fits: the ask is shown, with its DoA
        d = doa_for_group(asked, p["obligor"]["internal_rating"], asked > ra_limit + 1e-9)
        out["increase_ask"] = {"kind": "increase_cap_requested", "from_sar_mn": cap["limit_sar_mn"], "to_sar_mn": asked,
                               "increase_sar_mn": round(asked - cap["limit_sar_mn"], 1),
                               "increase_pct": round(100 * (asked - cap["limit_sar_mn"]) / cap["limit_sar_mn"], 1),
                               "fits_without_increase_ead_sar_mn": round(max(0.0, binding - before), 2), "doa": d,
                               "text": (f"Business asks to increase the approved group exposure cap of {st.get('group_name')} from SAR "
                                        f"{cap['limit_sar_mn']:,.1f}m to SAR {asked:,.1f}m (+SAR {asked - cap['limit_sar_mn']:,.1f}m), as per business. "
                                        f"Group exposure after this deal SAR {after:,.1f}m. Approval authority: {d['level']}."),
                               "alternative": f"This deal fits under the current cap with SAR {binding - after:,.1f}m to spare."}
    if status == "breach":
        need = max(after, asked or 0.0)
        rating = p["obligor"]["internal_rating"]
        current = cap["limit_sar_mn"] if cap else ra_limit
        beyond = need > ra_limit + 1e-9
        d = doa_for_group(need, rating, beyond)
        what = "approved group exposure cap" if cap else "connected group limit"
        ref = f" (last set by {cap['approved_by']}{', ' + cap['committee_ref'] if cap.get('committee_ref') else ''}{', ' + cap['approved_on'] if cap.get('approved_on') else ''})" if cap and cap.get("approved_by") else ""
        fits = max(0.0, binding - before)
        out["increase_ask"] = {
            "kind": "increase_cap" if cap and not beyond else "policy_exception",
            "from_sar_mn": current, "to_sar_mn": round(need, 1), "increase_sar_mn": round(need - current, 1),
            "increase_pct": round(100 * (need - current) / current, 1) if current else None,
            "fits_without_increase_ead_sar_mn": round(fits, 2),
            "doa": d,
            "text": (f"Increase the {what} of {st.get('group_name')} from SAR {current:,.1f}m to SAR {need:,.1f}m "
                     f"(+SAR {need - current:,.1f}m){ref}, to accommodate the requested facility's year-1 exposure of "
                     f"SAR {dl:,.1f}m on a group exposure of SAR {before:,.1f}m as at {AS_OF}. "
                     f"Approval authority: {d['level']}."),
            "alternative": (f"Without the increase the group can take SAR {fits:,.1f}m of new year-1 exposure; the optimiser "
                            "holds the amount to that (the recommended structure)."),
        }
    return out
