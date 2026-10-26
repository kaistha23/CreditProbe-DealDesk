"""The metric catalogue and the dimensions a lens can use (PLAN_R5 L1.3 "Add ratio", L2).

Every metric is a SQL aggregate over one of the lens relations; nothing is a stored figure.

  corp   one row per corporate facility-quarter: the book (corp_facility_quarter) as the Early Warning
         release carries it (ews score, band, reasons), with branch, business unit, RM and current
         rating (EWS `enriched`), and the borrower's financials (corp_borrower_quarter: DSCR, leverage)
  ret    one row per retail account-month: the book (retail_account_month) with EWS, behaviour and branch
  sc     the scorecard domain's scored observations (SME-ANN for corporate, RET-BEH for retail)
  dd     the Deal Desk proposals and their results (dd_proposal x dd_result, view 'ask')

Kinds:
  sum       SUM(expr)                         additive, can carry a filter (custom ratios)
  distinct  COUNT(DISTINCT owner)             additive, can carry a filter
  wavg      EAD-weighted mean of expr
  ratio     num / den x scale (num, den: additive metric keys)
  scorecard an aggregate over `sc` for the obligors in scope
  dealdesk  an aggregate over the Deal Desk proposals in scope (sector, region)
  cor       cost of risk, trailing twelve months, in bps: sum over the last 12 months (4 quarters) of
            (ECL build of the exposures in scope + new write-offs) / average EAD over the same window.
            Annual by construction (no x4 / x12 multiplier on one period); flows are attributed exposure by
            exposure, so a scope or a segment that exposures move in and out of is not charged for the move
            (R13 L: the 1,812 bps on Makkah retail cards was one month's ECL build x 12 over month-end EAD).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.v5common import ratings

WARNED = "ews_band IN ('moderate','high','critical')"
SEVERE = "ews_band IN ('high','critical')"


@dataclass
class Metric:
    key: str
    label: str
    unit: str
    kind: str
    expr: str = ""
    cond: str = ""
    num: str = ""
    den: str = ""
    scale: float = 1.0
    books: tuple[str, ...] = ("corporate", "retail")
    source: str = "Books"
    description: str = ""
    better: str = "lower"         # which direction is good (colours the change)
    group: str = "Exposure"

    def public(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "unit": self.unit, "kind": self.kind, "books": list(self.books),
                "source": self.source, "description": self.description, "group": self.group, "better": self.better}


def _m(*a: Any, **k: Any) -> Metric:
    return Metric(*a, **k)


METRICS: dict[str, Metric] = {m.key: m for m in [
    # ---- exposure and loss (the books)
    _m("ead", "EAD", "sar_mn", "sum", "ead_sar_mn", description="Exposure at default", better="none"),
    _m("ecl", "ECL", "sar_mn", "sum", "ecl_sar_mn", description="Recognised expected credit loss", group="Loss"),
    _m("limit", "Limit", "sar_mn", "sum", "limit_sar_mn", description="Approved limits", better="none"),
    _m("drawn", "Drawn", "sar_mn", "sum", "drawn", description="Drawn balance (corporate drawn, retail balance)", better="none"),
    _m("coverage", "ECL coverage", "pct", "ratio", num="ecl", den="ead", scale=100, description="ECL / EAD", group="Loss"),
    _m("utilisation", "Limit utilisation", "pct", "ratio", num="drawn", den="limit", scale=100, description="Drawn / limit", better="none"),
    _m("stage2_ead", "Stage 2 EAD", "sar_mn", "sum", "ead_sar_mn", cond="stage = 2", group="Staging"),
    _m("stage3_ead", "Stage 3 EAD", "sar_mn", "sum", "ead_sar_mn", cond="stage = 3", group="Staging"),
    _m("stage2_share", "Stage 2 share", "pct", "ratio", num="stage2_ead", den="ead", scale=100, group="Staging"),
    _m("stage3_share", "Stage 3 share", "pct", "ratio", num="stage3_ead", den="ead", scale=100, group="Staging"),
    _m("npl_ratio", "NPL ratio", "pct", "ratio", num="stage3_ead", den="ead", scale=100,
       description="Non-performing (Stage 3) EAD / EAD", group="Staging"),
    _m("dpd30_ead", "30+ DPD EAD", "sar_mn", "sum", "ead_sar_mn", cond="dpd_days >= 30", group="Delinquency"),
    _m("dpd30_share", "30+ DPD share", "pct", "ratio", num="dpd30_ead", den="ead", scale=100, group="Delinquency"),
    _m("dpd90_ead", "90+ DPD EAD", "sar_mn", "sum", "ead_sar_mn", cond="dpd_days >= 90", group="Delinquency"),
    _m("dpd90_share", "90+ DPD share", "pct", "ratio", num="dpd90_ead", den="ead", scale=100, group="Delinquency"),
    _m("write_offs", "Write-offs", "sar_mn", "sum", "new_write_off_sar_mn", group="Loss",
       description="New write-offs in the period (a balance written off is counted once, in the period it is first written off)"),
    _m("cost_of_risk", "Cost of risk (12m)", "bps", "cor", group="Loss",
       description="Trailing 12 months: (ECL build + new write-offs) / average EAD, in bps"),
    _m("pd", "Average PD (12m, performing)", "pct", "wavg", "pd_pit_12m", cond="stage < 3", scale=100,
       description="EAD-weighted 12-month PD of the performing book (Stage 1 and 2; defaulted exposures carry PD 100%)",
       group="Risk parameters"),
    _m("lgd", "Average LGD", "pct", "wavg", "lgd_pct", description="EAD-weighted LGD", group="Risk parameters"),
    _m("ltv", "Average LTV", "pct", "wavg", "collateral_ltv_pct", description="EAD-weighted collateral LTV", group="Collateral"),
    _m("obligors", "Obligors", "count", "distinct", better="none", description="Borrowers (corporate) or customers (retail)"),
    _m("exposures", "Exposures", "count", "sum", "1", better="none", description="Facilities (corporate) or accounts (retail)"),
    # ---- Early Warning
    _m("warned", "Warned obligors", "count", "distinct", cond=WARNED, source="Early Warning", group="Early Warning"),
    _m("high_critical", "High or critical", "count", "distinct", cond=SEVERE, source="Early Warning", group="Early Warning"),
    _m("warned_ead", "Warned EAD", "sar_mn", "sum", "ead_sar_mn", cond=WARNED, source="Early Warning", group="Early Warning"),
    _m("high_critical_ead", "High/critical EAD", "sar_mn", "sum", "ead_sar_mn", cond=SEVERE, source="Early Warning", group="Early Warning"),
    _m("warned_share", "Warned share of obligors", "pct", "ratio", num="warned", den="obligors", scale=100, source="Early Warning", group="Early Warning"),
    _m("severe_ead_share", "High/critical share of EAD", "pct", "ratio", num="high_critical_ead", den="ead", scale=100,
       source="Early Warning", group="Early Warning"),
    # ---- corporate only
    _m("dscr", "Average DSCR", "ratio", "wavg", "dscr_x", books=("corporate",), description="EAD-weighted debt service cover", group="Financials", better="higher"),
    _m("leverage", "Average leverage", "ratio", "wavg", "leverage_x", books=("corporate",), description="EAD-weighted debt / EBITDA", group="Financials"),
    _m("watchlist", "On watchlist", "count", "distinct", cond="watchlist_flag = 1", books=("corporate",), group="Early Warning"),
    _m("downgraded", "Downgraded this quarter", "count", "distinct", cond="rating_notches_moved > 0", books=("corporate",), group="Ratings"),
    _m("covenant_breaches", "Covenant breaches", "count", "sum", "COALESCE(covenant_breaches, 0)", books=("corporate",), group="Covenants"),
    # ---- retail only
    _m("behaviour_score", "Average behaviour score", "score", "wavg", "behaviour_score", books=("retail",), group="Behaviour", better="higher"),
    _m("missed_payments", "Accounts with a missed payment (12m)", "count", "sum", "1", cond="missed_payments_12m > 0", books=("retail",), group="Behaviour"),
    # ---- What-If (Delta method: ECL moves with PD)
    _m("ecl_pd20", "ECL at PD +20% (What-If, Delta)", "sar_mn", "sum", "ecl_sar_mn * CASE WHEN stage < 3 THEN 1.2 ELSE 1 END", source="What-If",
       description="What-If Delta method: ECL scales with PD in Stages 1 and 2; Stage 3 is defaulted (PD 100%) and does not move",
       group="What-If"),
    _m("ecl_pd20_uplift", "ECL uplift at PD +20% (What-If)", "sar_mn", "sum", "CASE WHEN stage < 3 THEN ecl_sar_mn * 0.2 ELSE 0 END",
       source="What-If", group="What-If", description="PD +20% on the performing book (Stage 3 does not move)"),
    # ---- Scorecard Validation domain
    _m("sc_score", "Scorecard average score", "score", "scorecard", "AVG(s.score)", source="Scorecard", group="Scorecard", better="higher",
       description="SME-ANN (corporate) or RET-BEH (retail) score of the obligors in scope"),
    _m("sc_pd_model", "Scorecard model PD", "pct", "scorecard", "AVG(s.pd_model) * 100", source="Scorecard", group="Scorecard"),
    _m("sc_bad_rate", "Scorecard 12m bad rate (matured)", "pct", "scorecard", "AVG(CASE WHEN s.matured THEN s.y12 END) * 100", source="Scorecard", group="Scorecard"),
    # ---- Deal Desk
    _m("dd_pipeline", "Deal Desk proposals", "count", "dealdesk", "COUNT(*)", books=("corporate",), source="Deal Desk", group="Deal Desk", better="none"),
    _m("dd_ask_sar_mn", "Deal Desk amount asked", "sar_mn", "dealdesk", "SUM(p.amount_sar_mn)", books=("corporate",), source="Deal Desk", group="Deal Desk", better="none"),
    _m("dd_raroc", "Deal Desk average RAROC (ask)", "pct", "dealdesk", "AVG(r.lifetime_raroc_pct)", books=("corporate",), source="Deal Desk", group="Deal Desk", better="higher"),
    _m("dd_below_hurdle", "Proposals below hurdle", "count", "dealdesk", "SUM(CASE WHEN r.lifetime_raroc_pct < r.hurdle_pct THEN 1 ELSE 0 END)",
       books=("corporate",), source="Deal Desk", group="Deal Desk"),
]}


@dataclass
class Dim:
    key: str
    label: str
    books: tuple[str, ...]
    expr: str = ""
    order: str = "value"          # value | rating | natural | band | stage
    child: str = ""               # the next level down

    @property
    def sql(self) -> str:
        return self.expr or self.key


BAND_ORDER = ("critical", "high", "moderate", "low", "none")
DIMS: dict[str, Dim] = {d.key: d for d in [
    Dim("sector", "Sector", ("corporate",), child="sub_sector"),
    Dim("sub_sector", "Sub-sector", ("corporate",)),
    Dim("region", "Region", ("corporate", "retail"), child="branch_name"),
    Dim("branch_name", "Branch", ("corporate", "retail"), child="rm_name"),
    Dim("business_unit", "Business unit", ("corporate",), child="rm_name"),
    Dim("rm_name", "Relationship manager", ("corporate",)),
    Dim("rating_current", "Rating", ("corporate",), order="rating"),
    Dim("relationship_tier", "Relationship tier", ("corporate",)),
    Dim("product_type", "Facility type", ("corporate",)),
    Dim("stage", "Stage", ("corporate", "retail"), expr="'Stage ' || CAST(stage AS VARCHAR)", order="natural"),
    Dim("ews_band", "Early Warning band", ("corporate", "retail"), order="band"),
    Dim("product", "Product", ("retail",), child="sub_product"),
    Dim("sub_product", "Sub-product", ("retail",)),
    Dim("customer_segment", "Customer segment", ("retail",)),
    Dim("employment_type", "Employment type", ("retail",)),
    Dim("delinquency_bucket", "Delinquency bucket", ("retail",), order="natural"),
    Dim("score_band", "Behaviour score band", ("retail",), order="natural"),
    Dim("vintage_year", "Vintage", ("retail",), expr="CAST(vintage_year AS VARCHAR)", order="natural"),
    Dim("origination_channel", "Origination channel", ("retail",)),
]}

#: Numeric columns a distribution tile can show, with their unit and bins.
DISTRIBUTIONS: dict[str, dict[str, Any]] = {
    "dscr_x": {"label": "DSCR", "unit": "ratio", "books": ("corporate",), "edges": [0, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]},
    "leverage_x": {"label": "Leverage (debt / EBITDA)", "unit": "ratio", "books": ("corporate",), "edges": [0, 1, 2, 3, 4, 5, 6, 8]},
    "collateral_ltv_pct": {"label": "LTV", "unit": "pct", "books": ("corporate", "retail"), "edges": [0, 40, 60, 80, 100, 120, 150]},
    "utilisation_pct": {"label": "Utilisation", "unit": "pct", "books": ("corporate", "retail"), "edges": [0, 25, 50, 75, 90, 100, 120]},
    "pd_pit_12m": {"label": "12-month PD", "unit": "pct", "books": ("corporate", "retail"), "scale": 100, "edges": [0, 0.5, 1, 2, 5, 10, 20, 100]},
    "dpd_days": {"label": "Days past due", "unit": "days", "books": ("corporate", "retail"), "edges": [0, 1, 30, 60, 90, 180]},
    "behaviour_score": {"label": "Behaviour score", "unit": "score", "books": ("retail",), "edges": [0, 450, 500, 550, 600, 650, 700, 1000]},
    "lgd_pct": {"label": "LGD", "unit": "pct", "books": ("corporate", "retail"), "edges": [0, 10, 20, 30, 45, 60, 100]},
    # R16 M5 (analyst lens: model inputs): EAD per facility (corporate) or account (retail), SAR m
    "ead_sar_mn": {"label": "EAD per exposure (SAR m)", "unit": "sar_mn", "books": ("corporate", "retail"),
                   "edges": [0, 0.05, 0.25, 1, 2.5, 5, 10, 15, 25]},
}


def metrics_for(book: str) -> list[Metric]:
    return [m for m in METRICS.values() if book in m.books]


def dims_for(book: str) -> list[Dim]:
    return [d for d in DIMS.values() if book in d.books]


def order_sql(dim: Dim, col: str = "k") -> str:
    if dim.order == "rating":
        return ratings.sql_rank(col)
    if dim.order == "band":
        return "CASE " + col + " " + " ".join(f"WHEN '{b}' THEN {i}" for i, b in enumerate(BAND_ORDER)) + " ELSE 9 END"
    if dim.order == "natural":
        return col
    return ""


def public(book: str) -> dict[str, Any]:
    return {"metrics": [m.public() for m in metrics_for(book)],
            "dimensions": [{"key": d.key, "label": d.label} for d in dims_for(book)],
            "distributions": [{"key": k, "label": v["label"], "unit": v["unit"]} for k, v in DISTRIBUTIONS.items() if book in v["books"]]}


@dataclass
class CustomRatio:
    """A ratio a user builds: numerator / denominator (additive metrics), the numerator optionally filtered."""
    label: str
    num: str
    den: str
    filters: list[dict[str, Any]] = field(default_factory=list)
    scale: float = 100.0
    unit: str = "pct"
