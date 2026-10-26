"use client";

/**
 * Deal Desk "Prepare for committee" (PLAN_R11_AGENTS G3). Session M mounts
 *
 *   <PrepareForCommitteeButton proposalId={id} />
 *
 * in the deal header next to the existing actions. It runs the "Committee Preparation" agent and opens
 * the shared AgentRunDrawer; the committee pack renders inside it (answer first), with the Word exports
 * through the existing report pattern (the committee pack, the review decision sheet, the house-style draft).
 */

import * as React from "react";
import { FileText } from "lucide-react";

import { AgentRunButton } from "@/components/v5/core/agent-run";
import { Chip } from "@/components/v5/dealdesk/kit";
import { type AgentRun, agentsOrigin } from "@/lib/v5/agents";
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import { type CommitteePack, packFigure, packTone } from "@/lib/v5/agents-committee";

export const COMMITTEE_AGENT = "dealdesk.committee";

export function PrepareForCommitteeButton({ proposalId, label = "Prepare for committee" }: { proposalId: string; label?: string }) {
  return (
    <AgentRunButton agent={COMMITTEE_AGENT} goal={`Prepare ${proposalId} for committee`} context={{ proposal_id: proposalId }}
                    label={label} primary={false} renderOutput={(run) => <CommitteePackView run={run} />}
                    testId="prepare-for-committee" />
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 py-1 text-[12px]">
      <span className="text-text-muted">{label}</span>
      <span className="min-w-0 text-text-primary">{children}</span>
    </div>
  );
}

function Doc({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[12px] text-text-secondary hover:bg-surface-hover">
      <FileText className="h-3.5 w-3.5" />{children}
    </a>
  );
}

export function CommitteePackView({ run }: { run: AgentRun }) {
  const pack = run.output as unknown as CommitteePack;
  if (!pack?.decision) return null;
  const cp = pack.counter_proposal;
  return (
    <section className="border-t border-border px-4 py-3" data-testid="committee-pack">
      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Committee pack</h3>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Chip tone={packTone(pack.decision)} testId="committee-decision">{pack.decision}</Chip>
        {pack.doa?.level ? <Chip>{pack.doa.level}</Chip> : null}
      </div>
      {pack.why?.length ? (
        <ul className="mb-2 list-disc pl-5 text-[12px] text-text-secondary">
          {pack.why.map((w, i) => <li key={i}>{w.text} <span className="text-text-muted">({w.evidence.join(", ")})</span></li>)}
        </ul>
      ) : null}
      <div className="divide-y divide-border">
        {cp ? (
          <Row label="Counter-proposal">
            <span className="font-medium">{cp.label}</span>: RAROC {packFigure(cp.raroc, "pct")}
            {cp.sva != null ? `, SVA ${packFigure(cp.sva, "m")}` : ""}{cp.ecl != null ? `, Day-1 ECL ${packFigure(cp.ecl, "m3")}` : ""}
            {cp.conditions?.length ? <span className="block text-text-secondary">{cp.conditions.filter(Boolean).slice(0, 4).join("; ")}</span> : null}
          </Row>
        ) : null}
        {pack.forward_risk ? <Row label="Forward risk">{pack.forward_risk.answer}</Row> : null}
        {pack.stress ? <Row label="Stress">{pack.stress.answer}</Row> : null}
        <Row label="Pipeline fit">{pack.pipeline?.answer ?? "Not run"}</Row>
        {pack.precedent ? <Row label="Precedent">{pack.precedent.summary}</Row> : null}
        {pack.conditions?.length ? (
          <Row label="Conditions">
            <ul className="space-y-0.5">{pack.conditions.slice(0, 8).map((c) => <li key={c.id}>{c.what} <span className="text-text-muted">· {c.owner} · {c.due}</span></li>)}</ul>
            {pack.conditions.length > 8 ? <span className="text-text-muted">and {pack.conditions.length - 8} more</span> : null}
          </Row>
        ) : null}
        {pack.open_questions?.length ? (
          <Row label="Questions for the RM">
            <ul className="space-y-0.5">{pack.open_questions.slice(0, 6).map((q, i) => <li key={i}>{q.question}</li>)}</ul>
          </Row>
        ) : null}
        {pack.not_verified?.length ? (
          <Row label="Not verified">
            <ul className="space-y-0.5 text-text-secondary">{pack.not_verified.slice(0, 6).map((x, i) => <li key={i}>{x.item}: {x.reason}</li>)}</ul>
          </Row>
        ) : null}
        <Row label="Time taken">{packFigure((pack.timing?.run_ms ?? run.duration_ms) / 1000, "s")}</Row>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Doc href={`${agentsOrigin()}/api/v1/agents/runs/${encodeURIComponent(run.run_id)}/pack.docx`}>Committee pack (Word)</Doc>
        {pack.review_sheet_docx ? <Doc href={`${dealdeskOrigin()}${pack.review_sheet_docx}`}>Decision sheet</Doc> : null}
        {pack.draft?.docx ? <Doc href={`${dealdeskOrigin()}${pack.draft.docx}`}>House-style draft{pack.draft.score?.total != null ? ` (style ${pack.draft.score.total})` : ""}</Doc> : null}
      </div>
    </section>
  );
}
