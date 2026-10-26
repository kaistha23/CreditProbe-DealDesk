"""G5 (PLAN_R5, extended in PLAN_R6 E2): no raw numbers anywhere.

Fails on:
  - any VISIBLE number with more than 4 decimals on the page (thread answers and chat included);
  - any TABLE CELL whose text holds a raw float (more than 4 decimals), in every table on the page, visible or not
    (collapsed panels, hidden tabs and folded thread turns count);
  - any THREAD ANSWER (answer blocks, turns, commentary, markdown) whose text holds a raw float, folded or not;
  - a share shown as a fraction (0.xx in a column whose header says share, %, rate, coverage, RAROC... where a
    percentage is meant);
  - a raw key used as a table header (`HEADROOM_SHARE`, `ead_sar_mn`);
  - a column with a header and not one filled cell (a yes/no column rendered from booleans shows nothing in React:
    the R6 screen 09 "Clears hurdle" column).
Every tab (`[role=tab]`) on a route is clicked in turn and the scan repeated, so each tab is scanned.
Plotly traces whose hover would show a long raw decimal (no hovertemplate and no x/y hover format) are listed as
an inventory (not a failure: the shared Plot wrapper formats them, PLAN_R6 E2).

    .venv/bin/python ops/raw_number_scan.py [route ...]     prints the hits, exit 1 if any (Deal Desk included)
    .venv/bin/python ops/raw_number_scan.py --no-tabs ...   the screen as it opens only
The sweep part "r5-threads" (ops/sweep_r5_threads.py) runs the same scan, thread screens included, and writes
evidence/v5/r5/g5_raw_numbers.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
UI = "http://127.0.0.1:5500"

LONG_DECIMAL = re.compile(r"(?<![\d.])-?\d+\.\d{5,}(?![\d.])")

#: Deal Desk screens were Session D's in R5 (scanned, not failed). PLAN_R6 E2 makes them fail like every other
#: screen; the constant stays for the sweeps that still report them apart.
DEALDESK = re.compile(r"^/deal-desk")

#: At most this many tabs are clicked per route.
MAX_TABS = 12

SCAN = r"""() => {
  const visible = (el) => { const r = el.getBoundingClientRect(); const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none'; };
  const LONG = /(^|[^\d.])-?\d+\.\d{5,}(?![\d.])/;
  const text = document.body ? document.body.innerText : '';
  const fractions = [], keys = [], cells = [], empty = [], answers = [];
  const pctHead = /share|%|percent|rate|coverage|utili[sz]ation|ltv|raroc|hurdle|weight|probability|\bpd\b|\blgd\b/i;
  const notPct = /\(sar|sar m|sar bn|bps|count|number|days|score|notch|\bn\b|ratio|dscr|\(x\)|clears|yes\/no/i;
  for (const table of document.querySelectorAll('table')) {
    const title = ((table.closest('[data-testid]') || {getAttribute: () => ''}).getAttribute('data-testid') || 'table');
    const heads = Array.from(table.querySelectorAll('thead th, tr:first-child th'));
    const body = Array.from(table.querySelectorAll('tbody tr'));
    // Every cell of every table, shown or not.
    for (const tr of body) for (const td of Array.from(tr.children)) {
      const v = (td.textContent || '').trim();
      if (LONG.test(v)) { const ci = Array.from(tr.children).indexOf(td);
        cells.push(`${title} · ${((heads[ci] || {}).textContent || '').trim() || 'column ' + (ci + 1)}: ${v.slice(0, 40)}`); }
    }
    if (!visible(table)) continue;
    heads.forEach((th) => {
      const raw = (th.textContent || '').trim();
      if (/^[A-Za-z0-9]+(_[A-Za-z0-9]+)+$/.test(raw)) keys.push(raw);
    });
    heads.forEach((th, ci) => {
      const h = (th.textContent || '').trim();
      if (h && body.length >= 2 && body.every((tr) => tr.children.length === heads.length && !((tr.children[ci] || {}).textContent || '').trim())) {
        empty.push(`${title} · ${h}`);
      }
      if (!pctHead.test(h) || notPct.test(h)) return;
      for (const tr of body) {
        const td = tr.children[ci];
        if (!td) continue;
        const v = (td.textContent || '').trim();
        if (/^[-−]?0\.\d{2,}$/.test(v)) { fractions.push(`${h}: ${v}`); break; }
      }
    });
  }
  // Thread answers, folded or not: their whole text, tables and prose.
  const ans = '[data-testid*=answer],[data-testid*=turn],[data-testid*=commentary],[data-testid*=markdown],[data-testid*=message]';
  for (const el of document.querySelectorAll(ans)) {
    if (el.parentElement && el.parentElement.closest(ans)) continue;
    const t = el.textContent || '';
    const m = t.match(/-?\d+\.\d{5,}(?![\d.])/);
    if (m && LONG.test(t)) answers.push(`${el.getAttribute('data-testid')}: ${t.slice(Math.max(0, m.index - 40), m.index + m[0].length + 10).replace(/\s+/g, ' ')}`);
  }
  const plots = [];
  for (const gd of document.querySelectorAll('.js-plotly-plot')) {
    for (const tr of (gd.data || [])) {
      if (tr.hovertemplate || tr.hoverinfo === 'skip' || tr.hoverinfo === 'none') continue;
      const vals = [...(tr.yhoverformat ? [] : Array.from(tr.y || [])), ...(tr.xhoverformat ? [] : Array.from(tr.x || []))].flat(2);
      const bad = vals.find((v) => typeof v === 'number' && Math.abs(v - Math.round(v * 10000) / 10000) > 1e-12);
      if (bad !== undefined) { plots.push(`${tr.name || 'trace'}: ${bad}`); }
    }
  }
  return { text, fractions, keys, cells, empty, answers, plots };
}"""

#: The tabs of a screen, each with a selector the scan can click.
TABS = r"""() => Array.from(document.querySelectorAll('[role=tab]')).filter((t) => {
  const r = t.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !t.disabled;
}).map((t, i) => { t.setAttribute('data-g5-tab', String(i)); return { i, label: (t.textContent || '').trim().slice(0, 40),
  selected: t.getAttribute('aria-selected') === 'true' || t.getAttribute('data-state') === 'active' }; })"""


def long_decimals(text: str) -> list[str]:
    out = []
    for m in LONG_DECIMAL.finditer(text):
        out.append(text[max(0, m.start() - 40):m.end() + 20].replace("\n", " "))
    return sorted(set(out))


def from_raw(r: dict) -> dict:
    """The scan result of one evaluation of SCAN (pure: unit-tested in tests/v5/test_raw_number_scan.py)."""
    return {"long_decimals": long_decimals(r.get("text") or ""), "fractions": sorted(set(r.get("fractions") or [])),
            "raw_keys": sorted(set(r.get("keys") or [])), "table_cells": sorted(set(r.get("cells") or [])),
            "empty_columns": sorted(set(r.get("empty") or [])), "thread_answers": sorted(set(r.get("answers") or [])),
            "plot_hover_inventory": sorted(set(r.get("plots") or []))[:20]}


def merge(a: dict, b: dict) -> dict:
    """Two scans of one route (two tabs) as one."""
    out = {}
    for k in set(a) | set(b):
        out[k] = sorted(set(a.get(k) or []) | set(b.get(k) or []))
    out["plot_hover_inventory"] = out.get("plot_hover_inventory", [])[:20]
    return out


def scan_page(page) -> dict:
    return from_raw(page.evaluate(SCAN))


def scan_tabs(page, settle_ms: int = 600) -> dict:
    """The page as it is, then every tab on it clicked in turn (PLAN_R6 E2: every tab)."""
    r = scan_page(page)
    try:
        tabs = page.evaluate(TABS)
    except Exception:  # noqa: BLE001
        tabs = []
    for t in [t for t in tabs if not t["selected"]][:MAX_TABS]:
        try:
            page.click(f"[data-g5-tab='{t['i']}']", timeout=3_000)
            page.wait_for_timeout(settle_ms)
            r = merge(r, scan_page(page))
        except Exception:  # noqa: BLE001  (a tab that re-rendered away is skipped)
            continue
    return r


def failures(r: dict) -> list[str]:
    hits = list(r.get("long_decimals") or [])
    hits += [f"raw float in a table cell · {x}" for x in r.get("table_cells") or []]
    hits += [f"raw float in a thread answer · {x}" for x in r.get("thread_answers") or []]
    hits += [f"share as a fraction · {x}" for x in r.get("fractions") or []]
    hits += [f"raw key header · {x}" for x in r.get("raw_keys") or []]
    hits += [f"empty column · {x}" for x in r.get("empty_columns") or []]
    return hits


def main() -> int:
    sys.path.insert(0, str(V5 / "ops"))
    import core_login
    from loose_text_scan import ROUTES, settle
    from playwright.sync_api import sync_playwright

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tabs = "--no-tabs" not in sys.argv
    routes = args or ROUTES
    bad, report = 0, {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(ctx, "anne")
        page = ctx.new_page()
        page.set_default_timeout(60_000)
        for route in routes:
            page.goto(UI + route, wait_until="domcontentloaded")
            settle(page)
            r = scan_tabs(page) if tabs else scan_page(page)
            report[route] = r
            hits = failures(r)
            bad += len(hits)
            print(f"{route}: {len(hits)} raw-number hits")
            for h in hits[:10]:
                print("   ", h)
        browser.close()
    out = V5 / "var" / "raw_number_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(f"\n{bad} raw-number hits; report in {out.relative_to(V5)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
