"""The house-style operations behind the API (and the tests): profile, corpus, drafts, edits, scoring, export."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk.house_style import corpus, draft as dr, facts as factsmod, fidelity, profile as prof, store


class NotFound(KeyError):
    pass


def _meta(pid: str) -> dict[str, Any]:
    try:
        return factsmod.memo_meta(pid)
    except KeyError:
        raise NotFound(f"No proposal {pid}.") from None


def profile_view(bank: str = "", kind: str = "", segment: str = "", proposal_id: str = "") -> dict[str, Any]:
    st = store.state()
    if proposal_id:
        m = _meta(proposal_id)
        bank, kind, segment = prof.house_for(st, m["bank"], m["segment"]), m["kind"], m["segment"]
    v = prof.view(st, bank or "house-uae", kind or "increase", segment or "contractor")
    return {"profile": v, "guide": prof.guide(v), "groups": prof.groups(st),
            "banks": [{"bank": k, "label": lab} for k, lab in corpus.BANKS.items()], "kinds": list(corpus.KINDS),
            "segments": list(corpus.SEGMENTS)}


def corpus_list() -> dict[str, Any]:
    docs = store.corpus_docs()
    rows = [{"doc_id": d["doc_id"], "title": d["title"], "source": d["source"], "bank": d["bank"], "bank_label": d["bank_label"],
             "kind": d["kind"], "segment": d["segment"], "role": prof.role_of(d), "weight": d["weight"], "primary": d.get("primary", False),
             "sections": len(d["sections"])} for d in docs]
    ex = [r for r in rows if r["source"] == "exemplar"]
    return {"documents": rows, "n": len(rows), "exemplars": len(ex),
            "summary": f"{len(rows)} proposals in the corpus" + (f", {len(ex)} anonymised exemplar(s) as primary" if ex else "")}


def ingest(name: str, data: bytes, bank: str = "house-uae", kind: str | None = None, segment: str | None = None) -> dict[str, Any]:
    st = store.state()
    m_before = None
    doc = corpus.ingest_upload(name, data, bank, kind, segment)
    key = prof.group_keys(doc["bank"], doc["kind"], doc["segment"])[0]
    if key in st["groups"]:
        m_before = st["groups"][key]["n"]
    store.record({"type": "doc", "doc": doc, "at": _now()})
    v = prof.view(store.state(), doc["bank"], doc["kind"], doc["segment"])
    return {"doc_id": doc["doc_id"], "title": doc["title"], "bank": doc["bank"], "kind": doc["kind"], "segment": doc["segment"],
            "sections": [s["heading"] or s["key"] for s in doc["sections"]], "profile_group": v["group"], "documents_before": m_before or 0,
            "documents_after": v["documents"], "summary": f"{name} added to the corpus: {len(doc['sections'])} sections; "
                                                          f"profile {v['group']} now from {v['documents']} documents."}


def rebuild() -> dict[str, Any]:
    store.reset()
    st = store.state()
    return {"groups": prof.groups(st), "events": st.get("events", 0)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_draft(pid: str, sections: list[str] | None = None, use_model: bool = True, by: str = "", bank: str | None = None) -> dict[str, Any]:
    _meta(pid)
    if sections is not None and (not isinstance(sections, list) or not all(isinstance(x, str) for x in sections)):
        raise ValueError("sections must be a list of section keys.")
    if bank and bank not in corpus.BANKS:
        bank = None
    from backend.dealdesk.rules import hook as rules_hook  # Round K: the writer's rules, to the model and applied after
    with rules_hook.drafting(by, "proposal"):
        d = dr.draft(pid, store.state(), store.index(), use_model=use_model, sections=sections, bank=bank)
    d["created_by"] = by
    return store.save(rules_hook.on_house_draft(d, by))


def get_draft(did: str) -> dict[str, Any]:
    d = store.get(did)
    if d is None:
        raise NotFound(f"No draft {did}.")
    return d


def latest(pid: str) -> dict[str, Any] | None:
    return store.latest(pid)


def _view_for(d: dict[str, Any]) -> dict[str, Any]:
    m = d["meta"]
    return prof.view(store.state(), m["bank"], m["kind"], m["segment"])


def _rescore(d: dict[str, Any]) -> dict[str, Any]:
    v = _view_for(d)
    d.update(fidelity.assess(d, v, store.state()))
    for s in d["sections"]:
        if s.get("figure_checks"):
            for msg in s["figure_checks"]:
                d["lint"].append({"id": f"L{len(d['lint']) + 1}", "rule": "uncited_figure", "severity": "major", "section": s["key"],
                                  "message": msg, "excerpt": "", "suggestion": "Cite the figure's source or take it from the data."})
    d["profile"]["edits_learned"] = v["edits_learned"]
    d["methods"] = sorted({s["method"].split(" (")[0] for s in d["sections"]})
    return d


def _section(d: dict[str, Any], key: str) -> tuple[int, dict[str, Any]]:
    for i, s in enumerate(d["sections"]):
        if s["key"] == key:
            return i, s
    raise NotFound(f"No section {key} in draft {d['draft_id']}.")


class _F(factsmod.Facts):
    pass


def _facts_obj(d: dict[str, Any]) -> factsmod.Facts:
    F = factsmod.Facts(d["meta"]["currency"], d.get("style"))
    F.items = d["facts"]
    for f in d["facts"]:
        F.by_section.setdefault(f["section"], []).append(f["id"])
    return F


def regenerate(did: str, key: str, use_model: bool = True) -> dict[str, Any]:
    with store.draft_lock(did):
        return _regenerate(did, key, use_model)


def _regenerate(did: str, key: str, use_model: bool = True) -> dict[str, Any]:
    d = get_draft(did)
    i, s = _section(d, key)
    v = _view_for(d)
    F = _facts_obj(d)
    from backend.dealdesk.rules import hook as rules_hook  # Round K: the rules again on the redrafted section
    if key not in dr.TEMPLATES:
        raise ValueError(f"{s['heading']} was added by a rule for the analyst to write; edit it instead.")
    with rules_hook.drafting(d.get("created_by") or "", "proposal"):
        new = dr.draft_section({"key": key, "heading": s["heading"], "voice": s.get("voice", "business")}, F, v, store.index(), d["meta"],
                               use_model=use_model, exclude={d["proposal_id"], f"{d['proposal_id']}-OPINION"}, variant=s.get("version", 1))
    new["version"] = s.get("version", 1) + 1
    d["sections"][i] = new
    d = rules_hook.on_house_draft(d, d.get("created_by") or "")
    return store.save(_rescore(d))


def _parse_text(text: str) -> tuple[list[str], list[str]]:
    paras, bullets = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^[-*•]\s+", line):
            bullets.append(re.sub(r"^[-*•]\s+", "", line))
        else:
            paras.append(line)
    return paras, bullets


def _strings(v: Any, name: str) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{name} must be a list of strings.")
    return [x for x in v if x.strip()]


def edit_section(did: str, key: str, body: dict[str, Any], by: str = "") -> dict[str, Any]:
    """An RM edit (and/or acceptance). The diff feeds the profile: phrases written are credited, phrases removed avoided."""
    if not isinstance(body, dict):
        raise ValueError("The body must be an object.")
    if "text" in body and not isinstance(body["text"], str):
        raise ValueError("text must be a string.")
    if body.get("accept") is not None and not isinstance(body["accept"], bool):
        raise ValueError("accept must be true or false.")
    with store.draft_lock(did):
        return _edit_section(did, key, body, by)


def _edit_section(did: str, key: str, body: dict[str, Any], by: str = "") -> dict[str, Any]:
    d = get_draft(did)
    i, s = _section(d, key)
    before = dr.CITE.sub("", dr.section_text(s)).strip()
    changed = False
    if "text" in body or "paragraphs" in body or "bullets" in body:
        if "text" in body:
            paras, bullets = _parse_text(str(body["text"]))
        else:
            paras, bullets = _strings(body.get("paragraphs") or [], "paragraphs"), _strings(body.get("bullets") or [], "bullets")
        if paras != s["paragraphs"] or bullets != s["bullets"]:
            s["paragraphs"], s["bullets"] = paras, bullets
            s["edited"], s["method"], changed = True, "RM edit", True
            s["version"] = s.get("version", 1) + 1
            all_facts = d["facts"]
            s["figure_checks"] = [p for p in dr.check(paras + bullets, all_facts) if not p.startswith("citation")]
            cited = set(dr.CITE.findall(" ".join(paras + bullets))) | set((s.get("table") or {}).get("cites", []))
            s["citations"] = [f for f in all_facts if f["id"] in cited]
    newly_accepted = bool(body.get("accept")) and s.get("status") != "accepted"
    if body.get("accept") is not None:
        s["status"] = "accepted" if body.get("accept") else "draft"
    s["edited_by"], s["edited_at"] = by, _now()
    m = d["meta"]
    after = dr.CITE.sub("", dr.section_text(s)).strip()
    if changed:
        store.record({"type": "edit", "bank": m["bank"], "kind": m["kind"], "segment": m["segment"], "section": key, "role": "business",
                      "voice": s.get("voice", "business"), "before": before, "after": after, "draft_id": did, "by": by, "at": _now()})
    elif newly_accepted and s.get("accept_learned") != s.get("version", 1):
        s["accept_learned"] = s.get("version", 1)  # an accept teaches once per section version, however often it is toggled
        store.record({"type": "edit", "bank": m["bank"], "kind": m["kind"], "segment": m["segment"], "section": key, "role": "business",
                      "voice": s.get("voice", "business"), "before": "", "after": after, "weight": 0.5, "draft_id": did, "by": by,
                      "at": _now(), "accepted": True})
    d["sections"][i] = s
    return store.save(_rescore(d))


def score(did: str) -> dict[str, Any]:
    d = _rescore(get_draft(did))
    store.save(d)
    return {"draft_id": did, "score": d["score"], "lint": d["lint"], "sections": [{"key": s["key"], "score": s.get("score")} for s in d["sections"]]}


def docx(did: str, by: str = "") -> tuple[bytes, str]:
    from backend.dealdesk.house_style import export
    return export.build(get_draft(did), by)


_HELD: dict[str, Any] = {}


def held_out(pid: str = "DD-05") -> dict[str, Any]:
    """P3 test, as the API reports it: hold one house memo out, rebuild the profile without it, redraft it from its facts and
    score the redraft against the band of the bank's own memos."""
    _meta(pid)
    key = f"{pid}|{store.state_key()}"
    if key in _HELD:
        return _HELD[key]
    docs = [d for d in store.corpus_docs() if d["doc_id"] not in (pid, f"{pid}-OPINION")]
    st = prof.build(docs)
    import backend.dealdesk.house_style.retrieve as rt
    idx = rt.Index(docs)
    d = dr.draft(pid, st, idx, use_model=False, with_engine=False)
    meta = d["meta"]
    v = prof.view(st, meta["bank"], meta["kind"], meta["segment"])
    redraft = fidelity.score_doc(dr.as_doc(d), v)
    b = fidelity.band(docs, meta["bank"])
    original = next((x for x in store.corpus_docs() if x["doc_id"] == pid), None)
    orig = fidelity.score_doc(original, v) if original else None
    out = {"held_out": pid, "profile_group": v["group"], "redraft_score": redraft["total"], "original_score": orig["total"] if orig else None,
           "band": {k: b[k] for k in ("low", "high", "mean", "n")}, "within_band": redraft["total"] >= b["low"],
           "summary": f"{pid} held out and redrafted from its facts: {redraft['total']} against the house band "
                      f"{b['low']}–{b['high']} ({b['n']} memos, leave-one-out)."}
    _HELD[key] = out
    return out


