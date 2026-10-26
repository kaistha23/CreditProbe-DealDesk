"""/api/v1/dealdesk/rules: the analysts' rules (Round K).

    GET    /rules                         the rules the signed-in user sees (theirs, their team's, the bank's); ?scope= ?document=
                                          ?mine=1 (only theirs) ?status=all
    POST   /rules/suggest                 {instruction, section?, section_label?, document?} -> the rule CreditProbe would save, or
                                          why it would not ask (a one-off about this deal; a rule they already have)
    POST   /rules                         {instruction? | text, kind?, params?, scope, document, section?, section_label?, source?}
    PATCH  /rules/{id}                    {text?, scope?, document?, section?, status?}   (author, team, or the bank's owners)
    DELETE /rules/{id}                    status -> removed (kept on record with its history)
    GET    /rules/{id}/history            every change: who, when, before, after
    GET    /rules/for-document?document=  the active rules that apply when the signed-in user writes that document
    POST   /rules/apply                   {document, doc} -> the doc with the rules applied and "Rules applied" (Round W calls it)
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk.rules import apply as AP
from backend.dealdesk.rules import classify as CL
from backend.dealdesk.rules import hook, store

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-rules"])
ASK = "Save this as a rule for your future documents?"


def _who(request: Request) -> str:
    u = hook.username(request)
    if not u:
        raise HTTPException(401, "Sign in to keep rules: a rule is stored with its author.")
    return u


def _out(r: dict[str, Any], user: str) -> dict[str, Any]:
    return {**r, "kind_label": CL.KIND_LABEL.get(r["kind"], r["kind"]), "can_edit": store.can_edit(r, user),
            "deterministic": r["kind"] != "instruction"}


def _err(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except store.NotFound as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "Not found.") from None
    except store.Forbidden as e:
        raise HTTPException(403, str(e)) from None
    except (store.Invalid, ValueError) as e:
        raise HTTPException(422, str(e)) from None


@router.get("/rules")
def list_rules(request: Request, scope: str = Query(""), document: str = Query(""), mine: bool = Query(False),
               status: str = Query(""), origin: str = Query("")) -> dict[str, Any]:
    user = hook.username(request)
    rows = store.listing(scope=scope, document=document, author=user if mine else "", status=status, visible_to=user or "-", origin=origin)
    me = store.person(user) if user else {"username": "", "name": "", "team": ""}
    counts = {s: sum(1 for r in rows if r["scope"] == s) for s in store.SCOPES}
    return {"rules": [_out(r, user) for r in rows], "counts": counts, "user": me,
            "scopes": [{"id": k, "label": v} for k, v in store.SCOPE_LABEL.items()],
            "documents": [{"id": k, "label": v} for k, v in store.DOCUMENT_LABEL.items()],
            "kinds": [{"id": k, "label": v} for k, v in CL.KIND_LABEL.items()]}


FIGURE = re.compile(r"\d")


def _same(a: dict[str, Any], kind: str, params: dict[str, Any], text: str) -> bool:
    if a["kind"] != kind:
        return False
    if kind == "instruction":
        return re.sub(r"\W+", " ", a["text"]).strip().lower() == re.sub(r"\W+", " ", text).strip().lower()
    norm = lambda d: {k: (str(v).lower() if isinstance(v, str) else v) for k, v in (d or {}).items()}  # noqa: E731
    return norm(a["params"]) == norm(params)


@router.post("/rules/suggest")
def suggest(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """What "Save this as a rule?" offers after an instruction. CreditProbe does not ask when the instruction is about this
    deal only (it carries a figure and no general rule can be read from it) or when the analyst already has the rule."""
    instruction = str(body.get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(422, "instruction: the analyst's instruction.")
    document = str(body.get("document") or "both")
    if document not in store.DOCUMENTS:
        document = "both"
    section, label = str(body.get("section") or ""), str(body.get("section_label") or "")
    s = CL.classify(instruction, section, label, use_model=bool(body.get("use_model", True)))
    user = hook.username(request)
    existing = [r for r in store.listing(status="active", visible_to=user or "-") if _same(r, s["kind"], s["params"], s["text"])]
    one_off = s["kind"] == "instruction" and bool(FIGURE.search(instruction))
    ask = not existing and not one_off and len(instruction.split()) >= 2
    who = {"me": "You have", "team": "Your team has", "bank": "The bank has"}.get(existing[0]["scope"], "You have") if existing else ""
    why = (f"{who} this rule already ({existing[0]['id']}): it is applied to every document you write." if existing else
           "This instruction is about this deal's figures, so it is not offered as a rule." if one_off else "")
    return {"ask": ask, "question": ASK if ask else "", "why_not": why, "suggestion": {**s, "document": document, "section_label": label,
            "scope": "me"}, "existing": [_out(r, user) for r in existing],
            "scopes": [{"id": k, "label": v} for k, v in store.SCOPE_LABEL.items()],
            "documents": [{"id": k, "label": v} for k, v in store.DOCUMENT_LABEL.items()]}


@router.post("/rules")
def create(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    user = _who(request)
    instruction = str(body.get("instruction") or "").strip()
    text = str(body.get("text") or "").strip()
    if not instruction and not text:
        raise HTTPException(422, "text: write the rule (or send the instruction it comes from).")
    section, label = str(body.get("section") or ""), str(body.get("section_label") or "")
    kind, params = body.get("kind"), body.get("params")
    method = "given"
    if kind not in CL.KINDS or not isinstance(params, dict):
        s = CL.classify(instruction or text, section, label, use_model=bool(body.get("use_model", True)))
        kind, params, method = s["kind"], s["params"], s["method"]
        text = text or s["text"]
        section = section or (s["section"] if kind in ("wording", "avoid", "must_mention", "heading", "table") else "")
    r = _err(store.create, text=text, kind=kind, params=params, scope=str(body.get("scope") or "me"), document=str(body.get("document") or "both"),
             section=section, section_label=label, author=user, source_instruction=instruction,
             source=body.get("source") if isinstance(body.get("source"), dict) else {}, origin="analyst", method=method)
    return {"rule": _out(r, user), "message": f"Saved. From now on it is applied to every {r['document_label'].lower()} "
                                              f"{'you write' if r['scope'] == 'me' else 'your team writes' if r['scope'] == 'team' else 'the bank writes'}."}


@router.get("/rules/for-document")
def for_document(request: Request, document: str = Query("proposal")) -> dict[str, Any]:
    user = hook.username(request)
    rows = store.for_document(user, document)
    return {"document": document, "rules": [_out(r, user) for r in rows], "instructions": AP.instructions(rows)}


@router.post("/rules/apply")
def apply_rules(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    doc = body.get("doc")
    if not isinstance(doc, dict) or not isinstance(doc.get("sections"), list):
        raise HTTPException(422, "doc: a document with sections.")
    document = str(body.get("document") or "proposal")
    return hook.apply_to(doc, hook.username(request), document, model_used=bool(body.get("model_used")))


@router.patch("/rules/{rule_id}")
def patch(rule_id: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    user = _who(request)
    changes = dict(body)
    if "text" in changes and "kind" not in changes:  # a reworded rule is read again (its kind may change)
        cur = _err(store.get, rule_id)
        s = CL.classify(str(changes["text"]), cur["section"], cur["section_label"], use_model=False)
        if s["kind"] != "instruction" or cur["kind"] == "instruction":
            changes["kind"], changes["params"] = s["kind"], s["params"]
    act = "paused" if changes.get("status") == "paused" else "resumed" if changes.get("status") == "active" else "edited"
    return {"rule": _out(_err(store.update, rule_id, changes, user, act), user)}


@router.delete("/rules/{rule_id}")
def delete(rule_id: str, request: Request) -> dict[str, Any]:
    user = _who(request)
    return {"rule": _out(_err(store.remove, rule_id, user), user), "message": "Removed. It stays on record with its history."}


@router.get("/rules/{rule_id}/history")
def history(rule_id: str) -> dict[str, Any]:
    return {"rule_id": rule_id, "events": _err(store.history, rule_id)}


hook.register_with_paper_workspace()  # Round W's "Rules applied" and provenance read this store once both are merged
