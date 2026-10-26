"""The paper workspace: open, instruct, accept, undo, mark final, versions, provenance, export.

    ws = open_workspace("proposal", proposal_id="DD-06", user=U)     # reopens the deal's latest proposal workspace, else v1 from the writer
    st = instruct(ws["ws_id"], "Shorten the financial synopsis", focus=None, user=U)
    st["last"]   {"kind": "edit" | "structure" | "reply" | "rejected", "version": 2, "section": "synopsis", ...}
    accept(ws_id, 2, U); undo(ws_id, 2, U); mark_final(ws_id, None, U)

U = {"username": "anne", "name": "Anne"}. Every change is a new version; a change stays "pending" (marked on the document) until
accepted or undone. Noor's replies are turns of the thread, kept with the workspace.
"""
from __future__ import annotations

import copy
import time
from typing import Any

from backend.dealdesk.paperws import figures as FG
from backend.dealdesk.paperws import hooks
from backend.dealdesk.paperws import instructions as IN
from backend.dealdesk.paperws import provenance as PV
from backend.dealdesk.paperws import sources as SRC
from backend.dealdesk.paperws import store as ST
from backend.dealdesk.paperws import structure as STR

PREFIX = "/api/v1/dealdesk/paper-workspaces"
KINDS = ("proposal", "request")
LABEL = {"proposal": "Credit proposal", "request": "Business request"}


class WsError(ValueError):
    def __init__(self, msg: str, status: int = 422):
        super().__init__(msg)
        self.status = status


def _who(user: dict[str, Any] | None) -> tuple[str, str]:
    u = user or {}
    return str(u.get("username") or ""), str(u.get("name") or u.get("username") or "Analyst")


def href(ws_id: str) -> str:
    return f"/deal-desk/paper/{ws_id}"


def links(ws_id: str) -> dict[str, str]:
    b = f"{PREFIX}/{ws_id}"
    return {"self": b, "open": href(ws_id), "instruct": f"{b}/instruct", "versions": f"{b}/versions", "provenance": f"{b}/provenance",
            "docx": f"{b}/export.docx", "pdf": f"{b}/export.pdf", "final_docx": f"{b}/export.docx?version=final", "mark_final": f"{b}/final"}


def row(w: dict[str, Any]) -> dict[str, Any]:
    return {"ws_id": w["ws_id"], "kind": w["kind"], "kind_label": LABEL.get(w["kind"], w["kind"]), "proposal_id": w["proposal_id"],
            "ref": w["ref"], "title": w["title"], "customer": w["customer"], "owner": w["owner"], "owner_name": w["owner_name"],
            "created": w["created"], "updated": w["updated"], "status": w["status"], "final_version": w["final_version"],
            "current_version": w["current_version"], "href": href(w["ws_id"])}


def _get(ws_id: str) -> dict[str, Any]:
    w = ST.default().get(ws_id)
    if w is None:
        raise WsError(f"no paper workspace {ws_id}", 404)
    return w


# ------------------------------------------------------------------------------------------------- open

def _greeting(kind: str, paper: dict[str, Any]) -> str:
    doc = "credit proposal" if kind == "proposal" else "business request"
    n = len(paper.get("sections") or [])
    return (f"This is the {doc} for {paper.get('customer') or paper.get('proposal_id')} in the bank's form: {n} sections, version 1. "
            "Tell me what to change, one section at a time, e.g. “Shorten the financial synopsis”, “Add to the background: …”, "
            "or “Set the amount to SAR 20m” (a number goes to the structure step and the paper is re-rendered from the engine). "
            "Click a section on the left to point me at it.")


