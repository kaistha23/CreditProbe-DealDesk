"""PLAN_R12 N2: screenshots of every module's answer in the shared answer style, at 1440x900 and 1280x800.

  .venv/bin/python ops/r12_answer_shots.py [--ui http://127.0.0.1:5500] [--only dealdesk,whatif,...]

Writes docs/v5/r12_answers/<module>-<w>x<h>.png and docs/v5/r12_answers/shots.json (overflow probe, headline present,
internal tool names absent). Needs the app running (ops/v5.sh start). Mints a session in the identity store; no
password or secret is read or printed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
from playwright.sync_api import Page, sync_playwright  # noqa: E402

OUT = V5 / "docs" / "v5" / "r12_answers"
SIZES = [(1440, 900), (1280, 800)]
TOOL = re.compile(r"\b(pipeline_optimi[sz]e|pipeline_test|stress_lab|whatif_[a-z_]+|lenses_[a-z_]+|fetch_[a-z_]+|run_query|query_dataset|"
                  r"compute_terms|review_memo|committee_sheet|forward_risk|ews_[a-z_]+|triage_[a-z_]+|propose_[a-z_]+)\b")

PROBE = r"""
(sel) => {
  const root = document.querySelector(sel);
  if (!root) return {missing: true};
  const vw = window.innerWidth, over = [];
  for (const e of root.querySelectorAll('*')) {
    if (e.offsetParent === null || e.closest('svg') || e.closest('.js-plotly-plot')) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.right > vw + 1) over.push('beyond viewport: ' + e.tagName + ' ' + (e.textContent || '').trim().slice(0, 40));
    if (over.length > 8) break;
  }
  return {docWidth: document.documentElement.scrollWidth, vw, overflow: over,
          headline: !!root.querySelector('[data-testid=answer-headline],[data-testid=v4-answer-headline]'),
          style: !!root.closest('[data-answer-style]') || !!root.querySelector('[data-answer-style]'),
          plotly: root.querySelectorAll('.js-plotly-plot').length,
          text: (root.innerText || '').slice(0, 4000)};
}
"""


def mint() -> str:
    from r10_chat_audit import session
    return session()


def ask_in(page: Page, composer: str, send: str, question: str) -> None:
    page.fill(composer, question)
    page.click(send)


# module -> (url, how to get an answer (None = the URL asks), answer selector, timeout s)
SCENES: dict[str, dict] = {}


def scene(name: str, url: str, answer: str, composer: str | None = None, send: str | None = None, question: str = "",
          timeout: int = 120, before=None, route=None):
    SCENES[name] = dict(url=url, answer=answer, composer=composer, send=send, question=question, timeout=timeout, before=before,
                        route=route)


scene("dealdesk", "/deal-desk/DD-01?q=Why%20does%20the%20ask%20fail%3F", '[data-testid="dealdesk-answer"]')
scene("dealdesk-chart", "/deal-desk/DD-01?q=Which%20levers%20clear%20the%20hurdle%20alone%3F", '[data-testid="dealdesk-answer"]')


def _committee(page: Page) -> None:
    page.wait_for_selector('[data-testid="prepare-for-committee"]', timeout=90_000)
    page.click('[data-testid="prepare-for-committee"]')


scene("agent-drawer", "/deal-desk/DD-01", '[data-testid="agent-answer"]', timeout=240, before=_committee)
scene("scorecard", "/scorecard-validation", '[data-testid="sv-answer"]', composer='[data-testid="sv-ask"]', send=None,
      question="Validate the retail application scorecard", timeout=180)
scene("playbook", "/playbook", '[data-testid="playbook-chat-message"][data-role="assistant"]', composer='[data-testid="playbook-chat-input"]',
      send='[data-testid="playbook-chat-send"]', question="I want to draft a corporate ECL report for the construction sector", timeout=240)
scene("projects", "/projects/construction-deep-dive-q2-2026/threads/pt-construction-why", '[data-testid="ws-thread-msg-assistant"]', timeout=90)
scene("brf", "/brf", '[data-testid="brf-answer"]', composer='[data-testid="brf-say"]', send='[data-testid="brf-say-send"]',
      question="What does this return need from the domains?", timeout=120)


def _admin(page: Page) -> None:
    page.wait_for_selector('[data-testid="admin-assistant-open"]', timeout=90_000)
    page.click('[data-testid="admin-assistant-open"]')
    page.locator('[data-testid="admin-assistant-seed"]').first.click()


scene("admin", "/workflow", '[data-testid="admin-assistant"] [data-testid="answer-blocks"]', timeout=180, before=_admin)


def _lens(page: Page) -> None:
    page.wait_for_selector('[data-testid="lenses-ask"]', timeout=90_000)
    page.fill('[data-testid="lenses-ask"]', "Construction sector dashboard")
    page.click('[data-testid="lenses-build"]')
    page.wait_for_selector('[data-testid="lens-view"]', timeout=180_000)
    page.wait_for_selector('[data-testid="lens-assistant"][data-busy="0"]', timeout=180_000)


scene("lenses", "/lenses", '[data-testid="lens-assistant"] [data-testid="thread-turn-assistant"]', timeout=60, before=_lens)


def _cockpit_query(page: Page) -> None:
    page.wait_for_selector('[data-testid="cockpit-v4-question"]', timeout=90_000)
    page.fill('[data-testid="cockpit-v4-question"]', "Answer the auditor's question on 30+ DPD loans still in Stage 1")
    page.click('[data-testid="cockpit-v4-ask"]')


scene("cockpit-queries", "/", '[data-testid="cockpit-queries"] section[data-testid$="-lead"]', timeout=180, before=_cockpit_query)


def _whatif_url() -> str:
    import urllib.request
    body = json.dumps({"domain": "corporate", "question": "What if oil falls 30% and PDs rise 15% in construction?"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8503/api/v1/whatif/threads", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Cookie": f"cp_session={TOKEN[0]}"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - loopback
        t = json.loads(r.read())
    return f"/what-if/thread/{t['thread']['thread_id'] if 'thread' in t else t['thread_id']}"


TOKEN: list[str] = []
DARK = {"cockpit", "whatif-question", "lenses", "dealdesk"}


# The Cockpit needs a model to answer; its renderer (FX-R12-02) is shown on a stored-thread transcript served to the page.
def _axis(label, unit, ticks):
    return {"kind": "measure", "label": label, "column": label, "unit": unit, "ticks": [{"value": v, "display": d} for v, d in ticks]}


def _pts(rows, cols, fmt):
    return [{"row_id": f"r{i}", "label": lab, "values": dict(zip(cols, vals)), "display": {c: fmt(v) for c, v in zip(cols, vals)}}
            for i, (lab, *vals) in enumerate(rows)]


SAR = lambda v: f"SAR {v:,.0f} million"  # noqa: E731
COCKPIT_THREAD = {
    "domain_id": "corporate", "domain_label": "Corporate book", "domain_short_label": "Corporate", "thread_id": "th-r12-demo",
    "title": "Construction Stage 2 since Q1", "turn_count": 1, "created_at": "2026-10-19T08:00:00Z", "context": {},
    "turns": [{"turn_id": "tu1", "run_id": "run-r12-demo", "ordinal": 1, "created_at": "2026-10-19T08:00:00Z",
               "question": "Why did Stage 2 rise in construction this quarter?",
               "answer": {
                   "disposition": "answer", "result_only": False, "executed": True, "coverage": [],
                   "intent": {"query_mode": "analysis", "owner": "", "understood_request": "Stage 2 movement in construction"},
                   "narrative": ("Stage 2 exposure in construction rose to **SAR 4,120 million** in 2026Q2, up **SAR 610 million** on 2026Q1, "
                                 "driven mainly by downgrades in building contracting.\n\nBuilding contracting added SAR 380 million and roads and "
                                 "bridges SAR 150 million; the other sub-sectors were broadly flat.\n\nSignificant-increase triggers were rating "
                                 "downgrades of two notches or more (62% of the move) and 30+ days past due (24%).\n\nCoverage on the new Stage 2 "
                                 "names is 4.1%, against 3.6% for the sector's existing Stage 2 book.\n\nThe move is concentrated: the five largest "
                                 "new Stage 2 names account for SAR 290 million of the SAR 610 million.\n\nEarly Warning had flagged four of those five "
                                 "names in the previous quarter."),
                   "tables": [], "numeric_claims": [], "limitations": [], "clarification_question": "", "clarification_options": [],
                   "referral_owner": "", "referral_reason": "",
                   "suggested_questions": [{"question": "Run pipeline_optimise on construction", "kind": "follow"},
                                           {"question": "Which new Stage 2 names were flagged by Early Warning?", "kind": "follow"}],
                   "charts": [
                       {"kind": "bar", "title": "Stage 2 increase by sub-sector, 2026Q2", "artifact_id": "a1", "x_column": "sub_sector",
                        "y_columns": ["increase"], "unit": "SAR million",
                        "points": _pts([("Building contracting", 380), ("Roads and bridges", 150), ("Electromechanical", 45),
                                        ("Marine works", 25), ("Site preparation", 10)], ["increase"], SAR),
                        "y_axis": _axis("Stage 2 increase", "SAR million", [(0, "0"), (100, "100"), (200, "200"), (300, "300"), (400, "400")])},
                       {"kind": "line", "title": "Construction Stage 2 exposure by quarter", "artifact_id": "a2", "x_column": "quarter",
                        "y_columns": ["stage2"], "unit": "SAR million",
                        "points": _pts([("2025Q3", 3210), ("2025Q4", 3380), ("2026Q1", 3510), ("2026Q2", 4120)], ["stage2"], SAR),
                        "y_axis": _axis("Stage 2 exposure", "SAR million", [(3000, "3,000"), (3500, "3,500"), (4000, "4,000"), (4500, "4,500")])},
                       {"kind": "waterfall", "title": "From 2026Q1 to 2026Q2", "artifact_id": "a3", "x_column": "step",
                        "y_columns": ["amount"], "unit": "SAR million",
                        "points": _pts([("2026Q1", 3510), ("Downgrades", 520), ("Past due", 180), ("Cures", -90), ("2026Q2", 4120)], ["amount"],
                                       lambda v: f"SAR {v:+,.0f} million" if abs(v) < 1000 else SAR(v)),
                        "y_axis": _axis("Stage 2 exposure", "SAR million", [(3000, "3,000"), (3500, "3,500"), (4000, "4,000"), (4500, "4,500")])},
                       {"kind": "donut", "title": "Triggers behind the move", "artifact_id": "a4", "x_column": "trigger",
                        "y_columns": ["share"], "unit": "%",
                        "points": _pts([("Downgrade of 2+ notches", 62), ("30+ days past due", 24), ("Watchlist", 9), ("Other", 5)], ["share"],
                                       lambda v: f"{v}%")},
                   ]}}],
}


def _cockpit_route(page: Page) -> None:
    body = json.dumps(COCKPIT_THREAD)
    page.route("**/api/v1/cockpit-v4/threads/th-r12-demo", lambda r: r.fulfill(status=200, content_type="application/json", body=body,
                                                                                   headers={"access-control-allow-origin": "http://127.0.0.1:5500",
                                                                                            "access-control-allow-credentials": "true"}))


scene("cockpit", "/cockpit/thread/th-r12-demo", '[data-testid="v4-turn-assistant"]', timeout=90, route=_cockpit_route)
scene("whatif", "@whatif", '[data-testid="whatif-answer"]', timeout=240)
scene("whatif-question", "@whatif", '[data-testid="whatif-answer"]', composer='[data-testid="whatif-composer"]', send='[data-testid="whatif-send"]',
      question="Which sub-sectors carry the most Stage 2 exposure, and how has it moved?", timeout=240)


def run(ui: str, only: set[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    token = mint()
    TOKEN.append(token)
    results = {}
    urls: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, sc in SCENES.items():
            if only and name not in only:
                continue
            for w, h in SIZES:
                ctx = browser.new_context(viewport={"width": w, "height": h})
                ctx.add_cookies([{"name": "cp_session", "value": token, "url": ui}])
                page = ctx.new_page()
                key = f"{name}-{w}x{h}"
                try:
                    if sc["route"]:
                        sc["route"](page)
                    url = sc["url"]
                    if url == "@whatif":
                        url = urls.setdefault("whatif", _whatif_url())
                    page.goto(ui + url, wait_until="domcontentloaded", timeout=90_000)
                    if sc["before"]:
                        sc["before"](page)
                    n0 = 0
                    if sc["composer"]:
                        page.wait_for_selector(sc["composer"], timeout=60_000)
                        page.wait_for_timeout(1500)
                        n0 = page.locator(sc["answer"]).count()
                        if sc["send"]:
                            ask_in(page, sc["composer"], sc["send"], sc["question"])
                        else:
                            page.fill(sc["composer"], sc["question"])
                            page.press(sc["composer"], "Enter")
                    if n0:
                        page.wait_for_function("([sel, n]) => document.querySelectorAll(sel).length > n", arg=[sc["answer"], n0],
                                               timeout=sc["timeout"] * 1000)
                    loc = page.locator(sc["answer"]).last
                    loc.wait_for(timeout=sc["timeout"] * 1000)
                    time.sleep(3.5)  # Plotly draws after mount; the thread finishes its own scroll
                    # The answer's top (its headline) at the top of the view, under the app bar.
                    loc.evaluate("e => { e.scrollIntoView({block: 'start'}); let s = e.parentElement; "
                                 "while (s && !(s.scrollHeight > s.clientHeight && /auto|scroll/.test(getComputedStyle(s).overflowY))) s = s.parentElement; "
                                 "if (s) s.scrollTop -= 72; else window.scrollBy(0, -72); }")
                    time.sleep(1.0)
                    probe = page.evaluate(PROBE, sc["answer"])
                    box = loc.bounding_box()
                    if box and box["height"] <= h - 160:
                        loc.screenshot(path=str(OUT / f"{key}-answer.png"))
                    page.screenshot(path=str(OUT / f"{key}.png"))
                    if w == 1440 and name in DARK:
                        page.evaluate("document.documentElement.setAttribute('data-theme', 'midnight')")
                        time.sleep(2.5)
                        page.screenshot(path=str(OUT / f"{key}-dark.png"))
                    text = probe.pop("text", "")
                    probe["tool_names"] = sorted(set(TOOL.findall(text)))
                    results[key] = probe
                except Exception as exc:  # noqa: BLE001
                    results[key] = {"error": str(exc).splitlines()[0][:200]}
                    try:
                        page.screenshot(path=str(OUT / f"{key}-error.png"))
                    except Exception:  # noqa: BLE001
                        pass
                print(key, json.dumps(results[key])[:300], flush=True)
                ctx.close()
        browser.close()
    prev = json.loads((OUT / "shots.json").read_text()) if (OUT / "shots.json").exists() else {}
    prev.update(results)
    (OUT / "shots.json").write_text(json.dumps(prev, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sys.exit(run(a.ui, {x for x in a.only.split(",") if x}))
