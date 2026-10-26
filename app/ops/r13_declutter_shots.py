"""PLAN_R13 Session X: screenshots of every screen the declutter changed, at 1440x900 and 1280x800, with the overflow probe.

  python ops/r13_declutter_shots.py [--ui http://127.0.0.1:5500] [--only landing,deal-more,...]

Writes docs/v5/r13_declutter/*.png and docs/v5/r13_declutter/x_shots.json. Needs the UI and the module APIs running
(Workspace/identity, Deal Desk, What-If, Lenses, Early Warning, Borrower 360). Mints a session in the identity store; no
password or secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_declutter"
SIZES = [(1440, 900), (1280, 800)]

# name, path, element to wait for, element to click first (or None)
SURFACES: list[tuple[str, str, str | None, str | None]] = [
    ("dealdesk-landing", "/deal-desk", '[data-testid="dealdesk-cards-row"]', None),
    ("dealdesk-landing-queue", "/deal-desk?card=to_review", '[data-testid="dealdesk-card-list"]', None),
    ("dealdesk-book", "/deal-desk?tab=book&filter=material_going_bad", '[data-testid="dealdesk-tab-book-panel"]', None),
    ("dealdesk-params", "/deal-desk?tab=params", '[data-testid="dealdesk-tab-params-panel"]', None),
    ("dealdesk-pipeline", "/deal-desk?mode=pipeline", '[data-testid="dealdesk-mode"]', None),
    ("deal-proposal", "/deal-desk/DD-01", '[data-testid="dealdesk-step-proposal-view"]', None),
    ("deal-more-menu", "/deal-desk/DD-01", '[data-testid="dealdesk-more-button"]', '[data-testid="dealdesk-more-button"]'),
    ("deal-review", "/deal-desk/DD-01?step=review", '[data-testid="dealdesk-step-review-view"]', None),
    ("deal-group-swot", "/deal-desk/R12-TWA", '[data-testid="dealdesk-more-button"]', "GROUP"),
    ("deal-pl-banner", "/deal-desk/PL-03?from=pipeline", '[data-testid="dealdesk-pipeline-banner"]', None),
    ("whatif-landing", "/what-if", '[data-testid="whatif-landing"]', None),
    ("whatif-thread", "THREAD", '[data-testid="whatif-glance"]', None),
    ("whatif-model-card", "/what-if/models/corporate/delta", '[data-testid="whatif-mc-data"]', None),
    ("lenses-landing", "/lenses", '[data-testid="lenses-landing"]', None),
    ("ews-landing", "/early-warning", '[data-testid="ews-askbar"]', None),
    ("ews-model-card", "/early-warning/model?domain=corporate", '[data-testid="ews-mc-sources"]', None),
    ("b360-landing", "/borrower-360", '[data-testid="b360-askbar"]', None),
    # round 3 of the notes audit (screens outside the five modules)
    ("playbooks", "/playbooks", "h1", None),
    ("studio", "/studio", "h1", None),
    ("stress", "/stress", "h1", None),
    ("accepted-risk", "/accepted-risk", "h1", None),
]


def whatif_thread(tok: str) -> str:
    """A What-If thread on a standard scenario (opened through the What-If API, as the library card does)."""
    def call(method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request("http://127.0.0.1:8503/api/v1/whatif" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Cookie": f"cp_session={tok}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"{}")
    lib = call("GET", "/library?domain=corporate")
    sid = lib["standard"][0]["scenario_id"]
    t = call("POST", "/threads", {"domain": "corporate", "library_id": sid})
    return f"/what-if/thread/{t['thread_id']}"


def run(ui: str, only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tok = mint()
    report: list[dict] = []
    thread = ""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in SIZES:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": tok, "domain": "127.0.0.1", "path": "/"}])
            page: Page = ctx.new_page()
            for name, path, sel, click in SURFACES:
                if only and name not in only:
                    continue
                if path == "THREAD":
                    try:
                        thread = thread or whatif_thread(tok)
                    except Exception as e:  # noqa: BLE001 - recorded as a missing surface
                        print(f"{name}: no thread ({type(e).__name__})")
                        report.append({"surface": name, "size": f"{w}x{h}", "found": False})
                        continue
                    path = thread
                page.goto(ui + path, wait_until="domcontentloaded", timeout=180000)
                ok = True
                if sel:
                    try:
                        page.wait_for_selector(sel, timeout=180000)
                    except Exception:  # noqa: BLE001
                        ok = False
                wait_idle(page, 1500)
                # Noor's panel (Session H's) opens on its own after login; closed so the module fills the screen.
                close = page.locator('[data-testid="noor-panel"] button[aria-label="Close"]')
                if close.count() and close.first.is_visible():
                    close.first.click()
                    page.wait_for_timeout(400)
                if click == "GROUP" and ok:
                    page.click('[data-testid="dealdesk-more-button"]')
                    page.click('[data-testid="dealdesk-action-group"]')
                    try:
                        page.wait_for_selector('[data-testid="r12-slot-Group"]', timeout=60000)
                    except Exception:  # noqa: BLE001
                        ok = False
                    wait_idle(page, 2500)
                elif click and ok:
                    page.click(click)
                    page.wait_for_timeout(600)
                probe = page.evaluate(PROBE, None)
                file = OUT / f"{name}-{w}x{h}.png"
                page.screenshot(path=str(file), full_page=False)
                report.append({"surface": name, "size": f"{w}x{h}", "found": ok, "file": str(file.relative_to(V5)), **probe})
                print(f"{name} {w}x{h}: found={ok} docWidth={probe.get('docWidth')} overflow={len(probe.get('overflow', []))} rough={probe.get('rough')}")
            ctx.close()
        browser.close()
    out = OUT / "x_shots.json"
    if only and out.exists():  # a partial run replaces only its own surfaces in the report
        keep = [r for r in json.loads(out.read_text()) if r.get("surface") not in only]
        report = keep + report
    out.write_text(json.dumps(report, indent=2))
    bad = [r for r in report if not r.get("found") or r.get("rough") or (r.get("docWidth", 0) > int(r["size"].split("x")[0]))]
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sys.exit(run(a.ui, {x for x in a.only.split(",") if x}))
