/**
 * R16 m (M2): pure helpers of the Early Warning segment analysis (no React, testable with node --test).
 */

export interface AnalysisScope {
  segment?: string; cls?: string; sub?: string; dims?: Record<string, string | undefined>;
}

/** The card key the analysis belongs to: the same key the card carries (`ews-card-<key>`). */
export function analysisKey(s: AnalysisScope): string {
  const dimValues = Object.values(s.dims ?? {}).filter((v): v is string => Boolean(v));
  return s.sub || s.cls || (dimValues.length ? dimValues[dimValues.length - 1] : "") || s.segment || "portfolio";
}

/** "+3" / "−2" / "0" for a change on the prior period; "—" when there is no prior period. */
export function change(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v > 0 ? `+${v.toLocaleString("en-US")}` : v < 0 ? `−${Math.abs(v).toLocaleString("en-US")}` : "0";
}
