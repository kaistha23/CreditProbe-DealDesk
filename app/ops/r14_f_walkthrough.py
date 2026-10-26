"""PLAN_R14 Session F: click-through walk of the Deal Desk flow screens F changed, at 1440x900 and 1280x800.

  .venv/bin/python ops/r14_f_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Every screen is reached by clicking (N6); the only goto is the first page after sign-in. Screens:
docs/v5/r14_review/f/<step>_<size>.png; report docs/v5/r14_review/f/walkthrough.json.

Items: K20 K23 (Stress header button over chosen structures, matrix, fails before stress, stress-proofing), K25 (structure
set, Select, sticky bar with the reason), K24 (Recommendation never blank), K21 (pipeline test on this deal's lines),
K35 (Propose for monitoring on the deal, Book and Early Warning; Monitoring page with maker-checker; Borrower 360 line),
K31 slot (Proposal check step), K25 (3) SWOT card on Analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint  # noqa: E402
from r14_u_walkthrough import DEV_OVERLAY, idle, nav, settle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r14_review" / "f"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LONG = 240_000


def to(page: Page, sel: str) -> None:
    page.locator(sel).first.scroll_into_view_if_needed()
    page.wait_for_timeout(300)


def open_deal(page: Page, pid: str, query: str) -> dict:
    page.keyboard.press("Escape")
    nav(page, "deal-desk", "dealdesk-home")
    if page.locator(T("dealdesk-tab-monitoring-panel")).count() or page.locator(T("dealdesk-tab-book-panel")).count():
        page.locator(T("dealdesk-back-home")).click()
    page.locator(T("dealdesk-mode-single")).click()
    page.wait_for_selector(T("dealdesk-table"), timeout=120_000)
    page.locator(T("dealdesk-search")).fill(query)
    page.wait_for_timeout(700)
    page.locator(T(f"dealdesk-row-{pid}")).click()
    page.wait_for_selector(T("dealdesk-stepper"), timeout=LONG)
    idle(page, 1200)
    return {"url": page.url}


def step(page: Page, key: str, ready: str) -> None:
    page.locator(T(f"dealdesk-step-{key}")).click()
    page.wait_for_selector(T(ready), timeout=LONG)
    settle(page)


# ---------------------------------------------------------------- steps
Step = tuple[str, str, Callable[[Page, str, dict], dict]]


def s_home(page: Page, ui: str, ctx: dict) -> dict:
    """The first page after sign-in is Deal Desk (the only goto); every other screen is reached by clicking."""
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=240_000)
    idle(page, 800)
    return {}


def s_twa_open(page: Page, ui: str, ctx: dict) -> dict:
    out = open_deal(page, "R12-TWA", "al sahel")
    labels = page.locator(f'{T("dealdesk-stepper")} button').all_inner_texts()
    stress = page.locator(T("dealdesk-stress-button"))
    out.update(steps=[" ".join(x.split()) for x in labels], stress_disabled=stress.is_disabled(), stress_title=stress.get_attribute("title"))
    return out


def s_proposal_check(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "proposal-check", "dealdesk-step-proposal-check-view")
    return {"slot": page.locator(T("dealdesk-step-proposal-check-view")).inner_text()[:160]}


def s_analysis_swot(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "analysis", "dealdesk-step-analysis-view")
    page.wait_for_selector(T("flow-swot-card"), timeout=LONG)
    to(page, T("flow-swot-card"))
    return {"swot": page.locator(T("flow-swot-card")).inner_text()[:200]}


def s_structure_set(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "structure", "flow-structure-table")
    to(page, T("flow-structure-set"))
    rows = page.locator('[data-testid^="flow-structure-row-"]')
    bar = page.locator(T("flow-selected-bar"))
    return {"rows": rows.count(), "bar": bar.inner_text()[:240], "bar_enabled": bar.get_attribute("data-enabled"),
            "stress_enabled": not page.locator(T("dealdesk-stress-button")).is_disabled()}


def s_structure_select(page: Page, ui: str, ctx: dict) -> dict:
    btn = page.locator('[data-testid^="flow-structure-select-alternative"]')
    key = "ask"
    if btn.count():
        key = (btn.first.get_attribute("data-testid") or "").replace("flow-structure-select-", "")
        btn.first.click()
    else:
        page.locator(T("flow-structure-select-ask")).click()
    page.wait_for_selector(T(f"flow-structure-selected-{key}"), timeout=LONG)
    to(page, T("flow-selected-bar"))
    out = {"selected": key, "bar": page.locator(T("flow-selected-bar")).inner_text()[:240]}
    # back to the recommended structure (the default) for the rest of the walk
    page.locator(T("flow-structure-select-recommended")).click()
    page.wait_for_selector(T("flow-structure-selected-recommended"), timeout=LONG)
    return out


def s_stress_choose(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-stress-button")).click()
    page.wait_for_selector(T("flow-stress-choices"), timeout=LONG)
    settle(page)
    picks = page.locator('[data-testid^="flow-stress-pick-"]')
    return {"choices": picks.count(), "ticked": page.locator('[data-testid^="flow-stress-pick-"]:checked').count()}


def s_stress_run(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("flow-stress-run")).click()
    page.wait_for_selector(T("flow-stress-matrix"), timeout=LONG)
    settle(page)
    to(page, T("flow-stress-matrix"))
    rows = page.locator('[data-testid^="flow-matrix-row-"]')
    return {"rows": rows.count(), "statuses": rows.evaluate_all("els => els.map(e => e.dataset.status)"),
            "regime": page.locator(T("flow-regime-line")).inner_text()[:200]}


def s_stress_force(page: Page, ui: str, ctx: dict) -> dict:
    f = page.locator('[data-testid^="flow-matrix-force-"]')
    if not f.count():
        return {"forced": False}
    key = (f.first.get_attribute("data-testid") or "").replace("flow-matrix-force-", "")
    f.first.click()
    page.wait_for_selector(f'[data-testid="flow-matrix-row-{key}"][data-status="stressed"]', timeout=LONG)
    settle(page)
    to(page, T("flow-interpreters"))
    return {"forced": True, "cells": page.locator('[data-testid^="flow-cell-"]').count()}


def s_stress_proof(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("flow-stress-proof"))
    page.locator(T("flow-proof-target-moderate")).click()
    page.locator(T("flow-proof-run")).click()
    page.wait_for_selector(T("flow-proof-result"), timeout=LONG)
    settle(page)
    to(page, T("flow-proof-result"))
    r = page.locator(T("flow-proof-result"))
    return {"survives": r.get_attribute("data-survives"), "text": r.inner_text()[:300]}


def s_recommendation(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "recommendation", "flow-rec-points")
    to(page, T("flow-rec-decision"))
    return {"decision": page.locator(T("flow-rec-decision-chip")).inner_text(), "approval": page.locator(T("flow-rec-approval")).inner_text(),
            "points": page.locator(f'{T("flow-rec-points")} li').count(),
            "prepare_button": page.locator(T("dealdesk-prepare-proposal")).count()}


def s_rec_findings(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("flow-rec-findings"))
    f = page.locator(T("flow-rec-finding"))
    return {"findings": f.count(), "cures": sorted(set(f.evaluate_all("els => els.map(e => e.dataset.cure)")))}


def s_rec_monitoring(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("flow-rec-monitoring"))
    return {"text": page.locator(T("flow-rec-monitoring")).inner_text()[:200]}


def s_pipeline(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "structure", "flow-structure-table")
    if page.locator(T("dealdesk-panel-pipeline")).count() == 0:
        return {"panel": False}
    to(page, T("dealdesk-panel-pipeline"))
    if not page.locator(T("dealdesk-pipeline-test-button")).is_visible():
        page.locator(f'{T("dealdesk-panel-pipeline")} button').first.click()
        page.wait_for_timeout(500)
    page.locator(T("dealdesk-pipeline-test-button")).click()
    page.wait_for_selector(T("dealdesk-pipeline-lines"), timeout=LONG)
    settle(page)
    to(page, T("dealdesk-pipeline-test-result"))
    lines = page.locator(T("dealdesk-pipeline-line"))
    return {"purpose": page.locator(T("dealdesk-pipeline-purpose")).inner_text()[:160], "lines": lines.count(),
            "label": page.locator(T("dealdesk-pipeline-label")).inner_text()[:160]}


def s_propose(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-propose-monitoring")).click()
    page.wait_for_selector(T("monitoring-reason"), timeout=LONG)
    settle(page, "[data-testid='monitoring-propose-dialog']")
    out = {"reason": page.locator(T("monitoring-reason")).input_value()[:200], "triggers": page.locator(f'{T("monitoring-triggers")} li').count()}
    page.screenshot(path=str(OUT / f"{ctx['sid']}_form_{ctx['tag']}.png"))
    page.locator(T("monitoring-submit")).click()
    page.wait_for_selector(T("monitoring-propose-dialog"), state="detached", timeout=LONG)
    page.wait_for_timeout(500)
    out["button"] = page.locator(T("dealdesk-propose-monitoring")).inner_text()
    return out


def s_dd06_open(page: Page, ui: str, ctx: dict) -> dict:
    out = open_deal(page, "DD-06", "dhahran")
    step(page, "structure", "flow-structure-table")
    to(page, T("flow-structure-set"))
    out["bar"] = page.locator(T("flow-selected-bar")).inner_text()[:200]
    return out


def s_dd06_proof(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-stress-button")).click()
    page.wait_for_selector(T("flow-stress-proof"), timeout=LONG)
    to(page, T("flow-stress-proof"))
    page.locator(T("flow-proof-run")).click()
    page.wait_for_selector(T("flow-proof-result"), timeout=LONG)
    settle(page)
    to(page, T("flow-stress-matrix"))
    return {"survives": page.locator(T("flow-proof-result")).get_attribute("data-survives"),
            "rows": page.locator('[data-testid^="flow-matrix-row-"]').count()}


def s_dd06_rec(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "recommendation", "flow-rec-points")
    to(page, T("flow-rec-decision"))
    return {"decision": page.locator(T("flow-rec-decision-chip")).inner_text()}


def s_twb_rec(page: Page, ui: str, ctx: dict) -> dict:
    open_deal(page, "R12-TWB", "gulf meridian")
    step(page, "recommendation", "flow-rec-points")
    to(page, T("flow-rec-decision"))
    return {"decision": page.locator(T("flow-rec-decision-chip")).inner_text()}


def s_monitoring_page(page: Page, ui: str, ctx: dict) -> dict:
    page.keyboard.press("Escape")
    nav(page, "deal-desk", "dealdesk-home")
    page.locator(T("dealdesk-tab-monitoring")).click()
    page.wait_for_selector(T("monitoring-page"), timeout=LONG)
    settle(page)
    return {"counts": page.locator(T("monitoring-counts")).inner_text().replace("\n", " ")[:200],
            "proposed": page.locator(f'{T("monitoring-proposed-table")} [data-testid="monitoring-row"]').count()}


def s_monitoring_approve(page: Page, ui: str, ctx: dict) -> dict:
    a = page.locator('[data-testid^="monitoring-approve-MP14-SEED"]')
    if not a.count():
        a = page.locator('[data-testid^="monitoring-approve-"]:not([disabled])')
    if not a.count():
        return {"approved": False}
    a.first.click()
    page.wait_for_selector(T("monitoring-message"), timeout=LONG)
    settle(page)
    return {"message": page.locator(T("monitoring-message")).inner_text()[:240]}


def s_book_monitor(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-tab-book")).click()
    page.wait_for_selector(T("book-row-monitor"), timeout=LONG)
    settle(page)
    n = page.locator(T("book-row-monitor")).count()
    page.locator(T("book-row-monitor")).first.click()
    page.wait_for_selector(T("monitoring-reason"), timeout=LONG)
    settle(page, "[data-testid='monitoring-propose-dialog']")
    out = {"buttons": n, "reason": page.locator(T("monitoring-reason")).input_value()[:200]}
    page.screenshot(path=str(OUT / f"{ctx['sid']}_form_{ctx['tag']}.png"))
    page.locator(T("monitoring-submit")).click()
    page.wait_for_selector(T("monitoring-propose-dialog"), state="detached", timeout=LONG)
    return out


def s_ews_monitor(page: Page, ui: str, ctx: dict) -> dict:
    page.keyboard.press("Escape")
    nav(page, "early-warning", "ews-level-portfolio")
    settle(page)
    page.locator('[data-testid="ews-children"] [data-testid^="ews-open-"]').first.click()
    page.wait_for_selector(T("ews-level-segment"), timeout=LONG)
    settle(page)
    page.locator('[data-testid="ews-children"] [data-testid^="ews-open-"]').first.click()
    page.wait_for_selector(T("ews-level-subsegment"), timeout=LONG)
    settle(page)
    page.locator(T("ews-open-warned")).click()
    page.wait_for_selector('[data-testid^="ews-monitor-CB"]', timeout=LONG)
    settle(page)
    n = page.locator('[data-testid^="ews-monitor-CB"]').count()
    page.locator('[data-testid^="ews-monitor-CB"]').first.click()
    page.wait_for_selector(T("monitoring-reason"), timeout=LONG)
    settle(page, "[data-testid='monitoring-propose-dialog']")
    out = {"buttons": n, "reason": page.locator(T("monitoring-reason")).input_value()[:200]}
    page.locator(T("monitoring-submit")).click()
    page.wait_for_selector(T("monitoring-propose-dialog"), state="detached", timeout=LONG)
    return out


def s_b360_line(page: Page, ui: str, ctx: dict) -> dict:
    """The borrower proposed from the Book (step 42) shows the monitoring line on Borrower 360 (opened from its Book row)."""
    page.keyboard.press("Escape")
    nav(page, "deal-desk", "dealdesk-home")
    page.locator(T("dealdesk-tab-book")).click()
    page.wait_for_selector(T("book-row-monitor"), timeout=LONG)
    settle(page)
    page.locator('[data-testid="book-row"] [data-b360-button="1"]').first.click()
    page.wait_for_selector(T("b360-header"), timeout=LONG)
    settle(page)
    try:
        page.wait_for_selector(T("monitoring-line"), timeout=30_000)
    except Exception:  # noqa: BLE001
        pass
    ln = page.locator(T("monitoring-line"))
    return {"line": ln.inner_text()[:240] if ln.count() else None}


STEPS: list[Step] = [
    ("00_home", "", s_home),
    ("10_twa_open_steps", "K23 K31", s_twa_open),
    ("11_twa_proposal_check", "K31", s_proposal_check),
    ("12_twa_analysis_swot", "K25", s_analysis_swot),
    ("13_twa_structure_set", "K23 K25", s_structure_set),
    ("14_twa_structure_select", "K25", s_structure_select),
    ("15_twa_stress_choose", "K20 K23", s_stress_choose),
    ("16_twa_stress_matrix", "K20 K23", s_stress_run),
    ("17_twa_stress_forced", "K23", s_stress_force),
    ("18_twa_stress_proof", "K23", s_stress_proof),
    ("19_twa_recommendation", "K24", s_recommendation),
    ("20_twa_rec_findings", "K24", s_rec_findings),
    ("21_twa_rec_monitoring", "K24", s_rec_monitoring),
    ("22_twa_pipeline_lines", "K21", s_pipeline),
    ("23_twa_propose_monitoring", "K35", s_propose),
    ("30_dd06_structure", "K25", s_dd06_open),
    ("31_dd06_stress_proof", "K23", s_dd06_proof),
    ("32_dd06_recommendation", "K24", s_dd06_rec),
    ("33_twb_recommendation", "K24", s_twb_rec),
    ("40_monitoring_page", "K35", s_monitoring_page),
    ("41_monitoring_approve", "K35", s_monitoring_approve),
    ("42_book_monitor", "K35", s_book_monitor),
    ("43_b360_monitoring_line", "K35", s_b360_line),
    ("44_ews_monitor", "K35", s_ews_monitor),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    path = OUT / "walkthrough.json"
    with sync_playwright() as pw:
        exe = "/opt/pw-browsers/chromium"
        b = pw.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        for w, h in sizes:
            tag = f"{w}x{h}"
            bctx = b.new_context(viewport={"width": w, "height": h})
            bctx.add_cookies([{"name": "cp_session", "value": token, "domain": "127.0.0.1", "path": "/"}])
            page = bctx.new_page()
            page.set_default_timeout(90_000)
            ctx: dict[str, Any] = {"tag": tag}
            errors: list[str] = []
            console: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.on("console", lambda m: console.append(m.text[:300]) if m.type == "error" else None)
            for sid, items, fn in STEPS:
                if only and not any(sid.startswith(o) for o in only) and sid != "00_home":
                    continue
                ctx["sid"] = sid
                errors.clear()
                console.clear()
                t0 = time.time()
                rec: dict[str, Any] = {"step": sid, "items": items, "size": tag}
                try:
                    rec["checks"] = fn(page, ui, ctx)
                    rec["found"] = True
                except Exception as e:  # noqa: BLE001 - recorded as a miss, the walk goes on
                    rec["found"] = False
                    rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:240]}"
                rec["seconds"] = round(time.time() - t0, 1)
                try:
                    page.screenshot(path=str(OUT / f"{sid}_{tag}.png"))
                    rec["probe"] = page.evaluate(PROBE, None)
                    rec["dev_overlay"] = page.evaluate(DEV_OVERLAY)
                except Exception as e:  # noqa: BLE001
                    rec["probe_error"] = str(e)[:120]
                rec["page_errors"] = list(errors)
                rec["console_errors"] = [c for c in console if "Failed to load resource" not in c]
                rec["clean"] = not rec["page_errors"] and not rec["console_errors"]
                report.append(rec)
                print(f"{tag} {sid} {'ok' if rec['found'] else 'MISS ' + rec.get('error', '')} "
                      f"{'clean' if rec['clean'] else 'ERRORS ' + json.dumps(rec['page_errors'] + rec['console_errors'])[:300]} {rec['seconds']}s "
                      f"{json.dumps(rec.get('checks'), default=str)[:300]}", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str))
            bctx.close()
        b.close()
    miss = [r for r in report if not r["found"]]
    dirty = [r for r in report if not r["clean"]]
    print(f"{len(report) - len(miss)} / {len(report)} found; {len(report) - len(dirty)} / {len(report)} clean")
    return 0 if not miss and not dirty else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
