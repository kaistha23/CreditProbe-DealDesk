/**
 * Registered presentation-layer exception FX-1 (docs/v5/FROZEN_EXCEPTIONS.md).
 *
 * The global rating order applied where the frozen Cockpit renders a chart or
 * sorts a table: a chart whose categories are ALL rating grades is drawn
 * AAA → D; a table sorted on a rating column sorts by the scale, not the
 * alphabet. Nothing else is touched: no value, label, title, unit, display
 * string or row is changed, added or removed -- only the order of the points
 * a chart already has, and the comparison a table sort already makes.
 */
import { RATING_ORDER, ratingRank } from "./ratings.ts";

const GRADES = new Set<string>(RATING_ORDER);

function isGrade(v: unknown): boolean {
  return typeof v === "string" && GRADES.has(v.trim().toUpperCase());
}

/** The chart, with its points in rating order when every category is a grade. */
export function withRatingOrder<T extends { points?: ({ label?: unknown } | null)[] | null }>(chart: T): T {
  const points = chart.points ?? [];
  if (points.length < 2 || !points.every((p) => p && isGrade(p.label))) return chart;
  const ordered = [...points].sort((a, b) => ratingRank(String(a?.label)) - ratingRank(String(b?.label)));
  return { ...chart, points: ordered };
}

/** Rating comparison for a table sort, or null when either value is not a grade. */
export function compareRatingValues(a: unknown, b: unknown): number | null {
  return isGrade(a) && isGrade(b) ? ratingRank(String(a)) - ratingRank(String(b)) : null;
}
