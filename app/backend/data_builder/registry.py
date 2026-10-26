"""The Data Builder registry: every v5 data domain and its relations, in one dict.

A new domain is ONE entry in `DOMAINS`. A relation names its parquet file
(relative to the v5 checkout, and always under `data/`), its book, its key
columns and its period column; the data dictionary is read from the manifest
it names (`manifest` + `manifest_kind`) and topped up from `CURATED`, and
anything still undocumented is described from its name (marked "derived").

The service reads these files read-only and opens nothing else.
"""
from __future__ import annotations

from typing import Any

_CORP = "data/cockpit_v4_lake/v4-saudi-corporate-20q-v4"
_RET = "data/cockpit_v4_lake/v4-saudi-retail-20m-v5"
_EWS_C = "data/ews/ews-saudi-corporate-20q-v4e2"
_EWS_R = "data/ews/ews-saudi-retail-20m-v5e1"
_EWS_M = "data/ews/EWS_PACKAGE_MANIFEST.json"
_BUR = "data/external/bureau-saudi-v1"
_OB = "data/external/open-banking-saudi-v1"
_DD = "data/dealdesk/dd-saudi-v1"

Q = "reporting_quarter"
M = "reporting_month"


def _rel(path: str, book: str, label: str, keys: list[str], period: str | None,
         description: str = "", manifest: str | None = None, manifest_kind: str | None = None,
         grain: str = "", fields: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    return {"path": path, "book": book, "label": label, "key_columns": keys, "period_column": period,
            "description": description, "manifest": manifest, "manifest_kind": manifest_kind, "grain": grain,
            "fields": fields or {}}


#: Group-level meaning of the amounts in the published series and reason tables.
_SERIES = {
    "ead_sar_mn": {"description": "Total exposure at default of the exposures in this group.",
                   "unit": "SAR million"},
    "ecl_sar_mn": {"description": "Total expected credit loss of the exposures in this group.",
                   "unit": "SAR million"},
}


#: domain id -> {label, status ("live" | "coming"), description, release_ids, relations{id: spec}}
DOMAINS: dict[str, dict[str, Any]] = {
    "cockpit": {
        "label": "Cockpit books",
        "status": "live",
        "description": "The two credit books the Cockpit reads: Saudi corporate (20 quarters) "
                       "and Saudi retail (20 months).",
        "relations": {
            "corp_borrower_quarter": _rel(f"{_CORP}/corp_borrower_quarter.parquet", "corporate",
                                          "Borrowers by quarter", ["borrower_id", Q], Q,
                                          manifest=f"{_CORP}/manifest.json", manifest_kind="cockpit"),
            "corp_facility_quarter": _rel(f"{_CORP}/corp_facility_quarter.parquet", "corporate",
                                          "Facilities by quarter", ["facility_id", Q], Q,
                                          manifest=f"{_CORP}/manifest.json", manifest_kind="cockpit"),
            "corp_collateral_quarter": _rel(f"{_CORP}/corp_collateral_quarter.parquet", "corporate",
                                            "Collateral by quarter", ["collateral_id", Q], Q,
                                            manifest=f"{_CORP}/manifest.json", manifest_kind="cockpit"),
            "corp_covenant_quarter": _rel(f"{_CORP}/corp_covenant_quarter.parquet", "corporate",
                                          "Covenants by quarter", ["covenant_id", Q], Q,
                                          manifest=f"{_CORP}/manifest.json", manifest_kind="cockpit"),
            "retail_customer_month": _rel(f"{_RET}/retail_customer_month.parquet", "retail",
                                          "Customers by month", ["customer_id", M], M,
                                          manifest=f"{_RET}/manifest.json", manifest_kind="cockpit"),
            "retail_account_month": _rel(f"{_RET}/retail_account_month.parquet", "retail",
                                         "Accounts by month", ["account_id", M], M,
                                         manifest=f"{_RET}/manifest.json", manifest_kind="cockpit"),
            "retail_behaviour_month": _rel(f"{_RET}/retail_behaviour_month.parquet", "retail",
                                           "Account behaviour by month", ["account_id", M], M,
                                           manifest=f"{_RET}/manifest.json", manifest_kind="cockpit"),
            "retail_collateral_month": _rel(f"{_RET}/retail_collateral_month.parquet", "retail",
                                            "Collateral by month", ["account_id", M], M,
                                            manifest=f"{_RET}/manifest.json", manifest_kind="cockpit"),
        },
    },
    "ews": {
        "label": "Early Warning",
        "status": "live",
        "description": "The Early Warning service's own releases: every exposure scored and banded by the "
                       "rule set, the owners, the supporting tables and the published series.",
        "relations": {
            "corp_exposure": _rel(f"{_EWS_C}/ews_corp_exposure.parquet", "corporate",
                                  "Corporate exposures, scored", ["facility_id", Q], Q,
                                  "Every corporate facility by quarter with its Early Warning score, band and "
                                  "reasons, and the bureau and open-banking signals it was scored on.",
                                  _EWS_M, "ews", "one row per facility per quarter"),
            "corp_owner": _rel(f"{_EWS_C}/ews_corp_owner.parquet", "corporate", "Corporate borrowers",
                               ["borrower_id", Q], Q, "The corporate borrowers the exposures belong to.",
                               _EWS_M, "ews", "one row per borrower per quarter"),
            "corp_collateral": _rel(f"{_EWS_C}/ews_corp_collateral.parquet", "corporate", "Corporate collateral",
                                    ["collateral_id", Q], Q, "Collateral carried onto the Early Warning release.",
                                    _EWS_M, "ews", "one row per collateral item per quarter"),
            "corp_covenant": _rel(f"{_EWS_C}/ews_corp_covenant.parquet", "corporate", "Corporate covenants",
                                  ["covenant_id", Q], Q, "Covenant tests carried onto the Early Warning release.",
                                  _EWS_M, "ews", "one row per covenant per quarter"),
            "corp_series_portfolio": _rel(f"{_EWS_C}/ews_series_portfolio.parquet", "corporate",
                                          "Corporate series: portfolio by band", [Q, "ews_band"], Q,
                                          "Published portfolio series: counts and exposure by band.",
                                          _EWS_M, "ews", fields=_SERIES),
            "corp_series_segment": _rel(f"{_EWS_C}/ews_series_segment.parquet", "corporate",
                                        "Corporate series: sector by band", [Q, "sector", "ews_band"], Q,
                                        "Published series by sector and band.", _EWS_M, "ews", fields=_SERIES),
            "corp_series_subsegment": _rel(f"{_EWS_C}/ews_series_subsegment.parquet", "corporate",
                                           "Corporate series: sub-sector by band",
                                           [Q, "sector", "sub_sector", "ews_band"], Q,
                                           "Published series by sector, sub-sector and band.", _EWS_M, "ews",
                                           fields=_SERIES),
            "corp_reason_period": _rel(f"{_EWS_C}/ews_reason_period.parquet", "corporate",
                                       "Corporate reasons by quarter", [Q, "reason"], Q,
                                       "How often each Early Warning reason fired, and on how much exposure.",
                                       _EWS_M, "ews", fields=_SERIES),
            "retail_exposure": _rel(f"{_EWS_R}/ews_retail_exposure.parquet", "retail",
                                    "Retail accounts, scored", ["account_id", M], M,
                                    "Every retail account by month with its Early Warning score, band and reasons, "
                                    "and the bureau and open-banking signals it was scored on.",
                                    _EWS_M, "ews", "one row per account per month"),
            "retail_owner": _rel(f"{_EWS_R}/ews_retail_owner.parquet", "retail", "Retail customers",
                                 ["customer_id", M], M, "The retail customers the accounts belong to.",
                                 _EWS_M, "ews", "one row per customer per month"),
            "retail_behaviour": _rel(f"{_EWS_R}/ews_retail_behaviour.parquet", "retail", "Retail behaviour",
                                     ["account_id", M], M, "Account behaviour carried onto the Early Warning release.",
                                     _EWS_M, "ews", "one row per account per month"),
            "retail_collateral": _rel(f"{_EWS_R}/ews_retail_collateral.parquet", "retail", "Retail collateral",
                                      ["account_id", M], M, "Collateral carried onto the Early Warning release.",
                                      _EWS_M, "ews", "one row per secured account per month"),
            "retail_series_portfolio": _rel(f"{_EWS_R}/ews_series_portfolio.parquet", "retail",
                                            "Retail series: portfolio by band", [M, "ews_band"], M,
                                            "Published portfolio series: counts and exposure by band.",
                                            _EWS_M, "ews", fields=_SERIES),
            "retail_series_segment": _rel(f"{_EWS_R}/ews_series_segment.parquet", "retail",
                                          "Retail series: product by band", [M, "product", "ews_band"], M,
                                          "Published series by product and band.", _EWS_M, "ews", fields=_SERIES),
            "retail_series_subsegment": _rel(f"{_EWS_R}/ews_series_subsegment.parquet", "retail",
                                             "Retail series: sub-product by band",
                                             [M, "product", "sub_product", "ews_band"], M,
                                             "Published series by product, sub-product and band.", _EWS_M, "ews",
                                             fields=_SERIES),
            "retail_reason_period": _rel(f"{_EWS_R}/ews_reason_period.parquet", "retail",
                                         "Retail reasons by month", [M, "reason"], M,
                                         "How often each Early Warning reason fired, and on how much exposure.",
                                         _EWS_M, "ews", fields=_SERIES),
        },
    },
    "bureau": {
        "label": "Bureau",
        "status": "live",
        "description": "SIMAH-style bureau signals, keyed to the books' customers and borrowers.",
        "relations": {
            "bureau_retail_month": _rel(f"{_BUR}/bureau_retail_month.parquet", "retail", "Retail bureau by month",
                                        ["customer_id", M], M, "Bureau view of each retail customer, by month.",
                                        f"{_BUR}/manifest.json", "external", "one row per customer per month"),
            "bureau_corp_quarter": _rel(f"{_BUR}/bureau_corp_quarter.parquet", "corporate",
                                        "Corporate bureau by quarter", ["borrower_id", Q], Q,
                                        "Bureau view of each corporate borrower, by quarter.",
                                        f"{_BUR}/manifest.json", "external", "one row per borrower per quarter"),
        },
    },
    "open_banking": {
        "label": "Open Banking",
        "status": "live",
        "description": "Open-banking account signals (inflows, buffers, returned payments), keyed to "
                       "the books' customers and borrowers.",
        "relations": {
            "openbanking_retail_month": _rel(f"{_OB}/openbanking_retail_month.parquet", "retail",
                                             "Retail open banking by month", ["customer_id", M], M,
                                             "Open-banking view of each retail customer, by month.",
                                             f"{_OB}/manifest.json", "external", "one row per customer per month"),
            "openbanking_corp_quarter": _rel(f"{_OB}/openbanking_corp_quarter.parquet", "corporate",
                                             "Corporate open banking by quarter", ["borrower_id", Q], Q,
                                             "Open-banking view of each corporate borrower, by quarter.",
                                             f"{_OB}/manifest.json", "external", "one row per borrower per quarter"),
        },
    },
    "deal_desk": {
        "label": "Deal Desk",
        "status": "live",
        "description": "Pre-deal credit proposals (existing borrowers keyed to the corporate book, new-to-bank names "
                       "with their own DN ids), their facility lines, financials, security, the versioned parameter "
                       "tables, the portfolio headroom the limits are measured against, and the priced results "
                       "(ask and recommended structure). Credit memos (.docx) stay as files in data/dealdesk/memos.",
        "relations": {
            name: _rel(f"{_DD}/{name}.parquet", "corporate", label, keys, Q, desc, f"{_DD}/manifest.json", "external", grain)
            for name, label, keys, desc, grain in (
                ("dd_proposal", "Credit proposals", ["proposal_id", Q],
                 "One row per proposal: obligor, new-to-bank or existing, ask terms and status.", "one row per proposal"),
                ("dd_proposal_facility", "Proposal facility lines", ["proposal_id", "line_id", Q],
                 "The proposed funded and unfunded lines, and the book facilities of existing borrowers.",
                 "one row per proposal facility line"),
                ("dd_obligor_financials", "Obligor financials", ["proposal_id", "year", Q],
                 "Three actual years and three projections per proposal.", "one row per proposal and financial year"),
                ("dd_collateral_guarantee", "Collateral and guarantees", ["proposal_id", "item_id", Q],
                 "Collateral items and guarantees offered in the ask or available.", "one row per item"),
                ("dd_parameter", "Parameter tables", ["table_name", "param_key", Q],
                 "Every Deal Desk parameter table flattened, with its owner, version and effective date.",
                 "one row per parameter value"),
                ("dd_portfolio_snapshot", "Portfolio snapshot and headroom", ["dimension", "dimension_key", Q],
                 "The corporate book at the as-of quarter by sector, rating bucket, collateral type and connected "
                 "group, with limits and headroom.", "one row per limit dimension and key"),
                ("dd_result", "Priced results", ["proposal_id", "view", Q],
                 "The last priced result per proposal for the ask and the recommended structure: PD, LGD, EAD, EL, "
                 "RWA, capital, RAROC, SVA, approval level and decision.", "one row per proposal and view"),
            )
        },
    },
    "borrower_360": {
        "label": "Borrower 360",
        "status": "coming",
        "description": "Arrives with the Borrower 360 module.",
        "relations": {},
    },
    "what_if": {
        "label": "What-If",
        "status": "coming",
        "description": "Arrives with the What-If module.",
        "relations": {},
    },
}

#: Definitions for columns no manifest documents (the Early Warning additions
#: and the published series). Looked up by column name, after the relation's
#: own manifest and the other domains' manifests.
CURATED: dict[str, dict[str, str]] = {
    "ews_score": {"description": "Early Warning score: the sum of the weights of the rules that fired on this "
                                 "exposure this period.", "unit": "points"},
    "ews_band": {"description": "Early Warning band from the score: critical, high, moderate or low."},
    "ews_reasons": {"description": "The Early Warning rules that fired on this exposure this period, "
                                   "separated by semicolons."},
    "ews_ruleset_version": {"description": "The Early Warning rule-set version that scored this row."},
    "ews_release_id": {"description": "The Early Warning release this row was published in."},
    "ews_grain": {"description": "The grain of this Early Warning row (for example facility_quarter)."},
    "source_release_id": {"description": "The Cockpit book release this row was derived from."},
    "source_dataset_release_id": {"description": "The dataset release of the source book row."},
    "source_table": {"description": "The Cockpit book relation this row was derived from."},
    "covenant_breaches": {"description": "Number of the facility's covenants in breach this quarter.",
                          "unit": "count"},
    "collateral_value_sar_mn": {"description": "Value of the collateral held against this exposure.",
                                "unit": "SAR million"},
    "collateral_ltv_pct": {"description": "Loan-to-value of this exposure against its collateral.", "unit": "%"},
    "customer_score_band": {"description": "The customer's behaviour score band this month (A best to E worst)."},
    "customer_score_band_previous": {"description": "The customer's behaviour score band in the previous month."},
    "customer_worst_dpd_days": {"description": "The worst days past due across the customer's accounts.",
                                "unit": "days"},
    "customer_worst_stage": {"description": "The worst IFRS 9 stage across the customer's accounts."},
    "n": {"description": "Number of exposures (facilities or accounts) in this group.", "unit": "count"},
    "owners": {"description": "Number of distinct owners (borrowers or customers) in this group.",
               "unit": "count"},
    "severe_ead_sar_mn": {"description": "Exposure at default of the exposures banded high or critical.",
                          "unit": "SAR million"},
    "reason": {"description": "The Early Warning rule (reason) that fired."},
}


# ---------------------------------------------------------------- PLAN_R4 18:58: every module's data in Data Builder
# Scorecard Validation, What-If and the branch / RM reference (B4) as live domains. Kept in one block after
# DOMAINS so each module's registration stays a separate edit.

import json as _json  # noqa: E402
import pathlib as _pathlib  # noqa: E402

_V5 = _pathlib.Path(__file__).resolve().parents[2]
_SC = "data/scorecard_v5/scorecard-saudi-v1"
_BR = "data/branches/branch-saudi-v1"
#: The What-If IFRS 9 domain: one parquet per period, rebuilt from the books by ops/whatif_build_domain.py
#: (ops/v5.sh runs it before the services start); data/whatif_v5/<book>/manifest.json holds its control totals.
_WI = "var/whatif_v5"


def _read(path: str) -> dict[str, Any]:
    try:
        return _json.loads((_V5 / path).read_text())
    except (OSError, ValueError):
        return {}


_SC_COMMON = {
    "period": {"description": "Scoring period: the month (retail) or quarter (SME) the score was taken."},
    "sample": {"description": "Development or monitoring sample the row belongs to."},
    "matured": {"description": "1 when the 12-month outcome window has closed for this row, otherwise 0.", "unit": "flag (0/1)"},
    "y12": {"description": "Outcome: 1 when the account or borrower defaulted within 12 months of the score.", "unit": "flag (0/1)"},
    "score": {"description": "Scorecard points: the sum of the points of every variable's bin plus the intercept.", "unit": "points"},
    "grade": {"description": "Score grade from the scorecard's grade cut-offs (1 best)."},
    "pd_grade": {"description": "Calibrated 12-month probability of default of the grade.", "unit": "%"},
    "pd_model": {"description": "12-month probability of default from the scorecard's logistic model.", "unit": "%"},
    "override_flag": {"description": "1 when a credit officer overrode the scorecard decision, otherwise 0.", "unit": "flag (0/1)"},
    "override_direction": {"description": "Direction of the override: up (approve a decline) or down."},
    "override_reason": {"description": "The reason the officer recorded for the override."},
    "override_level": {"description": "The authority level that approved the override."},
    "scorecard_id": {"description": "The scorecard that produced this row (RET-APP, RET-BEH or SME-ANN)."},
}


def _sc_fields(sid: str) -> dict[str, dict[str, str]]:
    spec = _read(f"{_SC}/{sid}.spec.json")
    out = dict(_SC_COMMON)
    for v in spec.get("candidates", []) + spec.get("excluded", []):
        out.setdefault(v["name"], {"description": f"{v.get('label', v['name'])}: a candidate characteristic, not in the final scorecard.",
                                   "label": v.get("label", "")})
    out.setdefault("revenue_growth_pct", {"description": "Year-on-year revenue growth of the borrower.", "unit": "%"})
    for v in spec.get("variables", []):
        out[v["name"]] = {"description": f"{v.get('label', v['name'])}: a characteristic of this scorecard (IV {v.get('iv', 0):.2f}).",
                          "label": v.get("label", "")}
        out[f"bin_{v['name']}"] = {"description": f"The bin of {v.get('label', v['name'])} this row falls in (its WoE and points come from the scorecard).",
                                   "label": f"Bin: {v.get('label', v['name'])}"}
    return out


def _wi_fields() -> dict[str, dict[str, str]]:
    out = {
        "period": {"description": "Reporting period of the exposure (quarter for corporate, month for retail)."},
        "exposure_id": {"description": "The facility (corporate) or account (retail) of the book."},
        "owner_id": {"description": "The borrower (corporate) or customer (retail) of the book."},
        "owner_name": {"description": "Name of the borrower or customer."},
        "ead": {"description": "Exposure at default used by the What-If engine.", "unit": "SAR million"},
        "ecl_book": {"description": "ECL recorded in the book for this exposure and period.", "unit": "SAR million"},
        "ecl_final": {"description": "ECL the What-If engine recomputes from its inputs; reconciles to the book.", "unit": "SAR million"},
        "ecl_reconciliation_diff": {"description": "ecl_final minus ecl_book.", "unit": "SAR million"},
        "collateral_value": {"description": "Value of the collateral held against the exposure.", "unit": "SAR million"},
        "collateral_allocated": {"description": "Collateral value allocated to this exposure after the haircut.", "unit": "SAR million"},
        "haircut_pct": {"description": "Haircut applied to the collateral value.", "unit": "%"},
        "secured_share": {"description": "Share of the exposure covered by allocated collateral.", "unit": "%"},
        "limit": {"description": "Approved limit.", "unit": "SAR million"},
        "drawn": {"description": "Drawn balance.", "unit": "SAR million"},
        "undrawn": {"description": "Undrawn commitment.", "unit": "SAR million"},
        "ccf": {"description": "Credit conversion factor applied to the undrawn amount.", "unit": "%"},
        "pd_ttc": {"description": "Through-the-cycle probability of default of the grade.", "unit": "%"},
        "rho": {"description": "Asset correlation used to condition the PD on the cycle (Vasicek)."},
        "cycle_a": {"description": "Cycle index of the period that conditions PD and LGD."},
        "term_k": {"description": "Remaining term in years used for the lifetime ECL.", "unit": "years"},
        "segment": {"description": "Sector (corporate) or product (retail) of the exposure."},
        "subsegment": {"description": "Sub-sector (corporate) or sub-product (retail) of the exposure."},
        "dpd": {"description": "Days past due at the period end.", "unit": "days"},
        "grade": {"description": "Rating grade (corporate) or behaviour grade (retail) at the period end."},
        "grade_rank": {"description": "Position of the grade in the global rating order (1 is AAA)."},
        "nfo": {"description": "1 for a non-funded (off-balance-sheet) facility such as a guarantee, otherwise 0.", "unit": "flag (0/1)"},
        "application_score": {"description": "Application score at origination (retail).", "unit": "points"},
        "lgd_pct_book": {"description": "LGD recorded in the book.", "unit": "%"},
        "pd12_book": {"description": "12-month PD recorded in the book.", "unit": "%"},
        "pdlt_book": {"description": "Lifetime PD recorded in the book.", "unit": "%"},
        "ecl12_book": {"description": "12-month ECL recorded in the book.", "unit": "SAR million"},
        "ecllt_book": {"description": "Lifetime ECL recorded in the book.", "unit": "SAR million"},
        "lgd_cal_y1": {"description": "Calibrated LGD for year 1, before the scenario overlay.", "unit": "%"},
        "lgd_cal_y2_5": {"description": "Calibrated LGD for years 2 to 5, before the scenario overlay.", "unit": "%"},
        "pd_12m": {"description": "Scenario-weighted 12-month PD.", "unit": "%"},
        "ecl_12m": {"description": "Scenario-weighted 12-month ECL.", "unit": "SAR million"},
        "ecl_lifetime": {"description": "Scenario-weighted lifetime ECL.", "unit": "SAR million"},
        "ecl_weighted": {"description": "Scenario-weighted ECL for the exposure's stage (12-month for Stage 1, lifetime otherwise).", "unit": "SAR million"},
    }
    for sc in ("base", "upturn", "downturn", "weighted"):
        for y in range(1, 6):
            out[f"pd_{sc}_y{y}"] = {"description": f"Marginal PD in year {y} under the {sc} scenario.", "unit": "%"}
            if sc != "weighted":
                out[f"lgd_{sc}_y{y}"] = {"description": f"LGD in year {y} under the {sc} scenario.", "unit": "%"}
        if sc != "weighted":
            out[f"w_{sc}"] = {"description": f"Probability weight of the {sc} scenario.", "unit": "%"}
            out[f"ecl_{sc}"] = {"description": f"Lifetime-or-12-month ECL under the {sc} scenario.", "unit": "SAR million"}
    return out


def _br_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_BR}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


