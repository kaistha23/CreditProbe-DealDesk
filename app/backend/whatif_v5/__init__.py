"""v5 What-If (PLAN_R2 item 6): conversational scenarios on the What-If IFRS 9 domain.

  domain/   the What-If data domain (facility/account x every period, term structures by
            scenario and year, reconciled to the books' ECL) and the Saudi MEVs
  models/   the engine, the Delta method, the XGBoost method, exact Shapley attribution, model cards
  chat/     the conversational thread: a fork of the Cockpit's architecture re-keyed to What-If
  api.py    the service on port 8503

Built on the 5318 What-If design (sources/b360) and the Cockpit's conversational architecture,
neither imported. Read-only over the books and the Early Warning store.
"""
