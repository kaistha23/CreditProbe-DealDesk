/**
 * Plotly figures for the frozen Cockpit's answer charts (presentation-only exception: Plotly rendering).
 *
 * The frozen Cockpit (`components/cockpit-v4/visuals.tsx`) draws its sixteen chart kinds as hand-made SVG and CSS.
 * This module builds the same charts as Plotly figures, and changes nothing a reader is told:
 *
 * - POSITIONS come from the canonical numbers (`point.values`, `matrix.cells`, the box's five numbers), and from the
 *   same arithmetic the SVG bodies do (absolute bar lengths, the 100% stack's share of a row, the waterfall's running
 *   totals, the scale `extentOf` picks from the server's axis).
 * - EVERY STRING a reader sees is the server's: hover text through `customdata` + `hovertemplate`, bar and slice
 *   labels from `point.display`, heatmap cells from `matrix.display`, measure-axis ticks from `axis.ticks[].display`
 *   (`tickmode: "array"`). Without server ticks the numeric tick labels are hidden, never left to Plotly's formatter.
 * - ORDER is the points' order (`categoryorder: "array"`); horizontal forms list the first point at the top.
 * - WHICH charts appear is unchanged: the figure is `null` exactly when the SVG body would render nothing.
 *
 * Pure TypeScript (no React, no DOM). Runtime imports are relative with `.ts` extensions so the node test runner can
 * load this file; the types are erased.
 */

import type { ChartAxis, ChartBox, ChartPoint, RenderedChart } from "@/components/cockpit-v4/client";

import { TONE, seriesColor } from "../../lib/plotly-theme.ts";
import { extentOf, labelStride } from "../cockpit-v4/chart-geometry.ts";
import { numeric, text } from "../cockpit-v4/visual-choice.ts";

type Figure = Record<string, unknown>;

export interface CockpitFigure {
  data: Figure[];
  layout: Figure;
  height: number;
}

/** Row height (px) of a horizontal form, the room for the ruler under it, and a frame chart's height. */
const ROW = 28;
const FRAME_HEIGHT = 300;

/**
 * A string Plotly will draw as written.
 *
 * Plotly reads `<`, `>` and `&` in text as its own pseudo-HTML; written as entities they are drawn back as the same
 * characters, so "<30 DPD" stays "<30 DPD" instead of becoming a broken tag.
 */
