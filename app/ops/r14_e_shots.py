"""PLAN_R14 Session E: screenshots of every screen E changed, at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_e_shots.py [--ui http://127.0.0.1:5500] [--only id,id]

Needs the UI, the Workspace API (identity) and the Deal Desk API running. Mints a session in the identity store (no
password read or printed). Writes docs/v5/r14_review/e/<step>_<size>.png and shots.json (found / page errors /
sideways-scroll probe / text checks per step).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "e"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731


def idle(page: Page, ms: int = 800, timeout: int = 60_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(ms)


def open_deal(page: Page, ui: str, pid: str, step: str, sel: str) -> None:
    page.goto(f"{ui}/deal-desk/{pid}?step={step}", wait_until="domcontentloaded", timeout=180_000)
    page.wait_for_selector(sel, timeout=240_000)
    idle(page, 1500)


def tile_info(page: Page, tile: str) -> str:
    t = page.locator(T(tile))
    t.locator('button[aria-label^="About"]').first.click()
    page.wait_for_timeout(1500)
    return t.inner_text()


def s_tiles_rwa(pid: str) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "proposal", T("dealdesk-kpis"))
        page.wait_for_selector(T("dealdesk-kpi-rwa"), timeout=120_000)
        idle(page, 2500)
        txt = tile_info(page, "dealdesk-kpi-rwa")
        return {"rwa_info": "risk weight" in txt and "SA exposure" in txt, "approval": page.locator(T("dealdesk-kpi-approval")).inner_text()[:120]}
    return f


def s_tiles_approval(pid: str) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "proposal", T("dealdesk-kpis"))
        idle(page, 2500)
        txt = tile_info(page, "dealdesk-kpi-approval")
        return {"approval_info": "→" in txt, "text": txt[:300]}
    return f


def s_review(pid: str, chip: str | None = None) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "review", T("dealdesk-step-review-view"))
        page.wait_for_selector(T("review-workspace"), timeout=300_000)
        idle(page, 1500)
        out = {"headline": page.locator(T("review-answer-headline")).inner_text()[:300]}
        if page.locator(T("findings-counts")).count():
            out["counts"] = page.locator(T("findings-counts")).inner_text()
            out["legend"] = page.locator(T("memo-legend")).inner_text()
        if chip and page.locator(T(f"findings-chip-{chip}")).count():
            page.locator(T(f"findings-chip-{chip}")).click()
            page.wait_for_timeout(600)
            page.locator(T("review-findings")).scroll_into_view_if_needed()
            out["chip_rows"] = page.locator(f'{T("review-findings")} {T("review-finding")}').count()
        else:
            page.locator(T("review-findings")).scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        return out
    return f


def s_counter(pid: str) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "review", T("dealdesk-step-review-view"))
        page.wait_for_selector(T("review-counters"), timeout=300_000)
        idle(page, 1000)
        page.locator(T("review-counters")).scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        cures = page.locator(T("counter-cure")).count()
        if page.locator(T("counter-cures")).count():
            page.locator(T("counter-cures")).first.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        return {"cures": cures, "not_curable": page.locator(f'{T("counter-cure")}[data-curable="0"]').count()}
    return f


def s_analysis(pid: str) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "analysis", T("dealdesk-step-analysis-view"))
        page.wait_for_selector(T("dealdesk-account-behaviour"), timeout=240_000)
        page.wait_for_selector(T("dealdesk-capacity"), timeout=120_000)
        page.locator(T("dealdesk-account-behaviour")).scroll_into_view_if_needed()
        idle(page, 1200)
        return {"capacity": page.locator(T("dealdesk-capacity")).inner_text()[:160],
                "bridge": page.locator(T("dealdesk-raroc-bridge")).inner_text()[:300] if page.locator(T("dealdesk-raroc-bridge")).count() else None}
    return f


def s_why(pid: str) -> Callable[[Page, str], dict]:
    def f(page: Page, ui: str) -> dict:
        open_deal(page, ui, pid, "recommendation", T("dealdesk-composer"))
        page.locator(T("dealdesk-composer")).fill("Why does the ask fail?")
        page.locator(T("dealdesk-send")).click()
        t0 = time.time()
        while time.time() - t0 < 240:
            body = page.locator("main").inner_text()
            if "The ask fails on" in body:
                break
            page.wait_for_timeout(1500)
        idle(page, 1500)
        loc = page.get_by_text("The ask fails on").last
        if loc.count():
            loc.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        return {"answered": "The ask fails on" in page.locator("main").inner_text()}
    return f


STEPS: list[tuple[str, Callable[[Page, str], dict]]] = [
    ("twa_tiles_rwa_info", s_tiles_rwa("R12-TWA")),
    ("twa_tiles_approval_info", s_tiles_approval("R12-TWA")),
    ("twa_review_findings", s_review("R12-TWA")),
    ("twa_review_fin_quality_chip", s_review("R12-TWA", "financial_quality")),
    ("twa_review_counter_cures", s_counter("R12-TWA")),
    ("twa_analysis_capacity_bridge", s_analysis("R12-TWA")),
    ("twa_why_fails", s_why("R12-TWA")),
    ("twb_review_findings", s_review("R12-TWB")),
    ("twb_tiles_rwa_info", s_tiles_rwa("R12-TWB")),
    ("dd06_review_findings", s_review("DD-06")),
    ("dd06_tiles_approval_info", s_tiles_approval("DD-06")),
    ("dd06_analysis_capacity", s_analysis("DD-06")),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    only = {x for x in a.only.split(",") if x}
    token = mint()
    report: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for size in a.sizes.split(","):
            w, h = (int(x) for x in size.split("x"))
            ctx = br.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            # the brief speaks first once a day and opens the Noor panel; these screens are the deal page, so mark it spoken
            ctx.add_init_script("(() => { const g = Storage.prototype.getItem; Storage.prototype.getItem = function (k) {"
                                " return String(k).startsWith('noor.spoke.') ? '1' : g.call(this, k); }; })()")
            for sid, fn in STEPS:
                if only and sid not in only:
                    continue
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)[:200]))
                rec: dict[str, Any] = {"step": sid, "size": size}
                try:
                    rec["checks"] = fn(page, a.ui)
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001
                    rec["found"] = False
                    rec["error"] = str(e)[:300]
                try:
                    page.screenshot(path=str(OUT / f"{sid}_{size}.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                except Exception as e:  # noqa: BLE001
                    rec["shot_error"] = str(e)[:200]
                rec["page_errors"] = errors
                report.append(rec)
                print(sid, size, "ok" if rec.get("found") else "MISSING", rec.get("checks") or rec.get("error", ""), flush=True)
                page.close()
            ctx.close()
        br.close()
    (OUT / "shots.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
