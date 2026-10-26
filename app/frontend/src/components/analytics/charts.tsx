"use client";

import * as React from "react";

import { byUnit, humanise } from "@/lib/format";
import {
  CHART_SLOTS as SLOTS,
  ChartFrame,
  PALETTES,
  PaletteControl,
  type PaletteId,
  useChartPalette,
} from "@/components/analytics/chart-palette";
import { Plot } from "@/components/v5/ews/plot";
import { SEQUENTIAL, TONE, resolveVars, seriesColor } from "@/lib/plotly-theme";
import { cn } from "@/lib/utils";

/**
 * Chart primitives, drawn through the shared Plotly surface (`v5/ews/plot.tsx`)
 * and the house theme (`lib/plotly-theme.ts`).
 *
 * Rules applied throughout, rather than per chart:
 *
 *  - **Colour is assigned in fixed slot order and never cycled.** A series keeps
 *    its colour when a filter changes how many series are on screen.
 *  - **One axis, always.** Two measures on different scales get two charts, never
 *    two y-scales on one.
 *  - **Thin marks, recessive grid.** 2px lines, gridlines across the value axis
 *    only, no axis lines competing with the data.
 *  - **A hover layer by default.** Every chart carries a hover label, and every
 *    figure in it is preformatted with the same `byUnit` formatter the tables
 *    use, never a raw float.
 *  - **A legend whenever there are two or more series**, so identity never rests
 *    on colour alone. One series needs none — the title names it.
 *  - **A 2px surface gap between stacked segments**, so adjacent bands read as
 *    separate quantities rather than one blurred mass.
 *
 * Colours are theme tokens (`var(--ipm-*)`) resolved by the Plotly surface at
 * draw time, so a theme switch repaints every chart with no chart-level code
 * involved. The reader's palette choice is applied here (`useSlotColors`).
 */

export { CHART_SLOTS } from "@/components/analytics/chart-palette";

type Figure = Record<string, unknown>;
type Row = Record<string, string | number | null>;

/**
 * Every chart is wrapped so it carries its own palette and its own control.
 *
 * The control belongs to the chart, not to whatever is rendering it. Putting it
 * in the result view covered analyses and missed the ten charts on the CRO
 * Lens, which is exactly the kind of gap that makes a control feel unreliable.
 *
 * It is invisible until the chart is hovered or focused. Ten visible palette
 * rows on one page is clutter in a product whose first principle is that
 * decoration comes last; ten that appear under your cursor are a tool.
 */
function Framed({
  children,
  className,
  height,
}: {
  children: React.ReactNode;
  className?: string;
  height: number;
}) {
  return (
    <ChartFrame className={cn("group/chart", className)} showControl={false}>
      <div className="w-full" style={{ height }}>
        {children}
      </div>
      <div
        className={cn(
          "opacity-0 transition-opacity duration-[--duration-quick]",
          "group-hover/chart:opacity-100 focus-within:opacity-100",
        )}
      >
        <PaletteControl />
      </div>
    </ChartFrame>
  );
}

/** Fixed-order slot colour. Never call this with an index derived from rank. */
export function slotColor(index: number): string {
  return seriesColor(index % SLOTS);
}

/* --------------------------------------------------------------- palette */

let probe: CanvasRenderingContext2D | null | undefined;

/**
 * A CSS colour Plotly cannot parse (`color-mix(...)`), as `rgb()`.
 *
 * The browser does the mixing: the colour is painted into one canvas pixel and
 * read back, so the result matches what CSS would have drawn.
 */
function toRgb(css: string, fallback: string): string {
  if (probe === undefined) {
    probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  }
  if (!probe) return fallback;
  probe.fillStyle = "#000";
  probe.fillStyle = css;
  probe.clearRect(0, 0, 1, 1);
  probe.fillRect(0, 0, 1, 1);
  const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

function subscribeTheme(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-theme", "style"],
  });
  return () => observer.disconnect();
}

