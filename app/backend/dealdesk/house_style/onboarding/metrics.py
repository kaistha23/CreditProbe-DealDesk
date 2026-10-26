"""P6: the metric library: what a credit policy clause can set, how to recognise it, and where it goes.

Each metric says
  - how a clause names it (`kw`, a regex on the whole clause) and which quantity it takes (`unit`);
  - which way is stricter (`stricter`: "lower" or "higher"), so a proposed value is compared with the parameter in force
    and with the regulation the same way whatever the clause's wording;
  - its target: a rule in Session R's `rules.json` schema (`rule`) and/or a Deal Desk parameter (`param`:
    `risk_appetite` / `doa` / `market_bounds` / `desk`);
  - the data fields that check it and whether the bank's data can (`auto`) or a person must (`manual`, with the reason);
  - the CBUAE CRM article it answers to (`reg`), when the Standards state a number.

A clause quantity no metric claims is still extracted, as an unmapped threshold for a person to configure.
"""
from __future__ import annotations

from typing import Any

from backend.v5common.ratings import RATING_ORDER

BUCKETS = {"IG": RATING_ORDER[:RATING_ORDER.index("BBB-") + 1],
           "BB": ["BB+", "BB", "BB-"], "B": ["B+", "B", "B-"], "CCC-C": ["CCC", "CC", "C"]}


def ratings_at_or_above(r: str) -> list[str]:
    return list(RATING_ORDER[:RATING_ORDER.index(r) + 1]) if r in RATING_ORDER else []


def _bucket_expr(values: dict[str, float], var: str = "rating") -> str:
    """'10 if rating in [...] else (7 if ... else None)' for a value per rating bucket."""
    out = "None"
    for b in reversed(list(values)):
        out = f"({values[b]!r} if {var} in {BUCKETS[b]!r} else {out})"
    return out


# CBUAE CRM numbers the policy is compared with (article, value, unit, what it says).
REG = {
    "review_months": ("CBUAE CRM Art. 4.3", 12, "months", "every wholesale obligor reviewed, and its rating updated, every year"),
    "review_months_sub": ("CBUAE CRM Art. 11.3", 12, "months", "ratings of all facilities and obligors reviewed at least yearly"),
    "dpd_stage2": ("CBUAE CRM Art. 7.8", 30, "days", "more than 30 days past due is a SICR (Stage 2)"),
    "dpd_default": ("CBUAE CRM Art. 6.4", 90, "days", "more than 90 days past due on a material obligation is default (Stage 3)"),
    "restructure_count": ("CBUAE CRM Art. 9.29", 3, "times", "restructured 3 or more times in financial difficulty: Stage 3"),
    "moratorium_months": ("CBUAE CRM Art. 9.31", 6, "months", "non-distressed restructuring with a moratorium over 6 months: Stage 2"),
    "write_off_years": ("CBUAE CRM Art. 12.5", 5, "years", "no Stage 3 exposure held more than 5 years after migration"),
    "valuation_months_stage3": ("CBUAE CRM Art. 10.11", 12, "months", "Stage 3 real estate valued within the last 12 months"),
    "board_reapproval_years": ("CBUAE CRM Art. 2.6", 3, "years", "material facilities approved by the Board at least every three years"),
    "board_material_pct": ("CBUAE CRM Art. 2.6", 10, "%", "material facilities include any exposure above 10% of Tier 1 capital"),
}
#: the words of the Standards each comparison quotes (must be found in the policy pack's clause text)
REG_QUOTE = {
    "review_months": "The CCO is required to review Obligors and associated exposures every year.",
    "review_months_sub": "The rating of all Credit Facilities and Obligors must be reviewed at least on a yearly cycle.",
    "dpd_stage2": "Credit Facilities with Repayments more than 30 Days-Past-Due must be identified as deteriorating assets and therefore subject to SICR.",
    "dpd_default": "The Obligor is Past Due for a period greater than 90 days on any material credit obligation to the LFI.",
    "restructure_count": "Any Credit Facility that has been restructured 3 times or more in a context of financial difficulty",
    "moratorium_months": "All non-distressed Restructured Credit Facilities with a Repayment moratorium exceeding 6 months must be classified as Stage 2",
    "write_off_years": "The LFI must not hold a Stage 3 exposure on the balance sheet for more than 5 years since the date of migration to Stage 3.",
    "valuation_months_stage3": "For Stage 3 Facilities, this valuation must have been performed within the last 12 months of the reporting date.",
    "board_reapproval_years": "Material Credit Facilities must be approved by the Board at least every three years.",
    "board_material_pct": "Any Facility leading to an exposure greater than 10% of the LFI’s Tier 1 Capital",
}