export function esc(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Category keys that stay distinct when two points share a label.
 *
 * Plotly merges equal categories into one, the SVG draws one row per point. A repeated label gets zero-width spaces
 * appended to its KEY only; every tick shows `ticktext`, which is the label itself.
 */
function uniqueKeys(labels: string[]): string[] {
  const seen = new Map<string, number>();
  return labels.map((label) => {
    const n = seen.get(label) ?? 0;
    seen.set(label, n + 1);
    return n === 0 ? label : `${label}${"​".repeat(n)}`;
  });
}

/** A horizontal form's label, cut like the SVG's `truncate` column (the hover carries the full label). */
const shortRow = (label: string, max = 28) => (label.length > max ? `${label.slice(0, max - 1)}…` : label);
/** A frame chart's x label, cut exactly as `chart-frame.tsx#XLabels` cuts it. */
const shortTick = (label: string) => (label.length > 12 ? `${label.slice(0, 11)}…` : label);

/** The hover line for a row id, as the SVG tooltip prints it under the values. */
const rowLine = (rowId: string | undefined) => (rowId ? `<br><span style="font-size:10px">${esc(rowId)}</span>` : "");

/** customdata = [label, display, series name, row-id line]. */
const HOVER = "<b>%{customdata[0]}</b><br>%{customdata[2]}: %{customdata[1]}%{customdata[3]}<extra></extra>";

/**
 * A measure axis drawn from the server's ticks.
 *
 * Only the ticks inside the drawn range count, exactly as `Ruler` / `Gridlines` filter them; `minTicks` is the
 * count below which the SVG draws no scale (two for a ruler, one for gridlines). No ticks: no numeric labels.
 */
function measureAxis(axis: ChartAxis | undefined, low: number, high: number, minTicks: number): Figure {
  const ticks = (axis?.ticks ?? []).filter((t) => Number.isFinite(t.value) && t.value >= low && t.value <= high);
  const scale: Figure = ticks.length >= minTicks && ticks.length > 0
    ? { tickmode: "array", tickvals: ticks.map((t) => t.value), ticktext: ticks.map((t) => esc(text(t.display))), showticklabels: true, showgrid: true }
    : { showticklabels: false, showgrid: false };
  return {
    type: "linear",
    range: [low, high],
    fixedrange: true,
    zeroline: low <= 0 && high >= 0,
    ...scale,
    ...(axis?.label ? { title: { text: esc(axis.label) } } : {}),
  };
}

/** The category axis of a horizontal form: the points' order, first point at the top. */
function rowAxis(keys: string[], labels: string[]): Figure {
  return {
    type: "category", categoryorder: "array", categoryarray: keys, autorange: "reversed",
    tickmode: "array", tickvals: keys, ticktext: labels.map((l) => esc(shortRow(l))), ticksuffix: "  ",
    fixedrange: true, showgrid: false, zeroline: false,
  };
}

/** The category axis along the bottom of a frame chart: the points' order, thinned and cut as the SVG does. */
function frameXAxis(keys: string[], labels: string[], axis: ChartAxis | undefined): Figure {
  const stride = labelStride(keys.length, 7);
  const shown = keys.map((_, i) => i).filter((i) => i % stride === 0 || i === keys.length - 1);
  return {
    type: "category", categoryorder: "array", categoryarray: keys,
    tickmode: "array", tickvals: shown.map((i) => keys[i]), ticktext: shown.map((i) => esc(shortTick(labels[i]))),
    showgrid: false, zeroline: false,
    ...(axis?.label ? { title: { text: esc(axis.label) } } : {}),
  };
}

const rowsHeight = (rows: number, perRow = ROW, extra = 0) => Math.max(120, rows * perRow + 48 + extra);

interface SeriesPoint { rowId: string; label: string; value: number; display: string }

/** `visuals.tsx#series`: the first y column's plottable points (a null is dropped, never drawn as zero). */
function series(chart: RenderedChart): { column: string; points: SeriesPoint[] } | null {
  const column = chart.y_columns?.[0];
  if (!column) return null;
  const points = (chart.points ?? [])
    .map((p: ChartPoint) => ({ rowId: p.row_id, label: text(p.label), value: numeric(p.values?.[column]), display: text(p.display?.[column]) }))
    .filter((p): p is SeriesPoint => p.value !== null);
  return points.length ? { column, points } : null;
}

const hoverData = (points: SeriesPoint[], column: string) =>
  points.map((p) => [esc(p.label), esc(p.display), esc(column), rowLine(p.rowId)]);

// ---- bar ----------------------------------------------------------------------------------------------------------

function barFigure(chart: RenderedChart): CockpitFigure | null {
  const data = series(chart);
  if (!data) return null;
  const { points, column } = data;
  const [, high] = extentOf(chart.y_axis, points.map((p) => p.value), { zeroBased: true });
  const max = Math.max(high, 0);
  const labels = points.map((p) => p.label);
  const keys = uniqueKeys(labels);
  const xaxis = measureAxis(chart.y_axis, 0, max > 0 ? max : 1, 2);
  return {
    data: [{
      type: "bar", orientation: "h", y: keys,
      // The SVG's length: |value| against the scale's top, nothing when that top is not above zero.
      x: points.map((p) => (max > 0 ? Math.abs(p.value) : 0)),
      text: points.map((p) => esc(p.display)), textposition: "outside", cliponaxis: false,
      textfont: { size: 11, color: "var(--ipm-text-secondary)" },
      marker: { color: seriesColor(0) }, name: esc(column),
      customdata: hoverData(points, column), hovertemplate: HOVER,
    }],
    layout: {
      showlegend: false, hovermode: "closest", bargap: 0.3,
      margin: { l: 8, r: 80, t: 8, b: 8 },
      xaxis, yaxis: rowAxis(keys, labels),
    },
    height: rowsHeight(points.length, ROW, chart.y_axis?.label ? 24 : 0),
  };
}

// ---- line, step line, area, scatter --------------------------------------------------------------------------------

function lineFigure(chart: RenderedChart, variant: "line" | "step_line" | "area" | "scatter"): CockpitFigure | null {
  const data = series(chart);
  if (!data || data.points.length < 2) return null;
  const { points, column } = data;
  const values = points.map((p) => p.value);
  const [low, high] = extentOf(chart.y_axis, values);
  const labels = points.map((p) => p.label);
  const keys = uniqueKeys(labels);
  const color = seriesColor(0);
  const traces: Figure[] = [];
  if (variant === "area") {
    // The fill to the baseline at the SVG's 15% opacity, drawn under the line and silent to hover.
    traces.push({
      type: "scatter", mode: "lines", x: keys, y: values, fill: "tozeroy", fillcolor: color,
      line: { width: 0, color }, opacity: 0.15, hoverinfo: "skip", showlegend: false,
    });
  }
  traces.push({
    type: "scatter",
    // A mark on every point on every variant; a scatter draws NO line.
    mode: variant === "scatter" ? "markers" : "lines+markers",
    x: keys, y: values, name: esc(column),
    line: { color, width: 2, shape: variant === "step_line" ? "hv" : "linear" },
    marker: { color, size: variant === "scatter" ? 9 : 6 },
    customdata: hoverData(points, column), hovertemplate: HOVER,
  });
  return {
    data: traces,
    layout: {
      showlegend: false, hovermode: "closest",
      xaxis: frameXAxis(keys, labels, chart.x_axis),
      yaxis: measureAxis(chart.y_axis, low, high, 1),
    },
    height: FRAME_HEIGHT,
  };
}

// ---- histogram ----------------------------------------------------------------------------------------------------

function histogramFigure(chart: RenderedChart): CockpitFigure | null {
  const data = series(chart);
  if (!data) return null;
  const { points, column } = data;
  const [low, high] = extentOf(chart.y_axis, points.map((p) => p.value), { zeroBased: true });
  const labels = points.map((p) => p.label);
  const keys = uniqueKeys(labels);
  return {
    data: [{
      type: "bar", x: keys, y: points.map((p) => p.value), name: esc(column),
      marker: { color: seriesColor(0), line: { color: TONE.surface, width: 0.5 } },
      customdata: hoverData(points, column), hovertemplate: HOVER,
    }],
    layout: {
      showlegend: false, hovermode: "closest",
      // Drawn TOUCHING: a DPD distribution has no gaps between its bands.
      bargap: 0,
      xaxis: frameXAxis(keys, labels, chart.x_axis),
      yaxis: measureAxis(chart.y_axis, low, high, 1),
    },
    height: FRAME_HEIGHT,
  };
}

// ---- stacked bar, 100% stacked bar ---------------------------------------------------------------------------------

function stackedFigure(chart: RenderedChart, normalise: boolean): CockpitFigure | null {
  const columns = chart.y_columns ?? [];
  const points = chart.points ?? [];
  if (columns.length < 2 || !points.length) return null;
  const parts = points.map((p) => columns.map((c) => Math.abs(numeric(p.values?.[c]) ?? 0)));
  const totals = parts.map((row) => row.reduce((a, b) => a + b, 0));
  const widest = extentOf(chart.y_axis, totals, { zeroBased: true })[1] || 1;
  const labels = points.map((p) => text(p.label));
  const keys = uniqueKeys(labels);
  const data: Figure[] = columns.map((column, slot) => ({
    type: "bar", orientation: "h", y: keys, name: esc(column),
    // A 100% stack is each segment's share of its own row (an empty row stays empty); a plain stack keeps lengths.
    x: parts.map((row, i) => (normalise ? row[slot] / (totals[i] || 1) : row[slot])),
    // BY SLOT, NEVER BY RANK, as `slotColor` colours it.
    marker: { color: seriesColor(slot), line: { color: TONE.surface, width: 0.5 } },
    customdata: points.map((p) => [esc(text(p.label)), esc(text(p.display?.[column])), esc(column), rowLine(p.row_id)]),
    hovertemplate: HOVER,
  }));
  // A 100% stack is read as a share of the row, so the absolute scale under it would be a second, wrong story.
  const xaxis: Figure = normalise
    ? { type: "linear", range: [0, 1], fixedrange: true, showticklabels: false, showgrid: false, zeroline: false }
    : measureAxis(chart.y_axis, 0, widest, 2);
  return {
    data,
    layout: {
      barmode: "stack", showlegend: true, hovermode: "closest", bargap: 0.3,
      legend: { traceorder: "normal" },
      margin: { l: 8, r: 16, t: 28, b: 8 },
      xaxis, yaxis: rowAxis(keys, labels),
    },
    height: rowsHeight(points.length, ROW, 28 + (!normalise && chart.y_axis?.label ? 24 : 0)),
  };
}

// ---- grouped bar --------------------------------------------------------------------------------------------------

function groupedFigure(chart: RenderedChart): CockpitFigure | null {
  const columns = chart.y_columns ?? [];
  const points = chart.points ?? [];
  if (columns.length < 2 || !points.length) return null;
  const max = extentOf(chart.y_axis, points.flatMap((p) => columns.map((c) => numeric(p.values?.[c]) ?? 0)), { zeroBased: true })[1] || 1;
  const labels = points.map((p) => text(p.label));
  const keys = uniqueKeys(labels);
  const data: Figure[] = columns.map((column, slot) => ({
    type: "bar", orientation: "h", y: keys, name: esc(column),
    x: points.map((p) => Math.abs(numeric(p.values?.[column]) ?? 0)),
    text: points.map((p) => esc(text(p.display?.[column]))), textposition: "outside", cliponaxis: false,
    textfont: { size: 10, color: TONE.textMuted },
    marker: { color: seriesColor(slot) },
    customdata: points.map((p) => [esc(text(p.label)), esc(text(p.display?.[column])), esc(column), rowLine(p.row_id)]),
    hovertemplate: HOVER,
  }));
  return {
    data,
    layout: {
      barmode: "group", showlegend: true, hovermode: "closest", bargap: 0.25, bargroupgap: 0.08,
      legend: { traceorder: "normal" },
      margin: { l: 8, r: 80, t: 28, b: 8 },
      xaxis: measureAxis(chart.y_axis, 0, max, 2), yaxis: rowAxis(keys, labels),
    },
    height: rowsHeight(points.length, Math.max(ROW, columns.length * 14 + 12), 28 + (chart.y_axis?.label ? 24 : 0)),
  };
}

// ---- combo --------------------------------------------------------------------------------------------------------

function comboFigure(chart: RenderedChart): CockpitFigure | null {
  const columns = chart.y_columns ?? [];
  const points = chart.points ?? [];
  if (columns.length < 2 || !points.length) return null;
  const [bars, line] = columns;
  const volumes = points.map((p) => numeric(p.values?.[bars]) ?? 0);
  const barMax = extentOf(chart.y_axis, volumes, { zeroBased: true })[1] || 1;
  const rates = points.map((p) => numeric(p.values?.[line]) ?? 0);
  // THE SECOND SCALE, published separately (not zero-based, exactly as the SVG reads it).
  const [bottom, top] = extentOf(chart.y_axis_secondary, rates);
  const labels = points.map((p) => text(p.label));
  const keys = uniqueKeys(labels);
  const rateText = points.map((p) => esc(text(p.display?.[line])));
  const secondary = measureAxis(chart.y_axis_secondary, bottom, top, 1);
  return {
    data: [
      {
        type: "bar", orientation: "h", y: keys, x: volumes.map((v) => Math.abs(v)), name: esc(bars),
        marker: { color: seriesColor(0) },
        customdata: points.map((p) => [esc(text(p.label)), esc(text(p.display?.[bars])), esc(bars), rowLine(p.row_id)]),
        hovertemplate: HOVER,
      },
      {
        // The rate: a tick on its own scale across the same row, in the warning tone the SVG uses.
        type: "scatter", mode: "markers", y: keys, x: rates, xaxis: "x2", name: esc(line),
        marker: { symbol: "line-ns-open", size: 18, color: TONE.warning, line: { color: TONE.warning, width: 3 } },
        customdata: points.map((p, i) => [esc(text(p.label)), rateText[i], esc(line), rowLine(p.row_id)]),
        hovertemplate: HOVER,
      },
    ],
    layout: {
      showlegend: false, hovermode: "closest", bargap: 0.3,
      margin: { l: 8, r: 80, t: 8, b: 8 },
      xaxis: measureAxis(chart.y_axis, 0, barMax, 2),
      xaxis2: {
        ...secondary, overlaying: "x", side: "top", showgrid: false, zeroline: false,
        tickfont: { size: 11, color: TONE.warning },
        ...(chart.y_axis_secondary?.label
          ? { title: { text: esc(chart.y_axis_secondary.label), font: { size: 12, color: TONE.warning } } } : {}),
      },
      yaxis: rowAxis(keys, labels),
      // The rate's server string at the end of each row, where the SVG prints it.
      annotations: keys.map((key, i) => ({
        xref: "paper", x: 1, xanchor: "left", xshift: 6, yref: "y", y: key, text: rateText[i],
        showarrow: false, font: { size: 11, color: TONE.warning },
      })),
    },
    height: rowsHeight(points.length, ROW, 48),
  };
}

// ---- pie, donut ---------------------------------------------------------------------------------------------------

function sliceFigure(chart: RenderedChart, hole: number): CockpitFigure | null {
  const data = series(chart);
  if (!data) return null;
  const { points, column } = data;
  const total = points.reduce((a, p) => a + Math.abs(p.value), 0);
  if (total <= 0) return null;
  // The legend reads like the SVG's list beside the pie: the label, then the server's string.
  const entries = uniqueKeys(points.map((p) => `${esc(p.label)} ${esc(p.display)}`));
  return {
    data: [{
      type: "pie", labels: entries, values: points.map((p) => Math.abs(p.value)),
      // The points' order, clockwise from twelve o'clock, as the SVG sweeps from -90 degrees.
      sort: false, direction: "clockwise", rotation: 0, hole,
      marker: { colors: points.map((_, i) => seriesColor(i)), line: { color: TONE.surface, width: 1 } },
      textinfo: "none", name: esc(column),
      customdata: hoverData(points, column), hovertemplate: HOVER,
    }],
    layout: {
      showlegend: true, hovermode: "closest",
      legend: { orientation: "v", x: 1.02, xanchor: "left", y: 0.5, yanchor: "middle", traceorder: "normal" },
      margin: { l: 8, r: 8, t: 8, b: 8 },
    },
    height: Math.max(220, Math.min(420, points.length * 22 + 40)),
  };
}

// ---- waterfall ----------------------------------------------------------------------------------------------------

function waterfallFigure(chart: RenderedChart): CockpitFigure | null {
  const data = series(chart);
  if (!data) return null;
  const { points, column } = data;
  // The SVG's running totals, and its rule for the closing total.
  const cumulative = points.reduce<number[]>((acc, p) => [...acc, acc[acc.length - 1] + p.value], [0]);
  const last = points[points.length - 1];
  const before = cumulative[cumulative.length - 2];
  const isTotal = Math.abs(before - last.value) <= Math.abs(last.value) * 1e-9;
  const steps = points.map((p, i) => (isTotal && i === points.length - 1
    ? { ...p, from: 0, to: p.value, total: true }
    : { ...p, from: cumulative[i], to: cumulative[i + 1], total: false }));
  const [floor, ceiling] = extentOf(chart.y_axis, steps.flatMap((s) => [s.from, s.to]), { zeroBased: true });
  const span = ceiling - floor || 1;
  const labels = steps.map((s) => s.label);
  const keys = uniqueKeys(labels);
  return {
    data: [{
      type: "bar", orientation: "h", y: keys,
      // Each step floats from where the last finished; the SVG's minimum visible width is kept.
      base: steps.map((s) => Math.min(s.from, s.to)),
      x: steps.map((s) => Math.max(Math.abs(s.to - s.from), span * 0.004)),
      marker: { color: steps.map((s) => (s.total ? "var(--ipm-text-secondary)" : s.value >= 0 ? TONE.positive : TONE.negative)) },
      text: steps.map((s) => esc(s.display)), textposition: "outside", cliponaxis: false,
      textfont: { size: 11, color: "var(--ipm-text-secondary)" }, name: esc(column),
      customdata: hoverData(steps, column), hovertemplate: HOVER,
    }],
    layout: {
      showlegend: false, hovermode: "closest", bargap: 0.3,
      margin: { l: 8, r: 80, t: 8, b: 8 },
      xaxis: measureAxis(chart.y_axis, floor, ceiling, 2), yaxis: rowAxis(keys, labels),
    },
    height: rowsHeight(points.length, ROW, chart.y_axis?.label ? 24 : 0),
  };
}

// ---- bubble -------------------------------------------------------------------------------------------------------

function bubbleFigure(chart: RenderedChart): CockpitFigure | null {
  const columns = chart.y_columns ?? [];
  const points = chart.points ?? [];
  if (columns.length < 2 || !points.length) return null;
  const [xColumn, yColumn, sizeColumn] = columns;
  const read = (column: string) => points.map((p) => numeric(p.values?.[column]) ?? 0);
  const xs = read(xColumn);
  const ys = read(yColumn);
  const sizes = sizeColumn ? read(sizeColumn) : ys.map(() => 1);
  const [xLow, xHigh] = extentOf(chart.x_axis, xs);
  const [yLow, yHigh] = extentOf(chart.y_axis, ys);
  const widest = Math.max(...sizes.map(Math.abs), 0) || 1;
  const color = seriesColor(0);
  return {
    data: [{
      type: "scatter", mode: "markers", x: xs, y: ys,
      // AREA, not radius: the SVG's radius 2 + 9 * sqrt(size / largest), as a diameter in pixels.
      marker: {
        size: sizes.map((s) => 2.3 * (2 + Math.sqrt(Math.abs(s) / widest) * 9)), sizemode: "diameter",
        color, opacity: 0.45, line: { color, width: 1 },
      },
      customdata: points.map((p) => [
        esc(text(p.label)),
        columns.map((c) => `${esc(c)}: ${esc(text(p.display?.[c]))}`).join("<br>"),
        rowLine(p.row_id),
      ]),
      hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]}%{customdata[2]}<extra></extra>",
    }],
    layout: {
      showlegend: false, hovermode: "closest",
      xaxis: { ...measureAxis(chart.x_axis, xLow, xHigh, 1), fixedrange: false },
      yaxis: { ...measureAxis(chart.y_axis, yLow, yHigh, 1), fixedrange: false },
      ...(sizeColumn ? {
        annotations: [{
          xref: "paper", yref: "paper", x: 1, y: 1, xanchor: "right", yanchor: "bottom", showarrow: false,
          text: esc(`Sized by ${sizeColumn}`), font: { size: 11, color: TONE.textMuted },
        }],
      } : {}),
    },
    height: FRAME_HEIGHT,
  };
}

