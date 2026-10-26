"use client";

/**
 * PLAN_R12 Session B (I17): the pre-flight check in the RM's Prepare view. `<PreflightPanel dealId="DD-01" onSubmit={…} />`.
 *
 * The same rules credit runs in Review, run before submission: what blocks submission, what the RM should explain, the documents still
 * missing and credit's open queries. Credit's opinion and internal notes are never shown here.
 */

import * as React from "react";
import { CheckCircle2, RefreshCw } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useLoad } from "@/lib/v5/dealdesk";
import { cn } from "@/lib/utils";

import { DocumentsPanel } from "../documents-panel";
import { Chip, Empty, PrimaryButton, SecondaryButton, Section } from "../kit";
import { review2Api } from "./api";
import { POINT_LABEL, POINT_TONE, type PreflightItem, SEV_LABEL, SEV_TONE } from "./helpers";
import { QueriesPanel } from "./queries-panel";

function Items({ title, items, testId }: { title: string; items: PreflightItem[]; testId: string }) {
  if (!items.length) return null;
  return (
    <div data-testid={testId}>
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{title} ({items.length})</h3>
      <ul className="space-y-1">
        {items.map((f) => (
          <li key={f.finding_id} className="rounded-md border border-border px-2.5 py-1.5">
            <div className="flex flex-wrap items-center gap-1.5"><Chip tone={SEV_TONE[f.severity]}>{SEV_LABEL[f.severity]}</Chip>
              <span className="text-[12px] font-medium text-text-primary">{f.title}</span>
              <span className="ml-auto text-[10px] text-text-muted">{f.point}. {f.point_name}</span></div>
            <p className="mt-0.5 whitespace-normal text-[12px] leading-5 text-text-secondary">{f.finding}</p>
          </li>))}
      </ul>
    </div>
  );
}

export function PreflightPanel({ dealId, onSubmit, showDocuments = true, showQueries = true }: {
  dealId: string; onSubmit?: () => void; showDocuments?: boolean; showQueries?: boolean;
}) {
  const [tick, setTick] = React.useState(0);
  const { data, error, loading } = useLoad(() => review2Api.preflight(dealId), `preflight:${dealId}:${tick}`);
  return (
    <div className="space-y-3" data-testid="preflight">
      <Section title="Pre-flight check" testId="preflight-panel"
               info={<>Before you submit, CreditProbe runs the same review rules credit will run: blocking items must be fixed (or the document
                 provided), items to explain should be answered in the proposal. Credit&rsquo;s own opinion is not shown here.</>}
               action={<SecondaryButton onClick={() => setTick((t) => t + 1)} aria-label="Run the pre-flight again"><RefreshCw size={13} aria-hidden />Re-run</SecondaryButton>}>
        {loading ? <Skeleton className="h-32 w-full" /> : error || !data ? <Empty>The pre-flight check is not available right now.</Empty> : (
          <div className="space-y-3">
            <div className={cn("flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2.5",
                               data.ready ? "border-positive/40 bg-positive-muted text-positive" : "border-warning/40 bg-warning-muted text-warning")}
                 data-testid="preflight-headline">
              {data.ready ? <CheckCircle2 size={16} aria-hidden /> : null}
              <p className="min-w-0 flex-1 text-[13px] font-semibold">{data.headline}</p>
              {onSubmit ? <PrimaryButton disabled={!data.ready} onClick={onSubmit} data-testid="preflight-submit">Submit to credit</PrimaryButton> : null}
            </div>
            <ul className="flex flex-wrap gap-1">
              {data.points.map((p) => <Chip key={p.point} tone={POINT_TONE[p.status]} title={POINT_LABEL[p.status]}>{p.point}. {p.name}</Chip>)}
            </ul>
            <Items title="Fix before submitting" items={data.blockers} testId="preflight-blockers" />
            <Items title="Explain in the proposal" items={data.warnings} testId="preflight-warnings" />
            <Items title="Notes" items={data.notes} testId="preflight-notes" />
          </div>)}
      </Section>
      {showDocuments ? <DocumentsPanel dealId={dealId} editable={false} canQuery={false} /> : null}
      {showQueries ? <QueriesPanel dealId={dealId} role="rm" /> : null}
    </div>
  );
}
