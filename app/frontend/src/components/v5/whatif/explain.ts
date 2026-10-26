/** R6 E4: the (i) explanations for every What-If chart, built from the chart's own figures. */

import type { Bar, PopulationSummary, RatingRow, Result, SegmentRow } from "@/lib/v5/whatif";

import { type ChartExplain, exNum, exPct, exSarM, maxBy } from "../core/chart-explain-core.ts";

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
const signed = (v: number) => `${v >= 0 ? "+" : "−"}${exSarM(Math.abs(v))}`;

// ---------------------------------------------------------------- population header

export function stageExplain(s: PopulationSummary): ChartExplain {
  const total = sum(s.stages.map((r) => r.ead));
  const st2 = s.stages.find((r) => r.stage === 2) ?? s.stages[1];
  return {
    shows: `How the exposure of ${s.scope_label} splits across the three IFRS 9 stages.`,
    formula: [
      "**Stage 1** = performing; **Stage 2** = significant increase in credit risk; **Stage 3** = credit-impaired (in default).",
      "**Slice share** = EAD in the stage ÷ total EAD × 100 (EAD = exposure at default, SAR m).",
    ],
    read: st2
      ? `${st2.label}: **${exSarM(st2.ead)} of ${exSarM(total)}** = **${exPct(st2.ead, total)}** of EAD, held by ${exNum(st2.owners)} ${s.labels.owners.toLowerCase()}.`
      : "Each slice is one stage; its size is that stage's share of EAD.",
    lookFor: "A **growing Stage 2 slice**: Stage 2 carries lifetime ECL, so migration there drives provisions up sharply.",
  };
}

export function gradeExplain(s: PopulationSummary): ChartExplain {
  const total = sum(s.grades.rows.map((r) => r.ead));
  const top = maxBy(s.grades.rows, (r) => r.ead);
  return {
    shows: `Exposure by ${s.grades.label.toLowerCase()}, best grade on the left (${s.grades.order.slice(0, 1).join("")} to ${s.grades.order.slice(-1).join("")}).`,
    formula: [
      `**Bar** = sum of EAD (SAR m) of the exposures in that ${s.grades.label.toLowerCase()}.`,
      "**Share** (in the example) = EAD in the grade ÷ total EAD × 100.",
    ],
    read: top
      ? `${top.grade}: **${exSarM(top.ead)} of ${exSarM(total)}** = **${exPct(top.ead, total)}** of EAD, the largest grade.`
      : "The taller the bar, the more exposure sits in that grade.",
    lookFor: "Weight **piling up towards the right** (weaker grades): a shock that downgrades names moves exposure rightwards and raises ECL.",
  };
}

export function splitExplain(s: PopulationSummary): ChartExplain {
  const total = sum(s.split.rows.map((r) => r.ead));
  const top = maxBy(s.split.rows, (r) => r.ead);
  const item = s.split.label.toLowerCase();
  return {
    shows: `Exposure by ${item}${s.split.within ? `, within ${s.split.within}` : ""}: where the book is concentrated.`,
    formula: [
      `**Bar** = sum of EAD (SAR m) of the exposures in the ${item}.`,
      "**Coverage** (on hover) = ECL ÷ EAD × 100.",
    ],
    read: top
      ? `${top.name}: **${exSarM(top.ead)} of ${exSarM(total)}** = **${exPct(top.ead, total)}** of EAD, coverage ${exNum(top.coverage_pct, 2)}%.`
      : `Each bar is one ${item}.`,
    lookFor: `**Concentration**: one ${item} holding a large share means a ${item}-specific shock moves the whole book.`,
  };
}

export function reasonsExplain(s: PopulationSummary): ChartExplain {
  const top = maxBy(s.reasons, (r) => r.owners);
  const own = s.labels.owners.toLowerCase();
  return {
    shows: `The Early Warning rules that fired most often in ${s.scope_label}, with the exposure they touch.`,
    formula: [
      `**${s.labels.owners} flagged** = count of distinct ${own} for whom the rule fired this period.`,
      "**EAD** = sum of EAD (SAR m) of the exposures the rule fired on.",
    ],
    read: top
      ? `"${top.reason}": **${exNum(top.owners)}** ${own} flagged, **${exSarM(top.ead)}** of EAD.`
      : "The longest bar is the most common reason.",
    lookFor: "A reason with **few names but large EAD** (a few big names), and reasons that point at the scenario you are about to run.",
  };
}

