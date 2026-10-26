"""PLAN_R13 Session H: Home (Brief and Ask tabs) and Noor's panel, screenshots at 1440x900 and 1280x800 with an
overflow probe and the checks J1-J3 ask for.

  .venv/bin/python ops/r13_home_shots.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800]

Writes docs/v5/r13_home/*.png and docs/v5/r13_home/home_walkthrough.json. Needs the UI and the v5 services running.
Mints a session in the identity store; no password or secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_home"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731


def probe(page: Page, name: str, report: list, sel: str | None = None) -> dict:
    page.screenshot(path=str(OUT / f"{name}.png"))
    r = page.evaluate(PROBE, sel)
    r["surface"] = name
    report.append(r)
    print(name, "overflow" if r.get("overflow") else "ok")
    return r


def run(ui: str, sizes: list[tuple[int, int]]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    checks: dict = {}
    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            ctx = b.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            # Brief tab is the landing page.
            page.goto(f"{ui}/", wait_until="domcontentloaded")
            page.wait_for_selector(T("home-tabs"), timeout=120_000)
            checks[f"{tag}.landing_tab"] = page.locator(T("home-tabs")).get_attribute("data-tab")
            page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
            wait_idle(page, 1200)
            checks[f"{tag}.headline"] = page.locator(T("noor-headline")).first.inner_text()
            checks[f"{tag}.lines_shown"] = page.locator(f'{T("noor-home-brief-lines")} > li').count()
            checks[f"{tag}.n_more"] = page.locator(T("noor-more")).first.inner_text() if page.locator(T("noor-more")).count() else ""
            checks[f"{tag}.attention_panel_on_page"] = page.locator(T("attention-panel")).count() + \
                page.locator("text=Requires attention").count()
            probe(page, f"01_brief_{tag}", report)
            first = page.locator(f'{T("noor-home-brief-lines")} > li').first
            first.hover()
            page.wait_for_timeout(400)
            checks[f"{tag}.actions_on_hover"] = first.locator(T("noor-why")).evaluate("e => getComputedStyle(e.parentElement).opacity")
            first.screenshot(path=str(OUT / f"02_brief_line_hover_{tag}.png"))
            # Why on a line with an evidence card opens the Cockpit drawer.
            with_ev = page.locator(f'{T("noor-home-brief-lines")} > li').filter(has=page.locator(T("noor-why")))
            checks[f"{tag}.speaker_state"] = page.locator(T("noor-speaker")).first.get_attribute("data-voice-state")
            # Ask tab.
            page.locator(T("home-tab-ask")).click()
            page.wait_for_selector(T("home-ask"), timeout=30_000)
            wait_idle(page, 1000)
            checks[f"{tag}.ask_title"] = page.locator(T("home-ask-title")).inner_text()
            checks[f"{tag}.placeholder"] = page.locator(T("cockpit-v4-question")).get_attribute("placeholder")
            checks[f"{tag}.starters"] = page.locator(T("cockpit-v4-prompt")).count()
            checks[f"{tag}.work_cards"] = page.locator(T("home-work-card")).count()
            probe(page, f"03_ask_{tag}", report)
            # Noor's panel: the brief in the same component, then a question it would have refused before.
            page.locator(T("ask-noor")).click()
            page.wait_for_selector(f'{T("noor-panel")} {T("noor-turn-brief")}', timeout=60_000)
            wait_idle(page, 800)
            probe(page, f"04_panel_brief_{tag}", report, T("noor-panel"))
            page.locator(T("noor-input")).fill("Which borrowers moved into Stage 2 this quarter?")
            checks[f"{tag}.asked_in_panel"] = "Which borrowers moved into Stage 2 this quarter?"
            page.locator(T("noor-input")).press("Enter")
            try:
                page.wait_for_selector(f'{T("noor-turn-routed")}, {T("noor-turn-error")}', timeout=60_000)
            except Exception:  # noqa: BLE001
                pass
            panel_text = page.locator(T("noor-thread")).inner_text()
            checks[f"{tag}.refusal_sentence"] = "could not tie that" in panel_text
            checks[f"{tag}.routed"] = page.locator(T("noor-turn-routed")).count()
            checks[f"{tag}.url_after_ask"] = page.url.replace(ui, "")
            wait_idle(page, 1500)
            probe(page, f"05_panel_routed_{tag}", report, T("noor-panel"))
            # A scenario question in the panel goes to What-If (the panel stays open on the thread).
            page.locator(T("noor-input")).fill("What if Brent falls 30% over the next year?")
            page.locator(T("noor-input")).press("Enter")
            try:
                page.wait_for_url("**/what-if/thread/**", timeout=60_000)
            except Exception:  # noqa: BLE001
                pass
            checks[f"{tag}.whatif_url"] = page.url.replace(ui, "")
            checks[f"{tag}.whatif_routed_turn"] = page.locator(T("noor-turn-routed")).count()
            wait_idle(page, 2500)
            probe(page, f"05b_panel_whatif_{tag}", report, T("noor-panel"))
            # Voice settings: the reader's own voice and the clear state when no voice is installed.
            page.locator('[aria-label="Noor\'s name and voice"]').click()
            page.wait_for_selector(T("noor-my-voice"), timeout=10_000)
            page.locator(T("noor-speaker")).first.click()
            page.wait_for_timeout(3000)
            checks[f"{tag}.voice_state_after_click"] = page.locator(T("noor-speaker")).first.get_attribute("data-voice-state")
            checks[f"{tag}.voice_on_after_click"] = page.locator(T("noor-speaker")).first.get_attribute("data-voice-on")
            checks[f"{tag}.voice_line"] = page.locator(T("noor-my-voice-state")).inner_text()
            page.locator(T("noor-panel")).screenshot(path=str(OUT / f"06_panel_voice_{tag}.png"))
            checks[f"{tag}.voice_kept_in_storage"] = page.evaluate(
                "() => Object.keys(localStorage).filter(k => k.startsWith('noor.voice.')).map(k => localStorage.getItem(k))")
            # Evidence: Why on the Brief tab opens the Cockpit attention card when the line has one.
            page.goto(f"{ui}/?tab=brief", wait_until="domcontentloaded")
            page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
            wait_idle(page, 800)
            if page.locator(T("noor-panel")).count():
                page.keyboard.press("Escape")
            line = page.locator('[data-testid="noor-line-appetite:Construction"]')
            first = line.first if line.count() else page.locator(f'{T("noor-home-brief-lines")} > li').first
            first.hover()
            first.locator(T("noor-why")).click()
            page.wait_for_timeout(4000)
            checks[f"{tag}.why_opened"] = ("drawer" if page.locator(T("attention-drawer")).count()
                                           else "panel" if page.locator(T("noor-turn-why")).count() else "none")
            probe(page, f"07_why_{tag}", report)
            checks[f"{tag}.page_errors"] = errors
            ctx.close()
        b.close()
    out = {"checks": checks, "overflow": [r for r in report if r.get("overflow")], "surfaces": report}
    (OUT / "home_walkthrough.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    a = ap.parse_args()
    sizes = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    out = run(a.ui, sizes)  # type: ignore[arg-type]
    print(json.dumps(out["checks"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
