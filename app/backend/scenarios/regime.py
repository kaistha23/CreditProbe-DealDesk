"""The current macro regime (R14 K12 (1), (4); PLAN_R14 §m (2)): the block every scenario answer opens with.

Read first, before any scenario is recommended or run:
  * the latest Brent price, dated (daily spot from `latest_observations.csv`, else the last EIA monthly average);
  * its 3- and 12-month change (against the EIA monthly average three months earlier, and the dated price a year
    earlier, else the EIA monthly average of the same month a year earlier);
  * the percentile of today's level in the last 35 years of EIA monthly averages (nominal USD);
  * the latest vintages of real GDP, non-oil GDP, CPI and the non-oil PMI;
  * an explicit regime label from deterministic rules (REGIME_RULES), and the oil reversal sizes measured on the
    post-spike reversals in the same 35 years (the peaks detected by `spike_reversals`: 2008–09, 2014–15, 2022–23).

Every figure names its source row (relation `whatif.mev_latest`, `whatif.brent_monthly_eia`, `whatif.mev_annual`) and its
vintage. Nothing here calls a model (N4): the same files give the same block.
"""
from __future__ import annotations

import csv
import datetime as dt
import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5.domain import mev

YEARS = 35
HIGH_PCT = 80.0          # level percentile at or above which oil is "high"
LOW_PCT = 20.0
SHOCK_YOY = 30.0         # a 12-month rise at least this large is a price shock
SLUMP_YOY = -30.0
REVERSAL_MIN = 30.0      # a peak counts as a post-spike reversal when the price fell at least this much ...
REVERSAL_WINDOW = 18     # ... within this many months
SHOCK_GAP = 3            # months of pause allowed inside one shock episode
PEAK_SPAN = 12           # a peak is the highest monthly average within +/- 12 months
SUPPLY_WORDS = ("supply disruption", "attack", "hormuz", "tanker", "export hub", "pipeline")
LATEST_FILE = mev.MEV_DIR / "latest_observations.csv"
RELATIONS = {"latest": "whatif_mev_latest (data/whatif_v5/mev/latest_observations.csv)",
             "monthly": "whatif.brent_monthly_eia (data/whatif_v5/mev/brent_monthly_eia.csv)",
             "annual": "whatif_mev_annual (data/whatif_v5/mev/mev_annual.csv)"}


def mev_annual_rows() -> list[dict[str, Any]]:
    """whatif_mev_annual: the MEV store as a Data Domains relation (K13, N3)."""
    t = mev.annual_table()
    cols = ("series", "year", "kind", "value", "unit", "source", "source_url", "vintage", "retrieved", "note")
    out = []
    for r in t.to_dict("records"):
        row = {k: r.get(k) for k in cols}
        row["year"] = int(row["year"])
        row["value"] = float(row["value"])
        row["version"] = 1
        for k in ("unit", "source", "source_url", "vintage", "retrieved", "note"):
            v = row.get(k)
            row[k] = "" if v is None or (isinstance(v, float) and v != v) else str(v)
        out.append(row)
    return out


def mev_latest_rows() -> list[dict[str, Any]]:
    """whatif_mev_latest: the dated observations as a Data Domains relation (K13, N3)."""
    out = []
    for r in latest_rows():
        out.append({**{k: r.get(k, "") for k in ("series", "date", "unit", "frequency", "kind", "source", "source_url", "vintage",
                                                  "retrieved", "note")},
                    "value": float(r["value"]) if r.get("value") not in (None, "") else None, "version": 1})
    return out

REGIME_RULES = [
    ("supply_shock_high_oil", "supply-shock high-oil regime",
     f"level at or above P{HIGH_PCT:.0f} of {YEARS} years, up at least {SHOCK_YOY:.0f}% in 12 months, and a dated supply-disruption context"),
    ("high_oil_rising", "high-oil, rising regime", f"level at or above P{HIGH_PCT:.0f} and up at least {SHOCK_YOY:.0f}% in 12 months"),
    ("high_oil", "high-oil regime", f"level at or above P{HIGH_PCT:.0f}"),
    ("oil_slump", "oil-slump regime", f"down at least {abs(SLUMP_YOY):.0f}% in 12 months"),
    ("low_oil", "low-oil regime", f"level at or below P{LOW_PCT:.0f}"),
    ("normal", "normal oil regime", "none of the above"),
]


