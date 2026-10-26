/**
 * R16 M5: the lens planner by persona, client side. A request that names an audience ("CRO dashboard",
 * "dashboard for an analyst", "risk analyst view") first shows a Metric plan card: per measure its definition, formula,
 * SQL and source relation (or "not available: why"); the user ticks measures in or out and builds the dashboard.
 *
 * Pure (node-testable): the word check that decides whether to ask the service for a plan, and the card's selection
 * logic. The service (`POST /plan`) decides the persona; `mentionsPersona` only avoids a round trip on plain requests.
 */

export type PersonaKey = "cro" | "analyst" | "cco" | "rm_head";

export interface PlanMetric {
  id: string; kind: "kpi" | "tile"; label: string; definition: string; formula: string; sql: string; relation: string;
  sources: string[]; tile_type: string; chart: string; available: boolean; reason: string; include: boolean; metric?: string;
}
export interface MetricPlan {
  persona: PersonaKey; persona_label: string; short: string; book: "corporate" | "retail"; scope_label: string; period: string;
  title: string; request: string; plain_words: string[]; relation_note: string; metrics: PlanMetric[];
}
export type PlanReply = MetricPlan | { persona: null };

/** Mirrors backend/lenses_v5/personas.py words (the service has the last word). */
const WORDS = [
  "cro", "chief risk officer", "risk committee", "board risk", "brc",
  "analyst", "analysts", "risk analyst", "credit analyst", "portfolio analyst",
  "cco", "chief credit officer", "credit committee", "head of credit",
  "branch head", "branch manager", "head of branch", "rm head", "head of rms", "rm dashboard", "rm view", "for an rm", "for my rms",
  "team leader", "regional head",
];

export function mentionsPersona(text: string): boolean {
  const t = ` ${text.toLowerCase()} `;
  return WORDS.some((w) => new RegExp(`(?<![a-z])${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![a-z])`).test(t));
}

export function isPlan(r: PlanReply | null | undefined): r is MetricPlan {
  return Boolean(r && r.persona);
}

/** The measures ticked when the card opens: every available one the plan includes. */
export function initialSelection(plan: MetricPlan): Set<string> {
  return new Set(plan.metrics.filter((m) => m.available && m.include).map((m) => m.id));
}

/** Tick or untick a measure; a measure the data cannot support never becomes ticked. */
export function toggle(plan: MetricPlan, selected: Set<string>, id: string): Set<string> {
  const m = plan.metrics.find((x) => x.id === id);
  const next = new Set(selected);
  if (!m || !m.available) return next;
  if (next.has(id)) next.delete(id); else next.add(id);
  return next;
}

/** The ids sent with "Build this dashboard", in plan order. */
export function includeIds(plan: MetricPlan, selected: Set<string>): string[] {
  return plan.metrics.filter((m) => m.available && selected.has(m.id)).map((m) => m.id);
}

/** A dashboard needs at least one chart or table (the key-figure strip alone is not a dashboard). */
export function canBuild(plan: MetricPlan, selected: Set<string>): boolean {
  return plan.metrics.some((m) => m.kind === "tile" && m.available && selected.has(m.id));
}

export function counts(plan: MetricPlan, selected: Set<string>): { tiles: number; kpis: number; unavailable: number } {
  const on = plan.metrics.filter((m) => m.available && selected.has(m.id));
  return { tiles: on.filter((m) => m.kind === "tile").length, kpis: on.filter((m) => m.kind === "kpi").length,
           unavailable: plan.metrics.filter((m) => !m.available).length };
}

/** "SQL: the relation it reads" in the card's last column ("corp", "ret"; the appetite tile also reads the appetite file). */
export function relationLabel(m: PlanMetric): string {
  const r = m.relation || "";
  if (r.startsWith("corp")) return r === "corp" ? "corp (corporate facility-quarter)" : r;
  if (r.startsWith("ret")) return r === "ret" ? "ret (retail account-month)" : r;
  return r;
}
