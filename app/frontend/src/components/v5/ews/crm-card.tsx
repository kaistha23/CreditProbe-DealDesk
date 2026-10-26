"use client";

/**
 * R7 (PLAN_R7 C3.3): the CBUAE CRM compliance card on the Early Warning home.
 *
 * The deterministic breach checks of the CBUAE Credit Risk Management Standards
 * on this book at its latest period (Early Warning service, GET /api/v1/ews/crm):
 * breaches by article with their EAD, ECL and provision shortfall, the largest
 * breaches, a link to the Standards in Policy Docs and the question for the
 * Cockpit. Shown at the portfolio level only.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Scale } from "lucide-react";

import { hbarFigure } from "@/components/answer/bar-figure";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Plot } from "@/components/v5/ews/plot";
import { type Crm, type DomainId, count, ews, sar, useEws } from "@/lib/v5/ews";
import { cn } from "@/lib/utils";

import { askCockpitHref } from "./parts";

const TONE: Record<string, string> = { high: "text-negative", medium: "text-warning", low: "text-text-muted" };

export function CrmComplianceCard({ domain }: { domain: DomainId }) {
  const router = useRouter();
  const { data, error, loading } = useEws<Crm>(() => ews.crm(domain), `crm|${domain}`);
  if (error) return <p className="text-sm text-negative" data-testid="ews-crm-error">{error}</p>;
  if (loading || !data) return <Skeleton className="h-40 w-full" />;
  const articleHref = (article: string) => `${data.href}&clause=${encodeURIComponent(article)}`;
  const articleText = (a: Crm["by_article"][number]) =>
    a.note ? a.note : a.breaches ? `${count(a.breaches)} · ${sar(a.ead_sar_mn)}` : "Compliant";
  // An article with a note (not testable) draws no bar, as before.
  const fig = hbarFigure({
    labels: data.by_article.map((a) => a.article),
    values: data.by_article.map((a) => (a.note ? 0 : a.breaches)),
    text: data.by_article.map(articleText),
    color: "var(--ipm-negative)",
    customdata: data.by_article.map((a) => articleHref(a.article)),
  });
  return (
    <Card className="space-y-3 p-4" data-testid="ews-crm-card">
      <div className="flex flex-wrap items-center gap-2">
        <Scale className="size-4 text-accent" aria-hidden />
        <p className="text-sm font-semibold text-text-primary">CBUAE CRM compliance</p>
        <p className="text-[11px] text-text-muted">{data.document} · {data.period}</p>
        <InfoPopover title="CBUAE CRM compliance">
          <p>Deterministic checks of this book against the CBUAE Credit Risk Management Standards: each breach names its
            article, the {domain === "corporate" ? "facility" : "account"}, the value measured and the value required,
            with its EAD and ECL.</p>
          <p className="mt-2">Not testable on these books: {data.not_checked.map((n) => `${n.article} (${n.why})`).join("; ")}.</p>
        </InfoPopover>
        <div className="ml-auto flex gap-2 text-xs">
          <Link href={data.href} className="text-accent hover:underline" data-testid="ews-crm-standards">Open the Standards</Link>
          <Link href={askCockpitHref(data.ask)} className="text-accent hover:underline" data-testid="ews-crm-ask">Ask the Cockpit</Link>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="ews-crm-kpis">
        <Stat label="Breaches" value={count(data.breaches)} sub={`${data.checks_in_breach} of ${data.checks} checks`} tone="negative" />
        <Stat label="High severity" value={count(data.high)} tone="warning" />
        <Stat label="EAD in breach" value={sar(data.ead_sar_mn)} sub={`ECL ${sar(data.ecl_sar_mn)}`} />
        <Stat label="Provision shortfall" value={sar(data.shortfall_sar_mn)} sub="against the Stage 3 floors" />
      </div>
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Breaches by article</p>
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Plot data={fig.data} layout={fig.layout} height={fig.height} testId="ews-crm-articles-chart" filename="crm-breaches-by-article"
                ariaLabel="Breaches by article of the CBUAE CRM Standards"
                onPointClick={(href) => { if (typeof href === "string") router.push(href); }} />
          <ul className="space-y-1" data-testid="ews-crm-articles">
            {data.by_article.map((a) => (
              <li key={a.article} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 text-[12px]"
                  data-testid="ews-crm-article">
                <Link href={articleHref(a.article)} className="truncate hover:underline"
                      title={`${a.article} ${a.title}`}>
                  <span className="font-semibold">{a.article}</span> <span className="text-text-secondary">{a.title}</span>
                </Link>
                <span className={cn("tabular-nums", a.breaches ? "text-text-secondary" : "text-positive")}>
                  {articleText(a)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {data.top.length ? (
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Largest breaches</p>
          <table className="w-full text-[12px]" data-testid="ews-crm-top">
            <thead className="text-left text-[10px] uppercase tracking-[0.06em] text-text-muted">
              <tr><th className="py-1">Article</th><th>{domain === "corporate" ? "Facility" : "Account"}</th>
                <th>Measured</th><th>Required</th><th className="text-right">EAD</th><th className="text-right">ECL</th></tr>
            </thead>
            <tbody>
              {data.top.map((b) => (
                <tr key={`${b.check_id}-${b.entity_id}-${b.detail}`} className="border-t border-border/60">
                  <td className="py-1"><span className="font-semibold">{b.article}</span>{" "}
                    <span className={cn("text-[10px] uppercase", TONE[b.severity])}>{b.severity}</span></td>
                  <td className="font-mono">{b.entity_id}</td>
                  <td>{fmt(b.measured, b.unit)}</td>
                  <td>{fmt(b.required, b.unit)}</td>
                  <td className="text-right tabular-nums">{sar(b.ead_sar_mn)}</td>
                  <td className="text-right tabular-nums">{sar(b.ecl_sar_mn)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

function fmt(v: number | string, unit: string): string {
  if (unit === "SAR million" && typeof v === "number") return sar(v);
  if (unit === "stage" && typeof v === "number") return `Stage ${v}`;
  if (unit === "stage") return `Stage ${v}`;
  return `${v} ${unit === "SAR million" ? "" : unit}`.trim();
}

function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: string; tone?: "negative" | "warning" }) {
  return (
    <div className="rounded-md border border-border p-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{label}</p>
      <p className={cn("mt-0.5 text-lg font-semibold tabular-nums", tone === "negative" && "text-negative",
                       tone === "warning" && "text-warning")}>{value}</p>
      {sub ? <p className="text-[11px] text-text-muted">{sub}</p> : null}
    </div>
  );
}
