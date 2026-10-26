"""The prepared fallback case and the rehearsal: every document set run end to end, timed, then wiped.

    python -m backend.dealdesk.try_docs.rehearse          # writes backend/dealdesk/try_docs/rehearsal.json

Documents (all fictional): the twins (Session F's exported PDFs when present under var/dealdesk/try_docs/rehearsal/,
else the R11 Word twins in demo_inputs/proposals), a PDF and a scan made from them, an Arabic proposal, and Session
O's fictional policy (Word, and as a PDF).
"""
from __future__ import annotations

import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
from typing import Any

from backend.dealdesk import paths

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "rehearsal.json"
PROPOSALS = paths.V5 / "demo_inputs" / "proposals"
POLICY = paths.V5 / "demo_inputs" / "policy" / "Fictional_Bank_Credit_Policy.docx"
TWINS = {"twin_a": "Al_Sahel_Building_Materials_credit_proposal.docx", "twin_b": "Gulf_Meridian_Contracting_credit_proposal.docx"}


def rehearsal_dir() -> pathlib.Path:
    return paths.VAR / "try_docs" / "rehearsal"


def fallback() -> dict[str, Any]:
    """What the 'use the prepared case' button loads: twin B (contractor) and the fictional policy."""
    return {"proposal": TWINS["twin_b"], "policy": POLICY.name, "proposals": list(TWINS.values()),
            "note": "Fictional twins and Session O's fictional policy (Sandstone Harbour Bank PJSC)."}


def fallback_bytes(which: str = "twin_b") -> tuple[tuple[str, bytes], tuple[str, bytes]]:
    f = PROPOSALS / TWINS.get(which, TWINS["twin_b"])
    return (f.name, f.read_bytes()), (POLICY.name, POLICY.read_bytes())


