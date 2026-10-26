"use client";

/**
 * A chart in an answer (PLAN_R12 N2, I10 b): drawn with Plotly through the one surface, in the house theme. Takes the
 * shared conversational chart block (docs/v5/CONVO_API.md: kind bar | hbar | line | stacked, x, y[], optional y2).
 * Rating axes read AAA to D; hovers are formatted by each series' key (never a raw float).
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { seriesColor } from "@/lib/plotly-theme";
import { hoverTemplate, kindOf } from "@/lib/v5/format";
import { orderRatingRows, ratingAxis } from "@/lib/v5/ratings";

import { A } from "./styles";

export interface AnswerChartBlock {
  type?: string;
  kind?: string;
  title?: string;
  x: string;
  y: string[];
  y2?: string | null;
  rows: Record<string, unknown>[];
  labels?: Record<string, string>;
}

/** A series' hover by its key (PLAN_R6 E2); a percentage column whose values are already points says so. */
export function seriesHover(key: string, values: unknown[], horizontal = false, name = ""): string {
  const pts = kindOf(key) === "pct_auto" && values.some((v) => typeof v === "number" && Math.abs(v) > 1.5);
  return hoverTemplate(pts ? "pct" : key, horizontal ? "x" : "y", horizontal ? "y" : "x", name);
}

/** The Plotly figure for a chart block (exported for tests and for modules drawing the same block their own way). */
export function answerFigure(raw: AnswerChartBlock): { data: Record<string, unknown>[]; layout: Record<string, unknown>; height: number } {
  const block = { ...raw, rows: orderRatingRows(raw.rows as Record<string, string | number>[], raw.x) as Record<string, unknown>[] };
  const xs = block.rows.map((r) => (typeof r[block.x] === "string" ? String(r[block.x]).replace(/_/g, " ") : r[block.x]) as string | number);
  const catOrder = ratingAxis(xs);
  const lab = (k: string) => block.labels?.[k] ?? k;
  const horizontal = block.kind === "hbar";
  const data: Record<string, unknown>[] = block.y.map((y, i) => {
    const vals = block.rows.map((r) => r[y] as number);
    if (block.kind === "line") {
      return { type: "scatter", mode: xs.length <= 12 ? "lines+markers" : "lines", name: lab(y), x: xs, y: vals,
               line: { color: seriesColor(i), width: 2 }, marker: { size: 6 }, hovertemplate: seriesHover(y, vals, false, lab(y)) };
    }
    return horizontal
      ? { type: "bar", orientation: "h", name: lab(y), y: xs, x: vals, marker: { color: seriesColor(i), cornerradius: 3 }, hovertemplate: seriesHover(y, vals, true, lab(y)) }
      : { type: "bar", name: lab(y), x: xs, y: vals, marker: { color: seriesColor(i), cornerradius: 3 }, hovertemplate: seriesHover(y, vals, false, lab(y)) };
  });
  if (block.y2) {
    const v2 = block.rows.map((r) => r[block.y2 as string] as number);
    data.push({ type: "scatter", mode: "lines+markers", name: lab(block.y2), x: xs, y: v2,
                yaxis: "y2", line: { color: seriesColor(block.y.length), width: 2 }, hovertemplate: seriesHover(block.y2, v2, false, lab(block.y2)) });
  }
  const many = data.length > 1;
  const layout: Record<string, unknown> = {
    barmode: block.kind === "stacked" ? "stack" : "group",
    showlegend: many,
    hovermode: horizontal ? "y unified" : "x unified",
    margin: { l: horizontal ? 150 : 52, r: block.y2 ? 52 : 16, t: many ? 28 : 8, b: 52 },
    xaxis: horizontal ? { title: { text: block.y.length === 1 ? lab(block.y[0]) : "" }, zeroline: true }
      : { title: { text: lab(block.x) }, tickangle: xs.length > 8 ? -35 : 0, showgrid: false, ...catOrder },
    yaxis: horizontal ? { autorange: "reversed", showgrid: false, ...catOrder } : { title: { text: block.y.length === 1 ? lab(block.y[0]) : "" } },
    ...(block.y2 ? { yaxis2: { overlaying: "y", side: "right", showgrid: false, title: { text: lab(block.y2) } } } : {}),
  };
  const height = (horizontal ? Math.max(220, 26 * xs.length + 60) : 300) + (many ? 24 : 0);
  return { data, layout, height };
}

export function AnswerChart({ block, testId = "answer-chart", height }: { block: AnswerChartBlock; testId?: string; height?: number }) {
  const fig = React.useMemo(() => answerFigure(block), [block]);
  return (
    <figure className={`${A.card} min-w-0 px-3 pt-2.5 pb-1.5`} data-testid={testId}>
      {block.title ? <figcaption className="pb-1 text-[12.5px] font-semibold text-text-primary">{block.title}</figcaption> : null}
      <Plot data={fig.data} layout={fig.layout} height={height ?? fig.height} ariaLabel={block.title || "Chart"}
            filename={(block.title || "chart").replace(/\W+/g, "-").toLowerCase()} />
    </figure>
  );
}
