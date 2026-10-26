"""What an assistant answer proposes for a report section, and how it merges in (PLAN_R5 P2, P3).

The section assistant writes for a person: it frames ("The headline for the section:", "Proposed wording",
"Detail worth naming in the text", "Suggested chart for the section: …"), quotes wording with `>`, and puts tables
in markdown pipes. None of that framing belongs in a credit report. So every answer carries a structured
`proposal` beside its chat text:

    {"blocks": [heading | paragraph | bullets | table | chart, ...], "placement": {"mode": "end"}}

and "Add to section" merges only the proposal:

  * the content meant for the report: the proposed wording (without quote markers), the tables (as real house-style
    tables, never raw pipes) and the suggested chart (drawn as a real Plotly chart from the answer's data);
  * never the framing, and never the assistant's asides ("Detail worth naming") when it proposed wording;
  * at the right point: the end by default, or after / in place of the paragraph the request names;
  * in the section's style: its heading numbering continues, and a heading the section already has is not repeated;
  * as one version, so one undo restores the section as it was (it shows in Versions).

A live model may also return the proposal itself, as a fenced ```proposal JSON block at the end of its answer;
that block is taken out of the chat text and used as it is (after the same cleaning).
"""
from __future__ import annotations

import json
import re
from typing import Any

# ------------------------------------------------------------------ markdown

_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_HEADING = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_LIST = re.compile(r"^\s*([-*•]|\d+[.)])\s+(.+)$")
_FENCE = re.compile(r"```\s*proposal\s*\n(.*?)```", re.S | re.I)


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _strip_md(s: str) -> str:
    return re.sub(r"\*\*|__|`", "", s).strip()


