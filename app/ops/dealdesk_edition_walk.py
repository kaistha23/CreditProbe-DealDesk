#!/usr/bin/env python3
"""Deal Desk edition: the browser walk over every screen the edition lists, on the production build.

    .venv/bin/python ops/dealdesk_edition_walk.py [--ui http://127.0.0.1:6600] [--out var/walk/dealdesk_edition]

Signs in (ops/core_login.py: CP_TEST_PASSWORD, or CP_MINT_SESSION=1), then opens, as a signed-in user:
  1. the landing page: "/" is the Cockpit (its brief and Ask are Deal Desk's);
  2. every route of a removed module: each must land on Deal Desk;
  3. every sidebar entry of the edition (Deal Desk, the Work group, Data, Trace, Admin), and the Deal Desk
     sub-screens (review, credit response, customer packs, parameters, portfolio RAROC, RAROC drift) and the first
     deal of the pipeline (the four-step thread screen);
and records, per screen: the final URL, the HTTP status, page errors, console errors, failed requests, the sidebar
labels, the removed-module labels found in the screen's content, and a screenshot. Exit 1 when any kept screen fails
to render, any removed route does not redirect, or (Round C) a kept screen outside Deal Desk names a module that is
not in the product or calls a service the edition does not run.
Standard library + Playwright (the venv's); no password printed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))

from core_login import add_session  # noqa: E402

HOME = "/deal-desk"
REMOVED = ["/brf", "/lenses", "/lenses/cro", "/early-warning", "/early-warning/model", "/playbooks",
           "/stress", "/what-if", "/borrower-360", "/scorecard-validation", "/engine-builder", "/analysis/x", "/intelligence",
           "/queries", "/accepted-risk"]
KEPT = ["/", "/?tab=ask", "/deal-desk", "/deal-desk/review", "/deal-desk/credit-response", "/deal-desk/customer-packs", "/deal-desk/parameters",
        "/deal-desk/raroc-drift",   # /deal-desk/portfolio-raroc redirects here by design
        "/workspace", "/workspace?tab=home", "/messages", "/projects", "/investigations", "/analyses", "/playbook", "/policy-docs",
        "/data-builder", "/studio", "/trace",
        "/workflow", "/users", "/agent-operations", "/ai-studio", "/settings", "/audit-log"]
EXPECTED_SIDEBAR = ["Cockpit", "Deal Desk", "Workspace", "Mail", "Playbook", "Policy Docs", "Projects", "Investigations", "Analyses",
                    "Data Domains", "Analysis Studio", "Trace & Lineage", "Workflow", "Users & Teams", "Agent Operations",
                    "AI Studio", "Settings", "Audit log"]
NOT_RUN_PORTS = ("8501", "8502", "8503", "8507", "8509", "8516")   # services the edition leaves down
#: Round C: labels of the modules that are not in the product. None may appear on a kept screen outside Deal Desk's
#: own screens (Deal Desk's book tab names the monitoring band a facility carries; that is data, not a module link).
REMOVED_LABELS = ("Early Warning", "Open Banking", "What-If", "Lenses", "Scorecard Validation", "BRF", "Stress Testing",
                  "Borrower 360", "ECL investigation", "temporarily unavailable")
#: Kept screens whose body is checked for those labels (everything that is not a Deal Desk screen).
LABEL_CHECKED = ("/", "/?tab=ask", "/workspace", "/workspace?tab=home", "/messages", "/projects", "/investigations", "/analyses",
                 "/playbook", "/policy-docs", "/data-builder", "/studio", "/trace", "/workflow", "/users", "/agent-operations",
                 "/ai-studio", "/settings", "/audit-log")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:6600")
    ap.add_argument("--out", default=str(V5 / "var" / "walk" / "dealdesk_edition"))
    ap.add_argument("--only-deals", action="store_true")
    ap.add_argument("--settle", type=float, default=2.5, help="seconds to let a screen load after networkidle")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    report: dict = {"ui": a.ui, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "removed": [], "kept": [], "failures": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        me = add_session(ctx)
        console: list[str] = []
        page_errors: list[str] = []
        failed: list[str] = []
        page = None

        def new_page():
            nonlocal page
            page = ctx.new_page()
            page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}") if m.type in ("error",) else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)[:200]))
            page.on("requestfailed", lambda r: failed.append(f"{r.method} {r.url} {r.failure}"))
            page.on("response", lambda r: failed.append(f"{r.request.method} {r.url} HTTP {r.status}") if r.status >= 500 else None)
            return page

        new_page()

        def visit(path: str) -> dict:
            try:
                return _visit(path)
            except Exception as e:  # noqa: BLE001 - a crashed tab (memory in a small container) gets one retry on a new tab
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
                new_page()
                try:
                    return _visit(path)
                except Exception as e2:  # noqa: BLE001
                    return {"path": path, "final": "", "status": None, "ms": 0, "broken": True,
                            "page_errors": [f"walk: {type(e).__name__}: {str(e)[:120]}", f"retry: {type(e2).__name__}: {str(e2)[:120]}"],
                            "console_errors": [], "failed_requests": [], "requests_to_services_not_run": [], "sidebar": [], "removed_labels": []}

        def _visit(path: str) -> dict:
            console.clear(); page_errors.clear(); failed.clear()
            t0 = time.monotonic()
            resp = page.goto(a.ui + path, wait_until="domcontentloaded", timeout=90_000)
            try:
                page.wait_for_load_state("networkidle", timeout=60_000)
            except Exception:  # noqa: BLE001 - a long poll keeps the network busy; the settle covers it
                pass
            time.sleep(a.settle)
            labels = [t.strip().split("\n")[0] for t in page.locator("[data-testid^='nav-']").all_inner_texts() if t.strip()]
            body = page.inner_text("body") if page.locator("body").count() else ""
            broken = any(s in body[:4000] for s in ("Application error", "Something went wrong", "This page could not be found", "Unhandled Runtime Error"))
            # the sidebar is the same on every screen; the labels check is about the screen's own content
            main = page.inner_text("main") if page.locator("main").count() else body
            removed_labels = sorted({l for l in REMOVED_LABELS if l in main}) if path in LABEL_CHECKED else []
            not_run = [f for f in failed if any(f":{p}/" in f for p in NOT_RUN_PORTS)]
            real_failed = [f for f in failed if f not in not_run]
            shot = out / (path.strip("/").replace("/", "_") or "root")
            page.screenshot(path=str(shot) + ".png", full_page=False)
            return {"path": path, "final": page.url.replace(a.ui, ""), "status": resp.status if resp else None,
                    "ms": round((time.monotonic() - t0) * 1000), "broken": broken, "page_errors": list(page_errors),
                    "console_errors": list(console)[:20], "failed_requests": real_failed[:20],
                    "requests_to_services_not_run": not_run[:20], "sidebar": labels, "removed_labels": removed_labels}

        for path in ([] if a.only_deals else REMOVED):
            r = visit(path)
            report["removed"].append(r)
            if not r["final"].startswith(HOME):
                report["failures"].append(f"{path} did not land on Deal Desk (landed on {r['final']})")
        for path in (["/deal-desk"] if a.only_deals else KEPT):
            r = visit(path)
            report["kept"].append(r)
            if r["broken"] or r["page_errors"] or (r["status"] and r["status"] >= 400) or not r["final"].startswith(path.split("?")[0]):
                report["failures"].append(f"{path}: status {r['status']}, landed {r['final']}, broken={r['broken']}, errors={r['page_errors'][:2]}")
            if r["removed_labels"]:
                report["failures"].append(f"{path}: names a module that is not in the product: {r['removed_labels']}")
            if path in LABEL_CHECKED and r["requests_to_services_not_run"]:
                report["failures"].append(f"{path}: calls a service the edition does not run: {r['requests_to_services_not_run'][:2]}")
        # the sidebar lists exactly the edition's entries (checked on the Deal Desk home)
        home = next(k for k in report["kept"] if k["path"] == "/deal-desk")
        missing = [l for l in EXPECTED_SIDEBAR if l not in home["sidebar"]]
        extra = [l for l in home["sidebar"] if l not in EXPECTED_SIDEBAR and l not in ("CreditProbe AI", "Deal Desk")]
        if missing:
            report["failures"].append(f"sidebar is missing {missing}")
        for gone in ["BRF", "Lenses", "Early Warning", "Playbooks", "Stress Testing", "What-If", "Borrower 360", "Scorecard"]:
            if gone in home["sidebar"]:
                report["failures"].append(f"sidebar still lists {gone}")
        report["sidebar_extra"] = extra
        # the Cockpit home in the edition: Deal Desk's brief on the Brief tab; a question on the Ask tab opens a desk thread
        try:
            page.goto(a.ui + "/", wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_selector("[data-testid='noor-home-brief'], [role='status']", timeout=90_000)
            time.sleep(a.settle)
            body = page.inner_text("body")
            report["home_brief"] = {"deal_desk_brief": "Deal Desk" in body and "pay attention to in Deal Desk" in body,
                                    "no_ecl_disclosure": page.locator("[data-testid='home-brief-more']").count() == 0}
            if not report["home_brief"]["deal_desk_brief"]:
                report["failures"].append("the home brief is not Deal Desk's")
            page.goto(a.ui + "/?tab=ask", wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_selector("[data-testid='cockpit-v4-question']", timeout=60_000)
            prompts = page.locator("[data-testid='cockpit-v4-prompt']").all_inner_texts()
            report["home_ask"] = {"starters": prompts, "deep_offered": page.locator("[data-testid='cockpit-v4-mode-deep']").count() > 0}
            page.fill("[data-testid='cockpit-v4-question']", "Which proposals breach a hard limit?")
            page.click("[data-testid='cockpit-v4-ask']")
            page.wait_for_url(lambda u: "/deal-desk/thread/" in u, timeout=120_000)
            report["home_ask"]["landed"] = page.url.replace(a.ui, "")
            page.wait_for_load_state("networkidle", timeout=120_000)
            time.sleep(a.settle)
            page.screenshot(path=str(out / "home_ask_thread.png"))
            if "/deal-desk/thread/" not in report["home_ask"]["landed"]:
                report["failures"].append("a question on the home did not open a Deal Desk thread")
        except Exception as e:  # noqa: BLE001
            report["failures"].append(f"home brief/ask: {type(e).__name__}: {str(e)[:160]}")
        # a deal's own screens: the four-step thread screen of the deal to committee and of the half-baked RM proposal
        for pid in ("R12-TWA", "R14-RWQ", "DD-01"):
            r = visit(f"/deal-desk/{pid}")
            report["kept"].append(r)
            if r["broken"] or r["page_errors"] or (r["status"] and r["status"] >= 400):
                report["failures"].append(f"/deal-desk/{pid}: status {r['status']}, broken={r['broken']} errors={r['page_errors'][:2]}")
        report["user"] = me.get("username")
        browser.close()
    (out / "report.json").write_text(json.dumps(report, indent=1))
    ok = not report["failures"]
    print(f"{'PASS' if ok else 'FAIL'}: {len(report['removed'])} removed routes redirect, {len(report['kept'])} kept screens; "
          f"{len(report['failures'])} failures -> {out / 'report.json'}")
    for f in report["failures"]:
        print("  -", f)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
