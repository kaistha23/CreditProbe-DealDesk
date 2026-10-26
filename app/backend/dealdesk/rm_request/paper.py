"""Assemble the business request.

    p = write(cf, ask_text, notes_text, rm="Anne")     # deterministic: the same inputs give the same paper (N4)
    p["sections"]   [{key, n, heading, voice, part, blocks, gaps}]  (the bankform content model, blocks.py)
    p["figures"]    every figure printed, with the section, label and source (document id or Data Domains relation and row)
    p["notes_used"] each RM note line and the section it was placed in
    p["plain_words"] the 3-4 line block on top of the panel
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.dealdesk.rm_request import ask as A
from backend.dealdesk.rm_request import inputs as I
from backend.dealdesk.rm_request import writers as WR

PARTS = [("action", "ACTION REQUESTED", "Business · Corporate Banking Group", ("action", "facilities", "security", "terms")),
         ("business", "BUSINESS COMMENTS", "Business · relationship manager", ("group_exposure", "counterparty", "background", "relationship", "financials", "documents")),
         ("justification", "RM'S JUSTIFICATION", "Business · relationship manager", ("justification",)),
         ("approvals", "BUSINESS APPROVALS", "RM · Unit head · Regional head", ("signatures",))]


def request_id(customer: dict[str, Any], ask_text: str, notes_text: str) -> str:
    h = hashlib.sha1(json.dumps([customer.get("proposal_id") or customer.get("key"), ask_text.strip(), notes_text.strip()]).encode()).hexdigest()[:8]
    return f"BR-{customer.get('proposal_id') or customer.get('key')}-{h}".upper()


def write(cf: dict[str, Any], ask_text: str, notes_text: str = "", rm: str = "", written: str = I.AS_OF) -> dict[str, Any]:
    existing = [{"facility": r.get("limit_name"), "limit": WR.num(r.get("existing_mn")), "outstanding": WR.num(r.get("outstanding_mn"))}
                for r in WR.top_limits((cf.get("bank") or {}).get("dd_facility_limit", []))]
    ask = A.parse_ask(ask_text, existing)
    notes = A.parse_notes(notes_text)
    w = WR.W(cf, ask, notes, rm=rm, written=written)
    secs = []
    placed: dict[int, str] = {}
    for key, n, heading, voice, fn in WR.SECTIONS:
        w.section = key
        before = set(w.used_notes)
        try:
            blocks, gaps = fn(w)
            method = "deterministic"
        except Exception as e:  # noqa: BLE001 - one section's data problem never takes the request down
            blocks, gaps, method = [{"t": "p", "text": f"{heading}: not available ({type(e).__name__}: {str(e)[:80]}).", "exempt": False}], [f"writer error {type(e).__name__}"], "error"
        if key in WR.OPTIONAL and not blocks:  # Round G: an optional section with nothing to say is left out
            continue
        for i in w.used_notes - before:
            placed[i] = heading
        secs.append({"key": key, "n": n, "heading": heading, "voice": voice, "part": "anatomy" if n else "business", "blocks": blocks,
                     "gaps": gaps, "method": method})
    c = cf["customer"]
    rows = WR.facility_rows(WR.W(cf, ask, notes, rm=rm, written=written))
    te, tp = WR._total(rows, "existing"), WR._total(rows, "proposed")  # noqa: SLF001
    rid = request_id(c, ask_text, notes_text)
    cl = I.checklist(cf)
    paper = {
        "request_id": rid, "proposal_id": c.get("proposal_id") or rid, "kind": "business_request", "title": f"Business request · {c.get('name')}",
        "customer": c.get("name"), "customer_key": c.get("key"), "cif": c.get("cif") or "", "cr_number": c.get("cr_number"), "group": c.get("group_name") or "",
        "sector": c.get("sector") or "", "existing": bool(c.get("existing")), "currency": "SAR", "as_of": written, "as_of_label": WR.dt(written),
        "rm": rm or "Relationship manager", "ask_text": ask_text, "notes_text": notes_text, "ask": ask, "notes": notes,
        "totals": {"existing": te, "proposed": tp, "change": (tp - (te or 0)) if tp is not None else None},
        "sections": secs, "parts": [{"key": k, "title": t, "subtitle": s, "sections": [x for x in keys if any(z["key"] == x for z in secs)]} for k, t, s, keys in PARTS],
        "figures": w.figures, "notes_used": [{"text": ln["text"], "topic": ln["topic"], "section": placed.get(i, "RM's justification")}
                                              for i, ln in enumerate(notes["lines"])],
        "checklist": {"received": sum(1 for x in cl if x["status"] == "received"), "expired": sum(1 for x in cl if x["status"] == "expired"),
                      "missing": sum(1 for x in cl if x["status"] == "missing"), "total": len(cl)},
        "origin": cf.get("origin"), "gaps": [{"section": s["key"], "heading": s["heading"], "missing": s["gaps"]} for s in secs if s["gaps"]],
        "header_line": [("Customer", c.get("name") or ""), ("CIF", c.get("cif") or "new to bank"), ("CR", c.get("cr_number") or ""),
                        ("Group", c.get("group_name") or "–"), ("Date", WR.dt(written)), ("RM", rm or "RM"), ("Request", _kind(ask)), ("Ref", rid)],
    }
    paper["disclosures"] = next((b["items"] for s in secs if s["key"] == "justification" for i, b in enumerate(s["blocks"])
                                 if b["t"] == "bullets" and i > 0 and s["blocks"][i - 1].get("text") == "Points disclosed for credit's review"), [])
    paper["plain_words"] = plain_words(paper)
    paper["untraced"] = [f for f in w.figures if f["source"] == "not traced"]
    return paper


def _kind(ask: dict[str, Any]) -> str:
    acts = [i["action"] for i in ask.get("items", [])]
    names = {"renew": "Renewal", "increase": "Increase", "new": "New limit", "takeover": "Takeover", "reduce": "Reduction", "cancel": "Cancellation"}
    return " + ".join(dict.fromkeys(names[a] for a in acts if a in names)) or "–"


def plain_words(p: dict[str, Any]) -> list[str]:
    """3-4 lines, at most 60 words, every line with a number (the shared plain-words rule)."""
    t = p["totals"]
    n_items = len(p["ask"].get("items", []))
    mv = (f"limits from SAR {t['existing']:,.1f}m to SAR {t['proposed']:,.1f}m" if t.get("existing") else f"limits of SAR {t['proposed']:,.1f}m") \
        if t.get("proposed") is not None else "no limits sized yet"
    used = len(p["notes_used"])
    ck = p["checklist"]
    return [f"Business request in the bank's form: {n_items} facilit{'y' if n_items == 1 else 'ies'}, {mv}.",
            f"{used} RM note{'s' if used != 1 else ''} placed where {'they belong' if used != 1 else 'it belongs'}, in the RM's voice." if used
            else "0 RM notes typed: add them and write again.",
            f"Documents: {ck['received']} received, {ck['expired']} expired, {ck['missing']} missing; {len(p['disclosures'])} points disclosed for credit.",
            f"Each of the {len(p['figures'])} figures names its document or bank record: open Trace."]
