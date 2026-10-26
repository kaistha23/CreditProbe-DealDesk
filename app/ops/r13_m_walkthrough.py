"""PLAN_R13 Session M: the UAT walk-through on the running services (production UI build), at 1440x900 and 1280x800.

  .venv/bin/python ops/r13_m_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Covers every J item of docs/v5/R12_FEEDBACK.md and every backlog idea of docs/v5/R14_BACKLOG_CCO_IDEAS.md built in R13.
Writes docs/v5/r13_review/m/<step>_<size>.png and docs/v5/r13_review/m/walkthrough.json (found / missing per step,
page errors, a sideways-scroll probe and the text checks each step records).

The login step signs in through the login form as a temporary fictional user created for the run with a random
password (never printed) and removed at the end; every other step uses a minted session (no password read).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r13_review" / "m"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
WALKER = "uat.walker"


def idle(page: Page, ms: int = 800, timeout: int = 45_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001 - a long poll keeps the network busy
        pass
    page.wait_for_timeout(ms)


def settle(page: Page, scope: str, timeout: int = 120_000) -> None:
    """Wait until no spinner / loading line is left inside `scope`."""
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        busy = (page.locator(f"{scope} .animate-spin").count() + page.locator(f"{scope} [aria-busy='true']").count()
                + page.locator(f"{scope} .animate-pulse").count())
        if not busy:
            break
        page.wait_for_timeout(800)
    page.wait_for_timeout(600)


def ask_home(page: Page, ui: str, q: str) -> None:
    page.goto(f"{ui}/?tab=ask", wait_until="domcontentloaded")
    page.wait_for_selector(T("home-ask"), timeout=120_000)
    page.locator(T("cockpit-v4-question")).fill(q)
    page.locator(T("cockpit-v4-question")).press("Enter")


# ---------------------------------------------------------------- the steps: (id, items, function) -> checks
Step = tuple[str, str, Callable[[Page, str, dict], dict]]


def s_login(page: Page, ui: str, ctx: dict) -> dict:
    page.context.clear_cookies()
    page.goto(f"{ui}/login", wait_until="domcontentloaded")
    page.wait_for_selector(T("login-username"), timeout=60_000)
    idle(page, 1500)   # hydration: a value typed before React takes over is reset
    page.locator(T("login-username")).fill(WALKER)
    page.locator(T("login-password")).fill(ctx["password"])
    page.locator(T("login-submit")).click()
    page.wait_for_selector(T("home-tabs"), timeout=120_000)
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page, 1200)
    out = {"landing_tab": page.locator(T("home-tabs")).get_attribute("data-tab"), "url": page.url}
    page.context.add_cookies([{"name": "cp_session", "value": ctx["token"], "domain": "127.0.0.1", "path": "/"}])
    return out


def s_brief(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("noor-home-brief"), timeout=120_000)
    idle(page, 1000)
    return {"tab": page.locator(T("home-tabs")).get_attribute("data-tab"),
            "headline": page.locator(T("noor-headline")).first.inner_text()[:160] if page.locator(T("noor-headline")).count() else "",
            "lines": page.locator(f'{T("noor-home-brief-lines")} > li').count(),
            "requires_attention_on_page": page.locator("text=Requires attention").count()}


def s_ask(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/", wait_until="domcontentloaded")
    page.wait_for_selector(T("home-tabs"), timeout=120_000)
    page.locator(T("home-tab-ask")).click()
    page.wait_for_selector(T("home-ask"), timeout=60_000)
    idle(page, 800)
    return {"title": page.locator(T("home-ask-title")).inner_text(),
            "placeholder": page.locator(T("cockpit-v4-question")).get_attribute("placeholder"),
            "starters": page.locator(T("cockpit-v4-prompt")).all_inner_texts()}


def intel_answer(key: str, q: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        ask_home(page, ui, q)
        sel = f'{T("intel-answer")}[data-intel="{key}"]'
        page.wait_for_selector(sel, timeout=60_000)
        idle(page, 1500, 90_000)
        settle(page, sel, 150_000)
        page.locator(sel).scroll_into_view_if_needed()
        return {"engine": page.locator(T("intel-answer-title")).inner_text(),
                "text": page.locator(sel).inner_text()[:600]}
    return f


def s_noor_panel(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("ask-noor"), timeout=120_000)
    page.locator(T("ask-noor")).click()
    page.wait_for_selector(T("noor-panel"), timeout=60_000)
    idle(page, 1500)
    speaker = page.locator(T("noor-speaker"))
    out = {"speaker_present": speaker.count(), "voice_state_before": speaker.first.get_attribute("data-voice-state") if speaker.count() else None}
    if speaker.count():
        speaker.first.click()
        page.wait_for_timeout(800)
        out["voice_state_after_click"] = speaker.first.get_attribute("data-voice-state")
        out["voice_note"] = page.locator(T("noor-voice-problem")).first.inner_text() if page.locator(T("noor-voice-problem")).count() else ""
    return out


def s_noor_routes(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/lenses", wait_until="domcontentloaded")
    page.wait_for_selector(T("ask-noor"), timeout=120_000)
    page.locator(T("ask-noor")).click()
    page.wait_for_selector(T("noor-input"), timeout=60_000)
    page.locator(T("noor-input")).fill("Who should I call today?")
    page.locator(T("noor-input")).press("Enter")
    page.wait_for_selector(T("intel-host"), timeout=90_000)
    idle(page, 1500, 90_000)
    settle(page, T("intel-host"))
    return {"url": page.url, "host": page.locator(T("intel-answer-title")).inner_text()}


def landing(path: str, sel: str, module: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(ui + path, wait_until="domcontentloaded")
        page.wait_for_selector(sel, timeout=120_000)
        idle(page, 1200)
        return {"noor_module_strips": page.locator('[data-testid^="noor-module-brief"]').count(),
                "chat": page.locator(sel).count(), "module": module}
    return f


def s_dd_landing(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-cards"), timeout=120_000)
    idle(page, 1500)
    counts = {}
    for el in page.locator('[data-testid^="dealdesk-card-"][data-testid$="-count"]').all():
        counts[el.get_attribute("data-testid")] = el.inner_text()
    return {"counters": counts, "noor_module_strips": page.locator('[data-testid^="noor-module-brief"]').count(),
            "header_buttons": page.locator(T("dealdesk-header-actions")).inner_text().replace("\n", " · ") if page.locator(T("dealdesk-header-actions")).count() else ""}


def s_book(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-tab-book"), timeout=120_000)
    page.locator(T("dealdesk-tab-book")).click()
    page.wait_for_selector(T("portfolio-tools-book-button"), timeout=120_000)
    idle(page, 1500)
    page.locator(T("portfolio-tools-book-button")).click()
    page.wait_for_timeout(500)
    return {"tools": page.locator('[data-testid^="portfolio-tool-"]').all_inner_texts()}


def s_renewals(page: Page, ui: str, ctx: dict) -> dict:
    s_book(page, ui, ctx)
    page.locator(T("portfolio-tool-renewals")).click()
    idle(page, 2500, 120_000)
    settle(page, "main")
    return {"text": page.locator("main").inner_text()[:500]}


def deal(pid: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(f"{ui}/deal-desk/{pid}", wait_until="domcontentloaded")
        page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
        idle(page, 1500, 90_000)
        page.locator(T("dealdesk-more-button")).click()
        page.wait_for_selector(T("dealdesk-more-menu"), timeout=10_000)
        return {"menu": page.locator(T("dealdesk-more-menu")).inner_text().split("\n")}
    return f


def deal_intel(pid: str, key: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(f"{ui}/deal-desk/{pid}", wait_until="domcontentloaded")
        page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
        idle(page, 800, 60_000)
        page.locator(T("dealdesk-more-button")).click()
        page.locator(T(f"dealdesk-intel-{key}")).click()
        dlg = T(f"dealdesk-intel-{key}-dialog")
        page.wait_for_selector(dlg, timeout=30_000)
        idle(page, 2000, 180_000)
        settle(page, dlg, 240_000)
        return {"text": page.locator(dlg).inner_text()[:700]}
    return f


def stress(pid: str) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(f"{ui}/deal-desk/{pid}", wait_until="domcontentloaded")
        page.wait_for_selector(T("dealdesk-step-stress"), timeout=180_000)
        page.locator(T("dealdesk-step-stress")).click()
        page.wait_for_selector(T("stress2-tier"), timeout=240_000)
        idle(page, 1500, 120_000)
        return {"tier": page.locator(T("stress2-tier")).inner_text(), "memo_link": page.locator(T("stress2-memo")).count(),
                "verdict": page.locator(T("stress2-verdict-card")).inner_text()[:300] if page.locator(T("stress2-verdict-card")).count() else ""}
    return f


def s_whatif_sev(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(T("whatif-calibrated"), timeout=120_000)
    page.locator(T("whatif-calibrated")).click()
    page.wait_for_selector(T("whatif-scenario-set"), timeout=300_000)
    idle(page, 1500, 60_000)
    page.locator(T("whatif-scenario-set")).first.scroll_into_view_if_needed()
    ctx["whatif_thread"] = page.url
    rows = {s: page.locator(T(f"whatif-scenario-{s}")).first.inner_text()[:200] for s in ("mild", "moderate", "severe")
            if page.locator(T(f"whatif-scenario-{s}")).count()}
    return {"url": page.url, "rows": rows, "evidence": page.locator(T("whatif-scenario-evidence")).count(),
            "cannot": page.locator(T("whatif-scenario-cannot")).first.inner_text()[:300] if page.locator(T("whatif-scenario-cannot")).count() else "",
            "memo": page.locator(T("whatif-scenario-memo")).count() + page.locator(T("whatif-scenario-memo-link")).count(),
            "question_first": page.evaluate("() => { const q = document.querySelector('[data-testid=\"whatif-turn-question\"], [data-testid=\"whatif-question\"]'); const g = document.querySelector('[data-testid=\"whatif-glance\"]'); return q && g ? q.getBoundingClientRect().top <= g.getBoundingClientRect().top : null; }")}


def s_whatif_evidence(page: Page, ui: str, ctx: dict) -> dict:
    if not ctx.get("whatif_thread"):
        s_whatif_sev(page, ui, ctx)
    else:
        page.goto(ctx["whatif_thread"], wait_until="domcontentloaded")
        page.wait_for_selector(T("whatif-scenario-set"), timeout=180_000)
        idle(page, 1000)
    ev = page.locator(T("whatif-scenario-evidence")).first
    ev.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    memo = page.locator(f'{T("whatif-scenario-memo-link")}, {T("whatif-scenario-memo")}').first
    return {"evidence": ev.inner_text()[:600], "memo_href": memo.get_attribute("href") if memo.count() else None}


def s_lens(page: Page, ui: str, ctx: dict) -> dict:
    if not ctx.get("lens"):
        req = urllib.request.Request("http://127.0.0.1:8509/api/v1/lenses/lenses", method="POST",
                                     data=json.dumps({"request": "Makkah retail cards", "book": "retail"}).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": f"cp_session={ctx['token']}"})
        with urllib.request.urlopen(req, timeout=240) as r:  # noqa: S310 - loopback service
            ctx["lens"] = json.loads(r.read())["lens"]["lens_id"]
    page.goto(f"{ui}/lenses/{ctx['lens']}", wait_until="domcontentloaded")
    page.wait_for_selector(T("lens-interpretation"), timeout=240_000)
    idle(page, 2500, 120_000)
    kpis = {el.get_attribute("data-testid"): el.inner_text().replace("\n", " ") for el in page.locator('[data-testid^="lens-kpi-"]:not([data-testid^="lens-kpi-change"]):not([data-testid^="lens-kpi-trace"])').all()}
    return {"interpretation": page.locator(T("lens-interpretation")).inner_text()[:700], "kpis": kpis}


def tools(path: str, button: str, item: str, wait: str | None = None) -> Callable[[Page, str, dict], dict]:
    def f(page: Page, ui: str, ctx: dict) -> dict:
        page.goto(ui + path, wait_until="domcontentloaded")
        page.wait_for_selector(T(button), timeout=180_000)
        idle(page, 1000, 60_000)
        page.locator(T(button)).click()
        page.wait_for_timeout(400)
        menu_items = page.locator('[role="menu"] [role="menuitem"]').all_inner_texts()
        page.locator(T(item)).click()
        if wait:
            page.wait_for_selector(wait, timeout=120_000)
        idle(page, 2500, 180_000)
        settle(page, "body", 240_000)
        scope = wait or "body"
        return {"menu": menu_items, "text": page.locator(scope).last.inner_text()[:600]}
    return f


def s_event_tool(page: Page, ui: str, ctx: dict) -> dict:
    out = tools("/borrower-360?customer_id=CB03184", "intel-network-tools-b360-button", "intel-network-tool-event",
                T("intel-network-sheet-event"))(page, ui, ctx)
    page.locator(T("intel-event-input")).fill("What if oil falls 30% this morning?")
    page.locator(T("intel-event-run")).click()
    idle(page, 2000, 180_000)
    settle(page, T("intel-network-sheet-event"), 240_000)
    out["after"] = page.locator(T("intel-event")).inner_text()[:800]
    return out


STEPS: list[Step] = [
    ("01_login_lands_on_brief", "J2", s_login),
    ("02_brief", "J2 J3", s_brief),
    ("03_ask_tab", "J2", s_ask),
    ("04_ask_who_to_call", "J2 #7", intel_answer("calls", "Who should I call today?")),
    ("05_ask_oil_falls_30", "J2 #8 J5", intel_answer("event", "oil falls 30% this morning")),
    ("06_noor_panel_voice", "J1 J3", s_noor_panel),
    ("07_noor_panel_routes_intel", "J2 §I", s_noor_routes),
    ("10_landing_dealdesk", "J7 J9 J10", s_dd_landing),
    ("11_landing_whatif", "J7", landing("/what-if", T("whatif-landing"), "whatif")),
    ("12_landing_lenses", "J7", landing("/lenses", T("lenses-landing"), "lenses")),
    ("13_landing_ews", "J7", landing("/early-warning", T("ews-askbar"), "ews")),
    ("14_landing_b360", "J7", landing("/borrower-360", T("b360-askbar"), "b360")),
    ("15_book_tools", "J10 #5 #14-17", s_book),
    ("16_renewal_autopilot", "#5", s_renewals),
    ("20_twa_more_menu", "J10", deal("R12-TWA")),
    ("21_twa_fin_quality", "J11 #6", deal_intel("R12-TWA", "fin-quality")),
    ("22_twa_committee_questions", "#1", deal_intel("R12-TWA", "challenger")),
    ("23_twa_make_approvable", "#4", deal_intel("R12-TWA", "reverse")),
    ("24_twa_security_value", "#3", deal_intel("R12-TWA", "security")),
    ("25_twa_decision_consistency", "#20", deal_intel("R12-TWA", "consistency")),
    ("26_twa_covenant_designer", "#2", deal_intel("R12-TWA", "covenants")),
    ("27_twa_stress_lab", "J5 J6 §S.6", stress("R12-TWA")),
    ("30_twb_fin_quality", "J11 #6", deal_intel("R12-TWB", "fin-quality")),
    ("31_twb_committee_questions", "#1", deal_intel("R12-TWB", "challenger")),
    ("32_twb_make_approvable", "#4", deal_intel("R12-TWB", "reverse")),
    ("33_twb_security_value", "#3", deal_intel("R12-TWB", "security")),
    ("34_twb_decision_consistency", "#20", deal_intel("R12-TWB", "consistency")),
    ("35_twb_stress_lab", "J5 §S.6", stress("R12-TWB")),
    ("40_whatif_mild_moderate_severe", "J4 J5 J6", s_whatif_sev),
    ("41_whatif_evidence_memo", "J6", s_whatif_evidence),
    ("46_lenses_headroom", "#14", tools("/lenses", "portfolio-tools-lenses-button", "portfolio-tool-headroom", T("portfolio-drawer-headroom"))),
    ("47_lenses_exits", "#15", tools("/lenses", "portfolio-tools-lenses-button", "portfolio-tool-exits", T("portfolio-drawer-exits"))),
    ("48_lenses_rwa", "#16", tools("/lenses", "portfolio-tools-lenses-button", "portfolio-tool-rwa", T("portfolio-drawer-rwa"))),
    ("49_lenses_ecl_bridge", "#17", tools("/lenses", "portfolio-tools-lenses-button", "portfolio-tool-ecl_bridge", T("portfolio-drawer-ecl_bridge"))),
    ("50_lenses_workout", "#11", tools("/lenses", "portfolio-tools-lenses-button", "portfolio-tool-workout", T("portfolio-drawer-workout"))),
    ("55_ews_who_to_call", "#7", tools("/early-warning", "ews-tools", "ews-tools-calls")),
    ("60_b360_event_translator", "#8", s_event_tool),
    ("61_b360_contagion", "#9", tools("/borrower-360?customer_id=CB03184", "intel-network-tools-b360-button", "intel-network-tool-contagion", T("intel-network-sheet-contagion"))),
    ("62_b360_employer", "#10", tools("/borrower-360?customer_id=CB03184", "intel-network-tools-b360-button", "intel-network-tool-employer", T("intel-network-sheet-employer"))),
    ("70_dd_inspection", "#18", tools("/deal-desk", "gov-tools", "gov-tool-inspection", T("gov-drawer-inspection"))),
    ("71_dd_exceptions", "#19", tools("/deal-desk", "gov-tools", "gov-tool-exceptions", T("gov-drawer-exceptions"))),
    ("72_dd_rm_track", "#21", tools("/deal-desk", "gov-tools", "gov-tool-rm-track", T("gov-drawer-rm-track"))),
    ("73_dd_doa", "#22", tools("/deal-desk", "gov-tools", "gov-tool-doa", T("gov-drawer-doa"))),
    ("45_lens_dashboard", "J8", s_lens),
    ("74_admin_governance", "#18-22", tools("/settings", "gov-tools", "gov-tool-doa", T("gov-drawer-doa"))),
]


DD_HEALTH = "http://127.0.0.1:8508/api/v1/dealdesk/desk/health"
DD_PID = V5 / "var" / "run" / "dealdesk.pid"


def _dd_rss_mb() -> float:
    try:
        pid = DD_PID.read_text().strip()
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return 0.0


def ensure_dealdesk(max_mb: float = 1400) -> str:
    """Cloud container only (8 GB): the Deal Desk service grows with each engine's caches and was OOM-killed during the
    walk; restart it when it is down or above `max_mb`, and wait until it answers. The Mac does not need this."""
    import subprocess
    ok = False
    try:
        urllib.request.urlopen(DD_HEALTH, timeout=5)  # noqa: S310 - loopback
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    if ok and _dd_rss_mb() < max_mb:
        return ""
    try:
        os.kill(int(DD_PID.read_text().strip()), 15)
        time.sleep(2)
    except (OSError, ValueError):
        pass
    env = {**os.environ, "DEALDESK_PORT": "8508", "DEALDESK_API_PORT": "8508",
           "DEALDESK_CORS_ORIGINS": "http://127.0.0.1:5500,http://localhost:5500"}
    log = open(V5 / "var" / "logs" / "dealdesk.log", "ab")  # noqa: SIM115
    p = subprocess.Popen([str(V5 / ".venv" / "bin" / "python"), "-m", "uvicorn", "backend.dealdesk_thread.api:app",
                          "--host", "127.0.0.1", "--port", "8508"], cwd=V5, env=env, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    DD_PID.write_text(str(p.pid))
    for _ in range(90):
        try:
            urllib.request.urlopen(DD_HEALTH, timeout=5)  # noqa: S310
            return "restarted"
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return "restart failed"


def walker(create: bool) -> str | None:
    """Create (or remove) the temporary fictional login used by step 01; returns the password, never printed."""
    from backend.identity_v5 import store as ids
    ids.ensure()
    with ids.db() as con:
        con.execute("DELETE FROM sessions WHERE username=?", (WALKER,))
        con.execute("DELETE FROM users WHERE username=?", (WALKER,))
        if not create:
            con.commit()
            return None
        admin = con.execute("SELECT * FROM users WHERE is_admin=1 ORDER BY username LIMIT 1").fetchone()
        pw = secrets.token_urlsafe(18)
        con.execute("INSERT INTO users(username, name, role, title, department, initials, books, team, is_admin, password_hash, position)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (WALKER, "Uat Walker", admin["role"], admin["title"], admin["department"], "UW", admin["books"], admin["team"], 1,
                     ids.hash_password(pw), admin["position"]))
        con.commit()
        return pw


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ctx: dict[str, Any] = {"token": mint(), "password": walker(True)}
    report: list[dict] = []
    path = OUT / "walkthrough.json"
    try:   # a partial re-run (--only) replaces its steps and keeps the others
        kept = [r for r in json.loads(path.read_text()) if isinstance(r, dict)]
    except (OSError, ValueError):
        kept = []
    try:
        with sync_playwright() as pw:
            exe = "/opt/pw-browsers/chromium"
            b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
            for w, h in sizes:
                tag = f"{w}x{h}"
                bctx = b.new_context(viewport={"width": w, "height": h}, accept_downloads=True)
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
                    except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
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
                        page.remove_listener("pageerror", handler)
                    except Exception:  # noqa: BLE001
                        pass
                    if page.is_closed() or "crashed" in rec.get("error", ""):
                        # the renderer died (memory in the 8 GB container): a fresh tab for the next step
                        try:
                            page.close()
                        except Exception:  # noqa: BLE001
                            pass
                        page = bctx.new_page()
                        page.set_default_timeout(60_000)
                    report.append(rec)
                    print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} {rec['seconds']}s", flush=True)
                    done = {(r["step"], r["size"]) for r in report}
                    path.write_text(json.dumps([r for r in kept if (r["step"], r["size"]) not in done] + report, indent=1, default=str))
                bctx.close()
            b.close()
    finally:
        walker(False)
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