def _section_score(doc: dict[str, Any], key: str, v: dict[str, Any]) -> float | None:
    one = {**doc, "sections": [s for s in doc["sections"] if s["key"] == key]}
    if not one["sections"] or not any(s.get("paragraphs") or s.get("bullets") for s in one["sections"]):
        return None
    return round(100 * (0.5 * fidelity.phrase_use(one, v) + 0.5 * fidelity.stylometrics(one, v)[0]), 1)


def held_out_sections(pid: str = "PRP-A-GMC", keys: list[str] | None = None) -> dict[str, Any]:
    """P3, section level: the named sections of a real-style memo are removed from the corpus, the profile is rebuilt, the
    sections are redrafted from the memo's facts, and each redraft is scored against the band of the bank's own memo
    sections (every section of every memo of the bank, scored against a profile built without that memo)."""
    key = f"S|{pid}|{keys}|{store.state_key()}"
    if key in _HELD:
        return _HELD[key]
    all_docs = store.corpus_docs()
    original = next((d for d in all_docs if d["doc_id"] == pid), None)
    if original is None:
        raise NotFound(f"{pid} is not a memo of the corpus.")
    keys = keys or [s["key"] for s in original["sections"] if s["key"] in dr.TEMPLATES and (s["paragraphs"] or s["bullets"])]
    held = {**original, "sections": [s for s in original["sections"] if s["key"] not in keys]}
    docs = [held if d["doc_id"] == pid else d for d in all_docs]
    st = prof.build(docs)
    import backend.dealdesk.house_style.retrieve as rt
    d = dr.draft(pid, st, rt.Index(docs), use_model=False, with_engine=False, sections=keys)
    meta = d["meta"]
    v = prof.view(st, meta["bank"], meta["kind"], meta["segment"])
    red = dr.as_doc(d)
    band_scores = []
    for b in [x for x in all_docs if x["bank"] == meta["bank"] and prof.role_of(x) == "business"]:
        rest = [x for x in all_docs if x["doc_id"] != b["doc_id"]]
        sv = prof.view(prof.build(rest), b["bank"], b["kind"], b["segment"])
        for s in b["sections"]:
            sc = _section_score(b, s["key"], sv) if s["key"] != "preamble" else None
            if sc is not None:
                band_scores.append(sc)
    vals = sorted(band_scores)
    low = vals[0] if len(vals) < 10 else vals[int(0.1 * (len(vals) - 1))]
    rows = []
    for k in keys:
        sc = _section_score(red, k, v)
        orig = _section_score(original, k, v)
        rows.append({"section": k, "redraft_score": sc, "original_score": orig, "within_band": sc is None or sc >= low,
                     "note": "no prose: the facts fill the house table, or the data has nothing for this section" if sc is None else ""})
    out = {"held_out": pid, "sections": rows, "profile_group": v["group"],
           "band": {"low": round(low, 1), "high": round(vals[-1], 1), "mean": round(sum(vals) / len(vals), 1), "n": len(vals)},
           "within_band": all(r["within_band"] for r in rows),
           "summary": f"{pid}: {len(rows)} sections held out and redrafted from the facts; "
                      + ", ".join(f"{r['section']} {r['redraft_score']}" for r in rows if r["redraft_score"] is not None)
                      + f" against the house band {round(low, 1)}–{round(vals[-1], 1)} ({len(vals)} sections of the bank's own memos)."}
    _HELD[key] = out
    return out


