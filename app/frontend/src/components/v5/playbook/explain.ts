/**
 * R6 E4: the (i) explanation of a Playbook chart. A Playbook chart can come from any
 * screen, so the text is matched on the chart's title (Playbook's own content charts and
 * the Scorecard Validation key charts); anything else gets an explanation built from the
 * figure itself (its series and axes). The example is always read off the figure.
 */

import { type ChartExplain, exNum } from "../core/chart-explain-core.ts";
import { scorecardChartExplain } from "../scorecard/explain.ts";

type Trace = Record<string, unknown>;
type Fig = { data?: Trace[]; layout?: Record<string, unknown> } | null;
type Text = { shows: string; formula: string[]; lookFor: string };

/** Playbook's own content charts (backend/playbook_v5/content.py), by title. */
const CONTENT: [RegExp, Text][] = [
  [/ECL and EAD, last/i, { shows: "The book's exposure (bars) and expected credit loss (line), quarter by quarter.",
    formula: ["**EAD (SAR bn)** = sum of exposure at default of every facility in scope.", "**ECL (SAR m)** = sum of PD × LGD × EAD across the facilities."],
    lookFor: "ECL rising **faster than EAD**: the book is getting riskier, not just bigger." }],
  [/EAD by stage/i, { shows: "Exposure split by IFRS 9 stage at two period ends.",
    formula: ["**Stage n** = sum of EAD (SAR bn) of the facilities in that stage.", "**Share** = stage EAD ÷ total EAD × 100."],
    lookFor: "Exposure **moving from Stage 1 into Stage 2 or 3** between the two periods: it drives ECL up." }],
  [/Borrowers by Early Warning band/i, { shows: "How many borrowers sit in each Early Warning band, in two periods.",
    formula: ["**Bar** = count of borrowers whose worst band is that band at the period end."],
    lookFor: "Names **moving into the high and critical bands** between the two periods." }],
  [/ECL change by sub-sector/i, { shows: "Which sub-sectors drove the sector's ECL change between two periods.",
    formula: ["**Bar** = ECL of the sub-sector at the later period − ECL at the earlier period (SAR m)."],
    lookFor: "**One or two sub-sectors** explaining most of the change: a targeted, not sector-wide, problem." }],
  [/DSCR and leverage/i, { shows: "Debt service cover and leverage over the last eight quarters.",
    formula: ["**DSCR (x)** = cash available for debt service ÷ debt service due.", "**Leverage (x)** = total debt ÷ EBITDA."],
    lookFor: "**DSCR falling towards 1x** while leverage rises: debt is outgrowing the cash to pay it." }],
];

/** The Scorecard Validation key charts (backend/scorecard_v5/playbook.KEY_CHARTS), by title. */
const SCORECARD: [RegExp, string][] = [
  [/^ROC curve/i, "roc"], [/^CAP curve/i, "cap"], [/^Gini by period/i, "gini_trend"], [/^Observed vs expected by grade/i, "oe_grade"],
  [/^Observed vs expected over time/i, "oe_trend"], [/^Score PSI/i, "psi_trend"], [/^CSI by variable/i, "csi_bar"],
  [/^Score distribution/i, "score_dist"], [/^Information value/i, "iv_bar"], [/^Default rate by override/i, "ovr_outcome"],
];

const axisTitle = (layout: Record<string, unknown> | undefined, key: string): string => {
  const ax = layout?.[key] as Record<string, unknown> | undefined;
  const t = ax?.title as unknown;
  return typeof t === "string" ? t : typeof (t as Record<string, unknown>)?.text === "string" ? String((t as Record<string, unknown>).text) : "";
};

function latest(t: Trace): { x: string; y: number } | null {
  const horizontal = t.orientation === "h";
  const cats = Array.isArray(horizontal ? t.y : t.x) ? (horizontal ? t.y : t.x) as unknown[] : [];
  const vals = Array.isArray(horizontal ? t.x : t.y) ? (horizontal ? t.x : t.y) as unknown[] : Array.isArray(t.values) ? t.values as unknown[] : [];
  const labels = Array.isArray(t.labels) ? t.labels as unknown[] : cats;
  for (let i = vals.length - 1; i >= 0; i--) {
    const v = Number(vals[i]);
    if (vals[i] != null && Number.isFinite(v)) return { x: String(labels[i] ?? ""), y: v };
  }
  return null;
}

const show = (v: number) => exNum(v, Number.isInteger(v) ? 0 : Math.abs(v) < 10 ? 2 : 1);

/** The example: the latest value of up to three series. */
function example(fig: Fig): string {
  const pts = (fig?.data ?? []).map((t) => ({ name: String(t.name ?? "Value"), p: latest(t) })).filter((r) => r.p).slice(0, 3);
  if (!pts.length) return "";
  const at = pts[0].p!.x;
  return `${at ? `${at}: ` : ""}${pts.map((r) => `${r.name} **${show(r.p!.y)}**`).join(", ")}.`;
}

export function playbookChartExplain(title: string, fig: Fig): ChartExplain {
  const sc = SCORECARD.find(([re]) => re.test(title));
  if (sc && fig?.data?.length) return scorecardChartExplain(sc[1], title, { data: fig.data, layout: fig.layout });
  const known = CONTENT.find(([re]) => re.test(title))?.[1];
  const ex = example(fig);
  const read = ex ? `${ex} Hover any point for its exact value.` : "Hover any point for its exact value; the legend names each series.";
  if (known) return { ...known, read };
  const traces = fig?.data ?? [];
  const yT = axisTitle(fig?.layout, "yaxis"), xT = axisTitle(fig?.layout, "xaxis");
  const names = traces.map((t) => String(t.name ?? "")).filter(Boolean);
  const formula = names.length
    ? names.slice(0, 4).map((n) => `**${n}** = the ${yT ? yT.toLowerCase() : "value"} computed by the source screen for each ${xT ? xT.toLowerCase() : "point"}, exactly as published there.`)
    : [`**Each point** = the ${yT ? yT.toLowerCase() : "value"} computed by the source screen, exactly as published there.`];
  return {
    shows: `${title || "This chart"}${names.length ? `: ${names.slice(0, 4).join(", ")}` : ""}${xT ? `, by ${xT.toLowerCase()}` : ""}.`,
    formula,
    read,
    lookFor: "The **latest point against the earlier ones**, and any series moving against the others; open the source screen for the full calculation.",
  };
}
