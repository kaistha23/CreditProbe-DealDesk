"use client";

/**
 * The pieces every level of the v5 Early Warning screen is built from.
 *
 * Visual vocabulary ported from the Retail Demo (c0db151f,
 * app/early-warning/parts.tsx) so a tile, a band badge and a reason row look
 * the same at portfolio, segment, sub-segment and customer level. The data
 * underneath is the Early Warning service (rule set gw-ews-1.1.0), for both
 * books.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { FileSpreadsheet, FlaskConical, LineChart, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  type Card as LevelCard, type Counts, type DomainId, type ExcelParams, type Level, type Reason, type SourceShare,
  type TrendPoint, asOfLabel, count, ews, excelHref, pct, sar, shortPeriod, signed,
} from "@/lib/v5/ews";
import { quietTrendNote } from "@/lib/v5/ews-trend";

import { CHART_HINT, CardTrendPlot, ChartDialog, LevelTrendPlot } from "./charts";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { cardTrendExplain, levelTrendExplain } from "./explain";
import { Spark } from "./spark";

export function bandTone(band: string): string {
  switch ((band || "").toLowerCase()) {
    case "critical":
      return "bg-negative-muted text-negative border-negative/30";
    case "high":
      return "bg-warning-muted text-warning border-warning/30";
    case "moderate":
      return "bg-accent-muted text-accent border-accent/30";
    default:
      return "bg-surface-muted text-text-secondary border-border";
  }
}

export function Band({ band, className }: { band: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold"
                        + " uppercase tracking-[0.08em]", bandTone(band), className)}
          data-testid={`ews-band-${(band || "none").toLowerCase()}`}>
      {band || "none"}
    </span>
  );
}

/** The as-of line every screen carries: the book, its period and its calendar. */
export function AsOf({ domain, period, release, testId }: {
  domain: DomainId; period: string; release?: string; testId?: string;
}) {
  return (
    <p className="text-[11px] text-text-muted" data-testid={testId ?? "ews-as-of"}>
      <span className="font-semibold uppercase tracking-[0.08em] text-text-secondary">As of</span>{" "}
      {asOfLabel(period)} · {domain === "corporate" ? "Corporate · quarterly" : "Retail · monthly"} · SAR
      {release ? <> · <span className="font-mono">{release}</span></> : null}
    </p>
  );
}

export function Kpi({ label, value, sub, testId, tone, onClick, hint }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; testId?: string;
  tone?: "negative" | "warning" | "default"; onClick?: () => void; hint?: string;
}) {
  const body = (
    <>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{label}</p>
      <p className={cn("mt-1 text-[22px] font-semibold leading-tight tabular-nums",
                       tone === "negative" && "text-negative", tone === "warning" && "text-warning")}>
        {value}
      </p>
      {sub ? <p className="mt-0.5 text-[11px] text-text-muted">{sub}</p> : null}
      {onClick ? <p className="mt-1 text-[10px] text-accent">{hint ?? "Open the list"}</p> : null}
    </>
  );
  if (!onClick) return <Card className="p-3.5" data-testid={testId}>{body}</Card>;
  return (
    <Card className="p-0" data-testid={testId}>
      <button type="button" onClick={onClick}
              className="w-full p-3.5 text-left transition-colors hover:bg-surface-muted/60">
        {body}
      </button>
    </Card>
  );
}

export function Figure({ label, value, tone }: {
  label: string; value: React.ReactNode; tone?: "negative" | "warning";
}) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("text-[13px] font-medium tabular-nums", tone === "negative" && "text-negative",
                       tone === "warning" && "text-warning")}>{value}</p>
    </div>
  );
}

