"""PLAN_R16 session t (M7): click-through walk of the thread actions (Share, Trace, Word, Add to report) and the
"write a memo" intent in every module, on the production build.

  .venv/bin/python ops/r16_t_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only dd,wi,...]

The first page of each module is opened once (its landing); everything after is clicks and typing. Screens, the
downloaded Word files and walk.json go to docs/v5/r16_review/t/. Fictional data only; a minted session (no password).
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

OUT = V5 / "docs" / "v5" / "r16_review" / "t"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LONG = 240_000


def txt(page: Page, sel: str, n: int = 300) -> str:
    loc = page.locator(sel).first
    return " ".join(loc.inner_text().split())[:n] if loc.count() else ""


def snap(page: Page, ctx: dict, name: str, sel: str | None = None) -> None:
    if sel and page.locator(sel).count():
        page.locator(sel).last.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"{name}_{ctx['tag']}.png"))


def last_bar(page: Page, prefix: str = "thread-actions") -> Any:
    return page.locator(f'[data-thread-actions][data-testid="{prefix}"]').last


def bar_checks(page: Page, ctx: dict, key: str, prefix: str = "thread-actions", word: bool = True, share: bool = True) -> dict:
    """Trace panel, Word download, Share dialog on the last answer's bar."""
    out: dict[str, Any] = {}
    bar = last_bar(page, prefix)
    bar.scroll_into_view_if_needed()
    out["buttons"] = [b for b in ("share", "trace", "word", "report") if bar.locator(T(f"{prefix}-{b}")).count()]
    snap(page, ctx, f"{key}_bar")
    bar.locator(T(f"{prefix}-trace")).click()
    page.wait_for_selector(T("thread-trace-relations"), timeout=60_000)
    page.wait_for_timeout(400)
    out["trace_plain_words"] = txt(page, T("thread-trace-plain-words"), 300)
    out["trace_relations"] = txt(page, T("thread-trace-relations"), 200)
    snap(page, ctx, f"{key}_trace")
    page.locator(T("thread-trace-close")).click()
    if word:
        w = bar.locator(T(f"{prefix}-word"))
        with page.expect_download(timeout=120_000) as dl:
            w.click()
            if page.locator(T(f"{prefix}-word-menu")).count():
                page.locator(T(f"{prefix}-word-thread")).last.click()
        d = dl.value
        dest = OUT / f"{key}_word_{ctx['tag']}.docx"
        d.save_as(str(dest))
        out["word_file"] = d.suggested_filename
        out["word_bytes"] = dest.stat().st_size
    if share and bar.locator(T(f"{prefix}-share")).count():
        bar.locator(T(f"{prefix}-share")).click()
        page.wait_for_selector(T("thread-share-users"), timeout=60_000)
        out["share_plain_words"] = txt(page, T("thread-share-plain-words"), 200)
        snap(page, ctx, f"{key}_share")
        page.locator(T("thread-share-close")).click()
    return out


def memo(page: Page, ctx: dict, key: str, composer: str, send: str | None, text: str, timeout: int = LONG) -> dict:
    """Type a memo request in the thread's composer; the Word document is written and downloadable."""
    n0 = page.locator(T("thread-memo")).count()
    box = page.locator(composer).last
    box.click()
    box.fill(text)
    if send:
        page.locator(send).last.click()
    else:
        box.press("Enter")
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"thread-memo\"]').length > {n0}", timeout=30_000)
    card = page.locator(T("thread-memo")).last
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        st = card.get_attribute("data-state")
        if st in ("done", "error", "empty"):
            break
        page.wait_for_timeout(800)
    st = card.get_attribute("data-state")
    out: dict[str, Any] = {"state": st, "card": " ".join(card.inner_text().split())[:400]}
    card.scroll_into_view_if_needed()
    snap(page, ctx, f"{key}_memo")
    if st == "done":
        with page.expect_download(timeout=60_000) as dl:
            card.locator(T("thread-memo-download")).click()
        dest = OUT / f"{key}_memo_{ctx['tag']}.docx"
        dl.value.save_as(str(dest))
        out["memo_file"] = dl.value.suggested_filename
        out["memo_bytes"] = dest.stat().st_size
    return out


