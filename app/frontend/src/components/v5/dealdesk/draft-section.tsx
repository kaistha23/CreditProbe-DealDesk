"use client";

/**
 * PLAN_R11 Session P (P5): one drafted section: its text with every figure's citation (hover for the source), the house
 * table, regenerate / edit / accept, and the nearest exemplar sections it was drafted against (in the (i)).
 */

import * as React from "react";
import { Check, Pencil, RefreshCw } from "lucide-react";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { cn } from "@/lib/utils";
import { type DraftSection, type Fact, citedFacts, methodLabel, sectionText, sectionTone, splitCitations } from "@/lib/v5/dealdesk-draft";

import { Chip, PrimaryButton, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

function Cite({ id, fact }: { id: string; fact?: Fact }) {
  const title = fact ? `${fact.label}: ${fact.display} · ${fact.source}${fact.derived ? ` (${fact.derived})` : ""}` : id;
  return (
    <sup className="mx-0.5 cursor-help rounded bg-accent-muted px-1 text-[10px] font-medium text-accent" title={title} data-testid="draft-cite">{id}</sup>
  );
}

function Line({ text, facts }: { text: string; facts: Map<string, Fact> }) {
  return (
    <>{splitCitations(text).map((s, i) => (s.kind === "text" ? <React.Fragment key={i}>{s.text}</React.Fragment> : <Cite key={i} id={s.id} fact={facts.get(s.id)} />))}</>
  );
}

export function DraftSectionCard({ s, index, busy, spinning, onRegenerate, onAccept, onSave, focused }: {
  s: DraftSection; index: number; busy: boolean; spinning?: boolean; focused?: boolean;
  onRegenerate: () => void; onAccept: (accept: boolean) => void; onSave: (text: string) => Promise<boolean>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState("");
  const facts = React.useMemo(() => new Map(s.citations.map((f) => [f.id, f])), [s.citations]);
  const cited = citedFacts(s);
  const accepted = s.status === "accepted";
  const ref = React.useRef<HTMLElement>(null);
  React.useEffect(() => { if (focused) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [focused]);
  const empty = !s.paragraphs.length && !s.bullets.length && !s.table?.rows.length;
  return (
    <article ref={ref} data-testid={`draft-section-${s.key}`} data-status={s.status}
             className={cn("rounded-lg border bg-surface p-3", accepted ? "border-positive/40" : focused ? "border-accent" : "border-border")}>
      <header className="mb-2 flex min-h-8 flex-wrap items-center gap-2">
        <h3 className="min-w-0 truncate text-[13px] font-semibold text-text-primary">{index}. {s.heading}</h3>
        <InfoPopover title={s.heading}>
          <p>Drafted section by section from data in the house style: {methodLabel(s.method).toLowerCase()}. Every figure carries its fact
            reference; hover a reference for the figure&apos;s source.</p>
          {s.exemplars.length ? (
            <p className="mt-1.5">Nearest house sections used for wording (never for facts): {s.exemplars.map((e) =>
              `${e.doc_id}${e.primary ? " (primary exemplar)" : ""} ${Math.round(e.similarity * 100)}%`).join(", ")}.</p>
          ) : <p className="mt-1.5">No comparable house section with prose; the house profile alone sets the wording.</p>}
        </InfoPopover>
        {s.judgement ? <Chip tone="accent" title="The RM's judgement: drafted as a suggestion to accept or change">RM judgement · suggestion</Chip> : null}
        {accepted ? <Chip tone="positive"><Check size={12} /> Accepted</Chip> : null}
        {s.score !== undefined ? <Chip tone={sectionTone(s.score)} title="Style score of this section against the house">Style {Math.round(s.score)}</Chip> : null}
        <div className="ml-auto flex items-center gap-1.5">
          <SecondaryButton onClick={onRegenerate} disabled={busy || editing} data-testid={`draft-regenerate-${s.key}`} aria-label={`Regenerate ${s.heading}`}>
            <RefreshCw size={13} className={spinning ? "animate-spin" : undefined} /> Regenerate</SecondaryButton>
          <SecondaryButton onClick={() => { setText(sectionText(s)); setEditing(true); }} disabled={busy || editing} data-testid={`draft-edit-${s.key}`}>
            <Pencil size={13} /> Edit</SecondaryButton>
          <SecondaryButton onClick={() => onAccept(!accepted)} disabled={busy || editing} data-testid={`draft-accept-${s.key}`}
                           className={accepted ? undefined : "border-positive/40 text-positive"}>
            <Check size={13} /> {accepted ? "Undo accept" : "Accept"}</SecondaryButton>
        </div>
      </header>
      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(12, Math.max(4, text.split("\n").length + 1))}
                    className="w-full rounded-md border border-border bg-surface px-2.5 py-2 text-[12.5px] leading-relaxed text-text-primary focus:border-accent focus:outline-none"
                    aria-label={`Edit ${s.heading}`} data-testid={`draft-textarea-${s.key}`} />
          <p className="flex items-center gap-1 text-[11px] text-text-muted">Editing tips<InfoPopover title="Editing">One paragraph per line; start a line with &quot;- &quot; for a bullet. Keep [F..] references on figures. Your edit teaches the house profile.</InfoPopover></p>
          <div className="flex gap-2">
            <PrimaryButton onClick={() => { void onSave(text).then((ok) => { if (ok) setEditing(false); }); }} disabled={busy} data-testid={`draft-save-${s.key}`}>Save edit</PrimaryButton>
            <SecondaryButton onClick={() => setEditing(false)}>Cancel</SecondaryButton>
          </div>
        </div>
      ) : (
        <div className={cn("text-[12.5px] leading-relaxed text-text-primary", s.judgement && !accepted ? "rounded-md border border-dashed border-accent/40 bg-accent-muted/30 px-2.5 py-2" : "")}>
          {empty ? <p className="text-text-muted">The data has nothing for this section; the RM completes it.</p> : null}
          {s.paragraphs.map((p, i) => <p key={i} className="mb-1.5 last:mb-0"><Line text={p} facts={facts} /></p>)}
          {s.bullets.length ? <ul className="mb-1.5 list-disc pl-5">{s.bullets.map((b, i) => <li key={i}><Line text={b} facts={facts} /></li>)}</ul> : null}
          {s.figure_checks?.length ? <p role="alert" className="mt-1 text-[11px] text-negative">{s.figure_checks[0]}</p> : null}
        </div>
      )}
      {s.table && s.table.rows.length ? (
        <div className="mt-2 max-w-full overflow-x-auto">
          <table className={tableCls} data-testid={`draft-table-${s.key}`}>
            <thead><tr>{s.table.header.map((h, i) => <th key={i} className={cn(thCls, i > 0 && "text-right")}>{h}</th>)}</tr></thead>
            <tbody>{s.table.rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j} className={cn(tdCls, j > 0 && "text-right", j === 0 && "whitespace-normal")}>{c}</td>)}</tr>
            ))}</tbody>
          </table>
          {s.table.cites.length ? <p className="mt-1 text-[11px] text-text-muted">Source: {s.table.cites.map((id) => <Cite key={id} id={id} fact={facts.get(id)} />)}</p> : null}
        </div>
      ) : null}
      {cited.length ? (
        <details className="mt-2 text-[11px] text-text-muted">
          <summary className="cursor-pointer select-none">Sources · {cited.length} figure{cited.length === 1 ? "" : "s"}</summary>
          <ul className="mt-1 flex flex-col gap-0.5">{cited.map((f) => (
            <li key={f.id} className="truncate" title={f.source}><span className="font-medium text-accent">{f.id}</span> {f.label}: {f.display} · {f.source}{f.derived ? ` (${f.derived})` : ""}</li>
          ))}</ul>
        </details>
      ) : null}
    </article>
  );
}
