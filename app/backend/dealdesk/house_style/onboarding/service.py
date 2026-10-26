"""P6 governance: a learning session (PROPOSED items), the maker-checker decisions and the accepted versions.

Store (git-ignored): `var/dealdesk/house_style/onboarding/`
    sessions/<sid>/session.json         the session: documents, items, conflicts, gaps, committee questions, structure
    sessions/<sid>/proposed_*.json      the proposals in the live schemas (rules.json; risk_appetite / doa / market_bounds /
                                        desk), every row status "proposed", enabled false, with "learned_from"
    sessions/<sid>/decisions.jsonl      every Accept / Edit / Reject with the checker, the time and the note
    versions/onb-<n>/                   one version per accepted change: rules.json (R's schema, base rules + accepted
                                        policy rules), params/<table>.json (the whole table, accepted rows changed, each
                                        with learned_from), committee.json, manifest.json
The committed `data/dealdesk/house_style/onboarding/proposed_*.json` are the demo session's proposals (built by
`python -m backend.dealdesk.house_style.onboarding.build`).

Nothing applies until accepted: learning writes proposals only; `data/dealdesk/review/rules.json` and
`data/dealdesk/params/v1/*` are never written here (tested). An accepted version is applied by the onboarding draft and
review (`draft_review`), which runs the accepted rules in Session R's rule engine and asks the accepted committee questions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import threading
import time
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.house_style.onboarding import demo_memos, demo_policy, learn as L

_LOCK = threading.RLock()
BANK = demo_policy.BANK
COMMITTED = paths.DATA / "house_style" / "onboarding"
KINDS = ("policy", "doa", "appetite")


class NotFound(KeyError):
    pass


class Conflict(ValueError):
    pass


def root() -> pathlib.Path:
    return paths.VAR / "house_style" / "onboarding"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _w(p: pathlib.Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    tmp.replace(p)


def _aed_sar() -> float:
    from backend.dealdesk import desk_params
    return float(desk_params.rows()["aed_sar"])


# ------------------------------------------------------------------ learning

def learn(policy: tuple[str, bytes], memos: list[tuple[str, bytes]], doa: tuple[str, bytes] | None = None,
          appetite: tuple[str, bytes] | None = None, by: str = "", bank: str = "", save: bool = True,
          memo_docs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Read every document and propose what it teaches. Returns the session (saved unless save=False)."""
    t0 = time.perf_counter()
    rate = _aed_sar()
    docs_in = [("policy", policy)] + ([("doa", doa)] if doa else []) + ([("appetite", appetite)] if appetite else [])
    documents, items, policy_doc = [], [], None
    for kind, (name, data) in docs_in:
        d = L.read_document(name, data)
        if kind == "policy":
            policy_doc = d
        if not d["clauses"] and not d["tables"]:
            raise ValueError(f"{name}: no numbered clauses or tables found (is it a scan? it needs a text layer).")
        its = L.extract(d, kind=kind, aed_sar=rate, bank=bank or BANK)
        documents.append({"name": name, "kind": kind, "sha256": d["sha256"], "clauses": len(d["clauses"]), "tables": len(d["tables"]),
                          "items": len(its)})
        items.extend(its)
    mdocs = list(memo_docs or [])
    for name, data in memos:
        md = L.read_memo(name, data)
        mdocs.append(md)
        documents.append({"name": name, "kind": "memo", "sha256": L.sha(data), "sections": len(md["sections"]), "doc_id": md["doc_id"]})
    for md in memo_docs or []:
        documents.append({"name": md.get("title") or md["doc_id"], "kind": "memo", "doc_id": md["doc_id"], "sections": len(md["sections"])})
    # one item per id (the same clause read from two documents keeps the first)
    seen, uniq = set(), []
    for it in items:
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
    items = uniq
    L.in_force(items)
    reg = L.regulatory(items)
    by_id = {r["item_id"]: r for r in reg["weaker"]}
    for it in items:
        if it["id"] in by_id:
            it["conflict"] = {"regulation": by_id[it["id"]]["regulation"], "message": by_id[it["id"]]["message"]}
    committee = L.committee(mdocs)
    struct = L.structure(mdocs)
    lang = L.language(mdocs)
    gaps_sections = L.section_gaps(policy_doc, mdocs) if policy_doc else []
    gaps_data = L.data_gaps(items)
    learn_s = round(time.perf_counter() - t0, 2)
    key = hashlib.sha1("|".join(sorted(d.get("sha256", d.get("doc_id", "")) for d in documents)).encode()).hexdigest()[:8]
    sid = f"ONS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{key}"
    s = {"session_id": sid, "created_at": _now(), "maker": by, "bank": bank or BANK, "documents": documents,
         "items": items, "committee": committee, "structure": struct, "language": lang,
         "conflicts": reg["weaker"], "consistent": reg["consistent"], "gaps": {"data": gaps_data, "sections": gaps_sections},
         "decisions": {}, "versions": [], "timings": {"learn_s": learn_s}}
    s["summary"] = summary(s)
    if save:
        with _LOCK:
            d = root() / "sessions" / sid
            _w(d / "session.json", s)
            write_proposed(s, d)
            _w(root() / "latest.json", {"session_id": sid})
    return s


