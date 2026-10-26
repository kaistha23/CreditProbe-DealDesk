"""UAT sweep, PLAN_R5 Session A (part "admin"). Imported by ops/uat_sweep.py (`--only admin`), which passes the Sweep.

Every Admin page, tab, control and Back path, signed in as the Administrator, with every figure checked against the
Admin API and the access figures checked against the books themselves (pandas over the lake and the Branches and RMs
domain, independently of the services). Then View as an RM: the module guard, and the B360 list and EWS customers
restricted to his portfolio. Each step ends with no console error, no page error and no failed request (the Sweep),
and with no known loose-text phrase (ops/loose_text_scan.KNOWN). Changes the sweep drafts are withdrawn, so the
seeded state stays as seeded.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import core_login
from loose_text_scan import scan_page

V5 = Path(__file__).resolve().parents[1]
ADM = "http://127.0.0.1:8510"
LAKE = V5 / "data" / "cockpit_v4_lake"
BR = V5 / "data" / "branches" / "branch-saudi-v1"


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def _call(path: str, cookie: str, method: str = "GET", body: Any = None, base: str = ADM) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Cookie": f"cp_session={cookie}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - loopback
        return json.loads(r.read())


def _rm_portfolio(rm: str) -> set[str]:
    """RM0005's borrowers from the Branches and RMs domain, read with pandas (independent of backend/access)."""
    b = pd.read_parquet(BR / "branch_corporate_quarter.parquet", columns=["borrower_id", "reporting_quarter", "rm_id"])
    b = b.sort_values("reporting_quarter").drop_duplicates("borrower_id", keep="last")
    c = pd.read_parquet(LAKE / "v4-saudi-corporate-20q-v4" / "corp_borrower_quarter.parquet", columns=["borrower_id"])
    return set(b[b["rm_id"] == rm]["borrower_id"]) & set(c["borrower_id"])


def _loose(s, page) -> None:
    inv = scan_page(page)
    s.check("no known loose-text phrase", not inv["known"], "none", inv["known"][:2])


def admin_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    # The browser's own session (View as is set on it), else a fresh sign-in.
    cookie = next((c["value"] for c in page.context.cookies() if c["name"] == "cp_session"), "") or core_login.login("anne")["cookie"]
    rm = "nawaf.alotaibi"
    mine = _rm_portfolio("RM0005")
    made: list[str] = []
    try:
        _steps(s, page, UI, wait_for, cookie, rm, mine, made)
    finally:
        for cid in made:
            try:
                _call(f"/api/v1/admin/changes/{cid}/withdraw", cookie, "POST", {})
            except Exception:  # noqa: BLE001
                pass
        try:
            _call("/api/v1/auth/view-as", cookie, "POST", {"username": None}, base=core_login.CORE)
        except Exception:  # noqa: BLE001
            pass


