"""PLAN_R14 Session G: screenshots of every panel G owns, reached by clicking, at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_g_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Each step opens the module page, clicks the menu (More / Tools / Governance / Network tools / Portfolio tools) and the
item, waits for the panel's "In plain words" block and its data, and records: the block's lines, whether it passes the
K34 rules in the browser (data-ok), page errors and the sideways-scroll probe. Writes docs/v5/r14_review/g/<step>_<size>.png
and docs/v5/r14_review/g/walkthrough.json. Uses a minted session (no password read or printed).
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

OUT = V5 / "docs" / "v5" / "r14_review" / "g"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
DEAL = "DD-06"
BORROWER = "CB00039"


def idle(page: Page, ms: int = 700, timeout: int = 30_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001 - long polls keep the network busy
        pass
    page.wait_for_timeout(ms)


def settle(page: Page, scope: str, timeout: int = 120_000) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        busy = (page.locator(f"{scope} .animate-spin").count() + page.locator(f"{scope} [aria-busy='true']").count()
                + page.locator(f"{scope} .animate-pulse").count())
        if not busy:
            break
        page.wait_for_timeout(700)
    page.wait_for_timeout(500)


def words(page: Page, scope: str, key: str) -> dict[str, Any]:
    sel = f'{scope} [data-panel-words="{key}"]'
    # R14 x: after the merge two panels are another session's (Write proposal -> p's credit-proposal preview, Committee
    # questions -> i's rehearsal); each opens with u's PlainWords itself, without g's wrapper: accept that block too.
    page.wait_for_selector(f"{sel} [data-plain-words], {scope} [data-plain-words]", timeout=120_000)
    if not page.locator(f"{sel} [data-plain-words]").count():
        sel = scope
    settle(page, sel)
    block = page.locator(f"{sel} [data-plain-words]").first
    block.scroll_into_view_if_needed()
    lines = [x.strip() for x in block.locator('[data-testid="plain-words-line"]').all_inner_texts()]
    return {"block": key, "ok": block.get_attribute("data-ok") == "1", "words": block.get_attribute("data-words"), "lines": lines,
            "has_number": any(ch.isdigit() for ln in lines for ch in ln)}


# ---------------------------------------------------------------- openers (clicks)

def deal_more(item_testid: str, key: str, dialog: str) -> Callable[[Page, str], dict]:
    def fn(page: Page, ui: str) -> dict:
        page.goto(f"{ui}/deal-desk/{DEAL}", wait_until="domcontentloaded")
        page.wait_for_selector(T("dealdesk-more-button"), timeout=120_000)
        idle(page, 1200)
        page.locator(T("dealdesk-more-button")).click()
        page.locator(T(item_testid)).first.click()
        page.wait_for_selector(T(dialog), timeout=60_000)
        out = words(page, T(dialog), key)
        settle(page, T(dialog))
        return out
    return fn


def book_tool(item: str, key: str, drawer: str | None) -> Callable[[Page, str], dict]:
    def fn(page: Page, ui: str) -> dict:
        page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
        page.wait_for_selector(T("dealdesk-tab-book"), timeout=120_000)
        idle(page, 800)
        page.locator(T("dealdesk-tab-book")).click()
        page.wait_for_selector(T("portfolio-tools-book-button"), timeout=120_000)
        page.locator(T("portfolio-tools-book-button")).click()
        page.locator(T(f"portfolio-tool-{item}")).click()
        scope = T(drawer) if drawer else "body"
        if drawer:
            page.wait_for_selector(scope, timeout=60_000)
        return words(page, scope, key)
    return fn


def gov_tool(item: str, key: str, then: Callable[[Page], None] | None = None) -> Callable[[Page, str], dict]:
    def fn(page: Page, ui: str) -> dict:
        page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
        page.wait_for_selector(T("gov-tools"), timeout=120_000)
        idle(page, 800)
        page.locator(T("gov-tools")).click()
        page.locator(T(f"gov-tool-{item}")).click()
        scope = T(f"gov-drawer-{item}")
        page.wait_for_selector(scope, timeout=60_000)
        if then:
            then(page)
        out = words(page, scope, key)
        return out
    return fn


def insp_result(page: Page) -> None:
    page.wait_for_selector(T("gov-insp-example"), timeout=60_000)
    page.locator(T("gov-insp-example")).click()
    page.wait_for_selector(T("gov-insp-answers"), timeout=120_000)


def net_tool(item: str, key: str, then: Callable[[Page], None] | None = None) -> Callable[[Page, str], dict]:
    def fn(page: Page, ui: str) -> dict:
        page.goto(f"{ui}/borrower-360?domain=corporate&customer_id={BORROWER}", wait_until="domcontentloaded")
        page.wait_for_selector(T("intel-network-tools-b360-button"), timeout=120_000)
        idle(page, 1000)
        page.locator(T("intel-network-tools-b360-button")).click()
        page.locator(T(f"intel-network-tool-{item}")).click()
        scope = T(f"intel-network-sheet-{item}")
        page.wait_for_selector(scope, timeout=60_000)
        if then:
            then(page)
        return words(page, scope, key)
    return fn


def run_event(page: Page) -> None:
    sheet = T("intel-network-sheet-event")
    page.locator(f'{sheet} [data-testid^="intel-event-pick-"]').first.click()
    page.wait_for_selector(T("intel-event-result"), timeout=180_000)


def ews_calls(page: Page, ui: str) -> dict:
    page.goto(f"{ui}/early-warning", wait_until="domcontentloaded")
    page.wait_for_selector(T("ews-tools"), timeout=120_000)
    idle(page, 1000)
    page.locator(T("ews-tools")).click()
    page.locator(T("ews-tools-calls")).click()
    return words(page, "body", "who-to-call")


def cockpit_ask(page: Page, ui: str) -> dict:
    """FX-R14-01: Noor's Ask tab has no 'Attach a letter / Letters on file' row."""
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("home-tabs"), timeout=120_000)
    page.locator('[data-testid="home-tabs"] [role="tab"]:has-text("Ask")').first.click()
    page.wait_for_selector(T("cockpit-v4-question"), timeout=60_000)
    idle(page, 1000)
    attach = page.locator(T("cockpit-queries-attach")).count() + page.locator(T("cockpit-queries-letters")).count()
    text = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
    return {"block": "fx-r14-01", "ok": attach == 0 and "Letters on file" not in text and "Attach a letter" not in text,
            "attach_controls": attach}


