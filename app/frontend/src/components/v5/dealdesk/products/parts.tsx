"use client";

/**
 * PLAN_R12 Session P: pieces the four product sections share — the answer line, the tile row (shared KpiRow), the
 * loading / error states and the (i) lineage line.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";

import { Empty, Section } from "../kit";
import { type Tile } from "./format";

export function Answer({ text, testId }: { text: string; testId?: string }) {
  return <p className="mb-3 text-[13px] leading-5 text-text-primary" data-testid={testId}>{text}</p>;
}

export function Tiles({ tiles, testId }: { tiles: Tile[]; testId?: string }) {
  if (!tiles.length) return null;
  return (
    <div className="mb-3" data-testid={testId}>
      <KpiRow tiles={tiles.map((t) => ({ label: t.label, value: t.value, sub: t.sub, tone: t.tone, info: t.info }))} />
    </div>
  );
}

export function Loading({ title, testId }: { title: string; testId?: string }) {
  return (
    <Section title={title} testId={testId}>
      <Skeleton className="mb-2 h-5 w-2/3" />
      <Skeleton className="h-24 w-full" />
    </Section>
  );
}

export function Failed({ title, message, testId, onRetry }: { title: string; message: string; testId?: string; onRetry?: () => void }) {
  return (
    <Section title={title} testId={testId}>
      <Empty>
        {message}{" "}
        {onRetry ? <button type="button" className="text-accent underline" onClick={onRetry}>Try again</button> : null}
      </Empty>
    </Section>
  );
}

export function Sub({ title, children, info }: { title: string; children: React.ReactNode; info?: string }) {
  return (
    <div className="mt-4 min-w-0">
      <h3 className="mb-1.5 text-[12px] font-medium text-text-secondary" title={info}>{title}</h3>
      {children}
    </div>
  );
}

export function Flags({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12px] text-text-secondary">
      {items.map((f) => <li key={f}>{f}</li>)}
    </ul>
  );
}

export const scrollCls = "max-w-full overflow-x-auto";