function themeSnapshot(): string {
  const el = document.documentElement;
  return `${el.className}|${el.getAttribute("data-theme") ?? ""}|${el.getAttribute("style") ?? ""}`;
}

/** The eight slot colours of one palette under one theme (the theme is the cache key). */
function paletteSlots(id: PaletteId, theme: string): string[] {
  const palette = PALETTES.find((p) => p.id === id) ?? PALETTES[0];
  const live = typeof document !== "undefined" && theme !== "server";
  const style = live ? getComputedStyle(document.documentElement) : null;
  return Array.from({ length: SLOTS }, (_, index) => {
    const css = palette.slots(index);
    // Plain tokens are resolved (and re-themed) by the Plotly surface itself.
    if (!css.includes("color-mix")) return css;
    if (!style) return seriesColor(index);
    return toRgb(resolveVars(css, (name) => style.getPropertyValue(name)), seriesColor(index));
  });
}

/**
 * The slot colours of the reader's chosen palette.
 *
 * The palette control overrides `--ipm-chart-1..8` on the chart's wrapper, but
 * Plotly resolves tokens against the document root, so the palette is applied
 * here instead: the same definitions, read from `chart-palette`, re-read when
 * the palette or the theme changes.
 */
function useSlotColors(): (slot: number) => string {
  const [palette] = useChartPalette();
  const theme = React.useSyncExternalStore(subscribeTheme, themeSnapshot, () => "server");
  const colors = React.useMemo(() => paletteSlots(palette, theme), [palette, theme]);
  return React.useCallback(
    (slot: number) => colors[((Math.trunc(slot) % SLOTS) + SLOTS) % SLOTS],
    [colors],
  );
}

/* --------------------------------------------------------------- helpers */