export function bandsExplain(s: PopulationSummary): ChartExplain {
  const all = sum(s.bands.map((b) => b.owners));
  const worst = s.bands[0];
  const own = s.labels.owners.toLowerCase();
  return {
    shows: `${s.labels.owners} by their worst Early Warning band, worst band first.`,
    formula: [
      `**Bar** = count of ${own} whose worst exposure is in that band (each name counted once).`,
      "**Share** (in the example) = names in the band ÷ all names shown × 100.",
    ],
    read: worst
      ? `${worst.label}: **${exNum(worst.owners)} of ${exNum(all)}** ${own} = **${exPct(worst.owners, all)}**, with ${exSarM(worst.ead)} EAD.`
      : "Each bar is one band; the worst band is first.",
    lookFor: "Names in the **critical and high** bands: they are the ones a stress scenario pushes into Stage 2 or default first.",
  };
}

// ---------------------------------------------------------------- scenario result

export function waterfallExplain(bars: Bar[]): ChartExplain {
  const start = bars.find((b) => b.kind === "total" || b.kind === "model");
  const end = [...bars].reverse().find((b) => b.kind === "total");
  const big = maxBy(bars.filter((b) => b.kind === "driver"), (b) => Math.abs(b.value));
  return {
    shows: "How the ECL moves from the reported figure to the scenario figure, one driver at a time.",
    formula: [
      "**Reported / start** = ECL before the scenario (the start is the same ECL recomputed by the model).",
      "**Driver bar** = the ECL change caused by that driver alone, measured as an exact Shapley value (its average effect across every order of applying the drivers).",
      "**Scenario** = start + sum of driver bars.",
    ],
    read: big && start && end
      ? `From **${exSarM(start.value)}** to **${exSarM(end.value)}**; the largest driver is **${big.label}** at **${signed(big.value)}**.`
      : "Green bars lower ECL, red bars raise it; the solid accent bars are totals.",
    lookFor: "The **one or two tallest driver bars**: they are where the scenario bites, and where a mitigating action helps most.",
  };
}

export function segmentExplain(rows: SegmentRow[], segment: string): ChartExplain {
  const big = maxBy(rows, (r) => r.ecl_after - r.ecl_before);
  return {
    shows: `ECL by ${segment.toLowerCase()} before and after the scenario (the 14 largest after the scenario).`,
    formula: [
      `**Before** = sum of ECL (SAR m) of the ${segment.toLowerCase()}'s exposures today.`,
      "**After** = the same sum with the scenario applied.",
      "**Change** = after − before.",
    ],
    read: big
      ? `${big.segment}: **${exSarM(big.ecl_before)} → ${exSarM(big.ecl_after)}**, a change of **${signed(big.ecl_after - big.ecl_before)}** (${exPct(big.ecl_after - big.ecl_before, big.ecl_before)}), the largest rise.`
      : "Compare the two bars in each row: the wider the gap, the harder the scenario hits.",
    lookFor: "Segments where the **after bar is much longer** than before relative to the others: the scenario's concentration risk.",
  };
}

export function ratingRowsExplain(rows: RatingRow[], grade: string): ChartExplain {
  const totalB = sum(rows.map((r) => r.ead_before));
  const worst = rows[rows.length - 1];
  return {
    shows: `Exposure by ${grade.toLowerCase()} before and after the scenario, best grade on the left.`,
    formula: [
      "**Before** = sum of EAD (SAR m) in the grade today.",
      "**After** = sum of EAD in the grade once the scenario has re-graded each exposure.",
      "**Share** (in the example) = EAD in the grade ÷ total EAD × 100.",
    ],
    read: worst
      ? `${worst.grade}: **${exSarM(worst.ead_before)} → ${exSarM(worst.ead_after)}** (${exPct(worst.ead_before, totalB)} → ${exPct(worst.ead_after, totalB)} of EAD).`
      : "Read each pair of bars: the after bar shows where the exposure lands once re-graded.",
    lookFor: "**After bars taller than before on the right** (weaker grades): downgrades, which raise PD and ECL.",
  };
}

export function scenarioWeightsExplain(result: Result): ChartExplain {
  const d = result.by_scenario.downturn;
  return {
    shows: "ECL under each of the three macro scenarios, before and after, with the weight each scenario carries.",
    formula: [
      "**Bar** = ECL (SAR m) computed with that scenario's macro path.",
      "**Reported ECL** = base × weight + upturn × weight + downturn × weight (the weights add up to 100%).",
    ],
    read: d
      ? `Downturn (${exNum(d.weight * 100)}% weight): **${exSarM(d.before)} → ${exSarM(d.after)}**, a change of **${signed(d.after - d.before)}**.`
      : "Compare before and after within each scenario.",
    lookFor: "A **large downturn change**: even with a small weight it moves the weighted ECL, and it shows how fragile the book is in a bad year.",
  };
}

