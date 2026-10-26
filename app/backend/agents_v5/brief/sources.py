"""Every source the brief ranks across (I11, I13 point 5). Each collector reads its facts through `readers` (Data
Domains) or, for agent working memory, through the owning agent's store, read-only. A collector that has nothing to
read on this build reports why and returns no lines; it never fails the brief.

Collectors and where they read:

| source | reads |
|---|---|
| cockpit_attention | the Cockpit attention cards, unchanged (passed in by the caller, who read the frozen feed) |
| sector_appetite | deal_desk.dd_portfolio_snapshot (sector share against the appetite limit) + dd_proposal (pipeline) |
| regulatory_breach | regulatory.crm_breach |
| ews_triage | the EWS triage agent's pending SICR / UTP / watchlist proposals (agents approvals store) + classification.cls_exposure (new Stage 2 / 3 this period) |
| lenses_alert | the Lenses monitoring agent's alerts (its store) |
| dd_queue | deal_desk.dd_workflow_event when E has published it, else deal_desk.dd_proposal status |
| dd_query | deal_desk.dd_query (open RM queries) |
| tier_high | deal_desk.dd_monitoring_plan (tier High) joined with ews.corp_exposure (who moved) |
| condition_due | deal_desk.dd_condition (due or overdue in 30 days) + watch.watch_item (accepted-risk triggers due) |
| renewal | deal_desk.dd_raroc_drift (below hurdle, renewal in 3–6 months) |
| approval | the agents' approvals waiting for this persona |
| deadline | queries.query_case (auditor and regulator letters) + ecl_runs.ecl_anomaly (re-run before the ECL run) |
| large_exposure | collateral.col_large_exposure (groups above 80% of the large-exposure limit) |
| scorecard_monitoring | scorecard_monitoring.sc_monitor_metric / sc_model_inventory / sc_findings_register (R16 M8: red MMSG breaches on Tier 1 scorecards) |
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import Item, fdate, fmt, num, src

logger = logging.getLogger(__name__)

ACTIVE_DEAL = ("new", "in_review", "counter_offered", "submitted", "draft", "queries")


from backend.v5common import edition as _edition  # noqa: E402

#: Deal Desk edition: the brief names no module that is not in the product, and links stay inside it.
_WARNED_LABEL = "flagged high or critical risk" if _edition.is_dealdesk() else "Early Warning rates high or critical"


def _open(full_href: str, full_label: str, dd_href: str, dd_label: str) -> dict:
    """A line's link: the full product's screen, or the Deal Desk edition's."""
    return {"href": dd_href, "label": dd_label} if _edition.is_dealdesk() else {"href": full_href, "label": full_label}