@functools.lru_cache(maxsize=1)
def latest_rows() -> list[dict[str, str]]:
    if not LATEST_FILE.exists():
        return []
    with LATEST_FILE.open() as fh:
        return list(csv.DictReader(fh))


def _rows(series: str) -> list[dict[str, str]]:
    return sorted((r for r in latest_rows() if r["series"] == series), key=lambda r: r["date"])


def monthly() -> pd.Series:
    s = mev.brent_monthly().copy()
    s.index = pd.PeriodIndex(s.index, freq="M")
    return s


def window_35y(last: pd.Period | None = None) -> pd.Series:
    s = monthly()
    last = last or s.index.max()
    return s[(s.index > last - YEARS * 12) & (s.index <= last)]


def percentile_of(level: float, sample: pd.Series) -> float:
    """Share of the months in the sample at or below the level, in % (ties count as below)."""
    return float((sample.to_numpy() <= level).mean() * 100) if len(sample) else float("nan")


def spike_reversals(s: pd.Series | None = None) -> list[dict[str, Any]]:
    """Peaks (highest monthly average within +/- PEAK_SPAN months, level at or above P80 of the 35-year window) followed by
    a fall of at least REVERSAL_MIN % within REVERSAL_WINDOW months. An episode whose window has not closed is left out."""
    s = monthly() if s is None else s
    w = window_35y(s.index.max())
    p80 = float(np.quantile(w.to_numpy(), HIGH_PCT / 100))
    v, idx = s.to_numpy(float), s.index
    out = []
    for i in range(len(s)):
        if idx[i] < w.index.min():
            continue
        lo, hi = max(0, i - PEAK_SPAN), min(len(s), i + PEAK_SPAN + 1)
        if v[i] < p80 or v[i] < v[lo:hi].max() or i + REVERSAL_WINDOW >= len(s):
            continue
        fut = v[i + 1:i + 1 + REVERSAL_WINDOW]
        j = int(fut.argmin())
        fall = (fut[j] / v[i] - 1) * 100
        if fall <= -REVERSAL_MIN:
            twelve = (v[i + 12] / v[i] - 1) * 100
            out.append({"peak": str(idx[i]), "peak_usd": round(float(v[i]), 2), "trough": str(idx[i + 1 + j]),
                        "trough_usd": round(float(fut[j]), 2), "fall_pct": round(float(fall), 1),
                        "months": j + 1, "fall_12m_pct": round(float(twelve), 1),
                        "label": f"{idx[i].year}–{str((idx[i] + 12).year)[2:]}"})
    return out


def _shock_start(s: pd.Series, gap: int = SHOCK_GAP) -> pd.Period | None:
    """First month of the current shock episode: months whose 12-month change is at least SHOCK_YOY %, allowing pauses of
    up to `gap` months (a spike that eases and flares again is one episode). None when the last 6 months hold no such month."""
    yoy = ((s / s.shift(12) - 1) * 100).dropna()
    hit = yoy.ge(SHOCK_YOY).to_numpy()
    if not len(hit) or not hit[-6:].any():
        return None
    i = len(hit) - 1 - int(np.argmax(hit[::-1]))
    first = i
    j = i - 1
    while j >= 0 and i - j <= gap + 1:
        if hit[j]:
            first = i = j
        j -= 1
    return yoy.index[first]


