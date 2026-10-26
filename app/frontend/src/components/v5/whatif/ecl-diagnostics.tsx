"use client";

/**
 * PLAN_R9 C3 (P6 ECL Diagnostics Intelligence), in What-If: what moved ECL between the two runs (each bar's top
 * clients), the input anomaly check with its rerun verdict, CBUAE coverage (Art 9.21 and the Stage 3 floors), PD /
 * LGD / macro shocks, and the ECL of current warnings (the same numbers as Early Warning, P3).
 */

import Link from "next/link";
import * as React from "react";
import { CheckCircle2, AlertTriangle } from "lucide-react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { Plot } from "@/components/v5/ews/plot";
import { type DomainId, count, sar, useEws } from "@/lib/v5/ews";
import { type Anomalies, type Coverage, type Impact, type Shocks, type Waterfall, intel } from "@/lib/v5/risk-intel";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "movement", label: "ECL movement" }, { key: "inputs", label: "Input check" },
  { key: "coverage", label: "CBUAE coverage" }, { key: "shocks", label: "Shocks" }, { key: "warnings", label: "ECL of warnings" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export function EclDiagnostics({ domain }: { domain: DomainId }) {
  const [tab, setTab] = React.useState<Tab>("movement");
  return (
    <Card className="space-y-3 p-4" data-testid="whatif-ecl-diagnostics">
      <div className="flex flex-wrap items-center gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">P6 Intelligence</p>
          <h2 className="text-[14px] font-semibold text-text-primary">ECL diagnostics</h2>
        </div>
        <InfoPopover title="ECL diagnostics">
          The prior ECL run (2026Q2) against the current run (2026Q3, equal to the books): what moved ECL, whether the
          inputs are fit for sign-off, and coverage against the CBUAE floors.
        </InfoPopover>
        <div className="ml-auto inline-flex rounded-md border border-border p-0.5 text-[12px]" role="tablist">
          {TABS.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                    data-testid={`whatif-diag-tab-${t.key}`}
                    className={cn("rounded px-2 py-0.5", tab === t.key ? "bg-accent text-accent-contrast" : "")}>{t.label}</button>
          ))}
        </div>
      </div>
      {tab === "movement" ? <Movement book={domain} /> : tab === "inputs" ? <Inputs book={domain} />
        : tab === "coverage" ? <CoverageView book={domain} /> : tab === "shocks" ? <ShocksView book={domain} /> : <Warnings domain={domain} />}
    </Card>
  );
}

function Loading({ error }: { error: string | null }) {
  return error ? <p className="text-sm text-negative">{error}</p> : <Skeleton className="h-64 w-full" />;
}

