# Saudi Arabia MEV dataset: sources and coverage

## R14 refresh (19 Oct 2026, session m; K13)

Applied by `ops/r14_m_mev_refresh.py` (idempotent), then `ops/whatif_build_mev.py`. Each refreshed row names its URL and
carries `retrieved = 2026-10-19`; every other row keeps its own vintage and `retrieved = 2026-10-10`.

**How:** the container still cannot reach imf.org or eia.gov from the shell (proxy 403). The figures were found with web
search and read with a page fetch of URLs that appeared in the results. The IMF DataMapper API v2
(`https://www.imf.org/external/datamapper/api/v2/NGDP_RPCH`) answered and reports "World Economic Outlook (October
2026)", last modified 2026-10-08, but the fetched text is cut off before the SAU entry, so the Saudi values come from
press reports that quote the October 2026 WEO tables.

| Series | Year | Value | Was | Vintage | Source (URL in the row) |
|---|---|---|---|---|---|
| Real GDP growth (NGDP_RPCH) | 2025 | 4.6 | 4.5 (Apr 2026) | IMF WEO October 2026 | Arab News, 13 Oct 2026 |
| Real GDP growth | 2026 | **-3.3** | 1.7 (Jul 2026) | IMF WEO October 2026 | Zawya / Saudi Gazette, 14 Oct 2026 |
| Real GDP growth | 2027 | 7.9 | 5.5 (Jul 2026) | IMF WEO October 2026 | Zawya / Saudi Gazette |
| CPI inflation (PCPIPCH) | 2025 / 2026 / 2027 | 2.0 / 1.9 / 2.2 | 2.0 / 2.3 / 2.1 | IMF WEO October 2026 | Zawya, Arab News |
| Current account (BCA_NGDPD) | 2026 | -3.5 | -1.6 | IMF WEO October 2026 | Edge Consultancy table |
| IMF oil-price assumption (APSP, futures-based) | 2026 / 2027 | 95.74 / 87.39 | 89.27 / 78.7 | IMF WEO October 2026 | TASS, 13 Oct 2026 |

`latest_observations.csv` (new, read by the current-regime block `backend/scenarios/regime.py`): Brent spot USD 108 on
19 Oct 2026 (Trading Economics: "fell 1.5% towards $108"; its statistics show 110.14 and +80.5% y/y), USD 107.29 on
13 Oct 2026 and 63.69 a year earlier (Fortune, +68.45% y/y); EIA STEO October 2026 (released 6 Oct): Brent 1Q26 81.11,
2Q26 102.93, 3Q26 95.95, 4Q26 forecast 104.69, 2026 average 96.32, 2027 average 83.74; September 2026 average 114
(agrees with the EIA monthly file, 114.16); GASTAT Q2 2026 real GDP -4.7% y/y (flash -4.8), non-oil +0.9%, oil -24.8%;
GASTAT CPI September 2026 1.9%; non-oil PMI September 2026 55.3 (S&P Global); MoF 2027 pre-budget statement deficit
4.9% of GDP in 2026 (ministry figure, not IMF); and the dated market context (Gulf supply disruption: Yanbu, Hormuz).

**Not refreshed (still their earlier vintage; listed in docs/STATUS_R14_M.md):** non-oil real GDP growth (IMF REO
October 2026 figures for Saudi Arabia not found in any fetched page: 2025-27 stay on the July 2026 Article IV),
unemployment (LUR) and government expenditure (GGX_NGDP) and net lending (GGXCNL_NGDP) for 2025-27 (no October 2026
figure found), current account 2025 and 2027, CPI 2028-30 and GDP 2028-30 (April 2026), SAMA and GASTAT annual series.
Brent monthly stays the EIA file to September 2026; October 2026 is a partial month and is carried by the daily rows.

**Effect:** the What-If domain, its credit-cycle model and the XGBoost What-If models were rebuilt on the new base path
(the 2026 GDP contraction enters the forward-looking PD), the §S scenario relations were republished, and the Deal Desk
forward-looking PD moves with it (twin A RAROC now 14.46%, was 14.52%; `dd_raroc_drift` rebuilt).

---

- Data file: `saudi_mev_annual.csv`, 407 rows. Columns: series, year, value, unit, kind, source, source_url, vintage, note.
- Retrieval date for every series: **2026-10-10**.
- Builder script: `../mev_build/build.py`. Raw downloads are in `dl/`. The script reads the downloaded files. Values that came from web-search snippets are typed into the script by hand, and each such row says so in its `note`.

## How the data was obtained

