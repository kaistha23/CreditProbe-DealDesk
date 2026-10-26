"""R16 session b: click-through walk of the RM business request on the production build, at 1440x900 and 1280x800.

  .venv/bin/python ops/r16_b_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--customers c1,c3,c4]

Every screen is reached by clicking (N6); the only goto is Deal Desk after sign-in. Screens: docs/v5/r16_review/b/<step>_<size>.png;
report docs/v5/r16_review/b/walkthrough.json. Steps per customer: the header "Business request" button, the customer picked, the
customer file brief, the ask and RM notes typed, the request written (page 1 with the Action requested, the business pages), Trace,
Share (dialog, send), Word (download); then the landing chat box: an ask typed there opens the studio on the named customer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402
from r14_u_walkthrough import DEV_OVERLAY, idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "b"
PART_A = False
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
PACKS = V5 / "data" / "dealdesk" / "demo_customers"

#: fallback asks when a customer's ASK.md has no "What Anne types" quote (fictional)
FALLBACK = {
    "c1": ("Renew all existing facilities and increase the overdraft to SAR 30m", "Owner is hands-on. New hospital tenders expected in 2027."),
    "c2": ("Renew the general limit SAR 160m and add a new SAR 120m project limit for Package C",
           "Package C awarded by SLDC in Aug 2026. Owner Turki is hands-on and banks with us since 2016."),
    "c3": ("Take over the facilities with other banks with a SAR 60m term loan over 5 years at SAIBOR + 1.75%", "Strong plant; owners keen to move the relationship."),
    "c4": ("New SAR 8m working capital limit, 12 months, SAIBOR + 2.5%", "Young company, clean VAT filings."),
}


def ask_of(key: str) -> tuple[str, str]:
    """The ask and RM notes Anne types, from the customer's ASK.md (blockquotes under the "types" headings)."""
    c = next((x for x in json.loads((PACKS / "customers.json").read_text())["customers"] if x["key"] == key), None)
    p = PACKS / (c or {}).get("folder", "-") / "ASK.md"
    if p.exists():
        txt = p.read_text()
        m = re.search(r"##[^\n]*(?:ask|types)[^\n]*\n+((?:>.*\n?)+)", txt, re.I)
        n = re.search(r"##[^\n]*notes[^\n]*\n+((?:>.*\n?)+)", txt, re.I)
        if m and "business request" not in m.group(1).lower() and "credit division" not in m.group(1).lower():
            q = lambda g: " ".join(x.lstrip("> ").strip() for x in g.splitlines() if x.strip())  # noqa: E731
            return q(m.group(1)), (q(n.group(1)) if n else FALLBACK.get(key, ("", ""))[1])
    return FALLBACK.get(key, ("Renew all existing facilities", ""))


def snap(page: Page, name: str, tag: str, rec: dict[str, Any], sel: str | None = None) -> None:
    if sel and page.locator(sel).count():
        page.locator(sel).first.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"{name}_{tag}.png"))
    rec.setdefault("shots", []).append(f"{name}_{tag}.png")


