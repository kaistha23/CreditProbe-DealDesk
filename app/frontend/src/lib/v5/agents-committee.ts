/**
 * The Deal Desk committee pack (backend/agents_v5/dealdesk/agent.py `conclude`), typed, plus its pure helpers.
 */

export interface CommitteePack {
  headline: string;
  decision: string;
  proposal_id: string;
  name: string;
  goal_type: string;
  why: { text: string; evidence: string[]; good: boolean }[];
  counter_proposal: { label: string; source: string; step: string; raroc: number; sva?: number | null; ecl?: number | null;
    amount?: number | null; conditions?: (string | null)[] } | null;
  forward_risk: { answer: string; figures: Record<string, number>; step: string } | null;
  stress: { answer: string; step: string } | null;
  pipeline: { answer: string; available?: boolean } | null;
  findings_by_severity: Record<string, unknown[]>;
  conditions: { id: string; what: string; owner: string; due: string; status: string }[];
  open_questions: { question: string; rule_id?: string }[];
  not_verified: { item: string; reason: string; step: string }[];
  precedent: { summary: string } | null;
  draft: { draft_id: string; docx: string; score?: { total?: number } } | null;
  doa: { level?: string } | null;
  review_sheet_docx: string | null;
  timing?: { run_ms: number };
}

export function packTone(decision: string): "positive" | "negative" | "warning" | "neutral" {
  const d = decision.toLowerCase();
  if (d.startsWith("approve as proposed")) return "positive";
  if (d.startsWith("do not") || d.startsWith("decline")) return "negative";
  if (d.startsWith("approve")) return "warning";
  return "neutral";
}

export function packFigure(v: number | null | undefined, kind: "pct" | "m" | "m3" | "s"): string {
  if (v == null || !Number.isFinite(v)) return "–";
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "m") return `${v.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}m`;
  if (kind === "m3") return `${v.toFixed(3)}m`;
  return `${v.toFixed(1)} s`;
}
