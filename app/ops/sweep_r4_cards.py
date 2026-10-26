"""UAT sweep, PLAN_R4 (part "r4-cards"): B1, Plotly charts on every Cockpit card, and G1 on the Cockpit home.

Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep. For both books, every card on the
Cockpit home opens its drawer and draws its four Plotly charts (trend, against the book, contributors, stage mix):
the attention items, the ECL highlights, and the ECL panel's EAD, Recognised ECL, Coverage, stage rows and
decomposition components. The drawn figures equal the chart API (backend/attention_v5), the chart API ends on the
card's own numbers, close (button and Escape) works, and the home carries none of the known loose-text phrases.
Console errors, failed requests and banned labels are checked by the Sweep at the end of every step.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable

import core_login
from loose_text_scan import known_in, SCREEN_TEXT
from uat_sweep_core import as_user, cookie_of, tid

COCKPIT = "http://127.0.0.1:8500/api/v1/cockpit-v4"
PLOTS = ("trend", "peers", "contributors", "stage")

#: Plotly draws into these, and the figure it holds is read back from the element (`el.data`).
READ = """(root) => {
  const scope = document.querySelector(root);
  const d = (id) => scope.querySelector('[data-testid="' + id + '"]').data;
  return {trend: d('attention-plot-trend'), peers: d('attention-plot-peers'),
          contrib: d('attention-plot-contributors'), stage: d('attention-plot-stage')};
}"""


def _cockpit(path: str) -> Any:
    with urllib.request.urlopen(COCKPIT + path, timeout=120) as r:  # noqa: S310 - loopback
        return json.load(r)


def _charts(ck: str, **q: str) -> dict:
    return core_login.api_get("/api/v1/attention/charts?" + urllib.parse.urlencode(q), ck)


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def _same(a: list, b: list) -> bool:
    """Equal lists of numbers, to the last few digits (two reads of a parallel SUM can differ at 1e-13)."""
    return len(a) == len(b) and all((x is None and y is None) or (x is not None and y is not None and _close(x, y, 1e-9))
                                    for x, y in zip(a, b))


def _figures_equal(s, label: str, got: dict, c: dict) -> None:
    """The four drawn figures carry exactly the chart API's numbers."""
    t = c["trend"]
    seg_name = (c.get("trend_labels") or {}).get("segment")
    line = got["trend"][0]
    book_line = next((tr for tr in got["trend"][1:] if tr.get("mode") == "lines"), None)
    book_expected = bool((c.get("trend_labels") or {"book": "Whole book"}).get("book"))
    s.check(f"{label}: trend is the API's {len(t['periods'])} periods",
            line["x"] == t["periods"] and _same(line["y"], t["segment"]) and (seg_name is None or line["name"] == seg_name)
            and ((book_line is not None and _same(book_line["y"], t["book"])) if book_expected else book_line is None),
            t["segment"][-2:], str(line["y"])[-80:])
    cur = got["trend"][-1]
    s.check(f"{label}: the current period is highlighted", cur["x"] == [t["periods"][-1]] and _same(cur["y"], [t["segment"][-1]]),
            t["periods"][-1], cur.get("x"))
    peers = sorted(c["peers"]["items"], key=lambda p: p["value"])
    s.check(f"{label}: against the book shows every {c['dimension_label'].lower()}",
            got["peers"][0]["y"] == [p.get("label") or p["segment"] for p in peers] and _same(got["peers"][0]["x"], [p["value"] for p in peers]),
            len(peers), len(got["peers"][0]["y"]))
    view = c["contributors"]["views"][0]
    wf = got["contrib"][0]
    s.check(f"{label}: the contributors waterfall adds up exactly ({view['total_change']:.4f})",
            _close(sum(wf["y"][:-1]), view["to"]) and wf["measure"][0] == "absolute" and wf["measure"][-1] == "total"
            and _close(sum(i["change"] for i in view["items"]), view["total_change"]), view["to"], sum(wf["y"][:-1]))
    ead = c["stage_mix"]["ead"]
    s.check(f"{label}: stage mix bars equal the API", len(got["stage"]) == 3
            and all(_same(got["stage"][k]["y"], [ead[0][k], ead[1][k]]) for k in range(3)),
            ead, [tr["y"] for tr in got["stage"]])


