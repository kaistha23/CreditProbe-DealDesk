"use client";

/**
 * R14 session p (K26, K27, D15): "Prepare the credit proposal" — the full bank-form credit proposal built from the selected
 * structure and the whole deal file, previewed page by page as in the Word/PDF (header block on every page, part banners for
 * the two voices, ruled boxes, key concerns underlined), with a section navigator and the Word and PDF downloads.
 *
 *   <PrepareProposalButton proposalId="R12-TWA" structureKey={selectedKey} />      // data-testid="dealdesk-prepare-proposal"
 *   <CreditProposalPreview proposalId="R12-TWA" structure={selectedKey} />          // the preview alone (dialog body)
 *
 * Session f places the button on the Recommendation step; it passes the selected structure's key (else the backend uses
 * the deal's selected structure, defaulting to the Review counter-proposal).
 */

import * as React from "react";
import { RulesApplied } from "@/components/v5/rules/rules-applied";  // Round K
import type { RuleApplied } from "@/lib/v5/dealdesk-rules";
import { Download, FileText, Loader2, RefreshCw, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { PlainWords } from "@/components/v5/ui/plain-words";

import { Chip, PrimaryButton, SecondaryButton } from "../kit";
import { errorText, fileHref, getJson } from "../papers/paper-view";
import { BlockView } from "./blocks";
import { useOpenPaper } from "../paperws/open";
import { type CreditProposal, PROPOSAL_TIMEOUT_MS, pageCards, pct, proposalTimeoutText, proposalUrls, sectionLabel, voiceOf, writingLine } from "./model";

const BOXED = new Set(["action", "recommendation"]);


export function PrepareProposalButton({ proposalId, structureKey, label = "Prepare the credit proposal", primary = true, testId = "dealdesk-prepare-proposal", section, small = false }: {
  proposalId: string; structureKey?: string | null; label?: string; primary?: boolean; testId?: string;
  /** R15 b (L10): open the proposal at this section ("Draft this section from data"). */
  section?: string; small?: boolean;
}) {
  // Round W: the button opens the proposal workspace (the document with Noor beside it, versions, Word/PDF); the deal's
  // latest workspace is reopened, else version 1 is written on this structure.
  const { open, busy, error } = useOpenPaper();
  const B = primary ? PrimaryButton : SecondaryButton;
  return (
    <>
      <B onClick={() => void open("proposal", { proposalId, structure: structureKey, section })} disabled={busy} className={small ? "h-7 px-2 text-[11.5px]" : undefined}
         data-testid={testId} data-tour={testId === "dealdesk-prepare-proposal" ? "prepare-proposal" : undefined}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} {busy ? "Opening the document…" : label}</B>
      {error ? <span role="alert" className="text-[11px] text-negative" data-testid={`${testId}-error`}>{error}</span> : null}
    </>
  );
}

export function ProposalDialog({ onClose, children, testId = "dealdesk-credit-proposal-dialog", label = "Credit proposal" }: {
  onClose: () => void; children: React.ReactNode; testId?: string; label?: string;
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={label} data-testid={testId} className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-3" onClick={onClose}>
      <div className="relative flex h-[calc(100vh-1.5rem)] w-full max-w-[1320px] flex-col overflow-hidden rounded-xl bg-surface-sunken shadow-xl" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onClose} aria-label="Close" data-testid={`${testId}-close`}
                className="absolute right-3 top-3 z-10 inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={15} /></button>
        {children}
      </div>
    </div>
  );
}

