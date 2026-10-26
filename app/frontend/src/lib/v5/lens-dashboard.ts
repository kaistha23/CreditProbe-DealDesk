/**
 * R13 L (J8): the lens dashboard's layout rules, as plain functions (node-testable; no DOM, no React).
 *
 *  - `stripCols`     the KPI strip: 6-8 small tiles in one row when there is room, else two even rows
 *  - `lensFigure`    a tile's Plotly figure on the house theme: the engine's hard-coded font, text colour and grid
 *                    give way to `lib/plotly-theme.ts`, its palette hexes become theme tokens (light and dark),
 *                    multi-series charts get the house legend on top
 *  - `deltaArrow`    the arrow and tone of a KPI change
 *  - `toneOf`        a movement line's marker colour
 */

export type Figure = Record<string, unknown>;

/** The engine's palette (backend/lenses_v5/engine.py V5_PALETTE, first eight) -> the theme's chart tokens. */
const HEX_TO_TOKEN: Record<string, string> = {
  "#2563a8": "var(--ipm-chart-1)", "#c2410c": "var(--ipm-chart-2)", "#0e8a6a": "var(--ipm-chart-3)", "#7c3aed": "var(--ipm-chart-4)",
  "#a16207": "var(--ipm-chart-5)", "#0891b2": "var(--ipm-chart-6)", "#be185d": "var(--ipm-chart-7)", "#3f6212": "var(--ipm-chart-8)",
  "#a92a25": "var(--ipm-negative)", "#64748b": "var(--ipm-border-strong)", "#cbd5e1": "var(--ipm-surface-sunken)",
};

const isObj = (v: unknown): v is Figure => Boolean(v) && typeof v === "object" && !Array.isArray(v);

function tokenise<T>(v: T): T {
  if (typeof v === "string") return (HEX_TO_TOKEN[v.toLowerCase()] ?? v) as T;
  if (Array.isArray(v)) return v.map(tokenise) as T;
  if (isObj(v)) {
    const out: Figure = {};
    for (const [k, x] of Object.entries(v)) out[k] = tokenise(x);
    return out as T;
  }
  return v;
}

/** Category names longer than this are shortened on a horizontal bar axis. */
export const LABEL_MAX = 26;

export function shortLabel(s: string): string {
  return s.length > LABEL_MAX ? s.slice(0, LABEL_MAX - 1).trimEnd() + "…" : s;
}

/** Layout keys the engine sets that the house theme owns. */
const THEME_OWNED = ["font", "paper_bgcolor", "plot_bgcolor", "hoverlabel"] as const;

export function lensFigure(fig: { data: Figure[]; layout: Figure }): { data: Figure[]; layout: Figure } {
  const data = tokenise(fig.data);
  const layout: Figure = { ...fig.layout };
  for (const k of THEME_OWNED) delete layout[k];
  for (const key of Object.keys(layout)) {
    if (/^[xy]axis\d*$/.test(key) && isObj(layout[key])) {
      const ax = { ...(layout[key] as Figure) };
      delete ax.gridcolor;
      layout[key] = ax;
    }
  }
  // horizontal bars: long category names are shortened on the axis (the hover keeps the full name), and the margin
  // is left to Plotly's automargin instead of the engine's fixed 140 px
  const hbar = data.some((t) => t.type === "bar" && t.orientation === "h");
  if (hbar && isObj(layout.yaxis)) {
    const names = Array.from(new Set(data.flatMap((t) => (Array.isArray(t.y) ? (t.y as unknown[]).map(String) : []))));
    if (names.some((n) => n.length > LABEL_MAX)) {
      layout.yaxis = { ...(layout.yaxis as Figure), tickmode: "array", tickvals: names, ticktext: names.map(shortLabel) };
    }
    if (isObj(layout.margin)) { const m = { ...(layout.margin as Figure) }; delete m.l; layout.margin = m; }
  }
  // heatmaps (migration, roll rates): the row-axis title needs Plotly's automargin, not a fixed left margin
  if (data.some((t) => t.type === "heatmap") && isObj(layout.margin)) {
    const m = { ...(layout.margin as Figure) }; delete m.l; layout.margin = m;
  }
  // value axes over large amounts: no decimals on the ticks ("10,000", not "10,000.0"), so they never rotate
  for (const [ax, dim] of [["xaxis", "x"], ["yaxis", "y"]] as const) {
    const a = layout[ax];
    if (!isObj(a) || a.tickformat !== ",.1f") continue;
    const vals = data.flatMap((t) => (Array.isArray(t[dim]) ? (t[dim] as unknown[]) : [])).filter((v): v is number => typeof v === "number");
    if (vals.length && Math.max(...vals.map(Math.abs)) >= 100) layout[ax] = { ...a, tickformat: ",.0f" };
  }
  const named = data.filter((t) => typeof t.name === "string" && t.name && t.type !== "pie" && t.type !== "treemap" && t.type !== "heatmap");
  const pie = data.some((t) => t.type === "pie");
  if (named.length > 1 || pie || layout.showlegend === true) {
    layout.showlegend = true;
    // the house legend: horizontal, above the plot, entries packed side by side
    layout.legend = { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", entrywidthmode: "pixels", entrywidth: 0, itemwidth: 24 };
    const m = isObj(layout.margin) ? { ...(layout.margin as Figure) } : {};
    m.t = Math.max(Number(m.t ?? 0), 28);
    layout.margin = m;
  }
  return { data, layout };
}

/** Columns for the KPI strip: all in one row when the content area is wide enough (no assistant panel). */
export function stripCols(n: number, panelOpen: boolean): string {
  const k = Math.max(1, Math.min(n, 8));
  if (k <= 4) return `grid-cols-2 sm:grid-cols-${k}`;
  const half = Math.ceil(k / 2);
  return panelOpen ? `grid-cols-2 sm:grid-cols-${half}` : `grid-cols-2 sm:grid-cols-${half} 2xl:grid-cols-${k}`;
}

/** Every class `stripCols` can return, spelled out so the CSS build keeps them. */
export const STRIP_CLASSES = "grid-cols-1 grid-cols-2 sm:grid-cols-1 sm:grid-cols-2 sm:grid-cols-3 sm:grid-cols-4 2xl:grid-cols-5 2xl:grid-cols-6 2xl:grid-cols-7 2xl:grid-cols-8";

export type Tone = "good" | "bad" | "neutral";

export function deltaArrow(change: number | null | undefined): "▲" | "▼" | "" {
  if (change == null || !Number.isFinite(change) || change === 0) return "";
  return change > 0 ? "▲" : "▼";
}

export function toneOf(t: string | null | undefined): Tone {
  return t === "good" || t === "bad" ? t : "neutral";
}

/** The comparison words under the interpretation header: "2026Q2 against 2026Q1". */
export function periodLine(period: string, prior: string): string {
  return prior ? `${period} against ${prior}` : period;
}