MANUAL_NO_REVIEW_DATE = "the books hold no review date"


def _m(key: str, label: str, kw: str, unit: str, stricter: str, **kw2: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "kw": kw, "unit": unit, "stricter": stricter, **kw2}


#: Order matters: the first metric whose keyword matches a clause claims the quantity of its unit there.
METRICS: list[dict[str, Any]] = [
    _m("board_material_pct", "Material facility threshold (share of Tier 1)", r"material facilit", "pct", "lower",
       qualifier=r"Tier 1", data=[], manual="the books hold no Tier 1 capital or approval record"),
    _m("board_reapproval_years", "Board re-approval of material facilities", r"re-?approved by the Board", "years", "lower",
       data=[], manual="the books hold no Board approval record"),
    _m("submission_days", "Application before expiry", r"before the expiry", "days", "higher",
       data=[], manual="the books hold no submission dates"),
    _m("audited_years", "Years of audited financial statements", r"audited financial statements", "count", "higher",
       data=["fin.<year>.kind"], auto_note="years of actuals in the financial spreading",
       rule={"inputs": {"fin": "fin"}, "derive": {"n": "len([y for y in fin if not contains(y, '_p')])"},
             "expr": "n", "op": ">=", "scope": ["dd"], "unit": "years",
             "finding": "{n} years of audited financial statements against the policy's {threshold:,.0f}.",
             "pass_text": "{n} years of audited financial statements analysed."}),
    _m("mgmt_accounts_months", "Age of management accounts", r"management accounts", "months", "lower",
       data=[], manual="the spreading carries no management-accounts date"),
    _m("bureau_days", "Age of the bureau report", r"bureau report", "days", "lower",
       data=["ev.sources.bureau"], manual="the bureau extract date is text in the evidence register, not a field"),
    _m("min_rating", "Minimum rating for new money", r"rated below|minimum rating", "rating", "higher",
       param={"table": "risk_appetite", "row": "min_rating", "field": "new_to_bank"},
       data=["subject.rating"],
       rule={"inputs": {"rating": "subject.rating"}, "assert_fn": "rating_floor",
             "finding": "Rating {rating} is below the policy floor {threshold} for new money.",
             "pass_text": "Rating {rating} meets the policy floor."}),
    _m("dscr", "DSCR after the deal", r"debt service coverage|\bDSCR\b", "x", "higher",
       param={"table": "risk_appetite", "row": "dscr", "field": "limit"}, data=["metrics.dscr_post"],
       rule={"inputs": {"dscr": "metrics.dscr_post"}, "expr": "dscr", "op": ">=", "unit": "x",
             "finding": "DSCR after the deal {dscr:,.2f}x against the policy minimum {threshold:,.2f}x.",
             "pass_text": "DSCR after the deal {dscr:,.2f}x meets the policy minimum."}),
    _m("debt_ebitda", "Debt/EBITDA after the deal", r"debt to EBITDA|debt/EBITDA|leverage", "x", "lower",
       param={"table": "risk_appetite", "row": "debt_ebitda", "field": "limit"}, data=["metrics.debt_ebitda_post"],
       rule={"inputs": {"lev": "metrics.debt_ebitda_post"}, "expr": "lev", "op": "<=", "unit": "x",
             "finding": "Debt/EBITDA after the deal {lev:,.2f}x against the policy maximum {threshold:,.2f}x.",
             "pass_text": "Debt/EBITDA after the deal {lev:,.2f}x within the policy maximum."}),
    _m("current_ratio", "Current ratio", r"current ratio", "x", "higher", data=["fin_last.current_ratio"],
       rule={"inputs": {"cr": "fin_last.current_ratio"}, "expr": "cr", "op": ">=", "unit": "x", "scope": ["dd"],
             "finding": "Current ratio {cr:,.2f}x against the policy minimum {threshold:,.2f}x.",
             "pass_text": "Current ratio {cr:,.2f}x meets the policy minimum."}),
    _m("balloon", "Balloon share", r"balloon|bullet repayment", "pct", "lower",
       param={"table": "risk_appetite", "row": "balloon", "field": "limit", "scale": 0.01}, data=["ask.balloon_pct"],
       rule={"inputs": {"b": "ask.balloon_pct"}, "expr": "b", "op": "<=", "unit": "%", "scope": ["dd"],
             "finding": "Balloon {b:,.0f}% against the policy maximum {threshold:,.0f}%.",
             "pass_text": "Balloon {b:,.0f}% within the policy maximum."}),
    _m("customer_concentration", "Single-customer share of revenue", r"single customer", "pct", "lower",
       data=[], manual="the spreading holds no revenue by customer"),
    _m("backlog_cover", "Backlog cover (contractors)", r"order backlog|backlog", "times", "lower",
       param={"table": "desk", "row": "max_backlog_cover", "field": "value"},
       data=["case.financials.backlog", "case.financials.revenue"],
       rule={"inputs": {"backlog": "case.financials.backlog", "revenue": "case.financials.revenue"}, "scope": ["case"],
             "expr": "backlog / revenue", "op": "<=", "unit": "x",
             "finding": "Backlog {value:,.1f}x revenue against the policy maximum {threshold:,.1f}x.",
             "pass_text": "Backlog {value:,.1f}x revenue within the policy maximum."}),
    _m("large_exposure_tier1", "Connected counterparties (share of Tier 1)", r"connected counterparties", "pct", "lower",
       param={"table": "risk_appetite", "row": "group_large_exposure", "field": "limit_pct_tier1", "scale": 0.01},
       data=[], manual="the books hold no Tier 1 capital"),
    _m("single_obligor", "Single obligor limit", r"single obligor", "money", "lower",
       param={"table": "risk_appetite", "row": "single_name", "field": "limit", "ccy": "SAR"},
       data=["subject.amount_sar", "obligor.existing_exposure_sar_mn"],
       rule={"inputs": {"amt": "subject.amount_sar", "ex": "obligor.existing_exposure_sar_mn"}, "optional": ["ex"],
             "derive": {"after": "amt + (ex or 0)"}, "expr": "after", "op": "<=", "unit": "SAR m", "ccy": "SAR",
             "finding": "Obligor exposure after the deal SAR {after:,.1f}m against the policy limit SAR {threshold:,.1f}m.",
             "pass_text": "Obligor exposure after the deal SAR {after:,.1f}m within the policy limit."}),
    _m("group_limit", "Connected group limit", r"group of connected obligors|connected group", "money", "lower",
       param={"table": "risk_appetite", "row": "group_connected", "field": "limit", "ccy": "SAR"},
       data=["case.group_cap.group_exposure_after"],
       rule={"inputs": {"after": "case.group_cap.group_exposure_after"}, "scope": ["case"], "expr": "after", "op": "<=",
             "unit": "AED m", "ccy": "AED",
             "finding": "Group exposure after the deal AED {after:,.1f}m against the policy limit AED {threshold:,.1f}m.",
             "pass_text": "Group exposure after the deal AED {after:,.1f}m within the policy limit."}),
    _m("re_construction_share", "Real estate and construction share of the book", r"real estate and construction", "pct",
       "lower", param={"table": "risk_appetite", "row": "re_construction_share", "field": "limit", "scale": 0.01},
       data=["corporate book: sector, EAD"], auto_note="book-level: the pipeline and risk-appetite engine measure it"),
    _m("sector_share", "Single sector share of the book", r"economic sector|single sector", "pct", "lower",
       param={"table": "risk_appetite", "row": "sector_policy", "field": "limit", "scale": 0.01},
       data=["corporate book: sector, EAD"], auto_note="book-level: the pipeline and risk-appetite engine measure it"),
    _m("max_tenor", "Maximum tenor by rating bucket", r"maximum tenor", "table_years", "lower",
       param={"table": "risk_appetite", "row": "max_tenor", "field": "limits"}, data=["ask.tenor_years", "subject.rating"],
       rule={"inputs": {"tenor": "ask.tenor_years", "rating": "subject.rating"}, "scope": ["dd"], "bucket_rule": True,
             "unit": "years", "finding": "Tenor {tenor:,.0f} years against the policy maximum {cap} years for rating {rating}.",
             "pass_text": "Tenor {tenor:,.0f} years within the policy maximum for rating {rating}."}),
    _m("wc_tenor_months", "Working capital tenor", r"working capital facilit", "months", "lower",
       param={"table": "desk", "row": "tenor_cap_years", "field": "Working capital", "scale": 1 / 12},
       data=["ask.facility_type", "ask.tenor_years"], auto_note="the loan origination record carries the facility type and tenor"),
    _m("ltv", "Loan to value (income-producing real estate)", r"loan-to-value|loan to value|\bLTV\b", "pct", "lower",
       param={"table": "risk_appetite", "row": "ltv", "field": "limit", "scale": 0.01},
       data=["subject.amount_sar", "collateral[].type", "collateral[].value"],
       rule={"inputs": {"amt": "subject.amount_sar", "coll": "collateral"}, "scope": ["dd"],
             "when": "any([contains(c['type'], 'real') for c in coll])",
             "derive": {"re": "sum([c['value'] for c in coll if contains(c['type'], 'real')])"},
             "expr": "100 * amt / re", "op": "<=", "unit": "%",
             "finding": "Loan to value {value:,.0f}% against the policy maximum {threshold:,.0f}%.",
             "pass_text": "Loan to value {value:,.0f}% within the policy maximum."}),
    _m("cash_margin", "Cash margin on contractor guarantees", r"cash margin", "pct", "higher",
       same_as="EXC-01", data=["ev.security.cash_margin_pct"],
       rule={"inputs": {"cm": "ev.security.cash_margin_pct"}, "scope": ["case"], "expr": "cm", "op": ">=", "unit": "%",
             "finding": "Cash margin {cm:,.0f}% on the guarantees against the policy minimum {threshold:,.0f}%.",
             "pass_text": "Cash margin {cm:,.0f}% meets the policy minimum."}),
    _m("valuation_months_stage3", "Stage 3 collateral valuation age", r"revalued", "months", "lower",
       qualifier=r"Stage 3", data=["collateral[].valuation_date", "corporate book: stage"],
       auto_note="valuation dates in the collateral register; Stage 3 from the corporate book"),
    _m("valuation_months", "Collateral valuation age", r"revalued", "months", "lower",
       data=["collateral[].valuation_date"],
       rule={"inputs": {"coll": "collateral"}, "scope": ["dd"],
             "derive": {"age": "max([months(c['valuation_date'], as_of) for c in coll if c.get('valuation_date')] or [0])"},
             "expr": "age", "op": "<=", "unit": "months",
             "finding": "Oldest collateral valuation {age:,.0f} months old against the policy maximum {threshold:,.0f}.",
             "pass_text": "Collateral valuations within {threshold:,.0f} months."}),
    _m("legal_opinion_months", "Legal opinion age at drawdown", r"legal opinion", "months", "lower", same_as="EXC-04",
       data=["ev.security.legal_opinion_date"],
       rule={"inputs": {"d": "ev.security.legal_opinion_date"}, "scope": ["case"], "expr": "months(d, as_of)", "op": "<=",
             "unit": "months", "finding": "Legal opinion {value:,.0f} months old against the policy maximum {threshold:,.0f}.",
             "pass_text": "Legal opinion within {threshold:,.0f} months."}),
    _m("perfection_deferral_days", "Deferral of security perfection", r"perfect", "days", "lower",
       data=["ev.security.corporate_guarantee_perfection"],
       manual="the security register records whether security is perfected, not the length of a deferral"),
    _m("collateral_cover", "Collateral cover after haircuts", r"collateral cover", "pct", "higher",
       data=["collateral[].value"], manual="the collateral register holds values but not the policy's haircuts"),
    _m("review_months_sub", "Review frequency (B+ or worse)", r"reviewed at least every", "months", "lower",
       qualifier=r"or worse", data=[], manual=MANUAL_NO_REVIEW_DATE),
    _m("review_months", "Review frequency", r"reviewed at least every", "months", "lower", data=[], manual=MANUAL_NO_REVIEW_DATE),
    _m("covenant_cert_days", "Covenant certificate submission", r"compliance certificate", "days", "lower",
       data=[], manual="the books hold no certificate submission dates"),
    _m("dpd_stage2", "Days past due to Stage 2", r"Stage 2", "days", "lower", qualifier=r"past due",
       data=["corporate book: dpd_days, stage"], auto_note="the CBUAE CRM checks read days past due and stage from the book"),
    _m("dpd_default", "Days past due to Stage 3", r"Stage 3", "days", "lower", qualifier=r"past due",
       data=["corporate book: dpd_days, stage"], auto_note="the CBUAE CRM checks read days past due and stage from the book"),
    _m("restructure_count", "Restructurings to Stage 3", r"restructured", "count", "lower", data=[],
       manual="the books flag a restructuring, not how many"),
    _m("moratorium_months", "Moratorium to Stage 2", r"moratorium", "months", "lower", data=[],
       manual="the books hold no moratorium period"),
    _m("write_off_years", "Stage 3 write-off period", r"written off", "years", "lower",
       data=["corporate book: stage history"], auto_note="months in Stage 3 from the stage history (CBUAE CRM check CRM-12.5)"),
    _m("raroc_floor", "Lifetime RAROC floor", r"\bRAROC\b", "pct", "higher",
       param={"table": "risk_appetite", "row": "raroc_floor", "field": "limit", "scale": 0.01},
       data=["metrics.lifetime_raroc"],
       rule={"inputs": {"raroc": "metrics.lifetime_raroc"}, "expr": "100 * raroc", "op": ">=", "unit": "%",
             "finding": "Lifetime RAROC {value:,.1f}% against the policy floor {threshold:,.1f}%.",
             "pass_text": "Lifetime RAROC {value:,.1f}% clears the policy floor."}),
    _m("margin_bounds", "Margin bounds by rating bucket", r"margin bounds|margins? shall be within", "table_bps", "higher",
       param={"table": "market_bounds", "row": "by_bucket", "field": "margin_bps"}, data=["ask.margin_bps", "subject.rating"],
       rule={"inputs": {"m": "ask.margin_bps", "rating": "subject.rating"}, "scope": ["dd"], "bucket_rule": True,
             "unit": "bps", "finding": "Margin {m:,.0f} bps outside the policy bounds {lo}–{hi} bps for rating {rating}.",
             "pass_text": "Margin {m:,.0f} bps within the policy bounds for rating {rating}."}),
    _m("doa", "Delegation of Authority", r"Delegation of Authority|approval authority by aggregate", "table_doa", "lower",
       param={"table": "doa", "row": "rows", "field": "max_exposure", "ccy": "SAR"}, data=["subject.amount_sar", "subject.rating"],
       auto_note="the Deal Desk derives the approval level from exposure after the deal and rating"),
]
BY_KEY = {m["key"]: m for m in METRICS}

