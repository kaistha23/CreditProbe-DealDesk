"""Early Warning <- Deal Desk: the read-only adapter (PLAN_R12 §1.5 "the tier travels").

EWS reads `dd_monitoring_plan` through this module; the EWS engine (rule set, weights, book-wide band floors) is
unchanged. Two things change for a name with a Deal Desk plan:

  threshold override   tier High lowers that name's band floors (`monitoring.rules.ews_thresholds`): the same rule
                       score reaches a band sooner. Shown next to the book band, never written into the EWS book.
  named triggers       the stressed driver as an observable condition ("largest customer share > 40%"). A fired
                       trigger on a tier-High name raises an EWS alert (`dd_monitoring_alert` where registered, else
                       the staging store) and a Book card; on tier Medium it is a Book watch card only.

Every observation is read from a registered relation: the EWS corporate exposure book through the EWS reader
(`backend.ews_domain.reader`), borrower ratios (`corp_borrower_quarter`) by its Data Domains registry path, and
deal facts (`dd_obligor_financials`, `dd_project`) through Session E's reader.
"""
from __future__ import annotations

import functools
import math
from typing import Any

from backend.dealdesk.monitoring import plan as mp
from backend.dealdesk.monitoring import rules as mr
from backend.dealdesk.stress2 import facts as fx
from backend.dealdesk.stress2 import store

DOMAIN = "corporate"


def _registry_path(relation: str):
    from pathlib import Path
    from backend.data_builder import registry
    for d in registry.DOMAINS.values():
        rel = d.get("relations", {})
        for rid, spec in rel.items():
            if rid == relation or spec.get("path", "").endswith(f"/{relation}.parquet"):
                return Path(__file__).resolve().parents[2] / spec["path"]
    raise LookupError(f"{relation} is not a registered relation")


@functools.lru_cache(maxsize=1)
def _borrowers():
    import pandas as pd
    b = pd.read_parquet(_registry_path("corp_borrower_quarter"))
    return b


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def ews_rows(customer_id: str, period: str = "") -> tuple[str | None, list[dict[str, Any]], str | None]:
    """(period, the name's facility rows in the EWS book at that period, the previous period)."""
    from backend.ews_domain import reader as rd
    try:
        chosen, prior, _all = rd.resolve_period(DOMAIN, period)
    except Exception:  # noqa: BLE001
        return None, [], None
    rows = rd.q(f'SELECT * FROM {rd.exposure(DOMAIN)} WHERE "borrower_id" = ? AND "reporting_quarter" = ?', [customer_id, chosen])
    return chosen, rows, prior


def observations(customer_id: str, period: str = "", proposal_id: str | None = None) -> dict[str, Any]:
    chosen, rows, prior = ews_rows(customer_id, period)
    obs: dict[str, Any] = {"customer_id": customer_id, "period": chosen, "in_ews_book": bool(rows)}
    if rows:
        def agg(col: str, f) -> float | None:
            vals = [_num(r.get(col)) for r in rows]
            vals = [v for v in vals if v is not None]
            return f(vals) if vals else None
        obs.update({"ews_score": agg("ews_score", max), "inflow_trend_pct": agg("inflow_trend_pct", min),
                    "returned_payments_q": agg("returned_payments_q", max), "external_dpd_days": agg("external_dpd_days", max),
                    "collateral_ltv_pct": agg("collateral_ltv_pct", max), "rating_notches_moved": agg("rating_notches_moved", min),
                    "dpd_days": agg("dpd_days", max), "stage": agg("stage", max)})
        obs["ews_band"] = max((str(r.get("ews_band") or "none") for r in rows), key=lambda b: ["none", "low", "moderate", "high", "critical"].index(b)
                              if b in ["none", "low", "moderate", "high", "critical"] else 0)
        if prior:
            _p, prow, _ = ews_rows(customer_id, prior)
            ps = [_num(r.get("ews_score")) for r in prow]
            ps = [v for v in ps if v is not None]
            obs["ews_score_prior"] = max(ps) if ps else None
            obs["prior_period"] = prior
        try:
            b = _borrowers()
            br = b[(b["borrower_id"] == customer_id) & (b["reporting_quarter"] == chosen)]
            if not br.empty:
                r = br.iloc[0].to_dict()
                obs["dscr_x"] = _num(r.get("dscr_x"))
                obs["ebitda_margin_pct"] = _num(r.get("ebitda_margin_pct"))
                obs["leverage_x"] = _num(r.get("leverage_x"))
        except Exception:  # noqa: BLE001 - ratios absent: those triggers read as not observed
            pass
    if proposal_id:
        try:
            p = store.deal(proposal_id)
            lc = fx.largest_customer(p)
            if lc:
                obs["largest_customer_share"] = lc["value"]
            prj = store.read("dd_project", proposal_id=proposal_id)
            ext = [(_num(r.get("eot_days")) or 0) / 30.44 if r.get("eot_days") is not None else _num(r.get("extension_months")) for r in prj]
            ext = [v for v in ext if v is not None]
            if ext:
                obs["extension_months"] = max(ext)
        except Exception:  # noqa: BLE001
            pass
    return obs


