"use client";

import Link from "next/link";
import * as React from "react";
import { Loader2, Search, X } from "lucide-react";

import type { AttentionItem } from "@/components/cockpit-v4/client";
import { Button } from "@/components/ui/button";
import { useCoreAuth } from "@/components/v5/core/auth";
import { type ChartExplain, ChartInfo } from "@/components/v5/core/chart-explain";
import { Plot } from "@/components/v5/ews/plot";
import { contributorsExplain, peersExplain, stageMixExplain, trendExplain } from "./explain";
import { ShareButton } from "@/components/v5/mail/share";
import { AddToReportButton, type BuiltSection } from "@/components/v5/playbook/add-to-report";
import { PolicyNote } from "@/components/v5/policy/policy-note";
import {
  contributorsFigure, fmt, fmtChange, itemText, peersFigure, stageFigure, trendFigure, type ChartsPayload,
} from "@/lib/v5/attention-figures";
import { core, type MailObject } from "@/lib/v5/core";
import { useWs, ws, type AddItem } from "@/lib/v5/workspace";
import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";

/** Which book an item belongs to: the Corporate book keeps quarters, the Retail book months. */
export function itemDomain(item: Pick<AttentionItem, "period_noun">): "corporate" | "retail" {
  return item.period_noun === "month" ? "retail" : "corporate";
}

/** The link back to one attention item: the Cockpit home on the right book, with the item's drawer open. */
export function attentionHref(item: Pick<AttentionItem, "item_id" | "period_noun">): string {
  return `/?domain=${itemDomain(item)}&attention=${encodeURIComponent(item.item_id)}`;
}

export function attentionObject(item: AttentionItem): MailObject {
  return {
    type: "attention-item", id: item.item_id, label: `Attention: ${item.headline}`, href: attentionHref(item),
    summary: item.what_changed.slice(0, 300),
    meta: { domain: itemDomain(item), family: item.family, segment: item.segment, period: item.reporting_period },
  };
}

/** Which policy question an item's movement raises (PLAN_R3 S1-2: the clause behind it, where one applies). */
export function policyMeasure(item: Pick<AttentionItem, "metric" | "family">): { measure: string; driver?: string } {
  const m = item.metric ?? "";
  if (m.startsWith("stage2")) return { measure: "stage2", driver: "downgrade" };
  if (m.startsWith("stage3")) return { measure: "stage3" };
  if (m.startsWith("ecl")) return { measure: "ecl" };
  if (m === "weighted_pd") return { measure: "pd" };
  if (m === "rating_rank") return { measure: "rating", driver: "downgrade" };
  if (m === "uncovered_share") return { measure: "lgd", driver: "collateral" };
  if (m === "past_due_share") return { measure: "dpd" };
  if (m === "concentration_share") return { measure: "concentration" };
  if (m === "covenant_breach_share") return { measure: "ews", driver: "watchlist" };
  return { measure: item.family === "stage_migration" ? "stage2" : "ecl" };
}

/** The item as a Playbook section: the text, its key numbers and the four charts of the drawer. */
async function attentionSection(item: AttentionItem): Promise<BuiltSection> {
  const blocks: BuiltSection["blocks"] = [
    { kind: "paragraph", text: `**${item.headline}.** ${item.what_changed} ${item.why_it_appeared}` },
  ];
  if (item.key_numbers.length) {
    blocks.push({ kind: "table", title: "Key numbers",
                  columns: [{ key: "label", label: "Measure", format: "text" }, { key: "value", label: "Value", format: "text" }],
                  rows: item.key_numbers.map((k) => ({ label: k.label, value: String((k as { display?: string }).display ?? k.value ?? "") })) });
  }
  try {
    const c = await core.attentionCharts({ domain: itemDomain(item), family: item.family, segment: item.segment,
                                           period: item.reporting_period, comparison: item.comparison_period });
    const view = c.contributors.views[0];
    const figs: [string, { data: unknown[]; layout: unknown }][] = [
      [`${c.measure_label}: ${c.segment_label ?? c.segment} against the book`, trendFigure(c)],
      [`${c.segment_label ?? c.segment} against the book, ${c.period}`, peersFigure(c)],
      ...(view ? [[`What drove the movement, ${c.contributors.before} to ${c.contributors.after}`, contributorsFigure(c, view)] as [string, { data: unknown[]; layout: unknown }]] : []),
      ["Stage mix", stageFigure(c)],
    ];
    for (const [title, f] of figs) blocks.push({ kind: "chart", title, figure: { data: f.data, layout: f.layout } } as BuiltSection["blocks"][number]);
  } catch {
    // The charts are optional: the text and numbers still make the section.
  }
  return { title: `Attention: ${item.headline}`, blocks };
}