#: Session R's "Draft from data" section keys (review_workspace.draft) -> the house-style section that writes that prose
REVIEW_KEYS = {"exposure": ("facilities", "obligor"), "conduct": ("conduct",), "bureau": ("conduct",), "financials": ("financials",),
               "collateral": ("security",), "business": ("business",), "risks": ("risks",), "recommendation": ("recommendation",)}


def prose_for_review(pid: str) -> dict[str, Any]:
    """PLAN_R11 P2 / R6 reconciliation: the house-style prose for each section of Session R's "Draft from data", so R's button
    can show P's wording (M wires it: for each R section whose key is here, replace `text` with `prose[key]["text"]`).
    Figures keep their citation ids; `facts` lists them with their sources."""
    d = latest(pid) or create_draft(pid, use_model=False)
    by = {s["key"]: s for s in d["sections"]}
    prose: dict[str, Any] = {}
    for rk, keys in REVIEW_KEYS.items():
        for k in keys:
            s = by.get(k)
            if s and (s["paragraphs"] or s["bullets"]):
                prose[rk] = {"text": " ".join(s["paragraphs"] + s["bullets"]), "section": k, "judgement": s["judgement"],
                             "method": s["method"]}
                break
    cited = {c for v in prose.values() for c in dr.CITE.findall(v["text"])}
    return {"proposal_id": pid, "draft_id": d["draft_id"], "profile_group": d["profile_group"], "prose": prose,
            "facts": [f for f in d["facts"] if f["id"] in cited], "score": d["score"]["total"]}
