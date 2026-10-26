id: deal_desk_levers
name: Deal Desk levers and alternative structures
screen: /deal-desk/DD-02
keywords: deal desk levers, deal desk lever, levers does deal desk, sell-down in deal desk, levers, lever, alternative structures, restructure, sell-down, hold level, guarantee, eca, credit insurance, cash margin, prepayment fee, covenants, cash sweep, dividend lock-up, review cycle, cross-sell, relationship raroc, minimum change, single lever, why it works, method appendix
example: dealdesk_levers

## What it is
Deal Desk restructures a proposal with every lever a credit risk manager has, grouped as in the term panel. **Pricing:** margin, upfront or arrangement fee, commitment fee on the undrawn, prepayment fee. **Structure:** tenor, amortisation (equal, sculpted, balloon), grace period, amount and hold level (sell-down), facility type and funded share (through the CCF), fixed or floating rate. **Risk mitigation:** cash margin, collateral package, guarantees from a parent, bank, the sovereign or an export credit agency (PD substitution on the covered part), credit insurance, assignment of contract proceeds. **Covenants and conditions:** leverage and DSCR covenants, cash sweep, dividend lock-up, negative pledge, a shorter review cycle. **Relationship:** cross-sell commitments, shown as relationship RAROC beside the deal RAROC. Each lever moves one RAROC channel (income, EAD, LGD, PD, capital, FTP), has an owned and versioned parameter table with its source, and moves inside market and policy bounds. For a deal below the hurdle the optimiser shows 2 to 4 alternative structures that clear it, each with its changed terms, RAROC, SVA, approval level and *why it works* (each lever's share of the RAROC gain), and the minimum change on each single lever that clears the hurdle alone. The Word report opens with the proposal as submitted and ends with a method appendix: the formula, the inputs, the parameter tables and a worked line for every metric and chart.

## Flow
1. Open a proposal from the Deal Desk pipeline: [Deal Desk](/deal-desk). Step 1 shows the proposal as submitted: obligor and group, rating and its date, every facility line, purpose, RM, existing exposure and the memo.
2. Step 2 measures the ask against the hurdle and the limits: [DD-02](/deal-desk/DD-02).
3. Press **Optimise** in the chat bar at the bottom: the counter-offers, the alternative structures with their lever contribution bars, and the minimum change on each lever.
4. Load a structure in the term panel and move any lever by group (Pricing, Structure, Risk mitigation, Covenants and conditions, Relationship); every move recomputes through the engine.
5. Ask in plain words: “What are my options?”, “What if we sell down 30% and take ECA cover on 40%?”, “Add a cash sweep and a semi-annual review”.
6. Recommend, save, and download the Word report with its method appendix, or add it to a Playbook report. Saved and optimised analyses appear under **Recent analyses** on the home, with **Continue where you left off**.

## Good to know
- The bar is lifetime RAROC at or above the hurdle (SVA ≥ 0) with every hard limit met; soft limits only with escalation.
- Deal terms never enter the PD model; covenants act through a capped PD/LGD overlay shown separately.
- A sell-down keeps the client's full facility for DSCR and leverage; the bank's exposure, capital and income scale with the hold, plus an arranger skim on the sold share.
- Every figure comes from the deterministic engine with a trace ID; the assistant never computes or chooses terms itself.
