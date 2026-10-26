"""The feedback brief to the RM: every query credit has on the business request, numbered, critical first, each with the
bank's evidence and its source, and one reply-by date. Deterministic; the reviewer edits it before sending.

Queries come from (one engine per fact):
  the request as read (sections or totals that could not be read)          request.read_gaps
  the proposal check of the request against the bank's data              flow step "check"   (proposal_check engine)
  the customer file read together (intake reconciliation, checklist)       session i's intake facts
  the deal's analysis (capacity, hurdle, stress, stress-proof)             flow steps "analysis", "structure", "stress", "proof"
  credit's own reading of the documents (extension of time, statements)   response.observations
"""
from __future__ import annotations

import datetime as dt
import io
from typing import Any

SEV = {"critical": 0, "major": 1, "minor": 2, "info": 3}
LABEL = {"critical": "Critical: needed before the request can go to approval", "major": "Major", "minor": "Minor", "info": "For information"}


def due_date(today: dt.date | None = None, days: int = 3) -> str:
    from backend.dealdesk.credit_response.projects import as_of
    d = (today or as_of()) + dt.timedelta(days=days)
    while d.weekday() in (4, 5):  # Friday, Saturday: the next working day
        d += dt.timedelta(days=1)
    return d.isoformat()


def _items(c: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.dealdesk.credit_response import response as RS
    st = c["steps"]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(sev: str, section: str, title: str, query: str, evidence: str = "", source: str = "") -> None:
        k = title.lower()[:60]
        if k in seen:
            return
        seen.add(k)
        out.append({"severity": sev, "section": section, "title": title, "query": query, "evidence": evidence, "source": source})
    req = st["read"]["data"]["request"]
    for g in req.get("read_gaps") or []:
        add("major", "Business request", g, f"Please resend the request with this part legible or complete: {g}.", source=req["document"])
    # credit's reading of the documents and the file (observations carry their own query)
    for o in RS.observations(c):
        if o.get("query"):
            add(o["severity"], o.get("section") or "Credit comments", o["title"], o["query"], o.get("text", ""), o.get("source", ""))
    # the proposal check's queries on the request
    chk = (st.get("check") or {}).get("data") or {}
    ev = {d.get("title"): d for d in chk.get("defects") or []}
    for q in chk.get("queries") or []:
        d = ev.get(q.get("title")) or {}
        add(q.get("severity") or "minor", f"{q.get('section')}. {q.get('heading')}" if q.get("section") else "Business request", q.get("title") or "",
            q.get("query") or "", d.get("evidence") or "", d.get("evidence_relation") or "")
    return out


def build(c: dict[str, Any]) -> dict[str, Any]:
    items = sorted(_items(c), key=lambda x: (SEV.get(x["severity"], 4),))
    due = due_date()
    for i, it in enumerate(items):
        it["n"] = i + 1
    groups = [{"severity": s, "label": LABEL[s], "items": [x for x in items if x["severity"] == s]} for s in SEV if any(x["severity"] == s for x in items)]
    req = c["steps"]["read"]["data"]["request"]
    cust = req["fields"].get("name") or c.get("customer") or "the customer"
    rm = req["fields"].get("rm") or "Relationship manager"
    crit = sum(1 for x in items if x["severity"] == "critical")
    major = sum(1 for x in items if x["severity"] == "major")
    rec = ((c["steps"].get("recommendation") or {}).get("data") or {})
    subject = f"{cust}: {len(items)} queries on the business request (reply by {due})"
    lines = [f"To: {rm}", f"Subject: {subject}", "",
             f"Credit has read the business request for {cust} ({req['document']}, received {req['header'].get('date') or 'undated'}) with the "
             f"{len(c['steps']['read']['data']['documents'])} documents uploaded and the bank's own data. Please answer the {len(items)} queries below by {due}"
             + (f"; the {crit} critical one{'s' if crit != 1 else ''} first: the request cannot go to approval without them." if crit else "."),
             ""]
    if rec.get("decision"):
        lines += [f"Where credit stands today: {rec['decision']}" + (f" ({rec.get('why')})" if rec.get("why") else "") + ".", ""]
    for g in groups:
        lines.append(g["label"])
        for it in g["items"]:
            lines.append(f"{it['n']}. {it['section']}: {it['title']}")
            lines.append(f"   Query: {it['query']}")
            if it["evidence"]:
                lines.append(f"   What credit sees: {it['evidence']}" + (f" (source: {it['source']})" if it["source"] else ""))
        lines.append("")
    lines.append("Credit division")
    pw = [f"{len(items)} queries for the RM ({crit} critical, {major} major), reply by {due}.",
          "Each query says what credit saw and where (the document or the bank's data), so the RM can answer it line by line."]
    return {"to": rm, "subject": subject, "due": due, "count": len(items), "critical": crit, "major": major, "groups": groups, "items": items,
            "text": "\n".join(lines).strip(), "plain_words": pw}


def docx(c: dict[str, Any]) -> tuple[bytes, str]:
    from backend.house_style import Meta
    from backend.house_style import docx as hd
    b = (c["steps"].get("brief") or {}).get("data") or build(c)
    req = c["steps"]["read"]["data"]["request"]
    cust = req["fields"].get("name") or c.get("customer") or "Customer"
    pid = c.get("proposal_id") or ""
    meta = Meta(f"Feedback to the RM · {cust}", book="corporate", period=f"reply by {b['due']}", subject=f"Business request {req['document']}",
                generated_by="Credit division (CreditProbe)", reference=f"{pid}-RMB")
    doc = hd.document(meta, kind="Feedback brief", cover=False)
    hd.para(doc, f"To: {b['to']}", bold=True)
    hd.para(doc, f"Subject: {b['subject']}", bold=True)
    head = b["text"].split("\n\n")[1] if "\n\n" in b["text"] else ""
    if head:
        hd.para(doc, head.replace("\n", " "))
    hd.key_figures(doc, [("Queries", str(b["count"])), ("Critical", str(b["critical"])), ("Reply by", b["due"])])
    for g in b["groups"]:
        hd.heading(doc, g["label"], 2)
        hd.table(doc, ["#", "Section", "Query", "What credit sees (source)"],
                 [[str(it["n"]), it["section"], f"{it['title']}: {it['query']}", (it["evidence"] + (f" ({it['source']})" if it["source"] else "")).strip()]
                  for it in g["items"]], widths=[1.0, 3.2, 6.6, 6.6])
    hd.para(doc, "Credit division", bold=True)
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue(), f"RM_feedback_{pid or 'request'}.docx"
