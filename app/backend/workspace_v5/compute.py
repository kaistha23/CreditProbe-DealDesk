"""Recompute a saved analysis for any period, from the data: the books or the What-If engine.

An analysis keeps a *spec*: what to compute, never the numbers. Two engines:

  book    the Cockpit books (data/cockpit_v4_lake, read-only, pandas): a measure set over one book and period,
          optionally grouped by one dimension and filtered.
            {"engine": "book", "book": "corporate", "by": "sector", "measures": ["ead", "ecl"],
             "filters": {"sector": ["Construction"]}, "sort": "ead"}
  whatif  the What-If engine (backend.whatif_v5.models.runner, in process, deterministic): the saved scenario
          re-run at the chosen period with the same method.
            {"engine": "whatif", "book": "corporate", "method": "delta", "scenario": {...Scenario.to_dict()...}}

`compute(spec, period)` returns one *result* in the shape the UI and the Playbook section read:

  {"period", "book", "engine", "figures": [{key, label, value, unit}], "table": {"columns", "rows", "key"},
   "chart": {"kind", "x", "y", "title"}, "source"}

`compare(before, after)` lines two results up figure by figure and row by row with the deltas. No model is
called and no figure is typed in: every number comes out of the parquet files or the What-If engine.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.workspace_v5 import paths

CORP_RETAIL = ("corporate", "retail")

#: The Cockpit books: one table each, the grain the Cockpit answers from.
BOOKS: dict[str, dict[str, Any]] = {
    "corporate": {"release": paths.CORP_BOOK, "table": "corp_facility_quarter", "period": "reporting_quarter",
                  "owner": "borrower_id", "row": "facility_id", "row_label": "Facilities", "owner_label": "Borrowers",
                  "dims": {"sector": "Sector", "sub_sector": "Sub-sector", "region": "Region",
                           "product_type": "Product", "facility_class": "Facility class",
                           "relationship_tier": "Relationship tier", "stage": "IFRS 9 stage"}},
    "retail": {"release": paths.RETAIL_BOOK, "table": "retail_account_month", "period": "reporting_month",
               "owner": "customer_id", "row": "account_id", "row_label": "Accounts", "owner_label": "Customers",
               "dims": {"product": "Product", "sub_product": "Sub-product", "region": "Region",
                        "customer_segment": "Customer segment", "employment_type": "Employment type",
                        "origination_channel": "Origination channel", "delinquency_bucket": "Delinquency bucket",
                        "score_band": "Behaviour score band", "stage": "IFRS 9 stage"}},
}

#: Measures: (label, unit). Sums are SAR million as the books publish them.
MEASURES: dict[str, tuple[str, str]] = {
    "ead": ("EAD", "sar_mn"), "ecl": ("ECL", "sar_mn"), "coverage_pct": ("ECL coverage", "pct"),
    "share_pct": ("Share of EAD", "pct"), "count": ("Count", "int"), "owners": ("Owners", "int"),
    "stage2_ead": ("Stage 2 EAD", "sar_mn"), "stage2_ecl": ("Stage 2 ECL", "sar_mn"),
    "stage2_count": ("Stage 2 count", "int"), "stage2_share_pct": ("Stage 2 share of EAD", "pct"),
    "stage3_ead": ("Stage 3 EAD", "sar_mn"), "stage3_ecl": ("Stage 3 ECL", "sar_mn"),
    "limit": ("Limit", "sar_mn"), "write_off": ("Write-off", "sar_mn"),
}


class ComputeError(ValueError):
    pass


def _book(book: str) -> dict[str, Any]:
    if book not in BOOKS:
        raise ComputeError(f"'{book}' is not a book. The books are corporate and retail.")
    return BOOKS[book]


@lru_cache(maxsize=2)
def frame(book: str) -> pd.DataFrame:
    b = _book(book)
    cols = [b["row"], b["owner"], b["period"], *b["dims"].keys(), "ead_sar_mn", "ecl_sar_mn", "limit_sar_mn",
            "write_off_sar_mn"]
    cols = list(dict.fromkeys(cols))
    return pd.read_parquet(paths.LAKE / b["release"] / f"{b['table']}.parquet", columns=cols)


def periods(book: str) -> list[str]:
    b = _book(book)
    return sorted(str(p) for p in frame(book)[b["period"]].unique())


def resolve(book: str, period: str | None) -> str:
    known = periods(book)
    if not period:
        return known[-1]
    if period not in known:
        raise ComputeError(f"{period} is not a period of the {book} book. It runs {known[0]} to {known[-1]}.")
    return period


def _measure_frame(g: pd.DataFrame, b: dict[str, Any], measures: list[str], total_ead: float) -> dict[str, float]:
    ead, ecl = float(g.ead_sar_mn.sum()), float(g.ecl_sar_mn.sum())
    s2, s3 = g[g.stage == 2], g[g.stage == 3]
    out: dict[str, float] = {}
    for m in measures:
        if m == "ead":
            out[m] = ead
        elif m == "ecl":
            out[m] = ecl
        elif m == "coverage_pct":
            out[m] = 100 * ecl / ead if ead else 0.0
        elif m == "share_pct":
            out[m] = 100 * ead / total_ead if total_ead else 0.0
        elif m == "count":
            out[m] = int(len(g))
        elif m == "owners":
            out[m] = int(g[b["owner"]].nunique())
        elif m == "stage2_ead":
            out[m] = float(s2.ead_sar_mn.sum())
        elif m == "stage2_ecl":
            out[m] = float(s2.ecl_sar_mn.sum())
        elif m == "stage2_count":
            out[m] = int(len(s2))
        elif m == "stage2_share_pct":
            out[m] = 100 * float(s2.ead_sar_mn.sum()) / ead if ead else 0.0
        elif m == "stage3_ead":
            out[m] = float(s3.ead_sar_mn.sum())
        elif m == "stage3_ecl":
            out[m] = float(s3.ecl_sar_mn.sum())
        elif m == "limit":
            out[m] = float(g.limit_sar_mn.sum())
        elif m == "write_off":
            out[m] = float(g.write_off_sar_mn.sum())
        else:
            raise ComputeError(f"'{m}' is not a measure.")
    return out


def _label(book: str, m: str) -> str:
    b = BOOKS[book]
    if m == "count":
        return b["row_label"]
    if m == "owners":
        return b["owner_label"]
    if m == "stage2_count":
        return f"Stage 2 {b['row_label'].lower()}"
    return MEASURES[m][0]


def book_result(spec: dict[str, Any], period: str | None) -> dict[str, Any]:
    book = str(spec.get("book") or "")
    b = _book(book)
    period = resolve(book, period)
    measures = [m for m in spec.get("measures") or ["ead", "ecl"] if m in MEASURES]
    if not measures:
        raise ComputeError("The analysis names no measure this workspace can compute.")
    by = spec.get("by") or None
    if by and by not in b["dims"]:
        raise ComputeError(f"'{by}' is not a dimension of the {book} book.")
    f = frame(book)
    q = f[f[b["period"]] == period]
    for col, values in (spec.get("filters") or {}).items():
        if col not in b["dims"]:
            raise ComputeError(f"'{col}' is not a dimension of the {book} book.")
        vals = values if isinstance(values, list) else [values]
        q = q[q[col].astype(str).isin([str(v) for v in vals])]
    total_ead = float(q.ead_sar_mn.sum())
    totals = _measure_frame(q, b, measures, total_ead)
    figures = [{"key": m, "label": _label(book, m), "value": totals[m], "unit": MEASURES[m][1]} for m in measures
               if m != "share_pct"]
    table = None
    chart = None
    if by:
        rows = []
        for k, g in q.groupby(by, sort=False):
            label = f"Stage {int(k)}" if by == "stage" else str(k)
            rows.append({by: label, **_measure_frame(g, b, measures, total_ead)})
        sort = str(spec.get("sort") or measures[0])
        if by == "stage":
            rows.sort(key=lambda r: r[by])
        elif sort in measures:
            rows.sort(key=lambda r: (-float(r[sort]), r[by]))
        columns = [{"key": by, "label": b["dims"][by], "unit": "text"}] + [
            {"key": m, "label": _label(book, m), "unit": MEASURES[m][1]} for m in measures]
        table = {"columns": columns, "rows": rows, "key": by,
                 "totals": {by: "Total", **{m: totals[m] for m in measures}}}
        y = str(spec.get("chart_measure") or measures[0])
        chart = {"kind": "bar", "x": by, "y": y, "title": f"{_label(book, y)} by {b['dims'][by].lower()}, {period}"}
    return {"engine": "book", "book": book, "period": period, "figures": figures, "table": table, "chart": chart,
            "source": f"{b['release']}/{b['table']}.parquet"}


def whatif_result(spec: dict[str, Any], period: str | None) -> dict[str, Any]:
    from backend.whatif_v5.domain import store as wstore
    from backend.whatif_v5.models import runner
    from backend.whatif_v5.models.scenario import Scenario

    book = str(spec.get("book") or "")
    try:
        period = wstore.resolve_period(book, period or "")
        sc = Scenario.from_dict({**spec["scenario"], "domain": book, "period": period})
        r = runner.run(sc, str(spec.get("method") or "delta"))
    except (KeyError, wstore.DomainError, runner.RunError) as e:
        raise ComputeError(str(e)) from e
    c = r["cards"]
    seg = r["labels"]["segment"]
    figures = [
        {"key": "reported_ecl", "label": "Reported ECL", "value": float(c["reported_ecl"]), "unit": "sar_mn"},
        {"key": "scenario_ecl", "label": "Scenario ECL", "value": float(c["scenario_ecl"]), "unit": "sar_mn"},
        {"key": "change", "label": "ECL change", "value": float(c["change"]), "unit": "sar_mn"},
        {"key": "change_pct", "label": "ECL change %", "value": float(c["change_pct"]), "unit": "pct"},
        {"key": "coverage_before", "label": "Coverage before", "value": float(c["coverage_before"]), "unit": "pct"},
        {"key": "coverage_after", "label": "Coverage after", "value": float(c["coverage_after"]), "unit": "pct"},
        {"key": "ead", "label": "EAD", "value": float(c["ead_before"]), "unit": "sar_mn"},
    ]
    rows = [{"segment": str(s["segment"]), "ead": float(s["ead_before"]), "ecl_before": float(s["ecl_before"]),
             "ecl_after": float(s["ecl_after"]), "change": float(s["change"])} for s in r["by_segment"]]
    rows.sort(key=lambda x: (-x["change"], x["segment"]))
    columns = [{"key": "segment", "label": seg, "unit": "text"}, {"key": "ead", "label": "EAD", "unit": "sar_mn"},
               {"key": "ecl_before", "label": "ECL before", "unit": "sar_mn"},
               {"key": "ecl_after", "label": "ECL after", "unit": "sar_mn"},
               {"key": "change", "label": "ECL change", "unit": "sar_mn"}]
    return {"engine": "whatif", "book": book, "period": r["period"], "figures": figures,
            "table": {"columns": columns, "rows": rows, "key": "segment",
                      "totals": {"segment": "Total", "ead": float(c["ead_before"]),
                                 "ecl_before": float(c["reported_ecl"]), "ecl_after": float(c["scenario_ecl"]),
                                 "change": float(c["change"])}},
            "chart": {"kind": "bar", "x": "segment", "y": "change",
                      "title": f"ECL change by {seg.lower()}, {r['period']}"},
            "source": f"What-If engine {r.get('method_name', '')} ({r.get('method_version', '')}), run {r['run_id']}",
            "run_id": r["run_id"], "method": r["method"], "method_name": r.get("method_name", ""),
            "scenario_name": sc.name, "steps": r.get("steps", [])}


def compute(spec: dict[str, Any] | None, period: str | None = None) -> dict[str, Any]:
    if not spec:
        raise ComputeError("This analysis was saved without a recipe that can be recomputed.")
    engine = spec.get("engine")
    if engine == "book":
        return book_result(spec, period)
    if engine == "whatif":
        return whatif_result(spec, period)
    raise ComputeError(f"'{engine}' is not an engine this workspace can run.")


def available_periods(spec: dict[str, Any] | None) -> list[str]:
    if not spec:
        return []
    if spec.get("engine") == "whatif":
        from backend.whatif_v5.domain import store as wstore
        try:
            return list(wstore.periods(str(spec.get("book"))))
        except wstore.DomainError:
            return []
    if spec.get("engine") == "book":
        return periods(str(spec.get("book")))
    return []


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Figure by figure and row by row: before, after, change (and % change for amounts and counts)."""
    def delta(a: Any, b: Any, unit: str) -> dict[str, Any]:
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return {"change": None, "change_pct": None}
        ch = float(b) - float(a)
        pct = (100 * ch / float(a)) if unit != "pct" and a else None
        return {"change": ch, "change_pct": pct}

    bf = {f["key"]: f for f in before.get("figures") or []}
    figures = []
    for f in after.get("figures") or []:
        old = bf.get(f["key"])
        a = old["value"] if old else None
        figures.append({"key": f["key"], "label": f["label"], "unit": f["unit"], "before": a, "after": f["value"],
                        **delta(a, f["value"], f["unit"])})
    rows: list[dict[str, Any]] = []
    tb, ta = before.get("table"), after.get("table")
    if tb and ta and tb.get("key") == ta.get("key"):
        key = ta["key"]
        num = [c for c in ta["columns"] if c["unit"] != "text"]
        old_rows = {str(r.get(key)): r for r in tb.get("rows") or []}
        seen = set()
        for r in ta.get("rows") or []:
            k = str(r.get(key))
            seen.add(k)
            o = old_rows.get(k, {})
            rows.append({"key": k, "cells": {c["key"]: {"before": o.get(c["key"]), "after": r.get(c["key"]),
                                                         **delta(o.get(c["key"]), r.get(c["key"]), c["unit"])}
                                             for c in num}})
        for k, o in old_rows.items():
            if k not in seen:
                rows.append({"key": k, "cells": {c["key"]: {"before": o.get(c["key"]), "after": None,
                                                             "change": None, "change_pct": None} for c in num}})
    return {"before_period": before.get("period"), "after_period": after.get("period"), "figures": figures,
            "rows": rows, "columns": (ta or {}).get("columns", [])}


