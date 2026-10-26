"""PLAN_R16 session v2: the click-through walk for regional voices in Settings -> Voice (Indian English, Arabic - Saudi,
Arabic - UAE (Gulf)), on the running services and the production UI build (`next start`).

    .venv/bin/python ops/r16_v2_walk.py [--ui http://127.0.0.1:5500] [--sizes 1600x1000,1280x800]

Steps: signed in and silent; Settings -> Voice by clicks; a table per accent under its language; Indian English shows
the Mac voices the browser exposes (stand-in: Rishi, Veena (Enhanced)) and the missing ones with how to get them; the
cloud rows are labelled and, with the cloud off (the default), cannot be played and say why; Listen Rishi (browser
speech, Rishi's voice); Use Rishi for English and Maged (ar-SA) for Arabic; then the cloud ON stand-in (the status
answered as if CP_TTS_CLOUD_KEY/REGION were set and the speak call for an azure: voice answered with a short WAV, since
no real key is used here): Listen Hamdan (ar-AE) posts his id and plays; Use Fatima for Arabic shows the cloud label in
the choice; choices cleared at the end.

Headless Chromium has no voices: a stand-in lists a Mac's usual voices plus en-IN Rishi and Veena (Enhanced).
Screens and walk.json in docs/v5/r16_review/v2/.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Route, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
sys.path.insert(0, str(V5))
from r11_ui_shots import mint  # noqa: E402
from r15_a_walk import FAKE_SPEECH, Walk, open_voice_settings, spoken, visible  # noqa: E402
from r16_v_walk import RECORD_PLAY, played  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "v2"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731
CLOUD_LABEL = "Cloud – text leaves the machine; demo with fictional data only"
FAKE = FAKE_SPEECH.replace('{name: "Google UK English Male"',
                           '{name: "Rishi", lang: "en-IN", localService: true, default: false},\n'
                           '    {name: "Veena (Enhanced)", lang: "en-IN", localService: true, default: false},\n'
                           '    {name: "Google UK English Male"')


def short_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * 4800)
    return buf.getvalue()


def rows(p: Page, region: str) -> list[dict[str, Any]]:
    return p.locator(f'{T(f"voice-region-{region}")} {T("voice-region-row")}').evaluate_all(
        "els => els.map(e => ({kind: e.dataset.kind, voice: e.dataset.voice, gender: e.dataset.gender, available: e.dataset.available,"
        " why: (e.querySelector('[data-testid=voice-region-why]')||{}).innerText || ''}))")


def row(p: Page, region: str, voice: str):
    return p.locator(f'{T(f"voice-region-{region}")} [data-testid="voice-region-row"][data-voice="{voice}"]')


def walk_v2(w: Walk, ui: str, speaks: list[dict[str, Any]]) -> None:
    p = w.page
    p.goto(f"{ui}/", wait_until="domcontentloaded")
    ok = visible(p, T("ask-noor"), 120_000)
    p.wait_for_timeout(4000)
    w.step("r1_signed_in_silent", ok and not speaks and not spoken(p) and not played(p), speak_calls=len(speaks))

    ok = open_voice_settings(p)
    p.locator(T("settings-voice-open")).click()
    ok = ok and visible(p, T("voice-sampler"), 60_000) and visible(p, T("voice-region-en-IN"), 30_000)
    p.wait_for_timeout(2500)
    placed = {r: p.locator(f'{T(f"voice-group-{g}")} {T(f"voice-region-{r}")}').count()
              for r, g in (("en-IN", "en"), ("ar-SA", "ar-gulf"), ("ar-AE", "ar-gulf"))}
    heads = [p.locator(T(f"voice-accent-main-{g}")).inner_text() for g in ("en", "ar-gulf")]
    w.step("r2_grouped_by_language_and_accent", ok and all(v == 1 for v in placed.values()), placed=placed, main=heads)

    p.locator(T("voice-region-en-IN")).scroll_into_view_if_needed()
    en = rows(p, "en-IN")
    macs = [(r["voice"], r["available"]) for r in en if r["kind"] == "mac"]
    cloud = [r for r in en if r["kind"] == "cloud"]
    labels = p.locator(f'{T("voice-region-en-IN")} {T("voice-cloud-label")}').all_inner_texts()
    off_note = p.locator(f'{T("voice-region-en-IN")} {T("voice-region-offline-note")}').inner_text()
    w.step("r3_indian_english_sources_and_why",
           ("Rishi", "true") in macs and ("Veena (Enhanced)", "true") in macs and ("Rishi (Enhanced)", "false") in macs
           and {c["gender"] for c in cloud} == {"male", "female"} and all(c["available"] == "false" and "off" in c["why"] for c in cloud)
           and labels and all(CLOUD_LABEL in t for t in labels) and "Piper" in off_note,
           mac=macs, cloud=[(c["voice"], c["available"]) for c in cloud], offline_note=off_note)

    sa, ae = rows(p, "ar-SA"), rows(p, "ar-AE")
    p.locator(T("voice-region-ar-SA")).scroll_into_view_if_needed()
    w.step("r4_arabic_saudi_and_uae", any(r["voice"] == "Maged" and r["available"] == "true" for r in sa)
           and {r["voice"] for r in sa if r["kind"] == "cloud"} == {"azure:ar-SA-HamedNeural", "azure:ar-SA-ZariyahNeural"}
           and {r["voice"] for r in ae if r["kind"] == "cloud"} == {"azure:ar-AE-HamdanNeural", "azure:ar-AE-FatimaNeural"}
           and not any(r["kind"] == "mac" for r in ae),
           saudi=[(r["kind"], r["voice"], r["available"]) for r in sa], uae=[(r["kind"], r["voice"], r["available"]) for r in ae])

    before = len(speaks)
    dis = row(p, "ar-AE", "azure:ar-AE-HamdanNeural").locator(T("voice-region-listen")).is_disabled()
    w.step("r5_cloud_off_cannot_play", dis and len(speaks) == before, listen_disabled=dis)

    n0 = len(spoken(p))
    p.locator(T("voice-region-en-IN")).scroll_into_view_if_needed()
    row(p, "en-IN", "Rishi").locator(T("voice-region-listen")).click()
    p.wait_for_timeout(800)
    new = spoken(p)[n0:]
    w.step("r6_listen_rishi", bool(new) and new[0]["voice"] == "Rishi", utterance=new[:1])

    row(p, "en-IN", "Rishi").locator(T("voice-region-use")).click()
    p.wait_for_timeout(1200)
    row(p, "ar-SA", "Maged").locator(T("voice-region-use")).click()
    p.wait_for_timeout(1200)
    lines = [p.locator(T(f"voice-chosen-{g}")).inner_text() for g in ("en", "ar-gulf")]
    w.step("r7_use_rishi_and_maged", "Rishi" in lines[0] and "Maged" in lines[1], chosen=lines)

    # Cloud ON stand-in: no real key is used in this container.
    wav = short_wav()

    def status(route: Route) -> None:
        r = route.fetch()
        b = r.json()
        b["engines"]["azure"] = True
        b["cloud"] = {**b.get("cloud", {}), "configured": True, "region": "uaenorth", "why": None}
        for v in b["voices"]:
            if v.get("where") == "cloud":
                v["installed"], v["why"] = True, None
        route.fulfill(response=r, json=b)

    def speak(route: Route) -> None:
        body = json.loads(route.request.post_data or "{}")
        if str(body.get("voice", "")).startswith("azure:"):
            route.fulfill(status=200, body=wav, headers={"Content-Type": "audio/wav", "X-Voice-Where": "cloud", "X-Voice-Cache": "miss"})
        else:
            route.continue_()

    p.route("**/api/v1/voice/status", status)
    p.route("**/api/v1/voice/speak", speak)
    p.reload(wait_until="domcontentloaded")
    ok = visible(p, T("voice-region-ar-AE"), 60_000)
    p.wait_for_timeout(2500)
    p.locator(T("voice-region-ar-AE")).scroll_into_view_if_needed()
    ae = rows(p, "ar-AE")
    p0 = len(played(p))
    b0 = len(speaks)
    row(p, "ar-AE", "azure:ar-AE-HamdanNeural").locator(T("voice-region-listen")).click()
    p.wait_for_timeout(1500)
    calls = speaks[b0:]
    w.step("r8_cloud_on_listen_hamdan", ok and all(r["available"] == "true" for r in ae if r["kind"] == "cloud")
           and calls and calls[0]["voice"] == "azure:ar-AE-HamdanNeural" and len(played(p)) > p0,
           calls=calls[:2], played=len(played(p)) - p0)

    row(p, "ar-AE", "azure:ar-AE-FatimaNeural").locator(T("voice-region-use")).click()
    p.wait_for_timeout(1500)
    line = p.locator(T("voice-chosen-ar-gulf")).inner_text()
    w.step("r9_use_fatima_cloud_labelled", "Fatima" in line and CLOUD_LABEL in line, chosen=line)

    p.unroute("**/api/v1/voice/status")
    p.unroute("**/api/v1/voice/speak")
    for g in ("en", "ar-gulf"):
        if p.locator(T(f"voice-clear-{g}")).count():
            p.locator(T(f"voice-clear-{g}")).click()
            p.wait_for_timeout(900)
    w.step("r10_choices_cleared",
           [p.locator(T(f"voice-chosen-{g}")).get_attribute("data-chosen") for g in ("en", "ar-gulf")] == ["false", "false"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1600x1000,1280x800")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: dict[str, Any] = {"ui": a.ui, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": [],
                              "note": "cloud ON steps use a stand-in status and WAV (no real key here); the backend's real "
                                      "Azure call is covered by tests/v5/voice/test_regional.py with a fake transport"}
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"],
                               **({"executable_path": exe} if os.path.exists(exe) else {}))
        for size in a.sizes.split(","):
            wd, ht = (int(x) for x in size.split("x"))
            ctx = b.new_context(viewport={"width": wd, "height": ht})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            ctx.add_init_script(FAKE)
            ctx.add_init_script(RECORD_PLAY)
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            speaks: list[dict[str, Any]] = []

            def on_request(req, speaks=speaks):
                if req.url.endswith("/api/v1/voice/speak") and req.method == "POST":
                    try:
                        body = json.loads(req.post_data or "{}")
                    except ValueError:
                        body = {}
                    speaks.append({"voice": body.get("voice"), "lang": body.get("lang"), "text": str(body.get("text", ""))[:100]})
            page.on("request", on_request)
            folder = OUT / size
            folder.mkdir(parents=True, exist_ok=True)
            w = Walk(page, folder)
            print(f"== {size}")
            try:
                walk_v2(w, a.ui, speaks)
            except Exception as e:  # noqa: BLE001
                w.step("v2_error", False, error=str(e)[:300])
            report["runs"].append({"size": size, "steps": w.steps, "speak_calls": speaks})
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
