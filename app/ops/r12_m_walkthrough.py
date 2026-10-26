"""PLAN_R12 Session M: the R12 walk-through with screenshots at 1440x900 and 1280x800, with an overflow probe.

  python ops/r12_m_walkthrough.py [--ui http://127.0.0.1:5500] [--sizes 1440x900,1280x800] [--only name,name]

Writes docs/v5/r12_review/m/*.png and docs/v5/r12_review/m/m_walkthrough.json. Needs the UI and the v5 services
running (ops/v5.sh start). Mints a session in the identity store; no password or secret is read or printed.
Each step: open a path, optionally click through a list of selectors (each waited for), then wait for the step's
proof element and shoot the page (and the proof element alone).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r11_ui_shots import PROBE, mint, wait_idle  # noqa: E402

OUT = V5 / "docs" / "v5" / "r12_review" / "m"
T = lambda s: f'[data-testid="{s}"]'  # noqa: E731

# (name, item ids, path, clicks before, proof selector)
STEPS: list[tuple[str, str, str, list[str], str]] = [
    # Landing (I30, I23), tabs (I7, I31, I2)
    ("01-landing-cards", "I30", "/deal-desk", [], T("dealdesk-cards-row")),
    ("02-card-to-review", "I30 I17", "/deal-desk?card=to_review", [], T("dealdesk-card-list")),
    ("03-card-going-bad", "I29 I30", "/deal-desk?card=going_bad", [], T("dealdesk-cards-row")),
    ("04-tab-book", "I31 I7", "/deal-desk?tab=book", [], T("book-tab")),
    ("05-tab-params", "I2 I3", "/deal-desk?tab=params", [], T("dealdesk-tab-params-panel")),
    # Twin A: Al Sahel Building Materials Group (renewal)
    ("10-twa-proposal", "I1 I23 I26", "/deal-desk/R12-TWA", [], T("dealdesk-step-proposal-view")),
    ("11-twa-documents", "I26", "/deal-desk/R12-TWA", [T("dealdesk-action-documents")], T("dealdesk-action-bar")),
    ("12-twa-review", "I16 I15", "/deal-desk/R12-TWA?step=review", [], T("review2-finding")),
    ("13-twa-analysis", "I15 O1", "/deal-desk/R12-TWA?step=analysis", [], T("dealdesk-step-analysis-view")),
    ("14-twa-stress", "I19 I20 I22 O3-O6", "/deal-desk/R12-TWA?step=stress", [], T("stress2-commentary")),
    ("15-twa-stress-ladder", "I20 O6", "/deal-desk/R12-TWA?step=stress", [], T("stress2-ladder")),
    ("16-twa-structure-group", "I24", "/deal-desk/R12-TWA?step=structure", [], T("dealdesk-group-panel")),
    ("17-twa-structure-swot", "I24 I14", "/deal-desk/R12-TWA?step=structure", [], T("dealdesk-swot-panel")),
    ("18a-twa-optimise", "I14 I15", "/deal-desk/R12-TWA?step=structure", [T("dealdesk-optimise")], T("dealdesk-optimise-view")),
    ("18b-twa-recommendation", "I15 I22", "/deal-desk/R12-TWA?step=structure", [T("dealdesk-optimise"), T("dealdesk-recommend-best")], T("dealdesk-step-recommendation-view")),
    ("19-twa-write-proposal", "I25", "/deal-desk/R12-TWA", [T("dealdesk-action-write")], T("dealdesk-write-proposal-paper")),
    ("20-twa-committee-paper", "I27", "/deal-desk/R12-TWA", [T("dealdesk-action-committee")], T("dealdesk-committee-paper-summary")),
    # Twin B: Gulf Meridian Contracting (project limit)
    ("30-twb-proposal-project", "I1 I28", "/deal-desk/R12-TWB", [], T("products-project")),
    ("31-twb-review", "I16", "/deal-desk/R12-TWB?step=review", [], T("review2-finding")),
    ("32-twb-analysis", "I15", "/deal-desk/R12-TWB?step=analysis", [], T("dealdesk-step-analysis-view")),
    ("33-twb-stress", "I22", "/deal-desk/R12-TWB?step=stress", [], T("stress2-verdict-card")),
    ("34-twb-structure-group", "I24", "/deal-desk/R12-TWB?step=structure", [], T("dealdesk-group-cap")),
    ("35-twb-structure-swot", "I24", "/deal-desk/R12-TWB?step=structure", [], T("dealdesk-weakness-mitigant-map")),
    ("36a-twb-optimise", "I14 I15", "/deal-desk/R12-TWB?step=structure", [T("dealdesk-optimise")], T("dealdesk-optimise-view")),
    ("36b-twb-recommendation", "I15 I22", "/deal-desk/R12-TWB?step=structure", [T("dealdesk-optimise"), T("dealdesk-recommend-best")], T("dealdesk-step-recommendation-view")),
    ("37-twb-write-proposal", "I25", "/deal-desk/R12-TWB", [T("dealdesk-action-write")], T("dealdesk-write-proposal-paper")),
    ("38-twb-committee-paper", "I27", "/deal-desk/R12-TWB", [T("dealdesk-action-committee")], T("dealdesk-committee-paper-summary")),
    # Pipeline deal (I21)
    ("40-pipeline-mode", "I21", "/deal-desk?mode=pipeline", [], T("dealdesk-pipeline-deals")),
    ("41-pl-deal-banner", "I21", "/deal-desk/PL-03?from=pipeline", [], T("dealdesk-pipeline-banner-decision")),
    # Book (I7, I8, I29, I31)
    ("50-book-going-bad", "I29", "/deal-desk?tab=book&filter=going_bad", [], T("book-table")),
    ("51-book-repricing", "I8", "/deal-desk?tab=book&filter=repricing", [], T("book-table")),
    ("52-book-tier-dialog", "I31 I22", "/deal-desk?tab=book&filter=going_bad", [T("book-row"), T("book-action-tier")], T("book-tier-dialog")),
    ("53-book-renewals", "I31", "/deal-desk?tab=book&filter=renewals_due", [], T("book-table")),
    # EWS tier panel (I22 tier travels)
    ("55-ews-tier-panel", "I22", "/early-warning?domain=corporate&customer=CB00935", [], T("ews-monitoring-tier")),
    # Parameters and policy (I2-I6)
    ("60-params-policies", "I3", "/deal-desk?tab=params", [T("params-tab-policies")], T("policy-library-table")),
    # Products (I28)
    ("70-escrow", "I28", "/deal-desk/R12-ESC", [], T("products-escrow")),
    ("71-syndicated", "I28", "/deal-desk/R12-SYN", [], T("products-synd")),
    ("72-sme-fast-track", "I28", "/deal-desk/R12-SME2", [], T("products-sme")),
    # Try it on your documents (I18)
    ("80-try-docs", "I18", "/deal-desk", [T("try-docs-entry")], T("try-docs-dialog")),
    # Noor (I11, I12, I13, I17)
    ("90-noor-panel-brief", "I11 I13", "/deal-desk", [T("ask-noor")], T("noor-panel")),
    ("91-noor-why", "I12", "/deal-desk", [T("ask-noor"), T("noor-why")], T("noor-turn-why")),
    ("92-viewing-as", "I17", "/deal-desk", [T("viewing-as")], T("viewing-as-current")),
    ("93-cockpit-brief", "I11 FX-R13-01 (Home Brief tab)", "/", [], T("noor-home-brief")),
    # Answers and Plotly across modules (I9, I10)
    ("95-whatif-module-brief", "I10 I13", "/what-if", [], T("noor-module-brief-whatif")),
    ("96-lenses-module-brief", "I10 I13", "/lenses", [], T("noor-module-brief-lenses")),
    ("97-dealdesk-module-brief", "I13", "/deal-desk", [], T("noor-module-brief-dealdesk")),
]


def run(ui: str, sizes: list[tuple[int, int]], only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tok = mint()
    report: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w, h in sizes:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            ctx.add_cookies([{"name": "cp_session", "value": tok, "domain": "127.0.0.1", "path": "/"}])
            page: Page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            for name, items, path, clicks, proof in STEPS:
                if only and not any(name.startswith(o) for o in only):
                    continue
                errors.clear()
                t0 = time.time()
                note = ""
                try:
                    page.goto(ui + path, wait_until="domcontentloaded", timeout=120000)
                    for c in clicks:
                        page.wait_for_selector(c, timeout=90000)
                        page.locator(c).first.click()
                        page.wait_for_timeout(400)
                    page.wait_for_selector(proof, timeout=150000)
                    ok = True
                except Exception as e:  # noqa: BLE001 - recorded as a missing surface
                    ok = False
                    note = str(e).splitlines()[0][:160]
                wait_idle(page, 1000)
                el = page.locator(proof).first
                if ok and el.count():
                    try:
                        el.scroll_into_view_if_needed(timeout=5000)
                    except Exception:  # noqa: BLE001
                        pass
                probe = page.evaluate(PROBE, None)
                file = OUT / f"{name}-{w}x{h}.png"
                page.screenshot(path=str(file), full_page=False)
                secs = round(time.time() - t0, 1)
                row = {"step": name, "items": items, "size": f"{w}x{h}", "found": ok, "seconds": secs,
                       "file": str(file.relative_to(V5)), "page_errors": list(errors), "note": note,
                       "docWidth": probe.get("docWidth"), "overflow": len(probe.get("overflow", []) or []), "rough": probe.get("rough")}
                report.append(row)
                print(f"{name} {w}x{h}: found={ok} {secs}s docWidth={row['docWidth']} overflow={row['overflow']} errors={len(errors)} {note}", flush=True)
                (OUT / "m_walkthrough.json").write_text(json.dumps(report, indent=2))
            ctx.close()
        browser.close()
    bad = [r for r in report if not r["found"] or r["page_errors"]]
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900,1280x800")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sz = [tuple(int(v) for v in s.split("x")) for s in a.sizes.split(",")]
    sys.exit(run(a.ui, sz, {o for o in a.only.split(",") if o}))
