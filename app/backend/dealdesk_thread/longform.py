"""PLAN_R6 D1 (Session D2): the long-form credit application, on screen and from an uploaded memo.

The long form keeps the short form's flat fields (obligor, CR number, group, sector, region, ratings, SIMAH)
and adds a structured ``long`` object:

    connected_parties   text            ownership          [{holder, share}]
    rating_date         YYYY-MM-DD      external_agency    text (the external grade is the flat field)
    years               [{year, revenue, ebitda, net_income, total_debt, cash, equity, operating_cash_flow,
                          capex, interest, debt_service}]      (three years, SAR million)
    lines               [{facility_type, structure, currency, amount, tenor_years, margin_bps, upfront_fee_bps,
                          commitment_fee_bps, commission_bps, amortisation, grace_years, purpose}]
    collateral          [{type, value, valuation_date}]       (LTV is computed: total amount / collateral value)
    guarantees          [{type, guarantor, coverage_pct}]
    receivables_assignment  bool        cash_margin_pct    number
    covenants           [{type, threshold}] (besides the flat DSCR minimum / leverage maximum)   conditions  text
    existing_exposure   SAR million     ancillary          {cash_management, payroll, fx, trade, deposits} SAR m p.a.
    rm, business_unit   text

Pricing several lines: the engine prices one ask per proposal. A long form with several lines is priced as
one aggregate ask (decision recorded in docs/STATUS_R6_LONGFORM.md): amounts summed (USD lines converted at
the engine's USD/SAR rate when currencies differ), margin, fees and commission amount-weighted, the longest
tenor (and its grace and repayment), the funded share from the funded lines, the largest line's facility
type and structure. Every line is still stored and shown line by line in the proposal view and the report.
"""
from __future__ import annotations

import re
from typing import Any

#: the financials grid, in order: key, label, label synonyms in a memo table (lower case)
METRICS: list[tuple[str, str, tuple[str, ...]]] = [
    ("revenue", "Revenue", ("revenue", "sales", "turnover")),
    ("ebitda", "EBITDA", ("ebitda",)),
    ("net_income", "Net income", ("net income", "net profit")),
    ("total_debt", "Total debt", ("total debt", "borrowings")),
    ("cash", "Cash", ("cash",)),
    ("equity", "Equity", ("net worth", "equity", "tangible net worth")),
    ("operating_cash_flow", "Operating cash flow", ("operating cash flow", "cash from operations")),
    ("capex", "Capex", ("capital expenditure", "capex")),
    ("interest", "Interest", ("interest", "finance cost", "profit expense")),
    ("debt_service", "Debt service", ("debt service",)),
]
LINE_KEYS = ("facility_type", "structure", "currency", "amount", "tenor_years", "margin_bps", "upfront_fee_bps",
             "commitment_fee_bps", "commission_bps", "amortisation", "grace_years", "purpose")
UNFUNDED = ("performance_lg", "financial_lg", "trade_lc")
ANCILLARY = ("cash_management", "payroll", "fx", "trade", "deposits")


def _f(v: Any) -> float | None:
    if v in (None, "") or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _metric(label: str) -> str | None:
    low = re.sub(r"\s+", " ", label.lower()).strip(" :")
    best, n = None, 0
    for key, _, syns in METRICS:
        for s in syns:
            if low.startswith(s) and len(s) > n:
                best, n = key, len(s)
    return best


# ---------------------------------------------------------------------------------------------- extraction

