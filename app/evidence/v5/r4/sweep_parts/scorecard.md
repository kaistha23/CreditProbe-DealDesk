# UAT sweep: 9/9 steps passed, 132 checks

UI http://127.0.0.1:5500 · API http://127.0.0.1:8501 · 2026-10-11T17:59:41.828051+00:00 · 47 s

| # | Book | UAT step | Step | Checks | Errors | Result |
|---|---|---|---|---|---|---|
| 1 | scorecard | S2-1 | Sidebar → Scorecard Validation: chat box on top, past validations below | 9/9 | 0 | PASS |
| 2 | scorecard | S2-2 | Open the SME validation: every tab, red / amber / green verdicts against stated thresholds, Plotly charts and tables | 62/62 | 0 | PASS |
| 3 | scorecard | S2-3 | Downloads in the house style (Word, Excel), Share through Mail, and Back | 12/12 | 0 | PASS |
| 4 | scorecard | S2-4 | From the chat box: choose a scorecard, change the plan, run it, ask about the results | 12/12 | 0 | PASS |
| 5 | scorecard | S2-4b | Conversation (PLAN_R4 A2): diagnosis in priority order; Gini by segment; PSI for one variable; overrides | 8/8 | 0 | PASS |
| 6 | scorecard | S2-5 | Review: record the conclusion; the Word report carries it; reopen from the home; Back | 11/11 | 0 | PASS |
| 7 | scorecard | S2-6 | Choose from the cards; a Mail or Playbook link (?validation=) opens the thread; an unknown thread is refused cleanly | 6/6 | 0 | PASS |
| 8 | scorecard | S2-7 | People: a persona sees the seeded validations and its own conversations; others do not; view-as is read only | 9/9 | 0 | PASS |
| 9 | scorecard | S2-8 | The sweep leaves the library as seeded: one validation per scorecard | 3/3 | 0 | PASS |
