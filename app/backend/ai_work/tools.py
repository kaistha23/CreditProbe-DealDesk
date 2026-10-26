"""The query tools a scoped conversation may call. Every figure an answer quotes comes from one of these.

Each tool reads one data domain read-only and returns a `Result`: a factual sentence, figures, at most one table,
citations (links that open the screen the figures come from), report blocks (for Playbook) and every number it
produced (what the validate stage checks an answer against).

Domains: corporate, retail (Cockpit books), ews (Early Warning), whatif (What-If engine and library), scorecard
(Scorecard Validation), b360 (Borrower 360), bureau, open_banking, product (product knowledge), documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.workspace_v5 import compute, paths
from backend.workspace_v5.book import mn, pct

DOMAINS: dict[str, str] = {
    "corporate": "Cockpit corporate book",
    "retail": "Cockpit retail book",
    "ews": "Early Warning",
    "whatif": "What-If",
    "bureau": "Bureau",
    "open_banking": "Open Banking",
    "scorecard": "Scorecard",
    "b360": "Borrower 360",
    "product": "CreditProbe product knowledge",
}
BOOKS = ("corporate", "retail")
BAND_ORDER = ["critical", "severe", "high", "moderate", "low", "none"]


@dataclass
class Result:
    tool: str
    args: dict[str, Any]
    domain: str
    text: str
    figures: list[dict[str, Any]] = field(default_factory=list)
    table: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def for_model(self) -> dict[str, Any]:
        """What the model sees: facts and rows, never more than it needs."""
        t = None
        if self.table:
            t = {"title": self.table.get("title"), "columns": [c["key"] for c in self.table["columns"]],
                 "rows": self.table["rows"][:25]}
        return {"tool": self.tool, "domain": self.domain, "facts": self.text, "figures": self.figures[:12],
                "table": t, "links": [c for c in self.citations if c.get("href")][:4], **self.extra}


class ToolError(ValueError):
    pass


def _nums(*vals: Any) -> list[float]:
    out: list[float] = []
    for v in vals:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, dict):
            out += _nums(*v.values())
        elif isinstance(v, (list, tuple)):
            out += _nums(*v)
        elif isinstance(v, str):
            out += [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", v)
                    if x.replace(",", "").replace(".", "").lstrip("-")]
    return out


# ------------------------------------------------------------------ books


def _prev(book: str, period: str) -> str | None:
    ps = compute.periods(book)
    i = ps.index(period)
    return ps[i - 1] if i > 0 else None


@lru_cache(maxsize=2)
def segments(book: str) -> tuple[str, ...]:
    col = "sector" if book == "corporate" else "product"
    return tuple(sorted(str(v) for v in compute.frame(book)[col].unique()))


def book_figures(book: str, period: str | None = None, segment: str | None = None, by: str | None = None,
                 measures: list[str] | None = None) -> Result:
    """EAD, ECL, coverage and stage mix on a Cockpit book, with the movement on the prior period."""
    if book not in BOOKS:
        raise ToolError(f"{book!r} is not a Cockpit book.")
    col = "sector" if book == "corporate" else "product"
    period = compute.resolve(book, period)
    measures = measures or ["ead", "ecl", "coverage_pct", "stage2_share_pct", "stage3_ead"]
    spec: dict[str, Any] = {"engine": "book", "book": book, "by": by, "measures": measures}
    if segment:
        spec["filters"] = {col: [segment]}
    now = compute.book_result(spec, period)
    prev_p = _prev(book, period)
    before = compute.book_result(spec, prev_p) if prev_p else None
    unit = {"sar_mn": mn, "pct": lambda v: pct(v, 2), "int": lambda v: f"{int(v):,}"}
    bf = {f["key"]: f for f in (before or {}).get("figures", [])}
    parts = []
    figures = []
    for f in now["figures"]:
        s = f"{f['label']} {unit[f['unit']](f['value'])}"
        fig = dict(f)
        if f["key"] in bf and prev_p:
            old = bf[f["key"]]["value"]
            fig["previous"] = old
            if f["unit"] == "sar_mn":
                ch = f["value"] - old
                s += f" ({'+' if ch >= 0 else '-'}{mn(abs(ch))} on {prev_p}" + (f", {ch / old * 100:+.1f}%" if old else "") + ")"
                fig["change"] = ch
            else:
                s += f" ({unit[f['unit']](old)} at {prev_p})"
        parts.append(s)
        figures.append(fig)
    scope = f"{segment}, {book} book" if segment else f"{book.capitalize()} book"
    text = f"{scope} at {period}: " + "; ".join(parts) + "."
    table = None
    if by and now["table"]:
        t = now["table"]
        table = {"title": f"{compute.MEASURES[measures[0]][0]} by {compute.BOOKS[book]['dims'][by].lower()}, {period}",
                 "columns": t["columns"], "rows": t["rows"], "key": by}
        m0 = measures[0]
        u0 = unit[compute.MEASURES[m0][1]]
        text += (f" By {compute.BOOKS[book]['dims'][by].lower()}: "
                 + "; ".join(f"{r[by]} {u0(r[m0])}" for r in t["rows"][:6]) + ("; …" if len(t["rows"]) > 6 else "") + ".")
    href = f"/cockpit?domain={book}"
    return Result("book_figures", {"book": book, "period": period, "segment": segment, "by": by}, book, text,
                  figures, table, [{"kind": "data", "label": f"{DOMAINS[book]} · {period}", "href": href}],
                  numbers=_nums(figures, table["rows"] if table else [], text),
                  extra={"period": period, "previous_period": prev_p})


def ecl_movement(book: str, period: str | None = None, segment: str | None = None, by: str | None = None) -> Result:
    """What moved ECL on the prior period: the change by a dimension (sub-sector or sector, product, stage), largest
    contributors first, with each one's share of the total change."""
    if book not in BOOKS:
        raise ToolError(f"{book!r} is not a Cockpit book.")
    col = "sector" if book == "corporate" else "product"
    by = by or (("sub_sector" if book == "corporate" else "sub_product") if segment else col)
    if by not in compute.BOOKS[book]["dims"]:
        raise ToolError(f"'{by}' is not a dimension of the {book} book.")
    period = compute.resolve(book, period)
    prev = _prev(book, period)
    if not prev:
        raise ToolError(f"There is no period before {period}.")
    spec: dict[str, Any] = {"engine": "book", "book": book, "by": by, "measures": ["ecl"]}
    if segment:
        spec["filters"] = {col: [segment]}
    now, before = compute.book_result(spec, period), compute.book_result(spec, prev)
    b = {r[by]: r["ecl"] for r in before["table"]["rows"]}
    rows = [{by: r[by], "ecl_before": round(b.get(r[by], 0.0), 2), "ecl_now": round(r["ecl"], 2),
             "change": round(r["ecl"] - b.get(r[by], 0.0), 2)} for r in now["table"]["rows"]]
    total = sum(r["change"] for r in rows)
    for r in rows:
        r["share_of_change_pct"] = round(r["change"] / total * 100, 1) if total else 0.0
    rows.sort(key=lambda r: -abs(r["change"]))
    label = compute.BOOKS[book]["dims"][by]
    where = f"{segment} ({book} book)" if segment else f"the {book} book"
    top = rows[:3]
    text = (f"ECL on {where} moved {'+' if total >= 0 else '-'}{mn(abs(total))} from {prev} to {period}. "
            f"By {label.lower()}, the largest contributors: "
            + "; ".join(f"{r[by]} {'+' if r['change'] >= 0 else '-'}{mn(abs(r['change']))} "
                        f"({r['share_of_change_pct']:.1f}% of the change)" for r in top) + ".")
    table = {"title": f"ECL movement by {label.lower()}, {prev} to {period}", "key": by, "rows": rows,
             "columns": [{"key": by, "label": label, "unit": "text"},
                         {"key": "ecl_before", "label": f"ECL {prev}", "unit": "sar_mn"},
                         {"key": "ecl_now", "label": f"ECL {period}", "unit": "sar_mn"},
                         {"key": "change", "label": "Change", "unit": "sar_mn"},
                         {"key": "share_of_change_pct", "label": "Share of change", "unit": "pct"}]}
    chart = {"kind": "chart", "title": f"ECL change by {label.lower()}, {prev} to {period} (SAR m)",
             "figure": {"data": [{"type": "bar", "orientation": "h", "x": [r["change"] for r in rows[:12]][::-1],
                                  "y": [str(r[by]) for r in rows[:12]][::-1], "marker": {"color": "#1F4E6B"}}],
                        "layout": {"margin": {"l": 180}}}}
    return Result("ecl_movement", {"book": book, "period": period, "segment": segment, "by": by}, book, text,
                  [{"key": "ecl_change", "label": f"ECL change {prev} to {period}", "value": total, "unit": "sar_mn"}],
                  table, [{"kind": "data", "label": f"{DOMAINS[book]} · {prev} to {period}", "href": f"/cockpit?domain={book}"}],
                  blocks=[chart], numbers=_nums(rows, total, text), extra={"period": period, "previous_period": prev})


