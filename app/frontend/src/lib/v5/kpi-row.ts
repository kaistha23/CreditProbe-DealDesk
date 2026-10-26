/**
 * PLAN_R10 S2 / G-TILES: the shared compact KPI row helpers (pure, tested).
 *
 * Every screen shows at most 4 KPI tiles, in one row. A tile carries one bold key number, one short sub-line and,
 * where it is a subset, "n of N · x% of exposure". The React component is `components/v5/core/kpi-row.tsx`.
 */

import { count, pct, type Num } from "./format.ts";

/** The hard ceiling of G-TILES. */
export const KPI_ROW_MAX = 4;

export interface KpiShare {
  /** The subset count (e.g. warned borrowers). */
  n: Num;
  /** The population count (e.g. all borrowers on the book). */
  of: Num;
  /** The subset's exposure, in any unit, same unit as `exposureTotal`. */
  exposure?: Num;
  /** The population exposure. */
  exposureTotal?: Num;
  /** What the percentage is "of"; default "exposure" ("of the book", "of balance" are fine). */
  basis?: string;
}

function finite(v: Num): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** "n of N": "214 of 1,250". Empty when either side is missing. */
export function nOfN(n: Num, of: Num): string {
  return finite(n) && finite(of) ? `${count(n)} of ${count(of)}` : "";
}

/** "x% of exposure" from two amounts; empty when the total is missing or zero. */
export function shareOf(part: Num, total: Num, basis = "exposure"): string {
  if (!finite(part) || !finite(total) || total === 0) return "";
  return `${pct(part / total)} of ${basis}`;
}

/** The tile sub-line for a subset: "214 of 1,250 · 18.4% of exposure" (either half may be absent). */
export function shareLine(s: KpiShare): string {
  return [nOfN(s.n, s.of), shareOf(s.exposure, s.exposureTotal, s.basis)].filter(Boolean).join(" · ");
}

/**
 * The tiles a row actually renders: never more than 4. Extra tiles are dropped (and reported in development) rather
 * than wrapped onto a second line, because G-TILES says one row, always.
 */
export function clampTiles<T>(tiles: readonly T[], max = KPI_ROW_MAX): T[] {
  return tiles.slice(0, Math.min(max, KPI_ROW_MAX));
}

/**
 * Grid columns for n tiles: always one row at >= 900 px; 2×2 below 900 px when there are 3 or 4 tiles.
 * Static class strings so Tailwind can see them.
 */
export function gridClass(n: number): string {
  switch (Math.max(1, Math.min(n, KPI_ROW_MAX))) {
    case 1: return "grid-cols-1";
    case 2: return "grid-cols-2";
    case 3: return "grid-cols-2 min-[900px]:grid-cols-3";
    default: return "grid-cols-2 min-[900px]:grid-cols-4";
  }
}
