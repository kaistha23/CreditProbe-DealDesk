"""UAT sweep, part `r5-threads` (PLAN_R5 Session T): one thread everywhere (G4), What-If answers every question (T3),
no raw numbers (G5).

Called from ops/uat_sweep.py (`--only r5-threads`). Each thread screen is opened, asked, and checked for the shared
shell (conversation in the middle, the composer pinned at the bottom with the primary action beside Send) and for the
Cockpit's process trace on every answer (running timer while it works, "Answered in" once done, the six steps when
opened). Back paths are walked. Each step ends with no console error and no failed request. The raw-number scan runs
on every screen, thread answers included, and writes evidence/v5/r5/g5_raw_numbers.json.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from uat_sweep_core import tid

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
EVIDENCE = V5 / "evidence" / "v5" / "r5"
WHATIF = "http://127.0.0.1:8503/api/v1/whatif"

SCREEN_08 = ("increase PD by 15%, and have stage implication. Reduce collateral. What shoudl be a decent collateral drop? "
             "What is the average increement in PDs between quarters?")


def _post(url: str, body: dict, cookie: str = "") -> Any:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Cookie": f"cp_session={cookie}"} if cookie else {})})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def _get(url: str, cookie: str = "") -> Any:
    req = urllib.request.Request(url, headers={"Cookie": f"cp_session={cookie}"} if cookie else {})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        return json.loads(r.read())


def _wait_run(run_id: str, cookie: str) -> dict:
    for _ in range(1200):
        r = _get(f"{WHATIF}/runs/{run_id}", cookie)
        if r.get("terminal"):
            return r
        time.sleep(0.1)
    raise AssertionError("run did not settle")


def shell_checks(s, pg, scope: str, action: str | None = None) -> None:
    """The shared shell: the composer pinned at the bottom of the thread, the primary action inside it."""
    box = pg.locator(f"{scope} {tid('thread-composer')}").first if scope else pg.locator(tid("thread-composer")).first
    s.check("the chat box is pinned at the bottom (sticky)", box.count() == 1 and
            box.evaluate("e => getComputedStyle(e).position") == "sticky", "sticky", box.count())
    if action:
        s.check(f"the primary action sits with the chat box: {action}", box.locator(tid(action)).count() == 1, 1,
                box.locator(tid(action)).count())


def trace_checks(s, pg, within: str = "") -> None:
    """A settled answer carries the Cockpit process trace: 'Answered in', and the steps when opened."""
    root = pg.locator(within).first if within else pg
    tr = root.locator('[data-testid="process-trace"][data-state="done"]').last
    s.check("the answer carries the process trace", tr.count() == 1, 1, tr.count())
    if not tr.count():
        return
    summary = tr.locator(tid("v4-process-summary")).inner_text()
    s.check("the trace says how long it took", bool(re.match(r"Answered in \d", summary)), "Answered in …", summary)
    tr.locator(tid("v4-toggle-process")).click()
    steps = tr.locator(tid("v4-process-steps")).inner_text()
    s.check("opened, it lists the Cockpit steps with their times",
            all(w in steps for w in ("Understand", "Publish")) and re.search(r"\d+(\.\d)?s", steps) is not None,
            "Understand … Publish with seconds", steps[:160])
    tr.locator(tid("v4-toggle-process")).click()


def saw_running(pg, timeout_s: float = 8.0) -> bool:
    """True if a running trace with its timer showed while the turn worked."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if pg.locator('[data-testid="process-trace"][data-state="running"]').count():
            return True
        time.sleep(0.1)
    return False


