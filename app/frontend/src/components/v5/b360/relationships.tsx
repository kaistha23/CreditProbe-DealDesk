"use client";

import * as React from "react";
import { FileSpreadsheet, Maximize2, Network } from "lucide-react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { shareBarFigure } from "@/components/answer/bar-figure";
import { Plot } from "@/components/v5/ews/plot";
import { b360, graphExcelHref, useB360, type DomainId, type Tab } from "@/lib/v5/b360";
import {
  BAND_COLOURS, BAND_LABEL, KIND_STYLE, graphFigure, kindsIn, sar, type GNode, type GraphPayload, type Kind,
} from "@/lib/v5/graph-figure";
import { TONE, seriesColor } from "@/lib/plotly-theme";
import { cn } from "@/lib/utils";
import { PoweredByLine } from "./intel";

const pct = (v: number | null | undefined, places = 1) => (v === null || v === undefined ? "—" : `${v.toFixed(places)}%`);

function Band({ band }: { band: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px]" data-band={band}>
      <span className="size-2 rounded-full" style={{ background: BAND_COLOURS[band] ?? "#94a3b8" }} aria-hidden />
      {BAND_LABEL[band] ?? band}
    </span>
  );
}

function Panel({ title, note, testId, children, tone }: { title: string; note?: string; testId: string; children: React.ReactNode; tone?: "warn" | "bad" }) {
  return (
    <Card className={cn("space-y-2 p-3", tone === "bad" && "border-negative/40", tone === "warn" && "border-warning/40")} data-testid={testId}>
      <div className="flex items-center gap-2">
        <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-text-muted">{title}</p>
        {note ? <InfoPopover title={title}><p>{note}</p></InfoPopover> : null}
      </div>
      {children}
    </Card>
  );
}