# ------------------------------------------------------- Cockpit answers


_DIM_ALIASES = {"product_type": ("product_type", "product"), "sub_sector": ("sub_sector", "subsector"),
                "sub_product": ("sub_product", "subproduct")}
_PERIOD = {"corporate": re.compile(r"\b(20\d\d)\s*-?\s*Q([1-4])\b", re.I), "retail": re.compile(r"\b(20\d\d)-(\d\d)\b")}


def period_in(book: str, *texts: str) -> str | None:
    """The last period of the book named in the text (a question or an answer), if any."""
    rx = _PERIOD.get(book)
    if not rx:
        return None
    found: list[str] = []
    for t in texts:
        for m in rx.finditer(t or ""):
            found.append(f"{m.group(1)}Q{m.group(2)}" if book == "corporate" else f"{m.group(1)}-{m.group(2)}")
    known = set(periods(book))
    found = [p for p in found if p in known]
    return found[-1] if found else None


def _measure_of(column: str) -> str | None:
    c = column.lower()
    if "coverage" in c:
        return "coverage_pct"
    if "share" in c or c.endswith("_pct") and "ead" in c:
        return "share_pct"
    stage = "stage2_" if re.search(r"stage_?2", c) else "stage3_" if re.search(r"stage_?3", c) else ""
    if "ecl" in c and not any(x in c for x in ("rate", "ratio", "change", "delta", "growth")):
        return f"{stage}ecl" if stage else "ecl"
    if "ead" in c and not any(x in c for x in ("rate", "ratio", "change", "delta", "growth")):
        return f"{stage}ead" if stage else "ead"
    if re.search(r"(borrower|customer)s?(_count)?$|^n_(borrowers|customers)$", c):
        return "owners"
    if re.search(r"(facilit(y|ies)|accounts?)(_count)?$|^(n|count)$|^n_(facilities|accounts)$", c):
        return "stage2_count" if stage == "stage2_" else "count"
    if c.startswith("limit"):
        return "limit"
    return None


