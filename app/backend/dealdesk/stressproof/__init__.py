"""R14 Session F: the Deal Desk flow after Review (PLAN_R14 "f", K20 K21 K23 K24 K25 K35).

    structures      the structure set: Ask, Recommended (the Review counter-proposal), Alternatives (the optimiser),
                    Your structures (saved by the user, and stress-proofed ones), each with base RAROC, SVA, DSCR,
                    covenant headroom, capacity check and approval; one selected structure per deal (dd_structure_set)
    matrix          one stress run over the selected structures: structures x mild / moderate / severe on the deal's
                    relevant drivers in the current regime (the R12 ladder, never a copy of it)
    solver          stress-proofing: the smallest change set that survives a target severity (dd_stress_proof)
    interpret       the deterministic interpreter text (what breaks first, why, what the proofed version changes and costs)
    recommendation  the Recommendation step content (never blank: default the Review counter-proposal)
    pipeline_lines  the pipeline test on the selected structure, read on this deal's own lines
    monitoring      Propose for monitoring + the Monitoring page (maker-checker; dd_monitoring_proposal)
    adapters        one engine per fact (N2): approval authority, SVA basis and capacity from Session E's engines when
                    present, else the R13 engines with the same output shape; the current regime from Session M
"""
