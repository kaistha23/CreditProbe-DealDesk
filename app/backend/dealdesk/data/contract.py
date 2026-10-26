"""Write docs/v5/R12_DATA_CONTRACT.md from schema.py (python3 -m backend.dealdesk.data.contract)."""
from __future__ import annotations

import pathlib

from backend.dealdesk.data import schema as S

V5 = pathlib.Path(__file__).resolve().parents[3]
OUT = V5 / "docs" / "v5" / "R12_DATA_CONTRACT.md"

HEAD = """# R12 data contract (Session E)

**Generated from `backend/dealdesk/data/schema.py`** by `python3 -m backend.dealdesk.data.contract`; do not edit by hand.
PLAN_R12 §0: every business fact is read from a relation registered in Data Domains through the shared readers, and
every decision is published back as a relation.

## How to read and write

```python
from backend.dealdesk.data import dd_read, dd_frame, publish, trace

dd_read("dd_document", proposal_id="R12-TWA", status=["pending", "expired"])   # list[dict], json columns parsed
dd_frame("bureau_cbrbr", proposal_id="R12-TWB")                               # pandas DataFrame
dd_read("rel_group_quarter", borrower_id="CB00001")                           # any registered relation works
publish("dd_review_finding", rows, mode="upsert", actor="B")                 # new version, manifest updated
trace("dd_document", row)   # {"domain", "relation", "key", "period", "version"} for (i) / Trace / Open in Data Domains
```

- `dd_read(relation, columns=None, parse_json=True, **filters)`: a filter is equality (scalar), membership (list, tuple,
  set) or `None` (is null). Unknown relations raise `KeyError`; an R12 relation not yet written reads as empty.
- `publish(relation, rows, mode="upsert"|"append"|"replace"|"replace_where", actor=..., where=None)`: only the relations below.
  `replace_where` drops the rows matching `where` (e.g. `{"proposal_id": "R12-TWA"}`) and adds yours: use it when you
  recompute one deal's findings, SWOT or stress results, so the rows Session E seeded for that deal are replaced. Rows are conformed
  to the contract (unknown columns raise `SchemaError`, missing ones are null, types coerced); `reporting_quarter`
  defaults to the as-of; `rel_version` and `published_at` are stamped. Upsert replaces rows with the same key. Each
  publish increments the version in the folder manifest (rows, columns, sha, last 50 history entries) and archives
  the previous parquet under `var/dealdesk/r12_history/<relation>/v<n>.parquet`.
- Tests set `DEALDESK_R12_ROOT` to a scratch copy of the checkout's `data/` so they never write committed files
  (see `backend/tests/test_r12_lineage.py`, fixture `r12_root`).
- Types: text, int, float, flag (0/1 integer), date (ISO `YYYY-MM-DD` text), ts (ISO UTC timestamp text), json (JSON
  text; `dd_read` parses it).
- Every relation ends with the lineage columns `reporting_quarter`, `rel_version`, `published_at`.
- Amounts in R12 demo deals are SAR million (the Deal Desk engine's currency), labelled `_mn`.

## Shared schemas other sessions write

| Relation | Writers | Use |
|---|---|---|
| `dd_review_finding` | B (review), C (governance and conduct flags), D (stress), I (book) | one row per finding; `review_point` 1..12, `severity`, evidence as relation + key + value, `rating_notch`, links to `condition_id` / `query_id` |
| `dd_monitoring_plan` | D at approval, I on a tier change | tier High / Medium / Standard from the stress verdict, `drivers`, `named_triggers` (json list of {metric, operator, threshold, label}), `ews_threshold_overrides` (json object), review frequency; a change writes a new active row and marks the old one superseded |
| `dd_condition` | B, D, I | conditions with status, due, trigger; `source = prior_approval` rows are the earlier conditions and their compliance |
| `dd_workflow_event`, `dd_query`, `dd_document` | U, B | workflow history, RM queries, the document checklist |
| `dd_stress_*`, `dd_swot`, `dd_promise`, `dd_raroc_drift`, `dd_policy*`, `dd_parameter_provenance` | D, T, C, I, G | as described per relation |

## Who reads what

| Session | Reads | Writes |
|---|---|---|
| U shell | `dd_deal` (landing cards: workflow_state, product, committee_date), `dd_workflow_event`, `dd_document` (badge), `dd_condition` (due), `deals.get` | `dd_workflow_event` (`bridge.publish_workflow`) |
| B review | `dd_financials_detail` (adjusted ratios, ageing, auditor), `bureau_*`, `other_bank_facility`, `dd_condition` (prior_approval), `dd_promise`, `b360_insider_link`, `dd_document_rule`, `dd_security`, `dd_tnc` | `dd_review_finding`, `dd_query`, `dd_document`, `dd_condition` |
| C group | `rel_*` (book borrowers), `b360_*` (R12 deals), `dd_group_exposure`, `dd_deal.group_cap_*`, `dd_account_conduct` / `dep_month`, `dd_returned_cheque`, `bureau_cbrbr` | `dd_review_finding` (governance, conduct), `dd_swot` |
| D stress | `dd_stress_scenario`, `dd_stress_sensitivity`, `dd_project_cashflow`, `dd_business_profile` (deal facts) | `dd_stress_result`, `dd_monitoring_plan` (`bridge.publish_monitoring_plan`), `dd_stress_scenario` (editor) |
| F papers | every relation in the product template's `relations` (`products/templates.py`), `dd_reference`, `dd_business_profile` | — |
| G parameters | `dd_policy`, `dd_policy_clause`, `dd_parameter_provenance` | the same |
| I book | `dd_raroc_drift`, `dd_promise`, `dd_monitoring_plan`, `dd_condition`, `orig_facility`, `cls_exposure`, `ecl_facility` | `dd_raroc_drift`, `dd_promise`, `dd_monitoring_plan` |
| P products | `dd_project`, `dd_project_cashflow`, `dd_syndication`, `dd_escrow_account`, `dd_escrow`, `dd_sme_application`, `dd_facility_limit` | — |
| T calibration | `dd_obligor_financials`, `dd_financials_detail`, book relations | `dd_stress_sensitivity` (new versions) |

## The R12 demo deals (all fictional)

| proposal_id | Deal | Product |
|---|---|---|
| R12-TWA | Twin A: Al Sahel Building Materials Group, trading group renewal | corporate (trade) |
| R12-TWB | Twin B: Gulf Meridian Contracting, new project limit (employer Saadiyat Crest Developments) | contracting |
| R12-SYN | Najd Petrochem Syndicate Participation | syndicated |
| R12-ESC | Marina Vista Off-plan Escrow | escrow |
| R12-SME1..3 | Three SME fast-track applications | sme |

Seeded rows that writers will replace: `dd_review_finding` (`E-…` ids, prior-review findings), `dd_swot` (R12-SYN),
`dd_stress_result` (the rating −1/−2/−3 family per R12 deal, engine-computed), `dd_monitoring_plan` (twin A's 2025 plan),
`dd_raroc_drift` (twin A), `dd_condition` (earlier approval conditions, `source = prior_approval`).

Product templates: `backend/dealdesk/products/templates.py` (`for_deal(pid)`, `applies(pid, kind, item)`).
Lineage and no-side-door harness: `backend/tests/test_r12_lineage.py` (add cases to `LINEAGE_CASES`, `SCOPED_SOURCES`,
`RUNTIME_CASES`), helpers in `backend/dealdesk/data/lineage.py` (`figure`, `untraced`, `watch_opens`, `side_doors`).
Rebuild the data: `python3 -m backend.dealdesk.data.build` (`--check` compares with the committed manifests).

`dd_deal` lists every deal (DD-01..15, PL-01..27, R12-*) with its product template; `backend.dealdesk.data.deals.get(pid)`
returns the engine-ready proposal record for any of them.

"""


