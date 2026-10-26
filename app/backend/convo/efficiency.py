"""Round E: fewer model calls and fewer input tokens per question, with the same figures.

Measured before this round (Opus, the 21 golden Deal Desk questions): 4.9 model calls and about 38k input tokens per
question. Five measures, each switchable off with `CONVO_EFFICIENCY=off` (the lab's "before" run, and a kill switch):

  1. Prompt caching (Anthropic). The stable head of the system prompt (charter, discipline, schema digest, worked
     examples) and the tool schemas are marked `cache_control: ephemeral`; the per-question tail (thread context,
     policy retrieved for the question, earlier turns) follows the break. Inside the analysis loop the last message is
     marked too, so each later step of the same turn reads the earlier steps from the cache. The OpenAI-compatible
     provider strips the break and sends one system string (no-op: vLLM and llama.cpp cache prefixes on their own).
  2. Engine first, then one writing call. For a question the domain's deterministic planner knows (`register(...,
     fast=...)`), the planner's tool calls run without the model, the planner's writer composes the engine's draft,
     and the model is called once to write the answer from the results and the draft (only `finalize_answer`
     offered). A model text with a figure that is not in the results, or that drops a figure of the draft's
     headline (its first line with a figure), is not published: the engine's draft is (no second call).
  3. A compact schema digest (relation, rows, grain, columns; a description only where one is given) and the
     domain's worked examples in place of the full typed catalog, for free-form questions.
  4. At most 20 result rows reach the model per tool call, with a summary of the whole result (row count, and per
     numeric column the total, minimum and maximum, which go into the turn's evidence); nested lists longer than 20
     are cut the same way. The artifact, the tables and the validator keep every row.
  5. History: the last 2 turns verbatim (answers cut at 1,200 characters), up to 10 earlier turns as one line each
     in the system prompt's tail.

Nothing here computes a figure the answer may quote except the column totals, minima and maxima of a result, which
the validator already accepts as arithmetic over cells (validate.py).
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

# A marker between the cacheable head of a system prompt and its per-question tail. Never shown to a model.
BREAK = "\n\n\x1f\x1f CACHE-BREAK \x1f\x1f\n\n"
MODEL_ROWS = 20
HISTORY_VERBATIM = 2
HISTORY_DIGEST = 10
ANSWER_CHARS = 1200
CACHE = {"type": "ephemeral"}
WRITE_PURPOSE = "ENGINE_FIRST_WRITE"
# calls that are followed by another call of the same turn: the last message is worth caching
LOOP_PURPOSES = ("ANALYSIS_ACTION", "ANSWER_CORRECTION")


def enabled() -> bool:
    return (os.environ.get("CONVO_EFFICIENCY") or "on").strip().lower() not in ("off", "0", "false", "no")


# ------------------------------------------------------------------ the domain hooks (engine first, worked examples)

@dataclass
class Hooks:
    #: (question, ToolContext) -> True when the deterministic planner knows this question type
    fast: Callable[[str, Any], bool] | None = None
    #: worked examples for free-form questions (question -> the calls that answer it), plain text
    examples: str = ""


_HOOKS: dict[str, Hooks] = {}


def register(domain_key: str, *, fast: Callable[[str, Any], bool] | None = None, examples: str = "") -> None:
    _HOOKS[domain_key] = Hooks(fast=fast, examples=examples)


def hooks(domain_key: str) -> Hooks:
    return _HOOKS.get(domain_key) or Hooks()


def engine_first(domain_key: str, question: str, ctx: Any) -> bool:
    h = hooks(domain_key)
    if not enabled() or h.fast is None:
        return False
    try:
        return bool(h.fast(question, ctx))
    except Exception:  # noqa: BLE001 - an unknown question goes to the model loop
        return False


# ------------------------------------------------------------------ system prompt: head | tail

def split(system: str) -> tuple[str, str]:
    head, sep, tail = (system or "").partition(BREAK)
    return (head, tail) if sep else (system or "", "")


def plain(system: str) -> str:
    """The system prompt as one string (OpenAI-compatible servers, logs, scripted providers)."""
    return (system or "").replace(BREAK, "\n\n")


def catalog_digest(catalog: list[dict[str, Any]]) -> str:
    """Relation, rows, grain, then the column names; a column's description only where the domain wrote one."""
    lines = []
    for r in catalog:
        cols = []
        for c in r["columns"]:
            d = (c.get("description") or "").strip()
            cols.append(f"{c['name']} ({d[:80]})" if d else c["name"])
        lines.append(f"- {r['relation']} ({r['rows']:,} rows, one per {r.get('grain') or 'record'}): {r.get('description', '')}\n"
                     f"  columns: {', '.join(cols)}")
    return "\n".join(lines)


