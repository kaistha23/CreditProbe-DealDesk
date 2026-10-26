"""UAT sweep, part `ai_work` (PLAN_R4 Session A2): Playbook AI, Project threads, Cockpit help.

Called from ops/uat_sweep.py (`--only ai_work`). Every figure on screen is checked against the service API or the
books (through backend/ai_work/tools.py, the tools the conversations use); every new control is clicked; each step
ends with no console error, no page error and no failed request; Back paths are walked. The sweep creates its own
report and project thread, named for the run, so it can be re-run and the seeded content stays as seeded.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

import core_login
from uat_sweep_core import as_user, cookie_of, tid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PB = "http://127.0.0.1:8506/api/v1/playbook"
WS = "/api/v1/workspace"
PRJ_RETAIL = "retail-stage2-review"


def _pb(path: str, cookie: str) -> Any:
    import json
    import urllib.request
    req = urllib.request.Request(PB + path, headers={"Cookie": f"cp_session={cookie}"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def _mn(v: float, places: int = 1) -> str:
    return f"SAR {v:,.{places}f}m"


def ai_work_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    from backend.ai_work import tools
    from backend.playbook_v5 import content

    browser = page.context.browser
    sara = cookie_of("sara.aldosari")
    ctx, pg, _ = as_user(browser, s, "sara.aldosari")

    # ------------------------------------------------------- 1. top chat
    s.start("corporate", "R4-A2-1", "Playbook top chat: 'I want to draft a corporate ECL report' discusses scope, "
                                    "proposes sections, takes a change and creates the report")
    pg.goto(UI + "/playbook", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("playbook-chat-input"), timeout=180_000)
    s.check("the chat offers the ECL report as a starting point",
            pg.locator(tid("playbook-chat-suggestion"), has_text="I want to draft a corporate ECL report").count() == 1)
    pg.fill(tid("playbook-chat-input"), "I want to draft a corporate ECL report")
    pg.click(tid("playbook-chat-send"))
    pg.wait_for_selector(tid("playbook-proposal"), timeout=120_000)
    reply = pg.locator(tid("playbook-chat-message")).nth(1).inner_text()
    now, before = content.corp_totals(), content.corp_totals(content.CORP_PRIOR)
    s.check("the reply quotes corporate ECL from the books", content.mn_words(now["ecl"]) in reply,
            content.mn_words(now["ecl"]), reply[:200])
    s.check("and the quarter's movement", content.mn_words(now["ecl"] - before["ecl"]) in reply)
    card = pg.locator(tid("playbook-proposal")).last.inner_text()
    s.check("the proposal lists the ECL sections",
            all(x in card for x in ("ECL overview", "Stage migration", "ECL by sector", "Early Warning")), "", card[:300])
    pg.fill(tid("playbook-chat-input"), "Add a section on concentrations")
    pg.click(tid("playbook-chat-send"))
    pg.wait_for_function("document.querySelectorAll('[data-testid=playbook-proposal]').length >= 2", timeout=120_000)
    s.check("the change is in the new proposal", "Concentrations" in pg.locator(tid("playbook-proposal")).last.inner_text())
    pg.fill(tid("playbook-chat-input"), "What is ECL by sector?")
    pg.click(tid("playbook-chat-send"))
    pg.wait_for_function("document.querySelectorAll('[data-testid=playbook-answer-blocks]').length >= 1", timeout=120_000)
    top = tools.book_figures("corporate", by="sector", measures=["ecl"]).table["rows"][0]
    blocks = pg.locator(tid("playbook-answer-blocks")).last.inner_text()
    s.check("a question is answered from the books with a table", top["sector"] in blocks, top["sector"], blocks[:200])
    pg.locator(tid("playbook-proposal-create")).last.click()
    pg.wait_for_url("**/playbook?report=*", timeout=180_000)
    pg.wait_for_selector(tid("playbook-section"), timeout=120_000)
    rid = pg.url.split("report=")[1].split("&")[0]
    rep = _pb(f"/reports/{rid}", sara)
    titles = [x["title"] for x in rep["sections"]]
    s.check("the report is created with the proposed sections", "Concentrations" in titles and "ECL overview" in titles,
            "", titles)
    s.check("its sections are drafted from the books", sum(1 for x in rep["sections"] if x["blocks"]) >= len(titles) - 1)

    # -------------------------------------------------- 2. section threads
    s.start("corporate", "R4-A2-2", "Section assistant: Early Warning section reads Early Warning, lists named "
                                    "clients, adds the answer to the section")
    ews_i = titles.index("Early Warning")
    sec = pg.locator(tid("playbook-section")).nth(ews_i)
    sec.locator(tid("playbook-section-thread-toggle")).click()
    sec.locator(tid("playbook-section-thread-body")).wait_for(timeout=60_000)
    s.check("the thread names its data", "Early Warning data" in sec.locator(tid("playbook-section-thread")).inner_text())
    sec.locator(tid("playbook-section-thread-chip"), has_text="What should go in this section?").click()
    sec.locator(tid("playbook-section-message")).nth(1).wait_for(timeout=120_000)
    brainstorm = sec.locator(tid("playbook-section-message")).nth(1).inner_text()
    hl = tools.ews_headline("corporate")
    s.check("brainstorm: a checklist grounded in the Early Warning headline",
            "named list" in brainstorm.lower() and f"{hl.figures[0]['value']:,}" in brainstorm, "", brainstorm[:300])
    sec.locator(tid("playbook-section-thread-input")).fill("Who are the 5 critical borrowers?")
    sec.locator(tid("playbook-section-thread-send")).click()
    sec.locator(tid("playbook-section-message")).nth(3).wait_for(timeout=120_000)
    want = tools.ews_clients("corporate", ["critical"], n=5).table["rows"]
    got = sec.locator(tid("playbook-answer-blocks")).last.inner_text()
    s.check("the five critical names are the Early Warning release's", all(r["id"] in got for r in want),
            [r["id"] for r in want], got[:300])
    n0 = len(_pb(f"/reports/{rid}", sara)["sections"][ews_i]["blocks"])
    sec.locator(tid("playbook-answer-apply")).last.click()
    deadline = time.time() + 60
    while time.time() < deadline and len(_pb(f"/reports/{rid}", sara)["sections"][ews_i]["blocks"]) == n0:
        time.sleep(1)
    s.check("Add to section puts the answer and its table into the section",
            len(_pb(f"/reports/{rid}", sara)["sections"][ews_i]["blocks"]) > n0)

    s.start("corporate", "R4-A2-3", "Section assistant: the scenario section imports a worked What-If scenario with "
                                    "its waterfall")
    sc_i = next(i for i, t in enumerate(titles) if "Scenario" in t)
    sec = pg.locator(tid("playbook-section")).nth(sc_i)
    sec.locator(tid("playbook-section-thread-toggle")).click()
    sec.locator(tid("playbook-section-thread-input")).fill("Import the oil price shock scenario")
    sec.locator(tid("playbook-section-thread-send")).click()
    sec.locator(tid("playbook-section-message")).nth(1).wait_for(timeout=180_000)
    s.check("the thread says what it imported", "waterfall" in sec.locator(tid("playbook-section-message")).nth(1).inner_text())
    secd = _pb(f"/reports/{rid}", sara)["sections"][sc_i]
    wf = [b for b in secd["blocks"] if b["kind"] == "chart" and b["figure"]["data"][0].get("type") == "waterfall"]
    oil = tools.whatif_scenario("corporate", "oil-shock")
    f = {x["key"]: x["value"] for x in oil.figures}
    s.check("the waterfall is in the section", len(wf) == 1)
    s.check("its commentary quotes the engine's ECL change",
            f"SAR {f['change']:,.1f}m" in secd["blocks"][-4]["text"] if len(secd["blocks"]) >= 4 else False)
    pg.wait_for_function(f"document.querySelectorAll('[data-testid=playbook-section]')[{sc_i}]"
                         ".querySelector('.js-plotly-plot') !== null", timeout=60_000)
    s.check("the chart is drawn", True)

    s.start("corporate", "R4-A2-4", "Right-hand assistant: a conversation over the whole report; the chips stay as shortcuts")
    pg.fill(tid("playbook-thread-input"), "Which sectors carry the most ECL?")
    pg.click(tid("playbook-thread-send"))
    pg.wait_for_function("document.querySelectorAll('[data-testid=playbook-thread] [data-testid=playbook-answer-blocks]').length >= 1",
                         timeout=120_000)
    side = pg.locator(tid("playbook-thread")).inner_text()
    s.check("the answer names the sector with the most ECL", top["sector"] in side)
    s.check("the suggestion chips are still offered", pg.locator(tid("playbook-thread-suggestion")).count() >= 1)
    # R7: Back is the exact previous screen: the report was created from the Playbook assistant's thread, so Back
    # returns to that thread, and its Back to the Playbook home.
    pg.locator(tid("playbook-back")).first.click()
    pg.wait_for_function("() => !/report=/.test(location.search)", timeout=60_000)
    s.check("Back leaves the report for the screen it was opened from", "/playbook" in pg.url and "report=" not in pg.url,
            "/playbook (thread or home)", pg.url)
    if "thread=" in pg.url:
        pg.click(tid("playbook-thread-back"))
    pg.wait_for_selector(tid("playbook-home"), timeout=60_000)
    s.check("Back again returns to the Playbook home", "/playbook" in pg.url and "thread=" not in pg.url and "report=" not in pg.url)
    ctx.close()

    # ------------------------------------------------------ 3. project thread
    s.start("retail", "R4-A3-1", "Project thread: '5 high-alert Early Warning clients in Stage 1' returns a table "
                                 "through the forked Cockpit agent; Back returns to the project")
    ctx, pg, _ = as_user(browser, s, "omar.alghamdi")
    omar = cookie_of("omar.alghamdi")
    th = core_login.api_post(f"{WS}/projects/{PRJ_RETAIL}/threads", {"title": f"Sweep {time.strftime('%H%M%S')}"}, omar)
    pg.goto(f"{UI}/projects/{PRJ_RETAIL}/threads/{th['id']}", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("ws-thread-input"), timeout=120_000)
    pg.fill(tid("ws-thread-input"), "Give me a list of 5 high-alert Early Warning clients who are in Stage 1")
    pg.click(tid("ws-thread-send"))
    pg.wait_for_selector(tid("ws-thread-table-row"), timeout=120_000)
    rows = pg.locator(tid("ws-thread-table-row"))
    want = tools.ews_clients("retail", ["high", "critical"], stage=1, n=5).table["rows"]
    seen = [rows.nth(i).inner_text() for i in range(rows.count())]
    s.check("five rows", rows.count() == 5, 5, rows.count())
    s.check("IDs, bands and EAD are the Early Warning release's",
            all(w["id"] in r and w["band"] in r and _mn(w["ead"], 2 if w["ead"] < 10 else 1) in r
                for w, r in zip(want, seen)), [w["id"] for w in want], seen[:2])
    s.check("each row carries its reasons", all(len(r.split("\t")[-1]) > 10 for r in seen))
    pg.fill(tid("ws-thread-input"), "What is corporate ECL?")
    pg.click(tid("ws-thread-send"))
    pg.wait_for_selector(tid("ws-thread-refusal"), timeout=120_000)
    s.check("a question outside the project's domains is refused, naming the scope",
            "This project only uses" in pg.locator(tid("ws-thread-msg-assistant")).last.inner_text())

    s.start("retail", "R4-A4-1", "Help: 'How does What-If work?' gives the flow with links and a worked example on the "
                                 "books; the link opens the screen")
    pg.fill(tid("ws-thread-input"), "How does What-If work?")
    pg.click(tid("ws-thread-send"))
    pg.wait_for_function("document.querySelectorAll('[data-testid=ws-thread-msg-assistant]').length >= 3", timeout=120_000)
    helptext = pg.locator(tid("ws-thread-msg-assistant")).last.inner_text()
    s.check("the flow, step by step", "The flow, step by step" in helptext and "Execute scenario" in helptext)
    s.check("the worked example quotes the engine's scenario ECL", f"SAR {f['scenario_ecl']:,.1f}m" in helptext)
    link = pg.locator(tid("ws-thread-msg-assistant")).last.locator("a", has_text="Open What-If").first
    s.check("the step links to What-If", link.count() == 1)
    link.click()
    pg.wait_for_url("**/what-if**", timeout=60_000)
    s.check("the link opens What-If", "/what-if" in pg.url)
    pg.go_back()
    pg.wait_for_selector(tid("ws-back"), timeout=60_000)
    pg.click(tid("ws-back"))
    pg.wait_for_url(f"**/projects/{PRJ_RETAIL}", timeout=60_000)
    s.check("Back returns to the project", pg.url.endswith(f"/projects/{PRJ_RETAIL}"))
    ctx.close()
