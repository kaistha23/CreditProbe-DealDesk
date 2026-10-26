"use client";

/**
 * An answer's prose. Since PLAN_R12 N2 this is the shared answer renderer's `AnswerProse`
 * (components/answer/prose.tsx): headline sentence first when asked, the refined type scale, key figures in bold,
 * pipe tables as compact house-kit tables, long bodies behind "Show more", banker words for internal names.
 */

import * as React from "react";

import { AnswerProse } from "@/components/answer";

export function AnswerMarkdown({ text, className, headline = false, compact = false }: {
  text: string; className?: string; headline?: boolean; compact?: boolean;
}) {
  return <AnswerProse text={String(text ?? "")} className={className} headline={headline} compact={compact} />;
}
