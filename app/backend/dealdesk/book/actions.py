"""Book row actions (PLAN_R12 §1.6): raise or lower the tier, open the deal, start the renewal, send to Early Warning.

Every action is a decision and is published (PLAN §0 rule 2) through E's publisher:
  tier change / send to EWS -> a new version of the facility's `dd_monitoring_plan` row (tier, reason, set by and on);
  start renewal             -> a `dd_workflow_event` (the deal reopens on Proposal) with the renewal pack.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk.book import core, drift, sources

TIER_RANK = {"Standard": 0, "Medium": 1, "High": 2}


class ActionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(fid: str) -> pd.Series:  # noqa: D401
    f, _ = core.frame()
    t = f[f.facility_id == fid]
    if not len(t):
        raise KeyError(fid)
    return t.iloc[0]


FREQ = {"High": "quarterly", "Medium": "semi_annual", "Standard": "annual"}
#: the contract's dd_monitoring_plan columns the Book writes (lineage columns are stamped by the publisher)
PLAN_COLS = ("plan_id", "proposal_id", "obligor_id", "facility_ref", "tier", "stress_verdict", "worst_breaking_severity", "drivers",
             "named_triggers", "ews_threshold_overrides", "review_frequency", "next_review_date", "set_by", "set_at", "reason",
             "status", "previous_tier")


def _prev_plan(r: pd.Series) -> dict[str, Any]:
    """The facility's current plan row as published (its own, else its deal's), or {}."""
    try:
        mp = sources.dd("dd_monitoring_plan")
    except sources.DataPending:
        return {}
    if not len(mp):
        return {}
    fc = core._col(mp, "facility_ref", "facility_id")  # noqa: SLF001
    deal = r.get("deal_id") if isinstance(r.get("deal_id"), str) else None
    if deal and "proposal_id" in mp.columns:  # a Deal Desk deal's facilities: the deal's own plan
        own = mp[mp.proposal_id == deal]
    else:
        own = mp[mp[fc] == r.facility_id] if fc else mp.iloc[0:0]
    if len(own):
        t = own
    elif "obligor_id" in mp.columns:  # no own plan: only a deal-wide plan of the obligor applies, never another facility's
        wide = mp[fc].astype(str).isin(["ALL", "", "None", "nan"]) | mp[fc].isna() if fc else pd.Series(True, index=mp.index)
        t = mp[(mp.obligor_id == r.borrower_id) & wide]
    else:
        t = mp.iloc[0:0]
    if "status" in t.columns:
        t = t[t.status.fillna("active").astype(str).str.lower() != "superseded"]
    if not len(t):
        return {}
    order = [x for x in ("rel_version", "set_at") if x in t.columns]
    if order:
        t = t.sort_values(order, kind="stable")
    row = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in t.iloc[-1].to_dict().items()}
    row["_own"] = bool(len(own))
    return row


def _plan_rows(r: pd.Series, prev: dict[str, Any], tier: str, reason: str, by: str, drivers_add: list[str] | None = None
               ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    months = int(drift.book_params()["tier_review_months"][tier])
    import uuid
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    drivers = core._json(prev.get("drivers")) if prev else None  # noqa: SLF001
    drivers = list(drivers) if isinstance(drivers, list) else []
    for d in drivers_add or []:
        if d not in drivers:
            drivers.append(d)
    keep = {k: prev.get(k) for k in ("stress_verdict", "worst_breaking_severity", "named_triggers", "ews_threshold_overrides")} if prev else {}
    if tier != "High":
        keep["ews_threshold_overrides"] = None  # only tier High lowers the EWS thresholds
    deal = r.get("deal_id") if isinstance(r.get("deal_id"), str) else None
    new = {**keep, "plan_id": f"MP-BK-{deal or r.facility_id}-{stamp}", "facility_ref": "ALL" if deal else r.facility_id,
           "obligor_id": r.borrower_id,
           "proposal_id": prev.get("proposal_id") if prev else (r.proposal_id if isinstance(r.proposal_id, str) else None),
           "tier": tier, "drivers": json.dumps(drivers), "review_frequency": FREQ[tier],
           "next_review_date": (datetime.now(timezone.utc).date() + timedelta(days=round(months * 30.44))).isoformat(),
           "set_by": by, "set_at": _now(), "reason": reason.strip(), "status": "active", "previous_tier": prev.get("tier") if prev else None}
    for k in ("named_triggers", "ews_threshold_overrides"):
        if isinstance(new.get(k), (list, dict)):
            new[k] = json.dumps(new[k])
    rows = [new]
    if prev and prev.get("_own") and prev.get("plan_id"):  # the facility's own previous version is superseded (a deal plan stays)
        old = {k: prev.get(k) for k in PLAN_COLS}
        for k in ("drivers", "named_triggers", "ews_threshold_overrides"):
            if isinstance(old.get(k), (list, dict)):
                old[k] = json.dumps(old[k])
        old["status"] = "superseded"
        old["reporting_quarter"] = prev.get("reporting_quarter")
        rows.insert(0, old)
    return new, rows


def set_tier(fid: str, tier: str, reason: str, by: str) -> dict[str, Any]:
    if tier not in TIER_RANK:
        raise ActionError(f"tier must be one of {', '.join(TIER_RANK)}")
    if not reason or not reason.strip():
        raise ActionError("a reason is required to change the monitoring tier")
    r = _row(fid)
    prev = _prev_plan(r)
    old = prev.get("tier") or None
    if old == tier:
        raise ActionError(f"the tier is already {tier}")
    direction = "raised" if old is None or TIER_RANK[tier] > TIER_RANK.get(old, -1) else "lowered"
    row, rows = _plan_rows(r, prev, tier, reason, by)
    res = sources.publish("dd_monitoring_plan", rows)
    core.refresh()
    return {"facility_id": fid, "tier": tier, "previous_tier": old, "change": direction, "plan": row, "published": res,
            "text": f"Monitoring tier {direction} to {tier} for {r.borrower_name} ({fid}) by {by}: {reason.strip()}"}


def send_to_ews(fid: str, reason: str, by: str) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise ActionError("a reason is required to send a name to Early Warning")
    r = _row(fid)
    prev = _prev_plan(r)
    tier = prev.get("tier") or "Medium"  # a name sent to Early Warning is watched at least semi-annually
    row, rows = _plan_rows(r, prev, tier, f"Sent to Early Warning from the Book: {reason.strip()}", by, drivers_add=["book_referral"])
    res = sources.publish("dd_monitoring_plan", rows)
    core.refresh()
    return {"facility_id": fid, "borrower_id": r.borrower_id, "tier": tier, "plan": row, "published": res, "ews_referral": True,
            "ews_url": f"/early-warning?domain=corporate&customer={r.borrower_id}",
            "text": f"{r.borrower_name} sent to Early Warning by {by} (monitoring tier {tier}): {reason.strip()}"}


def renewal_pack(fid: str) -> dict[str, Any]:
    """Last year's file, the status of its conditions and the drift, for the renewal proposal."""
    d = core.facility(fid)
    r = d["facility"]
    pid = r.get("proposal_id")
    conds: list[dict[str, Any]] = []
    try:
        c = sources.dd("dd_condition")
        if pid is not None and "proposal_id" in c.columns:
            conds = c[c.proposal_id == pid].replace({np.nan: None}).to_dict("records")
    except sources.DataPending:
        pass
    return {"facility_id": fid, "proposal_id": pid, "borrower_id": r["borrower_id"], "borrower_name": r["borrower_name"],
            "last_file": {"proposal_id": pid, "orig_date": r["orig_date"], "orig_rating": r["orig_rating"], "limit_sar_mn": r["limit_sar_mn"]},
            "conditions": conds, "promises": d["promises"], "drift": {"raroc_orig": r["raroc_orig"], "raroc_now": r["raroc_now"],
                                                                     "hurdle": r["hurdle"], "waterfall": d["waterfall"]},
            "repricing": d["repricing"], "covenants": d["covenants"]}


