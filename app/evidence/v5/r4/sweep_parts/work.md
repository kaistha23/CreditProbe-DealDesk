# UAT sweep: 20/20 steps passed, 177 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T17:57:07.318980+00:00 · 84 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | both | S3-2 | Analyses: one card per item the API returns, the seeded ones included | 4/4 | 0 | PASS |
| 2 | both | S3-2 | Investigations: one card per item the API returns, the seeded ones included | 4/4 | 0 | PASS |
| 3 | both | S3-2 | Projects: one card per item the API returns, the seeded ones included | 4/4 | 0 | PASS |
| 4 | retail | S3-2 | Visibility: Omar (retail analyst) sees the retail project, not the corporate one | 4/4 | 0 | PASS |
| 5 | corporate | S3-2 | Analysis 'EAD by sector': question, answer and key figures as saved; Back | 10/10 | 0 | PASS |
| 6 | retail | S3-2 | Analysis 'Retail Stage 2 build': question, answer and key figures as saved; Back | 11/11 | 0 | PASS |
| 7 | corporate | S3-2 | Analysis 'What-If: oil -40%': question, answer and key figures as saved; Back | 13/13 | 0 | PASS |
| 8 | corporate | S3-2 | Analysis 'Construction ECL by sub-sector': question, answer and key figures as saved; Back | 10/10 | 0 | PASS |
| 9 | corporate | S3-2 | Refresh ead-by-sector-2026q2 to 2025Q4: before and after side by side, every figure equal to the API | 14/14 | 0 | PASS |
| 10 | retail | S3-2 | Refresh retail-stage2-build-2026-08 to 2026-05: before and after side by side, every figure equal to the API | 16/16 | 0 | PASS |
| 11 | corporate | S3-2 | Refresh whatif-oil-minus-40-corporate to 2025Q4: before and after side by side, every figure equal to the API | 20/20 | 0 | PASS |
| 12 | both | S3-2 | Investigation 'Construction ECL rise, Q2 2026': the whole conversation; Continue opens the source; Back | 6/6 | 0 | PASS |
| 13 | both | S3-2 | Investigation 'Retail risk build-up': the whole conversation; Continue opens the source; Back | 6/6 | 0 | PASS |
| 14 | corporate | S3-2 | Continue an investigation here: a turn added appears in its conversation | 4/4 | 0 | PASS |
| 15 | both | S3-2 | Project 'Construction sector deep-dive Q2 2026' as khalid.alotaibi: access, documents, threads; a thread answers in scope and refuses outside | 13/13 | 0 | PASS |
| 16 | both | S3-2 | Project 'Retail Stage 2 review' as omar.alghamdi: access, documents, threads; a thread answers in scope and refuses outside | 13/13 | 0 | PASS |
| 17 | corporate | S3-2 | What-If: Save as analysis (figures equal the What-If engine) and Save as investigation (every turn) | 8/8 | 0 | PASS |
| 18 | corporate | S3-2 | Early Warning: Save as investigation from the Construction level | 4/4 | 0 | PASS |
| 19 | both | S3-2 | Share an analysis through Mail (arrives in Sara's inbox); Share and Add to report open on investigations and projects | 8/8 | 0 | PASS |
| 20 | both | S3-2 | Back paths: analysis → Analyses, investigation → Investigations, project → Projects | 5/5 | 0 | PASS |
