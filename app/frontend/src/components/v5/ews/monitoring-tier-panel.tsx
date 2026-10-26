"use client";

/**
 * PLAN_R12 Session D: the Deal Desk monitoring tier on the Early Warning customer page (the one EWS panel R12 adds).
 * Reads dd_monitoring_plan through the read-only EWS link (GET /api/v1/dealdesk/monitoring/ews/{customer_id}):
 * "Monitoring tier High, set by Deal Desk on <date> because <driver>", the lowered band floors for a tier-High name
 * next to the book band, and the named triggers with what was observed. Shows nothing when the name has no plan or
 * the Deal Desk service is not running.
 */

import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { observedText, stress2Api, type EwsPanel } from "@/lib/v5/dealdesk-stress2";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

const TIER = { High: "bg-negative-muted text-negative", Medium: "bg-warning-muted text-warning", Standard: "bg-positive-muted text-positive" } as const;

export function MonitoringTierPanel({ customerId, period = "" }: { customerId: string; period?: string }) {
  const [d, setD] = React.useState<EwsPanel | null>(null);
  React.useEffect(() => {
    let live = true;
    stress2Api.ewsPanel(customerId, period).then((x) => { if (live) setD(x); }).catch(() => { if (live) setD(null); });
    return () => { live = false; };
  }, [customerId, period]);
  if (!d || !d.has_plan || !d.tier) return null;
  const th = d.thresholds;
  return (
    <Card className="p-4" data-testid="ews-monitoring-tier">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-text-primary">Deal Desk monitoring</p>
        <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-medium", TIER[d.tier])} data-testid="ews-monitoring-tier-chip">Tier {d.tier}</span>
        {d.alerts?.length ? <span className="rounded bg-negative-muted px-1.5 py-0.5 text-[11px] text-negative" data-testid="ews-monitoring-alert">{d.alerts.length} alert{d.alerts.length > 1 ? "s" : ""} raised</span> : null}
      </div>
      <p className="mt-1 text-[13px] text-text-primary" data-testid="ews-monitoring-sentence">{d.sentence}.</p>
      <p className="mt-0.5 text-[12px] text-text-secondary">Review every {d.review_frequency_months} months · next {d.next_review_date} · deal {d.proposal_id}</p>
      {th?.override ? (
        <p className="mt-2 text-[12px] text-text-secondary" data-testid="ews-monitoring-override">
          Tighter alert thresholds for this name
          <InfoPopover title="Alert thresholds">Moderate from {th.band_floors.moderate}, high from {th.band_floors.high}, critical from {th.band_floors.critical} points
          (book {th.book_floors.moderate}/{th.book_floors.high}/{th.book_floors.critical}).</InfoPopover>
          {d.in_ews_book ? <> Score {d.score ?? 0}: band <b>{d.band_with_override}</b> with the Deal Desk thresholds, {d.book_band} on the book&apos;s.</> : null}
        </p>) : null}
      {d.triggers?.length ? (
        <ul className="mt-2 space-y-1 text-[12px]" data-testid="ews-monitoring-triggers">
          {d.triggers.map((t) => (
            <li key={t.trigger_id} className="flex flex-wrap items-center gap-2" title={`${t.basis} · ${t.source}`}>
              <span className={cn("size-2 shrink-0 rounded-full", t.fired ? "bg-negative" : t.fired === false ? "bg-positive" : "bg-border")} aria-hidden />
              <span className="min-w-0 flex-1 text-text-primary">{t.label}</span>
              <span className="tabular-nums text-text-muted">{observedText(t)}{t.fired ? " · fired" : ""}</span>
            </li>))}
        </ul>) : null}
    </Card>
  );
}
