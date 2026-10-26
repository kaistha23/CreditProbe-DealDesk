"""PLAN_R13 §I Session IC: network and events (R14 backlog items 8, 9, 10).

  events.py     event translator: a shock -> drivers -> borrowers hit (direct, suppliers, employers) -> ECL and Stage 2
                (What-If engine) -> who to call
  contagion.py  if a named borrower fails: second-order exposure through guarantees, shared collateral, group,
                suppliers and customers, and contractors paid by the same project employer
  employer.py   bank exposure to a project employer held through every contractor it pays
  common.py     the readers, appetite, lineage and the computed-view publisher shared by the three
  writer.py     the deterministic writers (N3): every sentence is composed from numbers, the model only polishes
  api.py        one route each, under /api/v1/intel/network (mounted on the Borrower 360 app)
"""
