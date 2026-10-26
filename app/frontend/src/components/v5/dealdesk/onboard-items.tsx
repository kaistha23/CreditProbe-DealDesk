"use client";

/**
 * PLAN_R11 P6: the maker-checker list. Every learned item with its source quote, the value proposed, the value in force,
 * whether the bank's data checks it, and Accept / Edit / Reject. Each accept writes the next version.
 */

import * as React from "react";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { cn } from "@/lib/utils";
import {
  type Filter, type Item, type Session, FILTERS, changeTone, countFor, editable, filterItems, fmtValue, paramLine, parseEdit,
  sourceOf, statusOf,
} from "@/lib/v5/dealdesk-onboard";

import { Chip, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

const TYPE: Record<string, string> = {
  threshold: "Threshold", condition: "Condition", committee_question: "Committee question", structure: "Structure", language: "Language",
};

function Target({ it }: { it: Item }) {
  const parts: React.ReactNode[] = [];
  if (it.rule) parts.push(<Chip key="r" tone="accent" title={`Rule ${it.rule.id} in the review rule book${it.same_as ? `; the rule book already has ${it.same_as}` : ""}`}>Rule{it.same_as ? ` = ${it.same_as}` : ""}</Chip>);
  if (it.param) parts.push(<Chip key="p" tone={changeTone(it.param.change)} title={it.param.conversion || `${it.param.table}.${it.param.row}`}>{it.param.table}: {paramLine(it.param)}</Chip>);
  if (!parts.length) parts.push(<span key="n" className="text-text-muted">{it.type === "committee_question" ? "Drafter and review" : it.type === "structure" || it.type === "language" ? "House-style drafter" : "Manual check"}</span>);
  return <div className="flex flex-wrap gap-1">{parts}</div>;
}

export function OnboardItems({ session, busy, onDecide }: {
  session: Session; busy: string; onDecide: (it: Item, action: "accept" | "edit" | "reject", value?: unknown) => void;
}) {
  const [filter, setFilter] = React.useState<Filter>("pending");
  const [edit, setEdit] = React.useState<{ id: string; text: string; err: string } | null>(null);
  const [open, setOpen] = React.useState<string | null>(null);
  const rows = filterItems(session, filter);

  const saveEdit = (it: Item) => {
    if (!edit) return;
    try { onDecide(it, "edit", parseEdit(it, edit.text)); setEdit(null); } catch (e) { setEdit({ ...edit, err: e instanceof Error ? e.message : String(e) }); }
  };

  return (
    <Section title="Learned items for the checker" testId="onboard-items"
             info={<>Every item learned from the documents, with the words it was learned from. Nothing applies until a checker accepts it:
               an accept (or an edit) writes the next version of the rule book and the parameter tables, each changed row carrying where it
               was learned from. The person who uploaded the documents cannot accept them (maker-checker).</>}>
      <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="Filter learned items">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)} data-testid={`onboard-filter-${f.key}`}
                  className={cn("h-7 rounded-full border px-3 text-[12px]", filter === f.key ? "border-accent bg-accent/10 text-text-primary" : "border-border text-text-secondary hover:bg-surface-hover")}>
            {f.label} <span className="tabular-nums text-text-muted">{countFor(session, f.key)}</span>
          </button>))}
      </div>
      {!rows.length ? <p className="text-[12px] text-text-muted">Nothing here.</p> : (
        <div className="max-h-[560px] overflow-auto">
          <table className={tableCls}>
            <thead className="sticky top-0 bg-surface"><tr>{["Clause", "What", "Learned", "Goes to", "Checked by", "Decision"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((it) => {
              const st = statusOf(session, it.id);
              const editing = edit?.id === it.id;
              return (
                <React.Fragment key={it.id}>
                  <tr data-testid="onboard-item" data-id={it.id} data-status={st}>
                    <td className={cn(tdCls, "font-medium")}>{it.clause ?? (it.type === "committee_question" ? `${it.raised_in} of ${it.of} memos` : "Memos")}</td>
                    <td className={cn(tdCls, "max-w-[300px] whitespace-normal")}>
                      <span className="inline-flex items-center gap-1">{it.type === "committee_question" ? it.question : it.label}
                        <InfoPopover title={`${TYPE[it.type] ?? it.type}: source`}>
                          <p className="italic">“{it.quote}”</p><p className="mt-2 text-text-muted">{sourceOf(it)}</p>
                          {it.conflict ? <p className="mt-2 text-negative">{it.conflict.message}</p> : null}
                        </InfoPopover></span>
                      {it.conflict ? <div className="mt-1"><Chip tone="negative" testId="onboard-item-conflict">Weaker than {it.conflict.regulation}</Chip></div> : null}
                    </td>
                    <td className={cn(tdCls, "max-w-[220px] whitespace-normal")}>{it.type === "committee_question" ? "Asked again and again" : it.type === "structure" ? `${it.sections?.length ?? 0} sections` : it.type === "language" ? `${it.phrases?.length ?? 0} house phrases` : fmtValue(it.value, it.unit)}</td>
                    <td className={cn(tdCls, "max-w-[280px] whitespace-normal")}><Target it={it} /></td>
                    <td className={cn(tdCls, "max-w-[200px] whitespace-normal")}>
                      <Chip tone={it.checkability === "auto" ? "positive" : "warning"} title={it.why}>{it.checkability === "auto" ? "Data" : "A person"}</Chip>
                    </td>
                    <td className={tdCls}>
                      {st === "proposed" ? (
                        <div className="flex gap-1">
                          <PrimaryButton disabled={!!busy} onClick={() => onDecide(it, "accept")} data-testid="onboard-accept">Accept</PrimaryButton>
                          {editable(it) ? <SecondaryButton disabled={!!busy} onClick={() => setEdit({ id: it.id, text: String(it.type === "committee_question" ? it.question : it.value), err: "" })} data-testid="onboard-edit">Edit</SecondaryButton> : null}
                          <SecondaryButton disabled={!!busy} onClick={() => onDecide(it, "reject")} data-testid="onboard-reject">Reject</SecondaryButton>
                        </div>
                      ) : (
                        <button type="button" className="text-left" onClick={() => setOpen(open === it.id ? null : it.id)}>
                          <Chip tone={st === "rejected" ? "neutral" : "positive"} testId="onboard-item-status">
                            {st === "rejected" ? "Rejected" : `${st === "edited" ? "Edited" : "Accepted"}${session.decisions[it.id]?.version ? ` · ${session.decisions[it.id]?.version}` : ""}`}
                          </Chip>
                        </button>)}
                    </td>
                  </tr>
                  {editing ? (
                    <tr><td colSpan={6} className="border-b border-border/60 p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <input value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value, err: "" })} data-testid="onboard-edit-value"
                               className="h-8 min-w-[240px] flex-1 rounded-md border border-border bg-surface px-2 text-[12px]" aria-label="New value" />
                        <SecondaryButton onClick={() => setEdit(null)}>Cancel</SecondaryButton>
                        <PrimaryButton onClick={() => saveEdit(it)} data-testid="onboard-edit-save">Accept edited</PrimaryButton>
                        {edit.err ? <span role="alert" className="text-[12px] text-negative">{edit.err}</span> : null}
                      </div></td></tr>) : null}
                  {open === it.id ? (
                    <tr><td colSpan={6} className="border-b border-border/60 p-2 text-[12px] text-text-secondary">
                      {session.decisions[it.id]?.by} · {session.decisions[it.id]?.at}{session.decisions[it.id]?.note ? ` · ${session.decisions[it.id]?.note}` : ""}
                    </td></tr>) : null}
                </React.Fragment>);
            })}</tbody>
          </table>
        </div>)}
    </Section>
  );
}
