id: what_if
name: What-If
screen: /what-if?domain=corporate
keywords: what-if, what if, scenario, stress, shock, oil, recession, downgrade
example: whatif_oil

## What it is
What-If runs scenarios on the books' IFRS 9 ECL: macro shocks (oil, rates, GDP, unemployment, real-estate prices), parameter shocks (PD, LGD, CCF), rating downgrades, sector stress and stage migration. Two engines answer: the Delta method (first-order, from the published PD and LGD sensitivities) and the XGBoost model. Each run shows ECL before and after, the waterfall by step, the change by segment and the capital impact.

## Flow
1. [Open What-If](/what-if?domain=corporate) and choose the book.
2. Pick a scenario from the library, or describe one in the chat ("oil 40% lower and a one-notch downgrade").
3. The assistant restates the shocks it understood and asks Delta or XGBoost if you have not chosen. You can mix questions and a scenario in one message ("Increase PD by 15% with stage implication. Reduce collateral. What is a decent collateral drop? What is the average PD increment between quarters?"): every question gets its own answer from the What-If data (collateral value history by segment with a recommended shock size; quarter-on-quarter PD by segment with a table), then the whole scenario is proposed, sized by those answers.
4. Press **Execute scenario** (or say "run it"): the result shows ECL before and after, the waterfall, the segments and the capital impact.
5. Ask why: the assistant explains the mechanics (for example how a collateral cut moves LGD) with this book's numbers.
6. Save the scenario, export the Word report, or import it into a Playbook scenario section with its waterfall.

## Good to know
- A scenario runs only when you execute it; questions never change anything.
- Collateral, haircut, LGD, PD, CCF, rating, sector and MEV are distinct levers.
- Every answer shows the process trace (Understand, Plan, Query, Answer, Validate, Publish) with a running timer while it works; open it afterwards to see each step's time.
- Choosing the model ("use the Delta method", "use XGBoost") does not run anything; Execute scenario does.
- "Staging effect" means every exposure is re-staged under the SICR rules after the shocks; the Stage 1 to 2 and 2 to 3 moves show in the result.
- Without the model key the header reads PLANNER MODE: the deterministic planner answers, every figure still from a real query.
