"use client";

/**
 * R14 Session F (K24, K25 (2)-(3)): the Recommendation step, never blank. Built on the selected structure (default the
 * Review counter-proposal, and it says so): the credit division's decision as numbered points with the approval authority
 * and its rule; key strengths and risks from the SWOT, each sourced; every critical and major finding with its cure;
 * conditions precedent prior to limit loading; covenants with headroom; the monitoring tier and its triggers; owners and
 * dates; the severity it was stress-proofed to. Buttons: "Prepare the credit proposal" (Session p's generator, test id
 * `dealdesk-prepare-proposal`) and the committee paper. The chat stays below (the thread).
 *
 * Also here: the one-card SWOT for the Analysis step (K25 (3)).
 */

import * as React from "react";
import { FileText, Gavel, ListChecks } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { type Recommendation, type SwotPoint, TIER_TONE, evidenceSource, flowApi, pct, sarm, swotSummary, x } from "@/lib/v5/dealdesk-flow";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";
import { Slot, hasSlot } from "./r12-slots";

function DialogShell({ label, onClose, children, testId }: { label: string; onClose: () => void; children: React.ReactNode; testId: string }) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={label} data-testid={testId} className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="relative h-[calc(100vh-2rem)] w-full max-w-[1180px] overflow-y-auto rounded-xl bg-surface-sunken p-3 pt-10 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} aria-label="Close" data-testid={`${testId}-close`}
                className="absolute right-3 top-3 z-10 inline-flex h-7 items-center rounded-md px-2 text-[12px] text-text-muted hover:bg-surface-hover">Close</button>
        {children}
      </div>
    </div>
  );
}

/** "Prepare the credit proposal" (p's generator when mounted in the PrepareProposal slot; else the bank-form writer). */
export function PrepareProposalButton({ proposalId, structureKey, terms }: { proposalId: string; structureKey: string; terms: Record<string, unknown> }) {
  const [open, setOpen] = React.useState(false);
  const close = React.useCallback(() => setOpen(false), []);
  if (hasSlot("PrepareProposal")) return <Slot name="PrepareProposal" props={{ proposalId, structureKey, terms }} />;
  return (
    <>
      <PrimaryButton onClick={() => setOpen(true)} data-testid="dealdesk-prepare-proposal" data-tour="dd-prepare-proposal" disabled={!hasSlot("WriteProposal")}
                     title={hasSlot("WriteProposal") ? "The bank-form credit proposal on this structure" : "The proposal writer is not installed"}>
        <FileText size={14} /> Prepare the credit proposal</PrimaryButton>
      {open ? <DialogShell label="Credit proposal" onClose={close} testId="dealdesk-prepare-proposal-dialog">
        <Slot name="WriteProposal" props={{ proposalId, onClose: close }} /></DialogShell> : null}
    </>
  );
}

export function CommitteePaperButton({ proposalId }: { proposalId: string }) {
  const [open, setOpen] = React.useState(false);
  const close = React.useCallback(() => setOpen(false), []);
  if (!hasSlot("CommitteePaper")) return null;
  return (
    <>
      <SecondaryButton onClick={() => setOpen(true)} data-testid="dealdesk-rec-committee-paper"><Gavel size={13} /> Committee paper</SecondaryButton>
      {open ? <DialogShell label="Committee paper" onClose={close} testId="dealdesk-rec-committee-dialog">
        <Slot name="CommitteePaper" props={{ proposalId, onClose: close }} /></DialogShell> : null}
    </>
  );
}

const CURE_TONE: Record<string, "positive" | "warning" | "negative" | "neutral"> = {
  cured_by_structure: "positive", covenant: "positive", condition_precedent: "warning", explanation: "warning", open: "negative", not_curable: "negative" };
const CURE_LABEL: Record<string, string> = {
  cured_by_structure: "Cured by the structure", covenant: "Covenant in the facility", condition_precedent: "Condition precedent", explanation: "Explanation required",
  open: "Open", not_curable: "Not curable by structure" };