def _wait_plots(pg, root: str) -> bool:
    try:
        for plot in PLOTS:
            pg.wait_for_selector(f'{root} {tid("attention-plot-" + plot)}[data-rendered="true"]', timeout=60_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def _no_unavailable(s, pg, label: str, root: str) -> None:
    text = pg.inner_text(root)
    s.check(f"{label}: no 'charts are not available', no retry", "not available" not in text.lower()
            and pg.locator(f'{root} {tid("attention-charts-retry")}').count() == 0, "charts drawn", text[:120])


def _open_home(pg, UI: str, book: str) -> None:
    pg.goto(UI + "/", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("attention-card"), timeout=120_000)
    pg.click(tid(f"domain-{book}"))
    pg.wait_for_selector(f'{tid("v4-ecl-panel")}[data-state="ready"][data-domain="{book}"]', timeout=120_000)
    pg.wait_for_timeout(1500)


def cards_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    browser = page.context.browser
    ctx, pg, _ = as_user(browser, s, "anne")
    ck = cookie_of("anne")
    for book in ("corporate", "retail"):
        feed = _cockpit(f"/attention?domain={book}")
        sections = (("segments-requiring-attention", feed["segments_requiring_attention"]), ("ecl-highlights", feed["ecl_highlights"]))
        families = sorted({it["family"] for _, items in sections for it in items})
        n_items = sum(len(items) for _, items in sections)

        s.start(book, "R4-B1", f"Cockpit home, {book}: all {n_items} attention and ECL highlight cards open a drawer with four Plotly charts equal to the chart API")
        s.page = pg
        _open_home(pg, UI, book)
        root = tid("attention-drawer")
        for section, items in sections:
            cards = pg.locator(f'{tid(section)} {tid("attention-card")}')
            s.check(f"{section}: the feed's {len(items)} cards are on the page", cards.count() == len(items), len(items), cards.count())
            for it in items:
                label = f"{it['family']} / {it['segment']}"
                cards.filter(has_text=it["headline"]).first.click()
                pg.wait_for_selector(root, timeout=30_000)
                s.check(f"{label}: drawer title is the card's headline", pg.inner_text(tid("attention-drawer-title")).strip() == it["headline"],
                        it["headline"], pg.inner_text(tid("attention-drawer-title")))
                nums = pg.inner_text(tid("attention-drawer-numbers"))
                s.check(f"{label}: key numbers are the feed's own", all(k["display"] in nums for k in it["key_numbers"]),
                        [k["display"] for k in it["key_numbers"]], nums[:160])
                drawn = _wait_plots(pg, root)
                s.check(f"{label}: trend, against the book, contributors and stage mix are drawn", drawn)
                _no_unavailable(s, pg, label, root)
                if drawn:
                    c = _charts(ck, domain=book, family=it["family"], segment=it["segment"], period=it["reporting_period"],
                                comparison=it["comparison_period"])
                    _figures_equal(s, label, pg.evaluate(READ, root), c)
                    mv = it.get("movement") or {}
                    if isinstance(mv.get("to"), (int, float)):
                        mult = 1 if c["kind"] == "amount" else 100
                        s.check(f"{label}: the trend ends on the card's numbers",
                                _close(c["trend"]["segment"][-1], mv["to"] * mult) and _close(c["trend"]["segment"][-2], mv["from"] * mult),
                                [mv["from"] * mult, mv["to"] * mult], c["trend"]["segment"][-2:])
                    elif it["family"] in ("ecl-total", "ecl-largest"):
                        s.check(f"{label}: the trend ends on the card's figure", f"{round(c['trend']['segment'][-1]):,}" in it["key_numbers"][0]["display"],
                                it["key_numbers"][0]["display"], c["trend"]["segment"][-1])
                pg.click(tid("attention-drawer-close"))
                pg.wait_for_selector(root, state="detached")
            s.check(f"{section}: closing the drawer leaves the Cockpit home", pg.locator(tid("cockpit-v4-home")).count() == 1)
        s.check(f"{book}: every family the feed emits ({', '.join(families)}) has charts",
                all(_charts(ck, domain=book, family=it["family"], segment=it["segment"]).get("trend") for _, items in sections for it in items))

        body = _cockpit(f"/ecl?domain={book}")
        prof, dec = body["profile"], body["decomposition"]
        specs = [("v4-ecl-ead", "ecl-ead", prof["domain_label"], [prof["display_total_ead"]]),
                 ("v4-ecl-ecl", "ecl-total", prof["domain_label"], [prof["display_total_ecl"], prof["display_ecl_movement"]]),
                 ("v4-ecl-coverage", "ecl-coverage", prof["domain_label"], [prof["display_coverage"]])]
        specs += [(f"v4-ecl-stage-{st['stage']}", "ecl-stage", str(st["stage"]), [st["display_ead"], st["display_ecl"], st["display_ecl_movement"]])
                  for st in prof["stages"]]
        specs += [(f"v4-ecl-component-{cp['component_id']}", "ecl-component", cp["component_id"], [cp["display_amount"], dec["display_movement"]])
                  for cp in dec["components"]]
        s.start(book, "R4-B1", f"ECL panel, {book}: all {len(specs)} cards (EAD, ECL, coverage, stages, components) open a drawer with four charts equal to the chart API")
        s.page = pg
        _open_home(pg, UI, book)
        root = tid("ecl-card-drawer")
        for n, (testid, family, segment, displays) in enumerate(specs):
            label = f"{testid}"
            el = pg.locator(tid(testid))
            s.check(f"{label}: is a card that opens a drawer", el.get_attribute("role") == "button", "button", el.get_attribute("role"))
            if n == 1:
                el.focus()
                pg.keyboard.press("Enter")
            else:
                el.click()
            pg.wait_for_selector(root, timeout=30_000)
            nums = pg.inner_text(tid("ecl-card-drawer-numbers"))
            s.check(f"{label}: key numbers are the panel's own", all(d in nums for d in displays), displays, nums[:160])
            drawn = _wait_plots(pg, root)
            s.check(f"{label}: trend, against the book, contributors and stage mix are drawn", drawn)
            _no_unavailable(s, pg, label, root)
            if drawn:
                c = _charts(ck, domain=book, family=family, segment=segment, period=prof["reporting_period"],
                            comparison=prof["comparison_period"])
                _figures_equal(s, label, pg.evaluate(READ, root), c)
                t = c["trend"]["segment"]
                if family == "ecl-ead":
                    s.check(f"{label}: the trend ends on the panel's EAD", _close(t[-1], prof["total_ead"]), prof["total_ead"], t[-1])
                elif family == "ecl-total":
                    s.check(f"{label}: the trend ends on the panel's ECL and its movement",
                            _close(t[-1], prof["total_ecl"]) and _close(t[-1] - t[-2], prof["ecl_movement"]), prof["total_ecl"], t[-1])
                elif family == "ecl-coverage":
                    s.check(f"{label}: the trend ends on the panel's coverage", _close(t[-1], 100 * prof["coverage"]), 100 * prof["coverage"], t[-1])
                elif family == "ecl-stage":
                    st = next(x for x in prof["stages"] if str(x["stage"]) == segment)
                    s.check(f"{label}: the trend ends on the stage's ECL and its movement",
                            _close(t[-1], st["ecl"]) and _close(t[-1] - t[-2], st["ecl_movement"], 1e-5), [st["ecl"], st["ecl_movement"]], t[-2:])
                else:
                    cp = next(x for x in dec["components"] if x["component_id"] == segment)
                    s.check(f"{label}: the trend ends on the component's amount", _close(t[-1], cp["amount"], 1e-5), cp["amount"], t[-1])
            if n % 2:
                pg.keyboard.press("Escape")
            else:
                pg.click(tid("ecl-card-drawer-close"))
            pg.wait_for_selector(root, state="detached")
        s.check("closing (button or Escape) returns to the Cockpit home", pg.locator(tid("cockpit-v4-home")).count() == 1)

        s.start(book, "R4-G1", f"Cockpit home, {book}: no loose provenance or runtime text, explanations behind (i)")
        s.page = pg
        _open_home(pg, UI, book)
        hits = known_in(pg.evaluate(SCREEN_TEXT))
        s.check("none of the known loose-text phrases on the home", not hits, "none", hits[:2])
        for gone in ("attention-footnote", "v4-not-in-runtime", "v4-ecl-reconciliation"):
            s.check(f"{gone} is not on the page", pg.locator(tid(gone)).count() == 0)
        s.check("the header does not describe the runtime", "dashboard service" not in pg.inner_text("header") if pg.locator("header").count() else True)
        pg.locator(f'{tid("v4-ecl-panel")} button[aria-expanded]').first.click()
        pg.wait_for_selector(f'{tid("v4-ecl-panel")} [role="dialog"]')
        s.check("the ECL panel's method is one click away, behind (i)",
                "movement" in pg.inner_text(f'{tid("v4-ecl-panel")} [role="dialog"]').lower())
        pg.keyboard.press("Escape")
        pg.locator(f'{tid("segments-requiring-attention")} button[aria-expanded]').first.click()
        pg.wait_for_selector(f'{tid("segments-requiring-attention")} [role="dialog"]')
        s.check("the attention page's basis is behind (i)",
                "release" in pg.inner_text(f'{tid("segments-requiring-attention")} [role="dialog"]').lower())
        pg.keyboard.press("Escape")
        first = feed["segments_requiring_attention"][0]
        pg.locator(f'{tid("segments-requiring-attention")} {tid("attention-card")}').filter(has_text=first["headline"]).first.click()
        pg.wait_for_selector(tid("attention-drawer"))
        _wait_plots(pg, tid("attention-drawer"))
        hits = known_in(pg.evaluate(SCREEN_TEXT))
        s.check("the open drawer has none of the known phrases", not hits, "none", hits[:2])
        s.check("the drawer's notes are behind (i), not inline",
                pg.locator(tid("attention-drawer-drilldown")).count() == 0 and pg.locator(tid("attention-investigate-note")).count() == 0)
        s.check("Investigate further is the drawer's one primary action", pg.locator(tid("attention-investigate")).count() == 1)
        pg.keyboard.press("Escape")
        pg.wait_for_selector(tid("attention-drawer"), state="detached")
        s.finish()
    s.page = page
    ctx.close()
