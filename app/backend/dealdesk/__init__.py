"""Deal Desk (Pre-deal Analysis): pre-deal RAROC structuring (docs/v5/DEAL_DESK_PROMPT.md).

Its own data domain (data/dealdesk, var/dealdesk) keyed to the shared spine. Reads the
corporate book and the What-If XGBoost PD model read-only; writes only its own store.

    params       versioned parameter tables (owner per table), Admin edits
    portfolio    read-only snapshot of the corporate book for marginal limits
    proposals    the 15 seeded credit proposals and user-created ones
    pd_model     obligor PD from the What-If corporate XGBoost model (PD only)
    engine       schedule, EAD, LGD, capital, profitability, RAROC, SVA
    constraints  marginal risk-appetite and regulatory limits, Delegation of Authority
    optimizer    closest-to-ask, maximum SVA, frontier, relaxation, stress
    api          the engine API on port 8508 (docs/v5/DEALDESK_API.md)
"""