// ---- heatmap ------------------------------------------------------------------------------------------------------

/** The SVG mixes 8% to 92% accent into the surface by |value| / largest; this colour range reproduces that ramp. */
const MIX_LOW = 0.08;
const MIX_SPAN = 0.84;

function heatmapFigure(chart: RenderedChart): CockpitFigure | null {
  const matrix = chart.matrix;
  if (!matrix?.rows?.length || !matrix.columns?.length) return null;
  const { rows, columns } = matrix;
  const cell = (r: string, c: string) => {
    const value = matrix.cells?.[`${r}|${c}`];
    return typeof value === "number" ? value : null;
  };
  const magnitudes = Object.values(matrix.cells ?? {}).filter((v): v is number => typeof v === "number").map(Math.abs);
  const max = magnitudes.length ? Math.max(...magnitudes) : 0;
  const top = max > 0 ? max : 1;
  // An empty cell is NOT a zero: it stays null in the value grid and is drawn by its own layer, with the SVG's dot.
  const z = rows.map((r) => columns.map((c) => {
    const v = cell(r, c);
    return v === null ? null : Math.abs(v);
  }));
  const absent = rows.map((r) => columns.map((c) => (cell(r, c) === null ? 1 : null)));
  const shown = rows.map((r) => columns.map((c) => (cell(r, c) === null ? "" : esc(text(matrix.display?.[`${r}|${c}`])))));
  const shapes: Figure[] = matrix.square
    ? rows.flatMap((r, i) => {
      const j = columns.indexOf(r);
      return j < 0 ? [] : [{
        type: "rect", xref: "x", yref: "y", x0: j - 0.5, x1: j + 0.5, y0: i - 0.5, y1: i + 0.5,
        line: { color: TONE.accent, width: 1.5 }, fillcolor: "rgba(0,0,0,0)",
      }];
    })
    : [];
  return {
    data: [
      {
        type: "heatmap", x: columns, y: rows, z: absent, showscale: false, hoverinfo: "skip",
        colorscale: [[0, "var(--ipm-surface-sunken)"], [1, "var(--ipm-surface-sunken)"]], zmin: 0, zmax: 1,
        text: absent.map((row) => row.map((v) => (v === null ? "" : "·"))), texttemplate: "%{text}",
        textfont: { color: TONE.textMuted }, xgap: 2, ygap: 2,
      },
      {
        type: "heatmap", x: columns, y: rows, z, showscale: false, hoverongaps: false,
        colorscale: [[0, TONE.surface], [1, TONE.accent]],
        zmin: -top * (MIX_LOW / MIX_SPAN), zmax: top * (1 + (1 - MIX_LOW - MIX_SPAN) / MIX_SPAN),
        text: shown, texttemplate: "%{text}", textfont: { size: 11 }, xgap: 2, ygap: 2,
        customdata: rows.map((r, i) => columns.map((c, j) => [esc(r), esc(c), shown[i][j]])),
        hovertemplate: "%{customdata[0]} → %{customdata[1]}: %{customdata[2]}<extra></extra>",
      },
    ],
    layout: {
      showlegend: false, hovermode: "closest",
      margin: { l: 8, r: 8, t: 8, b: 8 },
      xaxis: {
        type: "category", categoryorder: "array", categoryarray: columns, side: "top",
        tickmode: "array", tickvals: columns, ticktext: columns.map(esc),
        showgrid: false, zeroline: false, fixedrange: true,
        ...(matrix.column_axis ? { title: { text: esc(matrix.column_axis) } } : {}),
      },
      yaxis: {
        type: "category", categoryorder: "array", categoryarray: rows, autorange: "reversed",
        tickmode: "array", tickvals: rows, ticktext: rows.map(esc), ticksuffix: "  ",
        showgrid: false, zeroline: false, fixedrange: true,
        ...(matrix.row_axis ? { title: { text: esc(matrix.row_axis) } } : {}),
      },
      shapes,
    },
    height: Math.max(160, rows.length * 32 + 72),
  };
}