export function CreditProposalPreview({ proposalId, structure, section }: { proposalId: string; structure?: string | null; section?: string }) {
  const urls = proposalUrls(proposalId, structure);
  const [p, setP] = React.useState<CreditProposal | null>(null);
  const [error, setError] = React.useState("");
  const [active, setActive] = React.useState("header");
  const scroller = React.useRef<HTMLDivElement>(null);

  const [attempt, setAttempt] = React.useState(0);
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    // R15 b (L12): never an endless wait. The bank-form writer is deterministic (no model); a request that takes longer
    // than the limit is stopped and the reason is shown with a retry.
    let live = true;
    const ctl = new AbortController();
    const started = Date.now();
    setP(null);
    setError("");
    setElapsed(0);
    const tick = window.setInterval(() => { if (live) setElapsed(Math.round((Date.now() - started) / 1000)); }, 1000);
    const limit = window.setTimeout(() => ctl.abort(), PROPOSAL_TIMEOUT_MS);
    getJson<CreditProposal>(urls.prepare, { signal: ctl.signal }).then((x) => { if (live) setP(x); }, (e: unknown) => {
      if (!live) return;
      setError(ctl.signal.aborted ? proposalTimeoutText(PROPOSAL_TIMEOUT_MS) : errorText(e));
    }).finally(() => { window.clearInterval(tick); window.clearTimeout(limit); });
    return () => { live = false; ctl.abort(); window.clearInterval(tick); window.clearTimeout(limit); };
  }, [urls.prepare, attempt]);

  const cards = React.useMemo(() => (p ? pageCards(p) : []), [p]);
  React.useEffect(() => {  // R15 b (L10): land on the section asked for once the pages are drawn
    if (!p || !section) return;
    const t = window.setTimeout(() => {
      setActive(section);
      const el = scroller.current?.querySelector(`[data-section="${section}"]`);
      if (el && "scrollIntoView" in el) (el as HTMLElement).scrollIntoView({ block: "start" });
    }, 50);
    return () => window.clearTimeout(t);
  }, [p, section]);
  const firstOf = React.useMemo(() => new Map((p?.parts ?? []).filter((x) => x.sections.length).map((x) => [x.sections[0], x] as const)), [p]);
  const go = (key: string) => {
    setActive(key);
    const el = scroller.current?.querySelector(`[data-section="${key}"]`);
    if (el && "scrollIntoView" in el) (el as HTMLElement).scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (error) {
    return (
      <div className="flex flex-col items-start gap-3 p-6" data-testid="dealdesk-credit-proposal-failed">
        <p role="alert" className="text-[13px] text-negative" data-testid="dealdesk-credit-proposal-error">The credit proposal could not be written: {error}</p>
        <SecondaryButton onClick={() => setAttempt((n) => n + 1)} data-testid="dealdesk-credit-proposal-retry"><RefreshCw size={13} /> Try again</SecondaryButton>
      </div>);
  }
  if (!p) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-[13px] text-text-muted" data-testid="dealdesk-credit-proposal-loading">
        <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={16} /> {writingLine(elapsed)}</span>
        <span className="text-[11.5px]" data-testid="dealdesk-credit-proposal-elapsed">{elapsed} s · stops with the reason after {Math.round(PROPOSAL_TIMEOUT_MS / 1000)} s</span>
      </div>);
  }
  const f = p.feed;
  return (
    <div className="flex h-full flex-col" data-testid="dealdesk-credit-proposal">
      <div className="space-y-2 border-b border-border bg-surface px-5 py-3 pr-12">
        <div className="flex flex-wrap items-center gap-2">
          <FileText size={16} className="text-accent" aria-hidden />
          <h2 className="text-[16px] font-semibold text-text-primary">Credit proposal (bank form)</h2>
          <span className="text-[12px] text-text-muted">{p.customer} · {p.proposal_id} · as at {p.as_of_label}</span>
          <div className="ml-auto flex flex-wrap gap-2">
            <a href={fileHref(urls.docx)} data-testid="dealdesk-credit-proposal-docx"><PrimaryButton><Download size={14} /> Word</PrimaryButton></a>
            <a href={fileHref(urls.pdf)} data-testid="dealdesk-credit-proposal-pdf"><SecondaryButton className="h-9"><Download size={13} /> PDF</SecondaryButton></a>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" data-testid="dealdesk-credit-proposal-chips">
          {f ? <Chip tone="accent" title={f.structure.source}>Structure: {f.structure.label}</Chip> : null}
          {f?.approval ? <Chip title={f.approval_rule ?? undefined}>Approval: {f.approval}</Chip> : null}
          {f?.raroc != null ? <Chip tone={f.hurdle != null && f.raroc >= f.hurdle - 1e-9 ? "positive" : "negative"} title={f.basis ?? undefined}>
            RAROC {pct(f.raroc)} vs {pct(f.hurdle)}</Chip> : null}
          <Chip>{p.pages.total} pages</Chip>
          <Chip tone={p.coverage.length ? "negative" : "positive"}>{p.coverage.length ? `${p.coverage.length} sections missing` : "All 20 sections"}</Chip>
          {p.gaps.length ? <Chip tone="warning" title={p.gaps.map((g) => g.heading).join(" · ")}>{p.gaps.length} with information not provided</Chip> : null}
        </div>
        <PlainWords lines={p.plain_words} speak testId="dealdesk-credit-proposal-plain" />
        <RulesApplied applied={(p as { rules_applied?: RuleApplied[] }).rules_applied} testId="dealdesk-credit-proposal-rules" />
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[230px_1fr]">
        <nav aria-label="Sections" className="min-h-0 overflow-y-auto border-r border-border bg-surface px-2 py-3" data-testid="dealdesk-credit-proposal-nav">
          <button type="button" onClick={() => go("header")} className={cn("flex w-full items-center gap-1 rounded px-2 py-1 text-left text-[11.5px]",
            active === "header" ? "bg-accent-muted text-accent" : "text-text-secondary hover:bg-surface-hover")}>
            <span className="w-7 shrink-0 tabular-nums text-text-muted">1.</span><span className="truncate">Header block</span>
            <span className="ml-auto text-[10px] text-text-muted">p. 1</span></button>
          {p.parts.map((part) => (
            <div key={part.key} className="mt-2">
              <p className="px-2 pb-0.5 text-[9.5px] font-semibold uppercase tracking-[0.1em] text-text-muted">{part.title}</p>
              {part.sections.map((k) => {
                const s = p.sections.find((x) => x.key === k);
                if (!s) return null;
                return (
                  <button key={k} type="button" onClick={() => go(k)} data-testid={`dealdesk-credit-proposal-nav-${k}`} title={s.heading}
                          className={cn("flex w-full items-center gap-1 rounded px-2 py-1 text-left text-[11.5px]",
                            active === k ? "bg-accent-muted text-accent" : "text-text-secondary hover:bg-surface-hover")}>
                    <span className="w-7 shrink-0 tabular-nums text-text-muted">{sectionLabel(p.sections, k)}</span>
                    <span className="truncate">{s.heading.replace(" (CreditProbe)", "")}</span>
                    {s.gaps.length ? <span className="size-1.5 shrink-0 rounded-full bg-warning" title={`Not provided: ${s.gaps.join(", ")}`} /> : null}
                    <span className="ml-auto shrink-0 text-[10px] text-text-muted">p. {p.pages.sections[k] ?? "–"}</span>
                  </button>);
              })}
            </div>))}
        </nav>
        <div ref={scroller} className="min-h-0 overflow-y-auto px-5 py-4" data-testid="dealdesk-credit-proposal-pages">
          <div className="mx-auto flex max-w-[1060px] flex-col gap-4">
            {cards.map((c) => (
              <article key={c.page} data-testid="dealdesk-credit-proposal-page" data-page={c.page}
                       className={cn("mx-auto w-full rounded-sm border border-border bg-surface shadow-sm", c.landscape ? "max-w-[1060px]" : "max-w-[800px]")}>
                <header className="border-b border-border px-6 pb-2 pt-3">
                  <p className="text-[9px] font-semibold tracking-[0.08em] text-text-muted"><span className="text-accent">CREDITPROBE</span> · CREDIT PROPOSAL (BANK FORM) · INTERNAL</p>
                  <div className="mt-1 grid grid-cols-4 border-l border-t border-border text-[9.5px]" data-testid="dealdesk-credit-proposal-page-header">
                    {p.header_line.map(([k, v]) => (
                      <div key={k} className="flex min-w-0 border-b border-r border-border">
                        <span className="w-[62px] shrink-0 bg-surface-sunken px-1 py-0.5 font-semibold text-text-muted">{k}</span>
                        <span className="truncate px-1 py-0.5 text-text-primary" title={v}>{v}</span></div>))}
                  </div>
                </header>
                <div className="space-y-3 px-6 py-4">
                  {c.sections.map((s) => (<React.Fragment key={s.key}>
                    {firstOf.has(s.key) ? (
                      <div className="rounded-sm bg-accent px-3 py-1.5 text-[11px] font-semibold text-accent-contrast" data-testid="dealdesk-credit-proposal-part">
                        {firstOf.get(s.key)!.title}<span className="ml-2 font-normal opacity-80">{firstOf.get(s.key)!.subtitle}</span></div>) : null}
                    <section data-section={s.key} className="scroll-mt-4 space-y-1.5">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <h4 className="text-[13px] font-semibold text-accent">{sectionLabel(p.sections, s.key)} {s.heading}</h4>
                        <span className="text-[10px] uppercase tracking-[0.06em] text-text-muted">{voiceOf(s)}</span>
                        {s.gaps.length ? <span className="text-[10px] text-warning" title={s.gaps.join(", ")}>information not provided: {s.gaps.length}</span> : null}
                      </div>
                      <div className={cn("space-y-1.5", BOXED.has(s.key) && "rounded-sm border-2 border-text-primary/70 p-3")}>
                        {s.blocks.map((b, i) => <BlockView key={i} b={b} dense />)}
                      </div>
                      {s.sources?.length ? <p className="text-[9.5px] text-text-muted">Data Domains: {s.sources.join(" · ")}</p> : null}
                    </section></React.Fragment>))}
                </div>
                <footer className="flex justify-between border-t border-border px-6 py-1.5 text-[9.5px] text-text-muted">
                  <span>CreditProbe · {p.proposal_id}-BFP</span><span>{c.to > c.page ? `Pages ${c.page}–${c.to}` : `Page ${c.page}`} of {p.pages.total}</span></footer>
              </article>))}
          </div>
        </div>
      </div>
    </div>
  );
}
