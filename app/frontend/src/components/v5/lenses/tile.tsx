"use client";

/**
 * One lens tile (PLAN_R5 L1.2-L1.3): its Plotly chart or table, the (i) with the query behind it (as in the Cockpit),
 * and the (⋯) menu: change metric, change chart type, show by, move, delete, explain, open in the Cockpit or as a
 * What-If cohort. Every number in a table goes through the G5 formatter.
 */

import Link from "next/link";
import * as React from "react";
import { Info, MoreHorizontal } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { lensFigure } from "@/lib/v5/lens-dashboard";
import { CHART_CHOICES, CHART_WORD, type Explain, type Meta, type Tile, type TileSpec, type Trace, cell } from "@/lib/v5/lenses";

const EXPLAIN_PARTS: [keyof Explain, string][] = [["shows", "What it shows"], ["formula", "How it is calculated"], ["read", "How to read it"],
  ["look_for", "What to look for"]];

export function TraceInfo({ trace, explain, testId = "lens-trace" }: { trace: Trace | null; explain?: Explain | null; testId?: string }) {
  const [open, setOpen] = React.useState(false);
  if (!trace && !explain) return null;
  return (
    <span className="relative inline-flex">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-label="How this figure is computed" data-testid={testId}
              className="inline-flex size-5 items-center justify-center rounded-full border border-border text-text-muted hover:text-text-secondary">
        <Info className="size-3" aria-hidden /></button>
      {open ? (
        <span role="dialog" className="absolute right-0 top-6 z-40 max-h-[70vh] w-[30rem] max-w-[85vw] space-y-1.5 overflow-auto rounded-md border border-border bg-surface-raised p-3 text-[12px] leading-relaxed text-text-secondary shadow-lg"
              data-testid={`${testId}-panel`}>
          {explain ? (
            <span className="block space-y-1.5" data-testid={`${testId}-explain`}>
              {EXPLAIN_PARTS.filter(([k]) => explain[k]).map(([k, title]) => (
                <span key={k} className="block"><b className="block text-[11px] font-semibold uppercase tracking-wide text-text-primary">{title}</b>{explain[k]}</span>))}
            </span>) : null}
          {trace ? <>
            <span className="block pt-1 text-[11px] font-semibold text-text-primary">Query · {trace.period} · {trace.row_count} rows</span>
            <code className="block max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-surface px-2 py-1 font-mono text-[10px] text-text-secondary">{trace.sql}</code>
            <span className="block text-[11px]">Sources: {trace.sources.join(", ")}</span>
          </> : null}
        </span>) : null}
    </span>
  );
}

