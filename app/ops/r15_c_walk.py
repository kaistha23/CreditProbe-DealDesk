"""R15 c walk: the Early Warning triage agent on the production build (L4, L5, L6), screens in docs/v5/r15_review/c/.

  CP_MINT_SESSION=1 .venv/bin/python ops/r15_c_walk.py [--ui http://127.0.0.1:5500] [--size 1440x900]

Clicks only (N6): Early Warning → Triage with agent → plain words and planning → answer (headline, ranked table,
Approve/Reject) → a finding row expands to the borrower's early-warning indicators → Borrower 360 → Back reopens the
run → Early Warning detail. A second pass fakes a run that never leaves planning and fast-forwards the clock 61 s to
show the way out. Writes report.md and summary.json next to the screens.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
from core_login import add_session  # noqa: E402

OUT = ROOT / "docs" / "v5" / "r15_review" / "c"
T = lambda tid: f'[data-testid="{tid}"]'  # noqa: E731


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--size", default="1440x900")
    a = ap.parse_args()
    w, h = (int(x) for x in a.size.split("x"))
    OUT.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []
    errors: list[str] = []
    tag = f"{w}x{h}"

    def shot(page: Page, name: str, note: str, ok: bool = True) -> None:
        p = OUT / f"{tag}_{name}.png"
        page.screenshot(path=str(p), full_page=False)
        steps.append({"step": name, "ok": ok, "note": note, "screen": p.name})
        print(("OK  " if ok else "MISS") + f" {name}: {note}", flush=True)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": w, "height": h})
        add_session(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        page.goto(f"{a.ui}/early-warning?domain=corporate", wait_until="domcontentloaded")
        page.wait_for_selector(T("ews-triage-agent"), timeout=90_000)
        page.wait_for_timeout(1500)
        shot(page, "01_early_warning", "Early Warning with the Triage with agent button")

        t0 = time.monotonic()
        page.click(T("ews-triage-agent"))
        page.wait_for_selector(T("agent-run-drawer"), timeout=30_000)
        page.wait_for_timeout(600)
        pw_ok = page.locator(T("agent-plain-words")).count() > 0
        shot(page, "02_plain_words_planning", "drawer opens with In plain words and live planning progress", pw_ok)

        page.wait_for_selector(T("agent-answer"), timeout=150_000)
        page.wait_for_selector(T("ews-triage-table"), timeout=30_000)
        secs = time.monotonic() - t0
        drawer = page.locator('[role="dialog"]')
        status = page.locator(T("agent-run-drawer")).inner_text()
        partial = "stopped after" in status
        shot(page, "03_answer_headline", f"run finished in {secs:.0f} s; headline + answer; partial stop shown: {partial}",
             not partial)
        page.locator(T("ews-triage-table")).scroll_into_view_if_needed()
        rows = page.locator(T("ews-triage-row")).count()
        approve = page.locator(f'{T("ews-triage-table")} {T("agent-approve")}').count()
        shot(page, "04_ranked_table", f"ranked table: {rows} rows, {approve} with Approve/Reject", rows > 0 and approve > 0)

        page.locator(T("agent-findings")).scroll_into_view_if_needed()
        tog = page.locator(T("agent-finding-toggle")).first
        tog.click()
        page.wait_for_selector(T("agent-finding-detail"), timeout=10_000)
        page.locator(T("agent-finding-detail")).first.scroll_into_view_if_needed()
        has_rules = page.locator(T("agent-finding-ews")).count() > 0
        shot(page, "05_finding_detail", "finding row expands: score, trend, rules, DPD, stage, rating, conduct, bureau",
             has_rules)

        page.locator(T("agent-finding-b360-link")).first.click()
        page.wait_for_url("**/borrower-360**", timeout=30_000)
        page.wait_for_timeout(2500)
        shot(page, "06_borrower_360", f"Borrower 360 opened from the finding ({page.url.split('?')[0]})")

        back = page.get_by_role("link", name="Back to Early Warning").first
        if back.count() == 0:
            back = page.get_by_text("Back to Early Warning").first
        back.click()
        page.wait_for_url("**/early-warning**", timeout=30_000)
        page.wait_for_selector(T("agent-run-drawer"), timeout=30_000)
        page.wait_for_selector(T("agent-answer"), timeout=30_000)
        shot(page, "07_back_reopens_run", "Back returns to Early Warning with the same run open")

        page.locator(T("agent-findings")).scroll_into_view_if_needed()
        page.locator(T("agent-finding-toggle")).first.click()
        page.locator(T("agent-finding-ews-link")).first.click()
        page.wait_for_timeout(3000)
        shot(page, "08_ews_detail", f"Early Warning detail for the borrower ({'customer=' in page.url})", "customer=" in page.url)

        # names in the answer text are links too
        page.goto(f"{a.ui}/early-warning?domain=corporate", wait_until="domcontentloaded")
        page.wait_for_selector(T("ews-triage-agent"), timeout=90_000)
        ctx2 = b.new_context(viewport={"width": w, "height": h})
        add_session(ctx2)
        p2 = ctx2.new_page()
        p2.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        fake = {"run_id": "agr_stall", "agent": "ews.triage", "goal": "Triage this period's warnings",
                "context": {"domain": "corporate"}, "trigger": "on_demand", "scope": "corporate", "status": "running",
                "plan": None, "findings": [], "narrative": "", "output": {}, "proposals": [], "approvals": [],
                "budget": {}, "stopped": "", "user": "", "created_at": "", "finished_at": "", "duration_ms": 0,
                "model": "", "citation_check": {}}
        p2.route("**/api/v1/agents/ews.triage/runs", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                          body=json.dumps(fake)))
        p2.route("**/api/v1/agents/runs/agr_stall**", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                           body=json.dumps(fake)))
        p2.clock.install()
        p2.goto(f"{a.ui}/early-warning?domain=corporate", wait_until="domcontentloaded")
        p2.wait_for_selector(T("ews-triage-agent"), timeout=90_000)
        p2.click(T("ews-triage-agent"))
        p2.wait_for_selector(T("agent-planning"), timeout=30_000)
        p2.clock.fast_forward(62_000)
        p2.clock.run_for(2_000)
        ok = p2.locator(T("agent-planning-stalled")).count() > 0
        p = OUT / f"{tag}_09_planning_stalled.png"
        p2.screenshot(path=str(p))
        steps.append({"step": "09_planning_stalled", "ok": ok, "screen": p.name,
                      "note": "after 60 s in planning: why, Run the written plan now, Show the warned list"})
        print(("OK  " if ok else "MISS") + " 09_planning_stalled", flush=True)
        b.close()

    errs = [e for e in errors if "favicon" not in e]
    (OUT / f"summary_{tag}.json").write_text(json.dumps({"size": tag, "steps": steps, "errors": errs}, indent=2))
    lines = [f"# R15 c walk ({tag}, production build)", "", "| Step | OK | What it shows | Screen |", "|---|---|---|---|"]
    lines += [f"| {s['step']} | {'yes' if s['ok'] else 'NO'} | {s['note']} | `{s['screen']}` |" for s in steps]
    lines += ["", f"Console/page errors: {len(errs)}"] + [f"- {e[:200]}" for e in errs[:20]]
    (OUT / f"report_{tag}.md").write_text("\n".join(lines) + "\n")
    print(f"{sum(s['ok'] for s in steps)}/{len(steps)} OK; {len(errs)} errors")
    return 0 if all(s["ok"] for s in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
