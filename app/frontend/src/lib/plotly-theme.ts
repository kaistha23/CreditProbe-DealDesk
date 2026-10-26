/**
 * The CreditProbe Plotly theme (PLAN_R12 N2, R11_FEEDBACK I10 b): one look for every chart in the app.
 *
 * Fonts, palette, gridlines, hover and the light / dark variants live here, and nowhere else. Every chart draws
 * through the shared Plotly surface (`components/v5/ews/plot.tsx`), which calls `themedLayout` and `plotlyConfig`
 * and resolves the `var(--ipm-*)` colours against the live theme just before it draws, so one figure renders in
 * Executive Ivory and in Midnight Boardroom without a second definition.
 *
 * Pure TypeScript (no DOM, no React): the node test runner and the server can import it.
 */

export type Figure = Record<string, unknown>;

/** The categorical series palette, in order. Colours are theme tokens, resolved at draw time. */
export const PALETTE: readonly string[] = [
  "var(--ipm-chart-1)", "var(--ipm-chart-2)", "var(--ipm-chart-3)", "var(--ipm-chart-4)",
  "var(--ipm-chart-5)", "var(--ipm-chart-6)", "var(--ipm-chart-7)", "var(--ipm-chart-8)",
];

/** The colour of series `i` (wraps after eight). */
export function seriesColor(i: number): string {
  const n = PALETTE.length;
  return PALETTE[((Math.trunc(i) % n) + n) % n];
}

/**
 * Meaning colours, the same in every module: the accent for "ours / recommended", positive for a gain or a pass,
 * negative for a loss or a breach, warning for a hurdle, a trigger or "near", muted for context.
 */
export const TONE = {
  accent: "var(--ipm-accent)",
  positive: "var(--ipm-positive)",
  negative: "var(--ipm-negative)",
  warning: "var(--ipm-warning)",
  info: "var(--ipm-info)",
  muted: "var(--ipm-border-strong)",
  text: "var(--ipm-text-primary)",
  textMuted: "var(--ipm-text-muted)",
  grid: "var(--ipm-border)",
  surface: "var(--ipm-surface)",
} as const;

/** A diverging scale for heatmaps (loss → neutral → gain), readable in light and dark themes. */
export const DIVERGING: [number, string][] = [[0, "var(--ipm-negative)"], [0.5, "var(--ipm-surface-sunken)"], [1, "var(--ipm-positive)"]];
/** A sequential scale (low → high) for intensity heatmaps. */
export const SEQUENTIAL: [number, string][] = [[0, "var(--ipm-surface-sunken)"], [1, "var(--ipm-accent)"]];

/** The type scale charts use: body 12, ticks 11, titles 13, hover 12. */
export const TYPE = { body: 12, tick: 11, title: 13, hover: 12, legend: 11 } as const;

/** The fallback font stack when the page's font cannot be read (server, tests). */
export const FONT_STACK = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';

/**
 * Light and dark token values, for code that draws with no live theme to read (tests, an exported PNG built off
 * screen). They mirror Executive Ivory and Midnight Boardroom in `app/globals.css`.
 */
