"use client";

/** Small shared pieces of the approval-intelligence panels: a figure with its lineage (i), the answer line, loading. */

import * as React from "react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";

import { type Fig, type Source, sourceLine } from "./model";

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

export function FigText({ f, children }: { f: Fig | null | undefined; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      {children}
      {f ? <Lineage title={f.label ?? "Figure"} sources={[f.source]} /> : null}
    </span>
  );
}

export function Answer({ children, testId }: { children: React.ReactNode; testId?: string }) {
  return <p className="text-[13px] leading-5 text-text-primary" data-testid={testId}>{children}</p>;
}

export function Loading({ error, height = "h-32" }: { error: string | null; height?: string }) {
  if (error) return <p role="alert" className="text-[12px] text-negative">{error}</p>;
  return <Skeleton className={`${height} w-full`} />;
}