function Card({ title, note, testId, children, right, info }: { title: string; note?: string; testId: string; children: React.ReactNode; right?: React.ReactNode; info?: ChartExplain }) {
  return (
    <section className="rounded-lg border border-border bg-surface p-3" data-testid={testId}>
      <div className="mb-1 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</h3>
          {note ? <p className="mt-0.5 text-[11px] text-text-muted">{note}</p> : null}
        </div>
        <div className="flex items-center gap-1.5">{right}{info ? <ChartInfo title={title} explain={info} align="right"
          hint="Hover for values · click a legend entry to hide it · drag to zoom, double-click to reset · camera icon saves a PNG." /> : null}</div>
      </div>
      {children}
    </section>
  );
}

/** What a card's charts are drawn for: one family, one segment, one pair of periods (GET /api/v1/attention/charts). */
export interface ChartRequest { domain: "corporate" | "retail"; family: string; segment: string; period?: string; comparison?: string }

/** Charts that explain the issue: the trend, the segment against the book, what contributed, the stage mix. */
export function AttentionCharts({ item }: { item: AttentionItem }) {
  const domain = itemDomain(item);
  return (
    <CardCharts request={{ domain, family: item.family, segment: item.segment, period: item.reporting_period, comparison: item.comparison_period }}
                policy={<PolicyNote book={domain} {...policyMeasure(item)} segment={item.segment_label || item.segment} period={item.reporting_period}
                                    prefix="Policy behind the movement:" testId="attention-policy-note"
                                    className="rounded-lg border border-border bg-surface px-3 py-2" />} />
  );
}