def elements(text: str) -> list[dict[str, Any]]:
    """Markdown as a list of elements: heading, table, quote, list, paragraph (in order)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[dict[str, Any]] = []
    i = 0
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append({"type": "paragraph", "text": "\n".join(para).strip()})
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            flush()
            i += 1
            continue
        if _TABLE_ROW.match(ln) and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1]):
            flush()
            head = _cells(ln)
            rows = []
            i += 2
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                if not _TABLE_RULE.match(lines[i]):
                    rows.append(_cells(lines[i]))
                i += 1
            out.append({"type": "table", "header": head, "rows": rows})
            continue
        m = _HEADING.match(ln)
        if m:
            flush()
            out.append({"type": "heading", "level": len(m.group(1)), "text": _strip_md(m.group(2))})
            i += 1
            continue
        if _QUOTE.match(ln):
            flush()
            q: list[str] = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                q.append(_QUOTE.match(lines[i]).group(1))  # type: ignore[union-attr]
                i += 1
            paras = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(q)) if p.strip()]
            out.append({"type": "quote", "paragraphs": paras})
            continue
        if _LIST.match(ln) and para and len(para) == 1 and (para[0].rstrip().endswith(":") or (
                para[0].strip().startswith("**") and para[0].strip().rstrip(":").endswith("**"))):
            flush()                                    # "**Detail worth naming**" directly above its list
        if _LIST.match(ln) and not para:
            items: list[str] = []
            while i < len(lines) and (_LIST.match(lines[i]) or (items and lines[i].startswith("  ") and lines[i].strip())):
                lm = _LIST.match(lines[i])
                if lm:
                    items.append(lm.group(2).strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append({"type": "list", "items": items, "ordered": bool(re.match(r"^\s*\d", ln))})
            continue
        para.append(ln.rstrip())
        i += 1
    flush()
    return out


_NUM = re.compile(r"^[+\-−]?\s*(SAR\s*)?[+\-−]?\d[\d,]*(\.\d+)?\s*(%|bps|bn|m|mn|x)?$", re.I)


def _is_num(s: str) -> bool:
    return bool(_NUM.match(s.replace(" ", "").strip()))


def num(s: Any) -> float | None:
    """A number out of a formatted cell: 'SAR 1,920.8m' -> 1920.8, '6.89%' -> 6.89, '+64.2' -> 64.2."""
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    t = str(s or "").replace(" ", "").replace("−", "-").strip()
    if not _is_num(t):
        return None
    m = re.search(r"[+\-]?\s*\d[\d,]*(\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0).replace(",", "").replace(" ", ""))
    if t.lstrip().startswith("-") and v > 0:
        v = -v
    return v


def table_from_md(header: list[str], rows: list[list[str]], title: str = "") -> dict[str, Any]:
    """A markdown table as a house-style table block. Cells keep the wording the answer gave them (already in
    plain units); the table renders as a real table on screen and in Word, never as pipes."""
    keys = [f"c{i}" for i in range(len(header))]
    cols = [{"key": k, "label": _strip_md(h) or f"Column {i + 1}", "format": "text"} for i, (k, h) in enumerate(zip(keys, header))]
    out_rows = []
    for r in rows[:500]:
        cells = (r + [""] * len(keys))[: len(keys)]
        out_rows.append({k: _strip_md(c) for k, c in zip(keys, cells)})
    b: dict[str, Any] = {"kind": "table", "columns": cols, "rows": out_rows}
    if title:
        b["title"] = title[:200]
    return b


def markdown_blocks(text: str) -> list[dict[str, Any]]:
    """Any markdown as report blocks: headings, paragraphs (quote markers removed), bullets and real tables."""
    out: list[dict[str, Any]] = []
    for e in elements(text):
        t = e["type"]
        if t == "heading":
            out.append({"kind": "heading", "text": e["text"], "level": 3 if e["level"] >= 3 else 2})
        elif t == "table":
            out.append(table_from_md(e["header"], e["rows"]))
        elif t == "quote":
            out += [{"kind": "paragraph", "text": p} for p in e["paragraphs"]]
        elif t == "list":
            out.append({"kind": "bullets", "items": e["items"][:40]})
        else:
            out.append({"kind": "paragraph", "text": e["text"]})
    return out


# ------------------------------------------------------------------ framing

_LABEL_WORDING = re.compile(r"\b(proposed|suggested|draft|recommended)\s+(wording|text|paragraphs?|narrative|commentary)\b|"
                            r"^\s*wording\b", re.I)
_LABEL_ASIDE = re.compile(r"\b(details?|points?|things?|figures?) (worth|to) (naming|name|noting|note|mention|mentioning|"
                          r"flag|flagging|highlight|highlighting)\b|\bnotes? for (the )?(author|you)\b|"
                          r"\bwhy (this|it) (matters|works)\b|\bcaveats?\b", re.I)
_LABEL_TABLE = re.compile(r"\btable\b|\bdrop-?in\b", re.I)
_LABEL_CHART = re.compile(r"^\s*(\*\*)?\s*(suggested|proposed|recommended)\s+(chart|visual|figure|graphic)\b", re.I)
_PREFIX = re.compile(r"^\s*(\*\*)?\s*(the\s+)?(headline|lead|opening|key message|one-line summary|summary line|"
                     r"proposed headline|suggested headline)(\s+(for|of)\s+(the|this)\s+section)?\s*:?\s*(\*\*)?\s*:\s*", re.I)
_CHART_LINE = re.compile(r"^\s*(\*\*)?\s*(suggested|proposed|recommended)\s+(chart|visual|figure)\b[^:]*:\s*(\*\*)?\s*(.+)$",
                         re.I | re.S)
_FILLER = re.compile(r"^\s*(here is|here's|below is|i would|i'd|you could|you can|for the section,|"
                     r"happy to|sure[,.!]|this gives you|use this)\b", re.I)


def _label_of(e: dict[str, Any]) -> str | None:
    """A short bold or colon-ended line that only announces what follows."""
    if e["type"] == "heading":
        txt = e["text"]
    elif e["type"] == "paragraph" and "\n" not in e["text"] and len(e["text"]) <= 90:
        raw = e["text"].strip()
        if not (raw.endswith(":") or (raw.startswith("**") and raw.rstrip(":").endswith("**"))):
            return None
        txt = _strip_md(raw).rstrip(":")
    else:
        return None
    if _LABEL_WORDING.search(txt):
        return "wording"
    if _LABEL_ASIDE.search(txt):
        return "aside"
    if _LABEL_CHART.search(txt):
        return "chart"
    if _LABEL_TABLE.search(txt):
        return "table"
    if e["type"] == "paragraph":
        return "label"
    return None


def _norm(s: str) -> str:
    s = re.sub(r"^\s*\d+(\.\d+)*[.)]?\s+", "", s or "")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ------------------------------------------------------------------ charts

_METRICS = ["ead", "ecl", "exposure", "coverage", "borrowers", "customers", "warned", "stage 2", "stage 3", "pd", "lgd",
            "limit", "headroom", "share", "change", "rwa", "raroc"]


def chart_from_table(table: dict[str, Any], hint: str, title: str = "") -> dict[str, Any] | None:
    """A grouped bar chart (Plotly) from a table, choosing the columns the suggestion names."""
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if len(cols) < 2 or not rows:
        return None
    xkey = cols[0]["key"]
    numeric = [c for c in cols[1:] if sum(num(r.get(c["key"])) is not None for r in rows) >= max(1, len(rows) // 2)]
    if not numeric:
        return None
    h = (hint or "").lower()
    share = bool(re.search(r"\bshare\b|%|percent|mix\b", h))
    picked: list[dict[str, Any]] = []
    for word in sorted({w for w in _METRICS if re.search(rf"\b{re.escape(w)}\b", h)}, key=lambda w: h.find(w)):
        if word == "share":
            continue
        cands = [c for c in numeric if word in c["label"].lower()]
        if not cands:
            continue
        pct = [c for c in cands if "%" in c["label"] or "share" in c["label"].lower()]
        best = (pct or cands)[0] if share else ([c for c in cands if c not in pct] or cands)[0]
        if best not in picked:
            picked.append(best)
    if not picked:
        picked = numeric[:2]
    pct_axis = all("%" in c["label"] or "share" in c["label"].lower() for c in picked)
    data = [{"type": "bar", "name": c["label"].replace("%", "").strip() + (" share" if pct_axis and "%" in c["label"] else ""),
             "x": [str(r.get(xkey) or "") for r in rows], "y": [num(r.get(c["key"])) for r in rows]}
            for c in picked[:4]]
    name = title or re.split(r",|\bwhich\b|\bthat\b|\(", hint or "")[0].strip(" .:") or table.get("title") or "Chart"
    layout: dict[str, Any] = {"barmode": "group", "xaxis": {"title": {"text": cols[0]["label"]}},
                              "yaxis": {"title": {"text": "Share (%)" if pct_axis else ""},
                                        **({"ticksuffix": "%"} if pct_axis else {})},
                              "legend": {"orientation": "h"}}
    return {"kind": "chart", "title": name[:1].upper() + name[1:200], "figure": {"data": data, "layout": layout}}


# ------------------------------------------------------------------ the proposal

def split_fenced(text: str) -> tuple[str, dict[str, Any] | None]:
    """A live model's own proposal (```proposal {json}```) out of its chat text."""
    m = _FENCE.search(text or "")
    if not m:
        return text, None
    try:
        got = json.loads(m.group(1))
    except ValueError:
        return text, None
    clean = (text[: m.start()] + text[m.end():]).strip()
    return clean, got if isinstance(got, dict) else None