The container blocks imf.org, worldbank.org, sama.gov.sa, stats.gov.sa, FRED and DBnomics. The data came from three routes:

1. **GitHub mirrors of official data files**, fetched with curl from raw.githubusercontent.com. The files were located with GitHub code search. Every mirrored number is a machine-readable copy of an IMF, SAMA, GASTAT or EIA publication. Nothing was retyped.
2. **WebSearch snippets** of IMF press releases, FRED tables, MoF and GASTAT releases, and Reuters, Argaam and Interfax reporting. These values were read from text, so they are flagged in `note`.
3. **Derived values.** These are simple arithmetic on official numbers, such as growth computed from levels or an annual mean of four quarters. Each one is marked `DERIVED` in `note`.

No value was interpolated or invented. Where a year could not be found, it is left out of the CSV and listed below.

### IMF vintages used (important for a What-If tool)

| Vintage | Where it came from | Used for |
|---|---|---|
| **IMF WEO April 2026** | IMF DataMapper API JSON snapshots taken 2026-04-22, mirrored in `github.com/ashishsalunkhe/geosyn` (`data/raw/imf/2026/04/22/*.json`). Horizon runs to 2031. 2026 GDP growth = 3.1, which matches the published April 2026 WEO. | Real GDP growth (1990-2025, 2028-30), CPI (1990-2030), current account (1990-2030) |
| **IMF WEO Update July 2026 / 2026 Article IV (PR26/267, 29 Jul 2026)** | Search snippets of the IMF press release and Arab News / Interfax reports | GDP growth 2026-27, non-oil growth 2025-27, oil price assumption 2026-27 |
| IMF REO Middle East & Central Asia, Oct 2025 | FRED series SAUNGDPXORPCHPT (last updated 2026-01-22), read from search snippets | Non-oil real GDP growth 2005-2024 |
| IMF WEO April 2025 | IMF data portal export `IMF.RES:WEO(6.0.0)`, mirrored in `github.com/felipebulgareli/Projeto-grupo3` | Unemployment 2014-2024 |
| IMF WEO October 2024 | WEO country-subject CSVs mirrored in `github.com/MohamedataS/Inflation-Forecasting-PanelModels`. Notes say "data last updated 09/2024" and 2024 GDP growth = 1.5. | Gov. expenditure % GDP 1990-2024, unemployment 1999-2013 |
| IMF WEO October 2025 (for cross-checks only) | IMF data portal export `WEO(9.0.0)` in `github.com/Center-for-Global-Development/25-Years-Health-Systems`, plus DataMapper snapshots from 2026-04-13 in geosyn | Notes only |

**Warning about mixed vintages.** GASTAT rebased the national accounts in 2024-25. This raised the level of nominal GDP (about +14% for 2023) and revised real growth: 2024 growth went from 1.3 to 2.0 to 2.6. Series taken from older vintages (gov. expenditure % GDP, unemployment before 2014) still use the old denominators and history. For GDP growth, 2026-27 come from July 2026 and 2028-30 from April 2026, so there is a vintage seam at 2027/2028.

---

## 1. Real GDP growth (`real_gdp_growth`, % y/y)
- **Found:** IMF WEO NGDP_RPCH, April 2026 vintage, for 1990-2025 (1 decimal, as published on DataMapper). Projections: 2026 = 1.7 and 2027 = 5.5 from the July 2026 WEO Update and the 2026 Article IV. 2028 = 3.6, 2029 = 3.5 and 2030 = 3.5 from April 2026.
- **URLs:** https://www.imf.org/external/datamapper/NGDP_RPCH@WEO/SAU ; mirror https://raw.githubusercontent.com/ashishsalunkhe/geosyn/HEAD/data/raw/imf/2026/04/22/230513_023913.json ; https://www.imf.org/en/news/articles/2026/07/29/pr26267-saudi-arabia-imf-concludes-2026-aiv
- **Alternatives (noted, not used):**
  - April 2026 WEO had 2026 = 3.1 and 2027 = 4.5.
  - October 2025 WEO had 2024 = 2.0, 2025 = 4.0, 2026 = 4.0, 2027 = 3.2, and 3.3 for 2028-30.
  - IMF Article IV July 2026 has 2025 = 4.6. GASTAT's flash estimate for 2025 was 4.5.
- **Missing/uncertain:** None missing for 1990-2030. The July 2026 values for 2026-27 were read from snippets, but two independent sources agree on them.

