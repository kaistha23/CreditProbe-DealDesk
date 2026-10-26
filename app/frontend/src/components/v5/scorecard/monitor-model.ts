/**
 * R16 M8: the pure rules of the Scorecard monitoring screens (no React, unit-tested): dates and names as a banker
 * writes them, the short criterion words, the sparkline geometry, the newspaper layout and the starter asks.
 */

export type CriterionKey = "discrimination" | "calibration" | "stability" | "overrides" | "migration" | "data_quality" | "usage" | "cycle" | "findings";

export const CRITERION_SHORT: Record<CriterionKey, string> = {
  discrimination: "Ranking", calibration: "PDs", stability: "Population", overrides: "Overrides", migration: "Grades",
  data_quality: "Data", usage: "Use", cycle: "Cycle", findings: "Findings",
};

/** "2026-10-21" → "21 Oct 2026"; periods ("2025Q2", "2025-08") pass through. */
export function day(iso: string): string {
  if (!/^\d{4}-\d{2}-\d{2}/.test(iso)) return iso;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** Owner without the role in brackets. */
export const person = (owner: string) => owner.split(" (")[0];

/** The ask a deep dive's "Run a full validation" sends. */
export const fullValidationAsk = (name: string) => `Run a full MMSG validation of the ${name}`;

/** The front page's centred Ask: a short placeholder (M3, at most 60 characters) and starter chips. */
export const ASK_PLACEHOLDER = "Ask, e.g. “Validate the SME scorecard”";
export const ASK_STARTERS = [
  { label: "Full MMSG validation: SME", send: "Run a full MMSG validation of the SME Scorecard" },
  { label: "Full MMSG validation: retail application", send: "Run a full MMSG validation of the Retail Application Scorecard" },
  { label: "Validate the behavioural scorecard", send: "Validate the retail behavioural scorecard" },
  { label: "Which scorecards can you validate?", send: "Which scorecards can you validate?" },
];

/** Points of a sparkline in a w × h box (null values break the line; a flat series sits in the middle). */
export function sparkPoints(values: (number | null)[], w = 96, h = 24, pad = 2): { x: number; y: number }[] {
  const nums = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (!nums.length) return [];
  const lo = Math.min(...nums);
  const hi = Math.max(...nums);
  const span = hi - lo || 1;
  const step = values.length > 1 ? (w - 2 * pad) / (values.length - 1) : 0;
  const out: { x: number; y: number }[] = [];
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) return;
    const y = hi === lo ? h / 2 : h - pad - ((v - lo) / span) * (h - 2 * pad);
    out.push({ x: Math.round((pad + i * step) * 10) / 10, y: Math.round(y * 10) / 10 });
  });
  return out;
}

/** The newspaper: the first breach is the lead story; the rest fill two columns in rank order. */
export function newspaper<T>(items: T[]): { lead: T | null; columns: [T[], T[]] } {
  const [lead, ...rest] = items;
  const left: T[] = [];
  const right: T[] = [];
  rest.forEach((x, i) => (i % 2 === 0 ? left : right).push(x));
  return { lead: lead ?? null, columns: [left, right] };
}

/** The front page headline: "10 breaches across 3 scorecards, 10 red". */
export function frontHeadline(n: number, scorecards: number, red: number): string {
  if (!n) return `All ${scorecards} scorecards are inside their limits`;
  return `${n} breach${n === 1 ? "" : "es"} across ${scorecards} scorecard${scorecards === 1 ? "" : "s"}, ${red} red`;
}
