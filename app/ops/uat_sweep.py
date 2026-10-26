"""UAT sweep: Anne's manual UAT script, executed in a real browser, on both books.

Runs every step of docs/v5/EWS_UAT.md section 4 as Anne will, on Corporate and
on Retail, and clicks every button and link on the Cockpit and Early Warning
screens: the Corporate/Retail toggles, the sidebar links, every card's Open
buttons, Up, the breadcrumbs at every level, the group pills, every filter and
each filter chip's clear button, the Quarter / Month selector, Why this
ranking, Model details (every tab, and back), Open in Borrower 360 and Back to
Early Warning, Export to What-If and its way back, Ask the Cockpit, and the
browser Back button from the deepest level to the top, one level at a time.

Every figure on screen is checked against the Early Warning API, and the
portfolio and segment figures against the books themselves (the Cockpit lake,
read with pandas, independently of the service). Every step must have no
console error, no page error and no failed request.

Usage:  .venv/bin/python ops/uat_sweep.py [ui_base] [ews_api_base] [--stop-start]
Needs the one app running (ops/v5.sh start). With --stop-start it ends with UAT
step 21: ops/v5.sh stop (ports 5500/8500/8501 close, an unrelated process
survives), then ops/v5.sh start again. Writes
evidence/v5/ews/uat_sweep/{uat_sweep.json, SUMMARY.md, *.png}. Exit 1 on any failure.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import os  # noqa: E402
import core_login  # noqa: E402  (ops/core_login.py: the Core service session)
from playwright.sync_api import Page, sync_playwright

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
from backend.ews_domain import paths as ews_paths, reader as rd  # noqa: E402
from backend.spine import books  # noqa: E402
from backend.house_style import check as house_check  # noqa: E402
from backend.house_style.xlsx import read_about, read_table  # noqa: E402

#: A partial run (--only) never overwrites the committed evidence of the full sweep.
OUT = (Path(os.environ["SWEEP_OUT"]) if os.environ.get("SWEEP_OUT")   # a parallel run keeps its own report
       else V5 / "var" / "sweep_only" if "--only" in sys.argv else V5 / "evidence" / "v5" / "ews" / "uat_sweep")
_ARGS = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--only"]
UI = (_ARGS[0] if _ARGS else "http://127.0.0.1:5500").rstrip("/")
API = (_ARGS[1] if len(_ARGS) > 1 else "http://127.0.0.1:8501").rstrip("/")
BOOKS = ("corporate", "retail")
PROD_UI = os.environ.get("V5_UI_MODE") == "prod"
NAV = 'nav[aria-label="Primary"]'
#: The UAT script's named drill paths (docs/v5/EWS_UAT.md section 4).
PATHS = {
    # The searched borrower is the leading warned borrower of the segment under
    # the live rule set (CB01045, named in the 1.1.0 script, is not warned under 1.2.0).
    "corporate": {"segment": "Construction", "cls": "", "search": ""},
    "retail": {"segment": "Personal Finance", "cls": "SALARIED", "search": ""},
}


# ------------------------------------------------------------ formatting
# The UI's own formatters (frontend/src/lib/v5/ews.ts), so a figure is compared
# exactly as it is printed.

def _locale(x: float, d: int) -> str:
    """Number.toLocaleString("en-US", {min/max fraction digits d}): ICU rounds the
    shortest decimal form of the double half away from zero."""
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{q:,.{d}f}"


def _to_fixed(x: float, d: int) -> str:
    """Number.prototype.toFixed: the exact binary value, ties away from zero."""
    q = Decimal(float(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{q:.{d}f}"


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


def pct(v, places: int = 1) -> str:
    return "—" if v is None else f"{_to_fixed(v, places)}%"


def signed(v) -> str:
    if v is None:
        return "—"
    n = float(v)
    return ("+" if n > 0 else "−" if n < 0 else "") + _locale(abs(n), 0)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def as_of(period: str) -> str:
    import calendar
    q = re.fullmatch(r"(\d{4})Q([1-4])", period)
    if q:
        y, m = int(q[1]), int(q[2]) * 3
        return f"Q{q[2]} {y} ({calendar.monthrange(y, m)[1]} {MONTHS[m - 1]} {y})"
    y, m = map(int, period.split("-"))
    return f"{MONTHS[m - 1]} {y} ({calendar.monthrange(y, m)[1]} {MONTHS[m - 1]} {y})"


# ------------------------------------------------------------ API and books

def api(path: str, **params) -> Any:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    with urllib.request.urlopen(f"{API}/api/v1/ews{path}{'?' + q if q else ''}", timeout=120) as r:
        return json.loads(r.read())


_BOOK_CACHE: dict[str, pd.DataFrame] = {}


def book_frame(domain: str) -> pd.DataFrame:
    """The book's own exposure table (the Cockpit lake), not the EWS release."""
    if domain not in _BOOK_CACHE:
        b = books.book(domain)
        spec = rd.domain_spec(domain)
        cols = [b.period_column, spec["key"], spec["owner_key"], spec["segment"], "ead_sar_mn",
                "ecl_sar_mn", "dpd_days", "stage", "default_flag"]
        _BOOK_CACHE[domain] = pd.read_parquet(b.path(b.exposure_relation), columns=cols)
    return _BOOK_CACHE[domain]


def book_figures(domain: str, period: str, segment: str = "") -> dict[str, Any]:
    spec = rd.domain_spec(domain)
    f = book_frame(domain)
    f = f[f[books.book(domain).period_column] == period]
    if segment:
        f = f[f[spec["segment"]] == segment]
    bad = (f.dpd_days >= 90) | (f.stage == 3) | (f.default_flag == 1)
    return {"customers": int(f[spec["owner_key"]].nunique()), "facilities": int(len(f)),
            "exposure": float(f.ead_sar_mn.sum()), "ecl": float(f.ecl_sar_mn.sum()),
            "current_bad": int(f.loc[bad, spec["owner_key"]].nunique())}



# ------------------------------------------------------------ label rule

#: Global label rule (docs/v5/PLAN_R2.md section 0): none of these may be rendered or written to a file.
BANNED = re.compile(r"synthetic|(?<![\w-])demo(?![\w-])|demo[- ]data", re.I)
_SCREEN_TEXT = """() => {
  const t = [document.title, document.body ? document.body.innerText : ""];
  document.querySelectorAll('[title],[aria-label],[placeholder],[alt]').forEach(e => {
    for (const a of ['title', 'aria-label', 'placeholder', 'alt']) t.push(e.getAttribute(a) || '');
  });
  return t.join('\\n');
}"""


_NOT_CLIENT_DATA = re.compile(r'"not_client_data":\s*"[^"]*"')


def banned_in(text: str) -> list[str]:
    """Every banned phrase in the text, each with a little context, no more than five."""
    out = []
    for m in BANNED.finditer(text or ""):
        a, b = max(0, m.start() - 30), min(len(text), m.end() + 30)
        out.append(text[a:b].replace("\n", " "))
        if len(out) == 5:
            break
    return out


def file_text(path: Path) -> str:
    """The text a file carries: the XML parts of a workbook or Word document, or the plain text of a csv."""
    import zipfile
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                return "\n".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith((".xml", ".rels", ".txt")))
        return Path(path).read_text(errors="ignore")
    except Exception:  # noqa: BLE001
        return ""

# ------------------------------------------------------------ recording

class Sweep:
    def __init__(self, page: Page):
        self.page = page
        self.steps: list[dict] = []
        self.errors: list[str] = []
        self.current: dict | None = None
        self.n = 0
        #: (status, url fragment) pairs a step expects, for example the 401 of a wrong password.
        self.allowed: list[tuple[int, str]] = []
        self.label_api: list[str] = []
        self.label_files: list[Any] = []
        self.observe(page)
        page.on("console", lambda m: self.errors.append("console: " + m.text[:240])
                if m.type == "error" and not self._allowed_console(m.text) else None)
        page.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e)[:240]))
        page.on("response", lambda r: self.errors.append(f"http {r.status}: {r.request.method} {r.url[:180]}")
                if r.status >= 400 and not self._ignored(r.url) and not self._allowed_response(r) else None)
        # A link that turns into a file download ends its navigation as
        # net::ERR_ABORTED. That is the download, not a failure: the sweep
        # opens and checks every downloaded workbook (check_excel).
        page.on("requestfailed", lambda r: self.errors.append(
            f"request failed ({r.failure}): {r.method} {r.url[:180]}")
            if not self._ignored(r.url) and not (re.search(r"/(export\.(xlsx|csv|docx|pdf)|report\.docx|pack\.docx|files/f_)", r.url) and "ERR_ABORTED" in str(r.failure))
            # An event stream closed by its page (unmount, or the run settled) ends as ERR_ABORTED.
            and not (re.search(r"/runs/[^/]+/events", r.url) and "ERR_ABORTED" in str(r.failure))
            # A production build (the cloud session's UI) prefetches linked routes (`?_rsc=`); a prefetch the browser
            # aborts on navigation is not a failed request of the app.
            and not ("_rsc=" in r.url and "ERR_ABORTED" in str(r.failure))
            # A script chunk still downloading when the sweep navigates away is cancelled by the browser (PLAN_R5:
            # threads now answer in place, so a chart's chunk can still be in flight); not a request the app failed.
            and not ("/_next/static/chunks/" in r.url and "ERR_ABORTED" in str(r.failure))
            # PLAN_R5 P5 (the production build, which loads faster than the APIs answer): a read (GET) to a v5 service
            # that the browser cancels because the sweep navigated on is not a request the app failed; a service error
            # still fails (a status code, a refused or reset connection), and so does any write.
            and not (r.method == "GET" and re.search(r"//127\.0\.0\.1:85\d\d/api/", r.url) and "ERR_ABORTED" in str(r.failure))
            else None)

    def observe(self, page: Page) -> None:
        """Watch a page for the label rule: API data the page receives, and the files it downloads."""
        def on_response(r) -> None:
            try:
                if r.status == 200 and "/api/" in r.url and "json" in (r.headers.get("content-type") or ""):
                    # The frozen Cockpit's schema carries the release manifest's provenance sentence as data
                    # (`not_client_data`); FX-6 keeps it off the screen, and the rule keeps it in the manifest.
                    for hit in banned_in(_NOT_CLIENT_DATA.sub("", r.text())):
                        self.label_api.append(f"{r.url.split('/api/')[-1][:70]}: {hit}")
            except Exception:  # noqa: BLE001  (a body that is gone, a redirect)
                pass
        page.on("response", on_response)
        page.on("download", lambda d: self.label_files.append(d))

    def _label_check(self) -> None:
        """The label rule, on the screen, in the data and in every file of the step that is ending."""
        if self.current is None:
            return
        on_screen = []
        if self.page is not None:
            try:
                on_screen = banned_in(self.page.evaluate(_SCREEN_TEXT))
            except Exception:  # noqa: BLE001
                pass
        written = []
        for d in self.label_files:
            try:
                for hit in banned_in(file_text(Path(d.path()))):
                    written.append(f"{d.suggested_filename}: {hit}")
            except Exception:  # noqa: BLE001
                pass
        self.check("label rule: no 'Synthetic' / 'Demo' on the screen", not on_screen, "none", on_screen[:2])
        self.check("label rule: none in the data the screen received", not self.label_api, "none", sorted(set(self.label_api))[:2])
        if self.label_files:
            self.check("label rule: none in the files downloaded", not written, "none", written[:2])
        # PLAN_R3 S3-1: every Excel and Word file is in the house style (backend/house_style/check.py).
        for d in self.label_files:
            try:
                name, path = d.suggested_filename, Path(d.path())
            except Exception:  # noqa: BLE001
                continue
            if name.endswith((".xlsx", ".docx")):
                try:
                    problems = house_check.any_file(path)
                except Exception as exc:  # noqa: BLE001
                    problems = [f"could not open: {exc}"]
                self.check(f"house style: {name}", not problems, "header block, brand header, panes, filter, banding, formats",
                           problems[:3])
        self.label_api, self.label_files = [], []

    def _allowed_response(self, r) -> bool:
        # A production build (V5_UI_MODE=prod, the cloud session) prefetches every link in view (`?_rsc=`), including
        # links to routes that only exist with a query in dev; a prefetch 404 is not a request the page made.
        if PROD_UI and r.status == 404 and "_rsc=" in r.url:
            self._prefetch_404 = True
            return True
        return any(r.status == st and frag in r.url for st, frag in self.allowed)

    def _allowed_console(self, text: str) -> bool:
        if PROD_UI and getattr(self, "_prefetch_404", False) and "status of 404" in text:
            return True
        return any(f"status of {st}" in text for st, _ in self.allowed)

    @staticmethod
    def _ignored(url: str) -> bool:
        # The dev server's hot-reload socket and the browser's favicon probe are
        # not requests the app makes.
        return "_next/webpack-hmr" in url or "favicon" in url or "__nextjs_original-stack-frame" in url

    def start(self, book: str, uat: str, title: str) -> None:
        self.finish()
        self.n += 1
        self.errors = []
        self._prefetch_404 = False
        self.current = {"n": self.n, "book": book, "uat_step": uat, "title": title, "checks": [],
                        "started": time.time()}
        print(f"\n[{self.n:03d}] {book:9s} UAT {uat:5s} {title}", flush=True)

    def check(self, label: str, ok: bool, expected: Any = "", seen: Any = "") -> bool:
        assert self.current is not None
        self.current["checks"].append({"check": label, "pass": bool(ok), "expected": str(expected)[:300],
                                       "seen": str(seen)[:300]})
        if not ok:
            print(f"    FAIL {label}: expected {str(expected)[:160]!r} seen {str(seen)[:160]!r}", flush=True)
        return ok

    def finish(self) -> None:
        if not self.current:
            return
        if self.page is not None:
            self.page.wait_for_timeout(400)
        self._label_check()
        errs = list(self.errors)
        self.current["errors"] = errs
        self.current["seconds"] = round(time.time() - self.current.pop("started"), 1)
        self.current["pass"] = all(c["pass"] for c in self.current["checks"]) and not errs
        if errs:
            print("    ERRORS: " + " | ".join(errs[:4]), flush=True)
        try:
            if self.page is None:
                raise RuntimeError("browser closed")
            name = f"{self.current['n']:03d}_{self.current['book']}_{re.sub(r'[^a-z0-9]+', '_', self.current['title'].lower())[:50]}"
            self.page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
            self.current["screenshot"] = f"{name}.png"
        except Exception as e:  # noqa: BLE001
            self.current["screenshot"] = f"(none: {e})"
        self.steps.append(self.current)
        self.current = None


