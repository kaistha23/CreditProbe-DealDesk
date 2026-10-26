"use client";

/**
 * How a Playbook section reads on screen: every block kind of PLAYBOOK_API.md 3.2 (paragraph, heading,
 * bullets, key figures, tables, charts, red/amber/green verdicts, callouts), plus the small pieces the
 * Playbook screens share (status pill, people initials, the "Imported from" provenance chip).
 *
 * Figures arrive as raw numbers with a format and are formatted here, once, by `formatValue`, so the
 * screen and the Word export say the same thing.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowUpRight, Info, OctagonAlert, TriangleAlert, X } from "lucide-react";

import { ChartInfo } from "@/components/v5/core/chart-explain";
import { Plot } from "@/components/v5/ews/plot";
import { useDirectory } from "@/components/v5/mail/people";
import { cn } from "@/lib/utils";
import { hasRichMarkdown, numericColumn, parseMarkdown } from "@/lib/v5/markdown";
import {
  type Block, type BulletsBlock, type CalloutBlock, type ChartBlock, type HeadingBlock, type KpisBlock, type ParagraphBlock,
  type Person, type PlaybookSource, type Rag, type RagBlock, type ReportStatus, type TableBlock, RAG_LABEL, formatDelta,
  formatValue, initialsOf, isNumericFormat, statusLabel,
} from "@/lib/v5/playbook";

import { playbookChartExplain } from "./explain";

// ---------------------------------------------------------------- shared pieces

const STATUS_TONE: Record<ReportStatus, string> = {
  draft: "bg-surface-sunken text-text-secondary border-border",
  in_review: "bg-warning-muted text-warning border-warning/30",
  approved: "bg-positive-muted text-positive border-positive/30",
  presented: "bg-info-muted text-info border-info/30",
};
const STATUS_DOT: Record<ReportStatus, string> = {
  draft: "bg-text-muted", in_review: "bg-warning", approved: "bg-positive", presented: "bg-info",
};

/** A report's workflow status, in words and colour. */
export function ReportStatusPill({ status, testId, className }: { status: string; testId?: string; className?: string }) {
  const s = status as ReportStatus;
  return (
    <span data-testid={testId} data-status={status}
          className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                        STATUS_TONE[s] ?? STATUS_TONE.draft, className)}>
      <span aria-hidden className={cn("size-1.5 rounded-full", STATUS_DOT[s] ?? STATUS_DOT.draft)} />
      {statusLabel(status)}
    </span>
  );
}

export function Initials({ person, size = 24, className }: { person: Person | null | undefined; size?: number; className?: string }) {
  return (
    <span title={person?.name ?? ""} style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.38)) }}
          className={cn("inline-flex shrink-0 items-center justify-center rounded-full bg-accent-muted font-semibold text-accent ring-2 ring-surface", className)}>
      <span aria-hidden>{initialsOf(person)}</span>
      <span className="sr-only">{person?.name ?? ""}</span>
    </span>
  );
}

/** Overlapping initials for a list of people (reviewers). */
export function PeopleStack({ people, max = 4, size = 24 }: { people: Person[] | null | undefined; max?: number; size?: number }) {
  const list = people ?? [];
  if (!list.length) return <span className="text-xs text-text-muted">—</span>;
  const shown = list.slice(0, max);
  return (
    <span className="inline-flex items-center -space-x-1.5" title={list.map((p) => p.name).join(", ")}>
      {shown.map((p) => <Initials key={p.username} person={p} size={size} />)}
      {list.length > max ? (
        <span style={{ width: size, height: size }}
              className="inline-flex items-center justify-center rounded-full bg-surface-sunken text-[10px] font-semibold text-text-secondary ring-2 ring-surface">
          +{list.length - max}
        </span>
      ) : null}
    </span>
  );
}

/** "Imported from <label>": the section's link back to where it came from. */
export function Provenance({ source, className }: { source: PlaybookSource | null | undefined; className?: string }) {
  if (!source) return null;
  const inner = (
    <>
      <span className="text-text-muted">Imported from</span>
      <span className="max-w-[320px] truncate font-medium">{source.label}</span>
      {source.href ? <ArrowUpRight className="size-3 shrink-0" aria-hidden /> : null}
    </>
  );
  const cls = cn("inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-surface-sunken px-2 py-0.5 text-[11px] text-accent",
                 className);
  if (!source.href || !source.href.startsWith("/")) return <span className={cls} data-testid="playbook-provenance">{inner}</span>;
  return (
    <Link href={source.href} className={cn(cls, "transition-colors hover:border-accent/50 hover:bg-accent-muted")}
          title={source.summary || source.label} data-testid="playbook-provenance" data-href={source.href}>
      {inner}
    </Link>
  );
}