## 2. Non-oil real GDP growth (`nonoil_real_gdp_growth`, % y/y)
- **Found:**
  - 2005-2024 from the IMF Regional Economic Outlook series on FRED (SAUNGDPXORPCHPT, Oct 2025 REO vintage), read from search snippets at 2 decimals.
  - 2025 = 4.2, 2026 = 2.6 and 2027 = 4.5 from the IMF 2026 Article IV "Selected Economic Indicators, 2025-27" table (PR26/267).
- **URLs:** https://fred.stlouisfed.org/series/SAUNGDPXORPCHPT ; https://fred.stlouisfed.org/data/SAUNGDPXORPCHPT ; https://www.imf.org/en/news/articles/2026/07/29/pr26267-saudi-arabia-imf-concludes-2026-aiv
- **Other sources disagree:**
  - GASTAT's 2025 flash estimate is 4.9.
  - GASTAT's Nov-2025 revision puts 2024 at about 6.0.
  - The IMF 2025 Article IV gives 2024 = 4.5 on the rebased methodology, or 4.2 on the old one.
  - Third-party trackers (Vision2030.ai, FocusEconomics) give different 2020-23 figures because they use pre- or post-rebasing vintages.
- **Missing:** 1990-2004 (not searched for). 2028-2030 projections: the Article IV only covers 2025-27. The Oct-2025 REO had 2026 = 3.53 and 2030 ≈ 3.48, but not 2028-29 reliably, so these were left out.
- **Uncertain:**
  - Every value comes from a snippet and was not downloaded.
  - 2005-2014 is the least confident, because the snippet said "about".
  - For 2025-27, the order of the Article IV columns was inferred.

## 3. Brent oil price (`brent_oil_price`, USD/bbl annual average) and IMF oil assumption (`oil_price_imf_apsp`)
- **Found:** EIA Europe Brent Spot FOB (RBRTE) annual averages for 1990-2025, from GitHub `datasets/oil-prices` `brent-year.csv`. The 2025 value is 69.14. Recomputing it from the daily file gives the same figure.
- **Projections:** I did not find IMF Brent projections. The IMF publishes an oil price assumption for its **APSP** index, which is the simple average of Brent, Dubai and WTI, not Brent. It is stored as a separate series, `oil_price_imf_apsp`:
  - 2026 = 89.27 and 2027 = 78.7 (July 2026 WEO Update, via Interfax; the IMF briefing says "about $89").
  - April 2026 WEO values were 82.22 and 75.97. January 2026 values were 62.13 and 62.17.
- **URLs:** https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-year.csv ; https://www.eia.gov/dnav/pet/hist/RBRTEA.htm ; https://www.imf.org/en/news/articles/2026/07/08/tr070826-weo-press-briefing-transcript-july-8-2026
- **For information (not in the CSV):** The EIA Brent daily average for 2026 year-to-date, through 6 Oct 2026, is 93.81 (193 obs; min 61.08, max 138.21). It is a partial year, so it was not stored.
- **Missing:** IMF oil assumptions for 2028-2030 were not found; the published WEO text gives only the next two years. The 2027 APSP figure comes from a single secondary source (Interfax), so it is less confident.

## 4. CPI inflation (`cpi_inflation`, % y/y annual average)
- **Found:** IMF WEO PCPIPCH, April 2026 vintage, for 1990-2030. Values for 2026 onward are projections; 2025 is an IMF estimate.
- **URLs:** https://www.imf.org/external/datamapper/PCPIPCH@WEO/SAU ; mirror https://raw.githubusercontent.com/ashishsalunkhe/geosyn/HEAD/data/raw/imf/2026/04/22/231421_768964.json
- **Alternatives:**
  - The 2026 Article IV (July 2026) shows 2.0 for 2025, 2.2 for 2026 and 2.1 for 2027 (column order inferred). The April 2026 value of 2.3 was kept for 2026.
  - The June 2026 mission statement also said about 2.3%.
  - SAMA bulletin CPI (2023=100) gives slightly different history because of the rebasing. It was not used.
- **Missing:** None for 1990-2030.

## 5. Unemployment rate (`unemployment_rate`, %): IMF LUR = total population (Saudis + non-Saudis), annual
- **Found:**
  - 2014-2024 from IMF WEO April 2025 (LUR). 2024 = 3.5, which matches the Oct-2025 DataMapper.
  - 1999-2013 from IMF WEO Oct 2024. These values are identical to the Apr-2015 vintage.
  - 2025 = 3.2 is **derived**: the mean of the four GASTAT quarterly overall rates (2.8, 3.2, 3.4, 3.5). The Q3 figure of 3.4 is inferred from the Q4 release, which reported "+0.1pp q/q".