def wait_answers(page: Page, sel: str, n: int, timeout: int = LONG) -> None:
    page.wait_for_function(f"() => document.querySelectorAll('{sel}').length >= {n}", timeout=timeout)
    idle(page, 600)


# ---------------------------------------------------------------- Deal Desk
def s_dd(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("dealdesk-home")} textarea').first
    box.click()
    box.fill("which proposals breach a hard limit")
    box.press("Enter")
    page.wait_for_selector(T("dealdesk-desk-thread"), timeout=LONG)
    wait_answers(page, '[data-testid="dealdesk-desk-turn"] [data-thread-actions]', 1)
    out = bar_checks(page, ctx, "dd")
    out.update(memo(page, ctx, "dd", T("dealdesk-desk-composer"), None, "prepare a memo to the CRO"))
    return out


def s_dd_report(page: Page, ui: str, ctx: dict) -> dict:
    bar = last_bar(page)
    bar.locator(T("thread-actions-report")).click()
    page.wait_for_timeout(1500)
    snap(page, ctx, "dd_report")
    found = page.locator('[role="dialog"]').count()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    if page.locator('[role="dialog"]').count():
        page.locator('[role="dialog"] button:has-text("Cancel")').first.click()
    return {"dialog": bool(found)}


def s_dd_ask_then_write(page: Page, ui: str, ctx: dict) -> dict:
    return memo(page, ctx, "dd2", T("dealdesk-desk-composer"), None, "write a note on which proposals are renewals due this quarter")


def wait_memo(page: Page, ctx: dict, key: str, timeout: int = LONG) -> dict:
    page.wait_for_selector(T("thread-memo"), timeout=timeout)
    card = page.locator(T("thread-memo")).last
    t0 = time.time()
    while time.time() - t0 < timeout / 1000 and card.get_attribute("data-state") not in ("done", "error", "empty"):
        page.wait_for_timeout(800)
    card.scroll_into_view_if_needed()
    snap(page, ctx, f"{key}_memo")
    out: dict[str, Any] = {"state": card.get_attribute("data-state"), "card": " ".join(card.inner_text().split())[:300]}
    if out["state"] == "done":
        with page.expect_download(timeout=60_000) as dl:
            card.locator(T("thread-memo-download")).click()
        dest = OUT / f"{key}_memo_{ctx['tag']}.docx"
        dl.value.save_as(str(dest))
        out["memo_file"] = dl.value.suggested_filename
    return out


def s_dd_landing(page: Page, ui: str, ctx: dict) -> dict:
    """Anne's M7 case typed in one go on the Deal Desk landing: the question is answered, then the memo is written."""
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("dealdesk-home")} textarea').first
    box.click()
    box.fill("prepare a memo on which proposals breach a hard limit")
    box.press("Enter")
    page.wait_for_selector(T("dealdesk-desk-thread"), timeout=LONG)
    return wait_memo(page, ctx, "dd4")


