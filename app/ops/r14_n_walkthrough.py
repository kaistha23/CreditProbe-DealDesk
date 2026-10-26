"""PLAN_R14 Session n: walk-through of every screen session n changed (K5, K6, K7, K9, K10, K16), by clicking, at
1440x900 and 1280x800, on the running services (production UI build).

  .venv/bin/python ops/r14_n_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Every step starts from the home page and reaches its screen by clicks (side navigation, buttons); the only typed
address is the home page itself. Writes docs/v5/r14_review/n/<step>_<size>.png and walkthrough.json (checks per step,
page errors, sideways-scroll probe). Uses a minted session (no password is read or printed).
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
from r13_m_walkthrough import ensure_dealdesk, idle, settle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "n"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731


def home(page: Page, ui: str, tab: str = "brief") -> None:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("home-tabs"), timeout=120_000)
    if page.locator(T("home-tabs")).get_attribute("data-tab") != tab:
        page.locator(T(f"home-tab-{tab}")).click()
    idle(page, 800)


def nav(page: Page, href: str) -> None:
    """Click the side navigation link to a module."""
    page.locator(f'nav[aria-label="Primary"] a[href="{href}"]').first.click()
    page.wait_for_url(re.compile(re.escape(href) + r"($|[/?#])"), timeout=60_000)
    idle(page, 1000)


def close_noor(page: Page) -> None:
    if page.locator(T("noor-panel")).count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def open_noor(page: Page) -> None:
    close_noor(page)
    page.locator(T("ask-noor")).click()
    page.wait_for_selector(T("noor-panel"), timeout=60_000)
    page.wait_for_timeout(500)


# ---------------------------------------------------------------- steps

def s_brief(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page, 1200)
    b = page.locator(T("noor-home-brief"))
    first_actions = b.locator(T("noor-line-actions")).first
    return {"eyebrow": b.locator(T("noor-brief-meta")).inner_text(),
            "headline": b.locator(T("noor-headline")).inner_text(),
            "lines": b.locator(T("noor-line-actions")).count(),
            "actions_visible_without_hover": first_actions.is_visible() and first_actions.evaluate("e => getComputedStyle(e).opacity") == "1",
            "actions_below_title": first_actions.bounding_box()["y"] > b.locator("li p").first.bounding_box()["y"],
            "listen": b.locator(T("noor-listen")).count(), "line_speakers": b.locator(T("noor-line-speaker")).count(),
            "new_chips": b.locator(T("noor-line-new")).count(),
            "since_yesterday_on_page": page.locator("text=since yesterday").count()}


def s_brief_more(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    more = page.locator(f'{T("noor-home-brief")} {T("noor-more")}')
    label = more.inner_text() if more.count() else ""
    if more.count():
        more.click()
        page.wait_for_timeout(500)
        more.scroll_into_view_if_needed()
    return {"more_label": label, "lines_after": page.locator(f'{T("noor-home-brief")} {T("noor-line-actions")}').count()}


def _panel_line(page: Page, i: int, action: str) -> str:
    """Click an action on brief line i inside the Noor panel's brief thread; returns the line's text."""
    lines = page.locator(f'{T("noor-panel")} li[data-testid^="noor-line-"]')
    li = lines.nth(i)
    title = li.locator("p").first.inner_text()
    li.locator(T(action)).click()
    return title


def s_k5_two_lines(page: Page, ui: str, ctx: dict) -> dict:
    """K5: Why on line 1, then Why on line 2 from the brief: two threads; line 2's thread does not hold line 1."""
    home(page, ui, "ask")
    open_noor(page)
    page.locator(T("noor-chip-brief")).click()
    page.wait_for_selector(f'{T("noor-panel")} li[data-testid^="noor-line-"]', timeout=120_000)
    t1 = _panel_line(page, 0, "noor-options")
    page.wait_for_selector(T("noor-turn-options"), timeout=120_000)
    idle(page, 800)
    first_thread = page.locator(T("noor-context")).inner_text()
    # back to the brief thread through the history, then line 2
    page.locator(T("noor-history-button")).click()
    page.locator(T("noor-history-item"), has_text="Today's brief").first.click()
    page.wait_for_selector(f'{T("noor-panel")} li[data-testid^="noor-line-"]', timeout=60_000)
    t2 = _panel_line(page, 1, "noor-why")
    page.wait_for_selector(T("noor-why-answer"), timeout=120_000)
    idle(page, 1500)
    thread_text = page.locator(T("noor-thread")).inner_text()
    page.locator(T("noor-history-button")).click()
    page.wait_for_timeout(400)
    hist = page.locator(T("noor-history-item")).all_inner_texts()
    return {"plain_words": page.locator(T("noor-plain-words")).count(), "line1": t1[:80], "line2": t2[:80], "thread1_title": first_thread, "thread2_title": page.locator(T("noor-context")).inner_text(),
            "line1_question_in_thread2": "What should we do?" in thread_text,
            "history": hist, "answer_speakers": page.locator(T("noor-answer-speaker")).count()}


