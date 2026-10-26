"""Seeded Saudi defaults for every Deal Desk parameter table (version v1).

`ops/dealdesk_build.py` writes these to data/dealdesk/params/v1/<table>.json; the service
reads the JSON files (and any Admin edits in var/dealdesk), never this module directly.
Where the bank's credit policy (backend/cockpit_v4/credit_policy.json) sets a figure, the
table uses it and cites the clause, so Deal Desk and the Cockpit apply one policy.
"""
from __future__ import annotations

from typing import Any

from backend.v5common.ratings import RATING_ORDER

GRADES = [r for r in RATING_ORDER if r != "D"]
EFFECTIVE = "2026-10-01"

#: 12-month through-the-cycle PD by grade: the corporate book's own master scale
#: (`pd_ttc_12m` by `rating_current`, identical in every quarter); AAA and AA+ are not
#: in the book and are extrapolated on the same log-linear slope.
MASTER_SCALE = {
    "AAA": 0.000100, "AA+": 0.000180, "AA": 0.000263, "AA-": 0.000389, "A+": 0.000576, "A": 0.000853,
    "A-": 0.001262, "BBB+": 0.001868, "BBB": 0.002765, "BBB-": 0.004092, "BB+": 0.006058, "BB": 0.008966,
    "BB-": 0.013271, "B+": 0.019644, "B": 0.029077, "B-": 0.043038, "CCC": 0.063704, "CC": 0.094293,
    "C": 0.139569,
}


def bucket(rating: str) -> str:
    i = GRADES.index(rating)
    return "IG" if i <= 9 else "BB" if i <= 12 else "B" if i <= 15 else "CCC-C"


def migration_matrix() -> list[dict[str, Any]]:
    """A one-year grade migration matrix whose default column is the master scale.

    Stay probability falls from 90% (AAA) to 68% (C); the rest is split 40% upgrade / 60%
    downgrade with a geometric decay of 0.35 per notch. Rows sum to 1 exactly (stay absorbs
    the rounding).
    """
    n = len(GRADES)
    rows = []
    for i, g in enumerate(GRADES):
        pd_ = MASTER_SCALE[g]
        stay = 0.90 - 0.22 * i / (n - 1)
        rest = max(0.0, 1.0 - pd_ - stay)
        up_w = [0.35 ** (i - j - 1) for j in range(i)]
        dn_w = [0.35 ** (j - i - 1) for j in range(i + 1, n)]
        up_share = 0.4 if up_w and dn_w else (1.0 if up_w else 0.0)
        dn_share = 1.0 - up_share if dn_w else 0.0
        if not dn_w:
            up_share = 1.0
        probs = {}
        for j, w in zip(range(i), up_w):
            probs[GRADES[j]] = round(rest * up_share * w / sum(up_w), 6)
        for j, w in zip(range(i + 1, n), dn_w):
            probs[GRADES[j]] = round(rest * dn_share * w / sum(dn_w), 6)
        probs["D"] = pd_
        probs[g] = round(1.0 - sum(probs.values()), 6)
        rows.append({"from": g, "to": {k: probs.get(k, 0.0) for k in GRADES + ["D"]}})
    return rows


#: R12-I: Book (back-book) assumptions, owned by Finance with the relationship table
BOOK_ROWS_DICT = {"reference_date": "today", "utilisation_at_origination": 0.75, "ftp_pass_through": 0.9, "routing_income_bps_of_turnover": 15,
                  "lgd_collateral_haircut": 0.4, "repricing_window_months": [3, 6], "renewals_due_days": 90,
                  "downgrade_notches": 2, "ews_warning_bands": ["high", "critical"], "promise_unmet_below": 0.8,
                  "tier_review_months": {"High": 3, "Medium": 6, "Standard": 12},
                  "hurdle_override_min_facilities": 30, "hurdle_override_min_drift": 0.005,
                  # R13 X (J9): the landing counters count material names only
                  "materiality_floor_sar_mn": 50, "materiality_drift_below_hurdle": 0.02}