def build(text: str, material: dict[str, Any] | None = None) -> dict[str, Any]:
    """The proposal of one answer: only what belongs in the report.

    `material` is the answer's rich part (its result tables as report blocks and its chart blocks)."""
    material = material or {}
    text, own = split_fenced(text)
    if own and isinstance(own.get("blocks"), list):
        blocks = [_from_own(b) for b in own["blocks"]]
        return {"blocks": [b for b in blocks if b], "placement": own.get("placement") or {"mode": "end"},
                "source": "model"}
    els = elements(text)
    role = None
    wording: list[dict[str, Any]] = []
    prose: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    headings: list[dict[str, Any]] = []
    chart_hints: list[str] = []
    for idx, e in enumerate(els):
        lab = _label_of(e)
        if lab and lab != "label":
            role = lab
            continue
        if lab == "label":
            role = None
            continue
        t = e["type"]
        if t == "heading":
            if idx == 0 or not headings:
                headings.append({"kind": "heading", "text": e["text"], "level": 3})
            role = None
            continue
        if t == "table":
            tables.append(table_from_md(e["header"], e["rows"]))
            continue
        if t == "paragraph":
            cm = _CHART_LINE.match(e["text"])
            if cm or role == "chart":
                chart_hints.append(_strip_md(cm.group(5) if cm else e["text"]))
                continue
            if _FILLER.match(e["text"]) and len(e["text"]) < 160:
                continue
            body = _PREFIX.sub("", e["text"]).strip()
            if not body:
                continue
            blk = {"kind": "paragraph", "text": body}
            (wording if role == "wording" else prose if role != "aside" else []).append(blk)
            continue
        if t == "quote":
            ps = [{"kind": "paragraph", "text": p} for p in e["paragraphs"] if p]
            (wording if role in ("wording", None) else []).extend(ps)
            continue
        if t == "list":
            if role == "aside":
                continue
            (wording if role == "wording" else prose).append({"kind": "bullets", "items": e["items"][:40]})
    body = wording or prose
    # Tables: the answer's own pipes first; else the result tables the tools returned.
    if not tables:
        tables = [b for b in material.get("table_blocks") or [] if b.get("kind") == "table"][:2]
    charts = [b for b in material.get("blocks") or [] if b.get("kind") == "chart"]
    if chart_hints and not charts:
        src = tables or [b for b in material.get("table_blocks") or [] if b.get("kind") == "table"]
        for hint in chart_hints[:1]:
            for tb in src:
                ch = chart_from_table(tb, hint)
                if ch:
                    charts.append(ch)
                    break
    out = [*headings[:1], *body, *tables, *charts[:2]]
    return {"blocks": out, "placement": {"mode": "end"}, "source": "answer"}