DOMAINS["scorecard"] = {
    "label": "Scorecard Validation",
    "status": "live",
    "description": "Retail application and behavioural scorecards and the SME scorecard: every scored account or "
                   "borrower, its characteristics and bins, score, grade, PD, overrides and the 12-month outcome. "
                   "Keyed to the books' customers, accounts and borrowers.",
    "relations": {
        "RET-APP": _rel(f"{_SC}/RET-APP.parquet", "retail", "Retail application scorecard",
                        ["account_id", "period"], "period", "One row per scored account per month.",
                        grain="one row per account per month", fields=_sc_fields("RET-APP")),
        "RET-BEH": _rel(f"{_SC}/RET-BEH.parquet", "retail", "Retail behavioural scorecard",
                        ["account_id", "period"], "period", "One row per scored account per month.",
                        grain="one row per account per month", fields=_sc_fields("RET-BEH")),
        "SME-ANN": _rel(f"{_SC}/SME-ANN.parquet", "corporate", "SME annual-review scorecard",
                        ["borrower_id", "period"], "period", "One row per scored SME borrower per quarter.",
                        grain="one row per borrower per quarter", fields=_sc_fields("SME-ANN")),
    },
}

# R16 M8 (session s): scorecard monitoring against the CBUAE MMSG criteria (backend/scorecard_v5/monitoring/build.py).
_SM = "data/scorecard_v5/monitoring-saudi-v1"
_SM_FIELDS = {
    "scorecard_id": {"description": "The scorecard (RET-APP, RET-BEH or SME-ANN)."},
    "criterion": {"description": "The MMSG monitoring criterion: discrimination, calibration, stability, overrides, migration, data_quality, usage."},
    "metric": {"description": "The metric (gini, ks, gini_drop_rel, gini_segment, oe_ratio, oe_grade, binomial_red, hl_p, psi, csi_max, override_rate, ...)."},
    "period": {"description": "The scoring period (month or quarter) the metric is measured on; window metrics carry the window's last period."},
    "segment": {"description": "The segment, grade, characteristic or reason the row is cut by (empty for the whole scorecard)."},
    "sample": {"description": "development, monitoring (outcome matured), open (outcome not yet matured) or window (the latest matured window)."},
    "value": {"description": "The metric's value (fractions for rates and Gini)."},
    "status": {"description": "green, amber, red or na against the stated threshold."},
    "n": {"description": "Observations behind the value."}, "defaults": {"description": "Defaults (or flagged rows) behind the value."},
    "observed": {"description": "Observed rate behind a ratio (e.g. the observed default rate)."},
    "expected": {"description": "Expected rate behind a ratio (e.g. the grade PD or the development Gini)."},
    "threshold": {"description": "The verdict rule applied."}, "note": {"description": "Window, comparison period or test detail."},
}
_SM_SC = {"scorecard_id": {"description": "The scorecard (RET-APP, RET-BEH or SME-ANN)."}}
_SM_CHAR = {**_SM_SC,
    "variable": {"description": "The characteristic's column name in the scorecard domain."}, "label": {"description": "The characteristic in words."},
    "in_model": {"description": "1 when the characteristic is in the scorecard, 0 for a candidate.", "unit": "flag (0/1)"},
    "period": {"description": "The scoring period (month or quarter)."}, "sample": {"description": "development, monitoring or open (outcome not yet matured)."},
    "csi": {"description": "Characteristic stability index against the development distribution."},
    "missing_pct": {"description": "Share of rows with the characteristic missing.", "unit": "%"},
    "unseen_pct": {"description": "Share of rows whose value falls in a bin empty at development.", "unit": "%"},
    "iv_dev": {"description": "Information value on the development sample."}, "iv_mon": {"description": "Information value on the matured monitoring sample."},
    "status": {"description": "green, amber, red or na for the CSI against its limit."}}
