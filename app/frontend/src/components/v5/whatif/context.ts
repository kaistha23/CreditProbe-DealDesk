/**
 * R16 m (M4): the context answer a What-If thread opens with (backend/whatif_v5/chat/subject.py), before the
 * proposed scenario. Pure helpers (node --test); the card is `ContextCard` in blocks.tsx. Every figure is the API's
 * own number and text; nothing is recomputed here.
 */

export interface ContextFigure { key: string; label: string; value: number; unit: "sar_mn" | "pct" | "count"; text: string }
export interface ContextTrendRow { period: string; ead: number; share_pct: number; stage23_pct: number; ecl: number; coverage_pct: number }

export interface ContextBlock {
  type: "context";
  kind: "scope" | "book";
  domain: string;
  period: string;
  subject: string;
  title: string;
  headline: string;
  trend_line: string;
  top_line: string;
  plain_words: string[];
  figures: ContextFigure[];
  trend: ContextTrendRow[];
  top: { title: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[] };
  source: string;
}

/** The tiles in reading order: size, share, stress (Stage 2, Stage 3), loss (ECL), warnings. */
export const TILE_KEYS = ["ead", "share_pct", "stage2_ead", "stage3_ead", "ecl", "warned_owners"] as const;

export function contextTiles(block: Pick<ContextBlock, "figures">): ContextFigure[] {
  const by = new Map(block.figures.map((f) => [f.key, f]));
  return TILE_KEYS.map((k) => by.get(k)).filter((f): f is ContextFigure => Boolean(f));
}

/** The heading of the card: "Construction today" / "The corporate book today". */
export function contextHeading(block: Pick<ContextBlock, "title" | "period">): string {
  return `${block.title} today · ${block.period}`;
}

/** A trend cell: one decimal, with the unit. */
export function trendCell(key: keyof ContextTrendRow, v: number | string): string {
  if (typeof v === "string") return v;
  if (key === "ead" || key === "ecl") return v >= 1000 ? `${(v / 1000).toFixed(2)}bn` : `${v.toFixed(1)}m`;
  return `${v.toFixed(1)}%`;
}
