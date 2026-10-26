/**
 * The answer type scale and spacing (PLAN_R12 N2, I10 a), as class strings: one place for every conversational layer.
 *
 * Headline 15/22 semibold primary · body 13.5/1.65 secondary · section label 11 caps muted · key figure semibold
 * tabular primary · table 12 with an 11 caps header (the Deal Desk house kit) · chip 12. Answer blocks stack at 16px,
 * paragraphs at 10px.
 */

export const A = {
  /** The answer stack: one block after another, generous but not loose. */
  stack: "space-y-4",
  stackCompact: "space-y-3",
  headline: "text-[15px] font-semibold leading-[1.45] tracking-[-0.005em] text-text-primary",
  headlineCompact: "text-[13.5px] font-semibold leading-[1.45] text-text-primary",
  body: "space-y-2.5 text-[13.5px] leading-[1.65] text-text-secondary",
  bodyCompact: "space-y-2 text-[12.5px] leading-[1.6] text-text-secondary",
  /** Key figures in prose: the eye lands on the number. */
  figure: "font-semibold tabular-nums text-text-primary",
  heading: "pt-1 text-[13px] font-semibold text-text-primary",
  label: "text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted",
  code: "rounded bg-surface-hover px-1 font-mono text-[12px]",
  link: "font-medium text-accent underline-offset-2 hover:underline",
  /** House-kit table (components/v5/dealdesk/kit.tsx), compact. */
  table: "w-full border-collapse text-[12px]",
  th: "whitespace-nowrap border-b border-border px-2.5 py-1.5 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted",
  td: "border-b border-border/60 px-2.5 py-1.5 tabular-nums text-text-secondary",
  card: "rounded-lg border border-border bg-surface",
  more: "inline-flex items-center gap-1 text-[12px] font-medium text-accent hover:underline",
  chip: "h-7 rounded-full border border-border bg-surface px-3 text-[12px] text-text-secondary transition-colors hover:border-accent hover:text-accent disabled:opacity-40",
  kpiLabel: "text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted",
  kpiValue: "mt-1 text-[18px] font-semibold leading-none tabular-nums text-text-primary",
} as const;
