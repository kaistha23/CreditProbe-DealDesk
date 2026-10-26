"""PLAN_R16 session n: click-through walk of **Listen** on every answer in every module, on the production build.

  .venv/bin/python ops/r16_n_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900] [--only dd,wi,...] [--voice neural|browser]

Each step reaches an answer by clicking from the module's landing (the navigation of session t's walk,
`ops/r16_t_walk.py`), then clicks Listen on the answer's bar and records: the narration written for that answer
(`data-narration`), whether it names a number and, when a chart is on screen, whether it points at it; the line on
screen while it plays and the element pulsing (`.cp-narrate-pulse`: a bar, slice or table row); a second click stops.
Screens and walk.json go to docs/v5/r16_review/n/.

The voice: `--voice neural` chooses the offline neural voice (R16 v; needs the add-on: ops/r16_install_tts.sh),
`--voice browser` a stand-in browser voice (headless Chromium has none: a stub `speechSynthesis` that "speaks" for the
time the words take, so the playback, the pulse and the stop are walked without sound).
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

import r16_t_walk as tw  # noqa: E402
from r11_ui_shots import mint  # noqa: E402
from r14_u_walkthrough import idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "n"
T = tw.T
LONG = tw.LONG
NUMBER = re.compile(r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|[a-z]+teen|twenty|thirty|forty|fifty|"
                    r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion|percent)\b|\d", re.I)

STUB_VOICE = """
(() => {
  const voice = { name: 'Walk Stand-in (en-US)', lang: 'en-US', default: true, localService: true, voiceURI: 'walk-en' };
  const ar = { name: 'Walk Stand-in (ar-SA)', lang: 'ar-SA', default: false, localService: true, voiceURI: 'walk-ar' };
  let timer = null, cur = null;
  const synth = {
    speaking: false, pending: false, paused: false, onvoiceschanged: null,
    getVoices: () => [voice, ar],
    speak(u) { cur = u; synth.speaking = true; window.__spoken = (window.__spoken || []).concat([u.text]);
      setTimeout(() => u.onstart && u.onstart(), 10);
      timer = setTimeout(() => { synth.speaking = false; cur = null; u.onend && u.onend(); }, Math.max(700, u.text.split(/\\s+/).length * 140)); },
    cancel() { if (timer) clearTimeout(timer); timer = null; synth.speaking = false; const u = cur; cur = null; if (u && u.onerror) u.onerror(); },
    pause() {}, resume() {}, addEventListener() {}, removeEventListener() {},
  };
  Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
  if (!window.SpeechSynthesisUtterance) window.SpeechSynthesisUtterance = function (t) { this.text = t; };
  const chosen = { en: { name: voice.name, lang: voice.lang, rate: 1, pitch: 1 }, 'ar-gulf': { name: ar.name, lang: ar.lang, rate: 1, pitch: 1 } };
  try { localStorage.setItem('cp.voice.chosen', JSON.stringify(chosen)); } catch (e) {}
})();
"""

NEURAL_VOICE = """
(() => {
  const chosen = { en: { name: 'am_michael', lang: 'en-US', rate: 1, pitch: 1, engine: 'neural', label: 'Michael' },
                   'ar-gulf': { name: 'ar_JO-kareem-medium', lang: 'ar-JO', rate: 1, pitch: 1, engine: 'neural', label: 'Kareem' } };
  try { localStorage.setItem('cp.voice.chosen', JSON.stringify(chosen)); } catch (e) {}
})();
"""

PULSE_PROBE = """
() => { const el = document.querySelector('.cp-narrate-pulse');
  if (!el) return null;
  const tag = el.tagName.toLowerCase(), cls = String(el.getAttribute('class') || '');
  const row = el.closest('tr');
  return { tag, kind: row ? 'row' : el.closest('.js-plotly-plot') ? (cls.includes('point') ? 'bar' : cls.includes('slice') ? 'slice' : tag === 'g' ? 'trace' : 'chart')
                                                                  : 'chart', text: (row ? row.innerText : '').replace(/\\s+/g, ' ').slice(0, 120) }; }