def band_with(floors: dict[str, int], score: float | None) -> str:
    s = int(score or 0)
    for name in ("critical", "high", "moderate"):
        if s >= floors[name]:
            return name
    return "low" if s >= 1 else "none"


def evaluate(plan: dict[str, Any], period: str = "") -> dict[str, Any]:
    oid = str(plan.get("obligor_id") or "")
    obs = observations(oid, period, plan["proposal_id"]) if oid else {"in_ews_book": False}
    th = plan.get("ews_thresholds") or mr.ews_thresholds(plan["tier"])
    trig = []
    for t in plan.get("triggers") or []:
        fired, val = mr.fires(t, obs)
        trig.append({**t, "observed": val, "fired": fired})
    over = band_with(th["band_floors"], obs.get("ews_score")) if obs.get("in_ews_book") else None
    return {"plan": plan, "observations": obs, "thresholds": th, "book_band": obs.get("ews_band"), "band_with_override": over,
            "override_raises_band": bool(over and obs.get("ews_band") and over != obs.get("ews_band") and th.get("override")),
            "triggers": trig, "fired": [t for t in trig if t["fired"]]}


def _sentence(plan: dict[str, Any]) -> str:
    because = ", ".join((d if len(d) > 1 and d[1].isupper() else d[:1].lower() + d[1:]) for d in plan.get("driver_labels") or []) \
        or ((lambda r: r if len(r) > 1 and r[1].isupper() else r[:1].lower() + r[1:])(str(plan.get("reason") or "").strip().rstrip(".")) or "of the stress verdict")  # R12 M: a Book tier change has a reason, no drivers
    return f"Monitoring tier {plan['tier']}, set by Deal Desk on {plan.get('set_on')} because {because}"


def panel(customer_id: str, period: str = "") -> dict[str, Any]:
    """What the EWS customer page shows: the plan (or none), the override, the triggers and any alert raised."""
    plans = mp.for_obligor(customer_id)
    if not plans:
        return {"customer_id": customer_id, "has_plan": False, "sentence": "No Deal Desk monitoring plan for this name.",
                "backend": store.backend("dd_monitoring_plan")}
    plan = max(plans, key=lambda r: mr.TIER_ORDER.get(r["tier"], 0))
    ev = evaluate(plan, period)
    alerts = raise_alerts([ev])
    return {"customer_id": customer_id, "has_plan": True, "sentence": _sentence(plan), "tier": plan["tier"],
            "set_by": plan.get("set_by"), "set_on": plan.get("set_on"), "reason": plan.get("reason"), "verdict": plan.get("verdict"),
            "review_frequency_months": plan.get("review_frequency_months"), "next_review_date": plan.get("next_review_date"),
            "proposal_id": plan["proposal_id"], "facility_id": plan.get("facility_id"), "drivers": plan.get("driver_labels") or [],
            "thresholds": ev["thresholds"], "book_band": ev["book_band"], "band_with_override": ev["band_with_override"],
            "override_raises_band": ev["override_raises_band"], "score": ev["observations"].get("ews_score"),
            "period": ev["observations"].get("period"), "in_ews_book": ev["observations"].get("in_ews_book"),
            "triggers": ev["triggers"], "alerts": alerts, "plans": [{"proposal_id": p["proposal_id"], "tier": p["tier"]} for p in plans],
            "backend": store.backend("dd_monitoring_plan"), "source": "dd_monitoring_plan (read-only)"}