def build() -> str:
    out = [HEAD]
    doms = {}
    for rid, s in S.RELATIONS.items():
        doms.setdefault(s["domain"], []).append(rid)
    out.append("## Borrower 360 (now live)\n\nRegistered as-is from `data/relationships/rel-saudi-v1` (read-only, built by "
               "`backend/rel_domains/build.py`; columns in its manifest):\n\n| Relation | Keys | Period | Meaning |\n|---|---|---|---|\n")
    for k, v in S.B360_EXISTING.items():
        out.append(f"| `{k}` | {', '.join(v['keys'])} | {v['period'] or '—'} | {v['description']} |\n")
    out.append("\n")
    titles = {"deal_desk": "Deal Desk (extended)", "deal_desk_products": "Deal Desk products (new domain)",
              "bureau": "Bureau (additions)", "borrower_360": "Borrower 360 (new relations)",
              "governance": "Governance (R13 IE, new domain; fictional history)"}
    for dom in ("deal_desk", "deal_desk_products", "bureau", "borrower_360", "governance"):
        out.append(f"## {titles[dom]}\n\n")
        for rid in doms.get(dom, []):
            s = S.RELATIONS[rid]
            out.append(f"### `{rid}` — {s['label']}\n\n{s['description']}\n\n- File: `{s['folder']}/{rid}.parquet`\n"
                       f"- Keys: {', '.join(s['keys'])} · Period: `{s['period']}` · Grain: {s['grain']}\n"
                       f"- Owner: {s['owner']} · Writers: {s['writers']}\n\n| Column | Type | Unit | Meaning |\n|---|---|---|---|\n")
            for n, t, u, d in S.columns(rid):
                out.append(f"| `{n}` | {t} | {u} | {d.replace('|', '/')} |\n")
            out.append("\n")
    return "".join(out)


def main() -> int:
    OUT.write_text(build())
    print(f"contract -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
