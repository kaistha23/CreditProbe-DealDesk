"""PLAN_R11 U4: screenshots of every new Deal Desk surface at 1440x900 (and the overflow probe at 1280x800).

  python ops/r11_ui_shots.py [--ui http://127.0.0.1:5500] [--only optimise,stress,...]

Writes docs/v5/r11_review/*.png and docs/v5/r11_review/u_review.json (overflow and tile checks per surface). Needs the
UI, the Workspace API (identity) and the Deal Desk API running. Mints a session in the identity store; no password or
secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

OUT = V5 / "docs" / "v5" / "r11_review"

PROBE = r"""
(sel) => {
  const root = sel ? document.querySelector(sel) : document.querySelector('main') || document.body;
  if (!root) return {missing: true};
  const vw = window.innerWidth, over = [];
  for (const e of root.querySelectorAll('*')) {
    if (e.offsetParent === null || e.closest('svg')) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > vw + 1) over.push('beyond viewport: ' + e.tagName + ' ' + (e.textContent || '').trim().slice(0, 40));
    const cs = getComputedStyle(e);
    if (e.scrollWidth > e.clientWidth + 2 && cs.overflowX === 'visible' && e.children.length === 0 && (e.textContent || '').trim())
      over.push('text overflow: ' + e.tagName + ' "' + e.textContent.trim().slice(0, 50) + '"');
    if (over.length > 12) break;
  }
  const rough = /TODO|FIXME|lorem|undefined|NaN|\[object Object\]|null\b/.exec(root.innerText || '');
  return {docWidth: document.documentElement.scrollWidth, vw, overflow: over, rough: rough ? rough[0] : null,
          tiles: root.querySelectorAll('[data-kpi-tile]').length};
}
"""


def mint() -> str:
    from r10_chat_audit import session  # mints a session in the identity store (no password)
    return session()


def wait_idle(page: Page, ms: int = 800) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:  # noqa: BLE001 - a long poll keeps the network busy; fall back to a pause
        pass
    page.wait_for_timeout(ms)


def shot(page: Page, name: str, report: list, sel: str | None = None) -> None:
    if sel:
        el = page.locator(sel).last
        if el.count():
            el.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f"{name}.png"))
    if sel and page.locator(sel).last.count():
        page.locator(sel).last.screenshot(path=str(OUT / f"{name}_panel.png"))
    r = page.evaluate(PROBE, sel)
    r["surface"] = name
    report.append(r)
    print(name, "overflow" if r.get("overflow") else "ok", r.get("rough") or "")


def deal(page: Page, ui: str, pid: str, step: str | None = None) -> None:
    page.goto(f"{ui}/deal-desk/{pid}" + (f"?step={step}" if step else ""))
    page.wait_for_selector('[data-testid="dealdesk-stepper"]', timeout=120000)
    wait_idle(page)


def optimise(page: Page) -> None:
    if page.locator('[data-testid="dealdesk-optimise-view"]').count():
        return
    page.click('[data-testid="dealdesk-optimise"]')
    page.wait_for_selector('[data-testid="dealdesk-optimise-view"]', timeout=180000)
    wait_idle(page, 1500)


def ask(page: Page, q: str) -> None:
    n = page.locator('[data-testid="dealdesk-turn"]').count()
    page.fill('[data-testid="dealdesk-composer"]', q)
    page.click('[data-testid="dealdesk-send"]')
    page.wait_for_function(f"document.querySelectorAll('[data-testid=\"dealdesk-turn\"]').length > {n}", timeout=180000)
    page.wait_for_timeout(1200)


def run(ui: str, only: set[str]) -> list:
    OUT.mkdir(parents=True, exist_ok=True)
    report: list = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h, tag in ((1440, 900, ""), (1280, 800, "_1280")):
            ctx = b.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": mint(), "domain": "127.0.0.1", "path": "/", "httpOnly": True, "sameSite": "Lax"}])
            page = ctx.new_page()
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(str(e)[:200]))
            if not only or "optimise" in only:
                deal(page, ui, "DD-01")
                optimise(page)
                shot(page, f"u01_dd01_optimise_structures{tag}", report, '[data-testid="dealdesk-optimise-view"]')
                shot(page, f"u02_dd01_forward_risk{tag}", report, '[data-testid="dealdesk-panel-forward"]')
                shot(page, f"u03_dd01_stress_summary{tag}", report, '[data-testid="dealdesk-panel-stress"]')
                shot(page, f"u04_dd01_pipeline_test{tag}", report, '[data-testid="dealdesk-panel-pipeline"]')
                btn = page.locator('[data-testid="dealdesk-pipeline-test-button"]').first
                if btn.count() and btn.is_enabled():
                    btn.click()
                    try:
                        page.wait_for_selector('[data-testid="dealdesk-pipeline-test-result"]', timeout=240000)
                    except Exception as e:  # noqa: BLE001
                        report.append({"surface": "pipeline test result", "error": str(e)[:200]})
                    page.wait_for_timeout(800)
                    shot(page, f"u05_dd01_pipeline_test_result{tag}", report, '[data-testid="dealdesk-panel-pipeline"]')
            if not only or "stress" in only:
                deal(page, ui, "DD-06")
                optimise(page)
                deal(page, ui, "DD-06", "stress")
                wait_idle(page, 2500)
                shot(page, f"u06_dd06_stress_step{tag}", report, '[data-testid="dealdesk-step-stress-view"]')
            if not only or "review" in only:
                for pid, label in (("DD-01", "dd01"), ("DD-05", "dd05"), ("DD-02", "dd02")):
                    deal(page, ui, pid)
                    optimise(page)
                    deal(page, ui, pid, "review")
                    wait_idle(page, 2500)
                    shot(page, f"u07_{label}_review_step{tag}", report, '[data-testid="dealdesk-step-review-view"]')
            if not only or "landing" in only:
                page.goto(f"{ui}/deal-desk")
                page.wait_for_selector('[data-testid="dealdesk-mode"]', timeout=120000)
                wait_idle(page, 1500)
                shot(page, f"u08_landing_conditions_due{tag}", report, '[data-testid="dealdesk-mode"]')
            if not tag and (not only or "thread" in only):
                deal(page, ui, "DD-01")
                for i, q in enumerate(["What is the chance of Stage 2 next quarter?", "Run early warning on this deal",
                                       "Stress this deal with oil −30%", "What breaks first?", "Test against pipeline",
                                       "Optimise the pipeline", "Review the memo", "Draft the committee sheet"]):
                    try:
                        ask(page, q)
                        shot(page, f"u1{i}_thread_{q.split()[0].lower()}_{i}", report, '[data-testid="dealdesk-turn"]')
                    except Exception as e:  # noqa: BLE001
                        report.append({"surface": f"thread {q}", "error": str(e)[:200]})
                    deal(page, ui, "DD-01")
            report.append({"viewport": f"{w}x{h}", "page_errors": errs})
            ctx.close()
        b.close()
    (OUT / "u_review.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    t = time.time()
    run(a.ui, {x for x in a.only.split(",") if x})
    print(f"done in {time.time() - t:.0f}s")
