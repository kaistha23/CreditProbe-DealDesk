"""UAT sweep, PLAN_R4 G1 (part "r4-g1"): no loose explanatory text, provenance notes or warnings on any screen.

Every screen's free-text paragraphs that are not page content are listed in evidence/v5/r4/g1_loose_text.json (the
inventory Anne reviews); a screen fails on any of the known phrases (ops/loose_text_scan.KNOWN). Explanations that
are still needed sit behind an (i) popover: the step opens one on each module and checks it says what moved there.
Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from loose_text_scan import ROUTES, scan_page, settle

V5 = Path(__file__).resolve().parents[1]
EVIDENCE = V5 / "evidence" / "v5" / "r4"

#: Where an explanation moved into an (i) popover, and a phrase it must still say when opened.
POPOVERS = [("/playbook", "playbook-home", "Committee packs"),
            ("/workspace", "ws-home", "Your home page"),
            ("/policy-docs", "policy-versions", "new version")]
#: What-If's chat explanation is A1's (i) (a title on whatif-chat-info), checked by A1's own sweep steps.


def g1_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    inventory: dict[str, Any] = {}
    s.start("all", "G1-1", "No known loose-text phrase on any screen; every loose paragraph listed for review")
    for route in ROUTES:
        page.goto(UI + route, wait_until="domcontentloaded")
        settle(page)
        r = scan_page(page)
        inventory[route] = r
        s.check(f"{route}: no known loose-text phrase", not r["known"], "none", r["known"][:2])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "g1_loose_text.json").write_text(json.dumps(
        {"routes": len(inventory), "loose_paragraphs": sum(len(v["loose"]) for v in inventory.values()),
         "known_hits": sum(len(v["known"]) for v in inventory.values()), "by_route": inventory}, indent=1))
    s.check("inventory written", (EVIDENCE / "g1_loose_text.json").exists())

    s.start("all", "G1-2", "Explanations that are still needed open from the (i) next to their title")
    for route, scope, phrase in POPOVERS:
        page.goto(UI + route, wait_until="domcontentloaded")
        settle(page)
        box = page.locator(f'[data-testid="{scope}"]').first
        button = box.locator('button[aria-label="What is this screen for?"]').first
        if not button.count():
            button = page.locator('button[aria-label="What is this screen for?"]').first
        ok = button.count() > 0
        s.check(f"{route}: the (i) is there", ok)
        if not ok:
            continue
        before = page.inner_text("body")
        s.check(f"{route}: the explanation is not inline", phrase not in before, "absent", phrase)
        button.click()
        page.wait_for_timeout(300)
        s.check(f"{route}: the (i) opens it", phrase in page.inner_text("body"), phrase, "")
        page.keyboard.press("Escape")
    s.finish()
