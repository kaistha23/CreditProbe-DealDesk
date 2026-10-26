"use client";

/**
 * R13 Session Q (PLAN_R13 §Q, J11): the compact **Financial quality** panel.
 *
 *   <FinQualityPanel proposalId="R12-TWA" />            the deal page's More menu (Session X mounts it through the slot)
 *   <FinQualityPanel facilityId="CF000011" compact />   the Book renewal row
 *
 * Grade A–D first, then one small counter per family, then the signals: flagged ones by default, all of them on request.
 * Each row shows the number, the threshold, the period and the Data Domains relation it was computed from; the sentence in
 * the credit voice, the formula, the policy clause and (for the statistical screens) the reliability note sit in the (i).
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { dealdeskOrigin, useLoad } from "@/lib/v5/dealdesk";

import { dataDomainsHref } from "../book/api";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeFinQuality } from "@/lib/v5/plain-words-g/deal";
import { InfoPopover } from "../explain";
import { Chip, Empty, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import { countsLine, finQualityUrl, gradeTone, ordered, sevTone, sourceLine, statusLabel, type FinQuality, type Signal, type Tone } from "./model";

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${dealdeskOrigin()}${url}`, { credentials: "include", cache: "no-store", ...init });
  if (r.status === 404) throw new Error("No financial statements on file for this deal.");
  if (!r.ok) throw new Error("The financial-quality screen is temporarily unavailable.");
  return (await r.json()) as T;
}

export function loadFinQuality(t: { proposalId?: string | null; facilityId?: string | null }): Promise<FinQuality> {
  const url = finQualityUrl(t);
  return url ? getJson<FinQuality>(url) : Promise.reject(new Error("No deal or facility given."));
}

export function publishFinQuality(proposalId: string): Promise<{ rows: number; grade: string }> {
  return getJson(`/api/v1/dealdesk/fin-quality/${encodeURIComponent(proposalId)}/publish`, { method: "POST" });
}

const TONE_BOX: Record<Tone, string> = {
  negative: "border-negative/40 bg-negative-muted text-negative",
  warning: "border-warning/40 bg-warning-muted text-warning",
  accent: "border-accent/40 bg-accent-muted text-accent",
  positive: "border-positive/40 bg-positive-muted text-positive",
  neutral: "border-border bg-surface text-text-secondary",
};

function GradeBadge({ grade }: { grade: string }) {
  return (
    <span data-testid="fin-quality-grade" aria-label={`Financial quality grade ${grade}`}
          className={cn("inline-flex size-10 shrink-0 items-center justify-center rounded-lg border text-[20px] font-bold", TONE_BOX[gradeTone(grade)])}>{grade}</span>
  );
}

function SourceCell({ s }: { s: Signal }) {
  const src = s.source;
  const line = sourceLine(s);
  if (!src?.domain) return <span className="text-text-muted">{line}</span>;
  return <a className="text-text-muted underline-offset-2 hover:text-text-secondary hover:underline" href={dataDomainsHref({ domain: src.domain, relation: src.relation, key: src.key, period: src.period ?? null })}
            title={`Open ${src.relation} in Data Domains`}>{line}</a>;
}

function SignalRow({ s }: { s: Signal }) {
  return (
    <tr data-testid={`fin-quality-signal-${s.code}`} data-flag={s.flag === null ? "na" : String(s.flag)}>
      <td className={cn(tdCls, "w-full min-w-[200px] whitespace-normal")}>
        <span className="inline-flex items-center gap-1">
          <span className="text-text-primary">{s.label}</span>
          <InfoPopover title={`${s.code} ${s.label}`}>
            <p>{s.text}</p>
            <p className="mt-1 text-text-muted">Formula: {s.basis}. Threshold: {s.policy_ref}.</p>
            {s.note ? <p className="mt-1 text-text-muted">Reliability: {s.note}</p> : null}
          </InfoPopover>
        </span>
        <div className="text-[11px]"><SourceCell s={s} /></div>
      </td>
      <td className={cn(tdCls, "text-right font-medium", s.flag ? "text-text-primary" : "text-text-secondary")}>{s.display}</td>
      <td className={cn(tdCls, "text-right text-text-secondary")}>{s.threshold_display}</td>
      <td className={tdCls}><Chip tone={s.flag === null ? "neutral" : sevTone(s.severity)}>{statusLabel(s)}</Chip></td>
    </tr>
  );
}

export function FinQualityView({ fq, compact = false, onPublish }: { fq: FinQuality; compact?: boolean; onPublish?: () => Promise<string> }) {
  const [all, setAll] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const g = fq.grade;
  const fams = fq.families.map((f) => f.family);
  const rows = ordered(fq.signals, fams);
  const flagged = rows.filter((s) => s.flag === true);
  const shown = all ? rows : flagged.slice(0, compact ? 3 : flagged.length);
  if (fq.mode === "none") return <Empty>No financial statements in Data Domains for {fq.subject.name}: the screen cannot run.</Empty>;
  return (
    <div className="space-y-3" data-testid="fin-quality-view">
      <div className="flex items-center gap-3">
        <GradeBadge grade={g.grade} />
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">Grade {g.grade}: {g.meaning}</p>
          <p className="text-[12px] tabular-nums text-text-secondary" data-testid="fin-quality-counts">
            {countsLine(g)} · {fq.subject.periods.slice(-3).join(", ") || "no audited periods"}
          </p>
        </div>
      </div>
      {!compact ? (
        <div className="flex flex-wrap gap-1.5" data-testid="fin-quality-families">
          {fq.families.map((f) => (
            <Chip key={f.family} tone={f.flagged ? sevTone(f.worst) : f.assessable ? "positive" : "neutral"}
                  title={`${f.flagged} flagged of ${f.signals}; ${f.assessable} assessable`}>
              {f.label} <b className="tabular-nums">{f.flagged}/{f.signals}</b>
            </Chip>))}
        </div>) : null}
      {shown.length ? (
        <table className={tableCls}>
          <thead><tr>{["Signal and source", "Value", "Threshold", "Status"].map((h, i) => <th key={h} className={cn(thCls, (i === 1 || i === 2) && "text-right")}>{h}</th>)}</tr></thead>
          <tbody>{shown.map((s) => <SignalRow key={s.code} s={s} />)}</tbody>
        </table>
      ) : <p className="text-[12px] text-text-secondary">No signal breaches its threshold on the data on file.</p>}
      <div className="flex flex-wrap items-center gap-2">
        <SecondaryButton onClick={() => setAll((a) => !a)} data-testid="fin-quality-toggle" aria-pressed={all}>
          {all ? "Flagged signals only" : `All ${rows.length} signals`}
        </SecondaryButton>
        {onPublish ? (
          <SecondaryButton data-testid="fin-quality-publish" onClick={async () => {
            try { setMsg(await onPublish()); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
          }}>Publish to review findings</SecondaryButton>) : null}
        {msg ? <span className="text-[12px] text-text-secondary" data-testid="fin-quality-message">{msg}</span> : null}
      </div>
    </div>
  );
}

/** The Financial quality panel for a deal (proposalId) or a Book renewal row (facilityId). */
export function FinQualityPanel({ proposalId, facilityId, compact = false }: { proposalId?: string; facilityId?: string; compact?: boolean }) {
  const key = `fin-quality:${proposalId ?? ""}:${facilityId ?? ""}`;
  const r = useLoad(() => loadFinQuality({ proposalId, facilityId }), key);
  const fq = r.data;
  const info = (
    <>
      <p>Seven families of signals on the statements, projects and account conduct in Data Domains: related-party balances, receivables quality,
        earnings quality (accruals, cash conversion, margins against sector peers, non-operating income), balance-sheet signals, audit signals,
        statistical screens (Beneish M-score, Benford first digits) and reported revenue against account turnover.</p>
      <p className="mt-1">{fq?.grade.rule ?? "Grade A–D from the flagged signals' severity."} Below 40% coverage the grade reflects only the data on file.</p>
    </>
  );
  return (
    <Section title="Financial quality" info={info} testId="fin-quality-panel">
      {compact ? null : <PanelWords panel="fin-quality" lines={fq ? () => writeFinQuality(fq) : r.error ? [] : null} />}
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p>
        : !fq ? <Skeleton className="h-40 w-full" />
        : <FinQualityView fq={fq} compact={compact}
                          onPublish={fq.subject.proposal_id && !compact ? async () => {
                            const x = await publishFinQuality(fq.subject.proposal_id as string);
                            return `${x.rows} finding(s) published to the review (grade ${x.grade}).`;
                          } : undefined} />}
    </Section>
  );
}
