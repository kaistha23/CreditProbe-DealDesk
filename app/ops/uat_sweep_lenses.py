"""UAT sweep, Lenses (PLAN_R5 Session L, L3): home, ask -> lens with the process trace, KPI row against the API,
8-14 charts, zero untraced figures, no raw numbers, the edit commands in the assistant, the tile menu, Add ratio,
undo / redo / versions, period in the URL, save, share, add to report, export, schedule, Back paths, both books.

Called from ops/uat_sweep.py (`--only lenses`). Every step ends with no console error, no page error and no failed
request (the Sweep's own checks). The lenses this sweep creates are removed at the end, so the library stays as seeded.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any, Callable

import core_login

LE = "http://127.0.0.1:8509/api/v1/lenses"
PB = "http://127.0.0.1:8506/api/v1/playbook/health"
RAW = re.compile(r"(?<![\w.])\d+\.\d{5,}(?![\d])")
LOOSE_SHARE = re.compile(r"(?<![\w.%])0\.\d{3,}(?![\d%])")


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def api(path: str, cookie: str, method: str = "GET", body: Any = None) -> Any:
    req = urllib.request.Request(LE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Cookie": f"cp_session={cookie}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


def raw_numbers(page) -> list[str]:
    """G5: Session T's scan (ops/raw_number_scan.py) on the whole page, thread answers included."""
    import raw_number_scan
    return raw_number_scan.failures(raw_number_scan.scan_page(page))[:5]


def wait_idle(page, timeout: int = 120_000) -> None:
    page.wait_for_selector(f'{tid("lens-assistant")}[data-busy="0"]', timeout=timeout)


def ask(page, text: str) -> None:
    n = page.locator(tid("thread-turn-assistant")).count()
    page.fill(tid("lens-assistant-composer"), text)
    page.click(tid("lens-assistant-send"))
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"thread-turn-assistant\"]').length > {n}", timeout=120_000)
    wait_idle(page)
    page.wait_for_timeout(1500)


