"use client";

/** R14 G: "Material names · All names" — the two-way scope of Who to call and the renewal autopilot (J9 floor by default). */

import * as React from "react";

import { cn } from "@/lib/utils";

export type Scope = "material" | "all";

export function ScopeToggle({ scope, onChange, floor, testId }: { scope: Scope; onChange: (s: Scope) => void; floor?: number; testId: string }) {
  const opts: [Scope, string, string][] = [
    ["material", "Material names", `Relationship EAD at least SAR ${floor ?? 50}m (Deal Desk Parameters, materiality floor)`],
    ["all", "All names", "Every name in the back book, including the smaller ones the RMs handle"],
  ];
  return (
    <div role="group" aria-label="Which names" className="inline-flex overflow-hidden rounded-md border border-border" data-testid={testId}>
      {opts.map(([k, label, hint]) => (
        <button key={k} type="button" aria-pressed={scope === k} title={hint} onClick={() => onChange(k)} data-testid={`${testId}-${k}`}
                className={cn("h-7 px-3 text-[12px]", scope === k ? "bg-accent-muted font-medium text-accent" : "text-text-secondary hover:bg-surface-hover",
                              k === "all" && "border-l border-border")}>{label}</button>))}
    </div>
  );
}