/** A cell as a plotted number: numbers and numeric strings, anything else a gap. */
function num(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

const category = (row: Row, key: string) => String(row[key] ?? "");

/** One series' hover line, its value preformatted by `byUnit`. */
const SERIES_HOVER = "%{fullData.name}: <b>%{customdata}</b><extra></extra>";

/** A plot with no axis line, ticks or gridlines of its own; callers add the grid they want. */
function axis(grid: boolean, extra: Figure = {}): Figure {
  return { showgrid: grid, zeroline: false, ...extra };
}

export interface SeriesDef {
  key: string;
  label: string;
  /** Fixed slot index. Assign once per series and never recompute from order. */
  slot: number;
}

interface BaseProps {
  data: Record<string, string | number | null>[];
  xKey: string;
  series: SeriesDef[];
  units?: Record<string, string>;
  height?: number;
  className?: string;
}

function seriesNames(series: SeriesDef[]): string {
  return series.map((s) => s.label).join(", ");
}

/** Change over time. */
export function TrendChart({
  data,
  xKey,
  series,
  units,
  height = 240,
  className,
  area = false,
}: BaseProps & { area?: boolean }) {
  const color = useSlotColors();
  const x = data.map((row) => category(row, xKey));
  const traces: Figure[] = series.flatMap((s) => {
    const y = data.map((row) => num(row[s.key]));
    const line: Figure = {
      type: "scatter",
      mode: "lines",
      name: s.label,
      legendgroup: s.key,
      x,
      y,
      customdata: data.map((row) => byUnit(row[s.key], units?.[s.key])),
      connectgaps: false,
      line: { color: color(s.slot), width: 2, shape: "linear" },
      hovertemplate: SERIES_HOVER,
    };
    if (!area) return [line];
    // The wash under the line is its own trace so its opacity leaves the line at full strength.
    const wash: Figure = {
      type: "scatter",
      mode: "none",
      x,
      y,
      fill: "tozeroy",
      fillcolor: color(s.slot),
      opacity: 0.12,
      legendgroup: s.key,
      showlegend: false,
      hoverinfo: "skip",
    };
    return [wash, line];
  });
  const layout: Figure = {
    showlegend: series.length > 1,
    hovermode: "x unified",
    xaxis: axis(false, { type: "category", showline: true, linecolor: TONE.grid }),
    yaxis: axis(true),
  };
  return (
    <Framed className={className} height={height}>
      <Plot
        data={traces}
        layout={layout}
        height={height}
        filename="creditprobe-trend"
        ariaLabel={`Trend of ${seriesNames(series)} by ${humanise(xKey)}`}
      />
    </Framed>
  );
}

/** Bars of one or more series over categories, shared by the grouped and stacked forms. */
function barFigure({
  data,
  xKey,
  series,
  units,
  horizontal,
  color,
  extra,
}: {
  data: Row[];
  xKey: string;
  series: SeriesDef[];
  units?: Record<string, string>;
  horizontal: boolean;
  color: (slot: number) => string;
  extra: (s: SeriesDef) => Figure;
}): Figure[] {
  const categories = data.map((row) => category(row, xKey));
  return series.map((s) => {
    const values = data.map((row) => num(row[s.key]));
    const { marker, ...own } = extra(s);
    return {
      type: "bar",
      orientation: horizontal ? "h" : "v",
      name: s.label,
      x: horizontal ? values : categories,
      y: horizontal ? categories : values,
      customdata: data.map((row) => byUnit(row[s.key], units?.[s.key])),
      hovertemplate: SERIES_HOVER,
      ...own,
      marker: { color: color(s.slot), ...((marker as Figure | undefined) ?? {}) },
    };
  });
}

/** Category axis and value axis for a bar chart; horizontal bars list the first row at the top. */
function barLayout(horizontal: boolean, legend: boolean, extra: Figure): Figure {
  const categoryAxis = axis(false, { type: "category" });
  const valueAxis = axis(true);
  return horizontal
    ? {
        showlegend: legend,
        hovermode: "y unified",
        xaxis: valueAxis,
        yaxis: { ...categoryAxis, autorange: "reversed" },
        ...extra,
      }
    : {
        showlegend: legend,
        hovermode: "x unified",
        xaxis: { ...categoryAxis, showline: true, linecolor: TONE.grid },
        yaxis: valueAxis,
        ...extra,
      };
}

/** Magnitude by category. Horizontal when the labels are words. */
export function CategoryBarChart({
  data,
  xKey,
  series,
  units,
  height = 260,
  className,
  horizontal = true,
}: BaseProps & { horizontal?: boolean }) {
  const color = useSlotColors();
  const traces = barFigure({
    data,
    xKey,
    series,
    units,
    horizontal,
    color,
    // Rounded data-end only, anchored to the baseline.
    extra: () => ({ marker: { cornerradius: 4 } }),
  });
  const layout = barLayout(horizontal, series.length > 1, {
    barmode: "group",
    bargap: horizontal ? 0.2 : 0.22,
  });
  return (
    <Framed className={className} height={height}>
      <Plot
        data={traces}
        layout={layout}
        height={height}
        filename="creditprobe-bars"
        ariaLabel={`${seriesNames(series)} by ${humanise(xKey)}`}
      />
    </Framed>
  );
}

/** Composition — parts of one whole. */
export function StackedBarChart({
  data,
  xKey,
  series,
  units,
  height = 260,
  className,
  horizontal = false,
}: BaseProps & { horizontal?: boolean }) {
  const color = useSlotColors();
  const traces = barFigure({
    data,
    xKey,
    series,
    units,
    horizontal,
    color,
    // A 2px surface-coloured edge separates adjacent bands, so a stack reads
    // as distinct quantities rather than one mass.
    extra: () => ({ marker: { line: { color: TONE.surface, width: 2 } } }),
  });
  const layout = barLayout(horizontal, series.length > 1, { barmode: "stack", bargap: 0.28 });
  return (
    <Framed className={className} height={height}>
      <Plot
        data={traces}
        layout={layout}
        height={height}
        filename="creditprobe-composition"
        ariaLabel={`Composition of ${humanise(xKey)} by ${seriesNames(series)}`}
      />
    </Framed>
  );
}

/** Signed contributions — a movement broken into its drivers. */
export function DivergingBarChart({
  data,
  xKey,
  valueKey,
  unit,
  height = 260,
  className,
}: {
  data: Record<string, string | number | null>[];
  xKey: string;
  valueKey: string;
  unit?: string;
  height?: number;
  className?: string;
}) {
  const trace: Figure = {
    type: "bar",
    orientation: "h",
    name: humanise(valueKey),
    x: data.map((row) => num(row[valueKey])),
    y: data.map((row) => category(row, xKey)),
    customdata: data.map((row) => byUnit(row[valueKey], unit ?? "")),
    hovertemplate: SERIES_HOVER,
    marker: {
      cornerradius: 4,
      // Polarity, not identity: an increase in loss is negative news, a
      // decrease is positive. Status colours, never categorical ones.
      color: data.map((row) => (Number(row[valueKey]) >= 0 ? TONE.negative : TONE.positive)),
    },
  };
  const layout = barLayout(true, false, { bargap: 0.2, xaxis: axis(true, { zeroline: true }) });
  return (
    <Framed className={className} height={height}>
      <Plot
        data={[trace]}
        layout={layout}
        height={height}
        filename="creditprobe-drivers"
        ariaLabel={`${humanise(valueKey)} by ${humanise(xKey)}, increases and decreases`}
      />
    </Framed>
  );
}

/**
 * Transition matrix.
 *
 * A sequential single-hue ramp: one colour, light to dark, encoding magnitude.
 * Any non-zero share starts 12% up the ramp so a small move is still visible
 * against an empty cell. The diagonal is outlined rather than coloured
 * differently — "stayed put" is a position on the grid, not a different kind of
 * quantity.
 */
export function MatrixHeatmap({
  categories,
  cells,
  className,
  diagonalHint = true,
}: {
  categories: string[];
  /** Row percentages keyed `${from}|${to}`. */
  cells: Record<string, number>;
  className?: string;
  diagonalHint?: boolean;
}) {
  const max = Math.max(1, ...Object.values(cells));
  const value = (from: string, to: string) => cells[`${from}|${to}`] ?? 0;

  const trace: Figure = {
    type: "heatmap",
    x: categories,
    y: categories,
    z: categories.map((from) =>
      categories.map((to) => {
        const v = value(from, to);
        return v > 0 ? 0.12 + (v / max) * 0.88 : 0;
      }),
    ),
    zmin: 0,
    zmax: 1,
    colorscale: SEQUENTIAL,
    showscale: false,
    xgap: 2,
    ygap: 2,
    text: categories.map((from) =>
      categories.map((to) => {
        const v = value(from, to);
        return v > 0 ? v.toFixed(1) : "·";
      }),
    ),
    texttemplate: "%{text}",
    textfont: { size: 11 },
    customdata: categories.map((from) =>
      categories.map((to) => `${from} → ${to}: ${value(from, to).toFixed(2)}%`),
    ),
    hovertemplate: "%{customdata}<extra></extra>",
  };
  const shapes = diagonalHint
    ? categories.map((_, i) => ({
        type: "rect",
        xref: "x",
        yref: "y",
        x0: i - 0.5,
        x1: i + 0.5,
        y0: i - 0.5,
        y1: i + 0.5,
        line: { color: TONE.muted, width: 1 },
        fillcolor: "rgba(0,0,0,0)",
      }))
    : [];
  const height = Math.max(160, categories.length * 30 + 72);
  const layout: Figure = {
    hovermode: "closest",
    margin: { l: 56, r: 8, t: 40, b: 8 },
    xaxis: axis(false, { type: "category", side: "top", title: { text: "To" } }),
    yaxis: axis(false, { type: "category", autorange: "reversed", title: { text: "From" } }),
    shapes,
  };
  return (
    <div className={cn("min-w-0", className)}>
      <Plot
        data={[trace]}
        layout={layout}
        height={height}
        filename="creditprobe-transition-matrix"
        ariaLabel={`Transition matrix across ${categories.length} categories, row percentages`}
      />
    </div>
  );
}


/* ------------------------------------------------------- relationships */

/**
 * The hover label for a point, which needs the thing's NAME as well as its
 * figures.
 *
 * A category hover labels a point by its x value, which for a scatter is a
 * number — "18.4" tells a reader nothing about which borrower they are hovering.
 * `customdata` carries `[pick value, name, band, ...formatted figures]`.
 */
function pointHover(keys: string[], labelKey?: string, bandKey?: string): string {
  const head = [
    labelKey ? "<b>%{customdata[1]}</b><br>" : "",
    bandKey ? "%{customdata[2]}<br>" : "",
  ].join("");
  const lines = keys.map((key, i) => `${humanise(key)}: <b>%{customdata[${i + 3}]}</b>`);
  return `${head}${lines.join("<br>")}<extra></extra>`;
}

function pointData(
  rows: Row[],
  keys: string[],
  pickKey: string,
  units?: Record<string, string>,
  labelKey?: string,
  bandKey?: string,
): string[][] {
  return rows.map((row) => [
    String(row[pickKey] ?? ""),
    labelKey ? String(row[labelKey] ?? "") : "",
    bandKey ? String(row[bandKey] ?? "") : "",
    ...keys.map((key) => byUnit(row[key], units?.[key])),
  ]);
}

/** What a clicked point is called: the first entry of its `customdata`. */
function picked(onPick?: (value: string) => void) {
  if (!onPick) return undefined;
  return (customdata: unknown) => {
    const value = Array.isArray(customdata) ? customdata[0] : customdata;
    onPick(String(value ?? ""));
  };
}

function pointLayout(xKey: string, yKey: string, legend: boolean): Figure {
  return {
    showlegend: legend,
    hovermode: "closest",
    xaxis: axis(true, { title: { text: humanise(xKey) }, showline: true, linecolor: TONE.grid }),
    yaxis: axis(true, { title: { text: humanise(yKey) } }),
  };
}

/**
 * Two measures against each other, one point per named thing.
 *
 * The form the registry chooses when a result is a RELATIONSHIP rather than a
 * ranking: EAD against coverage, leverage against DSCR. Until now the registry
 * named it and this module could not draw it, so those results silently fell
 * back to a table and the reader was told nothing about why.
 *
 * A point is a row of the result and nothing else. No regression line is drawn
 * and no correlation is quoted: a trend line through a scatter is a claim, and
 * a claim belongs to the analysis, not to the picture of it.
 */
export function ScatterPlot({
  data,
  xKey,
  yKey,
  labelKey,
  units,
  height = 320,
  className,
  onPick,
  emphasis,
}: {
  data: Record<string, string | number | null>[];
  xKey: string;
  yKey: string;
  /** The column naming each point, shown in the tooltip. */
  labelKey?: string;
  units?: Record<string, string>;
  height?: number;
  className?: string;
  /** Clicking a point picks it out. */
  onPick?: (value: string) => void;
  /** How strongly to draw each point, by its label. */
  emphasis?: (value: string) => number;
}) {
  const color = useSlotColors();
  const pickKey = labelKey ?? xKey;
  const keys = [xKey, yKey];
  const trace: Figure = {
    type: "scatter",
    mode: "markers",
    name: humanise(yKey),
    x: data.map((row) => num(row[xKey])),
    y: data.map((row) => num(row[yKey])),
    customdata: pointData(data, keys, pickKey, units, labelKey),
    hovertemplate: pointHover(keys, labelKey),
    marker: {
      color: color(0),
      size: 9,
      opacity: data.map((row) => emphasis?.(String(row[pickKey] ?? "")) ?? 0.75),
    },
  };
  return (
    <Framed className={className} height={height}>
      <Plot
        data={[trace]}
        layout={pointLayout(xKey, yKey, false)}
        height={height}
        filename="creditprobe-scatter"
        onPointClick={picked(onPick)}
        ariaLabel={`${humanise(yKey)} against ${humanise(xKey)}, ${data.length} points`}
      />
    </Framed>
  );
}

/** Bubble area range in px², the smallest for a zero value and the largest for the maximum. */
const BUBBLE_AREA: [number, number] = [40, 720];

/**
 * The Risk Landscape: three measures at once, and a governed band as colour.
 *
 * §54's first renderer. Position carries two measures, the point's AREA carries
 * a third, and colour carries a category — a stage, a rating band — so four
 * dimensions are readable at a glance without a rotating cube nobody can read
 * a value off.
 *
 * Area rather than radius, deliberately. Doubling a radius quadruples the ink,
 * and a reader comparing two bubbles reads the ink. The size value is mapped
 * linearly onto AREA (`BUBBLE_AREA`, from zero to the largest value) and only
 * then turned into the diameter Plotly draws, which is the honest encoding.
 */
export function BubbleChart({
  data,
  xKey,
  yKey,
  sizeKey,
  bandKey,
  labelKey,
  units,
  height = 380,
  className,
  onPick,
  emphasis,
}: {
  data: Record<string, string | number | null>[];
  xKey: string;
  yKey: string;
  sizeKey: string;
  /** The governed category that colours each point — Stage, rating band. */
  bandKey?: string;
  labelKey?: string;
  units?: Record<string, string>;
  height?: number;
  className?: string;
  onPick?: (value: string) => void;
  emphasis?: (value: string) => number;
}) {
  const color = useSlotColors();

  // One colour per band, assigned in the order the bands first appear so a
  // band keeps its colour when a filter changes how many are on screen.
  const bands = React.useMemo(() => {
    if (!bandKey) return [];
    const seen: string[] = [];
    for (const row of data) {
      const value = String(row[bandKey] ?? "");
      if (value && !seen.includes(value)) seen.push(value);
    }
    return seen;
  }, [data, bandKey]);

  const pickKey = labelKey ?? xKey;
  const keys = [xKey, yKey, sizeKey];
  const maxSize = Math.max(0, ...data.map((row) => num(row[sizeKey]) ?? 0)) || 1;
  const diameter = (row: Row) => {
    const share = Math.max(0, num(row[sizeKey]) ?? 0) / maxSize;
    const area = BUBBLE_AREA[0] + share * (BUBBLE_AREA[1] - BUBBLE_AREA[0]);
    return 2 * Math.sqrt(area / Math.PI);
  };
  const trace = (rows: Row[], name: string, slot: number, opacity: number | number[]): Figure => ({
    type: "scatter",
    mode: "markers",
    name,
    x: rows.map((row) => num(row[xKey])),
    y: rows.map((row) => num(row[yKey])),
    customdata: pointData(rows, keys, pickKey, units, labelKey, bandKey),
    hovertemplate: pointHover(keys, labelKey, bandKey),
    marker: { color: color(slot), size: rows.map(diameter), sizemode: "diameter", opacity },
  });

  const traces =
    bands.length > 0
      ? bands.map((band, slot) =>
          trace(
            data.filter((row) => String(row[bandKey as string] ?? "") === band),
            band,
            slot,
            0.7,
          ),
        )
      : [
          trace(
            data,
            humanise(sizeKey),
            0,
            data.map((row) => emphasis?.(String(row[pickKey] ?? "")) ?? 0.7),
          ),
        ];

  return (
    <Framed className={className} height={height}>
      <Plot
        data={traces}
        layout={pointLayout(xKey, yKey, bands.length > 1)}
        height={height}
        filename="creditprobe-landscape"
        onPointClick={picked(onPick)}
        ariaLabel={`${humanise(yKey)} against ${humanise(xKey)}, sized by ${humanise(sizeKey)}${
          bandKey ? `, coloured by ${humanise(bandKey)}` : ""
        }`}
      />
    </Framed>
  );
}
