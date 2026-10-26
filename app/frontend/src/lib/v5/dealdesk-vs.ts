/**
 * PLAN_R12 Session G (R11_FEEDBACK I14): "Structure it yourself" is always judged against the recommended structure.
 * The strip compares four figures for the structure on the panel and the recommended one, from the same engine run
 * (POST /proposals/{id}/forward-risk scores both): lifetime RAROC, SVA, ECL (day one) and P(Stage 2) next quarter.
 * Pure and tested (dealdesk-vs.test.ts); the component formats the numbers.
 */

export type VsKey = "raroc" | "sva" | "ecl" | "p_stage2";
export interface VsFigures { raroc: number; sva: number; ecl: number; p_stage2: number | null }
export interface VsRow { key: VsKey; label: string; mine: number | null; rec: number | null; delta: number | null; better: boolean | null }

const LABEL: Record<VsKey, string> = { raroc: "RAROC", sva: "SVA", ecl: "ECL (day one)", p_stage2: "P(Stage 2) next quarter" };
/** Higher is better for RAROC and SVA; lower is better for ECL and P(Stage 2). */
const HIGHER_BETTER: Record<VsKey, boolean> = { raroc: true, sva: true, ecl: false, p_stage2: false };
const EPS: Record<VsKey, number> = { raroc: 5e-5, sva: 5e-4, ecl: 5e-4, p_stage2: 5e-5 };

export function vsRows(mine: VsFigures | null, rec: VsFigures | null): VsRow[] {
  return (Object.keys(LABEL) as VsKey[]).map((k) => {
    const a = mine ? mine[k] : null;
    const b = rec ? rec[k] : null;
    const d = a === null || b === null || !Number.isFinite(a) || !Number.isFinite(b) ? null : a - b;
    const better = d === null || Math.abs(d) < EPS[k] ? null : HIGHER_BETTER[k] ? d > 0 : d < 0;
    return { key: k, label: LABEL[k], mine: a, rec: b, delta: d === null || Math.abs(d) < EPS[k] ? (d === null ? null : 0) : d, better };
  });
}

/** True when the panel holds the recommended structure itself (every delta zero). */
export function sameAsRecommended(rows: VsRow[]): boolean {
  return rows.every((r) => r.delta === 0 || (r.delta === null && r.mine === null));
}

/** One line in words: how many of the four are better, and the RAROC gap in points. */
export function vsVerdict(rows: VsRow[]): string {
  if (!rows.length || rows.every((r) => r.delta === null)) return "Comparing with the recommended structure…";
  if (sameAsRecommended(rows)) return "This is the recommended structure.";
  const known = rows.filter((r) => r.better !== null || r.delta === 0);
  const better = rows.filter((r) => r.better === true).length;
  const raroc = rows.find((r) => r.key === "raroc");
  const pts = raroc && raroc.delta !== null ? Math.abs(raroc.delta * 100).toFixed(1) : null;
  const gap = pts === null || raroc?.delta === 0 ? "the same RAROC" : `${pts} pts ${raroc && (raroc.delta ?? 0) > 0 ? "more" : "less"} RAROC`;
  return `Better on ${better} of ${known.length} against the recommended structure, with ${gap}.`;
}