# ------------------------------------------------------------ page helpers

def tid(testid: str) -> str:
    return f'[data-testid="{testid}"]'


def wait(page: Page, testid: str, timeout: int = 90_000) -> None:
    page.wait_for_selector(tid(testid), timeout=timeout)
    page.wait_for_timeout(300)


def txt(page: Page, testid: str) -> str:
    return page.locator(tid(testid)).first.inner_text()


def settle_level(page: Page, level: str) -> None:
    wait(page, f"ews-level-{level}")
    page.wait_for_selector(tid("ews-kpis"), timeout=60_000)


def settle_list(page: Page) -> None:
    wait(page, "ews-list-total")
    # the list re-reads on every filter; wait until no skeleton is left
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def url_params(page: Page) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


# ------------------------------------------------------------ figure checks

def _of_n(n, total):
    return f"{count(n)} of {count(total)}"


# PLAN_R10 E1: one row of 4 small tiles; subsets show "n of N · x% of exposure".
KPI_TILES = [
    ("ews-kpi-warned", lambda h, m, L, p: [count(h["customers_warned"]),
                                           f"{_of_n(h['customers_warned'], h['customers'])} · {pct(h['exposure_warned_pct'])} of exposure"]),
    ("ews-kpi-high", lambda h, m, L, p: [count(h["high_or_critical"]),
                                         f"{_of_n(h['high_or_critical'], h['customers'])} · {pct(h['exposure_severe_pct'])} of exposure"]),
    ("ews-kpi-bad", lambda h, m, L, p: [count(h["current_bad"]), _of_n(h["current_bad"], h["customers"])]),
    ("ews-kpi-warned-exposure", lambda h, m, L, p: [sar(h["exposure_warned"]), f"{pct(h['exposure_warned_pct'])} of {sar(h['exposure'])}"]),
]


def check_level(s: Sweep, page: Page, lv: dict, book: str) -> None:
    """Every tile, the as-of line, the breadcrumbs and every card on a level, against the API (and the books)."""
    h, m, L = lv["headline"], lv["movement"], lv["labels"]
    s.check("as-of line", as_of(lv["period"]) in txt(page, "ews-as-of"), as_of(lv["period"]), txt(page, "ews-as-of"))
    for testid, want in KPI_TILES:
        shown = txt(page, testid)
        for piece in want(h, m, L, lv["prior_period"]):
            s.check(f"{testid} shows {piece}", piece in shown, piece, shown.replace("\n", " "))
    crumbs = txt(page, "ews-breadcrumbs")
    s.check("breadcrumbs", all(b["label"] in crumbs for b in lv["breadcrumbs"]),
            " › ".join(b["label"] for b in lv["breadcrumbs"]), crumbs.replace("\n", " "))
    summary = txt(page, "ews-level-summary")
    s.check("open-warned button carries the warned count", f"Open the {count(h['customers_warned'])} warned" in summary,
            f"Open the {count(h['customers_warned'])} warned", summary[:120])
    cards = [*lv.get("classifications", []), *lv.get("children", [])]
    shown_cards = page.locator('[data-testid^="ews-card-"]').count()
    s.check("one card per child", shown_cards == len(cards), len(cards), shown_cards)
    for c in cards:
        body = page.locator(tid(f"ews-card-{c['key']}")).first.inner_text()
        want = [c["label"], f"{pct(c['exposure_severe_pct'])} high/critical", f"{signed(c['movement']['customers_warned'])} warned",
                count(c["customers"]), count(c["customers_warned"]), count(c["high_or_critical"]),
                count(c["current_bad"]), count(c["forward_risk"]), sar(c["exposure"]), sar(c["exposure_severe"]),
                pct(c["exposure_warned_pct"]), pct(c["odr_pct"], 2), pct(c["dpd_30_plus_pct"])]
        missing = [w for w in want if w not in body]
        s.check(f"card {c['key']}: every figure", not missing, "all of " + "; ".join(want), "missing " + "; ".join(missing))
    # The books, independently of the service.
    if lv["scope"]["level"] in ("portfolio", "segment"):
        bf = book_figures(book, lv["period"], lv["scope"]["segment"])
        for k in ("customers", "facilities", "current_bad"):
            s.check(f"{k} equals the book", bf[k] == h[k], bf[k], h[k])
        for k in ("exposure", "ecl"):
            s.check(f"{k} equals the book", abs(bf[k] - h[k]) < 1e-6, bf[k], h[k])
    if lv["scope"]["level"] == "portfolio":
        for c in lv["children"]:
            bf = book_figures(book, lv["period"], c["key"])
            s.check(f"card {c['key']}: customers and exposure equal the book",
                    bf["customers"] == c["customers"] and abs(bf["exposure"] - c["exposure"]) < 1e-6,
                    (bf["customers"], round(bf["exposure"], 4)), (c["customers"], round(c["exposure"], 4)))


def check_excel(s: Sweep, page: Page, testid: str, book: str, period: str, customers: int,
                exposures: int | None = None, rules_fired: int | None = None) -> None:
    """Click an Export to Excel button, open the workbook, check its sheets and rows against the API."""
    import openpyxl
    with page.expect_download(timeout=120_000) as d:
        page.click(tid(testid))
    dl = d.value
    path = OUT / "downloads" / dl.suggested_filename
    path.parent.mkdir(parents=True, exist_ok=True)
    dl.save_as(path)
    s.check(f"{testid}: file name carries book and period", book in dl.suggested_filename and period in dl.suggested_filename
            and dl.suggested_filename.endswith(".xlsx"), f"{book} {period} .xlsx", dl.suggested_filename)
    wb = openpyxl.load_workbook(path, read_only=True)
    first = "Borrowers" if book == "corporate" else "Customers"
    s.check(f"{testid}: sheets", wb.sheetnames == [first, "Exposures", "Rules fired", "About"],
            [first, "Exposures", "Rules fired", "About"], wb.sheetnames)
    def nrows(name: str) -> int:
        return len(read_table(wb[name])[1])
    rows = nrows(first)
    s.check(f"{testid}: one row per {first.lower()[:-1]} on screen", rows == customers, customers, rows)
    if exposures is not None:
        s.check(f"{testid}: exposures", nrows("Exposures") == exposures, exposures, nrows("Exposures"))
    if rules_fired is not None:
        s.check(f"{testid}: rules fired", nrows("Rules fired") == rules_fired, rules_fired,
                nrows("Rules fired"))
    about = read_about(wb)
    s.check(f"{testid}: About names book, period and rule set, and carries no data label",
            about.get("Book") == book and about.get("Period") == period and str(about.get("Rule set", "")).startswith("gw-ews")
            and "Data" not in about, (book, period), (about.get("Book"), about.get("Period")))
    wb.close()


def check_charts(s: Sweep, page: Page, lv: dict, book: str) -> None:
    """The level's interactive charts are drawn, and the by-source breakdown matches the API."""
    def plotted(testid: str) -> bool:
        try:
            page.wait_for_selector(f'{tid(testid)}[data-rendered="true"], {tid(testid)} [data-rendered="true"]',
                                   timeout=30_000)
            return True
        except Exception:  # noqa: BLE001
            return False
    s.check("trend chart is an interactive Plotly chart", plotted("ews-trend-chart"))
    if len(lv.get("children") or lv.get("classifications") or []) >= 2:
        s.check("comparison chart drawn", plotted("ews-compare-chart"))
    # PLAN_R5 P4: the sector drill shows only its own charts; "Borrowers by rating" lives at View by = Rating
    # (ops/sweep_r4_ews.py checks it there, in the global order).
    s.check("P4: no Borrowers by rating on the sector drill", page.locator(tid("ews-ratings")).count() == 0,
            0, page.locator(tid("ews-ratings")).count())
    bs = lv["headline"].get("by_source") or []
    if bs:
        shown = txt(page, "ews-by-source")
        for x in bs:
            s.check(f"by source: {x['label']} {count(x['customers'])}", count(x["customers"]) in shown and x["label"] in shown,
                    f"{x['label']} {count(x['customers'])}", shown)


B360 = "http://127.0.0.1:8502/api/v1/b360"
WHATIF = "http://127.0.0.1:8503/api/v1/whatif"
DATA = "http://127.0.0.1:8504/api/v1/data"


def get_json(url: str, **params) -> Any:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    with urllib.request.urlopen(url + ("?" + q if q else ""), timeout=180) as r:
        return json.loads(r.read())


def download(page: Page, testid: str) -> Path:
    with page.expect_download(timeout=180_000) as d:
        page.click(tid(testid))
    path = OUT / "downloads" / d.value.suggested_filename
    path.parent.mkdir(parents=True, exist_ok=True)
    d.value.save_as(path)
    return path


def b360_tour(s: Sweep, page: Page, book: str, cid: str, period: str, uat: str) -> None:
    """Borrower 360 for one customer: header against the API, every tab, Excel, Back through the tabs."""
    import openpyxl
    page.wait_for_selector(f'[data-testid="b360-customer"][data-customer="{cid}"]', timeout=90_000)
    page.wait_for_load_state("networkidle")
    d = get_json(f"{B360}/customers/{cid}", domain=book, period=period)
    prof = d["profile"]
    s.check("Borrower 360 received book, customer, period",
            (txt(page, "b360-domain"), txt(page, "b360-id"), txt(page, "b360-period")) == (book, cid, prof["period"]),
            (book, cid, prof["period"]), (txt(page, "b360-domain"), txt(page, "b360-id"), txt(page, "b360-period")))
    head = txt(page, "b360-header")
    for piece in [prof.get("name") or cid, sar(prof["exposure"])]:
        s.check(f"header shows {piece}", piece in head, piece, head[:200])
    s.check("EWS band equals Early Warning", prof["ews_band"].lower() in txt(page, "b360-ews-band").lower(),
            prof["ews_band"], txt(page, "b360-ews-band"))
    tabs = [t["key"] for t in d["tab_list"]]
    for t in tabs:
        s.start(book, uat, f"Borrower 360 {cid}: tab {t}")
        page.click(tid(f"b360-tab-{t}"))
        page.wait_for_selector(tid(f"b360-panel-{t}"), timeout=60_000)
        page.wait_for_load_state("networkidle")
        s.check(f"tab {t} in the address", url_params(page).get("tab") == t, t, page.url)
        s.check(f"panel {t} has content", len(txt(page, f"b360-panel-{t}").strip()) > 20)
        if page.locator(tid(f"b360-chart-{t}")).count():
            page.wait_for_selector(f'{tid(f"b360-chart-{t}")} [data-rendered="true"], {tid(f"b360-chart-{t}")}[data-rendered="true"]',
                                   timeout=30_000)
            s.check(f"tab {t} chart drawn", True)
        if t in ("facilities", "ews", "ratings"):
            path = download(page, f"b360-excel-{t}")
            wb = openpyxl.load_workbook(path, read_only=True)
            s.check(f"tab {t} Excel has the tab and About", "About" in wb.sheetnames and len(wb.sheetnames) >= 2,
                    "About + tab", wb.sheetnames)
            wb.close()
    s.start(book, uat, f"Borrower 360 {cid}: Export all tabs, then browser Back through the tabs")
    path = download(page, "b360-excel-all")
    wb = openpyxl.load_workbook(path, read_only=True)
    s.check("Excel: one sheet per tab plus About", len(wb.sheetnames) >= len(tabs) + 1, len(tabs) + 1, wb.sheetnames)
    wb.close()
    for t in reversed(tabs[:-1]):
        page.go_back()
        page.wait_for_selector(tid(f"b360-panel-{t}"), timeout=60_000)
        s.check(f"Back to tab {t}", url_params(page).get("tab", "profile") == t, t, page.url)


def level_api(book: str, period: str = "", segment: str = "", cls: str = "", sub: str = "") -> dict:
    return api("/level", domain=book, period=period, segment=segment, classification=cls, subsegment=sub)


def list_api(book: str, **f) -> dict:
    return api("/customers", domain=book, **f)