def s_k7_fresh(page: Page, ui: str, ctx: dict) -> dict:
    """K7: opening Noor on Early Warning starts an empty thread; earlier threads in the history only."""
    home(page, ui, "brief")
    nav(page, "/early-warning")
    open_noor(page)
    return {"empty_thread": page.locator(T("noor-empty-thread")).count(), "context": page.locator(T("noor-context")).inner_text(),
            "turns_shown": page.locator(f'{T("noor-thread")} [data-turn]').count(),
            "history_items": page.locator(T("noor-history-button")).get_attribute("aria-label"),
            "mic": page.locator(T("noor-mic")).count(), "mic_lang": page.locator(T("noor-mic")).get_attribute("data-mic-lang")}


def s_noor_history(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    nav(page, "/early-warning")
    open_noor(page)
    page.locator(T("noor-history-button")).click()
    page.wait_for_selector(T("noor-history"), timeout=10_000)
    return {"items": page.locator(T("noor-history-item")).all_inner_texts()[:8]}


def s_noor_mic(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    open_noor(page)
    page.locator(T("noor-input")).fill("Which sectors are over appetite")
    mic = page.locator(T("noor-mic"))
    out = {"mic": mic.count(), "state_before": mic.get_attribute("data-mic-state"), "label": mic.get_attribute("aria-label")}
    if mic.is_enabled():
        mic.click()
        page.wait_for_timeout(1500)
    out["state_after"] = mic.get_attribute("data-mic-state")
    out["status"] = page.locator(T("noor-mic-status")).inner_text() if page.locator(T("noor-mic-status")).count() else ""
    out["box_kept"] = page.locator(T("noor-input")).input_value()
    return out


def s_noor_settings(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    open_noor(page)
    page.locator('[aria-label="Noor\'s name and voice"]').click()
    page.wait_for_selector(T("noor-settings"), timeout=10_000)
    return {"note": page.locator(T("noor-enhanced-voice-note")).count(),
            "gender": page.locator(T("noor-settings-gender")).inner_text()}


def s_cockpit_ask(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "ask")
    page.wait_for_selector(T("home-ask"), timeout=60_000)
    close_noor(page)
    return {"mic": page.locator(T("home-ask-mic")).count(), "mic_label": page.locator(T("home-ask-mic")).get_attribute("aria-label")}


def _dd_ask(page: Page, q: str) -> str:
    page.wait_for_selector(T("dealdesk-ask"), timeout=120_000)
    page.locator(T("dealdesk-ask")).fill(q)
    page.locator(T("dealdesk-ask-send")).click()
    page.wait_for_url(re.compile(r".*/deal-desk/thread/DK-[0-9a-f]+.*"), timeout=60_000)
    page.wait_for_selector(T("dealdesk-desk-turn"), timeout=180_000)
    idle(page, 1200, 60_000)
    return re.search(r"/deal-desk/thread/(DK-[0-9a-f]+)", page.url).group(1)


def s_k16_dealdesk(page: Page, ui: str, ctx: dict) -> dict:
    """K16: two landing questions -> two threads; Q1 is not in Q2's thread."""
    home(page, ui, "brief")
    close_noor(page)
    nav(page, "/deal-desk")
    q1, q2 = "Which proposals breach a hard limit?", "What is the pipeline headroom in Construction?"
    a = _dd_ask(page, q1)
    page.locator(T("dealdesk-thread-back")).click()
    page.wait_for_url(re.compile(r".*/deal-desk($|\?)"), timeout=60_000)
    b = _dd_ask(page, q2)
    asked = page.locator(f'{T("dealdesk-desk-thread")} {T("thread-turn-user")}').all_inner_texts()
    ctx["dd_threads"] = [a, b]
    return {"thread1": a, "thread2": b, "two_threads": a != b, "questions_in_thread2": asked, "q1_in_thread2": q1 in asked,
            "title": page.locator(T("dealdesk-thread-title")).inner_text(), "url_has_thread_desk": "thread=desk" in page.url,
            "composer_mic": page.locator(T("dealdesk-desk-mic")).count(), "answer_speakers": page.locator(T("answer-speaker")).count()}


def s_k16_dealdesk_recent(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    close_noor(page)
    nav(page, "/deal-desk")
    page.wait_for_selector(T("dealdesk-landing"), timeout=120_000)
    idle(page, 1500)
    cards = page.locator('[data-testid^="dealdesk-thread-card-"]')
    out = {"thread_cards": cards.all_inner_texts()[:4], "landing_mic": page.locator(T("dealdesk-mic")).count()}
    if cards.count():
        cards.first.click()
        page.wait_for_url(re.compile(r".*/deal-desk/thread/DK-.*"), timeout=60_000)
        page.wait_for_selector(T("dealdesk-desk-turn"), timeout=120_000)
        idle(page, 800)
        out["reopened"] = page.url.rsplit("/", 1)[-1]
        out["reopened_turns"] = page.locator(T("dealdesk-desk-turn")).count()
    return out


def _wi_ask(page: Page, q: str) -> str:
    page.wait_for_selector(T("whatif-ask"), timeout=120_000)
    page.locator(T("whatif-ask")).fill(q)
    page.locator(T("whatif-ask-send")).click()
    page.wait_for_url(re.compile(r".*/what-if/thread/.+"), timeout=90_000)
    idle(page, 1500, 30_000)
    return page.url.rsplit("/", 1)[-1].split("?")[0]


def s_k16_whatif(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    close_noor(page)
    nav(page, "/what-if")
    a = _wi_ask(page, "What happens to ECL if oil falls 20%?")
    nav(page, "/what-if")
    b = _wi_ask(page, "What happens to Stage 2 if rates rise 200 bps?")
    return {"thread1": a, "thread2": b, "two_threads": a != b, "composer_mic": page.locator('[data-testid$="-mic"]').count()}


def s_landing_mics(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    close_noor(page)
    out = {}
    for href, sel in (("/lenses", "lenses-mic"), ("/early-warning", "ews-mic"), ("/borrower-360", "b360-mic"),
                      ("/scorecard-validation", "sv-mic"), ("/playbook", "playbook-mic")):
        nav(page, href)
        try:
            page.wait_for_selector(T(sel), timeout=60_000)
            out[href] = page.locator(T(sel)).count()
        except Exception:  # noqa: BLE001
            out[href] = 0
    return out


def s_k16_scorecard(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    close_noor(page)
    ids = []
    for q in ("Validate the SME scorecard", "Validate the retail mortgage scorecard"):
        nav(page, "/scorecard-validation")
        page.wait_for_selector(T("sv-ask"), timeout=60_000)
        page.locator(T("sv-ask")).fill(q)
        page.locator(T("sv-ask-send")).click()
        page.wait_for_url(re.compile(r".*/scorecard-validation/thread/.+"), timeout=60_000)
        idle(page, 1500, 30_000)
        ids.append(page.url.rsplit("/", 1)[-1].split("?")[0])
    return {"threads": ids, "two_threads": len(set(ids)) == 2}


def s_k16_playbook(page: Page, ui: str, ctx: dict) -> dict:
    home(page, ui, "brief")
    close_noor(page)
    ids = []
    for q in ("hello", "good morning"):
        nav(page, "/playbook")
        page.wait_for_selector(T("playbook-chat-input"), timeout=60_000)
        page.locator(T("playbook-chat-input")).fill(q)
        page.locator(T("playbook-chat-send")).click()
        page.wait_for_url(re.compile(r".*/playbook\?thread=.+"), timeout=90_000)
        idle(page, 1200, 30_000)
        ids.append(page.url.split("thread=")[-1])
    return {"threads": ids, "two_threads": len(set(ids)) == 2}


def s_home_recent(page: Page, ui: str, ctx: dict) -> dict:
    """K16: Home Recent work is one list, newest first; the Deal Desk threads just asked are on it."""
    home(page, ui, "ask")
    close_noor(page)
    page.wait_for_selector(T("home-recent-work"), timeout=60_000)
    idle(page, 1500)
    cards = page.locator(T("home-work-card"))
    page.locator(T("home-recent-work")).scroll_into_view_if_needed()
    return {"kinds": [c.get_attribute("data-kind") for c in cards.all()], "first": cards.first.inner_text()[:120] if cards.count() else ""}


STEPS: list[tuple[str, str, Callable[[Page, str, dict], dict]]] = [
    ("01_brief", "K6 K9 K10", s_brief),
    ("02_brief_more", "K6", s_brief_more),
    ("03_k5_line_threads", "K5 K10", s_k5_two_lines),
    ("04_noor_history", "K5 K7", s_noor_history),
    ("05_k7_fresh_on_ews", "K7 K10", s_k7_fresh),
    ("06_noor_mic", "K10", s_noor_mic),
    ("07_noor_settings_voice", "K10", s_noor_settings),
    ("08_cockpit_ask_mic", "K10 K16", s_cockpit_ask),
    ("10_k16_dealdesk_two_threads", "K16 K10", s_k16_dealdesk),
    ("11_k16_dealdesk_recent", "K16", s_k16_dealdesk_recent),
    ("12_k16_whatif_two_threads", "K16", s_k16_whatif),
    ("13_k16_scorecard_two_threads", "K16", s_k16_scorecard),
    ("14_k16_playbook_two_threads", "K16", s_k16_playbook),
    ("15_module_mics", "K10", s_landing_mics),
    ("16_home_recent_work", "K16", s_home_recent),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ctx: dict[str, Any] = {"token": mint()}
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
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": ctx["token"], "domain": "127.0.0.1", "path": "/"}])
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
                note = ensure_dealdesk()
                if note:
                    rec["dealdesk"] = note
                try:
                    rec["checks"] = fn(page, ui, ctx)
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
                    rec["dev_overlay"] = page.locator("nextjs-portal").count()
                except Exception:  # noqa: BLE001 - a crashed tab
                    rec["dev_overlay"] = None
                    rec["error"] = rec.get("error") or "crashed"
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
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} {rec['seconds']}s "
                      f"{json.dumps(rec.get('checks'), default=str)[:400]}", flush=True)
                done = {(r["step"], r["size"]) for r in report}
                path.write_text(json.dumps([r for r in kept if (r["step"], r["size"]) not in done] + report, indent=1, default=str))
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
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
