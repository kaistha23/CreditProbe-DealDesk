"use client";

/**
 * R14 G (K34): the "In plain words" block for one panel — session u's `PlainWords` fed by the panel's own deterministic
 * writer (`lib/v5/plain-words-g`). A writer never breaks its panel: if it throws, the block is left out.
 *
 *   <PanelWords panel="covenants" lines={data ? writeCovenants(data) : null} />
 */

import * as React from "react";

import { PlainWords } from "@/components/v5/ui/plain-words";

export function PanelWords({ panel, lines, source, className }: {
  panel: string; lines: (() => string[]) | string[] | null | undefined; source?: React.ReactNode; className?: string;
}) {
  let out: string[] | null = null;
  try {
    out = typeof lines === "function" ? lines() : (lines ?? null);
  } catch {
    out = [];
  }
  if (out && !out.length) return null;
  return (
    <div data-panel-words={panel} className={className ?? "mb-3"}>
      <PlainWords lines={out ?? []} loading={out == null} speak source={source} />
    </div>
  );
}
