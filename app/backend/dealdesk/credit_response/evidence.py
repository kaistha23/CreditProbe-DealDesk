"""The customer's supporting documents uploaded with the business request: what each one is and what it prints.

    docs = read_all([(name, bytes), ...])      # [{name, doc_type, label, subject, fields, tables, method, sha, read_error}]
    by = index(docs)                           # {doc_type: [doc, ...]} in upload order

Classification and fields: session i's intake (backend/dealdesk/intake) when it is merged and exposes a classifier;
otherwise the document types of the R16 demo contract (ops/r16_customers/doctypes.py: every document prints its title and
a "Key details" block of `Label: value` lines). Amounts are SAR units as printed (SAR 12,345,678); the writers convert to
millions. Deterministic.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.credit_response import reading


def _types() -> list[Any]:
    try:
        from ops.r16_customers import doctypes
        return list(doctypes.DOC_TYPES)
    except Exception:  # noqa: BLE001 - the demo contract is not merged: no typed reading
        return []


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9%]+", "", str(s).lower())


DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")


def typed(v: str, kind: str) -> Any:
    v = (v or "").strip().strip("|").strip()
    if v in ("", "–", "-", "n/a", "N/A", "None"):
        return None
    if kind == "date":
        m = DATE.match(v) or re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
        if m:
            return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = ISO.match(v)
        return m.group(0).strip() if m else v
    if kind == "sar":
        m = re.search(r"\(?-?[\d,]+(?:\.\d+)?\)?", v.replace("SAR", ""))
        if not m:
            return None
        t = m.group(0)
        neg = t.startswith("(") or t.startswith("-")
        try:
            x = float(t.strip("()-").replace(",", ""))
        except ValueError:
            return None
        return -x if neg else x
    if kind == "pct":
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        return float(m.group(0)) if m else None
    if kind == "int":
        m = re.search(r"-?\d[\d,]*", v)
        return int(m.group(0).replace(",", "")) if m else None
    return v


def classify(text: str, name: str) -> tuple[Any | None, float]:
    """(DocType, score) from the printed title and labels; the file name is a hint only."""
    best, score = None, 0.0
    head = text[:1500].upper()
    body = _key(text[:6000])
    for dt in _types():
        s = 0.0
        for kw in dt.keywords:
            if kw.upper() in head:
                s += 3.0 if kw.isupper() else 1.0
        hits = sum(1 for _f, lb, _t in dt.fields if _key(lb + ":") in body or _key(lb) in body)
        s += hits / max(len(dt.fields), 1) * 3.0
        if dt.code in name.lower():
            s += 1.0
        if s > score:
            best, score = dt, s
    return (best, score) if score >= 2.5 else (None, score)


def _split_pairs(line: str) -> list[tuple[str, str]]:
    out = []
    cells = [c.strip() for c in line.split("|")] if "|" in line else [line]
    for i, c in enumerate(cells):
        m = re.match(r"^([A-Za-z][A-Za-z0-9 /().,%'&-]{1,70}?)\s*:\s*(.*)$", c)
        if m:
            v = m.group(2).strip()
            if not v and i + 1 < len(cells):  # "Label: | value" (a Word key-value table)
                v = cells[i + 1]
            out.append((m.group(1).strip(), v))
    if "|" in line and not out and len(cells) % 2 == 0:  # a two-column Word table: Label | value
        out = [(cells[i], cells[i + 1]) for i in range(0, len(cells), 2)]
    return out


def _tables(lines: list[str]) -> list[list[list[str]]]:
    out, cur = [], []
    for ln in lines:
        if ln.count("|") >= 2:
            cur.append([c.strip() for c in ln.split("|")])
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _list_field(tables: list[list[list[str]]], sub: list[str]) -> list[dict[str, Any]] | None:
    """The table whose header row matches the most sub-fields, as a list of {sub-field: cell}."""
    best, best_hits, best_map = None, 0, {}
    for t in tables:
        hdr = [_key(c) for c in t[0]]
        mp = {}
        for s in sub:
            sk = _key(s.replace("_", ""))
            words = [w for w in s.split("_") if w not in ("pct", "mn")]
            for j, h in enumerate(hdr):
                if j in mp.values():
                    continue
                if h == sk or (words and all(_key(w) in h for w in words)) or (len(sk) > 3 and (sk in h or h in sk) and h):
                    mp[s] = j
                    break
        if len(mp) > best_hits:
            best, best_hits, best_map = t, len(mp), mp
    if best is None or best_hits < max(2, len(sub) // 3):
        return None
    rows = []
    for r in best[1:]:
        if not any(c.strip() for c in r):
            continue
        rows.append({s: (r[j] if j < len(r) else "") for s, j in best_map.items()})
    return rows


def _transactions(tables: list[list[list[str]]]) -> list[dict[str, Any]] | None:
    """Statement lines Date | Description | Debit | Credit | Balance where a PDF drops the empty cell: debit or credit is
    told by the running balance (it rises on a credit)."""
    start = None
    for i, t in enumerate(tables):
        hdr = [_key(c) for c in t[0]]
        if "date" in hdr and "balance" in hdr and ("credit" in hdr or "debit" in hdr):
            start = i
            break
    if start is None:
        return None
    rows = tables[start][1:] + [r for t in tables[start + 1:] for r in t]  # the table runs on over the next pages
    out, prev = [], None
    for r in rows:
        cells = [c for c in r if c.strip()]
        if len(cells) < 3 or not DATE.match(cells[0]):
            continue
        bal = typed(cells[-1], "sar")
        nums = [typed(c, "sar") for c in cells[2:-1]]
        nums = [x for x in nums if x is not None]
        debit = credit = None
        if len(nums) >= 2:
            debit, credit = nums[0] or None, nums[1] or None
        elif len(nums) == 1 and bal is not None and prev is not None:
            if bal >= prev:
                credit = nums[0]
            else:
                debit = nums[0]
        elif len(nums) == 1:
            credit = nums[0] if re.search(r"(?i)payment from|receipt|received|certificate payment|transfer in|collection|IPC", cells[1]) else None
            debit = None if credit else nums[0]
        out.append({"date": typed(cells[0], "date"), "description": cells[1], "debit": debit, "credit": credit, "balance": bal})
        prev = bal if bal is not None else prev
    return out


def extract(text: str, dt: Any) -> dict[str, Any]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    pairs: dict[str, str] = {}
    for ln in lines:
        for k, v in _split_pairs(ln):
            pairs.setdefault(_key(k), v)
    tables = _tables(lines)
    out: dict[str, Any] = {}
    for fname, label, kind in dt.fields:
        if fname == "transactions":
            tx = _transactions(tables)
            if tx:
                out[fname] = tx
            continue
        if kind.startswith("list"):
            sub = kind.split(":", 1)[1].split(",") if ":" in kind else []
            rows = _list_field(tables, sub)
            if rows is not None:
                types = {}
                for s in sub:
                    types[s] = "sar" if s in ("limit", "outstanding", "overdue", "amount", "value", "credits", "debits", "closing_balance", "avg_balance",
                                              "contract_value", "billed", "received", "retention_held", "sales", "purchases", "taxable_sales",
                                              "zero_rated_sales", "output_vat", "input_vat", "net_vat_due", "debit", "credit", "balance", "total",
                                              "b0_90", "b91_180", "b181_365", "over_365", "over_180", "existing", "proposed") else (
                        "pct" if s.endswith("pct") or s in ("share_pct", "pct") else ("date" if s in ("start", "planned_completion", "opened", "filed_on", "date", "maturity") else "text"))
                out[fname] = [{s: typed(r.get(s, ""), types[s]) if types[s] != "text" else (r.get(s) or "").strip() for s in sub} for r in rows]
            continue
        v = pairs.get(_key(label))
        if v is None:
            m = re.search(rf"{re.escape(label)}\s*[:|]\s*([^\n|]+)", text, re.I)
            v = m.group(1) if m else None
        if v is not None:
            out[fname] = typed(v, kind)
    return out


def _intake_classifier() -> Any | None:
    for mod in ("backend.dealdesk.intake.classify", "backend.dealdesk.intake.extract", "backend.dealdesk.intake.documents"):
        try:
            m = __import__(mod, fromlist=["x"])
        except Exception:  # noqa: BLE001
            continue
        for fn in ("read_document", "classify_and_extract", "document"):
            if hasattr(m, fn):
                return getattr(m, fn)
    return None


def read_one(name: str, data: bytes) -> dict[str, Any]:
    try:
        r = reading.read(name, data)
    except reading.ReadError as e:
        return {"name": name, "doc_type": None, "label": "Not readable", "fields": {}, "method": "", "sha": "", "read_error": str(e), "text": ""}
    fn = _intake_classifier()
    if fn is not None:
        try:
            got = fn(name, data)
            if isinstance(got, dict) and got.get("doc_type"):
                return {"name": name, "doc_type": got["doc_type"], "label": got.get("label") or got["doc_type"], "fields": got.get("fields") or {},
                        "subject": got.get("subject") or "", "method": r["method"], "sha": r["sha"], "read_error": "", "text": r["text"],
                        "classified_by": "session i intake"}
        except Exception:  # noqa: BLE001 - fall back to the contract reader
            pass
    dt, score = classify(r["text"], name)
    if dt is None:
        return {"name": name, "doc_type": None, "label": "Not recognised", "fields": {}, "method": r["method"], "sha": r["sha"], "read_error": "",
                "text": r["text"], "classified_by": "document-type contract", "score": round(score, 2)}
    f = extract(r["text"], dt)
    subj = f.get("full_name") or f.get("bank_name") or f.get("project_id") or f.get("certificate_number") or ""
    fy = f.get("fiscal_year") or f.get("period_to") or ""
    if dt.code in ("audited_fs", "inhouse_fs") and fy:
        subj = str(fy)[:4] if dt.code == "audited_fs" else f"{str(f.get('period_from', ''))[:7]}..{str(fy)[:7]}"
    return {"name": name, "doc_type": dt.code, "label": dt.label, "group": dt.group, "fields": f, "subject": str(subj), "method": r["method"],
            "sha": r["sha"], "read_error": "", "text": r["text"], "classified_by": "document-type contract", "score": round(score, 2)}


def read_all(files: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
    return [read_one(n, b) for n, b in files]


def index(docs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        if d.get("doc_type"):
            out.setdefault(d["doc_type"], []).append(d)
    return out


def is_request(text: str) -> bool:
    """A business request (the bank-form 'Action requested'), not a supporting document."""
    head = text[:3000].upper()
    return ("ACTION REQUESTED" in head or "BUSINESS REQUEST" in head) and "CREDIT DIVISION COMMENTS" not in head