# ----------------------------------------------------------- early warning


@lru_cache(maxsize=4)
def _ews(book: str) -> pd.DataFrame:
    if book == "corporate":
        cols = ["facility_id", "borrower_id", "borrower_name", "reporting_quarter", "sector", "region", "ead_sar_mn",
                "ecl_sar_mn", "stage", "dpd_days", "ews_score", "ews_band", "ews_reasons"]
        return pd.read_parquet(paths.EWS / paths.EWS_CORP / "ews_corp_exposure.parquet", columns=cols)
    d = pd.read_parquet(paths.EWS / paths.EWS_RETAIL / "ews_retail_exposure.parquet")
    keep = [c for c in ["account_id", "customer_id", "reporting_month", "product", "region", "ead_sar_mn", "ecl_sar_mn",
                        "stage", "dpd_days", "ews_score", "ews_band", "ews_reasons"] if c in d.columns]
    return d[keep]


def _ews_period(book: str, period: str | None) -> str:
    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
    ps = sorted(_ews(book)[pcol].unique())
    if period and period in ps:
        return period
    return str(ps[-1])


def ews_clients(book: str = "corporate", bands: list[str] | None = None, stage: int | None = None,
                segment: str | None = None, n: int = 10, period: str | None = None, closest: bool = True) -> Result:
    """Named Early Warning clients: ID, name, segment, band, score, EAD, ECL, stage and the warning reasons."""
    bands = [b.lower() for b in (bands or ["high", "critical"])]
    d = _ews(book)
    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
    owner = "borrower_id" if book == "corporate" else "customer_id"
    seg_col = "sector" if book == "corporate" else "product"
    period = _ews_period(book, period)
    q = d[d[pcol] == period]
    if segment:
        q = q[q[seg_col] == segment]
    # A client's band and score are its worst facility's; its stage is its worst stage.
    worst = q.sort_values("ews_score", ascending=False).drop_duplicates(owner).set_index(owner)
    agg = {"ead": ("ead_sar_mn", "sum"), "ecl": ("ecl_sar_mn", "sum"), "stage": ("stage", "max")}
    g = q.groupby(owner).agg(**agg)
    g["band"] = worst.ews_band
    g["score"] = worst.ews_score
    g["reasons"] = worst.ews_reasons.astype(str) if "ews_reasons" in worst else ""
    g["segment"] = worst[seg_col]
    if book == "corporate":
        g["name"] = worst.borrower_name
    g = g[g.band.isin(bands)]
    if stage is not None:
        g = g[g.stage == stage]
    total = len(g)
    g = g.reset_index().sort_values(["score", "ead"], ascending=[False, False]).head(max(1, min(int(n), 50)))
    rows = []
    for r in g.itertuples():
        reasons = [x.strip() for x in re.split(r";|\|", str(r.reasons)) if x.strip() and x.strip() != "nan"]
        row = {"id": getattr(r, owner), "segment": str(r.segment), "band": str(r.band).capitalize(),
               "score": round(float(r.score), 1), "ead": round(float(r.ead), 2), "ecl": round(float(r.ecl), 2),
               "stage": int(r.stage), "reasons": "; ".join(reasons[:3])}
        if book == "corporate":
            row = {"id": row["id"], "name": str(r.name), **{k: v for k, v in row.items() if k != "id"}}
        rows.append(row)
    who = "borrowers" if book == "corporate" else "customers"
    cols = [{"key": "id", "label": "Borrower" if book == "corporate" else "Customer", "unit": "text"},
            *([{"key": "name", "label": "Name", "unit": "text"}] if book == "corporate" else []),
            {"key": "segment", "label": "Sector" if book == "corporate" else "Product", "unit": "text"},
            {"key": "band", "label": "Band", "unit": "text"}, {"key": "score", "label": "Score", "unit": "num"},
            {"key": "ead", "label": "EAD", "unit": "sar_mn"}, {"key": "ecl", "label": "ECL", "unit": "sar_mn"},
            {"key": "stage", "label": "Stage", "unit": "int"}, {"key": "reasons", "label": "Reasons", "unit": "text"}]
    band_words = " or ".join(bands)
    filt = (f" in Stage {stage}" if stage is not None else "") + (f" in {segment}" if segment else "")
    text = ((f"{total:,} {book} {who} carry" if total else f"No {book} {who[:-1]} carries")
            + f" a {band_words} Early Warning{filt} at {period}"
            + (f"; the {len(rows)} with the highest score are listed" if rows else "") + ".")
    if rows:
        top = rows[0]
        text += (f" The highest is {top['id']}" + (f" ({top['name']})" if top.get("name") else "")
                 + f", score {top['score']:.1f}, EAD {mn(top['ead'])}.")
    table = {"title": f"{band_words.capitalize()} Early Warning {who}{filt}, {period}", "columns": cols,
             "rows": rows, "key": "id"}
    href = f"/early-warning?domain={book}" + (f"&segment={segment}" if segment else "")
    if not total and closest:
        # The list asked for is empty: say where those clients sit, and give the closest real list.
        relaxed = ["moderate", "low"] if set(bands) & {"high", "critical"} else ["low"]
        alt = ews_clients(book, relaxed, stage, segment, n, period, closest=False)
        mix = ews_stage_mix(book, bands, period, segment)
        text = f"{text} {mix}"
        if alt.extra.get("count"):
            text += " Closest list: " + alt.text
            table = dict(alt.table, title="Closest: " + alt.table["title"])
            rows = alt.table["rows"]
    return Result("ews_clients", {"book": book, "bands": bands, "stage": stage, "segment": segment, "n": n,
                                  "period": period}, "ews", text,
                  [{"key": "count", "label": f"{band_words.capitalize()} {who}{filt}", "value": total, "unit": "int"}],
                  table, [{"kind": "data", "label": f"Early Warning · {book} · {period}", "href": href}],
                  numbers=_nums(rows, total, text), extra={"period": period, "count": total})


