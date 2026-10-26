"use client";

/**
 * The Deal Desk design kit (DEAL_DESK_PROMPT section 4, PLAN_R4 G3): one card,
 * one table, one KPI tile, one chip, one button hierarchy and the deal
 * stepper, all on the Executive Ivory tokens and an 8-pt spacing scale.
 * Explanations live in the (i) popover, never as loose text on the screen.
 */

import * as React from "react";
import { Check, ChevronDown, ChevronRight } from "lucide-react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { cn } from "@/lib/utils";

/**
 * PLAN_R11 U2: a Section inside <Collapsible> (the panels under the Optimise structures) gets the fold chevron in its
 * own header, so a component that renders its own Section (ForwardRiskPanel, StressSummary, ...) is folded without a
 * second card around it. Only the outermost Section claims it: it hands its children no context.
 */
const FoldContext = React.createContext<{ open: boolean; toggle: () => void; testId?: string } | null>(null);

export function Section({ title, info, action, children, testId, className }: {
  title: string; info?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; testId?: string; className?: string;
}) {
  const fold = React.useContext(FoldContext);
  const open = !fold || fold.open;
  return (
    <Card className={cn("p-4", className)} data-testid={testId} data-open={fold ? (open ? "true" : "false") : undefined}>
      <div className={cn("flex min-h-8 items-center gap-2", open && "mb-3")}>
        {fold ? (
          <button type="button" onClick={fold.toggle} aria-expanded={open} aria-label={`${open ? "Fold" : "Unfold"} ${title}`}
                  data-testid={fold.testId ? `${fold.testId}-toggle` : undefined}
                  className="-ml-1 inline-flex size-6 shrink-0 items-center justify-center rounded text-text-muted hover:bg-surface-hover hover:text-text-secondary">
            <ChevronDown size={14} aria-hidden className={cn("transition-transform", !open && "-rotate-90")} />
          </button>) : null}
        <h2 className="text-[14px] font-semibold text-text-primary">{title}</h2>
        {info ? <InfoPopover title={title}>{info}</InfoPopover> : null}
        {action ? <div className="ml-auto flex items-center gap-2">{action}</div> : null}
      </div>
      <FoldContext.Provider value={null}>{open ? children : null}</FoldContext.Provider>
    </Card>
  );
}

/** A chart's own title and (i) inside a card holding more than one chart (PLAN_R6 D4). */
export function ChartTitle({ title, info }: { title: string; info: React.ReactNode }) {
  return (
    <div className="mb-1 flex items-center gap-2">
      <h3 className="text-[12px] font-medium text-text-secondary">{title}</h3>
      <InfoPopover title={title}>{info}</InfoPopover>
    </div>
  );
}

export function Kpi({ label, value, sub, tone, info, testId }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "positive" | "negative" | "neutral"; info?: string; testId?: string;
}) {
  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-surface px-3 py-2.5" data-testid={testId} title={info}>
      <p className="truncate text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("mt-0.5 truncate text-[20px] font-bold tabular-nums leading-7",
                       tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text-primary")}>{value}</p>
      {sub ? <p className="mt-0.5 truncate text-[12px] tabular-nums text-text-secondary" title={typeof sub === "string" ? sub : undefined}>{sub}</p> : null}
    </div>
  );
}

export function Chip({ children, tone = "neutral", title, testId }: {
  children: React.ReactNode; tone?: "neutral" | "positive" | "negative" | "warning" | "accent"; title?: string; testId?: string;
}) {
  const tones = {
    neutral: "border-border bg-surface text-text-secondary",
    positive: "border-positive/30 bg-positive-muted text-positive",
    negative: "border-negative/30 bg-negative-muted text-negative",
    warning: "border-warning/30 bg-warning-muted text-warning",
    accent: "border-accent/30 bg-accent-muted text-accent",
  };
  return <span title={title} data-testid={testId}
               className={cn("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full border px-2 text-[11px] font-medium", tones[tone])}>{children}</span>;
}

export function PrimaryButton({ children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...props}
                 className={cn("inline-flex h-9 items-center gap-2 rounded-md bg-accent px-4 text-[13px] font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-40", className)}>{children}</button>;
}

export function SecondaryButton({ children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...props}
                 className={cn("inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover disabled:opacity-40", className)}>{children}</button>;
}