export function LensTable({ table, testId, owners }: { table: NonNullable<Tile["table"]>; testId?: string; owners?: string }) {
  return (
    <div className="max-h-[420px] overflow-auto" data-testid={testId}>
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-text-muted">
            {table.columns.map((c) => <th key={c.key} className={cn("px-2 py-1.5 font-medium", c.unit !== "text" && "text-right")}>{c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} className="border-b border-border/60 hover:bg-surface-hover">
              {table.columns.map((c, j) => (
                <td key={c.key} className={cn("px-2 py-1.5", c.unit !== "text" ? "text-right tabular-nums" : "text-text-primary")}>
                  {j === 0 && owners && typeof r[c.key] === "string" && /^(CB|RC)\d+/.test(String(r[c.key]))
                    ? <Link href={`${owners}${r[c.key]}`} className="text-accent hover:underline">{String(r[c.key])}</Link>
                    : cell(r[c.key], c.unit)}
                </td>))}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

type Op = Record<string, unknown>;

/** PLAN_R6 L5: a filter on this tile only (on top of the lens scope): pick a dimension and a value; clear it again. */
function TileFilter({ spec, meta, go }: { spec: TileSpec; meta: Meta; go: (op: Op) => void }) {
  const dims = meta.dimensions.filter((d) => (meta.values[d.key] ?? []).length > 0);
  const current = spec.filters ?? [];
  const [dim, setDim] = React.useState(current[0]?.dim ?? dims[0]?.key ?? "");
  if (!dims.length) return null;
  return (
    <div className="space-y-0.5" data-testid="lens-tile-filter">
      <span className="text-[11px] text-text-muted">Filter this tile</span>
      {current.length ? (
        <p className="flex flex-wrap items-center gap-1 text-[11px]" data-testid="lens-tile-filter-current">
          {current.map((f) => (
            <span key={f.dim} className="rounded-full border border-border px-1.5 py-0.5">{dims.find((d) => d.key === f.dim)?.label ?? f.dim}: {f.values.join(", ")}</span>))}
          <button type="button" className="text-accent hover:underline" data-testid="lens-tile-filter-clear" onClick={() => go({ op: "filter", tile_id: spec.id })}>Clear</button>
        </p>) : null}
      <div className="flex gap-1">
        <select className="w-1/2 rounded border border-border bg-surface px-1 py-1" value={dim} onChange={(e) => setDim(e.target.value)} data-testid="lens-tile-filter-dim"
                aria-label="Filter dimension">
          {dims.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
        </select>
        <select className="w-1/2 rounded border border-border bg-surface px-1 py-1" defaultValue="" data-testid="lens-tile-filter-value" aria-label="Filter value"
                onChange={(e) => e.target.value && go({ op: "filter", tile_id: spec.id, dim, values: [e.target.value] })}>
          <option value="">Value…</option>
          {(meta.values[dim] ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>
    </div>
  );
}

function Menu({ spec, meta, canEdit, onOp, onAsk, onHandoff, close }: { spec: TileSpec; meta: Meta | null; canEdit: boolean; onOp: (op: Op) => void;
  onAsk: (text: string) => void; onHandoff: (t: "cockpit" | "whatif") => void; close: () => void }) {
  const charts = CHART_CHOICES[spec.type] ?? [];
  const metricTile = ["trend", "breakdown", "mix_trend", "top_names", "compare"].includes(spec.type);
  const dimTile = spec.type === "breakdown";
  const go = (op: Op) => { onOp(op); close(); };
  return (
    <div role="menu" className="absolute right-0 top-7 z-40 w-64 space-y-2 rounded-md border border-border bg-surface-raised p-2.5 text-[12px] shadow-lg" data-testid="lens-tile-menu">
      {canEdit && metricTile && meta ? (
        <label className="block space-y-0.5"><span className="text-[11px] text-text-muted">Metric</span>
          <select className="w-full rounded border border-border bg-surface px-1.5 py-1" data-testid="lens-tile-metric" defaultValue=""
                  onChange={(e) => e.target.value && go({ op: "metric", tile_id: spec.id, metric: e.target.value })}>
            <option value="">Change metric…</option>
            {meta.metrics.filter((m) => !["scorecard", "dealdesk"].includes(m.kind) || spec.type === "trend").map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select></label>) : null}
      {canEdit && charts.length > 1 ? (
        <label className="block space-y-0.5"><span className="text-[11px] text-text-muted">Chart type</span>
          <select className="w-full rounded border border-border bg-surface px-1.5 py-1" data-testid="lens-tile-chart" value={spec.chart ?? charts[0]}
                  onChange={(e) => go({ op: "chart", tile_id: spec.id, chart: e.target.value })}>
            {charts.map((c) => <option key={c} value={c}>{CHART_WORD[c] ?? c}</option>)}
          </select></label>) : null}
      {canEdit && dimTile && meta ? (
        <label className="block space-y-0.5"><span className="text-[11px] text-text-muted">Show by</span>
          <select className="w-full rounded border border-border bg-surface px-1.5 py-1" data-testid="lens-tile-dim" value={spec.dim}
                  onChange={(e) => go({ op: "dim", tile_id: spec.id, dim: e.target.value })}>
            {meta.dimensions.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
          </select></label>) : null}
      {canEdit && meta && spec.type !== "pinned" ? <TileFilter spec={spec} meta={meta} go={go} /> : null}
      <div className="grid grid-cols-2 gap-1">
        {canEdit ? <>
          <button type="button" className="rounded border border-border px-2 py-1 hover:bg-surface-hover" data-testid="lens-tile-up" onClick={() => go({ op: "move", tile_id: spec.id, direction: "up" })}>Move up</button>
          <button type="button" className="rounded border border-border px-2 py-1 hover:bg-surface-hover" data-testid="lens-tile-down" onClick={() => go({ op: "move", tile_id: spec.id, direction: "down" })}>Move down</button>
        </> : null}
        <button type="button" className="rounded border border-border px-2 py-1 hover:bg-surface-hover" data-testid="lens-tile-explain"
                onClick={() => { onAsk(`Explain the tile ${spec.id}`); close(); }}>Explain</button>
        <button type="button" className="rounded border border-border px-2 py-1 hover:bg-surface-hover" data-testid="lens-tile-cockpit"
                onClick={() => { onHandoff("cockpit"); close(); }}>Cockpit thread</button>
        <button type="button" className="rounded border border-border px-2 py-1 hover:bg-surface-hover" data-testid="lens-tile-whatif"
                onClick={() => { onHandoff("whatif"); close(); }}>What-If cohort</button>
        {canEdit ? <button type="button" className="rounded border border-border px-2 py-1 text-negative hover:bg-surface-hover" data-testid="lens-tile-delete"
                           onClick={() => go({ op: "delete", tile_id: spec.id })}>Delete</button> : null}
      </div>
    </div>
  );
}

export function TileCard({ tile, spec, meta, canEdit, onOp, onAsk, onHandoff, book }: { tile: Tile; spec: TileSpec | undefined; meta: Meta | null; canEdit: boolean;
  onOp: (op: Op) => void; onAsk: (text: string) => void; onHandoff: (tileId: string, t: "cockpit" | "whatif") => void; book: string }) {
  const [menu, setMenu] = React.useState(false);
  const ref = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (!menu) return;
    const off = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [menu]);
  const height = tile.size === "wide" ? 320 : 260;
  const fig = React.useMemo(() => (tile.figure ? lensFigure(tile.figure) : null), [tile.figure]);
  return (
    <Card className="flex min-w-0 flex-col gap-1.5 px-3.5 pb-2.5 pt-3" style={tile.size === "wide" ? { gridColumn: "1 / -1" } : undefined}
          data-testid={`lens-tile-${tile.type}`} data-tile={tile.id} data-size={tile.size}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-[13px] font-semibold leading-snug text-text-primary" title={tile.title} data-testid="lens-tile-title">{tile.title}</h3>
          {tile.badges?.length ? (
            <p className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-text-muted">
              {tile.badges.map((b) => <span key={b.label}>{b.label}: <b className="text-text-primary">{b.display}</b></span>)}</p>) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1" ref={ref}>
          <TraceInfo trace={tile.trace} explain={tile.explain} />
          <span className="relative">
            <button type="button" aria-label={`Options for ${tile.title}`} onClick={() => setMenu((m) => !m)} data-testid="lens-tile-menu-button"
                    className="inline-flex size-6 items-center justify-center rounded hover:bg-surface-hover"><MoreHorizontal size={15} /></button>
            {menu && spec ? <Menu spec={spec} meta={meta} canEdit={canEdit} onOp={onOp} onAsk={onAsk} onHandoff={(t) => onHandoff(tile.id, t)} close={() => setMenu(false)} /> : null}
          </span>
        </div>
      </div>
      {tile.error ? <p className="text-[12px] text-text-muted" data-testid="lens-tile-error">{tile.error}</p>
        : fig ? <Plot data={fig.data} layout={fig.layout} height={height} ariaLabel={tile.title} testId="lens-plot" filename={`lens-${tile.id}`} />
          : tile.table ? <LensTable table={tile.table} testId="lens-top-names" owners={tile.links?.owner ? `/borrower-360?domain=${book}&id=` : undefined} /> : null}
    </Card>
  );
}
