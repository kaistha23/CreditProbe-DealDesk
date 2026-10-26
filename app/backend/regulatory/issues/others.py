"""Issue views for the brief lines that used to open Data Domains and are not CRM checks:

  le:near                 large exposures (collateral.col_large_exposure): group exposure as % of Tier 1 vs the 25% limit
  ecl:anomalies:<run>     ECL input data issues before the run (ecl_runs.ecl_anomaly)
  ews:migrations:<period> exposures that moved to a worse stage this period (classification.cls_exposure)

Same sections as the CRM views: headline, plain words, rule, bank vs requirement, decomposition that sums, impact,
actions with owner and date, source link and what the data cannot tell us.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt
from backend.regulatory.issues import common as K

LE_RULE = ("A bank's exposure to one counterparty or group of connected counterparties may not exceed 25% of its "
           "Tier 1 capital; an exposure of 10% or more is a large exposure and is reported.")


def _empty_bits() -> dict[str, Any]:
    return {"tables": [], "bridge": None, "concentration": None, "impact": [], "actions": [], "exposures": None}


# ------------------------------------------------------------------ large exposures

def large_exposure(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    r = R.read("collateral", "col_large_exposure", order="pct_of_capital DESC, group_id", limit=15)
    s = K.src("collateral", "col_large_exposure", {}, "pct_of_capital", "")
    if r.status != "ok" or not r.rows:
        return {"id": "le:near", "kind": "large_exposure", "module": "Regulatory intelligence",
                "title": "Large exposures", "headline": "Large exposures are not available on this build.",
                "plain_words": ["This checks each group's exposure against the 25% limit.", "No data on this build."],
                "rule": {"article": "Large exposures", "text": LE_RULE, "href": "", "detail": ""},
                "comparison": None, "source": None, "cannot_tell": [], "trace": [], **_empty_bits()}
    rows = r.rows
    top = rows[0]
    period = str(top.get("as_of_date") or "")
    t1 = float(top.get("tier1_capital_sar_mn") or 0.0)
    allg = R.read("collateral", "col_large_exposure", columns="pct_of_capital, limit_pct, breach, large_exposure").rows
    near = [x for x in allg if float(x["pct_of_capital"]) >= 0.8 * float(x["limit_pct"])]
    over = [x for x in allg if x.get("breach")]
    large = [x for x in allg if x.get("large_exposure")]
    limit = float(top.get("limit_pct") or 25.0)
    head = t1 * limit / 100.0 - float(top["ead_sar_mn"])
    s = {**s, "period": period}
    tbl = K.table("groups", "The largest connected groups against the limit",
                  [("name", "Group", "text"), ("members", "Members", "n"), ("ead", "Exposure", "SAR mn"),
                   ("pct", "% of Tier 1", "%"), ("limit", "Limit", "%"), ("room", "Room to the limit", "SAR mn")],
                  [{"name": x["group_name"], "group_id": x["group_id"], "members": int(x.get("members") or 0),
                    "ead": K.r2(x["ead_sar_mn"]), "pct": float(x["pct_of_capital"]), "limit": float(x["limit_pct"]),
                    "room": K.r2(t1 * float(x["limit_pct"]) / 100.0 - float(x["ead_sar_mn"])),
                    "href": f"/borrower-360?q={x['group_id']}"} for x in rows[:10]])
    # Decomposition of the largest group by member (cockpit.corp_borrower_quarter -> corp_facility_quarter).
    mem = R.read("cockpit", "corp_borrower_quarter", columns="borrower_id, borrower_name, max(reporting_quarter) AS q",
                 where="group_id = ?", args=[top["group_id"]], group="borrower_id, borrower_name")
    q = max((str(m["q"]) for m in mem.rows), default="")
    steps = []
    if mem.rows and q:
        ids = [str(m["borrower_id"]) for m in mem.rows]
        ph = ", ".join("?" for _ in ids)
        f = R.read("cockpit", "corp_facility_quarter", columns="borrower_id, sum(ead_sar_mn) AS ead",
                   where=f"borrower_id IN ({ph}) AND reporting_quarter = ?", args=[*ids, q], group="borrower_id",
                   order="ead DESC")
        nm = {str(m["borrower_id"]): str(m["borrower_name"]) for m in mem.rows}
        steps = [{"key": str(x["borrower_id"]), "label": nm.get(str(x["borrower_id"]), str(x["borrower_id"])),
                  "value": float(x["ead"] or 0.0), "facilities": None, "ead": K.r2(x["ead"]),
                  "explain": "Member's exposure in the corporate book.", "rows": [str(x["borrower_id"])], "link": None,
                  "source": K.src("cockpit", "corp_facility_quarter", {"borrower_id": x["borrower_id"]}, "ead_sar_mn", q)}
                 for x in f.rows]
    total_members = sum(st["value"] for st in steps)
    bridge = K.bridge(f"{top['group_name']}: exposure by member ({q})", total_members, steps,
                      "Each member's EAD in the corporate book at its latest quarter; the group register "
                      "(col_large_exposure) may include off-book or other-entity exposure.") if steps else None
    status = (f"{len(over)} group(s) above the limit" if over else
              f"{len(near)} group(s) above 80% of the limit" if near else "no group above 80% of the limit")
    return {
        "id": "le:near", "kind": "large_exposure", "module": "Regulatory intelligence", "title": "Large exposures",
        "period": period, "severity": "critical" if over else ("high" if near else "low"),
        "headline": (f"Large exposures at {period}: {status}; the largest, {top['group_name']}, is "
                     f"{float(top['pct_of_capital']):.1f}% of Tier 1 capital against {limit:.0f}%."),
        "plain_words": ["This checks how much the bank lends to any one group of related companies against its capital.",
                        f"The largest group is {float(top['pct_of_capital']):.1f}% of capital; the limit is {limit:.0f}%.",
                        f"{status.capitalize()}; {len(large)} group(s) are large exposures (10% or more).",
                        "Keep new lending to the top groups inside the room left." if not over else
                        "Stop new lending to the groups over the limit and agree a reduction plan."],
        "rule": {"article": "Large exposures (25% of Tier 1)", "text": LE_RULE, "href": "", "detail": ""},
        "comparison": {"sentence": (f"Bank's largest group exposure is {float(top['pct_of_capital']):.1f}% of Tier 1 "
                                    f"({fmt(float(top['ead_sar_mn']), 'SAR mn')}) against a limit of {limit:.0f}% "
                                    f"({fmt(t1 * limit / 100.0, 'SAR mn')}): {fmt(head, 'SAR mn')} of room."),
                       "bank": K.fig("Largest group, % of Tier 1", float(top["pct_of_capital"]), "%", s),
                       "required": K.fig("Limit, % of Tier 1", limit, "%", s), "model": None,
                       "figures": [K.fig("Tier 1 capital", K.r2(t1), "SAR mn", {**s, "column": "tier1_capital_sar_mn"}),
                                   K.fig("Groups above 80% of the limit", len(near), "", s),
                                   K.fig("Groups over the limit", len(over), "", s)]},
        "tables": [tbl], "bridge": bridge, "concentration": None,
        "impact": [K.fig("Room left on the largest group", K.r2(head), "SAR mn", s)],
        "actions": ([K.action(1, "Freeze new limits for the groups over the limit and agree a reduction plan", "limits",
                              today, 14, LE_RULE)] if over else []) +
                   [K.action(len(over and [1] or []) + 1, f"Keep a pre-deal check on the top {min(5, len(rows))} groups: "
                             "any new deal must fit the room left", "limits", today, 30, "Avoids a breach at approval."),
                    K.action(len(over and [1] or []) + 2, "Confirm the connected-party mapping of the top groups with "
                             "the relationship managers", "credit", today, 45,
                             "Group membership decides the measure; unmapped connections understate it.")],
        "exposures": None,
        "source": {"label": "Source: collateral.col_large_exposure", "domain": "collateral",
                   "relation": "col_large_exposure", "href": "/data-builder?domain=collateral&relation=col_large_exposure"},
        "cannot_tell": ["Exposures through other group entities or off-balance-sheet items not in the corporate book.",
                        "Credit risk mitigation eligible to reduce the measure is not netted here."],
        "trace": [s],
    }


# ------------------------------------------------------------------ ECL data issues

def ecl_anomalies(run: str = "", today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    where, args = ("run_id = ?", [run]) if run else ("", [])
    a = R.read("ecl_runs", "ecl_anomaly", where=where, args=args, order="rerun_required DESC, anomaly_id")
    rows = a.rows
    run = run or (str(rows[0]["run_id"]) if rows else "")
    s = K.src("ecl_runs", "ecl_anomaly", {"run_id": run}, "rerun_required", run)
    must = [x for x in rows if int(x.get("rerun_required") or 0)]
    ids = [str(x["exposure_id"]) for x in rows]
    ecl_by: dict[str, float] = {}
    if ids:
        ph = ", ".join("?" for _ in ids)
        e = R.read("ecl_runs", "ecl_facility", columns="exposure_id, ecl_sar_mn, ead_sar_mn",
                   where=f"run_id = ? AND exposure_id IN ({ph})", args=[run, *ids])
        ecl_by = {str(x["exposure_id"]): float(x.get("ecl_sar_mn") or 0.0) for x in e.rows}
    kinds: dict[str, list[dict[str, Any]]] = {}
    for x in rows:
        kinds.setdefault(str(x["kind"]), []).append(x)
    ecl_total = sum(ecl_by.get(str(x["exposure_id"]), 0.0) for x in rows)
    steps = [{"key": k, "label": k, "value": sum(ecl_by.get(str(x["exposure_id"]), 0.0) for x in xs),
              "facilities": len(xs), "ead": None, "explain": f"{sum(int(x.get('rerun_required') or 0) for x in xs)} "
              "need a re-run.", "rows": [str(x["exposure_id"]) for x in xs], "link": None,
              "source": K.src("ecl_runs", "ecl_facility", {"run_id": run, "exposure_id": [str(x["exposure_id"]) for x in xs]},
                              "ecl_sar_mn", run)} for k, xs in sorted(kinds.items(), key=lambda kv: kv[0])]
    owner_of = {"PD changed with no rating change": "model", "LGD changed with no collateral change": "model",
                "Missing collateral value": "collateral", "Stage inconsistent with DPD": "classification",
                "Stage 3 with zero ECL": "ecl_run", "EAD greater than limit": "data"}
    actions = [K.action(i + 1, f"Fix {len(xs)} × {k.lower()} ({', '.join(str(x['exposure_id']) for x in xs[:3])})",
                        owner_of.get(k, "data"), today, 7, xs[0].get("expected") or "Input check.")
               for i, (k, xs) in enumerate(sorted(kinds.items(), key=lambda kv: kv[0]))]
    actions.append(K.action(len(actions) + 1, f"Re-run the {run} ECL once the {len(must)} blocking issues are cleared",
                            "ecl_run", today, 10, "A run on wrong inputs has to be redone."))
    return {
        "id": f"ecl:anomalies:{run}", "kind": "ecl_anomaly", "module": "ECL runs", "title": "ECL input data issues",
        "period": run, "severity": "high" if must else "medium",
        "headline": f"{len(rows)} input issues in the {run} ECL run, {len(must)} of them need a re-run; the exposures "
                    f"affected carry {fmt(ecl_total, 'SAR mn')} of ECL.",
        "plain_words": ["This checks the inputs of the provision run for changes that make no sense before it is "
                        "published.",
                        f"{len(rows)} issues found; {len(must)} would make the run wrong.",
                        f"The affected loans carry {fmt(ecl_total, 'SAR mn')} of provisions.",
                        "Fix the inputs, then re-run the provisions."],
        "rule": {"article": "ECL run input controls", "text": "Every ECL input that moves without a reason (a PD with no "
                 "rating change, an LGD with no collateral change, a stage that contradicts days past due) is "
                 "explained or corrected before the run is signed off.", "href": "", "detail": ""},
        "comparison": {"sentence": f"Run {run} has {len(must)} blocking input issues against a sign-off requirement of 0.",
                       "bank": K.fig("Blocking issues", len(must), "", s), "required": K.fig("Allowed at sign-off", 0, "", s),
                       "model": None, "figures": [K.fig("All issues", len(rows), "", s)]},
        "tables": [K.table("issues", "Every issue", [("anomaly_id", "Id", "text"), ("exposure_id", "Exposure", "text"),
                                                    ("kind", "Issue", "text"), ("prior_value", "Prior", "text"),
                                                    ("current_value", "Now", "text"), ("expected", "Expected", "text"),
                                                    ("rerun", "Re-run", "text")],
                           [{**{k: str(x.get(k) or "") for k in ("anomaly_id", "exposure_id", "kind", "prior_value",
                                                                  "current_value", "expected")},
                             "rerun": "Yes" if int(x.get("rerun_required") or 0) else "No"} for x in rows])],
        "bridge": K.bridge("ECL on the affected exposures, by issue", ecl_total, steps,
                           "ECL of each affected exposure in the run (ecl_runs.ecl_facility), by issue kind.") if steps else None,
        "concentration": None,
        "impact": [K.fig("ECL on the affected exposures", K.r2(ecl_total), "SAR mn",
                         K.src("ecl_runs", "ecl_facility", {"run_id": run}, "ecl_sar_mn", run))],
        "actions": actions, "exposures": None,
        "source": {"label": "Source: ecl_runs.ecl_anomaly", "domain": "ecl_runs", "relation": "ecl_anomaly",
                   "href": "/data-builder?domain=ecl_runs&relation=ecl_anomaly"},
        "cannot_tell": ["How much the ECL moves once each input is fixed: that needs the re-run.",
                        "Whether a business reason (a new valuation, a rating action not yet loaded) explains a change."],
        "trace": [s],
    }


# ------------------------------------------------------------------ stage migrations this period

def migrations(period: str = "", today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    if not period:
        period = R.latest_period("classification", "cls_exposure", "period") or ""
    c = R.read("classification", "cls_exposure",
               columns="exposure_id, obligor_id, stage, previous_stage, dpd_days, sicr_reasons, utp_reasons",
               where="book = 'corporate' AND stage > previous_stage AND period = ?", args=[period])
    rows = c.rows
    s = K.src("classification", "cls_exposure", {"book": "corporate", "period": period}, "stage, previous_stage", period)
    fac: dict[str, dict[str, Any]] = {}
    ids = [str(x["exposure_id"]) for x in rows]
    for part in K._chunks(ids):
        ph = ", ".join("?" for _ in part)
        f = R.read("cockpit", "corp_facility_quarter", columns="facility_id, ead_sar_mn, ecl_sar_mn, sector",
                   where=f"facility_id IN ({ph}) AND reporting_quarter = ?", args=[*part, period])
        fac.update({str(x["facility_id"]): x for x in f.rows})
    acc: dict[str, list[float]] = {}
    enriched = []
    for x in rows:
        f = fac.get(str(x["exposure_id"]), {})
        k = f"Stage {int(x['previous_stage'])} → Stage {int(x['stage'])}"
        a = acc.setdefault(k, [0, 0.0, 0.0])
        a[0] += 1
        a[1] += float(f.get("ead_sar_mn") or 0.0)
        a[2] += float(f.get("ecl_sar_mn") or 0.0)
        enriched.append({"borrower_id": str(x["obligor_id"]), "ead": float(f.get("ead_sar_mn") or 0.0)})
    ead = sum(a[1] for a in acc.values())
    s3 = sum(1 for x in rows if int(x["stage"]) == 3)
    steps = [{"key": k, "label": k, "value": a[1], "facilities": int(a[0]), "ead": K.r2(a[1]),
              "explain": f"ECL now {fmt(a[2], 'SAR mn')}.", "rows": [], "link": None, "source": s}
             for k, a in sorted(acc.items())]
    names = len({x["obligor_id"] for x in rows})
    return {
        "id": f"ews:migrations:{period}", "kind": "migrations", "module": "Early Warning",
        "title": "Exposures moved to a worse stage", "period": period, "severity": "high" if s3 else "medium",
        "headline": f"{len(rows):,} corporate exposures ({names:,} names, {fmt(ead, 'SAR mn')} EAD) moved to a worse "
                    f"stage in {period}, {s3:,} of them into Stage 3.",
        "plain_words": ["This shows the loans that got worse this quarter.",
                        f"{len(rows):,} loans of {names:,} borrowers moved down, {s3:,} into default.",
                        f"They carry {fmt(ead, 'SAR mn')} of exposure.",
                        "Check each borrower in Early Warning and confirm the new stage."],
        "rule": {"article": "IFRS 9 staging (CBUAE CRM Art. 7, 9)", "text": "An exposure moves to Stage 2 on a "
                 "significant increase in credit risk and to Stage 3 on default; each move carries its reason.",
                 "href": f"{K.POLICY_HREF}&clause=CBUAE CRM Art. 7.8", "detail": ""},
        "comparison": None, "tables": [],
        "bridge": K.bridge(f"{fmt(ead, 'SAR mn')} of EAD by move", ead, steps, "EAD of each moved exposure, by the "
                           "stage it came from and went to.") if steps else None,
        "concentration": K.concentration(enriched, "ead", period, label="EAD moved") if enriched else None,
        "impact": [K.fig("EAD moved", K.r2(ead), "SAR mn", s)],
        "actions": [K.action(1, "Confirm the new stages and their reasons", "classification", today, 14,
                             "Every move needs its SICR or default reason on file."),
                    K.action(2, "Review the names moved into Stage 3 with remedial", "remedial", today, 21,
                             "Early action improves recovery.",
                             link={"label": "Open Early Warning", "href": "/early-warning?domain=corporate"})],
        "exposures": None,
        "source": {"label": "Source: classification.cls_exposure", "domain": "classification", "relation": "cls_exposure",
                   "href": "/data-builder?domain=classification&relation=cls_exposure"},
        "cannot_tell": ["Moves already reversed after the period end."],
        "trace": [s],
    }
