/**
 * How a Scorecard Validation figure is drawn in the browser (PLAN_R4 B3).
 *
 * The figure spec comes from the Scorecard service already in the house chart style (horizontal bars for
 * variable charts, wrapped labels, automargin, legend above the plot). In the browser the chart title is the
 * card's own heading (it wraps on a narrow card, a Plotly title is clipped), so the figure drops its title
 * and its top margin shrinks to the legend.
 */

export type Figure = { data: Record<string, unknown>[]; layout: Record<string, unknown> };

/** Charts drawn across the full width of the grid: heatmaps (labels on both axes). */
export const WIDE = new Set(["csi_heat", "corr"]);

export const DEFAULT_HEIGHT = 320;

export function chartTitle(fig: Figure, fallback: string): string {
  const t = fig.layout?.title as { text?: unknown } | string | undefined;
  const text = typeof t === "string" ? t : typeof t?.text === "string" ? t.text : "";
  return text || fallback;
}

export function browserLayout(fig: Figure): Record<string, unknown> {
  const layout = { ...(fig.layout ?? {}) };
  const legend = layout.showlegend !== false && (fig.data ?? []).filter((t) => t.name && t.type !== "heatmap" && t.showlegend !== false).length > 1;
  const margin = { l: 8, r: 16, b: 44, pad: 4, ...((layout.margin as Record<string, unknown>) ?? {}) };
  layout.title = { text: "" };
  layout.margin = { ...margin, t: legend ? 36 : 12 };
  layout.legend = { orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom", font: { size: 11 }, bgcolor: "rgba(0,0,0,0)", ...((layout.legend as Record<string, unknown>) ?? {}) };
  for (const key of ["xaxis", "yaxis"]) layout[key] = { ...((layout[key] as Record<string, unknown>) ?? {}), automargin: true };
  const height = typeof layout.height === "number" ? layout.height : DEFAULT_HEIGHT;
  // The figure's height counted the title band, which the card heading now carries.
  layout.height = Math.max(240, height - (legend ? 40 : 36));
  return layout;
}
