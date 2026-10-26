"use client";

/**
 * PLAN_R12 Session I (I7): "Portfolio RAROC at origination" renamed to the Book's **RAROC drift** view. The share of the
 * corporate book (by EAD) above hurdle at origination and now, the drift split into PD migration, LGD, funding, fees,
 * utilisation and unrealised cross-sell, and the cuts by sector, rating, vintage and product. Every figure comes from Data
 * Domains (origination, Early Warning, ECL runs, deposits) through the Book service; the old fixture is gone.
 * `RarocDriftView` is the body (used inside BookTab); `PortfolioRarocPage` / `RarocDriftPage` is the stand-alone page.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { InfoPopover } from "@/components/ui/info-popover";

import { bookApi, type Cut, type Drift, DRIFT_LABELS } from "./book/api";
import { Section, tableCls, tdCls, thCls } from "./kit";

const COMPONENTS = ["pd_migration", "lgd", "funding", "fees", "utilisation", "cross_sell"] as const;

function ShareChart({ rows, title }: { rows: Cut[]; title: string }) {
  return (
    <Plot ariaLabel={title} filename={title.toLowerCase().replace(/\s+/g, "-")} height={300}
          data={[{ type: "bar", name: "At origination", x: rows.map((r) => r.group), y: rows.map((r) => r.share_above_orig * 100), marker: { color: "#C9BC9C" },
                   hovertemplate: fmt.hoverTemplate("share_pct") },
                 { type: "bar", name: "Now", x: rows.map((r) => r.group), y: rows.map((r) => r.share_above_now * 100), marker: { color: "#1F4E79" },
                   hovertemplate: fmt.hoverTemplate("share_pct") }] as never[]}
          layout={{ barmode: "group", xaxis: { type: "category" }, margin: { l: 48, r: 10, t: 10, b: 90 }, legend: { orientation: "h", y: 1.12 }, yaxis: { title: { text: "Share of EAD above hurdle (%)" } } } as never} />
  );
}

/** The book's drift from origination to now, as a waterfall in RAROC points. */
export function DriftWaterfall({ start, steps, end, title, height = 280 }: {
  start: number; steps: { label: string; value: number }[]; end: number; title: string; height?: number;
}) {
  // two-line category labels so the steps read horizontally at 1280 px
  const x = ["At<br>origination", ...steps.map((s) => s.label.replace(" ", "<br>")), "Now"];
  const y = [start * 100, ...steps.map((s) => s.value * 100), end * 100];
  const measure = ["absolute", ...steps.map(() => "relative"), "total"];
  return (
    <Plot ariaLabel={title} filename={title.toLowerCase().replace(/\s+/g, "-")} height={height}
          data={[{ type: "waterfall", x, y, measure, text: y.map((v, i) => (i === 0 || i === y.length - 1 ? fmt.pct(v, { scale: "points" }) : fmt.pp(v, { signed: true }))),
                   textposition: "outside", connector: { line: { color: "#A8A29E" } },
                   increasing: { marker: { color: "#2F7D5B" } }, decreasing: { marker: { color: "#B4442F" } }, totals: { marker: { color: "#1F4E79" } },
                   hovertemplate: "%{x}: %{y:.2f} points<extra></extra>" }] as never[]}
          layout={{ margin: { l: 48, r: 10, t: 20, b: 60 }, yaxis: { title: { text: "One-year RAROC (%)" } }, xaxis: { type: "category", tickangle: 0, tickfont: { size: 10 }, automargin: true }, showlegend: false } as never} />
  );
}