#: Condition clauses (no number) that become rules: (key, label, regex, rule, same_as)
CONDITIONS: list[dict[str, Any]] = [
    {"key": "approved_auditor", "label": "Auditor on the approved list", "kw": r"approved list", "same_as": "GOV-03",
     "data": ["ev.governance.auditor", "approved_auditors"],
     "rule": {"inputs": {"aud": "ev.governance.auditor", "lst": "approved_auditors"}, "scope": ["case"], "assert": "aud in lst",
              "finding": "Auditor {aud} is not on the approved list.", "pass_text": "Auditor {aud} is on the approved list."}},
    {"key": "perfection_before_drawdown", "label": "Security perfected before drawdown", "kw": r"perfected before the first drawdown",
     "same_as": "EXC-03", "data": ["ev.security.corporate_guarantee_perfection"],
     "rule": {"inputs": {"perf": "ev.security.corporate_guarantee_perfection"}, "scope": ["case"], "assert": "perf == 'perfected'",
              "finding": "Security is {perf}, not perfected before drawdown.", "pass_text": "Security perfected before drawdown."}},
    {"key": "guarantee_format", "label": "Guarantees dated and in the bank's format", "kw": r"expiry date and follow",
     "same_as": "EXC-02", "data": ["ev.security.guarantee_expiry", "ev.security.guarantee_format"],
     "rule": {"inputs": {"exp": "ev.security.guarantee_expiry", "fmt": "ev.security.guarantee_format"}, "scope": ["case"],
              "assert": "exp != 'open-ended' and fmt == 'bank'",
              "finding": "Guarantees {exp}, in the {fmt} format.", "pass_text": "Guarantees dated, in the bank's format."}},
    {"key": "conflict_declared", "label": "Approver conflicts declared", "kw": r"holds an interest", "data": ["ev.connected.staff_interest"],
     "rule": {"inputs": {"si": "ev.connected.staff_interest"}, "scope": ["case"], "assert": "len(si) == 0",
              "finding": "{si} approver interest(s) recorded.", "pass_text": "No approver interest recorded."}},
    {"key": "cp_before_drawdown", "label": "Conditions precedent evidenced before drawdown", "kw": r"conditions precedent are satisfied",
     "data": [], "manual": "conditions are tracked in the Deal Desk conditions tracker; evidence is attached by a person"},
]
