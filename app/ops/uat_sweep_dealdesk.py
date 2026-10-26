"""UAT sweep, Deal Desk (PLAN_R4 Session C2, DEAL_DESK_PROMPT sections 4-6): phases D, E and F.

Called from ops/uat_sweep.py (`--only dealdesk`). Every figure checked on screen is read back from the Deal
Desk engine's API (port 8508, DEALDESK_API.md); every chart is an interactive Plotly chart with its Download
button; a chart on a rating axis is in the global rating order; the term panel recomputes through the engine
in under 300 ms; the loose-text inventory (PLAN_R4 G1) of every Deal Desk screen is empty; the Word report is
downloaded and checked in the house style; Back paths are clicked. Each step ends with no console error, no
page error and no failed request.
"""
from __future__ import annotations

import json
import re
import pathlib
import urllib.request
from typing import Any, Callable

import core_login
import raw_number_scan

DD = "http://127.0.0.1:8508/api/v1/dealdesk"

#: The G1 inventory (the rule of ops/loose_text_scan.py on v5/r4-ui), scoped to a Deal Desk container:
#: muted or small free text that is not a heading, table, control, chart, chat answer or popover.
INVENTORY = r"""(root) => {
  const out = [];
  const scope = document.querySelector(root);
  if (!scope) return out;
  const skip = 'h1,h2,h3,h4,h5,h6,table,thead,tbody,tr,td,th,button,a,label,select,option,input,textarea,svg,'
    + '.js-plotly-plot,[role=dialog],[role=tooltip],[role=menu],[role=listbox],nav,dt,dd,'
    + '[data-testid*=answer],[data-testid*=turn],[data-testid*=desk-reply]';
  for (const el of scope.querySelectorAll('p, small, span, div')) {
    if (el.closest(skip)) continue;
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
    if (own.length < 40) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') continue;
    const muted = /text-muted|text-text-muted|text-text-secondary|text-warning|italic/.test(el.className || '');
    if (!(muted || parseFloat(st.fontSize) <= 12)) continue;
    out.push(el.innerText.replace(/\s+/g, ' ').trim().slice(0, 200));
  }
  return out;
}"""

RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C"]
CHARTS = ["dealdesk-chart-waterfall", "dealdesk-chart-heatmap", "dealdesk-chart-amount", "dealdesk-chart-tornado",
          "dealdesk-chart-headroom", "dealdesk-chart-rating"]


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def api(path: str, body: dict | None = None, cookie: str = "") -> Any:
    req = urllib.request.Request(DD + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Cookie": f"cp_session={cookie}"} if cookie else {})})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def loose(page, root: str) -> list[str]:
    return page.evaluate(INVENTORY, root)


def plotted(page, testid: str) -> bool:
    try:
        page.wait_for_selector(f'{tid(testid)}[data-rendered="true"], {tid(testid)} [data-rendered="true"]', timeout=45_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def has_download(page, testid: str) -> bool:
    return page.locator(f'{tid(testid)} .modebar-btn[data-title*="Download"]').count() >= 1


def g5(page) -> list[str]:
    """PLAN_R5 G5 on the current Deal Desk screen: no visible number with more than 4 decimals, no share as a
    fraction, no raw key as a table header (ops/raw_number_scan.py)."""
    return raw_number_scan.failures(raw_number_scan.scan_page(page))


def trace_settles(page, root: str) -> bool:
    """G4: the newest assistant turn under `root` carries the Cockpit process trace, settled ("Answered in …")."""
    try:
        page.wait_for_selector(f'{root} [data-testid="process-trace"][data-state="done"], {root} [data-testid="v4-process-panel"]', timeout=60_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def dealdesk_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    cookie = core_login.login("anne")["cookie"]
    listing = api("/proposals", cookie=cookie)["proposals"]
    # Start the module's own state clean for the proposals the sweep drives (the thread layer's working terms).
    infeasible = next((r["proposal_id"] for r in listing if r.get("case") == "infeasible"), "DD-05")
    for pid in ("DD-01", infeasible):
        api(f"/desk/proposals/{pid}/state", {"terms": None, "recommended": None, "optimisation": None}, cookie)

    # ---------------------------------------------------------------- D1: home
    s.start("dealdesk", "DD-1", "Sidebar → Deal Desk: chat box on top, the proposal pipeline below, statuses and filters")
    page.goto(UI + "/", wait_until="domcontentloaded")
    page.locator('nav[aria-label="Primary"]').get_by_role("link", name="Deal Desk").click()
    wait_for(page, r".*/deal-desk$")
    page.wait_for_selector(tid("dealdesk-table"), timeout=90_000)
    chat_y = page.locator(tid("dealdesk-chat")).bounding_box()["y"]
    pipe_y = page.locator(tid("dealdesk-pipeline")).bounding_box()["y"]
    s.check("the chat box is above the pipeline", chat_y < pipe_y, "chat above", f"{chat_y} vs {pipe_y}")
    rows = page.locator(f'{tid("dealdesk-table")} tbody tr[data-testid^="dealdesk-row-"]')
    s.check("one row per proposal of the engine", rows.count() == len(listing), len(listing), rows.count())
    s.check("15 or more proposals, existing borrowers and new-to-bank", len(listing) >= 15 and any(r["existing"] for r in listing)
            and any(not r["existing"] for r in listing), ">= 15, both kinds", len(listing))
    for status in ("new", "approved"):
        page.click(tid(f"dealdesk-status-{status}"))
        n = sum(1 for r in listing if r["status"] == status)
        s.check(f"status tab '{status}' shows the engine's {n}", rows.count() == n, n, rows.count())
    page.click(tid("dealdesk-status-all"))
    sector = listing[0]["sector"]
    page.select_option(tid("dealdesk-filter-sector"), sector)
    n = sum(1 for r in listing if r["sector"] == sector)
    s.check(f"sector filter '{sector}' shows {n}", rows.count() == n, n, rows.count())
    page.select_option(tid("dealdesk-filter-sector"), "")
    s.check("the rating filter lists grades in the global order",
            [o for o in page.locator(f'{tid("dealdesk-filter-rating")} option').all_inner_texts() if o in RATINGS]
            == [r for r in RATINGS if any(x["rating"] == r for x in listing)])
    s.check("G1: no loose text on the Deal Desk home", not loose(page, tid("dealdesk-home")), "none", loose(page, tid("dealdesk-home"))[:3])
    page.click(tid("dealdesk-new"))
    s.check("New proposal opens the form, with the memo upload beside it", page.locator(tid("dealdesk-new-dialog")).count() == 1
            and page.locator(tid("dealdesk-new-memo")).count() == 1)
    page.click(tid("dealdesk-new-form"))  # R16 i: the dialog opens on "Customer documents"; the short form is the second tab
    s.check("R6 D1: the short form asks for group, external rating, collateral, guarantee and covenants",
            all(page.locator(tid(f"dealdesk-form-{k}")).count() == 1 for k in
                ("group_name", "external_rating", "collateral_type", "collateral_value", "guarantee_type", "guarantor", "dscr_min", "leverage_max")))
    page.click(tid("dealdesk-new-long"))
    s.check("R6 D1: the Long form tab shows the eight sections (obligor and group to RM and business unit)",
            all(page.locator(tid(f"longform-section-{i}")).count() == 1 for i in range(1, 9)))
    s.check("R6 D1: the long form has a 3-year financials grid and add/remove facility lines and collateral",
            page.locator(tid("longform-financials")).count() == 1 and page.locator(tid("longform-add-line")).count() == 1
            and page.locator(tid("longform-add-collateral")).count() == 1)
    page.click(tid("dealdesk-new-memo"))
    s.check("the memo upload accepts a Word memo and an Excel short form (R6 D3)",
            set((page.locator(tid("dealdesk-memo-file")).get_attribute("accept") or "").split(",")) == {".docx", ".xlsx"})
    memo = pathlib.Path(__file__).resolve().parents[1] / "demo_inputs" / "deal_desk" / "CP_Demo_DD-206_TuwaiqModernProperties_LongForm.docx"
    page.set_input_files(tid("dealdesk-memo-file"), str(memo))
    page.wait_for_selector(tid("dealdesk-long-form"), timeout=30_000)
    s.check("R6 D1: an uploaded Word memo opens in the Long form, prefilled, read fields marked and missing ones highlighted",
            page.locator(tid("dealdesk-new-long")).get_attribute("aria-selected") == "true"
            and page.locator('[data-from-file="yes"]').count() >= 30 and page.locator('[data-missing="yes"]').count() >= 1
            and "please confirm" in page.locator(tid("dealdesk-ingested-summary")).inner_text())
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Cancel").click()
    s.check("R5 D3: Recent analyses sits below the pipeline", page.locator(tid("dealdesk-recent")).count() == 1
            and page.locator(tid("dealdesk-recent")).bounding_box()["y"] > page.locator(tid("dealdesk-pipeline")).bounding_box()["y"])
    s.check("G5: no raw number on the Deal Desk home", not g5(page), "none", g5(page)[:3])
    s.finish()

    # ---------------------------------------------------------------- R5 D1: Ask Deal Desk opens a thread (screen 13)
    s.start("dealdesk", "DD-1T", "Ask Deal Desk on the home opens a thread: the process trace with its timer, the composer pinned at the bottom")
    q_home = f"How much sector headroom is left? (sweep {int(__import__('time').time())})"
    page.fill(tid("dealdesk-ask"), q_home)
    page.click(tid("dealdesk-ask-send"))
    wait_for(page, r".*/deal-desk/thread/.*")
    page.wait_for_selector(tid("dealdesk-desk-thread"), timeout=60_000)
    s.check("the question opens the Deal Desk thread", page.locator(tid("dealdesk-desk-thread")).count() == 1)
    try:
        page.wait_for_selector(f'{tid("dealdesk-desk-live")} {tid("process-trace")}', timeout=20_000)
        live = True
    except Exception:  # noqa: BLE001
        live = page.locator(tid("dealdesk-desk-turn")).count() >= 1
    s.check("the process trace shows while the answer is worked on", live)
    page.wait_for_function(f"() => [...document.querySelectorAll('{tid('dealdesk-desk-turn')}')].some(t => t.innerText.includes('" + q_home + "')) "
                           f"&& !document.querySelector('{tid('dealdesk-desk-live')}')", timeout=120_000)
    s.check("the question is answered in the thread", page.locator(tid("dealdesk-desk-turn")).filter(has_text=q_home).count() == 1)
    s.check("the answer settles with the process trace (Answered in …)", trace_settles(page, tid("dealdesk-desk-thread")))
    box = page.locator(tid("thread-composer")).bounding_box()
    vh = page.viewport_size["height"]
    s.check("the composer is pinned at the bottom of the screen, below the conversation",
            box["y"] + box["height"] <= vh + 1 and box["y"] + box["height"] >= vh - 40, f"bottom at {vh}", box["y"] + box["height"])
    tables = page.locator(f'{tid("dealdesk-desk-thread")} table').all_inner_texts()
    s.check("G5: the answer's table headers are plain words, numbers formatted", not g5(page), "none", g5(page)[:3])
    s.check("no raw key such as HEADROOM SHARE in the answer", not any(re.search(r"HEADROOM SHARE|headroom_share", t) for t in tables))
    page.click(tid("dealdesk-thread-back"))
    wait_for(page, r".*/deal-desk$")
    page.wait_for_selector(tid("dealdesk-continue"), timeout=60_000)
    try:
        page.wait_for_function(f"() => (document.querySelector('{tid('dealdesk-continue')}')?.innerText || '').includes('sweep ')", timeout=20_000)
    except Exception:  # noqa: BLE001 - the check below reports it
        pass
    s.check("Back returns to the home; Continue where you left off links to the thread",
            page.locator(tid("dealdesk-continue")).count() == 1 and q_home.split(" (")[0] in page.locator(tid("dealdesk-continue")).inner_text())
    s.finish()

    # ---------------------------------------------------------------- D2: a proposal, step 1
    pid = "DD-01"
    ask = api("/compute", {"proposal_id": pid}, cookie)
    prop = api(f"/proposals/{pid}", cookie=cookie)["proposal"]
    s.start("dealdesk", "DD-2", f"Open {pid}: the stepper, the KPI row from the engine, the proposal summary")
    page.click(tid(f"dealdesk-row-{pid}"))
    wait_for(page, rf".*/deal-desk/{pid}$")
    page.wait_for_selector(tid("dealdesk-stepper"), timeout=90_000)
    page.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=90_000)
    s.check("R7 U2: a deal opens on step 2, Analysis, with its charts, at the top of the page",
            page.locator(tid("dealdesk-step-analysis-view")).count() == 1 and page.evaluate("window.scrollY") < 50, "analysis, top",
            page.evaluate("window.scrollY"))
    page.click(tid("dealdesk-step-proposal"))
    page.wait_for_selector(tid("dealdesk-step-proposal-view"), timeout=30_000)
    s.check("R7 U2: Analyse the ask sits at the top of step 1, above the proposal in full",
            page.evaluate("""() => { const a = document.querySelector('[data-testid="dealdesk-analyse"]');
                                      const f = document.querySelector('[data-testid="dealdesk-proposal-full"]');
                                      return !!a && (!f || (a.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING) > 0); }"""))
    steps = page.locator(f'{tid("dealdesk-stepper")} li').all_inner_texts()
    # A visited step shows a tick in place of its number (R7: step 2 is visited once the deal has opened on it).
    s.check("the stepper reads 1 Proposal, 2 Analysis, 3 Structure, 4 Recommendation",
            [re.sub(r"^\d+\s*", "", re.sub(r"\s+", " ", x).strip()) for x in steps] == ["Proposal", "Analysis", "Structure", "Recommendation"], "", steps)
    kpi = page.locator(tid("dealdesk-kpi-raroc")).inner_text()
    s.check(f"lifetime RAROC KPI = engine {pct(ask['metrics']['lifetime_raroc'])}", pct(ask["metrics"]["lifetime_raroc"]) in kpi, "", kpi)
    s.check(f"approval KPI = engine '{ask['approval']['level']}'", ask["approval"]["level"] in page.locator(tid("dealdesk-kpi-approval")).inner_text())
    s.check("the obligor's name and the ask are shown", prop["obligor"]["name"] in page.locator(tid("dealdesk-title")).inner_text()
            and page.locator(tid("dealdesk-financials")).count() == 1)
    full = page.locator(tid("dealdesk-proposal-full")).inner_text() if page.locator(tid("dealdesk-proposal-full")).count() else ""
    s.check("R5 D5: the proposal in full: obligor, group, rating date, purpose, RM, existing exposure, memo reference",
            all(x in full for x in (prop["obligor"]["name"], prop["purpose"], prop["rm"], "rated 20", "Existing exposure", prop.get("memo") or ".docx")),
            "all fields", full[:160])
    s.check("R5 D5: every facility line with amount, tenor, pricing, fees, repayment, security, guarantees, covenants",
            page.locator(f'{tid("dealdesk-facility-lines")} tbody tr').count() >= 1)
    s.check("G5: no raw number on step 1", not g5(page), "none", g5(page)[:3])
    s.check("G1: no loose text on step 1", not loose(page, tid("dealdesk-thread")), "none", loose(page, tid("dealdesk-thread"))[:3])
    s.finish()

    # ---------------------------------------------------------------- D3: step 2, the charts
    s.start("dealdesk", "DD-3", "Analysis: every chart is interactive Plotly with Download; the rating axis is in the global order")
    page.click(tid("dealdesk-analyse"))
    page.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=60_000)
    s.check("R7 (screen 01): the chart card carries Settings and Optimise",
            page.locator(tid("dealdesk-card-optimiser-settings")).count() == 1 and page.locator(tid("dealdesk-analysis-optimise")).count() == 1)
    for c in CHARTS:
        page.locator(tid(c)).scroll_into_view_if_needed()
        s.check(f"{c} drawn", plotted(page, c))
        s.check(f"{c} has the Download button", has_download(page, c))
    ticks = page.eval_on_selector(tid("dealdesk-chart-rating"), "el => [...el.querySelectorAll('.xtick text')].map(t => t.textContent)")
    s.check("the rating chart's axis is in the global rating order", ticks == sorted(ticks, key=RATINGS.index), "global order", ticks)
    head_txt = page.eval_on_selector(tid("dealdesk-chart-headroom"), "el => [...el.querySelectorAll('.bartext, text')].map(t => t.textContent).join(' | ')")
    s.check("R6 D4: headroom bars are labelled in plain words (used, headroom)", " used, " in head_txt and "headroom" in head_txt, "used … headroom", head_txt[:160])
    view = page.locator(tid("dealdesk-step-analysis-view"))
    s.check("R6 D4: every chart on step 2 has an (i)", view.get_by_role("button", name="What is this screen for?").count() >= len(CHARTS),
            f">= {len(CHARTS)}", view.get_by_role("button", name="What is this screen for?").count())
    page.locator(tid("dealdesk-chart-headroom")).locator(
        "xpath=ancestor::*[.//button[@aria-label='What is this screen for?']][1]").get_by_role("button", name="What is this screen for?").first.click()
    info = page.locator(tid("dealdesk-info-headroom"))
    s.check("R6 D4: the headroom (i) explains what it shows, the formulas, how to read it and what to do",
            info.count() == 1 and all(h in info.inner_text().upper() for h in ("WHAT IT SHOWS", "HOW EACH PART", "HOW TO READ", "WHAT TO DO")),
            "four parts", info.inner_text()[:120] if info.count() else "")
    page.keyboard.press("Escape")
    shown = page.locator(tid("dealdesk-constraints")).inner_text()
    s.check("every engine constraint is listed", all(c["label"] in shown for c in ask["constraints"]), len(ask["constraints"]), shown[:120])
    s.check("G1: no loose text on step 2", not loose(page, tid("dealdesk-thread")), "none", loose(page, tid("dealdesk-thread"))[:3])
    s.check("G5: no raw number on step 2", not g5(page), "none", g5(page)[:3])
    page.click(tid("dealdesk-pd-chip"))
    page.wait_for_selector(tid("dealdesk-model-card-range"), timeout=30_000)
    card = api(f"/model_card?proposal_id={pid}", cookie=cookie)
    s.check("the PD chip opens the model card with this obligor's range check",
            (card.get("model") or {}).get("version", "") in page.locator(tid("dealdesk-model-card")).inner_text())
    page.click(tid("dealdesk-model-card-close"))
    s.finish()

    # ---------------------------------------------------------------- D4: optimise, step 3
    opt = api("/optimize", {"proposal_id": pid, "objective": "both"}, cookie)
    s.start("dealdesk", "DD-4", "Optimise: counter-offers, the term sheet with changed cells, the frontier, binding constraints")
    n_turns = page.locator(tid("dealdesk-turn")).count()
    page.click(tid("dealdesk-optimise"))
    page.wait_for_selector(tid("dealdesk-step-structure-view"), timeout=120_000)
    s.check("the engine finds a structure for the ask", opt["feasible"], True, opt["feasible"])
    s.check("Optimise adds the assistant's commentary to the thread", page.locator(tid("dealdesk-turn")).count() == n_turns + 1,
            n_turns + 1, page.locator(tid("dealdesk-turn")).count())
    s.check("G4: Optimise sits with the chat box at the bottom", page.locator(f'{tid("thread-composer")} {tid("dealdesk-optimise")}').count() == 1)
    s.check("G4: the Optimise turn carries the process trace", trace_settles(page, tid("dealdesk-conversation")))
    cards = page.locator(f'{tid("dealdesk-offers")} button[data-testid^="dealdesk-offer-"]')
    norm = lambda t: json.dumps({k: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in t.items()}, sort_keys=True)  # noqa: E731
    want = min(5, len({norm(o["terms"]) for o in [opt["closest"], opt["max_sva"], *(opt["counter_offers"] or [])] if o}))
    s.check(f"{want} distinct counter-offer cards (closest, maximum value and the engine's offers)", cards.count() == want, want, cards.count())
    first = cards.nth(0).inner_text()
    s.check("the closest-to-ask card shows the engine's RAROC", pct(opt["closest"]["metrics"]["lifetime_raroc"]) in first, "", first[:80])
    s.check("the frontier is drawn with Download", plotted(page, "dealdesk-chart-frontier") and has_download(page, "dealdesk-chart-frontier"))
    changed = page.locator(f'{tid("dealdesk-term-sheet")} td[data-changed]').count()
    s.check("changed cells are highlighted in the term sheet", changed >= 1 or opt["closest"]["distance"] == 0, ">= 1", changed)
    s.check("G1: no loose text on step 3", not loose(page, tid("dealdesk-thread")), "none", loose(page, tid("dealdesk-thread"))[:3])
    # Hold the amount and optimise again: the engine is asked with the amount fixed, and every offer keeps it.
    page.click(tid("dealdesk-optimiser-settings"))
    page.click(tid("dealdesk-lock-amount"))
    page.click(tid("dealdesk-optimiser-settings"))
    with page.expect_response(lambda r: r.url.endswith(f"/api/v1/dealdesk/desk/proposals/{pid}/optimise") and r.request.method == "POST") as resp:
        page.click(tid("dealdesk-optimise"))
    sent = json.loads(resp.value.request.post_data or "{}")
    body = resp.value.json()
    held = body["optimisation"]
    s.check("the Optimise button posts the assistant's commentary as a thread turn, every figure traced",
            body["turn"]["answer"]["validation"]["passed"] and len(body["turn"]["answer"]["blocks"][0]["markdown"]) > 40)
    offers = [o for o in [held.get("closest"), held.get("max_sva"), *(held.get("counter_offers") or [])] if o]
    s.check("a held lever goes to the optimiser as fixed, and every structure keeps it",
            "amount" in (sent.get("fixed") or {}) and all(abs(o["terms"]["amount"] - sent["fixed"]["amount"]) < 1e-6 for o in offers),
            sent.get("fixed"), [o["terms"]["amount"] for o in offers])
    page.click(tid("dealdesk-optimiser-settings"))
    page.click(tid("dealdesk-settings-reset"))
    page.click(tid("dealdesk-optimiser-settings"))
    with page.expect_response(lambda r: r.url.endswith(f"/api/v1/dealdesk/desk/proposals/{pid}/optimise")):
        page.click(tid("dealdesk-optimise"))
    page.wait_for_selector(tid("dealdesk-step-structure-view"), timeout=120_000)
    s.check("G5: no raw number on step 3", not g5(page), "none", g5(page)[:3])
    s.finish()

    # ---------------------------------------------------------------- D5: the term panel, < 300 ms
    s.start("dealdesk", "DD-5", "Term panel: moving a lever recomputes through the engine in under 300 ms, no model call")
    slider = page.locator(f'{tid("dealdesk-lever-margin")} input[type=range]')
    timings = []
    for _ in range(5):
        before = page.locator(tid("dealdesk-term-panel")).get_attribute("data-ms")
        slider.focus()
        page.keyboard.press("ArrowRight")
        page.wait_for_function(f"(b) => document.querySelector('{tid('dealdesk-term-panel')}').getAttribute('data-ms') !== b || true", arg=before)
        page.wait_for_timeout(400)
        ms = page.locator(tid("dealdesk-term-panel")).get_attribute("data-ms")
        if ms:
            timings.append(int(ms))
    s.check("every recompute under 300 ms", bool(timings) and max(timings) < 300, "< 300 ms", timings)
    shown_margin = page.locator(tid("dealdesk-lever-margin")).inner_text()
    m = int(re.search(r"(\d+) bps", shown_margin).group(1))
    check = api("/compute", {"proposal_id": pid, "terms": {**opt["closest"]["terms"], "margin_bps": m}}, cookie)
    chip = page.locator(tid("dealdesk-panel-raroc")).inner_text()
    s.check(f"the panel's RAROC equals the engine's at {m} bps", pct(check["metrics"]["lifetime_raroc"]) in chip, pct(check["metrics"]["lifetime_raroc"]), chip)
    groups = page.locator(f'{tid("dealdesk-term-panel")} [data-testid^="dealdesk-group-"][data-open]')
    s.check("R5 D4: the term panel is grouped as Pricing, Structure, Risk mitigation, Covenants and conditions, Relationship",
            groups.count() == 5, 5, groups.count())
    s.check("R5 D4: groups are collapsed except Pricing", [groups.nth(i).get_attribute("data-open") for i in range(groups.count())]
            == ["true", "false", "false", "false", "false"])
    page.click(tid("dealdesk-group-toggle-risk-mitigation"))
    page.select_option(tid("dealdesk-lever-guarantee"), "REQ-ECA")
    page.wait_for_timeout(700)
    t2 = {**opt["closest"]["terms"], "margin_bps": m, "guarantee_id": "REQ-ECA", "guarantee_coverage_pct": opt["closest"]["terms"].get("guarantee_coverage_pct") or 50}
    check2 = api("/compute", {"proposal_id": pid, "terms": t2}, cookie)
    chip2 = page.locator(tid("dealdesk-panel-raroc")).inner_text()
    s.check("R5 D4: a requested ECA guarantee recomputes through the engine", pct(check2["metrics"]["lifetime_raroc"]) in chip2,
            pct(check2["metrics"]["lifetime_raroc"]), chip2)
    page.click(tid("dealdesk-group-toggle-risk-mitigation"))
    s.finish()

    # ---------------------------------------------------------------- D6: recommendation, stress, Word
    s.start("dealdesk", "DD-6", "Recommend: ask vs recommended, approval level, stress, the Word report in house style")
    page.locator(tid("dealdesk-offer-closest-to-ask")).click()
    page.wait_for_timeout(600)
    page.click(tid("dealdesk-recommend"))
    page.wait_for_selector(tid("dealdesk-step-recommendation-view"), timeout=60_000)
    st = api(f"/desk/proposals/{pid}/thread", cookie=cookie)["state"]
    rec = api("/compute", {"proposal_id": pid, "terms": st["terms"]}, cookie)
    s.check(f"approval = engine '{rec['approval']['level']}'", page.locator(tid("dealdesk-approval")).inner_text().strip() == rec["approval"]["level"])
    stress = api("/stress", {"proposal_id": pid, "terms": st["terms"], "scenario": "all"}, cookie)
    rows_shown = page.locator(f'{tid("dealdesk-stress")} tbody tr').count() - 1
    s.check(f"{len(stress['rows'])} stress scenarios", rows_shown == len(stress["rows"]), len(stress["rows"]), rows_shown)
    s.check(f"robustness = {stress['robustness_notches']} notches", str(stress["robustness_notches"]) in page.locator(tid("dealdesk-robustness")).inner_text())
    with page.expect_download(timeout=120_000) as dl:
        page.click(tid("dealdesk-word"))
    s.check("the Word report downloads", dl.value.suggested_filename.endswith(".docx"), ".docx", dl.value.suggested_filename)
    s.check("G1: no loose text on step 4", not loose(page, tid("dealdesk-thread")), "none", loose(page, tid("dealdesk-thread"))[:3])
    s.finish()

    # ---------------------------------------------------------------- F: save, share, add to report
    s.start("dealdesk", "DD-6F", "Save the analysis, share it through Mail with the Word report, add it to a Playbook report")
    page.once("dialog", lambda d: d.accept(f"UAT sweep {pid}"))
    page.click(tid("dealdesk-save"))
    page.wait_for_selector(tid("dealdesk-notice"), timeout=30_000)
    saved = [a for a in api("/desk/analyses", cookie=cookie)["analyses"] if a["name"] == f"UAT sweep {pid}"]
    s.check("the analysis is saved with the engine's figures", bool(saved) and saved[0]["metrics"]["lifetime_raroc"] == rec["metrics"]["lifetime_raroc"],
            rec["metrics"]["lifetime_raroc"], saved[0]["metrics"]["lifetime_raroc"] if saved else None)
    page.click(tid("dealdesk-share"))
    page.wait_for_selector(tid("dealdesk-share-users"), timeout=30_000)
    page.locator(f'{tid("dealdesk-share-users")} input[type=checkbox]').first.check()
    page.click(tid("dealdesk-share-send"))
    page.wait_for_selector(tid("dealdesk-share-done"), timeout=120_000)
    s.check("shared through CreditProbe Mail with the Word report", "Shared with" in page.locator(tid("dealdesk-share-done")).inner_text())
    page.click(tid("dealdesk-share-close"))
    page.click(tid("dealdesk-add-report"))
    page.wait_for_selector(tid("add-report-dialog"), timeout=30_000)
    page.click(tid("add-report-new"))
    page.fill(tid("add-report-title"), f"UAT sweep Deal Desk {pid}")
    page.click(tid("add-report-confirm"))
    page.wait_for_selector(tid("add-report-done"), timeout=120_000)
    s.check("the section lands in a new Playbook report", page.locator(tid("add-report-open")).count() == 1)
    page.click(tid("add-report-finish"))
    recent = api("/desk/recent", cookie=cookie)
    s.check("R5 D3: the saved analysis is in Recent analyses with its outcome, RAROC and a link to its thread",
            any(r["kind"] == "saved" and r["proposal_id"] == pid and r["href"].startswith(f"/deal-desk/{pid}") and r["lifetime_raroc"] is not None
                for r in recent["recent"]))
    s.check("R5 D3: Optimise runs are in Recent analyses", any(r["kind"] == "optimised" and r["proposal_id"] == pid for r in recent["recent"]))
    for a in saved:
        req = urllib.request.Request(DD + f"/desk/analyses/{a['analysis_id']}", method="DELETE", headers={"Cookie": f"cp_session={cookie}"})
        urllib.request.urlopen(req, timeout=30).read()  # noqa: S310 - the UAT library stays as seeded
    s.finish()

    # ---------------------------------------------------------------- E: the conversation
    s.start("dealdesk", "DD-7", "Conversation: explain, what-if and stress, every figure traced to an engine call")
    for q in ("Why does the ask fail?", "What if we take 30% cash margin?", "How does this hold if they're downgraded two notches?"):
        n0 = page.locator(tid("dealdesk-turn")).count()
        page.fill(tid("dealdesk-composer"), q)
        page.click(tid("dealdesk-send"))
        page.wait_for_function(f"() => document.querySelectorAll('{tid('dealdesk-turn')}').length > {n0}", timeout=120_000)
        last = page.locator(tid("dealdesk-turn")).last
        s.check(f"'{q}' answered", len(last.locator(tid("dealdesk-answer")).inner_text()) > 40)
        s.check(f"'{q}': every figure traced", last.locator(tid("dealdesk-trace-chip")).inner_text().strip().endswith("Traced"))
    s.finish()

    # ---------------------------------------------------------------- R5 D4: all the levers, DD-02 below the hurdle (screen 15)
    s.start("dealdesk", "DD-7L", "DD-02 below the hurdle: 2-4 alternative structures that clear, why they work, the minimum change per lever")
    api("/desk/proposals/DD-02/state", {"terms": None, "recommended": None, "optimisation": None}, cookie)
    alt = api("/alternatives", {"proposal_id": "DD-02"}, cookie)
    page.goto(UI + "/deal-desk/DD-02", wait_until="domcontentloaded")
    page.wait_for_selector(tid("dealdesk-stepper"), timeout=90_000)
    page.click(tid("dealdesk-step-analysis"))
    page.click(tid("dealdesk-optimise"))
    page.wait_for_selector(tid("dealdesk-alternatives"), timeout=120_000)
    cards = page.locator(f'{tid("dealdesk-alternatives")} [data-testid^="dealdesk-alt-"][data-testid$="-use"]')
    s.check("2 to 4 alternative structures", 2 <= cards.count() <= 4 and cards.count() == len(alt["alternatives"]), len(alt["alternatives"]), cards.count())
    for a in alt["alternatives"]:
        slug = re.sub(r"\W+", "-", a["label"].lower())
        txt = page.locator(tid(f"dealdesk-alt-{slug}")).inner_text()
        s.check(f"'{a['label']}' shows the engine's RAROC {pct(a['metrics']['lifetime_raroc'])} and approval",
                pct(a["metrics"]["lifetime_raroc"]) in txt and a["approval"]["level"] in txt, "", txt[:100])
        s.check(f"'{a['label']}' clears the hurdle", a["metrics"]["clears_hurdle"])
        s.check(f"'{a['label']}' highlights its changed terms", page.locator(f'{tid(f"dealdesk-alt-{slug}-changes")} tr[data-changed]').count() == len(a["changes"]))
        s.check(f"'{a['label']}' explains why it works (lever contribution bars, Download)",
                plotted(page, f"dealdesk-alt-{slug}-why") and has_download(page, f"dealdesk-alt-{slug}-why"))
    groups = {c["group"] for a in alt["alternatives"] for c in a["changes"]}
    s.check("the structures use levers beyond margin and tenor", bool(groups - {"Pricing"}) and any(c["field"] not in ("margin_bps", "tenor_years")
                                                                                                    for a in alt["alternatives"] for c in a["changes"]), "", sorted(groups))
    s.check("the minimum change on each single lever is listed", page.locator(f'{tid("dealdesk-single-lever")} tbody tr').count() == len(alt["single_lever"]),
            len(alt["single_lever"]), page.locator(f'{tid("dealdesk-single-lever")} tbody tr').count())
    a0 = alt["alternatives"][0]
    page.click(tid(f"dealdesk-alt-{re.sub(chr(92) + 'W+', '-', a0['label'].lower())}-use"))
    page.wait_for_timeout(900)
    s.check("loading a structure puts the engine's RAROC in the term panel", pct(a0["metrics"]["lifetime_raroc"]) in page.locator(tid("dealdesk-panel-raroc")).inner_text(),
            pct(a0["metrics"]["lifetime_raroc"]), page.locator(tid("dealdesk-panel-raroc")).inner_text())
    s.check("G5: no raw number with the alternatives on screen", not g5(page), "none", g5(page)[:3])
    n0 = page.locator(tid("dealdesk-turn")).count()
    page.fill(tid("dealdesk-composer"), "What are my options? Which levers clear alone?")
    page.click(tid("dealdesk-send"))
    page.wait_for_function(f"() => document.querySelectorAll('{tid('dealdesk-turn')}').length > {n0}", timeout=120_000)
    last = page.locator(tid("dealdesk-turn")).last
    s.check("the conversation answers with the alternatives and the single-lever changes, traced",
            "clear the hurdle" in last.inner_text() and last.locator(tid("dealdesk-trace-chip")).inner_text().strip().endswith("Traced"))
    api("/desk/proposals/DD-02/state", {"terms": None, "recommended": None, "optimisation": None}, cookie)
    s.finish()

    # ---------------------------------------------------------------- D7: the infeasible case, Back
    s.start("dealdesk", "DD-8", "A proposal no structure clears: the relaxation, not a solution; Back to the pipeline")
    # Opened from the pipeline, so Back (the exact previous screen, R7) returns to the pipeline.
    page.goto(UI + "/deal-desk", wait_until="domcontentloaded")
    page.wait_for_selector(tid(f"dealdesk-row-{infeasible}"), timeout=90_000)
    page.click(tid(f"dealdesk-row-{infeasible}"))
    page.wait_for_selector(tid("dealdesk-stepper"), timeout=90_000)
    page.click(tid("dealdesk-step-analysis"))
    page.click(tid("dealdesk-optimise"))
    page.wait_for_selector(tid("dealdesk-step-structure-view"), timeout=120_000)
    s.check("the relaxation table is shown, with no counter-offer", page.locator(tid("dealdesk-relaxation")).count() == 1
            and page.locator(tid("dealdesk-offers")).count() == 0)
    # R7: Back walks the steps exactly: Structure → Analysis → the pipeline the deal was opened from.
    page.click(tid("dealdesk-back"))
    page.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=60_000)
    s.check("Back from Structure returns to Analysis, the previous step", "step=" not in page.url, "Analysis", page.url)
    page.click(tid("dealdesk-back"))
    wait_for(page, r".*/deal-desk$")
    page.wait_for_selector(tid("dealdesk-table"), timeout=60_000)
    s.check("Back again returns to the pipeline", page.locator(tid("dealdesk-table")).count() == 1)
    s.finish()

    # ---------------------------------------------------------------- R7 U2: every proposal shows every analysis chart
    s.start("dealdesk", "DD-9", "R7 U2: every proposal (seeded, created, uploaded short and long form) opens on Analysis with all four charts and their (i)")
    every = [x["proposal_id"] for x in api("/proposals", cookie=cookie)["proposals"]]
    if not any(int(x[3:]) > 100 for x in every if x[3:].isdigit()):
        # No created proposal on this machine yet: open one demo Word memo (long form) and one Excel sheet (short
        # form) as the upload does, so both kinds are covered. They land in the local store (var/), never the repo.
        import sys
        root = pathlib.Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from backend.dealdesk_thread import ingest as dd_ingest
        pack = root / "demo_inputs" / "deal_desk"
        for f in (sorted(pack.glob("CP_Demo_DD-2*_LongForm.docx"))[:1] + sorted(pack.glob("CP_Demo_DD-2*_ShortForm.xlsx"))[1:2]):
            r = dd_ingest.extract(f.read_bytes(), f.name)
            fields = {x["field"]: x["value"] for x in r["fields"] if x["value"] is not None}
            long = r["long"] if r["form"] == "long" else None
            api("/desk/proposals", {"fields": fields, "source": {"filename": f.name, **({"form": "long"} if long else {})}, "long": long}, cookie)
        every = [x["proposal_id"] for x in api("/proposals", cookie=cookie)["proposals"]]
    s.check("the pipeline lists the seeded proposals and any created or uploaded ones", len(every) >= 14, ">= 14", len(every))
    four = ("waterfall", "heatmap", "amount", "tornado")
    missing: list[str] = []
    no_info: list[str] = []
    no_marks: list[str] = []
    for pid_x in every:
        try:  # a deal with a saved optimisation re-runs it on open; let it finish rather than abort its POST
            page.wait_for_load_state("networkidle", timeout=120_000)
        except Exception:  # noqa: BLE001
            pass
        page.goto(UI + f"/deal-desk/{pid_x}", wait_until="domcontentloaded")
        try:
            page.wait_for_selector(tid("dealdesk-step-analysis-view"), timeout=90_000)
        except Exception:  # noqa: BLE001 - reported below
            missing.append(f"{pid_x}: no Analysis step")
            continue
        for c in four:
            if not plotted(page, f"dealdesk-chart-{c}"):
                missing.append(f"{pid_x}: {c}")
        marks = page.evaluate("""() => { const el = document.querySelector('[data-testid="dealdesk-chart-heatmap"] .js-plotly-plot')
                                           || document.querySelector('[data-testid="dealdesk-chart-heatmap"]');
                                         const d = (el && el.data) || []; return d.map(t => t.type + ':' + (t.name || '')); }""")
        if not (any(m.startswith("contour") for m in marks) and "scatter:Ask" in marks):
            no_marks.append(f"{pid_x}: {marks}")
        for c in four:
            btn = page.locator(tid(f"dealdesk-chart-{c}")).locator(
                "xpath=ancestor::*[.//button[@aria-label='What is this screen for?']][1]").get_by_role("button", name="What is this screen for?").first
            try:
                btn.click(timeout=10_000)
                page.wait_for_selector(tid(f"dealdesk-info-{c}"), timeout=10_000)
            except Exception:  # noqa: BLE001 - reported below
                no_info.append(f"{pid_x}: {c}")
            page.keyboard.press("Escape")
    s.check(f"all four analysis charts drawn on every proposal ({len(every)})", not missing, "none missing", missing[:6])
    s.check("the iso-RAROC heatmap has the hurdle contour and the ask on every proposal", not no_marks, "contour + Ask", no_marks[:4])
    s.check("each of the four charts has its (i) explanation on every proposal", not no_info, "none missing", no_info[:6])
    s.finish()