/** Reviewers picked from the user directory: chips plus a typeahead. */
export function ReviewerPicker({ value, onChange, testId = "playbook-reviewers", label = "Reviewers" }: {
  value: string[]; onChange: (v: string[]) => void; testId?: string; label?: string;
}) {
  const users = useDirectory();
  const [text, setText] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const byName = React.useMemo(() => new Map(users.map((u) => [u.username, u])), [users]);
  const needle = text.trim().toLowerCase();
  const options = users.filter((u) => !value.includes(u.username)
    && (!needle || `${u.name} ${u.username} ${u.role} ${u.title}`.toLowerCase().includes(needle))).slice(0, 30);

  React.useEffect(() => {
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const add = (username: string) => { onChange([...value, username]); setText(""); setOpen(false); };

  return (
    <div ref={ref} className="relative" data-testid={testId}>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 focus-within:border-accent">
        {value.map((u) => {
          const p = byName.get(u);
          return (
            <span key={u} className="inline-flex items-center gap-1 rounded-full bg-accent-muted py-0.5 pl-0.5 pr-1.5 text-xs text-accent"
                  data-testid={`${testId}-chip`} data-username={u}>
              <Initials person={p ? { username: u, name: p.name, initials: p.initials } : { username: u, name: u }} size={18} className="ring-0" />
              {p?.name ?? u}
              <button type="button" onClick={() => onChange(value.filter((x) => x !== u))} aria-label={`Remove ${p?.name ?? u}`}>
                <X className="size-3" aria-hidden />
              </button>
            </span>
          );
        })}
        <input value={text} onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
               onKeyDown={(e) => {
                 if (e.key === "Enter") { e.preventDefault(); if (options[0]) add(options[0].username); }
                 if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); }
                 if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
               }}
               placeholder={value.length ? "" : "Add reviewers"} aria-label={label} data-testid={`${testId}-input`}
               className="min-w-[120px] flex-1 bg-transparent py-1 text-sm text-text-primary outline-none placeholder:text-text-muted" />
      </div>
      {open && options.length > 0 ? (
        <ul role="listbox" aria-label={`${label} options`} data-testid={`${testId}-options`}
            className="absolute z-30 mt-1 max-h-60 w-full overflow-y-auto rounded-md border border-border bg-surface p-1 shadow-lg">
          {options.map((u) => (
            <li key={u.username}>
              <button type="button" role="option" aria-selected="false" onClick={() => add(u.username)} data-username={u.username}
                      className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-hover">
                <Initials person={{ username: u.username, name: u.name, initials: u.initials || initialsOf({ username: u.username, name: u.name }) }} size={22} className="ring-0" />
                <span className="min-w-0">
                  <span className="block truncate text-text-primary">{u.name}</span>
                  <span className="block truncate text-xs text-text-muted">{u.title || u.role}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- light markdown

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;

/** `**bold**` and `*italic*`, nothing else. */
export function Inline({ text }: { text: string }) {
  const parts = String(text ?? "").split(INLINE);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**") && p.length > 4) {
          return <strong key={i} className="font-semibold text-text-primary">{p.slice(2, -2)}</strong>;
        }
        if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <em key={i}>{p.slice(1, -1)}</em>;
        return <React.Fragment key={i}>{p}</React.Fragment>;
      })}
    </>
  );
}

// ---------------------------------------------------------------- tones

const RAG_PILL: Record<Rag, string> = {
  green: "bg-positive-muted text-positive border-positive/30",
  amber: "bg-warning-muted text-warning border-warning/30",
  red: "bg-negative-muted text-negative border-negative/30",
};
const RAG_DOT: Record<Rag, string> = { green: "bg-positive", amber: "bg-warning", red: "bg-negative" };

/** A verdict says its colour in words as well, so it reads in print and to a screen reader. */
export function RagPill({ status }: { status: Rag | null | undefined }) {
  if (!status || !RAG_LABEL[status]) return <span className="text-text-muted">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold", RAG_PILL[status])}
          data-rag={status}>
      <span aria-hidden className={cn("size-2 rounded-full", RAG_DOT[status])} />
      {RAG_LABEL[status]}
    </span>
  );
}

// ---------------------------------------------------------------- blocks

/**
 * PLAN_R5 P2: assistant markdown rendered properly. Pipe tables are real house-style tables (never raw pipes),
 * quotes lose their markers, headings are headings. `inline` renders a run of text (bold, italics, links).
 */
export function MarkdownBody({ text, inline, className, testId = "markdown-body" }: {
  text: string; inline?: (t: string) => React.ReactNode; className?: string; testId?: string;
}) {
  const parts = React.useMemo(() => parseMarkdown(text), [text]);
  const run = inline ?? ((t: string) => <Inline text={t} />);
  return (
    <div className={cn("space-y-2.5", className)} data-testid={testId}>
      {parts.map((p, i) => {
        if (p.type === "table") {
          const block: TableBlock = {
            kind: "table",
            columns: p.header.map((h, j) => ({ key: `c${j}`, label: h.replace(/\*\*/g, ""), format: "text" })),
            rows: p.rows.map((r) => Object.fromEntries(p.header.map((_, j) => [`c${j}`, (r[j] ?? "").replace(/\*\*/g, "")]))),
          } as TableBlock;
          return <div key={i} data-testid="markdown-table"><TableView block={block} /></div>;
        }
        if (p.type === "heading") {
          return p.level <= 2
            ? <p key={i} className="pt-1 text-[15px] font-semibold text-text-primary">{run(p.text)}</p>
            : <p key={i} className="pt-1 text-[14px] font-semibold text-text-primary">{run(p.text)}</p>;
        }
        if (p.type === "quote") {
          return (
            <div key={i} className="space-y-2 border-l-2 border-accent/40 pl-3">
              {p.paragraphs.map((q, j) => <p key={j} className="whitespace-pre-line">{run(q)}</p>)}
            </div>
          );
        }
        if (p.type === "list") {
          const Tag = p.ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={cn("space-y-1 pl-5", p.ordered ? "list-decimal" : "list-disc marker:text-accent")}>
              {p.items.map((it, j) => <li key={j}>{run(it)}</li>)}
            </Tag>
          );
        }
        return <p key={i} className="whitespace-pre-line">{run(p.text)}</p>;
      })}
    </div>
  );
}

