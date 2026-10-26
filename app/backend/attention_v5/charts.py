"""Chart data behind one "requiring attention" item, computed from the Cockpit books (read-only, DuckDB).

The attention items themselves (selection, order, severity, text, numbers) are the frozen Cockpit's and are not
touched. This module only draws what already explains an item: the measure over the last 8 quarters (corporate) or
12 months (retail), the segment against the book, what contributed to the movement, and the stage mix.

Each family below restates the frozen definition in backend/cockpit_v4/attention_v2.py as a numerator and
denominator (`value = SUM(num) / SUM(den)`, or `SUM(num)` for an amount), and tests/v5/attention compares the last two
trend points of every family with the numbers the live feed prints, so the two cannot drift apart.

Contributors are an exact decomposition of the movement: for an amount, a contributor's change in the numerator; for a
ratio, `num_c1 / D1 - num_c0 / D0` with D the segment's denominator in each period. They add up to the movement of the
segment's value to the last decimal, with a single "All others" bar for what is not shown.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import duckdb

V5 = pathlib.Path(__file__).resolve().parents[2]
LAKE = pathlib.Path(os.environ.get("ATTENTION_LAKE") or V5 / "data" / "cockpit_v4_lake")
RELEASE = {"corporate": "v4-saudi-corporate-20q-v4", "retail": "v4-saudi-retail-20m-v5"}
PERIOD_COL = {"corporate": "reporting_quarter", "retail": "reporting_month"}
#: How many periods the trend shows: 8 quarters (corporate), 12 months (retail).
TREND_PERIODS = {"corporate": 8, "retail": 12}
PERIOD_NOUN = {"corporate": "quarter", "retail": "month"}
TOP_CONTRIBUTORS = 7
MAX_PEERS = 14


class Unavailable(LookupError):
    """The item's family has no chart data here. Said plainly, never faked."""


@dataclass(frozen=True)
class Fam:
    domain: str
    relation: str
    dimension: str
    dimension_label: str
    measure: str
    measure_label: str
    #: "amount" (SUM(num), SAR million) or "share" (SUM(num) / SUM(den), shown as a percentage).
    kind: str
    num: str
    den: str = "1"
    filter: str = ""
    #: Columns a contributor can be (finer cuts of the same population), in preference order.
    contrib: tuple[str, ...] = ()
    #: The counterparty column of the relation, and the column holding its name when it has one.
    counterparty: str = ""
    counterparty_name: str = ""
    counterparty_label: str = ""
    #: How to read the stage mix: "stage" column on the relation, or a join to the facility / account relation;
    #: "book" is the whole book's mix (a card whose segment is itself a stage).
    stage: str = "column"
    #: A whole-book card (the Cockpit's ECL highlights and ECL panel): the segment is the book itself, and `dimension`
    #: is only the cut the "against the book" chart shows the book by.
    portfolio: bool = False
    #: How a segment value reads, e.g. "Stage {}" for the stage column.
    value_label: str = ""


_S2 = "CASE WHEN stage >= 2 THEN ead_sar_mn ELSE 0 END"
_PD = "CASE WHEN dpd_days > 0 THEN ead_sar_mn ELSE 0 END"

FAMILIES: dict[str, Fam] = {}


def _add(key: str, f: Fam) -> None:
    FAMILIES[f"{f.domain}:{key}"] = f


_CF = dict(domain="corporate", relation="corp_facility_quarter", counterparty="borrower_id",
           counterparty_name="borrower_name", counterparty_label="borrower")
_add("sector_stage2", Fam(**_CF, dimension="sector", dimension_label="Sector", measure="stage2_share",
                          measure_label="Stage 2 share of EAD", kind="share", num=_S2, den="ead_sar_mn",
                          contrib=("sub_sector", "product_type", "region")))
_add("sector_ecl", Fam(**_CF, dimension="sector", dimension_label="Sector", measure="ecl", measure_label="Recognised ECL",
                       kind="amount", num="ecl_sar_mn", contrib=("sub_sector", "product_type", "region")))
_add("sector_coverage", Fam(**_CF, dimension="sector", dimension_label="Sector", measure="ecl_coverage",
                            measure_label="ECL as a share of EAD", kind="share", num="ecl_sar_mn", den="ead_sar_mn",
                            contrib=("sub_sector", "product_type", "region")))
