"use client";

/**
 * R14 Session F (K35): Propose for monitoring and the Monitoring page.
 *
 *   ProposeMonitoringButton   on the deal header and on every row of Going bad, Renewals, Book and Early Warning: a short
 *                             form (tier, reason prefilled from the evidence, review frequency, named triggers, owner, due date)
 *   MonitoringPage            Deal Desk → Monitoring (header button next to Book): proposed (maker-checker approve / reject),
 *                             active by tier, triggers hit, reviews due, history
 *   MonitoringLine            the one line Early Warning and Borrower 360 show for a borrower under monitoring
 * Everything is published to Data Domains (dd_monitoring_proposal); an approval changes the deal's monitoring plan or the
 * Book facility's tier through their own writers.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { Eye, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import {
  type MonitoringPage as Page, type MonitoringPrefill, type MonitoringProposal, type MonitoringSubject, type ObligorMonitoring, TIER_TONE, flowApi,
} from "@/lib/v5/dealdesk-flow";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";

const FREQ_LABEL: Record<string, string> = { monthly: "Monthly", quarterly: "Quarterly", semi_annual: "Semi-annual", annual: "Annual" };

function ProposeForm({ subject, onClose, onDone }: { subject: MonitoringSubject; onClose: () => void; onDone: (p: MonitoringProposal) => void }) {
  const [pre, setPre] = React.useState<MonitoringPrefill | null>(null);
  const [form, setForm] = React.useState<Partial<MonitoringPrefill>>({});
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => {
    let live = true;
    void flowApi.prefill(subject).then((p) => { if (live) { setPre(p); setForm(p); } }).catch((e) => { if (live) setErr(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, [subject]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const set = (k: keyof MonitoringPrefill, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const submit = async () => {
    if (!pre) return;
    setBusy(true);
    setErr("");
    try {
      onDone(await flowApi.propose({ ...pre, ...form, evidence: pre.evidence, subject_kind: pre.proposal_id ? "deal" : subject.facilityRef ? "facility" : "borrower" }));
    } catch (e) { setErr(friendlyMessage(e, "Deal Desk")); } finally { setBusy(false); }
  };
  // A portal: the form opens from inside table cells and clickable cards; events stop here so the row or card does not react.
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Propose for monitoring" data-testid="monitoring-propose-dialog"
         className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4" onClick={(e) => { e.stopPropagation(); onClose(); }}
         onKeyDown={(e) => e.stopPropagation()}>
      <div className="relative mt-10 w-full max-w-[640px] rounded-xl bg-surface p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} aria-label="Close" data-testid="monitoring-propose-close"
                className="absolute right-3 top-3 inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={15} /></button>
        <h2 className="text-[16px] font-semibold text-text-primary">Propose for monitoring</h2>
        <p className="text-[12px] text-text-secondary">{pre?.obligor_name || subject.obligorName || subject.obligorId || subject.proposalId}{subject.facilityRef && subject.facilityRef !== "ALL" ? ` · ${subject.facilityRef}` : ""}</p>
        {err ? <p role="alert" className="mt-2 text-[12px] text-negative">{err}</p> : null}
        {!pre && !err ? <Skeleton className="mt-3 h-56 w-full" /> : null}
        {pre ? (
          <div className="mt-3 space-y-3 text-[12px]">
            <PlainWords lines={pre.plain_words} testId="monitoring-propose-plain-words" />
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-28 text-text-muted">Tier</span>
              {pre.tiers.map((t) => (
                <button key={t} type="button" onClick={() => set("tier", t)} aria-pressed={form.tier === t} data-testid={`monitoring-tier-${t.toLowerCase()}`}
                        className={cn("h-7 rounded-full border px-3", form.tier === t ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>{t}</button>))}
            </div>
            <label className="flex items-start gap-2"><span className="w-28 pt-1.5 text-text-muted">Reason</span>
              <textarea value={form.reason ?? ""} onChange={(e) => set("reason", e.target.value)} rows={3} data-testid="monitoring-reason"
                        className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5" /></label>
            {pre.evidence.length ? <ul className="ml-[120px] space-y-0.5 text-[11px] text-text-muted" data-testid="monitoring-evidence">
              {pre.evidence.map((e) => <li key={e.label}>{e.label}: {e.value} <span>({e.relation})</span></li>)}</ul> : null}
            <label className="flex items-center gap-2"><span className="w-28 text-text-muted">Review</span>
              <select value={form.review_frequency} onChange={(e) => set("review_frequency", e.target.value)} data-testid="monitoring-frequency"
                      className="h-8 rounded-md border border-border bg-background px-2">{pre.frequencies.map((f) => <option key={f} value={f}>{FREQ_LABEL[f] ?? f}</option>)}</select></label>
            <div className="flex items-start gap-2"><span className="w-28 pt-0.5 text-text-muted">Triggers</span>
              <ul className="min-w-0 flex-1 space-y-0.5" data-testid="monitoring-triggers">{(form.triggers ?? []).map((t) => <li key={t.label}>{t.label}</li>)}</ul></div>
            <label className="flex items-center gap-2"><span className="w-28 text-text-muted">Owner</span>
              <input value={form.owner ?? ""} onChange={(e) => set("owner", e.target.value)} data-testid="monitoring-owner"
                     className="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2" /></label>
            <label className="flex items-center gap-2"><span className="w-28 text-text-muted">First review due</span>
              <input type="date" value={form.due_date ?? ""} onChange={(e) => set("due_date", e.target.value)} data-testid="monitoring-due"
                     className="h-8 rounded-md border border-border bg-background px-2" /></label>
            <div className="flex justify-end gap-2 pt-1">
              <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
              <PrimaryButton onClick={() => void submit()} disabled={busy || (form.reason ?? "").trim().length < 5} data-testid="monitoring-submit">
                {busy ? "Proposing…" : "Propose (a checker approves)"}</PrimaryButton>
            </div>
          </div>) : null}
      </div>
    </div>, document.body);
}

export function ProposeMonitoringButton({ subject, compact, label = "Propose for monitoring", onDone, testId = "monitoring-propose" }: {
  subject: MonitoringSubject; compact?: boolean; label?: string; onDone?: (p: MonitoringProposal) => void; testId?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [done, setDone] = React.useState<MonitoringProposal | null>(null);
  const subj = React.useMemo(() => subject, [subject.proposalId, subject.obligorId, subject.facilityRef, subject.source]); // eslint-disable-line react-hooks/exhaustive-deps
  const click = (e: React.MouseEvent) => { e.stopPropagation(); setOpen(true); };
  return (
    <>
      {compact ? (
        <button type="button" onClick={click} data-testid={testId} title={done ? `Proposed: tier ${done.tier}, awaiting a checker` : label}
                className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded border px-1.5 text-[10.5px]", done ? "border-accent text-accent" : "border-border text-text-secondary hover:border-accent hover:text-accent")}>
          <Eye size={11} aria-hidden /> {done ? "Proposed" : "Monitor"}</button>
      ) : (
        <SecondaryButton onClick={click} data-testid={testId} title={done ? `Proposed: tier ${done.tier}, awaiting a checker` : undefined}>
          <Eye size={13} /> {done ? `Proposed (tier ${done.tier})` : label}</SecondaryButton>)}
      {open ? <ProposeForm subject={subj} onClose={() => setOpen(false)} onDone={(p) => { setDone(p); setOpen(false); onDone?.(p); }} /> : null}
    </>
  );
}

function Rows({ rows, onDecide, busy, testId }: { rows: MonitoringProposal[]; onDecide?: (p: MonitoringProposal, approve: boolean) => void; busy?: boolean; testId: string }) {
  if (!rows.length) return <p className="text-[12px] text-text-muted" data-testid={`${testId}-empty`}>None.</p>;
  return (
    <div className="overflow-x-auto"><table className={cn(tableCls, "table-fixed min-w-[820px]")} data-testid={testId}>
      <colgroup><col className="w-[22%]" /><col className="w-[8%]" /><col className="w-[34%]" /><col className="w-[12%]" /><col className="w-[10%]" /><col className="w-[14%]" /></colgroup>
      <thead><tr>{["Borrower", "Tier", "Reason", "Review · due", "Proposed by", onDecide ? "Decision" : "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.monitoring_proposal_id} data-testid="monitoring-row" data-status={r.status}>
          <td className={cn(tdCls, "whitespace-normal")}><p className="font-medium">{r.obligor_name || r.obligor_id}</p>
            <p className="text-[11px] text-text-muted">{[r.proposal_id, r.facility_ref !== "ALL" ? r.facility_ref : "", r.source_screen.replace(/_/g, " ")].filter(Boolean).join(" · ")}</p></td>
          <td className={tdCls}><Chip tone={TIER_TONE[r.tier] ?? "neutral"}>{r.tier}</Chip>{r.previous_tier ? <span className="block text-[11px] text-text-muted">was {r.previous_tier}</span> : null}</td>
          <td className={cn(tdCls, "whitespace-normal text-text-secondary")}>
            {r.status === "active" && r.triggers_hit_json?.length ? (
              <span className="mb-0.5 block text-negative" data-testid="monitoring-hit">Triggered: {r.triggers_hit_json.map((h) => `${h.label} (${typeof h.value === "number" ? Number(h.value.toFixed(2)) : String(h.value ?? "")}${h.at ? `, ${h.at}` : ""})`).join("; ")}</span>) : null}
            <span className="line-clamp-3" title={r.reason}>{r.reason}</span></td>
          <td className={cn(tdCls, "whitespace-normal")}>{FREQ_LABEL[r.review_frequency] ?? r.review_frequency}<span className="block text-[11px] text-text-muted">{r.due_date}</span></td>
          <td className={cn(tdCls, "whitespace-normal")}>{r.maker}<span className="block text-[11px] text-text-muted">{String(r.made_at).slice(0, 10)}</span></td>
          <td className={cn(tdCls, "whitespace-normal")}>{onDecide ? (
            <div className="flex flex-wrap gap-1">
              <PrimaryButton className="h-7 px-2.5 text-[12px]" disabled={busy || r.own} onClick={() => onDecide(r, true)} data-testid={`monitoring-approve-${r.monitoring_proposal_id}`}
                             title={r.own ? "You proposed it: another person approves (maker-checker)" : undefined}>Approve</PrimaryButton>
              <SecondaryButton className="h-7 px-2.5 text-[12px]" disabled={busy || r.own} onClick={() => onDecide(r, false)} data-testid={`monitoring-reject-${r.monitoring_proposal_id}`}
                               title={r.own ? "You proposed it: another person decides (maker-checker)" : undefined}>Reject</SecondaryButton>
            </div>) : <><Chip tone={r.status === "active" ? "accent" : r.status === "rejected" ? "negative" : "neutral"}>{r.status}</Chip>
              {r.checker ? <span className="block text-[11px] text-text-muted">{r.checker}{r.decision_note ? `: ${r.decision_note}` : ""}</span> : null}</>}
          </td>
        </tr>))}</tbody>
    </table></div>
  );
}

export function MonitoringPage() {
  const [p, setP] = React.useState<Page | null>(null);
  const [err, setErr] = React.useState("");
  const [msg, setMsg] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    let live = true;
    void flowApi.monitoringPage().then((x) => { if (live) setP(x); }).catch((e) => { if (live) setErr(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, [nonce]);
  const decide = async (r: MonitoringProposal, approve: boolean) => {
    const note = approve ? "" : (window.prompt("Why reject? (required)") ?? "");
    if (!approve && note.trim().length < 5) return;
    setBusy(true);
    setMsg("");
    try {
      const d = await flowApi.decide(r.monitoring_proposal_id, approve, note);
      setMsg(approve ? `Approved: ${d.obligor_name || d.obligor_id} is on tier ${d.tier}.${d.applied ? ` ${d.applied}.` : ""}` : `Rejected: ${d.obligor_name || d.obligor_id}.`);
      setNonce((n) => n + 1);
    } catch (e) { setMsg(friendlyMessage(e, "Deal Desk")); } finally { setBusy(false); }
  };
  if (err) return <p role="alert" className="text-[12px] text-negative">{err}</p>;
  if (!p) return <Skeleton className="h-96 w-full" />;
  return (
    <div className="space-y-4" data-testid="monitoring-page">
      <PlainWords lines={p.plain_words} speak testId="monitoring-plain-words" />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="monitoring-counts">
        {([["Awaiting approval", p.counts.proposed], ["Active", p.counts.active], ["Reviews due in 30 days", p.counts.due_30d], ["Triggers hit", p.counts.triggers_hit]] as const).map(([l, v]) => (
          <div key={l} className="rounded-lg border border-border bg-surface px-3 py-2"><p className="text-[11px] text-text-muted">{l}</p><p className="text-[20px] font-semibold tabular-nums">{v}</p></div>))}
      </div>
      {msg ? <p className="rounded-md border border-border bg-surface px-3 py-2 text-[12px]" data-testid="monitoring-message">{msg}</p> : null}
      <Section title={`Proposed, awaiting a checker (${p.proposed.length})`} testId="monitoring-proposed"
               info="Maker-checker: a second person approves or rejects; the person who proposed cannot decide their own proposal.">
        <Rows rows={p.proposed} onDecide={(r, a) => void decide(r, a)} busy={busy} testId="monitoring-proposed-table" /></Section>
      <Section title={`Active by tier: High ${p.active_by_tier.High ?? 0} · Medium ${p.active_by_tier.Medium ?? 0} · Standard ${p.active_by_tier.Standard ?? 0}`} testId="monitoring-active">
        <Rows rows={p.active} testId="monitoring-active-table" /></Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title={`Triggers hit (${p.triggers_hit.length})`} testId="monitoring-hits"><Rows rows={p.triggers_hit} testId="monitoring-hits-table" /></Section>
        <Section title={`Reviews due in the next 30 days (${p.reviews_due.length})`} testId="monitoring-due"><Rows rows={p.reviews_due} testId="monitoring-due-table" /></Section>
      </div>
      <details className="rounded-lg border border-border bg-surface" data-testid="monitoring-history">
        <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-text-secondary">History of changes ({p.history.length})</summary>
        <div className="p-4 pt-0"><Rows rows={p.history} testId="monitoring-history-table" /></div>
      </details>
      <p className="text-[11px] text-text-muted">Source: Data Domains, deal_desk.dd_monitoring_proposal ({p.as_of}). Approved tiers also update the deal&apos;s monitoring plan (dd_monitoring_plan) or the Book facility.</p>
    </div>
  );
}

/** The line Early Warning and Borrower 360 show for a borrower proposed for or under monitoring (nothing when none). */
export function MonitoringLine({ obligorId, className }: { obligorId: string | null | undefined; className?: string }) {
  const [m, setM] = React.useState<ObligorMonitoring | null>(null);
  React.useEffect(() => {
    let live = true;
    if (!obligorId) return;
    void flowApi.obligorMonitoring(obligorId).then((x) => { if (live) setM(x); }).catch(() => null);
    return () => { live = false; };
  }, [obligorId]);
  if (!m?.line) return null;
  const tier = (m.active ?? m.proposed)?.tier ?? "";
  return (
    <p className={cn("flex flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] text-text-secondary", className)}
       data-testid="monitoring-line" data-status={m.active ? "active" : "proposed"}>
      <Eye size={12} aria-hidden className="text-accent" /><Chip tone={TIER_TONE[tier] ?? "neutral"}>{m.active ? `Monitoring ${tier}` : `Proposed ${tier}`}</Chip>
      <span className="min-w-0 flex-1">{m.line}</span>
    </p>
  );
}