def demo_inputs() -> tuple[tuple[str, bytes], list[tuple[str, bytes]], list[dict[str, Any]]]:
    """The fictional policy, the four fictional committee memos and the house's existing memos (DD memos, cases)."""
    if not demo_policy.OUT.exists():
        demo_policy.write()
    if not demo_memos.files():
        demo_memos.write()
    pol = (demo_policy.OUT.name, demo_policy.OUT.read_bytes())
    memos = [(f.name, f.read_bytes()) for f in demo_memos.files()]
    from backend.dealdesk.house_style import corpus
    house = [d for d in corpus.load(include_uploads=False) if d["source"] in ("memo", "case", "opinion")]
    return pol, memos, house


def learn_demo(by: str = "", save: bool = True) -> dict[str, Any]:
    pol, memos, house = demo_inputs()
    return learn(pol, memos, by=by, save=save, memo_docs=house)


def summary(s: dict[str, Any]) -> dict[str, Any]:
    its = s["items"]
    rules = [i for i in its if i.get("rule")]
    prm = [i for i in its if i.get("param")]
    dec = s.get("decisions", {})
    allx = its + s["committee"] + s["structure"] + s["language"]
    n_acc = sum(1 for v in dec.values() if v["action"] in ("accept", "edit"))
    n_rej = sum(1 for v in dec.values() if v["action"] == "reject")
    thr = [i for i in its if i["type"] == "threshold"]
    text = (f"Learned {len(thr)} thresholds and {len(its) - len(thr)} conditions from the policy: {len(rules)} rules, "
            f"{len(prm)} parameter changes; {len(s['conflicts'])} clauses weaker than the CBUAE CRM Standards; "
            f"{len(s['gaps']['data'])} rules a person must check; {len(s['gaps']['sections'])} required sections the memos skip; "
            f"{len(s['committee'])} questions committees keep asking. {n_acc} of {len(allx)} accepted, {n_rej} rejected; "
            "nothing applies until accepted.")
    return {"thresholds": len(thr), "conditions": len(its) - len(thr), "rules": len(rules), "params": len(prm),
            "auto": sum(1 for i in its if i.get("checkability") == "auto"), "manual": sum(1 for i in its if i.get("checkability") == "manual"),
            "conflicts": len(s["conflicts"]), "data_gaps": len(s["gaps"]["data"]), "section_gaps": len(s["gaps"]["sections"]),
            "committee": len(s["committee"]), "items": len(allx), "accepted": n_acc, "rejected": n_rej,
            "pending": len(allx) - n_acc - n_rej, "text": text}


def _rules_header() -> dict[str, Any]:
    rb = json.loads((paths.DATA / "review" / "rules.json").read_text())
    return {k: v for k, v in rb.items() if k != "rules"}


def write_proposed(s: dict[str, Any], d: pathlib.Path) -> list[pathlib.Path]:
    """The session's proposals in the live schemas, every row PROPOSED (enabled false)."""
    hdr = _rules_header()
    rules = [copy.deepcopy(i["rule"]) | {"learned_item": i["id"], "checkability": i["checkability"], "data_fields": i["data_fields"],
                                          **({"same_as": i["same_as"]} if i.get("same_as") else {})}
             for i in s["items"] if i.get("rule")]
    out = {
        "proposed_rules.json": {**hdr, "description": "PROPOSED by P6 onboarding: rules learned from the bank's credit policy. "
                                "Not live: enabled false until a checker accepts each one.", "version": "proposed",
                                "status": "proposed", "session_id": s["session_id"], "rules": rules},
        "proposed_params.json": {"status": "proposed", "session_id": s["session_id"], "description":
                                 "PROPOSED parameter values in the Deal Desk params schema (risk_appetite, doa, market_bounds, desk), "
                                 "each with the clause it was learned from and the value in force. Not live.",
                                 "changes": [{"item_id": i["id"], "clause": i["clause"], "label": i["label"], **i["param"],
                                              "checkability": i["checkability"], "learned_from": i["learned_from"], "status": "proposed"}
                                             for i in s["items"] if i.get("param")]},
        "proposed_checks.json": {"status": "proposed", "session_id": s["session_id"],
                                 "items": [{k: v for k, v in i.items() if k not in ("rule", "param")} for i in s["items"]]},
        "proposed_conflicts.json": {"status": "proposed", "session_id": s["session_id"], "weaker_than_regulation": s["conflicts"],
                                    "consistent_with_regulation": s["consistent"], "gaps": s["gaps"]},
        "proposed_committee.json": {"status": "proposed", "session_id": s["session_id"], "questions": s["committee"]},
        "proposed_structure.json": {"status": "proposed", "session_id": s["session_id"], "structure": s["structure"],
                                    "language": s["language"]},
    }
    paths_out = []
    for name, obj in out.items():
        _w(d / name, obj)
        paths_out.append(d / name)
    return paths_out


