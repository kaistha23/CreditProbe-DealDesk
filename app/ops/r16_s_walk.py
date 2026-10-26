"""R16 session s (M8): the click-through walk of Scorecard Validation as a monitoring system, on the running services
and the production UI build (`next start`, V5_UI_MODE=prod).

    .venv/bin/python ops/r16_s_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800]

Clicks, not URLs: Home → Noor's brief "n more" → the scorecard monitoring alert → Open (deep dive); Home → the Scorecard Validation link → Scorecards today (front page) → the lead breach (deep dive) →
Back → a health card → Back → Ask tab (register, history) → front page starter "Full MMSG validation: SME" → the
thread with the results and the MMSG panel → download the Word report → propose the conclusion as maker (Anne) → the
four-eyes refusal when Anne tries to check her own → a checker (Faisal Al-Qahtani, Head of Risk) approves.
Screens in docs/v5/r16_review/s/<size>/<nn>_<step>.png and docs/v5/r16_review/s/walk.json. Sessions are minted in the
local identity store (no password read or printed).
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
OUT = V5 / "docs" / "v5" / "r16_review" / "s"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731
IGNORED_CONSOLE = ("favicon", "Download the React DevTools", "net::ERR_ABORTED", "Failed to load resource")


def mint(username: str) -> str:
    from backend.identity_v5 import store as ids
    ids.ensure()
    with ids.db() as con:
        tok = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions(token_hash, username, view_as, created_at, expires_at) VALUES(?,?,?,?,?)",
                    (ids._hash_token(tok), username, None, ids.now(), ids._later(120)))
        con.commit()
    return tok


class Walk:
    def __init__(self, page: Page, folder: Path):
        self.page, self.folder, self.steps, self.n = page, folder, [], 0
        self.errors: list[str] = []
        self.console: list[str] = []
        page.on("pageerror", lambda e: self.errors.append(str(e)[:300]))
        page.on("console", lambda m: self.console.append(m.text[:300]) if m.type == "error" and not any(s in m.text for s in IGNORED_CONSOLE) else None)

    def step(self, name: str, found: bool, full: bool = False, **extra: Any) -> None:
        self.n += 1
        p = self.page
        shot = self.folder / f"{self.n:02d}_{name}.png"
        try:
            p.screenshot(path=str(shot), full_page=full)
        except Exception:  # noqa: BLE001
            pass
        geo = p.evaluate("() => ({doc: document.documentElement.scrollWidth, vw: window.innerWidth})")
        rec = {"n": self.n, "step": name, "found": bool(found), "page_errors": list(self.errors), "console_errors": list(self.console),
               "dev_overlay": p.locator("nextjs-portal").count() > 0, "wider_than_viewport": geo["doc"] > geo["vw"] + 1,
               "shot": str(shot.relative_to(V5)), **extra}
        self.errors.clear()
        self.console.clear()
        self.steps.append(rec)
        print(f"  {self.n:02d} {name}: {'found' if found else 'MISSING'} {json.dumps(extra, ensure_ascii=False)[:200]}", flush=True)


def visible(page: Page, sel: str, ms: int = 30_000) -> bool:
    try:
        page.wait_for_selector(sel, timeout=ms, state="visible")
        return True
    except Exception:  # noqa: BLE001
        return False


def to_scorecard(p: Page, ui: str) -> bool:
    """From Home, click the Scorecard Validation link in the navigation (open a menu that holds it if needed)."""
    p.goto(f"{ui}/", wait_until="domcontentloaded")
    visible(p, "body", 60_000)
    p.wait_for_timeout(2500)
    link = p.locator('a[href="/scorecard-validation"]')
    for _ in range(3):
        vis = [i for i in range(link.count()) if link.nth(i).is_visible()]
        if vis:
            link.nth(vis[0]).click()
            return visible(p, T("sv-home"), 60_000)
        # the link may sit in a collapsed group of the side navigation
        for label in ("Model risk", "Risk", "Tools", "More", "Modules"):
            b = p.get_by_role("button", name=label)
            if b.count() and b.first.is_visible():
                b.first.click()
                p.wait_for_timeout(500)
                break
        else:
            break
    return False


def brief_to_deep_dive(p: Page, w: Walk, ui: str) -> None:
    """Home → Brief → "n more" → the scorecard monitoring line → Open → the scorecard's deep dive."""
    p.goto(f"{ui}/", wait_until="domcontentloaded")
    visible(p, T("noor-headline"), 120_000)
    if p.locator(T("noor-more")).count():
        p.locator(T("noor-more")).first.click()
        p.wait_for_timeout(800)
    line = p.locator('[data-testid^="noor-line-scorecard:"]')
    ok = line.count() > 0
    if ok:
        line.first.scroll_into_view_if_needed()
        p.wait_for_timeout(400)
    w.step("noor_brief_scorecard_alert", ok, lines=line.count(), title=line.first.inner_text()[:120] if ok else "")
    if ok:
        line.first.locator(T("noor-open")).click()
        ok = visible(p, T("sm-deep"), 60_000)
        w.step("brief_open_to_deep_dive", ok, scorecard=p.locator(T("sm-deep")).get_attribute("data-scorecard") if ok else "")


