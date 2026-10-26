"use client";

/**
 * One customer (retail) or borrower (corporate): why the warning fired.
 *
 * Structure ported from the Retail Demo's customer detail (c0db151f,
 * app/early-warning/customer-detail.tsx): headline figures, the drivers, every
 * exposure with every rule evaluated against the values it read, and the full
 * history. Every rule shown is the same rule, with the same condition, that
 * the model page lists -- one definition, everywhere.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowLeft, ExternalLink, MessageSquareText, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ShareCurrent } from "@/components/v5/mail/share";
import { PanelActions } from "@/components/v5/thread/panel-actions";
import { b360Sources, ewsSources } from "@/lib/v5/thread-actions";
import { type CustomerDetail as Detail, type DomainId, count, ews, pct, sar, shortPeriod, useEws } from "@/lib/v5/ews";

import { CHART_HINT, CustomerHistoryPlot } from "./charts";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { customerHistoryExplain } from "./explain";
import { Band, ExcelLink, ExportToWhatIf, Figure, askCockpitHref, rememberBook } from "./parts";
import { TileRow } from "./tile-row";
import { MonitoringTierPanel } from "./monitoring-tier-panel";
import { MonitoringLine } from "@/components/v5/dealdesk/flow-monitoring"; // R14 F (K35)

const FACT_LABELS: Record<string, string> = {
  group_id: "Group", group_name: "Group name", rating_current: "Rating", rating_previous: "Previous rating",
  rating_outlook: "Outlook", watchlist_flag: "On watchlist", watchlist_reason: "Watchlist reason",
  relationship_tier: "Relationship tier", region: "Region", customer_segment: "Segment",
  employment_type: "Employment", tenure_months: "Tenure (months)", behaviour_score: "Behaviour score",
  behaviour_score_previous: "Previous behaviour score", score_band: "Score band",
  score_migration: "Score migration", accounts_held: "Accounts held",
};

function factValue(key: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (key === "watchlist_flag") return Number(v) ? "Yes" : "No";
  if (typeof v === "number") return String(Math.round(v * 100) / 100);
  const s = String(v);
  return /^[A-Z_]+$/.test(s) ? s.charAt(0) + s.slice(1).toLowerCase() : s;
}

export function CustomerDetail({ domain, id, period, onBack }: {
  domain: DomainId; id: string; period: string; onBack: () => void;
}) {
  const { data, error, loading } = useEws<Detail>(() => ews.customer(domain, id, period), `${domain}|${id}|${period}`);
  if (error) {
    return (
      <div className="space-y-3">
        <Button variant="outline" size="sm" onClick={onBack} data-testid="ews-detail-back"><ArrowLeft className="mr-1 size-3.5" aria-hidden /> Back</Button>
        <p className="text-sm text-negative" data-testid="ews-customer-error">{error}</p>
      </div>
    );
  }
  if (loading || !data) return <Skeleton className="h-64 w-full" />;
  const d = data;
  const worstDpd = Math.max(0, ...d.exposures.map((e) => e.dpd || 0));
  const corporate = domain === "corporate";
  const name = d.customer_name ?? d.customer_id;
  const question = corporate
    ? `Why is ${name} (${d.customer_id}) deteriorating, and what is our exposure to its group?`
    : `What is driving the arrears and stage of customer ${d.customer_id}?`;

  return (
    <div className="space-y-4" data-testid="ews-customer-detail">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" size="sm" onClick={onBack} data-testid="ews-detail-back">
          <ArrowLeft className="mr-1 size-3.5" aria-hidden /> Back
        </Button>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-text-primary">{name}</h2>
            {d.customer_name ? <span className="font-mono text-[12px] text-text-muted">{d.customer_id}</span> : null}
            <Band band={d.band} />
            {d.current_bad ? <span className="rounded bg-negative-muted px-1.5 py-0.5 text-[10px] text-negative">Already bad</span> : null}
            {d.forward_risk ? <span className="rounded bg-warning-muted px-1.5 py-0.5 text-[10px] text-warning">Forward risk</span> : null}
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Link href={d.links.borrower_360} data-testid="ews-link-b360"
                className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
            <UserRound className="size-3.5" aria-hidden /> Open in Borrower 360
          </Link>
          <ExcelLink testId="ews-excel-customer" params={{ domain, period: d.period, customer_id: d.customer_id }} />
          <ShareCurrent type="borrower" testId="ews-share-customer" id={d.customer_id}
                        label={`${d.customer_id}${d.customer_name ? ` ${d.customer_name}` : ""} (Early Warning, ${d.period})`}
                        summary={`Early Warning ${d.band} (score ${d.score}); exposure ${sar(d.exposure)}, ECL ${sar(d.ecl)}.`}
                        meta={{ domain, period: d.period }} />
          {/* R16 t (M7): Trace, Word and Add to report on this customer's Early Warning answer */}
          <PanelActions module="ews" id={d.customer_id} title={`${name} · Early Warning, ${d.period}`} container='[data-testid="ews-customer-detail"]'
                        share={false} testId="ews-customer-actions" sources={[...ewsSources({ domain, customer: d.customer_id }), ...(corporate ? b360Sources(d.customer_id) : [])]} />
          <ExportToWhatIf testId="ews-export-customer" label="Export to What-If"
                          body={{ domain, period: d.period, customer_id: d.customer_id }} />
          <Link href={askCockpitHref(question)} onClick={() => rememberBook(domain)} data-testid="ews-link-cockpit"
                className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
            <MessageSquareText className="size-3.5" aria-hidden /> Ask the Cockpit
          </Link>
        </div>
      </div>

      {/* PLAN_R10 G-TILES: 4 small tiles in one row. */}
      <TileRow testId="ews-customer-kpis" tiles={[
        { label: "Score", value: d.score, sub: `band ${d.band} · ${count(d.reasons.length)} rules fired`,
          tone: d.band === "high" || d.band === "critical" ? "warning" : undefined },
        { label: "Exposure", value: sar(d.exposure), sub: `${count(d.facilities)} ${d.labels.exposures}` },
        { label: "ECL", value: sar(d.ecl), sub: `${pct(d.exposure ? (100 * d.ecl) / d.exposure : null, 2)} coverage` },
        { label: "Worst DPD", value: count(worstDpd), tone: worstDpd >= 30 ? "negative" : undefined,
          sub: `worst stage ${Math.max(...d.exposures.map((e) => e.stage || 0))}` },
      ]} />

      {corporate ? <MonitoringTierPanel customerId={d.customer_id} period={d.period} /> /* R12 D: Deal Desk monitoring tier */ : null}
      {corporate ? <MonitoringLine obligorId={d.customer_id} /> /* R14 F (K35): proposed for or under Deal Desk monitoring */ : null}
      <Card className="p-4" data-testid="ews-customer-facts">
        <p className="text-sm font-semibold text-text-primary">{corporate ? "Borrower" : "Customer"}</p>
        <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
          {Object.entries(d.facts).map(([k, v]) => (
            <Figure key={k} label={FACT_LABELS[k] ?? k.replace(/_/g, " ")} value={factValue(k, v)} />
          ))}
        </div>
      </Card>

      <Card className="p-4" data-testid="ews-customer-trends">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-sm font-semibold text-text-primary">How it moved</p>
          <ChartInfo title="How it moved" explain={customerHistoryExplain(d.history, d.warned_min, d.labels.owner)} hint={CHART_HINT} />
        </div>
        {d.history.length ? (
          <CustomerHistoryPlot history={d.history} warnedMin={d.warned_min} testId="ews-customer-history-chart" />
        ) : <p className="mt-2 text-[11px] italic text-text-muted">No history published for this {d.labels.owner}.</p>}
      </Card>

      <div className="space-y-3" data-testid="ews-customer-exposures">
        <p className="text-sm font-semibold text-text-primary">
          {d.labels.exposures.charAt(0).toUpperCase() + d.labels.exposures.slice(1)} and the rules evaluated on each
        </p>
        {d.exposures.map((e) => (
          <Card key={e.exposure_id} className="p-3.5" data-testid={`ews-exposure-${e.exposure_id}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[12px] font-semibold text-text-primary">{e.exposure_id}</span>
              <Band band={e.band} />
              <span className="text-[11px] text-text-secondary">score {e.score} · {e.subsegment}{e.product_type ? ` · ${e.product_type.replace(/_/g, " ")}` : ""}</span>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-6">
              <Figure label="Exposure (EAD)" value={sar(e.exposure)} />
              <Figure label="Limit" value={sar(e.limit)} />
              <Figure label="Utilisation" value={pct(e.utilisation_pct)} />
              <Figure label="ECL" value={sar(e.ecl)} />
              <Figure label="DPD" value={count(e.dpd)} tone={e.dpd >= 30 ? "negative" : undefined} />
              <Figure label="Stage" value={e.stage} />
            </div>
            <table className="mt-2 w-full text-[11px]">
              <thead>
                <tr className="text-[9px] uppercase tracking-[0.06em] text-text-muted">
                  <th className="py-1 text-left font-medium">Rule</th>
                  <th className="py-1 text-left font-medium">Layer</th>
                  <th className="py-1 text-left font-medium">Condition</th>
                  <th className="py-1 text-left font-medium">Value read</th>
                  <th className="py-1 text-right font-medium">Weight</th>
                </tr>
              </thead>
              <tbody>
                {e.rules.map((r) => (
                  <tr key={r.id} className={cn("border-t border-border/60", r.fired ? "text-text-primary" : "text-text-muted")}
                      data-testid={`ews-rule-${e.exposure_id}-${r.id}`} title={r.limitation || undefined}>
                    <td className="py-1"><span className="font-mono">{r.id}</span> {r.name}</td>
                    <td className="py-1">{r.layer_name}</td>
                    <td className="py-1 font-mono text-[10px]">{r.condition}</td>
                    <td className="py-1 font-mono text-[10px]">
                      {r.available ? Object.entries(r.values).map(([k, v]) => `${k}=${v === null ? "∅" : typeof v === "number" ? Math.round(v * 100) / 100 : v}`).join(", ") : "not published in this book"}
                    </td>
                    <td className="py-1 text-right tabular-nums">{r.fired ? `+${r.weight}` : "0"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ))}
      </div>

      <Card className="overflow-x-auto p-4" data-testid="ews-customer-history">
        <p className="text-sm font-semibold text-text-primary">History, every {d.labels.period}</p>
        <table className="mt-2 w-full text-[11px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-[0.06em] text-text-muted">
              <th className="py-1 text-left font-medium">Period</th>
              <th className="py-1 text-left font-medium">Band</th>
              <th className="py-1 text-right font-medium">Score</th>
              <th className="py-1 text-right font-medium">DPD</th>
              <th className="py-1 text-right font-medium">Stage</th>
              <th className="py-1 text-right font-medium">Exposure</th>
              <th className="py-1 text-left font-medium">Rules fired</th>
            </tr>
          </thead>
          <tbody>
            {[...d.history].reverse().map((h) => (
              <tr key={h.period} className="border-t border-border/60">
                <td className="py-1">{shortPeriod(h.period)}</td>
                <td className="py-1"><Band band={h.band} /></td>
                <td className="py-1 text-right tabular-nums">{h.score}</td>
                <td className="py-1 text-right tabular-nums">{h.dpd}</td>
                <td className="py-1 text-right tabular-nums">{h.stage}</td>
                <td className="py-1 text-right tabular-nums">{sar(h.exposure)}</td>
                <td className="py-1 text-text-secondary">{h.reasons.join("; ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <p className="text-[10px] text-text-muted">
        <ExternalLink className="mr-1 inline size-3" aria-hidden />
        {d.definitions.customer_score} {d.definitions.current_bad}
      </p>
    </div>
  );
}
