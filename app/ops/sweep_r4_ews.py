"""UAT sweep, PLAN_R4 (part "r4-ews"): B4, Early Warning card levels and drill journeys.

Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep. On both books:
  * every level of the View-by toggle: the toggle selects it and the address carries it; every KPI tile and every
    card figure equals the levels API; every card draws its sparklines and opens its Plotly chart; the trend and
    comparison charts are drawn; the cards add up to the book (exposure, exposures, and customers where a customer
    sits in one card) and the level's headline is the book total; Sector / Product equal the original drill;
  * the four drill journeys end to end (Corporate Region > Branch > Sector > Borrower, Rating grade > Sector >
    Borrower; Retail Region > Branch > Product > Customer, Score band > Product > Customer): breadcrumbs at every
    step, the Back button and the browser Back at every step, Export to What-If at every level (the frozen cohort
    carries the full drill filter and its customers equal the level's warned), the list equals its card, the
    customer opens and Back returns to the list.
Console errors, failed requests and banned labels ("Synthetic", "Demo") are checked by the Sweep at every step.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from typing import Any, Callable


def _u():
    """The running uat_sweep module (it is __main__ when the sweep runs), for its helpers and formats."""
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "KPI_TILES"):
        return main
    import uat_sweep  # noqa: PLC0415
    return uat_sweep


LEVELS = {
    "corporate": [("sector", "Sector"), ("region", "Region"), ("branch", "Branch"), ("rating", "Rating grade"),
                  ("rm", "RM / business unit"), ("product", "Product")],
    "retail": [("product", "Product"), ("region", "Region"), ("branch", "Branch"), ("band", "Score band"),
               ("salaried", "Salaried / Non-Salaried"), ("vintage", "Vintage")],
}
DEFAULT = {"corporate": "sector", "retail": "product"}
OWNER_DIMS = {"sector", "region", "branch", "rating", "bu", "rm", "band", "salaried"}


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def view_api(U, book: str, level: str, dims: dict | None = None, period: str = "") -> dict:
    q = {"domain": book, "level": level, "period": period}
    if dims:
        q["dims"] = json.dumps(dims)
    return U.api("/levels/view", **q)


def customers_api(U, book: str, dims: dict, cohort: str = "warned") -> dict:
    return U.api("/customers", domain=book, cohort=cohort, dims=json.dumps(dims), limit=25)


def qparams(page) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def settle_dim(page, depth: int) -> None:
    page.wait_for_selector(tid(f"ews-dim-level-{depth}"), timeout=120_000)
    page.wait_for_selector(tid("ews-kpis"), timeout=60_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)


def settle_list(page) -> None:
    page.wait_for_selector(tid("ews-list-total"), timeout=120_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)


def plotted(page, testid: str) -> bool:
    try:
        page.wait_for_selector(f'{tid(testid)}[data-rendered="true"], {tid(testid)} [data-rendered="true"]',
                               timeout=30_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def check_view(s, page, U, book: str, v: dict, book_total: dict | None) -> None:
    """Tiles, crumbs, every card figure, sparklines, charts and the reconciliation, against the API."""
    h, m, L = v["headline"], v["movement"], v["labels"]
    for testid, want in U.KPI_TILES:
        shown = U.txt(page, testid)
        missing = [p for p in want(h, m, L, v["prior_period"]) if p not in shown]
        s.check(f"{testid} equals the API", not missing, "all figures", f"missing {missing}")
    crumbs = U.txt(page, "ews-breadcrumbs")
    s.check("breadcrumbs", all(b["label"] in crumbs for b in v["breadcrumbs"]),
            " > ".join(b["label"] for b in v["breadcrumbs"]), crumbs.replace("\n", " "))
    summary = U.txt(page, "ews-level-summary")
    s.check("open-warned carries the warned count", f"Open the {U.count(h['customers_warned'])} warned" in summary,
            U.count(h["customers_warned"]), summary[:120])
    cards = v["children"]
    shown_cards = page.locator('[data-testid^="ews-card-"]').count()
    s.check("one card per value of the level", shown_cards == len(cards), len(cards), shown_cards)
    no_spark = []
    for c in cards:
        body = page.locator(tid(f"ews-card-{c['key']}")).first.inner_text()
        want = [c["label"], f"{U.pct(c['exposure_severe_pct'])} high/critical",
                f"{U.signed(c['movement']['customers_warned'])} warned", U.count(c["customers"]),
                U.count(c["customers_warned"]), U.count(c["high_or_critical"]), U.count(c["current_bad"]),
                U.count(c["forward_risk"]), U.sar(c["exposure"]), U.sar(c["exposure_severe"]),
                U.pct(c["exposure_warned_pct"]), U.pct(c["odr_pct"], 2), U.pct(c["dpd_30_plus_pct"])]
        missing = [w for w in want if w not in body]
        s.check(f"card {c['key']}: every figure equals the API", not missing, "all", "missing " + "; ".join(missing))
        series = {"warned": "customers_warned", "odr": "odr_pct", "severe": "exposure_severe"}
        for k in ("warned", "odr", "severe"):
            if not any(p.get(series[k]) is not None for p in c["trend"]):
                continue  # nothing to draw: no point has a value (e.g. no default-entry eligibles)
            if page.locator(f'{tid(f"ews-trends-{c["key"]}-{k}")} svg').count() == 0:
                no_spark.append(f"{c['key']}:{k}")
    s.check("every card draws its three sparklines", not no_spark, "drawn", no_spark[:4])
    s.check("trend chart drawn (Plotly)", plotted(page, "ews-trend-chart"))
    if len(cards) > 1:
        s.check("comparison chart drawn (Plotly)", plotted(page, "ews-compare-chart"))
    # PLAN_R5 P4: "Borrowers by rating" only at View by = Rating (its top level); every other level only its own charts.
    rating_level = v.get("level") == "rating" and v.get("next_dim") == "rating"
    if book == "corporate" and rating_level and v.get("rating_mix"):
        s.check("P4: Borrowers by rating drawn at the rating level", plotted(page, "ews-rating-chart"))
    else:
        s.check("P4: no Borrowers by rating outside the rating level", page.locator(tid("ews-ratings")).count() == 0,
                0, page.locator(tid("ews-ratings")).count())
    if v.get("reconcile"):
        r = v["reconcile"]
        s.check("cards add up: exposure", abs(r["exposure"] - h["exposure"]) < 1e-6, h["exposure"], r["exposure"])
        s.check("cards add up: exposures", r["facilities"] == h["facilities"], h["facilities"], r["facilities"])
        if v["next_dim"] in OWNER_DIMS:
            s.check(f"cards add up: {L['owners']}", r["customers"] == h["customers"], h["customers"], r["customers"])
        else:
            s.check(f"cards: {L['owners']} counted in each (overlap)", r["customers"] >= h["customers"],
                    f">= {h['customers']}", r["customers"])
    if book_total is not None:
        bh = book_total["headline"]
        s.check("headline is the book total", (h["customers"], h["facilities"]) == (bh["customers"], bh["facilities"])
                and abs(h["exposure"] - bh["exposure"]) < 1e-6, (bh["customers"], bh["facilities"], bh["exposure"]),
                (h["customers"], h["facilities"], h["exposure"]))


def card_chart(s, page, key: str) -> None:
    page.click(tid(f"ews-trend-open-{key}"))
    ok = True
    try:
        page.wait_for_selector(f'{tid("ews-trend-dialog")} [data-rendered="true"]', timeout=30_000)
    except Exception:  # noqa: BLE001
        ok = False
    s.check(f"card {key}: sparklines open the Plotly chart", ok)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    s.check("Escape closes the chart", page.locator(tid("ews-trend-dialog")).count() == 0)


def export_whatif(s, page, U, testid: str, dims: dict, warned: int, settle: Callable[[], None]) -> None:
    """Export to What-If: the frozen cohort carries the drill filter; browser Back returns to the same view."""
    before = page.url
    # R16 M2: a card's Analyse opens the segment analysis; "Stress this cohort" inside it is the export.
    if testid.startswith("ews-export-"):
        page.click(tid(testid.replace("ews-export-", "ews-analyse-", 1)))
    with page.expect_response(lambda r: "/api/v1/ews/export" in r.url and r.request.method == "POST",
                              timeout=120_000) as resp:
        page.click(tid(testid))
    try:
        obj = resp.value.json()
    except Exception:  # noqa: BLE001
        obj = None
    U.wait_url(page, r".*/what-if/thread/.*", timeout=120_000)
    page.wait_for_selector(tid("whatif-cohort"), timeout=120_000)
    shown = U.txt(page, "whatif-customers")
    s.check(f"{testid}: What-If customers equal the level's warned", shown == U.count(warned), U.count(warned), shown)
    s.check(f"{testid}: the cohort carries the full drill filter", obj is not None and
            (obj.get("request", {}).get("scope", {}).get("dims") or {}) == dims, dims,
            (obj or {}).get("request", {}).get("scope"))
    # The What-If hand-off may add one or two history entries (the cohort link, then its thread).
    for _ in range(3):
        page.go_back()
        for _ in range(40):  # a client-side Back fires no load event: poll the address
            if "/early-warning" in page.url:
                break
            page.wait_for_timeout(250)
        if "/early-warning" in page.url:
            break
    settle()
    s.check(f"{testid}: browser Back returns to the same view", _same(page.url, before), before, page.url)


def _same(a: str, b: str) -> bool:
    pa = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(a).query))
    pb = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(b).query))
    return pa == pb


def level_steps(s, page, U, UI: str, book: str) -> None:
    total = U.api("/level", domain=book)
    page.goto(f"{UI}/early-warning?domain={book}", timeout=180_000)
    page.wait_for_selector(tid("ews-level-toggle"), timeout=180_000)
    for key, label in LEVELS[book]:
        s.start(book, "B4", f"View by {label}: cards, sparklines, figures, totals")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.click(tid(f"ews-lv-{key}"))
        if key == DEFAULT[book]:
            page.wait_for_selector(tid("ews-level-portfolio"), timeout=120_000)
            page.wait_for_load_state("networkidle")
            s.check("default level is the original drill", "lv" not in qparams(page), "no lv", page.url)
            v = view_api(U, book, key)
            orig = {c["key"]: c for c in total["children"]}
            same = all(orig.get(c["key"], {}).get("customers") == c["customers"]
                       and orig.get(c["key"], {}).get("customers_warned") == c["customers_warned"]
                       and abs(orig.get(c["key"], {}).get("exposure", -1) - c["exposure"]) < 1e-6 for c in v["children"])
            s.check(f"{label} level API equals the original {label.lower()} cards", same and len(orig) == len(v["children"]),
                    len(orig), len(v["children"]))
            shown = page.locator('[data-testid^="ews-card-"]').count()
            s.check("original cards shown", shown == len(total["children"]) + len(total.get("classifications", [])),
                    len(total["children"]), shown)
            s.check("trend chart drawn (Plotly)", plotted(page, "ews-trend-chart"))
        else:
            settle_dim(page, 0)
            s.check("toggle selected", page.get_attribute(tid(f"ews-lv-{key}"), "aria-selected") == "true")
            s.check("address carries the level", qparams(page).get("lv") == key, key, page.url)
            v = view_api(U, book, key)
            check_view(s, page, U, book, v, total)
            if key == "rating":
                keys = [c["key"] for c in v["children"]]
                from backend.v5common import ratings  # noqa: PLC0415
                s.check("rating grades in the global order", keys == ratings.ordered(keys), ratings.ordered(keys), keys)
                order = page.eval_on_selector_all('[data-testid^="ews-card-"]',
                                                  "els => els.map(e => e.getAttribute('data-testid').slice(9))")
                s.check("rating cards shown in the global order", order == keys, keys, order)
                if v.get("rating_mix"):
                    ticks = page.eval_on_selector(tid("ews-rating-chart"),
                                                  "el => [...el.querySelectorAll('.xtick text')].map(t => t.textContent)")
                    want = [r["rating"] for r in v["rating_mix"]]
                    s.check("P4: Borrowers by rating axis in the global order", ticks == want, want, ticks)
            card_chart(s, page, v["children"][0]["key"])


JOURNEYS = [
    ("corporate", "region", "Region > Branch > Sector > Borrower", {"region": "Riyadh"}),
    ("corporate", "rating", "Rating grade > Sector > Borrower", {"rating": "BB"}),
    ("retail", "region", "Region > Branch > Product > Customer", {"region": "Riyadh"}),
    ("retail", "band", "Score band > Product > Customer", {"band": "D"}),
]


def journey(s, page, U, UI: str, book: str, level: str, title: str, first: dict) -> None:
    v0 = view_api(U, book, level)
    s.start(book, "B4", f"Journey {title}: top level, Export to What-If")
    page.goto(f"{UI}/early-warning?domain={book}&lv={level}", timeout=180_000)
    settle_dim(page, 0)
    s.check("no Back at the top of the journey", page.locator(tid("ews-level-back")).count() == 0)
    export_whatif(s, page, U, "ews-export-level", {}, v0["headline"]["customers_warned"], lambda: settle_dim(page, 0))

    journey_dims = v0["journey"]
    dims: dict[str, str] = {}
    path_urls = [page.url]
    v = v0
    for depth, dim in enumerate(journey_dims):
        # The value to open: the given first step, else the card with the most warned.
        cards = v["children"]
        value = first.get(dim) or max(cards, key=lambda c: (c["customers_warned"], c["exposure"]))["key"]
        card = next(c for c in cards if c["key"] == value)
        dims = {**dims, dim: value}
        last = depth == len(journey_dims) - 1
        s.start(book, "B4", f"Journey {title}: open {card['label']} ({'list' if last else dim})")
        # A card's What-If export before opening it (Export to What-If on the card at every level).
        export_whatif(s, page, U, f"ews-export-{value}", dims, card["customers_warned"],
                      (lambda d=depth: settle_dim(page, d)))
        page.click(tid(f"ews-open-{value}"))
        if last:
            settle_list(page)
            p = qparams(page)
            s.check("address carries the full drill filter", all(p.get(f"f_{k}") == v2 for k, v2 in dims.items())
                    and p.get("lv") == level and p.get("cohort") == "warned", dims, page.url)
            lst = customers_api(U, book, dims)
            s.check("list total equals the card's warned", lst["total"] == card["customers_warned"],
                    card["customers_warned"], lst["total"])
            shown = U.txt(page, "ews-list-total")
            s.check("list total on screen", U.count(lst["total"]) in shown, U.count(lst["total"]), shown)
            rows = page.locator('[data-testid^="ews-customer-"]:not([data-testid="ews-customer-list"])').count()
            s.check("list rows shown", rows == min(25, lst["total"]), min(25, lst["total"]), rows)
            crumbs = U.txt(page, "ews-breadcrumbs")
            want = [b["label"] for b in view_api(U, book, level, dims)["breadcrumbs"]]
            s.check("list breadcrumbs carry the whole journey", all(w in crumbs for w in want), want, crumbs)
            break
        settle_dim(page, depth + 1)
        p = qparams(page)
        s.check("address carries the drill filter", all(p.get(f"f_{k}") == v2 for k, v2 in dims.items()), dims, page.url)
        v = view_api(U, book, level, dims)
        check_view(s, page, U, book, v, None)
        s.check("headline equals the card it was opened from",
                (v["headline"]["customers"], v["headline"]["customers_warned"]) == (card["customers"], card["customers_warned"]),
                (card["customers"], card["customers_warned"]), (v["headline"]["customers"], v["headline"]["customers_warned"]))
        s.check("level shows the next step of the journey", v["next_dim"] == journey_dims[depth + 1],
                journey_dims[depth + 1], v["next_dim"])
        s.start(book, "B4", f"Journey {title}: {card['label']} Export to What-If, Back, breadcrumbs")
        export_whatif(s, page, U, "ews-export-level", dims, v["headline"]["customers_warned"],
                      (lambda d=depth: settle_dim(page, d + 1)))
        # The Back button goes one step up (a new history entry); browser Back returns here.
        page.click(tid("ews-level-back"))
        settle_dim(page, depth)
        s.check("Back goes one step up", _same(page.url, path_urls[-1]), path_urls[-1], page.url)
        page.go_back()
        settle_dim(page, depth + 1)
        s.check("browser Back returns to the level", all(qparams(page).get(f"f_{k}") == v2 for k, v2 in dims.items()),
                dims, page.url)
        # Every breadcrumb opens its level; browser Back returns here.
        here = page.url
        for i in range(len(v["breadcrumbs"]) - 1):
            page.click(tid(f"ews-crumb-{i}"))
            settle_dim(page, i)
            s.check(f"breadcrumb {i} opens its level", _same(page.url, path_urls[i]), path_urls[i], page.url)
            page.go_back()
            settle_dim(page, depth + 1)
            s.check(f"browser Back from breadcrumb {i}", _same(page.url, here), here, page.url)
        path_urls.append(page.url)

    # The list: Export to What-If with the full filter, open a customer, Back at every step.
    s.start(book, "B4", f"Journey {title}: list Export to What-If, customer, Back")
    lst = customers_api(U, book, dims)
    export_whatif(s, page, U, "ews-export-list", dims, lst["total"], lambda: settle_list(page))
    first_row = lst["customers"][0]["customer_id"] if lst["customers"] else None
    if first_row:
        page.click(f'{tid("ews-customer-" + first_row)} button >> nth=0')
        page.wait_for_selector(tid("ews-customer-detail"), timeout=120_000)
        page.wait_for_load_state("networkidle")
        crumbs = U.txt(page, "ews-breadcrumbs")
        s.check("customer breadcrumbs end at the customer", first_row in crumbs, first_row, crumbs)
        facts = U.txt(page, "ews-customer-detail")
        s.check("customer opened", first_row in facts, first_row, facts[:80])
        page.click(tid("ews-detail-back"))
        settle_list(page)
        s.check("customer Back returns to the list", "customer" not in qparams(page)
                and all(qparams(page).get(f"f_{k}") == v2 for k, v2 in dims.items()), dims, page.url)
    s.start(book, "B4", f"Journey {title}: list Back returns to the level it was opened from")
    if page.locator(tid("ews-list-back")).count():
        page.click(tid("ews-list-back"))
    depth = len(journey_dims) - 1
    settle_dim(page, depth)
    p = qparams(page)
    s.check("list Back opens the last level of the journey", "cohort" not in p
            and all(p.get(f"f_{k}") == dims[k] for k in journey_dims[:depth]) and f"f_{journey_dims[-1]}" not in p,
            {k: dims[k] for k in journey_dims[:depth]}, page.url)
    # A deep link opens the same view (state lives in the address).
    page.goto(page.url, timeout=180_000)
    settle_dim(page, depth)
    s.check("deep link reopens the same level", U.txt(page, "ews-level-name") == view_api(
        U, book, level, {k: dims[k] for k in journey_dims[:depth]})["name"])


def ews_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    U = _u()
    for book in ("corporate", "retail"):
        level_steps(s, page, U, UI, book)
    for book, level, title, first in JOURNEYS:
        journey(s, page, U, UI, book, level, title, first)
