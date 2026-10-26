# R12 stress sensitivity calibration: model card (I19-2)

**Version `calibrated-v1` (source "calibrated v1")**, published to Data Domains as a new `dd_stress_sensitivity` version through Session E's publisher; Session D's Stress Lab engine reads it. Built by `backend/dealdesk/calibration/sensitivity.py`; coefficients in `backend/dealdesk/calibration/calibrated_v1.json`; this card is written by `python -m backend.dealdesk.calibration.card` (the same files always give the same numbers).

## Answer first

- **10 of 30 sector × driver sensitivities are estimated from the bank's own history; 20 keep the expert value and are flagged.**
- **Oil:** 0 of 15 sectors calibrated. Over 2022Q3–2025Q4 the bank's borrower revenues show no oil effect that can be told from zero in any sector, although Brent moved from -37% to +32% year on year. The oil sensitivities in `stress_scenarios.json` (oil −30% → Construction −12%, Chemicals −15% …) therefore stay as **untested expert assumptions**.
- **Non-oil GDP:** 10 of 15 rows calibrated (book-wide default included). The estimated betas are much smaller than the expert ones: a 3-point non-oil GDP shortfall costs Real Estate, Hospitality and Construction about 0.5–0.6% of revenue in this history, against 7.5–9.0% of revenue in the expert table. Information Technology, Power and Utilities and Telecommunications move against the cycle in this history (wrong sign) and keep the expert value. Chemicals and Metals and Mining keep the expert value because the fit is too weak. 
- **Read with care:** the sample is one expansion (non-oil growth between 4.2% and 10.9%), with no contraction; a 3-point shortfall is about 1.4× the largest slowdown seen, so every GDP row is flagged **extrapolated**. A history that includes a downturn would very likely give larger betas. Risk Models can override any row (maker-checker), and every row carries the expert value beside the estimate.

## Data (PLAN_R12 §0)

| Input | Relation / file | Use |
|---|---|---|
| Borrower financials history | Data Domains `cockpit.corp_borrower_quarter` (`data/cockpit_v4_lake/v4-saudi-corporate-20q-v4/corp_borrower_quarter.parquet`): `revenue_sar_mn`, `sector`, by borrower and quarter, 2021Q3–2026Q2 | sector year-on-year revenue growth on a balanced panel |
| Brent | U.S. EIA Europe Brent spot (RBRTE), monthly averages; data/whatif_v5/mev/brent_monthly_eia.csv (public) | quarterly average, year-on-year log change |
| Real non-oil GDP | IMF real non-oil GDP growth via FRED SAUNGDPXORPCHPT, annual; data/whatif_v5/mev/mev_annual.csv (public) | four-quarter-ending growth (annual rates weighted by quarter) |

The macro series are the public files the What-If MEV already uses; they are not yet a registered Data Domains relation (Session E owns the registry: recorded as a gap in `docs/STATUS_R12_TRY.md`). No other source is read.

## Method

- **Sample:** 14 quarters, 2022Q3 to 2025Q4 (year-on-year windows need four earlier quarters). Left out: 2026Q1, 2026Q2 (their window needs the 2026 GDP projection, not history).
- **Dependent variable:** g = 100 × ln(Σ revenue_t / Σ revenue_t−4) over the sector's borrowers with revenue in both quarters.
- **Regression:** g = a + b_oil × oil + b_gdp × gdp, OLS; **Newey-West** standard errors with 4 lags (the year-on-year windows overlap); **90% bands** with Student t (11 degrees of freedom).
- **Robustness:** the same regression on borrower-level growth, pooled within the sector, standard errors clustered by quarter (`panel_estimate` in the relation); the two agree closely.
- **Stress value:** the revenue change at the scenario shock: `oil_30` (Brent −30%, log change ln 0.7) and `gdp_3` (non-oil GDP 3 points below plan), with the band carried through.
- **When the expert value stays (flagged):** fewer than 12 quarters; the 90% band includes zero; the wrong sign; R² below 0.30; the driver's own partial R² below 0.05; or the shock more than 1.5× the largest adverse move in the sample. The row then has `fallback = true`, `source = "expert (fallback)"` and the reason in `flag`.

## Results: oil (Brent −30%)

