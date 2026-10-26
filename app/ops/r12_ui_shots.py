"""PLAN_R12 Session U: screenshots of the Deal Desk shell at 1440x900 and 1280x800, with an overflow probe.

  python ops/r12_ui_shots.py [--ui http://127.0.0.1:5500]

Writes docs/v5/r12_ui/*.png and docs/v5/r12_ui/u_shots.json. Needs the UI, the Workspace API (identity) and the Deal
Desk API running. Mints a session in the identity store; no password or secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r12_ui"
SIZES = [(1440, 900), (1280, 800)]

SURFACES: list[tuple[str, str, str | None, str | None]] = [
    # name, path, element to wait for, element to click first
    ("landing", "/deal-desk", '[data-testid="dealdesk-cards-row"]', None),
    ("landing-card-list", "/deal-desk?card=to_review", '[data-testid="dealdesk-card-list"]', None),
    ("tab-book", "/deal-desk?tab=book", '[data-testid="dealdesk-tab-book-panel"]', None),
    ("tab-params", "/deal-desk?tab=params", '[data-testid="dealdesk-tab-params-panel"]', None),
    ("pipeline-mode", "/deal-desk?mode=pipeline", '[data-testid="dealdesk-pipeline-deals"]', None),
    ("deal-dd-proposal", "/deal-desk/DD-01", '[data-testid="dealdesk-step-proposal-view"]', None),
    ("deal-dd-review", "/deal-desk/DD-01?step=review", '[data-testid="dealdesk-step-review-view"]', None),
    ("deal-pl-banner", "/deal-desk/PL-03?from=pipeline", '[data-testid="dealdesk-pipeline-banner-decision"]', None),
    ("deal-pl-analysis", "/deal-desk/PL-03?step=analysis&from=pipeline", '[data-testid="dealdesk-step-analysis-view"]', None),
    ("twin-a-review", "/deal-desk/R12-TWA?step=review", '[data-testid="dealdesk-step-review-view"]', None),
    ("twin-b-proposal", "/deal-desk/R12-TWB", '[data-testid="dealdesk-step-proposal-view"]', None),
    ("twin-b-stress", "/deal-desk/R12-TWB?step=stress", '[data-testid="dealdesk-step-stress-view"]', None),
    ("twin-a-structure", "/deal-desk/R12-TWA?step=structure", '[data-testid="dealdesk-stepper"]', None),
]


def run(ui: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tok = mint()
    report: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in SIZES:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": tok, "domain": "127.0.0.1", "path": "/"}])
            page: Page = ctx.new_page()
            for name, path, sel, click in SURFACES:
                page.goto(ui + path, wait_until="domcontentloaded", timeout=120000)
                ok = True
                if sel:
                    try:
                        page.wait_for_selector(sel, timeout=120000)
                    except Exception:  # noqa: BLE001 - recorded as a missing surface
                        ok = False
                if click:
                    page.click(click)
                wait_idle(page, 1200)
                probe = page.evaluate(PROBE, None)
                file = OUT / f"{name}-{w}x{h}.png"
                page.screenshot(path=str(file), full_page=False)
                report.append({"surface": name, "size": f"{w}x{h}", "found": ok, "file": str(file.relative_to(V5)), **probe})
                print(f"{name} {w}x{h}: found={ok} docWidth={probe.get('docWidth')} overflow={len(probe.get('overflow', []))} rough={probe.get('rough')}")
            ctx.close()
        browser.close()
    (OUT / "u_shots.json").write_text(json.dumps(report, indent=2))
    bad = [r for r in report if not r["found"] or r.get("overflow") or r.get("rough") or (r.get("docWidth", 0) > int(r["size"].split("x")[0]))]
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    sys.exit(run(ap.parse_args().ui))