def _from_own(b: Any) -> dict[str, Any] | None:
    """A block of a model-written proposal: text | table | chart."""
    if not isinstance(b, dict):
        return None
    k = b.get("kind") or b.get("type")
    if k in ("text", "paragraph"):
        return {"kind": "paragraph", "text": str(b.get("text") or "").lstrip("> ").strip()} if b.get("text") else None
    if k == "heading":
        return {"kind": "heading", "text": _strip_md(str(b.get("text") or "")), "level": 3}
    if k == "bullets":
        return {"kind": "bullets", "items": [str(x) for x in b.get("items") or []][:40]}
    if k == "table":
        if b.get("markdown"):
            el = next((e for e in elements(str(b["markdown"])) if e["type"] == "table"), None)
            return table_from_md(el["header"], el["rows"], str(b.get("title") or "")) if el else None
        if b.get("header") and b.get("rows"):
            return table_from_md([str(x) for x in b["header"]], [[str(c) for c in r] for r in b["rows"]],
                                 str(b.get("title") or ""))
        return None
    if k == "chart" and isinstance(b.get("figure"), dict):
        return {"kind": "chart", "title": str(b.get("title") or ""), "figure": b["figure"]}
    return None


# ------------------------------------------------------------------ placement

_AFTER = re.compile(r"\bafter (the )?(paragraph|para|text|part|sentence|line)s?\b\s*(?:(on|about|that|which|naming|"
                    r"mentioning|covering|with|starting)\b)?\s*(?:(names?|mentions?|covers?|says?|starts? with)\b)?\s*"
                    r"(?P<q>.+)$", re.I)
_REPLACE = re.compile(r"\breplace (the )?(?P<ord>first|second|third|last|opening|\d+(st|nd|rd|th)?)?\s*(paragraph|para|text)"
                      r"\s*(?:(on|about|that|which|naming|mentioning|covering|with)\b)?\s*(?:(names?|mentions?|covers?|says?)\b)?\s*"
                      r"(?P<q>.*)$", re.I)
_START = re.compile(r"\b(at|to) the (start|top|beginning)\b|\bbefore everything\b", re.I)
_ORD = {"first": 0, "opening": 0, "second": 1, "third": 2, "last": -1}