"""


def listen(page: Page, ctx: dict, key: str, prefix: str = "thread-actions") -> dict:
    """Listen on the last answer's bar: narration, the pulse while it plays, a second click stops."""
    bar = tw.last_bar(page, prefix)
    bar.scroll_into_view_if_needed()
    btn = bar.locator(T(f"{prefix}-listen"))
    out: dict[str, Any] = {"listen": bool(btn.count())}
    if not btn.count():
        return out
    answer_has_chart = page.evaluate(
        """(p) => { const bars = document.querySelectorAll(`[data-thread-actions][data-testid="${p}"]`); const bar = bars[bars.length - 1];
                    let el = bar; for (let i = 0; i < 6 && el; i += 1) { el = el.parentElement; if (el && el.querySelector('.js-plotly-plot, table')) break; }
                    return { chart: !!(el && el.querySelector('.js-plotly-plot')), table: !!(el && el.querySelector('table')) }; }""", prefix)
    btn.click()
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"{prefix}-listen\"][data-narration]').length > 0", timeout=20_000)
    narr = btn.get_attribute("data-narration") or ""
    out["narration"] = narr
    out["names_number"] = bool(NUMBER.search(narr))
    out["points_to_visual"] = bool(re.search(r"\b(chart|waterfall|row of the table)\b|الرسم|الجدول", narr))
    out.update({f"answer_{k}": v for k, v in answer_has_chart.items()})
    seen: list[Any] = []
    lines: list[str] = []
    state_playing = False
    t0 = time.time()
    while time.time() - t0 < 25:
        st = btn.get_attribute("data-state")
        state_playing = state_playing or st == "playing"
        ln = bar.locator(T(f"{prefix}-listen-line"))
        if ln.count():
            t = ln.first.inner_text()
            if t and (not lines or lines[-1] != t):
                lines.append(t)
        p = page.evaluate(PULSE_PROBE)
        if p and p not in seen:
            seen.append(p)
            tw.snap(page, ctx, f"{key}_listen_pulse")
        if st == "idle" and state_playing:
            break
        if len(lines) >= 3 and state_playing and not out.get("stopped_checked"):
            # the second click stops
            tw.snap(page, ctx, f"{key}_listen_playing")
            btn.click()
            page.wait_for_timeout(400)
            out["stopped_checked"] = True
            out["stopped"] = btn.get_attribute("data-state") == "idle" and not page.locator(".cp-narrate-pulse").count()
            break
        page.wait_for_timeout(150)
    out["played"] = state_playing
    out["lines_seen"] = lines[:6]
    out["pulsed"] = seen[:4]
    note = bar.locator(T(f"{prefix}-listen-note"))
    out["note"] = note.first.inner_text() if note.count() else ""
    if not out.get("stopped_checked"):
        tw.snap(page, ctx, f"{key}_listen_playing")
    return out


def choose_voice(page: Page, ui: str, ctx: dict, voice: str) -> dict:
    """Settings -> Voice: press "Use for English" / "Use for Arabic" on the first voice (neural table or browser table)."""
    page.goto(f"{ui}/settings/voice", wait_until="domcontentloaded")
    page.wait_for_selector(T("voice-chosen"), timeout=LONG)
    idle(page, 1500)
    out: dict[str, Any] = {}
    for g in ("en", "ar-gulf"):
        if voice == "neural":
            page.wait_for_selector(f'{T(f"voice-neural-{g}")}[data-available="true"]', timeout=60_000)
            row = page.locator(f'{T(f"voice-neural-table-{g}")} {T("voice-neural-use")}').first
        else:
            row = page.locator(f'{T(f"voice-table-{g}")} {T("voice-use")}').first
        if row.count() and row.is_enabled():
            row.click()
            page.wait_for_timeout(1200)
        out[g] = page.locator(T(f"voice-chosen-{g}")).first.inner_text()[:160]
    tw.snap(page, ctx, "voice_settings")
    return out


