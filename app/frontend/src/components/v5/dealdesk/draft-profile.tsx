"use client";

/**
 * PLAN_R11 Session P (P1): the house style the draft follows, in brief: the structure, the number format, the voice of the
 * business unit and of the credit division, the standard phrases, what RM edits taught, and adding a proposal to the corpus.
 */

import * as React from "react";
import { FileUp } from "lucide-react";

import { type ProfileView, drafting, numberFormatLine, voiceLine } from "@/lib/v5/dealdesk-draft";

import { Chip, Section } from "./kit";

export function DraftHouseProfile({ proposalId, currency, bank, refreshKey, onLearned }: {
  proposalId: string; currency: string; bank?: string; refreshKey?: string | number; onLearned?: () => void;
}) {
  const [view, setView] = React.useState<ProfileView | null>(null);
  const [note, setNote] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    let live = true;
    drafting.profile(proposalId).then((v) => { if (live) setView(v); }, () => { if (live) setView(null); });
    return () => { live = false; };
  }, [proposalId, refreshKey]);
  const upload = async (f: File) => {
    setBusy(true);
    try {
      const own = view?.profile.group.split("|")[0];
      const r = await drafting.ingest(f, bank || (own && own !== "*" ? own : "house-uae"));
      setNote(r.summary);
      setView(await drafting.profile(proposalId));
      onLearned?.();
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  if (!view) return null;
  const p = view.profile;
  return (
    <Section title="House style" testId="draft-house-profile"
             info={<>The profile the draft follows, learned from {p.documents} of the bank&apos;s proposals{p.primary_exemplars.length ? " with the anonymised exemplar as the primary model" : ""}.
               It updates as proposals are added and as RMs edit drafts: phrases an RM writes are preferred next time, phrases an RM removes are avoided.</>}
             action={<>
               <input ref={input} type="file" accept=".docx,.md,.txt" className="hidden" data-testid="draft-corpus-input"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
               <button type="button" onClick={() => input.current?.click()} disabled={busy} aria-label="Add a proposal to the house corpus"
                       title="Add a proposal (.docx) to the house corpus" data-testid="draft-corpus-add"
                       className="inline-flex size-8 items-center justify-center rounded-md border border-border text-text-secondary hover:bg-surface-hover disabled:opacity-40">
                 <FileUp size={14} /></button>
             </>}>
      <div className="flex flex-col gap-2.5 text-[12px] text-text-secondary">
        <div>
          <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">Structure</p>
          <ol>{p.sections.map((s, i) => <li key={s.key} className="truncate" title={s.heading}><span className="tabular-nums text-text-muted">{i + 1}.</span> {s.heading}</li>)}</ol>
        </div>
        <div>
          <p className="mb-0.5 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">Numbers</p>
          <p>{numberFormatLine(p.numbers, currency, p.spelling)}</p>
        </div>
        <div>
          <p className="mb-0.5 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">Voice</p>
          <p><span className="text-text-primary">Business unit:</span> {voiceLine(p.voices.business)}</p>
          {p.voices.credit ? <p><span className="text-text-primary">Credit division:</span> {voiceLine(p.voices.credit)}</p> : null}
        </div>
        {p.phrases.length ? (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">House phrases</p>
            <div className="flex flex-wrap gap-1">{p.phrases.slice(0, 6).map((x) => <Chip key={x.text} title="@ is a name, # a figure">{x.text}</Chip>)}</div>
          </div>
        ) : null}
        {p.abbreviations.length ? <p className="truncate" title={p.abbreviations.map((a) => a.text).join(", ")}>Abbreviations: {p.abbreviations.slice(0, 8).map((a) => a.text).join(", ")}</p> : null}
        {p.edits_learned ? <p data-testid="draft-learned">{p.edits_learned} RM edit{p.edits_learned === 1 ? "" : "s"} learned{p.learned.avoid.length ? ` · ${p.learned.avoid.length} phrases avoided` : ""}</p> : null}
        {note ? <p role="status" className="text-[11px] text-text-muted" data-testid="draft-corpus-note">{note}</p> : null}
      </div>
    </Section>
  );
}
