# UAT sweep: 62/62 steps passed, 462 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T18:11:12.096058+00:00 · 189 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | corporate | D | Sidebar → Borrower 360; book toggle; search | 7/7 | 0 | PASS |
| 2 | corporate | D | Borrower 360 CB01045: tab profile | 4/4 | 0 | PASS |
| 3 | corporate | D | Borrower 360 CB01045: tab facilities | 7/7 | 0 | PASS |
| 4 | corporate | D | Borrower 360 CB01045: tab exposure | 5/5 | 0 | PASS |
| 5 | corporate | D | Borrower 360 CB01045: tab ratings | 8/8 | 0 | PASS |
| 6 | corporate | D | Borrower 360 CB01045: tab stage-dpd | 5/5 | 0 | PASS |
| 7 | corporate | D | Borrower 360 CB01045: tab collateral | 5/5 | 0 | PASS |
| 8 | corporate | D | Borrower 360 CB01045: tab covenants | 5/5 | 0 | PASS |
| 9 | corporate | D | Borrower 360 CB01045: tab financials | 5/5 | 0 | PASS |
| 10 | corporate | D | Borrower 360 CB01045: tab group | 5/5 | 0 | PASS |
| 11 | corporate | D | Borrower 360 CB01045: tab relationships | 4/4 | 0 | PASS |
| 12 | corporate | D | Borrower 360 CB01045: tab ews | 8/8 | 0 | PASS |
| 13 | corporate | D | Borrower 360 CB01045: tab bureau | 5/5 | 0 | PASS |
| 14 | corporate | D | Borrower 360 CB01045: tab open-banking | 5/5 | 0 | PASS |
| 15 | corporate | D | Borrower 360 CB01045: tab notes | 4/4 | 0 | PASS |
| 16 | corporate | D | Borrower 360 CB01045: Export all tabs, then browser Back through the tabs | 18/18 | 0 | PASS |
| 17 | corporate | D | Borrower 360 → Back to Early Warning (this customer) | 3/3 | 0 | PASS |
| 18 | retail | D | Sidebar → Borrower 360; book toggle; search | 7/7 | 0 | PASS |
| 19 | retail | D | Borrower 360 RC023173: tab profile | 4/4 | 0 | PASS |
| 20 | retail | D | Borrower 360 RC023173: tab facilities | 7/7 | 0 | PASS |
| 21 | retail | D | Borrower 360 RC023173: tab exposure | 5/5 | 0 | PASS |
| 22 | retail | D | Borrower 360 RC023173: tab ratings | 8/8 | 0 | PASS |
| 23 | retail | D | Borrower 360 RC023173: tab stage-dpd | 5/5 | 0 | PASS |
| 24 | retail | D | Borrower 360 RC023173: tab collateral | 5/5 | 0 | PASS |
| 25 | retail | D | Borrower 360 RC023173: tab financials | 5/5 | 0 | PASS |
| 26 | retail | D | Borrower 360 RC023173: tab group | 4/4 | 0 | PASS |
| 27 | retail | D | Borrower 360 RC023173: tab relationships | 4/4 | 0 | PASS |
| 28 | retail | D | Borrower 360 RC023173: tab ews | 8/8 | 0 | PASS |
| 29 | retail | D | Borrower 360 RC023173: tab bureau | 5/5 | 0 | PASS |
| 30 | retail | D | Borrower 360 RC023173: tab open-banking | 5/5 | 0 | PASS |
| 31 | retail | D | Borrower 360 RC023173: tab notes | 4/4 | 0 | PASS |
| 32 | retail | D | Borrower 360 RC023173: Export all tabs, then browser Back through the tabs | 17/17 | 0 | PASS |
| 33 | retail | D | Borrower 360 → Back to Early Warning (this customer) | 3/3 | 0 | PASS |
| 34 | corporate | W1 | Sidebar → What-If; book toggle; chat box on top, library below | 6/6 | 0 | PASS |
| 35 | corporate | W2 | Ask: PD +30% for Construction → proposal (nothing runs) → Execute → which model → Delta method | 12/12 | 0 | PASS |
| 36 | corporate | W3 | Chip: rerun with XGBoost → side by side | 4/4 | 0 | PASS |
| 37 | corporate | W4 | Intensify, stack, likelihood | 7/7 | 0 | PASS |
| 38 | corporate | W5 | Custom shocks panel (structured editor) as a new scenario | 3/3 | 0 | PASS |
| 39 | corporate | W6 | Save; Word report (5 pages); Excel; Add to report | 11/11 | 0 | PASS |
| 40 | corporate | W7 | ← What-If; the saved scenario is in the repository; the pack is listed | 5/5 | 0 | PASS |
| 41 | corporate | W8 | Library: a standard scenario opens a thread that describes it, then its impact; Back | 5/5 | 0 | PASS |
| 42 | corporate | W9 | Model cards: Delta and XGBoost, every section; Back | 13/13 | 0 | PASS |
| 43 | corporate | W10 | Conversation: collateral is a lever; the mechanics question is answered from the book; Execute; Back | 10/10 | 0 | PASS |
| 44 | retail | W1 | Sidebar → What-If; book toggle; chat box on top, library below | 6/6 | 0 | PASS |
| 45 | retail | W2 | Ask: PD +30% for Auto Finance → proposal (nothing runs) → Execute → which model → Delta method | 12/12 | 0 | PASS |
| 46 | retail | W3 | Chip: rerun with XGBoost → side by side | 4/4 | 0 | PASS |
| 47 | retail | W4 | Intensify, stack, likelihood | 7/7 | 0 | PASS |
| 48 | retail | W5 | Custom shocks panel (structured editor) as a new scenario | 3/3 | 0 | PASS |
| 49 | retail | W6 | Save; Word report (5 pages); Excel; Add to report | 11/11 | 0 | PASS |
| 50 | retail | W7 | ← What-If; the saved scenario is in the repository; the pack is listed | 5/5 | 0 | PASS |
| 51 | retail | W8 | Library: a standard scenario opens a thread that describes it, then its impact; Back | 5/5 | 0 | PASS |
| 52 | retail | W9 | Model cards: Delta and XGBoost, every section; Back | 13/13 | 0 | PASS |
| 53 | retail | W10 | Conversation: collateral is a lever; the mechanics question is answered from the book; Execute; Back | 10/10 | 0 | PASS |
| 54 | both | C | Sidebar → Data Builder; domains grouped | 10/10 | 0 | PASS |
| 55 | both | C | Data Builder cockpit/corp_borrower_quarter: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 56 | both | C | Data Builder ews/corp_exposure: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 57 | both | C | Data Builder bureau/bureau_retail_month: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 58 | both | C | Data Builder open_banking/openbanking_retail_month: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 59 | both | C | Data Builder deal_desk/dd_proposal: rows, dictionary, search, filter, compare, exports, Back | 12/12 | 0 | PASS |
| 60 | both | C | Data Builder what_if/whatif_corporate: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 61 | both | C | Data Builder scorecard/RET-APP: rows, dictionary, search, filter, compare, exports, Back | 13/13 | 0 | PASS |
| 62 | both | C | Data Builder branches/branch_corporate_quarter: rows, dictionary, search, filter, compare, exports, Back | 11/11 | 0 | PASS |
