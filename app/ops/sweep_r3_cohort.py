"""UAT sweep, PLAN_R3 S3-5: the What-If thread header and the Early Warning cohort dashboard.

Called from ops/uat_sweep.py as `cohort_steps(s, page, UI, wait_url)` (`--only cohort`), in the style of
ops/uat_sweep_core.py. On both books:

  1. Early Warning: open a sector or product, open its warned list and Export it to What-If; the thread opens.
  2. The header is the cohort dashboard: every chart drawn (`data-rendered="true"`), every card equal to the
     API (`GET /cohort/{id}/summary`), and the cohort reconciles to the Early Warning list it came from
     (count and EAD, from the Early Warning API).
  3. EAD by rating on the global order (corporate) or the book's band order (retail), on the API and on the
     drawn chart's axis.
  4. The top-20 table: 20 rows (or every owner of a smaller cohort), sorted by EAD, equal to the API.
  5. A borrower opens Borrower 360 (book, customer, period, the Profile tab) and browser Back returns to the thread.
  6. A scenario runs on the cohort; Save, Share and Add to report work on the thread.
  7. A normal What-If thread (typed on the What-If home) opens with the header for its scope.

Every step ends, as the sweep's own do, with no console error, no page error and no failed request, and the
label rule (no "Synthetic", no "Demo") on the screen, in the data and in the files.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

import core_login
from backend.v5common import ratings  # noqa: E402  (ops/uat_sweep.py puts the repo on the path)

EWS = "http://127.0.0.1:8501/api/v1/ews"
WHATIF = "http://127.0.0.1:8503/api/v1/whatif"
#: The list exported from Early Warning on each book: a sector (corporate) or a product (retail).
SEGMENT = {"corporate": "Construction", "retail": "Personal Finance"}
CHARTS = ("stage-donut", "rating", "split", "reasons", "bands")
CARDS = {"owners": "owners", "exposures": "exposures", "ead": "ead", "ecl": "ecl", "coverage": "coverage_pct",
         "stage2": "stage2_ead_pct", "stage3": "stage3_ead_pct", "ews-score": "ews_avg_score",
         "warned": "ews_warned_owners", "warned-ead": "ews_warned_ead"}


# ------------------------------------------------------------ helpers (the UI's own formatters, as in uat_sweep.py)

def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def txt(page, t: str) -> str:
    return page.locator(tid(t)).first.inner_text()


def _locale(x: float, d: int) -> str:
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{q:,.{d}f}"


def count(v) -> str:
    return "—" if v is None else _locale(float(v), 0)


def sar(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v == 0:
        return "SAR 0"
    a = abs(v)
    scaled, suffix = (v / 1000, "bn") if a >= 1000 else (v, "m") if a >= 1 else (v * 1000, "k") if a >= 0.001 else (v * 1e6, "")
    d = 0 if abs(scaled) >= 100 else 1 if abs(scaled) >= 10 else 2
    return f"SAR {_locale(scaled, d)}{suffix}"


def url_params(page) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def close(a: float, b: float, rel: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(a)), abs(float(b)))


def cohort_steps(s, page, UI: str, wait_url: Callable[..., Any]) -> None:
    cookie = core_login.login("anne")["cookie"]

    def get(url: str, **params) -> Any:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        req = urllib.request.Request(url + ("?" + q if q else ""), headers={"Cookie": f"cp_session={cookie}"})
        with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 - loopback
            return json.loads(r.read())

    def thread_id() -> str:
        return page.url.rstrip("/").split("/what-if/thread/")[1].split("?")[0].split("#")[0]

    def drawn(prefix: str) -> None:
        """Every chart of the header drawn by Plotly; each a figure with data."""
        for c in CHARTS:
            sel = tid(f"{prefix}-{c}")
            if c == "reasons" and page.locator(sel).count() == 0:
                continue
            page.wait_for_selector(f'{sel}[data-rendered="true"]', timeout=60_000)
            traces = page.evaluate("(sel) => (document.querySelector(sel)?.data || []).length", sel)
            s.check(f"chart {c} drawn with data", traces >= 1, ">= 1 trace", traces)
        png = page.evaluate("""(sel) => [...document.querySelectorAll(sel + ' .modebar-btn')]
                                  .some(b => (b.getAttribute('data-title') || '').toLowerCase().includes('png'))""",
                            tid(f"{prefix}-stage-donut"))
        s.check("charts offer PNG download (mode bar)", png, True, png)

    def cards_equal(prefix: str, want: dict) -> None:
        c = want["cards"]
        for key, field in CARDS.items():
            el = page.locator(tid(f"{prefix}-kpi-{key}")).first
            raw = el.get_attribute("data-value")
            s.check(f"card {key} equals the API", raw is not None and close(float(raw), c[field]), c[field], raw)
        for key, fmt in (("owners", count), ("exposures", count), ("ead", sar), ("ecl", sar), ("warned-ead", sar)):
            field = CARDS[key]
            s.check(f"card {key} printed as the API", txt(page, f"{prefix}-kpi-{key}") == fmt(c[field]), fmt(c[field]),
                    txt(page, f"{prefix}-kpi-{key}"))

    def rating_axis(prefix: str, want: dict, book: str) -> None:
        order = want["grades"]["order"]
        if book == "corporate":
            s.check("API rating order is the global order", order == ratings.ordered(order), ratings.ordered(order), order)
        else:
            s.check("API band order is the book's (A best)", order == sorted(order), sorted(order), order)
        axis = page.evaluate("(sel) => { const g = document.querySelector(sel); return g && g.layout ? g.layout.xaxis.categoryarray : null; }",
                             tid(f"{prefix}-rating"))
        xs = page.evaluate("(sel) => { const g = document.querySelector(sel); return g && g.data ? g.data[0].x : null; }",
                           tid(f"{prefix}-rating"))
        s.check("drawn rating axis in that order", axis == order and xs == order, order, axis)
        s.check("axis titled with words", page.evaluate(
            "(sel) => document.querySelector(sel).layout.xaxis.title.text", tid(f"{prefix}-rating")) == want["grades"]["label"],
            want["grades"]["label"])

    # ------------------------------------------------------------ 1-5. Early Warning -> What-If, both books
    for book in ("corporate", "retail"):
        seg = SEGMENT[book]
        s.start(book, "S3-5", f"Early Warning {seg}: Export the warned list to What-If; the cohort thread opens")
        page.goto(UI + f"/early-warning?domain={book}", wait_until="domcontentloaded")
        page.wait_for_selector(tid("ews-level-portfolio"), timeout=90_000)
        page.wait_for_load_state("networkidle")
        page.click(tid(f"ews-open-{seg}"))
        page.wait_for_selector(tid("ews-level-segment"), timeout=60_000)
        page.click(tid("ews-open-warned"))
        page.wait_for_selector(tid("ews-list-total"), timeout=60_000)
        page.wait_for_load_state("networkidle")
        ews_url = page.url
        listed = get(f"{EWS}/customers", domain=book, segment=seg, cohort="warned", limit=1)
        page.click(tid("ews-export-list"))
        wait_url(page, r".*/what-if/thread/.*")
        page.wait_for_selector(f'{tid("whatif-header")}[data-kind="cohort"]', timeout=120_000)
        page.wait_for_selector(tid("whatif-cohort"), timeout=120_000)
        thread_url = page.url
        th = get(f"{WHATIF}/threads/{thread_id()}")
        s.check("the thread is a cohort thread", bool(th["cohort_id"]), "ews-cohort-…", th["cohort_id"])
        want = get(f"{WHATIF}/cohort/{th['cohort_id']}/summary")
        head = get(f"{WHATIF}/threads/{thread_id()}/summary")
        s.check("thread header = cohort summary", head["cards"] == want["cards"] and head["kind"] == "cohort")

        s.start(book, "S3-5", "Cohort dashboard: every chart drawn; cards equal the API; reconciles to Early Warning")
        drawn("whatif-cohort")
        cards_equal("whatif-cohort", want)
        c = want["cards"]
        s.check("customers equal the Early Warning list", c["owners"] == listed["total"], listed["total"], c["owners"])
        s.check("EAD equals the Early Warning list", close(c["ead"], listed["total_exposure"], 1e-9),
                listed["total_exposure"], c["ead"])
        s.check("API reconciliation passes", want["reconciliation"]["matches"], True, want["reconciliation"]["checks"])
        s.check("reconciliation shown", page.get_attribute(tid("whatif-cohort-reconciliation"), "data-matches") == "true"
                and page.get_attribute(tid("whatif-cohort-reconciliation"), "data-membership-verified") == "true")
        s.check("the turn's cohort card agrees", txt(page, "whatif-customers") == count(listed["total"])
                and txt(page, "whatif-ead") == sar(listed["total_exposure"]),
                (count(listed["total"]), sar(listed["total_exposure"])), (txt(page, "whatif-customers"), txt(page, "whatif-ead")))
        bands = page.evaluate("(sel) => document.querySelector(sel).data[0].x", tid("whatif-cohort-bands"))
        s.check("bands in band order, worst first", bands == [b["label"] for b in want["bands"]],
                [b["label"] for b in want["bands"]], bands)
        s.check("warned list: only moderate or worse", all(b["band"] in ("critical", "high", "moderate") for b in want["bands"] if b["owners"]))
        reasons = page.evaluate("(sel) => document.querySelector(sel).data.length", tid("whatif-cohort-reasons"))
        s.check("reasons: count and EAD panels", reasons == 2, 2, reasons)

        s.start(book, "S3-5", "EAD by rating in the global order; the sector or product split")
        rating_axis("whatif-cohort", want, book)
        split = page.evaluate("(sel) => document.querySelector(sel).data[0].y", tid("whatif-cohort-split"))
        s.check("split equals the API (largest first)", list(reversed(split)) == [r["name"] for r in want["split"]["rows"]],
                [r["name"] for r in want["split"]["rows"]], split)

        s.start(book, "S3-5", "Top 20 by EAD: rows, order, figures")
        rows = page.locator(tid("whatif-cohort-top20-row"))
        n = rows.count()
        s.check("20 rows (or every owner)", n == min(20, c["owners"]) == len(want["top"]["rows"]), min(20, c["owners"]), n)
        eads = [float(rows.nth(i).get_attribute("data-ead")) for i in range(n)]
        s.check("sorted by EAD, largest first", eads == sorted(eads, reverse=True), "descending", eads[:5])
        owners = [rows.nth(i).get_attribute("data-owner") for i in range(n)]
        s.check("the API's owners, in its order", owners == [r["owner_id"] for r in want["top"]["rows"]],
                [r["owner_id"] for r in want["top"]["rows"]][:5], owners[:5])
        shown = page.locator(tid("whatif-cohort-top20-ead")).all_inner_texts()
        s.check("EAD printed as the API", shown == [sar(r["ead"]) for r in want["top"]["rows"]],
                [sar(r["ead"]) for r in want["top"]["rows"]][:3], shown[:3])

        s.start(book, "S3-5", "Top 20: a borrower opens Borrower 360 (Profile); browser Back returns to the thread")
        first = want["top"]["rows"][0]
        link = page.locator(tid(f"whatif-cohort-b360-{first['owner_id']}"))
        s.check("link carries book, customer, period and tab", link.get_attribute("href") == first["href"]
                and f"customer_id={first['owner_id']}" in first["href"] and "tab=profile" in first["href"], first["href"],
                link.get_attribute("href"))
        link.click()
        wait_url(page, r".*/borrower-360\?.*")
        page.wait_for_selector(f'[data-testid="b360-customer"][data-customer="{first["owner_id"]}"]', timeout=90_000)
        page.wait_for_load_state("networkidle")
        q = url_params(page)
        s.check("Borrower 360 on the book, customer, period and Profile",
                (q.get("domain"), q.get("customer_id"), q.get("period"), q.get("tab")) == (book, first["owner_id"], want["period"], "profile"),
                (book, first["owner_id"], want["period"], "profile"), q)
        s.check("Borrower 360 shows that customer", txt(page, "b360-id") == first["owner_id"], first["owner_id"], txt(page, "b360-id"))
        page.go_back()
        wait_url(page, re.escape(thread_url.split("?")[0]) + r".*")
        page.wait_for_selector(f'{tid("whatif-header")}[data-kind="cohort"]', timeout=90_000)
        page.wait_for_selector(f'{tid("whatif-cohort-stage-donut")}[data-rendered="true"]', timeout=60_000)
        s.check("Back on the same thread", page.url.split("?")[0] == thread_url.split("?")[0], thread_url, page.url)

        s.start(book, "S3-5", "A scenario on the cohort; Save, Share and Add to report on the thread")
        tid_ = thread_id()
        n_turns = page.locator(tid("whatif-turn")).count()
        page.fill(tid("whatif-composer"), "increase PD by 20% using the delta method")
        page.click(tid("whatif-send"))
        page.wait_for_function(
            "(n) => document.querySelectorAll('[data-testid=\"whatif-turn\"]').length > n"
            " && !document.querySelector('[data-testid=\"whatif-live-turn\"]')", arg=n_turns, timeout=180_000)
        s.check("a proposal first; nothing ran", page.locator(tid("whatif-proposal")).count() >= 1)
        n_turns = page.locator(tid("whatif-turn")).count()
        page.click(tid("whatif-execute"))                 # PLAN_R4 A1: a scenario runs only on Execute
        page.wait_for_function(
            "(n) => document.querySelectorAll('[data-testid=\"whatif-turn\"]').length > n"
            " && !document.querySelector('[data-testid=\"whatif-live-turn\"]')", arg=n_turns, timeout=180_000)
        page.wait_for_load_state("networkidle")
        s.check("the result ran on the cohort", "cohort" in page.locator(tid("whatif-result")).last.inner_text().lower())
        s.check("header unchanged by the scenario (still the cohort)",
                page.get_attribute(tid("whatif-header"), "data-kind") == "cohort")
        page.once("dialog", lambda d: d.accept(f"Cohort {book} PD +20%"))
        page.click(tid("whatif-save"))
        page.wait_for_selector(tid("whatif-notice"), timeout=60_000)
        s.check("saved to the repository", "Saved" in txt(page, "whatif-notice"), "Saved…", txt(page, "whatif-notice"))
        page.click(tid(f"whatif-add-pack-{tid_}"))       # What-If's own pack; "Add to report" is Playbook's dialog (S1)
        page.wait_for_timeout(1500)
        pack = get(f"{WHATIF}/reports")
        s.check("added to the report pack", any(i["ref"] == tid_ for i in pack["items"]), tid_, [i["ref"] for i in pack["items"]][:5])
        page.click(tid(f"whatif-share-{tid_}"))
        page.wait_for_selector(tid("whatif-share-dialog"), timeout=30_000)
        s.check("share dialog lists recipients", page.locator('[data-testid^="whatif-share-user-"]').count() >= 1)
        page.click(tid("whatif-share-close"))

        s.start(book, "S3-5", "Cohort thread: browser Back returns to the Early Warning list it came from")
        page.go_back()
        wait_url(page, r".*/early-warning.*")
        page.wait_for_selector(tid("ews-list-total"), timeout=90_000)
        s.check("browser Back returns to the Early Warning list", url_params(page).get("domain") == book, ews_url, page.url)

    # ------------------------------------------------------------ 7. a normal thread has the header too
    for book in ("corporate", "retail"):
        meta = get(f"{WHATIF}/meta", domain=book)
        seg = "Construction" if book == "corporate" else meta["segments"][0]
        s.start(book, "S3-5", f"A normal What-If thread ({seg}) opens with the header for its scope")
        page.goto(UI + f"/what-if?domain={book}", wait_until="domcontentloaded")
        page.wait_for_selector(tid("whatif-library"), timeout=90_000)
        page.wait_for_load_state("networkidle")
        page.fill(tid("whatif-ask"), f"increase PD by 30% for {seg} using delta")
        page.click(tid("whatif-ask-send"))
        wait_url(page, r".*/what-if/thread/.*")
        page.wait_for_function(
            "() => document.querySelectorAll('[data-testid=\"whatif-turn\"]').length >= 1"
            " && !document.querySelector('[data-testid=\"whatif-live-turn\"]')", timeout=180_000)
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(f'{tid("whatif-header")}[data-kind="scope"]', timeout=60_000)
        want = get(f"{WHATIF}/threads/{thread_id()}/summary")
        s.check("header follows the scenario's scope", want["kind"] == "scope" and seg in want["scope_label"], seg, want["scope_label"])
        s.check("header title names the scope", seg in txt(page, "whatif-header-title"), seg, txt(page, "whatif-header-title"))
        drawn("whatif-header")
        cards_equal("whatif-header", want)
        rating_axis("whatif-header", want, book)
        page.click(tid("whatif-header-toggle"))
        s.check("header folds", page.locator(tid("whatif-header-cards")).count() == 0)
        page.click(tid("whatif-header-toggle"))
        page.wait_for_selector(f'{tid("whatif-header-rating")}[data-rendered="true"]', timeout=60_000)
        s.check("and unfolds", page.locator(tid("whatif-header-cards")).count() == 1)
        n_turns = page.locator(tid("whatif-turn")).count()
        page.click(tid("whatif-execute"))                 # PLAN_R4 A1: the proposal runs on Execute
        page.wait_for_function(
            "(n) => document.querySelectorAll('[data-testid=\"whatif-turn\"]').length > n"
            " && !document.querySelector('[data-testid=\"whatif-live-turn\"]')", arg=n_turns, timeout=180_000)
        page.wait_for_load_state("networkidle")
        s.check("the header still follows the scope after Execute",
                page.get_attribute(tid("whatif-header"), "data-kind") == "scope")
        s.check("the result blocks are still below", page.locator(tid("whatif-result")).count() >= 1
                and page.locator('[data-testid^="whatif-waterfall-chart-"][data-rendered="true"]').count() >= 1)
        page.click(tid("whatif-back"))
        wait_url(page, r".*/what-if\?.*")
        page.wait_for_selector(tid("whatif-library"), timeout=60_000)
        s.check("← What-If returns home", "/what-if/thread/" not in page.url, "/what-if", page.url)


__all__ = ["cohort_steps"]