def ews_stage_mix(book: str, bands: list[str], period: str | None = None, segment: str | None = None) -> str:
    """Where the clients in these bands sit by IFRS 9 stage (one sentence)."""
    d = _ews(book)
    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
    owner = "borrower_id" if book == "corporate" else "customer_id"
    seg_col = "sector" if book == "corporate" else "product"
    period = _ews_period(book, period)
    q = d[d[pcol] == period]
    if segment:
        q = q[q[seg_col] == segment]
    st = q.groupby(owner).stage.max()
    w = q.sort_values("ews_score", ascending=False).drop_duplicates(owner).set_index(owner)
    w = w[w.ews_band.isin(bands)]
    mix = st[st.index.isin(w.index)].value_counts().sort_index()
    who = "borrowers" if book == "corporate" else "customers"
    return (f"The {int(mix.sum()):,} {' or '.join(bands)} {who} sit in " +
            ", ".join(f"Stage {int(k)} ({int(v):,})" for k, v in mix.items()) +
            ": the rule set's staging and default triggers raise a high band only once a name has left Stage 1."
            if len(mix) else f"No {who} carry a {' or '.join(bands)} warning.")


def ews_headline(book: str = "corporate", period: str | None = None, segment: str | None = None) -> Result:
    """Clients and EAD by Early Warning band, against the prior period."""
    d = _ews(book)
    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
    owner = "borrower_id" if book == "corporate" else "customer_id"
    seg_col = "sector" if book == "corporate" else "product"
    period = _ews_period(book, period)
    ps = sorted(d[pcol].unique())
    prior = ps[ps.index(period) - 1] if ps.index(period) > 0 else None

    def by_band(p: str) -> dict[str, tuple[int, float]]:
        q = d[d[pcol] == p]
        if segment:
            q = q[q[seg_col] == segment]
        w = q.sort_values("ews_score", ascending=False).drop_duplicates(owner)
        e = q.groupby(owner).ead_sar_mn.sum()
        w = w.assign(ead=w[owner].map(e))
        g = w.groupby("ews_band").agg(n=(owner, "count"), ead=("ead", "sum"))
        return {str(b): (int(g.loc[b, "n"]), float(g.loc[b, "ead"])) for b in g.index}

    now, before = by_band(period), (by_band(prior) if prior else {})
    bands = [b for b in BAND_ORDER if b in now] + [b for b in now if b not in BAND_ORDER]
    rows = [{"band": b.capitalize(), "clients": now[b][0], "ead": round(now[b][1], 2),
             "prior": before.get(b, (0, 0.0))[0]} for b in bands]
    hc = sum(now.get(b, (0, 0))[0] for b in ("high", "critical", "severe"))
    hc0 = sum(before.get(b, (0, 0))[0] for b in ("high", "critical", "severe"))
    who = "borrowers" if book == "corporate" else "customers"
    where = f"{segment} ({book})" if segment else f"the {book} book"
    text = (f"Early Warning on {where} at {period}: " + "; ".join(f"{r['band'].lower()} {r['clients']:,} {who} "
                                                                 f"({mn(r['ead'])})" for r in rows)
            + (f". High and critical: {hc:,}, against {hc0:,} at {prior}." if prior else "."))
    table = {"title": f"Early Warning bands, {where}, {period}", "key": "band", "rows": rows,
             "columns": [{"key": "band", "label": "Band", "unit": "text"},
                         {"key": "clients", "label": who.capitalize(), "unit": "int"},
                         {"key": "ead", "label": "EAD", "unit": "sar_mn"},
                         {"key": "prior", "label": f"{who.capitalize()} at {prior}", "unit": "int"}]}
    chart = {"kind": "chart", "title": f"{who.capitalize()} by Early Warning band, {prior} and {period}",
             "figure": {"data": [{"type": "bar", "name": str(prior), "x": [r["band"] for r in rows],
                                  "y": [r["prior"] for r in rows], "marker": {"color": "#9DB7C9"}},
                                 {"type": "bar", "name": period, "x": [r["band"] for r in rows],
                                  "y": [r["clients"] for r in rows], "marker": {"color": "#1F4E6B"}}],
                        "layout": {"barmode": "group", "legend": {"orientation": "h"}}}}
    href = f"/early-warning?domain={book}" + (f"&segment={segment}" if segment else "")
    return Result("ews_headline", {"book": book, "period": period, "segment": segment}, "ews", text,
                  [{"key": "high_critical", "label": "High and critical", "value": hc, "unit": "int",
                    "previous": hc0}], table,
                  [{"kind": "data", "label": f"Early Warning · {book} · {period}", "href": href}],
                  blocks=[chart], numbers=_nums(rows, hc, hc0, text), extra={"period": period, "prior": prior})


