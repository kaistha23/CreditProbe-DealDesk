"""List every banned label (plan R2 section 0) a signed-in Administrator sees, route by route.

The sweep (`ops/uat_sweep.py --only labels`) fails on the first two hits of a screen; this prints all of them,
with their context, so a clean-up can be finished in one pass.   Usage:  .venv/bin/python ops/label_scan.py [route ...]
"""
from __future__ import annotations

import re
import sys

import core_login
from playwright.sync_api import sync_playwright

UI = "http://127.0.0.1:5500"
BANNED = re.compile(r"synthetic|(?<![\w-])demo(?![\w-])|demo[- ]data", re.I)
TEXT = """() => {
  const t = [document.title, document.body ? document.body.innerText : ""];
  document.querySelectorAll('[title],[aria-label],[placeholder],[alt]').forEach(e => {
    for (const a of ['title', 'aria-label', 'placeholder', 'alt']) t.push(e.getAttribute(a) || '');
  });
  return t.join('\\n');
}"""
ROUTES = ["/", "/workspace", "/messages", "/messages?folder=all", "/analyses/ead-by-sector-2026q2",
          "/investigations/construction-ecl-rise-q2-2026", "/projects/construction-deep-dive-q2-2026",
          "/projects/construction-deep-dive-q2-2026/threads/pt-construction-why", "/projects", "/investigations", "/analyses", "/playbook", "/playbook?report=rp_ccp_q2_2026", "/policy-docs",
          "/policy-docs?doc=pd_circ_c_2026_03", "/early-warning",
          "/early-warning?domain=retail", "/early-warning/model", "/what-if", "/deal-desk", "/deal-desk/DD-01", "/borrower-360",
          "/borrower-360?domain=corporate&customer_id=CB01312&period=2026Q2&tab=profile",
          "/borrower-360?domain=retail&customer_id=RC000001&period=2026-08&tab=profile",
          "/data-builder", "/trace", "/workflow", "/agent-operations", "/ai-studio", "/ai-studio/brain-center",
          "/ai-studio/continuous-learning", "/ai-studio/feedback-learning", "/users", "/settings", "/stress",
          "/scorecard-validation", "/lenses", "/lenses/cro", "/playbooks", "/studio", "/studio/regulatory-intelligence",
          "/engine-builder", "/cockpit/data"]


def main() -> int:
    routes = sys.argv[1:] or ROUTES
    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(ctx, "anne")
        page = ctx.new_page()
        page.set_default_timeout(60_000)
        for route in routes:
            page.goto(UI + route, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(600)
            text = page.evaluate(TEXT)
            hits = sorted({text[max(0, m.start() - 45):m.end() + 45].replace("\n", " ") for m in BANNED.finditer(text)})
            total += len(hits)
            print(f"{route}: {len(hits)}")
            for h in hits:
                print("    ", h)
        browser.close()
    print(f"\n{total} distinct hits")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
