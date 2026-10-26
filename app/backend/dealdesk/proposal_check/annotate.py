"""The annotated proposal (K31): the RM's own Word file with the check's comments in the margin (Word comments, author
"CreditProbe proposal check"), a summary block on top and the query list to the RM at the end. Deterministic.

    data, name = annotated(original_bytes, result)
    data, name = queries_docx(result)          # the query list alone (Send back to RM attachment)
    data, name = batch_xlsx(rows)              # the batch table (K33 export)
"""
from __future__ import annotations

import io
from typing import Any

from backend.dealdesk.house_style.bankform import registry

AUTHOR, INITIALS = "CreditProbe proposal check", "CP"
SEV = {"critical": "CRITICAL", "major": "MAJOR", "minor": "minor", "info": "info"}


def _comment_text(f: dict[str, Any]) -> str:
    out = [f"[{SEV.get(f['severity'], f['severity'])} · {f['category']}] {f['title']}."]
    if f.get("evidence"):
        out.append(f"Bank data: {f['evidence']}")
    if f.get("query"):
        out.append(f"Query to RM: {f['query']}")
    return "\n".join(out)


def _anchor_paragraph(doc: Any, f: dict[str, Any], res: dict[str, Any]) -> Any:
    ps = doc.paragraphs
    i = f.get("para")
    if isinstance(i, int) and 0 <= i < len(ps) and ps[i].text.strip():
        return ps[i]
    # an omission in a missing section: anchor on the heading of the section that should precede it
    n = registry.BY_KEY[f["section_key"]].n if f.get("section_key") in registry.BY_KEY else 0
    best = None
    for p in ps:
        t = p.text.strip()
        if t[:3].rstrip(". ").isdigit() and int(t[:3].rstrip(". ").split(".")[0]) < n:
            best = p
    return best or next((p for p in ps if p.text.strip()), ps[0])


def annotated(original: bytes, res: dict[str, Any]) -> tuple[bytes, str]:
    from docx import Document
    from docx.shared import Pt, RGBColor
    doc = Document(io.BytesIO(original))
    findings = sorted(res["defects"] + res["observations"], key=lambda f: f["n"])
    for f in findings:
        p = _anchor_paragraph(doc, f, res)
        runs = [r for r in p.runs if r.text.strip()] or [p.add_run(" ")]
        doc.add_comment(runs, text=_comment_text(f), author=AUTHOR, initials=INITIALS)
    first = next((p for p in doc.paragraphs if p.text.strip()), doc.paragraphs[0])
    lines = [f"PROPOSAL CHECK · {res['customer']} · {res['proposal_id']} · score {res['score']:.0f}/100 (grade {res['grade']})",
             f"{len(res['defects'])} defects ({res['critical']} critical), {len(res['observations'])} observations; {res['sections_present']} of 20 sections present; "
             f"checked against Data Domains as at {res['as_of']} ({res['method']}). Run {res['run_id']}."]
    for t in lines:
        q = first.insert_paragraph_before("")
        r = q.add_run(t)
        r.bold = t.startswith("PROPOSAL CHECK")
        r.font.size = Pt(8.5)
        r.font.color.rgb = RGBColor(0x9B, 0x1C, 0x1C)
    _query_table(doc, res)
    b = io.BytesIO()
    doc.save(b)
    base = res["document"].rsplit(".", 1)[0]
    return b.getvalue(), f"{base}_checked.docx"


def _query_table(doc: Any, res: dict[str, Any]) -> None:
    from docx.shared import Pt
    doc.add_page_break()
    h = doc.add_paragraph()
    r = h.add_run(f"Queries to the RM ({len(res['queries'])}) · {res['customer']} · run {res['run_id']}")
    r.bold, r.font.size = True, Pt(11)
    t = doc.add_table(rows=1, cols=4)
    t.style = doc.styles["Table Grid"]
    for c, txt in zip(t.rows[0].cells, ("#", "Section", "Finding", "Query")):
        c.text = txt
        for rr in c.paragraphs[0].runs:
            rr.bold, rr.font.size = True, Pt(8)
    for q in res["queries"]:
        cells = t.add_row().cells
        for c, txt in zip(cells, (str(q["n"]), f"{q['section']}. {q['heading']}" if q["section"] else "", f"[{q['severity']}] {q['title']}", q["query"])):
            c.text = txt
            for rr in c.paragraphs[0].runs:
                rr.font.size = Pt(8)


def queries_docx(res: dict[str, Any]) -> tuple[bytes, str]:
    from docx import Document
    doc = Document()
    doc.add_paragraph(f"Proposal check · {res['customer']} ({res['proposal_id']}) · score {res['score']:.0f}/100")
    _query_table(doc, res)
    b = io.BytesIO()
    doc.save(b)
    return b.getvalue(), f"Queries_{res['proposal_id']}.docx"


def batch_xlsx(table: list[dict[str, Any]], rm_view: list[dict[str, Any]]) -> tuple[bytes, str]:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Proposals"
    cols = ["rank", "proposal_id", "customer", "rm", "branch", "sector", "status", "document", "score", "grade", "defects", "critical",
            "undisclosed", "contradicted", "queries_open", "sections_present", "top_defect"]
    ws.append([c.replace("_", " ").capitalize() for c in cols])
    for r in table:
        ws.append([r.get(c) for c in cols])
    ws2 = wb.create_sheet("By RM")
    cols2 = ["rm", "proposals", "average_score", "critical", "queries_open", "recurring"]
    ws2.append([c.replace("_", " ").capitalize() for c in cols2])
    for r in rm_view:
        ws2.append([r.get(c) if c != "recurring" else "; ".join(f"{k} ({v})" for k, v in r.get("recurring", [])) for c in cols2])
    for w in (ws, ws2):
        for c in w[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F3A5F")
        for col in w.columns:
            w.column_dimensions[col[0].column_letter].width = min(48, max(10, max(len(str(c.value or "")) for c in col) + 2))
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue(), "Proposal_check_all_pending.xlsx"