_SM_INV = {**_SM_SC,
    "name": {"description": "The scorecard's name."}, "version": {"description": "The scorecard's version."},
    "type": {"description": "application or behavioural scorecard."}, "book": {"description": "The book it scores (retail or corporate)."},
    "segment_col": {"description": "The column the approved scope is defined on (product or sector)."},
    "approved_segments": {"description": "The segments the scorecard is approved for (those in its development sample)."},
    "development_from": {"description": "First period of the development sample."}, "development_to": {"description": "Last period of the development sample."},
    "dev_gini": {"description": "Gini on the matured development sample."}, "validator": {"description": "The independent validator."},
    "model_owner": {"description": "The model owner."}, "data_owner": {"description": "The owner of the model's input data."},
    "override_owner": {"description": "The owner of the override policy."}, "tier": {"description": "Model risk tier (Tier 1 or Tier 2)."},
    "tier_reason": {"description": "Why the model has its tier."}, "intended_use": {"description": "What the model is approved to be used for."},
    "approved_on": {"description": "Date of approval.", "unit": "date"}, "approved_by": {"description": "The approving committee and its reference."},
    "last_full_validation": {"description": "Date of the last full independent validation.", "unit": "date"},
    "last_validation_ref": {"description": "Reference of the last full independent validation."},
    "last_validation_conclusion": {"description": "Its conclusion: fit, conditions or not_fit."},
    "validation_cycle_months": {"description": "Months between full validations for the model's tier (bank policy).", "unit": "months"},
    "monitoring_frequency": {"description": "How often the scorecard is monitored (monthly or quarterly)."}}
