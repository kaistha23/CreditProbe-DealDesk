"""P1: the proposal corpus, read into sections.

Sources (all in the system):
  - the Deal Desk reference memos `data/dealdesk/memos/DD-*.docx` (business-unit voice, KSA book);
  - the prepared UAE cases: the proposals as submitted (business unit) and the credit review opinions (credit division),
    from `backend/dealdesk/proposal_review` and `demo_inputs/proposals/`;
  - anonymised exemplars in `data/dealdesk/house_style/exemplars/` (.docx, .md, .txt; optional `<name>.json` sidecar
    with bank, kind, segment, voice, weight);
  - proposals uploaded to the house-style corpus (var/dealdesk/house_style/corpus/, through the API).

A document becomes {doc_id, title, source, bank, kind, segment, weight, primary, sections: [{key, heading, voice,
paragraphs, bullets, tables}]}. Reading is deterministic: headings by Word style (or '#' / numbered lines in text),
section keys through a keyword table, voice by section and source.
"""
from __future__ import annotations

import io
import json
import pathlib
import re
from typing import Any

from backend.dealdesk import paths

V5 = paths.V5
EXEMPLARS = paths.DATA / "house_style" / "exemplars"
DEMO = V5 / "demo_inputs" / "proposals"

#: fictional bank identities (never a real bank's name)
BANKS = {"house-uae": "UAE house (anonymised)", "house-ksa": "KSA reference house"}
KINDS = ("new", "renewal", "increase")
SEGMENTS = ("contractor", "trader", "real_estate", "corporate")
EXEMPLAR_WEIGHT = 5.0

#: section key, label, heading keywords (first match wins, so the specific ones come first)
SECTION_KEYS: list[tuple[str, str, tuple[str, ...]]] = [
    ("counter", "Counter-proposals", ("counter-proposal", "counter proposal", "counterproposal")),
    ("watch", "Watch entry", ("watch entry", "watchlist", "accepted risk watch")),
    ("checks", "Arithmetic and reconciliation", ("arithmetic", "reconciliation")),
    ("gaps", "Information gaps", ("information gap", "queries to the rm")),
    ("summary", "Executive summary", ("executive summary", "summary", "overview", "introduction", "synopsis")),
    ("conditions", "Conditions and covenants", ("condition", "covenant", "terms and conditions", "undertaking")),
    ("recommendation", "Recommendation", ("recommendation", "conclusion", "approval sought")),
    ("opinion", "Credit opinion", ("opinion", "credit review", "cro review", "credit comment")),
    ("risks", "Risks and mitigants", ("risk", "weakness", "mitigant", "exception", "stress")),
    ("request", "Request", ("request", "proposal summary", "purpose of the", "approval required")),
    ("facilities", "Facilities", ("facilit", "limits", "terms", "exposure", "pricing", "raroc", "profitability")),
    ("financials", "Financial highlights", ("financial", "spreading", "performance")),
    ("business", "Business and projects", ("business", "project", "backlog", "contract", "operations", "market", "industry")),
    ("conduct", "Account conduct and bureau", ("conduct", "account", "bureau", "deposit", "aecb", "relationship")),
    ("security", "Security", ("security", "collateral", "guarantee")),
    ("obligor", "Obligor and group", ("obligor", "borrower", "customer", "background", "group", "profile", "ownership", "shareholding", "management", "shareholder", "company")),
]
LABEL = {k: lab for k, lab, _ in SECTION_KEYS}
CREDIT_SECTIONS = {"opinion", "checks", "gaps", "watch", "counter"}


def section_key(heading: str) -> str:
    low = re.sub(r"^[\d.\s]+", "", heading.lower()).strip()
    for key, _, words in SECTION_KEYS:
        if any(w in low for w in words):
            return key
    return "other"


def clean_heading(h: str) -> str:
    return re.sub(r"^\s*\d+(\.\d+)*\.?\s+", "", h).strip()