def _next_seq(pid: str | None) -> int:
    if not pid:
        return 1
    try:
        ev = sources.dd("dd_workflow_event")
    except sources.DataPending:
        return 1
    if not len(ev) or "seq" not in ev.columns:
        return 1
    s = pd.to_numeric(ev[ev.proposal_id == pid].seq, errors="coerce")
    return int(s.max()) + 1 if len(s) and s.notna().any() else 1


def start_renewal(fid: str, by: str, note: str = "", role: str = "") -> dict[str, Any]:
    pack = renewal_pack(fid)
    pid = pack["proposal_id"]
    created = False
    if not pid:  # a back-book facility without a Deal Desk file: open a renewal proposal pre-filled from the book
        from backend.dealdesk.book import renewal
        try:
            pid = renewal.create(fid, by)["proposal_id"]
            created = True
            pack["proposal_id"] = pid
        except Exception as e:  # noqa: BLE001 -- the proposal could not be pre-filled: say why, keep the pack
            pack["why_no_file"] = str(e)[:200]
    dr = pack["drift"]
    drift_txt = (f"drift {dr['raroc_orig'] * 100:.1f}% -> {dr['raroc_now'] * 100:.1f}% against {dr['hurdle'] * 100:.0f}%"
                 if all(isinstance(dr.get(k), (int, float)) for k in ("raroc_orig", "raroc_now", "hurdle")) else "no RAROC drift published")
    note = note or f"Renewal of {fid} started from the Book: {drift_txt}; {pack['repricing']['text'] or 'no repricing needed'}"
    ev = {"event_id": f"WE-RN-{fid}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", "proposal_id": pid, "seq": _next_seq(pid),
          "from_state": "approved", "to_state": "renewal_opened", "actor": by, "actor_role": role or "credit_reviewer", "at": _now(),
          "note": note[:500]}
    res = sources.publish("dd_workflow_event", [ev]) if pid else None
    url = (f"/deal-desk/{pid}?step=proposal&renewal={fid}" if pid
           else f"/deal-desk?tab=origination&new=renewal&obligor={pack['borrower_id']}&renewal={fid}")
    return {"facility_id": fid, "proposal_id": pid, "event": ev, "published": res, "url": url, "pack": pack,
            "created": created,
            "text": (f"Renewal of {pack['borrower_name']} opened as {pid} on Proposal, pre-filled from the book with last year's terms, "
                     f"the drift and the promises" if created else
                     f"Renewal of {pack['borrower_name']} reopened on Proposal with last year's file, conditions and drift" if pid
                     else f"Renewal of {pack['borrower_name']} started; the proposal could not be pre-filled ({pack.get('why_no_file', '')})")}


def open_deal(fid: str) -> dict[str, Any]:
    r = _row(fid)
    pid = r.proposal_id if isinstance(r.proposal_id, str) else None
    return {"facility_id": fid, "proposal_id": pid, "url": f"/deal-desk/{pid}" if pid else None,
            "book_url": f"/deal-desk?tab=book&facility={fid}"}
