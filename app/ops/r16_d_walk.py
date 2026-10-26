"""PLAN_R16 session d: click-through walk of the demo customers on the production build (1440x900 and 1280x800).

  .venv/bin/python ops/r16_d_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Every screen is reached by clicking (N6); the only goto is the first page after sign-in. Screens and walk.json go to
docs/v5/r16_review/d/. Services: core (sign-in), Deal Desk (8508), Borrower 360 (8502) and the UI (next start).
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
from r14_u_walkthrough import DEV_OVERLAY, idle, nav  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "d"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LONG = 240_000


def text(page: Page, sel: str, n: int = 300) -> str:
    loc = page.locator(sel).first
    return " ".join(loc.inner_text().split())[:n] if loc.count() else ""


def to(page: Page, sel: str) -> None:
    page.locator(sel).first.scroll_into_view_if_needed()
    page.wait_for_timeout(400)


def s_home(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 800)
    return {}


def s_list(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-mode-single")).click()
    page.wait_for_selector(T("dealdesk-table"), timeout=120_000)
    page.locator(T("dealdesk-search")).fill("customer file")
    page.wait_for_timeout(300)
    page.locator(T("dealdesk-search")).fill("")
    page.locator(T("dealdesk-search")).fill("naseem")
    page.wait_for_timeout(800)
    to(page, T("dealdesk-row-R16-C1"))
    return {"row": text(page, T("dealdesk-row-R16-C1"), 300)}


def s_packs(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-search")).fill("")
    page.wait_for_timeout(300)
    to(page, T("dealdesk-customer-packs-link"))
    page.locator(T("dealdesk-customer-packs-link")).click()
    page.wait_for_selector(T("packs-cards"), timeout=LONG)
    page.wait_for_selector(T("packs-docs"), timeout=LONG)
    idle(page, 600)
    return {"words": text(page, T("packs-words"), 400), "cards": page.locator('[data-testid^="packs-card-"]').count()}


def s_c1_bank(page: Page, ui: str, ctx: dict) -> dict:
    page.wait_for_selector(T("packs-bank"), timeout=LONG)
    to(page, T("packs-bank"))
    return {"bank": text(page, T("packs-bank-words"), 400), "accounts": page.locator(f'{T("packs-bank-accounts")} tbody tr').count()}


def s_c2(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("packs-card-c2")).click()
    page.wait_for_selector(T("packs-business-request"), timeout=LONG)
    idle(page, 500)
    return {"ask": text(page, T("packs-ask-text"), 200), "br": text(page, T("packs-business-request"), 200)}


def s_c2_checklist(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("packs-checklist"))
    return {"words": text(page, T("packs-checklist-words"), 300), "missing": page.locator(T("packs-doc-missing")).count(),
            "received": page.locator(T("packs-doc-received")).count()}


def s_c4(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("packs-card-c4")).click()
    page.wait_for_selector(T("packs-doc-expired"), timeout=LONG)
    to(page, T("packs-checklist"))
    return {"expired": page.locator(T("packs-doc-expired")).count(), "missing": page.locator(T("packs-doc-missing")).count(),
            "bank": text(page, T("packs-bank-words"), 200)}


def s_c1_deal(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("packs-card-c1")).click()
    page.wait_for_selector(T("packs-open-deal"), timeout=LONG)
    page.locator(T("packs-open-deal")).click()
    page.wait_for_selector(T("dealdesk-stepper"), timeout=LONG)
    idle(page, 1500)
    return {"url": page.url.split("?")[0][-30:], "header": text(page, "main", 300)}


def s_c1_review(page: Page, ui: str, ctx: dict) -> dict:
    btn = page.locator('[data-testid="dealdesk-step-review"]')
    if btn.count():
        btn.first.click()
        page.wait_for_selector(T("review-workspace"), timeout=LONG)
        idle(page, 1500)
    return {"review": text(page, T("review-workspace"), 300)}


def s_b360(page: Page, ui: str, ctx: dict) -> dict:
    page.keyboard.press("Escape")
    nav(page, "borrower-360", "b360-list")
    page.wait_for_selector(T("b360-search"), timeout=LONG)
    page.locator(f'{T("b360-search")} input, input{T("b360-search")}').first.fill("Sawaed")
    page.wait_for_timeout(1500)
    idle(page, 800)
    return {"summary": text(page, T("b360-list-summary"), 200), "rows": text(page, T("b360-list-table"), 400)}


def s_b360_customer(page: Page, ui: str, ctx: dict) -> dict:
    row = page.locator(f'{T("b360-list-table")} tbody tr', has_text="Sawaed Al Bina").first
    row.click()
    page.wait_for_selector(T("b360-customer"), timeout=LONG)
    idle(page, 1500)
    return {"header": text(page, T("b360-header"), 300), "tabs": text(page, T("b360-tabs"), 300)}


def s_b360_group(page: Page, ui: str, ctx: dict) -> dict:
    tab = page.locator(f'{T("b360-tabs")} button, {T("b360-tabs")} [role="tab"]', has_text="Relationships").first
    if not tab.count():
        tab = page.locator(f'{T("b360-tabs")} button, {T("b360-tabs")} [role="tab"]', has_text="Group").first
    tab.click()
    idle(page, 2500)
    return {"tab": text(page, T("b360-customer"), 400)}


Step = tuple[str, str, Callable[[Page, str, dict], dict]]
STEPS: list[Step] = [
    ("00_dealdesk_home", "", s_home),
    ("01_list_customer_file_chip", "R16-C1 in the list", s_list),
    ("02_customer_packs", "packs page, plain words", s_packs),
    ("03_c1_bank_file", "C1 the Bank's file (traced)", s_c1_bank),
    ("04_c2_what_to_type", "C2 business request files", s_c2),
    ("05_c2_checklist", "C2 checklist", s_c2_checklist),
    ("06_c4_expired_missing", "C4 thin file", s_c4),
    ("07_c1_open_deal", "C1 customer file on Deal Desk", s_c1_deal),
    ("08_c1_review", "C1 review on the seeded data", s_c1_review),
    ("09_b360_search", "B360 finds the customers by search", s_b360),
    ("10_b360_customer", "C2 in Borrower 360", s_b360_customer),
    ("11_b360_relationships", "C2 group / relationships", s_b360_group),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    path = OUT / "walk.json"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(90_000)
            ctx: dict[str, Any] = {"tag": tag}
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            for sid, items, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only) and sid != "00_dealdesk_home":
                    continue
                errors.clear()
                console.clear()
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "items": items, "size": tag}
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
                    rec["dev_overlay"] = page.evaluate(DEV_OVERLAY)
                except Exception as e:  # noqa: BLE001
                    rec["probe_error"] = str(e)[:120]
                rec["page_errors"] = list(errors)
                rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                rec["clean"] = not rec["page_errors"] and not rec["console_errors"]
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} "
                      f"{'clean' if rec['clean'] else 'ERRORS ' + json.dumps(rec['page_errors'] + rec['console_errors'])[:300]} {rec['seconds']}s "
                      f"{json.dumps(rec.get('checks'), default=str, ensure_ascii=False)[:400]}", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"]]
    dirty = [r for r in report if not r["clean"]]
    print(f"{len(report) - len(miss)} / {len(report)} found; {len(report) - len(dirty)} / {len(report)} clean")
    return 0 if not miss and not dirty else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
