# Proposal review rule book (R11 Session R)

`rules.json` is read by `backend/dealdesk/review_rules.py` on every review; add or change a rule here, no code change.
(`ops/r11_review_rules_build.py` wrote the first version; the JSON is the source of truth.)

## Rule fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | unique, e.g. `EXC-01` |
| `category` | yes | `data` · `consistency` · `policy` · `connected` |
| `title`, `tests` | yes | what is checked, in words |
| `scope` | no | `["case"]`, `["dd"]` or both (default both) |
| `inputs` | yes* | `{name: "dotted.path"}` into the review evidence (`review_facts.facts`): `case.*`, `ev.*`, `dd.*`, `obligor.*`, `ask.*`, `fin.<year>.*`, `book.*`, `conduct.*`, `metrics.*`, `covenants.*`, `collateral`, `connected`, `memo.<claim key>`, `subject.*`, `approved_auditors` |
| `optional` | no | input names that may be missing |
| `when` | no | precondition expression; if false, or its data is missing, the rule does not apply |
| `derive` | no | `{name: expression}` computed before the test, usable in the finding text |
| `expr` + `op` + `threshold` | one of | test `expr op threshold`; `op` in `<= < >= > == !=` |
| `assert` | one of | boolean expression; true = supported |
| `threshold` | | number, or `"param:<table>.<key>"` (`param:desk.<key>` = Admin → Deal Desk Parameters) |
| `threshold_input` | no | take the threshold from an input (e.g. the memo's covenant) |
| `on_fail` | yes | `contradicted` (data contradicts the memo) or `exception` (policy departure) |
| `severity` | yes | `critical` · `major` · `minor`; `severity_when: [{"if": expr, "severity": ...}]` grades it |
| `policy_ref`, `crm_article` | yes | bank policy clause; `CBUAE CRM Art. n` |
| `doa_rank` | no | Delegation of Authority rank (`params/v1/doa.json`) a failure needs |
| `claims` | no | memo claim keys (assertion ids in `claims.json`, or figure keys) the rule anchors to |
| `line_match` | no | regex on memo lines to mark |
| `finding`, `evidence`, `pass_text` | yes | wording; `{name}` and `{name:,.1f}` take inputs, derived names, `value`, `threshold` |
| `sources` | no | evidence source keys |
| `condition` | no | trigger on failure: `kind` (`CP`/`covenant`/`watch`), `what`, `source`, `due` (`YYYY-MM-DD`, `+60d`, `monthly`, `annual`, or text), `owner`, optional `inputs` + `check` (evaluated from data) |
| `lever` | no | counter-proposal lever: `cap`, `tranche_funded`, `cash_margin`, `drop_line`, `routing`, `no_new_funded`, `advance_payment`, `cp`, `optimise` (see `packages.json`) |
| `type: "ledger"` + `map` | alt | compare every memo figure whose key matches `map[].claim` (regex) with `map[].fact` (path; `{0}` = regex groups) |

Expressions: arithmetic, comparisons, `and/or/not`, list comprehensions, subscripts and the functions
`days months min max abs sum len any all round lower contains year float bool isnull sqrt str sorted join`.

Other files: `claims.json` (assertion patterns for the claims ledger), `packages.json` (counter-proposal packages),
`precedent.json` (precedent matching), `evidence/<case>.json` (bank evidence for the prepared cases),
`approved_auditors.json`.
