"""Import existing CreditProbe work into a report: list importable objects and turn one into a section.

Each source type has a lister and a resolver. Objects owned by another v5 service are fetched from that service
server side, forwarding the caller's `cp_session` cookie, so the caller only sees what they may see there; a
service that is down is listed as unavailable and never fails the page. The Early Warning lists, Borrower 360
pages of corporate borrowers and the Data Builder extracts are built from the same books those modules read.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from backend.playbook_v5 import content, paths, store
from backend.identity_v5.client import cookie_name as _cookie_name

TYPE_LABEL = {"cockpit-thread": "Cockpit answer", "investigation": "Investigation", "attention-item": "Attention item",
              "document": "Document", "project": "Project",
              "early-warning-list": "Early Warning list", "borrower": "Borrower 360", "whatif-scenario": "What-If scenario",
              "whatif-thread": "What-If thread", "data-extract": "Data Domains extract", "analysis": "Analysis",
              "scorecard-validation": "Scorecard validation", "report": "Report", "policy-document": "Policy document",
              "dealdesk-proposal": "Deal Desk proposal", "dealdesk-analysis": "Deal Desk analysis", "lens": "Lens",
              "crm-compliance": "CBUAE CRM compliance"}
#: The service names a user reads when one cannot answer (never a port or a host).
SERVICE_LABEL = {"core": "Workspace", "cockpit": "The Cockpit", "ews": "Early Warning", "b360": "Borrower 360",
                 "whatif": "What-If", "data": "Data Domains", "scorecard": "Scorecard Validation",
                 "dealdesk": "Deal Desk", "lenses": "Lenses", "playbook": "Playbook"}
TIMEOUT = 6


class Unavailable(RuntimeError):
    pass


def _get(service: str, path: str, cookie: str | None) -> Any:
    url = paths.SERVICES[service].rstrip("/") + path
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = f"{_cookie_name()}={cookie}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise store.NotFound(f"{TYPE_LABEL.get(service, service)}: not found.") from exc
        raise Unavailable(f"{SERVICE_LABEL.get(service, "That service")} could not answer just now") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise Unavailable(f"{SERVICE_LABEL.get(service, "That service")} is temporarily unavailable") from exc


def _src(type_: str, id_: str, label: str, href: str, summary: str = "", **meta: Any) -> dict[str, Any]:
    out = {"type": type_, "id": str(id_), "label": store.BANNED.sub("", label)[:200], "href": href, "type_label":
           TYPE_LABEL.get(type_, type_), "available": True}
    if summary:
        out["summary"] = store.BANNED.sub("", summary)[:400]
    if meta:
        out["meta"] = meta
    return out


def _num(v: Any) -> float | None:
    try:
        if isinstance(v, str):
            v = v.replace(",", "")
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _clean(text: Any, limit: int = store.MAX_TEXT) -> str:
    return store.BANNED.sub("", str(text or ""))[:limit].strip()


# ---------------------------------------------------------- cockpit threads


def list_cockpit(cookie: str | None) -> list[dict[str, Any]]:
    s = _get("cockpit", "/api/v1/cockpit-v4/session", cookie)
    out = [_src("cockpit-thread", t["thread_id"], t.get("title") or t.get("last_question") or "Cockpit thread",
                f"/cockpit/thread/{t['thread_id']}", t.get("last_question") or "") for t in s.get("recent_threads") or []]
    try:
        saved = _get("cockpit", "/api/v1/cockpit-v4/saved-analyses", cookie).get("saved") or []
        out += [_src("cockpit-thread", f"saved:{a['saved_id']}", a.get("title") or a.get("question") or "Saved answer",
                     f"/cockpit/saved/{a['saved_id']}", a.get("question") or "") for a in saved]
    except (Unavailable, store.NotFound):
        pass
    return out


def _cockpit_chart(c: dict[str, Any]) -> dict[str, Any] | None:
    pts = c.get("points") or []
    ys = c.get("y_columns") or []
    if not pts or not ys:
        return None
    labels = [str(p.get("label")) for p in pts]
    kind = c.get("kind")
    data = []
    for y in ys:
        vals = [_num((p.get("values") or {}).get(y)) for p in pts]
        if kind == "line":
            data.append({"type": "scatter", "mode": "lines+markers", "name": y, "x": labels, "y": vals})
        else:
            data.append({"type": "bar", "name": y, "x": labels, "y": vals})
    return {"kind": "chart", "title": _clean(c.get("title"), 200) or "Chart",
            "figure": {"data": data, "layout": {"yaxis": {"title": {"text": c.get("unit") or ""}}}}}


def _cockpit_table(t: dict[str, Any]) -> dict[str, Any] | None:
    cols = (t.get("columns") or [])[:30]
    rows = (t.get("rows") or [])[:500]
    if not cols or not rows:
        return None
    return {"kind": "table", "title": _clean(t.get("title"), 200),
            "columns": [{"key": f"c{i}", "label": _clean(c, 120) or f"Column {i + 1}", "format": "text"}
                        for i, c in enumerate(cols)],
            "rows": [{f"c{i}": _clean((r.get("display") or {}).get(c, (r.get("canonical") or {}).get(c, "")), 500)
                      for i, c in enumerate(cols)} for r in rows]}


def resolve_cockpit(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if id_.startswith("saved:"):
        sid = id_.split(":", 1)[1]
        saved = _get("cockpit", f"/api/v1/cockpit-v4/saved-analyses/{urllib.parse.quote(sid)}", cookie)
        thread_id = saved.get("thread_id")
        src = _src("cockpit-thread", id_, saved.get("title") or "Saved answer", f"/cockpit/saved/{sid}")
    else:
        thread_id, src = id_, None
    t = _get("cockpit", f"/api/v1/cockpit-v4/threads/{urllib.parse.quote(str(thread_id))}", cookie)
    src = src or _src("cockpit-thread", id_, t.get("title") or "Cockpit thread", f"/cockpit/thread/{thread_id}")
    blocks: list[dict[str, Any]] = []
    for turn in (t.get("turns") or [])[-3:]:
        a = turn.get("answer") or {}
        blocks.append({"kind": "heading", "level": 3, "text": _clean(turn.get("question"), 200) or "Question"})
        if a.get("narrative"):
            blocks.append({"kind": "paragraph", "text": _clean(a["narrative"])})
        for c in (a.get("charts") or [])[:3]:
            ch = _cockpit_chart(c)
            if ch:
                blocks.append(ch)
        for tb in (a.get("tables") or [])[:2]:
            tt = _cockpit_table(tb)
            if tt:
                blocks.append(tt)
    if not blocks:
        blocks = [{"kind": "paragraph", "text": "This Cockpit thread has no answered question yet."}]
    return src, f"Cockpit: {_clean(t.get('title'), 150) or 'answer'}", blocks[:60]


# ---------------------------------------------------------- attention items


def list_attention(cookie: str | None) -> list[dict[str, Any]]:
    out = []
    for domain in ("corporate", "retail"):
        feed = _get("cockpit", f"/api/v1/cockpit-v4/attention?domain={domain}", cookie)
        for it in [*(feed.get("segments_requiring_attention") or []), *(feed.get("ecl_highlights") or [])]:
            out.append(_src("attention-item", it["item_id"], f"Attention: {it.get('headline', '')}",
                            f"/?domain={domain}&attention={urllib.parse.quote(it['item_id'])}", it.get("one_line") or "",
                            domain=domain))
    return out


def resolve_attention(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    r = _get("cockpit", f"/api/v1/cockpit-v4/attention/{urllib.parse.quote(id_)}", cookie)
    it = r["item"]
    domain = "retail" if it.get("period_noun") == "month" or r.get("domain_id") == "retail" else "corporate"
    src = _src("attention-item", id_, f"Attention: {it.get('headline', '')}",
               f"/?domain={domain}&attention={urllib.parse.quote(id_)}", it.get("one_line") or "")
    blocks: list[dict[str, Any]] = [{"kind": "paragraph", "text": _clean(
        f"**{it.get('headline', '')}.** {it.get('what_changed', '')} {it.get('why_it_appeared', '')}")}]
    kn = it.get("key_numbers") or []
    if kn:
        blocks.append({"kind": "table", "title": "Key numbers", "columns": [
            {"key": "label", "label": "Measure", "format": "text"}, {"key": "value", "label": "Value", "format": "text"}],
            "rows": [{"label": _clean(k.get("label"), 200), "value": _clean(k.get("value"), 200)} for k in kn[:20]]})
    drivers = [_clean(d.get("statement"), 400) for d in (it.get("possible_drivers") or []) if d.get("statement")]
    if drivers:
        blocks.append({"kind": "bullets", "items": drivers[:10]})
    try:
        q = urllib.parse.urlencode({"domain": domain, "family": it.get("family", ""), "segment": it.get("segment", ""),
                                    "period": it.get("reporting_period", ""),
                                    "comparison": it.get("comparison_period", "")})
        c = _get("core", f"/api/v1/attention/charts?{q}", cookie)
        t = c.get("trend") or {}
        if t.get("periods"):
            blocks.append({"kind": "chart", "title": f"{c.get('measure_label', '')}: {c.get('segment_label', '')} "
                                                     "against the book",
                           "figure": {"data": [
                               {"type": "scatter", "mode": "lines+markers", "name": c.get("segment_label", "Segment"),
                                "x": t["periods"], "y": t.get("segment"), "marker": {"color": "#C2410C"}},
                               {"type": "scatter", "mode": "lines", "name": "Whole book", "x": t["periods"],
                                "y": t.get("book"), "line": {"dash": "dash"}, "marker": {"color": "#1F4E6B"}}],
                               "layout": {"yaxis": {"title": {"text": c.get("unit", "")}}, "legend": {"orientation": "h"}}}})
        view = ((c.get("contributors") or {}).get("views") or [None])[0]
        if view and view.get("items"):
            items = view["items"][:12]
            blocks.append({"kind": "chart", "title": f"What drove the movement, by {view.get('label', '').lower()}",
                           "figure": {"data": [{"type": "bar", "orientation": "h", "y": [str(i.get("name")) for i in items],
                                                "x": [_num(i.get("change")) for i in items],
                                                "marker": {"color": "#2E7D9A"}}], "layout": {"margin": {"l": 160}}}})
    except (Unavailable, store.NotFound):
        pass
    from backend.playbook_v5 import policy

    try:
        with store.db() as con:
            ex = policy.explain(con, domain, "ecl", segment=str(it.get("segment_label") or it.get("segment") or ""),
                                period=str(it.get("reporting_period") or ""))
        if ex.get("sentence"):
            blocks.append({"kind": "callout", "tone": "info", "text": f"Policy: {ex['sentence']}"})
    except store.Invalid:
        pass
    return src, f"Attention: {_clean(it.get('headline'), 150)}", blocks


# --------------------------------------------------------- early warning


def list_ews(cookie: str | None) -> list[dict[str, Any]]:
    out = [_src("early-warning-list", "corporate", "Early Warning: corporate book, high and critical",
                f"/early-warning?domain=corporate&period={content.CORP_PERIOD}")]
    top = [r["sector"] for r in content.sector_table()["rows"][:6]]
    out += [_src("early-warning-list", f"corporate:{s}", f"Early Warning: {s}, high and critical",
                 f"/early-warning?domain=corporate&segment={urllib.parse.quote(s)}&period={content.CORP_PERIOD}")
            for s in top]
    out.append(_src("early-warning-list", "retail", "Early Warning: retail book, high and critical",
                    "/early-warning?domain=retail"))
    return out


def resolve_ews(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if id_ == "retail":
        r = _get("ews", "/api/v1/ews/customers?domain=retail&cohort=high_or_critical&limit=20", cookie)
        rows = [{"id": c.get("customer_id"), "name": _clean(c.get("customer_name"), 200), "band": str(c.get("band", "")).capitalize(),
                 "score": _num(c.get("score")), "ead": (_num(c.get("exposure")) or 0) * 1e6,
                 "dpd": _num(c.get("dpd")), "reason": _clean(((c.get("reasons") or [{}])[0] or {}).get("name"), 200)}
                for c in r.get("customers") or []]
        src = _src("early-warning-list", id_, "Early Warning: retail book, high and critical", "/early-warning?domain=retail")
        return src, "Early Warning: retail book", [
            {"kind": "paragraph", "text": f"{r.get('total', len(rows)):,} retail customers are high or critical on Early "
                                          "Warning; the 20 largest are listed."},
            {"kind": "table", "title": "Retail high and critical warnings",
             "columns": [{"key": "id", "label": "Customer", "format": "text"}, {"key": "name", "label": "Name", "format": "text"},
                         {"key": "band", "label": "Band", "format": "text"}, {"key": "score", "label": "Score", "format": "int"},
                         {"key": "ead", "label": "Exposure", "format": "sar"}, {"key": "dpd", "label": "DPD", "format": "int"},
                         {"key": "reason", "label": "Main reason", "format": "text"}], "rows": rows}]
    sector = id_.split(":", 1)[1] if ":" in id_ else None
    title, blocks = content.ews_section(sector=sector)
    label = f"Early Warning: {sector or 'corporate book'}, high and critical"
    href = (f"/early-warning?domain=corporate&period={content.CORP_PERIOD}" +
            (f"&segment={urllib.parse.quote(sector)}" if sector else ""))
    return _src("early-warning-list", id_, label, href), title if not sector else f"Early Warning: {sector}", blocks


# ----------------------------------------------------------- borrower 360


def list_borrowers(cookie: str | None, q: str = "") -> list[dict[str, Any]]:
    rows = content.ews_rows(top=20)
    ids = ["CB01312", *[r["borrower_id"] for r in rows if r["borrower_id"] != "CB01312"]]
    names = {r["borrower_id"]: r["name"] for r in rows}
    names.setdefault("CB01312", "Al Kharj Gulf Engineering")
    m = re.search(r"\b([CR][BC]\d{4,6})\b", q.upper())
    if m and m.group(1) not in ids:
        ids.insert(0, m.group(1))
    return [_src("borrower", i, f"Borrower 360: {names.get(i, i)} ({i})",
                 f"/borrower-360?domain={'retail' if i.startswith('RC') else 'corporate'}&customer_id={i}&period="
                 f"{content.RETAIL_PERIOD if i.startswith('RC') else content.CORP_PERIOD}") for i in ids]


def resolve_borrower(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    id_ = id_.upper()
    if id_.startswith("RC"):
        r = _get("b360", f"/api/v1/b360/customers/{id_}?domain=retail&period={content.RETAIL_PERIOD}", cookie)
        p = r.get("profile") or {}
        src = _src("borrower", id_, f"Borrower 360: {p.get('name', id_)} ({id_})",
                   f"/borrower-360?domain=retail&customer_id={id_}&period={content.RETAIL_PERIOD}")
        return src, f"Borrower 360: {id_}", [{"kind": "kpis", "items": [
            {"label": "Exposure", "value": (_num(p.get("exposure")) or 0) * 1e6, "format": "sar"},
            {"label": "ECL", "value": (_num(p.get("ecl")) or 0) * 1e6, "format": "sar"},
            {"label": "Early Warning score", "value": _num(p.get("ews_score")), "format": "int"},
            {"label": "Worst DPD", "value": _num(p.get("worst_dpd")), "format": "int"}]}]
    try:
        parts = content.borrower_sections(id_)
    except LookupError as exc:
        raise store.NotFound(str(exc)) from exc
    name = content.borrowers()
    nm = str(name[name.borrower_id == id_].borrower_name.iloc[-1])
    blocks: list[dict[str, Any]] = []
    for title, bl in parts[1:6]:
        blocks.append({"kind": "heading", "level": 3, "text": title})
        blocks.extend(bl)
    src = _src("borrower", id_, f"Borrower 360: {nm} ({id_})",
               f"/borrower-360?domain=corporate&customer_id={id_}&period={content.CORP_PERIOD}")
    return src, f"Borrower 360: {nm} ({id_})", blocks


# ---------------------------------------------------------------- what-if


def list_whatif(cookie: str | None) -> list[dict[str, Any]]:
    out = []
    for domain in ("corporate", "retail"):
        lib = _get("whatif", f"/api/v1/whatif/library?domain={domain}", cookie)
        for s in [*(lib.get("saved") or []), *(lib.get("standard") or [])][:15]:
            ch = _num(s.get("change"))
            out.append(_src("whatif-scenario", s["scenario_id"], f"What-If: {s.get('name', '')}",
                            f"/what-if?domain={domain}&open={urllib.parse.quote(s['scenario_id'])}",
                            f"ECL change {ch:+,.1f}m" if ch is not None else ""))
    try:
        for t in (_get("whatif", "/api/v1/whatif/threads", cookie).get("threads") or [])[:10]:
            out.append(_src("whatif-thread", t["thread_id"], f"What-If thread: {t.get('title', '')}",
                            f"/what-if/thread/{t['thread_id']}"))
    except (Unavailable, store.NotFound):
        pass
    return out


def _whatif_result_blocks(res: dict[str, Any]) -> list[dict[str, Any]]:
    cards = res.get("cards") or {}
    blocks: list[dict[str, Any]] = []
    if cards:
        blocks.append({"kind": "kpis", "items": [
            {"label": "ECL before", "value": (_num(cards.get("start_ecl")) or 0) * 1e6, "format": "sar"},
            {"label": "ECL under the scenario", "value": (_num(cards.get("scenario_ecl")) or 0) * 1e6, "format": "sar",
             "delta": (_num(cards.get("change")) or 0) * 1e6, "status": "amber"},
            {"label": "Change", "value": (_num(cards.get("change_pct")) or 0) / 100, "format": "pct"},
            {"label": "Capital impact", "value": (_num(cards.get("capital_impact")) or 0) * 1e6, "format": "sar"}]})
    wf = res.get("waterfall") or []
    if wf:
        blocks.append({"kind": "chart", "title": "ECL decomposition (SAR m)", "figure": {"data": [{
            "type": "waterfall", "x": [str(w.get("label")) for w in wf], "y": [_num(w.get("value")) for w in wf],
            "measure": ["absolute" if w.get("kind") in ("start", "end", "total") else "relative" for w in wf]}],
            "layout": {}}})
    seg = res.get("by_segment") or []
    if seg:
        blocks.append({"kind": "table", "title": "By segment", "columns": [
            {"key": "segment", "label": "Segment", "format": "text"}, {"key": "b", "label": "ECL before", "format": "sar"},
            {"key": "a", "label": "ECL after", "format": "sar"}, {"key": "c", "label": "Change", "format": "sar"}],
            "rows": [{"segment": _clean(s.get("segment"), 200), "b": (_num(s.get("ecl_before")) or 0) * 1e6,
                      "a": (_num(s.get("ecl_after")) or 0) * 1e6, "c": (_num(s.get("change")) or 0) * 1e6}
                     for s in seg[:30]]})
    return blocks


def resolve_whatif(id_: str, cookie: str | None, kind: str = "whatif-scenario") -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if kind == "whatif-thread":
        t = _get("whatif", f"/api/v1/whatif/threads/{urllib.parse.quote(id_)}", cookie)
        blocks: list[dict[str, Any]] = []
        for turn in (t.get("turns") or [])[-2:]:
            blocks.append({"kind": "heading", "level": 3, "text": _clean(turn.get("question"), 200) or "Question"})
            for b in ((turn.get("answer") or {}).get("blocks") or []):
                if b.get("type") in ("text", "commentary") and b.get("text"):
                    blocks.append({"kind": "paragraph", "text": _clean(b["text"])})
                elif b.get("type") == "result" and isinstance(b.get("result"), dict):
                    blocks.extend(_whatif_result_blocks(b["result"]))
        src = _src("whatif-thread", id_, f"What-If thread: {t.get('title', '')}", f"/what-if/thread/{id_}")
        return src, f"What-If: {_clean(t.get('title'), 150)}", blocks or [{"kind": "paragraph", "text": "No result yet."}]
    s = _get("whatif", f"/api/v1/whatif/scenarios/{urllib.parse.quote(id_)}", cookie)
    domain = s.get("domain") or "corporate"
    src = _src("whatif-scenario", id_, f"What-If: {s.get('name', '')}",
               f"/what-if?domain={domain}&open={urllib.parse.quote(id_)}")
    b0, b1 = _num(s.get("ecl_before")) or 0, _num(s.get("ecl_after")) or 0
    blocks = [{"kind": "paragraph", "text": _clean(
        f"**{s.get('name', '')}** ({s.get('method', 'delta')} method, {domain}, {s.get('period', '')}). "
        f"{s.get('description', '')} ECL moves from SAR {b0:,.1f}m to SAR {b1:,.1f}m "
        f"({(_num(s.get('change_pct')) or 0):+.1f}%).")}]
    summ = s.get("summary")
    if isinstance(summ, dict) and isinstance(summ.get("result"), dict):
        blocks.extend(_whatif_result_blocks(summ["result"]))
    elif isinstance(summ, dict):
        blocks.extend(_whatif_result_blocks(summ))
    if len(blocks) == 1:
        blocks.append({"kind": "kpis", "items": [
            {"label": "ECL before", "value": b0 * 1e6, "format": "sar"},
            {"label": "ECL after", "value": b1 * 1e6, "format": "sar", "delta": (b1 - b0) * 1e6, "status": "amber"}]})
    return src, f"What-If: {_clean(s.get('name'), 150)}", blocks


# ------------------------------------------------------------ data builder

EXTRACTS = {
    "construction-top50": ("Construction facilities, top 50 by EAD", "Construction"),
    "realestate-top50": ("Real Estate facilities, top 50 by EAD", "Real Estate"),
    "stage3-top50": ("Stage 3 facilities, top 50 by EAD", None),
}


def list_extracts(cookie: str | None) -> list[dict[str, Any]]:
    return [_src("data-extract", k, f"Data Domains: {v[0]}, {content.CORP_PERIOD}",
                 "/data-builder?domain=ews&relation=corp_exposure&period=" + content.CORP_PERIOD +
                 (f"&f={urllib.parse.quote(json.dumps([{'column': 'sector', 'op': 'eq', 'value': v[1]}]))}" if v[1] else
                  f"&f={urllib.parse.quote(json.dumps([{'column': 'stage', 'op': 'eq', 'value': 3}]))}") +
                 "&sort=ead_sar_mn&desc=1") for k, v in EXTRACTS.items()]


def resolve_extract(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if id_ not in EXTRACTS:
        raise store.NotFound(f"There is no extract {id_!r}.")
    label, sector = EXTRACTS[id_]
    e = content.corp()
    q = e[e.reporting_quarter == content.CORP_PERIOD]
    q = q[q.sector == sector] if sector else q[q.stage == 3]
    q = q.sort_values("ead_sar_mn", ascending=False).head(50)
    src = next(s for s in list_extracts(cookie) if s["id"] == id_)
    rows = [{"facility": r.facility_id, "borrower": r.borrower_id, "name": r.borrower_name, "sub": r.sub_sector,
             "product": str(r.product_type).replace("_", " "), "ead": content.sar(r.ead_sar_mn), "stage": float(r.stage),
             "pd": float(r.pd_pit_12m), "ecl": content.sar(r.ecl_sar_mn), "band": str(r.ews_band).capitalize()}
            for r in q.itertuples()]
    return src, f"Data Domains: {label}", [
        {"kind": "paragraph", "text": f"Extract from Data Domains (Early Warning domain, corporate exposure), "
                                      f"{content.CORP_PERIOD}: {label.lower()}."},
        {"kind": "table", "title": label, "columns": [
            {"key": "facility", "label": "Facility", "format": "text"}, {"key": "borrower", "label": "Borrower", "format": "text"},
            {"key": "name", "label": "Name", "format": "text"}, {"key": "sub", "label": "Sub-sector", "format": "text"},
            {"key": "product", "label": "Product", "format": "text"}, {"key": "ead", "label": "EAD", "format": "sar"},
            {"key": "stage", "label": "Stage", "format": "int"}, {"key": "pd", "label": "PD 12m", "format": "pct"},
            {"key": "ecl", "label": "ECL", "format": "sar"}, {"key": "band", "label": "EW band", "format": "text"}],
         "rows": rows}]


# --------------------------------------------------------------- workspace

_UNIT = {"sar_mn": "sar", "pct": "pct", "int": "int", "text": "text"}


def list_workspace(kind: str, cookie: str | None) -> list[dict[str, Any]]:
    if kind == "analysis":
        rows = _get("core", "/api/v1/workspace/analyses", cookie).get("analyses") or []
        return [_src("analysis", a["id"], f"Analysis: {a.get('title', '')}", f"/analyses/{a['id']}",
                     a.get("description") or "") for a in rows]
    rows = _get("core", "/api/v1/workspace/investigations", cookie).get("investigations") or []
    return [_src("investigation", i["id"], f"Investigation: {i.get('title', '')}", f"/investigations/{i['id']}",
                 i.get("summary") or "") for i in rows]


def resolve_workspace(kind: str, id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    seg = "analyses" if kind == "analysis" else "investigations"
    try:  # S3 may publish a ready section (PLAYBOOK_API.md section 8): prefer it.
        ready = _get("core", f"/api/v1/workspace/{seg}/{urllib.parse.quote(id_)}/playbook-section", cookie)
        if isinstance(ready, dict) and ready.get("section"):
            return ready["source"], ready["section"]["title"], ready["section"]["blocks"]
    except (Unavailable, store.NotFound):
        pass
    o = _get("core", f"/api/v1/workspace/{seg}/{urllib.parse.quote(id_)}", cookie)
    href = f"/{seg}/{id_}"
    if kind == "analysis":
        cols = o.get("columns") or []
        fmt = {c["key"]: _UNIT.get(c.get("unit", "text"), "text") for c in cols}

        def val(k: str, v: Any) -> Any:
            if fmt[k] == "sar":
                return (_num(v) or 0) * 1e6
            if fmt[k] == "pct":
                return (_num(v) or 0) / 100
            return v

        rows = [{c["key"]: val(c["key"], r.get(c["key"])) for c in cols} for r in (o.get("rows") or [])[:500]]
        blocks = [{"kind": "paragraph", "text": _clean(o.get("description")) or _clean(o.get("title"))}]
        if cols:
            blocks.append({"kind": "table", "title": _clean(o.get("title"), 200),
                           "columns": [{"key": c["key"], "label": _clean(c.get("label"), 120), "format": fmt[c["key"]]}
                                       for c in cols], "rows": rows,
                           "note": _clean(f"{o.get('period', '')}. Source: {o.get('source', '')}", 1000)})
            num = next((c["key"] for c in cols if fmt[c["key"]] == "sar"), None)
            if num and rows:
                blocks.append({"kind": "chart", "title": _clean(o.get("title"), 200), "figure": {"data": [{
                    "type": "bar", "x": [str(r.get(cols[0]["key"])) for r in rows[:20]],
                    "y": [round((r.get(num) or 0) / 1e6, 2) for r in rows[:20]], "marker": {"color": "#1F4E6B"}}],
                    "layout": {"yaxis": {"title": {"text": "SAR m"}}}}})
        return _src("analysis", id_, f"Analysis: {o.get('title', '')}", href), _clean(o.get("title"), 200), blocks
    blocks = [{"kind": "paragraph", "text": _clean(o.get("summary")) or _clean(o.get("title"))}]
    figs = o.get("figures") or []
    if figs:
        blocks.append({"kind": "table", "title": "Figures", "columns": [
            {"key": "label", "label": "Figure", "format": "text"}, {"key": "period", "label": "Period", "format": "text"},
            {"key": "value", "label": "Value", "format": "text"}],
            "rows": [{"label": _clean(f.get("label"), 200), "period": _clean(f.get("period"), 40),
                      "value": f"{_num(f.get('value')) or 0:,.1f} {'SAR m' if f.get('unit') == 'sar_mn' else f.get('unit', '')}"}
                     for f in figs[:30]]})
    notes = [f"{(t.get('author') or {}).get('name', '') if isinstance(t.get('author'), dict) else t.get('author', '')}: "
             f"{_clean(t.get('body'), 400)}" for t in (o.get("timeline") or [])[-8:] if t.get("body")]
    if notes:
        blocks.append({"kind": "bullets", "items": notes})
    return (_src("investigation", id_, f"Investigation: {o.get('title', '')}", href),
            f"Investigation: {_clean(o.get('title'), 150)}", blocks)


# --------------------------------------------------------------- scorecard


def list_scorecard(cookie: str | None) -> list[dict[str, Any]]:
    got = _get("scorecard", "/api/v1/scorecard/playbook/sources", cookie)
    return [{**s, "type_label": TYPE_LABEL["scorecard-validation"], "available": True} for s in got.get("sources") or []]


def resolve_scorecard(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    got = _get("scorecard", f"/api/v1/scorecard/playbook/section?id={urllib.parse.quote(id_)}", cookie)
    return got["source"], got["section"]["title"], got["section"]["blocks"]


# ------------------------------------------------------------------ lenses (PLAN_R5 Session L)

def list_lenses(cookie: str | None) -> list[dict[str, Any]]:
    got = _get("lenses", "/api/v1/lenses/playbook/sources", cookie)
    return [{**s, "type_label": TYPE_LABEL["lens"], "available": True} for s in got.get("sources") or []]


def resolve_lens(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """The Lenses service builds the section from the lens's live queries (GET /api/v1/lenses/playbook/section)."""
    got = _get("lenses", f"/api/v1/lenses/playbook/section?id={urllib.parse.quote(id_)}", cookie)
    return got["source"], got["section"]["title"], got["section"]["blocks"]