def walk_customer(page: Page, ui: str, key: str, tag: str, rec: dict[str, Any]) -> None:
    ask, notes = ask_of(key)
    rec["ask"], rec["notes"] = ask, notes
    page.locator(T("dealdesk-business-request")).first.click()
    page.wait_for_selector(T("br-studio"))
    snap(page, f"{key}_01_studio_empty", tag, rec)
    page.locator(T("br-customer")).select_option(key)
    page.wait_for_selector(T("br-customer-file"), timeout=120_000)
    idle(page, 500)
    snap(page, f"{key}_02_customer_file", tag, rec)
    rec["customer_plain_words"] = page.locator(T("br-customer-plain-words")).inner_text()[:400]
    page.locator(T("br-ask")).fill(ask)
    page.locator(T("br-notes")).fill(notes)
    t0 = time.time()
    page.locator(T("br-write")).click()
    page.wait_for_selector(T("br-preview"), timeout=180_000)
    rec["write_seconds"] = round(time.time() - t0, 1)
    idle(page, 600)
    snap(page, f"{key}_03_written_page1", tag, rec)
    rec["plain_words"] = page.locator(T("br-plain-words")).inner_text()[:500]
    rec["action_requested"] = page.locator(T("br-section-action")).inner_text()[:900]
    for s in ("facilities", "security", "terms", "group_exposure", "background", "relationship", "financials", "documents", "justification"):
        rec.setdefault("sections", {})[s] = page.locator(T(f"br-section-{s}")).count() == 1
    page.locator(T("br-section-facilities")).scroll_into_view_if_needed()
    snap(page, f"{key}_04_facilities_security_terms", tag, rec)
    page.locator(T("br-page-business")).scroll_into_view_if_needed()
    snap(page, f"{key}_05_business_comments", tag, rec)
    page.locator(T("br-section-financials")).scroll_into_view_if_needed()
    snap(page, f"{key}_06_financials", tag, rec)
    page.locator(T("br-section-justification")).scroll_into_view_if_needed()
    snap(page, f"{key}_07_justification", tag, rec)
    page.locator(T("br-trace-toggle")).click()
    page.wait_for_selector(T("br-trace"))
    snap(page, f"{key}_08_trace", tag, rec)
    rec["trace_plain_words"] = page.locator(T("br-trace-plain-words")).inner_text()[:300]
    page.locator(T("br-trace-toggle")).click()
    with page.expect_download(timeout=120_000) as dl:
        page.locator(T("br-word")).click()
    d = dl.value
    path = OUT / f"{key}_business_request.docx"
    d.save_as(str(path))
    rec["word"] = {"file": d.suggested_filename, "bytes": path.stat().st_size}
    page.locator(T("br-share")).click()
    page.wait_for_selector(T("br-share-dialog"))
    page.wait_for_selector(f'{T("br-share-users")} input', timeout=60_000)
    snap(page, f"{key}_09_share", tag, rec)
    page.locator(f'{T("br-share-users")} input').first.check()
    page.locator(T("br-share-send")).click()
    page.wait_for_selector(T("br-share-done"), timeout=120_000)
    rec["shared"] = page.locator(T("br-share-done")).inner_text()
    snap(page, f"{key}_10_shared", tag, rec)
    page.locator(T("br-share-close")).click()
    page.locator(T("br-close")).click()
    page.wait_for_selector(T("br-studio"), state="detached")


def walk_chatbox(page: Page, key: str, tag: str, rec: dict[str, Any]) -> None:
    """The RM types the ask in the Deal Desk chat box: the studio opens on the customer, the ask prefilled."""
    c = next(x for x in json.loads((PACKS / "customers.json").read_text())["customers"] if x["key"] == key)
    ask, _ = ask_of(key)
    box = page.locator(f'{T("dealdesk-home")} textarea').first
    box.fill(f"{c['short']}: {ask}")
    box.press("Enter")
    page.wait_for_selector(T("br-studio"), timeout=60_000)
    page.wait_for_selector(T("br-customer-file"), timeout=120_000)
    rec["chat_customer"] = page.locator(T("br-customer")).input_value()
    rec["chat_ask"] = page.locator(T("br-ask")).input_value()
    snap(page, f"{key}_11_chat_box_opens_studio", tag, rec)
    page.locator(T("br-close")).click()


def walk_deal(page: Page, key: str, tag: str, rec: dict[str, Any]) -> None:
    """On the deal page (Deal Desk pipeline → the customer's deal): the header "Business request" opens the studio on the deal; a
    request written before reopens from the list."""
    c = next(x for x in json.loads((PACKS / "customers.json").read_text())["customers"] if x["key"] == key)
    page.locator(T("dealdesk-search")).fill(c["short"])
    page.wait_for_timeout(800)
    page.locator(T(f"dealdesk-row-{c['proposal_id']}")).click()
    page.wait_for_selector(T("dealdesk-deal-business-request"), timeout=240_000)
    idle(page, 800)
    snap(page, f"{key}_12_deal_page", tag, rec)
    page.locator(T("dealdesk-deal-business-request")).click()
    page.wait_for_selector(T("br-customer-file"), timeout=120_000)
    rec["deal_customer"] = page.locator(T("br-customer")).input_value()
    prev = page.locator(f'[data-testid^="br-previous-BR-"]')
    if prev.count():
        prev.first.click()
        page.wait_for_selector(T("br-preview"), timeout=60_000)
        rec["reopened"] = True
    snap(page, f"{key}_13_deal_studio_reopened", tag, rec)
    page.locator(T("br-close")).click()
    ask, _ = ask_of(key)
    page.locator(T("dealdesk-composer")).fill(ask)
    page.locator(T("dealdesk-send")).click()
    page.wait_for_selector(T("br-customer-file"), timeout=120_000)
    rec["deal_chat_ask"] = page.locator(T("br-ask")).input_value()
    if rec["deal_chat_ask"] != ask:
        raise AssertionError("the ask typed in the deal's chat box did not open the business request")
    snap(page, f"{key}_14_deal_chat_ask_opens_studio", tag, rec)
    page.locator(T("br-close")).click()
    page.go_back()
    page.wait_for_selector(T("dealdesk-home"), timeout=120_000)