export const tableCls = "w-full border-collapse text-[12px]";
export const thCls = "border-b border-border px-2 py-2 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted";
export const tdCls = "whitespace-nowrap border-b border-border/60 px-2 py-2 tabular-nums";

export const STEPS = [
  // PLAN_R14 (K23, K31): Upload · Proposal check · Review · Analysis · Structure · Recommendation. Stress is a header button
  // from Structure on (R14 F), over the structures the user selects; its ?step=stress view keeps the R12 key.
  // (PLAN_R12 §1.2, I15 before: Proposal · Review · Analysis · Stress · Structure · Recommendation.)
  { key: "proposal", label: "Upload" },
  { key: "proposal-check", label: "Proposal check" },
  { key: "review", label: "Review" },
  { key: "analysis", label: "Analysis" },
  { key: "structure", label: "Structure" },
  { key: "recommendation", label: "Recommendation" },
] as const;
export type StepKey = (typeof STEPS)[number]["key"] | "stress";

/**
 * PLAN_R10 D2 (G-STEPS): one horizontal step bar, 1 → 2 → … → 6 in a single row at every width. A flex row with
 * nowrap (not a grid that a narrow column can collapse to one track), each step shrinking and truncating its label.
 * PLAN_R12 O2: a tick means "visited and done" (`done`), never "computed"; every step can be opened.
 */
export function Stepper({ step, done, onStep }: { step: StepKey; done: ReadonlySet<string>; onStep: (s: StepKey) => void }) {
  const at = STEPS.findIndex((s) => s.key === step);
  return (
    <nav aria-label="Deal steps" data-testid="dealdesk-stepper" data-layout="horizontal">
      <ol className="flex w-full flex-row flex-nowrap items-center gap-1" style={{ display: "flex", flexDirection: "row" }}>
        {STEPS.map((s, i) => {
          const ticked = done.has(s.key);
          const state = i === at ? "current" : ticked ? "done" : "open";
          return (
            <li key={s.key} className="flex min-w-0 flex-1 items-center gap-1">
              <button type="button" onClick={() => onStep(s.key)} data-testid={`dealdesk-step-${s.key}`} data-tour={`dd-${s.key}`}
                      data-state={state} data-done={ticked ? "true" : "false"} aria-current={i === at ? "step" : undefined}
                      className={cn("flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border px-2.5 text-left text-[13px] transition-colors",
                                    i === at ? "border-accent bg-accent-muted font-semibold text-accent"
                                      : "border-border bg-surface text-text-secondary hover:border-accent")}>
                <span className={cn("inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                                    i === at ? "bg-accent text-accent-contrast" : ticked ? "bg-positive text-accent-contrast" : "bg-surface-hover text-text-muted")}>
                  {ticked && i !== at ? <Check size={12} aria-label="Done" /> : i + 1}</span>
                <span className="min-w-0 truncate">{s.label}</span>
              </button>
              {i < STEPS.length - 1 ? <ChevronRight size={14} aria-hidden className="shrink-0 text-text-muted" /> : null}
            </li>);
        })}
      </ol>
    </nav>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-border text-[12px] text-text-muted">{children}</div>;
}

/** The index of a step in the bar (0-based), for the reached / visited bookkeeping of the deal view. */
export const stepIndex = (s: StepKey): number => STEPS.findIndex((x) => x.key === s);

function readOpen(key: string, fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(`dealdesk.panel.${key}`);
    return v === null ? fallback : v === "1";
  } catch {
    return fallback;
  }
}

/**
 * PLAN_R11 U2: makes the Section its child renders collapsible (chevron in that Section's header), open by default,
 * the state remembered per panel in this browser. The child keeps its own title, (i) and actions.
 */
export function Collapsible({ id, children, testId, defaultOpen = true }: {
  id: string; children: React.ReactNode; testId?: string; defaultOpen?: boolean;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  React.useEffect(() => { setOpen(readOpen(id, defaultOpen)); }, [id, defaultOpen]);
  const toggle = React.useCallback(() => setOpen((o) => {
    try { window.localStorage.setItem(`dealdesk.panel.${id}`, o ? "0" : "1"); } catch { /* storage blocked: the state lasts the visit */ }
    return !o;
  }), [id]);
  const value = React.useMemo(() => ({ open, toggle, testId }), [open, toggle, testId]);
  return (
    <div data-testid={testId} data-open={open ? "true" : "false"} className="min-w-0">
      <FoldContext.Provider value={value}>{children}</FoldContext.Provider>
    </div>
  );
}