_SM_FIND = {
    "finding_id": {"description": "The finding's reference."}, **_SM_SC, "source_ref": {"description": "The validation or monitoring report that raised it."},
    "criterion": {"description": "The MMSG criterion it belongs to."}, "severity": {"description": "High, Medium or Low."},
    "title": {"description": "The finding in one line."}, "text": {"description": "What was found."}, "remediation": {"description": "What fixes it."},
    "raised_on": {"description": "Date the finding was raised.", "unit": "date"}, "owner": {"description": "Who owns the remediation."},
    "due_on": {"description": "Date the remediation is due.", "unit": "date"}, "status": {"description": "open, in_progress or closed."}}
_SM_SCHED = {**_SM_SC, "frequency": {"description": "Monitoring frequency (monthly or quarterly)."},
    "last_run": {"description": "Date of the last monitoring run.", "unit": "date"}, "next_run": {"description": "Date of the next monitoring run.", "unit": "date"},
    "report_to": {"description": "Where the monitoring results are reported."}, "alert_to": {"description": "Where red breaches are alerted."}}
DOMAINS["scorecard_monitoring"] = {
    "label": "Scorecard monitoring (MMSG)",
    "status": "live",
    "description": "Scorecard monitoring against the CBUAE MMSG criteria: every monitoring metric per scorecard, period and "
                   "segment with its limit and verdict, the characteristics, the model inventory (tier, owners, scope, last "
                   "validation), the findings register and the monitoring schedule. Computed from the Scorecard Validation domain.",
    "relations": {}}
