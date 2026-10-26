"""PLAN_R14 Session r: screenshots of every screen r changed, reached by clicking from the Brief, at 1440x900 and
1280x800 (N6, N8). Reuses ops/r13_m_walkthrough.py patterns (minted session, page-error capture, sideways probe).

  .venv/bin/python ops/r14_r_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Writes docs/v5/r14_review/r/<step>_<size>.png and walkthrough.json (found / error / page errors / probe per step).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402
from r13_m_walkthrough import idle, settle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "r"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LINE = 'li[data-testid="noor-line-crm:CRM-9.23"]'


def _brief(page: Page, ui: str) -> None:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page, 1200)


def _line(page: Page, sel: str = LINE):
    loc = page.locator(sel)
    if not loc.count() and page.locator(T("noor-more")).count():
        page.locator(T("noor-more")).first.click()
        page.wait_for_timeout(600)
    loc = page.locator(sel).first
    loc.scroll_into_view_if_needed()
    loc.hover()
    page.wait_for_timeout(400)
    return loc


def _issue_ready(page: Page) -> None:
    page.wait_for_selector(T("issue-view"), timeout=120_000)
    settle(page, T("regulatory-issue-page"), 60_000)
    idle(page, 800)


def _to(page: Page, testid: str) -> None:
    el = page.locator(T(testid)).first
    el.evaluate("e => e.scrollIntoView({block: 'start'})")
    page.wait_for_timeout(700)


def s_brief_line(page: Page, ui: str, ctx: dict) -> dict:
    _brief(page, ui)
    ln = _line(page)
    return {"line": ln.inner_text()[:300]}


def s_open_issue(page: Page, ui: str, ctx: dict) -> dict:
    _brief(page, ui)
    _line(page).locator(T("noor-open")).click()
    _issue_ready(page)
    return {"url": page.url, "headline": page.locator(T("issue-headline")).inner_text(),
            "plain_words": page.locator(T("issue-plain-words")).inner_text()[:400],
            "plain_words_ok": page.locator(T("issue-plain-words")).get_attribute("data-ok"),
            "bank": page.locator(T("issue-bank-rate")).inner_text(), "required": page.locator(T("issue-required-rate")).inner_text()}


def section(testid: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        if not page.locator(T("issue-view")).count():
            s_open_issue(page, ui, ctx)
        _to(page, testid)
        return {"section": testid, "text": page.locator(T(testid)).first.inner_text()[:500]}
    return f


def s_list(page: Page, ui: str, ctx: dict) -> dict:
    if not page.locator(T("issue-back-list")).count():
        s_open_issue(page, ui, ctx)
    page.locator(T("issue-back-list")).click()
    page.wait_for_selector(T("issues-list"), timeout=120_000)
    idle(page, 800)
    return {"rows": page.locator(T("issues-row")).count(), "url": page.url}


def from_list(issue: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        if not page.locator(T("issues-list")).count():
            s_list(page, ui, ctx)
        page.locator(f'{T("issues-row")}[data-issue="{issue}"]').click()
        _issue_ready(page)
        out = {"issue": issue, "headline": page.locator(T("issue-headline")).inner_text()}
        page.go_back()
        page.wait_for_selector(T("issues-list"), timeout=60_000)
        idle(page, 500)
        page.go_forward()
        _issue_ready(page)
        return out
    return f


def s_bridge_link(page: Page, ui: str, ctx: dict) -> dict:
    """From the CRM-9.23 bridge, the haircut driver opens the CRM-10.8 view (clicks, not URLs)."""
    s_open_issue(page, ui, ctx)
    _to(page, "issue-bridge")
    page.locator(f'{T("issue-bridge-steps")} li[data-step="haircut"] button').click()
    _issue_ready(page)
    return {"url": page.url, "headline": page.locator(T("issue-headline")).inner_text()}


def s_why(page: Page, ui: str, ctx: dict) -> dict:
    _brief(page, ui)
    _line(page).locator(T("noor-why")).click()
    page.wait_for_selector(T("noor-why-answer"), timeout=120_000)
    idle(page, 2500)
    chart = page.locator(T("noor-why-chart"))
    if chart.count():
        chart.last.evaluate("e => e.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(1200)
    return {"answer": page.locator(T("noor-why-answer")).first.inner_text()[:500], "chart": chart.count()}


def s_options(page: Page, ui: str, ctx: dict) -> dict:
    _brief(page, ui)
    _line(page).locator(T("noor-options")).click()
    page.wait_for_selector(T("noor-turn-options"), timeout=120_000)
    idle(page, 1500)
    opt = page.locator(T("noor-turn-options")).last
    opt.evaluate("e => e.scrollIntoView({block: 'start'})")
    page.wait_for_timeout(800)
    return {"options": opt.inner_text()[:800]}


def s_ri_tab(tab: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(f"{ui}/studio", wait_until="domcontentloaded")
        page.locator('a[href="/studio/regulatory-intelligence"]').first.click()
        page.wait_for_selector(T(f"ri-tab-{tab}"), timeout=120_000)
        page.locator(T(f"ri-tab-{tab}")).click()
        idle(page, 1500)
        return {"tab": tab, "notes_as_text": page.locator("main p.text-\\[11px\\]").count()}
    return f


def s_studio(page: Page, ui: str, ctx: dict) -> dict:
    """Analysis Studio (clicked from Regulatory intelligence's own header link back): the library says in words when
    the method service is not switched on (R13 X gap 1: no API path on screen)."""
    page.goto(f"{ui}/studio", wait_until="domcontentloaded")
    idle(page, 2000)
    html = page.inner_text("main")
    return {"api_path_on_screen": "/studio?" in html, "raw_json_on_screen": '{"' in html}


STEPS: list[tuple[str, str, Callable[[Page, str, dict], dict]]] = [
    ("01_brief_regulatory_line", "K2 K4", s_brief_line),
    ("02_issue_floor_top", "K2 K4", s_open_issue),
    ("03_issue_floor_tables", "K4", section("issue-table-by_vintage")),
    ("04_issue_floor_bridge", "K4", section("issue-bridge")),
    ("05_issue_floor_concentration_impact", "K4", section("issue-concentration")),
    ("06_issue_floor_actions", "K2 K4", section("issue-actions")),
    ("07_issue_floor_exposures_footer", "K2 K4", section("issue-exposures")),
    ("08_issue_floor_source", "K2", section("issue-footer")),
    ("10_issues_list", "K2", s_list),
    ("11_issue_cross_default", "K4", from_list("crm:CRM-6.12")),
    ("12_issue_ecl_anomalies", "K2", from_list("ecl:anomalies:2026Q3")),
    ("13_issue_large_exposure", "K2", from_list("le:near")),
    ("14_issue_write_off", "K4", from_list("crm:CRM-12.5")),
    ("15_issue_haircut_from_bridge", "K4", s_bridge_link),
    ("20_brief_why_floor", "K4", s_why),
    ("21_brief_what_to_do_floor", "K2", s_options),
    ("30_ri_requirements_notes", "X gap 1", s_ri_tab("requirements")),
    ("31_ri_conflicts_notes", "X gap 1", s_ri_tab("conflicts")),
    ("32_studio_library_plain", "X gap 1", s_studio),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict[str, Any]] = []
    path = OUT / "walkthrough.json"
    try:
        kept = [r for r in json.loads(path.read_text()) if isinstance(r, dict)]
    except (OSError, ValueError):
        kept = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(60_000)
            for sid, items, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only):
                    continue
                errors: list[str] = []
                handler = lambda e: errors.append(str(e)[:200])  # noqa: E731
                page.on("pageerror", handler)
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "items": items, "size": tag}
                try:
                    rec["checks"] = fn(page, ui, {})
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001
                    rec["found"] = False
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                rec["seconds"] = round(time.time() - t0, 1)
                try:
                    page.screenshot(path=str(OUT / f"{sid}_{tag}.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                except Exception as e:  # noqa: BLE001
                    rec["probe_error"] = str(e)[:120]
                rec["page_errors"] = errors
                try:
                    page.remove_listener("pageerror", handler)
                except Exception:  # noqa: BLE001
                    pass
                if page.is_closed():
                    page = bctx.new_page()
                    page.set_default_timeout(60_000)
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} {rec['seconds']}s", flush=True)
                done = {(r["step"], r["size"]) for r in report}
                path.write_text(json.dumps([r for r in kept if (r["step"], r["size"]) not in done] + report, indent=1,
                                           default=str))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"]]
    print(f"{len(report) - len(miss)} / {len(report)} found")
    return 0 if not miss else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {x for x in a.only.split(",") if x}))
