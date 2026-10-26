"""UAT sweep, PLAN_R3 S3-2: Analyses, Investigations and Projects (Anne's definitions).

Call from ops/uat_sweep.py like the Core parts:

    ("work", lambda: __import__("sweep_r3_work").work_steps(s, page, UI, wait_url)),

What it walks, as the seeded personas, with every figure on screen checked against the Core service's API:
  1. the three lists (one card per item the API returns; a retail analyst sees only what is visible to him)
  2. every seeded analysis: question, narrative and key figures equal the API; Back
  3. Refresh "EAD by sector" to 2025Q4 and "What-If: oil -40%" to 2025Q4: before and after side by side, every
     figure equal to the API's refresh of the same analysis and period
  4. every seeded investigation: the whole conversation (turns and artifacts) as the API holds it; Continue opens the
     source; a turn added here appears in the conversation
  5. both seeded projects: access rules, documents and threads as the API holds them; a new thread answers in scope
     with the book's figure and refuses out of scope; the retail project the same way for Omar
  6. Save as analysis and Save as investigation from a What-If thread (figures equal the What-If engine's), and Save
     as investigation from Early Warning
  7. Share (sent through Mail and arriving in Sara's inbox) and the Add to report dialog
  8. every Back path: analysis, investigation, project, project thread

The Playbook service (8506) must be up for the Add to report dialog to list its reports (after the R3 merge it is).
Each step ends with no console error, no page error and no failed request (the Sweep object enforces it).
"""
from __future__ import annotations

import os
import re
import time
import urllib.request
from typing import Any, Callable

import core_login

A = "/api/v1/workspace"
WHATIF = os.environ.get("WHATIF_API_ORIGIN", "http://127.0.0.1:8503").rstrip("/") + "/api/v1/whatif"
NAV = 'nav[aria-label="Primary"]'

A_SECTOR, A_RETAIL_S2, A_OIL = "ead-by-sector-2026q2", "retail-stage2-build-2026-08", "whatif-oil-minus-40-corporate"
A_SUBSECTOR = "construction-ecl-by-subsector-2026q1-q2"
INV_CONSTRUCTION, INV_RETAIL = "construction-ecl-rise-q2-2026", "retail-risk-build-up-2026"
PRJ_CONSTRUCTION, PRJ_RETAIL = "construction-deep-dive-q2-2026", "retail-stage2-review"


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def _watch(page, s) -> None:
    s.observe(page)
    page.on("console", lambda m: s.errors.append("console: " + m.text[:240])
            if m.type == "error" and not s._allowed_console(m.text) else None)
    page.on("pageerror", lambda e: s.errors.append("pageerror: " + str(e)[:240]))
    page.on("response", lambda r: s.errors.append(f"http {r.status}: {r.request.method} {r.url[:180]}")
            if r.status >= 400 and not s._ignored(r.url) and not s._allowed_response(r) else None)
    page.on("requestfailed", lambda r: s.errors.append(f"request failed ({r.failure}): {r.method} {r.url[:180]}")
            if not s._ignored(r.url) and "ERR_ABORTED" not in str(r.failure) else None)


def _as(browser, s, user: str):
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
    core_login.add_session(ctx, user)
    pg = ctx.new_page()
    pg.set_default_timeout(60_000)
    _watch(pg, s)
    return ctx, pg


def _close(a: Any, b: Any, rel: float = 1e-9) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(a - b) <= max(1e-6, rel * max(abs(a), abs(b)))