def walk(p: Page, w: Walk, ui: str, checker_token: str, ctx_factory) -> None:
    brief_to_deep_dive(p, w, ui)
    clicked = to_scorecard(p, ui)
    if not clicked:
        p.goto(f"{ui}/scorecard-validation", wait_until="domcontentloaded")
    ok = visible(p, T("sm-front"), 60_000) and visible(p, T("sm-lead"), 90_000)
    w.step("front_page", ok, clicked_from_nav=clicked, stories=p.locator(T("sm-story")).count() + p.locator(T("sm-lead")).count(),
           health=p.locator(T("sm-health")).count(), headline=p.locator(T("sm-headline-top")).inner_text() if ok else "")
    w.step("front_page_full", ok, full=True)
    p.locator(T("sm-paper")).scroll_into_view_if_needed()
    p.wait_for_timeout(400)
    w.step("front_page_newspaper", p.locator(T("sm-story")).count() >= 4)
    lead_head = p.locator(T("sm-lead")).locator(T("sm-headline")).inner_text()
    p.locator(T("sm-lead")).click()
    ok = visible(p, T("sm-deep"), 60_000) and visible(p, T("sm-criteria"))
    w.step("deep_dive_lead", ok, lead=lead_head, scorecard=p.locator(T("sm-deep")).get_attribute("data-scorecard") if ok else "")
    p.locator(T("sm-root-cause")).scroll_into_view_if_needed()
    p.wait_for_timeout(400)
    w.step("deep_dive_root_cause_actions", p.locator(T("sm-action")).count() > 0, actions=p.locator(T("sm-action")).count())
    p.locator(T("sm-charts")).scroll_into_view_if_needed()
    p.wait_for_timeout(1200)
    w.step("deep_dive_tests_over_time", p.locator(T("sm-charts")).locator("[data-testid^=sv-chart-card-]").count() > 0)
    p.locator(T("sm-segments")).scroll_into_view_if_needed()
    p.wait_for_timeout(400)
    w.step("deep_dive_segments_grades_characteristics", p.locator(T("sm-segment")).count() > 0)
    w.step("deep_dive_full", True, full=True)
    p.locator(T("sm-deep-back")).click()
    ok = visible(p, T("sm-front"), 30_000)
    w.step("back_to_front", ok)
    visible(p, T("sm-health"), 60_000)
    p.locator(f'{T("sm-health")}[data-scorecard="RET-APP"]').click()
    ok = visible(p, T("sm-deep"), 60_000) and visible(p, T("sm-segments"))
    p.locator(T("sm-segments")).scroll_into_view_if_needed()
    p.wait_for_timeout(400)
    w.step("deep_dive_retail_application_scope", ok and p.locator(f'{T("sm-segment")}[data-in-scope="false"]').count() > 0)
    p.locator(T("sm-deep-back")).click()
    visible(p, T("sm-front"), 30_000)
    p.locator(T("sv-tab-home-ask")).click()
    ok = visible(p, T("sv-ask-tab"), 30_000) and visible(p, T("sm-register"), 60_000)
    w.step("ask_tab_register_history", ok, findings=p.locator(T("sm-finding")).count(), overdue=p.locator(f'{T("sm-finding")}[data-overdue="true"]').count())
    w.step("ask_tab_full", ok, full=True)
    p.locator(T("sv-tab-home-today")).click()
    visible(p, T("sm-front"), 30_000)
    p.locator(T("sm-starter")).first.click()
    ok = visible(p, T("sv-thread"), 60_000) and visible(p, T("sm-mmsg"), 180_000)
    w.step("full_mmsg_validation_thread", ok)
    p.locator(T("sm-mmsg")).scroll_into_view_if_needed()
    p.wait_for_timeout(500)
    w.step("mmsg_panel", ok, proposed=p.locator(T("sm-mmsg-proposed")).inner_text()[:160] if ok else "")
    size = 0
    try:
        with p.expect_download(timeout=120_000) as dl:
            p.locator(T("sm-mmsg-download")).click()
        path = dl.value.path()
        size = Path(path).stat().st_size if path else 0
        (OUT / "mmsg_report_sample.docx").write_bytes(Path(path).read_bytes())
    except Exception as e:  # noqa: BLE001
        print("download failed", e)
    w.step("mmsg_word_downloaded", size > 10_000, bytes=size)
    p.locator(T("sm-mmsg-note")).fill("Recalibrate the grade PDs; PD overlay until the Model Oversight Committee approves.")
    p.locator(T("sm-mmsg-propose")).click()
    ok = visible(p, f'{T("sm-mmsg")}[data-state="proposed"]', 30_000)
    w.step("maker_proposed", ok)
    p.locator(T("sm-mmsg-approve")).click()
    ok = visible(p, T("sm-mmsg-error"), 30_000)
    w.step("four_eyes_refusal_for_the_maker", ok, error=p.locator(T("sm-mmsg-error")).inner_text() if ok else "")
    thread_url = p.url
    ctx2 = ctx_factory(checker_token)
    q = ctx2.new_page()
    w2 = Walk(q, w.folder)
    w2.n = w.n
    q.goto(thread_url, wait_until="domcontentloaded")
    ok = visible(q, T("sm-mmsg-approve"), 120_000)
    q.locator(T("sm-mmsg-approve")).scroll_into_view_if_needed()
    q.locator(T("sm-mmsg-note")).fill("Agreed. Overlay to be in the Q4 ECL run.")
    q.locator(T("sm-mmsg-approve")).click()
    ok = visible(q, f'{T("sm-mmsg")}[data-state="approved"]', 30_000)
    w2.step("checker_approved", ok, checker="Faisal Al-Qahtani")
    w.steps += w2.steps
    w.n = w2.n
    ctx2.close()
    p.locator(T("sv-back")).click()
    ok = visible(p, T("sv-home"), 30_000)
    p.wait_for_timeout(1500)
    w.step("back_after_validation", ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for size in a.sizes.split(","):
            wd, ht = (int(x) for x in size.split("x"))
            folder = OUT / size
            folder.mkdir(parents=True, exist_ok=True)

            def ctx_for(token: str):
                c = b.new_context(viewport={"width": wd, "height": ht}, accept_downloads=True)
                c.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
                return c
            ctx = ctx_for(mint("anne"))
            page = ctx.new_page()
            w = Walk(page, folder)
            print(f"== {size}", flush=True)
            try:
                walk(page, w, a.ui, mint("faisal.alqahtani"), ctx_for)
            except Exception as e:  # noqa: BLE001
                w.step("aborted", False, error=str(e)[:300])
            ctx.close()
            summary[size] = w.steps
        b.close()
    (OUT / "walk.json").write_text(json.dumps(summary, indent=1))
    tot = sum(len(v) for v in summary.values())
    found = sum(s["found"] for v in summary.values() for s in v)
    errs = sum(len(s["page_errors"]) + len(s["console_errors"]) for v in summary.values() for s in v)
    wide = sum(s["wider_than_viewport"] for v in summary.values() for s in v)
    over = sum(s["dev_overlay"] for v in summary.values() for s in v)
    print(f"steps {tot} found {found} page/console errors {errs} wider {wide} overlay {over}")
    return 0 if found == tot and not errs else 1


if __name__ == "__main__":
    sys.exit(main())
