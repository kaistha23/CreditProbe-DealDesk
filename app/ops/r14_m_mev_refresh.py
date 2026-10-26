"""R14 session m (K13): apply the October 2026 macro refresh to the What-If MEV store, then rebuild it.

    .venv/bin/python ops/r14_m_mev_refresh.py          apply (idempotent) and run ops/whatif_build_mev.py

What it does
  1. data/whatif_v5/mev/sources_raw.csv: replaces the rows the IMF World Economic Outlook October 2026 superseded
     (Saudi real GDP growth 2025-2027, CPI 2025-2027, current account 2026, the IMF oil-price assumption 2026-2027),
     each with its vintage, URL and retrieval date (2026-10-19). Every other row is kept as it was (vintage stated).
  2. data/whatif_v5/mev/latest_observations.csv: the dated observations the current-regime block reads (Brent daily
     spot, EIA STEO quarterly and annual Brent, GASTAT flash GDP and monthly CPI, the non-oil PMI, the MoF pre-budget
     deficit, the dated market context line). One row per observation, with source, URL, vintage and retrieval date.

How the figures were obtained (19 Oct 2026): the build container cannot reach imf.org or eia.gov (proxy 403). The
figures were found with web search and read with a page fetch of URLs that appeared in the search results:
  * the IMF DataMapper API v2 (https://www.imf.org/external/datamapper/api/v2/NGDP_RPCH) answered and reports
    "World Economic Outlook (October 2026)", last modified 2026-10-08, but its text is cut before the SAU entry, so the
    Saudi values are taken from press reports that quote the October 2026 WEO tables (Arab News, Zawya / Saudi Gazette,
    Edge Consultancy, TASS); each row says so in `note`.
  * Brent: Trading Economics and Fortune (daily), EIA STEO October 2026 (quarterly and annual), the EIA monthly file
    already in the store (to September 2026).
No value is invented or interpolated. Rows that could not be refreshed are listed in docs/STATUS_R14_M.md.
"""
from __future__ import annotations

import csv
import pathlib
import subprocess
import sys

V5 = pathlib.Path(__file__).resolve().parents[1]
MEV = V5 / "data" / "whatif_v5" / "mev"
RETRIEVED = "2026-10-19"
WEO = "IMF WEO October 2026"
WEO_API = "https://www.imf.org/external/datamapper/api/v2/NGDP_RPCH"
ARAB_NEWS = "https://www.arabnews.com/business/saudi-arabia-to-outpace-global-growth-with-79-expansion-in-2027-imf-3006034"
ZAWYA = "https://www.zawya.com/en/economy/imf-raises-saudi-arabias-growth-forecast-to-7.9-in-2027-1"
SAUDI_GAZETTE = "https://saudigazette.com.sa/article/665380/saudi-arabia/imf-raises-saudi-arabias-growth-forecast-to-79-in-2027"
EDGE = "https://edgeconsultancykw.com/imf-weo-gfsr-october-2026-egypt-growth-gulf-rebound/"
TASS = "https://tass.com/economy/2201255/amp"
PRESS = ("reported from the IMF WEO October 2026 tables (DataMapper API v2 shows the October 2026 vintage, last modified "
         "2026-10-08; the SAU entry could not be read from here)")

#: (raw series, year) -> (value, kind, source, url, note)
REFRESH: dict[tuple[str, int], tuple[float, str, str, str, str]] = {
    ("real_gdp_growth", 2025): (4.6, "history", f"{WEO}, NGDP_RPCH (Arab News 13 Oct 2026)", ARAB_NEWS,
                                f"{PRESS}; April 2026 vintage had 4.5"),
    ("real_gdp_growth", 2026): (-3.3, "projection", f"{WEO}, Table 1.1 (Zawya / Saudi Gazette 14 Oct 2026)", ZAWYA,
                                f"{PRESS}; July 2026 Update had 1.7 (revision -5.0 pp)"),
    ("real_gdp_growth", 2027): (7.9, "projection", f"{WEO}, Table 1.1 (Zawya / Saudi Gazette 14 Oct 2026)", ZAWYA,
                                f"{PRESS}; July 2026 Update had 5.5 (revision +2.4 pp)"),
    ("cpi_inflation", 2025): (2.0, "history", f"{WEO}, PCPIPCH (Zawya 14 Oct 2026)", ZAWYA, f"{PRESS}; unchanged from April 2026"),
    ("cpi_inflation", 2026): (1.9, "projection", f"{WEO}, PCPIPCH (Arab News 13 Oct 2026)", ARAB_NEWS,
                              f"{PRESS}; April 2026 vintage had 2.3"),
    ("cpi_inflation", 2027): (2.2, "projection", f"{WEO}, PCPIPCH (Arab News 13 Oct 2026)", ARAB_NEWS,
                              f"{PRESS}; April 2026 vintage had 2.1"),
    ("current_account_balance", 2026): (-3.5, "projection", f"{WEO}, BCA_NGDPD (Edge Consultancy table, Oct 2026)", EDGE,
                                        f"{PRESS}; April 2026 vintage had -1.6; 2025 and 2027 not found in October 2026 reporting"),
    ("oil_price_imf_apsp", 2026): (95.74, "projection", f"{WEO}, oil-price assumption (futures-based) (TASS 13 Oct 2026)", TASS,
                                   "IMF average petroleum spot price assumption; July 2026 Update had 89.27"),
    ("oil_price_imf_apsp", 2027): (87.39, "projection", f"{WEO}, oil-price assumption (futures-based) (TASS 13 Oct 2026)", TASS,
                                   "IMF average petroleum spot price assumption; July 2026 Update had 78.7"),
}

