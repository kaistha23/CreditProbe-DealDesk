"""PLAN_R14 Session U: click-through walk of the shell screens U changed, at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_u_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Every screen is reached by clicking (N6); the only goto is the first page after sign-in. Each step records page
errors, console errors and whether the Next.js development overlay / "N Issues" badge is on the page (K8: it must
never be). Screens: docs/v5/r14_review/u/<step>_<size>.png; report: docs/v5/r14_review/u/walkthrough.json.

Items: K1 (Back to <origin>), K8 (no runtime error, no dev badge), K11 (Borrower 360 on borrower cards and rows),
K17 (every dd_deal deal in the list, counts agree, fuzzy search, a deal named in Ask opens it), K28 (house menus).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = Path(os.environ.get("R14_U_OUT") or V5 / "docs" / "v5" / "r14_review" / "u")  # R14_U_OUT: a dev-mode check elsewhere
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
DEV = False

# The development overlay (next dev): its portal and the "N Issues" badge. Never present on a production build.
DEV_OVERLAY = r"""
() => {
  const portal = document.querySelector('nextjs-portal');
  const badge = !!(portal && portal.shadowRoot && portal.shadowRoot.querySelector('[data-nextjs-dev-tools-button],[data-issues],[data-nextjs-toast]'));
  const text = portal && portal.shadowRoot ? (portal.shadowRoot.textContent || '') : '';
  return {portal: !!portal, badge, issues: /\d+\s*Issues?/.test(text) ? text.match(/\d+\s*Issues?/)[0] : null};
}
"""


def idle(page: Page, ms: int = 700, timeout: int = 30_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001 - a long poll keeps the network busy
        pass
    page.wait_for_timeout(ms)


def settle(page: Page, scope: str = "main", timeout: int = 90_000) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        busy = page.locator(f"{scope} .animate-spin").count() + page.locator(f"{scope} [aria-busy='true']").count()
        if not busy:
            break
        page.wait_for_timeout(600)
    page.wait_for_timeout(400)


def nav(page: Page, slug: str, ready: str) -> None:
    page.locator(T(f"nav-{slug}")).first.click()
    page.wait_for_selector(T(ready), timeout=120_000)
    idle(page)


# ---------------------------------------------------------------- steps
Step = tuple[str, str, Callable[[Page, str, dict], dict]]


def s_home(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("home-tabs"), timeout=120_000)
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page, 1200)
    return {"tab": page.locator(T("home-tabs")).get_attribute("data-tab")}


def s_brief_open(page: Page, ui: str, ctx: dict) -> dict:
    """K1: Open on a brief line lands on its page with "← Back to Brief"; the link returns to the Brief."""
    nav(page, "home", "noor-home-brief")
    line = page.locator(f'{T("noor-home-brief-lines")} > li').first
    line.hover()
    page.wait_for_timeout(300)
    line.locator(T("noor-open")).first.click(force=True)
    page.wait_for_selector(T("origin-back-link"), timeout=120_000)
    idle(page, 1200)
    out = {"url": page.url, "from_in_url": "from=brief" in page.url, "back_text": page.locator(T("origin-back-link")).inner_text()}
    page.screenshot(path=str(OUT / f"{ctx['sid']}_target_{ctx['tag']}.png"))
    page.locator(T("origin-back-link")).click()
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page)
    out["returned_to"] = page.url
    out["back_on_brief"] = page.locator(T("home-tabs")).get_attribute("data-tab") == "brief"
    return out


def s_user_menu(page: Page, ui: str, ctx: dict) -> dict:
    """K28: the user / sign-out menu on the house dropdown."""
    page.locator(T("user-menu")).click()
    page.wait_for_selector(T("user-menu-panel"))
    box = page.locator(T("user-menu-panel")).bounding_box() or {}
    rows = page.locator(f'{T("user-menu-panel")} [role="menuitem"]')
    heights = [round((rows.nth(i).bounding_box() or {}).get("height", 0)) for i in range(rows.count())]
    out = {"width": round(box.get("width", 0)), "items": rows.all_inner_texts(), "row_heights": heights}
    page.keyboard.press("ArrowDown")
    out["focus_after_arrow"] = page.evaluate("document.activeElement && document.activeElement.textContent")
    return out


def s_dd_list(page: Page, ui: str, ctx: dict) -> dict:
    """K17: every dd_deal deal in the Proposal pipeline; Pending equals the Pipeline tab."""
    page.keyboard.press("Escape")
    nav(page, "deal-desk", "dealdesk-home")
    page.wait_for_selector(T("dealdesk-table"), timeout=120_000)
    settle(page)
    page.locator(T("dealdesk-pipeline")).scroll_into_view_if_needed()
    all_n = int(page.locator(T("dealdesk-count-all")).inner_text())
    pend_n = int(page.locator(T("dealdesk-count-pending")).inner_text())
    ids = [x.replace("dealdesk-row-", "") for x in page.locator('tr[data-testid^="dealdesk-row-"]').evaluate_all("els => els.map(e => e.dataset.testid)")]
    return {"all": all_n, "pending": pend_n, "rows": len(ids),
            "has_twins": all(i in ids for i in ("R12-TWA", "R12-TWB", "R12-ESC", "R12-SYN")), "has_pl": any(i.startswith("PL-") for i in ids)}


def s_dd_pipeline_tab(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-mode-pipeline")).click()
    page.wait_for_selector(T("dealdesk-pipeline-selected"), timeout=180_000)
    settle(page)
    txt = page.locator(T("dealdesk-pipeline-selected")).inner_text()
    m = re.search(r"of (\d+) deals", txt)
    out = {"pipeline_text": txt, "pipeline_count": int(m.group(1)) if m else None}
    page.locator(T("dealdesk-mode-single")).click()
    page.wait_for_selector(T("dealdesk-table"), timeout=120_000)
    out["list_pending"] = int(page.locator(T("dealdesk-count-pending")).inner_text())
    out["agree"] = out["pipeline_count"] == out["list_pending"]
    return out


def s_dd_search(page: Page, ui: str, ctx: dict) -> dict:
    """K17: "al sahal" finds Al Sahel (R12-TWA)."""
    page.locator(T("dealdesk-search")).fill("al sahal")
    page.wait_for_timeout(600)
    page.locator(T("dealdesk-search")).scroll_into_view_if_needed()
    rows = page.locator('tr[data-testid^="dealdesk-row-"]')
    return {"rows": rows.count(), "first": rows.first.get_attribute("data-testid") if rows.count() else None}


def s_dd_open_twa(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-row-R12-TWA")).click()
    page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
    idle(page, 1500)
    return {"url": page.url}


def s_dd_more(page: Page, ui: str, ctx: dict) -> dict:
    """K28: deal More menu: two sections, one-line labels, ≥260 px, 32 px rows, the count explained."""
    page.locator(T("dealdesk-more-button")).click()
    page.wait_for_selector(T("dealdesk-more-menu"))
    menu = page.locator(T("dealdesk-more-menu"))
    box = menu.bounding_box() or {}
    sections = menu.locator("[data-dropdown-section]").evaluate_all("els => els.map(e => e.textContent)")
    rows = menu.locator('[role="menuitem"]')
    wrapped = rows.evaluate_all("els => els.filter(e => { const l = e.querySelector('span.truncate'); return l && l.scrollWidth > l.clientWidth + 1; }).map(e => e.textContent)")
    badge = page.locator(T("dealdesk-more-badge"))
    return {"width": round(box.get("width", 0)), "sections": sections, "items": rows.count(), "truncated": wrapped,
            "badge_tooltip": badge.get_attribute("title") if badge.count() else None}


def s_dd_ask_named(page: Page, ui: str, ctx: dict) -> dict:
    """K17: a deal named in the Deal Desk Ask box opens the deal."""
    page.keyboard.press("Escape")
    nav(page, "deal-desk", "dealdesk-home")
    box = page.locator("textarea").first
    box.fill("Why does Al Sahal fail?")
    box.press("Enter")
    page.wait_for_url(re.compile(r".*/deal-desk/R12-TWA.*"), timeout=120_000)
    idle(page, 1200)
    return {"url": page.url}


def s_dd_governance(page: Page, ui: str, ctx: dict) -> dict:
    nav(page, "deal-desk", "dealdesk-home")
    page.locator(T("gov-tools")).click()
    page.wait_for_selector(T("gov-tools-menu"))
    box = page.locator(T("gov-tools-menu")).bounding_box() or {}
    return {"width": round(box.get("width", 0)), "items": page.locator(f'{T("gov-tools-menu")} [role="menuitem"]').count()}


def s_book_tools(page: Page, ui: str, ctx: dict) -> dict:
    page.keyboard.press("Escape")
    page.locator(T("dealdesk-tab-book")).click()
    page.wait_for_selector(T("portfolio-tools-book-button"), timeout=120_000)
    page.wait_for_selector(T("book-row"), timeout=180_000)
    settle(page)
    out = {"b360_buttons_in_book": page.locator('[data-b360-button="1"]').count()}
    page.locator(T("portfolio-tools-book-button")).click()
    page.wait_for_selector(T("portfolio-tools-book-menu"))
    out["sections"] = page.locator(f'{T("portfolio-tools-book-menu")} [data-dropdown-section]').all_inner_texts()
    out["items"] = page.locator(f'{T("portfolio-tools-book-menu")} [role="menuitem"]').count()
    return out


def s_ews_cards(page: Page, ui: str, ctx: dict) -> dict:
    """K11: every borrower card has Borrower 360 →; K1: Back returns to the same list."""
    page.keyboard.press("Escape")
    nav(page, "early-warning", "ews-level-portfolio")
    settle(page)
    page.locator('[data-testid="ews-children"] [data-testid^="ews-open-"]').first.click()
    page.wait_for_selector(T("ews-level-segment"), timeout=120_000)
    settle(page)
    page.locator('[data-testid="ews-children"] [data-testid^="ews-open-"]').first.click()
    page.wait_for_selector(T("ews-level-subsegment"), timeout=120_000)
    settle(page)
    page.locator(T("ews-open-warned")).click()
    page.wait_for_selector('[data-testid^="ews-customer-CB"]', timeout=120_000)
    settle(page)
    cards = page.locator('[data-testid^="ews-customer-CB"]')
    with_btn = page.locator('[data-testid^="ews-customer-CB"] [data-b360-button="1"]')
    ctx["ews_list_url"] = page.url
    return {"cards": cards.count(), "cards_with_b360": with_btn.count()}


def s_ews_to_b360(page: Page, ui: str, ctx: dict) -> dict:
    btn = page.locator('[data-testid^="ews-customer-CB"] [data-b360-button="1"]').first
    href = btn.get_attribute("href")
    btn.click()
    page.wait_for_selector(T("origin-back-link"), timeout=120_000)
    settle(page)
    cid = re.search(r"customer_id=(CB\d+)", href or "")
    page.wait_for_selector(T("b360-id"), timeout=120_000)
    settle(page)
    out = {"href": href, "back_text": page.locator(T("origin-back-link")).inner_text(),
           "b360_opened": page.locator("text=could not be opened").count() == 0,
           "b360_id": page.locator(T("b360-id")).inner_text(), "expected_id": cid.group(1) if cid else None}
    if not out["b360_opened"]:
        raise AssertionError("Borrower 360 could not open the borrower")
    page.screenshot(path=str(OUT / f"{ctx['sid']}_b360_{ctx['tag']}.png"))
    page.locator(T("origin-back-link")).click()
    page.wait_for_selector('[data-testid^="ews-customer-CB"]', timeout=120_000)
    idle(page)
    out["returned_to_same_list"] = page.url.split("#")[0] == ctx.get("ews_list_url", "").split("#")[0]
    return out


def s_who_to_call(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("ews-tools")).click()
    page.locator(T("ews-tools-calls")).click()
    page.wait_for_selector('[data-testid^="calls-row-"]', timeout=180_000)
    settle(page)
    return {"rows": page.locator('[data-testid^="calls-row-"]').count(),
            "rows_with_b360": page.locator('[data-testid^="calls-row-"] [data-b360-button="1"]').count()}


def s_drawer_back(page: Page, ui: str, ctx: dict) -> dict:
    """K1: a borrower opened from the Who to call drawer; Back returns to the page with the drawer open again."""
    row = page.locator('[data-testid^="calls-row-"] [data-b360-button="1"]').first
    row.click()
    page.wait_for_selector(T("origin-back-link"), timeout=120_000)
    settle(page)
    out = {"back_text": page.locator(T("origin-back-link")).inner_text()}
    page.locator(T("origin-back-link")).click()
    page.wait_for_selector('[data-testid^="calls-row-"]', timeout=180_000)
    settle(page)
    out["drawer_reopened"] = page.locator('[data-testid^="calls-row-"]').count() > 0
    out["url"] = page.url
    return out


STEPS: list[Step] = [
    ("00_home", "K8", s_home),
    ("01_brief_open_back", "K1 K8", s_brief_open),
    ("02_user_menu", "K28", s_user_menu),
    ("10_dd_list_all_deals", "K17", s_dd_list),
    ("11_dd_pipeline_counts_agree", "K17", s_dd_pipeline_tab),
    ("12_dd_search_al_sahal", "K17", s_dd_search),
    ("13_dd_open_twa", "K17", s_dd_open_twa),
    ("14_dd_more_menu", "K28", s_dd_more),
    ("15_dd_ask_names_deal", "K17", s_dd_ask_named),
    ("16_dd_governance_menu", "K28", s_dd_governance),
    ("17_book_tools_b360", "K28 K11", s_book_tools),
    ("20_ews_cards_b360", "K11", s_ews_cards),
    ("21_ews_b360_back", "K11 K1", s_ews_to_b360),
    ("22_ews_who_to_call", "K11 K28", s_who_to_call),
    ("23_drawer_b360_back", "K1 K11", s_drawer_back),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    path = OUT / "walkthrough.json"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(60_000)
            ctx: dict[str, Any] = {"tag": tag}
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            for sid, items, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only) and sid != "00_home":
                    continue
                ctx["sid"] = sid
                errors.clear(); console.clear()
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
                # Network failures of optional polls are not runtime errors of the page; everything else is.
                rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                ov = rec.get("dev_overlay") or {}
                # Production: the overlay must not exist at all. --dev (a `next dev` check): its button is always there,
                # so the check is that it counts no issues.
                rec["clean"] = (not rec["page_errors"] and not rec["console_errors"] and not ov.get("issues")
                                and (DEV or not ov.get("portal")))
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} "
                      f"{'clean' if rec['clean'] else 'ERRORS ' + json.dumps(rec['page_errors'] + rec['console_errors'])[:300]} {rec['seconds']}s", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"]]
    dirty = [r for r in report if not r["clean"]]
    print(f"{len(report) - len(miss)} / {len(report)} found; {len(report) - len(dirty)} / {len(report)} clean (no page/console error, no dev overlay)")
    return 0 if not miss and not dirty else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    ap.add_argument("--dev", action="store_true", help="the UI is `next dev`: judge the overlay by its issue count")
    a = ap.parse_args()
    DEV = a.dev
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
