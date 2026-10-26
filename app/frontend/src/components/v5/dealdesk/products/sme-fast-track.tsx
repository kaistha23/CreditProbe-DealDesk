"use client";

/**
 * PLAN_R12 Session P (I28): the SME fast-track lane, one screen. The lane (every application with its decision) on
 * the left; the open application on the right: the decision first, then the scorecard (points per characteristic),
 * the programme rules, the authority by amount, the conditions and the short paper. Exceptions leave the lane:
 * "Open in the full flow" hands the route to Session U (`onOpenFullFlow`). Every figure from
 * GET /products/sme/fast-track[/{id}]. `useSmeFastTrackCount` feeds U's landing card.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { Chip, Empty, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import { productsApi, useProduct } from "./api";
import { type SmeDecision, type SmeLaneRow, decisionTone, pct, ruleValue, smeCardLine, smeTiles } from "./format";
import { Answer, Failed, Flags, Loading, Sub, Tiles, scrollCls } from "./parts";

const TITLE = "SME fast track";

export function useSmeFastTrackCount() {
  const { data, error, loading } = useProduct("sme-count", (s) => productsApi.smeCount(s));
  return { count: data?.count ?? null, line: data ? smeCardLine(data) : "", data, error, loading };
}

export function SmeFastTrack({ applicationId, onOpenFullFlow, status = "" }: {
  applicationId?: string; status?: string;
  /** U opens the deal in the full Deal Desk flow for an exception. */
  onOpenFullFlow?: (route: { applicationId: string; proposalId: string | null; reasons: string[] }) => void;
}) {
  const lane = useProduct(`sme-lane:${status}`, (s) => productsApi.smeLane(status, s));
  // a pick holds until the parent opens another application
  const [picked, setPicked] = React.useState<{ base?: string; id: string } | null>(null);
  if (lane.loading && !lane.data) return <Loading title={TITLE} testId="products-sme-loading" />;
  if (lane.error) return <Failed title={TITLE} message={lane.error} onRetry={lane.reload} testId="products-sme-error" />;
  const apps = lane.data?.applications ?? [];
  const current = (picked && picked.base === applicationId ? picked.id : applicationId) ?? apps[0]?.application_id;
  return (
    <Section title={TITLE} testId="products-sme"
             info={<>Programme lending decided on one screen: the SME scorecard, the programme rules and the authority by amount
               (applications from dd_sme_application). An exception goes to the full Deal Desk flow.</>}>
      {lane.data ? <Tiles tiles={smeTiles(lane.data.counts)} testId="products-sme-tiles" /> : null}
      {!apps.length ? <Empty>No SME applications in the lane.</Empty> : (
        <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(260px,1fr)_minmax(0,2fr)]">
          <LaneList apps={apps} current={current} onPick={(id) => setPicked({ base: applicationId, id })} />
          {current ? <Application key={current} aid={current} onOpenFullFlow={onOpenFullFlow} onDecided={lane.reload} /> : null}
        </div>)}
    </Section>
  );
}

function LaneList({ apps, current, onPick }: { apps: SmeLaneRow[]; current?: string; onPick: (id: string) => void }) {
  return (
    <ul className="min-w-0 divide-y divide-border rounded-lg border border-border" data-testid="products-sme-lane">
      {apps.map((a) => (
        <li key={a.application_id}>
          <button type="button" onClick={() => onPick(a.application_id)} aria-current={a.application_id === current}
                  className={cn("flex w-full min-w-0 flex-col gap-1 px-3 py-2 text-left hover:bg-surface-hover",
                                a.application_id === current && "bg-accent-muted")}>
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-[13px] font-medium text-text-primary">{a.applicant}</span>
              <span className="ml-auto shrink-0"><Chip tone={decisionTone(a.decision)}>{a.decision}</Chip></span>
            </span>
            <span className="truncate text-[12px] tabular-nums text-text-secondary">
              SAR {a.amount_sar_mn.toFixed(2)}m · {a.sector} · grade {a.grade} · {a.doa_level}
            </span>
          </button>
        </li>))}
    </ul>
  );
}

