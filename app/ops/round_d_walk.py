"""Round D walk (PLAN_DEALDESK_EDITION row D): DD-06's Deposit requirement on the term sheet and in the paper.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers CP_TEST_PASSWORD=anne .venv/bin/python ops/round_d_walk.py

Steps (screenshots under var/walk/round-d/): open DD-06; the ask shows the Deposit row; Structure -> Optimise; the term
sheet has a "Deposit requirement" row (Ask: operating balances, Recommended: lien-marked cash); the Risk mitigation group
of "Structure it yourself" has the deposit lever; Prepare proposal -> the bank-form paper carries the lien-marked deposit
in Security and in Terms and conditions. Exit 0 = PASS.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
from core_login import add_session  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:6600")
    ap.add_argument("--pid", default="DD-06")
    ap.add_argument("--out", default=str(V5 / "var" / "walk" / "round-d"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    rep: dict = {"ui": a.ui, "pid": a.pid, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checks": [], "failures": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        rep["checks"].append({"check": name, "ok": bool(ok), "detail": detail[:400]})
        if not ok:
            rep["failures"].append(f"{name}: {detail[:200]}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        add_session(ctx)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        def shot(name: str, full: bool = False) -> None:
            page.screenshot(path=str(out / f"{name}.png"), full_page=full)

        page.goto(f"{a.ui}/deal-desk/{a.pid}", wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_selector("[data-testid='dealdesk-title']", timeout=120_000)
        time.sleep(3)
        shot("01_deal")
        # 1. the ask (Proposal step): the Deposit row
        if page.locator("[data-testid='dealdesk-step-proposal']").count():
            page.click("[data-testid='dealdesk-step-proposal']")
            time.sleep(2)
        dep = page.locator("[data-testid='dealdesk-ask-deposit']")
        if dep.count():
            dep.first.scroll_into_view_if_needed()
            check("ask shows the deposit requirement", "Operating balances" in dep.first.inner_text(), dep.first.inner_text())
            shot("02_ask_deposit")
        else:
            check("ask shows the deposit requirement", False, "no dealdesk-ask-deposit row on the Proposal step")
        # 2. Structure -> Optimise -> the term sheet
        page.click("[data-testid='dealdesk-step-structure']")
        time.sleep(3)
        if page.locator("[data-testid='dealdesk-term-sheet']").count() == 0:
            page.locator("[data-testid='dealdesk-optimise']").first.click()
        page.wait_for_selector("[data-testid='dealdesk-term-sheet']", timeout=240_000)
        time.sleep(2)
        ts = page.locator("[data-testid='dealdesk-term-sheet']").first
        row = ts.locator("tr", has_text="Deposit requirement").first
        row.scroll_into_view_if_needed()
        cells = [c.strip() for c in row.locator("td").all_inner_texts()]
        rep["term_sheet_row"] = cells
        check("term sheet has the Deposit requirement row", bool(cells) and cells[0] == "Deposit requirement", json.dumps(cells))
        check("Ask column: operating balances", len(cells) > 1 and cells[1].startswith("Operating balances"), json.dumps(cells))
        check("Recommended column: lien-marked cash", len(cells) > 2 and cells[2].startswith("Lien-marked cash"), json.dumps(cells))
        page.evaluate("el => el.scrollIntoView({block: 'center'})", row.element_handle())
        time.sleep(1)
        shot("03_term_sheet")
        # 3. the lever in Structure it yourself
        g = page.locator("[data-testid='dealdesk-group-toggle-risk-mitigation']")
        if g.count():
            g.first.scroll_into_view_if_needed()
            if page.locator("[data-testid='dealdesk-group-risk-mitigation']").first.get_attribute("data-open") != "true":
                g.first.click()
            time.sleep(1)
            sel = page.locator("[data-testid='dealdesk-lever-deposit-type']")
            check("the deposit lever is in Risk mitigation", sel.count() > 0, "")
            if sel.count():
                sel.first.select_option("lien_cash")
                time.sleep(3)
                sel.first.scroll_into_view_if_needed()
                check("the deposit slider appears", page.locator("[data-testid='dealdesk-lever-deposit']").count() > 0, "")
                shot("04_lever")
        # 4. the paper: Prepare proposal -> security and terms
        page.click("[data-testid='dealdesk-step-recommendation']")
        try:  # the Recommendation is built on the selected structure (default: the Review counter-proposal)
            page.wait_for_selector("[data-testid='dealdesk-prepare-proposal']", timeout=300_000)
        except Exception:  # noqa: BLE001 - reported by the check below
            pass
        time.sleep(2)
        shot("05_recommendation")
        btn = page.locator("[data-testid='dealdesk-prepare-proposal']")
        check("Prepare proposal button", btn.count() > 0, "")
        if btn.count():
            btn.first.click()
            # Round W: "Prepare the credit proposal" opens the paper workspace (the document with Noor beside it)
            page.wait_for_url(lambda u: "/deal-desk/paper/PW-" in u, timeout=300_000)
            page.wait_for_selector("[data-testid='pw-paper']", timeout=180_000)
            time.sleep(3)
            paper = page.locator("[data-testid='pw-paper']").first
            text = paper.inner_text()
            check("paper: security lists the lien-marked cash deposit", "Lien-marked cash deposit" in text, "")
            check("paper: terms carry the placement condition", "lien-marked in the Bank's favour" in text, "")
            for needle, name in (("Lien-marked cash deposit (", "06_paper_security"), ("lien-marked in the Bank's favour", "07_paper_terms")):
                hit = paper.get_by_text(needle, exact=False)
                if hit.count():
                    page.evaluate("el => el.scrollIntoView({block: 'center'})", hit.first.element_handle())
                    time.sleep(1)
                shot(name)
        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()
    rep["result"] = "PASS" if not rep["failures"] else "FAIL"
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("result", "failures", "term_sheet_row")}, indent=1))
    return 0 if rep["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
