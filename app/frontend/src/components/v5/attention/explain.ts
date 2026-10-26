/** R6 E4: the (i) explanations for the four charts of a Cockpit card in the v5 drawer, built from the chart's own figures. */

import { type ChartsPayload, type ContribView, fmt } from "../../../lib/v5/attention-figures.ts";
import { type ChartExplain, exPct, maxBy } from "../core/chart-explain-core.ts";

const measureFormula = (c: ChartsPayload) => (c.kind === "share"
  ? `**${c.measure_label}** is a percentage (${c.unit || "%"}): the measure's numerator ÷ its base × 100, for the ${c.period_noun}.`
  : `**${c.measure_label}** is an amount in SAR million: the sum over the exposures in scope, for the ${c.period_noun}.`);

export function trendExplain(c: ChartsPayload): ChartExplain {
  const name = c.segment_label ?? c.segment;
  const t = c.trend;
  const i = t.current_index;
  const cur = t.segment[i];
  const prev = i > 0 ? t.segment[i - 1] : null;
  const book = t.book[i];
  const hasBook = (c.scope ?? "segment") === "segment" && t.book.some((v) => v != null);
  return {
    shows: `${c.measure_label} for ${name} over the last ${t.periods.length} ${c.period_noun}s${hasBook ? ", with the whole book as a reference line" : ""}.`,
    formula: [
      measureFormula(c),
      ...(hasBook ? [`**Book line** = the same measure for the whole ${c.domain} book.`] : []),
      `**Change** = this ${c.period_noun} − the previous ${c.period_noun}.`,
    ],
    read: cur != null
      ? `${t.periods[i]}: **${fmt(cur, c.kind)}**${prev != null ? `, against **${fmt(prev, c.kind)}** in ${t.periods[i - 1]}` : ""}${hasBook && book != null ? `; the book is at ${fmt(book, c.kind)}` : ""}.`
      : `Each point is one ${c.period_noun}; the highlighted point is the current one.`,
    lookFor: hasBook
      ? "The segment line **pulling away from the book line**: a move specific to this segment, not the whole market."
      : `A **break in the trend** in the latest ${c.period_noun} after a stable run: that is what put this card on the list.`,
  };
}

export function peersExplain(c: ChartsPayload): ChartExplain {
  const items = c.peers.items;
  const me = items.find((p) => p.is_segment) ?? maxBy(items, (p) => p.value);
  const sorted = [...items].sort((a, b) => b.value - a.value);
  const rank = me ? sorted.indexOf(me) + 1 : 0;
  return {
    shows: `${c.measure_label} in ${c.period} for every ${c.dimension_label.toLowerCase()} side by side${c.peers.book != null ? `, with the ${c.peers.book_label.toLowerCase()} marked` : ""}.`,
    formula: [
      measureFormula(c),
      `**Bar** = that measure for one ${c.dimension_label.toLowerCase()}; the highlighted bar is the card's own.`,
      ...(c.peers.book != null ? [`**${c.peers.book_label}** = the same measure across the whole book.`] : []),
    ],
    read: me
      ? `${me.label ?? me.segment}: **${fmt(me.value, c.kind)}**, rank **${rank} of ${items.length}**${c.peers.book != null ? ` against the ${c.peers.book_label.toLowerCase()} at ${fmt(c.peers.book, c.kind)}` : ""}.`
      : "The longer the bar, the higher the measure.",
    lookFor: "Whether the card's segment is an **outlier** or simply sits where its peers do: an outlier deserves its own action.",
  };
}

export function contributorsExplain(c: ChartsPayload, view: ContribView | undefined): ChartExplain {
  const big = view ? maxBy(view.items, (i) => Math.abs(i.change)) : undefined;
  const by = view?.label.toLowerCase() ?? "contributor";
  return {
    shows: `How the movement from ${c.contributors.before} to ${c.contributors.after} breaks down, by ${by}.`,
    formula: [
      `**First and last bars** = the measure at ${c.contributors.before} and at ${c.contributors.after}.`,
      `**Each bar between** = its own change: value at ${c.contributors.after} − value at ${c.contributors.before}.`,
      "**Total change** = sum of the bars between = last bar − first bar.",
    ],
    read: big && view
      ? `${big.name}: **${fmt(big.from, c.kind)} → ${fmt(big.to, c.kind)}**, a change of **${fmt(big.change, c.kind)}**, out of ${fmt(view.total_change, c.kind)} in total${view.total_change ? ` (${exPct(big.change, view.total_change)})` : ""}.`
      : "Red bars push the measure up, green bars bring it down.",
    lookFor: "Whether **one contributor explains most** of the movement (a targeted issue) or it is spread across many (a book-wide trend).",
  };
}

export function stageMixExplain(c: ChartsPayload): ChartExplain {
  const s = c.stage_mix;
  const j = s.ead.length - 1;
  const row = s.ead[j] ?? [];
  const total = row.reduce((a, b) => a + b, 0);
  const k2 = s.stages.indexOf(2);
  return {
    shows: `The exposure of the card's scope by IFRS 9 stage, ${s.periods[0]} against ${s.periods[1]} (${s.basis}).`,
    formula: [
      "**Stage 1** = performing, 12-month ECL; **Stage 2** = significant increase in credit risk, lifetime ECL; **Stage 3** = credit-impaired.",
      "**Segment of a bar** = EAD (SAR m) in the stage; the label is EAD in the stage ÷ total EAD × 100.",
    ],
    read: k2 >= 0 && total
      ? `${s.periods[1]}: Stage 2 holds **${fmt(row[k2], "amount")} of ${fmt(total, "amount")}** = **${exPct(row[k2], total)}**` +
        (s.ead[0] ? `, against ${exPct(s.ead[0][k2], s.ead[0].reduce((a, b) => a + b, 0))} in ${s.periods[0]}.` : ".")
      : "Compare the two bars: the colours show where the exposure sits.",
    lookFor: "The **amber (Stage 2) and red (Stage 3) parts growing** between the two periods: that is what moves ECL most.",
  };
}