def classify(text: str, sector: str = "") -> tuple[str, str]:
    """(kind, segment) of a memo from its text and sector."""
    low = (text or "").lower()
    s = (sector + " " + low[:2000]).lower()
    if re.search(r"\b(increase|raise|enhance|additional|top-up|new [a-z0-9.\s-]{0,40}limit)", low) and re.search(r"\b(renew|existing)", low):
        kind = "increase"
    elif re.search(r"\brenew", low):
        kind = "renewal"
    elif re.search(r"\b(increase|raise|enhance)", low):
        kind = "increase"
    else:
        kind = "new"
    if re.search(r"construct|contract(ing|or)|engineering|electromechanical|infrastructure|epc\b", s):
        seg = "contractor"
    elif re.search(r"real estate|propert|developer|ijara financing of a completed", s):
        seg = "real_estate"
    elif re.search(r"trad(ing|er)|wholesale|distribut|building materials", s):
        seg = "trader"
    else:
        seg = "corporate"
    return kind, seg


def _new_section(key: str, heading: str, voice: str, numbered: bool = False) -> dict[str, Any]:
    return {"key": key, "heading": heading, "voice": voice, "numbered": numbered, "paragraphs": [], "bullets": [], "tables": []}


def _voice(key: str, heading: str, default: str) -> str:
    if key in CREDIT_SECTIONS or re.search(r"\bcro\b|credit (risk|division|review)", heading.lower()):
        return "credit"
    return default


def _skip_table(rows: list[list[str]]) -> bool:
    if not rows:
        return True
    first = rows[0][0].strip().upper()
    return "CREDITPROBE" in first or first in ("BOOK",)


def _is_heading_para(p: Any, text: str, style: str) -> bool:
    """A heading in a real proposal: a Heading style; or a short line (at most 10 words, no final full stop) that is all bold,
    all capitals, or numbered like '3. Financial highlights' / '3.1 Projects'."""
    if style.startswith("Heading"):
        return True
    words = text.split()
    if not words or len(words) > 10 or text.endswith((".", ";", ",")) or ":" in text[:-1]:
        return False
    runs = [r for r in p.runs if r.text.strip()]
    bold = bool(runs) and all(bool(r.bold) or bool(p.style is not None and p.style.font is not None and p.style.font.bold) for r in runs)
    caps = text.isupper() and len(text) > 3 and any(c.isalpha() for c in text)
    numbered = bool(re.match(r"^\d+(\.\d+)*\.?\s+[A-Z]", text))
    return bold or caps or numbered


def _cell_heading(text: str) -> bool:
    return 0 < len(text.split()) <= 6 and not text.endswith(".") and section_key(text) != "other"


