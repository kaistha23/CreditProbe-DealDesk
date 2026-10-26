"""R13 Session S: the shared, data-driven scenario engine (PLAN_R13 §S, R12 feedback J5 and J6).

    from backend.scenarios import engine
    res = engine.build()            # calibration, joint scenarios, satellite models, translation (cached)

Modules
  data        the inputs and what they can and cannot support (bank history, MEVs)
  calibrate   mild / moderate / severe for every driver from the empirical distribution of its change
  joint       joint scenarios: historical analogues and a Gaussian copula on the observed correlation
  satellite   sector PD and Stage 1 -> 2 migration on macro drivers (pooled panel, sector effects, ridge)
  translate   driver -> PD, LGD, EAD, ECL, stage and capital on the corporate book, by severity
  ladder      the calibrated Deal Desk Stress Lab ladder (the R12 tier rule reads it)
  publish     the calibration, joint scenarios, satellite models and the ladder to Data Domains
  chat        What-If answers: headline by severity, evidence, "what this data cannot tell us"
  memo        the house-style Word methodology memo
  tiers       the tier distribution across the demo deals, before and after

Every number traces to a data window and a method (N5). Nothing here calls a model: every text has a
deterministic writer (N3).
"""
from __future__ import annotations

ENGINE = "scenario-engine"
VERSION = "r13-s1"