export const LIGHT_TOKENS: Record<string, string> = {
  "--ipm-surface": "#ffffff", "--ipm-surface-sunken": "#f0f2f5", "--ipm-border": "#dce1e7", "--ipm-border-strong": "#c2cad3",
  "--ipm-text-primary": "#12181f", "--ipm-text-secondary": "#414c59", "--ipm-text-muted": "#6b7684",
  "--ipm-accent": "#10527a", "--ipm-positive": "#12704b", "--ipm-warning": "#9a6208", "--ipm-negative": "#a92a25", "--ipm-info": "#10527a",
  "--ipm-chart-1": "#2563A8", "--ipm-chart-2": "#C2410C", "--ipm-chart-3": "#0E8A6A", "--ipm-chart-4": "#7C3AED",
  "--ipm-chart-5": "#A16207", "--ipm-chart-6": "#0891B2", "--ipm-chart-7": "#BE185D", "--ipm-chart-8": "#3F6212",
};
export const DARK_TOKENS: Record<string, string> = {
  "--ipm-surface": "#111823", "--ipm-surface-sunken": "#070b11", "--ipm-border": "#22303f", "--ipm-border-strong": "#33455a",
  "--ipm-text-primary": "#eef2f6", "--ipm-text-secondary": "#b3c0cf", "--ipm-text-muted": "#7d8b9c",
  "--ipm-accent": "#4d9fd4", "--ipm-positive": "#4bb98a", "--ipm-warning": "#dda43f", "--ipm-negative": "#e07a72", "--ipm-info": "#4d9fd4",
  "--ipm-chart-1": "#3B82C4", "--ipm-chart-2": "#D97036", "--ipm-chart-3": "#2FA37B", "--ipm-chart-4": "#8B6FE0",
  "--ipm-chart-5": "#B37F22", "--ipm-chart-6": "#2196C4", "--ipm-chart-7": "#D4629A", "--ipm-chart-8": "#749B34",
};

/** The themes in `app/globals.css` that are dark (they set `color-scheme: dark`). */
export const DARK_THEMES = new Set(["midnight", "graphite", "oxblood", "forest"]);
export const isDarkTheme = (name: string | null | undefined): boolean => DARK_THEMES.has(String(name ?? ""));

const VAR = /var\((--[\w-]+)\)/g;

/**
 * Replace every `var(--x)` inside a figure's strings with the theme's value. `lookup` reads one token (the live
 * computed style in the browser, `LIGHT_TOKENS` / `DARK_TOKENS` elsewhere); a token it cannot read becomes a
 * neutral grey rather than an invalid colour.
 */
export function resolveVars<T>(value: T, lookup: (name: string) => string): T {
  if (typeof value === "string") {
    return (value.includes("var(") ? value.replace(VAR, (_, name: string) => (lookup(name) || "").trim() || "#888") : value) as T;
  }
  if (Array.isArray(value)) return value.map((v) => resolveVars(v, lookup)) as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) out[k] = resolveVars(v, lookup);
    return out as T;
  }
  return value;
}

/** A lookup over a fixed token map (light or dark), for drawing with no live theme. */
export const tokenLookup = (dark = false) => (name: string): string => (dark ? DARK_TOKENS : LIGHT_TOKENS)[name] ?? "";

/** The axis every chart gets: hairline gridlines, a firmer zero line, muted ticks, automatic margins. */
export function axisTheme(): Figure {
  return {
    gridcolor: TONE.grid, gridwidth: 1, zerolinecolor: TONE.muted, zerolinewidth: 1, linecolor: TONE.grid,
    tickfont: { size: TYPE.tick, color: TONE.textMuted }, title: { font: { size: TYPE.body, color: "var(--ipm-text-secondary)" } },
    automargin: true, ticks: "", showline: false,
  };
}

/** The hover label: the surface colour with a hairline border, the page's font, full series names. */
export function hoverTheme(font = FONT_STACK): Figure {
  return { namelength: -1, font: { size: TYPE.hover, family: font, color: TONE.text }, bgcolor: TONE.surface, bordercolor: TONE.grid, align: "left" };
}

/** The base layout (before a chart's own layout is merged over it). */
export function baseLayout(height: number, font = FONT_STACK): Figure {
  return {
    height,
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: font || FONT_STACK, size: TYPE.body, color: "var(--ipm-text-secondary)" },
    colorway: [...PALETTE],
    margin: { l: 56, r: 16, t: 12, b: 40 },
    hovermode: "x unified",
    // Unified hover answers for the nearest period wherever the pointer is on the plot, not only near a marker.
    hoverdistance: -1,
    modebar: { bgcolor: "rgba(0,0,0,0)", color: TONE.textMuted, activecolor: TONE.accent },
    hoverlabel: hoverTheme(font),
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { size: TYPE.legend, color: "var(--ipm-text-secondary)" }, bgcolor: "rgba(0,0,0,0)" },
    title: { font: { size: TYPE.title, color: TONE.text } },
    bargap: 0.28,
    // Keep what the reader did (legend toggles, zoom) across re-renders of the same chart.
    uirevision: "reader",
  };
}