def read_docx(data: bytes, default_voice: str = "business") -> dict[str, Any]:
    """Title and sections of a Word memo, paragraphs and tables in document order.

    Real proposals are read as well as generated ones: headings by Word style or by form (bold, capitals, numbered, short);
    a form-style table whose rows are 'Section | text' opens a section per row; prose inside table cells (12 words or more)
    is read as the section's paragraphs, so a proposal written in a table template still teaches its phrasing."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(io.BytesIO(data))
    title = ""
    sections: list[dict[str, Any]] = []
    cur = _new_section("preamble", "", default_voice)

    def open_section(text: str) -> None:
        nonlocal cur
        if cur["paragraphs"] or cur["bullets"] or cur["tables"] or cur["key"] != "preamble":
            sections.append(cur)
        key = section_key(text)
        cur = _new_section(key, clean_heading(text), _voice(key, text, default_voice), bool(re.match(r"^\s*\d", text)))

    for el in doc.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, doc)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            if style in ("Title", "CP Cover Title") or (not title and style.startswith("Title")):
                title = title or text
                continue
            if text.upper() in ("CREDIT MEMO",):
                continue
            if _is_heading_para(p, text, style):
                if not title and not sections and cur["key"] == "preamble" and not cur["paragraphs"] and (
                        section_key(text) == "other" or re.search(r"proposal|application|memo|credit", text.lower())):
                    title = text
                    continue
                open_section(text)
                continue
            (cur["bullets"] if "List" in style or re.match(r"^[•▪◦-]\s", text) else cur["paragraphs"]).append(re.sub(r"^[•▪◦-]\s+", "", text))
        elif tag == "tbl":
            t = Table(el, doc)
            rows = [[c.text.strip() for c in r.cells] for r in t.rows]
            if _skip_table(rows):
                continue
            form = [r for r in rows if len(r) >= 2 and _cell_heading(r[0]) and len(r[-1].split()) >= 12]
            if form and len(form) >= max(1, len(rows) // 2):
                for r in rows:
                    if len(r) >= 2 and _cell_heading(r[0]):
                        open_section(r[0])
                        cur["paragraphs"].extend(x.strip() for x in r[-1].splitlines() if x.strip())
                continue
            cur["tables"].append({"header": rows[0], "rows": len(rows) - 1})
            seen: set[str] = set()
            for r in rows:
                for c in r:
                    if len(c.split()) >= 12 and c not in seen:
                        seen.add(c)
                        cur["paragraphs"].extend(x.strip() for x in c.splitlines() if len(x.split()) >= 4)
    sections.append(cur)
    return {"title": title, "sections": [s for s in sections if s["paragraphs"] or s["bullets"] or s["tables"]]}


def read_text(text: str, default_voice: str = "business") -> dict[str, Any]:
    """Markdown or plain text: '#' headings or numbered heading lines ('3. Financial highlights')."""
    title = ""
    sections: list[dict[str, Any]] = []
    cur = _new_section("preamble", "", default_voice)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(#+)\s*(.+)$", line)
        if m and len(m.group(1)) == 1 and not title:
            title = m.group(2).strip()
            continue
        heading = m.group(2).strip() if m else (line if re.match(r"^\d+(\.\d+)*\.?\s+[A-Z][^.:]{2,70}$", line) else None)
        if heading:
            if cur["paragraphs"] or cur["bullets"] or cur["tables"]:
                sections.append(cur)
            key = section_key(heading)
            cur = _new_section(key, clean_heading(heading), _voice(key, heading, default_voice), bool(re.match(r"^\s*\d", heading)))
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            if not cur["tables"] or cur.get("_tbl_open") is not True:
                cur["tables"].append({"header": cells, "rows": 0})
                cur["_tbl_open"] = True
            else:
                cur["tables"][-1]["rows"] += 1
            continue
        cur["_tbl_open"] = False
        if re.match(r"^[-*•]\s+", line):
            cur["bullets"].append(re.sub(r"^[-*•]\s+", "", line))
        else:
            cur["paragraphs"].append(line)
    sections.append(cur)
    for s in sections:
        s.pop("_tbl_open", None)
    return {"title": title, "sections": [s for s in sections if s["paragraphs"] or s["bullets"] or s["tables"]]}


def text_of(doc: dict[str, Any]) -> str:
    return "\n".join([doc.get("title", "")] + [x for s in doc["sections"] for x in [s["heading"], *s["paragraphs"], *s["bullets"]]])


def make_doc(doc_id: str, parsed: dict[str, Any], source: str, bank: str, sector: str = "", kind: str | None = None,
             segment: str | None = None, weight: float = 1.0, primary: bool = False, path: str = "") -> dict[str, Any]:
    k, s = classify(text_of(parsed), sector)
    return {"doc_id": doc_id, "title": parsed.get("title", ""), "source": source, "bank": bank,
            "bank_label": BANKS.get(bank, bank), "kind": kind or k, "segment": segment or s, "weight": float(weight),
            "primary": bool(primary), "path": path, "sections": parsed["sections"]}


def _dd_docs() -> list[dict[str, Any]]:
    from backend.dealdesk import proposals
    out = []
    for f in sorted((paths.DATA / "memos").glob("DD-*.docx")):
        pid = f.stem
        try:
            p = proposals.get(pid)
            sector, existing = p["obligor"]["sector"], p["obligor"].get("existing")
        except Exception:  # noqa: BLE001 - the memo is read even without the book
            sector, existing = "", False
        parsed = read_docx(f.read_bytes())
        kind = "increase" if existing else "new"
        out.append(make_doc(pid, parsed, "memo", "house-ksa", sector, kind=kind, path=str(f.relative_to(V5))))
    return out


def _case_docs() -> list[dict[str, Any]]:
    from backend.dealdesk import proposal_cases as pc
    from backend.dealdesk import proposal_review as pr
    out = []
    for cid, c in pc.CASES.items():
        f = DEMO / c["file_name"]
        data = f.read_bytes() if f.exists() else pr.proposal_docx(cid)
        case = make_doc(cid, read_docx(data), "case", "house-uae", c["sector"], path=str(f.relative_to(V5)) if f.exists() else "")
        out.append(case)
        out.append(make_doc(f"{cid}-OPINION", read_docx(pr.opinion_docx(cid), default_voice="credit"), "opinion", "house-uae",
                            c["sector"], kind=case["kind"], segment=case["segment"]))
    return out


def _sidecar(f: pathlib.Path) -> dict[str, Any]:
    side = f.with_suffix(".json")
    if side.exists() and side != f:
        try:
            return json.loads(side.read_text())
        except ValueError:
            return {}
    return {}


def read_file(f: pathlib.Path, default_voice: str = "business") -> dict[str, Any] | None:
    if f.suffix.lower() == ".docx":
        return read_docx(f.read_bytes(), default_voice)
    if f.suffix.lower() in (".md", ".txt"):
        return read_text(f.read_text(errors="replace"), default_voice)
    return None


def _exemplar_docs(directory: pathlib.Path | None = None) -> list[dict[str, Any]]:
    directory = directory or EXEMPLARS
    out = []
    if not directory.exists():
        return out
    for f in sorted(directory.iterdir()):
        if f.name.lower().startswith("readme") or f.suffix.lower() not in (".docx", ".md", ".txt"):
            continue
        meta = _sidecar(f)
        parsed = read_file(f, meta.get("voice", "business"))
        if not parsed or not parsed["sections"]:
            continue
        doc = make_doc(f"EX-{f.stem}", parsed, "exemplar", meta.get("bank", "house-uae"), meta.get("sector", ""),
                       kind=meta.get("kind"), segment=meta.get("segment"), weight=float(meta.get("weight", EXEMPLAR_WEIGHT)),
                       primary=bool(meta.get("primary", True)), path=str(f.relative_to(V5)) if f.is_relative_to(V5) else f.name)
        out.append(doc)
    return out


def uploads_dir() -> pathlib.Path:
    return paths.VAR / "house_style" / "corpus"


def _upload_docs() -> list[dict[str, Any]]:
    d = uploads_dir()
    out = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except ValueError:
            continue
    return out


def load(include_uploads: bool = True) -> list[dict[str, Any]]:
    """Every document in the corpus, committed sources first."""
    docs = _dd_docs() + _case_docs() + _exemplar_docs()
    return docs + (_upload_docs() if include_uploads else [])


def ingest_upload(name: str, data: bytes, bank: str = "house-uae", kind: str | None = None, segment: str | None = None) -> dict[str, Any]:
    """A proposal uploaded to the corpus: read, stored under var, returned (the profile adds it incrementally)."""
    if name.lower().endswith(".docx"):
        parsed = read_docx(data)
    else:
        parsed = read_text(data.decode("utf-8", errors="replace"))
    if not parsed["sections"]:
        raise ValueError(f"{name} has no readable sections (headings and text).")
    import hashlib
    stem = re.sub(r"[^A-Za-z0-9-]+", "-", pathlib.Path(name).stem)[:50].strip("-") or "upload"
    doc = make_doc(f"UP-{stem}-{hashlib.sha1(data).hexdigest()[:8]}", parsed, "upload", bank if bank in BANKS else "house-uae", kind=kind, segment=segment)
    d = uploads_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{doc['doc_id']}.json").write_text(json.dumps(doc))
    return doc


def fingerprint() -> str:
    """Changes when a committed source or an exemplar changes (the profile cache key)."""
    parts = []
    for d in (paths.DATA / "memos", EXEMPLARS, DEMO):
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    st = f.stat()
                    parts.append(f"{f.name}:{st.st_size}:{int(st.st_mtime)}")
    import hashlib
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]
