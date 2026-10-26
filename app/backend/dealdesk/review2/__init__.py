"""PLAN_R12 Session B: the full credit review (I16, 12 points plus the R12 additions), documents (I26) and RM queries (I17).

Modules:
  source      the deal file every check reads: one adapter over the Data Domains readers (backend.dealdesk.data),
              each figure tagged with its relation, key and period (PLAN §0)
  analytics   adjusted ratios, receivables quality, auditor quality, bureau and other-bank matrix with reconciliation,
              status of earlier conditions, insider and staff links
  points      the 12 review points, each with its checks, status and findings
  findings    findings by severity with evidence; the dd_review_finding schema; publish
  queries     RM queries through Mail, replies threaded back (dd_query)
  opinion     the quality score and the reviewer opinion in the credit voice (deterministic writer, N6)
  workspace   review(), preflight()
  publish     the bridge to E's publisher
  api         the HTTP routes (one include_router line in api.py)
"""