export function compareExplain(drivers: { driver: string; delta: number; xgboost: number }[]): ChartExplain {
  const gap = maxBy(drivers, (d) => Math.abs(d.xgboost - d.delta));
  return {
    shows: "The ECL change per driver from the two methods side by side: the Delta method and XGBoost.",
    formula: [
      "**Delta method** = change in ECL from re-scoring PD with the linear sensitivities of each driver.",
      "**XGBoost** = change in ECL from re-scoring PD with the machine-learning model.",
      "**Gap** = XGBoost − Delta.",
    ],
    read: gap
      ? `${gap.driver}: Delta **${signed(gap.delta)}**, XGBoost **${signed(gap.xgboost)}**, a gap of ${signed(gap.xgboost - gap.delta)}, the largest.`
      : "Read each pair of bars: similar bars mean the two methods agree.",
    lookFor: "Drivers where the **methods disagree** strongly: the effect is non-linear there, and the result deserves a challenge.",
  };
}

// ---------------------------------------------------------------- model card

type Pt = { predicted: number; actual: number };

export function calibrationExplain(target: string, cal: Pt[], oot: Pt[]): ChartExplain {
  const set = oot.length ? oot : cal;
  const last = set[set.length - 1];
  return {
    shows: `Whether the ${target.toUpperCase()} model's predictions match what actually happened, on two held-out test sets.`,
    formula: [
      "**Point** = one decile of test rows sorted by prediction: x = mean predicted, y = mean actual.",
      "**Random 30% test** = rows held out at random; **out-of-time test** = the latest periods, never seen in training.",
      "**Perfect** = the diagonal, actual = predicted.",
    ],
    read: last
      ? `Highest ${oot.length ? "out-of-time " : ""}decile: predicted **${exNum(last.predicted, 4)}**, actual **${exNum(last.actual, 4)}**.`
      : "Points on the dotted diagonal are perfectly calibrated.",
    lookFor: "Out-of-time points **drifting off the diagonal**: the model is biased on recent data (above = under-predicts).",
  };
}

export function importanceExplain(kind: "gain" | "shap", target: string, rows: { feature: string; share_pct?: number }[]): ChartExplain {
  const top = rows[0];
  return {
    shows: `The ${Math.min(12, rows.length)} inputs that matter most to the ${target.toUpperCase()} model.`,
    formula: [kind === "gain"
      ? "**Gain share** = the error reduction from all tree splits on the input ÷ the total over all inputs × 100."
      : "**Mean |SHAP| share** = average absolute SHAP value of the input over the test rows ÷ the total over all inputs × 100."],
    read: top ? `${top.feature}: **${exNum(top.share_pct ?? 0, 1)}%** of the total, the largest.` : "The longer the bar, the more the input drives the model.",
    lookFor: "Whether the **top inputs make credit sense** (ratings, arrears, macro), and no single input dominating everything.",
  };
}

export function beeswarmExplain(features: string[]): ChartExplain {
  return {
    shows: "For each of the top inputs, how every test row's value pushed the PD prediction up or down.",
    formula: ["**Dot** = one test row; x = its SHAP value for the input (its contribution to the model output).",
      "**Colour** = the input's value for that row, blue low to red high."],
    read: features.length
      ? `Top row, **${features[0]}**: red dots on the right would mean high values of it raise the predicted PD; blue on the right, low values do.`
      : "Dots right of zero raise the prediction, left of zero lower it.",
    lookFor: "A **clean colour split** (red on one side, blue on the other): a monotonic, explainable effect.",
  };
}

export function cycleExplain(book: Record<string, number>, fitted: Record<string, number>): ChartExplain {
  const ks = Object.keys(book);
  const k = ks[ks.length - 1];
  return {
    shows: "The credit-cycle index implied by observed defaults, and the same index fitted on the macro variables (MEVs).",
    formula: ["**From observed defaults** = Z, the standard-normal shift that turns the long-run PD into the period's default rate (higher = better).",
      "**Fitted on the MEVs** = Z predicted by a regression on the macroeconomic variables."],
    read: k ? `${k}: observed Z **${exNum(book[k], 2)}**, fitted **${exNum(fitted[k], 2)}**.` : "The closer the two lines, the better the macro model explains the cycle.",
    lookFor: "Periods where the **lines diverge**: the MEVs miss part of the cycle, so scenarios on them will too.",
  };
}

export function sensitivitiesExplain(rows: { name: string; ecl_change_pct: number }[]): ChartExplain {
  const top = maxBy(rows, (r) => Math.abs(r.ecl_change_pct));
  return {
    shows: "How much the book's ECL moves for a one-standard-deviation adverse move in each macro variable.",
    formula: ["**Bar** = (ECL with the MEV moved one standard deviation adversely − base ECL) ÷ base ECL × 100."],
    read: top ? `${top.name}: **${exNum(top.ecl_change_pct, 2)}%** ECL change, the most sensitive.` : "The longer the bar, the more ECL reacts to that variable.",
    lookFor: "The **two or three variables** that move ECL most: those are the ones a scenario must get right.",
  };
}