def latest_price() -> dict[str, Any]:
    spot = _rows("brent_spot")
    s = monthly()
    if spot and spot[-1]["date"][:7] > str(s.index.max()):
        r = spot[-1]
        return {"value": float(r["value"]), "date": r["date"], "kind": "daily spot", "source": r["source"],
                "source_url": r["source_url"], "note": r["note"], "relation": RELATIONS["latest"]}
    return {"value": float(s.iloc[-1]), "date": str(s.index.max()), "kind": "EIA monthly average",
            "source": "U.S. EIA Europe Brent spot (RBRTE), monthly average", "source_url": "https://www.eia.gov/dnav/pet/hist/RBRTEM.htm",
            "note": "", "relation": RELATIONS["monthly"]}


def _year_ago(date: str) -> dict[str, Any]:
    d = dt.date.fromisoformat(date if len(date) == 10 else date + "-15")
    target = d.replace(year=d.year - 1)
    for r in _rows("brent_spot"):
        rd = dt.date.fromisoformat(r["date"])
        if abs((rd - target).days) <= 10:
            return {"value": float(r["value"]), "date": r["date"], "source": r["source"], "relation": RELATIONS["latest"]}
    s = monthly()
    p = pd.Period(target.strftime("%Y-%m"), freq="M")
    return {"value": float(s[p]), "date": str(p), "source": "EIA monthly average", "relation": RELATIONS["monthly"]}


def _annual(key: str, year: int) -> dict[str, Any] | None:
    t = mev.annual_table()
    r = t[(t["series"] == key) & (t["year"] == year)]
    if r.empty:
        return None
    x = r.iloc[0]
    return {"year": year, "value": float(x["value"]), "kind": str(x["kind"]), "vintage": str(x["vintage"]),
            "source_url": str(x["source_url"]), "relation": RELATIONS["annual"]}


def _obs(series: str) -> dict[str, Any] | None:
    rows = _rows(series)
    if not rows:
        return None
    r = rows[-1]
    return {"value": float(r["value"]), "date": r["date"], "source": r["source"], "vintage": r["vintage"],
            "source_url": r["source_url"], "note": r["note"], "relation": RELATIONS["latest"]}


def classify(pct: float, yoy: float, supply_context: bool) -> tuple[str, str, str]:
    if pct >= HIGH_PCT and yoy >= SHOCK_YOY and supply_context:
        k = "supply_shock_high_oil"
    elif pct >= HIGH_PCT and yoy >= SHOCK_YOY:
        k = "high_oil_rising"
    elif pct >= HIGH_PCT:
        k = "high_oil"
    elif yoy <= SLUMP_YOY:
        k = "oil_slump"
    elif pct <= LOW_PCT:
        k = "low_oil"
    else:
        k = "normal"
    rule = next(r for r in REGIME_RULES if r[0] == k)
    return k, rule[1], rule[2]


def reversal_sizes(today: float, pre_level: float | None, hist: list[dict[str, Any]]) -> dict[str, Any]:
    """Oil reversal from today's level: mild = half-way back to the pre-shock level, moderate = back to the pre-shock level,
    severe = the median peak-to-trough of the past post-spike reversals. Each as a % fall from today and a USD level."""
    med = float(np.median([h["fall_pct"] for h in hist])) if hist else -40.0
    if pre_level is None or pre_level >= today:
        pre_level = today * (1 + med / 100 / 2)
    mild_lvl = (today + pre_level) / 2
    out = {}
    for sev, lvl, basis in (
            ("mild", mild_lvl, f"half-way back to the pre-shock level (USD {pre_level:.0f})"),
            ("moderate", pre_level, "back to the pre-shock level (the 12 months before the shock)"),
            ("severe", today * (1 + med / 100), f"the median of the {len(hist)} post-spike reversals in {YEARS} years "
                                                f"({', '.join(h['label'] + ' ' + format(h['fall_pct'], '.0f') + '%' for h in hist)})")):
        out[sev] = {"to_usd": round(float(lvl), 1), "fall_pct": round(float((lvl / today - 1) * 100), 1), "basis": basis}
    out["history"] = hist
    out["median_fall_pct"] = round(med, 1)
    return out


