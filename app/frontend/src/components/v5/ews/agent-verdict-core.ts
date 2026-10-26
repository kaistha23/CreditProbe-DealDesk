/**
 * PLAN_R11_AGENTS E4 helpers (pure, tested): the Early Warning triage agent's verdicts as the list shows them.
 *
 * The verdicts come from the agent's run (`ews.triage`, findings of kind `ews.verdict.<v>`); nothing is decided here.
 */

export type Verdict = "noise" | "watch" | "watchlist" | "sicr" | "utp";

export const AGENT_ID = "ews.triage";
export const TRIAGE_GOAL = "Triage this period's warnings";

export const VERDICT_LABEL: Record<Verdict, string> = {
  noise: "Noise", watch: "Watch", watchlist: "Watchlist", sicr: "SICR", utp: "UTP",
};

const ORDER: Verdict[] = ["noise", "watch", "watchlist", "sicr", "utp"];

export function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && (ORDER as string[]).includes(v);
}

/** Chip tone per verdict, in the Early Warning band palette (proposals in the alert tones). */
export function verdictTone(v: Verdict): string {
  switch (v) {
    case "utp": return "bg-negative-muted text-negative border-negative/30";
    case "sicr": return "bg-warning-muted text-warning border-warning/30";
    case "watchlist": return "bg-accent-muted text-accent border-accent/30";
    default: return "bg-surface-muted text-text-secondary border-border";
  }
}

export interface VerdictFinding {
  kind?: string;
  data?: { borrower_id?: string; verdict?: string } | null;
}

/** `{borrower_id: verdict}` from a run's findings. */
export function verdictMap(findings: VerdictFinding[] | null | undefined): Record<string, Verdict> {
  const out: Record<string, Verdict> = {};
  for (const f of findings ?? []) {
    if (!f?.kind?.startsWith("ews.verdict.")) continue;
    const id = f.data?.borrower_id;
    const v = f.data?.verdict;
    if (id && isVerdict(v)) out[id] = v;
  }
  return out;
}

export interface RunRow {
  run_id: string; goal?: string | null; scope?: string | null; status?: string | null; created_at?: string | null;
}

/** The period triage runs of a book, newest first (borrower and sector runs carry their own scope). */
export function periodRuns(runs: RunRow[] | null | undefined, domain: string): RunRow[] {
  return (runs ?? [])
    .filter((r) => (r.scope ?? "") === domain && (r.status === "completed" || r.status === "partial"))
    .sort((a, b) => String(b.created_at ?? "").localeCompare(String(a.created_at ?? "")));
}

/** A run's period, from its output or its context (the run resolves an empty period to the latest). */
export function runPeriod(run: { output?: { period?: string | null } | null; context?: { period?: string | null } | null }): string {
  return String(run.output?.period || run.context?.period || "");
}
