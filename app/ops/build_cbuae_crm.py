"""Build the seed data of the CBUAE Credit Risk Management Standards from their PDF (R7, Session C, C1).

    python3 ops/build_cbuae_crm.py         # writes backend/playbook_v5/data/cbuae_crm.json

"Credit Risk Management Standards", Central Bank of the UAE (44 pages, Articles 1-13), split into the Standards'
own paragraphs, numbered as the Central Bank numbers them: the two paragraphs of "Introduction and Scope", Article 1
(one paragraph, no number) and paragraphs 2.1 to 13.x. Each clause id is "CBUAE CRM Art. <n>" ("CBUAE CRM Art. 7.8",
"CBUAE CRM Intro 1"). A paragraph's title is its own heading ("DPD indicator", "Stage 3 to Stage 2") or, without
one, the sub-heading it sits under ("Non-payment", "Provisioning") or the Article's title. Page headers ("CBUAE
Classification: Public"), page footers and the table of contents are dropped; the tables inside an Article stay in
the paragraph that holds them. The JSON is committed, so the seed needs no PDF tool at runtime.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "demo_inputs" / "policy" / "CBUAE_Credit_Risk_Management_Standards_EN_5996.pdf"
OUT = ROOT / "backend" / "playbook_v5" / "data" / "cbuae_crm.json"
PREFIX = "CBUAE CRM"

ART_RE = re.compile(r"^ARTICLE (\d{1,2}):\s*(.+?)\s*$")
PARA_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\s+(\S.*)$")
INTRO_RE = re.compile(r"^([12])\.\s+(\S.*)$")
HEAD_RE = re.compile(r"^([A-Z][A-Za-z0-9 ,/&’'()\-–]{2,60}?):\s*(.*)$", re.S)
SUBHEAD_RE = re.compile(r"^[A-Z][A-Za-z ’'&/\-]{3,70}$")


def _text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True,
                          text=True).stdout


def _lines(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        s = re.sub(r"\s{2,}", " ", ln.strip())
        if s.startswith("CBUAE Classification") or re.fullmatch(r"Page \d+ of \d+", s):
            continue
        out.append(s)
    return out


def _title_case(s: str) -> str:
    small = {"and", "of", "the", "for", "in", "on", "to"}
    words = s.lower().split()
    return " ".join(w if (i and w in small) else (w.upper() if w == "npa" else w.capitalize()) for i, w in enumerate(words))


def build(text: str) -> dict:
    lines = _lines(text)
    # The body starts at the second "INTRODUCTION AND SCOPE" (the first is the table of contents).
    starts = [i for i, s in enumerate(lines) if s == "INTRODUCTION AND SCOPE"]
    start = starts[-1]
    body = lines[start + 1:]
    articles: dict[str, str] = {"0": "Introduction and Scope"}
    clauses: list[dict] = []
    cur: dict | None = None
    art, last_para, sub = "0", 0, ""
    skipping = False  # a footnote at a page foot: from its bare number to the next paragraph

    def next_nonblank(i: int) -> str:
        for s in body[i + 1:]:
            if s:
                return s
        return ""

    for i, s in enumerate(body):
        if not s:
            if cur is not None and not skipping:
                cur["lines"].append("")
            continue
        m = ART_RE.match(s)
        if m:
            art, last_para, sub, skipping = m.group(1), 0, "", False
            articles[art] = _title_case(m.group(2))
            cur = None
            if art == "1":  # Article 1 is one unnumbered paragraph
                cur = {"num": "1", "article": "1", "sub": "", "lines": []}
                clauses.append(cur)
            continue
        p = PARA_RE.match(s)
        if p and p.group(1) == art and int(p.group(2)) > last_para:
            last_para = int(p.group(2))
            skipping = False
            cur = {"num": f"{art}.{int(p.group(2))}", "article": art, "sub": sub, "lines": [p.group(3)]}
            clauses.append(cur)
            continue
        if art == "0":
            q = INTRO_RE.match(s)
            if q:
                cur = {"num": f"Intro {q.group(1)}", "article": "0", "sub": "", "lines": [q.group(2)]}
                clauses.append(cur)
                continue
        if re.fullmatch(r"\d", s) and art != "0":
            skipping = True
            continue
        if skipping:
            continue
        nxt = next_nonblank(i)
        if SUBHEAD_RE.match(s) and not s.endswith(",") and (PARA_RE.match(nxt) or ART_RE.match(nxt)):
            sub = s
            continue
        if cur is not None:
            cur["lines"].append(s)

    out = []
    for c in clauses:
        raw = "\n".join(c["lines"]).strip()
        paras = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]
        rule = "\n".join(paras)
        rule = re.sub(r"(\w)- (\w)", r"\1-\2", rule)
        title = c["sub"] or articles[c["article"]]
        h = HEAD_RE.match(rule)
        if h and len(h.group(1).split()) <= 7 and not re.search(r"\b(are|is|as follows)\b", h.group(1)):
            title = h.group(1).strip()
            if title in ("Retail Obligors", "Wholesale Obligors") and c["sub"]:
                title = f"{c['sub']}: {title}"
            rule = h.group(2).strip() or rule
            rule = rule[:1].upper() + rule[1:]
        num = c["num"]
        cid = f"{PREFIX} Art. {num}" if not num.startswith("Intro") else f"{PREFIX} {num}"
        sec = f"{PREFIX} Art. {c['article']}" if c["article"] != "0" else f"{PREFIX} Intro"
        out.append({"clause": cid, "number": num, "article": int(c["article"]), "section": sec,
                    "section_title": articles[c["article"]], "title": title, "rule": rule})
    return {
        "id": "pd_cbuae_crm", "reference": PREFIX, "kind": "regulation",
        "title": "Credit Risk Management Standards",
        "issuer": "Central Bank of the UAE", "jurisdiction": "UAE", "category": "Regulatory",
        "effective_from": "2026-10-12",
        "source_file": "demo_inputs/policy/" + PDF.name,
        "sections": [{"section": (f"{PREFIX} Art. {k}" if k != "0" else f"{PREFIX} Intro"),
                      "title": (f"Article {k}: {v}" if k != "0" else v)} for k, v in articles.items()],
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
