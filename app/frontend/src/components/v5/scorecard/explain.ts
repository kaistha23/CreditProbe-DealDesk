/**
 * R6 E4: the (i) explanations for every Scorecard Validation chart, by chart id. The
 * example is read off the chart's own figure (the current validation run).
 */

import { type ChartExplain, exNum } from "../core/chart-explain-core.ts";

type Trace = Record<string, unknown>;
type Fig = { data: Trace[]; layout?: Record<string, unknown> };
type Text = { shows: string; formula: string[]; lookFor: string; pct?: boolean };

/** What each chart shows, its formulas and what to look for. `pct`: values are shares. */
export const TEXT: Record<string, Text> = {
  roc: { shows: "How well the score separates borrowers who defaulted from those who did not, in development (grey) and monitoring.",
    formula: ["**True positive rate** = defaults with a score at or below the cut-off ÷ all defaults.",
      "**False positive rate** = non-defaults at or below the cut-off ÷ all non-defaults; each point is one cut-off.",
      "**AUC** = area under the curve; **Gini** = 2 × AUC − 1."],
    lookFor: "The monitoring curve **sagging below development** or towards the dotted diagonal (no skill): the score ranks risk less well than it did." },
  cap: { shows: "The share of all defaults captured when you take the riskiest observations first.",
    formula: ["**x** = share of observations, sorted riskiest score first.", "**y** = defaults among them ÷ all defaults.",
      "**Perfect model** catches every default first; **Random** is the diagonal."],
    lookFor: "How close the curve sits to the **perfect line**; a gap opening against development means the ranking weakened." },
  ks: { shows: "Cumulative share of defaults and of non-defaults by score, in the monitoring sample.",
    formula: ["**Defaults line** = defaults at or below the score ÷ all defaults.", "**Non-defaults line** = non-defaults at or below the score ÷ all non-defaults.",
      "**KS** = the largest vertical gap between the two lines."],
    lookFor: "A **wide gap**: the score pushes defaults to the low end. A narrowing gap against development is a warning." },
  gini_trend: { pct: true, shows: "The Gini coefficient (ranking power) period by period; grey bars are development periods.",
    formula: ["**Gini** = 2 × AUC − 1 for the period's observations (0 = random, 100% = perfect).", "**Green / amber thresholds** = the policy limits for the verdict."],
    lookFor: "Monitoring bars **falling below the amber line**, or a steady decline period after period." },
  gini_segment: { pct: true, shows: "Gini for each segment of the monitoring sample.",
    formula: ["**Gini** = 2 × AUC − 1 within the segment.", "**Colour** = the verdict against the thresholds; grey = fewer than 30 defaults, no verdict."],
    lookFor: "A segment **much weaker than the rest**: the score may not suit it." },
  ks_trend: { pct: true, shows: "The KS statistic (separation of defaults from non-defaults) period by period; grey bars are development periods.",
    formula: ["**KS** = the largest gap between the cumulative share of defaults and of non-defaults by score, for the period's observations.",
      "**Green / amber thresholds** = the policy limits for the verdict."],
    lookFor: "Monitoring bars **falling below the amber line**, or KS narrowing period after period." },
  ks_segment: { pct: true, shows: "KS for each segment of the monitoring sample.",
    formula: ["**KS** = the largest gap between the cumulative share of defaults and of non-defaults by score within the segment.",
      "**Grey** = fewer than 30 defaults, shown for reference only."],
    lookFor: "A segment whose KS is **far below the others**: the score separates risk poorly there." },
  oe_grade: { pct: true, shows: "For each grade, the default rate the model expected against the rate actually observed.",
    formula: ["**Expected PD** = average predicted probability of default of the grade.", "**Observed** = defaults ÷ observations in the grade, with its 95% interval.",
      "**Colour** = the binomial traffic light: is the gap bigger than chance explains?"],
    lookFor: "Observed markers **above the bars with red lights**: the model under-predicts risk in those grades." },
  oe_trend: { pct: true, shows: "Expected and observed default rates for the whole sample, period by period.",
    formula: ["**Expected** = average predicted PD of the period.", "**Observed** = defaults within 12 months ÷ observations of the period."],
    lookFor: "Observed **staying above expected** for several periods: the PD is too low and needs recalibration." },
  psi_trend: { shows: "How much the score distribution has shifted against development, period by period.",
    formula: ["**PSI** = Σ over score bands of (actual share − development share) × ln(actual share ÷ development share).",
      "**Thresholds**: below 0.10 stable, 0.10 to 0.25 watch, above 0.25 shifted."],
    lookFor: "PSI **climbing towards 0.25**: the population scored today differs from the one the model was built on." },
  score_dist: { pct: true, shows: "The share of observations in each score band, development against the latest period.",
    formula: ["**Bar** = observations in the band ÷ all observations of the sample."],
    lookFor: "The latest bars **shifting left or right** of development: the population has moved." },
  csi_bar: { shows: "How much each input variable's distribution has shifted against development.",
    formula: ["**CSI** = Σ over the variable's bins of (actual share − development share) × ln(actual ÷ development).",
      "**Colour**: green up to 0.10, amber up to 0.25, red above."],
    lookFor: "**Red or amber variables**: their shift explains a moving score." },
  csi_heat: { shows: "CSI for every variable (rows) in every period (columns); development periods are the reference, so zero.",
    formula: ["**Cell** = CSI of the variable in the period = Σ (actual share − development share) × ln(actual ÷ development)."],
    lookFor: "A row **getting darker over time**: a variable drifting steadily, not a one-off." },
  drift: { shows: "The average score of each period against the development mean.",
    formula: ["**Mean score** = sum of scores ÷ observations in the period.", "**Development mean** = the same over the development sample."],
    lookFor: "A **persistent move away** from the development line: a population or a data change." },
  woe: { shows: "The weight of evidence of each bin of this variable, development against monitoring.",
    formula: ["**WoE** = ln(share of non-defaults in the bin ÷ share of defaults in the bin).", "Positive WoE = safer than average; negative = riskier."],
    lookFor: "Monitoring bars **changing sign or order** against development: the variable no longer separates risk the same way." },
  iv_bar: { shows: "The information value (predictive power) of each variable, development against monitoring.",
    formula: ["**IV** = Σ over bins of (share of non-defaults − share of defaults) × WoE.", "Verdict: green from 0.10, amber 0.02 to 0.10, red below 0.02."],
    lookFor: "A variable whose **monitoring IV has fallen** well below development: it is losing power." },
  corr: { shows: "How strongly each pair of WoE-transformed variables moves together, in the monitoring sample.",
    formula: ["**Cell** = Pearson correlation of the two variables' WoE values (−1 to 1); the diagonal is 1."],
    lookFor: "**Off-diagonal cells near ±1**: two variables carry the same information, which makes the weights unstable." },
  vif: { shows: "The variance inflation factor of each variable: how much of it the other variables already explain.",
    formula: ["**VIF** = 1 ÷ (1 − R²), with R² from regressing the variable on all the others.", "**Colour**: green up to 5, amber up to 10, red above."],
    lookFor: "**VIF above 5**: collinearity; the variable's weight cannot be trusted on its own." },
  ovr_rate: { pct: true, shows: "The share of decisions where a credit officer overrode the score, period by period.",
    formula: ["**Override rate** = overridden decisions ÷ all scored decisions in the period."],
    lookFor: "A **rising override rate**: officers trust the score less, often a sign it is out of date." },
  ovr_outcome: { pct: true, shows: "The default rate of each override decision, observed against expected.",
    formula: ["**Observed** = defaults ÷ observations with that decision.", "**Expected** = their average predicted PD."],
    lookFor: "**Upward overrides defaulting more than expected**: the overrides are destroying value." },
};

