"""R14 i: screenshots of every D6-D13 panel, reached by clicking, at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_i_shots.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Writes docs/v5/r14_review/i/<step>_<size>.png (+ _panel.png of the dialog) and shots.json (found, page errors,
sideways-scroll probe, the plain-words lines). Uses a minted session (no password is read or printed).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "i"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731


def idle(page: Page, ms: int = 800, timeout: int = 45_000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(ms)


def settle(page: Page, scope: str, timeout: int = 180_000) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout / 1000:
        busy = page.locator(f"{scope} .animate-pulse").count() + page.locator(f"{scope} .animate-spin").count()
        if not busy:
            break
        page.wait_for_timeout(700)
    page.wait_for_timeout(500)


def open_deal(page: Page, ui: str, pid: str, step: str | None = None) -> None:
    page.goto(f"{ui}/deal-desk/{pid}", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
    idle(page, 1200, 90_000)
    if step:
        page.locator(T(f"dealdesk-step-{step}")).first.click()
        idle(page, 1500, 120_000)


def more(pid: str, key: str) -> Callable[[Page, str], tuple[str, dict]]:
    def f(page: Page, ui: str) -> tuple[str, dict]:
        open_deal(page, ui, pid)
        page.locator(T("dealdesk-more-button")).click()
        page.wait_for_selector(T("dealdesk-more-menu"), timeout=10_000)
        page.locator(T(f"dealdesk-intel-{key}")).click()
        dlg = T(f"dealdesk-intel-{key}-dialog")
        page.wait_for_selector(dlg, timeout=30_000)
        idle(page, 1500, 180_000)
        settle(page, dlg)
        return dlg, {"text": page.locator(dlg).inner_text()[:600]}
    return f


def menu(pid: str) -> Callable[[Page, str], tuple[str, dict]]:
    def f(page: Page, ui: str) -> tuple[str, dict]:
        open_deal(page, ui, pid)
        page.locator(T("dealdesk-more-button")).click()
        page.wait_for_selector(T("dealdesk-more-menu"), timeout=10_000)
        page.wait_for_timeout(500)
        return T("dealdesk-more-menu"), {"menu": page.locator(T("dealdesk-more-menu")).inner_text().split("\n")}
    return f


def step_chip(pid: str, step: str, panel: str) -> Callable[[Page, str], tuple[str, dict]]:
    def f(page: Page, ui: str) -> tuple[str, dict]:
        open_deal(page, ui, pid, step)
        page.wait_for_selector(T(f"i-step-{panel}"), timeout=120_000)
        page.locator(T(f"i-step-{panel}")).click()
        dlg = T(f"i-step-{panel}-dialog")
        page.wait_for_selector(dlg, timeout=30_000)
        idle(page, 1500, 180_000)
        settle(page, dlg)
        return dlg, {"text": page.locator(dlg).inner_text()[:600]}
    return f


def noor_ask(q: str) -> Callable[[Page, str], tuple[str, dict]]:
    def f(page: Page, ui: str) -> tuple[str, dict]:
        page.goto(f"{ui}/", wait_until="domcontentloaded")
        page.wait_for_selector(T("home-tabs"), timeout=120_000)
        idle(page, 1200, 60_000)
        page.locator(T("home-tab-ask")).click()
        page.wait_for_selector(T("cockpit-v4-question"), timeout=60_000)
        page.locator(T("cockpit-v4-question")).fill(q)
        page.locator(T("cockpit-v4-question")).press("Enter")
        page.wait_for_selector(T("intel-answer"), timeout=120_000)
        idle(page, 1500, 180_000)
        settle(page, T("intel-answer"))
        return T("intel-answer"), {"text": page.locator(T("intel-answer")).inner_text()[:500],
                                   "engine": page.locator(T("intel-answer")).get_attribute("data-intel")}
    return f


STEPS: list[tuple[str, str, Callable[[Page, str], tuple[str, dict]]]] = [
    ("00_dd06_more_menu", "More menu, Intelligence section", menu("DD-06")),
    ("01_dd06_frontier", "D6", more("DD-06", "frontier")),
    ("02_dd06_premortem", "D7", more("DD-06", "premortem")),
    ("03_dd06_precedents", "D8", more("DD-06", "precedents")),
    ("04_dd06_pricing", "D9", more("DD-06", "pricing")),
    ("05_dd06_revenue", "D10", more("DD-06", "revenue-check")),
    ("06_dd06_renewal_diff", "D11", more("DD-06", "renewal-diff")),
    ("07_dd06_group_contagion", "D12 Taif Central Trading", more("DD-06", "group-contagion")),
    ("08_dd06_committee_questions", "D13 K29", more("DD-06", "challenger")),
    ("10_twa_revenue", "D10 twin A not supported", more("R12-TWA", "revenue-check")),
    ("11_twa_renewal_diff", "D11 twin A", more("R12-TWA", "renewal-diff")),
    ("12_twa_committee_questions", "D13 twin A", more("R12-TWA", "challenger")),
    ("13_twb_frontier", "D6 twin B (unfunded: commission)", more("R12-TWB", "frontier")),
    ("14_twb_premortem", "D7 twin B", more("R12-TWB", "premortem")),
    ("20_dd06_structure_step_frontier", "D6 from the Structure step", step_chip("DD-06", "structure", "frontier")),
    ("21_dd06_review_step_contagion", "D12 from the Review step", step_chip("DD-06", "review", "group-contagion")),
    ("22_twa_proposal_step_renewal", "D11 from the Proposal step", step_chip("R12-TWA", "proposal", "renewal-diff")),
    ("30_noor_ask_premortem", "Noor intent D7", noor_ask("How could DD-06 go bad?")),
    ("31_noor_ask_rehearsal", "Noor intent D13", noor_ask("Rehearse the committee for DD-06.")),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict[str, Any]] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h in sizes:
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            for sid, items, fn in STEPS:
                if only and sid not in only:
                    continue
                page = bctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e, errs=errors: errs.append(str(e)[:300]))
                rec: dict[str, Any] = {"step": sid, "items": items, "size": f"{w}x{h}"}
                try:
                    sel, extra = fn(page, ui)
                    rec.update(extra)
                    rec["found"] = True
                    name = f"{sid}_{w}x{h}"
                    page.screenshot(path=str(OUT / f"{name}.png"))
                    el = page.locator(sel).last
                    if el.count():
                        inner = el.locator("> div").first if "dialog" in sel else el
                        (inner if inner.count() else el).screenshot(path=str(OUT / f"{name}_panel.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                    pw = page.locator(f"{sel} [data-testid$='-plain']")
                    rec["plain"] = pw.first.inner_text() if pw.count() else None
                except Exception as e:  # noqa: BLE001
                    rec["found"] = False
                    rec["error"] = str(e)[:400]
                    try:
                        page.screenshot(path=str(OUT / f"{sid}_{w}x{h}_FAILED.png"))
                    except Exception:  # noqa: BLE001
                        pass
                rec["page_errors"] = errors
                rec["doc_wider_than_viewport"] = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                print(sid, f"{w}x{h}", "ok" if rec["found"] else "MISSING", "errors" if errors else "", flush=True)
                report.append(rec)
                page.close()
            bctx.close()
        b.close()
    prev = json.loads((OUT / "shots.json").read_text()) if (OUT / "shots.json").exists() else []
    merged = {(r["step"], r["size"]): r for r in prev}
    merged.update({(r["step"], r["size"]): r for r in report})   # a partial run (--only) keeps the other steps
    (OUT / "shots.json").write_text(json.dumps(sorted(merged.values(), key=lambda r: (r["size"], r["step"])), indent=1, default=str))
    bad = [r for r in report if not r["found"] or r["page_errors"]]
    print(f"{len(report) - len(bad)}/{len(report)} ok")
    return 0 if not bad else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    raise SystemExit(run(a.ui, sz, {x for x in a.only.split(",") if x}))