def history_split(history: list[dict[str, Any]], answer_text: Callable[[dict], str]) -> tuple[list[dict[str, Any]], str]:
    """(the recent turns sent verbatim, one line per earlier turn for the system prompt's tail)."""
    turns = [t for t in history or [] if str(t.get("question") or "").strip()]
    recent = turns[-HISTORY_VERBATIM:] if HISTORY_VERBATIM else []
    older = turns[:-HISTORY_VERBATIM][-HISTORY_DIGEST:] if HISTORY_VERBATIM else turns[-HISTORY_DIGEST:]
    lines = []
    for t in older:
        a = re.sub(r"\s+", " ", answer_text(t.get("answer") or {})).strip()
        first = re.split(r"(?<=[.!?])\s", a, maxsplit=1)[0][:160] if a else ""
        lines.append(f"- Q: {str(t['question']).strip()[:140]} | A: {first}")
    return recent, ("Earlier in this thread (one line per turn; their figures are not evidence for this turn):\n"
                    + "\n".join(lines)) if lines else ""


# ------------------------------------------------------------------ tool results as the model sees them

def _numeric_summary(columns: list[str], rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for c in columns:
        vals = [r.get(c) for r in rows if isinstance(r, dict)]
        nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums and len(nums) == len([v for v in vals if v is not None]) and not c.lower().endswith("_id"):
            out[c] = {"total": round(sum(nums), 6), "min": round(min(nums), 6), "max": round(max(nums), 6)}
    return out


def _cut(x: Any, depth: int = 0) -> Any:
    if isinstance(x, list) and len(x) > MODEL_ROWS:
        return [_cut(v, depth + 1) for v in x[:MODEL_ROWS]] + [f"... {len(x) - MODEL_ROWS} more not shown ({len(x)} in all)"]
    if isinstance(x, list):
        return [_cut(v, depth + 1) for v in x]
    if isinstance(x, dict) and depth < 6:
        return {k: _cut(v, depth + 1) for k, v in x.items()}
    return x


def model_view(out: dict[str, Any], full_rows: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """(what the model sees of a tool result, the summary to add to the evidence or None).

    Rows beyond 20 are replaced by a summary of the whole result; `full_rows` (the artifact's rows) is what the
    summary is computed on when the tool already cut what it returned."""
    view = copy.copy(out)
    rows = full_rows if full_rows is not None else out.get("rows")
    summary = None
    if isinstance(rows, list) and len(rows) > MODEL_ROWS:
        cols = list(out.get("columns") or (rows[0].keys() if rows and isinstance(rows[0], dict) else []))
        summary = {"row_count": len(rows), "rows_shown": MODEL_ROWS, "column_summary": _numeric_summary(cols, rows)}
        view["rows"] = list((out.get("rows") or rows)[:MODEL_ROWS])
        view["rows_summary"] = summary
        view.pop("note", None)
    if "data" in view:
        view["data"] = _cut(view["data"])
    return view, summary


def tool_content(out: dict[str, Any], limit: int = 24000) -> str:
    return json.dumps(out, default=str, separators=(",", ":"))[:limit]


# ------------------------------------------------------------------ Anthropic request with cache breakpoints

def anthropic_request(system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]], purpose: str = "") -> dict[str, Any]:
    """The `system`, `tools` and `messages` arguments of messages.create, with cache_control on the stable head of the
    system prompt, the last tool schema, and (for a loop step that another step follows) the last message."""
    if not enabled():
        return {"system": plain(system), "tools": tools, "messages": messages}
    head, tail = split(system)
    sys_blocks: list[dict[str, Any]] = []
    if head.strip():
        sys_blocks.append({"type": "text", "text": head, "cache_control": CACHE})
    if tail.strip():
        sys_blocks.append({"type": "text", "text": tail})
    t2 = [dict(t) for t in tools or []]
    if t2:
        t2[-1] = {**t2[-1], "cache_control": CACHE}
    m2 = messages
    if purpose in LOOP_PURPOSES and messages:
        m2 = [dict(m) for m in messages]
        last = m2[-1]
        content = last.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        else:
            content = [dict(b) for b in content or []]
        if content:
            content[-1] = {**content[-1], "cache_control": CACHE}
            m2[-1] = {**last, "content": content}
    return {"system": sys_blocks or plain(system), "tools": t2, "messages": m2}