/** The four charts of any Cockpit card (an attention item, an ECL highlight, an ECL panel card), from the chart API. */
export function CardCharts({ request, policy }: { request: ChartRequest; policy?: React.ReactNode }) {
  const { domain, family, segment, period, comparison } = request;
  const key = `attn|${domain}|${family}|${segment}|${period ?? ""}|${comparison ?? ""}`;
  const [attempt, setAttempt] = React.useState(0);
  const charts = useWs(() => core.attentionCharts({ domain, family, segment, period, comparison }), `${key}|${attempt}`);
  const [viewKey, setViewKey] = React.useState<string>("");

  if (charts.error) {
    return (
      <div className="flex items-center gap-2" data-testid="attention-charts-retry" data-error={charts.error}>
        <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>Draw the charts again</Button>
      </div>
    );
  }
  const c: ChartsPayload | null = charts.data;
  if (!c) {
    return <p className="flex items-center gap-2 text-xs text-text-muted" data-testid="attention-charts-loading"><Loader2 className="size-3.5 animate-spin" aria-hidden /> Drawing the charts…</p>;
  }
  const view = c.contributors.views.find((v) => v.key === viewKey) ?? c.contributors.views[0];
  const periodsLabel = c.period_noun === "quarter" ? `last ${c.trend.periods.length} quarters` : `last ${c.trend.periods.length} months`;
  const t = c.trend;
  const prev = t.segment[t.current_index - 1];
  const cur = t.segment[t.current_index];
  const name = c.segment_label ?? c.segment;
  const scope = c.scope ?? "segment";
  const filename = `attention-${c.domain}-${c.family}-${c.segment.replace(/\W+/g, "-")}`;
  const trendTitle = scope === "component" ? `${name}: ${periodsLabel}` : `${c.measure_label}: ${periodsLabel}`;
  const peersTitle = scope === "portfolio" ? `${c.measure_label} by ${c.dimension_label.toLowerCase()}, ${c.period}`
    : scope === "component" ? `Every component of the ECL movement, ${c.comparison_period} to ${c.period}`
    : `${name} against the book, ${c.period}`;
  const contribTitle = scope === "component" ? `What makes up ${name.toLowerCase()}, ${c.contributors.before} to ${c.contributors.after}`
    : `What drove the movement, ${c.contributors.before} to ${c.contributors.after}`;
  const now = `Now ${fmt(cur, c.kind)}${prev === null || prev === undefined ? "" : `, ${fmtChange((cur ?? 0) - (prev ?? 0), c.kind)} on ${t.periods[t.current_index - 1]}`}`;
  return (
    <div className="space-y-3" data-testid="attention-charts" data-chart-period={c.period} data-family={c.family} data-scope={scope}>
      {policy}
      <Card title={trendTitle} testId="attention-chart-trend" note={now} info={trendExplain(c)}>
        <Plot data={trendFigure(c).data} layout={trendFigure(c).layout} height={230} ariaLabel={`${c.measure_label} trend for ${name}`}
              testId="attention-plot-trend" filename={`${filename}-trend`} />
      </Card>
      <Card title={peersTitle} testId="attention-chart-peers" info={peersExplain(c)}
            note={scope === "segment" || c.kind === "share" ? undefined : `${c.peers.book_label} ${fmt(c.peers.book, c.kind)}`}>
        <Plot data={peersFigure(c).data} layout={peersFigure(c).layout} height={Math.max(180, 34 * c.peers.items.length + 70)}
              ariaLabel={`${c.measure_label} by ${c.dimension_label}`} testId="attention-plot-peers" filename={`${filename}-peers`} />
      </Card>
      {view ? (
        <Card title={contribTitle} testId="attention-chart-contributors" info={contributorsExplain(c, view)}
              note={`${fmtChange(view.total_change, c.kind)} in total`}
              right={c.contributors.views.length > 1 ? (
                <select value={view.key} onChange={(e) => setViewKey(e.target.value)} aria-label="Split the movement by" data-testid="attention-contrib-view"
                        className="rounded border border-border bg-surface px-1.5 py-1 text-[11px] text-text-primary">
                  {c.contributors.views.map((v) => <option key={v.key} value={v.key}>By {v.label.toLowerCase()}</option>)}
                </select>
              ) : null}>
          <Plot data={contributorsFigure(c, view).data} layout={contributorsFigure(c, view).layout} height={290}
                ariaLabel={`Contributors to the movement, by ${view.label}`} testId="attention-plot-contributors" filename={`${filename}-contributors`} />
        </Card>
      ) : null}
      <Card title={`Stage mix, ${c.comparison_period} and ${c.period}`} testId="attention-chart-stage" info={stageMixExplain(c)}>
        <Plot data={stageFigure(c).data} layout={stageFigure(c).layout} height={240} ariaLabel={`Stage mix: ${c.stage_mix.basis}`}
              testId="attention-plot-stage" filename={`${filename}-stage`} />
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- add to

/** Add to report goes to Playbook (AddToReportButton); this dialog is Add to investigation. */
type Target = "investigation";

function AddDialog({ target, item, onClose }: { target: Target; item: AttentionItem; onClose: () => void }) {
  const { viewingAs } = useCoreAuth();
  const list = useWs<{ id: string; title: string }[]>(
    () => ws.investigations().then((r) => r.investigations),
    `add|${target}`);
  const rows = list.data;
  const [choice, setChoice] = React.useState<string>("");
  const [title, setTitle] = React.useState(item.headline);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState<{ id: string; title: string } | null>(null);
  const isNew = choice === "" || choice === "__new";
  const noun = "investigation";

  React.useEffect(() => {
    // Capture phase and stopped: an Escape that closes this dialog must not also close the drawer under it.
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  async function add() {
    setBusy(true);
    setError(null);
    const payload: AddItem = { title: item.headline, body: itemText(item), href: attentionHref(item), label: `Attention: ${item.headline}`, type: "attention-item" };
    try {
      const inv = isNew ? await ws.createInvestigation(title.trim() || item.headline) : { id: choice, title: rows?.find((r) => r.id === choice)?.title ?? "" };
      const out = await ws.addToInvestigation(inv.id, payload);
      setDone({ id: out.id, title: out.title });
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const href = done ? `/investigations/${done.id}` : "";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-label={`Add to ${noun}`} data-testid={`add-${target}-dialog`} className="w-full max-w-[480px] rounded-xl border border-border bg-surface p-5 shadow-2xl">
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-text-primary">Add to {noun}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X className="size-4" /></button>
        </div>
        <p className="mt-1 text-xs text-text-muted">{item.headline}. The text and numbers come from the card, with a link back to it.</p>
        {done ? (
          <div className="mt-4 space-y-3" data-testid={`add-${target}-done`}>
            <p className="text-sm text-positive">Added to {done.title}.</p>
            <div className="flex gap-2">
              <Button asChild variant="outline" size="sm"><Link href={href} data-testid={`add-${target}-open`}>Open the {noun}</Link></Button>
              <Button size="sm" onClick={onClose}>Done</Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            {viewingAs ? <p role="alert" className="text-sm text-warning">You are viewing as {viewingAs.name}. Stop viewing as to add.</p> : null}
            <fieldset className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              <legend className="px-1 text-[11px] text-text-muted">Which {noun}</legend>
              {(rows ?? []).map((r) => (
                <label key={r.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover">
                  <input type="radio" name="target" checked={choice === r.id} onChange={() => setChoice(r.id)} data-testid={`add-${target}-existing`} data-id={r.id} />
                  <span className="min-w-0 truncate">{r.title}</span>
                </label>
              ))}
              <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-hover">
                <input type="radio" name="target" checked={isNew} onChange={() => setChoice("__new")} data-testid={`add-${target}-new`} />
                <span>A new {noun}</span>
              </label>
            </fieldset>
            {isNew ? (
              <div className="space-y-2">
                <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-label="Title" data-testid={`add-${target}-title`}
                       className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none" />
              </div>
            ) : null}
            {error ? <p role="alert" className="text-sm text-negative" data-testid={`add-${target}-error`}>{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
              <Button size="sm" onClick={() => void add()} disabled={busy || !!viewingAs || (isNew && !title.trim())} data-testid={`add-${target}-confirm`}>
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} Add
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Share, Add to investigation and Add to report: the three things to do with an item besides investigating it. */
export function AttentionActions({ item }: { item: AttentionItem }) {
  const [open, setOpen] = React.useState<Target | null>(null);
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="attention-actions">
      <ShareButton object={attentionObject(item)} testId="attention-share" />
      <Button variant="outline" size="sm" onClick={() => setOpen("investigation")} data-testid="attention-add-investigation"><Search aria-hidden /> Add to investigation</Button>
      <AddToReportButton source={attentionObject(item)} build={() => attentionSection(item)} testId="attention-add-report"
                         defaultTemplate="risk-committee-report" defaultTitle={`Attention: ${item.headline}`} />
      {open ? <AddDialog target={open} item={item} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

/** Opens the drawer of the item named in `?attention=` (a link from Mail or a report), on the item's own book. */
export function AttentionDeepLink({ attention, onOpen, onDomain, readItem }: {
  attention: string | null; onOpen: (item: AttentionItem) => void; onDomain: (d: "corporate" | "retail") => void;
  readItem: (id: string) => Promise<{ item: AttentionItem }>;
}) {
  const done = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!attention || done.current === attention) return;
    done.current = attention;
    readItem(attention).then(({ item }) => {
      onDomain(itemDomain(item));
      onOpen(item);
    }, () => undefined);
  }, [attention, onOpen, onDomain, readItem]);
  return null;
}
