"""Rating order sweep check (PLAN_R6 E3, screen 16).

Every rating axis, legend, table and dropdown reads in the global order AAA, AA+, AA, AA-, ... CCC, CC, C, D
(backend/v5common/ratings.py), never sorted by value. This module flags any rendered label sequence whose
grades run out of that order.

    from ops.rating_order_scan import scan_sequences, scan_page
    scan_sequences({"ews table": ["AAA", "BB", "A"]})          -> [{"where": "ews table", ...}]
    scan_page(page, "Early Warning")                            -> the same, read from a Playwright page

A sequence is checked only when it is a rating sequence (at least two grades, anything else a total-like row),
so a borrower list that merely shows a rating column is not flagged.

    .venv/bin/python ops/rating_order_scan.py sequences.json    exit 1 when a sequence is out of order
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.v5common import ratings  # noqa: E402

# Collects, from the rendered page: the first column of every table, every Plotly category axis (tick labels
# in drawn order), every Plotly legend, and the options of every <select>.
JS_COLLECT = r"""
() => {
  const out = [];
  const txt = (e) => (e.textContent || "").trim();
  document.querySelectorAll("table").forEach((t, i) => {
    const col = [...t.querySelectorAll("tbody tr")].map((r) => r.cells[0] ? txt(r.cells[0]) : "");
    out.push({ where: `table ${i + 1}` + (t.dataset.testid ? ` (${t.dataset.testid})` : ""), labels: col });
  });
  document.querySelectorAll(".js-plotly-plot").forEach((p, i) => {
    const name = p.closest("[data-testid]")?.getAttribute("data-testid") || `chart ${i + 1}`;
    ["xtick", "ytick"].forEach((k) => {
      const ticks = [...p.querySelectorAll(`g.${k} text`)];
      const pos = (e) => { const r = e.getBoundingClientRect(); return k === "xtick" ? r.left : r.top; };
      ticks.sort((a, b) => pos(a) - pos(b));
      out.push({ where: `${name} ${k === "xtick" ? "x" : "y"} axis`, labels: ticks.map(txt) });
    });
    out.push({ where: `${name} legend`, labels: [...p.querySelectorAll("g.legend .legendtext")].map(txt) });
  });
  document.querySelectorAll("select").forEach((s, i) => {
    out.push({ where: `dropdown ${s.getAttribute("data-testid") || s.name || i + 1}`, labels: [...s.options].map(txt) });
  });
  return out;
}
"""


def is_rating_sequence(labels: Iterable[Any]) -> bool:
    return ratings.is_rating_values(labels)


def check_sequence(labels: Iterable[Any]) -> dict[str, Any] | None:
    """None when the sequence is fine (or not a rating sequence); else what is wrong and the expected order."""
    seq = [str(v).strip() for v in labels if v is not None]
    if not is_rating_sequence(seq) or ratings.in_order(seq):
        return None
    grades = [v for v in seq if ratings.is_grade(v)]
    return {"found": grades, "expected": ratings.axis_order(grades)}


def scan_sequences(seqs: Mapping[str, Iterable[Any]] | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every rating sequence out of the global order, as {"where", "found", "expected"}."""
    items = ([{"where": k, "labels": v} for k, v in seqs.items()] if isinstance(seqs, Mapping) else list(seqs))
    out = []
    for it in items:
        bad = check_sequence(it.get("labels") or [])
        if bad:
            out.append({"where": it.get("where", ""), **bad})
    return out


def scan_page(page: Any, where: str = "") -> list[dict[str, Any]]:
    """Read the tables, chart axes, legends and dropdowns of a Playwright page and flag rating disorder."""
    found = page.evaluate(JS_COLLECT)
    return [{**f, "where": f"{where}: {f['where']}" if where else f["where"]} for f in scan_sequences(found)]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    bad = scan_sequences(json.loads(Path(argv[1]).read_text()))
    for b in bad:
        print(f"OUT OF ORDER  {b['where']}: {' '.join(b['found'])}  (expected {' '.join(b['expected'])})")
    print(f"rating order: {len(bad)} sequence(s) out of order")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
