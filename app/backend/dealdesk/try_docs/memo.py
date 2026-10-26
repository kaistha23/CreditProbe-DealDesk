"""The proposal as the review reads it, and step 5: the credit memo drafted in the language of the participant's memo.

English: Session P's house-style drafter (deterministic; the model polishes only in model mode with a key, N6).
Arabic: a deterministic writer in formal banking Arabic, every sentence a fact with its number, built from the same
deal, review and counter-proposal results the English draft uses. Both export to Word (Arabic right-to-left).
"""
from __future__ import annotations

import io
from typing import Any

from backend.dealdesk import proposals
from backend.dealdesk_thread.proposal_full import FACILITY


def save_review_memo(pid: str, doc: dict[str, Any], data: bytes) -> None:
    """The R11 review reads the memo's claims from a .docx; a PDF, scan or text proposal is laid out as one."""
    from backend.dealdesk import review_facts as RF
    if doc["name"].lower().endswith(".docx"):
        RF.save_uploaded_memo(pid, data)
        return
    from docx import Document
    d = Document()
    for ln in doc["text"].splitlines():
        if ln.strip():
            d.add_paragraph(ln.strip())
    b = io.BytesIO()
    d.save(b)
    RF.save_uploaded_memo(pid, b.getvalue())


# ------------------------------------------------------------------ Arabic

AR_FACILITY = {"term_loan": "تمويل لأجل", "revolver": "تمويل رأس مال عامل متجدد", "performance_lg": "خطابات ضمان حسن التنفيذ",
               "financial_lg": "خطابات ضمان مالية", "trade_lc": "اعتمادات مستندية"}
AR_SECTOR = {"Construction": "المقاولات والبناء", "Real Estate": "العقارات", "Wholesale Trade": "تجارة الجملة", "Retail Trade": "تجارة التجزئة",
             "Manufacturing": "الصناعة", "Chemicals": "الكيماويات", "Hospitality": "الضيافة", "Healthcare": "الرعاية الصحية",
             "Transport and Logistics": "النقل والخدمات اللوجستية", "Power and Utilities": "الكهرباء والمرافق",
             "Telecommunications": "الاتصالات", "Information Technology": "تقنية المعلومات", "Metals and Mining": "المعادن والتعدين",
             "Agriculture and Agri-processing": "الزراعة والصناعات الغذائية"}
AR_SEV = {"critical": "حرجة", "major": "جوهرية", "minor": "ثانوية"}
AR_DECISION = {"Approve": "الموافقة", "Approve with conditions": "الموافقة بشروط", "Counter-offer": "تقديم مقترح مضاد",
               "Decline": "الرفض", "Refer": "الإحالة إلى لجنة أعلى"}


def _n(x: float | None, d: int = 1) -> str:
    return "غير متوفر" if x is None else f"{x:,.{d}f}"


def _ar_decision(dec: str | None) -> str:
    if not dec:
        return "الإحالة إلى لجنة الائتمان"
    for k, v in AR_DECISION.items():
        if dec.lower().startswith(k.lower()):
            return v
    return dec


