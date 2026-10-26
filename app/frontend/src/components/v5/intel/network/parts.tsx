"use client";

/**
 * PLAN_R13 §I Session IC: small pieces the three network panels share — the severity switch, the findings list and
 * the folded "Assumptions and data limits" block (mantra: the first view is the answer; detail behind a fold).
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { type Calibration, type Severity, type Source, type Writer, calibrationLine, sourceLine } from "./format";

export const SEVERITIES: Severity[] = ["mild", "moderate", "severe"];

export function SeveritySwitch({ value, onChange, testId }: { value: Severity; onChange: (s: Severity) => void; testId?: string }) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5" role="radiogroup" aria-label="Severity" data-testid={testId}>
      {SEVERITIES.map((s) => (
        <button key={s} type="button" role="radio" aria-checked={value === s} onClick={() => onChange(s)}
                className={cn("rounded px-2 py-0.5 text-[11px] capitalize",
                              value === s ? "bg-accent text-white" : "text-text-secondary hover:bg-surface-hover")}>
          {s}
        </button>
      ))}
    </div>
  );
}

export function Findings({ text, testId }: { text: Writer; testId?: string }) {
  return (
    <div className="mb-3" data-testid={testId}>
      <p className="mb-1.5 text-[13px] font-medium leading-5 text-text-primary">{text.headline}</p>
      <ul className="list-disc space-y-0.5 pl-4 text-[12px] leading-5 text-text-secondary">
        {text.lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </div>
  );
}

export function Limits({ assumptions = [], limits, calibration, lineage, testId }: {
  assumptions?: string[]; limits: string[]; calibration?: Calibration; lineage: Source[]; testId?: string;
}) {
  return (
    <details className="mt-3 rounded-md border border-border/70 px-3 py-2 text-[12px] text-text-secondary" data-testid={testId}>
      <summary className="cursor-pointer text-[12px] font-medium text-text-secondary">Assumptions and data limits</summary>
      <ul className="mt-2 list-disc space-y-1 pl-4 leading-5">
        {assumptions.map((a) => <li key={a}>{a}</li>)}
        {limits.map((l) => <li key={l}>{l}</li>)}
      </ul>
      {calibration ? <p className="mt-2 text-[11px] text-text-muted">{calibrationLine(calibration)}</p> : null}
      <p className="mt-1 text-[11px] text-text-muted">Sources: {sourceLine(lineage)}.</p>
    </details>
  );
}