# ----------------------------------------------------------------- what-if

_SCENARIO_WORDS = {
    "corporate": [("oil", "oil-shock"), ("rate", "rates-up"), ("saibor", "rates-up"), ("recession", "recession"),
                  ("downgrade", "downgrade-1"), ("notch", "downgrade-1"), ("construction", "construction"),
                  ("real estate", "real-estate"), ("collateral", "real-estate"), ("lgd", "parameters"),
                  ("pd +", "parameters"), ("parameter", "parameters"), ("stage 2", "migration"),
                  ("migration", "migration")],
    "retail": [("unemployment", "unemployment"), ("rate", "rates-up"), ("house", "house-prices"),
               ("mortgage", "house-prices"), ("card", "cards"), ("score", "score-band"), ("recession", "recession")],
}


def whatif_library(book: str = "corporate") -> Result:
    from backend.whatif_v5.chat import library
    rows = [{"key": e["key"], "name": e["name"], "description": e["description"]} for e in library.STANDARD[book]]
    text = f"What-If library for the {book} book: " + "; ".join(f"{r['name']} ({r['description']})" for r in rows) + "."
    return Result("whatif_library", {"book": book}, "whatif", text, [],
                  {"title": f"What-If scenarios, {book} book", "key": "key", "rows": rows,
                   "columns": [{"key": "name", "label": "Scenario", "unit": "text"},
                               {"key": "description", "label": "Definition", "unit": "text"}]},
                  [{"kind": "data", "label": "What-If library", "href": f"/what-if?domain={book}"}],
                  numbers=_nums(text))