function Paragraph({ block }: { block: ParagraphBlock }) {
  if (hasRichMarkdown(block.text)) {
    return <MarkdownBody text={block.text} className="text-[14px] leading-[1.7] text-text-primary" testId="playbook-markdown" />;
  }
  const paras = String(block.text ?? "").split(/\n{2,}/).filter((p) => p.trim());
  return (
    <div className="space-y-2.5 text-[14px] leading-[1.7] text-text-primary">
      {paras.map((p, i) => <p key={i} className="whitespace-pre-line"><Inline text={p} /></p>)}
    </div>
  );
}

function Heading({ block }: { block: HeadingBlock }) {
  if (block.level === 3) return <h4 className="pt-1 text-[14px] font-semibold text-text-primary"><Inline text={block.text} /></h4>;
  return <h3 className="pt-2 text-[16px] font-semibold text-text-primary"><Inline text={block.text} /></h3>;
}

function Bullets({ block }: { block: BulletsBlock }) {
  return (
    <ul className="ml-5 list-disc space-y-1.5 text-[14px] leading-[1.65] text-text-primary marker:text-accent">
      {(block.items ?? []).map((item, i) => <li key={i}><Inline text={item} /></li>)}
    </ul>
  );
}

function Kpis({ block }: { block: KpisBlock }) {
  const items = block.items ?? [];
  return (
    <div className={cn("grid gap-3", items.length <= 2 ? "grid-cols-2" : items.length === 3 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2 sm:grid-cols-4")}>
      {items.map((k, i) => (
        <div key={`${k.label}-${i}`} className="relative overflow-hidden rounded-lg border border-border bg-surface p-3.5" data-testid="playbook-kpi">
          {k.status ? <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", RAG_DOT[k.status])} /> : null}
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{k.label}</p>
          <p className="mt-1 text-[22px] font-semibold leading-tight tabular-nums text-text-primary">{formatValue(k.value, k.format)}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
            {k.delta !== undefined && k.delta !== null ? (
              <span className="tabular-nums text-text-secondary">{formatDelta(k.delta, k.format)}</span>
            ) : null}
            {k.status && RAG_LABEL[k.status] ? (
              <span className="inline-flex items-center gap-1 font-medium text-text-secondary">
                <span aria-hidden className={cn("size-2 rounded-full", RAG_DOT[k.status])} />
                {RAG_LABEL[k.status]}
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function BlockTitle({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-[13px] font-semibold text-text-primary">{children}</p>;
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-[11px] leading-relaxed text-text-muted">{children}</p>;
}

export function TableView({ block }: { block: TableBlock }) {
  const columns = block.columns ?? [];
  const rows = block.rows ?? [];
  // Text columns that hold only figures (a table an assistant wrote) align like numbers.
  const right = React.useMemo(() => new Set(columns.filter((c) => isNumericFormat(c.format)
    || (c.format === "text" && numericColumn(rows.map((r) => r?.[c.key])))).map((c) => c.key)), [columns, rows]);
  return (
    <figure>
      {block.title ? <BlockTitle>{block.title}</BlockTitle> : null}
      <div className="max-h-[520px] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 z-[1]">
            <tr className="bg-accent text-accent-contrast">
              {columns.map((c) => (
                <th key={c.key} scope="col"
                    className={cn("whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.05em]",
                                  right.has(c.key) ? "text-right" : "text-left")}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={Math.max(1, columns.length)} className="px-3 py-4 text-center text-text-muted">No rows.</td></tr>
            ) : rows.map((r, i) => (
              <tr key={i} className={cn("border-t border-border", i % 2 === 1 ? "bg-surface-sunken" : "bg-surface")}>
                {columns.map((c) => (
                  <td key={c.key}
                      className={cn("px-3 py-1.5 text-text-primary", right.has(c.key) ? "whitespace-nowrap text-right tabular-nums" : "text-left")}>
                    {formatValue(r?.[c.key], c.format)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.note ? <Note>{block.note}</Note> : null}
    </figure>
  );
}

const PALETTE = Array.from({ length: 8 }, (_, i) => `var(--ipm-chart-${i + 1})`);

type Trace = Record<string, unknown>;

/** Give traces that name no colour the house palette, in fixed order. */
function colourTraces(data: Trace[]): Trace[] {
  return data.map((t, i) => {
    const type = String(t.type ?? "scatter");
    const marker = (t.marker && typeof t.marker === "object" ? t.marker : {}) as Trace;
    if (type === "pie") {
      if (marker.colors) return t;
      const n = Array.isArray(t.labels) ? t.labels.length : Array.isArray(t.values) ? t.values.length : 8;
      return { ...t, marker: { ...marker, colors: Array.from({ length: n }, (_, j) => PALETTE[j % PALETTE.length]) } };
    }
    if (type === "heatmap" || type === "contour" || type === "histogram2d" || type === "choropleth") return t;
    const colour = PALETTE[i % PALETTE.length];
    const line = (t.line && typeof t.line === "object" ? t.line : {}) as Trace;
    const out: Trace = { ...t };
    if (!marker.color) out.marker = { ...marker, color: colour };
    if (type === "scatter" && !line.color) out.line = { ...line, color: colour, width: line.width ?? 2.25 };
    return out;
  });
}

function ChartView({ block }: { block: ChartBlock }) {
  const figure = block.figure ?? null;
  const data = React.useMemo(() => colourTraces(Array.isArray(figure?.data) ? figure.data : []), [figure]);
  const layout = React.useMemo(() => {
    const l = { ...((figure?.layout ?? {}) as Trace) };
    delete l.title;
    delete l.width;
    const traces = Array.isArray(figure?.data) ? figure.data : [];
    if (traces.length > 0 && traces.every((t) => t.type === "pie")) l.hovermode = "closest";
    return l;
  }, [figure]);
  const height = typeof figure?.layout?.height === "number" ? (figure.layout.height as number) : 320;
  const slug = (block.title || "chart").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (
    <figure className="rounded-lg border border-border bg-surface p-3">
      {block.title || data.length > 0 ? (
        <div className="flex items-start justify-between gap-2">
          {block.title ? <BlockTitle>{block.title}</BlockTitle> : <span />}
          {data.length > 0 ? <ChartInfo title={block.title || "About this chart"} explain={playbookChartExplain(block.title || "", figure)} align="right"
            hint="Hover for values · click a legend entry to hide it · drag to zoom, double-click to reset · camera icon saves a PNG." /> : null}
        </div>) : null}
      {data.length > 0 ? (
        <Plot data={data} layout={layout} height={height} ariaLabel={block.title || "Chart"} testId="playbook-chart"
              filename={`playbook-${slug}`} />
      ) : block.png_base64 ? (
        // A rendered PNG sent with the section: the figure itself was not included.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={`data:image/png;base64,${block.png_base64}`} alt={block.title || "Chart"} className="mx-auto max-h-[420px] w-auto" />
      ) : (
        <p className="py-6 text-center text-xs text-text-muted">This chart has no data to draw.</p>
      )}
      {block.note ? <Note>{block.note}</Note> : null}
    </figure>
  );
}

function RagView({ block }: { block: RagBlock }) {
  const items = block.items ?? [];
  return (
    <figure>
      {block.title ? <BlockTitle>{block.title}</BlockTitle> : null}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-surface-sunken text-left text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">
              <th scope="col" className="px-3 py-2">Test</th>
              <th scope="col" className="px-3 py-2 text-right">Value</th>
              <th scope="col" className="px-3 py-2">Threshold</th>
              <th scope="col" className="px-3 py-2">Verdict</th>
              <th scope="col" className="px-3 py-2">Comment</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={`${r.test}-${i}`} className="border-t border-border align-top" data-testid="playbook-rag-row" data-status={r.status}>
                <td className="px-3 py-2 font-medium text-text-primary">{r.test}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-text-primary">{formatValue(r.value, r.format)}</td>
                <td className="px-3 py-2 text-text-secondary">{r.threshold || "—"}</td>
                <td className="px-3 py-2"><RagPill status={r.status} /></td>
                <td className="px-3 py-2 text-text-secondary">{r.comment ? <Inline text={r.comment} /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

const CALLOUT: Record<CalloutBlock["tone"], { cls: string; icon: React.ComponentType<{ className?: string }>; label: string }> = {
  info: { cls: "border-info/30 bg-info-muted text-info", icon: Info, label: "Note" },
  warning: { cls: "border-warning/30 bg-warning-muted text-warning", icon: TriangleAlert, label: "Warning" },
  critical: { cls: "border-negative/30 bg-negative-muted text-negative", icon: OctagonAlert, label: "Critical" },
};

function Callout({ block }: { block: CalloutBlock }) {
  const tone = CALLOUT[block.tone] ?? CALLOUT.info;
  const Icon = tone.icon;
  return (
    <div className={cn("flex gap-3 rounded-lg border border-l-4 px-4 py-3", tone.cls)} role="note" aria-label={tone.label}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="space-y-2 text-[14px] leading-[1.6] text-text-primary">
        {String(block.text ?? "").split(/\n{2,}/).map((p, i) => <p key={i} className="whitespace-pre-line"><Inline text={p} /></p>)}
      </div>
    </div>
  );
}

export function BlockView({ block }: { block: Block }) {
  switch (block?.kind) {
    case "paragraph": return <Paragraph block={block} />;
    case "heading": return <Heading block={block} />;
    case "bullets": return <Bullets block={block} />;
    case "kpis": return <Kpis block={block} />;
    case "table": return <TableView block={block} />;
    case "chart": return <ChartView block={block} />;
    case "rag": return <RagView block={block} />;
    case "callout": return <Callout block={block} />;
    default: return null;
  }
}

export function Blocks({ blocks, className }: { blocks: Block[] | null | undefined; className?: string }) {
  const list = blocks ?? [];
  return (
    <div className={cn("space-y-4", className)}>
      {list.map((b, i) => (
        <div key={b.id ?? `${b.kind}-${i}`} data-testid="playbook-block" data-kind={b.kind}><BlockView block={b} /></div>
      ))}
    </div>
  );
}
