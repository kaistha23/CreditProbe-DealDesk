"use client";

/**
 * R14 session p (K31, D1): the "Proposal check" step — the quality of the RM's paper, separate from the quality of the deal.
 * Upload the RM's Word proposal (or try the demo proposal), and the check grades it: completeness against the 20-section
 * bank form, accuracy of every claim against Data Domains, internal consistency, disclosure, voice, policy and T&C gaps.
 * Output: score by section, the defects with the bank's evidence, the annotated Word (comments in the margin), the query
 * list and "Send back to RM".
 *
 *   <ProposalCheckStep proposalId="R14-RWQ" />          // data-testid="dealdesk-step-proposal-check" (session f places the step)
 */

import * as React from "react";
import { CheckCircle2, Download, FileUp, Loader2, Send, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import { PlainWords } from "@/components/v5/ui/plain-words";

import { Chip, PrimaryButton, SecondaryButton, Section } from "../kit";
import { errorText, fileHref, getJson } from "../papers/paper-view";
import { CATEGORY_LABEL, type CheckFinding, type CheckResult, type SectionDetail, CHECK_API, checkPlainWords, checkUrls, noProposalState, scoreTone, SEVERITY_TONE } from "./model";
import { PrepareProposalButton } from "./credit-proposal";
import { ProposalDocButton, RmBrief } from "./rm-brief";
import { DealDeskError } from "@/lib/v5/dealdesk";

const DEMO_ID = "R14-RWQ"; // the sample deal of the proposal-check pack

async function upload(file: File, pid?: string): Promise<CheckResult> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${dealdeskOrigin()}${CHECK_API.upload(pid)}`, { method: "POST", body: fd, credentials: "include" });
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error((body && typeof body.detail === "string" ? body.detail : "") || "The proposal could not be checked.");
  return body as CheckResult;
}

export function ProposalCheckStep({ proposalId, onDone, onNext }: { proposalId: string; onDone?: (r: CheckResult) => void; onNext?: () => void }) {
  const [res, setRes] = React.useState<CheckResult | null>(null);
  const [busy, setBusy] = React.useState<string>("");
  const [error, setError] = React.useState("");
  const [sent, setSent] = React.useState("");
  const [cat, setCat] = React.useState<string>("");
  const fileRef = React.useRef<HTMLInputElement>(null);
  const urls = checkUrls(proposalId);
  const isDemo = proposalId === DEMO_ID;

  const [none, setNone] = React.useState(false);  // R15 b (L7): nothing on file to check: no spinner, a plain state
  const [renewal, setRenewal] = React.useState(false);
  React.useEffect(() => { try { setRenewal(new URLSearchParams(window.location.search).has("renewal")); } catch { /* no URL */ } }, []);
  const run = React.useCallback((p: Promise<CheckResult>, what: string) => {
    setBusy(what);
    setError("");
    setSent("");
    p.then((r) => { setRes(r); setNone(false); onDone?.(r); }, (e: unknown) => {
      if (what === "load" && e instanceof DealDeskError && e.status === 404) setNone(true);
      else setError(errorText(e));
    }).finally(() => setBusy(""));
  }, [onDone]);

  React.useEffect(() => {  // what is on file (an earlier upload, the memo, or the submission record)
    run(getJson<CheckResult>(urls.run), "load");
  }, [urls.run, run]);

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) run(upload(f, proposalId), "upload");
    e.target.value = "";
  };
  const sendBack = () => {
    setBusy("send");
    getJson<{ message: string }>(urls.sendBack, { method: "POST", body: JSON.stringify({ to: res?.rm }) })
      .then((x) => setSent(x.message), (e: unknown) => setError(errorText(e))).finally(() => setBusy(""));
  };

  const defects = (res?.defects ?? []).filter((d) => !cat || d.category === cat);
  return (
    <Section title="Proposal check" testId="dealdesk-proposal-check"
             info="Grades the RM's paper, not the deal: completeness against the 20-section bank form, every claim checked against Data Domains, totals recomputed, undisclosed facts found, vague claims flagged. Deterministic rules; no model."
             >
      <div className="mb-3 flex flex-wrap gap-2" data-testid="dealdesk-proposal-check-actions">
               <input ref={fileRef} type="file" accept=".docx" className="hidden" onChange={onFile} data-testid="dealdesk-proposal-check-file" />
               <PrimaryButton onClick={() => fileRef.current?.click()} disabled={!!busy} data-testid="dealdesk-proposal-check-upload" data-tour="proposal-check-upload"
                              className={none && !res ? "hidden" : undefined}>
                 {busy === "upload" ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />} Upload the RM&apos;s proposal (Word)</PrimaryButton>
               {isDemo ? (<>
                 <SecondaryButton onClick={() => run(getJson<CheckResult>(urls.demo("half"), { method: "POST" }), "half")} disabled={!!busy} data-testid="dealdesk-proposal-check-demo-half">
                   Sample RM proposal (half-baked)</SecondaryButton>
                 <SecondaryButton onClick={() => run(getJson<CheckResult>(urls.demo("corrected"), { method: "POST" }), "corrected")} disabled={!!busy} data-testid="dealdesk-proposal-check-demo-corrected">
                   Sample RM proposal (corrected)</SecondaryButton></>) : null}
      </div>
      {error ? <p role="alert" className="mb-2 text-[12px] text-negative">{error}</p> : null}
      {!res && none ? (() => {
        const st = noProposalState(renewal);
        return (
          <div className="space-y-2 rounded-md border border-border bg-surface-sunken px-4 py-3" data-testid="dealdesk-proposal-check-none">
            <p className="text-[13px] font-medium text-text-primary">{st.title}</p>
            <p className="text-[12px] text-text-secondary">{st.line}</p>
            <div className="flex flex-wrap gap-2">
              <SecondaryButton onClick={() => fileRef.current?.click()} disabled={!!busy} data-testid="dealdesk-proposal-check-none-upload"><FileUp size={13} /> {st.actions[0].label}</SecondaryButton>
              <SecondaryButton onClick={() => run(getJson<CheckResult>(urls.record), "record")} disabled={!!busy} data-testid="dealdesk-proposal-check-use-record">
                {busy === "record" ? <Loader2 size={13} className="animate-spin" /> : null} {st.actions[1].label}</SecondaryButton>
              <PrepareProposalButton proposalId={proposalId} label={st.actions[2].label} primary testId="dealdesk-proposal-check-draft-from-data" />
            </div>
          </div>);
      })() : !res && !error ? (
        <div className="flex items-center gap-2 py-6 text-[12px] text-text-muted"><Loader2 size={14} className="animate-spin" /> Checking the proposal on file…</div>
      ) : !res ? null : (
        <div className="space-y-4" data-testid="dealdesk-proposal-check-result" data-score={res.score} data-defects={res.defects.length}>
          <PlainWords lines={checkPlainWords(res)} speak testId="dealdesk-proposal-check-plain" />
          {/* R15 b (L11 (1)): the one-page brief of all issues for the RM, at the top */}
          <RmBrief res={res} sendBackUrl={urls.sendBack} />
          <div className="flex flex-wrap items-center gap-3">
            <div className={cn("flex size-[68px] shrink-0 flex-col items-center justify-center rounded-lg border",
              scoreTone(res.score) === "positive" ? "border-positive/40 bg-positive-muted text-positive" : scoreTone(res.score) === "warning" ? "border-warning/40 bg-warning-muted text-warning" : "border-negative/40 bg-negative-muted text-negative")}
                 data-testid="dealdesk-proposal-check-score">
              <span className="text-[22px] font-bold leading-6 tabular-nums">{Math.round(res.score)}</span><span className="text-[10px] font-semibold">grade {res.grade}</span></div>
            <div className="min-w-[240px] flex-1">
              <p className="text-[13px] font-medium text-text-primary">{res.headline}</p>
              <p className="text-[11px] text-text-muted">Checked: {res.document}{res.document_kind === "record" ? " (no Word on file: the RM's submission record)" : ""} · {res.checks_n} checks against Data Domains as at {res.as_of} · {res.elapsed_s.toFixed(1)} s · run {res.run_id}</p>
            </div>
            <div className="flex w-full flex-wrap gap-2">
              <ProposalDocButton res={res} />
              <a href={fileHref(res.links.annotated)} data-testid="dealdesk-proposal-check-annotated"><SecondaryButton><Download size={13} /> Annotated Word</SecondaryButton></a>
              <a href={fileHref(res.links.queries)} data-testid="dealdesk-proposal-check-queries-docx"><SecondaryButton><Download size={13} /> Query list</SecondaryButton></a>
              <PrimaryButton onClick={sendBack} disabled={!!busy || !res.queries.length} data-testid="dealdesk-proposal-check-send-back">
                {busy === "send" ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Send back to RM ({res.queries.length})</PrimaryButton>
              {onNext ? <SecondaryButton className="h-9" onClick={onNext} data-testid="dealdesk-proposal-check-next">Review the deal →</SecondaryButton> : null}
            </div>
          </div>
          {sent || res.sent.length ? (
            <p className="text-[12px] text-positive" data-testid="dealdesk-proposal-check-sent"><CheckCircle2 size={13} className="mr-1 inline" />
              {sent || `${res.sent.length} send-back(s) on file, last to ${res.sent[res.sent.length - 1].to} on ${res.sent[res.sent.length - 1].at.slice(0, 10)}.`}</p>) : null}

          <SectionScores res={res} proposalId={proposalId} />

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-1.5" data-testid="dealdesk-proposal-check-categories">
              <button type="button" onClick={() => setCat("")} className={cn("h-6 rounded-full border px-2 text-[11px]", !cat ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>
                All defects {res.defects.length}</button>
              {Object.entries(res.by_category).filter(([, n]) => n > 0).map(([k, n]) => (
                <button key={k} type="button" onClick={() => setCat(k === cat ? "" : k)} data-testid={`dealdesk-proposal-check-cat-${k}`}
                        className={cn("h-6 rounded-full border px-2 text-[11px]", cat === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>
                  {CATEGORY_LABEL[k] ?? k} {n}</button>))}
            </div>
            {defects.length ? (
              <ol className="space-y-2" data-testid="dealdesk-proposal-check-defects">
                {defects.map((d) => <DefectRow key={d.n} d={d} sections={res.sections} />)}
              </ol>) : <p className="text-[12px] text-positive"><CheckCircle2 size={13} className="mr-1 inline" /> No defect in this category.</p>}
            {res.observations.length ? (
              <details className="rounded-md border border-border px-3 py-2 text-[12px]" data-testid="dealdesk-proposal-check-observations">
                <summary className="cursor-pointer text-text-secondary">{res.observations.length} minor observations (voice, thin sections)</summary>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-text-secondary">{res.observations.map((o) => <li key={o.n}>{o.title}{o.claim ? ` — “${o.claim}”` : ""}</li>)}</ul>
              </details>) : null}
          </div>
        </div>)}
    </Section>
  );
}

function DefectRow({ d, sections }: { d: CheckFinding; sections: CheckResult["sections"] }) {
  const s = sections.find((x) => x.key === d.section_key);
  return (
    <li className="rounded-md border border-border bg-surface px-3 py-2" data-testid="dealdesk-proposal-check-defect" data-defect={d.defect_type}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={SEVERITY_TONE[d.severity]}>{d.severity === "critical" ? <ShieldAlert size={11} /> : null}{d.severity}</Chip>
        <Chip>{CATEGORY_LABEL[d.category] ?? d.category}</Chip>
        {s ? <span className="text-[11px] text-text-muted">Section {s.n} · {s.heading}</span> : null}
      </div>
      <p className="mt-1 text-[12.5px] font-medium text-text-primary">{d.title}</p>
      {d.claim ? <p className="mt-0.5 border-l-2 border-warning/60 pl-2 text-[11.5px] italic text-text-secondary">The proposal says: “{d.claim}”</p> : null}
      {d.evidence ? <p className="mt-0.5 text-[11.5px] text-text-secondary"><span className="font-medium text-text-primary">Bank data:</span> {d.evidence}
        {d.evidence_relation ? <span className="ml-1 text-[10.5px] text-text-muted">({d.evidence_relation}{d.evidence_key ? ` · ${d.evidence_key}` : ""})</span> : null}</p> : null}
      {d.query ? <p className="mt-0.5 text-[11.5px] text-accent"><span className="font-medium">Query to RM:</span> {d.query}</p> : null}
    </li>
  );
}


/** R15 b (L10): the 20 section rows, each one opens its detail (requirement, the RM's text, every check, why, queries). */
function SectionScores({ res, proposalId }: { res: CheckResult; proposalId: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const sd = res.section_detail;
  const sec = res.sections.find((s) => s.key === open) ?? null;
  const d: SectionDetail | undefined = open ? sd?.sections[open] : undefined;
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Score by section</p>
      {sd?.summary ? <p className="mb-1.5 text-[12px] text-text-primary" data-testid="dealdesk-proposal-check-section-summary">{sd.summary}.</p> : null}
      <div className="grid grid-cols-5 gap-1.5 lg:grid-cols-10" data-testid="dealdesk-proposal-check-sections">
        {res.sections.map((s) => (
          <button key={s.key} type="button" onClick={() => setOpen(open === s.key ? null : s.key)} aria-expanded={open === s.key}
                  title={`${s.n}. ${s.heading}: ${s.present ? `${s.score.toFixed(0)}/100, ${s.defects} defects` : s.applicable ? "missing" : "not applicable"} · open the detail`}
                  data-testid={`dealdesk-proposal-check-section-${s.key}`}
                  className={cn("rounded-md border px-1.5 py-1 text-left text-[10.5px] hover:ring-1 hover:ring-accent/50", open === s.key && "ring-2 ring-accent",
                    !s.applicable ? "border-border text-text-muted" : !s.present ? "border-negative/50 bg-negative-muted text-negative"
                      : s.score >= 95 ? "border-positive/30 bg-positive-muted text-positive" : s.score >= 60 ? "border-warning/40 bg-warning-muted text-warning" : "border-negative/40 bg-negative-muted text-negative")}>
            <div className="flex items-baseline justify-between gap-1"><span className="font-semibold tabular-nums">{s.n}</span>
              <span className="tabular-nums">{!s.applicable ? "n/a" : s.present ? s.score.toFixed(0) : "missing"}</span></div>
            <div className="truncate">{s.heading}</div>
          </button>))}
      </div>
      {sec ? (
        <div className="mt-2 space-y-2 rounded-md border border-border bg-surface px-4 py-3 text-[12px]" data-testid="dealdesk-proposal-check-section-detail" data-section={sec.key}>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-semibold text-text-primary">{sec.n}. {sec.heading}</p>
            <Chip tone={!sec.applicable ? undefined : !sec.present ? "negative" : sec.score >= 95 ? "positive" : "warning"}>
              {!sec.applicable ? "n/a" : sec.present ? `${sec.score.toFixed(0)}/100` : "missing"}</Chip>
            <div className="ml-auto flex gap-2">
              {d?.draft_from_data !== false ? <PrepareProposalButton proposalId={proposalId} section={sec.key} label="Draft this section from data" primary={false} small
                                                                     testId="dealdesk-proposal-check-section-draft" /> : null}
              <SecondaryButton className="h-7 px-2" onClick={() => setOpen(null)} aria-label="Close the section detail">Close</SecondaryButton>
            </div>
          </div>
          {!d ? <p className="text-text-muted">Re-run the check to see this section&apos;s detail.</p> : (<>
            <p className="font-medium text-text-primary" data-testid="dealdesk-proposal-check-section-why">{d.why}</p>
            <div><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">What the bank form requires</p><p className="text-text-secondary">{d.requires}</p></div>
            {sec.applicable ? (
              <div><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">What the RM&apos;s proposal says</p>
                {d.quote.length ? d.quote.map((q, i) => <blockquote key={i} className="border-l-2 border-border pl-2 italic text-text-secondary">{q}</blockquote>)
                  : <p className="text-negative">Nothing: the section is not in the paper.</p>}
                {d.quote_more ? <p className="text-[11px] text-text-muted">and {d.quote_more} more paragraph{d.quote_more > 1 ? "s" : ""}</p> : null}</div>) : null}
            {d.checks.length ? (
              <div><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Checks run on this section</p>
                <ul className="space-y-1" data-testid="dealdesk-proposal-check-section-checks">
                  {d.checks.map((c, i) => (
                    <li key={i} className="flex gap-2">
                      <Chip tone={c.result === "pass" ? "positive" : c.result === "observation" ? undefined : SEVERITY_TONE[c.severity as keyof typeof SEVERITY_TONE] ?? "warning"}>
                        {c.result === "pass" ? "pass" : c.result === "observation" ? "note" : c.severity}</Chip>
                      <span className="min-w-0"><span className="text-text-primary">{c.title}</span>
                        {c.evidence ? <span className="block text-[11px] text-text-muted">{c.evidence}{c.source ? ` (Data Domains: ${c.source}${c.key ? `, ${c.key}` : ""})` : ""}</span> : null}</span>
                    </li>))}
                </ul></div>) : null}
            {d.queries.length ? (
              <div><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Query to the RM</p>
                {d.queries.map((q, i) => <p key={i} className="text-text-secondary">{q}</p>)}</div>) : null}
          </>)}
        </div>) : null}
    </div>
  );
}