def scenario_key(book: str, text: str) -> str | None:
    t = text.lower()
    return next((k for w, k in _SCENARIO_WORDS.get(book, []) if w in t), None)


def whatif_scenario(book: str = "corporate", key: str | None = None, text: str = "", period: str | None = None) -> Result:
    """Run a library scenario through the What-If engine (Delta method): ECL before and after, the waterfall by
    step, and the change by segment."""
    from backend.whatif_v5.chat import library
    entries = {e["key"]: e for e in library.STANDARD[book]}
    key = key if key in entries else scenario_key(book, text)
    if not key:
        raise ToolError("no scenario named")
    e = entries[key]
    sc = library.scenario_for(book, e, "")
    spec = {"engine": "whatif", "book": book, "method": "delta", "scenario": sc.to_dict()}
    try:
        res = compute.whatif_result(spec, period)
    except compute.ComputeError:
        res = compute.whatif_result(spec, None)
    f = {x["key"]: x["value"] for x in res["figures"]}
    rows = res["table"]["rows"]
    top = rows[:3]
    text_out = (f"What-If '{e['name']}' ({e['description']}) on the {book} book at {res['period']}, Delta method: "
                f"ECL {mn(f['reported_ecl'])} → {mn(f['scenario_ecl'])} ({'+' if f['change'] >= 0 else '-'}"
                f"{mn(abs(f['change']))}, {f['change_pct']:+.2f}%); coverage {pct(f['coverage_before'], 2)} → "
                f"{pct(f['coverage_after'], 2)}. Largest moves: "
                + "; ".join(f"{r['segment']} {'+' if r['change'] >= 0 else '-'}{mn(abs(r['change']))}" for r in top) + ".")
    steps = res.get("steps") or []
    wf_x, wf_y, wf_m = ["Reported ECL"], [round(f["reported_ecl"], 2)], ["absolute"]
    for s in steps:
        ch = s.get("change") if isinstance(s, dict) else None
        if ch is None and isinstance(s, dict):
            ch = (s.get("ecl_after") or 0) - (s.get("ecl_before") or 0) if "ecl_after" in s else None
        if ch is not None:
            wf_x.append(str(s.get("label") or s.get("restatement") or s.get("instruction") or "Step"))
            wf_y.append(round(float(ch), 2))
            wf_m.append("relative")
    if len(wf_x) == 1:
        wf_x.append(e["name"])
        wf_y.append(round(f["change"], 2))
        wf_m.append("relative")
    wf_x.append("Scenario ECL")
    wf_y.append(round(f["scenario_ecl"], 2))
    wf_m.append("total")
    lo, hi = min(f["reported_ecl"], f["scenario_ecl"]), max(f["reported_ecl"], f["scenario_ecl"])
    pad = max((hi - lo) * 0.6, hi * 0.01)
    waterfall = {"kind": "chart", "title": f"ECL waterfall, {e['name']} (SAR m)",
                 "figure": {"data": [{"type": "waterfall", "x": wf_x, "y": wf_y, "measure": wf_m,
                                      "connector": {"line": {"color": "#9DB7C9"}},
                                      "increasing": {"marker": {"color": "#C2410C"}},
                                      "decreasing": {"marker": {"color": "#5B8C5A"}},
                                      "totals": {"marker": {"color": "#1F4E6B"}}}],
                            "layout": {"showlegend": False,
                                       "yaxis": {"range": [round(lo - pad, 1), round(hi + pad, 1)]}}}}
    table = {"title": f"ECL change by {res['table']['columns'][0]['label'].lower()}, {e['name']}",
             "columns": res["table"]["columns"], "rows": rows, "key": "segment"}
    return Result("whatif_scenario", {"book": book, "key": key, "period": res["period"]}, "whatif", text_out,
                  res["figures"], table,
                  [{"kind": "data", "label": f"What-If · {e['name']}", "href": f"/what-if?domain={book}"}],
                  blocks=[waterfall], numbers=_nums(res["figures"], rows, wf_y, text_out),
                  extra={"scenario": e["name"], "period": res["period"], "run_id": res.get("run_id")})


