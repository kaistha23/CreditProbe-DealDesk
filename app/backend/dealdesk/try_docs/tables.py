"""Tables in a proposal's text, however the file laid them out.

A Word table arrives as pipe rows ("Revenue | 612.0 | 655.0 | 702.0"); a PDF from a report writer arrives one cell per
line (the label on one line, each value on the next lines), a long name wrapped over lines and a sub-limit indented.
Two readers here: the facilities table (limit / sub-limit, existing, outstanding, proposed, cash margin, particulars)
with the total row, and the period tables of the financials (Item | FY2023 | FY2024 | FY2025 | H1 2026).
"""
from __future__ import annotations

import re
from typing import Any

_NUMV = r"-?\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|-?\d+(?:\.\d+)?"
NUM_LINE = re.compile(rf"^\s*({_NUMV})\s*(?:x|%|m)?\s*$")
DASH = re.compile(r"^\s*[–—-]\s*$")
PCT = re.compile(r"^\s*\d+(?:\.\d+)?\s*%\s*$")
PERIOD = re.compile(r"^(FY\s?\d{4}|\d{4}A?|\d{4}[PE]|H[12]\s?\d{4}|Q[1-4]\s?\d{4}|9M\s?\d{4}|[A-Z][a-z]{2}\s?\d{4})$")
SPREAD = re.compile(r"(?:SAIBOR|EIBOR|SOFR|KIBOR|benchmark)\s*\+\s*(\d+(?:\.\d+)?)\s*(%|bps|bp)?", re.I)
COMMISSION = re.compile(r"commission\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*%", re.I)
NUM_COLS = ("existing", "outstanding", "proposed")


def num(s: str) -> float | None:
    m = re.search(_NUMV, s or "")
    if not m:
        return None
    t = m.group(0)
    neg = t.startswith("(") and t.endswith(")")
    v = float(t.strip("()").replace(",", ""))
    return -v if neg else v


def pricing(particulars: str) -> tuple[int | None, int | None]:
    """(spread over the benchmark in bps, commission in bps) from a facility's particulars."""
    sp = cm = None
    m = SPREAD.search(particulars or "")
    if m:
        v = float(m.group(1))
        sp = int(round(v if (m.group(2) or "").startswith("bp") or v >= 20 else v * 100))
    m = COMMISSION.search(particulars or "")
    if m:
        cm = int(round(float(m.group(1)) * 100))
    return sp, cm


def _row(name: str, vals: dict[str, float | None], particulars: str, level: int) -> dict[str, Any]:
    sp, cm = pricing(particulars)
    return {"facility": " ".join(name.split()), "existing": vals.get("existing"), "outstanding": vals.get("outstanding"),
            "proposed": vals.get("proposed"), "pricing_bps": sp, "commission_bps": cm, "particulars": " ".join(particulars.split()),
            "level": level, "total": bool(re.match(r"^(total|الإجمالي|المجموع)", name.strip(), re.I))}


