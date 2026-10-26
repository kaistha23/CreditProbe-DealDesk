id: scorecard_validation
name: Scorecard Validation
screen: /scorecard-validation
keywords: scorecard, validation, gini, psi, calibration, discrimination
example: scorecard_verdicts

## What it is
Scorecard Validation tests the retail application, retail behavioural and SME scorecards: discrimination (Gini, AUC, KS), calibration (observed against expected, binomial and traffic-light tests), stability (PSI and CSI), variables (IV, WoE monotonicity, VIF) and overrides, each with a red, amber or green verdict against stated thresholds.

## Flow
1. [Open Scorecard Validation](/scorecard-validation) and start a validation in the chat, naming the scorecard.
2. Agree the plan the assistant proposes (tests, samples, thresholds).
3. Run it: results arrive as charts and tables with a verdict per test.
4. Ask the assistant what is wrong and what to do; it can run extra analyses (segment Gini, one variable's PSI, overrides).
5. Review and export the Word validation report, or send it to Playbook.

## Good to know
- Every verdict states its threshold; the findings carry a remedy and an owner.