@functools.lru_cache(maxsize=1)
def current() -> dict[str, Any]:
    s = monthly()
    lp = latest_price()
    today = lp["value"]
    w = window_35y(s.index.max())
    pct = percentile_of(today, w)
    three = s.index.max() - 2 if lp["kind"] == "daily spot" else s.index.max() - 3
    m3 = float(s[three])
    ya = _year_ago(lp["date"])
    ch3 = (today / m3 - 1) * 100
    ch12 = (today / ya["value"] - 1) * 100
    pub = _obs("brent_spot_yoy_pct")
    ctx = _rows("context")
    ctx_text = ctx[-1]["note"] if ctx else ""
    supply = any(word in ctx_text.lower() for word in SUPPLY_WORDS)
    key, label, rule = classify(pct, ch12, supply)
    start = _shock_start(s)
    pre = None
    if start is not None:
        pre_w = s[(s.index >= start - 12) & (s.index < start)]
        pre = float(pre_w.mean()) if len(pre_w) else None
    hist = spike_reversals(s)
    year = int(lp["date"][:4])
    gdp = _annual("gdp_real", year)
    nonoil = _annual("gdp_nonoil", year)
    cpi = _annual("cpi", year)
    imf_oil = _annual("brent", year)
    imf_oil_next = _annual("brent", year + 1)
    q_gdp, q_nonoil, q_oil = _obs("gdp_real_q_yoy"), _obs("gdp_nonoil_q_yoy"), _obs("gdp_oil_q_yoy")
    pmi, cpi_m = _obs("pmi_nonoil"), _obs("cpi_m_yoy")
    steo = [r for r in _rows("brent_eia_year")]
    bm = mev.brent_monthly()
    ytd = [float(v) for m, v in bm.items() if m.startswith(str(year))]
    growth_flag = gdp is not None and gdp["value"] < 0
    out = {
        "as_of": lp["date"], "regime": key, "label": label, "rule": rule, "supply_context": ctx_text if supply else "",
        "context_source": ({"source": ctx[-1]["source"], "source_url": ctx[-1]["source_url"], "date": ctx[-1]["date"]} if ctx else None),
        "brent": {"latest": lp, "three_months_ago": {"value": m3, "date": str(three), "relation": RELATIONS["monthly"]},
                  "year_ago": ya, "change_3m_pct": round(ch3, 1), "change_12m_pct": round(ch12, 1),
                  "published_12m_pct": (pub["value"] if pub else None), "published_12m_source": (pub["source"] if pub else None),
                  "percentile_35y": round(pct, 1), "window": f"{w.index.min()}–{w.index.max()} ({len(w)} EIA monthly averages, nominal USD)",
                  "p80_35y": round(float(np.quantile(w.to_numpy(), HIGH_PCT / 100)), 1),
                  "median_35y": round(float(w.median()), 1),
                  "last_month": {"value": float(s.iloc[-1]), "month": str(s.index.max())},
                  "ytd_avg": round(float(np.mean(ytd)), 2) if ytd else None, "ytd_months": len(ytd),
                  "shock_start": str(start) if start is not None else None, "pre_shock_level": round(pre, 2) if pre else None,
                  "imf_assumption": {"this_year": imf_oil, "next_year": imf_oil_next},
                  "eia_forecast": [{"year": r["date"][:4], "value": float(r["value"]), "vintage": r["vintage"]} for r in steo]},
        "growth": {"gdp_real": gdp, "gdp_nonoil": nonoil, "cpi": cpi, "gdp_real_quarter": q_gdp, "gdp_nonoil_quarter": q_nonoil,
                   "gdp_oil_quarter": q_oil, "pmi_nonoil": pmi, "cpi_month": cpi_m, "contraction": growth_flag},
        "reversal": reversal_sizes(today, pre, hist),
        "relations": list(RELATIONS.values()),
    }
    out["lines"] = lines(out)
    out["vintage_line"] = vintage_line(out)
    return out


def _fmt_date(d: str) -> str:
    try:
        x = dt.date.fromisoformat(d)
        return f"{x.day} {x.strftime('%b %Y')}"
    except ValueError:
        p = pd.Period(d, freq="M")
        return p.strftime("%b %Y")