# --------------------------------------------------------------- scorecard


def scorecard_overview(scorecard: str | None = None) -> Result:
    """The scorecards and their latest validation: verdict, test counts, Gini and the findings with their remedies."""
    from backend.scorecard_v5 import engine
    from backend.scorecard_v5.api import store as sc_store
    st = sc_store()
    vals = st.validations()
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for c in engine.scorecards():
        sid, name = c["scorecard_id"], c.get("name") or c["scorecard_id"]
        if scorecard and scorecard.lower() not in f"{sid} {name}".lower():
            continue
        v = next((x for x in vals if x.get("scorecard_id") == sid), None)
        if not v:
            rows.append({"scorecard": name, "verdict": "Not validated", "red": 0, "amber": 0, "green": 0, "gini": None})
            continue
        full = st.validation(v["validation_id"]) or {}
        res = full.get("result") or {}
        cnt = v.get("counts") or {}
        gini = next((t.get("value") for sec in res.get("sections") or [] for t in sec.get("tests") or []
                     if t.get("id") == "gini"), None)
        rows.append({"scorecard": name, "verdict": str(v.get("overall", "")).capitalize(), "red": int(cnt.get("red", 0)),
                     "amber": int(cnt.get("amber", 0)), "green": int(cnt.get("green", 0)),
                     "gini": round(float(gini) * 100, 1) if gini is not None else None,
                     "validation_id": v["validation_id"]})
        for f in res.get("findings") or []:
            if f.get("status") in ("red", "amber"):
                findings.append({"scorecard": name, "status": f["status"], "test": f.get("label", f.get("test")),
                                 "finding": f.get("text", ""), "action": f.get("action", "")})
    findings.sort(key=lambda f: 0 if f["status"] == "red" else 1)
    text = ("Latest validations: " + "; ".join(
        f"{r['scorecard']} {r['verdict'].lower()} ({r['red']} red, {r['amber']} amber, {r['green']} green"
        + (f", Gini {r['gini']:.1f}%" if r.get("gini") is not None else "") + ")" for r in rows) + ".")
    if findings:
        text += " Main findings: " + " ".join(f"{f['scorecard']}, {f['test']} ({f['status']}): {f['finding']} "
                                              f"Remedy: {f['action']}" for f in findings[:4])
    table = {"title": "Scorecard validation verdicts", "key": "scorecard", "rows": rows,
             "columns": [{"key": "scorecard", "label": "Scorecard", "unit": "text"},
                         {"key": "verdict", "label": "Verdict", "unit": "text"},
                         {"key": "red", "label": "Red", "unit": "int"}, {"key": "amber", "label": "Amber", "unit": "int"},
                         {"key": "green", "label": "Green", "unit": "int"},
                         {"key": "gini", "label": "Gini %", "unit": "num"}]}
    return Result("scorecard_overview", {"scorecard": scorecard}, "scorecard", text, [], table,
                  [{"kind": "data", "label": "Scorecard Validation", "href": "/scorecard-validation"}],
                  numbers=_nums(rows, text, [f["finding"] for f in findings]), extra={"findings": findings[:8]})


# ------------------------------------------------------------ borrower 360


