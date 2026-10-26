"""Why? and What should we do? for one brief line (I12 steps 2–6), deterministic (N6).

`why(item)` returns the trace steps the panel plays out live (each with its counter: facilities read, limits checked,
breaches found), a one-line answer and one Plotly figure, every number stamped with its relation.

`options(item)` returns three options with numbers from the engines: for a sector or a deal they are the Deal Desk
engine's priced results (`dd_result`: `engine.analyse` on the ask and the optimiser's recommended structure), summed
over the deals concerned, with the sector share after each option from `dd_portfolio_snapshot`.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt, num, src
from backend.agents_v5.brief.sources import ACTIVE_DEAL, _f, _src

#: Plotly theme hooks the panel maps to the shared CreditProbe theme (N2's plotly-theme.ts when it lands).
SERIES = {"primary": "var(--ipm-accent)", "warn": "var(--ipm-warning)", "limit": "var(--ipm-negative)",
          "muted": "var(--ipm-text-muted)"}


from backend.v5common import edition as _edition  # noqa: E402

#: Deal Desk edition wording: the risk flag on a facility, not the name of a module that is not in the product.
_BAND = "risk flag" if _edition.is_dealdesk() else "Early Warning band"
_ON = "on the risk flags" if _edition.is_dealdesk() else "on Early Warning"



class Step:
    def __init__(self, steps: list[dict[str, Any]], label: str):
        self.steps, self.label, self.t0 = steps, label, time.monotonic()

    def done(self, count: int | float | None, unit: str, source: dict[str, Any] | None = None, note: str = "") -> None:
        self.steps.append({"label": self.label, "count": count, "unit": unit, "note": note,
                           "ms": int((time.monotonic() - self.t0) * 1000), "source": source or {}})


# ------------------------------------------------------------------ Why?

def why(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get("kind")
    if kind == "sector_appetite" or (item.get("entity") or {}).get("kind") == "sector":
        return _why_sector(item)
    if kind == "deal_queue":
        return _why_deals(item)
    if kind == "breach":
        return _why_breach(item)
    return _why_generic(item)


def _label(t: dict[str, Any]) -> str:
    """A relation in banker words: its Data Domains label, or the agent record it came from."""
    spec = R.registered(str(t.get("domain") or ""), str(t.get("relation") or ""))
    if spec:
        return str(spec.get("label") or t.get("relation"))
    rel = str(t.get("relation") or "")
    return {"approvals (ews.triage)": "Early Warning triage proposals", "approvals": "approvals waiting",
            "lenses monitoring alerts": "Lenses monitoring alerts", "attention feed": "Cockpit attention cards"}.get(rel, rel)


def _count(t: dict[str, Any]) -> int | None:
    """Rows behind a trace stamp whose keys are plain column filters; None when it is not a Data Domains relation."""
    if t.get("status") != "ok" or not R.registered(str(t.get("domain")), str(t.get("relation"))):
        return None
    keys = {k: v for k, v in (t.get("keys") or {}).items()}
    preds, args = [], []
    for k, v in keys.items():
        if not isinstance(k, str) or not k.replace("_", "").isalnum():
            return None
        if isinstance(v, (list, tuple)):
            if not v:
                continue
            preds.append(f'"{k}" IN ({", ".join("?" for _ in v)})')
            args.extend(v)
        elif isinstance(v, (str, int, float)) and not (isinstance(v, str) and v[:1] in "<>="):
            preds.append(f'"{k}" = ?')
            args.append(v)
        else:
            return None
    r = R.read(str(t["domain"]), str(t["relation"]), columns="count(*) AS n", where=" AND ".join(preds), args=args)
    return int(r.rows[0]["n"]) if r.status == "ok" and r.rows else None


def _why_breach(item: dict[str, Any]) -> dict[str, Any]:
    e = item.get("entity") or {}
    check = str(e.get("id") or "")
    steps: list[dict[str, Any]] = []
    s = Step(steps, "Read the regulatory checks on the corporate book")
    allr = R.read("regulatory", "crm_breach", columns="count(*) AS n, count(DISTINCT check_id) AS checks, max(period) AS p",
                  where="book = 'corporate'")
    a0 = allr.rows[0] if allr.rows else {}
    s.done(int(a0.get("checks") or 0), "checks read", allr.stamp({"book": "corporate"}, str(a0.get("p") or "")))
    s = Step(steps, f"Tested every exposure against {e.get('article') or check}")
    rows = R.read("regulatory", "crm_breach", columns="entity_id, owner_id, ead_sar_mn, shortfall_sar_mn, period",
                  where="book = 'corporate' AND check_id = ?", args=[check], order="shortfall_sar_mn DESC, ead_sar_mn DESC")
    s.done(len(rows.rows), "exposures in breach", rows.stamp({"check_id": check, "book": "corporate"}, ""))
    s = Step(steps, "Named the borrowers behind the largest")
    top = rows.rows[:10]
    owners = sorted({str(r["owner_id"]) for r in top})
    names: dict[str, str] = {}
    if owners:
        ph = ", ".join("?" for _ in owners)
        nm = R.read("ews", "corp_exposure", columns="borrower_id, any_value(borrower_name) AS name",
                    where=f"borrower_id IN ({ph})", args=owners, group="borrower_id")
        names = {str(r["borrower_id"]): str(r["name"]) for r in nm.rows}
    s.done(len(names), "borrowers named", {})
    by_sf = any((_f(r.get("shortfall_sar_mn")) or 0) > 0 for r in top)
    col = "shortfall_sar_mn" if by_sf else "ead_sar_mn"
    total = sum(_f(r.get(col)) or 0 for r in rows.rows)
    top_sum = sum(_f(r.get(col)) or 0 for r in top)
    lead = top[0] if top else {}
    what = "provision shortfall" if by_sf else "exposure"
    answer = (f"{len(rows.rows):,} exposures breach {e.get('article') or check} ({e.get('name')}); the 10 largest carry "
              f"{(100 * top_sum / total) if total else 0:.0f}% of the {fmt(total, 'SAR mn')} {what}, led by "
              f"{names.get(str(lead.get('owner_id')), lead.get('owner_id'))} ({fmt(_f(lead.get(col)), 'SAR mn')}).") if top else \
        f"No exposure breaches {check} now."
    labels = [f"{names.get(str(r['owner_id']), r['owner_id'])} · {r['entity_id']}" for r in top]
    figure = {"data": [{"type": "bar", "orientation": "h", "y": list(reversed(labels)),
                        "x": [round(_f(r.get(col)) or 0, 2) for r in reversed(top)],
                        "marker": {"color": SERIES["limit"] if by_sf else SERIES["primary"]},
                        "hovertemplate": "%{y}: SAR %{x:,.2f}m<extra></extra>"}],
              "layout": {"title": {"text": f"The 10 largest by {what}"}, "xaxis": {"title": {"text": "SAR m"}},
                         "yaxis": {"automargin": True, "tickfont": {"size": 10}},
                         "margin": {"l": 8, "r": 16, "t": 16, "b": 36}, "height": 320}} if top else None
    # R14 r (K4 (2)): Why runs the root-cause decomposition of the issue view: the rule as a comparison (bank vs
    # requirement, both rates) and the shortfall bridge; the full deep dive opens from "Show me" (the issue view).
    deep = _issue_why(f"crm:{check}")
    if deep and deep.get("comparison"):
        b = deep.get("bridge") or {}
        parts = [s for s in (b.get("steps") or []) if (s.get("value") or 0) > 0]
        parts.sort(key=lambda s: -(s.get("value") or 0))
        reasons = "; ".join(f"{s['label'][:1].lower()}{s['label'][1:]} {s['display']} ({s.get('share_pct') or 0:.0f}%)" for s in parts[:3])
        answer = deep["comparison"]["sentence"] + (f" Why: {reasons}." if reasons else "")
        s = Step(steps, "Laid the shortfall out by driver")
        s.done(len(parts), "drivers", {"domain": "regulatory", "relation": "crm_breach", "keys": {"check_id": check},
                                        "period": "", "status": "ok"})
        if parts:
            figure = {"data": [{"type": "waterfall", "orientation": "v", "measure": ["relative"] * len(parts) + ["total"],
                                "x": [_wrap(s["label"]) for s in parts] + ["Shortfall"],
                                "y": [round(s["value"], 2) for s in parts] + [round(b.get("total") or 0, 2)],
                                "connector": {"line": {"color": SERIES["muted"]}},
                                "increasing": {"marker": {"color": SERIES["limit"]}},
                                "totals": {"marker": {"color": SERIES["primary"]}},
                                "hovertemplate": "%{x}: SAR %{y:,.1f}m<extra></extra>"}],
                      "layout": {"title": {"text": b.get("title") or "Where the shortfall comes from"},
                                 "yaxis": {"title": {"text": "SAR m"}}, "xaxis": {"automargin": True, "tickangle": 0, "tickfont": {"size": 10}},
                                 "margin": {"l": 8, "r": 16, "t": 16, "b": 36}, "height": 320}}
    return {"item_id": item.get("id"), "answer": answer, "steps": steps, "figure": figure,
            "numbers": item.get("numbers") or [], "trace": [st["source"] for st in steps if st.get("source")],
            "follow_ups": ["What should we do?", (item.get("show_me") or {}).get("label") or "Show me"]}


def _wrap(label: str, width: int = 14) -> str:
    """A chart label on short lines (no rotated ticks in the panel)."""
    lines, cur = [], ""
    for w in label.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return "<br>".join(lines[:3])


def _issue_why(issue_id: str) -> dict[str, Any] | None:
    try:
        from backend.regulatory.issues.service import why
        return why(issue_id)
    except Exception:  # noqa: BLE001 - Why falls back to the top-10 answer
        return None


def _sector_name(item: dict[str, Any]) -> str:
    e = item.get("entity") or {}
    return str(e.get("name") or e.get("id") or "")


def _why_sector(item: dict[str, Any]) -> dict[str, Any]:
    sector = _sector_name(item)
    steps: list[dict[str, Any]] = []
    s = Step(steps, f"Read the {sector} facilities in the corporate book")
    fac = R.read("ews", "corp_exposure", columns="count(*) AS n, count(DISTINCT borrower_id) AS names, max(reporting_quarter) AS q",
                 where=f"sector = ? AND reporting_quarter = (SELECT max(reporting_quarter) FROM {_src('ews', 'corp_exposure')})",
                 args=[sector])
    f0 = fac.rows[0] if fac.rows else {}
    s.done(int(f0.get("n") or 0), "facilities read", fac.stamp({"sector": sector}, str(f0.get("q") or "")),
           f"{int(f0.get('names') or 0):,} borrowers")
    s = Step(steps, "Checked the sector appetite limits")
    snap = R.read("deal_desk", "dd_portfolio_snapshot", where="dimension = 'sector'")
    limits = [r for r in snap.rows if _f(r.get("limit_pct"))]
    s.done(len(limits), "limits checked", snap.stamp({"dimension": "sector"}, str((snap.rows or [{}])[0].get("reporting_quarter") or "")))
    s = Step(steps, "Found sectors over or near their limit")
    over = [r for r in limits if (_f(r.get("share_pct")) or 0) > (_f(r.get("limit_pct")) or 0)]
    near = [r for r in limits if r not in over and (_f(r.get("share_pct")) or 0) >= 0.9 * (_f(r.get("limit_pct")) or 1)]
    s.done(len(over) + len(near), "breaches and near-limits found", snap.stamp({"share_pct": ">= 90% of limit"}, ""),
           f"{len(over)} over, {len(near)} within 10%")
    s = Step(steps, f"Read {sector} by {_BAND}, 8 quarters")
    ser = R.read("ews", "corp_series_segment",
                 columns="reporting_quarter AS q, sum(ead_sar_mn) AS ead, "
                         "sum(CASE WHEN ews_band IN ('critical','high') THEN ead_sar_mn ELSE 0 END) AS warned, "
                         "sum(CASE WHEN ews_band IN ('critical','high') THEN owners ELSE 0 END) AS warned_names",
                 where="sector = ?", args=[sector], group="1", order="1 DESC", limit=8)
    tot = R.read("ews", "corp_series_segment", columns="reporting_quarter AS q, sum(ead_sar_mn) AS ead", group="1",
                 order="1 DESC", limit=8)
    s.done(len(ser.rows), "quarters read", ser.stamp({"sector": sector}, ""))
    s = Step(steps, f"Read the {sector} deals in the pipeline")
    pipe = R.read("deal_desk", "dd_proposal", columns="proposal_id, obligor_name, status, amount_sar_mn",
                  where="sector = ?", args=[sector])
    live = [p for p in pipe.rows if str(p.get("status")) in ACTIVE_DEAL]
    s.done(len(live), "pipeline deals", pipe.stamp({"sector": sector}, ""))

    rows = list(reversed(ser.rows))
    totals = {r["q"]: _f(r["ead"]) or 0.0 for r in tot.rows}
    qs = [r["q"] for r in rows]
    warned = [_f(r["warned"]) or 0.0 for r in rows]
    share = [round(100 * (_f(r["ead"]) or 0.0) / totals[r["q"]], 2) if totals.get(r["q"]) else None for r in rows]
    srow = next((r for r in limits if str(r.get("dimension_name")) == sector), {})
    limit = _f(srow.get("limit_pct"))
    answer = f"{sector} is {share[-1]:.1f}% of the corporate book" if share and share[-1] is not None else sector
    if limit:
        answer += f" against a {limit:.0f}% limit"
    if len(rows) >= 5 and warned[-5] > 0:
        mult = warned[-1] / warned[-5]
        w_share = 100 * warned[-1] / (_f(rows[-1]["ead"]) or 1)
        answer += (f", and the part flagged high or critical risk has grown {mult:.1f}x in a year to "
                   f"{fmt(warned[-1], 'SAR mn')} ({w_share:.1f}% of the sector, from "
                   f"{100 * warned[-5] / (_f(rows[-5]['ead']) or 1):.1f}% in {qs[-5]})")
    if live:
        answer += f"; {len(live)} more deal{'s' if len(live) != 1 else ''} ask {fmt(sum(_f(p.get('amount_sar_mn')) or 0 for p in live), 'SAR mn')}"
    answer += "."
    figure = {
        "data": [
            {"type": "bar", "x": qs, "y": [round(w, 1) for w in warned], "name": f"High or critical {_ON} (SAR m)",
             "marker": {"color": SERIES["warn"]}, "hovertemplate": "%{x}: SAR %{y:,.1f}m<extra></extra>"},
            {"type": "scatter", "mode": "lines+markers", "x": qs, "y": share, "name": "Share of the corporate book (%)",
             "yaxis": "y2", "line": {"color": SERIES["primary"], "width": 2},
             "hovertemplate": "%{x}: %{y:.2f}%<extra></extra>"},
        ] + ([{"type": "scatter", "mode": "lines", "x": [qs[0], qs[-1]], "y": [limit, limit], "yaxis": "y2",
               "name": f"Appetite limit ({limit:.0f}%)", "line": {"color": SERIES["limit"], "dash": "dash", "width": 1.5},
               "hoverinfo": "skip"}] if limit and qs else []),
        "layout": {"title": {"text": f"{sector}: warned exposure and share of the book"},
                   "xaxis": {"tickvals": qs, "ticktext": [f"Q{q[-1]} {q[2:4]}" for q in qs], "tickangle": 0},
                   "yaxis": {"title": {"text": "SAR m"}, "rangemode": "tozero"},
                   "yaxis2": {"title": {"text": "% of book"}, "overlaying": "y", "side": "right",
                              "range": [min([v for v in share if v is not None] + [limit or 0]) - 1, max([v for v in share if v is not None] + [limit or 0]) + 0.5] if share else None},
                   "legend": {"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom", "font": {"size": 10}},
                   "margin": {"l": 52, "r": 52, "t": 64, "b": 32}, "height": 320},
    }
    return {"item_id": item.get("id"), "answer": answer, "steps": steps, "figure": figure,
            "numbers": [num("Share of book", share[-1] if share else None, "%",
                            source=src("ews", "corp_series_segment", {"sector": sector, "reporting_quarter": qs[-1]}, "ead_sar_mn", qs[-1])
                            if qs else None),
                        num("Limit", limit, "%", source=src("deal_desk", "dd_portfolio_snapshot",
                                                            {"dimension": "sector", "dimension_name": sector}, "limit_pct")),
                        num("Warned exposure", warned[-1] if warned else None, "SAR mn",
                            source=src("ews", "corp_series_segment", {"sector": sector, "reporting_quarter": qs[-1],
                                                                      "ews_band": ["critical", "high"]}, "ead_sar_mn", qs[-1])
                            if qs else None),
                        num("Facilities read", int(f0.get("n") or 0),
                            source=src("ews", "corp_exposure", {"sector": sector, "reporting_quarter": str(f0.get("q") or "")},
                                       "facility_id", str(f0.get("q") or "")))],
            "trace": [st["source"] for st in steps if st.get("source")],
            "follow_ups": ["What should we do?", f"Show the {sector} names {_ON}", f"Show the {sector} deals"]}


_LIVE: dict[str, dict[str, Any]] = {}
LIVE_MAX = 4


def _price_live(pid: str) -> dict[str, Any] | None:
    """A deal the engine has not published a result for (R12 demo and pipeline deals): priced now with the Deal Desk
    engine on its record from Data Domains (`dd_deal` / `dd_pipeline` through `deals.get`), in the dd_result shape."""
    if pid in _LIVE:
        return _LIVE[pid]
    try:
        from backend.dealdesk import engine
        from backend.dealdesk.data import deals
        m = engine.public(engine.analyse(deals.get(pid)))
        mt, ap = m.get("metrics") or {}, m.get("approval") or {}
    except Exception:  # noqa: BLE001 - a deal the engine cannot price is simply not priced
        return None
    row = {"proposal_id": pid, "view": "ask", "live": True, "ead_y1_sar_mn": mt.get("ead_y1"),
           "el_lifetime_sar_mn": mt.get("el_lifetime"), "capital_y1_sar_mn": mt.get("capital_y1"),
           "lifetime_raroc_pct": 100 * float(mt.get("lifetime_raroc") or 0), "hurdle_pct": 100 * float(mt.get("hurdle") or 0),
           "sva_sar_mn": mt.get("sva"), "decision": "approve" if mt.get("clears_hurdle") else "counter_offer",
           "hard_breaches": ", ".join(ap.get("hard_breaches") or []), "soft_breaches": ", ".join(ap.get("soft_breaches") or [])}
    _LIVE[pid] = row
    return row


def _deal_rows(ids: list[str]) -> tuple[R.Read, R.Read]:
    """(priced results, deal register rows) for these deals: dd_result where the engine published one, else priced
    live (at most LIVE_MAX deals); names and amounts from dd_deal (E's register), else dd_proposal."""
    if not ids:
        return R.Read("deal_desk", "dd_result"), R.Read("deal_desk", "dd_deal")
    ph = ", ".join("?" for _ in ids)
    res = R.read("deal_desk", "dd_result", where=f"proposal_id IN ({ph})", args=ids)
    pro = R.read("deal_desk", "dd_deal", columns="proposal_id, obligor_name, status, rm, proposed_limits_mn AS amount_sar_mn",
                 where=f"proposal_id IN ({ph})", args=ids)
    if pro.status != "ok" or not pro.rows:
        pro = R.read("deal_desk", "dd_proposal", columns="proposal_id, obligor_name, sector, status, amount_sar_mn, rm",
                     where=f"proposal_id IN ({ph})", args=ids)
    priced = {r["proposal_id"] for r in res.rows}
    for pid in [p for p in ids if p not in priced][:LIVE_MAX]:
        row = _price_live(pid)
        if row:
            res.rows.append(row)
    return res, pro


def _why_deals(item: dict[str, Any]) -> dict[str, Any]:
    ids = list((item.get("entity") or {}).get("deals") or [])
    steps: list[dict[str, Any]] = []
    s = Step(steps, "Read the deals in this queue")
    res, pro = _deal_rows(ids)
    s.done(len(pro.rows), "deals read", pro.stamp({"proposal_id": ids}, ""))
    s = Step(steps, "Read the engine's priced results for each")
    s.done(len(res.rows), "results read", res.stamp({"proposal_id": ids}, ""))
    s = Step(steps, "Checked each against its hurdle and the limits")
    asks = {r["proposal_id"]: r for r in res.rows if r.get("view") == "ask"}
    below = [p for p, r in asks.items() if (_f(r.get("lifetime_raroc_pct")) or 0) < (_f(r.get("hurdle_pct")) or 0)]
    breaches = [p for p, r in asks.items() if r.get("hard_breaches") or r.get("soft_breaches")]
    s.done(len(below) + len(breaches), "issues found", res.stamp({"view": "ask"}, ""),
           f"{len(below)} below hurdle, {len(breaches)} with limit breaches")
    names = {p["proposal_id"]: p.get("obligor_name") for p in pro.rows}
    x = [f"{pid}" for pid in ids if pid in asks]
    figure = {"data": [
        {"type": "bar", "x": x, "y": [round(_f(asks[p].get("lifetime_raroc_pct")) or 0, 1) for p in x], "name": "RAROC as asked (%)",
         "marker": {"color": SERIES["primary"]}, "customdata": [names.get(p) for p in x],
         "hovertemplate": "%{x} %{customdata}: %{y:.1f}%<extra></extra>"},
        {"type": "scatter", "mode": "markers", "x": x, "y": [_f(asks[p].get("hurdle_pct")) for p in x], "name": "Hurdle (%)",
         "marker": {"color": SERIES["limit"], "symbol": "line-ew-open", "size": 28, "line": {"width": 2}}}],
        "layout": {"title": {"text": "RAROC as asked against the hurdle"}, "yaxis": {"title": {"text": "%"}},
                   "legend": {"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom", "font": {"size": 10}},
                   "margin": {"l": 48, "r": 16, "t": 48, "b": 32}, "height": 280}}
    answer = (f"{len(ids)} deal{'s' if len(ids) != 1 else ''} in this queue; {len(below)} price below hurdle as asked"
              + (f" ({', '.join(below[:3])})" if below else "") + f" and {len(breaches)} touch a limit.")
    return {"item_id": item.get("id"), "answer": answer, "steps": steps, "figure": figure if x else None,
            "numbers": [num("Deals", len(ids)), num("Below hurdle", len(below)), num("Limit breaches", len(breaches))],
            "trace": [st["source"] for st in steps if st.get("source")],
            "follow_ups": ["What should we do?", "Show these deals", "Open the first deal"]}


def _why_generic(item: dict[str, Any]) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for t in item.get("trace") or []:
        if not t:
            continue
        lab = _label(t)
        lab = lab[:1].lower() + lab[1:] if len(lab) > 1 and lab[1].islower() else lab
        s = Step(steps, f"Read the {lab}")
        n = _count(t)
        s.done(n, "rows read" if n is not None else "", t)
    nums = [n for n in (item.get("numbers") or []) if isinstance(n.get("value"), (int, float))]
    figure = None
    if len(nums) >= 2 and len({n.get("unit") for n in nums}) == 1:
        figure = {"data": [{"type": "bar", "x": [n["label"] for n in nums], "y": [n["value"] for n in nums],
                            "marker": {"color": SERIES["primary"]}, "hovertemplate": "%{x}: %{y:,}<extra></extra>"}],
                  "layout": {"margin": {"l": 48, "r": 16, "t": 16, "b": 40}, "height": 240}}
    answer = item.get("title", "") + (f". {item.get('detail')}" if item.get("detail") else "")
    return {"item_id": item.get("id"), "answer": answer.rstrip(".") + ".", "steps": steps, "figure": figure,
            "numbers": item.get("numbers") or [], "trace": [s["source"] for s in steps],
            "follow_ups": ["What should we do?", (item.get("show_me") or {}).get("label") or "Show me"]}


# ------------------------------------------------------------------ Who drives it? (the names behind a line)

def drivers(item: dict[str, Any], limit: int = 8) -> dict[str, Any]:
    """The borrowers behind a sector line: the largest Early Warning high or critical exposures in the sector at the
    latest quarter, with their stage, days past due and the warning's reasons (ews.corp_exposure)."""
    e = item.get("entity") or {}
    if e.get("kind") != "sector" and item.get("kind") != "sector_appetite":
        return {"item_id": item.get("id"), "answer": "", "rows": [], "columns": [], "trace": []}
    sector = _sector_name(item)
    r = R.read("ews", "corp_exposure",
               columns="borrower_id, any_value(borrower_name) AS name, sum(ead_sar_mn) AS ead, max(stage) AS stage, "
                       "max(dpd_days) AS dpd, max(rating_notches_moved) AS notches, any_value(ews_band) AS band, "
                       "max(reporting_quarter) AS q",
               where=f"sector = ? AND ews_band IN ('critical', 'high') AND reporting_quarter = "
                     f"(SELECT max(reporting_quarter) FROM {_src('ews', 'corp_exposure')})",
               args=[sector], group="borrower_id", order="ead DESC", limit=limit)
    tot = R.read("ews", "corp_exposure", columns="count(DISTINCT borrower_id) AS n, sum(ead_sar_mn) AS ead",
                 where=f"sector = ? AND ews_band IN ('critical', 'high') AND reporting_quarter = "
                       f"(SELECT max(reporting_quarter) FROM {_src('ews', 'corp_exposure')})", args=[sector])
    t0 = tot.rows[0] if tot.rows else {}
    shown = sum(_f(x.get("ead")) or 0 for x in r.rows)
    total = _f(t0.get("ead")) or 0
    q = str((r.rows[0] if r.rows else {}).get("q") or "")
    rows = [{"name": x.get("name") or x["borrower_id"], "borrower_id": x["borrower_id"], "band": str(x.get("band") or "").capitalize(),
             "ead": fmt(_f(x.get("ead")), "SAR mn"), "stage": int(_f(x.get("stage")) or 0), "dpd": int(_f(x.get("dpd")) or 0),
             "notches": int(_f(x.get("notches")) or 0),
             "href": (f"/deal-desk/customer-packs?cif={x['borrower_id']}" if _edition.is_dealdesk()
                      else f"/early-warning?domain=corporate&customer={x['borrower_id']}")} for x in r.rows]
    answer = (f"{int(t0.get('n') or 0):,} {sector} borrowers are high or critical {_ON} in {q}, "
              f"{fmt(total, 'SAR mn')}; the {len(rows)} largest carry {fmt(shown, 'SAR mn')} "
              f"({(100 * shown / total) if total else 0:.0f}%), led by {rows[0]['name']} ({rows[0]['ead']}).") if rows else \
        f"No {sector} borrower is high or critical {_ON} now."
    return {"item_id": item.get("id"), "answer": answer, "rows": rows,
            "columns": [{"key": "name", "label": "Borrower"}, {"key": "band", "label": "Warning"},
                        {"key": "ead", "label": "EAD", "align": "right"}, {"key": "stage", "label": "Stage", "align": "right"}],
            "trace": [r.stamp({"sector": sector, "ews_band": ["critical", "high"]}, q)],
            "show_me": {"href": (f"/deal-desk/review?sector={quote(sector)}" if _edition.is_dealdesk()
                                 else f"/early-warning?domain=corporate&segment={quote(sector)}"),
                        "label": f"Show the {sector} names {_ON}"}}


# ------------------------------------------------------------------ What should we do?

def _sum(rows: list[dict[str, Any]], col: str) -> float:
    return round(sum(_f(r.get(col)) or 0.0 for r in rows), 4)


def _weighted_raroc(rows: list[dict[str, Any]]) -> float | None:
    cap = _sum(rows, "capital_y1_sar_mn")
    if not cap:
        return None
    return round(sum((_f(r.get("lifetime_raroc_pct")) or 0) * (_f(r.get("capital_y1_sar_mn")) or 0) for r in rows) / cap, 2)


def _option(key: str, title: str, rows: list[dict[str, Any]], how: str, effect: str, *, share_after: float | None = None,
            limit: float | None = None, recommended: bool = False,
            source_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ead, ecl, cap = _sum(rows, "ead_y1_sar_mn"), _sum(rows, "el_lifetime_sar_mn"), _sum(rows, "capital_y1_sar_mn")
    sva, raroc = _sum(rows, "sva_sar_mn"), _weighted_raroc(rows)
    traced = rows or source_rows or []  # an option that takes nothing is traced to what it forgoes
    lkey = ({"proposal_id": sorted({r["proposal_id"] for r in traced}), "view": sorted({r["view"] for r in traced})}
            if traced else None)

    live = any(r.get("live") for r in traced)

    def s_(col: str) -> dict[str, Any] | None:
        if not lkey:
            return None
        if live:  # priced now by the engine from the deal's record in dd_deal
            return src("deal_desk", "dd_deal", {"proposal_id": lkey["proposal_id"]}, "proposal_json")
        return src("deal_desk", "dd_result", lkey, col)
    numbers = [num("New exposure", ead, "SAR mn", source=s_("ead_y1_sar_mn")),
               num("Lifetime ECL", ecl, "SAR mn", source=s_("el_lifetime_sar_mn")),
               num("Capital", cap, "SAR mn", source=s_("capital_y1_sar_mn")),
               num("RAROC", raroc, "%", source=s_("lifetime_raroc_pct")), num("SVA", sva, "SAR mn", source=s_("sva_sar_mn"))]
    if share_after is not None:
        numbers.append(num("Sector share after", share_after, "%", f"{share_after:.2f}%",
                           source=src("deal_desk", "dd_portfolio_snapshot", {"dimension": "sector"}, "ead_sar_mn")))
    return {"key": key, "title": title, "how": how, "effect": effect, "recommended": recommended, "numbers": numbers,
            "figures": {"ead": ead, "ecl": ecl, "capital": cap, "raroc": raroc, "sva": sva, "share_after": share_after,
                        "limit": limit},
            "deals": sorted({r["proposal_id"] for r in rows})}


def options(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get("kind")
    if kind == "sector_appetite" or (item.get("entity") or {}).get("kind") == "sector":
        return _options_sector(item)
    if kind == "deal_queue":
        return _options_deals(item, list((item.get("entity") or {}).get("deals") or []))
    got = _options_issue(item)
    return got or _options_generic(item)


def _options_issue(item: dict[str, Any]) -> dict[str, Any] | None:
    """R14 r (K2 (a)): a line with an issue view answers "What to do" with the view's actions, each with its owner and
    due date (deterministic)."""
    href = str((item.get("open") or {}).get("href") or "")
    if "issue=" not in href:
        return None
    from urllib.parse import parse_qs, urlparse
    iid = (parse_qs(urlparse(href).query).get("issue") or [""])[0]
    try:
        from backend.regulatory.issues.service import get
        v = get(iid)
    except Exception:  # noqa: BLE001
        return None
    acts = (v.get("actions") or [])[:3]
    if not acts:
        return None
    from datetime import date as _d

    def _due(x: str) -> str:
        try:
            return _d.fromisoformat(x).strftime("%-d %b %Y")
        except ValueError:
            return x
    opts = [{"key": f"a{a['n']}", "title": a["action"],
             "how": f"Owner: {a['owner']}. Due {_due(a['due'])}. {a.get('why') or ''}".strip(),
             "effect": "", "recommended": i == 0,
             "numbers": [a["figure"]] if a.get("figure") else [], "figures": {}} for i, a in enumerate(acts)]
    return {"item_id": item.get("id"), "answer": f"{len(opts)} actions, in order. {v.get('headline') or ''}",
            "options": opts, "recommended": opts[0]["key"], "engine": "regulatory issue view",
            "trace": v.get("trace") or item.get("trace") or []}


def _options_sector(item: dict[str, Any]) -> dict[str, Any]:
    sector = _sector_name(item)
    pipe = R.read("deal_desk", "dd_proposal", columns="proposal_id, status, amount_sar_mn", where="sector = ?", args=[sector])
    ids = sorted(p["proposal_id"] for p in pipe.rows if str(p.get("status")) in ACTIVE_DEAL)
    out = _options_deals(item, ids, sector=sector)
    out["trace"].append(pipe.stamp({"sector": sector, "status": list(ACTIVE_DEAL)}, ""))
    return out


def _options_deals(item: dict[str, Any], ids: list[str], sector: str = "") -> dict[str, Any]:
    res, pro = _deal_rows(ids)
    ask = [r for r in res.rows if r.get("view") == "ask"]
    rec_by = {r["proposal_id"]: r for r in res.rows if r.get("view") == "recommended"}
    # Recommended structures where the optimiser found one that clears the hurdle; the rest are declined.
    rec = [rec_by[p] for p in sorted(rec_by) if (_f(rec_by[p].get("sva_sar_mn")) or 0) >= -1e-9
           and "decline" not in str(rec_by[p].get("decision") or "")]
    # A deal with no optimiser result (priced now): approved as asked when it clears the hurdle, else counter-offered.
    no_rec = [r for r in ask if r["proposal_id"] not in rec_by]
    rec += [r for r in no_rec if (_f(r.get("sva_sar_mn")) or 0) >= -1e-9]
    kept = {r["proposal_id"] for r in rec}
    engine_declines = {r["proposal_id"] for r in no_rec if "decline" in str(r.get("decision") or "")}
    declined = sorted(({r["proposal_id"] for r in ask if r["proposal_id"] in rec_by} | engine_declines) - kept)
    countered = sorted({r["proposal_id"] for r in no_rec} - kept - engine_declines)
    snap = R.read("deal_desk", "dd_portfolio_snapshot", where="dimension = 'sector'")
    total = sum(_f(r.get("ead_sar_mn")) or 0.0 for r in snap.rows)
    srow = next((r for r in snap.rows if str(r.get("dimension_name")) == sector), {}) if sector else {}
    s_ead, limit = _f(srow.get("ead_sar_mn")), _f(srow.get("limit_pct"))

    def share(add: float) -> float | None:
        return round(100 * ((s_ead or 0) + add) / (total + add), 2) if sector and total and s_ead is not None else None

    label = f"the {sector} pipeline" if sector else "these deals"
    a = _option("as_asked", f"Approve {label} as asked", ask,
                "Every deal on its asked terms.",
                "Takes all the new exposure, including deals that price below hurdle.",
                share_after=share(_sum(ask, "ead_y1_sar_mn")), limit=limit)
    b = _option("recommended", ("Approve on the recommended structures" if rec_by else "Approve the deals that clear the hurdle")
                + (f"; decline {', '.join(declined)}" if declined else "")
                + (f"; counter-offer {', '.join(countered)} on price" if countered else ""),
                rec, "The optimiser's structure closest to each ask (price, tenor, security); deals that cannot clear the "
                     "hurdle are declined, and deals priced now that fall short go back to the RM for a better price.",
                "Keeps the business that pays for its risk and capital.",
                share_after=share(_sum(rec, "ead_y1_sar_mn")), limit=limit, recommended=True)
    c = _option("hold", f"Hold new {sector} lending; put the sector on enhanced monitoring" if sector
                else "Hold these deals; ask the relationship managers for more information",
                [],"No new limits until the next quarterly review; tier High monitoring on the warned names.",
                f"Forgoes {fmt(_sum(rec, 'sva_sar_mn'), 'SAR mn')} of SVA from the recommended structures.",
                share_after=share(0.0), limit=limit, source_rows=rec or ask)
    c["figures"]["sva_forgone"] = _sum(rec, "sva_sar_mn")
    for o in (a, b, c):
        if limit and o["figures"]["share_after"] is not None:
            o["effect"] += (f" Sector share {o['figures']['share_after']:.2f}% against the {limit:.0f}% limit"
                            f" ({'over' if o['figures']['share_after'] > limit else 'within'}).")
    asked = _sum(pro.rows, "amount_sar_mn")
    lead = (f"For {sector}: {len(ask)} live deal{'s ask' if len(ask) != 1 else ' asks'} {fmt(asked, 'SAR mn')} "
            f"({fmt(_sum(ask, 'ead_y1_sar_mn'), 'SAR mn')} first-year exposure). " if sector else "")
    answer = (lead + f"On the recommended structures RAROC is {b['figures']['raroc'] or 0:.1f}% for "
              f"{fmt(b['figures']['capital'], 'SAR mn')} of capital and {fmt(b['figures']['ecl'], 'SAR mn')} lifetime ECL; "
              f"as asked it is {a['figures']['raroc'] or 0:.1f}%.") if ask else (lead + "No priced deals to compare.")
    return {"item_id": item.get("id"), "answer": answer, "options": [a, b, c], "recommended": "recommended",
            "engine": ("Deal Desk engine and optimiser (published results" + (", and deals priced now from their records"
                       if any(r.get("live") for r in res.rows) else "") + ")"),
            "trace": [res.stamp({"proposal_id": ids}, ""), pro.stamp({"proposal_id": ids}, ""),
                      snap.stamp({"dimension": "sector", "dimension_name": sector}, "")]}


def _options_generic(item: dict[str, Any]) -> dict[str, Any]:
    nums = item.get("numbers") or []
    owner = {"regulatory": "Finance and Risk", "ews": "the relationship managers", "dealdesk": "the credit reviewers",
             "lenses": "the portfolio team", "queries": "Risk", "ecl": "the ECL run owner", "watch": "the watch owners",
             "agents": "you"}.get(str(item.get("module")), "the owner")
    first = nums[0] if nums else None
    opts = [
        {"key": "act", "title": "Act now", "how": f"Ask {owner} to resolve it this week and report back.",
         "effect": item.get("title", ""), "recommended": item.get("severity") in ("critical", "high"), "numbers": nums[:3],
         "figures": {}},
        {"key": "assign", "title": "Assign with a due date", "how": f"Assign to {owner} with a due date in 14 days; Noor "
         "follows up and raises it again if it is still open.", "effect": "Tracked; no change today.",
         "recommended": item.get("severity") not in ("critical", "high"), "numbers": [first] if first else [], "figures": {}},
        {"key": "monitor", "title": "Monitor", "how": "Keep it in the brief and decide at the next review.",
         "effect": "No change; it returns in tomorrow's brief if it moves.", "recommended": False, "numbers": [], "figures": {}},
    ]
    return {"item_id": item.get("id"), "answer": f"Three ways to handle it. {item.get('title', '')}.", "options": opts,
            "recommended": next(o["key"] for o in opts if o["recommended"]), "engine": "", "trace": item.get("trace") or []}

