"""Governance and conduct red flags (PLAN_R12 §1.4, I24) and where they go:

* **Review findings**: each flag is a finding in B's shared schema (`dd_review_finding`), review point "Group and
  connected parties", "Collateral and legal" or "Track record", with its evidence (domain, relation, row keys, value).
* **Rating overlay**: one notch per flag that carries a notch, capped (rules.py `overlay`), shown with its reasons.
  The overlaid rating is a proposal to the reviewer; the engine prices at it only on request (`overlay=1`).
* **Conditions**: each flag's condition template, filled with the parties and numbers behind it.

The tests and texts are deterministic (N6).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.dealdesk.group import conduct as C, deal, exposure as X, facts as F
from backend.dealdesk.seed import GRADES

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
POINT_LABEL = {"group_and_connected": "Group and connected parties", "collateral_and_legal": "Collateral and legal",
               "track_record": "Track record"}


def rules() -> dict[str, Any]:
    from backend.dealdesk.group.rules import RULES
    return RULES


def _rule(code: str) -> dict[str, Any]:
    return next(r for r in rules()["rules"] if r["code"] == code)


def _names(rows: list[dict[str, Any]], key: str = "name", n: int = 4) -> str:
    xs = [str(r.get(key) or r.get("borrower_id")) for r in rows]
    return ", ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def _ev(src: dict[str, Any] | list[dict[str, Any]], field: str | None = None, value: Any = None) -> list[dict[str, Any]]:
    srcs = src if isinstance(src, list) else [src]
    return [{"domain": s.get("domain"), "relation": s.get("relation"), "keys": s.get("keys", {}), "field": field, "observed": value}
            for s in srcs if s]


def evaluate(pid: str, fx: dict[str, Any] | None = None, cd: dict[str, Any] | None = None,
             cap: dict[str, Any] | None = None) -> dict[str, Any]:
    p = deal.get(pid)
    fx = fx or F.build(pid)
    cd = cd or C.build(pid)
    if cap is None:
        try:
            cap = X.cap_test(pid)
        except Exception:  # noqa: BLE001 -- the engine cannot price this deal: the cap test is skipped, said in gaps
            cap = None
    th = rules()["thresholds"]
    flags: list[dict[str, Any]] = []

    def flag(code: str, detail: str, parties: str, evidence: list[dict[str, Any]], severity: str | None = None,
             fill: dict[str, Any] | None = None) -> None:
        r = _rule(code)
        cond = dict(r["condition"])
        cond["text"] = cond["text"].format(parties=parties, **(fill or {}))
        flags.append({"code": code, "family": r["family"], "review_point": r["review_point"],
                      "review_point_label": POINT_LABEL[r["review_point"]], "severity": severity or r["severity"],
                      "notch": int(r["notch"]), "title": r["title"], "detail": detail, "parties": parties,
                      "evidence": evidence, "condition": cond, "condition_only": bool(r.get("condition_only"))})

    cp = fx["connected_parties"]
    # ---- governance
    ins = fx["insiders"]
    if ins["count"]:
        who = "; ".join(f"{r['party']} ({r['link']}{', ' + r['role'] if r.get('role') else ''}"
                        f"{', ' + format(r['pct'], '.1f') + '%' if r.get('pct') else ''})" for r in ins["rows"])
        flag("GOV-INSIDER", f"{ins['count']} insider or staff link{'s' if ins['count'] > 1 else ''} to the obligor or its group: {who}.",
             who, _ev(ins["source"], "link_type", [r["link"] for r in ins["rows"]]))
    cls = [r for r in cp["rows"] if r["classified"]]
    if cls:
        flag("GOV-CONN-CLASSIFIED", f"{len(cls)} connected part{'ies' if len(cls) > 1 else 'y'} classified as at {deal.AS_OF}: "
             + "; ".join(f"{r['name']} ({', '.join(r['links'])}; {', '.join(r['classified_basis'])}; "
                       + (f"exposure with the bank SAR {r['ead']:,.1f}m" if r["ead"] else "no exposure with the bank")
                       + (f"; {r['note']}" if r.get("note") else "") + ")" for r in cls[:4]) + ".",
             _names(cls), _ev([{"domain": "cockpit", "relation": "corp_facility_quarter",
                                "keys": {"borrower_id": [r["borrower_id"] for r in cls], "reporting_quarter": deal.AS_OF}}], "stage",
                              [r["worst_stage"] for r in cls]))
    lit = [r for r in cp["rows"] if r["in_litigation"]]
    if lit:
        flag("GOV-CONN-LITIGATION", f"{len(lit)} connected part{'ies' if len(lit) > 1 else 'y'} in litigation (SICR litigation indicator "
             f"or court cases on the bureau): {_names(lit)}; combined exposure with the bank SAR {sum(r['ead'] for r in lit):,.1f}m.",
             _names(lit), _ev([{"domain": "classification", "relation": "cls_reason",
                                "keys": {"obligor_id": [r["borrower_id"] for r in lit], "code": "SICR-LITIGATION"}}], "code", "SICR-LITIGATION"))
    arr = [r for r in cp["rows"] if r["in_arrears"] and not r["classified"]]
    if arr:
        flag("GOV-CONN-ARREARS", f"{len(arr)} connected part{'ies' if len(arr) > 1 else 'y'} in arrears in the 4 quarters to {deal.AS_OF}: "
             + "; ".join(f"{r['name']} (max {r['max_dpd_4q']} days past due)" for r in arr[:4]) + ".",
             _names(arr), _ev([{"domain": "cockpit", "relation": "corp_facility_quarter",
                                "keys": {"borrower_id": [r["borrower_id"] for r in arr]}}], "dpd_days", [r["max_dpd_4q"] for r in arr]))
    oc = fx["ownership_changes"]
    if oc["count"]:
        txt = "; ".join(f"{r['date']}: " + (f"{r['holder']} in {r.get('entity')}, " if r.get("holder") else "")
                        + f"{r.get('from') or 'n/a'} → {r.get('to') or 'n/a'}" + ("" if r.get("disclosed", True) else " (not disclosed)")
                        for r in oc["rows"])
        flag("GOV-OWNERSHIP-CHANGE", f"Ownership changed in the last {oc['lookback']}: {txt}.", txt, _ev(oc["source"]))
    sh = fx["shareholders"]
    if sh["rows"] and not sh["ubo_identified"] and sh["identified_pct"] < th["ubo_min_identified_pct"]:
        flag("GOV-UBO-UNIDENTIFIED", f"Shareholders identified to {sh['identified_pct']:.1f}% of the capital; no ultimate beneficial "
             f"owner of {th['ubo_pg_min_pct']}% or more named.", "the owners", _ev(sh["source"], "ownership_pct", sh["identified_pct"]),
             fill={"identified": f"{sh['identified_pct']:.1f}"})
    flagged = {r["name"] for r in cp["rows"] if r["borrower_id"] in cp["adverse"] or r["classified"]}
    linked = [dict(b, linked_to_stressed=[x for x in b["linked_to_stressed"] if x not in flagged]) for b in fx["board"]["rows"]]
    linked = [b for b in linked if b["linked_to_stressed"]]  # names already flagged as connected parties count once
    if linked:
        txt = "; ".join(f"{b['name']} ({', '.join(b['roles'])}) also of {', '.join(b['linked_to_stressed'][:3])}" for b in linked[:4])
        flag("GOV-KEYPERSON-LINK", f"{len(linked)} board member{'s' if len(linked) > 1 else ''} or key person{'s' if len(linked) > 1 else ''} "
             f"linked to borrowers in arrears, litigation, classified or in high Early Warning: {txt}.",
             ", ".join(sorted({x for b in linked for x in b["linked_to_stressed"]})[:6]), _ev(fx["board"]["source"]))
    sc = fx["shared_collateral"]
    over = [a for a in sc["assets"] if a["over_pledged"]]
    if over:
        flag("GOV-SHARED-COLLATERAL", f"{len(over)} collateral item{'s' if len(over) > 1 else ''} shared with other borrowers and claimed "
             f"above value: " + "; ".join(f"{a['collateral_id']} ({a['type']}, SAR {a['market_value']:,.1f}m, claims {a['total_pct']:.0f}%)"
                                          for a in over) + ".",
             ", ".join(a["collateral_id"] for a in over), _ev(sc["source"], "allocation_pct", [a["total_pct"] for a in over]))
    gu = fx["guarantees"]
    if gu.get("unperfected"):
        txt = "; ".join(f"{str(g.get('kind') or 'guarantee').replace('_', ' ')} by {g['guarantor_id']} (SAR {g['amount'] or 0:,.1f}m"
                        + (f", deadline {g['deadline']}" if g.get("deadline") else "") + ")" for g in gu["unperfected"])
        n = len(gu["unperfected"])
        flag("GOV-GUARANTEE-UNPERFECTED", f"{n} security item{'s' if n > 1 else ''} not perfected as at {deal.AS_OF}: {txt}.", txt,
             _ev(gu["source"][-1:], "perfected", 0))
    if cap and cap.get("increase_ask"):
        ask = cap["increase_ask"]
        flag("GOV-GROUP-CAP", f"Group exposure after the deal SAR {cap['after_ead']:,.1f}m against the {cap['binding']} of SAR "
             f"{cap['binding_limit']:,.1f}m ({cap['utilisation_pct']:.0f}%). {ask['alternative']}", ask["text"],
             _ev(cap["source"] + [cap["connected_group_limit"]["source"]] + ([cap["approved_cap"]["source"]] if cap.get("approved_cap") else []),
                 "after_ead", round(cap["after_ead"], 4)))
    # ---- conduct
    rc = cd["returned_cheques"]
    if rc["count_12m"] >= th["returned_cheques_count_12m"] or rc["amount_12m_sar_mn"] >= th["returned_cheques_amount_sar_mn"]:
        sev = "high" if rc["count_12m"] >= th["returned_cheques_high_count_12m"] else "medium"
        dates = ", ".join(f"{d['month']} ({d['count']})" for d in rc["dates"][-6:])
        flag("CON-RETURNED-CHEQUES", f"{rc['count_12m']} cheques returned in the 12 months to {deal.AS_OF} (SAR {rc['amount_12m_sar_mn']:,.2f}m), "
             f"in {rc['months_with_returns']} months: {dates}" + (f"; reasons: {', '.join(rc['reasons'])}" if rc["reasons"] else "") + ".",
             f"{rc['count_12m']} returned cheques", _ev(cd["source"][1], "cheques_returned_count", rc["count_12m"]), severity=sev)
    pdq = cd["past_dues"]
    if pdq["max_dpd_4q"] >= th["past_due_days_high"]:
        flag("CON-PAST-DUE", f"Past dues on the bank's facilities in {pdq['quarters_past_due_8q']} of the last {len(pdq['quarters'])} quarters, "
             f"up to {pdq['max_dpd_8q']} days; last in {pdq['last_past_due']}.", f"up to {pdq['max_dpd_4q']} days in the last 4 quarters",
             _ev(cd["source"][3], "dpd_days", pdq["max_dpd_4q"]))
    ut = cd["utilisation"]
    if ut["over_90_4q"] or ut["excess_days_12m"] >= th["excess_days_12m"]:
        hi = [f for f in ut["facilities"] if f["facility_id"] in ut["over_90_4q"]]
        txt = "; ".join(f"{f['facility_id']} ({f['product']}) average {f['avg_4q_pct']:.0f}%" for f in hi)
        flag("CON-OVERUTILISATION", f"Utilisation above {th['utilisation_avg_4q_pct']}% on average over 4 quarters"
             + (f": {txt}" if txt else "") + f"; {ut['excess_days_12m']} excess days in 12 months.",
             ", ".join(ut["over_90_4q"]) or "the revolving lines", _ev(cd["source"][3], "utilisation_pct", [f["avg_4q_pct"] for f in hi]))
    tv = cd["turnover"]
    if tv.get("routing_compliant") is False:
        if tv.get("routing_unit") == "%":
            txt = f"{tv['routing_required_x']:.0f}% of receipts required, {tv['routing_actual_x']:.0f}% routed"
        else:
            txt = f"{tv['routing_required_x']:.1f}x the limits required, {tv['routing_actual_x']:.2f}x achieved ({tv['routing_achieved_pct']:.0f}%)"
        flag("CON-ROUTING", f"Business routing undertaking not met: {txt} in the 12 months to {deal.AS_OF}.", txt,
             _ev(cd["source"][2], "routing_actual_x", tv["routing_actual_x"]))
    if tv.get("growth_pct") is not None and tv["growth_pct"] <= th["turnover_decline_pct"]:
        txt = f"SAR {tv['credit_turnover_12m_sar_mn']:,.1f}m (PY SAR {tv['credit_turnover_prev_12m_sar_mn']:,.1f}m, {tv['growth_pct']:.0f}%)"
        flag("CON-TURNOVER-DECLINE", f"Credit turnover fell to {txt} in the 12 months to {deal.AS_OF}.", txt,
             _ev(cd["source"][1], "credit_turnover_sar_mn", tv["credit_turnover_12m_sar_mn"]))
    bu = cd["bureau"]
    if bu["trend"] == "deteriorating":
        enq = f" and {bu['enquiries_4q']} enquiries in the last 4 quarters" if bu.get("enquiries_4q") is not None else ""
        flag("CON-BUREAU", f"Bureau trend deteriorating to {deal.AS_OF}: worst external days past due {bu['max_external_dpd_4q'] or 0}{enq}.",
             fx["obligor"]["name"],
             _ev(cd["source"][4], "external_dpd_days", bu["max_external_dpd_4q"]))
    court = [e for e in bu["entity_reports"] if (e.get("court_cases") or 0) > 0]
    if court:
        flag("CON-BUREAU-COURT", "Court cases on the bureau: " + "; ".join(f"{e['entity']} ({e['court_cases']})" for e in court) + ".",
             _names(court, "entity"), _ev(cd["source"][5], "court_cases", [e["court_cases"] for e in court]))
    # ---- UBO personal guarantee, when governance flags exist and a UBO is named
    gov = [f for f in flags if f["family"] == "governance" and f["notch"]]
    ubos = [r for r in sh["rows"] if r["ubo"] and ((r.get("pct") or r.get("indirect_pct") or 0) >= th["ubo_pg_min_pct"])]
    if ubos and (gov or [f for f in flags if f["family"] == "conduct" and f["notch"]]):
        txt = ", ".join(f"{u['name']} ({(u.get('pct') or u.get('indirect_pct') or 0):.1f}%)" for u in ubos)
        flag("GOV-UBO-PG", f"Red flags on governance or conduct with identified UBOs: {txt}.", txt, _ev(sh["source"]))
    flags.sort(key=lambda f: (f["condition_only"], SEV_ORDER.get(f["severity"], 9), f["code"]))
    for i, f in enumerate(flags, 1):
        f["finding_id"] = finding_id(pid, f["code"])
        f["condition"]["condition_id"] = f"C-{pid}-COND-{f['code']}"
        f["condition"]["source_finding"] = f["finding_id"]
    ov = overlay(p["obligor"]["internal_rating"], [f for f in flags if not f["condition_only"]])
    return {"proposal_id": pid, "as_of": deal.AS_OF, "flags": [f for f in flags if not f["condition_only"]],
            "conditions": [f["condition"] for f in flags], "overlay": ov,
            "counts": {"governance": sum(1 for f in flags if f["family"] == "governance" and not f["condition_only"]),
                       "conduct": sum(1 for f in flags if f["family"] == "conduct"),
                       "high": sum(1 for f in flags if f["severity"] == "high")},
            "rules_version": rules()["version"]}


def notch(rating: str, n: int) -> str:
    """`n` notches worse on the master scale (C is the floor)."""
    if rating not in GRADES:
        return rating
    i = min(len(GRADES) - 1, GRADES.index(rating) + max(0, n))
    return GRADES[i]


def overlay(rating: str, flags: list[dict[str, Any]]) -> dict[str, Any]:
    o = rules()["overlay"]
    reasons = [{"code": f["code"], "title": f["title"], "notch": f["notch"], "severity": f["severity"], "finding_id": f.get("finding_id")}
               for f in flags if f["notch"]]
    raw = sum(r["notch"] * o["notch_per_flag"] for r in reasons)
    applied = min(raw, o["cap_notches"])
    capped = f" (capped at {o['cap_notches']})" if raw > applied else ""
    return {"base_rating": rating, "notches_raw": raw, "notches": applied, "capped": raw > applied, "cap": o["cap_notches"],
            "overlaid_rating": notch(rating, applied), "reasons": reasons, "basis": o["basis"],
            "text": (f"Rating overlay: {applied} notch{'es' if applied != 1 else ''} for {len(reasons)} red flag{'s' if len(reasons) != 1 else ''}"
                     f"{capped}: {rating} → {notch(rating, applied)}."
                     if reasons else f"No governance or conduct red flag: rating {rating} unchanged.")}


REVIEW_POINT_NO = {"group_and_connected": 6, "collateral_and_legal": 7, "track_record": 8}
CATEGORY = {"GOV-INSIDER": "insider_link", "GOV-GROUP-CAP": "group_exposure"}


def _key_text(keys: dict[str, Any]) -> str:
    """Row keys as col=value pairs separated by semicolons (the contract's evidence_key)."""
    out = []
    for k, v in keys.items():
        if isinstance(v, (list, tuple, set)):
            v = ",".join(str(x) for x in list(v)[:20])
        out.append(f"{k}={v}")
    return ";".join(out)


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)) and v and all(isinstance(x, (int, float)) for x in v):
        return float(max(v))
    return None


def finding_id(pid: str, code: str) -> str:
    return f"C-{pid}-{code}"


def findings_rows(ev: dict[str, Any]) -> list[dict[str, Any]]:
    """The flags as rows of the shared review finding relation `dd_review_finding` (contract: B's schema)."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = []
    for f in ev["flags"]:
        e0 = f["evidence"][0] if f["evidence"] else {}
        out.append({"finding_id": f["finding_id"], "proposal_id": ev["proposal_id"], "review_point": REVIEW_POINT_NO[f["review_point"]],
                    "category": CATEGORY.get(f["code"], f["family"]), "severity": f["severity"], "title": f["title"],
                    "finding_text": f["detail"], "claim_text": None, "claim_value": None, "evidence_value": _num(e0.get("observed")),
                    "evidence_unit": e0.get("field"), "evidence_domain": e0.get("domain"), "evidence_relation": e0.get("relation"),
                    "evidence_key": _key_text(e0.get("keys", {})), "status": "open", "rating_notch": -int(f["notch"]),
                    "condition_id": f["condition"]["condition_id"], "query_id": None, "raised_by": "C", "raised_at": now,
                    "resolved_at": None, "reporting_quarter": ev["as_of"]})
    return out