DOMAINS["scorecard_monitoring"]["relations"].update({
    "sc_monitor_metric": _rel(f"{_SM}/sc_monitor_metric.parquet", "both", "Scorecard monitoring metrics (MMSG criteria)",
                              ["scorecard_id", "criterion", "metric", "period", "segment"], "period",
                              "Every monitoring metric per scorecard, criterion, period and segment, with its threshold and verdict.",
                              grain="one row per scorecard x metric x period x segment", fields=_SM_FIELDS),
    "sc_monitor_characteristic": _rel(f"{_SM}/sc_monitor_characteristic.parquet", "both", "Scorecard characteristics monitoring",
                                      ["scorecard_id", "variable", "period"], "period",
                                      "CSI, missing rate, share outside the development ranges and IV per characteristic and period.",
                                      grain="one row per scorecard x characteristic x period", fields=_SM_CHAR),
    "sc_model_inventory": _rel(f"{_SM}/sc_model_inventory.parquet", "both", "Scorecard model inventory",
                               ["scorecard_id"], "last_full_validation", "Tier, owners, intended use and scope, approval and last full independent validation (demo records).",
                               grain="one row per scorecard", fields=_SM_INV),
    "sc_findings_register": _rel(f"{_SM}/sc_findings_register.parquet", "both", "Scorecard findings register",
                                 ["finding_id"], "raised_on", "Validation and monitoring findings with severity, owner, due date and status (demo seed; runtime changes in the service store).",
                                 grain="one row per finding", fields=_SM_FIND),
    "sc_monitor_schedule": _rel(f"{_SM}/sc_monitor_schedule.parquet", "both", "Scorecard monitoring schedule",
                                ["scorecard_id"], "next_run", "Monitoring frequency, last and next run, and where the alerts go.",
                                grain="one row per scorecard", fields=_SM_SCHED),
})