- **URLs:**
  - https://www.imf.org/external/datamapper/LUR@WEO/SAU
  - Mirrors: https://raw.githubusercontent.com/felipebulgareli/Projeto-grupo3/HEAD/dataset_2025-06-04T01_01_07.768164706Z_DEFAULT_INTEGRATION_IMF.RES_WEO_6.0.0.csv and https://raw.githubusercontent.com/MohamedataS/Inflation-Forecasting-PanelModels/HEAD/02-Dataset/01-DataSet/dataset_Org/06-WEO_Data_EMP_LUR.csv
  - GASTAT LMS: https://www.stats.gov.sa/en/statistics
- **Related:** The unemployment rate for Saudi nationals is much higher: 7.2 in Q4-2025 (6.3 Q1, 6.8 Q2, 7.5 Q3). Its annual history is not included.
- **Missing:**
  - 1990-1998: the IMF has no data.
  - IMF LUR projections for 2026-2030 were not found; the IMF may not publish them for SAU.
  - The April 2026 vintage of LUR could not be retrieved.
  - 2025 is less confident.

## 6. SAMA repo rate (`sama_repo_rate`, % end of year)
- **Found:** 2007-2025 from SAMA Monthly Statistical Bulletin Feb-2026, Section 5 Table 6 (annual rows = end of period, checked against the December monthly rows). 2025 = 4.25. The table also has reverse repo (3.75 at end-2025), which is not stored.
- **URLs:** https://www.sama.gov.sa/en-US/EconomicReports/Pages/MonthlyStatistics.aspx ; mirror https://raw.githubusercontent.com/civillizard/Saudi-Real-Estate-Data/main/sama/SAMA-Monthly-Bulletin-Feb-2026/5-6.csv
- **Missing:**
  - **1990-2006.** The table starts in 2007. Press reports show the repo rate was raised to 4.50% in Oct-2005, but no year-end 2005 or 2006 value was confirmed.
  - 2026 is not needed. It was 4.25 as of Feb-2026. A SAMA decision on 17-Sep-2026 exists, but its figure was not retrieved.

## 7. 3-month SAIBOR (`saibor_3m` = annual average; `saibor_3m_december` = December monthly average, a year-end proxy)
- **Found:** 2007-2025 from the same SAMA table. The annual row is the average of the monthly averages; the 2022 value of 3.13 against December's 5.28 confirms that it is an average.
- **URLs:** same as section 6.
- **Missing:** 1990-2006 (not in the table).

## 8. Government expenditure
- `gov_expenditure_pct_gdp`: IMF WEO GGX_NGDP (general government total expenditure, % GDP), **October 2024 vintage**, 1990-2024. 2024 was still an estimate in that vintage.
  - URLs: https://www.imf.org/external/datamapper/GGX_NGDP@WEO/SAU ; mirror https://raw.githubusercontent.com/MohamedataS/Inflation-Forecasting-PanelModels/HEAD/02-Dataset/01-DataSet/dataset_Org/07.2-WEO_Data_GGX_NGDP.csv
  - **Caveat:** This vintage predates GASTAT's GDP rebasing, so ratios from about 2018 onward are overstated compared with current IMF data. A secondary site quoting the WEO gives about 29.2% for 2024 and about 29% for 2025 (not confirmed, not used). The 2025 Article IV table (central government) shows expenditure of 29.6 / 28.1 / 27.9 % GDP, which is probably 2024-26; this is a different coverage and the column order was inferred.
- `gov_expenditure_sar_bn`: MoF actual central-government budget expenditure in SAR bn, 2015-2024, from Argaam's reproduction of MoF data (2026 budget article).
  - 2025 = 1,388.4 is **derived** as the sum of the MoF quarterly figures (322.3 + 336.1 + 358.4 + 371.6). The press reported about SR1.39 trillion.
  - URLs: https://www.argaam.com/en/article/articledetail/id/1863220 ; https://www.mof.gov.sa/en/budget/Pages/QuarterlyReports.aspx ; https://mof.gov.sa/en/generalservcies/open-data/Documents/RevenuesExpendituresActual.pdf (not readable from here)
- **Missing:**
  - GGX_NGDP for 2025 and all IMF projections for 2026-2030 (the current vintage could not be retrieved).
  - SAR bn values for 1990-2014.
  - Projections in SAR bn: the MoF 2026 budget is about SAR 1.31 tn, but the exact figure was not confirmed and it is a budget, not an IMF projection.

