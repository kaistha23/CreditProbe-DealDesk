"""Propose for monitoring (K35): one action and one page.

    prefill(...)        the form: tier, reason prefilled from the evidence (stress tier and drivers, RAROC drift, EWS band,
                        unmet promise, open critical findings), review frequency, named triggers, owner, due date
    propose(...)        a proposal row in dd_monitoring_proposal (status proposed; maker)
    decide(...)         maker-checker: approve (status active; the deal's monitoring plan or the Book facility's tier is
                        changed through their own writers, so Early Warning and Borrower 360 show it) or reject
    page()              the Monitoring page: proposed (awaiting approval), active by tier, triggers hit, reviews due, history
    for_obligor(id)     what Early Warning and Borrower 360 show for a borrower
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from backend.dealdesk import paths

TIERS = ("High", "Medium", "Standard")
FREQ = {"monthly": 1, "quarterly": 3, "semi_annual": 6, "annual": 12}
TIER_FREQ = {"High": "quarterly", "Medium": "semi_annual", "Standard": "annual"}
SOURCES = ("deal", "going_bad", "renewals", "book", "ews", "brief", "b360")
TODAY = dt.date.fromisoformat(getattr(paths, "AS_OF_DATE", "2026-10-18"))


class MonitoringError(ValueError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rows(**f: Any) -> list[dict[str, Any]]:
    from backend.dealdesk.data import store
    try:
        return store.dd_read("dd_monitoring_proposal", **f)
    except Exception:  # noqa: BLE001 - an empty relation is no proposals
        return []


def _due(freq: str) -> str:
    return (TODAY + dt.timedelta(days=30 * FREQ.get(freq, 3))).isoformat()


# ------------------------------------------------------------------ the form

def prefill(proposal_id: str | None = None, obligor_id: str | None = None, source: str = "deal", facility_ref: str = "ALL",
            evidence: list[dict[str, Any]] | None = None, obligor_name: str = "") -> dict[str, Any]:
    ev: list[dict[str, Any]] = list(evidence or [])
    tier, triggers, name, drivers = "Medium", [], obligor_name, []
    if proposal_id:
        from backend.dealdesk.stressproof import matrix as MX
        from backend.dealdesk.stressproof import structures as ST
        try:
            s = ST.structure_set(proposal_id)
            p = ST.deal(proposal_id)
            name = p["obligor"]["name"]
            obligor_id = obligor_id or p["obligor"].get("obligor_id")
            sel = next(r for r in s["rows"] if r["selected"])
            lr = MX.ladder_for(p, sel)
            tier = lr["tier"]["tier"]
            triggers = [{"metric": t.get("metric"), "operator": t.get("op"), "threshold": t.get("threshold"), "label": t.get("label")}
                        for t in lr["tier"]["triggers"]]
            drivers = lr["tier"].get("driver_labels") or []
            ev.append({"label": "Stress verdict", "value": f"{lr['verdict']['verdict']} (tier {tier}): {lr['verdict']['why']}",
                       "relation": "dd_stress_result"})
        except Exception:  # noqa: BLE001
            pass
        from backend.dealdesk.data import store
        try:
            dr = store.dd_read("dd_raroc_drift", proposal_id=proposal_id)
            if dr:
                d = dr[0]
                ev.append({"label": "RAROC drift", "value": f"{d['raroc_orig_pct']:.1f}% at origination → {d['raroc_now_pct']:.1f}% now "
                           f"({d['drift_pp']:+.1f} pp; hurdle {d['hurdle_pct']:.1f}%)", "relation": "dd_raroc_drift"})
        except Exception:  # noqa: BLE001
            pass
        try:
            pr = [r for r in store.dd_read("dd_promise", proposal_id=proposal_id) if str(r.get("status", "")).lower() in ("unmet", "missed", "behind")]
            if pr:
                ev.append({"label": "Unmet promise", "value": f"{len(pr)} promise{'s' if len(pr) > 1 else ''} not met: {pr[0].get('promise_text') or pr[0].get('label') or ''}".strip(),
                           "relation": "dd_promise"})
        except Exception:  # noqa: BLE001
            pass
    if not triggers:
        triggers = [{"metric": "dscr_x", "operator": "<", "threshold": 1.1, "label": "DSCR below 1.10x"},
                    {"metric": "dpd_days", "operator": ">", "threshold": 30, "label": "Days past due above 30"}]
    reason = "; ".join(f"{e['label']}: {e['value']}" for e in ev[:3]) or "Proposed for monitoring from " + source.replace("_", " ")
    freq = TIER_FREQ[tier]
    return {"proposal_id": proposal_id or "", "obligor_id": obligor_id or "", "obligor_name": name, "facility_ref": facility_ref or "ALL",
            "source_screen": source if source in SOURCES else "deal", "tier": tier, "reason": reason, "evidence": ev,
            "review_frequency": freq, "triggers": triggers, "owner": "Credit Risk monitoring", "due_date": _due(freq),
            "drivers": drivers, "tiers": list(TIERS), "frequencies": list(FREQ),
            "plain_words": ["This puts a borrower on a closer watch list, with a named reason, triggers and a review date.",
                            f"Suggested tier {tier}, reviewed {freq.replace('_', '-')}, from the evidence below.",
                            "A second person approves it before it becomes active (maker-checker)."]}


# ------------------------------------------------------------------ propose and decide

def propose(body: dict[str, Any], maker: str) -> dict[str, Any]:
    from backend.dealdesk.data import store
    tier = body.get("tier")
    if tier not in TIERS:
        raise MonitoringError("tier is High, Medium or Standard")
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 5:
        raise MonitoringError("a reason is required")
    freq = body.get("review_frequency") or TIER_FREQ[tier]
    if freq not in FREQ:
        raise MonitoringError("review frequency is monthly, quarterly, semi_annual or annual")
    if not (body.get("proposal_id") or body.get("obligor_id")):
        raise MonitoringError("a deal or a borrower is required")
    subj = body.get("proposal_id") or body.get("obligor_id")
    prev = [r for r in _rows() if (r.get("proposal_id") or r.get("obligor_id")) == subj]
    fac = body.get("facility_ref") or "ALL"
    open_ = next((r for r in prev if r["status"] == "proposed" and (r.get("facility_ref") or "ALL") == fac), None)
    n = len(prev) + 1
    # one open proposal per borrower and facility: proposing again revises it (same id), it does not add a second one
    mid = open_["monitoring_proposal_id"] if open_ else "MP14-" + hashlib.sha1(f"{subj}|{fac}|{n}".encode()).hexdigest()[:8].upper()
    active = [r for r in prev if r["status"] == "active"]
    row = {"monitoring_proposal_id": mid, "subject_kind": body.get("subject_kind") or ("deal" if body.get("proposal_id") else "borrower"),
           "proposal_id": body.get("proposal_id") or "", "obligor_id": body.get("obligor_id") or "", "obligor_name": body.get("obligor_name") or "",
           "facility_ref": body.get("facility_ref") or "ALL", "source_screen": body.get("source_screen") or "deal", "tier": tier,
           "previous_tier": active[-1]["tier"] if active else "", "reason": reason, "evidence_json": body.get("evidence") or [],
           "review_frequency": freq, "triggers_json": body.get("triggers") or [], "owner": body.get("owner") or "Credit Risk monitoring",
           "due_date": body.get("due_date") or _due(freq), "status": "proposed", "maker": maker or "deal desk", "made_at": _now(),
           "checker": "", "decided_at": None, "decision_note": "", "triggers_hit_json": []}
    store.publish("dd_monitoring_proposal", [row], mode="upsert", actor=maker or "deal desk")
    return get(mid)


def get(mid: str) -> dict[str, Any]:
    r = _rows(monitoring_proposal_id=mid)
    if not r:
        raise KeyError(mid)
    return r[0]


def _apply(row: dict[str, Any], by: str) -> str:
    """Apply an approved tier through the owner's writer: the Book facility, else the deal's monitoring plan."""
    reason = f"Monitoring proposal {row['monitoring_proposal_id']} approved: {row['reason']}"[:400]
    if row.get("facility_ref") and row["facility_ref"] != "ALL":
        try:
            from backend.dealdesk.book import actions
            actions.set_tier(row["facility_ref"], row["tier"], reason, by)
            return f"Book facility {row['facility_ref']} set to tier {row['tier']}"
        except Exception as e:  # noqa: BLE001
            return f"Book facility not changed ({str(e)[:80]})"
    if row.get("proposal_id"):
        try:
            from backend.dealdesk.monitoring import plan
            cur = plan.current(row["proposal_id"])
            if cur and cur["tier"] != row["tier"]:
                plan.change_tier(row["proposal_id"], row["tier"], by=by, reason=reason)
                return f"Monitoring plan of {row['proposal_id']} changed to tier {row['tier']}"
            if cur:
                return f"Monitoring plan of {row['proposal_id']} already tier {row['tier']}"
            return "No monitoring plan on the deal yet: the tier is set at approval; this proposal is the record"
        except Exception as e:  # noqa: BLE001
            return f"Monitoring plan not changed ({str(e)[:80]})"
    return "Recorded for the borrower (no deal or facility)"


def decide(mid: str, approve: bool, checker: str, note: str = "") -> dict[str, Any]:
    from backend.dealdesk.data import store
    r = get(mid)
    if r["status"] != "proposed":
        raise MonitoringError(f"{mid} is {r['status']}, not awaiting a decision")
    if checker and r.get("maker") and checker == r["maker"]:
        raise MonitoringError("maker-checker: the person who proposed cannot approve or reject")
    if not approve and len((note or "").strip()) < 5:
        raise MonitoringError("a rejection needs a note")
    applied = _apply(r, checker or "checker") if approve else ""
    row = {**r, "status": "active" if approve else "rejected", "checker": checker or "checker", "decided_at": _now(),
           "decision_note": ((note or "").strip() + (f" · {applied}" if applied else "")).strip(" ·")}
    row = {k: v for k, v in row.items() if k not in ("reporting_quarter", "rel_version", "published_at")}
    upd = [row]
    if approve:
        for o in _rows():
            if o["monitoring_proposal_id"] != mid and o["status"] == "active" and (o.get("proposal_id") or o.get("obligor_id")) == (r.get("proposal_id") or r.get("obligor_id")) \
                    and (o.get("facility_ref") or "ALL") == (r.get("facility_ref") or "ALL"):
                upd.append({**{k: v for k, v in o.items() if k not in ("reporting_quarter", "rel_version", "published_at")}, "status": "closed",
                            "decision_note": (o.get("decision_note") or "") + f" · superseded by {mid}"})
    store.publish("dd_monitoring_proposal", upd, mode="upsert", actor=checker or "checker")
    return {**get(mid), "applied": applied}


# ------------------------------------------------------------------ the page and the borrower view

def hits(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The named triggers of an active proposal tested on the borrower's latest Early Warning and ratio data
    (ews_link.observations: the EWS book and corp_borrower_quarter, read through registered relations)."""
    if not row.get("obligor_id"):
        return []
    try:
        from backend.dealdesk.monitoring import rules as mr
        from backend.ews_link import adapter
        obs = adapter.observations(row["obligor_id"], "", row.get("proposal_id") or None)
    except Exception:  # noqa: BLE001 - no EWS data: no trigger can be tested
        return []
    out = []
    for t in row.get("triggers_json") or []:
        op = t.get("operator") or t.get("op")
        if not t.get("metric") or op not in ("<", "<=", ">", ">=") or t.get("threshold") is None:
            continue
        fired, val = mr.fires({"metric": t["metric"], "op": op, "threshold": t["threshold"]}, obs)
        if fired:
            out.append({"label": t.get("label") or t["metric"], "value": val, "at": obs.get("period")})
    return out


