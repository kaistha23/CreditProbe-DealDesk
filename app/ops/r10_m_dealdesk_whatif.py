"""R10 M: Deal Desk open (no thread) + Optimise, and What-If compound scenario in the browser, at 1440x900."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10_chat_audit import session
from playwright.sync_api import sync_playwright
OUT = Path(__file__).resolve().parents[1] / "docs/v5/r10_review"
UI = "http://127.0.0.1:5500"
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_cookies([{"name": "cp_session", "value": session(), "domain": "127.0.0.1", "path": "/"}])
    pg = ctx.new_page()
    pg.goto(UI + "/deal-desk/DD-01", wait_until="domcontentloaded")
    pg.wait_for_selector("[data-testid=dealdesk-stepper]", timeout=90000); pg.wait_for_timeout(2500)
    box = pg.locator("[data-testid=dealdesk-stepper]").bounding_box()
    res["stepper_horizontal"] = bool(box and box["width"] > 3 * box["height"])
    res["thread_open_on_open"] = pg.locator("[data-testid=dealdesk-thread]").count() > 0 and pg.locator("[data-testid=dealdesk-thread]").first.is_visible()
    res["kpi_tiles"] = pg.locator("[data-kpi-tile]").count()
    pg.screenshot(path=str(OUT / "m_dealdesk_open.png"))
    btn = pg.locator("[data-testid=dealdesk-analysis-optimise], [data-testid=dealdesk-optimise]").first
    btn.click(); pg.wait_for_selector("[data-testid=dealdesk-optimise-charts] .main-svg", timeout=90000); pg.wait_for_timeout(1500)
    res["optimise_charts"] = pg.locator("[data-testid=dealdesk-optimise-charts] .main-svg").count()
    pg.screenshot(path=str(OUT / "m_dealdesk_optimise.png"), full_page=False)
    b.close()
print(json.dumps(res))
