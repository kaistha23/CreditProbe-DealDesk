# Bank-form proposal: gap audit (R14 session p, K26 / K27)

19 Oct 2026, 18:10 UTC. Compares what the R12/R13 bank-form writer (`backend/dealdesk/house_style/bankform/`, "More → Write proposal", I25)
produced on `v5/r14-base` for twin A (R12-TWA), twin B (R12-TWB) and DD-06 with the anatomy of the two bank proposals Anne shared
(`docs/v5/house_style/PROPOSAL_ANATOMY.md`). No name or figure from the originals is used; the feature is called the "bank-form proposal".

Method: `paper.write(pid)` → `render.docx` → LibreOffice PDF → page images; every section read against anatomy §2 (skeleton), §3 (voice)
and the K26/K27 rows. Baseline: twin A 18 pages, twin B 20, **DD-06 9** (target 15–25).

## A. Whole-document gaps (layout, voice, feed)

| # | Anatomy / K26 asks | R13 output | Gap → fix in R14 |
|---|---|---|---|
| A1 | Header block on **every page** (customer, CIF, group, date, rating, request ticks) | House-style cover page, then the header block once as section 1; running header is the generic CreditProbe band | No cover page; page 1 opens with the full header block; a compact header block (customer · CIF · group · date · request · rating · ref) repeats in the Word page header and the PDF page frame on every page |
| A2 | Two voices: Action requested (business) → Credit division comments → Credit division recommendation → CRO / committee | One flat numbered list of 26 sections; voice only in metadata | Four ruled part banners: **ACTION REQUESTED (Business)**, **CREDIT DIVISION COMMENTS**, **CREDITPROBE ANALYSIS (independent re-performance)**, **CREDIT DIVISION RECOMMENDATION**, **APPROVALS**; voice label on each section in the preview |
| A3 | Facilities table landscape, full width | Portrait, 6 columns, particulars squeezed | Facilities (section 3) on its own **landscape** page: limit / sub-limit, product, existing, outstanding, proposed, cash margin, commission, benchmark + spread, floor, tenor / validity, repayment, particulars; totals row; study fee line |
| A4 | Ruled boxes; bold / underlined key concerns | Plain paragraphs; `**bold**` only | Action requested and the recommendation sit in ruled boxes; key concerns (critical / high findings, not complied conditions, unperfected security, contradicted claims) are **bold and underlined** (`__text__` markup in the content model; Word and PDF honour it) |
| A5 | Signature blocks: analyst / senior manager, VP credit, CCO; CRO comments box; committee instructions box with authority | Present but authority from `dd_deal.approval_authority` text or a local threshold table (a second DoA, breaks N2) | Signature grid with name lines prefilled (analyst from `dd_deal.credit_analyst`); authority from the **one DoA engine** (session e's `approval_authority(deal, structure)` through an adapter; fallback = the Deal Desk engine's `approval.level` on the selected structure, labelled) with the rule and reasons |
| A6 | Fed by the **selected structure** (K23/K25) and the whole deal file | Fed by the ask (`dd_proposal`/`dd_deal`) and the optimiser's closest structure; the selected structure is unknown | New `bankform/feed.py`: the selected structure (f's API when present; else the Review counter-proposal = optimiser closest, labelled "default: Review counter-proposal") drives action requested, the recommendation, the RAROC/SVA section, stress and the approval authority |
| A7 | Every sentence a fact, a number and a date; attribution; "information not provided" | Voice validator passes 258/258 sentences on twin A; but some lines print raw data (`revenue {'default': 0.0, 'by_sector': {...}}%` in section 16), lower-cased bank names ("We note that peninsula Trade Bank"), and a wrong verb ("Pricing **clears** the hurdle: RAROC 14.5% against a 15.0% hurdle") | Fix the three writer bugs; validator extended: no `{`/`}` or `_` identifiers in prose |
| A8 | Length and density 15–25 pages | 18 / 20 / **9** pages | DD-06 (an R11 deal with thin relations) gets its sections from the proposal record and the engines (facilities from the ask lines, security, covenants, conduct from the book, stress matrix, alternatives); landscape facilities and per-page header; target 15–25 on all three |
| A9 | Preview, Word, PDF; every figure traced | Word / PDF / Markdown download only (More → Write proposal); figures traced in `papers/figures` | On-screen **paginated preview with a section navigator** (pages as in the Word, section list with voice, gaps and source chips), Word and PDF from the same content model; the button "Prepare the credit proposal" on the Recommendation step |
| A10 | CreditProbe's own sections | RAROC/SVA "not available" on twin A (dd_result empty; engine fallback failed without the What-If domain); forward risk not available | RAROC/SVA from session e's economics engine (one basis, labelled) via adapter, fallback the Deal Desk engine on the selected structure; P(Stage 2) / ECL; precedent; stress on the selected structure **and the severity it was proofed to** (f's stress-proof result, adapter); pipeline fit |

## B. Section by section

| § | Anatomy | R13 output (twin A unless stated) | Gap → R14 |
|---|---|---|---|
| 1 Header block | 16 fields incl. ticks, codes, ratings | 16-field 2-column grid, once | Same grid on page 1 (4 columns, denser) + compact header every page (A1); DD-06: 6 fields "not available" → filled from `dd_deal` (cif, group_no, ao/ro, codes) where present, else "information not provided" |
| 2 Action requested | One paragraph naming every ask with the previous committee ref | Present (3 sentences) | Ruled box; names the **selected structure** ("as structured in the selected structure *Recommended*: amount, tenor, margin, cash margin") and the group cap change; DD-06 "previous committee reference not provided" kept as an explicit line |
| 3 Facilities table | Per limit / sub-limit; existing, outstanding, proposed, cash margin, particulars (commission, validity, benchmark + spread with floor, tenor, repayment); totals; study fee | 6 columns portrait, particulars merged | Landscape, 12 columns (A3); selected structure's terms replace the ask's where they differ, marked "▲ changed by credit"; fee line |
| 4 Security and support | Per limit group; guarantees with NW statement date; perfection deadline | Present per limit group | Perfection status as a column table per group (provider, kind, amount, NW and date, status, deadline, legal opinion age); **unperfected / pending underlined** |
| 5 Terms and conditions | Numbered per limit group, status of existing conditions | Present, numbered; "Status of existing conditions" table | "Not complied" underlined; conditions from the selected structure's covenants (thresholds and headroom) appended per group; DD-06: covenants from the proposal record instead of "not provided" |
| 6 Group exposure and references | Funded / total, cap, references | Present | Cap test line (exposure after deal vs cap, headroom %) |
| 7 Background | Licence, shareholders table, parent, ownership changes, entities, activity mix, sales / purchase terms, staff | Present (tables) | — (kept); DD-06: "information not provided" per missing item, named |
| 8 Relationship | Since when, turnover, average balance, limit history, utilisation vs cap, past dues, returned cheques | Present with monthly table | Returned cheques in 12 months summarised in one underlined line when > 0 |
| 9 Financed projects | Per project table + paragraph | Twin B present; twin A "not applicable" line | — |
| 10 CBRBR | Table subject + related | Present | — |
| 11 Credit bureau | Per entity and UBO; reports not provided | Present | Missing UBO reports underlined |
| 12 Other banks | Matrix + reconciliation | Present | Gap lines underlined when not clarified |
| 13 New project | Project details, cash flow, employer | Twin B present | — |
| 14 Financials | Auditor, opinion, basis; 3 years + interim; subject / combined / parent | Present (tables) | Landscape when > 5 columns |
| 15 Financial synopsis | Bullets with PY in brackets; **adjusted** NW / leverage / WC | Present incl. financial-quality block (R13 Q) | Adjusted figures in a small "reported → adjusted" table |
| 16 Geopolitical | Effects on routes, ports, input costs, labour | Lists every bank scenario with raw shock dicts (bug) | **Current regime** block (session m's regime when present; else the latest MEV / Brent in Data Domains, dated) + the 2–3 scenarios relevant to the deal's sector in words + business's own statement or "not provided" |
| 17 Exceptions and observations | Each exception with business's reason; observations | Present; verb bug; long unordered list | Exceptions numbered with reason; observations ordered by severity, critical/high underlined; capped at 15 with "n more in the findings register" |
| 18 Key strengths | 3–4 bullets | 4 bullets from dd_swot, sourced | — (kept; capped at 4) |
| 19 Recommendation | Numbered decisions, group exposure, security, CP "prior to limit loading", undertakings, monitoring duties | Present (4 decisions + 24 conditions on twin A); not from the selected structure | Decisions from the **selected structure**; authority + rule (A5); findings and their cures; monitoring tier and triggers with owners and dates; ruled box |
| 20 Signatures | Analyst / SM, VP credit, CCO; CRO; committee | Present | A5 |

## C. Acceptance (tests in `tests/v5/house_style/test_r14_proposal.py`)

All 20 sections on R12-TWA, R12-TWB and DD-06; no section without either content or an explicit "information not provided" line;
RAROC / SVA / authority equal the engines' values for the selected structure; 15–25 pages (LibreOffice); header on every page
(Word header part present; PDF page frame); facilities section landscape; no raw dict / identifier text in prose; deterministic
(same JSON twice, timestamps excluded).