def raise_alerts(evals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A fired trigger on a tier-High plan is an EWS alert (once per plan, trigger and period)."""
    out = []
    for ev in evals:
        plan = ev["plan"]
        per = ev["observations"].get("period") or ""
        for t in ev["fired"]:
            if t.get("action") != "alert":
                continue
            aid = f"EA-{plan['proposal_id']}-{t['trigger_id']}-{per}"
            row = {"alert_id": aid, "proposal_id": plan["proposal_id"], "obligor_id": plan.get("obligor_id"),
                   "obligor_name": plan.get("obligor_name"), "tier": plan["tier"], "trigger_id": t["trigger_id"],
                   "trigger": t["label"], "metric": t["metric"], "observed": t["observed"], "threshold": t["threshold"],
                   "period": per, "raised_at": store.now(), "source": "Deal Desk named trigger (dd_monitoring_plan)",
                   "plan_id": plan.get("plan_id"), "status": "open"}
            if not store.read("dd_monitoring_alert", alert_id=aid):
                store.publish("dd_monitoring_alert", [row])
            out.append(row)
    return out


def evaluate_all(period: str = "") -> dict[str, Any]:
    evals = [evaluate(p, period) for p in mp.all_current()]
    alerts = raise_alerts(evals)
    return {"plans": len(evals), "alerts": alerts, "cards": book_cards(evals)}


def book_cards(evals: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Book cards for Session I / U: a raised alert (tier High) or a watched driver that moved (tier Medium)."""
    evals = evals if evals is not None else [evaluate(p) for p in mp.all_current()]
    cards = []
    for ev in evals:
        p = ev["plan"]
        for t in ev["fired"]:
            cards.append({"proposal_id": p["proposal_id"], "obligor_id": p.get("obligor_id"), "obligor_name": p.get("obligor_name"),
                          "tier": p["tier"], "kind": "ews_alert" if t.get("action") == "alert" else "driver_watch",
                          "trigger_id": t["trigger_id"], "text": f"{p.get('obligor_name')}: {t['label']} (observed {_fmt(t['observed'], t.get('unit'))})",
                          "period": ev["observations"].get("period")})
    return cards


def tier_high_movers(period: str = "") -> list[dict[str, Any]]:
    """For Noor's brief: tier-High names whose EWS score rose on the quarter or whose trigger fired."""
    out = []
    for p in mp.all_current():
        if p["tier"] != "High":
            continue
        ev = evaluate(p, period)
        o = ev["observations"]
        moved = o.get("ews_score") is not None and o.get("ews_score_prior") is not None and o["ews_score"] > o["ews_score_prior"]
        if moved or ev["fired"]:
            out.append({"proposal_id": p["proposal_id"], "obligor_id": p.get("obligor_id"), "obligor_name": p.get("obligor_name"),
                        "score": o.get("ews_score"), "score_prior": o.get("ews_score_prior"), "fired": [t["label"] for t in ev["fired"]],
                        "sentence": f"{p.get('obligor_name')} (tier High): " + "; ".join(
                            ([f"EWS score {int(o['ews_score_prior'])} -> {int(o['ews_score'])}"] if moved else []) + [t["label"] for t in ev["fired"]])})
    return out


def _fmt(v: Any, unit: str | None) -> str:
    if v is None:
        return "not observed"
    if unit == "share":
        return f"{float(v) * 100:.0f}%"
    if unit == "%":
        return f"{float(v):.1f}%"
    if unit == "x":
        return f"{float(v):.2f}x"
    if unit == "months":
        return f"{float(v):.1f} months"
    return f"{float(v):.4g}"
