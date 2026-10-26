"""PLAN_R16 session m: the click-through walk for M1-M6 on the running services and the production UI build
(`next start`, V5_UI_MODE=prod).

    .venv/bin/python ops/r16_m_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only m1,m2,m3,m4,m5,m6]

Screens in docs/v5/r16_review/m/<size>/<nn>_<step>.png, docs/v5/r16_review/m/walk.json and a short report.md table
(every step: found or not, its checks, page errors, console errors, development overlay, document wider than the
viewport). A minted session cookie is used (no password is read or printed). Modules are reached by clicking the
sidebar / header (a URL only when a nav item is not on screen; the step records `via`). Headless Chromium has no
voices, so a stand-in for the browser's speech lists a Mac's usual voices and records every utterance in
`window.__spoken`; no voice is chosen by the walk (M1: nothing may speak without a chosen voice and a click).
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

from playwright.sync_api import Page, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
sys.path.insert(0, str(V5))
from r11_ui_shots import mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r16_review" / "m"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731
IGNORED_CONSOLE = ("favicon", "Download the React DevTools", "net::ERR_ABORTED", "Failed to load resource")
STEP_MS = 90_000          # no single wait in a step is longer than this
PLACEHOLDER_MAX = 60

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
                            during_tour: !!document.querySelector('[data-testid="tour-player"]'), path: location.pathname});
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
    def __init__(self, page: Page, folder: Path, ui: str):
        self.page, self.folder, self.ui, self.steps, self.n = page, folder, ui, [], 0
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
        try:
            geo = p.evaluate("() => ({doc: document.documentElement.scrollWidth, vw: window.innerWidth})")
            overlay = p.locator("nextjs-portal").count() > 0
        except Exception:  # noqa: BLE001
            geo, overlay = {"doc": 0, "vw": 0}, False
        rec = {"n": self.n, "step": name, "found": bool(found), "page_errors": list(self.errors), "console_errors": list(self.console),
               "dev_overlay": overlay, "wider_than_viewport": geo["doc"] > geo["vw"] + 1,
               "url": p.url.replace(self.ui, ""), "shot": str(shot.relative_to(V5)), **extra}
        self.errors.clear()
        self.console.clear()
        self.steps.append(rec)
        print(f"  {self.n:02d} {name}: {'found' if found else 'MISSING'} {json.dumps(extra, ensure_ascii=False)[:260]}", flush=True)


# ---------------------------------------------------------------- helpers

def spoken(page: Page) -> list[dict[str, Any]]:
    return page.evaluate("() => window.__spoken || []")


def visible(page: Page, sel: str, ms: int = 15_000) -> bool:
    try:
        page.wait_for_selector(sel, timeout=min(ms, STEP_MS), state="visible")
        return True
    except Exception:  # noqa: BLE001
        return False


def attached(page: Page, sel: str, ms: int = 15_000) -> bool:
    try:
        page.wait_for_selector(sel, timeout=min(ms, STEP_MS), state="attached")
        return True
    except Exception:  # noqa: BLE001
        return False


def wait_url(page: Page, pattern: str, ms: int = 60_000) -> bool:
    try:
        page.wait_for_url(re.compile(pattern), timeout=min(ms, STEP_MS))
        return True
    except Exception:  # noqa: BLE001
        return False


def nav(w: Walk, slug: str, landing: str, ms: int = 60_000) -> str:
    """Open a module by clicking its sidebar item; a URL only when the item is not on screen. Returns how."""
    p = w.page
    item = p.locator(T(f"nav-{slug}")).first
    href = "/" if slug == "home" else f"/{slug}"
    via = "click"
    try:
        item.wait_for(state="visible", timeout=8_000)
        item.click()
    except Exception:  # noqa: BLE001
        via = "url"
        p.goto(f"{w.ui}{href}", wait_until="domcontentloaded")
    visible(p, landing, ms)
    return via


def body_text(p: Page) -> str:
    try:
        return p.locator("main").first.inner_text(timeout=5_000)
    except Exception:  # noqa: BLE001
        return p.locator("body").inner_text()


def ask_box(p: Page, box: str, send: str, text: str) -> None:
    p.locator(T(box)).first.fill(text)
    btn = p.locator(T(send)).first
    if btn.count():
        btn.click()
    else:
        p.locator(T(box)).first.press("Enter")


def close_tour(p: Page) -> None:
    for _ in range(3):
        if not p.locator(T("tour-player")).count():
            return
        for tid in ("tour-close", "tour-skip"):
            loc = p.locator(T(tid)).first
            if loc.count() and loc.is_visible():
                loc.click()
                break
        else:
            p.keyboard.press("Escape")
        p.wait_for_timeout(800)


# ---------------------------------------------------------------- M1 voice

def walk_m1(w: Walk) -> dict[str, Any]:
    p = w.page
    out: dict[str, Any] = {}
    p.goto(f"{w.ui}/", wait_until="domcontentloaded")
    ok = visible(p, T("home-brief"), STEP_MS) or visible(p, T("tour-take"), 30_000)
    p.wait_for_timeout(3000)
    said = spoken(p)
    w.step("m1_home_no_auto_speech", ok and not said, utterances=len(said), first=said[:1])

    visible(p, T("noor-listen"), 60_000)
    sp = p.locator(f'{T("home-brief")} {T("noor-speaker")}').first
    if not sp.count():
        sp = p.locator(f'{T("noor-listen")}, {T("noor-speaker")}').first
    clicked = False
    if sp.count():
        sp.scroll_into_view_if_needed()
        sp.click()
        clicked = True
    note = visible(p, T("noor-voice-choose"), 10_000)
    p.wait_for_timeout(1200)
    said = spoken(p)
    text = p.locator(T("noor-voice-choose")).inner_text() if note else ""
    w.step("m1_speaker_click_silent_with_note", clicked and note and not said and "Choose a voice" in text,
           clicked=clicked, note=text[:120], utterances=len(said))
    if note:
        try:
            p.locator(f'{T("noor-voice-choose")} button[aria-label="Dismiss"]').click(timeout=3_000)
        except Exception:  # noqa: BLE001
            pass

    # Settings -> Voice by clicks: the user menu -> Settings -> Voice -> Open.
    visible(p, T("user-menu"), 30_000)
    p.locator(T("user-menu")).click()
    visible(p, T("menu-settings"))
    p.locator(T("menu-settings")).click()
    visible(p, T("settings-voice"), 60_000)
    p.locator(T("settings-voice-open")).click()
    ok = visible(p, T("voice-sampler"), 60_000) or visible(p, T("voice-row"), 30_000)
    p.wait_for_timeout(2000)
    rows = p.locator(T("voice-row"))
    ranked = rows.evaluate_all("els => els.map(e => [e.dataset.voice, e.dataset.quality].filter(Boolean).join(' · '))")
    chosen = [p.locator(T(f"voice-chosen-{g}")).get_attribute("data-chosen") for g in ("en",)
              if p.locator(T(f"voice-chosen-{g}")).count()]
    out["ranked_voices"] = ranked
    w.step("m1_voice_sampler_ranked", ok and len(ranked) > 0 and not spoken(p), ranked=ranked[:10], chosen=chosen,
           piper_note=p.locator(T("voice-piper-note")).count() > 0)

    # the tour: captions by default; two steps, nothing spoken
    n0 = len(spoken(p))
    nav(w, "home", T("tour-take"))
    visible(p, T("tour-take"), 60_000)
    p.locator(T("tour-take")).first.click()
    ok = attached(p, T("tour-player"), 30_000)
    idx = 0
    t0 = time.time()
    while time.time() - t0 < 45:
        p.wait_for_timeout(1000)
        try:
            idx = int(p.locator(T("tour-player")).get_attribute("data-index") or 0)
        except Exception:  # noqa: BLE001
            break
        if idx >= 2:
            break
    advanced = "auto"
    if idx < 2:     # captions mode may wait for the reader: step on with the Next control
        advanced = "next"
        for _ in range(2 - idx):
            nxt = p.locator(T("tour-next"))
            if nxt.count() and nxt.is_enabled():
                nxt.click()
                p.wait_for_timeout(2500)
        try:
            idx = int(p.locator(T("tour-player")).get_attribute("data-index") or 0)
        except Exception:  # noqa: BLE001
            pass
    said = spoken(p)[n0:]
    voice_btn = p.locator(T("tour-voice"))
    voice_on = voice_btn.get_attribute("aria-pressed") if voice_btn.count() else None
    w.step("m1_tour_two_steps_silent", ok and idx >= 2 and not said, index=idx, advanced=advanced, utterances=len(said),
           voice_toggle_pressed=voice_on, caption=(p.locator(T("tour-caption")).first.inner_text()[:120]
                                                   if p.locator(T("tour-caption")).count() else ""))
    close_tour(p)
    w.step("m1_tour_closed", p.locator(T("tour-player")).count() == 0 and not spoken(p), utterances=len(spoken(p)))
    return out


# ---------------------------------------------------------------- M2 EWS analyse

def walk_m2(w: Walk) -> dict[str, Any]:
    p = w.page
    via = nav(w, "early-warning", T("ews-workspace"))
    btn = p.locator('[data-testid^="ews-analyse-"]').first
    ok = attached(p, '[data-testid^="ews-analyse-"]', STEP_MS)
    key = (btn.get_attribute("data-testid") or "").removeprefix("ews-analyse-") if ok else ""
    w.step("m2_ews_cards", ok, via=via, first_key=key)
    if not ok:
        return {}
    btn.click()
    ok = visible(p, T("ews-segment-analysis"), STEP_MS)
    parts = {k: p.locator(T(t)).count() > 0 for k, t in (
        ("plain_words", "ews-analysis-plain-words"), ("headline", "ews-analysis-headline"), ("drivers", "ews-analysis-drivers"),
        ("ecl", "ews-analysis-ecl-true"), ("stage", "ews-analysis-stage"))}
    parts["rules"] = p.locator('[data-testid^="ews-analysis-rule-"]').count()
    parts["top_names"] = p.locator('[data-testid^="ews-analysis-name-"]').count()
    parts["actions"] = p.locator('[data-testid^="ews-analysis-action-"]').count()
    all_ok = ok and all(v for v in parts.values()) and "analysis=1" in p.url
    w.step("m2_segment_analysis", all_ok, key=key, parts=parts,
           title=p.locator(T("ews-analysis-title")).inner_text() if ok else "")
    if not ok:
        return {}
    analysis_url = p.url
    p.locator(T(f"ews-export-{key}")).first.click()
    ok = wait_url(p, r"/what-if/thread/", STEP_MS) and visible(p, T("whatif-cohort-analysis"), STEP_MS)
    p.wait_for_timeout(1500)
    geo = p.evaluate("""() => {
      const g = (id) => { const e = document.querySelector(`[data-testid="${id}"]`); if (!e) return null;
        const r = e.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), sw: e.scrollWidth, cw: e.clientWidth}; };
      return {title: g('whatif-thread-title'), header_title: g('whatif-header-title'), header: g('whatif-header')};
    }""")
    t, ht = geo.get("title") or {}, geo.get("header_title") or {}
    not_squeezed = bool(t) and t["w"] >= 240 and t["sw"] <= t["cw"] + 1 and (not ht or ht["sw"] <= ht["cw"] + 1)
    w.step("m2_cohort_thread_compact_analysis", ok and not_squeezed, geometry=geo,
           drivers=p.locator(T("whatif-cohort-analysis-drivers")).count() > 0,
           top=p.locator(T("whatif-cohort-analysis-top")).count() > 0)
    p.go_back()
    ok = visible(p, f'{T("ews-segment-analysis")}, [data-testid^="ews-analyse-"]', STEP_MS)
    w.step("m2_back_returns", ok and "/early-warning" in p.url, back_url=p.url.replace(w.ui, ""),
           same_as_analysis=p.url == analysis_url, analysis_shown=p.locator(T("ews-segment-analysis")).count() > 0)
    return {"key": key}


# ---------------------------------------------------------------- M3 placeholders

PLACES = [  # name, nav slug (or None), landing selector, input test id
    ("whatif", "what-if", "whatif-landing", "whatif-ask"),
    ("lenses", "lenses", "lenses-landing", "lenses-ask"),
    ("dealdesk", "deal-desk", "dealdesk-landing", "dealdesk-ask"),
    ("scorecard", "scorecard-validation", "sv-home", "sv-ask"),
    ("playbook", "playbook", "playbook-chat", "playbook-chat-input"),
    ("home_ask", "home", "cockpit-v4-question", "cockpit-v4-question"),
    ("ews", "early-warning", "ews-askbar-input", "ews-askbar-input"),
    ("b360", "borrower-360", "b360-askbar-input", "b360-askbar-input"),
]


def walk_m3(w: Walk) -> dict[str, Any]:
    p = w.page
    found: dict[str, Any] = {}
    for name, slug, landing, box in PLACES:
        via = nav(w, slug, T(landing) if name != "home_ask" else T("home-tabs"))
        if name == "home_ask":
            p.locator(T("home-tab-ask")).first.click()
        ok = visible(p, T(box), 60_000)
        ph = p.locator(T(box)).first.get_attribute("placeholder") if ok else None
        found[name] = {"placeholder": ph, "len": len(ph) if ph is not None else None, "via": via}
    # Noor's panel
    try:
        p.locator(T("ask-noor")).first.click()
        ok = visible(p, T("noor-input"), 30_000)
        ph = p.locator(T("noor-input")).get_attribute("placeholder") if ok else None
    except Exception:  # noqa: BLE001
        ph = None
    found["noor"] = {"placeholder": ph, "len": len(ph) if ph is not None else None, "via": "click"}
    bad = {k: v for k, v in found.items() if v["len"] is None or v["len"] > PLACEHOLDER_MAX}
    w.step("m3_placeholders", not bad, placeholders=found, over_or_missing=sorted(bad))
    p.keyboard.press("Escape")
    p.wait_for_timeout(400)
    return found


# ---------------------------------------------------------------- M4 facts first

def walk_m4(w: Walk) -> dict[str, Any]:
    p = w.page
    via = nav(w, "what-if", T("whatif-library"))
    if p.locator(T("whatif-book-corporate")).count() and p.locator(T("whatif-book-corporate")).get_attribute("aria-pressed") != "true":
        p.locator(T("whatif-book-corporate")).click()
        visible(p, T("whatif-library"), 60_000)
    item = p.locator(T("whatif-lib-std-corporate-construction"))
    if not item.count():
        item = p.locator('[data-testid^="whatif-lib-"]', has_text="Construction sector stress")
    attached(p, '[data-testid^="whatif-lib-std-"]', 60_000)
    found_item = item.count() > 0
    if found_item:
        item.first.click()
    ok = found_item and wait_url(p, r"/what-if/thread/", STEP_MS) and visible(p, T("whatif-context"), STEP_MS)
    visible(p, T("whatif-proposal"), 60_000)
    order = p.evaluate("""() => {
      const c = document.querySelector('[data-testid="whatif-context"]');
      const pr = document.querySelector('[data-testid="whatif-proposal"]');
      return {context: !!c, proposal: !!pr,
              context_first: !!c && !!pr && !!(c.compareDocumentPosition(pr) & Node.DOCUMENT_POSITION_FOLLOWING),
              heading: c ? (c.querySelector('[data-testid="whatif-context-plain"]')?.innerText || '').split('\\n')[0] : ''};
    }""")
    if ok:
        p.locator(T("whatif-context")).scroll_into_view_if_needed()
    w.step("m4_whatif_construction_context_first", ok and order["context_first"] and "construction" in (order["heading"] or "").lower(),
           via=via, order=order)

    via = nav(w, "scorecard-validation", T("sv-home"))
    ex = p.locator(T("sv-example"), has_text="Validate the SME scorecard")
    attached(p, T("sv-example"), 60_000)
    if not ex.count():
        ex = p.locator(T("sv-example"), has_text="SME")
    found_ex = ex.count() > 0
    if found_ex:
        ex.first.click()
    ok = found_ex and wait_url(p, r"/scorecard-validation/thread/", STEP_MS) and visible(p, T("sv-turn"), STEP_MS)
    visible(p, T("sv-plan"), 60_000)
    facts = p.evaluate("""() => {
      const turn = document.querySelector('[data-testid="sv-turn"]');
      if (!turn) return {};
      const t = turn.innerText; const plan = turn.querySelector('[data-testid="sv-plan"]');
      const planAt = plan ? t.indexOf(plan.innerText.slice(0, 40)) : -1;
      const gini = t.search(/Gini/i), psi = t.search(/PSI/);
      return {gini_at: gini, psi_at: psi, plan_at: planAt, first: t.slice(0, 200)};
    }""")
    facts_first = facts.get("gini_at", -1) >= 0 and facts.get("psi_at", -1) >= 0 and (
        facts.get("plan_at", -1) < 0 or facts["gini_at"] < facts["plan_at"])
    w.step("m4_scorecard_sme_facts_first", ok and facts_first, via=via, facts=facts)
    return {"whatif_order": order, "scorecard": facts}


# ---------------------------------------------------------------- M5 persona dashboards

def persona(w: Walk, label: str, request: str) -> tuple[list[str], str]:
    p = w.page
    nav(w, "lenses", T("lenses-landing"))
    ask_box(p, "lenses-ask", "lenses-build", request)
    ok = visible(p, T("lens-metric-plan"), STEP_MS)
    rows = p.locator('[data-testid^="lens-metric-plan-row-"]').count()
    plan_persona = p.locator(T("lens-metric-plan")).get_attribute("data-persona") if ok else None
    w.step(f"m5_{label}_metric_plan", ok and rows > 0, persona=plan_persona, metrics=rows,
           na=p.locator(T("lens-metric-plan-na")).count())
    if not ok:
        return [], ""
    p.locator(T("lens-metric-plan-build")).click()
    ok = wait_url(p, r"/lenses/[^/?]+$", STEP_MS) and visible(p, T("lens-tile-title"), STEP_MS)
    p.wait_for_timeout(4000)
    titles = p.locator(T("lens-tile-title")).all_inner_texts()
    types = p.locator('[data-testid^="lens-tile-"][data-tile]').evaluate_all("els => els.map(e => e.dataset.testid)")
    errors = p.locator(T("lens-tile-error")).all_inner_texts()
    lens_id = p.url.rstrip("/").split("/")[-1].split("?")[0]
    w.step(f"m5_{label}_dashboard", ok and len(titles) >= 3, lens=lens_id, tiles=titles, tile_types=types, tile_errors=errors[:5])
    return titles, lens_id


def walk_m5(w: Walk) -> dict[str, Any]:
    cro, cro_id = persona(w, "cro", "CRO dashboard")
    ana, ana_id = persona(w, "analyst", "Analyst dashboard")
    a, b = {t.strip().lower() for t in cro}, {t.strip().lower() for t in ana}
    overlap = len(a & b) / max(1, len(a | b))
    w.step("m5_cro_vs_analyst_differ", bool(a) and bool(b) and overlap < 0.3 and cro_id != ana_id,
           overlap=round(overlap, 3), shared=sorted(a & b), cro_lens=cro_id, analyst_lens=ana_id)
    return {"cro": cro, "analyst": ana, "overlap": overlap, "cro_lens": cro_id, "analyst_lens": ana_id}


# ---------------------------------------------------------------- M6 new question = new thread

M6_CASES = [  # name, nav slug, landing, box, send, url pattern, q1, q2
    ("whatif", "what-if", "whatif-landing", "whatif-ask", "whatif-ask-send", r"/what-if/thread/([^/?#]+)",
     "What is the ECL of the Construction sector?", "Which sectors have the most Stage 2 exposure?"),
    ("lenses", "lenses", "lenses-landing", "lenses-ask", "lenses-build", r"/lenses/([^/?#]+)$",
     "Show ECL by sector", "Show Stage 2 exposure by region"),
    ("dealdesk", "deal-desk", "dealdesk-landing", "dealdesk-ask", "dealdesk-ask-send", r"/deal-desk/thread/([^/?#]+)",
     "How much sector headroom is left?", "Which proposals breach a hard limit?"),
]


def walk_m6(w: Walk) -> dict[str, Any]:
    p = w.page
    out: dict[str, Any] = {}
    for name, slug, landing, box, send, pat, q1, q2 in M6_CASES:
        ids = []
        try:
            for q in (q1, q2):
                nav(w, slug, T(landing))
                visible(p, T(box), 60_000)
                ask_box(p, box, send, q)
                wait_url(p, pat, STEP_MS)
                m = re.search(pat, p.url.replace(w.ui, ""))
                ids.append(m.group(1) if m else None)
                p.wait_for_timeout(5000)    # let the thread render (and any carried-over guard show itself)
            # Q1 must not be a turn of thread B; suggestion chips (buttons) may legitimately offer the same question.
            text = p.evaluate("""() => { const c = document.body.cloneNode(true);
                c.querySelectorAll('button, nav, aside').forEach((b) => b.remove()); return c.innerText; }""")
            ok = all(ids) and ids[0] != ids[1] and q1 not in text
            w.step(f"m6_{name}_two_threads", ok, thread_a=ids[0], thread_b=ids[1], q1_on_b=q1 in text, q2_on_b=q2 in text)
        except Exception as e:  # noqa: BLE001
            w.step(f"m6_{name}_error", False, error=str(e)[:300], ids=ids)
        out[name] = ids
    return out


# ---------------------------------------------------------------- report

def write_report(report: dict[str, Any]) -> None:
    sizes = [r["size"] for r in report["runs"]]
    names: list[str] = []
    for r in report["runs"]:
        for s in r["steps"]:
            if s["step"] not in names:
                names.append(s["step"])
    by = {(r["size"], s["step"]): s for r in report["runs"] for s in r["steps"]}
    lines = ["# R16 m walk (M1-M6)", "", f"UI {report['ui']} · started {report['started']} · production build", "",
             "| step | " + " | ".join(sizes) + " |", "|---|" + "---|" * len(sizes)]
    for n in names:
        cells = []
        for sz in sizes:
            s = by.get((sz, n))
            if not s:
                cells.append("—")
                continue
            flag = "pass" if s["found"] else "**FAIL**"
            extras = []
            if s["page_errors"]:
                extras.append(f"{len(s['page_errors'])} page err")
            if s["console_errors"]:
                extras.append(f"{len(s['console_errors'])} console err")
            if s["dev_overlay"]:
                extras.append("overlay")
            if s["wider_than_viewport"]:
                extras.append("wide")
            cells.append(flag + (f" ({', '.join(extras)})" if extras else ""))
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    sm = report["summary"]
    lines += ["", f"Steps {sm['steps']}, found {sm['found']}, page errors {sm['page_errors']}, console errors {sm['console_errors']}, "
              f"dev overlay {sm['dev_overlay']}, wider than viewport {sm['wider_than_viewport']}.", ""]
    first = report["runs"][0] if report["runs"] else {}
    if first.get("m3"):
        lines += ["## Placeholders (M3)", "", "| box | chars | placeholder |", "|---|---|---|"]
        for k, v in first["m3"].items():
            lines.append(f"| {k} | {v['len']} | {v['placeholder']} |")
        lines.append("")
    if first.get("m5"):
        m5 = first["m5"]
        lines += ["## Persona dashboards (M5)", "", f"CRO: {', '.join(m5['cro'])}", "", f"Analyst: {', '.join(m5['analyst'])}", "",
                  f"Title overlap (Jaccard): {m5['overlap']:.2f}", ""]
    if first.get("m6"):
        lines += ["## Threads (M6)", ""] + [f"- {k}: {v}" for k, v in first["m6"].items()] + [""]
    (OUT / "report.md").write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="m1,m2,m3,m4,m5,m6")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    host = re.sub(r"^https?://", "", a.ui).split(":")[0].split("/")[0]
    report: dict[str, Any] = {"ui": a.ui, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}
    walks: list[tuple[str, Callable[[Walk], Any]]] = [("m1", walk_m1), ("m2", walk_m2), ("m3", walk_m3),
                                                      ("m4", walk_m4), ("m5", walk_m5), ("m6", walk_m6)]
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for size in a.sizes.split(","):
            wd, ht = (int(x) for x in size.split("x"))
            ctx = b.new_context(viewport={"width": wd, "height": ht})
            ctx.add_cookies([{"name": "cp_session", "value": token, "domain": host, "path": "/"}])
            ctx.add_init_script(FAKE_SPEECH)
            page = ctx.new_page()
            page.set_default_timeout(60_000)
            folder = OUT / size
            folder.mkdir(parents=True, exist_ok=True)
            w = Walk(page, folder, a.ui)
            print(f"== {size}", flush=True)
            extra: dict[str, Any] = {}
            for name, fn in walks:
                if name not in a.only.split(","):
                    continue
                try:
                    r = fn(w)
                    if r:
                        extra[name] = r
                except Exception as e:  # noqa: BLE001 - one item's failure is recorded, the walk goes on
                    w.step(f"{name}_error", False, error=str(e)[:300])
                    try:
                        page.keyboard.press("Escape")
                    except Exception:  # noqa: BLE001
                        pass
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
    write_report(report)
    print(json.dumps(report["summary"]))
    return 0 if report["summary"]["found"] == len(steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
