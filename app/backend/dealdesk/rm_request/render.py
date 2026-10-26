"""The business request in Word, in the bank-form layout of bankform/render_bank.py (same helpers: header block on every page, part
banners, the action requested in a ruled box, the facilities table on a landscape page, __key concerns__ bold and underlined,
signature grid), titled BUSINESS REQUEST. House style kept (`backend.house_style.check.docx(data, cover=False) == []`).
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.house_style.bankform import render_bank as RB
from backend.house_style import ACCENT, INK, MUTED, Meta
from backend.house_style import docx as hd

BOXED = ("action",)
LANDSCAPE = ("facilities",)
NEW_PAGE = ("business", "justification")


def _meta(p: dict[str, Any], generated_by: str) -> Meta:
    return Meta(f"Business request · {p['customer']}", book="corporate", period=str(p.get("as_of_label") or ""),
                subject=" · ".join(x for x in (p.get("sector"), p.get("group")) if x), generated_by=generated_by or p.get("rm") or "",
                reference=p["request_id"])


def _header(doc, sec, line, width_cm: float) -> None:
    RB._header_block(doc, sec, line, width_cm)  # noqa: SLF001
    hp = sec.header.paragraphs[0]
    for r in hp.runs:
        if "CREDIT PROPOSAL" in r.text:
            r.text = "BUSINESS REQUEST (BANK FORM) · INTERNAL"


def _landscape(s: dict[str, Any]) -> bool:
    """A section goes on a landscape page only when its table needs it: more than 8 columns or more than 12 rows (R16 X11);
    otherwise the facilities and the security stay on the same portrait page."""
    if s["key"] not in LANDSCAPE:
        return False
    return any(b.get("t") == "table" and (len(b.get("header") or []) > 8 or len(b.get("rows") or []) > 12) for b in s["blocks"])


def parts(p: dict[str, Any]) -> list[dict[str, Any]]:
    by = {s["key"]: s for s in p["sections"]}
    return [{**x, "sections": [by[k] for k in x["sections"] if k in by]} for x in p["parts"]]


def docx(p: dict[str, Any], generated_by: str = "") -> tuple[bytes, str]:
    from docx.shared import Cm, Pt
    doc = hd.document(_meta(p, generated_by), kind="Business request", cover=False)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1.6)
    sec.top_margin, sec.bottom_margin = Cm(3.3), Cm(1.7)
    sec.header_distance, sec.footer_distance = Cm(0.7), Cm(0.8)
    line = [tuple(x) for x in p["header_line"]]
    pw, lw = 21.0 - 3.2, 29.7 - 3.2
    _header(doc, sec, line, pw)
    for r in sec.footer.paragraphs[0].runs:
        if "\t\t" in r.text:
            r.text = r.text.replace("\t\t", "  ·  ")
    by = {s["key"]: s for s in p["sections"]}
    t = doc.add_paragraph()
    RB._runs(t, "BUSINESS REQUEST", size=13, colour=ACCENT, bold=True)  # noqa: SLF001
    RB._runs(t, f"   {p['customer']} · {p['request_id']} · {p.get('as_of_label') or ''}", size=9, colour=MUTED)  # noqa: SLF001
    hd.heading(doc, "1. Header block", 2)
    if "header" in by:
        RB._blocks(doc, doc, by["header"]["blocks"], pw)  # noqa: SLF001
    i = 1
    for pi, part in enumerate(parts(p)):
        if pi and part["key"] in NEW_PAGE:
            hd.page_break(doc)
        RB._banner(doc, part["title"], part["subtitle"], pw)  # noqa: SLF001
        for s in part["sections"]:
            i += 1
            wide = _landscape(s)
            if wide:
                ls = RB._new_section(doc, True)  # noqa: SLF001
                _header(doc, ls, line, lw)
            hd.heading(doc, f"{i}. {s['heading']}", 2)
            if s["key"] in BOXED:
                tb = doc.add_table(rows=1, cols=1)
                RB._borders(tb, INK, 10)  # noqa: SLF001
                RB._widths(tb, [pw - 0.2])  # noqa: SLF001
                cell = tb.rows[0].cells[0]
                cell.paragraphs[0].text = ""
                RB._blocks(cell, doc, s["blocks"], pw - 0.6)  # noqa: SLF001
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            else:
                RB._blocks(doc, doc, s["blocks"], lw if wide else pw)  # noqa: SLF001
            if wide:
                ps = RB._new_section(doc, False)  # noqa: SLF001
                _header(doc, ps, line, pw)
    safe = re.sub(r"[^\w-]+", "-", f"Business-request-{p['customer']}-{p['request_id']}")[:90].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"


def markdown(p: dict[str, Any]) -> str:
    """Plain text of the request (Share note body, tests)."""
    out = [f"# Business request · {p['customer']}", f"{p['request_id']} · {p.get('as_of_label')} · RM {p.get('rm')}", ""]
    for s in p["sections"]:
        out.append(f"## {s['heading']}")
        for b in s["blocks"]:
            if b["t"] in ("p", "h"):
                out.append(b["text"])
            elif b["t"] == "bullets":
                out += [f"- {x}" for x in b["items"]]
            elif b["t"] == "numbered":
                out += [f"{n}. {x}" for n, x in enumerate(b["items"], start=1)]
            elif b["t"] == "table":
                out.append(" | ".join(map(str, b["header"])))
                out += [" | ".join(map(str, r)) for r in b["rows"]]
            elif b["t"] == "kv":
                out += [f"{k}: {v}" for k, v in b["pairs"]]
            elif b["t"] == "sign":
                out.append(" · ".join(f"{r[0]}: {r[1] or '________'}" for r in b.get("rows") or []))
            elif b["t"] == "box":
                out.append(f"{b.get('title') or ''}: ________")
        out.append("")
    return "\n".join(out)