def extract_docx(doc: Any, flat: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The long-form object from a Word memo, and the keys read from it (for marking on screen)."""
    from backend.dealdesk_thread import ingest
    found: list[str] = []
    long: dict[str, Any] = {}
    years: dict[int, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    coll_dates: list[str] = []
    for table in doc.tables:
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        if not rows:
            continue
        header = rows[0]
        ycols = [(i, int(m.group(1))) for i, h in enumerate(header) if (m := re.fullmatch(r"((?:19|20)\d{2})A?", h.strip()))]
        if ycols:
            for cells in rows[1:]:
                key = _metric(cells[0]) if cells else None
                if not key:
                    continue
                for i, y in ycols:
                    v = _f(re.sub(r"[^\d.\-]", "", cells[i]) if i < len(cells) else None)
                    if v is not None:
                        years.setdefault(y, {"year": y})[key] = v
                        found.append(f"fin.{y}.{key}")
            continue
        low0 = header[0].lower() if header else ""
        if low0.startswith("ownership"):
            own = [{"holder": r[0], "share": r[1]} for r in rows[1:] if len(r) > 1 and r[0]]
            if own:
                long["ownership"] = own
                found.append("ownership")
            continue
        if low0.startswith("term") and len(header) > 2:
            # several facility lines: Term | Line 1 | Line 2 ...
            for col in range(1, len(header)):
                ln: dict[str, Any] = {}
                for r in rows[1:]:
                    field = ingest._match(r[0]) if r else None
                    if field in LINE_KEYS and col < len(r):
                        v = ingest.FIELDS[field][2](r[col])
                        if v not in (None, ""):
                            ln[field] = v
                if ln.get("amount"):
                    lines.append(ln)
        for r in rows:
            if len(r) > 1 and r[0].lower().startswith("valuation date") and re.search(r"\d{4}-\d{2}-\d{2}", r[1]):
                coll_dates.append(re.search(r"\d{4}-\d{2}-\d{2}", r[1]).group(0))
            if len(r) > 1 and r[0].lower().startswith(("assignment of receivables", "receivables assignment")):
                long["receivables_assignment"] = not re.match(r"\s*(no|none|n/a)", r[1], re.I)
                found.append("receivables_assignment")
            if len(r) > 1 and r[0].lower().startswith(("rating date", "internal rating date")):
                long["rating_date"] = r[1]
                found.append("rating_date")
            if len(r) > 1 and r[0].lower().startswith(("rating agency", "external agency")):
                long["external_agency"] = r[1]
                found.append("external_agency")
            if len(r) > 1 and r[0].lower().startswith("existing exposure"):
                v = ingest._num(r[1])
                if v is not None:
                    long["existing_exposure"] = v
                    found.append("existing_exposure")
    section = ""
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style is not None and str(para.style.name).startswith("Heading"):
            section = text.lower()
            continue
        m = re.match(r"^Reference\s+\S+\s+·\s+([^·]+?)\s+·", text)
        if m and "business_unit" not in long:
            long["business_unit"] = m.group(1).strip()
            found.append("business_unit")
        if text.lower().startswith("conditions precedent") and "conditions" not in long:
            long["conditions"] = text
            found.append("conditions")
        if "group structure" in section and "connected_parties" not in long:
            s = re.search(r"[^.]*(sister compan|connected part)[^.]*\.", text, re.I)
            if s:
                long["connected_parties"] = s.group(0).strip()
                found.append("connected_parties")
    if years:
        long["years"] = [years[y] for y in sorted(years)][-3:]
    if not lines:
        ln = {k: flat[k] for k in LINE_KEYS if flat.get(k) not in (None, "")}
        if ln.get("amount"):
            lines = [ln]
    long["lines"] = lines
    if flat.get("cash_margin_pct") is not None:
        long["cash_margin_pct"] = flat["cash_margin_pct"]
        found.append("cash_margin_pct")
    for i, ln in enumerate(lines):
        found += [f"line.{i}.{k}" for k in ln]
    if flat.get("collateral_type") and flat.get("collateral_value") is not None:
        long["collateral"] = [{"type": flat["collateral_type"], "value": flat["collateral_value"],
                               "valuation_date": coll_dates[0] if coll_dates else ""}]
        found += ["coll.0.type", "coll.0.value"] + (["coll.0.valuation_date"] if coll_dates else [])
    if flat.get("guarantee_type"):
        long["guarantees"] = [{"type": flat["guarantee_type"], "guarantor": flat.get("guarantor") or "",
                               "coverage_pct": flat.get("guarantee_coverage_pct")}]
        found += ["guar.0.type"] + (["guar.0.guarantor"] if flat.get("guarantor") else []) + \
                 (["guar.0.coverage_pct"] if flat.get("guarantee_coverage_pct") is not None else [])
    return long, found


#: labels that only a long form carries; an Excel sheet with any of them opens in the long form
LONG_ONLY = ("net income", "operating cash flow", "capital expenditure", "valuation date", "ownership", "rating date",
             "existing exposure", "line 2", "assignment of receivables", "conditions precedent")


def kind_of_xlsx(data: bytes) -> str:
    try:
        import io

        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if isinstance(v, str) and v.strip().lower().startswith(LONG_ONLY):
                        return "long"
    except Exception:  # noqa: BLE001 - extraction reports unreadable files
        return "short"
    return "short"


# ---------------------------------------------------------------------------------------------- validation

def validate(long: dict[str, Any]) -> list[str]:
    """Plain-word messages for a long form that cannot be priced."""
    from backend.dealdesk_thread.ingest import RATINGS
    msgs: list[str] = []
    lines = long.get("lines") or []
    if not lines:
        msgs.append("Facility lines: add at least one line.")
    for i, ln in enumerate(lines, start=1):
        amt, ten, gr = _f(ln.get("amount")), _f(ln.get("tenor_years")), _f(ln.get("grace_years")) or 0
        if not amt or amt <= 0:
            msgs.append(f"Line {i}: the amount must be a number above zero (million).")
        if ten is None or ten != int(ten) or not 1 <= ten <= 10:
            msgs.append(f"Line {i}: the tenor must be a whole number of years from 1 to 10.")
        elif gr >= ten:
            msgs.append(f"Line {i}: the grace period must be shorter than the tenor.")
        if _f(ln.get("margin_bps")) is None and ln.get("facility_type") not in UNFUNDED:
            msgs.append(f"Line {i}: state the margin in basis points.")
    for i, c in enumerate(long.get("collateral") or [], start=1):
        if not c.get("type"):
            msgs.append(f"Collateral {i}: choose a type.")
        v = _f(c.get("value"))
        if v is None or v < 0:
            msgs.append(f"Collateral {i}: the value must be a number of zero or more (million).")
        if c.get("valuation_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(c["valuation_date"])):
            msgs.append(f"Collateral {i}: the valuation date must be a date (YYYY-MM-DD).")
    for i, g in enumerate(long.get("guarantees") or [], start=1):
        cv = _f(g.get("coverage_pct"))
        if cv is not None and not 0 <= cv <= 100:
            msgs.append(f"Guarantee {i}: the cover must be between 0% and 100%.")
        if g.get("guarantor_rating") and g["guarantor_rating"] not in RATINGS:
            msgs.append(f"Guarantee {i}: the guarantor's rating is not a grade on the scale.")
    if long.get("rating_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(long["rating_date"])):
        msgs.append("Ratings: the internal rating date must be a date (YYYY-MM-DD).")
    cm = _f(long.get("cash_margin_pct"))
    if cm is not None and not 0 <= cm <= 100:
        msgs.append("Security: the cash margin must be between 0% and 100%.")
    return msgs


# ---------------------------------------------------------------------------------------------- the proposal

def apply(p: dict[str, Any], long: dict[str, Any], rating: str) -> dict[str, Any]:
    """Fold the long form into the engine Proposal built from the flat fields."""
    from backend.dealdesk import params
    try:
        usd = float(params.rows("capital")["usd_sar"])
    except Exception:  # noqa: BLE001 - the engine's rate is the default
        usd = 3.75
    long = dict(long)
    ob, ask, sec = p["obligor"], p["ask"], p["security"]
    assumed: list[str] = [a for a in p.get("assumed", [])]
    # 1 obligor and group
    if long.get("connected_parties"):
        ob["connected_parties"] = [s.strip() for s in re.split(r"[;\n]", str(long["connected_parties"])) if s.strip()]
    if long.get("ownership"):
        ob["ownership"] = long["ownership"]
    # 2 ratings
    if long.get("rating_date"):
        ob["rating_date"] = str(long["rating_date"])
    if long.get("external_agency"):
        ob["external_agency"] = str(long["external_agency"])
    # 3 financials
    yrs = []
    for y in sorted(long.get("years") or [], key=lambda r: int(_f(r.get("year")) or 0)):
        if not any(_f(y.get(k)) is not None for k, _, _ in METRICS):
            continue
        row = {"year": int(_f(y.get("year")) or 0), "kind": "actual"}
        for k, _, _ in METRICS:
            row[k] = _f(y.get(k)) or 0.0
        if not _f(y.get("debt_service")):
            row["debt_service"] = row["interest"]
        row["net_worth"] = row["equity"]
        row["current_ratio"] = _f(y.get("current_ratio")) or 0.0
        yrs.append(row)
    if yrs:
        p["financials"] = {"currency": "SAR", "years": yrs}
        assumed = [a for a in assumed if not a.startswith("no financials stated")]
        if any(not _f(y.get("debt_service")) for y in long.get("years") or []):
            assumed.append("debt service taken as the interest stated where no debt service is given")
    # 4 facility lines, priced as one aggregate ask
    lines = [dict(ln) for ln in long.get("lines") or [] if _f(ln.get("amount"))]
    if lines:
        ccys = {str(ln.get("currency") or "SAR") for ln in lines}
        ccy = ccys.pop() if len(ccys) == 1 else "SAR"

        def amt(ln: dict[str, Any]) -> float:
            a = _f(ln.get("amount")) or 0.0
            return a * usd if ccy == "SAR" and (ln.get("currency") or "SAR") == "USD" else a
        total = sum(amt(ln) for ln in lines)
        funded = sum(amt(ln) for ln in lines if (ln.get("facility_type") or "term_loan") not in UNFUNDED)

        def wavg(k: str, which: list[dict[str, Any]]) -> int:
            w = sum(amt(ln) for ln in which)
            return int(round(sum(amt(ln) * (_f(ln.get(k)) or 0) for ln in which) / w)) if w else 0
        f_lines = [ln for ln in lines if (ln.get("facility_type") or "term_loan") not in UNFUNDED]
        u_lines = [ln for ln in lines if (ln.get("facility_type") or "term_loan") in UNFUNDED]
        longest = max(lines, key=lambda ln: (_f(ln.get("tenor_years")) or 1, amt(ln)))
        largest_f = max(f_lines, key=amt) if f_lines else None
        largest_u = max(u_lines, key=amt) if u_lines else None
        main = largest_f or largest_u or lines[0]
        ask.update({
            "facility_type": main.get("facility_type") or "term_loan",
            "structure": (max(lines, key=amt).get("structure") or "conventional"),
            "currency": ccy, "amount": round(total, 4),
            "tenor_years": int(_f(longest.get("tenor_years")) or 1),
            "grace_years": int(_f(longest.get("grace_years")) or 0),
            "amortisation": longest.get("amortisation") or "equal",
            "margin_bps": wavg("margin_bps", f_lines) if f_lines else int(_f(main.get("margin_bps")) or 0),
            "upfront_fee_bps": wavg("upfront_fee_bps", lines),
            "commitment_fee_bps": wavg("commitment_fee_bps", f_lines) if f_lines else 0,
            "commission_bps": wavg("commission_bps", u_lines) if u_lines else int(_f(main.get("commission_bps")) or 0),
            "funded_share_pct": round(100 * funded / total, 2) if total else 100,
            "unfunded_type": (largest_u or {}).get("facility_type") or "performance_lg",
        })
        if len(lines) > 1:
            assumed.append(f"{len(lines)} facility lines priced as one aggregate ask (amount-weighted margin and fees, longest tenor)")
        purposes = [str(ln.get("purpose")) for ln in lines if ln.get("purpose")]
        if purposes and not p.get("purpose"):
            p["purpose"] = "; ".join(dict.fromkeys(purposes))
        p["assumed"] = [a for a in assumed if a not in ("upfront fee 0 bps", "no grace period", "equal amortisation",
                                                        "conventional structure", "SAR", "term finance")]
        assumed = p["assumed"]
    p["facility_lines_long"] = lines
    # 5 security
    if "collateral" in long:
        coll = []
        for i, c in enumerate(long.get("collateral") or [], start=1):
            v = _f(c.get("value"))
            if not c.get("type") or v is None:
                continue
            from backend.dealdesk_thread.ingest import FIELDS
            t = c["type"] if c["type"] in ("cash", "real_estate", "plant_equipment", "receivables", "shares", "vehicles") else \
                (FIELDS["collateral_type"][2](str(c["type"])) or c["type"])
            coll.append({"collateral_id": f"C{i}", "type": t, "value": v, "currency": c.get("currency") or "SAR",
                         "valuation_date": str(c.get("valuation_date") or ""), "pledged_in_ask": True})
        sec["collateral"] = coll
        ask["collateral_ids"] = [c["collateral_id"] for c in coll]
    if "guarantees" in long:
        from backend.dealdesk_thread.ingest import FIELDS
        guar = []
        for i, g in enumerate(long.get("guarantees") or [], start=1):
            if not g.get("type"):
                continue
            t = g["type"] if g["type"] in ("corporate", "personal", "government", "kafalah", "bank") else \
                (FIELDS["guarantee_type"][2](str(g["type"])) or g["type"])
            cover = _f(g.get("coverage_pct"))
            if cover is None:
                cover = 100.0
                assumed.append(f"guarantee {i} cover 100%")
            if not g.get("guarantor"):
                assumed.append(f"guarantor {i} not named")
            guar.append({"guarantee_id": f"G{i}", "type": t, "guarantor": g.get("guarantor") or "Guarantor not named",
                         "guarantor_rating": g.get("guarantor_rating") or rating, "coverage_pct": cover, "offered_in_ask": True})
        sec["guarantees"] = guar
        best = max(guar, key=lambda g: g["coverage_pct"]) if guar else None
        ask["guarantee_id"] = best["guarantee_id"] if best else None
        ask["guarantee_coverage_pct"] = best["coverage_pct"] if best else 0
        if len(guar) > 1:
            assumed.append("several guarantees: the engine prices the one with the highest cover; the others are listed")
    if _f(long.get("cash_margin_pct")) is not None:
        ask["cash_margin_pct"] = _f(long["cash_margin_pct"])
    sec["receivables_assignment"] = bool(long.get("receivables_assignment"))
    # 6 covenants and conditions
    if "covenants" in long:
        covs = [{"type": c["type"], "threshold": _f(c.get("threshold"))} for c in long.get("covenants") or []
                if c.get("type") and _f(c.get("threshold")) is not None]
        sec["covenants"] = (sec.get("covenants") or []) + covs  # DSCR / leverage come from the flat fields
        covs = sec["covenants"]
        pkg = "standard" if covs else "none"
        sec["covenant_package"] = ask["covenant_package"] = pkg
    if long.get("conditions"):
        sec["conditions"] = str(long["conditions"])
    if sec.get("collateral") or sec.get("guarantees"):
        assumed = [a for a in assumed if a != "unsecured, no guarantee"]
    if sec.get("covenants"):
        assumed = [a for a in assumed if a != "no financial covenants"]
    # 7 relationship
    if _f(long.get("existing_exposure")) is not None:
        ob["existing_exposure_sar_mn"] = _f(long["existing_exposure"])
    anc = {k: _f(v) for k, v in (long.get("ancillary") or {}).items() if k in ANCILLARY and _f(v)}
    if anc:
        p["business_case"] = {"ancillary_income_sar_mn_pa": anc}
    # 8 RM and business unit
    if long.get("rm"):
        p["rm"] = str(long["rm"])
    if long.get("business_unit"):
        p["business_unit"] = str(long["business_unit"])
    p["assumed"] = list(dict.fromkeys(assumed))
    p["long_form"] = long
    return p


__all__ = ["METRICS", "LINE_KEYS", "extract_docx", "kind_of_xlsx", "validate", "apply"]