function Rows({ rows, cols, testId, onOpen }: {
  rows: Record<string, unknown>[]; cols: { key: string; label: string; fmt?: (v: unknown) => string; align?: "right" }[]; testId: string;
  onOpen?: (id: string) => void;
}) {
  if (!rows.length) return <p className="text-xs text-text-muted" data-testid={`${testId}-empty`}>None.</p>;
  return (
    <div className="max-h-56 overflow-auto rounded border border-border" data-testid={testId}>
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-surface-sunken text-text-muted">
          <tr>{cols.map((c) => <th key={c.key} className={cn("px-2 py-1 text-left font-medium", c.align === "right" && "text-right")}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border" data-row-id={String(r.borrower_id ?? r.customer_id ?? r.collateral_id ?? i)}>
              {cols.map((c) => {
                const v = r[c.key];
                const text = c.key === "ews_band" && typeof v === "string" ? null : c.fmt ? c.fmt(v) : v === null || v === undefined ? "—" : String(v);
                return (
                  <td key={c.key} className={cn("px-2 py-1", c.align === "right" && "text-right tabular-nums")}>
                    {c.key === "ews_band" && typeof v === "string" ? <Band band={v} />
                      : c.key === "borrower_id" && onOpen ? <button type="button" onClick={() => onOpen(String(v))} className="font-mono text-accent hover:underline">{text}</button> : text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A horizontal bar of shares that add up to 100%: the names in the bank's book, then everything else. */
function ShareBar({ items, other, otherLabel, testId, flagAt }: {
  items: { label: string; value: number }[]; other: number; otherLabel: string; testId: string; flagAt: number;
}) {
  const colour = (k: number) => seriesColor(k % 6);
  const otherColour = "var(--ipm-surface-sunken)";
  const fig = shareBarFigure({ height: 22, segments: [
    ...items.map((i, k) => ({ label: i.label, value: i.value, color: colour(k), text: pct(i.value),
                              outline: i.value > flagAt ? TONE.negative : undefined })),
    ...(other > 0 ? [{ label: otherLabel, value: other, color: otherColour, text: pct(other) }] : []),
  ] });
  return (
    <div data-testid={testId}>
      <Plot data={fig.data} layout={{ ...fig.layout, xaxis: { visible: false, fixedrange: true, range: [0, 100] } }} height={fig.height}
            ariaLabel="Shares of the total" filename="shares" />
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-text-secondary">
        {items.map((i, k) => <span key={i.label} className="inline-flex items-center gap-1"><span className="size-2 rounded-sm" style={{ background: colour(k) }} aria-hidden />{i.label} {pct(i.value)}</span>)}
        <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm" style={{ background: otherColour }} aria-hidden />{otherLabel} {pct(other)}</span>
      </div>
    </div>
  );
}

function GroupLimit({ a, onOpen }: { a: GraphPayload["analytics"]["group"]; onOpen: (id: string) => void }) {
  if (a.standalone) {
    return <Panel title="Connected group against the limit" testId="rel-group" note={`${a.policy.clause} ${a.policy.title}: SAR ${a.policy.limit_sar_mn.toLocaleString("en-US")}m`}>
      <p className="text-sm text-text-secondary" data-testid="rel-group-standalone">No other borrower in the book is connected to this one by ownership or control.</p>
    </Panel>;
  }
  const tone = a.status === "breach" ? "bad" : a.status === "watch" ? "warn" : undefined;
  const periods = a.trend.map((t: { period: string }) => t.period);
  const eads = a.trend.map((t: { ead: number }) => t.ead);
  return (
    <Panel title="Connected group against the limit" testId="rel-group" tone={tone}
           note={`${a.policy.clause} ${a.policy.title}: SAR ${a.policy.limit_sar_mn.toLocaleString("en-US")}m. ${a.group_id} ${a.group_name}, ${a.members} companies. Book group field: ${a.legacy_group_id} ${a.legacy_group_name}.`}>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">Group EAD</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-group-ead">{sar(a.exposure)}</p></div>
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">Limit used</p>
          <p className={cn("text-lg font-semibold tabular-nums", a.status === "breach" && "text-negative", a.status === "watch" && "text-warning")} data-testid="rel-group-used">{pct(a.utilisation_pct)}</p></div>
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">Headroom</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-group-headroom">{sar(a.headroom)}</p></div>
        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase", a.status === "breach" ? "bg-negative-muted text-negative" : a.status === "watch" ? "bg-warning-muted text-warning" : "bg-positive-muted text-positive")}
              data-testid="rel-group-status">{a.status === "breach" ? "Over the limit" : a.status === "watch" ? "Above 80% of the limit" : "Within the limit"}</span>
      </div>
      <Plot height={190} ariaLabel="Group exposure by quarter against the limit" testId="rel-plot-group" filename="group-exposure"
            data={[{ type: "bar", x: periods, y: eads, marker: { color: periods.map((_: string, i: number) => (i === periods.length - 1 ? "#6366f1" : "#c7d2fe")) },
                     text: eads.map((v: number) => sar(v)), textposition: "outside", cliponaxis: false, hovertemplate: "%{x}: SAR %{y:,.1f}m<extra></extra>" }]}
            layout={{ showlegend: false, hovermode: "closest", margin: { l: 56, r: 16, t: 18, b: 36 }, xaxis: { type: "category" },
                      yaxis: { title: { text: "SAR million" }, rangemode: "tozero", range: [0, Math.max(a.policy.limit_sar_mn, ...eads) * 1.25] },
                      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: a.policy.limit_sar_mn, y1: a.policy.limit_sar_mn, line: { color: "#dc2626", dash: "dash", width: 2 } }],
                      annotations: [{ xref: "paper", x: 1, yref: "y", y: a.policy.limit_sar_mn, text: `${a.policy.clause} limit`, showarrow: false, yshift: 10, xanchor: "right", font: { color: "#dc2626", size: 10 } }] }} />
      <Rows testId="rel-group-rows" onOpen={onOpen} rows={a.rows}
            cols={[{ key: "borrower_id", label: "Borrower" }, { key: "name", label: "Name" }, { key: "role", label: "Role" },
                   { key: "exposure", label: "EAD", fmt: (v) => sar(v as number), align: "right" }, { key: "share_pct", label: "Share", fmt: (v) => pct(v as number), align: "right" },
                   { key: "ews_band", label: "EWS band" }]} />
    </Panel>
  );
}

function Concentration({ title, a, kind, testId, onOpen }: { title: string; a: GraphPayload["analytics"]["suppliers"]; kind: "suppliers" | "customers"; testId: string; onOpen: (id: string) => void }) {
  const key = kind === "suppliers" ? "purchase_share_pct" : "revenue_share_pct";
  const lead = kind === "suppliers" ? "of its purchases" : "of its revenue";
  return (
    <Panel title={title} testId={testId} tone={a.flag ? "warn" : undefined}
           note={`Names in the bank's book ${lead}; the rest is with names the bank does not lend to.`}>
      {a.count === 0 ? <p className="text-sm text-text-secondary" data-testid={`${testId}-none`}>No {kind} in the bank&rsquo;s book.</p> : (
        <>
          <ShareBar testId={`${testId}-bar`} flagAt={a.threshold_pct} other={a.other_share_pct} otherLabel={a.other_label}
                    items={a.rows.map((r: Record<string, unknown>) => ({ label: String(r.name ?? r.borrower_id), value: Number(r[key]) }))} />
          <p className="text-[12px] text-text-secondary" data-testid={`${testId}-lead`}>
            Largest: <b>{pct(a.largest_share_pct)}</b> {lead}{a.flag ? ` (above the ${a.threshold_pct}% flag)` : ""} · in the book {pct(a.in_book_share_pct)} · concentration index {a.hhi}
          </p>
          <Rows testId={`${testId}-rows`} onOpen={onOpen} rows={a.rows}
                cols={[{ key: "borrower_id", label: "Borrower" }, { key: "name", label: "Name" }, { key: key, label: kind === "suppliers" ? "Purchases" : "Revenue", fmt: (v) => pct(v as number), align: "right" },
                       { key: "annual_value_sar_mn", label: "Annual", fmt: (v) => sar(v as number), align: "right" }, { key: "ews_band", label: "EWS band" }]} />
        </>
      )}
    </Panel>
  );
}

function Contagion({ a, onOpen }: { a: GraphPayload["analytics"]["contagion"]; onOpen: (id: string) => void }) {
  const bands = ["critical", "high", "moderate", "low", "none"];
  return (
    <Panel title="Contagion: related names in Early Warning" testId="rel-contagion" tone={a.high_or_critical ? "warn" : undefined}
           note="Every name linked to this borrower, whatever the link, by its Early Warning band.">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">Related names</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-contagion-related">{a.related}</p></div>
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">In Early Warning</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-contagion-warned">{a.in_early_warning}</p></div>
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">High or critical</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-contagion-high">{a.high_or_critical}</p></div>
        <div><p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">EAD in Early Warning</p><p className="text-lg font-semibold tabular-nums" data-testid="rel-contagion-exposure">{sar(a.exposure_in_early_warning)}</p></div>
      </div>
      <Plot height={150} ariaLabel="Related names by Early Warning band" testId="rel-plot-contagion" filename="contagion"
            data={[{ type: "bar", orientation: "h", y: bands.map((b) => BAND_LABEL[b]), x: bands.map((b) => a.by_band[b] ?? 0),
                     marker: { color: bands.map((b) => BAND_COLOURS[b]) }, text: bands.map((b) => `${a.by_band[b] ?? 0} · ${sar(a.exposure_by_band[b] ?? 0)}`),
                     textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{x} names<extra></extra>" }]}
            layout={{ showlegend: false, hovermode: "closest", margin: { l: 80, r: 90, t: 6, b: 24 }, yaxis: { autorange: "reversed" }, xaxis: { dtick: 1, rangemode: "tozero" } }} />
      <Rows testId="rel-contagion-rows" onOpen={onOpen} rows={a.rows.slice(0, 12).map((r: Record<string, unknown>) => ({ ...r, kinds: (r.kinds as string[]).join(", ") }))}
            cols={[{ key: "borrower_id", label: "Borrower" }, { key: "name", label: "Name" }, { key: "kinds", label: "Linked as" },
                   { key: "ews_band", label: "EWS band" }, { key: "exposure", label: "EAD", fmt: (v) => sar(v as number), align: "right" }]} />
    </Panel>
  );
}

function SharedCollateral({ a }: { a: GraphPayload["analytics"]["collateral"] }) {
  return (
    <Panel title="Shared collateral overlap" testId="rel-collateral" tone={a.over_pledged ? "warn" : undefined}
           note="Assets this borrower pledges together with other borrowers, and how much of each asset's value is claimed.">
      {a.count === 0 ? <p className="text-sm text-text-secondary" data-testid="rel-collateral-none">This borrower shares no pledged asset with another borrower.</p> : (
        <>
          <Plot height={Math.max(130, 46 * a.assets.length + 50)} ariaLabel="Claims on each shared asset" testId="rel-plot-collateral" filename="shared-collateral"
                data={Array.from(new Set<string>(a.assets.flatMap((x: { claims: { borrower_id: string }[] }) => x.claims.map((c) => c.borrower_id)))).map((bid, k) => ({
                  type: "bar", orientation: "h", name: bid, y: a.assets.map((x: { collateral_id: string }) => x.collateral_id),
                  x: a.assets.map((x: { claims: { borrower_id: string; allocation_pct: number }[] }) => x.claims.find((c) => c.borrower_id === bid)?.allocation_pct ?? 0),
                  marker: { color: ["#6366f1", "#0ea5e9", "#f59e0b", "#ec4899"][k % 4] }, hovertemplate: `${bid}: %{x:.1f}% of the asset's value<extra></extra>` }))}
                layout={{ barmode: "stack", hovermode: "closest", margin: { l: 70, r: 16, t: 10, b: 36 }, xaxis: { title: { text: "% of the asset's value claimed" }, rangemode: "tozero" },
                          yaxis: { automargin: true },
                          shapes: [{ type: "line", yref: "paper", y0: 0, y1: 1, xref: "x", x0: 100, x1: 100, line: { color: "#dc2626", dash: "dash", width: 2 } }] }} />
          <Rows testId="rel-collateral-rows" rows={a.assets.map((x: { collateral_id: string; type: string; market_value: number; total_pct: number; over_pledged: boolean; claims: { borrower_id: string; allocation_pct: number }[] }) => ({
            collateral_id: x.collateral_id, type: x.type, market_value: x.market_value, claims: x.claims.map((c) => `${c.borrower_id} ${c.allocation_pct.toFixed(0)}%`).join(", "),
            total_pct: x.total_pct, over: x.over_pledged ? "Over-pledged" : "Within value" }))}
                cols={[{ key: "collateral_id", label: "Asset" }, { key: "type", label: "Type" }, { key: "market_value", label: "Value", fmt: (v) => sar(v as number), align: "right" },
                       { key: "claims", label: "Claims" }, { key: "total_pct", label: "Claimed", fmt: (v) => pct(v as number, 0), align: "right" }, { key: "over", label: "" }]} />
        </>
      )}
    </Panel>
  );
}

function Selected({ node, onOpen }: { node: GNode | null; onOpen: (id: string, href?: string) => void }) {
  if (!node) return <p className="text-[12px] text-text-muted" data-testid="rel-selected-hint">Hover a name for its figures. Click a name to open it in Borrower 360.</p>;
  return (
    <div className="space-y-1 text-[12px]" data-testid="rel-selected" data-node-id={node.id}>
      <p className="text-sm font-semibold text-text-primary">{node.name ?? node.id}</p>
      {node.type !== "person" ? (
        <>
          <p className="text-text-secondary">{[node.sector, node.sub_sector].filter(Boolean).join(" · ") || node.region}</p>
          <p>Rating {node.rating ?? "—"} · <Band band={node.ews_band} />{node.ews_score !== null && node.ews_score !== undefined ? ` · score ${node.ews_score}` : ""}</p>
          <p>Exposure {sar(node.exposure)}{node.ecl ? ` · ECL ${sar(node.ecl)}` : ""}</p>
          {node.classification ? <p>Classification <b>{node.classification}</b>{node.level ? ` · ${node.level}` : ""}</p> : null}
          {node.note ? <p className="text-text-secondary">{node.note}</p> : null}
          {node.type === "external" ? <p className="text-text-muted">Off book: from the proposal and bureau.</p>
            : !node.is_focal ? <button type="button" className="mt-1 text-accent hover:underline" onClick={() => onOpen(node.id, node.href)} data-testid="rel-open-selected">Open in Borrower 360</button> : <p className="text-text-muted">The borrower in the middle.</p>}
        </>
      ) : <p className="text-text-secondary">{(node.roles ?? []).map((r) => `${r.role} of ${r.borrower_id}`).join(" · ")}</p>}
    </div>
  );
}

/** The Relationships tab: the network, its legend and filters, and the analytics beside it. */
export function RelationshipsTab({ domain, id, tab, onOpen }: {
  domain: DomainId; id: string; tab: Tab; onOpen: (id: string, domain?: DomainId, period?: string) => void;
}) {
  const [depth, setDepth] = React.useState<1 | 2>(1);
  const base = tab.graph as GraphPayload;
  const wider = useB360<GraphPayload | null>(() => (depth === 2 ? b360.graph(domain, id, tab.period, 2) : Promise.resolve(null)), `graph|${domain}|${id}|${tab.period}|${depth}`);
  const g: GraphPayload = depth === 2 && wider.data ? wider.data : base;
  const kinds = React.useMemo(() => kindsIn(g), [g]);
  const [off, setOff] = React.useState<Set<string>>(new Set());
  const on = React.useMemo(() => new Set<string>(kinds.filter((k) => !off.has(k))), [kinds, off]);
  const [selected, setSelected] = React.useState<GNode | null>(null);
  // PLAN_R9 B7: colour by classification (default) or by Early Warning band.
  const [colourBy, setColourBy] = React.useState<"class" | "ews">("class");
  const shownGraph = React.useMemo<GraphPayload>(() => (colourBy === "class"
    ? { ...g, nodes: g.nodes.map((n) => (n.class_band ? { ...n, ews_band: n.class_band } : n)) } : g), [g, colourBy]);
  const fig = React.useMemo(() => graphFigure(shownGraph, on), [shownGraph, on]);
  const toggle = (k: string) => setOff((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const byId = React.useMemo(() => new Map(g.nodes.map((n) => [n.id, n])), [g]);
  const a = g.analytics;
  const open = (nid: string, href?: string) => {
    const node = byId.get(nid);
    const h = href ?? node?.href;
    const m = h ? new URLSearchParams(h.split("?")[1] ?? "") : null;
    onOpen(nid, (m?.get("domain") as DomainId) ?? domain, m?.get("period") ?? tab.period);
  };
  const corporate = domain === "corporate";

  return (
    <div className="space-y-4" data-testid="rel-tab" data-nodes={fig.shown.nodes} data-edges={fig.shown.edges} data-period={g.period}>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
        <Card className="p-3" data-testid="rel-graph-card">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Network className="size-4 text-accent" aria-hidden />
            <p className="text-[13px] font-semibold text-text-primary">Relationship network at {g.period}</p>
            <span className="text-[11px] text-text-muted" data-testid="rel-counts">{fig.shown.nodes} names · {fig.shown.edges} links{g.truncated.note ? ` · ${g.truncated.note}` : ""}</span>
            <span className="ml-auto inline-flex rounded-md border border-border p-0.5" role="group" aria-label="How far to look">
              {([1, 2] as const).map((d) => (
                <button key={d} type="button" onClick={() => { setDepth(d); setSelected(null); }} aria-pressed={depth === d} data-testid={`rel-depth-${d}`} disabled={!corporate && d === 2}
                        className={cn("rounded px-2 py-1 text-[11px] font-medium", depth === d ? "bg-accent-muted text-accent" : "text-text-secondary hover:text-text-primary", !corporate && d === 2 && "opacity-40")}>
                  {d === 1 ? "Direct links" : "Two steps"}
                </button>
              ))}
            </span>
            <a href={graphExcelHref(domain, id, tab.period, depth)} download data-testid="rel-excel"
               className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-hover">
              <FileSpreadsheet className="size-3.5" aria-hidden /> Export relationships to Excel
            </a>
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Show relationship types" data-testid="rel-legend">
            {kinds.map((k) => {
              const st = KIND_STYLE[k as Kind];
              const isOn = on.has(k);
              return (
                <button key={k} type="button" onClick={() => toggle(k)} aria-pressed={isOn} data-testid={`rel-legend-${k}`} data-count={g.legend[k]?.count ?? 0}
                        className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors", isOn ? "border-border-strong bg-surface text-text-primary" : "border-border text-text-muted line-through")}>
                  <span className="inline-block h-0 w-5 border-t-2" style={{ borderColor: st.colour, borderTopStyle: st.dash === "solid" ? "solid" : st.dash === "dot" ? "dotted" : "dashed" }} aria-hidden />
                  {st.label} <span className="tabular-nums text-text-muted">{g.legend[k]?.count ?? 0}</span>
                </button>
              );
            })}
          </div>
          <div className="relative mt-2">
            <Plot data={fig.data} layout={fig.layout} height={520} ariaLabel={`Relationship network of ${id}`} testId="rel-plot" filename={`relationships-${id}`} scrollZoom
                  onPointClick={(cd) => {
                    const c = cd as { id?: string; type?: string; focal?: boolean; href?: string } | undefined;
                    if (!c?.id) return;
                    setSelected(byId.get(c.id) ?? null);
                    if (c.type !== "person" && c.type !== "external" && !c.focal) open(c.id, c.href);
                  }} />
            <button type="button" onClick={() => setOff(new Set())} title="Show every type" data-testid="rel-reset"
                    className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded border border-border bg-surface px-2 py-1 text-[11px] text-text-secondary hover:bg-surface-hover">
              <Maximize2 className="size-3" aria-hidden /> All types
            </button>
          </div>
        </Card>
        <div className="space-y-3">
          <Card className="space-y-2 p-3" data-testid="rel-key">
            <div className="flex items-center gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Colour: {colourBy === "class" ? "classification" : "Early Warning band"}</p>
              <span className="ml-auto inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Colour by">
                {(["class", "ews"] as const).map((m) => (
                  <button key={m} type="button" onClick={() => setColourBy(m)} aria-pressed={colourBy === m} data-testid={`rel-colour-${m}`}
                          className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", colourBy === m ? "bg-accent-muted text-accent" : "text-text-secondary")}>
                    {m === "class" ? "Class" : "EWS"}
                  </button>
                ))}
              </span>
              <InfoPopover title="Reading the graph">
                <p>Size: exposure to the bank. Ringed: the borrower in the middle. Arrows: supplier to buyer, guarantor to guaranteed, parent to member.</p>
                <p>Hover for values; scroll to zoom, drag to pan, double-click to reset; click a legend type to hide it; click a name to open it.</p>
              </InfoPopover>
            </div>
            {colourBy === "class" ? (
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]" data-testid="rel-class-key">
                {[["critical", "Default · Stage 3 · UTP"], ["high", "Stage 2 · SICR"], ["moderate", "Watch"], ["none", "Performing"]].map(([b, l]) => (
                  <span key={b} className="inline-flex items-center gap-1"><span className="inline-block size-2.5 rounded-full" style={{ background: BAND_COLOURS[b] }} aria-hidden />{l}</span>
                ))}
              </div>
            ) : <div className="flex flex-wrap gap-x-3 gap-y-1">{["critical", "high", "moderate", "low", "none"].map((b) => <Band key={b} band={b} />)}</div>}
          </Card>
          <Card className="p-3"><Selected node={selected} onOpen={open} /></Card>
        </div>
      </div>
      {corporate && g.network_intelligence ? <NetworkInsights ni={g.network_intelligence} /> : null}
      {corporate ? (
        <div className="grid gap-3 xl:grid-cols-2">
          <GroupLimit a={a.group} onOpen={(nid) => open(nid)} />
          <Contagion a={a.contagion} onOpen={(nid) => open(nid)} />
          <Concentration title="Supplier concentration" a={a.suppliers} kind="suppliers" testId="rel-suppliers" onOpen={(nid) => open(nid)} />
          <Concentration title="Customer concentration" a={a.customers} kind="customers" testId="rel-customers" onOpen={(nid) => open(nid)} />
          <SharedCollateral a={a.collateral} />
          <Panel title="Guarantees and workforce" testId="rel-guarantees" note="Guarantees are the book's own Corporate Guarantee collateral; the workforce is the retail customers this borrower employs.">
            <Rows testId="rel-guarantee-rows" rows={a.guarantees.rows} cols={[{ key: "direction", label: "" }, { key: "guarantor_id", label: "Guarantor" }, { key: "guaranteed_id", label: "Guaranteed" },
              { key: "facility_id", label: "Facility" }, { key: "amount", label: "Value", fmt: (v) => sar(v as number), align: "right" }, { key: "basis", label: "Guarantor is" }]} />
            <p className="text-[12px] text-text-secondary" data-testid="rel-workforce">
              {a.workforce.customers ? <>Employs {a.workforce.customers} customers in the retail book (EAD {sar(a.workforce.exposure)}, Stage 2 share {pct(a.workforce.stage2_share_pct)}) at {a.workforce.month}.</> : "No retail customer is recorded as employed by this borrower."}
            </p>
          </Panel>
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          <Panel title="Household" testId="rel-household" note={a.household.members > 1 ? `${a.household.members} customers, SAR ${a.household.exposure.toFixed(2)}m EAD together.` : "This customer is not recorded in a shared household."}>
            <Rows testId="rel-household-rows" onOpen={(cid) => open(cid)} rows={a.household.rows.map((r: Record<string, unknown>) => ({ ...r, borrower_id: undefined }))}
                  cols={[{ key: "customer_id", label: "Customer" }, { key: "role", label: "Role" }, { key: "exposure", label: "EAD", fmt: (v) => sar(v as number), align: "right" }, { key: "ews_band", label: "EWS band" }]} />
          </Panel>
          <Panel title="Employer" testId="rel-employer" note="The corporate borrower that employs this salaried customer, and its colleagues in the retail book.">
            {a.employer.employer ? (
              <div className="space-y-1 text-[12px]" data-testid="rel-employer-detail">
                <button type="button" className="text-sm font-semibold text-accent hover:underline" onClick={() => open(a.employer.employer.borrower_id)} data-testid="rel-employer-open">{a.employer.employer.name} ({a.employer.employer.borrower_id})</button>
                <p>{a.employer.employer.sector} · rating {a.employer.employer.rating} · <Band band={a.employer.employer.ews_band} /> · EAD {sar(a.employer.employer.exposure)}</p>
                <p>{a.employer.colleagues} customers in the retail book work there (EAD {sar(a.employer.colleagues_exposure)}, Stage 2 share {pct(a.employer.colleagues_stage2_share_pct)}).</p>
              </div>
            ) : <p className="text-sm text-text-secondary" data-testid="rel-employer-none">No private-sector employer is recorded for this customer.</p>}
          </Panel>
        </div>
      )}
    </div>
  );
}

/** PLAN_R9 B7: P5 Network Intelligence insights beside the graph. */
function NetworkInsights({ ni }: { ni: NonNullable<GraphPayload["network_intelligence"]> }) {
  return (
    <Card className="space-y-2 p-3" data-testid="rel-network-intelligence" data-cross-default={ni.cross_default_required ? "true" : "false"}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[13px] font-semibold text-text-primary">Network intelligence</p>
        {ni.case ? <span className="rounded bg-accent-muted px-1.5 py-0.5 text-[10px] text-accent" data-testid="rel-case">{ni.case.case} · {ni.case.proposal}</span> : null}
        <span className="text-[11px] text-text-muted">
          {Object.entries(ni.classification_counts).filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(" · ")}
        </span>
        <InfoPopover title="Levels">
          {Object.entries(ni.levels).map(([k, v]) => <p key={k}><b>{k}</b>: {v}</p>)}
        </InfoPopover>
      </div>
      <ul className="space-y-1">
        {ni.insights.map((x, i) => (
          <li key={`${x.key}-${i}`} className="text-[12px]" data-testid={`rel-insight-${x.key}`}>
            <span className={cn("mr-1.5 inline-block size-2 rounded-full", x.severity === "high" ? "bg-negative" : x.severity === "medium" ? "bg-warning" : "bg-positive")} aria-hidden />
            <b className="text-text-primary">{x.title}.</b> <span className="text-text-secondary">{x.text}</span>
          </li>
        ))}
      </ul>
      <PoweredByLine p={ni.powered_by} testId="rel-powered" />
    </Card>
  );
}