def to_pdf(docx: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path | None:
    """Word to PDF with LibreOffice (rehearsal only; not used at run time)."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)], capture_output=True, timeout=180)
    p = out_dir / (docx.stem + ".pdf")
    return p if p.exists() else None


def to_scan(pdf: pathlib.Path, out: pathlib.Path) -> pathlib.Path | None:
    """A PDF with no text layer: the pages rendered to images and put back into a PDF (Pillow)."""
    if not shutil.which("pdftoppm"):
        return None
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "150", "-png", str(pdf), f"{td}/p"], check=True, capture_output=True, timeout=180)
        imgs = [Image.open(p).convert("RGB") for p in sorted(pathlib.Path(td).glob("p*.png"))]
        if not imgs:
            return None
        imgs[0].save(out, save_all=True, append_images=imgs[1:], format="PDF")
    return out


def arabic_proposal() -> tuple[str, bytes]:
    """A short fictional Arabic proposal (Word), for the Arabic path."""
    from docx import Document
    d = Document()
    for t in ("مقترح ائتماني: شركة واحة الرمال للتجارة العامة",
              "القطاع: تجارة الجملة",
              "التصنيف الداخلي: BB+",
              "الغرض: تمويل رأس المال العامل لاستيراد مواد البناء",
              "المبلغ: 45 مليون ريال",
              "المدة: 3 سنوات",
              "الهامش: 275 نقطة أساس",
              "الإيرادات: 310.5 مليون ريال",
              "الأرباح قبل الفوائد والضرائب والإهلاك والاستهلاك: 28.4 مليون ريال",
              "إجمالي الديون: 96.0 مليون ريال",
              "خدمة الدين: 14.2 مليون ريال",
              "صافي حقوق الملكية: 120.0 مليون ريال",
              "مدير العلاقة: سلمى الحربي",
              "ملاحظات: لم تقدم الشركة قوائم مالية مدققة لعام 2025؛ يوجد شيكان مرتجعان في يونيو 2026."):
        d.add_paragraph(t)
    b = io.BytesIO()
    d.save(b)
    return "Wahat_Al_Rimal_Trading_proposal_AR.docx", b.getvalue()


F_TWINS = {"twin_a": "R12-TWA", "twin_b": "R12-TWB"}


def f_exports(rd: pathlib.Path) -> dict[str, dict[str, pathlib.Path]]:
    """Session F's bank-form twins exported to PDF and Word (when F's writer is merged)."""
    try:
        from backend.dealdesk.house_style.bankform import paper, render
    except Exception:  # noqa: BLE001 - F not merged: the R11 Word twins are used
        return {}
    out: dict[str, dict[str, pathlib.Path]] = {}
    for key, pid in F_TWINS.items():
        p = paper.write(pid)
        pdf, _ = render.pdf(p, kind="Credit proposal")
        doc, _ = render.docx(p, kind="Credit proposal")
        out[key] = {"pdf": rd / f"{pid}_bank_form.pdf", "docx": rd / f"{pid}_bank_form.docx"}
        out[key]["pdf"].write_bytes(pdf)
        out[key]["docx"].write_bytes(doc)
    return out


def cases() -> list[dict[str, Any]]:
    rd = rehearsal_dir()
    rd.mkdir(parents=True, exist_ok=True)
    pol = (POLICY.name, POLICY.read_bytes())
    pol_pdf = to_pdf(POLICY, rd)
    out: list[dict[str, Any]] = []
    fx = f_exports(rd)
    for key, files in fx.items():
        out.append({"case": f"{key} Session F bank-form PDF + policy Word", "proposal": (files["pdf"].name, files["pdf"].read_bytes()), "policy": pol})
        out.append({"case": f"{key} Session F bank-form Word + policy PDF", "proposal": (files["docx"].name, files["docx"].read_bytes()),
                    "policy": (pol_pdf.name, pol_pdf.read_bytes()) if pol_pdf else pol})
        if key == "twin_b":
            scan = to_scan(files["pdf"], rd / f"{F_TWINS[key]}_bank_form_scan.pdf")
            if scan:
                out.append({"case": f"{key} Session F bank-form scanned PDF (OCR) + policy Word", "proposal": (scan.name, scan.read_bytes()), "policy": pol})
    for key, fn in TWINS.items():
        f = PROPOSALS / fn
        f_pdf = sorted(rd.glob(f"*{key}*.pdf")) or sorted(rd.glob(f"{f.stem}*.pdf"))
        pdf = f_pdf[0] if f_pdf else to_pdf(f, rd)
        out.append({"case": f"{key} Word + policy Word", "proposal": (f.name, f.read_bytes()), "policy": pol})
        if pdf:
            out.append({"case": f"{key} PDF ({'Session F export' if f_pdf else 'LibreOffice export'}) + policy PDF",
                        "proposal": (pdf.name, pdf.read_bytes()), "policy": (pol_pdf.name, pol_pdf.read_bytes()) if pol_pdf else pol})
            scan = to_scan(pdf, rd / f"{f.stem}_scan.pdf")
            if scan and key == "twin_b":
                out.append({"case": f"{key} scanned PDF (OCR) + policy Word", "proposal": (scan.name, scan.read_bytes()), "policy": pol})
    out.append({"case": "Arabic proposal (Word) + policy Word", "proposal": arabic_proposal(), "policy": pol})
    from backend.dealdesk.try_docs import arabic
    out.append({"case": "Arabic proposal (Word) + Arabic policy (Word)", "proposal": arabic_proposal(), "policy": arabic.demo_policy()})
    out.append({"case": "twin_b Word, no policy (defaults only)", "proposal": (PROPOSALS / TWINS["twin_b"]).name and
                ((PROPOSALS / TWINS["twin_b"]).name, (PROPOSALS / TWINS["twin_b"]).read_bytes()), "policy": None})
    return out


def run_case(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.try_docs import session as S
    t0 = time.perf_counter()
    v = S.start(c["proposal"], c["policy"], mode="deterministic", by="rehearsal")
    sid = v["session_id"]
    v = S.run_all(sid)
    wall = round(time.perf_counter() - t0, 2)
    s = S.get(sid)
    w = S.wipe(sid)
    steps = {st["key"]: {"status": st["status"], "seconds": st["seconds"], "summary": st["summary"]} for st in v["steps"]}
    ex = (s["steps"]["extract"].get("result") or {}).get("deal") or {}
    return {"case": c["case"], "complete": v["complete"], "total_seconds": v["total_seconds"], "wall_seconds": wall, "steps": steps,
            "deal": {k: ex.get(k) for k in ("name", "sector", "rating", "facility_type", "amount", "tenor_years", "margin_bps")},
            "defaults": len((s["steps"]["extract"].get("result") or {}).get("defaults") or []),
            "wipe": {"rows_removed": w["rows_removed"], "files": len(w["files"]), "seconds": w["seconds"]}}


def rehearse(write: bool = True) -> dict[str, Any]:
    res = [run_case(c) for c in cases()]
    out = {"cases": res, "all_complete": all(r["complete"] for r in res)}
    if write:
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":  # pragma: no cover
    r = rehearse()
    for c in r["cases"]:
        print(f"{c['case']:60s} {'OK ' if c['complete'] else 'ERR'} {c['total_seconds']:6.2f}s  {c['deal'].get('name')}")