// ---- box ----------------------------------------------------------------------------------------------------------

const BOX_STATS: [keyof ChartBox & string, string][] = [
  ["minimum", "min"], ["q1", "Q1"], ["median", "median"], ["q3", "Q3"], ["maximum", "max"],
];

function boxFigure(chart: RenderedChart): CockpitFigure | null {
  const boxes = chart.boxes ?? [];
  if (!boxes.length) return null;
  const numbers = boxes.flatMap((b) => [Number(b.minimum), Number(b.maximum)]).filter((n) => Number.isFinite(n));
  if (!numbers.length) return null;
  const top = Math.max(...numbers);
  const bottom = Math.min(...numbers);
  const pad = (top - bottom || 1) * 0.02;
  const labels = boxes.map((b) => b.label || "All");
  const keys = uniqueKeys(labels);
  const color = seriesColor(0);
  const hover = boxes.map((b) => BOX_STATS
    .filter(([key]) => b.display?.[key] !== undefined)
    .map(([key, name]) => `${name}: ${esc(text(b.display?.[key]))}`)
    .join("<br>"));
  return {
    data: [
      {
        // The server's five numbers, drawn as given: Plotly computes nothing.
        type: "box", orientation: "h", y: keys,
        lowerfence: boxes.map((b) => Number(b.minimum)), q1: boxes.map((b) => Number(b.q1)),
        median: boxes.map((b) => Number(b.median)), q3: boxes.map((b) => Number(b.q3)),
        upperfence: boxes.map((b) => Number(b.maximum)),
        boxpoints: false, whiskerwidth: 0, line: { color, width: 1.5 }, hoverinfo: "skip",
      },
      {
        // The hover sits on the median, carrying the server's strings (Plotly's own box hover would format numbers).
        type: "scatter", mode: "markers", y: keys, x: boxes.map((b) => Number(b.median)),
        marker: { size: 14, color: "rgba(0,0,0,0)" },
        customdata: boxes.map((b, i) => [esc(labels[i]), hover[i], esc(text(b.display?.median))]),
        hovertemplate: "<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
      },
    ],
    layout: {
      showlegend: false, hovermode: "closest",
      margin: { l: 8, r: 80, t: 8, b: 8 },
      // The SVG draws no scale under a box plot.
      xaxis: { type: "linear", range: [bottom - pad, top + pad], fixedrange: true, showticklabels: false, showgrid: false, zeroline: false },
      yaxis: rowAxis(keys, labels),
      // The median's server string at the end of each row, where the SVG prints it.
      annotations: keys.map((key, i) => ({
        xref: "paper", x: 1, xanchor: "left", xshift: 6, yref: "y", y: key, text: esc(text(boxes[i].display?.median)),
        showarrow: false, font: { size: 11, color: "var(--ipm-text-secondary)" },
      })),
    },
    height: rowsHeight(boxes.length, 32),
  };
}

