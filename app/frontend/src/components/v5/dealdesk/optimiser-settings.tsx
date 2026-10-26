"use client";

/**
 * Optimiser settings (DEAL_DESK_PROMPT 3.6): hold any lever at its current value, weight the distance from the
 * ask (amount cut, tenor cut, margin increase, added collateral, fees; most costly first by default), and allow
 * soft limits with escalation. The settings go with the next Optimise.
 */

import * as React from "react";
import { Lock, LockOpen, SlidersHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Terms } from "@/lib/v5/dealdesk";

import { SecondaryButton } from "./kit";

export interface OptimiserSettings { fixed: Partial<Terms>; weights: Record<string, number>; allow_soft: boolean }
export const DEFAULT_WEIGHTS: Record<string, number> = { amount: 5, tenor: 4, margin: 3, collateral: 2, fees: 1 };
export const DEFAULT_SETTINGS: OptimiserSettings = { fixed: {}, weights: DEFAULT_WEIGHTS, allow_soft: false };

const LOCKABLE: [keyof Terms, string][] = [
  ["amount", "Amount"], ["tenor_years", "Tenor"], ["margin_bps", "Margin"], ["upfront_fee_bps", "Upfront fee"],
  ["cash_margin_pct", "Cash margin"], ["structure", "Structure"], ["collateral_ids", "Collateral"],
];
const WEIGHT_LABEL: Record<string, string> = { amount: "Amount cut", tenor: "Tenor cut", margin: "Margin increase", collateral: "Added collateral", fees: "Fees" };

export function OptimiserSettingsButton({ terms, value, onChange, testId = "dealdesk-optimiser" }: {
  terms: Terms; value: OptimiserSettings; onChange: (v: OptimiserSettings) => void;
  /** R7: the analysis card carries its own copy (screen 01), with its own test ids. */
  testId?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const locked = Object.keys(value.fixed).length;
  const custom = JSON.stringify(value.weights) !== JSON.stringify(DEFAULT_WEIGHTS) || value.allow_soft;
  return (
    <div className="relative">
      <SecondaryButton onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid={`${testId}-settings`}>
        <SlidersHorizontal size={13} /> Settings{locked || custom ? ` · ${locked} held` : ""}</SecondaryButton>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-[360px] space-y-4 rounded-lg border border-border bg-surface p-4 shadow-lg" role="dialog"
             aria-label="Optimiser settings" data-testid={`${testId}-panel`}>
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Hold at the current value</p>
            <div className="flex flex-wrap gap-2">
              {LOCKABLE.map(([k, label]) => {
                const on = k in value.fixed;
                return (
                  <button key={k} type="button" aria-pressed={on} data-testid={`dealdesk-lock-${k}`}
                          onClick={() => {
                            const fixed = { ...value.fixed } as Record<string, unknown>;
                            if (on) delete fixed[k]; else fixed[k] = terms[k];
                            onChange({ ...value, fixed: fixed as Partial<Terms> });
                          }}
                          className={cn("inline-flex h-7 items-center gap-1 rounded-full border px-3 text-[12px]",
                                        on ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
                    {on ? <Lock size={11} /> : <LockOpen size={11} />} {label}</button>);
              })}
            </div>
          </div>
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Cost of moving away from the ask</p>
            <div className="space-y-2">
              {Object.keys(DEFAULT_WEIGHTS).map((k) => (
                <label key={k} className="flex items-center gap-3 text-[12px] text-text-secondary">
                  <span className="w-32">{WEIGHT_LABEL[k]}</span>
                  <input type="range" min={0} max={10} step={0.5} value={value.weights[k] ?? 0} data-testid={`dealdesk-weight-${k}`}
                         onChange={(e) => onChange({ ...value, weights: { ...value.weights, [k]: Number(e.target.value) } })}
                         className="flex-1 accent-[var(--ipm-accent)]" aria-label={WEIGHT_LABEL[k]} />
                  <span className="w-8 text-right tabular-nums text-text-primary">{value.weights[k] ?? 0}</span>
                </label>))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-[12px] text-text-secondary">
            <input type="checkbox" checked={value.allow_soft} onChange={(e) => onChange({ ...value, allow_soft: e.target.checked })}
                   data-testid="dealdesk-allow-soft" /> Allow soft limits with escalation</label>
          <div className="flex justify-between">
            <SecondaryButton onClick={() => onChange(DEFAULT_SETTINGS)} data-testid="dealdesk-settings-reset">Reset</SecondaryButton>
            <SecondaryButton onClick={() => setOpen(false)}>Done</SecondaryButton>
          </div>
        </div>) : null}
    </div>
  );
}
