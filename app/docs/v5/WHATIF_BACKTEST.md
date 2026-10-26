# What-If accuracy back-test

Relation `whatif_backtest` (version 1, 19 rows). Produced by `python -m backend.whatif_v5.backtest` (deterministic; PLAN_R14 §m (7)).

## What is measured

What-If Delta method at quarter t with the macro moves realised to t+1 (Brent, non-oil GDP, SAIBOR; one-year shock) against the full engine's final ECL at t+1 on the facilities present in both quarters; naive = ECL held at t.

## Result

Back-tested on 19 quarter-to-quarter steps over 20 quarters, the What-If estimate of the corporate book's ECL was within 10.0% of the full ECL engine on average (P95 17.3%, worst 19.2% in 2024Q3→2024Q4); holding the ECL flat misses by 10.4% on average.

| Statistic | What-If | Naive (ECL held) |
|---|---|---|
| Mean absolute error, % of actual ECL | 10.04% | 10.42% |
| P95 absolute error | 17.28% | 19.58% |
| Worst quarter | 19.21% (2024Q3→2024Q4, SAR +754.3m) | |
| Mean signed error (bias) | -6.21% | |
| Quarters where What-If beats naive | 12 of 19 | |

## By quarter

| From → to | Facilities | Brent move | Non-oil GDP move | SAIBOR move | ECL start (SAR m) | What-If estimate | Full engine | Error | Error % |
|---|---|---|---|---|---|---|---|---|---|
| 2021Q3 → 2021Q4 | 18,942 | +8.3% | +2.66 pp | -10 bps | 1,606.9 | 1,468.6 | 1,633.0 | -164.4 | -10.07% |
| 2021Q4 → 2022Q1 | 18,942 | +26.0% | +0.77 pp | +58 bps | 1,633.0 | 1,598.0 | 1,683.5 | -85.5 | -5.08% |
| 2022Q1 → 2022Q2 | 18,942 | +13.2% | +0.77 pp | +58 bps | 1,683.5 | 1,661.6 | 1,713.5 | -51.9 | -3.03% |
| 2022Q2 → 2022Q3 | 18,942 | -11.3% | +0.77 pp | +58 bps | 1,713.5 | 1,717.8 | 1,835.9 | -118.1 | -6.43% |
| 2022Q3 → 2022Q4 | 18,942 | -12.1% | +0.77 pp | +58 bps | 1,835.9 | 1,838.8 | 2,065.2 | -226.3 | -10.96% |
| 2022Q4 → 2023Q1 | 18,942 | -8.3% | -1.27 pp | +70 bps | 2,065.2 | 2,205.3 | 2,357.6 | -152.3 | -6.46% |
| 2023Q1 → 2023Q2 | 18,942 | -3.5% | -1.27 pp | +70 bps | 2,357.6 | 2,496.4 | 2,930.6 | -434.3 | -14.82% |
| 2023Q2 → 2023Q3 | 18,942 | +10.7% | -1.27 pp | +70 bps | 2,930.6 | 3,060.4 | 3,656.8 | -596.4 | -16.31% |
| 2023Q3 → 2023Q4 | 18,942 | -3.4% | -1.27 pp | +70 bps | 3,656.8 | 3,821.4 | 4,274.6 | -453.2 | -10.60% |
| 2023Q4 → 2024Q1 | 18,942 | -0.9% | -0.33 pp | +2 bps | 4,274.6 | 4,304.7 | 4,550.9 | -246.1 | -5.41% |
| 2024Q1 → 2024Q2 | 18,942 | +2.0% | -0.33 pp | +2 bps | 4,550.9 | 4,577.6 | 4,573.7 | +3.9 | +0.08% |
| 2024Q2 → 2024Q3 | 18,942 | -5.7% | -0.33 pp | +2 bps | 4,573.7 | 4,612.7 | 4,640.4 | -27.6 | -0.60% |
| 2024Q3 → 2024Q4 | 18,942 | -6.5% | -0.33 pp | +2 bps | 4,640.4 | 4,680.4 | 3,926.1 | +754.3 | +19.21% |
| 2024Q4 → 2025Q1 | 18,942 | +1.6% | -0.07 pp | -18 bps | 3,926.1 | 3,914.3 | 3,343.7 | +570.6 | +17.06% |
| 2025Q1 → 2025Q2 | 18,942 | -10.3% | -0.07 pp | -18 bps | 3,343.7 | 3,346.4 | 3,482.8 | -136.3 | -3.91% |
| 2025Q2 → 2025Q3 | 18,942 | +1.4% | -0.07 pp | -18 bps | 3,482.8 | 3,471.7 | 4,121.9 | -650.2 | -15.77% |
| 2025Q3 → 2025Q4 | 18,942 | -7.7% | -0.07 pp | -18 bps | 4,121.9 | 4,125.8 | 4,751.0 | -625.3 | -13.16% |
| 2025Q4 → 2026Q1 | 19,651 | +26.1% | -0.40 pp | +0 bps | 4,822.2 | 4,807.4 | 5,677.7 | -870.3 | -15.33% |
| 2026Q1 → 2026Q2 | 20,426 | +28.8% | -0.40 pp | +0 bps | 5,742.7 | 5,718.4 | 6,848.7 | -1,130.2 | -16.50% |

## What this back-test cannot tell us

- The full engine's ECL at t+1 also moves with rating migrations, staging and idiosyncratic defaults the macro drivers do not carry; the What-If is given only the macro moves, so the error includes everything else that happened to the same facilities over the quarter.
- 19 steps over one partial cycle (2021Q3–2026Q2): the statistics are indicative, not a validation sample.
- The corporate book only; the retail What-If (20 months) is not back-tested here.
