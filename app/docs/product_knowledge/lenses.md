id: lenses
name: Lenses
screen: /lenses
keywords: lens, lenses, dashboard, build a lens, add ratio, custom ratio, kpi, tile, template
example: lenses_construction

## What it is
Lenses builds a live dashboard from a request in plain words, on the corporate book (quarterly) or the retail book (monthly): a KPI row (EAD, ECL, coverage, Stage 2 and 3 share, warned and high/critical names, NPL ratio, cost of risk, DSCR or 30+ DPD), 8 to 14 Plotly charts (trends over 8 quarters or 12 months, stage mix, ratings in the global order, sub-segments, regions and branches, Early Warning bands and reasons, migration or roll rates, vintages, concentration with HHI, utilisation), the top 20 names and a short commentary. Every figure is a query on the books, with its SQL under the (i).

## Flow
1. [Open Lenses](/lenses), choose Corporate or Retail, and ask for a dashboard, for example "construction sector dashboard", "Makkah retail cards" or "Stage 2 migration by RM". A template card (CRO portfolio, Construction sector, Real Estate concentration, Makkah region, Retail cards, Stage 2 watch, Early Warning critical names) opens a lens the same way.
2. The lens opens at once; the assistant on the right shows its process (Understand, Plan, Query, Answer, Validate, Publish) with the timer and writes the commentary.
3. Change it by conversation in the assistant: "add DSCR distribution", "remove the map", "show by region instead", "compare with Real Estate", "switch to retail personal finance". Or by hand: each tile's (⋯) menu changes the metric, chart type or dimension, moves or deletes the tile, explains it, or opens it as a Cockpit thread or a What-If cohort.
4. Add ratio opens the metric catalogue (books, Early Warning, What-If, Scorecard, Deal Desk) and the custom ratio builder (numerator over denominator with a filter), which the engine validates on the book before it is added.
5. Undo, Redo and Versions move through every change. The As-of selector reruns every figure for an earlier period; the period stays in the address.
6. Save (name, description, tags), Share with people or teams through Mail, Add to report (a Playbook section with the lens figures and charts), export to Excel or PDF in the house style, or Schedule a refresh note.

## Good to know
- Ask for **Regulatory breaches by article** (or "CBUAE breaches") to add a tile with the CBUAE Credit Risk Management Standards breaches on the whole book, one bar per article, with EAD, ECL and the provision shortfall.
- Nothing on a lens is a stored figure: opening it runs its queries on the current books, so it never goes stale.
- Templates are read only: saving one keeps your own copy. A lens someone shared with you can be duplicated.
- Warned means Early Warning band moderate, high or critical, as Early Warning counts it; cost of risk is the ECL change plus write-offs over EAD, annualised, in bps.