def page(viewer: str = "") -> dict[str, Any]:
    rows = sorted(_rows(), key=lambda r: r.get("made_at") or "", reverse=True)
    for r in rows:
        r["own"] = bool(viewer) and r.get("maker") == viewer
        if r["status"] == "active":
            live = hits(r)
            if live:
                r["triggers_hit_json"] = live
    proposed = [r for r in rows if r["status"] == "proposed"]
    active = [r for r in rows if r["status"] == "active"]
    by_tier = {t: [r for r in active if r["tier"] == t] for t in TIERS}
    hit = [r for r in active if r.get("triggers_hit_json")]
    due = sorted([r for r in active if str(r.get("due_date") or "") <= (TODAY + dt.timedelta(days=30)).isoformat()], key=lambda r: str(r.get("due_date")))
    plans = []
    try:
        from backend.dealdesk.monitoring import plan
        plans = plan.all_current()
    except Exception:  # noqa: BLE001
        pass
    plain = ["This page lists every borrower proposed for closer monitoring and every one under watch.",
             f"{len(proposed)} proposal{'s' if len(proposed) != 1 else ''} wait for a checker; {len(active)} active "
             f"({len(by_tier['High'])} High, {len(by_tier['Medium'])} Medium, {len(by_tier['Standard'])} Standard).",
             f"{len(due)} review{'s' if len(due) != 1 else ''} due in the next 30 days; {len(hit)} with a trigger hit (tested on the latest Early Warning data).",
             "Approve or reject a proposal; the maker cannot approve their own."]
    return {"as_of": paths.AS_OF, "today": TODAY.isoformat(), "proposed": proposed, "active": active,
            "active_by_tier": {t: len(v) for t, v in by_tier.items()}, "triggers_hit": hit, "reviews_due": due,
            "history": rows[:200], "plans_from_approval": len(plans), "plain_words": plain,
            "counts": {"proposed": len(proposed), "active": len(active), "due_30d": len(due), "triggers_hit": len(hit)}}


def for_obligor(obligor_id: str) -> dict[str, Any]:
    rows = [r for r in _rows(obligor_id=obligor_id) if r["status"] in ("proposed", "active")]
    act = next((r for r in rows if r["status"] == "active"), None)
    prop = next((r for r in rows if r["status"] == "proposed"), None)
    line = None
    if act:
        line = f"Monitoring tier {act['tier']} since {str(act.get('decided_at') or '')[:10]}: {act['reason'][:140]}; next review {act['due_date']}."
    elif prop:
        line = f"Proposed for monitoring (tier {prop['tier']}), awaiting approval: {prop['reason'][:140]}."
    return {"obligor_id": obligor_id, "active": act, "proposed": prop, "line": line}