function Movement({ book }: { book: string }) {
  const { data, error } = useEws<Waterfall>(() => intel.waterfall(book), `wf|${book}`);
  const [pick, setPick] = React.useState<string>("stage_transfers");
  if (!data) return <Loading error={error} />;
  const bar = data.bars.find((b) => b.key === pick) ?? data.bars[0];
  const x = ["Opening " + data.prior_run, ...data.bars.map((b) => b.label), "Closing " + data.current_run];
  const y = [data.opening, ...data.bars.map((b) => b.value), data.closing];
  return (
    <div className="space-y-3" data-testid="whatif-diag-movement">
      <p className="text-[13px] text-text-secondary">
        ECL moved from <strong>{sar(data.opening)}</strong> to <strong>{sar(data.closing)}</strong> ({data.change >= 0 ? "+" : ""}{sar(data.change)}).
        The largest driver is <strong>{[...data.bars].sort((a, b) => Math.abs(b.value) - Math.abs(a.value))[0].label.toLowerCase()}</strong>.
      </p>
      <div className="flex items-center gap-2">
        <p className="text-sm font-semibold text-text-primary">ECL movement {data.prior_run} → {data.current_run}</p>
        <InfoPopover title="ECL movement">{data.method} Click a bar to see its top clients.</InfoPopover>
      </div>
      <Plot testId="whatif-diag-waterfall" ariaLabel="ECL movement waterfall" height={320} filename="ecl-movement-waterfall"
            onPointClick={(cd) => { if (typeof cd === "string" && cd) setPick(cd); }}
            data={[{
              type: "waterfall", x, y, measure: ["absolute", ...data.bars.map(() => "relative"), "total"],
              customdata: ["", ...data.bars.map((b) => b.key), ""],
              text: y.map((v) => `${v >= 0 ? "" : "−"}${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 1 })}`), textposition: "outside",
              increasing: { marker: { color: "var(--ipm-negative)" } }, decreasing: { marker: { color: "var(--ipm-positive)" } },
              totals: { marker: { color: "var(--ipm-chart-1)" } }, connector: { line: { color: "var(--ipm-border)" } },
              hovertemplate: "%{x}<br>SAR %{y:,.1f}m<extra></extra>",
            }]}
            layout={{ yaxis: { title: { text: "SAR million" }, tickformat: ",.0f" }, xaxis: { automargin: true }, margin: { l: 60, r: 10, t: 20, b: 80 }, showlegend: false }} />
      <div className="flex flex-wrap gap-1.5">
        {data.bars.map((b) => (
          <button key={b.key} type="button" onClick={() => setPick(b.key)} data-testid={`whatif-diag-bar-${b.key}`}
                  className={cn("rounded-full border px-2.5 py-0.5 text-[12px]", pick === b.key ? "border-accent text-accent" : "border-border text-text-secondary")}>
            {b.label}: <strong>{sar(b.value)}</strong></button>
        ))}
      </div>
      <div data-testid="whatif-diag-top-clients">
        <p className="text-[12px] font-semibold text-text-primary">{bar.label}: top clients <span className="font-normal text-text-muted">({count(bar.exposures)} exposures) · {bar.info}</span></p>
        {bar.top_clients.length ? (
          <table className="mt-1 w-full text-[12px]"><tbody>
            {bar.top_clients.map((c) => (
              <tr key={c.obligor_id} className="border-t border-border">
                <td className="py-1">{book === "corporate" ? <Link className="text-accent hover:underline" href={`/early-warning?domain=corporate&customer=${encodeURIComponent(c.obligor_id)}`}>{c.name}</Link> : c.name} <span className="text-text-muted">{c.obligor_id}</span></td>
                <td className="text-right font-semibold tabular-nums">{c.value >= 0 ? "+" : ""}{sar(c.value)}</td>
              </tr>))}
          </tbody></table>
        ) : <p className="text-[12px] text-text-muted">No exposure moved through this step between the two runs.</p>}
      </div>
      <p className="text-[11px] text-text-muted">Source: {data.source}.</p>
      <PoweredBy pack="P6" rule="P6-MOV-01" article={data.powered_by.article} confidence="high" trace={{ href: "/data-builder?domain=cockpit" }} testId="whatif-diag-powered-movement" />
    </div>
  );
}

function Inputs({ book }: { book: string }) {
  const { data, error } = useEws<Anomalies>(() => intel.anomalies(book), `an|${book}`);
  const [check, setCheck] = React.useState("");
  if (!data) return <Loading error={error} />;
  const rerun = data.verdict === "Rerun recommended";
  const rows = check ? data.rows.filter((r) => r.check === check) : data.rows;
  return (
    <div className="space-y-3" data-testid="whatif-diag-inputs">
      <div className={cn("flex items-start gap-2 rounded-md border p-3", rerun ? "border-negative bg-negative-muted" : "border-positive bg-positive-muted")} data-testid="whatif-diag-verdict">
        {rerun ? <AlertTriangle className="mt-0.5 size-4 text-negative" aria-hidden /> : <CheckCircle2 className="mt-0.5 size-4 text-positive" aria-hidden />}
        <div><p className="text-[14px] font-bold text-text-primary">{data.verdict}</p><p className="text-[12px] text-text-secondary">{data.why}</p></div>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {data.checks.map((c) => (
          <button key={c.key} type="button" onClick={() => setCheck(check === c.key ? "" : c.key)} data-testid={`whatif-diag-check-${c.key}`}
                  className={cn("rounded-md border p-2 text-left", check === c.key ? "border-accent" : "border-border", c.count && c.input_error ? "bg-warning-muted/40" : "")}>
            <p className="text-[12px] font-medium text-text-primary">{c.label}</p>
            <p className="text-lg font-bold tabular-nums">{count(c.count)}</p>
            <p className="text-[11px] text-text-muted">{c.input_error ? "input error" : "data-quality exception"} · ECL {sar(c.ecl_at_stake)}</p>
          </button>
        ))}
      </div>
      {rows.length ? (
        <table className="w-full text-[12px]" data-testid="whatif-diag-anomaly-rows">
          <thead><tr className="text-left text-text-muted"><th className="py-1">Check</th><th>Exposure</th><th>Borrower</th><th className="text-right">Stage</th>
            <th className="text-right">EAD</th><th>Field</th><th className="text-right">Prior / expected</th><th className="text-right">Current</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={`${r.check}-${r.exposure_id}`} className="border-t border-border">
              <td className="py-1">{r.label}</td><td className="tabular-nums">{r.exposure_id}</td><td>{r.name}</td>
              <td className="text-right">{r.stage}</td><td className="text-right tabular-nums">{sar(r.ead)}</td><td className="text-text-muted">{r.field}</td>
              <td className="text-right tabular-nums">{r.prior === null ? "—" : r.prior.toLocaleString("en-US", { maximumFractionDigits: 2 })}</td>
              <td className="text-right font-semibold tabular-nums">{r.current === null ? (r.check === "missing_collateral" ? "missing" : "—") : r.current.toLocaleString("en-US", { maximumFractionDigits: 2 })}</td>
            </tr>))}</tbody>
        </table>
      ) : <p className="text-[12px] text-text-muted">No exposure fails this check.</p>}
      <p className="flex items-center gap-1 text-[11px] text-text-muted">{count(data.input_errors)} input errors, {count(data.data_quality)} data-quality exceptions<InfoPopover title="Checks">Source: {data.source}. The run listed {count(data.planted_listed)} anomalies; {count(data.planted_found)} were found by these checks.</InfoPopover></p>
      <PoweredBy pack="P6" rule="P6-ERR-02" article={data.powered_by.article} confidence="high" trace={{ href: "/data-builder?domain=cockpit" }} testId="whatif-diag-powered-inputs" />
    </div>
  );
}

