/**
 * R13 Session Q: the financial-quality detector's response (GET /api/v1/dealdesk/fin-quality/{pid} and /book/{fid}) and
 * the pure helpers the panel uses. No React here, so `npm test` covers it.
 */

export type Severity = "critical" | "high" | "medium" | "low" | "info" | "none" | "not_assessable";
export type Grade = "A" | "B" | "C" | "D";

export interface Source { relation: string; key?: Record<string, unknown>; period?: string | null; domain?: string | null }

export interface Signal {
  code: string; family: string; family_label: string; label: string;
  value: number | string | null; display: string; unit: string;
  threshold: number | string | null; op: string; threshold_display: string;
  flag: boolean | null; severity: Severity; period: string | null;
  source: Source | null; sources: Source[]; text: string; basis: string; policy_ref: string; note: string;
}

export interface FamilySummary { family: string; label: string; signals: number; flagged: number; assessable: number; worst: Severity | null }

export interface GradeInfo {
  grade: Grade; meaning: string; points: number; flagged: number; assessable: number; signals: number; coverage: number; limited: boolean;
  by_severity: Record<"critical" | "high" | "medium" | "low", number>; rule: string;
}

export interface FinQuality {
  subject: { kind: "deal" | "book"; id: string; proposal_id: string | null; facility_id: string | null; name: string; sector: string | null;
             currency: string; periods: string[]; entity: string | null; scope: string | null };
  as_of: string; period: string | null; mode: "detail" | "summary" | "book" | "none";
  grade: GradeInfo; signals: Signal[]; flagged: string[]; families: FamilySummary[]; headline: string; lines: string[]; sources: string[];
}

export const BASE = "/api/v1/dealdesk/fin-quality";

export function finQualityUrl(t: { proposalId?: string | null; facilityId?: string | null }): string | null {
  if (t.proposalId) return `${BASE}/${encodeURIComponent(t.proposalId)}`;
  if (t.facilityId) return `${BASE}/book/${encodeURIComponent(t.facilityId)}`;
  return null;
}

export const SEV_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4, none: 5, not_assessable: 6 };

export type Tone = "negative" | "warning" | "positive" | "neutral" | "accent";

export function gradeTone(g: Grade | string | null | undefined): Tone {
  return g === "D" ? "negative" : g === "C" ? "warning" : g === "B" ? "accent" : g === "A" ? "positive" : "neutral";
}

export function sevTone(s: Severity | null | undefined): Tone {
  return s === "critical" || s === "high" ? "negative" : s === "medium" ? "warning" : s === "low" ? "accent" : s === "none" ? "positive" : "neutral";
}

/** The status word a row shows: the severity of a breach, "within" when inside the threshold, "no data" when not assessable. */
export function statusLabel(s: Pick<Signal, "flag" | "severity">): string {
  if (s.flag === null) return "no data";
  if (s.flag === false) return "within";
  return s.severity;
}

/** Signals in panel order: flagged first by severity, then within threshold, then not assessable; family order kept inside. */
export function ordered(signals: Signal[], families: string[]): Signal[] {
  const fi = (f: string) => { const i = families.indexOf(f); return i < 0 ? 99 : i; };
  const bucket = (s: Signal) => (s.flag === true ? 0 : s.flag === false ? 1 : 2);
  return [...signals].sort((a, b) => bucket(a) - bucket(b) || (a.flag ? SEV_RANK[a.severity] - SEV_RANK[b.severity] : 0) || fi(a.family) - fi(b.family) || a.code.localeCompare(b.code));
}

/** "10 of 24 flagged · 22 assessable" (with "limited data" below 40% coverage). */
export function countsLine(g: Pick<GradeInfo, "flagged" | "signals" | "assessable" | "limited">): string {
  return `${g.flagged} of ${g.signals} flagged · ${g.assessable} assessable${g.limited ? " · limited data" : ""}`;
}

/** "dd_financials_detail · FY2025" — the source line under a value. */
export function sourceLine(s: Pick<Signal, "source" | "period">): string {
  const rel = s.source?.relation ?? "Data Domains";
  return s.period ? `${rel} · ${s.period}` : rel;
}
