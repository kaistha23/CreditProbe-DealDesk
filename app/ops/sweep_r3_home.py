"""UAT sweep, PLAN_R3 S3-4: My workspace is each user's home page.

Imported by ops/uat_sweep.py (part "home"), which puts the repo on the path and passes the Sweep.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable

import core_login
from uat_sweep_core import cookie_of, tid, watch

EWS = "http://127.0.0.1:8501/api/v1/ews"
CORE = "http://127.0.0.1:8505/api/v1/workspace"
PERSONAS = ["anne", "faisal.alqahtani", "noura.alharbi", "khalid.alotaibi", "reem.alshehri", "abdullah.alzahrani",
            "sara.aldosari", "omar.alghamdi", "lama.almutairi"]


def _get(url: str, cookie: str) -> Any:
    req = urllib.request.Request(url, headers={"Cookie": f"cp_session={cookie}"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - loopback
        return json.loads(r.read())


def _value(page, testid: str) -> str:
    return page.inner_text(tid(f"{testid}-value")).strip()


def home_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    browser = page.context.browser

    s.start("both", "H1", "Sign-in with no page asked for lands on the Cockpit (R10 S1); My workspace is one click away")
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
    pg = ctx.new_page()
    watch(pg, s)
    s.page = pg
    pg.goto(UI + "/login", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("login-screen"), timeout=90_000)
    pg.wait_for_load_state("networkidle")
    for _ in range(5):          # a form filled before React hydrates keeps its button disabled: fill again
        pg.fill(tid("login-username"), "khalid.alotaibi")
        pg.fill(tid("login-password"), core_login.password_for("khalid.alotaibi"))
        if pg.locator(tid("login-submit")).is_enabled():
            break
        pg.wait_for_timeout(1000)
    pg.click(tid("login-submit"))
    # PLAN_R10 S1: sign-in lands on the Cockpit (/); the Workspace is under Work and in the user menu.
    pg.wait_for_url(lambda u: not u.rstrip("/").endswith("/login") and "/login?" not in u, timeout=90_000)
    s.check("landed on the Cockpit", pg.url.split("?")[0].rstrip("/") == UI.rstrip("/"), UI + "/", pg.url)
    pg.goto(UI + "/workspace", wait_until="domcontentloaded")
    # PLAN_R9 G4: /workspace opens on the Intelligence Briefing; the R3 home figures are the "My work" tab.
    pg.wait_for_selector(tid("ws-briefing"), timeout=90_000)
    pg.click(tid("ws-tab-workspace"))
    pg.wait_for_selector(tid("ws-home-overview"), timeout=90_000)

    s.start("corporate", "H2", "Home figures equal their sources: tasks, mentions, mail, Early Warning")
    cookie = cookie_of("khalid.alotaibi")
    h = _get(f"{CORE}/home", cookie)
    pg.wait_for_selector(f'{tid("ws-home-ews-corporate")}', timeout=90_000)
    s.check("tasks tile", _value(pg, "ws-home-tasks-count") == str(h["tasks"]["total"]), h["tasks"]["total"], _value(pg, "ws-home-tasks-count"))
    s.check("mentions tile", _value(pg, "ws-home-mentions-count") == str(h["mentions"]["unread"]), h["mentions"]["unread"],
            _value(pg, "ws-home-mentions-count"))
    s.check("mail tile", _value(pg, "ws-home-mail-count") == str(h["mail"]["unread"]), h["mail"]["unread"], _value(pg, "ws-home-mail-count"))
    s.check("projects tile", _value(pg, "ws-home-projects-count") == str(h["mine"]["counts"]["projects"]),
            h["mine"]["counts"]["projects"], _value(pg, "ws-home-projects-count"))
    lv = _get(f"{EWS}/level?domain=corporate", cookie)
    crit = lv["headline"]["critical"]
    s.check("Early Warning critical equals the level API", pg.inner_text(tid("ws-home-ews-corporate-critical")).replace(",", "") == str(crit),
            crit, pg.inner_text(tid("ws-home-ews-corporate-critical")))
    s.check("Early Warning critical tile", _value(pg, "ws-home-ews-count").replace(",", "") == str(crit), crit, _value(pg, "ws-home-ews-count"))
    s.check("Khalid covers corporate only: no retail panel", pg.locator(tid("ws-home-ews-retail")).count() == 0)
    s.check("unread mail rows listed", pg.locator(tid("ws-home-mail-row")).count() == len(h["mail"]["items"]),
            len(h["mail"]["items"]), pg.locator(tid("ws-home-mail-row")).count())
    s.check("reviews panel is shown (Playbook list or its unavailable note)", pg.locator(tid("ws-home-reviews")).count() == 1)

    s.start("corporate", "H3", "Every home row opens its page; browser Back returns to the home page")
    for testid in ("ws-home-ews-name", "ws-home-recent-row", "ws-home-mail-row", "ws-home-task", "ws-home-mention"):
        rows = pg.locator(tid(testid))
        if rows.count() == 0:
            continue
        href = rows.first.locator("a").get_attribute("href")
        rows.first.locator("a").click()
        pg.wait_for_url(lambda u, h=href: h.split("?")[0] in u, timeout=60_000)
        s.check(f"{testid}: opened {href}", href.split("?")[0] in pg.url, href, pg.url)
        pg.go_back()
        pg.wait_for_selector(tid("ws-home-overview"), timeout=90_000)
        s.check(f"{testid}: Back to My workspace", "/workspace" in pg.url, "/workspace", pg.url)
    pg.click(tid("ws-home-mentions-count"))
    pg.wait_for_selector(tid("ws-inbox"), timeout=60_000)
    s.check("the mentions tile opens the inbox on mentions", "kind=mention" in pg.url, "kind=mention", pg.url)
    s.finish()
    ctx.close()

    s.start("both", "H4", "Every persona has a home page that renders")
    for user in PERSONAS:
        c2 = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(c2, user)
        p2 = c2.new_page()
        watch(p2, s)
        s.page = p2
        p2.goto(UI + "/workspace?tab=work", wait_until="domcontentloaded")
        try:
            p2.wait_for_selector(tid("ws-home-overview"), timeout=90_000)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        s.check(f"{user}: home renders", ok)
        books = _get(f"{CORE}/home", cookie_of(user))["user"]["books"]
        if ok:
            for b in books:
                p2.wait_for_selector(tid(f"ws-home-ews-{b}"), timeout=90_000)
            s.check(f"{user}: Early Warning panels for {', '.join(books)}",
                    all(p2.locator(tid(f"ws-home-ews-{b}")).count() == 1 for b in books), books, "")
        c2.close()
    s.page = page
    s.finish()