def usage_row(usage: Any) -> dict[str, Any]:
    """Cache counters as separate telemetry fields (the sqlite keeps their sum as cached_tokens)."""
    read = getattr(usage, "cache_read_input_tokens", None) or 0
    made = getattr(usage, "cache_creation_input_tokens", None) or 0
    return {"cache_read_tokens": read or None, "cache_creation_tokens": made or None}


# ------------------------------------------------------------------ the one writing call

def writer_system(charter: str, scope_label: str, rules: str) -> str:
    head = (f"{charter}\n\nYou are writing the answer to one question on {scope_label}. The engine has already run "
            "every calculation the question needs; its results and its own draft answer are in the user message. "
            "Write the answer for a bank's credit committee and publish it with finalize_answer, once.\n\n"
            "Rules: every figure you write must appear in the results or in the engine's draft, written exactly as "
            "there (same rounding, same unit); add no figure, never compute, estimate or recall a number. Keep every "
            "figure of the draft's first line that has figures. Lead with the direct answer in one line, then the evidence in short "
            "paragraphs or bullets; no filler, no disclaimers, no notes about provenance. Do not repeat the tables "
            "(they are published with the answer); refer to them. Up to 4 follow-up suggestions in the banker's words. "
            + rules)
    return head + BREAK


WRITER_RESULT_CHARS = 10000


def _note(v: Any) -> int | None:
    m = re.match(r"\.\.\. \d+ more not shown \((\d+) in all\)$", v) if isinstance(v, str) else None
    return int(m.group(1)) if m else None


def shrink(x: Any, budget: int) -> Any:
    """Halve the longest list (anywhere in the structure) until the JSON fits the budget; each cut list ends with a
    note of how many items it had. For the writing call only: the evidence keeps the full result."""
    x = copy.deepcopy(x)
    size = lambda v: len(json.dumps(v, default=str, separators=(",", ":")))  # noqa: E731
    for _ in range(40):
        if size(x) <= budget:
            break
        best: list[Any] = [0, None]

        def walk(v: Any) -> None:
            if isinstance(v, list):
                items = [i for i in v if _note(i) is None]
                if len(items) > 1 and size(v) > best[0]:
                    best[0], best[1] = size(v), v
                for i in v:
                    walk(i)
            elif isinstance(v, dict):
                for i in v.values():
                    walk(i)
        walk(x)
        lst = best[1]
        if lst is None:
            break
        items = [i for i in lst if _note(i) is None]
        orig = next((_note(i) for i in lst if _note(i) is not None), len(items))
        keep = items[:max(1, len(items) // 2)]
        lst[:] = keep + [f"... {orig - len(keep)} more not shown ({orig} in all)"]
    return x


def writer_message(question: str, results: list[dict[str, Any]], draft: str) -> str:
    compact = []
    for r in results:
        view, _ = model_view(r.get("out") or {})
        compact.append({"tool": r.get("tool"), "args": r.get("args"), "error": bool(r.get("error")),
                        "result": shrink(view, WRITER_RESULT_CHARS)})
    return json.dumps({"question": question, "engine_results": compact, "engine_draft": draft}, default=str,
                      ensure_ascii=False, separators=(",", ":"))[:60000]


def headline_figures(markdown: str) -> list[str]:
    from backend.convo.validate import numbers
    lines = [ln for ln in (markdown or "").splitlines() if ln.strip()][:4]
    first = next((ln for ln in lines if numbers(ln)), "")
    return [tok for tok, _, _ in numbers(first)]


def keeps_headline(draft: str, text: str) -> list[str]:
    """The figures of the draft's headline (its first line with a figure, among the first four) that the model's
    text dropped (empty = kept)."""
    from backend.convo.validate import numbers
    have = {tok for tok, _, _ in numbers(text or "")}
    return [t for t in headline_figures(draft) if t not in have]
