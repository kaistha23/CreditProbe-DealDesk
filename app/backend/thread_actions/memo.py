"""Word (R16 t, M7): the house-style memo, note or paper of one answer or a whole thread. Deterministic writer.

    build(doc, kind="memo", scope="thread", to="", by="", at=datetime, memo_id="", answer_index=None) -> bytes

Layout (docs/v5/HOUSE_STYLE.md, cover block on page 1):
    cover block   MEMO / NOTE / PAPER · title · To, From, Module, Reference
    In plain words  one line per answer (its first sentence), what the document holds
    1..n          one section per question: the question, the answer's text, key figures, tables (house table style)
    Sources and trace  every source, query, relation and row the answers named (backend/thread_actions/trace.py)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend import house_style as H
from backend.house_style import docx as hd

from . import trace as T

KIND_LABEL = {"memo": "Memo", "note": "Note", "paper": "Paper"}


_GREETING = re.compile(r"^(?:good\s+(?:morning|afternoon|evening)|hello|hi)\b[^.!?]*[.!?]\s*", re.I)


def first_sentence(text: str, n: int = 260) -> str:
    t = re.sub(r"^\s*#+\s*", "", text or "").strip()
    t = re.sub(r"\*\*", "", t)
    t = _GREETING.sub("", t) or t
    t = t.split("\n")[0].strip("-• ").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    s = m.group(1) if m else t
    s = re.sub(r"\s*:\s*$", ".", s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def plain_words(doc: dict[str, Any], turns: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for t in turns[:6]:
        text = next((b["text"] for b in t["blocks"] if b["kind"] == "text"), "")
        if not text:
            text = next((b["items"][0] for b in t["blocks"] if b["kind"] == "bullets"), "")
        line = first_sentence(text) if text else ""
        if not line:
            tb = next((b for b in t["blocks"] if b["kind"] == "table"), None)
            if tb:
                line = f"{tb['title'] or 'A table'} with {tb['row_count']} rows."
        if line:
            q = t["question"]
            out.append(f"**{q[:120]}{'…' if len(q) > 120 else ''}**: {line}" if q and len(turns) > 1 else line)
    tables = sum(1 for t in turns for b in t["blocks"] if b["kind"] == "table")
    srcs = sum(len(t["sources"]) for t in turns)
    out.append(f"This {('answer' if len(turns) == 1 else f'thread of {len(turns)} answers')} from {doc['module_label']} "
               f"carries {tables} table{'s' if tables != 1 else ''} and {srcs} source{'s' if srcs != 1 else ''}; "
               "every figure is as the thread showed it and the last section traces it.")
    return out


def _md(d, text: str) -> None:
    items: list[str] = []
    numbered = False

    def flush() -> None:
        nonlocal items
        if items:
            hd.bullets(d, items, numbered=numbered)
            items = []

    for raw in (text or "").splitlines():
        line = raw.strip()
        m = re.match(r"^(?:[-•*]|(\d+)[.)])\s+(.*)$", line)
        if m and not line.startswith("**"):
            if items and numbered != bool(m.group(1)):
                flush()
            numbered = bool(m.group(1))
            items.append(m.group(2))
            continue
        flush()
        if line.startswith("#"):
            hd.heading(d, line.lstrip("#").strip()[:200], 3)
        elif line:
            hd.para(d, line)
    flush()


def _widths(cols: int) -> list[float] | None:
    if cols <= 1:
        return None
    first = 5.0 if cols <= 4 else 3.6
    rest = (17.0 - first) / (cols - 1)
    return [first] + [rest] * (cols - 1)


def build(doc: dict[str, Any], kind: str = "memo", scope: str = "thread", to: str = "", by: str = "",
          at: datetime | None = None, memo_id: str = "", answer_index: int | None = None) -> bytes:
    at = at or datetime.now(timezone.utc)
    kind = kind if kind in KIND_LABEL else "memo"
    turns = doc["turns"]
    if scope == "answer":
        idx = answer_index if answer_index is not None and 0 <= answer_index < len(turns) else len(turns) - 1
        turns = [turns[idx]]
    title = doc["title"][:1].upper() + doc["title"][1:]
    meta = H.Meta(title=title, subject=f"{doc['module_label']} · {'one answer' if len(turns) == 1 else f'{len(turns)} answers'}",
                  generated_by=by, generated_at=at, reference=memo_id)
    details = [("To", to)] if to else []
    details += [("Module", doc["module_label"])]
    d = hd.document(meta, kind=KIND_LABEL[kind], subtitle="", cover="block", details=details)

    hd.heading(d, "In plain words", 1)
    hd.bullets(d, plain_words(doc, turns))

    for i, t in enumerate(turns, 1):
        hd.heading(d, f"{i}. {first_sentence(t['question'], 140) or 'Answer'}" if len(turns) > 1 else
                   (t["question"][:180] or "The answer"), 1)
        if t["question"] and len(turns) > 1 and len(t["question"]) > 140:
            hd.note(d, f"Question: {t['question']}")
        for b in t["blocks"]:
            if b["kind"] == "text":
                _md(d, b["text"])
            elif b["kind"] == "bullets":
                if b.get("title"):
                    hd.heading(d, b["title"], 3)
                hd.bullets(d, b["items"])
            elif b["kind"] == "figures":
                hd.key_figures(d, [(x["label"], x["value"]) for x in b["items"]], per_row=min(3, len(b["items"])) or 1)
            elif b["kind"] == "table":
                if b["title"]:
                    hd.heading(d, b["title"], 3)
                rows = b["rows"][:120]
                hd.table(d, b["columns"], rows, widths=_widths(len(b["columns"])), right_from=1, size=8 if len(b["columns"]) > 6 else 8.5)
                if b["row_count"] > len(rows):
                    hd.note(d, f"{len(rows)} of {b['row_count']} rows shown; the thread holds the rest.")

    tr = T.trace({**doc, "turns": turns})
    hd.heading(d, "Sources and trace", 1)
    hd.bullets(d, tr["plain_words"])
    src_rows = []
    for j, s in enumerate(tr["sources"][:60], 1):
        where = s.get("relation", "") or (", ".join(T.relations_in_sql(s["sql"])[:4]) if s.get("sql") else "")
        if s.get("domain") and s.get("relation"):
            where = f"{s['domain']}.{where}"
        keys = ", ".join(f"{k}={v}" for k, v in (s.get("keys") or {}).items())
        detail = "; ".join(x for x in (keys, s.get("period", ""), f"{s['rows']} rows" if s.get("rows") is not None else "") if x)
        src_rows.append([j, s["kind"].capitalize(), s["label"], where or "—", detail or "—"])
    if not src_rows:
        src_rows = [[1, "Screen", f"{doc['module_label']} thread", "—", "as shown on screen"]]
    hd.table(d, ["#", "Kind", "Source", "Relation", "Rows, keys, period"], src_rows, widths=[0.8, 2.0, 6.0, 4.4, 3.8], size=8)
    if tr["relations"]:
        hd.heading(d, "Data Domains relations", 3)
        hd.table(d, ["Relation", "Domain", "What it holds", "Registered"],
                 [[r["relation"], r["domain"] or "—", r["label"], "Yes" if r["registered"] else "No"] for r in tr["relations"]],
                 widths=[4.5, 3.0, 7.5, 2.0], size=8)
    for q in tr["queries"][:12]:
        hd.heading(d, f"Query: {q['label'][:120]}", 3)
        hd.para(d, q["sql"][:3000], size=7.5, colour=H.MUTED if hasattr(H, "MUTED") else None)
    hd.note(d, f"Prepared by CreditProbe from the {doc['module_label']} thread"
               f"{' for ' + by if by else ''} on {at.strftime('%d %b %Y %H:%M UTC')}. Deterministic writer: the same thread "
               "gives the same document.")
    return hd.to_bytes(d)