def _get_json(url: str) -> Any:
    import json
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def work_steps(s, page, UI: str, wait_url: Callable[..., Any]) -> None:
    browser = page.context.browser
    ck = {u: core_login.login(u)["cookie"] for u in ("anne", "khalid.alotaibi", "sara.aldosari", "omar.alghamdi",
                                                     "reem.alshehri", "abdullah.alzahrani")}
    get = lambda path, user="anne": core_login.api_get(A + path, ck[user])  # noqa: E731
    post = lambda path, body, user="anne": core_login.api_post(A + path, body, ck[user])  # noqa: E731

    # ------------------------------------------------------------- 1. lists
    ctx, pg = _as(browser, s, "anne")
    s.page = pg
    for label, path, key, prefix in (("Analyses", "/analyses", "analyses", "ws-analysis-"),
                                     ("Investigations", "/investigations", "investigations", "ws-investigation-"),
                                     ("Projects", "/projects", "projects", "ws-project-")):
        s.start("both", "S3-2", f"{label}: one card per item the API returns, the seeded ones included")
        ids = [x["id"] for x in get(path)[key]]
        pg.goto(UI + path, wait_until="domcontentloaded")
        for i in ids:
            pg.wait_for_selector(tid(prefix + i), timeout=90_000)
        s.check(f"{label}: every item listed once", all(pg.locator(tid(prefix + i)).count() == 1 for i in ids), ids, "")
        seeded = {"Analyses": {A_SECTOR, A_RETAIL_S2, A_OIL}, "Investigations": {INV_CONSTRUCTION, INV_RETAIL},
                  "Projects": {PRJ_CONSTRUCTION, PRJ_RETAIL}}[label]
        s.check(f"{label}: the seeded items are there", seeded <= set(ids), sorted(seeded), ids)
        s.finish()

    s.start("retail", "S3-2", "Visibility: Omar (retail analyst) sees the retail project, not the corporate one")
    octx, opg = _as(browser, s, "omar.alghamdi")
    s.page = opg
    opg.goto(UI + "/projects", wait_until="domcontentloaded")
    opg.wait_for_selector(tid(f"ws-project-{PRJ_RETAIL}"), timeout=90_000)
    s.check("retail project listed", opg.locator(tid(f"ws-project-{PRJ_RETAIL}")).count() == 1)
    s.check("corporate deep-dive not listed", opg.locator(tid(f"ws-project-{PRJ_CONSTRUCTION}")).count() == 0)
    s.finish()
    s.page = pg

    # --------------------------------------------- 2. every seeded analysis
    for aid in (A_SECTOR, A_RETAIL_S2, A_OIL, A_SUBSECTOR):
        a = get(f"/analyses/{aid}")
        s.start(a.get("book") or "both", "S3-2", f"Analysis '{a['title']}': question, answer and key figures as saved; Back")
        pg.goto(UI + "/analyses", wait_until="domcontentloaded")
        pg.wait_for_selector(tid(f"ws-analysis-open-{aid}"), timeout=90_000)
        pg.click(tid(f"ws-analysis-open-{aid}"))
        pg.wait_for_selector(tid(f"ws-analysis-detail-{aid}"), timeout=60_000)
        s.check("the question is shown", a["question"] in pg.inner_text(tid("ws-analysis-question")), a["question"], "")
        s.check("the narrative is shown", a["answer"]["narrative"][:60] in pg.inner_text(tid("ws-analysis-narrative")))
        for f in a["answer"].get("figures") or []:
            got = pg.get_attribute(tid(f"ws-analysis-figure-{f['key']}"), "data-value")
            s.check(f"figure {f['label']} equals the API", _close(got, f["value"]), f["value"], got)
        s.check("its table is shown", pg.locator(tid("ws-analysis-table")).count() == 1)
        pg.wait_for_selector(tid("ws-analysis-refresh"), timeout=60_000)
        pg.click(tid("ws-back"))
        wait_url(pg, r".*/analyses$")
        s.check("Back returns to Analyses", pg.url.rstrip("/").endswith("/analyses"), "/analyses", pg.url)
        s.finish()

    # ------------------------------------------- 3. refresh to another period
    for aid, period, book in ((A_SECTOR, "2025Q4", "corporate"), (A_RETAIL_S2, "2026-05", "retail"),
                              (A_OIL, "2025Q4", "corporate")):
        s.start(book, "S3-2", f"Refresh {aid} to {period}: before and after side by side, every figure equal to the API")
        pg.goto(UI + f"/analyses/{aid}", wait_until="domcontentloaded")
        pg.wait_for_selector(tid("ws-analysis-period"), timeout=90_000)
        pg.select_option(tid("ws-analysis-period"), period)
        pg.click(tid("ws-analysis-refresh-run"))
        pg.wait_for_selector(tid("ws-analysis-compare"), timeout=120_000)
        api = post(f"/analyses/{aid}/refresh", {"period": period})
        box = pg.locator(tid("ws-analysis-compare"))
        s.check("after period shown", box.get_attribute("data-after") == period, period, box.get_attribute("data-after"))
        s.check("before period is the saved one", box.get_attribute("data-before") == api["before"]["period"],
                api["before"]["period"], box.get_attribute("data-before"))
        for f in api["comparison"]["figures"]:
            row = pg.locator(tid(f"ws-compare-fig-{f['key']}"))
            s.check(f"{f['label']} after = API", _close(row.get_attribute("data-after-value"), f["after"]), f["after"],
                    row.get_attribute("data-after-value"))
            if f["before"] is not None:
                s.check(f"{f['label']} before = API", _close(row.get_attribute("data-before-value"), f["before"]),
                        f["before"], row.get_attribute("data-before-value"))
        s.check("row-by-row comparison shown", pg.locator('[data-testid^="ws-compare-row-"]').count()
                == len(api["comparison"]["rows"]), len(api["comparison"]["rows"]),
                pg.locator('[data-testid^="ws-compare-row-"]').count())
        s.check("before and after charts", pg.locator(tid("ws-compare-chart-before")).count() == 1
                and pg.locator(tid("ws-compare-chart-after")).count() == 1)
        s.finish()

    # ------------------------------------------------------ 4. investigations
    for iid in (INV_CONSTRUCTION, INV_RETAIL):
        inv = get(f"/investigations/{iid}")
        s.start("both", "S3-2", f"Investigation '{inv['title']}': the whole conversation; Continue opens the source; Back")
        pg.goto(UI + "/investigations", wait_until="domcontentloaded")
        pg.wait_for_selector(tid(f"ws-investigation-{iid}"), timeout=90_000)
        pg.locator(tid(f"ws-investigation-{iid}")).locator("a").first.click()
        pg.wait_for_selector(tid("ws-conversation"), timeout=60_000)
        turns = inv["turns"]
        shown = pg.locator('[data-testid^="ws-turn-"][data-index]').count()
        s.check("every turn shown", shown == len(turns), len(turns), shown)
        arts = sum(len(t["artifacts"]) for t in turns)
        s.check("every artifact shown", pg.locator('[data-testid^="ws-artifact-"]').count() == arts, arts,
                pg.locator('[data-testid^="ws-artifact-"]').count())
        cont = pg.get_attribute(tid("ws-investigation-continue"), "href")
        s.check("Continue goes to the source thread", cont == inv["continue_href"], inv["continue_href"], cont)
        pg.click(tid("ws-investigation-continue"))
        wait_url(pg, re.escape(inv["continue_href"].split("?")[0]) + r".*")
        pg.wait_for_load_state("networkidle")
        s.check("the source opens", inv["continue_href"].split("?")[0] in pg.url, inv["continue_href"], pg.url)
        pg.go_back()
        pg.wait_for_selector(tid("ws-conversation"), timeout=60_000)
        s.finish()

    s.start("corporate", "S3-2", "Continue an investigation here: a turn added appears in its conversation")
    before = len(get(f"/investigations/{INV_CONSTRUCTION}")["turns"])
    # Opened from the list, so Back (the exact previous screen, R7) returns to the list.
    pg.goto(UI + "/investigations", wait_until="domcontentloaded")
    pg.wait_for_selector(tid(f"ws-investigation-{INV_CONSTRUCTION}"), timeout=90_000)
    pg.locator(tid(f"ws-investigation-{INV_CONSTRUCTION}")).locator("a").first.click()
    pg.wait_for_selector(tid("ws-turn-input"), timeout=90_000)
    pg.fill(tid("ws-turn-input"), f"Sweep check {time.strftime('%H:%M:%S')}: figures confirmed against the book.")
    pg.click(tid("ws-turn-send"))
    pg.wait_for_function(f"document.querySelectorAll('[data-testid^=\"ws-turn-\"][data-index]').length === {before + 1}",
                         timeout=60_000)
    s.check("the API holds the new turn", len(get(f"/investigations/{INV_CONSTRUCTION}")["turns"]) == before + 1)
    pg.click(tid("ws-back"))
    wait_url(pg, r".*/investigations$")
    s.check("Back returns to Investigations", pg.url.rstrip("/").endswith("/investigations"))
    s.finish()

    # ------------------------------------------------------------- 5. projects
    for pid, user, inside, outside, figure_check in (
            (PRJ_CONSTRUCTION, "khalid.alotaibi", "What is the ECL and how has it moved?", "What is the retail Stage 2 build?",
             "ecl"),
            (PRJ_RETAIL, "omar.alghamdi", "What is the Stage 2 build by product?", "What is Construction ECL in the corporate book?",
             "stage2_ead")):
        p = get(f"/projects/{pid}", user)
        s.start("both", "S3-2", f"Project '{p['name']}' as {user}: access, documents, threads; a thread answers in scope and refuses outside")
        cx, upg = _as(browser, s, user)
        s.page = upg
        upg.goto(UI + "/projects", wait_until="domcontentloaded")
        upg.wait_for_selector(tid(f"ws-project-{pid}"), timeout=90_000)
        upg.locator(tid(f"ws-project-{pid}")).locator("a").first.click()
        upg.wait_for_selector(tid("ws-project-access"), timeout=60_000)
        on = sorted(d for d in ("corporate", "retail", "ews", "whatif", "bureau", "open_banking", "scorecard")
                    if upg.get_attribute(tid(f"ws-project-domain-{d}"), "data-on") == "1")
        s.check("access rules as the API holds them", on == sorted(p["domains"]), sorted(p["domains"]), on)
        s.check("every document listed", all(upg.locator(tid(f"ws-project-doc-{f['id']}")).count() == 1 for f in p["files"]),
                [f["name"] for f in p["files"]], "")
        s.check("every thread listed", all(upg.locator(tid(f"ws-project-thread-{t['id']}")).count() == 1 for t in p["threads"]),
                [t["title"] for t in p["threads"]], "")
        if p["threads"]:
            first = p["threads"][-1]
            upg.locator(tid(f"ws-project-thread-{first['id']}")).locator("a").first.click()
            upg.wait_for_selector(tid("ws-thread-messages"), timeout=60_000)
            th = get(f"/projects/{pid}/threads/{first['id']}", user)
            n = upg.locator(tid("ws-thread-msg-user")).count() + upg.locator(tid("ws-thread-msg-assistant")).count()
            s.check("seeded thread: every message shown", n == len(th["messages"]), len(th["messages"]), n)
            upg.click(tid("ws-back"))
            upg.wait_for_selector(tid("ws-project-access"), timeout=60_000)
            s.check("Back from the thread returns to the project", f"/projects/{pid}" in upg.url)
        upg.fill(tid("ws-project-new-thread"), inside)
        upg.click(tid("ws-project-new-thread-start"))
        wait_url(upg, rf".*/projects/{re.escape(pid)}/threads/.*")
        upg.wait_for_selector(tid("ws-thread-msg-assistant"), timeout=90_000)
        tid_ = upg.url.rstrip("/").split("/threads/")[1].split("?")[0]
        th = get(f"/projects/{pid}/threads/{tid_}", user)
        reply = th["messages"][-1]
        s.check("in scope: answered, not refused", upg.get_attribute(tid("ws-thread-msg-assistant"), "data-refused") == "0"
                and not reply["refused"])
        # R6 emphasis: the API text carries **bold** markers, which the screen renders as bold.
        plain = re.sub(r"\*\*|__", "", reply["text"])[:80]
        s.check("the answer on screen is the API's", plain in upg.inner_text(tid("ws-thread-messages")), plain,
                upg.inner_text(tid("ws-thread-messages"))[:120])
        fig = next((f for f in reply.get("figures") or [] if f["key"] == figure_check), None)
        s.check(f"the {figure_check} figure is shown and equals the API", fig is not None and _close(
            upg.locator(tid(f"ws-thread-figure-{figure_check}")).first.get_attribute("data-value"), fig["value"]),
            fig and fig["value"], "")
        upg.fill(tid("ws-thread-input"), outside)
        upg.click(tid("ws-thread-send"))
        upg.wait_for_selector(tid("ws-thread-refusal"), timeout=60_000)
        last = get(f"/projects/{pid}/threads/{tid_}", user)["messages"][-1]
        s.check("outside scope: refused", last["refused"] and last["text"].startswith("This project only uses"), True,
                last["text"][:80])
        s.check("the refusal names what the project uses", "This project only uses" in upg.inner_text(tid("ws-thread-messages")))
        upg.click(tid("ws-back"))
        upg.wait_for_selector(tid("ws-project-access"), timeout=60_000)
        upg.click(tid("ws-back"))
        wait_url(upg, r".*/projects$")
        s.check("Back from the project returns to Projects", upg.url.rstrip("/").endswith("/projects"))
        s.finish()
        s.page = pg
        cx.close()

    # ---------------------------------------- 6. Save as … from What-If and EWS
    s.start("corporate", "S3-2", "What-If: Save as analysis (figures equal the What-If engine) and Save as investigation (every turn)")
    kctx, kpg = _as(browser, s, "khalid.alotaibi")
    s.page = kpg
    kpg.goto(UI + "/what-if?domain=corporate", wait_until="domcontentloaded")
    kpg.wait_for_selector(tid("whatif-ask"), timeout=90_000)
    kpg.fill(tid("whatif-ask"), "oil price -40%")
    kpg.click(tid("whatif-ask-send"))
    wait_url(kpg, r".*/what-if/thread/.*")
    deadline = time.time() + 180
    executed = False
    while time.time() < deadline:
        # PLAN_R4 A1: the statement is a proposal; Execute runs it (then the model question).
        if not executed and kpg.locator(tid("whatif-proposal")).count() and \
                kpg.locator(f'{tid("whatif-execute")}:not([disabled])').count():
            kpg.click(tid("whatif-execute"))
            executed = True
        if kpg.locator(tid("whatif-option-delta-method")).count():
            kpg.click(tid("whatif-option-delta-method"))
        if kpg.locator(f'{tid("whatif-save-analysis")}:not([disabled])').count():
            break
        kpg.wait_for_timeout(1000)
    thread_id = kpg.url.rstrip("/").split("/what-if/thread/")[1].split("?")[0]
    kpg.wait_for_selector(f'{tid("whatif-save-analysis")}:not([disabled])', timeout=60_000)
    kpg.click(tid("whatif-save-analysis"))
    kpg.wait_for_selector(tid("ws-save-dialog"))
    title = f"Sweep oil -40% {time.strftime('%H%M%S')}"
    kpg.fill(tid("ws-save-title"), title)
    kpg.click(tid("ws-save-confirm"))
    kpg.wait_for_selector(tid("ws-save-done"), timeout=120_000)
    kpg.click(tid("ws-save-open"))
    wait_url(kpg, r".*/analyses/.*")
    kpg.wait_for_selector(tid("ws-analysis-figures"), timeout=60_000)
    aid = kpg.url.rstrip("/").split("/analyses/")[1].split("?")[0]
    saved = get(f"/analyses/{aid}", "khalid.alotaibi")
    th = _get_json(f"{WHATIF}/threads/{thread_id}")
    result = next(b["result"] for t in reversed(th["turns"]) for b in t["answer"]["blocks"] if b["type"] == "result")
    figs = {f["key"]: f["value"] for f in saved["answer"]["figures"]}
    s.check("saved title", saved["title"] == title and saved["origin"] == "whatif", title, saved["title"])
    s.check("scenario ECL equals the What-If thread's result", _close(figs["scenario_ecl"], result["cards"]["scenario_ecl"]),
            result["cards"]["scenario_ecl"], figs["scenario_ecl"])
    s.check("ECL change equals the What-If thread's result", _close(figs["change"], result["cards"]["change"]),
            result["cards"]["change"], figs["change"])
    s.check("on screen", _close(kpg.get_attribute(tid("ws-analysis-figure-change"), "data-value"), figs["change"]))
    kpg.go_back()
    kpg.wait_for_selector(tid("whatif-save-investigation"), timeout=60_000)
    kpg.click(tid("whatif-save-investigation"))
    kpg.wait_for_selector(tid("ws-save-dialog"))
    kpg.click(tid("ws-save-confirm"))
    kpg.wait_for_selector(tid("ws-save-done"), timeout=60_000)
    kpg.click(tid("ws-save-open"))
    wait_url(kpg, r".*/investigations/.*")
    kpg.wait_for_selector(tid("ws-conversation"), timeout=60_000)
    iid = kpg.url.rstrip("/").split("/investigations/")[1].split("?")[0]
    inv = get(f"/investigations/{iid}", "khalid.alotaibi")
    s.check("every What-If turn saved (question and answer)", len(inv["turns"]) == 2 * len(th["turns"]), 2 * len(th["turns"]),
            len(inv["turns"]))
    s.check("Continue returns to the What-If thread", inv["continue_href"] == f"/what-if/thread/{thread_id}",
            f"/what-if/thread/{thread_id}", inv["continue_href"])
    s.finish()

    s.start("corporate", "S3-2", "Early Warning: Save as investigation from the Construction level")
    kpg.goto(UI + "/early-warning?domain=corporate&segment=Construction", wait_until="domcontentloaded")
    kpg.wait_for_selector(tid("ews-save-investigation"), timeout=120_000)
    kpg.click(tid("ews-save-investigation"))
    kpg.wait_for_selector(tid("ws-save-dialog"))
    kpg.click(tid("ws-save-confirm"))
    kpg.wait_for_selector(tid("ws-save-done"), timeout=60_000)
    kpg.click(tid("ws-save-open"))
    wait_url(kpg, r".*/investigations/.*")
    kpg.wait_for_selector(tid("ws-conversation"), timeout=60_000)
    iid = kpg.url.rstrip("/").split("/investigations/")[1].split("?")[0]
    inv = get(f"/investigations/{iid}", "khalid.alotaibi")
    s.check("source is the Early Warning level", inv["source"]["type"] == "early-warning-level"
            and inv["continue_href"].startswith("/early-warning"), "/early-warning…", inv["continue_href"])
    s.check("headline figures and top reasons saved", {a["kind"] for a in inv["turns"][1]["artifacts"]} >= {"figures", "table"})
    s.finish()
    s.page = pg
    kctx.close()

    # ---------------------------------------------------- 7. Share, Add to report
    s.start("both", "S3-2", "Share an analysis through Mail (arrives in Sara's inbox); Share and Add to report open on investigations and projects")
    before = core_login.api_get("/api/v1/mail/counts", ck["sara.aldosari"])["unread"]
    pg.goto(UI + f"/analyses/{A_SECTOR}", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("ws-analysis-share"), timeout=90_000)
    pg.click(tid("ws-analysis-share"))
    pg.wait_for_selector(tid("share-dialog"))
    pg.fill(tid("share-to-input"), "sara")
    pg.click(f'{tid("share-to-options")} [data-username="sara.aldosari"]')
    pg.click(tid("share-send"))
    pg.wait_for_selector(tid("share-done"), timeout=30_000)
    pg.click(tid("share-finish"))
    s.check("Sara's unread count rose by one", core_login.api_get("/api/v1/mail/counts", ck["sara.aldosari"])["unread"] == before + 1)
    t0 = core_login.api_get("/api/v1/mail/threads?folder=inbox", ck["sara.aldosari"])["threads"][0]
    d = core_login.api_get(f"/api/v1/mail/threads/{t0['thread_id']}", ck["sara.aldosari"])
    o = d["messages"][0]["attachments"][0]["object"]
    s.check("the object is the analysis with its link", o["type"] == "analysis" and o["href"] == f"/analyses/{A_SECTOR}",
            f"/analyses/{A_SECTOR}", o.get("href"))
    pg.click(tid("ws-analysis-add-report"))
    pg.wait_for_selector(tid("add-report-dialog"))
    pg.wait_for_selector(f'{tid("add-report-new")}', timeout=30_000)
    s.check("Add to report: the dialog offers a new report and lists the editable ones",
            pg.locator(tid("add-report-new")).count() == 1 and pg.locator(tid("add-report-error")).count() == 0)
    section = get(f"/analyses/{A_SECTOR}/playbook-section")
    s.check("the section it would add has a table and key figures (Playbook contract)",
            {b["kind"] for b in section["section"]["blocks"]} >= {"table", "kpis"})
    pg.click(tid("add-report-close"))
    for path, share_id, report_id in ((f"/investigations/{INV_RETAIL}", "ws-investigation-share", "ws-investigation-add-report"),
                                      (f"/projects/{PRJ_CONSTRUCTION}", "ws-project-share", "ws-project-add-report")):
        pg.goto(UI + path, wait_until="domcontentloaded")
        pg.wait_for_selector(tid(share_id), timeout=90_000)
        pg.click(tid(share_id))
        pg.wait_for_selector(tid("share-dialog"))
        pg.click(tid("share-close"))
        pg.click(tid(report_id))
        pg.wait_for_selector(tid("add-report-dialog"))
        s.check(f"{path}: Share and Add to report open", pg.locator(tid("add-report-dialog")).count() == 1)
        pg.click(tid("add-report-close"))
    s.finish()

    s.start("both", "S3-2", "Back paths: analysis → Analyses, investigation → Investigations, project → Projects")
    for path, back in ((f"/analyses/{A_OIL}", "/analyses"), (f"/investigations/{INV_RETAIL}", "/investigations"),
                       (f"/projects/{PRJ_RETAIL}", "/projects")):
        # R7: Back is the exact previous screen; in a fresh tab (no previous screen) it is the item's list.
        tab = ctx.new_page()
        tab.goto(UI + path, wait_until="domcontentloaded")
        tab.wait_for_selector(tid("ws-back"), timeout=90_000)
        tab.click(tid("ws-back"))
        wait_url(tab, rf".*{re.escape(back)}$")
        s.check(f"Back from {path} (fresh tab)", tab.url.rstrip("/").endswith(back), back, tab.url)
        tab.close()
    s.finish()
    s.page = page
    ctx.close()
    octx.close()