LATEST_COLS = ["series", "date", "value", "unit", "frequency", "kind", "source", "source_url", "vintage", "retrieved", "note"]
TE = "https://tradingeconomics.com/commodity/brent-crude-oil"
FORTUNE = "https://fortune.com/article/price-of-oil-10-13-2026/"
STEO = "https://www.eia.gov/outlooks/steo/pdf/steo_full.pdf"
PETRO = "https://www.petroleumnews.com/story/2026/10/11/finance/eia-september-brent-up-23-from-august/50437.html"
LATEST: list[dict[str, str]] = [
    {"series": "brent_spot", "date": "2026-10-19", "value": "108.0", "unit": "USD/bbl", "frequency": "daily", "kind": "observation",
     "source": "Trading Economics, Brent crude (19 Oct 2026)", "source_url": TE, "vintage": "market price 2026-10-19",
     "note": "'Brent crude fell 1.5% towards $108 a barrel on Monday'; the page's statistics show 110.14 and +80.5% y/y (CFD prices, not the official benchmark)"},
    {"series": "brent_spot_yoy_pct", "date": "2026-10-19", "value": "80.5", "unit": "% y/y", "frequency": "daily", "kind": "observation",
     "source": "Trading Economics, Brent crude (19 Oct 2026)", "source_url": TE, "vintage": "market price 2026-10-19",
     "note": "one-year change as published on the page (+80.36% in its table)"},
    {"series": "brent_spot", "date": "2026-10-13", "value": "107.29", "unit": "USD/bbl", "frequency": "daily", "kind": "observation",
     "source": "Fortune, current price of oil (13 Oct 2026, 7:45 a.m. ET)", "source_url": FORTUNE, "vintage": "market price 2026-10-13",
     "note": "a year earlier 63.69; +68.45% y/y"},
    {"series": "brent_spot", "date": "2025-10-13", "value": "63.69", "unit": "USD/bbl", "frequency": "daily", "kind": "observation",
     "source": "Fortune, current price of oil (13 Oct 2026): year-ago price", "source_url": FORTUNE, "vintage": "market price 2025-10-13",
     "note": "the year-ago reference Fortune quotes"},
    {"series": "brent_eia_quarter", "date": "2026-03-31", "value": "81.11", "unit": "USD/bbl", "frequency": "quarterly", "kind": "observation",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (1Q26)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06", "note": ""},
    {"series": "brent_eia_quarter", "date": "2026-06-30", "value": "102.93", "unit": "USD/bbl", "frequency": "quarterly", "kind": "observation",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (2Q26)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06", "note": ""},
    {"series": "brent_eia_quarter", "date": "2026-09-30", "value": "95.95", "unit": "USD/bbl", "frequency": "quarterly", "kind": "observation",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (3Q26)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06", "note": ""},
    {"series": "brent_eia_quarter", "date": "2026-12-31", "value": "104.69", "unit": "USD/bbl", "frequency": "quarterly", "kind": "forecast",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (4Q26 forecast)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06",
     "note": "up USD 14 from the September STEO (Petroleum News 11 Oct 2026)"},
    {"series": "brent_eia_year", "date": "2026-12-31", "value": "96.32", "unit": "USD/bbl", "frequency": "annual", "kind": "forecast",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (2026 average)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06", "note": ""},
    {"series": "brent_eia_year", "date": "2027-12-31", "value": "83.74", "unit": "USD/bbl", "frequency": "annual", "kind": "forecast",
     "source": "EIA Short-Term Energy Outlook October 2026, Table 2 (2027 average)", "source_url": STEO, "vintage": "EIA STEO 2026-10-06", "note": ""},
    {"series": "brent_eia_month", "date": "2026-09-30", "value": "114", "unit": "USD/bbl", "frequency": "monthly", "kind": "observation",
     "source": "EIA STEO October 2026 via Petroleum News (11 Oct 2026): September Brent up USD 23 from August", "source_url": PETRO,
     "vintage": "EIA STEO 2026-10-06", "note": "agrees with the EIA monthly file in the store (114.16)"},
    {"series": "gdp_real_q_yoy", "date": "2026-06-30", "value": "-4.7", "unit": "% y/y", "frequency": "quarterly", "kind": "observation",
     "source": "GASTAT, Q2 2026 GDP (revised, 7 Sep 2026) via Arab News", "source_url": "https://www.arabnews.com/business/saudi-non-oil-activities-up-09-in-q2-gastat-3000883",
     "vintage": "GASTAT 2026-09-07", "note": "flash (end-July) -4.8; oil activities -24.8%, non-oil +0.9%"},
    {"series": "gdp_nonoil_q_yoy", "date": "2026-06-30", "value": "0.9", "unit": "% y/y", "frequency": "quarterly", "kind": "observation",
     "source": "GASTAT, Q2 2026 GDP (revised, 7 Sep 2026) via Arab News", "source_url": "https://www.arabnews.com/business/saudi-non-oil-activities-up-09-in-q2-gastat-3000883",
     "vintage": "GASTAT 2026-09-07", "note": "flash +0.6"},
    {"series": "gdp_oil_q_yoy", "date": "2026-06-30", "value": "-24.8", "unit": "% y/y", "frequency": "quarterly", "kind": "observation",
     "source": "GASTAT, Q2 2026 GDP (revised, 7 Sep 2026) via Arab News", "source_url": "https://www.arabnews.com/business/saudi-non-oil-activities-up-09-in-q2-gastat-3000883",
     "vintage": "GASTAT 2026-09-07", "note": "oil volumes fell with the export disruption while the price rose"},
    {"series": "cpi_m_yoy", "date": "2026-09-30", "value": "1.9", "unit": "% y/y", "frequency": "monthly", "kind": "observation",
     "source": "GASTAT CPI September 2026 via Zawya", "source_url": "https://www.zawya.com/en/economy/saudi-inflation-remains-stable-at-1.9-in-september-despit",
     "vintage": "GASTAT 2026-10-15", "note": "August 1.8"},
    {"series": "pmi_nonoil", "date": "2026-09-30", "value": "55.3", "unit": "index (50 = no change)", "frequency": "monthly", "kind": "observation",
     "source": "S&P Global Saudi Arabia PMI (non-oil private sector), September 2026, via Arab News", "source_url": "https://www.arabnews.pk/business/saudi-non-oil-pmi-rises-to-553-highest-since-february-300",
     "vintage": "S&P Global 2026-10-05", "note": "highest since February 2026"},
    {"series": "fiscal_balance_mof", "date": "2026-12-31", "value": "-4.9", "unit": "% of GDP", "frequency": "annual", "kind": "forecast",
     "source": "Saudi MoF 2027 pre-budget statement (30 Sep 2026), reported", "source_url": "https://www.zawya.com/en/economy/saudi-arabia-estimates-fiscal-deficit-of-3.6-of-gdp-in-20",
     "vintage": "MoF 2026-09-30", "note": "SAR 245bn; 2027 -3.6% (SAR 191bn). Ministry figures, not IMF"},
    {"series": "context", "date": "2026-10-19", "value": "", "unit": "", "frequency": "daily", "kind": "context",
     "source": "Trading Economics, Brent crude (19 Oct 2026)", "source_url": TE, "vintage": "news 2026-10-19",
     "note": "Gulf supply disruption: attacks on Yanbu, a key Saudi export hub, and tankers struck in the Gulf and the Strait of Hormuz; regional oil flows about 80% of pre-conflict levels (US Energy Secretary). IMF assumes Hormuz traffic resumes in March 2027 (WEO October 2026)."},
]


def apply_refresh() -> int:
    path = MEV / "sources_raw.csv"
    rows = list(csv.DictReader(path.open()))
    cols = list(rows[0].keys())
    if "retrieved" not in cols:
        cols.append("retrieved")
    have = {(r["series"], int(r["year"])): r for r in rows}
    changed = 0
    for (series, year), (value, kind, source, url, note) in REFRESH.items():
        r = have.get((series, year))
        unit = r["unit"] if r else next(x["unit"] for x in rows if x["series"] == series)
        new = {"series": series, "year": str(year), "value": f"{value:g}", "unit": unit, "kind": kind, "source": source,
               "source_url": url, "vintage": WEO, "note": note, "retrieved": RETRIEVED}
        if r is None:
            rows.append(new)
            changed += 1
        elif any(str(r.get(k, "")) != str(v) for k, v in new.items()):
            r.update(new)
            changed += 1
    for r in rows:
        r.setdefault("retrieved", "")
        if not r["retrieved"]:
            r["retrieved"] = "2026-10-10"
    rows.sort(key=lambda r: (r["series"], int(r["year"])))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (MEV / "latest_observations.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LATEST_COLS, lineterminator="\n")
        w.writeheader()
        for r in LATEST:
            w.writerow({**r, "retrieved": RETRIEVED})
    return changed


def main() -> int:
    n = apply_refresh()
    print(f"sources_raw.csv: {n} rows refreshed to {WEO}; latest_observations.csv: {len(LATEST)} rows")
    return subprocess.call([sys.executable, str(V5 / "ops" / "whatif_build_mev.py")])


if __name__ == "__main__":
    raise SystemExit(main())