def borrower_profile(borrower_id: str) -> Result:
    """One corporate borrower: rating, sector, exposure, ECL, stage, Early Warning band and reasons."""
    from backend.playbook_v5 import content
    bid = borrower_id.upper()
    e = content.corp()
    q = e[(e.borrower_id == bid) & (e.reporting_quarter == content.CORP_PERIOD)]
    if q.empty:
        raise ToolError(f"There is no corporate borrower {bid} at {content.CORP_PERIOD}.")
    b = content.borrowers()
    bq = b[(b.borrower_id == bid) & (b.reporting_quarter == content.CORP_PERIOD)]
    rating = str(bq.rating_current.iloc[-1]) if len(bq) and "rating_current" in bq else ""
    worst = q.sort_values("ews_score", ascending=False).iloc[0]
    ead, ecl = float(q.ead_sar_mn.sum()), float(q.ecl_sar_mn.sum())
    reasons = [x.strip() for x in str(worst.ews_reasons).split(";") if x.strip() and x.strip() != "nan"]
    name = str(worst.borrower_name)
    text = (f"{bid} {name} ({worst.sector}, {worst.region}) at {content.CORP_PERIOD}: rating {rating or 'n/a'}; "
            f"{len(q)} facilities; EAD {mn(ead)}; ECL {mn(ecl)} (coverage {pct(ecl / ead * 100 if ead else 0, 2)}); "
            f"Stage {int(q.stage.max())}; Early Warning {str(worst.ews_band)} (score {float(worst.ews_score):.1f})"
            + (f"; reasons: {'; '.join(reasons[:3])}" if reasons else "") + ".")
    rows = [{"facility": r.facility_id, "ead": round(float(r.ead_sar_mn), 2), "ecl": round(float(r.ecl_sar_mn), 2),
             "stage": int(r.stage), "dpd": int(r.dpd_days), "band": str(r.ews_band).capitalize()}
            for r in q.sort_values("ead_sar_mn", ascending=False).itertuples()]
    table = {"title": f"{bid} facilities, {content.CORP_PERIOD}", "key": "facility", "rows": rows,
             "columns": [{"key": "facility", "label": "Facility", "unit": "text"},
                         {"key": "ead", "label": "EAD", "unit": "sar_mn"}, {"key": "ecl", "label": "ECL", "unit": "sar_mn"},
                         {"key": "stage", "label": "Stage", "unit": "int"}, {"key": "dpd", "label": "DPD", "unit": "int"},
                         {"key": "band", "label": "Early Warning", "unit": "text"}]}
    return Result("borrower_profile", {"borrower_id": bid}, "b360", text,
                  [{"key": "ead", "label": "EAD", "value": ead, "unit": "sar_mn"},
                   {"key": "ecl", "label": "ECL", "value": ecl, "unit": "sar_mn"}], table,
                  [{"kind": "data", "label": f"Borrower 360 · {bid}", "href": f"/borrower-360?borrower={bid}"}],
                  numbers=_nums(rows, ead, ecl, ecl / ead * 100 if ead else 0, text), extra={"name": name})


# --------------------------------------------------------------- documents


def document_passages(question: str, documents: list[dict[str, Any]], context: str = "") -> Result:
    from backend.workspace_v5.responder import passages
    found = passages(question, documents, limit=3, context=context)
    text = " ".join(f"“{p['text']}” ({p['name']})" for p in found)
    return Result("document_passages", {"question": question[:200]}, "documents", text, [], None,
                  [{"kind": "document", "label": p["name"], "doc_id": p["doc_id"]} for p in found],
                  numbers=_nums(text), extra={"passages": found})


# ---------------------------------------------------------------- product


def product_walkthrough(module: str = "", question: str = "") -> Result:
    """How a CreditProbe module works: what it is, the flow step by step with links, a worked example on the books."""
    from backend.ai_work import knowledge
    m = knowledge.module_with_example(module) if module else None
    if m is None:
        m = knowledge.find(question or module)
    if m is None:
        names = ", ".join(x["name"] for x in knowledge.modules())
        return Result("product_walkthrough", {"module": module}, "product",
                      f"CreditProbe's modules: {names}. Name one and I will walk you through it with a worked example "
                      "on the books.", numbers=[])
    w = knowledge.walkthrough(m["id"])
    return Result("product_walkthrough", {"module": m["id"]}, "product", w["markdown"], [], None,
                  [{"kind": "screen", "label": x["label"], "href": x["href"]} for x in w["links"]],
                  numbers=_nums(w["markdown"]), extra={"module": m["id"], "as_of": w["as_of"]})


# --------------------------------------------------------------- registry

