/**
 * R16 n: reads the chart(s) and table(s) actually rendered with an answer, for the narration writer
 * (`lib/v5/narration.ts`), and finds the element to pulse while a line is said.
 *
 * Charts: the shared Plotly surface (`components/v5/ews/plot.tsx`, a `.js-plotly-plot` host carrying the drawn
 * figure in `.data` / `.layout`): type, orientation, series, labels, values, text labels. Any other drawn chart
 * (`role="img"` with an svg, large enough not to be an icon) is named by its label without figures.
 * Tables: `<table>` and ARIA grids (`role="table"` / `role="row"`). Hidden copies, dialogs and the action bar are left out.
 */

import type { ChartFacts, ChartKind, ChartSeries, NarrationTarget, Place, TableFacts } from "@/lib/v5/narration";

interface PlotTrace {
  type?: string; orientation?: string; mode?: string; name?: string; visible?: unknown;
  x?: unknown[]; y?: unknown[]; labels?: unknown[]; values?: unknown[]; text?: unknown; z?: unknown[];
}
interface PlotHost extends HTMLElement { data?: PlotTrace[]; layout?: Record<string, unknown> }

export interface ReadChart { facts: ChartFacts; host: HTMLElement; plotly: boolean; traces: { type: string; nth: number }[] }
export interface ReadTable { facts: TableFacts; rows: HTMLElement[] }
export interface Visuals { charts: ReadChart[]; tables: ReadTable[] }

const HIDDEN = '[data-no-doc],[role="dialog"],.sr-only,[data-thread-actions],[aria-hidden="true"]';

function shown(el: Element): boolean {
  if (el.closest(HIDDEN)) return false;
  const r = (el as HTMLElement).getBoundingClientRect?.();
  return !r || (r.width > 0 && r.height > 0);
}

const txt = (el: Element | null | undefined) => String((el as HTMLElement | null)?.innerText ?? el?.textContent ?? "").replace(/\s+/g, " ").trim();
const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));
const nums = (a: unknown[] | undefined) => (a ?? []).map((v) => (typeof v === "number" ? v : Number(str(v).replace(/,/g, ""))));

function titleOf(layout: Record<string, unknown> | undefined): string {
  const t = layout?.title as unknown;
  if (typeof t === "string") return t;
  if (t && typeof t === "object" && typeof (t as { text?: unknown }).text === "string") return (t as { text: string }).text;
  return "";
}

function axisText(layout: Record<string, unknown> | undefined): string {
  const out: string[] = [];
  for (const k of ["xaxis", "yaxis"]) {
    const a = layout?.[k] as Record<string, unknown> | undefined;
    if (!a) continue;
    out.push(str(a.ticksuffix), str(a.tickprefix), titleOf(a as Record<string, unknown>));
  }
  return out.join(" ");
}

function unitOf(text: string): string {
  // Plotly's own placeholders (%{y}, %{customdata[0]}) are not units
  const t = text.replace(/<[^>]+>/g, " ").replace(/%\{[^}]*\}/g, " ");
  const sar = /SAR\s*(bn|mn|m|k)\b/i.exec(t);
  if (sar) return `SAR ${sar[1].toLowerCase() === "m" ? "mn" : sar[1].toLowerCase()}`;
  if (/%|percent/i.test(t)) return "%";
  if (/\bbps\b/i.test(t)) return "bps";
  if (/SAR|riyal/i.test(t)) return "SAR";
  return "";
}

function kindOf(tr: PlotTrace): ChartKind {
  const t = tr.type ?? "scatter";
  if (t === "bar") return tr.orientation === "h" ? "hbar" : "bar";
  if (t === "pie") return "pie";
  if (t === "waterfall") return "waterfall";
  if (t === "heatmap" || t === "contour") return "heatmap";
  if (t === "scatter" || t === "scattergl") return /lines/.test(tr.mode ?? "lines") ? "line" : "scatter";
  return "other";
}

function seriesOf(tr: PlotTrace): ChartSeries {
  const k = kindOf(tr);
  const texts = Array.isArray(tr.text) ? (tr.text as unknown[]).map(str) : undefined;
  if (k === "pie") return { name: str(tr.name), labels: (tr.labels ?? []).map(str), values: nums(tr.values), texts };
  if (k === "hbar" || (k === "waterfall" && tr.orientation === "h")) return { name: str(tr.name), labels: (tr.y ?? []).map(str), values: nums(tr.x), texts };
  if (k === "heatmap" || k === "other") return { name: str(tr.name), labels: [], values: [] };
  return { name: str(tr.name), labels: (tr.x ?? []).map(str), values: nums(tr.y), texts };
}

/** Where `el` sits against the answer's words (the first paragraph outside any chart or table). */
function placeOf(el: Element, root: Element): Place {
  const words = Array.from(root.querySelectorAll("p, li, h1, h2, h3, h4")).find((p) => !p.closest('.js-plotly-plot, [role="img"], table, [role="table"]') && shown(p) && txt(p).length > 10);
  const a = (el as HTMLElement).getBoundingClientRect?.(), b = (words as HTMLElement | undefined)?.getBoundingClientRect?.();
  if (!a || !b || !a.width || !b.width) return "below";
  const mid = b.left + b.width / 2;
  const overlapY = a.top < b.bottom && a.bottom > b.top;
  if (a.left >= mid && (overlapY || a.left >= b.right - 4)) return "right";
  if (a.right <= mid && overlapY) return "left";
  return a.top >= b.top ? "below" : "above";
}

