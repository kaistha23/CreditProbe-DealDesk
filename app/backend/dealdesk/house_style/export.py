"""P5: the drafted proposal in Word, in the house's own structure (the report_docx pattern: backend.house_style.docx).

Section headings and order follow the house profile; figures keep their citation ([F3]) and the last page lists every cited
fact with its source. A judgement section the RM has not accepted carries the note that it is a suggestion.
"""
from __future__ import annotations

import re
from typing import Any

from backend.house_style import Meta
from backend.house_style import docx as hd


def build(d: dict[str, Any], generated_by: str = "") -> tuple[bytes, str]:
    m = d["meta"]
    meta = Meta(d["title"], book="corporate", period="", subject=f"{m['sector']} · {m['rating']} · {d['profile']['bank_label']} house style",
                generated_by=generated_by, reference=d["draft_id"])
    doc = hd.document(meta, kind="Credit proposal (draft)", subtitle=m["name"], cover="block")
    sc = d.get("score") or {}
    if sc:
        hd.note(doc, f"House-style score {sc['total']} (band {sc['band']['low']}–{sc['band']['high']}, {sc['band'].get('basis', '')}). "
                     f"Drafted from data; every figure cites its source.")
    for i, s in enumerate(d["sections"], start=1):
        hd.heading(doc, f"{i}. {s['heading']}")
        if s.get("judgement") and s.get("status") != "accepted":
            hd.note(doc, "Suggestion for the RM's judgement: to be confirmed or changed before submission.")
        for p in s.get("paragraphs", []):
            hd.para(doc, p)
        if s.get("bullets"):
            hd.bullets(doc, s["bullets"])
        t = s.get("table")
        if t and t.get("rows"):
            hd.table(doc, t["header"], t["rows"], gap=False, size=8)
            if t.get("cites"):
                hd.note(doc, "Source: " + ", ".join(t["cites"][:6]) + (f"; {t['source']}" if t.get("source") else ""))
    cited = {c for s in d["sections"] for c in re.findall(r"\[(F\d+)\]", " ".join(s.get("paragraphs", []) + s.get("bullets", [])))}
    cited |= {c for s in d["sections"] for c in ((s.get("table") or {}).get("cites") or [])}
    rows = [[f["id"], f["label"], f["display"], f["source"] + (f" ({f['derived']})" if f.get("derived") else "")]
            for f in d["facts"] if f["id"] in cited]
    if rows:
        hd.page_break(doc)
        hd.heading(doc, "Sources of the figures")
        hd.table(doc, ["Ref", "Item", "Value", "Source"], rows, gap=False, size=7.5)
    safe = re.sub(r"[^\w-]+", "-", f"Draft-proposal-{m['pid']}-{m['name']}")[:80].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"