| Sector | Elasticity [90% band] | R² / partial | n | Revenue at shock [band] | Expert | Used | Why expert |
|---|---|---|---|---|---|---|---|
| Agriculture and Agri-processing | -0.001 [-0.007, +0.006] | 0.66 / 0.00 | 14 q, 321 borrowers | +0.02% [-0.20%, +0.24%] | -4.0% | **expert (flag)**: -4.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Chemicals | -0.002 [-0.006, +0.003] | 0.15 / 0.04 | 14 q, 382 borrowers | +0.06% [-0.10%, +0.22%] | -15.0% | **expert (flag)**: -15.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Construction | +0.004 [+0.001, +0.007] | 0.93 / 0.02 | 14 q, 622 borrowers | -0.14% [-0.26%, -0.02%] | -12.0% | **expert (flag)**: -12.00% | the driver adds only 0.017 to R² (below 0.05): the fit comes from the other driver |
| Healthcare | -0.002 [-0.006, +0.002] | 0.46 / 0.03 | 14 q, 341 borrowers | +0.06% [-0.08%, +0.20%] | -3.0% | **expert (flag)**: -3.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Hospitality | +0.002 [-0.006, +0.009] | 0.83 / 0.00 | 14 q, 381 borrowers | -0.06% [-0.31%, +0.20%] | -10.0% | **expert (flag)**: -10.00% | the 90% band (-0.006 to 0.009) includes zero: the effect is not identified |
| Information Technology | -0.002 [-0.005, +0.001] | 0.26 / 0.09 | 14 q, 352 borrowers | +0.09% [-0.02%, +0.19%] | -5.0% | **expert (flag)**: -5.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Manufacturing | -0.000 [-0.005, +0.005] | 0.71 / 0.00 | 14 q, 482 borrowers | +0.01% [-0.16%, +0.19%] | -8.0% | **expert (flag)**: -8.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Metals and Mining | -0.001 [-0.004, +0.002] | 0.20 / 0.02 | 14 q, 281 borrowers | +0.03% [-0.06%, +0.13%] | -12.0% | **expert (flag)**: -12.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Power and Utilities | -0.003 [-0.005, -0.000] | 0.42 / 0.10 | 14 q, 342 borrowers | +0.10% [+0.01%, +0.19%] | -3.0% | **expert (flag)**: -3.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Real Estate | +0.004 [-0.002, +0.009] | 0.89 / 0.01 | 14 q, 542 borrowers | -0.13% [-0.32%, +0.06%] | -10.0% | **expert (flag)**: -10.00% | the 90% band (-0.002 to 0.009) includes zero: the effect is not identified |
| Retail Trade | +0.001 [-0.001, +0.004] | 0.80 / 0.01 | 14 q, 381 borrowers | -0.05% [-0.16%, +0.05%] | -6.0% | **expert (flag)**: -6.00% | the 90% band (-0.001 to 0.004) includes zero: the effect is not identified |
| Telecommunications | -0.001 [-0.004, +0.003] | 0.35 / 0.00 | 14 q, 242 borrowers | +0.03% [-0.11%, +0.16%] | -3.0% | **expert (flag)**: -3.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Transport and Logistics | -0.000 [-0.003, +0.002] | 0.62 / 0.00 | 14 q, 402 borrowers | +0.01% [-0.09%, +0.10%] | -8.0% | **expert (flag)**: -8.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Wholesale Trade | -0.001 [-0.004, +0.002] | 0.52 / 0.01 | 14 q, 341 borrowers | +0.03% [-0.08%, +0.13%] | -8.0% | **expert (flag)**: -8.00% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| default | +0.000 [-0.003, +0.004] | 0.76 / 0.00 | 14 q, 5,412 borrowers | -0.01% [-0.13%, +0.12%] | -6.0% | **expert (flag)**: -6.00% | the 90% band (-0.003 to 0.004) includes zero: the effect is not identified |

## Results: real non-oil GDP (3 points below plan)

