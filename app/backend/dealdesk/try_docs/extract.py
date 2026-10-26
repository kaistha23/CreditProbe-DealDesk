"""Extract a participant's proposal (any layout, English or Arabic) into a Deal Desk deal.

Two readers, the better one wins field by field:
  * the Deal Desk short-form reader (`dealdesk_thread.ingest`) for a Word file in the Deal Desk layout;
  * a free-text reader for a bank-form proposal, a PDF or a scan: labelled lines ("Sector: Construction"), inline
    labels ("... Internal rating BB- ..."), table rows ("Revenue | 2,050.0"), the facilities table (existing |
    proposed | pricing) and Arabic labels.

Every field says where it was read ("line 3", "facilities table") or that it is a labelled default. AED amounts
become SAR at the Deal Desk rate (aed_sar), shown on the field.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk_thread import ingest

SECTORS = ("Agriculture and Agri-processing", "Chemicals", "Construction", "Healthcare", "Hospitality", "Information Technology",
           "Manufacturing", "Metals and Mining", "Power and Utilities", "Real Estate", "Retail Trade", "Telecommunications",
           "Transport and Logistics", "Wholesale Trade")
#: words (English and Arabic) that place a business in a sector
SECTOR_WORDS = {
    "Construction": ("construction", "contracting", "contractor", "civil works", "مقاولات", "المقاولات", "البناء", "إنشاءات"),
    "Real Estate": ("real estate", "property develop", "developer", "off-plan", "عقارات", "العقارات", "التطوير العقاري"),
    "Wholesale Trade": ("wholesale", "trading", "distribution", "building materials", "تجارة الجملة", "التجارة", "مواد البناء", "توزيع"),
    "Retail Trade": ("retail", "supermarket", "التجزئة"),
    "Manufacturing": ("manufactur", "factory", "industrial", "تصنيع", "مصنع", "الصناعة"),
    "Chemicals": ("chemical", "petrochem", "كيماويات", "البتروكيماويات"),
    "Hospitality": ("hotel", "hospitality", "الضيافة", "فندق", "الفنادق"),
    "Healthcare": ("hospital", "healthcare", "clinic", "الرعاية الصحية", "مستشفى"),
    "Transport and Logistics": ("logistics", "transport", "shipping", "النقل", "الخدمات اللوجستية"),
    "Power and Utilities": ("power", "utility", "utilities", "الكهرباء", "المرافق"),
    "Telecommunications": ("telecom", "الاتصالات"),
    "Information Technology": ("software", "information technology", "تقنية المعلومات"),
    "Metals and Mining": ("steel", "mining", "metals", "التعدين", "الحديد"),
    "Agriculture and Agri-processing": ("agri", "food processing", "الزراعة", "الأغذية"),
}
RATINGS = ingest.RATINGS
_RATING = r"(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|CC|C)"
_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"

#: Arabic labels -> field (ingest.FIELDS keys)
AR_LABELS = {
    "name": ("اسم العميل", "العميل", "المقترض", "اسم الشركة", "الشركة", "طالب التمويل"),
    "sector": ("القطاع", "النشاط"),
    "group_name": ("المجموعة",),
    "internal_rating": ("التصنيف الداخلي", "التصنيف", "درجة المخاطر"),
    "rm": ("مدير العلاقة",),
    "purpose": ("الغرض", "الغرض من التمويل"),
    "amount": ("المبلغ", "مبلغ التمويل", "الحد المطلوب", "إجمالي الحدود", "الحد"),
    "tenor_years": ("المدة", "الأجل", "مدة التمويل"),
    "margin_bps": ("الهامش", "هامش الربح", "التسعير"),
    "revenue": ("الإيرادات", "المبيعات", "الإيراد"),
    "ebitda": ("الأرباح قبل الفوائد والضرائب والإهلاك والاستهلاك", "الربح قبل الفوائد", "EBITDA"),
    "total_debt": ("إجمالي الديون", "إجمالي القروض", "الديون"),
    "debt_service": ("خدمة الدين",),
    "net_worth": ("صافي حقوق الملكية", "حقوق الملكية", "صافي الثروة"),
    "current_ratio": ("نسبة التداول",),
}
FIN = ("revenue", "ebitda", "total_debt", "debt_service", "net_worth")


def _n(s: str) -> float | None:
    m = re.search(_NUM, s or "")
    return float(m.group(1).replace(",", "")) if m else None


def _last_n(s: str) -> float | None:
    """The last number of a row (the latest year or the proposed column)."""
    xs = re.findall(_NUM, s or "")
    return float(xs[-1].replace(",", "")) if xs else None


def currency_of(text: str) -> str:
    c = {k: len(re.findall(rf"\b{k}\b", text)) for k in ("AED", "SAR", "USD")}
    c["AED"] += len(re.findall(r"درهم", text))
    c["SAR"] += len(re.findall(r"ريال", text))
    return max(c, key=lambda k: c[k]) if any(c.values()) else "SAR"


def _offer(found: dict[str, dict[str, Any]], field: str, value: Any, source: str, conf: float, raw: str = "") -> None:
    if value in (None, ""):
        return
    if field in found and found[field]["confidence"] >= conf:
        return
    found[field] = {"field": field, "label": ingest.FIELDS[field][0], "value": value, "source": source, "confidence": conf,
                    "raw": raw.strip()[:140]}


def clean_name(raw: str) -> str:
    """A name without bullets, a trailing reference ('· R12-TWB') or the sentence after it."""
    v = re.sub(r"^[\s·•\-–—*]+", "", raw or "")
    v = re.split(r"\s+·\s+|\.\s|\s\(|;|\s\|", v)[0]
    return v.strip(" .·")


#: ISIC section (and division) -> the book's sector
ISIC = [(r"^A", "Agriculture and Agri-processing"), (r"^B", "Metals and Mining"), (r"^C(19|20|21)", "Chemicals"),
        (r"^C24", "Metals and Mining"), (r"^C", "Manufacturing"), (r"^[DE]", "Power and Utilities"), (r"^F", "Construction"),
        (r"^G4[56]", "Wholesale Trade"), (r"^G47", "Retail Trade"), (r"^G", "Wholesale Trade"), (r"^H", "Transport and Logistics"),
        (r"^I", "Hospitality"), (r"^J61", "Telecommunications"), (r"^J", "Information Technology"), (r"^L", "Real Estate"),
        (r"^Q", "Healthcare")]


def sector_of_code(code: str) -> str | None:
    c = (code or "").strip().upper()
    if not re.match(r"^[A-U]\d{2,4}$", c):
        return None
    return next((sec for pat, sec in ISIC if re.match(pat, c)), None)


def _sector(s: str) -> str | None:
    low = s.lower()
    for sec in SECTORS:
        if sec.lower() in low:
            return sec
    for sec, words in SECTOR_WORDS.items():
        if any(w in low for w in words):
            return sec
    return None


def _ar_field(label: str) -> str | None:
    lab = label.strip(" :：-–|")
    best, blen = None, 0
    for f, syns in AR_LABELS.items():
        for s in syns:
            if lab.startswith(s) and len(s) > blen:
                best, blen = f, len(s)
    return best


def _value_of(field: str, raw: str) -> Any:
    if field in FIN or field in ("amount", "current_ratio"):
        return _last_n(raw) if field in FIN else _n(raw)
    if field == "tenor_years":
        v = _n(raw)
        if v is not None and re.search(r"month|شهر|أشهر", raw, re.I):
            v = max(1, round(v / 12))
        return int(v) if v else None
    if field == "margin_bps":
        m = re.search(r"\+\s*" + _NUM + r"\s*(bps|bp|basis|%|نقطة)?", raw)
        if m:
            v = float(m.group(1).replace(",", ""))
            return int(round(v * 100)) if (m.group(2) or "").startswith("%") or v < 20 else int(round(v))
        v = _n(raw)
        if v is None:
            return None
        return int(round(v * 100)) if ("%" in raw or v < 20) else int(round(v))
    if field == "internal_rating":
        m = re.search(r"\b" + _RATING + r"(?![A-Za-z])", raw)
        return m.group(1) if m and m.group(1) in RATINGS else None
    if field == "sector":
        return _sector(raw) or None
    if field in ("name", "group_name"):
        v = clean_name(raw)
        return v[:120] or None
    return ingest.FIELDS[field][2](raw)


_SUFFIX = re.compile(r"\b(LLC|L\.L\.C|PJSC|PSC|JSC|Company|Co\.|Ltd|Limited|Group|Trading|Est\.?|Establishment|Holding|Contracting|شركة|مؤسسة)\b", re.I)


def unwrap(text: str) -> list[str]:
    """Lines of the text with PDF line wraps joined (a PDF text line that wraps ends with a space)."""
    raw = text.splitlines()
    out: list[str] = []
    carry = ""
    for ln in raw:
        if not ln.strip():
            if carry:
                out.append(carry.strip())
                carry = ""
            continue
        carry = (carry + " " + ln.strip()) if carry else ln.strip()
        if not ln.endswith((" ", "\t")) or "|" in ln:
            out.append(carry.strip())
            carry = ""
    if carry:
        out.append(carry.strip())
    return out


#: a label followed by a number on one line ("Revenue 2,050.0"), as PDF text gives a two-column table
_LABEL_NUM = re.compile(r"^([A-Za-z][A-Za-z /&()'.-]{2,40}?)\s+\(?(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)\)?(?:\s|$)")


_HEADER_LABEL = re.compile(r"^(customer|borrower|obligor|group( no\.?)?|branch|cif|date|purpose code|industry code|collateral code|"
                           r"rating|rm|ao|review date|request|related)", re.I)
#: header labels whose value needs more than the generic field parser
_SPECIAL = {r"^customer$|^borrower$|^obligor$|^applicant$": "name", r"^rating existing\s*/\s*proposed$": "rating_pair",
            r"^industry code$": "_isic", r"^group$": "group_name"}


def _pair(found: dict[str, dict[str, Any]], label: str, value: str, where: str, raw: str, only_special: bool = False) -> bool:
    lab = " ".join(label.lower().split()).rstrip(":")
    for pat, f in _SPECIAL.items():
        if re.match(pat, lab):
            if f == "_isic":
                sec = sector_of_code(value)
                if sec:
                    _offer(found, "sector", sec, f"{where} (industry code {value.strip()})", 0.98, raw)
            elif f == "rating_pair":
                rs = [r for r in re.findall(r"\b" + _RATING + r"(?![A-Za-z])", value) if r in RATINGS]
                if rs:
                    _offer(found, "internal_rating", rs[-1], f"{where} (proposed rating)", 0.98, raw)
            else:
                _offer(found, f, _value_of(f, value), where, 0.98, raw)
            return True
    if only_special:
        return False
    field = ingest._match(label) or _ar_field(label)
    if field and field in ingest.FIELDS and field not in ("sector",):
        _offer(found, field, _value_of(field, value), where, 0.9, raw)
    return bool(field)


def free_text(text: str, tables: list[list[list[str]]] | None = None) -> dict[str, dict[str, Any]]:
    """Fields read from the text of any proposal layout (English or Arabic)."""
    found: dict[str, dict[str, Any]] = {}
    lines = unwrap(text)
    # 1. the title: "Credit Proposal: <name>" / "Credit proposal for <name>" / Arabic "مقترح ائتماني: <name>"
    for i, ln in enumerate(lines[:8]):
        m = re.match(r"^(?:credit\s+(?:proposal|application|memo(?:randum)?)|facility\s+proposal|مقترح\s+ائتماني|طلب\s+تسهيلات(?:\s+ائتمانية)?|مذكرة\s+ائتمانية)"
                     r"\s*(?:[:\-–—·]|for|لـ|ل)?\s*(.+)$", ln, re.I)
        if m and len(m.group(1)) > 2:
            name = m.group(1)
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if (nxt and len(nxt) <= 40 and ":" not in nxt and not _SUFFIX.search(name)
                    and _SUFFIX.search(nxt)):
                name = f"{name} {nxt}"  # a title wrapped over two lines (PDF, scan)
            _offer(found, "name", _value_of("name", name), f"title (line {i + 1})", 0.95, ln)
            break
    # 2. labelled lines and table rows
    for i, ln in enumerate(lines, start=1):
        cells = [c.strip() for c in ln.split("|")] if "|" in ln else None
        if cells and len(cells) >= 4 and len(cells) % 2 == 0 and _HEADER_LABEL.match(cells[2]):
            # a header block row of label | value pairs ("Branch / unit | … | Customer | …")
            for j in range(0, len(cells) - 1, 2):
                _pair(found, cells[j], cells[j + 1], f"table row {i}", ln)
            continue
        if cells and len(cells) >= 2:
            if _pair(found, cells[0], cells[1], f"table row {i}", ln, only_special=True):
                continue
            label, rest = cells[0], " | ".join(cells[1:])
        else:
            m = re.match(r"^([^:：]{2,48})[:：]\s*(.+)$", ln)
            if not m:
                m2 = _LABEL_NUM.match(ln)
                f2 = (ingest._match(m2.group(1)) or ("total_debt" if re.match(r"net debt", m2.group(1), re.I) else None)) if m2 else None
                if f2 in FIN + ("current_ratio",):
                    _offer(found, f2, float(m2.group(2).replace(",", "")), f"line {i}", 0.85, ln)
                continue
            label, rest = m.group(1), m.group(2)
        field = ingest._match(label) or _ar_field(label) or ("total_debt" if re.match(r"\s*net debt", label, re.I) else None)
        if field and field in ingest.FIELDS:
            v = _value_of(field, rest)
            _offer(found, field, v, f"{'table row' if cells else 'line'} {i}", 0.9, ln)
    # 2b. a bank-form header block one cell per line: the label on one line, its value on the next
    two = {"customer": "name", "borrower": "name", "obligor": "name", "applicant": "name", "group": "group_name",
           "rating existing / proposed": "internal_rating", "rating existing/proposed": "internal_rating", "internal rating": "internal_rating",
           "industry code": "_isic", "sector": "sector", "rm / unit": "rm", "relationship manager": "rm"}
    for i in range(len(lines) - 1):
        lab = lines[i].strip().lower().rstrip(":")
        nxt, k = lines[i + 1], i + 1
        if lab.endswith("/") and i + 2 < len(lines):
            lab, nxt, k = f"{lab} {lines[i + 1].strip().lower()}", lines[i + 2], i + 2
        f = two.get(lab)
        if not f or ":" in nxt or "|" in nxt:
            continue
        if f == "_isic":
            sec = sector_of_code(nxt)
            if sec:
                _offer(found, "sector", sec, f"line {k + 1} (industry code {nxt.strip()})", 0.92, nxt)
            continue
        if f == "internal_rating":
            rs = re.findall(r"\b" + _RATING + r"(?![A-Za-z])", nxt)
            v = rs[-1] if rs and rs[-1] in RATINGS else None
        else:
            v = _value_of(f, nxt)
        _offer(found, f, v, f"line {k + 1}", 0.93, nxt)
    # 2c. the ask in a sentence: "total limits from SAR 318.0m to SAR 514.0m", "Total limits AED 476.6m -> AED 656.8m"
    for i, ln in enumerate(lines, start=1):
        m = re.search(r"total limits?\s*(?:\|\s*)?(?:from\s*)?(?:SAR|AED|USD)\s*([\d,.]+)\s*(m|bn)?\s*(?:to|->|→)\s*(?:SAR|AED|USD)\s*([\d,.]+)\s*(m|bn)",
                      ln, re.I)
        if m:
            v = float(m.group(3).replace(",", "")) * (1000 if m.group(4).lower() == "bn" else 1)
            _offer(found, "amount", v, f"line {i} (total limits)", 0.9, ln)
            break
    # 3. inline facts anywhere ("Sector: Construction." inside a sentence, "Internal rating BB-", "rated BB-")
    for i, ln in enumerate(lines, start=1):
        for pat, field in ((r"\bsector\s*[:\-]?\s*([A-Z][A-Za-z ]{3,40})", "sector"),
                           (r"(?:internal|obligor|risk)?\s*rating\s*(?:of|is|:)?\s*" + _RATING + r"(?![A-Za-z])", "internal_rating"),
                           (r"\brated\s+" + _RATING + r"(?![A-Za-z])", "internal_rating"),
                           (r"التصنيف(?:\s+الداخلي)?\s*[:：]?\s*" + _RATING, "internal_rating"),
                           (r"\btenor\s+(?:of\s+)?(\d{1,2})\s*(?:years?|yrs?)", "tenor_years"),
                           (r"(\d{1,2})[- ]year\s+(?:term|tenor|facility|loan)", "tenor_years"),
                           (r"(?:SAIBOR|EIBOR|SOFR|KIBOR)\s*\+\s*" + _NUM + r"\s*(?:bps|bp|basis points|%)?", "margin_bps")):
            m = re.search(pat, ln, re.I)
            if not m:
                continue
            raw = m.group(0)
            v = _value_of(field, m.group(1) if field not in ("margin_bps",) else raw)
            if field == "sector":
                v = _sector(m.group(1))
            _offer(found, field, v, f"line {i}", 0.8, ln)
    if "sector" in found and found["sector"]["value"] not in SECTORS:
        sec = sector_of_code(str(found["sector"]["value"])) or _sector(str(found["sector"]["value"]))
        if sec:
            found["sector"]["value"] = sec
        else:
            found.pop("sector")
    # 4. a sector from the business words when no sector is stated
    if "sector" not in found:
        sec = _sector(" ".join(lines[:40]))
        if sec:
            _offer(found, "sector", sec, "business description (inferred)", 0.5, "")
    return found


_ROW_NUMS = re.compile(r"^(.*?)\s*((?:\s*-?\d{1,3}(?:,\d{3})*(?:\.\d+)?){2,3})(?:\s+[^\s\d]{1,3})?\s*$")


def _facilities_plain(text: str) -> list[dict[str, Any]]:
    """The same table as PDF text gives it: 'Facility Existing Proposed Pricing (bps)', then '<name> 50.0 50.0 75',
    a long name wrapped over lines before its numbers."""
    out: list[dict[str, Any]] = []
    on, label = False, ""
    for ln in text.splitlines():
        s = ln.strip()
        if not s or "|" in s:
            continue
        if re.search(r"\bexisting\b", s, re.I) and re.search(r"\bproposed\b", s, re.I) and len(s) < 90:
            on, label = True, ""
            continue
        if not on:
            continue
        if re.match(r"^(total|الإجمالي|المجموع)", s, re.I):
            break
        m = _ROW_NUMS.match(s)
        if m and (m.group(1) or label):
            nums = [float(x.replace(",", "")) for x in m.group(2).split()]
            name = (label + " " + m.group(1)).strip()
            label = ""
            out.append({"facility": name, "existing": nums[0], "proposed": nums[1],
                        "pricing_bps": nums[2] if len(nums) > 2 else None})
        elif re.match(r"^\d", s) or re.match(r"^\d+\.", s) and len(out) > 0:
            break
        else:
            label = (label + " " + s).strip()
            if len(label) > 160:
                break
    return out


def facilities_table(text: str) -> list[dict[str, Any]]:
    """Rows of a facilities table: '<facility> | <existing> | <proposed> | <pricing bps>' (Word or PDF text)."""
    plain = _facilities_plain(text)
    if plain and "|" not in text:
        return plain
    out = []
    head_seen = False
    for ln in text.splitlines():
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        low = " ".join(cells).lower()
        if re.search(r"facility|limit|التسهيل|الحد", cells[0], re.I) and re.search(r"proposed|existing|مقترح|حالي", low):
            head_seen = True
            continue
        if not head_seen or len(cells) < 3:
            continue
        if re.match(r"^(total|الإجمالي|المجموع)", cells[0], re.I):
            head_seen = False
            continue
        nums = [_n(c) for c in cells[1:]]
        if nums[0] is None and (len(nums) < 2 or nums[1] is None):
            head_seen = False
            continue
        out.append({"facility": cells[0], "existing": nums[0], "proposed": nums[1] if len(nums) > 1 else nums[0],
                    "pricing_bps": nums[2] if len(nums) > 2 else None})
    return out


def facility_type_of(name: str) -> str:
    low = name.lower()
    if re.search(r"bid bond|performance|guarantee|\blg\b|advance payment|retention|ضمان|كفالة", low):
        return "performance_lg"
    if re.search(r"letter of credit|\blc\b|اعتماد", low):
        return "trade_lc"
    if re.search(r"overdraft|revolv|working capital|receivable|trade finance|سحب على المكشوف|رأس المال العامل", low):
        return "revolver"
    return "term_loan"
