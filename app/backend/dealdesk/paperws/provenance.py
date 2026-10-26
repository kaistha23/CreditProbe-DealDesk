"""Round T: the provenance of every section and every important point of a paper (extends R16's figure trace).

    pv = build(paper, versions=[...], rules=[...])
    pv["sections"]   [{key, heading, label, sources: [evidence], points: [{id, block, item, text, evidence: [evidence], traced}],
                       rules: [...], edits: [...]}]
    pv["summary"]    {points, with_figures, figures_traced, untraced: [...], documents, relations, engine, rules, edits}

An evidence item names where a point comes from, one of:

    document   an uploaded document: {doc_id, label, page?, status?}               (intake / the customer's pack / dd_document)
    data       a bank data relation and its row: {relation, domain, row, column?, value?, period}
    engine     an engine result: {engine, label, value}                             (economics, approval authority, structure, capacity)
    rule       an analyst's or the bank's rule (Round K): {rule_id, text, author, at, scope}
    analyst    an instruction applied in the workspace: {author, at, instruction, version}
    rm         the RM's ask or notes (business request)

The proposal's points are matched to the deal's Data Domains rows (figure values at 0-2 decimals, quoted text), the engine's
results and the bank's document checklist; the business request's points are matched to R16 b's figure list, where every figure
already names its document or row. Nothing here is computed for the paper: it only says where each printed point came from.
"""
from __future__ import annotations

import re
import time
from typing import Any

from backend.dealdesk.paperws import figures as FG

DOC_ID = re.compile(r"\(([A-Z]{1,3}\d*-\d{1,3}(?:[;,]\s*[A-Z]{1,3}\d*-\d{1,3})*)\)")
PAGE = re.compile(r"\bp(?:age|\.)\s?(\d{1,3})\b", re.I)
SKIP_COLS = re.compile(r"(^|_)(id|seq|version|rel_version|quarter|year|month|n|rank|notch|point)$|_at$|_date$|^published|^reporting")
_CACHE: dict[str, tuple[float, Any]] = {}
TTL = 120.0


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    v = fn()
    _CACHE[key] = (time.time(), v)
    return v


# ------------------------------------------------------------------------------------------------- points of a section