// ---- dispatch -----------------------------------------------------------------------------------------------------

const BUILDERS: Record<string, (chart: RenderedChart) => CockpitFigure | null> = {
  heatmap: heatmapFigure,
  box: boxFigure,
  line: (c) => lineFigure(c, "line"),
  step_line: (c) => lineFigure(c, "step_line"),
  area: (c) => lineFigure(c, "area"),
  scatter: (c) => lineFigure(c, "scatter"),
  stacked_bar: (c) => stackedFigure(c, false),
  stacked_bar_100: (c) => stackedFigure(c, true),
  grouped_bar: groupedFigure,
  combo: comboFigure,
  pie: (c) => sliceFigure(c, 0),
  donut: (c) => sliceFigure(c, 0.55),
  histogram: histogramFigure,
  bubble: bubbleFigure,
  waterfall: waterfallFigure,
  bar: barFigure,
};

/**
 * The Plotly figure for one Cockpit answer chart, or `null` exactly when the SVG body would draw nothing.
 *
 * An unknown kind falls back as `visuals.tsx#ResultChart` does: a 100% stack when there is more than one y column,
 * otherwise bars.
 */
export function cockpitFigure(chart: RenderedChart): CockpitFigure | null {
  const build = Object.prototype.hasOwnProperty.call(BUILDERS, chart.kind) ? BUILDERS[chart.kind] : undefined;
  if (build) return build(chart);
  return (chart.y_columns ?? []).length > 1 ? stackedFigure(chart, true) : barFigure(chart);
}
