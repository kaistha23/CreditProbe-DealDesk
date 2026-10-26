"""PLAN_R15 session b: click-through walk of the Deal Desk fixes (L7, L8, L10, L11, L12, L13), 1440x900 and 1280x800.

  .venv/bin/python ops/r15_b_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only id,id]

Every screen is reached by clicking (N6); the only goto is the first page after sign-in. Screens and the report go to
docs/v5/r15_review/b/<step>_<size>.png and walk.json. Deals: DD-11 (L12, L13), DD-02 (L8), DD-06 (L10, L11), a renewal
started from the Book with no RM proposal (L7, the cloud stand-in for the Mac's DD-104), R14-RWQ (L10, L11 on the demo pack).
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
from r14_f_walkthrough import open_deal, step, to  # noqa: E402

OUT = V5 / "docs" / "v5" / "r15_review" / "b"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731
LONG = 240_000
HALF = V5 / "data" / "dealdesk" / "demo_proposals" / "R14-RWQ_RM_proposal_half_baked.docx"


def text(page: Page, sel: str, n: int = 300) -> str:
    loc = page.locator(sel).first
    return " ".join(loc.inner_text().split())[:n] if loc.count() else ""


def close_dialog(page: Page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)


# ---------------------------------------------------------------- DD-11: L13 one story, L12 draft proposal
def s_home(page: Page, ui: str, ctx: dict) -> dict:
    page.goto(f"{ui}/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(T("dealdesk-home"), timeout=LONG)
    idle(page, 800)
    return {}


def s_dd11_analysis(page: Page, ui: str, ctx: dict) -> dict:
    open_deal(page, "DD-11", "al kharj")
    step(page, "analysis", "dealdesk-step-analysis-view")
    page.wait_for_selector(T("dealdesk-story"), timeout=LONG)
    to(page, T("dealdesk-kpis"))
    return {"raroc_tile": text(page, T("dealdesk-kpi-raroc"), 120), "story": text(page, T("dealdesk-story-sentence"), 400),
            "pd_chip": text(page, T("dealdesk-oor"), 120)}


def s_dd11_raroc_info(page: Page, ui: str, ctx: dict) -> dict:
    btn = page.locator(f'{T("dealdesk-kpi-raroc")} button').first
    btn.click()
    page.wait_for_selector(T("dealdesk-kpi-return-view"), timeout=30_000)
    page.locator(T("dealdesk-kpi-return-view-relationship_deposits")).click()
    page.wait_for_timeout(300)
    return {"view": text(page, T("dealdesk-kpi-return-view-value"), 160), "line": text(page, T("dealdesk-kpi-return-view-line"), 240),
            "rule": text(page, T("dealdesk-kpi-return-view-rule"), 240)}


def s_dd11_pd_note(page: Page, ui: str, ctx: dict) -> dict:
    close_dialog(page)
    to(page, T("dealdesk-verdict"))
    return {"chip": text(page, T("dealdesk-oor"), 120), "note": text(page, T("dealdesk-oor-note"), 400)}


def s_dd11_review(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "review", "review-workspace")
    page.wait_for_selector(T("review-answer-story"), timeout=LONG)
    to(page, T("review-answer"))
    findings = page.locator('[data-testid="review-findings"] li, [data-testid^="engine-finding"]').all_inner_texts()[:6]
    return {"headline": text(page, T("review-answer-headline"), 400), "story": text(page, T("review-answer-story"), 400),
            "bureau_none": "SIMAH flag None" in page.content()}


def s_dd11_draft(page: Page, ui: str, ctx: dict) -> dict:
    t0 = time.time()
    page.locator(T("review-draft-toggle")).click()
    page.wait_for_selector(f'{T("dealdesk-credit-proposal")}, {T("dealdesk-credit-proposal-failed")}', timeout=200_000)
    idle(page, 600)
    return {"seconds": round(time.time() - t0, 1), "written": page.locator(T("dealdesk-credit-proposal")).count() == 1,
            "chips": text(page, T("dealdesk-credit-proposal-chips"), 300)}


# ---------------------------------------------------------------- DD-02: L8 deposits and the stress matrix
def s_dd02_deposits(page: Page, ui: str, ctx: dict) -> dict:
    close_dialog(page)
    open_deal(page, "DD-02", "taif central")
    step(page, "analysis", "dealdesk-step-analysis-view")
    page.wait_for_selector(T("dealdesk-account-behaviour"), timeout=LONG)
    page.wait_for_selector(T("dealdesk-ab-return-view"), timeout=LONG)
    to(page, T("dealdesk-account-behaviour"))
    return {"deposit_tile": text(page, T("dealdesk-raroc-deposits"), 160), "deposit_value": text(page, T("dealdesk-deposit-value"), 160),
            "formula": page.locator(T("dealdesk-deposit-value")).get_attribute("title"), "plain": text(page, T("dealdesk-deposit-plain"), 500),
            "cross_check": text(page, T("dealdesk-capacity-cross-check"), 160)}


def s_dd02_return_switch(page: Page, ui: str, ctx: dict) -> dict:
    out = {}
    for k in ("relationship", "relationship_deposits", "deal"):
        page.locator(T(f"dealdesk-ab-return-view-{k}")).click()
        page.wait_for_timeout(250)
        out[k] = text(page, T("dealdesk-ab-return-view-value"), 120)
    to(page, T("dealdesk-ab-return-view"))
    return out


def s_dd02_stress(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "structure", "flow-structure-table")
    page.locator(T("dealdesk-stress-button")).click()
    page.wait_for_selector(T("flow-stress-choices"), timeout=LONG)
    settle(page)
    page.locator(T("flow-stress-run")).click()
    page.wait_for_selector(T("flow-stress-matrix"), timeout=LONG)
    settle(page)
    to(page, T("flow-stress-how-to-read"))
    labels = page.locator(f'{T("flow-stress-matrix")} .text-negative').all_inner_texts()[:4]
    return {"how_to_read": text(page, T("flow-stress-how-to-read"), 600), "first_breaks": labels,
            "times_sign": "(×" in page.locator(T("flow-stress-matrix")).inner_text()}


# ---------------------------------------------------------------- DD-06: L10 section detail, L11 brief and the document
def s_dd06_check(page: Page, ui: str, ctx: dict) -> dict:
    open_deal(page, "DD-06", "dhahran continental")
    step(page, "proposal-check", "dealdesk-proposal-check-result")
    to(page, T("dealdesk-proposal-check-section-summary"))
    return {"summary": text(page, T("dealdesk-proposal-check-section-summary"), 200), "brief": text(page, T("dealdesk-rm-brief-line"), 200)}


def _section(page: Page, key: str) -> dict:
    page.locator(T(f"dealdesk-proposal-check-section-{key}")).click()
    page.wait_for_selector(f'{T("dealdesk-proposal-check-section-detail")}[data-section="{key}"]', timeout=30_000)
    to(page, T("dealdesk-proposal-check-section-detail"))
    return {"why": text(page, T("dealdesk-proposal-check-section-why"), 300),
            "checks": page.locator(f'{T("dealdesk-proposal-check-section-checks")} li').count()}


def s_dd06_section_75(page: Page, ui: str, ctx: dict) -> dict:
    return _section(page, "security")


def s_dd06_section_missing(page: Page, ui: str, ctx: dict) -> dict:
    return _section(page, "facilities")


def s_dd06_section_na(page: Page, ui: str, ctx: dict) -> dict:
    return _section(page, "projects")


def s_dd06_section_draft(page: Page, ui: str, ctx: dict) -> dict:
    _section(page, "facilities")
    page.locator(T("dealdesk-proposal-check-section-draft")).click()
    page.wait_for_selector(T("dealdesk-credit-proposal"), timeout=200_000)
    idle(page, 1200)
    active = page.locator(f'{T("dealdesk-credit-proposal-nav-facilities")}').get_attribute("class") or ""
    return {"landed_on_facilities": "accent" in active}


def s_dd06_brief(page: Page, ui: str, ctx: dict) -> dict:
    close_dialog(page)
    page.locator(T("dealdesk-rm-brief-toggle")).click()
    page.wait_for_selector(T("dealdesk-rm-brief-text"))
    to(page, T("dealdesk-rm-brief"))
    page.locator(T("dealdesk-rm-brief-text")).fill(page.locator(T("dealdesk-rm-brief-text")).input_value() + "\nEdited by the reviewer.")
    return {"lines": page.locator(T("dealdesk-rm-brief-text")).input_value().count("\n"),
            "reset_shown": page.locator(T("dealdesk-rm-brief-reset")).count() == 1}


def s_dd06_brief_send(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-rm-brief-send")).click()
    page.wait_for_selector(T("dealdesk-rm-brief-msg"), timeout=60_000)
    return {"msg": text(page, T("dealdesk-rm-brief-msg"), 300)}


def s_dd06_view_proposal(page: Page, ui: str, ctx: dict) -> dict:
    to(page, T("dealdesk-view-proposal"))
    page.locator(T("dealdesk-view-proposal")).click()
    page.wait_for_selector(T("dealdesk-proposal-doc"))
    idle(page, 500)
    return {"sections": page.locator(f'{T("dealdesk-proposal-doc")} section').count(),
            "comments": page.locator(f'{T("dealdesk-proposal-doc-comments")} > div').count()}


def s_dd06_review_memo_view(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-proposal-doc-close")).click()
    step(page, "review", "review-workspace")
    to(page, T("review-memo"))
    page.locator(T("review-memo-view-proposal")).click()
    page.wait_for_selector(T("dealdesk-proposal-doc"), timeout=60_000)
    idle(page, 400)
    return {"opened": True}


def s_dd06_more_documents(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-proposal-doc-close")).click()
    page.locator(T("dealdesk-more-button")).click()
    page.locator(T("dealdesk-action-documents")).click()
    page.wait_for_selector(T("documents-panel"), timeout=60_000)
    page.locator(T("documents-view-rm-proposal")).click()
    page.wait_for_selector(T("dealdesk-proposal-doc"), timeout=60_000)
    idle(page, 400)
    return {"opened": True}


# ---------------------------------------------------------------- L7: a renewal with no RM proposal (Book → Start renewal)
def s_renewal_start(page: Page, ui: str, ctx: dict) -> dict:
    close_dialog(page)
    close_dialog(page)
    nav(page, "deal-desk", "dealdesk-home")
    page.locator(T("dealdesk-tab-book")).click()
    page.wait_for_selector(T("book-row"), timeout=LONG)
    rows = page.locator(T("book-row"))
    for i in range(min(rows.count(), 25)):
        rows.nth(i).click()
        page.wait_for_selector(T("book-actions"), timeout=60_000)
        if page.locator(T("book-action-open")).is_disabled():
            break
        rows.nth(i).click()
        page.wait_for_timeout(300)
    to(page, T("book-actions"))
    name = text(page, T("book-detail"), 120)
    page.locator(T("book-action-renewal")).click()
    page.wait_for_selector(T("dealdesk-stepper"), timeout=LONG)
    idle(page, 800)
    return {"url": page.url.split("5500")[-1], "facility": name}


def s_renewal_check(page: Page, ui: str, ctx: dict) -> dict:
    step(page, "proposal-check", "dealdesk-proposal-check-none")
    to(page, T("dealdesk-proposal-check-none"))
    body = page.locator(T("dealdesk-proposal-check")).inner_text()
    return {"state": text(page, T("dealdesk-proposal-check-none"), 400), "spinner": "Checking the proposal on file" in body,
            "raw": "No proposal DD-" in body}


def s_renewal_record(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-proposal-check-use-record")).click()
    page.wait_for_selector(T("dealdesk-proposal-check-result"), timeout=120_000)
    to(page, T("dealdesk-proposal-check-score"))
    return {"score": page.locator(T("dealdesk-proposal-check-result")).get_attribute("data-score")}


def s_renewal_draft(page: Page, ui: str, ctx: dict) -> dict:
    # the third action: the step is reopened to the no-proposal state by a fresh check of another renewal? Here: Review →
    # Draft proposal writes the same bank-form proposal from data for the renewal.
    step(page, "review", "review-workspace")
    page.locator(T("review-draft-toggle")).click()
    page.wait_for_selector(f'{T("dealdesk-credit-proposal")}, {T("dealdesk-credit-proposal-failed")}', timeout=200_000)
    idle(page, 600)
    return {"written": page.locator(T("dealdesk-credit-proposal")).count() == 1, "chips": text(page, T("dealdesk-credit-proposal-chips"), 200)}


# ---------------------------------------------------------------- R14-RWQ: the demo pack
def s_rwq_check(page: Page, ui: str, ctx: dict) -> dict:
    close_dialog(page)
    open_deal(page, "R14-RWQ", "rwq")
    step(page, "proposal-check", "dealdesk-proposal-check-result")
    page.locator(T("dealdesk-proposal-check-demo-half")).click()
    page.wait_for_timeout(500)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"dealdesk-proposal-check-upload\"]').disabled", timeout=90_000)
    to(page, T("dealdesk-rm-brief"))
    return {"defects": page.locator(T("dealdesk-proposal-check-result")).get_attribute("data-defects"),
            "brief": text(page, T("dealdesk-rm-brief-line"), 200), "summary": text(page, T("dealdesk-proposal-check-section-summary"), 200)}


def s_rwq_section(page: Page, ui: str, ctx: dict) -> dict:
    secs = page.locator('[data-testid^="dealdesk-proposal-check-section-"][aria-expanded]')
    key = None
    for i in range(secs.count()):
        t = secs.nth(i).inner_text()
        if any(ch.isdigit() for ch in t.split("\n")[-1]) or "missing" not in t:
            key = (secs.nth(i).get_attribute("data-testid") or "").replace("dealdesk-proposal-check-section-", "")
            if t.split()[1:2] and t.split()[1] not in ("100", "n/a"):
                break
    return _section(page, key or "facilities") | {"key": key}


def s_rwq_brief(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-rm-brief-toggle")).click()
    page.wait_for_selector(T("dealdesk-rm-brief-text"))
    to(page, T("dealdesk-rm-brief"))
    v = page.locator(T("dealdesk-rm-brief-text")).input_value()
    return {"critical_first": v.find("Critical") < v.find("Major") if "Critical" in v and "Major" in v else None, "chars": len(v)}


def s_rwq_view(page: Page, ui: str, ctx: dict) -> dict:
    page.locator(T("dealdesk-view-proposal")).click()
    page.wait_for_selector(T("dealdesk-proposal-doc"))
    idle(page, 500)
    return {"sections": page.locator(f'{T("dealdesk-proposal-doc")} section').count(),
            "comments": page.locator(f'{T("dealdesk-proposal-doc-comments")} > div').count()}


Step = tuple[str, str, Callable[[Page, str, dict], dict]]
STEPS: list[Step] = [
    ("00_home", "", s_home),
    ("10_dd11_analysis_story", "L13", s_dd11_analysis),
    ("11_dd11_raroc_return_view", "L13", s_dd11_raroc_info),
    ("12_dd11_pd_chip", "L13", s_dd11_pd_note),
    ("13_dd11_review_banner", "L13 L12", s_dd11_review),
    ("14_dd11_draft_proposal", "L12", s_dd11_draft),
    ("20_dd02_deposits", "L8", s_dd02_deposits),
    ("21_dd02_return_switch", "L8 L13", s_dd02_return_switch),
    ("22_dd02_stress_matrix", "L8", s_dd02_stress),
    ("30_dd06_check_summary", "L10 L11", s_dd06_check),
    ("31_dd06_section_75", "L10", s_dd06_section_75),
    ("32_dd06_section_missing", "L10", s_dd06_section_missing),
    ("33_dd06_section_na", "L10", s_dd06_section_na),
    ("34_dd06_section_draft", "L10", s_dd06_section_draft),
    ("35_dd06_brief", "L11", s_dd06_brief),
    ("36_dd06_brief_sent", "L11", s_dd06_brief_send),
    ("37_dd06_view_proposal", "L11", s_dd06_view_proposal),
    ("38_dd06_review_memo_view", "L11", s_dd06_review_memo_view),
    ("39_dd06_more_documents_view", "L11", s_dd06_more_documents),
    ("40_renewal_start", "L7", s_renewal_start),
    ("41_renewal_no_proposal", "L7", s_renewal_check),
    ("42_renewal_use_record", "L7", s_renewal_record),
    ("43_renewal_draft_from_data", "L7 L12", s_renewal_draft),
    ("50_rwq_half_baked", "L10 L11", s_rwq_check),
    ("51_rwq_section", "L10", s_rwq_section),
    ("52_rwq_brief", "L11", s_rwq_brief),
    ("53_rwq_view_proposal", "L11", s_rwq_view),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    report: list[dict] = []
    path = OUT / "walk.json"
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
                      f"{json.dumps(rec.get('checks'), default=str, ensure_ascii=False)[:400]}", flush=True)
                path.write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False))
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