/** The counts every card carries, laid out once. */
export function CountsRow({ counts, owners }: { counts: Counts; owners: string }) {
  const Owners = owners.charAt(0).toUpperCase() + owners.slice(1);
  return (
    <div className="grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-5">
      <Figure label={Owners} value={count(counts.customers)} />
      <Figure label="Warned" value={count(counts.customers_warned)} />
      <Figure label="High or critical" value={count(counts.high_or_critical)} tone="warning" />
      <Figure label="Already bad" value={count(counts.current_bad)} tone="negative" />
      <Figure label="Forward risk" value={count(counts.forward_risk)} tone="warning" />
      <Figure label="Exposure" value={sar(counts.exposure)} />
      <Figure label="High/critical exposure" value={sar(counts.exposure_severe)} />
      <Figure label="% exposure warned" value={pct(counts.exposure_warned_pct)} />
      <Figure label="Default-entry rate" value={pct(counts.odr_pct, 2)} />
      <Figure label="30+ DPD exposure" value={pct(counts.dpd_30_plus_pct)} />
    </div>
  );
}

/**
 * Three six-period sparklines on every card: warned, default-entry rate,
 * high/critical exposure. Given a `cardKey`, they are one button that opens
 * the card's full interactive chart in a dialog.
 */
export function CardTrends({ trend, owners, testId, cardKey, title }: {
  trend: TrendPoint[]; owners: string; testId?: string; cardKey?: string; title?: string;
}) {
  const [open, setOpen] = React.useState(false);
  // All three series zero in every period shown: one line, not three flat ones (PLAN_R6 E5).
  const quiet = quietTrendNote(trend);
  if (quiet) {
    return (
      <p className="rounded-md bg-surface-muted/60 px-3 py-2 text-xs text-text-secondary"
         data-testid={testId ? `${testId}-quiet` : "ews-trends-quiet"}>
        {quiet}
      </p>
    );
  }
  const sparks = (
    <div className="grid grid-cols-3 gap-4" data-testid={testId}>
      <Spark label={`Warned ${owners}`} tone="warning" height={40} testId={`${testId}-warned`} directional
             points={trend.map((p) => ({ period: p.period, value: p.customers_warned }))} />
      <Spark label="Default-entry rate" unit="%" tone="negative" height={40} testId={`${testId}-odr`} directional
             points={trend.map((p) => ({ period: p.period, value: p.odr_pct }))} />
      <Spark label="High/critical EAD (SAR m)" tone="accent" height={40} testId={`${testId}-severe`} directional
             points={trend.map((p) => ({ period: p.period, value: p.exposure_severe }))} />
    </div>
  );
  if (!cardKey) return sparks;
  return (
    <>
      <div className="-mb-1 flex justify-end">
        <ChartInfo title={`${title ?? cardKey} · trend`} explain={cardTrendExplain(trend, owners, title)} align="right" />
      </div>
      <button type="button" onClick={() => setOpen(true)} data-testid={`ews-trend-open-${cardKey}`}
              aria-haspopup="dialog" title="Open the interactive chart"
              className="group w-full rounded-md p-1 -m-1 text-left transition-colors hover:bg-surface-muted/60">
        {sparks}
        <span className="mt-0.5 flex items-center gap-1 text-[10px] text-accent">
          <LineChart className="size-3" aria-hidden /> Open the interactive chart
        </span>
      </button>
      {open ? (
        <ChartDialog title={`${title ?? cardKey} · trend`} onClose={() => setOpen(false)}
                     subtitle={`${trend.length} periods, ${trend[0] ? shortPeriod(trend[0].period) : ""} to ${trend.length ? shortPeriod(trend[trend.length - 1].period) : ""}.`}>
          <div className="mb-1 flex justify-end"><ChartInfo title={`${title ?? cardKey} · trend`} explain={cardTrendExplain(trend, owners, title)} hint={CHART_HINT} /></div>
          <CardTrendPlot trend={trend} owners={owners} testId={`ews-trend-dialog-chart`}
                         filename={`early-warning-${cardKey}-trend`} />
        </ChartDialog>
      ) : null}
    </>
  );
}

