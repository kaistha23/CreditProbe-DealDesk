"use client";

/**
 * PLAN_R9 C2 (P4 Accepted Risk Intelligence): the Accepted Risk Watch, a CRO screen.
 * Concerns accepted at approval become dated watch items; two or more missed items, or one missed critical item,
 * escalate to the Bank Watchlist and a SICR assessment. Exposure on the list and the ECL if Tier 1 moved to Stage 2.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { Plot } from "@/components/v5/ews/plot";
import { count, sar, useEws } from "@/lib/v5/ews";
import { type WatchClient, type WatchView, intel } from "@/lib/v5/risk-intel";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<string, string> = {
  "on track": "bg-positive-muted text-positive", due: "bg-warning-muted text-warning", missed: "bg-negative-muted text-negative",
};

export function AcceptedRiskWatch() {
  const params = useSearchParams();
  const router = useRouter();
  const tier = Number(params.get("tier") || 0);
  const [tick, setTick] = React.useState(0);
  const { data, error, loading } = useEws<WatchView>(() => intel.watch(), `w|${tick}`);
  const setTier = (t: number) => router.replace(t ? `/accepted-risk?tier=${t}` : "/accepted-risk");
  return (
    <div className="space-y-5" data-testid="accepted-risk">
      <div className="flex flex-wrap items-center gap-3">
        <BackButton fallback={{ href: "/early-warning", label: "Early Warning" }} testId="arw-back" />
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <h1 className="text-2xl font-semibold text-text-primary">Accepted Risk Watch</h1>
        </div>
        <InfoPopover title="Accepted Risk Watch">
          Concerns the committee accepted at approval, without a SICR, recorded as dated watch items. Each item is on track,
          due (within 21 days) or missed. {data?.rule}
        </InfoPopover>
        <span className="ml-auto text-[12px] text-text-muted">As of {data?.as_of ?? "…"} · SAR million</span>
      </div>
      {error ? <p className="text-sm text-negative" data-testid="arw-error">{error}</p> : null}
      {loading || !data ? <Skeleton className="h-96 w-full" /> : <Body v={data} tier={tier} setTier={setTier} reload={() => setTick((x) => x + 1)} />}
    </div>
  );
}

function Body({ v, tier, setTier, reload }: { v: WatchView; tier: number; setTier: (t: number) => void; reload: () => void }) {
  const rows = tier ? v.clients.filter((c) => c.tier === tier) : v.clients;
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="arw-kpis">
        <Kpi label="Names on the list" value={count(v.names)} sub={`${count(v.items.total)} watch items`} onClick={() => setTier(0)} testId="arw-kpi-names" />
        <Kpi label="Exposure on the list" value={sar(v.exposure)} sub={`ECL ${sar(v.ecl)}`} testId="arw-kpi-exposure" />
        <Kpi label="Escalate now" value={count(v.escalations)} sub="Bank Watchlist + SICR" tone="negative" testId="arw-kpi-escalate" />
        <Kpi label="Items due / missed" value={`${count(v.items.due)} / ${count(v.items.missed)}`} sub={`${count(v.items.on_track)} on track`} tone="warning" testId="arw-kpi-items" />
        <Kpi label="ECL if Tier 1 moved to Stage 2" value={sar(v.tier1_stage2.stage2_ecl)} sub={`+${sar(v.tier1_stage2.uplift)} on ${sar(v.tier1_stage2.current_ecl)}`}
             tone="warning" testId="arw-kpi-tier1" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">Tiers: exposure and ECL if moved to Stage 2</p>
            <InfoPopover title="Tiers">Tier 1 is closest to a SICR and reviewed monthly; Tier 3 quarterly. The amber bar is
              the ECL if the tier moved to Stage 2 (lifetime PD on its Stage 1 facilities). Click a bar to filter.</InfoPopover>
          </div>
          <Plot testId="arw-tier-chart" ariaLabel="Accepted Risk Watch tiers" height={240} filename="accepted-risk-tiers"
                onPointClick={(cd) => setTier(Number(cd) || 0)}
                data={[
                  { type: "bar", name: "Current ECL", x: v.tiers.map((t) => `Tier ${t.tier}`), y: v.tiers.map((t) => t.ecl),
                    customdata: v.tiers.map((t) => t.tier), marker: { color: "var(--ipm-chart-1)" },
                    hovertemplate: "%{x}<br>Current ECL SAR %{y:,.1f}m<extra></extra>" },
                  { type: "bar", name: "ECL if Stage 2", x: v.tiers.map((t) => `Tier ${t.tier}`), y: v.tiers.map((t) => t.ecl_stage2),
                    customdata: v.tiers.map((t) => t.tier), marker: { color: "var(--ipm-warning)" },
                    hovertemplate: "%{x}<br>ECL if Stage 2 SAR %{y:,.1f}m<extra></extra>" },
                ]}
                layout={{ barmode: "group", yaxis: { title: { text: "SAR million" }, tickformat: ",.1f" }, legend: { orientation: "h", y: -0.2 },
                          margin: { l: 50, r: 10, t: 10, b: 40 } }} />
          <div className="mt-2 flex flex-wrap gap-2" data-testid="arw-tier-filter">
            {[0, 1, 2, 3].map((t) => (
              <Button key={t} size="sm" variant={tier === t ? "default" : "outline"} onClick={() => setTier(t)} data-testid={`arw-tier-${t}`}>
                {t ? `Tier ${t} (${v.tiers[t - 1].names})` : `All (${v.names})`}
              </Button>
            ))}
          </div>
        </Card>
        <Card className="space-y-2 p-4" data-testid="arw-rule">
          <p className="text-sm font-semibold text-text-primary">Escalation rule</p>
          <p className="text-[13px] text-text-secondary">{v.rule}</p>
          <ul className="space-y-1 text-[12px]">
            {v.clients.filter((c) => c.escalation.escalate).map((c) => (
              <li key={c.watch_id} className="flex items-start gap-1"><AlertTriangle className="mt-0.5 size-3.5 text-negative" aria-hidden />
                <span><strong>{c.name}</strong> (Tier {c.tier}): {c.escalation.why}. {c.escalation.action}.</span></li>
            ))}
          </ul>
          <p className="text-[11px] text-text-muted">{v.currency_note}</p>
          <PoweredBy pack="P4" rule="P4-ESC-02" article={v.powered_by.article} confidence="high" trace={{ href: "/data-builder?domain=watch" }} testId="arw-powered-by" />
        </Card>
      </div>

      <Card className="p-0" data-testid="arw-list">
        <div className="grid grid-cols-[24px_1.6fr_0.5fr_0.9fr_0.9fr_0.9fr_1.1fr_1fr] gap-2 border-b border-border px-3 py-2 text-[11px] uppercase tracking-[0.06em] text-text-muted">
          <span /><span>Client</span><span>Tier</span><span className="text-right">Exposure</span><span className="text-right">ECL</span>
          <span className="text-right">ECL if Stage 2</span><span>Items</span><span>Escalation</span>
        </div>
        {rows.map((c) => <Row key={c.watch_id} c={c} reload={reload} />)}
      </Card>
    </>
  );
}

function Row({ c, reload }: { c: WatchClient; reload: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const counts = { "on track": 0, due: 0, missed: 0 } as Record<string, number>;
  c.items.forEach((i) => { counts[i.status] = (counts[i.status] ?? 0) + 1; });
  const escalate = async () => {
    try {
      await intel.action({ kind: "bank_watchlist", obligor_ids: [c.obligor_id], name: c.name, note: c.escalation.why });
      await intel.action({ kind: "sicr_assessment", obligor_ids: [c.obligor_id], name: c.name, note: c.escalation.why });
      setNote("Moved to the Bank Watchlist; SICR assessment requested.");
      reload();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div className="border-b border-border last:border-b-0" data-testid={`arw-row-${c.watch_id}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} data-testid={`arw-open-${c.watch_id}`}
              className="grid w-full grid-cols-[24px_1.6fr_0.5fr_0.9fr_0.9fr_0.9fr_1.1fr_1fr] items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-surface-muted">
        {open ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
        <span><span className="font-medium text-text-primary">{c.name}</span>
          <span className="block text-[11px] text-text-muted">{c.obligor_id} · {c.sector}{c.source === "proposal" ? " · proposal case (AED)" : ""}</span></span>
        <span className="tabular-nums">{c.tier}</span>
        <span className="text-right tabular-nums">{sar(c.exposure_sar_mn)}</span>
        <span className="text-right tabular-nums">{sar(c.ecl_sar_mn)}</span>
        <span className="text-right tabular-nums">{sar(c.ecl_stage2_sar_mn)}</span>
        <span className="flex flex-wrap gap-1 text-[11px]">
          {(["on track", "due", "missed"] as const).map((s) => counts[s] ? <span key={s} className={cn("rounded-full px-1.5", STATUS_TONE[s])}>{counts[s]} {s}</span> : null)}
        </span>
        <span className={cn("text-[12px]", c.escalation.escalate ? "font-semibold text-negative" : "text-text-muted")}>
          {c.escalation.escalate ? "Escalate" : "Within appetite"}
        </span>
      </button>
      {open ? (
        <div className="space-y-3 bg-surface-muted/40 px-10 pb-4 pt-1" data-testid={`arw-detail-${c.watch_id}`}>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">No-SICR rationale recorded at approval</p>
            <p className="text-[13px] text-text-secondary">{c.no_sicr_rationale}</p>
            <p className="text-[11px] text-text-muted">Approved {c.approved_on} by {c.approved_by}{c.currency === "AED" && c.exposure_ccy_mn ? ` · exposure AED ${c.exposure_ccy_mn.toFixed(1)} million` : ""}</p>
          </div>
          {c.items.length ? (
            <table className="w-full text-[12px]">
              <thead><tr className="text-left text-text-muted"><th className="py-1">Watch item (trigger)</th><th>Metric</th><th>Due</th><th>Frequency</th><th>Status</th><th>Article</th></tr></thead>
              <tbody>
                {c.items.map((i) => (
                  <tr key={i.item_id} className="border-t border-border">
                    <td className="py-1">{i.trigger}{i.critical ? <span className="ml-1 rounded bg-negative-muted px-1 text-[10px] text-negative">critical</span> : null}</td>
                    <td>{i.metric}</td><td className="tabular-nums">{i.due_date}</td><td>{i.frequency}</td>
                    <td><span className={cn("rounded-full px-1.5 py-0.5", STATUS_TONE[i.status])}>{i.status}</span></td>
                    <td className="text-text-muted">{i.article}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-[12px] text-text-muted">Watch items are set at the next watch committee.</p>}
          <div className="flex flex-wrap items-center gap-2">
            {c.escalation.escalate ? (
              <Button size="sm" onClick={() => void escalate()} data-testid={`arw-escalate-${c.watch_id}`}>Move to Bank Watchlist and request SICR assessment</Button>
            ) : null}
            {c.source === "book" ? (
              <a href={`/early-warning?domain=corporate&customer=${encodeURIComponent(c.obligor_id)}`} className="text-[12px] text-accent hover:underline"
                 data-testid={`arw-ews-${c.watch_id}`}>Open in Early Warning</a>
            ) : (
              <a href="/deal-desk" className="text-[12px] text-accent hover:underline" data-testid={`arw-dealdesk-${c.watch_id}`}>Open the proposal in Deal Desk</a>
            )}
            {note ? <span className="text-[12px] text-text-secondary">{note}</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ label, value, sub, tone, testId, onClick }: { label: string; value: string; sub?: string; tone?: "warning" | "negative"; testId: string; onClick?: () => void }) {
  const C = onClick ? "button" : "div";
  return (
    <C {...(onClick ? { type: "button" as const, onClick } : {})} data-testid={testId}
       className={cn("rounded-md border border-border bg-surface p-3 text-left", onClick && "hover:border-accent")}>
      <p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("text-lg font-bold tabular-nums", tone === "negative" ? "text-negative" : tone === "warning" ? "text-warning" : "text-text-primary")}>{value}</p>
      {sub ? <p className="text-[11px] tabular-nums text-text-muted">{sub}</p> : null}
    </C>
  );
}
