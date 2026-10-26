"""PLAN_R16 session v: the click-through walk for Noor's human-sounding voice (offline neural add-on), on the running
Deal Desk and Workspace services and the production UI build (`next start`).

    .venv/bin/python ops/r16_v_walk.py [--ui http://127.0.0.1:5500] [--sizes 1600x1000,1280x800] [--samples]

Steps: sign in and wait (nothing speaks, no audio is fetched); Settings -> Voice by clicks; the neural voices are
listed beside the browser's for English and Arabic; Listen to a neural English and the Arabic voice (a WAV from
/api/v1/voice/speak, played in the page); the same line again is not fetched twice; choose a neural voice per language;
Noor's speaker reads with it; with the add-on answering 503 (stand-in for "not installed") the speaker reads with the
browser's voice and says why; the choices are cleared at the end (the walk leaves nothing chosen).

Headless Chromium has no voices: a stand-in for the browser's speech lists a Mac's usual voices and records each
utterance. `HTMLMediaElement.play` is wrapped to record what is played (the real audio still plays). With `--samples`
the same sample line is saved as WAV per neural voice in docs/v5/r16_review/v/samples/ so Anne can listen anywhere.
Screens and walk.json in docs/v5/r16_review/v/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
sys.path.insert(0, str(V5))
from r11_ui_shots import mint  # noqa: E402
from r15_a_walk import FAKE_SPEECH, Walk, attached, open_voice_settings, spoken, visible  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "v"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731
DD = "http://127.0.0.1:8508"
EN, AR = "bm_george", "ar_JO-kareem-medium"
SAMPLE_EN = ("Good morning, Anne. Three names need your decision today. Total exposure is SAR 1.48 bn, up 12.5% on "
             "the quarter; the largest, Al Noor Trading, missed its DSCR covenant at 1.1x.")
SAMPLE_AR = "صباح الخير. ثلاثة عملاء يحتاجون قرارك اليوم. إجمالي التعرض ١٫٤٨ مليار ريال، بزيادة 12.5% خلال الربع."

RECORD_PLAY = r"""
(() => {
  window.__played = [];
  const orig = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    window.__played.push({src: String(this.src).slice(0, 60), at: Date.now()});
    return orig.call(this);
  };
})();
"""


def played(p: Page) -> list[dict[str, Any]]:
    return p.evaluate("() => window.__played || []")


def walk_v(w: Walk, ui: str, speaks: list[dict[str, Any]]) -> dict[str, Any]:
    p = w.page
    out: dict[str, Any] = {}
    p.goto(f"{ui}/", wait_until="domcontentloaded")
    ok = visible(p, T("ask-noor"), 120_000)
    p.wait_for_timeout(6000)
    w.step("v1_signed_in_silent", ok and not speaks and not spoken(p) and not played(p),
           speak_calls=len(speaks), utterances=len(spoken(p)), played=len(played(p)))

    ok = open_voice_settings(p)
    p.locator(T("settings-voice-open")).click()
    ok = ok and visible(p, T("voice-sampler"), 60_000) and visible(p, T("voice-neural-row"), 30_000)
    p.wait_for_timeout(2500)
    en_rows = p.locator(f'{T("voice-neural-en")} {T("voice-neural-row")}')
    ar_rows = p.locator(f'{T("voice-neural-ar-gulf")} {T("voice-neural-row")}')
    ids = en_rows.evaluate_all("els => els.map(e => e.dataset.voice)")
    genders = sorted(set(en_rows.evaluate_all("els => els.map(e => e.dataset.gender)")))
    avail = [p.locator(T(f"voice-neural-{g}")).get_attribute("data-available") for g in ("en", "ar-gulf")]
    want = {"am_michael", "am_adam", "bm_george", "bm_lewis"}
    w.step("v2_neural_beside_browser_voices", ok and want <= set(ids) and genders == ["female", "male"] and ar_rows.count() >= 1
           and avail == ["true", "true"] and p.locator(T("voice-side-by-side-en")).count() == 1,
           neural_en=len(ids), neural_ar=ar_rows.count(), first=ids[:6], genders=genders, available=avail,
           browser_rows=p.locator(T("voice-row")).count())
    p.locator(T("voice-group-en")).scroll_into_view_if_needed()
    w.step("v2b_side_by_side_english", True)

    # Listen: a neural English voice
    n0, m0 = len(speaks), len(played(p))
    row = p.locator(f'{T("voice-neural-row")}[data-voice="am_michael"]')
    row.locator(T("voice-neural-listen")).click()
    for _ in range(60):
        p.wait_for_timeout(500)
        if len(played(p)) > m0:
            break
    got = speaks[n0:]
    w.step("v3_listen_neural_english", bool(got) and got[0]["status"] == 200 and got[0]["type"] == "audio/wav"
           and got[0]["voice"] == "am_michael" and len(played(p)) > m0, call=got[:1])
    p.wait_for_timeout(1500)
    # the same line again: played from the page's cache, not fetched
    n1 = len(speaks)
    row.locator(T("voice-neural-listen")).click()   # stop (it may still be playing) or listen again
    p.wait_for_timeout(400)
    if "Stop" not in row.locator(T("voice-neural-listen")).inner_text():
        row.locator(T("voice-neural-listen")).click()
    p.wait_for_timeout(800)
    w.step("v3b_same_line_not_fetched_again", len(speaks) == n1, calls=len(speaks) - n1)
    p.locator(T("voice-neural-play-all-en")).scroll_into_view_if_needed()

    # Listen: the Arabic neural voice
    p.locator(T("voice-group-ar-gulf")).scroll_into_view_if_needed()
    n0, m0 = len(speaks), len(played(p))
    p.locator(f'{T("voice-neural-row")}[data-voice="{AR}"]').locator(T("voice-neural-listen")).click()
    for _ in range(60):
        p.wait_for_timeout(500)
        if len(played(p)) > m0:
            break
    got = [x for x in speaks[n0:] if x["voice"] == AR]   # an English chunk made ahead may still land first
    w.step("v4_listen_neural_arabic", bool(got) and got[0]["status"] == 200 and got[0]["voice"] == AR and len(played(p)) > m0,
           call=got[:1], sample=p.locator(T("voice-sample-ar-gulf")).inner_text()[:100])

    # Choose a neural voice per language
    p.locator(T("voice-group-en")).scroll_into_view_if_needed()
    p.locator(f'{T("voice-neural-row")}[data-voice="{EN}"]').locator(T("voice-neural-use")).click()
    visible(p, T("voice-msg"), 20_000)
    p.wait_for_timeout(600)
    p.locator(T("voice-group-ar-gulf")).scroll_into_view_if_needed()
    p.locator(f'{T("voice-neural-row")}[data-voice="{AR}"]').locator(T("voice-neural-use")).click()
    p.wait_for_timeout(1200)
    p.locator(T("voice-chosen")).scroll_into_view_if_needed()
    lines = [p.locator(T(f"voice-chosen-{g}")).inner_text() for g in ("en", "ar-gulf")]
    w.step("v5_neural_chosen_per_language", all("offline neural voice" in x for x in lines) and "George" in lines[0] and "Kareem" in lines[1],
           lines=[x[:160] for x in lines])

    # Noor's speaker reads with the chosen neural voice
    p.locator(T("ask-noor")).click()
    visible(p, T("noor-panel"))
    p.wait_for_timeout(2500)
    n0, m0, u0 = len(speaks), len(played(p)), len(spoken(p))
    p.locator(f'{T("noor-panel")} {T("noor-speaker")}').first.click()
    for _ in range(90):
        p.wait_for_timeout(500)
        if len(played(p)) > m0:
            break
    got = speaks[n0:]
    out["noor_call"] = got[:1]
    w.step("v6_noor_speaker_reads_neural", bool(got) and got[0]["voice"] == EN and got[0]["status"] == 200
           and len(played(p)) > m0 and len(spoken(p)) == u0, call=got[:1], browser_utterances=len(spoken(p)) - u0)
    p.wait_for_timeout(500)
    if p.locator(f'{T("noor-panel")} {T("noor-speaker")}').first.get_attribute("data-voice-state") == "speaking":
        p.locator(f'{T("noor-panel")} {T("noor-speaker")}').first.click()   # stop
    p.wait_for_timeout(500)

    # The add-on absent (503): the browser's voice reads, with a note
    def absent(route: Route) -> None:
        route.fulfill(status=503, content_type="application/json",
                      body=json.dumps({"available": False, "reason": "The English neural voice (Kokoro) is not installed on this computer."}))
    p.route("**/api/v1/voice/speak", absent)
    p.reload(wait_until="domcontentloaded")   # a fresh page: the WAVs it held are gone, so the line is fetched again
    visible(p, T("ask-noor"), 120_000)
    p.locator(T("ask-noor")).click()
    visible(p, T("noor-panel"))
    p.wait_for_timeout(2500)
    u0 = len(spoken(p))
    p.locator(f'{T("noor-panel")} {T("noor-speaker")}').first.click()
    p.wait_for_timeout(2500)
    said = spoken(p)[u0:]
    note = p.locator(T("noor-voice-choose")).inner_text() if p.locator(T("noor-voice-choose")).count() else ""
    w.step("v7_absent_add_on_falls_back_with_a_note", bool(said) and "not installed" in note,
           browser_utterance=said[:1], note=note[:200])
    p.unroute("**/api/v1/voice/speak")
    p.keyboard.press("Escape")

    # Clear the choices again (the walk leaves nothing chosen)
    p.goto(f"{ui}/settings/voice", wait_until="domcontentloaded")
    visible(p, T("voice-sampler"), 60_000)
    p.wait_for_timeout(1500)
    for g in ("en", "ar-gulf"):
        if p.locator(T(f"voice-clear-{g}")).count():
            p.locator(T(f"voice-clear-{g}")).click()
            p.wait_for_timeout(800)
    w.step("v8_choices_cleared", [p.locator(T(f"voice-chosen-{g}")).get_attribute("data-chosen") for g in ("en", "ar-gulf")] == ["false", "false"])
    return out


def samples() -> list[dict[str, Any]]:
    """The same line in every neural voice, saved as WAV for Anne (generated by the running service)."""
    folder = OUT / "samples"
    folder.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{DD}/api/v1/voice/voices", timeout=30) as r:
        voices = json.loads(r.read())["voices"]
    out = []
    for v in voices:
        text = SAMPLE_AR if v["group"] == "ar-gulf" else SAMPLE_EN
        req = urllib.request.Request(f"{DD}/api/v1/voice/speak", method="POST", headers={"Content-Type": "application/json"},
                                     data=json.dumps({"text": text, "voice": v["id"], "speed": 0.95}).encode())
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=300) as r:
            audio = r.read()
        (folder / f"{v['id']}.wav").write_bytes(audio)
        out.append({"voice": v["id"], "bytes": len(audio), "seconds": round(time.monotonic() - t0, 2)})
        print(f"  sample {v['id']}: {len(audio)} bytes")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1600x1000,1280x800")
    ap.add_argument("--samples", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: dict[str, Any] = {"ui": a.ui, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"],
                               **({"executable_path": exe} if os.path.exists(exe) else {}))
        for size in a.sizes.split(","):
            wd, ht = (int(x) for x in size.split("x"))
            ctx = b.new_context(viewport={"width": wd, "height": ht})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            ctx.add_init_script(FAKE_SPEECH)
            ctx.add_init_script(RECORD_PLAY)
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            speaks: list[dict[str, Any]] = []

            def on_response(resp, speaks=speaks):
                if resp.url.endswith("/api/v1/voice/speak") and resp.request.method == "POST":
                    try:
                        body = json.loads(resp.request.post_data or "{}")
                    except ValueError:
                        body = {}
                    speaks.append({"status": resp.status, "type": resp.headers.get("content-type", ""),
                                   "cache": resp.headers.get("x-voice-cache", ""), "voice": body.get("voice"),
                                   "speed": body.get("speed"), "text": str(body.get("text", ""))[:120]})
            page.on("response", on_response)
            folder = OUT / size
            folder.mkdir(parents=True, exist_ok=True)
            w = Walk(page, folder)
            print(f"== {size}")
            extra: dict[str, Any] = {}
            try:
                extra = walk_v(w, a.ui, speaks) or {}
            except Exception as e:  # noqa: BLE001
                w.step("v_error", False, error=str(e)[:300])
            report["runs"].append({"size": size, "steps": w.steps, "speak_calls": speaks, **extra})
            ctx.close()
        b.close()
    if a.samples:
        report["samples"] = samples()
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