def lines(r: dict[str, Any]) -> list[str]:
    """The block in 4 lines (plain words, numbers and dates; deterministic)."""
    b = r["brent"]
    lp = b["latest"]
    g = r["growth"]
    pub = (f"; {b['published_12m_source'].split(',')[0]} publishes {b['published_12m_pct']:+.0f}%"
           if b.get("published_12m_pct") is not None else "")
    l1 = (f"Brent USD {lp['value']:.0f} on {_fmt_date(lp['date'])} ({lp['kind']}): {b['change_3m_pct']:+.0f}% in 3 months, "
          f"{b['change_12m_pct']:+.0f}% in 12 months (from USD {b['year_ago']['value']:.0f}{pub}); higher than "
          f"{b['percentile_35y']:.0f}% of the last {YEARS} years' months.")
    parts = []
    if g["gdp_real"]:
        parts.append(f"real GDP {g['gdp_real']['value']:+.1f}% in {g['gdp_real']['year']} ({g['gdp_real']['vintage']})")
    if g["gdp_real_quarter"]:
        q = g["gdp_real_quarter"]
        parts.append(f"Q2 2026 {q['value']:+.1f}% y/y" + (f", non-oil {g['gdp_nonoil_quarter']['value']:+.1f}%" if g["gdp_nonoil_quarter"] else "")
                     + f" (GASTAT, {_fmt_date(q['vintage'].split()[-1])})")
    if g["pmi_nonoil"]:
        parts.append(f"non-oil PMI {g['pmi_nonoil']['value']:.1f} ({_fmt_date(g['pmi_nonoil']['date'])[3:]})")
    if g["cpi_month"]:
        parts.append(f"CPI {g['cpi_month']['value']:.1f}% ({_fmt_date(g['cpi_month']['date'])[3:]})")
    l2 = "Growth: " + "; ".join(parts) + "." if parts else "Growth: no current vintage in the store."
    l3 = f"Regime: **{r['label']}** (rule: {r['rule']})."
    if r["supply_context"]:
        l3 += f" Context ({_fmt_date(r['context_source']['date'])}): {r['supply_context'].split(';')[0]}."
    rv = r["reversal"]
    if r["regime"] in ("supply_shock_high_oil", "high_oil_rising", "high_oil"):
        l4 = (f"So the oil risk is a **reversal from today's level**, not a fall from the long-run average: back to the pre-shock "
              f"USD {rv['moderate']['to_usd']:.0f} is {rv['moderate']['fall_pct']:.0f}%; past post-spike reversals fell "
              + ", ".join(f"{h['fall_pct']:.0f}% ({h['label']})" for h in rv["history"]) + ".")
    else:
        l4 = "Oil is not at a spike, so the calibrated one-year falls from history apply."
    return [l1, l2, l3, l4]


def vintage_line(r: dict[str, Any]) -> str:
    g = r["growth"]
    v = sorted({x["vintage"] for x in (g["gdp_real"], g["cpi"], g["gdp_nonoil"]) if x})
    return (f"Macro vintage: {'; '.join(v)}; Brent to {_fmt_date(r['brent']['latest']['date'])} "
            f"({r['brent']['latest']['source'].split(',')[0]}), EIA monthly to {r['brent']['last_month']['month']}.")


def is_high(r: dict[str, Any] | None = None) -> bool:
    r = r or current()
    return r["regime"] in ("supply_shock_high_oil", "high_oil_rising", "high_oil")