function Application({ aid, onOpenFullFlow, onDecided }: {
  aid: string; onOpenFullFlow?: (route: { applicationId: string; proposalId: string | null; reasons: string[] }) => void; onDecided: () => void;
}) {
  const { data, error, loading } = useProduct(`sme:${aid}`, (s) => productsApi.smeOne(aid, s));
  const [saving, setSaving] = React.useState(false);
  const [note, setNote] = React.useState("");
  if (loading && !data) return <div><Skeleton className="mb-2 h-6 w-2/3" /><Skeleton className="h-40 w-full" /></div>;
  if (error || !data) return <Empty>{error || "Application not found."}</Empty>;
  const d = data;
  const record = async () => {
    setSaving(true);
    try {
      const r = await productsApi.smeDecide(aid);
      setNote(r.published.published ? `Decision recorded: ${r.decision}.` : `Decision ${r.decision} shown; not recorded (${r.published.reason ?? "publisher unavailable"}).`);
      onDecided();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not record the decision.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="min-w-0" data-testid="products-sme-application">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Chip tone={decisionTone(d.decision)} testId="products-sme-decision">{d.decision}</Chip>
        <span className="text-[12px] text-text-secondary">{d.application_id}{d.received_date ? ` · received ${d.received_date}` : ""}{d.rm ? ` · RM ${d.rm}` : ""}</span>
        <span className="ml-auto flex gap-2">
          {d.route && onOpenFullFlow ? (
            <SecondaryButton type="button" onClick={() => onOpenFullFlow({ applicationId: d.application_id, proposalId: d.route?.proposal_id ?? null, reasons: d.route?.reasons ?? [] })}>
              Open in the full flow
            </SecondaryButton>) : null}
          <PrimaryButton type="button" onClick={record} disabled={saving}>{saving ? "Recording…" : "Record decision"}</PrimaryButton>
        </span>
      </div>
      <Answer text={d.answer} testId="products-sme-answer" />
      {note ? <p className="mb-2 text-[12px] text-text-secondary">{note}</p> : null}
      <Tiles testId="products-sme-app-tiles" tiles={[
        { label: "Score", value: d.scorecard.score.toFixed(0), sub: `${d.scorecard.scorecard.name} v${d.scorecard.scorecard.version}` },
        { label: "Grade", value: d.scorecard.grade, sub: `PD ${pct(d.scorecard.pd, 2)}` },
        { label: "Programme rules", value: `${d.rules.filter((r) => r.pass).length} of ${d.rules.length}`, sub: d.exceptions.length ? `${d.exceptions.length} not met` : "all met",
          tone: d.rules.every((r) => r.pass) ? "positive" : "warning" },
        { label: "Exposure", value: `SAR ${d.doa.exposure_sar_mn.toFixed(2)}m`, sub: d.doa.level, info: d.doa.reason },
      ]} />
      <Scorecard d={d} />
      <Rules d={d} />
      {d.exceptions.length ? <Sub title={d.decision === "Decline" ? "Why declined" : "Exceptions (to the full flow)"}><Flags items={d.exceptions} /></Sub> : null}
      {d.conditions.length ? <Sub title="Conditions"><ol className="list-decimal space-y-0.5 pl-4 text-[12px] text-text-secondary">{d.conditions.map((c) => <li key={c}>{c}</li>)}</ol></Sub> : null}
      <Sub title="Short paper">
        <div className="space-y-1 rounded-lg border border-border bg-surface px-3 py-2 text-[12px] leading-5 text-text-primary" data-testid="products-sme-paper">
          <p className="font-medium">{d.paper.headline}</p>
          {d.paper.lines.map((l) => <p key={l}>{l}</p>)}
        </div>
      </Sub>
    </div>
  );
}

function Scorecard({ d }: { d: SmeDecision }) {
  if (!d.scorecard.lines.length) {
    return (
      <Sub title={`Scorecard: ${d.scorecard.score.toFixed(0)} points`}>
        <p className="text-[12px] text-text-secondary">
          Score and grade as recorded with the application ({d.scorecard.scorecard.id} v{d.scorecard.scorecard.version}); the characteristics are not on the application.
        </p>
      </Sub>);
  }
  return (
    <Sub title={`Scorecard: ${d.scorecard.score.toFixed(0)} points`} info="Points per characteristic from the SME scorecard's own bins (Scorecard domain, SME-ANN).">
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-sme-score">
          <thead><tr>{["Characteristic", "Value", "Band", "Points"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{d.scorecard.lines.map((l) => (
            <tr key={l.variable}><td className={tdCls}>{l.label}</td><td className={tdCls}>{ruleValue(l.value)}</td>
              <td className={tdCls}>{l.bin}</td><td className={tdCls}>{l.points.toFixed(0)}</td></tr>))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}

function Rules({ d }: { d: SmeDecision }) {
  return (
    <Sub title="Programme rules">
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-sme-rules">
          <thead><tr>{["Rule", "Value", "Threshold", "Result"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{d.rules.map((r) => (
            <tr key={r.id}><td className={cn(tdCls, "whitespace-normal")}>{r.rule}</td><td className={tdCls}>{r.value_text ?? ruleValue(r.value)}</td>
              <td className={cn(tdCls, "whitespace-normal")}>{r.threshold}</td>
              <td className={tdCls}>{r.pass ? <Chip tone="positive">Met</Chip> : <Chip tone={r.on_fail === "hard" ? "negative" : "warning"}>{r.on_fail === "hard" ? "Not met: decline" : "Not met: full flow"}</Chip>}</td></tr>))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}
