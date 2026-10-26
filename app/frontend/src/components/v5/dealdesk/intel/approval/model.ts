/**
 * R13 Session IA: the approval-intelligence response shapes and their pure helpers (no path aliases, so they run
 * under `node --test`). Server: backend/dealdesk/intel/approval (GET /api/v1/dealdesk/intel/approval/{id}/...).
 */

export type Source = {
  domain?: string; relation?: string; key?: Record<string, unknown>; column?: string; period?: string | null; version?: number | null;
  engine?: string; terms?: unknown; note?: string;
};
export type Fig = { value: number | null; unit: string; source: Source; label?: string };
export type Tone = "positive" | "negative" | "warning" | "neutral";

// ---------------------------------------------------------------- committee challenger
export type Question = {
  id: string; rank: number; source: string; score: number; question: string; answer: string; evidence: (Fig | { value: null; source: Source })[];
  avoided: boolean; avoided_reason: string; asks_for: string;
};
export type Challenger = {
  proposal_id: string; obligor: string; headline: string; questions: Question[];
  avoided: { id: string; question: string; reason: string; source: string }[]; considered: number; method: string; trace_id?: string;
};

// ---------------------------------------------------------------- reverse solver
export type Change = { field: string; ask: unknown; value: unknown; unit: string; text: string };
export type StressCheck = { verdict: string | null; tier?: string | null; worst_breaking_severity?: string | null; why?: string;
  breaking?: { scenario: string; severity: string; breaks: string[] }[] } | null;
export type Candidate = {
  label: string; family: string; also_reached_by: string[]; distance: number; changes: Change[]; lifetime_raroc: Fig; sva: Fig; rwa_y1: Fig;
  el_y1: Fig; approval: { level: string; approvable: boolean }; stress: StressCheck; terms: Record<string, unknown>;
};
export type Failure = { kind: "hurdle" | "limit" | "policy" | "stress"; label: string; text: string; name?: string };
export type Reverse = {
  proposal_id: string; obligor: string; currency: string; headline: string; approvable_as_asked: boolean; failures: Failure[];
  candidates: Candidate[]; counter_offer: (Candidate & { headline: string; rm_text: string; note: string | null; client_asks: string[] }) | null;
  termless_blockers?: string[]; ask: { lifetime_raroc: Fig; hurdle: Fig; sva: Fig }; method: string; seconds: number; trace_id?: string;
};

// ---------------------------------------------------------------- security optimiser
export type Delta = { lgd_y1: Fig; el_lifetime_pv: Fig; rwa_y1: Fig; capital_y1: Fig; lifetime_raroc: Fig; sva: Fig };
export type SecurityItem = {
  id: string; kind: "collateral" | "guarantee" | "cash"; type: string; label: string; in_ask: boolean; value: Fig | null; recovery_value: Fig | null;
  standalone: Delta; marginal_in_ask?: Delta; cost_sar_mn: Fig; crm: { eligible: boolean; basis: string }; clears_alone: boolean;
  sva_per_sar_tied: Fig | null;
};
export type Package = { label: string; clears: boolean; text: string; cost_sar_mn: Fig; lifetime_raroc: Fig; lgd_y1: Fig; rwa_y1: Fig; sva: Fig;
  hard_breaches: string[] };
/** R14 G (K30): security the obligor could add (a what-if on a copy of the deal, not an item on file). */
export type AddOn = {
  id: string; kind: "guarantee" | "collateral" | "assignment"; label: string; detail: string; hypothetical: true; cost_sar_mn: Fig;
  standalone: Delta; clears_alone: boolean; on_ask?: Delta; on_ask_raroc?: Fig; clears_on_ask?: boolean; text: string;
};
export type Security = {
  proposal_id: string; obligor: string; headline: string; items: SecurityItem[]; ask_package: Package | null; cheapest_package: Package | null;
  best_package: Package | null; cost_measure: string; method: string; trace_id?: string;
  /** R14 G (K30): every package evaluated (cheapest first), what the obligor could add, "tied up" in words, the reverse solver link. */
  combinations?: Package[]; add_ons?: AddOn[]; tied_up_text?: string; needs_price?: boolean; reverse_href?: string;
};

