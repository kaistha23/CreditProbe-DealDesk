"""R11 R1: the claims ledger. A credit memo (.docx) read into ordered lines and structured claims.

Each memo line keeps its section and its source text. Each claim is either
  * a figure: a number with its unit (AED m, SAR m, %, x, days, months, years, a date), the label it is
    attached to (the table row label, or the words before it in a sentence) and a stable key, or
  * an assertion: what the memo claims in words ("retentions not due", "approve all", "CRO box empty"),
    matched by the configurable phrase patterns in data/dealdesk/review/claims.json.

The reader is deterministic and model-free: the same memo always gives the same ledger.
"""
from __future__ import annotations

import functools
import io
import json
import re
from typing import Any

from backend.dealdesk import paths

REVIEW_DIR = paths.DATA / "review"


@functools.lru_cache(maxsize=1)
def claim_patterns() -> list[dict[str, Any]]:
    return json.loads((REVIEW_DIR / "claims.json").read_text())["assertions"]


def reload() -> None:
    claim_patterns.cache_clear()


# ------------------------------------------------------------------ docx -> lines

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]


def read_lines(data: bytes) -> list[dict[str, Any]]:
    """The memo's paragraphs and table rows in document order, each with its section."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    lines: list[dict[str, Any]] = []
    section = "Cover"
    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            txt = p.text.strip()
            if not txt:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            if style.startswith("Heading") or style == "Title":
                section = re.sub(r"^\d+\.\s*", "", txt)
                lines.append({"kind": "heading", "section": section, "text": txt})
                continue
            if txt.upper() == txt and len(txt) < 30:
                continue  # running header such as "CREDIT MEMO"
            lines.append({"kind": "text", "section": section, "text": txt})
        elif tag == "tbl":
            t = Table(child, d)
            rows = []
            for r in t.rows:
                seen: set[int] = set()
                cells = []
                for c in r.cells:  # a merged cell repeats the same element: keep it once
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(c.text.strip())
                rows.append(cells)
            if not rows:
                continue
            head = rows[0]
            for r in rows[1:] if len(rows) > 1 else rows:
                if not any(r) or len(r) < 2:
                    continue
                lines.append({"kind": "row", "section": section, "text": " | ".join(x for x in r), "cells": r, "header": head})
    for i, ln in enumerate(lines):
        ln["line_id"] = f"L{i + 1:03d}"
    return lines


# ------------------------------------------------------------------ figures

_NUM = r"-?\d[\d,]*(?:\.\d+)?"
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_FIG = re.compile(
    rf"(?P<date>\b\d{{1,2}}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b)"
    rf"|(?P<ccy>AED|SAR|USD)\s*(?P<camt>{_NUM})\s*(?P<cscale>bn|m|million|billion)?"
    rf"|(?P<amt>{_NUM})\s*(?P<unit>%|x\b|bps\b|days\b|months?\b|years?\b|bn\b|m\b)", re.I)


def _date(s: str) -> str | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", s)
    if m:
        return f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


def _figures(text: str, default_unit: str = "") -> list[dict[str, Any]]:
    out = []
    for m in _FIG.finditer(text):
        if m.group("date"):
            out.append({"value": _date(m.group("date")), "unit": "date", "raw": m.group(0), "pos": m.start()})
        elif m.group("ccy"):
            v = float(m.group("camt").replace(",", ""))
            sc = (m.group("cscale") or "m").lower()
            if sc in ("bn", "billion"):
                v *= 1000
            out.append({"value": v, "unit": f"{m.group('ccy').upper()} m", "raw": m.group(0), "pos": m.start()})
        else:
            v = float(m.group("amt").replace(",", ""))
            u = m.group("unit").lower()
            if u == "bn":
                v, u = v * 1000, (default_unit or "m")
            elif u == "m":
                u = default_unit or "m"
            u = {"month": "months", "year": "years"}.get(u, u)
            out.append({"value": v, "unit": u, "raw": m.group(0), "pos": m.start()})
    return out


def _unit_of_section(section: str) -> str:
    m = re.search(r"\((AED|SAR|USD)\s*(?:m|million)\)", section, re.I)
    return f"{m.group(1).upper()} m" if m else ""


def _bare_numbers(cell: str) -> list[float]:
    if re.search(r"[A-Za-z]{3,}", cell.replace("bps", "").replace("SAIBOR", "")):
        return []
    return [float(x.replace(",", "")) for x in re.findall(_NUM, cell)]


#: Identifiers and cover fields that are not claims.
SKIP_LABELS = r"^(?:cr number|obligor id|reference|sector code|period|generated|classification|book|scope|prepared by|id|field|term|item)$"


def claims(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every figure and every assertion, with its line and section."""
    out: list[dict[str, Any]] = []
    sec_unit = ""

    def add(**k: Any) -> None:
        out.append({"claim_id": f"C{len(out) + 1:03d}", **k})

    for ln in lines:
        if ln["kind"] == "heading":
            sec_unit = _unit_of_section(ln["text"])
            continue
        if ln["kind"] == "row":
            cells, head = ln["cells"], ln.get("header") or []
            label = cells[0]
            if re.search(SKIP_LABELS, label, re.I):
                continue
            row_unit = _unit_of_section(label) or sec_unit
            for j, cell in enumerate(cells[1:], start=1):
                col = head[j] if j < len(head) and head[j] != label else ""
                unit = "bps" if "bps" in col.lower() else ("x" if re.search(r"\(x\)", label) else row_unit)
                figs = _figures(cell, unit)
                lead = re.match(rf"\s*({_NUM})(?![\d.,])(?!\s*(?:%|x\b|bps|days|months?|years?))", cell)
                if lead and not re.match(r"\s*\d{4}-\d{2}", cell) and not re.search(r"[A-Za-z]{2,}\d|\d[A-Za-z]{2,}", cell.split()[0] if cell.split() else ""):
                    figs = [{"value": float(lead.group(1).replace(",", "")), "unit": unit or "", "raw": lead.group(1)}] + \
                           [f for f in figs if f.get("pos", 0) > lead.end()]
                for k, f in enumerate(figs):
                    key = _slug(label) + (f"@{_slug(col)}" if col and col.lower() not in ("value", "amount") else "") + (f"#{k + 1}" if k else "")
                    add(line_id=ln["line_id"], section=ln["section"], kind="figure", label=label, column=col, key=key,
                        value=f["value"], unit=f["unit"], raw=f["raw"], text=ln["text"],
                        claims=f"{label}{(' (' + col + ')') if col else ''} = {f['raw']}")
        else:
            figs = _figures(ln["text"], sec_unit)
            for k, f in enumerate(figs):
                before = ln["text"][: f.get("pos", 0)]
                label = re.split(r"[;:.,]\s*", before.strip())[-1].strip() or ln["text"][:40]
                key = _slug(ln["section"]) + "." + _slug(label)[:40] + (f"#{k + 1}" if k else "")
                add(line_id=ln["line_id"], section=ln["section"], kind="figure", label=label, column="", key=key,
                    value=f["value"], unit=f["unit"], raw=f["raw"], text=ln["text"], claims=f"{label} {f['raw']}".strip())
        low = ln["text"].lower()
        for a in claim_patterns():
            m = re.search(a["pattern"], ln["text"], re.I)
            if m and (not a.get("section") or re.search(a["section"], ln["section"], re.I)):
                add(line_id=ln["line_id"], section=ln["section"], kind="assertion", label=a["label"], column="", key=a["id"],
                    value=(m.group("v").strip() if "v" in m.groupdict() and m.group("v") is not None else True), unit="",
                    raw=m.group(0), text=ln["text"], claims=a["claims"])
        _ = low
    return out


def ledger(data: bytes) -> dict[str, Any]:
    lines = read_lines(data)
    cl = claims(lines)
    by_line: dict[str, list[str]] = {}
    for c in cl:
        by_line.setdefault(c["line_id"], []).append(c["claim_id"])
    sections = list(dict.fromkeys(ln["section"] for ln in lines))
    return {"lines": [dict({k: v for k, v in ln.items() if k not in ("cells", "header")}, claim_ids=by_line.get(ln["line_id"], []))
                      for ln in lines],
            "claims": cl, "sections": sections,
            "counts": {"lines": len(lines), "figures": sum(1 for c in cl if c["kind"] == "figure"),
                       "assertions": sum(1 for c in cl if c["kind"] == "assertion")}}


def claim_index(cl: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """First claim per key (assertions by id, figures by key)."""
    out: dict[str, dict[str, Any]] = {}
    for c in cl:
        out.setdefault(c["key"], c)
    return out
