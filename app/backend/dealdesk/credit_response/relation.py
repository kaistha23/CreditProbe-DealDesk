"""R16 c: the Data Domains relations of the credit response (pure data at module level, in the shape of
backend/dealdesk/data/schema.py; registered there by RELATIONS.update).

    dd_credit_request    one row per line read from an uploaded business request (header field, limit line, security
                         item, term), with the document, reading method and the deal it set up
    dd_credit_response   one row per item of the credit division's response: each flow step's outcome, each query in
                         the RM feedback brief, each numbered recommendation and condition precedent

Folder data/dealdesk/credit-response-v1 (own manifest: no other session's manifest is touched). Demo rows: the committed
snapshot `seed_rows.json` beside this file (the customer 2 run), published by `ops/r16_c_publish_seed.py`.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

FOLDER = "data/dealdesk/credit-response-v1"
PERIOD = "reporting_quarter"
SEED = pathlib.Path(__file__).with_name("seed_rows.json")
SEED_ACTOR = "R16-c:seed"
RUN_ACTOR = "R16-c:credit_response"
MN = "million (deal currency, SAR)"


def _r(label: str, grain: str, keys: list[str], desc: str, cols: list[tuple[str, str, str, str]]) -> dict[str, Any]:
    return {"domain": "deal_desk", "folder": FOLDER, "label": label, "grain": grain, "keys": keys, "period": PERIOD, "description": desc,
            "columns": cols, "owner": "c", "writers": "c (backend/dealdesk/credit_response, at runtime; seed: ops/r16_c_publish_seed.py)"}


RELATIONS: dict[str, dict[str, Any]] = {
    "dd_credit_request": _r("Business requests read", "one row per line read from an uploaded business request", ["line_id", PERIOD],
        "What CreditProbe read from a business request uploaded for a credit response (Word, PDF or photos): the header "
        "fields, every limit line with existing, outstanding and proposed amounts, every security item and every term, "
        "with the document, the reading method and the deal (proposal_id) it set up. The request as received, before credit's view.", [
        ("line_id", "text", "", "Row id <case_id>:<kind>:<seq>."),
        ("case_id", "text", "", "Credit-response case (CRS-...)."),
        ("proposal_id", "text", "", "Deal the request set up (dd_deal.proposal_id)."),
        ("document", "text", "", "File the request was read from (or the photos of its pages)."),
        ("document_sha", "text", "", "SHA-256 (first 16 hex) of the text read."),
        ("method", "text", "", "How it was read: word, pdf text (layout), pdf scan (OCR), image (OCR)."),
        ("line_kind", "text", "", "header, action, facility, total, security or term."),
        ("seq", "int", "", "Order within its kind."),
        ("label", "text", "", "Field label, limit name, security kind or term category."),
        ("group_label", "text", "", "Limit group the security item or term belongs to ('All limits' when general)."),
        ("value_text", "text", "", "The line as read (text)."),
        ("existing_mn", "float", MN, "Existing limit (facility lines)."),
        ("outstanding_mn", "float", MN, "Outstanding (facility lines)."),
        ("proposed_mn", "float", MN, "Proposed limit (facility lines) or the amount of a security item."),
        ("status", "text", "", "Perfection status (security), existing-condition status (terms), level (facilities)."),
        ("read_at", "ts", "", "When the request was read."),
    ]),
    "dd_credit_response": _r("Credit responses", "one row per item of a credit division response", ["item_id", PERIOD],
        "The credit division's response to a business request, item by item: the outcome of each Deal Desk step run on it "
        "(proposal check, review, analysis, structure, stress, stress-proof, recommendation), each query of the feedback "
        "brief to the RM with the bank's evidence, each numbered recommendation and each condition precedent 'prior to "
        "limit loading'. The full paper is rendered from these and the deal's relations (Word and PDF).", [
        ("item_id", "text", "", "Row id <case_id>:<kind>:<seq>."),
        ("case_id", "text", "", "Credit-response case (CRS-...)."),
        ("proposal_id", "text", "", "Deal (dd_deal.proposal_id)."),
        ("customer", "text", "", "Customer name."),
        ("item_kind", "text", "", "step, query, observation, recommendation, condition or decision."),
        ("seq", "int", "", "Order within its kind."),
        ("label", "text", "", "Step name, query section, recommendation number or condition owner."),
        ("text", "text", "", "The item in words (deterministic writer)."),
        ("severity", "text", "", "critical, major, minor or info (queries and observations); blank otherwise."),
        ("status", "text", "", "done or error (steps); open (queries); proposed (recommendations, conditions)."),
        ("value", "float", "", "The item's main number when it has one (score, RAROC %, amount SAR m)."),
        ("unit", "text", "", "Unit of value."),
        ("evidence_relation", "text", "", "Data Domains relation or uploaded document the item rests on."),
        ("due_date", "date", "", "Reply-by date (queries) or deadline (conditions)."),
        ("created_at", "ts", "", "When the response was written."),
    ]),
}


def seed_rows() -> dict[str, list[dict[str, Any]]]:
    if not SEED.exists():
        return {r: [] for r in RELATIONS}
    d = json.loads(SEED.read_text())
    return {r: d.get(r, []) for r in RELATIONS}


def request_rows(c: dict[str, Any]) -> list[dict[str, Any]]:
    req = c["steps"]["read"]["data"]["request"]
    cid, pid, at = c["case_id"], c.get("proposal_id") or "", c["steps"]["read"].get("at")
    base = {"case_id": cid, "proposal_id": pid, "document": req["document"], "document_sha": req.get("sha", ""), "method": req["method"], "read_at": at}
    out = []
    for i, (k, v) in enumerate(sorted(req["header"].items())):
        out.append({**base, "line_id": f"{cid}:header:{i + 1}", "line_kind": "header", "seq": i + 1, "label": k, "group_label": "", "value_text": str(v)[:300]})
    if req["action"].get("text"):
        out.append({**base, "line_id": f"{cid}:action:1", "line_kind": "action", "seq": 1, "label": "Action requested", "group_label": "",
                    "value_text": req["action"]["text"][:1500]})
    for f in req["facilities"]:
        kind = "total" if f.get("total") else "facility"
        out.append({**base, "line_id": f"{cid}:{kind}:{f['seq']}", "line_kind": kind, "seq": f["seq"], "label": f["limit_name"][:200],
                    "group_label": str(f.get("parent") or ""), "value_text": (f.get("particulars") or "")[:300], "existing_mn": f.get("existing_mn"),
                    "outstanding_mn": f.get("outstanding_mn"), "proposed_mn": f.get("proposed_mn"), "status": f"level {f.get('level')}"})
    for s in req["security"]:
        out.append({**base, "line_id": f"{cid}:security:{s['seq']}", "line_kind": "security", "seq": s["seq"], "label": s["kind"], "group_label": s["group"][:120],
                    "value_text": s["text"][:500], "proposed_mn": s.get("amount_mn"), "status": s["perfection_status"]})
    for t in req["terms"]:
        out.append({**base, "line_id": f"{cid}:term:{t['seq']}", "line_kind": "term", "seq": t["seq"], "label": t["category"], "group_label": t["group"][:120],
                    "value_text": t["text"][:600], "status": t["existing_status"]})
    return out


def response_rows(c: dict[str, Any]) -> list[dict[str, Any]]:
    cid, pid, cust = c["case_id"], c.get("proposal_id") or "", c.get("customer") or ""
    at = (c["steps"].get("response") or {}).get("at")
    out = []

    def add(kind: str, seq: int, label: str, text: str, **kw: Any) -> None:
        out.append({"item_id": f"{cid}:{kind}:{seq}", "case_id": cid, "proposal_id": pid, "customer": cust, "item_kind": kind, "seq": seq,
                    "label": label[:200], "text": text[:1500], "created_at": at, **kw})
    for i, (k, st) in enumerate(c["steps"].items()):
        add("step", i + 1, st.get("label") or k, st.get("headline") or "; ".join(st.get("plain_words") or [])[:600], status=st.get("status"),
            value=st.get("seconds"), unit="seconds", evidence_relation="")
    b = (c["steps"].get("brief") or {}).get("data") or {}
    for q in b.get("items") or []:
        add("query", q["n"], q.get("section") or "", q["query"], severity=q.get("severity"), status="open", evidence_relation=q.get("source") or "",
            due_date=b.get("due"))
    s = ((c["steps"].get("response") or {}).get("data") or {}).get("summary") or {}
    if s.get("decision"):
        add("decision", 1, "Credit division recommendation", s["decision"], status="proposed")
    for i, t in enumerate(s.get("recommendation") or []):
        add("recommendation", i + 1, f"Recommendation {i + 1}", t, status="proposed")
    for i, t in enumerate(s.get("conditions") or []):
        add("condition", i + 1, "Prior to limit loading", t, status="proposed")
    for i, o in enumerate(s.get("observations") or []):
        add("observation", i + 1, o.get("title", "")[:200], o.get("text", ""), severity=o.get("severity"), evidence_relation=o.get("source") or "")
    return out


def publish_case(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.data import store
    out = {}
    for rel, rows in (("dd_credit_request", request_rows(c)), ("dd_credit_response", response_rows(c))):
        if rows:
            out[rel] = store.publish(rel, rows, mode="replace_where", where={"case_id": c["case_id"]}, actor=RUN_ACTOR)["rows"]
    return out
