#!/usr/bin/env python3
"""Round S: the browser walk of the Intelligence Studio (production build), with screenshots.

    CORE_API_ORIGIN=http://127.0.0.1:9005 CP_TEST_PASSWORD=... .venv/bin/python ops/round_se_walk.py --ui http://127.0.0.1:7000

Deal Desk's home → the Intelligence Studio link → every section of the Studio (headline tiles, customers and source
coverage, documents, proposals per bank and analyst, rules, policies, reader accuracy, corrections, governance), then
Agent Operations → its link to the Studio. Writes var/walk/round-se/*.png and report.json; exit 1 on a failure.
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

SECTIONS = ["studio-kpis", "studio-customers", "studio-documents", "studio-proposals", "studio-rules", "studio-policies",
            "studio-reader", "studio-corrections", "studio-governance"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:7000")
    ap.add_argument("--out", default=str(V5 / "var" / "walk" / "round-se"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    rep: dict = {"ui": a.ui, "steps": [], "failures": []}
    errors: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        add_session(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        def step(name: str, ok: bool, **kw):
            rep["steps"].append({"step": name, "ok": ok, **kw})
            if not ok:
                rep["failures"].append(name)
            print(("PASS " if ok else "FAIL ") + name, kw or "")

        page.goto(a.ui + "/deal-desk", wait_until="domcontentloaded", timeout=120_000)
        link = page.locator("[data-testid='intelligence-studio-link']")
        link.wait_for(timeout=120_000)
        page.screenshot(path=str(out / "01_deal_desk_home.png"), full_page=False)
        link.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "02_deal_desk_link.png"))
        link.click()
        page.wait_for_url("**/deal-desk/intelligence", timeout=60_000)
        step("Deal Desk home links to the Studio", page.url.endswith("/deal-desk/intelligence"), url=page.url)
        page.locator("[data-testid='studio-kpis']").wait_for(timeout=120_000)
        time.sleep(2)
        kpis = page.locator("[data-testid='studio-kpis']").inner_text()
        step("Headline tiles", "customers known" in kpis.lower(), text=kpis.replace("\n", " | ")[:400])
        page.screenshot(path=str(out / "03_studio_top.png"))
        for i, s in enumerate(SECTIONS[1:], start=4):
            loc = page.locator(f"[data-testid='{s}']")
            ok = loc.count() == 1
            if ok:
                loc.scroll_into_view_if_needed()
                time.sleep(0.6)
                loc.screenshot(path=str(out / f"{i:02d}_{s}.png"))
            empty = loc.locator("[data-testid='studio-empty']").all_inner_texts() if ok else []
            step(f"Section {s}", ok, empty_state=empty[:1])
        page.screenshot(path=str(out / "13_studio_full.png"), full_page=True)
        words = page.locator("[data-testid='studio-words']").inner_text() if page.locator("[data-testid='studio-words']").count() else ""
        step("Plain words", "customers" in words, text=words[:500])

        page.goto(a.ui + "/agent-operations", wait_until="domcontentloaded", timeout=120_000)
        al = page.locator("[data-testid='agentops-intelligence-studio-link']")
        try:
            al.wait_for(timeout=90_000)
            page.screenshot(path=str(out / "14_agent_operations_link.png"))
            al.click()
            page.wait_for_url("**/deal-desk/intelligence", timeout=60_000)
            step("Agent Operations links to the Studio", True)
        except Exception as e:  # noqa: BLE001
            page.screenshot(path=str(out / "14_agent_operations_link.png"))
            step("Agent Operations links to the Studio", False, error=str(e)[:200])
        step("No page errors", not errors, errors=errors[:5])
        b.close()
    (out / "report.json").write_text(json.dumps(rep, indent=1))
    print(f"{len(rep['steps']) - len(rep['failures'])}/{len(rep['steps'])} steps passed -> {out}")
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