def lens_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    cookie = core_login.login("anne")["cookie"]
    made: list[str] = []

    # ---------------------------------------------------------------- 1. home
    s.start("lenses", "L1-1", "Sidebar → Intelligence → Lenses: chat box on top, mine / shared / templates as cards, book toggle")
    page.goto(UI + "/", wait_until="domcontentloaded")
    page.locator('nav[aria-label="Primary"]').get_by_role("link", name="Lenses").click()
    wait_for(page, r".*/lenses$")
    page.wait_for_selector(tid("lenses-templates") + " button", timeout=90_000)
    listing = api("/lenses?book=corporate", cookie)
    s.check("the chat box is on the page", page.locator(tid("lenses-ask")).count() == 1)
    box = page.locator(tid("lenses-ask")).bounding_box()["y"]
    s.check("saved lenses are below the chat box", page.locator(tid("lenses-mine")).bounding_box()["y"] > box)
    s.check("templates shown as cards equal the API's", page.locator(f'{tid("lenses-templates")} button').count() == len(listing["templates"]) >= 6,
            len(listing["templates"]), page.locator(f'{tid("lenses-templates")} button').count())
    s.check("each card has a thumbnail with figures", page.locator(tid("lens-card-thumb")).count() >= len(listing["templates"]))
    s.check("shared with me lists the seeded share", page.locator(f'{tid("lenses-shared")} button').count() >= 1)
    # PLAN_R6 L1: a full home: Featured row, at least 4 of Anne's lenses and 3 shared, cards 3-4 per row
    feat = [page.locator(tid(f"lens-featured-card-{k}")).count() for k in ("cro-portfolio", "stage2-watch", "ews-critical", "concentration-risk")]
    s.check("Featured: CRO portfolio, Stage 2 watch, Early Warning critical names, Concentration risk", feat == [1, 1, 1, 1], [1, 1, 1, 1], feat)
    s.check("Featured is the first row", page.locator(tid("lenses-featured")).bounding_box()["y"] < page.locator(tid("lenses-mine")).bounding_box()["y"])
    s.check("My lenses has 4 or more", page.locator(f'{tid("lenses-mine")} button').count() >= 4, ">= 4", page.locator(f'{tid("lenses-mine")} button').count())
    s.check("Shared with me has 3 or more", page.locator(f'{tid("lenses-shared")} button').count() >= 3, ">= 3", page.locator(f'{tid("lenses-shared")} button').count())
    cards = page.locator(f'{tid("lenses-templates-grid")} > button')
    ys = [round(cards.nth(i).bounding_box()["y"]) for i in range(min(cards.count(), 4))]
    s.check("cards fill the width (3 or more per row)", len(ys) >= 3 and ys[0] == ys[1] == ys[2], "3+ on the first row", ys)
    page.click(tid("lenses-book-retail"))
    wait_for(page, r".*/lenses\?book=retail$")
    page.wait_for_selector(tid("lens-card-retail-cards"), timeout=60_000)
    s.check("Retail shows the retail templates", page.locator(tid("lens-card-retail-cards")).count() == 1)
    page.click(tid("lenses-book-corporate"))
    wait_for(page, r".*/lenses$")
    s.check("no raw numbers on the home (G5)", not raw_numbers(page), "none", raw_numbers(page))
    s.finish()

    # ---------------------------------------------------------------- 2. ask -> a lens
    s.start("lenses", "L1-2", "Ask 'Construction sector dashboard': a lens opens, the process trace runs, KPI row, 8-14 charts, top names, commentary")
    page.wait_for_selector(tid("lenses-ask"))
    page.fill(tid("lenses-ask"), "Construction sector dashboard")
    page.click(tid("lenses-build"))
    wait_for(page, r".*/lenses/lens-[0-9a-f]+$", timeout=120_000)
    lid = page.url.rstrip("/").split("/")[-1]
    made.append(lid)
    page.wait_for_selector(tid("lens-view"), timeout=120_000)
    try:
        page.wait_for_selector(f'{tid("lens-assistant")} {tid("process-trace")}, {tid("lens-assistant")} {tid("v4-process-panel")}', timeout=60_000)
        traced = True
    except Exception:  # noqa: BLE001
        traced = False
    s.check("the process trace shows while it builds or after", traced)
    wait_idle(page)
    page.wait_for_selector(tid("thread-turn-assistant"), timeout=60_000)
    s.check("the build answer settles with its process trace", page.locator(f'{tid("thread-turn-assistant")} {tid("v4-process-panel")}').count() >= 1
            or page.locator(f'{tid("thread-turn-assistant")} {tid("process-trace")}').count() >= 1)
    r = api(f"/lenses/{lid}/render", cookie)
    view = page.locator(tid("lens-view"))
    s.check("8-14 charts", 8 <= int(view.get_attribute("data-charts") or 0) <= 14, "8-14", view.get_attribute("data-charts"))
    s.check("zero untraced figures", view.get_attribute("data-untraced") == "0")
    for k in r["kpis"]:
        shown = page.locator(tid(f"lens-kpi-{k['key']}")).inner_text()
        s.check(f"KPI {k['label']} equals the API ({k['display']})", k["display"] in shown, k["display"], shown[:80])
    s.check("the scope chip names Construction", "Construction" in page.locator(tid("lens-scope")).inner_text())
    s.check("a top-names table", page.locator(tid("lens-top-names")).count() == 1 and page.locator(f'{tid("lens-top-names")} tbody tr').count() >= 10)
    # R13 L (J8): the reading on top replaces the commentary card: a headline and the 2-3 movements that matter
    s.check("an interpretation of 3-5 lines", 3 <= int(page.locator(tid("lens-interpretation")).get_attribute("data-lines") or 0) <= 5)
    s.check("a compact KPI strip of 6-8", 6 <= int(page.locator(tid("lens-kpis")).get_attribute("data-count") or 0) <= 8)
    page.locator(tid("lens-tiles")).scroll_into_view_if_needed()
    page.wait_for_selector(f'{tid("lens-plot")} .main-svg', timeout=60_000)
    s.check("Plotly charts are drawn", page.locator(f'{tid("lens-plot")} .main-svg').count() >= 2)
    s.check("no raw numbers on the lens (G5)", not raw_numbers(page), "none", raw_numbers(page))
    page.locator(tid("lens-kpi-trace-ead")).click()
    s.check("the KPI (i) shows its query", "SELECT" in page.locator(tid("lens-kpi-trace-ead-panel")).inner_text())
    page.locator(tid("lens-kpi-trace-ead")).click()
    # PLAN_R6 L3: every tile's (i) explains it in four plain-word parts before the query
    first_trace = page.locator(f'{tid("lens-tiles")} {tid("lens-trace")}').first
    first_trace.click()
    panel = page.locator(tid("lens-trace-explain")).first
    text = panel.inner_text() if panel.count() else ""
    s.check("the tile (i) explains it (shows, formula, how to read, what to look for)",
            all(w in text.upper() for w in ("WHAT IT SHOWS", "HOW IT IS CALCULATED", "HOW TO READ IT", "WHAT TO LOOK FOR")), "four parts", text[:120])
    first_trace.click()
    s.check("every tile has an (i)", page.locator(f'{tid("lens-tiles")} {tid("lens-trace")}').count() == page.locator(f'{tid("lens-tiles")} > div').count())
    # PLAN_R6 L2: "Add to lens" under a table in an assistant answer places it as a tile after the chosen tile; Undo removes it
    tiles_before = page.locator(f'{tid("lens-tiles")} > div').count()
    first_tile = page.locator(f'{tid("lens-tiles")} > div').first.get_attribute("data-tile") or ""
    ask(page, f"Explain the tile {first_tile}")
    add = page.locator(tid("lens-add-block")).last
    s.check("an answer table has Add to lens under it", add.count() == 1 and add.locator(tid("lens-add-block-button")).count() == 1)
    add.locator(tid("lens-add-block-position")).select_option(first_tile)
    add.locator(tid("lens-add-block-button")).click()
    page.wait_for_selector(tid("lens-add-block-done"), timeout=60_000)
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"lens-tiles\"] > div').length > {tiles_before}", timeout=60_000)
    second = page.locator(f'{tid("lens-tiles")} > div').nth(1)
    s.check("the placed tile is right after the chosen tile", second.get_attribute("data-testid") == "lens-tile-pinned", "lens-tile-pinned",
            second.get_attribute("data-testid"))
    s.check("no raw numbers after placing it (G5)", not raw_numbers(page), "none", raw_numbers(page))
    page.locator(tid("lens-add-block-undo")).last.click()
    page.wait_for_function(f"() => document.querySelectorAll('[data-testid=\"lens-tiles\"] > div').length === {tiles_before}", timeout=60_000)
    s.check("Undo removes it", page.locator(tid("lens-tile-pinned")).count() == 0)
    s.finish()

    # ---------------------------------------------------------------- 3. editing by conversation
    s.start("lenses", "L1-3", "Edit by conversation: add DSCR distribution, remove the map, show by region instead, compare with Real Estate")
    v0 = int(view.get_attribute("data-version") or 1)
    ask(page, "Add DSCR distribution")
    page.wait_for_function(f"() => Number(document.querySelector('[data-testid=\"lens-view\"]').dataset.version) > {v0}", timeout=60_000)
    s.check("a DSCR distribution tile appears", page.locator(tid("lens-tile-distribution")).filter(has_text="DSCR").count() >= 1)
    ask(page, "remove the map")
    ask(page, "show by region instead")
    ask(page, "compare with Real Estate")
    page.wait_for_selector(tid("lens-tile-compare"), timeout=60_000)
    s.check("comparison tiles appear", page.locator(tid("lens-tile-compare")).count() == 2)
    s.check("the scope shows the comparator", "Real Estate" in page.locator(tid("lens-scope")).inner_text())
    spec = api(f"/lenses/{lid}", cookie)
    s.check("five versions after four edits", spec["head"] == 5, 5, spec["head"])
    ask(page, "Explain the stage migration")
    s.check("the assistant explains a tile", "migration" in page.locator(tid("thread-turn-assistant")).last.inner_text().lower())
    ask(page, "What should I add next?")
    s.check("the assistant suggests tiles", page.locator(tid("thread-turn-assistant")).last.locator("li").count() >= 2)
    s.check("no raw numbers in the thread answers (G5)", not raw_numbers(page), "none", raw_numbers(page))
    s.finish()

    # ---------------------------------------------------------------- 4. undo, redo, versions, the tile menu
    s.start("lenses", "L1-3b", "Undo / redo / versions; tile (⋯): chart type, delete; Add ratio with a custom ratio validated by the engine")
    page.click(tid("lens-undo"))
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-view\"]').dataset.version === '4'", timeout=60_000)
    s.check("undo restores the previous version", page.locator(tid("lens-tile-compare")).count() == 0)
    page.click(tid("lens-redo"))
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-view\"]').dataset.version === '5'", timeout=60_000)
    s.check("redo brings it back", page.locator(tid("lens-tile-compare")).count() == 2)
    page.click(tid("lens-versions"))
    s.check("versions are listed", page.locator(tid("lens-version")).count() == 5)
    page.click(tid("lens-versions-dialog-close"))
    first = page.locator(f'{tid("lens-tiles")} > div').first
    first_id = first.get_attribute("data-tile")
    first.locator(tid("lens-tile-menu-button")).click()
    page.select_option(tid("lens-tile-chart"), "bar")
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-view\"]').dataset.version === '6'", timeout=60_000)
    chart = next(t["chart"] for t in api(f"/lenses/{lid}", cookie)["spec"]["tiles"] if t["id"] == first_id)
    s.check("chart type changed to columns", chart == "bar", "bar", chart)
    page.locator(f'{tid("lens-tiles")} > div[data-tile="{first_id}"] {tid("lens-tile-menu-button")}').click()
    page.click(tid("lens-tile-delete"))
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-view\"]').dataset.version === '7'", timeout=60_000)
    s.check("the tile is deleted", page.locator(f'[data-tile="{first_id}"]').count() == 0)
    page.click(tid("lens-add-ratio"))
    page.click(tid("lens-ratio-tab-custom"))
    page.fill(tid("lens-ratio-label"), "Makkah Stage 2 share of construction")
    page.select_option(tid("lens-ratio-num"), "stage2_ead")
    page.select_option(tid("lens-ratio-den"), "ead")
    page.select_option(tid("lens-ratio-filter-dim"), "region")
    page.select_option(tid("lens-ratio-filter-value"), "Makkah")
    page.click(tid("lens-ratio-validate"))
    page.wait_for_selector(tid("lens-ratio-valid"), timeout=30_000)
    page.click(tid("lens-ratio-add"))
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-view\"]').dataset.version === '8'", timeout=60_000)
    s.check("the custom ratio is on the lens with a trace", page.locator('[data-testid^="lens-kpi-custom-"]').count() == 1
            and page.locator(f'{tid("lens-view")}').get_attribute("data-untraced") == "0")
    s.finish()

    # ---------------------------------------------------------------- 5. period, save, share, report, export, schedule
    s.start("lenses", "L1-5", "As-of period in the URL; Save, Share through Mail, Add to report, Excel and PDF, Schedule")
    page.select_option(tid("lens-period"), "2026Q1")
    wait_for(page, r".*/lenses/lens-[0-9a-f]+\?.*period=2026Q1")
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-period\"]').value === '2026Q1'", timeout=60_000)
    r1 = api(f"/lenses/{lid}/render?period=2026Q1", cookie)
    s.check("figures follow the period", r1["kpis"][0]["display"] in page.locator(tid(f"lens-kpi-{r1['kpis'][0]['key']}")).inner_text())
    page.select_option(tid("lens-period"), "2026Q2")
    page.click(tid("lens-save"))
    page.fill(tid("lens-save-name"), "Construction watch (sweep)")
    page.click(tid("lens-save-confirm"))
    page.wait_for_function("() => document.querySelector('[data-testid=\"lens-title\"]')?.innerText === 'Construction watch (sweep)'", timeout=30_000)
    s.check("saved with its name", api(f"/lenses/{lid}", cookie)["name"] == "Construction watch (sweep)")
    page.click(tid("lens-share"))
    page.check(tid("lens-share-user-noura.alharbi"))
    page.click(tid("lens-share-confirm"))
    page.wait_for_selector(tid("lens-share-done"), timeout=30_000)
    s.check("shared through Mail", "Shared through Mail" in page.locator(tid("lens-share-done")).inner_text())
    page.click(tid("lens-share-dialog-close"))
    if up(PB):
        page.click(tid("lens-add-report"))
        page.click(tid("lens-report-new"))
        page.fill(tid("lens-report-title"), "Lens sweep report")
        page.click(tid("lens-report-confirm"))
        page.wait_for_selector(tid("lens-report-done"), timeout=60_000)
        s.check("added to a new Playbook report", page.locator(tid("lens-report-open")).count() == 1)
        page.click(tid("lens-report-dialog-close"))
    for kind in ("xlsx", "pdf"):
        with page.expect_download(timeout=120_000) as dl:
            page.click(tid(f"lens-export-{kind}"))
        d = dl.value
        head = open(d.path(), "rb").read(4)
        s.check(f"the {kind} export downloads", head[:2] == b"PK" if kind == "xlsx" else head == b"%PDF", kind, head)
    page.click(tid("lens-schedule"))
    page.click(tid("lens-schedule-weekly"))
    page.click(tid("lens-schedule-confirm"))
    page.wait_for_selector(f'{tid("lens-schedule")}:has-text("weekly")', timeout=30_000)
    s.check("a weekly refresh note is scheduled", (api(f"/lenses/{lid}", cookie)["schedule"] or {}).get("cadence") == "weekly")
    s.finish()

    # ---------------------------------------------------------------- 6. Back paths, hand-off, retail
    s.start("lenses", "L1-5b", "Breadcrumb and browser Back to Lenses; the saved lens is in My lenses; tile to Cockpit; retail template with roll rates")
    page.wait_for_load_state("networkidle")
    # R7: the breadcrumb is a link forward to the Lenses home (lens-crumb-home); Back (lens-back) is the previous screen.
    page.click(tid("lens-crumb-home"))
    wait_for(page, r".*/lenses$")
    page.wait_for_selector(tid(f"lens-card-{lid}"), timeout=60_000)
    s.check("the saved lens is in My lenses", page.locator(f'{tid("lenses-mine")} {tid(f"lens-card-{lid}")}').count() == 1)
    page.go_back()
    wait_for(page, rf".*/lenses/{lid}.*")
    page.wait_for_selector(tid("lens-view"), timeout=60_000)
    page.wait_for_load_state("networkidle")
    s.check("browser Back returns to the lens", page.locator(tid("lens-title")).inner_text() == "Construction watch (sweep)")
    tile = page.locator(tid("lens-tile-top_names"))
    tile.locator(tid("lens-tile-menu-button")).click()
    page.click(tid("lens-tile-cockpit"))
    wait_for(page, r".*/\?q=.*", timeout=60_000)
    s.check("the tile opens a Cockpit thread with its question", "q=" in page.url)
    page.go_back()
    wait_for(page, rf".*/lenses/{lid}.*")
    page.wait_for_selector(tid("lens-view"), timeout=60_000)
    page.wait_for_load_state("networkidle")
    s.check("Back from the Cockpit returns to the lens", page.locator(tid("lens-title")).inner_text() == "Construction watch (sweep)")
    page.goto(UI + "/lenses?book=retail", wait_until="domcontentloaded")
    page.wait_for_selector(tid("lens-card-retail-cards"), timeout=60_000)
    page.click(tid("lens-card-retail-cards"))
    wait_for(page, r".*/lenses/lens-[0-9a-f]+$", timeout=120_000)
    made.append(page.url.rstrip("/").split("/")[-1])
    page.wait_for_selector(tid("lens-view"), timeout=120_000)
    wait_idle(page)
    s.check("the retail lens has roll rates and vintages", page.locator(tid("lens-tile-roll_rate")).count() == 1 and page.locator(tid("lens-tile-vintage")).count() == 1)
    v = page.locator(tid("lens-view"))
    s.check("retail: 8-14 charts, zero untraced", 8 <= int(v.get_attribute("data-charts") or 0) <= 14 and v.get_attribute("data-untraced") == "0")
    s.check("no raw numbers on the retail lens (G5)", not raw_numbers(page), "none", raw_numbers(page))
    page.click(tid("lens-toggle-assistant"))
    wait_for(page, r".*panel=0.*")
    s.check("the assistant panel collapses (state in the URL)", page.locator(tid("lens-assistant-panel")).count() == 0)
    s.finish()

    for x in made:
        try:
            api(f"/lenses/{x}", cookie, method="DELETE")
        except Exception:  # noqa: BLE001
            pass
