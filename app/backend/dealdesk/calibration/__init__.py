"""R12 Session T (I19-2): sector revenue sensitivities to oil and non-oil GDP, estimated from the bank's own
borrower financials history in Data Domains, with confidence bands, R², n and a model card.

    from backend.dealdesk.calibration import sensitivity
    est = sensitivity.estimate()          # every sector x driver, calibrated or expert fallback (flagged)
    sensitivity.publish_version(est)      # dd_stress_sensitivity "calibrated v1" through Session E's publisher
"""
