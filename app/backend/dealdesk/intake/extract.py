"""R16 i: classify a read document and extract its printed fields (deterministic; no model).

Classification scores every document type on (a) its title keywords near the top, (b) how many of its printed labels
appear as "Label: value" lines, (c) the file-name hint; the best score wins and the margin over the runner-up is the
confidence. Extraction finds each label at the start of a line (spaces, case and punctuation ignored, so OCR that drops
spaces still matches), parses the value by type (date DD/MM/YYYY → ISO, "SAR 12,345,678" → number, "12.3%" → 12.3),
and reads list fields as the table printed under their label (header row → sub-fields).
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from backend.dealdesk.intake.doctypes import BY_CODE, DOC_TYPES, DocType

_NORM = re.compile(r"[^a-z0-9]")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def norm(s: str) -> str:
    return _NORM.sub("", str(s).lower())


# ------------------------------------------------------------------------------------------------ value parsing
def parse_date(v: str) -> str | None:
    s = str(v).strip()
    s2 = re.sub(r"\s+", "", s)
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", s2)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s2)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s*([A-Za-z]{3})[a-z]*\.?\s*(\d{4})", s)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return dt.date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def parse_month(v: str) -> str | None:
    """'Oct 2025' / '10/2025' / '2025-10' / 'Oct-25' → '2025-10'."""
    s = str(v).strip()
    m = re.search(r"([A-Za-z]{3})[a-z]*[\s\-/]*(\d{4}|\d{2})\b", s)
    if m and m.group(1).lower() in _MONTHS:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        return f"{y:04d}-{_MONTHS[m.group(1).lower()]:02d}"
    m = re.search(r"\b(\d{4})-(\d{1,2})\b", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2})/(\d{4})\b", s)
    if m:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    d = parse_date(s)
    return d[:7] if d else None


_OCR_DIGIT = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"})


def parse_amount(v: str) -> float | None:
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.rstrip().endswith(")") or s.lstrip().startswith("-") or s.lstrip().startswith("−")
    s = re.sub(r"(?i)^\s*(SAR|SR|USD)(?=\s|\d|[Oo]\b|[Oo]$)", "", s)
    s = re.sub(r"(?i)\b(SAR|SR|USD)\b", "", s)
    mult = 1.0
    if re.search(r"(?i)\b(mn|million|m)\b\s*$", s):
        mult = 1e6
        s = re.sub(r"(?i)\b(mn|million|m)\b\s*$", "", s)
    if re.fullmatch(r"\s*[Oo0]+\s*", s):  # "SAR O" (OCR)
        return 0.0
    m = re.search(r"\d[\dOo,.]*", s)
    if not m:
        return None
    tok = m.group(0).rstrip(",.").translate(_OCR_DIGIT)
    if not re.search(r"\d", tok):
        return None
    # thousands separators: "1,234,567" / "1.234.567" / "1,234.50"; OCR mixes them ("300,250.000"): when every group
    # after the first has exactly three digits, all separators are thousands separators
    groups = re.split(r"[,.]", tok)
    if len(groups) >= 3 and all(len(g) == 3 for g in groups[1:]) and 1 <= len(groups[0]) <= 3:
        tok = "".join(groups)
    elif tok.count(",") and tok.count("."):
        tok = tok.replace(",", "")
    elif tok.count(",") >= 1 and all(len(p) == 3 for p in tok.split(",")[1:]):
        tok = tok.replace(",", "")
    elif tok.count(".") > 1:
        tok = tok.replace(".", "")
    else:
        tok = tok.replace(",", ".")
    try:
        x = float(tok) * mult
    except ValueError:
        return None
    return -x if neg else x


def parse_pct(v: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v).replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


def parse_int(v: str) -> int | None:
    x = parse_amount(v)
    return int(round(x)) if x is not None else None


def parse_value(v: str, typ: str) -> Any:
    v = str(v).strip().strip("|").strip()
    if typ == "date":
        return parse_date(v)
    if typ == "sar":
        return parse_amount(v)
    if typ == "pct":
        return parse_pct(v)
    if typ == "int":
        return parse_int(v)
    return re.sub(r"\s+", " ", v).strip(" :|") or None


# ------------------------------------------------------------------------------------------------ label lookup
def _split_after_label(line: str, label_n: str) -> str | None:
    """If `line` starts with the label (normalised) followed by ':' or '|', return the text after the separator."""
    count = 0
    i = 0
    n = len(label_n)
    low = line.lower()
    while i < len(line) and count < n:
        ch = low[i]
        if ch.isalnum():
            if ch != label_n[count]:
                return None
            count += 1
        i += 1
    if count < n:
        return None
    rest = line[i:]
    m = re.match(r"[\s.)\]]*(?:\([^)]{0,24}\))?\s*[:|\-–]\s?(.*)$", rest)
    if m:
        return m.group(1)
    if rest[:1] == "" or rest.startswith(" " * 2):
        return rest.strip()
    return None


def find_label(lines: list[str], label: str, start: int = 0) -> tuple[int, str] | None:
    ln = norm(label)
    if not ln:
        return None
    for i in range(start, len(lines)):
        if not norm(lines[i]).startswith(ln):
            # a label wrapped over two lines in a PDF table: "Total standard-rated sales (12 | SAR 473,206,000" + "months):"
            if "|" in lines[i] and i + 1 < len(lines):
                head, _, tail = lines[i].partition("|")
                hn, nx = norm(head), norm(lines[i + 1])
                if hn and len(hn) >= 6 and ln.startswith(hn) and nx and hn + nx == ln and len(lines[i + 1]) < 40:
                    return i, tail.strip()
            continue
        v = _split_after_label(lines[i], ln)
        if v is not None:
            return i, v.strip()
    return None


def _cells(line: str) -> list[str]:
    if "|" in line:
        return [c.strip() for c in line.split("|")]
    if re.search(r"\S {2,}\S", line):
        return [c.strip() for c in re.split(r" {2,}", line.strip())]
    # one-space text (PDF text / OCR): numbers, dates and percents are their own cells, words run together
    toks = re.findall(r"\(?-?[\d][\d,./\-]*\)?%?|[^\s\d][^\s]*", line)
    out: list[str] = []
    for t in toks:
        isnum = bool(re.match(r"\(?-?\d", t))
        if out and not isnum and not re.match(r"\(?-?\d", out[-1]):
            out[-1] = out[-1] + " " + t
        else:
            out.append(t)
    return out


def _sub_types(code: str, sub: str) -> str:
    if sub in ("name", "lender", "product", "status", "remark", "facility", "purpose", "role", "powers", "mode", "nationality", "customer",
               "supplier", "relationship", "terms", "country", "asset", "liability", "description", "project", "employer", "item",
               "beneficiary", "pricing", "tenor", "limit_name", "id_number", "project_id", "pep", "period", "month"):
        return "text"
    if sub in ("pct", "share_pct", "work_done_pct", "cash_margin_pct"):
        return "pct"
    if sub in ("opened", "start", "planned_completion", "filed_on", "date", "maturity"):
        return "date" if sub != "start" else "text"
    if sub in ("shares", "returned_cheques"):
        return "int"
    return "sar"


ALIASES: dict[str, list[str]] = {
    "name": ["name", "shareholder", "owner", "signatory", "guarantor", "partner", "customer", "supplier"],
    "customer": ["customer", "buyer", "client", "debtor"], "supplier": ["supplier", "vendor", "creditor"],
    "pct": ["pct", "percent", "share", "ownership", "holding", "%"], "share_pct": ["share", "sharepct", "%", "percent"],
    "b0_90": ["090", "0to90"], "b91_180": ["91180"], "b181_365": ["181365"], "over_365": ["over365", "365"], "over_180": ["over180", "180"],
    "project_id": ["id", "projectid", "ref", "no"], "planned_completion": ["completion", "plannedcompletion"],
    "work_done_pct": ["done", "workdone", "progress", "complete"], "retention_held": ["retention", "retentionheld"],
    "contract_value": ["contractvalue", "value", "contract"], "credits": ["credit", "credits"], "debits": ["debit", "debits"],
    "closing_balance": ["closing", "closingbalance", "balance"], "avg_balance": ["average", "avgbalance", "averagebalance"],
    "returned_cheques": ["returned", "returnedcheques", "cheques"], "beneficiary": ["beneficiary", "guaranteedparty", "party"],
    "limit": ["limit", "limits"], "item": ["item"], "id_number": ["idnumber", "id", "idcr", "nationalid"],
    "taxable_sales": ["taxablesales", "standardrated", "standardratedsales"], "zero_rated_sales": ["zerorated", "zeroratedsales"],
    "net_vat_due": ["netvat", "netvatdue", "vatdue"], "filed_on": ["filed", "filedon"], "period": ["period", "month"],
    "facility": ["facility", "facilities", "product"], "amount": ["amount"], "lender": ["lender", "bank"],
    "relationship": ["relationship", "relation"], "terms": ["terms"], "country": ["country"], "purchases": ["purchases", "purchase"],
    "sales": ["sales"], "pricing": ["pricing", "price", "profitrate", "rate"], "tenor": ["tenor"], "maturity": ["maturity"],
    "asset": ["asset"], "liability": ["liability"], "description": ["description", "details"], "value": ["value"],
    "existing": ["existing"], "proposed": ["proposed"], "outstanding": ["outstanding"], "cash_margin_pct": ["cashmargin", "margin"],
    "pep": ["pep"], "role": ["role", "capacity", "position"], "powers": ["powers"], "mode": ["mode"], "shares": ["shares"],
    "nationality": ["nationality"],
}


def _header_map(cells: list[str], subs: list[str]) -> list[str | None] | None:
    """Map header cells to sub-field names; None when the row does not look like this table's header."""
    out: list[str | None] = [None] * len(cells)
    used: set[str] = set()
    norms = [norm(c) or ("%" if "%" in c else "") for c in cells]
    for i, cn in enumerate(norms):  # exact names first
        for s in subs:
            if s not in used and cn and cn == norm(s):
                out[i] = s
                used.add(s)
                break
    for i, cn in enumerate(norms):  # then aliases: equal, then prefix
        if out[i] or not cn:
            continue
        for strict in (True, False):
            hit = None
            for s in subs:
                if s in used:
                    continue
                for a in ALIASES.get(s, [norm(s)]):
                    if cn == a or (not strict and len(a) >= 3 and (cn.startswith(a) or (len(cn) >= 3 and a.startswith(cn)))):
                        hit = s
                        break
                if hit:
                    break
            if hit:
                out[i] = hit
                used.add(hit)
                break
    hits = len(used)
    need = len(subs) if len(subs) <= 2 else max(2, -(-len(subs) * 5 // 10))
    if hits >= need and hits >= min(2, len(cells)):
        return out
    return None


def read_list(lines: list[str], at: int, code: str, subs: list[str]) -> list[dict[str, Any]]:
    """The table printed under the label at line `at`: the first header-like row within 3 lines, then its rows."""
    hdr = None
    i = at + 1
    while i < min(len(lines), at + 4):
        hm = _header_map(_cells(lines[i]), subs)
        if hm:
            hdr = hm
            break
        i += 1
    if hdr is None:
        return []
    return _rows_after(lines, i, code, hdr)


def _shape(cell: str) -> str:
    return re.sub(r"[A-Za-z]+", "a", re.sub(r"\d+", "9", cell.strip()))


_NUMFRAG = re.compile(r"^[\d,./%\-()]+$")


def _join(a: str, b: str) -> str:
    a, b = a.strip(), b.strip()
    if not a:
        return b
    if not b:
        return a
    if _NUMFRAG.match(b) and re.search(r"[\d,./\-]$", a):  # "486,000,0" + "00", "01/03/2" + "025", "41" + "%"
        return a + b
    return a + " " + b


_FULLNUM = re.compile(r"\d{1,3}(?:,\d{3})+|\d{1,2}/\d{1,2}/\d{4}|\b\d{4}-\d{2}\b|\b\d+(?:\.\d+)?%")
_FOOTER = re.compile(r"(?i)fictional demo document|\bpage \d+\b")


def _rows_spans(lines: list[str], spans: list[Any], i: int, code: str, hdr: list[str | None]) -> list[dict[str, Any]]:
    """PDF layout tables: cells placed by their character columns under the header (empty cells stay empty, wrapped
    cells continue the row above, a repeated header after a page footer continues the table)."""
    hs = spans[i]
    m = len(hdr)
    numeric = any(h and _sub_types(code, h) != "text" for h in hdr)
    hnorm = norm(lines[i])

    starts = [a for a, _, _ in hs]

    def col(a: int, b: int, t: str) -> int:
        # text is left-aligned under its header; numbers are right-aligned, so their right edge decides
        x = (b - 1) if re.fullmatch(r"[\d,.%()\-/ ]+", t.strip()) else (a + 2)
        k = max([k for k in range(m) if starts[k] <= x] or [0])
        return k
    raw: list[list[str]] = []
    j = i + 1
    while j < len(lines):
        line, sp = lines[j], spans[j] or []
        if _FOOTER.search(line):  # page break: continue after the repeated header, if the table goes on
            k = next((k for k in range(j + 1, min(len(lines), j + 12)) if norm(lines[k]) == hnorm), None)
            if k is None:
                break
            j = k + 1
            continue
        if re.match(r"(?i)^\s*(total|totals)\b", line):
            break
        if len(sp) <= 2 and sp and sp[0][2].rstrip().endswith(":"):
            break
        if len(sp) == 1 and len(sp[0][2]) > 60:
            break  # prose after the table
        cells: dict[int, str] = {}
        if raw and len(sp) == 1 and sp[0][0] <= starts[0] + 2 and j + 1 < len(lines):  # a title line before the next table ("Guarantees given")
            nxt = spans[j + 1] or []
            if len(nxt) >= 3 and not re.search(r"\d", lines[j + 1]):
                break
        for a, b, t in sp:
            c = col(a, b, t)
            cells[c] = _join(cells.get(c, ""), t)
        lead = any(abs(a - starts[0]) <= 3 for a, _, _ in sp)
        full = 0 in cells and lead and (not numeric or len(cells) >= max(2, m // 2 + 1) or any(_FULLNUM.search(t) for t in cells.values()))
        if not numeric and not lead and len(sp) == 1 and sp[0][0] > starts[-1] + 10:
            break
        if not raw and not full:
            if not re.search(r"\d", line) and j - i <= 2:
                j += 1  # wrapped header words
                continue
            if not cells:
                break
            full = True
        if full:
            row = [""] * m
            for c, t in cells.items():
                row[c] = t
            raw.append(row)
        else:
            if len(sp) > 1 and all(_FULLNUM.search(t) is None for t in cells.values()) or len(sp) == 1:
                for c, t in cells.items():
                    raw[-1][c] = _join(raw[-1][c], t)
            else:
                break
        j += 1
    rows: list[dict[str, Any]] = []
    for cells_ in raw:
        rec: dict[str, Any] = {}
        for h, c in zip(hdr, cells_):
            if h:
                t = _sub_types(code, h)
                rec[h] = parse_value(c, t) if t != "text" else (c.strip() or None)
        vals = [v for v in rec.values() if v not in (None, "")]
        if vals and not (len(vals) == 1 and re.fullmatch(r"(?i)none|nil|n/?a|-+|—", str(vals[0]).strip())):
            rows.append(rec)
    return rows


def _rows_after(lines: list[str], i: int, code: str, hdr: list[str | None], spans: list[Any] | None = None) -> list[dict[str, Any]]:
    """Rows of the table whose header is lines[i]. PDF tables wrap long cells onto extra lines: a line with fewer cells
    than the header continues the row above (numbers glued, text joined with a space)."""
    if spans and i < len(spans) and spans[i] and len(spans[i]) == len(hdr):
        return _rows_spans(lines, spans, i, code, hdr)
    piped = "|" in lines[i]
    m = len(hdr)
    raw: list[list[str]] = []
    first_shape = ""
    j = i + 1
    skipped_head = 0
    while j < len(lines):
        line = lines[j]
        if piped and "|" not in line:
            if not raw and skipped_head < 2 and len(line) < 40 and not re.search(r"\d", line):  # wrapped header words ("cheques")
                skipped_head += 1
                j += 1
                continue
            break
        cells = _cells(line)
        if re.match(r"(?i)^\s*(total|totals)\b", line):
            break
        if ":" in line and "|" not in line and len(cells) <= 2:
            break
        if piped and raw and not re.search(r"\d", line) and any(h and _sub_types(code, h) != "text" for h in hdr):
            break  # the next table's header (a numeric table's rows always carry a number)
        starts = len(cells) >= m - 1 or (first_shape and _shape(cells[0]) == first_shape and len(first_shape) <= 6)
        if not raw or starts:
            if not raw:
                first_shape = _shape(cells[0])
            if len(cells) < max(2, m - 3) and not raw:
                break
            raw.append((cells + [""] * m)[:m] if len(cells) <= m else cells[:m])
        else:  # continuation of the row above
            row = raw[-1]
            if len(cells) >= m - 3:  # right-aligned (the key column is empty)
                for k, c in enumerate(cells):
                    col = m - len(cells) + k
                    row[col] = _join(row[col], c)
            else:  # only text columns continue: align to the text columns (not the key), from the right
                textcols = [k for k in range(1, m) if row[k] and not _NUMFRAG.match(row[k].replace(" ", ""))]
                cols = textcols[-len(cells):] if len(textcols) >= len(cells) else list(range(m - len(cells), m))
                for c, col in zip(cells, cols):
                    row[col] = _join(row[col], c)
        j += 1
    rows: list[dict[str, Any]] = []
    for cells in raw:
        rec: dict[str, Any] = {}
        for h, c in zip(hdr, cells):
            if h:
                t = _sub_types(code, h)
                rec[h] = parse_value(c, t) if t != "text" else (c.strip() or None)
        vals = [v for v in rec.values() if v not in (None, "")]
        if vals and not (len(vals) == 1 and re.fullmatch(r"(?i)none|nil|n/?a|-+|—", str(vals[0]).strip())):
            rows.append(rec)
    return rows


# ------------------------------------------------------------------------------------------------ classify
def classify(name: str, lines: list[str]) -> dict[str, Any]:
    top = " ".join(lines[:18]).upper()
    top_n = norm(top)
    all_n = norm(" ".join(lines))
    starts = {norm(x)[:40] for x in lines}
    fname = norm(name)
    scores: list[tuple[float, str, list[str]]] = []
    for d in DOC_TYPES:
        if d.code == "reference_proposal" and "creditdivisioncomments" not in all_n:
            continue
        why: list[str] = []
        s = 0.0
        for k in d.keywords:
            kn = norm(k)
            if kn and kn in top_n:
                s += 3.0 if k.isupper() else 1.0
                why.append(f"title \"{k}\"")
            elif kn and kn in all_n:
                s += 0.5
        labels = [lab for (_, lab, _) in d.fields if norm(lab) not in ("customername", "crnumber", "name", "date")]
        hit = sum(1 for lab in labels if any(st.startswith(norm(lab)) for st in starts))
        if labels:
            s += 6.0 * hit / len(labels)
            if hit:
                why.append(f"{hit} of {len(labels)} labels")
        if norm(d.code) in fname:
            s += 2.5
            why.append("file name")
        scores.append((s, d.code, why))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1] if len(scores) > 1 else (0.0, "", [])
    # disambiguation the keywords alone cannot do
    code = best[1]
    if code in ("simah_company", "simah_consumer"):
        code = "simah_consumer" if ("CONSUMER" in top or "worststatus" in all_n) else "simah_company"
    if code in ("bank_statement", "other_bank_statement") and ("STATEMENT OF FACILITIES" in top or "LIABILITY STATEMENT" in top):
        code = "other_bank_statement"
    if code == "audited_fs" and ("MANAGEMENT ACCOUNTS" in top or "UNAUDITED" in top):
        code = "inhouse_fs"
    conf = 0.0 if best[0] <= 0 else min(1.0, (best[0] - second[0]) / max(best[0], 1e-9) + 0.35)
    if best[0] < 2.0:
        return {"doc_type": "unknown", "label": "Not recognised", "confidence": round(conf * 0.5, 2), "why": best[2], "runner_up": second[1]}
    return {"doc_type": code, "label": BY_CODE[code].label, "confidence": round(conf, 2), "why": best[2], "runner_up": second[1]}


# ------------------------------------------------------------------------------------------------ extract
def extract(code: str, lines: list[str], spans: list[Any] | None = None) -> dict[str, dict[str, Any]]:
    """{field: {value, label, type, line, raw}} for every printed field found."""
    d: DocType | None = BY_CODE.get(code)
    if d is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    taken: set[int] = set()
    if code == "business_request":
        business_request_extra(lines, out)
    for fname, label, typ in d.fields:
        if fname in out:
            continue
        if typ.startswith("list:"):
            subs = typ.split(":", 1)[1].split(",")
            hit = find_label(lines, label)
            rows: list[dict[str, Any]] = []
            at = -1
            if hit is not None:
                for k in range(hit[0] + 1, min(len(lines), hit[0] + 4)):
                    if _header_map(_cells(lines[k]), subs):
                        at = k
                        break
            if at < 0:  # the table is printed without its label (e.g. under an article heading): find its header row
                best = (0, -1)
                for k, ln in enumerate(lines):
                    if k in taken or ("|" not in ln and "  " not in ln) or re.search(r"\d{1,3}(,\d{3})+|\d{5,}", ln):
                        continue
                    hm = _header_map(_cells(ln), subs)
                    if hm:
                        n = sum(1 for h in hm if h)
                        if n > best[0]:
                            best = (n, k)
                at = best[1]
            if at >= 0:
                hm = _header_map(_cells(lines[at]), subs)
                rows = _rows_after(lines, at, code, hm, spans) if hm else []
            if rows:
                taken.add(at)
                out[fname] = {"value": rows, "label": label, "type": "list", "line": at + 1, "raw": f"{len(rows)} rows"}
            continue
        hit = find_label(lines, label)
        if hit is None and fname in ("customer_name",):
            hit = find_label(lines, "Customer") or find_label(lines, "Company name") or find_label(lines, "Name of company")
        if hit is None:
            continue
        i, raw = hit
        if typ.startswith("list:"):
            subs = typ.split(":", 1)[1].split(",")
            rows = read_list(lines, i, code, subs)
            if rows:
                out[fname] = {"value": rows, "label": label, "type": "list", "line": i + 1, "raw": f"{len(rows)} rows"}
            continue
        if not raw.strip() and i + 1 < len(lines):  # value on the next line (photo of a form)
            raw = lines[i + 1]
        if spans is not None and typ == "text" and len(raw) >= 60 and i + 1 < len(lines):  # a long value wrapped onto the next line (PDF)
            nx = lines[i + 1]
            if "|" not in nx and ":" not in nx and len(nx) < 90 and not nx.isupper():
                raw = raw.rstrip() + " " + nx.strip()
        val = parse_value(raw, typ)
        if val is None or val == "":
            continue
        out[fname] = {"value": val, "label": label, "type": typ, "line": i + 1, "raw": raw[:120]}
    return out


def _section(lines: list[str], head: str) -> tuple[int, list[str]]:
    """The lines under a numbered bank-form heading ("3. Security and support") up to the next numbered heading."""
    hn = norm(head)
    for i, ln in enumerate(lines):
        if re.match(r"^\s*\d{1,2}\.\s*[A-Z]", ln) and norm(re.sub(r"^\s*\d{1,2}\.\s*", "", ln)).startswith(hn):
            out = []
            for x in lines[i + 1:]:
                if re.match(r"^\s*\d{1,2}\.\s*[A-Z][a-z]", x) and "|" not in x and len(x) < 60:
                    break
                out.append(x)
            return i, out
    return -1, []


def business_request_extra(lines: list[str], out: dict[str, dict[str, Any]]) -> None:
    """The bank-form business request prints its header as a block and its body as numbered sections."""
    def put(field: str, value: Any, label: str, typ: str, line: int, raw: str = "") -> None:
        if value not in (None, "", []) and field not in out:
            out[field] = {"value": value, "label": label, "type": typ, "line": line, "raw": raw or (f"{len(value)} rows" if isinstance(value, list) else str(value))[:120]}
    for label, field in (("CIF / base no.", "cif"), ("CIF", "cif"), ("Customer", "customer_name")):
        h = find_label(lines, label)
        if h:
            put(field, parse_value(h[1], "text"), label, "text", h[0] + 1)
    h = find_label(lines, "AO / RO")
    if h:
        put("rm", h[1].strip(" |").split("/")[0].strip(" |"), "AO / RO", "text", h[0] + 1)
    for i, ln in enumerate(lines[:12]):
        m = re.search(r"\bRM\s+([A-Z][A-Za-z' \-]+?)\s*$", ln)
        if m:
            put("rm", m.group(1).strip(), "RM", "text", i + 1)
        m = re.search(r"\bDate\s+(\d{1,2}/\d{1,2}/\d{4})", ln)
        if m:
            put("request_date", parse_date(m.group(1)), "Date", "date", i + 1)
    i, sec = _section(lines, "Action requested")
    if sec:
        put("action_requested", " ".join(x.strip() for x in sec if x.strip() and "|" not in x)[:2000], "Action requested", "text", i + 2)
    i, sec = _section(lines, "Facilities")
    if sec:
        hdr_i = next((k for k, x in enumerate(sec) if "|" in x and re.search(r"(?i)existing", x) and re.search(r"(?i)proposed", x)), None)
        if hdr_i is not None:
            cells = [norm(c) for c in sec[hdr_i].split("|")]
            col = {name: next((k for k, c in enumerate(cells) if c.startswith(name)), None) for name in ("existing", "outstanding", "proposed", "cashmargin", "particulars")}
            rows = []
            for x in sec[hdr_i + 1:]:
                if "|" not in x:
                    break
                cs = [c.strip() for c in x.split("|")]

                def num(k: str) -> float | None:
                    j = col.get(k)
                    v = parse_amount(cs[j]) if j is not None and j < len(cs) else None
                    return v * 1e6 if v is not None else None   # the table is in SAR million
                rows.append({"limit": cs[0], "existing": num("existing"), "outstanding": num("outstanding"), "proposed": num("proposed"),
                             "cash_margin_pct": parse_pct(cs[col["cashmargin"]]) if col.get("cashmargin") is not None and col["cashmargin"] < len(cs) and cs[col["cashmargin"]] else None,
                             "pricing": cs[col["particulars"]] if col.get("particulars") is not None and col["particulars"] < len(cs) else None, "tenor": None})
            tot = next((r for r in rows if re.match(r"(?i)total", r["limit"])), None)
            if tot:
                put("total_existing", tot["existing"], "Total facilities (existing)", "sar", i + hdr_i + 3)
                put("total_proposed", tot["proposed"], "Total facilities (proposed)", "sar", i + hdr_i + 3)
            put("facilities", [r for r in rows if r is not tot], "Facilities", "list", i + hdr_i + 2)
    for head, field in (("Security and support", "security"), ("Terms and conditions", "conditions")):
        i, sec = _section(lines, head)
        items = [{"item": re.sub(r"^\s*(\d+[.)]|[-•·])\s*", "", x).strip()} for x in sec if x.strip() and "|" not in x and len(x.strip()) > 12]
        put(field, items, head, "list", i + 2)


def title_of(lines: list[str]) -> str:
    for ln in lines[:8]:
        t = ln.strip()
        if len(t) > 6 and not re.search(r"[؀-ۿ]", t) and ":" not in t:
            return t[:120]
    return ""
