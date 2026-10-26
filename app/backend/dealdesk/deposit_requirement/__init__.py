"""Round D (PLAN_DEALDESK_EDITION row D): the Deposit requirement term.

Anne, UAT 1: "The term sheet does not have the deposit requirement."

    term.py   the term (five flat term keys beside the engine's other levers), its validation, its words, its amount, and
              the engine's two channels:
                lien-marked cash collateral  -> recognised as cash (haircut row `lgd.collateral.lien_deposit`) in the LGD
                                                recoveries and netted from the SA exposure, so EAD net of the deposit, LGD,
                                                RWA, EL and capital fall (the existing collateral / cash-margin mechanics);
                relationship / operating balances -> funding value (FTP credit less the profit paid, `uae_desk.deposit_ftp_credit`
                                                and `relationship.deposit_requirement`) added to relationship RAROC only.
    docs.py   the term in every document: bank form / committee paper (dd_security + dd_tnc rows), the RM's business request
              (security line and maintenance condition), the credit response (conditions precedent), the review (counter-proposal
              terms and a tracked condition).

The figures are the engine's: the documents print the amount the engine used (`analysis["deposit"]`), never one of their own.
"""
from backend.dealdesk.deposit_requirement.term import (  # noqa: F401
    KEYS, NEUTRAL, TYPES, describe, engine_effect, from_terms, normalise, short, validate,
)