// ---------------------------------------------------------------- decision consistency
export type Decision = { decision: string; rank: number | null; by: string; authority: string; pending: boolean };
export type DealCard = { proposal_id: string; obligor: string; sector: string; rating: string; rm: string; amount: Fig; raroc: Fig;
  hurdle: Fig; decision: Decision; similarity?: number };
export type Pair = { better: string; worse: string; status: "explained" | "partly explained" | "not explained"; text: string; similarity: number;
  rms: string[]; decided_by: string[] };
export type Consistency = {
  proposal_id: string; obligor: string; headline: string; decision: Decision; similar: DealCard[]; decided_differently: Pair[];
  desk_vs_committee: { text: string } | null; data_note: string | null; method: string; trace_id?: string;
};

// ---------------------------------------------------------------- helpers

export function pct(x: number | null | undefined, dp = 1): string {
  return x === null || x === undefined || !Number.isFinite(x) ? "–" : `${(x * 100).toFixed(dp)}%`;
}

export function sarm(x: number | null | undefined, ccy = "SAR"): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const a = Math.abs(x);
  return a >= 1000 ? `${ccy} ${(x / 1000).toFixed(2)}bn` : `${ccy} ${x.toFixed(a >= 10 ? 1 : 2)}m`;
}

/** A signed delta in the figure's own unit ("−4.2 pp", "−17.0m", "+0.26m"). */
export function delta(f: Fig | null | undefined): string {
  if (!f || f.value === null || !Number.isFinite(f.value)) return "–";
  const v = f.value;
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (f.unit === "share") return `${s}${(a * 100).toFixed(1)} pp`;
  return `${s}${a.toFixed(a >= 10 ? 1 : 2)}m`;
}

/** "deal_desk · dd_condition · condition_id=CO-TWA-1 · status" or "engine.analyse on dd_deal R12-TWA". */
export function sourceLine(s: Source | null | undefined): string {
  if (!s) return "–";
  const key = Object.entries(s.key ?? {}).map(([k, v]) => `${k}=${String(v)}`).join(", ");
  const head = [s.domain, s.relation, key, s.column].filter(Boolean).join(" · ");
  return s.engine ? `${s.engine} on ${head}` : head;
}

export function statusTone(s: Pair["status"]): Tone {
  return s === "explained" ? "positive" : s === "partly explained" ? "warning" : "negative";
}

export function decisionTone(d: string): Tone {
  return d === "approve" ? "positive" : d === "decline" ? "negative" : "warning";
}

export function failureTone(k: Failure["kind"]): Tone {
  return k === "limit" ? "negative" : "warning";
}

/** The question list split for the panel: what committee will ask, and how many the proposal leaves unanswered. */
export function questionSummary(c: Pick<Challenger, "questions">): { total: number; avoided: number; line: string } {
  const total = c.questions.length;
  const avoided = c.questions.filter((q) => q.avoided).length;
  return { total, avoided, line: `${total} question${total === 1 ? "" : "s"}, ${avoided} not answered in the proposal` };
}

/** Items in the order a risk manager reads them: most SVA per SAR tied up first, items without a cost last. */
export function rankItems(items: SecurityItem[]): SecurityItem[] {
  return [...items].sort((a, b) => (b.sva_per_sar_tied?.value ?? -Infinity) - (a.sva_per_sar_tied?.value ?? -Infinity)
    || (b.standalone.sva.value ?? 0) - (a.standalone.sva.value ?? 0));
}

export function pairCounts(p: Pair[]): Record<Pair["status"], number> {
  const out = { "explained": 0, "partly explained": 0, "not explained": 0 } as Record<Pair["status"], number>;
  for (const x of p) out[x.status] += 1;
  return out;
}
