"""
The ONE active early-warning signal catalogue, and what it is NOT.

`ews.py` holds the governed rule set that actually scores the published book:
six retail rules, six corporate ones, a weight each, summed in SQL and cut
into bands. That is the deployed model. It is also the only thing on this
instance that produces an early-warning band for a real customer.

This module adds the metadata those rules always implied but never wrote
down, so that ONE catalogue can serve four surfaces without any of them
re-stating a rule of their own:

    * the model-details screen (what the model is, in full);
    * the customer's fired signals (what this customer actually shows);
    * the investigation handoff into Cockpit / Borrower 360;
    * the evidence a signal carries - field, unit, grain, observation date.

Nothing here changes a rule, a weight, a threshold or a band. Every signal
is keyed by the EXISTING rule id (`R-DPD`, `C-WATCH`, ...) so saved cohorts,
threads, filters and histories keep resolving.

Sources are not risk layers
---------------------------
A SOURCE is where an observation came from: the bank's own systems, a credit
bureau, an account-information (Open Banking) feed. A LAYER is what kind of
risk it speaks to. They are different axes, and a signal belongs to exactly
one of each, so it is counted once however the screen is grouped.

Two of the three source groups are declared and EMPTY on this release. The
candidate books publish no bureau file and no account-information feed, so
`bureau` and `open_banking` carry zero active signals and say so. A payment
ratio computed from the bank's own ledger is a BANK INTERNAL observation; it
is not an Open Banking observation because it happens to be about cash.

The reference model
-------------------
A richer four-layer retail model exists in another checkout (the reference
instance at `/early-warning/model`). Its definitions are carried here as
`reference` for comparison and for the compatibility audit - NOT as scoring.
No number on any screen comes from it. `REFERENCE_STATUS` says so, and the
compatibility verdicts in `reference_compatibility()` state per input why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.ews_domain import ews_rules as ews

CATALOGUE_VERSION = "gw-ews-catalogue-1.1.0"

#: The deployed scoring identity. Unchanged by this module.
ACTIVE_MODEL = {
    "id": "gw-ews",
    "name": "Guided Workspace Early Warning rule set",
    "version": ews.RULESET_VERSION,
    "kind": "deterministic_rule_set",
    "status": "ACTIVE",
    "scoring": ("Each live rule contributes its integer WEIGHT when its SQL "
                "is true on the exposure row; the weights are summed into "
                "ews_score and ews.bands(book) cuts that sum into a severity "
                "band."),
    "contribution_kind": "rule_weight",
    "contribution_caveat": (
        "A rule weight is a severity weight in a deterministic rule set, not "
        "a fitted score contribution. It is not a coefficient, a shapley "
        "value or a percentage of the score, and it must not be presented as "
        "one."),
    "overrides": (
        "gw-ews (1.0.0 and 1.1.0) has NO override, floor or hard-trigger mechanism: the "
        "band is the banded sum and nothing overrides it. Where a customer "
        "is already impaired, the booked stage and DPD are shown beside the "
        "band rather than folded into it."),
    "model_calls": 0,
}


# ------------------------------------------------------------------ sources

@dataclass(frozen=True)
class Source:
    """Where an observation came from. One of three, for both domains."""

    key: str
    label: str
    means: str
    #: True only where the open release actually publishes a feed of this
    #: provenance. Never set from a proxy.
    connected: bool
    #: Set when `connected` is False: what is missing, in one sentence.
    absent_because: str = ""
    #: What would have to arrive for this group to carry observations.
    requires: tuple[str, ...] = ()


SOURCES: tuple[Source, ...] = (
    Source(
        key="bank_internal",
        label="Bank Internal",
        means=("Observed in the bank's own systems: the account and customer "
               "ledger, the behaviour mart, the risk and IFRS 9 marts and "
               "the credit officer's own flags."),
        connected=True),
    Source(
        key="bureau",
        label="Bureau & External Credit",
        means=("Observed in a dated credit-bureau pull: an external score, "
               "external delinquency, external leverage and enquiries. In v5 "
               "this is the SIMAH-style Bureau domain "
               "(data/external/bureau-saudi-v1), keyed to the same customers, "
               "borrowers and periods as the books."),
        connected=True),
    Source(
        key="open_banking",
        label="Open Banking",
        means=("Observed through an account-information feed: inflows, salary "
               "credits, balance buffers and returned payments. In v5 this is "
               "the Open Banking domain (data/external/"
               "open-banking-saudi-v1), keyed to the same customers, borrowers "
               "and periods as the books."),
        connected=True),
)

SOURCE_BY_KEY: dict[str, Source] = {s.key: s for s in SOURCES}


# ----------------------------------------------------------------- families

@dataclass(frozen=True)
class Family:
    key: str
    label: str
    means: str
    #: The risk layer this family speaks to. A SEPARATE axis from the source.
    layer: str


FAMILIES: tuple[Family, ...] = (
    Family("delinquency", "Delinquency",
           "The customer is behind on a contractual payment now.",
           "behavioural"),
    Family("payment_behaviour", "Payment behaviour",
           "How the customer has been paying, short of being in arrears.",
           "behavioural"),
    Family("score_migration", "Score migration",
           "The bank's own behavioural score and the direction it moved.",
           "behavioural"),
    Family("utilisation", "Utilisation & exposure",
           "How much of the available limit the customer is using.",
           "exposure"),
    Family("affordability", "Affordability",
           "Whether the customer's income can carry the obligation.",
           "affordability"),
    Family("rating_watchlist", "Rating & watchlist",
           "The bank's own credit opinion and the officer's own flag.",
           "credit_opinion"),
    Family("covenant", "Covenant",
           "A contractual test the borrower has failed.",
           "documentation"),
    Family("transfer", "Stage & transfer",
           "The booked IFRS 9 position, not a prediction.",
           "booked_accounting"),
    Family("external_score", "External score",
           "The bureau's own score for the customer.",
           "behavioural"),
    Family("credit_appetite", "Credit appetite",
           "How hard the customer is looking for new credit elsewhere.",
           "behavioural"),
    Family("liquidity", "Liquidity & cash flow",
           "What flows into the customer's accounts and how long the balance lasts.",
           "liquidity"),
)

FAMILY_BY_KEY: dict[str, Family] = {f.key: f for f in FAMILIES}

#: The risk layers, as an axis in their own right. Declared so a screen can
#: group by layer without inventing a layer per signal.
#:
#: A layer carries BOTH a display label and its meaning, because every
#: surface that shows a layer shows it to a reader: the key is an internal
#: identifier and must never reach the screen as the layer's name.
LAYER_LABELS: dict[str, str] = {
    "behavioural": "Behavioural",
    "exposure": "Exposure",
    "affordability": "Affordability",
    "credit_opinion": "Credit opinion",
    "documentation": "Documentation",
    "booked_accounting": "Booked accounting",
    "liquidity": "Liquidity",
}

LAYERS: dict[str, str] = {
    "behavioural": "How the customer is servicing the facility.",
    "exposure": "How much is drawn against what was granted.",
    "affordability": "Whether income can carry the debt.",
    "credit_opinion": "The bank's own rating and watchlist.",
    "documentation": "Covenants and contractual tests.",
    "booked_accounting": ("The IFRS 9 position already recognised, shown for "
                          "context, never as a prediction."),
    "liquidity": "Cash coming in and the balance buffer, seen in the customer's accounts.",
}


def layer_label(key: str) -> str:
    """The reader-facing name of a risk layer. Never the raw key."""
    return LAYER_LABELS.get(key, "")


# ------------------------------------------------------------------ signals

@dataclass(frozen=True)
class Input:
    """One canonical field a signal reads, and what it means."""

    column: str
    label: str
    unit: str
    meaning: str
    #: exposure | owner — the grain the field is published at.
    grain: str
    source: str = "bank_internal"
    #: How the value is dated. "" means "the reporting period itself".
    observed_as: str = ""


@dataclass(frozen=True)
class SignalMeta:
    """The catalogue entry for ONE existing rule of `ews.RULES`."""

    #: The EXISTING rule id. Stable; saved objects resolve through it.
    id: str
    domain: str
    source: str
    family: str
    #: The condition in words. The SQL itself stays the single source of
    #: truth and is served beside this.
    condition: str
    inputs: tuple[Input, ...]
    #: The field whose value a customer card should show as "observed".
    observed_column: str
    review: str
    proxy: bool = False


# Canonical fields, declared once and shared by the signals that read them.
_RETAIL_FIELDS: dict[str, Input] = {
    "bureau_score": Input("bureau_score", "Bureau score", "points",
                          "SIMAH-style bureau score, 300 worst to 900 best.", "owner", source="bureau"),
    "external_dpd_days": Input("external_dpd_days", "External DPD", "days",
                               "Worst days past due at other lenders.", "owner", source="bureau"),
    "enquiries_3m": Input("enquiries_3m", "Bureau enquiries, 3 months", "count",
                          "Credit enquiries by other lenders in the last 3 months.", "owner",
                          source="bureau"),
    "salary_interruption_flag": Input("salary_interruption_flag", "Salary interruption", "flag",
                                      "Salaried customer with no salary credit this month.",
                                      "owner", source="open_banking"),
    "balance_buffer_months": Input("balance_buffer_months", "Balance buffer", "months",
                                   "Months of obligations the average balance covers.",
                                   "owner", source="open_banking"),
    "inflow_trend_pct": Input("inflow_trend_pct", "Inflow trend", "%",
                              "Change in account inflows against 3 months earlier.",
                              "owner", source="open_banking"),
    "customer_score_band": Input("customer_score_band", "Customer behaviour band", "band",
                                 "The customer's behavioural score band, A best to E "
                                 "worst, at month-end.", "owner"),
    "customer_score_band_previous": Input("customer_score_band_previous",
                                          "Customer behaviour band last month", "band",
                                          "The customer's band at the previous month-end.",
                                          "owner", observed_as="previous month"),
    "dpd_days": Input("dpd_days", "Days past due", "days",
                      "Contractual days past due on the account at month-end.",
                      "exposure"),
    "score_band": Input("score_band", "Behaviour score band", "band",
                        "The bank's own behavioural score band, A best to E "
                        "worst, at month-end.", "exposure"),
    "score_migration": Input("score_migration", "Score migration", "category",
                             "Improved / Stable / Deteriorated against the "
                             "previous month's band.", "owner",
                             observed_as="month-on-month comparison"),
    "utilisation_pct": Input("utilisation_pct", "Utilisation", "percent",
                             "Balance over approved limit, in per cent.",
                             "exposure"),
    "payment_ratio_pct": Input("payment_ratio_pct", "Payment ratio", "percent",
                               "Amount paid over amount due in the month, in "
                               "per cent, from the bank's behaviour mart.",
                               "exposure"),
    "payment_ratio_change_3m": Input("payment_ratio_change_3m", "Payment ratio change, 3 months", "points",
                                     "Payment ratio now less the payment ratio 3 months earlier, in points.",
                                     "exposure", observed_as="3-month comparison"),
    "employment_type": Input("employment_type", "Employment type", "category",
                             "Declared employment type on the customer "
                             "record.", "owner"),
    "employer_sector_group": Input("employer_sector_group", "Employer sector",
                                   "category",
                                   "Cyclicality grouping of the declared "
                                   "employer sector.", "owner"),
}

_CORPORATE_FIELDS: dict[str, Input] = {
    "external_dpd_days": Input("external_dpd_days", "External DPD", "days",
                               "Worst days past due at other lenders.", "owner", source="bureau"),
    "inflow_trend_pct": Input("inflow_trend_pct", "Operating inflow trend", "%",
                              "Change in operating-account inflows against the same quarter a year earlier.",
                              "owner", source="open_banking"),
    "enquiries_q": Input("enquiries_q", "Bureau enquiries, quarter", "count",
                         "Credit enquiries by other lenders this quarter.", "owner", source="bureau"),
    "balance_buffer_months": Input("balance_buffer_months", "Operating balance buffer", "months",
                                   "Months of obligations the average operating balance covers.",
                                   "owner", source="open_banking"),
    "returned_payments_q": Input("returned_payments_q", "Returned payments", "count",
                                 "Returned payments on the operating accounts this quarter.",
                                 "owner", source="open_banking"),
    "stage": Input("stage", "IFRS 9 stage", "stage",
                   "The facility's booked IFRS 9 stage at quarter-end.", "exposure"),
    "default_flag": Input("default_flag", "Default flag", "flag",
                          "The facility is flagged as in default at quarter-end.", "exposure"),
    "watchlist_flag": Input("watchlist_flag", "Watchlist", "flag",
                            "The credit officer has placed the borrower on "
                            "the watchlist.", "owner"),
    "rating_notches_moved": Input("rating_notches_moved", "Notches moved",
                                  "notches",
                                  "Movement in the bank's own rating this "
                                  "quarter; negative is a downgrade.",
                                  "owner"),
    "covenant_breaches": Input("covenant_breaches", "Covenant breaches",
                               "count",
                               "Covenant tests recorded in breach this "
                               "quarter.", "exposure"),
    "dpd_days": Input("dpd_days", "Days past due", "days",
                      "Contractual days past due on the facility at "
                      "quarter-end.", "exposure"),
    "sicr_flag": Input("sicr_flag", "SICR", "flag",
                       "Significant increase in credit risk, as booked under "
                       "the bank's IFRS 9 policy.", "exposure"),
    "utilisation_pct": Input("utilisation_pct", "Utilisation", "percent",
                             "Drawn over approved limit, in per cent.",
                             "exposure"),
}

SIGNALS: tuple[SignalMeta, ...] = (
    # ------------------------------------------------------------- retail
    SignalMeta(
        id="R-DPD", domain="retail", source="bank_internal",
        family="delinquency",
        condition="Days past due is above zero at the reporting month-end.",
        inputs=(_RETAIL_FIELDS["dpd_days"],),
        observed_column="dpd_days",
        review="Confirm the arrears are real and not a direct-debit failure, "
               "then agree a collection action."),
    SignalMeta(
        id="R-SCORE-LOW", domain="retail", source="bank_internal",
        family="score_migration",
        condition="The behavioural score band is E.",
        inputs=(_RETAIL_FIELDS["score_band"],),
        observed_column="score_band",
        review="Read the band against the customer's own history before "
               "treating a long-standing weak band as news."),
    SignalMeta(
        id="R-SCORE-DOWN", domain="retail", source="bank_internal",
        family="score_migration",
        condition=("The customer's behavioural score band fell 2 or more bands "
                   "against last month (A best, E worst)."),
        inputs=(_RETAIL_FIELDS["customer_score_band_previous"],
                _RETAIL_FIELDS["customer_score_band"]),
        observed_column="customer_score_band",
        review="Check what drove the migration before acting on the band "
               "alone."),
    SignalMeta(
        id="R-UTIL", domain="retail", source="bank_internal",
        family="utilisation",
        condition="Utilisation is at or above 85 per cent of the limit.",
        inputs=(_RETAIL_FIELDS["utilisation_pct"],),
        observed_column="utilisation_pct",
        review="High utilisation on a revolving product is normal for some "
               "customers; read it with the payment ratio."),
    SignalMeta(
        id="R-MINPAY", domain="retail", source="bank_internal",
        family="payment_behaviour",
        condition=("The payment ratio is below 30 per cent of the amount due and fell by 10 points or "
                   "more in 3 months."),
        inputs=(_RETAIL_FIELDS["payment_ratio_pct"], _RETAIL_FIELDS["payment_ratio_change_3m"]),
        observed_column="payment_ratio_pct",
        review="Persistent minimum payment is an affordability question, not "
               "a collections one."),
    SignalMeta(
        id="R-SALARY", domain="retail", source="bank_internal",
        family="affordability",
        condition=("A salaried customer in a cyclical employer sector whose "
                   "payment ratio is below 35 per cent."),
        inputs=(_RETAIL_FIELDS["employment_type"],
                _RETAIL_FIELDS["employer_sector_group"],
                _RETAIL_FIELDS["payment_ratio_pct"]),
        observed_column="payment_ratio_pct",
        review="Ask for the salary evidence. This is a stand-in, and the "
               "answer may be that nothing happened to the salary at all.",
        proxy=True),
    # ---------------------------------------------------------- corporate
    SignalMeta(
        id="C-WATCH", domain="corporate", source="bank_internal",
        family="rating_watchlist",
        condition="The borrower is on the bank's watchlist.",
        inputs=(_CORPORATE_FIELDS["watchlist_flag"],),
        observed_column="watchlist_flag",
        review="Read the watchlist reason and the quarters on watchlist "
               "before treating the flag as new information."),
    SignalMeta(
        id="C-DOWNGRADE", domain="corporate", source="bank_internal",
        family="rating_watchlist",
        condition="The bank's own rating moved down this quarter (notches moved below zero; positive means an upgrade in this book).",
        inputs=(_CORPORATE_FIELDS["rating_notches_moved"],),
        observed_column="rating_notches_moved",
        review="Compare the notches moved with the rating history; a single "
               "notch off a strong grade is not the same finding."),
    SignalMeta(
        id="C-COVENANT", domain="corporate", source="bank_internal",
        family="covenant",
        condition="One or more covenant tests are in breach this quarter.",
        inputs=(_CORPORATE_FIELDS["covenant_breaches"],),
        observed_column="covenant_breaches",
        review="Identify which covenant and whether a waiver has been "
               "requested."),
    SignalMeta(
        id="C-DPD", domain="corporate", source="bank_internal",
        family="delinquency",
        condition="Days past due is above 59 at the reporting quarter-end (90+ in this book).",
        inputs=(_CORPORATE_FIELDS["dpd_days"],),
        observed_column="dpd_days",
        review="Confirm whether the arrears are administrative or a genuine "
               "payment failure."),
    SignalMeta(
        id="C-SICR", domain="corporate", source="bank_internal",
        family="transfer",
        condition="The SICR flag is raised on the facility.",
        inputs=(_CORPORATE_FIELDS["sicr_flag"],),
        observed_column="sicr_flag",
        review="SICR is a BOOKED accounting classification already "
               "recognised, not a prediction of future deterioration."),
    SignalMeta(
        id="C-UTIL", domain="corporate", source="bank_internal",
        family="utilisation",
        condition="Utilisation is at or above 98 per cent of the limit.",
        inputs=(_CORPORATE_FIELDS["utilisation_pct"],),
        observed_column="utilisation_pct",
        review="Read utilisation with the undrawn commitment and the "
               "facility class."),
    SignalMeta(
        id="C-DEFAULT", domain="corporate", source="bank_internal",
        family="transfer",
        condition="The facility is in Stage 3 or carries the default flag.",
        inputs=(_CORPORATE_FIELDS["stage"], _CORPORATE_FIELDS["default_flag"]),
        observed_column="stage",
        review="Already impaired: this keeps a defaulted name on the warning "
               "list; the workout, not the warning, is the action."),
    # ------------------------------------------- gw-ews-1.2.0: external sources
    SignalMeta(
        id="R-BUR-SCORE", domain="retail", source="bureau", family="external_score",
        condition="The bureau score is below the threshold.",
        inputs=(_RETAIL_FIELDS["bureau_score"],), observed_column="bureau_score",
        review="Compare with the bank's own behaviour score; a gap between them is itself a finding."),
    SignalMeta(
        id="R-BUR-EXTDPD", domain="retail", source="bureau", family="delinquency",
        condition="The customer is past due at another lender beyond the threshold.",
        inputs=(_RETAIL_FIELDS["external_dpd_days"],), observed_column="external_dpd_days",
        review="Arrears elsewhere often reach this bank's book a few months later."),
    SignalMeta(
        id="R-BUR-ENQ", domain="retail", source="bureau", family="credit_appetite",
        condition="Other lenders have run at least the threshold number of enquiries in 3 months.",
        inputs=(_RETAIL_FIELDS["enquiries_3m"],), observed_column="enquiries_3m",
        review="A burst of enquiries can be shopping for a mortgage, or a search for liquidity; read with the buffer."),
    SignalMeta(
        id="R-OB-SALARY", domain="retail", source="open_banking", family="affordability",
        condition="A salaried customer received no salary credit this month.",
        inputs=(_RETAIL_FIELDS["salary_interruption_flag"],), observed_column="salary_interruption_flag",
        review="Confirm the employer and whether the salary moved to another bank before acting. "
               "Replaces the R-SALARY proxy with the observed salary-credit signal."),
    SignalMeta(
        id="R-OB-BUFFER", domain="retail", source="open_banking", family="liquidity",
        condition="The balance covers less than the threshold in months of obligations.",
        inputs=(_RETAIL_FIELDS["balance_buffer_months"],), observed_column="balance_buffer_months",
        review="A thin buffer turns any income shock into a missed payment."),
    SignalMeta(
        id="R-OB-INFLOW", domain="retail", source="open_banking", family="liquidity",
        condition="Account inflows fell by at least the threshold against 3 months earlier.",
        inputs=(_RETAIL_FIELDS["inflow_trend_pct"],), observed_column="inflow_trend_pct",
        review="Separate a lost income from a one-off: look at the salary credit first."),
    SignalMeta(
        id="C-BUR-EXTDPD", domain="corporate", source="bureau", family="delinquency",
        condition="The borrower is past due at another lender beyond the threshold.",
        inputs=(_CORPORATE_FIELDS["external_dpd_days"],), observed_column="external_dpd_days",
        review="Ask the relationship manager which lender, which facility and since when."),
    SignalMeta(
        id="C-OB-INFLOW", domain="corporate", source="open_banking", family="liquidity",
        condition="Operating-account inflows fell by at least the threshold against the same quarter a year earlier.",
        inputs=(_CORPORATE_FIELDS["inflow_trend_pct"],), observed_column="inflow_trend_pct",
        review="Year on year, so a seasonal quarter is not read as distress; check contract timing."),
    # ------------------------------------------- gw-ews-1.3.0: the story signals (EWS_STORY.md)
    SignalMeta(
        id="C-BUR-ENQ", domain="corporate", source="bureau", family="credit_appetite",
        condition="Other lenders have run at least the threshold number of enquiries this quarter.",
        inputs=(_CORPORATE_FIELDS["enquiries_q"],), observed_column="enquiries_q",
        review="A borrower looking for new lines while its own are full is looking for liquidity."),
    SignalMeta(
        id="C-OB-BUFFER", domain="corporate", source="open_banking", family="liquidity",
        condition="The operating balance covers less than the threshold in months of obligations.",
        inputs=(_CORPORATE_FIELDS["balance_buffer_months"],), observed_column="balance_buffer_months",
        review="Contractors waiting on payment certificates run their buffers down first."),
    SignalMeta(
        id="C-OB-RETURNED", domain="corporate", source="open_banking", family="payment_behaviour",
        condition="At least the threshold number of payments from the operating accounts were returned this quarter.",
        inputs=(_CORPORATE_FIELDS["returned_payments_q"],), observed_column="returned_payments_q",
        review="Returned supplier payments are the first visible sign of a payment chain under strain."),
)

BY_ID: dict[tuple[str, str], SignalMeta] = {(s.domain, s.id): s
                                            for s in SIGNALS}


def signal(domain_id: str, signal_id: str) -> SignalMeta | None:
    return BY_ID.get((domain_id, signal_id))


def _rule(domain_id: str, signal_id: str) -> dict[str, Any] | None:
    for one in ews.RULES.get(domain_id, ()):
        if one["id"] == signal_id:
            return one
    return None


def signal_dict(domain_id: str, signal_id: str) -> dict[str, Any]:
    """One catalogue entry, joined to the rule that actually scores it."""
    rule = _rule(domain_id, signal_id)
    if rule is None:
        return {}
    meta = signal(domain_id, signal_id)
    src = SOURCE_BY_KEY.get(meta.source if meta else "bank_internal")
    fam = FAMILY_BY_KEY.get(meta.family if meta else "")
    return {
        "id": signal_id,
        "label": rule["label"],
        "expression": rule["sql"],
        "weight": rule["weight"],
        "contribution_kind": ACTIVE_MODEL["contribution_kind"],
        "limitation": rule.get("limitation", ""),
        "ruleset": ews.RULESET_VERSION,
        "source": src.key if src else "",
        "source_label": src.label if src else "",
        "source_connected": bool(src and src.connected),
        "family": fam.key if fam else "",
        "family_label": fam.label if fam else "",
        "layer": fam.layer if fam else "",
        "layer_label": LAYER_LABELS.get(fam.layer, "") if fam else "",
        "layer_means": LAYERS.get(fam.layer, "") if fam else "",
        "condition": meta.condition if meta else "",
        "review": meta.review if meta else "",
        "proxy": bool(meta and meta.proxy),
        "observed_column": meta.observed_column if meta else "",
        "inputs": [{"column": i.column, "label": i.label, "unit": i.unit,
                    "meaning": i.meaning, "grain": i.grain,
                    "source": i.source, "observed_as": i.observed_as}
                   for i in (meta.inputs if meta else ())],
    }


def catalogue(domain_id: str) -> dict[str, Any]:
    """The whole active catalogue for one domain. No release read."""
    entries = [signal_dict(domain_id, one["id"])
               for one in ews.RULES.get(domain_id, ())]
    by_source: dict[str, list[str]] = {s.key: [] for s in SOURCES}
    for one in entries:
        by_source.setdefault(one["source"], []).append(one["id"])
    return {
        "catalogue_version": CATALOGUE_VERSION,
        "active_model": ACTIVE_MODEL,
        "domain_id": domain_id,
        "signals": entries,
        "families": [{"key": f.key, "label": f.label, "means": f.means,
                      "layer": f.layer,
                      "signals": [e["id"] for e in entries
                                  if e["family"] == f.key]}
                     for f in FAMILIES],
        "layers": [{"key": k, "label": LAYER_LABELS.get(k, ""), "means": v,
                    "signals": [e["id"] for e in entries if e["layer"] == k]}
                   for k, v in LAYERS.items()],
        "sources": [{"key": s.key, "label": s.label, "means": s.means,
                     "connected": s.connected,
                     # What `connected` actually means here. It is a
                     # PUBLISHED relation in the governed canonical release,
                     # which is a static snapshot: no screen may word it as a
                     # live connection to a source system.
                     "availability": ("Published in this release"
                                      if s.connected
                                      else "Not published in this release"),
                     "availability_means": (
                         "These observations are read from the published "
                         "canonical relations of this release -- a governed "
                         "static snapshot, not a live feed or an integration "
                         "with the source system."
                         if s.connected else
                         "No relation of this provenance exists in the "
                         "release, so no signal in this group is evaluated."),
                     "absent_because": s.absent_because,
                     "requires": list(s.requires),
                     "signals": by_source.get(s.key, []),
                     "signal_count": len(by_source.get(s.key, []))}
                    for s in SOURCES],
        "axes": ("Source and risk layer are separate axes. Every signal "
                 "belongs to exactly one source and one layer, so it is "
                 "counted once however the screen is grouped."),
        "model_calls": 0,
    }


# -------------------------------------------------------- reference model

#: The reference instance's four-layer retail model, carried as DEFINITIONS
#: for comparison. Captured read-only; no score, band, customer or count from
#: that instance is carried with it.
REFERENCE_FILE = (Path(__file__).resolve().parent / "data"
                  / "ews_reference_retail_v3.json")

#: The reference model is a RETAIL model. It is not a corporate rule set and
#: is not a comparison for one: a corporate reader opening it must be told
#: that, rather than be shown retail layers under a corporate heading.
REFERENCE_DOMAIN = "retail"

REFERENCE_STATUS = {
    "status": "NOT_DEPLOYED",
    "scores_active": False,
    "means": ("Definitions only, captured for the compatibility audit. No "
              "band, score, weight or threshold on any screen of this "
              "instance comes from this model, and importing it is a "
              "separately versioned proposal that needs a valid input "
              "mapping and canonical parity evidence first."),
}


@lru_cache(maxsize=1)
def reference() -> dict[str, Any]:
    """The reference catalogue, or an honest empty one."""
    try:
        return json.loads(REFERENCE_FILE.read_text())
    except (OSError, ValueError):
        return {"available": False,
                "why": "The reference catalogue file is not present in this "
                       "checkout.", **REFERENCE_STATUS}


def reference_compatibility(domain_id: str = "retail") -> dict[str, Any]:
    """Per-input compatibility of the reference model with this release.

    The reference model covers ONE domain. `applies_to_domain` says whether
    the book being read is that domain, so a corporate screen states that
    this is a retail model rather than presenting retail layers, triggers and
    thresholds as a comparison for the corporate rule set.
    """
    ref = reference()
    applies = (domain_id or REFERENCE_DOMAIN) == REFERENCE_DOMAIN
    return {**REFERENCE_STATUS,
            "available": bool(ref.get("inputs")),
            "model": {k: ref.get(k) for k in
                      ("model_id", "model_name", "model_version", "source",
                       "captured_utc", "file_sha256")},
            "summary": ref.get("summary", {}),
            "inputs": ref.get("inputs", []),
            "layers": ref.get("layers", []),
            "domain_id": domain_id,
            "reference_domain": REFERENCE_DOMAIN,
            "applies_to_domain": applies,
            "domain_note": (
                "" if applies else
                f"This is a {REFERENCE_DOMAIN} model. It is carried for the "
                f"{REFERENCE_DOMAIN} compatibility audit and is not a "
                f"comparison for the {domain_id} rule set: its layers, "
                "triggers and thresholds are defined over "
                f"{REFERENCE_DOMAIN} fields, and no {domain_id} mapping of "
                "them exists or is proposed here.")}


__all__ = ["ACTIVE_MODEL", "CATALOGUE_VERSION", "FAMILIES", "LAYERS",
           "LAYER_LABELS", "REFERENCE_DOMAIN", "SIGNALS", "SOURCES",
           "catalogue", "layer_label", "reference",
           "reference_compatibility", "signal", "signal_dict"]