const isRef = (t: Trace) => /threshold|perfect|random|no skill|development mean/i.test(String(t.name ?? ""));
const nums = (v: unknown): number[] => (Array.isArray(v) ? v.map((x) => Number(x)) : []);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x)) : []);

function val(v: number, pct?: boolean): string {
  if (!Number.isFinite(v)) return "n/a";
  return pct ? `${exNum(v * 100, 1)}%` : exNum(v, Math.abs(v) >= 10 ? 1 : 3);
}

/** The point of a curve whose x is closest to `at`. */
function near(t: Trace, at: number): { x: number; y: number } | null {
  const xs = nums(t.x), ys = nums(t.y);
  let best = -1;
  for (let i = 0; i < xs.length; i++) if (Number.isFinite(xs[i]) && (best < 0 || Math.abs(xs[i] - at) < Math.abs(xs[best] - at))) best = i;
  return best < 0 ? null : { x: xs[best], y: ys[best] };
}

/** The example sentence for a chart, read from its figure. */
export function exampleFor(id: string, fig: Fig): string {
  const key = id.startsWith("woe_") ? "woe" : id;
  const pct = TEXT[key]?.pct;
  const traces = (fig.data ?? []).filter((t) => !isRef(t));
  const byName = (re: RegExp) => traces.find((t) => re.test(String(t.name ?? "")));
  if (key === "roc" || key === "cap") {
    const mon = byName(/monitoring/i) ?? traces[0];
    const p = mon ? near(mon, 0.2) : null;
    if (!p) return "";
    return key === "roc"
      ? `Monitoring: at a false positive rate of **${val(p.x, true)}** the score catches **${val(p.y, true)}** of defaults.`
      : `Monitoring: the riskiest **${val(p.x, true)}** of observations hold **${val(p.y, true)}** of the defaults.`;
  }
  if (key === "ks") {
    const d = byName(/^defaults/i), g = byName(/non-defaults/i);
    if (!d || !g) return "";
    const xs = nums(d.x), dy = nums(d.y), gy = nums(g.y);
    let i = -1;
    for (let k = 0; k < xs.length; k++) if (Number.isFinite(dy[k] - gy[k]) && (i < 0 || Math.abs(dy[k] - gy[k]) > Math.abs(dy[i] - gy[i]))) i = k;
    if (i < 0) return "";
    return `At score **${exNum(xs[i], 0)}**: **${val(dy[i], true)}** of defaults against **${val(gy[i], true)}** of non-defaults score at or below it; the gap, **${val(Math.abs(dy[i] - gy[i]), true)}**, is the KS.`;
  }
  const heat = (fig.data ?? []).find((t) => t.type === "heatmap");
  if (heat) {
    const z = Array.isArray(heat.z) ? (heat.z as unknown[][]) : [];
    const xs = strs(heat.x), ys = strs(heat.y);
    let bi = -1, bj = -1;
    z.forEach((row, i) => (Array.isArray(row) ? row : []).forEach((v, j) => {
      const n = Number(v);
      if (v == null || !Number.isFinite(n) || (key === "corr" && xs[j] === ys[i])) return;
      if (bi < 0 || Math.abs(n) > Math.abs(Number(z[bi][bj]))) { bi = i; bj = j; }
    }));
    if (bi < 0) return "";
    return key === "corr"
      ? `The strongest pair is **${ys[bi]}** and **${xs[bj]}** at **${val(Number(z[bi][bj]))}**.`
      : `The largest shift is **${ys[bi]}** in **${xs[bj]}**, CSI **${val(Number(z[bi][bj]))}**.`;
  }
  const main = traces[0];
  if (!main) return "";
  const horizontal = main.orientation === "h";
  const cats = strs(horizontal ? main.y : main.x);
  const v1 = nums(horizontal ? main.x : main.y);
  if (!cats.length) return "";
  // Horizontal bars are drawn bottom-up, so the top bar is the last; for vertical, the latest category is the last.
  const i = cats.length - 1;
  const second = traces[1];
  const v2 = second ? nums(horizontal ? second.x : second.y) : [];
  const n1 = String(main.name ?? "Value"), n2 = String(second?.name ?? "");
  return `${cats[i].replace(/<br>/g, " ")}: ${n1} **${val(v1[i], pct)}**${second && Number.isFinite(v2[i]) ? `, ${n2} **${val(v2[i], pct)}**` : ""}.`;
}

/** The full explanation of a Scorecard Validation chart. */
export function scorecardChartExplain(id: string, title: string, fig: Fig): ChartExplain {
  const t = TEXT[id.startsWith("woe_") ? "woe" : id];
  const ex = exampleFor(id, fig);
  return {
    shows: t?.shows ?? `${title}.`,
    formula: t?.formula ?? ["**Each series** = the figure the validation engine computed for the run."],
    read: ex ? `${ex} Hover any point for its exact value.` : "Hover any point for its exact value; the legend names each series.",
    lookFor: t?.lookFor ?? "A **move against development** or a value crossing its threshold.",
  };
}
