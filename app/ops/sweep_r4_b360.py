"""UAT sweep, PLAN_R4 (part "r4-b360"). Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep.

Steps are added by the item that owns this part; each step is s.start(book, uat_step, title) then s.check(...).

B2, the Borrower 360 list, on both books: the full book loads (count and EAD equal the books, read here
straight from the parquet files), paging next/prev and page size, sorting on several columns, every filter,
search, the column chooser (kept after a reload), Export to Excel (the file opened: rows, order, columns,
house style), and a row -> Borrower 360 -> Back (the browser's and the screen's) keeping the list's state.
Console errors, failed requests and banned labels are checked by the Sweep at the end of every step.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable

B360 = "http://127.0.0.1:8502/api/v1/b360"
PERIOD = {"corporate": "2026Q2", "retail": "2026-08"}



def _more_filters(page, key: str) -> None:
    """PLAN_R10 E2: secondary filters sit behind "More filters"; open it when the one wanted is hidden."""
    if page.locator(f'[data-testid="b360-filter-{key}"]').count() == 0:
        page.click('[data-testid="b360-filters-more"]')

def _api(path: str, **params: Any) -> Any:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    with urllib.request.urlopen(f"{B360}{path}" + (f"?{q}" if q else ""), timeout=180) as r:  # noqa: S310 - loopback
        return json.loads(r.read())


def _books(book: str, period: str) -> dict[str, Any]:
    """Owners and EAD on the book at the period, straight from the parquet files Borrower 360 reads."""
    import duckdb
    from backend.b360 import paths
    if book == "corporate":
        b, f, key, per = paths.RELATIONS["corp_borrower"], paths.RELATIONS["corp_facility"], "borrower_id", "reporting_quarter"
    else:
        b, f, key, per = paths.RELATIONS["ret_customer"], paths.RELATIONS["ret_account"], "customer_id", "reporting_month"
    c = duckdb.connect()
    n, ead, ecl = c.execute(
        f"SELECT COUNT(DISTINCT o.{key}), SUM(x.ead_sar_mn), SUM(x.ecl_sar_mn) FROM read_parquet('{f}') x "
        f"JOIN (SELECT DISTINCT {key} FROM read_parquet('{b}') WHERE {per} = ?) o USING ({key}) WHERE x.{per} = ?",
        [period, period]).fetchone()
    return {"n": int(n), "ead": float(ead), "ecl": float(ecl)}


def b360_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    from uat_sweep import count, download, sar, tid, txt, url_params
    from backend.house_style import check as house_check
    from backend.house_style.xlsx import read_about, read_table

    def dev_refresh_only() -> None:
        """Drop one kind of error: a dev-server refresh of the page (an `_rsc` fetch, sent when another session's
        edit hot-reloads) that the list's next pushState supersedes ends as ERR_ABORTED. It is not the app failing."""
        s.errors[:] = [e for e in s.errors if not ("ERR_ABORTED" in e and "_rsc=" in e)]

    def start(book: str, uat: str, title: str) -> None:
        dev_refresh_only()
        s.start(book, uat, title)

    def ids() -> list[str]:
        return [x.replace("b360-row-", "") for x in
                page.eval_on_selector_all('[data-testid^="b360-row-"]', "els => els.map(e => e.dataset.testid)")]

    def settle(want: dict | None = None) -> None:
        """The list has loaded, and (when given) shows the API page `want`."""
        page.wait_for_selector('[data-testid="b360-list"][data-loading="false"] [data-testid="b360-list-table"]', timeout=120_000)
        if want is not None:
            first = want["rows"][0]["id"] if want["rows"] else None
            page.wait_for_function(
                """([total, first]) => {
                     const l = document.querySelector('[data-testid="b360-list"]');
                     if (!l || l.dataset.loading !== 'false' || l.dataset.total !== String(total)) return false;
                     const r = document.querySelector('[data-testid^="b360-row-"]');
                     return first === null ? !r : (r && r.dataset.testid === 'b360-row-' + first);
                   }""", arg=[want["total"], first], timeout=120_000)
        page.wait_for_timeout(250)

    def query_of_url() -> dict[str, Any]:
        u = url_params(page)
        size = int(u.get("size", 50))
        q = {k: u[k] for k in ("q", "segment", "subsegment", "region", "branch", "product", "band", "stage", "ews", "dpd",
                               "ead_min", "ead_max", "sort", "dir", "period") if u.get(k)}
        q.update(offset=(int(u.get("page", 1)) - 1) * size, limit=size)
        return q

    def same_as_api(book: str, label: str) -> dict:
        want = _api("/list", domain=book, **query_of_url())
        settle(want)
        expected = [r["id"] for r in want["rows"]]
        try:  # the whole page, read in one go (a dev-server refresh can remount the list for a moment)
            page.wait_for_function(
                """ids => JSON.stringify([...document.querySelectorAll('[data-testid^="b360-row-"]')]
                           .map(e => e.dataset.testid.slice(9))) === JSON.stringify(ids)""", arg=expected, timeout=30_000)
        except Exception:  # noqa: BLE001 - the check below records what was seen
            pass
        got = ids()
        s.check(f"{label}: the rows on screen are the API's page, in order", got == [r["id"] for r in want["rows"]],
                [r["id"] for r in want["rows"]][:5], got[:5])
        s.check(f"{label}: total {count(want['total'])}", txt(page, "b360-list-total").strip() == count(want["total"]),
                count(want["total"]), txt(page, "b360-list-total"))
        s.check(f"{label}: EAD {sar(want['totals']['ead'])}", txt(page, "b360-list-ead").strip() == sar(want["totals"]["ead"]),
                sar(want["totals"]["ead"]), txt(page, "b360-list-ead"))
        return want

    for book in ("corporate", "retail"):
        owners = "borrowers" if book == "corporate" else "customers"
        period = PERIOD[book]

        # ---- the full book
        start(book, "B2", f"Borrower 360 list: every {owners[:-1]} on the {book} book")
        page.wait_for_load_state("networkidle")       # a reload aborts what is in flight
        page.goto(f"{UI}/borrower-360?domain={book}", wait_until="domcontentloaded")
        want = same_as_api(book, "full book")
        truth = _books(book, want["period"])
        s.check(f"the list is the full book: {count(truth['n'])} {owners} (parquet)", want["total"] == truth["n"] > 25,
                truth["n"], want["total"])
        s.check("EAD total equals the book (parquet)", abs(want["totals"]["ead"] - truth["ead"]) < 1e-6
                and txt(page, "b360-list-ead").strip() == sar(truth["ead"]), sar(truth["ead"]), txt(page, "b360-list-ead"))
        s.check("ECL total equals the book (parquet)", abs(want["totals"]["ecl"] - truth["ecl"]) < 1e-6
                and txt(page, "b360-list-ecl").strip() == sar(truth["ecl"]), sar(truth["ecl"]), txt(page, "b360-list-ecl"))
        s.check("50 rows on the first page", len(ids()) == 50, 50, len(ids()))
        s.check(f"the period is the book's latest ({period})", want["period"] == period, period, want["period"])
        s.check("page info", txt(page, "b360-page-info").strip() == f"1–50 of {count(truth['n'])}",
                f"1–50 of {count(truth['n'])}", txt(page, "b360-page-info"))

        # ---- paging
        start(book, "B2", "Borrower 360 list: page next, previous, rows per page")
        page.click(tid("b360-page-next"))
        page.wait_for_url(lambda u: "page=2" in u, timeout=30_000)
        same_as_api(book, "page 2")
        s.check("page 2 in the address and on screen", url_params(page).get("page") == "2"
                and txt(page, "b360-page-info").strip().startswith("51–100 of"), "51–100", txt(page, "b360-page-info"))
        page.click(tid("b360-page-next"))
        page.wait_for_url(lambda u: "page=3" in u, timeout=30_000)
        same_as_api(book, "page 3")
        page.click(tid("b360-page-prev"))
        page.wait_for_url(lambda u: "page=2" in u, timeout=30_000)
        same_as_api(book, "back to page 2")
        page.go_back()
        page.wait_for_url(lambda u: "page=3" in u, timeout=30_000)
        same_as_api(book, "browser Back: page 3")
        page.select_option(tid("b360-page-size"), "100")
        page.wait_for_url(lambda u: "size=100" in u, timeout=30_000)
        same_as_api(book, "100 rows per page")
        s.check("100 rows, back on page 1", len(ids()) == 100 and "page" not in url_params(page), 100, len(ids()))
        page.select_option(tid("b360-page-size"), "50")
        page.wait_for_url(lambda u: "size=" not in u, timeout=30_000)
        settle()

        # ---- sorting
        start(book, "B2", "Borrower 360 list: sort by column, both directions")
        cols = [c["key"] for c in want["columns"] if c["default"]]
        for key in [k for k in ("ead", "rating", "id", "dpd", "ews_band", "segment") if k in cols]:
            page.click(tid(f"b360-sort-{key}"))
            page.wait_for_url(lambda u, k=key: f"sort={k}" in u, timeout=30_000)
            first_dir = url_params(page).get("dir")
            same_as_api(book, f"sort {key} {first_dir}")
            page.click(tid(f"b360-sort-{key}"))
            page.wait_for_url(lambda u, d=first_dir: f"dir={'asc' if d == 'desc' else 'desc'}" in u, timeout=30_000)
            same_as_api(book, f"sort {key} {url_params(page).get('dir')}")
            hdr = page.get_attribute(f'th:has({tid(f"b360-sort-{key}")})', "aria-sort")
            s.check(f"sort {key}: the header says so", hdr in ("ascending", "descending"), "ascending|descending", hdr)
        page.click(tid(f"b360-book-{book}"))          # the book toggle starts the list afresh (no reload)
        page.wait_for_url(lambda u: "sort=" not in u, timeout=30_000)
        settle()

        # ---- every filter
        start(book, "B2", "Borrower 360 list: every filter, one at a time")
        opts = _api("/list/options", domain=book)
        filters = ["segment", "subsegment", "region", "product", "band", "stage", "ews", "dpd"]
        if opts.get("branch_available"):
            filters.insert(3, "branch")
        else:
            s.check("no branch filter while the books carry no branch", page.locator(tid("b360-filter-branch")).count() == 0)
        for key in filters:
            counts: dict[str, int] = {}
            for o in opts[key]:                      # a sub-sector can sit under several sectors: add them up
                counts[o["value"]] = counts.get(o["value"], 0) + o["count"]
            values = [v for v, c in counts.items() if c > 0]
            value = values[min(1, len(values) - 1)]
            _more_filters(page, key)
            page.select_option(tid(f"b360-filter-{key}"), value)
            page.wait_for_url(lambda u, k=key: f"{k}=" in u, timeout=30_000)
            got = same_as_api(book, f"filter {key} = {value}")
            n = counts[value]
            s.check(f"filter {key} = {value}: {count(n)} {owners}, as the options said", got["total"] == n, n, got["total"])
            page.select_option(tid(f"b360-filter-{key}"), "")
            page.wait_for_url(lambda u, k=key: f"{k}=" not in u, timeout=30_000)
            settle()
        lo = round(want["totals"]["ead"] / want["total"], 2)
        _more_filters(page, "ead_min")
        page.fill(tid("b360-filter-ead_min"), str(lo))
        page.press(tid("b360-filter-ead_min"), "Enter")
        page.wait_for_url(lambda u: "ead_min=" in u, timeout=30_000)
        page.fill(tid("b360-filter-ead_max"), str(round(lo * 3, 2)))
        page.press(tid("b360-filter-ead_max"), "Enter")
        page.wait_for_url(lambda u: "ead_max=" in u, timeout=30_000)
        got = same_as_api(book, f"EAD from {lo} to {round(lo * 3, 2)} (SAR m)")
        s.check("the EAD range narrows the list", 0 < got["total"] < want["total"], f"0 < n < {want['total']}", got["total"])
        page.select_option(tid("b360-filter-stage"), "2")
        page.wait_for_url(lambda u: "stage=2" in u, timeout=30_000)
        same_as_api(book, "EAD range and stage 2 together")
        page.click(tid("b360-filters-clear"))
        page.wait_for_url(lambda u: "stage=" not in u and "ead_min=" not in u, timeout=30_000)
        same_as_api(book, "filters cleared")

        # ---- search
        start(book, "B2", "Borrower 360 list: search by ID and name")
        target = want["rows"][3]["id"]
        page.fill(tid("b360-search"), target)
        page.press(tid("b360-search"), "Enter")
        page.wait_for_url(lambda u: "q=" in u, timeout=30_000)
        got = same_as_api(book, f"search {target}")
        s.check(f"search {target} finds it first", got["rows"] and got["rows"][0]["id"] == target, target, ids()[:3])
        term = (want["rows"][0].get("name") or "").split()[0] if book == "corporate" else target[:5]
        page.fill(tid("b360-search"), term)
        page.wait_for_url(lambda u, t=term: urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("q") == [t],
                          timeout=30_000)  # typing commits on its own
        got = same_as_api(book, f"search “{term}”")
        s.check(f"search “{term}” finds several", got["total"] > 1, "> 1", got["total"])
        page.click(tid("b360-search-clear"))
        page.wait_for_url(lambda u: "q=" not in u, timeout=30_000)
        same_as_api(book, "search cleared")

        # ---- column chooser
        start(book, "B2", "Borrower 360 list: column chooser, kept after a reload")
        extra = next(c["key"] for c in want["columns"] if not c["default"])
        drop = next(c["key"] for c in want["columns"] if c["default"] and c["key"] not in ("id", "ead"))
        s.check(f"{extra} is not shown by default", page.locator(tid(f"b360-sort-{extra}")).count() == 0)
        page.click(tid("b360-columns"))
        page.click(tid(f"b360-column-toggle-{extra}"))
        page.click(tid(f"b360-column-toggle-{drop}"))
        s.check("the id column cannot be hidden", page.is_disabled(tid("b360-column-toggle-id")))
        page.keyboard.press("Escape")
        s.check(f"{extra} shown, {drop} hidden", page.locator(tid(f"b360-sort-{extra}")).count() == 1
                and page.locator(tid(f"b360-sort-{drop}")).count() == 0)
        page.wait_for_load_state("networkidle")
        page.reload(wait_until="domcontentloaded")
        settle()
        page.wait_for_selector(tid(f"b360-sort-{extra}"), timeout=30_000)
        s.check("the choice is kept after a reload", page.locator(tid(f"b360-sort-{extra}")).count() == 1
                and page.locator(tid(f"b360-sort-{drop}")).count() == 0)

        # ---- Export to Excel: the filtered, sorted full list, with the chosen columns
        start(book, "B2", "Borrower 360 list: Export to Excel (filtered, sorted, all rows, chosen columns, house style)")
        seg = max(opts["segment"], key=lambda o: o["count"])["value"]
        page.select_option(tid("b360-filter-segment"), seg)
        page.wait_for_url(lambda u: "segment=" in u, timeout=30_000)
        settle()
        page.click(tid("b360-sort-ead"))
        page.wait_for_url(lambda u: "sort=ead" in u, timeout=30_000)
        flt = same_as_api(book, f"{seg}, by EAD")
        shown = [h.replace("b360-sort-", "") for h in
                 page.eval_on_selector_all('[data-testid^="b360-sort-"]', "els => els.map(e => e.dataset.testid)")]
        path = download(page, "b360-list-excel")
        import openpyxl
        body = path.read_bytes()
        problems = house_check.xlsx(body)
        s.check("the workbook is in the house style", not problems, "[]", problems[:3])
        wb = openpyxl.load_workbook(path)
        ws = wb.worksheets[0]
        header, rows = read_table(ws)
        s.check(f"every row of the filtered list: {count(flt['total'])}", len(rows) == flt["total"], flt["total"], len(rows))
        s.check("one column per column on screen, in order", len(header) == len(shown), shown, header)
        s.check("the screen's order (first rows)", [r[0] for r in rows[:len(flt["rows"])]] == [r["id"] for r in flt["rows"]],
                [r["id"] for r in flt["rows"]][:5], [r[0] for r in rows[:5]])
        ead_col = shown.index("ead") if "ead" in shown else None
        if ead_col is not None:
            eads = [r[ead_col] for r in rows]
            s.check("sorted by EAD, highest first", eads == sorted(eads, reverse=True))
            s.check("EAD total equals the list", abs(sum(eads) - flt["totals"]["ead"]) < 1e-6, flt["totals"]["ead"], sum(eads))
        s.check("brand header row and frozen panes", ws.freeze_panes is not None and bool(ws.auto_filter.ref), "panes + filter",
                (ws.freeze_panes, ws.auto_filter.ref))
        about = read_about(wb)
        s.check("About: book, period, filter and rows", about.get("Period") == flt["period"]
                and str(about.get(f"Rows: {owners}")) == str(flt["total"]) and seg in json.dumps(about, default=str),
                (flt["period"], flt["total"], seg), about)
        wb.close()

        # ---- a row opens its Borrower 360; Back returns to the same list
        start(book, "B2", "Borrower 360 list: row → Borrower 360 → Back keeps the list (filters, sort, page)")
        page.click(tid("b360-page-next"))
        page.wait_for_url(lambda u: "page=2" in u, timeout=30_000)
        before = same_as_api(book, "page 2 of the filtered list")
        list_url = page.url
        who = before["rows"][0]["id"]
        page.click(tid(f"b360-row-{who}"))
        page.wait_for_selector(f'[data-testid="b360-customer"][data-customer="{who}"]', timeout=90_000)
        s.check("the row opened its Borrower 360", txt(page, "b360-id").strip() == who
                and url_params(page).get("customer_id") == who, who, txt(page, "b360-id"))
        head = txt(page, "b360-header")
        s.check("its header shows the row's EAD", sar(before["rows"][0]["ead"]) in head, sar(before["rows"][0]["ead"]), head[:160])
        page.click(tid("b360-tab-facilities"))
        page.wait_for_selector(tid("b360-panel-facilities"), timeout=60_000)
        page.go_back()
        page.wait_for_selector(tid("b360-panel-profile"), timeout=60_000)
        page.go_back()
        settle(before)
        s.check("browser Back: the same list URL", page.url == list_url, list_url, page.url)
        s.check("browser Back: the same rows", ids()[:5] == [r["id"] for r in before["rows"][:5]])
        page.go_forward()
        page.wait_for_selector(f'[data-testid="b360-customer"][data-customer="{who}"]', timeout=90_000)
        page.click(tid("b360-back-to-list"))
        settle(before)
        u = url_params(page)
        s.check("All borrowers/customers: filters, sort and page kept", (u.get("segment"), u.get("sort"), u.get("page")) == (seg, "ead", "2"),
                (seg, "ead", "2"), (u.get("segment"), u.get("sort"), u.get("page")))
        s.check("All borrowers/customers: the same rows", ids()[:5] == [r["id"] for r in before["rows"][:5]])
        page.wait_for_load_state("networkidle")
        page.reload(wait_until="domcontentloaded")
        settle(before)
        s.check("a reload of the list address shows the same page", ids()[:5] == [r["id"] for r in before["rows"][:5]])

        # ---- the deep link and the columns reset
        start(book, "B2", "Borrower 360 deep link still opens the borrower; columns back to default")
        deep = "CB01312" if book == "corporate" else "RC023173"
        page.wait_for_load_state("networkidle")
        page.goto(f"{UI}/borrower-360?domain={book}&customer_id={deep}&period={period}&tab=profile", wait_until="domcontentloaded")
        page.wait_for_selector(f'[data-testid="b360-customer"][data-customer="{deep}"]', timeout=90_000)
        s.check("deep link opens the borrower on its tab", page.locator(tid("b360-panel-profile")).count() == 1)
        page.click(tid("b360-back-to-list"))
        settle()
        s.check("from a deep link, the list opens on the book", url_params(page).get("domain", "corporate") == book
                and "customer_id" not in url_params(page))
        page.click(tid("b360-columns"))
        page.click(tid("b360-columns-reset"))
        page.keyboard.press("Escape")
        defaults = [c["key"] for c in want["columns"] if c["default"]]
        now = [h.replace("b360-sort-", "") for h in
               page.eval_on_selector_all('[data-testid^="b360-sort-"]', "els => els.map(e => e.dataset.testid)")]
        s.check("Default columns restores the default set", now == defaults, defaults, now)
    dev_refresh_only()
    s.finish()