function CutTable({ rows, testId }: { rows: Cut[]; testId: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={tableCls} data-testid={testId}>
        <thead><tr>{["", "EAD", "Facilities", "Median RAROC at origination", "Median RAROC now", "Hurdle", "Above hurdle at origination", "Above hurdle now", "Drift", "Main driver"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => {
          const main = COMPONENTS.reduce((a, c) => ((r[c] ?? 0) < (r[a] ?? 0) ? c : a), COMPONENTS[0]);
          return (
            <tr key={r.group}><td className={cn(tdCls, "font-medium")}>{r.group}</td><td className={cn(tdCls, "text-right")}>{fmt.sar(r.ead_sar_mn)}</td>
              <td className={cn(tdCls, "text-right")}>{fmt.count(r.facilities_count)}</td><td className={cn(tdCls, "text-right")}>{fmt.pct(r.raroc_orig)}</td>
              <td className={cn(tdCls, "text-right")}>{fmt.pct(r.raroc_now)}</td><td className={cn(tdCls, "text-right")}>{fmt.pct(r.hurdle)}</td>
              <td className={cn(tdCls, "text-right")}>{fmt.pct(r.share_above_orig)}</td>
              <td className={cn(tdCls, "text-right", r.share_above_now < r.share_above_orig - 0.05 && "text-negative")}><b>{fmt.pct(r.share_above_now)}</b></td>
              <td className={cn(tdCls, "text-right", r.drift < 0 && "text-negative")}>{fmt.pp((r.drift ?? 0) * 100, { signed: true })}</td>
              <td className={tdCls}>{DRIFT_LABELS[main]}</td></tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

/** The RAROC drift body: tiles, summary, attribution waterfall and cuts. */
export function RarocDriftView({ data: given }: { data?: Drift }) {
  const r = useLoad(() => (given ? Promise.resolve(given) : bookApi.drift()), given ? "raroc-drift-given" : "raroc-drift");
  const d = r.data;
  if (r.error) return <p role="alert" className="text-[12px] text-negative">{r.error}</p>;
  if (!d) return <Skeleton className="h-96 w-full" />;
  const steps = d.attribution.map((a) => ({ label: a.label, value: a.value }));
  return (
    <div className="space-y-4" data-testid="raroc-drift">
      <KpiRow testId="portfolio-raroc-tiles" tiles={[
        { label: "Above hurdle at origination", value: fmt.pct(d.share_above_hurdle_orig), sub: <>of <b>{fmt.sar(d.ead_sar_mn)}</b> EAD</>, testId: "portfolio-raroc-share",
          info: "Share of the performing corporate book's EAD whose one-year RAROC at origination cleared its hurdle." },
        { label: "Above hurdle now", value: fmt.pct(d.share_above_hurdle_now), tone: d.share_above_hurdle_now < d.share_above_hurdle_orig ? "negative" : "positive",
          info: "The same facilities at today's rating, PD, LGD, utilisation, funding, fees and delivered cross-sell." },
        { label: "RAROC drift since origination", value: fmt.pp(d.drift * 100, { signed: true }), tone: d.drift < 0 ? "negative" : "positive",
          info: "EAD-weighted change in one-year RAROC, origination to now: the sum of the six drivers below." },
        { label: "Cleared then, not now", value: fmt.count(d.decayed_count), sub: <>{fmt.sar(d.decayed_ead_sar_mn)} EAD</>, tone: "negative" },
      ]} />
      <Section title="Summary" testId="portfolio-raroc-summary" info={<>Written from the figures on this page. Book as of {d.as_of}; {fmt.count(d.defaulted_count)} defaulted facilities ({fmt.sar(d.defaulted_ead_sar_mn)} EAD) are in workout and left out.</>}>
        <p className="text-[13px] leading-6 text-text-primary">{d.summary}</p>
      </Section>
      <Section title="Why the book drifted" testId="raroc-drift-attribution"
               info={<>Each facility&apos;s one-year RAROC is moved from origination to now one driver at a time, in this order: PD migration (PD and risk weight), LGD, funding (the FTP change the base reset did not pass on), fees (upfront fee fully earned, no renewal fee), utilisation (drawn share and limit), unrealised cross-sell (promised routing income not delivered). The steps add up to the drift. EAD-weighted over the performing book. {d.method}</>}>
        <DriftWaterfall title="RAROC drift attribution" start={d.mean_raroc_orig} steps={steps} end={d.mean_raroc_now} />
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Share above hurdle by sector" info="Share of each sector's EAD whose RAROC cleared the hurdle at origination and clears it now."><ShareChart rows={d.by_sector} title="By sector" /></Section>
        <Section title="Share above hurdle by vintage" info="By origination year: older vintages show how pricing has held up as ratings migrated."><ShareChart rows={d.by_vintage} title="By vintage" /></Section>
      </div>
      <Section title="By sector" info="Each sector against its own hurdle, with the driver that took most."><CutTable rows={d.by_sector} testId="portfolio-raroc-sector" /></Section>
      <Section title="By rating at origination" info="Ratings in the global order AAA … C."><CutTable rows={d.by_rating} testId="portfolio-raroc-rating" /></Section>
      <Section title="By product" info="Short-tenor products lose their upfront fee at rollover when no renewal fee is taken."><CutTable rows={d.by_product} testId="raroc-drift-product" /></Section>
      <p className="text-[11px] text-text-muted" data-testid="raroc-drift-sources">
        Sources: {d.sources.map((s) => `${s.domain}.${s.relation}`).filter((v, i, a) => a.indexOf(v) === i).join(", ")}.
      </p>
    </div>
  );
}

export function RarocDriftPage() {
  return (
    <div className="space-y-4" data-testid="portfolio-raroc">
      <BackButton fallback={{ href: "/deal-desk", label: "Deal Desk" }} testId="portfolio-raroc-back" />
      <div className="flex items-center gap-2">
        <div><p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deal Desk · Book</p>
          <h1 className="text-2xl font-semibold text-text-primary">RAROC drift</h1></div>
        <InfoPopover title="RAROC drift">Every live corporate facility&apos;s one-year RAROC at origination against now, and why it moved. Hurdles from Admin → Deal Desk Parameters.</InfoPopover>
      </div>
      <PoweredBy pack="P7" rule="P7-PRO-01" confidence="medium" trace={{ href: "/deal-desk/parameters" }} testId="portfolio-raroc-powered-by" />
      <RarocDriftView />
    </div>
  );
}

/** The old name, kept so existing imports keep working. */
export const PortfolioRarocPage = RarocDriftPage;