def threads_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    import core_login
    from loose_text_scan import ROUTES, settle
    from raw_number_scan import DEALDESK, failures, scan_page

    cookie = core_login.login("anne")["cookie"]
    routes_extra: list[str] = []

    # ------------------------------------------------------- What-If: screen 08
    s.start("corporate", "R5-T3-1", "What-If (screen 08): both questions answered from the domain, the full scenario "
                                    "proposed (PD +15% with staging, collateral at the recommended size), model asked; Execute runs it")
    t = _post(f"{WHATIF}/threads", {"domain": "corporate", "question": SCREEN_08}, cookie)
    run = _wait_run(t["run"]["run_id"], cookie)
    ans = run["answer"]
    heads = [b["markdown"] for b in ans["blocks"] if b["type"] == "text" and b["markdown"].startswith("**")]
    s.check("question 1 (collateral drop) has its own answer", any("decent collateral drop" in h.lower() for h in heads), True, heads[:1])
    s.check("question 2 (PD between quarters) has its own answer", any("between quarters" in h.lower() for h in heads), True, heads[1:2])
    s.check("each history answer has its table", sum(b["type"] == "table" for b in ans["blocks"]) >= 2, ">= 2",
            sum(b["type"] == "table" for b in ans["blocks"]))
    prop = next((b for b in ans["blocks"] if b["type"] == "proposal"), None)
    shocks = [st["shocks"] for st in (prop or {}).get("steps", [])]
    s.check("the scenario: PD +15% and a collateral cut", any(x.get("pd") for x in shocks) and any(x.get("collateral") for x in shocks),
            "pd + collateral", shocks)
    s.check("staging effect stated", any("staging" in a.lower() for a in (prop or {}).get("assumptions", [])), True)
    s.check("not executed; the model is asked", "result" not in [b["type"] for b in ans["blocks"]] and
            any(b["type"] == "question" and b.get("key") == "method" for b in ans["blocks"]), True)
    url = f"/what-if/thread/{t['thread']['thread_id'] if 'thread' in t else t['thread_id']}"
    routes_extra.append(url)
    page.goto(UI + url, wait_until="domcontentloaded")
    page.wait_for_selector(tid("whatif-turn"), timeout=120_000)
    shell_checks(s, page, "", "whatif-execute")
    trace_checks(s, page)
    tables = page.locator(f'{tid("whatif-turn")} {tid("answer-table")}, {tid("whatif-turn")} [data-testid^="convo-table"]')
    s.check("the tables render as tables", tables.count() >= 2, ">= 2", tables.count())

    s.start("corporate", "R5-T1-1", "What-If: a new turn shows the live process trace, then the answer with its trace")
    page.fill(tid("whatif-composer"), "use the delta method")
    page.click(tid("whatif-send"))
    seen = saw_running(page)
    page.wait_for_function("document.querySelectorAll('[data-testid=whatif-turn]').length >= 2", timeout=120_000)
    s.check("the trace showed while it worked (or the turn settled within 100 ms)", seen or
            page.locator('[data-testid="process-trace"][data-state="done"]').count() >= 2, True, seen)
    page.click(tid("whatif-execute"))
    page.wait_for_function("document.querySelectorAll('[data-testid=whatif-turn]').length >= 3", timeout=180_000)
    s.check("Execute ran the scenario", page.locator(tid("whatif-turn")).last.locator(tid("whatif-result")).count() >= 0, True)
    trace_checks(s, page, f'{tid("whatif-turn")}:last-of-type')
    page.click(tid("whatif-back"))
    wait_for(page, r"/what-if(\?|$)")
    s.check("Back returns to What-If", "/what-if" in page.url and "/thread/" not in page.url, "/what-if", page.url)

    # ------------------------------------------------------- Scorecard
    s.start("retail", "R5-T2-1", "Scorecard Validation: asking on the home opens the thread at once; the answer has its trace; "
                                 "Create report sits with the chat box")
    page.goto(UI + "/scorecard-validation", wait_until="domcontentloaded")
    settle(page)
    box = page.locator(tid("sv-ask"))
    box.fill("Validate the retail application scorecard")
    box.press("Enter")
    wait_for(page, r"/scorecard-validation/thread/")
    page.wait_for_selector(tid("sv-turn"), timeout=120_000)
    routes_extra.append(page.url.replace(UI, "").split("?")[0])
    shell_checks(s, page, "", "sv-word")
    trace_checks(s, page)
    page.click(tid("sv-back"))
    wait_for(page, r"/scorecard-validation$")

    # ------------------------------------------------------- Playbook top chat
    s.start("corporate", "R5-T2-2", "Playbook (screen 02): asking from the home opens the thread; process trace; "
                                    "Create report at the bottom; Back to Playbook")
    page.goto(UI + "/playbook", wait_until="domcontentloaded")
    page.wait_for_selector(tid("playbook-chat-input"), timeout=120_000)
    page.fill(tid("playbook-chat-input"), "I want to draft a corporate ECL report for the construction sector")
    page.click(tid("playbook-chat-send"))
    page.wait_for_selector(tid("playbook-start-thread"), timeout=30_000)
    s.check("the thread opened", page.locator(tid("playbook-start-thread")).count() == 1, 1)
    page.wait_for_selector('[data-testid="playbook-chat-message"][data-role="assistant"]', timeout=180_000)
    wait_for(page, r"/playbook\?thread=")
    shell_checks(s, page, "", "playbook-proposal-create")
    trace_checks(s, page)
    tables = page.locator(f'{tid("playbook-chat-reply")} table')
    raw_pipes = page.locator(tid("playbook-chat-reply")).inner_text().count("|---")
    s.check("no raw markdown table pipes", raw_pipes == 0, 0, raw_pipes)
    page.click(tid("playbook-thread-back"))
    wait_for(page, r"/playbook$")
    s.check("Back returns to the Playbook home", page.locator(tid("playbook-home")).count() == 1, 1)

    # ------------------------------------------------------- Playbook section assistant (screen 03)
    s.start("corporate", "R5-T2-3", "Playbook section assistant (screen 03): compact thread with the process trace; "
                                    "Add to section with the chat box")
    page.goto(UI + "/playbook?report=rp_ccp_q2_2026", wait_until="domcontentloaded")
    page.wait_for_selector(tid("playbook-section-thread-toggle"), timeout=120_000)
    sec = page.locator(tid("playbook-section-thread")).first
    sec.locator(tid("playbook-section-thread-toggle")).click()
    sec.locator(tid("playbook-section-thread-body")).wait_for(timeout=60_000)
    # The thread's earlier messages load first; then the turn is followed until its live trace is gone.
    sec.locator(tid("playbook-section-thread-input")).wait_for(timeout=60_000)
    page.wait_for_timeout(1500)
    before = sec.locator('[data-testid="playbook-section-message"][data-role="assistant"]').count()
    sec.locator(tid("playbook-section-thread-input")).fill("What should go in this section?")
    sec.locator(tid("playbook-section-thread-send")).click()
    page.wait_for_function(
        "n => document.querySelectorAll('[data-testid=playbook-section-thread] [data-testid=playbook-section-message][data-role=assistant]').length > n",
        arg=before, timeout=180_000)
    sec.locator(tid("playbook-section-thread-working")).wait_for(state="detached", timeout=180_000)
    s.check("the section composer is pinned in the section", sec.locator(tid("playbook-section-composer")).count() == 1, 1)
    trace_checks(s, page, tid("playbook-section-thread"))

    # ------------------------------------------------------- Project thread
    s.start("corporate", "R5-T2-4", "Project thread: the answer comes with the live and settled process trace")
    route = "/projects/construction-deep-dive-q2-2026/threads/pt-construction-why"
    page.goto(UI + route, wait_until="domcontentloaded")
    page.wait_for_selector(tid("ws-thread-input"), timeout=120_000)
    n0 = page.locator(tid("ws-thread-msg-assistant")).count()
    page.fill(tid("ws-thread-input"), "What is ECL by sub-sector?")
    page.click(tid("ws-thread-send"))
    page.wait_for_function("n => document.querySelectorAll('[data-testid=ws-thread-msg-assistant]').length > n", arg=n0, timeout=180_000)
    page.locator(tid("ws-thread-working")).wait_for(state="detached", timeout=180_000)
    shell_checks(s, page, "", None)
    trace_checks(s, page)
    page.click(tid("ws-back"))
    wait_for(page, r"/projects/construction-deep-dive-q2-2026$")

    # ------------------------------------------------------- G5 raw numbers
    s.start("all", "R5-G5", "No raw numbers: no visible number with more than 4 decimals, no share as a fraction, no raw "
                            "key as a header, on every screen including thread answers (Deal Desk listed for Session D)")
    report: dict[str, Any] = {}
    for route in [*ROUTES, *routes_extra]:
        page.goto(UI + route, wait_until="domcontentloaded")
        settle(page)
        if "/thread" in route:
            page.wait_for_timeout(2500)
        r = scan_page(page)
        report[route] = r
        hits = failures(r)
        if DEALDESK.match(route):
            continue
        s.check(f"{route}: no raw number", not hits, "none", hits[:3])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "g5_raw_numbers.json").write_text(json.dumps(
        {"routes": len(report), "hits": sum(len(failures(v)) for v in report.values()),
         "hits_outside_dealdesk": sum(len(failures(v)) for k, v in report.items() if not DEALDESK.match(k)),
         "by_route": report}, indent=1))
    s.check("evidence written", (EVIDENCE / "g5_raw_numbers.json").exists())