_add("sector_pastdue", Fam(**_CF, dimension="sector", dimension_label="Sector", measure="past_due_share",
                           measure_label="Past-due share of EAD", kind="share", num=_PD, den="ead_sar_mn",
                           contrib=("sub_sector", "product_type", "region")))
_add("product_stage2", Fam(**_CF, dimension="product_type", dimension_label="Product type", measure="stage2_share",
                           measure_label="Stage 2 share of EAD", kind="share", num=_S2, den="ead_sar_mn",
                           contrib=("sector", "region")))
_add("product_ecl", Fam(**_CF, dimension="product_type", dimension_label="Product type", measure="ecl",
                        measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn", contrib=("sector", "region")))
_add("region_ecl", Fam(**_CF, dimension="region", dimension_label="Region", measure="ecl",
                       measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn",
                       contrib=("sector", "product_type")))
_CB = dict(domain="corporate", relation="corp_borrower_quarter", counterparty="borrower_id",
           counterparty_name="borrower_name", counterparty_label="borrower", stage="borrower")
_add("sector_downgrades", Fam(**_CB, dimension="sector", dimension_label="Sector", measure="downgrade_share",
                              measure_label="Share of obligors downgraded this quarter", kind="share",
                              num="CASE WHEN rating_notches_moved < 0 THEN 1 ELSE 0 END", contrib=("sub_sector", "region")))
_add("sector_watchlist", Fam(**_CB, dimension="sector", dimension_label="Sector", measure="watchlist_share",
                             measure_label="Share of obligors on the watch list", kind="share",
                             num="watchlist_flag", contrib=("sub_sector", "region")))
_CV = dict(domain="corporate", relation="corp_covenant_quarter", counterparty="borrower_id",
           counterparty_label="borrower", stage="facility")
_add("sector_breaches", Fam(**_CV, dimension="sector", dimension_label="Sector", measure="breach_share",
                            measure_label="Share of covenant tests breached", kind="share", num="breach_flag",
                            contrib=("covenant_type",)))
_add("covenant_breaches", Fam(**_CV, dimension="covenant_type", dimension_label="Covenant type",
                              measure="breach_share", measure_label="Share of covenant tests breached", kind="share",
                              num="breach_flag", contrib=("sector",)))
_add("sector_ltv", Fam(domain="corporate", relation="corp_collateral_quarter", counterparty="borrower_id",
                       counterparty_label="borrower", stage="facility", dimension="collateral_type",
                       dimension_label="Collateral type", measure="ltv",
                       measure_label="Exposure as a share of pledged collateral value", kind="share",
                       num="ltv_pct / 100.0", contrib=("sector",)))
_RA = dict(domain="retail", relation="retail_account_month", counterparty="customer_id", counterparty_label="customer")
_add("product_stage2", Fam(**_RA, dimension="product", dimension_label="Product", measure="stage2_share",
                           measure_label="Stage 2 share of EAD", kind="share", num=_S2, den="ead_sar_mn",
                           contrib=("sub_product", "customer_segment", "region")))
_add("product_ecl", Fam(**_RA, dimension="product", dimension_label="Product", measure="ecl",
                        measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn",
                        contrib=("sub_product", "customer_segment", "region")))
_add("product_delinquency", Fam(**_RA, dimension="product", dimension_label="Product", measure="dpd_share",
                                measure_label="Share of EAD past due", kind="share", num=_PD, den="ead_sar_mn",
                                contrib=("sub_product", "customer_segment", "region")))
_add("band_stage2", Fam(**_RA, dimension="score_band", dimension_label="Behaviour score band", measure="stage2_share",
                        measure_label="Stage 2 share of EAD", kind="share", num=_S2, den="ead_sar_mn",
                        contrib=("product", "customer_segment", "region")))
_add("vintage_stage2", Fam(**_RA, dimension="vintage_year", dimension_label="Origination vintage",
                           measure="stage2_share", measure_label="Stage 2 share of EAD", kind="share", num=_S2,
                           den="ead_sar_mn", contrib=("product", "customer_segment", "region")))
_add("segment_ecl", Fam(**_RA, dimension="customer_segment", dimension_label="Customer segment", measure="ecl",
                        measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn",
                        contrib=("product", "region", "score_band")))
_add("product_utilisation", Fam(**_RA, dimension="product", dimension_label="Product", measure="utilisation",
                                measure_label="Average utilisation", kind="share", num="utilisation_pct / 100.0",
                                contrib=("sub_product", "customer_segment", "region")))
_add("region_delinquency", Fam(**_RA, dimension="region", dimension_label="Region", measure="dpd_share",
                               measure_label="Share of EAD past due", kind="share", num=_PD, den="ead_sar_mn",
                               contrib=("product", "customer_segment", "score_band")))
_add("segment_score_decline", Fam(domain="retail", relation="retail_customer_month", counterparty="customer_id",
                                  counterparty_label="customer", stage="customer", dimension="customer_segment",
                                  dimension_label="Customer segment", measure="deteriorated_share",
                                  measure_label="Share of customers whose score deteriorated", kind="share",
                                  num="CASE WHEN score_migration = 'DETERIORATED' THEN 1 ELSE 0 END",
                                  contrib=("employment_type", "region", "score_band")))

# ------------------------------------------------- the Cockpit's ECL highlights and ECL panel (PLAN_R4 B1)
#
# The four ECL highlight cards (`ecl-total`, `ecl-largest`, `ecl-increase`, `ecl-stage2`, restated from
# backend/cockpit_v4/attention_v2._highlights) and the ECL panel's cards (EAD, recognised ECL, coverage and the stage
# rows, restated from backend/cockpit_v4/ecl.stage_profile) draw the same four charts. A whole-book card is `portfolio`:
# its segment is the book, and the "against the book" chart shows the book by sector (corporate) or product (retail).
# The decomposition components (`ecl-component`) are computed by `component_charts` below.
for _dom, _rel, _dim, _dlabel, _cp, _cpl, _contrib, _seg_contrib in (
        ("corporate", "corp_facility_quarter", "sector", "Sector", "borrower_id", "borrower",
         ("sector", "product_type", "region"), ("sub_sector", "product_type", "region")),
        ("retail", "retail_account_month", "product", "Product", "customer_id", "customer",
         ("product", "customer_segment", "region", "score_band"), ("sub_product", "customer_segment", "region"))):
    _base = dict(domain=_dom, relation=_rel, counterparty=_cp, counterparty_label=_cpl,
                 counterparty_name="borrower_name" if _dom == "corporate" else "")
    _book = dict(_base, dimension=_dim, dimension_label=_dlabel, portfolio=True, stage="book", contrib=_contrib)
    _add("ecl-total", Fam(**_book, measure="ecl", measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn"))
    _add("ecl-stage2", Fam(**_book, measure="stage23_share", measure_label="Stage 2 and 3 share of exposure",
                           kind="share", num=_S2, den="ead_sar_mn"))
    _add("ecl-ead", Fam(**_book, measure="ead", measure_label="Exposure at default", kind="amount", num="ead_sar_mn"))
    _add("ecl-coverage", Fam(**_book, measure="ecl_coverage", measure_label="ECL coverage of exposure", kind="share",
                             num="ecl_sar_mn", den="ead_sar_mn"))
    for _key in ("ecl-largest", "ecl-increase"):
        _add(_key, Fam(**_base, dimension=_dim, dimension_label=_dlabel, measure="ecl", measure_label="Recognised ECL",
                       kind="amount", num="ecl_sar_mn", contrib=_seg_contrib))
    _add("ecl-stage", Fam(**_base, dimension="stage", dimension_label="Stage", value_label="Stage {}", stage="book",
                          measure="ecl", measure_label="Recognised ECL", kind="amount", num="ecl_sar_mn",
                          contrib=_contrib))

LABEL = {"sub_sector": "Sub-sector", "product_type": "Product type", "region": "Region", "sector": "Sector",
         "covenant_type": "Covenant type", "sub_product": "Sub-product", "customer_segment": "Customer segment",
         "product": "Product", "score_band": "Behaviour score band", "employment_type": "Employment type"}


def family(domain: str, key: str) -> Fam:
    if key == COMPONENT:
        raise Unavailable("The ECL decomposition components are drawn by component_charts.")
    f = FAMILIES.get(f"{domain}:{key}")
    if f is None:
        raise Unavailable(f"No chart data for the '{key}' family in the {domain} book.")
    return f


# --------------------------------------------------------------- the lake


@lru_cache(maxsize=4)
def _con(domain: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    base = LAKE / RELEASE[domain]
    for rel in base.glob("*.parquet"):
        con.execute(f"CREATE VIEW {rel.stem} AS SELECT * FROM read_parquet('{rel.as_posix()}')")
    return con


def _q(domain: str, sql: str, *args: Any) -> list[tuple]:
    # A cursor per query: the one connection is shared by the service's worker threads.
    return _con(domain).cursor().execute(sql, list(args)).fetchall()


def periods(domain: str, relation: str) -> list[str]:
    col = PERIOD_COL[domain]
    return [r[0] for r in _q(domain, f"SELECT DISTINCT {col} FROM {relation} ORDER BY 1")]


def _value(num: float | None, den: float | None, f: Fam) -> float | None:
    if num is None:
        return None
    if f.kind == "amount":
        return float(num)
    return float(num) / float(den) if den else None


def _scale(v: float | None, f: Fam) -> float | None:
    """Amounts stay in SAR million; a share is shown as a percentage."""
    return None if v is None else (v if f.kind == "amount" else 100.0 * v)


def _seg(f: Fam) -> str:
    # A whole-book card still binds its segment parameter (the book's name), so every query keeps one shape.
    return "CAST(? AS VARCHAR) IS NOT NULL" if f.portfolio else f"CAST({f.dimension} AS VARCHAR) = ?"


def _label(f: Fam, value: Any) -> Any:
    return f.value_label.format(value) if f.value_label else label_of(value)


def _flt(f: Fam) -> str:
    return f" AND {f.filter}" if f.filter else ""


# ------------------------------------------------------------------ charts


def trend(f: Fam, segment: str, period: str) -> dict[str, Any]:
    ps = periods(f.domain, f.relation)
    upto = [p for p in ps if p <= period][-TREND_PERIODS[f.domain]:]
    col = PERIOD_COL[f.domain]
    sel = f"SUM({f.num}), SUM({f.den})"
    seg = {r[0]: _scale(_value(r[1], r[2], f), f) for r in _q(
        f.domain, f"SELECT {col}, {sel} FROM {f.relation} WHERE {_seg(f)}{_flt(f)} AND {col} IN ({','.join('?' * len(upto))}) "
                  f"GROUP BY 1", segment, *upto)}
    book = {r[0]: _scale(_value(r[1], r[2], f), f) for r in _q(
        f.domain, f"SELECT {col}, {sel} FROM {f.relation} WHERE TRUE{_flt(f)} AND {col} IN ({','.join('?' * len(upto))}) "
                  f"GROUP BY 1", *upto)}
    return {"periods": upto, "segment": [seg.get(p) for p in upto], "book": [book.get(p) for p in upto],
            "current_index": len(upto) - 1}


def peers(f: Fam, segment: str, period: str) -> dict[str, Any]:
    col = PERIOD_COL[f.domain]
    rows = _q(f.domain, f"SELECT CAST({f.dimension} AS VARCHAR), SUM({f.num}), SUM({f.den}), COUNT(*) FROM {f.relation} "
                        f"WHERE {col} = ?{_flt(f)} GROUP BY 1", period)
    items = [{"segment": r[0], "value": _scale(_value(r[1], r[2], f), f), "rows": int(r[3])} for r in rows]
    items = [i for i in items if i["value"] is not None]
    items.sort(key=lambda i: -i["value"])
    if len(items) > MAX_PEERS:
        keep = items[:MAX_PEERS]
        if not f.portfolio and not any(i["segment"] == segment for i in keep):
            keep = keep[:-1] + [next(i for i in items if i["segment"] == segment)]
        items = keep
    tot = _q(f.domain, f"SELECT SUM({f.num}), SUM({f.den}) FROM {f.relation} WHERE {col} = ?{_flt(f)}", period)[0]
    return {"period": period, "items": [{**i, "label": _label(f, i["segment"]), "is_segment": not f.portfolio and i["segment"] == segment}
                                        for i in items],
            "book": _scale(_value(tot[0], tot[1], f), f),
            "book_label": "Book total" if f.kind == "amount" else "Book"}


_CODE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)+")


def label_of(value: Any) -> Any:
    """A stored code such as `supply_chain_finance` as a reader sees it ("Supply Chain Finance"); names pass through."""
    if isinstance(value, str) and _CODE.fullmatch(value):
        return " ".join(w.capitalize() for w in value.split("_"))
    return value


def _contrib_by(f: Fam, segment: str, before: str, after: str, column: str, name_col: str = "") -> dict[str, Any]:
    col = PERIOD_COL[f.domain]
    sel_name = f", ANY_VALUE({name_col})" if name_col else ", ''"
    rows = _q(f.domain, f"SELECT CAST({column} AS VARCHAR), {col}, SUM({f.num}), SUM({f.den}){sel_name} FROM {f.relation} "
                        f"WHERE {_seg(f)}{_flt(f)} AND {col} IN (?, ?) GROUP BY 1, 2", segment, before, after)
    num = {(r[0], r[1]): float(r[2] or 0.0) for r in rows}
    names = {r[0]: r[4] for r in rows if r[4]}
    den = {p: sum(float(r[3] or 0.0) for r in rows if r[1] == p) for p in (before, after)}
    keys = sorted({k for k, _ in num})
    out = []
    for k in keys:
        n0, n1 = num.get((k, before), 0.0), num.get((k, after), 0.0)
        if f.kind == "amount":
            out.append((k, n0, n1, n1 - n0))
        else:
            v0 = n0 / den[before] if den[before] else 0.0
            v1 = n1 / den[after] if den[after] else 0.0
            out.append((k, v0, v1, v1 - v0))
    total_before = sum(o[1] for o in out)
    total_after = sum(o[2] for o in out)
    out.sort(key=lambda o: -abs(o[3]))
    top, rest = out[:TOP_CONTRIBUTORS], out[TOP_CONTRIBUTORS:]
    mult = 1.0 if f.kind == "amount" else 100.0
    items = [{"name": names.get(k) or label_of(k), "id": k, "from": a * mult, "to": b * mult, "change": c * mult}
             for k, a, b, c in top]
    if rest:
        items.append({"name": f"All others ({len(rest)})", "id": "", "from": sum(o[1] for o in rest) * mult,
                      "to": sum(o[2] for o in rest) * mult, "change": sum(o[3] for o in rest) * mult})
    items.sort(key=lambda i: (i["id"] == "", -i["change"]))
    return {"items": items, "from": total_before * mult, "to": total_after * mult,
            "total_change": (total_after - total_before) * mult}


def contributors(f: Fam, segment: str, before: str, after: str) -> dict[str, Any]:
    """The same movement cut every way that is available: finer segments, then counterparties."""
    views = []
    for column in f.contrib:
        views.append({"key": column, "label": LABEL.get(column, column), **_contrib_by(f, segment, before, after, column)})
    if f.counterparty:
        views.append({"key": f.counterparty, "label": f"{f.counterparty_label.capitalize()} (top {TOP_CONTRIBUTORS})",
                      **_contrib_by(f, segment, before, after, f.counterparty, f.counterparty_name)})
    return {"before": before, "after": after, "views": views}


_STAGE_SQL = {
    # (population SQL for one period `?`, columns) -> rows of (stage, ead)
    "column": "SELECT stage, SUM(ead_sar_mn) FROM {rel} WHERE {seg} AND {pc} = ? GROUP BY 1",
    "facility": ("SELECT f.stage, SUM(f.ead_sar_mn) FROM corp_facility_quarter f WHERE f.reporting_quarter = ? AND "
                 "f.facility_id IN (SELECT facility_id FROM {rel} WHERE {seg} AND {pc} = ?) GROUP BY 1"),
    "borrower": ("SELECT f.stage, SUM(f.ead_sar_mn) FROM corp_facility_quarter f WHERE f.reporting_quarter = ? AND "
                 "f.borrower_id IN (SELECT borrower_id FROM {rel} WHERE {seg} AND {pc} = ?) GROUP BY 1"),
    "customer": "SELECT worst_stage, SUM(total_ead_sar_mn) FROM {rel} WHERE {seg} AND {pc} = ? GROUP BY 1",
    "book": "SELECT stage, SUM(ead_sar_mn) FROM {rel} WHERE CAST(? AS VARCHAR) IS NOT NULL AND {pc} = ? GROUP BY 1",
}


def stage_mix(f: Fam, segment: str, before: str, after: str) -> dict[str, Any]:
    pc = PERIOD_COL[f.domain]
    sql = _STAGE_SQL[f.stage].format(rel=f.relation, seg=_seg(f), pc=pc)
    out: dict[str, dict[int, float]] = {}
    for p in (before, after):
        if f.stage in ("facility", "borrower"):
            rows = _q(f.domain, sql, p, segment, p)
        else:
            rows = _q(f.domain, sql, segment, p)
        out[p] = {int(r[0]): float(r[1] or 0.0) for r in rows}
    stages = [1, 2, 3]
    basis = {"column": "Exposure at default of the segment", "facility": "Exposure at default of the facilities these tests / pledges cover",
             "borrower": "Exposure at default of these obligors' facilities", "customer": "Exposure of these customers, by their worst stage",
             "book": "Exposure at default of the whole book"}[f.stage]
    return {"periods": [before, after], "stages": stages, "ead": [[out[p].get(s, 0.0) for s in stages] for p in (before, after)],
            "unit": "SAR million", "basis": basis}


def charts(domain: str, key: str, segment: str, period: str | None = None, comparison: str | None = None) -> dict[str, Any]:
    if key == COMPONENT:
        return component_charts(domain, segment, period, comparison)
    f = family(domain, key)
    ps = periods(domain, f.relation)
    period = period or ps[-1]
    if period not in ps:
        raise Unavailable(f"{period} is not a period of the {domain} book.")
    comparison = comparison or ps[ps.index(period) - 1]
    exists = _q(domain, f"SELECT COUNT(*) FROM {f.relation} WHERE {_seg(f)} AND {PERIOD_COL[domain]} = ?", segment, period)[0][0]
    if not exists:
        raise Unavailable(f"No '{segment}' in {f.dimension_label.lower()} at {period}.")
    t = trend(f, segment, period)
    return {"domain": domain, "family": key, "segment": segment, "segment_label": _label(f, segment), "dimension": f.dimension, "dimension_label": f.dimension_label,
            "scope": "portfolio" if f.portfolio else "segment",
            "trend_labels": {"segment": "Whole book" if f.portfolio else str(_label(f, segment)), "book": "" if f.portfolio else "Whole book"},
            "measure": f.measure, "measure_label": f.measure_label, "kind": f.kind,
            "unit": "SAR million" if f.kind == "amount" else "%", "period": period, "comparison_period": comparison,
            "period_noun": PERIOD_NOUN[domain], "trend": t, "peers": peers(f, segment, period),
            "contributors": contributors(f, segment, comparison, period), "stage_mix": stage_mix(f, segment, comparison, period),
            "source": f"{RELEASE[domain]}/{f.relation}"}


# ------------------------------------------------- the ECL panel's decomposition components (PLAN_R4 B1)
#
# Restates backend/cockpit_v4/ecl.decompose: every exposure (facility / account) is NEW, CLOSED or RETAINED between
# two periods; a retained exposure whose stage changed is STAGE MIGRATION, one whose stage did not is split into its
# EAD movement at last period's coverage (EXPOSURE CHANGE) and the remainder (RISK AND OVERLAY CHANGE). The five
# components add up to the ECL movement exactly. tests/v5/attention checks every number against the frozen function.

COMPONENT = "ecl-component"
COMPONENT_IDS = ("new", "closed", "stage_migration", "exposure_change", "risk_change")
_GRAIN = {"corporate": ("corp_facility_quarter", "facility_id", "facilities", "borrower_id", "borrower_name", "borrower",
                        "sector", "Sector", ("sector", "product_type", "region")),
          "retail": ("retail_account_month", "account_id", "accounts", "customer_id", "", "customer",
                     "product", "Product", ("product", "customer_segment", "region"))}


def component_label(domain: str, cid: str) -> str:
    plural = _GRAIN[domain][2]
    return {"new": f"New {plural}", "closed": f"Closed {plural}", "stage_migration": "Stage migration",
            "exposure_change": "Exposure change", "risk_change": "Risk and overlay change"}[cid]


def _bucketed(domain: str, before: str, after: str, group: str = "", name: str = "") -> list[tuple]:
    """(bucket, group, name, d_ecl, d_exposure, n) of the exposures between two periods, optionally by a column."""
    rel, key = _GRAIN[domain][0], _GRAIN[domain][1]
    pc = PERIOD_COL[domain]
    g = f", {group} AS g" if group else ", '' AS g"
    nm = f", {name} AS nm" if name else ", '' AS nm"
    sql = f"""
        WITH now AS (SELECT {key} AS id, stage, ead_sar_mn AS ead, ecl_sar_mn AS ecl{g}{nm} FROM {rel} WHERE {pc} = ?),
        before AS (SELECT {key} AS id, stage, ead_sar_mn AS ead, ecl_sar_mn AS ecl{g}{nm} FROM {rel} WHERE {pc} = ?)
        SELECT CASE WHEN before.id IS NULL THEN 'new' WHEN now.id IS NULL THEN 'closed'
                    WHEN now.stage <> before.stage THEN 'stage_migration' ELSE 'retained' END AS bucket,
               CAST(COALESCE(now.g, before.g) AS VARCHAR), ANY_VALUE(COALESCE(now.nm, before.nm)),
               SUM(COALESCE(now.ecl, 0) - COALESCE(before.ecl, 0)),
               SUM(CASE WHEN before.id IS NOT NULL AND now.id IS NOT NULL AND now.stage = before.stage
                        THEN (now.ead - before.ead) * CASE WHEN before.ead = 0 THEN 0 ELSE before.ecl / before.ead END
                        ELSE 0 END),
               COUNT(*)
        FROM now FULL OUTER JOIN before ON now.id = before.id GROUP BY 1, 2"""
    return _q(domain, sql, after, before)


def _components(rows: list[tuple]) -> dict[str, dict[str, float]]:
    """{component: {group: amount}} from bucketed rows."""
    out: dict[str, dict[str, float]] = {c: {} for c in COMPONENT_IDS}
    for bucket, grp, _nm, d_ecl, d_exp, _n in rows:
        d_ecl, d_exp = float(d_ecl or 0.0), float(d_exp or 0.0)
        if bucket == "retained":
            out["exposure_change"][grp] = out["exposure_change"].get(grp, 0.0) + d_exp
            out["risk_change"][grp] = out["risk_change"].get(grp, 0.0) + d_ecl - d_exp
        else:
            out[bucket][grp] = out[bucket].get(grp, 0.0) + d_ecl
    return out


@lru_cache(maxsize=64)
def component_amounts(domain: str, before: str, after: str) -> dict[str, float]:
    """The five components of the ECL movement from `before` to `after` (SAR million)."""
    return {c: float(sum(v.values())) for c, v in _components(_bucketed(domain, before, after)).items()}


def _total_ecl(domain: str, period: str) -> float:
    rel = _GRAIN[domain][0]
    return float(_q(domain, f"SELECT SUM(ecl_sar_mn) FROM {rel} WHERE {PERIOD_COL[domain]} = ?", period)[0][0] or 0.0)


def component_charts(domain: str, cid: str, period: str | None = None, comparison: str | None = None) -> dict[str, Any]:
    if cid not in COMPONENT_IDS:
        raise Unavailable(f"'{cid}' is not a component of the ECL movement.")
    rel, _key, plural, cp, cp_name, cp_label, dim, dim_label, contrib = _GRAIN[domain]
    ps = periods(domain, rel)
    period = period or ps[-1]
    if period not in ps or ps.index(period) == 0:
        raise Unavailable(f"{period} is not a period of the {domain} book with one before it.")
    comparison = comparison or ps[ps.index(period) - 1]
    if comparison not in ps:
        raise Unavailable(f"{comparison} is not a period of the {domain} book.")
    upto = [p for p in ps if p <= period][-TREND_PERIODS[domain]:]
    seg, book = [], []
    for p in upto:
        i = ps.index(p)
        if i == 0:
            seg.append(None)
            book.append(None)
            continue
        prev = comparison if p == period else ps[i - 1]
        seg.append(component_amounts(domain, prev, p)[cid])
        book.append(_total_ecl(domain, p) - _total_ecl(domain, prev))
    now = component_amounts(domain, comparison, period)
    movement = _total_ecl(domain, period) - _total_ecl(domain, comparison)
    label = component_label(domain, cid)

    def view(column: str, vlabel: str, name_col: str = "") -> dict[str, Any]:
        rows = _bucketed(domain, comparison, period, column, name_col)
        parts = _components(rows)[cid]
        names = {r[1]: r[2] for r in rows if r[2]}
        out = sorted(parts.items(), key=lambda kv: -abs(kv[1]))
        top, rest = out[:TOP_CONTRIBUTORS], out[TOP_CONTRIBUTORS:]
        items = [{"name": names.get(k) or label_of(k), "id": k, "from": 0.0, "to": v, "change": v} for k, v in top]
        if rest:
            r = sum(v for _, v in rest)
            items.append({"name": f"All others ({len(rest)})", "id": "", "from": 0.0, "to": r, "change": r})
        items.sort(key=lambda i: (i["id"] == "", -i["change"]))
        return {"key": column, "label": vlabel, "items": items, "from": 0.0, "to": now[cid], "total_change": now[cid]}

    views = [view(c, LABEL.get(c, c)) for c in contrib]
    views.append(view(cp, f"{cp_label.capitalize()} (top {TOP_CONTRIBUTORS})", cp_name))

    # The stage mix of the exposures in this component, at both ends of the movement.
    key = _GRAIN[domain][1]
    pc = PERIOD_COL[domain]
    cond = {"new": "before.id IS NULL", "closed": "now.id IS NULL",
            "stage_migration": "now.id IS NOT NULL AND before.id IS NOT NULL AND now.stage <> before.stage"}.get(
        cid, "now.id IS NOT NULL AND before.id IS NOT NULL AND now.stage = before.stage")
    rows = _q(domain, f"""
        WITH now AS (SELECT {key} AS id, stage, ead_sar_mn AS ead FROM {rel} WHERE {pc} = ?),
        before AS (SELECT {key} AS id, stage, ead_sar_mn AS ead FROM {rel} WHERE {pc} = ?),
        j AS (SELECT now.stage AS s1, now.ead AS e1, before.stage AS s0, before.ead AS e0
              FROM now FULL OUTER JOIN before ON now.id = before.id WHERE {cond})
        SELECT 0, s0, SUM(e0) FROM j WHERE s0 IS NOT NULL GROUP BY 2
        UNION ALL SELECT 1, s1, SUM(e1) FROM j WHERE s1 IS NOT NULL GROUP BY 2""", period, comparison)
    mix = [{int(r[1]): float(r[2] or 0.0) for r in rows if r[0] == k} for k in (0, 1)]
    return {
        "domain": domain, "family": COMPONENT, "segment": cid, "segment_label": label, "dimension": "component",
        "dimension_label": "Component", "scope": "component",
        "trend_labels": {"segment": label, "book": "Total ECL movement"},
        "measure": "ecl_movement", "measure_label": f"{label}: contribution to the ECL movement", "kind": "amount",
        "unit": "SAR million", "period": period, "comparison_period": comparison, "period_noun": PERIOD_NOUN[domain],
        "trend": {"periods": upto, "segment": seg, "book": book, "current_index": len(upto) - 1},
        "peers": {"period": period, "book": movement, "book_label": "Total ECL movement",
                  "items": [{"segment": c, "label": component_label(domain, c), "value": now[c], "rows": 0, "is_segment": c == cid}
                            for c in COMPONENT_IDS]},
        "contributors": {"before": comparison, "after": period, "views": views},
        "stage_mix": {"periods": [comparison, period], "stages": [1, 2, 3],
                      "ead": [[mix[k].get(s, 0.0) for s in (1, 2, 3)] for k in (0, 1)], "unit": "SAR million",
                      "basis": f"Exposure at default of the {plural} in this component"},
        "source": f"{RELEASE[domain]}/{rel}",
    }