def _pipe_facilities(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    head: list[str] | None = None
    for ln in lines:
        if "|" not in ln:
            if head and out:
                break
            continue
        cells = [c.strip() for c in ln.split("|")]
        low = [c.lower() for c in cells]
        if re.search(r"facility|limit|التسهيل|الحد", low[0]) and any(re.search(r"proposed|مقترح", c) for c in low):
            head = low
            continue
        if head is None:
            continue
        if len(cells) < 3 or low[0] == "item" or all(PERIOD.match(c) for c in cells[1:] if c):
            break
        vals: dict[str, float | None] = {}
        for k in NUM_COLS:
            idx = next((i for i, h in enumerate(head) if h.startswith(k) or (k == "proposed" and "مقترح" in h)), None)
            if idx is not None and idx < len(cells):
                vals[k] = num(cells[idx])
        pidx = next((i for i, h in enumerate(head) if re.search(r"particular|pricing|terms|bps", h)), None)
        part = cells[pidx] if pidx is not None and pidx < len(cells) else ""
        bps = None
        if pidx is not None and re.search(r"bps", head[pidx]) and num(part) is not None and not SPREAD.search(part):
            bps, part = num(part), ""  # a bare 'Pricing (bps)' column: margin on a funded line, commission on an LG or LC
        if vals.get("proposed") is None and vals.get("existing") is None:
            if out:
                break
            continue
        r = _row(cells[0], vals, part, 0)
        r["bps"] = bps
        out.append(r)
        if r["total"] and len(out) > 1:
            break  # the closing total row
    return out


def _cell_facilities(lines: list[str]) -> list[dict[str, Any]]:
    """One cell per line (a PDF from a report writer): header cells, then per row name lines, the numbers, margin, particulars."""
    start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*limit\s*/\s*sub-?limit\s*$|^\s*facilit(y|ies)\s*$", ln, re.I)), None)
    if start is None:
        return []
    head: list[str] = []
    i = start + 1
    while i < len(lines) and i < start + 12:
        low = lines[i].strip().lower()
        if low.startswith("particulars") or low.startswith("pricing"):
            i += 1
            break
        for k in NUM_COLS:
            if low.startswith(k):
                head.append(k)
        i += 1
    if "proposed" not in head:
        return []
    margin = any(re.match(r"^\s*cash\s*$|^\s*cash margin", ln, re.I) for ln in lines[start:i])
    rows: list[dict[str, Any]] = []
    name: list[str] = []
    vals: list[float | None] = []
    part: list[str] = []
    level = 0
    state = "name"

    def flush() -> None:
        if name and vals:
            rows.append(_row(" ".join(name), dict(zip(head, vals, strict=False)), " ".join(part), level))

    for ln in lines[i:]:
        s = ln.strip()
        if not s:
            continue
        if re.match(r"^source:", s, re.I) or re.match(r"^\d{1,2}\.\s+[A-Z]", s):
            break
        starts_row = ln.startswith((" ", "\t")) or re.match(r"^(total)", s, re.I)
        if state == "part" and starts_row:
            flush()
            name, vals, part, state = [], [], [], "name"
        if state == "name":
            if NUM_LINE.match(s) and name:
                vals.append(num(s))
                state = "nums" if len(vals) < len(head) else ("margin" if margin else "part")
            else:
                if not name:
                    level = (len(ln) - len(ln.lstrip(" "))) // 4
                name.append(s)
            continue
        if state == "nums":
            vals.append(num(s) if NUM_LINE.match(s) else None)
            if len(vals) >= len(head):
                state = "margin" if margin else "part"
            continue
        if state == "margin":
            state = "part"
            if DASH.match(s) or PCT.match(s):
                continue
        if state == "part":
            if DASH.match(s):
                continue
            part.append(s)
    if state in ("part", "margin") or (state == "nums" and len(vals) >= len(head)):
        flush()
    return rows


def facilities(text: str) -> list[dict[str, Any]]:
    """Every row of the facilities table, the total row marked (`total: True`); [] when there is none."""
    lines = text.splitlines()
    rows = _pipe_facilities(lines) if "|" in text else []
    if not rows:
        rows = _cell_facilities(lines)
    return rows


# ------------------------------------------------------------------ period tables (financials)

FIN_LABELS = {
    "revenue": (r"^(revenue|sales|turnover|net sales|الإيرادات|المبيعات)\b",),
    "ebitda": (r"^ebitda\b", r"^الأرباح قبل الفوائد"),
    "net_worth": (r"^(tangible )?net worth\b", r"^(total )?(shareholders'? )?equity$", r"^صافي حقوق الملكية"),
    "current_ratio": (r"^current ratio\b", r"^نسبة التداول"),
    "total_debt": (r"^total (bank )?debt\b", r"^(total )?borrowings\b", r"^إجمالي الديون"),
    "debt_service": (r"^debt service\b", r"^خدمة الدين"),
    "bank_debt_st": (r"^bank debt short[- ]term\b",),
    "bank_debt_lt": (r"^bank debt long[- ]term\b",),
}


def _field(label: str) -> str | None:
    low = label.strip().lower()
    for f, pats in FIN_LABELS.items():
        if any(re.match(p, low) for p in pats):
            return f
    return None


def _pick(periods: list[str]) -> int:
    """The latest full-year column (FY or a bare year), else the last."""
    full = [i for i, p in enumerate(periods) if re.match(r"^(FY\s?)?\d{4}A?$", p)]
    return full[-1] if full else len(periods) - 1


def period_tables(text: str) -> list[dict[str, Any]]:
    """[{title, periods, values: {field: [..]}}] for every 'Item | FY… | FY…' table (pipe rows or one cell per line)."""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if "|" in ln:
            cells = [c.strip() for c in ln.split("|")]
            if len(cells) >= 3 and all(PERIOD.match(c) for c in cells[1:] if c) and sum(1 for c in cells[1:] if c) >= 1:
                periods = [c for c in cells[1:] if c]
                title = lines[i - 1] if i else ""
                t = {"title": title, "periods": periods, "values": {}}
                j = i + 1
                while j < len(lines) and "|" in lines[j]:
                    cs = [c.strip() for c in lines[j].split("|")]
                    f = _field(cs[0])
                    if f:
                        t["values"][f] = [num(c) for c in cs[1:1 + len(periods)]]
                    j += 1
                out.append(t)
                i = j
                continue
        elif ln.lower() == "item" and i + 1 < len(lines) and PERIOD.match(lines[i + 1]):
            j = i + 1
            periods = []
            while j < len(lines) and PERIOD.match(lines[j]):
                periods.append(lines[j])
                j += 1
            title = next((lines[k] for k in range(i - 1, max(-1, i - 4), -1) if lines[k]), "")
            t = {"title": title, "periods": periods, "values": {}}
            n = len(periods)
            while j < len(lines):
                lab = lines[j]
                if not lab:
                    j += 1
                    continue
                if lab.lower().startswith("source:") or re.match(r"^\d{1,2}\.\s+[A-Z]", lab):
                    break
                if lab.lower() == "item":  # the table continues on the next page with its header repeated
                    j += 1
                    while j < len(lines) and PERIOD.match(lines[j]):
                        j += 1
                    continue
                vals = lines[j + 1:j + 1 + n]
                if len(vals) == n and all(NUM_LINE.match(v) or v in ("–", "-", "—") for v in vals):
                    f = _field(lab)
                    if f:
                        t["values"][f] = [num(v) for v in vals]
                    j += 1 + n
                else:
                    j += 1
            out.append(t)
            i = j
            continue
        i += 1
    return out


def financials(text: str, obligor: str | None = None) -> dict[str, Any] | None:
    """The obligor's own statement (the table titled with its name or 'standalone', else the first) at its latest full year."""
    ts = [t for t in period_tables(text) if t["values"]]
    if not ts:
        return None
    def score(t: dict[str, Any]) -> int:
        tl = t["title"].lower()
        return (2 if obligor and obligor.lower()[:20] in tl else 0) + (1 if "standalone" in tl else 0) - (1 if "consolidated" in tl or "combined" in tl else 0)
    t = max(ts, key=score)
    k = _pick(t["periods"])
    vals = {f: (v[k] if k < len(v) else None) for f, v in t["values"].items()}
    if vals.get("total_debt") is None and (vals.get("bank_debt_st") is not None or vals.get("bank_debt_lt") is not None):
        vals["total_debt"] = (vals.get("bank_debt_st") or 0) + (vals.get("bank_debt_lt") or 0)
    vals.pop("bank_debt_st", None)
    vals.pop("bank_debt_lt", None)
    return {"title": t["title"], "period": t["periods"][k], "values": {f: v for f, v in vals.items() if v is not None}}