function areaOf(el: Element): number { const r = (el as HTMLElement).getBoundingClientRect?.(); return r ? r.width * r.height : 0; }

export function readVisuals(root: Element | null): Visuals {
  const charts: ReadChart[] = [];
  const tables: ReadTable[] = [];
  if (!root) return { charts, tables };
  const plots = Array.from(root.querySelectorAll<PlotHost>(".js-plotly-plot")).filter(shown);
  for (const host of plots) {
    const data = (host.data ?? []).filter((t) => t && t.visible !== false && t.visible !== "legendonly");
    if (!data.length) continue;
    const counts: Record<string, number> = {};
    const traces = data.map((t) => { const type = t.type ?? "scatter"; const nth = counts[type] ?? 0; counts[type] = nth + 1; return { type, nth }; });
    // the main trace decides the kind: the one with the most points
    const main = data.reduce((best, t) => (seriesOf(t).values.length > seriesOf(best).values.length ? t : best), data[0]);
    const label = host.getAttribute("aria-label") || titleOf(host.layout);
    charts.push({ host, plotly: true, traces,
      facts: { kind: kindOf(main), title: label, place: placeOf(host, root), series: data.map(seriesOf), area: areaOf(host),
               unit: unitOf(`${label} ${axisText(host.layout)} ${data.map((d) => str((d as Record<string, unknown>).hovertemplate)).join(" ")}`) } });
  }
  const others = Array.from(root.querySelectorAll<HTMLElement>('[role="img"]')).filter((el) => !el.classList.contains("js-plotly-plot") && !el.closest(".js-plotly-plot")
    && el.querySelector("svg, canvas") && shown(el) && (el.getBoundingClientRect?.().width ?? 0) >= 120 && (el.getBoundingClientRect?.().height ?? 0) >= 60);
  for (const host of others) {
    charts.push({ host, plotly: false, traces: [], facts: { kind: "other", title: host.getAttribute("aria-label") || "", place: placeOf(host, root), series: [], area: areaOf(host) * 0.5 } });
  }
  const tabs = Array.from(root.querySelectorAll<HTMLElement>('table, [role="table"]')).filter((t) => shown(t) && !t.parentElement?.closest('table, [role="table"]'));
  for (const t of tabs) {
    const aria = t.getAttribute("role") === "table";
    const all = Array.from(t.querySelectorAll<HTMLElement>(aria ? '[role="row"]' : "tr")).filter(shown);
    const cellsOf = (r: HTMLElement, read: (e: Element) => string = txt) =>
      Array.from(r.querySelectorAll(aria ? '[role="cell"],[role="gridcell"],[role="columnheader"],[role="rowheader"]' : "td, th")).map(read);
    // headers as written (innerText would return them as styled, e.g. upper case)
    const headText = (e: Element) => String(e.textContent ?? "").replace(/\s+/g, " ").trim();
    const isHead = (r: HTMLElement) => (aria ? !!r.querySelector('[role="columnheader"]') && !r.querySelector('[role="cell"],[role="gridcell"]')
                                              : !r.querySelector("td")) || !!r.closest("thead");
    const head = all.find(isHead);
    const body = all.filter((r) => !isHead(r) && cellsOf(r).some(Boolean));
    if (!body.length) continue;
    tables.push({ rows: body, facts: { title: t.getAttribute("aria-label") || "", columns: head ? cellsOf(head, headText) : [], rows: body.map((r) => cellsOf(r)), place: placeOf(t, root) } });
  }
  return { charts, tables };
}

/** The element a line points at: the bar, slice or line in the chart, or the table row; else the chart itself. */
export function targetElement(v: Visuals, target: NarrationTarget | undefined): { el: HTMLElement | SVGElement; host: HTMLElement } | null {
  if (!target) return null;
  if (target.kind === "row") {
    const t = v.tables[target.table];
    const el = t?.rows[target.row];
    return el ? { el, host: el } : null;
  }
  const c = v.charts[target.chart];
  if (!c) return null;
  if (!c.plotly || target.point < 0) return { el: c.host, host: c.host };
  const tr = c.traces[target.series];
  const layer = tr?.type === "bar" ? ".barlayer" : tr?.type === "pie" ? ".pielayer" : tr?.type === "waterfall" ? ".waterfalllayer" : tr?.type?.startsWith("scatter") ? ".scatterlayer" : "";
  if (!tr || !layer) return { el: c.host, host: c.host };
  const trace = c.host.querySelectorAll<SVGElement>(`${layer} .trace`)[tr.nth];
  if (!trace) return { el: c.host, host: c.host };
  if (tr.type.startsWith("scatter")) return { el: trace, host: c.host };
  const pts = trace.querySelectorAll<SVGElement>(tr.type === "pie" ? ".slice" : ".point");
  return { el: pts[target.point] ?? trace, host: c.host };
}