export function RecommendationPanel({ proposalId, nonce = 0, onChoose }: { proposalId: string; nonce?: number; onChoose?: () => void }) {
  const want = `${proposalId}|${nonce}`;
  const [got, setGot] = React.useState<{ key: string; r: Recommendation } | null>(null);
  const [err, setErr] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void flowApi.recommendation(proposalId).then((x2) => { if (live) setGot({ key: `${proposalId}|${nonce}`, r: x2 }); })
      .catch((e) => { if (live) setErr(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, [proposalId, nonce]);
  const r = got?.key === want ? got.r : null;
  if (err) return <p role="alert" className="text-[12px] text-negative">{err}</p>;
  if (!r) return <div className="space-y-3"><PlainWords lines={[]} loading /><Skeleton className="h-72 w-full" /></div>;
  const st = r.structure;
  return (
    <div className="space-y-4" data-testid="flow-recommendation" data-structure={st.key}>
      <PlainWords lines={r.plain_words} speak testId="flow-recommendation-plain-words" />
      <Section title={`Credit division recommendation: ${st.label}`} testId="flow-rec-decision"
               info={`Built on the selected structure (${st.origin}). Approval authority from the one Delegation of Authority engine; findings and cures from the findings engine; covenants, tier and triggers from the Stress Lab on this structure.`}
               action={<div className="flex flex-wrap items-center gap-2">
                 {onChoose ? <SecondaryButton onClick={onChoose} data-testid="flow-rec-change-structure">Change structure</SecondaryButton> : null}
                 <CommitteePaperButton proposalId={proposalId} />
                 <PrepareProposalButton proposalId={proposalId} structureKey={st.key} terms={st.terms} />
               </div>}>
        {r.default_note ? <p className="mb-2 text-[12px] text-text-secondary" data-testid="flow-rec-default-note">{r.default_note} Change it on the Structure step.</p> : null}
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={r.decision.tone} testId="flow-rec-decision-chip">{r.decision.label}</Chip>
          <Chip testId="flow-rec-approval" title={[r.approval.rule, ...r.approval.reasons].join(" · ")}>{r.approval.level}</Chip>
          <span className="text-[12px] text-text-secondary">RAROC {pct(st.raroc, 2)} vs {pct(st.hurdle)} · SVA {sarm(st.sva)} · DSCR {x(st.dscr)}</span>
          {r.proofed_to ? <Chip tone="positive">Stress-proofed to {r.proofed_to}</Chip> : null}
        </div>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-[13px] text-text-primary" data-testid="flow-rec-points">
          {r.decision.points.map((p) => <li key={p}>{p}</li>)}</ol>
        <p className="mt-2 text-[11px] text-text-muted" data-testid="flow-rec-approval-rule">Approval rule: {r.approval.rule || "Delegation of Authority"}.</p>
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Key strengths" testId="flow-rec-strengths" info="From the deal's SWOT; each point names its Data Domains source.">
          <ul className="space-y-1.5 text-[12px]">{r.strengths.map((s) => <li key={s.text}>{s.text} <span className="text-text-muted">· {s.source}</span></li>)}
            {!r.strengths.length ? <li className="text-text-muted">No strength recorded in the SWOT.</li> : null}</ul>
        </Section>
        <Section title="Key risks" testId="flow-rec-risks" info="Weaknesses and threats from the deal's SWOT, each sourced.">
          <ul className="space-y-1.5 text-[12px]">{r.risks.map((s) => <li key={s.text}>{s.text} <span className="text-text-muted">· {s.source}</span></li>)}
            {!r.risks.length ? <li className="text-text-muted">No risk recorded in the SWOT.</li> : null}</ul>
        </Section>
      </div>
      <Section title={`Findings and how each is cured (${r.findings.length})`} testId="flow-rec-findings"
               info="Every open critical and major finding on the deal, with the cure on the selected structure: the structure itself, a condition precedent, an explanation, or not curable by structure.">
        <div className="overflow-x-auto"><table className={cn(tableCls, "table-fixed min-w-[760px]")}>
          <colgroup><col className="w-[9%]" /><col className="w-[36%]" /><col className="w-[17%]" /><col className="w-[38%]" /></colgroup>
          <thead><tr>{["Severity", "Finding", "Cure", "How"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.findings.map((f, i) => (
            <tr key={`${f.title}-${i}`} data-testid="flow-rec-finding" data-cure={f.cure_kind}>
              <td className={tdCls}><Chip tone={f.severity === "critical" ? "negative" : "warning"}>{f.severity === "critical" ? "Critical" : "Major"}</Chip></td>
              <td className={cn(tdCls, "whitespace-normal")}>{f.title}<span className="block text-[11px] text-text-muted">{f.source}</span></td>
              <td className={cn(tdCls, "whitespace-normal")}><Chip tone={CURE_TONE[f.cure_kind] ?? "neutral"}>{CURE_LABEL[f.cure_kind] ?? f.cure_kind}</Chip></td>
              <td className={cn(tdCls, "whitespace-normal text-text-secondary")}>{f.cure}</td>
            </tr>))}</tbody>
        </table></div>
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Conditions precedent (prior to limit loading)" testId="flow-rec-cps">
          {r.conditions_precedent.length ? (
            <ol className="list-decimal space-y-1 pl-5 text-[12px]">{r.conditions_precedent.map((c) => (
              <li key={c.text}>{c.text} <span className="text-text-muted">· {c.owner} · {c.due}</span></li>))}</ol>
          ) : <p className="text-[12px] text-text-muted">None beyond the standard documentation.</p>}
        </Section>
        <Section title="Covenants, monitoring and owners" testId="flow-rec-monitoring">
          <div className="space-y-2 text-[12px]">
            {r.covenants.length ? (
              <table className={tableCls}><thead><tr>{["Covenant", "Level", "Today", "Headroom"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
                <tbody>{r.covenants.map((c) => (
                  <tr key={c.type}><td className={tdCls}>{c.type}</td><td className={tdCls}>{x(c.threshold)}</td><td className={tdCls}>{x(c.today)}</td>
                    <td className={cn(tdCls, c.headroom != null && c.headroom < 0.1 && "text-warning", c.headroom != null && c.headroom < 0 && "text-negative")}>{c.headroom == null ? "–" : pct(c.headroom, 0)}</td></tr>))}</tbody></table>
            ) : null}
            <p><Chip tone={TIER_TONE[r.monitoring.tier] ?? "neutral"}>Tier {r.monitoring.tier}</Chip> review every {r.monitoring.review_frequency_months} months.</p>
            {r.monitoring.triggers.length ? <ul className="space-y-0.5 text-text-secondary" data-testid="flow-rec-triggers">
              {r.monitoring.triggers.slice(0, 6).map((t) => <li key={t.label}><ListChecks className="mr-1 inline size-3" aria-hidden />{t.label}</li>)}</ul> : null}
            <table className={tableCls} data-testid="flow-rec-owners"><thead><tr>{["What", "Owner", "Due"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{r.owners.map((o) => <tr key={o.what}><td className={cn(tdCls, "whitespace-normal")}>{o.what}</td><td className={tdCls}>{o.owner}</td><td className={tdCls}>{o.due}</td></tr>)}</tbody></table>
          </div>
        </Section>
      </div>
    </div>
  );
}

/** K25 (3): the SWOT in one card on the Analysis step; the full SWOT stays in More → Group & SWOT. */
export function SwotCard({ proposalId }: { proposalId: string }) {
  const [pts, setPts] = React.useState<SwotPoint[] | null>(null);
  const [err, setErr] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void flowApi.swot(proposalId).then((s) => { if (live) setPts(s.points ?? []); }).catch((e) => { if (live) setErr(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, [proposalId]);
  if (err) return null;
  if (!pts) return <Skeleton className="h-32 w-full" />;
  const s = swotSummary(pts);
  return (
    <Section title="SWOT in one card" testId="flow-swot-card" info="The strongest points of the deal's SWOT (dd_swot), each with its source; they feed Key strengths and Key risks in the Recommendation. The full SWOT is in More → Group & SWOT.">
      <PlainWords testId="flow-swot-plain-words" lines={[
        `What helps and what hurts this deal: ${s.counts.strength} strengths, ${s.counts.weakness} weaknesses, ${s.counts.opportunity} opportunities and ${s.counts.threat} threats.`,
        s.weaknesses[0] ? `The biggest concern: ${s.weaknesses[0].text}` : "No weakness recorded.",
        "These points carry into the recommendation and the committee paper.",
      ]} />
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {([["Strengths", s.strengths, "positive"], ["Weaknesses and threats", s.weaknesses, "negative"]] as const).map(([t, list, tone]) => (
          <div key={t} className="rounded-md border border-border p-3">
            <p className={cn("text-[11px] font-semibold uppercase tracking-[0.08em]", tone === "positive" ? "text-positive" : "text-negative")}>{t}</p>
            <ul className="mt-1 space-y-1 text-[12px]">{list.map((p) => <li key={p.id}>{p.text} <span className="text-text-muted">· {evidenceSource(p)}</span></li>)}</ul>
          </div>))}
      </div>
    </Section>
  );
}
