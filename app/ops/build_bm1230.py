"""Build the seed data of CBO circular BM-1230's annexure from its PDF (R6 policy, Session P2).

    python3 ops/build_bm1230.py            # writes backend/playbook_v5/data/bm1230.json

The annexure ("Credit Management – Prudential Framework") is split into its own paragraphs, numbered as the
Central Bank numbers them: the Introduction's paragraphs a–d and paragraphs 1.1 to 7.9 (3.4.1 to 3.4.7 kept as
their own clauses). Each clause id is "BM-1230 §<number>". Footnotes and page footers are dropped; the annexed
reporting templates (section 8) are not clauses. The JSON is committed, so the seed needs no PDF tool at runtime.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "demo_inputs" / "policy" / "CBO_BM-1230_Annexure_Credit_Management_Prudential_Framework.pdf"
OUT = ROOT / "backend" / "playbook_v5" / "data" / "bm1230.json"

SECTION_RE = re.compile(r"^(\d)\.\s{2,}([A-Z][^.]{3,90})$")
PARA_RE = re.compile(r"^\s{0,8}(\d\.\d{1,2}(?:\.\d{1,2})?)\.?\s+(\S.*)$")
INTRO_RE = re.compile(r"^([a-d])\.\s+(\S.*)$")
FOOTER_RE = re.compile(r"^\s*Page \d+ of \d+\s*$")


def _text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True,
                          text=True).stdout


def _strip_footnotes(lines: list[str]) -> list[str]:
    """Drop footnote blocks (a bare footnote number, its text, up to the page footer) and the footers."""
    out, skipping = [], False
    for i, ln in enumerate(lines):
        if FOOTER_RE.match(ln):
            skipping = False
            continue
        if not skipping and re.fullmatch(r"\s*\d\s*", ln) and i + 1 < len(lines) and lines[i + 1].strip() \
                and not PARA_RE.match(lines[i + 1]):
            skipping = True
        if not skipping:
            out.append(ln)
    return out


def _title(num: str, first: str, section_title: str) -> tuple[str, str]:
    """A paragraph's own heading ("Scope:", "Days Past Due Trigger:") or, without one, a short title."""
    m = re.match(r"^([A-Z][A-Za-z /&’'()\-–]{2,70}?):\s*(.*)$", first)
    if m:
        return m.group(1).strip(), m.group(2)
    if len(first) < 80 and not first.rstrip().endswith((".", ",", ";")) and not re.search(r"\b(shall|should|is|are)\b", first):
        return first.strip(), ""
    return section_title, first


def build(text: str) -> dict:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "Introduction")
    end = next(i for i, ln in enumerate(lines) if re.match(r"^8\.\s+Annexures\s*$", ln.strip()))
    body = _strip_footnotes(lines[start:end])
    sections: dict[str, str] = {"0": "Introduction"}
    clauses: list[dict] = []
    cur: dict | None = None
    sec = "0"
    for ln in body:
        s = ln.strip()
        if not s or s.startswith("*****"):
            if cur is not None:
                cur["lines"].append("")
            continue
        m = SECTION_RE.match(s)
        if m and not PARA_RE.match(ln) and int(m.group(1)) == int(sec) + 1 and len(ln) - len(ln.lstrip()) <= 4:
            sec = m.group(1)
            sections[sec] = re.sub(r"\s+", " ", m.group(2)).strip()
            cur = None
            continue
        p = PARA_RE.match(ln)
        if p and p.group(1).split(".")[0] == sec:
            cur = {"num": p.group(1), "section": sec, "lines": [p.group(2)]}
            clauses.append(cur)
            continue
        i = INTRO_RE.match(s) if sec == "0" else None
        if i:
            cur = {"num": f"Intro ({i.group(1)})", "section": "0", "lines": [i.group(2)]}
            clauses.append(cur)
            continue
        if cur is not None:
            cur["lines"].append(s)
    out = []
    groups: dict[str, str] = {}
    for c in clauses:
        head = c["lines"][0].strip()
        own = (len(head) < 62 and "," not in head and not head.endswith((".", ";")) and ":" not in head
               and not re.search(r"\b(shall|should|is|are|will)\b", head))
        body_lines = c["lines"][1:] if own else c["lines"]
        if own and not "".join(body_lines).strip():
            groups[c["num"]] = head      # a heading paragraph (4.6, 5.7): its sub-paragraphs carry it
            continue
        raw = "\n".join(body_lines).strip()
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
        joined = "\n".join(paras)
        first, _, rest = joined.partition("\n")
        parent = groups.get(c["num"].rsplit(".", 1)[0], "")
        if own:
            title, lead = head, first
        else:
            title, lead = _title(c["num"], first, parent or sections[c["section"]])
        rule = "\n".join(x for x in (lead, rest) if x).strip()
        rule = re.sub(r"(\w)- (\w)", r"\1-\2", rule)
        if not rule:
            continue
        num = c["num"]
        out.append({"clause": f"BM-1230 §{num}" if not num.startswith("Intro") else f"BM-1230 {num}",
                    "number": num, "section": f"BM-1230 §{c['section']}" if c["section"] != "0" else "BM-1230 Intro",
                    "section_title": sections[c["section"]], "title": title, "rule": rule})
    return {
        "id": "pd_cbo_bm1230", "reference": "BM-1230", "kind": "regulation",
        "title": "Credit Management – Prudential Framework (Annexure to Circular BM-1230)",
        "issuer": "Central Bank of Oman", "jurisdiction": "Oman", "category": "Regulatory",
        "effective_from": "2026-07-01",
        "source_file": "demo_inputs/policy/" + PDF.name,
        "sections": [{"section": (f"BM-1230 §{k}" if k != "0" else "BM-1230 Intro"), "title": v}
                     for k, v in sections.items()],
        "clauses": out,
    }


def main() -> int:
    data = build(_text(PDF))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['clauses'])} clauses in {len(data['sections'])} sections -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
