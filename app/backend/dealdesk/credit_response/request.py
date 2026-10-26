"""Read an uploaded business request (Word, PDF with text, scanned PDF or photo) into the deal the RM asks for.

    r = parse(text, name, tables=None, method="word")
    r["header"]      {customer, cif, group_no, group, branch, rm, date, rating_existing, rating_proposed, industry, request_kind, ...}
    r["action"]      {text, purpose, previous_ref, previous_date, from_total, to_total}
    r["facilities"]  [{seq, limit_name, product_code, level, parent, existing_mn, outstanding_mn, proposed_mn, cash_margin_pct,
                       commission_pct_pa, benchmark, spread_pct, floor_pct, tenor_text, particulars, total, source}]
    r["totals"]      {existing, outstanding, proposed}
    r["security"]    [{seq, group, kind, provider, amount_mn, net_worth_mn, net_worth_date, perfection_status, deadline, text}]
    r["terms"]       [{seq, group, category, text, existing_status}]
    r["sections"]    {key: [lines]}   (action, facilities, security, terms, group_exposure, background, relationship, projects,
                                       financials, justification, ...) - the text as read, for the proposal check and the trace
    r["fields"]      {name, sector, internal_rating, amount, tenor_years, margin_bps, commission_bps, facility_type, rm, purpose, group_name}
    r["read_gaps"]   what could not be read (a plain list)

Deterministic: the same text gives the same request. The same parser reads Word (pipe rows), PDF text (cells on one line)
and OCR text (no table structure, numbers separated by spaces), so a photo of the request reads like its Word.
"""
from __future__ import annotations

import re
from typing import Any

# ------------------------------------------------------------------ sections

#: normalised heading -> section key (anatomy keys where they exist; justification is the RM's own)
HEADINGS: list[tuple[str, str]] = [
    ("action requested", "action"), ("actions requested", "action"), ("request", "action"), ("the ask", "action"),
    ("facilities table", "facilities"), ("facilities", "facilities"), ("facility table", "facilities"), ("proposed facilities", "facilities"),
    ("security and support", "security"), ("security", "security"), ("securities", "security"),
    ("terms and conditions", "terms"), ("terms & conditions", "terms"), ("conditions", "terms"),
    ("group exposure and references", "group_exposure"), ("group exposure", "group_exposure"),
    ("background and ownership", "background"), ("background", "background"), ("company background", "background"),
    ("relationship with the bank", "relationship"), ("relationship with bank", "relationship"), ("relationship", "relationship"),
    ("status of financed projects", "projects"), ("projects", "projects"), ("project status", "projects"), ("project details", "new_project"),
    ("new project details", "new_project"), ("new project details and cash flow", "new_project"),
    ("financials", "financials"), ("financial highlights", "financials"), ("financial summary", "financials"), ("key financials", "financials"),
    ("rm's justification", "justification"), ("rm justification", "justification"), ("justification", "justification"),
    ("business justification", "justification"), ("business rationale", "justification"), ("rm's recommendation", "justification"),
    ("recommendation of business", "justification"), ("rationale", "justification"),
    ("header block", "header"), ("customer details", "header"), ("customer information", "header"),
]
HEAD_NUM = re.compile(r"^\s*(?:section\s+)?(\d{1,2})\s*[.):]?\s*([A-Za-z].{2,80})$", re.I)
BULLET = re.compile(r"^\s*(?:[•·▪●◦\-*–\x7f\uf0b7]\s*(?:\d{1,2}[.)](?!\d))?\s*|\(?[a-z]\)\s+|\(?\d{1,2}[.)](?!\d)\s*)")


def _norm(s: str) -> str:
    s = re.sub(r"^\s*(?:section\s+)?\d{1,2}\s*[.):]?\s*", "", str(s).lower())
    s = s.replace("’", "'")
    return re.sub(r"[^a-z&' ]+", " ", s).strip()


def heading_key(line: str) -> str | None:
    """The section a line opens, or None. Short lines only (a heading, not a sentence)."""
    t = line.strip().strip("|").strip()
    if not t or len(t) > 70 or t.endswith((".", ",", ";")) or "|" in t:
        return None
    n = _norm(t)
    if not n or len(n.split()) > 7 or len(n) > 48:
        return None
    nc = n.replace(" ", "")
    for h, k in HEADINGS:
        if n == h or nc == h.replace(" ", ""):
            return k
    if HEAD_NUM.match(t):  # "3. Facilities (SAR million)" - numbered: a looser match is safe (OCR drops spaces)
        for h, k in HEADINGS:
            if len(h) > 5 and (n.startswith(h) or nc.startswith(h.replace(" ", ""))):
                return k
    return None


