"""Browser smoke for /queries and /brf (PLAN_R9 Session F): every case end to end and the BRF flow, no console errors.

    .venv/bin/python ops/smoke_queries.py [ui_base]
Writes evidence/v5/queries/{*.png, smoke.json}. Exit 1 on failure.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_login  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "queries"
UI = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5500").rstrip("/")
BANNED = ("demo", "sample", "synthetic", "mock", "lorem")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    s = core_login.login("anne")
    errors: list[str] = []
    steps: list[dict] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_cookies([{"name": "cp_session", "value": s["cookie"], "url": UI}])
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"failed: {r.url}"))
        page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)

        def shot(name: str) -> None:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            body = page.inner_text("body").lower()
            bad = [w for w in BANNED if f" {w} " in f" {body} "]
            steps.append({"step": name, "banned_words": bad})
            if bad:
                errors.append(f"{name}: banned words {bad}")

        page.goto(f"{UI}/queries", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=queries-case-Q1]", timeout=30000)
        shot("01_queries_home")
        for c in ("Q1", "Q2", "Q3", "Q4", "Q5"):
            page.goto(f"{UI}/queries", wait_until="domcontentloaded")
            page.click(f"[data-testid=queries-case-{c}]")
            page.wait_for_selector("[data-testid=answer-1]", timeout=60000)
            page.wait_for_timeout(1500)
            page.click("[data-testid=answer-1-trace]")
            shot(f"02_query_{c}")
        page.goto(f"{UI}/queries", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=queries-tracker]")
        shot("03_tracker")
        # R10 Session B: the BRF studio is chat + flowchart; each quick start opens a flow, Lock → Run → Publish
        # (the full template flow is ops/smoke_brf_studio.py).
        page.goto(f"{UI}/brf", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=brf-quick-R1]")
        shot("04_brf_home")
        for r in ("R1", "R2", "R3", "R4"):
            page.goto(f"{UI}/brf?r={r}", wait_until="domcontentloaded")
            page.wait_for_selector(".react-flow__node", timeout=60000)
            page.wait_for_timeout(800)
            page.click("[data-testid=brf-lock]")
            page.wait_for_timeout(500)
            page.click("[data-testid=brf-run]")
            page.wait_for_selector("[data-testid=brf-grid]", timeout=60000)
            page.click("[data-testid=brf-publish]")
            page.wait_for_timeout(800)
            shot(f"05_brf_{r}")
        b.close()
    (OUT / "smoke.json").write_text(json.dumps({"ui": UI, "steps": steps, "errors": errors}, indent=2))
    print(json.dumps({"steps": len(steps), "errors": errors[:10]}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
