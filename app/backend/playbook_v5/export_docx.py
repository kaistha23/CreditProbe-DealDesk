"""A Playbook report as a house-style Word document: cover, contents, sections, tables, charts, verdicts, sources."""
from __future__ import annotations

from typing import Any

from backend.playbook_v5 import charts, formats, house


def _block(doc, b: dict[str, Any]) -> None:
    k = b["kind"]
    if k == "paragraph":
        for chunk in [p for p in b["text"].split("\n\n") if p.strip()]:
            house.para(doc, chunk.strip())
    elif k == "heading":
        doc.add_heading(b["text"], level=3 if b.get("level") == 3 else 2)
    elif k == "bullets":
        house.bullets(doc, b["items"])
    elif k == "callout":
        house.callout(doc, b["text"], b.get("tone", "info"))
    elif k == "kpis":
        items = b["items"]
        rows = [[i["label"], formats.value(i.get("value"), i["format"]),
                 formats.delta(i.get("delta"), i["format"]) if i.get("delta") is not None else "",
                 house.RAG[i["status"]][2] if i.get("status") else ""] for i in items]
        fills = [[None, None, None, house.RAG[i["status"]][0] if i.get("status") else None] for i in items]
        inks = [[None, None, None, house.RAG[i["status"]][1] if i.get("status") else None] for i in items]
        house.table(doc, ["Key figure", "Value", "Change", "Status"], rows, numeric=[False, True, True, False],
                    fills=fills, inks=inks)
    elif k == "table":
        if b.get("title"):
            house.label(doc, b["title"])
        cols = b["columns"]
        rows = [[formats.value(r.get(c["key"]), c["format"]) for c in cols] for r in b["rows"]]
        house.table(doc, [c["label"] for c in cols], rows, numeric=[c["format"] in formats.NUMERIC for c in cols])
        if b.get("note"):
            house.caption(doc, b["note"])
    elif k == "chart":
        img = charts.block_png(b)
        if img:
            house.figure(doc, img, b.get("note") or b.get("title") or "")
        else:
            house.caption(doc, f"[Chart: {b.get('title') or 'figure'}; open the report in CreditProbe to view it.]")
    elif k == "rag":
        if b.get("title"):
            house.label(doc, b["title"])
        items = b["items"]
        rows = [[i["test"], formats.value(i.get("value"), i["format"]), i["threshold"], house.RAG[i["status"]][2],
                 i.get("comment", "")] for i in items]
        fills = [[None, None, None, house.RAG[i["status"]][0], None] for i in items]
        inks = [[None, None, None, house.RAG[i["status"]][1], None] for i in items]
        house.table(doc, ["Test", "Result", "Threshold", "Verdict", "Comment"], rows,
                    numeric=[False, True, False, False, False], fills=fills, inks=inks)


def build(report: dict[str, Any], generated_by: str = "") -> bytes:
    owner = (report.get("owner") or {}).get("name", "")
    reviewers = ", ".join(p["name"] for p in report.get("reviewers") or [])
    book = {"corporate": "Corporate book", "retail": "Retail book", "both": "Corporate and retail books"}.get(
        report.get("book") or "", "")
    meta = [("Document", report.get("template_name", "")), ("Status", report.get("status_label", "")),
            ("Version", str(report.get("version", ""))), ("Owner", owner), ("Reviewers", reviewers or "—"),
            ("Due", report.get("due_date") or "—")]
    if book:
        meta.insert(1, ("Book", book))
    if report.get("period"):
        meta.insert(2 if book else 1, ("Period", report["period"]))
    doc = house.new_document(report["title"], report.get("template_name", ""), meta,
                             kind=report.get("template_name", "Report"), generated_by=generated_by)
    house.contents(doc)
    sources: list[dict[str, Any]] = []
    for n, s in enumerate(report.get("sections") or [], start=1):
        doc.add_heading(f"{n}. {s['title']}", level=1)
        if not s.get("blocks"):
            house.caption(doc, "This section has not been drafted yet.")
        for b in s.get("blocks") or []:
            _block(doc, b)
        if s.get("source"):
            src = s["source"]
            sources.append({"n": n, **src})
            house.caption(doc, f"Source: {src.get('label', '')} (CreditProbe {src.get('href', '')})")
    hist = report.get("history") or []
    if sources or hist:
        doc.add_heading("Appendix: sources and approvals", level=1)
    if sources:
        doc.add_heading("Sources", level=2)
        house.table(doc, ["Section", "Imported from", "Where in CreditProbe"],
                    [[str(s["n"]), s.get("label", ""), s.get("href", "")] for s in sources], widths=[2, 7, 7])
    if hist:
        doc.add_heading("Status history", level=2)
        house.table(doc, ["When", "Who", "From", "To", "Note"],
                    [[h["at"][:16].replace("T", " "), (h.get("who") or {}).get("name", ""),
                      (h.get("from") or "").replace("_", " ").capitalize(), h["to"].replace("_", " ").capitalize(),
                      h.get("note", "")] for h in hist])
    return house.save(doc)