# ------------------------------------------------------------------ reading sessions

def latest_id() -> str | None:
    f = root() / "latest.json"
    return json.loads(f.read_text())["session_id"] if f.exists() else None


def get(sid: str) -> dict[str, Any]:
    f = root() / "sessions" / sid / "session.json"
    if not f.exists():
        raise NotFound(f"No onboarding session {sid}.")
    return json.loads(f.read_text())


def overview() -> dict[str, Any]:
    sid = latest_id()
    return {"session": get(sid) if sid else None, "versions": versions(),
            "demo": {"policy": str(demo_policy.OUT.relative_to(paths.V5)),
                     "memos": [str(f.relative_to(paths.V5)) for f in demo_memos.files()]}}


def _all_items(s: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in s["items"] + s["committee"] + s["structure"] + s["language"]}


# ------------------------------------------------------------------ maker-checker

def decide(sid: str, item_id: str, action: str, by: str = "", value: Any = None, note: str = "") -> dict[str, Any]:
    """Accept, Edit (accept with a changed value) or Reject one item. Accept and Edit create the next version."""
    if action not in ("accept", "edit", "reject"):
        raise ValueError("action is accept, edit or reject.")
    with _LOCK:
        s = get(sid)
        items = _all_items(s)
        if item_id not in items:
            raise NotFound(f"No item {item_id} in {sid}.")
        if by and s.get("maker") and by == s["maker"]:
            raise Conflict("Maker-checker: the person who uploaded the documents cannot accept what was learned from them.")
        it = items[item_id]
        if action == "edit":
            if value is None:
                raise ValueError("Edit needs a value.")
            _apply_edit(it, value)
        rec = {"item_id": item_id, "action": action, "by": by or "checker", "at": _now(), "note": note,
               **({"value": value} if action == "edit" else {})}
        s["decisions"][item_id] = rec
        _replace_item(s, it)
        d = root() / "sessions" / sid
        with (d / "decisions.jsonl").open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        ver = None
        if action in ("accept", "edit"):
            ver = _publish(s, by or "checker")
            s["versions"].append(ver["version"])
            rec["version"] = ver["version"]
        it["status"] = {"accept": "accepted", "edit": "accepted (edited)", "reject": "rejected"}[action]
        _replace_item(s, it)
        s["summary"] = summary(s)
        _w(d / "session.json", s)
        return {"decision": rec, "item": it, "version": ver, "summary": s["summary"]}


def _replace_item(s: dict[str, Any], it: dict[str, Any]) -> None:
    for key in ("items", "committee", "structure", "language"):
        s[key] = [it if x["id"] == it["id"] else x for x in s[key]]


def _apply_edit(it: dict[str, Any], value: Any) -> None:
    """An edited value replaces the learned one in the item, its rule threshold and its parameter proposal."""
    if it["type"] == "committee_question":
        it["question"] = it["label"] = str(value)
        return
    it["edited_from"] = it.get("value")
    if isinstance(it.get("value"), (int, float)):
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{value!r} is not a number.") from None
        it["value"] = v
        p = it.get("param") or {}
        if it.get("rule") and "threshold" in it["rule"] and not it["rule"].get("threshold_input"):
            it["rule"]["threshold"] = round(v * _aed_sar(), 2) if p.get("conversion") else v
        if p:
            p["proposed"] = round(v * float(p.get("factor") or 1.0), 6)
            p["change"] = L._change(p.get("in_force"), p["proposed"], it.get("stricter", ""))
    else:
        it["value"] = value
        if it.get("param"):
            it["param"]["proposed"] = value


