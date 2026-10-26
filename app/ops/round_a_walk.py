#!/usr/bin/env python3
"""Round A: the browser walk of the agentic intake on the production build, with screenshots.

    .venv/bin/python ops/round_a_walk.py [--ui http://127.0.0.1:6600] [--out var/walk/round-a]

Deal Desk → New proposal → Customer documents → Load sample deal (16 files) → hold back three files (the SIMAH report,
the rating sheet, the account conduct report) → Run the agent → the three steps finish with timings → the completeness
meter and "What I cannot assess with this file" (critical in red) → the business request (cited, completeness line under
the header) → Word download → add the three files and run again → "x% → y% (+z)" and "Now covered since the last run" →
Revise (needs the model: with no key the message says so) → the customer file and "Create the proposal from this file" →
the deal opens. Exit 1 on any failed check. Standard library + Playwright; no password printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))

from core_login import add_session  # noqa: E402

HOLD = ("05 ", "06 ", "11 ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:6600")
    ap.add_argument("--out", default=str(V5 / "var" / "walk" / "round-a"))
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds a run may take (OCR of the photos and the scan)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    checks: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, note: str = "") -> None:
        checks.append((name, bool(cond), note))
        print(("PASS " if cond else "FAIL ") + name + (f" — {note}" if note else ""), flush=True)

    T = lambda t: f'[data-testid="{t}"]'  # noqa: E731
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        add_session(ctx)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        n = [0]

        def shot(name: str, full: bool = True, loc=None) -> None:
            n[0] += 1
            p = out / f"{n[0]:02d}-{name}.png"
            (loc.screenshot(path=str(p)) if loc is not None else page.screenshot(path=str(p), full_page=full))

        page.goto(f"{a.ui}/deal-desk", wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(1500)
        page.wait_for_selector(T("dealdesk-new"), timeout=60_000)
        page.click(T("dealdesk-new"))
        page.wait_for_selector(T("dealdesk-new-dialog"), timeout=30_000)
        page.click(T("dealdesk-new-docs"))
        page.wait_for_selector(T("agent-intake"), timeout=30_000)
        ok("New proposal → Customer documents opens the agent", page.locator(T("agent-run")).count() == 1)
        shot("agent-empty")

        # the sample deal
        page.click(T("agent-load-sample"))
        page.wait_for_function("document.querySelectorAll('[data-testid=\"agent-file-new\"]').length >= 16", timeout=60_000)
        ok("Load sample deal puts 16 files in the drop", page.locator(T("agent-file-new")).count() == 16)
        ok("the ask and RM notes are filled", "Al Qirawan" in page.input_value(T("agent-ask")) and "January 2027" in page.input_value(T("agent-notes")))
        # hold back three documents for the re-run
        for _ in range(3):
            rows = page.locator(T("agent-file-new"))
            for i in range(rows.count()):
                if rows.nth(i).inner_text().startswith(HOLD):
                    rows.nth(i).get_by_role("button").click()
                    break
        ok("three files held back for the re-run", page.locator(T("agent-file-new")).count() == 13)
        shot("sample-loaded")

        t0 = time.time()
        page.click(T("agent-run-button"))
        page.wait_for_selector(f'{T("agent-step-read")}[data-status="running"], {T("agent-step-read")}[data-status="done"], {T("agent-step-read")}[data-status="warn"]', timeout=60_000)
        page.wait_for_timeout(1500)
        shot("run-reading")
        page.wait_for_selector(f'{T("agent-step-draft")}[data-status="done"]', timeout=int(a.timeout * 1000))
        page.wait_for_timeout(1000)
        took = time.time() - t0
        times = [page.inner_text(T(f"agent-step-{k}-time")) for k in ("read", "check", "draft")]
        ok("three steps finish, each with a timing", all(re.fullmatch(r"\d+\.\ds", x) for x in times), f"{times}, run {took:.0f}s")
        ok("16 → 13 documents read (D1..D13)", page.locator(T("agent-read-doc")).count() == 13)
        meter1 = page.inner_text(T("agent-meter"))
        ok("completeness meter", bool(re.match(r"Completeness \d+%", meter1)), meter1)
        crit = page.locator(f'{T("agent-gap")}[data-critical="1"]').count()
        ok("What I cannot assess: critical lines (red) for the missing SIMAH, rating, conduct", crit >= 3, f"{crit} critical")
        shot("run-done")
        shot("agent-run-panel", loc=page.locator(T("agent-run")))
        paper = page.inner_text(T("agent-paper"))
        low = paper.lower()
        ok("the business request: title, cited figures, completeness under the header",
           paper.startswith("Business Request") and "[D" in paper and page.locator(T("agent-paper-completeness")).count() == 1
           and "action requested" in low and low.index("completeness:") < low.index("action requested"))
        ok("the could-not-assess block in the paper", page.locator(T("agent-paper-gaps")).count() == 1)
        shot("business-request", loc=page.locator(T("agent-request")))
        # Word
        with page.expect_download(timeout=60_000) as dl:
            page.click(T("agent-docx"))
        d = dl.value
        dest = out / d.suggested_filename
        d.save_as(str(dest))
        ok("Word download", dest.stat().st_size > 10_000 and dest.read_bytes()[:2] == b"PK", dest.name)

        # add the three held-back documents and run again
        files = [p for p in sorted((V5 / "data" / "dealdesk" / "agent_sample").iterdir()) if p.name.startswith(HOLD)]
        page.set_input_files(T("agent-drop-input"), [str(p) for p in files])
        page.wait_for_timeout(500)
        ok("three new files in the drop", page.locator(T("agent-file-new")).count() == 3)
        page.click(T("agent-run-button"))
        page.wait_for_selector(f'{T("agent-step-check")}[data-status="pending"], {T("agent-step-read")}[data-status="running"]', timeout=60_000)
        page.wait_for_selector(f'{T("agent-step-draft")}[data-status="done"]', timeout=int(a.timeout * 1000))
        page.wait_for_timeout(1000)
        meter2 = page.inner_text(T("agent-meter"))
        ok("re-run: the meter shows before → after (+delta)", bool(re.match(r"Completeness \d+% → \d+% ?\(\+\d+\)", meter2)), meter2)
        cov = page.inner_text(T("agent-now-covered")) if page.locator(T("agent-now-covered")).count() else ""
        ok("Now covered since the last run", "Propose a rating" in cov and "exposure with other banks" in cov, cov.replace("\n", " | ")[:200])
        ok("16 documents after the re-run", page.locator(T("agent-read-doc")).count() == 16)
        shot("rerun-done")
        shot("rerun-check", loc=page.locator(T("agent-step-check")))

        # revise
        page.fill(T("agent-revise-input"), "Tighten section 7 to three rows")
        page.click(T("agent-revise-button"))
        page.wait_for_timeout(2500)
        st = page.inner_text(T("agent-status"))
        model_on = "Model:" in page.inner_text(T("agent-model-line"))
        if model_on:
            page.wait_for_selector(f'{T("agent-step-draft")}[data-status="done"]', timeout=300_000)
            ok("Revise: a new version", "version 2" in page.inner_text(T("agent-draft-meta")))
        else:
            ok("Revise with no model key says it needs the model", "needs the model" in st, st[:120])
        shot("revise")

        # the customer file and the deal
        page.wait_for_selector(T("agent-customer-file"), timeout=60_000)
        ok("R16's customer file under the run", page.locator(T("intake-checklist")).count() == 1)
        shot("customer-file")
        opener = page.locator(T("intake-open-deal"))
        (opener if opener.count() else page.locator(T("intake-create"))).click()
        page.wait_for_url(re.compile(r".*deal-desk.*"), timeout=120_000)
        page.wait_for_timeout(4000)
        ok("the deal opens", page.locator(T("dealdesk-new-dialog")).count() == 0, page.url)
        shot("deal-opened", full=False)
        ok("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()

    failed = [c for c in checks if not c[1]]
    (out / "report.json").write_text(json.dumps({"checks": [{"check": c, "pass": p, "note": nt} for c, p, nt in checks]}, indent=1))
    print(f"\nRound A walk: {len(checks) - len(failed)} of {len(checks)} checks PASS; screenshots in {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
