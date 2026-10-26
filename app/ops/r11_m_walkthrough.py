"""PLAN_R11 Session M: browser walk-throughs at 1440x900 for the R11 UAT pack (Playwright, Chromium at /opt/pw-browsers).

  .venv/bin/python ops/r11_m_walkthrough.py [--ui http://127.0.0.1:5500] [--only optimise,stress,review,pipeline,draft,
                                            committee,ews,whatif,lenses,thread]

Needs every v5 service up (`V5_UI_MODE=prod ops/v5.sh start` after a production build). Screenshots go to
docs/v5/r11_review/m_*.png (agents: agents_*_m.png); docs/v5/r11_review/m_walkthrough.json records each step's check,
timing (seconds, wall clock in the browser), page errors and the overflow probe. The agents run with the deterministic
planner (no model key in the cloud). Mints a session in the local identity store; no password or secret is read or
printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r11_review"
LOG: list[dict] = []
TOKEN = ""


def api(method: str, url: str, body: dict | None = None, timeout: float = 300) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Cookie": f"cp_session={TOKEN}",
                                          "Origin": "http://127.0.0.1:5500"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - local services only
        return json.loads(r.read() or b"{}")


def idle(page: Page, ms: int = 800) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:  # noqa: BLE001 - long polls keep the network busy
        pass
    page.wait_for_timeout(ms)


def record(name: str, ok: bool, seconds: float, detail: str = "", page: Page | None = None, shot: str | None = None,
           sel: str | None = None) -> None:
    row: dict = {"step": name, "ok": bool(ok), "seconds": round(seconds, 1), "detail": detail}
    if page is not None and shot:
        if sel and page.locator(sel).count():
            try:
                page.locator(sel).first.scroll_into_view_if_needed(timeout=5000)
                page.wait_for_timeout(400)
            except Exception:  # noqa: BLE001
                pass
        page.screenshot(path=str(OUT / f"{shot}.png"))
        row["screenshot"] = f"docs/v5/r11_review/{shot}.png"
        probe = page.evaluate(PROBE, None)
        row["doc_width"] = probe.get("docWidth")
        row["overflow"] = probe.get("overflow")
        row["rough"] = probe.get("rough")
    LOG.append(row)
    print(f"{'PASS' if ok else 'FAIL'} {name} ({seconds:.1f}s) {detail}", flush=True)


def deal(page: Page, ui: str, pid: str, step: str | None = None) -> None:
    page.goto(f"{ui}/deal-desk/{pid}" + (f"?step={step}" if step else ""))
    page.wait_for_selector('[data-testid="dealdesk-stepper"]', timeout=120000)
    idle(page)


def optimise(page: Page) -> None:
    if page.locator('[data-testid="dealdesk-optimise-view"]').count():
        return
    page.click('[data-testid="dealdesk-optimise"]')
    page.wait_for_selector('[data-testid="dealdesk-optimise-view"]', timeout=180000)


def guarded(name: str):
    def wrap(fn):
        def run(*a, **k):
            t = time.time()
            try:
                fn(*a, **k)
            except Exception as e:  # noqa: BLE001 - a walk-through records the failure and carries on
                record(name, False, time.time() - t, f"{type(e).__name__}: {str(e)[:300]}")
        return run
    return wrap


@guarded("DD-01 Optimise")
def w_optimise(page: Page, ui: str) -> None:
    deal(page, ui, "DD-01")
    t = time.time()
    optimise(page)
    n = page.locator('[data-testid="dealdesk-optimise-view"]').count()
    record("DD-01 Optimise: structures (unchanged view first)", n == 1, time.time() - t, "", page,
           "m01_dd01_optimise_structures", '[data-testid="dealdesk-optimise-view"]')
    t = time.time()
    page.wait_for_selector('[data-testid="dealdesk-forward-answer"]', timeout=180000)
    record("DD-01 Forward risk under the structures", True, time.time() - t,
           page.locator('[data-testid="dealdesk-forward-answer"]').inner_text()[:200], page, "m02_dd01_forward_risk",
           '[data-testid="dealdesk-panel-forward"]')
    t = time.time()
    page.wait_for_selector('[data-testid="stress-summary-answer"]', timeout=180000)
    record("DD-01 Stress summary", True, time.time() - t,
           page.locator('[data-testid="stress-summary-answer"]').inner_text()[:200], page, "m03_dd01_stress_summary",
           '[data-testid="dealdesk-panel-stress"]')
    btn = page.locator('[data-testid="dealdesk-pipeline-test-button"]').first
    t = time.time()
    btn.wait_for(timeout=60000)
    for _ in range(120):
        if btn.is_enabled():
            break
        page.wait_for_timeout(500)
    record("DD-01 Test against pipeline active without a click", btn.is_enabled(), time.time() - t, "", page,
           "m04_dd01_pipeline_button_active", '[data-testid="dealdesk-panel-pipeline"]')
    t = time.time()
    btn.click()
    page.wait_for_selector('[data-testid="dealdesk-pipeline-test-result"]', timeout=300000)
    page.wait_for_timeout(800)
    record("DD-01 Test against pipeline result", True, time.time() - t,
           page.locator('[data-testid="dealdesk-pipeline-test-line"]').first.inner_text()[:200], page,
           "m05_dd01_pipeline_test_result", '[data-testid="dealdesk-pipeline-test-result"]')


@guarded("DD-06 Stress step")
def w_stress(page: Page, ui: str) -> None:
    deal(page, ui, "DD-06")
    optimise(page)
    t = time.time()
    deal(page, ui, "DD-06", "stress")
    page.wait_for_selector('[data-testid="stress-answer"]', timeout=180000)
    page.wait_for_timeout(1500)
    record("DD-06 Stress step", page.locator('[data-testid="stress-heatmap"]').count() > 0, time.time() - t,
           page.locator('[data-testid="stress-answer"]').inner_text()[:200], page, "m06_dd06_stress_step")
    page.locator('[data-testid="stress-heatmap"]').first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "m06b_dd06_stress_heatmap.png"))


@guarded("Review")
def w_review(page: Page, ui: str) -> None:
    for cid, tag in (("PRP-A-GMC", "a"), ("PRP-B-ASB", "b")):
        t = time.time()
        page.goto(f"{ui}/deal-desk/review?case={cid}&view=workspace")
        page.wait_for_selector('[data-testid="review-answer"]', timeout=240000)
        idle(page, 1200)
        shown = page.locator('[data-testid="review-finding"]').count()
        ws = api("POST", f"http://127.0.0.1:8508/api/v1/dealdesk/proposals/{cid}/review", {})
        expected = len(ws.get("findings") or [])
        record(f"Case {tag.upper()} Review: every finding visible", shown >= expected and expected > 0, time.time() - t,
               f"{shown} findings on screen, {expected} from the API; " + page.locator('[data-testid="review-answer"]').inner_text()[:160],
               page, f"m07{tag}_case_{tag}_review")
    # the DD Review step in the deal view
    deal(page, ui, "DD-02")
    optimise(page)
    t = time.time()
    deal(page, ui, "DD-02", "review")
    page.wait_for_selector('[data-testid="review-answer"]', timeout=240000)
    record("DD-02 Review step", True, time.time() - t, page.locator('[data-testid="review-answer"]').inner_text()[:160],
           page, "m07c_dd02_review_step")


@guarded("Pipeline mode")
def w_pipeline(page: Page, ui: str) -> None:
    page.goto(f"{ui}/deal-desk?mode=pipeline")
    page.wait_for_selector('[data-testid="dealdesk-pipeline-mode"]', timeout=120000)
    idle(page, 1000)
    record("Pipeline mode: pending deals listed", page.locator('[data-testid^="dealdesk-pipeline-deal-"]').count() > 20, 0,
           f"{page.locator('[data-testid^=dealdesk-pipeline-deal-]').count()} deals", page, "m08_pipeline_mode")
    t = time.time()
    page.click('[data-testid="dealdesk-pipeline-optimise"]')
    page.wait_for_selector('[data-testid="dealdesk-pipeline-headline"]', timeout=300000)
    page.wait_for_timeout(1200)
    record("Pipeline mode: Optimise pipeline", True, time.time() - t,
           page.locator('[data-testid="dealdesk-pipeline-headline"]').inner_text()[:220], page, "m09_pipeline_result",
           '[data-testid="dealdesk-pipeline-result"]')
    page.locator('[data-testid="dealdesk-pipeline-appetite-card"]').first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "m09b_pipeline_appetite.png"))
    page.locator('[data-testid="dealdesk-pipeline-frontier-card"]').first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "m09c_pipeline_frontier.png"))


@guarded("Draft proposal Case A")
def w_draft(page: Page, ui: str) -> None:
    page.goto(f"{ui}/deal-desk/review?case=PRP-A-GMC&view=workspace")
    page.wait_for_selector('[data-testid="review-answer"]', timeout=240000)
    t = time.time()
    page.click('[data-testid="review-draft-toggle"]')
    page.wait_for_selector('[data-testid="draft-proposal-dialog"]', timeout=30000)
    page.wait_for_selector('[data-testid="draft-answer"]', timeout=240000)
    page.wait_for_timeout(1000)
    record("Draft proposal (house style) for Case A, from the Review workspace", True, time.time() - t,
           page.locator('[data-testid="draft-answer"]').inner_text()[:220], page, "m10_case_a_draft_proposal")
    page.keyboard.press("Escape")
    # the same button on the deal's Proposal step
    deal(page, ui, "DD-01", "proposal")
    record("Draft proposal button on the Proposal step", page.locator('[data-testid="draft-proposal-button"]').count() == 1, 0,
           "", page, "m10b_dd01_proposal_step_draft_button")


@guarded("Prepare for committee")
def w_committee(page: Page, ui: str) -> None:
    deal(page, ui, "DD-02")
    btn = page.locator('[data-testid="prepare-for-committee"]').first
    record("Prepare for committee in the deal header", btn.count() == 1, 0, "", page, "agents_dealdesk_m1_header")
    t = time.time()
    btn.click()
    page.wait_for_selector('[data-testid="agent-run-drawer"]', timeout=30000)
    page.wait_for_timeout(4000)
    page.screenshot(path=str(OUT / "agents_dealdesk_m2_live.png"))
    page.wait_for_selector('[data-testid="agent-narrative"]', timeout=300000)
    page.wait_for_timeout(1500)
    head = page.locator('[data-testid="agent-headline"]').first.inner_text()[:220] if page.locator('[data-testid="agent-headline"]').count() else ""
    record("Committee Preparation agent DD-02 end to end (deterministic planner)", True, time.time() - t, head, page,
           "agents_dealdesk_m3_pack")
    page.locator('[data-testid="agent-findings"]').first.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "agents_dealdesk_m4_findings.png"))


@guarded("Early Warning triage agent")
def w_ews(page: Page, ui: str) -> None:
    page.goto(f"{ui}/early-warning")
    page.wait_for_selector('[data-testid="ews-triage-agent"]', timeout=120000)
    idle(page, 1000)
    t = time.time()
    page.click('[data-testid="ews-triage-agent"]')
    page.wait_for_selector('[data-testid="agent-run-drawer"]', timeout=30000)
    page.wait_for_selector('[data-testid="agent-narrative"]', timeout=300000)
    page.wait_for_timeout(1500)
    head = page.locator('[data-testid="agent-headline"]').first.inner_text()[:220] if page.locator('[data-testid="agent-headline"]').count() else ""
    record("Early Warning triage agent, this period (deterministic planner)", True, time.time() - t, head, page,
           "agents_ews_m1_period_drawer")
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    if page.locator('[data-testid="agent-run-drawer"]').count():
        page.mouse.click(300, 450)  # the drawer closes on its backdrop
        page.wait_for_timeout(600)
    if page.locator('[data-testid="ews-open-warned"]').count():
        page.click('[data-testid="ews-open-warned"]')
        idle(page, 800)
        fwd = page.get_by_text("Forward risk (warned, still performing)", exact=False)
        if fwd.count():  # Stage 3 names lead the warned list and are outside triage; the triaged names are here
            fwd.first.click()
        try:
            page.wait_for_selector('[data-testid^="ews-agent-verdict-"]', timeout=60000)
        except Exception:  # noqa: BLE001 - recorded as the count below
            pass
    idle(page, 1500)
    chips = page.locator('[data-testid^="ews-agent-verdict-"]').count()
    record("Agent verdict chips in the borrower list", chips > 0, 0, f"{chips} chips on this view", page, "agents_ews_m2_list")


@guarded("What-If goal agent")
def w_whatif(page: Page, ui: str) -> None:
    th = api("POST", "http://127.0.0.1:8503/api/v1/whatif/threads", {"domain": "corporate"})
    page.goto(f"{ui}/what-if/thread/{th['thread_id']}")
    box = page.get_by_test_id("whatif-composer")
    box.wait_for(timeout=120000)
    box.fill("oil price -40%")
    page.wait_for_timeout(600)
    single = page.get_by_test_id("whatif-run-as-agent").count()
    box.fill("are we provisioned enough for an oil shock?")
    page.get_by_test_id("whatif-run-as-agent").wait_for(timeout=10000)
    record("What-If: a single scenario shows no agent button; a goal does", single == 0, 0, "", page, "agents_whatif_m1_goal")
    t = time.time()
    page.get_by_test_id("whatif-run-as-agent").click()
    page.get_by_test_id("whatif-agent-open").wait_for(timeout=400000)
    page.wait_for_timeout(1500)
    record("What-If goal agent end to end (deterministic planner)", True, time.time() - t, "", page, "agents_whatif_m2_results")
    page.get_by_test_id("whatif-agent-open").click()
    page.wait_for_selector('[data-testid="agent-run-drawer"]', timeout=20000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "agents_whatif_m3_drawer.png"))
    page.keyboard.press("Escape")


@guarded("Lenses monitoring agent")
def w_lenses(page: Page, ui: str) -> None:
    page.goto(f"{ui}/lenses")
    page.wait_for_selector('[data-testid="lens-monitoring-agent"]', timeout=120000)
    idle(page, 800)
    page.click('[data-testid="lens-monitoring-agent"]')
    page.wait_for_selector('[data-testid="monitor-panel"]', timeout=30000)
    t = time.time()
    plan = page.locator('[data-testid="monitor-plan"], [data-testid="monitor-replan"]').first
    plan.wait_for(timeout=60000)
    plan.click()
    page.wait_for_selector('[data-testid="monitor-proposed-table"]', timeout=400000)
    page.wait_for_timeout(1500)
    rows = page.locator('[data-testid="monitor-proposed-table"] tbody tr').count()
    record("Lenses monitoring agent plans the set (deterministic planner)", rows > 0, time.time() - t,
           f"{rows} proposed metrics", page, "agents_lenses_m1_proposed")
    if page.locator('[data-testid="agent-run-drawer"]').count():
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "agents_lenses_m2_panel.png"))


@guarded("Thread intents")
def w_thread(page: Page, ui: str) -> None:
    qs = ["What is the chance of Stage 2 next quarter?", "Run early warning on this deal", "Stress this deal with oil -30%",
          "What breaks first?", "Does this make the cut?", "Optimise the pipeline", "What's wrong with this proposal?",
          "Draft the committee sheet"]
    for i, q in enumerate(qs):
        deal(page, ui, "DD-01")
        n = page.locator('[data-testid="dealdesk-turn"]').count()
        t = time.time()
        page.fill('[data-testid="dealdesk-composer"]', q)
        page.click('[data-testid="dealdesk-send"]')
        page.wait_for_function(f"document.querySelectorAll('[data-testid=\"dealdesk-turn\"]').length > {n}", timeout=300000)
        page.wait_for_timeout(1500)
        last = page.locator('[data-testid="dealdesk-turn"]').last
        txt = last.inner_text()[:200].replace("\n", " ")
        bad = any(w in txt for w in ("couldn't", "could not", "Error", "error"))
        last.scroll_into_view_if_needed()
        record(f"Thread: {q}", not bad, time.time() - t, txt, page, f"m2{i}_thread_{i}")


def main() -> int:
    global TOKEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {x for x in a.only.split(",") if x}
    OUT.mkdir(parents=True, exist_ok=True)
    TOKEN = mint()
    steps = [("optimise", w_optimise), ("stress", w_stress), ("review", w_review), ("pipeline", w_pipeline),
             ("draft", w_draft), ("committee", w_committee), ("ews", w_ews), ("whatif", w_whatif), ("lenses", w_lenses),
             ("thread", w_thread)]
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies([{"name": "cp_session", "value": TOKEN, "domain": "127.0.0.1", "path": "/", "httpOnly": True, "sameSite": "Lax"}])
        page = ctx.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        for key, fn in steps:
            if only and key not in only:
                continue
            fn(page, a.ui)
        LOG.append({"page_errors": errs})
        b.close()
    path = OUT / ("m_walkthrough.json" if not only else f"m_walkthrough_{'_'.join(sorted(only))}.json")
    path.write_text(json.dumps(LOG, indent=1))
    bad = [r for r in LOG if r.get("ok") is False]
    print(f"{len(LOG) - 1 - len(bad)} of {len(LOG) - 1} steps passed; page errors: {len(errs)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
