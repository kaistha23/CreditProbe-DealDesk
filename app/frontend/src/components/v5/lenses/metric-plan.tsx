"use client";

/**
 * R16 M5: the Metric plan card. A request that names a persona (CRO, analyst, CCO, branch or RM head) first shows the
 * plan: In plain words on top, then per measure its definition, formula, SQL (collapsed) and source relation, or
 * "not available: why". "Edit" shows a tick box per measure; "Build this dashboard" builds the lens from the plan.
 */

import * as React from "react";
import { Hammer, Pencil, X } from "lucide-react";

import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { type MetricPlan, canBuild, counts, includeIds, initialSelection, relationLabel, toggle } from "@/lib/v5/lenses-plan";

export function MetricPlanCard({ plan, busy, error, onBuild, onCancel, buildLabel = "Build this dashboard" }: {
  plan: MetricPlan; busy?: boolean; error?: string; onBuild: (include: string[]) => void; onCancel?: () => void; buildLabel?: string }) {
  const [selected, setSelected] = React.useState(() => initialSelection(plan));
  const [editing, setEditing] = React.useState(false);
  const c = counts(plan, selected);
  return (
    <section className="space-y-2.5" data-testid="lens-metric-plan" data-persona={plan.persona} aria-label="Metric plan">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Metric plan</p>
          <h3 className="text-[14px] font-semibold text-text-primary">{plan.persona_label} · {plan.scope_label} · as of {plan.period}</h3>
        </div>
        {onCancel ? (
          <button type="button" onClick={onCancel} aria-label="Close the plan" data-testid="lens-metric-plan-close"
                  className="inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={14} /></button>) : null}
      </div>
      <PlainWords lines={plan.plain_words} testId="lens-metric-plan-words" />
      <div className="max-h-[26rem] overflow-auto rounded-md border border-border">
        <table className="w-full border-collapse text-left text-[12px]" data-testid="lens-metric-plan-table">
          <thead className="sticky top-0 bg-surface-raised text-[11px] text-text-muted">
            <tr>
              {editing ? <th className="w-8 px-2 py-1.5"><span className="sr-only">Include</span></th> : null}
              <th className="px-2 py-1.5 font-medium">Metric</th>
              <th className="px-2 py-1.5 font-medium">Definition</th>
              <th className="px-2 py-1.5 font-medium">Formula</th>
              <th className="px-2 py-1.5 font-medium">SQL</th>
              <th className="px-2 py-1.5 font-medium">Source relation</th>
            </tr>
          </thead>
          <tbody>
            {plan.metrics.map((m) => {
              const on = m.available && selected.has(m.id);
              return (
                <tr key={m.id} data-testid={`lens-metric-plan-row-${m.id}`} data-available={m.available ? "1" : "0"} data-included={on ? "1" : "0"}
                    className={cn("border-t border-border align-top", !m.available && "text-text-muted", m.available && !on && "opacity-60")}>
                  {editing ? (
                    <td className="px-2 py-1.5">
                      <input type="checkbox" checked={on} disabled={!m.available || busy} aria-label={`Include ${m.label}`}
                             data-testid={`lens-metric-plan-include-${m.id}`} onChange={() => setSelected((s) => toggle(plan, s, m.id))} />
                    </td>) : null}
                  <td className="px-2 py-1.5">
                    <p className="font-medium text-text-primary">{m.label}</p>
                    <p className="text-[10px] uppercase tracking-wide text-text-muted">{m.kind === "kpi" ? "Key figure" : m.chart || m.tile_type}</p>
                  </td>
                  <td className="px-2 py-1.5">{m.available ? m.definition : <span data-testid="lens-metric-plan-na">{m.reason}</span>}</td>
                  <td className="px-2 py-1.5">{m.formula}</td>
                  <td className="px-2 py-1.5">
                    {m.sql ? (
                      <details data-testid="lens-metric-plan-sql">
                        <summary className="cursor-pointer text-accent">Show SQL</summary>
                        <pre className="mt-1 max-w-[28rem] overflow-auto whitespace-pre-wrap break-words rounded bg-surface-hover p-2 font-mono text-[10.5px] leading-snug">{m.sql}</pre>
                      </details>) : <span>–</span>}
                  </td>
                  <td className="px-2 py-1.5">{m.available ? relationLabel(m) : "–"}</td>
                </tr>);
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" disabled={busy || !canBuild(plan, selected)} onClick={() => onBuild(includeIds(plan, selected))} data-testid="lens-metric-plan-build"
                className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast disabled:opacity-50">
          <Hammer size={13} /> {busy ? "Building…" : buildLabel}</button>
        <button type="button" disabled={busy} onClick={() => setEditing((e) => !e)} aria-pressed={editing} data-testid="lens-metric-plan-edit"
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-[12px] font-medium text-text-secondary hover:bg-surface-hover disabled:opacity-50">
          <Pencil size={13} /> {editing ? "Done" : "Edit"}</button>
        <span className="text-[11px] text-text-muted" data-testid="lens-metric-plan-counts">
          {c.tiles} charts or tables, {c.kpis} key figures{c.unavailable ? `, ${c.unavailable} not available` : ""}</span>
      </div>
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
    </section>
  );
}