def block(r: dict[str, Any] | None = None) -> dict[str, Any]:
    """The `regime` block the What-If thread and the Stress Lab render first (a text fallback is in `lines`)."""
    r = r or current()
    b = r["brent"]
    return {"type": "regime", "title": "Current regime", "label": r["label"], "regime": r["regime"], "as_of": r["as_of"],
            "lines": r["lines"], "vintage": r["vintage_line"],
            "tiles": [{"label": "Brent", "value": f"USD {b['latest']['value']:.0f}", "sub": _fmt_date(b["latest"]["date"])},
                      {"label": "3 months", "value": f"{b['change_3m_pct']:+.0f}%"},
                      {"label": "12 months", "value": f"{b['change_12m_pct']:+.0f}%"},
                      {"label": f"Percentile, {YEARS} years", "value": f"P{b['percentile_35y']:.0f}"}],
            "relations": r["relations"]}


def markdown(r: dict[str, Any] | None = None) -> str:
    r = r or current()
    return "**Current regime.** " + " ".join(r["lines"]) + f"\n\n_{r['vintage_line']}_"


def reset() -> None:
    latest_rows.cache_clear()
    current.cache_clear()


def relation_rows(r: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """dd_macro_regime: one row per measure of the block (Data Domains, N3)."""
    r = r or current()
    b, g = r["brent"], r["growth"]
    lp = b["latest"]
    base = {"version": 1, "regime": r["regime"], "regime_label": r["label"]}

    def row(measure, value, unit, as_of, label, source="", url="", vintage="", relation=""):
        return {**base, "measure": measure, "value": (None if value is None else float(value)), "unit": unit, "as_of": str(as_of),
                "label": label, "source": source, "source_url": url, "vintage": vintage, "relation": relation}
    out = [row("brent_latest", lp["value"], "USD/bbl", lp["date"], f"Brent, {lp['kind']}", lp["source"], lp["source_url"],
               lp["date"], lp["relation"]),
           row("brent_change_3m", b["change_3m_pct"], "%", lp["date"], f"Brent against the EIA monthly average of {b['three_months_ago']['date']}",
               "EIA", "", "", RELATIONS["monthly"]),
           row("brent_change_12m", b["change_12m_pct"], "%", lp["date"], f"Brent against {b['year_ago']['date']} (USD {b['year_ago']['value']:.2f})",
               b["year_ago"]["source"], "", "", b["year_ago"]["relation"]),
           row("brent_percentile_35y", b["percentile_35y"], "percentile", lp["date"], f"Level percentile over {b['window']}",
               "EIA", "", "", RELATIONS["monthly"]),
           row("pre_shock_level", b["pre_shock_level"], "USD/bbl", b["shock_start"] or "", "Average of the 12 months before the shock started",
               "EIA", "", "", RELATIONS["monthly"]),
           row("brent_ytd_avg", b["ytd_avg"], "USD/bbl", f"{lp['date'][:4]} ({b['ytd_months']} months)", "Brent average this year to date (EIA monthly)",
               "EIA", "", "", RELATIONS["monthly"])]
    for key, unit in (("gdp_real", "% y/y"), ("gdp_nonoil", "% y/y"), ("cpi", "% y/y")):
        x = g[key]
        if x:
            out.append(row(key, x["value"], unit, x["year"], f"{key.replace('_', ' ')} ({x['kind']})", "IMF", x["source_url"], x["vintage"], x["relation"]))
    for key, unit in (("gdp_real_quarter", "% y/y"), ("gdp_nonoil_quarter", "% y/y"), ("pmi_nonoil", "index"), ("cpi_month", "% y/y")):
        x = g[key]
        if x:
            out.append(row(key, x["value"], unit, x["date"], key.replace("_", " "), x["source"], x["source_url"], x["vintage"], x["relation"]))
    for sev in ("mild", "moderate", "severe"):
        rv = r["reversal"][sev]
        out.append(row(f"reversal_{sev}", rv["fall_pct"], "%", lp["date"], f"Oil reversal {sev}: to USD {rv['to_usd']:.1f} ({rv['basis']})",
                       "EIA", "", "", RELATIONS["monthly"]))
    out.append(row("regime", None, "", lp["date"], f"{r['label']}: {r['rule']}", r["context_source"]["source"] if r["context_source"] else "",
                   r["context_source"]["source_url"] if r["context_source"] else "", "", RELATIONS["latest"]))
    return out