DOMAINS["what_if"] = {
    "label": "What-If",
    "status": "live",
    "description": "The What-If IFRS 9 domain: every exposure with the PD, LGD, EAD and scenario inputs the engine "
                   "re-measures ECL from, per period; final ECL reconciles to the books.",
    "relations": {
        f"whatif_{b}": {**_rel(f"{_WI}/{b}/*.parquet", b, f"{'Corporate facilities' if b == 'corporate' else 'Retail accounts'}: IFRS 9 inputs",
                               ["exposure_id", "period"], "period",
                               "One row per exposure per period, with the engine's PD, LGD and ECL by scenario and year.",
                               grain="one row per exposure per period", fields=_wi_fields()),
                        "glob": True, "release": f"whatif-{b}"}
        for b in ("corporate", "retail")
    },
}

DOMAINS["branches"] = {
    "label": "Branches and RMs",
    "status": "live",
    "description": "The branch (and, for corporate, the business unit and relationship manager) of every book "
                   "customer, by period, consistent with the customer's region.",
    "relations": {
        "branch_corporate_quarter": _rel(f"{_BR}/branch_corporate_quarter.parquet", "corporate", "Borrower branch by quarter",
                                         ["borrower_id", Q], Q, "Branch, business unit and RM of each borrower.",
                                         grain="one row per borrower per quarter", fields=_br_fields()),
        "branch_retail_month": _rel(f"{_BR}/branch_retail_month.parquet", "retail", "Customer branch by month",
                                    ["customer_id", M], M, "Branch of each retail customer.",
                                    grain="one row per customer per month", fields=_br_fields()),
    },
}


# PLAN_R5 A7: the Admin domain (seeded configuration snapshot; the live store moves by maker-checker changes).
_ADM = "data/admin/admin-saudi-v1"


def _adm_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_ADM}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


DOMAINS["admin"] = {
    "label": "Admin",
    "status": "live",
    "description": "The Admin console's configuration: users and their roles, teams, data access policies and their "
                   "scope, approval workflow steps, AI Studio configurations and the AI run log. Keyed to the Core "
                   "users (username) and the Branches and RMs domain (RM and branch IDs).",
    "relations": {
        name: _rel(f"{_ADM}/{name}.parquet", "both", label, keys, "snapshot", desc, grain=grain, fields=_adm_fields())
        for name, label, keys, desc, grain in [
            ("admin_users", "Users", ["username"], "One row per user: role, team, RM ID, status.", "one row per user"),
            ("admin_roles", "Roles", ["role_id"], "The six roles and the modules they open.", "one row per role"),
            ("admin_teams", "Teams", ["team_id"], "Teams and their leads.", "one row per team"),
            ("admin_policies", "Data access policies", ["policy_id"], "Books, modules, actions, masking and assignees.",
             "one row per policy"),
            ("admin_policy_scope", "Policy scope", ["policy_id", "book", "field", "value"],
             "Each value a policy allows, per book and dimension.", "one row per policy value"),
            ("admin_workflow_steps", "Approval workflow steps", ["workflow_id", "step_no"],
             "Each step of each workflow: assignee, SLA and escalation.", "one row per step"),
            ("admin_studio", "AI Studio configurations", ["module"], "Each module's assistant: model, tools, kill switch.",
             "one row per module"),
            ("admin_ai_runs", "AI runs", ["run_id"], "The seeded AI run log (Agent Operations).", "one row per run"),
        ]
    },
}


# R7 (Session C, C3): the CBUAE Credit Risk Management Standards breach checks on the books, published by
# ops/build_crm_breaches.py (backend.regulatory.crm_checks). Keyed to the corporate and retail book IDs.
_REG = "data/regulatory/cbuae-crm-v1"


def _reg_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_REG}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


DOMAINS["regulatory"] = {
    "label": "Regulatory",
    "status": "live",
    "description": "Breaches of the CBUAE Credit Risk Management Standards found on the books: one row per breach "
                   "(article, facility or account, measured vs required, EAD and ECL) and one row per check and book. "
                   "Keyed to the corporate (CF…/CB…) and retail (RA…/RC…) book IDs at their latest periods.",
    "relations": {
        "crm_breach": _rel(f"{_REG}/crm_breach.parquet", "both", "CBUAE CRM breaches", ["breach_id"], "period",
                           "One row per breach of a CBUAE CRM check.", grain="one row per breach",
                           fields=_reg_fields()),
        "crm_check": _rel(f"{_REG}/crm_check.parquet", "both", "CBUAE CRM checks", ["check_id", "book"], "period",
                          "One row per check and book: tested, breaches, status, EAD/ECL and shortfall.",
                          grain="one row per check and book", fields=_reg_fields()),
    },
}


# R9 (Session C, P4): the Accepted Risk Watch list, published by ops/build_watch.py (backend.risk_intel.watch). Keyed
# to the corporate book's borrower IDs (CB…) at its as-of quarter; the two UAE proposal cases are UAE-… (AED).
_WATCH = "data/watch/watch-v1"


def _watch_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_WATCH}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


DOMAINS["watch"] = {
    "label": "Accepted Risk Watch",
    "status": "live",
    "description": "Concerns accepted at approval, as dated watch items: one row per watched client (tier, exposure, "
                   "ECL, ECL if moved to Stage 2, the no-SICR rationale) and one row per watch item (trigger, due "
                   "date, frequency, status, critical flag, article).",
    "relations": {
        "watch_client": _rel(f"{_WATCH}/watch_client.parquet", "corporate", "Accepted Risk Watch clients", ["watch_id"],
                             "period", "One row per client on the Accepted Risk Watch.", grain="one row per client",
                             fields=_watch_fields()),
        "watch_item": _rel(f"{_WATCH}/watch_item.parquet", "corporate", "Accepted Risk Watch items", ["item_id"], "period",
                           "One row per watch item.", grain="one row per watch item", fields=_watch_fields()),
    },
}


