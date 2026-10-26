"""PLAN_R13 Session L (J8): screenshots of the Lenses home and the lens dashboard at 1440x900 and 1280x800.

  python ops/r13_lenses_shots.py [--ui http://127.0.0.1:5500]

Needs the UI (5500), the Lenses API (8509) and the identity service (8505). Builds two lenses by request (Makkah
retail cards, the 1,812 bps lens of J8, and CRO portfolio), opens each with the assistant panel and without it, and
writes docs/v5/r13_lenses/*.png plus shots.json (overflow probe, interpretation lines, KPI count). Mints a session in
the identity store; no password or secret is read or printed.
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
from playwright.sync_api import sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_lenses"
SIZES = [(1440, 900), (1280, 800)]
LE = "http://127.0.0.1:8509/api/v1/lenses"
REQUESTS = [("makkah-cards", "Makkah retail cards", "retail"), ("cro", "CRO portfolio", "corporate")]


def create(tok: str, request: str, book: str) -> str:
    req = urllib.request.Request(f"{LE}/lenses", data=json.dumps({"request": request, "book": book}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": f"cp_session={tok}"})
    with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 - the Lenses service on loopback
        return json.loads(r.read())["lens"]["lens_id"]


def run(ui: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tok = mint()
    lenses = {key: create(tok, text, book) for key, text, book in REQUESTS}
    report: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in SIZES:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": tok, "url": ui}])
            page = ctx.new_page()
            page.goto(f"{ui}/lenses", wait_until="domcontentloaded", timeout=120000)
            page.wait_for_selector('[data-testid="lenses-chat"]', timeout=120000)
            wait_idle(page, 1500)
            page.screenshot(path=str(OUT / f"home_{w}.png"))
            for key, lid in lenses.items():
                for panel in ("", "0"):
                    name = f"{key}{'_nopanel' if panel else ''}_{w}"
                    page.goto(f"{ui}/lenses/{lid}" + ("?panel=0" if panel else ""), wait_until="domcontentloaded", timeout=120000)
                    page.wait_for_selector('[data-testid="lens-interpretation"]', timeout=120000)
                    page.wait_for_selector('[data-testid="lens-plot"] .main-svg', timeout=120000)
                    wait_idle(page, 2500)
                    page.screenshot(path=str(OUT / f"{name}.png"))
                    if not panel:   # the chart grid (the page scrolls inside the shell, so a full-page shot stops at the fold)
                        tiles = page.locator('[data-testid="lens-tiles"] > *')
                        for j, at in enumerate(range(0, tiles.count(), 4)):
                            tiles.nth(at).evaluate("e => e.scrollIntoView({block: 'start'})")
                            wait_idle(page, 1800)
                            page.screenshot(path=str(OUT / f"{name}_grid{j + 1}.png"))
                    r = page.evaluate(PROBE, None)
                    r.update({"surface": name, "interpretation_lines": int(page.locator('[data-testid="lens-interpretation"]').get_attribute("data-lines") or 0),
                              "kpis": int(page.locator('[data-testid="lens-kpis"]').get_attribute("data-count") or 0),
                              "charts": page.locator('[data-testid="lens-plot"]').count()})
                    report.append(r)
                    print(name, "overflow" if r.get("overflow") else "ok", r["interpretation_lines"], r["kpis"], r.get("rough") or "")
            ctx.close()
        browser.close()
    (OUT / "shots.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    sys.exit(run(ap.parse_args().ui))