/** The level's own trend, interactive (Plotly): warned, high or critical, forward risk. */
export function TrendChart({ trend, owners, testId }: { trend: TrendPoint[]; owners: string; testId?: string }) {
  return (
    <Card className="p-4" data-testid={testId ?? "ews-trend-chart"}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-sm font-semibold text-text-primary">{trend.length === 6 ? "Six-period" : `${trend.length}-period`} trend</p>
        <ChartInfo title="Trend" explain={levelTrendExplain(trend, owners)} hint={CHART_HINT} />
      </div>
      <div className="mt-1">
        <LevelTrendPlot trend={trend} owners={owners} />
      </div>
    </Card>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  bank_internal: "Bank internal", bureau: "Bureau", open_banking: "Open Banking",
};
const SOURCE_ORDER = Object.keys(SOURCE_LABELS);

/** "Warned by source: Bank internal 812 · Bureau 140 · Open Banking 95". Nothing when not published. */
export function BySource({ sources, testId, className }: {
  sources: SourceShare[] | null | undefined; testId?: string; className?: string;
}) {
  if (!sources?.length) return null;
  const rank = (k: string) => { const i = SOURCE_ORDER.indexOf(k); return i < 0 ? SOURCE_ORDER.length : i; };
  const rows = [...sources].sort((a, b) => rank(a.key) - rank(b.key));
  return (
    <p className={cn("text-[11px] text-text-secondary", className)} data-testid={testId}>
      <span className="text-text-muted">Warned by source:</span>{" "}
      {rows.map((s, i) => (
        <React.Fragment key={s.key}>
          {i ? <span className="text-text-muted"> · </span> : null}
          <span title={s.share_pct != null ? `${pct(s.share_pct)} of warned` : undefined}
                data-source={s.key}>
            {s.label || SOURCE_LABELS[s.key] || s.key}{" "}
            <span className="font-medium tabular-nums text-text-primary">{count(s.customers)}</span>
          </span>
        </React.Fragment>
      ))}
    </p>
  );
}

/** Download the service's Excel workbook for a view. */
export function ExcelLink({ params, label = "Export to Excel", testId }: {
  params: ExcelParams; label?: string; testId: string;
}) {
  return (
    <a href={excelHref(params)} download data-testid={testId} title="Download this view as an Excel workbook"
       className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
      <FileSpreadsheet className="size-3.5" aria-hidden /> {label}
    </a>
  );
}

/** The top warning reasons, with what each did on the period. Clicking opens the list. */
export function TopReasons({ reasons, onOpen, owners, period, testId }: {
  reasons: Reason[]; onOpen?: (reasonLabel: string) => void; owners: string; period: string; testId?: string;
}) {
  if (!reasons.length) return <p className="text-xs text-text-muted">No warning rule fired here.</p>;
  return (
    <div className="space-y-1" data-testid={testId}>
      {reasons.map((reason) => {
        const body = (
          <>
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="shrink-0 rounded border border-border px-1 font-mono text-[10px] text-text-muted">
                {reason.key}
              </span>
              <span className="truncate text-text-primary">{reason.name}</span>
              {reason.layer_name ? (
                <span className="hidden shrink-0 text-[10px] text-text-muted sm:inline">· {reason.layer_name}</span>
              ) : null}
            </span>
            <span className="flex shrink-0 items-center gap-2 tabular-nums">
              <span className="text-text-primary">{count(reason.customers)}</span>
              <span className="w-16 text-right text-text-muted">{sar(reason.exposure)}</span>
              <span className={cn("w-12 text-right",
                                  (reason.change ?? 0) > 0 ? "text-negative"
                                    : (reason.change ?? 0) < 0 ? "text-positive" : "text-text-muted")}>
                {signed(reason.change)}
              </span>
            </span>
          </>
        );
        const className = "flex w-full items-center justify-between gap-3 rounded px-1.5 py-1 text-[11px]";
        return onOpen ? (
          <button key={reason.key} type="button" onClick={() => onOpen(reason.reason)}
                  data-testid={`ews-reason-${reason.key}`}
                  className={cn(className, "transition-colors hover:bg-surface-muted")}>
            {body}
          </button>
        ) : (
          <div key={reason.key} className={className} data-testid={`ews-reason-${reason.key}`}>{body}</div>
        );
      })}
      <p className="px-1.5 pt-0.5 text-[10px] text-text-muted">
        {owners.charAt(0).toUpperCase() + owners.slice(1)} · exposure · change on last {period}.
      </p>
    </div>
  );
}

export function Commentary({ text, testId }: { text: string; testId?: string }) {
  return (
    <p className="rounded-md border border-border bg-surface-muted/40 p-2.5 text-[12px] leading-relaxed text-text-secondary"
       data-testid={testId}>{text}</p>
  );
}

export function ActiveFilters({ chips, testId }: {
  chips: { label: string; onClear?: () => void }[]; testId?: string;
}) {
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid={testId ?? "ews-active-filters"}>
      <span className="text-[10px] uppercase tracking-[0.08em] text-text-muted">Showing</span>
      {chips.map((chip) => chip.onClear ? (
        <button key={chip.label} type="button" onClick={chip.onClear} data-testid="ews-chip-clear"
                className="rounded-full border border-accent bg-accent-muted px-2 py-0.5 text-[11px] text-accent">
          {chip.label} ✕
        </button>
      ) : (
        <span key={chip.label} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-text-secondary">
          {chip.label}
        </span>
      ))}
    </div>
  );
}