def _f(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _today(ctx: dict[str, Any]) -> date:
    t = ctx.get("today")
    if isinstance(t, date):
        return t
    try:
        return date.fromisoformat(str(t))
    except (TypeError, ValueError):
        return date.today()


# ------------------------------------------------------------------ Cockpit attention cards (evidence layer)

_COCKPIT_SEV = {"critical": "critical", "high": "high", "elevated": "high", "medium": "medium", "moderate": "medium",
                "low": "low", "info": "low"}


def cockpit_attention(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    cards = ctx.get("attention") or []
    if not cards:
        return [], {"status": "not_supplied", "note": "The Cockpit attention cards are read by the page and passed in."}
    out: list[Item] = []
    for c in cards[:10]:
        if not isinstance(c, dict) or not c.get("item_id"):
            continue
        seg = c.get("segment_label") or c.get("segment") or ""
        numbers = [num(str(k.get("label") or ""), _f(k.get("value")), str(k.get("unit") or ""),
                       str(k.get("display") or k.get("formatted") or ""))
                   for k in (c.get("key_numbers") or [])[:3] if isinstance(k, dict)]
        out.append(Item(
            id=f"cockpit:{c['item_id']}", source="cockpit_attention", source_label="Cockpit", module="cockpit",
            title=str(c.get("headline") or c.get("one_line") or seg), detail=str(c.get("one_line") or c.get("what_changed") or ""),
            severity=_COCKPIT_SEV.get(str(c.get("severity") or "").lower(), "medium"),
            materiality_sar_mn=None, since=str(c.get("reporting_period") or ""), audiences=("cro", "analyst", "reviewer"),
            kind="sector_appetite" if str(c.get("segment_dimension") or "") == "sector" else "attention",
            numbers=numbers,
            trace=[{"domain": "cockpit", "relation": "attention feed", "keys": {"item_id": c["item_id"]},
                    "period": str(c.get("reporting_period") or ""), "status": "frozen_feed"}],
            show_me={"href": f"/?attention={c['item_id']}", "label": "Open the card on the Cockpit"},
            open={"href": f"/?attention={c['item_id']}", "label": "Open"},
            entity={"kind": "segment", "id": str(c.get("segment") or ""), "name": seg,
                    "dimension": str(c.get("segment_dimension") or ""), "score": c.get("score")},
        ))
    return out, {"status": "ok", "rows": len(out)}


# ------------------------------------------------------------------ sector appetite (Deal Desk portfolio headroom)

def sector_appetite(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    snap = R.read("deal_desk", "dd_portfolio_snapshot", where="dimension = 'sector'")
    if snap.status != "ok":
        return [], {"status": snap.status, "note": snap.note}
    pipe = R.read("deal_desk", "dd_proposal", columns="proposal_id, obligor_name, sector, status, amount_sar_mn")
    pipeline: dict[str, list[dict[str, Any]]] = {}
    for p in pipe.rows:
        if str(p.get("status") or "") in ACTIVE_DEAL:
            pipeline.setdefault(str(p.get("sector") or ""), []).append(p)
    # Early Warning's high or critical exposure per sector, now and four quarters back (ews.corp_series_segment).
    ser = R.read("ews", "corp_series_segment",
                 columns="sector, reporting_quarter AS q, sum(CASE WHEN ews_band IN ('critical','high') THEN ead_sar_mn "
                         "ELSE 0 END) AS warned",
                 where=f"reporting_quarter IN (SELECT DISTINCT reporting_quarter FROM {_src('ews', 'corp_series_segment')} "
                       "ORDER BY 1 DESC LIMIT 5)", group="1, 2")
    qs = sorted({str(x["q"]) for x in ser.rows})
    warned = {(str(x["sector"]), str(x["q"])): _f(x["warned"]) or 0.0 for x in ser.rows}
    out: list[Item] = []
    for r in snap.rows:
        share, limit = _f(r.get("share_pct")), _f(r.get("limit_pct"))
        if share is None or not limit:
            continue
        use = share / limit
        if use < 0.9:
            continue
        sector = str(r.get("dimension_name") or r.get("dimension_key"))
        head = _f(r.get("headroom_sar_mn")) or 0.0
        deals = pipeline.get(sector, [])
        asked = sum(_f(d.get("amount_sar_mn")) or 0.0 for d in deals)
        q = str(r.get("reporting_quarter") or "")
        k_snap = {"dimension": "sector", "dimension_key": r.get("dimension_key")}
        breach = share > limit
        title = (f"{sector} is {share:.1f}% of the corporate book, above its {limit:.0f}% appetite limit "
                 f"({fmt(-head, 'SAR mn')} over)" if breach else
                 f"{sector} is {share:.1f}% of the corporate book against a {limit:.0f}% appetite limit: "
                 f"{fmt(head, 'SAR mn')} headroom left")
        w_now = warned.get((sector, qs[-1])) if qs else None
        w_then = warned.get((sector, qs[0])) if len(qs) >= 5 else None
        growth = (w_now / w_then) if w_now and w_then else None
        if growth and growth >= 1.5:
            title += (f"; the part {_WARNED_LABEL} has grown {growth:.1f}x in a year to "
                      f"{fmt(w_now, 'SAR mn')}")
        if deals:
            title += (f", and {len(deals)} more deal{'s ask' if len(deals) != 1 else ' asks'} {fmt(asked, 'SAR mn')}")
        out.append(Item(
            id=f"appetite:{r.get('dimension_key')}", source="sector_appetite", source_label="Risk appetite",
            module="dealdesk", title=title,
            detail=(f"{str(r.get('limit_kind') or '').capitalize() or 'Appetite'} limit. Exposure "
                    f"{fmt(_f(r.get('ead_sar_mn')), 'SAR mn')} at {q}."),
            severity="critical" if breach and r.get("limit_kind") == "hard" else
                     ("high" if breach or use >= 0.95 or (growth or 0) >= 2 else "medium"),
            materiality_sar_mn=abs(head) if breach else (w_now or asked or None), since=q, audiences=("cro", "reviewer", "rm", "analyst"),
            kind="sector_appetite",
            numbers=[num("Share of book", share, "%", source=src("deal_desk", "dd_portfolio_snapshot", k_snap, "share_pct", q)),
                     num("Appetite limit", limit, "%", source=src("deal_desk", "dd_portfolio_snapshot", k_snap, "limit_pct", q)),
                     num("Headroom", head, "SAR mn", source=src("deal_desk", "dd_portfolio_snapshot", k_snap, "headroom_sar_mn", q)),
                     num("Pipeline asked", asked, "SAR mn",
                         source=src("deal_desk", "dd_proposal", {"proposal_id": [d["proposal_id"] for d in deals]}, "amount_sar_mn")
                         if deals else None)]
                    + ([num("Warned exposure", w_now, "SAR mn", source=src("ews", "corp_series_segment",
                            {"sector": sector, "reporting_quarter": qs[-1], "ews_band": ["critical", "high"]}, "ead_sar_mn", qs[-1])),
                        num("Warned, a year ago", w_then, "SAR mn", source=src("ews", "corp_series_segment",
                            {"sector": sector, "reporting_quarter": qs[0], "ews_band": ["critical", "high"]}, "ead_sar_mn", qs[0]))]
                       if growth else []),
            trace=[snap.stamp({"dimension": "sector", "dimension_key": r.get("dimension_key")}, q),
                   ser.stamp({"sector": sector, "ews_band": ["critical", "high"]}, qs[-1] if qs else ""),
                   pipe.stamp({"sector": sector, "status": "active"}, q)],
            show_me={"href": f"/deal-desk?sector={quote(sector)}", "label": f"Show the {sector} deals"},
            open=_open(f"/early-warning?domain=corporate&segment={quote(sector)}", f"Open {sector} in Early Warning",
                       f"/deal-desk/review?sector={quote(sector)}", f"Open the {sector} deals in review"),
            entity={"kind": "sector", "id": str(r.get("dimension_key")), "name": sector,
                    "deals": [d.get("proposal_id") for d in deals]},
        ))
    return out, {"status": "ok", "rows": len(out)}


# ------------------------------------------------------------------ regulatory breaches

def regulatory_breach(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    r = R.read("regulatory", "crm_breach",
               columns="check_id, article, title, severity, max(period) AS period, count(*) AS n, "
                       "sum(ead_sar_mn) AS ead, sum(shortfall_sar_mn) AS shortfall",
               where="book = 'corporate' AND severity IN ('high', 'critical')", group="1, 2, 3, 4",
               order="shortfall DESC, ead DESC", limit=3)
    if r.status != "ok":
        return [], {"status": r.status, "note": r.note}
    out = []
    for b in r.rows:
        n, ead, sf = int(b.get("n") or 0), _f(b.get("ead")) or 0.0, _f(b.get("shortfall")) or 0.0
        title = f"{b['title']}: {n:,} exposure{'s' if n != 1 else ''}, {fmt(ead, 'SAR mn')} EAD"
        if sf:
            title += f", {fmt(sf, 'SAR mn')} provision shortfall"
        # R14 r (K4 (1)): the line states the rule as a comparison, bank vs requirement, both rates named.
        compare = _issue_line(str(b["check_id"]))
        issue = _issue_href(f"crm:{b['check_id']}")
        if compare:
            title = f"{b['title']}: {compare[0].lower()}{compare[1:]}"
        out.append(Item(
            id=f"crm:{b['check_id']}", source="regulatory_breach", source_label="Regulatory checks", module="regulatory",
            title=title, detail=f"{b.get('article')}.",
            severity="critical" if sf > 100 else "high",
            materiality_sar_mn=sf or ead, since=str(b.get("period") or ""), audiences=("cro", "analyst"),
            kind="breach",
            numbers=[num("Exposures", n), num("EAD", ead, "SAR mn"), num("Shortfall", sf, "SAR mn")],
            trace=[r.stamp({"check_id": b["check_id"], "book": "corporate"}, str(b.get("period") or ""))],
            show_me={"href": issue, "label": "Open the deep dive"},
            open={"href": issue, "label": "Open the issue"},
            entity={"kind": "check", "id": b["check_id"], "name": b["title"], "article": b.get("article")},
        ))
    return out, {"status": "ok", "rows": len(out)}


# ------------------------------------------------------------------ Early Warning triage

def ews_triage(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    out: list[Item] = []
    status: dict[str, Any] = {"status": "ok"}
    try:
        from backend.agents_v5.runtime import approvals
        pend = [a for a in approvals.listing(agent="ews.triage", status="pending")]
    except Exception as e:  # noqa: BLE001
        pend, status = [], {"status": "unavailable", "note": str(e)[:200]}
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for a in pend:
        by_kind.setdefault(str(a.get("kind") or "proposal"), []).append(a)
    for kind, rows in sorted(by_kind.items()):
        label = {"utp": "unlikely-to-pay", "sicr": "SICR (Stage 2)", "watchlist": "watchlist"}.get(kind.split(".")[-1], kind)
        names = [str((a.get("change") or {}).get("borrower_name") or a.get("title") or "") for a in rows[:3]]
        out.append(Item(
            id=f"ews:proposals:{kind}", source="ews_triage", source_label="Early Warning triage", module="ews",
            title=f"Early Warning proposes {len(rows)} {label} classification{'s' if len(rows) != 1 else ''} for your decision",
            detail="Names: " + ", ".join(n for n in names if n) + ("…" if len(rows) > 3 else ""),
            severity="high" if kind.endswith("utp") else "medium", materiality_sar_mn=None,
            since=str(rows[0].get("created_at") or "")[:10], audiences=("cro", "analyst"), kind="ews_proposals",
            numbers=[num("Proposals", len(rows))],
            trace=[{"domain": "agents", "relation": "approvals (ews.triage)", "keys": {"kind": kind}, "period": "",
                    "status": "agent_store"}],
            show_me={"href": "/agent-operations?tab=queue", "label": "Show the triage proposals"},
            open={"href": "/early-warning?domain=corporate", "label": "Open Early Warning"},
            entity={"kind": "ews_proposals", "id": kind},
        ))
    # New Stage 2 / 3 this period, from the classification domain.
    cls = R.read("classification", "cls_exposure",
                 columns="period, count(*) AS n, count(DISTINCT obligor_id) AS names, sum(CASE WHEN stage = 3 THEN 1 ELSE 0 END) AS s3",
                 where="book = 'corporate' AND stage > previous_stage AND period = (SELECT max(period) FROM "
                       + _src("classification", "cls_exposure") + ")", group="period")
    if cls.status == "ok" and cls.rows and int(cls.rows[0].get("n") or 0):
        c = cls.rows[0]
        n, names, s3 = int(c["n"]), int(c.get("names") or 0), int(c.get("s3") or 0)
        out.append(Item(
            id=f"ews:migrations:{c['period']}", source="ews_triage", source_label="Early Warning", module="ews",
            title=f"{n:,} corporate exposures ({names:,} names) moved to a worse stage in {c['period']}, {s3:,} of them into Stage 3",
            severity="high" if s3 else "medium", materiality_sar_mn=None, since=str(c["period"]),
            audiences=("cro", "analyst", "reviewer"), kind="migrations",
            numbers=[num("Exposures", n), num("Names", names), num("Into Stage 3", s3)],
            trace=[cls.stamp({"book": "corporate", "stage": "> previous_stage"}, str(c["period"]))],
            show_me={"href": "/early-warning?domain=corporate", "label": "Show the warned names"},
            open={"href": _issue_href(f"ews:migrations:{c['period']}"), "label": "Open the issue"},
            entity={"kind": "migrations", "id": str(c["period"])},
        ))
    status["rows"] = len(out)
    return out, status


def _issue_href(issue_id: str) -> str:
    """R14 r (K2): brief lines open the issue view in the owning module, never the Data Domains catalogue."""
    from backend.regulatory.issues.common import issue_href
    return issue_href(issue_id)


def _issue_line(check_id: str) -> str | None:
    """R14 r (K4 (1)): the bank-vs-requirement sentence of a check (both rates), from the issue engine."""
    try:
        from backend.regulatory.issues.service import brief_line
        return brief_line(check_id)
    except Exception:  # noqa: BLE001 - the brief never fails on a view
        return None


def _src(domain: str, relation: str) -> str:
    try:
        from backend.data_builder import store
        return store.source(domain, relation)
    except Exception:  # noqa: BLE001
        return "(SELECT NULL AS period)"


# ------------------------------------------------------------------ Lenses monitoring alerts

def lenses_alert(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    try:
        from backend.agents_v5.lenses import mstore
        rows = mstore.get().alerts(limit=30)
    except Exception as e:  # noqa: BLE001
        return [], {"status": "unavailable", "note": str(e)[:200]}
    out = []
    seen: set[str] = set()
    for a in rows:
        if str(a.get("status") or "") in ("closed", "dismissed", "ok") or a.get("metric_key") in seen:
            continue
        seen.add(str(a.get("metric_key")))
        sev = str(a.get("severity") or "medium").lower()
        out.append(Item(
            id=f"lenses:{a['alert_id']}", source="lenses_alert", source_label="Lenses monitoring", module="lenses",
            title=str(a.get("headline") or f"{a.get('label')}: {a.get('display')}"),
            detail=" ".join((a.get("explanation") or [])[:2]), severity=sev if sev in ("critical", "high", "medium", "low") else "medium",
            since=str(a.get("period") or ""), audiences=("cro", "analyst"), kind="lens_alert",
            numbers=[num(str(a.get("label") or "Value"), _f(a.get("value")), "", str(a.get("display") or ""))],
            trace=[{"domain": "agents", "relation": "lenses monitoring alerts", "keys": {"alert_id": a["alert_id"]},
                    "period": str(a.get("period") or ""), "status": "agent_store"}],
            show_me={"href": "/lenses?monitor=alerts", "label": "Show the alert in Lenses"},
            open={"href": "/lenses?monitor=alerts", "label": "Open"},
            entity={"kind": "lens_alert", "id": a["alert_id"], "metric": a.get("metric_key")},
        ))
        if len(out) >= 3:
            break
    return out, {"status": "ok", "rows": len(out)}


# ------------------------------------------------------------------ Deal Desk queues

def _days(since: str, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(since)[:10])).days
    except ValueError:
        return None


def _deals(ctx: dict[str, Any]) -> tuple[R.Read, list[dict[str, Any]]]:
    """Every deal Deal Desk can open with its workflow state: `dd_deal` (E's register, workflow_state from
    dd_workflow_event), else `dd_proposal` with its status. An RM sees their own deals; a demo account viewing as RM
    sees the desk."""
    reg = R.read("deal_desk", "dd_deal", columns="proposal_id, source, obligor_name, deal_name, status, workflow_state, "
                                                  "rm, credit_analyst, received_date, committee_date, proposed_limits_mn")
    if reg.status == "ok" and reg.rows:
        rows = [{**r, "state": str(r.get("workflow_state") or r.get("status") or "").lower(),
                 "amount": _f(r.get("proposed_limits_mn"))} for r in reg.rows]
    else:
        reg = R.read("deal_desk", "dd_proposal", columns="proposal_id, obligor_name, sector, status, rm, amount_sar_mn, received_date")
        st = {"new": "submitted", "counter_offered": "recommended"}
        rows = [{**r, "state": st.get(str(r.get("status")), str(r.get("status") or "")), "amount": _f(r.get("amount_sar_mn"))}
                for r in reg.rows]
    mine = my_deals(ctx, rows)
    if mine is not None:
        rows = [r for r in rows if r["proposal_id"] in mine]
    return reg, rows


def my_deals(ctx: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> set[str] | None:
    """The deals that are the reader's own: an RM's (dd_deal.rm) or an analyst's (dd_deal.credit_analyst). None when the
    persona works across the desk, or the reader has no deals of their own (a demo account viewing as that role)."""
    col = {"rm": "rm", "analyst": "credit_analyst"}.get(str(ctx.get("persona")))
    me = str((ctx.get("user") or {}).get("name") or "").lower()
    if not col or not me:
        return None
    if rows is None:
        rows = R.read("deal_desk", "dd_deal", columns="proposal_id, rm, credit_analyst").rows
    mine = {str(r["proposal_id"]) for r in rows if str(r.get(col) or "").lower() == me}
    return mine or None


def dd_queue(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    today = _today(ctx)
    reg, rows = _deals(ctx)
    wf = R.read("deal_desk", "dd_workflow_event", columns="proposal_id, to_state, actor, at", order="at")
    last_move = {str(e["proposal_id"]): e for e in wf.rows}  # ordered by time: the last wins
    groups = {
        "to_review": ("submitted",),
        "in_review": ("in_review", "queries"),
        "committee": ("recommended", "committee"),
    }
    out: list[Item] = []
    for g, states in groups.items():
        deals = sorted((r for r in rows if r["state"] in states), key=lambda r: (str(r.get("received_date") or ""), r["proposal_id"]))
        if not deals:
            continue
        ids = [d["proposal_id"] for d in deals]
        amount = sum(d["amount"] or 0.0 for d in deals)
        since = [str((last_move.get(pid) or {}).get("at") or d.get("received_date") or "")[:10] for pid, d in zip(ids, deals)]
        oldest = min((x for x in since if x), default="")
        age = _days(oldest, today) if oldest else None
        lead = deals[0]
        if g == "to_review":
            title = (f"{len(ids)} deal{'s' if len(ids) != 1 else ''} waiting for credit review, {fmt(amount, 'SAR mn')} asked"
                     + (f"; the oldest has waited {age} days" if age is not None and age >= 0 else ""))
            aud, sev, href = ("reviewer", "cro", "analyst"), ("high" if (age or 0) > 7 else "medium"), "/deal-desk?status=new&card=new"
        elif g == "in_review":
            q = sum(1 for d in deals if d["state"] == "queries")
            title = (f"{len(ids)} deal{'s' if len(ids) != 1 else ''} in review, {fmt(amount, 'SAR mn')}"
                     + (f"; {q} waiting on answers from the relationship managers" if q else ""))
            aud, sev, href = ("reviewer", "rm", "analyst"), "medium", "/deal-desk?status=in_review&card=in_review"
        else:
            title = (f"{len(ids)} deal{'s' if len(ids) != 1 else ''} ready for a committee decision, {fmt(amount, 'SAR mn')}"
                     f" (first: {lead.get('obligor_name') or lead['proposal_id']})")
            aud, sev, href = ("cro", "reviewer", "rm"), "high", "/deal-desk?card=committee"
        out.append(Item(
            id=f"dd:{g}", source="dd_queue", source_label="Deal Desk", module="dealdesk", title=title,
            detail=", ".join(f"{d['proposal_id']} {d.get('obligor_name') or ''}".strip() for d in deals[:4]),
            severity=sev, materiality_sar_mn=amount, since=oldest or None, audiences=aud, kind="deal_queue",
            numbers=[num("Deals", len(ids), source=src("deal_desk", reg.relation, {"proposal_id": ids})),
                     num("Asked", amount, "SAR mn", source=src("deal_desk", reg.relation, {"proposal_id": ids},
                                                                 "proposed_limits_mn" if reg.relation == "dd_deal" else "amount_sar_mn"))]
                    + ([num("Oldest, days", age, source=src("deal_desk", reg.relation, {"proposal_id": ids}, "received_date"))]
                       if age is not None else []),
            trace=[reg.stamp({"workflow_state": list(states)}, ""), wf.stamp({"proposal_id": ids[:6]}, "")],
            show_me={"href": href, "label": "Show these deals"},
            open={"href": f"/deal-desk/{lead['proposal_id']}", "label": f"Open {lead['proposal_id']}"},
            entity={"kind": "deal_queue", "id": g, "deals": ids,
                    "rms": sorted({str(d.get('rm') or '') for d in deals if d.get('rm')})},
        ))
    # Committee in the next 30 days (dd_deal.committee_date): what the CRO and the reviewers must have ready.
    horizon = (today + timedelta(days=30)).isoformat()
    soon = sorted((r for r in rows if str(r.get("committee_date") or "") and today.isoformat() <= str(r["committee_date"]) <= horizon
                   and r["state"] not in ("approved", "declined")), key=lambda r: str(r["committee_date"]))
    if soon:
        first = soon[0]
        open_q = [r for r in soon if r["state"] == "queries"]
        amount = sum(r["amount"] or 0.0 for r in soon)
        out.append(Item(
            id="dd:committee_dates", source="dd_queue", source_label="Deal Desk committee calendar", module="dealdesk",
            title=(f"{len(soon)} deal{'s go' if len(soon) != 1 else ' goes'} to committee in the next 30 days, {fmt(amount, 'SAR mn')}; "
                   f"first {first.get('obligor_name') or first['proposal_id']} on {fdate(first['committee_date'])}"
                   + (f", {len(open_q)} still with open queries" if open_q else "")),
            detail=", ".join(f"{r['proposal_id']} on {fdate(r['committee_date'])}" for r in soon[:4]),
            severity="high" if open_q else "medium", materiality_sar_mn=amount, due=str(first["committee_date"]),
            audiences=("cro", "reviewer", "rm"), kind="deal_queue",
            numbers=[num("Deals", len(soon), source=src("deal_desk", reg.relation, {"proposal_id": [r["proposal_id"] for r in soon]},
                                                          "committee_date")),
                     num("Limits asked", amount, "SAR mn", source=src("deal_desk", reg.relation,
                         {"proposal_id": [r["proposal_id"] for r in soon]}, "proposed_limits_mn")),
                     num("With open queries", len(open_q), source=src("deal_desk", reg.relation,
                         {"proposal_id": [r["proposal_id"] for r in soon]}, "workflow_state"))],
            trace=[reg.stamp({"committee_date": f"<= {horizon}"}, "")],
            show_me={"href": "/deal-desk?card=committee", "label": "Show the committee deals"},
            open={"href": f"/deal-desk/{first['proposal_id']}", "label": f"Open {first['proposal_id']}"},
            entity={"kind": "deal_queue", "id": "committee_dates", "deals": [r["proposal_id"] for r in soon]},
        ))
    return out, {"status": "ok", "rows": len(out), "register": reg.relation, "workflow": wf.status}


def dd_query(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    q = R.read("deal_desk", "dd_query", order="query_id, seq")
    if q.status != "ok":
        return [], {"status": q.status, "note": q.note}
    last: dict[str, dict[str, Any]] = {}
    for r in q.rows:
        last[str(r.get("query_id"))] = r  # ordered by seq: the last message of each thread wins
    today = _today(ctx)
    to_rm = [r for r in last.values() if str(r.get("status") or "") == "open" and str(r.get("direction")) == "to_rm"]
    to_cr = [r for r in last.values() if str(r.get("status") or "") in ("open", "answered") and str(r.get("direction")) == "from_rm"]
    persona = ctx.get("persona")
    waiting = to_rm if persona in ("rm", None) or not to_cr else (to_cr if persona == "reviewer" else to_rm + to_cr)
    if persona == "rm":
        waiting = to_rm
    who = "relationship managers" if waiting is to_rm else "credit"
    mine = my_deals(ctx)
    if mine is not None:
        waiting = [r for r in waiting if str(r.get("proposal_id")) in mine]
    if not waiting:
        return [], {"status": "ok", "rows": 0}
    deals = sorted({str(r.get("proposal_id") or "") for r in waiting} - {""})
    ages = [d for d in (_days(str(r.get("sent_at") or ""), today) for r in waiting) if d is not None]
    old = max(ages) if ages else None
    first = sorted(waiting, key=lambda r: str(r.get("sent_at") or ""))[0]
    return [Item(
        id="dd:queries", source="dd_query", source_label="Deal Desk queries", module="dealdesk",
        title=((f"{len(waiting)} credit quer{'ies' if len(waiting) != 1 else 'y'} waiting for the relationship managers"
                if who != "credit" else f"{len(waiting)} RM repl{'ies' if len(waiting) != 1 else 'y'} waiting for credit review")
               + f" on {len(deals)} deal{'s' if len(deals) != 1 else ''}" + (f"; the oldest sent {old} days ago" if old else "")),
        detail=f"{first.get('proposal_id')}: {first.get('subject')}. {str(first.get('body') or '')[:140]}",
        severity="high" if (old or 0) > 7 else "medium", audiences=("rm", "reviewer"), kind="queries",
        numbers=[num("Open queries", len(waiting)), num("Deals", len(deals))] + ([num("Oldest, days", old)] if old else []),
        trace=[q.stamp({"query_id": sorted(last)[:6], "status": "open"}, "")],
        show_me={"href": "/deal-desk?status=in_review&card=in_review", "label": "Show the open queries"},
        open={"href": f"/deal-desk/{deals[0]}", "label": f"Open {deals[0]}"},
        entity={"kind": "queries", "id": "open", "deals": deals},
    )], {"status": "ok", "rows": 1}


# ------------------------------------------------------------------ tier-High movers, conditions, renewals

def tier_high(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    mp = R.read("deal_desk", "dd_monitoring_plan")
    if mp.status != "ok":
        return [], {"status": mp.status, "note": mp.note}
    high = [r for r in mp.rows if str(r.get("tier") or "").lower() == "high"]
    if not high:
        return [], {"status": "ok", "rows": 0}
    ids = sorted({str(r.get("obligor_id") or r.get("borrower_id") or "") for r in high} - {""})
    moved: list[dict[str, Any]] = []
    ews = None
    if ids:
        ph = ", ".join("?" for _ in ids)
        ews = R.read("ews", "corp_exposure",
                     columns="borrower_id, any_value(borrower_name) AS name, max(reporting_quarter) AS q, "
                             "sum(ead_sar_mn) AS ead, max(rating_notches_moved) AS notches, max(dpd_days) AS dpd, "
                             "max(covenant_breaches) AS cov, max(watchlist_flag) AS watch",
                     where=f"borrower_id IN ({ph}) AND reporting_quarter = (SELECT max(reporting_quarter) FROM "
                           f"{_src('ews', 'corp_exposure')})", group="borrower_id", args=ids)
        moved = [r for r in ews.rows if (_f(r.get("notches")) or 0) > 0 or (_f(r.get("dpd")) or 0) > 0
                 or (_f(r.get("cov")) or 0) > 0]
    plan = {str(r.get("obligor_id") or r.get("borrower_id")): r for r in high}
    out = []
    for m in sorted(moved, key=lambda r: -(_f(r.get("ead")) or 0))[:3]:
        p = plan.get(str(m["borrower_id"]), {})
        why = []
        if (_f(m.get("notches")) or 0) > 0:
            why.append(f"down {int(_f(m['notches']) or 0)} notch{'es' if (_f(m['notches']) or 0) > 1 else ''}")
        if (_f(m.get("dpd")) or 0) > 0:
            why.append(f"{int(_f(m['dpd']) or 0)} days past due")
        if (_f(m.get("cov")) or 0) > 0:
            why.append("a covenant breached")
        name = m.get("name") or p.get("obligor_name") or m["borrower_id"]
        out.append(Item(
            id=f"tier:{m['borrower_id']}", source="tier_high", source_label="Monitoring tier High", module="ews",
            title=f"{name}, on monitoring tier High, moved: {', '.join(why)} ({fmt(_f(m.get('ead')), 'SAR mn')} EAD)",
            detail=f"Tier set by Deal Desk on {p.get('set_on') or p.get('set_at') or '–'} because {p.get('reason') or p.get('drivers') or 'the stress verdict'}.",
            severity="high", materiality_sar_mn=_f(m.get("ead")), since=str(m.get("q") or ""),
            audiences=("cro", "reviewer", "rm"), kind="tier_high",
            numbers=[num("EAD", _f(m.get("ead")), "SAR mn"), num("Notches moved", _f(m.get("notches"))),
                     num("Days past due", _f(m.get("dpd")))],
            trace=[mp.stamp({"obligor_id": m["borrower_id"], "tier": "High"}, ""),
                   (ews.stamp({"borrower_id": m["borrower_id"]}, str(m.get("q") or "")) if ews else {})],
            show_me=_open(f"/early-warning?domain=corporate&customer={m['borrower_id']}", "Show the customer in Early Warning",
                          f"/deal-desk/customer-packs?cif={m['borrower_id']}", "Show the customer file"),
            open=_open(f"/early-warning?domain=corporate&customer={m['borrower_id']}", "Open",
                       f"/deal-desk/customer-packs?cif={m['borrower_id']}", "Open"),
            entity={"kind": "borrower", "id": m["borrower_id"], "name": name},
        ))
    return out, {"status": "ok", "rows": len(out)}


def condition_due(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    today = _today(ctx)
    horizon = (today + timedelta(days=30)).isoformat()
    out: list[Item] = []
    c = R.read("deal_desk", "dd_condition")
    if c.status == "ok" and c.rows:
        due_col = next((k for k in ("due", "due_date") if k in c.rows[0]), None)
        if due_col:
            bad = ("not_complied", "breached")
            mine = my_deals(ctx)
            rows_c = [r for r in c.rows if mine is None or str(r.get("proposal_id")) in mine]
            live = [r for r in rows_c if str(r.get("status") or "open").lower() not in ("met", "closed", "waived", "satisfied")
                    and (str(r.get(due_col) or "9999") <= horizon or str(r.get("status")).lower() in bad)]
            overdue = [r for r in live if str(r.get(due_col) or "9999") < today.isoformat() or str(r.get("status")).lower() in bad]
            if live:
                deals = sorted({str(r.get("deal_id") or r.get("proposal_id") or "") for r in live} - {""})
                out.append(Item(
                    id="dd:conditions", source="condition_due", source_label="Conditions and covenants", module="dealdesk",
                    title=(f"{len(live)} approval condition{'s' if len(live) != 1 else ''} open or due in the next 30 days"
                           + (f", {len(overdue)} overdue or not complied with" if overdue else "")
                           + f" across {len(deals)} deal{'s' if len(deals) != 1 else ''}"),
                    detail="; ".join(str(r.get("what") or r.get("text") or r.get("condition") or "")[:80] for r in (overdue or live)[:2]),
                    severity="high" if overdue else "medium", due=min((str(r.get(due_col)) for r in live if r.get(due_col)), default=None),
                    audiences=("rm", "reviewer", "analyst", "cro"), kind="conditions",
                    numbers=[num("Due in 30 days", len(live)), num("Overdue", len(overdue))],
                    trace=[c.stamp({due_col: f"<= {horizon}"}, "")],
                    show_me={"href": "/deal-desk?card=conditions", "label": "Show the conditions due"},
                    open={"href": "/deal-desk?card=conditions", "label": "Open"},
                    entity={"kind": "conditions", "id": "due", "deals": deals},
                ))
    w = R.read("watch", "watch_item", where="due_date <= ? AND status <> 'met'", args=[horizon], order="due_date")
    if w.status == "ok" and w.rows:
        crit = [r for r in w.rows if r.get("critical")]
        missed = [r for r in w.rows if str(r.get("status") or "").lower() in ("missed", "breached", "off track")]
        out.append(Item(
            id="watch:due", source="condition_due", source_label="Accepted-risk watch", module="watch",
            title=(f"{len(w.rows)} accepted-risk trigger{'s' if len(w.rows) != 1 else ''} fall due by {fdate(horizon)}"
                   + (f"; {len(missed)} off track" if missed else "") + (f"; {len(crit)} critical" if crit else "")),
            detail=f"First: {w.rows[0].get('trigger')} ({w.rows[0].get('obligor_id')}, due {fdate(w.rows[0].get('due_date'))}).",
            severity="high" if missed or crit else "low", due=str(w.rows[0].get("due_date")),
            audiences=("analyst", "cro", "reviewer"), kind="watch_due",
            numbers=[num("Triggers due", len(w.rows)), num("Off track", len(missed))],
            trace=[w.stamp({"due_date": f"<= {horizon}"}, str(w.rows[0].get("period") or ""))],
            show_me=_open("/accepted-risk", "Show the triggers due", "/deal-desk/review?view=conditions", "Show the conditions due"),
            open=_open("/accepted-risk", "Open", "/deal-desk/review?view=conditions", "Open"),
            entity={"kind": "watch", "id": "due"},
        ))
    return out, {"status": "ok", "rows": len(out), "dd_condition": c.status}


def renewal(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    d = R.read("deal_desk", "dd_raroc_drift")
    if d.status != "ok":
        return [], {"status": d.status, "note": d.note}
    if not d.rows:
        return [], {"status": "ok", "rows": 0}
    today = _today(ctx)
    k = d.rows[0]
    now_col = next((c for c in ("raroc_now_pct", "raroc_now", "current_raroc_pct") if c in k), None)
    hur_col = next((c for c in ("hurdle_pct", "hurdle") if c in k), None)
    ren_col = next((c for c in ("renewal_date", "next_review", "maturity_date") if c in k), None)
    if not (now_col and hur_col):
        return [], {"status": "ok", "rows": 0, "note": "dd_raroc_drift has no RAROC or hurdle column yet"}
    lo, hi = today.isoformat(), (today + timedelta(days=183)).isoformat()  # due now to six months out
    mine = my_deals(ctx)
    below = [r for r in d.rows if (mine is None or str(r.get("proposal_id")) in mine)
             and (_f(r.get(now_col)) or 0) < (_f(r.get(hur_col)) or 0)
             and (not ren_col or lo <= str(r.get(ren_col) or "") <= hi)]
    if not below:
        return [], {"status": "ok", "rows": 0}
    gap = sum((_f(r.get(hur_col)) or 0) - (_f(r.get(now_col)) or 0) for r in below) / len(below)
    ead = sum(_f(r.get("ead_sar_mn")) or 0.0 for r in below)
    return [Item(
        id="book:repricing", source="renewal", source_label="Book: renewals and repricing", module="dealdesk",
        title=(f"{len(below)} facilit{'ies' if len(below) != 1 else 'y'} up for renewal within six months "
               f"below hurdle, on average {gap:.1f}pp short" + (f", {fmt(ead, 'SAR mn')} EAD" if ead else "")
               + (f"; first on {fdate(min(str(r.get(ren_col)) for r in below))}" if ren_col else "")),
        detail="; ".join(f"{r.get('facility_id')}: {(_f(r.get(now_col)) or 0):.1f}% against {(_f(r.get(hur_col)) or 0):.1f}%"
                         for r in below[:3]),
        severity="high" if ren_col and min(str(r.get(ren_col)) for r in below) <= (today + timedelta(days=90)).isoformat() else "medium",
        materiality_sar_mn=ead or None, due=min((str(r.get(ren_col)) for r in below), default=None) if ren_col else None,
        audiences=("rm", "cro", "reviewer"), kind="repricing",
        numbers=[num("Facilities", len(below)), num("Average gap to hurdle", gap, "pp"), num("EAD", ead, "SAR mn")],
        trace=[d.stamp({"below_hurdle": True, "renewal": f"{lo}..{hi}"}, "")],
        show_me={"href": "/deal-desk?tab=book&filter=repricing", "label": "Show the repricing list"},
        open={"href": f"/deal-desk/{below[0].get('proposal_id')}" if below[0].get("proposal_id") else "/deal-desk?tab=book", "label": "Open"},
        entity={"kind": "repricing", "id": "0-6m", "deals": sorted({str(r.get('proposal_id')) for r in below if r.get('proposal_id')})},
    )], {"status": "ok", "rows": 1}


# ------------------------------------------------------------------ approvals, deadlines, large exposures

def approval(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    try:
        from backend.agents_v5.runtime import approvals
        rows = approvals.listing(status="pending")
    except Exception as e:  # noqa: BLE001
        return [], {"status": "unavailable", "note": str(e)[:200]}
    persona = ctx.get("persona") or "analyst"
    role = {"cro": "CCO", "reviewer": "CREDIT_OFFICER", "rm": "RM", "analyst": "ANALYST"}[persona]
    try:
        mine = [r for r in rows if approvals.may_decide(role, r) and r.get("agent") != "ews.triage"]
    except Exception:  # noqa: BLE001
        mine = []
    if not mine:
        return [], {"status": "ok", "rows": 0}
    first = mine[0]
    return [Item(
        id="approvals:pending", source="approval", source_label="Approvals", module="agents",
        title=f"{len(mine)} approval{'s' if len(mine) != 1 else ''} waiting for you; first: {first.get('title')}",
        detail=str(first.get("reason") or "")[:200], severity="high" if len(mine) > 3 else "medium",
        since=str(first.get("created_at") or "")[:10], due=str(first.get("expires_at") or "")[:10] or None,
        audiences=("cro", "reviewer", "analyst", "rm"), kind="approvals",
        numbers=[num("Waiting", len(mine))],
        trace=[{"domain": "agents", "relation": "approvals", "keys": {"status": "pending", "approver_role": role},
                "period": "", "status": "agent_store"}],
        show_me={"href": "/agent-operations?tab=queue", "label": "Show the approvals"},
        open={"href": "/agent-operations?tab=queue", "label": "Open"},
        entity={"kind": "approvals", "id": "pending", "ids": [r["id"] for r in mine[:10]]},
    )], {"status": "ok", "rows": 1}


def deadline(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    out: list[Item] = []
    q = R.read("queries", "query_case")
    if q.status == "ok" and q.rows:
        aud = [r for r in q.rows if str(r.get("sender") or "").lower() in ("auditor", "external auditor", "internal audit")]
        reg = [r for r in q.rows if r not in aud]
        n_q = sum(int(r.get("questions") or 0) for r in q.rows)
        out.append(Item(
            id="queries:letters", source="deadline", source_label="Auditor and regulator letters", module="queries",
            title=(f"{len(q.rows)} auditor and regulator letters open with {n_q} questions"
                   f" ({len(aud)} from the auditor, {len(reg)} from regulators)"),
            detail=f"First: {q.rows[0].get('title')} ({q.rows[0].get('sender')}, {q.rows[0].get('article')}).",
            severity="medium", since=str(q.rows[0].get("period") or ""), audiences=("cro", "analyst"), kind="letters",
            numbers=[num("Letters", len(q.rows)), num("Questions", n_q)],
            trace=[q.stamp({}, str(q.rows[0].get("period") or ""))],
            show_me={"href": "/?focus=ask&letters=1", "label": "Show the letters on the Cockpit"},
            open={"href": "/?focus=ask&letters=1", "label": "Open"},
            entity={"kind": "letters", "id": "open", "cases": [r.get("case_id") for r in q.rows]},
        ))
    a = R.read("ecl_runs", "ecl_anomaly", where="rerun_required = 1")
    if a.status == "ok" and a.rows:
        run = str(a.rows[0].get("run_id") or "")
        out.append(Item(
            id=f"ecl:anomalies:{run}", source="deadline", source_label="ECL run data checks", module="ecl",
            title=f"{len(a.rows)} data issue{'s' if len(a.rows) != 1 else ''} to clear before the {run} ECL run; first: {a.rows[0].get('kind')}",
            detail=str(a.rows[0].get("note") or ""), severity="high", due=str(a.rows[0].get("as_of_date") or "") or None,
            since=run, audiences=("analyst", "cro"), kind="ecl_anomaly",
            numbers=[num("Issues needing a re-run", len(a.rows))],
            trace=[a.stamp({"rerun_required": 1}, run)],
            show_me={"href": _issue_href(f"ecl:anomalies:{run}"), "label": "Show the data issues"},
            open={"href": _issue_href(f"ecl:anomalies:{run}"), "label": "Open the issue"},
            entity={"kind": "ecl_anomaly", "id": run},
        ))
    return out, {"status": "ok", "rows": len(out)}


def large_exposure(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    r = R.read("collateral", "col_large_exposure", where="pct_of_capital >= 0.8 * limit_pct",
               order="pct_of_capital DESC", limit=5)
    if r.status != "ok":
        return [], {"status": r.status, "note": r.note}
    if not r.rows:
        return [], {"status": "ok", "rows": 0}
    top = r.rows[0]
    breach = [x for x in r.rows if x.get("breach")]
    return [Item(
        id="le:near", source="large_exposure", source_label="Large exposures", module="regulatory",
        title=(f"{len(r.rows)} connected group{'s' if len(r.rows) != 1 else ''} above 80% of the large-exposure limit; "
               f"{top.get('group_name')} at {_f(top.get('pct_of_capital')) or 0:.1f}% of Tier 1 against {_f(top.get('limit_pct')) or 0:.0f}%"),
        severity="critical" if breach else "high", materiality_sar_mn=_f(top.get("ead_sar_mn")),
        since=str(top.get("as_of_date") or ""), audiences=("cro", "reviewer"), kind="large_exposure",
        numbers=[num("Groups", len(r.rows)), num("Largest, % of Tier 1", _f(top.get("pct_of_capital")), "%"),
                 num("EAD", _f(top.get("ead_sar_mn")), "SAR mn")],
        trace=[r.stamp({"pct_of_capital": ">= 80% of limit"}, str(top.get("as_of_date") or ""))],
        show_me={"href": f"/borrower-360?q={quote(str(top.get('group_id') or ''))}", "label": "Show the group"},
        open={"href": _issue_href("le:near"), "label": "Open the issue"},
        entity={"kind": "group", "id": top.get("group_id"), "name": top.get("group_name")},
    )], {"status": "ok", "rows": 1}


# ------------------------------------------------------------------ R16 M8 (session s): scorecard monitoring alerts

def scorecard_monitoring(ctx: dict[str, Any]) -> tuple[list[Item], dict[str, Any]]:
    """Red breaches of the MMSG monitoring criteria on Tier 1 scorecards (backend/scorecard_v5/monitoring/front.py)."""
    try:
        from backend.scorecard_v5.monitoring import front
        from backend.scorecard_v5.store import Store
        from backend.scorecard_v5 import paths as sc_paths
        rows = front.brief_items(_today(ctx), Store(sc_paths.store_path()), limit=2)
    except Exception as e:  # noqa: BLE001
        return [], {"status": "unavailable", "note": str(e)[:200]}
    out = []
    for r in rows:
        t0 = (r.get("trace") or [{}])[0]
        source = src(t0.get("domain", "scorecard_monitoring"), t0.get("relation", "sc_monitor_metric"), t0.get("keys") or {}, t0.get("column", "value"),
                     t0.get("period", "")) if t0.get("relation", "").startswith("sc_") else None
        out.append(Item(
            id=r["id"], source="scorecard_monitoring", source_label="Scorecard monitoring", module="scorecard",
            title=r["title"], detail=r["detail"], severity=r["severity"], since=r.get("since") or None, owner=r.get("owner"),
            audiences=("cro", "analyst", "reviewer"), kind="model_breach",
            numbers=[num(r["label"], r.get("value"), "", r.get("display", ""), source=source)] if source else [],
            trace=[{"domain": t.get("domain"), "relation": t.get("relation"), "keys": t.get("keys") or {}, "period": t.get("period", ""),
                    "status": t.get("status", "published")} for t in r.get("trace") or []],
            show_me={"href": r["href"], "label": "Show the breach in Scorecard Validation"},
            open={"href": r["href"], "label": "Open"},
            entity={"kind": "scorecard", "id": r["scorecard_id"], "criterion": r["criterion"]},
        ))
    return out, {"status": "ok", "rows": len(out)}


COLLECTORS: dict[str, Callable[[dict[str, Any]], tuple[list[Item], dict[str, Any]]]] = {
    "cockpit_attention": cockpit_attention,
    "sector_appetite": sector_appetite,
    "regulatory_breach": regulatory_breach,
    "ews_triage": ews_triage,
    "lenses_alert": lenses_alert,
    "dd_queue": dd_queue,
    "dd_query": dd_query,
    "tier_high": tier_high,
    "condition_due": condition_due,
    "renewal": renewal,
    "approval": approval,
    "deadline": deadline,
    "large_exposure": large_exposure,
    "scorecard_monitoring": scorecard_monitoring,
    # Round G: cross-deal counterparty signals from the Deal Desk graph (backend/dealdesk/graph/brief.py)
    "counterparty_exposure": __import__("backend.dealdesk.graph.brief", fromlist=["collect"]).collect,
}


def collect(ctx: dict[str, Any], only: tuple[str, ...] | None = None) -> tuple[list[Item], dict[str, dict[str, Any]]]:
    items: list[Item] = []
    status: dict[str, dict[str, Any]] = {}
    for name, fn in COLLECTORS.items():
        if only and name not in only:
            continue
        try:
            got, st = fn(ctx)
        except Exception as e:  # noqa: BLE001 - one source never takes the brief down
            logger.exception("brief source %s failed", name)
            got, st = [], {"status": "error", "note": f"{type(e).__name__}: {str(e)[:160]}"}
        items.extend(got)
        status[name] = st
    return items, status
