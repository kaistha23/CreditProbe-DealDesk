#!/usr/bin/env python3
"""FX-2 in the browser: re-open the answers the A/B re-run published.

Costs no model call. For every run of the given build in
evidence/v5/cockpit/ask_runs.jsonl it reads the published answer from the
Cockpit API, opens its thread in the v5 UI, and checks:
  - every bar and grouped-bar chart is drawn in exactly the published order;
  - a chart FX-2 put in order is drawn largest first by its charted measure;
  - no console errors and no failed requests.

    <workspace>/.venv/bin/python ops/fx2_chart_check.py [build-label]
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

V5 = Path(__file__).resolve().parents[1]
LOG = V5 / "evidence" / "v5" / "cockpit" / "ask_runs.jsonl"
UI = "http://127.0.0.1:5500"
API = "http://127.0.0.1:8500/api/v1/cockpit-v4"


def run_of(run_id: str) -> dict:
    with urllib.request.urlopen(f"{API}/runs/{run_id}", timeout=30) as r:
        return json.loads(r.read())


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "v5-fx2"
    runs = [json.loads(x) for x in LOG.open() if json.loads(x)["build"] == label]
    checks, failed = 0, 0

    def check(ok: bool, what: str) -> None:
        nonlocal checks, failed
        checks += 1
        failed += not ok
        print(("PASS " if ok else "FAIL ") + what, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for r in runs:
            record = run_of(r["run_id"])
            published = record.get("final_response") or {}
            charts = [c for c in published.get("charts") or []
                      if c.get("kind") in ("bar", "grouped_bar") and c.get("points")]
            page = browser.new_page()
            errors: list[str] = []
            page.on("console", lambda m: m.type == "error" and errors.append(m.text[:200]))
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.on("requestfailed", lambda q: errors.append("request failed " + q.url[:160]))
            page.goto(f"{UI}/cockpit/thread/{record['thread_id']}", wait_until="networkidle",
                      timeout=180_000)
            page.wait_for_timeout(2000)
            drawn = page.evaluate("""() => [...document.querySelectorAll('[data-testid=v4-result-chart]')]
              .map(f => ({kind: f.dataset.kind, labels: [...f.querySelectorAll(
                '[data-testid=v4-chart-bars] > li > span:first-child, [data-testid=v4-chart-grouped] > ol > li > span:first-child')]
                .map(s => s.textContent.trim())}))""")
            drawn = [d for d in drawn if d["kind"] in ("bar", "grouped_bar")]
            q = r["question_id"]
            check(len(drawn) == len(charts), f"{q}: {len(charts)} bar chart(s) published, {len(drawn)} drawn")
            for c, d in zip(charts, drawn):
                want = [str(pt.get("label")) for pt in c["points"]]
                check(d["labels"] == want, f"{q}: '{c.get('title')}' drawn in the published order")
                order = c.get("presentation_order")
                if order:
                    vals = [float(pt["values"][order["column"]]) for pt in c["points"]]
                    check(vals == sorted(vals, reverse=True),
                          f"{q}: FX-2 put '{c.get('title')}' largest first by {order['column']}")
            check(not errors, f"{q}: no console errors or failed requests {errors[:2]}")
            page.close()
        browser.close()
    print(f"FX-2 browser check: {checks - failed}/{checks} checks passed over {len(runs)} answers")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
