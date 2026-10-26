#!/usr/bin/env python3
"""Rounds B and G: a browser walk of Borrower 360 in the deal and the customer file, and the cross-deal counterparty signals.

    .venv/bin/python ops/round_bg_walk.py [--ui http://127.0.0.1:6600] [--out var/walk/round-bg]

Steps (each a screenshot and a check):
  1. R16-C2 (Sawaed Al Bina): the counterparty line on the deal names Al Kharj United Contracting (a supplier in declined deal DD-11);
  2. open Borrower 360 from the line: the panel's Counterparty exposure tab lists the signal with its document (C2-25) and DD-11;
  3. the panel's tabs: Deals and proposals, Core banking, Limits, Bureau, Group, Learned from uploads (sources and dates shown);
  4. DD-11 (Al Kharj United Contracting): the panel says it is a supplier of Sawaed Al Bina (R16-C2);
  5. R16-C1 (Dar Al Naseem): a buyer in default (Al Faisaliah Continental Medical) is told;
  6. a borrower link /deal-desk/customer-packs?cif=CB01655 lands on that customer's 360 (no deal of its own; joined to R16-C1);
  7. /deal-desk/customer-packs?cif=CB09001: the customer file shows the 360 and the customer pack below it;
  8. the Cockpit brief carries a Counterparty exposure line (Deal Desk brief, via the API the page reads).
Exit 1 on a failed check. Signs in as ops/dealdesk_edition_walk.py does.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))

from core_login import add_session  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:6600")
    ap.add_argument("--api", default="http://127.0.0.1:8508")
    ap.add_argument("--out", default=str(V5 / "var" / "walk" / "round-bg"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    errors: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append({"step": name, "ok": bool(ok), "detail": detail[:300]})
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail[:160]}" if detail else ""))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        add_session(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))

        def go(path: str, wait: str = "", timeout: int = 90_000) -> None:
            page.goto(a.ui + path, wait_until="domcontentloaded", timeout=timeout)
            if wait:
                page.wait_for_selector(wait, timeout=timeout)
            time.sleep(1.0)

        def shot(name: str) -> None:
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)

        # 1-3: R16-C2
        go("/deal-desk/R16-C2", "[data-testid='dealdesk-title']")
        try:
            page.wait_for_selector("[data-testid='dealdesk-counterparty-line']", timeout=60_000)
            line = page.inner_text("[data-testid='dealdesk-counterparty-line']")
        except Exception as e:  # noqa: BLE001
            line = f"no line: {e}"
        shot("01_r16c2_counterparty_line")
        check("1 R16-C2 shows the counterparty line", "Al Kharj United Contracting" in line, line)
        page.click("[data-testid='dealdesk-counterparty-open']")
        page.wait_for_selector("[data-testid='dealdesk-b360']", timeout=90_000)
        time.sleep(1.0)
        page.click("[data-testid='b360-tab-counterparty']")
        time.sleep(0.5)
        txt = page.inner_text("[data-testid='b360-counterparty']")
        shot("02_r16c2_b360_counterparty")
        check("2 the signal names DD-11 and the document C2-25", "DD-11" in txt and "C2-25" in txt and "declined" in txt, txt[:200])
        check("2b the deal URL carries ?b360=1", "b360=1" in page.url, page.url)
        for i, tab in enumerate(("deals", "core", "limits", "bureau", "group", "learned")):
            page.click(f"[data-testid='b360-tab-{tab}']")
            time.sleep(0.4)
            body = page.inner_text(f"[data-testid='b360-section-{tab}']")
            shot(f"03_{i}_r16c2_tab_{tab}")
            check(f"3 tab {tab} shows facts with their source", ("Source:" in body or "·" in body) and len(body) > 40, body[:120])
        # 4: DD-11
        go("/deal-desk/DD-11?b360=1", "[data-testid='dealdesk-b360']")
        page.click("[data-testid='b360-tab-counterparty']")
        time.sleep(0.5)
        txt = page.inner_text("[data-testid='b360-counterparty']")
        shot("04_dd11_supplier_of_r16c2")
        check("4 DD-11 is told it supplies the borrower of R16-C2", "Sawaed Al Bina" in txt and "R16-C2" in txt, txt[:200])
        # 5: R16-C1
        go("/deal-desk/R16-C1?b360=1", "[data-testid='dealdesk-b360']")
        page.click("[data-testid='b360-tab-counterparty']")
        time.sleep(0.5)
        txt = page.inner_text("[data-testid='b360-counterparty']")
        shot("05_r16c1_buyer_in_default")
        check("5 R16-C1 is told a buyer is in default", "Al Faisaliah Continental Medical" in txt and "default" in txt, txt[:200])
        # 6: a borrower link with no deal
        go("/deal-desk/customer-packs?cif=CB01655", "[data-testid='customer-b360']")
        body = page.inner_text("[data-testid='customer-b360']")
        shot("06_cif_cb01655_customer_360")
        check("6 ?cif= lands on the customer's 360", "Al Faisaliah Continental Medical" in body, body[:160])
        # 7: the customer file with its pack
        go("/deal-desk/customer-packs?cif=CB09001", "[data-testid='customer-b360']")
        page.wait_for_selector("[data-testid='packs-checklist']", timeout=60_000)
        page.click("[data-testid='b360-tab-learned']")
        time.sleep(0.5)
        body = page.inner_text("[data-testid='b360-section-learned']")
        shot("07_cif_cb09001_customer_file")
        check("7 the customer file: 360, what the uploads taught, the pack below", "C1-" in body and "page" in body.lower(), body[:160])
        browser.close()
    # 8: the brief (the API the Cockpit reads)
    try:
        from core_login import login
        req = urllib.request.Request(f"{a.api}/api/v1/noor/brief?module=dealdesk&persona=analyst&top=5")
        req.add_header("Cookie", f"cp_session={login()['cookie']}")
        brief = json.loads(urllib.request.urlopen(req, timeout=120).read())
        lines = [i for i in brief.get("items", []) + brief.get("more", []) if i.get("source") == "counterparty_exposure"]
        (out / "08_brief_counterparty_lines.json").write_text(json.dumps(lines[:6], indent=1))
        check("8 Noor's Deal Desk brief carries counterparty exposure lines", bool(lines), lines[0]["title"] if lines else str(brief.get("sources", {}).get("counterparty_exposure")))
    except Exception as e:  # noqa: BLE001
        check("8 Noor's Deal Desk brief carries counterparty exposure lines", False, f"{type(e).__name__}: {e}")
    check("no page errors", not errors, "; ".join(errors[:3]))
    (out / "report.json").write_text(json.dumps({"ui": a.ui, "results": results, "page_errors": errors}, indent=1))
    ok = all(r["ok"] for r in results)
    print("ROUND B/G WALK " + ("PASS" if ok else "FAIL") + f" ({sum(r['ok'] for r in results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