def _steps(s, page, UI, wait_for, cookie, rm, mine, made) -> None:
    # ---------------------------------------------------------------- A1 data access
    pols = _call("/api/v1/admin/objects/policy", cookie)
    s.start("both", "R5-A1-1", "Workflow opens on Data access: the live policies, the changes waiting, View as an RM")
    page.goto(UI + "/workflow", wait_until="domcontentloaded")
    wait_for(page, r".*/workflow$")
    page.wait_for_selector(tid("policy-card"), timeout=90_000)
    cards = page.locator(tid("policy-card"))
    s.check("one card per live policy", cards.count() == len(pols["objects"]), len(pols["objects"]), cards.count())
    s.check("the Riyadh RM policy is shown", page.locator(f'{tid("policy-card")}[data-id="POL-RM-OWN"]').count() == 1)
    pend = [c for c in pols["changes"] if c["status"] in ("draft", "submitted")]
    s.check("changes in progress listed", page.locator(tid("change-row")).count() == len(pend), len(pend), page.locator(tid("change-row")).count())
    page.wait_for_selector(f'{tid("view-as-preview")}[data-user="{rm}"]', timeout=60_000)
    corp = page.locator(f'{tid("view-as-book")}[data-book="corporate"]')
    s.check("View as Nawaf: his borrowers only, as the books give them", corp.get_attribute("data-customers") == str(len(mine)),
            len(mine), corp.get_attribute("data-customers"))
    s.check("View as Nawaf: no retail book", page.locator(f'{tid("view-as-book")}[data-book="retail"]').get_attribute("data-visible") == "false")
    s.check("modules he cannot open are marked", "No What-If" in page.locator(tid("view-as-modules")).inner_text())
    rows = page.locator(f'{tid("view-as-sample")} tbody tr')
    ids = [rows.nth(i).locator("td").first.inner_text().strip() for i in range(rows.count())]
    s.check("every sample row is in his portfolio", ids and set(ids) <= mine, "subset of RM0005", ids[:3])
    _loose(s, page)

    s.start("both", "R5-A1-2", "View as the auditor: names masked, no export, no approval")
    page.select_option(tid("view-as-user"), "hind.alsubaie")
    page.wait_for_selector(f'{tid("view-as-preview")}[data-user="hind.alsubaie"]', timeout=60_000)
    txt = page.locator(tid("view-as-preview")).inner_text()
    s.check("names withheld in the sample", "Name withheld" in txt)
    s.check("export and approval refused", "No Export" in txt and "No Approve" in txt)

    s.start("both", "R5-A1-3", "New policy: the editor previews the rows a user would see; save as draft, then withdraw")
    page.locator(tid("policy-new")).click()
    page.wait_for_selector(tid("policy-editor"))
    page.fill(tid("policy-name"), "Sweep: Makkah desk")
    page.locator(tid("policy-book-retail")).click()
    page.locator(f'{tid("policy-corporate-regions")}:has-text("Makkah")').first.click()
    page.select_option(tid("policy-preview-user"), "sara.aldosari")
    page.wait_for_function("() => document.querySelectorAll('[data-testid=\"policy-preview-book\"]').length === 2", timeout=30_000)
    page.wait_for_timeout(800)
    want = _call("/api/v1/admin/access/preview-draft", cookie, "POST", {"username": "sara.aldosari", "body": {
        "name": "x", "books": ["corporate", "retail"], "scope": {"corporate": {"regions": ["Makkah"]}}}})
    got = page.locator(f'{tid("policy-preview-book")}[data-book="corporate"]').get_attribute("data-customers")
    c = pd.read_parquet(LAKE / "v4-saudi-corporate-20q-v4" / "corp_borrower_quarter.parquet", columns=["borrower_id", "reporting_quarter", "region"])
    c = c.sort_values("reporting_quarter").drop_duplicates("borrower_id", keep="last")
    s.check("preview equals the API and the books", got == str(want["books"]["corporate"]["customers"]) == str(int((c["region"] == "Makkah").sum())),
            int((c["region"] == "Makkah").sum()), got)
    page.locator(tid("policy-save")).click()
    page.wait_for_selector(f'{tid("change-row")}[data-status="draft"]', timeout=30_000)
    drafts = [x for x in _call("/api/v1/admin/changes?status=draft&kind=policy", cookie)["changes"] if x["title"].endswith("Sweep: Makkah desk")]
    s.check("the draft is in the maker-checker queue", len(drafts) == 1)
    made.extend(d["change_id"] for d in drafts)
    row = page.locator(f'{tid("change-row")}[data-id="{drafts[0]["change_id"]}"]') if drafts else None
    if row is not None:
        row.locator(tid("change-withdraw")).click()
        page.wait_for_function(f"() => !document.querySelector('[data-testid=\"change-row\"][data-id=\"{drafts[0]['change_id']}\"]')", timeout=30_000)
        s.check("withdrawn: it leaves the queue", True)

    s.start("both", "R5-A1-4", "Edit a policy opens the editor on it; Cancel closes it")
    page.locator(f'{tid("policy-card")}[data-id="POL-AUDIT"] {tid("policy-edit")}').click()
    page.wait_for_selector(tid("policy-editor"))
    s.check("editor carries the policy", page.input_value(tid("policy-name")) == "Auditor read-only, names masked")
    s.check("masking is on", page.locator(tid("policy-mask-name")).get_attribute("aria-pressed") == "true")
    page.locator(tid("policy-cancel")).click()
    s.check("closed", page.locator(tid("policy-editor")).count() == 0)

    # ---------------------------------------------------------------- A1 workflows
    wfs = _call("/api/v1/admin/objects/workflow", cookie)["objects"]
    s.start("both", "R5-A1-5", "Approval workflows: step cards per workflow; simulate the Critical EWS route on a real name")
    page.locator(tid("admin-tab-workflows")).click()
    wait_for(page, r".*/workflow\?tab=workflows$")
    page.wait_for_selector(tid("workflow-card"))
    s.check("one card per workflow", page.locator(tid("workflow-card")).count() == len(wfs), len(wfs), page.locator(tid("workflow-card")).count())
    for w in wfs:
        n = page.locator(f'{tid("workflow-card")}[data-id="{w["id"]}"] {tid("workflow-step")}').count()
        s.check(f"{w['id']}: one card per step", n == len(w["body"]["steps"]), len(w["body"]["steps"]), n)
    card = page.locator(f'{tid("workflow-card")}[data-id="WF-EWS-CRIT"]')
    card.locator(tid("workflow-simulate")).click()
    page.wait_for_selector(tid("workflow-sim-row"))
    chosen = page.locator(f'{tid("workflow-card")}[data-id="WF-EWS-CRIT"] {tid("workflow-sim-object")}').input_value()
    obj = next(x for x in _call("/api/v1/admin/workflows/samples", cookie)["samples"]["ews_name"] if x["id"] == chosen)
    sim = _call("/api/v1/admin/workflows/simulate", cookie, "POST", {"workflow_id": "WF-EWS-CRIT", "object": obj})
    first = page.locator(tid("workflow-sim-row")).first.inner_text()
    s.check("the first step goes to the borrower's RM with its due date", sim["timeline"][0]["assignee"] in first and sim["timeline"][0]["due"] in first,
            sim["timeline"][0], first)
    s.check("escalation to the Head of Credit after 10 days", "Noura Al-Harbi" in first)
    dd = page.locator(f'{tid("workflow-card")}[data-id="WF-DD-DOA"]')
    dd.locator(tid("workflow-simulate")).click()
    page.wait_for_timeout(1500)
    s.check("the Deal Desk route names a DOA level", "DOA level" in dd.inner_text())

    s.start("both", "R5-A1-6", "Edit a workflow: the editor previews the step cards and simulates them; Cancel")
    card.locator(tid("workflow-edit")).click()
    page.wait_for_selector(tid("workflow-editor"))
    s.check("steps in the editor", page.locator(tid("workflow-edit-step")).count() == len(next(w for w in wfs if w["id"] == "WF-EWS-CRIT")["body"]["steps"]))
    page.locator(tid("workflow-step-add")).click()
    s.check("a step can be added", page.locator(tid("workflow-edit-step")).count() == len(next(w for w in wfs if w["id"] == "WF-EWS-CRIT")["body"]["steps"]) + 1)
    page.locator(tid("workflow-cancel")).click()

    s.start("both", "R5-A1-7", "Live items: the open workflow items, overdue flagged")
    items = _call("/api/v1/admin/workflows/items", cookie)["items"]
    page.locator(tid("admin-tab-items")).click()
    page.wait_for_selector(tid("item-row"))
    s.check("one row per open item", page.locator(tid("item-row")).count() == len(items), len(items), page.locator(tid("item-row")).count())

    # ---------------------------------------------------------------- G4 assistant
    s.start("both", "R5-G4-1", "Admin assistant: 'Critical EWS names need an RM action plan within 5 days, escalate after 10' drafts the workflow")
    page.locator(tid("admin-tab-access")).click()
    page.locator(tid("admin-assistant-open")).click()
    page.locator(tid("admin-assistant-seed")).first.click()
    page.wait_for_selector(tid("admin-draft-card"), timeout=120_000)
    txt = page.locator(tid("admin-draft-card")).first.inner_text()
    s.check("a draft workflow card", "Draft workflow" in txt.title() or "DRAFT WORKFLOW" in txt.upper())
    s.check("5 days, escalates after 10", "5 days" in txt and "escalates after 10" in txt, "5 days / 10", txt[:200])
    page.locator(tid("admin-draft-save")).first.click()
    page.wait_for_selector(tid("admin-draft-msg"))
    m = re.search(r"(CH-[0-9A-F]+)", page.locator(tid("admin-draft-msg")).inner_text())
    s.check("saved as a draft change", bool(m))
    if m:
        made.append(m.group(1))
    page.locator(tid("admin-assistant-close")).click()

    # ---------------------------------------------------------------- A2 users
    page.wait_for_selector(tid("view-as-preview"), timeout=60_000)   # nothing left loading when the page is left
    us = _call("/api/v1/admin/users", cookie)
    s.start("both", "R5-A2-1", "Users and Teams: every user with role, team and policies; Teams, Roles, RM hierarchy")
    page.goto(UI + "/users", wait_until="domcontentloaded")
    page.wait_for_selector(tid("user-row"))
    s.check("12 users", page.locator(tid("user-row")).count() == len(us["users"]) == 12, 12, page.locator(tid("user-row")).count())
    s.check("Nawaf carries the RM policy", "Riyadh RMs see only their portfolio" in page.locator(f'{tid("user-row")}[data-user="{rm}"]').inner_text())
    for t, testid, n in (("teams", "team-card", len(us["teams"])), ("roles", "role-card", len(us["roles"]))):
        page.locator(tid(f"admin-tab-{t}")).click()
        page.wait_for_selector(tid(testid))
        s.check(f"{t}: one card each", page.locator(tid(testid)).count() == n, n, page.locator(tid(testid)).count())
    page.locator(tid("admin-tab-rms")).click()
    page.wait_for_selector(tid("rm-branch"))
    s.check("RM hierarchy by branch", page.locator(tid("rm-branch")).count() > 5 and "RM0005" in page.locator(tid("rm-tree")).inner_text())
    page.go_back()
    wait_for(page, r".*/workflow(\?tab=\w+)?$")
    page.wait_for_selector(tid("view-as-preview"), timeout=60_000)
    s.check("Back returns to Workflow", True)
    page.go_forward()
    wait_for(page, r".*/users(\?tab=\w+)?$")
    page.wait_for_selector(tid("admin-users"))
    s.check("Forward returns to Users and Teams", True)

    # ---------------------------------------------------------------- A3 agent ops
    runs = _call("/api/v1/admin/agent-ops/runs", cookie)
    s.start("both", "R5-A3-1", "Agent Operations: the live log, a run's full trace, failures and refusals")
    page.goto(UI + "/agent-operations", wait_until="domcontentloaded")
    page.wait_for_selector(tid("agentops-run"))
    s.check("KPI runs equals the API", re.sub(r"\D", "", page.locator(tid("kpi-runs")).inner_text()) == str(runs["total"]),
            runs["total"], page.locator(tid("kpi-runs")).inner_text())
    page.locator(tid("agentops-run")).first.click()
    page.wait_for_selector(tid("agentops-trace"))
    s.check("the trace shows each step with a time bar", page.locator(tid("agentops-step")).count() >= 3)
    page.locator(tid("agentops-trace-close")).click()
    page.select_option(tid("agentops-module"), "deal_desk")
    page.wait_for_timeout(1200)
    dd = _call("/api/v1/admin/agent-ops/runs?module=deal_desk", cookie)
    s.check("module filter", page.locator(tid("agentops-run")).count() == len(dd["runs"]), len(dd["runs"]), page.locator(tid("agentops-run")).count())
    page.select_option(tid("agentops-module"), "")
    page.locator(tid("admin-tab-queue")).click()
    page.wait_for_selector(tid("agentops-run"))
    try:   # the list re-renders when the tab and the module filter settle
        page.wait_for_function("() => [...document.querySelectorAll('[data-testid=\"agentops-run\"] td:last-child')]"
                               ".every(e => e.innerText.trim() !== 'completed')", timeout=20_000)
    except Exception:  # noqa: BLE001 - the check below reports what is on screen
        pass
    outs = page.locator(f'{tid("agentops-run")} td:last-child').all_inner_texts()
    s.check("the queue holds only failures and refusals", outs and all(o.strip() != "completed" for o in outs), "refused/failed", outs[:3])

    s.start("both", "R5-A3-2", "Agent Operations: daily charts (runs, latency p50/p95, cost, refusal rate by module)")
    page.locator(tid("admin-tab-charts")).click()
    page.wait_for_selector(tid("agentops-charts"))
    page.wait_for_timeout(2500)
    s.check("four charts drawn", page.locator(f'{tid("agentops-charts")} .js-plotly-plot').count() == 4,
            4, page.locator(f'{tid("agentops-charts")} .js-plotly-plot').count())

    s.start("both", "R5-A3-3", "Agent Operations: run the Admin evaluation suite; kill switch on and off")
    page.locator(tid("admin-tab-evals")).click()
    page.wait_for_selector(tid("eval-suite"))
    suite = page.locator(f'{tid("eval-suite")}[data-module="admin"]')
    suite.locator(tid("eval-run")).click()
    page.wait_for_selector(f'{tid("eval-suite")}[data-module="admin"] {tid("eval-last")}', timeout=120_000)
    last = suite.locator(tid("eval-last"))
    s.check("the suite passes", last.get_attribute("data-passed") == last.get_attribute("data-total") == "4",
            "4/4", f"{last.get_attribute('data-passed')}/{last.get_attribute('data-total')}")
    page.locator(tid("admin-tab-switches")).click()
    page.wait_for_selector(tid("kill-switch"))
    sw = page.locator(f'{tid("kill-switch")}[data-module="what_if"]')
    sw.locator(tid("kill-switch-toggle")).click()
    page.wait_for_selector(f'{tid("kill-switch")}[data-module="what_if"][data-on="true"]')
    st = {c["id"]: c["body"]["kill_switch"] for c in _call("/api/v1/admin/studio", cookie)["configs"]}
    s.check("the What-If assistant falls back to planner mode", st["what_if"] is True)
    page.locator(f'{tid("kill-switch")}[data-module="what_if"] {tid("kill-switch-toggle")}').click()
    page.wait_for_selector(f'{tid("kill-switch")}[data-module="what_if"][data-on="false"]')
    s.check("and back on", _call("/api/v1/admin/studio", cookie)["configs"] and
            not next(c for c in _call("/api/v1/admin/studio", cookie)["configs"] if c["id"] == "what_if")["body"]["kill_switch"])
    s.check("the Cockpit has no switch here (frozen)", page.locator(f'{tid("kill-switch")}[data-module="cockpit"] {tid("kill-switch-toggle")}').count() == 0)

    # ---------------------------------------------------------------- A4 studio
    s.start("both", "R5-A4-1", "AI Studio: the Cockpit is read-only; What-If test bench live vs draft")
    page.goto(UI + "/ai-studio", wait_until="domcontentloaded")
    page.wait_for_selector(tid("studio-config"))
    page.locator(tid("studio-module-cockpit")).click()
    page.wait_for_selector(f'{tid("studio-config")}[data-module="cockpit"]')
    s.check("Cockpit inputs are disabled", page.locator(tid("studio-instructions")).is_disabled())
    page.locator(tid("studio-module-what_if")).click()
    page.wait_for_selector(f'{tid("studio-config")}[data-module="what_if"]')
    page.locator(tid("studio-guard-scope_refusal")).click()
    page.fill(tid("studio-question"), "What is the weather in Riyadh?")
    page.locator(tid("studio-test")).click()
    page.wait_for_selector(tid("studio-bench-side"))
    sides = page.locator(tid("studio-bench-side")).all_inner_texts()
    s.check("live refuses out of scope, the draft without the guardrail does not", len(sides) == 2 and "Outside" in sides[0] and "Outside" not in sides[1], "", sides)

    # ---------------------------------------------------------------- A5 settings
    st = _call("/api/v1/admin/settings", cookie)
    s.start("both", "R5-A5-1", "Settings: bank profile, house style, notifications, retention; parameter register; data feeds")
    page.goto(UI + "/settings", wait_until="domcontentloaded")
    page.wait_for_selector(tid("param-row"))
    # PLAN_R6 B6 adds the fifth: "LLM model names" (display name -> real model ID).
    s.check("five settings, one is the LLM model names", page.locator(tid("setting-card")).count() == len(st["settings"]) == 5
            and any(x.get("id") == "model_names" for x in st["settings"]))
    s.check("one row per parameter table", page.locator(tid("param-row")).count() == len(st["parameters"]), len(st["parameters"]), page.locator(tid("param-row")).count())
    s.check("feeds", page.locator(tid("feed-card")).count() == len(st["feeds"]))
    s.check("the bank profile shows the reporting currency", "SAR" in page.locator(f'{tid("setting-card")}[data-id="bank_profile"]').inner_text())

    # ---------------------------------------------------------------- A6 audit
    au = _call("/api/v1/admin/audit", cookie)
    s.start("both", "R5-A6-1", "Audit log: events from Admin, Core and the assistants; filter; Excel export in house style")
    page.goto(UI + "/audit-log", wait_until="domcontentloaded")
    page.wait_for_selector(tid("audit-row"))
    s.check("the total equals the API", page.locator(tid("audit-total")).inner_text().split(" ")[0].replace(",", "") in (str(au["total"]), str(au["total"] + 1), str(au["total"] + 2)),
            au["total"], page.locator(tid("audit-total")).inner_text())
    page.select_option(tid("audit-category"), "approval")
    page.wait_for_timeout(1200)
    cats = set(page.locator(tid("audit-row")).evaluate_all("els => els.map(e => e.dataset.category)"))
    s.check("filtered to approvals", cats == {"approval"}, {"approval"}, cats)
    with page.expect_download(timeout=60_000) as dl:
        page.locator(tid("audit-export")).click()
    path = Path(dl.value.path())
    s.check("an Excel file", path.stat().st_size > 2000)
    from backend.house_style import check as house_check
    problems = house_check.xlsx(path.read_bytes())
    s.check("house style", not problems, "no problem", problems[:3])

    # ---------------------------------------------------------------- A1 enforcement as the RM
    s.start("corporate", "R5-A1-8", "View as Nawaf (RM): What-If is closed; B360 and Early Warning show only his borrowers")
    _call("/api/v1/auth/view-as", cookie, "POST", {"username": rm}, base=core_login.CORE)
    page.goto(UI + "/what-if", wait_until="domcontentloaded")
    page.wait_for_selector(tid("access-denied"), timeout=60_000)
    s.check("What-If refused by the route guard", page.locator(tid("access-denied")).get_attribute("data-module") == "what_if")
    lst = _call("/api/v1/b360/list?domain=corporate&limit=500", cookie, base="http://127.0.0.1:8502")
    s.check("B360 list: his borrowers, as the books give them", lst["total"] == len(mine) and {r["id"] for r in lst["rows"]} == mine,
            len(mine), lst["total"])
    ews = _call("/api/v1/ews/customers?domain=corporate&cohort=all&limit=500", cookie, base="http://127.0.0.1:8501")
    rows = ews.get("customers") or ews.get("rows") or []
    s.check("Early Warning customers: only his", rows and {r["customer_id"] for r in rows} <= mine, "subset", len(rows))
    s.check("What-If API refuses him", _status("http://127.0.0.1:8503/api/v1/whatif/threads", cookie) == 403)
    page.goto(UI + "/borrower-360", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    s.check("the B360 page renders for him", page.locator(tid("access-denied")).count() == 0)
    _call("/api/v1/auth/view-as", cookie, "POST", {"username": None}, base=core_login.CORE)
    page.goto(UI + "/workflow", wait_until="domcontentloaded")
    page.wait_for_selector(tid("policy-card"))
    s.check("back as the Administrator: Admin opens again", page.locator(tid("access-denied")).count() == 0)


def _status(url: str, cookie: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"Cookie": f"cp_session={cookie}"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return r.status
    except urllib.error.HTTPError as e:   # type: ignore[attr-defined]
        return e.code
