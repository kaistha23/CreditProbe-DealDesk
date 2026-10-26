/**
 * R6 E4: the shared shape of a chart explanation and the helpers that build its
 * example from the chart's current figures. Pure (no React, no path aliases) so the
 * node tests import it directly. Rendered by ./chart-explain.tsx.
 *
 * Four short parts, in plain words for a non-specialist:
 *   - shows: what the chart shows;
 *   - formula: how each series is calculated (one line per series, with the formula);
 *   - read: how to read it, with an example built from the chart's current figures;
 *   - lookFor: what to look for.
 * Text may carry **bold** spans.
 */

export interface ChartExplain {
  shows: string;
  formula: string[];
  read: string;
  lookFor: string;
}

/** True when every part of the explanation has text. */
export function isCompleteExplain(e: ChartExplain | null | undefined): boolean {
  if (!e) return false;
  return Boolean(e.shows?.trim()) && e.formula.length > 0 && e.formula.every((f) => Boolean(f?.trim()))
    && Boolean(e.read?.trim()) && Boolean(e.lookFor?.trim());
}

/** A number for an example sentence: thousands separated, `dp` decimals. */
export function exNum(v: number | null | undefined, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return "n/a";
  return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

/** a / b as a percentage string, or "n/a". */
export function exPct(a: number | null | undefined, b: number | null | undefined, dp = 1): string {
  if (a == null || b == null || !b) return "n/a";
  return `${exNum((100 * a) / b, dp)}%`;
}

/** SAR millions for an example sentence. */
export function exSarM(v: number | null | undefined, dp = 1): string {
  return v == null || !Number.isFinite(v) ? "n/a" : `SAR ${exNum(v, dp)}m`;
}

/** The last element with a usable value of `pick`, or undefined. */
export function lastWith<T>(rows: T[], pick: (r: T) => number | null | undefined): T | undefined {
  for (let i = rows.length - 1; i >= 0; i--) {
    const v = pick(rows[i]);
    if (v != null && Number.isFinite(v)) return rows[i];
  }
  return undefined;
}

/** The row with the largest value of `pick`, or undefined. */
export function maxBy<T>(rows: T[], pick: (r: T) => number | null | undefined): T | undefined {
  let best: T | undefined;
  let bv = -Infinity;
  for (const r of rows) {
    const v = pick(r);
    if (v != null && Number.isFinite(v) && v > bv) { bv = v; best = r; }
  }
  return best;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026Q2" -> "Q2 26", "2026-06" -> "Jun 26", anything else unchanged. */
export function periodLabel(period: string | null | undefined): string {
  if (!period) return "";
  const q = /^(\d{4})Q([1-4])$/.exec(period);
  if (q) return `Q${q[2]} ${q[1].slice(2)}`;
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${m[1].slice(2)}` : period;
}
