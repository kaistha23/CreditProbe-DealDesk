"""PLAN_R15 session a: the click-through walk for L1 (tour only on the button), L2 (Settings -> Voice) and L9 (Noor
answers in the page context), on the running services and the production UI build (`next start`, V5_UI_MODE=prod).

    .venv/bin/python ops/r15_a_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800]

Screens in docs/v5/r15_review/a/<size>/<nn>_<step>.png and docs/v5/r15_review/a/walk.json (every step: found or not,
page errors, console errors, development overlay, document wider than the viewport). A minted session cookie is used
(no password is read or printed). Headless Chromium has no voices, so a stand-in for the browser's speech lists a Mac's
usual voices (male and female, English and Arabic, Enhanced and Premium) and records every utterance (voice, rate,
pitch); the walk chooses a voice, checks Noor and the tour read with it, then clears the choice again (no voice is left
fixed by the walk).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
sys.path.insert(0, str(V5))
from r11_ui_shots import mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r15_review" / "a"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731
IGNORED_CONSOLE = ("favicon", "Download the React DevTools", "net::ERR_ABORTED", "Failed to load resource")
CHOSEN = ("Zoe (Premium)", "en-US")

FAKE_SPEECH = r"""
(() => {
  const voices = [
    {name: "Samantha", lang: "en-US", localService: true, default: true},
    {name: "Zoe (Premium)", lang: "en-US", localService: true, default: false},
    {name: "Evan (Enhanced)", lang: "en-US", localService: true, default: false},
    {name: "Daniel", lang: "en-GB", localService: true, default: false},
    {name: "Kate", lang: "en-GB", localService: true, default: false},
    {name: "Majed", lang: "ar-001", localService: true, default: false},
    {name: "Maged", lang: "ar-SA", localService: true, default: false},
    {name: "Laila", lang: "ar-SA", localService: true, default: false},
    {name: "Google UK English Male", lang: "en-GB", localService: false, default: false},
  ].map((v) => ({...v, voiceURI: v.name}));
  window.__spoken = [];
  const synth = {
    speaking: false, pending: false, paused: false,
    getVoices: () => voices,
    addEventListener: () => {}, removeEventListener: () => {},
    cancel() { this.speaking = false; },
    pause() {}, resume() {},
    speak(u) {
      window.__spoken.push({voice: u.voice && u.voice.name, rate: u.rate, pitch: u.pitch, lang: u.lang, text: String(u.text).slice(0, 160),
                            during_tour: !!document.querySelector('[data-testid="tour-player"]')});
      this.speaking = true;
      setTimeout(() => { u.onstart && u.onstart(new Event("start")); }, 5);
      setTimeout(() => { this.speaking = false; u.onend && u.onend(new Event("end")); }, 60);
    },
  };
  Object.defineProperty(window, "speechSynthesis", {value: synth, configurable: true});
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
"""


class Walk:
    def __init__(self, page: Page, folder: Path):
        self.page, self.folder, self.steps, self.n = page, folder, [], 0
        self.errors: list[str] = []
        self.console: list[str] = []
        page.on("pageerror", lambda e: self.errors.append(str(e)[:300]))
        page.on("console", lambda m: self.console.append(m.text[:300]) if m.type == "error" and not any(
            s in m.text for s in IGNORED_CONSOLE) else None)

    def step(self, name: str, found: bool, **extra: Any) -> None:
        self.n += 1
        p = self.page
        shot = self.folder / f"{self.n:02d}_{name}.png"
        try:
            p.screenshot(path=str(shot))
        except Exception:  # noqa: BLE001
            pass
        geo = p.evaluate("() => ({doc: document.documentElement.scrollWidth, vw: window.innerWidth})")
        rec = {"n": self.n, "step": name, "found": bool(found), "page_errors": list(self.errors), "console_errors": list(self.console),
               "dev_overlay": p.locator("nextjs-portal").count() > 0, "wider_than_viewport": geo["doc"] > geo["vw"] + 1,
               "shot": str(shot.relative_to(V5)), **extra}
        self.errors.clear()
        self.console.clear()
        self.steps.append(rec)
        print(f"  {self.n:02d} {name}: {'found' if found else 'MISSING'} {json.dumps(extra, ensure_ascii=False)[:220]}")


def spoken(page: Page) -> list[dict[str, Any]]:
    return page.evaluate("() => window.__spoken || []")


def visible(page: Page, sel: str, ms: int = 15_000) -> bool:
    try:
        page.wait_for_selector(sel, timeout=ms, state="visible")
        return True
    except Exception:  # noqa: BLE001
        return False


def attached(page: Page, sel: str, ms: int = 15_000) -> bool:
    try:
        page.wait_for_selector(sel, timeout=ms, state="attached")
        return True
    except Exception:  # noqa: BLE001
        return False


def open_voice_settings(p: Page) -> bool:
    """Clicks, not URLs: the user menu -> Settings -> Voice -> Open."""
    visible(p, T("user-menu"), 120_000)
    p.locator(T("user-menu")).click()
    visible(p, T("menu-settings"))
    p.locator(T("menu-settings")).click()
    ok = visible(p, T("settings-voice"), 60_000)
    p.locator(T("settings-voice")).scroll_into_view_if_needed()
    return ok


def walk_l1(w: Walk, ui: str) -> None:
    p = w.page
    # Even with the old start links, nothing but the button starts the tour (and no first-login prompt appears).
    p.goto(f"{ui}/?tour=1&tour_prompt=1", wait_until="domcontentloaded")
    ok = visible(p, T("tour-take"), 120_000)
    p.wait_for_timeout(3000)
    w.step("l1_signed_in_no_tour", ok and p.locator(T("tour-player")).count() == 0 and p.locator(T("tour-prompt")).count() == 0,
           player=p.locator(T("tour-player")).count(), prompt=p.locator(T("tour-prompt")).count())
    p.locator(T("tour-take")).click()
    ok = attached(p, T("tour-player"), 30_000)
    p.wait_for_timeout(1200)
    w.step("l1_tour_from_the_button", ok)
    p.keyboard.press("Escape")
    p.wait_for_timeout(600)
    if p.locator(T("tour-player")).count():
        p.locator(T("tour-skip")).first.click()
        p.wait_for_timeout(600)
    w.step("l1_tour_closed", p.locator(T("tour-player")).count() == 0)


def walk_l2(w: Walk, ui: str) -> dict[str, Any]:
    p = w.page
    out: dict[str, Any] = {}
    p.goto(f"{ui}/", wait_until="domcontentloaded")
    ok = open_voice_settings(p)
    w.step("l2_settings_voice_card", ok)
    p.locator(T("settings-voice-open")).click()
    ok = visible(p, T("voice-sampler"), 60_000) and visible(p, T("voice-row"), 20_000)
    p.wait_for_timeout(2500)   # the brief's lines
    rows = p.locator(T("voice-row"))
    genders = sorted(set(rows.evaluate_all("els => els.map(e => e.dataset.gender)")))
    quality = sorted(set(rows.evaluate_all("els => els.map(e => e.dataset.quality)")))
    nothing = [p.locator(T(f"voice-chosen-{g}")).get_attribute("data-chosen") for g in ("en", "ar-gulf")]
    w.step("l2_voice_buffet", ok and nothing == ["false", "false"], voices=rows.count(), genders=genders, quality=quality,
           chosen_before=nothing, sample=p.locator(T("voice-sample-en")).inner_text()[:120])
    for k in ("offline", "cloud"):
        p.locator(T(f"voice-options-{k}")).scroll_into_view_if_needed()
    w.step("l2_more_voices_labelled", p.locator(T("voice-option")).count() >= 6 and p.locator(T("voice-mac-downloads")).count() == 1,
           options=p.locator(T("voice-option")).count(), downloads=p.locator(T("voice-download")).count())
    p.locator(T("voice-group-en")).scroll_into_view_if_needed()
    # rate 0.86 on the English slider, then listen to Zoe (Premium)
    p.locator(T("voice-rate-en")).evaluate("(el) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; "
                                           "s.call(el, '0.86'); el.dispatchEvent(new Event('input', {bubbles: true})); }")
    zoe = p.locator(f'{T("voice-row")}[data-voice="{CHOSEN[0]}"]')
    n0 = len(spoken(p))
    zoe.locator(T("voice-listen")).click()
    p.wait_for_timeout(500)
    said = spoken(p)[n0:]
    w.step("l2_listen_one_voice", bool(said) and said[0]["voice"] == CHOSEN[0] and abs(said[0]["rate"] - 0.86) < 1e-6,
           utterance=said[:1])
    zoe.locator(T("voice-use")).click()
    ok = visible(p, T("voice-msg"), 20_000)
    p.wait_for_timeout(500)
    w.step("l2_chosen_for_english", ok and p.locator(T("voice-chosen-en")).get_attribute("data-chosen") == "true",
           line=p.locator(T("voice-chosen-en")).inner_text()[:160])
    # Noor reads with the chosen voice
    p.locator(T("ask-noor")).click()
    visible(p, T("noor-panel"))
    n0 = len(spoken(p))
    p.locator('[data-testid="noor-panel"] [data-testid="noor-speaker"]').first.click()
    p.wait_for_timeout(1500)
    said = spoken(p)[n0:]
    out["noor_voice"] = said[0] if said else None
    w.step("l2_noor_reads_with_the_choice", bool(said) and said[0]["voice"] == CHOSEN[0], utterance=said[:1])
    p.keyboard.press("Escape")
    # the tour reads with it too
    n0 = len(spoken(p))
    p.locator(T("tour-take")).click()
    attached(p, T("tour-player"), 30_000)
    said: list[dict[str, Any]] = []
    for _ in range(60):                                  # the tour's script may take a while on a cold service
        p.wait_for_timeout(1000)
        said = [x for x in spoken(p)[n0:] if x.get("during_tour")]
        if said:
            break
    out["tour_voice"] = said[0] if said else None
    w.step("l2_tour_reads_with_the_choice", bool(said) and said[0]["voice"] == CHOSEN[0], utterance=said[:1])
    p.keyboard.press("Escape")
    p.wait_for_timeout(500)
    if p.locator(T("tour-player")).count():
        p.locator(T("tour-skip")).first.click()
    # leave nothing fixed: back to Settings -> Voice by clicks and clear the walk's choice
    open_voice_settings(p)
    p.locator(T("settings-voice-open")).click()
    visible(p, T("voice-clear-en"), 60_000)
    p.locator(T("voice-clear-en")).click()
    p.wait_for_timeout(1200)
    w.step("l2_choice_cleared", p.locator(T("voice-chosen-en")).get_attribute("data-chosen") == "false")
    return out


def walk_l9(w: Walk, ui: str) -> None:
    p = w.page
    p.goto(f"{ui}/deal-desk/DD-02", wait_until="domcontentloaded")
    visible(p, T("dealdesk-step-structure"), 180_000)
    p.locator(T("dealdesk-step-structure")).click()           # Stress is a header button from Structure on
    p.wait_for_selector(f'{T("dealdesk-stress-button")}:not([disabled])', timeout=180_000)
    p.locator(T("dealdesk-stress-button")).click()
    ok = visible(p, T("flow-stress-run"), 120_000)
    p.locator(T("flow-stress-run")).click()
    ok = ok and visible(p, T("flow-stress-matrix"), 240_000)
    w.step("l9_dd02_stress_run_on_screen", ok)
    p.locator(T("ask-noor")).click()
    visible(p, T("noor-input"))
    p.locator(T("noor-input")).fill("how is this failing on all stress scenario?")
    p.locator(T("noor-input")).press("Enter")
    ok = visible(p, T("noor-turn-here"), 240_000)
    url_after = p.url
    here = p.locator(T("noor-turn-here")).last
    text = here.inner_text() if ok else ""
    w.step("l9_answers_on_dd02_not_what_if", ok and "DD-02" in text and "/what-if" not in url_after and "EAD SAR" not in text,
           url=url_after.replace(ui, ""), first_lines=text[:300])
    ok = visible(p, f'{T("noor-here-fix")}[data-ready="true"]', 180_000)
    p.locator(T("noor-here-fix")).last.scroll_into_view_if_needed()
    w.step("l9_cheapest_fix", ok, fix=p.locator(T("noor-here-fix")).last.inner_text()[:300] if ok else "")
    p.locator(T("noor-here-action-scroll")).last.click()
    p.wait_for_timeout(1500)
    top = p.evaluate("() => { const e = document.querySelector('[data-testid=\"flow-stress-proof\"]'); return e ? e.getBoundingClientRect().top : null }")
    w.step("l9_open_stress_proof", top is not None and -50 < top < 700, top=top)
    # A book question leaves the page with the reason; "Answer here instead" brings it back to DD-02.
    p.locator(T("noor-input")).fill("Run a mild, moderate and severe scenario on the whole book")
    p.locator(T("noor-input")).press("Enter")
    ok = visible(p, T("noor-routed-why"), 180_000)
    p.wait_for_timeout(2500)
    w.step("l9_book_question_goes_to_what_if_with_why", ok and "/what-if" in p.url,
           url=p.url.replace(ui, ""), why=p.locator(T("noor-routed-why")).last.inner_text() if ok else "")
    if p.locator(T("noor-answer-here-instead")).count():
        p.locator(T("noor-answer-here-instead")).last.click()
        ok = visible(p, f'{T("noor-turn-here")} >> nth=1', 240_000) or p.locator(T("noor-turn-here")).count() >= 2
        p.wait_for_timeout(1500)
        w.step("l9_answer_here_instead", ok and "/deal-desk/DD-02" in p.url, url=p.url.replace(ui, ""))
    else:
        w.step("l9_answer_here_instead", False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="l1,l2,l9")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: dict[str, Any] = {"ui": a.ui, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for size in a.sizes.split(","):
            wd, ht = (int(x) for x in size.split("x"))
            ctx = b.new_context(viewport={"width": wd, "height": ht})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            ctx.add_init_script(FAKE_SPEECH)
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            folder = OUT / size
            folder.mkdir(parents=True, exist_ok=True)
            w = Walk(page, folder)
            print(f"== {size}")
            extra: dict[str, Any] = {}
            for name, fn in (("l1", walk_l1), ("l2", walk_l2), ("l9", walk_l9)):
                if name not in a.only.split(","):
                    continue
                try:
                    r = fn(w, a.ui)
                    if r:
                        extra[name] = r
                except Exception as e:  # noqa: BLE001 - one item's failure is recorded, the walk goes on
                    w.step(f"{name}_error", False, error=str(e)[:300])
            report["runs"].append({"size": size, "steps": w.steps, **extra})
            ctx.close()
        b.close()
    steps = [s for r in report["runs"] for s in r["steps"]]
    report["summary"] = {"steps": len(steps), "found": sum(s["found"] for s in steps),
                         "page_errors": sum(len(s["page_errors"]) for s in steps),
                         "console_errors": sum(len(s["console_errors"]) for s in steps),
                         "dev_overlay": sum(s["dev_overlay"] for s in steps),
                         "wider_than_viewport": sum(s["wider_than_viewport"] for s in steps)}
    (OUT / "walk.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report["summary"]))
    return 0 if report["summary"]["found"] == len(steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
