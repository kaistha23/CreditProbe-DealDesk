"""Noor's brief agent (PLAN_R12 §2, N1; R11_FEEDBACK I11–I13): one ranked, role-based brief from every source, with
Why? / What should we do? / Send to committee. Deterministic (N6); the model only polishes the opening with a key.

Not an agents-runtime agent: the brief is a read across the other agents' outputs and Data Domains, so it is served by
`backend.agents_v5.brief.api.router` (mounted on the Deal Desk service in its `# R12 routers` block).
"""
