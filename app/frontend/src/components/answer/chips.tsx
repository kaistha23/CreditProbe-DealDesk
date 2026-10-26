"use client";

/**
 * Follow-up chips (PLAN_R12 N2, I9): a banker's next questions, never a tool name. Every chip label and the text it
 * sends pass through `bankerChips`; at most four are shown.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { bankerChips } from "./banker";
import { A } from "./styles";

export interface AnswerChip { label: string; send: string }

export const chipSlug = (s: string) => s.toLowerCase().replace(/\W+/g, "-");

export function AnswerChips({ chips, onAsk, busy = false, disabled = false, testId = "answer-chips", chipTestId, limit = 4, className }: {
  chips: readonly { label: string; send?: string }[] | null | undefined;
  onAsk: (send: string, chip: AnswerChip) => void;
  busy?: boolean;
  disabled?: boolean;
  testId?: string;
  /** A function naming each chip's test id (modules keeping their sweep ids); default `${testId}-<slug>`. */
  chipTestId?: (label: string) => string;
  limit?: number;
  className?: string;
}) {
  const shown = bankerChips(chips ?? [], limit);
  if (!shown.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)} data-testid={testId}>
      {shown.map((c) => (
        <button key={c.label} type="button" disabled={busy || disabled} onClick={() => onAsk(c.send, c)} title={c.send !== c.label ? c.send : undefined}
                data-testid={chipTestId ? chipTestId(c.label) : `${testId}-${chipSlug(c.label)}`} className={A.chip}>
          {c.label}</button>))}
    </div>
  );
}
