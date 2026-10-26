"""PLAN_R16 session c: click-through walk of the credit response (Part B of the demo), 1440x900 and 1280x800.

  .venv/bin/python ops/r16_c_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--photos]

Every screen is reached by clicking (N6); the only goto is Deal Desk after sign-in. The upload uses the file chooser with
customer 2's business request (PDF, or the photos with --photos) and its documents (PDF), as Anne does. Screens and the
report go to docs/v5/r16_review/c/<step>_<size>.png and walk.json.
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
from r14_u_walkthrough import DEV_OVERLAY, idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "c"
C2 = V5 / "data" / "dealdesk" / "demo_customers" / "c2_sawaed_al_bina"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LONG = 600_000


def text(page: Page, sel: str, n: int = 300) -> str:
    loc = page.locator(sel).first
    return " ".join(loc.inner_text().split())[:n] if loc.count() else ""


def to(page: Page, sel: str) -> None:
    page.locator(sel).first.scroll_into_view_if_needed()
    page.wait_for_timeout(400)


def s_home(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-credit-response"), timeout=LONG)
    idle(page, 600)
    if page.locator(T("noor-panel")).count() and page.locator(T("noor-panel")).first.is_visible():
        page.locator(T("ask-noor")).first.click()  # the demo runs with Noor's panel closed (DEMO_SCRIPT checklist)
        page.wait_for_timeout(500)
    return {}


def s_open(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-credit-response")).first.click()
    page.wait_for_selector(T("credit-response-upload"), timeout=120_000)
    idle(page, 600)
    return {"plain": text(page, T("credit-response-plain"), 300), "demo": text(page, T("credit-response-demo"), 200)}


def s_choose(page: Page, ui: str, ctx: dict) -> dict:
    req = sorted((C2 / "business_request").glob("business_request_p*.jpg")) if ctx.get("photos") else [C2 / "business_request" / "business_request.pdf"]
    docs = sorted((C2 / "pdf").glob("*.pdf"))
    page.locator(T("credit-response-file")).set_input_files([str(p) for p in req + docs])
    page.wait_for_selector(T("credit-response-files"), timeout=30_000)
    return {"files": text(page, T("credit-response-files"), 200)}


def s_start(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("credit-response-start")).click()
    page.wait_for_selector(T("credit-response-steps"), timeout=300_000)
    page.wait_for_selector(f'{T("credit-response-step-check")}[data-status="done"]', timeout=LONG)
    return {"steps": text(page, T("credit-response-steps"), 400)}


def s_done(page: Page, ui: str, ctx: dict) -> dict:
    page.wait_for_selector(T("credit-response-paper"), timeout=LONG)
    idle(page, 800)
    ctx["url"] = page.url
    return {"decision": text(page, T("credit-response-decision"), 120), "plain": text(page, T("credit-response-plain"), 400)}


def s_step_open(page: Page, ui: str, ctx: dict) -> dict:
    done = page.locator(f'{T("credit-response-steps-done")} summary')
    if done.count():
        done.first.click()
        page.wait_for_selector(T("credit-response-step-recommendation"), timeout=30_000)
    page.locator(f'{T("credit-response-step-recommendation")} button').first.click()
    page.wait_for_selector(T("credit-response-step-recommendation-plain"), timeout=30_000)
    return {"plain": text(page, T("credit-response-step-recommendation-plain"), 300)}


def s_comments(page: Page, ui: str, ctx: dict) -> dict:
    done = page.locator(f'{T("credit-response-steps-done")} summary')
    if done.count():
        done.first.click()  # fold the steps away again
    to(page, T("credit-response-section-cr_file"))
    return {"comments": text(page, T("credit-response-section-cr_file"), 600)}


def s_projects(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("credit-response-section-projects"))
    return {"projects": text(page, T("credit-response-section-projects"), 400)}


def s_recommendation(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("credit-response-section-recommendation"))
    return {"recommendation": text(page, T("credit-response-section-recommendation"), 600)}


def s_brief(page: Page, ui: str, ctx: dict) -> dict:
    page.evaluate("window.scrollTo(0, 0)")
    page.locator(T("credit-response-tab-brief")).click()
    page.wait_for_selector(T("credit-response-brief"), timeout=30_000)
    return {"brief": text(page, T("credit-response-brief"), 400)}


def s_request(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("credit-response-tab-request")).click()
    page.wait_for_selector(T("credit-response-request"), timeout=30_000)
    return {"request": text(page, T("credit-response-request"), 300)}


def s_downloads(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("credit-response-tab-response")).click()
    page.wait_for_selector(T("credit-response-docx"), timeout=30_000)
    out = {}
    for tid in ("credit-response-docx", "credit-response-pdf"):
        with page.expect_download(timeout=180_000) as d:
            page.locator(T(tid)).click()
        dl = d.value
        p = OUT / f"download_{ctx['tag']}_{dl.suggested_filename}"
        dl.save_as(str(p))
        out[tid] = {"name": dl.suggested_filename, "bytes": p.stat().st_size}
    page.locator(T("credit-response-tab-brief")).click()
    with page.expect_download(timeout=120_000) as d:
        page.locator(T("credit-response-brief-docx")).click()
    out["brief"] = d.value.suggested_filename
    page.locator(T("credit-response-tab-response")).click()
    return out


def s_open_deal(page: Page, ui: str, ctx: dict) -> dict:
    page.evaluate("window.scrollTo(0, 0)")
    page.locator(T("credit-response-open-deal")).click()
    page.wait_for_url("**/deal-desk/R16-C2**", timeout=120_000)
    idle(page, 1500)
    return {"url": page.url}


def s_back(page: Page, ui: str, ctx: dict) -> dict:
    page.go_back()
    page.wait_for_selector(T("credit-response-paper"), timeout=180_000)
    return {"url": page.url}


STEPS: list[tuple[str, str, Callable[[Page, str, dict], dict]]] = [
    ("00_deal_desk", "entry", s_home), ("01_credit_response", "landing", s_open), ("02_files_chosen", "upload", s_choose),
    ("03_running", "steps", s_start), ("04_response", "response", s_done), ("05_step_plain_words", "steps", s_step_open),
    ("06_credit_comments", "response", s_comments), ("07_projects", "response", s_projects), ("08_recommendation", "response", s_recommendation),
    ("09_rm_brief", "brief", s_brief), ("10_request_as_read", "request", s_request), ("11_downloads", "word pdf", s_downloads),
    ("12_open_deal", "deal", s_open_deal), ("13_back", "back", s_back),
]


def run(ui: str, sizes: list[tuple[int, int]], photos: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(90_000)
            ctx: dict[str, Any] = {"tag": tag, "photos": photos}
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            for sid, items, fn in STEPS:
                errors.clear()
                console.clear()
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "items": items, "size": tag, "photos": photos}
                try:
                    rec["checks"] = fn(page, ui, ctx)
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
                    rec["found"] = False
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                rec["seconds"] = round(time.time() - t0, 1)
                name = f"{sid}{'_photos' if photos else ''}_{tag}"
                try:
                    page.screenshot(path=str(OUT / f"{name}.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                    rec["dev_overlay"] = page.evaluate(DEV_OVERLAY)
                except Exception as e:  # noqa: BLE001
                    rec["probe_error"] = str(e)[:120]
                rec["page_errors"] = list(errors)
                rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                rec["clean"] = not rec["page_errors"] and not rec["console_errors"]
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} "
                      f"{'clean' if rec['clean'] else 'ERRORS ' + json.dumps(rec['page_errors'] + rec['console_errors'])[:300]} {rec['seconds']}s", flush=True)
            bctx.close()
        b.close()
    path = OUT / ("walk_photos.json" if photos else "walk.json")
    path.write_text(json.dumps(report, indent=1, default=str))
    miss = [r for r in report if not r["found"]]
    print(f"WALK {'PASS' if not miss else 'MISS ' + str(len(miss))}: {sum(1 for r in report if r['found'])}/{len(report)} found, "
          f"{sum(1 for r in report if not r['clean'])} with errors")
    return 0 if not miss else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--photos", action="store_true")
    a = ap.parse_args()
    raise SystemExit(run(a.ui, [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")], a.photos))  # type: ignore[misc]
