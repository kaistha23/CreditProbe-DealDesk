"""Browser smoke for R10 Session Q: auditor and regulator queries answered in the Cockpit, and Analyses that answer.

    .venv/bin/python ops/smoke_cockpit_queries.py [ui_base]

1. Cockpit (/): Anne's question typed in the Ask box ("Answer the auditor's question on 30+ DPD loans still in
   Stage 1") renders the answer under the box (headline with a bold figure, evidence, Trace).
2. The five letters on file, each asked from "Letters on file", answer in place.
3. "Who are you?" is NOT taken by the queries panel (it goes to the Cockpit's own agent).
4. /analyses: every card's title is a question with a bold answer line; one detail opens answer first.
Writes evidence/v5/r10_queries/{*.png, smoke.json}. Exit 1 on failure. Nothing secret is printed.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "r10_queries"
UI = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5500").rstrip("/")
BANNED = ("demo", "sample", "synthetic", "mock", "lorem")
ANNE = "Answer the auditor's question on 30+ DPD loans still in Stage 1"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    s = core_login.login("anne")
    errors: list[str] = []
    steps: list[dict] = []
    with sync_playwright() as pw:
        exe = os.environ.get("PW_CHROMIUM")  # a pinned browser (the cloud container) instead of the bundled one
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies([{"name": "cp_session", "value": s["cookie"], "url": UI}])
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def shot(name: str, **extra) -> None:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
            body = page.inner_text("body").lower()
            bad = [w for w in BANNED if f" {w} " in f" {body} "]
            steps.append({"step": name, "banned_words": bad, **extra})
            if bad:
                errors.append(f"{name}: banned words {bad}")

        page.goto(f"{UI}/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=cockpit-v4-question]", timeout=60000)
        page.wait_for_selector("[data-testid=cockpit-queries]", state="attached", timeout=30000)  # R14 FX-R14-01: no attach row
        shot("01_cockpit_home")

        # 1. Anne's question in the Cockpit's own Ask box.
        page.fill("[data-testid=cockpit-v4-question]", ANNE)
        page.click("[data-testid=cockpit-v4-ask]")
        page.wait_for_selector("[data-testid=cockpit-query-1-lead]", timeout=90000)
        lead = page.inner_text("[data-testid=cockpit-query-1-lead]")
        bold = page.locator("[data-testid=cockpit-query-1-lead] strong").count()
        page.wait_for_selector("[data-testid=cockpit-query-1-lead-chart] .main-svg", timeout=60000)
        page.click("[data-testid=cockpit-query-1-lead-trace]")
        page.locator("[data-testid=cockpit-query-1-lead]").scroll_into_view_if_needed()
        shot("02_anne_question", case=page.get_attribute("[data-testid=cockpit-query-1]", "data-case"), bold_figures=bold,
             headline=lead.splitlines()[1] if len(lead.splitlines()) > 1 else lead)
        if page.get_attribute("[data-testid=cockpit-query-1]", "data-case") != "Q1" or bold < 1:
            errors.append("Anne's question did not render the Q1 answer with a bold figure")
        if "/cockpit/thread/" in page.url:
            errors.append("Anne's question opened a Cockpit thread instead of the query answer")

        # 2. The five letters on file, typed (R14 FX-R14-01 removed the "Letters on file" row; the cue "letter Qn" still answers).
        for i, c in enumerate(("Q1", "Q2", "Q3", "Q4", "Q5"), start=2):
            page.fill("[data-testid=cockpit-v4-question]", f"Answer the auditor's letter {c}")
            page.click("[data-testid=cockpit-v4-ask]")
            page.wait_for_selector(f"[data-testid=cockpit-query-{i}-lead]", timeout=90000)
            got = page.get_attribute(f"[data-testid=cockpit-query-{i}]", "data-case")
            if page.locator(f"[data-testid=cockpit-query-{i}-lead-chart]").count():
                page.wait_for_selector(f"[data-testid=cockpit-query-{i}-lead-chart] .main-svg", timeout=60000)
            has_ev = page.locator(f"[data-testid=cockpit-query-{i}-lead-evidence]").count()
            page.locator(f"[data-testid=cockpit-query-{i}]").scroll_into_view_if_needed()
            shot(f"03_letter_{c}", case=got, evidence=has_ev)
            if got != c or not has_ev:
                errors.append(f"letter {c}: rendered case {got}, evidence {has_ev}")

        # 3. "Who are you?" stays with the Cockpit's agent.
        before = page.locator("[data-testid^=cockpit-query-][data-case]").count()
        page.fill("[data-testid=cockpit-v4-question]", "Who are you?")
        page.click("[data-testid=cockpit-v4-ask]")
        page.wait_for_timeout(4000)
        after = page.locator("[data-testid^=cockpit-query-][data-case]").count()
        steps.append({"step": "04_who_are_you", "queries_answers_before": before, "after": after, "url": page.url})
        if after != before:
            errors.append("'Who are you?' was taken by the queries panel")

        # 4. Analyses.
        page.goto(f"{UI}/analyses", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid^=ws-analysis-headline-]", timeout=60000)
        cards = page.locator("[data-testid^=ws-analysis-headline-]")
        n = cards.count()
        bolds = sum(1 for k in range(n) if cards.nth(k).locator("strong").count() > 0)
        shot("05_analyses", cards=n, with_bold_answer=bolds)
        if n < 4 or bolds != n:
            errors.append(f"analyses: {bolds} of {n} cards lead with a bold answer")
        page.locator("[data-testid^=ws-analysis-open-]").first.click()
        page.wait_for_selector("[data-testid=ws-analysis-headline]", timeout=60000)
        page.wait_for_selector("[data-testid=ws-analysis-table]", timeout=60000)
        page.wait_for_selector("[data-testid=ws-analysis-plot] .main-svg", timeout=60000)
        title = page.inner_text("h1") if page.locator("h1").count() else ""
        shot("06_analysis_detail", title=title, chart=page.locator("[data-testid=ws-analysis-chart]").count())
        if not title.strip().endswith("?"):
            errors.append(f"analysis title is not the question: {title!r}")
        b.close()
    (OUT / "smoke.json").write_text(json.dumps({"ui": UI, "steps": steps, "errors": errors}, indent=1))
    print(json.dumps({"steps": len(steps), "errors": errors}, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
