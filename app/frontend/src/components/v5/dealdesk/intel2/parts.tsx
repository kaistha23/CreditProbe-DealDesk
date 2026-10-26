"use client";

/**
 * R14 i: shared pieces of the D6-D13 panels.
 *
 * `PlainWords` is session u's shared K34 block (`components/v5/ui/plain-words.tsx`), re-exported for the panels.
 */

import * as React from "react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";

import { type Fig, type Source, type Structure, sourceLine } from "./model";

/** K34: the shared block (session u's component). */
export { PlainWords } from "@/components/v5/ui/plain-words";

export function Lineage({ title, sources, children }: { title: string; sources: (Source | null | undefined)[]; children?: React.ReactNode }) {
  const s = sources.filter((x): x is Source => Boolean(x));
  return (
    <InfoPopover title={title}>
      {children}
      {s.length ? <p className={children ? "mt-2" : undefined}>Source{s.length > 1 ? "s" : ""}:</p> : null}
      {s.length ? <ul className="mt-1 list-disc pl-4">{s.map((x, i) => <li key={i} className="break-words">{sourceLine(x)}</li>)}</ul> : null}
    </InfoPopover>
  );
}

/** A number with its lineage (i). */
export function Num({ f, children, testId }: { f: Fig | null | undefined; children: React.ReactNode; testId?: string }) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums" data-testid={testId}>
      {children}
      {f ? <Lineage title={f.label ?? "Figure"} sources={[f.source]} /> : null}
    </span>
  );
}

export function Headline({ children, testId }: { children: React.ReactNode; testId?: string }) {
  return <p className="text-[13px] leading-5 text-text-primary" data-testid={testId}>{children}</p>;
}

export function StructureLine({ s }: { s?: Structure }) {
  if (!s) return null;
  return <p className="mb-2 text-[11.5px] text-text-muted" data-testid="intel2-structure" title={s.note}>On: <span className="text-text-secondary">{s.label}</span> · {s.note}</p>;
}

export function Loading({ error, height = "h-32" }: { error: string | null; height?: string }) {
  if (error) return <p role="alert" className="text-[12px] text-negative">{error}</p>;
  return <Skeleton className={`${height} w-full`} />;
}
