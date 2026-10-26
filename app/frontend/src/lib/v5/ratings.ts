/**
 * Credit rating order, best to worst, for every v5 Early Warning view that
 * lists or charts ratings. A rating the scale does not know sorts after D,
 * so an unexpected grade is shown last rather than dropped or misplaced.
 *
 * Plain TypeScript (no enums, no imports) so `node --test
 * --experimental-strip-types` runs it as-is.
 */

export const RATING_ORDER: readonly string[] = [
  "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
  "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-",
  "CCC", "CC", "C", "D",
];

const RANK: ReadonlyMap<string, number> = new Map(RATING_ORDER.map((r, i) => [r, i]));

/** Position on the scale (0 = AAA); unknown, empty or missing ratings rank after D. */
export function ratingRank(rating: string | null | undefined): number {
  if (rating === null || rating === undefined) return RATING_ORDER.length;
  const rank = RANK.get(String(rating).trim().toUpperCase());
  return rank === undefined ? RATING_ORDER.length : rank;
}

/** Comparator, best first: negative when `a` is better than `b`. Unknowns tie, by name. */
export function compareRatings(a: string | null | undefined, b: string | null | undefined): number {
  const diff = ratingRank(a) - ratingRank(b);
  if (diff !== 0) return diff;
  return String(a ?? "").localeCompare(String(b ?? ""));
}

/** A copy of `items` ordered by the rating held in `key`, best first. Stable. */
export function sortByRating<T>(items: readonly T[], key: keyof T): T[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((x, y) => compareRatings(x.item[key] as unknown as string, y.item[key] as unknown as string)
      || x.index - y.index)
    .map(({ item }) => item);
}

// ------------------------------------------------------------------ tables, axes, legends (PLAN_R6 E3)
// The shared sort for every table, axis, legend and dropdown whose category is a rating grade. The backend
// mirror is `order_table` / `order_chart_rows` / `axis_order` in backend/v5common/ratings.py.
//
//   orderRatingTable(rows, columns)   rows of a table whose FIRST column holds grades, AAA to D
//   orderRatingRows(rows, key)        rows ordered by `key` when that column holds grades, else unchanged
//   ratingAxis(values)                Plotly axis props: { categoryorder: "array", categoryarray } or {}
//   ratingAxisOrder(values)           the grades present, AAA to D, then anything else
//   ratingsInOrder(labels)            whether the grades of a rendered label sequence read AAA to D

/** Rows a rating table may carry beside its grades (they keep their place after D). */
const TOTAL_LIKE = /^\s*(total|overall|all|book|portfolio|unrated|not rated|n\/?a|other|others|—|-)?\s*$/i;

/** Whether a value is a grade of the global scale. */
export function isGrade(v: unknown): boolean {
  return typeof v === "string" && RANK.has(v.trim().toUpperCase());
}

/** A column key or label that names a rating (rating, grade, internal_rating, rating_current ...). */
export function isRatingName(name: unknown): boolean {
  return typeof name === "string" && /rating|grade/i.test(name);
}

/** At least two grades, anything else a total-like row (Total, Overall, Unrated, blank). */
export function isRatingValues(values: readonly unknown[]): boolean {
  let grades = 0;
  for (const v of values) {
    if (isGrade(v)) grades += 1;
    else if (!(v === null || v === undefined || (typeof v === "string" && TOTAL_LIKE.test(v)))) return false;
  }
  return grades >= 2;
}

function cellOf(row: unknown, key: string | number): unknown {
  if (Array.isArray(row)) return row[key as number];
  return row && typeof row === "object" ? (row as Record<string | number, unknown>)[key] : undefined;
}

/** Rows (objects or arrays) ordered by the grade in `key`, best first, when that column holds grades; else a copy. Stable. */
export function orderRatingRows<T>(rows: readonly T[], key: string | number): T[] {
  if (!isRatingValues(rows.map((r) => cellOf(r, key)))) return [...rows];
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => ratingRank(cellOf(a.row, key) as string) - ratingRank(cellOf(b.row, key) as string) || a.index - b.index)
    .map(({ row }) => row);
}

/**
 * A table's rows in the global rating order when its first (category) column holds grades; else unchanged.
 * `columns` may be keys or `{ key }` objects; array rows (markdown tables) use column 0.
 */
export function orderRatingTable<T>(rows: readonly T[], columns?: readonly (string | { key: string })[]): T[] {
  if (!rows.length) return [];
  const first = columns?.[0];
  const key: string | number = Array.isArray(rows[0]) || first === undefined ? 0 : typeof first === "string" ? first : first.key;
  return orderRatingRows(rows, key);
}

/** The category order for a rating axis, legend or dropdown: the grades present, AAA to D, then anything else as given. */
export function ratingAxisOrder<T>(values: readonly T[]): T[] {
  const seen = [...new Set(values)];
  return seen
    .map((v, index) => ({ v, index }))
    .sort((a, b) => ratingRank(a.v as unknown as string) - ratingRank(b.v as unknown as string) || a.index - b.index)
    .map(({ v }) => v);
}

/** Plotly axis props pinning a rating category axis to the global order; {} when the values are not grades. */
export function ratingAxis(values: readonly unknown[]): { categoryorder?: "array"; categoryarray?: unknown[] } {
  return isRatingValues(values) ? { categoryorder: "array", categoryarray: ratingAxisOrder(values) } : {};
}

/** Whether the grades in a rendered label sequence (table column, axis ticks, legend) read AAA to D. */
export function ratingsInOrder(labels: readonly unknown[]): boolean {
  const ranks = labels.filter(isGrade).map((v) => ratingRank(v as string));
  return ranks.every((r, i) => i === 0 || ranks[i - 1] <= r);
}
