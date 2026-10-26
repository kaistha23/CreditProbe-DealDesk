# UAT sweep: 5/5 steps passed, 256 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T18:16:08.344185+00:00 · 249 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | corporate | R2-7 | Borrower 360 Relationships: the graph renders with nodes and edges for 28 borrowers across all 14 sectors, equal to the API | 170/170 | 0 | PASS |
| 2 | corporate | R2-7 | Relationships of CB01312: legend toggles, two steps, click a name, Back, Excel export | 18/18 | 0 | PASS |
| 3 | corporate | R2-7 | Relationships: the analytics beside the graph equal the API (group against CP-1.2, concentration, contagion, collateral, guarantees) | 22/22 | 0 | PASS |
| 4 | corporate | R2-7 | Borrower 360: every chart on every tab has data (three borrowers) | 35/35 | 0 | PASS |
| 5 | retail | R2-7 | Retail Borrower 360: household and employer links, equal to the API; click the employer, Back | 11/11 | 0 | PASS |
