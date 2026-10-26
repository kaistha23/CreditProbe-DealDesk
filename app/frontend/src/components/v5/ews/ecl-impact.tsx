"use client";

/**
 * PLAN_R9 C1 (P3 Early Warning → ECL Intelligence): "ECL impact of current warnings".
 *
 * Expected ECL = Σ [p × ECL if defaulted (Stage 3, EAD × LGD) + (1 − p) × current ECL] over the warned names, p the
 * bucket's 12-month default probability (management estimate, Admin → Settings). Severe case: every Critical and High
 * name at 90+ DPD. By sector (or product) and bucket, top 10 contributors, and the actions a CRO takes from here.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { FileText, Loader2, ShieldAlert, Eye, ClipboardCheck, Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { type DomainId, count, sar, useEws } from "@/lib/v5/ews";
import { BUCKETS, BUCKET_COLOR, BUCKET_LABEL, type Impact, intel } from "@/lib/v5/risk-intel";
import { ws3 } from "@/lib/v5/workspace-r3";

import { ExportToWhatIf } from "./parts";
import { Plot } from "./plot";

export function EclImpactPanel({ domain, period, segment = "", onOpenCustomer }: {
  domain: DomainId; period: string; segment?: string; onOpenCustomer?: (id: string) => void;
}) {
  const key = [domain, period, segment].join("|");
  const [tick, setTick] = React.useState(0);
  const { data, error, loading } = useEws<Impact>(() => intel.impact(domain, period, segment), `${key}|${tick}`);
  if (error) return <Card className="p-4 text-sm text-negative" data-testid="ews-ecl-impact-error">{error}</Card>;
  if (loading || !data) return <Skeleton className="h-72 w-full" />;
  return <Panel d={data} domain={domain} segment={segment} onOpenCustomer={onOpenCustomer} reload={() => setTick((t) => t + 1)} />;
}

function Panel({ d, domain, segment, onOpenCustomer, reload }: {
  d: Impact; domain: DomainId; segment: string; onOpenCustomer?: (id: string) => void; reload: () => void;
}) {
  const t = d.total;
  const L = d.labels;
  const segs = d.by_segment.slice(0, 12);
  return (
    <Card className="space-y-4 p-4" data-testid="ews-ecl-impact">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">P3 Intelligence</p>
        <h2 className="text-base font-semibold text-text-primary">ECL impact of current warnings</h2>
        <InfoPopover title="How it is computed">{d.method}</InfoPopover>
        <span className="text-[11px] text-text-muted">{segment ? `${segment} · ` : ""}{d.period} · SAR</span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="ews-ecl-kpis">
        <Stat label={`Flagged ${L.names} (Critical to Low)`} value={count(t.names)}
              sub={`${count(d.by_bucket.filter((b) => b.bucket !== "low").reduce((a, b) => a + b.names, 0))} warned (Medium and above) · exposure ${sar(t.ead)}`}
              testId="ews-ecl-names" />
        <Stat label="Current ECL of flagged names (performing)" value={sar(t.current_ecl)}
              sub={`${d.book.ecl ? ((100 * t.current_ecl) / d.book.ecl).toFixed(1) : "—"}% of book ECL`} testId="ews-ecl-current" />
        <Stat label="Expected ECL if warnings come true" value={sar(t.expected_ecl)} sub={`+${sar(t.uplift)}`} tone="warning"
              testId="ews-ecl-expected" />
        <Stat label="Severe case (Critical and High at 90+ DPD)" value={sar(t.severe_ecl)} sub={`+${sar(t.severe_uplift)}`}
              tone="negative" testId="ews-ecl-severe" />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[12px]" data-testid="ews-ecl-pd">
        <span className="text-text-muted">PD by warning bucket</span>
        {d.by_bucket.map((b) => (
          <span key={b.bucket} className="rounded-full border border-border px-2 py-0.5 tabular-nums">
            {b.label} <strong>{b.pd_pct.toFixed(0)}%</strong>
          </span>
        ))}
        <span className="italic text-text-muted">management estimate · v{d.pd_by_bucket.version}</span>
        <Link href="/settings?tab=ews-pd" className="inline-flex items-center gap-1 text-accent hover:underline" data-testid="ews-ecl-edit-pd">
          <Settings2 className="size-3.5" aria-hidden /> Edit in Admin
        </Link>
        <button type="button" onClick={reload} className="text-accent hover:underline" data-testid="ews-ecl-refresh">Refresh</button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">ECL uplift by {L.segment.toLowerCase()} and bucket</p>
            <InfoPopover title={`ECL uplift by ${L.segment.toLowerCase()}`}>
              Each bar is the expected ECL minus the current ECL of the warned names in that {L.segment.toLowerCase()},
              split by warning bucket. Hover for the amount; click a legend entry to hide a bucket.
            </InfoPopover>
          </div>
          <Plot testId="ews-ecl-by-segment" ariaLabel={`ECL uplift by ${L.segment.toLowerCase()} and bucket`} height={300}
                filename="ecl-uplift-by-segment"
                data={BUCKETS.map((b) => ({
                  type: "bar", orientation: "h", name: BUCKET_LABEL[b], marker: { color: BUCKET_COLOR[b] },
                  y: segs.map((s) => s.segment), x: segs.map((s) => s.by_bucket[b] ?? 0),
                  hovertemplate: `%{y}<br>${BUCKET_LABEL[b]}: SAR %{x:,.1f}m<extra></extra>`,
                }))}
                layout={{ barmode: "stack", yaxis: { autorange: "reversed", automargin: true },
                          xaxis: { title: { text: "SAR million" }, tickformat: ",.0f" }, legend: { orientation: "h", y: -0.32, traceorder: "normal" },
                          margin: { l: 10, r: 10, t: 10, b: 70 } }} />
        </div>
        <div>
          <p className="mb-1 text-sm font-semibold text-text-primary">By bucket</p>
          <table className="w-full text-[12px]" data-testid="ews-ecl-bucket-table">
            <thead><tr className="text-left text-text-muted">
              <th className="py-1">Bucket</th><th className="text-right">PD</th><th className="text-right">Names</th>
              <th className="text-right">Current ECL</th><th className="text-right">If defaulted</th><th className="text-right">Expected</th>
            </tr></thead>
            <tbody>
              {d.by_bucket.map((b) => (
                <tr key={b.bucket} className="border-t border-border">
                  <td className="py-1"><span className="mr-1 inline-block size-2 rounded-full" style={{ background: BUCKET_COLOR[b.bucket] }} />{b.label}</td>
                  <td className="text-right tabular-nums">{b.pd_pct.toFixed(0)}%</td>
                  <td className="text-right tabular-nums">{count(b.names)}</td>
                  <td className="text-right tabular-nums">{sar(b.current_ecl)}</td>
                  <td className="text-right tabular-nums">{sar(b.ecl_if_defaulted)}</td>
                  <td className="text-right font-semibold tabular-nums">{sar(b.expected_ecl)}</td>
                </tr>
              ))}
              <tr className="border-t border-border-strong font-semibold">
                <td className="py-1">Total</td><td /><td className="text-right tabular-nums">{count(t.names)}</td>
                <td className="text-right tabular-nums">{sar(t.current_ecl)}</td><td className="text-right tabular-nums">{sar(t.ecl_if_defaulted)}</td>
                <td className="text-right tabular-nums">{sar(t.expected_ecl)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {d.top_contributors.length ? (
        <div>
          <p className="mb-1 text-sm font-semibold text-text-primary">Top 10 contributors to the uplift</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="ews-ecl-top">
              <thead><tr className="text-left text-text-muted">
                <th className="py-1">Borrower</th><th>Sector</th><th>Bucket</th><th className="text-right">Stage</th>
                <th className="text-right">Exposure</th><th className="text-right">Current ECL</th><th className="text-right">Expected ECL</th>
                <th className="text-right">Uplift</th>
              </tr></thead>
              <tbody>
                {d.top_contributors.map((r) => (
                  <tr key={r.owner} className="cursor-pointer border-t border-border hover:bg-surface-muted" title={r.reasons}
                      onClick={() => onOpenCustomer?.(r.owner)} data-testid={`ews-ecl-top-${r.owner}`}>
                    <td className="py-1 text-accent">{r.owner_name} <span className="text-text-muted">{r.owner}</span></td>
                    <td>{r.segment}</td><td>{BUCKET_LABEL[r.bucket]}</td>
                    <td className="text-right tabular-nums">{r.stage}</td>
                    <td className="text-right tabular-nums">{sar(r.ead)}</td>
                    <td className="text-right tabular-nums">{sar(r.current_ecl)}</td>
                    <td className="text-right tabular-nums">{sar(r.expected_ecl)}</td>
                    <td className="text-right font-semibold tabular-nums">{sar(r.uplift)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="text-[12px] text-text-muted" data-testid="ews-ecl-retail-note">
          Retail is shown at {L.segment.toLowerCase()} level: the uplift by {L.segment.toLowerCase()} is in the chart above.
        </p>
      )}

      <Actions d={d} domain={domain} segment={segment} />
      <PoweredBy pack="P3" rule="P3-ECL-02" article={d.powered_by.article} confidence="medium"
                 trace={{ href: `/early-warning/model?domain=${domain}` }} testId="ews-ecl-powered-by" />
    </Card>
  );
}

function Actions({ d, domain, segment }: { d: Impact; domain: DomainId; segment: string }) {
  const router = useRouter();
  const [busy, setBusy] = React.useState("");
  const [note, setNote] = React.useState("");
  const run = async (kind: string, fn: () => Promise<string>) => {
    setBusy(kind); setNote("");
    try { setNote(await fn()); } catch (e) { setNote(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  const scope = { domain, period: d.period, segment, buckets: ["critical", "high"] };
  const crit = d.by_bucket.filter((b) => b.bucket === "critical" || b.bucket === "high").reduce((a, b) => a + b.names, 0);
  const sicr = () => run("sicr", async () => {
    const top = d.top_contributors;
    const made = await ws3.importInvestigation({
      source: { type: "early-warning-level", id: `${domain}|${d.period}|${segment || "all"}`, label: "Early Warning · ECL impact",
                href: `/early-warning?domain=${domain}&period=${d.period}` },
      title: `SICR assessment: Critical and High warnings, ${segment || (domain === "corporate" ? "corporate book" : "retail book")}, ${d.period}`,
      continue_href: `/early-warning?domain=${domain}&period=${d.period}`, period: d.period,
      turns: [
        { role: "user", text: `Assess SICR (CBUAE CRM Art. 7.11) for the ${count(crit)} Critical and High names. Evidence pack attached.` },
        { role: "assistant", text: `Evidence pack: ${count(d.total.names)} warned names, current ECL ${sar(d.total.current_ecl)}, expected ECL ${sar(d.total.expected_ecl)}, severe case ${sar(d.total.severe_ecl)}. Each name below lists its warning reasons; confirm or rebut SICR with CCO and CRO sign-off (Art. 7.10).`,
          artifacts: [
            { kind: "figures", title: "ECL impact of current warnings", period: d.period, figures: [
              { key: "names", label: "Warned names", value: d.total.names, unit: "int" },
              { key: "current", label: "Current ECL", value: d.total.current_ecl, unit: "sar_mn" },
              { key: "expected", label: "Expected ECL", value: d.total.expected_ecl, unit: "sar_mn" },
              { key: "severe", label: "Severe case ECL", value: d.total.severe_ecl, unit: "sar_mn" } ] },
            { kind: "table", title: "Names for SICR assessment (evidence)", period: d.period,
              columns: [{ key: "name", label: "Borrower", unit: "text" }, { key: "bucket", label: "Bucket", unit: "text" },
                        { key: "ead", label: "Exposure", unit: "sar_mn" }, { key: "ecl", label: "Current ECL", unit: "sar_mn" },
                        { key: "reasons", label: "Warning evidence", unit: "text" }],
              rows: top.map((r) => ({ name: `${r.owner_name} (${r.owner})`, bucket: BUCKET_LABEL[r.bucket], ead: r.ead, ecl: r.current_ecl, reasons: r.reasons })) },
          ] },
      ],
    } as Parameters<typeof ws3.importInvestigation>[0]);
    router.push(`/investigations/${encodeURIComponent(made.id)}`);
    return "Investigation created.";
  });
  return (
    <div className="space-y-2" data-testid="ews-ecl-actions">
      <div className="flex flex-wrap items-center gap-2">
        <ExportToWhatIf testId="ews-ecl-whatif" label="Send all Critical and High borrowers to What-If (incl. defaulted)" body={{ domain, period: d.period, segment, cohort: "high_or_critical" }} />
        {domain === "corporate" ? (
          <>
            <Button variant="outline" size="sm" disabled={!!busy} data-testid="ews-ecl-bank-watchlist"
                    onClick={() => run("bw", async () => { const r = await intel.action({ kind: "bank_watchlist", ...scope }); return `${count(r.added)} Critical and High names added to the Bank Watchlist.`; })}>
              {busy === "bw" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <Eye className="mr-1 size-3.5" aria-hidden />} Add to Bank Watchlist
            </Button>
            <Button variant="outline" size="sm" disabled={!!busy} data-testid="ews-ecl-arw"
                    onClick={() => run("arw", async () => {
                      const ids = d.top_contributors.filter((r) => r.stage < 3).slice(0, 5).map((r) => r.owner);
                      const r = await intel.action({ kind: "accepted_risk_watch", ...scope, obligor_ids: ids, tier: 2 });
                      return `${count(r.added)} performing top contributors added to the Accepted Risk Watch (Tier 2).`;
                    })}>
              {busy === "arw" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <ShieldAlert className="mr-1 size-3.5" aria-hidden />} Add to Accepted Risk Watch
            </Button>
          </>
        ) : null}
        <Button variant="outline" size="sm" disabled={!!busy} onClick={() => void sicr()} data-testid="ews-ecl-sicr">
          {busy === "sicr" ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <ClipboardCheck className="mr-1 size-3.5" aria-hidden />} Request SICR assessment
        </Button>
        <a href={intel.memoHref(domain, d.period)} data-testid="ews-ecl-memo"
           className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
          <FileText className="size-3.5" aria-hidden /> Draft memo to CRO (Word)
        </a>
        {domain === "corporate" ? (
          <Link href="/borrower-360?domain=corporate&card=accepted_risk" className="text-[12px] text-accent hover:underline" data-testid="ews-ecl-open-arw">Accepted Risk Watch names in Borrower 360</Link>
        ) : null}
      </div>
      <p className="flex items-center gap-1 text-[11px] text-text-muted" data-testid="ews-ecl-whatif-note">Sent to What-If<InfoPopover title="Sent to What-If">What-If receives every Critical and High {d.labels.names.replace(/s$/, "")} with all its exposures, including those already in Stage 3 or 90+ DPD (the Early Warning High or critical card), so its totals are larger than the performing-only figures above.</InfoPopover></p>
      {note ? <p className="text-[12px] text-text-secondary" data-testid="ews-ecl-action-note">{note}</p> : null}
    </div>
  );
}

function Stat({ label, value, sub, tone, testId }: { label: string; value: string; sub?: string; tone?: "warning" | "negative"; testId: string }) {
  return (
    <div className="rounded-md border border-border p-3" data-testid={testId}>
      <p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${tone === "negative" ? "text-negative" : tone === "warning" ? "text-warning" : "text-text-primary"}`}>{value}</p>
      {sub ? <p className="text-[11px] text-text-muted tabular-nums">{sub}</p> : null}
    </div>
  );
}
