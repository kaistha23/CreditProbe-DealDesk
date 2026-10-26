"""R16 i: click-through walk of the customer file on the production build, at 1440x900 and 1280x800.

  .venv/bin/python ops/r16_i_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--customers c1,c4] [--mix word|pdf|images|mixed]

Deal Desk → New proposal (opens on "Customer documents") → drop the customer's documents (a mix of Word, PDF and photos
from data/dealdesk/demo_customers/<folder>/) → the customer file (plain words, header, checklist, reconciliation, the
Bank's data, documents; one document opened) → open / create the deal → More → Customer file on the deal.
Every screen reached by clicking (the only goto is the first page). Screens: docs/v5/r16_review/i/<step>_<size>.png;
report: docs/v5/r16_review/i/walkthrough.json (page errors, console errors, dev overlay, wider than the viewport).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "i"
DEMO = V5 / "data" / "dealdesk" / "demo_customers"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
WIDTH = "() => ({doc: document.documentElement.scrollWidth, vw: window.innerWidth})"
DEV = "() => !!document.querySelector('nextjs-portal')"


def files_for(customer: str, mix: str) -> list[Path]:
    folder = next(p for p in DEMO.glob(f"{customer}_*") if p.is_dir())
    man = json.loads((folder / "manifest.json").read_text())
    out: list[Path] = []
    for i, d in enumerate(man["documents"]):
        f = d["files"]
        pick = mix if mix != "mixed" else ("images" if f.get("images") and i % 3 == 0 else "pdf" if i % 3 == 1 else "docx")
        if pick == "images" and f.get("images"):
            out.extend(folder / x for x in f["images"])
        elif pick == "pdf" and f.get("pdf"):
            out.append(folder / f["pdf"])
        else:
            out.append(folder / f["docx"])
    return out


def idle(page: Page, ms: int = 600) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(ms)


def run(ui: str, sizes: list[tuple[int, int]], customers: list[str], mix: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for customer, (w, h) in [(c, sz) for c in customers for sz in sizes]:
            files = files_for(customer, mix)
            ctx = b.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = ctx.new_page()
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            page.on("console", lambda m: console.append(m.text[:200]) if m.type == "error" else None)
            size = f"{w}x{h}"

            def step(name: str, sel: str | None = None, full: bool = False, **extra: Any) -> None:
                wd = page.evaluate(WIDTH)
                name = f"{customer}_{name}"
                path = OUT / f"{name}_{size}.png"
                if sel and page.locator(sel).count():
                    page.locator(sel).first.scroll_into_view_if_needed()
                    page.screenshot(path=str(path))
                else:
                    page.screenshot(path=str(path), full_page=full)
                report.append({"step": name, "size": size, "customer": customer, "found": bool(not sel or page.locator(sel).count()), "page_errors": list(errors),
                               "console_errors": [c for c in console if "favicon" not in c][:5], "dev_overlay": page.evaluate(DEV),
                               "wider_than_viewport": wd["doc"] > wd["vw"] + 1, **extra})
                errors.clear()
                console.clear()

            page.goto(f"{ui}/", wait_until="domcontentloaded")
            page.wait_for_selector(T("nav-deal-desk"), timeout=120_000)
            page.locator(T("nav-deal-desk")).first.click()
            page.wait_for_selector(T("dealdesk-home"), timeout=120_000)
            idle(page)
            page.locator(T("dealdesk-new")).first.click()
            page.wait_for_selector(T("intake-new"), timeout=30_000)
            idle(page, 400)
            step("01_new_proposal_customer_documents", T("dealdesk-new-dialog"))
            t0 = time.time()
            page.set_input_files(T("intake-drop-input"), [str(p) for p in files])
            page.wait_for_selector(T("intake-file"), timeout=600_000)
            secs = round(time.time() - t0, 1)
            idle(page, 800)
            n_docs = page.locator(T("intake-doc-row")).count()
            step("02_customer_file_top", None, uploaded=len(files), documents=n_docs, seconds=secs,
                 shown=page.locator(T("intake-customer")).inner_text())
            page.locator(T("intake-checklist")).scroll_into_view_if_needed()
            step("03_checklist", T("intake-checklist"), missing=page.locator(f'{T("intake-check-line")}[data-status="missing"]').count(),
                 expired=page.locator(f'{T("intake-check-line")}[data-status="expired"]').count())
            page.locator(T("intake-recon")).scroll_into_view_if_needed()
            step("04_read_together", T("intake-recon"), key_concerns=page.locator(f'{T("intake-recon-line")}[data-severity="3"]').count())
            page.locator(T("intake-bank")).scroll_into_view_if_needed()
            step("05_bank_data", T("intake-bank"), existing=page.locator(T("intake-existing")).count() > 0)
            page.locator(T("intake-docs")).scroll_into_view_if_needed()
            step("06_documents", T("intake-docs"))
            photo = page.locator(f'{T("intake-doc-row")}').filter(has_text=".jpg")
            (photo.first if photo.count() else page.locator(T("intake-doc-row")).first).locator(T("intake-doc-name")).click()
            page.wait_for_selector(T("intake-doc-text"), timeout=30_000)
            idle(page, 300)
            step("07_document_opened", T("intake-doc-detail"))
            # open the deal from the file
            btn = T("intake-open-deal") if page.locator(T("intake-open-deal")).count() else T("intake-create")
            page.locator(T("intake-plain")).scroll_into_view_if_needed()
            page.locator(btn).first.click()
            page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
            idle(page, 1200)
            step("08_deal_opened", None, via=btn, url=page.url.split("?")[0].rsplit("/", 1)[-1])
            page.locator(T("dealdesk-more-button")).first.click()
            page.locator(T("dealdesk-action-customer-file")).first.click()
            page.wait_for_selector(T("intake-file"), timeout=60_000)
            idle(page, 800)
            step("09_deal_more_customer_file", T("dealdesk-customer-file-dialog"))
            ctx.close()
        b.close()
    (OUT / "walkthrough.json").write_text(json.dumps({"customers": customers, "mix": mix, "steps": report}, indent=1))
    bad = [r for r in report if not r["found"] or r["page_errors"] or r["dev_overlay"] or r["wider_than_viewport"]]
    for r in report:
        print(f"{r['size']} {r['step']}: found={r['found']} errors={len(r['page_errors'])} console={len(r['console_errors'])} "
              f"dev={r['dev_overlay']} wide={r['wider_than_viewport']} " + " ".join(f"{k}={v}" for k, v in r.items()
              if k not in ("step", "size", "customer", "found", "page_errors", "console_errors", "dev_overlay", "wider_than_viewport")))
    print("WALK", "PASS" if not bad else f"ISSUES {len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--customers", default="c1,c4")
    ap.add_argument("--mix", default="mixed")
    a = ap.parse_args()
    sys.exit(run(a.ui, [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")], a.customers.split(","), a.mix))
