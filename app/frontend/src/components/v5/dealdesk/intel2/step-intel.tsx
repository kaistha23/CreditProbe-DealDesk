"use client";

/**
 * R14 i: the intelligence the plan places in a step (PLAN_R14 plan doc, Deal Desk table "Where it lives"), as one compact
 * row of buttons under the step; each opens its panel in a dialog. Renders nothing when the step has none.
 */

import * as React from "react";
import { Lightbulb, X } from "lucide-react";

import { loadIntel2 } from "./api";
import { type RenewalDiff, featuresForStep } from "./model";
import { INTEL2_PANELS } from "./panels";

export function StepIntel({ step, proposalId, caseType }: { step: string; proposalId: string; caseType?: string | null }) {
  // case type unknown on the page: ask the renewal diff whether it applies (one cached call, proposal step only)
  const [renewal, setRenewal] = React.useState<boolean | null>(caseType ? /renewal/.test(caseType) : null);
  React.useEffect(() => {
    if (caseType || step !== "proposal") return;
    let live = true;
    loadIntel2<RenewalDiff>(proposalId, "renewal-diff").then((d) => { if (live) setRenewal(d.applies); }).catch(() => null);
    return () => { live = false; };
  }, [caseType, step, proposalId]);
  const items = featuresForStep(step, renewal ? "renewal" : null);
  const [open, setOpen] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  if (!items.length) return null;
  const f = items.find((x) => x.key === open);
  const Panel = f ? INTEL2_PANELS[f.key] : null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[12px]" data-testid="i-step-intel" data-step={step}>
      <span className="inline-flex items-center gap-1 text-text-muted"><Lightbulb size={13} /> Intelligence for this step:</span>
      {items.map((x) => (
        <button key={x.key} type="button" onClick={() => setOpen(x.key)} data-testid={`i-step-${x.panel}`}
                className="rounded-full border border-border bg-surface px-2.5 py-0.5 text-text-secondary hover:border-accent hover:text-text-primary">{x.label}</button>))}
      {f && Panel ? (
        <div role="dialog" aria-modal="true" aria-label={f.label} data-testid={`i-step-${f.panel}-dialog`}
             className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4" onClick={() => setOpen(null)}>
          <div className="relative max-h-[calc(100vh-2rem)] w-full max-w-[980px] overflow-y-auto rounded-xl bg-surface-sunken p-3 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={() => setOpen(null)} aria-label="Close" data-testid={`i-step-${f.panel}-close`}
                    className="absolute right-3 top-3 z-10 inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={15} /></button>
            <div className="pt-8"><Panel proposalId={proposalId} /></div>
          </div>
        </div>) : null}
    </div>
  );
}
