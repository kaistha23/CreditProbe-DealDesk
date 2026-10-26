/**
 * Early Warning card trends: when a segment is quiet (PLAN_R6 E5).
 *
 * A card shows three sparklines (warned, default-entry rate, high/critical
 * EAD). Where all three are zero in every period shown, three flat lines say
 * nothing; the card shows one line instead: "No warnings in 6 quarters".
 * Pure (no React, no aliases) so node --test can run it.
 */

export interface QuietTrendPoint {
  period: string;
  customers_warned: number | null;
  odr_pct: number | null;
  exposure_severe: number | null;
}

/** "quarters" for 2026Q2-style periods, "months" for 2026-08-style ones. */
export function periodWord(periods: string[], n: number): string {
  const quarterly = periods.length > 0 && periods.every((p) => /^\d{4}Q[1-4]$/.test(p));
  const monthly = periods.length > 0 && periods.every((p) => /^\d{4}-\d{2}$/.test(p));
  const unit = quarterly ? "quarter" : monthly ? "month" : "period";
  return n === 1 ? unit : `${unit}s`;
}

const zero = (v: number | null | undefined) => v == null || Math.abs(v) < 1e-9;

/** True when every period has zero warned, zero default-entry and zero high/critical EAD. */
export function isQuietTrend(trend: QuietTrendPoint[]): boolean {
  return trend.length > 0
    && trend.every((p) => zero(p.customers_warned) && zero(p.odr_pct) && zero(p.exposure_severe))
    // At least one real zero (not only missing values): a trend with no data is not "no warnings".
    && trend.some((p) => p.customers_warned === 0 || p.odr_pct === 0 || p.exposure_severe === 0);
}

/** "No warnings in 6 quarters" for a quiet trend, else null (show the sparklines). */
export function quietTrendNote(trend: QuietTrendPoint[]): string | null {
  if (!isQuietTrend(trend)) return null;
  const periods = trend.map((p) => p.period);
  return `No warnings in ${trend.length} ${periodWord(periods, trend.length)}`;
}
