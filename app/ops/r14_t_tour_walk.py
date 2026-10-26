"""PLAN_R14 session t (K36, K36a): the tour walk test on the running services (production UI build).

  .venv/bin/python ops/r14_t_tour_walk.py [--ui http://127.0.0.1:5500] [--runs en@1440x900,ar@1440x900,en@1280x800]

For each run: open the Brief, click "Take the tour" in the header (a click, not a URL: N6), switch to Arabic with the
tour's own language button for the Arabic runs, and let the tour play by itself (`?tour_speed=` shortens each line's
time; there is no voice in headless Chromium, so the tour runs on its captions). At every step the walker pauses the
tour, takes a screenshot, records the highlighted element, and presses Play again; the run passes when the tour
reaches its end with no page error and no console error. Also shots the header and checks (R15 L1) that nothing but the button starts the tour.

Writes docs/v5/r14_review/t/<run>/<nn>_<step>.png and docs/v5/r14_review/t/walk.json. A minted session cookie is
used (no password read or printed).
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

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "t"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
PLAYER = T("tour-player")
IGNORED_CONSOLE = ("Download the React DevTools", "favicon", "net::ERR_", "Failed to load resource")


def attr(page: Page, name: str) -> str:
    return page.locator(PLAYER).get_attribute(name) or ""


def play_tour(page: Page, ui: str, lang: str, folder: Path, speed: int) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    page.goto(f"{ui}/?tour_speed={speed}", wait_until="domcontentloaded")
    page.wait_for_selector(T("tour-take"), timeout=120_000)
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    page.wait_for_timeout(1500)
    page.locator(T("tour-take")).click()
    page.wait_for_selector(PLAYER, state="attached", timeout=30_000)
    if lang == "ar":
        page.wait_for_selector(f'{PLAYER}:not([data-n="0"])', state="attached", timeout=60_000)
        page.locator(T("tour-lang")).click()
        page.wait_for_selector(f'{PLAYER}[data-lang="ar"]', state="attached", timeout=10_000)
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    t0 = time.time()
    while time.time() - t0 < 900:
        status = attr(page, "data-status")
        if status in ("done", "error"):
            break
        key, busy = attr(page, "data-step"), attr(page, "data-busy")
        if key and busy == "false" and key not in seen and status == "playing":
            seen.add(key)
            idx = int(attr(page, "data-index") or 0)
            page.locator(T("tour-play")).click()          # pause on the step
            page.wait_for_timeout(700)                     # spotlight transition
            if key in ("ews", "whatif") and page.locator(f'{T("tour-sources")}:not([open])').count():
                page.locator(f'{T("tour-sources")} summary').click()   # the figures' sources, opened once
                page.wait_for_timeout(200)
            name = f"{idx + 1:02d}_{key}.png"
            page.screenshot(path=str(folder / name))
            cap = page.locator(T("tour-caption")).first.inner_text() if page.locator(T("tour-caption")).count() else ""
            src = page.locator(f'{T("tour-sources")} li').all_inner_texts() if page.locator(T("tour-sources")).count() else []
            steps.append({"n": idx + 1, "step": key, "target": attr(page, "data-target"), "caption": cap, "sources": src,
                          "url": page.url.replace(ui, ""), "shot": name,
                          "probe": page.evaluate(PROBE, None)})
            page.locator(T("tour-play")).click()          # play on (replays this line, then moves on)
            page.wait_for_timeout(200)
        page.wait_for_timeout(150)
    final = attr(page, "data-status")
    page.screenshot(path=str(folder / "99_done.png"))
    return {"status": final, "steps": steps, "skipped": [s for s in attr(page, "data-skipped").split(",") if s],
            "n": int(attr(page, "data-n") or 0), "seconds": round(time.time() - t0, 1)}


# A stand-in for the browser's speech (headless Chromium has no voices): the Mac's usual voices, female and male; every
# utterance is recorded (voice, rate, pitch, text) and ends after 60 ms, so the tour runs on its voice path.
FAKE_SPEECH = r"""
(() => {
  const voices = [
    {name: "Samantha", lang: "en-US", localService: true, default: true, voiceURI: "Samantha"},
    {name: "Daniel", lang: "en-GB", localService: true, default: false, voiceURI: "Daniel"},
    {name: "Kate", lang: "en-GB", localService: true, default: false, voiceURI: "Kate"},
    {name: "Laila", lang: "ar-SA", localService: true, default: false, voiceURI: "Laila"},
    {name: "Maged", lang: "ar-SA", localService: true, default: false, voiceURI: "Maged"},
  ];
  window.__spoken = [];
  const synth = {
    speaking: false, pending: false, paused: false,
    getVoices: () => voices,
    addEventListener: () => {}, removeEventListener: () => {},
    cancel() { this.speaking = false; },
    pause() {}, resume() {},
    speak(u) {
      window.__spoken.push({voice: u.voice && u.voice.name, rate: u.rate, pitch: u.pitch, lang: u.lang, text: u.text,
                            during_tour: !!document.querySelector('[data-testid="tour-player"]')});
      this.speaking = true;
      setTimeout(() => { this.speaking = false; u.onend && u.onend(new Event("end")); }, 60);
    },
  };
  Object.defineProperty(window, "speechSynthesis", {value: synth, configurable: true});
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
"""


def voice_run(page: Page, ui: str, lang: str) -> dict[str, Any]:
    """The tour on its voice path (speed 1): which voice read each line, at what rate and pitch."""
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("tour-take"), timeout=120_000)
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    page.wait_for_timeout(1000)
    page.locator(T("tour-take")).click()
    page.wait_for_selector(PLAYER, state="attached", timeout=30_000)
    if lang == "ar":
        page.wait_for_selector(f'{PLAYER}:not([data-n="0"])', state="attached", timeout=60_000)
        page.locator(T("tour-lang")).click()
    t0 = time.time()
    while time.time() - t0 < 600 and attr(page, "data-status") not in ("done", "error"):
        page.wait_for_timeout(500)
    allspoken = page.evaluate("window.__spoken")
    lines = page.evaluate("""async (lang) => {
        const r = await fetch(`http://127.0.0.1:8508/api/v1/tour/script?lang=${lang}`, {credentials: "include"});
        return (await r.json()).steps.map((s) => s.voice); }""", lang)
    spoken = [x for x in allspoken if x.get("text") in lines]          # the tour's own lines
    other = [x for x in allspoken if x.get("text") not in lines]       # anything else the page read (Noor's own voice)
    voices = sorted({str(x["voice"]) for x in spoken})
    return {"status": attr(page, "data-status"), "utterances": len(spoken), "lines": len(lines), "voices": voices,
            "rates": sorted({x["rate"] for x in spoken if x["rate"] is not None}),
            "pitches": sorted({x["pitch"] for x in spoken if x["pitch"] is not None}),
            "other_page_speech": [{"voice": x.get("voice"), "text": str(x.get("text"))[:80],
                                   "during_tour": x.get("during_tour")} for x in other][:5],
            "first": spoken[0]["text"][:120] if spoken else "", "seconds": round(time.time() - t0, 1)}


def header_shots(page: Page, ui: str, folder: Path) -> dict[str, Any]:
    """R15 L1: nothing starts the tour but the header button: not the first sign-in, not ?tour=1, not ?tour_prompt=1."""
    folder.mkdir(parents=True, exist_ok=True)
    page.goto(f"{ui}/?tour=1&tour_prompt=1", wait_until="domcontentloaded")
    page.wait_for_selector(T("tour-take"), timeout=120_000)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(folder / "00_header_no_auto_tour.png"))
    return {"take_button": page.locator(T("tour-take")).count(), "prompt": page.locator(T("tour-prompt")).count(),
            "player_without_click": page.locator(PLAYER).count(), "take_text": page.locator(T("tour-take")).inner_text()}


def run(ui: str, runs: list[tuple[str, int, int]], speed: int, voice: bool = True) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for lang, w, h in runs:
            tag = f"{lang}_{w}x{h}"
            ctx = b.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))  # noqa: B023
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" and not any(  # noqa: B023
                s in m.text for s in IGNORED_CONSOLE) else None)
            rec: dict[str, Any] = {"run": tag, "lang": lang, "size": f"{w}x{h}"}
            try:
                if lang == "en":
                    rec["header"] = header_shots(page, ui, OUT / tag)
                rec.update(play_tour(page, ui, lang, OUT / tag, speed))
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
                try:
                    page.screenshot(path=str(OUT / tag / "error.png"))
                except Exception:  # noqa: BLE001
                    pass
            rec["page_errors"] = errors
            rec["console_errors"] = console
            rec["passed"] = rec.get("status") == "done" and not errors and "error" not in rec
            report.append(rec)
            print(f"{tag}: {rec.get('status')} {len(rec.get('steps', []))} steps, skipped {rec.get('skipped')}, "
                  f"page errors {len(errors)}, console errors {len(console)}, {rec.get('seconds')}s", flush=True)
            (OUT / "walk.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
            ctx.close()
        if voice:
            for lang in ("en", "ar"):
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
                ctx.add_init_script(FAKE_SPEECH)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:300]))  # noqa: B023
                rec = {"run": f"voice_{lang}", "lang": lang}
                try:
                    rec.update(voice_run(page, ui, lang))
                except Exception as e:  # noqa: BLE001
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:300]}"
                want = "Maged" if lang == "ar" else "Daniel"
                rec["page_errors"] = errors
                rec["passed"] = (rec.get("status") == "done" and rec.get("voices") == [want] and rec.get("rates") == [0.92]
                                 and rec.get("pitches") == [0.9] and rec.get("utterances", 0) >= rec.get("lines", 99)
                                 and not any(o.get("during_tour") for o in rec.get("other_page_speech", []))
                                 and not errors)
                report.append(rec)
                print(f"voice_{lang}: {rec.get('status')} {rec.get('utterances')} lines read by {rec.get('voices')} "
                      f"rate {rec.get('rates')} pitch {rec.get('pitches')} {rec.get('seconds')}s", flush=True)
                (OUT / "voice.json").write_text(json.dumps([r for r in report if r["run"].startswith("voice_")], indent=1,
                                                           ensure_ascii=False, default=str))
                ctx.close()
        b.close()
    return 0 if all(r["passed"] for r in report) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--runs", default="en@1440x900,ar@1440x900,en@1280x800,ar@1280x800")
    ap.add_argument("--speed", type=int, default=6)
    ap.add_argument("--no-voice-check", action="store_true", help="skip the voice-path runs (stand-in speech)")
    a = ap.parse_args()
    rs = []
    for r in ([] if a.runs == "none" else a.runs.split(",")):
        lang, size = r.split("@")
        w, h = (int(x) for x in size.split("x"))
        rs.append((lang, w, h))
    sys.exit(run(a.ui, [] if a.runs == "none" else rs, a.speed, not a.no_voice_check))