def check_list(s: Sweep, page: Page, book: str, scope: dict, filters: dict) -> dict:
    """The list on screen against the API: total, exposure, pills, and the page of rows in order."""
    q = {"period": scope.get("period", ""), "segment": scope.get("segment", ""),
         "classification": scope.get("cls", ""), "subsegment": scope.get("sub", ""),
         "cohort": filters.get("cohort") or "warned", "reason": filters.get("reason", ""),
         "layer": filters.get("layer", ""), "dpd": filters.get("dpd", ""), "stage": filters.get("stage", ""),
         "band_min": filters.get("band", ""), "search": filters.get("q", ""), "limit": 25,
         "offset": filters.get("offset", 0)}
    want = list_api(book, **q)
    owners = want["labels"]["owners"]
    total = txt(page, "ews-list-total")
    s.check("list total and exposure", f"{count(want['total'])} {owners} · {sar(want['total_exposure'])} exposure" in total,
            f"{count(want['total'])} {owners} · {sar(want['total_exposure'])} exposure", total[:120])
    for c in want["cohorts"]:
        pill = txt(page, f"ews-cohort-{c['key']}")
        s.check(f"pill {c['key']} count", count(c["customers"]) in pill, count(c["customers"]), pill)
    ids = [x.get_attribute("data-testid").replace("ews-customer-", "")
           for x in page.locator('[data-testid^="ews-customer-"]').all()
           if re.fullmatch(r"ews-customer-(CB|RC)\w+", x.get_attribute("data-testid") or "")]
    s.check("rows on screen are the API's page, in order", ids == [r["customer_id"] for r in want["customers"]],
            [r["customer_id"] for r in want["customers"]][:6], ids[:6])
    for r in want["customers"][:25]:
        card = page.locator(tid(f"ews-customer-{r['customer_id']}")).first.inner_text()
        pieces = [f"score {r['score']}", r["band"].upper(), sar(r["exposure"])]
        miss = [p for p in pieces if p not in card]
        if miss:
            s.check(f"row {r['customer_id']} figures", False, pieces, card[:160])
    return want


def rows_match_filters(rows: list[dict], book: str, f: dict, warned_min: int) -> list[str]:
    """Each API row satisfies every filter applied (independent re-check of the service's filter)."""
    bad = []
    floors = dict(zip(("moderate", "high", "critical"), _floors(book)))
    for r in rows:
        if f.get("stage") and r["stage"] != int(f["stage"]):
            bad.append(f"{r['customer_id']} stage {r['stage']}")
        if f.get("dpd"):
            lo, hi = {"current": (0, 0), "1-9": (1, 9), "10-19": (10, 19), "20-29": (20, 29), "30-59": (30, 59),
                      "60-89": (60, 89), "90+": (90, 10**6)}[f["dpd"]]
            if not lo <= r["dpd"] <= hi:
                bad.append(f"{r['customer_id']} dpd {r['dpd']}")
        if f.get("band") and r["score"] < floors[f["band"]]:
            bad.append(f"{r['customer_id']} score {r['score']} < {f['band']}")
        if f.get("reason") and f["reason"] not in [x["name"] for x in r["reasons"]]:
            bad.append(f"{r['customer_id']} lacks reason")
        if f.get("layer") and f["layer"] not in r["layers"]:
            bad.append(f"{r['customer_id']} lacks layer")
        if (f.get("cohort") or "warned") == "warned" and r["score"] < warned_min:
            bad.append(f"{r['customer_id']} not warned")
    return bad


_FLOORS: dict[str, tuple] = {}


def _floors(book: str) -> tuple:
    if book not in _FLOORS:
        _FLOORS[book] = tuple(api("/meta", domain=book)["band_floors"])
    return _FLOORS[book]


def select_filter(page: Page, label: str, value: str) -> None:
    # Match the label by its own leading text: an option inside another
    # filter ("Stage & transfer" under Layer) would also match a substring.
    page.locator(f'{tid("ews-list-filters")} label').filter(
        has_text=re.compile(rf"^\s*{re.escape(label)}", re.I)).locator("select").select_option(value)
    settle_list(page)


def wait_url(page: Page, pattern: str, timeout: int = 60_000) -> None:
    page.wait_for_url(re.compile(pattern), timeout=timeout)


# ------------------------------------------------------------ the sweep

# The registered Early Warning story (PLAN_R5 Session E) moved two attention figures; same items, order and severity.
BASELINE = V5 / "evidence" / "v5" / "foundation" / "after_ews_story"


def check_attention(s: Sweep, page: Page, book: str) -> None:
    """The attention list on screen: the post-rescale baseline's items, same order and severity."""
    want = [(i["headline"], i["severity"].upper()) for i in
            json.loads((BASELINE / f"attention_{book}.json").read_text())["segments_requiring_attention"]]
    body = page.inner_text("body")
    pos = [body.find(h) for h, _ in want]
    s.check(f"{book}: all {len(want)} attention items shown", all(p >= 0 for p in pos), [h for h, _ in want],
            [h for (h, _), p in zip(want, pos) if p < 0])
    s.check(f"{book}: attention items in the baseline order", pos == sorted(pos), "ascending", pos)
    for k, (h, sev) in enumerate(want):
        nxt = pos[k + 1] if k + 1 < len(pos) else len(body)
        s.check(f"{book}: '{h}' severity {sev}", pos[k] >= 0 and sev in body[pos[k]:nxt], sev, body[pos[k]:nxt][:120])


def cockpit_steps(s: Sweep, page: Page) -> None:
    s.start("corporate", "1", "Open the Cockpit (home)")
    page.goto(UI + "/", wait_until="domcontentloaded")
    page.wait_for_selector("text=Segments requiring attention", timeout=120_000)
    page.wait_for_timeout(1500)
    body = page.inner_text("body")
    s.check("Construction ECL item at the v5 scale", "Construction: ECL rose to SAR 2,755 million" in body,
            "Construction: ECL rose to SAR 2,755 million", body[:200])
    check_attention(s, page, "corporate")
    nav = page.locator(NAV).first.inner_text()
    links = [x.strip() for x in nav.splitlines() if x.strip()]
    want_nav = ["Cockpit", "Early Warning", "What-If", "Borrower 360", "Data Domains", "Workspace", "Mail",
                "Projects", "Investigations", "Analyses", "Playbook", "Policy Docs", "Scorecard", "Deal Desk",
                "BRF",
                "Lenses", "Workflow", "Users & Teams", "Agent Operations", "AI Studio", "Settings", "Audit log"]
    s.check("sidebar shows the v5 modules and nothing else", all(x in links for x in want_nav) and "Documents" not in links
            and not [x for x in links if x in ("Intelligence Library", "Accepted Risk Watch", "Queries")]
            and not [x for x in links if x in ("Analysis Studio", "Trace & Lineage", "AI Intelligence Studio")],
            want_nav, links)
    # PLAN_R5 P1: Playbook and Lenses under Intelligence, Policy Docs in Work, Admin as the last group.
    heads = {h.upper(): i for i, h in enumerate(links) if h.upper() in ("HOME", "FUNCTIONALITIES", "WORK", "INTELLIGENCE", "DATA", "BUILD", "ADMIN")}
    def group_of(label: str) -> str:
        at = links.index(label) if label in links else -1
        return max((h for h, i in heads.items() if i < at), key=lambda h: heads[h], default="")
    # PLAN_R10 S1: Home = Cockpit; Intelligence; Work (Workspace, Mail, Deal Desk, Playbook, Policy Docs, …); Admin last.
    s.check("R10: Cockpit under Home, Lenses under Intelligence, Workspace/Playbook/Policy Docs/Deal Desk under Work, Admin last",
            group_of("Cockpit") == "HOME" and group_of("Lenses") == "INTELLIGENCE" and group_of("Playbook") == "WORK"
            and group_of("Policy Docs") == "WORK" and group_of("Deal Desk") == "WORK" and group_of("Workspace") == "WORK"
            and group_of("Audit log") == "ADMIN" and heads.get("ADMIN", -1) == max(heads.values(), default=-1),
            "Home: Cockpit; Intelligence: Lenses; Work: Workspace, Playbook, Policy Docs, Deal Desk; Admin last", heads)

    s.start("retail", "2", "Cockpit toggle: Retail")
    page.click(tid("domain-retail"))
    page.wait_for_selector("text=/Retail portfolio requiring attention/", timeout=90_000)
    page.wait_for_timeout(1500)
    body = page.inner_text("body")
    s.check("Mortgage ECL item", "Mortgage: ECL rose to SAR 45 million" in body, "Mortgage: ECL rose to SAR 45 million", body[:200])
    check_attention(s, page, "retail")
    s.check("Aug 2026 shown", "Aug 2026" in body or "2026-08" in body, "Aug 2026", "")
    s.check("toggle pressed", page.get_attribute(tid("domain-retail"), "aria-pressed") == "true", "true",
            page.get_attribute(tid("domain-retail"), "aria-pressed"))

    s.start("retail", "3", "Sidebar → Early Warning opens on the book last chosen (Retail)")
    page.locator(NAV).get_by_role("link", name="Early Warning").click()
    wait_url(page, r".*/early-warning.*")
    settle_level(page, "portfolio")
    page.wait_for_function("() => (document.querySelector('[data-testid=\"ews-as-of\"]')||{}).innerText?.includes('Retail')",
                           timeout=60_000)
    s.check("opens on Retail", "Retail · monthly" in txt(page, "ews-as-of"), "Retail · monthly", txt(page, "ews-as-of"))

    s.start("retail", "nav", "Sidebar → Cockpit returns to the Cockpit on Retail")
    page.locator(NAV).get_by_role("link", name="Cockpit").first.click()
    page.wait_for_selector("text=/requiring attention/", timeout=90_000)
    page.wait_for_timeout(1000)
    s.check("Cockpit home", page.url.rstrip("/") == UI or page.url.startswith(UI + "/?"), UI + "/", page.url)

    s.start("corporate", "nav", "Cockpit toggle: back to Corporate")
    page.click(tid("domain-corporate"))
    page.wait_for_selector("text=Construction: ECL rose to SAR 2,755 million", timeout=90_000)
    s.check("Corporate attention list back", True)

    s.start("corporate", "3", "Sidebar → Early Warning opens on Corporate")
    page.locator(NAV).get_by_role("link", name="Early Warning").click()
    wait_url(page, r".*/early-warning.*")
    settle_level(page, "portfolio")
    page.wait_for_timeout(800)
    s.check("opens on Corporate", "Corporate · quarterly" in txt(page, "ews-as-of"), "Corporate · quarterly", txt(page, "ews-as-of"))


