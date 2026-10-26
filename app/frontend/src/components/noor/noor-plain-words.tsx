"use client";

/**
 * "In plain words" (K34 block; R14 n content for Noor's answers): 3–4 short lines a layman understands, at the top of
 * an answer, with a speaker. Deterministic lines from the server (`plain_words`). When session u's shared
 * `<PlainWords>` (components/v5/ui/plain-words.tsx) is merged, this renders the same way and can be swapped for it.
 */

import { cn } from "@/lib/utils";

import { SpeakText } from "./speak-text";

export function NoorPlainWords({ lines, speak, ar, className, testId = "plain-words" }: {
  lines: string[]; speak?: string; ar?: string | null; className?: string; testId?: string;
}) {
  if (!lines?.length) return null;
  return (
    <section aria-label="In plain words" data-testid={testId}
             className={cn("rounded-md border-l-2 border-accent bg-accent/5 px-3 py-2", className)}>
      <header className="flex items-center gap-2">
        <p className="flex-1 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-accent">In plain words</p>
        <SpeakText en={speak || lines.join(" ")} ar={ar} label="Listen" testId={`${testId}-speaker`} />
      </header>
      <ul className="mt-0.5 space-y-0.5 text-[12.5px] leading-snug text-text-primary">
        {lines.map((l, i) => <li key={i}>{l}</li>)}
      </ul>
    </section>
  );
}
