"""Credit memo ingestion: a memo (.docx) read into the engine's Proposal schema
(DEALDESK_API.md section 2), every field with where in the memo it was found
and a confidence, for the user to confirm before any analysis.

The reader is deterministic: it walks the memo's tables (label | value rows)
and its paragraphs ("Label: value"), matches each label to a field through a
synonym table, and parses the value with the field's parser. A field found in
a labelled table cell is read with high confidence; one found in running text
with a pattern, lower. Nothing is guessed: a field the memo does not state is
returned empty with confidence 0.

`write_memo(proposal)` writes a memo in house style from a proposal (the
reference engine's memos and the tests).
"""
from __future__ import annotations

import io
import re
from typing import Any, Callable


class IngestError(ValueError):
    """A memo that cannot be read, with a reason the user can act on."""


def _num(s: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", s.replace("−", "-"))
    if not m:
        return None
    v = float(m.group(0).replace(",", ""))
    low = s.lower()
    if re.search(r"\b(bn|billion)\b", low):
        v *= 1000
    return v


def _int(s: str) -> int | None:
    v = _num(s)
    return None if v is None else int(round(v))


def _pct(s: str) -> float | None:
    return _num(s)


def _bps(s: str) -> int | None:
    v = _num(s.split("+")[-1]) if "+" in s else _num(s)
    if v is None:
        return None
    if "%" in s and "bps" not in s.lower():
        v *= 100
    return int(round(v))


def _text(s: str) -> str:
    return s.strip().strip(".").strip()


def _name(s: str) -> str:
    """A name without a trailing book or group code: 'Al Rayyan Holding (DG001)' -> 'Al Rayyan Holding'."""
    return re.sub(r"\s*\((?:[A-Z]{1,3}\d{2,6}|CR\s*\d+)\)\s*$", "", _text(s))


RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C"]


def _rating(s: str) -> str | None:
    for tok in re.findall(r"\b(?:AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC|CC|C)(?![A-Za-z])", s):
        if tok in RATINGS:
            return tok
    return None


def _choice(options: dict[str, str]) -> Callable[[str], str | None]:
    def parse(s: str) -> str | None:
        low = s.lower()
        for key, value in options.items():
            if key in low:
                return value
        return None
    return parse


FACILITY = _choice({"performance": "performance_lg", "financial guarantee": "financial_lg", "financial lg": "financial_lg",
                    "letter of credit": "trade_lc", "trade lc": "trade_lc", " lc": "trade_lc", "revolv": "revolver",
                    "working capital": "revolver", "term": "term_loan"})
STRUCTURE = _choice({"murabaha": "murabaha", "tawarruq": "tawarruq", "ijara": "ijara", "ijarah": "ijara", "musharaka": "musharaka",
                     "conventional": "conventional"})
CURRENCY = _choice({"usd": "USD", "us dollar": "USD", "sar": "SAR", "riyal": "SAR"})
AMORT = _choice({"balloon": "balloon", "bullet": "bullet", "equal": "equal", "amortis": "equal", "amortiz": "equal"})

#: field -> (label, synonyms (lower-case label starts), parser, section)
FIELDS: dict[str, tuple[str, tuple[str, ...], Callable[[str], Any]]] = {
    "name": ("Obligor", ("obligor", "borrower", "customer name", "applicant", "company"), _name),
    "cr_number": ("CR number", ("cr number", "cr no", "commercial registration"), lambda s: (re.search(r"\d{8,12}", s) or [None])[0]),
    "sector": ("Sector", ("sector", "industry"), _text),
    "region": ("Region", ("region", "location", "city"), _text),
    "group_name": ("Group", ("group", "connected group"), _name),
    "internal_rating": ("Internal rating", ("internal rating", "rating", "obligor rating", "risk rating"), _rating),
    "simah_flag": ("SIMAH", ("simah",), lambda s: _text(s).lower()),
    "rm": ("Relationship manager", ("relationship manager", "rm"), _text),
    "purpose": ("Purpose", ("purpose",), _text),
    "facility_type": ("Facility", ("facility type", "facility", "product"), FACILITY),
    "structure": ("Structure", ("islamic structure", "structure", "shariah structure"), STRUCTURE),
    "currency": ("Currency", ("currency",), CURRENCY),
    "amount": ("Amount (million)", ("amount", "requested amount", "limit", "facility amount"), _num),
    "tenor_years": ("Tenor (years)", ("tenor", "maturity"), _int),
    "grace_years": ("Grace (years)", ("grace",), _int),
    "amortisation": ("Repayment", ("repayment", "amortisation", "amortization"), AMORT),
    "margin_bps": ("Margin (bps)", ("margin", "pricing", "profit rate"), _bps),
    "upfront_fee_bps": ("Upfront fee (bps)", ("upfront fee", "arrangement fee", "front-end fee"), _bps),
    "commitment_fee_bps": ("Commitment fee (bps)", ("commitment fee",), _bps),
    "commission_bps": ("Commission (bps)", ("commission", "lg commission", "lc commission", "lg/lc commission"), _bps),
    "revenue": ("Revenue (million)", ("revenue", "sales", "turnover"), _num),
    "ebitda": ("EBITDA (million)", ("ebitda",), _num),
    "total_debt": ("Total debt (million)", ("total debt", "borrowings"), _num),
    "debt_service": ("Debt service (million)", ("debt service",), _num),
    "net_worth": ("Net worth (million)", ("net worth", "equity", "tangible net worth"), _num),
    "current_ratio": ("Current ratio", ("current ratio",), _num),
    "collateral_type": ("Collateral", ("collateral type", "collateral", "security offered"), _choice({
        "real estate": "real_estate", "property": "real_estate", "land": "real_estate", "receivable": "receivables",
        "cash": "cash", "share": "shares", "equipment": "plant_equipment", "vehicle": "vehicles"})),
    "collateral_value": ("Collateral value (million)", ("collateral value", "security value", "market value"), _num),
    "guarantee_type": ("Guarantee", ("guarantee type", "guarantee", "kafalah"), _choice({
        "kafalah": "kafalah", "government": "government", "personal": "personal", "bank": "bank", "corporate": "corporate"})),
    "guarantee_coverage_pct": ("Guarantee cover (%)", ("guarantee cover", "coverage", "guarantee coverage"), _pct),
    # PLAN_R6 D1: the short form's remaining fields
    "external_rating": ("External rating", ("external rating", "agency rating"), _rating),
    "guarantor": ("Guarantor", ("guarantor",), lambda s: None if re.match(r"\s*(none|n/a|-)", s, re.I) else _name(s)),
    "dscr_min": ("DSCR minimum (x)", ("dscr minimum", "dscr covenant", "minimum dscr", "dscr min"), _num),
    "leverage_max": ("Debt/EBITDA maximum (x)", ("leverage maximum", "debt/ebitda maximum", "leverage covenant", "maximum leverage",
                                                  "debt/ebitda covenant", "leverage max"), _num),
    "cash_margin_pct": ("Cash margin (%)", ("cash margin",), _pct),
}
REQUIRED = ("name", "internal_rating", "facility_type", "amount", "tenor_years", "margin_bps")


def _match(label: str) -> str | None:
    low = re.sub(r"\s+", " ", label.lower()).strip(" :")
    best, best_len = None, 0
    for field, (_, syns, _) in FIELDS.items():
        for s in syns:
            if (low == s or low.startswith(s + " ") or low.startswith(s + "(") or low.startswith(s)) and len(s) > best_len:
                best, best_len = field, len(s)
    return best


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def extract_xlsx(data: bytes, filename: str) -> dict[str, Any]:
    """PLAN_R6 D3: a short-form sheet read by labelled cells (label in one cell, the value in the next cell to the right)."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001 - any unreadable file
        raise IngestError(f"{filename} is not a readable Excel workbook (.xlsx).") from e
    found: dict[str, dict[str, Any]] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            cells = [(c.coordinate if hasattr(c, "coordinate") else "", _cell(c.value)) for c in row]
            for i, (coord, text) in enumerate(cells[:-1]):
                if not text or not re.search(r"[A-Za-z]", text):
                    continue
                field = _match(text)
                if not field:
                    continue
                nxt = next(((cd, t) for cd, t in cells[i + 1:] if t), None)
                if not nxt:
                    continue
                value = FIELDS[field][2](nxt[1])
                if value in (None, "") or (field in found and found[field]["confidence"] >= 0.97):
                    continue
                found[field] = {"field": field, "label": FIELDS[field][0], "value": value,
                                "source": f"Sheet {ws.title}, cell {nxt[0]}", "confidence": 0.97}
    from backend.dealdesk_thread import longform
    out = _result(found, filename)
    # PLAN_R6 D1 (D2 session): a short-form sheet opens in the Short form; a sheet with long-form labels in the Long form
    flat = {f["field"]: f["value"] for f in out["fields"] if f["value"] is not None}
    ln = {k: flat[k] for k in longform.LINE_KEYS if k in flat}
    out.update({"form": longform.kind_of_xlsx(data), "long": {"lines": [ln] if ln.get("amount") else []},
                "long_found": [f"line.0.{k}" for k in ln] if ln.get("amount") else []})
    return out


def _result(found: dict[str, dict[str, Any]], filename: str) -> dict[str, Any]:
    fields = []
    for field, (label, _, _) in FIELDS.items():
        f = found.get(field) or {"field": field, "label": label, "value": None, "source": "Not stated in the file", "confidence": 0.0}
        fields.append({k: v for k, v in f.items() if k != "raw"})
    stated = sum(1 for f in fields if f["value"] is not None)
    missing = [FIELDS[f][0] for f in REQUIRED if f not in found]
    return {"filename": filename, "fields": fields, "coverage": round(stated / len(fields), 4), "missing_required": missing,
            "read": stated, "total": len(fields),
            "summary": f"{stated} of {len(fields)} fields read; please confirm",
            "proposal": proposal_from_fields({f["field"]: f["value"] for f in fields if f["value"] is not None},
                                             {"filename": filename}, strict=False)}


def extract(data: bytes, filename: str) -> dict[str, Any]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        return extract_xlsx(data, filename)
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001 - any unreadable file
        raise IngestError(f"{filename} is not a readable Word document (.docx).") from e
    found: dict[str, dict[str, Any]] = {}

    def offer(field: str, raw: str, source: str, confidence: float) -> None:
        value = FIELDS[field][2](raw)
        if value in (None, ""):
            return
        if field in found and found[field]["confidence"] >= confidence:
            return
        found[field] = {"field": field, "label": FIELDS[field][0], "value": value, "source": source, "confidence": confidence, "raw": raw.strip()[:120]}

    # Tables: label | value (| value ...). For a financials table (label | 2023 | 2024 | 2025 | 2026P ...), the latest actual year.
    for ti, table in enumerate(doc.tables, start=1):
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        header = rows[0] if rows else []
        years = [i for i, h in enumerate(header) if re.fullmatch(r"(19|20)\d{2}A?", h.strip())]
        for ri, cells in enumerate(rows, start=1):
            if len(cells) < 2:
                continue
            field = _match(cells[0])
            if not field:
                continue
            if years and field in ("revenue", "ebitda", "total_debt", "debt_service", "net_worth", "current_ratio"):
                col = years[-1]
                offer(field, cells[col], f"Table {ti}, row {ri}, {header[col]}", 0.97)
            else:
                offer(field, cells[1], f"Table {ti}, row {ri}", 0.97)
    # Paragraphs: "Label: value".
    for pi, para in enumerate(doc.paragraphs, start=1):
        text = para.text.strip()
        m = re.match(r"^([A-Za-z][A-Za-z /()&'-]{1,40}):\s*(.+)$", text)
        if m:
            field = _match(m.group(1))
            if field:
                offer(field, m.group(2), f"Paragraph {pi}", 0.9)
        elif re.search(r"(saibor|sofr)\s*\+", text, re.I):
            offer("margin_bps", text[text.lower().find("+"):], f"Paragraph {pi}", 0.75)
    from backend.dealdesk_thread import longform
    out = _result(found, filename)
    # PLAN_R6 D1 (D2 session): a Word memo opens in the Long form, prefilled, with every read field marked
    long, long_found = longform.extract_docx(doc, {f["field"]: f["value"] for f in out["fields"] if f["value"] is not None})
    out.update({"form": "long", "long": long, "long_found": long_found})
    return out


def _f(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def proposal_from_fields(fields: dict[str, Any], source: dict[str, Any], strict: bool = True,
                         long: dict[str, Any] | None = None) -> dict[str, Any]:
    """The engine's Proposal (without proposal_id) from confirmed fields (and, from the long form, its sections)."""
    if long:
        from backend.dealdesk_thread import longform
        lines = long.get("lines") or []
        fields = dict(fields)
        if lines:  # the flat ask fields come from the first line; longform.apply aggregates every line
            for k in longform.LINE_KEYS:
                if lines[0].get(k) not in (None, "") and k != "purpose":
                    fields[k] = lines[0][k]
            fields["amount"] = sum(float(longform._f(ln.get("amount")) or 0) for ln in lines) or fields.get("amount")
        if strict:
            msgs = longform.validate(long)
            if msgs:
                raise IngestError(" ".join(msgs))
        p = proposal_from_fields(fields, source, strict=strict)
        return longform.apply(p, long, p["obligor"]["internal_rating"])
    g = fields.get
    if strict:
        missing = [FIELDS[k][0] for k in ("name", "sector", "internal_rating", "amount", "tenor_years", "margin_bps") if g(k) in (None, "")]
        if missing:
            raise IngestError(f"Missing: {', '.join(missing)}.")
        if g("internal_rating") not in RATINGS:
            raise IngestError(f"{g('internal_rating')} is not a grade on the rating scale.")
    amount = _f(g("amount")) or 0.0
    tenor = int(_f(g("tenor_years")) or 1)
    ft = g("facility_type") or "term_loan"
    funded = ft in ("term_loan", "revolver")
    rating = g("internal_rating") or "BBB"
    year = {"year": 2025, "kind": "actual", "revenue": _f(g("revenue")) or 0.0, "ebitda": _f(g("ebitda")) or 0.0,
            "total_debt": _f(g("total_debt")) or 0.0, "debt_service": _f(g("debt_service")) or 0.0,
            "net_worth": _f(g("net_worth")) or 0.0, "current_ratio": _f(g("current_ratio")) or 0.0}
    assumed: list[str] = []
    fields = dict(fields)
    for k in ("collateral_type", "guarantee_type", "facility_type", "structure", "amortisation", "currency"):
        v = fields.get(k)
        if isinstance(v, str) and v and " " in v.strip() or (isinstance(v, str) and v and v != v.lower() and k != "currency"):
            fields[k] = FIELDS[k][2](v) or v  # form labels ("real estate", "plant and equipment") to the engine's keys
    g = fields.get
    gid, gname, existing_group = _group(g("group_name") or "")
    coll = []
    if g("collateral_type") and _f(g("collateral_value")):
        coll.append({"collateral_id": "C1", "type": g("collateral_type"), "value": _f(g("collateral_value")), "currency": "SAR",
                     "valuation_date": "", "pledged_in_ask": True})
    guar = []
    if g("guarantee_type"):
        cover = _f(g("guarantee_coverage_pct"))
        if cover is None:
            cover = 100.0
            assumed.append("guarantee cover 100%")
        if not g("guarantor"):
            assumed.append("guarantor not named")
        guar.append({"guarantee_id": "G1", "type": g("guarantee_type"), "guarantor": g("guarantor") or "Guarantor not named", "guarantor_rating": rating,
                     "coverage_pct": cover, "offered_in_ask": True})
    covenants = []
    if _f(g("dscr_min")):
        covenants.append({"type": "DSCR", "threshold": _f(g("dscr_min"))})
    if _f(g("leverage_max")):
        covenants.append({"type": "Net debt / EBITDA", "threshold": _f(g("leverage_max"))})
    package = "standard" if covenants else "none"
    for k, text in (("margin_bps", None), ("upfront_fee_bps", "upfront fee 0 bps"), ("grace_years", "no grace period"),
                    ("amortisation", "equal amortisation"), ("structure", "conventional structure"), ("currency", "SAR"),
                    ("facility_type", "term finance")):
        if text and g(k) in (None, ""):
            assumed.append(text)
    if not (_f(g("revenue")) or _f(g("ebitda"))):
        assumed.append("no financials stated: DSCR and Debt/EBITDA not tested")
    if not coll and not guar:
        assumed.append("unsecured, no guarantee")
    if not covenants:
        assumed.append("no financial covenants")
    return {
        "status": "new", "rm": g("rm") or "", "business_unit": "Corporate Banking", "received": "", "purpose": g("purpose") or "",
        "obligor": {"obligor_id": "", "existing": False, "name": g("name") or "", "cr_number": str(g("cr_number") or ""), "group_id": gid,
                    "group_name": gname, "connected_parties": [], "sector": g("sector") or "", "sub_sector": "", "sector_code": "",
                    "segment": g("sector") or "", "region": g("region") or "", "sme": (g("sector") or "") == "SME", "gre": False,
                    "internal_rating": rating, "external_rating": g("external_rating") or None, "pd_master_scale": None, "simah_flag": g("simah_flag") or "clear",
                    "existing_exposure_sar_mn": 0.0, "existing_facilities": []},
        "financials": {"currency": "SAR", "years": [year]},
        "ask": {"facility_type": ft, "structure": g("structure") or "conventional", "currency": g("currency") or "SAR", "amount": amount,
                "tenor_years": tenor, "grace_years": int(_f(g("grace_years")) or 0), "amortisation": g("amortisation") or "equal",
                "balloon_pct": 0, "margin_bps": int(_f(g("margin_bps")) or 0), "upfront_fee_bps": int(_f(g("upfront_fee_bps")) or 0),
                "commitment_fee_bps": int(_f(g("commitment_fee_bps")) or 0), "commission_bps": int(_f(g("commission_bps")) or 0),
                "utilisation_pct": 100, "funded_share_pct": 100 if funded else 0, "unfunded_type": ft if not funded else "performance_lg",
                "cash_margin_pct": _f(g("cash_margin_pct")) or 0, "collateral_ids": [c["collateral_id"] for c in coll],
                "guarantee_id": "G1" if guar else None, "guarantee_coverage_pct": guar[0]["coverage_pct"] if guar else 0,
                "covenant_package": package},
        "security": {"collateral": coll, "guarantees": guar, "covenant_package": package, "covenants": covenants},
        "assumed": assumed,
        "business_case": {"ancillary_income_sar_mn_pa": {}},
        "source": source,
    }


def _group(name: str) -> tuple[str, str, bool]:
    """A group named on the form or in a memo, matched to the corporate book's connected groups by ID or name."""
    name = (name or "").strip()
    if not name:
        return "", "", False
    try:
        from backend.dealdesk import portfolio
        names = portfolio.snapshot()["group_names"]
    except Exception:  # noqa: BLE001 - the book is optional for ingestion
        return "", name, False
    code = re.search(r"\b(CG\d{3,6}(?:-\d{3})?)(?![\d-])", name)
    if code and code.group(1) in names:
        return code.group(1), names[code.group(1)], True
    low = re.sub(r"\s*\(CG[\d-]+\)\s*$", "", name).lower()
    for gid, gn in names.items():
        if str(gn).lower() == low:
            return gid, gn, True
    return "", name, False


def groups(q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Type-ahead over the book's connected groups (PLAN_R6 D1)."""
    from backend.dealdesk import portfolio
    s = portfolio.snapshot()
    low = q.lower().strip()
    rows = [{"group_id": k, "group_name": v, "ead_sar_mn": round(float(s["by_group"].get(k, 0.0)), 1),
             "borrowers": s["group_borrowers"].get(k, 0)} for k, v in s["group_names"].items()
            if not low or low in str(v).lower() or low in str(k).lower()]
    return sorted(rows, key=lambda r: -r["ead_sar_mn"])[:limit]


# ------------------------------------------------------------------ memos (reference engine, tests)

FACILITY_LABEL = {"term_loan": "Term finance", "revolver": "Revolving working capital", "performance_lg": "Performance letter of guarantee",
                  "financial_lg": "Financial letter of guarantee", "trade_lc": "Trade letter of credit"}


def write_memo(p: dict[str, Any]) -> bytes:
    """A credit memo in house style for a proposal: the fields a credit officer reads, in labelled tables."""
    from backend.house_style import Meta
    from backend.house_style import docx as hd
    ob, a = p["obligor"], p["ask"]
    from backend.dealdesk.economics import reporting_period  # R14 E (K18 #2): one reporting period
    meta = Meta(f"Credit proposal · {ob['name']}", book="corporate", period=reporting_period()["quarter"], subject=p.get("purpose", ""),
                generated_by=p.get("rm", ""), reference=p["proposal_id"])
    doc = hd.document(meta, kind="Credit memo", subtitle=ob["name"], cover="block")
    hd.heading(doc, "1. Obligor")
    hd.table(doc, ["Item", "Detail"], [["Obligor", ob["name"]], ["CR number", ob["cr_number"]], ["Sector", ob["sector"]],
                                      ["Region", ob["region"]], ["Group", ob["group_name"]], ["Internal rating", ob["internal_rating"]],
                                      ["SIMAH", ob["simah_flag"]], ["Relationship manager", p.get("rm", "")]], gap=False)
    hd.heading(doc, "2. Facility requested")
    hd.para(doc, f"Purpose: {p.get('purpose', '')}")
    hd.table(doc, ["Term", "Requested"], [
        ["Facility", FACILITY_LABEL.get(a["facility_type"], a["facility_type"])], ["Structure", a["structure"].capitalize()],
        ["Currency", a["currency"]], ["Amount", f"{a['currency']} {a['amount']:,.1f} million"], ["Tenor", f"{a['tenor_years']} years"],
        ["Grace", f"{a['grace_years']} years"], ["Repayment", a["amortisation"]],
        ["Margin", f"{'SOFR' if a['currency'] == 'USD' else 'SAIBOR'} + {a['margin_bps']} bps"], ["Upfront fee", f"{a['upfront_fee_bps']} bps"],
        ["Commitment fee", f"{a['commitment_fee_bps']} bps"], ["Commission", f"{a['commission_bps']} bps"]], gap=False)
    hd.heading(doc, "3. Financials")
    years = p["financials"]["years"]
    hd.table(doc, ["SAR million"] + [f"{y['year']}{'P' if y['kind'] == 'projection' else ''}" for y in years],
             [[lab] + [y[k] for y in years] for lab, k in (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("Total debt", "total_debt"),
                                                         ("Debt service", "debt_service"), ("Net worth", "net_worth"),
                                                         ("Current ratio", "current_ratio"))], gap=False)
    hd.heading(doc, "4. Security")
    coll = p["security"]["collateral"]
    pledged = [c for c in coll if c.get("pledged_in_ask")] or coll[:1]
    rows = []
    if pledged:
        rows += [["Collateral", pledged[0]["type"].replace("_", " ")], ["Collateral value", f"SAR {pledged[0]['value']:,.1f} million"]]
    for g in p["security"]["guarantees"][:1]:
        rows += [["Guarantee", g["type"]], ["Guarantee cover", f"{g['coverage_pct']}%"]]
    hd.table(doc, ["Item", "Detail"], rows or [["Collateral", "none"]], gap=False)
    return hd.to_bytes(doc)
