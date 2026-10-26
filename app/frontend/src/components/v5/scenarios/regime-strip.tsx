"use client";

/**
 * R14 m (K12): the current-regime block every scenario answer opens with (What-If thread, calibrated severities,
 * Stress Lab). The backend writes every word and number (backend/scenarios/regime.py, deterministic); this only lays
 * them out: one line with the regime and four tiles, the four plain-words lines, the macro vintage and the sources.
 */

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { AnswerMarkdown } from "@/components/v5/thread/markdown";
import { cn } from "@/lib/utils";
import { HIGH_OIL_REGIMES as HIGH, type RegimeBlock } from "@/lib/v5/regime";

export type { RegimeBlock };


export function RegimeStrip({ block, compact = false, testId = "regime-strip" }: { block: RegimeBlock | null | undefined; compact?: boolean; testId?: string }) {
  const [open, setOpen] = React.useState(!compact);
  if (!block) return null;
  const high = HIGH.has(block.regime);
  return (
    <section className={cn("rounded-md border px-3 py-2", high ? "border-warning/50 bg-warning-muted/40" : "border-border bg-surface")}
             data-testid={testId} data-regime={block.regime}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid={`${testId}-toggle`}
                className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted hover:text-text-primary">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}{block.title}</button>
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", high ? "bg-warning/20 text-text-primary" : "bg-accent-muted text-accent")}
              data-testid={`${testId}-label`}>{block.label}</span>
        <div className="ml-auto flex flex-wrap items-baseline gap-x-4 gap-y-0.5">
          {block.tiles.map((t) => (
            <span key={t.label} className="whitespace-nowrap text-[11px] text-text-muted">
              {t.label} <span className="text-[13px] font-semibold tabular-nums text-text-primary">{t.value}</span>
              {t.sub ? <span className="ml-1">{t.sub}</span> : null}</span>))}
        </div>
      </div>
      {open ? (
        <div className="mt-1.5 space-y-1" data-testid={`${testId}-lines`}>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">In plain words</p>
          <ul className="space-y-0.5">
            {block.lines.map((l, i) => (
              <li key={i} className="text-[12px] leading-snug text-text-secondary"><AnswerMarkdown text={l} /></li>))}
          </ul>
          <p className="text-[11px] leading-snug text-text-muted" data-testid={`${testId}-vintage`}>{block.vintage}</p>
          <p className="text-[11px] text-text-muted">Data Domains: dd_macro_regime · {block.relations.join(" · ")}</p>
        </div>
      ) : (
        <p className="mt-1 truncate text-[12px] text-text-secondary" title={block.lines.join(" ")}>{block.lines[0]}</p>
      )}
    </section>
  );
}