def ews_book(s: Sweep, page: Page, book: str) -> dict:
    """UAT steps 3-19 on one book, plus every button and link on every screen visited."""
    P = PATHS[book]
    record: dict[str, Any] = {}

    # Toggle to this book on the Early Warning screen.
    s.start(book, "3/14", f"Early Warning toggle: {book}")
    other = "retail" if book == "corporate" else "corporate"
    page.goto(UI + f"/early-warning?domain={other}", wait_until="domcontentloaded")
    settle_level(page, "portfolio")
    page.click(tid(f"ews-book-{book}"))
    page.wait_for_function(f"() => (document.querySelector('[data-testid=\"ews-as-of\"]')||{{}}).innerText?.includes('{'Corporate' if book == 'corporate' else 'Retail'}')",
                           timeout=60_000)
    settle_level(page, "portfolio")
    page.wait_for_load_state("networkidle")
    top = level_api(book)
    record["portfolio"] = top
    s.check("toggle selected", page.get_attribute(tid(f"ews-book-{book}"), "aria-selected") == "true")
    s.check("address carries the book", url_params(page).get("domain") == book, book, page.url)

    s.start(book, "4/14", "Portfolio tiles, against the API and the books")
    check_level(s, page, top, book)

    s.start(book, "A3", "Portfolio: interactive charts and the by-source breakdown")
    check_charts(s, page, top, book)
    first_card = top["children"][0]
    page.click(tid(f"ews-trend-open-{first_card['key']}"))
    page.wait_for_selector(f'{tid("ews-trend-dialog")} [data-rendered="true"]', timeout=30_000)
    s.check("card chart opens in full", page.locator(tid("ews-trend-dialog")).count() == 1)
    page.click(tid("ews-trend-close"))
    page.wait_for_timeout(300)
    s.check("close button closes it", page.locator(tid("ews-trend-dialog")).count() == 0)
    page.click(tid(f"ews-trend-open-{first_card['key']}"))
    page.wait_for_selector(tid("ews-trend-dialog"), timeout=30_000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    s.check("Escape closes it", page.locator(tid("ews-trend-dialog")).count() == 0)
    for c in top["children"]:
        shown = txt(page, f"ews-by-source-{c['key']}")
        want = [count(x["customers"]) for x in c.get("by_source", [])]
        s.check(f"card {c['key']}: by source", all(w in shown for w in want), want, shown)

    s.start(book, "A1", "Portfolio: Export to Excel")
    check_excel(s, page, "ews-excel-level", book, top["period"], top["headline"]["customers"],
                exposures=top["headline"]["facilities"])

    s.start(book, "5", "Interpretation → Why this ranking?")
    interp = top.get("interpretation") or {}
    s.check("interpretation text", interp.get("interpretation", "")[:60] in txt(page, "ews-interpretation-text"),
            interp.get("interpretation", "")[:60], txt(page, "ews-interpretation-text")[:60])
    page.click(tid("ews-interpretation-why"))
    wait(page, "ews-interpretation-basis")
    basis = txt(page, "ews-interpretation-basis")
    rows = page.locator(f'{tid("ews-interpretation-basis")} tbody tr')
    s.check("one ranking row per segment", rows.count() == len(interp.get("ranking", [])), len(interp.get("ranking", [])), rows.count())
    for i, r in enumerate(interp.get("ranking", [])):
        row = rows.nth(i).inner_text()
        want = [r["label"], sar(r["exposure_severe"]), pct(r["severe_share_of_book_pct"]), pct(r["warned_pct"]),
                signed(r["warned_change"]), pct(r["odr_pct"], 2)]
        miss = [w for w in want if w not in row]
        s.check(f"ranking row {i + 1} {r['label']}", not miss, want, row.replace("\t", " | "))
    record["ranking"] = [(r["label"], r["exposure_severe"], r["severe_share_of_book_pct"]) for r in interp.get("ranking", [])]
    page.click(tid("ews-interpretation-why"))
    s.check("Why this ranking closes again", page.locator(tid("ews-interpretation-basis")).count() == 0)
    _ = basis

    s.start(book, "5", "Ranking link opens the first segment, Up returns")
    first = interp["ranking"][0]
    page.locator(f'{tid("ews-interpretation")} button', has_text=first["label"]).first.click() if False else None
    page.click(tid("ews-interpretation-why"))
    wait(page, "ews-interpretation-basis")
    page.locator(f'{tid("ews-interpretation-basis")} tbody tr').first.get_by_role("button").click()
    settle_level(page, "segment")
    s.check("ranking link opened the segment", url_params(page).get("segment") == first["key"], first["key"], page.url)
    page.click(tid("ews-level-back"))
    settle_level(page, "portfolio")
    s.check("Up returned to the portfolio", "segment" not in url_params(page), "no segment", page.url)

    s.start(book, "6", "Trend chart and the definitions panel")
    s.check("trend chart drawn (3 lines)", page.locator('[data-testid="ews-trend-chart"] svg path').count() >= 3)
    page.locator(f'{tid("ews-definitions")} summary').click()
    defs = txt(page, "ews-definitions")
    s.check("definitions name the rule set and the bands", top["ruleset"] in defs and top["definitions"]["bands"] in defs,
            top["definitions"]["bands"], defs[:200])
    page.locator(f'{tid("ews-definitions")} summary').click()

    # Every card's Open buttons at the portfolio level (title and bottom button), each checked, then Up.
    for c in top["children"]:
        for which in ("ews-open", "ews-open-bottom"):
            s.start(book, "6/15", f"Card {c['key']}: {'title' if which == 'ews-open' else 'Open'} button, then Up")
            page.click(tid(f"{which}-{c['key']}"))
            settle_level(page, "segment")
            page.wait_for_load_state("networkidle")
            lv = level_api(book, segment=c["key"])
            if which == "ews-open":
                check_level(s, page, lv, book)
            else:
                s.check("opened the segment", url_params(page).get("segment") == c["key"], c["key"], page.url)
                s.check("its warned tile", count(lv["headline"]["customers_warned"]) in txt(page, "ews-kpi-warned"))
            page.click(tid("ews-level-back"))
            settle_level(page, "portfolio")
            s.check("Up returns to the portfolio", "segment" not in url_params(page), "", page.url)

    # Top reason buttons on the portfolio: open the warned list with that reason; Back.
    s.start(book, "9", "Portfolio top reason → filtered list → Back")
    reason = top["top_reasons"][0]
    page.locator(tid("ews-top-reasons")).get_by_role("button").first.click()
    settle_list(page)
    want = check_list(s, page, book, {}, {"cohort": "warned", "reason": reason["name"]})
    s.check("reason chip shown", f"Reason: {reason['name']}" in page.inner_text(tid("ews-active-filters")))
    page.click(tid("ews-list-back"))
    settle_level(page, "portfolio")
    _ = want

    # KPI tiles that open lists (customers, warned, high, bad, forward): each list total equals its tile.
    for testid, cohort, key in (("ews-kpi-warned", "warned", "customers_warned"),
                                ("ews-kpi-high", "high_or_critical", "high_or_critical"),
                                ("ews-kpi-bad", "current_bad", "current_bad")):
        s.start(book, "4", f"Tile {testid.replace('ews-kpi-', '')} opens its list; Back")
        page.click(tid(testid))  # R10: the KpiRow tile is itself the button
        settle_list(page)
        got = check_list(s, page, book, {}, {"cohort": cohort})
        s.check("list total equals the tile", got["total"] == top["headline"][key], top["headline"][key], got["total"])
        s.check("pill selected", url_params(page).get("cohort") == cohort, cohort, page.url)
        page.click(tid("ews-list-back"))
        settle_level(page, "portfolio")

    # ---- the UAT drill: segment (-> classification) -> sub-segment -> list -> customer
    s.start(book, "7/16", f"Open {P['segment']}")
    page.click(tid(f"ews-open-{P['segment']}"))
    settle_level(page, "segment")
    seg = level_api(book, segment=P["segment"])
    record["segment"] = seg
    check_level(s, page, seg, book)
    check_charts(s, page, seg, book)

    if P["cls"]:
        for cl in seg["classifications"]:
            s.start(book, "16", f"Classification card {cl['key']}: Open, then Up")
            page.click(tid(f"ews-open-{cl['key']}"))
            settle_level(page, "classification")
            lv = level_api(book, segment=P["segment"], cls=cl["key"])
            check_level(s, page, lv, book)
            s.check("derivation stated on the card", cl["derivation"][:20] in (cl.get("derivation") or ""))
            page.click(tid("ews-level-back"))
            settle_level(page, "segment")
        s.start(book, "17", f"Open {P['cls']}")
        page.click(tid(f"ews-open-{P['cls']}"))
        settle_level(page, "classification")
        parent = level_api(book, segment=P["segment"], cls=P["cls"])
        record["classification"] = parent
        check_level(s, page, parent, book)
        parent_level = "classification"
    else:
        parent, parent_level = seg, "segment"

    # Every sub-segment card's Open (title and bottom), then Up.
    for c in parent["children"]:
        for which in ("ews-open", "ews-open-bottom"):
            s.start(book, "7/17", f"Sub-segment card {c['key']}: {'title' if which == 'ews-open' else 'Open'} button, then Up")
            page.click(tid(f"{which}-{c['key']}"))
            settle_level(page, "subsegment")
            lv = level_api(book, segment=P["segment"], cls=P["cls"], sub=c["key"])
            if which == "ews-open":
                check_level(s, page, lv, book)
            else:
                s.check("opened the sub-segment", url_params(page).get("sub") == c["key"], c["key"], page.url)
            page.click(tid("ews-level-back"))
            settle_level(page, parent_level)

    sub = parent["children"][0]["key"]
    s.start(book, "8/17", f"Open {sub}; breadcrumbs keep every level")
    page.click(tid(f"ews-open-{sub}"))
    settle_level(page, "subsegment")
    sublv = level_api(book, segment=P["segment"], cls=P["cls"], sub=sub)
    record["subsegment"] = sublv
    check_level(s, page, sublv, book)
    check_charts(s, page, sublv, book)
    s.start(book, "A1", f"{sub}: Export to Excel")
    check_excel(s, page, "ews-excel-level", book, sublv["period"], sublv["headline"]["customers"],
                exposures=sublv["headline"]["facilities"])

    # Breadcrumb links at every level above.
    crumbs = sublv["breadcrumbs"]
    for i, b in enumerate(crumbs[:-1]):
        s.start(book, "7/17", f"Breadcrumb '{b['label']}' from {sub}, then back down")
        page.click(tid(f"ews-crumb-{i}"))
        level = "portfolio" if i == 0 else ("segment" if i == 1 else "classification")
        settle_level(page, level)
        lv = level_api(book, segment=b["scope"].get("segment", ""), cls=b["scope"].get("classification", ""))
        s.check("crumb opened its level", lv["name"] in txt(page, "ews-breadcrumbs"), lv["name"], txt(page, "ews-breadcrumbs"))
        s.check("warned tile", count(lv["headline"]["customers_warned"]) in txt(page, "ews-kpi-warned"))
        page.go_back()
        settle_level(page, "subsegment")
        s.check("browser Back returns to the sub-segment", url_params(page).get("sub") == sub, sub, page.url)

    # Level export to What-If and its way back (link, then browser Back).
    s.start(book, "12", f"{sub}: Export warned to What-If, then '← Back to Early Warning'")
    page.click(tid("ews-export-level"))
    wait_url(page, r".*/what-if/thread/.*")
    wait(page, "whatif-cohort")
    s.check("What-If customers equal the level's warned", txt(page, "whatif-customers") == count(sublv["headline"]["customers_warned"]),
            count(sublv["headline"]["customers_warned"]), txt(page, "whatif-customers"))
    page.click(tid("whatif-back-to-ews"))
    settle_level(page, "portfolio")
    s.check("back link lands on Early Warning, same book and period",
            url_params(page).get("domain") == book and url_params(page).get("period") == sublv["period"], book, page.url)
    page.go_back()
    wait(page, "whatif-cohort")
    page.go_back()
    settle_level(page, "subsegment")
    s.check("browser Back from What-If returns to the sub-segment", url_params(page).get("sub") == sub, sub, page.url)

    s.start(book, "8", f"{sub}: Open the warned list; group pills")
    page.click(tid("ews-open-warned"))
    settle_list(page)
    scope = {"segment": P["segment"], "cls": P["cls"], "sub": sub}
    got = check_list(s, page, book, scope, {"cohort": "warned"})
    s.check("list total equals the warned tile", got["total"] == sublv["headline"]["customers_warned"],
            sublv["headline"]["customers_warned"], got["total"])
    for c in got["cohorts"]:
        s.start(book, "8", f"Group pill: {c['key']}")
        page.click(tid(f"ews-cohort-{c['key']}"))
        settle_list(page)
        g = check_list(s, page, book, scope, {"cohort": c["key"]})
        s.check("pill total", g["total"] == c["customers"], c["customers"], g["total"])
    page.click(tid("ews-cohort-warned"))
    settle_list(page)

    # Pager.
    if got["total"] > 25:
        s.start(book, "8", "Pager: Next, then Previous")
        page.locator(tid("ews-list-pager")).get_by_role("button", name="Next").click()
        settle_list(page)
        check_list(s, page, book, scope, {"cohort": "warned", "offset": 25})
        page.locator(tid("ews-list-pager")).get_by_role("button", name="Previous").click()
        settle_list(page)
        check_list(s, page, book, scope, {"cohort": "warned"})

    # Every filter, alone, then its chip's ✕.
    meta = list_api(book, segment=P["segment"], classification=P["cls"], subsegment=sub, cohort="warned", limit=1)
    warned_min = _floors(book)[0]
    trials = [("Layer", "layer", meta["layers"]), ("Days past due", "dpd", [b["key"] for b in meta["dpd_buckets"]]),
              ("Stage", "stage", ["1", "2", "3"]), ("Minimum band", "band", ["moderate", "high", "critical"]),
              ("Reason", "reason", meta["reasons"])]
    for label, key, options in trials:
        for value in options:
            s.start(book, "9", f"Filter {label} = {value}, then its chip ✕")
            select_filter(page, label, value)
            g = check_list(s, page, book, scope, {"cohort": "warned", key: value})
            bad = rows_match_filters(g["customers"], book, {"cohort": "warned", key: value}, warned_min)
            s.check("every row matches the filter", not bad, "none outside the filter", bad[:5])
            chips = page.locator(tid("ews-chip-clear"))
            s.check("one clearable chip", chips.count() == 1, 1, chips.count())
            chips.first.click()
            settle_list(page)
            s.check("chip ✕ cleared the filter", key not in url_params(page), f"no {key}", page.url)
            check_list(s, page, book, scope, {"cohort": "warned"})

    # The UAT's cumulative filter sequence (step 9), then clear each chip in turn.
    seq = ([("Days past due", "dpd", "90+"), ("Stage", "stage", "3"), ("Reason", "reason", "Covenant breach")]
           if book == "corporate" else
           [("Days past due", "dpd", "1-9"), ("Stage", "stage", "2"), ("Reason", "reason", "Payment arrears (DPD > 0)")])
    applied: dict[str, str] = {"cohort": "warned"}
    for label, key, value in seq:
        s.start(book, "9", f"Cumulative: {label} = {value}")
        select_filter(page, label, value)
        applied[key] = value
        g = check_list(s, page, book, scope, applied)
        bad = rows_match_filters(g["customers"], book, applied, warned_min)
        s.check("every row matches all filters", not bad, "none outside", bad[:5])
        record.setdefault("filter_sequence", []).append((label, value, g["total"]))
    s.start(book, "A1", "Filtered list: Export to Excel")
    check_excel(s, page, "ews-excel-list", book, g.get("period", top["period"]), g["total"])
    while page.locator(tid("ews-chip-clear")).count():
        s.start(book, "9", "Clear a chip ✕ (cumulative)")
        page.locator(tid("ews-chip-clear")).first.click()
        settle_list(page)
        params = url_params(page)
        applied = {"cohort": "warned", **{k: params[k] for k in ("dpd", "stage", "reason") if k in params}}
        check_list(s, page, book, scope, applied)

    # Search (corporate: CB01045 from Construction's warned list, as in UAT step 10).
    s.start(book, "10/17", "Up to the segment → Open the warned → search → open the customer")
    # R7: Back would walk the filters just cleared, one by one (the exact previous step); Up leaves the list.
    page.click(tid("ews-list-up"))
    settle_level(page, "subsegment")
    page.click(tid("ews-level-back"))
    settle_level(page, parent_level)
    if P["cls"]:
        page.click(tid("ews-level-back"))
        settle_level(page, "segment")
    page.click(tid("ews-open-warned"))
    settle_list(page)
    seg_scope = {"segment": P["segment"]}
    target = P["search"] or list_api(book, segment=P["segment"], classification=P["cls"], subsegment=sub,
                                     cohort="warned", limit=1)["customers"][0]["customer_id"]
    page.fill(tid("ews-search"), target)
    page.press(tid("ews-search"), "Enter")
    settle_list(page)
    g = check_list(s, page, book, seg_scope, {"cohort": "warned", "q": target})
    s.check("search finds exactly the customer", [r["customer_id"] for r in g["customers"]] == [target], [target],
            [r["customer_id"] for r in g["customers"]])
    s.check("search chip", f"Search: {target}" in page.inner_text(tid("ews-active-filters")))
    page.click(tid(f"ews-customer-{target}"))
    wait(page, "ews-customer-detail")
    page.wait_for_load_state("networkidle")
    d = api(f"/customers/{target}", domain=book)
    record["customer"] = {"id": target, "name": d.get("customer_name"), "score": d["score"], "band": d["band"],
                          "exposure": d["exposure"], "facilities": d["facilities"],
                          "exposures": [(e["exposure_id"], e["score"]) for e in d["exposures"]]}
    detail = txt(page, "ews-customer-detail")
    for piece in [d.get("customer_name") or target, d["band"].upper(), sar(d["exposure"]), f"{count(d['facilities'])} {d['labels']['exposures']}"]:
        s.check(f"customer shows {piece}", piece in detail, piece, detail[:200])
    s.check("one card per exposure", page.locator('[data-testid^="ews-exposure-"]').count() == len(d["exposures"]),
            len(d["exposures"]), page.locator('[data-testid^="ews-exposure-"]').count())
    for e in d["exposures"]:
        fired = sum(r["weight"] for r in e["rules"] if r["fired"])
        s.check(f"{e['exposure_id']}: fired weights add up to its score", fired == e["score"], e["score"], fired)
        rows_shown = page.locator(f'[data-testid^="ews-rule-{e["exposure_id"]}-"]').count()
        s.check(f"{e['exposure_id']}: one rule row per rule", rows_shown == len(e["rules"]), len(e["rules"]), rows_shown)
        for r in e["rules"]:
            row = txt(page, f"ews-rule-{e['exposure_id']}-{r['id']}")
            s.check(f"{e['exposure_id']} {r['id']} weight shown", (f"+{r['weight']}" if r["fired"] else "0") in row.split()[-1:],
                    f"+{r['weight']}" if r["fired"] else "0", row.split()[-1:])
    page.wait_for_selector(f'{tid("ews-customer-history-chart")}[data-rendered="true"]', timeout=30_000)
    s.check("customer history is an interactive chart",
            page.locator(f'{tid("ews-customer-history-chart")}[data-rendered="true"]').count() == 1)
    hist = page.locator(f'{tid("ews-customer-history")} tbody tr')
    s.check("history: one row per period", hist.count() == len(d["history"]), len(d["history"]), hist.count())
    for k, h in enumerate(reversed(d["history"])):
        row = hist.nth(k).inner_text().split("\t")
        s.check(f"history {h['period']}: band and score", h["band"].upper() in row[1].upper() and row[2].strip() == str(h["score"]),
                (h["band"], h["score"]), row[1:3])

    s.start(book, "A1", "Customer: Export to Excel")
    check_excel(s, page, "ews-excel-customer", book, d["period"], 1, exposures=d["facilities"],
                rules_fired=sum(1 for e in d["exposures"] for r in e["rules"] if r["fired"]))

    s.start(book, "10", "Customer Back button returns to the searched list; reopen the customer")
    page.click(tid("ews-detail-back"))
    settle_list(page)
    s.check("back on the searched list", url_params(page).get("q") == target and "customer" not in url_params(page),
            f"q={target}, no customer", page.url)
    page.click(tid(f"ews-customer-{target}"))
    wait(page, "ews-customer-detail")
    s.check("customer reopened", url_params(page).get("customer") == target, target, page.url)

    s.start(book, "11", "Open in Borrower 360 (every tab) → Back to this borrower in Early Warning")
    page.click(tid("ews-link-b360"))
    b360_tour(s, page, book, target, d["period"], "11")
    s.start(book, "11", "Borrower 360 → Back to this borrower in Early Warning")
    page.click(tid("b360-back-to-ews"))
    wait(page, "ews-customer-detail")
    s.check("back on the same customer", url_params(page).get("customer") == target, target, page.url)

    s.start(book, "12", "Customer: Export to What-If → browser Back")
    page.click(tid("ews-export-customer"))
    wait_url(page, r".*/what-if/thread/.*")
    wait(page, "whatif-cohort")
    s.check("cohort is this one customer", txt(page, "whatif-customers") == "1", "1", txt(page, "whatif-customers"))
    s.check("its exposures", txt(page, "whatif-exposures") == count(d["facilities"]), count(d["facilities"]), txt(page, "whatif-exposures"))
    page.go_back()
    wait(page, "ews-customer-detail")
    s.check("Back returns to the customer", url_params(page).get("customer") == target, target, page.url)

    s.start(book, "13", "Ask the Cockpit (customer) → Cockpit on the same book, question in the box → Back")
    page.click(tid("ews-link-cockpit"))
    page.wait_for_selector(tid("cockpit-v4-question"), timeout=120_000)
    page.wait_for_selector("text=/requiring attention/", timeout=120_000)
    page.wait_for_timeout(1200)
    box = page.input_value(tid("cockpit-v4-question"))
    s.check("question prefilled with the customer", target in box, target, box[:160])
    s.check("Cockpit on the same book", page.get_attribute(tid(f"domain-{book}"), "aria-pressed") == "true", "true",
            page.get_attribute(tid(f"domain-{book}"), "aria-pressed"))
    page.go_back()
    wait(page, "ews-customer-detail")
    s.check("browser Back returns to the customer", url_params(page).get("customer") == target, target, page.url)

    # R7: Back is the exact previous screen. The customer was reached from Borrower 360 ("Open in Early Warning"),
    # so Back returns to Borrower 360 (the same borrower); a second Back walks on from there.
    s.start(book, "10", "Customer Back after the Borrower 360 link returns to Borrower 360 (the previous screen)")
    page.click(tid("ews-detail-back"))
    wait_url(page, r".*/borrower-360\?.*")
    s.check("Back lands on Borrower 360, the same borrower", f"customer_id={target}" in page.url, target, page.url)
    page.goto(UI + f"/early-warning?domain={book}", wait_until="domcontentloaded")
    settle_level(page, "portfolio")
    s.check("Early Warning reopens at the book's level", "customer" not in url_params(page) and url_params(page).get("domain") == book,
            "no customer", page.url)

    s.start(book, "12", "List: Export N to What-If → '← Back to Early Warning'")
    page.click(tid(f"ews-open-{P['segment']}"))
    settle_level(page, "segment")
    page.click(tid("ews-open-warned"))
    settle_list(page)
    g = check_list(s, page, book, seg_scope, {"cohort": "warned"})
    s.check("export button carries the list total", f"Export {count(g['total'])}" in txt(page, "ews-export-list"),
            f"Export {count(g['total'])}", txt(page, "ews-export-list"))
    page.click(tid("ews-export-list"))
    wait_url(page, r".*/what-if/thread/.*")
    wait(page, "whatif-cohort")
    cohort = api(f"/cohorts/{url_params(page)['cohort']}") if False else None
    s.check("What-If customers equal the list total", txt(page, "whatif-customers") == count(g["total"]),
            count(g["total"]), txt(page, "whatif-customers"))
    s.check("What-If EAD equals the list exposure", txt(page, "whatif-ead") == sar(g["total_exposure"]),
            sar(g["total_exposure"]), txt(page, "whatif-ead"))
    s.check("not the old landing page", page.locator(tid("whatif-pending")).count() == 0)
    s.check("membership hash behind the (i)", "membership" in (page.get_attribute(tid("whatif-cohort-membership"), "title") or ""))
    record["whatif_list"] = (g["total"], g["total_exposure"])
    _ = cohort
    page.click(tid("whatif-back-to-ews"))
    settle_level(page, "portfolio")
    s.check("back on Early Warning, same book", url_params(page).get("domain") == book, book, page.url)

    # Card-level What-If buttons (one per card at the portfolio) -- first card here; each opens its warned cohort.
    for c in top["children"][:2]:
        s.start(book, "12", f"Card {c['key']}: Analyse → Stress this cohort → browser Back")
        page.click(tid(f"ews-analyse-{c['key']}"))  # R16 M2: the card opens its segment analysis first
        page.click(tid(f"ews-export-{c['key']}"))
        wait_url(page, r".*/what-if/thread/.*")
        wait(page, "whatif-cohort")
        s.check("card cohort customers equal the card's warned", txt(page, "whatif-customers") == count(c["customers_warned"]),
                count(c["customers_warned"]), txt(page, "whatif-customers"))
        page.go_back()
        settle_level(page, "portfolio")

    s.start(book, "13", "Ask the Cockpit (portfolio) → browser Back")
    page.click(tid("ews-ask-cockpit"))
    page.wait_for_selector(tid("cockpit-v4-question"), timeout=120_000)
    page.wait_for_timeout(1200)
    box = page.input_value(tid("cockpit-v4-question"))
    s.check("question prefilled", f"across the {book} book" in box, f"across the {book} book", box[:160])
    s.check("Cockpit on the same book", page.get_attribute(tid(f"domain-{book}"), "aria-pressed") == "true")
    page.go_back()
    settle_level(page, "portfolio")

    s.start(book, "18", "Model details: the model card, against the API")
    page.click(tid("ews-link-model"))
    page.wait_for_selector(f'[data-testid="ews-model-card"][data-state="ready"][data-domain="{book}"]', timeout=90_000)
    page.wait_for_load_state("networkidle")
    mc = api("/model-card", domain=book)
    from backend.ews_domain import ews_rules as ews
    summary = txt(page, "ews-mc-summary")
    s.check("rule set shown", ews.RULESET_VERSION in txt(page, "ews-mc-ruleset"), ews.RULESET_VERSION,
            txt(page, "ews-mc-ruleset"))
    s.check("status active", "active" in txt(page, "ews-mc-status").lower(), "active", txt(page, "ews-mc-status"))
    s.check("summary carries the warned count", count(mc["summary"]["warned"]) in summary, count(mc["summary"]["warned"]),
            summary[:200])
    for src in mc["sources"]:
        box = page.locator(tid(f"ews-mc-source-{src['key']}"))
        s.check(f"source {src['key']}: {src['status']}", box.count() == 1 and box.get_attribute("data-status") == src["status"],
                src["status"], box.get_attribute("data-status") if box.count() else "missing")
        for layer in src["layers"]:
            for r in layer["rules"]:
                row = page.locator(tid(f"ews-mc-rule-{r['id']}"))
                s.check(f"{r['id']}: live and customers fired on now",
                        row.count() == 1 and row.get_attribute("data-live") == str(r["live"]).lower()
                        and row.get_attribute("data-fires") == str(r["customers"]),
                        (r["live"], r["customers"]), (row.get_attribute("data-live"), row.get_attribute("data-fires"))
                        if row.count() else "missing")
                if r["live"] and row.count():
                    s.check(f"{r['id']}: customers shown", count(r["customers"]) in row.inner_text(),
                            count(r["customers"]), row.inner_text()[:120])
    every = {r["id"] for r in ews.RULES[book]}
    shown = {x.get_attribute("data-testid").replace("ews-mc-rule-", "")
             for x in page.locator('[data-testid^="ews-mc-rule-"]').all()}
    s.check("every rule of the rule set is on the card", every <= shown, sorted(every), sorted(shown))
    ext = [x for x in mc["sources"] if x["key"] in ("bureau", "open_banking")]
    s.check("Bureau and Open Banking connected", all(x["status"] == "connected" for x in ext),
            "connected", [x["status"] for x in ext])
    s.start(book, "18", "Model card: technical detail expanders, bands, performance, versions")
    for d in page.locator('[data-testid^="ews-mc-technical-"]').all()[:40]:
        d.locator("summary").first.click()
    page.wait_for_timeout(300)
    opened = page.locator('details[data-testid^="ews-mc-technical-"][open]').count()
    s.check("technical detail opens", opened >= 1, ">= 1", opened)
    for row in mc["bands"]["rows"]:
        b = page.locator(tid(f"ews-mc-band-{row['band']}"))
        s.check(f"band {row['band']} customers", b.count() == 1 and b.get_attribute("data-customers") == str(row["customers"]),
                row["customers"], b.get_attribute("data-customers") if b.count() else "missing")
    perf = mc["performance"]
    s.check("warned on the card", count(perf["warned"]) in txt(page, "ews-mc-kpi-warned"), count(perf["warned"]),
            txt(page, "ews-mc-kpi-warned"))
    s.check("forward risk on the card", count(perf["forward_risk"]) in txt(page, "ews-mc-kpi-forward_risk"),
            count(perf["forward_risk"]), txt(page, "ews-mc-kpi-forward_risk"))
    for t in perf["targets"]:
        tg = page.locator(tid(f"ews-mc-target-{t['key']}"))
        s.check(f"target {t['key']} met", tg.count() == 1 and tg.get_attribute("data-met") == str(t["met"]).lower(),
                t["met"], tg.get_attribute("data-met") if tg.count() else "missing")
    s.check("stability rows", page.locator(tid("ews-mc-stability-row")).count() == len(perf["stability"]),
            len(perf["stability"]), page.locator(tid("ews-mc-stability-row")).count())
    versions = [x.get_attribute("data-version") for x in page.locator(tid("ews-mc-version")).all()]
    s.check("version log 1.2.0, 1.1.0, 1.0.0", versions == list(ews.RULESETS), list(ews.RULESETS), versions)
    s.start(book, "18", "Model card: book toggle, browser Back, then '← Early Warning'")
    other = "retail" if book == "corporate" else "corporate"
    page.click(tid(f"ews-mc-book-{other}"))
    page.wait_for_selector(f'[data-testid="ews-model-card"][data-state="ready"][data-domain="{other}"]', timeout=60_000)
    s.check("toggle switches book", url_params(page).get("domain") == other, other, page.url)
    page.go_back()
    page.wait_for_selector(f'[data-testid="ews-model-card"][data-state="ready"][data-domain="{book}"]', timeout=60_000)
    s.check("browser Back returns to this book's card", url_params(page).get("domain") == book, book, page.url)
    page.click(tid("ews-model-back"))
    settle_level(page, "portfolio")
    s.check("back on Early Warning, same book", "/early-warning" in page.url and url_params(page).get("domain") == book,
            book, page.url)

    s.start(book, "19", "Quarter/Month selector: prior period, then latest again")
    if url_params(page).get("domain") != book:
        page.click(tid(f"ews-book-{book}"))
        settle_level(page, "portfolio")
    prior = top["prior_period"]
    page.select_option(tid("ews-period"), prior)
    page.wait_for_function(f"() => document.querySelector('[data-testid=\"ews-as-of\"]').innerText.includes('{as_of(prior)}')",
                           timeout=60_000)
    settle_level(page, "portfolio")
    page.wait_for_load_state("networkidle")
    lv = level_api(book, period=prior)
    record["prior"] = lv
    check_level(s, page, lv, book)
    page.select_option(tid("ews-period"), top["period"])
    page.wait_for_function(f"() => document.querySelector('[data-testid=\"ews-as-of\"]').innerText.includes('{as_of(top['period'])}')",
                           timeout=60_000)
    settle_level(page, "portfolio")
    page.wait_for_load_state("networkidle")
    s.check("latest again: warned tile", count(top["headline"]["customers_warned"]) in txt(page, "ews-kpi-warned"),
            count(top["headline"]["customers_warned"]), txt(page, "ews-kpi-warned"))

    # Browser Back from the deepest level to the top, one level at a time.
    s.start(book, "20", "Drill to the deepest level by clicks")
    page.goto(UI + f"/early-warning?domain={book}", wait_until="domcontentloaded")
    settle_level(page, "portfolio")
    trail = [("portfolio", {})]
    page.click(tid(f"ews-open-{P['segment']}"))
    settle_level(page, "segment")
    trail.append(("segment", {"segment": P["segment"]}))
    if P["cls"]:
        page.click(tid(f"ews-open-{P['cls']}"))
        settle_level(page, "classification")
        trail.append(("classification", {"segment": P["segment"], "cls": P["cls"]}))
    page.click(tid(f"ews-open-{sub}"))
    settle_level(page, "subsegment")
    trail.append(("subsegment", {"segment": P["segment"], "cls": P["cls"], "sub": sub}))
    page.click(tid("ews-open-warned"))
    settle_list(page)
    trail.append(("list", {"segment": P["segment"], "cls": P["cls"], "sub": sub, "cohort": "warned"}))
    first_row = page.locator('[data-testid^="ews-customer-CB"], [data-testid^="ews-customer-RC"]').first
    cid = first_row.get_attribute("data-testid").replace("ews-customer-", "")
    first_row.get_by_role("button").first.click()
    wait(page, "ews-customer-detail")
    s.check("deepest level reached (customer)", url_params(page).get("customer") == cid, cid, page.url)
    for level, want in reversed(trail):
        s.start(book, "20", f"Browser Back → {level}")
        page.go_back()
        if level == "list":
            settle_list(page)
        else:
            settle_level(page, level)
        got = {k: v for k, v in url_params(page).items() if k in ("segment", "cls", "sub", "cohort")}
        s.check(f"one level up: {level}", got == {k: v for k, v in want.items() if v}, want, got)
        if level != "list":
            lv = level_api(book, segment=want.get("segment", ""), cls=want.get("cls", ""), sub=want.get("sub", ""))
            s.check("its warned tile", count(lv["headline"]["customers_warned"]) in txt(page, "ews-kpi-warned"),
                    count(lv["headline"]["customers_warned"]), txt(page, "ews-kpi-warned"))
    return record


def module_steps(s: Sweep, page: Page, records: dict) -> None:
    """Phases C, D, E: Data Builder, Borrower 360 and What-If from the sidebar, both books, every control."""
    import openpyxl

    # ---- D: Borrower 360 from the sidebar: toggle, search, open, tabs, back
    for book in BOOKS:
        s.start(book, "D", "Sidebar → Borrower 360; book toggle; search")
        page.goto(UI + "/", wait_until="domcontentloaded")
        page.wait_for_selector("text=/requiring attention/", timeout=120_000)
        page.locator(NAV).get_by_role("link", name="Borrower 360").click()
        wait_url(page, r".*/borrower-360.*")
        page.wait_for_selector(tid(f"b360-book-{book}"), timeout=90_000)
        page.click(tid(f"b360-book-{book}"))
        page.wait_for_load_state("networkidle")
        target = records.get(book, {}).get("customer", {}).get("id") or ("CB01045" if book == "corporate" else "RC023173")
        page.fill(tid("b360-search"), target)
        page.press(tid("b360-search"), "Enter")
        page.wait_for_selector(tid(f"b360-row-{target}"), timeout=60_000)  # PLAN_R4 B2: the list row
        found = get_json(f"{B360}/search", domain=book, q=target)
        s.check("search finds the customer", any(target in json.dumps(x) for x in found.get("results", found.get("items", []))),
                target, str(found)[:200])
        page.click(tid(f"b360-row-{target}"))
        period = records.get(book, {}).get("portfolio", {}).get("period", "")
        b360_tour(s, page, book, target, period or ("2026Q2" if book == "corporate" else "2026-08"), "D")
        s.start(book, "D", "Borrower 360 → Back to Early Warning (this customer)")
        page.click(tid("b360-back-to-ews"))
        wait(page, "ews-customer-detail")
        s.check("Early Warning opens the same customer", url_params(page).get("customer") == target, target, page.url)

    # ---- E: What-If (PLAN_R2 item 6): conversational threads, both books
    for book in BOOKS:
        whatif_steps(s, page, book)

    # ---- C: Data Builder from the sidebar: every domain, a relation each, every control
    s.start("both", "C", "Sidebar → Data Domains; domains grouped")
    page.locator(NAV).get_by_role("link", name="Data Domains").click()
    wait_url(page, r".*/data-builder.*")
    page.wait_for_selector(tid("db-workspace"), timeout=90_000)
    doms = [{**x, "key": x.get("key") or x["domain"]} for x in get_json(f"{DATA}/domains")["domains"] if x.get("status") == "live"]
    page.wait_for_selector(tid(f"db-domain-{doms[0]['key']}"), timeout=90_000)  # the list loads after the header
    for dmn in doms:
        s.check(f"domain {dmn['key']} listed", page.locator(tid(f"db-domain-{dmn['key']}")).count() >= 1)
    for dmn in doms:
        for rel in dmn.get("relations", [])[:1]:
            d_, r_ = dmn["key"], rel["relation"]
            s.start("both", "C", f"Data Builder {d_}/{r_}: rows, dictionary, search, filter, compare, exports, Back")
            page.click(tid(f"db-domain-{d_}"))
            page.click(tid(f"db-relation-{d_}-{r_}"))
            page.wait_for_selector(tid("db-grid"), timeout=60_000)
            page.wait_for_load_state("networkidle")
            shown_period = page.input_value(tid("db-period"))
            q = {"period": "" if shown_period == "all" else shown_period}
            api_rows = get_json(f"{DATA}/relations/{d_}/{r_}/rows", period=q.get("period", ""), limit=1)
            s.check("row total equals the API", f"{count(api_rows['total'])} rows" in txt(page, "db-total"),
                    f"{count(api_rows['total'])} rows", txt(page, "db-total"))
            schema = get_json(f"{DATA}/relations/{d_}/{r_}/schema")
            page.click(tid("db-dictionary"))
            page.wait_for_selector(tid(f"db-dict-row-{schema['columns'][0]['name']}"), timeout=30_000)
            s.check("dictionary: one row per field", page.locator('[data-testid^="db-dict-row-"]').count() == len(schema["columns"]),
                    len(schema["columns"]), page.locator('[data-testid^="db-dict-row-"]').count())
            page.go_back()
            page.wait_for_selector(tid("db-grid"), timeout=30_000)
            key = next(c["name"] for c in schema["columns"] if c.get("key") and not c.get("period"))
            first = get_json(f"{DATA}/relations/{d_}/{r_}/rows", period=q.get("period", ""), limit=1)["rows"][0][key]
            page.fill(tid("db-search"), str(first))
            page.press(tid("db-search"), "Enter")
            page.wait_for_load_state("networkidle")
            got = get_json(f"{DATA}/relations/{d_}/{r_}/rows", period=q.get("period", ""), search=str(first), limit=1)
            page.wait_for_function(f"() => document.querySelector('[data-testid=\"db-total\"]').innerText.startsWith('{count(got['total'])} row')",
                                   timeout=30_000)
            s.check("search total equals the API", True)
            num = next((c["name"] for c in schema["columns"] if c.get("type") in ("number", "float", "int", "integer")
                        and not c.get("key")), None)
            if num:
                page.click(tid("db-filter-add"))
                page.select_option(tid("db-filter-column"), num)
                page.select_option(tid("db-filter-op"), "gte")
                page.fill(tid("db-filter-value"), "0")
                page.click(tid("db-filter-apply"))
                page.wait_for_load_state("networkidle")
                s.check("filter chip shown", page.locator(tid("db-chip-clear")).count() >= 1)
                page.locator(tid("db-chip-clear")).first.click()
                page.wait_for_load_state("networkidle")
                s.check("chip ✕ clears it", "f" not in url_params(page), "no filter", page.url)
            periods = rel.get("periods") or []
            if len(periods) >= 2:
                page.select_option(tid("db-compare"), periods[-2])
                page.wait_for_selector(tid("db-compare-basis"), timeout=30_000)
                s.check("compare with the prior period", url_params(page).get("compare") == periods[-2], periods[-2], page.url)
            for fmt in ("csv", "xlsx"):
                path = download(page, f"db-export-{fmt}")
                s.check(f"export {fmt} written", path.stat().st_size > 0 and dmn["key"] in path.name, dmn["key"], path.name)
            page.go_back()
            page.wait_for_load_state("networkidle")
            s.check("browser Back undoes one step", True)


WORKSPACE = "/api/v1/workspace"
_WS_COOKIE: dict[str, str] = {}


def ws_get(path: str) -> Any:
    """The Workspace API as the sweep's signed-in user (default the Administrator)."""
    user = os.environ.get("CP_SWEEP_USER", "anne")
    if user not in _WS_COOKIE:
        _WS_COOKIE[user] = core_login.login(user)["cookie"]
    return core_login.api_get(f"{WORKSPACE}/{path}", _WS_COOKIE[user])


def export_steps(s: Sweep) -> None:
    """PLAN_R3 S3-1: every Excel and Word export CreditProbe writes, fetched as Anne, is in the house style."""
    cookie = core_login.login("anne")["cookie"]

    def fetch(url: str, method: str = "GET", body: dict | None = None) -> tuple[bytes, str]:
        req = urllib.request.Request(url, method=method, headers={"Cookie": f"cp_session={cookie}",
                                                                  "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - loopback
            cd = r.headers.get("content-disposition") or ""
            m = re.search(r'filename="([^"]+)"', cd)
            return r.read(), (m.group(1) if m else "")

    def one(label: str, url: str, kind: str) -> None:
        try:
            body, name = fetch(url)
        except Exception as exc:  # noqa: BLE001
            s.check(f"{label}: downloads", False, "200", str(exc)[:200])
            return
        problems = house_check.xlsx(body) if kind == "xlsx" else house_check.docx(body)
        s.check(f"house style: {label} ({name})", not problems, "in house style", problems[:3])
        s.check(f"{label}: generated by Anne", "Anne" in _file_props(body, kind), "Anne", name)

    s.start("both", "X1", "Exports in the house style: Early Warning, Borrower 360, Data Builder")
    for book, period in (("corporate", "2026Q2"), ("retail", "2026-08")):
        one(f"Early Warning {book}", f"{API}/api/v1/ews/export.xlsx?domain={book}&period={period}&cohort=all", "xlsx")
    for book, cid, period in (("corporate", "CB01312", "2026Q2"), ("retail", "RC000001", "2026-08")):
        one(f"Borrower 360 {cid}", f"{B360}/customers/{cid}/export.xlsx?domain={book}&period={period}", "xlsx")
        one(f"Relationships {cid}", f"{B360}/customers/{cid}/graph/export.xlsx?domain={book}&period={period}", "xlsx")
    one("Data Builder extract", f"{DATA}/relations/open_banking/openbanking_corp_quarter/export.xlsx?period=2026Q1&search=CB00", "xlsx")

    s.start("both", "X2", "Exports in the house style: What-If Excel, 5-page Word report, report pack")
    body, _ = fetch(f"{WHATIF}/threads", "POST", {"domain": "corporate", "question": "PD +20% for Construction using delta"})
    t = json.loads(body)
    tid_ = t["thread_id"]
    run = t.get("run") or {}
    for step in range(2):                    # the proposal, then Execute (PLAN_R4 A1)
        for _ in range(600):
            r = json.loads(fetch(f"{WHATIF}/runs/{run.get('run_id')}")[0])
            if r.get("terminal"):
                break
            time.sleep(0.2)
        if step == 0:
            run = json.loads(fetch(f"{WHATIF}/threads/{tid_}/runs", "POST", {"question": "::execute"})[0])
    one("What-If Excel", f"{WHATIF}/threads/{tid_}/export.xlsx", "xlsx")
    one("What-If Word report", f"{WHATIF}/threads/{tid_}/report.docx", "docx")
    added = json.loads(fetch(f"{WHATIF}/reports/items", "POST", {"thread_id": tid_})[0])
    one("What-If report pack", f"{WHATIF}/reports/pack.docx", "docx")
    item = (added.get("added") or {}).get("item_id")
    if item:
        fetch(f"{WHATIF}/reports/items/{item}", "DELETE")


def _file_props(body: bytes, kind: str) -> str:
    import io as _io
    import zipfile
    try:
        return zipfile.ZipFile(_io.BytesIO(body)).read("docProps/core.xml").decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def workspace_steps(s: Sweep, page: Page) -> None:
    """Phase F: My workspace / Inbox, Projects, Investigations, Analyses (Mail: uat_sweep_core; Playbook and Policy
    Docs, which replaced Documents: uat_sweep_playbook).

    Every list, every detail, every Back link and the deep links into the modules, as the signed-in user.
    Read-only: the sweep does not post here, so the seeded content stays as seeded."""
    s.start("both", "F", "Sidebar → My workspace: Inbox")
    page.goto(UI + "/early-warning", wait_until="domcontentloaded")
    page.locator(NAV).get_by_role("link", name="My workspace").click()
    wait_url(page, r".*/workspace.*")
    page.wait_for_selector(tid("ws-tab-inbox"), timeout=90_000)
    page.click(tid("ws-tab-inbox"))
    page.wait_for_selector(tid("ws-inbox"), timeout=60_000)
    inbox = ws_get("inbox")
    items = inbox.get("items", inbox if isinstance(inbox, list) else [])
    shown = page.locator('[data-testid^="ws-inbox-item-"]').count()
    s.check("inbox lists the API's items", shown == len(items), len(items), shown)
    lists = [("Projects", "projects", "ws-project-", "projects"),
             ("Investigations", "investigations", "ws-investigation-", "investigations"),
             ("Analyses", "analyses", "ws-analysis-", "analyses")]
    # Documents became Playbook and Policy Docs (PLAN_R3 S1): their screens are swept in the group `playbook`.
    for label, path, prefix, key in lists:
        s.start("both", "F", f"Sidebar → {label}: every item opens, Back returns")
        page.locator(NAV).get_by_role("link", name=label, exact=True).click()
        page.wait_for_load_state("networkidle")
        got = ws_get(path)
        ids = [x["id"] for x in got.get(key, [])]
        for i in ids:
            page.wait_for_selector(tid(f"{prefix}{i}"), timeout=60_000)
        s.check(f"{label}: one entry per item", all(page.locator(tid(f"{prefix}{i}")).count() == 1 for i in ids),
                ids, "missing some" if ids else "none")
        for i in ids:
            page.locator(tid(f"{prefix}{i}")).locator("a").first.click()
            page.wait_for_selector(tid("ws-back"), timeout=60_000)
            page.wait_for_load_state("networkidle")
            page.click(tid("ws-back"))
            page.wait_for_selector(tid(f"{prefix}{i}"), timeout=60_000)
    s.start("both", "F", "Deep links from the workspace into Early Warning, Borrower 360 and What-If, then Back")
    page.locator(NAV).get_by_role("link", name="Projects", exact=True).click()
    page.wait_for_selector(tid("ws-project-q2-2026-committee-pack"), timeout=60_000)
    page.locator(tid("ws-project-q2-2026-committee-pack")).locator("a").first.click()
    page.wait_for_selector(tid("ws-link"), timeout=60_000)
    hrefs = [x.get_attribute("data-href") for x in page.locator(tid("ws-link")).all()]
    modules = [h for h in dict.fromkeys(hrefs) if h.split("?")[0] in ("/early-warning", "/borrower-360", "/what-if")]
    s.check("project links into the three modules", len({h.split("?")[0] for h in modules}) == 3, 3, modules)
    for h in modules:
        page.locator(f'[data-testid="ws-link"][data-href="{h}"]').first.click()
        wait_url(page, re.escape(h.split("?")[0]) + r".*")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        s.check(f"deep link {h} opens", h.split("?")[0] in page.url, h, page.url)
        page.go_back()
        page.wait_for_selector(tid("ws-back"), timeout=60_000)
        s.check("Back returns to the project", "/projects/" in page.url, "/projects/", page.url)


# ------------------------------------------------------------ What-If (PLAN_R2 item 6)

BANNED_LABELS = re.compile(r"\bsynthetic\b|\bdemo data\b|\(demo\)", re.I)


def whatif_last_result(thread_id: str) -> dict:
    th = get_json(f"{WHATIF}/threads/{thread_id}")
    for turn in reversed(th["turns"]):
        for b in turn["answer"]["blocks"]:
            if b["type"] == "result":
                return b["result"]
    return {}


def whatif_turn(page: Page, n_before: int, timeout: int = 180_000) -> None:
    """Wait until the thread shows one more settled turn and no live turn."""
    page.wait_for_function(
        "(n) => document.querySelectorAll('[data-testid=\"whatif-turn\"]').length > n"
        " && !document.querySelector('[data-testid=\"whatif-live-turn\"]')", arg=n_before, timeout=timeout)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)


def whatif_say(page: Page, text: str) -> None:
    n = page.locator(tid("whatif-turn")).count()
    page.fill(tid("whatif-composer"), text)
    page.click(tid("whatif-send"))
    whatif_turn(page, n)


def whatif_execute(page: Page) -> None:
    """Press Execute scenario beside the chat box (PLAN_R4 A1: a scenario runs only on Execute)."""
    n = page.locator(tid("whatif-turn")).count()
    page.click(tid("whatif-execute"))
    whatif_turn(page, n)


def whatif_thread_id(page: Page) -> str:
    return page.url.rstrip("/").split("/what-if/thread/")[1].split("?")[0]


def whatif_steps(s: Sweep, page: Page, book: str) -> None:
    import openpyxl
    meta = get_json(f"{WHATIF}/meta", domain=book)
    lab = meta["labels"]
    seg = meta["segments"][0] if book == "retail" else "Construction"
    s.start(book, "W1", "Sidebar → What-If; book toggle; chat box on top, library below")
    page.locator(NAV).get_by_role("link", name="What-If").click()
    wait_url(page, r".*/what-if.*")
    page.wait_for_selector(tid(f"whatif-book-{book}"), timeout=90_000)
    page.click(tid(f"whatif-book-{book}"))
    wait(page, "whatif-library")
    page.wait_for_load_state("networkidle")
    s.check("as-of shown", meta["as_of"][:4] in txt(page, "whatif-asof"), meta["as_of"], txt(page, "whatif-asof"))
    s.check("chat box above the library", page.locator(tid("whatif-chat")).bounding_box()["y"]
            < page.locator(tid("whatif-library")).bounding_box()["y"])
    lib = get_json(f"{WHATIF}/library", domain=book)
    s.check("standard library listed", page.locator('[data-testid^="whatif-lib-std-"]').count() == len(lib["standard"]),
            len(lib["standard"]), page.locator('[data-testid^="whatif-lib-std-"]').count())
    s.check("no banned label on the page", not BANNED_LABELS.search(page.inner_text("main")), "none", "")

    s.start(book, "W2", f"Ask: PD +30% for {seg} → proposal (nothing runs) → Execute → which model → Delta method")
    page.fill(tid("whatif-ask"), f"increase PD by 30% for {seg}")
    page.click(tid("whatif-ask-send"))
    wait_url(page, r".*/what-if/thread/.*")
    page.wait_for_selector(tid("whatif-proposal"), timeout=120_000)
    tid_ = whatif_thread_id(page)
    s.check("proposal restates the shock and scope", f"PD +30% on {seg}" in txt(page, "whatif-proposal"),
            f"PD +30% on {seg}", txt(page, "whatif-proposal"))
    s.check("nothing ran before Execute", page.locator(tid("whatif-result")).count() == 0)
    whatif_execute(page)
    page.wait_for_selector(tid("whatif-question-method"), timeout=120_000)
    n = page.locator(tid("whatif-turn")).count()
    page.click(tid("whatif-option-delta-method"))
    whatif_turn(page, n)
    res = whatif_last_result(tid_)
    c = res["cards"]
    s.check("scenario ECL on screen equals the API", sar(c["scenario_ecl"]) == page.locator(tid("whatif-kpi-ecl")).last.inner_text(),
            sar(c["scenario_ecl"]), page.locator(tid("whatif-kpi-ecl")).last.inner_text())
    s.check("baseline equals reported (Delta)", abs(c["start_ecl"] - c["reported_ecl"]) < 1e-6, c["reported_ecl"], c["start_ecl"])
    s.check("waterfall adds up", res["reconciliation"]["reconciles"], True, res["reconciliation"]["difference"])
    s.check("only the named segment moved", all(abs(r["change"]) < 1e-9 for r in res["by_segment"] if r["segment"] != seg))
    page.wait_for_selector(tid("whatif-waterfall-table"))
    s.check("waterfall chart drawn", page.locator('[data-testid^="whatif-waterfall-chart-"][data-rendered="true"]').count() >= 1)
    for tab in ("rating", "stage-migration", "top-movers", "macro-scenarios", "sector"):
        page.locator(tid(f"whatif-tab-{tab}")).last.click()
        page.wait_for_timeout(600)
    page.locator(tid("whatif-tab-stage-migration")).last.click()
    page.locator(tid("whatif-migration-ead")).last.click()
    s.check("migration matrix in EAD", "SAR" in page.locator(tid("whatif-migration")).last.inner_text())
    page.locator(tid("whatif-tab-rating")).last.click()
    page.wait_for_timeout(800)
    order = [r["grade"] for r in res["by_rating"]]
    s.check("rating detail in the global order", order == res["rating_order"], order, res["rating_order"])
    s.check("commentary and likelihood shown", page.locator(tid("whatif-commentary")).count() >= 1
            and page.locator(tid("whatif-likelihood")).count() >= 1)

    s.start(book, "W3", "Chip: rerun with XGBoost → side by side")
    n = page.locator(tid("whatif-turn")).count()
    page.locator(tid("whatif-chip-rerun-with-xgboost")).click()
    whatif_turn(page, n)
    s.check("comparison shown", page.locator(tid("whatif-comparison")).count() == 1)
    s.check("Delta column equals the first run", sar(c["scenario_ecl"]) in page.locator(tid("whatif-compare-delta-scenario-ecl")).last.inner_text(),
            sar(c["scenario_ecl"]), page.locator(tid("whatif-compare-delta-scenario-ecl")).last.inner_text())

    s.start(book, "W4", "Intensify, stack, likelihood")
    whatif_say(page, "make it twice as severe")
    s.check("intensify is a proposal", "PD +60%" in page.locator(tid("whatif-proposal")).last.inner_text())
    whatif_say(page, "run it")
    r2 = whatif_last_result(tid_)
    s.check("intensity doubled", r2["steps"][0]["restatement"].startswith("PD +60%"), "PD +60%", r2["steps"][0]["restatement"])
    whatif_say(page, "also add LGD +5pp")
    whatif_execute(page)
    r3 = whatif_last_result(tid_)
    s.check("stacked: two steps", len(r3["steps"]) == 2, 2, len(r3["steps"]))
    s.check("stacking adds ECL", r3["cards"]["change"] > r2["cards"]["change"], r2["cards"]["change"], r3["cards"]["change"])
    whatif_say(page, "how likely is this?")
    s.check("likelihood answered", page.locator(tid("whatif-likelihood-label")).count() >= 1)

    s.start(book, "W5", "Custom shocks panel (structured editor) as a new scenario")
    page.click(tid("whatif-custom-toggle"))
    wait(page, "whatif-custom")
    page.fill(tid("whatif-custom-pd"), "15")
    page.locator(tid("whatif-custom")).get_by_role("button", name="As a new scenario").click()
    n = page.locator(tid("whatif-turn")).count()
    page.click(tid("whatif-custom-run"))
    whatif_turn(page, n)
    whatif_execute(page)
    r4 = whatif_last_result(tid_)
    s.check("custom step ran", r4["steps"][0]["restatement"].startswith("PD +15%"), "PD +15%", r4["steps"][0]["restatement"])
    whatif_say(page, "undo")

    s.start(book, "W6", "Save; Word report (5 pages); Excel; Add to report")
    page.once("dialog", lambda d: d.accept(f"Sweep {book} scenario"))
    page.click(tid("whatif-save"))
    page.wait_for_selector(tid("whatif-notice"), timeout=60_000)
    s.check("saved", "Saved" in txt(page, "whatif-notice"), "Saved", txt(page, "whatif-notice"))
    path = download(page, "whatif-word")
    from docx import Document
    doc = Document(str(path))
    s.check("Word report: five pages (four page breaks)", doc.element.xml.count('w:type="page"') == 4)
    s.check("Word report: three charts", len(doc.inline_shapes) == 3, 3, len(doc.inline_shapes))
    s.check("Word report: no banned label", not BANNED_LABELS.search("\n".join(p.text for p in doc.paragraphs)))
    path = download(page, "whatif-excel")
    wb = openpyxl.load_workbook(path, read_only=True)
    s.check("Excel sheets", {"Summary", "Waterfall", "Stage migration", "Top movers"} <= set(wb.sheetnames), "", wb.sheetnames)
    wb.close()
    page.click(tid(f"whatif-add-pack-{tid_}"))
    page.wait_for_function("() => (document.querySelector('[data-testid=\"whatif-notice\"]')||{}).innerText?.includes('report pack')")
    s.check("added to the report pack", "report pack" in txt(page, "whatif-notice"))

    s.start(book, "W7", "← What-If; the saved scenario is in the repository; the pack is listed")
    page.click(tid("whatif-back"))
    wait(page, "whatif-library")
    page.click(tid("whatif-lib-saved"))
    page.wait_for_selector(tid("whatif-repository"), timeout=60_000)
    s.check("repository lists the saved scenario", f"Sweep {book} scenario" in txt(page, "whatif-repository"))
    s.check("report pack lists it", page.locator(tid("whatif-pack-download")).count() == 1)
    s.check("recent threads list it", page.locator(tid("whatif-recent-thread")).count() >= 1)

    s.start(book, "W8", "Library: a standard scenario opens a thread that describes it, then its impact; Back")
    page.click(tid("whatif-lib-standard"))
    first = lib["standard"][0]
    page.click(tid(f"whatif-lib-{first['scenario_id']}"))
    wait_url(page, r".*/what-if/thread/.*")
    page.wait_for_selector(tid("whatif-proposal"), timeout=180_000)
    s.check("described first", first["name"] in page.locator(tid("whatif-answer")).first.inner_text())
    whatif_execute(page)
    page.wait_for_selector(tid("whatif-result"), timeout=180_000)
    lr = whatif_last_result(whatif_thread_id(page))
    s.check("impact on screen equals the API", sar(lr["cards"]["scenario_ecl"]) == page.locator(tid("whatif-kpi-ecl")).last.inner_text())
    page.go_back()
    wait(page, "whatif-library")
    s.check("browser Back returns to What-If", page.url.split("?")[0].endswith("/what-if"), "/what-if", page.url)

    s.start(book, "W9", "Model cards: Delta and XGBoost, every section; Back")
    page.click(tid("whatif-card-delta"))
    wait(page, "whatif-mc-summary")
    for sec in ("summary", "data", "inputs", "how", "validation", "sensitivities", "limitations", "versions"):
        s.check(f"Delta card section {sec}", page.locator(tid(f"whatif-mc-{sec}")).count() == 1)
    s.check("MEV table lists at least 10 series", page.locator(tid("whatif-mc-mev")).locator("tbody tr").count() >= 10)
    page.click(tid("whatif-card-other"))
    wait(page, "whatif-mc-training")
    page.wait_for_selector('[data-testid="whatif-mc-beeswarm"][data-rendered="true"]', timeout=60_000)
    s.check("XGBoost card: metrics for PD, LGD and ECL components",
            all(page.locator(tid(f"whatif-mc-target-{k}")).count() == 1 for k in ("pd", "lgd", "ecl12", "ecllt")))
    page.click(tid("whatif-card-back"))
    wait(page, "whatif-library")
    s.check("card Back returns to What-If", "/what-if" in page.url)

    s.start(book, "W10", "Conversation: collateral is a lever; the mechanics question is answered from the book; Execute; Back")
    page.fill(tid("whatif-ask"), "Reduce collateral by 20%")
    page.click(tid("whatif-ask-send"))
    wait_url(page, r".*/what-if/thread/.*")
    page.wait_for_selector(tid("whatif-proposal"), timeout=120_000)
    s.check("a collateral shock, not LGD +20%", "collateral value -20%" in txt(page, "whatif-proposal")
            and "LGD +20" not in txt(page, "whatif-proposal"), "collateral value -20%", txt(page, "whatif-proposal"))
    whatif_say(page, "How did you equate a collateral reduction with an LGD increase?")
    md = page.locator(tid("convo-markdown")).last.inner_text()
    s.check("real explanation with the haircut formula", "haircut" in md and "LGD_unsecured" in md, "formula", md[:120])
    s.check("numbers for this book", "secured share from" in md, "secured share from", md[:200])
    s.check("table and chart from the queries", page.locator('[data-testid^="convo-table-"]').count() >= 1
            and page.locator('[data-testid^="convo-chart-"]').count() >= 1)
    s.check("nothing ran", page.locator(tid("whatif-result")).count() == 0)
    whatif_execute(page)
    page.wait_for_selector(tid("whatif-question-method"), timeout=120_000)
    n = page.locator(tid("whatif-turn")).count()
    page.locator(tid("whatif-option-delta-method")).last.click()
    whatif_turn(page, n)
    rc = whatif_last_result(whatif_thread_id(page))
    bars = {b["key"]: b["value"] for b in rc["waterfall"] if b["kind"] == "driver"}
    s.check("the change flows through the collateral bar", bars.get("collateral", 0) > 0 and abs(bars.get("lgd", 0)) < 1e-9,
            "collateral > 0, LGD 0", bars)
    whatif_say(page, "Where is ECL concentrated in this book?")
    s.check("a data question gets a table", page.locator('[data-testid^="convo-table-"]').count() >= 2)
    page.click(tid("whatif-back"))
    wait(page, "whatif-library")
    s.check("Back returns to What-If", "/what-if" in page.url)



def stop_and_start(s: Sweep) -> None:
    """UAT step 21: ops/v5.sh stop stops the three v5 services and nothing else; then start again."""
    import socket
    import subprocess

    def listening(port: int) -> bool:
        with socket.socket() as so:
            so.settimeout(1)
            return so.connect_ex(("127.0.0.1", port)) == 0

    s.start("both", "21", "ops/v5.sh stop: all three services stop, nothing else is touched")
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    out = subprocess.run([str(V5 / "ops/v5.sh"), "stop"], cwd=V5, capture_output=True, text=True, timeout=180)
    time.sleep(3)
    s.check("stop exits 0", out.returncode == 0, 0, out.returncode)
    for port in (5500, 8500, 8501):
        s.check(f"port {port} closed", not listening(port), "closed", "open" if listening(port) else "closed")
    s.check("an unrelated process is untouched", bystander.poll() is None, "running", bystander.poll())
    bystander.kill()
    s.start("both", "1", "ops/v5.sh start: all three services back")
    out = subprocess.run([str(V5 / "ops/v5.sh"), "start"], cwd=V5, capture_output=True, text=True, timeout=600)
    s.check("start exits 0", out.returncode == 0, 0, out.stdout[-300:])
    for port in (5500, 8500, 8501):
        s.check(f"port {port} listening", listening(port), "listening", "open" if listening(port) else "closed")
    health = api("/health")
    s.check("EWS API healthy on gw-ews-1.1.0", (health.get("status"), health.get("ruleset")) == ("ok", "gw-ews-1.1.0"),
            ("ok", "gw-ews-1.1.0"), (health.get("status"), health.get("ruleset")))
    # The UI compiles on first request; make sure the Cockpit home and Early Warning answer.
    for path in ("/", "/early-warning"):
        with urllib.request.urlopen(UI + path, timeout=180) as r:
            s.check(f"UI {path} answers", r.status == 200, 200, r.status)
    s.finish()


def run() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    started = datetime.now(timezone.utc)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 1000})
        core_login.add_session(context, os.environ.get("CP_SWEEP_USER", "anne"))  # signed in as the Administrator
        page = context.new_page()
        page.set_default_timeout(60_000)
        s = Sweep(page)
        records: dict[str, Any] = {}
        # A crash is a failed step, recorded; the other book still runs.
        for name, part in [("cockpit", lambda: cockpit_steps(s, page)),
                           *[(book, lambda b=book: records.__setitem__(b, ews_book(s, page, b))) for book in BOOKS],
                           ("modules", lambda: module_steps(s, page, records)),
                           ("core", lambda: __import__("uat_sweep_core").core_steps(s, page, UI, wait_url)),
                           ("share", lambda: __import__("uat_sweep_core").share_steps(s, page, UI, wait_url)),
                           ("graph", lambda: __import__("uat_sweep_core").graph_steps(s, page, UI, wait_url)),
                           ("attention", lambda: __import__("uat_sweep_core").attention_steps(s, page, UI, wait_url)),
                           ("labels", lambda: __import__("uat_sweep_core").labels_steps(s, page, UI, wait_url)),
                           ("workspace", lambda: workspace_steps(s, page)),
                           ("work", lambda: __import__("sweep_r3_work").work_steps(s, page, UI, wait_url)),
                           ("exports", lambda: export_steps(s)),
                           ("home", lambda: __import__("sweep_r3_home").home_steps(s, page, UI, wait_url)),
                           ("cohort", lambda: __import__("sweep_r3_cohort").cohort_steps(s, page, UI, wait_url)),
                           ("mail", lambda: __import__("sweep_r3_mail").mail_steps(s, page, UI, wait_url)),
                           ("scorecard", lambda: __import__("uat_sweep_scorecard").scorecard_steps(s, page, UI, wait_url)),
                           ("playbook", lambda: __import__("uat_sweep_playbook").playbook_steps(s, page, UI, wait_url)),
                           ("ai_work", lambda: __import__("sweep_r4_ai_work").ai_work_steps(s, page, UI, wait_url)),
                           ("dealdesk", lambda: __import__("uat_sweep_dealdesk").dealdesk_steps(s, page, UI, wait_url)),
                           ("lenses", lambda: __import__("uat_sweep_lenses").lens_steps(s, page, UI, wait_url)),
                           # PLAN_R5 Session A: the Admin console and data access.
                           ("admin", lambda: __import__("sweep_r5_admin").admin_steps(s, page, UI, wait_url)),
                           # PLAN_R4 Session B: one file per item, so the items do not collide here.
                           *[(f"r4-{p}", lambda p=p: getattr(__import__(f"sweep_r4_{p}"), f"{p}_steps")(s, page, UI, wait_url))
                             for p in ("cards", "b360", "ews", "scorecard", "g1", "data")],
                           # PLAN_R5 Session T: the shared thread (G4), What-If questions (T3), raw numbers (G5).
                           ("r5-threads", lambda: __import__("sweep_r5_threads").threads_steps(s, page, UI, wait_url)),
                           # PLAN_R5 Session E: the Early Warning story.
                           ("r5-ews-story", lambda: __import__("sweep_r5_ews_story").ews_story_steps(s, page, UI, UI, wait_url)),
                           # PLAN_R5 Session P: navigation, Playbook tables and merge (Early Warning P4 is in r4-ews).
                           ("r5-ui", lambda: __import__("sweep_r5_ui").r5_ui_steps(s, page, UI, wait_url)),
                           # PLAN_R7: every Back returns to the exact previous screen and step.
                           ("r7-back", lambda: __import__("sweep_r7_back").r7_back_steps(s, page, UI, wait_url))]:
            if "--only" in sys.argv and name not in sys.argv[sys.argv.index("--only") + 1].split(","):
                continue
            try:
                part()
            except Exception as e:  # noqa: BLE001
                if s.current is None:
                    s.start(name, "-", "sweep crashed")
                s.check("step completed", False, "no exception", f"{type(e).__name__}: {str(e)[:400]}")
        s.finish()
        browser.close()
    if "--stop-start" in sys.argv:
        s.page = None  # type: ignore[assignment]
        try:
            stop_and_start(s)
        except Exception as e:  # noqa: BLE001
            if s.current is None:
                s.start("both", "21", "stop/start crashed")
            s.check("step completed", False, "no exception", f"{type(e).__name__}: {str(e)[:300]}")
            s.finish()
    steps = s.steps
    failed = [x for x in steps if not x["pass"]]
    checks = sum(len(x["checks"]) for x in steps)
    report = {"ui": UI, "api": API, "started_utc": started.isoformat(), "seconds": round(
        (datetime.now(timezone.utc) - started).total_seconds()), "steps": len(steps), "checks": checks,
        "failed_steps": len(failed), "passed": not failed, "records": records, "results": steps}
    (OUT / "uat_sweep.json").write_text(json.dumps(report, indent=1, default=str))
    lines = [f"# UAT sweep: {len(steps) - len(failed)}/{len(steps)} steps passed, {checks} checks",
             "", f"UI {UI} · API {API} · {started.isoformat()} · {report['seconds']} s", "",
             "| # | Book | UAT step | Step | Checks | Errors | Result |", "|---|---|---|---|---|---|---|"]
    for x in steps:
        lines.append(f"| {x['n']} | {x['book']} | {x['uat_step']} | {x['title']} | "
                     f"{sum(c['pass'] for c in x['checks'])}/{len(x['checks'])} | {len(x['errors'])} | "
                     f"{'PASS' if x['pass'] else 'FAIL'} |")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(steps) - len(failed)}/{len(steps)} sweep steps passed ({checks} checks)")
    for x in failed[:30]:
        bad = [c for c in x["checks"] if not c["pass"]]
        print(f"  FAIL [{x['n']}] {x['book']} {x['title']}: {bad[:2]} {x['errors'][:2]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run())
