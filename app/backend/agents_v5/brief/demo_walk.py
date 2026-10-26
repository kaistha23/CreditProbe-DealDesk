"""The scripted 90-second Noor demo (R11_FEEDBACK I12), driven in a real browser and timed.

    .venv/bin/python -m backend.agents_v5.brief.demo_walk [--ui http://127.0.0.1:5500] [--out docs/v5/r12_noor]

Needs the UI, the Core service (identity) and the Deal Desk service (Noor's endpoints) running. Mints a session for
the administrator in the identity store (no password is read or printed), clears today's "brief spoke" flag so the
brief speaks first, then plays the path without typing:

  1. sign-in lands on the Cockpit; the brief opens by itself in Noor's panel
  2. Why? on the Construction line; the trace steps play out live
  3. the one-line answer and its Plotly chart
  4. What should we do?: three options with the engines' numbers
  5. Send to committee on the recommended option: the committee item is created

Writes a screenshot per step at 1440x900, the panel at 1280x800, and `demo_timings.json` (seconds from sign-in to
each step). Exit 1 if the path takes 90 seconds or more, or a step is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[3]
ITEM = "appetite:Construction"


def mint(username: str = "anne") -> str:
    from backend.identity_v5 import store as ids
    ids.ensure()
    tok = secrets.token_urlsafe(32)
    with ids.db() as con:
        con.execute("INSERT INTO sessions(token_hash, username, view_as, created_at, expires_at) VALUES(?,?,?,?,?)",
                    (ids._hash_token(tok), username, None, ids.now(), ids._later(120)))
        con.commit()
    return tok


def overflow(page, sel: str) -> list[str]:
    return page.evaluate("""(sel) => {
      const root = document.querySelector(sel); if (!root) return ['missing'];
      const r = root.getBoundingClientRect(), out = [];
      for (const e of root.querySelectorAll('*')) {
        if (e.offsetParent === null || e.closest('svg') || e.closest('.js-plotly-plot')) continue;
        const b = e.getBoundingClientRect();
        if (b.width && (b.right > r.right + 1 || b.left < r.left - 1)) out.push((e.textContent || e.tagName).trim().slice(0, 60));
        if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX === 'visible' && e.children.length === 0)
          out.push('text overflow: ' + (e.textContent || '').trim().slice(0, 60));
      }
      return out.slice(0, 10);
    }""", sel)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--out", default=str(V5 / "docs" / "v5" / "r12_noor"))
    ap.add_argument("--start", default="/", help="the first screen after sign-in")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    t: dict[str, float] = {}
    checks: dict[str, object] = {}
    with sync_playwright() as pw:
        exe = os.environ.get("NOOR_DEMO_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        host = a.ui.split("//", 1)[1].split(":")[0].split("/")[0]
        ctx.add_cookies([{"name": "cp_session", "value": mint(), "domain": host, "path": "/", "httpOnly": True,
                          "sameSite": "Lax"}])
        page = ctx.new_page()
        page.add_init_script("""try { for (const k of Object.keys(localStorage)) if (k.startsWith('noor.spoke.')
          || k === 'cp.viewingAs') localStorage.removeItem(k); for (const k of Object.keys(sessionStorage))
          if (k.startsWith('noor.thread.')) sessionStorage.removeItem(k); } catch (e) {}""")
        t0 = time.monotonic()
        page.goto(a.ui + a.start, wait_until="domcontentloaded")
        panel = page.locator("[data-testid=noor-panel]")
        panel.locator("[data-testid=noor-turn-brief]").first.wait_for(timeout=60_000)
        t["1_brief_spoke_first"] = time.monotonic() - t0
        checks["opening"] = panel.locator("[data-testid=noor-opening]").first.inner_text()
        checks["lines"] = panel.locator("[data-testid=noor-turn-brief] li").count()
        page.wait_for_timeout(1500)  # the presenter reads the brief
        page.screenshot(path=str(out / "1_brief.png"))
        line = panel.locator(f'[data-testid="noor-line-{ITEM}"]').first
        if line.count() == 0:
            panel.locator("[data-testid=noor-more]").first.click()
        line.locator("[data-testid=noor-why]").click()
        t["2_why_clicked"] = time.monotonic() - t0
        panel.locator("[data-testid=noor-trace-step]").first.wait_for(timeout=30_000)
        page.wait_for_timeout(900)
        page.screenshot(path=str(out / "2_trace_live.png"))
        panel.locator("[data-testid=noor-why-chart] .js-plotly-plot, [data-testid=noor-why-chart] svg").first.wait_for(timeout=30_000)
        t["3_answer_and_chart"] = time.monotonic() - t0
        checks["why"] = panel.locator("[data-testid=noor-why-answer]").last.inner_text()
        checks["trace_steps"] = panel.locator("[data-testid=noor-trace-step]").count()
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "3_why_answer.png"))
        panel.locator("[data-testid=noor-why-chart]").last.screenshot(path=str(out / "3b_why_chart.png"))
        panel.locator("[data-testid=noor-why-options]").last.click()
        panel.locator("[data-testid=noor-option-recommended]").last.wait_for(timeout=30_000)
        t["4_three_options"] = time.monotonic() - t0
        checks["options"] = [panel.locator(f"[data-testid=noor-option-{k}] h4").last.inner_text()
                             for k in ("as_asked", "recommended", "hold")]
        page.wait_for_timeout(1500)
        panel.locator("[data-testid=noor-option-recommended]").last.scroll_into_view_if_needed()
        page.screenshot(path=str(out / "4_options.png"))
        panel.locator("[data-testid=noor-committee-recommended]").last.click()
        panel.locator("[data-testid=noor-turn-committee]").last.wait_for(timeout=30_000)
        t["5_committee_item_created"] = time.monotonic() - t0
        checks["committee"] = panel.locator("[data-testid=noor-turn-committee]").last.inner_text()
        page.screenshot(path=str(out / "5_committee.png"))
        # Not timed: point-and-ask "Who drives it?" on the Why answer names the borrowers.
        panel.locator("[data-testid=noor-why-drivers]").last.click()
        panel.locator("[data-testid=noor-drivers-table]").last.wait_for(timeout=30_000)
        checks["who_drives_it"] = panel.locator("[data-testid=noor-turn-drivers] [data-testid=answer-headline]").last.inner_text()
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "5b_who_drives_it.png"))
        checks["overflow_1440"] = overflow(page, "[data-testid=noor-panel]")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / "6_panel_1280x800.png"))
        checks["overflow_1280"] = overflow(page, "[data-testid=noor-panel]")
        # Show me keeps the panel open on the next module.
        page.set_viewport_size({"width": 1440, "height": 900})
        panel.locator("[data-testid=noor-chip-brief]").click()
        panel.locator("[data-testid=noor-turn-brief]").last.wait_for(timeout=30_000)
        # R13 H (J3): a line's actions are Why · What to do · Open; Show me sits under the Why answer.
        panel.locator("[data-testid=noor-turn-brief]").last.locator(f'[data-testid="noor-line-{ITEM}"] [data-testid=noor-why]').click()
        panel.locator("[data-testid=noor-why-show]").last.click(timeout=30_000)
        page.wait_for_url("**/deal-desk**", timeout=60_000)
        page.wait_for_timeout(2500)
        checks["show_me_url"] = page.url.replace(a.ui, "")
        checks["panel_open_after_show_me"] = page.locator("[data-testid=noor-panel]").count() == 1
        page.screenshot(path=str(out / "7_show_me_deal_desk.png"))
        # Viewing as (admin account): switch to RM and back.
        page.locator("[data-testid=viewing-as] button").first.click()
        page.locator("[data-testid=viewing-as-rm]").click()
        page.wait_for_timeout(800)
        checks["viewing_as"] = page.locator("[data-testid=viewing-as-current]").inner_text()
        checks["panel_persona"] = page.locator("[data-testid=noor-context]").inner_text()
        checks["html_data_viewing_as"] = page.evaluate("document.documentElement.dataset.viewingAs || ''")
        page.screenshot(path=str(out / "8_viewing_as_rm.png"))
        browser.close()
    total = t["5_committee_item_created"]
    report = {"timings_s": {k: round(v, 1) for k, v in t.items()}, "total_s": round(total, 1), "budget_s": 90,
              "pass": total < 90 and checks.get("trace_steps", 0) >= 3 and len(checks.get("options", [])) == 3,
              "checks": checks}
    (out / "demo_timings.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