# ------------------------------------------------------------------- index

# ------------------------------------------------------------ deal desk

def resolve_dealdesk(type_: str, id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """The Deal Desk service builds the section itself (GET /api/v1/dealdesk/desk/section): the figures are the engine's."""
    out = _get("dealdesk", f"/api/v1/dealdesk/desk/section?type={urllib.parse.quote(type_)}&id={urllib.parse.quote(id_)}", cookie)
    s = out.get("source") or {}
    src = _src(type_, id_, s.get("label") or id_, s.get("href") or "/deal-desk", s.get("summary") or "")
    sec = out.get("section") or {}
    return src, _clean(sec.get("title"), 200) or src["label"], sec.get("blocks") or [{"kind": "paragraph", "text": "No analysis yet."}]


def list_dealdesk(cookie: str | None) -> list[dict[str, Any]]:
    rows = _get("dealdesk", "/api/v1/dealdesk/desk/analyses", cookie).get("analyses") or []
    return [_src("dealdesk-analysis", a["analysis_id"], f"Deal Desk: {a.get('name', '')}", f"/deal-desk/{a.get('proposal_id', '')}",
                 a.get("obligor", "")) for a in rows]


# ------------------------------------------------- CBUAE CRM compliance (R7 C3.4)

CRM_IDS = {"all": "both books", "corporate": "corporate book", "retail": "retail book"}


def list_crm(cookie: str | None) -> list[dict[str, Any]]:
    return [_src("crm-compliance", k, f"CBUAE CRM compliance summary: {v}", "/early-warning?crm=1" if k == "all" else
                 f"/early-warning?domain={k}",
                 "Breaches of the CBUAE Credit Risk Management Standards on the books, by article, with EAD, ECL and "
                 "provision shortfall.") for k, v in CRM_IDS.items()]


def resolve_crm(id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Computed in-process by the deterministic engine (no service call)."""
    from backend.regulatory import crm_checks

    if id_ not in CRM_IDS:
        raise store.NotFound("CBUAE CRM compliance: not found.")
    res = crm_checks.run()
    books = ["corporate", "retail"] if id_ == "all" else [id_]
    checks = [c for c in res["checks"] if c["book"] in books]
    rows = [r for r in res["breaches"] if r["book"] in books]
    ead = sum(r["ead_sar_mn"] for r in rows if r["entity_type"] != "book")
    short = sum(r["shortfall_sar_mn"] for r in rows)
    per = ", ".join(f"{b} {res['periods'][b]}" for b in books)
    in_breach = [c for c in checks if c["breaches"]]
    ok = [c for c in checks if not c["breaches"]]
    text = (f"Checked against the **CBUAE Credit Risk Management Standards** ({per}): **{len(rows):,} breaches** in "
            f"{len(in_breach)} of {len(checks)} checks, on {content.mn_words(ead)} of EAD"
            + (f", with a provision shortfall of {content.mn_words(short)} against the Stage 3 floors" if short else "")
            + ". " + ("Compliant: " + "; ".join(f"{c['article']} ({c['book']})" for c in ok) + "." if ok else ""))
    table = {"kind": "table", "title": "Breaches by article",
             "columns": [{"key": "article", "label": "Article", "format": "text"},
                         {"key": "check", "label": "Check", "format": "text"},
                         {"key": "book", "label": "Book", "format": "text"},
                         {"key": "breaches", "label": "Breaches", "format": "int"},
                         {"key": "ead", "label": "EAD", "format": "sar"},
                         {"key": "ecl", "label": "ECL", "format": "sar"},
                         {"key": "shortfall", "label": "Provision shortfall", "format": "sar"}],
             "rows": [{"article": c["article"], "check": c["title"], "book": c["book"], "breaches": c["breaches"],
                       "ead": content.sar(c["ead_sar_mn"]), "ecl": content.sar(c["ecl_sar_mn"]),
                       "shortfall": content.sar(c["shortfall_sar_mn"])} for c in in_breach]}
    top = {"kind": "table", "title": "Largest breaches",
           "columns": [{"key": "article", "label": "Article", "format": "text"},
                       {"key": "entity", "label": "Facility / account", "format": "text"},
                       {"key": "owner", "label": "Borrower / customer", "format": "text"},
                       {"key": "measured", "label": "Measured", "format": "text"},
                       {"key": "required", "label": "Required", "format": "text"},
                       {"key": "ead", "label": "EAD", "format": "sar"}],
           "rows": [{"article": r["article"], "entity": r["entity_id"], "owner": r["borrower_id"],
                     "measured": f"{r['measured']} {r['unit']}", "required": f"{r['required']} {r['unit']}",
                     "ead": content.sar(r["ead_sar_mn"])}
                    for r in sorted((r for r in rows if r["entity_type"] != "book"), key=lambda r: -r["ead_sar_mn"])[:10]]}
    src = _src("crm-compliance", id_, f"CBUAE CRM compliance summary: {CRM_IDS[id_]}",
               "/early-warning?crm=1" if id_ == "all" else f"/early-warning?domain={id_}")
    return src, "CBUAE CRM compliance", [{"kind": "paragraph", "text": text}, table, top]


# ------------------------------------- Workspace documents and projects (Deal Desk edition's picker)

def list_workspace_docs(kind: str, cookie: str | None) -> list[dict[str, Any]]:
    if kind == "project":
        rows = _get("core", "/api/v1/workspace/projects", cookie).get("projects") or []
        return [_src("project", p["id"], f"Project: {p.get('name', '')}", f"/projects/{p['id']}", p.get("description") or "")
                for p in rows]
    rows = _get("core", "/api/v1/workspace/documents", cookie).get("documents") or []
    return [_src("document", d_["id"], f"Document: {d_.get('title', '')}", f"/documents/{d_['id']}", d_.get("summary") or "")
            for d_ in rows]


def resolve_workspace_doc(kind: str, id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if kind == "project":
        o = _get("core", f"/api/v1/workspace/projects/{urllib.parse.quote(id_)}", cookie)
        blocks: list[dict[str, Any]] = [{"kind": "paragraph", "text": _clean(o.get("description")) or _clean(o.get("name"))}]
        tasks = [f"{_clean(t.get('title'), 200)} ({_clean(t.get('status'), 20)})" for t in (o.get("tasks") or [])[:20]]
        if tasks:
            blocks.append({"kind": "bullets", "items": tasks})
        return (_src("project", id_, f"Project: {o.get('name', '')}", f"/projects/{id_}"),
                f"Project: {_clean(o.get('name'), 150)}", blocks)
    o = _get("core", f"/api/v1/workspace/documents/{urllib.parse.quote(id_)}", cookie)
    blocks = [{"kind": "paragraph", "text": _clean(o.get("summary")) or _clean(o.get("title"))}]
    for sec in (o.get("sections") or [])[:12]:
        blocks.append({"kind": "heading", "text": _clean(sec.get("heading"), 200)})
        blocks.append({"kind": "paragraph", "text": _clean(sec.get("body"))})
    return _src("document", id_, f"Document: {o.get('title', '')}", f"/documents/{id_}"), _clean(o.get("title"), 200), blocks


LISTERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "crm-compliance": list_crm,
    "cockpit-thread": list_cockpit, "attention-item": list_attention, "early-warning-list": list_ews,
    "borrower": list_borrowers, "whatif-scenario": list_whatif, "data-extract": list_extracts,
    "analysis": lambda c: list_workspace("analysis", c), "investigation": lambda c: list_workspace("investigation", c),
    "scorecard-validation": list_scorecard, "dealdesk-analysis": list_dealdesk, "lens": list_lenses,
    "document": lambda c: list_workspace_docs("document", c), "project": lambda c: list_workspace_docs("project", c),
}
FULL_ORDER = ["cockpit-thread", "investigation", "attention-item", "early-warning-list", "borrower", "whatif-scenario",
              "data-extract", "analysis", "scorecard-validation", "dealdesk-analysis", "lens", "crm-compliance"]
#: Deal Desk edition: Deal Desk first; nothing of Early Warning, What-If, Borrower 360, Lenses, Scorecard or the
#: Cockpit's attention items (PLAN_DEALDESK_EDITION Round C).
DEALDESK_ORDER = ["dealdesk-analysis", "investigation", "analysis", "document", "project"]
ORDER = FULL_ORDER


def order() -> list[str]:
    from backend.v5common.edition import is_dealdesk
    return DEALDESK_ORDER if is_dealdesk() else FULL_ORDER


def sources(cookie: str | None, type_: str = "", q: str = "") -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for t in order():
        if type_ and t != type_ and not (type_ == "whatif-scenario" and t == "whatif-thread"):
            continue
        try:
            got = list_borrowers(cookie, q) if t == "borrower" else LISTERS[t](cookie)
            out.extend(got)
        except (Unavailable, store.NotFound) as exc:
            unavailable.append({"type": t, "type_label": TYPE_LABEL[t], "reason": f"Not available: {exc}."})
    if q:
        words = [w for w in re.split(r"\W+", q.lower()) if len(w) > 2]
        if words:
            scored = [(sum(w in (s["label"] + " " + s.get("summary", "") + " " + s["id"]).lower() for w in words), s)
                      for s in out]
            out = [s for n, s in sorted(scored, key=lambda x: -x[0]) if n > 0] or out
    return {"sources": out, "unavailable": unavailable}


def resolve(type_: str, id_: str, cookie: str | None) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    try:
        if type_ == "cockpit-thread":
            src, title, blocks = resolve_cockpit(id_, cookie)
        elif type_ == "attention-item":
            src, title, blocks = resolve_attention(id_, cookie)
        elif type_ == "early-warning-list":
            src, title, blocks = resolve_ews(id_, cookie)
        elif type_ == "borrower":
            src, title, blocks = resolve_borrower(id_, cookie)
        elif type_ in ("whatif-scenario", "whatif-thread"):
            src, title, blocks = resolve_whatif(id_, cookie, type_)
        elif type_ == "data-extract":
            src, title, blocks = resolve_extract(id_, cookie)
        elif type_ in ("analysis", "investigation"):
            src, title, blocks = resolve_workspace(type_, id_, cookie)
        elif type_ == "scorecard-validation":
            src, title, blocks = resolve_scorecard(id_, cookie)
        elif type_ in ("dealdesk-proposal", "dealdesk-analysis"):
            src, title, blocks = resolve_dealdesk(type_, id_, cookie)
        elif type_ == "lens":
            src, title, blocks = resolve_lens(id_, cookie)
        elif type_ == "crm-compliance":
            src, title, blocks = resolve_crm(id_, cookie)
        elif type_ in ("document", "project"):
            src, title, blocks = resolve_workspace_doc(type_, id_, cookie)
        else:
            raise store.Invalid(f"{type_!r} cannot be imported.")
    except Unavailable as exc:
        raise store.Invalid(f"{TYPE_LABEL.get(type_, type_)} cannot be imported right now: {exc}.") from exc
    src = {k: v for k, v in src.items() if k not in ("type_label", "available")}
    return src, title, blocks
