"""Round A: the agent's business request in Word, through R16's bank-form path (backend/dealdesk/rm_request/render.py).

The drafted markdown becomes R16's paper shape (header line, parts, sections of blocks) so the Word file has the bank form's
header block on every page, the part banners, the action requested in a ruled box and the signature grid.
"""
from __future__ import annotations

import re
from typing import Any

KEYS = {1: "action", 2: "facilities", 3: "security", 4: "group_exposure", 5: "background", 6: "financials", 7: "justification",
        8: "documents", 9: "recommendation"}
PARTS = [("action", "ACTION REQUESTED", "Business · Corporate Banking Group", ("action", "facilities", "security")),
         ("business", "BUSINESS COMMENTS", "Business · relationship manager", ("group_exposure", "background", "financials", "documents")),
         ("justification", "RM'S JUSTIFICATION", "Business · relationship manager", ("justification", "recommendation")),
         ("approvals", "BUSINESS APPROVALS", "RM · Unit head · Regional head", ("signatures",))]


def _plain(t: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", t).replace("`", "").strip()


def _table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    rows = [[_plain(c) for c in ln.strip().strip("|").split("|")] for ln in lines if not re.match(r"^\|?\s*:?-{2,}", ln.strip())]
    return (rows[0], rows[1:]) if rows else ([], [])


def blocks(md_lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(md_lines):
        ln = md_lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.lstrip().startswith("|"):
            tbl = []
            while i < len(md_lines) and md_lines[i].lstrip().startswith("|"):
                tbl.append(md_lines[i])
                i += 1
            h, rows = _table(tbl)
            if h:
                out.append({"t": "table", "header": h, "rows": rows})
            continue
        if re.match(r"^\s*[-*] ", ln):
            items = []
            while i < len(md_lines) and re.match(r"^\s*[-*] ", md_lines[i]):
                items.append(_plain(re.sub(r"^\s*[-*] ", "", md_lines[i])))
                i += 1
            out.append({"t": "bullets", "items": items})
            continue
        if ln.startswith("### "):
            out.append({"t": "h", "text": _plain(ln[4:])})
        else:
            out.append({"t": "p", "text": _plain(ln)})
        i += 1
    return out


def paper(run: dict[str, Any]) -> dict[str, Any]:
    md = (run.get("draft") or {}).get("md") or ""
    lines = md.splitlines()
    title = next((x[2:].strip() for x in lines if x.startswith("# ")), f"Business Request — {run.get('customer') or ''}")
    secs: dict[str, dict[str, Any]] = {}
    cur = "header"
    buf: dict[str, list[str]] = {"header": []}
    heads: dict[str, str] = {"header": "Header block"}
    for ln in lines:
        if ln.startswith("# "):
            continue
        m = re.match(r"^##\s*(\d+)[.)]?\s*(.+)$", ln)
        if m and int(m.group(1)) in KEYS:
            cur = KEYS[int(m.group(1))]
            heads[cur] = m.group(2).strip()
            buf[cur] = []
            continue
        if re.match(r"^##\s*What this request could not assess", ln):
            buf[cur].append("### What this request could not assess")
            continue
        buf.setdefault(cur, []).append(ln)
    for k, ls in buf.items():
        secs[k] = {"key": k, "heading": heads.get(k, k), "blocks": blocks(ls)}
    # the header table becomes the bank form's key-value block
    hb = secs["header"]["blocks"]
    if hb and hb[0]["t"] == "table" and len(hb[0]["header"]) == 2:
        pairs = [tuple(r[:2]) for r in hb[0]["rows"] if len(r) >= 2]
        hb[0] = {"t": "kv", "pairs": pairs, "cols": 2}
    secs["signatures"] = {"key": "signatures", "heading": "Signatures", "blocks": [
        {"t": "sign", "rows": [("Relationship manager", run.get("rm") or ""), ("Unit head, Corporate Banking", ""), ("Regional head", "")]}]}
    order = ["header", *KEYS.values(), "signatures"]
    sections = [secs[k] for k in order if k in secs]
    rid = run["run_id"]
    return {"request_id": rid, "customer": run.get("customer") or title.split("—")[-1].strip(), "as_of_label": run.get("as_of") or "",
            "sector": "", "group": "", "rm": run.get("rm") or "",
            "header_line": [("Customer", run.get("customer") or ""), ("CR", run.get("cr") or ""), ("Date", run.get("as_of") or ""),
                            ("RM", run.get("rm") or "RM"), ("Request", run.get("request_type") or ""), ("Ref", rid)],
            "sections": sections,
            "parts": [{"key": k, "title": t, "subtitle": s, "sections": [x for x in keys if x in secs]} for k, t, s, keys in PARTS]}


def docx(run: dict[str, Any], generated_by: str = "") -> tuple[bytes, str]:
    from backend.dealdesk.rm_request import render as RD
    data, _ = RD.docx(paper(run), generated_by=generated_by)
    safe = re.sub(r"[^\w-]+", "-", f"Business-request-{run.get('customer') or 'customer'}-{run['as_of']}")[:90].strip("-")
    return data, f"{safe}.docx"
