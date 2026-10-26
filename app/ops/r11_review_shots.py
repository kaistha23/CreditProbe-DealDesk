"""R11 Session R: browser walk-through of the review surfaces at 1440x900 and 1280x800 (screenshots to docs/v5/r11_review/).

Needs the Deal Desk API (8508), Core (8505) and the UI (5500) running; signs in through ops/core_login (password from
the environment, never printed).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core_login  # noqa: E402

UI = os.environ.get("UI_ORIGIN", "http://127.0.0.1:5500")
OUT = Path(__file__).resolve().parents[1] / "docs" / "v5" / "r11_review"
SHOTS = [
    ("review_workspace_case_a", "/deal-desk/review?case=PRP-A-GMC&view=workspace", "[data-testid=review-answer]", (1440, 900)),
    ("review_workspace_case_b", "/deal-desk/review?case=PRP-B-ASB&view=workspace", "[data-testid=review-answer]", (1440, 900)),
    ("review_workspace_dd01_clean", "/deal-desk/review?case=DD-01&view=workspace", "[data-testid=review-answer]", (1440, 900)),
    ("review_workspace_case_a_1280", "/deal-desk/review?case=PRP-A-GMC&view=workspace", "[data-testid=review-answer]", (1280, 800)),
    ("review_workspace_case_b_1280", "/deal-desk/review?case=PRP-B-ASB&view=workspace", "[data-testid=review-answer]", (1280, 800)),
    ("review_conditions_1280", "/deal-desk/review?view=conditions", "[data-testid=conditions-table]", (1280, 800)),
    ("review_list", "/deal-desk/review", "[data-testid=review-subjects-table]", (1440, 900)),
    ("review_conditions", "/deal-desk/review?view=conditions", "[data-testid=conditions-table]", (1440, 900)),
    ("review_rules", "/deal-desk/review?view=rules", "[data-testid=review-rules-table]", (1440, 900)),
    ("review_r9_case_a", "/deal-desk/review?case=PRP-A-GMC", "[data-testid=review-view]", (1440, 900)),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    bad = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").is_file() else None)
        for name, path, sel, (w, h) in SHOTS:
            if only and name not in only:
                continue
            ctx = b.new_context(viewport={"width": w, "height": h})
            core_login.add_session(ctx, "anne")
            p = ctx.new_page()
            errs: list[str] = []
            p.on("pageerror", lambda e: errs.append(str(e)[:200]))
            p.goto(UI + path, wait_until="domcontentloaded", timeout=180000)
            try:
                p.wait_for_selector(sel, timeout=180000)
                p.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001
                errs.append(f"selector {sel}: {type(e).__name__}")
            over = p.evaluate("""() => { const out = []; for (const el of document.querySelectorAll('[data-testid^=review], [data-testid^=condition], [data-testid^=memo]')) {
                  const r = el.getBoundingClientRect(); if (r.right > window.innerWidth + 1) out.push(el.dataset.testid); } return out.slice(0, 5); }""")
            p.screenshot(path=str(OUT / f"{name}.png"))
            if name.startswith("review_workspace") and not name.endswith("1280"):
                p.screenshot(path=str(OUT / f"{name}_full.png"), full_page=True)
            if name == "review_workspace_case_a":
                p.hover("[data-mark=contradicted] >> nth=0")
                p.wait_for_timeout(400)
                p.screenshot(path=str(OUT / "review_workspace_case_a_hover.png"))
                p.click("[data-testid=review-draft-toggle]")
                p.wait_for_selector("[data-testid=review-draft-sections]", timeout=60000)
                p.wait_for_timeout(800)
                p.screenshot(path=str(OUT / "review_workspace_case_a_draft.png"))
            print(name, "ok" if not errs and not over else f"issues {errs} overflow {over}")
            bad += bool(errs or over)
            ctx.close()
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
