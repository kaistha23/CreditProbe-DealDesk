/** R6 E4: the (i) explanations for every Early Warning chart, built from the chart's own figures. */

import type { Card as LevelCard, CustomerDetail, RatingMix, TrendPoint } from "@/lib/v5/ews";

import { type ChartExplain, exNum, exPct, exSarM as sarM, lastWith, maxBy, periodLabel as shortPeriod } from "../core/chart-explain-core.ts";

/** The level trend: warned, high or critical, forward risk. */
export function levelTrendExplain(trend: TrendPoint[], owners: string): ChartExplain {
  const p = lastWith(trend, (t) => t.customers_warned);
  const first = trend.find((t) => t.customers_warned != null);
  return {
    shows: `How many ${owners} the Early Warning model flagged in each of the last ${trend.length} periods, and how many of them are serious.`,
    formula: [
      `**Warned ${owners}** = count of ${owners} whose warning score is at or above the warning threshold (any band from watch up).`,
      `**High or critical** = count of warned ${owners} whose score falls in the high or critical band.`,
      `**Forward risk** = count of warned ${owners} not yet in default or 30+ days past due: problems still ahead of us.`,
    ],
    read: p
      ? `At ${shortPeriod(p.period)}: **${exNum(p.customers_warned)}** ${owners} warned, of which **${exNum(p.high_or_critical)}** high or critical and **${exNum(p.forward_risk)}** forward risk`
        + (first && first !== p ? `; at ${shortPeriod(first.period)} warned was ${exNum(first.customers_warned)}.` : ".")
      : `Each point is one period; the higher the line, the more ${owners} are flagged.`,
    lookFor: "A **rising high-or-critical line** even when warned is flat (problems deepening), and forward risk growing faster than warned (new trouble not yet in arrears).",
  };
}

/** A card's full trend dialog (and its three sparklines). */
export function cardTrendExplain(trend: TrendPoint[], owners: string, label?: string): ChartExplain {
  const p = lastWith(trend, (t) => t.customers_warned);
  const who = label ? `${label}: ` : "";
  return {
    shows: `${label ?? "This card"} over ${trend.length} periods: the counts of flagged ${owners}, the default-entry rate and the exposure in the high or critical bands.`,
    formula: [
      `**Warned / high or critical / forward risk** = counts of ${owners} flagged, in the high or critical band, and flagged but not yet in arrears.`,
      `**Default-entry rate (%)** = ${owners} that entered default in the period ÷ ${owners} not in default at its start × 100.`,
      "**High/critical EAD (SAR m)** = sum of exposure at default of the high or critical names.",
    ],
    read: p
      ? `${who}at ${shortPeriod(p.period)}, **${exNum(p.customers_warned)}** ${owners} warned, default-entry rate **${p.odr_pct == null ? "n/a" : `${exNum(p.odr_pct, 2)}%`}**, high/critical EAD **${sarM(p.exposure_severe)}**.`
      : `Each panel shares the period axis; read across a period to compare the three.`,
    lookFor: "Warned and high/critical EAD **rising together** ahead of a rise in the default-entry rate: the warnings usually lead defaults by one or two periods.",
  };
}

/** Child segments compared: warned and high/critical exposure. */
export function compareExplain(cards: LevelCard[], owners: string, kind: string): ChartExplain {
  const top = maxBy(cards, (c) => c.customers_warned);
  return {
    shows: `Each of the ${cards.length} ${kind || "segments"} side by side: how many ${owners} are warned (left axis) and how much exposure sits in the high or critical bands (right axis).`,
    formula: [
      `**Warned ${owners}** = count of ${owners} in the segment with a warning score at or above the threshold.`,
      "**High/critical exposure (SAR m)** = sum of EAD of the segment's names in the high or critical band.",
      `**Share warned** (in the example) = warned ÷ all ${owners} in the segment × 100.`,
    ],
    read: top
      ? `${top.label}: **${exNum(top.customers_warned)} of ${exNum(top.customers)}** ${owners} warned = **${exPct(top.customers_warned, top.customers)}**, with **${sarM(top.exposure_severe)}** high/critical exposure.`
      : "Each pair of bars is one segment; click a bar to open it.",
    lookFor: "A segment whose **red bar is tall relative to its orange bar**: few names but large severe exposure, i.e. concentration. Click a bar to drill in.",
  };
}

/** Borrowers by rating grade, all and warned. */
export function ratingExplain(mix: RatingMix[], owners: string): ChartExplain {
  const worst = maxBy(mix, (r) => (r.borrowers ? r.warned / r.borrowers : null));
  return {
    shows: `How the ${owners} spread across rating grades (AAA best, D worst) and how many in each grade are warned.`,
    formula: [
      `**${owners.charAt(0).toUpperCase() + owners.slice(1)}** = count of ${owners} with that rating.`,
      `**Warned** = count of those ${owners} with a warning score at or above the threshold.`,
      "**Warned share** (in the example) = warned ÷ all in the grade × 100.",
    ],
    read: worst
      ? `${worst.rating}: **${exNum(worst.warned)} of ${exNum(worst.borrowers)}** ${owners} warned = **${exPct(worst.warned, worst.borrowers)}**, the highest share of any grade.`
      : "Compare the two bars in each grade; the closer they are, the more of the grade is flagged.",
    lookFor: "Warnings in **good grades** (A and above): the rating has not yet caught up with the signals, a candidate for review.",
  };
}

/** One customer's history: score, days past due, exposure. */
type HistoryPoint = Pick<CustomerDetail["history"][number], "period"> & {
  score: number | null; dpd: number | null; exposure: number | null; band?: string | null;
};

export function customerHistoryExplain(history: HistoryPoint[], warnedMin: number, owner: string): ChartExplain {
  const p = history[history.length - 1];
  return {
    shows: `This ${owner}'s warning score, days past due and exposure, period by period, on one shared time axis.`,
    formula: [
      "**Score** = sum of the weights of the Early Warning rules that fired for this name in the period (higher is worse); its band is shown on hover.",
      "**Days past due** = the most overdue days on any of its exposures at the period end.",
      "**Exposure (SAR m)** = sum of its exposure at default across facilities.",
    ],
    read: p
      ? `At ${shortPeriod(p.period)}: score **${exNum(p.score)}**${p.band ? ` (band ${p.band})` : ""} against a warning threshold of **${exNum(warnedMin)}**, **${exNum(p.dpd)}** days past due, exposure **${sarM(p.exposure)}**.`
      : `The dotted lines mark the warning threshold (${exNum(warnedMin)}) and 30 days past due.`,
    lookFor: "The **score crossing the dotted threshold before** days past due rise: that is the early warning working. Also watch exposure growing while the score worsens.",
  };
}