function CoverageView({ book }: { book: string }) {
  const { data, error } = useEws<Coverage>(() => intel.coverage(book), `cv|${book}`);
  if (!data) return <Loading error={error} />;
  const s3 = data.stage3;
  return (
    <div className="space-y-3" data-testid="whatif-diag-coverage">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Stage 1 + 2 ECL" value={sar(data.stage12_ecl)} sub={`${data.coverage_pct_of_crwa?.toFixed(2) ?? "—"}% of credit RWA`} />
        <Stat label="Required: 1.50% of credit RWA (Art 9.21)" value={sar(data.required_9_21)} sub={`credit RWA ${sar(data.crwa)}`} />
        <Stat label="Art 9.21 shortfall" value={data.meets_9_21 ? "None" : sar(data.shortfall_9_21)} tone={data.meets_9_21 ? undefined : "negative"} sub={data.meets_9_21 ? "meets the floor" : "below the floor"} />
        <Stat label={`Stage 3 below the minimum floors (${s3.article?.replace("CBUAE CRM ", "") ?? "Art 9.23"})`} value={sar(s3.shortfall)} tone={s3.shortfall > 0 ? "negative" : undefined}
              sub={`${count(s3.breaches)} facilities · Stage 3 ECL ${sar(s3.stage3_ecl)}`} />
      </div>
      <p className="text-[13px] text-text-secondary" data-testid="whatif-diag-total-shortfall">Total provisioning shortfall against the CBUAE floors: <strong>{sar(data.total_shortfall)}</strong>.</p>
      {s3.top.length ? (
        <table className="w-full text-[12px]" data-testid="whatif-diag-floor-rows">
          <thead><tr className="text-left text-text-muted"><th className="py-1">Facility</th><th>Borrower</th><th className="text-right">ECL</th><th className="text-right">Floor</th><th className="text-right">Shortfall</th></tr></thead>
          <tbody>{s3.top.map((r) => (
            <tr key={r.entity_id} className="border-t border-border"><td className="py-1 tabular-nums">{r.entity_id}</td><td>{r.borrower_id}</td>
              <td className="text-right tabular-nums">{sar(r.ecl)}</td><td className="text-right tabular-nums">{sar(r.floor)}</td>
              <td className="text-right font-semibold tabular-nums">{sar(r.shortfall)}</td></tr>))}</tbody>
        </table>) : null}
      <p className="text-[11px] text-text-muted">Credit RWA: {data.crwa_source}.{s3.error ? ` ${s3.error}` : ""}</p>
      <PoweredBy pack="P6" rule="P6-FLR-03" article="CBUAE CRM Art. 9.21, 9.23" confidence="high" trace={{ href: "/policy-docs?doc=pd_cbuae_crm" }} testId="whatif-diag-powered-coverage" />
    </div>
  );
}