STEPS: list[tuple[str, Callable[[Page, str], dict]]] = [
    ("01_more_documents", deal_more("dealdesk-action-documents", "documents", "dealdesk-documents-dialog")),
    ("02_more_group", deal_more("dealdesk-action-group", "group", "dealdesk-group-dialog")),
    ("03_more_write", deal_more("dealdesk-action-write", "write", "dealdesk-write-dialog")),
    ("04_more_committee", deal_more("dealdesk-action-committee", "committee", "dealdesk-committee-dialog")),
    ("05_more_try", deal_more("dealdesk-action-try", "try", "try-docs-dialog")),
    ("06_more_fin_quality", deal_more("dealdesk-intel-fin-quality", "fin-quality", "dealdesk-intel-fin-quality-dialog")),
    ("07_more_challenger", deal_more("dealdesk-intel-challenger", "challenger", "dealdesk-intel-challenger-dialog")),
    ("08_more_reverse", deal_more("dealdesk-intel-reverse", "reverse", "dealdesk-intel-reverse-dialog")),
    ("09_more_security", deal_more("dealdesk-intel-security", "security", "dealdesk-intel-security-dialog")),
    ("10_more_consistency", deal_more("dealdesk-intel-consistency", "consistency", "dealdesk-intel-consistency-dialog")),
    ("11_more_covenants", deal_more("dealdesk-intel-covenants", "covenants", "dealdesk-intel-covenants-dialog")),
    ("12_book_renewals", book_tool("renewals", "renewals", None)),
    ("13_book_headroom", book_tool("headroom", "headroom", "portfolio-drawer-headroom")),
    ("14_book_exits", book_tool("exits", "exits", "portfolio-drawer-exits")),
    ("15_book_rwa", book_tool("rwa", "rwa", "portfolio-drawer-rwa")),
    ("16_book_ecl_bridge", book_tool("ecl_bridge", "ecl-bridge", "portfolio-drawer-ecl_bridge")),
    ("17_book_workout", book_tool("workout", "workout", "portfolio-drawer-workout")),
    ("18_ews_who_to_call", ews_calls),
    ("19_gov_inspection_empty", gov_tool("inspection", "inspection")),
    ("20_gov_inspection_result", gov_tool("inspection", "inspection", insp_result)),
    ("21_gov_exceptions", gov_tool("exceptions", "exceptions")),
    ("22_gov_rm_track", gov_tool("rm-track", "rm-track")),
    ("23_gov_doa", gov_tool("doa", "doa")),
    ("24_net_contagion", net_tool("contagion", "contagion")),
    ("25_net_employer", net_tool("employer", "employer")),
    ("26_net_event", net_tool("event", "event", run_event)),
    ("27_cockpit_ask_no_attach_row", cockpit_ask),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
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
            bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(60_000)
            for sid, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only):
                    continue
                errors: list[str] = []
                handler = lambda e: errors.append(str(e)[:200])  # noqa: E731
                page.on("pageerror", handler)
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "size": tag}
                try:
                    rec["checks"] = fn(page, ui)
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001 - recorded as a miss; the walk goes on
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
                if page.is_closed() or "crashed" in rec.get("error", ""):
                    try:
                        page.close()
                    except Exception:  # noqa: BLE001
                        pass
                    page = bctx.new_page()
                    page.set_default_timeout(60_000)
                report.append(rec)
                c = rec.get("checks") or {}
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} words_ok={c.get('ok')} {rec['seconds']}s", flush=True)
                done = {(r["step"], r["size"]) for r in report}
                path.write_text(json.dumps([r for r in kept if (r["step"], r["size"]) not in done] + report, indent=1, default=str))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"] or not (r.get("checks") or {}).get("ok")]
    print(f"{len(report) - len(miss)} / {len(report)} found with a passing block")
    return 0 if not miss else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