def placement_of(request: str) -> dict[str, Any]:
    """Where the request asks the content to go: end (default), start, after or in place of a paragraph."""
    r = (request or "").strip()
    m = _REPLACE.search(r)
    if m:
        o = (m.group("ord") or "").lower()
        n = _ORD.get(o, int(re.match(r"\d+", o).group(0)) - 1 if re.match(r"\d+", o) else None)  # type: ignore[union-attr]
        q = re.sub(r"\b(with (this|that|it)|by (this|that|it))\b.*$", "", m.group("q") or "", flags=re.I).strip(" .,")
        return {"mode": "replace", **({"index": n} if n is not None else {}), **({"match": q} if q else {})}
    m = _AFTER.search(r)
    if m:
        q = re.sub(r"\b(in|of) (the|this) section\b.*$", "", m.group("q"), flags=re.I).strip(" .,")
        return {"mode": "after", "match": q}
    if _START.search(r):
        return {"mode": "start"}
    return {"mode": "end"}


def _words(s: str) -> set[str]:
    stop = {"the", "a", "an", "of", "on", "in", "and", "to", "for", "about", "that", "this", "with", "is", "are", "by"}
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in stop and len(w) > 1}


def _find_paragraph(blocks: list[dict[str, Any]], place: dict[str, Any]) -> int | None:
    paras = [i for i, b in enumerate(blocks) if b.get("kind") in ("paragraph", "bullets", "callout")]
    if not paras:
        return None
    if "index" in place:
        try:
            return paras[place["index"]]
        except IndexError:
            return None
    want = _words(place.get("match", ""))
    if not want:
        return None
    best, score = None, 0.0
    for i in paras:
        b = blocks[i]
        have = _words(b.get("text") or " ".join(b.get("items") or []))
        s = len(want & have) / len(want)
        if s > score:
            best, score = i, s
    return best if score >= 0.34 else None


# ------------------------------------------------------------------ the merge

_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")


def merge(section_title: str, current: list[dict[str, Any]], proposal: dict[str, Any],
          placement: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], str]:
    """The section's blocks with the proposal merged in, and a sentence saying where it went."""
    place = placement or proposal.get("placement") or {"mode": "end"}
    new = [dict(b) for b in proposal.get("blocks") or []]
    existing_heads = {_norm(b.get("text", "")) for b in current if b.get("kind") == "heading"} | {_norm(section_title)}
    # No duplicate headings: drop a proposed heading the section already has (or the section's own title).
    new = [b for b in new if not (b.get("kind") == "heading" and _norm(b.get("text", "")) in existing_heads)]
    # Numbering: continue the section's heading numbers ("3.1", "3.2" -> "3.3").
    nums = [_NUMBERED.match(b.get("text", "")) for b in current if b.get("kind") == "heading"]
    nums = [m.group(1) for m in nums if m]
    if nums:
        last = nums[-1].split(".")
        for b in new:
            if b.get("kind") == "heading" and not _NUMBERED.match(b["text"]):
                last = [*last[:-1], str(int(last[-1]) + 1)]
                b["text"] = f"{'.'.join(last)} {b['text']}"
    # No duplicate paragraphs or tables: content already in the section is not added twice.
    have = {_norm(b.get("text", "")) for b in current if b.get("kind") == "paragraph"}
    have_tables = {json.dumps([c.get("label") for c in b.get("columns") or []]) + json.dumps(b.get("rows") or [])[:2000]
                   for b in current if b.get("kind") == "table"}
    keep = []
    for b in new:
        if b.get("kind") == "paragraph" and _norm(b.get("text", "")) in have:
            continue
        if b.get("kind") == "table" and (json.dumps([c.get("label") for c in b.get("columns") or []])
                                         + json.dumps(b.get("rows") or [])[:2000]) in have_tables:
            continue
        keep.append(b)
    new = keep
    mode = place.get("mode", "end")
    if mode == "start":
        return [*new, *current], "at the start"
    if mode in ("after", "replace"):
        at = _find_paragraph(current, place)
        if at is not None:
            if mode == "after":
                return [*current[: at + 1], *new, *current[at + 1:]], f"after paragraph {at + 1}"
            return [*current[:at], *new, *current[at + 1:]], f"in place of paragraph {at + 1}"
    return [*current, *new], "at the end"
