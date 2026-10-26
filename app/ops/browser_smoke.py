"""Browser smoke test for the v5 one app (gate item 5), Early Warning journeys.

Drives the real UI (default http://127.0.0.1:5500) headless with Playwright.
Every step records console errors, page errors and failed requests, takes a
screenshot, and checks what is on screen against the Early Warning API.

Usage: <workspace venv>/python ops/browser_smoke.py [ui_base] [ews_api_base]
Writes evidence/v5/ews/browser/{*.png, browser_smoke.json}. Exit 1 on failure.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import os  # noqa: E402
import core_login  # noqa: E402  (ops/core_login.py: the Core service session)
from playwright.sync_api import Page, sync_playwright

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "ews" / "browser"
UI = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5500").rstrip("/")
API = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8501").rstrip("/")

results: list[dict] = []
problems: list[str] = []


def api(path: str):
    with urllib.request.urlopen(f"{API}/api/v1/ews{path}", timeout=60) as r:
        return json.loads(r.read())


def check(step: str, ok: bool, detail: str = "") -> None:
    results.append({"step": step, "pass": bool(ok), "detail": detail})
    if not ok:
        problems.append(f"{step}: {detail}")
    print(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail and not ok else ""))


class Watch:
    """Console errors, page errors and failed requests, per step."""

    def __init__(self, page: Page):
        self.errors: list[str] = []
        page.on("console", lambda m: self.errors.append("console: " + m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e)[:200]))
        page.on("response", lambda r: self.errors.append(f"http {r.status}: {r.url[:160]}")
                if r.status >= 400 and "favicon" not in r.url and "_next/webpack-hmr" not in r.url else None)

    def take(self) -> list[str]:
        out, self.errors = self.errors, []
        return out


def settle(page: Page, testid: str, timeout: int = 60_000) -> None:
    page.wait_for_selector(f'[data-testid="{testid}"]', timeout=timeout)
    page.wait_for_timeout(600)


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def clean(step: str, watch: Watch) -> None:
    errs = watch.take()
    check(f"{step}: no console errors, page errors or failed requests", not errs, "; ".join(errs[:5]))


def text(page: Page, testid: str) -> str:
    return page.locator(f'[data-testid="{testid}"]').first.inner_text()


def run() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(context, os.environ.get("CP_SWEEP_USER", "anne"))  # signed in as the Administrator
        page = context.new_page()
        watch = Watch(page)

        # 1. The frozen Cockpit home is unchanged and the sidebar is the v5 one.
        page.goto(UI + "/", wait_until="domcontentloaded")
        page.wait_for_selector("text=Segments requiring attention", timeout=90_000)
        page.wait_for_timeout(1500)
        shot(page, "01_cockpit_home")
        body = page.inner_text("body")
        check("cockpit home renders the frozen toggle and attention", "Corporate" in body and "Retail" in body
              and "Construction: ECL rose to SAR 2,755 million" in body, body[:200])
        nav = page.locator("aside, nav").first.inner_text()
        # PLAN_R5 P1: Playbook and Lenses under Intelligence, Admin at the bottom; no pre-v5 capability.
        check("sidebar lists the v5 modules (R5 navigation)",
              "Early Warning" in nav and "Lenses" in nav and "Playbook" in nav
              and nav.find("INTELLIGENCE") < nav.find("Playbook") < nav.find("DATA")
              and "Analysis Studio" not in nav and "Trace & Lineage" not in nav, nav[:300])
        clean("cockpit home", watch)

        # 2. Corporate portfolio.
        corp = api("/level?domain=corporate")
        page.goto(UI + "/early-warning?domain=corporate", wait_until="domcontentloaded")
        settle(page, "ews-level-portfolio")
        shot(page, "02_ews_corporate_portfolio")
        check("corporate as-of shown", "Q2 2026 (30 Jun 2026)" in text(page, "ews-as-of"), text(page, "ews-as-of"))
        warned = text(page, "ews-kpi-warned")
        check("corporate warned KPI equals the API", f"{corp['headline']['customers_warned']:,}" in warned, warned)
        page.wait_for_selector('[data-testid="ews-trend-chart"] [data-rendered="true"]', timeout=60_000)
        check("corporate trend chart drawn (interactive)", page.locator('[data-testid="ews-trend-chart"] svg path').count() >= 3)
        cards = page.locator('[data-testid="ews-children"] [data-testid^="ews-card-"]').count()
        check("one card per sector", cards == len(corp["children"]), f"{cards} vs {len(corp['children'])}")
        check("interpretation shown", "carries the largest" in text(page, "ews-interpretation-text"))
        clean("corporate portfolio", watch)

        # 3. Sector -> sub-sector -> borrowers -> borrower.
        lead = corp["children"][0]["key"]
        page.click(f'[data-testid="ews-open-{lead}"]')
        settle(page, "ews-level-segment")
        shot(page, "03_ews_corporate_sector")
        check("sector breadcrumbs", lead in text(page, "ews-breadcrumbs"))
        sector = api(f"/level?domain=corporate&segment={urllib.request.quote(lead)}")
        sub = sector["children"][0]["key"]
        page.click(f'[data-testid="ews-open-{sub}"]')
        settle(page, "ews-level-subsegment")
        shot(page, "04_ews_corporate_subsector")
        page.click('[data-testid="ews-open-warned"]')
        settle(page, "ews-customer-list")
        page.wait_for_selector('[data-testid^="ews-customer-CB"]', timeout=60_000)
        shot(page, "05_ews_corporate_borrowers")
        listed = api(f"/customers?domain=corporate&segment={urllib.request.quote(lead)}"
                     f"&subsegment={urllib.request.quote(sub)}&cohort=warned&limit=1")
        check("borrower list total equals the API", f"{listed['total']:,} borrowers" in text(page, "ews-list-total"),
              text(page, "ews-list-total")[:120])
        first = page.locator('[data-testid^="ews-customer-CB"]').first
        borrower = first.get_attribute("data-testid").replace("ews-customer-", "")
        first.click()
        settle(page, "ews-customer-detail")
        shot(page, "06_ews_corporate_borrower")
        detail = api(f"/customers/{borrower}?domain=corporate")
        check("borrower detail lists every facility", page.locator('[data-testid^="ews-exposure-"]').count()
              == len(detail["exposures"]))
        check("rule table rendered", page.locator('[data-testid^="ews-rule-"]').count()
              == sum(len(e["rules"]) for e in detail["exposures"]))
        clean("corporate drill", watch)

        # 4. Back walks up one level at a time.
        page.go_back()
        settle(page, "ews-customer-list")
        check("Back returns to the borrower list", True)
        page.go_forward()
        settle(page, "ews-customer-detail")

        # 5. Borrower 360 link carries book, borrower and period; and comes back.
        page.click('[data-testid="ews-link-b360"]')
        settle(page, "b360-context")
        page.wait_for_selector('[data-testid="b360-back-to-ews"]', timeout=60_000)
        shot(page, "07_b360_landing")
        check("Borrower 360 received the borrower", text(page, "b360-id") == borrower
              and text(page, "b360-domain") == "corporate" and text(page, "b360-period") == "2026Q2",
              f"{text(page, 'b360-id')} {text(page, 'b360-period')}")
        page.click('[data-testid="b360-back-to-ews"]')
        settle(page, "ews-customer-detail")
        check("Borrower 360 links back to the same borrower in Early Warning", borrower in page.url)
        clean("borrower 360 round trip", watch)

        # 6. Export a list to What-If: the cohort it opens is the list.
        page.goto(UI + f"/early-warning?domain=corporate&segment={urllib.request.quote(lead)}&cohort=high_or_critical",
                  wait_until="domcontentloaded")
        settle(page, "ews-customer-list")
        page.wait_for_selector('[data-testid^="ews-customer-CB"]', timeout=60_000)
        expected = api(f"/customers?domain=corporate&segment={urllib.request.quote(lead)}&cohort=high_or_critical&limit=1")
        page.click('[data-testid="ews-export-list"]')
        page.wait_for_url(re.compile(r".*/what-if/thread/.*"), timeout=60_000)
        settle(page, "whatif-cohort")
        shot(page, "08_whatif_cohort")
        check("What-If cohort holds exactly the exported borrowers",
              text(page, "whatif-customers") == f"{expected['total']:,}",
              f"{text(page, 'whatif-customers')} vs {expected['total']}")
        clean("export to what-if", watch)

        # 7. Retail: product -> Salaried -> sub-product -> customers -> customer.
        retail = api("/level?domain=retail")
        page.goto(UI + "/early-warning?domain=retail", wait_until="domcontentloaded")
        settle(page, "ews-level-portfolio")
        shot(page, "09_ews_retail_portfolio")
        check("retail as-of shown", "Aug 2026 (31 Aug 2026)" in text(page, "ews-as-of"), text(page, "ews-as-of"))
        check("retail warned KPI equals the API",
              f"{retail['headline']['customers_warned']:,}" in text(page, "ews-kpi-warned"))
        page.click('[data-testid="ews-open-Personal Finance"]')
        settle(page, "ews-classifications")
        shot(page, "10_ews_retail_product")
        check("Salaried and Non-Salaried shown", page.locator('[data-testid="ews-card-SALARIED"]').count() == 1
              and page.locator('[data-testid="ews-card-NON_SALARIED"]').count() == 1)
        page.click('[data-testid="ews-open-SALARIED"]')
        settle(page, "ews-level-classification")
        shot(page, "11_ews_retail_salaried")
        sal = api("/level?domain=retail&segment=Personal%20Finance&classification=SALARIED")
        subp = sal["children"][0]["key"]
        page.click(f'[data-testid="ews-open-{subp}"]')
        settle(page, "ews-level-subsegment")
        check("sub-product breadcrumbs keep the classification",
              "Salaried" in text(page, "ews-breadcrumbs") and subp in text(page, "ews-breadcrumbs"))
        page.click('[data-testid="ews-open-warned"]')
        settle(page, "ews-customer-list")
        page.wait_for_selector('[data-testid^="ews-customer-RC"]', timeout=60_000)
        shot(page, "12_ews_retail_customers")
        page.locator('[data-testid^="ews-customer-RC"]').first.click()
        settle(page, "ews-customer-detail")
        shot(page, "13_ews_retail_customer")
        clean("retail drill", watch)

        # 8. Ask the Cockpit opens the frozen Cockpit on the same book, question in the box.
        page.click('[data-testid="ews-link-cockpit"]')
        # Retail's panel is titled "Retail portfolio requiring attention".
        page.wait_for_selector("text=/requiring attention/", timeout=90_000)
        page.wait_for_timeout(1500)
        shot(page, "14_cockpit_from_ews")
        box = page.evaluate("""() => [...document.querySelectorAll('input, textarea')]
                                   .map((e) => e.value).find((v) => v && v.includes('customer')) || ''""")
        check("Cockpit opened with the question prefilled", "customer RC" in box, box[:120])
        check("Cockpit opened on the Retail book", "Retail portfolio requiring attention" in page.inner_text("body"))
        clean("ask the cockpit", watch)

        # 9. Model details: not blank, for both books.
        for d, rule in (("corporate", "C-WATCH"), ("retail", "R-DPD")):
            page.goto(UI + f"/early-warning/model?domain={d}", wait_until="domcontentloaded")
            page.wait_for_selector(f"text={rule}", timeout=60_000)
            page.wait_for_timeout(800)
            shot(page, f"15_model_{d}")
            check(f"model details render for {d}", rule in page.inner_text("body"))
            clean(f"model details {d}", watch)

        browser.close()
    report = {"ui": UI, "api": API, "results": results, "failed": len(problems), "problems": problems}
    (OUT / "browser_smoke.json").write_text(json.dumps(report, indent=1))
    print(f"{len(results) - len(problems)}/{len(results)} browser checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run())
