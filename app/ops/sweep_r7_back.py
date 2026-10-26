"""UAT sweep, part `r7-back` (PLAN_R7, Anne: "all Back buttons work and go to exactly the previous step").

Called from ops/uat_sweep.py (`--only r7-back`). Each journey checks the in-app Back button and the browser's Back:
- Deal Desk: filtered pipeline → deal → step 1 → browser Back to step 2 → Back to the pipeline, still filtered;
- a deal opened from another module (Early Warning) → Back returns there, not to the pipeline;
- a deal opened in a fresh tab (no history) → Back goes to the pipeline;
- Policy Docs: filtered library → document → Back to the library, still filtered;
- Borrower 360 → Open in Early Warning → Back returns to Borrower 360 (the same customer);
- Mail: a message → browser Back returns to the list; Back button likewise;
- Investigations: list → item → Back to the list; Workspace → item → Back to the Workspace.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from uat_sweep_core import as_user, tid


def _wait_url(pg, pattern: str, timeout: int = 60_000) -> bool:
    try:
        pg.wait_for_url(re.compile(pattern), timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 - reported by the check
        return False


def r7_back_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    browser = page.context.browser

    # ------------------------------------------------------------ Deal Desk
    s.start("both", "R7-B1", "Deal Desk: filtered pipeline → deal → steps with browser Back → Back to the filtered pipeline")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/deal-desk", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("dealdesk-table"), timeout=120_000)
    pg.fill('input[aria-label="Search proposals"]', "DD-02")
    s.check("the pipeline search is kept in the address", _wait_url(pg, r".*/deal-desk\?search=DD-02$", 10_000), "?search=DD-02", pg.url)
    pg.click(tid("dealdesk-row-DD-02"))
    pg.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=120_000)
    pg.click(tid("dealdesk-step-proposal"))
    pg.wait_for_selector(tid("dealdesk-step-proposal-view"), timeout=30_000)
    s.check("a step is in the address", "step=proposal" in pg.url, "step=proposal", pg.url)
    pg.go_back()
    pg.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=30_000)
    s.check("browser Back returns to the previous step (Analysis)", "step=" not in pg.url and "/deal-desk/DD-02" in pg.url, "Analysis", pg.url)
    pg.go_forward()
    pg.wait_for_selector(tid("dealdesk-step-proposal-view"), timeout=30_000)
    s.check("browser Forward returns to step 1", "step=proposal" in pg.url, "step=proposal", pg.url)
    pg.click(tid("dealdesk-back"))
    s.check("Back (from step 1) walks back to Analysis, the previous step", _wait_url(pg, r".*/deal-desk/DD-02$", 30_000), "/deal-desk/DD-02", pg.url)
    pg.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=30_000)
    pg.click(tid("dealdesk-back"))
    s.check("Back returns to the pipeline exactly as filtered", _wait_url(pg, r".*/deal-desk\?search=DD-02$", 30_000), "?search=DD-02", pg.url)
    pg.wait_for_selector(tid("dealdesk-table"), timeout=60_000)
    s.check("the search box still reads DD-02", pg.input_value('input[aria-label="Search proposals"]') == "DD-02")
    s.check("only the matching proposal is listed", pg.locator(tid("dealdesk-row-DD-02")).count() == 1)
    pg.click(tid("dealdesk-new"))
    pg.wait_for_function("() => location.search.includes('new=1')", timeout=10_000)
    pg.go_back()
    s.check("browser Back closes the New proposal dialog, staying on the pipeline",
            _wait_url(pg, r".*/deal-desk\?search=DD-02$", 10_000), "?search=DD-02", pg.url)
    ctx.close()
    s.finish()

    s.start("both", "R7-B2", "A deal opened from Early Warning: Back returns to Early Warning, not to the pipeline")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/early-warning?domain=corporate", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("ews-kpis"), timeout=120_000)
    pg.goto(UI + "/deal-desk/DD-02", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=120_000)
    pg.click(tid("dealdesk-back"))
    s.check("Back lands on Early Warning", _wait_url(pg, r".*/early-warning\?domain=corporate", 30_000), "/early-warning", pg.url)
    ctx.close()
    s.finish()

    s.start("both", "R7-B3", "A deal opened in a fresh tab (no history): Back goes to the pipeline")
    ctx, pg, _ = as_user(browser, s, "anne")
    fresh = ctx.new_page()
    fresh.goto(UI + "/deal-desk/DD-02", wait_until="domcontentloaded")
    fresh.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=120_000)
    fresh.click(tid("dealdesk-back"))
    s.check("Back with no history goes to the Deal Desk pipeline", _wait_url(fresh, r".*/deal-desk$", 30_000), "/deal-desk", fresh.url)
    ctx.close()
    s.finish()

    # ------------------------------------------------------------ Policy Docs
    s.start("both", "R7-B4", "Policy Docs: filtered library → document → Back to the library, still filtered")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/policy-docs", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("policy-doc-row"), timeout=120_000)
    pg.click(tid("policy-filter-policy"))
    s.check("the filter is in the address", _wait_url(pg, r".*/policy-docs\?filter=policy$", 10_000), "?filter=policy", pg.url)
    pg.locator(tid("policy-doc-row")).first.click()
    pg.wait_for_selector(tid("policy-back"), timeout=60_000)
    pg.click(tid("policy-back"))
    s.check("Back returns to the library with its filter", _wait_url(pg, r".*/policy-docs\?filter=policy$", 30_000), "?filter=policy", pg.url)
    pg.wait_for_selector(tid("policy-doc-row"), timeout=60_000)
    s.check("the Policies tab is still selected", pg.get_attribute(tid("policy-filter-policy"), "aria-selected") == "true")
    ctx.close()
    s.finish()

    # ------------------------------------------------------------ Borrower 360 ↔ Early Warning
    s.start("corporate", "R7-B5", "Borrower 360 → Open in Early Warning → Back returns to the same Borrower 360 customer")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/borrower-360?domain=corporate", wait_until="domcontentloaded")
    pg.wait_for_selector('[data-testid^="b360-open-row-"]', timeout=120_000)
    pg.locator('[data-testid^="b360-open-row-"]').first.click()
    pg.wait_for_selector(tid("b360-back-to-ews"), timeout=120_000)
    b360_url = pg.url
    s.check("a Borrower 360 customer is open", "customer_id=" in b360_url, "customer_id=", b360_url)
    pg.click(tid("b360-back-to-ews"))
    pg.wait_for_selector(tid("ews-customer-detail"), timeout=120_000)
    pg.click(tid("ews-detail-back"))
    s.check("Back from the Early Warning customer returns to Borrower 360, the same customer",
            _wait_url(pg, r".*/borrower-360\?.*customer_id=", 30_000) and pg.url.split("customer_id=")[1].split("&")[0]
            == b360_url.split("customer_id=")[1].split("&")[0], b360_url, pg.url)
    pg.click(tid("b360-back"))
    s.check("Back from the customer returns to the Borrower 360 list it was opened from",
            _wait_url(pg, r".*/borrower-360\?domain=corporate$", 30_000), "/borrower-360?domain=corporate", pg.url)
    ctx.close()
    s.finish()

    # ------------------------------------------------------------ Mail
    s.start("both", "R7-B6", "Mail: open a message → browser Back and the Back button return to the list")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/messages", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("mail-row"), timeout=120_000)
    pg.locator(tid("mail-row")).first.click()
    s.check("the message opens", _wait_url(pg, r".*/messages\?.*thread=", 30_000), "thread=", pg.url)
    pg.go_back()
    s.check("browser Back returns to the list (stays in Mail)", _wait_url(pg, r".*/messages$", 30_000), "/messages", pg.url)
    pg.locator(tid("mail-row")).first.click()
    pg.wait_for_selector(tid("mail-back"), timeout=30_000)
    pg.click(tid("mail-back"))
    s.check("the Back button returns to the list", _wait_url(pg, r".*/messages$", 30_000), "/messages", pg.url)
    ctx.close()
    s.finish()

    # ------------------------------------------------------------ Investigations
    s.start("both", "R7-B7", "Workspace items (investigations, analyses, projects): list → item → Back to the list; Workspace → item → Back")
    ctx, pg, _ = as_user(browser, s, "anne")
    opened = 0
    for kind in ("investigations", "analyses", "projects"):
        pg.goto(UI + f"/{kind}", wait_until="domcontentloaded")
        pg.wait_for_selector(tid(f"ws-{kind}"), timeout=120_000)
        pg.wait_for_timeout(1500)
        link = pg.locator(f'main a[href^="/{kind}/"]').first
        if not link.count():
            continue
        opened += 1
        href = link.get_attribute("href") or ""
        link.click()
        pg.wait_for_selector(tid("ws-back"), timeout=60_000)
        pg.locator(tid("ws-back")).first.click()
        s.check(f"{kind}: Back returns to the list", _wait_url(pg, rf".*/{kind}$", 30_000), f"/{kind}", pg.url)
        pg.goto(UI + "/workspace", wait_until="domcontentloaded")
        pg.wait_for_timeout(1500)
        pg.goto(UI + href, wait_until="domcontentloaded")
        pg.wait_for_selector(tid("ws-back"), timeout=60_000)
        pg.locator(tid("ws-back")).first.click()
        s.check(f"{kind}: opened from the Workspace, Back returns to the Workspace", _wait_url(pg, r".*/workspace", 30_000), "/workspace", pg.url)
    s.check("at least one Workspace item kind had an item to open", opened >= 1, ">= 1", opened)
    ctx.close()
    s.finish()