const isObj = (v: unknown): v is Figure => Boolean(v) && typeof v === "object" && !Array.isArray(v);

/** A chart's layout with the house theme under it: its own keys win, axes and hover labels are merged key by key. */
export function themedLayout(layout: Figure | undefined, height: number, font = FONT_STACK): Figure {
  const base = baseLayout(height, font);
  const own = layout ?? {};
  const merged: Figure = { ...base, ...own };
  for (const key of ["hoverlabel", "legend", "font", "modebar"]) {
    if (isObj(own[key])) merged[key] = { ...(base[key] as Figure), ...(own[key] as Figure) };
  }
  const axis = axisTheme();
  for (const key of Object.keys(merged)) {
    if (/^[xy]axis\d*$/.test(key)) {
      const mine = (merged[key] ?? {}) as Figure;
      const title = typeof mine.title === "string" ? { text: mine.title } : mine.title;
      merged[key] = { ...axis, ...mine, ...(title ? { title: { ...(axis.title as Figure), ...(title as Figure) } } : {}) };
    }
  }
  if (!merged.xaxis) merged.xaxis = axis;
  if (!merged.yaxis) merged.yaxis = axis;
  return merged;
}

/** The Plotly config every chart gets: mode bar on hover, PNG download at 2x, no lasso / select, no logo. */
export function plotlyConfig({ filename = "creditprobe-chart", scrollZoom = false, staticPlot = false }:
  { filename?: string; scrollZoom?: boolean; staticPlot?: boolean } = {}): Figure {
  return {
    responsive: true,
    displaylogo: false,
    displayModeBar: staticPlot ? false : "hover",
    staticPlot,
    scrollZoom,
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
    toImageButtonOptions: { format: "png", filename, scale: 2 },
  };
}

const LONG = (v: unknown) => typeof v === "number" && Number.isFinite(v) && Math.abs(v - Math.round(v * 10000) / 10000) > 1e-12;

/**
 * G5 safety net (PLAN_R6 E2): a trace that sets no hovertemplate and no hover format of its own, and carries a
 * number with more than 4 decimals, hovers at most 2 decimals with thousands separators (4 below 0.01), never
 * the raw float. Traces that format their own hover are left alone.
 */
export function safeHover(data: Figure[]): Figure[] {
  return data.map((tr) => {
    if (tr.hovertemplate || tr.hoverinfo === "skip" || tr.hoverinfo === "none") return tr;
    const out: Figure = { ...tr };
    for (const ax of ["x", "y", "z"] as const) {
      const key = `${ax}hoverformat`;
      const vals = tr[ax];
      if (out[key] || !Array.isArray(vals)) continue;
      const flat = (vals as unknown[]).flat(2);
      if (!flat.some(LONG)) continue;
      const small = flat.every((v) => typeof v !== "number" || Math.abs(v) < 0.01);
      out[key] = small ? ",.4f" : ",.2f";
    }
    return out;
  });
}

/** A minimal sparkline figure (one line, optional reference lines, no axes), for cards and table rows. */
export function sparkFigure(values: (number | null)[], { color = TONE.accent, bands = [], labels }:
  { color?: string; bands?: number[]; labels?: string[] } = {}): { data: Figure[]; layout: Figure } {
  const x = labels ?? values.map((_, i) => i);
  const data: Figure[] = [{ type: "scatter", mode: "lines", x, y: values, connectgaps: false,
    line: { color, width: 1.6, shape: "linear" }, hoverinfo: "skip" }];
  const shapes = bands.map((b) => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: b, y1: b,
    line: { color: TONE.muted, width: 1, dash: "dot" } }));
  return { data, layout: { margin: { l: 0, r: 0, t: 2, b: 2 }, showlegend: false, hovermode: false, shapes,
    xaxis: { visible: false, fixedrange: true }, yaxis: { visible: false, fixedrange: true } } };
}
