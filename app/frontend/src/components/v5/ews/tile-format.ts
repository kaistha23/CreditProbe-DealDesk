/**
 * PLAN_R10 G-TILES helpers (pure, tested): "n of N" and "n of N · x% of exposure" for a subset tile.
 */

function whole(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : Math.round(Number(v)).toLocaleString("en-US");
}

/** "368 of 5,412". */
export function ofN(n: number | null | undefined, total: number | null | undefined): string {
  return `${whole(n)} of ${whole(total)}`;
}

/** "368 of 5,412 · 4.9% of exposure"; the share is left out when unknown. */
export function ofNLine(n: number | null | undefined, total: number | null | undefined,
                        sharePct?: number | null, of = "exposure"): string {
  const head = ofN(n, total);
  if (sharePct === null || sharePct === undefined || !Number.isFinite(sharePct)) return head;
  return `${head} · ${Number(sharePct).toFixed(1)}% of ${of}`;
}

/** Share in percent of a part of a whole; null when the whole is zero or unknown. */
export function shareOf(part: number | null | undefined, totalAmount: number | null | undefined): number | null {
  if (part === null || part === undefined || !totalAmount || !Number.isFinite(totalAmount)) return null;
  return (100 * Number(part)) / Number(totalAmount);
}