def points(section: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for bi, b in enumerate(section.get("blocks") or []):
        t = b.get("t")
        if t == "p":
            out.append({"id": f"{section['key']}:{bi}", "block": bi, "item": None, "kind": "p", "text": b.get("text") or ""})
        elif t in ("bullets", "numbered"):
            for ii, x in enumerate(b.get("items") or []):
                out.append({"id": f"{section['key']}:{bi}:{ii}", "block": bi, "item": ii, "kind": "item", "text": str(x)})
        elif t in ("table", "kv"):
            out.append({"id": f"{section['key']}:{bi}", "block": bi, "item": None, "kind": t, "text": "\n".join(FG.block_texts(b)),
                        "source": b.get("source") or ""})
    return out


def _clean(t: str) -> str:
    return str(t).replace("**", "").replace("__", "")


# ------------------------------------------------------------------------------------------------- the proposal's evidence

def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return str(v)


def _deal_index(pid: str) -> dict[str, Any]:
    from backend.dealdesk.house_style.bankform import ctx
    D = ctx.load(pid, price=False)
    nums: dict[float, list[dict[str, Any]]] = {}
    texts: list[tuple[str, dict[str, Any]]] = []
    docs: list[dict[str, Any]] = []
    rels: dict[str, str] = {}
    for rel, rows in D.data.items():
        if not rows:
            continue
        rels[rel] = D.src(rel)
        for r in rows[:400]:
            src = r.get("_src") if isinstance(r.get("_src"), dict) else {}
            base = {"kind": "data", "relation": src.get("relation") or rel, "domain": src.get("domain") or "", "row": src.get("row") or "",
                    "period": src.get("period") or ""}
            for c, v in r.items():
                if c == "_src" or SKIP_COLS.search(c):
                    continue
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    fv = float(v)
                    if abs(fv) < 0.05:
                        continue
                    ev = {**base, "column": c, "value": fv, "label": f"{base['relation']}.{c} = {_fmt(fv)}"}
                    for x in FG._forms(fv, ratio=abs(fv) <= 1.5):  # noqa: SLF001
                        nums.setdefault(x, []).append(ev)
                elif isinstance(v, str) and len(v) >= 25:
                    texts.append((v.strip()[:160].lower(), {**base, "column": c, "label": f"{base['relation']}.{c}"}))
        if rel == "dd_document":
            for r in rows:
                lab = r.get("doc_label") or r.get("name") or r.get("doc_type")
                if lab:
                    docs.append({"kind": "document", "doc_id": str(r.get("document_id") or ""), "label": str(lab), "status": r.get("status") or "",
                                 "date": str(r.get("received_date") or r.get("doc_date") or ""), "page": r.get("page"),
                                 "file": r.get("file_ref") or "", "relation": "dd_document"})
    return {"nums": nums, "texts": texts, "docs": docs, "rels": rels}


def _engine(paper: dict[str, Any]) -> list[dict[str, Any]]:
    f = paper.get("feed") or {}
    st = f.get("structure") or {}
    eng = (f.get("sources") or {})
    out = []
    for k, lab, src in (("raroc", "RAROC (lifetime) on the selected structure", eng.get("economics")),
                        ("hurdle", "RAROC hurdle", eng.get("economics")), ("sva", "SVA (lifetime)", eng.get("economics")),
                        ("capacity", "Capacity (SAR m)", "session e capacity engine")):
        if isinstance(f.get(k), (int, float)):
            out.append({"kind": "engine", "engine": src or "Deal Desk engine", "label": lab, "value": f[k], "field": k})
    tot = paper.get("totals") or {}
    for k in ("existing", "outstanding", "proposed"):
        if isinstance(tot.get(k), (int, float)) and tot[k]:
            out.append({"kind": "engine", "engine": "bank-form writer: sum of the deal's facility rows (dd_facility_limit / dd_proposal_facility)",
                        "label": f"Total {k} limits (SAR m) = {_fmt(tot[k])}", "value": tot[k], "field": f"total_{k}"})
    if f.get("approval"):
        out.append({"kind": "engine", "engine": eng.get("approval") or "approval authority", "label": f"Approval authority: {f['approval']}",
                    "value": f["approval"], "field": "approval", "rule": f.get("approval_rule")})
    for k, v in (st.get("terms") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k in ("amount", "tenor_years", "margin_bps", "upfront_fee_bps", "cash_margin_pct",
                                                                              "commitment_fee_bps", "utilisation_pct", "guarantee_coverage_pct"):
            out.append({"kind": "engine", "engine": f"structure: {st.get('label') or st.get('key')} ({st.get('source') or ''})".strip(),
                        "label": f"{k} = {_fmt(v)}", "value": v, "field": k})
    return out


AS_PER = re.compile(r"\b(?:as per|per|in|from)\s+((?:dd|b360|bureau|rel|corp|dep|net|other)_[a-z0-9_]+)\b")
ENGINE_SECTIONS = {"action", "facilities", "cp_selected", "cp_findings", "cp_raroc", "cp_stress", "recommendation", "header"}


def _proposal_evidence(paper: dict[str, Any], section: dict[str, Any], pt: dict[str, Any], idx: dict[str, Any],
                       engine: list[dict[str, Any]], section_rels: set[str]) -> list[dict[str, Any]]:
    text = _clean(pt["text"])
    low = text.lower()
    ev: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(e: dict[str, Any]) -> None:
        k = f"{e.get('kind')}|{e.get('label')}|{e.get('row', '')}"
        if k not in seen and len(ev) < 6:
            seen.add(k)
            ev.append(e)

    for n in FG.numbers(text, dates=False):
        if abs(n) < 0.05 or (float(n).is_integer() and abs(n) < 4):
            continue
        key = round(abs(n), 4)
        eng = [e for e in engine if isinstance(e.get("value"), (int, float)) and key in FG._forms(float(e["value"]), ratio=abs(float(e["value"])) <= 1.5)]  # noqa: SLF001
        cands = idx["nums"].get(key, [])
        mine = [c for c in cands if c["relation"] in section_rels]
        if section["key"] in ENGINE_SECTIONS:
            pick = eng[:1] + mine[:2]
        else:
            pick = mine[:2] or eng[:1]
        if not pick and cands and not float(n).is_integer():
            pick = cands[:1]
        for e in pick:
            add({**e, "printed": _fmt(n)})
    for rel in AS_PER.findall(text):
        add({"kind": "data", "relation": rel, "domain": "", "row": "", "label": f"{rel} (named in the text)"})
    for t, e in idx["texts"]:
        if len(t) >= 25 and t[:60] in low:
            add(e)
    for d in idx["docs"]:
        if d["label"].lower() in low:
            add(d)
    if pt["kind"] in ("table", "kv") and pt.get("source"):
        add({"kind": "data", "label": str(pt["source"]), "relation": _rel_of(str(pt["source"])), "row": "", "domain": ""})
    return ev


def _rel_of(s: str) -> str:
    m = re.search(r"\b((?:dd|b360|bureau|rel|other|dep|net)_[a-z0-9_]+)\b", s)
    return m.group(1) if m else ""


# ------------------------------------------------------------------------------------------------- the request's evidence

def source_evidence(source: str) -> dict[str, Any]:
    """One R16 b figure source string -> an evidence item."""
    s = str(source or "")
    ids = DOC_ID.search(s)
    page = PAGE.search(s)
    if ids:
        return {"kind": "document", "doc_id": ids.group(1), "label": DOC_ID.sub("", s).strip(" ·"), "page": int(page.group(1)) if page else None}
    if s.lower().startswith(("rm's", "rm ", "as per rm")):
        return {"kind": "rm", "label": s}
    rel = _rel_of(s)
    if rel:
        parts = [x.strip() for x in s.split("·")]
        row = " · ".join(x for x in parts if "=" in x)
        period = next((x for x in parts if re.match(r"^\d{4}Q\d$", x)), "")
        return {"kind": "data", "relation": rel, "domain": parts[0] if parts else "", "row": row, "period": period, "label": s}
    if "tariff" in s.lower() or "policy" in s.lower():
        return {"kind": "rule", "label": s, "text": s, "author": "the Bank", "at": "", "scope": "bank"}
    return {"kind": "data", "relation": "", "row": "", "label": s}


def _request_evidence(paper: dict[str, Any], section: dict[str, Any], pt: dict[str, Any]) -> list[dict[str, Any]]:
    low = _clean(pt["text"]).lower()
    ev: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in paper.get("figures") or []:
        if f.get("section") != section["key"]:
            continue
        txt = str(f.get("text") or "").strip().lower()
        if len(txt) < 2 or txt not in low:
            continue
        e = {**source_evidence(f.get("source") or ""), "printed": f.get("text"), "figure": f.get("label")}
        k = f"{e['kind']}|{e.get('label')}|{e.get('doc_id', '')}|{f.get('label')}"
        if k not in seen and len(ev) < 6:
            seen.add(k)
            ev.append(e)
    for n in paper.get("notes_used") or []:
        if n.get("section") == section.get("heading") and str(n.get("text") or "")[:40].lower() in low:
            ev.append({"kind": "rm", "label": f"RM's note: {n['text']}", "topic": n.get("topic")})
    return ev


# ------------------------------------------------------------------------------------------------- the whole paper

def _edits_by_section(versions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for v in versions or []:
        ch = v.get("change") or {}
        for s in ch.get("sections") or []:
            out.setdefault(s["key"], []).append({"kind": "analyst", "version": v["n"], "author": v.get("author") or "", "at": v.get("at"),
                                                 "instruction": v.get("instruction") or "", "action": v.get("action"), "status": ch.get("status"),
                                                 "label": f"v{v['n']} · {v.get('instruction') or v.get('action')}"})
    return out


def _engine_text(section: dict[str, Any], pt: dict[str, Any]) -> bool:
    """Is this point the engine's own text (not added or reworded by an instruction)?"""
    eb = section.get("engine_blocks")
    if eb is None:
        return True
    want = _clean(pt["text"]).strip()
    for b in eb:
        if any(_clean(t).strip() == want for t in FG.block_texts(b)):
            return True
    return False


def build(paper: dict[str, Any], versions: list[dict[str, Any]] | None = None, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    kind = paper.get("doc_kind") or ("request" if paper.get("request_id") else "proposal")
    pid = paper.get("proposal_id") or ""
    idx: dict[str, Any] = {"nums": {}, "texts": [], "docs": [], "rels": {}}
    engine: list[dict[str, Any]] = []
    spec_rels: dict[str, set[str]] = {}
    if kind == "proposal" and pid:
        try:
            idx = _cached(f"deal|{pid}", lambda: _deal_index(pid))
        except Exception:  # noqa: BLE001 - no deal file: the sections' own source lines stand
            pass
        engine = _engine(paper)
        try:
            from backend.dealdesk.house_style.bankform import registry
            spec_rels = {k: set(s.needs) | set(s.uses) for k, s in registry.BY_KEY.items()}
        except Exception:  # noqa: BLE001
            spec_rels = {}
    edits = _edits_by_section(versions or [])
    rules = rules or []
    out_secs = []
    n_pts = n_fig = n_traced = 0
    untraced: list[dict[str, Any]] = []
    kinds: dict[str, int] = {}
    for s in paper.get("sections") or []:
        rels = spec_rels.get(s["key"], set())
        # the relations the writer reads (bankform) normalised to the names rows carry
        rels_rows = rels | {"dd_deal" if r == "dd_proposal" else r for r in rels} | {"dd_obligor_financials" for r in rels if r == "dd_financials_detail"} \
            | {"dd_collateral_guarantee" for r in rels if r == "dd_security"}
        pts = []
        for pt in points(s):
            ev = _request_evidence(paper, s, pt) if kind == "request" else _proposal_evidence(paper, s, pt, idx, engine, rels_rows)
            if not _engine_text(s, pt):
                last = (edits.get(s["key"]) or [{}])[-1]
                ev.insert(0, {"kind": "analyst", "label": f"Written by an instruction: {last.get('instruction') or 'edit'}", **{k: last.get(k) for k in ("author", "at", "version", "instruction")}})
            has_fig = bool([n for n in FG.numbers(_clean(pt["text"]), dates=False) if abs(n) >= 0.05]) and pt["kind"] in ("p", "item")
            traced = any(e["kind"] in ("data", "engine", "document", "rm") for e in ev)
            n_pts += 1
            if has_fig:
                n_fig += 1
                if traced:
                    n_traced += 1
                else:
                    untraced.append({"section": s["key"], "point": pt["id"], "text": _clean(pt["text"])[:160]})
            for e in ev:
                kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
            pts.append({**pt, "text": pt["text"], "evidence": ev, "traced": traced, "has_figure": has_fig})
        sources: list[dict[str, Any]] = []
        if kind == "proposal":
            for r in sorted(rels):
                if r in idx["rels"]:
                    sources.append({"kind": "data", "relation": r, "label": idx["rels"][r]})
            if s["key"] in ENGINE_SECTIONS:
                eng = (paper.get("feed") or {}).get("sources") or {}
                for k, v in eng.items():
                    if v and v != "not available":
                        sources.append({"kind": "engine", "engine": v, "label": f"{k}: {v}"})
            for lab in s.get("sources") or []:
                if not any(x.get("label") == lab for x in sources):
                    sources.append({"kind": "data", "relation": _rel_of(lab), "label": lab})
        else:
            seen = set()
            for f in paper.get("figures") or []:
                if f.get("section") == s["key"] and f.get("source") not in seen:
                    seen.add(f.get("source"))
                    sources.append(source_evidence(f.get("source") or ""))
        srules = [dict(r, kind="rule") for r in rules if not r.get("section") or r.get("section") == s["key"]]
        out_secs.append({"key": s["key"], "heading": s.get("heading"), "n": s.get("n"), "voice": s.get("voice"), "sources": sources,
                         "points": pts, "rules": srules, "edits": edits.get(s["key"], []), "gaps": s.get("gaps") or []})
    docs = sorted({(e.get("doc_id") or "", e.get("label") or "") for s in out_secs for p in s["points"] for e in p["evidence"] if e["kind"] == "document"})
    rels_used = sorted({e.get("relation") for s in out_secs for p in s["points"] for e in p["evidence"] if e["kind"] == "data" and e.get("relation")})
    summary = {"points": n_pts, "with_figures": n_fig, "figures_traced": n_traced, "untraced": untraced[:50], "by_kind": kinds,
               "documents": [{"doc_id": a, "label": b} for a, b in docs], "relations": rels_used,
               "engine": sorted({e.get("engine") for e in engine if e.get("engine")}), "rules": rules,
               "edits": len({e["version"] for v in edits.values() for e in v})}
    return {"kind": kind, "proposal_id": pid, "customer": paper.get("customer"), "sections": out_secs, "summary": summary,
            "plain_words": plain_words(summary, kind)}


def plain_words(sm: dict[str, Any], kind: str) -> list[str]:
    doc = "business request" if kind == "request" else "credit proposal"
    return [f"This {doc} has {sm['points']} points; {sm['with_figures']} carry a figure and {sm['figures_traced']} of them are traced to their source.",
            f"Sources: {len(sm['documents'])} documents, {len(sm['relations'])} bank data relations, {len(sm['engine'])} engine results, "
            f"{len(sm['rules'])} rules.",
            f"{sm['edits']} change{'s' if sm['edits'] != 1 else ''} made by instruction, each with who, when and the instruction.",
            "Click any point to see its evidence."]


def annex_rows(pv: dict[str, Any], limit_per_section: int = 14) -> list[tuple[str, str, str, str]]:
    """(section, point, evidence kind, evidence) rows for the Word annex."""
    rows = []
    for s in pv["sections"]:
        label = f"{s['n']}. {s['heading']}" if s.get("n") else str(s["heading"])
        for src in s["sources"][:6]:
            rows.append((label, "Section", src["kind"], describe(src)))
        for r in s["rules"]:
            rows.append((label, "Section", "rule", describe(r)))
        k = 0
        for p in s["points"]:
            for e in p["evidence"][:2]:
                if k >= limit_per_section:
                    break
                rows.append((label, _clean(p["text"])[:110], e["kind"], describe(e)))
                k += 1
    return rows


def describe(e: dict[str, Any]) -> str:
    k = e.get("kind")
    if k == "document":
        pg = f", page {e['page']}" if e.get("page") else ""
        st = f" ({e['status']})" if e.get("status") else ""
        return f"{e.get('label') or ''}{' [' + e['doc_id'] + ']' if e.get('doc_id') else ''}{pg}{st}"
    if k == "data":
        row = f" · {e['row']}" if e.get("row") else ""
        col = f" · {e['column']}" if e.get("column") else ""
        if e.get("relation") and e.get("column"):
            val = f" = {_fmt(e['value'])}" if e.get("value") is not None else ""
            return f"{e.get('domain') or 'Data Domains'} · {e['relation']}{row}{col}{val}"
        return str(e.get("label") or e.get("relation") or "")
    if k == "engine":
        return f"{e.get('label')} ({e.get('engine')})"
    if k == "rule":
        who = ", ".join(x for x in (e.get("author"), str(e.get("at") or "")[:10], e.get("scope")) if x)
        return f"{e.get('text') or e.get('label')}" + (f" ({who})" if who else "")
    if k == "analyst":
        at = time.strftime("%d %b %Y %H:%M", time.gmtime(e["at"])) if isinstance(e.get("at"), (int, float)) else str(e.get("at") or "")
        return f"v{e.get('version')} · {e.get('author') or 'analyst'} · {at} · “{e.get('instruction') or ''}”"
    return str(e.get("label") or "")
