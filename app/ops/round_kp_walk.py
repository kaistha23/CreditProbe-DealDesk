#!/usr/bin/env python3
"""Rounds K and P: the browser walk of the analysts' rules and Policy Docs as the rulebook, on the running edition.

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers CP_TEST_PASSWORD=anne .venv/bin/python ops/round_kp_walk.py [--ui http://127.0.0.1:6600]

  1. Policy Docs: the four kinds; Regulation; "Add a policy or circular" with the synthetic SAMA circular
     (demo_inputs/round_kp) -> CreditProbe's interpretation -> Deal Desk impact (summary, thresholds, pipeline: "46 pending,
     12 construction: N would fail", if applied / if not applied) -> Yes, add it -> applied, deals flagged;
  2. a flagged pending deal shows the flag with the clause cited;
  3. My rules: an instruction -> "Save this as a rule for your future documents?" -> Yes -> saved;
  4. the next credit proposal (More -> Write proposal) lists it under "Rules applied", applied;
  5. Policy Docs -> Global rules (the seeded SIB-style rules) and Gold-standard documents (upload -> differences).
Screenshots and results.json under var/walk/round-kp/. Exit 1 on any failed check.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
from core_login import add_session  # noqa: E402

CIRCULAR = V5 / "demo_inputs/round_kp/SAMA_Circular_Construction_Financing_2026.txt"
GOLD = V5 / "demo_inputs/round_kp/Gold_Standard_Credit_Proposal_Example.txt"
T = lambda x: f'[data-testid="{x}"]'  # noqa: E731


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:6600")
    ap.add_argument("--api", default="http://127.0.0.1:8508")
    ap.add_argument("--out", default=str(V5 / "var/walk/round-kp"))
    ap.add_argument("--steps", default="1,2,3,4,5", help="which steps to run (a re-run after a browser crash)")
    ap.add_argument("--deal", default="R12-TWA", help="the deal whose draft shows Rules applied")
    a = ap.parse_args()
    steps = {int(x) for x in a.steps.split(",") if x.strip()}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    errors: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        add_session(ctx)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        shot = lambda n: page.screenshot(path=str(out / f"{n}.png"), full_page=False)  # noqa: E731

        failing: list = []
        rid = ""
        # 1. Policy Docs: kinds, regulation upload, impact, approve
        if 1 in steps:
          page.goto(a.ui + "/policy-docs", wait_until="domcontentloaded", timeout=120_000)
          page.wait_for_selector(T("policy-kinds"), timeout=120_000)
          labels = page.inner_text(T("policy-kinds"))
          check("Policy Docs lists the four kinds", all(k in labels for k in ("Regulation", "Internal credit policy", "Gold-standard documents", "Global rules")), labels.replace("\n", " "))
          page.click(T("policy-kind-regulation"))
          page.wait_for_selector(T("rulebook-assessments-regulation"), timeout=60_000)
          shot("01_regulation_tab")
          page.click(T("policy-add"))
          page.wait_for_selector(T("policy-add-dialog"))
          page.set_input_files(T("policy-upload-input"), str(CIRCULAR))
          page.click(T("policy-upload-submit"))
          page.wait_for_selector(T("policy-interpretation"), timeout=120_000)
          page.wait_for_selector(T("rulebook-pipeline-headline"), timeout=240_000)
          head = page.inner_text(T("rulebook-pipeline-headline"))
          summ = page.inner_text(T("rulebook-summary"))
          check("instant summary of the circular", "DSCR" in summ and "1.40x" in summ, summ[:160])
          check("pipeline impact: pending, construction, would fail", "pending" in head and "construction" in head and "would fail" in head, head)
          check("thresholds and the checks they move", page.locator(T("rulebook-param")).count() >= 3)
          check("if applied / if not applied", page.locator(T("rulebook-if-applied")).count() == 1 and page.locator(T("rulebook-if-not")).count() == 1)
          failing = [page.locator(T("rulebook-deal-row")).nth(i).get_attribute("data-id") for i in range(page.locator(T("rulebook-deal-row")).count())
                     if page.locator(T("rulebook-deal-row")).nth(i).get_attribute("data-new-fail") == "true"]
          check("the deals that would fail are named", len(failing) >= 1, ", ".join(failing))
          page.locator(T("policy-dealdesk-impact")).scroll_into_view_if_needed()
          shot("02_impact_summary")
          page.locator(T("rulebook-pipeline")).scroll_into_view_if_needed()
          shot("03_impact_pipeline")
          page.click(T("policy-add-yes"))
          page.wait_for_selector(T("policy-add-confirm"), timeout=30_000)
          page.click(T("policy-add-confirm"))
          page.wait_for_selector(T("policy-dealdesk-applied"), timeout=120_000)
          applied = page.inner_text(T("policy-dealdesk-applied"))
          check("approve -> applied, pending deals flagged", "flagged" in applied, applied)
          page.locator(T("policy-dealdesk-applied")).scroll_into_view_if_needed()
          shot("04_applied")
          page.click(T("policy-add-finish"))

        if 2 in steps and failing:
          if failing:
              pid = failing[0]
              page.goto(a.ui + f"/deal-desk/{pid}", wait_until="domcontentloaded", timeout=120_000)
              try:
                  page.wait_for_selector(T("deal-policy-flags"), timeout=90_000)
                  txt = page.inner_text(T("deal-policy-flags"))
                  check(f"deal {pid} shows the policy flag with the clause", "Circular" in txt or "2." in txt or "3." in txt, txt[:200].replace("\n", " "))
              except Exception as e:  # noqa: BLE001
                  check(f"deal {pid} shows the policy flag with the clause", False, str(e)[:120])
              time.sleep(1.5)
              shot("05_deal_flagged")

        # 3. save a rule from an instruction (Round W's living document is not merged here: the same prompt, on My rules)
        if 3 in steps:
          page.goto(a.ui + "/deal-desk/rules", wait_until="domcontentloaded", timeout=120_000)
          page.wait_for_selector(T("my-rules"), timeout=90_000)
          page.fill(T("my-rules-try-input"), "write amounts in millions as SAR 12.5 mn")
          page.click(T("my-rules-try-go"))
          page.wait_for_selector(T("rule-prompt"), timeout=60_000)
          check("CreditProbe asks “Save this as a rule for your future documents?”",
                "Save this as a rule for your future documents?" in page.inner_text(T("rule-prompt")))
          shot("06_save_rule_prompt")
          page.click(T("rule-prompt-yes"))
          page.wait_for_selector(T("rule-prompt-saved"), timeout=60_000)
          rid = page.get_attribute(T("rule-prompt-saved"), "data-rule")
          check("yes makes it a rule", bool(rid), rid or "")
          time.sleep(1.0)
          shot("07_rule_saved")

        # 4. the next draft (Deal Desk -> More -> Write proposal: the bank-form credit proposal) lists it under Rules applied
        if 4 in steps:
          if not rid:
            mine = page.request.get(a.api + '/api/v1/dealdesk/rules?mine=true').json()['rules']
            rid = next((r['id'] for r in mine if r['kind'] == 'units'), '')
          page.goto(a.ui + f"/deal-desk/{a.deal}", wait_until="domcontentloaded", timeout=120_000)
          try:
              page.wait_for_selector(T("dealdesk-more-button"), timeout=180_000)
              page.click(T("dealdesk-more-button"))
              page.click(T("dealdesk-action-write"))
              page.wait_for_selector(T("dealdesk-credit-proposal-rules"), timeout=240_000)
              page.click(T("dealdesk-credit-proposal-rules-toggle"))
              row = page.locator(f'{T("dealdesk-credit-proposal-rules-row")}[data-rule="{rid}"]')
              row.wait_for(timeout=60_000)
              st = row.get_attribute("data-status")
              check("the next draft shows the rule under Rules applied, applied", st == "applied", f"{rid}: {st}; {row.inner_text()[:160]}")
              line = page.inner_text(T("dealdesk-credit-proposal-rules-line"))
              check("Rules applied lists the bank's rules too", "rules in force" in line, line)
              row.scroll_into_view_if_needed()
              shot("08_rules_applied_on_proposal")
              body = page.inner_text(T("dealdesk-credit-proposal-pages"))
              check("the proposal follows the rule (amounts as SAR 12.5 mn)", " mn" in body, "")
          except Exception as e:  # noqa: BLE001
              shot("08_rules_applied_failed")
              check("the next draft shows the rule under Rules applied, applied", False, str(e)[:200])

        # 5. Global rules and gold standards
        if 5 in steps:
          page.goto(a.ui + "/policy-docs?view=rules", wait_until="domcontentloaded", timeout=120_000)
          page.wait_for_selector(T("global-rules-row"), timeout=90_000)
          n = page.locator(T("global-rules-row")).count()
          check("Global rules: the seeded SIB-style rules", n >= 8, f"{n} rules")
          shot("09_global_rules")
          page.click(T("policy-kind-gold"))
          page.wait_for_selector(T("rulebook-gold"), timeout=60_000)
          page.set_input_files(T("rulebook-gold-input"), str(GOLD))
          page.wait_for_selector(T("rulebook-gold-compare"), timeout=240_000)
          d = page.locator(T("rulebook-gold-diff")).count()
          check("gold standard: differences from how CreditProbe writes today", d >= 3, f"{d} differences")
          shot("10_gold_differences")
          page.click(T("rulebook-gold-apply"))
          page.wait_for_selector(T("rulebook-gold-result"), timeout=120_000)
          res = page.inner_text(T("rulebook-gold-result"))
          check("“Apply these?” -> bank rules and house style", "rule" in res, res)
          shot("11_gold_applied")
        browser.close()
    check("no page error", not errors, "; ".join(errors[:3]))
    (out / f"results_steps-{a.steps.replace(',', '')}.json").write_text(json.dumps({"checks": checks, "page_errors": errors}, indent=2))
    ok = all(c["ok"] for c in checks)
    print(f"{'PASS' if ok else 'FAIL'}: {sum(c['ok'] for c in checks)}/{len(checks)} checks; screenshots in {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