# R9 (Session E): P7 proposal intelligence. The two prepared UAE proposals (AED), their facilities and every review
# finding (checks, information gaps, weaknesses, watch items), published by ops/build_proposals.py from
# backend.dealdesk.proposal_review at the seeded Deal Desk parameters.
_PRP = "data/proposals/proposals-uae-v1"


def _prp_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_PRP}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


DOMAINS["proposals"] = {
    "label": "Proposals",
    "status": "live",
    "description": "Credit proposals under review (P7 Proposal Intelligence): one row per proposal with its quality score, "
                   "RAROC and hurdle; one row per facility (existing and proposed limits, AED million); one row per review "
                   "finding with its CBUAE CRM article. As of the review date in the manifest.",
    "relations": {
        "proposal": _rel(f"{_PRP}/proposal.parquet", "corporate", "Proposals", ["proposal_id"], "as_of",
                         "One row per proposal under review.", grain="one row per proposal", fields=_prp_fields()),
        "proposal_facility": _rel(f"{_PRP}/proposal_facility.parquet", "corporate", "Proposal facilities", ["proposal_id", "facility"], "as_of",
                                  "One row per facility in a proposal.", grain="one row per facility", fields=_prp_fields()),
        "proposal_finding": _rel(f"{_PRP}/proposal_finding.parquet", "corporate", "Proposal review findings", ["finding_id"], "as_of",
                                 "One row per check, information gap, weakness or watch item.", grain="one row per finding",
                                 fields=_prp_fields()),
    },
}


# R9 (Session F): P7 regulatory response -- the prepared query cases and the BRF credit returns, built by
# ops/build_queries_domains.py from the corporate book and the CBUAE CRM checks (backend.queries_v5).
_QB = "data/queries_v5/queries-brf-v1"


def _qb_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_QB}/manifest.json").get("dictionary") or {}
    return {k: {"description": v} for k, v in d.items()}


DOMAINS["queries"] = {
    "label": "Queries",
    "status": "live",
    "description": "Auditor, CBUAE and internal-audit queries with their numbered questions and the drafted answers "
                   "(rule, CBUAE article, sources, period). Computed on the corporate book at its as-of quarter.",
    "relations": {
        "query_case": _rel(f"{_QB}/query_case.parquet", "corporate", "Query cases", ["case_id"], "period",
                           "One row per prepared query letter.", grain="one row per letter", fields=_qb_fields()),
        "query_answer": _rel(f"{_QB}/query_answer.parquet", "corporate", "Query answers", ["case_id", "question_no"], "period",
                             "One row per question with its drafted answer's headline, rule and article.", grain="one row per question",
                             fields=_qb_fields()),
    },
}

DOMAINS["brf"] = {
    "label": "BRF returns",
    "status": "live",
    "description": "The credit returns of the BRF studio: each return's field map (domain, dataset, filters, calculation) and its "
                   "grid at the book's as-of, whose totals equal the book.",
    "relations": {
        "brf_return": _rel(f"{_QB}/brf_return.parquet", "corporate", "BRF returns", ["return_id"], "period",
                           "One row per credit return.", grain="one row per return", fields=_qb_fields()),
        "brf_field": _rel(f"{_QB}/brf_field.parquet", "corporate", "BRF field map", ["return_id", "field_id"], "period",
                          "One row per return field and its mapping.", grain="one row per field", fields=_qb_fields()),
        "brf_line": _rel(f"{_QB}/brf_line.parquet", "corporate", "BRF return lines", ["return_id", "line_no"], "period",
                         "One row per line of each return's grid at the as-of.", grain="one row per line", fields=_qb_fields()),
    },
}

# R9 (Session A): the six shared data domains, built by ops/build_r9_data.py (backend.r9_data.build), read through
# backend.r9_data.read. Keyed to the corporate (CB…/CF…) and retail (RC…/RA…) book IDs at their as-of periods.
_R9 = "data/r9_data/r9-saudi-v1"


def _r9_fields() -> dict[str, dict[str, str]]:
    d = _read(f"{_R9}/manifest.json").get("dictionary") or {}
    return {k: ({"description": v} if isinstance(v, str) else v) for k, v in d.items()}


def _r9(name: str, label: str, keys: list[str], period: str | None, desc: str, grain: str) -> dict[str, Any]:
    return _rel(f"{_R9}/{name}.parquet", "both", label, keys, period, desc, grain=grain, fields=_r9_fields())