def split_sections(text: str) -> tuple[dict[str, list[str]], list[str]]:
    secs: dict[str, list[str]] = {}
    pre: list[str] = []
    cur: list[str] = pre
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        k = heading_key(ln)
        if k is not None:
            cur = secs.setdefault(k, [])
            continue
        cur.append(ln)
    return secs, pre


# ------------------------------------------------------------------ numbers and money

_AMT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
MONEY = re.compile(rf"(?:SAR|SR|ر\.س)\s*({_AMT})\s*(bn|billion|b|mn|m|million|k|thousand)?\b", re.I)
MONEY_AFTER = re.compile(rf"({_AMT})\s*(bn|billion|mn|m|million)\b", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DATE = re.compile(r"\b(\d{1,2})[\s-]+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,-]+(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b", re.I)


def to_mn(v: str, unit: str | None) -> float:
    x = float(v.replace(",", ""))
    u = (unit or "").lower()
    if u in ("bn", "billion", "b"):
        return round(x * 1000.0, 4)
    if u in ("k", "thousand"):
        return round(x / 1000.0, 6)
    if u in ("m", "mn", "million"):
        return x
    return round(x / 1e6, 6) if x >= 100_000 else x


def money(text: str) -> list[float]:
    out = [to_mn(m.group(1), m.group(2)) for m in MONEY.finditer(text or "")]
    if not out:
        out = [to_mn(m.group(1), m.group(2)) for m in MONEY_AFTER.finditer(text or "")]
    return out


def dates(text: str) -> list[str]:
    out = []
    for m in DATE.finditer(text or ""):
        if m.group(1):
            out.append(f"{int(m.group(3)):04d}-{MONTHS[m.group(2)[:3].lower()]:02d}-{int(m.group(1)):02d}")
        elif m.group(4):
            out.append(f"{m.group(4)}-{m.group(5)}-{m.group(6)}")
        else:
            out.append(f"{int(m.group(9)):04d}-{int(m.group(8)):02d}-{int(m.group(7)):02d}")
    return out


# ------------------------------------------------------------------ header block

HEADER_LABELS: list[tuple[str, tuple[str, ...]]] = [
    ("customer", ("customer name", "customer", "borrower name", "borrower", "obligor", "applicant", "company name", "name of the customer")),
    ("cif", ("cif / base no", "cif/base no", "cif no", "cif", "base no", "customer id")),
    ("group_no", ("group no", "group id", "group number")),
    ("group", ("group name", "group")),
    ("branch", ("branch / unit", "branch/unit", "unit / branch", "unit/branch", "branch", "unit")),
    ("rm", ("rm / unit", "relationship manager", "rm name", "rm", "ao / ro")),
    ("date", ("date of request", "request date", "date")),
    ("account_opened", ("date account opened", "account opened", "customer since", "relationship since")),
    ("rating", ("rating existing / proposed", "existing / proposed rating", "internal rating", "risk rating", "rating", "orr")),
    ("industry", ("industry code", "industry", "sector", "activity")),
    ("request_kind", ("request type", "type of request", "request", "nature of request")),
    ("cr_no", ("cr no", "cr number", "commercial registration")),
    ("purpose_code", ("purpose code",)),
    ("review_date", ("review date", "next review")),
    ("connected", ("related / connected party", "connected party", "related party")),
    ("collateral_code", ("collateral code",)),
]


def _label_key(label: str) -> str | None:
    n = re.sub(r"[^a-z/]+", "", label.lower())
    for key, labels in HEADER_LABELS:
        for lb in labels:
            lc = lb.replace(" ", "")
            if n == lc or (len(lc) > 3 and n.startswith(lc) and len(n) <= len(lc) + 10):
                return key
    return None


def header(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        if "|" in ln:
            cells = [c.strip() for c in ln.split("|")]
            for j in range(0, len(cells) - 1, 2):
                k = _label_key(cells[j]) if cells[j] else None
                if k and cells[j + 1] and k not in out:
                    out[k] = cells[j + 1]
            continue
        for m in re.finditer(r"([A-Za-z][A-Za-z /.']{1,34}?)\s*:\s*([^:]+?)(?=\s{2,}[A-Za-z][A-Za-z /.']{1,34}?\s*:|$)", ln):
            k = _label_key(m.group(1))
            if k and k not in out and m.group(2).strip():
                out[k] = m.group(2).strip()
    if "rating" in out:
        parts = [p.strip() for p in re.split(r"\s*/\s*|\s*(?:→|->|to)\s*", out["rating"]) if p.strip()]
        out["rating_existing"] = parts[0] if parts else out["rating"]
        out["rating_proposed"] = parts[-1] if parts else out["rating"]
    if "request_kind" in out:  # ticked boxes: "[x] Renewal [x] Additional"
        ticked = re.findall(r"\[\s*[xX✓✔]\s*\]\s*([A-Za-z]+)", out["request_kind"])
        if ticked:
            out["request_kind"] = " and ".join(t.lower() for t in ticked)
        elif "[ ]" in out["request_kind"]:
            out["request_kind"] = ""
    return out


# ------------------------------------------------------------------ facilities

PRODUCT = re.compile(r"^(?:BB|APG|PB|RB|LC[_ ]?SIGHT|LC[_ ]?USANCE|LCM|LC|DMCCM[_ ]?PC|DMCCM[_ ]?SUP|DMCCM|OD|TL|RCF|TR|LG[_ ]?CASH|LG|VHM|STL|WCF|MUR|TWR|IJR)$", re.I)
NUM_TOKEN = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?$|^\(?-?\d+(?:\.\d+)?\)?$")
DASH_TOKEN = re.compile(r"^[–—\-]$|^nil$|^n/?a$", re.I)
SPREAD = re.compile(r"((?:\d+M\s*)?(?:SAIBOR|SOFR|EIBOR|SIBOR|LIBOR|benchmark|COF))\s*\+\s*(\d+(?:\.\d+)?)\s*(%|bps|bp)?", re.I)
FLOOR = re.compile(r"floor\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%", re.I)
COMM = re.compile(r"(?:comm(?:ission)?\.?\s*(?:of\s*)?)?(\d+(?:\.\d+)?)\s*%\s*(p\.?\s?a\.?|p\.?\s?q\.?|per annum|per quarter|flat)", re.I)
TENOR = re.compile(r"(?:up to\s*)?(\d+(?:\.\d+)?)\s*(months?|years?|days?)", re.I)
COL_ALIASES = {"existing": ("existing", "current limit", "present limit", "existing limit"),
               "outstanding": ("outstand", "o/s", "utilised", "utilized", "balance"),
               "proposed": ("proposed", "requested", "new limit", "recommended"),
               "cash_margin": ("cash margin", "margin %", "cm"),
               "commission": ("commissio",), "pricing": ("benchmark", "pricing", "profit rate", "rate"),
               "tenor": ("tenor", "validity"), "repayment": ("repayment",), "particulars": ("particulars", "remarks", "notes"),
               "product": ("product", "type"), "name": ("limit", "facility", "facilities", "limit / sub-limit", "description")}


def _num(tok: str) -> float | None:
    t = re.sub(r"(?<=\d)[:;](?=\d)", ".", tok.strip())
    if DASH_TOKEN.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    try:
        v = float(t.strip("()").replace(",", ""))
    except ValueError:
        return None
    v = to_mn(str(abs(v)), None)
    return -v if neg else v


def _pricing(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = SPREAD.search(text or "")
    if m:
        v = float(m.group(2))
        bps = (m.group(3) or "").lower().startswith("bp") or v >= 20
        out["benchmark"] = " ".join(m.group(1).split()).upper().replace("BENCHMARK", "benchmark")
        out["spread_pct"] = round(v / 100.0, 4) if bps else v
    m = FLOOR.search(text or "")
    if m:
        out["floor_pct"] = float(m.group(1))
    m = COMM.search(text or "")
    if m:
        v = float(m.group(1))
        out["commission_pct_pa"] = round(v * 4, 4) if re.match(r"p\.?\s?q|per quarter", m.group(2), re.I) else v
    return out


def _clean_name(name: str) -> tuple[str, str]:
    toks = name.strip(" |:-–").split()
    prod = ""
    while toks and (PRODUCT.match(toks[-1]) or DASH_TOKEN.match(toks[-1])):
        t = toks.pop()
        if PRODUCT.match(t) and not prod:
            prod = t.upper().replace(" ", "_")
    if len(toks) >= 2 and PRODUCT.match(toks[-1].replace("_", "")):
        prod = prod or toks.pop().upper()
    return " ".join(toks).strip(" |:-–"), prod


def _line_row(ln: str) -> dict[str, Any] | None:
    """One facility line read from text (PDF cells on one line, or OCR): name [product] existing outstanding proposed rest."""
    toks = re.sub(r"(?<=\d)[:;](?=\d)", ".", ln.replace("|", " ")).split()
    run_start = None
    for i in range(len(toks)):
        window = toks[i:i + 3]
        if len(window) < 3:
            break
        if all(NUM_TOKEN.match(t) or DASH_TOKEN.match(t) for t in window) and sum(1 for t in window if NUM_TOKEN.match(t)) >= 2:
            # a number inside the name ("Project limit 1:", "Phase 2") is followed by words, not by two more numbers
            run_start = i
            break
    if run_start is None or run_start == 0:
        return None
    name, prod = _clean_name(" ".join(toks[:run_start]))
    if not name or not re.search(r"[A-Za-z]", name):
        return None
    vals = [_num(t) for t in toks[run_start:run_start + 3]]
    rest = " ".join(toks[run_start + 3:])
    row = {"limit_name": name, "product_code": prod, "existing_mn": vals[0], "outstanding_mn": vals[1], "proposed_mn": vals[2],
           "particulars": rest, "source": "text line"}
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*%\s+(?!p\.?a)", rest)
    if m:
        row["cash_margin_pct"] = float(m.group(1))
    row.update(_pricing(rest))
    t = TENOR.search(rest)
    if t:
        row["tenor_text"] = rest[t.start():].split("  ")[0][:80]
    return row


def _pipe_rows(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cols: dict[str, int] | None = None
    for ln in lines:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        low = [c.lower() for c in cells]
        if cols is None:
            if any("existing" in c for c in low) and any(("proposed" in c or "requested" in c) for c in low):
                cols = {}
                for key, al in COL_ALIASES.items():
                    for j, c in enumerate(low):
                        if j not in cols.values() and any(c.startswith(a) or a in c for a in al):
                            cols[key] = j
                            break
                cols.setdefault("name", 0)
                if len({cols.get("existing"), cols.get("outstanding"), cols.get("proposed")}) < 3:
                    return [r for r in (_line_row(x) for x in lines if "|" in x) if r]
            continue
        name_raw = cells[cols["name"]] if cols["name"] < len(cells) else ""
        if not name_raw or name_raw.lower().startswith(("limit", "facility")) and "existing" in " ".join(low):
            continue

        def cell(k: str) -> str:
            j = cols.get(k)
            return cells[j] if j is not None and j < len(cells) else ""
        nums = {k: _num(cell(k)) if cell(k) else None for k in ("existing", "outstanding", "proposed")}
        if all(v is None for v in nums.values()) or any(cell(k) and _num(cell(k)) is None and not DASH_TOKEN.match(cell(k)) for k in nums):
            alt = _line_row(ln)  # cells out of line with the header (an empty cell, a wrapped one): read the numbers in order
            if alt:
                alt["source"] = "table (numbers in order)"
                out.append(alt)
            continue
        name, prod = _clean_name(name_raw)
        prod = prod or (cell("product").upper().replace(" ", "_") if PRODUCT.match(cell("product").replace("_", " ").strip() or "x") else "")
        # the cells after the three amounts, whatever the header says (a PDF drops empty cells): cash margin, pricing, tenor, particulars
        jp = cols.get("proposed", 0)
        tail = [c for c in cells[jp + 1:] if c and c not in ("–", "-")]
        rest = " ".join(tail)
        row = {"limit_name": name, "product_code": prod, "existing_mn": nums["existing"], "outstanding_mn": nums["outstanding"],
               "proposed_mn": nums["proposed"], "particulars": rest[:300], "tenor_text": "", "repayment_text": "", "source": "table"}
        cm = next((c for c in tail if re.fullmatch(r"\d+(?:\.\d+)?\s*%", c)), None)
        if cm:
            row["cash_margin_pct"] = float(cm.rstrip("% "))
        t = TENOR.search(rest)
        if t:
            row["tenor_text"] = rest[t.start():][:80]
        row.update(_pricing(rest))
        out.append(row)
    return out


def facilities(lines: list[str]) -> list[dict[str, Any]]:
    rows = _pipe_rows(lines)
    if not rows:
        rows = [r for r in (_line_row(ln) for ln in lines) if r]
    # drop a repeated total row, keep the first; number them; find limits and their sub-limits
    out, seen_total = [], False
    for r in rows:
        r["total"] = bool(re.match(r"^(grand\s+)?total", r["limit_name"], re.I))
        if r["total"]:
            if seen_total:
                continue
            seen_total = True
        out.append(r)
    for i, r in enumerate(out):
        r["seq"] = i + 1
        r["level"] = 0 if r["total"] else 1
        r["parent"] = None
    i = 0
    while i < len(out):
        r = out[i]
        p = r.get("proposed_mn") or 0.0
        e = r.get("existing_mn") or 0.0
        if r["total"] or not re.search(r"limit|line|umbrella|facilit", r["limit_name"], re.I) or (p <= 0 and e <= 0):
            i += 1
            continue
        s_p = s_e = 0.0
        j = i + 1
        while j < len(out) and not out[j]["total"]:
            s_p += out[j].get("proposed_mn") or 0.0
            s_e += out[j].get("existing_mn") or 0.0
            if abs(s_p - p) < 0.6 and abs(s_e - e) < 0.6:
                break
            if s_p > p + 0.6:
                j = -1
                break
            j += 1
        if j > i and j < len(out) and abs(s_p - p) < 0.6:
            for k in range(i + 1, j + 1):
                out[k]["level"], out[k]["parent"] = 2, r["seq"]
            i = j + 1
        else:
            i += 1
    return out


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    t = next((r for r in rows if r["total"]), None)
    top = [r for r in rows if r["level"] == 1]
    calc = {k: round(sum(r.get(f"{k}_mn") or 0.0 for r in top), 4) for k in ("existing", "outstanding", "proposed")}
    if t:
        stated = {k: t.get(f"{k}_mn") for k in ("existing", "outstanding", "proposed")}
        return {**{k: (stated[k] if stated[k] is not None else calc[k]) for k in calc}, "stated": True, "calculated": calc,
                "adds_up": all(stated[k] is None or abs(stated[k] - calc[k]) < 0.6 for k in calc)}
    return {**calc, "stated": False, "calculated": calc, "adds_up": True}


# ------------------------------------------------------------------ security and terms

SEC_KINDS: list[tuple[str, str]] = [
    (r"personal\s*guarantee|\bPG\b", "personal_guarantee"), (r"corporate\s*guarantee|\bCG\b", "corporate_guarantee"),
    (r"security\s*cheque|undated\s*cheque|\bcheque", "security_cheque"), (r"promissory|\bPN\b|sanad", "promissory_note"),
    (r"assignment\s*of\s*(?:the\s*)?[\w\s-]{0,40}?proceeds|project\s*proceeds|contract\s*proceeds", "assignment_project_proceeds"),
    (r"assignment\s*of\s*(?:the\s*)?receivables|receivables", "assignment_receivables"),
    (r"assignment\s*of\s*(?:the\s*)?insurance|insurance", "assignment_insurance"), (r"mortgage|title\s*deed", "mortgage"),
    (r"hypothecation", "hypothecation"), (r"subordination", "subordination"), (r"cash\s*margin|cash\s*collateral|lien\s*on\s*deposit", "cash_margin"),
    (r"pledge|shares", "pledge"), (r"\bNOC\b|no\s+objection", "noc"), (r"undertaking", "undertaking")]


def _kind(text: str) -> str:
    for pat, k in SEC_KINDS:
        if re.search(pat, text, re.I):
            return k
    return "other"


def _provider(text: str) -> str:
    m = re.search(r"(?:guarantee|cheque|subordination|assignment[^,;]*?|note|pledge|mortgage)\s*(?:of|from|by|issued by|signed by)\s*"
                  r"(?:Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Eng\.?\s+|Sheikh\s+)?([A-Z][A-Za-z.&'\- ]{2,60}?)(?=\s+(?:for|covering|of SAR|SAR|to|in favour|\(|,|;|with|net)|[,;(.]|$)", text)
    return m.group(1).strip() if m else ""


def _unpipe(ln: str) -> str:
    return re.sub(r"\s*\|\s*", " ", ln).strip()


def security(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    group = "All limits"
    for ln in _joined(lines):
        t = _unpipe(ln)
        g = re.match(r"^(?:security|securities)\s+(?:for|against)\s+(.+?):?$", t, re.I) or re.match(r"^(?:for|against)\s+(.+?):$", t, re.I)
        if g and len(t) < 110:
            group = g.group(1).strip()
            continue
        body = BULLET.sub("", t).strip()
        if len(body) < 12 or re.match(r"^(\d+ of \d+ security items|source:)", body, re.I):
            continue
        k = _kind(body)
        if k == "other" and not money(body):
            continue
        amts = money(body)
        nw = re.search(rf"net\s*worth\s*(?:of\s*)?(?:SAR|SR)\s*({_AMT})\s*(bn|billion|mn|m|million)?", body, re.I)
        ds = dates(body)
        low = body.lower()
        if re.search(r"not\s+(?:yet\s+)?perfected|to\s+be\s+(?:perfected|obtained|executed|registered|acknowledged|signed)|pending|awaited|not\s+yet\s+(?:executed|obtained|received)|\(new\b|new,", low):
            st = "pending"
        elif re.search(r"executed|perfected|held|registered|in place|available|\(existing|existing[;,)]|acknowledged by", low):
            st = "perfected"
        else:
            st = "not_stated"
        out.append({"seq": len(out) + 1, "group": group, "kind": k, "provider": _provider(body), "amount_mn": amts[0] if amts else None,
                    "net_worth_mn": to_mn(nw.group(1), nw.group(2)) if nw else None,
                    "net_worth_date": ds[0] if nw and ds else None, "perfection_status": st,
                    "deadline": ds[-1] if st == "pending" and ds else None, "text": body})
    return out


TNC_CATS: list[tuple[str, str]] = [
    (r"not\s+complied|existing\s+condition|status of (?:the )?existing", "existing_condition"),
    (r"audited|interim|financial statements|within \d+ days|reporting|submit", "reporting"),
    (r"routing|route|business of|turnover of|x the limit|times the limit", "routing"), (r"auditor", "auditor"),
    (r"cover(?:age)? ratio|covered by|remaining contract", "cover_ratio"), (r"settle|waterfall|proceeds first", "settlement"),
    (r"disburse|against (?:certified )?payment certificate|% of (?:the )?(?:certified|certificate)", "disbursement"),
    (r"purpose|not be used|inter-?group|related part", "purpose"), (r"cap|maximum|not exceed|at any time", "cap"),
    (r"utili[sz]", "utilisation")]


def _joined(lines: list[str]) -> list[str]:
    """Wrapped lines back into items: a line that does not open a bullet, a number or a group heading continues the last item."""
    out: list[str] = []
    for ln in lines:
        t = _unpipe(ln)
        if not t:
            continue
        opens = bool(BULLET.match(t)) or bool(re.match(r"^(?:security|securities|terms|for|against|applicable)\b", t, re.I)) or t.endswith(":")
        if out and not opens and not out[-1].endswith(":") and (out[-1][-1:] not in ".;" or t[:1].islower() or t[:1] in "(0123456789"):
            out[-1] = f"{out[-1]} {t}"
        else:
            out.append(t)
    return out


def terms(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    group = "All limits"
    for ln in _joined(lines):
        t = _unpipe(ln)
        g = re.match(r"^(?:terms(?:\s+and\s+conditions)?\s+)?(?:for|applicable to)\s+(.+?):?$", t, re.I)
        if g and len(t) < 110 and not BULLET.match(t):
            group = g.group(1).strip()
            continue
        body = BULLET.sub("", t).strip()
        if len(body) < 15 or body.lower().startswith("source:"):
            continue
        cat = next((c for pat, c in TNC_CATS if re.search(pat, body, re.I)), "other")
        low = body.lower()
        st = "not_complied" if "not complied" in low else ("complied" if re.search(r"\bcomplied\b", low) else "new")
        out.append({"seq": len(out) + 1, "group": group, "category": cat, "text": body, "existing_status": st})
    return out


# ------------------------------------------------------------------ the ask and the engine fields

def action(lines: list[str], tot: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(lines)
    out: dict[str, Any] = {"text": text}
    m = re.search(r"purpose(?:\s+as\s+per\s+business)?\s*[:\-]\s*(.+?)(?:\.\s|$)", text, re.I)
    if m:
        out["purpose"] = m.group(1).strip()
    m = re.search(r"(?:approved|sanctioned)\s*(?:by|vide|under)\s*(?:committee\s+)?(?:ref(?:erence)?\.?\s*)?([A-Z]{2,6}[-/ ]?\d{2,4}[-/]\d{1,4})\s*(?:on|dated)?\s*([^.;,]*)", text, re.I)
    if m:
        out["previous_ref"] = m.group(1)
        ds = dates(m.group(2) or "")
        out["previous_date"] = ds[0] if ds else None
    m = re.search(rf"from\s*(?:SAR|SR)\s*({_AMT})\s*(bn|mn|m|million)?\s*to\s*(?:SAR|SR)\s*({_AMT})\s*(bn|mn|m|million)?", text, re.I)
    if m:
        out["from_total"], out["to_total"] = to_mn(m.group(1), m.group(2)), to_mn(m.group(3), m.group(4))
    m = re.search(rf"exposure\s*cap\s*from\s*(?:SAR|SR)\s*({_AMT})\s*(bn|mn|m|million)?\s*to\s*(?:SAR|SR)\s*({_AMT})\s*(bn|mn|m|million)?", text, re.I)
    if m:
        out["cap_from"], out["cap_to"] = to_mn(m.group(1), m.group(2)), to_mn(m.group(3), m.group(4))
    out["asks"] = [s.strip() for s in re.split(r";\s*|\s+and\s+(?=(?:renew|increase|reduce|approve|set|grant|establish|extend|take over|a new))", text) if
                   re.match(r"^(?:business requests? approval.*?to\s+)?(renew|increase|reduce|approve|set|grant|establish|extend|take over|a new|new)", s.strip(), re.I)][:12]
    return out


SECTOR_WORDS = [(r"contract|construction|civil works|epc|building works", "Construction"), (r"trading|distribut|wholesale|building materials|medical supplies", "Wholesale Trade"),
                (r"manufactur|factory|industr|plant", "Manufacturing"), (r"logistic|transport|haulage", "Transport and Logistics"),
                (r"hospital|healthcare|clinic|medical", "Healthcare"), (r"real estate|developer|properties", "Real Estate"),
                (r"service|facility management|consult|it services|cleaning|catering", "Services")]


def sector_of(text: str) -> str | None:
    for pat, s in SECTOR_WORDS:
        if re.search(pat, text or "", re.I):
            return s
    return None


def _facility_type(rows: list[dict[str, Any]]) -> str:
    by: dict[str, float] = {}
    for r in rows:
        if r["level"] == 0:
            continue
        p = (r.get("product_code") or "").upper()
        n = r["limit_name"].lower()
        if p in ("PB", "APG", "RB", "BB") or re.search(r"performance|advance.?payment|bid bond|retention|\blg", n):
            ft = "performance_lg"
        elif p.startswith(("LC", "LCM", "TR")) or re.search(r"letter of credit|\blc\b|trust receipt", n):
            ft = "trade_lc"
        elif p in ("TL", "STL") or "term" in n:
            ft = "term_loan"
        elif p in ("OD", "RCF", "WCF") or p.startswith("DMCCM") or re.search(r"overdraft|working capital|revolv|murabaha|payment certificate", n):
            ft = "revolver"
        else:
            continue
        by[ft] = by.get(ft, 0.0) + (r.get("proposed_mn") or 0.0)
    return max(by, key=by.get) if by else "revolver"


RATING = re.compile(r"(?<![A-Za-z])(AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?|CCC[+-]?|CC|C|D)(?![A-Za-z])")


def fields(h: dict[str, str], act: dict[str, Any], rows: list[dict[str, Any]], tot: dict[str, Any], text: str) -> dict[str, Any]:
    f: dict[str, Any] = {}
    if h.get("customer"):
        f["name"] = re.sub(r"\s*\(.*?\)\s*$", "", h["customer"]).strip()
    f["group_name"] = h.get("group") or ""
    f["rm"] = re.split(r"\s*/\s*", h.get("rm") or "")[0].strip()
    rt = RATING.findall(h.get("rating_proposed") or h.get("rating") or "")
    if rt:
        f["internal_rating"] = rt[-1]
    f["sector"] = sector_of(" ".join([h.get("industry", ""), f.get("name", ""), act.get("purpose", "")])) or sector_of(text[:3000])
    f["amount"] = tot.get("proposed")
    f["purpose"] = act.get("purpose") or ""
    f["facility_type"] = _facility_type(rows)
    spreads = [r["spread_pct"] for r in rows if r.get("spread_pct")]
    comms = [r["commission_pct_pa"] for r in rows if r.get("commission_pct_pa")]
    if spreads:
        f["margin_bps"] = int(round(max(spreads) * 100))
    if comms:
        f["commission_bps"] = int(round(max(comms) * 100))
    if "margin_bps" not in f and comms:
        f["margin_bps"] = f["commission_bps"]
    months = []
    for r in rows:
        for n, u in TENOR.findall(" ".join(str(r.get(k) or "") for k in ("tenor_text", "particulars"))):
            v = float(n)
            months.append(v * 12 if u.lower().startswith("year") else v / 30 if u.lower().startswith("day") else v)
    f["tenor_years"] = max(1, min(10, int(round(max(months) / 12.0)))) if months else 1
    cms = [r["cash_margin_pct"] for r in rows if r.get("cash_margin_pct")]
    if cms:
        f["cash_margin_pct"] = max(cms)
    return {k: v for k, v in f.items() if v not in (None, "")}


# ------------------------------------------------------------------ the projects table of the request (contractors)

PROJ_COLS = {"project": ("project",), "employer": ("employer", "client"), "value": ("value", "contract"), "done": ("done", "work done", "progress"),
             "billed": ("billed", "certified"), "received": ("received", "collected"), "retention": ("retention",), "completion": ("completion", "finish")}


def projects(lines: list[str]) -> list[dict[str, Any]]:
    """Rows of the request's 'Status of financed projects' table (SAR millions as the request prints them)."""
    out: list[dict[str, Any]] = []
    cols: dict[str, int] | None = None
    for ln in lines:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        low = [re.sub(r"[^a-z ]", "", c.lower()) for c in cells]
        if cols is None:
            if any("project" in c for c in low) and any(("employer" in c or "client" in c) for c in low):
                cols = {}
                for k, al in PROJ_COLS.items():
                    j = next((j for j, c in enumerate(low) if j not in cols.values() and any(a in c for a in al)), None)
                    if j is not None:
                        cols[k] = j
            continue
        if len(cells) < len(cols) - 1:
            continue

        def cell(k: str) -> str:
            j = cols.get(k)
            return cells[j] if j is not None and j < len(cells) else ""
        val = _num(cell("value")) if cell("value") else None
        if val is None or not re.search(r"[A-Za-z]", cell("project")):
            continue
        dn = PCT.search(cell("done"))
        out.append({"project": cell("project"), "employer": cell("employer"), "value_mn": val, "done_pct": float(dn.group(1)) if dn else None,
                    "billed_mn": _num(cell("billed")) if cell("billed") else None, "received_mn": _num(cell("received")) if cell("received") else None,
                    "retention_mn": _num(cell("retention")) if cell("retention") else None, "completion": (dates(cell("completion")) or [None])[0]})
    return out


# ------------------------------------------------------------------ the whole request

def parse(text: str, name: str = "request", method: str = "text") -> dict[str, Any]:
    if "OCR" in method:  # OCR runs words together ("Generallimit"): split runs of known words before reading
        from backend.dealdesk.credit_response.respace import respace
        text = "\n".join(respace(ln, text) for ln in text.splitlines())
    secs, pre = split_sections(text)
    h = header(pre + secs.get("header", []))
    if not h.get("customer"):
        m = re.search(r"(?:customer|borrower|obligor)\s*(?:name)?\s*[:|]\s*([^|\n]{3,80})", text, re.I)
        if m:
            h["customer"] = m.group(1).strip()
    fac = facilities(secs.get("facilities", []))
    if not fac:  # a request without a facilities heading: the table may sit under the action or in the preamble
        fac = facilities(secs.get("action", []) + pre)
    tot = totals(fac) if fac else {"existing": None, "outstanding": None, "proposed": None, "stated": False, "adds_up": True}
    act = action(secs.get("action", []), tot)
    fm = re.search(r"(?:study|arrangement)\s*(?:and|&)?\s*(?:documentation)?\s*fee\s*:\s*(.+?)(?:\.(?:\s|$)|$)", text, re.I | re.M)
    if fm:
        act["fee"] = fm.group(1).strip()
    if tot.get("proposed") in (None, 0) and act.get("to_total"):
        tot["proposed"] = act["to_total"]
    sec = security(secs.get("security", []))
    tnc = terms(secs.get("terms", []))
    fl = fields(h, act, fac, tot, text)
    gaps = []
    for k, label in (("action", "Action requested"), ("facilities", "Facilities table"), ("security", "Security and support"),
                     ("terms", "Terms and conditions")):
        if not secs.get(k):
            gaps.append(f"{label}: section not found in {name}")
    if not fac:
        gaps.append("Facilities: no limit lines could be read (existing, outstanding, proposed)")
    if not tot.get("adds_up", True):
        c = tot["calculated"]
        gaps.append(f"Facilities: the stated total (SAR {tot['proposed']:,.1f}m proposed) differs from the sum of the limits (SAR {c['proposed']:,.1f}m)")
    for k, label in (("name", "customer name"), ("internal_rating", "rating"), ("sector", "sector")):
        if k not in fl:
            gaps.append(f"Header: {label} not read")
    if not act.get("purpose") and act.get("text"):
        act["purpose"] = re.split(r"(?<=[a-z0-9)])\.\s", act["text"])[0][:300]
        fl.setdefault("purpose", act["purpose"])
    return {"document": name, "method": method, "header": h, "action": act, "facilities": fac, "totals": tot, "security": sec, "projects": projects(secs.get("projects", [])),
            "terms": tnc, "sections": secs, "preamble": pre, "fields": fl, "read_gaps": gaps,
            "counts": {"facilities": len([r for r in fac if not r["total"]]), "security": len(sec), "terms": len(tnc),
                       "sections": len(secs)}}


def as_check_doc(r: dict[str, Any], sha: str) -> dict[str, Any]:
    """The request in the proposal check's document shape (parse.read_docx), whatever file it came from."""
    from backend.dealdesk.house_style.bankform import registry
    secs = []
    hdr_lines = [f"{k}: {v}" for k, v in r["header"].items()]
    src = dict(r["sections"])
    src["header"] = hdr_lines + src.get("header", [])
    for k in registry.ANATOMY:
        lines = src.get(k)
        if not lines:
            continue
        paras = [{"i": None, "text": ln} for ln in lines if "|" not in ln]
        tables = [[[c.strip() for c in ln.split("|")] for ln in lines if "|" in ln]]
        tables = [t for t in tables if t]
        if k == "facilities" and not tables and r["facilities"]:
            tables = [[["Limit", "Existing", "Outstanding", "Proposed", "Particulars"]] +
                      [[f["limit_name"], str(f.get("existing_mn") or ""), str(f.get("outstanding_mn") or ""), str(f.get("proposed_mn") or ""),
                        f.get("particulars") or ""] for f in r["facilities"]]]
        spec = registry.BY_KEY[k]
        secs.append({"key": k, "n": spec.n, "heading": spec.heading, "paras": paras, "tables": tables, "heading_i": None,
                     "words": sum(len(p["text"].split()) for p in paras) + sum(len(" ".join(c for row in t for c in row).split()) for t in tables)})
    full = "\n".join(ln for v in src.values() for ln in v)
    if r["sections"].get("justification"):
        full += "\n" + "\n".join(r["sections"]["justification"])
    return {"name": r["document"], "kind": r["method"], "sha": sha, "title": f"Business request · {r['header'].get('customer', '')}",
            "header": {k.replace("_", " ").title(): v for k, v in r["header"].items()}, "sections": secs, "paragraphs": 0, "full_text": full}