def s_wi_landing(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(T("whatif-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("whatif-home")} textarea').first
    box.click()
    box.fill("write a note to the CRO on the ECL of the construction sector")
    box.press("Enter")
    page.wait_for_selector(T("whatif-thread"), timeout=LONG)
    return wait_memo(page, ctx, "wi2")


def s_share_send(page: Page, ui: str, ctx: dict) -> dict:
    """Share the memo from its card: one colleague, the Word memo attached, Send (CreditProbe Mail)."""
    card = page.locator(T("thread-memo")).last
    card.locator(T("thread-memo-share")).click()
    page.wait_for_selector(T("thread-share-users"), timeout=60_000)
    page.locator('[data-testid^="thread-share-user-"]').first.check()
    attach = page.locator(T("thread-share-attach"))
    out: dict[str, Any] = {"attach_default": attach.is_checked()}
    if not out["attach_default"]:
        attach.check()
    page.locator(T("thread-share-note")).fill("The note from the What-If thread, with the Word file.")
    page.locator(T("thread-share-send")).click()
    page.wait_for_selector(T("thread-share-done"), timeout=60_000)
    out["done"] = txt(page, T("thread-share-done"), 200)
    snap(page, ctx, "wi_share_sent")
    page.locator(T("thread-share-close")).click()
    return out


# ---------------------------------------------------------------- What-If
def s_wi(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(T("whatif-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("whatif-home")} textarea').first
    box.click()
    box.fill("what is the ECL of the construction sector?")
    box.press("Enter")
    page.wait_for_selector(T("whatif-thread"), timeout=LONG)
    wait_answers(page, '[data-testid="whatif-turn"] [data-thread-actions]', 1)
    out = bar_checks(page, ctx, "wi")
    out.update(memo(page, ctx, "wi", T("whatif-composer"), None, "write a note to the CRO on this"))
    return out


# ---------------------------------------------------------------- Lenses
def s_ln(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/lenses", wait_until="domcontentloaded")
    page.wait_for_selector(T("lenses-home"), timeout=LONG)
    idle(page, 800)
    card = page.locator(f'{T("lenses-featured-grid")} button').first
    card.click()
    page.wait_for_selector(T("lens-assistant"), timeout=LONG)
    idle(page, 1500)
    box = page.locator(T("lens-assistant-composer")).last
    box.click()
    box.fill("which sector has the highest Stage 2 share?")
    box.press("Enter")
    wait_answers(page, '[data-testid="lens-assistant"] [data-thread-actions]', 1)
    out = bar_checks(page, ctx, "ln")
    out.update(memo(page, ctx, "ln", T("lens-assistant-composer"), None, "give me this as a Word document"))
    return out


# ---------------------------------------------------------------- Scorecard
def s_sv(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/scorecard-validation", wait_until="domcontentloaded")
    page.wait_for_selector(T("sv-ask"), timeout=LONG)
    idle(page, 800)
    page.locator(T("sv-ask")).fill("Validate the SME scorecard")
    page.locator(T("sv-ask-send")).click()
    page.wait_for_selector(T("sv-thread"), timeout=LONG)
    wait_answers(page, '[data-testid="sv-turn"] [data-thread-actions]', 1)
    out = bar_checks(page, ctx, "sv")
    out.update(memo(page, ctx, "sv", T("sv-composer"), None, "draft a committee paper"))
    return out


# ---------------------------------------------------------------- Early Warning, Borrower 360
def s_ews(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/early-warning", wait_until="domcontentloaded")
    page.wait_for_selector(T("ews-level-summary"), timeout=LONG)
    idle(page, 1000)
    return bar_checks(page, ctx, "ews", prefix="ews-level-actions", share=False)


def s_agent(page: Page, ui: str, ctx: dict) -> dict:
    """The Early Warning triage agent's answer (the agent run drawer) carries the bar too."""
    page.locator(T("ews-triage-agent")).first.click()
    page.wait_for_selector(T("agent-run-drawer"), timeout=LONG)
    page.wait_for_selector(T("agent-actions"), timeout=LONG)
    idle(page, 800)
    out = bar_checks(page, ctx, "agent", prefix="agent-actions")
    page.keyboard.press("Escape")
    return out


def s_b360(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/borrower-360", wait_until="domcontentloaded")
    page.wait_for_selector('table tbody tr', timeout=LONG)
    idle(page, 800)
    cell = page.locator('table tbody tr').first.locator('a, button').first
    (cell if cell.count() else page.locator('table tbody tr td').first).click()
    page.wait_for_selector(T("b360-workspace"), timeout=LONG)
    page.wait_for_selector(T("b360-actions"), timeout=LONG)
    idle(page, 1000)
    return bar_checks(page, ctx, "b360", prefix="b360-actions", share=False)


# ---------------------------------------------------------------- Noor, intel panel, Cockpit
def s_noor(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 600)
    if not page.locator(T("noor-chip-brief")).count():
        page.get_by_role("button", name="Ask Noor").first.click()
    page.wait_for_selector(T("noor-chip-brief"), timeout=60_000)
    page.locator(T("noor-new-thread")).click()
    page.locator(T("noor-chip-brief")).click()
    wait_answers(page, '[data-testid="noor-thread"] [data-thread-actions]', 1, 120_000)
    out = bar_checks(page, ctx, "noor", share=False)
    out.update(memo(page, ctx, "noor", T("noor-input"), None, "write a memo of this"))
    return out


def s_intel(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    idle(page, 1000)
    if not page.locator(T("cockpit-v4-question")).count():
        page.locator(T("home-tab-ask")).click()
    page.wait_for_selector(T("cockpit-v4-question"), timeout=LONG)
    idle(page, 800)
    page.locator(T("cockpit-v4-question")).fill("which renewals are due in the next 90 days?")
    page.locator(T("cockpit-v4-ask")).click()
    page.wait_for_selector(T("intel-actions"), timeout=120_000)
    idle(page, 1500)
    return bar_checks(page, ctx, "intel", prefix="intel-actions")


# ---------------------------------------------------------------- Playbook, Cockpit
def s_pb(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/playbook", wait_until="domcontentloaded")
    page.wait_for_selector(T("playbook-chat-input"), timeout=LONG)
    idle(page, 800)
    page.locator(T("playbook-chat-input")).fill("What is the corporate book's ECL this quarter?")
    page.locator(T("playbook-chat-send")).click()
    page.wait_for_selector(T("playbook-start-thread"), timeout=LONG)
    wait_answers(page, '[data-testid="playbook-chat-reply"] [data-thread-actions]', 1)
    out = bar_checks(page, ctx, "pb")
    out.update(memo(page, ctx, "pb", T("playbook-chat-input"), None, "write a memo of this"))
    return out


def s_cockpit(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    idle(page, 1000)
    if not page.locator(T("cockpit-v4-question")).count():
        page.locator(T("home-tab-ask")).click()
    page.locator(T("cockpit-v4-question")).fill("What is the Stage 2 exposure by sector?")
    page.locator(T("cockpit-v4-ask")).click()
    page.wait_for_selector('[data-testid="v4-turn-assistant"]', timeout=LONG)
    idle(page, 2000)
    page.wait_for_selector('[data-testid="cockpit-thread-actions"]', timeout=120_000)
    out = bar_checks(page, ctx, "cockpit", prefix="cockpit-thread-actions", share=False)
    out.update(memo(page, ctx, "cockpit", '[data-testid="v4-thread-composer"] textarea, textarea', None, "prepare a memo to the CRO"))
    return out


STEPS: list[tuple[str, str, Callable[[Page, str, dict], dict]]] = [
    ("dd_01_thread", "Deal Desk: bar, Trace, Word, Share, memo intent", s_dd),
    ("dd_02_report", "Deal Desk: Add to report", s_dd_report),
    ("dd_03_ask_then_write", "Deal Desk: memo with a question", s_dd_ask_then_write),
    ("dd_04_landing_memo", "Deal Desk: memo with its question from the landing", s_dd_landing),
    ("wi_01_thread", "What-If", s_wi),
    ("wi_02_landing_memo", "What-If: note with its question from the landing", s_wi_landing),
    ("wi_03_share_send", "Share the note in Mail with the Word file attached", s_share_send),
    ("ln_01_thread", "Lenses", s_ln),
    ("sv_01_thread", "Scorecard", s_sv),
    ("ews_01_level", "Early Warning", s_ews),
    ("ews_02_agent", "Early Warning triage agent", s_agent),
    ("b360_01", "Borrower 360", s_b360),
    ("noor_01", "Noor", s_noor),
    ("intel_01", "Intel panel", s_intel),
    ("pb_01", "Playbook", s_pb),
    ("cockpit_01", "Cockpit", s_cockpit),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    path = OUT / "walk.json"
    if path.exists() and only:
        report = [r for r in json.loads(path.read_text()) if not any(r["step"].startswith(o) for o in only)]
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
                if only and not any(sid.startswith(o) for o in only):
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
                      f"{json.dumps(rec.get('checks'), default=str, ensure_ascii=False)[:600]}", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"]]
    print(f"WALK {len(report) - len(miss)}/{len(report)} found; {sum(1 for r in report if not r['clean'])} with errors")
    return 0 if not miss else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sizes = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sizes, {o for o in a.only.split(",") if o}))