/** Share of the parent level, on customers, exposures and EAD. */
export function Materiality({ card, parent, labels, testId }: {
  card: LevelCard; parent: string; labels: { owners: string; exposures: string }; testId?: string;
}) {
  if (!card.materiality) return null;
  const m = card.materiality;
  return (
    <div className="rounded-md border border-border bg-surface-muted/30 p-2.5" data-testid={testId}>
      <p className="text-[9px] uppercase tracking-[0.08em] text-text-muted">Materiality · share of {parent}</p>
      <div className="mt-1 grid grid-cols-3 gap-2 text-[11px]">
        <Figure label={labels.owners} value={pct(m.customers_pct)} />
        <Figure label={labels.exposures} value={pct(m.facilities_pct)} />
        <Figure label="Exposure" value={pct(m.exposure_pct)} />
      </div>
    </div>
  );
}

/** The management reading of the portfolio, and the arithmetic behind its ranking. */
export function Interpretation({ level, onOpen, testId }: {
  level: Level; onOpen: (segment: string) => void; testId?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const reading = level.interpretation;
  if (!reading || !reading.interpretation) return null;
  return (
    <Card className="border-accent/30 bg-accent-muted/20 px-4 py-3" data-testid={testId ?? "ews-interpretation"}>
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="size-4 shrink-0 text-accent" aria-hidden />
        <p className="text-sm font-semibold text-text-primary">Interpretation</p>
        <span className="text-[11px] text-text-muted">{reading.headline}</span>
        <button type="button" onClick={() => setOpen((was) => !was)} data-testid="ews-interpretation-why"
                className="ml-auto rounded-full border border-border px-2.5 py-0.5 text-[11px] text-text-secondary transition-colors hover:bg-surface-muted">
          Why this ranking?
        </button>
      </div>
      {/* PLAN_R10 E1: three lines at most until "Why this ranking?" opens, so the cards start above the fold. */}
      <p className={cn("mt-1.5 text-[13px] leading-relaxed text-text-primary", !open && "line-clamp-3")}
         title={open ? undefined : reading.interpretation} data-testid="ews-interpretation-text">
        {reading.interpretation}
      </p>
      {open ? (
        <div className="mt-3 overflow-x-auto border-t border-border pt-3" data-testid="ews-interpretation-basis">
          <p className="text-[11px] text-text-secondary">{reading.ranking_basis} Written by fixed rules from the figures on this screen.</p>
          <table className="mt-2 w-full text-[11px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-[0.06em] text-text-muted">
                <th className="px-1 py-1 text-left font-medium">#</th>
                <th className="px-1 py-1 text-left font-medium">{level.labels.segment}</th>
                <th className="px-1 py-1 text-right font-medium">High/critical EAD</th>
                <th className="px-1 py-1 text-right font-medium">% of book</th>
                <th className="px-1 py-1 text-right font-medium">Warned</th>
                <th className="px-1 py-1 text-right font-medium">Change</th>
                <th className="px-1 py-1 text-right font-medium">Default-entry</th>
              </tr>
            </thead>
            <tbody>
              {reading.ranking.map((r) => (
                <tr key={r.key} className="border-t border-border/60">
                  <td className="px-1 py-1 tabular-nums text-text-muted">{r.rank}</td>
                  <td className="px-1 py-1">
                    <button type="button" className="text-accent hover:underline" onClick={() => onOpen(r.key)}>{r.label}</button>
                  </td>
                  <td className="px-1 py-1 text-right tabular-nums">{sar(r.exposure_severe)}</td>
                  <td className="px-1 py-1 text-right tabular-nums font-medium">{pct(r.severe_share_of_book_pct)}</td>
                  <td className="px-1 py-1 text-right tabular-nums">{pct(r.warned_pct)}</td>
                  <td className="px-1 py-1 text-right tabular-nums">{signed(r.warned_change)}</td>
                  <td className="px-1 py-1 text-right tabular-nums">{pct(r.odr_pct, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

/**
 * Freeze this population for What-If and open it there.
 *
 * Writes a cohort (the exact exposures of the customers in view, with a
 * membership hash) to the Early Warning service, then opens What-If on it.
 */
export function ExportToWhatIf({ body, label, testId, size = "sm" }: {
  body: Record<string, unknown>; label?: string; testId?: string; size?: "sm" | "default";
}) {
  const router = useRouter();
  const [busy, setBusy] = React.useState(false);
  const [problem, setProblem] = React.useState("");
  const go = React.useCallback(async () => {
    setBusy(true);
    setProblem("");
    try {
      const made = await ews.exportCohort(body);
      router.push(`/what-if?cohort=${encodeURIComponent(made.object_id)}`);
    } catch (failed) {
      setProblem(failed instanceof Error ? failed.message : String(failed));
      setBusy(false);
    }
  }, [router, body]);
  return (
    <span className="inline-flex flex-col items-start">
      <Button variant="outline" size={size} onClick={() => void go()} disabled={busy}
              data-testid={testId ?? "ews-export-whatif"}>
        {busy ? <Loader2 className="mr-1 size-3.5 animate-spin" aria-hidden />
              : <FlaskConical className="mr-1 size-3.5" aria-hidden />}
        {label ?? "Export to What-If"}
      </Button>
      {problem ? <span className="mt-1 text-[10px] text-negative">{problem}</span> : null}
    </span>
  );
}

/** Corporate / Retail, remembered with the Cockpit's own key so both open on the same book. */
export const BOOK_KEY = "cockpit-v4:domain";

export function rememberBook(domain: DomainId): void {
  try { sessionStorage.setItem(BOOK_KEY, domain); } catch { /* storage blocked: default next time */ }
}

export function recallBook(): DomainId | null {
  try {
    const raw = sessionStorage.getItem(BOOK_KEY);
    return raw === "corporate" || raw === "retail" ? raw : null;
  } catch {
    return null;
  }
}

export function BookToggle({ domain, onChange }: { domain: DomainId; onChange: (d: DomainId) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" data-testid="ews-book-toggle">
      {(["corporate", "retail"] as const).map((d) => (
        <button key={d} type="button" role="tab" aria-selected={domain === d} onClick={() => onChange(d)}
                data-testid={`ews-book-${d}`}
                className={cn("rounded px-3 py-1 text-[13px] font-medium transition-colors",
                              domain === d ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-muted")}>
          {d === "corporate" ? "Corporate" : "Retail"}
        </button>
      ))}
    </div>
  );
}

/** Open the frozen Cockpit on this book with a question already in the Ask box. */
export function askCockpitHref(question: string): string {
  return `/?q=${encodeURIComponent(question)}`;
}