def tables() -> dict[str, dict[str, Any]]:
    def t(name: str, owner: str, description: str, rows: Any, **extra: Any) -> dict[str, Any]:
        return {"name": name, "owner": owner, "version": "v1", "effective_from": EFFECTIVE,
                "approved_by": "Faisal Al-Qahtani (Head of Risk)", "description": description, **extra, "rows": rows}

    out = [
        t("pd_master_scale", "Risk Models", "12-month TTC PD by internal grade (the corporate book's master scale).",
          [{"rating": g, "pd_ttc": MASTER_SCALE[g], "bucket": bucket(g)} for g in GRADES]),
        t("pd_migration", "Risk Models", "One-year grade migration matrix; cumulative PD and Stage 2 migration by matrix power.",
          migration_matrix(), sicr_notches=3),
        t("lgd", "Risk Models", "Unsecured LGD by seniority, collateral haircuts (CP-4.1) and recovery time, LGD floor, structure adjustment.",
          {"unsecured": {"senior": 0.45, "subordinated": 0.75},
           "floor": 0.10, "recovery_discount_rate": 0.08,
           "collateral": {
               "cash": {"label": "Cash deposit", "haircut": 0.00, "recovery_years": 0.0, "eligible_sa": True},
               "real_estate": {"label": "Real estate", "haircut": 0.30, "recovery_years": 2.5, "eligible_sa": False},
               "plant_equipment": {"label": "Plant and equipment", "haircut": 0.45, "recovery_years": 1.5, "eligible_sa": False},
               "receivables": {"label": "Receivables", "haircut": 0.50, "recovery_years": 1.0, "eligible_sa": False},
               "shares": {"label": "Listed shares", "haircut": 0.40, "recovery_years": 0.5, "eligible_sa": False},
               "vehicles": {"label": "Vehicles", "haircut": 0.40, "recovery_years": 1.0, "eligible_sa": False}},
           "structure": {"conventional": 1.00, "murabaha": 1.00, "tawarruq": 1.00, "ijara": 0.85, "musharaka": 1.10},
           "guarantor_lgd": {"government": 0.10, "kafalah": 0.10, "bank": 0.40, "corporate": 0.45, "personal": 0.70}},
          policy="CP-4.1 haircuts: cash 0%, real estate 30%, plant and equipment 45%, receivables 50%"),
        t("ccf", "Risk Models", "Credit conversion factors by product: regulatory (SA) and economic (EAD for EL).",
          {"undrawn_committed": {"regulatory": 0.40, "economic": 0.60},
           "performance_lg": {"regulatory": 0.50, "economic": 0.50},
           "financial_lg": {"regulatory": 1.00, "economic": 1.00},
           "trade_lc": {"regulatory": 0.20, "economic": 0.20}}),
        t("sa_risk_weights", "Finance", "SAMA Basel III Standardised Approach risk weights.",
          {"corporate_by_external": {"AAA": 0.20, "AA+": 0.20, "AA": 0.20, "AA-": 0.20, "A+": 0.50, "A": 0.50, "A-": 0.50,
                                     "BBB+": 0.75, "BBB": 0.75, "BBB-": 0.75, "BB+": 1.00, "BB": 1.00, "BB-": 1.00,
                                     "B+": 1.50, "B": 1.50, "B-": 1.50, "CCC": 1.50, "CC": 1.50, "C": 1.50},
           "corporate_unrated": 1.00, "sme_corporate": 0.85, "sovereign": 0.00, "gre": 0.20,
           "ipre_ltv": [{"max_ltv": 0.60, "rw": 0.70}, {"max_ltv": 0.80, "rw": 0.90}, {"max_ltv": 9.99, "rw": 1.10}],
           "adc": 1.50,
           "guarantor": {"government": 0.00, "kafalah": 0.00, "bank": 0.50, "corporate": None, "personal": None},
           "cash_collateral_rw": 0.00, "fx_mismatch_haircut": 0.08}),
        t("capital", "CFO", "Capital basis, target ratio, Tier 1, economic-capital settings, operational risk.",
          {"basis": "max", "capital_ratio_target": 0.135, "tier1_sar_mn": 28000.0, "usd_sar": 3.75,
           "economic": {"confidence": 0.999, "maturity_floor": 1.0, "maturity_cap": 5.0, "correlation_min": 0.12,
                        "correlation_max": 0.24, "correlation_k": 50.0, "pd_floor": 0.0003},
           "operational": {"alpha": 0.15}}),
        t("ftp", "Treasury", "Funds transfer pricing: base curves by tenor (SAIBOR, SOFR) and liquidity premium by tenor.",
          {"tenors": [0.25, 1, 2, 3, 5, 7, 10],
           "base": {"SAR": [0.0520, 0.0505, 0.0475, 0.0455, 0.0440, 0.0445, 0.0455],
                    "USD": [0.0410, 0.0385, 0.0360, 0.0350, 0.0355, 0.0365, 0.0385]},
           "liquidity_premium_bps": {"SAR": [5, 10, 20, 30, 45, 60, 75], "USD": [15, 20, 30, 40, 55, 70, 85]},
           "contingent_bps": {"undrawn_committed": 15, "performance_lg": 5, "financial_lg": 10, "trade_lc": 5},
           "reference_tenor": 0.25}),
        t("opex", "Finance", "Origination and annual servicing cost by segment.",
          {"corporate": {"origination_fixed": 0.05, "origination_bps": 15, "servicing_fixed": 0.02, "servicing_bps": 20},
           "sme": {"origination_fixed": 0.03, "origination_bps": 25, "servicing_fixed": 0.02, "servicing_bps": 35},
           "gre": {"origination_fixed": 0.05, "origination_bps": 10, "servicing_fixed": 0.02, "servicing_bps": 12},
           "covenant_monitoring": {"none": 0.0, "standard": 0.01, "enhanced": 0.03}}),
        t("returns", "CFO", "Hurdle rate by business line (sector overrides), return on allocated capital, zakat.",
          {"hurdle": {"Corporate Banking": 0.15, "SME Banking": 0.16, "Government and GRE": 0.13},
           "hurdle_sector": {"Real Estate": 0.16, "Construction": 0.16},
           "capital_benefit_rate": 0.050, "zakat_rate": 0.10, "ancillary_realisation": 0.60}),
        t("risk_appetite", "CFO", "Risk appetite and regulatory limits, each hard or soft.",
          [
              {"name": "single_name", "label": "Single obligor", "kind": "hard", "limit": 250.0, "unit": "SAR m", "basis": "CP-1.1: SAR 250m per obligor, funded and unfunded EAD"},
              {"name": "group_connected", "label": "Connected group", "kind": "hard", "limit": 500.0, "unit": "SAR m", "basis": "CP-1.2: SAR 500m per connected group (ownership or control, relationship domain rel-saudi-v1)"},
              {"name": "group_large_exposure", "label": "Group large exposure", "kind": "hard", "limit_pct_tier1": 0.25, "unit": "SAR m", "basis": "SAMA large exposures: 25% of Tier 1"},
              {"name": "sector_policy", "label": "Sector (policy)", "kind": "hard", "limit": 0.18, "unit": "share", "basis": "CP-1.3: 18% of the corporate book"},
              {"name": "sector_appetite", "label": "Sector (appetite)", "kind": "soft", "limits": {"Real Estate": 0.10, "Construction": 0.13}, "unit": "share", "basis": "Risk appetite statement 2026"},
              {"name": "rating_bucket", "label": "Rating bucket", "kind": "soft", "limits": {"IG": 1.0, "BB": 0.36, "B": 0.20, "CCC-C": 0.08}, "unit": "share", "basis": "Risk appetite statement 2026"},
              {"name": "collateral_type", "label": "Collateral concentration", "kind": "soft", "limits": {"real_estate": 0.20}, "unit": "share", "basis": "Share of book EAD secured by real estate"},
              {"name": "min_rating", "label": "Minimum rating", "kind": "hard", "new_to_bank": "B-", "existing": "B-", "existing_soft": "CCC", "unit": "rating", "basis": "Credit policy: no new money below B-; existing clients to CCC by escalation"},
              {"name": "max_tenor", "label": "Maximum tenor", "kind": "hard", "limits": {"IG": 10, "BB": 7, "B": 5, "CCC-C": 2}, "unit": "years", "basis": "Tenor matrix by rating bucket"},
              {"name": "ltv", "label": "Loan to value", "kind": "hard", "limit": 0.70, "unit": "share", "basis": "Real-estate finance: maximum LTV 70%"},
              {"name": "dscr", "label": "DSCR after the deal", "kind": "hard", "limit": 1.20, "unit": "x", "basis": "CP-2.1: DSCR at least 1.20x"},
              {"name": "debt_ebitda", "label": "Debt/EBITDA after the deal", "kind": "hard", "limit": 4.0, "unit": "x", "basis": "CP-2.1: leverage at most 4.0x"},
              {"name": "balloon", "label": "Balloon share", "kind": "hard", "limit": 0.50, "unit": "share", "basis": "Credit policy: balloon at most 50%"},
              {"name": "bu_rwa_budget", "label": "BU RWA budget", "kind": "soft", "headroom_sar_mn": 2500.0, "unit": "SAR m", "basis": "Corporate Banking new-business RWA budget, Q4 2026"},
              {"name": "bu_el_budget", "label": "BU EL budget", "kind": "soft", "headroom_sar_mn": 60.0, "unit": "SAR m", "basis": "Corporate Banking new-business EL budget, Q4 2026 (year-1 EL)"},
          ]),
        t("market_bounds", "Treasury", "Market-acceptable pricing by rating bucket; sector add-on on margins.",
          {"by_bucket": {
              "IG": {"margin_bps": [90, 260], "upfront_fee_bps": [20, 100], "commitment_fee_bps": [10, 40], "commission_bps": [40, 120]},
              "BB": {"margin_bps": [175, 375], "upfront_fee_bps": [40, 125], "commitment_fee_bps": [15, 50], "commission_bps": [60, 160]},
              "B": {"margin_bps": [300, 500], "upfront_fee_bps": [50, 150], "commitment_fee_bps": [20, 60], "commission_bps": [90, 200]},
              "CCC-C": {"margin_bps": [450, 650], "upfront_fee_bps": [75, 175], "commitment_fee_bps": [25, 75], "commission_bps": [120, 250]}},
           "sector_margin_addon_bps": {"Real Estate": 25, "Construction": 25},
           "min_amount_share": 0.60}),
        t("doa", "Risk", "Delegation of Authority: approval level by obligor exposure after the deal, rating and soft breaches.",
          [
              {"rank": 1, "level": "Corporate Credit Manager", "max_exposure": 25.0, "min_rating": "BBB-", "max_soft": 0},
              {"rank": 2, "level": "Head of Credit", "max_exposure": 100.0, "min_rating": "BB-", "max_soft": 0},
              {"rank": 3, "level": "Chief Risk Officer", "max_exposure": 175.0, "min_rating": "B-", "max_soft": 1},
              {"rank": 4, "level": "Executive Credit Committee", "max_exposure": 250.0, "min_rating": "CCC", "max_soft": 2},
              {"rank": 5, "level": "Board Credit Committee", "max_exposure": 1e9, "min_rating": "C", "max_soft": 99},
          ], simah_adverse_min_rank=4),
        t("covenant_packages", "Risk", "Covenant package overlay on PD and LGD (outside the PD model), capped.",
          {"cap": 0.15, "packages": {
              "none": {"label": "No financial covenants", "pd_multiplier": 1.00, "lgd_multiplier": 1.00},
              "standard": {"label": "Standard: DSCR, leverage, interest cover (CP-2.1)", "pd_multiplier": 0.95, "lgd_multiplier": 0.98},
              "enhanced": {"label": "Enhanced: standard plus cash sweep and negative pledge", "pd_multiplier": 0.90, "lgd_multiplier": 0.95}}}),
        t("structures", "Shariah and Risk", "Facility types and the structures each allows.",
          {"term_loan": ["conventional", "murabaha", "tawarruq", "ijara", "musharaka"],
           "revolver": ["conventional", "murabaha", "tawarruq"],
           "performance_lg": ["conventional"], "financial_lg": ["conventional"], "trade_lc": ["conventional", "murabaha"],
           "ijara_requires": ["real_estate", "plant_equipment"]}),
        t("stress", "Risk Models", "Stress scenarios for the deal.",
          {"downgrade_1": {"label": "Rating -1 notch", "notches": 1},
           "downgrade_2": {"label": "Rating -2 notches", "notches": 2},
           "collateral_20": {"label": "Collateral value -20%", "collateral_shock": -0.20},
           "collateral_30": {"label": "Collateral value -30%", "collateral_shock": -0.30},
           "saibor_200": {"label": "SAIBOR +200 bps", "rate_shock_bps": 200},
           "utilisation": {"label": "Utilisation shock", "utilisation_pct": 100, "ccf_add": 0.25}}),
        # ---- R5 D4: the full lever set. Each lever's own parameters, owner and source.
        t("pricing_behaviour", "Treasury",
          "Behavioural and ALM parameters for the pricing and structure levers: prepayment, fixed rate, sell-down, sculpting.",
          {"prepayment_cpr": {"IG": 0.06, "BB": 0.04, "B": 0.03, "CCC-C": 0.02},
           "prepayment_fee_max_bps": 200,
           "fixed_rate_alm_premium_bps": {"SAR": 20, "USD": 15},
           "arranger_skim_bps": 35, "hold_min_pct": 40,
           "sculpt_growth": 0.10,
           # R12-I: rating-linked margin ratchet lever (bps added per notch of downgrade; 0 = no ratchet)
           "margin_ratchet_max_bps_per_notch": 50},
          source="Treasury ALM behavioural study 2026 (prepayment CPR by rating bucket, 2019–2026 corporate book); "
                 "ALM fixed-rate hedging premium; syndications desk arranger skim on sold-down shares"),
        t("credit_protection", "Risk Models",
          "Guarantee providers the risk manager can ask for, credit insurance and assignment of receivables (CRM).",
          {"guarantee_catalogue": {
              "REQ-PARENT": {"type": "parent", "label": "Parent company guarantee", "rating_uplift_notches": 2, "lgd": 0.45, "sa_rw": None,
                             "requires_group": True},
              "REQ-BANK": {"type": "bank", "label": "Bank guarantee (A-rated local bank)", "rating": "A", "lgd": 0.40, "sa_rw": 0.50},
              "REQ-SOVEREIGN": {"type": "sovereign", "label": "Sovereign guarantee (Ministry of Finance)", "rating": "A+", "lgd": 0.10, "sa_rw": 0.00,
                                "requires_gre_or_contract": False},
              "REQ-ECA": {"type": "eca", "label": "Export credit agency cover", "rating": "AA", "lgd": 0.10, "sa_rw": 0.00}},
           "credit_insurance": {"insurer_rating": "A", "lgd": 0.45, "sa_rw": 0.50, "premium_bps": 45, "max_cover_pct": 90},
           "receivables_assignment": {"haircut": 0.50, "recovery_years": 1.0, "max_pct": 100, "sa_eligible": False}},
          source="CP-4.1 haircuts (receivables 50%); SAMA Basel III CRM: guarantee substitution for sovereign, bank and ECA "
                 "protection, credit insurance from A-rated insurers treated as an eligible guarantee; Risk Models LGD study 2025"),
        t("covenant_items", "Risk",
          "PD and LGD adjustment for each covenant or condition and for the review cycle, with the monitoring cost; capped with the package.",
          {"items": {
              "leverage": {"label": "Leverage covenant (Debt/EBITDA)", "pd_multiplier": 0.97, "lgd_multiplier": 1.00, "monitoring": 0.002},
              "dscr": {"label": "DSCR covenant", "pd_multiplier": 0.97, "lgd_multiplier": 1.00, "monitoring": 0.002},
              "cash_sweep": {"label": "Cash sweep", "pd_multiplier": 0.96, "lgd_multiplier": 0.97, "monitoring": 0.004},
              "dividend_lockup": {"label": "Dividend lock-up", "pd_multiplier": 0.97, "lgd_multiplier": 0.99, "monitoring": 0.001},
              "negative_pledge": {"label": "Negative pledge and pari passu", "pd_multiplier": 1.00, "lgd_multiplier": 0.95, "monitoring": 0.001}},
           "review_cycles": {
              "12": {"label": "Annual review", "pd_multiplier": 1.00, "maturity_cap": None, "monitoring": 0.0},
              "6": {"label": "Semi-annual review", "pd_multiplier": 0.98, "maturity_cap": 3.0, "monitoring": 0.004},
              "3": {"label": "Quarterly review", "pd_multiplier": 0.96, "maturity_cap": 2.0, "monitoring": 0.010}}},
          source="Risk Models covenant-effectiveness study 2025 (early-trigger cures on the corporate book); the package cap of "
                 "covenant_packages applies to the product of package, items and review cycle"),
        t("relationship", "Finance",
          "Cross-sell commitments: realisation of committed ancillary income for relationship RAROC (uncommitted lines use returns.ancillary_realisation).",
          {"committed_realisation": 0.90,
           "lines": {"cash_management": "Operating accounts and cash management", "payroll": "Payroll", "fx": "FX",
                     "trade": "Trade finance", "deposits": "Deposits"},
           # R12-I: "flat" uses committed_realisation; "actual" uses the realised share of matured promises (dd_promise)
           "committed_realisation_basis": "flat", "actual_min_promises": 5, "book": BOOK_ROWS_DICT},
          source="Corporate Banking relationship P&L 2025: realised share of committed and uncommitted cross-sell"),
    ]
    return {x["name"]: x for x in out}
