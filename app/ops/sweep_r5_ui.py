"""UAT sweep, part `r5-ui` (PLAN_R5 Session P): navigation, tables in Playbook, merging into a section.

Called from ops/uat_sweep.py (`--only r5-ui`). Early Warning P4 is checked in the `r4-ews` part and the sector
drill (the rating chart only at View by = Rating). Each step ends with no console error, no page error and no failed
request. The sweep creates its own report, named for the run, so the seeded content stays as seeded.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from uat_sweep_core import as_user, cookie_of, tid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PB = "http://127.0.0.1:8506/api/v1/playbook"
NAV = 'nav[aria-label="Primary"]'

TABLE_MD = ("Rating mix at 2026Q2:\n\n| Rating grade | Borrowers | % EAD | % ECL |\n|---|---|---|---|\n"
            "| AA to A- | 677 | 12.0% | 1.7% |\n| CCC and below | 408 | 7.9% | 49.9% |")
FRAMING = ("The headline for the section", "Proposed wording", "Detail worth naming", "Suggested chart")


def _pb(path: str, cookie: str, method: str = "GET", body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PB + path, data=data, method=method,
                                 headers={"Cookie": f"cp_session={cookie}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def _groups(nav_text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = ""
    for x in [y.strip() for y in nav_text.splitlines() if y.strip()]:
        if x.upper() in ("HOME", "FUNCTIONALITIES", "WORK", "INTELLIGENCE", "DATA", "BUILD", "GOVERN", "ADMIN") and x == x.upper():
            cur = x
            out[cur] = []
        elif cur and not x.isdigit():          # the Mail unread badge is a number, not a link
            out[cur].append(x)
    return out


def r5_ui_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    browser = page.context.browser

    # ------------------------------------------------------------ P1 navigation
    s.start("both", "R5-P1", "Navigation: Playbook and Lenses under Intelligence, Policy Docs in Work, Admin at the bottom")
    ctx, pg, _ = as_user(browser, s, "anne")
    pg.goto(UI + "/workspace", wait_until="domcontentloaded")
    pg.wait_for_function("() => (document.querySelector('nav[aria-label=\"Primary\"]')||{}).innerText?.includes('Audit log')",
                         timeout=120_000)
    g = _groups(pg.locator(NAV).first.inner_text())
    # PLAN_R10 S1 supersedes the R5/R9 grouping: Home = Cockpit, Intelligence, Work, Data, Admin.
    s.check("Home", g.get("HOME") == ["Cockpit"], "Cockpit", g.get("HOME"))
    s.check("Intelligence", g.get("INTELLIGENCE") == ["Early Warning", "Borrower 360", "What-If", "Lenses", "Scorecard", "BRF"],
            "", g.get("INTELLIGENCE"))
    s.check("Work", g.get("WORK") == ["Workspace", "Mail", "Deal Desk", "Playbook", "Policy Docs", "Projects", "Investigations",
                                      "Analyses"], "Workspace … Analyses", g.get("WORK"))
    s.check("Admin is the last group, with its six pages", list(g)[-1:] == ["ADMIN"] and g["ADMIN"] == [
        "Workflow", "Users & Teams", "Agent Operations", "AI Studio", "Settings", "Audit log"], "", g.get("ADMIN"))
    pg.locator(NAV).get_by_role("link", name="Playbook").click()
    pg.wait_for_url("**/playbook*", timeout=60_000)
    s.check("Playbook opens from Work", "/playbook" in pg.url, "/playbook", pg.url)
    ctx.close()

    s.start("both", "R5-P1", "Navigation: a user who is not an administrator sees no Admin group")
    ctx, pg, _ = as_user(browser, s, "sara.aldosari")
    pg.goto(UI + "/workspace", wait_until="domcontentloaded")
    pg.wait_for_function("() => (document.querySelector('nav[aria-label=\"Primary\"]')||{}).innerText?.includes('Playbook')",
                         timeout=120_000)
    pg.wait_for_timeout(1500)
    g = _groups(pg.locator(NAV).first.inner_text())
    s.check("no Admin group", "ADMIN" not in g, "no ADMIN", list(g))
    ctx.close()

    # ------------------------------------------------------------ P2 tables
    sara = cookie_of("sara.aldosari")
    stamp = time.strftime("%H%M%S")
    rid = _pb("/reports", sara, "POST", {"title": f"R5 sweep {stamp}", "template": "portfolio-review",
                                         "book": "corporate", "period": "2026Q2"})["id"]
    rep = _pb(f"/reports/{rid}", sara)
    sid = rep["sections"][0]["id"]
    title = rep["sections"][0]["title"]
    _pb(f"/reports/{rid}/sections/{sid}", sara, "PUT", {"blocks": [
        {"kind": "paragraph", "text": "Corporate ECL rose on the quarter, led by the B and BB grades."},
        {"kind": "paragraph", "text": TABLE_MD}]})

    s.start("corporate", "R5-P2", "Playbook: a table in a section's text is a real house-style table, never raw pipes")
    ctx, pg, _ = as_user(browser, s, "sara.aldosari")
    pg.goto(f"{UI}/playbook?report={rid}", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("playbook-section"), timeout=120_000)
    sec = pg.locator(tid("playbook-section")).first
    body = sec.inner_text()
    s.check("the section shows a table", sec.locator(f'{tid("playbook-markdown")} table').count() == 1)
    s.check("no raw pipes", "|---" not in body and "| AA to A-" not in body, "no pipes", body[:200])
    heads = sec.locator(f'{tid("playbook-markdown")} th').all_inner_texts()
    s.check("headers in plain words", [h.strip().upper() for h in heads] == ["RATING GRADE", "BORROWERS", "% EAD", "% ECL"],
            "Rating grade, Borrowers, % EAD, % ECL", heads)

    # ------------------------------------------------------------ P2 + P3 in the section thread
    s.start("corporate", "R5-P3", "Section assistant: the answer's table renders as a table; Add to section merges the "
                                  "proposal only; Undo restores the section and shows in Versions")
    sec.locator(tid("playbook-section-thread-toggle")).click()
    sec.locator(tid("playbook-section-thread-body")).wait_for(timeout=60_000)
    sec.locator(tid("playbook-section-thread-input")).fill("ECL by sector")
    sec.locator(tid("playbook-section-thread-send")).click()
    sec.locator(tid("playbook-section-message")).nth(1).wait_for(timeout=180_000)
    thread = sec.locator(tid("playbook-section-thread-body")).inner_text()
    s.check("the thread shows no raw pipes", "|---" not in thread and "\n| " not in thread, "no pipes", thread[:200])
    s.check("the answer carries a table", sec.locator(f'{tid("playbook-section-thread-body")} table').count() >= 1)
    before = _pb(f"/reports/{rid}", sara)["sections"][0]["blocks"]
    sec.locator(tid("playbook-answer-apply")).last.click()
    sec.locator(tid("playbook-merged")).wait_for(timeout=60_000)
    after = _pb(f"/reports/{rid}", sara)["sections"][0]["blocks"]
    s.check("the proposal is merged at the end", len(after) > len(before)
            and [b["text"] for b in after[:2]] == [b["text"] for b in before[:2]], f"> {len(before)} blocks", len(after))
    txt = json.dumps(after[len(before):], ensure_ascii=False)
    s.check("no framing and no pipes in what was merged", not any(f in txt for f in FRAMING) and "|---" not in txt
            and "\\n> " not in txt, "clean", [f for f in FRAMING if f in txt])
    heads = [b["text"] for b in after if b["kind"] == "heading"]
    s.check("no duplicate headings", len(heads) == len(set(heads)) and title not in heads, "unique", heads)
    s.check("the merged table is a table block", any(b["kind"] == "table" for b in after[len(before):]))
    vs = _pb(f"/reports/{rid}/versions", sara)["versions"]
    s.check("the merge is one version", vs[0]["action"] == "assistant-merge", "assistant-merge", vs[0]["action"])
    sec.locator(tid("playbook-merge-undo")).click()
    pg.wait_for_function("() => (document.querySelector('[data-testid=playbook-merged]')||{}).innerText?.includes('Undone')",
                         timeout=60_000)
    restored = _pb(f"/reports/{rid}", sara)["sections"][0]["blocks"]
    s.check("one undo restores the section", [(b["kind"], b.get("text")) for b in restored]
            == [(b["kind"], b.get("text")) for b in before], len(before), len(restored))
    vs = _pb(f"/reports/{rid}/versions", sara)["versions"]
    s.check("the undo shows in Versions", vs[0]["action"] == "undo", "undo", vs[0]["action"])
    ctx.close()
