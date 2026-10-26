"use client";

/**
 * Round T: the provenance of the whole paper, for committee and audit. Per section: the sources it reads (documents, bank
 * data relations, engine results), the rules applied (whose, when), the changes made by instruction (who, when, what), and
 * every point with its evidence. Figures without a traced source are listed on top. The Word export carries the same as an annex.
 */

import * as React from "react";
import { Loader2 } from "lucide-react";

import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";

import { Chip, tableCls, tdCls, thCls } from "../kit";
import { Rich } from "../proposal/blocks";
import { type Evidence, EVIDENCE_LABEL, type Provenance, evidenceText } from "./model";

const TONE: Record<Evidence["kind"], "accent" | "neutral" | "positive" | "warning"> = {
  document: "accent", data: "neutral", engine: "positive", rule: "warning", analyst: "warning", rm: "accent",
};

export function ProvenanceView({ pv, onOpen }: { pv: Provenance | null; onOpen?: (sectionKey: string) => void }) {
  if (!pv) {
    return <p className="flex items-center gap-2 p-6 text-[13px] text-text-muted" data-testid="pw-provenance-loading"><Loader2 size={15} className="animate-spin" /> Tracing every point to its source…</p>;
  }
  const sm = pv.summary;
  return (
    <div className="mx-auto max-w-[920px] space-y-4" data-testid="pw-provenance">
      <PlainWords lines={pv.plain_words} testId="pw-provenance-plain" />
      <div className="flex flex-wrap gap-1.5" data-testid="pw-provenance-counts">
        <Chip tone="accent">{sm.figures_traced} of {sm.with_figures} figures traced</Chip>
        {(Object.keys(EVIDENCE_LABEL) as Evidence["kind"][]).map((k) => (sm.by_kind[k] ? <Chip key={k} tone={TONE[k]}>{EVIDENCE_LABEL[k]}: {sm.by_kind[k]}</Chip> : null))}
        <Chip>{sm.documents.length} documents</Chip><Chip>{sm.relations.length} relations</Chip><Chip>{sm.rules.length} rules</Chip><Chip>{sm.edits} changes by instruction</Chip>
      </div>
      {sm.untraced.length ? (
        <details className="rounded-md border border-warning/50 bg-surface p-2" data-testid="pw-provenance-untraced">
          <summary className="cursor-pointer text-[12px] text-text-primary">{sm.untraced.length} figure{sm.untraced.length === 1 ? "" : "s"} without a traced source</summary>
          <ul className="mt-1 space-y-0.5 text-[11px] text-text-secondary">{sm.untraced.map((u) => <li key={u.point}><b>{u.section}</b>: {u.text}</li>)}</ul>
        </details>) : null}
      {pv.sections.map((s) => {
        const traced = s.points.filter((p) => p.has_figure && p.traced).length;
        const figs = s.points.filter((p) => p.has_figure).length;
        return (
          <details key={s.key} className="rounded-md border border-border bg-surface" data-testid={`pw-prov-section-${s.key}`}>
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 text-[12.5px]">
              <span className="font-semibold text-accent">{s.n ? `${s.n}. ` : ""}{s.heading}</span>
              <span className="text-[11px] text-text-muted">{s.points.length} points · {traced}/{figs} figures traced · {s.sources.length} sources</span>
              {s.rules.length ? <Chip tone="warning">{s.rules.length} rule{s.rules.length === 1 ? "" : "s"}</Chip> : null}
              {s.edits.length ? <Chip tone="warning">{s.edits.length} change{s.edits.length === 1 ? "" : "s"}</Chip> : null}
              {onOpen ? <button type="button" className="ml-auto text-[11px] text-accent underline" onClick={(e) => { e.preventDefault(); onOpen(s.key); }}>Open in the document</button> : null}
            </summary>
            <div className="space-y-2 border-t border-border px-3 py-2">
              {s.sources.length ? (
                <div><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Sources</p>
                  <ul className="space-y-0.5">{s.sources.map((e, i) => <EvLine key={i} e={e} />)}</ul></div>) : null}
              {s.rules.length ? (
                <div data-testid="pw-prov-rules"><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Rules applied</p>
                  <ul className="space-y-0.5">{s.rules.map((r, i) => <EvLine key={i} e={{ ...r, kind: "rule" }} />)}</ul></div>) : null}
              {s.edits.length ? (
                <div data-testid="pw-prov-edits"><p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">Changes by instruction</p>
                  <ul className="space-y-0.5">{s.edits.map((e, i) => <EvLine key={i} e={e} />)}</ul></div>) : null}
              <table className={cn(tableCls, "text-[11px]")}>
                <thead><tr><th className={thCls}>Point</th><th className={thCls}>Evidence</th></tr></thead>
                <tbody>{s.points.map((p) => (
                  <tr key={p.id} data-testid="pw-prov-point" className={cn(p.has_figure && !p.traced && "bg-warning/5")}>
                    <td className={cn(tdCls, "max-w-[340px] whitespace-normal align-top")}><Rich text={p.text.length > 220 ? `${p.text.slice(0, 220)}…` : p.text} /></td>
                    <td className={cn(tdCls, "whitespace-normal align-top")}>
                      {p.evidence.length ? <ul className="space-y-0.5">{p.evidence.map((e, i) => <EvLine key={i} e={e} />)}</ul>
                        : <span className="text-text-muted">{p.has_figure ? "no source found" : "wording"}</span>}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </details>);
      })}
    </div>
  );
}

function EvLine({ e }: { e: Evidence }) {
  return (
    <li className="flex items-start gap-1.5 text-[11px]">
      <Chip tone={TONE[e.kind]}>{EVIDENCE_LABEL[e.kind]}</Chip>
      <span className="min-w-0 break-words text-text-secondary">{evidenceText(e)}</span>
    </li>);
}