DOMAINS["deposits"] = {
    "label": "Deposits",
    "status": "live",
    "description": "Every obligor's deposit accounts, 24 months of balances, turnover, cheques, payroll and overdraft "
                   "use, the top 10 counterparties per month (corporate) and the derived routing, returned-cheque and "
                   "volatility measures.",
    "relations": {
        "dep_account": _r9("dep_account", "Deposit accounts", ["account_no"], "as_of_date",
                           "Type, currency, open date, status, profit rate, lien and overdraft limit.", "one row per account"),
        "dep_month": _r9("dep_month", "Deposits by month", ["obligor_id", "month"], "as_of_date",
                         "Balances, turnover, transactions, cheques, payroll, excess days.", "one row per obligor per month"),
        "dep_counterparty": _r9("dep_counterparty", "Top counterparties", ["obligor_id", "month", "rank"], "as_of_date",
                                "Top 10 counterparties per month with direction, amount and category.",
                                "one row per obligor, month and rank"),
        "dep_derived": _r9("dep_derived", "Deposit measures", ["obligor_id"], "as_of_date",
                           "Turnover to revenue, routing compliance, returned-cheque rate, balance volatility.",
                           "one row per obligor"),
    },
}
DOMAINS["origination"] = {
    "label": "Origination",
    "status": "live",
    "description": "Every facility and account at origination: date, margin, fees, rating, PD, FTP, tenor, collateral, "
                   "hurdle rate and limit.",
    "relations": {"orig_facility": _r9("orig_facility", "Facilities at origination", ["exposure_id"], "as_of_date",
                                       "Origination terms per exposure.", "one row per exposure")},
}
DOMAINS["classification"] = {
    "label": "Classification",
    "status": "live",
    "description": "IFRS 9 stage and previous stage, DPD bucket, deferrals, the CBUAE SICR and unlikeliness-to-pay "
                   "indicators with article and source, Early Warning bucket and signals, watch status and "
                   "restructuring with probation end.",
    "relations": {
        "cls_exposure": _r9("cls_exposure", "Classification by exposure", ["exposure_id"], "as_of_date",
                            "Stage, SICR/UTP flags and reasons, EWS, watch and restructuring.", "one row per exposure"),
        "cls_reason": _r9("cls_reason", "SICR and UTP reasons", ["exposure_id", "kind", "code"], "as_of_date",
                          "Each indicator present: code, text, CBUAE article and clause, source and date.",
                          "one row per exposure and reason"),
    },
}
DOMAINS["collateral"] = {
    "label": "Collateral and registers",
    "status": "live",
    "description": "Collateral items, guarantees, the restructured register, the related-party register, large "
                   "exposures by economic group and credit risk-weighted assets per exposure.",
    "relations": {
        "col_item": _r9("col_item", "Collateral items", ["collateral_id"], "as_of_date",
                        "Type, value, haircut, valuation date, registration.", "one row per collateral item"),
        "col_guarantee": _r9("col_guarantee", "Guarantees", ["guarantee_id"], "as_of_date",
                             "Guarantor, amount, perfection.", "one row per guarantee"),
        "col_restructured": _r9("col_restructured", "Restructured register", ["exposure_id"], "as_of_date",
                                "Restructure date, type, count, probation end, status.", "one row per restructured exposure"),
        "col_related_party": _r9("col_related_party", "Related-party register", ["obligor_id", "party_cif"], "as_of_date",
                                 "Parents and staff links per obligor.", "one row per obligor and party"),
        "col_large_exposure": _r9("col_large_exposure", "Large exposures", ["group_id"], "as_of_date",
                                  "Exposure by economic group against Tier 1 capital and the 25% limit.",
                                  "one row per economic group"),
        "col_crwa": _r9("col_crwa", "Credit RWA", ["exposure_id"], "as_of_date",
                        "EAD, credit risk mitigation, risk weight, CRWA.", "one row per exposure"),
    },
}
DOMAINS["relationships"] = {
    "label": "Relationships network",
    "status": "live",
    "description": "The network graph: obligors, groups and persons as nodes; group membership, guarantors, "
                   "shareholders and sponsors (nominee flags), staff links and deposit counterparties as links.",
    "relations": {
        "rel_node": _r9("rel_node", "Network nodes", ["node_id"], "as_of_date", "Obligors, groups and persons.", "one row per node"),
        "rel_link": _r9("rel_link", "Network links", ["link_id"], "as_of_date", "Typed links with share, nominee and amount.",
                        "one row per link"),
    },
}
DOMAINS["ecl_runs"] = {
    "label": "ECL runs",
    "status": "live",
    "description": "Facility-level ECL for the 2026Q2 (prior) and 2026Q3 (current) runs: EAD, PD, LGD, stage, ECL by "
                   "scenario, weighted and overlay. The current run equals the books; the input anomalies are listed.",
    "relations": {
        "ecl_facility": _r9("ecl_facility", "ECL by exposure and run", ["run_id", "exposure_id"], "run_id",
                            "Inputs and ECL per exposure per run.", "one row per exposure per run"),
        "ecl_anomaly": _r9("ecl_anomaly", "ECL input anomalies", ["anomaly_id"], "run_id",
                           "Input anomalies found in the runs, with whether a rerun is needed.", "one row per anomaly"),
    },
}


# ---------------------------------------------------------------- PLAN_R12 §0 (Session E): everything flows from Data Domains
# The R12 contract (backend/dealdesk/data/schema.py, docs/v5/R12_DATA_CONTRACT.md): new Deal Desk relations, the
# Deal Desk products domain, the Bureau additions, and Borrower 360 live (the existing rel-saudi-v1 tables plus the
# b360-saudi-v1 group, ownership, board, insider and ownership-change relations). Each relation's dictionary is its
# own column list (registry fields), so shared column names such as "status" keep their per-relation meaning.

from backend.dealdesk.data import schema as _r12  # noqa: E402  (pure data: no pandas, no Deal Desk engine)


def _r12_rel(rid: str) -> dict[str, Any]:
    s = _r12.RELATIONS[rid]
    fields = {n: {"description": d, "unit": u} for n, _t, u, d in _r12.columns(rid)}
    book = "corporate"
    return _rel(f"{s['folder']}/{rid}.parquet", book, s["label"], s["keys"], s["period"], s["description"],
                f"{s['folder']}/{_r12.MANIFEST[s['folder']]}", "external", s["grain"], fields)


for _rid, _s in _r12.RELATIONS.items():
    if _s["domain"] == "deal_desk_products" and "deal_desk_products" not in DOMAINS:
        _lab, _desc = _r12.DOMAIN_TEXT["deal_desk_products"]
        DOMAINS["deal_desk_products"] = {"label": _lab, "status": "live", "description": _desc, "relations": {}}
    if _s["domain"] == "borrower_360" and DOMAINS["borrower_360"]["status"] != "live":
        _lab, _desc = _r12.DOMAIN_TEXT["borrower_360"]
        # rel-saudi-v1's manifest keeps its dictionary as {column: text}: read it into registry fields
        _rel_d = {_c: ({"description": _t} if isinstance(_t, str) else _t)
                  for _c, _t in (_read(f"{_r12.REL_DIR}/manifest.json").get("dictionary") or {}).items()}
        DOMAINS["borrower_360"] = {"label": _lab, "status": "live", "description": _desc, "relations": {
            _k: _rel(f"{_r12.REL_DIR}/{_k}.parquet", "corporate", _v["label"], _v["keys"], _v["period"], _v["description"],
                     grain=_v["grain"], fields=_rel_d)
            for _k, _v in _r12.B360_EXISTING.items()}}
    if _s["domain"] not in DOMAINS and _s["domain"] in _r12.DOMAIN_TEXT:  # R13 IE: governance
        _lab, _desc = _r12.DOMAIN_TEXT[_s["domain"]]
        DOMAINS[_s["domain"]] = {"label": _lab, "status": "live", "description": _desc, "relations": {}}
    DOMAINS[_s["domain"]]["relations"][_rid] = _r12_rel(_rid)
