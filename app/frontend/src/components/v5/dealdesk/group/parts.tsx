"use client";

/** Small shared pieces of the group panels: the source (i), status chips and the loading / error states. */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { InfoPopover } from "@/components/ui/info-popover";

import { Chip } from "../kit";
import { type Source, type Tone, evidenceLine, statusTone } from "./model";

export function SourceInfo({ title, sources, children }: { title: string; sources: Source[]; children?: React.ReactNode }) {
  return (
    <InfoPopover title={title}>
      {children}
      {sources.length ? <p className={children ? "mt-2" : undefined}>Source{sources.length > 1 ? "s" : ""} in Data Domains:</p> : null}
      {sources.length ? <ul className="mt-1 list-disc pl-4">
        {sources.map((s, i) => <li key={i} className="break-words">{evidenceLine(s)}{s.observed !== undefined && s.observed !== null && typeof s.observed !== "object"
          ? ` → ${String(s.observed)}` : ""}</li>)}
      </ul> : null}
    </InfoPopover>
  );
}

export function StatusChip({ status, testId }: { status: string; testId?: string }) {
  return <Chip tone={statusTone(status) as Tone} testId={testId}>{status}</Chip>;
}

export function Loading({ error, height = "h-40" }: { error: string | null; height?: string }) {
  if (error) return <p role="alert" className="text-[12px] text-negative">{error}</p>;
  return <Skeleton className={`${height} w-full`} />;
}

export function SubTitle({ children, info }: { children: React.ReactNode; info?: React.ReactNode }) {
  return (
    <div className="mb-1 mt-4 flex items-center gap-2">
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">{children}</h3>
      {info}
    </div>
  );
}

export function Answer({ children, testId }: { children: React.ReactNode; testId?: string }) {
  return <p className="text-[13px] leading-5 text-text-primary" data-testid={testId}>{children}</p>;
}
