# Deal Desk demo pack (PLAN_R6 D3)

Synthetic Saudi credit applications for the CreditProbe Deal Desk demo. **Not client data.** Group members use real connected-group IDs and names from the synthetic corporate book (2026Q2), so the analysis shows connected exposure and group-limit effects.

Each case comes as a long-form Word credit memo (`…_LongForm.docx`: executive summary, background, group structure, management, industry, 3-year financials, facility, security, covenants, risk assessment and recommendation, appendix) and a short-form Excel sheet (`…_ShortForm.xlsx`: one labelled cell per field). Upload either through **Deal Desk → New proposal → Upload a memo**. The extraction summary says how many fields were read; fields a file states as "None offered" count as not read.

| Case | Obligor | Group | What it shows |
|---|---|---|---|
| DD-201 | Al Khobar Modern Logistics Company | Al Khobar Modern Logistics Group (CG9317-006) | Clears easily |
| DD-202 | Rawabi Industrial Works Fabrication Company | Rawabi Industrial Works Group (CG1277) | Breaches the SAR 500m connected-group limit |
| DD-203 | Najd Central Engineering Contracting Company | Najd Central Engineering Group (CG6292-119) | Below the 16% hurdle unsecured (about 15%), no security or covenants stated: the thread asks for them; SAR 45m of real-estate collateral or a 100% BBB corporate guarantee lifts it to about 16.5–17% |
| DD-204 | Tabuk Dates Processing Company | New to bank | Clears comfortably |
| DD-205 | Jazan Cold Chain Services Company | New to bank | Ijara with no underlying asset: fails the structure rule |
| DD-206 | Tuwaiq Modern Properties Development Company | Tuwaiq Modern Properties Group (CG3425-011) | Real-estate sector appetite and connected-group breaches |
| DD-207 | Taif First Logistics Company | Taif First Logistics Group (CG9317-018) | Just below the hurdle; revolving facility |
| DD-208 | Qassim Specialist Healthcare Company | New to bank | Kafalah guarantee carries a BB- obligor |
| DD-209 | Wadi Hanifah Technologies Company | Wadi Hanifah Technologies Group (CG1191-011) | Performance LG with a 20% cash margin |

Regenerate and test end to end (extract every file, create the proposal, run the engine): `.venv/bin/python ops/make_dealdesk_demo.py --check`. The last run's output is in `CHECK.txt`.

Anne's local session copies this folder into her launchers folder as `CreditProbe_Demo_Inputs/`.