def versions() -> list[dict[str, Any]]:
    d = root() / "versions"
    if not d.exists():
        return []
    out = []
    for v in sorted(d.iterdir(), key=lambda p: int(p.name.split("-")[1]) if p.name.startswith("onb-") else 0):
        m = v / "manifest.json"
        if m.exists():
            out.append(json.loads(m.read_text()))
    return out


def version(vid: str) -> dict[str, Any]:
    d = root() / "versions" / vid
    if not (d / "manifest.json").exists():
        raise NotFound(f"No version {vid}.")
    out = json.loads((d / "manifest.json").read_text())
    out["rules"] = json.loads((d / "rules.json").read_text())
    out["params"] = {f.stem: json.loads(f.read_text()) for f in sorted((d / "params").glob("*.json"))}
    out["committee"] = json.loads((d / "committee.json").read_text())
    return out


def _accepted(s: dict[str, Any]) -> list[dict[str, Any]]:
    items = _all_items(s)
    return [items[k] for k, v in s["decisions"].items() if v["action"] in ("accept", "edit") and k in items]


def _publish(s: dict[str, Any], by: str) -> dict[str, Any]:
    """The next version: the whole rule book and the whole parameter tables with every accepted item applied."""
    from backend.dealdesk import desk_params, params
    vs = versions()
    n = (max(int(v["version"].split("-")[1]) for v in vs) + 1) if vs else 1
    vid = f"onb-{n}"
    acc = _accepted(s)
    prev = version(vs[-1]["version"]) if vs else None
    # rules: R's rule book + accepted policy rules (enabled, with provenance)
    base = prev["rules"] if prev else json.loads((paths.DATA / "review" / "rules.json").read_text())
    rb = copy.deepcopy(base)
    have = {r["id"]: i for i, r in enumerate(rb["rules"])}
    for it in acc:
        if not it.get("rule"):
            continue
        r = copy.deepcopy(it["rule"])
        r.update({"enabled": True, "status": "accepted", "accepted_by": by, "accepted_at": _now(), "version": vid})
        if r["id"] in have:
            rb["rules"][have[r["id"]]] = r
        else:
            have[r["id"]] = len(rb["rules"])
            rb["rules"].append(r)
    rb["version"] = f"{json.loads((paths.DATA / 'review' / 'rules.json').read_text())['version']}+{vid}"
    rb["effective_from"] = datetime.now(timezone.utc).date().isoformat()
    # params: whole tables, accepted rows changed
    tables: dict[str, Any] = copy.deepcopy(prev["params"]) if prev else {}
    for it in acc:
        p = it.get("param")
        if not p:
            continue
        t = p["table"]
        if t not in tables:
            tables[t] = copy.deepcopy(desk_params.table() if t == "desk" else params.table(t))
        tab = tables[t]
        prov = {"session_id": s["session_id"], "item_id": it["id"], "document": it["learned_from"].get("document"),
                "clause": it["clause"], "quote": it["quote"], "accepted_by": by, "version": vid}
        if t == "doa":
            for lv in p["proposed"]:
                row = next((r for r in tab["rows"] if r["level"].lower() == lv["level"].lower()), None)
                if row is not None and lv.get("max_exposure") is not None:
                    row["max_exposure"] = lv["max_exposure"]
                if row is not None and lv.get("min_rating"):
                    row["min_rating"] = lv["min_rating"]
                if row is not None:
                    row["learned_from"] = prov
        elif t == "market_bounds":
            for b, rng in p["proposed"].items():
                if b in tab["rows"]["by_bucket"]:
                    tab["rows"]["by_bucket"][b]["margin_bps"] = rng
            tab["rows"].setdefault("learned_from", []).append(prov)
        elif t == "desk":
            rows = tab.get("rows", tab)
            if isinstance(rows.get(p["row"]), dict):
                rows[p["row"]][p["field"]] = p["proposed"]
            else:
                rows[p["row"]] = p["proposed"]
            tab.setdefault("learned_from", []).append(prov)
        else:
            row = next((r for r in tab["rows"] if r["name"] == p["row"]), None)
            if row is None:
                continue
            row[p["field"]] = p["proposed"]
            row["learned_from"] = prov
            row["basis"] = f"{s['bank']} Credit Policy {it['clause']} (learned, accepted {vid})"
        tab["version"] = vid
        tab["effective_from"] = datetime.now(timezone.utc).date().isoformat()
        tab["approved_by"] = by
    committee = [i for i in acc if i["type"] == "committee_question"]
    structure = [i for i in acc if i["type"] in ("structure", "language")]
    d = root() / "versions" / vid
    _w(d / "rules.json", rb)
    for t, tab in tables.items():
        _w(d / "params" / f"{t}.json", tab)
    _w(d / "committee.json", {"questions": committee, "structure": structure})
    man = {"version": vid, "created_at": _now(), "by": by, "session_id": s["session_id"], "previous": prev["version"] if prev else None,
           "accepted_items": [i["id"] for i in acc], "rules_added": sum(1 for i in acc if i.get("rule")),
           "params_changed": sorted({i["param"]["table"] for i in acc if i.get("param")}), "committee_questions": len(committee),
           "learned_from": sorted({(i.get("learned_from") or {}).get("document") or "memos" for i in acc}),
           "applies_to": "the onboarding draft and review; the live rules.json and params/v1 are promoted by their owners"}
    _w(d / "manifest.json", man)
    return man


