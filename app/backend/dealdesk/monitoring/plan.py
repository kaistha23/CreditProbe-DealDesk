"""The monitoring plan (`dd_monitoring_plan`): set at approval from the stress verdict, carried on the facility, read by
the Book and by Early Warning (through `backend.ews_link`), changed only with a reason (logged as a new version).

One row per (deal, facility, version): tier, verdict, drivers, thresholds (EWS band floors and the named triggers),
review frequency and next review date, set by and on, reason, source (stress verdict or manual change), the stress
run behind it, and status (active, superseded).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.dealdesk.monitoring import rules as mr
from backend.dealdesk.stress2 import store


class PlanError(ValueError):
    pass


def _rows(**f: Any) -> list[dict[str, Any]]:
    out = []
    for r in store.read("dd_monitoring_plan", **f):
        r = dict(r)
        for k in ("drivers", "driver_labels", "triggers", "ews_thresholds"):
            r[k] = store.decode(r.get(k))
        r["version"] = int(r.get("version") or 1)
        out.append(r)
    return out


def history(proposal_id: str) -> list[dict[str, Any]]:
    return sorted(_rows(proposal_id=proposal_id), key=lambda r: (str(r.get("set_at") or r.get("set_on") or ""), r["version"]))


def current(proposal_id: str) -> dict[str, Any] | None:
    h = [r for r in history(proposal_id) if r.get("status") != "superseded"] or history(proposal_id)
    return h[-1] if h else None


def all_current() -> list[dict[str, Any]]:
    """The plan in force per deal, and per back-book facility for the Book's facility plans (Session I writes those
    with no deal: keyed by facility_ref). Superseded rows never count."""
    by: dict[str, dict[str, Any]] = {}
    for r in _rows():
        if r.get("status") == "superseded":
            continue
        k = r.get("proposal_id") or f"facility:{r.get('facility_id')}"
        if k not in by or (str(r.get("set_at") or r.get("set_on") or ""), r["version"]) > (
                str(by[k].get("set_at") or by[k].get("set_on") or ""), by[k]["version"]):
            by[k] = r
    return sorted(by.values(), key=lambda r: (-mr.TIER_ORDER.get(r["tier"], 0), r.get("proposal_id") or "", r.get("facility_id") or ""))


def for_obligor(obligor_id: str) -> list[dict[str, Any]]:
    return [r for r in all_current() if str(r.get("obligor_id")) == str(obligor_id) and r.get("status") != "superseded"]


def _facility(proposal_id: str) -> str:
    rows = store.read("dd_proposal_facility", proposal_id=proposal_id)
    if rows:
        return str(rows[0].get("facility_id") or f"{proposal_id}-F1")
    return f"{proposal_id}-F1"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _row(base: dict[str, Any], **kw: Any) -> dict[str, Any]:
    r = {**base, **kw}
    months = int(r["review_frequency_months"])
    on = date.fromisoformat(str(r["set_on"])[:10])
    r["next_review_date"] = (on + timedelta(days=round(months * 30.44))).isoformat()
    return r


def publish_at_approval(proposal_id: str, terms: dict[str, Any] | None = None, *, approved_by: str, reason: str = "",
                        run: dict[str, Any] | None = None, el_view: str = "economic", capital_basis: str | None = None) -> dict[str, Any]:
    """At approval: stress the approved structure, publish its results (context approval) and the monitoring plan."""
    from backend.dealdesk.stress2 import ladder
    if not approved_by:
        raise PlanError("approved_by is required")
    p = store.deal(proposal_id)
    out = run or ladder.run(p, terms, el_view=el_view, capital_basis=capital_basis, publish=False)
    ladder.publish_result(out, context="approval", by=approved_by)
    t = out["tier"]
    prev = current(proposal_id)
    ver = (prev["version"] + 1) if prev else 1
    row = _row({
        "plan_id": f"MP-{proposal_id}-{ver}", "proposal_id": proposal_id, "facility_id": _facility(proposal_id),
        "obligor_id": p["obligor"].get("obligor_id"), "obligor_name": p["obligor"]["name"], "sector": p["obligor"]["sector"],
        "tier": t["tier"], "verdict": out["verdict"]["verdict"], "worst_breaking_severity": out["verdict"]["worst_breaking_severity"], "drivers": t["drivers"], "driver_labels": t["driver_labels"],
        "triggers": t["triggers"], "ews_thresholds": t["ews_thresholds"], "review_frequency_months": t["review_frequency_months"],
        "set_by": approved_by, "set_on": _today().isoformat(), "set_at": store.now(),
        "reason": reason or t["reason"], "source": "Deal Desk stress verdict at approval", "run_id": out["run_id"],
        "sensitivity_version": out["sensitivity_version"], "status": "active", "version": ver,
        "previous_tier": prev["tier"] if prev else None, "condition": f"Monitoring tier {t['tier']}: review every {t['review_frequency_months']} months"
                                                                      + (", named triggers: " + "; ".join(x["label"] for x in t["triggers"]) if t["triggers"] else ""),
    })
    old = [{**prev, "status": "superseded"}] if prev else []
    pub = store.publish("dd_monitoring_plan", old + [row])
    cond = store.publish("dd_condition", conditions(row, approved_by))
    find = store.publish("dd_review_finding", [finding(out, row, approved_by)])
    return {"plan": row, "published": pub, "conditions": cond, "finding": find, "stress": {"run_id": out["run_id"], "verdict": out["verdict"], "tier": t,
                                                       "commentary": out["commentary"]["text"]}}


def change_tier(proposal_id: str, tier: str, *, by: str, reason: str) -> dict[str, Any]:
    """Raise or lower the tier: only with a reason; the change is a new version, the old one stays in the log."""
    if tier not in mr.TIERS:
        raise PlanError(f"tier is one of {', '.join(mr.TIERS)}")
    if not by:
        raise PlanError("who changes the tier is required")
    if not reason or len(reason.strip()) < 5:
        raise PlanError("a tier change needs a reason")
    prev = current(proposal_id)
    if prev is None:
        raise PlanError(f"{proposal_id} has no monitoring plan yet: it is set at approval")
    if prev["tier"] == tier:
        raise PlanError(f"{proposal_id} is already tier {tier}")
    trig = [{**x, "action": "alert" if tier == "High" else "watch"} for x in (prev.get("triggers") or [])] if tier != "Standard" else []
    if tier != "Standard" and not trig:
        trig = [{"trigger_id": "T-DSCR", "driver": "dscr", "label": "DSCR below 1.10x", "metric": "dscr_x",
                 "source": "corp_borrower_quarter (borrower ratios)", "op": "<", "threshold": 1.1, "unit": "x",
                 "action": "alert" if tier == "High" else "watch", "basis": "set on a manual tier change"}]
    ver = prev["version"] + 1
    row = _row({**{k: v for k, v in prev.items() if k not in ("next_review_date",)},
                "plan_id": f"MP-{proposal_id}-{ver}", "tier": tier, "triggers": trig, "ews_thresholds": mr.ews_thresholds(tier),
                "review_frequency_months": mr.REVIEW_MONTHS[tier], "set_by": by, "set_on": _today().isoformat(), "set_at": store.now(),
                "reason": reason.strip(), "source": "manual tier change", "status": "active", "version": ver, "previous_tier": prev["tier"]})
    pub = store.publish("dd_monitoring_plan", [{**prev, "status": "superseded"}, row])
    gone = [{"condition_id": f"D-{proposal_id}-{t['trigger_id']}", "proposal_id": proposal_id, "kind": "monitoring", "status": "waived",
             "text": f"Named trigger withdrawn with the tier change to {tier}: {t['label']}.", "source": "stress", "set_by": by,
             "set_at": row["set_at"]} for t in (prev.get("triggers") or []) if t["trigger_id"] not in {x["trigger_id"] for x in trig}]
    store.publish("dd_condition", conditions(row, by) + gone)
    return {"plan": row, "published": pub, "change": {"from": prev["tier"], "to": tier, "by": by, "reason": reason.strip()}}


def as_json(r: dict[str, Any]) -> str:
    return json.dumps(r, default=str, sort_keys=True)


FREQ_WORD = {3: "quarterly", 6: "semi_annual", 12: "annual"}
SEVERITY = {"Restructure": "high", "Approve with enhanced monitoring": "medium", "Approve, standard monitoring": "low", "Approve": "info"}


def conditions(plan: dict[str, Any], by: str) -> list[dict[str, Any]]:
    """The tier as approval conditions (dd_condition, source stress): the review cycle, and one monitoring condition per
    named trigger with its metric, operator and threshold."""
    pid = plan["proposal_id"]
    at = plan["set_at"]
    rows = [{"condition_id": f"D-{pid}-TIER", "proposal_id": pid, "limit_id": "ALL", "kind": "monitoring",
             "text": f"Monitoring tier {plan['tier']} set from the stress verdict ({plan['verdict']}): credit review every "
                     f"{plan['review_frequency_months']} months, next by {plan['next_review_date']}; the tier changes only with a recorded reason.",
             "owner": "RM and credit risk", "due_date": plan["next_review_date"], "frequency": FREQ_WORD.get(int(plan["review_frequency_months"]), "annual"),
             "status": "open", "source": "stress", "set_by": by, "set_at": at}]
    for t in plan.get("triggers") or []:
        rows.append({"condition_id": f"D-{pid}-{t['trigger_id']}", "proposal_id": pid, "limit_id": "ALL", "kind": "monitoring",
                     "text": f"Named trigger: {t['label']} ({'Early Warning alert' if t.get('action') == 'alert' else 'watched'}; {t.get('basis', '')}).",
                     "owner": "Early Warning and RM", "frequency": "quarterly", "trigger_metric": t["metric"], "trigger_operator": t["op"],
                     "trigger_threshold": float(t["threshold"]), "status": "open", "source": "stress", "set_by": by, "set_at": at})
    return rows


def finding(out: dict[str, Any], plan: dict[str, Any], by: str) -> dict[str, Any]:
    """The stress verdict as a review finding (dd_review_finding, point 4 re-performed analysis, category stress)."""
    v = out["verdict"]
    return {"finding_id": f"D-{plan['proposal_id']}-STRESS", "proposal_id": plan["proposal_id"], "review_point": 4, "category": "stress",
            "severity": SEVERITY.get(v["verdict"], "info"), "title": f"Stress verdict: {v['verdict']} (tier {plan['tier']})",
            "finding_text": out["commentary"]["text"], "evidence_domain": "deal_desk", "evidence_relation": "dd_stress_result",
            "evidence_key": f"run_id={out['run_id']}", "status": "open", "rating_notch": 0, "condition_id": f"D-{plan['proposal_id']}-TIER",
            "raised_by": f"D:{by}", "raised_at": plan["set_at"]}
