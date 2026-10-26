#!/usr/bin/env python3
"""R14 session p: screens of the proposal check, the batch check and the bank-form credit proposal at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_p_shots.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800]

Needs the Deal Desk service (8508), the Cockpit API (8500, sign-in) and the UI (production build). Screens and a JSON report
(page errors, dev overlay, sideways scroll) go to docs/v5/r14_review/p/. From the landing every screen is reached by clicking,
except the twin-A deal page (opened by its URL to land on the Recommendation step).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "p"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
HALF = V5 / "data" / "dealdesk" / "demo_proposals" / "R14-RWQ_RM_proposal_half_baked.docx"
PROBE = "() => ({docWidth: document.documentElement.scrollWidth, vw: window.innerWidth, overlay: !!document.querySelector('nextjs-portal')})"


def idle(page: Page, ms: int = 800) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(ms)


def close_noor(page: Page) -> None:
    """Noor's panel opens with the brief; close it so the page has its full width (the screens show the module)."""
    try:
        c = page.locator('aside button[aria-label="Close"], [role="complementary"] button[aria-label="Close"]')
        if not c.count():
            c = page.get_by_role("button", name="Close")
        if c.count() and c.first.is_visible():
            c.first.click()
            page.wait_for_timeout(400)
    except Exception:  # noqa: BLE001
        pass


def shot(page: Page, name: str, tag: str, rep: list, errors: list) -> None:
    page.screenshot(path=str(OUT / f"{name}_{tag}.png"))
    r = page.evaluate(PROBE)
    rep.append({"step": name, "size": tag, "errors": list(errors), "sideways": r["docWidth"] > r["vw"], "dev_overlay": r["overlay"]})
    errors.clear()


def run(ui: str, sizes: list[tuple[int, int]]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    rep: list[dict] = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            ctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = ctx.new_page()
            page.set_default_timeout(90_000)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            # landing: the batch button
            page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
            page.locator(T("dealdesk-batch-check")).first.wait_for()
            idle(page, 2500)
            try:  # Noor's panel opens with the brief; close it so the page has its full width
                c = page.get_by_role("button", name="Close")
                if c.count():
                    c.first.click()
                    page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                pass
            shot(page, "p01_landing_batch_button", tag, rep, errors)
            page.locator(T("dealdesk-batch-check")).first.click()
            page.locator(T("dealdesk-batch-check-table")).wait_for(timeout=120_000)
            idle(page, 600)
            shot(page, "p02_batch_check_ranked", tag, rep, errors)
            page.locator(T("dealdesk-batch-check-view-rm")).click()
            page.locator(T("dealdesk-batch-check-rm")).wait_for()
            shot(page, "p03_batch_check_by_rm", tag, rep, errors)
            page.locator(T("dealdesk-batch-check-view-deals")).click()
            # open the demo deal from the ranked table (a click)
            page.locator(f'{T("dealdesk-batch-check-row")}[data-pid="R14-RWQ"]').click()
            page.locator(T("dealdesk-proposal-check")).wait_for(timeout=120_000)
            page.locator(T("dealdesk-proposal-check-result")).wait_for(timeout=120_000)
            close_noor(page)
            page.locator(T("dealdesk-proposal-check")).scroll_into_view_if_needed()
            idle(page, 500)
            shot(page, "p04_deal_proposal_check_on_file", tag, rep, errors)
            # live upload of the half-baked RM proposal
            page.locator(T("dealdesk-proposal-check-file")).set_input_files(str(HALF))
            page.wait_for_timeout(500)
            page.wait_for_function("() => !document.querySelector('[data-testid=\"dealdesk-proposal-check-upload\"]').disabled", timeout=90_000)
            page.locator(T("dealdesk-proposal-check-result")).wait_for()
            page.locator(T("dealdesk-proposal-check-score")).scroll_into_view_if_needed()
            idle(page, 500)
            shot(page, "p05_proposal_check_uploaded_score_sections", tag, rep, errors)
            page.locator(T("dealdesk-proposal-check-defects")).scroll_into_view_if_needed()
            shot(page, "p06_proposal_check_defects", tag, rep, errors)
            page.locator(T("dealdesk-proposal-check-send-back")).click()
            page.locator(T("dealdesk-proposal-check-sent")).wait_for()
            page.locator(T("dealdesk-proposal-check-score")).scroll_into_view_if_needed()
            shot(page, "p07_proposal_check_sent_back", tag, rep, errors)
            page.locator(T("dealdesk-proposal-check-demo-corrected")).click()
            page.wait_for_timeout(500)
            page.wait_for_function("() => !document.querySelector('[data-testid=\"dealdesk-proposal-check-upload\"]').disabled", timeout=90_000)
            idle(page, 500)
            page.locator(T("dealdesk-proposal-check-score")).scroll_into_view_if_needed()
            shot(page, "p08_proposal_check_corrected", tag, rep, errors)
            # twin A: Recommendation -> Prepare the credit proposal
            page.goto(f"{ui}/deal-desk/R12-TWA?step=recommendation", wait_until="domcontentloaded")
            page.locator(T("dealdesk-prepare-proposal")).first.wait_for(timeout=120_000)
            idle(page)
            close_noor(page)
            page.locator(T("dealdesk-prepare-proposal")).first.scroll_into_view_if_needed()
            shot(page, "p09_recommendation_prepare_button", tag, rep, errors)
            page.locator(T("dealdesk-prepare-proposal")).first.click()
            page.locator(T("dealdesk-credit-proposal")).wait_for(timeout=180_000)
            idle(page, 800)
            shot(page, "p10_credit_proposal_page1", tag, rep, errors)
            for k, n in (("facilities", "p11_credit_proposal_facilities_landscape"), ("relationship", "p12_credit_proposal_relationship"),
                         ("exceptions", "p13_credit_proposal_exceptions"), ("cp_selected", "p14_credit_proposal_selected_structure"),
                         ("recommendation", "p15_credit_proposal_recommendation"), ("signatures", "p16_credit_proposal_signatures")):
                page.locator(T(f"dealdesk-credit-proposal-nav-{k}")).click()
                page.wait_for_timeout(1200)
                shot(page, n, tag, rep, errors)
            page.keyboard.press("Escape")
            ctx.close()
        b.close()
    (OUT / "shots.json").write_text(json.dumps(rep, indent=1) + "\n")
    bad = [r for r in rep if r["errors"] or r["dev_overlay"] or r["sideways"]]
    print(f"{len(rep)} screens, {len(bad)} with a page error, dev overlay or sideways scroll")
    for r in bad:
        print("  ", r)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    a = ap.parse_args()
    t0 = time.time()
    rc = run(a.ui, [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")])  # type: ignore[misc]
    print(f"done in {time.time() - t0:.0f} s")
    raise SystemExit(rc)
