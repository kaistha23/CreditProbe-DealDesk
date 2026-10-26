"""PLAN_R9 D: the CRM upload in the Lenses chat -> instant dashboard, twice in a row (button, then typed), the library
and a committee playbook Run. Usage: .venv/bin/python ops/r9_lenses_e2e.py (services and UI running)."""
import sys, time
import os, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core_login
from playwright.sync_api import sync_playwright
PDF = str(HERE.parent / "demo_inputs/policy/CBUAE_Credit_Risk_Management_Standards_EN_5996.pdf")
OUT = os.environ.get("R9_SHOTS", str(HERE.parent / "var" / "r9_lenses_shots"))
os.makedirs(OUT, exist_ok=True)
UI = os.environ.get("V5_UI", "http://127.0.0.1:5500")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    core_login.add_session(ctx, "anne")
    pg = ctx.new_page()
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("requestfailed", lambda r: errs.append("FAILED " + r.url[:90]))
    pg.on("pageerror", lambda e: errs.append(str(e)))
    for run in (1, 2):
        pg.goto(UI + "/lenses", wait_until="networkidle", timeout=120000)
        t = time.time()
        pg.set_input_files("[data-testid=lenses-upload-input]", PDF)
        pg.wait_for_selector("[data-testid=crm-answer]", timeout=30000)
        print(f"run {run}: answer in {time.time()-t:.1f}s; articles", pg.locator("[data-testid=crm-article-row]").count())
        pg.locator("[data-testid=crm-article-row]").nth(8).click()
        pg.screenshot(path=f"{OUT}/r{run}_answer.png", full_page=True)
        t = time.time()
        if run == 1:
            pg.click("[data-testid=crm-create-dashboard]")
        else:
            pg.fill("[data-testid=lenses-ask]", "create the dashboard")
            pg.keyboard.press("Enter")
        try:
            pg.wait_for_selector("[data-testid=crm-findings]", timeout=60000)
        except Exception:
            pg.screenshot(path=f"{OUT}/fail.png"); print("URL", pg.url, "errs", errs[:5]); raise
        pg.wait_for_selector("[data-testid=lens-kpis]", timeout=60000)
        pg.wait_for_timeout(2500)
        print(f"run {run}: lens {pg.url} in {time.time()-t:.1f}s; findings", pg.locator("[data-testid=crm-finding]").count())
        pg.screenshot(path=f"{OUT}/r{run}_lens.png", full_page=False)
    pg.goto(UI + "/lenses?tab=library", wait_until="networkidle")
    pg.wait_for_selector("[data-testid=crm-library-row]", timeout=30000)
    print("library rows", pg.locator("[data-testid=crm-library-row]").count())
    pg.screenshot(path=f"{OUT}/library.png")
    pg.goto(UI + "/playbook", wait_until="networkidle")
    pg.wait_for_selector("[data-testid=committee-ecl-committee-run]", timeout=30000)
    with pg.expect_download(timeout=60000) as dl:
        pg.click("[data-testid=committee-ecl-committee-run]")
    print("playbook download", dl.value.suggested_filename)
    pg.screenshot(path=f"{OUT}/playbook.png")
    b.close()
print("console errors:", len(errs)); [print(" ", e[:200]) for e in sorted(set(e for e in errs if e.startswith("FAILED") or "REFUSED" not in e))[:12]]