def arabic_sections(pid: str, review: dict[str, Any] | None, counter: dict[str, Any] | None, policy: dict[str, Any] | None) -> list[dict[str, Any]]:
    p = proposals.get(pid)
    ob, a = p["obligor"], p["ask"]
    y = p["financials"]["years"][-1]
    ccy = "ريال سعودي" if a["currency"] == "SAR" else "دولار أمريكي"
    lev = (y["total_debt"] / y["ebitda"]) if y.get("ebitda") else None
    dscr = (y["ebitda"] / y["debt_service"]) if y.get("debt_service") else None
    secs: list[dict[str, Any]] = []
    secs.append({"key": "request", "heading": "أولاً: ملخص الطلب", "paragraphs": [
        f"تطلب وحدة الأعمال الموافقة على {AR_FACILITY.get(a['facility_type'], a['facility_type'])} لصالح {ob['name']} بمبلغ "
        f"{_n(a['amount'])} مليون {ccy} لمدة {a['tenor_years']} سنة وبهامش {a['margin_bps']} نقطة أساس، وذلك وفقاً لما ورد في المقترح المقدم "
        f"(تاريخ الاستلام {p.get('received', '')})."]})
    secs.append({"key": "obligor", "heading": "ثانياً: المقترض", "paragraphs": [
        f"المقترض {ob['name']}، ويعمل في قطاع {AR_SECTOR.get(ob['sector'], ob['sector'])}، وتصنيفه الداخلي {ob['internal_rating']}"
        + (f"، ضمن مجموعة {ob['group_name']}" if ob.get("group_name") and ob["group_name"] != ob["name"] else "") + ".",
        "مصدر البيانات: المقترض كما ورد في المقترح المقدم من وحدة الأعمال؛ لم يتم التحقق من السجل التجاري في هذه الجلسة التجريبية."]})
    fin = [f"الإيرادات {_n(y.get('revenue'))} مليون ريال، والأرباح قبل الفوائد والضرائب والإهلاك والاستهلاك {_n(y.get('ebitda'))} مليون ريال "
           f"(سنة {y['year']})."]
    if lev is not None:
        fin.append(f"إجمالي الديون إلى الأرباح التشغيلية {_n(lev, 2)} مرة.")
    if dscr is not None:
        fin.append(f"نسبة تغطية خدمة الدين {_n(dscr, 2)} مرة.")
    if not y.get("ebitda"):
        fin.append("لم يتضمن المقترح بيانات مالية كافية؛ لم يتم اختبار نسبة تغطية خدمة الدين ونسبة المديونية.")
    secs.append({"key": "financials", "heading": "ثالثاً: المؤشرات المالية", "paragraphs": fin})
    if policy:
        found = [f for f in policy.get("found", []) if f.get("type") == "threshold"]
        miss = [m for m in policy.get("missing", []) if m.get("value") is not None]
        secs.append({"key": "policy", "heading": "رابعاً: سياستكم الائتمانية", "paragraphs": [
            f"تم استخلاص {len(found)} حداً من سياستكم الائتمانية، وتم تطبيق القيم الافتراضية لنظام CreditProbe على {len(miss)} معياراً "
            "لم تحددها السياسة (موضحة كقيم افتراضية). هذه نسخة تجريبية لا تغيّر معايير البنك إلا بعد اعتمادها."]})
    if review:
        pc = review.get("policy_counts") or {}
        bullets = [f"[{AR_SEV.get(f['severity'], f['severity'])}] {f['title'] or f['rule_id']}: {f['finding']} ({f['source']})"
                   for f in (review.get("findings") or [])[:12]]
        secs.append({"key": "review", "heading": "خامساً: نتائج المراجعة الائتمانية", "paragraphs": [
            f"تمت مراجعة المقترح مقابل بنود سياستكم: {pc.get('supported', 0)} بنداً مستوفى، و{pc.get('contradicted', 0) + pc.get('exception', 0)} "
            f"بنداً غير مستوفى، و{pc.get('unverifiable', 0)} بنداً يتطلب بيانات غير متوفرة في المقترح. إجمالي الملاحظات {len(review.get('findings') or [])} "
            f"({review.get('severity', {}).get('critical', 0)} حرجة، {review.get('severity', {}).get('major', 0)} جوهرية، "
            f"{review.get('severity', {}).get('minor', 0)} ثانوية)."], "bullets": bullets})
    if counter:
        cps = counter.get("counter_proposals") or []
        secs.append({"key": "counter", "heading": "سادساً: المقترح المضاد", "paragraphs": [
            (f"أعدّ محرك التحسين {len(cps)} بديلاً للهيكلة مع التسعير وعائد رأس المال المعدّل بالمخاطر؛ تفاصيلها في ورقة اللجنة المرفقة."
             if cps else "لم يُقترح بديل للهيكلة؛ الطلب كما هو ضمن حدود السياسة.")]})
    dec = (review or {}).get("decision")
    secs.append({"key": "recommendation", "heading": "سابعاً: التوصية", "paragraphs": [
        f"توصي إدارة الائتمان بـ{_ar_decision(dec)}، مع استيفاء الملاحظات الحرجة والجوهرية أعلاه قبل العرض على اللجنة.",
        "أُعدّت هذه المسودة آلياً (دون نموذج لغوي) من بيانات المقترح ونتائج المراجعة، وكل رقم فيها مأخوذ من المقترح أو من محرك CreditProbe."]})
    return secs


# ------------------------------------------------------------------ the draft step