def infer_book_spec(book: str, tables: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A Cockpit answer's first table read back as a book spec: one dimension and the measures it shows.

    None when the table is not a measure-by-dimension cut of the book (then the analysis keeps the Cockpit's own
    figures and says it cannot be recomputed here without the Cockpit)."""
    if book not in BOOKS:
        return None
    dims = BOOKS[book]["dims"]
    for i, t in enumerate(tables or []):
        cols = [str(c) for c in t.get("columns") or []]
        by = None
        for c in cols:
            lc = c.lower()
            for d in dims:
                if lc == d or lc in _DIM_ALIASES.get(d, ()):
                    by = d
                    break
            if by:
                break
        measures = list(dict.fromkeys(m for m in (_measure_of(c) for c in cols if c.lower() != (by or "")) if m))
        if measures:
            spec: dict[str, Any] = {"engine": "book", "book": book, "by": by, "measures": measures, "cockpit_table": i}
            return spec
    return None


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def reproduces(spec: dict[str, Any], table: dict[str, Any], result: dict[str, Any]) -> bool:
    """Does the book recipe give back the Cockpit's own figures? Every value of every row of the Cockpit's table that
    maps to a measure must equal the recomputed one (to the rounding a query may apply). A table the recipe does not
    reproduce (a filter it does not carry, a different measure) is kept as published and not refreshed here."""
    cols = [str(c) for c in table.get("columns") or []]
    by = spec.get("by")
    dim_col = None
    if by:
        dim_col = next((c for c in cols if c.lower() == by or c.lower() in _DIM_ALIASES.get(by, ())), None)
    mapping = {c: m for c in cols if c != dim_col for m in [_measure_of(c)] if m in (spec.get("measures") or [])}
    if not mapping:
        return False
    rows = [r.get("canonical") if isinstance(r, dict) and "canonical" in r else r for r in table.get("rows") or []]
    if by:
        base = {str(r[by]): r for r in (result.get("table") or {}).get("rows") or []}
    else:
        base = {"": {f["key"]: f["value"] for f in result.get("figures") or []}}
    matched = 0
    for row in rows:
        if not isinstance(row, dict):
            return False
        if by:
            key = row.get(dim_col)
            key = f"Stage {int(_num(key))}" if by == "stage" and _num(key) is not None else str(key)
        else:
            key = ""
        if key not in base:
            return False
        for col, m in mapping.items():
            got, want = _num(row.get(col)), _num(base[key].get(m))
            if got is None:
                continue
            if want is None or abs(got - want) > max(0.051, 1e-4 * abs(want)):
                return False
            matched += 1
    return matched > 0