#: name -> (function, domain it needs, description for the model, JSON schema of its arguments)
REGISTRY: dict[str, tuple[Any, str, str, dict[str, Any]]] = {
    "book_figures": (book_figures, "book", "EAD, ECL, coverage, Stage 2 share and Stage 3 EAD on a Cockpit book, "
                     "optionally for one sector (corporate) or product (retail) and broken down by a dimension, with "
                     "the movement on the prior period.",
                     {"type": "object", "properties": {
                         "book": {"type": "string", "enum": ["corporate", "retail"]},
                         "period": {"type": "string", "description": "2026Q2 (corporate) or 2026-08 (retail); omit for the latest"},
                         "segment": {"type": "string", "description": "a sector (corporate) or product (retail)"},
                         "measures": {"type": "array", "items": {"type": "string", "enum": [
                             "ead", "ecl", "coverage_pct", "stage2_ead", "stage2_share_pct", "stage3_ead", "stage2_ecl",
                             "stage3_ecl", "count", "owners"]}},
                         "by": {"type": "string", "enum": ["sector", "sub_sector", "region", "product_type", "stage",
                                                           "product", "sub_product", "score_band", "employment_type"]}},
                      "required": ["book"]}),
    "ecl_movement": (ecl_movement, "book", "What moved ECL against the prior period: the change by sub-sector or "
                     "sector (corporate), product (retail) or stage, largest contributors first with their share.",
                     {"type": "object", "properties": {
                         "book": {"type": "string", "enum": ["corporate", "retail"]}, "period": {"type": "string"},
                         "segment": {"type": "string"},
                         "by": {"type": "string", "enum": ["sector", "sub_sector", "region", "product_type", "stage",
                                                           "product", "sub_product", "score_band"]}},
                      "required": ["book"]}),
    "ews_clients": (ews_clients, "ews", "Named Early Warning clients with ID, name, band, score, EAD, ECL, stage and "
                    "reasons; filter by band, IFRS 9 stage and segment.",
                    {"type": "object", "properties": {
                        "book": {"type": "string", "enum": ["corporate", "retail"]},
                        "bands": {"type": "array", "items": {"type": "string", "enum": ["critical", "high", "moderate", "low"]}},
                        "stage": {"type": "integer", "enum": [1, 2, 3]},
                        "segment": {"type": "string"}, "n": {"type": "integer", "minimum": 1, "maximum": 50}},
                     "required": ["book"]}),
    "ews_headline": (ews_headline, "ews", "Clients and EAD by Early Warning band against the prior period.",
                     {"type": "object", "properties": {"book": {"type": "string", "enum": ["corporate", "retail"]},
                                                       "segment": {"type": "string"}}, "required": ["book"]}),
    "whatif_library": (whatif_library, "whatif", "The What-If standard scenarios for a book.",
                       {"type": "object", "properties": {"book": {"type": "string", "enum": ["corporate", "retail"]}},
                        "required": ["book"]}),
    "whatif_scenario": (whatif_scenario, "whatif", "Run a library scenario through the What-If engine: ECL before "
                        "and after, waterfall and change by segment.",
                        {"type": "object", "properties": {
                            "book": {"type": "string", "enum": ["corporate", "retail"]},
                            "key": {"type": "string", "description": "oil-shock, rates-up, recession, downgrade-1, "
                                    "construction, real-estate, parameters, migration (corporate); unemployment, "
                                    "rates-up, house-prices, cards, score-band, recession (retail)"}},
                         "required": ["book", "key"]}),
    "scorecard_overview": (scorecard_overview, "scorecard", "Scorecards and the verdicts of their latest validation.",
                           {"type": "object", "properties": {"scorecard": {"type": "string"}}}),
    "product_walkthrough": (product_walkthrough, "product", "How a CreditProbe module works: what it is, the full "
                            "flow step by step with links that open each screen, and a worked example computed on the "
                            "current books. Modules: cockpit, early_warning, borrower_360, what_if, "
                            "scorecard_validation, data_builder, playbook, policy_docs, projects, "
                            "analyses_investigations, mail, workspace, deal_desk.",
                            {"type": "object", "properties": {"module": {"type": "string"}, "question": {"type": "string"}}}),
    "borrower_profile": (borrower_profile, "b360", "One corporate borrower's Borrower 360 profile and facilities.",
                         {"type": "object", "properties": {"borrower_id": {"type": "string", "pattern": "^CB\\d{5}$"}},
                          "required": ["borrower_id"]}),
}


def allowed(name: str, scope: list[str]) -> bool:
    need = REGISTRY[name][1]
    if need == "book":
        return any(b in scope for b in BOOKS)
    if need == "b360":
        return "b360" in scope or "corporate" in scope
    return need in scope


def call(name: str, args: dict[str, Any], scope: list[str]) -> Result:
    if name not in REGISTRY:
        raise ToolError(f"There is no tool {name!r}.")
    if not allowed(name, scope):
        raise ToolError(f"{name} reads {DOMAINS.get(REGISTRY[name][1], REGISTRY[name][1])}, outside this conversation's scope.")
    fn = REGISTRY[name][0]
    if name == "book_figures" and args.get("book") not in scope:
        books = [b for b in BOOKS if b in scope]
        args = {**args, "book": books[0]}
    try:
        return fn(**args)
    except (KeyError, compute.ComputeError) as e:
        raise ToolError(str(e)) from e