def bankform_section(x: dict[str, Any]) -> dict[str, Any]:
    """A Session F section (typed blocks) as heading, paragraphs, bullets and one table."""
    paras: list[str] = []
    bullets: list[str] = []
    table = None
    for b in x.get("blocks") or []:
        if b.get("text"):
            paras.append(str(b["text"]))
        for it in b.get("items") or []:
            bullets.append(str(it.get("text") if isinstance(it, dict) else it))
        if b.get("rows") and table is None:
            table = {"header": [str(h) for h in (b.get("header") or b.get("columns") or [])], "rows": b["rows"]}
        elif b.get("pairs"):
            bullets.extend(f"{k}: {v}" for k, v in (b["pairs"].items() if isinstance(b["pairs"], dict) else b["pairs"]))
    out = {"key": x.get("key", ""), "heading": f"{x['n']}. {x['heading']}" if x.get("n") else x.get("heading", ""), "paragraphs": paras,
           "bullets": bullets}
    if table:
        out["table"] = table
    return out


def _en_sections(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in d["sections"]:
        sec = {"key": s["key"], "heading": s.get("heading") or s["key"], "paragraphs": list(s.get("paragraphs") or []),
               "bullets": list(s.get("bullets") or [])}
        if s.get("table"):
            sec["table"] = s["table"]
        out.append(sec)
    return out


def draft(pid: str, language: str, use_model: bool, review: dict[str, Any] | None = None, counter: dict[str, Any] | None = None,
          policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if language == "ar":
        secs = arabic_sections(pid, review, counter, policy)
        words = sum(len(" ".join(s.get("paragraphs", []) + s.get("bullets", [])).split()) for s in secs)
        return {"language": "ar", "direction": "rtl", "engine": "Arabic deterministic writer (no model)", "sections": secs,
                "words": words, "draft_id": None, "style_score": None,
                "summary": f"مسودة باللغة العربية: {len(secs)} أقسام، {words} كلمة (Arabic draft, {len(secs)} sections, no model)."}
    from backend.dealdesk.try_docs import engines
    f = engines._find(engines.F_PROPOSAL)  # noqa: SLF001
    if f:
        try:
            paper = engines._call(f[1], pid, polish_text=use_model)  # noqa: SLF001
            secs = [bankform_section(x) for x in paper.get("sections") or []]
            words = sum(len(" ".join(s["paragraphs"] + s.get("bullets", [])).split()) for s in secs)
            return {"language": "en", "direction": "ltr", "engine": "Session F bank-form proposal" + (" with model polish" if use_model else " (deterministic, no model)"),
                    "sections": secs, "words": words, "draft_id": None, "style_score": None,
                    "summary": f"English bank-form proposal: {len(secs)} sections, {words} words."}
        except Exception:  # noqa: BLE001 - F's writer cannot take this deal: Session P's drafter writes it
            pass
    from backend.dealdesk.house_style import service as hs
    d = hs.create_draft(pid, use_model=use_model, by="try-docs")
    secs = _en_sections(d)
    words = sum(len(" ".join(s.get("paragraphs", []) + s.get("bullets", [])
                             + [str(c) for r in (s.get("table") or {}).get("rows", []) for c in r]).split()) for s in secs)
    score = (d.get("score") or {}).get("total")
    eng = "house-style drafter" + (" with model polish" if use_model else " (deterministic, no model)")
    return {"language": "en", "direction": "ltr", "engine": eng, "sections": secs, "words": words, "draft_id": d["draft_id"],
            "style_score": score,
            "summary": f"English draft in the house style: {len(secs)} sections, {words} words, style score {score}."}


def docx(result: dict[str, Any], title: str) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    rtl = result.get("direction") == "rtl"
    d = Document()

    def para(text: str, style: str | None = None) -> None:
        p = d.add_paragraph(text, style=style)
        if rtl:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            ppr = p._p.get_or_add_pPr()  # noqa: SLF001
            ppr.append(OxmlElement("w:bidi"))
            for r in p.runs:
                rpr = r._r.get_or_add_rPr()  # noqa: SLF001
                rpr.append(OxmlElement("w:rtl"))
                r.font.name = "Arial"
                rpr.rFonts.set(qn("w:cs"), "Arial")

    para(title, "Title")
    for s in result["sections"]:
        para(s["heading"], "Heading 1")
        for t in s.get("paragraphs", []):
            para(t)
        for b in s.get("bullets", []):
            para(b, "List Bullet")
        tb = s.get("table")
        if tb and tb.get("rows"):
            t = d.add_table(rows=1, cols=len(tb["header"]))
            for i, h in enumerate(tb["header"]):
                t.rows[0].cells[i].text = str(h)
            for row in tb["rows"]:
                cells = t.add_row().cells
                for i, v in enumerate(row[: len(cells)]):
                    cells[i].text = str(v)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


__all__ = ["FACILITY", "arabic_sections", "docx", "draft", "save_review_memo"]