def open_workspace(kind: str, proposal_id: str | None = None, ref: str | None = None, structure: Any = None,
                   paper: dict[str, Any] | None = None, source: str | None = None, fresh: bool = False,
                   user: dict[str, Any] | None = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise WsError("kind: proposal or request")
    store = ST.default()
    if paper is None and source is None and not fresh:
        found = store.listing(proposal_id=proposal_id if kind == "proposal" else None, kind=kind, ref=ref if kind == "request" else None, limit=1)
        if found and (kind == "proposal" and proposal_id or kind == "request" and ref):
            return state(found[0]["ws_id"])
    try:
        if paper is not None:
            p = SRC.given(paper, kind)
        elif source:
            p = SRC.given(SRC.named(source, ref or ""), kind)
        elif kind == "proposal":
            if not proposal_id:
                raise WsError("proposal_id: name the deal")
            p = SRC.proposal(proposal_id, structure)
        else:
            if not ref:
                raise WsError("ref: the business request id (BR-…)")
            p = SRC.request(ref)
    except SRC.SourceError as e:
        raise WsError(str(e), 404) from None
    username, name = _who(user)
    pid = str(p.get("proposal_id") or proposal_id or "")
    r = ref or (p.get("request_id") if kind == "request" else (structure if isinstance(structure, str) else p.get("structure_key"))) or ""
    title = f"{LABEL[kind]} · {p.get('customer') or pid}"
    ws_id = store.create(kind, pid, str(r), title, str(p.get("customer") or ""), username, name, {"source": source or ("given" if paper else kind)})
    store.add_version(ws_id, p, name, "created", note="written by " + ("the bank-form writer" if kind == "proposal" and not paper else
                                                                       "R16 b's request writer" if kind == "request" and not paper else source or "the caller"))
    store.add_turn(ws_id, "noor", _greeting(kind, p), version=1)
    return state(ws_id)


# ------------------------------------------------------------------------------------------------- read

def pending(versions: list[dict[str, Any]], paper: dict[str, Any]) -> list[dict[str, Any]]:
    """Changes still marked on the document: pending, and the section still as the change left it."""
    by = {s["key"]: s for s in paper.get("sections") or []}
    out = []
    for v in versions:
        ch = v.get("change") or {}
        if ch.get("status") != "pending":
            continue
        secs = [s for s in ch.get("sections") or [] if s["key"] in by and _same(by[s["key"]].get("blocks"), s.get("after"))]
        if secs:
            out.append({"version": v["n"], "action": v["action"], "instruction": v.get("instruction"), "author": v.get("author"), "at": v.get("at"),
                        "note": ch.get("note"), "fields": ch.get("fields"), "sections": secs})
    return out


def _same(a: Any, b: Any) -> bool:
    import json
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _rules_ctx(w: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    return {"kind": w["kind"], "proposal_id": w["proposal_id"], "ws_id": w["ws_id"], "owner": w["owner"],
            "sections": [s["key"] for s in paper.get("sections") or []]}


def state(ws_id: str, version: int | None = None) -> dict[str, Any]:
    w = _get(ws_id)
    store = ST.default()
    v = store.version(ws_id, version)
    if v is None:
        raise WsError(f"no version {version} of {ws_id}", 404)
    vers = store.versions(ws_id)
    paper = v["paper"]
    return {"workspace": row(w), "version": {k: v[k] for k in ("n", "author", "at", "action", "instruction", "section", "note")},
            "paper": {**paper, "sections": [{k: x for k, x in s.items() if k != "engine_blocks"} | {"edited": "engine_blocks" in s}
                                             for s in paper.get("sections") or []]},
            "versions": vers, "turns": store.turns(ws_id), "pending": pending(vers, paper) if version is None else [],
            "rules_applied": hooks.rules(_rules_ctx(w, paper)), "model": IN.model_available(), "links": links(ws_id)}


def listing(proposal_id: str | None = None, kind: str | None = None, owner: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return [row(w) for w in ST.default().listing(proposal_id=proposal_id, kind=kind, owner=owner, limit=limit)]


# ------------------------------------------------------------------------------------------------- instruct

CAN_DO = ("I can: shorten a section; add to a section (“Add to the background: …”); start a section with a line; replace wording "
          "(“Replace \"weak\" with \"modest\" in the synopsis”); remove a sentence about something; underline a sentence as a key concern; "
          "turn a section into bullet points or a paragraph; and change a term (amount, tenor, margin, cash margin, upfront fee) "
          "through the structure step.")


def _reply(ws_id: str, text: str, kind: str, extra: dict[str, Any] | None = None, section: str = "") -> dict[str, Any]:
    ST.default().add_turn(ws_id, "noor", text, section=section, meta={"kind": kind, **(extra or {})})
    out = state(ws_id)
    out["last"] = {"kind": kind, "text": text, **(extra or {})}
    return out


def _label(s: dict[str, Any] | None) -> str:
    if not s:
        return ""
    return f"{s['n']}. {s['heading']}" if s.get("n") else str(s.get("heading") or s.get("key"))


def instruct(ws_id: str, text: str, focus: str | None = None, user: dict[str, Any] | None = None) -> dict[str, Any]:
    w = _get(ws_id)
    store = ST.default()
    username, name = _who(user)
    text = " ".join(str(text or "").split())
    if not text:
        raise WsError("text: type an instruction")
    cur = store.version(ws_id)
    paper = cur["paper"]
    store.add_turn(ws_id, "user", text, author=name, version=cur["n"], section=focus or "")

    # 1. a number: the structure step
    if w["kind"] == "request" and STR.is_request_ask(text):
        return _structure(w, paper, text, None, name)
    try:
        it = IN.parse(text, paper, focus)
    except IN.NotUnderstood as e:
        return _reply(ws_id, str(e), "reply")
    if it["op"] == "structure":
        if w["kind"] == "request":
            return _reply(ws_id, "In a business request the figures come from the RM's ask: name the facility and the amount, e.g. "
                                 "“Increase the overdraft to SAR 35m”, and I will write the request again from the ask.", "reply")
        return _structure(w, paper, text, it["fields"], name)
    if it["op"] == "figure":
        return _reply(ws_id, f"I did not type “{it['new']}” in place of “{it['old']}”: figures are the engine's. Tell me the term to change "
                             "(e.g. “Set the amount to SAR 20m”, “Set the tenor to 5 years”) and I will send it to the structure step and re-render "
                             "the paper from the engine.", "rejected", {"reason": "figure"})

    # 2. the section
    key = it.get("section")
    if not key and it["op"] in ("replace", "remove", "emphasise"):
        key = IN.find_phrase_section(paper, it.get("old") or it.get("phrase") or "")
    if not key:
        return _reply(ws_id, "Which section? Click a section on the left, or name it (e.g. “in the financial synopsis”).", "reply")
    sec = IN.section_by_key(paper, key)
    if sec is None:
        return _reply(ws_id, f"This paper has no section {key}.", "reply")
    if sec.get("voice") == "form" and it["op"] not in ("add", "lead"):
        return _reply(ws_id, f"{_label(sec)} is the bank's form block; it is filled from the deal record, not edited by instruction.", "reply", section=key)

    # 3. the edit: rules first, the model for anything else
    # the evidence of ONE section: its own printed figures, the header, the engine's results (the model and the analyst see this section)
    allowed = FG.evidence({"sections": [sec], "header_line": paper.get("header_line") or []}, _engine_values(paper))
    try:
        new_blocks, note = IN.apply(it, sec)
        method = "rules"
    except IN.NotUnderstood as e:
        if str(e) != "model":
            return _reply(ws_id, str(e), "reply", section=key)
        if not IN.model_available():
            return _reply(ws_id, "I could not read that as one of the instructions I can apply without the model. " + CAN_DO, "reply", section=key)
        try:
            new_blocks, note = IN.model_edit(it, sec, allowed, {"ws_id": ws_id, "kind": w["kind"], "customer": paper.get("customer")})
            method = "model"
        except IN.FigureRejected as fr:
            return _reply(ws_id, f"I rejected the model's rewrite of {_label(sec)}: it wrote {fr} , which is not in the evidence. Figures are "
                                 "the engine's; the section is unchanged.", "rejected", {"reason": "figure", "figures": fr.figures}, section=key)
        except IN.NotUnderstood as e2:
            return _reply(ws_id, str(e2), "reply", section=key)
    bad = FG.blocks_unknown(new_blocks, allowed)
    if bad:
        shown = ", ".join(IN._fmt(x) for x in bad)  # noqa: SLF001
        return _reply(ws_id, f"I did not change {_label(sec)}: {shown} is not a figure in the evidence (this section, the deal's engine results or "
                             "the header). Figures are the engine's: to change a term, say e.g. “Set the amount to SAR 20m” and I will send it "
                             "to the structure step.", "rejected", {"reason": "figure", "figures": bad}, section=key)

    # 4. the new version, marked
    new_paper = copy.deepcopy(paper)
    for s in new_paper["sections"]:
        if s["key"] == key:
            s.setdefault("engine_blocks", copy.deepcopy(s["blocks"]))
            s["blocks"] = new_blocks
            s["edited_by"] = {"author": name, "at": time.time(), "instruction": text}
    change = {"sections": [{"key": key, "heading": _label(sec), "before": sec["blocks"], "after": new_blocks}], "status": "pending",
              "note": note, "method": method, "op": it["op"]}
    n = store.add_version(ws_id, new_paper, name, "edit", instruction=text, section=key, change=change)
    hooks.instruction_applied({"ws_id": ws_id, "kind": w["kind"], "proposal_id": w["proposal_id"], "section": key, "heading": sec.get("heading"),
                               "instruction": text, "author": username or name, "version": n, "at": time.time()})
    return _reply(ws_id, f"Done in {_label(sec)}: {note}. It is marked on the document as version {n}; accept it or undo it there.",
                  "edit", {"version": n, "section": key, "heading": sec.get("heading"), "instruction": text, "method": method}, section=key)


def _engine_values(paper: dict[str, Any]) -> list[Any]:
    f = paper.get("feed") or {}
    vals = [f.get(k) for k in ("raroc", "hurdle", "sva", "capacity")] + list((paper.get("totals") or {}).values())
    vals += [v for v in (paper.get("structure_terms") or {}).values() if isinstance(v, (int, float))]
    vals += [f2.get("value") for f2 in paper.get("figures") or [] if isinstance(f2.get("value"), (int, float))]
    return [v for v in vals if isinstance(v, (int, float))]


def _structure(w: dict[str, Any], paper: dict[str, Any], text: str, fields: list[dict[str, Any]] | None, name: str) -> dict[str, Any]:
    ws_id = w["ws_id"]
    try:
        if w["kind"] == "request":
            new_paper, info = STR.request_ask(paper, text)
        else:
            new_paper, info = STR.proposal_terms(paper, fields or [])
    except STR.StructureError as e:
        return _reply(ws_id, str(e), "reply")
    old_by = {s["key"]: s for s in paper["sections"]}
    secs = [{"key": k, "heading": _label(next((s for s in new_paper["sections"] if s["key"] == k), None)),
             "before": (old_by.get(k) or {}).get("blocks") or [], "after": next(s["blocks"] for s in new_paper["sections"] if s["key"] == k)}
            for k in info["changed"]]
    if not secs:
        return _reply(ws_id, "The engine re-priced the new terms and no section of the paper changed.", "structure", {"fields": info["fields"]})
    change = {"sections": secs, "status": "pending", "fields": info["fields"], "note": "re-rendered from the engine", "op": "structure",
              "engine": info.get("engine")}
    n = ST.default().add_version(ws_id, new_paper, name, "structure", instruction=text, section=secs[0]["key"], change=change)
    moves = "; ".join(f"{f['label']} {_v(f['from'])} → {_v(f['to'])}" for f in info["fields"]) if w["kind"] == "proposal" else \
        f"the ask now reads “{info.get('ask_text')}”"
    eco = ""
    if info.get("raroc") is not None and info.get("hurdle") is not None:
        eco = f" The engine prices it at RAROC {info['raroc'] * 100:.1f}% against a {info['hurdle'] * 100:.1f}% hurdle" + (
            f", approval by {info['approval']}." if info.get("approval") else ".")
    rep = f" My wording in {', '.join(info['replaced'])} was replaced by the engine's new text." if info.get("replaced") else ""
    hooks.instruction_applied({"ws_id": ws_id, "kind": w["kind"], "proposal_id": w["proposal_id"], "section": secs[0]["key"], "heading": secs[0]["heading"],
                               "instruction": text, "author": name, "version": n, "at": time.time(), "structure": True})
    return _reply(ws_id, f"Sent to the structure step: {moves}.{eco} {len(secs)} section{'s' if len(secs) != 1 else ''} re-rendered from the "
                         f"engine's figures (version {n}, marked on the document).{rep}",
                  "structure", {"version": n, "fields": info["fields"], "sections": [s["key"] for s in secs]}, section=secs[0]["key"])


def _v(x: Any) -> str:
    if isinstance(x, float):
        return f"{x:,.2f}".rstrip("0").rstrip(".")
    return str(x if x is not None else "–")


# ------------------------------------------------------------------------------------------------- accept / undo / final

def accept(ws_id: str, n: int, user: dict[str, Any] | None = None) -> dict[str, Any]:
    _get(ws_id)
    store = ST.default()
    v = store.version(ws_id, n)
    if v is None or not v.get("change"):
        raise WsError(f"version {n} has no change to accept", 404)
    ch = v["change"]
    if ch.get("status") != "pending":
        raise WsError(f"version {n} is already {ch.get('status')}")
    ch["status"], ch["accepted_by"], ch["accepted_at"] = "accepted", _who(user)[1], time.time()
    store.set_change(ws_id, n, ch)
    return _reply(ws_id, f"Accepted version {n} ({', '.join(s['heading'] for s in ch['sections'])}).", "accepted", {"version": n})


def undo(ws_id: str, n: int, user: dict[str, Any] | None = None) -> dict[str, Any]:
    _get(ws_id)
    store = ST.default()
    v = store.version(ws_id, n)
    if v is None or not v.get("change"):
        raise WsError(f"version {n} has no change to undo", 404)
    ch = v["change"]
    if ch.get("status") == "undone":
        raise WsError(f"version {n} is already undone")
    cur = store.version(ws_id)
    name = _who(user)[1]
    if v["action"] == "structure":
        if cur["n"] != n:
            raise WsError("A later version changed the paper after this structure change: undo the later versions first.", 409)
        prev = store.version(ws_id, n - 1)
        new_paper = prev["paper"]
    else:
        new_paper = copy.deepcopy(cur["paper"])
        by = {s["key"]: s for s in new_paper["sections"]}
        for s in ch["sections"]:
            now = by.get(s["key"])
            if now is None or not _same(now.get("blocks"), s["after"]):
                raise WsError(f"A later change touched {s['heading']}: undo that one first.", 409)
            now["blocks"] = copy.deepcopy(s["before"])
            if _same(now.get("engine_blocks"), now["blocks"]):
                now.pop("engine_blocks", None)
                now.pop("edited_by", None)
    m = store.add_version(ws_id, new_paper, name, "undo", instruction=f"Undo version {n}", section=v.get("section") or "",
                          change={"sections": [{"key": s["key"], "heading": s["heading"], "before": s["after"], "after": s["before"]} for s in ch["sections"]],
                                  "status": "accepted", "undo_of": n, "note": f"undo of version {n}"})
    ch["status"], ch["undone_by"], ch["undone_at"], ch["undone_in"] = "undone", name, time.time(), m
    store.set_change(ws_id, n, ch)
    return _reply(ws_id, f"Undone: version {n} is reverted in version {m}.", "undone", {"version": m, "undo_of": n})


def mark_final(ws_id: str, n: int | None = None, user: dict[str, Any] | None = None, final: bool = True) -> dict[str, Any]:
    w = _get(ws_id)
    store = ST.default()
    if not final:
        store.update(ws_id, status="draft", final_version=None)
        return _reply(ws_id, "The committee copy is cleared; the paper is a working draft again.", "final", {"final_version": None})
    n = n or w["current_version"]
    if store.version(ws_id, n) is None:
        raise WsError(f"no version {n}", 404)
    p = pending(store.versions(ws_id), store.version(ws_id)["paper"]) if n == w["current_version"] else []
    store.update(ws_id, status="final", final_version=n)
    warn = f" {len(p)} change{'s are' if len(p) != 1 else ' is'} still marked as pending in it." if p else ""
    return _reply(ws_id, f"Version {n} is marked final: it is the committee copy (Word and PDF).{warn}", "final", {"final_version": n})


# ------------------------------------------------------------------------------------------------- provenance and files

def _resolve_version(w: dict[str, Any], version: str | int | None) -> int | None:
    if version in (None, "", "current"):
        return None
    if version == "final":
        if not w.get("final_version"):
            raise WsError("no version is marked final yet", 404)
        return int(w["final_version"])
    try:
        return int(version)
    except (TypeError, ValueError):
        raise WsError("version: a number, 'current' or 'final'") from None


def provenance(ws_id: str, version: str | int | None = None) -> dict[str, Any]:
    w = _get(ws_id)
    store = ST.default()
    v = store.version(ws_id, _resolve_version(w, version))
    if v is None:
        raise WsError("no such version", 404)
    vers = [x for x in store.versions(ws_id) if x["n"] <= v["n"]]
    pv = PV.build(v["paper"], vers, hooks.rules(_rules_ctx(w, v["paper"])))
    return {**pv, "ws_id": ws_id, "version": v["n"], "final_version": w.get("final_version")}


def export(ws_id: str, fmt: str, version: str | int | None = None, generated_by: str = "") -> tuple[bytes, str]:
    from backend.dealdesk.paperws import export as EX
    w = _get(ws_id)
    store = ST.default()
    v = store.version(ws_id, _resolve_version(w, version))
    if v is None:
        raise WsError("no such version", 404)
    vers = [x for x in store.versions(ws_id) if x["n"] <= v["n"]]
    pv = PV.build(v["paper"], vers, hooks.rules(_rules_ctx(w, v["paper"])))
    meta = {"version": v["n"], "final": w.get("final_version") == v["n"], "final_version": w.get("final_version"), "ws_id": ws_id,
            "generated_by": generated_by, "versions": vers}
    return EX.docx(v["paper"], pv, meta) if fmt == "docx" else EX.pdf(v["paper"], pv, meta)