# ---------------------------------------------------------------- the answers (navigation from session t's walk, minus its Word/Share checks)
def go_dd(page: Page, ui: str, q: str = "which proposals breach a hard limit") -> None:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("dealdesk-home")} textarea').first
    box.click(); box.fill(q); box.press("Enter")
    page.wait_for_selector(T("dealdesk-desk-thread"), timeout=LONG)
    tw.wait_answers(page, '[data-testid="dealdesk-desk-turn"] [data-thread-actions]', 1)


def s_dd(page: Page, ui: str, ctx: dict) -> dict:
    go_dd(page, ui)
    return listen(page, ctx, "dd")


def s_dd_chart(page: Page, ui: str, ctx: dict) -> dict:
    go_dd(page, ui, "show me the pipeline by sector")
    return listen(page, ctx, "dd_chart")


def s_wi(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(T("whatif-home"), timeout=LONG)
    idle(page, 800)
    box = page.locator(f'{T("whatif-home")} textarea').first
    box.click(); box.fill("what is the ECL of the construction sector?"); box.press("Enter")
    page.wait_for_selector(T("whatif-thread"), timeout=LONG)
    tw.wait_answers(page, '[data-testid="whatif-turn"] [data-thread-actions]', 1)
    idle(page, 1500)
    return listen(page, ctx, "wi")


def s_ln(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/lenses", wait_until="domcontentloaded")
    page.wait_for_selector(T("lenses-home"), timeout=LONG)
    idle(page, 800)
    page.locator(f'{T("lenses-featured-grid")} button').first.click()
    page.wait_for_selector(T("lens-assistant"), timeout=LONG)
    idle(page, 1500)
    box = page.locator(T("lens-assistant-composer")).last
    box.click(); box.fill("which sector has the highest Stage 2 share?"); box.press("Enter")
    tw.wait_answers(page, '[data-testid="lens-assistant"] [data-thread-actions]', 1)
    return listen(page, ctx, "ln")


def s_sv(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/scorecard-validation", wait_until="domcontentloaded")
    page.wait_for_selector(T("sv-ask"), timeout=LONG)
    idle(page, 800)
    page.locator(T("sv-ask")).fill("Validate the SME scorecard")
    page.locator(T("sv-ask-send")).click()
    page.wait_for_selector(T("sv-thread"), timeout=LONG)
    tw.wait_answers(page, '[data-testid="sv-turn"] [data-thread-actions]', 1)
    idle(page, 1500)
    return listen(page, ctx, "sv")


def s_ews(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/early-warning", wait_until="domcontentloaded")
    page.wait_for_selector(T("ews-level-summary"), timeout=LONG)
    idle(page, 1500)
    return listen(page, ctx, "ews", prefix="ews-level-actions")


def s_agent(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("ews-triage-agent")).first.click()
    page.wait_for_selector(T("agent-run-drawer"), timeout=LONG)
    page.wait_for_selector(T("agent-actions"), timeout=LONG)
    idle(page, 800)
    out = listen(page, ctx, "agent", prefix="agent-actions")
    page.keyboard.press("Escape")
    return out


def s_b360(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/borrower-360", wait_until="domcontentloaded")
    page.wait_for_selector("table tbody tr", timeout=LONG)
    idle(page, 800)
    cell = page.locator("table tbody tr").first.locator("a, button").first
    (cell if cell.count() else page.locator("table tbody tr td").first).click()
    page.wait_for_selector(T("b360-actions"), timeout=LONG)
    idle(page, 1500)
    return listen(page, ctx, "b360", prefix="b360-actions")


def s_noor(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 600)
    if not page.locator(T("noor-chip-brief")).count():
        page.get_by_role("button", name="Ask Noor").first.click()
    page.wait_for_selector(T("noor-chip-brief"), timeout=60_000)
    page.locator(T("noor-new-thread")).click()
    page.locator(T("noor-chip-brief")).click()
    tw.wait_answers(page, '[data-testid="noor-thread"] [data-thread-actions]', 1, 120_000)
    return listen(page, ctx, "noor")


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
    return listen(page, ctx, "intel", prefix="intel-actions")


def s_pb(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/playbook", wait_until="domcontentloaded")
    page.wait_for_selector(T("playbook-chat-input"), timeout=LONG)
    idle(page, 800)
    page.locator(T("playbook-chat-input")).fill("What is the corporate book's ECL this quarter?")
    page.locator(T("playbook-chat-send")).click()
    page.wait_for_selector(T("playbook-start-thread"), timeout=LONG)
    tw.wait_answers(page, '[data-testid="playbook-chat-reply"] [data-thread-actions]', 1)
    return listen(page, ctx, "pb")


def s_cockpit(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    idle(page, 1000)
    if not page.locator(T("cockpit-v4-question")).count():
        page.locator(T("home-tab-ask")).click()
    page.locator(T("cockpit-v4-question")).fill("What is the Stage 2 exposure by sector?")
    page.locator(T("cockpit-v4-ask")).click()
    page.wait_for_selector('[data-testid="cockpit-thread-actions"]', timeout=120_000)
    idle(page, 2000)
    return listen(page, ctx, "cockpit", prefix="cockpit-thread-actions")


STEPS: list[tuple[str, str, Callable[[Page, str, dict], dict]]] = [
    ("dd_01", "Deal Desk thread answer", s_dd),
    ("dd_02_chart", "Deal Desk answer with a chart", s_dd_chart),
    ("wi_01", "What-If answer (charts)", s_wi),
    ("ln_01", "Lenses assistant answer", s_ln),
    ("sv_01", "Scorecard answer", s_sv),
    ("ews_01", "Early Warning level summary", s_ews),
    ("ews_02_agent", "Agent result (triage)", s_agent),
    ("b360_01", "Borrower 360 panel", s_b360),
    ("noor_01", "Noor panel brief", s_noor),
    ("intel_01", "Intelligence panel", s_intel),
    ("pb_01", "Playbook answer", s_pb),
    ("cockpit_01", "Cockpit Ask answer", s_cockpit),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str], voice: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tw.OUT = OUT
    token = mint()
    report: list[dict] = []
    path = OUT / "walk.json"
    if path.exists() and only:
        report = [r for r in json.loads(path.read_text()) if not any(r["step"].startswith(o) for o in only)]
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(args=["--disable-dev-shm-usage"], **({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            bctx.add_init_script(NEURAL_VOICE if voice == "neural" else STUB_VOICE)
            page = bctx.new_page()
            page.set_default_timeout(90_000)
            ctx: dict[str, Any] = {"tag": tag}
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            try:
                print("voice chosen:", json.dumps(choose_voice(page, ui, ctx, voice), ensure_ascii=False), flush=True)
            except Exception as e:  # noqa: BLE001
                print("voice not chosen:", str(e)[:200], flush=True)
            for sid, items, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only):
                    continue
                errors.clear(); console.clear()
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "items": items, "size": tag, "voice": voice}
                try:
                    rec["checks"] = fn(page, ui, ctx)
                    c = rec["checks"]
                    rec["found"] = bool(c.get("listen"))
                    rec["ok"] = bool(c.get("listen") and c.get("names_number") and c.get("played")
                                     and (c.get("points_to_visual") or not (c.get("answer_chart") or c.get("answer_table"))))
                except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
                    rec["found"] = False
                    rec["ok"] = False
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                rec["seconds"] = round(time.time() - t0, 1)
                try:
                    page.screenshot(path=str(OUT / f"{sid}_{tag}.png"))
                except Exception:  # noqa: BLE001
                    pass
                rec["page_errors"] = list(errors)
                rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                rec["clean"] = not rec["page_errors"] and not rec["console_errors"]
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['ok'] else 'MISS ' + rec.get('error', '')} {'clean' if rec['clean'] else 'ERRORS'} {rec['seconds']}s "
                      f"{json.dumps(rec.get('checks'), default=str, ensure_ascii=False)[:700]}", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
            bctx.close()
        b.close()
    ok = [r for r in report if r.get("ok")]
    print(f"WALK {len(ok)}/{len(report)} ok; {sum(1 for r in report if not r['clean'])} with errors")
    return 0 if len(ok) == len(report) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900")
    ap.add_argument("--only", default="")
    ap.add_argument("--voice", default="browser", choices=["browser", "neural"])
    a = ap.parse_args()
    sizes = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sizes, {o for o in a.only.split(",") if o}, a.voice))