def walk_part_a(page: Page, key: str, tag: str, rec: dict[str, Any]) -> None:
    """The demo path end to end: New proposal → Customer documents (the customer's PDFs, several at once) → open the deal (an
    existing customer's deal, or a new proposal) → the deal header "Business request" → ask + RM notes → Write → the request
    reads the intake file (its documents section says "read by CreditProbe intake")."""
    c = next(x for x in json.loads((PACKS / "customers.json").read_text())["customers"] if x["key"] == key)
    files = sorted(str(p) for p in (PACKS / c["folder"] / "pdf").glob("*.pdf"))
    ask, notes = ask_of(key)
    page.locator(T("dealdesk-new")).click()
    page.wait_for_selector(T("dealdesk-new-dialog"))
    page.locator(T("intake-drop-input")).set_input_files(files)
    page.wait_for_selector(T("intake-actions"), timeout=300_000)
    idle(page, 600)
    snap(page, f"{key}_20_customer_documents", tag, rec)
    opener = page.locator(T("intake-open-deal"))
    (opener if opener.count() else page.locator(T("intake-create"))).click()
    page.wait_for_selector(T("dealdesk-deal-business-request"), timeout=300_000)
    rec["deal_url"] = page.url
    idle(page, 800)
    page.locator(T("dealdesk-deal-business-request")).click()
    page.wait_for_selector(T("br-customer-file"), timeout=120_000)
    page.locator(T("br-ask")).fill(ask)
    page.locator(T("br-notes")).fill(notes)
    page.locator(T("br-write")).click()
    page.wait_for_selector(T("br-preview"), timeout=180_000)
    idle(page, 600)
    snap(page, f"{key}_21_part_a_request", tag, rec)
    rec["documents_section"] = page.locator(T("br-section-documents")).inner_text()[:300]
    rec["from_intake"] = "read by CreditProbe intake" in rec["documents_section"]
    page.locator(T("br-section-justification")).scroll_into_view_if_needed()
    snap(page, f"{key}_22_part_a_disclosures", tag, rec)
    page.locator(T("br-close")).click()
    if not rec["from_intake"]:
        raise AssertionError("the request did not read the uploaded documents through intake")


def run(ui: str, sizes: list[tuple[int, int]], keys: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(60_000)
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
            page.wait_for_selector(T("dealdesk-home"), timeout=240_000)
            idle(page, 800)
            for key in keys:
                steps = [("studio", lambda r: walk_customer(page, ui, key, tag, r)), ("chat_box", lambda r: walk_chatbox(page, key, tag, r))]
                if key == "c1":
                    steps.append(("deal_page", lambda r: walk_deal(page, key, tag, r)))
                if PART_A:
                    steps.append(("part_a", lambda r: (walk_part_a(page, key, tag, r), page.go_back(), page.wait_for_selector(T("dealdesk-home"), timeout=120_000))))
                for name, fn in steps:
                    errors.clear(); console.clear()
                    rec: dict[str, Any] = {"customer": key, "step": name, "size": tag}
                    t0 = time.time()
                    try:
                        fn(rec)
                        rec["found"] = True
                    except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
                        rec["found"] = False
                        rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                        page.screenshot(path=str(OUT / f"{key}_{name}_error_{tag}.png"))
                        page.keyboard.press("Escape")
                    rec["seconds"] = round(time.time() - t0, 1)
                    rec["probe"] = page.evaluate(PROBE, None)
                    rec["dev_overlay"] = page.evaluate(DEV_OVERLAY)
                    rec["page_errors"] = list(errors)
                    rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                    rec["clean"] = not rec["page_errors"] and not rec["console_errors"] and not (rec["dev_overlay"] or {}).get("portal")
                    report.append(rec)
                    print(f"{tag} {key} {name} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} {'clean' if rec['clean'] else 'ERRORS'} {rec['seconds']}s", flush=True)
                    (OUT / "walkthrough.json").write_text(json.dumps(report, indent=1, default=str))
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
    ap.add_argument("--customers", default="c1,c3,c4")
    ap.add_argument("--part-a", action="store_true", help="also the upload path: New proposal → Customer documents → deal → Business request")
    a = ap.parse_args()
    PART_A = a.part_a
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, [k for k in a.customers.split(",") if k]))
