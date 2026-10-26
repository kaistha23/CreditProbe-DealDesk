"""An Arabic credit policy for Session O's learner, which reads English clause wording.

The banking terms and units the metric library looks for are mapped to their English wording clause by clause (numbers,
clause numbers and quotes kept), so an Arabic policy gives the same thresholds an English one would. The original Arabic
quote stays on every learned item. Fictional demo policy: `demo_policy()`.
"""
from __future__ import annotations

import io
import re

from backend.dealdesk.try_docs.reader import normalise_digits

#: Arabic wording -> the English wording the metric library recognises (longest first when applied)
TERMS = {
    "نسبة تغطية خدمة الدين": "debt service coverage ratio (DSCR)",
    "تغطية خدمة الدين": "debt service coverage (DSCR)",
    "نسبة الدين إلى الأرباح قبل الفوائد والضرائب والإهلاك والاستهلاك": "debt/EBITDA",
    "نسبة الدين إلى الربح التشغيلي": "debt/EBITDA",
    "الرافعة المالية": "leverage",
    "نسبة التداول": "current ratio",
    "نسبة القرض إلى القيمة": "loan-to-value (LTV)",
    "الهامش النقدي": "cash margin",
    "هامش نقدي": "cash margin",
    "حد العميل الواحد": "single obligor limit",
    "العميل الواحد": "single obligor",
    "مجموعة العملاء المترابطين": "group of connected obligors",
    "الأطراف المترابطة": "connected counterparties",
    "القطاع الاقتصادي الواحد": "single economic sector",
    "قطاع اقتصادي واحد": "single economic sector",
    "العائد على رأس المال المعدل بالمخاطر": "RAROC",
    "عائد رأس المال المعدل بالمخاطر": "RAROC",
    "الدفعة الأخيرة": "balloon",
    "القوائم المالية المدققة": "audited financial statements",
    "تقرير المكتب الائتماني": "bureau report",
    "تقرير الائتمان": "bureau report",
    "الرأي القانوني": "legal opinion",
    "الحسابات الإدارية": "management accounts",
    "تتم مراجعة": "reviewed at least every",
    "يراجع كل": "reviewed at least every",
    "المرحلة الثانية": "Stage 2",
    "المرحلة الثالثة": "Stage 3",
    "لا تقل عن": "not less than",
    "لا يقل عن": "not less than",
    "لا تزيد عن": "not more than",
    "لا يزيد عن": "not more than",
    "لا تتجاوز": "not more than",
    "لا يتجاوز": "not more than",
    "على الأقل": "at least",
    "مصنف أقل من": "rated below",
    "تصنيف أقل من": "rated below",
    "الحد الأدنى للتصنيف": "minimum rating",
    "رأس المال الأساسي": "Tier 1",
    "سقف": "limit",
}
UNIT = [
    (r"(\d[\d,]*(?:\.\d+)?)\s*(?:مليون)\s*(?:درهم(?:\s*إماراتي)?)", r"AED \1 million"),
    (r"(\d[\d,]*(?:\.\d+)?)\s*(?:مليون)\s*(?:ريال(?:\s*سعودي)?)", r"SAR \1 million"),
    (r"(\d[\d,]*(?:\.\d+)?)\s*(?:مليار)\s*(?:درهم)", r"AED \1 bn"),
    (r"(\d+(?:\.\d+)?)\s*(?:٪|في المائة|بالمائة|بالمئة)", r"\1%"),
    (r"(\d+(?:\.\d+)?)\s*(?:مرة|مرات)\b", r"\1x"),
    (r"(\d+)\s*(?:يوم(?:ًا|ا)?|أيام)", r"\1 days"),
    (r"(\d+)\s*(?:شهر(?:ًا|ا)?|أشهر)", r"\1 months"),
    (r"(\d+)\s*(?:سنة|سنوات|أعوام|عام(?:ًا|ا)?)", r"\1 years"),
]


def is_arabic(text: str) -> bool:
    a = len(re.findall(r"[؀-ۿ]", text))
    return a > len(re.findall(r"[A-Za-z]", text))


def to_english_terms(line: str) -> str:
    s = normalise_digits(line)
    for pat, rep in UNIT:
        s = re.sub(pat, rep, s)
    for ar in sorted(TERMS, key=len, reverse=True):
        s = s.replace(ar, TERMS[ar])
    return s


def policy_text(text: str) -> str:
    """The policy as text lines the learner reads (numbered clauses kept on their own lines)."""
    return "\n".join(to_english_terms(ln) for ln in text.splitlines())


def demo_policy() -> tuple[str, bytes]:
    """A short fictional Arabic credit policy (Word) for the rehearsal and the tests."""
    from docx import Document
    d = Document()
    for t in ("سياسة الائتمان - بنك الواحة الرملية (وهمي)",
              "4. النسب المالية",
              "4.2 يجب ألا تقل نسبة تغطية خدمة الدين بعد التمويل عن 1.25 مرة.",
              "4.3 يجب ألا تزيد الرافعة المالية (نسبة الدين إلى الأرباح قبل الفوائد والضرائب والإهلاك والاستهلاك) عن 3.5 مرة.",
              "4.4 يجب ألا تقل نسبة التداول عن 1.10 مرة.",
              "5. حدود التركز",
              "5.1 لا يتجاوز حد العميل الواحد 300 مليون درهم.",
              "5.4 لا تتجاوز حصة قطاع اقتصادي واحد 15% من المحفظة.",
              "7. الضمانات",
              "7.1 لا تتجاوز نسبة القرض إلى القيمة 65% للعقارات المدرة للدخل.",
              "7.2 هامش نقدي لا يقل عن 10% على ضمانات المقاولين.",
              "9. التسعير",
              "9.1 لا يقل عائد رأس المال المعدل بالمخاطر على مدى عمر التسهيل عن 12%."):
        d.add_paragraph(t)
    b = io.BytesIO()
    d.save(b)
    return "Sandy_Oasis_Bank_Policy_AR.docx", b.getvalue()
