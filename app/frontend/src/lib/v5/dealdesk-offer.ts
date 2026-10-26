/**
 * PLAN_R10 D4: what Optimise shows, the same for every deal. Pure functions over engine results (no formatting, no
 * fetch), so the screen and the tests read the same numbers:
 *
 *   rarocByTenor   lifetime RAROC against tenor at the asked price, read from the iso-RAROC grid (margin x tenor)
 *   bestTenorRate  the longest tenor that clears the hurdle at the asked price, and the lowest price that clears it
 *                  at the asked tenor (from the same grid; the engine's breakeven margin when the grid has none)
 *   bestOffers     the recommended structure (closest to the ask that clears) and two alternatives, each a distinct
 *                  engine solution with RAROC and SVA
 */
import type { Grid, OptimizeResult, Solution, Terms } from "./dealdesk.ts";

const xs = (g: Grid): number[] => g.x_values ?? (Array.isArray(g.x) ? g.x : []);
const ys = (g: Grid): number[] => g.y_values ?? (Array.isArray(g.y) ? g.y : []);
const nearest = (vals: number[], v: number): number => {
  let best = -1;
  vals.forEach((x, i) => { if (best < 0 || Math.abs(x - v) < Math.abs(vals[best] - v)) best = i; });
  return best;
};

/** The price lever the grid runs over (margin for funded asks, commission for LGs and LCs). */
export const priceKey = (g: Grid): "margin_bps" | "commission_bps" => (g.x === "commission_bps" ? "commission_bps" : "margin_bps");

/** RAROC against tenor at the asked price (the grid column nearest the ask). Empty when the grid is not 2-D. */
export function rarocByTenor(g: Grid, ask: Terms): { tenor: number; raroc: number }[] {
  const x = xs(g); const y = ys(g);
  const z = g.values as number[][];
  if (!x.length || !y.length || !Array.isArray(z[0])) return [];
  const j = nearest(x, g.ask?.x ?? ask[priceKey(g)]);
  return y.map((t, i) => ({ tenor: t, raroc: z[i]?.[j] })).filter((r) => Number.isFinite(r.raroc));
}

export interface TenorRate {
  /** Longest tenor on the grid that clears the hurdle at the asked price, or null when none does. */
  maxTenor: number | null;
  /** Lowest price (bps) on the grid that clears the hurdle at the asked tenor, or the engine breakeven, or null. */
  minPrice: number | null;
  priceKey: "margin_bps" | "commission_bps";
}

export function bestTenorRate(g: Grid, ask: Terms, breakevenBps: number | null): TenorRate {
  const x = xs(g); const y = ys(g);
  const z = g.values as number[][];
  const key = priceKey(g);
  if (!x.length || !y.length || !Array.isArray(z[0])) return { maxTenor: null, minPrice: breakevenBps, priceKey: key };
  const j = nearest(x, g.ask?.x ?? ask[key]);
  const i = nearest(y, g.ask?.y ?? ask.tenor_years);
  const clearing = y.filter((_, r) => (z[r]?.[j] ?? -Infinity) >= g.hurdle);
  const maxTenor = clearing.length ? Math.max(...clearing) : null;
  const prices = x.filter((_, c) => (z[i]?.[c] ?? -Infinity) >= g.hurdle);
  const gridMin = prices.length ? Math.min(...prices) : null;
  const minPrice = key === "margin_bps" && breakevenBps !== null && Number.isFinite(breakevenBps) ? Math.ceil(breakevenBps) : gridMin;
  return { maxTenor, minPrice, priceKey: key };
}

export interface Offer { role: "recommended" | "alternative"; title: string; solution: Solution }

/** The recommended structure and up to two distinct alternatives, in a fixed order for every deal. */
export function bestOffers(opt: OptimizeResult | null): Offer[] {
  if (!opt) return [];
  const seen = new Set<string>();
  const out: Offer[] = [];
  const add = (s: Solution | null | undefined, role: Offer["role"], title: string) => {
    if (!s || out.length >= 3) return;
    const k = JSON.stringify(s.terms);
    if (seen.has(k)) return;
    seen.add(k);
    out.push({ role, title, solution: s });
  };
  add(opt.closest, "recommended", "Closest to the ask");
  add(opt.max_sva, "alternative", "Maximum value");
  for (const a of opt.alternatives ?? []) add(a as unknown as Solution, "alternative", a.label);
  for (const c of opt.counter_offers ?? []) add(c, "alternative", c.label);
  if (out.length && out[0].role !== "recommended") out[0] = { ...out[0], role: "recommended" };
  return out;
}
