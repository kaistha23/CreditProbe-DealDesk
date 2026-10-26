"""Browser smoke for the BRF studio as chat + flowchart (PLAN_R10 Session B, item 13).

    python ops/smoke_brf_studio.py [ui_base] [--stub-core]

Steps: open /brf → attach the template in the chat → "complete all data for this template" → the flowchart draws →
add a node, delete a node (canvas) → edit by chat (GL reconciliation, collateral, remove) → Lock → Run (populated
return with checks) → Publish; plus a quick start. Screens at 1440×900 to evidence/v5/brf_studio/. Exit 1 on failure.

`--stub-core` answers the Core service's session call with a fictional user (for a sandbox without the Core
service); without it the script signs in through ops/core_login (password from the environment, never printed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "brf_studio"
TEMPLATE = V5 / "demo_inputs" / "brf" / "BRF_Credit_Quality_Return.xlsx"
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
UI = (ARGS[0] if ARGS else "http://127.0.0.1:5500").rstrip("/")
STUB = "--stub-core" in sys.argv
BANNED = ("demo", "sample", "synthetic", "mock", "lorem")
USER = {"username": "lhaddad", "name": "Lina Haddad", "role": "CRO", "title": "Chief Risk Officer", "department": "Risk", "initials": "LH",
        "books": ["corporate", "retail"], "team": "risk", "is_admin": True}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    steps: list[dict] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-proxy-server"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        if STUB:
            def core(route):
                url = route.request.url
                if url.endswith("/api/v1/auth/session"):
                    return route.fulfill(json={"authenticated": True, "user": USER, "effective_user": USER, "viewing_as": None, "is_admin": True})
                return route.fulfill(json=[] if route.request.method == "GET" else {"ok": True})
            ctx.route("http://127.0.0.1:8505/**", core)
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import core_login  # noqa: PLC0415
            ctx.add_cookies([{"name": "cp_session", "value": core_login.login("anne")["cookie"], "url": UI}])
        page = ctx.new_page()
        # with --stub-core the shell's notification bell gets an empty stub reply; its error is not the studio's
        page.on("pageerror", lambda e: None if STUB and "NotificationBell" in (getattr(e, "stack", "") or "") else errors.append(f"pageerror: {e}"))
        page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 and "/brf/" in r.url else None)

        def shot(name: str, **extra) -> None:
            page.screenshot(path=str(OUT / f"{name}.png"))
            body = page.inner_text("body").lower()
            bad = [w for w in BANNED if f" {w} " in f" {body} "]
            # G-BOUNDS: no horizontal page overflow
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            steps.append({"step": name, "banned_words": bad, "h_overflow": overflow, **extra})
            if bad:
                errors.append(f"{name}: banned words {bad}")
            if overflow:
                errors.append(f"{name}: horizontal overflow")

        def last_reply() -> str:
            return page.locator("[data-testid=brf-msg-studio]").last.inner_text()

        def say(text: str) -> str:
            n = page.locator("[data-testid=brf-msg-studio]").count()
            page.fill("[data-testid=brf-say]", text)
            page.click("[data-testid=brf-say-send]")
            page.wait_for_function(f"document.querySelectorAll('[data-testid=brf-msg-studio]').length > {n}", timeout=60000)
            page.wait_for_timeout(900)
            return last_reply()

        page.goto(f"{UI}/brf", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=brf-chat]", timeout=90000)
        page.wait_for_selector("[data-testid=brf-quick-R1]", timeout=30000)
        shot("01_open")

        # 1. upload the template in the chat and ask to complete all data
        page.set_input_files("[data-testid=brf-file]", str(TEMPLATE))
        page.wait_for_selector("[data-testid=brf-attached]")
        reply = say("complete all data for this template")
        page.wait_for_selector(".react-flow__node", timeout=30000)
        n_nodes = page.locator(".react-flow__node").count()
        vals = page.locator("[data-testid=brf-node-value]").count()
        shot("02_flow_from_template", reply=reply, nodes=n_nodes, values=vals)
        if n_nodes < 20 or "Mapped" not in reply:
            errors.append(f"template flow: {n_nodes} nodes; reply {reply[:120]}")
        # chat and flow above the fold
        box = page.locator("[data-testid=brf-flow]").bounding_box()
        if not box or box["y"] > 600:
            errors.append(f"flow not above the fold: {box}")

        # 2. canvas edits: add a check, select a calculation and delete it
        before = page.locator(".react-flow__node").count()
        page.click("[data-testid=brf-add-check]")
        page.wait_for_timeout(400)
        after_add = page.locator(".react-flow__node").count()
        page.locator(".react-flow__node", has_text="Stage 2 coverage").first.click()
        page.wait_for_selector("[data-testid=brf-inspector]")
        shot("03_inspector")
        page.click("[data-testid=brf-insp-delete]")
        page.wait_for_timeout(1500)
        after_del = page.locator(".react-flow__node").count()
        steps.append({"step": "canvas_edit", "before": before, "after_add": after_add, "after_delete": after_del})
        if not (after_add == before + 1 and after_del == after_add - 1):
            errors.append(f"canvas edit counts {before} → {after_add} → {after_del}")
        unmapped = page.locator(".react-flow__node", has_text="Not mapped").count()
        if unmapped < 1:
            errors.append("deleting the coverage calculation did not recompute the output line")

        # 3. chat edits
        for msg in ("add a reconciliation to the GL", "take collateral from the collateral dataset", "remove the check Values agree",
                    "add a check that Stage 3 coverage is at least 40%"):
            r = say(msg)
            steps.append({"step": f"chat: {msg}", "reply": r})
            if "could not" in r.lower() or "upload a brf template" in r.lower():
                errors.append(f"chat '{msg}': {r[:120]}")
        shot("04_after_chat_edits")

        # 4. Lock → Run → Publish
        page.click("[data-testid=brf-lock]")
        page.wait_for_timeout(500)
        page.click("[data-testid=brf-run]")
        page.wait_for_selector("[data-testid=brf-result]", timeout=60000)
        page.locator("[data-testid=brf-result]").scroll_into_view_if_needed()
        shot("05_run", result=page.locator("[data-testid=brf-result]").inner_text()[:300])
        with page.expect_download(timeout=30000) as dl:
            page.click("[data-testid=brf-export]")
        steps.append({"step": "excel", "file": dl.value.suggested_filename})
        page.click("[data-testid=brf-publish]")
        page.wait_for_timeout(1200)
        if "Published" not in last_reply():
            errors.append(f"publish: {last_reply()[:120]}")
        page.evaluate("window.scrollTo(0, 0)")
        shot("06_published")

        # 5. a quick start and the chat run command
        page.click("[data-testid=brf-quick-R4]")
        page.wait_for_function("document.querySelector('[data-testid=brf-thread]').innerText.includes('R4')", timeout=60000)
        page.wait_for_timeout(1200)
        r = say("run")
        page.wait_for_selector("[data-testid=brf-result]", timeout=60000)
        shot("07_quick_R4_run", reply=r)
        b.close()
    (OUT / "smoke.json").write_text(json.dumps({"ui": UI, "steps": steps, "errors": errors}, indent=2, ensure_ascii=False))
    print(json.dumps({"steps": len(steps), "errors": errors[:12]}, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