| Sector | Beta [90% band] | R² / partial | n | Revenue at shock [band] | Expert | Used | Why expert |
|---|---|---|---|---|---|---|---|
| Agriculture and Agri-processing | +0.102 [+0.062, +0.142] | 0.66 / 0.61 | 14 q, 321 borrowers | -0.31% [-0.43%, -0.19%] | -2.4% | calibrated: -0.31% |  |
| Chemicals | +0.024 [-0.001, +0.048] | 0.15 / 0.15 | 14 q, 382 borrowers | -0.07% [-0.14%, +0.00%] | -4.5% | **expert (flag)**: -4.50% | the 90% band (-0.001 to 0.048) includes zero: the effect is not identified |
| Construction | +0.181 [+0.158, +0.205] | 0.93 / 0.75 | 14 q, 622 borrowers | -0.54% [-0.61%, -0.47%] | -9.0% | calibrated: -0.54% |  |
| Healthcare | +0.048 [+0.026, +0.070] | 0.46 / 0.46 | 14 q, 341 borrowers | -0.14% [-0.21%, -0.08%] | -1.5% | calibrated: -0.14% |  |
| Hospitality | +0.203 [+0.149, +0.256] | 0.83 / 0.72 | 14 q, 381 borrowers | -0.61% [-0.77%, -0.45%] | -7.5% | calibrated: -0.61% |  |
| Information Technology | -0.017 [-0.031, -0.003] | 0.26 / 0.09 | 14 q, 352 borrowers | +0.05% [+0.01%, +0.09%] | -3.6% | **expert (flag)**: -3.60% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Manufacturing | +0.094 [+0.062, +0.126] | 0.71 / 0.65 | 14 q, 482 borrowers | -0.28% [-0.38%, -0.19%] | -4.5% | calibrated: -0.28% |  |
| Metals and Mining | +0.023 [+0.010, +0.036] | 0.20 / 0.20 | 14 q, 281 borrowers | -0.07% [-0.11%, -0.03%] | -6.0% | **expert (flag)**: -6.00% | R² 0.20 is below 0.30 |
| Power and Utilities | -0.029 [-0.039, -0.019] | 0.42 / 0.20 | 14 q, 342 borrowers | +0.09% [+0.06%, +0.12%] | -1.5% | **expert (flag)**: -1.50% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Real Estate | +0.210 [+0.166, +0.254] | 0.89 / 0.73 | 14 q, 542 borrowers | -0.63% [-0.76%, -0.50%] | -7.5% | calibrated: -0.63% |  |
| Retail Trade | +0.090 [+0.070, +0.109] | 0.80 / 0.67 | 14 q, 381 borrowers | -0.27% [-0.33%, -0.21%] | -6.0% | calibrated: -0.27% |  |
| Telecommunications | -0.050 [-0.075, -0.026] | 0.35 / 0.29 | 14 q, 242 borrowers | +0.15% [+0.08%, +0.22%] | -2.4% | **expert (flag)**: -2.40% | the estimate has the wrong sign (revenue does not fall with the driver in this history) |
| Transport and Logistics | +0.053 [+0.041, +0.066] | 0.62 / 0.56 | 14 q, 402 borrowers | -0.16% [-0.20%, -0.12%] | -4.5% | calibrated: -0.16% |  |
| Wholesale Trade | +0.046 [+0.030, +0.062] | 0.52 / 0.49 | 14 q, 341 borrowers | -0.14% [-0.19%, -0.09%] | -5.4% | calibrated: -0.14% |  |
| default | +0.085 [+0.062, +0.107] | 0.76 / 0.67 | 14 q, 5,412 borrowers | -0.25% [-0.32%, -0.18%] | -4.5% | calibrated: -0.25% |  |

## The relation (`dd_stress_sensitivity`, version 2 = calibrated v1)

Session E's contract keys a sensitivity by `sensitivity_id` (`<sector>:<driver>`) and `version`; E seeded version 1 from `stress_scenarios.json` (`method = expert`). Calibrated v1 publishes **version 2** of the oil and non-oil GDP rows (15 sectors with `default`, two drivers): `beta` is the value the engine uses (revenue % change per 1% fall in Brent, or per 1 point of non-oil GDP growth below plan); `method = regression` with `band_low`, `band_high` (90%), `n_obs` and `r2` where the data carries it; otherwise `method = expert`, the expert `beta` again, no band, and `source` starting "expert (fallback)" with the reason and the estimate that was rejected. `owner` is "Risk Models (calibrated v1, R12 Session T)", `model_card_ref` points here. The other drivers (fixed-cost, largest-customer and project shares) stay at version 1. The engine reads the highest version per `sensitivity_id` (`backend.dealdesk.calibration.publish.latest`). The full estimate (partial R², the borrower-panel estimate, the shock reach, the extrapolation flag) is in `calibrated_v1.json`.

## Limits

1. One expansion, 14 usable quarters (about 3.5 non-overlapping years): the bands are conditional on a short sample, and the GDP regressor is built from annual data (5 calendar years), so its information is thinner than 14 points suggest.
2. Revenue only. Margin, receivable days and the largest-customer and project shares keep the expert assumptions.
3. No listed-company or public sector series are in the repo, so the plan's "plus public data" part is limited to the two macro series.
4. The relation records both values; replacing the expert value in the Stress Lab is Session D's engine reading this version. An expert override goes through maker-checker (D's scenario editor).
