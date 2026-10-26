"""Borrower 360: every tab for one corporate borrower or retail customer.

All figures are read from the v5 releases (see `paths`): the books for the
customer, its exposures, collateral and covenants; the Early Warning release
for the score, band and the rules fired; the synthetic Bureau and Open
Banking domains for the external signals. Nothing is computed that a release
does not publish, except stated aggregations (sums over a customer's
exposures, worst DPD, worst stage) and the customer EWS score, which is the
Early Warning service's own definition: the highest exposure score, banded by
the rule set's floors (backend/ews_domain/ews_rules.py).

A tab is a dict:

    {key, label, summary: [{label, value, unit}], tables: [{id, title,
     columns: [{key, label, unit}], rows}], series: [...per period...],
     note, meta}

`unit` tells the screen and the workbook how to show a value; the unit
"@unit" means each row carries its own (`row["unit"]`).
"""
from __future__ import annotations

import calendar
import re
from functools import lru_cache
from typing import Any, Callable

import pandas as pd

from backend.b360 import notes as demo_notes
from backend.b360 import paths
from backend.b360.store import NotFound, book_periods, clean, df, manifest, records, rows
from backend.ews_domain import ews_catalogue as cat
from backend.ews_domain import ews_rules as ews
from backend.v5common import ratings

SPEC: dict[str, dict[str, Any]] = {
    "corporate": {
        "owner": "borrower_id", "period": "reporting_quarter", "key": "facility_id",
        "rel": {"owner": "corp_borrower", "exp": "corp_facility", "coll": "corp_collateral",
                "cov": "corp_covenant", "ews": "ews_corp", "bureau": "bureau_corp", "ob": "ob_corp"},
        "book": paths.CORP_BOOK, "ews_release": paths.EWS_CORP, "frequency": "quarterly",
        "owner_label": "borrower", "exposure_label": "facility", "exposures_label": "facilities",
    },
    "retail": {
        "owner": "customer_id", "period": "reporting_month", "key": "account_id",
        "rel": {"owner": "ret_customer", "exp": "ret_account", "coll": "ret_collateral",
                "beh": "ret_behaviour", "ews": "ews_ret", "bureau": "bureau_ret", "ob": "ob_ret"},
        "book": paths.RET_BOOK, "ews_release": paths.EWS_RET, "frequency": "monthly",
        "owner_label": "customer", "exposure_label": "account", "exposures_label": "accounts",
    },
}

TABS: dict[str, list[tuple[str, str]]] = {
    "corporate": [
        ("profile", "Profile"), ("facilities", "Facilities"), ("exposure", "Exposure & ECL history"),
        ("ratings", "Ratings history"), ("stage-dpd", "Stage & DPD history"), ("collateral", "Collateral"),
        ("covenants", "Covenants"), ("financials", "Financials"), ("group", "Group"),
        ("relationships", "Relationships"), ("ews", "Early Warning signals"), ("bureau", "Bureau"), ("open-banking", "Open Banking"),
        ("notes", "Documents & notes"),
    ],
    "retail": [
        ("profile", "Profile"), ("facilities", "Accounts"), ("exposure", "Exposure & ECL history"),
        ("ratings", "Behaviour score history"), ("stage-dpd", "Stage & DPD history"),
        ("collateral", "Collateral"), ("financials", "Income (Open Banking)"),
        ("group", "Relationship"), ("relationships", "Household & employer"),
        ("ews", "Early Warning signals"), ("bureau", "Bureau"),
        ("open-banking", "Open Banking"), ("notes", "Documents & notes"),
    ],
}

#: Retail behaviour bands, best to worst (the book's own scale).
BEHAVIOUR_BANDS = ("A", "B", "C", "D", "E")

SOURCE_SHORT = {"bank_internal": "Bank internal", "bureau": "Bureau", "open_banking": "Open Banking"}


def spec(domain_id: str) -> dict[str, Any]:
    if domain_id not in SPEC:
        raise ValueError(f"{domain_id!r} is not a Borrower 360 book; use corporate or retail.")
    return SPEC[domain_id]


def tab_keys(domain_id: str) -> list[str]:
    return [k for k, _ in TABS[domain_id]]


def as_of(period: str) -> str:
    q = re.fullmatch(r"(\d{4})Q([1-4])", period or "")
    if q:
        y, m = int(q[1]), int(q[2]) * 3
    else:
        mm = re.fullmatch(r"(\d{4})-(\d{2})", period or "")
        if not mm:
            return period
        y, m = int(mm[1]), int(mm[2])
    return f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def col(key: str, label: str, unit: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "unit": unit}


def table(tid: str, title: str, columns: list[dict[str, str]], data: list[dict[str, Any]] | pd.DataFrame,
          note: str = "") -> dict[str, Any]:
    if isinstance(data, pd.DataFrame):
        keep = [c["key"] for c in columns if c["key"] in data.columns]
        data = records(data[keep]) if not data.empty else []
    out = {"id": tid, "title": title, "columns": columns, "rows": clean(data)}
    if note:
        out["note"] = note
    return out


def fig(label: str, value: Any, unit: str = "text") -> dict[str, Any]:
    return {"label": label, "value": clean(value), "unit": unit}


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f


# ------------------------------------------------------------------ EWS rules

@lru_cache(maxsize=4)
def rule_meta(domain_id: str) -> tuple[dict[str, Any], ...]:
    out = []
    for r in ews.RULES[domain_id]:
        meta = cat.signal_dict(domain_id, r["id"])
        src = meta.get("source") or "bank_internal"
        out.append({"id": r["id"], "label": r["label"], "weight": r["weight"], "condition": r["sql"],
                    "inputs": sorted(ews._columns(r["sql"])), "source": src,
                    "source_label": SOURCE_SHORT.get(src, src),
                    "source_catalogue_label": meta.get("source_label", ""),
                    "family": meta.get("family_label", ""), "layer": meta.get("layer_label", ""),
                    "limitation": r.get("limitation", "")})
    return tuple(out)


def _by_label(domain_id: str) -> dict[str, dict[str, Any]]:
    return {r["label"]: r for r in rule_meta(domain_id)}


def _value_read(row: dict[str, Any], inputs: list[str]) -> str:
    parts = []
    for c in inputs:
        v = clean(row.get(c))
        if isinstance(v, float):
            v = round(v, 2)
        parts.append(f"{c}={'∅' if v is None else v}")
    return ", ".join(parts)


def _reasons(text: Any) -> list[str]:
    return [x.strip() for x in str(text or "").split(";") if x.strip()]


# ------------------------------------------------------------------ the bundle

@lru_cache(maxsize=64)
def bundle(domain_id: str, owner_id: str) -> dict[str, pd.DataFrame]:
    """Every row any release holds for this customer, all periods."""
    s = spec(domain_id)
    out: dict[str, pd.DataFrame] = {}
    for name, rel in s["rel"].items():
        order = f'{s["period"]}' + (f', {s["key"]}' if name in ("exp", "ews", "coll", "cov", "beh") else "")
        if name == "coll":
            order = f'{s["period"]}, {"collateral_id" if domain_id == "corporate" else "account_id"}'
        if name == "cov":
            order = f'{s["period"]}, covenant_id'
        out[name] = df(f'SELECT * FROM {rel} WHERE {s["owner"]} = ? ORDER BY {order}', [owner_id])
    if out["exp"].empty:
        raise NotFound(f"{owner_id} is not a {s['owner_label']} in the {domain_id} book ({s['book']}).")
    return out


def periods_of(domain_id: str, owner_id: str) -> list[str]:
    s = spec(domain_id)
    return sorted(bundle(domain_id, owner_id)["exp"][s["period"]].unique().tolist())


def resolve(domain_id: str, owner_id: str, period: str) -> str:
    have = periods_of(domain_id, owner_id)
    if not period:
        return have[-1]
    if period not in book_periods(domain_id):
        raise NotFound(f"{period!r} is not a period of the {domain_id} book; it runs "
                       f"{book_periods(domain_id)[0]}..{book_periods(domain_id)[-1]}.")
    if period not in have:
        raise NotFound(f"{owner_id} is not on the {domain_id} book in {period}; it is on book "
                       f"{have[0]}..{have[-1]}.")
    return period


