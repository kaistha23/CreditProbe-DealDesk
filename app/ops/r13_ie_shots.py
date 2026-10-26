"""R13 IE: screenshots of the four governance panels at 1440x900 and 1280x800, opened from the Deal Desk and Admin
tools menus, with the overflow probe.

  python ops/r13_ie_shots.py [--ui http://127.0.0.1:5500]

Writes docs/v5/r13_ie/*.png and docs/v5/r13_ie/ie_shots.json. Needs the UI, the Workspace API (identity), the Deal
Desk API and the Admin API running. Mints a session in the identity store; no password or secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_ie"
SIZES = [(1440, 900), (1280, 800)]
Q = "The auditor asks for the approvals, conditions and stage history of the 5 largest Stage 3 borrowers in Construction"

SURFACES: list[tuple[str, str, str, str | None]] = [
    # name, path, element to wait for (inside the drawer), element to click first
    ("dd-tools-menu", "/deal-desk", '[data-testid="gov-tools-menu"]', '[data-testid="gov-tools"]'),
    ("dd-inspection", "/deal-desk?gov=inspection&q=" + Q.replace(" ", "%20"), '[data-testid="gov-insp-pack"]', None),
    ("dd-exceptions", "/deal-desk?gov=exceptions", '[data-testid="gov-exc-table"]', None),
    ("dd-rm-track", "/deal-desk?gov=rm-track", '[data-testid="gov-rm-table"]', None),
    ("dd-doa", "/deal-desk?gov=doa", '[data-testid="gov-doa-table"]', None),
    ("admin-tools-menu", "/settings", '[data-testid="gov-tools-menu"]', '[data-testid="gov-tools"]'),
    ("admin-inspection-sample", "/settings?gov=inspection&q=SAMA%20sample%3A%20exposure%2C%20ECL%20and%20policy%20exceptions%20for%20CB00039%2C%20R12-TWA%20and%20CB99999",
     '[data-testid="gov-insp-pack"]', None),
    ("admin-exceptions", "/settings?gov=exceptions", '[data-testid="gov-exc-table"]', None),
    ("admin-rm-branch", "/settings?gov=rm-track", '[data-testid="gov-rm-table"]', '[data-testid="gov-rm-group-branch"]'),
    ("admin-doa", "/settings?gov=doa", '[data-testid="gov-doa-table"]', None),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report, bad = [], 0
    with sync_playwright() as p:
        exe = Path("/opt/pw-browsers/chromium")  # the cloud container's browser; elsewhere Playwright's own
        b = p.chromium.launch(executable_path=str(exe)) if exe.exists() else p.chromium.launch()
        for w, h in SIZES:
            ctx = b.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = ctx.new_page()
            for name, path, wait, click in SURFACES:
                page.goto(a.ui + path, wait_until="domcontentloaded")
                wait_idle(page)
                try:
                    if click:
                        page.locator(click).first.click(timeout=30000)
                    page.wait_for_selector(wait, timeout=90000)
                    if "rm-track" in path and click:
                        page.wait_for_selector('[data-testid="gov-rm-table"]', timeout=60000)
                    page.wait_for_timeout(1200)
                except Exception as e:  # noqa: BLE001
                    print(name, w, "MISSING", str(e).splitlines()[0])
                    bad += 1
                drawer = '[role="dialog"] aside' if "gov=" in path else None
                page.screenshot(path=str(OUT / f"{name}-{w}x{h}.png"))
                r = page.evaluate(PROBE, drawer)
                r.update({"surface": name, "size": f"{w}x{h}"})
                report.append(r)
                if r.get("missing") or r.get("overflow") or r.get("rough") or r.get("docWidth", 0) > w:
                    bad += 1
                print(name, f"{w}x{h}", "overflow" if r.get("overflow") else "ok", r.get("rough") or "")
            ctx.close()
        b.close()
    (OUT / "ie_shots.json").write_text(json.dumps(report, indent=1) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
