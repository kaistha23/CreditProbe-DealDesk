"""Build the What-If MEV store from the sourced raw file.

    .venv/bin/python ops/whatif_build_mev.py

Reads  data/whatif_v5/mev/sources_raw.csv   (every figure with its source, URL and vintage;
                                             collected 2026-10-10, see SOURCES.md)
       data/whatif_v5/mev/brent_*_eia.csv   (EIA Brent via the datasets/oil-prices mirror)
Writes data/whatif_v5/mev/mev_annual.csv    (the 11 model series, history + projection)
       data/whatif_v5/mev/manifest.json

Choices (each also written into the manifest):
  * Brent history: EIA annual averages. Projection 2026-2027: the IMF WEO oil-price
    assumption (average of Brent, Dubai and WTI), the closest published path; 2028-2030
    held at 2027.
  * Real-estate price index: GASTAT changed method in 2024. The old index (2014=100) is
    used to 2021 and the new index (2023=100) from 2022, chained at 2021 by the new
    index's growth. Both originals stay in sources_raw.csv.
  * Government expenditure: % of GDP (IMF WEO October 2024 vintage).
  * Series with no published projection are held flat at the last value (mev.py).
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
MEV = V5 / "data" / "whatif_v5" / "mev"
RETRIEVED = "2026-10-19"   # R14 m: the October 2026 refresh (ops/r14_m_mev_refresh.py); each row keeps its own date

MAP = {
    "gdp_real": "real_gdp_growth",
    "gdp_nonoil": "nonoil_real_gdp_growth",
    "brent": "brent_oil_price",
    "cpi": "cpi_inflation",
    "unemployment": "unemployment_rate",
    "repo": "sama_repo_rate",
    "saibor_3m": "saibor_3m",
    "gov_spend": "gov_expenditure_pct_gdp",
    "current_account": "current_account_balance",
    "credit_growth": "bank_credit_private_growth",
}


def main() -> int:
    rows = list(csv.DictReader((MEV / "sources_raw.csv").open()))
    by = {}
    for r in rows:
        by.setdefault(r["series"], []).append(r)
    out = []
    series_meta = []
    for key, raw in MAP.items():
        got = sorted(by.get(raw, []), key=lambda r: int(r["year"]))
        for r in got:
            out.append({"series": key, "year": int(r["year"]), "value": float(r["value"]), "unit": r["unit"],
                        "kind": r["kind"], "source": r["source"], "source_url": r["source_url"],
                        "vintage": r["vintage"], "note": r["note"], "retrieved": r.get("retrieved") or "2026-10-10"})
        hist = [int(r["year"]) for r in got if r["kind"] == "history"]
        proj = [int(r["year"]) for r in got if r["kind"] == "projection"]
        series_meta.append({"key": key, "raw_series": raw, "source": got[0]["source"] if got else "",
                            "source_url": got[0]["source_url"] if got else "",
                            "vintage": "; ".join(sorted({r["vintage"] for r in got})),
                            "history": [min(hist), max(hist)] if hist else None,
                            "projection": [min(proj), max(proj)] if proj else None,
                            "retrieved": max((r.get("retrieved") or "2026-10-10") for r in got) if got else RETRIEVED})
    # Brent projection: the IMF oil-price assumption.
    for r in sorted(by.get("oil_price_imf_apsp", []), key=lambda r: int(r["year"])):
        out.append({"series": "brent", "year": int(r["year"]), "value": float(r["value"]), "unit": "USD/bbl",
                    "kind": "projection", "source": r["source"], "source_url": r["source_url"],
                    "vintage": r["vintage"],
                    "note": "IMF oil-price assumption (average of Brent, Dubai, WTI) used as the Brent base path. " + r["note"],
                    "retrieved": r.get("retrieved") or "2026-10-10"})
    brent_meta = next(m for m in series_meta if m["key"] == "brent")
    brent_meta["projection"] = [2026, 2027]
    brent_meta["note"] = ("History: EIA Europe Brent spot (annual and monthly averages, datasets/oil-prices mirror of the "
                          "EIA API). Base path 2026-2027: IMF WEO oil-price assumption; 2028-2030 held at 2027.")
    # Real-estate price index: chain old (2014=100) to 2021 and the new index from 2022.
    old = {int(r["year"]): float(r["value"]) for r in by.get("repi_index_2014base", [])}
    new = {int(r["year"]): float(r["value"]) for r in by.get("repi_index_2023base", [])}
    src_old = by["repi_index_2014base"][0]
    src_new = by["repi_index_2023base"][0]
    for y in sorted(old):
        if y <= 2021:
            out.append({"series": "re_price", "year": y, "value": old[y], "unit": "index, 2014=100 (chained)",
                        "kind": "history", "source": src_old["source"], "source_url": src_old["source_url"],
                        "vintage": src_old["vintage"], "note": "old methodology (2014=100)",
                        "retrieved": src_old.get("retrieved") or "2026-10-10"})
    for y in sorted(new):
        if y >= 2022 and 2021 in new and 2021 in old:
            out.append({"series": "re_price", "year": y, "value": round(old[2021] * new[y] / new[2021], 4),
                        "unit": "index, 2014=100 (chained)", "kind": "history", "source": src_new["source"],
                        "source_url": src_new["source_url"], "vintage": src_new["vintage"],
                        "note": f"new methodology (2023=100) chained to the old index at 2021: old2021 x new{y}/new2021",
                        "retrieved": src_new.get("retrieved") or "2026-10-10"})
    series_meta.append({"key": "re_price", "raw_series": "repi_index_2014base + repi_index_2023base",
                        "source": "GASTAT Real Estate Price Index (old 2014=100 to 2021; new 2023=100 from 2022, chained)",
                        "source_url": src_new["source_url"], "vintage": f"{src_old['vintage']}; {src_new['vintage']}",
                        "history": [min(old), max(new)], "projection": None, "retrieved": src_new.get("retrieved") or "2026-10-10",
                        "note": "GASTAT changed method in 2024; the two indices disagree on 2022 (+1.1% old, +12.7% new). "
                                "No published projection: held flat at 2025."})
    out.sort(key=lambda r: (r["series"], r["year"], r["kind"]))
    with (MEV / "mev_annual.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    from backend.whatif_v5.domain import mev
    mev.annual_table.cache_clear()
    mev.annual.cache_clear()
    mev.fill_notes.cache_clear()
    notes = mev.fill_notes()
    for m in series_meta:
        m["name"] = mev.BY_KEY[m["key"]].name
        m["coverage"] = notes.get(m["key"], "")
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(MEV.glob("*.csv"))}
    man = {"domain": "whatif_mev", "country": "Saudi Arabia", "frequency": "annual (calendar year)",
           "retrieved": RETRIEVED, "series": sorted(series_meta, key=lambda m: [s.key for s in mev.SERIES].index(m["key"])),
           "files": files,
           "latest_observations": "latest_observations.csv (dated Brent spot, EIA STEO, GASTAT flash GDP and CPI, PMI, "
                                  "MoF; read by the current-regime block, backend/scenarios/regime.py)",
           "access_note": ("R14 (19 Oct 2026): IMF WEO October 2026 figures for Saudi GDP, CPI, current account and the oil "
                           "assumption replaced the April/July 2026 values (ops/r14_m_mev_refresh.py; each row names its URL). "
                           "The build container could not reach imf.org could not reach imf.org, sama.gov.sa or stats.gov.sa directly. The "
                           "figures were read from public GitHub mirrors of the IMF DataMapper/WEO extracts, the SAMA "
                           "Monthly Statistical Bulletin and GASTAT files, from EIA via datasets/oil-prices, and from "
                           "IMF press releases. ops/whatif_fetch_mev.py re-checks them against the IMF API on a machine "
                           "that can reach it."),
           "scenario_design": {"weights": mev.WEIGHTS, "upturn_sd": mev.UP_SD, "downturn_sd": mev.DOWN_SD,
                               "upturn_profile": mev.UP_PROFILE, "downturn_profile": mev.DOWN_PROFILE}}
    (MEV / "manifest.json").write_text(json.dumps(man, indent=1))
    print(f"mev_annual.csv: {len(out)} rows, {len(series_meta)} series")
    for m in man["series"]:
        print(f"  {m['key']:16s} {m['coverage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