def _at(frame: pd.DataFrame, domain_id: str, period: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[frame[spec(domain_id)["period"]] == period]


def _one(frame: pd.DataFrame, domain_id: str, period: str) -> dict[str, Any]:
    at = _at(frame, domain_id, period)
    return clean(at.iloc[0].to_dict()) if not at.empty else {}


def ews_series(domain_id: str, b: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Customer score and band per period: the highest exposure score, banded."""
    s = spec(domain_id)
    e = b["ews"]
    if e.empty:
        return []
    labels = _by_label(domain_id)
    out = []
    for period, grp in e.groupby(s["period"], sort=True):
        score = int(grp["ews_score"].max())
        fired = sorted({x for r in grp["ews_reasons"] for x in _reasons(r)})
        by_src = {"bank_internal": 0, "bureau": 0, "open_banking": 0}
        for lab in fired:
            src = labels.get(lab, {}).get("source", "bank_internal")
            by_src[src] = by_src.get(src, 0) + 1
        out.append({"period": period, "score": score, "band": ews.band_of(domain_id, score),
                    "exposures": int(len(grp)), "rules_fired": len(fired),
                    "bank_internal": by_src["bank_internal"], "bureau": by_src["bureau"],
                    "open_banking": by_src["open_banking"], "reasons": "; ".join(fired)})
    return out


# ------------------------------------------------------------------ profile

def profile(domain_id: str, owner_id: str, period: str) -> dict[str, Any]:
    s = spec(domain_id)
    b = bundle(domain_id, owner_id)
    period = resolve(domain_id, owner_id, period)
    o = _one(b["owner"], domain_id, period)
    exp = _at(b["exp"], domain_id, period)
    ser = {p["period"]: p for p in ews_series(domain_id, b)}.get(period, {})
    corporate = domain_id == "corporate"
    out = {
        "domain_id": domain_id, "customer_id": owner_id, "period": period, "as_of": as_of(period),
        "periods": periods_of(domain_id, owner_id), "book_periods": list(book_periods(domain_id)),
        "frequency": s["frequency"], "currency": "SAR", "money_unit": "SAR million",
        "name": o.get("borrower_name") if corporate else None,
        "exposure": float(exp["ead_sar_mn"].sum()), "ecl": float(exp["ecl_sar_mn"].sum()),
        "limit": float(exp["limit_sar_mn"].sum()), "facilities": int(len(exp)),
        "worst_dpd": int(exp["dpd_days"].max()), "worst_stage": int(exp["stage"].max()),
        "ews_score": ser.get("score"), "ews_band": ser.get("band", "none"),
        "ews_ruleset": ews.RULESET_VERSION,
        "releases": {"book": s["book"], "ews": s["ews_release"], "bureau": paths.BUREAU,
                     "open_banking": paths.OPEN_BANKING},
        "labels": {"owner": s["owner_label"], "exposure": s["exposure_label"],
                   "exposures": s["exposures_label"]},
    }
    if corporate:
        out.update({"rating": o.get("rating_current"), "rating_label": "Rating",
                    "rating_previous": o.get("rating_previous"),
                    "rating_rank": ratings.rank(o.get("rating_current")),
                    "segment": o.get("sector"), "subsegment": o.get("sub_sector"), "region": o.get("region"),
                    "group_id": o.get("group_id"), "group_name": o.get("group_name"),
                    "relationship_tier": o.get("relationship_tier"),
                    "watchlist": bool(o.get("watchlist_flag")), "watchlist_reason": o.get("watchlist_reason") or "",
                    "outlook": o.get("rating_outlook")})
    else:
        out.update({"rating": o.get("score_band"), "rating_label": "Behaviour band",
                    "rating_previous": o.get("score_band_previous"), "behaviour_score": o.get("behaviour_score"),
                    "segment": o.get("customer_segment"), "subsegment": o.get("employment_type"),
                    "region": o.get("region"), "tenure_months": o.get("tenure_months"),
                    "accounts_held": o.get("accounts_held"),
                    "products": sorted(exp["product"].dropna().unique().tolist())})
    return clean(out)


def _tab_profile(ctx: Ctx) -> dict[str, Any]:
    p, o = ctx.profile, ctx.owner
    if ctx.corporate:
        fields = [
            ("Borrower id", p["customer_id"], "id"), ("Name", p.get("name"), "text"),
            ("Group", f'{o.get("group_id")} · {o.get("group_name")}', "text"), ("Sector", o.get("sector"), "text"),
            ("Sub-sector", o.get("sub_sector"), "text"), ("Region", o.get("region"), "text"),
            ("Relationship tier", o.get("relationship_tier"), "text"),
            ("Rating", o.get("rating_current"), "rating"), ("Previous rating", o.get("rating_previous"), "rating"),
            ("Rating at origination", o.get("rating_at_origination"), "rating"),
            ("Outlook", o.get("rating_outlook"), "text"), ("Rating migration", o.get("rating_migration"), "text"),
            ("Rating driver", o.get("rating_driver"), "text"), ("PD (TTC, 12m)", o.get("pd_ttc_12m"), "prob"),
            ("On watchlist", o.get("watchlist_flag"), "flag"), ("Watchlist reason", o.get("watchlist_reason") or "—", "text"),
            ("Quarters on watchlist", o.get("quarters_on_watchlist"), "int"),
            ("Restructured", o.get("restructured_flag"), "flag"), ("Qualitative score", o.get("qualitative_score"), "num"),
        ]
    else:
        fields = [
            ("Customer id", p["customer_id"], "id"), ("Segment", o.get("customer_segment"), "text"),
            ("Employment", o.get("employment_type"), "text"), ("Region", o.get("region"), "text"),
            ("Tenure (months)", o.get("tenure_months"), "int"), ("Accounts held", o.get("accounts_held"), "int"),
            ("Products", ", ".join(p.get("products") or []), "text"),
            ("Behaviour score", o.get("behaviour_score"), "num"), ("Behaviour band", o.get("score_band"), "text"),
            ("Previous band", o.get("score_band_previous"), "text"),
            ("Score migration", o.get("score_migration"), "text"),
        ]
    fields += [
        ("Exposure (EAD)", p["exposure"], "sar_mn"), ("Limit", p["limit"], "sar_mn"), ("ECL", p["ecl"], "sar_mn"),
        (f'{ctx.s["exposures_label"].capitalize()} on book', p["facilities"], "int"),
        ("Worst DPD", p["worst_dpd"], "days"), ("Worst stage", p["worst_stage"], "int"),
        ("Early Warning score", p.get("ews_score"), "int"), ("Early Warning band", p.get("ews_band"), "ews_band"),
        ("Early Warning rule set", ews.RULESET_VERSION, "text"),
        ("Book release", p["releases"]["book"], "id"), ("Early Warning release", p["releases"]["ews"], "id"),
    ]
    summary = [fig("Exposure (EAD)", p["exposure"], "sar_mn"), fig("ECL", p["ecl"], "sar_mn"),
               fig(ctx.s["exposures_label"].capitalize(), p["facilities"], "int"),
               fig(p["rating_label"], p.get("rating"), "rating" if ctx.corporate else "text"),
               fig("EWS band", p.get("ews_band"), "ews_band"), fig("Worst DPD", p["worst_dpd"], "days"),
               fig("Worst stage", p["worst_stage"], "int")]
    return {"summary": summary, "tables": [table(
        "fields", "Profile", [col("label", "Field"), col("value", "Value", "@unit")],
        [{"label": a, "value": v, "unit": u} for a, v, u in fields])]}


# ------------------------------------------------------------------ context

class Ctx:
    def __init__(self, domain_id: str, owner_id: str, period: str):
        self.domain_id = domain_id
        self.owner_id = owner_id
        self.s = spec(domain_id)
        self.b = bundle(domain_id, owner_id)
        self.period = resolve(domain_id, owner_id, period)
        self.corporate = domain_id == "corporate"
        self.P, self.K = self.s["period"], self.s["key"]
        self.owner = _one(self.b["owner"], domain_id, self.period)
        self.exp = _at(self.b["exp"], domain_id, self.period)
        self.ews = _at(self.b["ews"], domain_id, self.period)
        self.profile = profile(domain_id, owner_id, self.period)
        self.series = ews_series(domain_id, self.b)

    def at(self, name: str) -> pd.DataFrame:
        return _at(self.b[name], self.domain_id, self.period)


# ------------------------------------------------------------------ facilities

def _tab_facilities(ctx: Ctx) -> dict[str, Any]:
    exp = ctx.exp.copy()
    e = ctx.ews[[ctx.K, "ews_score", "ews_band", "ews_reasons"]] if not ctx.ews.empty else pd.DataFrame(
        columns=[ctx.K, "ews_score", "ews_band", "ews_reasons"])
    exp = exp.merge(e, on=ctx.K, how="left").sort_values(["ead_sar_mn", ctx.K], ascending=[False, True])
    if ctx.corporate:
        cols = [col("facility_id", "Facility", "id"), col("product_type", "Product"),
                col("facility_class", "Class"), col("limit_sar_mn", "Limit", "sar_mn"),
                col("drawn_sar_mn", "Drawn", "sar_mn"), col("undrawn_sar_mn", "Undrawn", "sar_mn"),
                col("utilisation_pct", "Utilisation", "pct"), col("ead_sar_mn", "EAD", "sar_mn"),
                col("stage", "Stage", "int"), col("sicr_flag", "SICR", "flag"),
                col("default_flag", "Default", "flag"), col("dpd_days", "DPD", "days"),
                col("pd_pit_12m", "PD (PIT 12m)", "prob"), col("pd_lifetime", "PD (lifetime)", "prob"),
                col("lgd_pct", "LGD", "pct"), col("ecl_sar_mn", "ECL", "sar_mn"),
                col("ecl_coverage_pct", "ECL cover", "pct"), col("origination_quarter", "Originated", "period"),
                col("quarters_in_stage", "Quarters in stage", "int"),
                col("ews_score", "EWS score", "int"), col("ews_band", "EWS band", "ews_band")]
    else:
        cols = [col("account_id", "Account", "id"), col("product", "Product"), col("sub_product", "Sub-product"),
                col("secured_flag", "Secured", "flag"), col("origination_month", "Originated", "period"),
                col("months_on_book", "Months on book", "int"), col("limit_sar_mn", "Limit", "sar_mn"),
                col("balance_sar_mn", "Balance", "sar_mn"), col("utilisation_pct", "Utilisation", "pct"),
                col("ead_sar_mn", "EAD", "sar_mn"), col("stage", "Stage", "int"), col("dpd_days", "DPD", "days"),
                col("delinquency_bucket", "Bucket"), col("pd_pit_12m", "PD (PIT 12m)", "prob"),
                col("lgd_pct", "LGD", "pct"), col("ecl_sar_mn", "ECL", "sar_mn"),
                col("behaviour_score", "Behaviour score", "num"), col("score_band", "Band"),
                col("ews_score", "EWS score", "int"), col("ews_band", "EWS band", "ews_band")]
    summary = [fig(ctx.s["exposures_label"].capitalize(), len(exp), "int"),
               fig("Limit", exp["limit_sar_mn"].sum(), "sar_mn"), fig("EAD", exp["ead_sar_mn"].sum(), "sar_mn"),
               fig("ECL", exp["ecl_sar_mn"].sum(), "sar_mn"),
               fig("Utilisation (EAD-weighted)", _wavg(exp, "utilisation_pct", "ead_sar_mn"), "pct")]
    return {"summary": summary, "tables": [table("exposures", f'{ctx.s["exposures_label"].capitalize()} at {ctx.period}',
                                                  cols, exp)]}


def _wavg(frame: pd.DataFrame, value: str, weight: str) -> float | None:
    w = frame[weight].fillna(0)
    return float((frame[value].fillna(0) * w).sum() / w.sum()) if w.sum() else None


# ------------------------------------------------------------------ exposure history

def _tab_exposure(ctx: Ctx) -> dict[str, Any]:
    e = ctx.b["exp"]
    drawn = "drawn_sar_mn" if ctx.corporate else "balance_sar_mn"
    g = e.groupby(ctx.P, sort=True).agg(exposures=(ctx.K, "count"), limit=("limit_sar_mn", "sum"),
                                        drawn=(drawn, "sum"), ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"),
                                        write_off=("write_off_sar_mn", "sum"),
                                        recovery=("recovery_sar_mn", "sum")).reset_index()
    g["coverage_pct"] = (100 * g["ecl"] / g["ead"]).where(g["ead"] > 0)
    g = g.rename(columns={ctx.P: "period"})
    hist_cols = [col("period", "Period", "period"), col("exposures", ctx.s["exposures_label"].capitalize(), "int"),
                 col("limit", "Limit", "sar_mn"), col("drawn", "Drawn" if ctx.corporate else "Balance", "sar_mn"),
                 col("ead", "EAD", "sar_mn"), col("ecl", "ECL", "sar_mn"), col("coverage_pct", "ECL cover", "pct"),
                 col("write_off", "Write-off", "sar_mn"), col("recovery", "Recovery", "sar_mn")]
    long = e[[ctx.P, ctx.K, "product_type" if ctx.corporate else "product", "ead_sar_mn", "ecl_sar_mn"]].rename(
        columns={ctx.P: "period", ctx.K: "exposure_id", "product_type": "product"})
    first, last = g.iloc[0], g.iloc[-1]
    cur = g[g["period"] == ctx.period].iloc[0]
    peak = g.loc[g["ead"].idxmax()]
    summary = [fig(f"EAD at {ctx.period}", cur["ead"], "sar_mn"), fig(f"ECL at {ctx.period}", cur["ecl"], "sar_mn"),
               fig("ECL cover", cur["coverage_pct"], "pct"),
               fig(f"EAD when first on book ({first['period']})", first["ead"], "sar_mn"),
               fig(f"Peak EAD ({peak['period']})", peak["ead"], "sar_mn"),
               fig(f"Periods on book (to {last['period']})", len(g), "int")]
    series = records(g)
    return {"summary": summary, "series": series,
            "tables": [table("history", "Exposure and ECL, every period", hist_cols, g),
                       table("by_exposure", f"EAD and ECL by {ctx.s['exposure_label']}, every period",
                             [col("period", "Period", "period"), col("exposure_id", ctx.s["exposure_label"].capitalize(), "id"),
                              col("product", "Product"), col("ead_sar_mn", "EAD", "sar_mn"),
                              col("ecl_sar_mn", "ECL", "sar_mn")], long)]}


# ------------------------------------------------------------------ ratings / behaviour score

def _tab_ratings(ctx: Ctx) -> dict[str, Any]:
    o = ctx.b["owner"].copy()
    if ctx.corporate:
        o["rating_rank"] = o["rating_current"].map(ratings.rank)
        o = o.rename(columns={ctx.P: "period"}).sort_values("period")
        cols = [col("period", "Period", "period"), col("rating_current", "Rating", "rating"),
                col("rating_previous", "Previous", "rating"), col("rating_at_origination", "At origination", "rating"),
                col("rating_notches_moved", "Notches moved", "int"),
                col("rating_notches_from_origination", "Notches from origination", "int"),
                col("rating_migration", "Migration"), col("rating_outlook", "Outlook"),
                col("rating_driver", "Driver"), col("pd_ttc_12m", "PD (TTC 12m)", "prob")]
        held = (o.groupby("rating_current").agg(quarters=("period", "count"), first=("period", "min"),
                                                last=("period", "max")).reset_index())
        held["rank"] = held["rating_current"].map(ratings.rank)
        held = held.sort_values("rank")
        cur = o[o["period"] == ctx.period].iloc[0]
        summary = [fig("Rating", cur["rating_current"], "rating"), fig("Previous", cur["rating_previous"], "rating"),
                   fig("At origination", cur["rating_at_origination"], "rating"),
                   fig("Notches from origination", cur["rating_notches_from_origination"], "int"),
                   fig("Outlook", cur["rating_outlook"]), fig("PD (TTC 12m)", cur["pd_ttc_12m"], "prob")]
        series = records(o[["period", "rating_current", "rating_rank", "rating_at_origination", "pd_ttc_12m",
                            "rating_outlook", "rating_migration"]])
        return {"summary": summary, "series": series,
                "meta": {"rating_order": list(ratings.RATING_ORDER)},
                "tables": [table("history", "Rating, every quarter (in period order)", cols, o),
                           table("held", "Ratings held, in the global rating order (best first)",
                                 [col("rating_current", "Rating", "rating"), col("quarters", "Quarters", "int"),
                                  col("first", "First", "period"), col("last", "Last", "period")], held)],
                "note": "Ratings are shown on the global scale AAA (best) to D (worst), backend/v5common/ratings.py."}
    o = o.rename(columns={ctx.P: "period"}).sort_values("period")
    o["band_rank"] = o["score_band"].map({b: i for i, b in enumerate(BEHAVIOUR_BANDS)})
    cols = [col("period", "Period", "period"), col("behaviour_score", "Behaviour score", "num"),
            col("behaviour_score_previous", "Previous", "num"), col("behaviour_score_change", "Change", "num"),
            col("score_band", "Band"), col("score_band_previous", "Previous band"),
            col("score_migration", "Migration")]
    held = o.groupby("score_band").agg(months=("period", "count"), first=("period", "min"),
                                       last=("period", "max")).reset_index()
    held["order"] = held["score_band"].map({b: i for i, b in enumerate(BEHAVIOUR_BANDS)})
    held = held.sort_values("order")
    beh = ctx.at("beh")
    beh_cols = [col("account_id", "Account", "id"), col("product", "Product"),
                col("utilisation_pct", "Utilisation", "pct"), col("utilisation_change_pp", "Utilisation change (pp)", "num"),
                col("payment_ratio_pct", "Payment ratio", "pct"), col("missed_payments_12m", "Missed payments 12m", "int"),
                col("delinquency_streak_months", "Delinquency streak (months)", "int"),
                col("balance_growth_pct", "Balance growth", "pct"), col("cash_advance_ratio_pct", "Cash advance ratio", "pct"),
                col("overlimit_flag", "Over limit", "flag"), col("inflow_change_pct", "Inflow change", "pct"),
                col("bureau_inquiries_6m", "Bureau enquiries 6m", "int"),
                col("repayment_behaviour_score", "Repayment behaviour score", "num")]
    cur = o[o["period"] == ctx.period]
    cur = cur.iloc[0] if not cur.empty else {}
    summary = [fig("Behaviour score", cur.get("behaviour_score"), "num"), fig("Band", cur.get("score_band")),
               fig("Previous band", cur.get("score_band_previous")), fig("Migration", cur.get("score_migration")),
               fig("Change", cur.get("behaviour_score_change"), "num")]
    return {"summary": summary, "series": records(o[["period", "behaviour_score", "score_band", "band_rank",
                                                     "score_migration"]]),
            "meta": {"band_order": list(BEHAVIOUR_BANDS)},
            "tables": [table("history", "Behaviour score and band, every month (in period order)", cols, o),
                       table("held", "Bands held, best (A) to worst (E)",
                             [col("score_band", "Band"), col("months", "Months", "int"),
                              col("first", "First", "period"), col("last", "Last", "period")], held),
                       table("behaviour", f"Account behaviour at {ctx.period}", beh_cols, beh)],
            "note": "Retail customers carry a behaviour score and band (A best .. E worst), not a rating."}


# ------------------------------------------------------------------ stage & DPD

def _tab_stage_dpd(ctx: Ctx) -> dict[str, Any]:
    e = ctx.b["exp"].copy()
    e["s1"] = (e["stage"] == 1).astype(int)
    e["s2"] = (e["stage"] == 2).astype(int)
    e["s3"] = (e["stage"] == 3).astype(int)
    e["dpd30"] = (e["dpd_days"] >= 30).astype(int)
    g = e.groupby(ctx.P, sort=True).agg(exposures=(ctx.K, "count"), worst_stage=("stage", "max"),
                                        worst_dpd=("dpd_days", "max"), stage1=("s1", "sum"), stage2=("s2", "sum"),
                                        stage3=("s3", "sum"), sicr=("sicr_flag", "sum"),
                                        defaulted=("default_flag", "sum"), dpd30=("dpd30", "sum"),
                                        ead=("ead_sar_mn", "sum")).reset_index().rename(columns={ctx.P: "period"})
    cols = [col("period", "Period", "period"), col("exposures", ctx.s["exposures_label"].capitalize(), "int"),
            col("worst_stage", "Worst stage", "int"), col("worst_dpd", "Worst DPD", "days"),
            col("stage1", "In stage 1", "int"), col("stage2", "In stage 2", "int"), col("stage3", "In stage 3", "int"),
            col("sicr", "SICR flags", "int"), col("defaulted", "In default", "int"),
            col("dpd30", "30+ DPD", "int")]
    long_cols = [col("period", "Period", "period"), col(ctx.K, ctx.s["exposure_label"].capitalize(), "id"),
                 col("stage", "Stage", "int"), col("dpd_days", "DPD", "days"), col("sicr_flag", "SICR", "flag"),
                 col("default_flag", "Default", "flag"), col("cure_flag", "Cure", "flag")]
    if ctx.corporate:
        long_cols.append(col("quarters_in_stage", "Quarters in stage", "int"))
    else:
        long_cols.append(col("delinquency_bucket", "Bucket"))
    long = e.rename(columns={ctx.P: "period"}).sort_values(["period", ctx.K])
    cur = g[g["period"] == ctx.period].iloc[0]
    summary = [fig("Worst stage", cur["worst_stage"], "int"), fig("Worst DPD", cur["worst_dpd"], "days"),
               fig("In stage 2", cur["stage2"], "int"), fig("In stage 3", cur["stage3"], "int"),
               fig("Highest DPD ever", g["worst_dpd"].max(), "days"),
               fig("Periods in stage 3", int((g["stage3"] > 0).sum()), "int")]
    pivot = e.pivot_table(index=ctx.P, columns=ctx.K, values="dpd_days", aggfunc="max").sort_index()
    by_exp = [{"exposure_id": k, "periods": list(pivot.index), "dpd": [clean(v) for v in pivot[k].tolist()]}
              for k in pivot.columns]
    return {"summary": summary, "series": records(g), "meta": {"dpd_by_exposure": by_exp},
            "tables": [table("history", "Stage and DPD, every period", cols, g),
                       table("by_exposure", f"Stage and DPD by {ctx.s['exposure_label']}, every period", long_cols, long)]}


# ------------------------------------------------------------------ collateral

def _tab_collateral(ctx: Ctx) -> dict[str, Any]:
    c = ctx.b["coll"]
    at = ctx.at("coll")
    ead_by_p = ctx.b["exp"].groupby(ctx.P)["ead_sar_mn"].sum()
    if ctx.corporate:
        cols = [col("collateral_id", "Collateral", "id"), col("facility_id", "Facility", "id"),
                col("collateral_type", "Type"), col("market_value_sar_mn", "Market value", "sar_mn"),
                col("haircut_pct", "Haircut", "pct"), col("allocated_value_sar_mn", "Allocated value", "sar_mn"),
                col("coverage_pct", "Coverage", "pct"), col("ltv_pct", "LTV", "pct"),
                col("valuation_age_quarters", "Valuation age (quarters)", "int")]
        value, alloc = "market_value_sar_mn", "allocated_value_sar_mn"
    else:
        cols = [col("account_id", "Account", "id"), col("product", "Product"), col("collateral_type", "Type"),
                col("collateral_value_sar_mn", "Collateral value", "sar_mn"), col("ltv_pct", "LTV", "pct"),
                col("collateral_coverage_pct", "Coverage", "pct"),
                col("valuation_age_months", "Valuation age (months)", "int")]
        value, alloc = "collateral_value_sar_mn", "collateral_value_sar_mn"
    if c.empty:
        hist = pd.DataFrame(columns=["period", "items", "value", "allocated", "ead", "cover_pct", "avg_ltv_pct"])
    else:
        hist = c.groupby(ctx.P, sort=True).agg(items=(ctx.K if not ctx.corporate else "collateral_id", "count"),
                                               value=(value, "sum"), allocated=(alloc, "sum"),
                                               avg_ltv_pct=("ltv_pct", "mean")).reset_index()
        hist["ead"] = hist[ctx.P].map(ead_by_p)
        hist["cover_pct"] = (100 * hist["allocated"] / hist["ead"]).where(hist["ead"] > 0)
        hist = hist.rename(columns={ctx.P: "period"})
    hist_cols = [col("period", "Period", "period"), col("items", "Items", "int"),
                 col("value", "Value", "sar_mn"), col("allocated", "Allocated" if ctx.corporate else "Value (allocated)",
                                                      "sar_mn"),
                 col("ead", "EAD", "sar_mn"), col("cover_pct", "Collateral over EAD", "pct"),
                 col("avg_ltv_pct", "Average LTV", "pct")]
    cur = hist[hist["period"] == ctx.period]
    cur = cur.iloc[0] if not cur.empty else {}
    summary = [fig("Collateral items", len(at), "int"), fig("Value", at[value].sum() if not at.empty else 0, "sar_mn"),
               fig("Collateral over EAD", cur.get("cover_pct"), "pct"), fig("Average LTV", cur.get("avg_ltv_pct"), "pct")]
    return {"summary": summary, "series": records(hist),
            "tables": [table("items", f"Collateral at {ctx.period}", cols, at,
                             note="" if not at.empty else f"No collateral recorded against this {ctx.s['owner_label']} "
                                                          f"at {ctx.period}."),
                       table("history", "Collateral, every period", hist_cols, hist)],
            "note": ("'Collateral over EAD' is the sum of allocated collateral value (corporate) or collateral value "
                     "(retail) over the sum of EAD at the period.")}


# ------------------------------------------------------------------ covenants

def _tab_covenants(ctx: Ctx) -> dict[str, Any]:
    c = ctx.b["cov"].copy()
    at = ctx.at("cov").sort_values(["breach_flag", "headroom_pct"], ascending=[False, True])
    cols = [col("covenant_id", "Covenant", "id"), col("facility_id", "Facility", "id"),
            col("covenant_type", "Type"), col("threshold_value", "Threshold", "num"),
            col("observed_value", "Observed", "num"), col("headroom_pct", "Headroom", "pct"),
            col("test_status", "Status"), col("breach_flag", "Breach", "flag"), col("waiver_flag", "Waiver", "flag"),
            col("waiver_status", "Waiver status"), col("waiver_quarter", "Waiver quarter", "period"),
            col("consecutive_breaches", "Consecutive breaches", "int")]
    if c.empty:
        hist = pd.DataFrame(columns=["period", "tested", "breaches", "watch", "waivers", "min_headroom_pct",
                                     "max_consecutive"])
    else:
        c["watch"] = (c["test_status"] == "WATCH").astype(int)
        c["granted"] = (c["waiver_status"] == "GRANTED").astype(int)
        hist = c.groupby(ctx.P, sort=True).agg(tested=("covenant_id", "count"), breaches=("breach_flag", "sum"),
                                               watch=("watch", "sum"), waivers=("granted", "sum"),
                                               min_headroom_pct=("headroom_pct", "min"),
                                               max_consecutive=("consecutive_breaches", "max")).reset_index()
        hist = hist.rename(columns={ctx.P: "period"})
    hist_cols = [col("period", "Period", "period"), col("tested", "Tested", "int"), col("breaches", "Breaches", "int"),
                 col("watch", "On watch", "int"), col("waivers", "Waivers granted", "int"),
                 col("min_headroom_pct", "Lowest headroom", "pct"),
                 col("max_consecutive", "Most consecutive breaches", "int")]
    summary = [fig("Covenants tested", len(at), "int"), fig("Breaches", int(at["breach_flag"].sum()) if not at.empty else 0, "int"),
               fig("Waivers", int(at["waiver_flag"].sum()) if not at.empty else 0, "int"),
               fig("Lowest headroom", at["headroom_pct"].min() if not at.empty else None, "pct"),
               fig("Quarters with a breach", int((hist["breaches"] > 0).sum()) if not hist.empty else 0, "int")]
    return {"summary": summary, "series": records(hist),
            "tables": [table("tests", f"Covenant tests at {ctx.period}", cols, at),
                       table("history", "Covenants, every quarter", hist_cols, hist)]}


# ------------------------------------------------------------------ financials

FIN_COLS = [("revenue_sar_mn", "Revenue", "sar_mn"), ("ebitda_sar_mn", "EBITDA", "sar_mn"),
            ("ebit_sar_mn", "EBIT", "sar_mn"), ("operating_cash_flow_sar_mn", "Operating cash flow", "sar_mn"),
            ("total_debt_sar_mn", "Total debt", "sar_mn"), ("cash_sar_mn", "Cash", "sar_mn"),
            ("net_debt_sar_mn", "Net debt", "sar_mn"), ("leverage_x", "Leverage", "x"), ("dscr_x", "DSCR", "x"),
            ("interest_cover_x", "Interest cover", "x"), ("current_ratio_x", "Current ratio", "x"),
            ("quick_ratio_x", "Quick ratio", "x"), ("ebitda_margin_pct", "EBITDA margin", "pct"),
            ("return_on_assets_pct", "Return on assets", "pct"), ("cash_conversion_pct", "Cash conversion", "pct"),
            ("qualitative_score", "Qualitative score", "num")]


def _tab_financials(ctx: Ctx) -> dict[str, Any]:
    if ctx.corporate:
        o = ctx.b["owner"].rename(columns={ctx.P: "period"}).sort_values("period")
        cols = [col("period", "Period", "period")] + [col(k, lab, u) for k, lab, u in FIN_COLS]
        cur = o[o["period"] == ctx.period].iloc[0]
        summary = [fig(lab, cur[k], u) for k, lab, u in FIN_COLS
                   if k in ("revenue_sar_mn", "ebitda_sar_mn", "net_debt_sar_mn", "leverage_x", "dscr_x",
                            "interest_cover_x")]
        return {"summary": summary, "series": records(o[["period"] + [k for k, _, _ in FIN_COLS]]),
                "tables": [table("history", "Financials, every quarter", cols, o)],
                "note": "Financials as the corporate book publishes them (SAR million; ratios in times)."}
    ob = ctx.b["ob"].rename(columns={ctx.P: "period"}).sort_values("period").copy()
    if ob.empty:
        return {"summary": [], "series": [], "tables": [],
                "note": "Open Banking publishes no inflows for this customer."}
    ob["inflows_3m_avg_sar_k"] = ob["total_inflows_sar_k"].rolling(3, min_periods=1).mean()
    ob["inflows_12m_sar_k"] = ob["total_inflows_sar_k"].rolling(12, min_periods=1).sum()
    cols = [col("period", "Month", "period"), col("total_inflows_sar_k", "Inflows", "sar_k"),
            col("inflows_3m_avg_sar_k", "Inflows, 3-month average", "sar_k"),
            col("inflows_12m_sar_k", "Inflows, trailing 12 months observed", "sar_k"),
            col("inflow_trend_pct", "Inflow trend (vs 3 months earlier)", "pct"),
            col("salaried_flag", "Salaried", "flag"), col("salary_credit_flag", "Salary credit", "flag"),
            col("salary_interruption_flag", "Salary missing", "flag"),
            col("balance_buffer_months", "Balance buffer (months)", "months")]
    cur = ob[ob["period"] == ctx.period]
    cur = cur.iloc[0] if not cur.empty else {}
    summary = [fig("Inflows this month", cur.get("total_inflows_sar_k"), "sar_k"),
               fig("3-month average", cur.get("inflows_3m_avg_sar_k"), "sar_k"),
               fig("Trailing 12 months observed", cur.get("inflows_12m_sar_k"), "sar_k"),
               fig("Salary credit", cur.get("salary_credit_flag"), "flag"),
               fig("Balance buffer", cur.get("balance_buffer_months"), "months")]
    return {"summary": summary, "series": records(ob[[c["key"] for c in cols]]),
            "tables": [table("history", "Income proxies from Open Banking inflows, every month", cols, ob)],
            "note": ("The retail book publishes no income field. These are income PROXIES read from the "
                     "Open Banking domain: credits into the customer's accounts (SAR thousand) and the salary-credit "
                     "flags. The trailing-12-month figure sums the months observed, fewer for newer customers.")}


# ------------------------------------------------------------------ group / relationship

def _tab_group(ctx: Ctx) -> dict[str, Any]:
    """The connected group, from the relationship domain: a handful of related companies, one parent, the rest owned
    or influenced by it. The book's own `group_id` is shown beside it and reconciled (every group sits inside exactly
    one book group)."""
    if not ctx.corporate:
        return _tab_relationship(ctx)
    from backend.b360 import graph as rel

    members = rel._group_of(ctx.period, ctx.owner_id)
    book_gid, book_gname = ctx.owner.get("group_id"), ctx.owner.get("group_name")
    pol = rel.policy_limit()
    if not members:
        cols = [col("borrower_id", "Borrower", "id"), col("borrower_name", "Name")]
        me = ctx.profile["exposure"]
        return {"summary": [fig("Group", "Stand-alone borrower"), fig("Members", 1, "int"),
                            fig("Exposure", me, "sar_mn"), fig(f"{pol['clause']} group limit", pol["limit_sar_mn"], "sar_mn")],
                "series": [], "meta": {"group_id": None, "book_group_id": book_gid, "standalone": True,
                                       "rating_order": list(ratings.RATING_ORDER)},
                "tables": [table("members", f"Borrowers connected to {ctx.owner.get('borrower_name')} at {ctx.period}", cols, [])],
                "note": (f"No other borrower in the book is connected to this one by ownership or control. The book's group "
                         f"field names it {book_gid} {book_gname}, a holding with this one borrower.")}
    ids = [m["borrower_id"] for m in members]
    attrs = rel._node_attrs(ctx.period, ids)
    warned_min = ews.floor("corporate", "moderate")
    out_rows = []
    for m in members:
        a = attrs.get(m["borrower_id"], {})
        out_rows.append({"borrower_id": m["borrower_id"], "borrower_name": a.get("borrower_name"), "role": m["role"],
                         "ownership_pct": m["ownership_pct"], "sector": a.get("sector"), "region": a.get("region"),
                         "rating_current": a.get("rating_current"), "facilities": a.get("facilities"), "ead": a.get("ead"),
                         "ecl": a.get("ecl"), "worst_stage": a.get("worst_stage"), "worst_dpd": a.get("worst_dpd"),
                         "watchlist_flag": a.get("watchlist_flag"), "ews_score": a.get("score"),
                         "ews_band": a.get("ews_band"), "is_self": m["borrower_id"] == ctx.owner_id})
    total = sum(_num(r.get("ead")) for r in out_rows)
    mix: dict[str, dict[str, Any]] = {}
    for m in out_rows:
        r = m.get("rating_current") or "unrated"
        x = mix.setdefault(r, {"rating": r, "borrowers": 0, "ead": 0.0, "warned": 0, "watchlist": 0})
        x["borrowers"] += 1
        x["ead"] += _num(m.get("ead"))
        x["warned"] += int((m.get("ews_score") or 0) >= warned_min)
        x["watchlist"] += int(m.get("watchlist_flag") or 0)
    mix_rows = sorted(mix.values(), key=lambda x: ratings.sort_key(x["rating"]))
    cols = [col("borrower_id", "Borrower", "id"), col("borrower_name", "Name"), col("role", "Role in group"),
            col("ownership_pct", "Held by parent %", "pct"), col("sector", "Sector"), col("region", "Region"),
            col("rating_current", "Rating", "rating"), col("facilities", "Facilities", "int"), col("ead", "EAD", "sar_mn"),
            col("ecl", "ECL", "sar_mn"), col("worst_stage", "Worst stage", "int"), col("worst_dpd", "Worst DPD", "days"),
            col("watchlist_flag", "Watchlist", "flag"), col("ews_score", "EWS score", "int"), col("ews_band", "EWS band", "ews_band")]
    me = ctx.profile["exposure"]
    summary = [fig("Group", f"{members[0]['group_id']} · {members[0]['group_name']}"), fig("Members", len(out_rows), "int"),
               fig("Group EAD", total, "sar_mn"), fig(f"{pol['clause']} group limit", pol["limit_sar_mn"], "sar_mn"),
               fig("Limit used", 100 * total / pol["limit_sar_mn"], "pct"),
               fig("This borrower's share", 100 * me / total if total else None, "pct"),
               fig("Members warned", sum(1 for m in out_rows if (m.get("ews_score") or 0) >= warned_min), "int"),
               fig("Members on watchlist", sum(int(m.get("watchlist_flag") or 0) for m in out_rows), "int")]
    return {"summary": summary, "series": [],
            "meta": {"group_id": members[0]["group_id"], "group_name": members[0]["group_name"],
                     "book_group_id": book_gid, "book_group_name": book_gname, "sectors": len({m.get("sector") for m in out_rows}),
                     "limit_sar_mn": pol["limit_sar_mn"], "rating_order": list(ratings.RATING_ORDER)},
            "tables": [table("members", f"Borrowers in group {members[0]['group_id']} at {ctx.period} (parent first)", cols, out_rows),
                       table("rating_mix", "Group members by rating, in the global rating order (best first)",
                             [col("rating", "Rating", "rating"), col("borrowers", "Borrowers", "int"),
                              col("ead", "EAD", "sar_mn"), col("warned", "Warned (EWS moderate or worse)", "int"),
                              col("watchlist", "On watchlist", "int")], mix_rows)],
            "note": (f"Connected group from the relationship domain: one parent and the companies it owns or influences. "
                     f"The book's own group field reads {book_gid} {book_gname}; every group here sits inside exactly one book "
                     f"group, and a book group of several hundred names is split into groups of a handful. "
                     f"The Relationships tab draws the group and every other link.")}


def _tab_relationships(ctx: Ctx) -> dict[str, Any]:
    """The relationship graph and the analytics beside it (backend/b360/graph.py)."""
    from backend.b360 import graph as rel

    g = rel.build(ctx.domain_id, ctx.owner_id, ctx.period)
    a = g["analytics"]
    if ctx.corporate:
        grp, sup, cus, con, col_, gu = a["group"], a["suppliers"], a["customers"], a["contagion"], a["collateral"], a["guarantees"]
        summary = [fig("Related names drawn", len([n for n in g["nodes"] if n["type"] == "borrower" and not n["is_focal"]]), "int"),
                   fig("Links", len(g["edges"]), "int"),
                   fig("Group exposure vs limit", grp.get("utilisation_pct"), "pct") if not grp["standalone"] else fig("Group", "Stand-alone"),
                   fig("Largest supplier share of purchases", sup["largest_share_pct"] if sup["count"] else None, "pct"),
                   fig("Largest customer share of revenue", cus["largest_share_pct"] if cus["count"] else None, "pct"),
                   fig("Related names in Early Warning", con["in_early_warning"], "int"),
                   fig("Shared collateral assets", col_["count"], "int")]
        tables = []
        if not grp["standalone"]:
            tables.append(table("group", f"Connected group against {grp['policy']['clause']} ({grp['policy']['title']})",
                                [col("borrower_id", "Borrower", "id"), col("name", "Name"), col("role", "Role"),
                                 col("ownership_pct", "Held by parent %", "pct"), col("exposure", "EAD", "sar_mn"),
                                 col("share_pct", "Share of group", "pct"), col("rating", "Rating", "rating"),
                                 col("ews_band", "EWS band", "ews_band")], grp["rows"]))
        scols = [col("borrower_id", "Borrower", "id"), col("name", "Name"), col("sector", "Sector"),
                 col("purchase_share_pct", "Share of purchases %", "pct"), col("revenue_share_pct", "Share of their revenue %", "pct"),
                 col("annual_value_sar_mn", "Annual value", "sar_mn"), col("exposure", "EAD with the bank", "sar_mn"),
                 col("rating", "Rating", "rating"), col("ews_band", "EWS band", "ews_band")]
        tables += [table("suppliers", "Suppliers in the bank's book", scols, sup["rows"]),
                   table("customers", "Customers (buyers) in the bank's book", scols, cus["rows"]),
                   table("contagion", "Related names and their Early Warning band",
                         [col("borrower_id", "Borrower", "id"), col("name", "Name"), col("kinds", "Linked as"),
                          col("ews_band", "EWS band", "ews_band"), col("ews_score", "EWS score", "int"),
                          col("exposure", "EAD", "sar_mn"), col("rating", "Rating", "rating"), col("watchlist", "Watchlist", "flag")],
                         [{**r, "kinds": ", ".join(r["kinds"])} for r in con["rows"]]),
                   table("collateral", "Shared collateral: assets this borrower claims together with others",
                         [col("collateral_id", "Asset", "id"), col("type", "Type"), col("market_value", "Market value", "sar_mn"),
                          col("claimants", "Claimants"), col("total_pct", "Claimed of value %", "pct"), col("over_pledged", "Over-pledged", "flag")],
                         [{**x, "claimants": ", ".join(f"{c['borrower_id']} {c['allocation_pct']:.0f}%" for c in x["claims"])}
                          for x in col_["assets"]]),
                   table("guarantees", "Guarantees given and received",
                         [col("direction", "Direction"), col("guarantor_id", "Guarantor", "id"), col("guarantor", "Guarantor name"),
                          col("guaranteed_id", "Guaranteed", "id"), col("guaranteed", "Guaranteed name"), col("facility_id", "Facility", "id"),
                          col("amount", "Guarantee value", "sar_mn"), col("basis", "Guarantor is"), col("guarantor_band", "Guarantor EWS band", "ews_band")],
                         gu["rows"]),
                   table("people", "Owners and directors shared across the companies drawn",
                         [col("person_id", "Person", "id"), col("name", "Name"), col("roles", "Roles")], a["people"]["rows"])]
        note = ("Group, supplier, customer, guarantor, shared-collateral and shared owner or director links at the quarter. "
                "Suppliers and customers are the names in the bank's book; the rest of a borrower's purchases and sales are with "
                "names the bank does not lend to. Guarantees are the book's own Corporate Guarantee collateral.")
    else:
        hh, emp = a["household"], a["employer"]
        summary = [fig("Household members", hh["members"] or 1, "int"), fig("Household EAD", hh["exposure"], "sar_mn"),
                   fig("Household members in Early Warning", hh["in_early_warning"], "int"),
                   fig("Employer", emp["employer"]["name"] if emp["employer"] else "None recorded"),
                   fig("Colleagues in the retail book", emp.get("colleagues"), "int") if emp["employer"] else fig("Colleagues", None, "int")]
        tables = [table("household", "Household", [col("customer_id", "Customer", "id"), col("role", "Role"), col("exposure", "EAD", "sar_mn"),
                                                   col("ecl", "ECL", "sar_mn"), col("rating", "Behaviour band", "rating"),
                                                   col("ews_band", "EWS band", "ews_band")], hh["rows"])]
        if emp["employer"]:
            e = emp["employer"]
            tables.append(table("employer", "Employer", [col("borrower_id", "Borrower", "id"), col("name", "Name"), col("sector", "Sector"),
                                                         col("exposure", "EAD", "sar_mn"), col("rating", "Rating", "rating"),
                                                         col("ews_band", "EWS band", "ews_band")], [e]))
        note = "Households are customers living together; the employer is the corporate borrower that employs a salaried customer."
    return {"summary": summary, "series": [], "graph": g, "tables": tables, "note": note,
            "meta": {"legend": g["legend"], "limit": a.get("group", {}).get("policy")}}


def _tab_relationship(ctx: Ctx) -> dict[str, Any]:
    e = ctx.b["exp"]
    g = e.groupby(ctx.K, sort=True).agg(product=("product", "first"), sub_product=("sub_product", "first"),
                                        secured_flag=("secured_flag", "first"),
                                        origination_month=("origination_month", "first"),
                                        first_month=(ctx.P, "min"), last_month=(ctx.P, "max"),
                                        months=(ctx.P, "count")).reset_index()
    now = ctx.exp.set_index(ctx.K)
    g["on_book"] = g[ctx.K].isin(now.index).astype(int)
    g["ead_now"] = g[ctx.K].map(now["ead_sar_mn"]) if not now.empty else None
    g["stage_now"] = g[ctx.K].map(now["stage"]) if not now.empty else None
    g["dpd_now"] = g[ctx.K].map(now["dpd_days"]) if not now.empty else None
    cols = [col("account_id", "Account", "id"), col("product", "Product"), col("sub_product", "Sub-product"),
            col("secured_flag", "Secured", "flag"), col("origination_month", "Originated", "period"),
            col("first_month", "First seen", "period"), col("last_month", "Last seen", "period"),
            col("months", "Months observed", "int"), col("on_book", f"On book at {ctx.period}", "flag"),
            col("ead_now", f"EAD at {ctx.period}", "sar_mn"), col("stage_now", "Stage", "int"),
            col("dpd_now", "DPD", "days")]
    mix = ctx.exp.groupby("product").agg(accounts=(ctx.K, "count"), ead=("ead_sar_mn", "sum"),
                                         ecl=("ecl_sar_mn", "sum")).reset_index().sort_values("ead", ascending=False)
    summary = [fig("Accounts ever held", len(g), "int"), fig(f"On book at {ctx.period}", int(g["on_book"].sum()), "int"),
               fig("Products held now", len(mix), "int"), fig("Accounts held (book)", ctx.owner.get("accounts_held"), "int"),
               fig("Tenure (months)", ctx.owner.get("tenure_months"), "int")]
    return {"summary": summary, "series": [],
            "tables": [table("accounts", "Every account this customer has held", cols, g),
                       table("products", f"Products held at {ctx.period}",
                             [col("product", "Product"), col("accounts", "Accounts", "int"), col("ead", "EAD", "sar_mn"),
                              col("ecl", "ECL", "sar_mn")], mix)],
            "note": "Retail relationships are the customer's own products and accounts; the book publishes no "
                    "household or guarantor links."}


# ------------------------------------------------------------------ early warning

def _tab_ews(ctx: Ctx) -> dict[str, Any]:
    rules = rule_meta(ctx.domain_id)
    labels = _by_label(ctx.domain_id)
    cur_rows, fired_rows = [], []
    for r in records(ctx.ews.sort_values(["ews_score", ctx.K], ascending=[False, True])):
        fired = set(_reasons(r.get("ews_reasons")))
        for rule in rules:
            hit = rule["label"] in fired
            cur_rows.append({"exposure_id": r[ctx.K], "exposure_score": r.get("ews_score"),
                             "exposure_band": r.get("ews_band"), "rule_id": rule["id"], "rule": rule["label"],
                             "source": rule["source_label"], "condition": rule["condition"],
                             "value_read": _value_read(r, rule["inputs"]), "weight": rule["weight"],
                             "fired": int(hit), "points": rule["weight"] if hit else 0})
    for r in records(ctx.b["ews"]):
        for lab in _reasons(r.get("ews_reasons")):
            rule = labels.get(lab)
            fired_rows.append({"period": r[ctx.P], "exposure_id": r[ctx.K], "rule_id": rule["id"] if rule else "",
                               "rule": lab, "source": rule["source_label"] if rule else "",
                               "value_read": _value_read(r, rule["inputs"]) if rule else "",
                               "weight": rule["weight"] if rule else None,
                               "exposure_score": r.get("ews_score"), "exposure_band": r.get("ews_band")})
    fired_rows.sort(key=lambda x: (x["period"], x["exposure_id"], x["rule_id"]))
    series = ctx.series
    now = next((p for p in series if p["period"] == ctx.period), {})
    fired_now = sorted({x["rule_id"] for x in cur_rows if x["fired"]})
    mod, high, crit = ews.BAND_FLOORS[ctx.domain_id]
    summary = [fig("EWS score", now.get("score"), "int"), fig("EWS band", now.get("band"), "ews_band"),
               fig("Rules fired", len(fired_now), "int"), fig("Bank internal", now.get("bank_internal"), "int"),
               fig("Bureau", now.get("bureau"), "int"), fig("Open Banking", now.get("open_banking"), "int"),
               fig("Rule set", ews.RULESET_VERSION)]
    exp_scores = [{"exposure_id": r[ctx.K], "score": r.get("ews_score"), "band": r.get("ews_band"),
                   "reasons": r.get("ews_reasons") or ""}
                  for r in records(ctx.ews.sort_values(["ews_score", ctx.K], ascending=[False, True]))]
    return {
        "summary": summary, "series": series,
        "meta": {"band_floors": {"moderate": mod, "high": high, "critical": crit}, "ruleset": ews.RULESET_VERSION,
                 "release": ctx.s["ews_release"], "rules": list(rules)},
        "tables": [
            table("history", "Score and band, every period (highest exposure score, banded)",
                  [col("period", "Period", "period"), col("score", "Score", "int"), col("band", "Band", "ews_band"),
                   col("exposures", ctx.s["exposures_label"].capitalize(), "int"),
                   col("rules_fired", "Rules fired", "int"), col("bank_internal", "Bank internal", "int"),
                   col("bureau", "Bureau", "int"), col("open_banking", "Open Banking", "int"),
                   col("reasons", "Rules fired (labels)")], series),
            table("exposures", f"{ctx.s['exposures_label'].capitalize()} scores at {ctx.period}",
                  [col("exposure_id", ctx.s["exposure_label"].capitalize(), "id"), col("score", "Score", "int"),
                   col("band", "Band", "ews_band"), col("reasons", "Rules fired")], exp_scores),
            table("evaluated", f"Every rule evaluated at {ctx.period}, with the value read",
                  [col("exposure_id", ctx.s["exposure_label"].capitalize(), "id"), col("rule_id", "Rule", "id"),
                   col("rule", "Signal"), col("source", "Source"), col("condition", "Condition", "code"),
                   col("value_read", "Value read", "code"), col("weight", "Weight", "int"),
                   col("fired", "Fired", "flag"), col("points", "Points", "int")], cur_rows),
            table("fired", "Every rule fired, every period",
                  [col("period", "Period", "period"), col("exposure_id", ctx.s["exposure_label"].capitalize(), "id"),
                   col("rule_id", "Rule", "id"), col("rule", "Signal"), col("source", "Source"),
                   col("value_read", "Value read", "code"), col("weight", "Weight", "int"),
                   col("exposure_score", "Exposure score", "int"), col("exposure_band", "Exposure band", "ews_band")],
                  fired_rows),
            table("rules", f"Rule set {ews.RULESET_VERSION} ({ctx.domain_id})",
                  [col("id", "Rule", "id"), col("label", "Signal"), col("source_label", "Source"),
                   col("condition", "Condition", "code"), col("weight", "Weight", "int"), col("layer", "Layer")],
                  list(rules)),
        ],
        "note": (f"Scores, bands and the rules fired are read from the Early Warning release {ctx.s['ews_release']} "
                 f"(rule set {ews.RULESET_VERSION}). A {ctx.s['owner_label']}'s score is its highest "
                 f"{ctx.s['exposure_label']} score; bands from {mod} (moderate), {high} (high), {crit} (critical)."),
    }


# ------------------------------------------------------------------ bureau & open banking

EXT_LABELS = {
    "bureau_score": "Bureau score", "external_dpd_days": "External DPD", "worst_external_status": "Worst external status",
    "external_facilities": "External facilities", "external_balance_sar_mn": "External balance",
    "external_leverage_x": "Debt-burden ratio", "enquiries_3m": "Enquiries (3 months)",
    "new_external_default": "New external default", "external_exposure_sar_mn": "External exposure",
    "external_default_flag": "In default elsewhere", "enquiries_q": "Enquiries (quarter)",
    "external_first_flag": "External-first marker (generator)", "salaried_flag": "Salaried",
    "salary_credit_flag": "Salary credit", "salary_interruption_flag": "Salary missing",
    "total_inflows_sar_k": "Inflows", "inflow_trend_pct": "Inflow trend", "balance_buffer_months": "Balance buffer",
    "returned_payments_3m": "Returned payments (3 months)", "gambling_bnpl_spend_share_pct": "Gambling/BNPL spend share",
    "operating_inflows_sar_mn": "Operating inflows", "returned_payments_q": "Returned payments (quarter)",
}


def _external(ctx: Ctx, name: str, manifest_key: str, title: str) -> dict[str, Any]:
    frame = ctx.b[name].rename(columns={ctx.P: "period"}).sort_values("period")
    m = manifest(manifest_key)
    dictionary = m.get("dictionary", {})
    fields = [c for c in frame.columns if c not in ("tenant_id", ctx.s["owner"], "period")]

    def unit(c: str) -> str:
        u = (dictionary.get(c) or {}).get("unit", "")
        t = (dictionary.get(c) or {}).get("type", "")
        return {"SAR million": "sar_mn", "SAR thousand": "sar_k", "%": "pct", "days": "days", "months": "months",
                "x": "x", "count": "int", "points": "int"}.get(u, "flag" if t == "flag" else "text")

    labels = {c: EXT_LABELS.get(c) or c.replace("_sar_mn", "").replace("_sar_k", "").replace("_pct", "")
              .replace("_", " ").capitalize() for c in fields}
    cols = [col("period", "Period", "period")] + [col(c, labels[c], unit(c)) for c in fields]
    cur = frame[frame["period"] == ctx.period]
    cur = cur.iloc[0].to_dict() if not cur.empty else {}
    summary = [fig(labels[c], cur.get(c), unit(c)) for c in fields if c != "external_first_flag"]
    src = "bureau" if manifest_key == "bureau" else "open_banking"
    fired_now = {lab for r in ctx.ews["ews_reasons"] for lab in _reasons(r)} if not ctx.ews.empty else set()
    rules = [{**{k: r[k] for k in ("id", "label", "condition", "weight")},
              "fired_now": int(r["label"] in fired_now)} for r in rule_meta(ctx.domain_id) if r["source"] == src]
    dict_rows = [{"column": c, "label": labels[c], "unit": (dictionary.get(c) or {}).get("unit", ""),
                  "description": (dictionary.get(c) or {}).get("description", "")} for c in fields]
    return {"summary": summary, "series": records(frame[["period"] + fields]),
            "meta": {"release": m.get("release_id"), "domain_label": m.get("domain_label")},
            "tables": [table("history", f"{title}, every period", cols, frame),
                       table("rules", f"Early Warning rules that read {title} (fired at {ctx.period}?)",
                             [col("id", "Rule", "id"), col("label", "Signal"), col("condition", "Condition", "code"),
                              col("weight", "Weight", "int"), col("fired_now", "Fired now", "flag")], rules),
                       table("dictionary", f"{title} dictionary ({m.get('release_id')})",
                             [col("column", "Column", "code"), col("label", "Label"), col("unit", "Unit"),
                              col("description", "Meaning")], dict_rows)],
            "note": f"{m.get('domain_label')} · release {m.get('release_id')}"}


def _tab_bureau(ctx: Ctx) -> dict[str, Any]:
    return _external(ctx, "bureau", "bureau", "Bureau")


def _tab_open_banking(ctx: Ctx) -> dict[str, Any]:
    return _external(ctx, "ob", "open_banking", "Open Banking")


# ------------------------------------------------------------------ notes

def _tab_notes(ctx: Ctx) -> dict[str, Any]:
    items = demo_notes.derive(ctx.domain_id, ctx.owner_id, ctx.b, ctx.series, ctx.period)
    cols = [col("period", "Period", "period"), col("date", "Date", "text"), col("kind", "Kind"),
            col("title", "Title"), col("text", "Note"), col("source", "Derived from", "code")]
    return {"summary": [fig("Notes", len(items), "int")], "series": [],
            "tables": [table("notes", "Notes (derived from the book's facts, newest first)", cols, items),
                       table("documents", "Documents", [col("text", "")],
                             [{"text": "No documents are held. v5 publishes no credit files, statements or "
                                       "agreements; nothing here is a real document."}])],
            "note": ("Each note is generated deterministically from a fact in the releases "
                     "(watchlist entry, rating change, covenant breach, stage or DPD movement, Early Warning band "
                     "change, external signals). No person wrote them.")}


BUILDERS: dict[str, Callable[[Ctx], dict[str, Any]]] = {
    "profile": _tab_profile, "facilities": _tab_facilities, "exposure": _tab_exposure, "ratings": _tab_ratings,
    "stage-dpd": _tab_stage_dpd, "collateral": _tab_collateral, "covenants": _tab_covenants,
    "financials": _tab_financials, "group": _tab_group, "relationships": _tab_relationships, "ews": _tab_ews, "bureau": _tab_bureau,
    "open-banking": _tab_open_banking, "notes": _tab_notes,
}


def tab(domain_id: str, owner_id: str, period: str, key: str, ctx: Ctx | None = None) -> dict[str, Any]:
    spec(domain_id)
    if key not in tab_keys(domain_id):
        raise NotFound(f"{key!r} is not a Borrower 360 tab for {domain_id}; tabs are {tab_keys(domain_id)}.")
    ctx = ctx or Ctx(domain_id, owner_id, period)
    out = {"summary": [], "series": [], "tables": [], "note": "", "meta": {}}
    out.update(BUILDERS[key](ctx))
    out.update({"key": key, "label": dict(TABS[domain_id])[key], "period": ctx.period})
    return clean(out)


def customer(domain_id: str, owner_id: str, period: str = "") -> dict[str, Any]:
    ctx = Ctx(domain_id, owner_id, period)
    return {"profile": ctx.profile,
            "tab_list": [{"key": k, "label": lab} for k, lab in TABS[domain_id]],
            "tabs": {k: tab(domain_id, owner_id, ctx.period, k, ctx) for k in tab_keys(domain_id)},
            "links": links(domain_id, owner_id, ctx.period)}


def links(domain_id: str, owner_id: str, period: str) -> dict[str, str]:
    from urllib.parse import urlencode
    return {"early_warning": "/early-warning?" + urlencode({"domain": domain_id, "customer": owner_id, "period": period}),
            "borrower_360": "/borrower-360?" + urlencode({"domain": domain_id, "customer_id": owner_id,
                                                          "period": period})}


# ------------------------------------------------------------------ search

def search(domain_id: str, q: str = "", period: str = "", limit: int = 25) -> dict[str, Any]:
    s = spec(domain_id)
    periods = book_periods(domain_id)
    period = period if period in periods else periods[-1]
    q = (q or "").strip()
    limit = max(1, min(int(limit or 25), 200))
    like = f"%{q.lower()}%"
    if domain_id == "corporate":
        base = """
          WITH f AS (SELECT borrower_id, COUNT(*) AS facilities, SUM(ead_sar_mn) AS exposure
                     FROM corp_facility WHERE reporting_quarter = ? GROUP BY 1),
               e AS (SELECT borrower_id, MAX(ews_score) AS score FROM ews_corp WHERE reporting_quarter = ? GROUP BY 1),
               b AS (SELECT borrower_id AS id, borrower_name AS name, sector AS segment, sub_sector AS subsegment,
                            rating_current AS rating, group_id, f.facilities, f.exposure, e.score
                     FROM corp_borrower JOIN f USING (borrower_id) LEFT JOIN e USING (borrower_id)
                     WHERE reporting_quarter = ?)"""
        params: list[Any] = [period, period, period]
        if q:
            where = """WHERE lower(id) LIKE ? OR lower(name) LIKE ? OR lower(group_id) = ?
                          OR id IN (SELECT borrower_id FROM corp_facility WHERE reporting_quarter = ?
                                    AND lower(facility_id) = ?)"""
            wparams: list[Any] = [like, like, q.lower(), period, q.lower()]
        else:
            where, wparams = "", []
    else:
        base = """
          WITH f AS (SELECT customer_id, COUNT(*) AS facilities, SUM(ead_sar_mn) AS exposure,
                            string_agg(DISTINCT product, ', ' ORDER BY product) AS products
                     FROM ret_account WHERE reporting_month = ? GROUP BY 1),
               e AS (SELECT customer_id, MAX(ews_score) AS score FROM ews_ret WHERE reporting_month = ? GROUP BY 1),
               b AS (SELECT customer_id AS id, NULL AS name, customer_segment AS segment, f.products AS subsegment,
                            score_band AS rating, NULL AS group_id, f.facilities, f.exposure, e.score
                     FROM ret_customer JOIN f USING (customer_id) LEFT JOIN e USING (customer_id)
                     WHERE reporting_month = ?)"""
        params = [period, period, period]
        if q:
            where = """WHERE lower(id) LIKE ? OR id IN (SELECT customer_id FROM ret_account
                                                       WHERE reporting_month = ? AND lower(account_id) LIKE ?)"""
            wparams = [like, period, like]
        else:
            where, wparams = "", []
    total = rows(f"{base} SELECT COUNT(*) AS n FROM b {where}", params + wparams)[0]["n"]
    found = rows(f"""{base} SELECT * FROM b {where}
                    ORDER BY (lower(id) = ?) DESC, score DESC NULLS LAST, exposure DESC NULLS LAST, id LIMIT ?""",
                 params + wparams + [q.lower(), limit])
    for r in found:
        r["band"] = ews.band_of(domain_id, r.get("score"))
    return clean({"domain_id": domain_id, "period": period, "q": q, "matched": total, "returned": len(found),
                  "ranked": not q, "order": "Early Warning score, highest first; then exposure",
                  "results": found, "labels": {"owner": s["owner_label"], "exposures": s["exposures_label"]}})