# ------------------------------------------------------------------ the accepted version at work: draft and review

def _covered(text: str, pattern: str) -> bool:
    import re
    return bool(re.search(pattern, text, re.I))


def committee_answers(draft: dict[str, Any], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each accepted committee question: answered in the draft, answered pre-emptively from the facts, or open."""
    import re
    secs = draft.get("sections", [])
    out = []
    for q in questions:
        pat = q.get("answer_pattern") or q["metric"]
        where = next((s["heading"] or s["key"] for s in secs
                      if _covered(" ".join([*s.get("paragraphs", []), *s.get("bullets", [])]), pat)), None)
        facts = [f for f in draft.get("facts", []) if re.search(pat, f.get("label", ""), re.I)]
        if where:
            out.append({"id": q["id"], "question": q["question"], "status": "answered", "where": where, "facts": []})
        elif facts:
            ans = "; ".join(f"{f['label']} {f['display']} ({f.get('source', '')})" for f in facts[:3])
            out.append({"id": q["id"], "question": q["question"], "status": "answered", "where": "Questions the committee asks",
                        "answer": ans, "facts": [f["id"] for f in facts[:3]]})
        else:
            out.append({"id": q["id"], "question": q["question"], "status": "open", "where": None,
                        "answer": "For the RM: no data in the proposal answers it yet.", "facts": []})
    return out


def draft_review(pid: str, vid: str | None = None, by: str = "") -> dict[str, Any]:
    """Draft the proposal in the house style with the accepted committee questions answered pre-emptively, then review it:
    Session R's review, the accepted policy rules (R's engine) and the questions the draft leaves open."""
    from backend.dealdesk import review_facts as RF, review_rules as RR, review_workspace as RW
    from backend.dealdesk.house_style import service as hs
    vs = versions()
    vid = vid or (vs[-1]["version"] if vs else None)
    ver = version(vid) if vid else None
    t0 = time.perf_counter()
    d = hs.create_draft(pid, use_model=False, by=by)
    qs = (ver or {}).get("committee", {}).get("questions", [])
    answers = committee_answers(d, qs)
    t1 = time.perf_counter()
    rev = RW.review(pid, refresh=True, with_counter=False) if RF.known(pid) else None
    policy_checks: list[dict[str, Any]] = []
    if ver and RF.known(pid):
        f = RF.facts(pid)
        for r in ver["rules"]["rules"]:
            if r.get("status") == "accepted" and r.get("enabled"):
                try:
                    policy_checks.extend(RR.run_rule(r, f))
                except Exception as e:  # noqa: BLE001 - a rule that cannot run is reported, never silent
                    policy_checks.append({"rule_id": r["id"], "verdict": "unverifiable", "finding": f"Rule could not run: {e}"})
    open_q = [{"rule_id": a["id"], "verdict": "open", "severity": "major", "finding": f"Committee question left open: {a['question']}"}
              for a in answers if a["status"] == "open"]
    t2 = time.perf_counter()
    findings = [c for c in (rev or {}).get("checks", []) if c.get("verdict") in ("contradicted", "exception")] if rev else []
    pol_find = [c for c in policy_checks if c.get("verdict") in ("contradicted", "exception")]
    return {"proposal_id": pid, "version": vid, "draft_id": d["draft_id"], "style_score": (d.get("score") or {}).get("total"),
            "sections": [s["heading"] or s["key"] for s in d["sections"]], "committee_answers": answers,
            "review": {"headline": (rev or {}).get("headline") or (rev or {}).get("answer"), "findings": len(findings),
                       "policy_checks": policy_checks, "policy_findings": len(pol_find), "open_questions": open_q},
            "timings": {"draft_s": round(t1 - t0, 2), "draft_to_review_s": round(t2 - t1, 2)}}