## 9. Real estate price index (GASTAT REPI)
There are two methodologies with an index break, kept as **separate series** with no splicing:
- `repi_index_2014base` (2014=100, old methodology, discontinued after 2024Q2): annual averages for 2015-2022 come from the GASTAT annual report (indicator EfPi0401). 2014 (100.0) and 2023 (82.626) are **derived** as the mean of the four GASTAT quarterly national indices. Mirror: https://raw.githubusercontent.com/civillizard/Saudi-Real-Estate-Data/main/gastat/GASTAT-REPI-By-Type-Region-2014base/Report.csv and `gastat/REPI-2024-Q1.csv`. Official: https://database.stats.gov.sa/home/report/225
- `repi_yoy_2014base`: 2015-2023, computed from those levels.
- `repi_index_2023base` (2023=100, new methodology from 2024Q3): 2021-2024 annual averages (84.64, 95.36, 100, 102.27) come from the KAPSARC/GASTAT file `kapsarc/KAPSARC-RE-Price-Index-2023base.csv`. 2025 = 104.32 is **derived** as the mean of the 2025 quarterly indices (104.93, 105.00, 103.88, 103.48). The Q4 value comes from the GASTAT Q4-2025 release (https://stats.gov.sa/en/w/news/157), which reported -0.7% y/y. The same averaging reproduces the published 2024 figure to within 0.01.
- `repi_yoy_2023base`: 2022 = 12.7, 2023 = 4.9 and 2024 = 2.3 are published. 2025 = 2.0 is derived.
- **Not used:** the KAPSARC "2014base" annual file (`KAPSARC-RE-Price-Index-2014base.csv`). Its general index for 2016-2024 does not match GASTAT's own 2014-base report (for example 2021: 88.24 vs 81.21).
- **Missing:** everything before 2014 (the index starts in 2014), and any IMF or official projections.
- **Uncertain:** the derived 2025 values. The two methodologies give very different 2022 growth (old +1.1% vs new +12.7%).

## 10. Current account balance (`current_account_balance`, % GDP)
- **Found:** IMF WEO BCA_NGDPD, April 2026 vintage, 1990-2030. Values from 2026 onward are projections; 2025 = -3.0 is an estimate.
- **URLs:** https://www.imf.org/external/datamapper/BCA_NGDPD@WEO/SAU ; mirror https://raw.githubusercontent.com/ashishsalunkhe/geosyn/HEAD/data/raw/imf/2026/04/22/231425_196664.json
- **Alternatives (noted, not used):**
  - The 2026 Article IV (July 2026) table appears to show -2.6 for 2025, -0.3 for 2026 and -0.8 for 2027. These reflect higher oil prices, but the column order is unconfirmed.
  - October 2025 WEO had 2024 = -0.5, 2025 = -2.1 and 2026 = -2.5.
  - The World Bank MPO (Apr-2026) gave a different 2025 estimate.
- **Missing:** None for 1990-2030. Note that the July 2026 IMF view is materially less negative for 2026-27.

## 11. Bank credit to private sector growth (`bank_credit_private_growth`, % y/y, end of year) and level (`bank_claims_private_sector_level`, SAR mn)
- **Found:** SAMA Monthly Statistical Bulletin Feb-2026, Table 12a "Bank Claims on Private Sector", year-end Grand Total for 1993-2025. Growth for 1994-2025 is **derived** from these levels. The `note` column also gives growth for loans, advances and bills only (excluding investments in private securities). 2025 = 10.23% (Grand Total).
- **URLs:** https://www.sama.gov.sa/en-US/EconomicReports/Pages/MonthlyStatistics.aspx ; mirror https://raw.githubusercontent.com/civillizard/Saudi-Real-Estate-Data/main/sama/SAMA-Monthly-Bulletin-Feb-2026/12a.csv
- **Missing:** 1990-1993 growth (the table starts at end-1993). There are no IMF projections. The IMF Article IV press-release table might include credit growth, but it was not retrieved.

---

## Things to verify when imf.org is reachable
1. Download the full WEO April 2026 database or DataMapper for GGX_NGDP and LUR, so they are on the same vintage as GDP, CPI and current account.
2. Confirm the 2026 Article IV table column order (2025/2026/2027) for non-oil growth, CPI and current account.
3. Confirm FRED SAUNGDPXORPCHPT values, especially 2005-2014.
4. Confirm the July 2026 APSP oil assumption for 2027 (78.7).
5. Note that the October 2026 WEO is due at the 2026 Annual Meetings (mid-October 2026) and will supersede all IMF projections here.
