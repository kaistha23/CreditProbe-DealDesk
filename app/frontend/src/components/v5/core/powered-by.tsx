"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  CONFIDENCE_LABEL,
  type Confidence,
  findPack,
  findRule,
  traceHref,
} from "@/lib/v5/intelligence-packs";

/**
 * PLAN_R9: "Powered by" — the shared strip under every intelligent answer.
 *
 * It names the Intelligence Pack, the rule ID or CBUAE article, a confidence
 * level and the Trace, so every answer says which piece of our IP produced it.
 *
 *   <PoweredBy pack="P2" rule="P2-UTP-03" confidence="high" trace={{ runId }} />
 *   <PoweredBy pack="P1" article="CBUAE CRM, credit concentration" trace={{ href: "/trace/abc" }} />
 *
 * `article` defaults to the rule's source when a known rule ID is given. With no
 * trace the Trace link is left out rather than drawn dead. `compact` drops the
 * pack's long name and the article (kept in the rule's tooltip) for tight rows.
 */
export interface PoweredByProps {
  /** Pack ID, "P1" … "P7". */
  pack: string;
  /** Our rule ID, e.g. "P2-UTP-03". */
  rule?: string | null;
  /** CBUAE article or regulatory source; defaults to the rule's source. */
  article?: string | null;
  confidence?: Confidence | null;
  /** Where the Trace opens: an app path, or the run ID for /trace/{id}. */
  trace?: { href?: string | null; runId?: string | null } | null;
  compact?: boolean;
  className?: string;
  testId?: string;
}

const CONFIDENCE_DOT: Record<Confidence, string> = {
  high: "bg-emerald-600 dark:bg-emerald-400",
  medium: "bg-amber-500 dark:bg-amber-400",
  low: "bg-rose-600 dark:bg-rose-400",
};

export function PoweredBy({
  pack,
  rule,
  article,
  confidence,
  trace,
  compact = false,
  className,
  testId = "powered-by",
}: PoweredByProps) {
  const p = findPack(pack);
  const r = rule ? findRule(rule) : undefined;
  const source = article ?? r?.rule.source ?? null;
  const href = traceHref(trace);
  const packId = p?.id ?? pack;

  return (
    <div
      data-testid={testId}
      data-pack={packId}
      className={cn(
        "flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[11px] leading-4 text-text-secondary",
        className,
      )}
    >
      <Sparkles className="size-3 shrink-0 text-accent" aria-hidden />
      <span className="text-text-muted">Powered by</span>
      {/* PLAN_R10 S1: the Intelligence Library screen is removed; the pack is named, with what it knows on hover. */}
      <span
        className="font-semibold text-text-primary"
        title={p ? `${p.id} ${p.name}: ${p.knows}` : packId}
        data-testid={`${testId}-pack`}
      >
        {compact || !p ? packId : `${p.id} ${p.name}`}
      </span>
      {rule ? (
        <>
          <Sep />
          <span className="font-mono text-[10.5px] text-text-primary" title={[r?.rule.title, source].filter(Boolean).join(" · ")} data-testid={`${testId}-rule`}>
            {rule.toUpperCase()}
          </span>
        </>
      ) : null}
      {source && (!compact || !rule) ? (
        <>
          <Sep />
          <span className="max-w-[28rem] truncate" title={source} data-testid={`${testId}-article`}>
            {source}
          </span>
        </>
      ) : null}
      {confidence ? (
        <>
          <Sep />
          <span className="inline-flex items-center gap-1" data-testid={`${testId}-confidence`}>
            <span className={cn("size-1.5 rounded-full", CONFIDENCE_DOT[confidence])} aria-hidden />
            {CONFIDENCE_LABEL[confidence]}
          </span>
        </>
      ) : null}
      {href ? (
        <>
          <Sep />
          <Link href={href} className="font-medium text-accent hover:underline" data-testid={`${testId}-trace`}>
            Trace
          </Link>
        </>
      ) : null}
    </div>
  );
}

function Sep() {
  return <span className="text-border-strong" aria-hidden>·</span>;
}
