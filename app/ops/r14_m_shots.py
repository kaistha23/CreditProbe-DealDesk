"""R14 session m: screenshots of every screen m changed, at 1440x900 and 1280x800, by clicking (N6), into
docs/v5/r14_review/m/<step>_<size>.png, with page errors and a sideways-scroll probe in walk.json.

    .venv/bin/python ops/r14_m_shots.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only 01,02]

Steps
  01_whatif_recommend        What-If landing → "What scenario should I run?" button: regime strip first, then the ideas
  02_whatif_recommend_ideas  the same answer scrolled to the ideas (revenue fall by sector, trade disruption, oil reversal)
  03_whatif_reversal_result  click the oil-reversal idea → Execute: the compact regime strip above the result
  04_whatif_calibrated       What-If landing → "Mild, moderate, severe": regime strip, regime note, evidence (conditional)
  05_whatif_calibrated_evidence  the evidence list (regime, conditional on today's level, revenue channel)
  06_stress_lab_twa          Deal Desk twin A → Stress step: regime strip on top of the Stress Lab, oil reversal rows
Uses a minted session (no password read or printed).
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

OUT = V5 / "docs" / "v5" / "r14_review" / "m"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731


def idle(page: Page, ms: int = 800, timeout: int = 45_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001 - a long poll keeps the network busy
        pass
    page.wait_for_timeout(ms)


def _landing(page: Page, ui: str) -> None:
    page.goto(f"{ui}/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(T("whatif-brainstorm"), timeout=120_000)
    idle(page, 1200)


def s_recommend(page: Page, ui: str, ctx: dict) -> dict:
    _landing(page, ui)
    page.locator(T("whatif-brainstorm")).click()
    page.wait_for_selector(T("whatif-ideas"), timeout=240_000)
    idle(page, 1200)
    ctx["rec_thread"] = page.url
    reg = page.locator('[data-testid^="whatif-regime-"][data-regime]').first
    reg.scroll_into_view_if_needed()
    ideas = page.locator(T("whatif-ideas")).first.inner_text()
    return {"url": page.url, "regime": reg.get_attribute("data-regime"), "regime_text": reg.inner_text()[:400],
            "ideas": ideas[:600], "first_idea": ideas.split("\n")[0], "oil_fall_from_average": "Historical: oil" in ideas}


def s_recommend_ideas(page: Page, ui: str, ctx: dict) -> dict:
    if not ctx.get("rec_thread"):
        s_recommend(page, ui, ctx)
    else:
        page.goto(ctx["rec_thread"], wait_until="domcontentloaded")
        page.wait_for_selector(T("whatif-ideas"), timeout=120_000)
        idle(page, 800)
    page.locator(T("whatif-ideas")).first.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    return {"ideas": page.locator(T("whatif-ideas")).first.inner_text()[:600]}


def s_reversal(page: Page, ui: str, ctx: dict) -> dict:
    if not ctx.get("rec_thread"):
        s_recommend(page, ui, ctx)
    else:
        page.goto(ctx["rec_thread"], wait_until="domcontentloaded")
        page.wait_for_selector(T("whatif-ideas"), timeout=120_000)
        idle(page, 800)
    btn = page.locator(f'{T("whatif-ideas")} button', has_text="Oil reversal").first
    btn.click()
    page.wait_for_selector(T("whatif-proposal-execute"), timeout=180_000)
    idle(page, 800)
    page.locator(T("whatif-proposal-execute")).last.click()
    t0 = time.time()
    while time.time() - t0 < 300:
        q = page.locator('[data-testid^="whatif-question-"] [data-testid^="whatif-option-"]')
        if q.count() and not page.locator(T("whatif-result")).count():
            q.first.click()   # the method question (Delta method or XGBoost): first option
            page.wait_for_timeout(2500)
            page.wait_for_timeout(1500)
        if page.locator('[data-testid^="whatif-regime-"][data-regime]').count() >= 2 or page.locator(T("whatif-result")).count():
            break
        page.wait_for_timeout(1500)
    idle(page, 1500, 120_000)
    regs = page.locator('[data-testid^="whatif-regime-"][data-regime]')
    regs.last.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    return {"regime_blocks": regs.count(), "url": page.url}


def s_calibrated(page: Page, ui: str, ctx: dict) -> dict:
    _landing(page, ui)
    page.locator(T("whatif-calibrated")).click()
    page.wait_for_selector(T("whatif-scenario-set"), timeout=300_000)
    idle(page, 1500, 60_000)
    ctx["cal_thread"] = page.url
    reg = page.locator('[data-testid^="whatif-regime-"][data-regime]').first
    reg.scroll_into_view_if_needed()
    note = page.locator(T("whatif-scenario-regime-note"))
    return {"regime": reg.get_attribute("data-regime"), "note": note.first.inner_text()[:400] if note.count() else ""}


def s_calibrated_evidence(page: Page, ui: str, ctx: dict) -> dict:
    if not ctx.get("cal_thread"):
        s_calibrated(page, ui, ctx)
    else:
        page.goto(ctx["cal_thread"], wait_until="domcontentloaded")
        page.wait_for_selector(T("whatif-scenario-set"), timeout=180_000)
        idle(page, 1000)
    ev = page.locator(T("whatif-scenario-evidence")).first
    ev.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    return {"evidence": ev.inner_text()[:800]}


def s_stress(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk/R12-TWA", wait_until="domcontentloaded")
    # R14 x: after f's merge Stress is a header button (enabled from Structure) and the R12 Stress Lab is the
    # "Full Stress Lab" section under the structures matrix; reach it by clicking.
    page.wait_for_selector(T("dealdesk-step-structure"), timeout=180_000)
    idle(page, 800, 60_000)
    page.locator(T("dealdesk-step-structure")).click()
    page.wait_for_selector(T("dealdesk-step-structure-view"), timeout=300_000)
    page.wait_for_selector(f'{T("dealdesk-stress-button")}:not([disabled])', timeout=120_000)
    idle(page, 800, 60_000)
    page.locator(T("dealdesk-stress-button")).click()
    page.wait_for_selector(T("flow-full-stress-lab"), timeout=300_000)
    page.locator(f'{T("flow-full-stress-lab")} > summary').click()
    page.wait_for_selector(T("stress2-tier"), timeout=300_000)
    idle(page, 1500, 120_000)
    reg = page.locator(T("stress2-regime"))
    if reg.count():
        reg.first.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    lad = page.locator(T("stress2-ladder"))
    return {"regime": reg.first.get_attribute("data-regime") if reg.count() else None,
            "tier": page.locator(T("stress2-tier")).inner_text(),
            "oil_rows": [x for x in (lad.first.inner_text().split("\n") if lad.count() else []) if "Oil" in x][:4]}


STEPS: list[tuple[str, Callable[[Page, str, dict], dict]]] = [
    ("01_whatif_recommend", s_recommend), ("02_whatif_recommend_ideas", s_recommend_ideas),
    ("03_whatif_reversal_result", s_reversal), ("04_whatif_calibrated", s_calibrated),
    ("05_whatif_calibrated_evidence", s_calibrated_evidence), ("06_stress_lab_twa", s_stress),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    ctx: dict[str, Any] = {}
    report = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(60_000)
            ctx.clear()
            for sid, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only):
                    continue
                errors: list[str] = []
                handler = lambda e: errors.append(str(e)[:200])  # noqa: E731
                page.on("pageerror", handler)
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "size": tag}
                try:
                    rec["checks"] = fn(page, ui, ctx)
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
                    rec["found"] = False
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                rec["seconds"] = round(time.time() - t0, 1)
                try:
                    page.screenshot(path=str(OUT / f"{sid}_{tag}.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                except Exception as e:  # noqa: BLE001
                    rec["probe_error"] = str(e)[:120]
                rec["page_errors"] = errors
                page.remove_listener("pageerror", handler)
                if page.is_closed():
                    page = bctx.new_page()
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} {rec['seconds']}s", flush=True)
            bctx.close()
        b.close()
    path = OUT / "walk.json"
    try:
        kept = [r for r in json.loads(path.read_text()) if isinstance(r, dict)]
    except (OSError, ValueError):
        kept = []
    done = {(r["step"], r["size"]) for r in report}
    path.write_text(json.dumps([r for r in kept if (r["step"], r["size"]) not in done] + report, indent=1, default=str))
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
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