function ShocksView({ book }: { book: string }) {
  const [shock, setShock] = React.useState({ pd: 20, lgd: 5, macro: 0 });
  const [applied, setApplied] = React.useState(shock);
  const { data, error } = useEws<Shocks>(() => intel.shocks(book, applied.pd, applied.lgd, applied.macro), `sh|${book}|${applied.pd}|${applied.lgd}|${applied.macro}`);
  return (
    <div className="space-y-3" data-testid="whatif-diag-shocks">
      <form className="flex flex-wrap items-end gap-3 text-[12px]" onSubmit={(e) => { e.preventDefault(); setApplied(shock); }}>
        {([["pd", "PD shock (%)"], ["lgd", "LGD shock (pp)"], ["macro", "Macro shock (% × sector beta)"]] as const).map(([k, label]) => (
          <label key={k} className="text-text-muted">{label}
            <input type="number" value={shock[k]} step={k === "lgd" ? 1 : 5} data-testid={`whatif-diag-shock-${k}`}
                   onChange={(e) => setShock({ ...shock, [k]: Number(e.target.value) })}
                   className="mt-0.5 block w-28 rounded border border-border bg-surface px-2 py-1 text-[13px] text-text-primary" /></label>
        ))}
        <button type="submit" className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast" data-testid="whatif-diag-shock-run">Apply</button>
      </form>
      {!data ? <Loading error={error} /> : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Current ECL" value={sar(data.base_ecl)} />
            <Stat label="Shocked ECL" value={sar(data.shocked_ecl)} tone="warning" />
            <Stat label="Portfolio impact" value={`${data.delta >= 0 ? "+" : ""}${sar(data.delta)}`} tone="negative"
                  sub={`${data.base_ecl ? ((100 * data.delta) / data.base_ecl).toFixed(1) : "—"}% of ECL`} />
          </div>
          {data.by_sector.length ? (
            <>
              <div className="flex items-center gap-2"><p className="text-sm font-semibold">Impact by sector</p>
                <InfoPopover title="Impact by sector">{data.method}</InfoPopover></div>
              <Plot testId="whatif-diag-shock-sector" ariaLabel="Shock impact by sector" height={260} filename="ecl-shock-by-sector"
                    data={[{ type: "bar", x: data.by_sector.map((s) => s.sector), y: data.by_sector.map((s) => s.delta), marker: { color: "var(--ipm-warning)" },
                             hovertemplate: "%{x}<br>+SAR %{y:,.1f}m<extra></extra>" }]}
                    layout={{ yaxis: { title: { text: "SAR million" }, tickformat: ",.0f" }, xaxis: { automargin: true }, margin: { l: 60, r: 10, t: 10, b: 90 } }} />
            </>) : null}
          <p className="text-sm font-semibold">Top movers</p>
          <table className="w-full text-[12px]" data-testid="whatif-diag-movers">
            <thead><tr className="text-left text-text-muted"><th className="py-1">Borrower</th><th className="text-right">Exposure</th><th className="text-right">ECL</th><th className="text-right">Shocked</th><th className="text-right">Change</th></tr></thead>
            <tbody>{data.top_movers.map((r) => (
              <tr key={r.obligor_id} className="border-t border-border"><td className="py-1">{r.name} <span className="text-text-muted">{r.obligor_id}</span></td>
                <td className="text-right tabular-nums">{sar(r.ead_sar_mn)}</td><td className="text-right tabular-nums">{sar(r.ecl_sar_mn)}</td>
                <td className="text-right tabular-nums">{sar(r.shocked)}</td><td className="text-right font-semibold tabular-nums">+{sar(r.delta)}</td></tr>))}</tbody>
          </table>
          <PoweredBy pack="P6" rule="P6-MOV-01" article={data.powered_by.article} confidence="medium" trace={{ href: "/what-if" }} testId="whatif-diag-powered-shocks" />
        </>)}
    </div>
  );
}

function Warnings({ domain }: { domain: DomainId }) {
  const { data, error } = useEws<Impact>(() => intel.impact(domain), `wi|${domain}`);
  if (!data) return <Loading error={error} />;
  const t = data.total;
  return (
    <div className="space-y-3" data-testid="whatif-diag-warnings">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={`Flagged ${data.labels.names} (Critical to Low)`} value={count(t.names)} sub={`exposure ${sar(t.ead)}`} />
        <Stat label="Current ECL" value={sar(t.current_ecl)} />
        <Stat label="Expected ECL" value={sar(t.expected_ecl)} sub={`+${sar(t.uplift)}`} tone="warning" />
        <Stat label="Severe case" value={sar(t.severe_ecl)} sub={`+${sar(t.severe_uplift)}`} tone="negative" />
      </div>
      <p className="text-[12px] text-text-muted">The same computation as Early Warning (P3), at the bucket PDs set in Admin: {data.by_bucket.map((b) => `${b.label} ${b.pd_pct.toFixed(0)}%`).join(", ")}.{" "}
        <Link href={`/early-warning?domain=${domain}`} className="text-accent hover:underline" data-testid="whatif-diag-open-ews">Open in Early Warning</Link></p>
      <PoweredBy pack="P3" rule="P3-ECL-02" article={data.powered_by.article} confidence="medium" trace={{ href: `/early-warning?domain=${domain}` }} testId="whatif-diag-powered-warnings" />
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "warning" | "negative" }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("text-lg font-bold tabular-nums", tone === "negative" ? "text-negative" : tone === "warning" ? "text-warning" : "text-text-primary")}>{value}</p>
      {sub ? <p className="text-[11px] tabular-nums text-text-muted">{sub}</p> : null}
    </div>
  );
}
